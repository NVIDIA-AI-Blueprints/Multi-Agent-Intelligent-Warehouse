# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Shared test fixtures for maiw-world tests.

make_tiny_world() creates a minimal but complete warehouse world used by
all test modules. Entity count: 24 total.
"""

from __future__ import annotations

from datetime import datetime, timezone

from maiw_world.edges import RelationshipType, WarehouseEdge
from maiw_world.entities import (
    CarrierCutoff,
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
from maiw_world.graph import CanonicalWarehouseGraph

_UTC = timezone.utc
_T0 = datetime(2026, 9, 1, 8, 0, 0, tzinfo=_UTC)


def make_tiny_world() -> CanonicalWarehouseGraph:
    """
    Build a minimal but structurally valid warehouse world.

    Contents:
      1 warehouse, 2 zones, 3 locations, 2 workers, 1 shift,
      1 AGV, 3 SKUs, 2 inventory positions, 2 waves, 4 tasks,
      2 orders, 1 carrier cutoff.
    Total entities: 24
    All relationships valid. Temporal edges use _T0 as valid_from.
    """
    g = CanonicalWarehouseGraph()

    # ── Entities ───────────────────────────────────────────────────────────────
    wh = Warehouse(id="DC-47", name="DC-47 Demo Warehouse")
    z1 = Zone(id="zone-A1", warehouse_id="DC-47", zone_code="A1", zone_type="picking")
    z2 = Zone(
        id="zone-RECV",
        warehouse_id="DC-47",
        zone_code="RECV",
        zone_type="receiving",
    )
    loc1 = Location(
        id="loc-A-001",
        zone_id="zone-A1",
        aisle="A",
        bay="01",
        level="01",
        location_code="A-01-01",
    )
    loc2 = Location(
        id="loc-A-002",
        zone_id="zone-A1",
        aisle="A",
        bay="01",
        level="02",
        location_code="A-01-02",
    )
    loc3 = Location(
        id="loc-RECV-001",
        zone_id="zone-RECV",
        aisle="R",
        bay="01",
        level="01",
        location_code="R-01-01",
    )

    w1 = Worker(
        id="worker-001",
        username="alice",
        full_name="Alice Chen",
        role="operator",
        skills=["pick", "pack"],
    )
    w2 = Worker(
        id="worker-002",
        username="bob",
        full_name="Bob Kim",
        role="operator",
        skills=["pick"],
    )
    shift = Shift(id="shift-day", shift_name="day", start_hour=6, end_hour=14)

    agv = Equipment(
        id="agv-001",
        equipment_type=EquipmentType.AGV,
        model="Locus Origin",
        zone_id="zone-A1",
    )

    sku1 = SKU(id="sku-000001", name="Lay's Classic 1.5oz", category="snacks")
    sku2 = SKU(id="sku-000002", name="Doritos Nacho 2oz", category="snacks")
    sku3 = SKU(id="sku-000003", name="Cheetos Crunchy 3oz", category="snacks")

    inv1 = InventoryPosition(
        id="invpos-001",
        sku_id="sku-000001",
        location_id="loc-A-001",
        quantity_available=2400,
        quantity_reserved=120,
        reorder_point=500,
    )
    inv2 = InventoryPosition(
        id="invpos-002",
        sku_id="sku-000002",
        location_id="loc-A-002",
        quantity_available=80,
        quantity_reserved=0,
        reorder_point=500,  # low stock scenario
    )

    wave1 = Wave(id="wave-017", wave_number=17, strategy="priority", status="active")
    wave2 = Wave(id="wave-018", wave_number=18, strategy="fifo", status="planning")

    task1 = Task(
        id="task-000001",
        task_type=TaskType.PICK,
        zone_id="zone-A1",
        status=TaskStatus.IN_PROGRESS,
        priority="high",
    )
    task2 = Task(
        id="task-000002",
        task_type=TaskType.PICK,
        zone_id="zone-A1",
        status=TaskStatus.PENDING,
        priority="high",
    )
    task3 = Task(
        id="task-000003",
        task_type=TaskType.PACK,
        zone_id="zone-A1",
        status=TaskStatus.PENDING,
        priority="normal",
    )
    task4 = Task(
        id="task-000004",
        task_type=TaskType.PUTAWAY,
        zone_id="zone-RECV",
        status=TaskStatus.PENDING,
        priority="normal",
    )

    order1 = Order(
        id="order-001",
        order_reference="ORD-2026-001",
        priority="critical",
    )
    order2 = Order(
        id="order-002",
        order_reference="ORD-2026-002",
        priority="normal",
    )

    cutoff = CarrierCutoff(
        id="cutoff-001",
        carrier="FedEx Priority",
        cutoff_time=datetime(2026, 9, 1, 14, 0, 0, tzinfo=_UTC),
    )

    # Add all entities (24 total)
    for entity in [
        wh, z1, z2, loc1, loc2, loc3,
        w1, w2, shift,
        agv,
        sku1, sku2, sku3,
        inv1, inv2,
        wave1, wave2,
        task1, task2, task3, task4,
        order1, order2,
        cutoff,
    ]:
        g.add_entity(entity)

    # ── Edges ──────────────────────────────────────────────────────────────────
    edges = [
        # Facility structure
        WarehouseEdge(
            id="e-wh-z1",
            source_id="DC-47",
            target_id="zone-A1",
            relationship_type=RelationshipType.CONTAINS,
        ),
        WarehouseEdge(
            id="e-wh-z2",
            source_id="DC-47",
            target_id="zone-RECV",
            relationship_type=RelationshipType.CONTAINS,
        ),
        WarehouseEdge(
            id="e-z1-l1",
            source_id="zone-A1",
            target_id="loc-A-001",
            relationship_type=RelationshipType.CONTAINS,
        ),
        WarehouseEdge(
            id="e-z1-l2",
            source_id="zone-A1",
            target_id="loc-A-002",
            relationship_type=RelationshipType.CONTAINS,
        ),
        WarehouseEdge(
            id="e-z2-l3",
            source_id="zone-RECV",
            target_id="loc-RECV-001",
            relationship_type=RelationshipType.CONTAINS,
        ),
        # Labor
        WarehouseEdge(
            id="e-wh-w1",
            source_id="DC-47",
            target_id="worker-001",
            relationship_type=RelationshipType.EMPLOYS,
        ),
        WarehouseEdge(
            id="e-wh-w2",
            source_id="DC-47",
            target_id="worker-002",
            relationship_type=RelationshipType.EMPLOYS,
        ),
        WarehouseEdge(
            id="e-w1-s",
            source_id="worker-001",
            target_id="shift-day",
            relationship_type=RelationshipType.MEMBER_OF,
        ),
        WarehouseEdge(
            id="e-w2-s",
            source_id="worker-002",
            target_id="shift-day",
            relationship_type=RelationshipType.MEMBER_OF,
        ),
        # Equipment
        WarehouseEdge(
            id="e-wh-agv",
            source_id="DC-47",
            target_id="agv-001",
            relationship_type=RelationshipType.OPERATES,
        ),
        # Inventory
        WarehouseEdge(
            id="e-wh-sku1",
            source_id="DC-47",
            target_id="sku-000001",
            relationship_type=RelationshipType.STORES,
        ),
        WarehouseEdge(
            id="e-wh-sku2",
            source_id="DC-47",
            target_id="sku-000002",
            relationship_type=RelationshipType.STORES,
        ),
        WarehouseEdge(
            id="e-wh-sku3",
            source_id="DC-47",
            target_id="sku-000003",
            relationship_type=RelationshipType.STORES,
        ),
        WarehouseEdge(
            id="e-ip1-l1",
            source_id="invpos-001",
            target_id="loc-A-001",
            relationship_type=RelationshipType.STORED_AT,
        ),
        WarehouseEdge(
            id="e-ip2-l2",
            source_id="invpos-002",
            target_id="loc-A-002",
            relationship_type=RelationshipType.STORED_AT,
        ),
        # Task assignments — temporal edges (open-ended, currently active)
        WarehouseEdge(
            id="e-w1-t1",
            source_id="worker-001",
            target_id="task-000001",
            relationship_type=RelationshipType.ASSIGNED_TO,
            valid_from=_T0,
        ),
        WarehouseEdge(
            id="e-w2-t2",
            source_id="worker-002",
            target_id="task-000002",
            relationship_type=RelationshipType.ASSIGNED_TO,
            valid_from=_T0,
        ),
        # Equipment supports task — temporal
        WarehouseEdge(
            id="e-agv-t1",
            source_id="agv-001",
            target_id="task-000001",
            relationship_type=RelationshipType.SUPPORTS,
            valid_from=_T0,
        ),
        # Tasks belong to waves
        WarehouseEdge(
            id="e-t1-w17",
            source_id="task-000001",
            target_id="wave-017",
            relationship_type=RelationshipType.BELONGS_TO,
        ),
        WarehouseEdge(
            id="e-t2-w17",
            source_id="task-000002",
            target_id="wave-017",
            relationship_type=RelationshipType.BELONGS_TO,
        ),
        WarehouseEdge(
            id="e-t3-w17",
            source_id="task-000003",
            target_id="wave-017",
            relationship_type=RelationshipType.BELONGS_TO,
        ),
        WarehouseEdge(
            id="e-t4-w18",
            source_id="task-000004",
            target_id="wave-018",
            relationship_type=RelationshipType.BELONGS_TO,
        ),
        # Task requires SKU
        WarehouseEdge(
            id="e-t1-sku1",
            source_id="task-000001",
            target_id="sku-000001",
            relationship_type=RelationshipType.REQUIRES,
        ),
        WarehouseEdge(
            id="e-t2-sku2",
            source_id="task-000002",
            target_id="sku-000002",
            relationship_type=RelationshipType.REQUIRES,
        ),
        # Wave fulfills orders — many-to-many: wave-017 fulfills BOTH orders
        WarehouseEdge(
            id="e-w17-o1",
            source_id="wave-017",
            target_id="order-001",
            relationship_type=RelationshipType.FULFILLS,
        ),
        WarehouseEdge(
            id="e-w17-o2",
            source_id="wave-017",
            target_id="order-002",
            relationship_type=RelationshipType.FULFILLS,
        ),
        # Wave constrained by carrier cutoff
        WarehouseEdge(
            id="e-w17-c1",
            source_id="wave-017",
            target_id="cutoff-001",
            relationship_type=RelationshipType.CONSTRAINED_BY,
        ),
    ]
    for edge in edges:
        g.add_edge(edge)

    return g
