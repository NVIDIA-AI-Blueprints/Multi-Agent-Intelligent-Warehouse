# API Migration Plan — Phase 9B

**Status:** IN PROGRESS (Phase 9B)  
**Branch:** `feat/phase-9b-api-migration`  
**Entering baseline:** 528 passed, 1 skipped, 0 failed (CORE CI)

---

## Objective

Move the application shell from `src/api/` to `apps/api/maiw_api/` so that
`apps/api` becomes the canonical FastAPI entrypoint and `MAIWRuntime` becomes
the canonical composition root.

Canonical packages (`maiw-models`, `maiw-mcp`, `maiw-state`, `maiw-skills`,
`maiw-decision`, `maiw-execution`, `maiw-agents`) must not depend on the API
layer. The API layer may depend on all of them.

---

## Ownership Audit

### `apps/api/maiw_api/` — new canonical application layer

| File | Action |
|------|--------|
| `bootstrap.py` | REWRITE — fix broken syntax, correct full wiring |
| `app.py` | CREATE — canonical FastAPI entrypoint |
| `config.py` | CREATE — application settings |
| `dependencies.py` | CREATE — FastAPI dependency helpers |
| `lifespan.py` | CREATE — FastAPI lifespan (startup/shutdown) |
| `routers/health.py` | CREATE — health, live, ready, version |
| `routers/equipment.py` | CREATE — canonical equipment (via MAIWRuntime) |
| `routers/operations.py` | CREATE — operations CRUD + agent |
| `routers/safety.py` | CREATE — safety CRUD |
| `routers/mcp_status.py` | CREATE — MCP v2 capability status |

### `src/api/routers/` — classification

| Router | New location | Canonical dependency | Status |
|--------|-------------|---------------------|--------|
| `health.py` | `maiw_api.routers.health` | MAIWRuntime | MOVED |
| `equipment.py` | `maiw_api.routers.equipment` | `maiw_agents.equipment` | MOVED |
| `operations.py` | `maiw_api.routers.operations` | SQLRetriever / `maiw_agents.operations` | MOVED |
| `safety.py` | `maiw_api.routers.safety` | SQLRetriever | MOVED |
| `mcp.py` | `maiw_api.routers.mcp_status` | `maiw_mcp` (canonical) | REPLACED |
| `chat.py` | imported from `src.api.routers.chat` | LangGraph planner | KEEP TEMPORARILY |
| `auth.py` | imported from `src.api.routers.auth` | JWT/RBAC | KEEP TEMPORARILY |
| `inventory.py` | imported from `src.api.routers.inventory` | SQLRetriever | KEEP TEMPORARILY |
| `wms.py` | imported from `src.api.routers.wms` | WMS integration | INTEGRATION-SPECIFIC |
| `iot.py` | imported from `src.api.routers.iot` | IoT integration | INTEGRATION-SPECIFIC |
| `erp.py` | imported from `src.api.routers.erp` | ERP integration | INTEGRATION-SPECIFIC |
| `scanning.py` | imported from `src.api.routers.scanning` | Scanning integration | INTEGRATION-SPECIFIC |
| `attendance.py` | imported from `src.api.routers.attendance` | Attendance integration | INTEGRATION-SPECIFIC |
| `reasoning.py` | imported from `src.api.routers.reasoning` | Reasoning service | KEEP TEMPORARILY |
| `migration.py` | imported from `src.api.routers.migration` | DB migration | KEEP TEMPORARILY |
| `document.py` | imported from `src.api.routers.document` | OCR/NeMo pipeline | KEEP TEMPORARILY — DOCUMENT INTEGRATION |
| `advanced_forecasting.py` | imported from `src.api.routers.advanced_forecasting` | Forecasting | INTEGRATION-SPECIFIC |
| `training.py` | imported from `src.api.routers.training` | Training (FUTURE) | INTEGRATION-SPECIFIC |

### `src/api/agents/` — classification

| Module | Classification | Reason |
|--------|---------------|--------|
| `inventory/equipment_agent.py` | LEGACY — keep during Phase 9B | Called by legacy chat router |
| `inventory/state_aware_ops.py` | LEGACY — superseded by `maiw_agents.equipment.state_aware_ops` | |
| `inventory/equipment_asset_tools.py` | ACTIVE INTEGRATION — EquipmentAssetTools → PostgreSQL | Used by canonical agent via bootstrap |
| `inventory/mcp_equipment_agent.py` | DEPRECATED — old custom MCP agent | No active callers post-migration |
| `inventory/action_executor.py` | SUPERSEDED — by `maiw_execution` package | |
| `operations/operations_agent.py` | LEGACY — keep during Phase 9B | Called by chat router |
| `operations/mcp_operations_agent.py` | DEPRECATED — old custom MCP agent | |
| `operations/labor_executor.py` | SUPERSEDED — by `maiw_execution.LaborActionExecutor` | |
| `operations/wave_executor.py` | SUPERSEDED — by `maiw_execution.WaveActionExecutor` | |
| `safety/safety_agent.py` | LEGACY — keep during Phase 9B | Called by chat router |
| `safety/mcp_safety_agent.py` | DEPRECATED — old custom MCP agent | |
| `forecasting/` | INTEGRATION-SPECIFIC — keep as-is | |
| `document/` | INTEGRATION-SPECIFIC — keep as-is | |

### `src/api/services/` — classification

| Module | Classification | Remove When |
|--------|---------------|------------|
| `model_gateway/__init__.py` | COMPATIBILITY SHIM → `maiw_models` | After all callers migrated to `maiw_models` |
| `model_gateway/*.py` | ACTIVE — original implementation (now in `maiw-models`) | Already shadowed by canonical package |
| `skills/inventory.py` | COMPATIBILITY SHIM → `maiw_skills` | After callers migrated |
| `skills/equipment.py` | COMPATIBILITY SHIM → `maiw_skills` | After callers migrated |
| `skills/labor.py` | COMPATIBILITY SHIM → `maiw_skills` | After callers migrated |
| `skills/wave.py` | COMPATIBILITY SHIM → `maiw_skills` | After callers migrated |
| `mcp/tool_discovery.py` | DEPRECATED — old custom MCP discovery | After `evidence_collector` migrated |
| `mcp/tool_binding.py` | DEPRECATED | |
| `mcp/tool_routing.py` | DEPRECATED | |
| `mcp/tool_validation.py` | DEPRECATED | |
| `mcp/base.py`, `client.py`, `server.py` | DEPRECATED | |
| `mcp/parameter_validator.py` | DEPRECATED | |
| `mcp/security.py` | DEPRECATED | |
| `mcp/adapters/` | DEPRECATED (except as referenced by mcp.py router) | After mcp router is replaced |
| `llm/nim_client.py` | ACTIVE INTEGRATION — wrapped by maiw_models | Keep until callers fully migrated |
| `evidence/evidence_collector.py` | DEPRECATED — imports legacy mcp.tool_discovery | Remove after audit |
| `evidence/evidence_integration.py` | DEPRECATED | |
| `auth/` | ACTIVE — keep | |
| `database.py` | ACTIVE — keep | |
| `monitoring/` | ACTIVE — keep | |
| `cache/` | ACTIVE — keep | |
| `memory/` | ACTIVE — keep | |
| `guardrails/` | ACTIVE — keep | |
| `routing/semantic_router.py` | ACTIVE — used by chat router | |

---

## Compatibility Shim Removal Gate

Shims are removed when **all** of the following are true:

1. Zero production router imports the shim path
2. Zero maintained test files import the shim path
3. The new canonical path is exercised by CORE CI

### Shim status at end of Phase 9B

| Shim | Remaining callers | Status |
|------|------------------|--------|
| `src.api.services.model_gateway` | Legacy src agents (not on canonical path) | REMOVE — legacy agents are no longer on production call path after new app is active |
| `src.api.skills.*` | Legacy src agents | REMOVE — same reason |

---

## MCP Legacy Status

`src/api/services/mcp/` — 13 files (not counting `__init__.py`).

Remaining callers after Phase 9B:
- `src/api/routers/mcp.py` → **REPLACED** by `maiw_api.routers.mcp_status`
- `src/api/graphs/mcp_*.py` → KEEP TEMPORARILY (LangGraph graphs used by chat router)
- `src/api/services/evidence/evidence_collector.py` → DEPRECATE
- `src/api/agents/*/mcp_*.py` → DEPRECATED stubs

After Phase 9B, `src/api/services/mcp/` callers are isolated to legacy graphs and
deprecated agent stubs. The new canonical `apps/api` app never imports from it.

---

## Forecasting Status

`INTEGRATION-SPECIFIC`. `integrations/forecasting/` and
`src/api/agents/forecasting/` remain as-is. The forecasting router is imported
into the new app from `src.api.routers.advanced_forecasting` during Phase 9B.
The forecasting integration does not use the `STATE → DECIDE → EXECUTE` pipeline.

**FORECASTING LEGACY INTEGRATION BOUNDARY:** The forecasting router pulls
`src.api.agents.forecasting.forecasting_agent` which imports
`src.api.services.model_gateway` (the shim). This is tolerated in Phase 9B
since forecasting remains on the legacy call path.

---

## Document Status

`KEEP TEMPORARILY — DOCUMENT INTEGRATION`. The document pipeline depends on
`asyncpg`, `pymilvus`, OCR libraries, and NeMo services. It is imported into the
new app from `src.api.routers.document` and remains isolated behind the legacy
call path. It is not part of Phase 9B scope.

---

## Docker / Deployment Impact

- Dockerfile updated to: `pip install -e apps/api`
- Entrypoint updated to: `uvicorn maiw_api.app:app`
- PYTHONPATH includes `/app` (same as before)
- All 7 canonical packages remain installed

---

## Test Strategy Update

Phase 9B adds `tests/api/` as a new test tier. These tests:
- Create the app without infrastructure
- Verify route registration
- Verify MAIWRuntime construction with mocks
- Verify package dependency direction

`tests/api/` is included in CORE CI if it is deterministic and
infrastructure-free. See `TEST_STRATEGY.md` for the updated canonical command.
