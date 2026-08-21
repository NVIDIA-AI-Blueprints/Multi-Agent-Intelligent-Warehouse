# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
LaborState — projected operational labor context.

``LaborState`` is NOT a raw database mirror.  It contains the fields
relevant for agent reasoning and DecisionEngine evaluation:

    - Worker availability count and utilization
    - Per-zone labor summary for cross-domain reasoning
    - Freshness of the data

Populated by ``WarehouseStateProvider`` calling ``LaborCapacitySkill``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from maiw_state.freshness import StateFreshness


class LaborWorkerSummary(BaseModel):
    """Operational summary for a single worker (minimal agent-facing projection)."""

    worker_id: str
    username: str
    full_name: str | None = None
    role: str = Field(description="operator | supervisor | manager")
    status: str = Field(description="active | inactive | on_leave")
    zone: str | None = None


class LaborZoneSummary(BaseModel):
    """Aggregated labor capacity for one zone."""

    zone: str
    total_workers: int = 0
    active_workers: int = 0
    utilization_pct: float = Field(default=0.0, description="0–100")


class LaborState(BaseModel):
    """
    Operational labor snapshot for a warehouse.

    Represents what the agent knows about workforce at a point in time.
    Populated through ``warehouse.labor.get_capacity`` capability calls.
    """

    warehouse_id: str
    workers: list[LaborWorkerSummary] = Field(default_factory=list)
    total_workers: int = Field(ge=0, default=0)
    available_workers: int = Field(ge=0, default=0)
    utilization_pct: float = Field(default=0.0, description="Fleet-wide 0–100")
    zone_summary: list[LaborZoneSummary] = Field(default_factory=list)
    freshness: StateFreshness

    @property
    def is_constrained(self) -> bool:
        """True when available workers is 20% or less of total (heuristic)."""
        if self.total_workers == 0:
            return True
        return (self.available_workers / self.total_workers) <= 0.20

    @classmethod
    def from_capacity_result(
        cls,
        warehouse_id: str,
        result: object,  # LaborCapacityResult — duck-typed to avoid circular dep
        *,
        freshness: StateFreshness,
    ) -> LaborState:
        """
        Project a ``LaborCapacityResult`` into ``LaborState``.

        Accepts any object with .workers (list), .total_workers, .available_workers,
        .utilization_pct attributes (structural duck-typing).
        """
        workers = [
            LaborWorkerSummary(
                worker_id=w.worker_id,
                username=w.username,
                full_name=w.full_name,
                role=w.role,
                status=w.status,
                zone=w.zone,
            )
            for w in result.workers
        ]

        # Build zone summaries from worker list
        zone_map: dict[str, list[LaborWorkerSummary]] = {}
        for w in workers:
            if w.zone:
                zone_map.setdefault(w.zone, []).append(w)

        zone_summary = [
            LaborZoneSummary(
                zone=zone,
                total_workers=len(zone_workers),
                active_workers=sum(1 for w in zone_workers if w.status == "active"),
                utilization_pct=round(
                    sum(1 for w in zone_workers if w.status == "active")
                    / max(len(zone_workers), 1)
                    * 100,
                    1,
                ),
            )
            for zone, zone_workers in zone_map.items()
        ]

        return cls(
            warehouse_id=warehouse_id,
            workers=workers,
            total_workers=result.total_workers,
            available_workers=result.available_workers,
            utilization_pct=result.utilization_pct,
            zone_summary=zone_summary,
            freshness=freshness,
        )
