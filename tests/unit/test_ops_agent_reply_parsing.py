# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
OperationsCoordinationAgent reads the model's assessment from any reply that
holds one, and says so when a reply holds none.

The agent accepted a reply only when it was pure JSON or JSON in a markdown
fence. Anything else (prose around the object, a reply cut off at the output
token limit, an empty reply) fell back to an empty assessment: no
recommendations, the summary "Assessment produced — see facts_observed.", and
nothing in the log. With hosted Nemotron 3 Ultra, the default for HIGH
reasoning since Super was retired (#159), the #309 counterfactual rerun got
zero recommendations in every MAIW cycle and could not be told apart from a
model that saw nothing to do.
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from maiw_agents.operations import OperationsCoordinationAgent
from maiw_agents.operations.agent import _first_json_object

# Reply from hosted nemotron-3-ultra-550b-a55b to the labor scenario on the
# DataPack world (2026-11-11), trimmed to one recommendation.
ULTRA_ASSESSMENT = {
    "summary": "DC-47 has 40 idle workers while 5 pending wave tasks remain unassigned.",
    "severity": "high",
    "domains_affected": ["labor", "wave"],
    "skills_consulted": ["warehouse.labor.allocate"],
    "recommendations": [
        {
            "domain": "labor",
            "capability": "warehouse.labor.allocate",
            "target": "5_unassigned_pending_tasks",
            "objective": "Assign idle workers to the 5 pending wave tasks",
            "rationale": "40 workers are idle while 5 pending tasks have no worker",
            "priority": "critical",
            "subtype": None,
        }
    ],
}
REPLY = json.dumps(ULTRA_ASSESSMENT, indent=2)


# ── _first_json_object ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        REPLY,
        f"```json\n{REPLY}\n```",
        f"```\n{REPLY}\n```",
        f"Here is my assessment of DC-47:\n\n{REPLY}\n\nLet me know if you need more.",
        f"Assessment follows.\n```json\n{REPLY}\n```",
        f'The task {{"task_id": "task-000012"}} has no worker.\n{REPLY}',
    ],
    ids=[
        "bare",
        "json-fence",
        "plain-fence",
        "prose",
        "prose-and-fence",
        "quoted-object",
    ],
)
def test_the_assessment_is_found_in_any_wrapping(text):
    assert _first_json_object(text) == ULTRA_ASSESSMENT


@pytest.mark.parametrize(
    "text",
    ["", "   ", "No JSON here.", REPLY[: len(REPLY) // 2], "```json\n{\n```"],
    ids=["empty", "blank", "prose-only", "truncated", "broken-fence"],
)
def test_no_object_is_none(text):
    assert _first_json_object(text) is None


def test_without_an_assessment_key_the_first_object_is_returned():
    assert _first_json_object('x {"a": 1} y {"b": 2}') == {"a": 1}


# ── analyze_disruption ────────────────────────────────────────────────────────


def _response(content, finish_reason="stop", usage=None):
    return SimpleNamespace(
        content=content,
        finish_reason=finish_reason,
        usage=usage or {},
        model_id="nvidia/nemotron-3-ultra-550b-a55b",
        latency_ms=8000.0,
        route_decision=SimpleNamespace(
            routing_rule="high_reasoning",
            routing_reason="reasoning=HIGH",
            requested_role="super",
            selected_role="ultra",
            fallback_from="super",
            fallback_reason="role=super is disabled",
        ),
    )


class _Gateway:
    def __init__(self, response):
        self._response = response

    async def generate(self, request):
        return self._response


def _snapshot():
    snapshot = MagicMock()
    snapshot.warehouse_id = "DC-47"
    snapshot.snapshot_id = "snap-001"
    snapshot.state = MagicMock()
    snapshot.state.equipment = None
    snapshot.state.labor = None
    snapshot.state.waves = None
    return snapshot


async def _analyze(response):
    agent = OperationsCoordinationAgent(model_gateway=_Gateway(response))
    return await agent.analyze_disruption(
        snapshot=_snapshot(), scenario_context="test", trace_id="trace-001"
    )


@pytest.mark.asyncio
async def test_prose_around_the_assessment_keeps_its_recommendations():
    assessment = await _analyze(_response(f"Here is my assessment:\n{REPLY}\nDone."))
    assert len(assessment.recommendations) == 1
    assert assessment.recommendations[0].capability == "warehouse.labor.allocate"
    assert assessment.summary == ULTRA_ASSESSMENT["summary"]


@pytest.mark.asyncio
async def test_a_reply_cut_off_at_the_token_limit_is_reported(caplog):
    usage = {
        "completion_tokens": 2000,
        "completion_tokens_details": {"reasoning_tokens": 1900},
    }
    with caplog.at_level(logging.WARNING, logger="maiw_agents.operations.agent"):
        assessment = await _analyze(
            _response(REPLY[:120], finish_reason="length", usage=usage)
        )
    assert assessment.recommendations == []
    assert "could not be read as an assessment" in assessment.summary
    assert "cut off at the output token limit" in assessment.summary
    assert "reasoning_tokens=1900" in assessment.summary
    assert "not a JSON assessment" in caplog.text
    assert "trace-001" in caplog.text


@pytest.mark.asyncio
async def test_an_empty_reply_is_reported(caplog):
    with caplog.at_level(logging.WARNING, logger="maiw_agents.operations.agent"):
        assessment = await _analyze(_response(""))
    assert assessment.recommendations == []
    assert "empty reply" in assessment.summary
    assert "not a JSON assessment" in caplog.text


@pytest.mark.asyncio
async def test_a_valid_reply_logs_nothing(caplog):
    with caplog.at_level(logging.WARNING, logger="maiw_agents.operations.agent"):
        assessment = await _analyze(_response(REPLY))
    assert len(assessment.recommendations) == 1
    assert "not a JSON assessment" not in caplog.text
