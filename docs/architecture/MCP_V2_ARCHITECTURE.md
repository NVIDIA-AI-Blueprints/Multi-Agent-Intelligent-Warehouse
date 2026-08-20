# MCP v2 Architecture — MAIW Capability Bus (Inventory + Equipment)
## Multi-Agent Intelligent Warehouse (MAIW)

**Phase:** 6B (Architecture hardening — MCP boundary enforcement)  
**Date:** 2026-08-20  
**SDK:** `mcp` 2.0.0 (official Anthropic MCP Python SDK)  
**Protocol version:** 2026-07-28  
**Status:** Implemented — 311 tests passing across Phase 3-6B test files (contract + MCP protocol + unit + architecture invariants)

---

## 1. Overview

Phase 2 proves one complete end-to-end path from an agent method call through the
official MCP protocol to the existing MAIW backend — without modifying the backend,
without breaking existing agents, and without touching the Phase 1 ModelGateway.

```
OperationsCoordinationAgent._lookup_inventory_sku("SKU-001")
  ↓
InventoryLookupSkill.execute(InventoryLookupRequest(sku="SKU-001"))
  ↓  [semantic capability name only]
MAIWMCPClient.invoke("warehouse.inventory.get", payload)
  ↓  [official MCP Python SDK]
streamablehttp_client(server_url) → ClientSession → session.call_tool(...)
  ↓  [MCP JSON-RPC 2.0 over Streamable HTTP — or in-memory for tests]
FastMCP server: mcp_servers/inventory/server.py
  ↓  [warehouse_inventory_get tool]
MAIWInventoryAdapter.get_inventory()
  ↓  [wraps existing code — zero new inventory logic]
InventoryQueries.get_item_by_sku() → SQLRetriever → PostgreSQL
```

---

## 2. Package Layout

```
packages/
└── maiw-mcp/                       ← editable install: pip install -e packages/maiw-mcp/
    └── maiw_mcp/
        ├── __init__.py
        ├── errors.py               ← typed error hierarchy
        ├── auth/
        │   └── auth.py             ← MCPAuthConfig (bearer token)
        ├── client/
        │   └── client.py           ← MAIWMCPClient (official SDK)
        ├── contracts/
        │   ├── actions.py          ← ActionProposal, RiskLevel (write boundary)
        │   ├── common.py           ← CapabilityMetadata
        │   ├── equipment.py        ← EquipmentStatusRequest/Result, TelemetryRequest/Result + metadata
        │   └── inventory.py        ← InventoryLookupRequest/Result/Location + metadata
        ├── registry/
        │   └── registry.py         ← CapabilityRegistry
        ├── telemetry/
        │   └── telemetry.py        ← CapabilityTelemetry (structured JSON log)
        └── testing/
            ├── conformance.py      ← run_inventory_conformance()
            ├── fixtures.py         ← make_inventory_result()
            └── mock_server.py      ← MockInventoryServer (in-memory transport)

mcp_servers/
├── inventory/                      ← deployable MCP server package
│   ├── __init__.py
│   ├── server.py                   ← MCPServer entry point (2 tools)
│   ├── provider.py                 ← InventoryProvider Protocol + MockInventoryProvider
│   └── adapters/
│       └── maiw_backend.py         ← MAIWInventoryAdapter
└── equipment/                      ← Phase 3: second MCP domain
    ├── __init__.py
    ├── server.py                   ← MCPServer entry point (3 tools)
    ├── provider.py                 ← EquipmentProvider Protocol + MockEquipmentProvider
    └── adapters/
        └── maiw_backend.py         ← MAIWEquipmentAdapter → EquipmentAssetTools

src/api/
└── skills/
    ├── inventory.py                ← InventoryLookupSkill + get_inventory_skill()
    └── equipment.py                ← EquipmentStatusSkill, EquipmentTelemetrySkill,
                                       EquipmentAssignmentSkill + factories

tests/
├── contract/
│   ├── test_inventory_capability.py   ← 78 contract tests (inventory)
│   └── test_equipment_capability.py   ← 44 contract tests (equipment + ActionProposal)
└── mcp/
    ├── test_inventory_mcp_server.py   ← 31 MCP protocol tests (inventory)
    └── test_equipment_mcp_server.py   ← 28 MCP protocol tests (equipment)
```

### Phase 3 Capability Bus

```
OperationsCoordinationAgent
  ├── _lookup_inventory_sku()       via InventoryLookupSkill
  ├── _get_equipment_status()       via EquipmentStatusSkill
  └── _get_equipment_telemetry()    via EquipmentTelemetrySkill

Skill layer (src/api/skills/)
  ↓ MAIWMCPClient.invoke(capability_name, payload)
  ↓ [MCP v2 Streamable HTTP or in-memory]
MCP Server layer (mcp_servers/)
  ├── InventoryMCPServer  (warehouse.inventory.get, warehouse.inventory.locate)
  └── EquipmentMCPServer  (warehouse.equipment.get_status,
                           warehouse.equipment.get_telemetry,
                           warehouse.equipment.assign → ActionProposal)
  ↓ Provider / Adapter layer
  ├── MAIWInventoryAdapter → InventoryQueries → PostgreSQL
  └── MAIWEquipmentAdapter → EquipmentAssetTools → PostgreSQL

Write seam (Phase 3 only — future DecisionEngine not yet implemented):
  warehouse.equipment.assign  →  ActionProposal (not executed)
  [future DecisionEngine]     →  EquipmentAssetTools.assign_equipment()
```

### ActionProposal — Write Boundary

Write capabilities do NOT execute directly. They return an `ActionProposal`:

```python
ActionProposal(
    proposal_id="uuid",
    action="warehouse.equipment.assign",
    parameters={"asset_id": "FL-001", "assignee": "op-1", ...},
    domain="equipment",
    risk_level=RiskLevel.MEDIUM,
    requires_approval=True,
    reason="Unload dock 3",
    requested_by="operations-agent",
)
```

This seam is the insertion point for the future DecisionEngine. Until then,
callers receive the proposal and may inspect or log it.

---

## 2B. MCP SDK v1 → v2 Migration Summary

| Aspect | v1 (mcp 1.27.0) | v2 (mcp 2.0.0) |
|--------|-----------------|-----------------|
| Protocol version | 2024-11-05 | 2026-07-28 |
| High-level server | `FastMCP` (`mcp.server.fastmcp`) | `MCPServer` (`mcp.server`) |
| High-level client | `ClientSession` + `streamablehttp_client` | `Client` (`mcp.client`) |
| In-memory test | `create_connected_server_and_client_session(server)` | `Client(server)` |
| HTTP client | `streamablehttp_client(url)` + `ClientSession` | `Client("http://url")` |
| Error flag | `result.isError` | `result.is_error` |
| Tool schema key | `tool.inputSchema` | `tool.input_schema` |
| Structured content | `result.structuredContent` | `result.structured_content` |
| Stateless HTTP | Not default | `stateless_http=True` on `run()` |
| Session init | Manual `session.initialize()` | Handled internally by `Client` |

**Breaking changes in MAIW code:**
1. `mcp.server.fastmcp` module removed entirely — no `FastMCP` anywhere
2. `mcp.shared.memory.create_connected_server_and_client_session` removed
3. `mcp.client.streamable_http.streamablehttp_client` renamed to `streamable_http_client` (superseded by `Client`)
4. All `isError` / `inputSchema` / `structuredContent` field names snake_cased

**Stateless HTTP for horizontal scaling:**

```python
# Production entry point — stateless_http=True means no Mcp-Session-Id required.
# Any request can be served by any pod behind a load balancer.
mcp_server.run("streamable-http", host=host, port=port, stateless_http=True)
```

---

## 3. Capability Naming Convention

All MAIW capabilities follow the `warehouse.<domain>.<action>` namespace:

| Capability Name               | Domain    | Action   | Side Effect | Risk |
|-------------------------------|-----------|----------|-------------|------|
| `warehouse.inventory.get`     | inventory | get      | read        | low  |
| `warehouse.inventory.locate`  | inventory | locate   | read        | low  |

Rules:
- All lowercase, dot-separated, no hyphens in the capability name itself.
- `warehouse` is the fixed top-level namespace for all MAIW MCP capabilities.
- `<domain>` maps to a single MAIW MCP server (one server per domain boundary).
- `<action>` is a verb: `get`, `locate`, `reserve`, `release`, `transfer`, etc.
- Side effects must be declared: `"read"` | `"write"` | `"reserve"`.
- Risk must be declared: `"low"` | `"medium"` | `"high"`.

---

## 4. Contract Structure

### 4.1 CapabilityMetadata (`maiw_mcp/contracts/common.py`)

Declarative per-capability metadata attached to every capability definition.

```python
class CapabilityMetadata(BaseModel):
    name: str                   # warehouse.<domain>.<action>
    version: int = 1            # integer — increment on breaking change
    domain: str                 # "inventory", "fulfillment", …
    side_effect: str = "read"   # "read" | "write" | "reserve"
    risk: str = "low"           # "low" | "medium" | "high"
    idempotent: bool = True
    timeout_seconds: int = 30
    required_permission: str | None = None
    description: str = ""
```

### 4.2 Inventory Contracts (`maiw_mcp/contracts/inventory.py`)

```
InventoryLookupRequest
  warehouse_id: str = "default"
  sku: str (min_length=1)
  location: str | None

InventoryLocation
  location_id: str
  quantity_available: int (≥0)
  quantity_reserved: int = 0 (≥0)
  reorder_point: int (≥0)
  → quantity_on_hand: int  [property = available + reserved]

InventoryLookupResult
  warehouse_id: str
  sku: str
  name: str
  locations: list[InventoryLocation]
  total_available: int (≥0)
  is_low_stock: bool
  observed_at: datetime
  source: str  ["maiw-backend" | "sap-ewm" | "manhattan" | "mock" | …]
```

**Vendor neutrality guarantee:** No field references any WMS vendor. The `source`
field identifies the backend for provenance — it does not change the contract shape.

---

## 5. MCP Server Architecture (`mcp_servers/inventory/server.py`)

### 5.1 Server Construction

```python
mcp_server = FastMCP("MAIW Inventory Server")

@mcp_server.tool(name="warehouse.inventory.get", description=INVENTORY_GET_METADATA.description)
async def warehouse_inventory_get(sku: str, warehouse_id: str = "default", location: str | None = None) -> str:
    result = await _get_provider().get_inventory(InventoryLookupRequest(sku=sku, ...))
    return json.dumps(result.model_dump(mode="json"), default=str)
```

### 5.2 Transport Selection

The server selects transport from the `MAIW_MCP_TRANSPORT` environment variable:

| `MAIW_MCP_TRANSPORT` | Transport          | Use case                       |
|----------------------|--------------------|--------------------------------|
| `stdio` (default)    | Standard I/O       | Local / subprocess             |
| `sse`                | Server-Sent Events | Legacy MCP clients             |
| `streamable-http`    | Streamable HTTP    | Production deployment (default)|

Production runs with `MAIW_MCP_TRANSPORT=streamable-http`.

### 5.3 Provider Injection

The module-level `_provider` is set via `configure_server(provider)`. This is
the primary injection point for both testing and production:

```python
# Production (wired in app startup or Kubernetes init container)
from mcp_servers.inventory.adapters.maiw_backend import MAIWInventoryAdapter
configure_server(MAIWInventoryAdapter(inventory_queries))

# Tests (no database)
configure_server(MockInventoryProvider())
```

---

## 6. Connector Boundary: InventoryProvider Protocol

```python
@runtime_checkable
class InventoryProvider(Protocol):
    async def get_inventory(self, request: InventoryLookupRequest) -> InventoryLookupResult: ...
```

Any object implementing `get_inventory` satisfies the Protocol — no base class
required. New WMS vendors add an adapter class; no MCP server changes needed.

| Adapter                  | Backend                     | Status           |
|--------------------------|-----------------------------|------------------|
| `MockInventoryProvider`  | In-memory fixture           | Implemented      |
| `MAIWInventoryAdapter`   | Existing MAIW PostgreSQL    | Implemented      |
| `SAPEWMAdapter`          | SAP Extended Warehouse Mgmt | Future Phase 3   |
| `ManhattanAdapter`       | Manhattan Associates WMS    | Future Phase 3   |

---

## 7. Client Architecture (`maiw_mcp/client/client.py`)

```python
class MAIWMCPClient:
    def __init__(self, registry: CapabilityRegistry, *, telemetry: CapabilityTelemetry | None = None)

    async def invoke(
        self,
        capability: str,            # "warehouse.inventory.get"
        payload: dict,              # request.model_dump(exclude_none=True)
        *,
        trace_id: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> dict
```

**Runtime path (MCP v2):**
1. `CapabilityRegistry.resolve(capability)` → server URL (raises `CapabilityNotFound` if not registered)
2. `async with Client(server_url, read_timeout_seconds=timeout_seconds) as client:` — `Client` handles the full MCP 2026-07-28 lifecycle (connect, initialize handshake, session teardown)
3. `await client.call_tool(capability, payload)` → MCP `tools/call` request
4. Check `result.is_error` → raise `MCPToolError` if true
5. Parse `TextContent[0].text` as JSON → return dict
6. `CapabilityTelemetry.record_success/failure()` → structured JSON log (includes `mcp_sdk_version` and `mcp_protocol_version`)

**v1 → v2 client changes:**
- `streamablehttp_client + ClientSession + session.initialize()` replaced by `Client(url)`
- `result.isError` → `result.is_error`
- `result.structuredContent` → `result.structured_content`
- No persistent session state; every `invoke()` is independently routable

**Error hierarchy** (`maiw_mcp/errors.py`):

```
MAIWMCPError
├── MCPUnavailable       — transport or protocol error
├── MCPTimeout           — client-side timeout exceeded
├── MCPToolError         — server returned isError=True
├── MCPContractError     — result not valid JSON or wrong shape
├── CapabilityNotFound   — no server URL registered for this capability
├── CapabilityPermissionDenied — auth check failed
└── BackendUnavailable   — adapter could not reach the WMS backend
```

---

## 8. Capability Registry (`maiw_mcp/registry/registry.py`)

Maps semantic capability names to MCP server URLs. In production, populated from
environment variables at startup.

```python
registry = CapabilityRegistry.from_env()
# Reads MAIW_MCP_SERVER_INVENTORY_URL=http://inventory-mcp:8080
# Registers: warehouse.inventory.get → http://inventory-mcp:8080
#            warehouse.inventory.locate → http://inventory-mcp:8080
```

Environment variable convention: `MAIW_MCP_SERVER_<DOMAIN>_URL`

| Domain     | Env Var                              | Capabilities Registered          |
|------------|--------------------------------------|----------------------------------|
| inventory  | `MAIW_MCP_SERVER_INVENTORY_URL`      | `warehouse.inventory.get`        |
|            |                                      | `warehouse.inventory.locate`     |
| fulfillment| `MAIW_MCP_SERVER_FULFILLMENT_URL`    | (future)                         |
| receiving  | `MAIW_MCP_SERVER_RECEIVING_URL`      | (future)                         |

---

## 9. Telemetry (`maiw_mcp/telemetry/telemetry.py`)

Every `invoke()` call emits one structured JSON record to the application logger:

```json
{
  "event": "mcp_capability_call",
  "trace_id": "trace-abc123",
  "capability_name": "warehouse.inventory.get",
  "capability_version": 1,
  "mcp_server": "http://inventory-mcp:8080",
  "transport": "streamable-http",
  "latency_ms": 12.4,
  "success": true,
  "backend": null,
  "error_class": null,
  "error_message": null
}
```

`trace_id` propagates from the ModelGateway request span, enabling correlation of
agent reasoning calls (`/api/v1/chat`) through the MCP capability invocations.

---

## 10. Security Model (Phase 2)

Phase 2 implements bearer-token auth only. OAuth 2.0 is deferred to Phase 4.

| Control               | Implementation                                                |
|-----------------------|---------------------------------------------------------------|
| Transport encryption  | TLS required for all non-localhost Streamable HTTP URLs       |
| Authentication        | `Authorization: Bearer <token>` from `MAIW_MCP_API_KEY`      |
| Authorization         | `required_permission` field on `CapabilityMetadata`          |
| Server-side enforcement | Phase 3 (FastMCP middleware layer)                          |
| OAuth 2.0             | Phase 4                                                       |

---

## 11. Skill Integration (`src/api/skills/inventory.py`)

```python
class InventoryLookupSkill:
    """Bridge between agent semantic needs and MCP capability invocation."""

    def __init__(self, client: MAIWMCPClient): ...

    async def execute(
        self,
        request: InventoryLookupRequest,
        *,
        trace_id: str | None = None,
    ) -> InventoryLookupResult:
        payload = request.model_dump(exclude_none=True)
        raw = await self._client.invoke(
            INVENTORY_GET_METADATA.name, payload, trace_id=trace_id
        )
        try:
            return InventoryLookupResult.model_validate(raw)
        except ValidationError as exc:
            raise MCPContractError(str(exc)) from exc
```

**Factory** for singleton use in agents:

```python
async def get_inventory_skill() -> InventoryLookupSkill:
    registry = CapabilityRegistry.from_env()
    client = MAIWMCPClient(registry, telemetry=CapabilityTelemetry())
    return InventoryLookupSkill(client)
```

---

## 12. Agent Integration (`src/api/agents/operations/operations_agent.py`)

### 12.1 Graceful Degradation

The skill is wired only when `MAIW_MCP_SERVER_INVENTORY_URL` is set:

```python
async def initialize(self) -> None:
    ...
    if os.getenv("MAIW_MCP_SERVER_INVENTORY_URL"):
        self.inventory_skill = await get_inventory_skill()
    # if not set: self.inventory_skill stays None — no crash, no warning needed
```

### 12.2 Lookup Method

```python
async def _lookup_inventory_sku(
    self,
    sku: str,
    warehouse_id: str = "default",
    trace_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if self.inventory_skill is None:
        return None  # MCP not configured — silent degradation
    try:
        result = await self.inventory_skill.execute(
            InventoryLookupRequest(sku=sku, warehouse_id=warehouse_id),
            trace_id=trace_id,
        )
        return {
            "sku": result.sku,
            "name": result.name,
            "total_available": result.total_available,
            "is_low_stock": result.is_low_stock,
            "locations": [loc.model_dump() for loc in result.locations],
        }
    except MAIWMCPError as exc:
        logger.warning("MCP inventory lookup failed for %s: %s", sku, exc)
        return None  # degrade gracefully
```

---

## 13. Deployment Model

### Development / CI

```
[pytest] → MockInventoryProvider → mcp_server (in-memory transport)
                                        ↑
                              create_connected_server_and_client_session()
```

No network, no database, no environment variables required.

### Staging / Production

```
[OperationsCoordinationAgent]
    ↓ MAIW_MCP_SERVER_INVENTORY_URL=http://inventory-mcp:8080
[MAIWMCPClient] → Client("http://inventory-mcp:8080") → [Load Balancer]
                                                              ↓
                                                    ┌─────────────────┐
                                                    │ inventory-mcp-1 │ MCPServer (stateless_http=True)
                                                    ├─────────────────┤
                                                    │ inventory-mcp-2 │
                                                    ├─────────────────┤
                                                    │ inventory-mcp-N │
                                                    └─────────────────┘
                                                              ↓
                                                     MAIWInventoryAdapter
                                                              ↓
                                                     InventoryQueries (existing)
                                                              ↓
                                                          PostgreSQL
```

Kubernetes: inventory MCP server runs as a Deployment with N replicas.
`stateless_http=True` means no `Mcp-Session-Id` is required — any replica can
serve any request.  No sticky sessions, no session affinity rules needed on the
Service or Ingress.  Agents discover the Service via `MAIW_MCP_SERVER_INVENTORY_URL`.

---

## 14. Testing Strategy

### 14.1 Contract Tests (`tests/contract/test_inventory_capability.py` — 37 tests)

Validate the Pydantic v2 contracts independent of any MCP protocol:
- `CapabilityMetadata` name pattern, version, risk, side-effect
- `InventoryLookupRequest` field validation (required sku, empty rejection)
- `InventoryLookupResult` low-stock logic, JSON round-trip
- `InventoryLookupSkill` correct capability name, trace_id propagation
- `MockInventoryProvider` Protocol conformance
- `MAIWInventoryAdapter` quantity mapping, error surfacing

### 14.2 MCP Protocol Tests (`tests/mcp/test_inventory_mcp_server.py` — 31 tests)

Exercise the real MCP 2026-07-28 protocol using `Client(server)` in-memory transport:
- `TestMCPV2Protocol` (6): SDK v2 import path, protocol version, FastMCP removed, telemetry fields
- `TestMCPServerInitialization` (3): server creates, name, Client connects
- `TestMCPToolDiscovery` (4): tool names, `input_schema` (snake_case v2), description
- `TestMCPInventoryGetTool` (7): valid request, JSON result, required fields, source, locate tool
- `TestMCPErrorHandling` (2): `BackendUnavailable` → `is_error=True`, empty SKU handled
- `TestMCPStatelessBehavior` (3): two independent clients, per-request Client pattern, state isolation
- `TestMCPConformanceSuite` (1): full 8-check conformance suite passes
- `TestMockInventoryServer` (5): respond, configured data, both tools, telemetry, session alias

### 14.3 ModelGateway Regression (`tests/unit/test_model_gateway.py` — 117 tests)

Unchanged. Phase 2B did not touch the ModelGateway.

**Total: 185 tests | 185 passed | 0 failed | 0 skipped**

---

## 15. What Was NOT Changed (Phase 2 Scope Boundary)

| Component                         | Status in Phase 2 |
|-----------------------------------|-------------------|
| ModelGateway                      | Untouched         |
| Existing MCP custom implementation| Untouched (operational) |
| NIM client / LLM routing          | Untouched         |
| InventoryQueries SQL layer        | Untouched (wrapped) |
| FastAPI routers                   | Untouched         |
| React frontend                    | Untouched         |
| Existing agent tool calls         | Untouched         |
| Existing test suite (117 tests)   | All passing       |

The only modifications to existing source files:
- `src/api/agents/operations/operations_agent.py` — added `inventory_skill` wiring +
  `_lookup_inventory_sku()`. No existing methods changed.

---

## Phase 4 — Central Runtime Architecture

### Runtime Flow

```
Agent request
    │
    ▼
StateRequirements  (agent declares what it needs)
    │
    ▼
WarehouseStateProvider.get_state()
    │  calls only the domains declared in requirements
    │  ┌───────────────────────────────┐
    ├──► EquipmentStatusSkill.execute() │  → EquipmentState
    │  └───────────────────────────────┘
    │  ┌───────────────────────────────┐
    └──► InventoryLookupSkill.execute() │  → InventoryState
       └───────────────────────────────┘
    │
    ▼
WarehouseState  (assembled, with StateFreshness + StateProvenance per domain)
    │
    ▼
WarehouseStateSnapshot.seal()  ← immutable, UUID-identified
    │
    ▼
Agent reasoning → ActionProposal (NEVER executed directly)
    │
    ▼
DecisionEngine.evaluate(DecisionRequest)
    │
    ├─ READ_ONLY → APPROVED
    ├─ stale state → REQUIRES_FRESH_STATE
    ├─ asset not in snapshot → REJECTED
    ├─ MEDIUM/HIGH/CRITICAL or requires_approval=True → REQUIRES_HUMAN_APPROVAL
    └─ LOW, no approval → APPROVED
    │
    ▼
DecisionResult + DecisionAuditRecord
```

### New Packages

| Package | Location | Depends on |
|---------|----------|-----------|
| `maiw-state` | `packages/maiw-state/` | `maiw-mcp` |
| `maiw-decision` | `packages/maiw-decision/` | `maiw-mcp`, `maiw-state` |

### Key Invariants

1. **No MCP write during decision**: `DecisionEngine.evaluate()` is synchronous and pure — no capability calls, no I/O.
2. **ActionProposal never executes itself**: write operations are proposed, evaluated, and returned; execution is a separate (future) step.
3. **Snapshot immutability**: `WarehouseStateSnapshot` carries the `snapshot_id` referenced in every audit record — decisions are always traceable to an exact state version.
4. **Circular dependency prevention**: `maiw-state` uses `typing.Protocol` for skill injection; it never imports `src/api/`.

### New Test Files (Phase 4)

| File | Tests | Coverage |
|------|-------|---------|
| `tests/unit/test_warehouse_state.py` | 37 | State composition, freshness, provenance, snapshot, provider, errors |
| `tests/unit/test_decision_engine.py` | 18 | All outcome paths, audit fields, constraint violations |
| `tests/mcp/test_decision_integration.py` | 7 | End-to-end: skill → snapshot → engine → REQUIRES_HUMAN_APPROVAL |

**Phase 4 total: 319 tests passing** (37 inventory contract + 44 equipment contract + 31 inventory MCP + 28 equipment MCP + 117 model gateway + 37 warehouse state + 18 decision engine + 7 decision integration)

### Documentation

- [`WAREHOUSE_STATE.md`](WAREHOUSE_STATE.md) — state assembly, freshness, provenance, snapshot semantics, adding domains
- [`DECISION_ENGINE.md`](DECISION_ENGINE.md) — outcomes, rule evaluation order, audit records, extending the rule set

---

## Phase 6 — Equipment Action Lifecycle (PROPOSE → DECIDE → EXECUTE → RESULT)

### New Capabilities

Five new MCP tools added to `mcp_servers/equipment/server.py`:

| Tool | Purpose |
|------|---------|
| `warehouse.equipment.propose_release` | Build `ActionProposal.for_equipment_release()` |
| `warehouse.equipment.propose_maintenance` | Build `ActionProposal.for_schedule_maintenance()` |
| `warehouse.equipment.execute_assign` | Execute an APPROVED assignment write |
| `warehouse.equipment.execute_release` | Execute an APPROVED release write |
| `warehouse.equipment.execute_maintenance` | Execute an APPROVED maintenance schedule write |

### New Contracts (`packages/maiw-mcp/maiw_mcp/contracts/`)

**`actions.py`** — two new factory classmethods on `ActionProposal`:
- `for_equipment_release(asset_id, released_by, ...)` — `risk_level=LOW`, `requires_approval=False`
- `for_schedule_maintenance(asset_id, maintenance_type, ...)` — `risk_level=MEDIUM`, `requires_approval=True`

**`equipment.py`** — new request/result types:
- `EquipmentReleaseRequest / EquipmentReleaseProposalResult`
- `EquipmentMaintenanceScheduleRequest / EquipmentMaintenanceProposalResult`
- `EquipmentExecuteAssignRequest / EquipmentExecuteAssignResult`
- `EquipmentExecuteReleaseRequest / EquipmentExecuteReleaseResult`
- `EquipmentExecuteMaintenanceRequest / EquipmentExecuteMaintenanceResult`

### New Source Files

| File | Purpose |
|------|---------|
| `src/api/agents/inventory/action_executor.py` (rewrite) | `EquipmentActionExecutor`, `NoOpActionExecutor`, typed error hierarchy |
| `src/api/agents/inventory/state_aware_ops.py` (extended) | `propose_equipment_release`, `propose_schedule_maintenance`, `_execute_action` |
| `src/api/skills/equipment.py` (extended) | `ExecuteEquipmentAssignmentSkill`, `ExecuteEquipmentReleaseSkill`, `ExecuteEquipmentMaintenanceSkill` + factories |

### Test Files Added (Phase 6)

| File | Tests | Coverage |
|------|-------|---------|
| `tests/unit/test_action_executor.py` | 14 | Executor guards (5), skill routing, backend errors, NoOp backward compat |
| `tests/unit/test_state_aware_ops_phase6.py` | 10 | Execution paths, release/maintenance proposals, warehouse_id, trace_id |

**Phase 6 total: 361 tests passing** (319 Phase 4 baseline + 18 Phase 5 + 14 action executor + 10 state_aware_ops Phase 6)

