# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Canonical typed entity models for the warehouse world.

All entities are immutable (frozen=True). Assignments are expressed as
WarehouseEdge relationships, not embedded fields.

Key design decisions:
- Task has NO assigned_to field — use ASSIGNED_TO edges for temporal assignments.
- CarrierCutoff.cutoff_time must be timezone-aware.
- InventoryPosition quantities must be non-negative.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class EntityType(str, Enum):
    WAREHOUSE = "warehouse"
    ZONE = "zone"
    LOCATION = "location"
    WORKER = "worker"
    SHIFT = "shift"
    EQUIPMENT = "equipment"
    SKU = "sku"
    INVENTORY_POSITION = "inventory_position"
    ORDER = "order"
    WAVE = "wave"
    TASK = "task"
    SHIPMENT = "shipment"
    CARRIER_CUTOFF = "carrier_cutoff"


class WarehouseEntity(BaseModel):
    """Base class for all warehouse world entities. Immutable once created."""

    model_config = ConfigDict(frozen=True)

    id: str
    entity_type: EntityType

    @field_validator("id")
    @classmethod
    def id_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Entity id must be non-empty")
        return v


class Warehouse(WarehouseEntity):
    entity_type: EntityType = EntityType.WAREHOUSE
    name: str
    timezone: str = "UTC"


class Zone(WarehouseEntity):
    entity_type: EntityType = EntityType.ZONE
    warehouse_id: str
    zone_code: str  # e.g. "A1", "RECEIVING"
    zone_type: str = "picking"  # "picking" | "packing" | "receiving" | "storage" | "dock"


class Location(WarehouseEntity):
    entity_type: EntityType = EntityType.LOCATION
    zone_id: str
    aisle: str
    bay: str
    level: str
    location_code: str  # human-readable e.g. "A-01-01"


class Worker(WarehouseEntity):
    entity_type: EntityType = EntityType.WORKER
    username: str
    full_name: str
    role: str  # "operator" | "supervisor" | "manager"
    skills: list[str] = []


class Shift(WarehouseEntity):
    entity_type: EntityType = EntityType.SHIFT
    shift_name: str  # "day" | "evening" | "night"
    start_hour: int  # 0–23
    end_hour: int    # 0–23

    @field_validator("start_hour", "end_hour")
    @classmethod
    def hour_range(cls, v: int) -> int:
        if v < 0 or v > 23:
            raise ValueError("Hour must be 0–23")
        return v


class EquipmentType(str, Enum):
    AGV = "agv"
    FORKLIFT = "forklift"
    CONVEYOR = "conveyor"


class Equipment(WarehouseEntity):
    entity_type: EntityType = EntityType.EQUIPMENT
    equipment_type: EquipmentType
    model: str = ""
    zone_id: str | None = None


class SKU(WarehouseEntity):
    entity_type: EntityType = EntityType.SKU
    name: str
    category: str = ""
    unit_of_measure: str = "EA"


class InventoryPosition(WarehouseEntity):
    entity_type: EntityType = EntityType.INVENTORY_POSITION
    sku_id: str
    location_id: str
    quantity_available: int = 0
    quantity_reserved: int = 0
    reorder_point: int = 0

    @model_validator(mode="after")
    def non_negative_quantities(self) -> "InventoryPosition":
        if self.quantity_available < 0:
            raise ValueError(
                f"quantity_available must be >= 0, got {self.quantity_available}"
            )
        if self.quantity_reserved < 0:
            raise ValueError(
                f"quantity_reserved must be >= 0, got {self.quantity_reserved}"
            )
        return self


class Order(WarehouseEntity):
    entity_type: EntityType = EntityType.ORDER
    order_reference: str
    customer_id: str = ""
    priority: str = "normal"  # "critical" | "high" | "normal" | "low"


class Wave(WarehouseEntity):
    entity_type: EntityType = EntityType.WAVE
    wave_number: int
    strategy: str = "priority"
    status: str = "planning"  # "planning" | "active" | "complete"


class TaskType(str, Enum):
    PICK = "PICK"
    PACK = "PACK"
    PUTAWAY = "PUTAWAY"
    CYCLE_COUNT = "CYCLE_COUNT"
    REPLENISHMENT = "REPLENISHMENT"
    INSPECTION = "INSPECTION"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


class Task(WarehouseEntity):
    """
    A discrete unit of warehouse work.

    IMPORTANT: Tasks have NO assigned_to field. Worker assignments are expressed
    exclusively as ASSIGNED_TO edges (Worker→Task). This supports:
    - Temporal reassignment: multiple ASSIGNED_TO edges over time
    - Zero, one, or many assignees at any point
    - Clean separation of state (task status) from relationships (assignment)
    """

    entity_type: EntityType = EntityType.TASK
    task_type: TaskType
    zone_id: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    priority: str = "normal"


class Shipment(WarehouseEntity):
    entity_type: EntityType = EntityType.SHIPMENT
    carrier: str = ""
    tracking_reference: str = ""


class CarrierCutoff(WarehouseEntity):
    entity_type: EntityType = EntityType.CARRIER_CUTOFF
    carrier: str
    cutoff_time: datetime  # must be timezone-aware UTC
    dock_door_id: str | None = None

    @field_validator("cutoff_time")
    @classmethod
    def cutoff_time_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError(
                "cutoff_time must be timezone-aware. "
                "Use datetime(..., tzinfo=timezone.utc) or similar."
            )
        return v
