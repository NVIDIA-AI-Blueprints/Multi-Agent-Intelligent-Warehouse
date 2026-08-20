# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW Backend Adapter — wraps the existing EquipmentAssetTools.

This is the connector between the vendor-neutral equipment MCP server and the
MAIW PostgreSQL equipment backend.  It reuses the existing business logic
entirely; no new equipment implementation is introduced.

Runtime path (read)
-------------------
    MCP tool (warehouse.equipment.get_status)
        ↓
    MAIWEquipmentAdapter.get_equipment_status()
        ↓
    EquipmentAssetTools.get_equipment_status()  ← existing MAIW code, unchanged
        ↓
    SQLRetriever.fetch_all() → PostgreSQL equipment_assets table

Runtime path (write — execution, only after APPROVED)
-------------------
    EquipmentActionExecutor (after DecisionEngine APPROVED)
        ↓
    ExecuteEquipmentAssignmentSkill / ExecuteEquipmentReleaseSkill / ExecuteEquipmentMaintenanceSkill
        ↓
    MCP tool (warehouse.equipment.assign / release / schedule_maintenance)
        ↓
    MAIWEquipmentAdapter.execute_equipment_assignment() / execute_equipment_release() / execute_schedule_maintenance()
        ↓
    EquipmentAssetTools.assign_equipment() / release_equipment() / schedule_maintenance()

Proposal path (local, no MCP call)
-------------------
    Agent layer (state_aware_ops.py / EquipmentAssignmentSkill)
        ↓
    ActionProposal.for_equipment_assign() / for_equipment_release() / for_schedule_maintenance()
        (built entirely in-process — never calls MCP)

Note: propose_equipment_assignment() is kept for backward compatibility with
contract tests that validate the adapter's asset-existence check before proposal.
"""

from __future__ import annotations

import logging
from datetime import datetime

from maiw_mcp.contracts.equipment import (
    ActionProposal,
    AvailableMetric,
    EquipmentAssetInfo,
    EquipmentAssignmentRequest,
    EquipmentAssignmentResult,
    EquipmentExecuteAssignRequest,
    EquipmentExecuteAssignResult,
    EquipmentExecuteMaintenanceRequest,
    EquipmentExecuteMaintenanceResult,
    EquipmentExecuteReleaseRequest,
    EquipmentExecuteReleaseResult,
    EquipmentStatusRequest,
    EquipmentStatusResult,
    EquipmentTelemetryRequest,
    EquipmentTelemetryResult,
    TelemetryPoint,
)
from maiw_mcp.errors import BackendUnavailable

logger = logging.getLogger(__name__)


class MAIWEquipmentAdapter:
    """
    Adapts existing ``EquipmentAssetTools`` to the ``EquipmentProvider`` Protocol.

    Parameters
    ----------
    tools:
        An initialised ``EquipmentAssetTools`` instance.
    """

    def __init__(self, tools: object) -> None:
        self._tools = tools

    async def get_equipment_status(
        self, request: EquipmentStatusRequest
    ) -> EquipmentStatusResult:
        try:
            raw = await self._tools.get_equipment_status(
                asset_id=request.asset_id,
                equipment_type=request.equipment_type,
                zone=request.zone,
                status=request.status_filter,
            )
        except Exception as exc:
            logger.error("MAIWEquipmentAdapter: get_equipment_status failed: %s", exc)
            raise BackendUnavailable(f"Equipment backend error: {exc}") from exc

        if "error" in raw:
            raise BackendUnavailable(raw["error"])

        assets = [
            EquipmentAssetInfo(
                asset_id=row["asset_id"],
                equipment_type=row["type"],
                model=row["model"],
                zone=row["zone"],
                status=row["status"],
                owner_user=row.get("owner_user"),
                next_pm_due=_parse_dt(row.get("next_pm_due")),
                last_maintenance=_parse_dt(row.get("last_maintenance")),
                metadata=row.get("metadata") or {},
            )
            for row in raw.get("equipment", [])
        ]

        return EquipmentStatusResult(
            equipment=assets,
            summary=raw.get("summary", {}),
            total_count=raw.get("total_count", len(assets)),
            source="maiw-backend",
        )

    async def get_equipment_telemetry(
        self, request: EquipmentTelemetryRequest
    ) -> EquipmentTelemetryResult:
        try:
            raw = await self._tools.get_equipment_telemetry(
                asset_id=request.asset_id,
                metric=request.metric,
                hours_back=request.hours_back,
            )
        except Exception as exc:
            logger.error(
                "MAIWEquipmentAdapter: get_equipment_telemetry failed for %s: %s",
                request.asset_id,
                exc,
            )
            raise BackendUnavailable(
                f"Equipment telemetry backend error for {request.asset_id!r}: {exc}"
            ) from exc

        if "error" in raw:
            raise BackendUnavailable(raw["error"])

        points = [
            TelemetryPoint(
                timestamp=_parse_dt(p["timestamp"]) or datetime.utcnow(),
                metric=p["metric"],
                value=float(p["value"]),
                unit=p.get("unit", "unknown"),
                quality_score=float(p.get("quality_score", 1.0)),
            )
            for p in raw.get("telemetry_data", [])
        ]

        available = [
            AvailableMetric(
                metric=m["metric"],
                unit=m.get("unit", "unknown"),
            )
            for m in raw.get("available_metrics", [])
        ]

        return EquipmentTelemetryResult(
            asset_id=request.asset_id,
            telemetry_data=points,
            available_metrics=available,
            hours_back=request.hours_back,
            data_points=len(points),
            source="maiw-backend",
        )

    async def propose_equipment_assignment(
        self, request: EquipmentAssignmentRequest
    ) -> EquipmentAssignmentResult:
        # Validate that the asset exists before building the proposal.
        # We call get_equipment_status with the specific asset_id only.
        try:
            raw = await self._tools.get_equipment_status(
                asset_id=request.asset_id,
                equipment_type=None,
                zone=None,
                status=None,
            )
        except Exception as exc:
            raise BackendUnavailable(
                f"Cannot validate asset {request.asset_id!r}: {exc}"
            ) from exc

        if not raw.get("equipment"):
            raise BackendUnavailable(
                f"Equipment asset {request.asset_id!r} not found"
            )

        proposal = ActionProposal.for_equipment_assign(
            asset_id=request.asset_id,
            assignee=request.assignee,
            assignment_type=request.assignment_type,
            task_id=request.task_id,
            duration_hours=request.duration_hours,
            notes=request.notes,
            reason=request.reason,
            requested_by=request.requested_by,
        )

        logger.info(
            "MAIWEquipmentAdapter: ActionProposal created for asset=%s assignee=%s proposal_id=%s",
            request.asset_id,
            request.assignee,
            proposal.proposal_id,
        )

        return EquipmentAssignmentResult(proposal=proposal, source="maiw-backend")

    async def execute_equipment_assignment(
        self, request: EquipmentExecuteAssignRequest
    ) -> EquipmentExecuteAssignResult:
        try:
            result = await self._tools.assign_equipment(
                asset_id=request.asset_id,
                assignee=request.assignee,
                assignment_type=request.assignment_type,
                task_id=request.task_id,
                duration_hours=int(request.duration_hours) if request.duration_hours else None,
                notes=request.notes,
            )
        except Exception as exc:
            raise BackendUnavailable(
                f"Assignment execution failed for {request.asset_id!r}: {exc}"
            ) from exc

        if not result.get("success"):
            raise BackendUnavailable(result.get("error", "Assignment failed"))

        logger.info(
            "MAIWEquipmentAdapter: assignment executed asset=%s assignee=%s assignment_id=%s proposal_id=%s",
            request.asset_id, request.assignee, result.get("assignment_id"), request.proposal_id,
        )
        return EquipmentExecuteAssignResult(
            assignment_id=result.get("assignment_id"),
            success=True,
            proposal_id=request.proposal_id,
            decision_id=request.decision_id,
            source="maiw-backend",
            message=result.get("message"),
        )

    async def execute_equipment_release(
        self, request: EquipmentExecuteReleaseRequest
    ) -> EquipmentExecuteReleaseResult:
        try:
            result = await self._tools.release_equipment(
                asset_id=request.asset_id,
                released_by=request.released_by,
                notes=request.notes,
            )
        except Exception as exc:
            raise BackendUnavailable(
                f"Release execution failed for {request.asset_id!r}: {exc}"
            ) from exc

        if not result.get("success"):
            raise BackendUnavailable(result.get("error", "Release failed"))

        logger.info(
            "MAIWEquipmentAdapter: release executed asset=%s proposal_id=%s",
            request.asset_id, request.proposal_id,
        )
        return EquipmentExecuteReleaseResult(
            success=True,
            proposal_id=request.proposal_id,
            decision_id=request.decision_id,
            source="maiw-backend",
            message=result.get("message"),
        )

    async def execute_schedule_maintenance(
        self, request: EquipmentExecuteMaintenanceRequest
    ) -> EquipmentExecuteMaintenanceResult:
        from datetime import datetime as _dt
        try:
            scheduled_for_dt = _dt.fromisoformat(request.scheduled_for.replace("Z", "+00:00"))
            result = await self._tools.schedule_maintenance(
                asset_id=request.asset_id,
                maintenance_type=request.maintenance_type,
                description=request.description,
                scheduled_by=request.scheduled_by,
                scheduled_for=scheduled_for_dt,
                estimated_duration_minutes=request.estimated_duration_minutes,
                priority=request.priority,
            )
        except Exception as exc:
            raise BackendUnavailable(
                f"Maintenance scheduling failed for {request.asset_id!r}: {exc}"
            ) from exc

        if not result.get("success"):
            raise BackendUnavailable(result.get("error", "Maintenance scheduling failed"))

        logger.info(
            "MAIWEquipmentAdapter: maintenance scheduled asset=%s proposal_id=%s",
            request.asset_id, request.proposal_id,
        )
        return EquipmentExecuteMaintenanceResult(
            maintenance_id=result.get("maintenance_id"),
            success=True,
            proposal_id=request.proposal_id,
            decision_id=request.decision_id,
            source="maiw-backend",
            message=result.get("message"),
        )


def _parse_dt(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None
