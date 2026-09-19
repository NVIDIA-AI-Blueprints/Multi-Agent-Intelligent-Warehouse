# MAIW Warehouse World

**Version:** MAIW v2
**Status:** AUTHORITATIVE
**Diagram:** [docs/architecture/diagrams/maiw-runtime-pipeline.png](diagrams/maiw-runtime-pipeline.png)

---

## Overview

The Warehouse World is MAIW's deterministic synthetic warehouse environment used for
development, demo, and evaluation. It provides a reproducible, layered simulation
that agents consume through the same `WarehouseState` contracts they always have —
agents do not know `maiw-world` exists.

For the full developer reference, see [docs/developer/WAREHOUSE_WORLD_MODEL.md](../developer/WAREHOUSE_WORLD_MODEL.md).

---

## Generation Path

```
WarehouseWorldConfig
    ↓
WarehouseWorldGenerator  (deterministic, seed-based)
    ↓
Canonical Operational Graph
  (13 entity types, 13 relationship types, 11 operational event types)
  (Worker → Task → Wave → Order → CarrierCutoff)
    ↓
WarehouseDataPack  (immutable, on-disk, verifiable)
  data/worlds/<dataset_id>/
    ↓
ScenarioOverlay  (deterministic disruption events)
    ↓
ScenarioWorld  (base + overlay, immutable view)
    ↓
DemoWarehouseWorld  (mutable runtime execution world)
    ↓
Simulation Providers (unchanged by world model)
    ↓
WarehouseStateProvider → WarehouseState → Agents
```

---

## Three-State Distinction

| State | Object | Mutability | Description |
|-------|--------|------------|-------------|
| **BASE** | `WarehouseDataPack` | Immutable | On-disk, checksummed artifact from `WarehouseWorldGenerator`. Contains the canonical graph. Never mutated by a demo run. Identified by `dataset_id + warehouse_id + seed`. |
| **SCENARIO** | `ScenarioWorld` | Immutable | DataPack base graph + deterministic event overlay. Validates entity references at construction. Does not modify the DataPack. |
| **LIVE** | `DemoWarehouseWorld` | Mutable | Runtime execution world. Derived from DataPack + ScenarioOverlay at scenario start. Reset reconstructs from immutable sources — not from a snapshot. |

```
DataPack           = what the warehouse is
ScenarioWorld      = what happened to it
DemoWarehouseWorld = what MAIW is currently operating on
```

**Key invariant:** The mutable runtime is derived from immutable sources, not the other way
around. Agents consume `WarehouseState`; they do not know the world model exists.

---

## Reproducibility Identity

Three independent identity dimensions:

```
dataset_id + warehouse_id + seed  →  identifies the warehouse world (DataPack)
scenario                          →  identifies the disruption overlay
trace_id                          →  identifies one MAIW reasoning/execution interaction
```

`trace_id` is a runtime correlation identifier. It does not identify a warehouse world
or scenario. These three dimensions are never merged.

---

## Operational Graph vs. Decision Graph

These are separate models that share canonical IDs as linking artifacts:

```
Operational Graph  = warehouse reality and operational context
                     entities: Worker, Task, Wave, Order, Location, Equipment, …
                     relationships: assigned_to, belongs_to, scheduled_for, …

Decision Graph     = MAIW reasoning and decision provenance
                     Evidence → Assessment → Recommendation → Proposal
                     → Decision → Approval → Execution → Outcome
```

They are never merged into a single structure.

---

## OperationalContextSnapshot

Each Copilot turn that reaches a model produces one `OperationalContextSnapshot`.
It is a first-class concept in MAIW.

**Capture:** Before the model call — not reconstructed afterward.

**Identity fields:**
- `context_snapshot_id` — unique snapshot identifier
- `turn_id` — the Copilot turn that triggered this snapshot
- `trace_id` — the broader operational trace
- `datapack_checksum` — links to the immutable `semantic_checksum` of the DataPack

**Immutability:** After capture, LIVE mutations do not change historical snapshots.
The exact context the model saw is preserved, regardless of subsequent warehouse mutations.

**Access:**
- WORLD tab → CONTEXT sub-tab in the Warehouse World Explorer UI
- `GET /api/v1/world/context/snapshots` — list all snapshots
- `GET /api/v1/world/context/by-turn/{turn_id}` — exact snapshot for a given turn

**Why it matters:**
- **Exact bounded context** — developers can inspect precisely what the model saw
- **Provenance** — traces back to the immutable DataPack via `datapack_checksum`
- **Reproducibility** — the context is preserved for historical inspection
- **Debugging** — mismatched outcomes can be diagnosed against the captured context

---

## Warehouse World Explorer UI

The Warehouse World Explorer is the operational observability UI at the WORLD tab.
It exposes read-only inspection of the entire lifecycle — from DataPack through LIVE state.

| Tab | Purpose |
|-----|---------|
| **OVERVIEW** | Warehouse identity (`dataset_id`, `seed`, `semantic_checksum`), entity counts, scenario summary |
| **CHANGES** | Scenario overlay events and affected-entity list (BASE → SCENARIO transitions) |
| **GRAPH** | Search-first entity browser backed by the Canonical Operational Graph |
| **LIVE** | Runtime state delta — field-level changes from governed execution (before/after KPIs) |
| **RAW** | Paginated entity browser; hard cap of 50 entities per page |
| **CONTEXT** | OperationalContextSnapshot list; exact bounded context captured before each model call |

---

## WORLD API

All World Explorer data is served at `GET /api/v1/world/*` (read-only).
The router imports no execution, decision, approval, or orchestration symbols.

| Route | Purpose |
|-------|---------|
| `GET /world/config` | Warehouse identity, config, DataPack checksum |
| `GET /world/summary` | Live entity counts, scenario state |
| `GET /world/changes` | Scenario overlay events |
| `GET /world/live` | LIVE runtime delta with KPI before/after |
| `GET /world/graph/search` | Entity search |
| `GET /world/graph/entity/{id}` | Single entity detail + direct edges |
| `GET /world/graph/neighbors/{id}` | Bounded BFS neighborhood (truncated to 50 nodes) |
| `GET /world/graph/entities` | Paginated entity browser (hard cap: 50 per page) |
| `GET /world/context/snapshots` | List all `OperationalContextSnapshot` objects |
| `GET /world/context/by-turn/{turn_id}` | Exact snapshot for a Copilot turn |
