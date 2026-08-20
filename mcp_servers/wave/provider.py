# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
WaveProvider — vendor-neutral wave/pick data source and write boundary.

The Protocol is the extension point for all wave backends:
    MAIWWaveAdapter       — wraps WMSIntegrationService + OperationsActionTools
    MockWaveProvider      — in-memory, for tests

Only WaveActionExecutor (after DecisionEngine APPROVED) calls execute_wave_reprioritize().
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from maiw_mcp.contracts.wave import (
    WaveGetRequest,
    WaveGetResult,
    WaveReprioritizeRequest,
    WaveReprioritizeResult,
    WaveRiskRequest,
    WaveRiskResult,
    WaveRiskFactor,
    WaveTaskInfo,
)


@runtime_checkable
class WaveProvider(Protocol):
    """Vendor-neutral wave data source and write boundary."""

    async def get_wave(self, request: WaveGetRequest) -> WaveGetResult: ...

    async def get_wave_risk(self, request: WaveRiskRequest) -> WaveRiskResult: ...

    async def execute_wave_reprioritize(
        self, request: WaveReprioritizeRequest
    ) -> WaveReprioritizeResult: ...


class MockWaveProvider:
    """In-memory wave provider for tests and development."""

    def __init__(self) -> None:
        self._tasks: list[WaveTaskInfo] = [
            WaveTaskInfo(
                task_id="task-001", task_type="PICK", zone="A1",
                status="in_progress", assigned_to="w-001", priority="high",
            ),
            WaveTaskInfo(
                task_id="task-002", task_type="PICK", zone="A1",
                status="pending", assigned_to=None, priority="medium",
                deadline="2026-08-20T14:00:00Z",
            ),
            WaveTaskInfo(
                task_id="task-003", task_type="PACK", zone="B2",
                status="pending", assigned_to=None, priority="medium",
            ),
            WaveTaskInfo(
                task_id="task-004", task_type="SHIP", zone="C3",
                status="pending", assigned_to=None, priority="low",
            ),
        ]

    async def get_wave(self, request: WaveGetRequest) -> WaveGetResult:
        tasks = self._tasks
        if request.zone:
            tasks = [t for t in tasks if t.zone == request.zone]
        if request.status_filter:
            tasks = [t for t in tasks if t.status == request.status_filter]
        if request.task_type:
            tasks = [t for t in tasks if t.task_type == request.task_type]

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
            source="mock",
        )

    async def get_wave_risk(self, request: WaveRiskRequest) -> WaveRiskResult:
        tasks = self._tasks
        if request.zone:
            tasks = [t for t in tasks if t.zone == request.zone]

        at_risk = [t for t in tasks if t.status == "pending" and t.assigned_to is None]
        has_deadline_risk = any(t.deadline is not None for t in at_risk)

        risk_factors = []
        if at_risk:
            risk_factors.append(WaveRiskFactor(
                factor="unassigned_pending_tasks",
                severity="high" if len(at_risk) > 2 else "medium",
                detail=f"{len(at_risk)} pending task(s) have no assigned worker",
            ))
        if has_deadline_risk:
            risk_factors.append(WaveRiskFactor(
                factor="deadline_approaching",
                severity="high",
                detail="One or more tasks have a carrier cutoff deadline",
            ))

        otif_at_risk = len(at_risk) > 0
        if not otif_at_risk:
            risk_level = "none"
        elif len(at_risk) <= 1 and not has_deadline_risk:
            risk_level = "low"
        elif has_deadline_risk:
            risk_level = "high"
        else:
            risk_level = "medium"

        recommendation = ""
        if otif_at_risk:
            recommendation = (
                f"Reprioritize wave to 'high' and allocate {len(at_risk)} "
                "additional worker(s) to reduce OTIF risk."
            )

        return WaveRiskResult(
            otif_at_risk=otif_at_risk,
            risk_level=risk_level,
            at_risk_task_count=len(at_risk),
            total_task_count=len(tasks),
            risk_factors=risk_factors,
            recommendation=recommendation,
            wave_id=request.wave_id,
            source="mock",
        )

    async def execute_wave_reprioritize(
        self, request: WaveReprioritizeRequest
    ) -> WaveReprioritizeResult:
        tasks = self._tasks
        if request.zone:
            tasks = [t for t in tasks if t.zone == request.zone]
        for t in tasks:
            t.priority = request.new_priority
        return WaveReprioritizeResult(
            success=True,
            tasks_updated=len(tasks),
            wave_id=request.wave_id,
            new_priority=request.new_priority,
            proposal_id=request.proposal_id,
            decision_id=request.decision_id,
            source="mock",
            message=f"Reprioritized {len(tasks)} task(s) to '{request.new_priority}'",
        )
