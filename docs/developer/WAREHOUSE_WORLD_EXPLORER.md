# Warehouse World Explorer — Phase 17 Developer Reference

**Status:** Phase 17F — Complete (Workstream 2 close)
**UI path:** WORLD tab in DemoShell
**API prefix:** `GET /api/v1/world/*`

---

## Architecture Overview

```
WarehouseWorldConfig (WarehouseWorldConfig.dc47_demo())
        │
        ▼
WarehouseWorldGenerator (deterministic, seed=42)
        │
        ▼
WarehouseDataPack (immutable, on-disk, verifiable)
        │ dataset_id="dc47-demo-v1"
        │ warehouse_id="DC-47"
        │ seed=42
        │ semantic_checksum=<sha256, invariant>
        │
        ├──► CanonicalWarehouseGraph (in-memory, read-only)
        │           │
        │           ├── Entities (Warehouse, Zone, Location, Worker,
        │           │            Equipment, SKU, InventoryPosition,
        │           │            Order, Wave, Task, CarrierCutoff)
        │           └── Edges (CONTAINS, ASSIGNED_TO, LOCATED_IN, ...)
        │
        └──► ScenarioOverlay (deterministic, scenario-specific events)
                    │
                    ▼
             ScenarioWorld (BASE graph + overlay = SCENARIO view)
                    │
                    ▼ (scenario start → DemoController.start())
             DemoWarehouseWorld (mutable runtime operational state)
                    │
                    ├── workers: {id → WorkerState}
                    ├── tasks:   {id → TaskState}
                    └── equipment: {id → EquipmentState}
                                │
                                ▼ (Copilot grounding)
                     OperationalContextSnapshot
                     (exact bounded neighborhood at decision time)
                                │
                                ▼ (action approval + execution)
                     WarehouseState delta (LIVE world changes)
```

---

## BASE / SCENARIO / LIVE Model

These three terms are distinct and must not be confused.

| Term | Source | Mutable? | Invariant |
|------|---------|----------|-----------|
| **BASE** | WarehouseDataPack canonical graph | No — immutable once generated | `semantic_checksum` never changes |
| **SCENARIO** | BASE + ScenarioOverlay events applied | No — overlay is deterministic | BASE checksum unchanged; overlay is additive |
| **LIVE** | DemoWarehouseWorld runtime state | Yes — mutates on execution | Workers/tasks change; checksum still unchanged |

**Key invariant:** BASE semantic_checksum does not change during scenario activation,
runtime execution, or reset. It is a fingerprint of the DataPack content, not of the
runtime state.

---

## Provenance Chain

```
DataPack (semantic_checksum=X, immutable)
    │
    │── Turn 1: "Why is Wave 17 at risk?"
    │       │
    │       ├── OperationalContextSnapshot (captured BEFORE model call)
    │       │     context_snapshot_id, turn_id, trace_id
    │       │     datapack_checksum=X (same immutable checksum)
    │       │     nodes=[Wave 17, Worker A, Worker B, ...]
    │       │     edges=[ASSIGNED_TO, ...]
    │       │     ← CONTEXT AT DECISION TIME
    │       │
    │       └── DecisionGraph node (reasoning provenance)
    │               trace_id (same trace_id links to snapshot)
    │
    │── Turn 2: "What should we do? Do it."
    │       │
    │       ├── GovernedAction → ApprovalRecord → ExecutionRecord
    │       │
    │       └── WarehouseState delta:
    │               WorkerA.status: "absent" → "active"
    │               TaskX.assigned_to: null → "worker-A"
    │
    └── LIVE world now reflects execution delta
            DataPack checksum still = X
            CURRENT OPERATIONAL CONTEXT (reconstructed now)
            ≠ CONTEXT AT DECISION TIME (exact stored snapshot)
```

---

## Operational Graph vs. Decision Graph

| Dimension | Operational Graph | Decision Graph |
|---|---|---|
| **What it models** | Warehouse reality | MAIW reasoning provenance |
| **Entity types** | Worker, Wave, Task, Equipment, SKU, ... | Agent, Skill, Proposal, Decision, Constraint, ... |
| **Linked by** | focus_entity_id, context_snapshot_id | trace_id, context_snapshot_id |
| **Mutates?** | BASE never; LIVE yes (on execution) | Append-only |
| **Inspector** | NodeInspector (WorldGraph) | DecisionGraph component |

They are separate in-memory structures linked by:
- `trace_id` (one per governed turn)
- `context_snapshot_id` (DecisionGraph → exact historical context)
- Canonical entity IDs (shared vocabulary)

---

## API Reference

All routes are GET-only. No WORLD route executes, approves, mutates, or resets state.

### GET /api/v1/world/config
Purpose: Canonical warehouse configuration from WarehouseWorldConfig.dc47_demo().
Bounds: Structured metadata only. No entity lists.
Typical payload: ~800 bytes.

### GET /api/v1/world/summary
Purpose: Live world summary — DataPack metadata, graph type counts, scenario state, runtime clock.
Bounds: Type counts only (e.g. {"Worker": 90, "Wave": 20}). No individual entities.
Typical payload: ~600 bytes.

### GET /api/v1/world/changes
Purpose: Current scenario overlay — events and affected entities.
Bounds: All overlay events for the active scenario. Returns scenario_active=false gracefully.
Typical payload: ~3–8 KB (bounded by overlay size, not DataPack size).

### GET /api/v1/world/live
Purpose: LIVE runtime world state — counts, changed entities, last execution KPI delta.
Bounds: Only entities that differ from scenario initial state. No full entity dump.
Poll interval: Safe at 15-second intervals.
Typical payload: ~2–5 KB.

### GET /api/v1/world/graph/search?q=&limit=
Purpose: Search the canonical Operational Graph by name, type, or ID prefix.
Bounds: limit ≤ 20 results.
Examples: q=Wave 17, q=worker, q=agv, q=task-000042, q=Jane.
Typical payload: ~1–3 KB.

### GET /api/v1/world/graph/entity/{entity_id}
Purpose: Full detail for one canonical entity — attributes, relationship counts, direct edges.
Bounds: Direct edges capped at 100.
Typical payload: ~2–4 KB.

### GET /api/v1/world/graph/neighbors/{entity_id}
Purpose: Bounded BFS neighborhood for an entity.
Hard caps: depth ≤ 2, entities ≤ 50, edges ≤ 100.
Returns: truncated=true with truncated_from when BFS exceeds cap.
Typical payload (Wave 17 depth=1): ~8–15 KB.

### GET /api/v1/world/graph/entities?entity_type=&limit=&offset=  [Phase 17F]
Purpose: Paginated entity browser. Developer surface for systematic entity inspection.
Hard cap: limit ≤ 50 per page. Never returns full 25k entity set.
Params: entity_type (optional filter), limit (default 20, max 50), offset (default 0).
Returns: {items, total, limit, offset, has_more, entity_type_filter}.
Each item: entity_id, entity_type, label, key_state (status/role summary fields).
Typical payload (20 workers): ~3–5 KB.

### GET /api/v1/world/context/by-turn/{turn_id}
Purpose: Exact operational context snapshot for a historical Copilot turn.
Semantics: This is what MAIW actually saw at decision time — the bounded graph
neighborhood assembled BEFORE the model call. Never reconstructed.
Returns 404: When turn_id unknown or turn was not grounded.
Typical payload: ~5–15 KB (≤50 nodes, ≤100 edges).

### GET /api/v1/world/context/snapshots  [Phase 17F]
Purpose: List all in-memory captured OperationalContextSnapshots, newest first.
Bounds: Process-local; cleared on API restart or demo reset.
Deduplicated: By context_snapshot_id.
Returns: {snapshots: [...], total, store_note}.
Each item: context_snapshot_id, turn_id, trace_id, focus_entity_id,
           focus_entity_type, focus_label, entity_count, captured_at, truncated.
Typical payload: ~1–3 KB.

---

## RAW Tab — Developer Inspection Surface (Phase 17F)

The RAW tab provides three bounded developer sections:

### MANIFEST
- All DataPack identity fields: dataset_id, warehouse_id, seed, schema_version,
  semantic_checksum, entity_count, edge_count, event_count, generator_version, pack_format
- Collapsible raw JSON view
- Source: GET /world/config

### ENTITIES
- Paginated entity browser, max 50 per page
- Entity type filter (Warehouse/Zone/Location/Worker/Equipment/SKU/
  InventoryPosition/Order/Wave/Task/CarrierCutoff)
- Selecting a row opens the existing NodeInspector (reused — no duplicate inspector)
- Source: GET /world/graph/entities

### CONTEXT SNAPSHOTS
- List of all captured OperationalContextSnapshots, newest first
- Selecting a row navigates to the CONTEXT tab for full historical snapshot view
- Source: GET /world/context/snapshots

What RAW does NOT expose:
- Full DataPack JSONL (the raw parquet/JSONL files)
- All 25k entities in one response
- Mutation controls

---

## Navigation Flows

All flows preserve: conversation_id, scenario state, approval state, execution state, trace state.

| Flow | Steps |
|------|-------|
| OPERATIONS → WORLD | Click WORLD tab in DemoShell mode switcher |
| Copilot → WORLD/GRAPH | VIEW OPERATIONAL CONTEXT → WorldShell auto-switches to GRAPH tab |
| Copilot → WORLD/CONTEXT | VIEW CONTEXT AT DECISION TIME → WorldShell auto-switches to CONTEXT tab |
| WORLD CONTEXT → Decision Trace | VIEW DECISION TRACE in WorldContextSnapshot |
| Decision Graph → Operational Context | VIEW OPERATIONAL CONTEXT in DecisionGraph trace panel |
| WORLD → Copilot | RETURN TO COPILOT button (preserved in WorldGraph) |
| RAW → CONTEXT | Click snapshot row in RAW tab → auto-switches to CONTEXT tab |

No historical typewriter replay on any navigation.

---

## Terminology Reference

| Term | Meaning | Where shown |
|------|---------|-------------|
| BASE | Immutable DataPack canonical graph | CHANGES tab, OVERVIEW card |
| SCENARIO | BASE + overlay disruption events | CHANGES tab, graph CHANGED badges |
| LIVE | Mutable runtime operational state | LIVE view, LIVE overview section |
| CONTEXT AT DECISION TIME | Exact stored OperationalContextSnapshot | CONTEXT tab, Copilot turn button |
| CURRENT OPERATIONAL CONTEXT | Neighborhood reconstructed now from live graph | WorldGraph provenance banner |
| DECISION GRAPH | Reasoning/action provenance chain | DecisionGraph component |

---

## DataPack Immutability

The semantic_checksum in the DataPack manifest is a SHA-256 hash of canonical entity
content. Computed at generation time and never recomputed during a session.

Proof: All four endpoints return the same value regardless of scenario or execution:
  GET /world/config       → generation.semantic_checksum
  GET /world/changes      → base_checksum
  GET /world/live         → base_checksum
  GET /world/context/...  → datapack_checksum

---

## Developer Setup Journey

  01 CONFIGURE  — WarehouseWorldConfig.dc47_demo() defines the warehouse
  02 GENERATE   — Run: maiw-world generate --preset dc47-demo (seed=42, ~700ms)
  03 VALIDATE   — CanonicalWarehouseGraph loads from DataPack; checksum verified
  04 EXPLORE    — Open WORLD: OVERVIEW, GRAPH, CHANGES, RAW tabs
  05 DISRUPT    — Start scenario "labor_constraint_wave_risk" → CHANGES shows overlay
  06 OPERATE    — Copilot: "Why is Wave 17 at risk?" → grounded answer + context snapshot
  07 OBSERVE    — Copilot: "Do it." → execution → LIVE world shows delta

---

## Architecture Invariants

1. All GET /api/v1/world/* endpoints are read-only — no POST, PATCH, DELETE
2. world.py router does not import: ActionExecutor, DecisionEngine, ApprovalStore,
   GovernedActionOrchestrator
3. semantic_checksum is identical across config, changes, live, and context endpoints
4. Historical OperationalContextSnapshot is immutable after capture — LIVE mutations do not affect it
5. BFS neighborhood hard-capped at 50 entities, 100 edges (server-enforced)
6. Entity page hard-capped at 50 per request (server-enforced)
7. No WORLD UI surface shows APPLY, EXECUTE, RETRY, or AUTHORIZE buttons
8. Context snapshots are process-local — not persisted across API restart
