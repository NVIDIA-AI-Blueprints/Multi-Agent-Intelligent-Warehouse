# WarehouseState — Operational Context Assembly

## Purpose

`WarehouseState` is the **operational context** that agents receive before reasoning, not a storage schema.  
Agents declare what they need via `StateRequirements`; `WarehouseStateProvider` assembles only those components by calling existing Skills (which call MCP capabilities).

The state is then **sealed** into an immutable `WarehouseStateSnapshot` before being passed to the `DecisionEngine` for proposal evaluation.

```
Agent request
    │
    ▼
StateRequirements (declare what's needed)
    │
    ▼
WarehouseStateProvider.get_state()
    │  ┌────────────────────────────────┐
    ├──► EquipmentStatusSkill.execute() │  (if equipment=True)
    │  └────────────────────────────────┘
    │  ┌────────────────────────────────┐
    └──► InventoryLookupSkill.execute() │  (if inventory=True)
       └────────────────────────────────┘
    │
    ▼
WarehouseState (assembled, mutable)
    │
    ▼
WarehouseStateSnapshot.seal()  ← assigns UUID, freezes for DecisionEngine
```

## Packages

| Package | Responsibility |
|---------|----------------|
| `packages/maiw-state/` | State models, freshness, provenance, provider |
| `packages/maiw-decision/` | Evaluates proposals against snapshots |
| `src/api/skills/` | Concrete skill implementations (app layer) |

**Dependency DAG**: `maiw-mcp` ← `maiw-state` ← `maiw-decision`  
`src/api/` imports from `maiw-state`; `maiw-state` never imports from `src/api/`.

## State Assembly

### StateRequirements

Agents declare what they need before state is assembled:

```python
from maiw_state import StateRequirements

req = StateRequirements(
    equipment=True,
    equipment_asset_id="FL-001",   # optional: scope to one asset
    inventory=False,
    max_age_ms=30_000,             # freshness threshold
)
```

Fields that are `False` or `None` are not fetched — no unnecessary capability calls.

### WarehouseStateProvider

```python
from maiw_state import WarehouseStateProvider

provider = WarehouseStateProvider(
    equipment_status_skill=equipment_status_skill,  # injected, not imported
    inventory_skill=inventory_skill,
)
state = await provider.get_state("warehouse-001", requirements)
```

Skills are injected at construction time.  `WarehouseStateProvider` accepts any object satisfying the `_EquipmentStatusSkillProto` or `_InventorySkillProto` structural protocols — no import of concrete skill classes.

If a skill raises, `StateAssemblyError` is propagated immediately with the failing domain name and the underlying cause.

## Freshness

Every state component carries a `StateFreshness` object:

```python
class StateFreshness(BaseModel):
    observed_at: datetime     # when the data was fetched
    age_ms: int | None        # milliseconds since observed_at
    stale: bool               # age_ms > stale_after_ms
    stale_after_ms: int       # threshold (default 30 000 ms)
```

`StateFreshness.now()` creates a fresh marker with `age_ms=0`.  
`StateFreshness.from_observed_at(ts)` computes age against the current UTC clock and sets `stale=True` if over the threshold.

## Provenance

Each populated domain adds a `StateProvenance` entry to `WarehouseState.provenance`:

```python
class StateProvenance(BaseModel):
    domain: str           # "equipment" | "inventory"
    capability: str       # "warehouse.equipment.get_status"
    server: str           # "equipment-mcp"
    provider: str         # class name of the concrete provider
    source: StateSource   # MCP | DIRECT_DB | CACHE | MOCK
    observed_at: datetime
    latency_ms: float | None
```

This allows agents and auditors to trace exactly where each state component came from.

## Snapshot Semantics

```python
snapshot = WarehouseStateSnapshot.seal(state)
# snapshot.snapshot_id  — UUID
# snapshot.created_at   — UTC timestamp of sealing
# snapshot.state        — copy of WarehouseState
```

Sealing is cheap — it wraps the state object and assigns a UUID.  The snapshot is **not a deep copy**; the `state` object should not be mutated after sealing.

Helpers on the snapshot:

```python
snapshot.equipment_age_ms()   # → int | None
snapshot.is_equipment_stale() # → bool
```

## Current State Domains

| Domain | Model | Source Capability |
|--------|-------|-------------------|
| `equipment` | `EquipmentState` | `warehouse.equipment.get_status` |
| `inventory` | `InventoryState` | `warehouse.inventory.get` |
| `waves` | *(planned)* | — |
| `labor` | *(planned)* | — |
| `orders` | *(planned)* | — |
| `docks` | *(planned)* | — |

## Errors

| Exception | When raised |
|-----------|-------------|
| `StateAssemblyError` | Skill not configured or capability call fails |
| `StateFreshnessError` | Caller explicitly checks and rejects stale state |

`StateFreshnessError` is not raised automatically by `WarehouseStateProvider` — the `DecisionEngine` raises equivalent `REQUIRES_FRESH_STATE` outcomes instead.

## Adding a New Domain

1. Create `packages/maiw-state/maiw_state/models/<domain>.py` with `<Domain>State` model
2. Add `<domain>: <Domain>State | None = None` to `WarehouseState`
3. Add `<domain>: bool = False` and filter fields to `StateRequirements`
4. Add a skill protocol to `provider.py` and a `_assemble_<domain>()` method
5. Update `WarehouseStateProvider.get_state()` to call the new assembler
6. Export the new model from `maiw_state/__init__.py`
