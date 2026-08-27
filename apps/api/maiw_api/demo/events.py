# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
ScenarioEventBus — structured pub-sub for simulation events.

Architecture
------------
- ``ScenarioEvent`` is the canonical event type for all demo activity.
- ``ScenarioEventBus`` holds a list of asyncio.Queue subscribers.
- Providers call ``publish_*`` helpers after mutating world state.
- ``DemoScenarioController`` calls ``publish_scenario`` for lifecycle events.
- The SSE router calls ``subscribe()`` and streams events to the browser.

The bus never imports from agents, skills, or decision packages.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

logger = logging.getLogger(__name__)

# ── Event types ───────────────────────────────────────────────────────────────

EventCategory = Literal[
    "STATE",          # Scenario lifecycle (start/pause/resume/reset)
    "INJECT",         # Manual fault / event injection
    "TICK",           # Clock tick
    "EXECUTE",        # Provider write executed (assign/release/maintenance/allocate/reprioritize)
    "MCP",            # MCP domain read activity
    "API",            # Demo API calls
    # MAIW Analysis lifecycle
    "OBSERVE",        # State assembly from SimulationProviders
    "REASON",         # ModelGateway call + OperationalAssessment produced
    "SKILL",          # Proposal builder invoked
    "PROPOSE",        # ActionProposal constructed
    "DECIDE",         # DecisionEngine evaluated proposal
    "OBSERVE_OUTCOME",  # Post-execution state refresh
    "KPI",            # KPI snapshot
    "RECOVERY",       # Recovery conditions met after disruption
    "APPROVE",        # Human approved a pending proposal
    "REJECT",         # Human rejected a pending proposal
    "RECONCILE",      # UNKNOWN execution reconciled against authoritative state
    # Operational failure labels (Phase 10E Checkpoint D)
    "MODEL TIMEOUT",       # NIM did not respond in time
    "REQUEST DEADLINE",    # Analyze/execution/reconciliation deadline exhausted
    "CAPABILITY TIMEOUT",  # MCP capability did not respond in time
    # Fault injection / reliability labels (Phase 10E Batch 6)
    "FAULT_INJECTED",          # Deterministic fault was triggered (test/demo boundary only)
    "CIRCUIT_OPEN",            # Domain circuit breaker tripped; calls rejected
    "RECONCILIATION_REQUIRED", # UNKNOWN execution requires operator reconciliation
    "CONFIRMED_EXECUTED",      # Reconciliation confirmed: mutation occurred
    "CONFIRMED_NOT_EXECUTED",  # Reconciliation confirmed: mutation did not occur
    "INDETERMINATE",           # Reconciliation cannot resolve; manual intervention needed
]


@dataclass
class ScenarioEvent:
    """A single structured simulation event."""

    category: EventCategory
    message: str
    detail: str = ""
    asset_id: str | None = None
    task_id: str | None = None
    worker_id: str | None = None
    sim_time_seconds: int | None = None
    ts: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))

    def to_sse_dict(self) -> dict:
        """Serialize to a dict suitable for JSON SSE payload."""
        return {
            "id": f"{self.ts.isoformat()}-{self.category}",
            "ts": self.ts.isoformat(),
            "category": self.category,
            "message": self.message,
            "detail": self.detail or None,
            "asset_id": self.asset_id,
            "task_id": self.task_id,
            "worker_id": self.worker_id,
            "sim_time_seconds": self.sim_time_seconds,
        }


# ── Bus ───────────────────────────────────────────────────────────────────────

class ScenarioEventBus:
    """
    Pub-sub event bus backed by asyncio queues.

    One queue per SSE subscriber.  The bus is a process singleton created
    by ``DemoScenarioController`` and injected into all SimulationProviders.
    """

    _MAX_QUEUE_DEPTH = 200
    _MAX_SUBSCRIBERS = 32

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []

    # ── Subscriber management ─────────────────────────────────────────────────

    def subscribe(self) -> asyncio.Queue:
        """Register a new SSE subscriber and return its dedicated queue."""
        if len(self._subscribers) >= self._MAX_SUBSCRIBERS:
            # Drop the oldest subscriber to bound memory usage
            dropped = self._subscribers.pop(0)
            logger.warning("ScenarioEventBus: max subscribers reached; evicting oldest")
            try:
                dropped.put_nowait(None)  # Sentinel to close SSE stream
            except Exception:
                pass
        q: asyncio.Queue = asyncio.Queue(maxsize=self._MAX_QUEUE_DEPTH)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Remove a subscriber queue (called on SSE disconnect)."""
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    # ── Publishing ────────────────────────────────────────────────────────────

    async def publish(self, event: ScenarioEvent) -> None:
        """Broadcast an event to all subscribers."""
        dead: list[asyncio.Queue] = []
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest item in this subscriber's queue to make room
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:
                    dead.append(q)
        for q in dead:
            self.unsubscribe(q)

    # ── Convenience publish helpers ───────────────────────────────────────────

    async def publish_scenario(
        self, message: str, detail: str = ""
    ) -> None:
        await self.publish(ScenarioEvent(
            category="STATE",
            message=message,
            detail=detail,
        ))

    async def publish_inject(
        self, event_type: str, detail: str = "", asset_id: str | None = None,
        sim_time_seconds: int | None = None,
    ) -> None:
        await self.publish(ScenarioEvent(
            category="INJECT",
            message=f"inject:{event_type}",
            detail=detail,
            asset_id=asset_id,
            sim_time_seconds=sim_time_seconds,
        ))

    async def publish_tick(self, elapsed_seconds: int, clock_iso: str, sim_time_seconds: int | None = None) -> None:
        await self.publish(ScenarioEvent(
            category="TICK",
            message=f"clock tick +{elapsed_seconds}s",
            detail=clock_iso,
            sim_time_seconds=sim_time_seconds,
        ))

    async def publish_equipment_write(
        self, action: str, asset_id: str, detail: str = ""
    ) -> None:
        await self.publish(ScenarioEvent(
            category="EXECUTE",
            message=f"equipment.{action}",
            detail=detail,
            asset_id=asset_id,
        ))

    async def publish_labor_write(
        self, task_id: str, worker_ids: list[str]
    ) -> None:
        await self.publish(ScenarioEvent(
            category="EXECUTE",
            message="labor.allocate",
            detail=f"workers={','.join(worker_ids)}",
            task_id=task_id,
        ))

    async def publish_wave_write(
        self, zone: str | None, new_priority: str, tasks_updated: int
    ) -> None:
        await self.publish(ScenarioEvent(
            category="EXECUTE",
            message="wave.reprioritize",
            detail=f"zone={zone or 'all'} priority={new_priority} tasks={tasks_updated}",
        ))

    async def publish_observe(
        self, message: str, detail: str = "", trace_id: str | None = None,
        sim_time_seconds: int | None = None,
    ) -> None:
        await self.publish(ScenarioEvent(
            category="OBSERVE",
            message=message,
            detail=detail if not trace_id else f"{detail} trace={trace_id[:8]}" if detail else f"trace={trace_id[:8]}",
            sim_time_seconds=sim_time_seconds,
        ))

    async def publish_reason(
        self, model_id: str, routing_rule: str, summary: str, trace_id: str | None = None,
        sim_time_seconds: int | None = None,
    ) -> None:
        detail = f"model={model_id} rule={routing_rule}"
        if trace_id:
            detail += f" trace={trace_id[:8]}"
        await self.publish(ScenarioEvent(
            category="REASON",
            message=summary[:120],
            detail=detail,
            sim_time_seconds=sim_time_seconds,
        ))

    async def publish_skill(
        self, capability: str, target: str, trace_id: str | None = None,
        sim_time_seconds: int | None = None,
    ) -> None:
        detail = f"target={target}"
        if trace_id:
            detail += f" trace={trace_id[:8]}"
        await self.publish(ScenarioEvent(
            category="SKILL",
            message=capability,
            detail=detail,
            sim_time_seconds=sim_time_seconds,
        ))

    async def publish_propose(
        self, action: str, proposal_id: str, trace_id: str | None = None,
        sim_time_seconds: int | None = None,
    ) -> None:
        detail = f"proposal={proposal_id[:8]}"
        if trace_id:
            detail += f" trace={trace_id[:8]}"
        await self.publish(ScenarioEvent(
            category="PROPOSE",
            message=action,
            detail=detail,
            sim_time_seconds=sim_time_seconds,
        ))

    async def publish_decide(
        self, outcome: str, proposal_id: str, decision_id: str, trace_id: str | None = None,
        sim_time_seconds: int | None = None,
    ) -> None:
        detail = f"proposal={proposal_id[:8]} decision={decision_id[:8]}"
        if trace_id:
            detail += f" trace={trace_id[:8]}"
        await self.publish(ScenarioEvent(
            category="DECIDE",
            message=f"outcome={outcome}",
            detail=detail,
            sim_time_seconds=sim_time_seconds,
        ))

    async def publish_observe_outcome(
        self, message: str, detail: str = "", trace_id: str | None = None,
        sim_time_seconds: int | None = None,
    ) -> None:
        if trace_id:
            detail = f"{detail} trace={trace_id[:8]}" if detail else f"trace={trace_id[:8]}"
        await self.publish(ScenarioEvent(
            category="OBSERVE_OUTCOME",
            message=message,
            detail=detail,
            sim_time_seconds=sim_time_seconds,
        ))

    async def publish_approve(
        self,
        capability: str,
        proposal_id: str,
        approved_by: str,
        *,
        trace_id: str | None = None,
        sim_time_seconds: int | None = None,
    ) -> None:
        await self.publish(ScenarioEvent(
            category="APPROVE",
            message=f"approved:{capability}",
            detail=f"proposal={proposal_id[:8]} by={approved_by}",
            sim_time_seconds=sim_time_seconds,
        ))

    async def publish_reject(
        self,
        capability: str,
        proposal_id: str,
        rejected_by: str,
        *,
        trace_id: str | None = None,
        sim_time_seconds: int | None = None,
    ) -> None:
        await self.publish(ScenarioEvent(
            category="REJECT",
            message=f"rejected:{capability}",
            detail=f"proposal={proposal_id[:8]} by={rejected_by}",
            sim_time_seconds=sim_time_seconds,
        ))

    async def publish_kpi(self, kpi_dict: dict, sim_time_seconds: int) -> None:
        detail = (
            f"equip={kpi_dict.get('equipment_operational_pct', 0):.0f}% "
            f"labor={kpi_dict.get('labor_availability_pct', 0):.0f}% "
            f"backlog={kpi_dict.get('pending_backlog', 0)} "
            f"wave={kpi_dict.get('wave_risk_level', '?')}"
        )
        await self.publish(ScenarioEvent(
            category="KPI",
            message="kpi:snapshot",
            detail=detail,
            sim_time_seconds=sim_time_seconds,
        ))
