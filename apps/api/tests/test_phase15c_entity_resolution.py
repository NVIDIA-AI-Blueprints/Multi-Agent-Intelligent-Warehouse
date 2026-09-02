# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 15C gate — entity resolution tests.

These tests MUST pass before ANALYZE implementation continues.

Requirements verified:
  1. Wave 17 in dc47_demo DataPack — generator produces wave-017
  2. "Wave 17" resolves to wave-017 (EXACT_ID or EXACT_ATTRIBUTE)
  3. "Wave 999" resolves to NOT_FOUND
  4. "Wave 17" with Wave 17 absent MUST NOT return Wave 1
  5. Intent classifier correctly routes ASK / ANALYZE / ACT
  6. Focus continuity: "what should we do?" inherits prior wave focus
"""

from __future__ import annotations

import pytest

from maiw_api.copilot.context import EntityResolution, MatchType, resolve, resolve_entity
from maiw_api.copilot.intent import classify
from maiw_api.copilot.models import CopilotIntent


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_mock_graph(wave_ids: list[tuple[str, int]]):
    """Build a minimal mock graph with the given (wave_id, wave_number) tuples."""
    from unittest.mock import MagicMock

    class FakeWave:
        def __init__(self, wave_id: str, wave_number: int):
            self.id = wave_id
            self.wave_number = wave_number
            self.entity_type = type("ET", (), {"value": "wave"})()

    waves = [FakeWave(wid, wn) for wid, wn in wave_ids]
    wave_by_id = {w.id: w for w in waves}

    from maiw_world.entities import EntityType

    graph = MagicMock()
    graph.entities_by_type.side_effect = lambda et: waves if et == EntityType.WAVE else []
    graph.get_entity.side_effect = lambda eid: wave_by_id.get(eid)
    graph.neighbors.return_value = []
    graph.outgoing_edges.return_value = []
    graph.incoming_edges.return_value = []
    return graph


# ── 1. DataPack gate: dc47_demo generates wave-017 ───────────────────────────

class TestDc47DemoWaveIdentity:

    def test_dc47_demo_wave_number_start_is_17(self):
        from maiw_world.config import WarehouseWorldConfig
        cfg = WarehouseWorldConfig.dc47_demo()
        assert cfg.waves.wave_number_start == 17

    def test_dc47_demo_generates_wave_017(self):
        from maiw_world.config import WarehouseWorldConfig
        from maiw_world.generator import WarehouseWorldGenerator
        from maiw_world.entities import EntityType

        cfg = WarehouseWorldConfig.dc47_demo()
        result = WarehouseWorldGenerator(cfg).generate()
        waves = result.graph.entities_by_type(EntityType.WAVE)
        wave_ids = [w.id for w in waves]
        wave_numbers = [w.wave_number for w in waves]

        assert "wave-017" in wave_ids, (
            f"dc47_demo DataPack must contain wave-017; found: {wave_ids}"
        )
        assert 17 in wave_numbers

    def test_dc47_demo_does_not_contain_wave_000(self):
        from maiw_world.config import WarehouseWorldConfig
        from maiw_world.generator import WarehouseWorldGenerator
        from maiw_world.entities import EntityType

        cfg = WarehouseWorldConfig.dc47_demo()
        result = WarehouseWorldGenerator(cfg).generate()
        waves = result.graph.entities_by_type(EntityType.WAVE)
        wave_ids = [w.id for w in waves]

        assert "wave-000" not in wave_ids, (
            "dc47_demo should not contain wave-000; wave_number_start=17"
        )

    def test_dc47_demo_primary_wave_is_active(self):
        from maiw_world.config import WarehouseWorldConfig
        from maiw_world.generator import WarehouseWorldGenerator
        from maiw_world.entities import EntityType

        cfg = WarehouseWorldConfig.dc47_demo()
        result = WarehouseWorldGenerator(cfg).generate()
        waves = result.graph.entities_by_type(EntityType.WAVE)
        wave017 = next((w for w in waves if w.id == "wave-017"), None)

        assert wave017 is not None
        assert wave017.status == "active"


# ── 2. Entity resolution: wave present ───────────────────────────────────────

class TestEntityResolutionWavePresent:

    def test_wave_17_resolves_exact_attribute(self):
        """Wave 17 exists → resolves to wave-017 via EXACT_ATTRIBUTE or EXACT_ID."""
        graph = _make_mock_graph([("wave-017", 17), ("wave-018", 18)])
        result = resolve_entity("Why is Wave 17 at risk?", graph)

        assert result.match_type in (MatchType.EXACT_ID, MatchType.EXACT_ATTRIBUTE)
        assert result.resolved_entity_id == "wave-017"
        assert result.entity_type == "wave"

    def test_wave_17_resolve_returns_correct_id(self):
        graph = _make_mock_graph([("wave-017", 17)])
        result = resolve_entity("What should we do about Wave 17?", graph)
        assert result.resolved_entity_id == "wave-017"

    def test_wave_resolution_is_case_insensitive(self):
        graph = _make_mock_graph([("wave-017", 17)])
        result = resolve_entity("why is wave 17 delayed?", graph)
        assert result.resolved_entity_id == "wave-017"

    def test_wave_17_requested_reference_captured(self):
        graph = _make_mock_graph([("wave-017", 17)])
        result = resolve_entity("Wave 17 status?", graph)
        assert "17" in result.requested_reference


# ── 3. Entity resolution: wave NOT found ─────────────────────────────────────

class TestEntityResolutionNotFound:

    def test_wave_999_returns_not_found(self):
        """Wave 999 does not exist → NOT_FOUND; no entity returned."""
        graph = _make_mock_graph([("wave-017", 17), ("wave-018", 18)])
        result = resolve_entity("Why is Wave 999 at risk?", graph)

        assert result.match_type == MatchType.NOT_FOUND
        assert result.resolved_entity_id is None

    def test_wave_17_absent_must_not_return_wave_1(self):
        """
        CRITICAL: Wave 17 requested, Wave 1 present, Wave 17 absent.
        MUST NOT silently substitute Wave 1.
        """
        graph = _make_mock_graph([("wave-001", 1), ("wave-002", 2)])
        result = resolve_entity("Why is Wave 17 at risk?", graph)

        assert result.match_type == MatchType.NOT_FOUND, (
            "When Wave 17 is not in the graph, resolver MUST return NOT_FOUND, "
            "not silently substitute the first available wave."
        )
        assert result.resolved_entity_id != "wave-001"
        assert result.resolved_entity_id is None

    def test_not_found_neighborhood_has_no_focus(self):
        """NOT_FOUND entity → ContextNeighborhood has no focus entity."""
        graph = _make_mock_graph([("wave-001", 1)])
        neighborhood = resolve(
            question="Why is Wave 17 at risk?",
            warehouse_id="DC-47",
            graph=graph,
        )

        assert neighborhood.focus_entity_id is None
        assert neighborhood.graph_available is True  # graph is there; entity just not found

    def test_no_graph_returns_graph_unavailable(self):
        neighborhood = resolve(
            question="Why is Wave 17 at risk?",
            warehouse_id="DC-47",
            graph=None,
        )
        assert neighborhood.graph_available is False
        assert neighborhood.focus_entity_id is None


# ── 4. Focus continuity ───────────────────────────────────────────────────────

class TestFocusContinuity:

    def test_prior_focus_used_when_no_explicit_entity(self):
        """
        "What should we do?" has no explicit wave reference.
        Prior turn's focus (wave-017) should be used.
        """
        graph = _make_mock_graph([("wave-017", 17)])
        neighborhood = resolve(
            question="What should we do?",
            warehouse_id="DC-47",
            graph=graph,
            focus_entity_id="wave-017",
            focus_entity_label="Wave 17",
        )
        assert neighborhood.focus_entity_id == "wave-017"

    def test_explicit_entity_overrides_prior_focus(self):
        """Explicit "Wave 18" overrides a prior focus of wave-017."""
        graph = _make_mock_graph([("wave-017", 17), ("wave-018", 18)])
        neighborhood = resolve(
            question="What about Wave 18?",
            warehouse_id="DC-47",
            graph=graph,
            focus_entity_id="wave-017",
            focus_entity_label="Wave 17",
        )
        # Explicit reference should win
        assert neighborhood.focus_entity_id == "wave-018"

    def test_prior_focus_not_found_in_graph_returns_none(self):
        """Prior focus entity no longer in graph → no focus."""
        graph = _make_mock_graph([("wave-017", 17)])
        neighborhood = resolve(
            question="What should we do?",
            warehouse_id="DC-47",
            graph=graph,
            focus_entity_id="wave-999",  # doesn't exist
            focus_entity_label="Wave 999",
        )
        assert neighborhood.focus_entity_id is None


# ── 5. Intent classifier ──────────────────────────────────────────────────────

class TestIntentClassifier:

    @pytest.mark.parametrize("message", [
        "Why is Wave 17 at risk?",
        "What happened to the carrier cutoff?",
        "How many workers are idle?",
        "Which tasks are blocked?",
        "What is the current status of Wave 17?",
        "Show me the labor shortage details.",
    ])
    def test_explanation_questions_are_ask(self, message: str):
        assert classify(message) == CopilotIntent.ASK

    @pytest.mark.parametrize("message", [
        "What should we do?",
        "What do you recommend?",
        "How should we respond to this risk?",
        "What's the best action here?",
        "Can you recommend a course of action?",
        "How can we reduce the risk?",
        "What actions should we take?",
        "How should we protect this wave?",
        "What should I do about Wave 17?",
        "What are our options?",
    ])
    def test_recommendation_questions_are_analyze(self, message: str):
        assert classify(message) == CopilotIntent.ANALYZE

    @pytest.mark.parametrize("message", [
        "Do it.",
        "Execute the recommendation.",
        "Allocate the workers now.",
        "Confirm and proceed.",
        "Go ahead and reprioritize.",
        "Apply the fix.",
    ])
    def test_operational_commands_are_act(self, message: str):
        assert classify(message) == CopilotIntent.ACT

    def test_analyze_wins_over_ask_on_recommend_keyword(self):
        assert classify("Can you recommend what we should do?") == CopilotIntent.ANALYZE

    def test_act_wins_over_analyze_on_execute_keyword(self):
        assert classify("Execute the recommendation please") == CopilotIntent.ACT


# ── 6. Architecture invariants (ANALYZE must not cross trust boundary) ────────

class TestAnalyzeArchitectureInvariants:

    def test_copilot_service_does_not_import_action_executor(self):
        import ast
        import pathlib
        src = pathlib.Path("apps/api/maiw_api/copilot/service.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [
                    alias.name for alias in getattr(node, "names", [])
                ]
                module = getattr(node, "module", "") or ""
                full = module + " " + " ".join(names)
                assert "ActionExecutor" not in full, (
                    "CopilotService MUST NOT import ActionExecutor"
                )
                assert "ApprovalStore" not in full, (
                    "CopilotService MUST NOT import ApprovalStore"
                )
                assert "DecisionEngine" not in full, (
                    "CopilotService MUST NOT import DecisionEngine"
                )

    def test_copilot_router_does_not_expose_approve_or_execute(self):
        import ast, pathlib
        src = pathlib.Path("apps/api/maiw_api/routers/copilot.py").read_text()
        tree = ast.parse(src)
        # Check that no route decorator targets these paths
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for dec in node.decorator_list:
                    dec_src = ast.unparse(dec)
                    assert "/approve" not in dec_src, "Router MUST NOT expose /approve"
                    assert "/execute" not in dec_src, "Router MUST NOT expose /execute"
                    assert "/force-action" not in dec_src, "Router MUST NOT expose /force-action"

    def test_copilot_analyze_result_has_no_proposal_fields(self):
        from maiw_api.copilot.models import CopilotAnalyzeResult
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(CopilotAnalyzeResult)}
        forbidden = {"proposal_id", "decision_id", "approval_id", "execution_id", "proposal"}
        overlap = forbidden & field_names
        assert not overlap, (
            f"CopilotAnalyzeResult must not contain proposal/decision/approval/execution "
            f"fields; found: {overlap}"
        )

    def test_recommended_action_result_has_no_proposal_fields(self):
        from maiw_api.copilot.models import RecommendedActionResult
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(RecommendedActionResult)}
        forbidden = {"proposal_id", "decision_id", "approval_id", "execution_id"}
        overlap = forbidden & field_names
        assert not overlap, (
            f"RecommendedActionResult must not contain proposal/decision/approval/execution "
            f"fields; found: {overlap}"
        )
