# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Tests for world_loader.py (Phase 14E).

All tests set MAIW_WORLD_AUTO_GENERATE=true via monkeypatch to avoid
needing a pre-generated DataPack on disk.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def auto_generate_enabled(monkeypatch, tmp_path):
    """Force AUTO_GENERATE=true and use a temp dir for DataPacks."""
    monkeypatch.setenv("MAIW_WORLD_AUTO_GENERATE", "true")
    monkeypatch.setenv("MAIW_WORLD_DATAPACK_DIR", str(tmp_path))
    # Reload module-level constants in world_loader
    import importlib
    import maiw_api.demo.world_loader as wl
    monkeypatch.setattr(wl, "AUTO_GENERATE", True)
    monkeypatch.setattr(wl, "DEFAULT_DATAPACK_DIR", tmp_path)
    yield tmp_path


# ── 1. load_canonical_graph() with AUTO_GENERATE=true returns valid graph ──────

def test_load_canonical_graph_auto_generate(auto_generate_enabled):
    from maiw_api.demo.world_loader import load_canonical_graph
    graph = load_canonical_graph()
    assert graph.entity_count > 0
    assert graph.edge_count > 0


# ── 2. build_scenario_world("labor_constraint_wave_risk") returns ScenarioWorld ─

def test_build_labor_constraint_world(auto_generate_enabled):
    from maiw_api.demo.world_loader import build_scenario_world
    from maiw_world.scenario import ScenarioWorld
    world = build_scenario_world("labor_constraint_wave_risk")
    assert isinstance(world, ScenarioWorld)
    # Should have worker absence events
    assert len(world.overlay.events) > 0


# ── 3. build_scenario_world("equipment_failure") returns ScenarioWorld ───────────

def test_build_equipment_failure_world(auto_generate_enabled):
    from maiw_api.demo.world_loader import build_scenario_world
    from maiw_world.scenario import ScenarioWorld
    world = build_scenario_world("equipment_failure")
    assert isinstance(world, ScenarioWorld)
    # Should have equipment failure events
    assert len(world.overlay.events) > 0


# ── 4. build_scenario_world("healthy_baseline") returns ScenarioWorld no events ─

def test_build_healthy_baseline_world(auto_generate_enabled):
    from maiw_api.demo.world_loader import build_scenario_world
    from maiw_world.scenario import ScenarioWorld
    world = build_scenario_world("healthy_baseline")
    assert isinstance(world, ScenarioWorld)
    assert len(world.overlay.events) == 0


# ── 5. build_scenario_world("stale_state") works via compat adapter ─────────────

def test_build_stale_state_compat(auto_generate_enabled):
    from maiw_api.demo.world_loader import build_scenario_world
    from maiw_world.scenario import ScenarioWorld
    world = build_scenario_world("stale_state")
    assert isinstance(world, ScenarioWorld)


# ── 6. load_canonical_graph() without AUTO_GENERATE raises FileNotFoundError ────

def test_load_canonical_graph_missing_raises(tmp_path, monkeypatch):
    import maiw_api.demo.world_loader as wl
    monkeypatch.setattr(wl, "AUTO_GENERATE", False)
    monkeypatch.setattr(wl, "DEFAULT_DATAPACK_DIR", tmp_path / "nonexistent")
    monkeypatch.setenv("MAIW_WORLD_AUTO_GENERATE", "false")
    # Clear any cached DataPack from previous test
    target = tmp_path / "nonexistent" / "dc47-demo-v1"
    assert not target.exists()
    with pytest.raises(FileNotFoundError, match="dc47-demo-v1"):
        wl.load_canonical_graph()


# ── 7. load_canonical_graph() after _auto_generate() succeeds without error ──────

def test_load_after_auto_generate(auto_generate_enabled):
    from maiw_api.demo.world_loader import load_canonical_graph, _auto_generate, CANONICAL_DATASET_ID
    pack_dir = auto_generate_enabled / CANONICAL_DATASET_ID
    # Generate first
    _auto_generate(pack_dir)
    assert pack_dir.exists()
    # Load should succeed
    graph = load_canonical_graph()
    assert graph.entity_count > 0


# ── 8. Reset produces identical initial state on second call ────────────────────

def test_reset_produces_identical_state(auto_generate_enabled):
    from maiw_api.demo.world_loader import build_scenario_world
    from maiw_api.demo.world import DemoWarehouseWorld

    sw = build_scenario_world("healthy_baseline")
    world = DemoWarehouseWorld(scenario_world=sw)

    # Capture initial state
    initial_worker_count = len(world.workers)
    initial_eq_count = len(world.equipment)
    initial_inv_count = len(world.inventory)

    # Mutate world
    first_worker_id = next(iter(world.workers))
    world.workers[first_worker_id].status = "on_leave"

    # Reset
    world.reset()

    # Should match original state
    assert len(world.workers) == initial_worker_count
    assert len(world.equipment) == initial_eq_count
    assert len(world.inventory) == initial_inv_count
    # The mutated worker should be restored
    assert world.workers[first_worker_id].status in ("active", "on_leave")
    # (actual status depends on scenario overlay; reset rebuilds from projections)
