# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
EquipmentProvider — vendor-neutral connector boundary.

This Protocol is the extension point for all equipment backends:

    MAIWEquipmentAdapter   — wraps existing EquipmentAssetTools
    (future) SAPAdapter    — wraps SAP PM REST API
    MockEquipmentProvider  — in-memory, for tests

The MCP server depends only on this Protocol.  It never knows which
backend is active.

Execution methods (write capabilities)
---------------------------------------
The provider exposes execution methods — not proposal methods.  Proposals are
built locally in the agent/skill layer (no MCP round-trip required).  Only
EquipmentActionExecutor (after DecisionEngine APPROVED) calls these methods.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from maiw_mcp.contracts.equipment import (
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


@runtime_checkable
class EquipmentProvider(Protocol):
    """
    Vendor-neutral equipment data source and write boundary.

    Any object implementing these methods can be registered as the
    backend for the MAIW Equipment MCP Server.
    """

    async def get_equipment_status(
        self, request: EquipmentStatusRequest
    ) -> EquipmentStatusResult:
        """
        Return current status of one or more equipment assets.

        Raises
        ------
        maiw_mcp.errors.BackendUnavailable
            Backend unreachable or no assets match the filters.
        """
        ...

    async def get_equipment_telemetry(
        self, request: EquipmentTelemetryRequest
    ) -> EquipmentTelemetryResult:
        """
        Return telemetry data for an asset.

        Raises
        ------
        maiw_mcp.errors.BackendUnavailable
            Asset not found or backend unreachable.
        """
        ...

    async def execute_equipment_assignment(
        self, request: EquipmentExecuteAssignRequest
    ) -> EquipmentExecuteAssignResult:
        """
        Execute an approved equipment assignment write.

        Only called after DecisionEngine returns APPROVED.

        Raises
        ------
        maiw_mcp.errors.BackendUnavailable
            Backend write failed.
        """
        ...

    async def execute_equipment_release(
        self, request: EquipmentExecuteReleaseRequest
    ) -> EquipmentExecuteReleaseResult:
        """
        Execute an approved equipment release write.

        Only called after DecisionEngine returns APPROVED.

        Raises
        ------
        maiw_mcp.errors.BackendUnavailable
            Backend write failed.
        """
        ...

    async def execute_schedule_maintenance(
        self, request: EquipmentExecuteMaintenanceRequest
    ) -> EquipmentExecuteMaintenanceResult:
        """
        Execute an approved maintenance schedule write.

        Only called after DecisionEngine returns APPROVED.

        Raises
        ------
        maiw_mcp.errors.BackendUnavailable
            Backend write failed.
        """
        ...


class MockEquipmentProvider:
    """
    Simple in-memory provider for development and testing.

    Pre-load assets with ``add_asset()``.  Missing assets return synthetic
    data.  Execution methods return mock success results without hitting any DB.
    """

    def __init__(self) -> None:
        self._assets: dict[str, EquipmentAssetInfo] = {}
        self._telemetry: dict[str, list[TelemetryPoint]] = {}

    def add_asset(self, asset: EquipmentAssetInfo) -> None:
        self._assets[asset.asset_id] = asset

    def add_telemetry(self, asset_id: str, points: list[TelemetryPoint]) -> None:
        self._telemetry.setdefault(asset_id, []).extend(points)

    async def get_equipment_status(
        self, request: EquipmentStatusRequest
    ) -> EquipmentStatusResult:
        assets = list(self._assets.values())

        if request.asset_id:
            assets = [a for a in assets if a.asset_id == request.asset_id]
        if request.equipment_type:
            assets = [a for a in assets if a.equipment_type == request.equipment_type]
        if request.zone:
            assets = [a for a in assets if a.zone == request.zone]
        if request.status_filter:
            assets = [a for a in assets if a.status == request.status_filter]

        if not assets and request.asset_id:
            # Synthetic fallback for an unknown single asset
            assets = [
                EquipmentAssetInfo(
                    asset_id=request.asset_id,
                    equipment_type="unknown",
                    model="mock-model",
                    zone="MOCK",
                    status="available",
                )
            ]

        summary: dict[str, dict[str, int]] = {}
        for a in assets:
            summary.setdefault(a.equipment_type, {})
            summary[a.equipment_type][a.status] = (
                summary[a.equipment_type].get(a.status, 0) + 1
            )

        return EquipmentStatusResult(
            equipment=assets,
            summary=summary,
            total_count=len(assets),
            source="mock",
        )

    async def get_equipment_telemetry(
        self, request: EquipmentTelemetryRequest
    ) -> EquipmentTelemetryResult:
        points = self._telemetry.get(request.asset_id, [])

        if request.metric:
            points = [p for p in points if p.metric == request.metric]

        metrics: dict[str, str] = {}
        for p in points:
            metrics[p.metric] = p.unit
        available = [AvailableMetric(metric=m, unit=u) for m, u in metrics.items()]

        return EquipmentTelemetryResult(
            asset_id=request.asset_id,
            telemetry_data=points,
            available_metrics=available,
            hours_back=request.hours_back,
            data_points=len(points),
            source="mock",
        )

    async def execute_equipment_assignment(
        self, request: EquipmentExecuteAssignRequest
    ) -> EquipmentExecuteAssignResult:
        return EquipmentExecuteAssignResult(
            assignment_id=1,
            success=True,
            proposal_id=request.proposal_id,
            decision_id=request.decision_id,
            source="mock",
            message=f"Assigned {request.asset_id} to {request.assignee}",
        )

    async def execute_equipment_release(
        self, request: EquipmentExecuteReleaseRequest
    ) -> EquipmentExecuteReleaseResult:
        return EquipmentExecuteReleaseResult(
            success=True,
            proposal_id=request.proposal_id,
            decision_id=request.decision_id,
            source="mock",
            message=f"Released {request.asset_id}",
        )

    async def execute_schedule_maintenance(
        self, request: EquipmentExecuteMaintenanceRequest
    ) -> EquipmentExecuteMaintenanceResult:
        return EquipmentExecuteMaintenanceResult(
            maintenance_id=1,
            success=True,
            proposal_id=request.proposal_id,
            decision_id=request.decision_id,
            source="mock",
            message=f"Scheduled {request.maintenance_type} for {request.asset_id}",
        )

    async def propose_equipment_assignment(
        self, request: EquipmentAssignmentRequest
    ) -> EquipmentAssignmentResult:
        from maiw_mcp.contracts.actions import ActionProposal
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
        return EquipmentAssignmentResult(proposal=proposal, source="mock")
