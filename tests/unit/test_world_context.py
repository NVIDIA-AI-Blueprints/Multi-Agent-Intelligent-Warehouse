# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 17E — Operational Context Snapshot backend tests.

16 test cases covering:
  C1.  OperationalContextSnapshot model stores all required fields
  C2.  InMemoryCopilotStore.store_context_snapshot indexes by turn_id
  C3.  InMemoryCopilotStore.store_context_snapshot indexes by context_snapshot_id
  C4.  get_context_snapshot_by_turn returns None on miss
  C5.  get_context_snapshot_by_id returns None on miss
  C6.  store.reset() clears context snapshots
  C7.  World router /context/by-turn/{turn_id} returns stored snapshot
  C8.  /context/by-turn/{turn_id} returns 404 when turn_id not present
  C9.  /context/by-turn/{turn_id} is GET-only (no POST/PATCH/DELETE)
  C10. ContextSnapshotNode is frozen (immutable)
  C11. ContextSnapshotEdge is frozen (immutable)
  C12. OperationalContextSnapshot carries datapack_checksum field
  C13. CopilotTurn carries context_snapshot_id field (may be None)
  C14. CopilotTurnResponse carries context_snapshot_id field (may be None)
  C15. World router does not import governance symbols (architecture invariant)
  C16. Two distinct snapshots do not collide in store (separate turn_ids)
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).parents[2]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_snapshot(
    *,
    context_snapshot_id: str = "ctx-snap-0001",
    conversation_id: str = "conv-0001",
    turn_id: str = "turn-0001",
    trace_id: str = "trace-0001",
    warehouse_id: str = "wh-test",
    dataset_id: str = "ds-test",
    datapack_checksum: str = "sha256:abc123",
    warehouse_state_snapshot_id: str | None = "snap-001",
    focus_entity_id: str = "worker-1",
    focus_entity_type: str = "worker",
    focus_label: str = "Alice (Picker)",
    depth: int = 2,
    truncated: bool = False,
):
    from maiw_api.copilot.models import (
        ContextSnapshotEdge,
        ContextSnapshotNode,
        OperationalContextSnapshot,
    )

    nodes = [
        ContextSnapshotNode(
            entity_id=focus_entity_id,
            entity_type=focus_entity_type,
            label=focus_label,
            attributes={"role": "picker", "shift_id": "shift-A"},
        )
    ]
    edges = [
        ContextSnapshotEdge(
            source_id=focus_entity_id,
            target_id="task-1",
            relationship_type="ASSIGNED_TO",
            valid_from="2025-01-01T00:00:00Z",
            valid_to=None,
        )
    ]
    return OperationalContextSnapshot(
        context_snapshot_id=context_snapshot_id,
        conversation_id=conversation_id,
        turn_id=turn_id,
        trace_id=trace_id,
        warehouse_id=warehouse_id,
        dataset_id=dataset_id,
        datapack_checksum=datapack_checksum,
        warehouse_state_snapshot_id=warehouse_state_snapshot_id,
        focus_entity_id=focus_entity_id,
        focus_entity_type=focus_entity_type,
        focus_label=focus_label,
        depth=depth,
        truncated=truncated,
        nodes=nodes,
        edges=edges,
        entity_count=len(nodes),
        relationship_count=len(edges),
        relationship_summary={"Tasks": ["task-1"]},
        captured_at=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# C1. OperationalContextSnapshot model stores all required fields
# ---------------------------------------------------------------------------


class TestOperationalContextSnapshotModel:
    def test_c1_all_required_fields_present(self):
        snap = _make_snapshot()
        assert snap.context_snapshot_id == "ctx-snap-0001"
        assert snap.turn_id == "turn-0001"
        assert snap.trace_id == "trace-0001"
        assert snap.warehouse_id == "wh-test"
        assert snap.dataset_id == "ds-test"
        assert snap.datapack_checksum == "sha256:abc123"
        assert snap.focus_entity_id == "worker-1"
        assert snap.focus_entity_type == "worker"
        assert snap.focus_label == "Alice (Picker)"
        assert snap.depth == 2
        assert snap.truncated is False
        assert snap.entity_count == 1
        assert snap.relationship_count == 1
        assert isinstance(snap.nodes, list)
        assert isinstance(snap.edges, list)
        assert isinstance(snap.relationship_summary, dict)
        assert isinstance(snap.captured_at, str)

    def test_c10_context_snapshot_node_is_frozen(self):
        from maiw_api.copilot.models import ContextSnapshotNode

        node = ContextSnapshotNode(
            entity_id="w1",
            entity_type="worker",
            label="Alice",
            attributes={"role": "picker"},
        )
        with pytest.raises(Exception):
            node.entity_id = "mutated"  # type: ignore[misc]

    def test_c11_context_snapshot_edge_is_frozen(self):
        from maiw_api.copilot.models import ContextSnapshotEdge

        edge = ContextSnapshotEdge(
            source_id="w1",
            target_id="t1",
            relationship_type="ASSIGNED_TO",
            valid_from=None,
            valid_to=None,
        )
        with pytest.raises(Exception):
            edge.source_id = "mutated"  # type: ignore[misc]

    def test_c12_datapack_checksum_field_exists_on_snapshot(self):
        snap = _make_snapshot(datapack_checksum="sha256:deadbeef")
        assert snap.datapack_checksum == "sha256:deadbeef"


# ---------------------------------------------------------------------------
# C2–C6. InMemoryCopilotStore snapshot methods
# ---------------------------------------------------------------------------


class TestInMemoryCopilotStoreSnapshots:
    def test_c2_store_indexes_by_turn_id(self):
        from maiw_api.copilot.store import InMemoryCopilotStore

        store = InMemoryCopilotStore()
        snap = _make_snapshot(turn_id="turn-abc", context_snapshot_id="ctx-abc")
        store.store_context_snapshot(snap)
        result = store.get_context_snapshot_by_turn("turn-abc")
        assert result is snap

    def test_c3_store_indexes_by_context_snapshot_id(self):
        from maiw_api.copilot.store import InMemoryCopilotStore

        store = InMemoryCopilotStore()
        snap = _make_snapshot(turn_id="turn-xyz", context_snapshot_id="ctx-xyz")
        store.store_context_snapshot(snap)
        result = store.get_context_snapshot_by_id("ctx-xyz")
        assert result is snap

    def test_c4_get_by_turn_returns_none_on_miss(self):
        from maiw_api.copilot.store import InMemoryCopilotStore

        store = InMemoryCopilotStore()
        assert store.get_context_snapshot_by_turn("nonexistent-turn-id") is None

    def test_c5_get_by_id_returns_none_on_miss(self):
        from maiw_api.copilot.store import InMemoryCopilotStore

        store = InMemoryCopilotStore()
        assert store.get_context_snapshot_by_id("nonexistent-ctx-id") is None

    def test_c6_reset_clears_context_snapshots(self):
        from maiw_api.copilot.store import InMemoryCopilotStore

        store = InMemoryCopilotStore()
        snap = _make_snapshot(turn_id="turn-reset", context_snapshot_id="ctx-reset")
        store.store_context_snapshot(snap)
        assert store.get_context_snapshot_by_turn("turn-reset") is not None
        store.reset()
        assert store.get_context_snapshot_by_turn("turn-reset") is None
        assert store.get_context_snapshot_by_id("ctx-reset") is None

    def test_c16_two_distinct_snapshots_do_not_collide(self):
        from maiw_api.copilot.store import InMemoryCopilotStore

        store = InMemoryCopilotStore()
        snap_a = _make_snapshot(turn_id="turn-A", context_snapshot_id="ctx-A")
        snap_b = _make_snapshot(turn_id="turn-B", context_snapshot_id="ctx-B")
        store.store_context_snapshot(snap_a)
        store.store_context_snapshot(snap_b)
        assert store.get_context_snapshot_by_turn("turn-A") is snap_a
        assert store.get_context_snapshot_by_turn("turn-B") is snap_b
        assert store.get_context_snapshot_by_id("ctx-A") is snap_a
        assert store.get_context_snapshot_by_id("ctx-B") is snap_b


# ---------------------------------------------------------------------------
# C7–C9. World router /context/by-turn endpoint
# ---------------------------------------------------------------------------


class TestWorldContextByTurnEndpoint:
    def _make_runtime(self, snap=None):
        """Build a minimal runtime mock with copilot_service.store wired."""
        from maiw_api.copilot.store import InMemoryCopilotStore

        store = InMemoryCopilotStore()
        if snap is not None:
            store.store_context_snapshot(snap)
        svc_mock = MagicMock()
        svc_mock.store = store
        runtime_mock = MagicMock()
        runtime_mock.copilot_service = svc_mock
        return runtime_mock

    def test_c7_endpoint_returns_snapshot_for_known_turn(self):
        """C7: endpoint logic returns snapshot when store has the turn_id."""
        import asyncio
        from maiw_api.routers.world import get_context_by_turn
        from fastapi import HTTPException

        snap = _make_snapshot(
            turn_id="turn-known",
            context_snapshot_id="ctx-known",
            focus_label="Bob (Sorter)",
        )
        runtime = self._make_runtime(snap)

        result = asyncio.run(get_context_by_turn(turn_id="turn-known", runtime=runtime))
        assert result.context_snapshot_id == "ctx-known"
        assert result.turn_id == "turn-known"
        assert result.focus_label == "Bob (Sorter)"

    def test_c8_endpoint_returns_404_for_missing_turn(self):
        """C8: endpoint raises HTTPException 404 when turn_id not in store."""
        import asyncio
        from maiw_api.routers.world import get_context_by_turn
        from fastapi import HTTPException

        runtime = self._make_runtime(snap=None)

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                get_context_by_turn(turn_id="nonexistent-turn-id", runtime=runtime)
            )
        assert exc_info.value.status_code == 404

    def test_c9_context_by_turn_endpoint_is_get_only(self):
        from fastapi.routing import APIRoute
        from maiw_api.routers import world as world_module

        context_route = None
        for route in world_module.router.routes:
            if isinstance(route, APIRoute) and "by-turn" in route.path:
                context_route = route
                break
        assert context_route is not None, "Route /context/by-turn/{turn_id} not found"
        assert context_route.methods == {
            "GET"
        }, f"Expected GET-only, got {context_route.methods}"


# ---------------------------------------------------------------------------
# C13–C14. CopilotTurn / CopilotTurnResponse carry context_snapshot_id
# ---------------------------------------------------------------------------


class TestContextSnapshotIdOnTurnModels:
    def test_c13_copilot_turn_has_context_snapshot_id_field(self):
        from maiw_api.copilot.models import CopilotTurn, CopilotIntent
        from datetime import datetime, timezone

        turn = CopilotTurn(
            turn_id="t1",
            conversation_id="c1",
            user_message="Hello",
            intent=CopilotIntent.ASK,
            created_at=datetime.now(timezone.utc),
            trace_id="tr1",
            response_summary="ok",
            context_snapshot_id="ctx-linked",
        )
        assert turn.context_snapshot_id == "ctx-linked"

    def test_c13_copilot_turn_context_snapshot_id_defaults_to_none(self):
        from maiw_api.copilot.models import CopilotTurn, CopilotIntent
        from datetime import datetime, timezone

        turn = CopilotTurn(
            turn_id="t2",
            conversation_id="c2",
            user_message="Hi",
            intent=CopilotIntent.ASK,
            created_at=datetime.now(timezone.utc),
            trace_id="tr2",
            response_summary="ok",
        )
        assert turn.context_snapshot_id is None

    def test_c14_copilot_turn_response_has_context_snapshot_id_field(self):
        from maiw_api.copilot.models import CopilotTurnResponse

        resp = CopilotTurnResponse(
            conversation_id="c1",
            turn_id="t1",
            trace_id="tr1",
            intent="ask",
            status="complete",
            context_snapshot_id="ctx-test",
        )
        assert resp.context_snapshot_id == "ctx-test"

    def test_c14b_copilot_turn_response_context_snapshot_id_defaults_to_none(self):
        from maiw_api.copilot.models import CopilotTurnResponse

        resp = CopilotTurnResponse(
            conversation_id="c1",
            turn_id="t1",
            trace_id="tr1",
            intent="ask",
            status="complete",
        )
        assert resp.context_snapshot_id is None


# ---------------------------------------------------------------------------
# C15. World router import boundary (architecture invariant)
# ---------------------------------------------------------------------------


class TestWorldRouterImportBoundary:
    def test_c15_world_router_does_not_import_governance_symbols(self):
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
