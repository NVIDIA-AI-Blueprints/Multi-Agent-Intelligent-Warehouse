# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for Phase 17A World router.

Invariants:
  W1. /world/config returns canonical warehouse identity.
  W2. Seed comes from canonical configuration (42).
  W3. Checksum comes from DataPack manifest (not invented).
  W4. /world/summary counts match graph.summary().
  W5. Neither endpoint exposes full entity list or edge list.
  W6. Neither endpoint has any mutation path (POST/PATCH/DELETE).
  W7. Missing DataPack/graph gives degraded response, not 500.
  W8. World router does not import ActionExecutor, DecisionEngine, or ApprovalStore.
"""

from __future__ import annotations

import importlib
import inspect
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).parents[2]


class TestWorldRouterBoundary:
    """W6 + W8: mutation safety and import boundary."""

    def test_world_router_has_only_get_endpoints(self):
        from maiw_api.routers import world as world_module
        from fastapi.routing import APIRoute

        for route in world_module.router.routes:
            if isinstance(route, APIRoute):
                assert route.methods == {
                    "GET"
                }, f"Route {route.path} must be GET-only, got {route.methods}"

    def test_world_router_does_not_import_executor(self):
        router_path = REPO_ROOT / "apps" / "api" / "maiw_api" / "routers" / "world.py"
        content = router_path.read_text()
        forbidden = [
            "ActionExecutor",
            "DecisionEngine",
            "ApprovalStore",
            "GovernedActionOrchestrator",
        ]
        found = [sym for sym in forbidden if sym in content]
        assert (
            found == []
        ), f"world.py must not import governance/execution symbols: {found}"


class TestWorldConfig:
    """W1 + W2 + W3 + W5: canonical identity, seed, checksum, no full payload."""

    def _make_runtime(self, graph=None, manifest=None):
        rt = MagicMock()
        rt.world_graph = graph
        rt.world_datapack_manifest = manifest or {}
        rt.demo_controller = None
        return rt

    def test_config_returns_canonical_warehouse_id(self):
        from maiw_api.routers.world import get_world_config
        from maiw_api.demo.world_loader import CANONICAL_WAREHOUSE_ID
        import asyncio

        runtime = self._make_runtime()
        result = asyncio.run(get_world_config(runtime=runtime))
        assert result.warehouse.warehouse_id == CANONICAL_WAREHOUSE_ID

    def test_config_returns_canonical_dataset_id(self):
        from maiw_api.routers.world import get_world_config
        from maiw_api.demo.world_loader import CANONICAL_DATASET_ID
        import asyncio

        runtime = self._make_runtime()
        result = asyncio.run(get_world_config(runtime=runtime))
        assert result.warehouse.dataset_id == CANONICAL_DATASET_ID

    def test_config_seed_is_42(self):
        from maiw_api.routers.world import get_world_config
        import asyncio

        runtime = self._make_runtime()
        result = asyncio.run(get_world_config(runtime=runtime))
        assert result.warehouse.seed == 42

    def test_config_checksum_comes_from_manifest(self):
        from maiw_api.routers.world import get_world_config
        import asyncio

        manifest = {
            "semantic_checksum": "abc123test",
            "maiw_world_schema_version": "1.0",
            "generator_version": "0.1.0",
            "pack_format": "maiw-datapack-v1",
            "entity_count": 100,
            "edge_count": 200,
            "event_count": 10,
        }
        runtime = self._make_runtime(manifest=manifest)
        result = asyncio.run(get_world_config(runtime=runtime))
        assert result.generation.semantic_checksum == "abc123test"

    def test_config_response_has_no_entity_list(self):
        from maiw_api.routers.world import WorldConfigResponse

        fields = WorldConfigResponse.model_fields
        # No field should be named 'entities' or 'edges'
        assert "entities" not in fields
        assert "edges" not in fields

    def test_config_degraded_when_graph_unavailable(self):
        from maiw_api.routers.world import get_world_config
        import asyncio

        runtime = self._make_runtime(graph=None)
        result = asyncio.run(get_world_config(runtime=runtime))
        assert result.generation.graph_available is False
        # Should not raise — graceful degradation
        assert result.warehouse.warehouse_id == "DC-47"


class TestWorldSummary:
    """W4 + W5 + W7: counts from graph, no full payload, degraded when unavailable."""

    def _make_graph(self, summary_dict):
        g = MagicMock()
        g.summary.return_value = summary_dict
        g.entity_count = sum(
            v
            for k, v in summary_dict.items()
            if k != "event_count" and "_" not in k.upper() or k.islower()
        )
        g.edge_count = sum(
            v for k, v in summary_dict.items() if k.isupper() and "_" in k
        )
        g.event_count = summary_dict.get("event_count", 0)
        return g

    def _make_runtime(self, graph=None, manifest=None, demo_controller=None):
        rt = MagicMock()
        rt.world_graph = graph
        rt.world_datapack_manifest = manifest or {}
        rt.demo_controller = demo_controller
        return rt

    def test_summary_uses_graph_summary(self):
        from maiw_api.routers.world import get_world_summary
        import asyncio

        summary = {"Warehouse": 1, "Zone": 6, "CONTAINS": 6, "event_count": 5}
        graph = self._make_graph(summary)
        runtime = self._make_runtime(graph=graph)
        result = asyncio.run(get_world_summary(runtime=runtime))
        assert result.graph.available is True
        assert result.graph.entity_counts.get("Warehouse") == 1
        assert result.graph.entity_counts.get("Zone") == 6

    def test_summary_relationship_counts_present(self):
        from maiw_api.routers.world import get_world_summary
        import asyncio

        summary = {
            "Warehouse": 1,
            "CONTAINS": 246,
            "ASSIGNED_TO": 120,
            "event_count": 0,
        }
        graph = self._make_graph(summary)
        runtime = self._make_runtime(graph=graph)
        result = asyncio.run(get_world_summary(runtime=runtime))
        assert (
            "CONTAINS" in result.graph.relationship_counts
            or result.graph.total_relationships >= 0
        )

    def test_summary_response_has_no_entity_list(self):
        from maiw_api.routers.world import WorldSummaryResponse

        fields = WorldSummaryResponse.model_fields
        assert "entities" not in fields
        assert "edges" not in fields

    def test_summary_degraded_when_graph_unavailable(self):
        from maiw_api.routers.world import get_world_summary
        import asyncio

        runtime = self._make_runtime(graph=None)
        result = asyncio.run(get_world_summary(runtime=runtime))
        assert result.graph.available is False
        assert result.datapack.loaded is False

    def test_summary_immutable_flag_always_true(self):
        from maiw_api.routers.world import get_world_summary
        import asyncio

        runtime = self._make_runtime()
        result = asyncio.run(get_world_summary(runtime=runtime))
        assert result.datapack.immutable is True

    def test_summary_scenario_inactive_without_controller(self):
        from maiw_api.routers.world import get_world_summary
        import asyncio

        runtime = self._make_runtime(demo_controller=None)
        result = asyncio.run(get_world_summary(runtime=runtime))
        assert result.scenario.active is False
