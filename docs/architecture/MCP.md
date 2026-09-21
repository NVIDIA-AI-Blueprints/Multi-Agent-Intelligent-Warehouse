# MAIW v2 MCP Architecture

> **Status:** Current — authoritative reference for MAIW v2.  
> **SDK:** `mcp>=2.0.0,<3` · Protocol version `2026-07-28`  
> **Last updated:** 2026-09-20

---

## Central Principle

**MCP is the interoperability layer, not the authority layer.**

MCP defines how MAIW capabilities are discovered, invoked, and monitored across
process boundaries. It says nothing about *whether* a capability may be invoked.
That authority belongs to the governed write path:
`DecisionEngine → Human Approval → ActionExecutor`.
Every write tool call that crosses the MCP boundary has already passed six
sequential guards in `BaseActionExecutor` before the wire is ever touched.

---

## 1. System Overview

MAIW v2 exposes warehouse capabilities as MCP tools hosted by four dedicated
servers (equipment, labor, wave, inventory). Agents and skills call those tools
exclusively through `MAIWMCPClient`. The LLM layer reasons and recommends; it
never touches the write path.

```
┌─────────────────── MAIW Authority Boundary ────────────────────────┐
│                                                                      │
│  Agent / SOP Runtime                                                 │
│      │                                                               │
│      ▼                                                               │
│  RecommendedAction           (AI reasoning output — read-only)       │
│      │                                                               │
│      ▼                                                               │
│  ActionProposal              (maiw-decision — struct, not request)   │
│      │                                                               │
│      ▼                                                               │
│  DecisionEngine              (policy evaluation)                     │
│      │                                                               │
│      ▼                                                               │
│  Human Approval Gate         (if requires_approval == True)          │
│      │                                                               │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ │
│  (write path only crosses this line after APPROVED decision)         │
│      │                                                               │
│      ▼                                                               │
│  BaseActionExecutor          (6 guards, maiw-execution)              │
│      │                                                               │
└──────┼───────────────────────────────────────────────────────────────┘
       │
       ▼  (MCP boundary — interoperability layer)
   MAIWMCPClient
       │
       ▼
   mcp.client.Client           (official MCP SDK 2.0, protocol 2026-07-28)
       │
       ▼
   MCPServer                   (one per domain — equipment / labor / wave / inventory)
       │
       ▼
   Provider / MAIW Backend Adapter
       │
       ▼
   Operational System          (warehouse equipment, labor, wave, inventory)
```

Read tools (inventory lookup, equipment status, labor capacity, wave risk) follow
the same path from the top but bypass the authority chain — skills call
`MAIWMCPClient.invoke()` directly after the reasoning phase.

---

## 2. Package Ownership

| Package | Owns | Does NOT own |
|---------|------|-------------|
| `maiw-contracts` | `CapabilityMetadata`, domain request/result models, tool name constants | ActionProposal, decision logic |
| `maiw-mcp` | `MAIWMCPClient`, `CapabilityRegistry`, auth, telemetry, circuit breaker, deadline, testing utilities | Warehouse domain contracts, ActionProposal |
| `maiw-decision` | `ActionProposal`, `DecisionEngine`, `DecisionResult`, `ApprovalStore`, `RiskLevel` | MCP transport |
| `maiw-execution` | `BaseActionExecutor`, domain executors (equipment, labor, wave), `ExecutionOutcome`, reconciliation | Decision policy |
| `mcp_servers/*` | Per-domain MCP servers (MCPServer instances with tool registrations and provider injection) | Domain business logic |

`maiw-mcp` has **zero imports** from `maiw-decision`. The two packages are
independent; `ActionProposal` is passed into `BaseActionExecutor` from the
orchestrator layer, not from within the MCP client.

There is **no `contracts/` subdirectory** inside `packages/maiw-mcp/maiw_mcp/`.
All domain contracts live in `packages/maiw-contracts/maiw_contracts/`.

---

## 3. Capability Taxonomy

All capability names follow the pattern `warehouse.<domain>.<action>` (enforced
by `CapabilityMetadata` field validation).

### Read capabilities

| Capability | Domain | Defined in |
|-----------|--------|-----------|
| `warehouse.inventory.get` | inventory | `maiw_contracts/inventory.py` |
| `warehouse.inventory.locate` | inventory | `maiw_contracts/inventory.py` |
| `warehouse.equipment.get_status` | equipment | `maiw_contracts/equipment.py` |
| `warehouse.equipment.get_telemetry` | equipment | `maiw_contracts/equipment.py` |
| `warehouse.labor.get_capacity` | labor | `maiw_contracts/labor.py` |
| `warehouse.labor.get_allocation` | labor | `maiw_contracts/labor.py` |
| `warehouse.wave.get` | wave | `maiw_contracts/wave.py` |
| `warehouse.wave.get_risk` | wave | `maiw_contracts/wave.py` |

### Write capabilities (require APPROVED DecisionResult)

| Capability | Domain | Risk level | Requires approval |
|-----------|--------|-----------|-------------------|
| `warehouse.equipment.assign` | equipment | MEDIUM | Yes |
| `warehouse.equipment.release` | equipment | LOW | No |
| `warehouse.equipment.schedule_maintenance` | equipment | MEDIUM | Yes |
| `warehouse.labor.allocate` | labor | MEDIUM | Yes |
| `warehouse.wave.reprioritize` | wave | MEDIUM | Yes |

Write tool functions require `proposal_id` and `decision_id` as mandatory
parameters. `BaseActionExecutor` verifies these match the approved
`DecisionResult` before the MCP call is made.

`CapabilityMetadata` carries `side_effect` (`"read"` | `"write"` | `"action"`),
`risk` (`"low"` | `"medium"` | `"high"`), `idempotent`, and `timeout_seconds`.
These fields are informational at this time; `required_permission` is defined
but not yet enforced at runtime.

---

## 4. Write Path Authority Chain

`BaseActionExecutor.execute()` enforces six guards in order before any write
reaches the MCP layer:

1. **APPROVED gate** — `decision.outcome == DecisionOutcome.APPROVED`; raises `ActionNotApproved`
2. **Proposal/decision bind** — `decision.proposal_id == proposal.proposal_id`; raises `ActionDecisionMismatch`
3. **Action allowlist** — `proposal.action in self._ALLOWED_ACTIONS`; raises `ActionUnsupported`
4. **Staleness check** — decision age ≤ `max_decision_age_seconds` (default 300 s); raises `ActionExpired`
5. **Additional guards** — `await self._check_additional_guards(proposal)` (subclass hook); raises `ActionConflict`
6. **Deadline check** — `deadline.expired` immediately before write; raises `RequestDeadlineExceeded` (no mutation occurs)

Only after all six guards pass does `_do_execute()` call `MAIWMCPClient.invoke()`
with the write capability.

`ActionProposal` factory classmethods (`ActionProposal.for_equipment_assign()`,
`for_labor_allocate()`, etc.) are defined in `maiw-decision/maiw_decision/proposal.py`.

---

## 5. MAIWMCPClient

File: `packages/maiw-mcp/maiw_mcp/client/client.py`

### MCP SDK imports

```python
from mcp import types
from mcp.client import Client
```

`ClientSession`, `streamablehttp_client`, `create_connected_server_and_client_session`,
and manual `session.initialize()` calls are **not used**. The v2 SDK's `Client`
context manager handles the full lifecycle.

### Constructor

```python
class MAIWMCPClient:
    def __init__(
        self,
        registry: CapabilityRegistry,
        *,
        telemetry: CapabilityTelemetry | None = None,
        circuit_registry: DomainCircuitRegistry | None = None,
    ) -> None:
```

### Public API

```python
async def invoke(
    self,
    capability: str,
    payload: dict[str, Any],
    *,
    trace_id: str | None = None,
    timeout_seconds: float = 30.0,
    deadline: RequestDeadline | None = None,
) -> dict[str, Any]:
```

`invoke()` is the sole public method.

### Internal call chain

```
MAIWMCPClient.invoke(capability, payload)
  → CapabilityRegistry.resolve(capability)          → server_url
  → DomainCircuitRegistry.get(domain).call(...)     → circuit guard
  → _call_tool(capability, payload, server_url, effective_timeout)
      → async with Client(server_url, read_timeout_seconds=timeout) as client:
          result: types.CallToolResult = await client.call_tool(capability, payload)
      → check result.is_error
      → _parse_result(result)
          → check result.structured_content
          → fallback: parse JSON from TextContent
```

`Client` accepts either a string URL (Streamable HTTP) or an `MCPServer` instance
(in-memory transport for tests). No transport-specific code in the client.

### Error taxonomy

| Condition | Exception |
|-----------|-----------|
| Deadline already expired at call entry | `RequestDeadlineExceeded` |
| Circuit breaker OPEN | `MCPUnavailable` |
| `call_result.is_error == True` | `MCPToolError` |
| Non-JSON or non-dict result | `MCPContractError` |
| `TimeoutError` from SDK | `MCPTimeout` |
| All other `Exception` | `MCPUnavailable` |
| `CapabilityNotFound`, `BackendUnavailable` | re-raised as-is |

---

## 6. Capability Registry

File: `packages/maiw-mcp/maiw_mcp/registry/registry.py`

```python
class CapabilityRegistry:
    def register(self, capability: str, server_url: object) -> None
    def register_domain(self, capabilities: list[str], server_url: object) -> None
    def resolve(self, capability: str) -> object      # raises CapabilityNotFound
    def all_capabilities(self) -> list[str]
    def is_registered(self, capability: str) -> bool
    @classmethod def from_env(cls) -> "CapabilityRegistry"
```

`from_env()` reads `MAIW_MCP_SERVER_INVENTORY_URL` and registers the two
inventory capabilities. Equipment, labor, and wave capabilities are registered
programmatically via `register_domain()` in application bootstrap code. The env
vars `MAIW_MCP_SERVER_EQUIPMENT_URL`, `MAIW_MCP_SERVER_LABOR_URL`, and
`MAIW_MCP_SERVER_WAVE_URL` are planned but not yet read by `from_env()`.

`server_url` accepts a string URL or an `MCPServer` instance. `mcp.client.Client`
handles both transports transparently.

---

## 7. MCP Servers

All four domain servers follow the same pattern.

### Server primitive

```python
from mcp.server import MCPServer   # all four servers — equipment, labor, wave, inventory
```

`FastMCP` is not used anywhere in the codebase.

### Tool registration

```python
@mcp_server.tool(
    name=SOME_CAPABILITY_METADATA.name,
    description=SOME_CAPABILITY_METADATA.description,
)
async def warehouse_<domain>_<action>(...) -> str:
    ...
```

Tool names and descriptions come from `CapabilityMetadata` constants in
`maiw-contracts`. Tool functions return JSON strings.

### Provider injection

Each server module exposes a `configure_server(provider)` function that sets a
module-level `_provider` global. Production startup calls this once with the real
backend adapter. Tests call it with a mock. No imports of the backend adapter
occur at module load time (deferred import in `_build_default_provider()`).

### Transport

```python
if transport == "streamable-http":
    mcp_server.run("streamable-http", host=host, port=port, stateless_http=True)
elif transport == "sse":
    mcp_server.run("sse", host=host, port=port)
else:
    mcp_server.run("stdio")
```

`stateless_http=True` enables Kubernetes horizontal scaling with no session
affinity. Controlled by `MAIW_MCP_TRANSPORT` env var (default: `stdio`).

---

## 8. Domain Contracts (`maiw-contracts`)

File layout:

```
packages/maiw-contracts/maiw_contracts/
    common.py      — CapabilityMetadata (base dataclass for all tool metadata)
    equipment.py   — request/result models + EQUIPMENT_* metadata constants
    inventory.py   — request/result models + INVENTORY_* metadata constants
    labor.py       — request/result models + LABOR_* metadata constants
    wave.py        — request/result models + WAVE_* metadata constants
```

`CapabilityMetadata` is the single source of truth for each capability's name,
description, `side_effect`, `risk`, `idempotent`, and `timeout_seconds`. Both
the MCP server tool registration and the capability registry use it.

---

## 9. Authentication

File: `packages/maiw-mcp/maiw_mcp/auth/auth.py`

Bearer token auth via `MAIW_MCP_API_KEY` environment variable:

```python
class MCPAuthConfig:
    @property
    def headers(self) -> dict[str, str]:
        if self._api_key:
            return {"Authorization": f"Bearer {self._api_key}"}
        return {}
```

OAuth 2.0 (via `mcp.client.auth.oauth2`) is the planned next step but is not
yet implemented.

---

## 10. Circuit Breaker

File: `packages/maiw-mcp/maiw_mcp/circuit_registry.py`

`DomainCircuitRegistry` maintains one `CircuitBreaker` per MCP domain:
`equipment`, `labor`, `wave`, `inventory`.

State machine: `CLOSED → OPEN → HALF_OPEN → CLOSED`

| Parameter | Default |
|-----------|---------|
| `consecutive_failures` threshold | 5 |
| `cooldown_seconds` | 30.0 |
| `success_threshold` (HALF_OPEN probe) | 1 |

Domain is extracted from the middle segment of `warehouse.<domain>.<action>`.
`CircuitOpen` is translated to `MCPUnavailable` at the `invoke()` boundary.
State transitions are protected by `asyncio.Lock`. A HALF_OPEN probe allows
exactly one in-flight call; additional callers receive `CircuitOpen` immediately.

---

## 11. Deadline and Timeout

File: `packages/maiw-mcp/maiw_mcp/deadline.py`

```python
@dataclass(frozen=True)
class RequestDeadline:
    @classmethod def from_timeout(cls, seconds: float) -> "RequestDeadline": ...
    @classmethod def unlimited(cls) -> "RequestDeadline": ...
    def effective_timeout(self, cap: float) -> float: ...  # min(cap, remaining)
    @property def expired(self) -> bool: ...
```

Two independent mechanisms:
- **`timeout_seconds`** (default 30.0): passed as `read_timeout_seconds` to `Client()`
- **`RequestDeadline`** (optional): monotonic-clock budget from request ingress; `effective_timeout()` returns `min(timeout_seconds, deadline.remaining_seconds)`. Deadline expired at call entry raises `RequestDeadlineExceeded` before any network I/O.

---

## 12. Telemetry

File: `packages/maiw-mcp/maiw_mcp/telemetry/telemetry.py`

`CapabilityTelemetry` emits structured `CapabilityCallRecord` JSON lines via
`logging.getLogger("maiw_mcp.telemetry")`.

Fields: `trace_id`, `capability_name`, `capability_version`, `mcp_server`,
`transport`, `latency_ms`, `success`, `error_class`, `error_message`,
`mcp_sdk_version`, `mcp_protocol_version` (hardcoded `"2026-07-28"`).

`record_success()` logs at INFO; `record_failure()` logs at ERROR. Telemetry is
recorded on `TimeoutError` and unclassified `Exception` only — domain exceptions
(`MCPToolError`, `MCPContractError`, `CapabilityNotFound`, etc.) re-raise without
a telemetry record.

---

## 13. Testing Architecture

`packages/maiw-mcp/maiw_mcp/testing/` provides:

| Module | Contents |
|--------|----------|
| `conformance.py` | `MCPConformanceSuite` — protocol-level tests runnable against any server |
| `fixtures.py` | Pytest fixtures: `mcp_client`, `capability_registry`, `mock_telemetry` |
| `mock_server.py` | `MockMCPServer` — in-memory test double with configurable tool responses |

In-memory transport (`async with Client(mcp_server) as client:`) is the default
test pattern — no network, no Docker. Production transport tests use
`MAIW_MCP_TRANSPORT=streamable-http` with a real server process.

---

## 14. Security Constraints

These constraints are enforced at the code boundary, not just at policy:

| Constraint | Rationale |
|-----------|-----------|
| `CopilotService` must not import `ActionExecutor`, `ApprovalStore`, or `DecisionEngine` | Copilot is a read/reasoning surface only |
| Router must not expose `/copilot/approve`, `/copilot/execute`, `/copilot/force-action` | No write path through the copilot HTTP API |
| `chain_of_thought`, `scratchpad`, `hidden_reasoning`, `reasoning_tokens` never in API responses | CoT is internal reasoning state, not operator-visible data |
| WORLD router (`/world`, `/world/*`) must not import `ActionExecutor`, `DecisionEngine`, `ApprovalStore`, `GovernedActionOrchestrator` | World is read-only; GET endpoints only |
| Model Lab backend must have zero imports of `DecisionEngine`, `ApprovalStore`, `ActionExecutor`, write MCP modules | Lab is evaluation-only; VIEW ONLY |
| Deep Agents runtime must use `ModelGateway` — no direct provider clients | Routing and cost governance must apply |
| `MAIWDeterministicRuntime` must not be removed | Deterministic runtime required for regression tests |
| Deep Agents must not be the default runtime | Production default is deterministic SOP runtime |
| No autonomous event triggering | All actions require an explicit decision chain |

---

## 15. Skill Layer

Canonical skill implementations live in the `maiw_skills.*` package tree.

`src/api/skills/` contains only deprecated compatibility shims marked for removal
by Phase 9. They re-export from `maiw_skills.*` without adding logic:

```python
# DEPRECATED compatibility shim — use maiw_skills.inventory directly. Remove by Phase 9.
from maiw_skills.inventory.lookup import InventoryLookupSkill, ...
```

Skills invoke `MAIWMCPClient.invoke()` for read capabilities. Write capabilities
are not invoked by skills directly — they are invoked by domain executors inside
`BaseActionExecutor._do_execute()` after all authority guards pass.

---

## 16. Known Gaps and Next Steps

| Area | Current state | Next step |
|------|--------------|-----------|
| `from_env()` domain wiring | Only inventory wired; equipment/labor/wave require programmatic `register_domain()` | Add `MAIW_MCP_SERVER_{EQUIPMENT,LABOR,WAVE}_URL` to `from_env()` |
| Auth wiring | `MCPAuthConfig.headers` defined but not injected into `Client()` | Wire auth headers at `Client` construction |
| OAuth 2.0 | Not implemented; bearer token only | Implement via `mcp.client.auth.oauth2` |
| `required_permission` enforcement | Field defined on `CapabilityMetadata` but not enforced | Enforce at `CapabilityRegistry.resolve()` |
| Labor/wave `__main__` block | Not defined in current server files | Add for consistency with inventory/equipment |

---

## 17. Migration History

This section preserves the v1 → v2 SDK migration record for reference. All v2
code in the current codebase uses the v2 APIs exclusively.

### SDK v1 → v2 breaking changes

| v1 (removed) | v2 (current) | Notes |
|-------------|-------------|-------|
| `streamablehttp_client` | `Client(url)` | `mcp.client` |
| `ClientSession` | `Client` context manager | `mcp.client` |
| `session.initialize()` | implicit in `async with Client()` | automatic |
| `create_connected_server_and_client_session()` | `async with Client(MCPServer)` | in-memory transport |
| `result.isError` (camelCase) | `result.is_error` | `mcp.types.CallToolResult` |
| `tool.inputSchema` (camelCase) | `tool.input_schema` | `mcp.types.Tool` |
| `FastMCP` | `MCPServer` | `mcp.server` |

Protocol version promoted from `2024-11-05` (v1) to `2026-07-28` (v2).

In-memory transport was available in v1 via `create_connected_server_and_client_session()`;
in v2 it is `async with Client(mcp_server)` — same semantics, simpler API.

---

## Appendix: File Index

```
packages/maiw-mcp/maiw_mcp/
    client/client.py          — MAIWMCPClient
    registry/registry.py      — CapabilityRegistry
    auth/auth.py              — MCPAuthConfig
    circuit_breaker.py        — CircuitBreaker (state machine)
    circuit_registry.py       — DomainCircuitRegistry
    deadline.py               — RequestDeadline
    errors.py                 — MCPToolError, MCPContractError, MCPTimeout, MCPUnavailable, ...
    telemetry/telemetry.py    — CapabilityTelemetry, CapabilityCallRecord
    testing/conformance.py    — MCPConformanceSuite
    testing/fixtures.py       — pytest fixtures
    testing/mock_server.py    — MockMCPServer

packages/maiw-contracts/maiw_contracts/
    common.py                 — CapabilityMetadata
    equipment.py / inventory.py / labor.py / wave.py

packages/maiw-decision/maiw_decision/
    proposal.py               — ActionProposal (with factory classmethods)
    engine.py                 — DecisionEngine
    approval.py               — ApprovalStore
    models.py                 — DecisionResult, DecisionOutcome, RiskLevel
    audit.py                  — AuditLog

packages/maiw-execution/maiw_execution/
    base.py                   — ActionExecutor (Protocol), BaseActionExecutor (6 guards)
    equipment.py / labor.py / wave.py
    outcome.py                — ExecutionOutcome
    reconciliation.py         — ReconciliationEngine
    registry.py               — ExecutorRegistry

mcp_servers/
    equipment/server.py       — MCPServer, tool registrations, configure_server()
    inventory/server.py       — MCPServer, tool registrations, configure_server()
    labor/server.py           — MCPServer, tool registrations, configure_server()
    wave/server.py            — MCPServer, tool registrations, configure_server()
```
