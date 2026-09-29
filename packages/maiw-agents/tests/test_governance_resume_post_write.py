# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Post-write completion — the hard invariant (Design Section 34).

Scenario under test, end to end:

    equipment assign step  →  WAITING_FOR_GOVERNANCE
                           →  governance APPROVED
                           →  authoritative re-read of warehouse state
                           →  STATE_PREDICATE decides COMPLETED or ESCALATED

A write-related step must never complete because governance returned APPROVED,
because a call returned 2xx, or because a model judged the response valid. And
an ambiguous outcome must never be resolved by re-issuing the write.
"""

from __future__ import annotations

import pytest

from maiw_agents.contracts.delegation import GovernanceOutcome
from maiw_agents.contracts.procedure_state import ProcedureStatus
from maiw_agents.contracts.sop import SOPStep
from maiw_agents.contracts.sop_v2 import (
    EscalationReasonCode,
    RetryPolicy,
    StepCompletionSpec,
    ValidatorType,
)
from maiw_agents.contracts.step_result import StepStatus
from maiw_agents.sop_engine import SOPEngine
from maiw_agents.sop_engine.validators import register_predicate, unregister_predicate

from conftest import ScriptedExecutor, make_sop, make_step_result

PREDICATE = "t_equipment_assigned"


@pytest.fixture(autouse=True)
def equipment_predicate():
    """Authoritative check: is the equipment actually assigned to the wave?"""

    def equipment_assigned(state, args):
        assignments = state.get("equipment_assignments", {})
        return assignments.get(args["equipment_id"]) == args["expected_wave_id"]

    register_predicate(PREDICATE, equipment_assigned)
    yield
    unregister_predicate(PREDICATE)


def _assign_sop(**step_overrides):
    return make_sop([
        SOPStep(
            id="assign_equipment",
            action="emit_recommended_action",
            objective="Assign forklift FL-9 to wave-17",
            completion=StepCompletionSpec(
                validator_type=ValidatorType.STATE_PREDICATE,
                predicate_name=PREDICATE,
                predicate_args={"equipment_id": "FL-9", "expected_wave_id": "wave-17"},
            ),
            evidence_requirements=["state_snapshot", "state_comparison"],
            **step_overrides,
        )
    ])


def _outcome(decision="APPROVED", execution="EXECUTED") -> GovernanceOutcome:
    return GovernanceOutcome(
        proposal_id="prop-001",
        decision_outcome=decision,
        execution_status=execution,
        execution_id="exec-001",
        resulting_context_snapshot_id="snap-post",
        trace_id="trace-sop-engine-v2",
    )


async def _pause(engine, definition, sop, context):
    state = await engine.run_procedure(
        definition=definition, sop=sop, agent_task_id="task-assign", context=context
    )
    assert state.status is ProcedureStatus.WAITING_FOR_GOVERNANCE
    assert state.current_step_id == "assign_equipment"
    return state


@pytest.fixture
def paused_engine():
    executor = ScriptedExecutor({
        "assign_equipment": [
            make_step_result("assign_equipment", status=StepStatus.WAITING_FOR_GOVERNANCE)
        ]
    })
    return SOPEngine(executor=executor), executor


# ── The pause ─────────────────────────────────────────────────────────────────

async def test_write_step_pauses_for_governance(paused_engine, definition, context):
    engine, executor = paused_engine
    state = await _pause(engine, definition, _assign_sop(), context)

    assert state.completed_step_ids == [], "the write step must not be completed yet"
    assert executor.calls == [("assign_equipment", 1)]


async def test_pause_does_not_run_the_predicate(paused_engine, definition, context):
    """Validation is deferred until there is post-execution state to read."""
    engine, _ = paused_engine
    state = await _pause(engine, definition, _assign_sop(), context)

    assert state.step_results["assign_equipment"].validation_result is None


# ── Confirmed write ───────────────────────────────────────────────────────────

async def test_confirmed_state_completes_the_step(paused_engine, definition, context):
    engine, _ = paused_engine
    sop = _assign_sop()
    paused = await _pause(engine, definition, sop, context)

    resumed = await engine.resume_after_governance(
        definition=definition, sop=sop, proc_state=paused, context=context,
        governance_outcome=_outcome(),
        warehouse_state_snapshot={"equipment_assignments": {"FL-9": "wave-17"}},
    )

    assert resumed.status is ProcedureStatus.COMPLETED
    assert resumed.completed_step_ids == ["assign_equipment"]
    result = resumed.step_results["assign_equipment"]
    assert result.status is StepStatus.COMPLETED
    assert result.validation_result.validator_type is ValidatorType.STATE_PREDICATE
    assert result.validation_result.valid is True


async def test_completion_evidence_names_the_predicate(paused_engine, definition, context):
    engine, _ = paused_engine
    sop = _assign_sop()
    paused = await _pause(engine, definition, sop, context)

    resumed = await engine.resume_after_governance(
        definition=definition, sop=sop, proc_state=paused, context=context,
        governance_outcome=_outcome(),
        warehouse_state_snapshot={"equipment_assignments": {"FL-9": "wave-17"}},
    )

    evidence = resumed.step_results["assign_equipment"].evidence
    assert any(e.metadata.get("predicate_name") == PREDICATE for e in evidence)
    assert any(e.type == "validator_result" for e in evidence)


# ── Unconfirmed write ─────────────────────────────────────────────────────────

async def test_unconfirmed_state_escalates_not_completes(paused_engine, definition, context):
    """Governance approved and execution reported success — but nothing changed."""
    engine, _ = paused_engine
    sop = _assign_sop()
    paused = await _pause(engine, definition, sop, context)

    resumed = await engine.resume_after_governance(
        definition=definition, sop=sop, proc_state=paused, context=context,
        governance_outcome=_outcome(),
        warehouse_state_snapshot={"equipment_assignments": {}},
    )

    assert resumed.status is ProcedureStatus.ESCALATED
    assert resumed.completed_step_ids == []
    result = resumed.step_results["assign_equipment"]
    assert result.status is StepStatus.ESCALATED
    assert result.escalation_reason is EscalationReasonCode.VALIDATION_FAILED


async def test_wrong_target_state_escalates(paused_engine, definition, context):
    """The forklift was assigned — to the wrong wave. That is not completion."""
    engine, _ = paused_engine
    sop = _assign_sop()
    paused = await _pause(engine, definition, sop, context)

    resumed = await engine.resume_after_governance(
        definition=definition, sop=sop, proc_state=paused, context=context,
        governance_outcome=_outcome(),
        warehouse_state_snapshot={"equipment_assignments": {"FL-9": "wave-99"}},
    )

    assert resumed.status is ProcedureStatus.ESCALATED


async def test_missing_snapshot_escalates(paused_engine, definition, context):
    """No authoritative state to read means no proof, so no completion."""
    engine, _ = paused_engine
    sop = _assign_sop()
    paused = await _pause(engine, definition, sop, context)

    resumed = await engine.resume_after_governance(
        definition=definition, sop=sop, proc_state=paused, context=context,
        governance_outcome=_outcome(), warehouse_state_snapshot=None,
    )

    assert resumed.status is ProcedureStatus.ESCALATED


# ── Indeterminate execution ───────────────────────────────────────────────────

@pytest.mark.parametrize("execution_status", ["UNKNOWN", "INDETERMINATE", "TIMEOUT"])
async def test_indeterminate_execution_escalates_with_its_own_code(
    paused_engine, definition, context, execution_status
):
    engine, _ = paused_engine
    sop = _assign_sop()
    paused = await _pause(engine, definition, sop, context)

    resumed = await engine.resume_after_governance(
        definition=definition, sop=sop, proc_state=paused, context=context,
        governance_outcome=_outcome(execution=execution_status),
        warehouse_state_snapshot={"equipment_assignments": {}},
    )

    assert resumed.status is ProcedureStatus.ESCALATED
    assert (
        resumed.step_results["assign_equipment"].escalation_reason
        is EscalationReasonCode.EXECUTION_INDETERMINATE
    )


async def test_indeterminate_but_state_confirms_still_completes(
    paused_engine, definition, context
):
    """
    Ambiguity is resolved by reading, not by retrying. If authoritative state
    proves the write landed, the step completes despite the unclear response.
    """
    engine, _ = paused_engine
    sop = _assign_sop()
    paused = await _pause(engine, definition, sop, context)

    resumed = await engine.resume_after_governance(
        definition=definition, sop=sop, proc_state=paused, context=context,
        governance_outcome=_outcome(execution="UNKNOWN"),
        warehouse_state_snapshot={"equipment_assignments": {"FL-9": "wave-17"}},
    )

    assert resumed.status is ProcedureStatus.COMPLETED


async def test_resume_never_re_executes_the_step(paused_engine, definition, context):
    """The decisive safety property: resuming must not re-issue the write."""
    engine, executor = paused_engine
    sop = _assign_sop()
    paused = await _pause(engine, definition, sop, context)
    calls_before = list(executor.calls)

    await engine.resume_after_governance(
        definition=definition, sop=sop, proc_state=paused, context=context,
        governance_outcome=_outcome(execution="UNKNOWN"),
        warehouse_state_snapshot={"equipment_assignments": {}},
    )

    assert executor.calls == calls_before, (
        "resume_after_governance must not call the executor again"
    )


async def test_write_step_cannot_declare_a_blind_retry_policy():
    """The contract makes the unsafe configuration unbuildable."""
    with pytest.raises(Exception, match="authoritative reread"):
        RetryPolicy(max_attempts=3, retry_on=["EXECUTION_INDETERMINATE"])


async def test_escalation_message_is_actionable(paused_engine, definition, context):
    engine, _ = paused_engine
    sop = _assign_sop()
    paused = await _pause(engine, definition, sop, context)

    resumed = await engine.resume_after_governance(
        definition=definition, sop=sop, proc_state=paused, context=context,
        governance_outcome=_outcome(),
        warehouse_state_snapshot={"equipment_assignments": {}},
    )

    message = resumed.step_results["assign_equipment"].escalation_message
    assert "Post-governance validation failed" in message
    assert PREDICATE in message


# ── Deep Agents runtime wrapper ───────────────────────────────────────────────

async def test_runtime_resume_escalates_when_state_does_not_confirm(definition, context):
    from maiw_agents.contracts.task import AgentTaskState, AgentTaskStatus
    from maiw_agents.runtime.deep_agents_runtime import DeepAgentsRuntime

    sop = _assign_sop()
    state = AgentTaskState(
        task_id="task-assign", agent_id=definition.agent_id,
        sop_id=sop.id, sop_version=sop.version, objective="assign",
        status=AgentTaskStatus.WAITING_FOR_GOVERNANCE,
        current_step_id="assign_equipment",
    )
    context.bounded_context["_warehouse_state_snapshot"] = {"equipment_assignments": {}}

    result = await DeepAgentsRuntime().resume_after_governance(
        definition, sop, state, context,
        governance_outcome={"decision_outcome": "APPROVED", "execution_status": "EXECUTED"},
    )

    assert result.final_status is AgentTaskStatus.ESCALATED
    assert EscalationReasonCode.VALIDATION_FAILED.value in result.escalation_reason


async def test_runtime_resume_completes_when_state_confirms(definition, context):
    from maiw_agents.contracts.task import AgentTaskState, AgentTaskStatus
    from maiw_agents.runtime.deep_agents_runtime import DeepAgentsRuntime

    sop = _assign_sop()
    state = AgentTaskState(
        task_id="task-assign", agent_id=definition.agent_id,
        sop_id=sop.id, sop_version=sop.version, objective="assign",
        status=AgentTaskStatus.WAITING_FOR_GOVERNANCE,
        current_step_id="assign_equipment",
    )
    context.bounded_context["_warehouse_state_snapshot"] = {
        "equipment_assignments": {"FL-9": "wave-17"}
    }

    result = await DeepAgentsRuntime().resume_after_governance(
        definition, sop, state, context,
        governance_outcome={"decision_outcome": "APPROVED", "execution_status": "EXECUTED"},
    )

    assert result.final_status is AgentTaskStatus.COMPLETED
    assert result.stop_reason == "OBJECTIVE_MET"


async def test_runtime_resume_records_validation_observation(definition, context):
    from maiw_agents.contracts.task import AgentTaskState, AgentTaskStatus
    from maiw_agents.runtime.deep_agents_runtime import DeepAgentsRuntime

    sop = _assign_sop()
    state = AgentTaskState(
        task_id="task-assign", agent_id=definition.agent_id,
        sop_id=sop.id, sop_version=sop.version, objective="assign",
        status=AgentTaskStatus.WAITING_FOR_GOVERNANCE,
        current_step_id="assign_equipment",
    )
    context.bounded_context["_warehouse_state_snapshot"] = {
        "equipment_assignments": {"FL-9": "wave-17"}
    }

    result = await DeepAgentsRuntime().resume_after_governance(
        definition, sop, state, context,
        governance_outcome={"decision_outcome": "APPROVED", "execution_status": "EXECUTED"},
    )

    validation_obs = [
        o for o in result.observations
        if o.get("observation_type") == "post_write_validation"
    ]
    assert validation_obs, "resume must record that post-write validation ran"
    assert validation_obs[0]["facts"]["validator"] == ValidatorType.STATE_PREDICATE.value
    assert validation_obs[0]["facts"]["valid"] is True
