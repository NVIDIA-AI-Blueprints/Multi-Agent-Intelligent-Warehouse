# Warehouse World Model — Phase 14A–14E

**Package:** `maiw-world` (`packages/maiw-world/`)
**Status:** Phase 14E — Canonical typed models + generated runtime architecture (stable)
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

---

## Projection Architecture (Phase 14E)

```
WarehouseWorldConfig
        ↓
WarehouseWorldGenerator  (deterministic, seed-based)
        ↓
CanonicalWarehouseGraph  (Canonical Operational Graph)
        ↓
WarehouseDataPack  (immutable, on-disk, verifiable)
        ↓
ScenarioOverlay  (disruption events — applied on top of DataPack)
        ↓
ScenarioWorld  (base_graph + ScenarioOverlay disruption events — immutable view)
        ↓
WarehouseProjectionBuilder  (at sim_time_offset)
        ├── inventory()    → InventoryProjection
        ├── labor()        → LaborProjection
        ├── equipment()    → EquipmentProjection
        └── waves()        → WaveProjection
        ↓
DemoWarehouseWorld  (mutable runtime state — rebuilt from immutable sources on reset)
        ↓
Simulation Providers  (existing, unchanged)
        ↓
WarehouseStateProvider → WarehouseState  (agent-facing contract, unchanged)
        ↓
Agents  (unaware of maiw-world)
```

**Three layers — kept explicit and separate:**

| Layer | Class | Mutable? | Purpose |
|---|---|---|---|
| DataPack | `WarehouseDataPack` (files on disk) | No | Reproducible warehouse definition |
| ScenarioWorld | `ScenarioWorld` | No | Baseline graph + overlay disruptions |
| Runtime | `DemoWarehouseWorld` | Yes | Live state after MAIW actions |

Summary:
```
DataPack          = what the warehouse is
ScenarioWorld     = what happened to it
DemoWarehouseWorld = what MAIW is currently operating on
```

**DataPack checksum** must remain unchanged throughout a demo run. All mutations happen in `DemoWarehouseWorld` only.

**Projection builder** (`WarehouseProjectionBuilder`) is the ONLY place that translates graph → domain model. Providers consume projections, not raw graph entities.

**Agents never know `maiw-world` exists.** The `WarehouseState` contract is unchanged.

---

## WarehouseDataPack

`WarehouseDataPack` is the immutable, reproducible artifact generated from a `WarehouseWorldConfig` + seed. It contains the canonical graph, entity IDs, seed, and semantic checksum. Once written, it is never mutated by a demo run.

### Immutability guarantee

A `WarehouseDataPack` is written once during world generation and read-only thereafter. The demo runtime, scenario loading, and provider initialization all read from the DataPack. No agent action, executor call, or provider write ever modifies the DataPack on disk.

### Semantic checksum

The DataPack checksum is a SHA-256 digest computed over:
- All entities (sorted by entity ID)
- All edges (sorted by edge ID)
- All operational events (sorted by event ID)

Wall-clock timestamps (e.g. file creation time) are excluded from the checksum. The same config + seed always produces the same checksum, regardless of when generation runs.

### On-disk structure

```
data/worlds/<dataset_id>/
├── manifest.json          # dataset_id, warehouse_id, seed, generated_at, entity_count, edge_count
├── checksums.json         # semantic_checksum (SHA-256), algorithm
├── graph/
│   ├── entities.jsonl     # one entity per line (newline-delimited JSON)
│   ├── edges.jsonl        # one edge per line
│   └── events.jsonl       # one operational event per line
```

### Atomic write

DataPack generation writes to a temporary directory first, then renames it into place. A partially-written DataPack is never visible to readers.

### Reload determinism

Loading the same DataPack always produces the same `CanonicalWarehouseGraph`. Entity ID assignment is stable across process restarts. The same DataPack loaded twice in the same process or in different processes produces identical graph state.

### DataPack location

The canonical DC-47 DataPack is stored at `data/worlds/dc47-demo-v1/` (committed to the repo).

Override with `MAIW_WORLD_DATAPACK_DIR` env var. Set `MAIW_WORLD_AUTO_GENERATE=true` for CI/local dev (generates on demand; never use in production).

---

## ScenarioOverlay

A `ScenarioOverlay` is an ordered list of `DisruptionEvent` records that describe what happened to the warehouse. It is applied on top of an immutable DataPack base graph to produce a `ScenarioWorld`.

### Base world + event overlay pattern

```
WarehouseDataPack (base graph — never mutated)
        +
ScenarioOverlay (disruption events)
        ↓
ScenarioWorld (immutable combined view)
```

The base graph is never mutated. ScenarioOverlay events are references into the base graph — they describe disruptions by entity ID, not by modifying entity state.

### Entity reference validation

At `ScenarioWorld` construction time, all entity IDs referenced by overlay events are validated against the base graph. A `ScenarioValidationError` is raised if an event references a non-existent entity. This prevents silent test-time mismatches when scenario definitions drift from the DataPack.

### Scenario migration status

| Scenario name | Status | Path |
|---|---|---|
| `labor_constraint_wave_risk` | DataPack-native | `labor_constraint_scenario()` overlay |
| `equipment_failure` | DataPack-native | `equipment_failure_scenario()` overlay |
| `healthy_baseline` | DataPack-native | No-disruption overlay |
| `stale_state` | Compat adapter → healthy_baseline | Maps to no-disruption overlay |
| `state_drift` | Compat adapter → healthy_baseline | Maps to no-disruption overlay |

`stale_state` and `state_drift` use the healthy_baseline overlay as a compatibility adapter. They are not fully migrated to DataPack-native overlays.

---

## Runtime Projection and Reset Semantics

### Loading a scenario (Phase 14E path)

```python
# world_loader.py entry point
from maiw_api.demo.world_loader import build_scenario_world
from maiw_api.demo.world import DemoWarehouseWorld

sw = build_scenario_world("labor_constraint_wave_risk")
world = DemoWarehouseWorld(scenario_world=sw)
# Providers wired to world as before — no changes needed
```

`DemoWarehouseWorld.__init__()` accepts an optional `ScenarioWorld` and populates its internal state from projections via `WarehouseProjectionBuilder`. Providers continue reading the same internal dict structure they always have — no provider changes were required.

### Reset semantics

```
Run starts  → DataPack + ScenarioOverlay → runtime world constructed from projections
MAIW acts   → DemoWarehouseWorld state changes (providers read/write here)
Reset       → DemoWarehouseWorld reconstructed from immutable sources
              (DataPack + ScenarioOverlay, not from a snapshot)
```

Reset does not use a snapshot of the pre-disruption state. It re-runs the projection pipeline from the original immutable DataPack + ScenarioOverlay. This guarantees that the reset world is bit-for-bit identical to the initial world regardless of how many mutations occurred during the run.

---

## Provider Integration

Providers remained unchanged through Phase 14E. The integration is:

1. `DemoWarehouseWorld.__init__(scenario_world=sw)` runs `WarehouseProjectionBuilder` at `sim_time_offset=0` and populates the internal dicts.
2. Providers (`InventorySimProvider`, `LaborSimProvider`, `EquipmentSimProvider`, `WaveSimProvider`) read from and write to those internal dicts exactly as before.
3. `ActionExecutor` mutates `DemoWarehouseWorld` through the existing provider write paths — no new write path was introduced.

The projection builder is the only translation boundary between the graph model and the provider model.

---

## Entity Identity Flow

Canonical entity IDs flow through the full stack:

```
Operational Graph (worker-042)
→ Projection (worker-042)
→ Provider (worker-042)
→ WarehouseState (worker-042)
→ Proposal/Execution (worker-042)
```

Entity IDs assigned in the DataPack are stable across reloads, resets, and across the full MAIW pipeline. This enables future Copilot context and Operational Graph → Decision Graph provenance links.

---

## Reproducibility Identity

```
dataset_id + warehouse_id + seed  →  identifies the warehouse world (DataPack)
scenario                          →  identifies the disruption overlay
trace_id                          →  identifies one MAIW reasoning/execution interaction
```

These three identity dimensions are kept separate:
- DataPack identity (`dataset_id + warehouse_id + seed`) is a property of the generated world artifact.
- Scenario identity is a property of the overlay applied on top of it.
- `trace_id` is a runtime correlation identifier that spans one OBSERVE→OUTCOME cycle. It does not identify a warehouse world or scenario.

Do not conflate DataPack identity with trace identity.

---

## Known Semantic Gap

```
KNOWN SEMANTIC GAP

TaskStatus.BLOCKED in the Operational Graph currently maps to "pending"
in DemoWarehouseWorld's runtime representation, because the demo runtime
has no BLOCKED state value.

Blocked tasks remain accessible via ScenarioWorld.blocked_tasks(at_offset).

This gap does not break any current scenario behavior. It will be
addressed if a concrete runtime need arises.
```

---

## Known Gaps (residual)

1. **No removal** — the graph is add-only. Edge expiry is expressed temporally; explicit removal is not supported.
2. **No thread safety** — the graph is not guarded by a lock. Safe for single-threaded simulation use.
3. **No cross-graph linking API** — the Operational Graph references the Decision Graph (Phase 13) only by shared IDs. A formal linking layer is deferred to a future phase.
4. **`stale_state` / `state_drift` scenarios** — these use the healthy_baseline overlay as a compatibility adapter. They are not DataPack-native overlays.
5. **Automated reconciliation trigger** — not yet implemented (operator-initiated only; see Phase 10E).
