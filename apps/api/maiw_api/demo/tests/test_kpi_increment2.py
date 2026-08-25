# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Deterministic tests for KPI Increment 2:
- Task progression (completion after processing_duration_seconds)
- wave_completion_pct and simulated_throughput KPI metrics
- Recovery detection
- stale_state scenario wave risk constraint
- Labor allocation sets started_at_sim_seconds
"""

from __future__ import annotations

import pathlib

import pytest
import pytest_asyncio

from maiw_api.demo.kpi import DemoKPIEngine
from maiw_api.demo.world import DemoWarehouseWorld, _DEFAULT_PROCESSING_SECONDS

# ── Helpers ───────────────────────────────────────────────────────────────────

_SCENARIOS_DIR = pathlib.Path(__file__).parent.parent / "scenarios"


def _minimal_world_with_task(
    task_type: str = "PICK",
    status: str = "in_progress",
    started_at: int = 0,
    clock_offset: int = 0,
) -> DemoWarehouseWorld:
    """Build a minimal world with one worker and one task."""
    w = DemoWarehouseWorld()
    w.seed(
        {
            "clock_offset_seconds": clock_offset,
            "inventory": [],
            "equipment": [],
            "workers": [
                {
                    "worker_id": "w-001",
                    "username": "alice",
                    "full_name": "Alice Chen",
                    "role": "operator",
                    "status": "active",
                    "zone": "A1",
                    "current_task_id": "task-001" if status == "in_progress" else None,
                }
            ],
            "tasks": [
                {
                    "task_id": "task-001",
                    "task_type": task_type,
                    "zone": "A1",
                    "status": status,
                    "assigned_to": "w-001" if status == "in_progress" else None,
                    "priority": "medium",
                }
            ],
        },
        rng_seed=42,
    )
    if status == "in_progress":
        # Override started_at after seed (seed sets it to clock.elapsed_seconds)
        w.tasks["task-001"].started_at_sim_seconds = started_at
    return w


# ── Test 1: Task completes after processing_duration_seconds ──────────────────

def test_task_progression_completes_after_duration():
    duration = _DEFAULT_PROCESSING_SECONDS["PICK"]  # 300
    w = _minimal_world_with_task(task_type="PICK", started_at=0)
    task = w.tasks["task-001"]
    worker = w.workers["w-001"]

    assert task.processing_duration_seconds == duration

    # Manually advance via controller logic equivalent
    from maiw_api.demo.controller import DemoScenarioController
    ctrl = DemoScenarioController()
    ctrl.world = w
    ctrl._scenario = object()  # non-None sentinel

    # Tick past the processing duration
    w.clock.tick(duration)
    elapsed = w.clock.elapsed_seconds
    completed = ctrl._advance_task_progression(elapsed)

    assert completed == 1
    assert task.status == "completed"
    assert worker.current_task_id is None
    assert task.assigned_to is None
    assert len(w._completion_log) == 1
    assert w._completion_log[0] == (duration, 1)


# ── Test 2: Task NOT completed before duration ────────────────────────────────

def test_task_not_completed_before_duration():
    duration = _DEFAULT_PROCESSING_SECONDS["PICK"]  # 300
    w = _minimal_world_with_task(task_type="PICK", started_at=0)
    task = w.tasks["task-001"]

    from maiw_api.demo.controller import DemoScenarioController
    ctrl = DemoScenarioController()
    ctrl.world = w
    ctrl._scenario = object()

    # Tick to just before duration
    w.clock.tick(duration - 1)
    elapsed = w.clock.elapsed_seconds
    completed = ctrl._advance_task_progression(elapsed)

    assert completed == 0
    assert task.status == "in_progress"


# ── Test 3: wave_completion_pct updates after task completes ──────────────────

def test_wave_completion_pct_updates():
    duration = _DEFAULT_PROCESSING_SECONDS["PICK"]
    w = _minimal_world_with_task(task_type="PICK", started_at=0)

    kpi_before = DemoKPIEngine(w).compute()
    assert kpi_before.wave_completion_pct == 0.0

    from maiw_api.demo.controller import DemoScenarioController
    ctrl = DemoScenarioController()
    ctrl.world = w
    ctrl._scenario = object()

    w.clock.tick(duration)
    ctrl._advance_task_progression(w.clock.elapsed_seconds)

    kpi_after = DemoKPIEngine(w).compute()
    assert kpi_after.wave_completion_pct > 0.0


# ── Test 4: simulated_throughput counts work units ────────────────────────────

def test_simulated_throughput():
    w = DemoWarehouseWorld()
    # Inject 3 completed tasks directly into completion log
    w._completion_log = [(100, 1), (200, 1), (300, 1)]
    w.clock.tick(400)  # ensure window_start = 400-3600 = negative, so all are in window

    kpi = DemoKPIEngine(w).compute()
    assert kpi.simulated_throughput == 3.0


# ── Test 5: Recovery detection ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_recovery_detection():
    from maiw_api.demo.controller import DemoScenarioController

    ctrl = DemoScenarioController()
    await ctrl.start("equipment_failure")

    # Manually set disruption time
    ctrl.world._disruption_sim_time = ctrl.world.clock.elapsed_seconds

    # Force world into a recovered state: no pending tasks with deadline+high priority
    for t in ctrl.world.tasks.values():
        if t.status == "pending":
            t.status = "completed"
            t.assigned_to = None

    elapsed = ctrl.world.clock.elapsed_seconds
    result = ctrl._check_recovery(elapsed)

    assert result is True
    assert ctrl._recovery_sim_time is not None
    assert ctrl.world._recovery_sim_time is not None

    kpi = DemoKPIEngine(ctrl.world, ctrl._last_analyze_wall_time).compute()
    assert kpi.time_to_recovery_seconds is not None
    assert kpi.time_to_recovery_seconds >= 0


# ── Test 6: Reset clears completion log ──────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario_reset_clears_completion_log():
    from maiw_api.demo.controller import DemoScenarioController

    ctrl = DemoScenarioController()
    await ctrl.start("healthy_baseline")

    # Inject completions
    ctrl.world._completion_log.append((100, 1))
    ctrl.world._completion_log.append((200, 1))

    kpi_before = DemoKPIEngine(ctrl.world).compute()
    # After reset, completion log should be empty
    await ctrl.reset()

    assert ctrl.world._completion_log == []
    kpi_after = DemoKPIEngine(ctrl.world).compute()
    assert kpi_after.wave_completion_pct == 0.0


# ── Test 7: stale_state has no CRITICAL wave risk ─────────────────────────────

def test_stale_state_no_wave_critical():
    import yaml
    data = yaml.safe_load((_SCENARIOS_DIR / "stale_state.yaml").read_text())
    initial = dict(data.get("initial_state", {}))
    initial["clock_offset_seconds"] = data.get("clock_offset_seconds", 0)
    w = DemoWarehouseWorld()
    w.seed(initial, rng_seed=42)
    snap = DemoKPIEngine(w).compute()
    assert snap.wave_risk_level != "critical", (
        f"stale_state should not be CRITICAL, got {snap.wave_risk_level}"
    )
    assert snap.sim_time_seconds >= 0


# ── Test 8: No execution → no recovery in stale_state ────────────────────────

def test_no_execution_no_recovery():
    import yaml
    data = yaml.safe_load((_SCENARIOS_DIR / "stale_state.yaml").read_text())
    initial = dict(data.get("initial_state", {}))
    initial["clock_offset_seconds"] = data.get("clock_offset_seconds", 0)
    w = DemoWarehouseWorld()
    w.seed(initial, rng_seed=42)

    snap_before = DemoKPIEngine(w).compute()
    # No disruption set, no execution — recovery time should be None
    assert snap_before.time_to_recovery_seconds is None
    # Backlog should be stable (2 pending tasks)
    assert snap_before.pending_backlog == 2


# ── Test 9: labor_allocate sets started_at_sim_seconds ───────────────────────

@pytest.mark.asyncio
async def test_labor_allocate_sets_started_at_sim_seconds():
    from maiw_api.demo.controller import DemoScenarioController
    from maiw_api.demo.providers.labor import SimulationLaborProvider
    from maiw_mcp.contracts.labor import LaborAllocateRequest

    ctrl = DemoScenarioController()
    await ctrl.start("labor_constraint_wave_risk")

    # Find a pending task and a free active worker
    pending = [t for t in ctrl.world.tasks.values() if t.status == "pending"]
    free_workers = [
        wk for wk in ctrl.world.workers.values()
        if wk.status == "active" and wk.current_task_id is None
    ]
    assert pending, "Expected at least one pending task"
    assert free_workers, "Expected at least one free active worker"

    task = pending[0]
    worker = free_workers[0]
    assert task.started_at_sim_seconds is None

    provider = ctrl.providers.labor
    req = LaborAllocateRequest(
        warehouse_id="DC-47",
        task_id=task.task_id,
        task_type=task.task_type,
        worker_ids=[worker.worker_id],
        proposal_id="test-proposal",
        decision_id="test-decision",
    )
    await provider.execute_labor_allocation(req)

    assert task.started_at_sim_seconds is not None
    assert task.started_at_sim_seconds == ctrl.world.clock.elapsed_seconds


# ── Test 10: Deterministic same seed → same completion count ──────────────────

@pytest.mark.asyncio
async def test_deterministic_same_seed_same_result():
    from maiw_api.demo.controller import DemoScenarioController

    async def run_scenario(n_ticks: int) -> int:
        ctrl = DemoScenarioController()
        await ctrl.start("labor_constraint_wave_risk")
        # Manually start one task so progression can happen
        pending = [t for t in ctrl.world.tasks.values() if t.status == "pending"]
        free = [
            wk for wk in ctrl.world.workers.values()
            if wk.status == "active" and wk.current_task_id is None
        ]
        if pending and free:
            t = pending[0]
            wk = free[0]
            t.status = "in_progress"
            t.assigned_to = wk.worker_id
            wk.current_task_id = t.task_id
            t.started_at_sim_seconds = ctrl.world.clock.elapsed_seconds

        for _ in range(n_ticks):
            await ctrl.tick(60)

        return len(ctrl.world._completion_log)

    count1 = await run_scenario(10)
    count2 = await run_scenario(10)
    assert count1 == count2, f"Non-deterministic: {count1} != {count2}"
