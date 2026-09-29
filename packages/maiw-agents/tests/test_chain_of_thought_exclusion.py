# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Chain-of-thought must never enter the operational record.

Design Section 24: evidence is structured references and bounded summaries, not
model transcripts. Violations fail at construction time so they cannot reach an
audit trail, a UI, or a persisted procedure state.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from maiw_agents.contracts.step_result import EvidenceRef, StepResult

from conftest import ScriptedExecutor, make_sop, make_step_result, now
from maiw_agents.contracts.sop import SOPStep
from maiw_agents.sop_engine import SOPEngine


BANNED = [
    "chain_of_thought",
    "scratchpad",
    "hidden_reasoning",
    "raw_reasoning",
    "system_prompt",
]


@pytest.mark.parametrize("field", BANNED)
def test_step_result_rejects_banned_output_field(field):
    with pytest.raises(ValidationError, match="chain-of-thought"):
        make_step_result("s1", output={field: "internal monologue"})


def test_step_result_rejects_banned_field_among_valid_ones():
    with pytest.raises(ValidationError, match="chain-of-thought"):
        make_step_result("s1", output={"wave_id": "w17", "scratchpad": "..."})


def test_step_result_reports_every_banned_field_found():
    with pytest.raises(ValidationError) as exc:
        make_step_result("s1", output={"scratchpad": "a", "chain_of_thought": "b"})
    message = str(exc.value)
    assert "scratchpad" in message and "chain_of_thought" in message


def test_step_result_allows_legitimate_structured_output():
    result = make_step_result("s1", output={
        "wave_id": "w17",
        "at_risk_count": 3,
        "recommendation": {"domain": "labor", "action": "reallocate"},
    })
    assert result.output["at_risk_count"] == 3


def test_banned_fields_are_rejected_on_model_copy_update():
    """Mutation paths must be guarded too, not just the constructor."""
    result = make_step_result("s1", output={"wave_id": "w17"})
    with pytest.raises(ValidationError, match="chain-of-thought"):
        StepResult.model_validate({
            **result.model_dump(),
            "output": {"chain_of_thought": "leaked"},
        })


# ── Evidence stores references, not reasoning ─────────────────────────────────

def test_evidence_ref_is_a_reference_not_a_transcript():
    fields = set(EvidenceRef.model_fields)
    assert fields == {
        "type", "source", "reference_id", "timestamp", "summary", "metadata"
    }
    for forbidden in ("text", "transcript", "messages", "reasoning", "content"):
        assert forbidden not in fields


def test_evidence_ref_requires_type_source_and_timestamp():
    with pytest.raises(ValidationError):
        EvidenceRef(source="x", timestamp=now())  # type missing


def test_evidence_ref_summary_is_optional_and_bounded_by_caller():
    ref = EvidenceRef(
        type="validator_result", source="schema",
        timestamp=now(), summary="schema check passed",
    )
    assert ref.summary == "schema check passed"


async def test_engine_evidence_contains_no_reasoning_keys(definition, context):
    sop = make_sop([
        SOPStep(id="a", action="no_op", next_step_id="b"),
        SOPStep(id="b", action="no_op"),
    ])
    engine = SOPEngine(executor=ScriptedExecutor(default_output={"wave_id": "w17"}))

    state = await engine.run_procedure(
        definition=definition, sop=sop, agent_task_id="task-1", context=context
    )

    assert state.evidence_refs
    for ref in state.evidence_refs:
        assert not (set(ref.metadata) & set(BANNED)), (
            f"evidence metadata leaked reasoning: {ref.metadata}"
        )


async def test_persisted_procedure_state_has_no_reasoning(definition, context):
    """Round-tripping the whole procedure must not surface banned keys anywhere."""
    sop = make_sop([SOPStep(id="a", action="no_op")])
    engine = SOPEngine(executor=ScriptedExecutor(default_output={"wave_id": "w17"}))

    state = await engine.run_procedure(
        definition=definition, sop=sop, agent_task_id="task-1", context=context
    )

    dumped = str(state.model_dump(mode="json"))
    for banned in BANNED:
        assert banned not in dumped
