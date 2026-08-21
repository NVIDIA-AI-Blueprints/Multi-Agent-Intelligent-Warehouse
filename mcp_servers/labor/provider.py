# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
LaborProvider — vendor-neutral labor data source and write boundary.

The Protocol is the extension point for all labor backends:
    MAIWLaborAdapter      — wraps OperationsActionTools workforce methods
    MockLaborProvider     — in-memory, for tests

Execution methods (write capabilities)
---------------------------------------
The provider exposes execution methods — not proposal methods.  Proposals are
built locally in the agent/skill layer.  Only LaborActionExecutor (after
DecisionEngine APPROVED) calls execute_labor_allocation().
"""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

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


@runtime_checkable
class LaborProvider(Protocol):
    """Vendor-neutral labor data source and write boundary."""

    async def get_labor_capacity(
        self, request: LaborCapacityRequest
    ) -> LaborCapacityResult: ...

    async def get_labor_allocation(
        self, request: LaborAllocationRequest
    ) -> LaborAllocationResult: ...

    async def execute_labor_allocation(
        self, request: LaborAllocateRequest
    ) -> LaborAllocateResult: ...


class MockLaborProvider:
    """In-memory labor provider for tests and development."""

    def __init__(self) -> None:
        self._workers: list[LaborWorkerInfo] = [
            LaborWorkerInfo(
                worker_id="w-001", username="alice", full_name="Alice Chen",
                role="operator", status="active", zone="A1",
            ),
            LaborWorkerInfo(
                worker_id="w-002", username="bob", full_name="Bob Smith",
                role="operator", status="active", zone="A1",
            ),
            LaborWorkerInfo(
                worker_id="w-003", username="carol", full_name="Carol Liu",
                role="supervisor", status="active", zone="B2",
            ),
            LaborWorkerInfo(
                worker_id="w-004", username="david", full_name="David Park",
                role="operator", status="inactive", zone="B2",
            ),
        ]
        self._tasks: list[LaborTaskInfo] = [
            LaborTaskInfo(
                task_id="t-001", task_type="PICK", zone="A1",
                status="in_progress", assigned_to="w-001", priority="high",
            ),
            LaborTaskInfo(
                task_id="t-002", task_type="PACK", zone="A1",
                status="pending", assigned_to=None, priority="medium",
            ),
        ]

    async def get_labor_capacity(
        self, request: LaborCapacityRequest
    ) -> LaborCapacityResult:
        workers = self._workers
        if request.zone:
            workers = [w for w in workers if w.zone == request.zone]
        if request.status_filter:
            workers = [w for w in workers if w.status == request.status_filter]
        available = sum(1 for w in workers if w.status == "active")
        total = len(workers)
        util = round((total - available) / max(total, 1) * 100, 1)
        return LaborCapacityResult(
            workers=workers,
            total_workers=total,
            available_workers=available,
            utilization_pct=util,
            zone=request.zone,
            shift=request.shift,
            source="mock",
        )

    async def get_labor_allocation(
        self, request: LaborAllocationRequest
    ) -> LaborAllocationResult:
        tasks = self._tasks
        if request.worker_id:
            tasks = [t for t in tasks if t.assigned_to == request.worker_id]
        if request.zone:
            tasks = [t for t in tasks if t.zone == request.zone]
        if request.task_type:
            tasks = [t for t in tasks if t.task_type == request.task_type]
        if request.status_filter:
            tasks = [t for t in tasks if t.status == request.status_filter]
        in_progress = sum(1 for t in tasks if t.status == "in_progress")
        pending = sum(1 for t in tasks if t.status == "pending")
        return LaborAllocationResult(
            allocations=tasks,
            total_tasks=len(tasks),
            in_progress_count=in_progress,
            pending_count=pending,
            source="mock",
        )

    async def execute_labor_allocation(
        self, request: LaborAllocateRequest
    ) -> LaborAllocateResult:
        return LaborAllocateResult(
            success=True,
            allocation_id=str(uuid.uuid4()),
            task_id=request.task_id,
            worker_ids=request.worker_ids,
            proposal_id=request.proposal_id,
            decision_id=request.decision_id,
            source="mock",
            message=f"Allocated {len(request.worker_ids)} worker(s) to task {request.task_id}",
        )
