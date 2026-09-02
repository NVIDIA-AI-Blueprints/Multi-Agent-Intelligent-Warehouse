# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
WarehouseWorldGenerator — deterministic CanonicalWarehouseGraph generator.

Input:  WarehouseWorldConfig
Output: GenerationResult (CanonicalWarehouseGraph + GenerationReport)

Determinism contract: same config + same seed → identical graph topology every time.
Changing seed produces a materially different but always-valid graph.
"""

from __future__ import annotations

import random
import time
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict

from .config import WarehouseWorldConfig
from .edges import RelationshipType, WarehouseEdge
from .entities import (
    CarrierCutoff,
    EntityType,
    Equipment,
    EquipmentType,
    InventoryPosition,
    Location,
    Order,
    SKU,
    Shift,
    Task,
    TaskStatus,
    TaskType,
    Wave,
    Warehouse,
    Worker,
    Zone,
)
from .events import OperationalEvent, OperationalEventType
from .graph import CanonicalWarehouseGraph
from .validation import ValidationReport

# ── Domain offsets for seed derivation ────────────────────────────────────────
DOMAIN_OFFSET_FACILITY = 1
DOMAIN_OFFSET_INVENTORY = 2
DOMAIN_OFFSET_LABOR = 3
DOMAIN_OFFSET_EQUIPMENT = 4
DOMAIN_OFFSET_ORDERS = 5
DOMAIN_OFFSET_WAVES = 6
DOMAIN_OFFSET_HISTORY = 7


def _domain_rng(seed: int, domain_offset: int) -> random.Random:
    """
    Derive a domain-specific Random instance from the root seed.

    Uses a fixed numeric XOR with a Fibonacci-hash constant to ensure
    different domains produce independent RNG streams without string hashing.
    """
    return random.Random(seed ^ (domain_offset * 0x9E3779B9))


# ── Report models ──────────────────────────────────────────────────────────────

class DomainCounts(BaseModel):
    warehouses: int = 0
    zones: int = 0
    locations: int = 0
    workers: int = 0
    shifts: int = 0
    equipment: int = 0
    skus: int = 0
    inventory_positions: int = 0
    orders: int = 0
    waves: int = 0
    tasks: int = 0
    shipments: int = 0
    carrier_cutoffs: int = 0


class GenerationReport(BaseModel):
    warehouse_id: str
    dataset_id: str
    seed: int
    generated_at: datetime          # caller stamps this AFTER generator returns
    duration_ms: float
    entity_counts: DomainCounts
    edge_count: int
    validation_result: ValidationReport  # run validate() on the graph before returning
    warnings: list[str] = []        # non-fatal generation notes


class GenerationResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    graph: CanonicalWarehouseGraph
    report: GenerationReport


# ── Generator ──────────────────────────────────────────────────────────────────

class WarehouseWorldGenerator:
    """
    Deterministic generator that produces a CanonicalWarehouseGraph from a
    WarehouseWorldConfig.

    Thread safety: each call to generate() is independent. The generator holds
    no mutable state between calls — the config is read-only.
    """

    def __init__(self, config: WarehouseWorldConfig) -> None:
        self._config = config

    def generate(self) -> GenerationResult:
        t0 = time.monotonic()
        g = CanonicalWarehouseGraph()
        warnings: list[str] = []

        # 1. Facility domain
        warehouse, zones, locations = self._generate_facility(g)
        # 2. Labor domain
        workers, shifts = self._generate_labor(g, warehouse)
        # 3. Equipment domain
        equipment_list = self._generate_equipment(g, warehouse, zones)
        # 4. Inventory domain
        skus, inv_positions = self._generate_inventory(g, warehouse, locations)
        # 5. Orders domain
        orders, carrier_cutoffs = self._generate_orders(g, warehouse)
        # 6. Waves domain (depends on orders, tasks, workers, equipment, skus)
        waves, tasks = self._generate_waves(
            g, orders, workers, equipment_list, skus, zones, warnings
        )
        # 7. History events
        self._generate_history(g, workers, equipment_list, tasks, skus, warnings)

        duration_ms = (time.monotonic() - t0) * 1000.0
        report = GenerationReport(
            warehouse_id=self._config.warehouse_id,
            dataset_id=self._config.dataset_id,
            seed=self._config.seed,
            generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),  # caller should stamp this
            duration_ms=duration_ms,
            entity_counts=DomainCounts(
                warehouses=1,
                zones=len(zones),
                locations=len(locations),
                workers=len(workers),
                shifts=len(shifts),
                equipment=len(equipment_list),
                skus=len(skus),
                inventory_positions=len(inv_positions),
                orders=len(orders),
                waves=len(waves),
                tasks=len(tasks),
                carrier_cutoffs=len(carrier_cutoffs),
            ),
            edge_count=g.edge_count,
            validation_result=g.validate(),
            warnings=warnings,
        )
        return GenerationResult(graph=g, report=report)

    # ── Domain generators ──────────────────────────────────────────────────────

    def _generate_facility(
        self, g: CanonicalWarehouseGraph
    ) -> tuple[Warehouse, list[Zone], list[Location]]:
        rng = _domain_rng(self._config.seed, DOMAIN_OFFSET_FACILITY)
        c = self._config.facility
        cfg = self._config

        wh = Warehouse(
            id=cfg.warehouse_id,
            name=f"{cfg.warehouse_id} Distribution Center",
            timezone="UTC",
        )
        g.add_entity(wh)

        zone_types = ["picking", "packing", "receiving", "storage", "dock"]
        zones: list[Zone] = []
        for i in range(c.zone_count):
            zone_type = zone_types[i % len(zone_types)]
            zone_code = (
                f"{chr(65 + i)}{(i // 26) + 1}" if i < 26 else f"Z{i:03d}"
            )
            z = Zone(
                id=f"zone-{zone_code}",
                warehouse_id=cfg.warehouse_id,
                zone_code=zone_code,
                zone_type=zone_type,
            )
            g.add_entity(z)
            g.add_edge(
                WarehouseEdge(
                    id=f"e-wh-{z.id}",
                    source_id=cfg.warehouse_id,
                    target_id=z.id,
                    relationship_type=RelationshipType.CONTAINS,
                )
            )
            zones.append(z)

        locations: list[Location] = []
        locs_per_zone = max(1, c.location_count // c.zone_count)
        remainder = c.location_count - (locs_per_zone * c.zone_count)
        loc_idx = 0
        for zi, zone in enumerate(zones):
            count = locs_per_zone + (1 if zi < remainder else 0)
            for j in range(count):
                aisle = chr(65 + (loc_idx % 26))
                bay = f"{(loc_idx // 26) % 100 + 1:02d}"
                level_choices = ["01", "02", "03", "04"]
                level = level_choices[rng.randint(0, len(level_choices) - 1)]
                loc_code = f"{aisle}-{bay}-{level}"
                loc = Location(
                    id=f"loc-{loc_idx:06d}",
                    zone_id=zone.id,
                    aisle=aisle,
                    bay=bay,
                    level=level,
                    location_code=loc_code,
                )
                g.add_entity(loc)
                g.add_edge(
                    WarehouseEdge(
                        id=f"e-{zone.id}-{loc.id}",
                        source_id=zone.id,
                        target_id=loc.id,
                        relationship_type=RelationshipType.CONTAINS,
                    )
                )
                locations.append(loc)
                loc_idx += 1

        return wh, zones, locations

    def _generate_labor(
        self, g: CanonicalWarehouseGraph, warehouse: Warehouse
    ) -> tuple[list[Worker], list[Shift]]:
        rng = _domain_rng(self._config.seed, DOMAIN_OFFSET_LABOR)
        c = self._config.labor

        shift_names = ["day", "evening", "night"]
        shift_hours = [(6, 14), (14, 22), (22, 6)]  # (start, end)
        shifts: list[Shift] = []
        for i in range(min(c.shift_count, 3)):
            name, (start, end) = shift_names[i], shift_hours[i]
            shift = Shift(
                id=f"shift-{name}", shift_name=name, start_hour=start, end_hour=end
            )
            g.add_entity(shift)
            shifts.append(shift)

        workers: list[Worker] = []
        for shift_idx, shift in enumerate(shifts):
            for w_idx in range(c.workers_per_shift):
                global_idx = shift_idx * c.workers_per_shift + w_idx
                skill_count = rng.randint(1, len(c.skills))
                skills = rng.sample(c.skills, skill_count)
                role = "supervisor" if w_idx == 0 else "operator"
                worker = Worker(
                    id=f"worker-{global_idx:06d}",
                    username=f"w{global_idx:06d}",
                    full_name=f"Worker {global_idx:06d}",
                    role=role,
                    skills=skills,
                )
                g.add_entity(worker)
                g.add_edge(
                    WarehouseEdge(
                        id=f"e-wh-{worker.id}",
                        source_id=warehouse.id,
                        target_id=worker.id,
                        relationship_type=RelationshipType.EMPLOYS,
                    )
                )
                g.add_edge(
                    WarehouseEdge(
                        id=f"e-{worker.id}-{shift.id}",
                        source_id=worker.id,
                        target_id=shift.id,
                        relationship_type=RelationshipType.MEMBER_OF,
                    )
                )
                workers.append(worker)

        return workers, shifts

    def _generate_equipment(
        self,
        g: CanonicalWarehouseGraph,
        warehouse: Warehouse,
        zones: list[Zone],
    ) -> list[Equipment]:
        rng = _domain_rng(self._config.seed, DOMAIN_OFFSET_EQUIPMENT)
        c = self._config.equipment

        equipment_list: list[Equipment] = []
        idx = 0
        specs = [
            (c.agv_count, EquipmentType.AGV, "agv", "Locus Origin"),
            (c.forklift_count, EquipmentType.FORKLIFT, "forklift", "Crown FC 5200"),
            (c.conveyor_count, EquipmentType.CONVEYOR, "conveyor", "Hytrol Series E"),
        ]
        for count, eq_type, prefix, model in specs:
            for i in range(count):
                zone = zones[idx % len(zones)]
                eq = Equipment(
                    id=f"{prefix}-{i:03d}",
                    equipment_type=eq_type,
                    model=model,
                    zone_id=zone.id,
                )
                g.add_entity(eq)
                g.add_edge(
                    WarehouseEdge(
                        id=f"e-wh-{eq.id}",
                        source_id=warehouse.id,
                        target_id=eq.id,
                        relationship_type=RelationshipType.OPERATES,
                    )
                )
                equipment_list.append(eq)
                idx += 1

        return equipment_list

    def _generate_inventory(
        self,
        g: CanonicalWarehouseGraph,
        warehouse: Warehouse,
        locations: list[Location],
    ) -> tuple[list[SKU], list[InventoryPosition]]:
        rng = _domain_rng(self._config.seed, DOMAIN_OFFSET_INVENTORY)
        c = self._config.inventory

        categories = [
            "snacks", "beverages", "electronics", "apparel", "home_goods",
            "sporting_goods", "toys", "automotive", "health", "grocery",
        ]

        skus: list[SKU] = []
        for i in range(c.sku_count):
            category = categories[i % len(categories)]
            sku = SKU(
                id=f"sku-{i:06d}",
                name=f"Product {i:06d}",
                category=category,
                unit_of_measure="EA",
            )
            g.add_entity(sku)
            g.add_edge(
                WarehouseEdge(
                    id=f"e-wh-{sku.id}",
                    source_id=warehouse.id,
                    target_id=sku.id,
                    relationship_type=RelationshipType.STORES,
                )
            )
            skus.append(sku)

        inv_positions: list[InventoryPosition] = []
        low_stock_count = int(c.sku_count * c.low_stock_pct)
        low_stock_indices = set(
            rng.sample(range(c.sku_count), min(low_stock_count, c.sku_count))
        )

        for i, sku in enumerate(skus):
            location = locations[i % len(locations)]
            reorder_point = rng.randint(200, 800)
            if i in low_stock_indices:
                quantity_available = rng.randint(0, reorder_point - 1)
            else:
                quantity_available = rng.randint(reorder_point, reorder_point * 5)
            quantity_reserved = rng.randint(0, min(50, quantity_available))
            inv = InventoryPosition(
                id=f"invpos-{i:06d}",
                sku_id=sku.id,
                location_id=location.id,
                quantity_available=quantity_available,
                quantity_reserved=quantity_reserved,
                reorder_point=reorder_point,
            )
            g.add_entity(inv)
            g.add_edge(
                WarehouseEdge(
                    id=f"e-{inv.id}-{location.id}",
                    source_id=inv.id,
                    target_id=location.id,
                    relationship_type=RelationshipType.STORED_AT,
                )
            )
            inv_positions.append(inv)

        return skus, inv_positions

    def _generate_orders(
        self, g: CanonicalWarehouseGraph, warehouse: Warehouse
    ) -> tuple[list[Order], list[CarrierCutoff]]:
        rng = _domain_rng(self._config.seed, DOMAIN_OFFSET_ORDERS)
        c = self._config.orders

        priorities = ["critical", "high", "normal", "low"]
        priority_weights = [5, 15, 70, 10]

        orders: list[Order] = []
        for i in range(c.daily_order_count):
            priority = rng.choices(priorities, weights=priority_weights)[0]
            order = Order(
                id=f"order-{i:06d}",
                order_reference=f"ORD-{i:06d}",
                customer_id=f"cust-{rng.randint(1, 1000):05d}",
                priority=priority,
            )
            g.add_entity(order)
            orders.append(order)

        # Carrier cutoffs (one per dock door)
        carriers = [
            "FedEx Priority", "UPS Ground", "USPS Priority", "DHL Express",
            "OnTrac", "LSO", "Spee-Dee", "LaserShip",
        ]
        cutoff_hours = [10, 12, 13, 14, 15, 16, 17, 18]
        carrier_cutoffs: list[CarrierCutoff] = []
        for dock_idx in range(self._config.facility.dock_door_count):
            carrier = carriers[dock_idx % len(carriers)]
            cutoff_hour = cutoff_hours[dock_idx % len(cutoff_hours)]
            cutoff = CarrierCutoff(
                id=f"cutoff-{dock_idx:03d}",
                carrier=carrier,
                cutoff_time=datetime(2026, 1, 1, cutoff_hour, 0, 0, tzinfo=timezone.utc),
            )
            g.add_entity(cutoff)
            carrier_cutoffs.append(cutoff)

        return orders, carrier_cutoffs

    def _generate_waves(
        self,
        g: CanonicalWarehouseGraph,
        orders: list[Order],
        workers: list[Worker],
        equipment_list: list[Equipment],
        skus: list[SKU],
        zones: list[Zone],
        warnings: list[str],
    ) -> tuple[list[Wave], list[Task]]:
        rng = _domain_rng(self._config.seed, DOMAIN_OFFSET_WAVES)
        wc = self._config.waves

        EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)

        waves: list[Wave] = []
        statuses = ["active", "planning", "planning"]
        wave_start = getattr(wc, "wave_number_start", 1)
        for wi in range(wc.active_wave_count):
            wave_num = wave_start + wi
            wave = Wave(
                id=f"wave-{wave_num:03d}",
                wave_number=wave_num,
                strategy=wc.strategy,
                status=statuses[wi % len(statuses)],
            )
            g.add_entity(wave)
            waves.append(wave)

        # Distribute orders across waves
        for i, order in enumerate(orders):
            wave = waves[i % wc.active_wave_count]
            g.add_edge(
                WarehouseEdge(
                    id=f"e-{wave.id}-{order.id}",
                    source_id=wave.id,
                    target_id=order.id,
                    relationship_type=RelationshipType.FULFILLS,
                )
            )

        # Assign carrier cutoffs to waves
        cutoffs = g.entities_by_type(EntityType.CARRIER_CUTOFF)
        for wi, wave in enumerate(waves):
            if cutoffs:
                cutoff = cutoffs[wi % len(cutoffs)]
                g.add_edge(
                    WarehouseEdge(
                        id=f"e-{wave.id}-cutoff-{wi}",
                        source_id=wave.id,
                        target_id=cutoff.id,
                        relationship_type=RelationshipType.CONSTRAINED_BY,
                    )
                )

        # Generate tasks
        tasks_per_wave = wc.task_count // wc.active_wave_count
        remainder_tasks = wc.task_count - (tasks_per_wave * wc.active_wave_count)

        # Build skill-based worker pools
        pick_workers = [w for w in workers if "pick" in w.skills]
        pack_workers = [w for w in workers if "pack" in w.skills]
        putaway_workers = [w for w in workers if "putaway" in w.skills]
        if not pick_workers:
            pick_workers = workers
            warnings.append("No workers with 'pick' skill; all workers used for PICK tasks")
        if not pack_workers:
            pack_workers = workers
        if not putaway_workers:
            putaway_workers = workers

        agvs_forklifts = [
            e for e in equipment_list
            if e.equipment_type in (EquipmentType.AGV, EquipmentType.FORKLIFT)
        ]

        # Zone lookup by type (fall back to all zones if none of the type exist)
        picking_zones = [z for z in zones if z.zone_type == "picking"] or zones
        packing_zones = [z for z in zones if z.zone_type == "packing"] or zones
        receiving_zones = [z for z in zones if z.zone_type == "receiving"] or zones

        tasks: list[Task] = []
        task_global_idx = 0
        worker_assign_idx = 0
        equip_assign_idx = 0
        sku_idx = 0

        for wi, wave in enumerate(waves):
            wave_task_count = tasks_per_wave + (1 if wi < remainder_tasks else 0)
            for ti in range(wave_task_count):
                task_slot = ti % 3  # rotate: PICK, PACK, PUTAWAY
                if task_slot == 0:
                    task_type = TaskType.PICK
                    zone = picking_zones[task_global_idx % len(picking_zones)]
                    worker_pool = pick_workers
                elif task_slot == 1:
                    task_type = TaskType.PACK
                    zone = packing_zones[task_global_idx % len(packing_zones)]
                    worker_pool = pack_workers
                else:
                    task_type = TaskType.PUTAWAY
                    zone = receiving_zones[task_global_idx % len(receiving_zones)]
                    worker_pool = putaway_workers

                priority = "high" if wave.status == "active" else "normal"
                task = Task(
                    id=f"task-{task_global_idx:06d}",
                    task_type=task_type,
                    zone_id=zone.id,
                    status=(
                        TaskStatus.IN_PROGRESS
                        if (wi == 0 and ti == 0)
                        else TaskStatus.PENDING
                    ),
                    priority=priority,
                )
                g.add_entity(task)

                # BELONGS_TO wave
                g.add_edge(
                    WarehouseEdge(
                        id=f"e-{task.id}-{wave.id}",
                        source_id=task.id,
                        target_id=wave.id,
                        relationship_type=RelationshipType.BELONGS_TO,
                    )
                )

                # ASSIGNED_TO worker (temporal, open-ended)
                if worker_pool:
                    worker = worker_pool[worker_assign_idx % len(worker_pool)]
                    g.add_edge(
                        WarehouseEdge(
                            id=f"e-{worker.id}-{task.id}",
                            source_id=worker.id,
                            target_id=task.id,
                            relationship_type=RelationshipType.ASSIGNED_TO,
                            valid_from=EPOCH,
                        )
                    )
                    worker_assign_idx += 1

                # SUPPORTS from equipment (PICK tasks only)
                if task_type == TaskType.PICK and agvs_forklifts:
                    eq = agvs_forklifts[equip_assign_idx % len(agvs_forklifts)]
                    g.add_edge(
                        WarehouseEdge(
                            id=f"e-{eq.id}-{task.id}",
                            source_id=eq.id,
                            target_id=task.id,
                            relationship_type=RelationshipType.SUPPORTS,
                            valid_from=EPOCH,
                        )
                    )
                    equip_assign_idx += 1

                # REQUIRES SKU for PICK and PUTAWAY tasks
                if task_type in (TaskType.PICK, TaskType.PUTAWAY) and skus:
                    sku = skus[sku_idx % len(skus)]
                    g.add_edge(
                        WarehouseEdge(
                            id=f"e-{task.id}-{sku.id}",
                            source_id=task.id,
                            target_id=sku.id,
                            relationship_type=RelationshipType.REQUIRES,
                        )
                    )
                    sku_idx += 1

                tasks.append(task)
                task_global_idx += 1

        return waves, tasks

    def _generate_history(
        self,
        g: CanonicalWarehouseGraph,
        workers: list[Worker],
        equipment_list: list[Equipment],
        tasks: list[Task],
        skus: list[SKU],
        warnings: list[str],
    ) -> None:
        rng = _domain_rng(self._config.seed, DOMAIN_OFFSET_HISTORY)
        days = self._config.history.history_days
        if days == 0:
            return

        EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)
        SECONDS_PER_DAY = 86400

        event_idx = 0
        for day in range(days):
            day_offset = day * SECONDS_PER_DAY
            event_time = datetime.fromtimestamp(
                EPOCH.timestamp() + day_offset, tz=timezone.utc
            )

            # Worker absences (~5% per worker per day)
            for worker in workers:
                if rng.random() < 0.05:
                    g.add_event(
                        OperationalEvent(
                            event_id=f"evt-{event_idx:08d}",
                            event_type=OperationalEventType.WORKER_ABSENCE,
                            event_time=event_time,
                            entity_id=worker.id,
                            source="generated",
                        )
                    )
                    event_idx += 1

            # Equipment failures (~2% per equipment per day)
            for eq in equipment_list:
                if rng.random() < 0.02:
                    g.add_event(
                        OperationalEvent(
                            event_id=f"evt-{event_idx:08d}",
                            event_type=OperationalEventType.EQUIPMENT_FAILURE,
                            event_time=event_time,
                            entity_id=eq.id,
                            source="generated",
                        )
                    )
                    event_idx += 1

        if event_idx > 0 and self._config.history.history_days > 0:
            warnings.append(
                f"Generated {event_idx} historical events over {days} days"
            )
