# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""SOPStep v2 fields, RetryPolicy, StepCompletionSpec and StepResult contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from maiw_agents.contracts.sop import SOPStep
from maiw_agents.contracts.sop_v2 import (
    EscalationReasonCode,
    RetryPolicy,
    StepCompletionSpec,
    ValidatorType,
)
from maiw_agents.contracts.step_result import StepResult, StepStatus

from conftest import make_step_result


# ── V2 fields are optional ────────────────────────────────────────────────────

def test_v2_fields_all_default_to_none():
    """A step declaring only v1 fields must construct with every v2 field None."""
    step = SOPStep(id="s1", action="no_op")

    assert step.objective is None
    assert step.required_inputs is None
    assert step.expected_output is None
    assert step.completion is None
    assert step.retry_policy is None
    assert step.timeout_seconds is None
    assert step.escalation_reason is None
    assert step.evidence_requirements is None


def test_v1_step_yaml_shape_still_loads():
    """The exact field set used by the v1 SOP YAML must still validate."""
    step = SOPStep.model_validate({
        "id": "establish_state",
        "action": "gather_operational_context",
        "description": "Assemble a fresh OperationalContextSnapshot.",
    })
    assert step.id == "establish_state"
    assert step.completion is None


def test_v2_step_accepts_full_completion_block():
    step = SOPStep.model_validate({
        "id": "observe",
        "action": "evaluate_post_execution_state",
        "objective": "Prove the write landed",
        "required_inputs": ["wave_id"],
        "expected_output": {"wave_id": "string"},
        "completion": {
            "validator_type": "state_predicate",
            "predicate_name": "wave_risk_reduced",
            "predicate_args": {"min_reduction": 1},
        },
        "retry_policy": {"max_attempts": 2, "backoff_seconds": 0.0},
        "timeout_seconds": 5.0,
        "escalation_reason": "state did not confirm",
        "evidence_requirements": ["state_snapshot"],
    })

    assert step.completion is not None
    assert step.completion.validator_type is ValidatorType.STATE_PREDICATE
    assert step.completion.predicate_name == "wave_risk_reduced"
    assert step.retry_policy is not None
    assert step.retry_policy.max_attempts == 2
    assert step.evidence_requirements == ["state_snapshot"]


# ── RetryPolicy ───────────────────────────────────────────────────────────────

def test_retry_policy_defaults():
    policy = RetryPolicy()
    assert policy.max_attempts == 3
    assert policy.backoff_seconds == 1.0
    assert policy.escalate_on_exhaustion is True
    assert "VALIDATION_FAILED" in policy.retry_on


def test_retry_policy_rejects_write_ambiguous():
    """Ambiguous writes must never be retried blindly."""
    with pytest.raises(ValidationError, match="authoritative reread"):
        RetryPolicy(retry_on=["VALIDATION_FAILED", "WRITE_AMBIGUOUS"])


def test_retry_policy_rejects_execution_indeterminate():
    with pytest.raises(ValidationError, match="authoritative reread"):
        RetryPolicy(retry_on=["EXECUTION_INDETERMINATE"])


def test_retry_policy_rejects_write_ambiguous_case_insensitively():
    with pytest.raises(ValidationError, match="authoritative reread"):
        RetryPolicy(retry_on=["write_ambiguous"])


@pytest.mark.parametrize("attempts", [0, 11])
def test_retry_policy_bounds_max_attempts(attempts):
    with pytest.raises(ValidationError):
        RetryPolicy(max_attempts=attempts)


def test_retry_policy_bounds_backoff():
    with pytest.raises(ValidationError):
        RetryPolicy(backoff_seconds=31.0)


# ── StepCompletionSpec ────────────────────────────────────────────────────────

def test_completion_spec_schema_type():
    spec = StepCompletionSpec(
        validator_type=ValidatorType.SCHEMA,
        schema_fields=["wave_id", "at_risk_count"],
    )
    assert spec.schema_fields == ["wave_id", "at_risk_count"]
    assert spec.predicate_name is None


def test_completion_spec_state_predicate_requires_name():
    with pytest.raises(ValidationError, match="requires predicate_name"):
        StepCompletionSpec(validator_type=ValidatorType.STATE_PREDICATE)


def test_completion_spec_capability_result_requires_capability():
    with pytest.raises(ValidationError, match="required_capability_result"):
        StepCompletionSpec(validator_type=ValidatorType.CAPABILITY_RESULT)


def test_completion_spec_legacy_success_needs_nothing():
    spec = StepCompletionSpec(validator_type=ValidatorType.LEGACY_SUCCESS)
    assert spec.validator_type is ValidatorType.LEGACY_SUCCESS


def test_validator_type_closed_set():
    """MODEL_JUDGE / HUMAN / COMPOSITE are deferred and must not exist yet."""
    values = {v.value for v in ValidatorType}
    assert values == {"schema", "state_predicate", "capability_result", "legacy_success"}


def test_escalation_reason_codes_are_typed():
    assert EscalationReasonCode.RETRY_BUDGET_EXHAUSTED.value == "retry_budget_exhausted"
    assert EscalationReasonCode.EXECUTION_INDETERMINATE.value == "execution_indeterminate"
    assert EscalationReasonCode.UNSUPPORTED_VALIDATOR.value == "unsupported_validator"


# ── StepResult ────────────────────────────────────────────────────────────────

def test_step_result_requires_runtime_and_step_id():
    result = make_step_result("s1")
    assert result.step_id == "s1"
    assert result.runtime == "test"
    assert result.status is StepStatus.COMPLETED
    assert result.attempt == 1


def test_step_result_rejects_chain_of_thought():
    with pytest.raises(ValidationError, match="chain-of-thought"):
        make_step_result("s1", output={"chain_of_thought": "first I thought..."})


def test_step_result_accepts_structured_output():
    result = make_step_result("s1", output={"wave_id": "wave-17", "at_risk_count": 3})
    assert result.output["wave_id"] == "wave-17"


def test_step_status_covers_full_lifecycle():
    values = {s.value for s in StepStatus}
    assert {
        "pending", "running", "validating", "completed", "retry",
        "escalated", "failed", "timed_out", "waiting_for_governance",
    } == values
