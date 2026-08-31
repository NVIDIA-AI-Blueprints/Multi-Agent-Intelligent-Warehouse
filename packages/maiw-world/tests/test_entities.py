# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for maiw_world.entities (10 tests)."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from maiw_world.entities import (
    CarrierCutoff,
    EntityType,
    Equipment,
    EquipmentType,
    InventoryPosition,
    Task,
    TaskStatus,
    TaskType,
    Warehouse,
    Worker,
)
from maiw_world.events import OperationalEventType


# ── 1. Warehouse model has correct entity_type ────────────────────────────────

def test_warehouse_entity_type():
    wh = Warehouse(id="DC-47", name="DC-47 Warehouse")
    assert wh.entity_type == EntityType.WAREHOUSE


# ── 2. Worker is frozen (mutating raises error) ───────────────────────────────

def test_worker_is_frozen():
    w = Worker(
        id="worker-001",
        username="alice",
        full_name="Alice Chen",
        role="operator",
    )
    with pytest.raises(Exception):  # ValidationError or TypeError (frozen model)
        w.username = "bob"  # type: ignore[misc]


# ── 3. Task has no assigned_to field ──────────────────────────────────────────

def test_task_has_no_assigned_to_field():
    task = Task(id="task-001", task_type=TaskType.PICK)
    assert not hasattr(task, "assigned_to"), (
        "Task must not have an assigned_to field — "
        "assignments are expressed as ASSIGNED_TO edges."
    )


# ── 4. InventoryPosition with negative quantity_available raises ValidationError

def test_inventory_position_negative_quantity():
    with pytest.raises(ValidationError, match="quantity_available"):
        InventoryPosition(
            id="invpos-001",
            sku_id="sku-001",
            location_id="loc-001",
            quantity_available=-1,
        )


# ── 5. Each entity type produces unique entity_type value ─────────────────────

def test_entity_type_values_unique():
    values = [et.value for et in EntityType]
    assert len(values) == len(set(values)), "EntityType enum values must be unique"


# ── 6. Equipment with AGV serializes correctly ────────────────────────────────

def test_equipment_agv_serialization():
    eq = Equipment(
        id="agv-001",
        equipment_type=EquipmentType.AGV,
        model="Locus Origin",
        zone_id="zone-A1",
    )
    data = eq.model_dump()
    assert data["equipment_type"] == "agv"
    assert data["entity_type"] == "equipment"
    assert data["id"] == "agv-001"


# ── 7. CarrierCutoff.cutoff_time must be timezone-aware ──────────────────────

def test_carrier_cutoff_naive_datetime_raises():
    with pytest.raises(ValidationError, match="timezone-aware"):
        CarrierCutoff(
            id="cutoff-001",
            carrier="FedEx",
            cutoff_time=datetime(2026, 9, 1, 14, 0, 0),  # naive — no tzinfo
        )


def test_carrier_cutoff_aware_datetime_valid():
    cutoff = CarrierCutoff(
        id="cutoff-001",
        carrier="FedEx",
        cutoff_time=datetime(2026, 9, 1, 14, 0, 0, tzinfo=timezone.utc),
    )
    assert cutoff.cutoff_time.tzinfo is not None


# ── 8. TaskType enum has expected values ──────────────────────────────────────

def test_task_type_enum_values():
    expected = {"PICK", "PACK", "PUTAWAY", "CYCLE_COUNT", "REPLENISHMENT", "INSPECTION"}
    actual = {t.value for t in TaskType}
    assert actual == expected


# ── 9. TaskStatus enum has expected values ────────────────────────────────────

def test_task_status_enum_values():
    expected = {"PENDING", "IN_PROGRESS", "COMPLETED", "BLOCKED"}
    actual = {s.value for s in TaskStatus}
    assert actual == expected


# ── 10. OperationalEventType has all 11 event types ──────────────────────────

def test_operational_event_type_count():
    expected = {
        "WORKER_ABSENCE",
        "WORKER_RETURN",
        "EQUIPMENT_FAILURE",
        "EQUIPMENT_RESTORED",
        "INVENTORY_ADJUSTMENT",
        "TASK_ASSIGNMENT",
        "TASK_COMPLETION",
        "TASK_BLOCKED",
        "WAVE_RELEASE",
        "WAVE_COMPLETION",
        "CARRIER_CUTOFF_MISSED",
    }
    actual = {e.value for e in OperationalEventType}
    assert actual == expected
