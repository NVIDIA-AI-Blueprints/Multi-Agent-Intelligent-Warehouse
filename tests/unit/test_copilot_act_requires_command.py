# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Only a command selects and runs a pending recommendation (#258).

ACT used to mean "an action verb appears anywhere in the message". A question
("Should we reassign Maria?"), a report ("I didn't ask you to move it") or a
noun use ("Tell me about the dispatch") was therefore ACT. With one stored
recommendation ``_select_recommendation`` returned it ("single"); with several,
a keyword such as "workers" picked one ("capability_match"). The governed
action then went to the DecisionEngine, and an APPROVED outcome executes with
no human approval step. Now:

  * ``intent.is_directive`` is true only when a clause of a non-question
    sentence opens with a command verb, optionally after a lead-in ("ok",
    "yes", "please", "let's", "then", "I want you to").
  * ``intent.classify`` returns ACT only for a directive that is not a
    cancellation; anything else falls through to ANALYZE / ASK.
  * ``intent.is_cancellation`` also recognises past-tense, perfect and subject
    negations of an action ("I didn't ask you to move it", "nobody said to
    reassign anyone"), so they get the deterministic decline reply.
  * ``_select_recommendation`` returns ``(None, "not_a_command")`` for a
    non-directive message, and ``CopilotService.act`` answers it with
    CLARIFICATION_REQUIRED without reaching the orchestrator.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from maiw_api.copilot.intent import classify, is_cancellation, is_directive
from maiw_api.copilot.models import (
    CopilotIntent,
    MutationState,
    RecommendedActionResult,
)
from maiw_api.copilot.service import CopilotService, _select_recommendation
from maiw_api.routers import copilot as copilot_router

# Questions, reports, suggestions and noun uses that name an action without
# commanding it: never ACT, never select a recommendation.
NOT_A_COMMAND = [
    # questions (the #258 report)
    "Should we reassign Maria?",
    "Why would we reassign anyone?",
    "Why not move it?",
    "Can you move it?",
    "Could we reprioritize wave 17?",
    "What if we dispatch FL-02?",
    "Should we reassign the workers?",
    "Should I confirm?",
    "Before you proceed, why?",
    "Do it?",
    "Go ahead?",
    "Go ahead, OK?",  # a tag question asks; "Go ahead." commands
    "Reassign Maria?",
    # statements and suggestions
    "What if we dispatch FL-02",
    "Maybe we should move FL-01 later",
    "We could allocate more workers",
    "The recommendation says to reassign workers",
    "If we move it, wave 17 recovers",
    "I haven't approved that",
    "Did you execute it",
    # noun uses
    "Tell me about the dispatch",
    "Show me the move",
    "Explain why you would reassign Maria",
]

# Past-tense, perfect and subject negations of an action: cancellations.
REPORTED_NEGATIONS = [
    "I didn't ask you to move it",
    "I didn’t ask you to move it",
    "Nobody said to reassign anyone",
    "No one told you to dispatch FL-02",
    "We never agreed to move it",
    "I didn't say to proceed",
    "I haven't asked you to approve anything",
]

# Commands: must stay ACT.
COMMANDS = [
    "Do it.",
    "do it!",
    "Proceed",
    "Go ahead",
    "Do the first one.",
    "Do #1.",
    "Prepare that action.",
    "Confirm and proceed.",
    "Allocate labor to Wave 17",
    "Move 3 workers to Wave 17 now.",
    "Reassign Maria to wave 17",
    "OK, do it",
    "OK do it",
    "Okay. Do it.",
    "Yes, go ahead.",
    "Yes do it",
    "Let's reprioritize wave 17",
    "Let’s do it",
    "Please proceed",
    "Just do it",
    "Sounds good, do it.",
    "Great — do it.",
    "Great - do it",
    "If it's safe, move it",
    "I want you to reassign Maria",
    "You can go ahead",
    "Thanks, proceed with the allocation",
    "Do it. Why not?",
]


def _rec(**overrides) -> RecommendedActionResult:
    fields = dict(
        recommendation_id="turn0001-rec-00",
        domain="labor",
        capability="warehouse.labor.allocate",
        target="wave-017",
        objective="Allocate labor to Wave 17",
        rationale="Workers idle.",
        priority="HIGH",
        subtype=None,
        conversation_id="conv-001",
        turn_id="turn-analyze-001",
        trace_id="trace-analyze-001",
        snapshot_id="snap-001",
        focus_entity_id="wave-017",
    )
    fields.update(overrides)
    return RecommendedActionResult(**fields)


def _two_recs() -> list[RecommendedActionResult]:
    return [
        _rec(recommendation_id="r-labor"),
        _rec(
            recommendation_id="r-wave",
            domain="wave",
            capability="warehouse.wave.reprioritize",
            objective="Reprioritize Wave 17",
        ),
    ]


class TestClassifier:
    @pytest.mark.parametrize("message", NOT_A_COMMAND)
    def test_a_mention_is_not_act(self, message):
        assert not is_directive(message)
        assert classify(message) != CopilotIntent.ACT

    @pytest.mark.parametrize("message", REPORTED_NEGATIONS)
    def test_reported_negation_is_a_cancellation(self, message):
        assert is_cancellation(message)
        assert classify(message) != CopilotIntent.ACT

    @pytest.mark.parametrize("message", COMMANDS)
    def test_commands_stay_act(self, message):
        assert is_directive(message)
        assert not is_cancellation(message)
        assert classify(message) == CopilotIntent.ACT

    def test_how_should_question_is_analyze_not_act(self):
        assert classify("How should we reassign workers?") == CopilotIntent.ANALYZE

    def test_command_then_cancel_is_a_cancellation(self):
        message = "Move it. Actually, cancel that."
        assert is_directive(message)
        assert is_cancellation(message)
        assert classify(message) != CopilotIntent.ACT


class TestSelection:
    @pytest.mark.parametrize("message", NOT_A_COMMAND)
    def test_single_recommendation_is_not_selected_by_a_mention(self, message):
        rec, reason = _select_recommendation(message, [_rec()])
        assert rec is None
        assert reason == "not_a_command"

    @pytest.mark.parametrize(
        "message",
        [
            "Should we reassign the workers?",
            "Why would we reprioritize the wave?",
            "Should we do the first one?",
            "Tell me about the labor allocation",
        ],
    )
    def test_keyword_or_index_in_a_mention_selects_nothing(self, message):
        # Before #258 these resolved via "capability_match" / "explicit_index".
        rec, reason = _select_recommendation(message, _two_recs())
        assert rec is None
        assert reason == "not_a_command"

    @pytest.mark.parametrize("message", COMMANDS)
    def test_single_recommendation_is_selected_by_a_command(self, message):
        rec, reason = _select_recommendation(message, [_rec()])
        assert rec is not None
        assert reason == "single"

    def test_commands_still_resolve_among_several(self):
        recs = _two_recs()
        assert _select_recommendation("Do the second one.", recs) == (
            recs[1],
            "explicit_index",
        )
        assert _select_recommendation("Reprioritize the wave.", recs) == (
            recs[1],
            "capability_match",
        )


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
    conv = svc.store.get_or_create(None, "DC-47", "labor-constraint-wave-risk")
    conv.last_recommendations = [_rec(conversation_id=conv.conversation_id)]
    return svc, orchestrator, conv


class TestServiceAct:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("message", NOT_A_COMMAND)
    async def test_act_with_a_mention_never_reaches_the_orchestrator(self, message):
        svc, orchestrator, conv = _service_with_one_recommendation()

        result, turn = await svc.act(
            message=message,
            conversation_id=conv.conversation_id,
            warehouse_id="DC-47",
            scenario_name="labor-constraint-wave-risk",
        )

        assert orchestrator.govern.call_count == 0
        assert result.decision_outcome == "CLARIFICATION_REQUIRED"
        assert result.degraded is False
        assert result.mutation_state == MutationState.NOT_ATTEMPTED
        assert result.proposal_id is None
        assert result.pending_approval_id is None
        assert "not prepared or run any action" in result.message
        assert turn.intent == CopilotIntent.ACT
        assert len(conv.last_recommendations) == 1

    @pytest.mark.asyncio
    async def test_act_with_a_command_reaches_the_orchestrator(self):
        svc, orchestrator, conv = _service_with_one_recommendation()

        with patch("maiw_api.copilot.service.WarehouseStateSnapshot") as snapshot:
            snapshot.seal.return_value = SimpleNamespace(
                snapshot_id="snap-002", warehouse_id="DC-47"
            )
            await svc.act(
                message="OK, do it",
                conversation_id=conv.conversation_id,
                warehouse_id="DC-47",
                scenario_name="labor-constraint-wave-risk",
            )

        assert orchestrator.govern.call_count == 1
        request = orchestrator.govern.call_args.kwargs["request"]
        assert request.recommendation_id == "turn0001-rec-00"


# ── HTTP: POST /api/v1/copilot/turn ───────────────────────────────────────────


def _client_and_service():
    svc, orchestrator, conv = _service_with_one_recommendation()
    svc.act = AsyncMock(side_effect=AssertionError("act() must not be called"))
    svc.decline_action = AsyncMock(
        side_effect=AssertionError("decline_action() must not be called")
    )
    app = FastAPI()
    app.include_router(copilot_router.router)
    app.state.runtime = SimpleNamespace(copilot_service=svc)
    return TestClient(app), svc, orchestrator, conv


@pytest.mark.parametrize(
    "message",
    [
        "Should we reassign Maria?",
        "Why not move it?",
        "Tell me about the dispatch",
        "How should we reassign workers?",
    ],
)
def test_http_turn_with_a_mention_is_answered_without_act(message):
    client, svc, orchestrator, conv = _client_and_service()
    # Stand-ins for the LLM-backed paths: record the call, return a 500 so the
    # test only depends on which path the router chose.
    svc.ask = AsyncMock(side_effect=RuntimeError("ask"))
    svc.analyze = AsyncMock(side_effect=RuntimeError("analyze"))

    response = client.post(
        "/api/v1/copilot/turn",
        json={
            "message": message,
            "conversation_id": conv.conversation_id,
            "warehouse_id": "DC-47",
            "scenario_name": "labor-constraint-wave-risk",
        },
    )

    assert response.status_code == 500
    assert svc.ask.call_count + svc.analyze.call_count == 1
    assert svc.act.call_count == 0
    assert svc.decline_action.call_count == 0
    assert orchestrator.govern.call_count == 0
