# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Proof SOP C — Picking / Inventory Exception.

The acceptance criterion under test, in one sentence:

    The SOP Engine controls the loop. The model may provide evidence, but it
    cannot decide that the loop is finished.

And its completion twin, inherited from Proof SOP B and re-proved here for a
second domain:

    A picking exception is resolved only when authoritative inventory state
    proves it — not when an adjustment was submitted, approved, or reported
    successful.

Everything here is built around a fake *world*, not a fake *executor response*.
``FakeInventoryWorld`` is the authoritative state; ``RecordingActionExecutor``
is a separate object that may or may not change that world and may or may not be
able to tell you whether it did. Keeping those two things apart is what makes it
possible to test the cases that matter:

  * the world reconciles on the first re-read      -> complete, 1 iteration
  * the world reconciles on the third re-read      -> complete, 3 iterations
  * the world never reconciles                     -> escalate, budget spent
  * the model insists it reconciled but it did not -> escalate anyway
  * quantity is sufficient but held nowhere        -> escalate, no model guess
  * the executor says UNKNOWN and the world changed-> complete (reconciled)
  * the executor says UNKNOWN and it did not       -> EXECUTION_INDETERMINATE

No test in this file asserts on prose, rationale wording, or model reasoning.
"""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from maiw_agents.contracts.agent import AgentDefinition
from maiw_agents.contracts.definitions import INVENTORY_AGENT_DEFINITION
from maiw_agents.contracts.procedure_state import ProcedureExecutionState, ProcedureStatus
from maiw_agents.contracts.registry import SKILL_REGISTRY, CapabilityClass
from maiw_agents.contracts.runtime import AgentExecutionContext, check_capability_alignment
from maiw_agents.contracts.sop import SOPDefinition, load_sop, validate_sop
from maiw_agents.contracts.sop_v2 import EscalationReasonCode, ValidatorType
from maiw_agents.contracts.step_result import EvidenceRef, StepResult, StepStatus
from maiw_agents.sop_engine import SOPEngine
from maiw_agents.sop_engine.validators import get_registered_predicates

# Importing the inventory domain is what registers its predicates.
import maiw_agents.inventory  # noqa: F401
from maiw_agents.inventory.predicates import (
    inventory_exception_resolved,
    inventory_quantity_sufficient,
    inventory_write_landed,
)

from conftest import SOP_DIR

SOP_PATH = SOP_DIR / "inventory" / "picking_inventory_exception.v1.yaml"

SOP_ID = "inventory.picking_inventory_exception"
SOP_VERSION = "1.0"

SKU = "SKU-88231"
BASELINE_AVAILABLE = 4
REQUIRED_QUANTITY = 12
PICK_LOCATION = "A-01-03"
ALTERNATE_LOCATION = "C-07-11"

LOOP_STEP = "reassess_inventory_state"
WRITE_STEP = "propose_resolution"
ZONE_ONLY_STEP = "inspect_alternate_locations"

# The full ordered chain in a zone-picking facility.
ZONE_STEP_SEQUENCE = [
    "detect_exception",
    "classify_exception",
    "select_picking_strategy",
    ZONE_ONLY_STEP,
    "evaluate_resolution_options",
    WRITE_STEP,
    LOOP_STEP,
    "resume_picking",
]

# In a discrete-picking facility the engine skips the zone-only step.
DISCRETE_STEP_SEQUENCE = [s for s in ZONE_STEP_SEQUENCE if s != ZONE_ONLY_STEP]

PRE_GOVERNANCE_ZONE_STEPS = ZONE_STEP_SEQUENCE[:5]


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── The fake world: authoritative state, separate from executor responses ─────


class FakeInventoryWorld:
    """
    An in-memory stand-in for authoritative warehouse inventory state.

    This is the *state source*, deliberately not the executor. Nothing here
    returns a success string; the only way to learn anything from this object is
    to read it — which is exactly what the bounded loop does, once per iteration.

    ``reconcile_after_reads`` models the thing a bounded loop exists for: the
    warehouse catching up some time after the adjustment was authorized.
    """

    def __init__(
        self,
        *,
        available: int = BASELINE_AVAILABLE,
        location_count: int = 1,
        reconcile_after_reads: int | None = None,
        reconciled_available: int = REQUIRED_QUANTITY,
        reconciled_location_count: int = 1,
    ) -> None:
        self.available = available
        self.location_count = location_count
        self.reads = 0
        self._reconcile_after_reads = reconcile_after_reads
        self._reconciled_available = reconciled_available
        self._reconciled_location_count = reconciled_location_count

    def set_available(self, quantity: int, *, location_count: int | None = None) -> None:
        self.available = quantity
        if location_count is not None:
            self.location_count = location_count

    def as_state_dict(self) -> dict[str, Any]:
        """The shape a sealed WarehouseStateSnapshot presents to a predicate."""
        self.reads += 1
        if (
            self._reconcile_after_reads is not None
            and self.reads >= self._reconcile_after_reads
        ):
            self.available = self._reconciled_available
            self.location_count = self._reconciled_location_count
        return {
            "warehouse_id": "wh-test",
            "inventory": {
                "warehouse_id": "wh-test",
                "items": [
                    {
                        "sku": SKU,
                        "name": "Widget, 40mm",
                        "total_available": self.available,
                        "is_low_stock": self.available < REQUIRED_QUANTITY,
                        "location_count": self.location_count,
                    }
                ],
                "total_items": 1,
                "low_stock_count": 1 if self.available < REQUIRED_QUANTITY else 0,
            },
        }


class LiveSnapshot:
    """
    A snapshot handle that re-reads the world every time it is consulted.

    The SOP Engine calls ``model_dump()`` on whatever it is handed, so each
    iteration of the bounded loop becomes a genuine fresh read of authoritative
    state — which is precisely the only repetition this procedure permits.
    """

    def __init__(self, world: FakeInventoryWorld) -> None:
        self._world = world

    def model_dump(self) -> dict[str, Any]:
        return self._world.as_state_dict()


class RecordingActionExecutor:
    """
    Stands in for the inventory ActionExecutor.

    Lives outside the agent package in production. Here it exists only so tests
    can count writes and decouple "what the executor reported" from "what
    actually happened".
    """

    def __init__(
        self,
        world: FakeInventoryWorld,
        *,
        mutate: bool = True,
        outcome: str = "EXECUTED",
        adjust_to: int = REQUIRED_QUANTITY,
    ) -> None:
        self._world = world
        self._mutate = mutate
        self._outcome = outcome
        self._adjust_to = adjust_to
        self.calls: list[dict[str, Any]] = []

    def execute_replenishment(self, *, sku: str, quantity: int) -> str:
        self.calls.append({"sku": sku, "quantity": quantity})
        if self._mutate:
            self._world.set_available(self._adjust_to)
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
    "warehouse.inventory.lookup": {
        "sku": SKU,
        "total_available": BASELINE_AVAILABLE,
        "required_quantity": REQUIRED_QUANTITY,
        "location_id": PICK_LOCATION,
    },
    "warehouse.inventory.locate": {
        "candidate_location_count": 1,
        "alternate_location_id": ALTERNATE_LOCATION,
    },
    "exception_type": "short_pick",
    "severity": "high",
    "sku": SKU,
    "required_quantity": REQUIRED_QUANTITY,
    "observed_available": BASELINE_AVAILABLE,
    "evidence": [f"{SKU} available={BASELINE_AVAILABLE} required={REQUIRED_QUANTITY}"],
    "picking_strategy": "zone",
    "strategy_source": "facility_configuration",
    "rationale": "Facility DC-47 is configured for zone picking.",
    "options": ["replenish_from_reserve", "substitute_equivalent_sku"],
    "selected_option": "replenish_from_reserve",
    "replenishment_source_location": ALTERNATE_LOCATION,
    "expected_available_after": REQUIRED_QUANTITY,
    "resolution": "replenished_from_reserve",
    "available_after": REQUIRED_QUANTITY,
    "pick_can_resume": True,
    "escalation_reason": "loop_budget_exhausted",
    "attempts": 3,
    "handoff_summary": "Reserve replenishment did not reconcile; physical count required.",
}


class _BaseExceptionExecutor:
    """
    Shared step-fulfilment logic for both runtimes.

    It fulfils exactly one step per call and reports what it produced. It does
    NOT decide completion, does NOT choose the next step, and — the point of
    Proof SOP C — has no way to say whether the loop should run again. It never
    writes.
    """

    RUNTIME_NAME = "base"
    EVIDENCE_TYPE = "step_execution"

    def __init__(self, facts: dict[str, Any] | None = None) -> None:
        self.calls: list[tuple[str, int]] = []
        self.facts = dict(_SCENARIO_FACTS if facts is None else facts)

    @property
    def step_ids(self) -> list[str]:
        return [s for s, _ in self.calls]

    def calls_for(self, step_id: str) -> list[tuple[str, int]]:
        return [c for c in self.calls if c[0] == step_id]

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


class DeterministicExceptionExecutor(_BaseExceptionExecutor):
    RUNTIME_NAME = "deterministic"
    EVIDENCE_TYPE = "step_execution"


class DeepAgentsExceptionExecutor(_BaseExceptionExecutor):
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
            "warehouse.inventory.lookup",
            "warehouse.inventory.locate",
        ]
        self.steps_seen_per_call: list[int] = []

    async def execute_step(self, *, definition, step, procedure_state, context, attempt):
        self.steps_seen_per_call.append(1)
        return await super().execute_step(
            definition=definition,
            step=step,
            procedure_state=procedure_state,
            context=context,
            attempt=attempt,
        )


class FailingCapabilityExecutor(_BaseExceptionExecutor):
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


class StarvedExecutor(_BaseExceptionExecutor):
    """Never produces the fields a given step needs — drives retry exhaustion."""

    RUNTIME_NAME = "deterministic"

    def __init__(self, starve_step: str) -> None:
        super().__init__()
        self._starve_step = starve_step

    def _output_for(self, step):
        if step.id == self._starve_step:
            return {}
        return super()._output_for(step)


class OverconfidentExecutor(_BaseExceptionExecutor):
    """
    A model that reports the loop step complete on every single pass.

    Proof SOP C's central adversary: it is right about nothing and says so
    confidently, every time.
    """

    RUNTIME_NAME = "deep_agents"

    async def execute_step(self, *, definition, step, procedure_state, context, attempt):
        result = await super().execute_step(
            definition=definition, step=step, procedure_state=procedure_state,
            context=context, attempt=attempt,
        )
        if step.id == LOOP_STEP:
            return result.model_copy(update={
                "status": StepStatus.COMPLETED,
                "output": {
                    **result.output,
                    "resolved": True,
                    "exit_loop": True,
                    "iterations_remaining": 0,
                },
            })
        return result


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def sop() -> SOPDefinition:
    return load_sop(SOP_PATH)


@pytest.fixture
def inventory_definition() -> AgentDefinition:
    return INVENTORY_AGENT_DEFINITION


@pytest.fixture
def world() -> FakeInventoryWorld:
    return FakeInventoryWorld()


def make_context(strategy: str = "zone") -> AgentExecutionContext:
    """
    Bounded context for one facility.

    ``facility_picking_strategy`` is deterministic operational configuration.
    The model is told which facility it is in; it is never offered a choice.
    """
    return AgentExecutionContext(
        warehouse_id="wh-test",
        trace_id="trace-proof-sop-c",
        bounded_context={
            "sku": SKU,
            "required_quantity": REQUIRED_QUANTITY,
            "facility_picking_strategy": strategy,
            "pick_location": PICK_LOCATION,
        },
    )


@pytest.fixture
def zone_context() -> AgentExecutionContext:
    return make_context("zone")


@pytest.fixture
def discrete_context() -> AgentExecutionContext:
    return make_context("discrete")


async def run_to_governance(executor, sop, definition, context, world):
    engine = SOPEngine(executor=executor, trace_id=context.trace_id)
    return await engine.run_procedure(
        definition=definition,
        sop=sop,
        agent_task_id="task-inv-exception",
        context=context,
        warehouse_state_snapshot=LiveSnapshot(world),
    )


async def resume_and_continue(executor, sop, definition, context, world, outcome, paused):
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


async def full_run(
    executor, sop, definition, context, world,
    *, mutate=True, outcome="EXECUTED", decision="APPROVED", adjust_to=REQUIRED_QUANTITY,
):
    """The canonical end-to-end path, with the write performed outside the SOP."""
    paused = await run_to_governance(executor, sop, definition, context, world)
    action_executor = RecordingActionExecutor(
        world, mutate=mutate, outcome=outcome, adjust_to=adjust_to
    )
    if decision == "APPROVED":
        action_executor.execute_replenishment(sku=SKU, quantity=REQUIRED_QUANTITY)

    final = await resume_and_continue(
        executor, sop, definition, context, world,
        GovernanceOutcomeStub(decision_outcome=decision, execution_status=outcome),
        paused,
    )
    return final, action_executor


# ══════════════════════════════════════════════════════════════════════════════
# 1. The SOP definition itself
# ══════════════════════════════════════════════════════════════════════════════


def test_sop_yaml_loads(sop):
    assert sop.id == SOP_ID
    assert sop.version == SOP_VERSION
    assert sop.agent == "inventory"
    assert sop.runtime_profile == "strict"


def test_validate_sop_passes(sop):
    validate_sop(sop)  # raises SOPValidationError on failure
    check_capability_alignment(INVENTORY_AGENT_DEFINITION, sop)


def test_step_count(sop):
    assert len(sop.steps) == 9


def test_explicit_step_chain(sop):
    by_id = {s.id: s for s in sop.steps}
    chain = [
        ("detect_exception", "classify_exception"),
        ("classify_exception", "select_picking_strategy"),
        ("select_picking_strategy", ZONE_ONLY_STEP),
        (ZONE_ONLY_STEP, "evaluate_resolution_options"),
        ("evaluate_resolution_options", WRITE_STEP),
        (WRITE_STEP, LOOP_STEP),
        (LOOP_STEP, "resume_picking"),
    ]
    for step_id, expected_next in chain:
        assert by_id[step_id].next_step_id == expected_next


def test_exactly_two_terminal_steps(sop):
    """One success terminal, one escalation terminal — and nothing else."""
    terminal = {s.id for s in sop.steps if s.next_step_id is None}
    assert terminal == {"resume_picking", "escalate_to_human"}


def test_every_non_terminal_step_names_its_successor(sop):
    for step in sop.steps:
        if step.id not in ("resume_picking", "escalate_to_human"):
            assert step.next_step_id is not None, f"{step.id} has no explicit successor"


def test_sop_cannot_declare_the_write_capability(sop):
    for cap in sop.allowed_capabilities:
        assert not cap.startswith("warehouse.inventory.adjust")
        assert "_direct" not in cap


def test_declaring_an_inventory_write_capability_is_rejected(sop):
    """The guard is real, not decorative."""
    from maiw_agents.contracts.sop import SOPValidationError

    bad = sop.model_copy(update={
        "allowed_capabilities": sop.allowed_capabilities + ["warehouse.inventory.adjust"]
    })
    with pytest.raises(SOPValidationError, match="not allowed"):
        validate_sop(bad)


def test_no_step_declares_a_blind_write_retry(sop):
    for step in sop.steps:
        if step.retry_policy is None:
            continue
        retry_on = {r.upper() for r in step.retry_policy.retry_on}
        assert "WRITE_AMBIGUOUS" not in retry_on
        assert "EXECUTION_INDETERMINATE" not in retry_on


def test_governance_step_has_neither_retry_nor_loop(sop):
    """
    The single most dangerous thing this SOP could do is repeat the write.
    Neither repetition mechanism is attached to the step that performs it.
    """
    step = next(s for s in sop.steps if s.id == WRITE_STEP)
    assert step.action == "emit_recommended_action"
    assert step.retry_policy is None
    assert step.loop is None


def test_validator_type_per_step(sop):
    expected = {
        "detect_exception": ValidatorType.CAPABILITY_RESULT,
        "classify_exception": ValidatorType.SCHEMA,
        "select_picking_strategy": ValidatorType.SCHEMA,
        ZONE_ONLY_STEP: ValidatorType.CAPABILITY_RESULT,
        "evaluate_resolution_options": ValidatorType.SCHEMA,
        WRITE_STEP: ValidatorType.STATE_PREDICATE,
        LOOP_STEP: ValidatorType.STATE_PREDICATE,
        "resume_picking": ValidatorType.SCHEMA,
        "escalate_to_human": ValidatorType.SCHEMA,
    }
    actual = {s.id: s.completion.validator_type for s in sop.steps if s.completion}
    assert actual == expected


def test_no_step_uses_legacy_success(sop):
    for step in sop.steps:
        assert step.completion is not None, f"{step.id} has no completion spec"
        assert step.completion.validator_type is not ValidatorType.LEGACY_SUCCESS


def test_every_step_declares_evidence_requirements(sop):
    for step in sop.steps:
        assert step.evidence_requirements, f"{step.id} declares no evidence requirements"


def test_every_step_declares_a_timeout_except_the_governance_pause(sop):
    for step in sop.steps:
        if step.id == WRITE_STEP:
            continue  # bounded by governance, not by a step clock
        assert step.timeout_seconds is not None, f"{step.id} has no timeout"


# ══════════════════════════════════════════════════════════════════════════════
# 2. The bounded loop, as declared
# ══════════════════════════════════════════════════════════════════════════════


def test_exactly_one_step_loops(sop):
    looping = [s.id for s in sop.steps if s.loop is not None]
    assert looping == [LOOP_STEP]


def test_loop_is_bounded_both_ways(sop):
    loop = next(s for s in sop.steps if s.id == LOOP_STEP).loop
    assert loop.max_iterations == 3
    assert loop.max_total_seconds == 120.0


def test_loop_targets_are_declared(sop):
    loop = next(s for s in sop.steps if s.id == LOOP_STEP).loop
    assert loop.exit_step_id == "resume_picking"
    assert loop.exhaustion_step_id == "escalate_to_human"


def test_loop_step_carries_no_retry_policy(sop):
    """One repetition budget per step, so iterations and attempts cannot diverge."""
    step = next(s for s in sop.steps if s.id == LOOP_STEP)
    assert step.retry_policy is None


def test_loop_exit_criterion_is_a_state_predicate(sop):
    step = next(s for s in sop.steps if s.id == LOOP_STEP)
    assert step.completion.validator_type is ValidatorType.STATE_PREDICATE
    assert step.completion.predicate_name == "inventory_exception_resolved"


def test_sop_yaml_contains_no_workflow_dsl():
    raw = SOP_PATH.read_text(encoding="utf-8")
    for token in ("repeat_until:", "foreach:", "while:", "expression:", "eval:", "lambda"):
        assert token not in raw, f"loop/expression DSL token {token!r} present in SOP"


def test_sop_yaml_declares_no_loop_back_edge():
    """The loop body is the step. A multi-step back-edge is not expressible."""
    raw = SOP_PATH.read_text(encoding="utf-8")
    assert "loop_back_step_id" not in raw
    assert "body_step_ids" not in raw


# ══════════════════════════════════════════════════════════════════════════════
# 3. Predicates: registration and behaviour in isolation
# ══════════════════════════════════════════════════════════════════════════════


def test_inventory_predicates_are_registered():
    registry = get_registered_predicates()
    for name in (
        "inventory_write_landed",
        "inventory_quantity_sufficient",
        "inventory_exception_resolved",
    ):
        assert name in registry


def test_sop_predicate_names_all_resolve(sop):
    from maiw_agents.domain_predicates import production_predicates

    registry = production_predicates()
    for step in sop.steps:
        if step.completion and step.completion.validator_type is ValidatorType.STATE_PREDICATE:
            assert step.completion.predicate_name in registry


def test_predicate_registration_is_domain_owned():
    """Registering inventory predicates must not require editing the engine."""
    from maiw_agents.domain_predicates import PREDICATE_DOMAIN_MODULES

    assert "maiw_agents.inventory.predicates" in PREDICATE_DOMAIN_MODULES


def test_inventory_predicate_names_do_not_collide_with_other_domains():
    from maiw_agents.equipment.predicates import EQUIPMENT_PREDICATES
    from maiw_agents.inventory.predicates import INVENTORY_PREDICATES
    from maiw_agents.wave.predicates import WAVE_PREDICATES

    assert not set(INVENTORY_PREDICATES) & set(EQUIPMENT_PREDICATES)
    assert not set(INVENTORY_PREDICATES) & set(WAVE_PREDICATES)


class TestPredicatesInIsolation:
    """The predicates are the completion criterion, so they get tested alone."""

    @staticmethod
    def state(available: int, *, location_count: int = 1, low: bool | None = None):
        return {
            "inventory": {
                "items": [
                    {
                        "sku": SKU,
                        "total_available": available,
                        "location_count": location_count,
                        "is_low_stock": (
                            available < REQUIRED_QUANTITY if low is None else low
                        ),
                    }
                ]
            }
        }

    def test_write_landed_is_direction_agnostic(self):
        args = {"sku": SKU, "baseline_available": 4}
        assert inventory_write_landed(self.state(12), args) is True
        assert inventory_write_landed(self.state(2), args) is True, (
            "a downward correction is still evidence the write landed"
        )
        assert inventory_write_landed(self.state(4), args) is False

    def test_write_landed_false_when_sku_absent(self):
        assert inventory_write_landed({"inventory": {"items": []}},
                                      {"sku": SKU, "baseline_available": 4}) is False

    def test_write_landed_false_when_inventory_unreadable(self):
        """Missing data is never proof."""
        assert inventory_write_landed({}, {"sku": SKU, "baseline_available": 4}) is False

    def test_quantity_sufficient_boundary(self):
        args = {"sku": SKU, "required_quantity": REQUIRED_QUANTITY}
        assert inventory_quantity_sufficient(self.state(11), args) is False
        assert inventory_quantity_sufficient(self.state(12), args) is True
        assert inventory_quantity_sufficient(self.state(13), args) is True

    def test_quantity_sufficient_rejects_a_requirement_of_zero(self):
        """A SOP asking whether zero units exist is asking for no proof."""
        assert inventory_quantity_sufficient(
            self.state(0), {"sku": SKU, "required_quantity": 0}
        ) is False

    def test_exception_resolved_requires_a_pickable_location(self):
        """Stock on the record with nowhere to pick it is not a resolution."""
        args = {"sku": SKU, "required_quantity": REQUIRED_QUANTITY, "min_locations": 1}
        assert inventory_exception_resolved(self.state(12, location_count=1), args) is True
        assert inventory_exception_resolved(self.state(12, location_count=0), args) is False

    def test_exception_resolved_is_strictly_stronger_than_sufficient(self):
        state = self.state(12, location_count=0)
        args = {"sku": SKU, "required_quantity": REQUIRED_QUANTITY}
        assert inventory_quantity_sufficient(state, args) is True
        assert inventory_exception_resolved(state, args) is False

    def test_low_stock_check_is_opt_in(self):
        state = self.state(12, low=True)
        base = {"sku": SKU, "required_quantity": REQUIRED_QUANTITY}
        assert inventory_exception_resolved(state, base) is True
        assert inventory_exception_resolved(state, {**base, "require_not_low_stock": True}) is False

    def test_booleans_are_not_read_as_counts(self):
        state = {"inventory": {"items": [
            {"sku": SKU, "total_available": True, "location_count": 1}
        ]}}
        assert inventory_quantity_sufficient(
            state, {"sku": SKU, "required_quantity": 1}
        ) is False

    def test_sealed_snapshot_nesting_is_unwrapped(self):
        sealed = {"state": self.state(12)}
        assert inventory_exception_resolved(
            sealed, {"sku": SKU, "required_quantity": REQUIRED_QUANTITY}
        ) is True

    def test_alternate_producer_field_spellings_are_tolerated(self):
        """maiw_world projections spell these sku_id / quantity_available."""
        projection = {"inventory": {"items": [
            {"sku_id": SKU, "quantity_available": 12, "location_count": 1}
        ]}}
        assert inventory_quantity_sufficient(
            projection, {"sku": SKU, "required_quantity": REQUIRED_QUANTITY}
        ) is True

    def test_per_location_rows_are_aggregated(self):
        per_location = {"inventory": {"items": [
            {"sku_id": SKU, "quantity_available": 7},
            {"sku_id": SKU, "quantity_available": 5},
        ]}}
        args = {"sku": SKU, "required_quantity": REQUIRED_QUANTITY}
        assert inventory_quantity_sufficient(per_location, args) is True
        assert inventory_exception_resolved(
            per_location, {**args, "min_locations": 2}
        ) is True

    def test_predicates_never_mutate_the_state_they_read(self):
        state = self.state(12)
        before = str(state)
        inventory_exception_resolved(state, {"sku": SKU, "required_quantity": 12})
        inventory_quantity_sufficient(state, {"sku": SKU, "required_quantity": 12})
        inventory_write_landed(state, {"sku": SKU, "baseline_available": 4})
        assert str(state) == before


# ══════════════════════════════════════════════════════════════════════════════
# 4. Deterministic runtime — the normal path
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_procedure_pauses_at_the_governance_handoff(
    sop, inventory_definition, zone_context, world
):
    executor = DeterministicExceptionExecutor()
    paused = await run_to_governance(executor, sop, inventory_definition, zone_context, world)

    assert paused.status is ProcedureStatus.WAITING_FOR_GOVERNANCE
    assert paused.current_step_id == WRITE_STEP


@pytest.mark.asyncio
async def test_pause_runs_no_step_beyond_the_handoff(
    sop, inventory_definition, zone_context, world
):
    executor = DeterministicExceptionExecutor()
    await run_to_governance(executor, sop, inventory_definition, zone_context, world)

    assert executor.step_ids == PRE_GOVERNANCE_ZONE_STEPS + [WRITE_STEP]
    assert LOOP_STEP not in executor.step_ids


@pytest.mark.asyncio
async def test_deterministic_normal_resolution_completes(
    sop, inventory_definition, zone_context, world
):
    executor = DeterministicExceptionExecutor()
    final, action_executor = await full_run(
        executor, sop, inventory_definition, zone_context, world
    )

    assert final.status is ProcedureStatus.COMPLETED
    assert final.completed_step_ids == ZONE_STEP_SEQUENCE
    assert action_executor.write_count == 1


@pytest.mark.asyncio
async def test_exact_step_order_is_engine_determined(
    sop, inventory_definition, zone_context, world
):
    executor = DeterministicExceptionExecutor()
    await full_run(executor, sop, inventory_definition, zone_context, world)

    assert executor.step_ids == (
        PRE_GOVERNANCE_ZONE_STEPS + [WRITE_STEP, LOOP_STEP, "resume_picking"]
    )


@pytest.mark.asyncio
async def test_resolution_rests_on_state_not_on_response(
    sop, inventory_definition, zone_context
):
    """
    The executor reports EXECUTED and the world did NOT change. The procedure
    must not complete.
    """
    world = FakeInventoryWorld()
    executor = DeterministicExceptionExecutor()

    final, _ = await full_run(
        executor, sop, inventory_definition, zone_context, world, mutate=False
    )

    assert final.status is ProcedureStatus.ESCALATED
    assert "resume_picking" not in final.completed_step_ids


# ══════════════════════════════════════════════════════════════════════════════
# 5. The bounded loop at runtime
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_loop_exits_on_first_iteration_when_already_reconciled(
    sop, inventory_definition, zone_context, world
):
    executor = DeterministicExceptionExecutor()
    final, _ = await full_run(executor, sop, inventory_definition, zone_context, world)

    assert final.attempt_by_step[LOOP_STEP] == 1
    assert len(executor.calls_for(LOOP_STEP)) == 1
    assert final.status is ProcedureStatus.COMPLETED


@pytest.mark.asyncio
async def test_loop_keeps_reading_until_the_world_catches_up(
    sop, inventory_definition, zone_context
):
    """
    Failure path D. The adjustment landed (so the governance gate passes) but
    availability only reaches the required quantity on the third read of the
    loop. The loop must notice, and must not have given up early.
    """
    world = FakeInventoryWorld()
    executor = DeterministicExceptionExecutor()

    paused = await run_to_governance(executor, sop, inventory_definition, zone_context, world)
    action_executor = RecordingActionExecutor(world, mutate=True, adjust_to=6)
    action_executor.execute_replenishment(sku=SKU, quantity=REQUIRED_QUANTITY)
    # Partial replenishment lands first; the rest arrives two reads later.
    world._reconcile_after_reads = world.reads + 3

    final = await resume_and_continue(
        executor, sop, inventory_definition, zone_context, world,
        GovernanceOutcomeStub(), paused,
    )

    assert final.status is ProcedureStatus.COMPLETED
    assert final.attempt_by_step[LOOP_STEP] > 1, "the loop had to look more than once"
    assert final.attempt_by_step[LOOP_STEP] <= 3, "and never more than its budget"
    assert action_executor.write_count == 1, "re-reading is not re-writing"


@pytest.mark.asyncio
async def test_loop_exhaustion_escalates_to_the_human_handoff(
    sop, inventory_definition, zone_context
):
    """Failure path A: inventory still short after the maximum safe re-reads."""
    world = FakeInventoryWorld()
    executor = DeterministicExceptionExecutor()

    paused = await run_to_governance(executor, sop, inventory_definition, zone_context, world)
    action_executor = RecordingActionExecutor(world, mutate=True, adjust_to=5)
    action_executor.execute_replenishment(sku=SKU, quantity=REQUIRED_QUANTITY)

    final = await resume_and_continue(
        executor, sop, inventory_definition, zone_context, world,
        GovernanceOutcomeStub(), paused,
    )

    assert final.status is ProcedureStatus.ESCALATED
    assert final.loop_exhausted_step_ids == [LOOP_STEP]
    assert final.attempt_by_step[LOOP_STEP] == 3
    assert "escalate_to_human" in final.completed_step_ids
    assert "resume_picking" not in final.completed_step_ids
    assert action_executor.write_count == 1


@pytest.mark.asyncio
async def test_loop_exhaustion_carries_a_typed_reason_not_prose(
    sop, inventory_definition, zone_context
):
    world = FakeInventoryWorld()
    executor = DeterministicExceptionExecutor()
    paused = await run_to_governance(executor, sop, inventory_definition, zone_context, world)
    RecordingActionExecutor(world, mutate=True, adjust_to=5).execute_replenishment(
        sku=SKU, quantity=REQUIRED_QUANTITY
    )

    final = await resume_and_continue(
        executor, sop, inventory_definition, zone_context, world,
        GovernanceOutcomeStub(), paused,
    )

    assert (
        final.step_results[LOOP_STEP].escalation_reason
        is EscalationReasonCode.LOOP_BUDGET_EXHAUSTED
    )


@pytest.mark.asyncio
async def test_a_clean_escalation_step_does_not_launder_the_outcome(
    sop, inventory_definition, zone_context
):
    """
    escalate_to_human runs and validates perfectly. The PROCEDURE still ends
    ESCALATED — reporting an unresolved exception tidily does not resolve it.
    """
    world = FakeInventoryWorld()
    executor = DeterministicExceptionExecutor()
    paused = await run_to_governance(executor, sop, inventory_definition, zone_context, world)
    RecordingActionExecutor(world, mutate=True, adjust_to=5).execute_replenishment(
        sku=SKU, quantity=REQUIRED_QUANTITY
    )

    final = await resume_and_continue(
        executor, sop, inventory_definition, zone_context, world,
        GovernanceOutcomeStub(), paused,
    )

    assert final.step_results["escalate_to_human"].status is StepStatus.COMPLETED
    assert final.status is ProcedureStatus.ESCALATED


@pytest.mark.asyncio
async def test_model_cannot_declare_the_loop_finished(
    sop, inventory_definition, zone_context
):
    """
    THE test for Proof SOP C. A model claims the loop step is complete on every
    pass; authoritative state never agrees. The loop runs its full budget and
    escalates anyway.
    """
    world = FakeInventoryWorld()
    executor = OverconfidentExecutor()
    paused = await run_to_governance(executor, sop, inventory_definition, zone_context, world)
    RecordingActionExecutor(world, mutate=True, adjust_to=5).execute_replenishment(
        sku=SKU, quantity=REQUIRED_QUANTITY
    )

    final = await resume_and_continue(
        executor, sop, inventory_definition, zone_context, world,
        GovernanceOutcomeStub(), paused,
    )

    assert len(executor.calls_for(LOOP_STEP)) == 3
    assert final.status is ProcedureStatus.ESCALATED
    assert "resume_picking" not in final.completed_step_ids


@pytest.mark.asyncio
async def test_each_loop_iteration_re_reads_authoritative_state(
    sop, inventory_definition, zone_context
):
    world = FakeInventoryWorld()
    executor = DeterministicExceptionExecutor()
    paused = await run_to_governance(executor, sop, inventory_definition, zone_context, world)
    RecordingActionExecutor(world, mutate=True, adjust_to=5).execute_replenishment(
        sku=SKU, quantity=REQUIRED_QUANTITY
    )
    reads_at_resume = world.reads

    await resume_and_continue(
        executor, sop, inventory_definition, zone_context, world,
        GovernanceOutcomeStub(), paused,
    )

    assert world.reads - reads_at_resume >= 3, "each iteration is a fresh read"


# ══════════════════════════════════════════════════════════════════════════════
# 6. Facility strategy variation
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_zone_facility_inspects_alternate_locations(
    sop, inventory_definition, zone_context, world
):
    executor = DeterministicExceptionExecutor()
    final, _ = await full_run(executor, sop, inventory_definition, zone_context, world)

    assert ZONE_ONLY_STEP in final.completed_step_ids
    assert final.completed_step_ids == ZONE_STEP_SEQUENCE


@pytest.mark.asyncio
async def test_discrete_facility_skips_alternate_location_search(
    sop, inventory_definition, discrete_context, world
):
    """
    Same SOP, same engine, same agent — different facility configuration.
    The variation is a declarative StepCondition, not a per-strategy code path.
    """
    executor = DeterministicExceptionExecutor()
    final, _ = await full_run(executor, sop, inventory_definition, discrete_context, world)

    assert final.status is ProcedureStatus.COMPLETED
    assert ZONE_ONLY_STEP not in executor.step_ids, "the step must not even run"
    assert final.completed_step_ids == DISCRETE_STEP_SEQUENCE


@pytest.mark.asyncio
async def test_both_strategies_reach_the_same_verdict_by_different_routes(
    sop, inventory_definition
):
    outcomes = {}
    for strategy in ("zone", "discrete"):
        world = FakeInventoryWorld()
        executor = DeterministicExceptionExecutor()
        final, _ = await full_run(
            executor, sop, inventory_definition, make_context(strategy), world
        )
        outcomes[strategy] = (final.status, ZONE_ONLY_STEP in final.completed_step_ids)

    assert outcomes["zone"] == (ProcedureStatus.COMPLETED, True)
    assert outcomes["discrete"] == (ProcedureStatus.COMPLETED, False)


@pytest.mark.asyncio
async def test_the_loop_is_bounded_identically_under_both_strategies(
    sop, inventory_definition
):
    """Strategy changes the route, never the safety bound."""
    for strategy in ("zone", "discrete"):
        world = FakeInventoryWorld()
        executor = DeterministicExceptionExecutor()
        paused = await run_to_governance(
            executor, sop, inventory_definition, make_context(strategy), world
        )
        RecordingActionExecutor(world, mutate=True, adjust_to=5).execute_replenishment(
            sku=SKU, quantity=REQUIRED_QUANTITY
        )
        final = await resume_and_continue(
            executor, sop, inventory_definition, make_context(strategy), world,
            GovernanceOutcomeStub(), paused,
        )
        assert final.attempt_by_step[LOOP_STEP] == 3
        assert final.status is ProcedureStatus.ESCALATED


def test_strategy_comes_from_configuration_not_from_the_model(sop):
    """
    The strategy step declares facility_picking_strategy as a required input, so
    the engine refuses to run it if configuration did not supply one.
    """
    step = next(s for s in sop.steps if s.id == "select_picking_strategy")
    assert "facility_picking_strategy" in (step.required_inputs or [])


@pytest.mark.asyncio
async def test_missing_strategy_configuration_escalates_missing_data(
    sop, inventory_definition, world
):
    context = AgentExecutionContext(
        warehouse_id="wh-test",
        trace_id="trace-no-strategy",
        bounded_context={"sku": SKU, "required_quantity": REQUIRED_QUANTITY},
    )
    executor = DeterministicExceptionExecutor()

    final = await run_to_governance(executor, sop, inventory_definition, context, world)

    assert final.status is ProcedureStatus.ESCALATED
    assert (
        final.step_results["select_picking_strategy"].escalation_reason
        is EscalationReasonCode.MISSING_DATA
    )


def test_only_the_strategies_the_codebase_supports_are_modelled(sop):
    """
    Documented limitation: batch, cluster and hybrid picking are not represented
    anywhere in this codebase, so this SOP does not pretend to support them.
    """
    raw = SOP_PATH.read_text(encoding="utf-8")
    for unsupported in ("batch_picking", "cluster_picking", "hybrid_picking"):
        assert unsupported not in raw


def test_no_per_strategy_agent_method_exists():
    """Strategy must not be a branch in Python. There is no inventory agent class."""
    import maiw_agents.inventory as inv

    for name in dir(inv):
        lowered = name.lower()
        assert not (lowered.startswith("zone_") or lowered.startswith("discrete_"))


# ══════════════════════════════════════════════════════════════════════════════
# 7. Write ambiguity — the loop must never amplify a write
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_unknown_write_reconciled_by_reread_completes(
    sop, inventory_definition, zone_context, world
):
    """The executor cannot say what happened; authoritative state can."""
    executor = DeterministicExceptionExecutor()
    final, action_executor = await full_run(
        executor, sop, inventory_definition, zone_context, world,
        mutate=True, outcome="UNKNOWN",
    )

    assert final.status is ProcedureStatus.COMPLETED
    assert action_executor.write_count == 1


@pytest.mark.asyncio
async def test_unknown_write_unconfirmed_escalates_indeterminate(
    sop, inventory_definition, zone_context, world
):
    executor = DeterministicExceptionExecutor()
    final, action_executor = await full_run(
        executor, sop, inventory_definition, zone_context, world,
        mutate=False, outcome="UNKNOWN",
    )

    assert final.status is ProcedureStatus.ESCALATED
    assert (
        final.step_results[WRITE_STEP].escalation_reason
        is EscalationReasonCode.EXECUTION_INDETERMINATE
    )
    assert action_executor.write_count == 1, "ambiguity must not trigger a second write"


@pytest.mark.asyncio
async def test_write_count_is_one_even_when_the_loop_runs_to_exhaustion(
    sop, inventory_definition, zone_context
):
    """
    Failure path F, and the sharpest edge of the loop design: three iterations
    of reassessment, one write. The loop can only read.
    """
    world = FakeInventoryWorld()
    executor = DeterministicExceptionExecutor()
    paused = await run_to_governance(executor, sop, inventory_definition, zone_context, world)
    action_executor = RecordingActionExecutor(world, mutate=True, adjust_to=5)
    action_executor.execute_replenishment(sku=SKU, quantity=REQUIRED_QUANTITY)

    final = await resume_and_continue(
        executor, sop, inventory_definition, zone_context, world,
        GovernanceOutcomeStub(), paused,
    )

    assert final.attempt_by_step[LOOP_STEP] == 3
    assert action_executor.write_count == 1


@pytest.mark.asyncio
async def test_governance_rejection_performs_no_write(
    sop, inventory_definition, zone_context, world
):
    executor = DeterministicExceptionExecutor()
    final, action_executor = await full_run(
        executor, sop, inventory_definition, zone_context, world, decision="REJECTED",
    )

    assert action_executor.write_count == 0
    assert final.status is ProcedureStatus.ESCALATED
    assert LOOP_STEP not in final.completed_step_ids


# ══════════════════════════════════════════════════════════════════════════════
# 8. Other failure paths
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_capability_unavailable_escalates_with_its_own_reason(
    sop, inventory_definition, zone_context, world
):
    """Failure path B."""
    executor = FailingCapabilityExecutor(
        "detect_exception", EscalationReasonCode.CAPABILITY_UNAVAILABLE
    )

    final = await run_to_governance(executor, sop, inventory_definition, zone_context, world)

    assert final.status is ProcedureStatus.ESCALATED
    assert (
        final.step_results["detect_exception"].escalation_reason
        is EscalationReasonCode.CAPABILITY_UNAVAILABLE
    )


@pytest.mark.asyncio
async def test_conflicting_state_escalates_without_a_model_guess(
    sop, inventory_definition, zone_context
):
    """
    Failure path C. Availability satisfies the requirement but the SKU is held
    in no location — the record contradicts itself. The engine must escalate
    rather than let a model reconcile the contradiction.
    """
    world = FakeInventoryWorld()
    executor = DeterministicExceptionExecutor()
    paused = await run_to_governance(executor, sop, inventory_definition, zone_context, world)
    # The adjustment lands (quantity moves) but leaves an inconsistent record.
    action_executor = RecordingActionExecutor(world, mutate=False)
    action_executor.execute_replenishment(sku=SKU, quantity=REQUIRED_QUANTITY)
    world.set_available(REQUIRED_QUANTITY, location_count=0)

    final = await resume_and_continue(
        executor, sop, inventory_definition, zone_context, world,
        GovernanceOutcomeStub(), paused,
    )

    assert final.status is ProcedureStatus.ESCALATED
    assert "resume_picking" not in final.completed_step_ids
    assert action_executor.write_count == 1, "no corrective write was invented"


@pytest.mark.asyncio
async def test_retry_budget_exhaustion_on_a_read_step_escalates(
    sop, inventory_definition, zone_context, world
):
    executor = StarvedExecutor("classify_exception")

    final = await run_to_governance(executor, sop, inventory_definition, zone_context, world)

    assert final.status is ProcedureStatus.ESCALATED
    assert (
        final.step_results["classify_exception"].escalation_reason
        is EscalationReasonCode.RETRY_BUDGET_EXHAUSTED
    )
    assert len(executor.calls_for("classify_exception")) == 2


@pytest.mark.asyncio
async def test_read_step_retry_is_distinct_from_loop_exhaustion(
    sop, inventory_definition, zone_context, world
):
    """
    Two different budgets, two different reason codes. Conflating them would
    tell an operator the wrong thing.
    """
    executor = StarvedExecutor("classify_exception")
    final = await run_to_governance(executor, sop, inventory_definition, zone_context, world)

    assert final.loop_exhausted_step_ids == []
    assert (
        final.step_results["classify_exception"].escalation_reason
        is EscalationReasonCode.RETRY_BUDGET_EXHAUSTED
    )


@pytest.mark.asyncio
async def test_missing_required_input_escalates_missing_data(
    sop, inventory_definition, world
):
    context = AgentExecutionContext(
        warehouse_id="wh-test",
        trace_id="trace-missing",
        bounded_context={"facility_picking_strategy": "zone"},
    )
    executor = DeterministicExceptionExecutor()

    final = await run_to_governance(executor, sop, inventory_definition, context, world)

    assert final.status is ProcedureStatus.ESCALATED
    assert (
        final.step_results["detect_exception"].escalation_reason
        is EscalationReasonCode.MISSING_DATA
    )


# ══════════════════════════════════════════════════════════════════════════════
# 9. Deep Agents runtime
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_deep_agents_normal_resolution_completes(
    sop, inventory_definition, zone_context, world
):
    executor = DeepAgentsExceptionExecutor()
    final, _ = await full_run(executor, sop, inventory_definition, zone_context, world)

    assert final.status is ProcedureStatus.COMPLETED
    assert final.completed_step_ids == ZONE_STEP_SEQUENCE


@pytest.mark.asyncio
async def test_deep_agents_receives_exactly_one_step_per_invocation(
    sop, inventory_definition, zone_context, world
):
    executor = DeepAgentsExceptionExecutor()
    await full_run(executor, sop, inventory_definition, zone_context, world)

    assert executor.steps_seen_per_call
    assert set(executor.steps_seen_per_call) == {1}


@pytest.mark.asyncio
async def test_deep_agents_cannot_skip_the_loop_step(
    sop, inventory_definition, zone_context, world
):
    executor = DeepAgentsExceptionExecutor()
    await full_run(executor, sop, inventory_definition, zone_context, world)

    assert LOOP_STEP in executor.step_ids
    assert executor.step_ids.index(WRITE_STEP) < executor.step_ids.index(LOOP_STEP)


@pytest.mark.asyncio
async def test_deep_agents_gets_the_same_loop_budget(sop, inventory_definition, zone_context):
    world = FakeInventoryWorld()
    executor = DeepAgentsExceptionExecutor()
    paused = await run_to_governance(executor, sop, inventory_definition, zone_context, world)
    RecordingActionExecutor(world, mutate=True, adjust_to=5).execute_replenishment(
        sku=SKU, quantity=REQUIRED_QUANTITY
    )

    final = await resume_and_continue(
        executor, sop, inventory_definition, zone_context, world,
        GovernanceOutcomeStub(), paused,
    )

    assert len(executor.calls_for(LOOP_STEP)) == 3
    assert final.status is ProcedureStatus.ESCALATED


def test_deep_agents_is_never_told_the_loop_state():
    """
    The runtime seam carries ``attempt``, which is a fact about the past. It
    carries nothing about the budget, the remaining iterations, or the decision.
    """
    import inspect as _inspect

    from maiw_agents.sop_engine.executor import SOPStepExecutor

    params = set(_inspect.signature(SOPStepExecutor.execute_step).parameters)
    for forbidden in (
        "iterations_remaining", "max_iterations", "loop", "loop_policy", "should_continue",
    ):
        assert forbidden not in params


def test_deep_agents_has_no_write_tools():
    executor = DeepAgentsExceptionExecutor()
    for tool in executor.tools:
        entry = SKILL_REGISTRY.get(tool)
        assert entry is not None, f"unregistered tool exposed: {tool}"
        assert entry.capability_class is CapabilityClass.READ
        assert entry.is_write is False


# ══════════════════════════════════════════════════════════════════════════════
# 10. Cross-runtime equivalence
# ══════════════════════════════════════════════════════════════════════════════


def _comparable(final: ProcedureExecutionState) -> tuple:
    """Structure and verdicts only — never prose."""
    return (
        final.status,
        tuple(final.completed_step_ids),
        tuple(sorted(final.attempt_by_step.items())),
        tuple(final.loop_exhausted_step_ids),
        tuple(
            (step_id, r.validation_result.validator_type, r.validation_result.valid)
            for step_id, r in sorted(final.step_results.items())
            if r.validation_result is not None
        ),
    )


@pytest.mark.asyncio
async def test_cross_runtime_equivalence_on_the_normal_path(sop, inventory_definition):
    results = {}
    for executor in (DeterministicExceptionExecutor(), DeepAgentsExceptionExecutor()):
        world = FakeInventoryWorld()
        final, _ = await full_run(
            executor, sop, inventory_definition, make_context("zone"), world
        )
        results[executor.RUNTIME_NAME] = _comparable(final)

    assert results["deterministic"] == results["deep_agents"]
    assert results["deterministic"][0] is ProcedureStatus.COMPLETED


@pytest.mark.asyncio
async def test_cross_runtime_equivalence_on_loop_exhaustion(sop, inventory_definition):
    """Same fixture, same budget, same escalation — under both runtimes."""
    results = {}
    for executor in (DeterministicExceptionExecutor(), DeepAgentsExceptionExecutor()):
        world = FakeInventoryWorld()
        context = make_context("zone")
        paused = await run_to_governance(executor, sop, inventory_definition, context, world)
        RecordingActionExecutor(world, mutate=True, adjust_to=5).execute_replenishment(
            sku=SKU, quantity=REQUIRED_QUANTITY
        )
        final = await resume_and_continue(
            executor, sop, inventory_definition, context, world,
            GovernanceOutcomeStub(), paused,
        )
        results[executor.RUNTIME_NAME] = _comparable(final)

    assert results["deterministic"] == results["deep_agents"]
    assert results["deterministic"][0] is ProcedureStatus.ESCALATED


@pytest.mark.asyncio
async def test_cross_runtime_equivalence_under_discrete_strategy(sop, inventory_definition):
    results = {}
    for executor in (DeterministicExceptionExecutor(), DeepAgentsExceptionExecutor()):
        world = FakeInventoryWorld()
        final, _ = await full_run(
            executor, sop, inventory_definition, make_context("discrete"), world
        )
        results[executor.RUNTIME_NAME] = _comparable(final)

    assert results["deterministic"] == results["deep_agents"]


@pytest.mark.asyncio
async def test_cross_runtime_governance_pause_timing(sop, inventory_definition):
    pauses = {}
    for executor in (DeterministicExceptionExecutor(), DeepAgentsExceptionExecutor()):
        world = FakeInventoryWorld()
        paused = await run_to_governance(
            executor, sop, inventory_definition, make_context("zone"), world
        )
        pauses[executor.RUNTIME_NAME] = (paused.status, paused.current_step_id)

    assert pauses["deterministic"] == pauses["deep_agents"]


# ══════════════════════════════════════════════════════════════════════════════
# 11. Evidence
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_every_loop_iteration_leaves_evidence(sop, inventory_definition, zone_context):
    world = FakeInventoryWorld()
    executor = DeterministicExceptionExecutor()
    paused = await run_to_governance(executor, sop, inventory_definition, zone_context, world)
    RecordingActionExecutor(world, mutate=True, adjust_to=5).execute_replenishment(
        sku=SKU, quantity=REQUIRED_QUANTITY
    )

    final = await resume_and_continue(
        executor, sop, inventory_definition, zone_context, world,
        GovernanceOutcomeStub(), paused,
    )

    attempts = sorted({
        ref.metadata.get("attempt")
        for ref in final.evidence_refs
        if ref.metadata.get("step_id") == LOOP_STEP
    })
    assert attempts == [1, 2, 3], "no iteration's evidence may be lost"


@pytest.mark.asyncio
async def test_loop_evidence_names_the_predicate_and_its_args(
    sop, inventory_definition, zone_context
):
    world = FakeInventoryWorld()
    executor = DeterministicExceptionExecutor()
    paused = await run_to_governance(executor, sop, inventory_definition, zone_context, world)
    RecordingActionExecutor(world, mutate=True, adjust_to=5).execute_replenishment(
        sku=SKU, quantity=REQUIRED_QUANTITY
    )

    final = await resume_and_continue(
        executor, sop, inventory_definition, zone_context, world,
        GovernanceOutcomeStub(), paused,
    )

    named = [
        ref for ref in final.evidence_refs
        if ref.metadata.get("predicate_name") == "inventory_exception_resolved"
    ]
    assert len(named) == 3
    assert named[0].metadata["predicate_args"]["required_quantity"] == REQUIRED_QUANTITY


@pytest.mark.asyncio
async def test_evidence_retained_for_every_completed_step(
    sop, inventory_definition, zone_context, world
):
    executor = DeterministicExceptionExecutor()
    final, _ = await full_run(executor, sop, inventory_definition, zone_context, world)

    covered = {ref.metadata.get("step_id") for ref in final.evidence_refs}
    for step_id in ZONE_STEP_SEQUENCE:
        assert step_id in covered


@pytest.mark.asyncio
async def test_no_chain_of_thought_in_evidence(
    sop, inventory_definition, zone_context, world
):
    executor = DeterministicExceptionExecutor()
    final, _ = await full_run(executor, sop, inventory_definition, zone_context, world)

    banned = {"chain_of_thought", "scratchpad", "hidden_reasoning", "raw_reasoning"}
    for ref in final.evidence_refs:
        assert not banned & set(ref.metadata)


@pytest.mark.asyncio
async def test_procedure_trace_identity_is_linked(
    sop, inventory_definition, zone_context, world
):
    executor = DeterministicExceptionExecutor()
    final, _ = await full_run(executor, sop, inventory_definition, zone_context, world)

    assert final.trace_id == zone_context.trace_id
    assert final.sop_id == SOP_ID
    assert final.sop_version == SOP_VERSION
    assert final.procedure_execution_id


# ══════════════════════════════════════════════════════════════════════════════
# 12. Human escalation is escalation, not a HUMAN validator
# ══════════════════════════════════════════════════════════════════════════════


def test_no_human_validator_was_introduced():
    """
    Design decision, argued in docs/sops/PICKING_INVENTORY_EXCEPTION.md: the
    human in this procedure is being handed control, not being awaited as a
    step's completion criterion. HUMAN stays deferred.
    """
    assert not hasattr(ValidatorType, "HUMAN")
    assert {v.value for v in ValidatorType} == {
        "schema", "state_predicate", "capability_result", "legacy_success",
    }


def test_escalation_step_completes_by_schema_not_by_waiting(sop):
    step = next(s for s in sop.steps if s.id == "escalate_to_human")
    assert step.completion.validator_type is ValidatorType.SCHEMA
    assert step.next_step_id is None, "nothing resumes after the handoff"


def test_escalation_payload_carries_what_a_human_needs(sop):
    step = next(s for s in sop.steps if s.id == "escalate_to_human")
    required = set(step.completion.schema_fields)
    assert {
        "escalation_reason", "sku", "required_quantity", "observed_available", "attempts",
    } <= required


def test_sop_declares_a_human_intervention_stop_condition(sop):
    assert "human_intervention_required" in sop.stop_conditions


# ══════════════════════════════════════════════════════════════════════════════
# 13. Authority boundary
# ══════════════════════════════════════════════════════════════════════════════


PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "maiw_agents"


def test_inventory_package_never_executes_a_write():
    for path in (PACKAGE_ROOT / "inventory").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "maiw_execution" not in alias.name
                    assert "ActionExecutor" not in alias.name
            elif isinstance(node, ast.ImportFrom):
                assert "maiw_execution" not in (node.module or "")


def test_inventory_predicates_use_no_expression_evaluation():
    """
    Checked against the AST, not the text: the module docstring legitimately
    discusses ``eval()`` in order to say it is absent, and a substring scan
    would flag the explanation as the violation.
    """
    tree = ast.parse((PACKAGE_ROOT / "inventory" / "predicates.py").read_text(encoding="utf-8"))
    banned = {"eval", "exec", "compile", "__import__", "getattr", "setattr"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in banned, f"predicate module calls {node.func.id}()"
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in ("subprocess", "os", "socket")
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "") not in ("subprocess", "os", "socket")


def test_inventory_agent_definition_cannot_invoke_action_executor():
    boundary = INVENTORY_AGENT_DEFINITION.governance_boundary
    assert boundary.may_invoke_action_executor is False
    assert boundary.may_invoke_decision_engine is False
    assert set(boundary.allowed_capability_classes) <= {"READ", "ANALYTICAL", "PROPOSAL"}


def test_inventory_agent_definition_points_at_this_sop():
    assert INVENTORY_AGENT_DEFINITION.sop_id == SOP_ID


def test_inventory_capabilities_are_classified():
    expected = {
        "warehouse.inventory.lookup": CapabilityClass.READ,
        "warehouse.inventory.locate": CapabilityClass.READ,
        "warehouse.inventory.evaluate_replenishment": CapabilityClass.ANALYTICAL,
        "warehouse.inventory.replenish": CapabilityClass.PROPOSAL,
    }
    for skill_id, cap_class in expected.items():
        entry = SKILL_REGISTRY[skill_id]
        assert entry.capability_class is cap_class
        assert entry.is_write is False


def test_no_inventory_write_capability_is_agent_reachable():
    for cap in INVENTORY_AGENT_DEFINITION.allowed_capabilities:
        assert SKILL_REGISTRY[cap].is_write is False


def test_loop_support_created_no_operational_authority():
    """
    A loop is repetition, not permission. Nothing about LoopPolicy widens what
    the agent package may do.
    """
    from maiw_agents.contracts.sop_v2 import LoopPolicy

    fields = set(LoopPolicy.model_fields)
    for forbidden in ("capability", "executor", "action", "write", "approval", "authority"):
        assert not any(forbidden in f for f in fields)
