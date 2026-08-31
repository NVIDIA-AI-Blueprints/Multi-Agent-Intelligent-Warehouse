# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
ScenarioOverlay — runtime disruption overlay applied on top of an immutable DataPack.

Architecture:
    Immutable DataPack (base world)
            +
    ScenarioOverlay (disruption events)
            ↓
    ScenarioWorld (runtime view)

The DataPack / base graph is NEVER modified. All overlay effects are computed on demand.
No filesystem I/O — overlays are in-memory only (14E handles provider integration).
No dependency on maiw-agents, maiw-decision, maiw-execution, or maiw-state.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from .entities import EntityType
from .graph import CanonicalWarehouseGraph


# ── OverlayEventKind ───────────────────────────────────────────────────────────


class OverlayEventKind(str, Enum):
    WORKER_ABSENCE = "WORKER_ABSENCE"
    WORKER_RETURN = "WORKER_RETURN"
    EQUIPMENT_FAILURE = "EQUIPMENT_FAILURE"
    EQUIPMENT_RESTORED = "EQUIPMENT_RESTORED"
    INVENTORY_SHOCK = "INVENTORY_SHOCK"       # sudden quantity drop on an InventoryPosition
    WAVE_PRIORITY_BUMP = "WAVE_PRIORITY_BUMP" # escalate a wave to "active"
    CARRIER_CUTOFF_MISS = "CARRIER_CUTOFF_MISS"  # mark a cutoff as missed
    TASK_BLOCK = "TASK_BLOCK"                 # block a task
    TASK_UNBLOCK = "TASK_UNBLOCK"
    LABOR_SURGE = "LABOR_SURGE"               # add temporary worker availability (not a new Worker entity)


# ── OverlayEvent ──────────────────────────────────────────────────────────────


class OverlayEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str                           # unique within overlay
    kind: OverlayEventKind
    entity_id: str                          # primary target
    secondary_entity_id: str | None = None
    sim_time_offset_seconds: float          # seconds from scenario start (>= 0)
    payload: dict[str, str | int | float | bool | None] = {}
    label: str = ""                         # human-readable description for UI

    @field_validator("sim_time_offset_seconds")
    @classmethod
    def non_negative_offset(cls, v: float) -> float:
        if v < 0:
            raise ValueError("sim_time_offset_seconds must be >= 0")
        return v


# ── ScenarioOverlay ───────────────────────────────────────────────────────────


class ScenarioOverlay(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenario_id: str              # e.g. "labor-constraint-wave-risk"
    name: str                     # human display name
    description: str = ""
    dataset_id: str               # must match the DataPack's dataset_id
    events: list[OverlayEvent] = []
    tags: list[str] = []          # e.g. ["labor", "equipment", "risk"]

    @model_validator(mode="after")
    def unique_event_ids(self) -> "ScenarioOverlay":
        ids = [e.event_id for e in self.events]
        if len(ids) != len(set(ids)):
            raise ValueError("ScenarioOverlay.events must have unique event_ids")
        return self

    def events_before(self, sim_time_offset_seconds: float) -> list[OverlayEvent]:
        """Return events with offset < given time, sorted by offset ascending."""
        return sorted(
            [e for e in self.events if e.sim_time_offset_seconds < sim_time_offset_seconds],
            key=lambda e: e.sim_time_offset_seconds,
        )

    def events_at_or_before(self, sim_time_offset_seconds: float) -> list[OverlayEvent]:
        """Return events with offset <= given time, sorted by offset ascending."""
        return sorted(
            [e for e in self.events if e.sim_time_offset_seconds <= sim_time_offset_seconds],
            key=lambda e: e.sim_time_offset_seconds,
        )

    def events_by_kind(self, kind: OverlayEventKind) -> list[OverlayEvent]:
        """Return all events of the given kind."""
        return [e for e in self.events if e.kind == kind]

    def affected_entities(self) -> set[str]:
        """Return all entity IDs referenced by this overlay."""
        ids = {e.entity_id for e in self.events}
        ids.update(e.secondary_entity_id for e in self.events if e.secondary_entity_id)
        return ids


# ── ScenarioWorld ─────────────────────────────────────────────────────────────


class ScenarioWorld:
    """
    A read-only runtime view combining an immutable base graph with a scenario overlay.

    The base graph is NEVER modified. All overlay effects are computed on demand.
    """

    def __init__(
        self,
        base_graph: CanonicalWarehouseGraph,
        overlay: ScenarioOverlay,
    ) -> None:
        # Validate that the base graph has at least one Warehouse entity
        warehouse_entities = base_graph.entities_by_type(EntityType.WAREHOUSE)
        if not warehouse_entities:
            raise ValueError("Base graph has no Warehouse entity")

        self._base = base_graph
        self._overlay = overlay

        # Validate all overlay entity references exist in base graph
        unknown = overlay.affected_entities() - set(base_graph._entities.keys())
        if unknown:
            raise ValueError(
                f"ScenarioOverlay references unknown entity IDs: "
                f"{sorted(unknown)[:5]}{'...' if len(unknown) > 5 else ''}"
            )

    @property
    def base_graph(self) -> CanonicalWarehouseGraph:
        return self._base

    @property
    def overlay(self) -> ScenarioOverlay:
        return self._overlay

    # ── Overlay queries ────────────────────────────────────────────────────────

    def absent_workers(self, at_offset: float) -> list[str]:
        """Return worker entity IDs absent at the given sim_time_offset (seconds)."""
        absent: set[str] = set()
        for ev in self._overlay.events_at_or_before(at_offset):
            if ev.kind == OverlayEventKind.WORKER_ABSENCE:
                absent.add(ev.entity_id)
            elif ev.kind == OverlayEventKind.WORKER_RETURN:
                absent.discard(ev.entity_id)
        return list(absent)

    def failed_equipment(self, at_offset: float) -> list[str]:
        """Return equipment entity IDs in failed state at the given offset."""
        failed: set[str] = set()
        for ev in self._overlay.events_at_or_before(at_offset):
            if ev.kind == OverlayEventKind.EQUIPMENT_FAILURE:
                failed.add(ev.entity_id)
            elif ev.kind == OverlayEventKind.EQUIPMENT_RESTORED:
                failed.discard(ev.entity_id)
        return list(failed)

    def blocked_tasks(self, at_offset: float) -> list[str]:
        """Return task entity IDs in blocked state at the given offset."""
        blocked: set[str] = set()
        for ev in self._overlay.events_at_or_before(at_offset):
            if ev.kind == OverlayEventKind.TASK_BLOCK:
                blocked.add(ev.entity_id)
            elif ev.kind == OverlayEventKind.TASK_UNBLOCK:
                blocked.discard(ev.entity_id)
        return list(blocked)

    def inventory_adjustments(self, at_offset: float) -> dict[str, int]:
        """
        Return dict of {inventory_position_id: adjusted_quantity_available}
        for all INVENTORY_SHOCK events at or before the given offset.
        Last event per entity wins.
        """
        adjustments: dict[str, int] = {}
        for ev in self._overlay.events_at_or_before(at_offset):
            if ev.kind == OverlayEventKind.INVENTORY_SHOCK:
                qty = ev.payload.get("quantity_available")
                if qty is not None:
                    adjustments[ev.entity_id] = int(qty)
        return adjustments

    def missed_cutoffs(self, at_offset: float) -> list[str]:
        """Return carrier cutoff entity IDs marked missed at or before offset."""
        return [
            ev.entity_id for ev in self._overlay.events_at_or_before(at_offset)
            if ev.kind == OverlayEventKind.CARRIER_CUTOFF_MISS
        ]

    def active_disruptions(self, at_offset: float) -> dict[str, list[str]]:
        """
        Summary of all active disruptions at offset:
        {
          "absent_workers": [...],
          "failed_equipment": [...],
          "blocked_tasks": [...],
          "missed_cutoffs": [...],
        }
        """
        return {
            "absent_workers":   self.absent_workers(at_offset),
            "failed_equipment": self.failed_equipment(at_offset),
            "blocked_tasks":    self.blocked_tasks(at_offset),
            "missed_cutoffs":   self.missed_cutoffs(at_offset),
        }

    def disruption_severity(self, at_offset: float) -> str:
        """
        Classify overall disruption severity at offset:
        - "CRITICAL": any missed cutoff OR > 20% workers absent OR > 30% equipment failed
        - "HIGH": any equipment failure OR > 10% workers absent
        - "MODERATE": any worker absence OR any blocked task
        - "NOMINAL": no active disruptions
        """
        absent = self.absent_workers(at_offset)
        failed = self.failed_equipment(at_offset)
        blocked = self.blocked_tasks(at_offset)
        missed = self.missed_cutoffs(at_offset)

        total_workers = len(self._base.entities_by_type(EntityType.WORKER))
        total_equipment = len(self._base.entities_by_type(EntityType.EQUIPMENT))

        if missed:
            return "CRITICAL"
        if total_workers > 0 and len(absent) / total_workers > 0.20:
            return "CRITICAL"
        if total_equipment > 0 and len(failed) / total_equipment > 0.30:
            return "CRITICAL"
        if failed:
            return "HIGH"
        if total_workers > 0 and len(absent) / total_workers > 0.10:
            return "HIGH"
        if absent or blocked:
            return "MODERATE"
        return "NOMINAL"


# ── ScenarioOverlayBuilder ────────────────────────────────────────────────────


class ScenarioOverlayBuilder:
    """
    Fluent builder for constructing ScenarioOverlay instances.
    Not frozen — accumulates events, then call build() to produce frozen ScenarioOverlay.
    """

    def __init__(
        self,
        scenario_id: str,
        name: str,
        dataset_id: str,
        description: str = "",
    ) -> None:
        self._scenario_id = scenario_id
        self._name = name
        self._dataset_id = dataset_id
        self._description = description
        self._events: list[OverlayEvent] = []
        self._tags: list[str] = []
        self._counter = 0

    def _next_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{self._scenario_id}-{prefix}-{self._counter:04d}"

    def worker_absence(self, worker_id: str, at: float, label: str = "") -> "ScenarioOverlayBuilder":
        self._events.append(OverlayEvent(
            event_id=self._next_id("abs"),
            kind=OverlayEventKind.WORKER_ABSENCE,
            entity_id=worker_id,
            sim_time_offset_seconds=at,
            label=label or f"Worker {worker_id} absent",
        ))
        return self

    def worker_return(self, worker_id: str, at: float, label: str = "") -> "ScenarioOverlayBuilder":
        self._events.append(OverlayEvent(
            event_id=self._next_id("ret"),
            kind=OverlayEventKind.WORKER_RETURN,
            entity_id=worker_id,
            sim_time_offset_seconds=at,
            label=label or f"Worker {worker_id} returns",
        ))
        return self

    def equipment_failure(self, equipment_id: str, at: float, label: str = "") -> "ScenarioOverlayBuilder":
        self._events.append(OverlayEvent(
            event_id=self._next_id("fail"),
            kind=OverlayEventKind.EQUIPMENT_FAILURE,
            entity_id=equipment_id,
            sim_time_offset_seconds=at,
            label=label or f"Equipment {equipment_id} failure",
        ))
        return self

    def equipment_restored(self, equipment_id: str, at: float, label: str = "") -> "ScenarioOverlayBuilder":
        self._events.append(OverlayEvent(
            event_id=self._next_id("rst"),
            kind=OverlayEventKind.EQUIPMENT_RESTORED,
            entity_id=equipment_id,
            sim_time_offset_seconds=at,
            label=label or f"Equipment {equipment_id} restored",
        ))
        return self

    def inventory_shock(
        self,
        invpos_id: str,
        new_quantity: int,
        at: float,
        label: str = "",
    ) -> "ScenarioOverlayBuilder":
        self._events.append(OverlayEvent(
            event_id=self._next_id("inv"),
            kind=OverlayEventKind.INVENTORY_SHOCK,
            entity_id=invpos_id,
            sim_time_offset_seconds=at,
            payload={"quantity_available": new_quantity},
            label=label or f"Inventory shock on {invpos_id}: qty={new_quantity}",
        ))
        return self

    def task_block(self, task_id: str, at: float, reason: str = "") -> "ScenarioOverlayBuilder":
        self._events.append(OverlayEvent(
            event_id=self._next_id("blk"),
            kind=OverlayEventKind.TASK_BLOCK,
            entity_id=task_id,
            sim_time_offset_seconds=at,
            payload={"reason": reason},
            label=f"Task {task_id} blocked" + (f": {reason}" if reason else ""),
        ))
        return self

    def task_unblock(self, task_id: str, at: float) -> "ScenarioOverlayBuilder":
        self._events.append(OverlayEvent(
            event_id=self._next_id("unblk"),
            kind=OverlayEventKind.TASK_UNBLOCK,
            entity_id=task_id,
            sim_time_offset_seconds=at,
        ))
        return self

    def carrier_cutoff_miss(self, cutoff_id: str, at: float, label: str = "") -> "ScenarioOverlayBuilder":
        self._events.append(OverlayEvent(
            event_id=self._next_id("cut"),
            kind=OverlayEventKind.CARRIER_CUTOFF_MISS,
            entity_id=cutoff_id,
            sim_time_offset_seconds=at,
            label=label or f"Carrier cutoff {cutoff_id} missed",
        ))
        return self

    def tag(self, *tags: str) -> "ScenarioOverlayBuilder":
        self._tags.extend(tags)
        return self

    def build(self) -> ScenarioOverlay:
        return ScenarioOverlay(
            scenario_id=self._scenario_id,
            name=self._name,
            description=self._description,
            dataset_id=self._dataset_id,
            events=list(self._events),
            tags=list(self._tags),
        )


# ── Canonical scenario presets ─────────────────────────────────────────────────


def labor_constraint_scenario(graph: CanonicalWarehouseGraph) -> ScenarioOverlay:
    """
    Labor constraint + wave risk scenario — mirrors the existing MAIW demo scenario.
    Marks ~15% of workers absent. Bumps cutoff risk at t=1800s.
    """
    workers = sorted(graph.entities_by_type(EntityType.WORKER), key=lambda w: w.id)
    absent_count = max(1, int(len(workers) * 0.15))
    absent_workers = workers[:absent_count]

    cutoffs = sorted(graph.entities_by_type(EntityType.CARRIER_CUTOFF), key=lambda c: c.id)
    tasks = sorted(graph.entities_by_type(EntityType.TASK), key=lambda t: t.id)
    blocked_tasks = tasks[:min(3, len(tasks))]

    warehouse_entities = graph.entities_by_type(EntityType.WAREHOUSE)
    dataset_id = warehouse_entities[0].id if warehouse_entities else "unknown"

    builder = (
        ScenarioOverlayBuilder(
            scenario_id="labor-constraint-wave-risk",
            name="Labor Constraint + Wave Risk",
            description="Unexpected absences reduce pick capacity; carrier cutoff at risk.",
            dataset_id=dataset_id,
        )
        .tag("labor", "wave", "risk")
    )

    for i, worker in enumerate(absent_workers):
        builder.worker_absence(
            worker.id,
            at=float(i * 30),
            label=f"Shift shortage: worker {worker.id} absent",
        )

    for task in blocked_tasks:
        builder.task_block(task.id, at=300.0, reason="understaffed")

    if cutoffs:
        builder.carrier_cutoff_miss(
            cutoffs[0].id,
            at=1800.0,
            label="FedEx Priority cutoff at risk",
        )

    return builder.build()


def equipment_failure_scenario(graph: CanonicalWarehouseGraph) -> ScenarioOverlay:
    """
    AGV fleet failure — one or more AGVs fail mid-shift, restored 30 minutes later.
    """
    from .entities import EquipmentType

    equipment = sorted(graph.entities_by_type(EntityType.EQUIPMENT), key=lambda e: e.id)
    agvs = [
        e for e in equipment
        if hasattr(e, "equipment_type") and e.equipment_type == EquipmentType.AGV
    ]
    target_agvs = agvs[:min(2, len(agvs))] or equipment[:1]

    warehouse_entities = graph.entities_by_type(EntityType.WAREHOUSE)
    dataset_id = warehouse_entities[0].id if warehouse_entities else "unknown"

    builder = (
        ScenarioOverlayBuilder(
            scenario_id="agv-fleet-failure",
            name="AGV Fleet Failure",
            description="AGV units fail mid-shift; pick throughput degraded until restored.",
            dataset_id=dataset_id,
        )
        .tag("equipment", "agv", "risk")
    )

    for agv in target_agvs:
        builder.equipment_failure(agv.id, at=0.0, label=f"AGV {agv.id} offline")
        builder.equipment_restored(agv.id, at=1800.0, label=f"AGV {agv.id} restored")

    return builder.build()
