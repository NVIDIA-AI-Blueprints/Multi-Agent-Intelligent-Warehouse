# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for maiw_world.edges (10 tests)."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from maiw_world.edges import (
    RELATIONSHIP_COMPATIBILITY,
    RelationshipType,
    WarehouseEdge,
)
from maiw_world.entities import EntityType, Equipment, EquipmentType, Task, TaskType, Warehouse, Wave, Zone
from maiw_world.graph import CanonicalWarehouseGraph

_UTC = timezone.utc
_T0 = datetime(2026, 9, 1, 8, 0, 0, tzinfo=_UTC)
_T1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=_UTC)
_T2 = datetime(2026, 9, 1, 12, 0, 0, tzinfo=_UTC)


def _graph_with_wh_and_zone() -> CanonicalWarehouseGraph:
    g = CanonicalWarehouseGraph()
    g.add_entity(Warehouse(id="wh-1", name="Test WH"))
    g.add_entity(Zone(id="zone-1", warehouse_id="wh-1", zone_code="A1"))
    return g


# ── 1. Valid edge Warehouse→Zone CONTAINS creates without error ────────────────

def test_valid_contains_edge():
    g = _graph_with_wh_and_zone()
    edge = WarehouseEdge(
        id="e-001",
        source_id="wh-1",
        target_id="zone-1",
        relationship_type=RelationshipType.CONTAINS,
    )
    g.add_edge(edge)  # should not raise
    assert g.edge_count == 1


# ── 2. Invalid relationship SKU ASSIGNED_TO Wave raises ValueError ────────────

def test_invalid_relationship_type_raises():
    from maiw_world.entities import SKU
    g = CanonicalWarehouseGraph()
    g.add_entity(SKU(id="sku-1", name="Test SKU"))
    g.add_entity(Wave(id="wave-1", wave_number=1))
    edge = WarehouseEdge(
        id="e-invalid",
        source_id="sku-1",
        target_id="wave-1",
        relationship_type=RelationshipType.ASSIGNED_TO,
    )
    with pytest.raises(ValueError, match="not valid"):
        g.add_edge(edge)


# ── 3. valid_to <= valid_from raises ValidationError ─────────────────────────

def test_invalid_temporal_interval_raises():
    with pytest.raises(ValidationError, match="valid_to"):
        WarehouseEdge(
            id="e-bad",
            source_id="a",
            target_id="b",
            relationship_type=RelationshipType.CONTAINS,
            valid_from=_T1,
            valid_to=_T0,  # before valid_from
        )


# ── 4. valid_to > valid_from is valid ─────────────────────────────────────────

def test_valid_temporal_interval():
    edge = WarehouseEdge(
        id="e-good",
        source_id="a",
        target_id="b",
        relationship_type=RelationshipType.CONTAINS,
        valid_from=_T0,
        valid_to=_T1,
    )
    assert edge.valid_from < edge.valid_to


# ── 5. is_active returns False before valid_from ──────────────────────────────

def test_is_active_before_valid_from():
    edge = WarehouseEdge(
        id="e-temp",
        source_id="a",
        target_id="b",
        relationship_type=RelationshipType.CONTAINS,
        valid_from=_T1,
    )
    before = datetime(2026, 9, 1, 7, 0, 0, tzinfo=_UTC)
    assert edge.is_active(at=before) is False


# ── 6. is_active returns True within valid window ─────────────────────────────

def test_is_active_within_window():
    edge = WarehouseEdge(
        id="e-temp2",
        source_id="a",
        target_id="b",
        relationship_type=RelationshipType.CONTAINS,
        valid_from=_T0,
        valid_to=_T2,
    )
    assert edge.is_active(at=_T1) is True


# ── 7. is_active returns False after valid_to ─────────────────────────────────

def test_is_active_after_valid_to():
    edge = WarehouseEdge(
        id="e-temp3",
        source_id="a",
        target_id="b",
        relationship_type=RelationshipType.CONTAINS,
        valid_from=_T0,
        valid_to=_T1,
    )
    after = datetime(2026, 9, 1, 11, 0, 0, tzinfo=_UTC)
    assert edge.is_active(at=after) is False


# ── 8. Multiple ASSIGNED_TO edges for same task are valid ─────────────────────

def test_multiple_assigned_to_edges_same_task():
    from maiw_world.entities import Worker
    g = CanonicalWarehouseGraph()
    g.add_entity(Worker(id="w-1", username="alice", full_name="Alice", role="operator"))
    g.add_entity(Worker(id="w-2", username="bob", full_name="Bob", role="operator"))
    g.add_entity(Task(id="t-1", task_type=TaskType.PICK))

    e1 = WarehouseEdge(
        id="e-assign-1",
        source_id="w-1",
        target_id="t-1",
        relationship_type=RelationshipType.ASSIGNED_TO,
        valid_from=_T0,
        valid_to=_T1,
    )
    e2 = WarehouseEdge(
        id="e-assign-2",
        source_id="w-2",
        target_id="t-1",
        relationship_type=RelationshipType.ASSIGNED_TO,
        valid_from=_T1,
    )
    g.add_edge(e1)
    g.add_edge(e2)  # multiple ASSIGNED_TO edges should work
    assert g.edge_count == 2


# ── 9. Multiple FULFILLS edges from wave to orders are valid ──────────────────

def test_multiple_fulfills_edges():
    from maiw_world.entities import Order
    g = CanonicalWarehouseGraph()
    g.add_entity(Wave(id="wave-1", wave_number=1))
    g.add_entity(Order(id="order-1", order_reference="ORD-001"))
    g.add_entity(Order(id="order-2", order_reference="ORD-002"))

    e1 = WarehouseEdge(
        id="e-f1",
        source_id="wave-1",
        target_id="order-1",
        relationship_type=RelationshipType.FULFILLS,
    )
    e2 = WarehouseEdge(
        id="e-f2",
        source_id="wave-1",
        target_id="order-2",
        relationship_type=RelationshipType.FULFILLS,
    )
    g.add_edge(e1)
    g.add_edge(e2)
    assert g.edge_count == 2


# ── 10. RELATIONSHIP_COMPATIBILITY contains all 13 relationship types ──────────

def test_relationship_compatibility_completeness():
    expected = set(RelationshipType)
    actual = set(RELATIONSHIP_COMPATIBILITY.keys())
    assert actual == expected, (
        f"Missing relationship types in compatibility matrix: {expected - actual}"
    )
    assert len(actual) == 13
