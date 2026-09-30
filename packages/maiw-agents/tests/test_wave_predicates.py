# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Wave domain state predicates + SOP/registry conformance.

Two things are under test here.

**The specific bug.** ``wave_risk_resolution.v2.yaml`` (Proof SOP A) ends on a
STATE_PREDICATE step naming ``wave_risk_reduced``. That name was owned by no
production module, so the terminal step of Proof SOP A resolved to
``unknown predicate`` at runtime. It is now owned by
``maiw_agents/wave/predicates.py`` and registered through the same path the
equipment domain uses.

**The class of bug.** ``test_all_sop_state_predicates_registered_in_production``
is the reason this file matters more than the fix. It walks *every* executable
SOP YAML, extracts *every* named STATE_PREDICATE, and asserts each one resolves
through the production registry. A SOP that names a predicate nobody implemented
now fails in CI instead of at 3am in front of an operator.

Nothing here registers a predicate, monkeypatches the registry, or inserts into
it by hand. Every resolution goes through
``maiw_agents.domain_predicates.production_predicates()``, which is the same
call ``apps/api/maiw_api/bootstrap.py`` makes at startup. A test that had to
register ``wave_risk_reduced`` itself would prove nothing.
"""

from __future__ import annotations

import ast
import inspect
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from maiw_agents.contracts.agent import AgentDefinition
from maiw_agents.contracts.procedure_state import (
    ProcedureExecutionState,
    ProcedureStatus,
)
from maiw_agents.contracts.runtime import AgentExecutionContext
from maiw_agents.contracts.sop import SOPDefinition, load_sop, validate_sop
from maiw_agents.contracts.sop_v2 import StepCompletionSpec, ValidatorType
from maiw_agents.contracts.step_result import EvidenceRef, StepResult, StepStatus
from maiw_agents.domain_predicates import (
    PREDICATE_DOMAIN_MODULES,
    production_predicates,
    register_all_domain_predicates,
)
from maiw_agents.sop_engine import SOPEngine
from maiw_agents.sop_engine.validators import (
    StatePredicateValidator,
    StepValidationContext,
    get_registered_predicates,
)
from maiw_agents.wave.predicates import wave_risk_reduced

from conftest import SOP_DIR, make_procedure_state, make_sop, make_step_result

SOP_PATH = SOP_DIR / "operations_coordination" / "wave_risk_resolution.v2.yaml"

SOP_ID = "operations_coordination.wave_risk_resolution_v2"
OBSERVE_STEP = "observe"
PREDICATE_NAME = "wave_risk_reduced"

EXPECTED_STEP_SEQUENCE = [
    "establish_state",
    "diagnose",
    "gather_specialist_evidence",
    "generate_candidates",
    "compare",
    "recommend",
    "submit",
    "observe",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── The fake world: authoritative wave state, separate from executor claims ───


class FakeWaveWorld:
    """
    An in-memory stand-in for authoritative warehouse wave state.

    This is the *state source*, deliberately not the executor. It mirrors the
    shape ``maiw_state.models.wave.WaveState`` dumps to. The only way to learn
    anything from this object is to read it — it returns no success strings and
    carries no opinion about whether an action worked.
    """

    def __init__(
        self, *, at_risk_count: int = 3, warehouse_id: str = "wh-test"
    ) -> None:
        self.warehouse_id = warehouse_id
        self.at_risk_count = at_risk_count
        self.total_tasks = 12
        self.reads = 0
        # When set, replaces the whole wave component — used by missing-data tests.
        self.wave_component_override: Any = _UNSET

    def resolve_risk(self, *, remaining: int = 0) -> None:
        """The world changes because something outside the SOP changed it."""
        self.at_risk_count = remaining

    def as_state_dict(self) -> dict[str, Any]:
        self.reads += 1
        if self.wave_component_override is not _UNSET:
            component = self.wave_component_override
            return (
                {"warehouse_id": self.warehouse_id}
                if component is None
                else {"warehouse_id": self.warehouse_id, "waves": component}
            )
        return {
            "warehouse_id": self.warehouse_id,
            "waves": {
                "warehouse_id": self.warehouse_id,
                "total_tasks": self.total_tasks,
                "pending_count": 4,
                "in_progress_count": 3,
                "completed_count": 5,
                "at_risk_count": self.at_risk_count,
                "zones_active": ["ZONE-A"],
                "tasks": [],
            },
        }


_UNSET = object()


class LiveSnapshot:
    """
    A snapshot handle that re-reads the world every time it is consulted.

    The SOP Engine calls ``model_dump()`` on whatever it is handed, so a
    STATE_PREDICATE retry becomes a genuine fresh read of authoritative state
    rather than a re-check of a stale dict.
    """

    def __init__(self, world: FakeWaveWorld) -> None:
        self._world = world

    def model_dump(self) -> dict[str, Any]:
        return self._world.as_state_dict()


class GovernanceOutcomeStub:
    """Duck-typed governance outcome: the engine reads two attributes."""

    def __init__(
        self, decision_outcome: str = "APPROVED", execution_status: str = "EXECUTED"
    ):
        self.decision_outcome = decision_outcome
        self.execution_status = execution_status


# ── Step executors: the two runtimes ─────────────────────────────────────────

_SCENARIO_FACTS: dict[str, Any] = {
    "wave_id": "wave-17",
    "at_risk_count": 3,
    "carrier_cutoff_minutes": 47,
    "primary_constraint": "labor",
}


class _BaseWaveExecutor:
    """
    Shared step-fulfilment logic for both runtimes.

    Fulfils exactly one step per call and reports what it produced. It does NOT
    decide completion and does NOT choose the next step — the SOP Engine owns
    both. It never writes.
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
        completion = step.completion
        if completion is None or not completion.schema_fields:
            return {}
        return {f: self.facts[f] for f in completion.schema_fields if f in self.facts}

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


class DeterministicWaveExecutor(_BaseWaveExecutor):
    RUNTIME_NAME = "deterministic"
    EVIDENCE_TYPE = "step_execution"


class DeepAgentsWaveExecutor(_BaseWaveExecutor):
    """Mimics the Deep Agents runtime: one step per invocation, READ-only tools."""

    RUNTIME_NAME = "deep_agents"
    EVIDENCE_TYPE = "model_response"

    def __init__(self, facts: dict[str, Any] | None = None) -> None:
        super().__init__(facts)
        self.tools = ["warehouse.wave.status", "warehouse.wave.inspect_tasks"]
        self.steps_seen_per_call: list[int] = []

    async def execute_step(
        self, *, definition, step, procedure_state, context, attempt
    ):
        self.steps_seen_per_call.append(1)
        return await super().execute_step(
            definition=definition,
            step=step,
            procedure_state=procedure_state,
            context=context,
            attempt=attempt,
        )


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def sop_a() -> SOPDefinition:
    return load_sop(SOP_PATH)


@pytest.fixture
def ops_definition() -> AgentDefinition:
    return AgentDefinition(
        agent_id="operations_coordination",
        version="1.0",
        objective="Resolve wave risk before carrier cutoff",
        domain="operations",
        allowed_capabilities=[],
        allowed_subagents=[],
        output_contract="RecommendedAction",
    )


@pytest.fixture
def wave_context() -> AgentExecutionContext:
    return AgentExecutionContext(
        warehouse_id="wh-test",
        trace_id="trace-proof-sop-a",
        bounded_context={
            "wave_id": "wave-17",
            "at_risk_count": 3,
            "carrier_cutoff_minutes": 47,
            "primary_constraint": "labor",
            "domains_affected": "labor",
        },
    )


@pytest.fixture
def world() -> FakeWaveWorld:
    return FakeWaveWorld()


async def run_proof_sop_a(executor, sop, definition, context, world, outcome):
    """
    The canonical Proof SOP A path: run to the governance pause, resume, finish.

    No predicate is registered anywhere in here.
    """
    engine = SOPEngine(executor=executor, trace_id=context.trace_id)
    paused = await engine.run_procedure(
        definition=definition,
        sop=sop,
        agent_task_id="task-wave-resolution",
        context=context,
        warehouse_state_snapshot=LiveSnapshot(world),
    )
    if paused.status is not ProcedureStatus.WAITING_FOR_GOVERNANCE:
        return paused

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


def observe_step(sop: SOPDefinition):
    return next(s for s in sop.steps if s.id == OBSERVE_STEP)


def _called_name(node: ast.Call) -> str | None:
    """The bare name of whatever a Call node invokes."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _executable_source(module) -> str:
    """
    A module's source with every docstring removed.

    Token bans must apply to code, not to prose. This module's own design notes
    and the wave predicate module's docstring both discuss ``ActionExecutor`` and
    ``ModelGateway`` precisely in order to state that neither is used — a
    substring scan over raw source would flag the documentation of the invariant
    as a violation of it.
    """
    tree = ast.parse(inspect.getsource(module))
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(tree))


# ══════════════════════════════════════════════════════════════════════════════
# 1. The predicate is registered in production
# ══════════════════════════════════════════════════════════════════════════════


def test_wave_predicate_registered_via_production_path():
    """
    The whole point of the fix.

    ``production_predicates()`` is the call bootstrap makes. Nothing in this
    test registers anything.
    """
    registry = production_predicates()
    assert PREDICATE_NAME in registry
    assert registry[PREDICATE_NAME] is wave_risk_reduced


def test_importing_the_wave_domain_is_what_registers_it():
    """Domain-owned, not engine-embedded: loading the wave package is the trigger."""
    import maiw_agents.wave  # noqa: F401

    assert PREDICATE_NAME in get_registered_predicates()


def test_registration_is_idempotent_and_deterministic():
    """Re-registering rebinds the same name to the same function, every time."""
    before = production_predicates()
    register_all_domain_predicates()
    register_all_domain_predicates()
    after = production_predicates()

    assert set(before) == set(after)
    assert after[PREDICATE_NAME] is before[PREDICATE_NAME]


def test_no_test_fixture_injection_required():
    """
    A cold process resolves the predicate with no help from the test suite.

    Asserted structurally, by walking this module's own AST: it never *calls*
    ``register_predicate``/``unregister_predicate`` and never reaches into the
    private registry dict. If it did, the registration assertions above would be
    proving the test's own setup rather than production wiring.
    """
    tree = ast.parse(Path(__file__).read_text())

    called = {
        _called_name(node) for node in ast.walk(tree) if isinstance(node, ast.Call)
    }
    assert "register_predicate" not in called
    assert "unregister_predicate" not in called

    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "_PREDICATES"
        for node in ast.walk(tree)
    ), "test must not reach into the private registry dict"

    assert PREDICATE_NAME in production_predicates()


# ══════════════════════════════════════════════════════════════════════════════
# 2. True state passes
# ══════════════════════════════════════════════════════════════════════════════


def test_true_state_passes_absolute_mode():
    """Objective restored: no tasks remain at risk."""
    state = FakeWaveWorld(at_risk_count=0).as_state_dict()
    assert wave_risk_reduced(state, {"min_reduction": 1}) is True


def test_true_state_passes_with_declared_threshold():
    state = FakeWaveWorld(at_risk_count=2).as_state_dict()
    assert (
        wave_risk_reduced(state, {"min_reduction": 1, "max_at_risk_count": 2}) is True
    )


def test_true_state_passes_relative_mode():
    """Declared baseline in the YAML, not a prior snapshot read."""
    state = FakeWaveWorld(at_risk_count=1).as_state_dict()
    args = {"min_reduction": 2, "baseline_at_risk_count": 3}
    assert wave_risk_reduced(state, args) is True


def test_nested_snapshot_shape_is_accepted():
    """A sealed WarehouseStateSnapshot nests the domains under ``state``."""
    inner = FakeWaveWorld(at_risk_count=0).as_state_dict()
    sealed = {"snapshot_id": "snap-1", "warehouse_id": "wh-test", "state": inner}
    assert wave_risk_reduced(sealed, {"min_reduction": 1}) is True


def test_singular_wave_key_is_accepted():
    inner = FakeWaveWorld(at_risk_count=0).as_state_dict()
    renamed = {"warehouse_id": "wh-test", "wave": inner["waves"]}
    assert wave_risk_reduced(renamed, {"min_reduction": 1}) is True


def test_predicate_is_pure_and_deterministic():
    """Same state, same args, same answer — and the state is not mutated."""
    state = FakeWaveWorld(at_risk_count=0).as_state_dict()
    snapshot_before = repr(state)
    results = {wave_risk_reduced(state, {"min_reduction": 1}) for _ in range(25)}
    assert results == {True}
    assert repr(state) == snapshot_before


# ══════════════════════════════════════════════════════════════════════════════
# 3. False state fails
# ══════════════════════════════════════════════════════════════════════════════


def test_false_state_fails_absolute_mode():
    """Risk still present. A partial improvement is not a resolution."""
    state = FakeWaveWorld(at_risk_count=2).as_state_dict()
    assert wave_risk_reduced(state, {"min_reduction": 1}) is False


def test_false_state_fails_relative_mode_insufficient_reduction():
    state = FakeWaveWorld(at_risk_count=2).as_state_dict()
    args = {"min_reduction": 2, "baseline_at_risk_count": 3}
    assert wave_risk_reduced(state, args) is False


def test_risk_that_got_worse_fails():
    state = FakeWaveWorld(at_risk_count=5).as_state_dict()
    args = {"min_reduction": 1, "baseline_at_risk_count": 3}
    assert wave_risk_reduced(state, args) is False


def test_wrong_warehouse_fails():
    """State for a different warehouse is not proof about this one."""
    state = FakeWaveWorld(at_risk_count=0, warehouse_id="wh-other").as_state_dict()
    args = {"min_reduction": 1, "warehouse_id": "wh-test"}
    assert wave_risk_reduced(state, args) is False


# ══════════════════════════════════════════════════════════════════════════════
# 4. Missing data must never pass
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "state,label",
    [
        ({}, "empty state"),
        ({"warehouse_id": "wh-test"}, "no wave component"),
        ({"waves": None}, "wave component is None"),
        ({"waves": []}, "wave component is not a mapping"),
        ({"waves": {"warehouse_id": "wh-test"}}, "at_risk_count absent"),
        ({"waves": {"at_risk_count": None}}, "at_risk_count is None"),
        ({"waves": {"at_risk_count": "0"}}, "at_risk_count is a string"),
        ({"waves": {"at_risk_count": 0.0}}, "at_risk_count is a float"),
        ({"waves": {"at_risk_count": False}}, "at_risk_count is a bool"),
        ({"waves": {"at_risk_count": -1}}, "at_risk_count is negative"),
    ],
)
def test_missing_or_malformed_state_does_not_pass(state, label):
    assert wave_risk_reduced(state, {"min_reduction": 1}) is False, label


@pytest.mark.parametrize(
    "state",
    [None, "waves", 42, ["waves"]],
)
def test_non_dict_state_does_not_pass(state):
    assert wave_risk_reduced(state, {"min_reduction": 1}) is False


@pytest.mark.parametrize(
    "args,label",
    [
        ({"min_reduction": 0}, "a reduction of zero is not proof"),
        ({"min_reduction": -1}, "negative reduction"),
        ({"min_reduction": "1"}, "min_reduction is a string"),
        ({"min_reduction": True}, "min_reduction is a bool"),
        ({"min_reduction": 1, "max_at_risk_count": -1}, "negative ceiling"),
        ({"min_reduction": 1, "max_at_risk_count": "0"}, "ceiling is a string"),
        ({"min_reduction": 1, "baseline_at_risk_count": "3"}, "baseline is a string"),
        ({"min_reduction": 1, "baseline_at_risk_count": -3}, "negative baseline"),
    ],
)
def test_malformed_args_do_not_pass(args, label):
    """Even against a state that would otherwise satisfy the predicate."""
    state = FakeWaveWorld(at_risk_count=0).as_state_dict()
    assert wave_risk_reduced(state, args) is False, label


def test_empty_args_still_requires_the_objective():
    """No args at all must not be a free pass."""
    assert (
        wave_risk_reduced(FakeWaveWorld(at_risk_count=3).as_state_dict(), {}) is False
    )
    assert wave_risk_reduced(FakeWaveWorld(at_risk_count=0).as_state_dict(), {}) is True


def test_missing_data_is_distinguishable_from_zero_risk():
    """
    The distinction that makes the predicate safe.

    "No wave data" and "wave data showing zero at-risk tasks" must not collapse
    into the same answer.
    """
    no_data = {"warehouse_id": "wh-test"}
    zero_risk = FakeWaveWorld(at_risk_count=0).as_state_dict()
    assert wave_risk_reduced(no_data, {"min_reduction": 1}) is False
    assert wave_risk_reduced(zero_risk, {"min_reduction": 1}) is True


# ══════════════════════════════════════════════════════════════════════════════
# 5. Proof SOP A — load, validate, resolve
# ══════════════════════════════════════════════════════════════════════════════


def test_proof_sop_a_loads_through_production_loader(sop_a):
    assert sop_a.id == SOP_ID
    assert sop_a.version == "2.0"
    assert [s.id for s in sop_a.steps] == EXPECTED_STEP_SEQUENCE


def test_proof_sop_a_validates(sop_a):
    validate_sop(sop_a)  # raises SOPValidationError on failure


def test_proof_sop_a_observe_step_declares_the_predicate(sop_a):
    completion = observe_step(sop_a).completion
    assert completion is not None
    assert completion.validator_type is ValidatorType.STATE_PREDICATE
    assert completion.predicate_name == PREDICATE_NAME
    assert completion.predicate_args == {"min_reduction": 1}


def test_proof_sop_a_predicate_resolves_in_production_registry(sop_a):
    """The regression test for the reported defect, stated directly."""
    name = observe_step(sop_a).completion.predicate_name
    assert name in production_predicates(), (
        f"Proof SOP A names STATE_PREDICATE {name!r}, which does not resolve "
        "through the production registry — this step would fail at runtime."
    )


@pytest.mark.asyncio
async def test_proof_sop_a_observe_step_does_not_report_unknown_predicate(
    sop_a, ops_definition, wave_context, world
):
    """Directly exercise the validator branch that produced the defect."""
    world.resolve_risk(remaining=0)
    validation = await StatePredicateValidator().validate(
        observe_step(sop_a),
        make_step_result(OBSERVE_STEP),
        StepValidationContext(
            step=observe_step(sop_a),
            procedure_state=make_procedure_state(sop_id=SOP_ID, version="2.0"),
            execution_context=wave_context,
            warehouse_state_snapshot=LiveSnapshot(world),
        ),
    )
    assert "unknown predicate" not in validation.reason
    assert validation.valid is True


# ══════════════════════════════════════════════════════════════════════════════
# 6. Proof SOP A — end to end, both runtimes
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_proof_sop_a_happy_path_completes(
    sop_a, ops_definition, wave_context, world
):
    """
    End to end with no test-only registry setup.

    The world is resolved *outside* the SOP — governance authorizes, an executor
    that lives outside this package acts, and the SOP only reads the result.
    """
    executor = DeterministicWaveExecutor()
    world.resolve_risk(remaining=0)

    final = await run_proof_sop_a(
        executor, sop_a, ops_definition, wave_context, world, GovernanceOutcomeStub()
    )

    assert final.status is ProcedureStatus.COMPLETED
    assert OBSERVE_STEP in final.completed_step_ids
    observe_result = final.step_results[OBSERVE_STEP]
    assert observe_result.validation_result.valid is True
    assert (
        observe_result.validation_result.validator_type is ValidatorType.STATE_PREDICATE
    )


@pytest.mark.asyncio
async def test_proof_sop_a_pauses_for_governance(
    sop_a, ops_definition, wave_context, world
):
    """The SOP halts at the handoff and runs nothing further on its own."""
    executor = DeterministicWaveExecutor()
    engine = SOPEngine(executor=executor, trace_id=wave_context.trace_id)
    paused = await engine.run_procedure(
        definition=ops_definition,
        sop=sop_a,
        agent_task_id="task-wave-resolution",
        context=wave_context,
        warehouse_state_snapshot=LiveSnapshot(world),
    )
    assert paused.status is ProcedureStatus.WAITING_FOR_GOVERNANCE
    assert OBSERVE_STEP not in executor.step_ids
    assert OBSERVE_STEP not in paused.completed_step_ids


@pytest.mark.asyncio
async def test_proof_sop_a_false_predicate_does_not_complete(
    sop_a, ops_definition, wave_context, world
):
    """
    Governance approved, the executor reported EXECUTED, the world did not move.

    The procedure must not complete. This is the invariant Proof SOP A exists
    to demonstrate.
    """
    executor = DeterministicWaveExecutor()
    world.resolve_risk(remaining=3)  # still at risk

    final = await run_proof_sop_a(
        executor, sop_a, ops_definition, wave_context, world, GovernanceOutcomeStub()
    )

    assert final.status is not ProcedureStatus.COMPLETED
    assert OBSERVE_STEP not in final.completed_step_ids
    assert final.step_results[OBSERVE_STEP].validation_result.valid is False


@pytest.mark.asyncio
async def test_proof_sop_a_missing_wave_state_does_not_complete(
    sop_a, ops_definition, wave_context, world
):
    """Unreadable state is not proof of success."""
    executor = DeterministicWaveExecutor()
    world.wave_component_override = None  # no wave component at all

    final = await run_proof_sop_a(
        executor, sop_a, ops_definition, wave_context, world, GovernanceOutcomeStub()
    )

    assert final.status is not ProcedureStatus.COMPLETED
    assert OBSERVE_STEP not in final.completed_step_ids


@pytest.mark.asyncio
async def test_proof_sop_a_reads_authoritative_state_not_a_stale_snapshot(
    sop_a, ops_definition, wave_context, world
):
    """
    The predicate is evaluated against a *fresh* read.

    The world is still at risk when the procedure starts and is resolved only
    after the governance pause. If the predicate were reading a pre-action
    snapshot, this run would fail.
    """
    executor = DeterministicWaveExecutor()
    engine = SOPEngine(executor=executor, trace_id=wave_context.trace_id)

    assert world.at_risk_count == 3
    paused = await engine.run_procedure(
        definition=ops_definition,
        sop=sop_a,
        agent_task_id="task-wave-resolution",
        context=wave_context,
        warehouse_state_snapshot=LiveSnapshot(world),
    )
    reads_at_pause = world.reads

    # The world changes after the SOP handed off — this is the only thing that
    # may make the terminal step complete.
    world.resolve_risk(remaining=0)

    resumed = await engine.resume_after_governance(
        definition=ops_definition,
        sop=sop_a,
        proc_state=paused,
        context=wave_context,
        governance_outcome=GovernanceOutcomeStub(),
        warehouse_state_snapshot=LiveSnapshot(world),
    )
    final = await engine.run_procedure(
        definition=ops_definition,
        sop=sop_a,
        agent_task_id=resumed.agent_task_id,
        context=wave_context,
        initial_state=resumed,
        warehouse_state_snapshot=LiveSnapshot(world),
    )

    assert final.status is ProcedureStatus.COMPLETED
    assert (
        world.reads > reads_at_pause
    ), "terminal step must re-read authoritative state"


@pytest.mark.asyncio
async def test_proof_sop_a_deep_agents_runtime_equivalent(
    sop_a, ops_definition, wave_context
):
    """Both runtimes traverse identically and reach the same verdicts."""
    results = {}
    for executor in (DeterministicWaveExecutor(), DeepAgentsWaveExecutor()):
        world = FakeWaveWorld()
        world.resolve_risk(remaining=0)
        final = await run_proof_sop_a(
            executor,
            sop_a,
            ops_definition,
            wave_context,
            world,
            GovernanceOutcomeStub(),
        )
        results[executor.RUNTIME_NAME] = (
            final.status,
            list(final.completed_step_ids),
            [
                (r.validation_result.validator_type, r.validation_result.valid)
                for r in final.step_results.values()
                if r.validation_result is not None
            ],
        )

    assert results["deterministic"] == results["deep_agents"]
    assert results["deterministic"][0] is ProcedureStatus.COMPLETED


@pytest.mark.asyncio
async def test_deep_agents_receives_exactly_one_step_per_invocation(
    sop_a, ops_definition, wave_context, world
):
    executor = DeepAgentsWaveExecutor()
    world.resolve_risk(remaining=0)
    await run_proof_sop_a(
        executor, sop_a, ops_definition, wave_context, world, GovernanceOutcomeStub()
    )
    assert executor.steps_seen_per_call
    assert set(executor.steps_seen_per_call) == {1}


# ══════════════════════════════════════════════════════════════════════════════
# 7. Cross-domain registration
# ══════════════════════════════════════════════════════════════════════════════


def test_both_domains_register_into_one_registry():
    registry = production_predicates()
    assert "wave_risk_reduced" in registry
    assert "equipment_recovery_complete" in registry
    assert "equipment_replacement_assigned" in registry
    assert "equipment_write_landed" in registry


def test_no_name_collision_between_domains():
    from maiw_agents.equipment.predicates import EQUIPMENT_PREDICATES
    from maiw_agents.wave.predicates import WAVE_PREDICATES

    assert not set(EQUIPMENT_PREDICATES) & set(WAVE_PREDICATES)


def test_domain_predicates_are_not_overridden_by_each_other():
    """Registration order does not change which function a name resolves to."""
    from maiw_agents.equipment.predicates import (
        equipment_recovery_complete,
        register_equipment_predicates,
    )
    from maiw_agents.wave.predicates import register_wave_predicates

    register_wave_predicates()
    register_equipment_predicates()
    first = production_predicates()

    register_equipment_predicates()
    register_wave_predicates()
    second = production_predicates()

    assert first[PREDICATE_NAME] is second[PREDICATE_NAME] is wave_risk_reduced
    assert (
        first["equipment_recovery_complete"]
        is second["equipment_recovery_complete"]
        is equipment_recovery_complete
    )


def test_every_declared_domain_module_is_importable():
    from importlib import import_module

    for module_path in PREDICATE_DOMAIN_MODULES:
        assert import_module(module_path) is not None


# ══════════════════════════════════════════════════════════════════════════════
# 8. THE REGISTRY-DRIFT TEST
#
# This is the test that would have caught the defect, and the reason this change
# is worth more than the one-line registration it contains.
# ══════════════════════════════════════════════════════════════════════════════


def _executable_sop_paths() -> list[Path]:
    """Every executable SOP YAML shipped in the repo."""
    return sorted(p for p in SOP_DIR.rglob("*.yaml") if p.is_file())


def _named_state_predicates(sop: SOPDefinition) -> list[tuple[str, str]]:
    """(step_id, predicate_name) for every STATE_PREDICATE step in a SOP."""
    found = []
    for step in sop.steps:
        completion = step.completion
        if completion is None:
            continue
        if completion.validator_type is not ValidatorType.STATE_PREDICATE:
            continue
        if completion.predicate_name is None:
            continue
        found.append((step.id, completion.predicate_name))
    return found


def test_sop_corpus_is_discoverable():
    """Guard the guard: the drift test is worthless if it scans nothing."""
    paths = _executable_sop_paths()
    assert paths, f"no SOP YAML found under {SOP_DIR}"
    assert any(p.name.endswith(".v2.yaml") for p in paths)


def test_all_sop_state_predicates_registered_in_production():
    """
    Every named STATE_PREDICATE referenced by any executable SOP YAML must
    resolve through the production registry.

    If this test fails, a SOP YAML references a predicate that would fail at
    runtime: the step reaches the validator, the lookup misses, and the result
    is a non-retryable ``unknown predicate`` escalation in front of an operator.
    The fix is to implement and register the predicate in the owning domain
    package — never to relax this assertion.
    """
    registry = production_predicates()

    unregistered: list[str] = []
    checked = 0

    for path in _executable_sop_paths():
        sop = load_sop(path)
        for step_id, predicate_name in _named_state_predicates(sop):
            checked += 1
            if predicate_name not in registry:
                unregistered.append(
                    f"{path.relative_to(SOP_DIR)}::{sop.id}::{step_id} "
                    f"-> {predicate_name!r}"
                )

    assert (
        checked > 0
    ), "no STATE_PREDICATE steps found in any SOP — the drift test is vacuous"
    assert not unregistered, (
        "SOP YAML references STATE_PREDICATE names that do not resolve through "
        "the production registry:\n  "
        + "\n  ".join(unregistered)
        + f"\n\nRegistered: {sorted(registry)}"
    )


def test_every_state_predicate_step_names_a_predicate():
    """A STATE_PREDICATE step with no name would silently validate as 'no predicate required'."""
    nameless = []
    for path in _executable_sop_paths():
        sop = load_sop(path)
        for step in sop.steps:
            completion = step.completion
            if completion is None:
                continue
            if completion.validator_type is ValidatorType.STATE_PREDICATE:
                if not completion.predicate_name:
                    nameless.append(f"{path.relative_to(SOP_DIR)}::{step.id}")
    assert not nameless, f"STATE_PREDICATE steps with no predicate_name: {nameless}"


def test_drift_test_detects_an_unregistered_predicate(sop_a):
    """
    Prove the drift test can fail.

    A guard that cannot fail is not a guard. Build a SOP naming a predicate that
    was never implemented and confirm the same check rejects it.
    """
    registry = production_predicates()
    step = observe_step(sop_a).model_copy(
        update={
            "completion": StepCompletionSpec(
                validator_type=ValidatorType.STATE_PREDICATE,
                predicate_name="wave_risk_definitely_not_implemented",
            )
        }
    )
    drifted = make_sop([step], sop_id="test.drifted", version="1.0")
    names = [n for _, n in _named_state_predicates(drifted)]

    assert names == ["wave_risk_definitely_not_implemented"]
    assert not all(n in registry for n in names)


# ══════════════════════════════════════════════════════════════════════════════
# 9. No generic fallback — unknown predicates fail explicitly
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_unknown_predicate_fails_explicitly_and_is_not_retryable(
    sop_a, wave_context, world
):
    """Hard invariant: an unregistered name must never be mistaken for a satisfied one."""
    step = observe_step(sop_a).model_copy(
        update={
            "completion": StepCompletionSpec(
                validator_type=ValidatorType.STATE_PREDICATE,
                predicate_name="no_such_predicate_anywhere",
            )
        }
    )
    world.resolve_risk(remaining=0)  # a state that would satisfy the real predicate

    validation = await StatePredicateValidator().validate(
        step,
        make_step_result(step.id),
        StepValidationContext(
            step=step,
            procedure_state=make_procedure_state(sop_id=SOP_ID, version="2.0"),
            execution_context=wave_context,
            warehouse_state_snapshot=LiveSnapshot(world),
        ),
    )

    assert validation.valid is False
    assert validation.retryable is False
    assert "unknown predicate" in validation.reason
    assert "no_such_predicate_anywhere" in validation.reason


# ══════════════════════════════════════════════════════════════════════════════
# 10. Engine neutrality, security boundary, chain-of-thought exclusion
# ══════════════════════════════════════════════════════════════════════════════

FORBIDDEN_TOKENS = [
    "ActionExecutor",
    "maiw_execution",
    "MAIWMCPClient",
    "ModelGateway",
    "DecisionEngine",
    "requests",
    "httpx",
    "subprocess",
    "eval(",
    "exec(",
    "os.environ",
]


def test_wave_predicates_module_has_no_write_or_model_capability():
    """The predicate is read/validation logic only — it cannot act on the world."""
    import maiw_agents.wave.predicates as mod

    code = _executable_source(mod)
    for token in FORBIDDEN_TOKENS:
        assert token not in code, f"wave/predicates.py must not reference {token}"


def test_wave_predicates_imports_only_the_validator_registry():
    """The module's entire import surface, asserted."""
    import maiw_agents.wave.predicates as mod

    tree = ast.parse(inspect.getsource(mod))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(f"{'.' * node.level}{node.module or ''}")

    assert imported == {"__future__", "typing", "..sop_engine.validators"}, imported


def test_generic_engine_stays_domain_neutral():
    """Wave semantics must not leak into the generic validator core or engine."""
    from maiw_agents.sop_engine import engine as engine_mod
    from maiw_agents.sop_engine import validators as validators_mod

    for mod in (engine_mod, validators_mod):
        code = _executable_source(mod).lower()
        for token in (
            "wave_risk_reduced",
            "at_risk_count",
            "carrier_cutoff",
            "forklift",
        ):
            assert token not in code, (
                f"{mod.__name__} embeds domain token {token!r} — "
                "domain semantics belong in the domain package"
            )


@pytest.mark.asyncio
async def test_validator_evidence_carries_no_reasoning(sop_a, wave_context, world):
    """Evidence records the verdict and its inputs — never model internals."""
    world.resolve_risk(remaining=0)
    step = observe_step(sop_a)
    validation = await StatePredicateValidator().validate(
        step,
        make_step_result(OBSERVE_STEP),
        StepValidationContext(
            step=step,
            procedure_state=make_procedure_state(sop_id=SOP_ID, version="2.0"),
            execution_context=wave_context,
            warehouse_state_snapshot=LiveSnapshot(world),
        ),
    )

    assert validation.evidence
    banned = {
        "reasoning",
        "thought",
        "thoughts",
        "scratchpad",
        "chain_of_thought",
        "system_prompt",
        "prompt",
        "raw_response",
        "completion_text",
    }
    for ref in validation.evidence:
        assert not banned & set(ref.metadata), ref.metadata
        assert ref.metadata["predicate_name"] == PREDICATE_NAME
        assert ref.metadata["predicate_args"] == {"min_reduction": 1}


def test_predicate_signature_matches_the_registry_contract():
    """``fn(state_dict, args) -> bool`` — the engine calls nothing else."""
    sig = inspect.signature(wave_risk_reduced)
    assert list(sig.parameters) == ["state", "args"]
    assert all(
        p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
        for p in sig.parameters.values()
    )
    assert isinstance(wave_risk_reduced({}, {}), bool)
