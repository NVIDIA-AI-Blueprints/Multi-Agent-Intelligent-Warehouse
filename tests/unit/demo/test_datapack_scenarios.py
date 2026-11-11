# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
The scripted scenarios run on the DC-47 DataPack world (#309).

Each scenario's YAML has a ``datapack`` block: a clock offset, initial_state
overrides of named DataPack entities, timed events counted from scenario
start and recovery thresholds. These tests run the controller the way the API
does and check the world it builds.
"""

from __future__ import annotations

import asyncio

import pytest

from maiw_api.demo import world_loader
from maiw_api.demo.controller import DemoScenarioController, reset_demo_controller
from maiw_api.demo.kpi import DemoKPIEngine
from maiw_contracts.labor import LaborAllocateRequest

TICKS = 30
TICK_SECONDS = 60
MOVED = [
    "equipment_failure",
    "labor_constraint_wave_risk",
    "stale_state",
    "state_drift",
]


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def reset_singleton():
    reset_demo_controller()
    yield
    reset_demo_controller()


def _started(name: str) -> DemoScenarioController:
    ctrl = DemoScenarioController()
    _run(ctrl.start(name))
    return ctrl


def _kpi(ctrl):
    return DemoKPIEngine(ctrl.world).compute()


@pytest.mark.parametrize("name", MOVED)
def test_scenario_runs_on_the_datapack_world_with_its_clock_offset(name):
    block = world_loader.datapack_block(name)
    assert block, f"{name}.yaml has no datapack block"
    assert name in world_loader.DATAPACK_SCENARIOS

    ctrl = _started(name)
    assert ctrl.world._scenario_world is not None
    assert "worker-000000" in ctrl.world.workers
    assert ctrl.world.clock.elapsed_seconds == block["clock_offset_seconds"]
    assert ctrl.world.scenario_elapsed_seconds == 0


@pytest.mark.parametrize("name", MOVED)
def test_initial_state_overrides_are_applied(name):
    block = world_loader.datapack_block(name)
    ctrl = _started(name)
    for section, entries in block["initial_state"].items():
        collection = getattr(ctrl.world, section)
        for entity_id, changes in entries.items():
            entity = collection[entity_id]
            for key, value in changes.items():
                actual = getattr(entity, key)
                if hasattr(actual, "isoformat"):
                    actual = actual.isoformat()
                assert actual == value, f"{section}.{entity_id}.{key}"


# ── equipment_failure ─────────────────────────────────────────────────────────


def test_equipment_failure_control_arm_never_recovers():
    """No intervention: agv-001 fails at start + 60 s, the two picks that lost
    their equipment stay unassigned and the wave stays critical."""
    ctrl = _started("equipment_failure")
    start = ctrl.world.clock.elapsed_seconds
    assert _kpi(ctrl).wave_risk_level == "critical"

    for i in range(TICKS):
        _run(ctrl.tick(TICK_SECONDS))
        kpi = _kpi(ctrl)
        assert kpi.wave_risk_level == "critical", f"tick {i + 1}"
        assert kpi.wave_risk_score == 95.0, f"tick {i + 1}"

    assert ctrl.world._disruption_sim_time == start + 60
    assert ctrl.world.equipment["agv-001"].status == "offline"
    assert ctrl._recovery_sim_time is None
    unassigned = sorted(
        t.task_id
        for t in ctrl.world.tasks.values()
        if t.status == "pending" and t.assigned_to is None
    )
    assert unassigned == ["task-000000", "task-000024"]


def test_equipment_failure_recovers_once_the_orphaned_picks_are_allocated():
    ctrl = _started("equipment_failure")
    start = ctrl.world.clock.elapsed_seconds
    _run(ctrl.tick(TICK_SECONDS))  # agv-001 fails: disruption at start + 60

    free = sorted(
        w.worker_id
        for w in ctrl.world.workers.values()
        if w.status == "active" and w.current_task_id is None
    )
    for task_id, worker_id in zip(["task-000000", "task-000024"], free):
        task = ctrl.world.tasks[task_id]
        _run(
            ctrl.providers.labor.execute_labor_allocation(
                LaborAllocateRequest(
                    warehouse_id="DC-47",
                    task_id=task_id,
                    task_type=task.task_type,
                    worker_ids=[worker_id],
                    proposal_id="p",
                    decision_id="d",
                )
            )
        )
    _run(ctrl.tick(TICK_SECONDS))

    assert _kpi(ctrl).wave_risk_level == "none"
    assert ctrl._recovery_sim_time == start + 2 * TICK_SECONDS
    assert _kpi(ctrl).time_to_recovery_seconds == TICK_SECONDS


# ── stale_state / state_drift ─────────────────────────────────────────────────


def test_stale_state_is_45_minutes_stale_with_a_critical_wave():
    ctrl = _started("stale_state")
    assert ctrl.world.clock.now().isoformat() == "2026-08-23T07:15:00+00:00"
    assert ctrl.world.equipment["agv-000"].status == "assigned"
    assert ctrl.world.equipment["agv-000"].owner_user == "worker-000000"
    assert _kpi(ctrl).wave_risk_level == "critical"
    assert ctrl._timed_events == []
    assert ctrl._recovery == {}


def test_state_drift_has_low_stock_and_a_charging_agv():
    ctrl = _started("state_drift")
    for sku in ("sku-000000", "sku-000001", "sku-000002"):
        assert ctrl.world.inventory[sku].is_low_stock, sku
    agv = ctrl.world.equipment["agv-001"]
    assert (agv.status, agv.battery_pct) == ("charging", 23.0)


# ── overlay, reset, failure modes ─────────────────────────────────────────────


def test_overlay_lists_the_disruptions_the_demo_runs():
    """The World Explorer reads the overlay: it must show the scenario's
    failures at their offsets from scenario start, not a preset."""
    ctrl = _started("equipment_failure")
    overlay = ctrl.world._scenario_world.overlay
    events = [
        (e.kind.value, e.entity_id, e.sim_time_offset_seconds) for e in overlay.events
    ]
    assert events == [
        ("EQUIPMENT_FAILURE", "agv-000", 0.0),
        ("EQUIPMENT_FAILURE", "agv-001", 60.0),
    ]
    sw = ctrl.world._scenario_world
    assert sw.failed_equipment(ctrl.world.scenario_elapsed_seconds) == ["agv-000"]
    _run(ctrl.tick(TICK_SECONDS))
    assert sorted(sw.failed_equipment(ctrl.world.scenario_elapsed_seconds)) == [
        "agv-000",
        "agv-001",
    ]


def test_state_drift_overlay_lists_the_inventory_drift():
    ctrl = _started("state_drift")
    kinds = {e.kind.value for e in ctrl.world._scenario_world.overlay.events}
    assert kinds == {"INVENTORY_SHOCK"}
    assert len(ctrl.world._scenario_world.overlay.events) == 3


def test_reset_restores_the_datapack_setup():
    ctrl = _started("equipment_failure")
    start = ctrl.world.clock.elapsed_seconds
    for _ in range(5):
        _run(ctrl.tick(TICK_SECONDS))
    _run(ctrl.reset())

    assert ctrl.world.clock.elapsed_seconds == start
    assert ctrl.world.equipment["agv-000"].status == "offline"
    assert ctrl.world.equipment["agv-001"].status == "available"
    assert ctrl.world.tasks["task-000000"].status == "pending"
    assert ctrl.world._disruption_sim_time is None

    _run(ctrl.tick(TICK_SECONDS))  # the timed event fires again after reset
    assert ctrl.world.equipment["agv-001"].status == "offline"


def test_an_unknown_datapack_id_fails_at_start(monkeypatch):
    """A block naming an entity the DataPack lacks must fail loudly, not run
    without its disruption (#308)."""
    import copy

    import maiw_api.demo.controller as controller_module

    original = controller_module._load_scenario_file

    def load_with_typo(path):
        defn = original(path)
        if defn.name == "stale_state":
            defn.datapack = copy.deepcopy(defn.datapack)
            defn.datapack["initial_state"]["equipment"]["AGV-01"] = {
                "status": "assigned"
            }
        return defn

    monkeypatch.setattr(controller_module, "_load_scenario_file", load_with_typo)
    with pytest.raises(ValueError, match="'AGV-01' is not in the DataPack world"):
        _started("stale_state")


def test_without_the_datapack_the_yaml_world_and_timeline_are_used(monkeypatch):
    monkeypatch.setattr(world_loader, "DATAPACK_SCENARIOS", frozenset())
    ctrl = _started("equipment_failure")
    assert ctrl.world._scenario_world is None
    assert "AGV-02" in ctrl.world.equipment
    assert [e.payload["asset_id"] for e in ctrl._timed_events] == ["AGV-02"]
    _run(ctrl.tick(TICK_SECONDS))
    assert ctrl.world.equipment["AGV-02"].status == "offline"
