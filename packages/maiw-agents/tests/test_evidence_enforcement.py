# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Evidence requirements as enforced completion preconditions.

The gap this closes: ``evidence_requirements`` was declared in every SOP and
checked by nothing. A step could claim it had re-read authoritative state while
producing no record that it ever did.

The rule under test throughout:

    Model prose cannot satisfy an evidence requirement. Only a structured
    EvidenceRef with a matching type, matching source, and the required fields
    will do.

Enforcement order is also under test — evidence is checked BEFORE the
completion validator, so a step that cannot show its work reports
EVIDENCE_MISSING rather than a misleading validation failure.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from conftest import (
    ScriptedExecutor,
    make_procedure_state,
    make_sop,
    make_step_result,
    now,
)
from maiw_agents.contracts.agent import AgentDefinition
from maiw_agents.contracts.procedure_state import ProcedureStatus
from maiw_agents.contracts.runtime import AgentExecutionContext
from maiw_agents.contracts.sop import SOPStep
from maiw_agents.contracts.sop_v2 import (
    EscalationReasonCode,
    EvidenceRequirement,
    RetryPolicy,
    StepCompletionSpec,
    ValidatorType,
)
from maiw_agents.contracts.step_result import EvidenceRef, StepStatus
from maiw_agents.sop_engine import SOPEngine
from maiw_agents.sop_engine.validators import (
    EvidenceRequirementsValidator,
    StepValidationContext,
)


def _definition() -> AgentDefinition:
    return AgentDefinition(
        agent_id="operations_coordination",
        version="1.0",
        objective="test",
        domain="operations",
        allowed_capabilities=[],
        allowed_subagents=[],
        output_contract="RecommendedAction",
    )


def _context() -> AgentExecutionContext:
    return AgentExecutionContext(
        warehouse_id="wh-test",
        trace_id="trace-evidence",
        bounded_context={"wave_id": "w1"},
    )


def _ref(
    *,
    type_: str = "state_snapshot",
    source: str = "authoritative_reread",
    metadata: dict | None = None,
    timestamp: datetime | None = None,
) -> EvidenceRef:
    return EvidenceRef(
        type=type_,
        source=source,
        reference_id="trace-evidence",
        timestamp=timestamp or now(),
        summary="observed",
        metadata=metadata or {},
    )


async def _check(step: SOPStep, result, procedure_state=None):
    validator = EvidenceRequirementsValidator()
    ctx = StepValidationContext(
        step=step,
        procedure_state=procedure_state or make_procedure_state(current_step_id=step.id),
        execution_context=_context(),
    )
    return await validator.validate(step, result, ctx)


# ── Contract shape ────────────────────────────────────────────────────────────

def test_evidence_requirement_defaults_are_conservative():
    req = EvidenceRequirement(evidence_type="state_snapshot")
    assert req.min_count == 1
    assert req.source is None
    assert req.required_fields == []
    assert req.max_age_seconds is None
    assert req.optional is False


def test_bare_string_requirements_remain_declarative_hints():
    """
    The two YAML forms mean different things, on purpose.

    Existing SOPs tag steps with strings naming evidence kinds no component
    emits. Retroactively enforcing those would fail every step rather than
    prove anything, so a string stays a hint and a mapping is the contract.
    """
    step = SOPStep(
        id="s", action="read_wave_status",
        evidence_requirements=["state_snapshot", "state_comparison"],
    )
    assert step.enforced_evidence() == []
    assert step.evidence_requirement_labels() == ["state_snapshot", "state_comparison"]


def test_structured_requirements_are_enforced_and_labelled():
    step = SOPStep(
        id="s", action="read_wave_status",
        evidence_requirements=[
            "a_hint",
            EvidenceRequirement(evidence_type="state_snapshot", source="authoritative_reread"),
        ],
    )
    enforced = step.enforced_evidence()
    assert len(enforced) == 1
    assert enforced[0].evidence_type == "state_snapshot"
    assert step.evidence_requirement_labels() == ["a_hint", "state_snapshot"]


def test_yaml_mapping_form_parses_into_the_contract():
    step = SOPStep.model_validate({
        "id": "verify",
        "action": "verify_inventory_reconciled",
        "evidence_requirements": [
            {
                "evidence_type": "state_snapshot",
                "source": "authoritative_reread",
                "required_fields": ["sku", "on_hand"],
                "max_age_seconds": 120,
            }
        ],
    })
    req = step.enforced_evidence()[0]
    assert req.source == "authoritative_reread"
    assert req.required_fields == ["sku", "on_hand"]
    assert req.max_age_seconds == 120


# ── Presence, type, source, fields ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_present_evidence_satisfies_the_requirement():
    step = SOPStep(
        id="s", action="read_wave_status",
        evidence_requirements=[EvidenceRequirement(evidence_type="state_snapshot")],
    )
    result = make_step_result("s")
    result = result.model_copy(update={"evidence": [_ref()]})

    verdict = await _check(step, result)
    assert verdict.valid is True


@pytest.mark.asyncio
async def test_absent_evidence_blocks_completion_with_a_structured_reason():
    step = SOPStep(
        id="s", action="read_wave_status",
        evidence_requirements=[EvidenceRequirement(evidence_type="state_snapshot")],
    )
    result = make_step_result("s")  # no evidence at all

    verdict = await _check(step, result)
    assert verdict.valid is False
    assert "state_snapshot" in verdict.reason
    assert verdict.metadata["unmet_evidence_requirements"]


@pytest.mark.asyncio
async def test_wrong_evidence_type_does_not_satisfy():
    step = SOPStep(
        id="s", action="read_wave_status",
        evidence_requirements=[EvidenceRequirement(evidence_type="state_snapshot")],
    )
    result = make_step_result("s").model_copy(
        update={"evidence": [_ref(type_="step_execution")]}
    )
    verdict = await _check(step, result)
    assert verdict.valid is False


@pytest.mark.asyncio
async def test_wrong_source_does_not_satisfy():
    step = SOPStep(
        id="s", action="read_wave_status",
        evidence_requirements=[
            EvidenceRequirement(
                evidence_type="state_snapshot", source="authoritative_reread"
            )
        ],
    )
    result = make_step_result("s").model_copy(
        update={"evidence": [_ref(source="model_assertion")]}
    )
    verdict = await _check(step, result)
    assert verdict.valid is False
    assert "authoritative_reread" in verdict.reason


@pytest.mark.asyncio
async def test_missing_required_fields_does_not_satisfy():
    step = SOPStep(
        id="s", action="read_wave_status",
        evidence_requirements=[
            EvidenceRequirement(
                evidence_type="state_snapshot", required_fields=["sku", "on_hand"]
            )
        ],
    )
    result = make_step_result("s").model_copy(
        update={"evidence": [_ref(metadata={"sku": "A1"})]}   # on_hand absent
    )
    verdict = await _check(step, result)
    assert verdict.valid is False


@pytest.mark.asyncio
async def test_min_count_requires_that_many_matches():
    step = SOPStep(
        id="s", action="read_wave_status",
        evidence_requirements=[
            EvidenceRequirement(evidence_type="state_snapshot", min_count=2)
        ],
    )
    one = make_step_result("s").model_copy(update={"evidence": [_ref()]})
    assert (await _check(step, one)).valid is False

    two = make_step_result("s").model_copy(update={"evidence": [_ref(), _ref()]})
    assert (await _check(step, two)).valid is True


@pytest.mark.asyncio
async def test_optional_requirements_never_block():
    step = SOPStep(
        id="s", action="read_wave_status",
        evidence_requirements=[
            EvidenceRequirement(evidence_type="nice_to_have", optional=True)
        ],
    )
    verdict = await _check(step, make_step_result("s"))
    assert verdict.valid is True


# ── Freshness ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stale_evidence_does_not_satisfy_a_freshness_bound():
    """
    Evidence captured before a write proves nothing about the state after it.
    """
    step = SOPStep(
        id="verify", action="verify_inventory_reconciled",
        evidence_requirements=[
            EvidenceRequirement(evidence_type="state_snapshot", max_age_seconds=60)
        ],
    )
    old = _ref(timestamp=datetime.now(timezone.utc) - timedelta(seconds=600))
    result = make_step_result("verify").model_copy(update={"evidence": [old]})

    verdict = await _check(step, result)
    assert verdict.valid is False


@pytest.mark.asyncio
async def test_fresh_evidence_satisfies_a_freshness_bound():
    step = SOPStep(
        id="verify", action="verify_inventory_reconciled",
        evidence_requirements=[
            EvidenceRequirement(evidence_type="state_snapshot", max_age_seconds=600)
        ],
    )
    result = make_step_result("verify").model_copy(update={"evidence": [_ref()]})
    assert (await _check(step, result)).valid is True


# ── Model prose cannot substitute for evidence ────────────────────────────────

@pytest.mark.asyncio
async def test_model_prose_in_output_cannot_satisfy_a_requirement():
    """
    THE rule. A confident sentence is not an observation.
    """
    step = SOPStep(
        id="verify", action="verify_inventory_reconciled",
        evidence_requirements=[
            EvidenceRequirement(
                evidence_type="state_snapshot", source="authoritative_reread"
            )
        ],
    )
    result = make_step_result(
        "verify",
        output={
            "state_snapshot": "I re-read inventory from the authoritative source "
                              "and confirmed the pick is now satisfiable.",
            "authoritative_reread": True,
            "evidence": "state_snapshot from authoritative_reread",
            "confidence": 0.99,
        },
    )
    # Every plausible way of asserting it in output — and still no evidence.
    verdict = await _check(step, result)
    assert verdict.valid is False
    assert "state_snapshot" in verdict.reason


@pytest.mark.asyncio
async def test_prose_cannot_complete_a_step_end_to_end():
    """The same rule, through the engine rather than the validator directly."""
    step = SOPStep(
        id="verify",
        action="verify_inventory_reconciled",
        completion=StepCompletionSpec(
            validator_type=ValidatorType.SCHEMA, schema_fields=["reconciled"]
        ),
        evidence_requirements=[
            EvidenceRequirement(
                evidence_type="state_snapshot", source="authoritative_reread"
            )
        ],
    )
    sop = make_sop([step])
    # The runtime returns a perfectly schema-valid output claiming success.
    executor = ScriptedExecutor(default_output={"reconciled": True})
    engine = SOPEngine(executor=executor)

    state = await engine.run_procedure(
        definition=_definition(), sop=sop, agent_task_id="t", context=_context()
    )

    assert state.status != ProcedureStatus.COMPLETED
    assert "verify" not in state.completed_step_ids
    assert state.step_results["verify"].escalation_reason is (
        EscalationReasonCode.EVIDENCE_MISSING
    )


@pytest.mark.asyncio
async def test_structured_evidence_completes_the_same_step():
    """Control for the test above: with real evidence, the step completes."""
    step = SOPStep(
        id="verify",
        action="verify_inventory_reconciled",
        completion=StepCompletionSpec(
            validator_type=ValidatorType.SCHEMA, schema_fields=["reconciled"]
        ),
        evidence_requirements=[
            EvidenceRequirement(
                evidence_type="state_snapshot", source="authoritative_reread"
            )
        ],
    )
    sop = make_sop([step])
    proving = make_step_result("verify", output={"reconciled": True}).model_copy(
        update={"evidence": [_ref()]}
    )
    engine = SOPEngine(executor=ScriptedExecutor(script={"verify": [proving]}))

    state = await engine.run_procedure(
        definition=_definition(), sop=sop, agent_task_id="t", context=_context()
    )
    assert state.status == ProcedureStatus.COMPLETED
    assert "verify" in state.completed_step_ids


# ── Enforcement ordering ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_evidence_is_checked_before_the_completion_validator():
    """
    A step failing both checks reports EVIDENCE_MISSING, not VALIDATION_FAILED.

    The two call for different operator responses: missing evidence means the
    procedure is not instrumented to prove what it claims, while a failed
    completion criterion means the world is not in the expected state.
    """
    step = SOPStep(
        id="verify",
        action="verify_inventory_reconciled",
        completion=StepCompletionSpec(
            validator_type=ValidatorType.SCHEMA, schema_fields=["definitely_absent"]
        ),
        evidence_requirements=[EvidenceRequirement(evidence_type="state_snapshot")],
    )
    sop = make_sop([step])
    engine = SOPEngine(executor=ScriptedExecutor())

    state = await engine.run_procedure(
        definition=_definition(), sop=sop, agent_task_id="t", context=_context()
    )
    result = state.step_results["verify"]
    assert result.escalation_reason is EscalationReasonCode.EVIDENCE_MISSING
    assert "missing required evidence" in result.validation_result.reason


@pytest.mark.asyncio
async def test_a_step_with_no_enforced_requirements_is_unaffected():
    """Backward compatibility: existing SOPs behave exactly as before."""
    step = SOPStep(
        id="s",
        action="read_wave_status",
        evidence_requirements=["state_snapshot"],   # hint form only
    )
    sop = make_sop([step])
    engine = SOPEngine(executor=ScriptedExecutor())
    state = await engine.run_procedure(
        definition=_definition(), sop=sop, agent_task_id="t", context=_context()
    )
    assert state.status == ProcedureStatus.COMPLETED


# ── Attempt correlation ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_evidence_from_a_failed_attempt_does_not_satisfy_the_next_attempt():
    """
    Attempt 1's evidence is not attempt 2's proof.

    If attempt 1 re-read state and the step still failed, attempt 2 must re-read
    again. Carrying the stale observation forward would let a retry "succeed"
    on an observation made before the condition it is meant to verify.
    """
    step = SOPStep(
        id="verify", action="verify_inventory_reconciled",
        evidence_requirements=[EvidenceRequirement(evidence_type="state_snapshot")],
    )

    # The procedure state carries attempt 1's evidence, correctly stamped.
    attempt_one_ref = _ref(metadata={"step_id": "verify", "attempt": 1})
    proc_state = make_procedure_state(
        current_step_id="verify",
        attempt_by_step={"verify": 1},
        evidence_refs=[attempt_one_ref],
    )

    # Attempt 2 produced nothing of its own.
    attempt_two = make_step_result("verify", attempt=2)

    verdict = await _check(step, attempt_two, procedure_state=proc_state)
    assert verdict.valid is False, "attempt 1 evidence must not satisfy attempt 2"

    # ...and attempt 1's own check, against the same state, does pass.
    attempt_one = make_step_result("verify", attempt=1)
    assert (await _check(step, attempt_one, procedure_state=proc_state)).valid is True


@pytest.mark.asyncio
async def test_evidence_from_another_step_does_not_satisfy_this_one():
    step = SOPStep(
        id="verify", action="verify_inventory_reconciled",
        evidence_requirements=[EvidenceRequirement(evidence_type="state_snapshot")],
    )
    other_step_ref = _ref(metadata={"step_id": "some_other_step", "attempt": 1})
    proc_state = make_procedure_state(
        current_step_id="verify", evidence_refs=[other_step_ref]
    )
    verdict = await _check(step, make_step_result("verify"), procedure_state=proc_state)
    assert verdict.valid is False


@pytest.mark.asyncio
async def test_retry_produces_fresh_evidence_and_then_completes():
    """
    End-to-end attempt correlation: attempt 1 has no evidence and fails,
    attempt 2 produces it and the step completes.
    """
    step = SOPStep(
        id="verify",
        action="verify_inventory_reconciled",
        evidence_requirements=[EvidenceRequirement(evidence_type="state_snapshot")],
        retry_policy=RetryPolicy(max_attempts=2, backoff_seconds=0.0),
    )
    sop = make_sop([step])
    executor = ScriptedExecutor(script={
        "verify": [
            make_step_result("verify"),                                    # attempt 1: nothing
            make_step_result("verify").model_copy(update={"evidence": [_ref()]}),  # attempt 2
        ],
    })
    engine = SOPEngine(executor=executor)
    state = await engine.run_procedure(
        definition=_definition(), sop=sop, agent_task_id="t", context=_context()
    )

    assert state.status == ProcedureStatus.COMPLETED
    assert state.attempt_by_step["verify"] == 2
    assert executor.calls == [("verify", 1), ("verify", 2)]


@pytest.mark.asyncio
async def test_evidence_refs_are_stamped_with_step_and_attempt():
    """Correlation only works if the engine stamps provenance. Verify it does."""
    step = SOPStep(id="s", action="read_wave_status")
    sop = make_sop([step])
    proving = make_step_result("s").model_copy(update={"evidence": [_ref()]})
    engine = SOPEngine(executor=ScriptedExecutor(script={"s": [proving]}))

    state = await engine.run_procedure(
        definition=_definition(), sop=sop, agent_task_id="t", context=_context()
    )
    stamped = [e for e in state.evidence_refs if e.type == "state_snapshot"]
    assert stamped
    assert all(e.metadata["step_id"] == "s" for e in stamped)
    assert all(e.metadata["attempt"] == 1 for e in stamped)


# ── Evidence never carries model internals ────────────────────────────────────

def test_evidence_ref_is_a_pointer_not_a_transcript():
    fields = set(EvidenceRef.model_fields)
    forbidden = {
        "chain_of_thought", "scratchpad", "hidden_reasoning", "raw_reasoning",
        "system_prompt", "messages", "transcript", "prompt",
    }
    assert not (fields & forbidden)
    # It carries a reference and a summary — deliberately not the content.
    assert {"type", "source", "reference_id", "summary"} <= fields
