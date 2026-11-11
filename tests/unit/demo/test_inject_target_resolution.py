# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Worker, SKU and task injection targets are resolved from the ACTIVE world.

The demo control bar sent ``worker_id: 'w-002'`` and ``sku: 'SKU-1001'``, and
the reliability panel ``w-003`` and ``task-001``: YAML ids the DC-47 DataPack
world lacks. Once equipment_failure, stale_state and state_drift run on the
DataPack world (#309), those buttons failed in four of five scenarios.

Rule (DemoScenarioController.resolve_inject_target), id omitted:
    worker_absence  active workers, those with a current task first
    worker_return   workers not active
    low_stock       SKUs not already low on stock
    task_deadline   pending tasks, high/critical priority first
    then the lowest id (plain string order).
"""

from __future__ import annotations

import asyncio

import pytest

from maiw_api.demo.controller import (
    DemoScenarioController,
    InjectTargetError,
    reset_demo_controller,
)


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


@pytest.fixture
def datapack_ctrl():
    ctrl = _started("healthy_baseline")
    assert ctrl.world._scenario_world is not None
    return ctrl


@pytest.fixture
def yaml_ctrl(monkeypatch):
    """labor_constraint_wave_risk on its YAML world (the DataPack fallback)."""
    from maiw_api.demo import world_loader

    monkeypatch.setattr(world_loader, "DATAPACK_SCENARIOS", frozenset())
    ctrl = _started("labor_constraint_wave_risk")
    assert ctrl.world._scenario_world is None
    return ctrl


def _inject(ctrl, event_type, **payload):
    return _run(ctrl.inject(event_type, payload))


def test_absence_targets_the_lowest_active_worker_with_work(datapack_ctrl):
    world = datapack_ctrl.world
    expected = min(
        wid
        for wid, w in world.workers.items()
        if w.status == "active" and w.current_task_id is not None
    )
    result = _inject(datapack_ctrl, "worker_absence")
    assert result["worker_id"] == expected
    assert result["target_resolution"] == "resolved"
    assert world.workers[expected].status == "on_leave"
    assert datapack_ctrl.world._disruption_sim_time is not None


def test_absence_prefers_workers_with_a_task(datapack_ctrl):
    world = datapack_ctrl.world
    for w in world.workers.values():
        w.current_task_id = None
    world.workers["worker-000005"].current_task_id = "task-000005"
    assert _inject(datapack_ctrl, "worker_absence")["worker_id"] == "worker-000005"


def test_return_targets_the_absent_worker(datapack_ctrl):
    absent = _inject(datapack_ctrl, "worker_absence")["worker_id"]
    result = _inject(datapack_ctrl, "worker_return")
    assert result["worker_id"] == absent
    assert datapack_ctrl.world.workers[absent].status == "active"


def test_return_with_everyone_active_is_typed(datapack_ctrl):
    with pytest.raises(InjectTargetError) as exc:
        _inject(datapack_ctrl, "worker_return")
    assert (exc.value.status_code, exc.value.code) == (409, "NO_ELIGIBLE_WORKER")


def test_low_stock_targets_the_lowest_sku_not_yet_low(datapack_ctrl):
    world = datapack_ctrl.world
    expected = min(sku for sku, i in world.inventory.items() if not i.is_low_stock)
    first = _inject(datapack_ctrl, "low_stock", quantity_available=0)
    assert first["sku"] == expected and first["is_low_stock"] is True
    second = _inject(datapack_ctrl, "low_stock", quantity_available=0)
    assert second["sku"] != expected  # the low one is skipped next time


def test_task_deadline_targets_a_high_priority_pending_task(datapack_ctrl):
    world = datapack_ctrl.world
    expected = min(
        tid
        for tid, t in world.tasks.items()
        if t.status == "pending" and t.priority in ("high", "critical")
    )
    result = _inject(
        datapack_ctrl, "task_deadline", deadline="2026-08-23T09:00:00+00:00"
    )
    assert result["task_id"] == expected
    assert world.tasks[expected].deadline == "2026-08-23T09:00:00+00:00"


@pytest.mark.parametrize(
    "event_type, payload, code",
    [
        ("worker_absence", {"worker_id": "w-002"}, "WORKER_NOT_IN_ACTIVE_WORLD"),
        ("worker_return", {"worker_id": "w-002"}, "WORKER_NOT_IN_ACTIVE_WORLD"),
        (
            "low_stock",
            {"sku": "SKU-1001", "quantity_available": 50},
            "SKU_NOT_IN_ACTIVE_WORLD",
        ),
        (
            "task_deadline",
            {"task_id": "task-001", "deadline": "x"},
            "TASK_NOT_IN_ACTIVE_WORLD",
        ),
    ],
)
def test_yaml_ids_are_not_in_the_datapack_world(
    datapack_ctrl, event_type, payload, code
):
    with pytest.raises(InjectTargetError) as exc:
        _run(datapack_ctrl.inject(event_type, payload))
    assert (exc.value.status_code, exc.value.code) == (404, code)
    assert exc.value.extra["world_source"] == "datapack"


def test_explicit_ids_still_work_on_the_yaml_world(yaml_ctrl):
    result = _inject(yaml_ctrl, "worker_absence", worker_id="w-005")
    assert result["target_resolution"] == "explicit"
    assert yaml_ctrl.world.workers["w-005"].status == "on_leave"


def test_omitted_ids_resolve_on_the_yaml_world(yaml_ctrl):
    # w-001 is active with task-001 in progress
    assert _inject(yaml_ctrl, "worker_absence")["worker_id"] == "w-001"
    # w-001, w-002 and w-004 are not active; w-001 is lowest
    assert _inject(yaml_ctrl, "worker_return")["worker_id"] == "w-001"
    assert _inject(yaml_ctrl, "low_stock", quantity_available=1)["sku"] == "SKU-1001"


def test_blank_id_is_treated_as_omitted(datapack_ctrl):
    result = _inject(datapack_ctrl, "worker_absence", worker_id="  ")
    assert result["target_resolution"] == "resolved"
