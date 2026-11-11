# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Work progresses in the DC-47 DataPack world (#309).

The DataPack world used to be static. Its one in-progress task had no start
time, so it never completed; its 119 pending tasks were all assigned, and
assigned pending tasks never started; no task had a deadline, although every
wave is constrained by a carrier cutoff. These tests run the controller the
way the API does, on ``healthy_baseline``, the scenario that runs on the
DataPack world.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from maiw_api.demo.controller import DemoScenarioController, reset_demo_controller
from maiw_api.demo.kpi import DemoKPIEngine
from maiw_api.demo.world import SimulationClock

SCENARIO = "healthy_baseline"
TICK_SECONDS = 60


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def reset_singleton():
    reset_demo_controller()
    yield
    reset_demo_controller()


@pytest.fixture
def ctrl() -> DemoScenarioController:
    controller = DemoScenarioController()
    _run(controller.start(SCENARIO))
    assert controller.world._scenario_world is not None, "DataPack world expected"
    return controller


def _in_progress_by_worker(ctrl) -> dict[str, list[str]]:
    by_worker: dict[str, list[str]] = {}
    for task in ctrl.world.tasks.values():
        if task.status == "in_progress" and task.assigned_to:
            by_worker.setdefault(task.assigned_to, []).append(task.task_id)
    return by_worker


def test_task_in_progress_at_load_has_a_start_time_and_completes(ctrl):
    in_progress = [t for t in ctrl.world.tasks.values() if t.status == "in_progress"]
    assert [t.task_id for t in in_progress] == ["task-000000"]
    task = in_progress[0]
    assert task.started_at_sim_seconds == 0
    worker = ctrl.world.workers[task.assigned_to]
    assert worker.current_task_id == task.task_id

    for _ in range(task.processing_duration_seconds // TICK_SECONDS):
        _run(ctrl.tick(TICK_SECONDS))
    assert task.status == "completed"


def test_assigned_pending_tasks_start_one_per_free_worker(ctrl):
    workers_with_work = {
        t.assigned_to
        for t in ctrl.world.tasks.values()
        if t.status in ("pending", "in_progress") and t.assigned_to
    }
    _run(ctrl.tick(TICK_SECONDS))

    by_worker = _in_progress_by_worker(ctrl)
    assert set(by_worker) == workers_with_work
    assert all(len(ids) == 1 for ids in by_worker.values())
    for worker_id, (task_id,) in by_worker.items():
        assert ctrl.world.workers[worker_id].current_task_id == task_id
        if task_id != "task-000000":
            assert ctrl.world.tasks[task_id].started_at_sim_seconds == TICK_SECONDS


def test_a_worker_runs_its_assigned_tasks_one_after_another(ctrl):
    queues: dict[str, list[str]] = {}
    for t in ctrl.world.tasks.values():
        if t.assigned_to:
            queues.setdefault(t.assigned_to, []).append(t.task_id)
    worker_id, task_ids = max(sorted(queues.items()), key=lambda kv: len(kv[1]))
    assert len(task_ids) >= 2

    seen_running: list[str] = []
    for _ in range(30):
        _run(ctrl.tick(TICK_SECONDS))
        running = _in_progress_by_worker(ctrl).get(worker_id, [])
        assert len(running) <= 1
        if running and running[0] not in seen_running:
            seen_running.append(running[0])
    assert sorted(seen_running) == sorted(task_ids)
    assert all(ctrl.world.tasks[tid].status == "completed" for tid in task_ids)


def test_absent_workers_tasks_stay_pending(ctrl):
    worker_id = next(
        t.assigned_to
        for t in sorted(ctrl.world.tasks.values(), key=lambda t: t.task_id)
        if t.status == "pending" and t.assigned_to
    )
    _run(ctrl.inject("worker_absence", {"worker_id": worker_id}))
    for _ in range(5):
        _run(ctrl.tick(TICK_SECONDS))
    theirs = [t for t in ctrl.world.tasks.values() if t.assigned_to == worker_id]
    assert theirs and all(t.status == "pending" for t in theirs)


def test_unassigned_pending_tasks_wait_for_an_allocation(ctrl):
    task = ctrl.world.tasks["task-000001"]
    assert task.status == "pending"
    task.assigned_to = None
    for _ in range(5):
        _run(ctrl.tick(TICK_SECONDS))
    assert task.status == "pending"
    assert task.started_at_sim_seconds is None


def test_tasks_take_their_waves_carrier_cutoff_as_deadline(ctrl):
    from maiw_world.edges import RelationshipType
    from maiw_world.entities import EntityType

    graph = ctrl.world._scenario_world.base_graph
    sim_date = SimulationClock._EPOCH.date()
    waves = graph.entities_by_type(EntityType.WAVE)
    assert waves
    for wave in waves:
        cutoffs = [
            graph.get_entity(e.target_id)
            for e in graph.outgoing_edges(wave.id, RelationshipType.CONSTRAINED_BY)
        ]
        assert cutoffs, f"{wave.id} has no carrier cutoff"
        earliest = min(c.cutoff_time.time() for c in cutoffs)
        expected = datetime.combine(
            sim_date, earliest, tzinfo=cutoffs[0].cutoff_time.tzinfo
        )
        for edge in graph.incoming_edges(wave.id, RelationshipType.BELONGS_TO):
            deadline = ctrl.world.tasks[edge.source_id].deadline
            assert datetime.fromisoformat(deadline) == expected, edge.source_id

    # The active wave is due at the FedEx Priority cutoff, 10:00 on shift day.
    assert ctrl.world.tasks["task-000000"].deadline == "2026-08-23T10:00:00+00:00"


def test_healthy_baseline_completes_its_work_on_time(ctrl):
    k0 = DemoKPIEngine(ctrl.world).compute()
    assert k0.pending_backlog == 119
    assert k0.wave_risk_level == "none"

    previous = 0.0
    for i in range(30):
        _run(ctrl.tick(TICK_SECONDS))
        kpi = DemoKPIEngine(ctrl.world).compute()
        assert kpi.wave_risk_level == "none", f"tick {i + 1}"
        assert kpi.projected_service_level == 100.0, f"tick {i + 1}"
        assert kpi.wave_completion_pct >= previous, f"tick {i + 1}"
        previous = kpi.wave_completion_pct
    assert kpi.pending_backlog == 0
    assert kpi.wave_completion_pct == 100.0
    assert all(t.status == "completed" for t in ctrl.world.tasks.values())


def test_reset_restores_the_loaded_world(ctrl):
    for _ in range(10):
        _run(ctrl.tick(TICK_SECONDS))
    _run(ctrl.reset())

    assert ctrl.world.clock.elapsed_seconds == 0
    statuses = [t.status for t in ctrl.world.tasks.values()]
    assert statuses.count("in_progress") == 1
    assert statuses.count("pending") == 119
    assert ctrl.world.tasks["task-000000"].started_at_sim_seconds == 0
