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

import re
from collections import deque
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
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


class OverlayEventDTO(BaseModel):
    event_id: str
    event_type: str          # OverlayEventKind value
    entity_id: str
    entity_type: str         # derived from event kind
    entity_label: str        # human-readable from graph or event label
    sim_time_offset_seconds: float
    before_state: str | None = None   # BASE state
    after_state: str | None = None    # SCENARIO state
    label: str               # overlay event label
    payload: dict[str, str | int | float | bool | None] = {}

class AffectedEntityDTO(BaseModel):
    entity_id: str
    entity_type: str
    entity_label: str
    disruption_type: str     # e.g. WORKER_ABSENCE, EQUIPMENT_FAILURE
    before_state: str | None = None
    after_state: str | None = None
    severity: str | None = None

class WorldChangesResponse(BaseModel):
    warehouse_id: str
    dataset_id: str
    scenario_id: str | None
    scenario_name: str | None
    scenario_active: bool
    scenario_severity: str
    base_checksum: str | None
    world_clock_seconds: float
    overlay_event_count: int
    affected_entity_count: int
    events: list[OverlayEventDTO]
    affected_entities: list[AffectedEntityDTO]


# ── Phase 17C: Graph inspection models ────────────────────────────────────────

class GraphSearchResultDTO(BaseModel):
    entity_id: str
    entity_type: str
    label: str
    match_type: str   # EXACT_ID | EXACT_ATTRIBUTE | ENTITY_TYPE | PREFIX_ID | NAME_MATCH

class GraphSearchResponse(BaseModel):
    query: str
    results: list[GraphSearchResultDTO]

class GraphNodeDTO(BaseModel):
    entity_id: str
    entity_type: str
    label: str
    attributes_summary: dict[str, str | int | float | bool | None]
    scenario_affected: bool
    scenario_severity: str | None = None
    bfs_depth: int = 1   # 0=focus, 1=direct neighbor, 2=two-hop

class GraphEdgeDTO(BaseModel):
    edge_id: str
    source_id: str
    target_id: str
    relationship_type: str
    valid_from: str | None = None
    valid_to: str | None = None
    temporal: bool = False
    active: bool = True

class GraphEntityDetailResponse(BaseModel):
    entity_id: str
    entity_type: str
    label: str
    attributes: dict[str, str | int | float | bool | None]
    incoming_count: int
    outgoing_count: int
    scenario_affected: bool
    scenario_severity: str | None = None
    direct_relationships: list[GraphEdgeDTO]

class GraphNeighborhoodResponse(BaseModel):
    focus_entity: GraphNodeDTO
    nodes: list[GraphNodeDTO]
    edges: list[GraphEdgeDTO]
    depth: int
    entity_count: int
    relationship_count: int
    truncated: bool
    truncated_from: int | None = None
    relationship_summary: dict[str, list[str]]
    dataset_id: str
    warehouse_id: str


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


# ── Phase 17B helpers ─────────────────────────────────────────────────────────

def _event_kind_to_entity_type(kind: str) -> str:
    _MAP = {
        "WORKER_ABSENCE": "worker",
        "WORKER_RETURN": "worker",
        "LABOR_SURGE": "worker",
        "EQUIPMENT_FAILURE": "equipment",
        "EQUIPMENT_RESTORED": "equipment",
        "TASK_BLOCK": "task",
        "TASK_UNBLOCK": "task",
        "CARRIER_CUTOFF_MISS": "carrier_cutoff",
        "INVENTORY_SHOCK": "inventory_position",
        "WAVE_PRIORITY_BUMP": "wave",
    }
    return _MAP.get(kind, "unknown")


def _event_kind_to_states(kind: str) -> tuple[str | None, str | None]:
    """Return (before_state, after_state) for a given overlay event kind."""
    _STATES = {
        "WORKER_ABSENCE":       ("ACTIVE",    "ABSENT"),
        "WORKER_RETURN":        ("ABSENT",    "ACTIVE"),
        "EQUIPMENT_FAILURE":    ("AVAILABLE", "FAILED"),
        "EQUIPMENT_RESTORED":   ("FAILED",    "AVAILABLE"),
        "TASK_BLOCK":           ("READY",     "BLOCKED"),
        "TASK_UNBLOCK":         ("BLOCKED",   "READY"),
        "CARRIER_CUTOFF_MISS":  ("AT_RISK",   "MISSED"),
        "INVENTORY_SHOCK":      ("NORMAL",    "SHOCK"),
        "WAVE_PRIORITY_BUMP":   ("PLANNING",  "ACTIVE"),
        "LABOR_SURGE":          (None,        "SURGE"),
    }
    return _STATES.get(kind, (None, None))


def _entity_label(graph: Any, entity_id: str, fallback: str = "") -> str:
    """Derive a human-readable label for an entity from the canonical graph."""
    if graph is None:
        return fallback or entity_id
    try:
        ent = graph.get_entity(entity_id)
        if ent is None:
            return fallback or entity_id
        etype = getattr(ent, "entity_type", None)
        if etype is not None:
            etype_val = etype.value if hasattr(etype, "value") else str(etype)
            if etype_val == "worker":
                return getattr(ent, "full_name", None) or getattr(ent, "username", entity_id)
            if etype_val == "equipment":
                eq_type = getattr(ent, "equipment_type", "")
                eq_type_val = eq_type.value if hasattr(eq_type, "value") else str(eq_type)
                model = getattr(ent, "model", "")
                return f"{eq_type_val.upper()} {entity_id}" + (f" ({model})" if model else "")
            if etype_val == "task":
                task_type = getattr(ent, "task_type", "")
                task_type_val = task_type.value if hasattr(task_type, "value") else str(task_type)
                return f"{task_type_val} {entity_id}"
            if etype_val == "wave":
                wave_num = getattr(ent, "wave_number", "")
                return f"Wave {wave_num}"
            if etype_val == "carrier_cutoff":
                carrier = getattr(ent, "carrier", "")
                return f"{carrier} cutoff" if carrier else entity_id
    except Exception:
        pass
    return fallback or entity_id


def _build_event_dto(event: Any, graph: Any) -> OverlayEventDTO:
    kind = event.kind.value if hasattr(event.kind, "value") else str(event.kind)
    before, after = _event_kind_to_states(kind)
    label = _entity_label(graph, event.entity_id, fallback=event.label or event.entity_id)
    return OverlayEventDTO(
        event_id=event.event_id,
        event_type=kind,
        entity_id=event.entity_id,
        entity_type=_event_kind_to_entity_type(kind),
        entity_label=label,
        sim_time_offset_seconds=event.sim_time_offset_seconds,
        before_state=before,
        after_state=after,
        label=event.label or f"{kind}: {event.entity_id}",
        payload=dict(event.payload),
    )


def _affected_entity_severity(kind: str) -> str | None:
    _SEV = {
        "EQUIPMENT_FAILURE":   "HIGH",
        "CARRIER_CUTOFF_MISS": "CRITICAL",
        "WORKER_ABSENCE":      "MODERATE",
        "TASK_BLOCK":          "MODERATE",
        "INVENTORY_SHOCK":     "MODERATE",
    }
    return _SEV.get(kind)


# ── Phase 17C: Graph inspection helpers ───────────────────────────────────────

def _entity_label_full(entity: Any) -> str:
    """Full human-readable label for graph display — used in all graph endpoints."""
    et = entity.entity_type.value if hasattr(entity.entity_type, "value") else str(entity.entity_type)
    if et == "worker":
        return getattr(entity, "full_name", None) or entity.id
    if et == "wave":
        num = getattr(entity, "wave_number", None)
        return f"Wave {num}" if num is not None else entity.id
    if et == "equipment":
        eq_type = getattr(entity, "equipment_type", None)
        type_str = eq_type.value.upper() if hasattr(eq_type, "value") else str(eq_type).upper() if eq_type else ""
        model = getattr(entity, "model", "") or ""
        suffix = f" ({model})" if model else ""
        return f"{type_str} {entity.id}{suffix}" if type_str else entity.id
    if et == "task":
        task_type = getattr(entity, "task_type", None)
        type_str = task_type.value if hasattr(task_type, "value") else str(task_type) if task_type else ""
        return f"{type_str} {entity.id}" if type_str else entity.id
    if et == "carrier_cutoff":
        carrier = getattr(entity, "carrier", "") or ""
        return f"{carrier} cutoff" if carrier else entity.id
    if et == "warehouse":
        return getattr(entity, "name", entity.id) or entity.id
    if et == "zone":
        code = getattr(entity, "zone_code", "") or ""
        return f"Zone {code}" if code else entity.id
    if et == "order":
        ref = getattr(entity, "order_reference", "") or ""
        return f"Order {ref}" if ref else entity.id
    if et == "sku":
        return getattr(entity, "name", entity.id) or entity.id
    if et == "location":
        code = getattr(entity, "location_code", "") or ""
        return f"Loc {code}" if code else entity.id
    return entity.id


def _entity_attributes_summary(entity: Any) -> dict[str, str | int | float | bool | None]:
    """3-5 key display attributes per entity type for the graph canvas node."""
    et = entity.entity_type.value if hasattr(entity.entity_type, "value") else str(entity.entity_type)

    def _v(attr: str, default: Any = None) -> Any:
        val = getattr(entity, attr, default)
        if val is None:
            return None
        if hasattr(val, "value"):
            return val.value
        if isinstance(val, list):
            return ", ".join(str(i) for i in val) if val else ""
        return val

    if et == "worker":
        return {"role": _v("role"), "skills": _v("skills")}
    if et == "wave":
        return {"wave_number": _v("wave_number"), "status": _v("status"), "strategy": _v("strategy")}
    if et == "equipment":
        return {"equipment_type": _v("equipment_type"), "model": _v("model", "")}
    if et == "task":
        return {"task_type": _v("task_type"), "status": _v("status"), "priority": _v("priority")}
    if et == "zone":
        return {"zone_code": _v("zone_code"), "zone_type": _v("zone_type")}
    if et == "location":
        return {"location_code": _v("location_code"), "aisle": _v("aisle")}
    if et == "warehouse":
        return {"name": _v("name"), "timezone": _v("timezone")}
    if et == "carrier_cutoff":
        ct = _v("cutoff_time")
        return {"carrier": _v("carrier"), "cutoff_time": ct.isoformat() if hasattr(ct, "isoformat") else str(ct) if ct else None}
    if et == "order":
        return {"order_reference": _v("order_reference"), "priority": _v("priority")}
    if et == "sku":
        return {"name": _v("name"), "category": _v("category")}
    if et == "shift":
        return {"shift_name": _v("shift_name"), "start_hour": _v("start_hour"), "end_hour": _v("end_hour")}
    return {}


def _entity_attributes_full(entity: Any) -> dict[str, str | int | float | bool | None]:
    """All serializable attributes for the entity detail panel."""
    result: dict[str, str | int | float | bool | None] = {}
    skip = {"id", "entity_type"}
    try:
        for k, v in entity.model_dump().items():
            if k in skip:
                continue
            if v is None:
                result[k] = None
            elif isinstance(v, (str, int, float, bool)):
                result[k] = v
            elif isinstance(v, list):
                result[k] = ", ".join(str(i) for i in v) if v else ""
            elif hasattr(v, "value"):
                result[k] = v.value
            elif hasattr(v, "isoformat"):
                result[k] = v.isoformat()
            else:
                result[k] = str(v)
    except Exception:
        pass
    return result


def _scenario_affected_map(runtime: MAIWRuntime) -> dict[str, str]:
    """Returns {entity_id: severity} for all scenario-affected entities."""
    try:
        ctrl = runtime.demo_controller
        if not ctrl or not getattr(ctrl, "active", False):
            return {}
        world = getattr(ctrl, "world", None)
        if not world:
            return {}
        sw = getattr(world, "_scenario_world", None)
        if not sw:
            return {}
        result: dict[str, str] = {}
        for ev in sw.overlay.events:
            if ev.entity_id not in result:
                kind = ev.kind.value if hasattr(ev.kind, "value") else str(ev.kind)
                result[ev.entity_id] = _affected_entity_severity(kind) or "LOW"
        return result
    except Exception:
        return {}


def _build_node_dto(entity: Any, scenario_map: dict[str, str], bfs_depth: int = 1) -> GraphNodeDTO:
    sev = scenario_map.get(entity.id)
    return GraphNodeDTO(
        entity_id=entity.id,
        entity_type=entity.entity_type.value,
        label=_entity_label_full(entity),
        attributes_summary=_entity_attributes_summary(entity),
        scenario_affected=entity.id in scenario_map,
        scenario_severity=sev,
        bfs_depth=bfs_depth,
    )


def _build_edge_dto_graph(edge: Any) -> GraphEdgeDTO:
    """Build a GraphEdgeDTO from a WarehouseEdge."""
    temporal_rels = {"ASSIGNED_TO", "SUPPORTS"}
    rel = edge.relationship_type.value if hasattr(edge.relationship_type, "value") else str(edge.relationship_type)
    temporal = rel in temporal_rels
    vf = edge.valid_from
    vt = edge.valid_to
    active = vt is None  # open-ended edges are active
    return GraphEdgeDTO(
        edge_id=edge.id,
        source_id=edge.source_id,
        target_id=edge.target_id,
        relationship_type=rel,
        valid_from=vf.isoformat() if vf else None,
        valid_to=vt.isoformat() if vt else None,
        temporal=temporal,
        active=active,
    )


def _bounded_bfs(
    graph: Any,
    focus_id: str,
    depth: int,
    max_entities: int,
    max_relationships: int,
) -> tuple[list[tuple[Any, int]], int, list[Any]]:
    """
    BFS from focus_id returning capped neighbors with their BFS depth.

    Returns:
        (neighbor_pairs, total_available, edges)
        neighbor_pairs = [(entity, bfs_depth), ...] capped at max_entities
        total_available = uncapped neighbor count (for truncated flag)
        edges = edges between nodes in the capped set, capped at max_relationships
    """
    visited: dict[str, int] = {focus_id: 0}
    queue: deque[tuple[str, int]] = deque([(focus_id, 0)])
    ordered: list[tuple[Any, int]] = []

    while queue:
        current_id, current_depth = queue.popleft()
        if current_depth >= depth:
            continue
        neighbor_ids: set[str] = set()
        for edge in graph.outgoing_edges(current_id):
            neighbor_ids.add(edge.target_id)
        for edge in graph.incoming_edges(current_id):
            neighbor_ids.add(edge.source_id)
        for nid in sorted(neighbor_ids):
            if nid not in visited:
                visited[nid] = current_depth + 1
                entity = graph.get_entity(nid)
                if entity is not None:
                    ordered.append((entity, current_depth + 1))
                queue.append((nid, current_depth + 1))

    total_available = len(ordered)
    # Stable order: (bfs_depth, entity_type, entity_id)
    ordered_sorted = sorted(ordered, key=lambda x: (x[1], x[0].entity_type.value, x[0].id))
    capped = ordered_sorted[:max_entities]

    # Edges where both endpoints are in capped set (including focus)
    capped_ids = {focus_id} | {e[0].id for e in capped}
    edges: list[Any] = []
    seen_edges: set[str] = set()
    focus_entity = graph.get_entity(focus_id)
    all_in_set = ([focus_entity] if focus_entity else []) + [e[0] for e in capped]
    for entity in all_in_set:
        for edge in graph.outgoing_edges(entity.id):
            if edge.id not in seen_edges and edge.target_id in capped_ids:
                edges.append(edge)
                seen_edges.add(edge.id)
        if len(edges) >= max_relationships:
            break

    return capped, total_available, edges[:max_relationships]


_ENTITY_TYPE_KEYWORDS: dict[str, str] = {
    "warehouse": "warehouse", "zone": "zone", "location": "location",
    "worker": "worker", "workers": "worker", "shift": "shift",
    "equipment": "equipment", "agv": "equipment", "forklift": "equipment", "conveyor": "equipment",
    "sku": "sku", "skus": "sku", "wave": "wave", "waves": "wave",
    "task": "task", "tasks": "task", "order": "order", "orders": "order",
    "carrier": "carrier_cutoff", "carrier_cutoff": "carrier_cutoff", "cutoff": "carrier_cutoff",
}
_EQUIP_SUBTYPES = {"agv", "forklift", "conveyor"}


def _graph_search(q: str, graph: Any, limit: int) -> list[GraphSearchResultDTO]:
    """
    Search the canonical graph. Reuses same canonical ID semantics as Copilot.

    Priority: EXACT_ID > wave/canonical resolution > ENTITY_TYPE keyword > PREFIX_ID > NAME_MATCH
    """
    from maiw_world.entities import EntityType

    results: list[GraphSearchResultDTO] = []
    seen: set[str] = set()
    q = q.strip()
    if not q:
        return results

    q_lower = q.lower()

    def add(entity: Any, match_type: str) -> None:
        if entity.id in seen or len(results) >= limit:
            return
        seen.add(entity.id)
        results.append(GraphSearchResultDTO(
            entity_id=entity.id,
            entity_type=entity.entity_type.value,
            label=_entity_label_full(entity),
            match_type=match_type,
        ))

    # 1. Exact entity ID
    e = graph.get_entity(q)
    if e:
        add(e, "EXACT_ID")

    # 2. Wave number reference ("Wave 17", "wave 17", "wave-017")
    wave_m = re.search(r"\bwave\s*[-_]?(\d+)\b", q_lower)
    if wave_m and len(results) < limit:
        num = int(wave_m.group(1))
        canonical = f"wave-{num:03d}"
        cw = graph.get_entity(canonical)
        if cw:
            add(cw, "EXACT_ID")
        else:
            for w in graph.entities_by_type(EntityType.WAVE):
                if getattr(w, "wave_number", None) == num:
                    add(w, "EXACT_ATTRIBUTE")
                    break

    # 3. Entity type keyword → list instances
    if len(results) < limit:
        matched_type_str = _ENTITY_TYPE_KEYWORDS.get(q_lower)
        if matched_type_str:
            try:
                et = EntityType(matched_type_str)
                candidates = graph.entities_by_type(et)
                if q_lower in _EQUIP_SUBTYPES:
                    candidates = [
                        c for c in candidates
                        if getattr(getattr(c, "equipment_type", None), "value", "") == q_lower
                    ]
                for c in sorted(candidates, key=lambda x: x.id):
                    add(c, "ENTITY_TYPE")
                    if len(results) >= limit:
                        break
            except ValueError:
                pass

    # 4. Prefix match on entity IDs (deterministic: sorted)
    if len(results) < limit:
        for et in EntityType:
            for e in sorted(graph.entities_by_type(et), key=lambda x: x.id):
                if len(results) >= limit:
                    break
                if e.id.lower().startswith(q_lower):
                    add(e, "PREFIX_ID")

    # 5. Worker full_name contains query
    if len(results) < limit:
        for w in sorted(graph.entities_by_type(EntityType.WORKER), key=lambda x: x.id):
            if len(results) >= limit:
                break
            fn = (getattr(w, "full_name", "") or "").lower()
            if q_lower in fn:
                add(w, "NAME_MATCH")

    return results[:limit]


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


@router.get("/changes", response_model=WorldChangesResponse, summary="Scenario overlay changes")
async def get_world_changes(runtime: MAIWRuntime = Depends(_runtime)) -> WorldChangesResponse:
    """
    Return the current scenario overlay as a bounded, typed response.

    Immutability invariant: base_checksum equals runtime.world_datapack_manifest
    semantic_checksum — DataPack is never modified by scenario activation.

    Returns a degraded response (scenario_active=False, empty events) when:
    - No scenario is active
    - Scenario used the legacy YAML path (no ScenarioWorld)
    - DataPack not loaded
    """
    manifest = runtime.world_datapack_manifest
    base_checksum = manifest.get("semantic_checksum")
    graph = runtime.world_graph
    warehouse_id = manifest.get("warehouse_id", "DC-47")
    dataset_id = manifest.get("dataset_id", "dc47-demo-v1")

    # ── No controller / no scenario ───────────────────────────────────────────
    if runtime.demo_controller is None or not runtime.demo_controller.active:
        return WorldChangesResponse(
            warehouse_id=warehouse_id,
            dataset_id=dataset_id,
            scenario_id=None,
            scenario_name=None,
            scenario_active=False,
            scenario_severity="NOMINAL",
            base_checksum=base_checksum,
            world_clock_seconds=0.0,
            overlay_event_count=0,
            affected_entity_count=0,
            events=[],
            affected_entities=[],
        )

    world = runtime.demo_controller.world
    elapsed = float(world.clock.elapsed_seconds)
    scenario_world = getattr(world, "_scenario_world", None)

    # ── Overlay not available (legacy YAML path) ──────────────────────────────
    if scenario_world is None:
        return WorldChangesResponse(
            warehouse_id=warehouse_id,
            dataset_id=dataset_id,
            scenario_id=None,
            scenario_name=runtime.demo_controller.scenario_name,
            scenario_active=True,
            scenario_severity="UNKNOWN",
            base_checksum=base_checksum,
            world_clock_seconds=elapsed,
            overlay_event_count=0,
            affected_entity_count=0,
            events=[],
            affected_entities=[],
        )

    overlay = scenario_world.overlay
    severity = scenario_world.disruption_severity(at_offset=elapsed)

    # ── Build event DTOs — temporal order ────────────────────────────────────
    sorted_events = sorted(overlay.events, key=lambda e: (e.sim_time_offset_seconds, e.event_id))
    event_dtos = [_build_event_dto(ev, graph) for ev in sorted_events]

    # ── Affected entities — deduplicated ─────────────────────────────────────
    seen_entity: dict[str, AffectedEntityDTO] = {}
    for ev in sorted_events:
        eid = ev.entity_id
        if eid in seen_entity:
            continue
        kind = ev.kind.value if hasattr(ev.kind, "value") else str(ev.kind)
        before, after = _event_kind_to_states(kind)
        seen_entity[eid] = AffectedEntityDTO(
            entity_id=eid,
            entity_type=_event_kind_to_entity_type(kind),
            entity_label=_entity_label(graph, eid, fallback=ev.label or eid),
            disruption_type=kind,
            before_state=before,
            after_state=after,
            severity=_affected_entity_severity(kind),
        )

    return WorldChangesResponse(
        warehouse_id=warehouse_id,
        dataset_id=dataset_id,
        scenario_id=overlay.scenario_id,
        scenario_name=overlay.name,
        scenario_active=True,
        scenario_severity=severity,
        base_checksum=base_checksum,
        world_clock_seconds=elapsed,
        overlay_event_count=len(overlay.events),
        affected_entity_count=len(seen_entity),
        events=event_dtos,
        affected_entities=list(seen_entity.values()),
    )


# ── Phase 17C: Graph inspection endpoints ─────────────────────────────────────

@router.get("/graph/search", response_model=GraphSearchResponse, summary="Search entities in the operational graph")
async def search_graph_entities(
    q: str = Query(..., min_length=1, max_length=200, description="Entity search query (name, type, or ID prefix)"),
    limit: int = Query(default=10, ge=1, le=20, description="Max results"),
    runtime: MAIWRuntime = Depends(_runtime),
) -> GraphSearchResponse:
    """
    Search the canonical Operational Graph by name, type keyword, or ID prefix.

    Examples: 'Wave 17', 'worker', 'agv', 'sku', 'task-000042', 'Jane'.
    Uses the same canonical entity-ID semantics as Copilot context resolution.
    GET-only — no graph mutations possible.
    """
    graph = runtime.world_graph
    if graph is None:
        raise HTTPException(status_code=503, detail="Operational graph not available")
    results = _graph_search(q, graph, limit)
    return GraphSearchResponse(query=q, results=results)


@router.get("/graph/entity/{entity_id}", response_model=GraphEntityDetailResponse, summary="Entity detail")
async def get_graph_entity(
    entity_id: str,
    runtime: MAIWRuntime = Depends(_runtime),
) -> GraphEntityDetailResponse:
    """
    Return full detail for a single canonical entity.

    Includes type-specific attributes, relationship counts, bounded direct edges,
    and current scenario annotation if an overlay is active.
    GET-only.
    """
    graph = runtime.world_graph
    if graph is None:
        raise HTTPException(status_code=503, detail="Operational graph not available")
    entity = graph.get_entity(entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")

    scenario_map = _scenario_affected_map(runtime)
    outgoing = graph.outgoing_edges(entity_id)
    incoming = graph.incoming_edges(entity_id)
    direct_edges = (outgoing + incoming)[:100]

    return GraphEntityDetailResponse(
        entity_id=entity.id,
        entity_type=entity.entity_type.value,
        label=_entity_label_full(entity),
        attributes=_entity_attributes_full(entity),
        incoming_count=len(incoming),
        outgoing_count=len(outgoing),
        scenario_affected=entity_id in scenario_map,
        scenario_severity=scenario_map.get(entity_id),
        direct_relationships=[_build_edge_dto_graph(e) for e in direct_edges],
    )


@router.get("/graph/neighbors/{entity_id}", response_model=GraphNeighborhoodResponse, summary="Bounded entity neighborhood")
async def get_graph_neighbors(
    entity_id: str,
    depth: int = Query(default=1, ge=1, le=2, description="BFS depth — server clamps to 2"),
    max_entities: int = Query(default=50, ge=1, le=50, description="Max neighbor entities — server clamps to 50"),
    max_relationships: int = Query(default=100, ge=1, le=100, description="Max edges — server clamps to 100"),
    runtime: MAIWRuntime = Depends(_runtime),
) -> GraphNeighborhoodResponse:
    """
    Return a bounded BFS neighborhood for an entity.

    Hard server caps: depth≤2, entities≤50, edges≤100.
    Client parameters are clamped — the full DataPack is never returned.

    When truncated=true, truncated_from shows how many neighbors exist before the cap.
    """
    graph = runtime.world_graph
    if graph is None:
        raise HTTPException(status_code=503, detail="Operational graph not available")
    focus = graph.get_entity(entity_id)
    if focus is None:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")

    # Server-side hard clamp (Query validators already enforce the max, but belt+suspenders)
    depth = min(depth, 2)
    max_entities = min(max_entities, 50)
    max_relationships = min(max_relationships, 100)

    scenario_map = _scenario_affected_map(runtime)
    manifest = runtime.world_datapack_manifest

    capped, total_available, edges = _bounded_bfs(graph, entity_id, depth, max_entities, max_relationships)

    focus_dto = _build_node_dto(focus, scenario_map, bfs_depth=0)
    node_dtos = [_build_node_dto(e, scenario_map, bfs_depth=d) for e, d in capped]
    edge_dtos = [_build_edge_dto_graph(e) for e in edges]

    # Relationship summary: entity_type_group → [label, ...]
    rel_summary: dict[str, list[str]] = {}
    for edge in edges:
        other_id = edge.target_id if edge.source_id == entity_id else edge.source_id
        if other_id == entity_id:
            continue
        other = graph.get_entity(other_id)
        if other is None:
            continue
        group = other.entity_type.value.replace("_", " ").title() + "s"
        label = _entity_label_full(other)
        rel_summary.setdefault(group, [])
        if label not in rel_summary[group]:
            rel_summary[group].append(label)

    return GraphNeighborhoodResponse(
        focus_entity=focus_dto,
        nodes=node_dtos,
        edges=edge_dtos,
        depth=depth,
        entity_count=len(capped),
        relationship_count=len(edges),
        truncated=total_available > max_entities,
        truncated_from=total_available if total_available > max_entities else None,
        relationship_summary=rel_summary,
        dataset_id=manifest.get("dataset_id", "dc47-demo-v1"),
        warehouse_id=manifest.get("warehouse_id", "DC-47"),
    )


# ── Phase 17D: LIVE world models ──────────────────────────────────────────────

class ChangedFieldDTO(BaseModel):
    field: str
    before_value: str | int | float | bool | None
    after_value: str | int | float | bool | None


class ChangedEntityDTO(BaseModel):
    entity_id: str
    entity_type: str          # "worker" | "task"
    label: str
    changed_fields: list[ChangedFieldDTO]
    note: str = "changed from scenario initial state"


class LiveSummaryDTO(BaseModel):
    workers: int
    idle_workers: int
    equipment: int
    available_equipment: int
    tasks: int
    pending_tasks: int
    in_progress_tasks: int


class LastExecutionDTO(BaseModel):
    execution_id: str | None = None
    trace_id: str | None = None
    outcome: str = "UNKNOWN"   # EXECUTED | FAILED | UNKNOWN | REJECTED | PENDING
    pre_kpi: dict | None = None
    post_kpi: dict | None = None
    kpi_delta: dict | None = None


class WorldLiveResponse(BaseModel):
    warehouse_id: str
    dataset_id: str
    base_checksum: str | None
    scenario_id: str | None
    scenario_active: bool
    runtime_status: str        # IDLE | ACTIVE | PAUSED
    world_clock: str | None    # ISO-8601 current simulation time
    summary: LiveSummaryDTO
    changed_entities: list[ChangedEntityDTO]
    last_execution: LastExecutionDTO | None


# ── Phase 17D: helpers ────────────────────────────────────────────────────────

def _compute_changed_entities(world: Any, snapshot: dict | None, graph: Any) -> list[ChangedEntityDTO]:
    """
    Compare current world.workers / world.tasks against the scenario initial
    snapshot.  Returns a list of entities with at least one changed field.
    Labels "changed from scenario initial state" — NOT relative to last execution.
    """
    if snapshot is None:
        return []

    result: list[ChangedEntityDTO] = []
    snap_workers: dict = snapshot.get("workers", {})
    snap_tasks: dict = snapshot.get("tasks", {})

    for worker_id, worker in world.workers.items():
        snap_w = snap_workers.get(worker_id)
        if snap_w is None:
            continue
        changed_fields: list[ChangedFieldDTO] = []
        if worker.status != snap_w.status:
            changed_fields.append(ChangedFieldDTO(
                field="status",
                before_value=snap_w.status,
                after_value=worker.status,
            ))
        if worker.current_task_id != snap_w.current_task_id:
            changed_fields.append(ChangedFieldDTO(
                field="current_task_id",
                before_value=snap_w.current_task_id,
                after_value=worker.current_task_id,
            ))
        if changed_fields:
            label = worker.full_name or worker.username or worker_id
            # Prefer canonical graph label if graph is available
            if graph is not None:
                label = _entity_label(graph, worker_id, fallback=label)
            result.append(ChangedEntityDTO(
                entity_id=worker_id,
                entity_type="worker",
                label=label,
                changed_fields=changed_fields,
            ))

    for task_id, task in world.tasks.items():
        snap_t = snap_tasks.get(task_id)
        if snap_t is None:
            continue
        changed_fields = []
        if task.status != snap_t.status:
            changed_fields.append(ChangedFieldDTO(
                field="status",
                before_value=snap_t.status,
                after_value=task.status,
            ))
        if task.assigned_to != snap_t.assigned_to:
            changed_fields.append(ChangedFieldDTO(
                field="assigned_to",
                before_value=snap_t.assigned_to,
                after_value=task.assigned_to,
            ))
        if changed_fields:
            label = f"{task.task_type} {task_id}"
            if graph is not None:
                label = _entity_label(graph, task_id, fallback=label)
            result.append(ChangedEntityDTO(
                entity_id=task_id,
                entity_type="task",
                label=label,
                changed_fields=changed_fields,
            ))

    return result


def _build_last_execution(ctrl: Any) -> LastExecutionDTO | None:
    """Extract last execution record from the controller. Returns None if no execution."""
    rec = getattr(ctrl, "_last_execution_record", None)
    if rec is None:
        return None
    return LastExecutionDTO(
        execution_id=rec.get("execution_id"),
        trace_id=rec.get("trace_id"),
        outcome=rec.get("outcome", "UNKNOWN"),
        pre_kpi=rec.get("pre_kpi"),
        post_kpi=rec.get("post_kpi"),
        kpi_delta=rec.get("kpi_delta"),
    )


# ── Phase 17D: LIVE endpoint ──────────────────────────────────────────────────

@router.get("/live", response_model=WorldLiveResponse, summary="LIVE runtime world state")
async def get_world_live(runtime: MAIWRuntime = Depends(_runtime)) -> WorldLiveResponse:
    """
    Return the LIVE mutable runtime state of the warehouse simulation.

    Polls-safe for 15-second intervals from the World Explorer LIVE view.

    Immutability:
    - base_checksum: DataPack checksum — never changes during session
    - changed_entities: entities that differ from scenario initial state
      (labeled 'changed from scenario initial state')
    - last_execution: populated only after execution completes;
      None = no execution has run since last start/reset

    Read-only boundary: no governance, execution, or orchestration symbols
    are imported by this router.  GET-only.
    """
    manifest = runtime.world_datapack_manifest
    base_checksum = manifest.get("semantic_checksum") or manifest.get("checksums", {}).get("semantic_checksum")
    warehouse_id = manifest.get("warehouse_id", "DC-47")
    dataset_id = manifest.get("dataset_id", "dc47-demo-v1")
    graph = runtime.world_graph

    ctrl = runtime.demo_controller
    if ctrl is None or not ctrl.active:
        return WorldLiveResponse(
            warehouse_id=warehouse_id,
            dataset_id=dataset_id,
            base_checksum=base_checksum,
            scenario_id=None,
            scenario_active=False,
            runtime_status="IDLE",
            world_clock=None,
            summary=LiveSummaryDTO(
                workers=0,
                idle_workers=0,
                equipment=0,
                available_equipment=0,
                tasks=0,
                pending_tasks=0,
                in_progress_tasks=0,
            ),
            changed_entities=[],
            last_execution=None,
        )

    world = ctrl.world

    # ── Scenario identity ─────────────────────────────────────────────────────
    scenario_id: str | None = None
    scenario_active = ctrl.active
    sw = getattr(world, "_scenario_world", None)
    if sw is not None:
        try:
            scenario_id = sw.overlay.scenario_id
        except Exception:
            pass

    # ── Runtime status ────────────────────────────────────────────────────────
    if getattr(ctrl, "_paused", False):
        runtime_status = "PAUSED"
    elif ctrl.active:
        runtime_status = "ACTIVE"
    else:
        runtime_status = "IDLE"

    # ── World clock ───────────────────────────────────────────────────────────
    try:
        world_clock = world.clock.now().isoformat()
    except Exception:
        world_clock = None

    # ── Live summary — direct counts from world ────────────────────────────────
    workers_list = list(world.workers.values())
    equipment_list = list(world.equipment.values())
    tasks_list = list(world.tasks.values())

    idle_workers = sum(
        1 for w in workers_list if w.status == "active" and w.current_task_id is None
    )
    summary = LiveSummaryDTO(
        workers=len(workers_list),
        idle_workers=idle_workers,
        equipment=len(equipment_list),
        available_equipment=sum(1 for e in equipment_list if e.status == "available"),
        tasks=len(tasks_list),
        pending_tasks=sum(1 for t in tasks_list if t.status == "pending"),
        in_progress_tasks=sum(1 for t in tasks_list if t.status == "in_progress"),
    )

    # ── Changed entities — compare current vs snapshot ────────────────────────
    snapshot = getattr(ctrl, "_snapshot", None)
    changed_entities = _compute_changed_entities(world, snapshot, graph)

    # ── Last execution record ─────────────────────────────────────────────────
    last_execution = _build_last_execution(ctrl)

    return WorldLiveResponse(
        warehouse_id=warehouse_id,
        dataset_id=dataset_id,
        base_checksum=base_checksum,
        scenario_id=scenario_id,
        scenario_active=scenario_active,
        runtime_status=runtime_status,
        world_clock=world_clock,
        summary=summary,
        changed_entities=changed_entities,
        last_execution=last_execution,
    )

# ── Phase 17E: Operational Context Snapshot (historical context) ──────────────

class ContextSnapshotNodeDTO(BaseModel):
    entity_id: str
    entity_type: str
    label: str
    attributes: dict[str, Any]

class ContextSnapshotEdgeDTO(BaseModel):
    source_id: str
    target_id: str
    relationship_type: str
    valid_from: str | None = None
    valid_to: str | None = None

class OperationalContextSnapshotResponse(BaseModel):
    """
    Exact operational context snapshot for one historical Copilot turn.

    This is what MAIW actually saw at decision time — not a reconstruction.
    """
    context_snapshot_id: str
    conversation_id: str
    turn_id: str
    trace_id: str
    warehouse_id: str
    dataset_id: str
    datapack_checksum: str
    warehouse_state_snapshot_id: str | None = None
    focus_entity_id: str
    focus_entity_type: str
    focus_label: str
    depth: int
    truncated: bool
    nodes: list[ContextSnapshotNodeDTO]
    edges: list[ContextSnapshotEdgeDTO]
    entity_count: int
    relationship_count: int
    relationship_summary: dict[str, list[str]]
    captured_at: str
    # Lifecycle note
    store_note: str = "Snapshot is process-local; not persisted across API restart."


# ── Phase 17F: paginated entity browser ───────────────────────────────────────

VALID_ENTITY_TYPES = {
    "Warehouse", "Zone", "Location", "Worker", "Equipment",
    "SKU", "InventoryPosition", "Order", "Wave", "Task",
    "CarrierCutoff", "Shift",
}

class EntityBrowserItemDTO(BaseModel):
    entity_id: str
    entity_type: str
    label: str
    key_state: dict[str, str | int | float | bool | None]

class EntityPageResponse(BaseModel):
    items: list[EntityBrowserItemDTO]
    total: int
    limit: int
    offset: int
    has_more: bool
    entity_type_filter: str | None


def _entity_key_state(entity: Any) -> dict[str, str | int | float | bool | None]:
    """Return the single most-relevant state field for the entity browser list."""
    et = entity.entity_type.value if hasattr(entity.entity_type, "value") else str(entity.entity_type)
    def _v(attr: str) -> Any:
        val = getattr(entity, attr, None)
        if val is None:
            return None
        if hasattr(val, "value"):
            return val.value
        return val

    if et == "worker":
        return {"status": _v("status"), "role": _v("role")}
    if et == "equipment":
        return {"status": _v("status"), "equipment_type": _v("equipment_type")}
    if et == "task":
        return {"status": _v("status"), "task_type": _v("task_type"), "priority": _v("priority")}
    if et == "wave":
        return {"wave_number": _v("wave_number"), "status": _v("status")}
    if et == "order":
        return {"priority": _v("priority"), "order_reference": _v("order_reference")}
    if et == "sku":
        return {"category": _v("category")}
    if et == "inventory_position":
        return {"on_hand": _v("on_hand"), "reserved": _v("reserved")}
    if et == "zone":
        return {"zone_type": _v("zone_type")}
    if et == "location":
        return {"location_code": _v("location_code")}
    if et == "carrier_cutoff":
        ct = _v("cutoff_time")
        return {"carrier": _v("carrier"), "cutoff_time": ct.isoformat() if hasattr(ct, "isoformat") else str(ct) if ct else None}
    return {}


@router.get(
    "/graph/entities",
    response_model=EntityPageResponse,
    summary="Paginated entity browser (bounded to 50 per page)",
)
async def get_graph_entities(
    entity_type: str | None = Query(default=None, description="Filter by entity type (e.g. Worker, Wave, Task)"),
    limit: int = Query(default=20, ge=1, le=50, description="Page size — server hard max is 50"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    runtime: MAIWRuntime = Depends(_runtime),
) -> EntityPageResponse:
    """
    Return a bounded, paginated list of entities from the canonical Operational Graph.

    Hard server cap: limit ≤ 50. Never returns the full 25k entity set.
    Supports filtering by entity_type (case-insensitive).
    Each item includes entity_id, entity_type, label, and key_state summary.

    Use GET /graph/entity/{id} or GET /graph/neighbors/{id} for full entity detail.

    GET-only. No graph mutations.
    """
    from maiw_world.entities import EntityType

    graph = runtime.world_graph
    if graph is None:
        raise HTTPException(status_code=503, detail="Operational graph not available")

    # Clamp limit server-side regardless of Query validation
    limit = min(limit, 50)

    # Resolve entity type filter
    et_filter: "EntityType | None" = None
    if entity_type:
        # Normalize: accept "Worker" or "worker"
        et_lower = entity_type.lower().replace(" ", "_")
        try:
            et_filter = EntityType(et_lower)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown entity_type '{entity_type}'. "
                       f"Valid types: {', '.join(sorted(VALID_ENTITY_TYPES))}",
            )

    if et_filter is not None:
        all_entities = sorted(graph.entities_by_type(et_filter), key=lambda e: e.id)
    else:
        all_entities = []
        for et in EntityType:
            all_entities.extend(graph.entities_by_type(et))
        all_entities = sorted(all_entities, key=lambda e: (e.entity_type.value, e.id))

    total = len(all_entities)
    page = all_entities[offset : offset + limit]

    items = [
        EntityBrowserItemDTO(
            entity_id=e.id,
            entity_type=e.entity_type.value,
            label=_entity_label_full(e),
            key_state=_entity_key_state(e),
        )
        for e in page
    ]

    return EntityPageResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
        entity_type_filter=et_filter.value if et_filter else None,
    )


# ── Phase 17F: context snapshot list ─────────────────────────────────────────

class ContextSnapshotListItemDTO(BaseModel):
    context_snapshot_id: str
    turn_id: str
    trace_id: str
    focus_entity_id: str
    focus_entity_type: str
    focus_label: str
    entity_count: int
    captured_at: str
    truncated: bool


class ContextSnapshotListResponse(BaseModel):
    snapshots: list[ContextSnapshotListItemDTO]
    total: int
    store_note: str = "Snapshots are process-local; cleared on API restart or demo reset."


@router.get(
    "/context/snapshots",
    response_model=ContextSnapshotListResponse,
    summary="List all in-memory operational context snapshots (newest first)",
)
async def list_context_snapshots(
    runtime: MAIWRuntime = Depends(_runtime),
) -> ContextSnapshotListResponse:
    """
    Return a bounded list of all captured OperationalContextSnapshots.

    These are the exact bounded graph contexts supplied to Copilot/agent turns.
    Sorted newest first.  Deduplicated by turn_id (each turn produces one snapshot).

    Use GET /context/by-turn/{turn_id} to fetch full snapshot detail.

    GET-only.  No governance, execution, or orchestration symbols imported.
    """
    svc = getattr(runtime, "copilot_service", None)
    if svc is None:
        # No copilot service — return empty list (degraded but not 503)
        return ContextSnapshotListResponse(snapshots=[], total=0)

    store = getattr(svc, "store", None)
    if store is None:
        return ContextSnapshotListResponse(snapshots=[], total=0)

    # Deduplicate: _context_snapshots is keyed by both turn_id AND context_snapshot_id
    # Collect only unique snapshots via context_snapshot_id dedup
    raw: dict = getattr(store, "_context_snapshots", {})
    seen_ids: set[str] = set()
    unique: list = []
    for snap in raw.values():
        cid = snap.context_snapshot_id
        if cid not in seen_ids:
            seen_ids.add(cid)
            unique.append(snap)

    # Sort newest first
    unique.sort(key=lambda s: s.captured_at, reverse=True)

    items = [
        ContextSnapshotListItemDTO(
            context_snapshot_id=s.context_snapshot_id,
            turn_id=s.turn_id,
            trace_id=s.trace_id,
            focus_entity_id=s.focus_entity_id,
            focus_entity_type=s.focus_entity_type,
            focus_label=s.focus_label,
            entity_count=s.entity_count,
            captured_at=s.captured_at,
            truncated=s.truncated,
        )
        for s in unique
    ]

    return ContextSnapshotListResponse(
        snapshots=items,
        total=len(items),
    )


@router.get(
    "/context/by-turn/{turn_id}",
    response_model=OperationalContextSnapshotResponse,
    summary="Exact operational context snapshot for a historical Copilot turn",
)
async def get_context_by_turn(
    turn_id: str,
    runtime: MAIWRuntime = Depends(_runtime),
) -> OperationalContextSnapshotResponse:
    """
    Return the exact operational context snapshot captured for a specific Copilot turn.

    This is what MAIW actually saw at decision time — the bounded graph neighborhood
    that was assembled BEFORE the model call.  It is never reconstructed: if this
    endpoint returns data, it reflects the exact context supplied to reasoning.

    Phase 17E: OPERATIONAL CONTEXT AT DECISION TIME
    - Linked to turn_id, trace_id, and warehouse_state_snapshot_id
    - Immutable after capture — LIVE mutations do NOT change this snapshot
    - Returns 404 when turn_id is unknown or no snapshot was captured (e.g. degraded turn)

    GET-only.  No governance, execution, or orchestration symbols imported.
    """
    svc = getattr(runtime, "copilot_service", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="Copilot service not available")

    store = getattr(svc, "store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Copilot store not available")

    snapshot = store.get_context_snapshot_by_turn(turn_id)
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=f"No operational context snapshot found for turn '{turn_id}'. "
                   "This turn may not have been grounded, or the snapshot was not captured.",
        )

    return OperationalContextSnapshotResponse(
        context_snapshot_id=snapshot.context_snapshot_id,
        conversation_id=snapshot.conversation_id,
        turn_id=snapshot.turn_id,
        trace_id=snapshot.trace_id,
        warehouse_id=snapshot.warehouse_id,
        dataset_id=snapshot.dataset_id,
        datapack_checksum=snapshot.datapack_checksum,
        warehouse_state_snapshot_id=snapshot.warehouse_state_snapshot_id,
        focus_entity_id=snapshot.focus_entity_id,
        focus_entity_type=snapshot.focus_entity_type,
        focus_label=snapshot.focus_label,
        depth=snapshot.depth,
        truncated=snapshot.truncated,
        nodes=[
            ContextSnapshotNodeDTO(
                entity_id=n.entity_id,
                entity_type=n.entity_type,
                label=n.label,
                attributes=n.attributes,
            )
            for n in snapshot.nodes
        ],
        edges=[
            ContextSnapshotEdgeDTO(
                source_id=e.source_id,
                target_id=e.target_id,
                relationship_type=e.relationship_type,
                valid_from=e.valid_from,
                valid_to=e.valid_to,
            )
            for e in snapshot.edges
        ],
        entity_count=snapshot.entity_count,
        relationship_count=snapshot.relationship_count,
        relationship_summary=snapshot.relationship_summary,
        captured_at=snapshot.captured_at,
    )
