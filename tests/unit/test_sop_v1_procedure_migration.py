# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW SOP V1 Procedure Migration — traversal, reachability, and iteration tests.

Context
-------
Before this migration, the multi-step V1 YAML SOPs declared no ``next_step_id``.
``SOPEngine._advance()`` treats ``next_step_id is None`` as TERMINAL — it does NOT
fall through to the next step in the YAML list — so each of those SOPs executed
exactly ONE step and then reported COMPLETED. The procedure graphs existed only
in the authors' heads and in the step descriptions.

The migration makes the intended graph explicit: every non-terminal step names
its successor, and exactly one terminal step per SOP omits it.

These tests are the regression gate. They assert, per migrated SOP:
    1. load_sop() succeeds
    2. validate_sop() passes
    3. every non-terminal step has a non-None next_step_id
    4. every next_step_id points at a real step
    5. exactly one terminal step exists
    6. full traversal from step 0 reaches every defined step
    7. no cycles
    8. no orphaned (unreachable) steps
    9. SOPEngine.run_procedure() completes every step, not just the first
   10. the labor and wave SOPs fit inside their agents' iteration budgets,
       while genuine runaway loops still escalate

No network, no database, no model provider.
"""

from __future__ import annotations

import pathlib
import sys
from datetime import datetime, timezone

import pytest

WORKTREE = pathlib.Path(__file__).resolve().parents[2]
SOP_DIR = WORKTREE / "agents" / "sops"
_PACKAGE_ROOT = WORKTREE / "packages" / "maiw-agents"

# Import THIS repo's maiw-agents, not a sibling editable install.
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))


# ── The migrated SOPs ─────────────────────────────────────────────────────────
# (relative path, sop id, expected ordered traversal)

MIGRATED_SOPS = [
    (
        "labor/labor_constraint_assessment.v1.yaml",
        "labor.labor_constraint_assessment",
        [
            "read_workers",
            "read_tasks",
            "evaluate_imbalance",
            "identify_deficit",
            "check_constraints",
            "generate_interventions",
            "rank",
            "return_assessment",
        ],
    ),
    (
        "wave/wave_risk_assessment.v1.yaml",
        "wave.wave_risk_assessment",
        [
            "read_wave_status",
            "read_orders",
            "read_cutoff",
            "critical_path",
            "identify_at_risk",
            "evaluate_reprioritization",
            "return_assessment",
        ],
    ),
    (
        "operations_coordination/wave_risk_resolution.v1.yaml",
        "operations_coordination.wave_risk_resolution",
        [
            "establish_state",
            "diagnose",
            "gather_specialist_evidence",
            "generate_candidates",
            "compare",
            "recommend",
            "submit",
            "observe",
        ],
    ),
]

_IDS = [s[1] for s in MIGRATED_SOPS]


@pytest.fixture(params=MIGRATED_SOPS, ids=_IDS)
def migrated(request):
    """Load a migrated SOP plus its expected traversal."""
    from maiw_agents.contracts.sop import load_sop

    rel, expected_id, expected_chain = request.param
    path = SOP_DIR / rel
    assert path.exists(), f"migrated SOP is missing: {path}"
    sop = load_sop(path)
    assert sop.id == expected_id
    return sop, expected_chain


def _traverse(sop) -> list[str]:
    """Walk next_step_id from the first step, stopping on None or on a repeat."""
    by_id = {s.id: s for s in sop.steps}
    chain: list[str] = []
    seen: set[str] = set()
    current = sop.steps[0].id if sop.steps else None
    while current is not None and current not in seen:
        seen.add(current)
        chain.append(current)
        step = by_id.get(current)
        if step is None:
            break
        current = step.next_step_id
    return chain


# ── 1 & 2: loads and validates ────────────────────────────────────────────────


def test_migrated_sop_loads(migrated):
    sop, _ = migrated
    assert sop.steps, "SOP must define steps"


def test_migrated_sop_validates(migrated):
    """load_sop() already validates; call validate_sop() explicitly as the gate."""
    from maiw_agents.contracts.sop import validate_sop

    sop, _ = migrated
    validate_sop(sop)  # raises SOPValidationError on failure


# ── 3: every non-terminal step names a successor ──────────────────────────────


def test_every_non_terminal_step_has_explicit_successor(migrated):
    sop, expected_chain = migrated
    terminal_id = expected_chain[-1]
    for step in sop.steps:
        if step.id == terminal_id:
            continue
        assert step.next_step_id is not None, (
            f"{sop.id}: non-terminal step {step.id!r} has no next_step_id — "
            "it would terminate the procedure early"
        )


# ── 4: successors point at real steps ─────────────────────────────────────────


def test_next_step_ids_reference_existing_steps(migrated):
    sop, _ = migrated
    known = {s.id for s in sop.steps}
    for step in sop.steps:
        if step.next_step_id is not None:
            assert step.next_step_id in known, (
                f"{sop.id}: step {step.id!r} points at unknown step "
                f"{step.next_step_id!r}"
            )


def test_on_failure_step_ids_reference_existing_steps(migrated):
    sop, _ = migrated
    known = {s.id for s in sop.steps}
    for step in sop.steps:
        if step.on_failure_step_id is not None:
            assert step.on_failure_step_id in known


# ── 5: exactly one terminal step ──────────────────────────────────────────────


def test_exactly_one_terminal_step(migrated):
    sop, expected_chain = migrated
    terminals = [s.id for s in sop.steps if s.next_step_id is None]
    assert terminals == [expected_chain[-1]], (
        f"{sop.id}: expected exactly one terminal step "
        f"({expected_chain[-1]!r}), found {terminals}"
    )


# ── 6: traversal reaches every step, in the intended order ────────────────────


def test_traversal_matches_intended_chain(migrated):
    sop, expected_chain = migrated
    assert _traverse(sop) == expected_chain


def test_traversal_reaches_every_defined_step(migrated):
    sop, _ = migrated
    chain = _traverse(sop)
    assert len(chain) == len(
        sop.steps
    ), f"{sop.id}: traversal reaches {len(chain)} of {len(sop.steps)} steps"
    assert set(chain) == {s.id for s in sop.steps}


# ── 7: no cycles ──────────────────────────────────────────────────────────────


def test_no_cycles(migrated):
    sop, _ = migrated
    by_id = {s.id: s for s in sop.steps}
    current = sop.steps[0].id
    seen: set[str] = set()
    while current is not None:
        assert current not in seen, f"{sop.id}: cycle detected at {current!r}"
        seen.add(current)
        current = by_id[current].next_step_id


# ── 8: no orphans ─────────────────────────────────────────────────────────────


def test_no_orphaned_steps(migrated):
    """Every step must be reachable from the first step."""
    sop, _ = migrated
    reachable = set(_traverse(sop))
    orphans = [s.id for s in sop.steps if s.id not in reachable]
    assert not orphans, f"{sop.id}: unreachable steps {orphans}"


# ── 9: the engine actually executes the whole procedure ───────────────────────


def _make_context(**extra):
    from maiw_agents.contracts.runtime import AgentExecutionContext

    bounded = {
        "wave_id": "wave-17",
        "at_risk_count": 3,
        "carrier_cutoff_minutes": 47,
        "primary_constraint": "labor",
        "domains_affected": "labor",
    }
    bounded.update(extra)
    return AgentExecutionContext(
        warehouse_id="wh-test",
        trace_id="trace-v1-migration",
        bounded_context=bounded,
    )


def _make_definition(agent_id: str):
    from maiw_agents.contracts.agent import AgentDefinition

    return AgentDefinition(
        agent_id=agent_id,
        version="1.0",
        objective="migration test",
        domain="operations",
        allowed_capabilities=[],
        allowed_subagents=[],
        output_contract="Assessment",
    )


class _AlwaysCompletesExecutor:
    """Mock SOPStepExecutor: every step reports COMPLETED with no output."""

    RUNTIME_NAME = "migration-test"

    def __init__(self) -> None:
        self.executed: list[str] = []

    async def execute_step(
        self, *, definition, step, procedure_state, context, attempt
    ):
        from maiw_agents.contracts.step_result import StepResult, StepStatus

        self.executed.append(step.id)
        now = datetime.now(timezone.utc)
        return StepResult(
            step_id=step.id,
            status=StepStatus.COMPLETED,
            output={},
            runtime=self.RUNTIME_NAME,
            attempt=attempt,
            started_at=now,
            completed_at=now,
        )


@pytest.mark.asyncio
async def test_engine_completes_every_step_not_just_the_first(migrated):
    from maiw_agents.contracts.procedure_state import ProcedureStatus
    from maiw_agents.sop_engine import SOPEngine

    sop, expected_chain = migrated
    executor = _AlwaysCompletesExecutor()
    engine = SOPEngine(executor=executor)

    state = await engine.run_procedure(
        definition=_make_definition(sop.agent),
        sop=sop,
        agent_task_id="task-v1-migration",
        context=_make_context(),
    )

    assert state.status is ProcedureStatus.COMPLETED
    assert state.completed_step_ids == expected_chain
    assert state.branch_history == expected_chain
    assert (
        len(state.completed_step_ids) > 1
    ), "regression: the procedure terminated after a single step"


@pytest.mark.asyncio
async def test_engine_pre_migration_would_have_stopped_at_one_step(migrated):
    """
    Guard the semantics this migration depends on: stripping next_step_id
    reproduces the old single-step behaviour. If this ever fails, the engine's
    terminal rule changed and the migration's premise must be re-examined.
    """
    from maiw_agents.contracts.procedure_state import ProcedureStatus
    from maiw_agents.sop_engine import SOPEngine

    sop, expected_chain = migrated
    stripped = sop.model_copy(
        update={
            "steps": [s.model_copy(update={"next_step_id": None}) for s in sop.steps]
        }
    )

    engine = SOPEngine(executor=_AlwaysCompletesExecutor())
    state = await engine.run_procedure(
        definition=_make_definition(sop.agent),
        sop=stripped,
        agent_task_id="task-pre-migration",
        context=_make_context(),
    )

    assert state.status is ProcedureStatus.COMPLETED
    assert state.completed_step_ids == [expected_chain[0]]


# ── 10: iteration budget vs step count ────────────────────────────────────────


@pytest.mark.parametrize(
    "agent_id,sop_rel",
    [
        ("labor", "labor/labor_constraint_assessment.v1.yaml"),
        ("wave", "wave/wave_risk_assessment.v1.yaml"),
        (
            "operations_coordination",
            "operations_coordination/wave_risk_resolution.v1.yaml",
        ),
    ],
)
def test_agent_iteration_budget_covers_its_sop(agent_id, sop_rel):
    """
    max_iterations is the SOP *step transition* budget: MAIWDeterministicRuntime
    passes (max_iterations - state.iteration) to SOPEngine as max_transitions.
    A budget smaller than the SOP's step count escalates a perfectly valid
    procedure before it can finish.
    """
    from maiw_agents.contracts.definitions import AGENT_DEFINITIONS
    from maiw_agents.contracts.sop import load_sop

    sop = load_sop(SOP_DIR / sop_rel)
    definition = AGENT_DEFINITIONS[agent_id]
    budget = definition.termination_policy.max_iterations

    assert budget >= len(sop.steps), (
        f"{agent_id}: max_iterations={budget} cannot execute "
        f"{sop.id} ({len(sop.steps)} steps) — procedure would escalate early"
    )


@pytest.mark.asyncio
async def test_labor_sop_traverses_all_steps_without_iteration_cap():
    """Labor SOP has 8 steps. It must complete all of them, not escalate."""
    from maiw_agents.contracts.definitions import LABOR_AGENT_DEFINITION
    from maiw_agents.contracts.procedure_state import ProcedureStatus
    from maiw_agents.contracts.sop import load_sop
    from maiw_agents.sop_engine import SOPEngine

    sop = load_sop(SOP_DIR / "labor" / "labor_constraint_assessment.v1.yaml")
    assert len(sop.steps) == 8

    budget = LABOR_AGENT_DEFINITION.termination_policy.max_iterations
    engine = SOPEngine(executor=_AlwaysCompletesExecutor(), max_transitions=budget)

    state = await engine.run_procedure(
        definition=LABOR_AGENT_DEFINITION,
        sop=sop,
        agent_task_id="task-labor-8-steps",
        context=_make_context(),
    )

    assert (
        state.status is ProcedureStatus.COMPLETED
    ), f"labor SOP escalated under max_iterations={budget}"
    assert state.completed_step_ids == [s.id for s in sop.steps]
    assert len(state.completed_step_ids) == 8


@pytest.mark.asyncio
async def test_wave_sop_traverses_all_steps_without_iteration_cap():
    """Wave SOP has 7 steps. It must complete all of them, not escalate."""
    from maiw_agents.contracts.definitions import WAVE_AGENT_DEFINITION
    from maiw_agents.contracts.procedure_state import ProcedureStatus
    from maiw_agents.contracts.sop import load_sop
    from maiw_agents.sop_engine import SOPEngine

    sop = load_sop(SOP_DIR / "wave" / "wave_risk_assessment.v1.yaml")
    assert len(sop.steps) == 7

    budget = WAVE_AGENT_DEFINITION.termination_policy.max_iterations
    engine = SOPEngine(executor=_AlwaysCompletesExecutor(), max_transitions=budget)

    state = await engine.run_procedure(
        definition=WAVE_AGENT_DEFINITION,
        sop=sop,
        agent_task_id="task-wave-7-steps",
        context=_make_context(),
    )

    assert state.status is ProcedureStatus.COMPLETED
    assert len(state.completed_step_ids) == 7


@pytest.mark.asyncio
async def test_runaway_loop_still_escalates():
    """
    The iteration budget must still stop a genuine runaway. A hand-built SOP
    that branches back on failure (which validate_sop()'s static next_step_id
    cycle check does not cover) must exhaust max_transitions and ESCALATE.
    """
    from maiw_agents.contracts.procedure_state import ProcedureStatus
    from maiw_agents.contracts.sop import SOPDefinition, SOPStep
    from maiw_agents.contracts.sop_v2 import EscalationReasonCode
    from maiw_agents.contracts.step_result import StepResult, StepStatus
    from maiw_agents.sop_engine import SOPEngine

    class _AlwaysFailsExecutor:
        RUNTIME_NAME = "migration-test-fail"

        async def execute_step(
            self, *, definition, step, procedure_state, context, attempt
        ):
            now = datetime.now(timezone.utc)
            return StepResult(
                step_id=step.id,
                status=StepStatus.FAILED,
                output={},
                runtime=self.RUNTIME_NAME,
                attempt=attempt,
                started_at=now,
                completed_at=now,
                error="always fails",
            )

    # a -> (on failure) -> b -> (on failure) -> a : an unbounded ping-pong that
    # the static next_step_id cycle check cannot see.
    sop = SOPDefinition(
        id="test.runaway",
        version="1.0",
        agent="operations_coordination",
        objective="provoke a runaway loop",
        stop_conditions=["max_iterations_reached"],
        steps=[
            SOPStep(id="a", action="no_op", next_step_id=None, on_failure_step_id="b"),
            SOPStep(id="b", action="no_op", next_step_id=None, on_failure_step_id="a"),
        ],
    )

    engine = SOPEngine(executor=_AlwaysFailsExecutor(), max_transitions=10)
    state = await engine.run_procedure(
        definition=_make_definition("operations_coordination"),
        sop=sop,
        agent_task_id="task-runaway",
        context=_make_context(),
    )

    assert (
        state.status is ProcedureStatus.ESCALATED
    ), "runaway loop was not stopped by the transition budget"
    reasons = {
        r.escalation_reason
        for r in state.step_results.values()
        if r.escalation_reason is not None
    }
    assert EscalationReasonCode.POLICY_CONFLICT in reasons


# ── Cross-cutting: nothing else about the SOPs changed ────────────────────────


def test_migration_added_no_write_capabilities(migrated):
    """The migration is sequencing-only: no capability may have been added."""
    import re

    sop, _ = migrated
    write_pattern = re.compile(
        r"^(warehouse\.(labor\.assign|wave\.assign|equipment\.(assign|release_direct|deploy))|"
        r"action_executor\.|exec\.)",
        re.IGNORECASE,
    )
    for cap in sop.allowed_capabilities:
        assert not write_pattern.match(cap), f"{sop.id}: write capability {cap!r}"


def test_migrated_sops_declare_no_v2_step_fields(migrated):
    """
    The migration adds only next_step_id — a V1 navigation field. These SOPs must
    still be pure V1: no completion specs, retry policies, or timeouts.
    """
    sop, _ = migrated
    for step in sop.steps:
        assert step.completion is None
        assert step.retry_policy is None
        assert step.timeout_seconds is None
        assert step.required_inputs is None
        assert step.evidence_requirements is None


def test_versions_were_incremented(migrated):
    """Traversal semantics changed, so the SOP version must have moved off 1.0."""
    sop, _ = migrated
    assert (
        sop.version != "1.0"
    ), f"{sop.id}: traversal semantics changed but version is still 1.0"
