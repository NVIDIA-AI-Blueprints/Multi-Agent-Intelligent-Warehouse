# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for DemoScenarioController."""

import asyncio
import pytest

from maiw_api.demo.controller import (
    DemoScenarioController,
    get_demo_controller,
    reset_demo_controller,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(autouse=True)
def reset_singleton():
    reset_demo_controller()
    yield
    reset_demo_controller()


@pytest.fixture
def ctrl():
    return DemoScenarioController()


class TestDemoScenarioControllerLifecycle:
    def test_initial_state_is_inactive(self, ctrl):
        assert not ctrl.active
        assert ctrl.scenario_name is None

    def test_list_scenarios_returns_five(self, ctrl):
        scenarios = ctrl.list_scenarios()
        assert len(scenarios) == 5
        names = [s["name"] for s in scenarios]
        assert "healthy_baseline" in names
        assert "equipment_failure" in names
        assert "labor_constraint_wave_risk" in names

    def test_start_unknown_scenario_raises(self, ctrl):
        with pytest.raises(ValueError, match="not found"):
            _run(ctrl.start("nonexistent_scenario"))

    def test_start_seeds_world(self, ctrl):
        _run(ctrl.start("healthy_baseline"))
        assert ctrl.active
        assert ctrl.scenario_name == "healthy_baseline"
        assert len(ctrl.world.equipment) > 0
        assert len(ctrl.world.workers) > 0

    def test_start_replaces_active_scenario(self, ctrl):
        _run(ctrl.start("healthy_baseline"))
        _run(ctrl.start("equipment_failure"))
        assert ctrl.scenario_name == "equipment_failure"

    def test_status_when_active(self, ctrl):
        _run(ctrl.start("healthy_baseline"))
        s = ctrl.status()
        assert s["active"] is True
        assert s["scenario"]["name"] == "healthy_baseline"
        assert "world" in s
        assert not s["paused"]

    def test_status_when_inactive(self, ctrl):
        s = ctrl.status()
        assert s["active"] is False
        assert s["scenario"] is None


class TestDemoScenarioControllerPauseResume:
    def test_pause_sets_paused_flag(self, ctrl):
        _run(ctrl.start("healthy_baseline"))
        _run(ctrl.pause())
        assert ctrl._paused

    def test_resume_clears_paused_flag(self, ctrl):
        _run(ctrl.start("healthy_baseline"))
        _run(ctrl.pause())
        _run(ctrl.resume())
        assert not ctrl._paused

    def test_pause_without_scenario_raises(self, ctrl):
        with pytest.raises(RuntimeError):
            _run(ctrl.pause())

    def test_resume_without_scenario_raises(self, ctrl):
        with pytest.raises(RuntimeError):
            _run(ctrl.resume())


class TestDemoScenarioControllerTick:
    def test_tick_advances_clock(self, ctrl):
        _run(ctrl.start("healthy_baseline"))
        initial = ctrl.world.clock.elapsed_seconds
        _run(ctrl.tick(60))
        assert ctrl.world.clock.elapsed_seconds == initial + 60

    def test_tick_without_scenario_raises(self, ctrl):
        with pytest.raises(RuntimeError):
            _run(ctrl.tick(60))

    def test_tick_when_paused_raises(self, ctrl):
        _run(ctrl.start("healthy_baseline"))
        _run(ctrl.pause())
        with pytest.raises(RuntimeError, match="paused"):
            _run(ctrl.tick(60))

    def test_tick_fires_timed_events(self, ctrl):
        _run(ctrl.start("equipment_failure"))
        # equipment_failure has a timed_event at +60s (AGV-02 battery critical)
        # Tick past it
        _run(ctrl.tick(120))
        # AGV-02 should have changed (battery_pct dropped based on timed event)
        agv02 = ctrl.world.equipment.get("AGV-02")
        if agv02:
            # If timed event fired, battery should be low
            assert agv02.battery_pct < 50 or agv02.status != "available"


class TestDemoScenarioControllerReset:
    def test_reset_restores_initial_state(self, ctrl):
        _run(ctrl.start("healthy_baseline"))
        initial_eq_status = {k: v.status for k, v in ctrl.world.equipment.items()}

        # Mutate world
        for asset in ctrl.world.equipment.values():
            asset.status = "offline"

        _run(ctrl.reset())

        for asset_id, status in initial_eq_status.items():
            assert ctrl.world.equipment[asset_id].status == status

    def test_reset_without_scenario_raises(self, ctrl):
        with pytest.raises(RuntimeError):
            _run(ctrl.reset())

    def test_reset_clears_paused(self, ctrl):
        _run(ctrl.start("healthy_baseline"))
        _run(ctrl.pause())
        _run(ctrl.reset())
        assert not ctrl._paused

    def test_reset_resets_event_index(self, ctrl):
        _run(ctrl.start("equipment_failure"))
        _run(ctrl.tick(120))  # fires timed events
        _run(ctrl.reset())
        assert ctrl._next_event_idx == 0


class TestDemoScenarioControllerInject:
    def test_inject_equipment_fault(self, ctrl):
        _run(ctrl.start("healthy_baseline"))
        asset_id = list(ctrl.world.equipment.keys())[0]
        result = _run(
            ctrl.inject(
                "equipment_fault",
                {
                    "asset_id": asset_id,
                    "fault_code": "E_MOTOR",
                    "new_status": "offline",
                },
            )
        )
        assert ctrl.world.equipment[asset_id].status == "offline"
        assert ctrl.world.equipment[asset_id].fault_code == "E_MOTOR"

    def test_inject_equipment_restore(self, ctrl):
        _run(ctrl.start("healthy_baseline"))
        asset_id = list(ctrl.world.equipment.keys())[0]
        ctrl.world.equipment[asset_id].status = "offline"
        ctrl.world.equipment[asset_id].fault_code = "E_MOTOR"
        _run(ctrl.inject("equipment_restore", {"asset_id": asset_id}))
        assert ctrl.world.equipment[asset_id].status == "available"
        assert ctrl.world.equipment[asset_id].fault_code is None

    def test_inject_low_stock(self, ctrl):
        _run(ctrl.start("healthy_baseline"))
        sku = list(ctrl.world.inventory.keys())[0]
        _run(ctrl.inject("low_stock", {"sku": sku, "quantity_available": 5}))
        assert ctrl.world.inventory[sku].quantity_available == 5

    def test_inject_worker_absence(self, ctrl):
        _run(ctrl.start("healthy_baseline"))
        worker_id = list(ctrl.world.workers.keys())[0]
        _run(ctrl.inject("worker_absence", {"worker_id": worker_id}))
        assert ctrl.world.workers[worker_id].status == "on_leave"

    def test_inject_worker_return(self, ctrl):
        _run(ctrl.start("healthy_baseline"))
        worker_id = list(ctrl.world.workers.keys())[0]
        ctrl.world.workers[worker_id].status = "on_leave"
        _run(ctrl.inject("worker_return", {"worker_id": worker_id}))
        assert ctrl.world.workers[worker_id].status == "active"

    def test_inject_task_deadline(self, ctrl):
        _run(ctrl.start("healthy_baseline"))
        task_id = list(ctrl.world.tasks.keys())[0]
        deadline = "2026-08-23T10:00:00+00:00"
        _run(ctrl.inject("task_deadline", {"task_id": task_id, "deadline": deadline}))
        assert ctrl.world.tasks[task_id].deadline == deadline

    def test_inject_unknown_event_raises(self, ctrl):
        _run(ctrl.start("healthy_baseline"))
        with pytest.raises(ValueError, match="Unknown event type"):
            _run(ctrl.inject("not_a_real_event", {}))

    def test_inject_without_scenario_raises(self, ctrl):
        with pytest.raises(RuntimeError, match="No active scenario"):
            _run(ctrl.inject("equipment_fault", {"asset_id": "AGV-01"}))


class TestGetDemoControllerSingleton:
    @pytest.fixture(autouse=True)
    def enable_demo_mode(self, monkeypatch):
        monkeypatch.setenv("MAIW_DEMO_MODE", "true")

    def test_returns_same_instance(self):
        c1 = get_demo_controller()
        c2 = get_demo_controller()
        assert c1 is c2

    def test_reset_creates_fresh_instance(self):
        c1 = get_demo_controller()
        reset_demo_controller()
        c2 = get_demo_controller()
        assert c1 is not c2
