# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Clean-path acceptance tests: config → generate → pack → validate → load → project → ScenarioWorld.
No PostgreSQL, Redis, Milvus, or Kafka required.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from maiw_world.config import WarehouseWorldConfig
from maiw_world.generator import WarehouseWorldGenerator
from maiw_world.datapack import WarehouseDataPack, compute_semantic_checksum
from maiw_world.projections import WarehouseProjectionBuilder
from maiw_world.scenario import labor_constraint_scenario, ScenarioWorld


def test_full_clean_path(tmp_path):
    """config → generate → pack → validate → load → project — no DB required."""
    cfg = WarehouseWorldConfig.small()
    result = WarehouseWorldGenerator(cfg).generate()
    g = result.graph

    WarehouseDataPack.write(g, cfg, tmp_path / "pack")

    v = WarehouseDataPack.verify(tmp_path / "pack")
    assert v.passed, f"DataPack verification failed: {v.errors}"

    g2 = WarehouseDataPack.load(tmp_path / "pack")
    assert compute_semantic_checksum(g) == compute_semantic_checksum(g2)

    overlay = labor_constraint_scenario(g2)
    world = ScenarioWorld(g2, overlay)
    proj = WarehouseProjectionBuilder(world).build_all()

    assert proj["labor"].total_count > 0
    assert proj["inventory"].total_sku_count > 0
    assert proj["equipment"].total_count > 0
    assert proj["waves"].waves


def test_dc47_identity():
    """Canonical DC-47 config produces correct identity."""
    cfg = WarehouseWorldConfig.dc47_demo()
    assert cfg.warehouse_id == "DC-47"
    assert cfg.dataset_id == "dc47-demo-v1"
    assert cfg.seed == 42


def test_small_config_no_db_required(tmp_path):
    """Small world generates, validates, and projects without any external DB."""
    cfg = WarehouseWorldConfig.small()
    g = WarehouseWorldGenerator(cfg).generate().graph
    WarehouseDataPack.write(g, cfg, tmp_path / "pack")
    v = WarehouseDataPack.verify(tmp_path / "pack")
    assert v.passed, f"Validation failed: {v.errors}"


def test_scenario_world_no_db(tmp_path):
    """ScenarioWorld + projections work without any DB."""
    cfg = WarehouseWorldConfig.small()
    g = WarehouseWorldGenerator(cfg).generate().graph

    overlay = labor_constraint_scenario(g)
    world = ScenarioWorld(g, overlay)

    # At t=600, some workers may be absent (events can fire within that window)
    proj = WarehouseProjectionBuilder(world, at_offset=600.0).build_all()
    assert proj["labor"].absent_count >= 0
    assert proj["labor"].total_count > 0


def test_reproducibility(tmp_path):
    """Same config + seed → same semantic checksum, always."""
    cfg = WarehouseWorldConfig.small()
    g1 = WarehouseWorldGenerator(cfg).generate().graph
    g2 = WarehouseWorldGenerator(cfg).generate().graph
    assert compute_semantic_checksum(g1) == compute_semantic_checksum(g2)
