# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
WaveState — projected operational wave/pick context.

``WaveState`` is NOT a raw WMS data mirror.  It contains the fields
relevant for agent reasoning and DecisionEngine evaluation:

    - Task counts by status and zone
    - OTIF risk indicators
    - Freshness of the data

Populated by ``WarehouseStateProvider`` calling ``WaveGetSkill``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from maiw_state.freshness import StateFreshness


class WaveTaskSummary(BaseModel):
    """Minimal operational task record for agent reasoning."""

    task_id: str
    task_type: str
    zone: str | None = None
    status: str = Field(
        description="pending | in_progress | completed | failed | cancelled"
    )
    priority: str = "medium"
    assigned_to: str | None = None


class WaveZoneSummary(BaseModel):
    """Aggregated wave task counts for one pick zone."""

    zone: str
    total_tasks: int = 0
    pending_tasks: int = 0
    in_progress_tasks: int = 0
    completed_tasks: int = 0


class WaveState(BaseModel):
    """
    Operational wave/pick snapshot for a warehouse.

    Represents what the agent knows about current wave activity at a point
    in time. Populated through ``warehouse.wave.get`` capability calls.
    """

    warehouse_id: str
    tasks: list[WaveTaskSummary] = Field(default_factory=list)
    total_tasks: int = Field(ge=0, default=0)
    pending_count: int = Field(ge=0, default=0)
    in_progress_count: int = Field(ge=0, default=0)
    completed_count: int = Field(ge=0, default=0)
    at_risk_count: int = Field(
        ge=0,
        default=0,
        description="Tasks flagged as OTIF-at-risk (pending past deadline heuristic)",
    )
    zones_active: list[str] = Field(default_factory=list)
    zone_summary: list[WaveZoneSummary] = Field(default_factory=list)
    freshness: StateFreshness

    @property
    def otif_at_risk(self) -> bool:
        """True when any tasks are flagged as OTIF-at-risk."""
        return self.at_risk_count > 0

    @classmethod
    def from_get_result(
        cls,
        warehouse_id: str,
        result: object,  # WaveGetResult — duck-typed to avoid circular dep
        *,
        freshness: StateFreshness,
    ) -> WaveState:
        """
        Project a ``WaveGetResult`` into ``WaveState``.

        Accepts any object with .tasks (list), .total_tasks, .zones_active,
        .summary attributes (structural duck-typing).
        """
        tasks = [
            WaveTaskSummary(
                task_id=t.task_id,
                task_type=t.task_type,
                zone=t.zone,
                status=t.status,
                priority=t.priority,
                assigned_to=t.assigned_to,
            )
            for t in result.tasks
        ]

        summary: dict[str, int] = getattr(result, "summary", {})
        pending = summary.get("pending", 0)
        in_progress = summary.get("in_progress", 0)
        completed = summary.get("completed", 0)

        # Build zone summaries
        zone_map: dict[str, list[WaveTaskSummary]] = {}
        for t in tasks:
            if t.zone:
                zone_map.setdefault(t.zone, []).append(t)

        zone_summary = [
            WaveZoneSummary(
                zone=zone,
                total_tasks=len(zone_tasks),
                pending_tasks=sum(1 for t in zone_tasks if t.status == "pending"),
                in_progress_tasks=sum(
                    1 for t in zone_tasks if t.status == "in_progress"
                ),
                completed_tasks=sum(1 for t in zone_tasks if t.status == "completed"),
            )
            for zone, zone_tasks in zone_map.items()
        ]

        # Simple OTIF heuristic: pending tasks with no assignee are at risk
        at_risk = sum(
            1 for t in tasks if t.status == "pending" and t.assigned_to is None
        )

        return cls(
            warehouse_id=warehouse_id,
            tasks=tasks,
            total_tasks=result.total_tasks,
            pending_count=pending,
            in_progress_count=in_progress,
            completed_count=completed,
            at_risk_count=at_risk,
            zones_active=list(result.zones_active),
            zone_summary=zone_summary,
            freshness=freshness,
        )
