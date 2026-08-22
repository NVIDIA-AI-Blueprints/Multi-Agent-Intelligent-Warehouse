# MAIW Package Ownership Map

**Phase:** 8  
**Date:** 2026-08-20

This document maps every major module to its target package in the Phase 8 architecture.
It is the authoritative guide for all move operations.

---

## Status Codes

| Code | Meaning |
|------|---------|
| `MOVE NOW` | Move in this phase; canonical home is the target package |
| `KEEP TEMPORARILY` | Keep at current path with compatibility re-export; migrate in a later phase |
| `EXTERNAL INTEGRATION` | Out of the core dependency graph; should not be imported by core packages |
| `DEPRECATE` | Functionally superseded; mark with deprecation notice, remove next phase |
| `DELETE` | No production callers, no compatibility requirement; remove now |

---

## Core Packages — Already Correct

These packages are in their canonical location and must not be moved.

| Module | Current path | Target package | Status |
|--------|-------------|----------------|--------|
| `CapabilityMetadata`, `ActionProposal`, `RiskLevel` | `packages/maiw-mcp/maiw_mcp/contracts/` | `maiw-mcp` | ✅ CORRECT |
| `MAIWMCPClient` | `packages/maiw-mcp/maiw_mcp/client/` | `maiw-mcp` | ✅ CORRECT |
| `CapabilityRegistry` | `packages/maiw-mcp/maiw_mcp/registry/` | `maiw-mcp` | ✅ CORRECT |
| `CapabilityTelemetry` | `packages/maiw-mcp/maiw_mcp/telemetry/` | `maiw-mcp` | ✅ CORRECT |
| `DecisionEngine` | `packages/maiw-decision/maiw_decision/` | `maiw-decision` | ✅ CORRECT |
| `DecisionResult`, `DecisionOutcome` | `packages/maiw-decision/maiw_decision/models.py` | `maiw-decision` | ✅ CORRECT |
| `WarehouseState`, `WarehouseStateSnapshot` | `packages/maiw-state/maiw_state/warehouse.py` | `maiw-state` | ✅ CORRECT |
| `EquipmentState`, `LaborState`, `WaveState` | `packages/maiw-state/maiw_state/models/` | `maiw-state` | ✅ CORRECT |
| `StateFreshness`, `StateRequirements` | `packages/maiw-state/maiw_state/` | `maiw-state` | ✅ CORRECT |
| `WarehouseStateProvider` | `packages/maiw-state/maiw_state/provider.py` | `maiw-state` | ✅ CORRECT |

---

## Batch 1: ModelGateway → `packages/maiw-models/`

| Module | Current path | Target package | Status | Action |
|--------|-------------|----------------|--------|--------|
| `ModelGateway` | `src/api/services/model_gateway/gateway.py` | `maiw-models` | `MOVE NOW` | Move to `packages/maiw-models/maiw_models/gateway.py` |
| `ModelRouter` | `src/api/services/model_gateway/router.py` | `maiw-models` | `MOVE NOW` | Move to `packages/maiw-models/maiw_models/router.py` |
| `ModelRegistry` | `src/api/services/model_gateway/registry.py` | `maiw-models` | `MOVE NOW` | Move to `packages/maiw-models/maiw_models/registry.py` |
| `ModelCapability`, `ModelRequest`, `ModelResponse` | `src/api/services/model_gateway/models.py` | `maiw-models` | `MOVE NOW` | Move to `packages/maiw-models/maiw_models/models.py` |
| `NIMProvider` | `src/api/services/model_gateway/providers/nim.py` | `maiw-models` | `MOVE NOW` | Move to `packages/maiw-models/maiw_models/providers/nim.py` |
| `GatewayTelemetry` | `src/api/services/model_gateway/telemetry.py` | `maiw-models` | `MOVE NOW` | Move to `packages/maiw-models/maiw_models/telemetry.py` |
| Model gateway errors | `src/api/services/model_gateway/errors.py` | `maiw-models` | `MOVE NOW` | Move to `packages/maiw-models/maiw_models/errors.py` |
| `get_model_gateway` singleton | `src/api/services/model_gateway/__init__.py` | `apps/api` (composition root) | `KEEP TEMPORARILY` | Compatibility re-export; wire in `apps/api/maiw_api/bootstrap.py` |
| `NIMClient` | `src/api/services/llm/nim_client.py` | `maiw-models` | `MOVE NOW` | Move to `packages/maiw-models/maiw_models/providers/nim_client.py` |

**Compatibility path:** `src/api/services/model_gateway/__init__.py` becomes a re-export shim:
```python
from maiw_models import *  # DEPRECATED: use maiw_models directly
```
Remove by Phase 9.

---

## Batch 2: Skills → `packages/maiw-skills/`

| Module | Current path | Target package | Status | Action |
|--------|-------------|----------------|--------|--------|
| `InventoryLookupSkill` | `src/api/skills/inventory.py` | `maiw-skills` | `MOVE NOW` | Move to `packages/maiw-skills/maiw_skills/inventory/lookup.py` |
| `EquipmentStatusSkill`, `EquipmentAssignmentSkill` | `src/api/skills/equipment.py` | `maiw-skills` | `MOVE NOW` | Move to `packages/maiw-skills/maiw_skills/equipment/` |
| `LaborCapacitySkill`, `ProposeLaborAllocationSkill` | `src/api/skills/labor.py` | `maiw-skills` | `MOVE NOW` | Move to `packages/maiw-skills/maiw_skills/labor/` |
| `WaveGetSkill`, `ProposeWaveReprioritizationSkill` | `src/api/skills/wave.py` | `maiw-skills` | `MOVE NOW` | Move to `packages/maiw-skills/maiw_skills/wave/` |

**Compatibility paths:** `src/api/skills/{domain}.py` become re-export shims.  Remove by Phase 9.

---

## Batch 3: Agents → `packages/maiw-agents/` + `packages/maiw-execution/`

> **Phase 9A status:** Executors moved to `maiw-execution` (shared guard layer); agents moved to `maiw-agents` (domain reasoning). All src.* imports eliminated from both packages.

| Module | Canonical path (Phase 9A) | Status | Notes |
|--------|--------------------------|--------|-------|
| `BaseActionExecutor`, error hierarchy | `packages/maiw-execution/maiw_execution/base.py` | ✅ DONE | 4-guard pattern: APPROVED, binding, allowlist, staleness |
| `EquipmentActionExecutor` | `packages/maiw-execution/maiw_execution/equipment.py` | ✅ DONE | Moved from `src/api/agents/inventory/action_executor.py` |
| `LaborActionExecutor` | `packages/maiw-execution/maiw_execution/labor.py` | ✅ DONE | Moved from `src/api/agents/operations/labor_executor.py` |
| `WaveActionExecutor` | `packages/maiw-execution/maiw_execution/wave.py` | ✅ DONE | Moved from `src/api/agents/operations/wave_executor.py` |
| `EquipmentAssetOperationsAgent` | `packages/maiw-agents/maiw_agents/equipment/agent.py` | ✅ DONE | Migrated from `src/api/agents/inventory/equipment_agent.py` |
| `OperationsCoordinationAgent` | `packages/maiw-agents/maiw_agents/operations/agent.py` | ✅ DONE | Migrated from `src/api/agents/operations/operations_agent.py` |
| `SafetyComplianceAgent` | `packages/maiw-agents/maiw_agents/safety/agent.py` | ✅ DONE | Migrated from `src/api/agents/safety/safety_agent.py` |
| `state_aware_ops.py` | `packages/maiw-agents/maiw_agents/equipment/state_aware_ops.py` | ✅ DONE | Copied from `src/api/agents/inventory/state_aware_ops.py` |
| `MCPEquipmentAgent`, `MCPOperationsAgent`, `MCPSafetyAgent` | `src/api/agents/*/mcp_*.py` | DEPRECATED | NIM-primary paths; never migrated to ModelGateway; marked with DEPRECATED comment |
| `ForecastingAgent` | `src/api/agents/forecasting/` | EXTERNAL INTEGRATION | Uses ModelGateway but not core transactional; classify as integration |
| Document agents | `src/api/agents/document/` | EXTERNAL INTEGRATION | Large external dependency surface (OCR, embeddings); not core |
## Batch 3: Agents → `packages/maiw-agents/`

| Module | Current path | Target package | Status | Notes |
|--------|-------------|----------------|--------|-------|
| `EquipmentActionExecutor` | `src/api/agents/inventory/action_executor.py` | `maiw-agents/equipment/` | `MOVE NOW` | Path is misleading; Equipment lives under "inventory" dir — fix during move |
| `EquipmentAssetOperationsAgent`, `MCPEquipmentAgent` | `src/api/agents/inventory/` | `maiw-agents/equipment/` | `MOVE NOW` | Domain: Equipment, not Inventory |
| `LaborActionExecutor` | `src/api/agents/operations/labor_executor.py` | `maiw-agents/labor/` | `MOVE NOW` | |
| `WaveActionExecutor` | `src/api/agents/operations/wave_executor.py` | `maiw-agents/wave/` | `MOVE NOW` | |
| `OperationsAgent`, `MCPOperationsAgent` | `src/api/agents/operations/` | `maiw-agents/operations/` | `MOVE NOW` | |
| `SafetyAgent`, `MCPSafetyAgent` | `src/api/agents/safety/` | `maiw-agents/safety/` | `MOVE NOW` | |
| `ForecastingAgent` | `src/api/agents/forecasting/` | `integrations/forecasting/` | `EXTERNAL INTEGRATION` | Uses ModelGateway but is not core transactional; classify as integration |
| Document agents | `src/api/agents/document/` | `integrations/document/` | `EXTERNAL INTEGRATION` | Large external dependency surface (OCR, embeddings); not core |
| `state_aware_ops.py` | `src/api/agents/inventory/state_aware_ops.py` | `maiw-agents/equipment/` | `MOVE NOW` | Belongs with equipment executor |

---

## Batch 4: API Composition

| Module | Current path | Target | Status | Notes |
|--------|-------------|--------|--------|-------|
| `app.py` | `src/api/app.py` | `apps/api/maiw_api/app.py` | `DONE (Phase 9B)` | Canonical FastAPI entrypoint: `uvicorn maiw_api.app:app` |
| health router | `src/api/routers/health.py` | `apps/api/maiw_api/routers/health.py` | `DONE (Phase 9B)` | Adds MAIWRuntime status block to /health |
| equipment router | `src/api/routers/equipment.py` | `apps/api/maiw_api/routers/equipment.py` | `DONE (Phase 9B)` | Write paths use canonical pipeline |
| operations router | `src/api/routers/operations.py` | `apps/api/maiw_api/routers/operations.py` | `DONE (Phase 9B)` | SQL CRUD (bug-fixed); canonical agent via chat |
| safety router | `src/api/routers/safety.py` | `apps/api/maiw_api/routers/safety.py` | `DONE (Phase 9B)` | SQL CRUD; static policies |
| mcp router | `src/api/routers/mcp.py` | `apps/api/maiw_api/routers/mcp_status.py` | `REPLACED (Phase 9B)` | Legacy custom MCP replaced with canonical MCP v2 status endpoint |
| `bootstrap.py` | (broken, Phase 8) | `apps/api/maiw_api/bootstrap.py` | `REWRITTEN (Phase 9B)` | MAIWRuntime composition root; correct full wiring |
| `config.py` | (new) | `apps/api/maiw_api/config.py` | `DONE (Phase 9B)` | Application settings |
| `dependencies.py` | (new) | `apps/api/maiw_api/dependencies.py` | `DONE (Phase 9B)` | FastAPI dependency helpers |
| `lifespan.py` | (new) | `apps/api/maiw_api/lifespan.py` | `DONE (Phase 9B)` | Startup/shutdown |
| Auth services | `src/api/services/auth/` | `apps/api/maiw_api/services/auth/` | `KEEP TEMPORARILY` | API-specific |
| DB service | `src/api/services/database.py` | `apps/api/maiw_api/services/` | `KEEP TEMPORARILY` | Infrastructure |
| Middleware | `src/api/middleware/` | `apps/api/maiw_api/middleware/` | `KEEP TEMPORARILY` | Imported from src.api in Phase 9B |

---

## MCP Server Normalization — Batch 5

| Module | Current path | Target | Status | Notes |
|--------|-------------|--------|--------|-------|
| Inventory MCP server | `mcp_servers/inventory/` | `mcp_servers/inventory/` | ✅ CORRECT | Name is consistent |
| Equipment MCP server | `mcp_servers/equipment/` | `mcp_servers/equipment/` | ✅ CORRECT | |
| Labor MCP server | `mcp_servers/labor/` | `mcp_servers/labor/` | ✅ CORRECT | |
| Wave MCP server | `mcp_servers/wave/` | `mcp_servers/wave/` | ✅ CORRECT | |

MCP servers are already in a consistent location. No moves needed. The directory name stays `mcp_servers/`
(Python packaging constraint — hyphens in directory names require extra configuration).

---

## Legacy MCP — Batch 5 (Audit)

The `src/api/services/mcp/` directory is the **old custom MCP system** predating MCP 2.0.
The new canonical path is `packages/maiw-mcp/` + `mcp_servers/`.

| File | Classification | Notes |
|------|---------------|-------|
| `src/api/services/mcp/base.py` | `DEPRECATE` | `MCPManager`, `MCPAdapter`, `MCPToolBase` — still used by `mcp_equipment_agent.py` |
| `src/api/services/mcp/client.py` | `DEPRECATE` | Old `MCPClient`, not MCP 2.0 |
| `src/api/services/mcp/server.py` | `DEPRECATE` | Old `MCPServer` — different from `mcp.server.MCPServer` |
| `src/api/services/mcp/tool_discovery.py` | `DEPRECATE` | Used by `mcp_equipment_agent.py` and `forecasting_agent.py` |
| `src/api/services/mcp/adapters/equipment_adapter.py` | `DEPRECATE` | Wraps old MCP, calls `equipment_asset_tools.py` |
| `src/api/services/mcp/adapters/forecasting_adapter.py` | `DEPRECATE` | Old MCP adapter for forecasting |
| `src/api/services/mcp/adapters/operations_adapter.py` | `DEPRECATE` | Old MCP adapter for operations |
| `src/api/services/mcp/adapters/safety_adapter.py` | `DEPRECATE` | Old MCP adapter for safety |
| `src/api/services/mcp/parameter_validator.py` | `DEPRECATE` | |
| `src/api/services/mcp/monitoring.py` | ✅ DELETED (Phase 9A) | Zero production callers confirmed before deletion |
| `src/api/services/mcp/rollback.py` | ✅ DELETED (Phase 9A) | Zero production callers confirmed before deletion |
| `src/api/services/mcp/security.py` | `DEPRECATE` | Security for old MCP |
| `src/api/services/mcp/service_discovery.py` | ✅ DELETED (Phase 9A) | Zero production callers confirmed before deletion |
| `src/api/services/mcp/tool_binding.py` | `DEPRECATE` | |
| `src/api/services/mcp/tool_routing.py` | `DEPRECATE` | |
| `src/api/services/mcp/tool_validation.py` | `DEPRECATE` | |
| `src/api/services/mcp/adapters/rfid_barcode_adapter.py` | ✅ DELETED (Phase 9A) | Hardware adapter, no active callers |
| `src/api/services/mcp/adapters/time_attendance_adapter.py` | ✅ DELETED (Phase 9A) | Hardware adapter, no active callers |

**Phase 9A status:** Remaining DEPRECATE items are still used by `mcp_equipment_agent.py`, `forecasting_agent.py`, `src/api/routers/mcp.py`, and `evidence_collector.py`. These will be cleaned up in Phase 9B when those callers are migrated to the MCP 2.0 path.
| `src/api/services/mcp/monitoring.py` | `DEPRECATE` | Monitoring for old MCP |
| `src/api/services/mcp/rollback.py` | `DEPRECATE` | |
| `src/api/services/mcp/security.py` | `DEPRECATE` | Security for old MCP |
| `src/api/services/mcp/service_discovery.py` | `DEPRECATE` | |
| `src/api/services/mcp/tool_binding.py` | `DEPRECATE` | |
| `src/api/services/mcp/tool_routing.py` | `DEPRECATE` | |
| `src/api/services/mcp/tool_validation.py` | `DEPRECATE` | |
| `src/api/services/mcp/adapters/rfid_barcode_adapter.py` | `DELETE` | Hardware adapter, no active callers |
| `src/api/services/mcp/adapters/time_attendance_adapter.py` | `DELETE` | Hardware adapter, no active callers |

**Decision:** Do not delete DEPRECATE items in Phase 8 because `mcp_equipment_agent.py` and
`forecasting_agent.py` still reference them. These will be cleaned up when those agents are migrated
to the MCP 2.0 path in a future phase.

---

## Other Services Classification

| Module | Current path | Target | Status | Notes |
|--------|-------------|--------|--------|-------|
| `NIMClient` | `src/api/services/llm/nim_client.py` | `maiw-models` | `MOVE NOW` | Core dependency for ModelGateway |
| Evidence services | `src/api/services/evidence/` | `apps/api` | `KEEP TEMPORARILY` | Uses old MCP tool discovery |
| Monitoring metrics | `src/api/services/monitoring/` | `apps/api` | `KEEP TEMPORARILY` | Prometheus metrics |
| Memory/conversation | `src/api/services/memory/` | `apps/api` | `KEEP TEMPORARILY` | Chat memory |
| Caching | `src/api/services/cache/` | `apps/api` | `KEEP TEMPORARILY` | Redis cache |
| Auth | `src/api/services/auth/` | `apps/api` | `KEEP TEMPORARILY` | JWT + user auth |
| Guardrails | `src/api/services/guardrails/` | `EXTERNAL INTEGRATION` | `KEEP TEMPORARILY` | NeMo Guardrails |
| Forecasting config | `src/api/services/forecasting_config.py` | `EXTERNAL INTEGRATION` | `KEEP TEMPORARILY` | |
| Retrieval | `src/retrieval/` | `EXTERNAL INTEGRATION` | `KEEP TEMPORARILY` | Vector store, SQL, embeddings |
| Adapters | `src/adapters/` | `connectors/` | `KEEP TEMPORARILY` | ERP/IoT adapters → future connectors |
| Document pipeline | `src/api/agents/document/` | `integrations/document/` | `EXTERNAL INTEGRATION` | |

---

## Target Package Dependency Graph

```
apps/api (FastAPI routers, bootstrap, HTTP auth)
    ↓
maiw-agents (agent reasoning roles)
    ↓
maiw-skills (per-domain skill implementations)
    ↓
maiw-mcp (contracts, client, registry)
    ↓ ← also used by:
maiw-state (WarehouseState, domain models)
    ↓ ← used by:
maiw-decision (DecisionEngine)
    ↑
maiw-agents (via ActionExecutor)

apps/api
    ↓
maiw-models (ModelGateway, NIMProvider)

maiw-skills
    ↓ (depends on)
maiw-mcp
maiw-state

maiw-agents
    ↓ (depends on)
maiw-skills
maiw-models
maiw-state
maiw-decision
maiw-mcp

apps/api
    ↓ (imports all packages)
    Does NOT export to any package
```

### Forbidden dependencies (must never be introduced)

```
maiw-state    →  apps/api         # state must not depend on API
maiw-mcp      →  maiw-agents      # MCP abstractions must not depend on agents
maiw-models   →  apps/api         # model layer must not depend on API
maiw-skills   →  apps/api         # skills must not depend on API
maiw-decision →  apps/api         # decision engine must not depend on API
```

---

## Connectors Directory

`connectors/` is **created as a directory spec only** in Phase 8.  No connector implementations are written.

```
connectors/
├── README.md          # Interface contract definition
├── generic/           # Generic REST/webhook connector template
├── sap-ewm/           # (FUTURE — not implemented)
├── manhattan/         # (FUTURE — not implemented)
└── blue-yonder/       # (FUTURE — not implemented)
```

The distinction between Provider and Connector:
- **Provider**: Internal implementation of a vendor-neutral capability (e.g., `MAIWInventoryAdapter`)
- **Connector**: Vendor/system-specific implementation (e.g., SAP EWM)
- MCP server depends on Provider interface → Connector implements Provider

---

## Integrations Directory

`integrations/` classifies non-core systems with heavy external dependencies.

```
integrations/
├── forecasting/        # ForecastingAgent + forecasting config (EXTERNAL INTEGRATION)
├── document/           # Document pipeline: OCR, NeMo Parse, embeddings, multimodal
├── simulation/         # (FUTURE)
├── optimization/       # (FUTURE)
└── training/           # (FUTURE — SFT, GRPO)
```

The core architecture must not import from `integrations/` except through well-defined interfaces.

---

## Move Execution Order

| Batch | Content | Risk | CI check |
|-------|---------|------|----------|
| 0 | Capability matrix fix | None | No |
| 1 | PACKAGE_OWNERSHIP.md | None | No |
| 2 | uv workspace config | Low | Yes |
| 3 | `maiw-models` package creation | Low-Medium | After install |
| 4 | `maiw-skills` package creation | Low-Medium | After install |
| 5 | `apps/api/` structure + bootstrap | Low | Yes |
| 6 | Architecture dependency tests | None | Yes |
| 7 | Legacy MCP classification | None | Yes |
| 8 | Final full regression | — | Yes |
