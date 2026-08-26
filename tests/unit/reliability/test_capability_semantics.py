# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 10E Batch 1 — Provider capability outcome semantics table (Section 12).

Verifies that each provider write method returns the correct canonical outcome
for every defined input state. This is the reference table from the spec.

    Capability                  Input state                         Expected outcome
    ─────────────────────────── ─────────────────────────────────── ────────────
    labor.allocate              task not found                      FAILED (exception)
    labor.allocate              no workers available                DEFERRED
    labor.allocate              task already assigned (same worker) NO_OP
    labor.allocate              new assignment                      EXECUTED

    wave.reprioritize           no tasks in zone                    FAILED (exception)
    wave.reprioritize           all tasks already at priority       NO_OP
    wave.reprioritize           tasks need reprioritization         EXECUTED

    equipment.assign            asset not found                     FAILED (exception)
    equipment.assign            same assignee+task already set      NO_OP
    equipment.assign            assigned to DIFFERENT task          CONFLICT
    equipment.assign            available asset                     EXECUTED

    equipment.release           asset not found                     FAILED (exception)
    equipment.release           already available                   NO_OP
    equipment.release           currently assigned                  EXECUTED

    equipment.maintenance       asset not found                     FAILED (exception)
    equipment.maintenance       already in maintenance              NO_OP
    equipment.maintenance       available/assigned asset            EXECUTED

CONFLICT reaches the provider write (returns outcome="conflict") —
it does NOT raise, so the executor sees CONFLICT, not FAILED.
FAILED is for provider exceptions (task/asset not found, unreachable).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from maiw_mcp.errors import BackendUnavailable


# ── World factory helpers ─────────────────────────────────────────────────────


def _make_labor_world(*, with_task: bool = True, with_worker: bool = True):
    from maiw_api.demo.world import DemoWarehouseWorld, TaskState, WorkerState
    world = DemoWarehouseWorld()
    if with_task:
        world.tasks["T-CAP"] = TaskState(
            task_id="T-CAP", task_type="PICK", zone="ZONE-A",
            status="pending", priority="medium",
        )
    if with_worker:
        world.workers["W-001"] = WorkerState(
            worker_id="W-001", username="worker1", full_name="Worker One",
            role="operator", status="active", zone="ZONE-A",
        )
    bus = MagicMock()
    bus.publish_labor_write = AsyncMock()
    return world, bus


def _make_wave_world(*, num_tasks: int = 2, priority: str = "medium"):
    from maiw_api.demo.world import DemoWarehouseWorld, TaskState
    world = DemoWarehouseWorld()
    for i in range(num_tasks):
        world.tasks[f"T-W{i}"] = TaskState(
            task_id=f"T-W{i}", task_type="PICK", zone="ZONE-A",
            status="pending", priority=priority,
        )
    bus = MagicMock()
    bus.publish_wave_write = AsyncMock()
    return world, bus


def _make_equip_world(*, status: str = "available", owner_user=None, current_task_id=None):
    from maiw_api.demo.world import DemoWarehouseWorld, EquipmentAsset
    world = DemoWarehouseWorld()
    metadata = {}
    if current_task_id:
        metadata["current_task_id"] = current_task_id
    world.equipment["FA-001"] = EquipmentAsset(
        asset_id="FA-001", equipment_type="forklift", model="XR500",
        zone="ZONE-A", status=status, owner_user=owner_user, metadata=metadata,
    )
    bus = MagicMock()
    bus.publish_equipment_write = AsyncMock()
    return world, bus


def _labor_req(**kwargs):
    from maiw_mcp.contracts.labor import LaborAllocateRequest
    defaults = dict(
        warehouse_id="default", task_id="T-CAP", task_type="PICK",
        worker_ids=["W-001"], proposal_id="p-cap", decision_id="d-cap",
        execution_id="exec-cap",
    )
    return LaborAllocateRequest(**{**defaults, **kwargs})


def _wave_req(**kwargs):
    from maiw_mcp.contracts.wave import WaveReprioritizeRequest
    defaults = dict(
        warehouse_id="default", zone="ZONE-A", new_priority="high",
        proposal_id="p-cap", decision_id="d-cap", execution_id="exec-cap",
    )
    return WaveReprioritizeRequest(**{**defaults, **kwargs})


def _assign_req(**kwargs):
    from maiw_mcp.contracts.equipment import EquipmentExecuteAssignRequest
    defaults = dict(
        warehouse_id="default", asset_id="FA-001", assignee="W-001",
        task_id="T-001", proposal_id="p-cap", decision_id="d-cap",
        execution_id="exec-cap",
    )
    return EquipmentExecuteAssignRequest(**{**defaults, **kwargs})


def _release_req(**kwargs):
    from maiw_mcp.contracts.equipment import EquipmentExecuteReleaseRequest
    defaults = dict(
        warehouse_id="default", asset_id="FA-001", released_by="W-001",
        proposal_id="p-cap", decision_id="d-cap", execution_id="exec-cap",
    )
    return EquipmentExecuteReleaseRequest(**{**defaults, **kwargs})


def _maint_req(**kwargs):
    from maiw_mcp.contracts.equipment import EquipmentExecuteMaintenanceRequest
    defaults = dict(
        asset_id="FA-001", maintenance_type="PM", description="Scheduled PM",
        scheduled_for="2026-09-01T08:00:00", scheduled_by="ops-manager",
        proposal_id="p-cap", decision_id="d-cap", execution_id="exec-cap",
    )
    return EquipmentExecuteMaintenanceRequest(**{**defaults, **kwargs})


# ── Labor capability table ────────────────────────────────────────────────────


class TestLaborAllocateSemantics:
    """Reference table for labor.allocate outcomes."""

    def test_task_not_found_raises_backend_unavailable(self):
        """FAILED: task_id not in world → BackendUnavailable raised."""
        world, bus = _make_labor_world(with_task=False)
        from maiw_api.demo.providers.labor import SimulationLaborProvider
        provider = SimulationLaborProvider(world=world, bus=bus)

        with pytest.raises(BackendUnavailable):
            asyncio.run(provider.execute_labor_allocation(_labor_req()))

        assert provider._mutation_count == 0

    def test_no_workers_available_returns_deferred(self):
        """DEFERRED: worker_ids=[] and no idle workers in world."""
        world, bus = _make_labor_world(with_worker=False)
        from maiw_api.demo.providers.labor import SimulationLaborProvider
        provider = SimulationLaborProvider(world=world, bus=bus)

        result = asyncio.run(
            provider.execute_labor_allocation(_labor_req(worker_ids=[]))
        )

        assert result.outcome == "deferred"
        assert result.success is False
        assert provider._mutation_count == 0

    def test_already_assigned_same_worker_returns_no_op(self):
        """NO_OP: task already in_progress assigned to same worker_id."""
        world, bus = _make_labor_world()
        world.tasks["T-CAP"].status = "in_progress"
        world.tasks["T-CAP"].assigned_to = "W-001"
        from maiw_api.demo.providers.labor import SimulationLaborProvider
        provider = SimulationLaborProvider(world=world, bus=bus)

        result = asyncio.run(provider.execute_labor_allocation(_labor_req()))

        assert result.outcome == "no_op"
        assert result.success is True
        assert provider._mutation_count == 0

    def test_new_assignment_returns_executed(self):
        """EXECUTED: valid task + worker → mutation committed."""
        world, bus = _make_labor_world()
        from maiw_api.demo.providers.labor import SimulationLaborProvider
        provider = SimulationLaborProvider(world=world, bus=bus)

        result = asyncio.run(provider.execute_labor_allocation(_labor_req()))

        assert result.outcome == "executed"
        assert result.success is True
        assert provider._mutation_count == 1
        assert world.tasks["T-CAP"].status == "in_progress"
        assert world.tasks["T-CAP"].assigned_to == "W-001"


# ── Wave reprioritize capability table ───────────────────────────────────────


class TestWaveReprioritizeSemantics:
    """Reference table for wave.reprioritize outcomes."""

    def test_no_tasks_in_zone_raises_backend_unavailable(self):
        """FAILED: zone has no tasks → BackendUnavailable raised."""
        world, bus = _make_wave_world(num_tasks=0)
        from maiw_api.demo.providers.wave import SimulationWaveProvider
        provider = SimulationWaveProvider(world=world, bus=bus)

        with pytest.raises(BackendUnavailable):
            asyncio.run(provider.execute_wave_reprioritize(_wave_req()))

        assert provider._mutation_count == 0

    def test_all_already_at_priority_returns_no_op(self):
        """NO_OP: all tasks already have new_priority."""
        world, bus = _make_wave_world(num_tasks=2, priority="high")
        from maiw_api.demo.providers.wave import SimulationWaveProvider
        provider = SimulationWaveProvider(world=world, bus=bus)

        result = asyncio.run(
            provider.execute_wave_reprioritize(_wave_req(new_priority="high"))
        )

        assert result.outcome == "no_op"
        assert result.tasks_updated == 0
        assert provider._mutation_count == 0

    def test_tasks_need_reprioritization_returns_executed(self):
        """EXECUTED: at least one task priority changed."""
        world, bus = _make_wave_world(num_tasks=3, priority="medium")
        from maiw_api.demo.providers.wave import SimulationWaveProvider
        provider = SimulationWaveProvider(world=world, bus=bus)

        result = asyncio.run(
            provider.execute_wave_reprioritize(_wave_req(new_priority="high"))
        )

        assert result.outcome == "executed"
        assert result.tasks_updated == 3
        assert provider._mutation_count == 1


# ── Equipment capability table ────────────────────────────────────────────────


class TestEquipmentAssignSemantics:
    """Reference table for equipment.assign outcomes."""

    def test_asset_not_found_raises_backend_unavailable(self):
        """FAILED: asset_id not in world → BackendUnavailable."""
        world, bus = _make_equip_world()
        world.equipment.clear()
        from maiw_api.demo.providers.equipment import SimulationEquipmentProvider
        provider = SimulationEquipmentProvider(world=world, bus=bus)

        with pytest.raises(BackendUnavailable):
            asyncio.run(provider.execute_equipment_assignment(_assign_req()))

        assert provider._mutation_count == 0

    def test_same_assignee_and_task_already_set_returns_no_op(self):
        """NO_OP: asset.status=assigned, owner_user=W-001, current_task_id=T-001."""
        world, bus = _make_equip_world(
            status="assigned", owner_user="W-001", current_task_id="T-001"
        )
        from maiw_api.demo.providers.equipment import SimulationEquipmentProvider
        provider = SimulationEquipmentProvider(world=world, bus=bus)

        result = asyncio.run(
            provider.execute_equipment_assignment(
                _assign_req(assignee="W-001", task_id="T-001")
            )
        )

        assert result.outcome == "no_op"
        assert result.success is True
        assert provider._mutation_count == 0

    def test_assigned_to_different_task_returns_conflict(self):
        """CONFLICT: asset assigned to T-OTHER, requested T-001."""
        world, bus = _make_equip_world(
            status="assigned", owner_user="W-999", current_task_id="T-OTHER"
        )
        from maiw_api.demo.providers.equipment import SimulationEquipmentProvider
        provider = SimulationEquipmentProvider(world=world, bus=bus)

        result = asyncio.run(
            provider.execute_equipment_assignment(
                _assign_req(task_id="T-001")
            )
        )

        assert result.outcome == "conflict"
        assert result.success is False
        # CONFLICT is returned (not raised) — mutation count = 0
        assert provider._mutation_count == 0

    def test_available_asset_returns_executed(self):
        """EXECUTED: asset available → assign mutation committed."""
        world, bus = _make_equip_world(status="available")
        from maiw_api.demo.providers.equipment import SimulationEquipmentProvider
        provider = SimulationEquipmentProvider(world=world, bus=bus)

        result = asyncio.run(
            provider.execute_equipment_assignment(
                _assign_req(assignee="W-001", task_id="T-001")
            )
        )

        assert result.outcome == "executed"
        assert result.success is True
        assert provider._mutation_count == 1
        assert world.equipment["FA-001"].status == "assigned"
        assert world.equipment["FA-001"].owner_user == "W-001"


class TestEquipmentReleaseSemantics:
    """Reference table for equipment.release outcomes."""

    def test_asset_not_found_raises_backend_unavailable(self):
        world, bus = _make_equip_world()
        world.equipment.clear()
        from maiw_api.demo.providers.equipment import SimulationEquipmentProvider
        provider = SimulationEquipmentProvider(world=world, bus=bus)

        with pytest.raises(BackendUnavailable):
            asyncio.run(provider.execute_equipment_release(_release_req()))

        assert provider._mutation_count == 0

    def test_already_available_returns_no_op(self):
        """NO_OP: asset already available with no owner."""
        world, bus = _make_equip_world(status="available", owner_user=None)
        from maiw_api.demo.providers.equipment import SimulationEquipmentProvider
        provider = SimulationEquipmentProvider(world=world, bus=bus)

        result = asyncio.run(provider.execute_equipment_release(_release_req()))

        assert result.outcome == "no_op"
        assert result.success is True
        assert provider._mutation_count == 0

    def test_assigned_asset_returns_executed(self):
        """EXECUTED: assigned asset released → mutation committed."""
        world, bus = _make_equip_world(status="assigned", owner_user="W-001")
        from maiw_api.demo.providers.equipment import SimulationEquipmentProvider
        provider = SimulationEquipmentProvider(world=world, bus=bus)

        result = asyncio.run(provider.execute_equipment_release(_release_req()))

        assert result.outcome == "executed"
        assert result.success is True
        assert provider._mutation_count == 1
        assert world.equipment["FA-001"].status == "available"
        assert world.equipment["FA-001"].owner_user is None


class TestEquipmentMaintenanceSemantics:
    """Reference table for equipment.schedule_maintenance outcomes."""

    def test_asset_not_found_raises_backend_unavailable(self):
        world, bus = _make_equip_world()
        world.equipment.clear()
        from maiw_api.demo.providers.equipment import SimulationEquipmentProvider
        provider = SimulationEquipmentProvider(world=world, bus=bus)

        with pytest.raises(BackendUnavailable):
            asyncio.run(provider.execute_schedule_maintenance(_maint_req()))

        assert provider._mutation_count == 0

    def test_already_in_maintenance_returns_no_op(self):
        """NO_OP: asset already in maintenance state."""
        world, bus = _make_equip_world(status="maintenance")
        from maiw_api.demo.providers.equipment import SimulationEquipmentProvider
        provider = SimulationEquipmentProvider(world=world, bus=bus)

        result = asyncio.run(provider.execute_schedule_maintenance(_maint_req()))

        assert result.outcome == "no_op"
        assert result.success is True
        assert provider._mutation_count == 0

    def test_available_asset_returns_executed(self):
        """EXECUTED: available asset scheduled for maintenance."""
        world, bus = _make_equip_world(status="available")
        from maiw_api.demo.providers.equipment import SimulationEquipmentProvider
        provider = SimulationEquipmentProvider(world=world, bus=bus)

        result = asyncio.run(provider.execute_schedule_maintenance(_maint_req()))

        assert result.outcome == "executed"
        assert result.success is True
        assert provider._mutation_count == 1
        assert world.equipment["FA-001"].status == "maintenance"

    def test_assigned_asset_can_be_scheduled_for_maintenance(self):
        """EXECUTED: currently assigned asset can be scheduled for maintenance."""
        world, bus = _make_equip_world(status="assigned", owner_user="W-001")
        from maiw_api.demo.providers.equipment import SimulationEquipmentProvider
        provider = SimulationEquipmentProvider(world=world, bus=bus)

        result = asyncio.run(provider.execute_schedule_maintenance(_maint_req()))

        assert result.outcome == "executed"
        assert provider._mutation_count == 1
        assert world.equipment["FA-001"].status == "maintenance"
