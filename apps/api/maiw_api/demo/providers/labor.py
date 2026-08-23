# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
SimulationLaborProvider — implements LaborProvider against DemoWarehouseWorld.

Write: execute_labor_allocation mutates task.assigned_to and worker.current_task_id
in the shared world, and publishes a ScenarioEvent.
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

if TYPE_CHECKING:
    from maiw_api.demo.events import ScenarioEventBus
    from maiw_api.demo.world import DemoWarehouseWorld


class SimulationLaborProvider:
    """Implements LaborProvider against the shared DemoWarehouseWorld."""

    def __init__(self, world: "DemoWarehouseWorld", bus: "ScenarioEventBus") -> None:
        self._world = world
        self._bus = bus

    async def get_labor_capacity(
        self, request: LaborCapacityRequest
    ) -> LaborCapacityResult:
        workers = self._world.workers_list(
            zone=request.zone,
            status_filter=request.status_filter or None,
        )
        # When status_filter is the default "active", apply it
        if request.status_filter == "active":
            workers = [w for w in workers if w.status == "active"]
        available = sum(1 for w in workers if w.status == "active")
        total = len(workers)
        util = round((total - available) / max(total, 1) * 100, 1)
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
        if task is not None:
            task.status = "in_progress"
            if request.worker_ids:
                task.assigned_to = request.worker_ids[0]

        for worker_id in request.worker_ids:
            worker = self._world.workers.get(worker_id)
            if worker is not None:
                worker.current_task_id = request.task_id

        import asyncio
        asyncio.create_task(self._bus.publish_labor_write(
            task_id=request.task_id,
            worker_ids=request.worker_ids,
        ))

        return LaborAllocateResult(
            success=True,
            allocation_id=str(uuid.uuid4()),
            task_id=request.task_id,
            worker_ids=request.worker_ids,
            proposal_id=request.proposal_id,
            decision_id=request.decision_id,
            source=self._world.SOURCE,
            message=f"[SIM] Allocated {len(request.worker_ids)} worker(s) to {request.task_id}",
        )
