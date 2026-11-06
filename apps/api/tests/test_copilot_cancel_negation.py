# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Cancellation and negated phrasings never select and run a pending recommendation.

"cancel that", "don't dispatch anything" and "no, don't move it" contain bare
operation verbs, which used to classify as ACT; with exactly one stored
recommendation ``_select_recommendation`` then returned it without reading the
message. Both layers now read the message:

  * ``intent.classify`` does not classify a cancel / negated message as ACT.
  * ``_select_recommendation`` (and so ``CopilotService.act``) selects nothing
    for such a message, even if ``act`` is called directly.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from maiw_api.copilot.intent import classify, is_cancellation
from maiw_api.copilot.models import (
    CopilotIntent,
    MutationState,
    RecommendedActionResult,
)
from maiw_api.copilot.service import CopilotService, _select_recommendation
from maiw_api.copilot.store import (
    InMemoryCopilotStore,
)  # noqa: F401  (service default store)

CANCEL_MESSAGES = [
    "cancel that",
    "Cancel the move.",
    "don't dispatch anything",
    "Don’t dispatch anything",
    "no, don't move it",
    "No, hold off on the move",
    "Do not allocate any workers",
    "never mind",
    "stop",
    "abort",
]

# Affirmative commands that must keep working.
ACT_MESSAGES = [
    "Do it.",
    "Proceed.",
    "Go ahead and apply the fix.",
    "Allocate the workers.",
    "Reprioritize the wave.",
    "Dispatch the forklift to zone B.",
    "Execute the recommendation please",
    "No problem, go ahead",
]


def _rec(**overrides) -> RecommendedActionResult:
    fields = dict(
        recommendation_id="turn0001-rec-00",
        domain="equipment",
        capability="warehouse.equipment.release",
        target="FL-01",
        objective="Release forklift FL-01",
        rationale="Idle.",
        priority="LOW",
        subtype=None,
        conversation_id="conv-001",
        turn_id="turn-analyze-001",
        trace_id="trace-analyze-001",
        snapshot_id="snap-001",
        focus_entity_id="FL-01",
    )
    fields.update(overrides)
    return RecommendedActionResult(**fields)


class TestClassifier:
    @pytest.mark.parametrize("message", CANCEL_MESSAGES)
    def test_cancel_and_negated_messages_are_not_act(self, message):
        assert is_cancellation(message)
        assert classify(message) != CopilotIntent.ACT

    @pytest.mark.parametrize("message", ACT_MESSAGES)
    def test_affirmative_commands_still_classify_as_act(self, message):
        assert not is_cancellation(message)
        assert classify(message) == CopilotIntent.ACT

    def test_cancel_that_falls_through_to_conversational_path(self):
        assert classify("cancel that") == CopilotIntent.ASK


class TestSelection:
    @pytest.mark.parametrize("message", CANCEL_MESSAGES)
    def test_single_recommendation_is_not_selected_by_a_cancel_message(self, message):
        rec, reason = _select_recommendation(message, [_rec()])
        assert rec is None
        assert reason == "cancelled"

    @pytest.mark.parametrize("message", CANCEL_MESSAGES)
    def test_multiple_recommendations_are_not_selected_by_a_cancel_message(
        self, message
    ):
        recs = [_rec(recommendation_id="r1"), _rec(recommendation_id="r2")]
        rec, reason = _select_recommendation(message, recs)
        assert rec is None
        assert reason == "cancelled"

    def test_affirmative_single_selection_is_unchanged(self):
        rec, reason = _select_recommendation("Do it.", [_rec()])
        assert rec is not None
        assert reason == "single"

    def test_no_recommendations_is_still_not_found(self):
        rec, reason = _select_recommendation("cancel that", [])
        assert rec is None
        assert reason == "not_found"


def _service_with_one_recommendation():
    provider = MagicMock()
    provider.get_state = AsyncMock(return_value=MagicMock())
    svc = CopilotService(
        operations_agent=MagicMock(),
        state_provider=provider,
        event_bus=None,
        graph=None,
    )
    orchestrator = AsyncMock()
    svc.set_orchestrator(orchestrator)
    conv = svc.store.get_or_create(None, "DC-47", "equipment-failure")
    conv.last_recommendations = [_rec(conversation_id=conv.conversation_id)]
    return svc, orchestrator, conv


class TestServiceAct:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("message", CANCEL_MESSAGES)
    async def test_act_with_cancel_message_never_reaches_the_orchestrator(
        self, message
    ):
        svc, orchestrator, conv = _service_with_one_recommendation()

        result, turn = await svc.act(
            message=message,
            conversation_id=conv.conversation_id,
            warehouse_id="DC-47",
            scenario_name="equipment-failure",
        )

        assert orchestrator.govern.call_count == 0
        assert result.decision_outcome == "CLARIFICATION_REQUIRED"
        assert result.degraded is False
        assert result.mutation_state == MutationState.NOT_ATTEMPTED
        assert result.proposal_id is None
        assert result.pending_approval_id is None
        assert "not prepared or run any action" in result.message
        # The stored recommendation is left alone.
        assert len(conv.last_recommendations) == 1
