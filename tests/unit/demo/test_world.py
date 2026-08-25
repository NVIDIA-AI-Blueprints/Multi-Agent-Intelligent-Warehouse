# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for DemoWarehouseWorld and SimulationClock."""

import pytest
from datetime import datetime, timezone

from maiw_api.demo.world import DemoWarehouseWorld, SimulationClock

# ── SimulationClock ───────────────────────────────────────────────────────────


class TestSimulationClock:
    def test_initial_epoch(self):
        clock = SimulationClock()
        assert clock.elapsed_seconds == 0
        assert clock.now() == SimulationClock._EPOCH

    def test_tick_advances(self):
        clock = SimulationClock()
        clock.tick(3600)
        assert clock.elapsed_seconds == 3600

    def test_tick_negative_raises(self):
        clock = SimulationClock()
        with pytest.raises(ValueError):
            clock.tick(-1)

    def test_snapshot_restore(self):
        clock = SimulationClock()
        clock.tick(120)
        snap = clock.snapshot()
        clock.tick(60)
        clock.restore(snap)
        assert clock.elapsed_seconds == 120

    def test_seed_offset(self):
        clock = SimulationClock(seed_seconds=1800)
        assert clock.elapsed_seconds == 1800


# ── DemoWarehouseWorld ────────────────────────────────────────────────────────

_MINIMAL_STATE = {
    "clock_offset_seconds": 0,
    "inventory": [
        {
            "sku": "SKU-001",
            "name": "Widget A",
            "zone": "A1",
            "location_id": "A-01-01",
            "quantity_available": 100,
            "quantity_reserved": 10,
            "reorder_point": 20,
        }
    ],
    "equipment": [
        {
            "asset_id": "AGV-01",
            "equipment_type": "agv",
            "model": "TestAGV",
            "zone": "A1",
            "status": "available",
            "battery_pct": 90.0,
        }
    ],
    "workers": [
        {
            "worker_id": "w-001",
            "username": "alice",
            "full_name": "Alice",
            "role": "operator",
            "status": "active",
            "zone": "A1",
        }
    ],
    "tasks": [
        {
            "task_id": "t-001",
            "task_type": "PICK",
            "zone": "A1",
            "status": "pending",
            "priority": "high",
        }
    ],
}


class TestDemoWarehouseWorld:
    def test_seed_populates_all_domains(self):
        world = DemoWarehouseWorld()
        world.seed(_MINIMAL_STATE)
        assert "SKU-001" in world.inventory
        assert "AGV-01" in world.equipment
        assert "w-001" in world.workers
        assert "t-001" in world.tasks

    def test_seed_clears_previous_state(self):
        world = DemoWarehouseWorld()
        world.seed(_MINIMAL_STATE)
        world.seed({"clock_offset_seconds": 0})  # empty state
        assert len(world.inventory) == 0
        assert len(world.equipment) == 0

    def test_low_stock_detection(self):
        world = DemoWarehouseWorld()
        world.seed(_MINIMAL_STATE)
        item = world.inventory["SKU-001"]
        assert not item.is_low_stock
        item.quantity_available = 15
        assert item.is_low_stock

    def test_snapshot_reset_determinism(self):
        world = DemoWarehouseWorld()
        world.seed(_MINIMAL_STATE)
        snap = world.snapshot()

        world.equipment["AGV-01"].status = "maintenance"
        world.inventory["SKU-001"].quantity_available = 0
        world.tasks["t-001"].status = "completed"

        world.reset(snap)
        assert world.equipment["AGV-01"].status == "available"
        assert world.inventory["SKU-001"].quantity_available == 100
        assert world.tasks["t-001"].status == "pending"

    def test_snapshot_is_deep_copy(self):
        world = DemoWarehouseWorld()
        world.seed(_MINIMAL_STATE)
        snap = world.snapshot()
        # Mutate world after snapshot
        world.equipment["AGV-01"].status = "offline"
        # Snapshot should be unaffected
        assert snap["equipment"]["AGV-01"].status == "available"

    def test_equipment_list_filtering(self):
        world = DemoWarehouseWorld()
        world.seed(_MINIMAL_STATE)
        assert len(world.equipment_list(asset_id="AGV-01")) == 1
        assert len(world.equipment_list(asset_id="MISSING")) == 0
        assert len(world.equipment_list(status_filter="available")) == 1
        assert len(world.equipment_list(status_filter="maintenance")) == 0

    def test_workers_list_filtering(self):
        world = DemoWarehouseWorld()
        world.seed(_MINIMAL_STATE)
        assert len(world.workers_list(zone="A1")) == 1
        assert len(world.workers_list(zone="B1")) == 0

    def test_tasks_list_filtering(self):
        world = DemoWarehouseWorld()
        world.seed(_MINIMAL_STATE)
        assert len(world.tasks_list(status_filter="pending")) == 1
        assert len(world.tasks_list(status_filter="in_progress")) == 0

    def test_status_summary(self):
        world = DemoWarehouseWorld()
        world.seed(_MINIMAL_STATE)
        s = world.status_summary()
        assert s["warehouse_id"] == "DC-47"
        assert s["equipment"]["total"] == 1
        assert s["workers"]["total"] == 1
        assert s["tasks"]["pending"] == 1
        assert s["inventory"]["total_skus"] == 1

    def test_clock_offset_applied(self):
        world = DemoWarehouseWorld()
        state = dict(_MINIMAL_STATE)
        state["clock_offset_seconds"] = 3600
        world.seed(state)
        assert world.clock.elapsed_seconds == 3600
