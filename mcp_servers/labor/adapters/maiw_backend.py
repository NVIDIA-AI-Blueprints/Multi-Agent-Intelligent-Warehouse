# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIWLaborAdapter — wraps existing OperationsActionTools workforce methods.

Architecture note
-----------------
This adapter is the translation layer between the vendor-neutral LaborProvider
Protocol and the MAIW backend (OperationsActionTools → PostgreSQL users table
and WMS work queue). It does NOT duplicate SQL logic — it delegates entirely
to the existing OperationsActionTools class.

OperationsActionTools.get_workforce_status() requires asyncpg and is only
available when the full MAIW infrastructure is running. Tests use
MockLaborProvider instead.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

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

logger = logging.getLogger(__name__)


class MAIWLaborAdapter:
    """Wraps OperationsActionTools for the LaborProvider Protocol."""

    def __init__(self, action_tools: Any | None = None) -> None:
        self._tools = action_tools

    async def _get_tools(self) -> Any:
        if self._tools is None:
            from src.api.agents.operations.action_tools import OperationsActionTools
            self._tools = OperationsActionTools()
        return self._tools

    async def get_labor_capacity(
        self, request: LaborCapacityRequest
    ) -> LaborCapacityResult:
        tools = await self._get_tools()
        raw = await tools.get_workforce_status(
            shift=request.shift,
            status=request.status_filter,
            zone=request.zone,
        )
        workers_raw = raw.get("workforce", [])
        workers = [
            LaborWorkerInfo(
                worker_id=str(w.get("worker_id", "")),
                username=w.get("username", ""),
                full_name=w.get("full_name"),
                role=w.get("role", "operator"),
                status=w.get("status", "active"),
                zone=request.zone,
            )
            for w in workers_raw
        ]
        active = sum(1 for w in workers if w.status == "active")
        total = len(workers)
        util = round((total - active) / max(total, 1) * 100, 1)
        return LaborCapacityResult(
            workers=workers,
            total_workers=total,
            available_workers=active,
            utilization_pct=util,
            zone=request.zone,
            shift=request.shift,
            source="maiw-backend",
        )

    async def get_labor_allocation(
        self, request: LaborAllocationRequest
    ) -> LaborAllocationResult:
        tools = await self._get_tools()
        raw = await tools.get_task_status(
            worker_id=request.worker_id,
            task_type=request.task_type,
            status=request.status_filter,
        )
        tasks_raw = raw.get("tasks", [])
        tasks = [
            LaborTaskInfo(
                task_id=str(t.get("task_id") or t.get("id", "")),
                task_type=t.get("task_type", "PICK"),
                zone=t.get("zone") or request.zone,
                status=t.get("status", "pending"),
                assigned_to=str(t.get("assigned_to") or t.get("worker_id") or ""),
                priority=t.get("priority", "medium"),
            )
            for t in tasks_raw
        ]
        in_progress = sum(1 for t in tasks if t.status == "in_progress")
        pending = sum(1 for t in tasks if t.status == "pending")
        return LaborAllocationResult(
            allocations=tasks,
            total_tasks=len(tasks),
            in_progress_count=in_progress,
            pending_count=pending,
            source="maiw-backend",
        )

    async def execute_labor_allocation(
        self, request: LaborAllocateRequest
    ) -> LaborAllocateResult:
        tools = await self._get_tools()
        allocation_id = str(uuid.uuid4())
        try:
            await tools.assign_task(
                task_id=request.task_id,
                worker_id=request.worker_ids[0] if request.worker_ids else "",
                assignment_type="manual",
            )
            return LaborAllocateResult(
                success=True,
                allocation_id=allocation_id,
                task_id=request.task_id,
                worker_ids=request.worker_ids,
                proposal_id=request.proposal_id,
                decision_id=request.decision_id,
                source="maiw-backend",
                message=f"Allocated {len(request.worker_ids)} worker(s) to {request.task_id}",
            )
        except Exception as exc:
            logger.error("Labor allocation write failed: %s", exc)
            return LaborAllocateResult(
                success=False,
                allocation_id=None,
                task_id=request.task_id,
                worker_ids=request.worker_ids,
                proposal_id=request.proposal_id,
                decision_id=request.decision_id,
                source="maiw-backend",
                message=str(exc),
            )
