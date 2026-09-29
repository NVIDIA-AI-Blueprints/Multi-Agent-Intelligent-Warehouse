# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Proof SOP B — Equipment Failure / Recovery.

The acceptance criterion under test, in one sentence:

    Equipment recovery is complete only when the physical/operational state
    proves the recovery — not when the agent, MCP server, or executor says
    it succeeded.

Everything here is built around a fake *world*, not a fake *executor response*.
``FakeEquipmentWorld`` is the authoritative state; ``RecordingActionExecutor``
is a separate object that may or may not change that world and may or may not be
able to tell you whether it did. Keeping those two things apart is what makes it
possible to test the cases that matter:

  * the executor says EXECUTED and the world changed        -> complete
  * the executor says EXECUTED and the world did NOT change -> escalate
  * the executor says UNKNOWN and the world changed         -> complete (reconciled)
  * the executor says UNKNOWN and the world did NOT change  -> EXECUTION_INDETERMINATE
  * the world changed but the objective is not restored     -> do NOT complete

No test in this file asserts on prose, rationale wording, or model reasoning.
"""

from __future__ import annotations

import ast
import inspect
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from maiw_agents.contracts.agent import AgentDefinition
from maiw_agents.contracts.definitions import EQUIPMENT_AGENT_DEFINITION
from maiw_agents.contracts.procedure_state import ProcedureExecutionState, ProcedureStatus
from maiw_agents.contracts.runtime import AgentExecutionContext, check_capability_alignment
from maiw_agents.contracts.sop import SOPDefinition, load_sop, validate_sop
from maiw_agents.contracts.sop_v2 import EscalationReasonCode, RetryPolicy, ValidatorType
from maiw_agents.contracts.step_result import EvidenceRef, StepResult, StepStatus
from maiw_agents.sop_engine import SOPEngine, SOPStepExecutor
from maiw_agents.sop_engine.validators import get_registered_predicates

# Importing the equipment domain is what registers its predicates.
import maiw_agents.equipment  # noqa: F401
from maiw_agents.equipment.predicates import (
    equipment_recovery_complete,
    equipment_replacement_assigned,
    equipment_write_landed,
)

from conftest import SOP_DIR

SOP_PATH = SOP_DIR / "equipment" / "equipment_failure_recovery.v1.yaml"

SOP_ID = "equipment.equipment_failure_recovery"
SOP_VERSION = "1.0"

FAILED_ASSET = "FL-101"
REPLACEMENT_ASSET = "FL-204"
ZONE = "ZONE-A"

EXPECTED_STEP_SEQUENCE = [
    "detect_failure",
    "assess_operational_impact",
    "inspect_alternatives",
    "determine_recovery_strategy",
    "produce_recommendation",
    "wait_for_governance",
    "verify_execution",
    "verify_recovery",
]

# Steps that run before the governance pause (the engine halts *on*
# wait_for_governance, so it is executed but not completed in the first leg).
PRE_GOVERNANCE_STEPS = EXPECTED_STEP_SEQUENCE[:5]


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── The fake world: authoritative state, separate from executor responses ─────


class FakeEquipmentWorld:
    """
    An in-memory stand-in for authoritative warehouse equipment state.

    This is the *state source*, deliberately not the executor. Nothing here
    returns a success string; the only way to learn anything from this object is
    to read it.
    """

    def __init__(self) -> None:
        self.assets: dict[str, dict[str, Any]] = {
            FAILED_ASSET: {
                "asset_id": FAILED_ASSET,
                "equipment_type": "forklift",
                "model": "FL-3000",
                "zone": ZONE,
                "status": "offline",
                "owner_user": None,
            },
            REPLACEMENT_ASSET: {
                "asset_id": REPLACEMENT_ASSET,
                "equipment_type": "forklift",
                "model": "FL-3000",
                "zone": ZONE,
                "status": "available",
                "owner_user": None,
            },
        }
        self.reads = 0

    def set_status(self, asset_id: str, status: str, **fields: Any) -> None:
        self.assets[asset_id]["status"] = status
        self.assets[asset_id].update(fields)

    def as_state_dict(self) -> dict[str, Any]:
        """The shape a sealed WarehouseStateSnapshot presents to a predicate."""
        self.reads += 1
        assets = [dict(a) for a in self.assets.values()]
        return {
            "warehouse_id": "wh-test",
            "equipment": {
                "warehouse_id": "wh-test",
                "assets": assets,
                "total_count": len(assets),
                "available_count": sum(1 for a in assets if a["status"] == "available"),
            },
        }


class LiveSnapshot:
    """
    A snapshot handle that re-reads the world every time it is consulted.

    The SOP Engine calls ``model_dump()`` on whatever it is handed, so a retry of
    a STATE_PREDICATE step becomes a genuine fresh read of authoritative state —
    which is precisely the only retry this procedure is allowed to perform.
    """

    def __init__(self, world: FakeEquipmentWorld) -> None:
        self._world = world

    def model_dump(self) -> dict[str, Any]:
        return self._world.as_state_dict()


class RecordingActionExecutor:
    """
    Stands in for maiw_execution.EquipmentActionExecutor.

    Lives outside the agent package in production (apps/api/maiw_api/routers/
    equipment.py). Here it exists only so tests can count writes and decouple
    "what the executor reported" from "what actually happened".
    """

    def __init__(
        self,
        world: FakeEquipmentWorld,
        *,
        mutate: bool = True,
        outcome: str = "EXECUTED",
    ) -> None:
        self._world = world
        self._mutate = mutate
        self._outcome = outcome
        self.calls: list[dict[str, Any]] = []

    def execute_assignment(self, *, asset_id: str, assignee: str) -> str:
        self.calls.append({"asset_id": asset_id, "assignee": assignee})
        if self._mutate:
            self._world.set_status(asset_id, "assigned", owner_user=assignee)
        return self._outcome

    @property
    def write_count(self) -> int:
        return len(self.calls)


class GovernanceOutcomeStub:
    """Duck-typed governance outcome: the engine reads two attributes."""

    def __init__(self, decision_outcome: str = "APPROVED", execution_status: str = "EXECUTED"):
        self.decision_outcome = decision_outcome
        self.execution_status = execution_status


# ── Step executors: the two runtimes ──────────────────────────────────────────

_SCENARIO_FACTS: dict[str, Any] = {
    "warehouse.equipment.status": {
        "failed_asset_id": FAILED_ASSET,
        "failed_asset_status": "offline",
        "zone": ZONE,
        "candidate_count": 1,
        "alternate_asset_id": REPLACEMENT_ASSET,
    },
    "affected_asset": FAILED_ASSET,
    "affected_operation": "wave-17 picking",
    "severity": "high",
    "evidence": [f"{FAILED_ASSET} status=offline", f"{REPLACEMENT_ASSET} status=available"],
    "strategy": "reassign_alternate",
    "replacement_asset_id": REPLACEMENT_ASSET,
    "rationale": "Same type, same zone, currently available.",
    "recommendation_id": "rec-eq-001",
    "domain": "equipment",
    "capability": "warehouse.equipment.assign",
    "target": REPLACEMENT_ASSET,
    "priority": "high",
}


class _BaseRecoveryExecutor:
    """
    Shared step-fulfilment logic for both runtimes.

    It fulfils exactly one step per call and reports what it produced. It does
    NOT decide completion and does NOT choose the next step — the SOP Engine
    owns both. It never writes.
    """

    RUNTIME_NAME = "base"
    EVIDENCE_TYPE = "step_execution"

    def __init__(self, facts: dict[str, Any] | None = None) -> None:
        self.calls: list[tuple[str, int]] = []
        self.facts = dict(_SCENARIO_FACTS if facts is None else facts)

    @property
    def step_ids(self) -> list[str]:
        return [s for s, _ in self.calls]

    def _output_for(self, step) -> dict[str, Any]:
        output: dict[str, Any] = {}
        completion = step.completion
        if completion is None:
            return output
        if completion.schema_fields:
            for field in completion.schema_fields:
                if field in self.facts:
                    output[field] = self.facts[field]
        if completion.required_capability_result:
            cap_id = completion.required_capability_result
            if cap_id in self.facts:
                payload = dict(self.facts[cap_id])
                # Only surface the fields this step actually declares it needs.
                needed = completion.required_result_fields or list(payload)
                output[cap_id] = {k: v for k, v in payload.items() if k in needed}
        return output

    async def execute_step(
        self, *, definition, step, procedure_state, context, attempt
    ) -> StepResult:
        self.calls.append((step.id, attempt))

        status = StepStatus.COMPLETED
        if step.action == "emit_recommended_action":
            # The handoff. The runtime stops; it does not execute anything.
            status = StepStatus.WAITING_FOR_GOVERNANCE

        return StepResult(
            step_id=step.id,
            status=status,
            output=self._output_for(step),
            runtime=self.RUNTIME_NAME,
            attempt=attempt,
            started_at=_now(),
            completed_at=_now(),
            evidence=[
                EvidenceRef(
                    type=self.EVIDENCE_TYPE,
                    source=self.RUNTIME_NAME,
                    reference_id=context.trace_id or None,
                    timestamp=_now(),
                    summary=f"{self.RUNTIME_NAME} fulfilled step {step.id!r}",
                    metadata={
                        "step_id": step.id,
                        "action": step.action,
                        "sop_id": procedure_state.sop_id,
                        "attempt": attempt,
                    },
                )
            ],
            metadata={"action": step.action, "sop_id": procedure_state.sop_id},
        )


class DeterministicRecoveryExecutor(_BaseRecoveryExecutor):
    RUNTIME_NAME = "deterministic"
    EVIDENCE_TYPE = "step_execution"


class DeepAgentsRecoveryExecutor(_BaseRecoveryExecutor):
    """
    Mimics the Deep Agents runtime: a model returns a structured claim per step.

    ``tools`` is the tool list the model would be handed. It is READ-only by
    construction — see test_deep_agents_has_no_write_tools.
    """

    RUNTIME_NAME = "deep_agents"
    EVIDENCE_TYPE = "model_response"

    def __init__(self, facts: dict[str, Any] | None = None) -> None:
        super().__init__(facts)
        self.tools = [
            "warehouse.equipment.status",
            "warehouse.equipment.telemetry",
        ]
        self.steps_seen_per_call: list[int] = []

    async def execute_step(self, *, definition, step, procedure_state, context, attempt):
        # The runtime is handed exactly one step per invocation.
        self.steps_seen_per_call.append(1)
        return await super().execute_step(
            definition=definition,
            step=step,
            procedure_state=procedure_state,
            context=context,
            attempt=attempt,
        )


class FailingCapabilityExecutor(_BaseRecoveryExecutor):
    """Reports a capability as unavailable at a chosen step."""

    RUNTIME_NAME = "deterministic"

    def __init__(self, fail_step: str, reason: EscalationReasonCode) -> None:
        super().__init__()
        self._fail_step = fail_step
        self._reason = reason

    async def execute_step(self, *, definition, step, procedure_state, context, attempt):
        if step.id == self._fail_step:
            self.calls.append((step.id, attempt))
            return StepResult(
                step_id=step.id,
                status=StepStatus.ESCALATED,
                output={},
                runtime=self.RUNTIME_NAME,
                attempt=attempt,
                started_at=_now(),
                completed_at=_now(),
                escalation_reason=self._reason,
                escalation_message=f"{self._reason.value} at {step.id}",
            )
        return await super().execute_step(
            definition=definition,
            step=step,
            procedure_state=procedure_state,
            context=context,
            attempt=attempt,
        )


class StarvedExecutor(_BaseRecoveryExecutor):
    """Never produces the fields a given step needs — drives retry exhaustion."""

    RUNTIME_NAME = "deterministic"

    def __init__(self, starve_step: str) -> None:
        super().__init__()
        self._starve_step = starve_step

    def _output_for(self, step):
        if step.id == self._starve_step:
            return {}
        return super()._output_for(step)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def sop() -> SOPDefinition:
    return load_sop(SOP_PATH)


@pytest.fixture
def equipment_definition() -> AgentDefinition:
    return EQUIPMENT_AGENT_DEFINITION


@pytest.fixture
def world() -> FakeEquipmentWorld:
    return FakeEquipmentWorld()


@pytest.fixture
def recovery_context() -> AgentExecutionContext:
    return AgentExecutionContext(
        warehouse_id="wh-test",
        trace_id="trace-proof-sop-b",
        bounded_context={
            "failed_asset_id": FAILED_ASSET,
            "replacement_asset_id": REPLACEMENT_ASSET,
            "zone": ZONE,
        },
    )


async def run_to_governance(executor, sop, definition, context, world) -> ProcedureExecutionState:
    engine = SOPEngine(executor=executor, trace_id=context.trace_id)
    state = await engine.run_procedure(
        definition=definition,
        sop=sop,
        agent_task_id="task-eq-recovery",
        context=context,
        warehouse_state_snapshot=LiveSnapshot(world),
    )
    return state


async def resume_and_continue(
    executor,
    sop,
    definition,
    context,
    world,
    outcome: GovernanceOutcomeStub,
    paused: ProcedureExecutionState,
) -> ProcedureExecutionState:
    """Resume after governance, then run any remaining steps."""
    engine = SOPEngine(executor=executor, trace_id=context.trace_id)
    resumed = await engine.resume_after_governance(
        definition=definition,
        sop=sop,
        proc_state=paused,
        context=context,
        governance_outcome=outcome,
        warehouse_state_snapshot=LiveSnapshot(world),
    )
    if resumed.status is not ProcedureStatus.RUNNING:
        return resumed
    return await engine.run_procedure(
        definition=definition,
        sop=sop,
        agent_task_id=resumed.agent_task_id,
        context=context,
        initial_state=resumed,
        warehouse_state_snapshot=LiveSnapshot(world),
    )


async def full_recovery_run(
    executor, sop, definition, context, world, *, mutate=True, outcome="EXECUTED", decision="APPROVED"
):
    """The canonical end-to-end path, with the write performed outside the SOP."""
    paused = await run_to_governance(executor, sop, definition, context, world)
    action_executor = RecordingActionExecutor(world, mutate=mutate, outcome=outcome)

    if decision == "APPROVED":
        action_executor.execute_assignment(asset_id=REPLACEMENT_ASSET, assignee="wave-17")

    final = await resume_and_continue(
        executor,
        sop,
        definition,
        context,
        world,
        GovernanceOutcomeStub(decision_outcome=decision, execution_status=outcome),
        paused,
    )
    return final, action_executor


# ══════════════════════════════════════════════════════════════════════════════
# 1-5. The SOP definition itself
# ══════════════════════════════════════════════════════════════════════════════


def test_sop_yaml_loads(sop):
    assert sop.id == SOP_ID
    assert sop.version == SOP_VERSION
    assert sop.agent == "equipment"


def test_validate_sop_passes(sop):
    validate_sop(sop)  # raises SOPValidationError on failure
    check_capability_alignment(EQUIPMENT_AGENT_DEFINITION, sop)


def test_explicit_step_chain(sop):
    """The chain is declared, not inferred from YAML ordering."""
    by_id = {s.id: s for s in sop.steps}
    assert [s.id for s in sop.steps] == EXPECTED_STEP_SEQUENCE

    walked = []
    cursor = sop.steps[0].id
    while cursor is not None:
        walked.append(cursor)
        cursor = by_id[cursor].next_step_id
    assert walked == EXPECTED_STEP_SEQUENCE


def test_every_non_terminal_step_names_its_successor(sop):
    for step in sop.steps[:-1]:
        assert step.next_step_id is not None, f"{step.id} has no next_step_id"


def test_exactly_one_terminal_step(sop):
    terminal = [s.id for s in sop.steps if s.next_step_id is None]
    assert terminal == ["verify_recovery"]


def test_sop_cannot_declare_the_write_capability(sop):
    """validate_sop() structurally forbids it; assert the SOP honours that."""
    assert "warehouse.equipment.assign" not in sop.allowed_capabilities
    assert "warehouse.equipment.status" in sop.allowed_capabilities


def test_no_step_declares_a_blind_write_retry(sop):
    """RetryPolicy makes the unsafe configuration unbuildable — verify none try."""
    for step in sop.steps:
        if step.retry_policy is None:
            continue
        for code in step.retry_policy.retry_on:
            assert code.upper() not in ("EXECUTION_INDETERMINATE", "WRITE_AMBIGUOUS")


def test_governance_step_has_no_retry_policy(sop):
    """Resuming must never re-issue the write, so the pause step gets no budget."""
    by_id = {s.id: s for s in sop.steps}
    assert by_id["wait_for_governance"].retry_policy is None


# ══════════════════════════════════════════════════════════════════════════════
# 6. Validators per step
# ══════════════════════════════════════════════════════════════════════════════


def test_validator_type_per_step(sop):
    by_id = {s.id: s for s in sop.steps}
    expected = {
        "detect_failure": ValidatorType.CAPABILITY_RESULT,
        "assess_operational_impact": ValidatorType.SCHEMA,
        "inspect_alternatives": ValidatorType.CAPABILITY_RESULT,
        "determine_recovery_strategy": ValidatorType.SCHEMA,
        "produce_recommendation": ValidatorType.SCHEMA,
        "wait_for_governance": ValidatorType.STATE_PREDICATE,
        "verify_execution": ValidatorType.STATE_PREDICATE,
        "verify_recovery": ValidatorType.STATE_PREDICATE,
    }
    actual = {sid: by_id[sid].completion.validator_type for sid in expected}
    assert actual == expected


def test_no_critical_step_uses_legacy_success(sop):
    for step in sop.steps:
        assert step.completion is not None, f"{step.id} would fall back to LEGACY_SUCCESS"
        assert step.completion.validator_type is not ValidatorType.LEGACY_SUCCESS


# ══════════════════════════════════════════════════════════════════════════════
# 20. Named predicate registration + isolated predicate behaviour
# ══════════════════════════════════════════════════════════════════════════════


def test_recovery_predicates_are_registered():
    registered = get_registered_predicates()
    for name in (
        "equipment_write_landed",
        "equipment_replacement_assigned",
        "equipment_recovery_complete",
    ):
        assert name in registered, f"{name} not registered by the equipment domain"


def test_sop_predicate_names_all_resolve(sop):
    registered = get_registered_predicates()
    for step in sop.steps:
        if step.completion.validator_type is ValidatorType.STATE_PREDICATE:
            assert step.completion.predicate_name in registered


def test_predicate_registration_is_domain_owned():
    """Equipment semantics must not live in the generic validator engine."""
    from maiw_agents.sop_engine import validators as generic

    source = inspect.getsource(generic)
    for token in ("forklift", "equipment_recovery_complete", "equipment_write_landed"):
        assert token not in source, f"{token!r} leaked into the generic validator engine"


class TestPredicatesInIsolation:
    def test_write_landed_false_when_still_available(self, world):
        assert not equipment_write_landed(
            world.as_state_dict(), {"replacement_asset_id": REPLACEMENT_ASSET}
        )

    def test_write_landed_true_once_status_changes(self, world):
        world.set_status(REPLACEMENT_ASSET, "assigned")
        assert equipment_write_landed(
            world.as_state_dict(), {"replacement_asset_id": REPLACEMENT_ASSET}
        )

    def test_write_landed_false_for_unknown_asset(self, world):
        assert not equipment_write_landed(
            world.as_state_dict(), {"replacement_asset_id": "NOPE-1"}
        )

    def test_replacement_assigned_rejects_wrong_transition(self, world):
        """Left the available pool, but into maintenance — not what we asked for."""
        world.set_status(REPLACEMENT_ASSET, "maintenance")
        args = {"replacement_asset_id": REPLACEMENT_ASSET, "expected_status": "assigned"}
        assert equipment_write_landed(world.as_state_dict(), {"replacement_asset_id": REPLACEMENT_ASSET})
        assert not equipment_replacement_assigned(world.as_state_dict(), args)

    def test_recovery_complete_happy_path(self, world):
        world.set_status(REPLACEMENT_ASSET, "assigned")
        assert equipment_recovery_complete(
            world.as_state_dict(),
            {
                "replacement_asset_id": REPLACEMENT_ASSET,
                "failed_asset_id": FAILED_ASSET,
                "expected_status": "assigned",
                "expected_zone": ZONE,
            },
        )

    def test_recovery_incomplete_when_failed_asset_back_in_service(self, world):
        world.set_status(REPLACEMENT_ASSET, "assigned")
        world.set_status(FAILED_ASSET, "available")
        assert not equipment_recovery_complete(
            world.as_state_dict(),
            {
                "replacement_asset_id": REPLACEMENT_ASSET,
                "failed_asset_id": FAILED_ASSET,
                "expected_status": "assigned",
            },
        )

    def test_recovery_incomplete_when_replacement_in_wrong_zone(self, world):
        world.set_status(REPLACEMENT_ASSET, "assigned", zone="ZONE-Z")
        assert not equipment_recovery_complete(
            world.as_state_dict(),
            {
                "replacement_asset_id": REPLACEMENT_ASSET,
                "failed_asset_id": FAILED_ASSET,
                "expected_status": "assigned",
                "expected_zone": ZONE,
            },
        )

    def test_predicates_do_not_mutate_state(self, world):
        before = world.as_state_dict()
        equipment_recovery_complete(
            before,
            {"replacement_asset_id": REPLACEMENT_ASSET, "failed_asset_id": FAILED_ASSET},
        )
        assert before == world.as_state_dict()


# ══════════════════════════════════════════════════════════════════════════════
# 7 + 9. Governance pause, and the normal deterministic recovery
# ══════════════════════════════════════════════════════════════════════════════


async def test_procedure_pauses_at_wait_for_governance(sop, equipment_definition, recovery_context, world):
    executor = DeterministicRecoveryExecutor()
    paused = await run_to_governance(executor, sop, equipment_definition, recovery_context, world)

    assert paused.status is ProcedureStatus.WAITING_FOR_GOVERNANCE
    assert paused.current_step_id == "wait_for_governance"
    assert paused.completed_step_ids == PRE_GOVERNANCE_STEPS


async def test_pause_runs_no_step_beyond_the_handoff(sop, equipment_definition, recovery_context, world):
    """The hard invariant: nothing executes until governance returns."""
    executor = DeterministicRecoveryExecutor()
    paused = await run_to_governance(executor, sop, equipment_definition, recovery_context, world)

    assert executor.step_ids == PRE_GOVERNANCE_STEPS + ["wait_for_governance"]
    assert "verify_execution" not in executor.step_ids
    assert "verify_recovery" not in executor.step_ids
    assert paused.step_results["wait_for_governance"].validation_result is None


async def test_deterministic_normal_recovery_completes(sop, equipment_definition, recovery_context, world):
    executor = DeterministicRecoveryExecutor()
    final, action_executor = await full_recovery_run(
        executor, sop, equipment_definition, recovery_context, world
    )

    assert final.status is ProcedureStatus.COMPLETED
    assert final.completed_step_ids == EXPECTED_STEP_SEQUENCE
    assert action_executor.write_count == 1


async def test_deterministic_recovery_completes_on_state_not_on_response(
    sop, equipment_definition, recovery_context, world
):
    """The decisive assertion: the verifying steps used STATE_PREDICATE."""
    executor = DeterministicRecoveryExecutor()
    final, _ = await full_recovery_run(executor, sop, equipment_definition, recovery_context, world)

    for step_id in ("wait_for_governance", "verify_execution", "verify_recovery"):
        result = final.step_results[step_id]
        assert result.validation_result.validator_type is ValidatorType.STATE_PREDICATE
        assert result.validation_result.valid is True


# ══════════════════════════════════════════════════════════════════════════════
# 7 (deep agents) + 8. Deep Agents runtime and cross-runtime equivalence
# ══════════════════════════════════════════════════════════════════════════════


async def test_deep_agents_normal_recovery_completes(sop, equipment_definition, recovery_context, world):
    executor = DeepAgentsRecoveryExecutor()
    final, action_executor = await full_recovery_run(
        executor, sop, equipment_definition, recovery_context, world
    )

    assert final.status is ProcedureStatus.COMPLETED
    assert final.completed_step_ids == EXPECTED_STEP_SEQUENCE
    assert action_executor.write_count == 1


async def test_deep_agents_receives_one_step_at_a_time(sop, equipment_definition, recovery_context, world):
    executor = DeepAgentsRecoveryExecutor()
    await full_recovery_run(executor, sop, equipment_definition, recovery_context, world)

    assert all(n == 1 for n in executor.steps_seen_per_call)
    assert len(executor.steps_seen_per_call) == len(executor.calls)


async def test_deep_agents_cannot_jump_to_verify_recovery(sop, equipment_definition, recovery_context, world):
    """It never sees a later step before the engine gives it one."""
    executor = DeepAgentsRecoveryExecutor()
    paused = await run_to_governance(executor, sop, equipment_definition, recovery_context, world)

    assert paused.status is ProcedureStatus.WAITING_FOR_GOVERNANCE
    assert "verify_recovery" not in executor.step_ids


def test_deep_agents_cannot_choose_the_next_step():
    source = inspect.getsource(DeepAgentsRecoveryExecutor)
    source += inspect.getsource(_BaseRecoveryExecutor.execute_step)
    assert "next_step_id" not in source
    assert "current_step_id" not in source


def test_deep_agents_has_no_write_tools():
    from maiw_agents.contracts.registry import SKILL_REGISTRY, CapabilityClass

    executor = DeepAgentsRecoveryExecutor()
    for cap_id in executor.tools:
        entry = SKILL_REGISTRY.get(cap_id)
        assert entry is not None, f"unknown capability {cap_id}"
        assert entry.capability_class not in (
            CapabilityClass.WRITE,
            CapabilityClass.EMERGENCY_WRITE,
        )


async def test_deep_agents_returns_step_results_only(sop, equipment_definition, recovery_context, world):
    executor = DeepAgentsRecoveryExecutor()
    final, _ = await full_recovery_run(executor, sop, equipment_definition, recovery_context, world)

    assert isinstance(executor, SOPStepExecutor)
    for result in final.step_results.values():
        assert isinstance(result, StepResult)


async def test_cross_runtime_equivalence(sop, equipment_definition, recovery_context):
    """Procedure semantics must not be a property of the runtime."""
    det_world, deep_world = FakeEquipmentWorld(), FakeEquipmentWorld()
    det_exec, deep_exec = DeterministicRecoveryExecutor(), DeepAgentsRecoveryExecutor()

    det_final, det_writes = await full_recovery_run(
        det_exec, sop, equipment_definition, recovery_context, det_world
    )
    deep_final, deep_writes = await full_recovery_run(
        deep_exec, sop, equipment_definition, recovery_context, deep_world
    )

    # Same completed steps, same order, same terminal state.
    assert det_final.status is deep_final.status is ProcedureStatus.COMPLETED
    assert det_final.completed_step_ids == deep_final.completed_step_ids
    assert det_exec.step_ids == deep_exec.step_ids

    # Structurally equivalent validator decisions.
    def verdicts(state):
        return {
            sid: (r.validation_result.validator_type, r.validation_result.valid)
            for sid, r in state.step_results.items()
        }

    assert verdicts(det_final) == verdicts(deep_final)

    # Same governance timing and the same single write.
    assert det_writes.write_count == deep_writes.write_count == 1

    # The runtime label is the only thing that differs.
    assert det_final.step_results["detect_failure"].runtime == "deterministic"
    assert deep_final.step_results["detect_failure"].runtime == "deep_agents"


async def test_cross_runtime_governance_pause_timing(sop, equipment_definition, recovery_context):
    det_paused = await run_to_governance(
        DeterministicRecoveryExecutor(), sop, equipment_definition, recovery_context, FakeEquipmentWorld()
    )
    deep_paused = await run_to_governance(
        DeepAgentsRecoveryExecutor(), sop, equipment_definition, recovery_context, FakeEquipmentWorld()
    )

    assert det_paused.current_step_id == deep_paused.current_step_id == "wait_for_governance"
    assert det_paused.completed_step_ids == deep_paused.completed_step_ids


# ══════════════════════════════════════════════════════════════════════════════
# 10-15. Failure paths
# ══════════════════════════════════════════════════════════════════════════════


async def test_no_alternate_asset_escalates_capability_unavailable(
    sop, equipment_definition, recovery_context, world
):
    """Path A: nothing to recover with is a real answer, not a retry loop."""
    executor = FailingCapabilityExecutor(
        "inspect_alternatives", EscalationReasonCode.CAPABILITY_UNAVAILABLE
    )
    state = await run_to_governance(executor, sop, equipment_definition, recovery_context, world)

    assert state.status is ProcedureStatus.ESCALATED
    assert (
        state.step_results["inspect_alternatives"].escalation_reason
        is EscalationReasonCode.CAPABILITY_UNAVAILABLE
    )
    assert "wait_for_governance" not in executor.step_ids


async def test_governance_rejection_performs_no_write(sop, equipment_definition, recovery_context, world):
    """Path B: rejected means nothing happened. Terminal state: ESCALATED."""
    executor = DeterministicRecoveryExecutor()
    final, action_executor = await full_recovery_run(
        executor,
        sop,
        equipment_definition,
        recovery_context,
        world,
        decision="REJECTED",
        outcome="NOT_EXECUTED",
    )

    assert action_executor.write_count == 0
    assert final.status is ProcedureStatus.ESCALATED
    assert world.assets[REPLACEMENT_ASSET]["status"] == "available"
    assert "verify_execution" not in executor.step_ids


async def test_unknown_write_reconciled_by_reread_completes(
    sop, equipment_definition, recovery_context, world
):
    """
    Reliability Path A: UNKNOWN -> reconcile -> CONFIRMED_EXECUTED -> COMPLETED.

    The executor could not say what happened. The world can.
    """
    executor = DeterministicRecoveryExecutor()
    final, action_executor = await full_recovery_run(
        executor, sop, equipment_definition, recovery_context, world, outcome="UNKNOWN", mutate=True
    )

    assert final.status is ProcedureStatus.COMPLETED
    assert action_executor.write_count == 1


async def test_unknown_write_unconfirmed_escalates_indeterminate(
    sop, equipment_definition, recovery_context, world
):
    """Reliability Path B: UNKNOWN -> reconcile -> INDETERMINATE -> escalate."""
    executor = DeterministicRecoveryExecutor()
    final, action_executor = await full_recovery_run(
        executor, sop, equipment_definition, recovery_context, world, outcome="UNKNOWN", mutate=False
    )

    assert final.status is ProcedureStatus.ESCALATED
    assert (
        final.step_results["wait_for_governance"].escalation_reason
        is EscalationReasonCode.EXECUTION_INDETERMINATE
    )
    assert action_executor.write_count == 1, "the ambiguous write must not be re-issued"


async def test_no_blind_write_retry(sop, equipment_definition, recovery_context, world):
    """
    write attempt -> UNKNOWN -> no second write -> reread -> reconcile.

    ActionExecutor must be called exactly once for the write.
    """
    executor = DeterministicRecoveryExecutor()
    paused = await run_to_governance(executor, sop, equipment_definition, recovery_context, world)

    action_executor = RecordingActionExecutor(world, mutate=False, outcome="UNKNOWN")
    action_executor.execute_assignment(asset_id=REPLACEMENT_ASSET, assignee="wave-17")
    assert action_executor.write_count == 1

    reads_before = world.reads
    final = await resume_and_continue(
        executor,
        sop,
        equipment_definition,
        recovery_context,
        world,
        GovernanceOutcomeStub(execution_status="UNKNOWN"),
        paused,
    )

    assert action_executor.write_count == 1, "no second write may be issued"
    assert world.reads > reads_before, "resolution must come from a re-read"
    assert final.status is ProcedureStatus.ESCALATED


async def test_executor_success_string_cannot_complete_the_sop(
    sop, equipment_definition, recovery_context, world
):
    """
    The headline invariant.

    Governance APPROVED, executor returned EXECUTED — and the world did not
    change. The procedure must not complete.
    """
    executor = DeterministicRecoveryExecutor()
    final, action_executor = await full_recovery_run(
        executor, sop, equipment_definition, recovery_context, world, mutate=False, outcome="EXECUTED"
    )

    assert action_executor.write_count == 1
    assert final.status is ProcedureStatus.ESCALATED
    assert final.status is not ProcedureStatus.COMPLETED
    assert (
        final.step_results["wait_for_governance"].escalation_reason
        is EscalationReasonCode.VALIDATION_FAILED
    )


async def test_execution_confirmed_but_recovery_predicate_fails(
    sop, equipment_definition, recovery_context, world
):
    """
    Path D — the subtle one.

    The write landed and the transition was the intended one, so verify_execution
    passes. But the failed asset came back online, so the operational objective
    is not restored. The procedure must NOT complete.
    """
    executor = DeterministicRecoveryExecutor()
    paused = await run_to_governance(executor, sop, equipment_definition, recovery_context, world)

    action_executor = RecordingActionExecutor(world, mutate=True, outcome="EXECUTED")
    action_executor.execute_assignment(asset_id=REPLACEMENT_ASSET, assignee="wave-17")
    # Somebody put the faulty forklift back into the available pool.
    world.set_status(FAILED_ASSET, "available")

    final = await resume_and_continue(
        executor,
        sop,
        equipment_definition,
        recovery_context,
        world,
        GovernanceOutcomeStub(),
        paused,
    )

    assert final.step_results["verify_execution"].validation_result.valid is True
    assert final.status is ProcedureStatus.ESCALATED
    assert "verify_recovery" not in final.completed_step_ids
    assert (
        final.step_results["verify_recovery"].escalation_reason
        is EscalationReasonCode.RETRY_BUDGET_EXHAUSTED
    )


async def test_wrong_transition_fails_verify_execution(
    sop, equipment_definition, recovery_context, world
):
    """The asset left the available pool — into maintenance. Not a recovery."""
    executor = DeterministicRecoveryExecutor()
    paused = await run_to_governance(executor, sop, equipment_definition, recovery_context, world)
    world.set_status(REPLACEMENT_ASSET, "maintenance")

    final = await resume_and_continue(
        executor,
        sop,
        equipment_definition,
        recovery_context,
        world,
        GovernanceOutcomeStub(),
        paused,
    )

    # wait_for_governance passes (something changed) but verify_execution does not.
    assert final.step_results["wait_for_governance"].validation_result.valid is True
    assert final.status is ProcedureStatus.ESCALATED
    assert "verify_execution" not in final.completed_step_ids


async def test_retry_budget_exhaustion_escalates(sop, equipment_definition, recovery_context, world):
    """A step whose required fields never arrive exhausts its bounded budget."""
    executor = StarvedExecutor("assess_operational_impact")
    state = await run_to_governance(executor, sop, equipment_definition, recovery_context, world)

    assert state.status is ProcedureStatus.ESCALATED
    result = state.step_results["assess_operational_impact"]
    assert result.escalation_reason is EscalationReasonCode.RETRY_BUDGET_EXHAUSTED
    assert state.attempt_by_step["assess_operational_impact"] == 2


async def test_safe_reread_retry_is_bounded_and_read_only(
    sop, equipment_definition, recovery_context, world
):
    """verify_recovery retries by re-reading state, never by re-writing."""
    executor = DeterministicRecoveryExecutor()
    paused = await run_to_governance(executor, sop, equipment_definition, recovery_context, world)

    action_executor = RecordingActionExecutor(world, mutate=True, outcome="EXECUTED")
    action_executor.execute_assignment(asset_id=REPLACEMENT_ASSET, assignee="wave-17")
    world.set_status(FAILED_ASSET, "available")  # forces verify_recovery to fail

    reads_before = world.reads
    final = await resume_and_continue(
        executor, sop, equipment_definition, recovery_context, world, GovernanceOutcomeStub(), paused
    )

    assert final.status is ProcedureStatus.ESCALATED
    assert action_executor.write_count == 1, "retries must never re-issue the write"
    assert world.reads > reads_before, "retries must be re-reads"
    assert final.attempt_by_step["verify_recovery"] == 3  # bounded by max_attempts


async def test_timeout_produces_structured_timeout_escalation(
    sop, equipment_definition, recovery_context, world
):
    import asyncio

    class _SlowExecutor(_BaseRecoveryExecutor):
        RUNTIME_NAME = "deterministic"

        async def execute_step(self, *, definition, step, procedure_state, context, attempt):
            if step.id == "detect_failure":
                await asyncio.sleep(5)
            return await super().execute_step(
                definition=definition,
                step=step,
                procedure_state=procedure_state,
                context=context,
                attempt=attempt,
            )

    fast_sop = load_sop(SOP_PATH)
    fast_sop.steps[0].timeout_seconds = 0.01
    # Drop the re-read budget so the timeout itself is the terminal outcome
    # rather than the budget it would otherwise exhaust.
    fast_sop.steps[0].retry_policy = None

    state = await run_to_governance(
        _SlowExecutor(), fast_sop, equipment_definition, recovery_context, world
    )

    assert state.status is ProcedureStatus.FAILED
    assert state.step_results["detect_failure"].status is StepStatus.TIMED_OUT
    assert state.step_results["detect_failure"].escalation_reason is EscalationReasonCode.TIMEOUT


async def test_timeout_inside_a_retry_budget_exhausts_the_budget(
    sop, equipment_definition, recovery_context, world
):
    """With a re-read budget, repeated timeouts terminate as budget exhaustion."""
    import asyncio

    class _SlowExecutor(_BaseRecoveryExecutor):
        RUNTIME_NAME = "deterministic"

        async def execute_step(self, *, definition, step, procedure_state, context, attempt):
            if step.id == "detect_failure":
                await asyncio.sleep(5)
            return await super().execute_step(
                definition=definition,
                step=step,
                procedure_state=procedure_state,
                context=context,
                attempt=attempt,
            )

    budgeted = load_sop(SOP_PATH)
    budgeted.steps[0].timeout_seconds = 0.01

    state = await run_to_governance(
        _SlowExecutor(), budgeted, equipment_definition, recovery_context, world
    )

    assert state.status is ProcedureStatus.ESCALATED
    assert (
        state.step_results["detect_failure"].escalation_reason
        is EscalationReasonCode.RETRY_BUDGET_EXHAUSTED
    )
    assert state.attempt_by_step["detect_failure"] == 3


async def test_missing_required_input_escalates_missing_data(
    sop, equipment_definition, world
):
    """detect_failure declares required_inputs; without them it must not run."""
    bare_context = AgentExecutionContext(
        warehouse_id="wh-test", trace_id="trace-proof-sop-b", bounded_context={}
    )
    executor = DeterministicRecoveryExecutor()
    state = await run_to_governance(executor, sop, equipment_definition, bare_context, world)

    assert state.status is ProcedureStatus.ESCALATED
    assert executor.calls == [], "the step must not execute without its declared inputs"


# ══════════════════════════════════════════════════════════════════════════════
# 14 + 15. Evidence and trace identity
# ══════════════════════════════════════════════════════════════════════════════


async def test_evidence_retained_for_every_completed_step(
    sop, equipment_definition, recovery_context, world
):
    executor = DeterministicRecoveryExecutor()
    final, _ = await full_recovery_run(executor, sop, equipment_definition, recovery_context, world)

    for step_id in final.completed_step_ids:
        assert final.step_results[step_id].evidence, f"{step_id} completed with no evidence"
    assert final.evidence_refs, "procedure-level evidence must accumulate"


async def test_post_write_evidence_names_the_predicate(
    sop, equipment_definition, recovery_context, world
):
    executor = DeterministicRecoveryExecutor()
    final, _ = await full_recovery_run(executor, sop, equipment_definition, recovery_context, world)

    expected = {
        "wait_for_governance": "equipment_write_landed",
        "verify_execution": "equipment_replacement_assigned",
        "verify_recovery": "equipment_recovery_complete",
    }
    for step_id, predicate in expected.items():
        evidence = final.step_results[step_id].evidence
        assert any(e.metadata.get("predicate_name") == predicate for e in evidence), (
            f"{step_id} evidence does not name {predicate}"
        )


async def test_no_chain_of_thought_in_evidence(sop, equipment_definition, recovery_context, world):
    banned = {
        "chain_of_thought",
        "scratchpad",
        "hidden_reasoning",
        "raw_reasoning",
        "system_prompt",
        "thoughts",
        "reasoning",
    }
    executor = DeepAgentsRecoveryExecutor()
    final, _ = await full_recovery_run(executor, sop, equipment_definition, recovery_context, world)

    for result in final.step_results.values():
        assert not (banned & set(result.output)), f"CoT leaked into {result.step_id} output"
        for ref in result.evidence:
            assert not (banned & set(ref.metadata)), f"CoT leaked into {result.step_id} evidence"


async def test_procedure_trace_identity_is_linked(sop, equipment_definition, recovery_context, world):
    """procedure_execution_id / agent_task_id / trace_id / recommendation_id."""
    executor = DeterministicRecoveryExecutor()
    final, _ = await full_recovery_run(executor, sop, equipment_definition, recovery_context, world)

    assert final.procedure_execution_id
    assert final.agent_task_id == "task-eq-recovery"
    assert final.trace_id == "trace-proof-sop-b"
    assert final.sop_id == SOP_ID
    assert final.sop_version == SOP_VERSION

    # The recommendation is linked through the produce_recommendation output.
    rec = final.step_results["produce_recommendation"].output
    assert rec["recommendation_id"] == "rec-eq-001"

    # The governance outcome is recorded on the pause step.
    gov = final.step_results["wait_for_governance"].output
    assert gov["governance_decision"] == "APPROVED"
    assert gov["execution_status"] == "EXECUTED"


# ══════════════════════════════════════════════════════════════════════════════
# 18-19. Authority boundary (static)
# ══════════════════════════════════════════════════════════════════════════════

_AGENT_PKG = Path(__file__).resolve().parent.parent / "maiw_agents"


def _python_sources(root: Path):
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_no_action_executor_import_in_agent_package():
    """
    No module under maiw_agents/ may import maiw_execution or ActionExecutor.

    Checked over the AST rather than raw text, so the many *docstrings* that
    correctly describe the boundary ("this module NEVER calls ActionExecutor")
    are not mistaken for violations of it.
    """
    offenders = []
    for path in _python_sources(_AGENT_PKG):
        rel = path.relative_to(_AGENT_PKG)
        for node in ast.walk(_parse(path)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] == "maiw_execution":
                        offenders.append(f"{rel}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.split(".")[0] == "maiw_execution":
                    offenders.append(f"{rel}: from {module} import ...")
                for alias in node.names:
                    if "ActionExecutor" in alias.name:
                        offenders.append(f"{rel}: imports {alias.name}")
    assert offenders == [], f"authority boundary violated: {offenders}"


def test_sop_engine_imports_nothing_write_capable():
    engine_path = _AGENT_PKG / "sop_engine" / "engine.py"
    source = engine_path.read_text(encoding="utf-8")
    import_lines = [
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    forbidden = ("maiw_execution", "ActionExecutor", "DecisionEngine", "MCPClient")
    for line in import_lines:
        for token in forbidden:
            assert token not in line, f"SOP Engine imports {token}: {line}"


def test_equipment_package_never_executes_a_write():
    """
    EquipmentAgent stays assessment/recommendation only.

    The equipment package may build proposals and consult the DecisionEngine
    (EQUIPMENT_AGENT_DEFINITION permits the latter), but it may never reach an
    executor or a write-capable MCP client.
    """
    offenders = []
    for path in _python_sources(_AGENT_PKG / "equipment"):
        for node in ast.walk(_parse(path)):
            # A reference to an executor symbol in executable code (not prose).
            if isinstance(node, ast.Name) and "ActionExecutor" in node.id:
                offenders.append(f"{path.name}: name {node.id}")
            elif isinstance(node, ast.Attribute) and "ActionExecutor" in node.attr:
                offenders.append(f"{path.name}: attribute {node.attr}")
            elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "maiw_execution"
            ):
                offenders.append(f"{path.name}: from {node.module}")
    assert offenders == [], f"equipment package holds write authority: {offenders}"


def test_equipment_definition_cannot_invoke_action_executor():
    boundary = EQUIPMENT_AGENT_DEFINITION.governance_boundary
    assert boundary.may_invoke_action_executor is False
    assert "WRITE" not in boundary.allowed_capability_classes
    assert "EMERGENCY_WRITE" not in boundary.allowed_capability_classes


def test_predicates_use_no_expression_evaluation():
    """Named predicates only — no eval(), no expression language."""
    banned = {"eval", "exec", "compile", "__import__"}
    tree = _parse(_AGENT_PKG / "equipment" / "predicates.py")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in banned, f"predicates.py calls {node.func.id}()"


# ══════════════════════════════════════════════════════════════════════════════
# 21/23. No generic loop DSL was introduced
# ══════════════════════════════════════════════════════════════════════════════


def test_no_loop_dsl_in_sop(sop):
    raw = SOP_PATH.read_text(encoding="utf-8")
    for token in ("repeat_until:", "foreach:", "while:", "expression:", "eval:"):
        assert token not in raw, f"loop/expression DSL token {token!r} present in SOP"


def test_retry_policy_is_the_only_repetition_mechanism(sop):
    for step in sop.steps:
        if step.retry_policy is not None:
            assert isinstance(step.retry_policy, RetryPolicy)
            assert 1 <= step.retry_policy.max_attempts <= 10
            assert step.retry_policy.backoff_seconds >= 0.0
