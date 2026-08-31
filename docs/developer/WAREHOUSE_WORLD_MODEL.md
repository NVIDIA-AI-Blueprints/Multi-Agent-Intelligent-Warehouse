# Warehouse World Model — Phase 14A

**Package:** `maiw-world` (`packages/maiw-world/`)
**Status:** Phase 14A — Canonical typed models (stable)
**Dependencies:** `pydantic>=2.0` only — no maiw-agents, maiw-decision, or maiw-execution

---

## Purpose of the Operational Graph

`CanonicalWarehouseGraph` is an in-memory typed graph that represents **warehouse reality**: equipment, labor, tasks, waves, orders, inventory, and their relationships at a point in time.

It is the single authoritative typed model for what a warehouse contains and how its entities relate. Agents, skills, and tools read from the Operational Graph to reason about the current state of operations.

---

## Critical Distinction: Operational Graph vs. Decision Graph

| Dimension | Operational Graph (`maiw-world`) | Decision Graph (Phase 13) |
|---|---|---|
| **What it models** | Warehouse reality — equipment, labor, tasks, waves, inventory | MAIW reasoning — agents, skills, proposals, decisions |
| **Entity types** | Warehouse, Zone, Location, Worker, Task, Wave, Order, ... | Agent, Skill, Proposal, Decision, Constraint, ... |
| **Mutation semantics** | Add-only log (entities and events accumulate) | Append-only provenance chain |
| **Links between them** | Shared entity IDs, snapshot IDs, trace IDs | — |
| **Never merged** | True — they are separate in-memory structures | True |

Agents bridge the two graphs: they **read** the Operational Graph for context and **write** to the Decision Graph to record their reasoning.

---

## Entity Types (13)

| EntityType | Description |
|---|---|
| `WAREHOUSE` | The root facility entity |
| `ZONE` | A named area within the warehouse (picking, packing, receiving, storage, dock) |
| `LOCATION` | A specific storage slot (aisle/bay/level) within a zone |
| `WORKER` | A human employee with a role and skill set |
| `SHIFT` | A named time window (day/evening/night) with start/end hours |
| `EQUIPMENT` | A physical asset (AGV, forklift, conveyor) |
| `SKU` | A stock-keeping unit in the catalog |
| `INVENTORY_POSITION` | Quantity of a SKU at a specific location |
| `ORDER` | A customer order with priority |
| `WAVE` | A pick wave grouping tasks for parallel execution |
| `TASK` | A discrete unit of work (PICK, PACK, PUTAWAY, CYCLE_COUNT, REPLENISHMENT, INSPECTION) |
| `SHIPMENT` | An outbound shipment with carrier and tracking reference |
| `CARRIER_CUTOFF` | A carrier pickup deadline at a specific dock door |

All entities are **immutable** (`ConfigDict(frozen=True)`).
`Task` has **no `assigned_to` field** — assignments are modeled as `ASSIGNED_TO` edges.

---

## Relationship Types (13) and Compatibility Matrix

| RelationshipType | Direction | Valid Source Types | Valid Target Types |
|---|---|---|---|
| `CONTAINS` | Warehouse→Zone, Zone→Location | WAREHOUSE, ZONE | ZONE, LOCATION |
| `EMPLOYS` | Warehouse→Worker | WAREHOUSE | WORKER |
| `MEMBER_OF` | Worker→Shift | WORKER | SHIFT |
| `OPERATES` | Warehouse→Equipment | WAREHOUSE | EQUIPMENT |
| `STORES` | Warehouse→SKU (catalog) | WAREHOUSE | SKU |
| `STORED_AT` | InventoryPosition→Location | INVENTORY_POSITION | LOCATION |
| `ASSIGNED_TO` | Worker→Task (temporal) | WORKER | TASK |
| `SUPPORTS` | Equipment→Task (temporal) | EQUIPMENT | TASK |
| `BELONGS_TO` | Task→Wave | TASK | WAVE |
| `REQUIRES` | Task→SKU | TASK | SKU |
| `FULFILLS` | Wave→Order (many-to-many) | WAVE | ORDER |
| `CONSTRAINED_BY` | Wave→CarrierCutoff | WAVE | CARRIER_CUTOFF |
| `SHIPPED_VIA` | Order→Shipment | ORDER | SHIPMENT |

The compatibility matrix is enforced at `add_edge()` time. Invalid combinations raise `ValueError`.

---

## Temporal Semantics

`WarehouseEdge` supports optional `valid_from` and `valid_to` fields:

- `valid_from=None` — edge is valid from world creation (no start constraint)
- `valid_to=None` — edge is open-ended (no expiry; currently active)
- `valid_to` must be strictly after `valid_from` when both are set

### Temporal relationships

`ASSIGNED_TO` (Worker→Task) and `SUPPORTS` (Equipment→Task) are designed for temporal use:

```python
# Worker assigned to task from T0 to T1
WarehouseEdge(
    id="e-assign-1",
    source_id="worker-001",
    target_id="task-000001",
    relationship_type=RelationshipType.ASSIGNED_TO,
    valid_from=datetime(2026, 9, 1, 8, tzinfo=UTC),
    valid_to=datetime(2026, 9, 1, 10, tzinfo=UTC),
)
# Reassigned to different worker at T1 (open-ended)
WarehouseEdge(
    id="e-assign-2",
    source_id="worker-002",
    target_id="task-000001",
    relationship_type=RelationshipType.ASSIGNED_TO,
    valid_from=datetime(2026, 9, 1, 10, tzinfo=UTC),
)
```

Multiple `ASSIGNED_TO` edges for the same task are valid. The graph does not enforce single-assignment invariants — domain logic belongs in validation or agents.

### Simulation vs. wall-clock time

`valid_from`/`valid_to` and `OperationalEvent.event_time` may be **simulation time** or **wall-clock time**. The caller chooses. All datetimes must be **timezone-aware** (UTC recommended). Mixing simulation and wall-clock times in the same graph is the caller's responsibility.

### Many-to-many relationships

`FULFILLS` (Wave→Order) supports many-to-many: one wave can fulfill multiple orders, and one order may be split across multiple waves. The graph enforces no uniqueness constraint on edge endpoints — only the edge `id` must be unique.

---

## Operational Events vs. Graph Edges

| Dimension | `WarehouseEdge` | `OperationalEvent` |
|---|---|---|
| **Semantics** | Structural relationship (what IS) | Temporal occurrence (what HAPPENED) |
| **Examples** | Worker→Task ASSIGNED_TO | TASK_ASSIGNMENT event |
| **Mutable?** | No (frozen) | No (frozen) |
| **Indexed** | Yes (adjacency maps) | No (linear scan) |
| **Linked** | By entity IDs | By entity IDs |

A `TASK_ASSIGNMENT` event and an `ASSIGNED_TO` edge are separate records. An event documents that something occurred; an edge documents the resulting structural state. Both may exist for the same assignment, or only one.

---

## Validation Rules

### Graph validation (`validate_graph`) — 10 checks

| Check | Code | Severity |
|---|---|---|
| Duplicate entity ID | `DUPLICATE_ENTITY_ID` | FAIL |
| Edge source entity not in graph | `DANGLING_EDGE_SOURCE` | FAIL |
| Edge target entity not in graph | `DANGLING_EDGE_TARGET` | FAIL |
| Self-loop edge detected | `SELF_LOOP_EDGE` | WARN |
| Invalid relationship/entity-type pair | `INVALID_RELATIONSHIP_TYPE_PAIR` | FAIL |
| `valid_to` ≤ `valid_from` on edge | `INVALID_TEMPORAL_INTERVAL` | FAIL |
| Event entity_id not in graph | `EVENT_ENTITY_NOT_FOUND` | FAIL |
| InventoryPosition quantity_available < 0 | `NEGATIVE_INVENTORY_QUANTITY` | FAIL |
| Task has no BELONGS_TO edge | `TASK_NO_WAVE` | WARN |
| Location has no incoming CONTAINS edge | `ORPHANED_LOCATION` | WARN |

### Config validation (`validate_config`) — 4 checks

| Check | Code | Severity |
|---|---|---|
| `task_count` < `active_wave_count` | `INSUFFICIENT_TASK_COUNT` | FAIL |
| `location_count` < `zone_count` | `INSUFFICIENT_LOCATION_COUNT` | FAIL |
| `low_stock_pct` > 0.5 | `HIGH_LOW_STOCK_PCT` | WARN |
| `history_days` > 365 | `LARGE_HISTORY_WINDOW` | WARN |

---

## WarehouseWorldConfig — Preset Configurations

```python
WarehouseWorldConfig.dc47_demo()  # seed=42, 25k SKUs, 40w/shift, 8 AGVs, 12 forklifts
WarehouseWorldConfig.small()      # seed=1,  1k SKUs, 20w/shift, 2 AGVs, 2 forklifts
WarehouseWorldConfig.large()      # seed=99, 100k SKUs, 150w/shift, 30 AGVs, 40 forklifts
```

`warehouse_id` and `dataset_id` are required non-empty strings. The `seed` controls all downstream RNG for deterministic world generation.

---

## Known Gaps for Phase 14B+

1. **No world generator** — `WarehouseWorldConfig` is a spec; Phase 14B will add a `WorldBuilder` that produces a populated `CanonicalWarehouseGraph` from config + seed.
2. **No serialization to/from JSON** — edges and entities serialize individually (Pydantic `.model_dump()`), but there's no graph-level snapshot/restore yet.
3. **No removal** — the graph is add-only in Phase 14A. Edge expiry is expressed temporally; explicit removal is not supported.
4. **No thread safety** — the graph is not guarded by a lock. Safe for single-threaded simulation use.
5. **No index on entity type** — `entities_by_type` is O(n). Phase 14B may add a secondary index for large graphs.
6. **No cross-graph linking API** — the Operational Graph references the Decision Graph (Phase 13) only by shared IDs. A formal linking layer is deferred to Phase 14C.
7. **No `Shipment` edges in tiny_world** — `SHIPPED_VIA` is defined but not exercised in the fixture. Phase 14B scenario generators will populate shipments.
