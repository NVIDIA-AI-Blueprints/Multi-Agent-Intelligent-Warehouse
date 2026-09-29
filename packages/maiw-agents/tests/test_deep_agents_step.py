# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Deep Agents one-step-at-a-time control.

What must be true after the V2 refactor:
  - the model is shown one step, never the whole SOP
  - the model cannot choose the next step
  - the reply becomes a typed StepResult
  - the model's "completed" claim is a claim, and the validator decides
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from maiw_agents.contracts.procedure_state import ProcedureStatus
from maiw_agents.contracts.sop import SOPStep
from maiw_agents.contracts.sop_v2 import StepCompletionSpec, ValidatorType
from maiw_agents.contracts.step_result import StepResult, StepStatus
from maiw_agents.runtime.deep_agents_runtime import (
    _build_step_system_prompt,
    _extract_json_object,
    _parse_step_response,
)
from maiw_agents.sop_engine import SOPEngine, SOPStepExecutor

from conftest import make_procedure_state, make_sop


class _Msg:
    """Minimal stand-in for a LangChain message."""

    def __init__(self, content: str) -> None:
        self.content = content


def _parse(text: str, step: SOPStep) -> StepResult:
    return _parse_step_response(
        messages=[_Msg(text)],
        step=step,
        attempt=1,
        started_at=datetime.now(timezone.utc),
        trace_id="trace-1",
    )


@pytest.fixture
def full_sop():
    return make_sop([
        SOPStep(id="a", action="no_op", next_step_id="b", description="first"),
        SOPStep(id="b", action="no_op", next_step_id="c", description="second"),
        SOPStep(id="c", action="no_op", description="third"),
    ])


# ── The prompt shows one step ─────────────────────────────────────────────────

def test_step_prompt_names_only_the_current_step(definition, full_sop, context):
    prompt = _build_step_system_prompt(definition, full_sop, full_sop.steps[0], context)

    assert "CURRENT STEP: a" in prompt
    assert "second" not in prompt, "the prompt must not reveal later steps"
    assert "third" not in prompt


def test_step_prompt_forbids_choosing_the_next_step(definition, full_sop, context):
    prompt = _build_step_system_prompt(definition, full_sop, full_sop.steps[0], context)
    assert "Do not decide the next step" in prompt
    assert "SOP\nEngine decides" in prompt or "Engine decides" in prompt


def test_step_prompt_carries_the_governance_hard_rule(definition, full_sop, context):
    prompt = _build_step_system_prompt(definition, full_sop, full_sop.steps[0], context)
    assert "GOVERNANCE HARD RULE" in prompt
    assert "may NOT execute warehouse writes" in prompt
    assert "WAITING_FOR_GOVERNANCE" in prompt


def test_step_prompt_includes_v2_step_metadata(definition, full_sop, context):
    step = SOPStep(
        id="obs", action="no_op",
        objective="prove the write landed",
        required_inputs=["wave_id"],
        expected_output={"wave_id": "string"},
        evidence_requirements=["state_snapshot"],
    )
    prompt = _build_step_system_prompt(definition, full_sop, step, context)

    assert "STEP OBJECTIVE: prove the write landed" in prompt
    assert "REQUIRED INPUTS: wave_id" in prompt
    assert "EXPECTED OUTPUT:" in prompt
    assert "EVIDENCE REQUIRED: state_snapshot" in prompt


def test_step_prompt_requests_structured_json(definition, full_sop, context):
    prompt = _build_step_system_prompt(definition, full_sop, full_sop.steps[0], context)
    assert '"step_id": "a"' in prompt
    assert "OUTPUT FORMAT" in prompt


# ── JSON extraction ───────────────────────────────────────────────────────────

def test_extract_json_handles_nested_objects():
    text = 'blah {"status": "completed", "output": {"a": {"b": 1}}} trailing'
    parsed = _extract_json_object(text, must_contain=("status",))
    assert parsed["output"]["a"]["b"] == 1


def test_extract_json_skips_non_matching_objects():
    text = '{"unrelated": 1} then {"status": "completed", "output": {}}'
    parsed = _extract_json_object(text, must_contain=("status",))
    assert parsed["status"] == "completed"


def test_extract_json_handles_braces_inside_strings():
    text = '{"status": "completed", "output": {"note": "a } brace"}}'
    parsed = _extract_json_object(text, must_contain=("status",))
    assert parsed["output"]["note"] == "a } brace"


def test_extract_json_returns_none_when_absent():
    assert _extract_json_object("no json here", must_contain=("status",)) is None


# ── Response parsing ──────────────────────────────────────────────────────────

def test_parse_structured_completed_response():
    step = SOPStep(id="a", action="no_op")
    text = json.dumps({
        "step_id": "a", "status": "completed",
        "output": {"wave_id": "w17", "at_risk_count": 3},
    })

    result = _parse(text, step)

    assert isinstance(result, StepResult)
    assert result.step_id == "a"
    assert result.runtime == "deep_agents"
    assert result.output["wave_id"] == "w17"


def test_parse_waiting_for_governance_response():
    step = SOPStep(id="submit", action="emit_recommended_action")
    text = json.dumps({
        "step_id": "submit", "status": "waiting_for_governance",
        "output": {}, "recommendation": {"domain": "labor", "action": "reallocate"},
    })

    result = _parse(text, step)

    assert result.status is StepStatus.WAITING_FOR_GOVERNANCE
    assert result.output["recommendation"]["domain"] == "labor"


def test_parse_failed_response():
    step = SOPStep(id="a", action="no_op")
    text = json.dumps({"step_id": "a", "status": "failed", "output": {}, "error": "no data"})

    result = _parse(text, step)

    assert result.status is StepStatus.FAILED
    assert result.error == "no data"


def test_parse_legacy_text_protocol():
    """Phase 19A's RECOMMENDATION/STOP text form must still be understood."""
    step = SOPStep(id="submit", action="emit_recommended_action")
    text = (
        "Analysis complete.\n"
        'RECOMMENDATION: {"domain": "labor", "action": "reallocate_workers"}\n'
        "STOP: WAITING_FOR_GOVERNANCE"
    )

    result = _parse(text, step)

    assert result.status is StepStatus.WAITING_FOR_GOVERNANCE
    assert result.output["recommendation"]["action"] == "reallocate_workers"


def test_parse_drops_chain_of_thought():
    """A model that volunteers its reasoning must not get it into the record."""
    step = SOPStep(id="a", action="no_op")
    text = json.dumps({
        "step_id": "a", "status": "completed",
        "output": {"wave_id": "w17"},
        "chain_of_thought": "first I considered...",
        "scratchpad": "notes",
    })

    result = _parse(text, step)

    assert "chain_of_thought" not in result.output
    assert "scratchpad" not in result.output
    assert result.output["wave_id"] == "w17"


def test_parse_records_model_claim_as_evidence_only():
    step = SOPStep(id="a", action="no_op")
    text = json.dumps({"step_id": "a", "status": "completed", "output": {}})

    result = _parse(text, step)

    assert result.evidence[0].type == "model_response"
    assert result.evidence[0].metadata["model_claimed_status"] == "completed"


# ── The model's claim is not completion ───────────────────────────────────────

async def test_model_claiming_completed_does_not_satisfy_a_schema_step(
    definition, context
):
    """The decisive test: the model says done, the validator says otherwise."""
    step = SOPStep(
        id="a", action="no_op",
        completion=StepCompletionSpec(
            validator_type=ValidatorType.SCHEMA, schema_fields=["required_proof"]
        ),
    )
    claimed = _parse(
        json.dumps({"step_id": "a", "status": "completed", "output": {"unrelated": 1}}),
        step,
    )
    assert claimed.status is StepStatus.COMPLETED  # the claim

    class _Executor:
        RUNTIME_NAME = "deep_agents"

        async def execute_step(self, **kwargs):
            return claimed

    engine = SOPEngine(executor=_Executor())
    state = await engine.run_procedure(
        definition=definition, sop=make_sop([step]),
        agent_task_id="t", context=context,
    )

    assert state.status is ProcedureStatus.FAILED
    assert state.step_results["a"].status is StepStatus.FAILED


async def test_model_cannot_skip_ahead(definition, context, full_sop):
    """
    Even if the model names a different step, the engine controls sequencing —
    the executor is asked for step ids in the SOP's order.
    """
    asked: list[str] = []

    class _Executor:
        RUNTIME_NAME = "deep_agents"

        async def execute_step(self, *, step, attempt, **kwargs):
            asked.append(step.id)
            # Model tries to claim it finished a later step.
            return _parse(
                json.dumps({"step_id": "c", "status": "completed", "output": {}}),
                step,
            ).model_copy(update={"step_id": step.id})

    engine = SOPEngine(executor=_Executor())
    state = await engine.run_procedure(
        definition=definition, sop=full_sop, agent_task_id="t", context=context
    )

    assert asked == ["a", "b", "c"], "engine must drive the order, not the model"
    assert state.completed_step_ids == ["a", "b", "c"]


# ── Protocol conformance ──────────────────────────────────────────────────────

def test_deep_agents_runtime_implements_sop_step_executor():
    from maiw_agents.runtime.deep_agents_runtime import DeepAgentsRuntime

    assert isinstance(DeepAgentsRuntime(), SOPStepExecutor)


def test_whole_sop_prompt_builder_is_gone():
    """The full-SOP system prompt is what let the model skip steps — it must go."""
    import maiw_agents.runtime.deep_agents_runtime as mod

    assert not hasattr(mod, "_build_sop_system_prompt")
    assert hasattr(mod, "_build_step_system_prompt")
