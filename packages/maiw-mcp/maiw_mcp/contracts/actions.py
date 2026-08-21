# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
ActionProposal — typed abstraction for warehouse write operations.

Design intent
-------------
Write capabilities (assign equipment, schedule maintenance, release equipment)
do NOT execute immediately.  Instead, they return an ``ActionProposal`` that
describes the intended mutation.  A future DecisionEngine will inspect the
proposal, validate authorisation, apply business rules, and either execute or
reject it.

This establishes the architectural seam:

    Agent
      ↓ (calls write skill)
    MCP write tool  →  ActionProposal
      ↓
    [future DecisionEngine: validate → execute or reject]
      ↓
    Backend mutation

Today, callers receive the ActionProposal and may choose to execute it
directly for development purposes.  In production, proposals should be
forwarded to the DecisionEngine.

Out of scope for Phase 3
------------------------
- Full DecisionEngine implementation
- Proposal persistence / approval workflow UI
- Rollback mechanisms
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Risk classification for warehouse write operations."""

    READ_ONLY = "read_only"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionProposal(BaseModel):
    """
    A proposed warehouse write operation awaiting authorisation.

    Fields
    ------
    proposal_id:
        UUID assigned at proposal creation.  Stable across retries if the
        caller supplies the same ``idempotency_key``.
    action:
        Stable semantic name of the write capability in
        ``warehouse.<domain>.<verb>`` format.
    parameters:
        Raw parameters for the action — same dict that would be passed to
        the backend if approved.
    domain:
        Warehouse domain: ``equipment``, ``inventory``, ``labor``, …
    risk_level:
        Declared risk of the operation (set by the capability author).
    reason:
        Why the action is being proposed — populated by the requesting agent.
    requested_by:
        Identity of the agent or system requesting the action.
    idempotency_key:
        Caller-supplied key.  If provided, re-submitting the same key should
        not double-execute.
    requires_approval:
        Whether this proposal must be reviewed by a human or DecisionEngine
        before execution.  ``True`` for MEDIUM risk and above.
    trace_id:
        Correlation ID from the calling agent span.
    proposed_at:
        UTC timestamp when the proposal was created.
    """

    proposal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    action: str = Field(..., description="Capability name, e.g. 'warehouse.equipment.assign'")
    parameters: dict[str, Any] = Field(default_factory=dict)
    domain: str = Field(..., description="Warehouse domain, e.g. 'equipment'")
    risk_level: RiskLevel = Field(RiskLevel.MEDIUM)
    reason: str = Field(default="", description="Why the agent is requesting this action")
    requested_by: str = Field(default="unknown", description="Agent or system name")
    idempotency_key: str | None = Field(default=None)
    requires_approval: bool = Field(
        default=True,
        description="True when risk_level >= MEDIUM — human or DecisionEngine must approve",
    )
    trace_id: str | None = Field(default=None)
    proposed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @classmethod
    def for_equipment_assign(
        cls,
        *,
        asset_id: str,
        assignee: str,
        assignment_type: str,
        task_id: str | None,
        duration_hours: int | None,
        notes: str | None,
        reason: str,
        requested_by: str,
        warehouse_id: str = "default",
        trace_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> ActionProposal:
        return cls(
            action="warehouse.equipment.assign",
            parameters={
                "asset_id": asset_id,
                "assignee": assignee,
                "assignment_type": assignment_type,
                "task_id": task_id,
                "duration_hours": duration_hours,
                "notes": notes,
                "warehouse_id": warehouse_id,
            },
            domain="equipment",
            risk_level=RiskLevel.MEDIUM,
            reason=reason,
            requested_by=requested_by,
            requires_approval=True,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )

    @classmethod
    def for_equipment_release(
        cls,
        *,
        asset_id: str,
        released_by: str,
        notes: str | None = None,
        reason: str = "",
        requested_by: str = "operations-agent",
        warehouse_id: str = "default",
        trace_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> ActionProposal:
        return cls(
            action="warehouse.equipment.release",
            parameters={
                "asset_id": asset_id,
                "released_by": released_by,
                "notes": notes,
                "warehouse_id": warehouse_id,
            },
            domain="equipment",
            risk_level=RiskLevel.LOW,
            reason=reason or f"Release {asset_id} from assignment",
            requested_by=requested_by,
            requires_approval=False,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )

    @classmethod
    def for_schedule_maintenance(
        cls,
        *,
        asset_id: str,
        maintenance_type: str,
        description: str,
        scheduled_by: str,
        scheduled_for: str,
        estimated_duration_minutes: int = 60,
        priority: str = "medium",
        reason: str = "",
        requested_by: str = "operations-agent",
        warehouse_id: str = "default",
        trace_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> ActionProposal:
        return cls(
            action="warehouse.equipment.schedule_maintenance",
            parameters={
                "asset_id": asset_id,
                "maintenance_type": maintenance_type,
                "description": description,
                "scheduled_by": scheduled_by,
                "scheduled_for": scheduled_for,
                "estimated_duration_minutes": estimated_duration_minutes,
                "priority": priority,
                "warehouse_id": warehouse_id,
            },
            domain="equipment",
            risk_level=RiskLevel.MEDIUM,
            reason=reason or f"Schedule {maintenance_type} maintenance for {asset_id}",
            requested_by=requested_by,
            requires_approval=True,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )

    @classmethod
    def for_labor_allocate(
        cls,
        *,
        task_id: str,
        task_type: str,
        worker_ids: list[str],
        zone: str | None = None,
        priority: str = "medium",
        notes: str | None = None,
        reason: str = "",
        requested_by: str = "operations-agent",
        warehouse_id: str = "default",
        trace_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> ActionProposal:
        """Propose assigning workers to a labor task. MEDIUM risk — requires approval."""
        return cls(
            action="warehouse.labor.allocate",
            parameters={
                "task_id": task_id,
                "task_type": task_type,
                "worker_ids": worker_ids,
                "zone": zone,
                "priority": priority,
                "notes": notes,
                "warehouse_id": warehouse_id,
            },
            domain="labor",
            risk_level=RiskLevel.MEDIUM,
            reason=reason or f"Allocate {len(worker_ids)} worker(s) to task {task_id}",
            requested_by=requested_by,
            requires_approval=True,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )

    @classmethod
    def for_wave_reprioritize(
        cls,
        *,
        wave_id: str | None = None,
        zone: str | None = None,
        new_priority: str,
        reason: str = "",
        requested_by: str = "operations-agent",
        warehouse_id: str = "default",
        trace_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> ActionProposal:
        """Propose reprioritizing a wave or zone's tasks. MEDIUM risk — requires approval."""
        scope = wave_id or zone or "all"
        return cls(
            action="warehouse.wave.reprioritize",
            parameters={
                "wave_id": wave_id,
                "zone": zone,
                "new_priority": new_priority,
                "warehouse_id": warehouse_id,
            },
            domain="wave",
            risk_level=RiskLevel.MEDIUM,
            reason=reason or f"Reprioritize wave {scope} to {new_priority}",
            requested_by=requested_by,
            requires_approval=True,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )
