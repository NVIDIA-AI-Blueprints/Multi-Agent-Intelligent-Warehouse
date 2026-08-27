# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
DemoKPIEngine — computes KPI snapshots from DemoWarehouseWorld state.

No side effects; pure computation from world state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

PICKS_PER_ACTIVE_WORKER_PER_HOUR = 12

_WAVE_TASK_TYPES = frozenset({"PICK", "PACK", "SHIP", "RECEIVE", "PUTAWAY", "TRANSFER"})

_WAVE_RISK_SCORE: dict[str, float] = {
    "none": 0.0,
    "low": 20.0,
    "medium": 50.0,
    "high": 75.0,
    "critical": 95.0,
}


@dataclass
class KPISnapshot:
    sim_time_seconds: int
    clock_iso: str
    # EXACT metrics (label in API/UI)
    equipment_total: int
    equipment_operational_pct: float  # (available+assigned+charging)/total*100
    labor_total: int
    labor_availability_pct: float  # active/total*100
    labor_utilization_pct: float  # workers_with_task/active*100
    pending_backlog: int
    wave_risk_score: float  # 0-100 numeric
    wave_risk_level: str  # none/low/medium/high/critical
    low_stock_count: int
    state_freshness_seconds: float | None  # None if never analyzed
    # SIMULATION-DERIVED PROXY metrics
    service_risk_index: float  # PROXY — fraction of critical deadline tasks
    capacity_throughput_proxy: float  # PROXY — active_with_task * 12
    # New EXACT within simulation metrics
    wave_completion_pct: float  # completed wave tasks / total wave tasks * 100
    simulated_throughput: float  # work units completed in last 3600 sim-seconds
    # New SIMULATION-DERIVED metrics
    projected_service_level: (
        float  # fraction of deadline tasks projected to complete on time
    )
    time_to_recovery_seconds: (
        float | None
    )  # sim seconds from disruption to recovery; None if not yet recovered

    def to_dict(self) -> dict[str, Any]:
        return {
            "sim_time_seconds": self.sim_time_seconds,
            "clock_iso": self.clock_iso,
            "equipment_total": self.equipment_total,
            "equipment_operational_pct": self.equipment_operational_pct,
            "labor_total": self.labor_total,
            "labor_availability_pct": self.labor_availability_pct,
            "labor_utilization_pct": self.labor_utilization_pct,
            "pending_backlog": self.pending_backlog,
            "wave_risk_score": self.wave_risk_score,
            "wave_risk_level": self.wave_risk_level,
            "low_stock_count": self.low_stock_count,
            "state_freshness_seconds": self.state_freshness_seconds,
            "service_risk_index": self.service_risk_index,
            "capacity_throughput_proxy": self.capacity_throughput_proxy,
            "wave_completion_pct": self.wave_completion_pct,
            "simulated_throughput": self.simulated_throughput,
            "projected_service_level": self.projected_service_level,
            "time_to_recovery_seconds": self.time_to_recovery_seconds,
        }

    def to_sse_detail(self) -> str:
        return (
            f"equip={self.equipment_operational_pct:.0f}% "
            f"labor_avail={self.labor_availability_pct:.0f}% "
            f"backlog={self.pending_backlog} "
            f"wave={self.wave_risk_level}"
        )

    def delta_to(self, other: "KPISnapshot") -> dict[str, float | int]:
        """Return delta: other - self. Negative pending_backlog/wave_risk = improvement."""
        return {
            "equipment_operational_pct": round(
                other.equipment_operational_pct - self.equipment_operational_pct, 1
            ),
            "labor_availability_pct": round(
                other.labor_availability_pct - self.labor_availability_pct, 1
            ),
            "labor_utilization_pct": round(
                other.labor_utilization_pct - self.labor_utilization_pct, 1
            ),
            "pending_backlog": other.pending_backlog - self.pending_backlog,
            "wave_risk_score": round(other.wave_risk_score - self.wave_risk_score, 1),
            "low_stock_count": other.low_stock_count - self.low_stock_count,
            "service_risk_index": round(
                other.service_risk_index - self.service_risk_index, 1
            ),
            "capacity_throughput_proxy": round(
                other.capacity_throughput_proxy - self.capacity_throughput_proxy, 1
            ),
            "wave_completion_pct": round(
                other.wave_completion_pct - self.wave_completion_pct, 1
            ),
            "simulated_throughput": round(
                other.simulated_throughput - self.simulated_throughput, 1
            ),
            "projected_service_level": round(
                other.projected_service_level - self.projected_service_level, 1
            ),
        }


class DemoKPIEngine:
    """Computes KPI snapshots from DemoWarehouseWorld state. No side effects."""

    def __init__(
        self,
        world: "DemoWarehouseWorld",
        last_analyze_wall_time: datetime | None = None,
    ) -> None:
        self._world = world
        self._last_analyze_wall_time = last_analyze_wall_time

    def compute(self) -> KPISnapshot:
        world = self._world
        elapsed = world.clock.elapsed_seconds

        # Equipment
        eq_list = list(world.equipment.values())
        eq_total = len(eq_list)
        eq_operational = sum(
            1 for a in eq_list if a.status in ("available", "assigned", "charging")
        )
        eq_pct = round(eq_operational / max(eq_total, 1) * 100, 1)

        # Labor
        wk_list = list(world.workers.values())
        wk_total = len(wk_list)
        wk_active = sum(1 for w in wk_list if w.status == "active")
        wk_with_task = sum(
            1 for w in wk_list if w.status == "active" and w.current_task_id is not None
        )
        labor_avail_pct = round(wk_active / max(wk_total, 1) * 100, 1)
        labor_util_pct = round(wk_with_task / max(wk_active, 1) * 100, 1)

        # Backlog
        pending_backlog = sum(1 for t in world.tasks.values() if t.status == "pending")

        # Wave risk (inline — avoids async call to WaveProvider)
        wave_tasks = [
            t for t in world.tasks.values() if t.task_type in _WAVE_TASK_TYPES
        ]
        at_risk = [
            t for t in wave_tasks if t.status == "pending" and t.assigned_to is None
        ]
        has_deadline = any(t.deadline is not None for t in at_risk)
        has_high_priority = any(t.priority in ("high", "critical") for t in at_risk)

        if not at_risk:
            wave_risk_level = "none"
        elif has_high_priority and has_deadline:
            wave_risk_level = "critical"
        elif has_deadline:
            wave_risk_level = "high"
        elif len(at_risk) > 2:
            wave_risk_level = "medium"
        else:
            wave_risk_level = "low"

        wave_risk_score = _WAVE_RISK_SCORE[wave_risk_level]

        # Inventory
        low_stock_count = sum(1 for i in world.inventory.values() if i.is_low_stock)

        # State freshness
        freshness: float | None = None
        if self._last_analyze_wall_time is not None:
            freshness = round(
                (
                    datetime.now(tz=timezone.utc) - self._last_analyze_wall_time
                ).total_seconds(),
                1,
            )

        # PROXY: Service Risk Index
        critical_deadline = [
            t
            for t in wave_tasks
            if t.status == "pending"
            and t.deadline is not None
            and t.priority in ("high", "critical")
        ]
        service_risk_index = (
            round(min(100.0, len(critical_deadline) / max(len(wave_tasks), 1) * 100), 1)
            if wave_tasks
            else 0.0
        )

        # PROXY: Capacity Throughput Proxy
        capacity_throughput_proxy = round(
            wk_with_task * PICKS_PER_ACTIVE_WORKER_PER_HOUR, 1
        )

        # NEW: Wave completion %
        wave_counts = world.wave_task_counts()
        total_wave = sum(wave_counts.values())
        completed_wave = wave_counts.get("completed", 0)
        wave_completion_pct = round(completed_wave / max(total_wave, 1) * 100, 1)

        # NEW: Simulated throughput — work units completed in the last 3600 sim-seconds
        window_start = elapsed - 3600
        throughput_units = sum(
            units for t, units in world._completion_log if t >= window_start
        )
        simulated_throughput = round(
            throughput_units / 1.0, 1
        )  # units per 60 min window

        # NEW: Projected service level (SIMULATION-DERIVED — not OTIF)
        deadline_tasks = [
            t
            for t in world.tasks.values()
            if t.deadline is not None and t.status in ("pending", "in_progress")
        ]
        if not deadline_tasks:
            projected_service_level = 100.0
        else:
            on_track = 0
            for t in deadline_tasks:
                try:
                    dl = datetime.fromisoformat(t.deadline)
                    world_now = world.clock.now()
                    time_to_deadline = (dl - world_now).total_seconds()
                    # Estimate remaining work
                    if (
                        t.status == "in_progress"
                        and t.started_at_sim_seconds is not None
                    ):
                        remaining = t.processing_duration_seconds - (
                            elapsed - t.started_at_sim_seconds
                        )
                        remaining = max(0, remaining)
                    else:
                        remaining = t.processing_duration_seconds
                    if remaining <= time_to_deadline:
                        on_track += 1
                except (ValueError, TypeError):
                    pass  # Unparseable deadline — skip
            projected_service_level = round(
                on_track / max(len(deadline_tasks), 1) * 100, 1
            )

        # NEW: Time to recovery
        if (
            world._recovery_sim_time is not None
            and world._disruption_sim_time is not None
        ):
            time_to_recovery_seconds = float(
                world._recovery_sim_time - world._disruption_sim_time
            )
        else:
            time_to_recovery_seconds = None

        return KPISnapshot(
            sim_time_seconds=elapsed,
            clock_iso=world.clock.now().isoformat(),
            equipment_total=eq_total,
            equipment_operational_pct=eq_pct,
            labor_total=wk_total,
            labor_availability_pct=labor_avail_pct,
            labor_utilization_pct=labor_util_pct,
            pending_backlog=pending_backlog,
            wave_risk_score=wave_risk_score,
            wave_risk_level=wave_risk_level,
            low_stock_count=low_stock_count,
            state_freshness_seconds=freshness,
            service_risk_index=service_risk_index,
            capacity_throughput_proxy=capacity_throughput_proxy,
            wave_completion_pct=wave_completion_pct,
            simulated_throughput=simulated_throughput,
            projected_service_level=projected_service_level,
            time_to_recovery_seconds=time_to_recovery_seconds,
        )
