# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
DemoScenarioController — scenario lifecycle management for the simulation layer.

Responsibilities
----------------
- Load scenario YAML definitions
- Seed the DemoWarehouseWorld from scenario initial_state
- Capture the initial snapshot for reset support
- Process timed_events as the clock advances
- Expose start / pause / resume / reset / tick / inject / status
- Publish lifecycle events to ScenarioEventBus

Invariants
----------
- ZERO agent, skill, decision, or MCP business logic lives here.
- All state mutations go through DemoWarehouseWorld methods or direct
  field writes on world entities (which SimulationProviders then read).
- The controller never calls configure_server() — that is done in bootstrap.py.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid as _uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from maiw_api.demo.events import ScenarioEvent, ScenarioEventBus
from maiw_api.demo.providers.equipment import SimulationEquipmentProvider
from maiw_api.demo.providers.inventory import SimulationInventoryProvider
from maiw_api.demo.providers.labor import SimulationLaborProvider
from maiw_api.demo.providers.wave import SimulationWaveProvider
from maiw_api.demo.world import DemoWarehouseWorld
from maiw_decision.approval import InMemoryApprovalStore

logger = logging.getLogger(__name__)

_SCENARIOS_DIR = Path(__file__).parent / "scenarios"

# Event types that count as disruptions for recovery tracking
_DISRUPTION_EVENT_TYPES = frozenset(
    {"equipment_fault", "worker_absence", "low_stock", "wave_delay"}
)


# ── Scenario definition ───────────────────────────────────────────────────────


@dataclass
class TimedEvent:
    offset_seconds: int
    type: str
    payload: dict[str, Any]


@dataclass
class ScenarioDefinition:
    name: str
    display_name: str
    description: str
    tags: list[str]
    rng_seed: int
    clock_offset_seconds: int
    initial_state: dict[str, Any]
    timed_events: list[TimedEvent]
    recovery: dict  # recovery threshold conditions; empty dict = no recovery tracking

    def metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "tags": self.tags,
        }


def _load_scenario_file(path: Path) -> ScenarioDefinition:
    with open(path) as f:
        raw = yaml.safe_load(f)
    timed_events = [
        TimedEvent(
            offset_seconds=e["offset_seconds"],
            type=e["type"],
            payload=e.get("payload", {}),
        )
        for e in (raw.get("timed_events") or [])
    ]
    # Merge clock_offset_seconds into initial_state for world.seed()
    initial_state = dict(raw.get("initial_state", {}))
    initial_state["clock_offset_seconds"] = raw.get("clock_offset_seconds", 0)
    return ScenarioDefinition(
        name=raw["name"],
        display_name=raw.get("display_name", raw["name"]),
        description=raw.get("description", ""),
        tags=raw.get("tags", []),
        rng_seed=raw.get("rng_seed", 42),
        clock_offset_seconds=raw.get("clock_offset_seconds", 0),
        initial_state=initial_state,
        timed_events=timed_events,
        recovery=raw.get("recovery", {}),
    )


def list_scenario_files() -> dict[str, Path]:
    """Return {name: path} for all YAML files in the scenarios directory."""
    return {p.stem: p for p in sorted(_SCENARIOS_DIR.glob("*.yaml"))}


# ── Providers container ───────────────────────────────────────────────────────


@dataclass
class SimulationProviders:
    inventory: SimulationInventoryProvider
    equipment: SimulationEquipmentProvider
    labor: SimulationLaborProvider
    wave: SimulationWaveProvider


# ── Controller ────────────────────────────────────────────────────────────────


class DemoScenarioController:
    """
    Process-singleton controller for the synthetic warehouse demo.

    Lifecycle
    ---------
    1. Created once in bootstrap when MAIW_DEMO_MODE=true.
    2. Providers are wired to mcp_servers via configure_server() in bootstrap.
    3. HTTP handlers call start/pause/resume/reset/tick/inject.
    4. SSE handler streams events from bus.subscribe().
    """

    _MAX_KPI_HISTORY = 120

    def __init__(self) -> None:
        self.world = DemoWarehouseWorld()
        self.bus = ScenarioEventBus()
        self.providers = SimulationProviders(
            inventory=SimulationInventoryProvider(self.world),
            equipment=SimulationEquipmentProvider(self.world, self.bus),
            labor=SimulationLaborProvider(self.world, self.bus),
            wave=SimulationWaveProvider(self.world, self.bus),
        )
        self._scenario: ScenarioDefinition | None = None
        self._snapshot: dict[str, Any] | None = None
        self._paused: bool = False
        self._tick_task: asyncio.Task | None = None
        self._next_event_idx: int = 0  # Index into scenario.timed_events
        self._kpi_history: list[dict] = []
        self._last_inject_wall_time: datetime | None = None
        self._last_analyze_wall_time: datetime | None = None
        self._recovery_sim_time: int | None = None
        self._pending_approvals: list[dict] = []
        self._approval_store: InMemoryApprovalStore = InMemoryApprovalStore()
        # Monotonically-incrementing run identity, reset on start() and reset().
        # Used as a dedup boundary so approvals from a previous run are never
        # confused with those from the current one.
        self._scenario_run_id: str = str(_uuid.uuid4())

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def active(self) -> bool:
        return self._scenario is not None

    @property
    def approval_store(self) -> InMemoryApprovalStore:
        return self._approval_store

    @property
    def scenario_name(self) -> str | None:
        return self._scenario.name if self._scenario else None

    # ── Scenario listing ──────────────────────────────────────────────────────

    def list_scenarios(self) -> list[dict[str, Any]]:
        """Return metadata for all available scenario YAML files."""
        result = []
        for name, path in list_scenario_files().items():
            try:
                defn = _load_scenario_file(path)
                result.append(defn.metadata())
            except Exception as exc:
                logger.warning("Failed to load scenario '%s': %s", name, exc)
        return result

    # ── start ─────────────────────────────────────────────────────────────────

    async def start(self, scenario_name: str) -> None:
        """Load and activate a scenario.  Replaces any currently active scenario."""
        files = list_scenario_files()
        if scenario_name not in files:
            raise ValueError(
                f"Scenario '{scenario_name}' not found. " f"Available: {sorted(files)}"
            )
        defn = _load_scenario_file(files[scenario_name])
        self._cancel_tick_task()

        self.world.seed(defn.initial_state, rng_seed=defn.rng_seed)
        self._snapshot = self.world.snapshot()
        self._scenario = defn
        self._paused = False
        self._next_event_idx = 0
        self._recovery_sim_time = None
        self._pending_approvals = []
        self._scenario_run_id = str(_uuid.uuid4())

        logger.info("Demo: started scenario '%s'", scenario_name)
        await self.bus.publish_scenario(
            message=f"scenario:start:{scenario_name}",
            detail=defn.display_name,
        )

    # ── pause / resume ────────────────────────────────────────────────────────

    async def pause(self) -> None:
        if not self.active:
            raise RuntimeError("No active scenario")
        self._paused = True
        self._cancel_tick_task()
        await self.bus.publish_scenario(message="scenario:pause")

    async def resume(self) -> None:
        if not self.active:
            raise RuntimeError("No active scenario")
        self._paused = False
        await self.bus.publish_scenario(message="scenario:resume")

    # ── reset ─────────────────────────────────────────────────────────────────

    async def reset(self) -> None:
        if not self.active:
            raise RuntimeError("No active scenario")
        self._cancel_tick_task()
        if self._snapshot is None:
            raise RuntimeError("No snapshot available — call start() first")
        self.world.reset(self._snapshot)
        self._paused = False
        self._next_event_idx = 0
        self._kpi_history = []
        self._last_inject_wall_time = None
        self._recovery_sim_time = None
        self._pending_approvals = []
        self._approval_store.reset()
        self._scenario_run_id = str(_uuid.uuid4())
        await self.bus.publish_scenario(
            message="scenario:reset",
            detail=self._scenario.name if self._scenario else "",
        )

    # ── tick ──────────────────────────────────────────────────────────────────

    async def tick(self, seconds: int = 60) -> None:
        """Advance the simulation clock and fire any due timed events."""
        if not self.active:
            raise RuntimeError("No active scenario")
        if self._paused:
            raise RuntimeError("Scenario is paused — call resume() first")
        if seconds < 1:
            raise ValueError("tick seconds must be >= 1")

        self.world.clock.tick(seconds)
        elapsed = self.world.clock.elapsed_seconds
        clock_iso = self.world.clock.now().isoformat()

        # 1. Fire due scenario timed events
        await self._fire_due_events(elapsed)

        # 2. Advance task progression and complete eligible tasks
        completed = self._advance_task_progression(elapsed)

        # 3. Check recovery conditions
        newly_recovered = self._check_recovery(elapsed)

        # 4. Compute KPI snapshot and publish
        from maiw_api.demo.kpi import DemoKPIEngine

        kpi = DemoKPIEngine(self.world, self._last_analyze_wall_time).compute()
        kpi_dict = kpi.to_dict()
        self._kpi_history.append(kpi_dict)
        if len(self._kpi_history) > self._MAX_KPI_HISTORY:
            self._kpi_history = self._kpi_history[-self._MAX_KPI_HISTORY :]

        # 5. Publish events
        await self.bus.publish_tick(
            elapsed_seconds=seconds, clock_iso=clock_iso, sim_time_seconds=elapsed
        )
        await self.bus.publish_kpi(kpi_dict, elapsed)

        if newly_recovered:
            ttr = elapsed - (self.world._disruption_sim_time or elapsed)
            await self.bus.publish(
                ScenarioEvent(
                    category="RECOVERY",
                    message="scenario:recovery:detected",
                    detail=f"TTR={ttr}s wave_risk={kpi.wave_risk_level} backlog={kpi.pending_backlog}",
                    sim_time_seconds=elapsed,
                )
            )

    # ── inject ────────────────────────────────────────────────────────────────

    async def inject(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Apply an ad-hoc fault or event to world state.

        Supported types
        ---------------
        equipment_fault         — set asset status/fault_code
        equipment_restore       — restore asset to available
        low_stock               — reduce inventory quantity
        worker_absence          — set worker status to on_leave
        worker_return           — set worker status to active
        task_deadline           — add/update deadline on a task
        wave_delay              — set all pending tasks to low priority + add deadline
        """
        if not self.active:
            raise RuntimeError("No active scenario")

        result = await self._apply_event(event_type, payload)
        self._last_inject_wall_time = datetime.now(tz=timezone.utc)

        # Record first disruption time (excluding tick/metadata events)
        if event_type in _DISRUPTION_EVENT_TYPES:
            if self.world._disruption_sim_time is None:
                self.world._disruption_sim_time = self.world.clock.elapsed_seconds

        await self.bus.publish_inject(
            event_type=event_type,
            detail=str(payload),
            asset_id=payload.get("asset_id"),
            sim_time_seconds=self.world.clock.elapsed_seconds,
        )
        return result

    # ── pending approvals ─────────────────────────────────────────────────────

    def add_pending_approval(
        self,
        *,
        proposal_id: str,
        decision_id: str,
        trace_id: str,
        capability: str,
        target: str,
        domain: str,
        priority: str,
        objective: str,
        rationale: str,
        risk_level: str,
        warehouse_id: str | None = None,
        proposal_data: dict | None = None,
    ) -> str:
        """Store a proposal pending human approval. Returns pending_id.

        Dedup: if a pending approval with the same logical identity
        (scenario_run_id + capability + target + domain) already exists for
        this run, returns its existing pending_id without creating a duplicate.
        This prevents retry storms from the frontend creating multiple
        approval cards for the same logical proposal.
        """
        dedup_key = f"{self._scenario_run_id}|{capability}|{target}|{domain}"
        for pa in self._pending_approvals:
            if pa.get("_dedup_key") == dedup_key:
                logger.debug(
                    "Dedup: returning existing pending_id=%s for key=%s",
                    pa["pending_id"], dedup_key,
                )
                return pa["pending_id"]

        approval_record = self._approval_store.create(
            proposal_id=proposal_id,
            decision_id=decision_id,
            warehouse_id=warehouse_id,
            trace_id=trace_id,
        )
        pending_id = str(_uuid.uuid4())
        self._pending_approvals.append({
            "pending_id": pending_id,
            "approval_id": approval_record.approval_id,
            "proposal_id": proposal_id,
            "decision_id": decision_id,
            "trace_id": trace_id,
            "capability": capability,
            "target": target,
            "domain": domain,
            "priority": priority,
            "objective": objective,
            "rationale": rationale,
            "risk_level": risk_level,
            "warehouse_id": warehouse_id,
            "proposal_data": proposal_data,
            "queued_at": datetime.now(tz=timezone.utc).isoformat(),
            "_dedup_key": dedup_key,
        })
        return pending_id

    def remove_pending_approval(self, pending_id: str) -> dict | None:
        """Remove and return a pending approval by pending_id."""
        for i, pa in enumerate(self._pending_approvals):
            if pa["pending_id"] == pending_id:
                return self._pending_approvals.pop(i)
        return None

    # ── status ────────────────────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        """Return current controller + world status for GET /demo/status."""
        world_summary = self.world.status_summary() if self.active else {}
        from maiw_api.demo.kpi import DemoKPIEngine

        current_kpis = (
            DemoKPIEngine(self.world, self._last_analyze_wall_time).compute().to_dict()
            if self.active
            else None
        )
        return {
            "active": self.active,
            "scenario": self._scenario.metadata() if self._scenario else None,
            "paused": self._paused,
            "world": world_summary,
            "current_kpis": current_kpis,
            "kpi_history": list(self._kpi_history),
            "pending_approvals": [
                {k: v for k, v in pa.items() if k != "_dedup_key"}
                for pa in self._pending_approvals
            ],
        }

    # ── internal helpers ──────────────────────────────────────────────────────

    def _cancel_tick_task(self) -> None:
        if self._tick_task is not None and not self._tick_task.done():
            self._tick_task.cancel()
        self._tick_task = None

    def _advance_task_progression(self, elapsed: int) -> int:
        """Advance in_progress task completion. Returns count of tasks completed this tick."""
        completed = 0
        for task in self.world.tasks.values():
            if task.status != "in_progress":
                continue
            if task.started_at_sim_seconds is None:
                continue
            time_worked = elapsed - task.started_at_sim_seconds
            if time_worked >= task.processing_duration_seconds:
                task.status = "completed"
                # Release worker
                if task.assigned_to:
                    worker = self.world.workers.get(task.assigned_to)
                    if worker is not None:
                        worker.current_task_id = None
                task.assigned_to = None
                self.world._completion_log.append((elapsed, task.work_units))
                completed += 1
        return completed

    def _check_recovery(self, elapsed: int) -> bool:
        """Check if recovery conditions are met. Returns True if newly recovered."""
        if not self._scenario or not self._scenario.recovery:
            return False
        if self._recovery_sim_time is not None:
            return False  # already detected
        if self.world._disruption_sim_time is None:
            return False  # no disruption recorded yet

        r = self._scenario.recovery
        from maiw_api.demo.kpi import DemoKPIEngine

        kpi = DemoKPIEngine(self.world, self._last_analyze_wall_time).compute()

        if (
            "wave_risk_max_score" in r
            and kpi.wave_risk_score > r["wave_risk_max_score"]
        ):
            return False
        if "backlog_max" in r and kpi.pending_backlog > r["backlog_max"]:
            return False
        if (
            "labor_availability_min_pct" in r
            and kpi.labor_availability_pct < r["labor_availability_min_pct"] * 100
        ):
            return False

        self.world._recovery_sim_time = elapsed
        self._recovery_sim_time = elapsed  # also track at controller level
        return True

    async def _fire_due_events(self, elapsed: int) -> None:
        """Process any timed events whose offset_seconds <= current elapsed."""
        if self._scenario is None:
            return
        events = self._scenario.timed_events
        while (
            self._next_event_idx < len(events)
            and events[self._next_event_idx].offset_seconds <= elapsed
        ):
            ev = events[self._next_event_idx]
            self._next_event_idx += 1
            try:
                await self._apply_event(ev.type, ev.payload)
                # Record first disruption time for timed disruption events
                if ev.type in _DISRUPTION_EVENT_TYPES:
                    if self.world._disruption_sim_time is None:
                        self.world._disruption_sim_time = elapsed
                await self.bus.publish_inject(
                    event_type=f"timed:{ev.type}",
                    detail=str(ev.payload),
                    asset_id=ev.payload.get("asset_id"),
                )
            except Exception as exc:
                logger.warning("Timed event '%s' failed: %s", ev.type, exc)

    async def _apply_event(
        self, event_type: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Apply a single event to world state; return a summary dict."""

        if event_type == "equipment_fault":
            asset_id = payload["asset_id"]
            asset = self.world.equipment.get(asset_id)
            if asset is None:
                raise ValueError(f"Asset '{asset_id}' not found")
            asset.status = payload.get("new_status", "offline")
            asset.fault_code = payload.get("fault_code") or payload.get("fault")
            if "battery_pct" in payload:
                asset.battery_pct = float(payload["battery_pct"])
            return {"asset_id": asset_id, "status": asset.status}

        if event_type == "equipment_restore":
            asset_id = payload["asset_id"]
            asset = self.world.equipment.get(asset_id)
            if asset is None:
                raise ValueError(f"Asset '{asset_id}' not found")
            asset.status = payload.get("new_status", "available")
            asset.fault_code = None
            if "battery_pct" in payload:
                asset.battery_pct = float(payload["battery_pct"])
            return {"asset_id": asset_id, "status": asset.status}

        if event_type == "low_stock":
            sku = payload["sku"]
            item = self.world.inventory.get(sku)
            if item is None:
                raise ValueError(f"SKU '{sku}' not found")
            item.quantity_available = int(payload.get("quantity_available", 0))
            return {
                "sku": sku,
                "quantity_available": item.quantity_available,
                "is_low_stock": item.is_low_stock,
            }

        if event_type == "worker_absence":
            worker_id = payload["worker_id"]
            worker = self.world.workers.get(worker_id)
            if worker is None:
                raise ValueError(f"Worker '{worker_id}' not found")
            worker.status = payload.get("new_status", "on_leave")
            return {"worker_id": worker_id, "status": worker.status}

        if event_type == "worker_return":
            worker_id = payload["worker_id"]
            worker = self.world.workers.get(worker_id)
            if worker is None:
                raise ValueError(f"Worker '{worker_id}' not found")
            worker.status = "active"
            return {"worker_id": worker_id, "status": "active"}

        if event_type == "task_deadline":
            task_id = payload["task_id"]
            task = self.world.tasks.get(task_id)
            if task is None:
                raise ValueError(f"Task '{task_id}' not found")
            task.deadline = payload["deadline"]
            return {"task_id": task_id, "deadline": task.deadline}

        if event_type == "wave_delay":
            zone = payload.get("zone")
            deadline = payload.get("deadline")
            tasks = self.world.tasks_list(zone=zone, status_filter="pending")
            for t in tasks:
                if deadline:
                    t.deadline = deadline
                t.priority = payload.get("new_priority", "low")
            return {"tasks_affected": len(tasks), "zone": zone}

        raise ValueError(f"Unknown event type: '{event_type}'")


# ── Process singleton ─────────────────────────────────────────────────────────

_controller: DemoScenarioController | None = None


def get_demo_controller() -> DemoScenarioController:
    """
    Return the process-level DemoScenarioController singleton.

    Raises RuntimeError when MAIW_DEMO_MODE is not set so the router
    returns 503, which the UI interprets as demo mode off.
    """
    global _controller
    if _controller is None:
        demo_mode = os.getenv("MAIW_DEMO_MODE", "false").lower() in ("1", "true", "yes")
        if not demo_mode:
            raise RuntimeError(
                "MAIW_DEMO_MODE is not enabled; demo endpoints are inactive"
            )
        _controller = DemoScenarioController()
    return _controller


def reset_demo_controller() -> None:
    """Reset singleton — for testing only."""
    global _controller
    _controller = None
