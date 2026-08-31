# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Tests for WarehouseProjectionBuilder (Phase 14E).

Uses WarehouseWorldConfig.small() + generator for all tests.
Also exercises the tiny_world fixture from fixtures.py for edge-case coverage.
"""

from __future__ import annotations

import pytest

from maiw_world.config import WarehouseWorldConfig
from maiw_world.generator import WarehouseWorldGenerator
from maiw_world.projections import WarehouseProjectionBuilder
from maiw_world.scenario import (
    ScenarioOverlay,
    ScenarioOverlayBuilder,
    ScenarioWorld,
    labor_constraint_scenario,
    equipment_failure_scenario,
)
from maiw_world.entities import EntityType

from .fixtures import make_tiny_world


# ── Fixtures ────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def small_graph():
    cfg = WarehouseWorldConfig.small()
    result = WarehouseWorldGenerator(cfg).generate()
    return result.graph


@pytest.fixture(scope="module")
def small_world(small_graph):
    """ScenarioWorld with a no-disruption overlay."""
    warehouse_entities = small_graph.entities_by_type(EntityType.WAREHOUSE)
    dataset_id = warehouse_entities[0].id if warehouse_entities else "small-demo-v1"
    overlay = ScenarioOverlay(
        scenario_id="small-healthy",
        name="Small Healthy",
        dataset_id=dataset_id,
        events=[],
    )
    return ScenarioWorld(small_graph, overlay)


@pytest.fixture(scope="module")
def tiny_graph():
    return make_tiny_world()


@pytest.fixture(scope="module")
def tiny_healthy_world(tiny_graph):
    overlay = ScenarioOverlay(
        scenario_id="tiny-healthy",
        name="Tiny Healthy",
        dataset_id="DC-47",
        events=[],
    )
    return ScenarioWorld(tiny_graph, overlay)


@pytest.fixture(scope="module")
def tiny_labor_world(tiny_graph):
    return ScenarioWorld(tiny_graph, labor_constraint_scenario(tiny_graph))


@pytest.fixture(scope="module")
def tiny_equipment_world(tiny_graph):
    return ScenarioWorld(tiny_graph, equipment_failure_scenario(tiny_graph))


# ── 1. InventoryProjection.total_sku_count matches graph inventory position count ─

def test_inventory_total_sku_count_matches_graph(small_world, small_graph):
    builder = WarehouseProjectionBuilder(small_world, at_offset=0.0)
    inv = builder.inventory()
    graph_invpos_count = len(small_graph.entities_by_type(EntityType.INVENTORY_POSITION))
    assert inv.total_sku_count == graph_invpos_count


# ── 2. InventoryProjection.low_stock_count > 0 when low_stock_pct > 0 ─────────

def test_inventory_low_stock_count_positive(small_world):
    # small config has low_stock_pct=0.05, so some items should be low stock
    builder = WarehouseProjectionBuilder(small_world, at_offset=0.0)
    inv = builder.inventory()
    assert inv.low_stock_count > 0


# ── 3. InventoryItemProjection.is_low_stock correct when qty < reorder_point ───

def test_inventory_item_is_low_stock_flag(small_world):
    builder = WarehouseProjectionBuilder(small_world, at_offset=0.0)
    inv = builder.inventory()
    for item in inv.items:
        expected = item.quantity_available < item.reorder_point
        assert item.is_low_stock == expected, (
            f"SKU {item.sku_id}: qty={item.quantity_available} rp={item.reorder_point} "
            f"is_low_stock={item.is_low_stock} expected={expected}"
        )


# ── 4. Inventory shock overlay reduces qty in projection ─────────────────────────

def test_inventory_shock_reduces_quantity(tiny_graph):
    inv_positions = tiny_graph.entities_by_type(EntityType.INVENTORY_POSITION)
    assert inv_positions, "Need at least one inventory position"
    target_pos = inv_positions[0]

    overlay = (
        ScenarioOverlayBuilder("shock-test", "Shock Test", dataset_id="DC-47")
        .inventory_shock(target_pos.id, new_quantity=0, at=0.0)
        .build()
    )
    world = ScenarioWorld(tiny_graph, overlay)
    builder = WarehouseProjectionBuilder(world, at_offset=1.0)
    inv = builder.inventory()

    shocked_items = [i for i in inv.items if i.sku_id == target_pos.sku_id]
    assert len(shocked_items) == 1
    assert shocked_items[0].quantity_available == 0


# ── 5. LaborProjection.total_count matches graph worker count ──────────────────

def test_labor_total_count_matches_graph(small_world, small_graph):
    builder = WarehouseProjectionBuilder(small_world, at_offset=0.0)
    labor = builder.labor()
    graph_worker_count = len(small_graph.entities_by_type(EntityType.WORKER))
    assert labor.total_count == graph_worker_count


# ── 6. LaborProjection.absent_count matches workers marked absent in overlay ───

def test_labor_absent_count_matches_overlay(tiny_graph):
    workers = tiny_graph.entities_by_type(EntityType.WORKER)
    assert len(workers) >= 1, "Need at least 1 worker"
    target_worker = workers[0]

    overlay = (
        ScenarioOverlayBuilder("absent-test", "Absent Test", dataset_id="DC-47")
        .worker_absence(target_worker.id, at=0.0)
        .build()
    )
    world = ScenarioWorld(tiny_graph, overlay)
    builder = WarehouseProjectionBuilder(world, at_offset=1.0)
    labor = builder.labor()
    assert labor.absent_count == 1


# ── 7. Absent worker has is_absent=True in projection ─────────────────────────

def test_absent_worker_flagged(tiny_graph):
    workers = tiny_graph.entities_by_type(EntityType.WORKER)
    target = workers[0]
    overlay = (
        ScenarioOverlayBuilder("abs-flag-test", "Abs Flag Test", dataset_id="DC-47")
        .worker_absence(target.id, at=0.0)
        .build()
    )
    world = ScenarioWorld(tiny_graph, overlay)
    builder = WarehouseProjectionBuilder(world, at_offset=1.0)
    labor = builder.labor()
    flagged = [w for w in labor.workers if w.worker_id == target.id]
    assert len(flagged) == 1
    assert flagged[0].is_absent is True


# ── 8. EquipmentProjection.total_count matches graph equipment count ────────────

def test_equipment_total_count_matches_graph(small_world, small_graph):
    builder = WarehouseProjectionBuilder(small_world, at_offset=0.0)
    eq = builder.equipment()
    graph_eq_count = len(small_graph.entities_by_type(EntityType.EQUIPMENT))
    assert eq.total_count == graph_eq_count


# ── 9. Equipment failure overlay marks is_failed=True in projection ─────────────

def test_equipment_failure_flagged(tiny_graph):
    equipment = tiny_graph.entities_by_type(EntityType.EQUIPMENT)
    assert equipment, "Need at least 1 equipment item"
    target = equipment[0]

    overlay = (
        ScenarioOverlayBuilder("eq-fail-test", "Eq Fail Test", dataset_id="DC-47")
        .equipment_failure(target.id, at=0.0)
        .build()
    )
    world = ScenarioWorld(tiny_graph, overlay)
    builder = WarehouseProjectionBuilder(world, at_offset=1.0)
    eq = builder.equipment()
    failed = [e for e in eq.items if e.equipment_id == target.id]
    assert len(failed) == 1
    assert failed[0].is_failed is True


# ── 10. EquipmentProjection.available_count = total - failed ───────────────────

def test_equipment_available_count_formula(tiny_equipment_world):
    builder = WarehouseProjectionBuilder(tiny_equipment_world, at_offset=1.0)
    eq = builder.equipment()
    assert eq.available_count == eq.total_count - eq.failed_count


# ── 11. WaveProjection wave count matches graph wave count ─────────────────────

def test_wave_count_matches_graph(small_world, small_graph):
    builder = WarehouseProjectionBuilder(small_world, at_offset=0.0)
    waves = builder.waves()
    graph_wave_count = len(small_graph.entities_by_type(EntityType.WAVE))
    assert len(waves.waves) == graph_wave_count


# ── 12. TaskProjection.is_blocked True when task in blocked set ─────────────────

def test_task_is_blocked_flag(tiny_graph):
    tasks = tiny_graph.entities_by_type(EntityType.TASK)
    assert tasks, "Need at least 1 task"
    target_task = tasks[0]

    overlay = (
        ScenarioOverlayBuilder("blk-test", "Block Test", dataset_id="DC-47")
        .task_block(target_task.id, at=0.0, reason="test")
        .build()
    )
    world = ScenarioWorld(tiny_graph, overlay)
    builder = WarehouseProjectionBuilder(world, at_offset=1.0)
    wave_proj = builder.waves()
    all_tasks = [t for w in wave_proj.waves for t in w.tasks]
    blocked = [t for t in all_tasks if t.task_id == target_task.id]
    assert len(blocked) == 1
    assert blocked[0].is_blocked is True


# ── 13. WaveItemProjection.missed_cutoff_ids populated when cutoff missed ────────

def test_wave_missed_cutoff_ids(tiny_graph):
    from maiw_world.entities import EntityType as ET
    cutoffs = tiny_graph.entities_by_type(ET.CARRIER_CUTOFF)
    assert cutoffs, "Need at least 1 carrier cutoff"
    cutoff = cutoffs[0]

    overlay = (
        ScenarioOverlayBuilder("cutoff-test", "Cutoff Test", dataset_id="DC-47")
        .carrier_cutoff_miss(cutoff.id, at=0.0)
        .build()
    )
    world = ScenarioWorld(tiny_graph, overlay)
    builder = WarehouseProjectionBuilder(world, at_offset=1.0)
    wave_proj = builder.waves()
    # wave-017 is constrained by cutoff-001 in tiny world
    constrained_waves = [w for w in wave_proj.waves if cutoff.id in w.carrier_cutoff_ids]
    assert constrained_waves, "Expected at least one wave constrained by the cutoff"
    for w in constrained_waves:
        assert cutoff.id in w.missed_cutoff_ids


# ── 14. Task→Worker assignment preserved in TaskProjection.assigned_worker_id ───

def test_task_assigned_worker_preserved(tiny_healthy_world):
    builder = WarehouseProjectionBuilder(tiny_healthy_world, at_offset=0.0)
    wave_proj = builder.waves()
    all_tasks = [t for w in wave_proj.waves for t in w.tasks]
    # tiny world assigns worker-001 to task-000001 via ASSIGNED_TO edge
    assigned = [t for t in all_tasks if t.assigned_worker_id is not None]
    assert assigned, "Expected at least one task with an assigned worker"
    task_ids = {t.task_id for t in assigned}
    assert "task-000001" in task_ids or "task-000002" in task_ids


# ── 15. Task→SKU requirement preserved in TaskProjection.required_sku_id ────────

def test_task_required_sku_preserved(tiny_healthy_world):
    builder = WarehouseProjectionBuilder(tiny_healthy_world, at_offset=0.0)
    wave_proj = builder.waves()
    all_tasks = [t for w in wave_proj.waves for t in w.tasks]
    # tiny world has task-000001 REQUIRES sku-000001
    tasks_with_sku = [t for t in all_tasks if t.required_sku_id is not None]
    assert tasks_with_sku, "Expected at least one task with a required SKU"


# ── 16. build_all() returns all four domains ────────────────────────────────────

def test_build_all_returns_four_domains(small_world):
    builder = WarehouseProjectionBuilder(small_world, at_offset=0.0)
    result = builder.build_all()
    assert set(result.keys()) == {"inventory", "labor", "equipment", "waves"}


# ── 17. Projection at at_offset=0 shows no disruptions for healthy world ────────

def test_no_disruptions_at_t0_healthy(tiny_healthy_world):
    builder = WarehouseProjectionBuilder(tiny_healthy_world, at_offset=0.0)
    labor = builder.labor()
    equipment = builder.equipment()
    assert labor.absent_count == 0
    assert equipment.failed_count == 0


# ── 18. Projection at at_offset=9999 shows all disruptions from labor_constraint ─

def test_all_disruptions_applied_at_large_offset(tiny_labor_world):
    builder = WarehouseProjectionBuilder(tiny_labor_world, at_offset=9999.0)
    labor = builder.labor()
    equipment = builder.equipment()
    # Labor constraint scenario marks workers absent
    assert labor.absent_count > 0
    # Equipment should remain healthy in labor_constraint scenario
    assert equipment.failed_count == 0


# ── 19. LaborProjection.available_count decreases after worker absences apply ───

def test_labor_available_decreases_after_absence(tiny_graph):
    workers = tiny_graph.entities_by_type(EntityType.WORKER)
    assert workers, "Need workers"
    target = workers[0]

    overlay = (
        ScenarioOverlayBuilder("avail-test", "Avail Test", dataset_id="DC-47")
        .worker_absence(target.id, at=100.0)
        .build()
    )
    world = ScenarioWorld(tiny_graph, overlay)
    builder_before = WarehouseProjectionBuilder(world, at_offset=50.0)
    builder_after = WarehouseProjectionBuilder(world, at_offset=150.0)

    before = builder_before.labor()
    after = builder_after.labor()
    assert after.available_count == before.available_count - 1


# ── 20. EquipmentProjection.failed_count is 0 at t=0 for healthy, > 0 after failure

def test_equipment_failed_count_before_and_after(tiny_graph):
    equipment = tiny_graph.entities_by_type(EntityType.EQUIPMENT)
    assert equipment, "Need equipment"
    target = equipment[0]

    overlay = (
        ScenarioOverlayBuilder("eq-timing", "Eq Timing", dataset_id="DC-47")
        .equipment_failure(target.id, at=500.0)
        .build()
    )
    world = ScenarioWorld(tiny_graph, overlay)

    before = WarehouseProjectionBuilder(world, at_offset=0.0).equipment()
    after = WarehouseProjectionBuilder(world, at_offset=600.0).equipment()

    assert before.failed_count == 0
    assert after.failed_count > 0
