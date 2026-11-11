# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Every demo scenario runs on a world its scripted timeline can act on (#308).

The scripted scenarios used to run on the DC-47 DataPack world, whose ids
(``worker-000000``, ``agv-000``) differ from the YAML ids their timed events
name (``w-003``, ``AGV-02``). Each timed event failed with a logged warning,
no disruption was recorded, wave risk stayed ``none`` and recovery could
never be detected, in either arm of the counterfactual. These tests run the
controller the way the API does and check the world it builds, not a world
seeded by hand.
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


def test_labor_constraint_control_arm_matches_the_published_control():
    """No intervention: the disruption is recorded at the first tick and the
    wave stays critical for the whole horizon (README, Counterfactual
    Evaluation, Control column: recovery not reached)."""
    ctrl = _started("labor_constraint_wave_risk")
    start = ctrl.world.clock.elapsed_seconds  # 5400: 90 minutes into the shift
    for i in range(TICKS):
        _run(ctrl.tick(TICK_SECONDS))
        kpi = DemoKPIEngine(ctrl.world).compute()
        assert kpi.pending_backlog == 5, f"tick {i + 1}"
        assert kpi.wave_risk_level == "critical", f"tick {i + 1}"
        assert kpi.wave_risk_score == 95.0, f"tick {i + 1}"
    assert ctrl.world._disruption_sim_time == start + TICK_SECONDS
    assert ctrl.world.workers["w-003"].status == "on_leave"
    assert ctrl._recovery_sim_time is None
    assert kpi.time_to_recovery_seconds is None


def test_equipment_failure_takes_the_scripted_agv_offline():
    ctrl = _started("equipment_failure")
    assert ctrl.world._scenario_world is not None  # DataPack world (#309)
    _run(ctrl.tick(TICK_SECONDS))
    assert ctrl.world.equipment["agv-001"].status == "offline"
    assert ctrl.world._disruption_sim_time is not None


def test_scripted_scenario_after_a_datapack_scenario_runs_on_its_yaml_world():
    """Starting a YAML scenario after healthy_baseline (DataPack) must not
    seed the DataPack world in place: reset() would rebuild the DataPack
    world and /world would report it."""
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
