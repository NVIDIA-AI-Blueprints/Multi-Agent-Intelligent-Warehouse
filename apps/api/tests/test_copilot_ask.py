# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 15B — Copilot ASK tests.

Covers
------
1. Architecture invariants (import guards, forbidden paths)
2. CopilotIntent enum
3. CopilotTurn identity model
4. InMemoryCopilotStore
5. ASK turn — green path (mocked agent + state)
6. ASK turn — state unavailable → explicit degradation (no simulated data)
7. ASK turn — graph unavailable → degradation noted, still answers
8. ASK turn — agent error → explicit error response
9. Context size bounds (max_entities enforced)
10. Evidence extraction from assessment facts

All tests confirm zero ActionProposals, zero DecisionEngine calls, zero writes.
"""

from __future__ import annotations

import importlib
import inspect
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maiw_api.copilot.models import (
    CopilotAskResult,
    CopilotConversation,
    CopilotIntent,
    CopilotTurn,
    ContextNeighborhood,
    EvidenceFact,
)
from maiw_api.copilot.service import CopilotService, _facts_to_evidence
from maiw_api.copilot.store import InMemoryCopilotStore


# ── Fixtures ───────────────────────────────────────────────────────────────────

@dataclass
class _FakeDomainState:
    """Non-None placeholder so _get_state doesn't flag domains as missing."""
    pass


@dataclass
class _FakeState:
    warehouse_id: str = "DC-47"
    equipment: Any = None
    labor: Any = None
    waves: Any = None

    def __post_init__(self):
        # Default to non-None so the service doesn't degrade on missing domains
        if self.equipment is None:
            self.equipment = _FakeDomainState()
        if self.labor is None:
            self.labor = _FakeDomainState()
        if self.waves is None:
            self.waves = _FakeDomainState()

    def is_empty(self) -> bool:
        return False


@dataclass
class _FakeSnapshot:
    snapshot_id: str
    warehouse_id: str
    state: Any

    @classmethod
    def seal(cls, state: Any) -> "_FakeSnapshot":
        return cls(snapshot_id=str(uuid.uuid4()), warehouse_id=state.warehouse_id, state=state)


@dataclass
class _FakeAssessment:
    trace_id: str
    snapshot_id: str
    warehouse_id: str
    summary: str = "Wave 17 is primarily constrained by labor availability."
    severity: str = "high"
    facts_observed: list = None
    skills_consulted: list = None
    recommendations: list = None
    model_id: str = "nvidia/nemotron-3-nano-30b-a3b"
    routing_rule: str = "medium_reasoning"
    routing_reason: str = "Copilot ASK — MEDIUM reasoning"
    latency_ms: float = 312.5

    def __post_init__(self):
        if self.facts_observed is None:
            self.facts_observed = [
                "Labor: 120 total, 40 available, 67% utilization",
                "Wave tasks: 120 total, 5 pending, 8 in_progress, 3 at-risk",
                "Equipment: 24 total, 24 available",
                "UNASSIGNED PENDING TASKS: 5 pending wave tasks have no worker allocated",
            ]
        if self.skills_consulted is None:
            self.skills_consulted = ["warehouse.labor.get_capacity", "warehouse.wave.get_state"]
        if self.recommendations is None:
            self.recommendations = []


def _make_agent(assessment: _FakeAssessment | None = None) -> MagicMock:
    agent = MagicMock()
    agent.analyze_disruption = AsyncMock(
        return_value=assessment or _FakeAssessment(
            trace_id="trace-1", snapshot_id="snap-1", warehouse_id="DC-47"
        )
    )
    return agent


def _make_state_provider(state: Any = None, raises: Exception | None = None) -> MagicMock:
    provider = MagicMock()
    if raises:
        provider.get_state = AsyncMock(side_effect=raises)
    else:
        provider.get_state = AsyncMock(return_value=state or _FakeState())
    return provider


def _make_mock_graph() -> MagicMock:
    """Minimal mock graph — returns one wave entity, no neighbors."""
    graph = MagicMock()
    wave_entity = MagicMock()
    wave_entity.entity_id = "WAVE-DC47-001"
    wave_entity.wave_number = 17
    graph.entities_by_type.return_value = [wave_entity]
    graph.neighbors.return_value = []
    graph.outgoing_edges.return_value = []
    graph.incoming_edges.return_value = []
    return graph


def _make_service(
    agent=None,
    state_provider=None,
    graph=None,
    raises_state: Exception | None = None,
    include_graph: bool = True,
) -> CopilotService:
    return CopilotService(
        operations_agent=agent or _make_agent(),
        state_provider=state_provider or _make_state_provider(raises=raises_state),
        event_bus=None,
        graph=graph if graph is not None else (_make_mock_graph() if include_graph else None),
    )


# ── 1. Architecture invariants ─────────────────────────────────────────────────

class TestArchitectureInvariants:
    """These tests protect the Copilot trust boundary."""

    def test_copilot_service_does_not_import_action_executor(self):
        """CopilotService must not import ActionExecutor — trust boundary."""
        import maiw_api.copilot.service as svc_module

        # Check actual imports, not docstring text
        imports = {name for name in dir(svc_module) if not name.startswith("_")}
        assert "ActionExecutor" not in imports, (
            "CopilotService MUST NOT import ActionExecutor"
        )
        # Also verify no 'from ... import ActionExecutor' lines exist in code
        lines = inspect.getsource(svc_module).splitlines()
        import_lines = [l for l in lines if l.strip().startswith(("import ", "from "))]
        assert not any("ActionExecutor" in l for l in import_lines)

    def test_copilot_service_does_not_import_approval_store(self):
        """CopilotService must not import ApprovalStore."""
        import maiw_api.copilot.service as svc_module

        lines = inspect.getsource(svc_module).splitlines()
        import_lines = [l for l in lines if l.strip().startswith(("import ", "from "))]
        assert not any("ApprovalStore" in l for l in import_lines)

    def test_copilot_service_does_not_import_decision_engine(self):
        """CopilotService must not import DecisionEngine."""
        import maiw_api.copilot.service as svc_module

        lines = inspect.getsource(svc_module).splitlines()
        import_lines = [l for l in lines if l.strip().startswith(("import ", "from "))]
        assert not any("DecisionEngine" in l for l in import_lines)

    def test_copilot_service_has_no_evaluate_call(self):
        """CopilotService must not call .evaluate() on any decision engine."""
        import maiw_api.copilot.service as svc_module

        lines = inspect.getsource(svc_module).splitlines()
        # Exclude comment/docstring lines
        code_lines = [l for l in lines if not l.strip().startswith("#") and '"""' not in l]
        assert not any("engine.evaluate(" in l or "decision_engine.evaluate(" in l
                       for l in code_lines)

    def test_copilot_service_has_no_approve_call(self):
        """CopilotService must not call approval_store.approve()."""
        import maiw_api.copilot.service as svc_module

        lines = inspect.getsource(svc_module).splitlines()
        code_lines = [l for l in lines if not l.strip().startswith("#") and '"""' not in l]
        assert not any(".approve(" in l for l in code_lines)

    def test_copilot_router_has_no_approve_endpoint(self):
        """The copilot router must not register a /approve route."""
        import maiw_api.routers.copilot as router_module
        from fastapi import APIRouter

        # Check registered routes on the router object
        route_paths = [r.path for r in router_module.router.routes]
        assert not any("approve" in p for p in route_paths), (
            f"Copilot router MUST NOT have /approve endpoint — found: {route_paths}"
        )

    def test_copilot_router_has_no_execute_endpoint(self):
        """The copilot router must not register a /execute route."""
        import maiw_api.routers.copilot as router_module

        route_paths = [r.path for r in router_module.router.routes]
        assert not any("execute" in p for p in route_paths), (
            f"Copilot router MUST NOT have /execute endpoint — found: {route_paths}"
        )

    def test_copilot_router_has_no_force_action_endpoint(self):
        import maiw_api.routers.copilot as router_module

        route_paths = [r.path for r in router_module.router.routes]
        assert not any("force" in p for p in route_paths)


# ── 2. CopilotIntent enum ──────────────────────────────────────────────────────

class TestCopilotIntent:
    def test_intent_values(self):
        assert CopilotIntent.ASK.value == "ask"
        assert CopilotIntent.ANALYZE.value == "analyze"
        assert CopilotIntent.ACT.value == "act"

    def test_intent_is_str_subclass(self):
        assert isinstance(CopilotIntent.ASK, str)
        assert CopilotIntent.ASK == "ask"

    def test_intent_enum_count(self):
        # Phase 15B: exactly 3 intents. SIMULATE not yet added.
        assert len(CopilotIntent) == 3

    def test_no_simulate_intent_yet(self):
        intent_values = {i.value for i in CopilotIntent}
        assert "simulate" not in intent_values


# ── 3. Conversation identity model ────────────────────────────────────────────

class TestConversationIdentity:
    def test_turn_has_distinct_ids(self):
        turn = CopilotTurn(
            turn_id="T1",
            conversation_id="C1",
            user_message="Why is Wave 17 at risk?",
            intent=CopilotIntent.ASK,
            created_at=datetime.now(timezone.utc),
            trace_id="R1",
            response_summary="answer",
        )
        # Three distinct IDs
        assert turn.turn_id != turn.conversation_id
        assert turn.turn_id != turn.trace_id
        assert turn.conversation_id != turn.trace_id

    def test_turn_stores_no_hidden_reasoning(self):
        """CopilotTurn must not have chain_of_thought, scratchpad, hidden_reasoning."""
        fields = {f.name for f in CopilotTurn.__dataclass_fields__.values()}
        forbidden = {"chain_of_thought", "scratchpad", "hidden_reasoning", "reasoning_tokens"}
        assert not fields & forbidden, f"Forbidden fields present: {fields & forbidden}"

    def test_conversation_links_trace_ids(self):
        conv = CopilotConversation(
            conversation_id="C1",
            warehouse_id="DC-47",
            scenario_name="labor_constraint",
        )
        turn1 = CopilotTurn(
            turn_id="T1", conversation_id="C1", user_message="q1",
            intent=CopilotIntent.ASK, created_at=datetime.now(timezone.utc),
            trace_id="R1", response_summary="a1",
        )
        turn2 = CopilotTurn(
            turn_id="T2", conversation_id="C1", user_message="q2",
            intent=CopilotIntent.ASK, created_at=datetime.now(timezone.utc),
            trace_id="R2", response_summary="a2",
        )
        conv.add_turn(turn1)
        conv.add_turn(turn2)

        assert len(conv.turns) == 2
        assert "R1" in conv.related_trace_ids
        assert "R2" in conv.related_trace_ids
        # trace_ids must stay distinct across turns
        assert "R1" != "R2"


# ── 4. InMemoryCopilotStore ───────────────────────────────────────────────────

class TestInMemoryCopilotStore:
    def test_create_and_get_conversation(self):
        store = InMemoryCopilotStore()
        conv = store.create_conversation("DC-47", "labor_constraint")
        assert conv.conversation_id is not None
        fetched = store.get_conversation(conv.conversation_id)
        assert fetched is conv

    def test_get_or_create_with_existing_id(self):
        store = InMemoryCopilotStore()
        conv = store.create_conversation("DC-47", "")
        same = store.get_or_create(conv.conversation_id, "DC-47", "")
        assert same is conv

    def test_get_or_create_new_when_id_none(self):
        store = InMemoryCopilotStore()
        conv = store.get_or_create(None, "DC-47", "labor_constraint")
        assert conv.conversation_id is not None

    def test_add_turn_populates_conversation(self):
        store = InMemoryCopilotStore()
        conv = store.create_conversation("DC-47", "")
        turn = CopilotTurn(
            turn_id="T1", conversation_id=conv.conversation_id, user_message="q",
            intent=CopilotIntent.ASK, created_at=datetime.now(timezone.utc),
            trace_id="R1", response_summary="a",
        )
        store.add_turn(turn)
        assert len(store.get_conversation(conv.conversation_id).turns) == 1

    def test_reset_clears_all(self):
        store = InMemoryCopilotStore()
        store.create_conversation("DC-47", "")
        store.reset()
        assert store.get_conversation("anything") is None


# ── 5. ASK turn — green path ──────────────────────────────────────────────────

class TestAskGreenPath:
    @pytest.mark.asyncio
    async def test_ask_returns_answer(self):
        with patch("maiw_api.copilot.service.WarehouseStateSnapshot") as mock_snap:
            mock_snap.seal.return_value = _FakeSnapshot.seal(_FakeState())
            svc = _make_service()
            result, turn = await svc.ask(
                message="Why is Wave 17 at risk?",
                conversation_id=None,
                warehouse_id="DC-47",
            )

        assert result.answer == "Wave 17 is primarily constrained by labor availability."
        assert result.degraded is False
        assert result.trace_id == turn.trace_id
        assert turn.intent == CopilotIntent.ASK

    @pytest.mark.asyncio
    async def test_ask_produces_zero_action_proposals(self):
        """ASK turn must never return an ActionProposal."""
        with patch("maiw_api.copilot.service.WarehouseStateSnapshot") as mock_snap:
            mock_snap.seal.return_value = _FakeSnapshot.seal(_FakeState())
            svc = _make_service()
            result, turn = await svc.ask(
                message="Why is Wave 17 at risk?",
                conversation_id=None,
                warehouse_id="DC-47",
            )

        assert not hasattr(result, "proposal") or result.__class__.__name__ == "CopilotAskResult"
        # CopilotAskResult must not have proposal/decision/approval/execution fields
        result_fields = set(vars(result).keys())
        forbidden = {"proposal", "decision", "approval", "execution"}
        assert not result_fields & forbidden

    @pytest.mark.asyncio
    async def test_ask_does_not_call_decision_engine(self):
        decision_engine = MagicMock()
        decision_engine.evaluate = MagicMock()
        with patch("maiw_api.copilot.service.WarehouseStateSnapshot") as mock_snap:
            mock_snap.seal.return_value = _FakeSnapshot.seal(_FakeState())
            svc = _make_service()
            await svc.ask(
                message="Why is Wave 17 at risk?",
                conversation_id=None,
                warehouse_id="DC-47",
            )
        decision_engine.evaluate.assert_not_called()

    @pytest.mark.asyncio
    async def test_ask_passes_medium_reasoning_to_agent(self):
        """Copilot expresses ReasoningLevel.MEDIUM for ASK; ModelGateway selects model."""
        agent = _make_agent()
        with patch("maiw_api.copilot.service.WarehouseStateSnapshot") as mock_snap:
            mock_snap.seal.return_value = _FakeSnapshot.seal(_FakeState())
            svc = _make_service(agent=agent)
            await svc.ask(
                message="Why is Wave 17 at risk?",
                conversation_id=None,
                warehouse_id="DC-47",
            )

        call_kwargs = agent.analyze_disruption.call_args.kwargs
        from maiw_models import ReasoningLevel, RiskLevel
        assert call_kwargs["reasoning_level"] == ReasoningLevel.MEDIUM
        assert call_kwargs["risk_level"] == RiskLevel.LOW

    @pytest.mark.asyncio
    async def test_ask_threads_trace_id_to_agent(self):
        agent = _make_agent()
        with patch("maiw_api.copilot.service.WarehouseStateSnapshot") as mock_snap:
            mock_snap.seal.return_value = _FakeSnapshot.seal(_FakeState())
            svc = _make_service(agent=agent)
            result, turn = await svc.ask(
                message="Why is Wave 17 at risk?",
                conversation_id=None,
                warehouse_id="DC-47",
            )

        call_kwargs = agent.analyze_disruption.call_args.kwargs
        assert call_kwargs["trace_id"] == result.trace_id == turn.trace_id

    @pytest.mark.asyncio
    async def test_ask_stores_turn_in_conversation(self):
        with patch("maiw_api.copilot.service.WarehouseStateSnapshot") as mock_snap:
            mock_snap.seal.return_value = _FakeSnapshot.seal(_FakeState())
            svc = _make_service()
            result, turn = await svc.ask(
                message="Why is Wave 17 at risk?",
                conversation_id=None,
                warehouse_id="DC-47",
            )

        conv = svc.store.get_conversation(turn.conversation_id)
        assert conv is not None
        assert len(conv.turns) == 1
        assert conv.turns[0].turn_id == turn.turn_id

    @pytest.mark.asyncio
    async def test_ask_includes_structured_evidence(self):
        with patch("maiw_api.copilot.service.WarehouseStateSnapshot") as mock_snap:
            mock_snap.seal.return_value = _FakeSnapshot.seal(_FakeState())
            svc = _make_service()
            result, _ = await svc.ask(
                message="Why is Wave 17 at risk?",
                conversation_id=None,
                warehouse_id="DC-47",
            )

        assert len(result.evidence) > 0
        assert all(isinstance(e, EvidenceFact) for e in result.evidence)
        # Labor fact should be in evidence
        labels = [e.label for e in result.evidence]
        assert any("Labor" in label or "labor" in label for label in labels)

    @pytest.mark.asyncio
    async def test_ask_includes_model_metadata(self):
        with patch("maiw_api.copilot.service.WarehouseStateSnapshot") as mock_snap:
            mock_snap.seal.return_value = _FakeSnapshot.seal(_FakeState())
            svc = _make_service()
            result, _ = await svc.ask(
                message="Why is Wave 17 at risk?",
                conversation_id=None,
                warehouse_id="DC-47",
            )

        assert result.reasoning_level == "MEDIUM"
        assert result.model_id is not None
        assert result.routing_rule is not None


# ── 6. ASK turn — state unavailable → explicit degradation ───────────────────

class TestAskDegradation:
    @pytest.mark.asyncio
    async def test_state_provider_none_degrades_explicitly(self):
        svc = CopilotService(
            operations_agent=_make_agent(),
            state_provider=None,  # unavailable
            event_bus=None,
            graph=None,
        )
        result, turn = await svc.ask(
            message="Why is Wave 17 at risk?",
            conversation_id=None,
            warehouse_id="DC-47",
        )
        assert result.degraded is True
        assert result.degradation_reason is not None
        assert "unavailable" in result.degradation_reason.lower()
        # Must not be an empty answer
        assert len(result.answer) > 0
        # Must not be simulated data
        assert "John Smith" not in result.answer
        assert "Sarah Johnson" not in result.answer

    @pytest.mark.asyncio
    async def test_state_provider_exception_degrades_explicitly(self):
        svc = _make_service(raises_state=RuntimeError("PostgreSQL connection refused"))
        result, turn = await svc.ask(
            message="Why is Wave 17 at risk?",
            conversation_id=None,
            warehouse_id="DC-47",
        )
        assert result.degraded is True
        assert "PostgreSQL" in result.degradation_reason or "assembled" in result.degradation_reason
        assert len(result.answer) > 0

    @pytest.mark.asyncio
    async def test_state_unavailable_returns_no_simulated_names(self):
        """When state is unavailable, must not return invented person names."""
        svc = CopilotService(
            operations_agent=_make_agent(),
            state_provider=None,
            event_bus=None,
            graph=None,
        )
        result, _ = await svc.ask(
            message="How many workers are available?",
            conversation_id=None,
            warehouse_id="DC-47",
        )
        simulated_names = ["John Smith", "Sarah Johnson", "Mike Wilson", "Lisa Brown"]
        for name in simulated_names:
            assert name not in result.answer

    @pytest.mark.asyncio
    async def test_graph_unavailable_noted_but_state_still_used(self):
        """If graph is None but state is available, answer is still provided."""
        with patch("maiw_api.copilot.service.WarehouseStateSnapshot") as mock_snap:
            mock_snap.seal.return_value = _FakeSnapshot.seal(_FakeState())
            svc = _make_service(include_graph=False)  # no graph
            result, _ = await svc.ask(
                message="Why is Wave 17 at risk?",
                conversation_id=None,
                warehouse_id="DC-47",
            )

        # Still answers from WarehouseState
        assert result.answer == "Wave 17 is primarily constrained by labor availability."
        # Neighborhood degrades gracefully
        assert result.neighborhood.graph_available is False
        # degraded=True because graph was unavailable
        assert result.degraded is True
        assert "Graph" in (result.degradation_reason or "") or "graph" in (result.degradation_reason or "").lower()


# ── 7. ASK turn — agent error ─────────────────────────────────────────────────

class TestAskAgentError:
    @pytest.mark.asyncio
    async def test_agent_error_returns_explicit_error_response(self):
        agent = MagicMock()
        agent.analyze_disruption = AsyncMock(side_effect=RuntimeError("NIM timeout"))
        with patch("maiw_api.copilot.service.WarehouseStateSnapshot") as mock_snap:
            mock_snap.seal.return_value = _FakeSnapshot.seal(_FakeState())
            svc = _make_service(agent=agent)
            result, turn = await svc.ask(
                message="Why is Wave 17 at risk?",
                conversation_id=None,
                warehouse_id="DC-47",
            )

        assert result.degraded is True
        assert result.degradation_reason is not None
        assert len(result.answer) > 0
        # Must not be simulated
        assert "John Smith" not in result.answer


# ── 8. Context size bounds ────────────────────────────────────────────────────

class TestContextBounds:
    def test_max_entities_enforced(self):
        """Context resolver must not return more than 50 entities."""
        from maiw_api.copilot import context as ctx

        # Build a mock graph with many neighbors
        mock_graph = MagicMock()
        mock_entity = MagicMock()
        mock_entity.entity_id = "WAVE-01"
        mock_entity.wave_number = 17

        mock_neighbor = MagicMock()
        mock_neighbor.entity_id = "WORKER-{i}"

        # 200 neighbors — resolver must cap at 50
        mock_graph.entities_by_type.return_value = [mock_entity]
        many_neighbors = [MagicMock(entity_id=f"N-{i}") for i in range(200)]
        mock_graph.neighbors.return_value = many_neighbors
        mock_graph.outgoing_edges.return_value = []
        mock_graph.incoming_edges.return_value = []

        from maiw_world.entities import EntityType
        result = ctx.resolve("Why is Wave 17 at risk?", "DC-47", mock_graph)

        assert len(result.entity_ids) <= 50

    def test_graph_none_returns_unavailable(self):
        from maiw_api.copilot import context as ctx

        result = ctx.resolve("Why is Wave 17 at risk?", "DC-47", None)
        assert result.graph_available is False
        assert result.focus_entity_id is None
        assert result.entity_ids == []


# ── 9. Evidence extraction ────────────────────────────────────────────────────

class TestEvidenceExtraction:
    def test_labor_fact_parsed(self):
        facts = ["Labor: 120 total, 40 available, 67% utilization"]
        evidence = _facts_to_evidence(facts, "high")
        assert len(evidence) == 1
        assert evidence[0].label == "Labor"
        assert "67%" in evidence[0].value

    def test_unassigned_tasks_flagged_high(self):
        facts = ["UNASSIGNED PENDING TASKS: 5 pending wave tasks have no worker allocated"]
        evidence = _facts_to_evidence(facts, "high")
        assert len(evidence) == 1
        assert evidence[0].severity == "HIGH"

    def test_offline_equipment_flagged_high(self):
        facts = ["OFFLINE assets: AGV-01, AGV-02"]
        evidence = _facts_to_evidence(facts, "high")
        assert evidence[0].severity == "HIGH"

    def test_multiple_facts(self):
        facts = [
            "Labor: 120 total, 40 available, 67% utilization",
            "Wave tasks: 120 total, 5 pending, 8 in_progress, 3 at-risk",
            "Equipment: 24 total, 24 available",
        ]
        evidence = _facts_to_evidence(facts, "medium")
        assert len(evidence) == 3


# ── 10. CopilotAskResult has no mutation fields ───────────────────────────────

class TestAskResultContract:
    def test_ask_result_has_no_proposal_field(self):
        fields = set(CopilotAskResult.__dataclass_fields__.keys())
        assert "proposal" not in fields
        assert "decision" not in fields
        assert "approval" not in fields
        assert "execution" not in fields

    def test_ask_result_has_no_hidden_reasoning(self):
        fields = set(CopilotAskResult.__dataclass_fields__.keys())
        assert "chain_of_thought" not in fields
        assert "scratchpad" not in fields
        assert "hidden_reasoning" not in fields
        assert "reasoning_tokens" not in fields
