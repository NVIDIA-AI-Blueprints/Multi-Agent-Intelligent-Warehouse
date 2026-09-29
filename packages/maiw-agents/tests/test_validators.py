# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""The four implemented step completion validators and the validator registry."""

from __future__ import annotations

import pytest

from maiw_agents.contracts.sop import SOPStep
from maiw_agents.contracts.sop_v2 import StepCompletionSpec, ValidatorType
from maiw_agents.contracts.step_result import StepStatus
from maiw_agents.sop_engine.validators import (
    DEFAULT_VALIDATOR_REGISTRY,
    CapabilityResultValidator,
    LegacySuccessValidator,
    SchemaValidator,
    StatePredicateValidator,
    StepValidationContext,
    ValidatorRegistry,
    register_predicate,
    unregister_predicate,
)

from conftest import make_procedure_state, make_step_result


def _ctx(step: SOPStep, context, snapshot=None) -> StepValidationContext:
    return StepValidationContext(
        step=step,
        procedure_state=make_procedure_state(current_step_id=step.id),
        execution_context=context,
        warehouse_state_snapshot=snapshot,
    )


# ── SchemaValidator ───────────────────────────────────────────────────────────

async def test_schema_validator_passes_when_all_fields_present(context):
    step = SOPStep(
        id="s1", action="no_op",
        completion=StepCompletionSpec(
            validator_type=ValidatorType.SCHEMA,
            schema_fields=["wave_id", "at_risk_count"],
        ),
    )
    result = make_step_result("s1", output={"wave_id": "w17", "at_risk_count": 3})

    verdict = await SchemaValidator().validate(step, result, _ctx(step, context))

    assert verdict.valid is True
    assert verdict.validator_type is ValidatorType.SCHEMA
    assert verdict.evidence, "a passing validator must still emit evidence"


async def test_schema_validator_fails_on_missing_fields(context):
    step = SOPStep(
        id="s1", action="no_op",
        completion=StepCompletionSpec(
            validator_type=ValidatorType.SCHEMA,
            schema_fields=["wave_id", "at_risk_count"],
        ),
    )
    result = make_step_result("s1", output={"wave_id": "w17"})

    verdict = await SchemaValidator().validate(step, result, _ctx(step, context))

    assert verdict.valid is False
    assert "at_risk_count" in verdict.reason
    assert verdict.retryable is True
    assert verdict.metadata["missing_fields"] == ["at_risk_count"]


async def test_schema_validator_passes_with_no_completion_spec(context):
    """No declared schema means nothing to prove — legacy pass."""
    step = SOPStep(id="s1", action="no_op")
    result = make_step_result("s1")

    verdict = await SchemaValidator().validate(step, result, _ctx(step, context))
    assert verdict.valid is True


# ── StatePredicateValidator ───────────────────────────────────────────────────

@pytest.fixture
def registered_predicate():
    def wave_risk_reduced(state, args):
        return state.get("at_risk_count", 99) <= args.get("max_at_risk", 0)

    register_predicate("t_wave_risk_reduced", wave_risk_reduced)
    yield "t_wave_risk_reduced"
    unregister_predicate("t_wave_risk_reduced")


async def test_state_predicate_passes_when_predicate_holds(context, registered_predicate):
    step = SOPStep(
        id="observe", action="evaluate_post_execution_state",
        completion=StepCompletionSpec(
            validator_type=ValidatorType.STATE_PREDICATE,
            predicate_name=registered_predicate,
            predicate_args={"max_at_risk": 0},
        ),
    )
    result = make_step_result("observe")

    verdict = await StatePredicateValidator().validate(
        step, result, _ctx(step, context, snapshot={"at_risk_count": 0})
    )

    assert verdict.valid is True
    assert verdict.evidence[0].metadata["predicate_name"] == registered_predicate


async def test_state_predicate_fails_when_predicate_does_not_hold(context, registered_predicate):
    step = SOPStep(
        id="observe", action="evaluate_post_execution_state",
        completion=StepCompletionSpec(
            validator_type=ValidatorType.STATE_PREDICATE,
            predicate_name=registered_predicate,
            predicate_args={"max_at_risk": 0},
        ),
    )
    result = make_step_result("observe")

    verdict = await StatePredicateValidator().validate(
        step, result, _ctx(step, context, snapshot={"at_risk_count": 3})
    )

    assert verdict.valid is False
    assert "did not hold" in verdict.reason


async def test_state_predicate_unregistered_is_not_retryable(context):
    """Re-running a step cannot make an unregistered predicate appear."""
    step = SOPStep(
        id="observe", action="evaluate_post_execution_state",
        completion=StepCompletionSpec(
            validator_type=ValidatorType.STATE_PREDICATE,
            predicate_name="never_registered",
        ),
    )
    result = make_step_result("observe")

    verdict = await StatePredicateValidator().validate(step, result, _ctx(step, context))

    assert verdict.valid is False
    assert verdict.retryable is False
    assert "unknown predicate" in verdict.reason


async def test_state_predicate_raising_predicate_is_contained(context):
    def boom(state, args):
        raise RuntimeError("predicate exploded")

    register_predicate("t_boom", boom)
    try:
        step = SOPStep(
            id="observe", action="no_op",
            completion=StepCompletionSpec(
                validator_type=ValidatorType.STATE_PREDICATE,
                predicate_name="t_boom",
            ),
        )
        verdict = await StatePredicateValidator().validate(
            step, make_step_result("observe"), _ctx(step, context)
        )
        assert verdict.valid is False
        assert verdict.retryable is False
        assert "raised" in verdict.reason
    finally:
        unregister_predicate("t_boom")


# ── CapabilityResultValidator ─────────────────────────────────────────────────

async def test_capability_result_present(context):
    step = SOPStep(
        id="s1", action="no_op",
        completion=StepCompletionSpec(
            validator_type=ValidatorType.CAPABILITY_RESULT,
            required_capability_result="warehouse.labor.capacity",
        ),
    )
    result = make_step_result("s1", output={"warehouse.labor.capacity": {"idle": 4}})

    verdict = await CapabilityResultValidator().validate(step, result, _ctx(step, context))
    assert verdict.valid is True


async def test_capability_result_missing(context):
    step = SOPStep(
        id="s1", action="no_op",
        completion=StepCompletionSpec(
            validator_type=ValidatorType.CAPABILITY_RESULT,
            required_capability_result="warehouse.labor.capacity",
        ),
    )
    result = make_step_result("s1", output={})

    verdict = await CapabilityResultValidator().validate(step, result, _ctx(step, context))
    assert verdict.valid is False
    assert "not found in output" in verdict.reason


async def test_capability_result_missing_required_fields(context):
    step = SOPStep(
        id="s1", action="no_op",
        completion=StepCompletionSpec(
            validator_type=ValidatorType.CAPABILITY_RESULT,
            required_capability_result="warehouse.labor.capacity",
            required_result_fields=["idle", "assigned"],
        ),
    )
    result = make_step_result("s1", output={"warehouse.labor.capacity": {"idle": 4}})

    verdict = await CapabilityResultValidator().validate(step, result, _ctx(step, context))
    assert verdict.valid is False
    assert "assigned" in verdict.reason


async def test_capability_result_not_a_mapping(context):
    step = SOPStep(
        id="s1", action="no_op",
        completion=StepCompletionSpec(
            validator_type=ValidatorType.CAPABILITY_RESULT,
            required_capability_result="warehouse.labor.capacity",
            required_result_fields=["idle"],
        ),
    )
    result = make_step_result("s1", output={"warehouse.labor.capacity": "ok"})

    verdict = await CapabilityResultValidator().validate(step, result, _ctx(step, context))
    assert verdict.valid is False
    assert "not a dict" in verdict.reason


# ── LegacySuccessValidator ────────────────────────────────────────────────────

async def test_legacy_success_valid_when_runtime_returned(context):
    step = SOPStep(id="s1", action="no_op")
    result = make_step_result("s1", status=StepStatus.COMPLETED)

    verdict = await LegacySuccessValidator().validate(step, result, _ctx(step, context))
    assert verdict.valid is True
    assert verdict.validator_type is ValidatorType.LEGACY_SUCCESS


@pytest.mark.parametrize(
    "status", [StepStatus.FAILED, StepStatus.TIMED_OUT, StepStatus.ESCALATED]
)
async def test_legacy_success_invalid_when_runtime_failed(context, status):
    step = SOPStep(id="s1", action="no_op")
    result = make_step_result("s1", status=status)

    verdict = await LegacySuccessValidator().validate(step, result, _ctx(step, context))
    assert verdict.valid is False
    assert verdict.retryable is True


# ── ValidatorRegistry ─────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "vtype,expected",
    [
        (ValidatorType.SCHEMA, SchemaValidator),
        (ValidatorType.STATE_PREDICATE, StatePredicateValidator),
        (ValidatorType.CAPABILITY_RESULT, CapabilityResultValidator),
        (ValidatorType.LEGACY_SUCCESS, LegacySuccessValidator),
    ],
)
def test_registry_get_by_type(vtype, expected):
    assert isinstance(DEFAULT_VALIDATOR_REGISTRY.get(vtype), expected)


def test_registry_step_without_completion_gets_legacy():
    step = SOPStep(id="s1", action="no_op")
    assert isinstance(
        DEFAULT_VALIDATOR_REGISTRY.get_for_step(step), LegacySuccessValidator
    )


def test_registry_step_with_completion_gets_declared_validator():
    step = SOPStep(
        id="s1", action="no_op",
        completion=StepCompletionSpec(
            validator_type=ValidatorType.SCHEMA, schema_fields=["x"]
        ),
    )
    assert isinstance(DEFAULT_VALIDATOR_REGISTRY.get_for_step(step), SchemaValidator)


def test_registry_rejects_unsupported_validator_type():
    """An unsupported criterion must raise, never silently pass."""
    empty = ValidatorRegistry(validators={})
    with pytest.raises(ValueError, match="MODEL_JUDGE and COMPOSITE are not yet implemented"):
        empty.get(ValidatorType.SCHEMA)


def test_registry_supported_types_is_the_documented_four():
    assert DEFAULT_VALIDATOR_REGISTRY.supported_types() == {
        ValidatorType.SCHEMA,
        ValidatorType.STATE_PREDICATE,
        ValidatorType.CAPABILITY_RESULT,
        ValidatorType.LEGACY_SUCCESS,
    }
