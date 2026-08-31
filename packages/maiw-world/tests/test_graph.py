# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for maiw_world.graph.CanonicalWarehouseGraph (20 tests)."""

from datetime import datetime, timezone

import pytest

from maiw_world.edges import RelationshipType, WarehouseEdge
from maiw_world.entities import (
    EntityType,
    Location,
    Order,
    SKU,
    Task,
    TaskType,
    Warehouse,
    Wave,
    Worker,
    Zone,
)
from maiw_world.graph import CanonicalWarehouseGraph
from tests.fixtures import make_tiny_world

_UTC = timezone.utc
_T0 = datetime(2026, 9, 1, 8, 0, 0, tzinfo=_UTC)
_T1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=_UTC)
_T2 = datetime(2026, 9, 1, 12, 0, 0, tzinfo=_UTC)


def _make_simple_graph() -> CanonicalWarehouseGraph:
    """Graph with 1 warehouse and 1 zone."""
    g = CanonicalWarehouseGraph()
    g.add_entity(Warehouse(id="wh-1", name="Test WH"))
    g.add_entity(Zone(id="zone-1", warehouse_id="wh-1", zone_code="A1"))
    return g


# ── 1. Empty graph has zero entities, edges, events ───────────────────────────

def test_empty_graph():
    g = CanonicalWarehouseGraph()
    assert g.entity_count == 0
    assert g.edge_count == 0
    assert g.event_count == 0


# ── 2. add_entity + get_entity round-trips correctly ──────────────────────────

def test_add_get_entity_roundtrip():
    g = CanonicalWarehouseGraph()
    wh = Warehouse(id="wh-1", name="Test Warehouse")
    g.add_entity(wh)
    retrieved = g.get_entity("wh-1")
    assert retrieved is not None
    assert retrieved.id == "wh-1"
    assert retrieved == wh


# ── 3. has_entity returns True for added, False for unknown ───────────────────

def test_has_entity():
    g = CanonicalWarehouseGraph()
    g.add_entity(Warehouse(id="wh-1", name="Test WH"))
    assert g.has_entity("wh-1") is True
    assert g.has_entity("unknown") is False


# ── 4. entities_by_type returns correct subset ────────────────────────────────

def test_entities_by_type():
    g = CanonicalWarehouseGraph()
    g.add_entity(Warehouse(id="wh-1", name="WH 1"))
    g.add_entity(Zone(id="zone-1", warehouse_id="wh-1", zone_code="A1"))
    g.add_entity(Zone(id="zone-2", warehouse_id="wh-1", zone_code="A2"))

    zones = g.entities_by_type(EntityType.ZONE)
    warehouses = g.entities_by_type(EntityType.WAREHOUSE)

    assert len(zones) == 2
    assert len(warehouses) == 1
    assert all(z.entity_type == EntityType.ZONE for z in zones)


# ── 5. Duplicate entity_id raises ValueError ──────────────────────────────────

def test_duplicate_entity_id_raises():
    g = CanonicalWarehouseGraph()
    g.add_entity(Warehouse(id="wh-1", name="WH 1"))
    with pytest.raises(ValueError, match="already exists"):
        g.add_entity(Warehouse(id="wh-1", name="WH Duplicate"))


# ── 6. add_edge with unknown source raises ValueError ─────────────────────────

def test_add_edge_unknown_source_raises():
    g = CanonicalWarehouseGraph()
    g.add_entity(Zone(id="zone-1", warehouse_id="wh-1", zone_code="A1"))
    edge = WarehouseEdge(
        id="e-001",
        source_id="unknown-wh",
        target_id="zone-1",
        relationship_type=RelationshipType.CONTAINS,
    )
    with pytest.raises(ValueError, match="source entity"):
        g.add_edge(edge)


# ── 7. add_edge with unknown target raises ValueError ─────────────────────────

def test_add_edge_unknown_target_raises():
    g = CanonicalWarehouseGraph()
    g.add_entity(Warehouse(id="wh-1", name="WH 1"))
    edge = WarehouseEdge(
        id="e-001",
        source_id="wh-1",
        target_id="unknown-zone",
        relationship_type=RelationshipType.CONTAINS,
    )
    with pytest.raises(ValueError, match="target entity"):
        g.add_edge(edge)


# ── 8. add_edge invalid type combination raises ValueError ────────────────────

def test_add_edge_invalid_type_combination_raises():
    g = CanonicalWarehouseGraph()
    g.add_entity(SKU(id="sku-1", name="Test SKU"))
    g.add_entity(Wave(id="wave-1", wave_number=1))
    edge = WarehouseEdge(
        id="e-bad",
        source_id="sku-1",
        target_id="wave-1",
        relationship_type=RelationshipType.FULFILLS,
    )
    with pytest.raises(ValueError, match="not valid"):
        g.add_edge(edge)


# ── 9. outgoing_edges returns correct edges ───────────────────────────────────

def test_outgoing_edges():
    g = _make_simple_graph()
    g.add_entity(Zone(id="zone-2", warehouse_id="wh-1", zone_code="A2"))
    e1 = WarehouseEdge(id="e-1", source_id="wh-1", target_id="zone-1", relationship_type=RelationshipType.CONTAINS)
    e2 = WarehouseEdge(id="e-2", source_id="wh-1", target_id="zone-2", relationship_type=RelationshipType.CONTAINS)
    g.add_edge(e1)
    g.add_edge(e2)
    out = g.outgoing_edges("wh-1")
    assert len(out) == 2
    assert all(e.source_id == "wh-1" for e in out)


# ── 10. incoming_edges returns correct edges ──────────────────────────────────

def test_incoming_edges():
    g = _make_simple_graph()
    e = WarehouseEdge(id="e-1", source_id="wh-1", target_id="zone-1", relationship_type=RelationshipType.CONTAINS)
    g.add_edge(e)
    inc = g.incoming_edges("zone-1")
    assert len(inc) == 1
    assert inc[0].source_id == "wh-1"


# ── 11. outgoing_edges(relationship_type=...) filters correctly ───────────────

def test_outgoing_edges_filter_by_relationship():
    g = CanonicalWarehouseGraph()
    g.add_entity(Warehouse(id="wh-1", name="WH"))
    g.add_entity(Zone(id="zone-1", warehouse_id="wh-1", zone_code="A1"))
    g.add_entity(Worker(id="w-1", username="alice", full_name="Alice", role="operator"))
    g.add_edge(WarehouseEdge(id="e-z", source_id="wh-1", target_id="zone-1", relationship_type=RelationshipType.CONTAINS))
    g.add_edge(WarehouseEdge(id="e-w", source_id="wh-1", target_id="w-1", relationship_type=RelationshipType.EMPLOYS))

    contains_edges = g.outgoing_edges("wh-1", relationship_type=RelationshipType.CONTAINS)
    assert len(contains_edges) == 1
    assert contains_edges[0].target_id == "zone-1"


# ── 12. neighbors(depth=1) returns direct neighbors only ──────────────────────

def test_neighbors_depth_1():
    g = _make_simple_graph()
    loc = Location(id="loc-1", zone_id="zone-1", aisle="A", bay="01", level="01", location_code="A-01-01")
    g.add_entity(loc)
    g.add_edge(WarehouseEdge(id="e-wz", source_id="wh-1", target_id="zone-1", relationship_type=RelationshipType.CONTAINS))
    g.add_edge(WarehouseEdge(id="e-zl", source_id="zone-1", target_id="loc-1", relationship_type=RelationshipType.CONTAINS))

    neighbors = g.neighbors("wh-1", depth=1)
    neighbor_ids = {n.id for n in neighbors}
    assert "zone-1" in neighbor_ids
    assert "loc-1" not in neighbor_ids  # too deep


# ── 13. neighbors(depth=2) returns 2-hop neighbors ───────────────────────────

def test_neighbors_depth_2():
    g = _make_simple_graph()
    loc = Location(id="loc-1", zone_id="zone-1", aisle="A", bay="01", level="01", location_code="A-01-01")
    g.add_entity(loc)
    g.add_edge(WarehouseEdge(id="e-wz", source_id="wh-1", target_id="zone-1", relationship_type=RelationshipType.CONTAINS))
    g.add_edge(WarehouseEdge(id="e-zl", source_id="zone-1", target_id="loc-1", relationship_type=RelationshipType.CONTAINS))

    neighbors = g.neighbors("wh-1", depth=2)
    neighbor_ids = {n.id for n in neighbors}
    assert "zone-1" in neighbor_ids
    assert "loc-1" in neighbor_ids


# ── 14. neighbors(direction='incoming') traverses incoming edges ──────────────

def test_neighbors_incoming():
    g = _make_simple_graph()
    g.add_edge(WarehouseEdge(id="e-wz", source_id="wh-1", target_id="zone-1", relationship_type=RelationshipType.CONTAINS))

    # From zone-1, incoming direction should find wh-1
    neighbors = g.neighbors("zone-1", direction="incoming")
    neighbor_ids = {n.id for n in neighbors}
    assert "wh-1" in neighbor_ids


# ── 15. neighbors does not return starting entity ─────────────────────────────

def test_neighbors_excludes_start():
    g = _make_simple_graph()
    g.add_edge(WarehouseEdge(id="e-wz", source_id="wh-1", target_id="zone-1", relationship_type=RelationshipType.CONTAINS))

    neighbors = g.neighbors("wh-1", depth=2)
    ids = {n.id for n in neighbors}
    assert "wh-1" not in ids


# ── 16. Temporal outgoing_edges(at=...) excludes expired edges ────────────────

def test_temporal_edge_filtering_excludes_expired():
    g = CanonicalWarehouseGraph()
    g.add_entity(Worker(id="w-1", username="alice", full_name="Alice", role="operator"))
    g.add_entity(Task(id="t-1", task_type=TaskType.PICK))
    expired_edge = WarehouseEdge(
        id="e-expired",
        source_id="w-1",
        target_id="t-1",
        relationship_type=RelationshipType.ASSIGNED_TO,
        valid_from=_T0,
        valid_to=_T1,
    )
    g.add_edge(expired_edge)
    # Query after valid_to
    after = _T2
    active = g.outgoing_edges("w-1", at=after)
    assert len(active) == 0


# ── 17. Temporal outgoing_edges(at=...) includes active edges ─────────────────

def test_temporal_edge_filtering_includes_active():
    g = CanonicalWarehouseGraph()
    g.add_entity(Worker(id="w-1", username="alice", full_name="Alice", role="operator"))
    g.add_entity(Task(id="t-1", task_type=TaskType.PICK))
    active_edge = WarehouseEdge(
        id="e-active",
        source_id="w-1",
        target_id="t-1",
        relationship_type=RelationshipType.ASSIGNED_TO,
        valid_from=_T0,
    )
    g.add_edge(active_edge)
    # Query during valid window
    at = _T1
    active = g.outgoing_edges("w-1", at=at)
    assert len(active) == 1


# ── 18. tiny_world fixture has correct entity count (24) ──────────────────────

def test_tiny_world_entity_count():
    g = make_tiny_world()
    assert g.entity_count == 24


# ── 19. tiny_world: worker-001 neighbors include task-000001 via ASSIGNED_TO ──

def test_tiny_world_worker_assigned_to_task():
    g = make_tiny_world()
    at = datetime(2026, 9, 1, 9, 0, 0, tzinfo=_UTC)  # after _T0
    neighbors = g.neighbors(
        "worker-001",
        relationship_type=RelationshipType.ASSIGNED_TO,
        direction="outgoing",
        at=at,
    )
    ids = {n.id for n in neighbors}
    assert "task-000001" in ids


# ── 20. tiny_world: wave-017 fulfills 2 orders (many-to-many) ────────────────

def test_tiny_world_wave_fulfills_multiple_orders():
    g = make_tiny_world()
    fulfills_edges = g.outgoing_edges("wave-017", relationship_type=RelationshipType.FULFILLS)
    order_ids = {e.target_id for e in fulfills_edges}
    assert "order-001" in order_ids
    assert "order-002" in order_ids
    assert len(order_ids) == 2
