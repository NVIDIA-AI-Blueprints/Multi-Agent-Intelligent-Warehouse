# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIWDeterministicRuntime as a SOPStepExecutor.

The behavioural change under test: the runtime no longer decides that a step is
done. It produces a StepResult; the SOP Engine validates it and only then
advances.
"""

from __future__ import annotations

import pytest

from maiw_agents.contracts.procedure_state import ProcedureStatus
from maiw_agents.contracts.sop import SOPDefinition, SOPStep
from maiw_agents.contracts.sop_v2 import (
    EscalationReasonCode,
    StepCompletionSpec,
    ValidatorType,
)
from maiw_agents.contracts.step_result import StepResult, StepStatus
from maiw_agents.contracts.task import AgentTaskState, AgentTaskStatus
from maiw_agents.runtime.deterministic import MAIWDeterministicRuntime
from maiw_agents.sop_engine import SOPEngine, SOPStepExecutor

from conftest import make_procedure_state, make_sop


@pytest.fixture
def runtime() -> MAIWDeterministicRuntime:
    return MAIWDeterministicRuntime()


@pytest.fixture
def task_state() -> AgentTaskState:
    return AgentTaskState(
        task_id="task-det-v2",
        agent_id="operations_coordination",
        sop_id="test.sop",
        sop_version="1.0",
        objective="test",
    )


# ── Protocol conformance ──────────────────────────────────────────────────────

def test_runtime_implements_sop_step_executor(runtime):
    assert isinstance(runtime, SOPStepExecutor)


def test_runtime_still_implements_agent_runtime(runtime):
    from maiw_agents.contracts.runtime import AgentRuntime

    assert isinstance(runtime, AgentRuntime)


# ── execute_step ──────────────────────────────────────────────────────────────

async def test_execute_step_returns_step_result(runtime, definition, context):
    step = SOPStep(id="s1", action="no_op")

    result = await runtime.execute_step(
        definition=definition,
        step=step,
        procedure_state=make_procedure_state(current_step_id="s1"),
        context=context,
        attempt=1,
    )

    assert isinstance(result, StepResult)
    assert result.step_id == "s1"
    assert result.runtime == "deterministic"
    assert result.attempt == 1
    assert result.evidence, "a step execution must leave evidence"


async def test_execute_step_satisfies_declared_schema_from_bounded_context(
    runtime, definition, context
):
    """The runtime's execution model is bounded_context in, structured output out."""
    step = SOPStep(
        id="s1", action="gather_operational_context",
        completion=StepCompletionSpec(
            validator_type=ValidatorType.SCHEMA,
            schema_fields=["wave_id", "at_risk_count"],
        ),
    )

    result = await runtime.execute_step(
        definition=definition,
        step=step,
        procedure_state=make_procedure_state(current_step_id="s1"),
        context=context,
        attempt=1,
    )

    assert result.output["wave_id"] == "wave-17"
    assert result.output["at_risk_count"] == 3


async def test_execute_step_records_attempt_number(runtime, definition, context):
    step = SOPStep(id="s1", action="no_op")
    result = await runtime.execute_step(
        definition=definition,
        step=step,
        procedure_state=make_procedure_state(current_step_id="s1"),
        context=context,
        attempt=4,
    )
    assert result.attempt == 4
    assert result.evidence[0].metadata["attempt"] == 4


# ── Write guard preserved ─────────────────────────────────────────────────────

@pytest.mark.parametrize("action", ["write", "execute", "mutate"])
async def test_execute_step_rejects_write_actions(runtime, definition, context, action):
    step = SOPStep.model_construct(id="bad", action=action)

    result = await runtime.execute_step(
        definition=definition,
        step=step,
        procedure_state=make_procedure_state(current_step_id="bad"),
        context=context,
        attempt=1,
    )

    assert result.status is StepStatus.FAILED
    assert result.escalation_reason is EscalationReasonCode.POLICY_CONFLICT
    assert result.output == {}


async def test_write_action_fails_the_procedure(runtime, definition, context):
    sop = make_sop([SOPStep.model_construct(id="bad", action="write")])
    engine = SOPEngine(executor=runtime)

    state = await engine.run_procedure(
        definition=definition, sop=sop, agent_task_id="t", context=context
    )

    assert state.status is ProcedureStatus.FAILED


async def test_write_capability_in_sop_still_raises(runtime, task_state, context):
    from maiw_agents.contracts.agent import AgentDefinition

    sop = SOPDefinition.model_construct(
        id="test.bad_sop", version="1.0", agent="test_agent", objective="test",
        steps=[SOPStep(id="s1", action="no_op")],
        stop_conditions=["objective_met"],
        allowed_capabilities=["warehouse.labor.assign_direct"],
        allowed_subagents=[], triggers=[], escalation=[], required_context=[],
    )
    bad_definition = AgentDefinition(
        agent_id="test_agent", version="1.0", objective="test", domain="test",
        allowed_capabilities=["warehouse.labor.assign_direct"],
        output_contract="test",
    )

    with pytest.raises(ValueError, match="WRITE capability"):
        await runtime.run_task(bad_definition, sop, task_state, context)


# ── The engine, not the runtime, decides completion ───────────────────────────

async def test_v2_step_does_not_advance_when_validator_fails(
    runtime, definition, context, task_state
):
    """The runtime returns COMPLETED; the unsatisfiable schema blocks advancement."""
    sop = make_sop([
        SOPStep(
            id="s1", action="no_op", next_step_id="s2",
            completion=StepCompletionSpec(
                validator_type=ValidatorType.SCHEMA,
                schema_fields=["field_not_in_context"],
            ),
        ),
        SOPStep(id="s2", action="no_op"),
    ])

    result = await runtime.run_task(definition, sop, task_state, context)

    assert result.final_status is AgentTaskStatus.FAILED
    assert all(o["step_id"] != "s2" for o in result.observations)


async def test_v2_step_advances_when_validator_passes(
    runtime, definition, context, task_state
):
    sop = make_sop([
        SOPStep(
            id="s1", action="no_op", next_step_id="s2",
            completion=StepCompletionSpec(
                validator_type=ValidatorType.SCHEMA, schema_fields=["wave_id"]
            ),
        ),
        SOPStep(id="s2", action="no_op"),
    ])

    result = await runtime.run_task(definition, sop, task_state, context)

    assert result.final_status is AgentTaskStatus.COMPLETED
    assert [o["step_id"] for o in result.observations] == ["s1", "s2"]


async def test_observations_record_the_validator_that_cleared_each_step(
    runtime, definition, context, task_state
):
    sop = make_sop([
        SOPStep(
            id="s1", action="no_op",
            completion=StepCompletionSpec(
                validator_type=ValidatorType.SCHEMA, schema_fields=["wave_id"]
            ),
        )
    ])

    result = await runtime.run_task(definition, sop, task_state, context)

    assert result.observations[0]["validator"] == ValidatorType.SCHEMA.value


# ── V1 behaviour preserved ────────────────────────────────────────────────────

async def test_v1_step_completes_via_legacy_success(
    runtime, definition, context, task_state
):
    sop = make_sop([SOPStep(id="s1", action="no_op")])

    result = await runtime.run_task(definition, sop, task_state, context)

    assert result.final_status is AgentTaskStatus.COMPLETED
    assert result.stop_reason == "OBJECTIVE_MET"
    assert result.observations[0]["validator"] == ValidatorType.LEGACY_SUCCESS.value


async def test_empty_sop_fails(runtime, definition, context, task_state):
    sop = SOPDefinition.model_construct(
        id="empty", version="1.0", agent="a", objective="o", steps=[],
        stop_conditions=["objective_met"], allowed_capabilities=[],
        allowed_subagents=[], triggers=[], escalation=[], required_context=[],
    )

    result = await runtime.run_task(definition, sop, task_state, context)
    assert result.final_status is AgentTaskStatus.FAILED


async def test_assessment_and_candidates_are_surfaced(runtime, definition, context):
    """The return-assessment step still lifts _agent_result out of bounded_context."""
    from maiw_agents.contracts.runtime import AgentExecutionContext

    ctx = AgentExecutionContext(
        warehouse_id="wh", trace_id="t",
        bounded_context={
            "_agent_result": {
                "summary": "labor constrained",
                "candidate_actions": [{"action": "reallocate", "priority": "high"}],
            }
        },
    )
    state = AgentTaskState(
        task_id="t1", agent_id="labor", sop_id="labor.x",
        sop_version="1.0", objective="o",
    )
    sop = make_sop([SOPStep(id="ret", action="return_labor_assessment")])

    result = await runtime.run_task(definition, sop, state, ctx)

    assert result.final_status is AgentTaskStatus.COMPLETED
    assert result.assessment["result"]["summary"] == "labor constrained"
    assert result.candidate_actions == [{"action": "reallocate", "priority": "high"}]


# ── Iteration budget ──────────────────────────────────────────────────────────

async def test_iteration_budget_already_spent_escalates(runtime, definition, context):
    spent = AgentTaskState(
        task_id="t", agent_id="a", sop_id="s", sop_version="1.0",
        objective="o", iteration=definition.termination_policy.max_iterations,
    )
    sop = make_sop([SOPStep(id="s1", action="no_op")])

    result = await runtime.run_task(definition, sop, spent, context)

    assert result.final_status is AgentTaskStatus.ESCALATED
    assert "Max iterations" in (result.escalation_reason or "")
