# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 17C backend tests — Operational Graph inspection API.

Invariants (G1–G18):
  G1.  search returns EXACT_ID for canonical wave ID
  G2.  search resolves "Wave 17" → wave-017 (EXACT_ATTRIBUTE or EXACT_ID)
  G3.  search with entity type keyword returns instances
  G4.  search with unknown query returns empty results (not 404)
  G5.  entity detail returns full attributes for wave-017
  G6.  entity detail returns 404 for unknown ID
  G7.  neighbors depth=1 returns ≤50 entities
  G8.  neighbors depth=2 returns ≤50 entities
  G9.  server clamps max_entities — never exceeds 50
  G10. server clamps max_relationships — never exceeds 100
  G11. truncated=True when available > capped; truncated_from set
  G12. deterministic ordering — same query returns same node order
  G13. scenario annotation present when overlay active
  G14. no full graph serialization — nodes ≤50, edges ≤100
  G15. GET-only routes on router (no mutation methods)
  G16. temporal edge fields present in response
  G17. focus entity has bfs_depth=0 in neighborhood
  G18. relationship summary groups by entity type
"""

from __future__ import annotations

import os
import pytest

os.environ.setdefault("MAIW_WORLD_AUTO_GENERATE", "true")

from unittest.mock import MagicMock
import asyncio

from maiw_api.bootstrap import MAIWRuntime
from maiw_api.demo.world_loader import load_canonical_graph
from maiw_api.routers.world import (
    _graph_search,
    _bounded_bfs,
    _entity_label_full,
    _scenario_affected_map,
    search_graph_entities,
    get_graph_entity,
    get_graph_neighbors,
    router,
)


def run(coro):
    """Run an async endpoint function synchronously in tests."""
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def graph():
    return load_canonical_graph()


@pytest.fixture(scope="module")
def runtime(graph):
    rt = MagicMock(spec=MAIWRuntime)
    rt.world_graph = graph
    rt.world_datapack_manifest = {
        "dataset_id": "dc47-demo-v1",
        "warehouse_id": "DC-47",
        "semantic_checksum": "test-checksum-abc123",
    }
    rt.demo_controller = None
    return rt


# ── G1. Exact ID search ───────────────────────────────────────────────────────


def test_g1_search_exact_id(graph):
    results = _graph_search("wave-017", graph, 10)
    assert len(results) >= 1
    assert results[0].entity_id == "wave-017"
    assert results[0].match_type == "EXACT_ID"


# ── G2. Wave number resolution ────────────────────────────────────────────────


def test_g2_search_wave_17_label(graph):
    results = _graph_search("Wave 17", graph, 10)
    ids = [r.entity_id for r in results]
    assert "wave-017" in ids
    wave = next(r for r in results if r.entity_id == "wave-017")
    assert wave.label == "Wave 17"
    assert wave.match_type in ("EXACT_ID", "EXACT_ATTRIBUTE")


# ── G3. Entity type keyword ───────────────────────────────────────────────────


def test_g3_search_entity_type_keyword(graph):
    results = _graph_search("worker", graph, 5)
    assert len(results) == 5
    for r in results:
        assert r.entity_type == "worker"
        assert r.match_type == "ENTITY_TYPE"


def test_g3_agv_subtype_keyword(graph):
    results = _graph_search("agv", graph, 20)
    assert len(results) >= 1
    for r in results:
        assert r.entity_type == "equipment"


# ── G4. Unknown query → empty (not error) ────────────────────────────────────


def test_g4_unknown_query_empty(graph):
    results = _graph_search("zzz-nonexistent-xyzabc999", graph, 10)
    assert results == []


# ── G5. Entity detail attributes ─────────────────────────────────────────────


def test_g5_entity_detail_wave017(runtime):
    resp = run(get_graph_entity("wave-017", runtime=runtime))
    assert resp.entity_id == "wave-017"
    assert resp.entity_type == "wave"
    assert resp.label == "Wave 17"
    assert "wave_number" in resp.attributes
    assert resp.attributes["wave_number"] == 17
    assert isinstance(resp.incoming_count, int)
    assert isinstance(resp.outgoing_count, int)
    assert resp.scenario_affected is False


# ── G6. Entity detail 404 ────────────────────────────────────────────────────


def test_g6_entity_detail_not_found(runtime):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        run(get_graph_entity("does-not-exist-xyzabc", runtime=runtime))
    assert exc_info.value.status_code == 404


# ── G7. Neighbors depth=1 ≤50 entities ───────────────────────────────────────


def test_g7_neighbors_depth1_capped(runtime):
    resp = run(
        get_graph_neighbors(
            "wave-017", depth=1, max_entities=50, max_relationships=100, runtime=runtime
        )
    )
    assert resp.focus_entity.entity_id == "wave-017"
    assert len(resp.nodes) <= 50
    assert resp.depth == 1


# ── G8. Neighbors depth=2 ≤50 entities ───────────────────────────────────────


def test_g8_neighbors_depth2_capped(runtime):
    resp = run(
        get_graph_neighbors(
            "wave-017", depth=2, max_entities=50, max_relationships=100, runtime=runtime
        )
    )
    assert len(resp.nodes) <= 50
    assert resp.depth == 2


# ── G9. Server clamps max_entities ───────────────────────────────────────────


def test_g9_server_clamps_max_entities(graph):
    capped, total, _ = _bounded_bfs(graph, "wave-017", 2, 50, 100)
    assert len(capped) <= 50
    assert total > 50  # wave-017 has 400 depth-2 neighbors


# ── G10. Server clamps max_relationships ──────────────────────────────────────


def test_g10_server_clamps_max_relationships(graph):
    _, _, edges = _bounded_bfs(graph, "wave-017", 2, 50, 100)
    assert len(edges) <= 100


# ── G11. Truncated flag when available > capped ───────────────────────────────


def test_g11_truncated_flag(runtime):
    resp = run(
        get_graph_neighbors(
            "wave-017", depth=1, max_entities=50, max_relationships=100, runtime=runtime
        )
    )
    assert resp.truncated is True
    assert resp.truncated_from is not None
    assert resp.truncated_from > 50


# ── G12. Deterministic ordering ───────────────────────────────────────────────


def test_g12_deterministic_ordering(graph):
    c1, _, _ = _bounded_bfs(graph, "wave-017", 1, 50, 100)
    c2, _, _ = _bounded_bfs(graph, "wave-017", 1, 50, 100)
    ids1 = [e[0].id for e in c1]
    ids2 = [e[0].id for e in c2]
    assert ids1 == ids2


# ── G13. Scenario annotation with mocked overlay ─────────────────────────────


def test_g13_scenario_annotation(graph):
    mock_ev = MagicMock()
    mock_ev.entity_id = "wave-017"
    mock_ev.kind.value = "WAVE_PRIORITY_BUMP"

    mock_overlay = MagicMock()
    mock_overlay.events = [mock_ev]

    mock_sw = MagicMock()
    mock_sw.overlay = mock_overlay

    mock_world = MagicMock()
    mock_world._scenario_world = mock_sw

    mock_ctrl = MagicMock()
    mock_ctrl.active = True
    mock_ctrl.world = mock_world

    rt = MagicMock(spec=MAIWRuntime)
    rt.world_graph = graph
    rt.world_datapack_manifest = {"dataset_id": "dc47-demo-v1", "warehouse_id": "DC-47"}
    rt.demo_controller = mock_ctrl

    resp = run(
        get_graph_neighbors(
            "wave-017", depth=1, max_entities=50, max_relationships=100, runtime=rt
        )
    )
    assert resp.focus_entity.scenario_affected is True
    assert resp.focus_entity.scenario_severity is not None


# ── G14. No full graph serialization ─────────────────────────────────────────


def test_g14_no_full_graph_serialization(runtime):
    resp = run(
        get_graph_neighbors(
            "wave-017", depth=2, max_entities=50, max_relationships=100, runtime=runtime
        )
    )
    assert len(resp.nodes) <= 50
    assert len(resp.edges) <= 100
    # Never the whole DataPack
    assert resp.entity_count < 1000


# ── G15. GET-only routes ──────────────────────────────────────────────────────


def test_g15_get_only_routes():
    from fastapi.routing import APIRoute

    for route in router.routes:
        if isinstance(route, APIRoute):
            assert route.methods == {
                "GET"
            }, f"Route {route.path} must be GET-only, got {route.methods}"


# ── G16. Temporal edge fields ─────────────────────────────────────────────────


def test_g16_temporal_edge_fields(runtime):
    resp = run(
        get_graph_neighbors(
            "wave-017", depth=1, max_entities=50, max_relationships=100, runtime=runtime
        )
    )
    assert len(resp.edges) > 0
    for edge in resp.edges[:5]:
        assert edge.edge_id
        assert edge.source_id
        assert edge.target_id
        assert edge.relationship_type
        assert isinstance(edge.temporal, bool)
        assert isinstance(edge.active, bool)


# ── G17. Focus entity bfs_depth=0 ────────────────────────────────────────────


def test_g17_focus_entity_bfs_depth_zero(runtime):
    resp = run(
        get_graph_neighbors(
            "wave-017", depth=1, max_entities=50, max_relationships=100, runtime=runtime
        )
    )
    assert resp.focus_entity.bfs_depth == 0
    for node in resp.nodes:
        assert node.bfs_depth >= 1


# ── G18. Relationship summary ─────────────────────────────────────────────────


def test_g18_relationship_summary(runtime):
    resp = run(
        get_graph_neighbors(
            "wave-017", depth=1, max_entities=50, max_relationships=100, runtime=runtime
        )
    )
    assert isinstance(resp.relationship_summary, dict)
    assert len(resp.relationship_summary) > 0
    for group, labels in resp.relationship_summary.items():
        assert isinstance(labels, list)
        assert len(labels) > 0
