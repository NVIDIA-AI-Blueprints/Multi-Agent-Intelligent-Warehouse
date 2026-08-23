# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
DemoWarehouseWorld — the single mutable source of truth for all simulation state.

All four SimulationProviders share one instance of this class.  Cross-domain
coherence is guaranteed because every domain read/write goes through the same
object.  The world never imports from the MCP contracts or agent packages —
it is a pure data layer.  SimulationProviders translate world state into
contract result types.

Design principles
-----------------
- Deterministic: seeded with a fixed integer; no datetime.now() at seed time.
- Snapshot / reset: deep-copy snapshot for scenario reload without restart.
- No asyncio: all mutations are synchronous; callers may be async but the
  world itself does not schedule work.
- No business logic: the world stores state; the controller applies events.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ── Simulation clock ──────────────────────────────────────────────────────────

class SimulationClock:
    """
    Virtual clock for the demo world.

    Starts at a fixed reference point and advances via ``tick()``.
    ``now()`` returns the current simulated UTC datetime.
    The clock is deliberately not tied to wall time so tests and
    scenario resets are fully deterministic.
    """

    _EPOCH = datetime(2026, 8, 23, 8, 0, 0, tzinfo=timezone.utc)  # DC-47 shift start

    def __init__(self, seed_seconds: int = 0) -> None:
        self._elapsed_seconds: int = seed_seconds

    def tick(self, seconds: int) -> None:
        """Advance the clock by ``seconds``."""
        if seconds < 0:
            raise ValueError("Cannot tick backwards")
        self._elapsed_seconds += seconds

    def now(self) -> datetime:
        """Return current simulated UTC time."""
        from datetime import timedelta
        return self._EPOCH + timedelta(seconds=self._elapsed_seconds)

    @property
    def elapsed_seconds(self) -> int:
        return self._elapsed_seconds

    def snapshot(self) -> dict[str, Any]:
        return {"elapsed_seconds": self._elapsed_seconds}

    def restore(self, snap: dict[str, Any]) -> None:
        self._elapsed_seconds = snap["elapsed_seconds"]


# ── World entity types ────────────────────────────────────────────────────────

@dataclass
class InventoryItem:
    sku: str
    name: str
    zone: str
    location_id: str
    quantity_available: int
    quantity_reserved: int
    reorder_point: int

    @property
    def is_low_stock(self) -> bool:
        return self.quantity_available <= self.reorder_point


@dataclass
class EquipmentAsset:
    asset_id: str
    equipment_type: str          # forklift | amr | agv | scanner | charger
    model: str
    zone: str
    status: str                  # available | assigned | charging | maintenance | offline
    owner_user: str | None = None
    next_pm_due: datetime | None = None
    last_maintenance: datetime | None = None
    fault_code: str | None = None
    battery_pct: float = 100.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkerState:
    worker_id: str
    username: str
    full_name: str
    role: str                    # operator | supervisor | manager
    status: str                  # active | inactive | on_leave
    zone: str | None = None
    current_task_id: str | None = None


@dataclass
class TaskState:
    task_id: str
    task_type: str               # PICK | PACK | SHIP | RECEIVE | PUTAWAY | CYCLE_COUNT
    zone: str | None
    status: str                  # pending | in_progress | completed | failed | cancelled
    assigned_to: str | None = None
    priority: str = "medium"
    deadline: str | None = None  # ISO-8601 string


# ── DemoWarehouseWorld ────────────────────────────────────────────────────────

class DemoWarehouseWorld:
    """
    Complete mutable warehouse state for one demo session.

    Lifecycle
    ---------
    1. ``__init__`` creates empty collections and a clock at t=0.
    2. ``seed(scenario_data, rng_seed)`` populates from a scenario dict.
    3. ``snapshot()`` captures the post-seed state (called by controller).
    4. ``reset(snap)`` restores to snapshot, called on /demo/scenario/reset.
    5. SimulationProviders read/write ``inventory``, ``equipment``,
       ``workers``, and ``tasks`` directly.

    Thread / async safety
    ---------------------
    Mutations are not guarded by a lock.  The FastAPI event loop is
    single-threaded; all writes arrive sequentially.  If background
    tick tasks are added later, use asyncio.Lock at the controller level.
    """

    WAREHOUSE_ID = "DC-47"
    SOURCE = "simulation"

    def __init__(self) -> None:
        self.clock = SimulationClock()
        self.inventory: dict[str, InventoryItem] = {}      # sku → item
        self.equipment: dict[str, EquipmentAsset] = {}     # asset_id → asset
        self.workers: dict[str, WorkerState] = {}          # worker_id → worker
        self.tasks: dict[str, TaskState] = {}              # task_id → task
        self._rng = random.Random(42)

    # ── seeding ──────────────────────────────────────────────────────────────

    def seed(self, data: dict[str, Any], rng_seed: int = 42) -> None:
        """Populate world from a scenario ``data`` dict. Clears previous state."""
        self._rng = random.Random(rng_seed)
        self.clock = SimulationClock(seed_seconds=data.get("clock_offset_seconds", 0))
        self.inventory.clear()
        self.equipment.clear()
        self.workers.clear()
        self.tasks.clear()

        for item_def in data.get("inventory", []):
            item = InventoryItem(**item_def)
            self.inventory[item.sku] = item

        for asset_def in data.get("equipment", []):
            asset_def = dict(asset_def)
            # Parse datetime strings
            for dt_field in ("next_pm_due", "last_maintenance"):
                raw = asset_def.get(dt_field)
                if isinstance(raw, str):
                    asset_def[dt_field] = datetime.fromisoformat(raw)
            asset = EquipmentAsset(**asset_def)
            self.equipment[asset.asset_id] = asset

        for worker_def in data.get("workers", []):
            w = WorkerState(**worker_def)
            self.workers[w.worker_id] = w

        for task_def in data.get("tasks", []):
            t = TaskState(**task_def)
            self.tasks[t.task_id] = t

    # ── snapshot / reset ─────────────────────────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        """Return a deep-copy snapshot of current world state."""
        return {
            "clock": self.clock.snapshot(),
            "inventory": copy.deepcopy(self.inventory),
            "equipment": copy.deepcopy(self.equipment),
            "workers": copy.deepcopy(self.workers),
            "tasks": copy.deepcopy(self.tasks),
        }

    def reset(self, snap: dict[str, Any]) -> None:
        """Restore world to a previously captured snapshot."""
        self.clock.restore(snap["clock"])
        self.inventory = copy.deepcopy(snap["inventory"])
        self.equipment = copy.deepcopy(snap["equipment"])
        self.workers = copy.deepcopy(snap["workers"])
        self.tasks = copy.deepcopy(snap["tasks"])

    # ── convenience queries ───────────────────────────────────────────────────

    def equipment_list(
        self,
        asset_id: str | None = None,
        equipment_type: str | None = None,
        zone: str | None = None,
        status_filter: str | None = None,
    ) -> list[EquipmentAsset]:
        assets = list(self.equipment.values())
        if asset_id:
            assets = [a for a in assets if a.asset_id == asset_id]
        if equipment_type:
            assets = [a for a in assets if a.equipment_type == equipment_type]
        if zone:
            assets = [a for a in assets if a.zone == zone]
        if status_filter:
            assets = [a for a in assets if a.status == status_filter]
        return assets

    def workers_list(
        self,
        zone: str | None = None,
        status_filter: str | None = None,
    ) -> list[WorkerState]:
        workers = list(self.workers.values())
        if zone:
            workers = [w for w in workers if w.zone == zone]
        if status_filter:
            workers = [w for w in workers if w.status == status_filter]
        return workers

    def tasks_list(
        self,
        zone: str | None = None,
        status_filter: str | None = None,
        task_type: str | None = None,
        worker_id: str | None = None,
    ) -> list[TaskState]:
        tasks = list(self.tasks.values())
        if zone:
            tasks = [t for t in tasks if t.zone == zone]
        if status_filter:
            tasks = [t for t in tasks if t.status == status_filter]
        if task_type:
            tasks = [t for t in tasks if t.task_type == task_type]
        if worker_id:
            tasks = [t for t in tasks if t.assigned_to == worker_id]
        return tasks

    def status_summary(self) -> dict[str, Any]:
        eq = list(self.equipment.values())
        wk = list(self.workers.values())
        tk = list(self.tasks.values())
        inv = list(self.inventory.values())
        return {
            "warehouse_id": self.WAREHOUSE_ID,
            "clock_iso": self.clock.now().isoformat(),
            "elapsed_seconds": self.clock.elapsed_seconds,
            "equipment": {
                "total": len(eq),
                "available": sum(1 for a in eq if a.status == "available"),
                "assigned": sum(1 for a in eq if a.status == "assigned"),
                "maintenance": sum(1 for a in eq if a.status == "maintenance"),
                "offline": sum(1 for a in eq if a.status == "offline"),
            },
            "workers": {
                "total": len(wk),
                "active": sum(1 for w in wk if w.status == "active"),
                "inactive": sum(1 for w in wk if w.status == "inactive"),
            },
            "tasks": {
                "total": len(tk),
                "pending": sum(1 for t in tk if t.status == "pending"),
                "in_progress": sum(1 for t in tk if t.status == "in_progress"),
                "completed": sum(1 for t in tk if t.status == "completed"),
            },
            "inventory": {
                "total_skus": len(inv),
                "low_stock": sum(1 for i in inv if i.is_low_stock),
            },
        }
