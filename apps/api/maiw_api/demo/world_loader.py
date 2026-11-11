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
# Demo scenarios the controller runs on the DataPack world. Every other
# scenario runs on the world its YAML defines (initial_state,
# clock_offset_seconds, timed_events, recovery).
#
# A scripted scenario runs on the DataPack world through the ``datapack``
# block of its YAML: DataPack ids, a clock offset, initial_state overrides,
# timed events counted from scenario start and recovery thresholds sized for
# the DataPack world (#309). Before #308 the scripted scenarios ran on the
# DataPack with their YAML timelines, whose ids (w-003, AGV-02) are not in
# the DataPack, so no disruption was ever recorded.
DATAPACK_SCENARIOS: frozenset[str] = frozenset(
    {
        "healthy_baseline",
        "equipment_failure",
        "labor_constraint_wave_risk",
        "stale_state",
        "state_drift",
    }
)

# Overlay presets for scenarios without a ``datapack`` block. A scenario with
# one gets its overlay from that block (see build_scenario_world).
SCENARIO_OVERLAYS: dict[str, str] = {
    "labor_constraint_wave_risk": "labor_constraint",
    "equipment_failure":           "equipment_failure",
    "healthy_baseline":            "healthy_baseline",
    "stale_state":                 "healthy_baseline",   # compat adapter
    "state_drift":                 "healthy_baseline",   # compat adapter
}

_SCENARIOS_DIR = Path(__file__).parent / "scenarios"


def load_scenario_yaml(scenario_name: str) -> dict:
    """The raw scenario YAML, or {} when there is no such scenario file."""
    import yaml

    path = _SCENARIOS_DIR / f"{scenario_name}.yaml"
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def datapack_block(scenario_name: str) -> dict:
    """The scenario YAML's ``datapack`` block, or {} when it has none."""
    return load_scenario_yaml(scenario_name).get("datapack") or {}


def build_scenario_world(scenario_name: str):
    """
    Load canonical graph and apply the scenario's overlay.

    A scenario with a ``datapack`` block gets an overlay built from it, so the
    World Explorer shows the disruptions the demo runs. Others use the preset
    in SCENARIO_OVERLAYS, falling back to a no-disruption overlay for unknown
    kinds. Use DATAPACK_SCENARIOS to check whether the demo controller runs a
    scenario on the DataPack world.
    """
    from maiw_world.scenario import ScenarioOverlay, ScenarioWorld
    from maiw_world.entities import EntityType

    graph = load_canonical_graph()
    warehouse_entities = graph.entities_by_type(EntityType.WAREHOUSE)
    dataset_id = warehouse_entities[0].id if warehouse_entities else CANONICAL_WAREHOUSE_ID

    raw = load_scenario_yaml(scenario_name)
    block = raw.get("datapack") or {}
    if block:
        overlay = _overlay_from_datapack_block(scenario_name, raw, block, graph, dataset_id)
        return ScenarioWorld(graph, overlay)

    overlay_kind = SCENARIO_OVERLAYS.get(scenario_name)

    if overlay_kind == "labor_constraint":
        from maiw_world.scenario import labor_constraint_scenario
        overlay = labor_constraint_scenario(graph)

    elif overlay_kind == "equipment_failure":
        from maiw_world.scenario import equipment_failure_scenario
        overlay = equipment_failure_scenario(graph)

    elif overlay_kind == "healthy_baseline" or overlay_kind is None:
        # Minimal no-disruption overlay using the warehouse entity's ID as dataset_id
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


def _overlay_from_datapack_block(scenario_name, raw, block, graph, dataset_id):
    """ScenarioOverlay for the disruptions a ``datapack`` block describes.

    Offset 0: offline equipment, absent workers and inventory quantities from
    initial_state. Later: the timed events, at their offsets from scenario
    start. Overrides and events without an overlay kind (task assignment,
    deadlines, priorities, other equipment statuses) are applied by the demo
    world but not listed in the overlay.
    """
    from maiw_world.entities import EntityType
    from maiw_world.scenario import ScenarioOverlayBuilder

    builder = ScenarioOverlayBuilder(
        scenario_id=scenario_name.replace("_", "-"),
        name=raw.get("display_name", scenario_name),
        dataset_id=dataset_id,
        description=" ".join(str(raw.get("description", "")).split()),
    ).tag(*raw.get("tags", []))

    positions: dict[str, str] | None = None

    def position_of(sku: str) -> str:
        nonlocal positions
        if positions is None:
            positions = {}
            for pos in graph.entities_by_type(EntityType.INVENTORY_POSITION):
                positions.setdefault(getattr(pos, "sku_id", ""), pos.id)
        if sku not in positions:
            raise ValueError(f"{scenario_name}: SKU {sku!r} has no DataPack inventory position")
        return positions[sku]

    initial = block.get("initial_state") or {}
    for asset_id, changes in sorted((initial.get("equipment") or {}).items()):
        if (changes or {}).get("status") == "offline":
            code = changes.get("fault_code")
            builder.equipment_failure(
                asset_id, at=0.0, label=f"{asset_id} offline" + (f" ({code})" if code else "")
            )
    for worker_id, changes in sorted((initial.get("workers") or {}).items()):
        if (changes or {}).get("status") == "on_leave":
            builder.worker_absence(worker_id, at=0.0)
    for sku, changes in sorted((initial.get("inventory") or {}).items()):
        if "quantity_available" in (changes or {}):
            builder.inventory_shock(
                position_of(sku), int(changes["quantity_available"]), at=0.0,
                label=f"{sku}: quantity {changes['quantity_available']}",
            )

    for ev in block.get("timed_events") or []:
        at = float(ev["offset_seconds"])
        payload = ev.get("payload") or {}
        kind = ev["type"]
        if kind == "equipment_fault":
            code = payload.get("fault_code") or payload.get("fault")
            builder.equipment_failure(
                payload["asset_id"], at=at,
                label=f"{payload['asset_id']} offline" + (f" ({code})" if code else ""),
            )
        elif kind == "equipment_restore":
            builder.equipment_restored(payload["asset_id"], at=at)
        elif kind == "worker_absence":
            builder.worker_absence(payload["worker_id"], at=at)
        elif kind == "worker_return":
            builder.worker_return(payload["worker_id"], at=at)
        elif kind == "low_stock":
            builder.inventory_shock(
                position_of(payload["sku"]), int(payload.get("quantity_available", 0)), at=at
            )
    return builder.build()


def read_datapack_manifest() -> dict:
    """Read manifest.json from the canonical DataPack without loading the full graph."""
    from maiw_world.datapack import WarehouseDataPack
    pack_dir = get_datapack_dir() / CANONICAL_DATASET_ID
    if not pack_dir.exists():
        return {}
    return WarehouseDataPack.read_manifest(pack_dir)
