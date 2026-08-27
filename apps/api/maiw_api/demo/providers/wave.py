# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
SimulationWaveProvider — implements WaveProvider against DemoWarehouseWorld.

Phase 10E Batch 1: canonical outcome semantics, execution_id propagation,
mutation counter, and fault injection support.

Write outcome semantics
-----------------------
reprioritize:
    FAILED   — no tasks found for the requested zone/wave (raises BackendUnavailable)
    NO_OP    — all matching tasks already have the requested priority
    EXECUTED — mutation committed (at least one task priority changed)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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
from maiw_mcp.errors import BackendUnavailable

if TYPE_CHECKING:
    from maiw_api.demo.events import ScenarioEventBus
    from maiw_api.demo.world import DemoWarehouseWorld

_WAVE_TYPES = frozenset({"PICK", "PACK", "SHIP", "RECEIVE", "PUTAWAY", "TRANSFER"})


class SimulationWaveProvider:
    """Implements WaveProvider against the shared DemoWarehouseWorld."""

    def __init__(self, world: "DemoWarehouseWorld", bus: "ScenarioEventBus") -> None:
        self._world = world
        self._bus = bus
        # Reliability testing instrumentation
        self._mutation_count: int = 0
        self._post_mutation_fault: Exception | None = None

    def _wave_tasks(
        self,
        zone: str | None = None,
        status_filter: str | None = None,
        task_type: str | None = None,
    ) -> list:
        tasks = self._world.tasks_list(
            zone=zone,
            status_filter=status_filter,
            task_type=task_type,
        )
        return [t for t in tasks if t.task_type in _WAVE_TYPES]

    async def get_wave(self, request: WaveGetRequest) -> WaveGetResult:
        tasks = self._wave_tasks(
            zone=request.zone,
            status_filter=request.status_filter,
            task_type=request.task_type,
        )
        zones_active = list({t.zone for t in tasks if t.zone})
        summary: dict[str, int] = {}
        for t in tasks:
            summary[t.status] = summary.get(t.status, 0) + 1
        return WaveGetResult(
            tasks=[
                WaveTaskInfo(
                    task_id=t.task_id,
                    task_type=t.task_type,
                    zone=t.zone,
                    status=t.status,
                    assigned_to=t.assigned_to,
                    priority=t.priority,
                    deadline=t.deadline,
                )
                for t in tasks
            ],
            total_tasks=len(tasks),
            zones_active=zones_active,
            summary=summary,
            wave_id=request.wave_id,
            source=self._world.SOURCE,
        )

    async def get_wave_risk(self, request: WaveRiskRequest) -> WaveRiskResult:
        tasks = self._wave_tasks(zone=request.zone)
        at_risk = [t for t in tasks if t.status == "pending" and t.assigned_to is None]
        has_deadline = any(t.deadline is not None for t in at_risk)
        overdue = [t for t in at_risk if t.priority in ("high", "critical")]

        risk_factors: list[WaveRiskFactor] = []
        if at_risk:
            risk_factors.append(
                WaveRiskFactor(
                    factor="unassigned_pending_tasks",
                    severity="high" if len(at_risk) > 2 else "medium",
                    detail=f"{len(at_risk)} pending task(s) have no assigned worker",
                )
            )
        if has_deadline:
            risk_factors.append(
                WaveRiskFactor(
                    factor="deadline_approaching",
                    severity="high",
                    detail=f"Task(s) have carrier cutoff deadline within {request.cutoff_minutes}min",
                )
            )
        if overdue:
            risk_factors.append(
                WaveRiskFactor(
                    factor="high_priority_unassigned",
                    severity="critical",
                    detail=f"{len(overdue)} high/critical priority task(s) unassigned",
                )
            )

        otif_at_risk = len(at_risk) > 0
        if not otif_at_risk:
            risk_level = "none"
        elif len(overdue) > 0 and has_deadline:
            risk_level = "critical"
        elif has_deadline:
            risk_level = "high"
        elif len(at_risk) > 2:
            risk_level = "medium"
        else:
            risk_level = "low"

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
            source=self._world.SOURCE,
        )

    async def execute_wave_reprioritize(
        self, request: WaveReprioritizeRequest
    ) -> WaveReprioritizeResult:
        tasks = self._wave_tasks(zone=request.zone)

        # FAILED: no tasks to reprioritize
        if not tasks:
            raise BackendUnavailable(
                f"No wave tasks found for zone={request.zone!r} wave_id={request.wave_id!r}"
            )

        # NO_OP: all tasks already have the requested priority
        already_correct = [t for t in tasks if t.priority == request.new_priority]
        if len(already_correct) == len(tasks):
            return WaveReprioritizeResult(
                success=True,
                tasks_updated=0,
                wave_id=request.wave_id,
                new_priority=request.new_priority,
                proposal_id=request.proposal_id,
                decision_id=request.decision_id,
                execution_id=request.execution_id,
                outcome="no_op",
                source=self._world.SOURCE,
                message=f"[SIM] NO_OP: all {len(tasks)} task(s) already at priority '{request.new_priority}'",
            )

        # ── MUTATION ────────────────────────────────────────────────────────────
        changed = 0
        for t in tasks:
            if t.priority != request.new_priority:
                t.priority = request.new_priority
                changed += 1
        self._mutation_count += 1

        import asyncio

        asyncio.create_task(
            self._bus.publish_wave_write(
                zone=request.zone,
                new_priority=request.new_priority,
                tasks_updated=changed,
            )
        )

        # Fault injection: raise AFTER mutation to simulate ambiguous write
        if self._post_mutation_fault is not None:
            fault = self._post_mutation_fault
            self._post_mutation_fault = None
            raise fault

        return WaveReprioritizeResult(
            success=True,
            tasks_updated=changed,
            wave_id=request.wave_id,
            new_priority=request.new_priority,
            proposal_id=request.proposal_id,
            decision_id=request.decision_id,
            execution_id=request.execution_id,
            outcome="executed",
            source=self._world.SOURCE,
            message=f"[SIM] Reprioritized {changed} task(s) to '{request.new_priority}'",
        )
