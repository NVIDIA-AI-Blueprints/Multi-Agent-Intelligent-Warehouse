# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Grounding for governed proposals built against the demo world: the default
maintenance slot and the concrete labor-allocation target.

Shared by the copilot's GovernedActionOrchestrator and the demo
analyze-disruption route, so both propose the same slot and the same target.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def default_scheduled_for(ctrl: Any = None) -> str:
    """
    Next-day slot for maintenance proposals that carry no explicit time.

    Demo mode runs on the world's SimulationClock, which is deliberately not
    tied to wall time, so "tomorrow" is the simulated now + 1 day. Without a
    simulation clock it falls back to UTC wall time.

    The slot is fixed when the proposal is built. The DecisionEngine rejects it
    at authorization if the clock has passed it by then (rule
    ``maintenance.scheduled_for_past``), so a late approval never executes a
    slot in the past.
    """
    clock = getattr(getattr(ctrl, "world", None), "clock", None)
    now = clock.now() if clock is not None else datetime.now(timezone.utc)
    return (now + timedelta(days=1)).isoformat()


_WAVE_TASK_TYPES = frozenset({"PICK", "PACK", "SHIP", "RECEIVE", "PUTAWAY", "TRANSFER"})


def labor_allocation_target(world: Any) -> tuple[str, list[str]]:
    """
    Ground a labor-allocation recommendation to a concrete (task_id, [worker_id]).

    The agent recommends at the semantic level ("wave_pending_tasks",
    "zone_A"); in production a task planner would supply the ids. The demo
    picks the pending wave task most at risk and an idle worker:

    - tasks with no worker first: they are what wave risk counts, while an
      assigned pending task starts as soon as its worker is free (#309);
    - then high priority, the earliest deadline and the lowest task id;
    - an active worker with no current task, in the task's zone when possible.

    Raises ValueError (CAPACITY_UNAVAILABLE) when no pair exists, so a proposal
    fails loudly instead of executing as a no-op that reports success.
    """
    if world is None:
        raise ValueError("CAPACITY_UNAVAILABLE: warehouse world not available")

    pending = sorted(
        [
            t
            for t in world.tasks.values()
            if t.status == "pending" and t.task_type in _WAVE_TASK_TYPES
        ],
        key=lambda t: (
            t.assigned_to is not None,
            0 if t.priority == "high" else 1 if t.priority == "medium" else 2,
            t.deadline or "9999",
            t.task_id,
        ),
    )
    available = [
        w
        for w in world.workers.values()
        if w.status == "active" and w.current_task_id is None
    ]

    if not pending:
        raise ValueError("CAPACITY_UNAVAILABLE: no pending wave tasks to allocate")
    if not available:
        active = sum(1 for w in world.workers.values() if w.status == "active")
        raise ValueError(
            f"CAPACITY_UNAVAILABLE: no idle workers available "
            f"({active} active workers all occupied)"
        )

    task = pending[0]
    same_zone = [w for w in available if w.zone == task.zone]
    worker = same_zone[0] if same_zone else available[0]
    return task.task_id, [worker.worker_id]
