# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
WarehouseWorldConfig — deterministic configuration for canonical world generation.

All counts must be positive. Validators fail fast with clear messages.
No random/non-deterministic logic — the seed field controls all downstream RNG.
"""

from __future__ import annotations

from pydantic import BaseModel, field_validator, model_validator


class FacilityConfig(BaseModel):
    """Physical facility configuration."""

    zone_count: int
    location_count: int
    dock_door_count: int

    @field_validator("zone_count")
    @classmethod
    def zone_count_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("zone_count must be >= 1")
        return v

    @field_validator("location_count")
    @classmethod
    def location_count_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("location_count must be >= 1")
        return v

    @field_validator("dock_door_count")
    @classmethod
    def dock_door_count_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("dock_door_count must be >= 1")
        return v

    @model_validator(mode="after")
    def location_count_gte_zone_count(self) -> "FacilityConfig":
        if self.location_count < self.zone_count:
            raise ValueError(
                f"location_count ({self.location_count}) must be >= zone_count ({self.zone_count})"
            )
        return self


class InventoryConfig(BaseModel):
    """Inventory catalog configuration."""

    sku_count: int
    low_stock_pct: float
    inventory_profile: str = "standard"  # "standard" | "peak" | "off-season"

    @field_validator("sku_count")
    @classmethod
    def sku_count_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("sku_count must be >= 1")
        return v

    @field_validator("low_stock_pct")
    @classmethod
    def low_stock_pct_range(cls, v: float) -> float:
        if v < 0.0 or v > 1.0:
            raise ValueError("low_stock_pct must be between 0.0 and 1.0 inclusive")
        return v

    @field_validator("inventory_profile")
    @classmethod
    def valid_profile(cls, v: str) -> str:
        allowed = {"standard", "peak", "off-season"}
        if v not in allowed:
            raise ValueError(f"inventory_profile must be one of {allowed}")
        return v


class LaborConfig(BaseModel):
    """Labor workforce configuration."""

    workers_per_shift: int
    shift_count: int
    skills: list[str] = ["pick", "pack", "putaway", "cycle_count"]

    @field_validator("workers_per_shift")
    @classmethod
    def workers_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("workers_per_shift must be >= 1")
        return v

    @field_validator("shift_count")
    @classmethod
    def shift_count_range(cls, v: int) -> int:
        if v < 1 or v > 3:
            raise ValueError("shift_count must be >= 1 and <= 3")
        return v


class EquipmentConfig(BaseModel):
    """Equipment fleet configuration."""

    agv_count: int = 0
    forklift_count: int = 0
    conveyor_count: int = 0

    @field_validator("agv_count", "forklift_count", "conveyor_count")
    @classmethod
    def non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Equipment counts must be >= 0")
        return v

    @model_validator(mode="after")
    def at_least_one_equipment(self) -> "EquipmentConfig":
        total = self.agv_count + self.forklift_count + self.conveyor_count
        if total < 1:
            raise ValueError(
                "EquipmentConfig must have at least one piece of equipment "
                "(agv_count + forklift_count + conveyor_count >= 1)"
            )
        return self


class OrderConfig(BaseModel):
    """Order volume configuration."""

    daily_order_count: int
    lines_per_order_mean: float

    @field_validator("daily_order_count")
    @classmethod
    def daily_order_count_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("daily_order_count must be >= 1")
        return v

    @field_validator("lines_per_order_mean")
    @classmethod
    def lines_positive(cls, v: float) -> float:
        if v <= 0.0:
            raise ValueError("lines_per_order_mean must be > 0.0")
        return v


class WaveConfig(BaseModel):
    """Wave management configuration."""

    active_wave_count: int
    strategy: str = "fifo"  # "fifo" | "priority" | "deadline"
    task_count: int

    @field_validator("active_wave_count")
    @classmethod
    def active_wave_count_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("active_wave_count must be >= 1")
        return v

    @field_validator("strategy")
    @classmethod
    def valid_strategy(cls, v: str) -> str:
        allowed = {"fifo", "priority", "deadline"}
        if v not in allowed:
            raise ValueError(f"strategy must be one of {allowed}")
        return v

    @field_validator("task_count")
    @classmethod
    def task_count_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("task_count must be >= 1")
        return v


class HistoryConfig(BaseModel):
    """Historical data window configuration."""

    history_days: int = 30

    @field_validator("history_days")
    @classmethod
    def history_days_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("history_days must be >= 0")
        return v


class WarehouseWorldConfig(BaseModel):
    """
    Complete deterministic configuration for canonical warehouse world generation.

    The ``seed`` field controls all downstream RNG. Given the same config,
    the same world is always produced.
    """

    warehouse_id: str
    dataset_id: str
    seed: int

    facility: FacilityConfig
    inventory: InventoryConfig
    labor: LaborConfig
    equipment: EquipmentConfig
    orders: OrderConfig
    waves: WaveConfig
    history: HistoryConfig = HistoryConfig()

    @field_validator("warehouse_id")
    @classmethod
    def warehouse_id_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("warehouse_id must be non-empty")
        return v

    @field_validator("dataset_id")
    @classmethod
    def dataset_id_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("dataset_id must be non-empty")
        return v

    @classmethod
    def dc47_demo(cls) -> "WarehouseWorldConfig":
        """Canonical DC-47 demo preset — seed=42, dataset_id='dc47-demo-v1'."""
        return cls(
            warehouse_id="DC-47",
            dataset_id="dc47-demo-v1",
            seed=42,
            facility=FacilityConfig(
                zone_count=6, location_count=240, dock_door_count=8
            ),
            inventory=InventoryConfig(sku_count=25000, low_stock_pct=0.04),
            labor=LaborConfig(workers_per_shift=40, shift_count=3),
            equipment=EquipmentConfig(agv_count=8, forklift_count=12, conveyor_count=4),
            orders=OrderConfig(daily_order_count=850, lines_per_order_mean=4.2),
            waves=WaveConfig(active_wave_count=3, strategy="priority", task_count=120),
            history=HistoryConfig(history_days=30),
        )

    @classmethod
    def small(cls) -> "WarehouseWorldConfig":
        """Small preset — 1k SKUs, 20 workers/shift, 2 AGVs, 2 forklifts."""
        return cls(
            warehouse_id="DC-SMALL",
            dataset_id="small-demo-v1",
            seed=1,
            facility=FacilityConfig(
                zone_count=2, location_count=40, dock_door_count=2
            ),
            inventory=InventoryConfig(sku_count=1000, low_stock_pct=0.05),
            labor=LaborConfig(workers_per_shift=20, shift_count=2),
            equipment=EquipmentConfig(agv_count=2, forklift_count=2, conveyor_count=0),
            orders=OrderConfig(daily_order_count=100, lines_per_order_mean=2.0),
            waves=WaveConfig(active_wave_count=1, strategy="fifo", task_count=20),
            history=HistoryConfig(history_days=7),
        )

    @classmethod
    def large(cls) -> "WarehouseWorldConfig":
        """Large preset — 100k SKUs, 150 workers/shift, 30 AGVs, 40 forklifts."""
        return cls(
            warehouse_id="DC-LARGE",
            dataset_id="large-demo-v1",
            seed=99,
            facility=FacilityConfig(
                zone_count=20, location_count=2000, dock_door_count=40
            ),
            inventory=InventoryConfig(sku_count=100000, low_stock_pct=0.02),
            labor=LaborConfig(workers_per_shift=150, shift_count=3),
            equipment=EquipmentConfig(
                agv_count=30, forklift_count=40, conveyor_count=20
            ),
            orders=OrderConfig(daily_order_count=5000, lines_per_order_mean=6.0),
            waves=WaveConfig(active_wave_count=10, strategy="priority", task_count=500),
            history=HistoryConfig(history_days=90),
        )
