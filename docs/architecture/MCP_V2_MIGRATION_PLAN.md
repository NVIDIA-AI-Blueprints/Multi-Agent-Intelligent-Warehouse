# MCP v2 Migration Plan
## Multi-Agent Intelligent Warehouse (MAIW)

**Date:** 2026-08-20  
**Audience:** Platform Engineers, Agent Platform Team, Warehouse Domain Teams  
**Status:** Phase 2B (SDK v1→v2 migration) IMPLEMENTED — see [MCP_V2_ARCHITECTURE.md](MCP_V2_ARCHITECTURE.md)

---

## Implementation Status (Phase 2 — 2026-08-20)

Phase 2B upgraded the MCP foundation from SDK 1.27.0 to 2.0.0 (protocol 2026-07-28)
while preserving all Phase 2 behavior.  The migration plan phases below describe the
full migration; the table shows what is already done.

| Item | Status |
|------|--------|
| `maiw-mcp` package (editable install) | **Done** — `packages/maiw-mcp/`, `mcp>=2.0.0,<3` |
| `maiw_mcp/errors.py` typed hierarchy | **Done** — 8 typed exceptions |
| `maiw_mcp/contracts/common.py` CapabilityMetadata | **Done** |
| `maiw_mcp/contracts/inventory.py` | **Done** — Request, Result, Location + 2 metadata constants |
| `maiw_mcp/registry/registry.py` CapabilityRegistry | **Done** — from_env() reads MAIW_MCP_SERVER_INVENTORY_URL |
| `maiw_mcp/telemetry/telemetry.py` CapabilityTelemetry | **Done** — adds `mcp_sdk_version`, `mcp_protocol_version` fields |
| `maiw_mcp/auth/auth.py` MCPAuthConfig | **Done** — bearer token from MAIW_MCP_API_KEY |
| `maiw_mcp/client/client.py` MAIWMCPClient | **Done** — `Client(url)` (MCP v2, no ClientSession) |
| `maiw_mcp/testing/mock_server.py` MockInventoryServer | **Done** — `Client(server)` in-memory, v2 API |
| `maiw_mcp/testing/conformance.py` run_inventory_conformance | **Done** — 8 checks, v2 Client |
| `maiw_mcp/testing/fixtures.py` make_inventory_result | **Done** |
| `mcp_servers/inventory/provider.py` InventoryProvider Protocol | **Done** + MockInventoryProvider |
| `mcp_servers/inventory/adapters/maiw_backend.py` MAIWInventoryAdapter | **Done** — wraps InventoryQueries |
| `mcp_servers/inventory/server.py` MCPServer (was FastMCP) | **Done** — stateless_http=True for K8s |
| `src/api/skills/inventory.py` InventoryLookupSkill | **Done** — unchanged (skill API stable) |
| `OperationsCoordinationAgent` inventory_skill wiring | **Done** — unchanged (graceful degradation) |
| `tests/contract/test_inventory_capability.py` | **Done** — 37 tests, all passing |
| `tests/mcp/test_inventory_mcp_server.py` | **Done** — 31 tests (added 10 v2-specific + stateless) |
| `docs/architecture/MCP_V2_ARCHITECTURE.md` | **Done** — updated for v2 API |
| `docs/architecture/MCP_V2_MIGRATION_PLAN.md` | **Done** — updated implementation status |
| OAuth 2.0 / scope enforcement | Deferred to Plan Phase 3 |
| ConnectionPool / CapabilityRouter | Deferred to Plan Phase 1 (full inventory server) |
| Remaining domain servers (equipment, labor, safety, forecasting, documents) | Deferred to Plan Phases 2–4 |

**SDK migration:** mcp 1.27.0 → mcp 2.0.0 (protocol 2026-07-28)

**Test totals as of 2026-08-20:** 185 passed (117 ModelGateway + 37 contract + 31 MCP protocol), 0 failed, 0 skipped.

---

## Table of Contents

1. [Current MCP/Tool Architecture](#1-current-mcptool-architecture)
2. [Gap vs Official MCP Python SDK v2](#2-gap-vs-official-mcp-python-sdk-v2)
3. [maiw-mcp Package Design](#3-maiw-mcp-package-design)
4. [MCP Server Boundaries](#4-mcp-server-boundaries)
5. [Warehouse Capability Contracts](#5-warehouse-capability-contracts)
6. [First Vertical Slice: Inventory MCP Server](#6-first-vertical-slice-inventory-mcp-server)
7. [Migration Sequence](#7-migration-sequence)
8. [Definition of Done](#8-definition-of-done)

---

## 1. Current MCP/Tool Architecture

### 1.1 Is the Official MCP Python SDK Used Today?

No. The official Anthropic `mcp` package (version 1.27.0) is installed in a separate virtualenv at `/home/nvidia/nvidia-wms-workshop/.venv/` and is not listed in `/home/nvidia/Multi-Agent-Intelligent-Warehouse/requirements.txt` or `pyproject.toml`. It is not imported anywhere in `src/`. Every MCP primitive in MAIW is a fully in-house implementation.

### 1.2 Custom Tool Abstractions

The custom implementation lives entirely in `src/api/services/mcp/` and consists of the following layers:

**Protocol layer (`server.py`, `client.py`)**

`MCPServer` implements JSON-RPC 2.0 message dispatch in-process with protocol version `2024-11-05`. It handles eight registered request methods: `tools/list`, `tools/call`, `resources/list`, `resources/read`, `prompts/list`, `prompts/get`, `initialize`, and `ping`. Tools are stored as `MCPTool` dataclasses (`name`, `description`, `MCPToolType` enum, `parameters` dict, `handler` callable). `execute_tool(name, arguments)` calls `tool.handler(arguments)` directly — there is no transport layer involved.

`MCPClient` supports three connection types via `MCPConnectionType` enum: `HTTP` (aiohttp), `WEBSOCKET` (websockets library), and `STDIO`. In practice, because `MCPServer` is in-process, the client side is not used for the primary agent path. The client's `call_tool()` sends a `tools/call` JSON-RPC request, but this is dead-code in the active graph.

**Adapter layer (`base.py`, `adapters/`)**

`MCPAdapter` is an abstract base with `tools: Dict[str, MCPTool]`, `resources`, `prompts`, and abstract `initialize()`, `connect()`, `disconnect()`, `health_check()` methods. Concrete subclasses are:

- `EquipmentMCPAdapter` — wraps `EquipmentAssetTools` (4 exposed tools)
- `OperationsMCPAdapter` — wraps `OperationsActionTools` (4 exposed tools)
- `SafetyMCPAdapter` — wraps `SafetyActionTools` (4 exposed tools)
- `ForecastingMCPAdapter` — wraps `ForecastingActionTools` (6 exposed tools)
- `WMSAdapter`, `ERPAdapter`, `IoTAdapter`, `RFIDBarcodeAdapter`, `TimeAttendanceAdapter` — integration adapters not yet registered in the active planner graph

**Discovery layer (`tool_discovery.py`)**

`ToolDiscoveryService` discovers tools from registered sources (mcp_server, mcp_adapter, external). It categorizes tools into a `ToolCategory` enum (DATA_ACCESS, DATA_MODIFICATION, ANALYSIS, REPORTING, INTEGRATION, UTILITY, SAFETY, EQUIPMENT, OPERATIONS, FORECASTING). Each discovered tool is wrapped in a `DiscoveredTool` dataclass that carries a `tool_id` (UUID), name, description, category, source, parameters, capabilities, usage stats, and success rate. A background discovery loop runs every 30 seconds and a cleanup loop runs every 5 minutes.

**Supplementary services**

- `tool_binding.py` — `ToolBindingService` with EXACT_MATCH, FUZZY_MATCH, SEMANTIC_MATCH, CATEGORY_MATCH, PERFORMANCE_BASED binding strategies and SEQUENTIAL, PARALLEL, PIPELINE, CONDITIONAL execution modes
- `tool_routing.py` — `ToolRoutingService`, initialized to `None` in the active graph (commented out)
- `parameter_validator.py` — `MCPParameterValidator` validates types, required fields, formats, and ranges; called in `EquipmentMCPAdapter.execute_tool()` before dispatch
- `security.py` — pattern-based blocklist enforcement (see section 1.6)

### 1.3 Tool Registration

Registration follows a four-step path:

1. `EquipmentMCPAdapter._register_tools()` (and equivalent on each adapter) populates `self.tools: Dict[str, MCPTool]` with `MCPTool` objects. Schemas are inline Python dicts following JSON Schema conventions. The handler callable points to an internal `_handle_*` method on the adapter.

2. `src/api/routers/mcp.py → _register_mcp_adapters()` calls `tool_discovery.register_discovery_source(name, adapter, "mcp_adapter")` for four adapters: `"equipment_asset_tools"`, `"operations_action_tools"`, `"safety_action_tools"`, `"forecasting_action_tools"`. The document adapter is not registered; it uses direct API endpoints.

3. `ToolDiscoveryService.discover_tools_from_source()` calls `_discover_from_mcp_adapter()`, iterates `adapter.tools`, and calls `_register_discovered_tool()` for each entry.

4. `_register_discovered_tool()` runs the security gate (`is_tool_blocked()`, `validate_tool_security()`) then stores the `DiscoveredTool` in `discovered_tools: Dict[str, DiscoveredTool]`.

### 1.4 Agent Discovery and Call Path

At graph initialization, the `_mcp_route_intent()` node calls `tool_discovery.get_available_tools()` and stores the catalog in `state["available_tools"]`. Individual agent classes (`MCPEquipmentAssetOperationsAgent`, etc.) receive this catalog through the graph state. Inside each agent:

1. `_discover_relevant_tools(query)` filters the catalog by domain keywords and category
2. `_create_tool_execution_plan()` selects ordered tool invocations
3. `_execute_tool_plan()` calls `tool_discovery.execute_tool(tool_id, arguments)` which dispatches to `adapter._handle_*(arguments)` which delegates to the underlying action tool class method
4. The action tool method performs the actual DB query or WMS/ERP API call
5. Results are passed back up to `_generate_response_with_tools()` which calls NIM LLM to produce `natural_language`

`ToolNode` and the `@tool` decorator from `langchain_core` are imported in `mcp_integrated_planner_graph.py` but never instantiated or used. LangGraph's `bind_tools()` pattern is absent throughout.

### 1.5 Transport Mechanism

In the active production code path, transport is effectively zero-hop: the `MCPServer` and all adapter handlers execute in the same Python process as the FastAPI application. The `MCPClient` HTTP and WebSocket connection types exist in code but are not exercised. The sole real network call in the tool path is the underlying `asyncpg` pool call (PostgreSQL) or the WMS/ERP httpx call made by the action tool implementation itself.

### 1.6 Error Handling

Each action tool method wraps its body in `try/except Exception`, logs the error, and returns a fallback dataclass or `{"success": False, "message": ..., "error": ...}` dict — never raising to the caller.

`MCPAdapter.execute_tool()` re-raises after logging. `ToolDiscoveryService.execute_tool()` calls `_update_usage_stats(success=False)` on exception and re-raises. The LangGraph graph wraps all agent calls with `asyncio.wait_for(..., timeout=...)`, catches `asyncio.TimeoutError`, and returns a user-friendly timeout message with `"response_type": "timeout"` and `"confidence": 0.3`. A graph-level fallback (`_create_fallback_response()`) handles any unhandled exception with a keyword-matched simple reply. Error strings are capped at 200 characters in `_create_error_response()` to prevent leakage.

Per-tool execution timeout: 15 seconds (hardcoded in `_execute_tool_plan`). Agent-level timeouts: 90s (simple) / 100s (complex) / 180s (reasoning). Graph-level timeouts: 120–460s depending on complexity and reasoning flag.

### 1.7 Authentication

- **LLM:** `NVIDIA_API_KEY` env var, passed as `Authorization: Bearer` in every NIM httpx request.
- **Database:** `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DB_HOST`, `DB_PORT` env vars; no per-query auth.
- **WMS/ERP:** credentials passed in adapter config dicts; SAP uses httpx `BasicAuth`.
- **MCP tool layer:** None. No RBAC is enforced. `adjust_reorder_point()` docstring references a "planner" role but the code does not check it. The security gate in `security.py` is exclusively pattern-based blocklist logic (30+ regex patterns blocking code execution primitives, CVE-2024-28088 path traversal), not identity-based authorization.

### 1.8 Schema Validation

Tool parameter schemas are inline Python dicts in each `_register_tools()` method. `MCPParameterValidator.validate_tool_parameters()` validates types, required fields, formats, and value ranges and is called before dispatch in the equipment adapter. The other adapters do not call the validator before dispatching. The `MCPServer._handle_tools_list()` response formats schemas as `{"inputSchema": {"type": "object", "properties": {...}, "required": [...]}}`, which matches the MCP specification format, but this endpoint is not consumed by any live graph node — tools are discovered through the adapter layer, not through the JSON-RPC tools/list path.

---

## 2. Gap vs Official MCP Python SDK v2

The following table enumerates every gap between the current implementation and a compliant `mcp` SDK v2 deployment.

| Area | Current State | Required Change |
|---|---|---|
| **SDK dependency** | No `mcp` package in requirements | Add `mcp>=1.27.0` to `requirements.txt` and `pyproject.toml` |
| **Server runtime** | Bespoke `MCPServer` JSON-RPC dispatcher in-process | Replace with `mcp.server.FastMCP` or `mcp.server.Server` instances, each running as an independent process/container |
| **Transport** | Zero-hop in-process function calls | Streamable HTTP (SSE + POST) for production; stdio for local dev and testing. Client uses `mcp.client.streamable_http.streamablehttp_client` |
| **Session and lifecycle** | No session concept; adapters initialized once at app startup | SDK manages `initialize` / `initialized` handshake, capability negotiation, and session lifecycle per connection |
| **Tool registration** | `MCPTool` dataclass + manual dict iteration | `@server.tool()` decorator on each capability function; SDK handles `tools/list` and `tools/call` dispatch automatically |
| **Resource protocol** | Stub methods on `MCPAdapter`; no real resource URIs | Implement `@server.resource()` for domain data resources (e.g., `warehouse://inventory/{sku}`, `warehouse://equipment/{asset_id}`) |
| **Prompt protocol** | Stub methods; no prompts defined | Implement `@server.prompt()` for warehouse-specific prompt templates |
| **Schema format** | Inline dicts in `_register_tools()`; not validated against JSON Schema draft 7 | Use Pydantic models as tool input types; SDK generates `inputSchema` automatically via `pydantic_core` |
| **Error format** | Ad-hoc `{"success": False, "error": "..."}` returns | Raise `mcp.types.McpError` with proper error codes (`-32602 InvalidParams`, `-32603 InternalError`) so the SDK returns conformant JSON-RPC error objects |
| **Parameter validation** | Only `EquipmentMCPAdapter` calls `MCPParameterValidator` | SDK enforces Pydantic model validation at the tool boundary for every server uniformly |
| **Discovery** | Custom `ToolDiscoveryService` with UUID-keyed registry, 30s polling loop | Replace polling with SDK `tools/list` over a persistent connection; implement a thin `CapabilityClient` wrapper for agent-side discovery |
| **Authentication** | No auth at tool layer | Add `mcp.server.auth` OAuth 2.1 resource server support for tool-level authorization; map warehouse RBAC roles to OAuth scopes |
| **RBAC enforcement** | Documented but not implemented (e.g., `adjust_reorder_point` planner role) | Enforce scopes per capability: read-only tools require `warehouse:read`, write tools require `warehouse:write:{domain}`, approval-required tools require `warehouse:approve` |
| **Multi-server routing** | Single `MCPManager` with one in-process server | `CapabilityRouter` selects target MCP server by canonical capability name prefix; `ConnectionPool` manages per-server connections |
| **Capability naming** | Flat names (`get_equipment_status`, `create_task`) with no namespace | Canonical names using dot notation: `warehouse.equipment.get_status`, `warehouse.operations.create_task` |
| **Telemetry** | Usage stats in `DiscoveredTool.usage_stats` dict; no structured tracing | Emit OpenTelemetry spans for every `tools/call` with attributes: `mcp.server`, `mcp.tool`, `mcp.session_id`, `warehouse.domain`, `warehouse.risk_level` |
| **Health** | `health_check()` abstract method on adapters; not wired to a health endpoint | Each MCP server exposes `/health` (liveness) and `/ready` (readiness); orchestrator polls these |
| **In-process only** | All tool execution in FastAPI process; no isolation | Each domain MCP server runs as a separate process/container; failures in one domain do not crash the planner |
| **Checkpointing** | Explicitly disabled to avoid CVE-2025-8709 | Remains disabled; trajectory store (separate from LangGraph checkpointer) captures execution records via the `mcp` SDK's progress notification mechanism |
| **Streaming tool results** | Not implemented | SDK supports `mcp.types.TextContent`, `ImageContent`, `EmbeddedResource` in tool results; large results (e.g., batch forecasts) should use resource streaming |

---

## 3. maiw-mcp Package Design

The `maiw-mcp` package is a standalone Python library installable by all components (servers, agents, tests). It provides the canonical contracts, the client pool, and the test harness. It has no dependency on the FastAPI application.

```
maiw-mcp/
├── pyproject.toml                  # mcp>=1.27.0, pydantic>=2.0, opentelemetry-sdk
├── src/
│   └── maiw_mcp/
│       ├── __init__.py
│       ├── core/
│       │   ├── client.py           # WarehouseMCPClient: thin wrapper around mcp.ClientSession
│       │   ├── registry.py         # CapabilityRegistry: maps canonical names to server URLs
│       │   ├── discovery.py        # CapabilityDiscovery: calls tools/list on startup; refreshes on reconnect
│       │   ├── auth.py             # OAuthTokenProvider: fetches/caches/refreshes bearer tokens per server
│       │   ├── errors.py           # WarehouseMcpError hierarchy mapping to MCP error codes
│       │   ├── telemetry.py        # OTel span helpers: start_tool_span(), record_tool_result()
│       │   └── health.py           # HealthAggregator: polls /health on all registered servers
│       ├── contracts/
│       │   ├── __init__.py         # Re-exports all Input/Output models
│       │   ├── inventory.py        # StockCheckInput/Output, ReserveInventoryInput/Output, etc.
│       │   ├── wave.py             # CreatePickWaveInput/Output, OptimizePickPathInput/Output
│       │   ├── labor.py            # GetWorkforceStatusInput/Output, CreateTaskInput/Output, etc.
│       │   ├── equipment.py        # GetEquipmentStatusInput/Output, AssignEquipmentInput/Output, etc.
│       │   ├── orders.py           # (future) PurchaseRequisitionInput/Output
│       │   ├── safety.py           # LogIncidentInput/Output, BroadcastAlertInput/Output, etc.
│       │   ├── forecasting.py      # GetForecastInput/Output, BatchForecastInput/Output, etc.
│       │   ├── optimization.py     # (future) ReslottingInput/Output, RebalanceWorkloadInput/Output
│       │   └── simulation.py       # (future) simulation contracts for digital twin
│       ├── client/
│       │   ├── pool.py             # ConnectionPool: per-server mcp.ClientSession lifecycle
│       │   ├── router.py           # CapabilityRouter: routes canonical name to server; fallback policy
│       │   └── capability_client.py# WarehouseCapabilityClient: call_capability(name, input_model) -> output_model
│       └── testing/
│           ├── conformance.py      # MCPConformanceChecker: runs protocol-level conformance suite
│           ├── fixtures.py         # pytest fixtures: mcp_server, capability_client, warehouse_db
│           ├── mock_server.py      # InMemoryMCPServer: in-process mcp.server for unit tests
│           └── contract_tests.py   # ContractTestSuite: parameterized tests for every canonical capability
└── tests/
    ├── unit/
    └── integration/
```

**Module responsibilities:**

`core/client.py` — wraps `mcp.ClientSession` from the official SDK. Adds automatic reconnect on transport failure, configurable backoff, and injects the OTel span context into each JSON-RPC request. Agents import this instead of calling `ToolDiscoveryService` directly.

`core/registry.py` — a `CapabilityRegistry` that maps canonical names (e.g., `warehouse.inventory.check_stock`) to the `(server_url, transport_type)` that owns them. Bootstrapped from environment variables or a config file; refreshed dynamically when a server updates its `tools/list`.

`core/discovery.py` — on startup, calls `tools/list` on every registered server URL and populates the registry. On reconnect after a server restart, rediscovers the tool list. This replaces the 30-second polling loop in `ToolDiscoveryService`.

`core/auth.py` — `OAuthTokenProvider` holds a client credentials grant per server. Calls the configured token endpoint, caches the token with a 60-second expiry buffer, and injects it as a bearer header. Individual action-level RBAC checking (e.g., `warehouse:approve` scope for `adjust_reorder_point`) is validated here before the call is dispatched.

`core/errors.py` — typed error hierarchy: `CapabilityNotFoundError`, `CapabilityTimeoutError`, `ApprovalRequiredError`, `ValidationError`, `RiskLimitExceededError`. Each maps to an MCP JSON-RPC error code and an HTTP status for the REST fallback.

`core/telemetry.py` — thin wrappers over the OpenTelemetry SDK. `start_tool_span(capability_name, input_data)` opens a span with standard MCP attributes plus warehouse-specific ones (`warehouse.domain`, `warehouse.risk_level`, `warehouse.idempotency_key`). `record_tool_result(span, output, success)` records outcome and closes the span. The trajectory store hooks into these spans.

`core/health.py` — `HealthAggregator.check_all()` concurrently GETs `/health` from every registered server. Returns a `Dict[str, HealthStatus]` consumed by the FastAPI `/health` and `/ready` endpoints.

`contracts/` — the canonical vendor-neutral warehouse semantic layer. Every input and output is a Pydantic v2 `BaseModel`. Models are shared between servers and clients so contract changes are detectable at import time. See Section 5 for the top-five contract specifications.

`client/pool.py` — `ConnectionPool` manages one `mcp.ClientSession` per server. Implements `acquire()` / `release()` semantics, connection health checks, and max-pool-size limits. Uses `anyio` task groups for concurrent initialization.

`client/router.py` — `CapabilityRouter.route(capability_name)` looks up the server URL from the registry, acquires a session from the pool, and returns the session. Applies fallback policy (try secondary server URL, then raise `CapabilityNotFoundError`).

`client/capability_client.py` — the primary interface for agents. `call_capability(canonical_name, input_model) -> OutputModel` serializes the Pydantic input, calls the router, sends `tools/call`, deserializes the response into the output model, and records the OTel span. Agents call this instead of `tool_discovery.execute_tool()`.

`testing/mock_server.py` — `InMemoryMCPServer` instantiates a real `mcp.server.FastMCP` in-process but registers mock handlers that return fixture data. Used in agent unit tests so the agent code runs against real MCP protocol paths without needing a running server process.

`testing/conformance.py` — `MCPConformanceChecker` tests that a given server URL correctly implements: `initialize` handshake, `tools/list` returns valid schemas, `tools/call` returns typed results, error payloads conform to JSON-RPC spec, and all required MCP capabilities are advertised.

`testing/contract_tests.py` — `ContractTestSuite` is a parameterized pytest class. For each canonical capability, it sends a valid input and asserts the output matches the contract model; sends an invalid input and asserts a `ValidationError` is returned; and tests idempotency by calling a write capability twice with the same idempotency key.

---

## 4. MCP Server Boundaries

Each server below is an independently deployable Python process exposing streamable HTTP transport. Domain boundaries follow the existing adapter structure but correct the gaps where action tools were split across multiple files for the same domain.

### 4.1 Inventory MCP Server (`maiw-mcp-inventory`)

**Existing tools/functions migrating here:**

From `src/api/agents/inventory/equipment_action_tools.py`:
- `check_stock(sku, site, locations)` → `warehouse.inventory.check_stock`
- `reserve_inventory(sku, qty, order_id, hold_until)` → `warehouse.inventory.reserve`
- `create_replenishment_task(sku, from_location, to_location, qty, priority)` → `warehouse.inventory.create_replenishment`
- `generate_purchase_requisition(...)` → `warehouse.inventory.generate_purchase_req`
- `adjust_reorder_point(sku, new_rp, rationale, user_id, requires_approval)` → `warehouse.inventory.adjust_reorder_point`
- `recommend_reslotting(sku, peak_velocity_window)` → `warehouse.inventory.recommend_reslotting`
- `start_cycle_count(sku, location, class_name, priority)` → `warehouse.inventory.start_cycle_count`
- `investigate_discrepancy(sku, location, expected_quantity, actual_quantity)` → `warehouse.inventory.investigate_discrepancy`

From `src/api/routers/inventory.py`: read endpoints become resources: `warehouse://inventory/{sku}`, `warehouse://inventory/movements`

**Current file locations:** `src/api/agents/inventory/equipment_action_tools.py`, `src/api/routers/inventory.py`, `src/retrieval/sql/inventory_queries.py`

**Scaling characteristics:** Read-heavy (check_stock, demand queries); write operations are low-frequency but latency-sensitive (reserve_inventory). Horizontally scalable behind a load balancer; stateless except for the asyncpg connection pool. The `reserve_inventory` capability requires row-level locking in PostgreSQL — connection pool sizing is the primary tuning knob.

**Domain boundary justification:** Inventory is the central record of "what do we have and where." It is referenced by every other domain but owns its own data. Separating it prevents the equipment, operations, and forecasting servers from coupling to inventory SQL queries directly.

---

### 4.2 WMS Integration MCP Server (`maiw-mcp-wms`)

**Existing tools/functions migrating here:**

From `src/api/services/integrations/wms/` and `src/api/services/mcp/adapters/wms_adapter.py`:
- WMS connection management
- Inventory sync (WMS → local DB)
- Task push/pull (create_task, assign_task routed through WMS)
- Order management
- Location lookups

From `src/api/agents/inventory/equipment_action_tools.py` (WMS-delegating methods):
- `reserve_inventory` (delegates to `WMSIntegrationService`)
- `create_replenishment_task`
- `adjust_reorder_point`
- `recommend_reslotting`
- `start_cycle_count`
- `investigate_discrepancy`

**Current file locations:** `src/api/services/integrations/wms/`, `src/api/routers/wms.py`, `src/api/services/mcp/adapters/wms_adapter.py`

**Scaling characteristics:** Throughput is bounded by the upstream WMS rate limits (SAP EWM, Manhattan, Oracle). Connection pooling per WMS vendor. Should be deployed with circuit breakers — WMS downtime must not cascade to the planner graph.

**Domain boundary justification:** Decouples the warehouse agent platform from vendor-specific WMS wire protocols. The Inventory MCP server calls this server for write operations, keeping local DB and WMS in sync through a single integration point.

---

### 4.3 Labor / Operations MCP Server (`maiw-mcp-labor`)

**Existing tools/functions migrating here:**

From `src/api/agents/operations/action_tools.py`:
- `assign_tasks` → `warehouse.labor.assign_tasks`
- `create_task` → `warehouse.labor.create_task`
- `assign_task` → `warehouse.labor.assign_task`
- `get_task_status` → `warehouse.labor.get_task_status`
- `get_workforce_status` → `warehouse.labor.get_workforce_status`
- `rebalance_workload` → `warehouse.labor.rebalance_workload`
- `generate_pick_wave` → `warehouse.labor.generate_pick_wave`
- `optimize_pick_paths` → `warehouse.labor.optimize_pick_paths`
- `manage_shift_schedule` → `warehouse.labor.manage_shift_schedule`
- `dock_scheduling` → `warehouse.labor.dock_scheduling`
- `dispatch_equipment` → `warehouse.labor.dispatch_equipment`
- `publish_kpis` → `warehouse.labor.publish_kpis`

From `src/api/services/mcp/adapters/operations_adapter.py`: wrapping is dissolved; tools register directly on the server.

**Current file locations:** `src/api/agents/operations/action_tools.py`, `src/api/routers/operations.py`, `src/api/services/mcp/adapters/operations_adapter.py`

**Scaling characteristics:** Moderate write throughput; pick wave generation is CPU-bound (optimization algorithm). Wave generation should be offloaded to a background task with progress notifications via MCP's `notifications/progress` mechanism. KPI publication is fire-and-forget.

**Domain boundary justification:** Labor/operations touches the `tasks`, `operations`, `operation_items`, and `workforce` tables directly. Keeping it separate from the inventory server prevents a slow wave generation from blocking stock checks.

---

### 4.4 Equipment MCP Server (`maiw-mcp-equipment`)

**Existing tools/functions migrating here:**

From `src/api/agents/inventory/equipment_asset_tools.py`:
- `get_equipment_status` → `warehouse.equipment.get_status`
- `assign_equipment` → `warehouse.equipment.assign`
- `release_equipment` → `warehouse.equipment.release`
- `get_equipment_telemetry` → `warehouse.equipment.get_telemetry`
- `schedule_maintenance` → `warehouse.equipment.schedule_maintenance`
- `get_maintenance_schedule` → `warehouse.equipment.get_maintenance_schedule`
- `get_equipment_utilization` → `warehouse.equipment.get_utilization`

From `src/api/agents/inventory/equipment_action_tools.py` (equipment-specific methods):
- `get_equipment_status(equipment_id)` (telemetry-based version) → merged with above
- `get_charger_status` → `warehouse.equipment.get_charger_status`

From `src/api/services/mcp/adapters/equipment_adapter.py`: wrapping dissolved.

**Current file locations:** `src/api/agents/inventory/equipment_asset_tools.py`, `src/api/agents/inventory/equipment_action_tools.py`, `src/api/routers/equipment.py`, `src/api/services/mcp/adapters/equipment_adapter.py`

**Scaling characteristics:** Telemetry reads are high-frequency (TimescaleDB hypertable queries). Equipment assignment writes are low-frequency but must be atomic (prevent double-assignment). The server should maintain a short in-process cache (30 seconds) for equipment status to reduce DB load from repeated polling by the planner.

**Domain boundary justification:** Equipment state (location, charge level, assignment) changes on a different cadence than inventory or labor. Isolating it allows the telemetry path to be tuned independently and prevents equipment polling storms from affecting other domains.

---

### 4.5 Safety MCP Server (`maiw-mcp-safety`)

**Existing tools/functions migrating here:**

From `src/api/agents/safety/action_tools.py`:
- `log_incident` → `warehouse.safety.log_incident`
- `start_checklist` → `warehouse.safety.start_checklist`
- `broadcast_alert` → `warehouse.safety.broadcast_alert`
- `lockout_tagout_request` → `warehouse.safety.lockout_tagout`
- `create_corrective_action` → `warehouse.safety.create_corrective_action`
- `retrieve_sds` → `warehouse.safety.retrieve_sds`
- `near_miss_capture` → `warehouse.safety.near_miss_capture`
- `get_safety_procedures` → `warehouse.safety.get_procedures`

From `src/api/services/mcp/adapters/safety_adapter.py`: wrapping dissolved.

**Current file locations:** `src/api/agents/safety/action_tools.py`, `src/api/routers/safety.py`, `src/api/services/mcp/adapters/safety_adapter.py`

**Scaling characteristics:** Low write throughput in normal operations; spike on incidents. `broadcast_alert` has hard latency requirements — it must reach IoT channels within 2 seconds. This server should have a dedicated connection to `IoTIntegrationService` and bypass the normal tool dispatch queue for severity >= HIGH alerts.

**Domain boundary justification:** Safety is the highest-risk domain. Isolating it ensures a planner bug or overloaded equipment server cannot delay an emergency broadcast. The DecisionEngine (target architecture) applies the strictest approval gates for write operations on this server.

---

### 4.6 Forecasting MCP Server (`maiw-mcp-forecasting`)

**Existing tools/functions migrating here:**

From `src/api/agents/forecasting/forecasting_action_tools.py`:
- `get_forecast` → `warehouse.forecasting.get_forecast`
- `get_batch_forecast` → `warehouse.forecasting.get_batch_forecast`
- `get_reorder_recommendations` → `warehouse.forecasting.get_reorder_recommendations`
- `get_model_performance` → `warehouse.forecasting.get_model_performance`
- `get_forecast_dashboard` → `warehouse.forecasting.get_dashboard`
- `get_business_intelligence` → `warehouse.forecasting.get_business_intelligence`

From `src/api/routers/advanced_forecasting.py`: REST endpoints become tools + resources. `ForecastResult` becomes a streamable MCP resource at `warehouse://forecasting/{sku}/{horizon_days}`.

From `src/api/services/mcp/adapters/forecasting_adapter.py`: wrapping dissolved.

**Current file locations:** `src/api/agents/forecasting/forecasting_action_tools.py`, `src/api/routers/advanced_forecasting.py`, `src/api/services/mcp/adapters/forecasting_adapter.py`, `scripts/forecasting/rapids_gpu_forecasting.py`

**Scaling characteristics:** Forecast reads are cache-friendly (results rarely change intraday). Batch forecasting (up to 100 SKUs) is the most resource-intensive tool and should return results via streaming content chunks rather than a single large JSON payload. The RAPIDS GPU training script remains a subprocess invoked by the training router — it is not exposed as an MCP tool.

**Domain boundary justification:** Forecasting is read-only from the agent perspective (no writes to core warehouse state). It is the most compute-intensive domain and benefits from independent horizontal scaling with GPU-capable nodes.

---

### 4.7 Document Processing MCP Server (`maiw-mcp-documents`)

**Existing tools/functions migrating here:**

From `src/api/agents/document/action_tools.py`:
- `upload_document` → `warehouse.documents.upload`
- `get_document_status` → `warehouse.documents.get_status`
- `extract_document_data` → `warehouse.documents.extract`
- `validate_document_quality` → `warehouse.documents.validate_quality`
- `search_documents` → `warehouse.documents.search`
- `get_document_analytics` → `warehouse.documents.get_analytics`
- `approve_document` → `warehouse.documents.approve`
- `reject_document` → `warehouse.documents.reject`

The six-stage NeMo pipeline (preprocessing, OCR, small LLM, embedding, judge, routing) remains internal to this server. The MCP interface exposes only document-level operations, hiding pipeline stages.

**Current file locations:** `src/api/agents/document/`, `src/api/routers/documents.py`

**Scaling characteristics:** Highly heterogeneous — OCR and LLM judge are GPU-bound; embedding is moderate; routing is CPU-bound. This server should be decomposed internally into an async pipeline with per-stage queuing, but the MCP interface stays coarse-grained. Upload returns immediately with a `document_id`; status polling via `warehouse.documents.get_status` shows stage progress.

**Domain boundary justification:** Document processing is the only domain that does not interact with real-time warehouse state during processing. It is self-contained with its own Postgres tables (`documents`, `processing_stages`, `extraction_results`, etc.) and Milvus collection.

---

### 4.8 Optimization MCP Server (`maiw-mcp-optimization`) — Future

Consolidates `recommend_reslotting`, `optimize_pick_paths`, `rebalance_workload`, `dock_scheduling` into a dedicated solver service. These are currently scattered across the inventory and operations action tools. This server calls back into the Inventory and Labor servers for state, runs the optimization, and returns a plan. No writes — the calling agent submits the plan to the Labor or Inventory server for execution. Planned for Phase 4.

---

### 4.9 Simulation MCP Server (`maiw-mcp-simulation`) — Future

Digital twin integration. No existing code. Planned for Phase 5 as part of the intelligence flywheel.

---

## 5. Warehouse Capability Contracts

The five most important capabilities by risk level and call frequency:

---

### 5.1 `warehouse.inventory.check_stock`

**Canonical name:** `warehouse.inventory.check_stock`  
**Risk level:** READ — no side effects  
**Idempotency:** Inherently idempotent (read only)  
**Approval required:** No  
**Side effects:** None

```python
from pydantic import BaseModel, Field
from typing import Optional, List
from decimal import Decimal

class StockCheckInput(BaseModel):
    sku: str = Field(..., description="Stock keeping unit identifier", min_length=1, max_length=50)
    site: Optional[str] = Field(None, description="Site/warehouse code; None = all sites")
    locations: Optional[List[str]] = Field(None, description="Specific location codes to check")
    include_reserved: bool = Field(True, description="Include reserved quantity in response")

class LocationStock(BaseModel):
    location_code: str
    on_hand_quantity: int
    reserved_quantity: int
    available_quantity: int
    last_counted_at: Optional[str]  # ISO 8601

class StockCheckOutput(BaseModel):
    sku: str
    total_on_hand: int
    total_reserved: int
    total_available: int
    reorder_point: int
    below_reorder_point: bool
    locations: List[LocationStock]
    freshness_timestamp: str   # ISO 8601; when the DB row was last updated
    source: str = "warehouse.inventory"
```

---

### 5.2 `warehouse.inventory.reserve`

**Canonical name:** `warehouse.inventory.reserve`  
**Risk level:** WRITE — modifies `inventory_locations.reserved_quantity`  
**Idempotency:** YES — idempotent on `idempotency_key`. Repeated calls with the same key return the existing reservation without incrementing stock.  
**Approval required:** No (system-initiated reservations); Yes for manual override reservations above max-hold threshold  
**Side effects:** Decrements `available_quantity` computed column; may trigger reorder recommendation event

```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from enum import Enum

class ReservationStatus(str, Enum):
    CONFIRMED = "confirmed"
    PARTIAL = "partial"       # Requested qty exceeded available; partial reserved
    FAILED = "failed"
    ALREADY_EXISTS = "already_exists"  # Idempotent replay

class ReserveInventoryInput(BaseModel):
    sku: str = Field(..., min_length=1, max_length=50)
    quantity: int = Field(..., gt=0, le=10000)
    order_id: str = Field(..., description="Order or task ID that owns this reservation")
    idempotency_key: str = Field(..., description="UUID v4; client-generated. Re-submitting with same key is a no-op")
    hold_until: Optional[datetime] = Field(None, description="Expiry; None = indefinite hold")
    location_preference: Optional[str] = Field(None, description="Preferred pick location code")
    allow_partial: bool = Field(False, description="Accept partial reservation if full qty unavailable")

class ReserveInventoryOutput(BaseModel):
    reservation_id: str          # UUID assigned by the server
    idempotency_key: str
    sku: str
    requested_quantity: int
    reserved_quantity: int
    status: ReservationStatus
    location_code: Optional[str]
    hold_until: Optional[str]    # ISO 8601
    created_at: str              # ISO 8601
    message: Optional[str]       # Human-readable explanation for partial or failed
```

---

### 5.3 `warehouse.safety.broadcast_alert`

**Canonical name:** `warehouse.safety.broadcast_alert`  
**Risk level:** WRITE — emits real-world alerts via IoT channels; cannot be undone  
**Idempotency:** Idempotent on `idempotency_key` within a 60-second deduplication window. After 60 seconds, the same key is treated as a new alert.  
**Approval required:** No for severity HIGH or CRITICAL (emergency path, human approval would introduce fatal delay). Yes for severity LOW/MEDIUM sent outside standard operating hours.  
**Side effects:** Triggers IoT alert broadcast; creates `safety_incidents` or `safety_alerts` DB row; notifies supervisors via configured channels

```python
from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum

class AlertSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class AlertChannel(str, Enum):
    PA_SYSTEM = "pa_system"
    MOBILE_DEVICE = "mobile_device"
    DISPLAY_BOARD = "display_board"
    EMAIL = "email"
    SMS = "sms"
    IOT_BEACON = "iot_beacon"

class BroadcastAlertInput(BaseModel):
    message: str = Field(..., min_length=5, max_length=500)
    zone: str = Field(..., description="Warehouse zone code; 'ALL' for facility-wide")
    severity: AlertSeverity = Field(..., description="Determines approval bypass and channel priority")
    channels: List[AlertChannel] = Field(default_factory=lambda: [AlertChannel.PA_SYSTEM, AlertChannel.MOBILE_DEVICE])
    idempotency_key: str = Field(..., description="UUID v4; prevents duplicate broadcasts")
    reporter: str = Field(..., description="User ID or system ID initiating the alert")
    related_incident_id: Optional[str] = Field(None, description="Link to an existing SafetyIncident")

class BroadcastAlertOutput(BaseModel):
    alert_id: str                         # UUID assigned by the server
    idempotency_key: str
    message: str
    zone: str
    severity: AlertSeverity
    channels_notified: List[AlertChannel]
    channels_failed: List[AlertChannel]   # Empty on full success
    broadcast_at: str                     # ISO 8601
    delivery_latency_ms: Optional[int]    # Measured end-to-end to IoT layer
    approval_bypassed: bool               # True when severity >= HIGH
```

---

### 5.4 `warehouse.equipment.assign`

**Canonical name:** `warehouse.equipment.assign`  
**Risk level:** WRITE — modifies `equipment_assignments` table; changes physical asset ownership  
**Idempotency:** YES on `idempotency_key`; if the same key arrives twice the second call returns the existing assignment  
**Approval required:** No for standard assignment types. Yes for reassignment when asset is currently assigned to another user.  
**Side effects:** Updates `equipment_assets.status`, creates `equipment_assignments` row, may notify current assignee via `dispatch_equipment`

```python
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

class AssignmentType(str, Enum):
    STANDARD = "standard"
    EMERGENCY = "emergency"
    MAINTENANCE = "maintenance"
    TRAINING = "training"

class AssignEquipmentInput(BaseModel):
    asset_id: str = Field(..., min_length=1, max_length=50)
    user_id: Optional[str] = Field(None, description="Assignee user ID; None for task-only assignment")
    task_id: Optional[str] = Field(None, description="Task that triggered this assignment")
    assignment_type: AssignmentType = Field(AssignmentType.STANDARD)
    idempotency_key: str = Field(..., description="UUID v4")
    force_reassign: bool = Field(False, description="Reassign even if currently assigned; triggers approval check")
    duration_hours: Optional[float] = Field(None, gt=0, le=24, description="Expected hold duration; None = indefinite")

class AssignEquipmentOutput(BaseModel):
    assignment_id: str              # BIGSERIAL from equipment_assignments
    idempotency_key: str
    asset_id: str
    user_id: Optional[str]
    task_id: Optional[str]
    assignment_type: AssignmentType
    assigned_at: str                # ISO 8601
    expires_at: Optional[str]       # ISO 8601 if duration_hours provided
    previous_assignee: Optional[str] # Populated if force_reassign
    approval_pending: bool           # True if force_reassign requires approval
```

---

### 5.5 `warehouse.inventory.adjust_reorder_point`

**Canonical name:** `warehouse.inventory.adjust_reorder_point`  
**Risk level:** WRITE — modifies replenishment policy; wrong values cause stockouts or excess inventory  
**Idempotency:** YES on `(sku, new_reorder_point, idempotency_key)`. A replay with the same three values returns the existing record.  
**Approval required:** YES — always requires `warehouse:approve` scope. The capability client will raise `ApprovalRequiredError` if the caller does not hold this scope. The server creates a pending approval record and returns status `PENDING_APPROVAL`; execution is deferred until an authorized approver calls `warehouse.inventory.approve_reorder_adjustment`.  
**Side effects:** When approved, updates `inventory_locations.reorder_point`; emits a policy change audit log entry

```python
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

class ReorderAdjustmentStatus(str, Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED_APPLIED = "approved_applied"
    REJECTED = "rejected"
    REPLAYED = "replayed"         # Idempotent replay of an already-applied change

class AdjustReorderPointInput(BaseModel):
    sku: str = Field(..., min_length=1, max_length=50)
    new_reorder_point: int = Field(..., ge=0, le=100000)
    rationale: str = Field(..., min_length=10, max_length=1000, description="Business justification recorded in audit log")
    user_id: str = Field(..., description="Requesting user; must hold warehouse:approve scope for execution")
    idempotency_key: str = Field(..., description="UUID v4")
    requires_approval: bool = Field(True, description="Always true; field retained for explicit contract visibility")

class AdjustReorderPointOutput(BaseModel):
    adjustment_id: str                 # UUID
    idempotency_key: str
    sku: str
    previous_reorder_point: int
    requested_reorder_point: int
    status: ReorderAdjustmentStatus
    submitted_at: str                  # ISO 8601
    approved_at: Optional[str]         # ISO 8601; None if still pending
    approved_by: Optional[str]
    rejection_reason: Optional[str]
    audit_log_entry_id: Optional[str]
```

---

## 6. First Vertical Slice: Inventory MCP Server

The inventory server is the highest-value first target: it is the most-queried domain, has a clean data boundary (its own Postgres tables), and demonstrates the full migration pattern for other teams to follow.

### 6.1 Capabilities to Implement First

Priority order (by call frequency and risk):

1. `warehouse.inventory.check_stock` — read-only, demonstrates the full client path
2. `warehouse.inventory.reserve` — write with idempotency, demonstrates the approval-free write path
3. `warehouse.inventory.get_movements` — read, demonstrates resource streaming
4. `warehouse.inventory.adjust_reorder_point` — demonstrates the approval-required write path and `ApprovalRequiredError` handling
5. `warehouse.inventory.start_cycle_count` — demonstrates task creation with WMS delegation

### 6.2 Contract Definitions

The five contracts for this slice use the Pydantic models defined in Section 5 plus two additional:

```python
# maiw_mcp/contracts/inventory.py (additions)

class GetMovementsInput(BaseModel):
    sku: Optional[str] = None
    movement_type: Optional[str] = Field(None, pattern="^(inbound|outbound|adjustment)$")
    start_date: Optional[str] = None   # ISO 8601
    end_date: Optional[str] = None
    location: Optional[str] = None
    limit: int = Field(100, ge=1, le=1000)

class InventoryMovement(BaseModel):
    id: int
    sku: str
    movement_type: str
    quantity: int
    timestamp: str
    location: str
    notes: Optional[str]

class GetMovementsOutput(BaseModel):
    movements: list[InventoryMovement]
    total_count: int
    next_cursor: Optional[str]    # Opaque cursor for pagination

class StartCycleCountInput(BaseModel):
    sku: str
    location: str
    class_name: Optional[str] = None   # ABC classification
    priority: str = Field("normal", pattern="^(normal|high|urgent)$")
    idempotency_key: str

class StartCycleCountOutput(BaseModel):
    cycle_count_id: str
    sku: str
    location: str
    priority: str
    assigned_to: Optional[str]
    scheduled_at: str
    status: str
    wms_reference_id: Optional[str]   # WMS task ID if delegated
```

### 6.3 Server Scaffolding

```python
# maiw-mcp-inventory/src/server.py

import asyncpg
from mcp.server.fastmcp import FastMCP
from mcp.server.auth.provider import OAuthAuthorizationServerProvider
from maiw_mcp.contracts.inventory import (
    StockCheckInput, StockCheckOutput,
    ReserveInventoryInput, ReserveInventoryOutput,
    GetMovementsInput, GetMovementsOutput,
    AdjustReorderPointInput, AdjustReorderPointOutput,
    StartCycleCountInput, StartCycleCountOutput,
)
from maiw_mcp.core.errors import ApprovalRequiredError
from maiw_mcp.core.telemetry import start_tool_span, record_tool_result

mcp = FastMCP(
    "maiw-inventory",
    version="1.0.0",
    capabilities={"tools": {}, "resources": {"subscribe": True}},
)

pool: asyncpg.Pool = None

@mcp.tool()
async def check_stock(input: StockCheckInput) -> StockCheckOutput:
    """Check on-hand, reserved, and available stock for a SKU."""
    with start_tool_span("warehouse.inventory.check_stock", input) as span:
        # ... asyncpg query against inventory_items + inventory_locations
        result = await _query_stock(pool, input)
        record_tool_result(span, result, success=True)
        return result

@mcp.tool()
async def reserve_inventory(input: ReserveInventoryInput) -> ReserveInventoryOutput:
    """Reserve inventory for an order. Idempotent on idempotency_key."""
    # ... idempotency check, row-level lock, update reserved_quantity
    ...

@mcp.tool()
async def get_movements(input: GetMovementsInput) -> GetMovementsOutput:
    """Retrieve inventory movements with optional filters."""
    ...

@mcp.tool()
async def adjust_reorder_point(input: AdjustReorderPointInput) -> AdjustReorderPointOutput:
    """Adjust reorder point. Always creates a pending approval record."""
    # Check caller scope from MCP auth context
    ctx = mcp.get_context()
    scopes = ctx.request_context.auth_info.scopes if ctx.request_context.auth_info else []
    if "warehouse:approve" not in scopes:
        raise ApprovalRequiredError(
            capability="warehouse.inventory.adjust_reorder_point",
            message="Caller does not hold warehouse:approve scope"
        )
    ...

@mcp.tool()
async def start_cycle_count(input: StartCycleCountInput) -> StartCycleCountOutput:
    """Initiate a cycle count task, delegating to WMS if configured."""
    ...

@mcp.resource("warehouse://inventory/{sku}")
async def inventory_resource(sku: str) -> str:
    """Current stock record for a SKU as a JSON resource."""
    ...
```

### 6.4 Transport Choice

**Production:** Streamable HTTP (SSE transport from the official SDK). Each `tools/call` arrives as a POST; progress and streaming results use SSE. TLS terminated at the ingress proxy. The FastAPI app's MCP router makes requests to `http://maiw-mcp-inventory:8001/mcp` inside the cluster.

**Local development / CI:** stdio transport. The `maiw-mcp` test harness uses `mcp.client.stdio.stdio_client` to spawn the server subprocess and run conformance and contract tests in a single pytest process. No network required.

**Rationale for streamable HTTP over WebSocket:** HTTP scales more naturally with existing infrastructure (load balancers, health probes, service mesh). WebSocket is reserved for future real-time subscription use cases (e.g., inventory level change events).

### 6.5 How Current Agent Code Routes to It

The migration does not change agent behavior — it changes the tool execution path underneath:

**Before (current):**
```
MCPEquipmentAssetOperationsAgent._execute_tool_plan()
  → tool_discovery.execute_tool("check_stock", {...})
    → EquipmentMCPAdapter._handle_get_equipment_status({...})
      → equipment_asset_tools.get_equipment_status(...)
        → SQLRetriever.fetch_all(SQL, ...)
```

**After (MCP v2):**
```
MCPEquipmentAssetOperationsAgent._execute_tool_plan()
  → capability_client.call_capability("warehouse.inventory.check_stock", StockCheckInput(...))
    → CapabilityRouter.route("warehouse.inventory.check_stock")
      → ConnectionPool.acquire(server_url="http://maiw-mcp-inventory:8001/mcp")
        → mcp.ClientSession.call_tool("check_stock", {...})
          [network] → maiw-mcp-inventory server
            → asyncpg pool → PostgreSQL
          [network] ← StockCheckOutput JSON
        ← StockCheckOutput (deserialized)
```

The agent class `MCPEquipmentAssetOperationsAgent` is updated to import `WarehouseCapabilityClient` from `maiw_mcp.client.capability_client` and call `call_capability()` instead of `tool_discovery.execute_tool()`. The graph structure and synthesize node are not changed.

### 6.6 Contract Tests to Write

```python
# maiw_mcp/testing/contract_tests.py (inventory section)

class TestInventoryContracts(ContractTestSuite):
    
    def test_check_stock_valid_sku(self, capability_client, seed_sku="CHE001"):
        result = capability_client.call_capability(
            "warehouse.inventory.check_stock",
            StockCheckInput(sku=seed_sku)
        )
        assert isinstance(result, StockCheckOutput)
        assert result.sku == seed_sku
        assert result.total_on_hand >= 0
        assert result.total_available == result.total_on_hand - result.total_reserved
        assert result.freshness_timestamp is not None

    def test_check_stock_unknown_sku_returns_zero_not_error(self, capability_client):
        result = capability_client.call_capability(
            "warehouse.inventory.check_stock",
            StockCheckInput(sku="NONEXISTENT_99999")
        )
        assert result.total_on_hand == 0

    def test_reserve_inventory_idempotency(self, capability_client):
        key = str(uuid.uuid4())
        r1 = capability_client.call_capability("warehouse.inventory.reserve",
            ReserveInventoryInput(sku="CHE001", quantity=5, order_id="ORD-001", idempotency_key=key))
        r2 = capability_client.call_capability("warehouse.inventory.reserve",
            ReserveInventoryInput(sku="CHE001", quantity=5, order_id="ORD-001", idempotency_key=key))
        assert r1.reservation_id == r2.reservation_id
        assert r2.status == ReservationStatus.ALREADY_EXISTS

    def test_reserve_inventory_insufficient_stock_partial_allowed(self, capability_client):
        result = capability_client.call_capability("warehouse.inventory.reserve",
            ReserveInventoryInput(sku="RARE-SKU", quantity=99999, order_id="ORD-002",
                                  idempotency_key=str(uuid.uuid4()), allow_partial=True))
        assert result.status == ReservationStatus.PARTIAL
        assert result.reserved_quantity < 99999

    def test_adjust_reorder_point_requires_approval_scope(self, capability_client_no_approve_scope):
        with pytest.raises(ApprovalRequiredError):
            capability_client_no_approve_scope.call_capability(
                "warehouse.inventory.adjust_reorder_point",
                AdjustReorderPointInput(sku="CHE001", new_reorder_point=50,
                    rationale="Seasonal demand increase", user_id="u1",
                    idempotency_key=str(uuid.uuid4())))

    def test_adjust_reorder_point_with_approval_scope_creates_pending(self, capability_client_approver):
        result = capability_client_approver.call_capability(
            "warehouse.inventory.adjust_reorder_point",
            AdjustReorderPointInput(sku="CHE001", new_reorder_point=50,
                rationale="Seasonal demand increase", user_id="u1",
                idempotency_key=str(uuid.uuid4())))
        assert result.status == ReorderAdjustmentStatus.PENDING_APPROVAL
        assert result.adjustment_id is not None
```

### 6.7 Conformance Tests to Write

```python
# maiw_mcp/testing/conformance.py (inventory section)

class InventoryServerConformance(MCPConformanceChecker):

    def test_initialize_handshake(self, server_url):
        """Server must respond to initialize with protocolVersion 2024-11-05."""
        session = self.connect(server_url)
        assert session.server_info.protocol_version == "2024-11-05"
        assert "tools" in session.server_capabilities

    def test_tools_list_returns_valid_schemas(self, server_url):
        """tools/list must return all five capabilities with valid inputSchema."""
        tools = self.get_tools_list(server_url)
        names = {t.name for t in tools}
        assert names == {
            "check_stock", "reserve_inventory", "get_movements",
            "adjust_reorder_point", "start_cycle_count"
        }
        for tool in tools:
            assert tool.input_schema["type"] == "object"
            assert "properties" in tool.input_schema

    def test_tools_call_invalid_params_returns_invalid_params_error(self, server_url):
        """tools/call with missing required param must return JSON-RPC -32602."""
        response = self.call_tool_raw(server_url, "check_stock", {})  # missing sku
        assert response["error"]["code"] == -32602

    def test_tools_call_internal_error_returns_internal_error_code(self, server_url, kill_db):
        """When DB is unavailable, tools/call must return JSON-RPC -32603."""
        response = self.call_tool_raw(server_url, "check_stock", {"sku": "CHE001"})
        assert response["error"]["code"] == -32603

    def test_ping_responds(self, server_url):
        """ping must return an empty result."""
        response = self.send_request(server_url, "ping", {})
        assert response.get("result") == {} or response.get("result") is None

    def test_resource_uri_resolves(self, server_url):
        """warehouse://inventory/{sku} resource must be readable."""
        content = self.read_resource(server_url, "warehouse://inventory/CHE001")
        data = json.loads(content)
        assert data["sku"] == "CHE001"
```

---

## 7. Migration Sequence

### Phase 0 — Foundation (2 weeks)

**Goal:** Zero agent behavior change. Establish the dependency, package structure, and test harness.

1. Add `mcp>=1.27.0` to `requirements.txt` and `pyproject.toml`.
2. Create the `maiw-mcp` package at the repository root with directory structure from Section 3.
3. Implement `maiw_mcp/contracts/` — all Pydantic models for the five domains in Section 5 plus the remaining contracts (wave, labor, optimization).
4. Implement `maiw_mcp/testing/` — `InMemoryMCPServer`, `MCPConformanceChecker`, `ContractTestSuite` base class, fixtures.
5. Write the conformance suite against the `InMemoryMCPServer` to validate the test harness itself.
6. Pin the existing `ToolDiscoveryService` path with a `@deprecated` annotation. No functional change.

**Exit criteria:** `pytest maiw-mcp/tests/` passes. `requirements.txt` installs cleanly. Existing API integration tests still pass.

---

### Phase 1 — Inventory MCP Server (3 weeks)

**Goal:** Deploy the first real MCP v2 server. The inventory agent path uses it; all other paths remain unchanged.

1. Scaffold `maiw-mcp-inventory/` as a standalone FastAPI + FastMCP service.
2. Implement the five capabilities from Section 6.1 against the existing asyncpg pool.
3. Implement stdio transport for testing; streamable HTTP for deployment.
4. Write contract tests (Section 6.6) and conformance tests (Section 6.7). All must pass.
5. Update `MCPEquipmentAssetOperationsAgent._execute_tool_plan()` to call `WarehouseCapabilityClient.call_capability()` for inventory-domain capability names. Equipment-domain names still use the adapter path.
6. Update `CapabilityRegistry` with the inventory server URL.
7. Implement `OAuthTokenProvider` skeleton (client credentials grant, in-memory token cache). Full scope enforcement deferred to Phase 3.
8. Deploy behind the cluster ingress alongside the existing FastAPI app.
9. Add `/health` and `/ready` endpoints to the inventory server; wire into `HealthAggregator`.

**Exit criteria:** `warehouse.inventory.check_stock` and `warehouse.inventory.reserve` are called via MCP protocol in production chat queries. Contract tests pass in CI. Conformance tests pass against the deployed server URL.

---

### Phase 2 — Equipment, Operations, Safety MCP Servers (4 weeks)

**Goal:** Three more domains migrated. `ToolDiscoveryService` adapter path used only for forecasting and document.

1. Scaffold `maiw-mcp-equipment/`, `maiw-mcp-labor/`, `maiw-mcp-safety/` using the same pattern as inventory.
2. Implement capabilities per Section 4 for each server. For safety, implement the emergency bypass path for severity >= HIGH in `broadcast_alert` (skip approval queue, direct IoT dispatch).
3. Update `MCPEquipmentAssetOperationsAgent`, `MCPOperationsAgent`, `MCPSafetyAgent` to use `WarehouseCapabilityClient`.
4. Retire `EquipmentMCPAdapter`, `OperationsMCPAdapter`, `SafetyMCPAdapter` from `src/api/services/mcp/adapters/`. Keep files but mark handlers as `raise NotImplementedError("Migrated to MCP server")`.
5. Update `_register_mcp_adapters()` to skip the three retired adapters.
6. Write contract and conformance tests for each server. All must pass.
7. Implement `ConnectionPool.acquire()` with health-aware routing — if a server's `/health` returns 503, route to a replica or return `CapabilityNotFoundError` immediately rather than waiting for timeout.

**Exit criteria:** Equipment, labor, and safety domains route through MCP protocol. The `ToolDiscoveryService` discovery loop no longer runs for those three domains. Per-domain error isolation confirmed: killing the safety server does not affect equipment queries.

---

### Phase 3 — Auth, Telemetry, Trajectory Store (3 weeks)

**Goal:** Close the security gap. Enforce RBAC at the MCP tool boundary. Start capturing execution trajectories.

1. Deploy an OAuth 2.1 authorization server (or configure an existing IdP). Register the warehouse scope hierarchy: `warehouse:read`, `warehouse:write:inventory`, `warehouse:write:labor`, `warehouse:write:equipment`, `warehouse:write:safety`, `warehouse:approve`.
2. Map existing `UserRole` enum to OAuth scopes:
   - `viewer` → `warehouse:read`
   - `operator` → `warehouse:read`, `warehouse:write:labor`, `warehouse:write:equipment`
   - `supervisor` → all write scopes except `warehouse:approve`
   - `manager` / `admin` → all scopes including `warehouse:approve`
3. Implement `OAuthTokenProvider.get_token(user_context)` — exchanges user JWT for a scoped service token per request.
4. Enable scope enforcement in each server for write capabilities. `adjust_reorder_point` and `approve_document` require `warehouse:approve`.
5. Implement `core/telemetry.py` fully — OTel spans exported to the configured collector. Add `warehouse.risk_level` and `warehouse.domain` span attributes.
6. Implement the trajectory store: a structured log (Postgres table `tool_trajectories`) recording `(session_id, capability_name, input_hash, output_hash, latency_ms, success, span_id)` for every `call_capability()` invocation. This is the seed data for the intelligence flywheel.
7. Retire `security.py` blocklist as the primary defense. Retain it as a defense-in-depth pre-check but the primary gate is now OAuth scope enforcement.

**Exit criteria:** A user with `viewer` role cannot call `warehouse.inventory.reserve`. All `tools/call` invocations produce OTel spans visible in the collector. Trajectory table is populated after a load test.

---

### Phase 4 — Forecasting and Document MCP Servers (3 weeks)

**Goal:** Complete the migration. Retire the entire `src/api/services/mcp/` custom layer.

1. Scaffold `maiw-mcp-forecasting/` and `maiw-mcp-documents/`.
2. Implement forecasting capabilities with streaming for `get_batch_forecast` (chunked SSE results for >10 SKUs).
3. Implement document capabilities. `upload` returns a `document_id` immediately; `get_status` polls stage progress using MCP resource subscriptions.
4. Update `ForecastingAgent` and `MCPDocumentAgent` to use `WarehouseCapabilityClient`.
5. Retire `ForecastingMCPAdapter` and document direct endpoints from the MCP router.
6. Delete `src/api/services/mcp/server.py`, `src/api/services/mcp/client.py`, `src/api/services/mcp/base.py`, `src/api/services/mcp/tool_discovery.py`, `src/api/services/mcp/tool_binding.py`, `src/api/services/mcp/tool_routing.py`, and all files in `src/api/services/mcp/adapters/`.
7. Delete `src/api/routers/mcp.py` and replace with a thin status endpoint reading from `HealthAggregator`.
8. Update `ToolNode` and `@tool` imports in `mcp_integrated_planner_graph.py` — either use them properly or remove the dead imports.

**Exit criteria:** `src/api/services/mcp/` directory is empty or removed. All seven domain paths route through `WarehouseCapabilityClient`. The `ToolDiscoveryService` class no longer exists in the codebase.

---

### Phase 5 — Optimization Server and Intelligence Flywheel (ongoing)

**Goal:** Deliver the remaining target architecture components.

1. Scaffold `maiw-mcp-optimization/` calling back into inventory and labor servers for state reads, running optimization, returning plans.
2. Implement `DecisionEngine` — deterministic policy/risk/approval gate sitting between `call_capability()` and the capability client's network dispatch. Reads risk level from the contract, applies approval rules, and either proceeds or creates an `ApprovalRequest`.
3. Wire the trajectory store into an offline SFT pipeline for domain-specialized Nemotron fine-tuning.
4. Scaffold `maiw-mcp-simulation/` as the digital twin integration point.

---

## 8. Definition of Done

A capability is **MCP v2 compliant** when all of the following hold:

**Protocol compliance**
- The server responds to `initialize` with `protocolVersion: "2024-11-05"` and advertises its capabilities correctly.
- `tools/list` returns valid JSON Schema `inputSchema` for every tool, generated from the Pydantic contract model.
- `tools/call` with valid input returns a result matching the output contract model.
- `tools/call` with invalid input returns a JSON-RPC error with code `-32602` (Invalid Params).
- `tools/call` when the backend is unavailable returns `-32603` (Internal Error) — never a 200 with `{"success": false}`.
- `ping` responds.
- The MCPConformanceChecker suite passes at 100% against the deployed server URL.

**Contract compliance**
- Every capability has an `Input` and `Output` Pydantic model in `maiw_mcp/contracts/`.
- The canonical name follows the `warehouse.{domain}.{action}` pattern.
- Idempotency behavior is tested and confirmed for all write capabilities.
- Approval-required capabilities raise `ApprovalRequiredError` (not silently create records) when the caller lacks the required scope.
- All contract tests pass.

**Security compliance**
- Write capabilities require a valid OAuth 2.1 bearer token with the appropriate `warehouse:write:{domain}` scope.
- Approval-required capabilities additionally require `warehouse:approve` scope.
- No tool accepts parameters named `code`, `script`, `command`, or `exec_code` (pattern blocklist retained as defense-in-depth).
- `adjust_reorder_point` and equivalent approval-gated capabilities are tested with a `viewer`-scoped token and return `ApprovalRequiredError`, not a data result.

**Operational compliance**
- Server exposes `/health` (liveness) and `/ready` (readiness, including DB pool check).
- Failing the DB check sets `/ready` to 503 without affecting `/health`.
- Every `tools/call` emits an OTel span with `mcp.server`, `mcp.tool`, `warehouse.domain`, and `warehouse.risk_level` attributes.
- A trajectory record is written to `tool_trajectories` for every successful and failed invocation.
- The server can be restarted without affecting other domain servers (no shared mutable state between servers).

**Migration compliance**
- The retired adapter (`src/api/services/mcp/adapters/{domain}_adapter.py`) has all handler methods replaced with `raise NotImplementedError("Migrated to MCP server — use WarehouseCapabilityClient")`.
- No agent class imports from `src/api/services/mcp/` after the domain is migrated.
- Existing integration tests for the migrated domain continue to pass without modification (behavior parity).

**The entire migration is complete** when all nine domain servers (inventory, wms, labor, equipment, safety, forecasting, documents, optimization, simulation) are MCP v2 compliant by the criteria above, and `src/api/services/mcp/` contains only empty `__init__.py` files or is removed from the repository.
