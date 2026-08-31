# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
world_loader.py — load canonical DataPack + apply scenario overlay.

This is the Phase 14E entry point for the demo API.
Does NOT generate worlds at startup — generation is a developer setup step.

Three-layer architecture:
  DataPack (files on disk)   →  CanonicalWarehouseGraph (immutable)
                             +  ScenarioOverlay (disruption events)
                             ↓
                             ScenarioWorld (combined runtime view)
                             ↓
                             DemoWarehouseWorld (mutable, via projections)

DataPack checksum never changes during a demo run.
"""

from __future__ import annotations

import os
from pathlib import Path

CANONICAL_DATASET_ID = "dc47-demo-v1"
CANONICAL_WAREHOUSE_ID = "DC-47"
CANONICAL_SEED = 42

# Default DataPack location — override with MAIW_WORLD_DATAPACK_DIR env var
DEFAULT_DATAPACK_DIR = (
    Path(__file__).parent.parent.parent.parent.parent / "data" / "worlds"
)

# For tests/CI only — auto-generate if pack missing
AUTO_GENERATE = os.environ.get("MAIW_WORLD_AUTO_GENERATE", "false").lower() == "true"


def get_datapack_dir() -> Path:
    env = os.environ.get("MAIW_WORLD_DATAPACK_DIR")
    return Path(env) if env else DEFAULT_DATAPACK_DIR


def load_canonical_graph():
    """
    Load the canonical DC-47 CanonicalWarehouseGraph from disk.

    Raises FileNotFoundError if the DataPack is missing and AUTO_GENERATE is false.
    Set MAIW_WORLD_AUTO_GENERATE=true to auto-generate for local dev / CI.
    """
    from maiw_world.datapack import WarehouseDataPack

    pack_dir = get_datapack_dir() / CANONICAL_DATASET_ID
    if not pack_dir.exists():
        if AUTO_GENERATE:
            _auto_generate(pack_dir)
        else:
            raise FileNotFoundError(
                f"Warehouse DataPack '{CANONICAL_DATASET_ID}' not found at {pack_dir}. "
                f"Run the Phase 14E setup step to generate it, or set "
                f"MAIW_WORLD_AUTO_GENERATE=true for local development."
            )
    return WarehouseDataPack.load(pack_dir)


def _auto_generate(pack_dir: Path) -> None:
    """Auto-generate canonical DataPack (test/dev only, not for production)."""
    from maiw_world.config import WarehouseWorldConfig
    from maiw_world.generator import WarehouseWorldGenerator
    from maiw_world.datapack import WarehouseDataPack

    cfg = WarehouseWorldConfig.dc47_demo()
    result = WarehouseWorldGenerator(cfg).generate()
    WarehouseDataPack.write(result.graph, cfg, pack_dir)


# ── Scenario overlay registry ────────────────────────────────────────────────
# Maps demo scenario names → overlay kind for DataPack-native path.
# Scenarios not listed here fall back to the legacy YAML path.
SCENARIO_OVERLAYS: dict[str, str] = {
    "labor_constraint_wave_risk": "labor_constraint",
    "equipment_failure":           "equipment_failure",
    "healthy_baseline":            "healthy_baseline",
    "stale_state":                 "healthy_baseline",   # compat adapter
    "state_drift":                 "healthy_baseline",   # compat adapter
}


def build_scenario_world(scenario_name: str):
    """
    Load canonical graph and apply scenario overlay by name.

    Falls back to a no-disruption healthy-baseline overlay for unknown kinds.
    Use SCENARIO_OVERLAYS to check whether a scenario name is DataPack-native.
    """
    from maiw_world.scenario import ScenarioOverlay, ScenarioWorld

    graph = load_canonical_graph()
    overlay_kind = SCENARIO_OVERLAYS.get(scenario_name)

    if overlay_kind == "labor_constraint":
        from maiw_world.scenario import labor_constraint_scenario
        overlay = labor_constraint_scenario(graph)

    elif overlay_kind == "equipment_failure":
        from maiw_world.scenario import equipment_failure_scenario
        overlay = equipment_failure_scenario(graph)

    elif overlay_kind == "healthy_baseline" or overlay_kind is None:
        # Minimal no-disruption overlay using the warehouse entity's ID as dataset_id
        from maiw_world.entities import EntityType
        warehouse_entities = graph.entities_by_type(EntityType.WAREHOUSE)
        dataset_id = warehouse_entities[0].id if warehouse_entities else CANONICAL_WAREHOUSE_ID
        overlay = ScenarioOverlay(
            scenario_id="healthy-baseline",
            name="Healthy Baseline",
            description="No active disruptions — warehouse operating nominally.",
            dataset_id=dataset_id,
            events=[],
        )

    else:
        raise ValueError(f"Unknown scenario overlay kind: {overlay_kind!r}")

    return ScenarioWorld(graph, overlay)
