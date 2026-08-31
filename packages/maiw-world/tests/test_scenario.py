# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 14D tests — ScenarioOverlay, ScenarioWorld, preset scenarios, builder.

Uses WarehouseWorldConfig.small() + WarehouseWorldGenerator for base graphs.
No real data files or filesystem I/O.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from maiw_world.config import WarehouseWorldConfig
from maiw_world.entities import EntityType
from maiw_world.generator import WarehouseWorldGenerator
from maiw_world.scenario import (
    OverlayEvent,
    OverlayEventKind,
    ScenarioOverlay,
    ScenarioOverlayBuilder,
    ScenarioWorld,
    equipment_failure_scenario,
    labor_constraint_scenario,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def small_graph():
    cfg = WarehouseWorldConfig.small()
    return WarehouseWorldGenerator(cfg).generate().graph


@pytest.fixture(scope="module")
def labor_overlay(small_graph):
    return labor_constraint_scenario(small_graph)


@pytest.fixture(scope="module")
def equip_overlay(small_graph):
    return equipment_failure_scenario(small_graph)


@pytest.fixture(scope="module")
def small_world(small_graph, labor_overlay):
    return ScenarioWorld(small_graph, labor_overlay)


# ── OverlayEvent validation tests ──────────────────────────────────────────────


def test_overlay_event_valid_constructs():
    """Test 1: Valid OverlayEvent constructs without error."""
    ev = OverlayEvent(
        event_id="ev-001",
        kind=OverlayEventKind.WORKER_ABSENCE,
        entity_id="worker-1",
        sim_time_offset_seconds=0.0,
    )
    assert ev.event_id == "ev-001"
    assert ev.kind == OverlayEventKind.WORKER_ABSENCE


def test_overlay_event_negative_offset_raises():
    """Test 2: sim_time_offset_seconds < 0 raises ValidationError."""
    with pytest.raises(ValidationError, match="sim_time_offset_seconds must be >= 0"):
        OverlayEvent(
            event_id="ev-bad",
            kind=OverlayEventKind.WORKER_ABSENCE,
            entity_id="worker-1",
            sim_time_offset_seconds=-1.0,
        )


def test_overlay_event_frozen():
    """Test 3: Frozen — mutating raises AttributeError."""
    ev = OverlayEvent(
        event_id="ev-001",
        kind=OverlayEventKind.WORKER_ABSENCE,
        entity_id="worker-1",
        sim_time_offset_seconds=0.0,
    )
    with pytest.raises(Exception):
        ev.label = "mutate attempt"  # type: ignore[misc]


# ── ScenarioOverlay tests ──────────────────────────────────────────────────────


def test_duplicate_event_ids_raises():
    """Test 4: Duplicate event_ids raises ValidationError."""
    ev = OverlayEvent(
        event_id="dup",
        kind=OverlayEventKind.WORKER_ABSENCE,
        entity_id="w1",
        sim_time_offset_seconds=0.0,
    )
    with pytest.raises(ValidationError, match="unique event_ids"):
        ScenarioOverlay(
            scenario_id="s1",
            name="S1",
            dataset_id="ds1",
            events=[ev, ev],
        )


def _make_overlay_with_events(*offsets_and_kinds):
    """Helper to build a ScenarioOverlay from (offset, kind, entity_id) triples."""
    events = [
        OverlayEvent(
            event_id=f"ev-{i}",
            kind=kind,
            entity_id=eid,
            sim_time_offset_seconds=offset,
        )
        for i, (offset, kind, eid) in enumerate(offsets_and_kinds)
    ]
    return ScenarioOverlay(
        scenario_id="test",
        name="Test",
        dataset_id="ds1",
        events=events,
    )


def test_events_at_or_before_filters_correctly():
    """Test 5: events_at_or_before(600) returns only events with offset <= 600."""
    overlay = _make_overlay_with_events(
        (0.0, OverlayEventKind.WORKER_ABSENCE, "w1"),
        (300.0, OverlayEventKind.WORKER_ABSENCE, "w2"),
        (600.0, OverlayEventKind.WORKER_ABSENCE, "w3"),
        (900.0, OverlayEventKind.WORKER_ABSENCE, "w4"),
    )
    result = overlay.events_at_or_before(600.0)
    assert len(result) == 3
    assert all(e.sim_time_offset_seconds <= 600.0 for e in result)


def test_events_before_filters_correctly():
    """Test 6: events_before(600) returns only events with offset < 600."""
    overlay = _make_overlay_with_events(
        (0.0, OverlayEventKind.WORKER_ABSENCE, "w1"),
        (300.0, OverlayEventKind.WORKER_ABSENCE, "w2"),
        (600.0, OverlayEventKind.WORKER_ABSENCE, "w3"),
        (900.0, OverlayEventKind.WORKER_ABSENCE, "w4"),
    )
    result = overlay.events_before(600.0)
    assert len(result) == 2
    assert all(e.sim_time_offset_seconds < 600.0 for e in result)


def test_events_by_kind_filters_correctly():
    """Test 7: events_by_kind(WORKER_ABSENCE) filters correctly."""
    overlay = _make_overlay_with_events(
        (0.0, OverlayEventKind.WORKER_ABSENCE, "w1"),
        (100.0, OverlayEventKind.EQUIPMENT_FAILURE, "eq1"),
        (200.0, OverlayEventKind.WORKER_ABSENCE, "w2"),
    )
    absences = overlay.events_by_kind(OverlayEventKind.WORKER_ABSENCE)
    assert len(absences) == 2
    assert all(e.kind == OverlayEventKind.WORKER_ABSENCE for e in absences)


def test_affected_entities_returns_all_ids():
    """Test 8: affected_entities() returns all entity IDs from events."""
    ev1 = OverlayEvent(
        event_id="e1",
        kind=OverlayEventKind.WORKER_ABSENCE,
        entity_id="w1",
        secondary_entity_id="shift-1",
        sim_time_offset_seconds=0.0,
    )
    ev2 = OverlayEvent(
        event_id="e2",
        kind=OverlayEventKind.EQUIPMENT_FAILURE,
        entity_id="eq1",
        sim_time_offset_seconds=0.0,
    )
    overlay = ScenarioOverlay(
        scenario_id="s",
        name="S",
        dataset_id="ds",
        events=[ev1, ev2],
    )
    affected = overlay.affected_entities()
    assert "w1" in affected
    assert "shift-1" in affected
    assert "eq1" in affected


def test_empty_overlay_no_affected_entities():
    """Test 9: Empty overlay has no affected entities."""
    overlay = ScenarioOverlay(
        scenario_id="empty",
        name="Empty",
        dataset_id="ds",
        events=[],
    )
    assert overlay.affected_entities() == set()


def test_builder_produces_frozen_overlay():
    """Test 10: Builder produces a frozen ScenarioOverlay."""
    overlay = (
        ScenarioOverlayBuilder("s1", "S1", "ds1")
        .build()
    )
    assert isinstance(overlay, ScenarioOverlay)
    with pytest.raises(Exception):
        overlay.name = "mutated"  # type: ignore[misc]


# ── ScenarioWorld construction tests ──────────────────────────────────────────


def test_scenario_world_constructs(small_graph, labor_overlay):
    """Test 11: ScenarioWorld with valid base_graph + overlay constructs without error."""
    world = ScenarioWorld(small_graph, labor_overlay)
    assert world.base_graph is small_graph
    assert world.overlay is labor_overlay


def test_scenario_world_no_warehouse_raises():
    """Test 12: Base graph with no Warehouse raises ValueError."""
    from maiw_world.graph import CanonicalWarehouseGraph

    empty_graph = CanonicalWarehouseGraph()
    overlay = ScenarioOverlay(
        scenario_id="s",
        name="S",
        dataset_id="ds",
        events=[],
    )
    with pytest.raises(ValueError, match="no Warehouse entity"):
        ScenarioWorld(empty_graph, overlay)


def test_scenario_world_unknown_entity_raises(small_graph):
    """Test 13: Overlay referencing unknown entity_id raises ValueError."""
    overlay = ScenarioOverlay(
        scenario_id="s",
        name="S",
        dataset_id="ds",
        events=[
            OverlayEvent(
                event_id="e1",
                kind=OverlayEventKind.WORKER_ABSENCE,
                entity_id="does-not-exist-xyz",
                sim_time_offset_seconds=0.0,
            )
        ],
    )
    with pytest.raises(ValueError, match="unknown entity IDs"):
        ScenarioWorld(small_graph, overlay)


# ── Overlay query tests ────────────────────────────────────────────────────────


def test_absent_workers_empty_before_events(small_world):
    """Test 14: absent_workers(at=-inf effectively) before any absence events."""
    # At t=-0.1 effectively but we clamp at 0 — use a time before first event
    # labor_overlay starts marking absences at t=0, so at t=-1 (not allowed; use boundary)
    # Actually sim_time_offset must be >= 0 for events; workers absent AT t=0 are captured
    # We test at a time when NO events have fired: events_at_or_before(-0.001) = []
    # The method takes any float, so pass a negative time to get zero events
    result = small_world.absent_workers(-1.0)
    assert result == []


def test_absent_workers_populated_after_events(small_world, labor_overlay):
    """Test 15: absent_workers at t=60 returns workers absent after events at t=0 and t=30."""
    absent = small_world.absent_workers(60.0)
    # labor_constraint adds absences at t=0, t=30, ... for 15% of workers
    # At t=60 we should have at least the first absence
    absence_events_at_or_before_60 = labor_overlay.events_at_or_before(60.0)
    absence_events = [
        e for e in absence_events_at_or_before_60
        if e.kind == OverlayEventKind.WORKER_ABSENCE
    ]
    assert len(absent) == len(absence_events)


def test_worker_return_removes_from_absent(small_graph):
    """Test 16: worker_return at t=120 removes worker from absent set after that offset."""
    workers = small_graph.entities_by_type(EntityType.WORKER)
    w = workers[0]
    warehouse = small_graph.entities_by_type(EntityType.WAREHOUSE)[0]

    overlay = (
        ScenarioOverlayBuilder("s", "S", warehouse.id)
        .worker_absence(w.id, at=0.0)
        .worker_return(w.id, at=120.0)
        .build()
    )
    world = ScenarioWorld(small_graph, overlay)

    assert w.id in world.absent_workers(60.0)
    assert w.id not in world.absent_workers(120.0)


def test_failed_equipment_at_offset_zero(small_world):
    """Test 17: failed_equipment(at=0) returns equipment that failed at t=0 (equip scenario)."""
    equip_graph = small_world.base_graph
    equip_ov = equipment_failure_scenario(equip_graph)
    world = ScenarioWorld(equip_graph, equip_ov)
    failed = world.failed_equipment(0.0)
    assert len(failed) >= 1


def test_equipment_restored_removes_from_failed(small_graph):
    """Test 18: equipment_restored removes equipment from failed set."""
    equip = small_graph.entities_by_type(EntityType.EQUIPMENT)
    eq = equip[0]
    warehouse = small_graph.entities_by_type(EntityType.WAREHOUSE)[0]

    overlay = (
        ScenarioOverlayBuilder("s", "S", warehouse.id)
        .equipment_failure(eq.id, at=0.0)
        .equipment_restored(eq.id, at=1800.0)
        .build()
    )
    world = ScenarioWorld(small_graph, overlay)

    assert eq.id in world.failed_equipment(900.0)
    assert eq.id not in world.failed_equipment(1800.0)


def test_blocked_tasks_at_600(small_world):
    """Test 19: blocked_tasks(at=600) returns tasks blocked at t=300."""
    blocked = small_world.blocked_tasks(600.0)
    # labor_constraint blocks tasks at t=300
    assert len(blocked) >= 1


def test_task_unblock_removes_from_blocked(small_graph):
    """Test 20: task_unblock removes task from blocked set."""
    tasks = small_graph.entities_by_type(EntityType.TASK)
    task = tasks[0]
    warehouse = small_graph.entities_by_type(EntityType.WAREHOUSE)[0]

    overlay = (
        ScenarioOverlayBuilder("s", "S", warehouse.id)
        .task_block(task.id, at=100.0, reason="test")
        .task_unblock(task.id, at=500.0)
        .build()
    )
    world = ScenarioWorld(small_graph, overlay)

    assert task.id in world.blocked_tasks(400.0)
    assert task.id not in world.blocked_tasks(500.0)


def test_inventory_adjustments(small_graph):
    """Test 21: inventory_adjustments returns last quantity for each inventory position."""
    inv_positions = small_graph.entities_by_type(EntityType.INVENTORY_POSITION)
    inv = inv_positions[0]
    warehouse = small_graph.entities_by_type(EntityType.WAREHOUSE)[0]

    overlay = (
        ScenarioOverlayBuilder("s", "S", warehouse.id)
        .inventory_shock(inv.id, new_quantity=50, at=100.0)
        .inventory_shock(inv.id, new_quantity=10, at=400.0)
        .build()
    )
    world = ScenarioWorld(small_graph, overlay)

    adj = world.inventory_adjustments(600.0)
    assert adj[inv.id] == 10  # last event wins

    adj_early = world.inventory_adjustments(200.0)
    assert adj_early[inv.id] == 50  # only first event at t=200


def test_missed_cutoffs_at_2000(small_world):
    """Test 22: missed_cutoffs(at=2000) returns cutoffs missed at t=1800."""
    missed = small_world.missed_cutoffs(2000.0)
    # labor_constraint adds a cutoff miss at t=1800
    assert len(missed) >= 1


def test_missed_cutoffs_before_event(small_world):
    """Test 23: missed_cutoffs(at=1000) returns empty (miss at t=1800 not yet occurred)."""
    missed = small_world.missed_cutoffs(1000.0)
    assert missed == []


# ── Severity tests ─────────────────────────────────────────────────────────────


def test_disruption_severity_nominal(small_graph):
    """Test 24: disruption_severity returns 'NOMINAL' with no disruptions."""
    warehouse = small_graph.entities_by_type(EntityType.WAREHOUSE)[0]
    overlay = ScenarioOverlayBuilder("s", "S", warehouse.id).build()
    world = ScenarioWorld(small_graph, overlay)
    assert world.disruption_severity(0.0) == "NOMINAL"


def test_disruption_severity_moderate_one_absent(small_graph):
    """Test 25: disruption_severity returns 'MODERATE' with 1 absent worker."""
    workers = small_graph.entities_by_type(EntityType.WORKER)
    warehouse = small_graph.entities_by_type(EntityType.WAREHOUSE)[0]
    # Mark just 1 worker absent — well under 10% threshold
    overlay = (
        ScenarioOverlayBuilder("s", "S", warehouse.id)
        .worker_absence(workers[0].id, at=0.0)
        .build()
    )
    world = ScenarioWorld(small_graph, overlay)
    severity = world.disruption_severity(60.0)
    # 1/40 workers = 2.5% -> MODERATE (not HIGH, not CRITICAL)
    assert severity == "MODERATE"


def test_disruption_severity_critical_cutoff_missed(small_world):
    """Test 26: disruption_severity returns 'CRITICAL' when cutoff missed."""
    assert small_world.disruption_severity(2000.0) == "CRITICAL"


def test_active_disruptions_has_four_keys(small_world):
    """Test 27: active_disruptions returns all four keys."""
    result = small_world.active_disruptions(600.0)
    assert set(result.keys()) == {
        "absent_workers",
        "failed_equipment",
        "blocked_tasks",
        "missed_cutoffs",
    }


# ── Preset scenario tests ──────────────────────────────────────────────────────


def test_labor_constraint_scenario_valid(small_graph, labor_overlay):
    """Test 28: labor_constraint_scenario produces valid overlay referencing real entity IDs."""
    assert isinstance(labor_overlay, ScenarioOverlay)
    assert labor_overlay.scenario_id == "labor-constraint-wave-risk"
    # All entity IDs referenced must be real
    known_ids = set(small_graph._entities.keys())
    for eid in labor_overlay.affected_entities():
        assert eid in known_ids, f"Unknown entity ID in labor overlay: {eid}"


def test_equipment_failure_scenario_valid(small_graph, equip_overlay):
    """Test 29: equipment_failure_scenario produces valid overlay."""
    assert isinstance(equip_overlay, ScenarioOverlay)
    assert equip_overlay.scenario_id == "agv-fleet-failure"
    known_ids = set(small_graph._entities.keys())
    for eid in equip_overlay.affected_entities():
        assert eid in known_ids, f"Unknown entity ID in equip overlay: {eid}"


def test_both_presets_scenario_world_constructs(small_graph, labor_overlay, equip_overlay):
    """Test 30: Both preset scenarios — ScenarioWorld constructs without error."""
    world_labor = ScenarioWorld(small_graph, labor_overlay)
    world_equip = ScenarioWorld(small_graph, equip_overlay)
    assert world_labor.overlay.scenario_id == "labor-constraint-wave-risk"
    assert world_equip.overlay.scenario_id == "agv-fleet-failure"


def test_labor_constraint_absent_workers_at_300(small_graph, labor_overlay):
    """Test 31: labor_constraint_scenario: absent_workers at t=300 is non-empty."""
    world = ScenarioWorld(small_graph, labor_overlay)
    absent = world.absent_workers(300.0)
    assert len(absent) >= 1


def test_equipment_failure_scenario_failed_at_0_empty_at_2000(small_graph, equip_overlay):
    """Test 32: equipment_failure_scenario: failed at t=0, empty at t=2000 (restored)."""
    world = ScenarioWorld(small_graph, equip_overlay)
    assert len(world.failed_equipment(0.0)) >= 1
    assert world.failed_equipment(2000.0) == []


# ── Builder fluent API test ────────────────────────────────────────────────────


def test_builder_full_chain(small_graph):
    """Test 33: Full builder chain with all event types produces valid ScenarioOverlay."""
    workers = small_graph.entities_by_type(EntityType.WORKER)
    equipment = small_graph.entities_by_type(EntityType.EQUIPMENT)
    tasks = small_graph.entities_by_type(EntityType.TASK)
    cutoffs = small_graph.entities_by_type(EntityType.CARRIER_CUTOFF)
    inv_positions = small_graph.entities_by_type(EntityType.INVENTORY_POSITION)
    warehouse = small_graph.entities_by_type(EntityType.WAREHOUSE)[0]

    builder = ScenarioOverlayBuilder(
        scenario_id="full-chain",
        name="Full Chain Test",
        dataset_id=warehouse.id,
        description="All event types exercised.",
    )

    if workers:
        builder.worker_absence(workers[0].id, at=0.0)
        builder.worker_return(workers[0].id, at=3600.0)
    if equipment:
        builder.equipment_failure(equipment[0].id, at=100.0)
        builder.equipment_restored(equipment[0].id, at=1900.0)
    if tasks:
        builder.task_block(tasks[0].id, at=200.0, reason="full-chain-test")
        builder.task_unblock(tasks[0].id, at=800.0)
    if cutoffs:
        builder.carrier_cutoff_miss(cutoffs[0].id, at=1800.0)
    if inv_positions:
        builder.inventory_shock(inv_positions[0].id, new_quantity=5, at=500.0)

    builder.tag("test", "full-chain")

    overlay = builder.build()
    assert isinstance(overlay, ScenarioOverlay)
    assert "test" in overlay.tags
    assert "full-chain" in overlay.tags

    # Validate it constructs a ScenarioWorld successfully
    world = ScenarioWorld(small_graph, overlay)
    disruptions = world.active_disruptions(2000.0)
    assert isinstance(disruptions, dict)
