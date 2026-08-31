# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for maiw_world.config (12 tests)."""

import pytest
from pydantic import ValidationError

from maiw_world.config import (
    EquipmentConfig,
    FacilityConfig,
    InventoryConfig,
    LaborConfig,
    OrderConfig,
    WarehouseWorldConfig,
    WaveConfig,
)
from maiw_world.validation import FindingSeverity, validate_config


# ── 1. dc47_demo() returns valid config ───────────────────────────────────────

def test_dc47_demo_returns_valid_config():
    cfg = WarehouseWorldConfig.dc47_demo()
    assert cfg.warehouse_id == "DC-47"
    assert cfg.facility.zone_count == 6
    assert cfg.labor.shift_count == 3


# ── 2. small() returns valid config ───────────────────────────────────────────

def test_small_returns_valid_config():
    cfg = WarehouseWorldConfig.small()
    assert cfg.inventory.sku_count == 1000
    assert cfg.labor.workers_per_shift == 20
    assert cfg.equipment.agv_count == 2
    assert cfg.equipment.forklift_count == 2


# ── 3. large() returns valid config ───────────────────────────────────────────

def test_large_returns_valid_config():
    cfg = WarehouseWorldConfig.large()
    assert cfg.inventory.sku_count == 100000
    assert cfg.labor.workers_per_shift == 150
    assert cfg.equipment.agv_count == 30
    assert cfg.equipment.forklift_count == 40


# ── 4. seed=42 retained in dc47_demo ─────────────────────────────────────────

def test_dc47_demo_seed():
    cfg = WarehouseWorldConfig.dc47_demo()
    assert cfg.seed == 42


# ── 5. dataset_id='dc47-demo-v1' retained ────────────────────────────────────

def test_dc47_demo_dataset_id():
    cfg = WarehouseWorldConfig.dc47_demo()
    assert cfg.dataset_id == "dc47-demo-v1"


# ── 6. Zero sku_count raises ValidationError ──────────────────────────────────

def test_zero_sku_count_raises():
    with pytest.raises(ValidationError, match="sku_count"):
        InventoryConfig(sku_count=0, low_stock_pct=0.05)


# ── 7. Negative zone_count raises ValidationError ────────────────────────────

def test_negative_zone_count_raises():
    with pytest.raises(ValidationError, match="zone_count"):
        FacilityConfig(zone_count=-1, location_count=10, dock_door_count=2)


# ── 8. low_stock_pct > 1.0 raises ValidationError ────────────────────────────

def test_low_stock_pct_above_one_raises():
    with pytest.raises(ValidationError, match="low_stock_pct"):
        InventoryConfig(sku_count=1000, low_stock_pct=1.1)


# ── 9. low_stock_pct < 0.0 raises ValidationError ────────────────────────────

def test_low_stock_pct_below_zero_raises():
    with pytest.raises(ValidationError, match="low_stock_pct"):
        InventoryConfig(sku_count=1000, low_stock_pct=-0.01)


# ── 10. shift_count > 3 raises ValidationError ───────────────────────────────

def test_shift_count_above_three_raises():
    with pytest.raises(ValidationError, match="shift_count"):
        LaborConfig(workers_per_shift=10, shift_count=4)


# ── 11. Zero equipment raises ValidationError ────────────────────────────────

def test_zero_equipment_raises():
    with pytest.raises(ValidationError, match="at least one"):
        EquipmentConfig(agv_count=0, forklift_count=0, conveyor_count=0)


# ── 12. validate_config(dc47_demo()) returns PASS ────────────────────────────

def test_validate_config_dc47_demo_passes():
    cfg = WarehouseWorldConfig.dc47_demo()
    report = validate_config(cfg)
    assert report.overall == FindingSeverity.PASS
    assert report.passed is True
    assert report.findings == []
