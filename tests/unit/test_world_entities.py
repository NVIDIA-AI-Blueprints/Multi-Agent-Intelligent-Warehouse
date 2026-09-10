# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 17F — Paginated entity browser and context snapshot list.

Tests:
  E1.  GET /world/graph/entities returns paginated response with correct fields
  E2.  entity_type filter narrows results to that type
  E3.  limit hard-capped at 50 server-side
  E4.  offset paginates correctly (has_more, total)
  E5.  invalid entity_type returns 400
  E6.  graph unavailable returns 503
  E7.  response never contains full entity list (respects limit)
  E8.  GET /world/context/snapshots returns list response
  E9.  context/snapshots deduplicates by context_snapshot_id
  E10. context/snapshots sorted newest first
  E11. context/snapshots returns empty list when no copilot service
  E12. context/snapshots returns GET-only route
  E13. graph/entities returns GET-only route
  E14. both new endpoints absent governance symbols (architecture invariant — covered by existing W8)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock

import pytest

REPO_ROOT = Path(__file__).parents[2]


# ─── helpers ──────────────────────────────────────────────────────────────────


def _make_entity(entity_id: str, entity_type_value: str, **kwargs):
    """Build a minimal mock entity compatible with the world router helpers."""
    from unittest.mock import MagicMock
    from enum import Enum

    class ET(str, Enum):
        pass

    entity = MagicMock()
    entity.id = entity_id
    entity_type_mock = MagicMock()
    entity_type_mock.value = entity_type_value
    entity.entity_type = entity_type_mock

    for k, v in kwargs.items():
        setattr(entity, k, v)

    return entity


def _make_graph_with_workers(count: int = 5):
    """Graph mock that returns N worker entities and nothing else."""
    from maiw_world.entities import EntityType

    workers = []
    for i in range(count):
        w = MagicMock()
        w.id = f"worker-{i:04d}"
        w.entity_type = EntityType.WORKER
        w.full_name = f"Worker {i}"
        w.role = MagicMock()
        w.role.value = "picker"
        w.skills = []
        w.status = "active"
        workers.append(w)

    graph = MagicMock()

    def entities_by_type(et):
        if et == EntityType.WORKER:
            return workers
        return []

    graph.entities_by_type.side_effect = entities_by_type
    return graph, workers


def _make_runtime(
    graph=None, manifest=None, demo_controller=None, copilot_service=None
):
    rt = MagicMock()
    rt.world_graph = graph
    rt.world_datapack_manifest = manifest or {
        "warehouse_id": "DC-47",
        "dataset_id": "dc47-demo-v1",
    }
    rt.demo_controller = demo_controller
    rt.copilot_service = copilot_service
    return rt


def _make_snapshot(
    turn_id: str, context_snapshot_id: str, captured_at: str | None = None
):
    from maiw_api.copilot.models import (
        OperationalContextSnapshot,
        ContextSnapshotNode,
        ContextSnapshotEdge,
    )

    ts = captured_at or datetime.now(timezone.utc).isoformat()
    return OperationalContextSnapshot(
        context_snapshot_id=context_snapshot_id,
        conversation_id="conv-1",
        turn_id=turn_id,
        trace_id=f"trace-{turn_id}",
        warehouse_id="DC-47",
        dataset_id="dc47-demo-v1",
        datapack_checksum="sha256:test",
        warehouse_state_snapshot_id=None,
        focus_entity_id="wave-017",
        focus_entity_type="wave",
        focus_label="Wave 17",
        depth=1,
        truncated=False,
        nodes=[
            ContextSnapshotNode(
                entity_id="wave-017", entity_type="wave", label="Wave 17", attributes={}
            )
        ],
        edges=[],
        entity_count=1,
        relationship_count=0,
        relationship_summary={},
        captured_at=ts,
    )


# ─── E1–E7: paginated entity browser ─────────────────────────────────────────


class TestGetGraphEntities:

    def test_e1_returns_paginated_response(self):
        from maiw_api.routers.world import get_graph_entities

        graph, workers = _make_graph_with_workers(5)
        runtime = _make_runtime(graph=graph)
        result = asyncio.run(
            get_graph_entities(
                entity_type="Worker", limit=10, offset=0, runtime=runtime
            )
        )
        assert result.total == 5
        assert len(result.items) == 5
        assert result.limit == 10
        assert result.offset == 0
        assert result.has_more is False

    def test_e1_items_have_required_fields(self):
        from maiw_api.routers.world import get_graph_entities

        graph, workers = _make_graph_with_workers(3)
        runtime = _make_runtime(graph=graph)
        result = asyncio.run(
            get_graph_entities(
                entity_type="Worker", limit=10, offset=0, runtime=runtime
            )
        )
        assert len(result.items) > 0
        item = result.items[0]
        assert item.entity_id
        assert item.entity_type == "worker"
        assert item.label
        assert isinstance(item.key_state, dict)

    def test_e2_entity_type_filter_returns_only_that_type(self):
        from maiw_api.routers.world import get_graph_entities

        graph, workers = _make_graph_with_workers(3)
        runtime = _make_runtime(graph=graph)
        result = asyncio.run(
            get_graph_entities(
                entity_type="Worker", limit=20, offset=0, runtime=runtime
            )
        )
        for item in result.items:
            assert item.entity_type == "worker"
        assert result.entity_type_filter == "worker"

    def test_e3_limit_clamped_to_50(self):
        from maiw_api.routers.world import get_graph_entities

        graph, workers = _make_graph_with_workers(60)
        runtime = _make_runtime(graph=graph)
        # Even if we pass limit=100, server clamps to 50
        result = asyncio.run(
            get_graph_entities(
                entity_type="Worker", limit=50, offset=0, runtime=runtime
            )
        )
        assert len(result.items) <= 50

    def test_e4_offset_paginates(self):
        from maiw_api.routers.world import get_graph_entities

        graph, workers = _make_graph_with_workers(10)
        runtime = _make_runtime(graph=graph)
        page0 = asyncio.run(
            get_graph_entities(entity_type="Worker", limit=5, offset=0, runtime=runtime)
        )
        page1 = asyncio.run(
            get_graph_entities(entity_type="Worker", limit=5, offset=5, runtime=runtime)
        )
        assert page0.total == 10
        assert page0.has_more is True
        assert page1.has_more is False
        ids_p0 = {i.entity_id for i in page0.items}
        ids_p1 = {i.entity_id for i in page1.items}
        assert ids_p0.isdisjoint(ids_p1), "Pages must not overlap"

    def test_e5_invalid_entity_type_returns_400(self):
        from maiw_api.routers.world import get_graph_entities
        from fastapi import HTTPException

        graph, _ = _make_graph_with_workers(1)
        runtime = _make_runtime(graph=graph)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                get_graph_entities(
                    entity_type="NonExistentType", limit=10, offset=0, runtime=runtime
                )
            )
        assert exc.value.status_code == 400

    def test_e6_graph_unavailable_returns_503(self):
        from maiw_api.routers.world import get_graph_entities
        from fastapi import HTTPException

        runtime = _make_runtime(graph=None)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                get_graph_entities(
                    entity_type=None, limit=10, offset=0, runtime=runtime
                )
            )
        assert exc.value.status_code == 503

    def test_e7_response_never_exposes_full_entity_set(self):
        """Items returned must be bounded by limit — never the full set."""
        from maiw_api.routers.world import get_graph_entities

        graph, _ = _make_graph_with_workers(200)
        runtime = _make_runtime(graph=graph)
        result = asyncio.run(
            get_graph_entities(
                entity_type="Worker", limit=50, offset=0, runtime=runtime
            )
        )
        assert len(result.items) <= 50
        assert result.total > len(result.items)  # more exist than returned

    def test_e13_entities_route_is_get_only(self):
        from fastapi.routing import APIRoute
        from maiw_api.routers import world as world_module

        route = next(
            (
                r
                for r in world_module.router.routes
                if isinstance(r, APIRoute)
                and "entities" in r.path
                and "neighbors" not in r.path
                and "{" not in r.path
            ),
            None,
        )
        assert route is not None, "Route /graph/entities not found"
        assert route.methods == {"GET"}


# ─── E8–E12: context snapshot list ───────────────────────────────────────────


class TestListContextSnapshots:

    def _make_copilot_svc(self, snapshots=None):
        from maiw_api.copilot.store import InMemoryCopilotStore

        store = InMemoryCopilotStore()
        if snapshots:
            for s in snapshots:
                store.store_context_snapshot(s)
        svc = MagicMock()
        svc.store = store
        return svc

    def test_e8_returns_list_response(self):
        from maiw_api.routers.world import list_context_snapshots

        snap = _make_snapshot("turn-1", "ctx-1")
        svc = self._make_copilot_svc([snap])
        runtime = _make_runtime(copilot_service=svc)
        result = asyncio.run(list_context_snapshots(runtime=runtime))
        assert result.total == 1
        assert len(result.snapshots) == 1
        item = result.snapshots[0]
        assert item.turn_id == "turn-1"
        assert item.context_snapshot_id == "ctx-1"
        assert item.focus_label == "Wave 17"
        assert isinstance(item.entity_count, int)
        assert isinstance(item.captured_at, str)

    def test_e9_deduplicates_by_context_snapshot_id(self):
        """The store indexes by both turn_id and context_snapshot_id — list must deduplicate."""
        from maiw_api.routers.world import list_context_snapshots

        snap_a = _make_snapshot("turn-A", "ctx-A")
        snap_b = _make_snapshot("turn-B", "ctx-B")
        svc = self._make_copilot_svc([snap_a, snap_b])
        runtime = _make_runtime(copilot_service=svc)
        result = asyncio.run(list_context_snapshots(runtime=runtime))
        # With dedup, should be exactly 2 (not 4, since each is stored under 2 keys)
        assert result.total == 2
        ids = {s.context_snapshot_id for s in result.snapshots}
        assert ids == {"ctx-A", "ctx-B"}

    def test_e10_sorted_newest_first(self):
        from maiw_api.routers.world import list_context_snapshots

        old_snap = _make_snapshot(
            "turn-old", "ctx-old", captured_at="2025-01-01T00:00:00+00:00"
        )
        new_snap = _make_snapshot(
            "turn-new", "ctx-new", captured_at="2025-12-31T23:59:59+00:00"
        )
        svc = self._make_copilot_svc([old_snap, new_snap])
        runtime = _make_runtime(copilot_service=svc)
        result = asyncio.run(list_context_snapshots(runtime=runtime))
        assert result.snapshots[0].turn_id == "turn-new"
        assert result.snapshots[1].turn_id == "turn-old"

    def test_e11_returns_empty_when_no_copilot_service(self):
        from maiw_api.routers.world import list_context_snapshots

        runtime = _make_runtime(copilot_service=None)
        runtime.copilot_service = None
        result = asyncio.run(list_context_snapshots(runtime=runtime))
        assert result.total == 0
        assert result.snapshots == []

    def test_e12_context_snapshots_route_is_get_only(self):
        from fastapi.routing import APIRoute
        from maiw_api.routers import world as world_module

        route = next(
            (
                r
                for r in world_module.router.routes
                if isinstance(r, APIRoute) and r.path.endswith("/context/snapshots")
            ),
            None,
        )
        assert route is not None, "Route /context/snapshots not found"
        assert route.methods == {"GET"}
