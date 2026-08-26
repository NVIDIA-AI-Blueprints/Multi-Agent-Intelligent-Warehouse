# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Vendor-neutral equipment capability contracts.

These types are independent of:
  - Any specific WMS vendor (Manhattan Associates, SAP EWM, Blue Yonder)
  - The MAIW database schema (equipment_assets, equipment_telemetry tables)
  - Any IoT platform or telematics vendor

Agents and skills depend only on these types.

Read capabilities
-----------------
    warehouse.equipment.get_status        — current status/availability of equipment
    warehouse.equipment.get_telemetry     — sensor/telemetry data for an asset

Execution capabilities (called only after DecisionEngine APPROVED)
-----------------
    warehouse.equipment.assign              — execute approved assignment write
    warehouse.equipment.release             — execute approved release write
    warehouse.equipment.schedule_maintenance — execute approved maintenance write
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .actions import ActionProposal
from .common import CapabilityMetadata


# ── Read requests ─────────────────────────────────────────────────────────────


class EquipmentStatusRequest(BaseModel):
    """
    Request for current status/availability of warehouse equipment.

    All filters are optional — omitting them returns the full fleet.
    """

    asset_id: str | None = Field(
        default=None, description="Filter to a single asset by ID"
    )
    equipment_type: str | None = Field(
        default=None,
        description="Filter by equipment type: forklift, amr, agv, scanner, …",
    )
    zone: str | None = Field(
        default=None, description="Filter by warehouse zone"
    )
    status_filter: str | None = Field(
        default=None,
        description="Filter by status: available, assigned, charging, maintenance, …",
    )


class EquipmentTelemetryRequest(BaseModel):
    """Request for equipment sensor / telemetry data."""

    asset_id: str = Field(..., min_length=1, description="Equipment asset ID")
    metric: str | None = Field(
        default=None,
        description="Specific metric name; None returns all available metrics",
    )
    hours_back: int = Field(
        default=24, ge=1, le=720, description="Hours of history to return (max 30 days)"
    )


# ── Write requests ─────────────────────────────────────────────────────────────


class EquipmentAssignmentRequest(BaseModel):
    """
    Request to assign equipment to a task or user.

    The proposal is built locally in the agent layer and forwarded to the
    DecisionEngine.  Only after APPROVED does an execution skill call
    warehouse.equipment.assign via MCP.
    """

    asset_id: str = Field(..., min_length=1, description="Equipment asset ID to assign")
    assignee: str = Field(..., min_length=1, description="User or system to assign to")
    assignment_type: str = Field(
        default="task",
        description="Assignment type: task, user, zone, maintenance",
    )
    task_id: str | None = Field(
        default=None, description="Task ID if assignment is task-related"
    )
    duration_hours: int | None = Field(
        default=None, ge=1, description="Estimated assignment duration in hours"
    )
    notes: str | None = Field(default=None)
    reason: str = Field(
        default="", description="Why the agent is requesting this assignment"
    )
    requested_by: str = Field(
        default="operations-agent", description="Agent or system making the request"
    )


class EquipmentExecuteAssignRequest(BaseModel):
    """Execution request — only valid after DecisionEngine returns APPROVED."""

    asset_id: str = Field(..., min_length=1)
    assignee: str = Field(..., min_length=1)
    assignment_type: str = Field(default="task")
    task_id: str | None = Field(default=None)
    duration_hours: float | None = Field(default=None)
    notes: str | None = Field(default=None)
    proposal_id: str = Field(..., description="Bound proposal identifier for audit")
    decision_id: str = Field(..., description="Bound decision identifier for audit")
    execution_id: str | None = Field(default=None, description="MAIW execution identity, propagated from BaseActionExecutor")


class EquipmentExecuteReleaseRequest(BaseModel):
    """Execution request — only valid after DecisionEngine returns APPROVED."""

    asset_id: str = Field(..., min_length=1)
    released_by: str = Field(..., min_length=1)
    notes: str | None = Field(default=None)
    proposal_id: str = Field(...)
    decision_id: str = Field(...)
    execution_id: str | None = Field(default=None, description="MAIW execution identity")


class EquipmentExecuteMaintenanceRequest(BaseModel):
    """Execution request — only valid after DecisionEngine returns APPROVED."""

    asset_id: str = Field(..., min_length=1)
    maintenance_type: str = Field(...)
    description: str = Field(...)
    scheduled_by: str = Field(...)
    scheduled_for: str = Field(..., description="ISO-8601 datetime string")
    estimated_duration_minutes: int = Field(default=60, ge=1)
    priority: str = Field(default="medium")
    proposal_id: str = Field(...)
    decision_id: str = Field(...)
    execution_id: str | None = Field(default=None, description="MAIW execution identity")


# ── Result fragments ───────────────────────────────────────────────────────────


class EquipmentAssetInfo(BaseModel):
    """Status snapshot of a single equipment asset."""

    asset_id: str
    equipment_type: str = Field(description="Asset type: forklift, amr, agv, scanner, …")
    model: str
    zone: str
    status: str = Field(description="available | assigned | charging | maintenance | offline")
    owner_user: str | None = Field(default=None, description="Currently assigned user")
    next_pm_due: datetime | None = Field(
        default=None, description="Next scheduled preventive maintenance"
    )
    last_maintenance: datetime | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TelemetryPoint(BaseModel):
    """A single equipment telemetry reading."""

    timestamp: datetime
    metric: str
    value: float
    unit: str
    quality_score: float = Field(ge=0.0, le=1.0)


class AvailableMetric(BaseModel):
    """A metric available for an equipment asset."""

    metric: str
    unit: str


# ── Results ────────────────────────────────────────────────────────────────────


class EquipmentStatusResult(BaseModel):
    """
    Fleet status snapshot — current state of one or more equipment assets.

    ``source`` identifies the backend so callers can reason about data
    freshness without inspecting internals.
    """

    equipment: list[EquipmentAssetInfo]
    summary: dict[str, dict[str, int]] = Field(
        default_factory=dict,
        description="summary[equipment_type][status] = count",
    )
    total_count: int = Field(ge=0)
    source: str = Field(
        description="Backend identifier: 'maiw-backend', 'mock', …"
    )


class EquipmentTelemetryResult(BaseModel):
    """Telemetry data for a single equipment asset over a time window."""

    asset_id: str
    telemetry_data: list[TelemetryPoint]
    available_metrics: list[AvailableMetric]
    hours_back: int
    data_points: int = Field(ge=0)
    source: str = Field(description="Backend identifier: 'maiw-backend', 'mock', …")


class EquipmentAssignmentResult(BaseModel):
    """
    Result of a warehouse.equipment.assign capability call.

    The assignment is NOT executed — it returns an ActionProposal for the
    DecisionEngine (future) or caller to act on.
    """

    proposal: ActionProposal
    source: str = Field(description="Backend identifier: 'maiw-backend', 'mock', …")


class EquipmentExecuteAssignResult(BaseModel):
    """Result of warehouse.equipment.assign execution — the DB write outcome."""

    assignment_id: int | None = None
    success: bool
    proposal_id: str
    decision_id: str
    execution_id: str | None = None
    outcome: str = "executed"
    source: str
    message: str | None = None


class EquipmentExecuteReleaseResult(BaseModel):
    """Result of warehouse.equipment.release execution — the DB write outcome."""

    success: bool
    proposal_id: str
    decision_id: str
    execution_id: str | None = None
    outcome: str = "executed"
    source: str
    message: str | None = None


class EquipmentExecuteMaintenanceResult(BaseModel):
    """Result of warehouse.equipment.schedule_maintenance execution — the DB write outcome."""

    maintenance_id: int | None = None
    success: bool
    proposal_id: str
    decision_id: str
    execution_id: str | None = None
    outcome: str = "executed"
    source: str
    message: str | None = None


# ── Capability metadata ────────────────────────────────────────────────────────

EQUIPMENT_GET_STATUS_METADATA = CapabilityMetadata(
    name="warehouse.equipment.get_status",
    version=1,
    domain="equipment",
    side_effect="read",
    risk="low",
    idempotent=True,
    timeout_seconds=10,
    required_permission="equipment:read",
    description=(
        "Get current status and availability of warehouse equipment. "
        "Filter by asset_id, equipment_type, zone, or status. "
        "Returns asset details and a fleet-level summary."
    ),
)

EQUIPMENT_GET_TELEMETRY_METADATA = CapabilityMetadata(
    name="warehouse.equipment.get_telemetry",
    version=1,
    domain="equipment",
    side_effect="read",
    risk="low",
    idempotent=True,
    timeout_seconds=15,
    required_permission="equipment:read",
    description=(
        "Get sensor and telemetry data for a specific equipment asset. "
        "Supports filtering by metric name and time window (up to 30 days). "
        "Returns time-series data points and a list of available metrics."
    ),
)

EQUIPMENT_ASSIGN_METADATA = CapabilityMetadata(
    name="warehouse.equipment.assign",
    version=1,
    domain="equipment",
    side_effect="write",
    risk="medium",
    idempotent=False,
    timeout_seconds=15,
    required_permission="equipment:execute",
    description=(
        "Execute an approved equipment assignment write. "
        "Must be called only with a bound APPROVED DecisionResult (proposal_id + decision_id). "
        "Writes to the equipment_assignments table and updates asset status."
    ),
)

EQUIPMENT_RELEASE_METADATA = CapabilityMetadata(
    name="warehouse.equipment.release",
    version=1,
    domain="equipment",
    side_effect="write",
    risk="low",
    idempotent=False,
    timeout_seconds=15,
    required_permission="equipment:execute",
    description=(
        "Execute an approved equipment release write. "
        "Must be called only with a bound APPROVED DecisionResult (proposal_id + decision_id). "
        "Updates the equipment_assignments table and asset status to available."
    ),
)

EQUIPMENT_SCHEDULE_MAINTENANCE_METADATA = CapabilityMetadata(
    name="warehouse.equipment.schedule_maintenance",
    version=1,
    domain="equipment",
    side_effect="write",
    risk="medium",
    idempotent=False,
    timeout_seconds=15,
    required_permission="equipment:execute",
    description=(
        "Execute an approved maintenance schedule write. "
        "Must be called only with a bound APPROVED DecisionResult (proposal_id + decision_id). "
        "Writes to the equipment_maintenance table."
    ),
)
