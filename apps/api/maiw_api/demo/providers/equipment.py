# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
SimulationEquipmentProvider — implements EquipmentProvider against DemoWarehouseWorld.

All five methods (2 reads + 3 writes) are backed by the shared world.
Write methods (assign, release, schedule_maintenance) mutate world state and
publish a ScenarioEvent so the activity feed updates in real time.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from maiw_mcp.contracts.equipment import (
    AvailableMetric,
    EquipmentAssetInfo,
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

if TYPE_CHECKING:
    from maiw_api.demo.events import ScenarioEventBus
    from maiw_api.demo.world import DemoWarehouseWorld


def _asset_to_info(asset: "DemoWarehouseWorld") -> EquipmentAssetInfo:  # type: ignore[name-defined]
    """Translate a world EquipmentAsset into the contract EquipmentAssetInfo."""
    from maiw_api.demo.world import EquipmentAsset
    a: EquipmentAsset = asset  # type: ignore[assignment]
    return EquipmentAssetInfo(
        asset_id=a.asset_id,
        equipment_type=a.equipment_type,
        model=a.model,
        zone=a.zone,
        status=a.status,
        owner_user=a.owner_user,
        next_pm_due=a.next_pm_due,
        last_maintenance=a.last_maintenance,
        metadata={
            "battery_pct": a.battery_pct,
            **({"fault_code": a.fault_code} if a.fault_code else {}),
            **a.metadata,
        },
    )


def _synthetic_telemetry(asset_id: str, hours_back: int) -> list[TelemetryPoint]:
    """Generate plausible telemetry points for a simulation asset."""
    import random
    rng = random.Random(hash(asset_id) & 0xFFFFFFFF)
    now = datetime.now(tz=timezone.utc)
    points: list[TelemetryPoint] = []
    for h in range(min(hours_back, 24), 0, -1):
        ts = now - timedelta(hours=h)
        points.append(TelemetryPoint(
            timestamp=ts,
            metric="battery_pct",
            value=round(rng.uniform(20.0, 100.0), 1),
            unit="%",
            quality_score=0.98,
        ))
        points.append(TelemetryPoint(
            timestamp=ts,
            metric="speed_mps",
            value=round(rng.uniform(0.0, 1.5), 2),
            unit="m/s",
            quality_score=0.97,
        ))
        points.append(TelemetryPoint(
            timestamp=ts,
            metric="load_kg",
            value=round(rng.uniform(0.0, 500.0), 1),
            unit="kg",
            quality_score=0.95,
        ))
    return points


class SimulationEquipmentProvider:
    """Implements EquipmentProvider against the shared DemoWarehouseWorld."""

    def __init__(self, world: "DemoWarehouseWorld", bus: "ScenarioEventBus") -> None:
        self._world = world
        self._bus = bus
        self._assignment_counter = 1000

    async def get_equipment_status(
        self, request: EquipmentStatusRequest
    ) -> EquipmentStatusResult:
        assets = self._world.equipment_list(
            asset_id=request.asset_id,
            equipment_type=request.equipment_type,
            zone=request.zone,
            status_filter=request.status_filter,
        )
        if not assets and request.asset_id:
            raise BackendUnavailable(
                f"Asset '{request.asset_id}' not found in simulation world"
            )
        infos = [_asset_to_info(a) for a in assets]
        summary: dict[str, dict[str, int]] = {}
        for a in assets:
            summary.setdefault(a.equipment_type, {})
            summary[a.equipment_type][a.status] = (
                summary[a.equipment_type].get(a.status, 0) + 1
            )
        return EquipmentStatusResult(
            equipment=infos,
            summary=summary,
            total_count=len(infos),
            source=self._world.SOURCE,
        )

    async def get_equipment_telemetry(
        self, request: EquipmentTelemetryRequest
    ) -> EquipmentTelemetryResult:
        if request.asset_id not in self._world.equipment:
            raise BackendUnavailable(
                f"Asset '{request.asset_id}' not found in simulation world"
            )
        points = _synthetic_telemetry(request.asset_id, request.hours_back)
        if request.metric:
            points = [p for p in points if p.metric == request.metric]
        metrics: dict[str, str] = {p.metric: p.unit for p in points}
        available = [AvailableMetric(metric=m, unit=u) for m, u in metrics.items()]
        return EquipmentTelemetryResult(
            asset_id=request.asset_id,
            telemetry_data=points,
            available_metrics=available,
            hours_back=request.hours_back,
            data_points=len(points),
            source=self._world.SOURCE,
        )

    async def execute_equipment_assignment(
        self, request: EquipmentExecuteAssignRequest
    ) -> EquipmentExecuteAssignResult:
        asset = self._world.equipment.get(request.asset_id)
        if asset is None:
            raise BackendUnavailable(
                f"Asset '{request.asset_id}' not found in simulation world"
            )
        # Mutate world state
        asset.status = "assigned"
        asset.owner_user = request.assignee
        if request.task_id:
            asset.metadata["current_task_id"] = request.task_id

        self._assignment_counter += 1
        assignment_id = self._assignment_counter

        import asyncio
        asyncio.create_task(self._bus.publish_equipment_write(
            action="assign",
            asset_id=request.asset_id,
            detail=f"→ {request.assignee}",
        ))

        return EquipmentExecuteAssignResult(
            assignment_id=assignment_id,
            success=True,
            proposal_id=request.proposal_id,
            decision_id=request.decision_id,
            source=self._world.SOURCE,
            message=f"[SIM] Assigned {request.asset_id} to {request.assignee}",
        )

    async def execute_equipment_release(
        self, request: EquipmentExecuteReleaseRequest
    ) -> EquipmentExecuteReleaseResult:
        asset = self._world.equipment.get(request.asset_id)
        if asset is None:
            raise BackendUnavailable(
                f"Asset '{request.asset_id}' not found in simulation world"
            )
        prev_owner = asset.owner_user
        asset.status = "available"
        asset.owner_user = None
        asset.metadata.pop("current_task_id", None)

        import asyncio
        asyncio.create_task(self._bus.publish_equipment_write(
            action="release",
            asset_id=request.asset_id,
            detail=f"released by {request.released_by} (was: {prev_owner})",
        ))

        return EquipmentExecuteReleaseResult(
            success=True,
            proposal_id=request.proposal_id,
            decision_id=request.decision_id,
            source=self._world.SOURCE,
            message=f"[SIM] Released {request.asset_id}",
        )

    async def execute_schedule_maintenance(
        self, request: EquipmentExecuteMaintenanceRequest
    ) -> EquipmentExecuteMaintenanceResult:
        asset = self._world.equipment.get(request.asset_id)
        if asset is None:
            raise BackendUnavailable(
                f"Asset '{request.asset_id}' not found in simulation world"
            )
        asset.status = "maintenance"
        try:
            asset.next_pm_due = datetime.fromisoformat(request.scheduled_for)
        except ValueError:
            pass

        import asyncio
        asyncio.create_task(self._bus.publish_equipment_write(
            action="maintenance",
            asset_id=request.asset_id,
            detail=f"{request.maintenance_type} scheduled by {request.scheduled_by}",
        ))

        return EquipmentExecuteMaintenanceResult(
            maintenance_id=int(uuid.uuid4().int % 100000),
            success=True,
            proposal_id=request.proposal_id,
            decision_id=request.decision_id,
            source=self._world.SOURCE,
            message=f"[SIM] Scheduled {request.maintenance_type} for {request.asset_id}",
        )
