# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Every demo scenario runs on a world its scripted timeline can act on.

From #83 to #308 the scripted scenarios ran on the DC-47 DataPack world with
timelines that named YAML ids (``w-003``, ``AGV-02``). Each timed event failed
with a logged warning, no disruption was recorded, wave risk stayed ``none``
and recovery could never be detected, in either arm of the counterfactual.
Since #309 each runs on the DataPack world through the ``datapack`` block of
its YAML, with DataPack ids. These tests run the controller the way the API
does and check the world it builds, not a world seeded by hand.
"""

from __future__ import annotations

import asyncio

import pytest

from maiw_api.demo.controller import (
    _DISRUPTION_EVENT_TYPES,
    DemoScenarioController,
    _load_scenario_file,
    list_scenario_files,
    reset_demo_controller,
)
from maiw_api.demo.kpi import DemoKPIEngine

# Timed-event payload keys that name an entity, and the world collection
# each one must be found in.
_TARGET_COLLECTIONS = {
    "worker_id": "workers",
    "asset_id": "equipment",
    "task_id": "tasks",
    "sku": "inventory",
}

_SCENARIOS = sorted(list_scenario_files())
_SCRIPTED = [
    name
    for name in _SCENARIOS
    if any(
        ev.type in _DISRUPTION_EVENT_TYPES
        for ev in _load_scenario_file(list_scenario_files()[name]).timed_events
    )
]

TICKS = 30
TICK_SECONDS = 60


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


def test_the_scripted_scenarios_are_known():
    assert _SCRIPTED == ["equipment_failure", "labor_constraint_wave_risk"]


@pytest.mark.parametrize("name", _SCENARIOS)
def test_every_timed_event_targets_an_entity_of_the_active_world(name):
    ctrl = _started(name)
    source = "DataPack" if ctrl.world._scenario_world is not None else "YAML"
    for ev in ctrl._timed_events:  # the YAML's, or its datapack block's
        for key, collection in _TARGET_COLLECTIONS.items():
            if key in ev.payload:
                assert ev.payload[key] in getattr(ctrl.world, collection), (
                    f"{name}: timed event {ev.type!r} at {ev.offset_seconds}s targets "
                    f"{key}={ev.payload[key]!r}, which is not in the {source} world"
                )


@pytest.mark.parametrize("name", _SCRIPTED)
def test_scripted_disruption_is_recorded(name, caplog):
    ctrl = _started(name)
    for _ in range(TICKS):
        _run(ctrl.tick(TICK_SECONDS))
    assert ctrl.world._disruption_sim_time is not None
    assert "Timed event" not in caplog.text  # no "Timed event ... failed"


_LABOR_ORPHANS = [
    "task-000012",  # worker-000024, absent from the start
    "task-000017",  # worker-000024
    "task-000021",  # worker-000038, absent from the start
    "task-000022",  # worker-000038
    "task-000028",  # worker-000049, absent at start + 120 s
]


def _unassigned_pending(ctrl) -> list[str]:
    return sorted(
        t.task_id
        for t in ctrl.world.tasks.values()
        if t.status == "pending" and t.assigned_to is None
    )


def test_labor_constraint_control_arm_never_recovers():
    """No intervention, DataPack world (#309): two workers are absent from the
    start and a third at start + 120 s. Their unstarted wave-017 tasks go back
    to the pool and stay there; the wave stays critical for the whole horizon
    and recovery is not reached (README, Counterfactual Evaluation, Control)."""
    ctrl = _started("labor_constraint_wave_risk")
    assert ctrl.world._scenario_world is not None
    start = ctrl.world.clock.elapsed_seconds  # 5400: 09:30
    assert _unassigned_pending(ctrl) == _LABOR_ORPHANS[:4]

    for i in range(TICKS):
        _run(ctrl.tick(TICK_SECONDS))
        kpi = DemoKPIEngine(ctrl.world).compute()
        assert kpi.wave_risk_level == "critical", f"tick {i + 1}"
        assert kpi.wave_risk_score == 95.0, f"tick {i + 1}"

    assert ctrl.world._disruption_sim_time == start + 120
    assert ctrl.world.workers["worker-000049"].status == "on_leave"
    assert _unassigned_pending(ctrl) == _LABOR_ORPHANS
    # Assigned work has drained; only the orphaned tasks are left.
    assert kpi.pending_backlog == len(_LABOR_ORPHANS)
    assert ctrl._recovery_sim_time is None
    assert kpi.time_to_recovery_seconds is None


def test_labor_constraint_recovers_once_the_orphaned_tasks_are_allocated():
    """The allocation target the analyze route and the Copilot use picks the
    orphaned tasks, not assigned tasks waiting for their worker (#309)."""
    from maiw_api.demo.scheduling import labor_allocation_target
    from maiw_contracts.labor import LaborAllocateRequest

    ctrl = _started("labor_constraint_wave_risk")
    start = ctrl.world.clock.elapsed_seconds
    for _ in range(2):  # past the absence at start + 120 s
        _run(ctrl.tick(TICK_SECONDS))
    assert ctrl.world._disruption_sim_time == start + 120

    allocated = []
    for _ in _LABOR_ORPHANS:
        task_id, workers = labor_allocation_target(ctrl.world)
        allocated.append(task_id)
        _run(
            ctrl.providers.labor.execute_labor_allocation(
                LaborAllocateRequest(
                    warehouse_id="DC-47",
                    task_id=task_id,
                    task_type=ctrl.world.tasks[task_id].task_type,
                    worker_ids=workers,
                    proposal_id="p",
                    decision_id="d",
                )
            )
        )
    assert sorted(allocated) == _LABOR_ORPHANS

    _run(ctrl.tick(TICK_SECONDS))
    kpi = DemoKPIEngine(ctrl.world).compute()
    assert kpi.wave_risk_level == "none"
    assert ctrl._recovery_sim_time == start + 3 * TICK_SECONDS
    assert kpi.time_to_recovery_seconds == TICK_SECONDS


def test_yaml_timed_events_count_from_scenario_start(monkeypatch):
    """On the YAML world (the DataPack fallback) the labor absence at offset
    120 s fires 120 s after start. Offsets used to be compared with the clock
    reading, which starts at 5400 s, so it fired on the first tick (#309)."""
    from maiw_api.demo import world_loader

    monkeypatch.setattr(world_loader, "DATAPACK_SCENARIOS", frozenset())
    ctrl = _started("labor_constraint_wave_risk")
    assert ctrl.world._scenario_world is None
    start = ctrl.world.clock.elapsed_seconds

    _run(ctrl.tick(TICK_SECONDS))
    assert ctrl.world.workers["w-003"].status == "active"
    assert ctrl.world._disruption_sim_time is None

    _run(ctrl.tick(TICK_SECONDS))
    assert ctrl.world.workers["w-003"].status == "on_leave"
    assert ctrl.world._disruption_sim_time == start + 120
    kpi = DemoKPIEngine(ctrl.world).compute()
    assert (kpi.pending_backlog, kpi.wave_risk_level) == (5, "critical")


def test_equipment_failure_takes_the_scripted_agv_offline():
    ctrl = _started("equipment_failure")
    assert ctrl.world._scenario_world is not None  # DataPack world (#309)
    _run(ctrl.tick(TICK_SECONDS))
    assert ctrl.world.equipment["agv-001"].status == "offline"
    assert ctrl.world._disruption_sim_time is not None


def test_scripted_scenario_after_a_datapack_scenario_runs_on_its_yaml_world(
    monkeypatch,
):
    """Starting a YAML scenario after healthy_baseline (DataPack) must not
    seed the DataPack world in place: reset() would rebuild the DataPack
    world and /world would report it."""
    from maiw_api.demo import world_loader

    # Run labor_constraint_wave_risk on its YAML world, as without a DataPack.
    monkeypatch.setattr(
        world_loader, "DATAPACK_SCENARIOS", frozenset({"healthy_baseline"})
    )
    ctrl = _started("healthy_baseline")
    assert ctrl.world._scenario_world is not None
    datapack_world = ctrl.world

    _run(ctrl.start("labor_constraint_wave_risk"))
    assert ctrl.world is not datapack_world
    assert ctrl.world._scenario_world is None
    assert "w-003" in ctrl.world.workers
    assert ctrl.providers.labor._world is ctrl.world

    from mcp_servers.labor import server as labor_server

    assert labor_server._provider is ctrl.providers.labor

    _run(ctrl.reset())
    assert ctrl.world._scenario_world is None
    assert "w-003" in ctrl.world.workers
    assert "worker-000000" not in ctrl.world.workers
