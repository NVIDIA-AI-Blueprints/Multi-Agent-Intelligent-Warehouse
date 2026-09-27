# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
SOP Engine procedure lifecycle: progression, validation, retry, escalation,
governance pause/resume and evidence accumulation.

The single invariant under test throughout: a step advances because its declared
completion criterion was proven, not because the executor said it was done.
"""

from __future__ import annotations

import pytest

from maiw_agents.contracts.procedure_state import ProcedureStatus
from maiw_agents.contracts.sop import SOPStep, StepCondition
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


def _schema_step(step_id: str, fields: list[str], **kw) -> SOPStep:
    return SOPStep(
        id=step_id,
        action="no_op",
        completion=StepCompletionSpec(
            validator_type=ValidatorType.SCHEMA, schema_fields=fields
        ),
        **kw,
    )


async def _run(engine, definition, sop, context, **kw):
    return await engine.run_procedure(
        definition=definition,
        sop=sop,
        agent_task_id="task-test",
        context=context,
        **kw,
    )


# ── Basic progression ─────────────────────────────────────────────────────────

async def test_single_step_completes_when_validator_passes(definition, context):
    sop = make_sop([_schema_step("s1", ["wave_id"])])
    executor = ScriptedExecutor(default_output={"wave_id": "w17"})
    engine = SOPEngine(executor=executor)

    state = await _run(engine, definition, sop, context)

    assert state.status is ProcedureStatus.COMPLETED
    assert state.completed_step_ids == ["s1"]
    assert state.step_results["s1"].status is StepStatus.COMPLETED
    assert state.step_results["s1"].validation_result.valid is True


async def test_single_step_fails_when_validator_fails(definition, context):
    """The executor claims COMPLETED; the validator disagrees and wins."""
    sop = make_sop([_schema_step("s1", ["wave_id"])])
    executor = ScriptedExecutor(default_output={})  # missing wave_id
    engine = SOPEngine(executor=executor)

    state = await _run(engine, definition, sop, context)

    assert state.status is ProcedureStatus.FAILED
    assert state.completed_step_ids == []
    result = state.step_results["s1"]
    assert result.status is StepStatus.FAILED
    assert result.escalation_reason is EscalationReasonCode.VALIDATION_FAILED
    assert "wave_id" in result.validation_result.reason


async def test_executor_claim_of_completed_is_not_trusted(definition, context):
    """An executor returning status=COMPLETED with no proof must not advance."""
    sop = make_sop([_schema_step("s1", ["proof"])])
    executor = ScriptedExecutor({
        "s1": [make_step_result("s1", status=StepStatus.COMPLETED, output={"other": 1})]
    })
    engine = SOPEngine(executor=executor)

    state = await _run(engine, definition, sop, context)

    assert state.status is ProcedureStatus.FAILED


async def test_multi_step_traversal_follows_next_step_id(definition, context):
    sop = make_sop([
        SOPStep(id="a", action="no_op", next_step_id="b"),
        SOPStep(id="b", action="no_op", next_step_id="c"),
        SOPStep(id="c", action="no_op"),
    ])
    executor = ScriptedExecutor()
    engine = SOPEngine(executor=executor)

    state = await _run(engine, definition, sop, context)

    assert state.status is ProcedureStatus.COMPLETED
    assert state.completed_step_ids == ["a", "b", "c"]
    assert executor.step_ids == ["a", "b", "c"]


async def test_condition_false_skips_step_without_executing(definition, context):
    sop = make_sop([
        SOPStep(
            id="a", action="no_op", next_step_id="b",
            condition=StepCondition(predicate="domains_affected", operator="eq", value="equipment"),
        ),
        SOPStep(id="b", action="no_op"),
    ])
    executor = ScriptedExecutor()
    engine = SOPEngine(executor=executor)

    state = await _run(engine, definition, sop, context)

    assert state.status is ProcedureStatus.COMPLETED
    assert executor.step_ids == ["b"], "skipped step must not reach the executor"
    assert state.branch_history == ["a", "b"]


async def test_unknown_step_escalates(definition, context):
    sop = make_sop([SOPStep(id="a", action="no_op", next_step_id="does_not_exist")])
    engine = SOPEngine(executor=ScriptedExecutor())

    state = await _run(engine, definition, sop, context)

    assert state.status is ProcedureStatus.ESCALATED
    assert (
        state.step_results["does_not_exist"].escalation_reason
        is EscalationReasonCode.INVALID_OUTPUT
    )


async def test_missing_required_inputs_escalates_missing_data(definition, context):
    sop = make_sop([SOPStep(id="a", action="no_op", required_inputs=["not_in_context"])])
    executor = ScriptedExecutor()
    engine = SOPEngine(executor=executor)

    state = await _run(engine, definition, sop, context)

    assert state.status is ProcedureStatus.ESCALATED
    assert state.step_results["a"].escalation_reason is EscalationReasonCode.MISSING_DATA
    assert executor.calls == [], "a step missing its inputs must not run"


# ── Retry ─────────────────────────────────────────────────────────────────────

async def test_retry_fails_twice_then_succeeds(definition, context):
    sop = make_sop([
        _schema_step(
            "s1", ["wave_id"],
            retry_policy=RetryPolicy(max_attempts=3, backoff_seconds=0.0),
        )
    ])
    executor = ScriptedExecutor({
        "s1": [
            make_step_result("s1", output={}),
            make_step_result("s1", output={}),
            make_step_result("s1", output={"wave_id": "w17"}),
        ]
    })
    engine = SOPEngine(executor=executor)

    state = await _run(engine, definition, sop, context)

    assert state.status is ProcedureStatus.COMPLETED
    assert executor.calls == [("s1", 1), ("s1", 2), ("s1", 3)]
    assert state.attempt_by_step["s1"] == 3
    assert state.step_results["s1"].attempt == 3


async def test_retry_budget_exhausted_escalates(definition, context):
    sop = make_sop([
        _schema_step(
            "s1", ["wave_id"],
            retry_policy=RetryPolicy(max_attempts=2, backoff_seconds=0.0),
        )
    ])
    executor = ScriptedExecutor(default_output={})
    engine = SOPEngine(executor=executor)

    state = await _run(engine, definition, sop, context)

    assert state.status is ProcedureStatus.ESCALATED
    assert executor.calls == [("s1", 1), ("s1", 2)]
    result = state.step_results["s1"]
    assert result.status is StepStatus.ESCALATED
    assert result.escalation_reason is EscalationReasonCode.RETRY_BUDGET_EXHAUSTED


async def test_non_retryable_failure_does_not_retry(definition, context):
    """An unregistered predicate is unfixable by repetition — one attempt only."""
    sop = make_sop([
        SOPStep(
            id="s1", action="no_op",
            completion=StepCompletionSpec(
                validator_type=ValidatorType.STATE_PREDICATE,
                predicate_name="never_registered",
            ),
            retry_policy=RetryPolicy(max_attempts=5, backoff_seconds=0.0),
        )
    ])
    executor = ScriptedExecutor()
    engine = SOPEngine(executor=executor)

    state = await _run(engine, definition, sop, context)

    assert executor.calls == [("s1", 1)]
    assert state.status is ProcedureStatus.FAILED
    assert (
        state.step_results["s1"].escalation_reason
        is EscalationReasonCode.VALIDATION_FAILED
    ), "a non-retryable failure must keep its real reason, not become budget exhaustion"


async def test_no_retry_policy_means_single_attempt(definition, context):
    sop = make_sop([_schema_step("s1", ["wave_id"])])
    executor = ScriptedExecutor(default_output={})
    engine = SOPEngine(executor=executor)

    await _run(engine, definition, sop, context)

    assert executor.calls == [("s1", 1)]


async def test_retry_policy_cannot_be_built_for_ambiguous_writes():
    """Restated at the engine layer: the contract makes blind write retry unbuildable."""
    with pytest.raises(Exception, match="authoritative reread"):
        RetryPolicy(max_attempts=3, retry_on=["WRITE_AMBIGUOUS"])


# ── Governance pause ──────────────────────────────────────────────────────────

async def test_governance_pause_stops_procedure(definition, context):
    sop = make_sop([
        SOPStep(id="submit", action="emit_recommended_action", next_step_id="observe"),
        SOPStep(id="observe", action="evaluate_post_execution_state"),
    ])
    executor = ScriptedExecutor({
        "submit": [make_step_result("submit", status=StepStatus.WAITING_FOR_GOVERNANCE)]
    })
    engine = SOPEngine(executor=executor)

    state = await _run(engine, definition, sop, context)

    assert state.status is ProcedureStatus.WAITING_FOR_GOVERNANCE
    assert state.current_step_id == "submit", "must stay on the paused step for resume"
    assert "observe" not in state.step_results
    assert executor.step_ids == ["submit"]


async def test_governance_pause_skips_validation(definition, context):
    """A pause is not a completion claim — it must not be validated or failed."""
    sop = make_sop([_schema_step("submit", ["impossible_field"])])
    executor = ScriptedExecutor({
        "submit": [make_step_result("submit", status=StepStatus.WAITING_FOR_GOVERNANCE)]
    })
    engine = SOPEngine(executor=executor)

    state = await _run(engine, definition, sop, context)

    assert state.status is ProcedureStatus.WAITING_FOR_GOVERNANCE
    assert state.step_results["submit"].validation_result is None


# ── Resume after governance ───────────────────────────────────────────────────

class _Outcome:
    def __init__(self, decision: str, execution: str) -> None:
        self.decision_outcome = decision
        self.execution_status = execution


@pytest.fixture
def risk_predicate():
    def wave_risk_reduced(state, args):
        return state.get("at_risk_count", 99) <= args.get("max_at_risk", 0)

    register_predicate("t_engine_risk_reduced", wave_risk_reduced)
    yield "t_engine_risk_reduced"
    unregister_predicate("t_engine_risk_reduced")


def _governed_sop(predicate_name: str):
    return make_sop([
        SOPStep(
            id="observe",
            action="evaluate_post_execution_state",
            completion=StepCompletionSpec(
                validator_type=ValidatorType.STATE_PREDICATE,
                predicate_name=predicate_name,
                predicate_args={"max_at_risk": 0},
            ),
        )
    ])


async def _pause_then_resume(definition, context, sop, outcome, snapshot, risk_predicate=None):
    executor = ScriptedExecutor({
        "observe": [make_step_result("observe", status=StepStatus.WAITING_FOR_GOVERNANCE)]
    })
    engine = SOPEngine(executor=executor)
    paused = await _run(engine, definition, sop, context)
    assert paused.status is ProcedureStatus.WAITING_FOR_GOVERNANCE

    return await engine.resume_after_governance(
        definition=definition,
        sop=sop,
        proc_state=paused,
        context=context,
        governance_outcome=outcome,
        warehouse_state_snapshot=snapshot,
    )


async def test_resume_with_confirming_state_advances(definition, context, risk_predicate):
    resumed = await _pause_then_resume(
        definition, context, _governed_sop(risk_predicate),
        _Outcome("APPROVED", "EXECUTED"), {"at_risk_count": 0},
    )

    assert resumed.status is ProcedureStatus.COMPLETED
    assert resumed.completed_step_ids == ["observe"]
    assert resumed.step_results["observe"].status is StepStatus.COMPLETED


async def test_resume_with_unconfirming_state_escalates_validation_failed(
    definition, context, risk_predicate
):
    """Governance said APPROVED, but the world did not change — do not complete."""
    resumed = await _pause_then_resume(
        definition, context, _governed_sop(risk_predicate),
        _Outcome("APPROVED", "EXECUTED"), {"at_risk_count": 3},
    )

    assert resumed.status is ProcedureStatus.ESCALATED
    result = resumed.step_results["observe"]
    assert result.escalation_reason is EscalationReasonCode.VALIDATION_FAILED
    assert result.status is StepStatus.ESCALATED


async def test_resume_with_indeterminate_execution_escalates(
    definition, context, risk_predicate
):
    resumed = await _pause_then_resume(
        definition, context, _governed_sop(risk_predicate),
        _Outcome("APPROVED", "INDETERMINATE"), {"at_risk_count": 3},
    )

    assert resumed.status is ProcedureStatus.ESCALATED
    assert (
        resumed.step_results["observe"].escalation_reason
        is EscalationReasonCode.EXECUTION_INDETERMINATE
    )


async def test_resume_indeterminate_cannot_be_closed_by_legacy_validator(definition, context):
    """
    A v1 step (no completion spec) must not be completed by an indeterminate
    write outcome. LEGACY_SUCCESS is not proof that a write landed.
    """
    sop = make_sop([SOPStep(id="observe", action="evaluate_post_execution_state")])

    resumed = await _pause_then_resume(
        definition, context, sop, _Outcome("APPROVED", "UNKNOWN"), None,
    )

    assert resumed.status is ProcedureStatus.ESCALATED
    assert (
        resumed.step_results["observe"].escalation_reason
        is EscalationReasonCode.EXECUTION_INDETERMINATE
    )


async def test_resume_determinate_v1_step_completes(definition, context):
    """A v1 step with a clean EXECUTED outcome still completes — no regression."""
    sop = make_sop([SOPStep(id="observe", action="evaluate_post_execution_state")])

    resumed = await _pause_then_resume(
        definition, context, sop, _Outcome("APPROVED", "EXECUTED"), None,
    )

    assert resumed.status is ProcedureStatus.COMPLETED


async def test_resume_without_current_step_raises(definition, context, risk_predicate):
    from conftest import make_procedure_state

    engine = SOPEngine(executor=ScriptedExecutor())
    state = make_procedure_state(current_step_id=None)

    with pytest.raises(ValueError, match="no current step"):
        await engine.resume_after_governance(
            definition=definition,
            sop=_governed_sop(risk_predicate),
            proc_state=state,
            context=context,
            governance_outcome=_Outcome("APPROVED", "EXECUTED"),
        )


# ── V1 compatibility through the engine ───────────────────────────────────────

async def test_v1_step_without_completion_uses_legacy_success(definition, context):
    sop = make_sop([SOPStep(id="a", action="no_op", next_step_id="b"),
                    SOPStep(id="b", action="no_op")])
    engine = SOPEngine(executor=ScriptedExecutor())

    state = await _run(engine, definition, sop, context)

    assert state.status is ProcedureStatus.COMPLETED
    for step_id in ("a", "b"):
        assert (
            state.step_results[step_id].validation_result.validator_type
            is ValidatorType.LEGACY_SUCCESS
        )


# ── Evidence ──────────────────────────────────────────────────────────────────

async def test_evidence_accumulates_across_steps(definition, context):
    sop = make_sop([
        SOPStep(id="a", action="no_op", next_step_id="b"),
        SOPStep(id="b", action="no_op"),
    ])
    engine = SOPEngine(executor=ScriptedExecutor())

    state = await _run(engine, definition, sop, context)

    assert len(state.evidence_refs) >= 2
    sources = {e.source for e in state.evidence_refs}
    assert ValidatorType.LEGACY_SUCCESS.value in sources
    for ref in state.evidence_refs:
        assert ref.timestamp is not None
        assert ref.type


async def test_step_evidence_includes_validator_verdict(definition, context):
    sop = make_sop([_schema_step("s1", ["wave_id"])])
    engine = SOPEngine(executor=ScriptedExecutor(default_output={"wave_id": "w17"}))

    state = await _run(engine, definition, sop, context)

    kinds = {e.type for e in state.step_results["s1"].evidence}
    assert "validator_result" in kinds


# ── Timeout ───────────────────────────────────────────────────────────────────

async def test_step_timeout_produces_timed_out_result(definition, context):
    import asyncio

    class SlowExecutor:
        RUNTIME_NAME = "slow"

        async def execute_step(self, **kwargs):
            await asyncio.sleep(1.0)
            raise AssertionError("should have been cancelled")

    sop = make_sop([SOPStep(id="s1", action="no_op", timeout_seconds=0.01)])
    engine = SOPEngine(executor=SlowExecutor())

    state = await _run(engine, definition, sop, context)

    assert state.status is ProcedureStatus.FAILED
    result = state.step_results["s1"]
    assert result.status is StepStatus.TIMED_OUT
    assert result.escalation_reason is EscalationReasonCode.TIMEOUT


async def test_executor_exception_is_contained(definition, context):
    class BoomExecutor:
        RUNTIME_NAME = "boom"

        async def execute_step(self, **kwargs):
            raise RuntimeError("executor exploded")

    sop = make_sop([SOPStep(id="s1", action="no_op")])
    engine = SOPEngine(executor=BoomExecutor())

    state = await _run(engine, definition, sop, context)

    assert state.status is ProcedureStatus.FAILED
    assert state.step_results["s1"].escalation_reason is EscalationReasonCode.MODEL_FAILURE


# ── Runaway protection ────────────────────────────────────────────────────────

async def test_max_transitions_guard_escalates(definition, context):
    """on_failure_step_id can form a loop that static validation does not catch."""
    sop = make_sop([
        SOPStep(id="a", action="no_op", on_failure_step_id="b"),
        SOPStep(id="b", action="no_op", on_failure_step_id="a"),
    ])
    executor = ScriptedExecutor(default_status=StepStatus.FAILED)
    engine = SOPEngine(executor=executor, max_transitions=10)

    state = await _run(engine, definition, sop, context)

    assert state.status is ProcedureStatus.ESCALATED
    assert len(executor.calls) <= 10


async def test_on_failure_branch_is_honoured(definition, context):
    sop = make_sop([
        _schema_step("a", ["impossible"], on_failure_step_id="recover"),
        SOPStep(id="recover", action="no_op"),
    ])
    executor = ScriptedExecutor(default_output={})
    engine = SOPEngine(executor=executor)

    state = await _run(engine, definition, sop, context)

    assert state.status is ProcedureStatus.COMPLETED
    assert executor.step_ids == ["a", "recover"]
