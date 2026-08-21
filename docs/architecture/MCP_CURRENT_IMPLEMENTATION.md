# MCP — Current Implementation Audit

**Audited:** 2026-08-20 | **Phase 2 pre-work**

---

## Summary

The MAIW repository contains a complete, hand-rolled MCP-style framework built entirely from
scratch using plain `aiohttp` and `websockets`.  It follows the MCP JSON-RPC spec
(protocol version `2024-11-05`) but does **not** import or use the official
`mcp` Python SDK.

---

## What is actual MCP

The protocol message format is correct MCP JSON-RPC 2.0.  The method names
(`tools/list`, `tools/call`, `resources/list`, `prompts/list`, `initialize`, `ping`)
match the official spec.  The `protocolVersion` field is set to `"2024-11-05"`.

---

## What is custom abstraction

Everything else:

| Layer | File | What it is |
|---|---|---|
| Server | `src/api/services/mcp/server.py` | Hand-rolled JSON-RPC server; stores tools in a `dict`; no SDK |
| Client | `src/api/services/mcp/client.py` | `aiohttp`/`websockets` client; manually crafts JSON-RPC; no SDK |
| Tool discovery | `src/api/services/mcp/tool_discovery.py` | Background polling loop; keyword-based categorisation |
| Tool binding | `src/api/services/mcp/tool_binding.py` | 5 binding strategies (EXACT_MATCH…PERFORMANCE_BASED) |
| Tool routing | `src/api/services/mcp/tool_routing.py` | Multi-criteria scoring; heuristic complexity classifier |
| Tool validation | `src/api/services/mcp/tool_validation.py` | Pre-execution param validation; error classification |
| Security | `src/api/services/mcp/security.py` | Blocklist guard (35 regex patterns); CVE-2024-28088 fix |
| Monitoring | `src/api/services/mcp/monitoring.py` | `psutil`-based metrics; alert rules; structured log |
| Parameter validator | `src/api/services/mcp/parameter_validator.py` | Domain-specific regexes for equipment/zone/task IDs |
| Rollback | `src/api/services/mcp/rollback.py` | Infrastructure present; **all rollback bodies are `pass` stubs** |
| Service discovery | `src/api/services/mcp/service_discovery.py` | SHA-256 ID registry; HTTP health-check loop |
| Base/manager | `src/api/services/mcp/base.py` | `MCPAdapter` ABC, `MCPManager` orchestrator |
| Adapters | `src/api/services/mcp/adapters/` | 8 adapters wrapping warehouse backends |

### MCP-enhanced agents

| Agent | File |
|---|---|
| `MCPEquipmentAssetOperationsAgent` | `src/api/agents/inventory/mcp_equipment_agent.py` |
| `MCPSafetyComplianceAgent` | `src/api/agents/safety/mcp_safety_agent.py` |
| `MCPOperationsCoordinationAgent` | `src/api/agents/operations/mcp_operations_agent.py` |
| MCP Document agent | `src/api/agents/document/mcp_document_agent.py` |

### Planner graphs

- `src/api/graphs/mcp_planner_graph.py` — `MCPWarehouseState` TypedDict; keyword-based routing
- `src/api/graphs/mcp_integrated_planner_graph.py` — production integrated planner

---

## Real runtime path (existing)

```
HTTP request
   ↓
FastAPI router (src/api/routers/mcp.py)
   ↓
get_mcp_services() singleton
  → ToolDiscoveryService.start_discovery()
  → register_mcp_adapters() [equipment, operations, safety, forecasting]
   ↓
Process query
   ↓
ToolRoutingService.route_tools()  [heuristic scoring]
   ↓
ToolBindingService.bind_tools()   [EXACT_MATCH / PERFORMANCE_BASED]
   ↓
ToolValidationService.validate_tool_execution()
   ↓
MCPAdapter.execute_tool()          [in-process function call — no network]
   ↓
Backend action tool / SQL query
```

**Critical observation:** Despite the JSON-RPC framing, all production tool execution is
in-process.  `MCPAdapter.execute_tool()` calls Python handlers directly.  No network
transport is used for the core warehouse tools.  The HTTP/WebSocket transport in `client.py`
is unused by the current production path.

---

## Transport status

| Transport | Status |
|---|---|
| HTTP (aiohttp) | Implemented in `client.py`; not exercised by production path |
| WebSocket | Implemented in `client.py`; not exercised |
| STDIO | Enum value in `MCPConnectionType`; **not implemented** (raises `ValueError`) |

---

## What can be retained

| Component | Recommendation |
|---|---|
| `security.py` | **KEEP** — transport-independent; plug into MCP v2 server directly |
| `parameter_validator.py` | **KEEP** — domain-specific validation rules; reuse in capability contracts |
| `monitoring.py` (metrics + alert) | **KEEP** — independent; wire structured log to new telemetry |
| `tool_discovery.py` | **MIGRATE NEXT** — replace polling with MCP `tools/list` from live servers |
| `tool_binding.py` | **MIGRATE NEXT** — replace heuristic binding with CapabilityRegistry routing |
| `tool_routing.py` | **MIGRATE NEXT** — fold into ModelGateway routing + CapabilityRegistry |
| `tool_validation.py` | **MIGRATE NEXT** — Pydantic v2 contracts replace this layer |
| `base.py` (`MCPAdapter` / `MCPManager`) | **DEPRECATE** — replace with official MCP server + `InventoryProvider` Protocol |
| `server.py` | **DEPRECATE** — replace with `FastMCP` (official SDK) |
| `client.py` | **DEPRECATE** — replace with `MAIWMCPClient` (official SDK) |
| `adapters/` | **WRAP** — existing adapters wrap working backends; Phase 2 wraps the inventory backend; others migrate as vertical slices are built |
| `rollback.py` | **DEPRECATE** — stubs; real rollback is the `MODEL_GATEWAY_ENABLED=false` flag from Phase 1 |
| `service_discovery.py` | **DEPRECATE** — replace with `CapabilityRegistry` |
| MCP agents (`mcp_*.py`) | **KEEP TEMPORARILY** — preserve while new skill path is proven; migrate in Phase 3 |
| Planner graphs | **KEEP TEMPORARILY** — `mcp_integrated_planner_graph.py` is production; migrate after agent-to-skill refactor |

---

## Legacy technical debt catalogue

| Symbol | File | Classification |
|---|---|---|
| `MCPServer` | `server.py` | DEPRECATE — replace with FastMCP |
| `MCPClient` | `client.py` | DEPRECATE — replace with MAIWMCPClient |
| `MCPAdapter` | `base.py` | DEPRECATE — replace with InventoryProvider Protocol |
| `MCPManager` | `base.py` | DEPRECATE — replace with CapabilityRegistry |
| `ToolDiscoveryService` | `tool_discovery.py` | MIGRATE NEXT |
| `ToolBindingService` | `tool_binding.py` | MIGRATE NEXT |
| `ToolRoutingService` | `tool_routing.py` | MIGRATE NEXT |
| `ToolValidationService` | `tool_validation.py` | MIGRATE NEXT |
| `MCPRollbackManager` | `rollback.py` | DEPRECATE |
| `ServiceRegistry` | `service_discovery.py` | DEPRECATE |
| `MCPEquipmentAssetOperationsAgent` | `mcp_equipment_agent.py` | KEEP TEMPORARILY |
| `MCPSafetyComplianceAgent` | `mcp_safety_agent.py` | KEEP TEMPORARILY |
| `MCPOperationsCoordinationAgent` | `mcp_operations_agent.py` | KEEP TEMPORARILY |
| `mcp_planner_graph.py` | graphs | KEEP TEMPORARILY |
| `mcp_integrated_planner_graph.py` | graphs | KEEP TEMPORARILY |

**Removal condition:** Each item above is removed when the corresponding MCP v2 vertical
slice proves equivalent behavior and its agent path is covered by updated contract tests.

---

## Package status

| Package | Location | Status |
|---|---|---|
| `mcp` (official SDK) | Already installed (`mcp==1.27.0`) | Ready — was not in MAIW `pyproject.toml` |
| Custom MCP protocol impl | `src/api/services/mcp/` | In production; DO NOT delete yet |
| `maiw-mcp` (new shared package) | `packages/maiw-mcp/` | Phase 2 — new |

---

## Tests

12 existing MCP test files — all test the custom `src.api.services.mcp.*` path.
None import the official `mcp` SDK.  None exercise a real network transport.

New Phase 2 tests (`tests/mcp/`, `tests/contract/`) will exercise the official protocol path.
