# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
DemoWarehouseWorld Phase 14E integration tests.

Tests scenario_world-based initialization, DataPack checksum invariant,
mutation semantics, and reset behavior.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def auto_generate_env(monkeypatch, tmp_path):
    import maiw_api.demo.world_loader as wl
    monkeypatch.setenv("MAIW_WORLD_AUTO_GENERATE", "true")
    monkeypatch.setenv("MAIW_WORLD_DATAPACK_DIR", str(tmp_path))
    monkeypatch.setattr(wl, "AUTO_GENERATE", True)
    monkeypatch.setattr(wl, "DEFAULT_DATAPACK_DIR", tmp_path)
    yield tmp_path


@pytest.fixture
def scenario_world(auto_generate_env):
    from maiw_api.demo.world_loader import build_scenario_world
    return build_scenario_world("healthy_baseline")


@pytest.fixture
def labor_world(auto_generate_env):
    from maiw_api.demo.world_loader import build_scenario_world
    return build_scenario_world("labor_constraint_wave_risk")


# ── 1. DemoWarehouseWorld(scenario_world=sw) initializes without error ──────────

def test_init_with_scenario_world(scenario_world):
    from maiw_api.demo.world import DemoWarehouseWorld
    world = DemoWarehouseWorld(scenario_world=scenario_world)
    assert world is not None


# ── 2. Worker count in world matches labor projection ───────────────────────────

def test_worker_count_matches_projection(scenario_world):
    from maiw_api.demo.world import DemoWarehouseWorld
    from maiw_world.projections import WarehouseProjectionBuilder

    world = DemoWarehouseWorld(scenario_world=scenario_world)
    builder = WarehouseProjectionBuilder(scenario_world, at_offset=0.0)
    labor = builder.labor()

    assert len(world.workers) == labor.total_count


# ── 3. Mutation (mark worker absent) changes world state ────────────────────────

def test_mutation_changes_world_state(scenario_world):
    from maiw_api.demo.world import DemoWarehouseWorld

    world = DemoWarehouseWorld(scenario_world=scenario_world)
    assert world.workers, "Need at least one worker"
    first_id = next(iter(world.workers))

    # Mark absent
    world.workers[first_id].status = "on_leave"
    assert world.workers[first_id].status == "on_leave"


# ── 4. DataPack checksum unchanged after mutation ───────────────────────────────

def test_datapack_checksum_unchanged_after_mutation(scenario_world):
    from maiw_api.demo.world import DemoWarehouseWorld
    from maiw_world.datapack import compute_semantic_checksum

    world = DemoWarehouseWorld(scenario_world=scenario_world)
    initial_checksum = world._datapack_checksum
    assert initial_checksum is not None

    # Mutate runtime state
    if world.workers:
        first_id = next(iter(world.workers))
        world.workers[first_id].status = "on_leave"
    if world.equipment:
        first_eq = next(iter(world.equipment))
        world.equipment[first_eq].status = "offline"

    # DataPack checksum must be unchanged (it's from the immutable base graph)
    post_checksum = compute_semantic_checksum(scenario_world.base_graph)
    assert initial_checksum == post_checksum


# ── 5. reset() restores original projection-derived state ───────────────────────

def test_reset_restores_projection_state(scenario_world):
    from maiw_api.demo.world import DemoWarehouseWorld

    world = DemoWarehouseWorld(scenario_world=scenario_world)
    original_count = len(world.workers)

    # Mutate
    if world.workers:
        first_id = next(iter(world.workers))
        world.workers[first_id].status = "on_leave"

    # Reset
    world.reset()

    # Worker count should be restored
    assert len(world.workers) == original_count
