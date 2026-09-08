# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
World inspection router — Phase 17A.

Read-only API exposing the canonical Operational Graph, DataPack metadata,
and runtime world state for the Warehouse World Explorer.

Mutation boundary: this router has GET endpoints only.
No execution, decision, approval, or orchestration imports.
"""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from maiw_api.bootstrap import MAIWRuntime, get_runtime

router = APIRouter(prefix="/api/v1/world", tags=["World"])


# ── Response models ────────────────────────────────────────────────────────────

class WorldWarehouseConfig(BaseModel):
    warehouse_id: str
    dataset_id: str
    seed: int

class WorldLayoutConfig(BaseModel):
    zone_count: int
    location_count: int
    dock_door_count: int

class WorldWorkforceConfig(BaseModel):
    workers_per_shift: int
    shift_count: int
    total_workers: int
    skills: list[str]

class WorldEquipmentConfig(BaseModel):
    agv_count: int
    forklift_count: int
    conveyor_count: int
    total: int

class WorldCommerceConfig(BaseModel):
    sku_count: int
    low_stock_pct: float
    daily_order_count: int
    lines_per_order_mean: float

class WorldOperationsConfig(BaseModel):
    active_wave_count: int
    task_count: int
    strategy: str

class WorldGenerationMeta(BaseModel):
    schema_version: str
    generator_version: str
    pack_format: str
    semantic_checksum: str | None = None
    total_entities: int
    total_edges: int
    total_events: int
    graph_available: bool

class WorldConfigResponse(BaseModel):
    warehouse: WorldWarehouseConfig
    layout: WorldLayoutConfig
    workforce: WorldWorkforceConfig
    equipment: WorldEquipmentConfig
    commerce: WorldCommerceConfig
    operations: WorldOperationsConfig
    generation: WorldGenerationMeta

class DataPackMeta(BaseModel):
    dataset_id: str
    warehouse_id: str
    seed: int
    schema_version: str
    semantic_checksum: str | None = None
    total_entities: int
    total_edges: int
    total_events: int
    pack_format: str
    generator_version: str
    immutable: bool = True
    loaded: bool

class GraphCounts(BaseModel):
    entity_counts: dict[str, int]
    relationship_counts: dict[str, int]
    total_entities: int
    total_relationships: int
    event_count: int
    available: bool

class ScenarioSummaryModel(BaseModel):
    scenario_id: str | None = None
    name: str | None = None
    severity: str | None = None
    active: bool

class RuntimeSummaryModel(BaseModel):
    status: str
    elapsed_seconds: float | None = None
    clock_iso: str | None = None

class WorldSummaryResponse(BaseModel):
    datapack: DataPackMeta
    graph: GraphCounts
    scenario: ScenarioSummaryModel
    runtime: RuntimeSummaryModel


# ── Dependency ─────────────────────────────────────────────────────────────────

async def _runtime() -> MAIWRuntime:
    return await get_runtime()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _manifest_int(manifest: dict, key: str) -> int:
    val = manifest.get(key, 0)
    if isinstance(val, int):
        return val
    if isinstance(val, dict):
        return val.get("count", 0)
    return int(val) if val else 0


def _manifest_schema_version(manifest: dict) -> str:
    """Return schema version from manifest, handling both field name variants."""
    return (
        manifest.get("maiw_world_schema_version")
        or manifest.get("schema_version")
        or "1.0"
    )


def _graph_summary(runtime: MAIWRuntime) -> dict[str, Any]:
    if runtime.world_graph is None:
        return {}
    try:
        return runtime.world_graph.summary()
    except Exception:
        return {}


def _split_summary(summary: dict) -> tuple[dict[str, int], dict[str, int], int]:
    """Split graph.summary() into entity_counts, relationship_counts, event_count."""
    entity_counts: dict[str, int] = {}
    relationship_counts: dict[str, int] = {}
    event_count = 0
    for key, val in summary.items():
        if key == "event_count":
            event_count = int(val)
        elif key.isupper() and "_" in key:
            # Relationship types are UPPER_SNAKE (e.g. CONTAINS, ASSIGNED_TO)
            relationship_counts[key] = int(val)
        else:
            entity_counts[key] = int(val)
    return entity_counts, relationship_counts, event_count


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/config", response_model=WorldConfigResponse, summary="Warehouse world configuration")
async def get_world_config(runtime: MAIWRuntime = Depends(_runtime)) -> WorldConfigResponse:
    """
    Return authoritative warehouse configuration from the canonical DataPack.

    Values come from WarehouseWorldConfig.dc47_demo() — the config used to
    generate the loaded DataPack. The DataPack is immutable once written;
    these values never change during a demo session.
    """
    from maiw_world.config import WarehouseWorldConfig
    from maiw_api.demo.world_loader import CANONICAL_WAREHOUSE_ID, CANONICAL_DATASET_ID, CANONICAL_SEED

    cfg = WarehouseWorldConfig.dc47_demo()
    manifest = runtime.world_datapack_manifest

    graph_available = runtime.world_graph is not None
    total_entities = _manifest_int(manifest, "entity_count") or (
        runtime.world_graph.entity_count if graph_available else 0
    )
    total_edges = _manifest_int(manifest, "edge_count") or (
        runtime.world_graph.edge_count if graph_available else 0
    )
    total_events = _manifest_int(manifest, "event_count") or (
        runtime.world_graph.event_count if graph_available else 0
    )
    checksum = manifest.get("semantic_checksum") or manifest.get("checksums", {}).get("semantic_checksum")

    return WorldConfigResponse(
        warehouse=WorldWarehouseConfig(
            warehouse_id=CANONICAL_WAREHOUSE_ID,
            dataset_id=CANONICAL_DATASET_ID,
            seed=CANONICAL_SEED,
        ),
        layout=WorldLayoutConfig(
            zone_count=cfg.facility.zone_count,
            location_count=cfg.facility.location_count,
            dock_door_count=cfg.facility.dock_door_count,
        ),
        workforce=WorldWorkforceConfig(
            workers_per_shift=cfg.labor.workers_per_shift,
            shift_count=cfg.labor.shift_count,
            total_workers=cfg.labor.workers_per_shift * cfg.labor.shift_count,
            skills=list(cfg.labor.skills),
        ),
        equipment=WorldEquipmentConfig(
            agv_count=cfg.equipment.agv_count,
            forklift_count=cfg.equipment.forklift_count,
            conveyor_count=cfg.equipment.conveyor_count,
            total=cfg.equipment.agv_count + cfg.equipment.forklift_count + cfg.equipment.conveyor_count,
        ),
        commerce=WorldCommerceConfig(
            sku_count=cfg.inventory.sku_count,
            low_stock_pct=cfg.inventory.low_stock_pct,
            daily_order_count=cfg.orders.daily_order_count,
            lines_per_order_mean=cfg.orders.lines_per_order_mean,
        ),
        operations=WorldOperationsConfig(
            active_wave_count=cfg.waves.active_wave_count,
            task_count=cfg.waves.task_count,
            strategy=cfg.waves.strategy,
        ),
        generation=WorldGenerationMeta(
            schema_version=_manifest_schema_version(manifest),
            generator_version=manifest.get("generator_version", "0.1.0"),
            pack_format=manifest.get("pack_format", "maiw-datapack-v1"),
            semantic_checksum=checksum,
            total_entities=total_entities,
            total_edges=total_edges,
            total_events=total_events,
            graph_available=graph_available,
        ),
    )


@router.get("/summary", response_model=WorldSummaryResponse, summary="Live world summary")
async def get_world_summary(runtime: MAIWRuntime = Depends(_runtime)) -> WorldSummaryResponse:
    """
    Return a bounded, safe world summary.

    Uses graph.summary() (entity/relationship type counts only) and manifest
    metadata — never serializes individual entities or edges.

    Immutability distinction:
      - datapack: immutable (checksum never changes during session)
      - scenario: overlay (disruption events applied at runtime)
      - runtime: mutable (workers/equipment/tasks change during demo)
    """
    manifest = runtime.world_datapack_manifest
    graph_available = runtime.world_graph is not None
    summary = _graph_summary(runtime)
    entity_counts, relationship_counts, event_count = _split_summary(summary)

    total_entities = sum(entity_counts.values()) or _manifest_int(manifest, "entity_count")
    total_relationships = sum(relationship_counts.values()) or _manifest_int(manifest, "edge_count")
    if not event_count:
        event_count = _manifest_int(manifest, "event_count")

    checksum = manifest.get("semantic_checksum") or manifest.get("checksums", {}).get("semantic_checksum")

    # ── Scenario state ─────────────────────────────────────────────────────
    scenario_summary = ScenarioSummaryModel(active=False)
    if runtime.demo_controller is not None:
        try:
            ctrl = runtime.demo_controller
            world = getattr(ctrl, "world", None)
            if world is not None:
                sw = getattr(world, "_scenario_world", None)
                if sw is not None:
                    overlay = sw.overlay
                    elapsed = getattr(getattr(world, "clock", None), "elapsed_seconds", 0.0)
                    disruptions = sw.active_disruptions(at_offset=elapsed)
                    severity = sw.disruption_severity(at_offset=elapsed)
                    scenario_summary = ScenarioSummaryModel(
                        scenario_id=overlay.scenario_id,
                        name=overlay.name,
                        severity=severity,
                        active=True,
                    )
        except Exception:
            pass

    # ── Runtime clock ──────────────────────────────────────────────────────
    runtime_summary = RuntimeSummaryModel(status="READY")
    if runtime.demo_controller is not None:
        try:
            status = runtime.demo_controller.status()
            clock = status.get("clock", {})
            runtime_summary = RuntimeSummaryModel(
                status="ACTIVE" if status.get("scenario_active") else "READY",
                elapsed_seconds=clock.get("elapsed_seconds"),
                clock_iso=clock.get("current_time"),
            )
        except Exception:
            pass

    return WorldSummaryResponse(
        datapack=DataPackMeta(
            dataset_id=manifest.get("dataset_id", "dc47-demo-v1"),
            warehouse_id=manifest.get("warehouse_id", "DC-47"),
            seed=manifest.get("seed", 42),
            schema_version=_manifest_schema_version(manifest),
            semantic_checksum=checksum,
            total_entities=total_entities,
            total_edges=total_relationships,
            total_events=event_count,
            pack_format=manifest.get("pack_format", "maiw-datapack-v1"),
            generator_version=manifest.get("generator_version", "0.1.0"),
            immutable=True,
            loaded=graph_available,
        ),
        graph=GraphCounts(
            entity_counts=entity_counts,
            relationship_counts=relationship_counts,
            total_entities=total_entities,
            total_relationships=total_relationships,
            event_count=event_count,
            available=graph_available,
        ),
        scenario=scenario_summary,
        runtime=runtime_summary,
    )
