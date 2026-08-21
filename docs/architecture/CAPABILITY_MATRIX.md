# MAIW Capability Matrix

**Phase:** 8  
**Date:** 2026-08-20  
**Baseline:** 483 passed, 1 skipped (CORE CI)  
**Domains:** 4 (Inventory, Equipment, Labor, Wave)  
**Capabilities:** 12 total (7 read-only, 5 write)

---

## Overview

Every interaction between the agent layer and a backend system passes through a named
MCP capability.  Each capability has a fixed risk tier, a side-effect category, and an
explicit permission token.  This document is the single authoritative catalog.

The platform boundary is always:

```
STATE → REASON → PROPOSE → DECIDE → EXECUTE → MCP → BACKEND
```

No capability bypasses this boundary.  Proposal skills are local (no MCP call).
Only `*ActionExecutor` classes reach write capabilities, and only after the 4-guard check:
APPROVED → binding → allowlist → staleness.

---

## Legend

| Column | Meaning |
|--------|---------|
| **Capability** | Semantic MCP tool name (`warehouse.<domain>.<verb>`) |
| **Risk** | `read_only` / `low` / `medium` / `high` |
| **Side-effect** | `read` / `write` |
| **Requires approval** | Must the DecisionEngine return APPROVED before execution? |
| **Idempotent** | Safe to retry? |
| **Proposal skill** | Local skill that builds ActionProposal (no MCP call) |
| **Execution skill** | Skill that calls MCP (read: any time; write: only via executor) |
| **Executor** | ActionExecutor subclass that owns write dispatch |
| **MCP server** | File in `mcp_servers/` |
| **State component** | Field in `WarehouseState` |

---

## Inventory Domain

| Capability | Risk | Side-effect | Req. approval | Idempotent | Proposal skill | Exec skill | Executor | MCP server | State component |
|---|---|---|---|---|---|---|---|---|---|
| `warehouse.inventory.get` | read_only | read | No | Yes | — | `InventoryLookupSkill` | — | `mcp_servers/inventory` | `InventoryState` |
| `warehouse.inventory.locate` | read_only | read | No | Yes | — | `InventoryLookupSkill` | — | `mcp_servers/inventory` | `InventoryState` |

**Permission token:** `inventory:read`  
**State model:** `InventoryState` (items, low_stock_count)  
**Proposal factory:** *(none — inventory is read-only)*  
**Executor:** *(none — inventory has no write capabilities)*  
**Note:** Inventory is the only read-only domain. No ActionProposal is ever generated for inventory.

---

## Equipment Domain

| Capability | Risk | Side-effect | Req. approval | Idempotent | Proposal skill | Exec skill | Executor | MCP server | State component |
|---|---|---|---|---|---|---|---|---|---|
| `warehouse.equipment.get_status` | read_only | read | No | Yes | — | `EquipmentStatusSkill` | — | `mcp_servers/equipment` | `EquipmentState` |
| `warehouse.equipment.assign` | medium | write | Yes | No | `EquipmentAssignmentSkill` | `ExecuteEquipmentAssignSkill` | `EquipmentActionExecutor` | `mcp_servers/equipment` | `EquipmentState` |
| `warehouse.equipment.release` | low | write | No | Yes | *(factory)* | `ExecuteEquipmentReleaseSkill` | `EquipmentActionExecutor` | `mcp_servers/equipment` | `EquipmentState` |
| `warehouse.equipment.schedule_maintenance` | medium | write | Yes | No | *(factory)* | `ExecuteMaintenanceSkill` | `EquipmentActionExecutor` | `mcp_servers/equipment` | `EquipmentState` |

**Permission token:** `equipment:execute`  
**State model:** `EquipmentState` (assets, available_count, summary)  
**Proposal factories:** `ActionProposal.for_equipment_assign()`, `for_equipment_release()`, `for_schedule_maintenance()`  
**Executor:** `EquipmentActionExecutor` — `_ALLOWED_ACTIONS = {assign, release, schedule_maintenance}`  
**State property:** `EquipmentState.find_asset(asset_id)`

---

## Labor Domain

| Capability | Risk | Side-effect | Req. approval | Idempotent | Proposal skill | Exec skill | Executor | MCP server | State component |
|---|---|---|---|---|---|---|---|---|---|
| `warehouse.labor.get_capacity` | read_only | read | No | Yes | — | `LaborCapacitySkill` | — | `mcp_servers/labor` | `LaborState` |
| `warehouse.labor.get_allocation` | read_only | read | No | Yes | — | `LaborAllocationSkill` | — | `mcp_servers/labor` | `LaborState` |
| `warehouse.labor.allocate` | medium | write | Yes | No | `ProposeLaborAllocationSkill` | `ExecuteLaborAllocationSkill` | `LaborActionExecutor` | `mcp_servers/labor` | `LaborState` |

**Permission token:** `labor:execute`  
**State model:** `LaborState` (workers, total_workers, available_workers, utilization_pct)  
**Proposal factory:** `ActionProposal.for_labor_allocate()`  
**Executor:** `LaborActionExecutor` — `_ALLOWED_ACTIONS = {warehouse.labor.allocate}`  
**State property:** `LaborState.is_constrained` → True when available_workers / total_workers ≤ 0.20

---

## Wave / WMS Domain

| Capability | Risk | Side-effect | Req. approval | Idempotent | Proposal skill | Exec skill | Executor | MCP server | State component |
|---|---|---|---|---|---|---|---|---|---|
| `warehouse.wave.get` | read_only | read | No | Yes | — | `WaveGetSkill` | — | `mcp_servers/wave` | `WaveState` |
| `warehouse.wave.get_risk` | read_only | read | No | Yes | — | `WaveRiskSkill` | — | `mcp_servers/wave` | `WaveState` |
| `warehouse.wave.reprioritize` | medium | write | Yes | No | `ProposeWaveReprioritizationSkill` | `ExecuteWaveReprioritizationSkill` | `WaveActionExecutor` | `mcp_servers/wave` | `WaveState` |

**Permission token:** `wave:execute`  
**State model:** `WaveState` (tasks, pending_count, in_progress_count, at_risk_count, zones_active)  
**Proposal factory:** `ActionProposal.for_wave_reprioritize()`  
**Executor:** `WaveActionExecutor` — `_ALLOWED_ACTIONS = {warehouse.wave.reprioritize}`  
**State property:** `WaveState.otif_at_risk` → True when at_risk_count > 0

---

## Capability Summary

| Domain | Read capabilities | Write capabilities | Total |
|--------|------------------|--------------------|-------|
| Inventory | 2 | 0 | **2** |
| Equipment | 1 | 3 | **4** |
| Labor | 2 | 1 | **3** |
| Wave | 2 | 1 | **3** |
| **Total** | **7** | **5** | **12** |

---

## Risk Tier Decision Matrix

| Risk tier | Requires human approval? | Auto-approve eligible? | Example |
|-----------|--------------------------|------------------------|---------|
| `read_only` | Never | N/A (reads, no proposal) | `get_status`, `get_capacity`, `get_risk`, `get`, `locate` |
| `low` | No | Yes (by DecisionEngine) | `equipment.release` |
| `medium` | Yes — always | Never | `allocate`, `reprioritize`, `assign`, `schedule_maintenance` |
| `high` | Yes — always | Never | *(reserved, not yet implemented)* |

---

## Cross-Domain Invariants

These invariants hold across all 4 domains and are enforced by `tests/unit/test_architecture_invariants.py`.

| # | Invariant |
|---|-----------|
| 1 | Proposal skill makes **no MCP call** |
| 2 | Proposal skill causes **no backend mutation** |
| 3 | `DecisionEngine.evaluate()` makes **no MCP call** |
| 4 | Non-APPROVED decision never reaches executor |
| 5 | Unknown action (outside `_ALLOWED_ACTIONS` frozenset) never reaches MCP |
| 6 | Expired decision (> `max_decision_age_seconds`) never reaches MCP |
| 7 | Proposal/decision ID mismatch never reaches MCP |
| 8 | `warehouse_id` propagates from proposal factory → executor → MCP request |
| 9 | MCP server exposes **only** execution tools (no propose/suggest tools) |
| 10 | Wave executor cannot execute Labor actions; Labor executor cannot execute Wave actions |

---

## Capability Registry

Environment variables for service discovery (all `CapabilityRegistry.from_env()` keys):

| Variable | Default | Domain |
|----------|---------|--------|
| `MAIW_MCP_SERVER_INVENTORY_URL` | `http://localhost:8001` | Inventory |
| `MAIW_MCP_SERVER_EQUIPMENT_URL` | `http://localhost:8002` | Equipment |
| `MAIW_MCP_SERVER_LABOR_URL` | `http://localhost:8003` | Labor |
| `MAIW_MCP_SERVER_WAVE_URL` | `http://localhost:8004` | Wave |

---

## Out of Scope (Phase 7–8)

The following capability categories were explicitly excluded:

- Document / knowledge-base capabilities (classified as LEGACY COMPATIBILITY)
- Forecasting capabilities (classified as EXTERNAL INTEGRATION candidate)
- Simulation / Optimization / Training capabilities
- SAP EWM / Manhattan / Blue Yonder ERP connectors (defined in `connectors/` interface spec)
- Order management capabilities
- Dock scheduling capabilities
