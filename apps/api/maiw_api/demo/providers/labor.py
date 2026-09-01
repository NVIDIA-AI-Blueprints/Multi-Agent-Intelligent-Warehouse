# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
SimulationLaborProvider — implements LaborProvider against DemoWarehouseWorld.

Phase 10E Batch 1: canonical outcome semantics, execution_id propagation,
mutation counter, and fault injection support.

Write outcome semantics
-----------------------
allocate:
    FAILED   — task_id not found in world state (raises BackendUnavailable)
    NO_OP    — task already assigned to exactly these worker_ids
    DEFERRED — no workers available (worker_ids list empty and no idle workers)
    EXECUTED — mutation committed
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from maiw_mcp.contracts.labor import (
    LaborAllocateRequest,
    LaborAllocateResult,
    LaborAllocationRequest,
    LaborAllocationResult,
    LaborCapacityRequest,
    LaborCapacityResult,
    LaborTaskInfo,
    LaborWorkerInfo,
)
from maiw_mcp.errors import BackendUnavailable

if TYPE_CHECKING:
    from maiw_api.demo.events import ScenarioEventBus
    from maiw_api.demo.world import DemoWarehouseWorld


class SimulationLaborProvider:
    """Implements LaborProvider against the shared DemoWarehouseWorld."""

    def __init__(self, world: "DemoWarehouseWorld", bus: "ScenarioEventBus") -> None:
        self._world = world
        self._bus = bus
        # Reliability testing instrumentation
        self._mutation_count: int = 0
        self._post_mutation_fault: Exception | None = None

    async def get_labor_capacity(
        self, request: LaborCapacityRequest
    ) -> LaborCapacityResult:
        workers = self._world.workers_list(
            zone=request.zone,
            status_filter=request.status_filter or None,
        )
        if request.status_filter == "active":
            workers = [w for w in workers if w.status == "active"]
        active_count = sum(1 for w in workers if w.status == "active")
        # idle = active workers with no task currently assigned
        available = sum(1 for w in workers if w.status == "active" and w.current_task_id is None)
        total = len(workers)
        # utilization = fraction of active workers currently running a task
        util = round((active_count - available) / max(active_count, 1) * 100, 1)
        return LaborCapacityResult(
            workers=[
                LaborWorkerInfo(
                    worker_id=w.worker_id,
                    username=w.username,
                    full_name=w.full_name,
                    role=w.role,
                    status=w.status,
                    zone=w.zone,
                )
                for w in workers
            ],
            total_workers=total,
            available_workers=available,
            utilization_pct=util,
            zone=request.zone,
            shift=request.shift,
            source=self._world.SOURCE,
        )

    async def get_labor_allocation(
        self, request: LaborAllocationRequest
    ) -> LaborAllocationResult:
        tasks = self._world.tasks_list(
            zone=request.zone,
            status_filter=request.status_filter,
            task_type=request.task_type,
            worker_id=request.worker_id,
        )
        in_progress = sum(1 for t in tasks if t.status == "in_progress")
        pending = sum(1 for t in tasks if t.status == "pending")
        return LaborAllocationResult(
            allocations=[
                LaborTaskInfo(
                    task_id=t.task_id,
                    task_type=t.task_type,
                    zone=t.zone,
                    status=t.status,
                    assigned_to=t.assigned_to,
                    priority=t.priority,
                )
                for t in tasks
            ],
            total_tasks=len(tasks),
            in_progress_count=in_progress,
            pending_count=pending,
            source=self._world.SOURCE,
        )

    async def execute_labor_allocation(
        self, request: LaborAllocateRequest
    ) -> LaborAllocateResult:
        task = self._world.tasks.get(request.task_id)

        # FAILED: task not found — raise so executor records FAILED (no mutation)
        if task is None:
            raise BackendUnavailable(
                f"Task '{request.task_id}' not found in world state"
            )

        # DEFERRED: no workers provided and none available
        if not request.worker_ids:
            available_workers = [
                w
                for w in self._world.workers.values()
                if w.status == "active" and w.current_task_id is None
            ]
            if not available_workers:
                return LaborAllocateResult(
                    success=False,
                    allocation_id=None,
                    task_id=request.task_id,
                    worker_ids=request.worker_ids,
                    proposal_id=request.proposal_id,
                    decision_id=request.decision_id,
                    execution_id=request.execution_id,
                    outcome="deferred",
                    source=self._world.SOURCE,
                    message=f"[SIM] DEFERRED: no available workers for task {request.task_id}",
                )

        # NO_OP: task already assigned to exactly the same worker
        if (
            task.status == "in_progress"
            and task.assigned_to
            and request.worker_ids
            and task.assigned_to == request.worker_ids[0]
        ):
            return LaborAllocateResult(
                success=True,
                allocation_id=None,
                task_id=request.task_id,
                worker_ids=request.worker_ids,
                proposal_id=request.proposal_id,
                decision_id=request.decision_id,
                execution_id=request.execution_id,
                outcome="no_op",
                source=self._world.SOURCE,
                message=f"[SIM] NO_OP: task {request.task_id} already assigned to {task.assigned_to}",
            )

        # ── MUTATION ────────────────────────────────────────────────────────────
        task.status = "in_progress"
        if request.worker_ids:
            task.assigned_to = request.worker_ids[0]
        task.started_at_sim_seconds = self._world.clock.elapsed_seconds

        for worker_id in request.worker_ids:
            worker = self._world.workers.get(worker_id)
            if worker is not None:
                worker.current_task_id = request.task_id

        allocation_id = str(uuid.uuid4())
        self._mutation_count += 1

        import asyncio

        asyncio.create_task(
            self._bus.publish_labor_write(
                task_id=request.task_id,
                worker_ids=request.worker_ids,
            )
        )

        # Fault injection: raise AFTER mutation to simulate ambiguous write
        if self._post_mutation_fault is not None:
            fault = self._post_mutation_fault
            self._post_mutation_fault = None
            raise fault

        return LaborAllocateResult(
            success=True,
            allocation_id=allocation_id,
            task_id=request.task_id,
            worker_ids=request.worker_ids,
            proposal_id=request.proposal_id,
            decision_id=request.decision_id,
            execution_id=request.execution_id,
            outcome="executed",
            source=self._world.SOURCE,
            message=f"[SIM] Allocated {len(request.worker_ids)} worker(s) to {request.task_id}",
        )
