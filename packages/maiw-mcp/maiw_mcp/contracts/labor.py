# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Labor domain contracts — typed request/result schemas and capability metadata.

Capabilities implemented:
    warehouse.labor.get_capacity     — READ  — workforce availability by zone/shift
    warehouse.labor.get_allocation   — READ  — active task assignments per worker
    warehouse.labor.allocate         — WRITE — assign workers to a task (MEDIUM risk)

Only capabilities backed by existing MAIW backend behavior (OperationsActionTools) are defined.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .common import CapabilityMetadata


# ── Shared types ───────────────────────────────────────────────────────────────


class LaborWorkerInfo(BaseModel):
    """Operational summary for a single worker."""

    worker_id: str
    username: str
    full_name: str | None = None
    role: str = Field(description="operator | supervisor | manager")
    status: str = Field(description="active | inactive | on_leave")
    zone: str | None = None


class LaborTaskInfo(BaseModel):
    """Operational summary for a labor task assignment."""

    task_id: str
    task_type: str
    zone: str | None = None
    status: str = Field(description="pending | in_progress | completed | failed | cancelled")
    assigned_to: str | None = None
    priority: str = "medium"


# ── Get Capacity ───────────────────────────────────────────────────────────────


class LaborCapacityRequest(BaseModel):
    """Request workforce capacity for a zone/shift."""

    warehouse_id: str = "default"
    zone: str | None = None
    shift: str | None = None
    status_filter: str = Field(default="active", description="Worker status filter")


class LaborCapacityResult(BaseModel):
    """Workforce capacity snapshot."""

    workers: list[LaborWorkerInfo] = Field(default_factory=list)
    total_workers: int = 0
    available_workers: int = 0
    utilization_pct: float = Field(default=0.0, description="0–100")
    zone: str | None = None
    shift: str | None = None
    source: str = "mock"


LABOR_GET_CAPACITY_METADATA = CapabilityMetadata(
    name="warehouse.labor.get_capacity",
    version=1,
    domain="labor",
    side_effect="read",
    risk="read_only",
    idempotent=True,
    timeout_seconds=10,
    required_permission="labor:read",
    description=(
        "Return current workforce capacity: available workers, utilization, "
        "and worker list for a given zone/shift. Read-only; no state mutation."
    ),
)


# ── Get Allocation ─────────────────────────────────────────────────────────────


class LaborAllocationRequest(BaseModel):
    """Request current task allocations (what each worker is doing)."""

    warehouse_id: str = "default"
    worker_id: str | None = None
    zone: str | None = None
    task_type: str | None = None
    status_filter: str | None = None


class LaborAllocationResult(BaseModel):
    """Current task allocations across the labor force."""

    allocations: list[LaborTaskInfo] = Field(default_factory=list)
    total_tasks: int = 0
    in_progress_count: int = 0
    pending_count: int = 0
    source: str = "mock"


LABOR_GET_ALLOCATION_METADATA = CapabilityMetadata(
    name="warehouse.labor.get_allocation",
    version=1,
    domain="labor",
    side_effect="read",
    risk="read_only",
    idempotent=True,
    timeout_seconds=10,
    required_permission="labor:read",
    description=(
        "Return current task allocations: which workers are assigned to which tasks. "
        "Read-only; no state mutation."
    ),
)


# ── Allocate (WRITE) ───────────────────────────────────────────────────────────


class LaborAllocateRequest(BaseModel):
    """Execute an approved labor allocation — assigns workers to a task."""

    warehouse_id: str
    task_id: str
    task_type: str
    worker_ids: list[str]
    zone: str | None = None
    priority: str = "medium"
    notes: str | None = None
    proposal_id: str = Field(..., description="Bound ActionProposal.proposal_id")
    decision_id: str = Field(..., description="Bound DecisionResult.result_id")
    execution_id: str | None = Field(default=None, description="MAIW execution identity, propagated from BaseActionExecutor")


class LaborAllocateResult(BaseModel):
    """Result of a labor allocation write."""

    success: bool
    allocation_id: str | None = None
    task_id: str
    worker_ids: list[str]
    proposal_id: str
    decision_id: str
    execution_id: str | None = None
    outcome: str = "executed"
    source: str = "mock"
    message: str = ""


LABOR_ALLOCATE_METADATA = CapabilityMetadata(
    name="warehouse.labor.allocate",
    version=1,
    domain="labor",
    side_effect="write",
    risk="medium",
    idempotent=False,
    timeout_seconds=15,
    required_permission="labor:execute",
    description=(
        "Execute an approved labor allocation write. "
        "Assigns one or more workers to a task in a zone. "
        "Must be called only with a bound APPROVED DecisionResult (proposal_id + decision_id). "
        "Writes to the work queue table via WMS integration."
    ),
)
