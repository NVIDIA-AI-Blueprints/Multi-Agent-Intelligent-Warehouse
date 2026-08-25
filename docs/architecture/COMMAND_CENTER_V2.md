# MAIW Command Center v2

<!-- Phase 10 — UI design spec for the v2 operational UI -->

## Purpose

The Command Center makes the MAIW v2 pipeline understandable to an operator
without requiring knowledge of the internal code.

An operator using the Command Center should be able to:

- See current warehouse state (inventory, equipment, labor, wave)
- Understand what the AI is proposing and why
- Know whether an action is approved, rejected, or blocked
- Trace how an approved action reaches a warehouse capability
- Assess system health without reading logs

---

## Primary Mental Model: The Decision Lifecycle

```
OBSERVE warehouse state
    ↓
REASON (ModelGateway → Nemotron)
    ↓
PROPOSE (ActionProposal)
    ↓
DECIDE (DecisionEngine)
    ↓
APPROVE / REJECT / REQUIRES_HUMAN_APPROVAL / REQUIRES_FRESH_STATE
    ↓
EXECUTE (ActionExecutor → MCP v2 → capability)
    ↓
OBSERVE OUTCOME
```

This lifecycle is the organizing principle for the UI, not individual agents.

---

## Views

### 1. Command Center Home (Dashboard)

Primary areas visible without navigation:

| Area | Data source |
|---|---|
| Warehouse State summary | `GET /api/v1/equipment`, `/api/v1/operations/tasks`, `/api/v1/operations/workforce` |
| Active Operational Risks | Derived from state responses (stale data, low capacity flags) |
| AI Recommendations | Recent ActionProposals (session/runtime data) |
| Pending Decisions | `REQUIRES_HUMAN_APPROVAL` results |
| Recent Executions | ActionExecutionResult log (session data) |
| Capability Health | `GET /api/v1/runtime/status`, `GET /api/v1/mcp/status` |

### 2. Warehouse State View

Covers all four implemented domains:

| Domain | Read endpoint | Key fields |
|---|---|---|
| Equipment | `GET /api/v1/equipment` | asset_id, status, location, last_updated |
| Operations / Tasks | `GET /api/v1/operations/tasks` | task_id, type, status, assignee, priority |
| Operations / Workforce | `GET /api/v1/operations/workforce` | shift, headcount, zone_allocations |
| Safety / Incidents | `GET /api/v1/safety/incidents` | type, severity, status, timestamp |
| Safety / Policies | `GET /api/v1/safety/policies` | domain, rule, active |

State freshness should be visually obvious. If `last_updated` is more than a
configurable threshold ago, the cell should render as stale (e.g. amber border).

### 3. Decision Center

Shows the full lifecycle view of an equipment action cycle:

- What was proposed (`ActionProposal`)
- What warehouse state was used (`snapshot_id`)
- What the DecisionEngine decided (`DecisionResult`)
- Decision status: `approved` / `rejected` / `requires_human_approval` / `requires_fresh_state`
- Risk level
- Whether execution occurred (`ActionExecutionResult`)

**Endpoint mapping:**

```
POST /api/v1/equipment/assign   → returns DecisionResult + ExecutionResult
POST /api/v1/equipment/release
POST /api/v1/equipment/maintenance
```

Decision status values (as returned by the API):

| Status | UI label | Meaning |
|---|---|---|
| `approved` | Approved & Executed | DecisionEngine approved; executor ran |
| `rejected` | Rejected | DecisionEngine rejected the proposal |
| `requires_human_approval` | Pending Approval | Risk too high for autonomous execution |
| `requires_fresh_state` | Blocked — Stale State | State snapshot too old to act on |

### 4. Pending Approval View

Displays `REQUIRES_HUMAN_APPROVAL` results as read-only cards:

Fields to show:
- Action type (assign / release / maintenance)
- Equipment asset ID
- Parameters (assignee, zone, schedule)
- Warehouse ID
- Risk level
- Snapshot age (how old was the state when the decision was made)
- `proposal_id` / `decision_id`
- Reason phrase

> **Note:** Approval submission is not yet implemented in the backend.
> The view is read-only. The submit button should be labeled
> "Approval submission not yet available" or hidden entirely.
> Do not fake state transitions.

### 5. Rejected / Blocked Actions

`REJECTED` and `REQUIRES_FRESH_STATE` are normal operational outcomes.
Render them as informational cards, not as errors.

Examples:

```
Wave reprioritization blocked
Reason: equipment state stale (snapshot age: 4 min, limit: 2 min)

Equipment assignment rejected
Reason: target zone at capacity
```

### 6. Execution History

Shows recent `ActionExecutionResult` values:

| Field | Source |
|---|---|
| action_type | ExecutionResult |
| success | ExecutionResult |
| execution_id | ExecutionResult |
| provider | ExecutionResult |
| latency_ms | ExecutionResult |
| timestamp | ExecutionResult |

If no persistence exists, show session/in-memory results only.
Do not invent an audit database.

### 7. Model Gateway View

Technical/operator view showing current model routing.

Data from `GET /api/v1/runtime/status` (availability) and future telemetry
endpoint. Initially show:

- `model_gateway_available: true/false`
- `decision_engine_available: true/false`

When model telemetry endpoint is available, add:

| Field | Value |
|---|---|
| Task | e.g. `equipment_assessment` |
| Role | e.g. `reasoning` |
| Selected model | e.g. `Nemotron Super` |
| Routing reason | e.g. `default` |
| Latency | 1.2s |
| Success | true |

Do not expose raw prompts or credentials.

### 8. Nemotron / Model Registry View

Shows current model roles from the ModelRegistry.

Render by logical role, not hardcoded model names:

| Role | Model |
|---|---|
| Lightning | Nemotron Lightning (fastest) |
| Nano | Nemotron Nano |
| Super | Nemotron Super |
| Ultra | Nemotron Ultra (most capable) |

Source: `GET /api/v1/runtime/status` → `model_gateway_available`.
Full role details: ModelRegistry (not exposed via API yet — Phase 10 deferred).

### 9. Capability Plane View

MCP domain status using `GET /api/v1/mcp/status` and `/api/v1/mcp/capabilities`.

| Domain | Configured | Available | Capabilities |
|---|---|---|---|
| Inventory | `inventory_mcp_configured` | runtime flag | `warehouse.inventory.get`, `.locate` |
| Equipment | `equipment_mcp_configured` | runtime flag | `warehouse.equipment.*` (5 caps) |
| Labor | `labor_mcp_configured` | runtime flag | `warehouse.labor.*` (3 caps) |
| Wave | `wave_mcp_configured` | runtime flag | `warehouse.wave.*` (3 caps) |

Each capability card should show READ / PROPOSAL / EXECUTION classification
and risk level (from `CAPABILITY_MATRIX.md`).

Source for availability: `GET /api/v1/runtime/status`
Source for capability list: `GET /api/v1/mcp/capabilities`

### 10. Agent View

Agents are reasoning roles, not tool-owners. Show:

| Agent | Domain | Uses |
|---|---|---|
| Equipment Asset Operations Agent | Equipment | ModelGateway, WarehouseState, Equipment Skills |
| Operations Coordination Agent | Labor / Wave | ModelGateway, WarehouseState, Labor+Wave Skills |
| Safety Compliance Agent | Safety | ModelGateway, WarehouseState |

Availability: `GET /api/v1/runtime/status` → `equipment_agent_available`, etc.

Do not show agents as the primary entry point. Show them as components
of the decision pipeline.

### 11. System Health View

Single page for all component status:

| Component | Source |
|---|---|
| API process | `GET /api/v1/live` |
| MAIWRuntime | `GET /api/v1/runtime/status` → `runtime_initialized` |
| ModelGateway | `GET /api/v1/runtime/status` → `model_gateway_available` |
| Inventory MCP | `GET /api/v1/runtime/status` → `inventory_mcp_configured` |
| Equipment MCP | `GET /api/v1/runtime/status` → `equipment_mcp_configured` |
| Labor MCP | `GET /api/v1/runtime/status` → `labor_mcp_configured` |
| Wave MCP | `GET /api/v1/runtime/status` → `wave_mcp_configured` |
| Database | `GET /api/v1/health` → `services.database.status` |
| Redis | `GET /api/v1/health` → `services.redis.status` |
| Milvus | `GET /api/v1/health` → `services.milvus.status` |

Render as a simple green/amber/red grid. This is not a full monitoring
platform. Do not build alert routing or notification pipelines.

---

## UI → API Mapping Summary

| View | Primary endpoint | Canonical package |
|---|---|---|
| System Health | `/api/v1/live`, `/api/v1/runtime/status`, `/api/v1/health` | `maiw_api.routers.health`, `maiw_api.routers.runtime_status` |
| Capability Plane | `/api/v1/mcp/status`, `/api/v1/mcp/capabilities` | `maiw_api.routers.mcp_status` |
| Warehouse State — Equipment | `/api/v1/equipment` | `maiw_api.routers.equipment` |
| Warehouse State — Operations | `/api/v1/operations/tasks`, `/api/v1/operations/workforce` | `maiw_api.routers.operations` |
| Warehouse State — Safety | `/api/v1/safety/incidents`, `/api/v1/safety/policies` | `maiw_api.routers.safety` |
| Decision Center | `/api/v1/equipment/assign`, `/release`, `/maintenance` | `maiw_api.routers.equipment` |
| Agent View | `/api/v1/runtime/status` | `maiw_api.routers.runtime_status` |
| Model Gateway View | `/api/v1/runtime/status` | `maiw_api.routers.runtime_status` |

---

## Terminology

Use v2 terms. Do not use v1 terms.

| Old (v1) | New (v2) |
|---|---|
| Llama model | Nemotron |
| custom MCP | MCP v2 / Streamable HTTP |
| agent directly executes tool | Agent → Skills → DecisionEngine → ActionExecutor → MCP |
| five-agent architecture | three-agent reasoning plane + capability layer |
| tool | skill (read/proposal) or MCP capability (execution) |

---

## Constraints

- The UI must call only `apps/api` endpoints
- The UI must not call MCP servers directly
- The UI must not embed credentials
- The UI must not know database schemas
- Approval submission must not be implemented until the backend supports it
- Do not fabricate data for visual richness
