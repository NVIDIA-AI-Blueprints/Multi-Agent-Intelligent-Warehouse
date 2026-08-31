# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
projections.py — translate ScenarioWorld → domain-specific runtime shapes.

The projection builder owns all graph → domain mapping.
Providers consume projections, not raw graph entities.

Three layers — kept EXPLICIT and SEPARATE:
  DataPack  (WarehouseDataPack on disk)   — immutable, reproducible definition
  ScenarioWorld (base_graph + overlay)    — immutable, baseline + disruptions
  DemoWarehouseWorld (runtime)            — mutable live state after MAIW actions

DataPack checksum is never changed by any demo mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .scenario import ScenarioWorld
from .entities import EntityType
from .edges import RelationshipType


# ── Inventory projection ───────────────────────────────────────────────────────

@dataclass
class InventoryItemProjection:
    sku_id: str
    sku_name: str
    category: str
    location_id: str
    location_code: str
    zone_id: str
    quantity_available: int
    quantity_reserved: int
    reorder_point: int
    is_low_stock: bool           # quantity_available < reorder_point
    unit_of_measure: str


@dataclass
class InventoryProjection:
    items: list[InventoryItemProjection] = field(default_factory=list)
    total_sku_count: int = 0
    low_stock_count: int = 0
    # at_offset is the sim_time_offset used to apply inventory shock events
    at_offset: float = 0.0


# ── Labor projection ───────────────────────────────────────────────────────────

@dataclass
class WorkerProjection:
    worker_id: str
    username: str
    full_name: str
    role: str
    skills: list[str]
    shift_id: str | None
    shift_name: str | None
    is_absent: bool              # from overlay WORKER_ABSENCE events
    assigned_task_ids: list[str] = field(default_factory=list)


@dataclass
class LaborProjection:
    workers: list[WorkerProjection] = field(default_factory=list)
    total_count: int = 0
    available_count: int = 0    # not absent
    absent_count: int = 0
    at_offset: float = 0.0


# ── Equipment projection ───────────────────────────────────────────────────────

@dataclass
class EquipmentItemProjection:
    equipment_id: str
    equipment_type: str         # "agv" | "forklift" | "conveyor"
    model: str
    zone_id: str | None
    is_failed: bool             # from overlay EQUIPMENT_FAILURE events
    supported_task_ids: list[str] = field(default_factory=list)


@dataclass
class EquipmentProjection:
    items: list[EquipmentItemProjection] = field(default_factory=list)
    total_count: int = 0
    failed_count: int = 0
    available_count: int = 0
    at_offset: float = 0.0


# ── Wave projection ────────────────────────────────────────────────────────────

@dataclass
class TaskProjection:
    task_id: str
    task_type: str               # "PICK" | "PACK" | "PUTAWAY" etc.
    zone_id: str | None
    status: str                  # TaskStatus value
    priority: str
    is_blocked: bool             # from overlay TASK_BLOCK events
    assigned_worker_id: str | None
    required_sku_id: str | None


@dataclass
class WaveItemProjection:
    wave_id: str
    wave_number: int
    strategy: str
    status: str
    tasks: list[TaskProjection] = field(default_factory=list)
    fulfills_order_ids: list[str] = field(default_factory=list)
    carrier_cutoff_ids: list[str] = field(default_factory=list)
    missed_cutoff_ids: list[str] = field(default_factory=list)


@dataclass
class WaveProjection:
    waves: list[WaveItemProjection] = field(default_factory=list)
    total_task_count: int = 0
    blocked_task_count: int = 0
    at_offset: float = 0.0


# ── Builder ────────────────────────────────────────────────────────────────────

class WarehouseProjectionBuilder:
    """
    Translates ScenarioWorld → domain projections at a given sim_time_offset.

    All graph → domain mapping is centralized here.
    No provider interprets graph edges directly.
    """

    def __init__(self, world: ScenarioWorld, at_offset: float = 0.0) -> None:
        self._world = world
        self._at_offset = at_offset
        self._graph = world.base_graph

    def inventory(self) -> InventoryProjection:
        inv_adjustments = self._world.inventory_adjustments(self._at_offset)
        items: list[InventoryItemProjection] = []
        for inv_pos in self._graph.entities_by_type(EntityType.INVENTORY_POSITION):
            # Resolve location via STORED_AT edge
            loc_edges = self._graph.outgoing_edges(inv_pos.id, RelationshipType.STORED_AT)
            location = self._graph.get_entity(loc_edges[0].target_id) if loc_edges else None
            # Resolve SKU by sku_id field
            sku = self._graph.get_entity(inv_pos.sku_id)  # type: ignore[attr-defined]
            if sku is None:
                continue
            # Apply scenario inventory shock (last event per entity wins)
            qty_available = inv_adjustments.get(inv_pos.id, inv_pos.quantity_available)  # type: ignore[attr-defined]
            items.append(InventoryItemProjection(
                sku_id=sku.id,
                sku_name=getattr(sku, "name", sku.id),
                category=getattr(sku, "category", ""),
                location_id=location.id if location else "",
                location_code=getattr(location, "location_code", "") if location else "",
                zone_id=getattr(location, "zone_id", "") if location else "",
                quantity_available=qty_available,
                quantity_reserved=getattr(inv_pos, "quantity_reserved", 0),  # type: ignore[attr-defined]
                reorder_point=getattr(inv_pos, "reorder_point", 0),  # type: ignore[attr-defined]
                is_low_stock=qty_available < getattr(inv_pos, "reorder_point", 0),  # type: ignore[attr-defined]
                unit_of_measure=getattr(sku, "unit_of_measure", "EA"),
            ))
        low_stock = sum(1 for i in items if i.is_low_stock)
        return InventoryProjection(
            items=items,
            total_sku_count=len(items),
            low_stock_count=low_stock,
            at_offset=self._at_offset,
        )

    def labor(self) -> LaborProjection:
        absent_ids = set(self._world.absent_workers(self._at_offset))
        workers: list[WorkerProjection] = []
        for worker in self._graph.entities_by_type(EntityType.WORKER):
            # Resolve shift via MEMBER_OF edge
            shift_edges = self._graph.outgoing_edges(worker.id, RelationshipType.MEMBER_OF)
            shift = self._graph.get_entity(shift_edges[0].target_id) if shift_edges else None
            # Resolve active task assignments — no temporal filter for initial projection
            assign_edges = self._graph.outgoing_edges(worker.id, RelationshipType.ASSIGNED_TO)
            assigned_task_ids = [e.target_id for e in assign_edges]
            workers.append(WorkerProjection(
                worker_id=worker.id,
                username=getattr(worker, "username", worker.id),
                full_name=getattr(worker, "full_name", worker.id),
                role=getattr(worker, "role", "operator"),
                skills=list(getattr(worker, "skills", [])),
                shift_id=shift.id if shift else None,
                shift_name=getattr(shift, "shift_name", None) if shift else None,
                is_absent=worker.id in absent_ids,
                assigned_task_ids=assigned_task_ids,
            ))
        available = [w for w in workers if not w.is_absent]
        return LaborProjection(
            workers=workers,
            total_count=len(workers),
            available_count=len(available),
            absent_count=len(workers) - len(available),
            at_offset=self._at_offset,
        )

    def equipment(self) -> EquipmentProjection:
        failed_ids = set(self._world.failed_equipment(self._at_offset))
        items: list[EquipmentItemProjection] = []
        for eq in self._graph.entities_by_type(EntityType.EQUIPMENT):
            # No temporal filter for initial projection
            support_edges = self._graph.outgoing_edges(eq.id, RelationshipType.SUPPORTS)
            items.append(EquipmentItemProjection(
                equipment_id=eq.id,
                equipment_type=getattr(eq, "equipment_type", None).value  # type: ignore[union-attr]
                    if hasattr(getattr(eq, "equipment_type", None), "value")
                    else str(getattr(eq, "equipment_type", "agv")),
                model=getattr(eq, "model", ""),
                zone_id=getattr(eq, "zone_id", None),
                is_failed=eq.id in failed_ids,
                supported_task_ids=[e.target_id for e in support_edges],
            ))
        failed = [i for i in items if i.is_failed]
        return EquipmentProjection(
            items=items,
            total_count=len(items),
            failed_count=len(failed),
            available_count=len(items) - len(failed),
            at_offset=self._at_offset,
        )

    def waves(self) -> WaveProjection:
        blocked_ids = set(self._world.blocked_tasks(self._at_offset))
        missed_cutoff_ids = set(self._world.missed_cutoffs(self._at_offset))

        wave_items: list[WaveItemProjection] = []
        total_tasks = 0
        blocked_tasks_count = 0

        for wave in self._graph.entities_by_type(EntityType.WAVE):
            # Tasks in this wave — BELONGS_TO is Task→Wave so use incoming edges to wave
            task_edges = self._graph.incoming_edges(wave.id, RelationshipType.BELONGS_TO)
            tasks: list[TaskProjection] = []
            for e in task_edges:
                task = self._graph.get_entity(e.source_id)
                if task is None:
                    continue
                # Worker assigned to task — ASSIGNED_TO is Worker→Task (incoming to task)
                assign_edges = self._graph.incoming_edges(task.id, RelationshipType.ASSIGNED_TO)
                assigned_worker = assign_edges[0].source_id if assign_edges else None
                # SKU required by task — REQUIRES is Task→SKU (outgoing from task)
                req_edges = self._graph.outgoing_edges(task.id, RelationshipType.REQUIRES)
                required_sku = req_edges[0].target_id if req_edges else None
                is_blocked = task.id in blocked_ids
                tasks.append(TaskProjection(
                    task_id=task.id,
                    task_type=getattr(task, "task_type", None).value  # type: ignore[union-attr]
                        if hasattr(getattr(task, "task_type", None), "value")
                        else str(getattr(task, "task_type", "PICK")),
                    zone_id=getattr(task, "zone_id", None),
                    status=getattr(task, "status", None).value  # type: ignore[union-attr]
                        if hasattr(getattr(task, "status", None), "value")
                        else str(getattr(task, "status", "PENDING")),
                    priority=getattr(task, "priority", "normal"),
                    is_blocked=is_blocked,
                    assigned_worker_id=assigned_worker,
                    required_sku_id=required_sku,
                ))
                total_tasks += 1
                if is_blocked:
                    blocked_tasks_count += 1

            # Orders fulfilled by wave — FULFILLS is Wave→Order (outgoing from wave)
            fulfills_edges = self._graph.outgoing_edges(wave.id, RelationshipType.FULFILLS)
            order_ids = [e.target_id for e in fulfills_edges]

            # Carrier cutoffs — CONSTRAINED_BY is Wave→CarrierCutoff (outgoing from wave)
            cutoff_edges = self._graph.outgoing_edges(wave.id, RelationshipType.CONSTRAINED_BY)
            cutoff_ids = [e.target_id for e in cutoff_edges]
            missed = [c for c in cutoff_ids if c in missed_cutoff_ids]

            wave_items.append(WaveItemProjection(
                wave_id=wave.id,
                wave_number=getattr(wave, "wave_number", 0),
                strategy=getattr(wave, "strategy", "fifo"),
                status=getattr(wave, "status", "planning"),
                tasks=tasks,
                fulfills_order_ids=order_ids,
                carrier_cutoff_ids=cutoff_ids,
                missed_cutoff_ids=missed,
            ))

        return WaveProjection(
            waves=wave_items,
            total_task_count=total_tasks,
            blocked_task_count=blocked_tasks_count,
            at_offset=self._at_offset,
        )

    def build_all(self) -> dict[str, Any]:
        return {
            "inventory": self.inventory(),
            "labor": self.labor(),
            "equipment": self.equipment(),
            "waves": self.waves(),
        }
