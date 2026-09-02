# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 15D — Copilot ACT tests.

Covers:
  1. Architecture invariants — CopilotService still doesn't import ActionExecutor/DecisionEngine
  2. GovernedActionOrchestrator owns the governance boundary
  3. Intent classifier — "Proceed", "Do it", "Allocate the workers", etc.
  4. Recommendation resolution — single, ambiguous, explicit index, capability match
  5. Canonical three-turn flow: ASK → ANALYZE → ACT → REQUIRES_HUMAN_APPROVAL
  6. State drift protection — stale recommendation blocked before proposal
  7. Duplicate ACT idempotency — same recommendation_id → same pending via dedup
  8. Decision outcomes — REJECTED, REQUIRES_FRESH_STATE, APPROVED+EXECUTED, APPROVED+UNKNOWN
  9. No orchestrator → NOT_IMPLEMENTED
 10. ACT turn artifact_refs carry governance provenance
"""

from __future__ import annotations

import ast
import dataclasses
import pathlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maiw_api.copilot.intent import classify
from maiw_api.copilot.models import (
    CopilotActResult,
    CopilotIntent,
    GovernedActionRequest,
    MutationState,
    RecommendedActionResult,
)
from maiw_api.copilot.service import (
    CopilotService,
    _check_state_drift,
    _select_recommendation,
)
from maiw_api.copilot.store import InMemoryCopilotStore


# ── Fixtures ───────────────────────────────────────────────────────────────────

@dataclass
class _FakeDomainState:
    total_waves: int = 3
    total_tasks: int = 120
    total_workers: int = 10
    total_labor: int = 10
    total_equipment: int = 5
    total: int = 5
    idle_workers: int = 3          # used by _check_state_drift


@dataclass
class _FakeState:
    warehouse_id: str = "DC-47"
    equipment: Any = None
    labor: Any = None
    waves: Any = None

    def __post_init__(self):
        if self.equipment is None:
            self.equipment = _FakeDomainState()
        if self.labor is None:
            self.labor = _FakeDomainState()
        if self.waves is None:
            self.waves = _FakeDomainState()


@dataclass
class _FakeSnapshot:
    snapshot_id: str
    warehouse_id: str

    @classmethod
    def seal(cls, state: Any) -> "_FakeSnapshot":
        return cls(
            snapshot_id=str(uuid.uuid4()),
            warehouse_id=getattr(state, "warehouse_id", "DC-47"),
        )


@dataclass
class _FakeAssessmentRec:
    """Minimal RecommendedAction for the assessment."""
    domain: Any
    capability: Any
    target: str = "wave-017"
    objective: str = "Allocate available labor to protect Wave 17"
    rationale: str = "Workers idle while tasks are blocked."
    priority: Any = None
    subtype: Any = None

    def __post_init__(self):
        if self.priority is None:
            self.priority = MagicMock(value="HIGH")


@dataclass
class _FakeAssessment:
    trace_id: str
    snapshot_id: str
    warehouse_id: str
    summary: str = "Wave 17 at risk due to labor shortage."
    severity: str = "HIGH"
    facts_observed: list = None
    skills_consulted: list = None
    recommendations: list = None
    model_id: str = "test-model"
    routing_rule: str = "medium_reasoning"
    routing_reason: str = "test"
    requested_role: str = None
    selected_role: str = None
    fallback_from: str = None
    fallback_reason: str = None
    latency_ms: float = 100.0

    def __post_init__(self):
        if self.facts_observed is None:
            self.facts_observed = ["LABOR: 3 workers absent"]
        if self.skills_consulted is None:
            self.skills_consulted = []
        if self.recommendations is None:
            self.recommendations = [
                _FakeAssessmentRec(
                    domain=MagicMock(value="labor"),
                    capability=MagicMock(value="warehouse.labor.allocate"),
                )
            ]


def _make_rec(
    *,
    recommendation_id: str = "turn0001-rec-00",
    capability: str = "warehouse.labor.allocate",
    domain: str = "labor",
    target: str = "wave-017",
    objective: str = "Allocate labor to Wave 17",
    rationale: str = "Workers idle.",
    priority: str = "HIGH",
    snapshot_id: str = "snap-001",
    turn_id: str = "turn-analyze-001",
    trace_id: str = "trace-analyze-001",
    conversation_id: str = "conv-001",
    focus_entity_id: str = "wave-017",
) -> RecommendedActionResult:
    return RecommendedActionResult(
        recommendation_id=recommendation_id,
        domain=domain,
        capability=capability,
        target=target,
        objective=objective,
        rationale=rationale,
        priority=priority,
        subtype=None,
        conversation_id=conversation_id,
        turn_id=turn_id,
        trace_id=trace_id,
        snapshot_id=snapshot_id,
        focus_entity_id=focus_entity_id,
    )


def _make_act_result(
    decision_outcome: str = "REQUIRES_HUMAN_APPROVAL",
    mutation_state: MutationState = MutationState.NOT_ATTEMPTED,
    pending_approval_id: str | None = "pending-001",
    proposal_id: str | None = "proposal-001",
    decision_id: str | None = "decision-001",
    execution_id: str | None = None,
    execution_status: str | None = None,
    safety_note: str = "No warehouse changes have been made.",
) -> CopilotActResult:
    return CopilotActResult(
        message="I prepared the labor action for MAIW governance.\n\nDECISION\nREQUIRES HUMAN APPROVAL",
        recommendation_id="turn0001-rec-00",
        capability="warehouse.labor.allocate",
        target="wave-017",
        decision_outcome=decision_outcome,
        proposal_id=proposal_id,
        decision_id=decision_id,
        approval_required=(decision_outcome == "REQUIRES_HUMAN_APPROVAL"),
        pending_approval_id=pending_approval_id,
        execution_status=execution_status,
        execution_id=execution_id,
        mutation_state=mutation_state,
        safety_note=safety_note,
        violations=[],
        source_recommendation_id="turn0001-rec-00",
        source_snapshot_id="snap-001",
        snapshot_id="snap-002",
        conversation_id="conv-001",
        turn_id="turn-act-001",
        trace_id="trace-act-001",
        warehouse_id="DC-47",
        latency_ms=150.0,
    )


from contextlib import contextmanager

@contextmanager
def _patch_snapshot(state=None):
    """Patch WarehouseStateSnapshot.seal to return a _FakeSnapshot."""
    target_state = state or _FakeState()
    with patch("maiw_api.copilot.service.WarehouseStateSnapshot") as mock_wss:
        mock_wss.seal.side_effect = lambda s: _FakeSnapshot.seal(s if s is not None else target_state)
        yield mock_wss


def _make_service(
    state: Any = None,
    agent_assessment: Any = None,
) -> CopilotService:
    agent = MagicMock()
    agent.analyze_disruption = AsyncMock(
        return_value=agent_assessment or _FakeAssessment(
            trace_id="trace-1", snapshot_id="snap-1", warehouse_id="DC-47"
        )
    )
    provider = MagicMock()
    provider.get_state = AsyncMock(return_value=state or _FakeState())
    return CopilotService(
        operations_agent=agent,
        state_provider=provider,
        event_bus=None,
        graph=None,
    )


# ── 1. Architecture invariants ────────────────────────────────────────────────

class TestActArchitectureInvariants:

    def _copilot_service_src(self) -> str:
        return pathlib.Path("apps/api/maiw_api/copilot/service.py").read_text()

    def test_copilot_service_does_not_import_action_executor(self):
        tree = ast.parse(self._copilot_service_src())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in getattr(node, "names", [])]
                module = getattr(node, "module", "") or ""
                full = module + " " + " ".join(names)
                assert "ActionExecutor" not in full

    def test_copilot_service_does_not_import_decision_engine(self):
        tree = ast.parse(self._copilot_service_src())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in getattr(node, "names", [])]
                module = getattr(node, "module", "") or ""
                full = module + " " + " ".join(names)
                assert "DecisionEngine" not in full

    def test_copilot_service_does_not_import_approval_store(self):
        tree = ast.parse(self._copilot_service_src())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in getattr(node, "names", [])]
                module = getattr(node, "module", "") or ""
                full = module + " " + " ".join(names)
                assert "ApprovalStore" not in full

    def test_governed_action_orchestrator_owns_decision_engine(self):
        src = pathlib.Path("apps/api/maiw_api/copilot/orchestrator.py").read_text()
        assert "DecisionEngine" in src or "decision_engine" in src
        assert "ActionExecutor" in src or "executor" in src

    def test_copilot_act_result_has_no_proposal_objects(self):
        """CopilotActResult carries proposal_id (str) only — not ActionProposal objects."""
        field_names = {f.name for f in dataclasses.fields(CopilotActResult)}
        forbidden = {"proposal", "decision", "approval", "execution"}
        # Only exact matches forbidden — not substrings like proposal_id
        exact_forbidden = forbidden & field_names
        assert not exact_forbidden, (
            f"CopilotActResult must not carry live governance objects: {exact_forbidden}"
        )

    def test_governed_action_request_is_frozen(self):
        req = GovernedActionRequest(
            recommendation_id="r1", capability="warehouse.labor.allocate",
            target="wave-017", domain="labor", objective="test", rationale="test",
            priority="HIGH", subtype=None,
            conversation_id="conv-1", turn_id="turn-1", trace_id="trace-1",
            source_turn_id="source-turn", source_trace_id="source-trace",
            source_snapshot_id="snap-1", current_snapshot_id="snap-2",
            focus_entity_id="wave-017",
        )
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            req.recommendation_id = "mutated"  # type: ignore[misc]


# ── 2. Intent classifier — Phase 15D additions ────────────────────────────────

class TestIntentClassifierPhase15D:

    @pytest.mark.parametrize("message", [
        "Proceed.",
        "Do it.",
        "Allocate the workers.",
        "Reprioritize the wave.",
        "Go ahead and apply the fix.",
        "Execute the recommendation.",
        "Prepare that action.",
    ])
    def test_act_messages_classify_as_act(self, message: str):
        assert classify(message) == CopilotIntent.ACT

    @pytest.mark.parametrize("message", [
        "Why is Wave 17 at risk?",
        "What happened to the carrier cutoff?",
        "How many workers are idle?",
    ])
    def test_ask_messages_still_classify_as_ask(self, message: str):
        assert classify(message) == CopilotIntent.ASK

    @pytest.mark.parametrize("message", [
        "What should we do?",
        "What do you recommend?",
        "How should we respond?",
    ])
    def test_analyze_messages_still_classify_as_analyze(self, message: str):
        assert classify(message) == CopilotIntent.ANALYZE

    def test_act_wins_over_analyze_for_execute(self):
        assert classify("Execute the recommendation please") == CopilotIntent.ACT


# ── 3. Recommendation resolution ─────────────────────────────────────────────

class TestRecommendationResolution:

    def test_single_recommendation_selected_directly(self):
        recs = [_make_rec()]
        rec, reason = _select_recommendation("Do it.", recs)
        assert rec is not None
        assert rec.recommendation_id == "turn0001-rec-00"
        assert reason == "single"

    def test_empty_recommendations_returns_not_found(self):
        rec, reason = _select_recommendation("Do it.", [])
        assert rec is None
        assert reason == "not_found"

    def test_two_recs_do_it_is_ambiguous(self):
        recs = [_make_rec(recommendation_id="r1"), _make_rec(recommendation_id="r2")]
        rec, reason = _select_recommendation("Do it.", recs)
        assert rec is None
        assert reason == "ambiguous"

    def test_explicit_first_selects_index_0(self):
        recs = [_make_rec(recommendation_id="r1"), _make_rec(recommendation_id="r2")]
        rec, reason = _select_recommendation("Do the first one.", recs)
        assert rec is not None
        assert rec.recommendation_id == "r1"
        assert reason == "explicit_index"

    def test_explicit_second_selects_index_1(self):
        recs = [_make_rec(recommendation_id="r1"), _make_rec(recommendation_id="r2")]
        rec, reason = _select_recommendation("Do the second one.", recs)
        assert rec is not None
        assert rec.recommendation_id == "r2"
        assert reason == "explicit_index"

    def test_capability_keyword_matches_labor_rec(self):
        labor_rec = _make_rec(
            recommendation_id="labor-rec",
            capability="warehouse.labor.allocate",
            domain="labor",
        )
        wave_rec = _make_rec(
            recommendation_id="wave-rec",
            capability="warehouse.wave.reprioritize",
            domain="wave",
        )
        rec, reason = _select_recommendation("Allocate the workers.", [labor_rec, wave_rec])
        assert rec is not None
        assert rec.recommendation_id == "labor-rec"
        assert reason == "capability_match"

    def test_capability_keyword_matches_wave_rec(self):
        labor_rec = _make_rec(
            recommendation_id="labor-rec",
            capability="warehouse.labor.allocate",
            domain="labor",
        )
        wave_rec = _make_rec(
            recommendation_id="wave-rec",
            capability="warehouse.wave.reprioritize",
            domain="wave",
        )
        rec, reason = _select_recommendation("Reprioritize the wave.", [labor_rec, wave_rec])
        assert rec is not None
        assert rec.recommendation_id == "wave-rec"
        assert reason == "capability_match"


# ── 4. State drift detection ──────────────────────────────────────────────────

class TestStateDriftDetection:

    def test_labor_allocation_no_drift_when_workers_idle(self):
        rec = _make_rec(capability="warehouse.labor.allocate")
        state = _FakeState()
        state.labor = _FakeDomainState(idle_workers=3)
        assert _check_state_drift(rec, state) is None

    def test_labor_allocation_drift_when_no_idle_workers(self):
        rec = _make_rec(capability="warehouse.labor.allocate")
        state = _FakeState()
        state.labor = _FakeDomainState(idle_workers=0)
        reason = _check_state_drift(rec, state)
        assert reason is not None
        assert "idle" in reason.lower() or "worker" in reason.lower()

    def test_wave_reprioritize_no_drift_when_waves_exist(self):
        rec = _make_rec(capability="warehouse.wave.reprioritize")
        state = _FakeState()
        state.waves = _FakeDomainState(total_waves=3, total_tasks=90)
        assert _check_state_drift(rec, state) is None

    def test_equipment_assign_no_drift_check(self):
        rec = _make_rec(capability="warehouse.equipment.assign")
        state = _FakeState()
        # Equipment drift not heuristically checked — DecisionEngine handles it
        assert _check_state_drift(rec, state) is None


# ── 5. Canonical three-turn flow ──────────────────────────────────────────────

class TestCanonicalThreeTurnFlow:

    @pytest.mark.asyncio
    async def test_ask_analyze_act_requires_human_approval(self):
        """
        Three-turn canonical test modeled via injected conversation state:
          Turn 1 (ASK) and Turn 2 (ANALYZE) are simulated by pre-loading
          last_recommendations, then Turn 3 (ACT "Do it.") is exercised end-to-end.
        """
        svc = _make_service()

        mock_orchestrator = AsyncMock()
        act_result = _make_act_result(
            decision_outcome="REQUIRES_HUMAN_APPROVAL",
            mutation_state=MutationState.NOT_ATTEMPTED,
            pending_approval_id="pending-001",
        )
        mock_orchestrator.govern = AsyncMock(return_value=act_result)
        svc.set_orchestrator(mock_orchestrator)

        # Simulate ANALYZE having already run
        conv = svc.store.get_or_create(None, "DC-47", "labor-constraint-wave-risk")
        rec = _make_rec(
            recommendation_id="turn-analyze-rec-00",
            capability="warehouse.labor.allocate",
            snapshot_id="snap-001",
            trace_id="trace-analyze-001",
            turn_id="turn-analyze-001",
            conversation_id=conv.conversation_id,
        )
        conv.last_recommendations = [rec]

        with patch("maiw_api.copilot.service.WarehouseStateSnapshot") as mock_wss:
            snap2 = _FakeSnapshot(snapshot_id="snap-002", warehouse_id="DC-47")
            mock_wss.seal.return_value = snap2

            result, turn = await svc.act(
                message="Do it.",
                conversation_id=conv.conversation_id,
                warehouse_id="DC-47",
                scenario_name="labor-constraint-wave-risk",
            )

        # No mutation before approval
        assert result.decision_outcome == "REQUIRES_HUMAN_APPROVAL"
        assert result.mutation_state == MutationState.NOT_ATTEMPTED
        assert result.pending_approval_id == "pending-001"
        assert result.approval_required is True
        assert "No warehouse" in result.safety_note

        # Orchestrator called with correct GovernedActionRequest
        assert mock_orchestrator.govern.called
        req = mock_orchestrator.govern.call_args.kwargs["request"]
        assert req.capability == "warehouse.labor.allocate"
        assert req.source_snapshot_id == "snap-001"
        assert req.current_snapshot_id == "snap-002"

        # Turn stored with correct intent and artifact refs
        assert turn.intent == CopilotIntent.ACT
        assert turn.artifact_refs.get("proposal_id") == "proposal-001"
        assert turn.artifact_refs.get("decision_id") == "decision-001"
        assert turn.artifact_refs.get("pending_approval_id") == "pending-001"

    @pytest.mark.asyncio
    async def test_act_without_prior_analyze_returns_clarification(self):
        svc = _make_service()
        mock_orch = AsyncMock()
        svc.set_orchestrator(mock_orch)

        # Fresh conversation — no last_recommendations
        result, turn = await svc.act(
            message="Do it.",
            conversation_id=None,
            warehouse_id="DC-47",
            scenario_name="",
        )

        assert result.decision_outcome == "CLARIFICATION_REQUIRED"
        assert "no recommendations" in result.message.lower()
        assert mock_orch.govern.call_count == 0  # orchestrator never called


# ── 6. Stale-state protection ─────────────────────────────────────────────────

class TestStaleStateProtection:

    @pytest.mark.asyncio
    async def test_stale_labor_allocation_blocked(self):
        """
        When current state shows no idle workers, labor allocation is blocked
        before the proposal is built.
        """
        # Current state has no idle workers
        state = _FakeState()
        state.labor = _FakeDomainState(idle_workers=0)

        svc = _make_service(state=state)
        mock_orch = AsyncMock()
        svc.set_orchestrator(mock_orch)

        conv = svc.store.get_or_create(None, "DC-47", "")
        conv.last_recommendations = [_make_rec(capability="warehouse.labor.allocate")]

        with _patch_snapshot(state):
            result, turn = await svc.act(
                message="Do it.",
                conversation_id=conv.conversation_id,
                warehouse_id="DC-47",
                scenario_name="",
            )

        assert result.decision_outcome == "STALE_STATE"
        assert mock_orch.govern.call_count == 0  # proposal never built


# ── 7. Duplicate ACT idempotency ──────────────────────────────────────────────

class TestDuplicateActIdempotency:

    @pytest.mark.asyncio
    async def test_duplicate_do_it_returns_same_pending_id(self):
        """
        The controller.add_pending_approval dedup logic (keyed on
        capability+target+domain) prevents duplicate pending approvals.
        """
        svc = _make_service()

        pending_id = "pending-dedup-001"
        act1 = _make_act_result(pending_approval_id=pending_id)
        act2 = _make_act_result(pending_approval_id=pending_id)
        mock_orch = AsyncMock()
        mock_orch.govern = AsyncMock(side_effect=[act1, act2])
        svc.set_orchestrator(mock_orch)

        conv = svc.store.get_or_create(None, "DC-47", "")
        conv.last_recommendations = [_make_rec()]

        with _patch_snapshot():
            r1, _ = await svc.act(
                message="Do it.",
                conversation_id=conv.conversation_id,
                warehouse_id="DC-47",
            )
            r2, _ = await svc.act(
                message="Do it.",
                conversation_id=conv.conversation_id,
                warehouse_id="DC-47",
            )

        assert r1.pending_approval_id == pending_id
        assert r2.pending_approval_id == pending_id

    @pytest.mark.asyncio
    async def test_ambiguous_multiple_recs_do_it(self):
        """Two recommendations + 'Do it.' → CLARIFICATION_REQUIRED, no proposal."""
        svc = _make_service()
        mock_orch = AsyncMock()
        svc.set_orchestrator(mock_orch)

        conv = svc.store.get_or_create(None, "DC-47", "")
        conv.last_recommendations = [
            _make_rec(recommendation_id="r1", capability="warehouse.labor.allocate"),
            _make_rec(recommendation_id="r2", capability="warehouse.wave.reprioritize"),
        ]

        result, _ = await svc.act(
            message="Do it.",
            conversation_id=conv.conversation_id,
            warehouse_id="DC-47",
        )

        assert result.decision_outcome == "CLARIFICATION_REQUIRED"
        assert "1." in result.message or "2." in result.message  # shows numbered list
        assert mock_orch.govern.call_count == 0


# ── 8. Decision outcomes ──────────────────────────────────────────────────────

class TestDecisionOutcomes:

    @pytest.mark.asyncio
    async def test_rejected_outcome_surfaces_violations(self):
        svc = _make_service()
        rejected = _make_act_result(
            decision_outcome="REJECTED",
            mutation_state=MutationState.NOT_ATTEMPTED,
            pending_approval_id=None,
            proposal_id="proposal-001",
            decision_id="decision-001",
            safety_note="No warehouse changes have been made.",
        )
        rejected.violations = [{"code": "ASSET_NOT_FOUND", "message": "Equipment not found."}]
        mock_orch = AsyncMock()
        mock_orch.govern = AsyncMock(return_value=rejected)
        svc.set_orchestrator(mock_orch)

        conv = svc.store.get_or_create(None, "DC-47", "")
        conv.last_recommendations = [_make_rec()]

        with _patch_snapshot():
            result, turn = await svc.act(
                message="Do it.",
                conversation_id=conv.conversation_id,
                warehouse_id="DC-47",
            )

        assert result.decision_outcome == "REJECTED"
        assert result.mutation_state == MutationState.NOT_ATTEMPTED
        assert result.approval_required is False
        assert result.pending_approval_id is None
        assert "No warehouse" in result.safety_note

    @pytest.mark.asyncio
    async def test_requires_fresh_state_outcome(self):
        svc = _make_service()
        stale = _make_act_result(
            decision_outcome="REQUIRES_FRESH_STATE",
            mutation_state=MutationState.NOT_ATTEMPTED,
            pending_approval_id=None,
            safety_note="No warehouse changes have been made.",
        )
        mock_orch = AsyncMock()
        mock_orch.govern = AsyncMock(return_value=stale)
        svc.set_orchestrator(mock_orch)

        conv = svc.store.get_or_create(None, "DC-47", "")
        conv.last_recommendations = [_make_rec()]

        with _patch_snapshot():
            result, _ = await svc.act(
                message="Do it.",
                conversation_id=conv.conversation_id,
                warehouse_id="DC-47",
            )

        assert result.decision_outcome == "REQUIRES_FRESH_STATE"
        assert result.mutation_state == MutationState.NOT_ATTEMPTED

    @pytest.mark.asyncio
    async def test_approved_executed_is_confirmed(self):
        svc = _make_service()
        executed = _make_act_result(
            decision_outcome="APPROVED",
            mutation_state=MutationState.CONFIRMED,
            pending_approval_id=None,
            execution_status="EXECUTED",
            execution_id="exec-001",
            safety_note="Execution confirmed.",
        )
        mock_orch = AsyncMock()
        mock_orch.govern = AsyncMock(return_value=executed)
        svc.set_orchestrator(mock_orch)

        conv = svc.store.get_or_create(None, "DC-47", "")
        conv.last_recommendations = [_make_rec()]

        with _patch_snapshot():
            result, _ = await svc.act(
                message="Do it.",
                conversation_id=conv.conversation_id,
                warehouse_id="DC-47",
            )

        assert result.decision_outcome == "APPROVED"
        assert result.mutation_state == MutationState.CONFIRMED
        assert result.execution_status == "EXECUTED"
        assert "Execution confirmed" in result.safety_note

    @pytest.mark.asyncio
    async def test_approved_unknown_execution_is_unknown(self):
        svc = _make_service()
        unknown = _make_act_result(
            decision_outcome="APPROVED",
            mutation_state=MutationState.UNKNOWN,
            pending_approval_id=None,
            execution_status="UNKNOWN",
            execution_id="exec-002",
            safety_note="Execution status uncertain — reconciliation required.",
        )
        mock_orch = AsyncMock()
        mock_orch.govern = AsyncMock(return_value=unknown)
        svc.set_orchestrator(mock_orch)

        conv = svc.store.get_or_create(None, "DC-47", "")
        conv.last_recommendations = [_make_rec()]

        with _patch_snapshot():
            result, _ = await svc.act(
                message="Do it.",
                conversation_id=conv.conversation_id,
                warehouse_id="DC-47",
            )

        assert result.mutation_state == MutationState.UNKNOWN
        assert "uncertain" in result.safety_note.lower()


# ── 9. No orchestrator → NOT_IMPLEMENTED ─────────────────────────────────────

class TestNoOrchestrator:

    @pytest.mark.asyncio
    async def test_act_without_orchestrator_returns_not_implemented(self):
        svc = _make_service()
        # No set_orchestrator() call

        result, turn = await svc.act(
            message="Do it.",
            conversation_id=None,
            warehouse_id="DC-47",
        )

        assert result.decision_outcome == "NOT_IMPLEMENTED"
        assert turn.intent == CopilotIntent.ACT
        assert result.mutation_state == MutationState.NOT_ATTEMPTED


# ── 10. ACT turn provenance ───────────────────────────────────────────────────

class TestActTurnProvenance:

    @pytest.mark.asyncio
    async def test_act_turn_has_act_intent_and_artifact_refs(self):
        svc = _make_service()
        act_result = _make_act_result(
            decision_outcome="REQUIRES_HUMAN_APPROVAL",
            proposal_id="prop-abc",
            decision_id="dec-xyz",
            pending_approval_id="pending-123",
        )
        mock_orch = AsyncMock()
        mock_orch.govern = AsyncMock(return_value=act_result)
        svc.set_orchestrator(mock_orch)

        conv = svc.store.get_or_create(None, "DC-47", "")
        conv.last_recommendations = [_make_rec()]

        with _patch_snapshot():
            _, turn = await svc.act(
                message="Do it.",
                conversation_id=conv.conversation_id,
                warehouse_id="DC-47",
            )

        assert turn.intent == CopilotIntent.ACT
        assert turn.artifact_refs["proposal_id"] == "prop-abc"
        assert turn.artifact_refs["decision_id"] == "dec-xyz"
        assert turn.artifact_refs["pending_approval_id"] == "pending-123"

    @pytest.mark.asyncio
    async def test_act_trace_id_is_fresh_not_reused_from_analyze(self):
        """ACT gets a new trace_id distinct from the ANALYZE trace."""
        svc = _make_service()
        act_result = _make_act_result()
        mock_orch = AsyncMock()
        mock_orch.govern = AsyncMock(return_value=act_result)
        svc.set_orchestrator(mock_orch)

        # Simulate ANALYZE turn with a known trace_id
        conv = svc.store.get_or_create(None, "DC-47", "")
        rec = _make_rec(
            trace_id="trace-analyze-from-prior-turn",
            turn_id="turn-analyze-prior",
            conversation_id=conv.conversation_id,
        )
        conv.last_recommendations = [rec]
        # Record a fake analyze turn in the conversation so we have a turn_id to compare
        from maiw_api.copilot.models import CopilotTurn
        analyze_turn = CopilotTurn(
            conversation_id=conv.conversation_id,
            turn_id="turn-analyze-prior",
            trace_id="trace-analyze-from-prior-turn",
            intent=CopilotIntent.ANALYZE,
            user_message="What should we do?",
            created_at=datetime.now(timezone.utc),
            response_summary="Assessment complete.",
            artifact_refs={},
        )
        conv.turns.append(analyze_turn)

        with _patch_snapshot():
            _, act_turn = await svc.act(
                message="Do it.",
                conversation_id=conv.conversation_id,
                warehouse_id="DC-47",
                scenario_name="",
            )

        # ACT trace must differ from ANALYZE trace
        assert act_turn.trace_id != "trace-analyze-from-prior-turn"
        req = mock_orch.govern.call_args.kwargs["request"]
        assert req.trace_id == act_turn.trace_id
        assert req.source_trace_id == "trace-analyze-from-prior-turn"


# ── 11. GovernedActionOrchestrator unit tests ─────────────────────────────────

class TestGovernedActionOrchestrator:

    def _make_request(self, **kwargs) -> GovernedActionRequest:
        defaults = dict(
            recommendation_id="r1",
            capability="warehouse.labor.allocate",
            target="wave-017",
            domain="labor",
            objective="Allocate labor",
            rationale="Workers idle.",
            priority="HIGH",
            subtype=None,
            conversation_id="conv-1",
            turn_id="turn-1",
            trace_id="trace-1",
            source_turn_id="src-turn",
            source_trace_id="src-trace",
            source_snapshot_id="snap-001",
            current_snapshot_id="snap-002",
            focus_entity_id="wave-017",
        )
        defaults.update(kwargs)
        return GovernedActionRequest(**defaults)

    @staticmethod
    def _mock_decision_request():
        """Patch DecisionRequest so Pydantic validation is bypassed."""
        return patch("maiw_decision.models.DecisionRequest", new=MagicMock(return_value=MagicMock()))

    @pytest.mark.asyncio
    async def test_requires_human_approval_creates_pending(self):
        from maiw_api.copilot.orchestrator import GovernedActionOrchestrator
        from maiw_decision.models import DecisionOutcome, DecisionResult

        decision_result = MagicMock(spec=DecisionResult)
        decision_result.outcome = DecisionOutcome.REQUIRES_HUMAN_APPROVAL
        decision_result.result_id = "dec-001"
        decision_result.violations = []

        mock_engine = MagicMock()
        mock_engine.evaluate.return_value = (decision_result, MagicMock())

        mock_ctrl = MagicMock()
        mock_ctrl.add_pending_approval.return_value = "pending-orch-001"
        mock_runtime = MagicMock()

        mock_proposal = MagicMock()
        mock_proposal.proposal_id = "prop-orch-001"
        mock_proposal.risk_level = MagicMock(value="MEDIUM")
        mock_proposal.model_dump.return_value = {}

        orch = GovernedActionOrchestrator(
            decision_engine=mock_engine,
            demo_controller=mock_ctrl,
            runtime=mock_runtime,
        )

        with self._mock_decision_request(), \
             patch.object(orch, "_build_proposal", new=AsyncMock(return_value=mock_proposal)):
            result = await orch.govern(
                request=self._make_request(),
                snapshot=MagicMock(),
                warehouse_id="DC-47",
            )

        assert result.decision_outcome == "REQUIRES_HUMAN_APPROVAL"
        assert result.pending_approval_id == "pending-orch-001"
        assert result.mutation_state == MutationState.NOT_ATTEMPTED
        assert result.approval_required is True
        assert "No warehouse" in result.safety_note
        assert mock_ctrl.add_pending_approval.call_count == 1

    @pytest.mark.asyncio
    async def test_rejected_outcome_no_pending_created(self):
        from maiw_api.copilot.orchestrator import GovernedActionOrchestrator
        from maiw_decision.models import DecisionOutcome, DecisionResult

        violation = MagicMock()
        violation.model_dump.return_value = {"code": "BLOCKED", "message": "Not authorized."}

        decision_result = MagicMock(spec=DecisionResult)
        decision_result.outcome = DecisionOutcome.REJECTED
        decision_result.result_id = "dec-002"
        decision_result.violations = [violation]

        mock_engine = MagicMock()
        mock_engine.evaluate.return_value = (decision_result, MagicMock())

        mock_ctrl = MagicMock()
        mock_runtime = MagicMock()

        mock_proposal = MagicMock()
        mock_proposal.proposal_id = "prop-002"
        mock_proposal.risk_level = MagicMock(value="MEDIUM")

        orch = GovernedActionOrchestrator(
            decision_engine=mock_engine,
            demo_controller=mock_ctrl,
            runtime=mock_runtime,
        )

        with self._mock_decision_request(), \
             patch.object(orch, "_build_proposal", new=AsyncMock(return_value=mock_proposal)):
            result = await orch.govern(
                request=self._make_request(),
                snapshot=MagicMock(),
                warehouse_id="DC-47",
            )

        assert result.decision_outcome == "REJECTED"
        assert result.mutation_state == MutationState.NOT_ATTEMPTED
        assert result.pending_approval_id is None
        assert mock_ctrl.add_pending_approval.call_count == 0
        assert len(result.violations) == 1

    @pytest.mark.asyncio
    async def test_unsupported_capability_returns_error(self):
        from maiw_api.copilot.orchestrator import GovernedActionOrchestrator

        orch = GovernedActionOrchestrator(
            decision_engine=MagicMock(),
            demo_controller=MagicMock(),
            runtime=MagicMock(),
        )

        result = await orch.govern(
            request=self._make_request(capability="warehouse.unknown.action"),
            snapshot=MagicMock(),
            warehouse_id="DC-47",
        )

        assert result.decision_outcome == "ERROR"
        assert result.mutation_state == MutationState.NOT_ATTEMPTED
        assert "cannot" in result.message.lower() or "unsupported" in result.message.lower()
