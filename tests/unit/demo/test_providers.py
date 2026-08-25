# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for SimulationProvider implementations."""

import asyncio
import pytest

from maiw_api.demo.events import ScenarioEventBus
from maiw_api.demo.world import DemoWarehouseWorld
from maiw_api.demo.providers.inventory import SimulationInventoryProvider
from maiw_api.demo.providers.equipment import SimulationEquipmentProvider
from maiw_api.demo.providers.labor import SimulationLaborProvider
from maiw_api.demo.providers.wave import SimulationWaveProvider
from maiw_mcp.contracts.inventory import InventoryLookupRequest
from maiw_mcp.contracts.equipment import (
    EquipmentStatusRequest,
    EquipmentExecuteAssignRequest,
)
from maiw_mcp.contracts.labor import LaborCapacityRequest, LaborAllocateRequest
from maiw_mcp.contracts.wave import WaveRiskRequest, WaveReprioritizeRequest
from maiw_mcp.errors import BackendUnavailable

_STATE = {
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
            "battery_pct": 85.0,
        }
    ],
    "workers": [
        {
            "worker_id": "w-001",
            "username": "alice",
            "full_name": "Alice Smith",
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


@pytest.fixture
def world():
    w = DemoWarehouseWorld()
    w.seed(_STATE)
    return w


@pytest.fixture
def bus():
    return ScenarioEventBus()


# ── SimulationInventoryProvider ───────────────────────────────────────────────


class TestSimulationInventoryProvider:
    def test_get_inventory_known_sku(self, world):
        provider = SimulationInventoryProvider(world)
        req = InventoryLookupRequest(sku="SKU-001")
        result = asyncio.get_event_loop().run_until_complete(
            provider.get_inventory(req)
        )
        assert result.sku == "SKU-001"
        assert result.total_available == 100
        assert result.warehouse_id == "DC-47"
        assert result.source == "simulation"
        assert not result.is_low_stock

    def test_get_inventory_low_stock(self, world):
        world.inventory["SKU-001"].quantity_available = 15
        provider = SimulationInventoryProvider(world)
        req = InventoryLookupRequest(sku="SKU-001")
        result = asyncio.get_event_loop().run_until_complete(
            provider.get_inventory(req)
        )
        assert result.is_low_stock

    def test_get_inventory_unknown_sku_raises(self, world):
        provider = SimulationInventoryProvider(world)
        req = InventoryLookupRequest(sku="SKU-MISSING")
        with pytest.raises(BackendUnavailable):
            asyncio.get_event_loop().run_until_complete(provider.get_inventory(req))

    def test_get_inventory_observed_at_matches_clock(self, world):
        provider = SimulationInventoryProvider(world)
        req = InventoryLookupRequest(sku="SKU-001")
        result = asyncio.get_event_loop().run_until_complete(
            provider.get_inventory(req)
        )
        assert result.observed_at == world.clock.now()


# ── SimulationEquipmentProvider ───────────────────────────────────────────────


class TestSimulationEquipmentProvider:
    def test_get_equipment_status_all(self, world, bus):
        provider = SimulationEquipmentProvider(world, bus)
        req = EquipmentStatusRequest()
        result = asyncio.get_event_loop().run_until_complete(
            provider.get_equipment_status(req)
        )
        assert result.total_count == 1
        assert result.equipment[0].asset_id == "AGV-01"
        assert result.source == "simulation"

    def test_get_equipment_status_filter_by_id(self, world, bus):
        provider = SimulationEquipmentProvider(world, bus)
        req = EquipmentStatusRequest(asset_id="AGV-01")
        result = asyncio.get_event_loop().run_until_complete(
            provider.get_equipment_status(req)
        )
        assert result.total_count == 1

    def test_get_equipment_status_unknown_id_raises(self, world, bus):
        provider = SimulationEquipmentProvider(world, bus)
        req = EquipmentStatusRequest(asset_id="MISSING")
        with pytest.raises(BackendUnavailable):
            asyncio.get_event_loop().run_until_complete(
                provider.get_equipment_status(req)
            )

    def test_get_equipment_metadata_has_battery(self, world, bus):
        provider = SimulationEquipmentProvider(world, bus)
        req = EquipmentStatusRequest(asset_id="AGV-01")
        result = asyncio.get_event_loop().run_until_complete(
            provider.get_equipment_status(req)
        )
        assert result.equipment[0].metadata["battery_pct"] == 85.0

    def test_execute_equipment_assignment_mutates_world(self, world, bus):
        provider = SimulationEquipmentProvider(world, bus)
        req = EquipmentExecuteAssignRequest(
            asset_id="AGV-01",
            assignee="alice",
            proposal_id="prop-1",
            decision_id="dec-1",
        )
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(provider.execute_equipment_assignment(req))
        finally:
            loop.close()
        assert result.success
        assert world.equipment["AGV-01"].status == "assigned"
        assert world.equipment["AGV-01"].owner_user == "alice"

    def test_execute_assignment_unknown_asset_raises(self, world, bus):
        provider = SimulationEquipmentProvider(world, bus)
        req = EquipmentExecuteAssignRequest(
            asset_id="MISSING",
            assignee="alice",
            proposal_id="prop-1",
            decision_id="dec-1",
        )
        with pytest.raises(BackendUnavailable):
            asyncio.get_event_loop().run_until_complete(
                provider.execute_equipment_assignment(req)
            )


# ── SimulationLaborProvider ───────────────────────────────────────────────────


class TestSimulationLaborProvider:
    def test_get_labor_capacity(self, world, bus):
        provider = SimulationLaborProvider(world, bus)
        req = LaborCapacityRequest()
        result = asyncio.get_event_loop().run_until_complete(
            provider.get_labor_capacity(req)
        )
        assert result.total_workers == 1
        assert result.available_workers == 1
        assert result.source == "simulation"

    def test_get_labor_capacity_zone_filter(self, world, bus):
        provider = SimulationLaborProvider(world, bus)
        req = LaborCapacityRequest(zone="B2")
        result = asyncio.get_event_loop().run_until_complete(
            provider.get_labor_capacity(req)
        )
        assert result.total_workers == 0

    def test_execute_labor_allocation_mutates_world(self, world, bus):
        provider = SimulationLaborProvider(world, bus)
        req = LaborAllocateRequest(
            warehouse_id="DC-47",
            task_id="t-001",
            task_type="PICK",
            worker_ids=["w-001"],
            proposal_id="prop-1",
            decision_id="dec-1",
        )
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(provider.execute_labor_allocation(req))
        finally:
            loop.close()
        assert result.success
        assert world.tasks["t-001"].status == "in_progress"
        assert world.tasks["t-001"].assigned_to == "w-001"
        assert world.workers["w-001"].current_task_id == "t-001"


# ── SimulationWaveProvider ────────────────────────────────────────────────────


class TestSimulationWaveProvider:
    def test_get_wave_risk_with_unassigned_pending(self, world, bus):
        provider = SimulationWaveProvider(world, bus)
        req = WaveRiskRequest()
        result = asyncio.get_event_loop().run_until_complete(
            provider.get_wave_risk(req)
        )
        assert result.otif_at_risk
        assert result.at_risk_task_count == 1
        assert result.risk_level in ("low", "medium", "high", "critical")

    def test_get_wave_risk_no_risk_when_all_assigned(self, world, bus):
        world.tasks["t-001"].assigned_to = "w-001"
        provider = SimulationWaveProvider(world, bus)
        req = WaveRiskRequest()
        result = asyncio.get_event_loop().run_until_complete(
            provider.get_wave_risk(req)
        )
        assert not result.otif_at_risk
        assert result.risk_level == "none"

    def test_execute_wave_reprioritize_mutates_world(self, world, bus):
        provider = SimulationWaveProvider(world, bus)
        req = WaveReprioritizeRequest(
            warehouse_id="DC-47",
            new_priority="critical",
            proposal_id="prop-1",
            decision_id="dec-1",
        )
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(provider.execute_wave_reprioritize(req))
        finally:
            loop.close()
        assert result.success
        assert result.tasks_updated == 1
        assert world.tasks["t-001"].priority == "critical"

    def test_wave_tasks_excludes_non_wave_types(self, world, bus):
        world.tasks["t-001"].task_type = "CYCLE_COUNT"  # not in _WAVE_TYPES
        provider = SimulationWaveProvider(world, bus)
        req = WaveRiskRequest()
        result = asyncio.get_event_loop().run_until_complete(
            provider.get_wave_risk(req)
        )
        assert result.total_task_count == 0
