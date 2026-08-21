# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIWWaveAdapter — wraps WMSIntegrationService and OperationsActionTools wave methods.

Architecture note
-----------------
Delegates entirely to existing backend services. Does not duplicate SQL or
business logic. Tests use MockWaveProvider instead (no WMS/asyncpg needed).
"""

from __future__ import annotations

import logging
from typing import Any

from maiw_mcp.contracts.wave import (
    WaveGetRequest,
    WaveGetResult,
    WaveReprioritizeRequest,
    WaveReprioritizeResult,
    WaveRiskFactor,
    WaveRiskRequest,
    WaveRiskResult,
    WaveTaskInfo,
)

logger = logging.getLogger(__name__)


class MAIWWaveAdapter:
    """Wraps WMSIntegrationService for the WaveProvider Protocol."""

    def __init__(self, wms_service: Any | None = None) -> None:
        self._wms = wms_service

    async def _get_wms(self) -> Any:
        if self._wms is None:
            from src.api.services.wms.integration_service import get_wms_service
            self._wms = await get_wms_service()
        return self._wms

    async def get_wave(self, request: WaveGetRequest) -> WaveGetResult:
        wms = await self._get_wms()
        raw_tasks = await wms.get_tasks(
            status=request.status_filter,
            task_type=request.task_type,
        )
        tasks = [
            WaveTaskInfo(
                task_id=str(t.get("id") or t.get("task_id", "")),
                task_type=t.get("task_type", "PICK"),
                zone=t.get("location") or t.get("zone") or request.zone,
                status=t.get("status", "pending"),
                assigned_to=str(t.get("assigned_to") or ""),
                priority=t.get("priority", "medium"),
                deadline=t.get("due_date") or t.get("deadline"),
            )
            for t in (raw_tasks or [])
        ]
        if request.zone:
            tasks = [t for t in tasks if t.zone == request.zone]

        zones_active = list({t.zone for t in tasks if t.zone})
        summary: dict[str, int] = {}
        for t in tasks:
            summary[t.status] = summary.get(t.status, 0) + 1

        return WaveGetResult(
            tasks=tasks,
            total_tasks=len(tasks),
            zones_active=zones_active,
            summary=summary,
            wave_id=request.wave_id,
            source="maiw-wms",
        )

    async def get_wave_risk(self, request: WaveRiskRequest) -> WaveRiskResult:
        wave_result = await self.get_wave(
            WaveGetRequest(
                warehouse_id=request.warehouse_id,
                wave_id=request.wave_id,
                zone=request.zone,
            )
        )
        tasks = wave_result.tasks
        at_risk = [t for t in tasks if t.status == "pending" and not t.assigned_to]
        has_deadline = any(t.deadline for t in at_risk)

        risk_factors: list[WaveRiskFactor] = []
        if at_risk:
            risk_factors.append(WaveRiskFactor(
                factor="unassigned_pending_tasks",
                severity="high" if len(at_risk) > 2 else "medium",
                detail=f"{len(at_risk)} pending task(s) without worker assignment",
            ))
        if has_deadline:
            risk_factors.append(WaveRiskFactor(
                factor="deadline_approaching",
                severity="high",
                detail="Tasks with carrier cutoff deadline are unassigned",
            ))

        otif = len(at_risk) > 0
        if not otif:
            lvl = "none"
        elif has_deadline:
            lvl = "high"
        elif len(at_risk) > 2:
            lvl = "medium"
        else:
            lvl = "low"

        rec = ""
        if otif:
            rec = f"Reprioritize and allocate additional workers to {len(at_risk)} at-risk task(s)."

        return WaveRiskResult(
            otif_at_risk=otif,
            risk_level=lvl,
            at_risk_task_count=len(at_risk),
            total_task_count=len(tasks),
            risk_factors=risk_factors,
            recommendation=rec,
            wave_id=request.wave_id,
            source="maiw-wms",
        )

    async def execute_wave_reprioritize(
        self, request: WaveReprioritizeRequest
    ) -> WaveReprioritizeResult:
        wms = await self._get_wms()
        wave_result = await self.get_wave(
            WaveGetRequest(
                warehouse_id=request.warehouse_id,
                wave_id=request.wave_id,
                zone=request.zone,
            )
        )
        updated = 0
        for task in wave_result.tasks:
            try:
                await wms.update_task_status(task.task_id, status=task.status)
                updated += 1
            except Exception as exc:
                logger.warning("Failed to update task %s: %s", task.task_id, exc)

        return WaveReprioritizeResult(
            success=True,
            tasks_updated=updated,
            wave_id=request.wave_id,
            new_priority=request.new_priority,
            proposal_id=request.proposal_id,
            decision_id=request.decision_id,
            source="maiw-wms",
            message=f"Reprioritized {updated} task(s) to '{request.new_priority}'",
        )
