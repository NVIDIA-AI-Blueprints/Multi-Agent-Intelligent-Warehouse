# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Cancellation and negated phrasings never select and run a pending recommendation (#221).

"cancel that", "don't dispatch anything" and "no, don't move it" contain bare
operation verbs, which used to classify as ACT; with exactly one stored
recommendation ``_select_recommendation`` then returned it without reading the
message. Now:

  * ``intent.is_cancellation`` recognises a message that opens with a cancel /
    negation marker, a negator that directly governs an operational verb, or a
    cancel verb whose object is the pending action -- and nothing broader, so a
    command with an unrelated negation ("... so we don't miss the cutoff")
    stays ACT.
  * ``intent.classify`` never returns ACT for a cancellation.
  * ``POST /api/v1/copilot/turn`` answers a cancellation with
    ``CopilotService.decline_action`` (deterministic, nothing selected or run),
    and ``CopilotService.act`` does the same if called directly.
  * The reply does not claim nothing is pending when an earlier turn left an
    approval in the queue.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from maiw_api.copilot.intent import classify, is_cancellation
from maiw_api.copilot.models import (
    CopilotIntent,
    MutationState,
    RecommendedActionResult,
)
from maiw_api.copilot.service import CopilotService, _select_recommendation
from maiw_api.routers import copilot as copilot_router

# Cancellations: must never be ACT and must never select a recommendation.
CANCEL_MESSAGES = [
    # leading cancel / negation marker
    "cancel that",
    "Cancel the move.",
    "cancelling the dispatch",
    "halt the dispatch",
    "stop",
    "abort",
    "never mind",
    "never-mind that",
    "Nevermind",
    "Not now, move it later",
    "Never move it",
    "No need to dispatch anything",
    "Mustn't reassign anyone",
    "no, don't move it",
    "No, hold off on the move",
    "No.",
    "Actually, don't.",
    "Wait",
    # negator directly governing an operational verb
    "don't dispatch anything",
    "Don’t dispatch anything",
    "dont move it",
    "Do not allocate any workers",
    "didn't I say not to move it?",
    "You shouldn't approve that",
    "There is no need to reassign anyone",
    # cancel verb taking the pending action as object, anywhere in the message
    "Move it. Actually, cancel that.",
    "Please stop the dispatch",
]

# Affirmative commands, including ones with an unrelated negation or the noun
# "stop": must stay ACT.
ACT_MESSAGES = [
    "Do it.",
    "Proceed.",
    "Go ahead",
    "Go ahead and apply the fix.",
    "Allocate the workers.",
    "Reprioritize the wave.",
    "Dispatch the forklift to zone B.",
    "Execute the recommendation please",
    "No problem, go ahead",
    "Reprioritize wave 17 so we don't miss the carrier cutoff",
    "Approve it, I don't see any risk",
    "Move FL-01 to the next stop",
    "Why not move it?",
]

# Questions that open with a marker but name no action: answered as ASK, not
# with the cancellation reply (they cannot run anything either way).
QUESTION_MESSAGES = [
    "Wait, why is FL-01 down?",
    "No, what about zone B?",
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

    @pytest.mark.parametrize("message", QUESTION_MESSAGES)
    def test_questions_opening_with_a_marker_stay_ask(self, message):
        assert not is_cancellation(message)
        assert classify(message) == CopilotIntent.ASK


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

    @pytest.mark.parametrize("message", ACT_MESSAGES)
    def test_affirmative_single_selection_is_unchanged(self, message):
        rec, reason = _select_recommendation(message, [_rec()])
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


def _assert_declined(result, orchestrator) -> None:
    assert orchestrator.govern.call_count == 0
    assert result.decision_outcome == "CLARIFICATION_REQUIRED"
    assert result.degraded is False
    assert result.mutation_state == MutationState.NOT_ATTEMPTED
    assert result.proposal_id is None
    assert result.pending_approval_id is None
    assert "not prepared or run any action" in result.message


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

        _assert_declined(result, orchestrator)
        assert turn.intent == CopilotIntent.ACT
        # The stored recommendation is left alone.
        assert len(conv.last_recommendations) == 1
        assert "recommendations remain available" in result.message

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "message",
        [
            "Reprioritize wave 17 so we don't miss the carrier cutoff",
            "Approve it, I don't see any risk",
        ],
    )
    async def test_act_with_unrelated_negation_still_reaches_the_orchestrator(
        self, message
    ):
        svc, orchestrator, conv = _service_with_one_recommendation()

        with patch("maiw_api.copilot.service.WarehouseStateSnapshot") as snapshot:
            snapshot.seal.return_value = SimpleNamespace(
                snapshot_id="snap-002", warehouse_id="DC-47"
            )
            await svc.act(
                message=message,
                conversation_id=conv.conversation_id,
                warehouse_id="DC-47",
                scenario_name="equipment-failure",
            )

        assert orchestrator.govern.call_count == 1
        request = orchestrator.govern.call_args.kwargs["request"]
        assert request.recommendation_id == "turn0001-rec-00"

    @pytest.mark.asyncio
    async def test_decline_does_not_claim_nothing_is_pending(self):
        svc, orchestrator, conv = _service_with_one_recommendation()
        earlier = SimpleNamespace(
            pending_approval_id="pend-123",
            capability="warehouse.equipment.release",
            target="FL-01",
        )
        conv.last_act_result = earlier

        result, _ = await svc.decline_action(
            message="cancel that",
            conversation_id=conv.conversation_id,
            warehouse_id="DC-47",
            scenario_name="equipment-failure",
        )

        _assert_declined(result, orchestrator)
        assert "pend-123" in result.message
        assert "does not withdraw it" in result.message
        assert "reject it" in result.message
        # The earlier ACT result stays the conversation's last ACT result, so a
        # later OBSERVE_OUTCOME turn still tracks the pending approval.
        assert conv.last_act_result is earlier


# ── HTTP: POST /api/v1/copilot/turn ───────────────────────────────────────────


def _client_and_service():
    svc, orchestrator, conv = _service_with_one_recommendation()
    # Neither the LLM-backed ASK/ANALYZE paths nor act() may handle a
    # cancellation.
    svc.ask = AsyncMock(side_effect=AssertionError("ask() must not be called"))
    svc.analyze = AsyncMock(side_effect=AssertionError("analyze() must not be called"))
    app = FastAPI()
    app.include_router(copilot_router.router)
    app.state.runtime = SimpleNamespace(copilot_service=svc)
    return TestClient(app), orchestrator, conv


@pytest.mark.parametrize(
    "message", ["cancel that", "don't dispatch anything", "Never move it"]
)
def test_http_turn_with_cancellation_gets_the_deterministic_reply(message):
    client, orchestrator, conv = _client_and_service()

    response = client.post(
        "/api/v1/copilot/turn",
        json={
            "message": message,
            "conversation_id": conv.conversation_id,
            "warehouse_id": "DC-47",
            "scenario_name": "equipment-failure",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["intent"] == CopilotIntent.ACT.value
    assert body["act_decision_outcome"] == "CLARIFICATION_REQUIRED"
    assert body["act_mutation_state"] == MutationState.NOT_ATTEMPTED.value
    assert body["act_proposal_id"] is None
    assert body["act_pending_approval_id"] is None
    assert "not prepared or run any action" in body["answer"]
    assert orchestrator.govern.call_count == 0
