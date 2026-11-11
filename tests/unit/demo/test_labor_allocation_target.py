# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
The labor-allocation target prefers tasks with no worker (#309).

The demo analyze route and the Copilot ground a labor recommendation to a
concrete task. They picked the highest-priority pending task with the lowest
id, assigned or not. On the DC-47 DataPack world most pending tasks are
assigned and only wait for their worker, so an allocation could move one of
them while the task that put the wave at risk stayed without a worker. Both
now use ``demo.scheduling.labor_allocation_target``.
"""

from __future__ import annotations

import asyncio

import pytest

from maiw_api.demo.controller import DemoScenarioController, reset_demo_controller
from maiw_api.demo.scheduling import labor_allocation_target


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def reset_singleton():
    reset_demo_controller()
    yield
    reset_demo_controller()


@pytest.fixture
def world():
    ctrl = DemoScenarioController()
    _run(ctrl.start("healthy_baseline"))
    return ctrl.world


def test_a_task_without_a_worker_beats_a_lower_id_assigned_one(world):
    world.tasks["task-000030"].assigned_to = None  # wave-017, high, 10:00
    assert world.tasks["task-000001"].assigned_to is not None  # same wave
    task_id, workers = labor_allocation_target(world)
    assert task_id == "task-000030"
    worker = world.workers[workers[0]]
    assert worker.status == "active" and worker.current_task_id is None


def test_priority_still_orders_tasks_without_a_worker(world):
    world.tasks["task-000050"].assigned_to = None  # wave-018, normal
    world.tasks["task-000030"].assigned_to = None  # wave-017, high
    assert labor_allocation_target(world)[0] == "task-000030"


def test_falls_back_to_assigned_tasks_when_every_task_has_a_worker(world):
    task_id, _ = labor_allocation_target(world)
    assert task_id == "task-000001"  # lowest pending high-priority task


def test_no_idle_worker_is_capacity_unavailable(world):
    for w in world.workers.values():
        w.current_task_id = w.current_task_id or "busy"
    with pytest.raises(ValueError, match="CAPACITY_UNAVAILABLE: no idle workers"):
        labor_allocation_target(world)


def test_the_route_and_the_copilot_use_the_same_target(monkeypatch, world):
    import maiw_api.demo.controller as controller_module
    from maiw_api.copilot.orchestrator import GovernedActionOrchestrator
    from maiw_api.routers.demo import _resolve_labor_allocation_target

    world.tasks["task-000030"].assigned_to = None

    class _Ctrl:
        pass

    ctrl = _Ctrl()
    ctrl.world = world
    monkeypatch.setattr(controller_module, "get_demo_controller", lambda: ctrl)
    orchestrator = GovernedActionOrchestrator.__new__(GovernedActionOrchestrator)
    orchestrator._ctrl = ctrl

    expected = labor_allocation_target(world)
    assert _resolve_labor_allocation_target(None) == expected
    assert orchestrator._resolve_labor_target() == expected
