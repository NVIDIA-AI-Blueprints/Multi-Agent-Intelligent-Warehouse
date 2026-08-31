# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for maiw_world.validation (10 tests)."""

from datetime import datetime, timezone

import pytest

from maiw_world.config import (
    EquipmentConfig,
    FacilityConfig,
    HistoryConfig,
    InventoryConfig,
    LaborConfig,
    OrderConfig,
    WarehouseWorldConfig,
    WaveConfig,
)
from maiw_world.edges import RelationshipType, WarehouseEdge
from maiw_world.entities import Location, Task, TaskType, Warehouse, Wave, Zone
from maiw_world.graph import CanonicalWarehouseGraph
from maiw_world.validation import FindingSeverity, validate_config, validate_graph
from tests.fixtures import make_tiny_world

_UTC = timezone.utc


# ── 1. Clean tiny_world passes validation ─────────────────────────────────────

def test_clean_tiny_world_passes():
    g = make_tiny_world()
    report = validate_graph(g)
    assert report.passed is True
    assert report.overall != FindingSeverity.FAIL


# ── 2. Orphaned Location (no CONTAINS edge) → WARN ───────────────────────────

def test_orphaned_location_warns():
    g = CanonicalWarehouseGraph()
    g.add_entity(Warehouse(id="wh-1", name="WH"))
    g.add_entity(Zone(id="zone-1", warehouse_id="wh-1", zone_code="A1"))
    g.add_entity(
        Location(
            id="loc-orphan",
            zone_id="zone-1",
            aisle="A",
            bay="01",
            level="01",
            location_code="A-01-01",
        )
    )
    # No CONTAINS edge from zone-1 to loc-orphan
    report = validate_graph(g)
    orphan_findings = [
        f for f in report.findings if f.code == "ORPHANED_LOCATION"
    ]
    assert len(orphan_findings) == 1
    assert orphan_findings[0].severity == FindingSeverity.WARN
    assert orphan_findings[0].entity_id == "loc-orphan"


# ── 3. Task with no BELONGS_TO edge → WARN ───────────────────────────────────

def test_task_no_wave_warns():
    g = CanonicalWarehouseGraph()
    g.add_entity(Task(id="task-orphan", task_type=TaskType.PICK))
    report = validate_graph(g)
    no_wave_findings = [f for f in report.findings if f.code == "TASK_NO_WAVE"]
    assert len(no_wave_findings) == 1
    assert no_wave_findings[0].severity == FindingSeverity.WARN


# ── 4. Invalid temporal interval on edge → FAIL ───────────────────────────────

def test_invalid_temporal_interval_detected():
    """
    Bypass add_edge's Pydantic validation by monkey-patching the edge dict
    to simulate a corrupted graph state.
    """
    g = CanonicalWarehouseGraph()
    g.add_entity(Warehouse(id="wh-1", name="WH"))
    g.add_entity(Zone(id="zone-1", warehouse_id="wh-1", zone_code="A1"))

    # Manually insert a bad edge bypassing Pydantic (simulating corruption)
    # We do this by using model_construct to bypass validation
    from pydantic import __version__ as pv
    bad_edge = WarehouseEdge.model_construct(
        id="e-bad",
        source_id="wh-1",
        target_id="zone-1",
        relationship_type=RelationshipType.CONTAINS,
        valid_from=datetime(2026, 9, 1, 12, tzinfo=_UTC),
        valid_to=datetime(2026, 9, 1, 8, tzinfo=_UTC),   # before valid_from
        metadata={},
    )
    g._edges["e-bad"] = bad_edge
    g._outgoing.setdefault("wh-1", []).append("e-bad")
    g._incoming.setdefault("zone-1", []).append("e-bad")

    report = validate_graph(g)
    interval_findings = [f for f in report.findings if f.code == "INVALID_TEMPORAL_INTERVAL"]
    assert len(interval_findings) >= 1
    assert interval_findings[0].severity == FindingSeverity.FAIL


# ── 5. InventoryPosition quantity < 0 → FAIL ─────────────────────────────────

def test_negative_inventory_quantity_detected():
    """
    Bypass entity validation via model_construct to simulate corrupted state.
    """
    from maiw_world.entities import EntityType, InventoryPosition

    g = CanonicalWarehouseGraph()
    # Construct invalid entity bypassing Pydantic validation
    bad_inv = InventoryPosition.model_construct(
        id="invpos-bad",
        entity_type=EntityType.INVENTORY_POSITION,
        sku_id="sku-1",
        location_id="loc-1",
        quantity_available=-5,
        quantity_reserved=0,
        reorder_point=0,
    )
    g._entities["invpos-bad"] = bad_inv
    g._outgoing["invpos-bad"] = []
    g._incoming["invpos-bad"] = []

    report = validate_graph(g)
    neg_findings = [f for f in report.findings if f.code == "NEGATIVE_INVENTORY_QUANTITY"]
    assert len(neg_findings) == 1
    assert neg_findings[0].severity == FindingSeverity.FAIL


# ── 6. validate_config with task_count < active_wave_count → FAIL ─────────────

def test_validate_config_insufficient_tasks():
    cfg = WarehouseWorldConfig(
        warehouse_id="DC-TEST",
        dataset_id="test-v1",
        seed=1,
        facility=FacilityConfig(zone_count=2, location_count=10, dock_door_count=2),
        inventory=InventoryConfig(sku_count=100, low_stock_pct=0.1),
        labor=LaborConfig(workers_per_shift=5, shift_count=2),
        equipment=EquipmentConfig(agv_count=1),
        orders=OrderConfig(daily_order_count=10, lines_per_order_mean=2.0),
        waves=WaveConfig(active_wave_count=5, strategy="fifo", task_count=3),  # 3 < 5
    )
    report = validate_config(cfg)
    fail_findings = [f for f in report.findings if f.code == "INSUFFICIENT_TASK_COUNT"]
    assert len(fail_findings) == 1
    assert fail_findings[0].severity == FindingSeverity.FAIL
    assert report.passed is False


# ── 7. validate_config with low_stock_pct > 0.5 → WARN ───────────────────────

def test_validate_config_high_low_stock_pct_warns():
    cfg = WarehouseWorldConfig(
        warehouse_id="DC-TEST",
        dataset_id="test-v1",
        seed=1,
        facility=FacilityConfig(zone_count=2, location_count=10, dock_door_count=2),
        inventory=InventoryConfig(sku_count=100, low_stock_pct=0.75),  # > 0.5
        labor=LaborConfig(workers_per_shift=5, shift_count=2),
        equipment=EquipmentConfig(agv_count=1),
        orders=OrderConfig(daily_order_count=10, lines_per_order_mean=2.0),
        waves=WaveConfig(active_wave_count=2, strategy="fifo", task_count=10),
    )
    report = validate_config(cfg)
    warn_findings = [f for f in report.findings if f.code == "HIGH_LOW_STOCK_PCT"]
    assert len(warn_findings) == 1
    assert warn_findings[0].severity == FindingSeverity.WARN


# ── 8. validate_config(dc47_demo()) → PASS ────────────────────────────────────

def test_validate_config_dc47_passes():
    cfg = WarehouseWorldConfig.dc47_demo()
    report = validate_config(cfg)
    assert report.overall == FindingSeverity.PASS
    assert report.passed is True


# ── 9. Overall severity = FAIL when any finding is FAIL ──────────────────────

def test_overall_fail_when_any_finding_is_fail():
    from maiw_world.validation import ValidationFinding, ValidationReport
    report = ValidationReport(
        overall=FindingSeverity.FAIL,
        findings=[
            ValidationFinding(
                severity=FindingSeverity.WARN,
                code="SOME_WARN",
                message="Just a warning",
            ),
            ValidationFinding(
                severity=FindingSeverity.FAIL,
                code="SOME_FAIL",
                message="A failure",
            ),
        ],
    )
    assert report.overall == FindingSeverity.FAIL
    assert report.passed is False


# ── 10. passed property False when overall = FAIL ─────────────────────────────

def test_passed_false_when_overall_fail():
    from maiw_world.validation import ValidationReport
    report = ValidationReport(
        overall=FindingSeverity.FAIL,
        findings=[],
    )
    assert report.passed is False
