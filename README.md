# Multi-Agent Intelligent Warehouse (MAIW)

*An NVIDIA AI Blueprint for agentic warehouse operations powered by Nemotron 3 and MCP v2.*

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.120+-green.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19+-61dafb.svg)](https://reactjs.org/)
[![NVIDIA NIMs](https://img.shields.io/badge/NVIDIA-NIMs-76B900.svg)](https://www.nvidia.com/en-us/ai-data-science/nim/)

---

## What MAIW Is

MAIW is a multi-agent system that lets warehouse operators ask natural-language questions and issue
structured commands against live warehouse data. It does not answer from static knowledge. Instead,
each agent assembles real-time state, reasons over it with a Nemotron model, proposes a concrete
action, passes the proposal through a local decision engine, and — if approved — executes it
through an MCP v2 capability server that writes to the backend database.

The system is designed around a single non-negotiable invariant: **the LLM never touches a write
path directly**. Every mutation is proposed, evaluated by a deterministic policy engine, and
executed by a typed executor that enforces four guards before a write reaches MCP.

---

## Architecture

![MAIW Runtime Pipeline](docs/architecture/diagrams/maiw-runtime-pipeline.png)

### Pipeline Stages

| Stage | Component | What it does |
|-------|-----------|--------------|
| **STATE** | `WarehouseStateProvider` | Assembles live snapshot of inventory, equipment, labor, and wave data via MCP read tools |
| **REASON** | `ModelGateway` → Nemotron 3 | Generates a structured action proposal — no raw text, no direct tool calls |
| **PROPOSE** | `ActionProposal` factory | Constructs a typed, immutable proposal locally; zero MCP calls at this stage |
| **DECIDE** | `DecisionEngine` | Evaluates the proposal against deterministic constraints → `APPROVED / REJECTED / DEFERRED` |
| **EXECUTE** | `BaseActionExecutor` | Enforces 4 guards, assigns a stable `execution_id`, then invokes the MCP write capability; result is one of six explicit outcomes: `EXECUTED / NO_OP / DEFERRED / CONFLICT / UNKNOWN / FAILED` |
| **MCP** | `mcp_servers.<domain>.server` | Independently deployable MCP v2 server; single entry point to backend writes |
| **BACKEND** | PostgreSQL / TimescaleDB | Source of truth; no agent writes directly here |

---

## Core Design Principles

1. **LLMs propose, policy decides.** The `DecisionEngine` is synchronous, deterministic, and
   performs no I/O. It cannot be overridden by a model-generated argument.

2. **Every write passes through a typed executor.** `BaseActionExecutor` checks four guards in
   order before any MCP write tool is called: (1) decision outcome is `APPROVED`, (2) decision
   binds to the exact proposal ID, (3) action name is in the executor's static allowlist,
   (4) the decision is not stale.

3. **State is immutable once sealed.** `WarehouseStateSnapshot.seal()` assigns a UUID and freezes
   the snapshot. Proposals reference the snapshot ID; the executor performs a best-effort state
   drift check before executing.

4. **Packages have one-way dependency flow.** `maiw-models` and `maiw-mcp` have no upstream
   dependencies. `maiw-state` and `maiw-skills` depend only on those. `maiw-decision` and
   `maiw-execution` depend on skills and state. `maiw-agents` depends on all of them. Nothing
   in any canonical package imports from `src.*`.

5. **MCP is the write plane, not a chat interface.** MCP tools are not exposed to the LLM's tool
   registry. The LLM produces a proposal; the executor translates that proposal to an MCP call.

---

## Nemotron Model Gateway

All inference is routed through a centralized `ModelGateway`. Agents specify what they need
(reasoning depth, risk level, task type) — never a physical model ID.

### Model Roles

| Role | Default model | Active params | Use case |
|------|--------------|--------------|----------|
| `lightning` | `nvidia/nemotron-3.5-lightning-30b-a3b` | 3B | Fast chat, intent classification |
| `nano` | `nvidia/nemotron-3-nano-30b-a3b` | 3B | Low-latency reads, summaries |
| `super` | `nvidia/nemotron-3-super-120b-a12b` | 12B | Standard operational reasoning |
| `ultra` | `nvidia/nemotron-3-ultra-550b-a55b` | 55B | Deep analytical tasks (opt-in, slow) |

All four models are confirmed live on `integrate.api.nvidia.com/v1` (validated 2026-08-20).
The suffix `a3b / a12b / a55b` is active parameter count under the MoE architecture.

Agents use `ReasoningLevel` (`FAST / STANDARD / DEEP / ANALYTICAL`) and `RiskLevel`; the
`ModelRouter` resolves the appropriate role. Override any role via environment variable
(see [Configuration](#configuration)).

**Legacy models retired:** All `nvidia/llama-*` Nemotron model IDs return 404 or broken
responses and are no longer used. Their identifiers are preserved as `LEGACY_*` constants in
`packages/maiw-models/maiw_models/registry.py` for audit purposes only.

See [docs/architecture/MODEL_GATEWAY.md](docs/architecture/MODEL_GATEWAY.md) for full routing
policy, telemetry schema, and role-to-model override documentation.

---

## Warehouse State

`WarehouseState` aggregates live data from four domains. State assembly always precedes
proposal generation.

```python
# Agents never construct state manually — they call the provider:
state = await state_provider.get_state(
    StateRequirements(equipment=True, asset_id="FORKLIFT-07")
)
snapshot = WarehouseStateSnapshot.seal(state)  # immutable, UUID-stamped
```

| Domain | State type | Key fields |
|--------|-----------|------------|
| Inventory | `InventoryState` | SKU levels, locations, reorder flags |
| Equipment | `EquipmentState` | status, battery, assignment, location |
| Labor | `LaborState` | capacity, allocations, shift info |
| Wave | `WaveState` | active waves, priorities, risk scores |

`StateFreshness` tracks age per domain. `StateProvenance` records which MCP tool provided each
value. Stale state triggers `DEFERRED` decisions rather than silent execution with bad data.

See [docs/architecture/WAREHOUSE_STATE.md](docs/architecture/WAREHOUSE_STATE.md).

---

## Skills and Capability Contracts

Skills are stateless, typed units of work. Each skill has a defined input schema, output type,
and declared capability name. They are the only layer that generates `ActionProposal` objects.

```python
# Read skill — calls MCP, returns typed result
result = await EquipmentStatusSkill(mcp_client=client).execute(asset_id="FORKLIFT-07")

# Write skill — builds proposal locally, NO MCP call
proposal = await EquipmentAssignmentSkill().execute(asset_id="FORKLIFT-07", task_id="TASK-42")
# proposal is an ActionProposal — it describes intent, does not perform it
```

Skills live in `packages/maiw-skills/`. They do not import `src.*`, do not hold infrastructure
connections, and can be instantiated in tests without database or network access.

---

## Decision and Execution Architecture

### DecisionEngine

`DecisionEngine` takes a `DecisionRequest` (proposal + state snapshot) and returns a
`DecisionResult` with outcome `APPROVED`, `REJECTED`, or `DEFERRED`. It is synchronous and
performs no I/O. Constraint rules are deterministic Python — not LLM-evaluated.

```
DecisionRequest(proposal, snapshot)
    │
    ├── Rule 1: Proposal is structurally valid
    ├── Rule 2: Action is in the allowed capability set for this agent
    ├── Rule 3: Risk level is within domain policy
    ├── Rule 4: State is within freshness bounds
    ├── Rule 5: LOW risk + requires_approval=False → APPROVED immediately
    └── ...
    │
    ▼
DecisionResult(outcome=APPROVED|REJECTED|DEFERRED, violations=[...], rationale=...)
```

See [docs/architecture/DECISION_ENGINE.md](docs/architecture/DECISION_ENGINE.md).

### BaseActionExecutor (4-Guard Pattern)

All three domain executors (`EquipmentActionExecutor`, `LaborActionExecutor`,
`WaveActionExecutor`) inherit from `BaseActionExecutor`. Before any MCP write tool is invoked,
the executor runs four mandatory guards in order:

1. **APPROVED gate** — `decision.outcome == DecisionOutcome.APPROVED` → else `ActionNotApproved`
2. **Binding check** — `decision.proposal_id == proposal.proposal_id` → else `ActionDecisionMismatch`
3. **Action allowlist** — `proposal.action in _ALLOWED_ACTIONS` (frozenset, static) → else `ActionUnsupported`
4. **Staleness check** — decision age ≤ `max_decision_age_seconds` → else `ActionExpired`

A best-effort state-drift check follows guard 4.

### Read vs. Write Workflow

**Read (no approval required):**
```
GET /api/v1/equipment/status/{asset_id}
  → EquipmentStatusSkill → MCP read tool → PostgreSQL → JSON response
```

**Write (MEDIUM risk, requires human approval):**
```
POST /api/v1/equipment/assign
  → Agent: get_state → seal snapshot → build proposal
  → DecisionEngine: evaluate → REQUIRES_HUMAN_APPROVAL
  → Response: {executed: false, proposal_id: ..., decision_id: ...}
  # Human posts approval → executor runs guards → MCP write → outcome classified
```

**Write (LOW risk, auto-executes):**
```
POST /api/v1/equipment/release
  → Agent: get_state → seal snapshot → build proposal (risk=LOW)
  → DecisionEngine: APPROVED immediately
  → EquipmentActionExecutor: 4 guards pass → MCP write
  → Response: {outcome: "executed", execution_id: ...}
```

See [docs/architecture/RUNTIME_EXECUTION_FLOW.md](docs/architecture/RUNTIME_EXECUTION_FLOW.md)
for full sequence diagrams of all implemented paths.

---

### Reliable Execution (Phase 10E)

**MAIW separates authorization from reliable execution.** Once an action is authorized,
`ActionExecutor` assigns a stable execution identity and applies idempotency protection
before invoking the MCP write capability. Execution results use explicit operational
semantics rather than reducing provider behavior to a simple success/failure boolean.

**Execution lifecycle:**

```
OBSERVE
   ↓
REASON
   ↓
PROPOSE
   ↓
DECIDE
   ↓
APPROVE
   ↓
EXECUTE
   │
   ├── EXECUTED   — mutation confirmed
   ├── NO_OP      — desired state already existed
   ├── DEFERRED   — valid action, capacity unavailable now
   ├── CONFLICT   — warehouse state changed; action no longer valid
   ├── UNKNOWN    — mutation may have occurred; response was lost
   └── FAILED     — mutation did not occur
   ↓
OBSERVE OUTCOME
```

**Outcome semantics:**

| Outcome | Meaning |
|---------|---------|
| `EXECUTED` | MAIW has sufficient evidence that the intended mutation occurred |
| `NO_OP` | Desired state already existed; no new mutation was required |
| `DEFERRED` | Valid action, but required operational capacity or conditions are not currently available |
| `CONFLICT` | Current warehouse state makes the approved action invalid |
| `UNKNOWN` | Mutation may have occurred, but MAIW cannot confirm the outcome |
| `FAILED` | MAIW has sufficient evidence that the mutation did not occur |

**A particularly important case is `UNKNOWN`:** if the provider may have changed warehouse
state but MAIW loses the acknowledgement before receiving confirmation, the system does not
incorrectly classify the operation as `FAILED` or blindly retry it. The execution is marked
`UNKNOWN`, automatic retry is suppressed, and reconciliation is required before another
consequential write can safely occur.

```
ActionExecutor
      ↓
MCP write
      ↓
Provider mutation occurs
      ↓
Response lost (network timeout, etc.)
      ↓
UNKNOWN                          ← NOT FAILED
      ↓
Automatic retry suppressed
      ↓
Reconciliation required
```

Without this distinction, the unsafe path is:
```
mutation → timeout → FAILED → blind retry → duplicate mutation
```

**Execution identity:** MAIW distinguishes six identity concepts across the write path:

| Identifier | Meaning |
|------------|---------|
| `trace_id` | Full request lifecycle correlation — spans the entire OBSERVE→OUTCOME cycle |
| `proposal_id` | Identity of the proposed warehouse change (stable from `evaluate()` through `authorize_with_approval()`) |
| `decision_id` | Identity of the authority evaluation |
| `approval_id` | Identity of the approval record — scopes exactly one human authorization event |
| `execution_id` | Identity of one MAIW logical execution attempt (generated before write, stable through MCP) |
| `idempotency_key` | Identity of the intended logical mutation (caller-supplied; deduplication key) |
| `provider_reference` | Backend-specific reference (allocation_id, transaction_id, etc.) |

These identifiers are not interchangeable. `execution_id` and `idempotency_key` together
protect against duplicate physical mutations. `trace_id` correlates the full lifecycle.
`provider_reference` is the backend's own record of the transaction. `approval_id` scopes
the authority grant — it is created at queue time, consumed after execution, and is never reused.

> **Current limitation (Phase 10E Batch 1):** Idempotency protection is provided by an
> in-memory `ExecutionRegistry` within a single process. It does not yet provide distributed
> or multi-replica exactly-once execution guarantees. This limitation is explicit and must
> not be treated as a production distributed guarantee.

**Execution Safety — Phase 10E Batch 1:**

```
✓ Explicit six-value execution outcome (EXECUTED / NO_OP / DEFERRED / CONFLICT / UNKNOWN / FAILED)
✓ Stable execution_id generated before write and propagated through MCP
✓ Idempotency protection by execution_id and capability:idempotency_key
✓ Duplicate mutation prevention (NO_OP with replayed metadata on duplicate)
✓ Ambiguous writes represented as UNKNOWN — never misclassified as FAILED
✓ Automatic retry suppressed after UNKNOWN
✗ Distributed/multi-replica exactly-once: not yet implemented
```

#### Approval Governance (Phase 10E Batch 2)

**Approval is an explicit, expirable, single-use authority grant** — not a boolean flag on a
record. Before execution, a proposal must pass through an `ApprovalRecord` state machine that
tracks the full authorization lifecycle and enforces its limits.

**Approval lifecycle:**

```
PENDING   ← created when REQUIRES_HUMAN_APPROVAL is returned by DecisionEngine
    │
    ├── APPROVED  ← human confirms via POST /demo/approve
    │       │
    │       └── CONSUMED  ← single use exhausted after ActionExecutor completes
    │
    ├── REJECTED  ← human declines via POST /demo/reject  (terminal)
    └── EXPIRED   ← TTL elapsed before decision or execution  (terminal)
```

**Binding:** Every `ApprovalRecord` is bound to a specific `proposal_id`, `decision_id`, and
`warehouse_id`. `authorize_with_approval()` enforces all three before granting execution authority:

1. `CONSUMED` check — CONSUMED approval is blocked immediately (before any binding check);
   replay behavior is deterministic and observable
2. `proposal_id` binding — approval must reference the exact proposal under review
3. `decision_id` binding — approval must reference the original decision that required human review
4. `warehouse_id` binding — approval is scoped to the warehouse it was issued for; an approval
   issued for DC-47 cannot authorize an action at DC-99 (confused-deputy prevention)
5. Expiry — approval authority has a finite validity window
6. State — only `APPROVED` grants execution authority; `CONSUMED`, `REJECTED`, `PENDING`, and
   `EXPIRED` all block execution

**Note on `approval.approved`:** The `approved` computed field returns `True` only when
`state == APPROVED`. `CONSUMED` returns `False` because the authority has already been
exercised. This field means "currently executable authority", not "was historically approved".
To determine whether a proposal was ever approved, inspect `state` directly.

**Expiration policy:** The default approval TTL is 300 seconds. This is a configurable policy
parameter (`InMemoryApprovalStore(default_ttl_seconds=N)`), not an architectural constant.
Different capability classes may warrant different validity windows; the store accepts a
per-create `ttl_seconds` override. Infinite authority (`expires_at=None`) is not permitted
by the store.

**Proposal identity preservation:** The `proposal_id` assigned during the PROPOSE phase is
preserved unchanged through `evaluate()`, `add_pending_approval()`, and
`authorize_with_approval()`. The approval endpoint restores the original `ActionProposal`
from a serialized snapshot in the pending record rather than rebuilding it at approval time.
This ensures `approval_id → proposal_id → decision_id` is a consistent audit chain.

> **Current limitation (Phase 10E Batch 2):** Approval state is held in
> `InMemoryApprovalStore` within a single process. PENDING → APPROVED → CONSUMED transitions
> are atomic under asyncio cooperative multitasking but are **not distributed**. After a
> process restart, all pending approvals are lost. Multi-replica approval state, durable
> approval storage, and distributed exactly-once authority are out of scope for Phase 10E.

**Authority Safety — Phase 10E Batch 2:**

```
✓ Explicit ApprovalState machine: PENDING / APPROVED / REJECTED / EXPIRED / CONSUMED
✓ Single-use consume guarantee — second consume() returns None without raising
✓ CONSUMED approval blocked before proposal binding check (deterministic replay detection)
✓ proposal_id stable from evaluate() through authorize_with_approval()
✓ warehouse_id binding prevents confused-deputy authorization reuse
✓ decision_id binding enforced when expected_decision_id supplied
✓ Finite approval TTL — 300s default; infinite authority not permitted by store
✓ Expiration enforced both dynamically (is_expired()) and via explicit EXPIRED state
✓ authority_type field: HUMAN / POLICY / SYSTEM for classification
✗ Distributed approval state: not yet implemented (single-process only)
✗ Durable approval storage: not yet implemented (in-memory only)
```

#### Reconciliation (Phase 10E Batch 3)

When an MCP write times out after the provider has mutated state, MAIW records
`ExecutionOutcome.UNKNOWN` and refuses to retry. Batch 3 adds the reconciliation
path that resolves the uncertainty by reading authoritative state through the
same canonical MCP read skills used during normal state assembly.

```
WRITE ATTEMPT
    ↓
ExecutionOutcome = UNKNOWN  ← original write history, never rewritten
    ↓
ReconciliationService.reconcile()  ← reads through MCP read skills only
    ↓
CONFIRMED_EXECUTED     → "effectively_executed"   (mutation is confirmed)
CONFIRMED_NOT_EXECUTED → "effectively_not_executed" (safe for re-evaluation)
INDETERMINATE          → "unknown"                (manual operator review)
```

**Key design decisions:**

- `ExecutionOutcome.UNKNOWN` is **never rewritten** — reconciliation is a separate
  `ReconciliationRecord` stored alongside the original record in `ExecutionRegistry`
- `effective_status` is a derived property, not a stored field; it is a read-only
  interpretation of `(outcome, reconciliation.outcome)` pairs and carries no
  authority of its own
- `CONFIRMED_NOT_EXECUTED` does **not** trigger automatic retry — higher-level
  re-evaluation is required; the original proposal, decision, and approval are gone
- Reconciliation reads exclusively through canonical MCP read skills
  (`LaborAllocationSkill`, `EquipmentStatusSkill`, `WaveGetSkill`). Provider
  internals, simulation state, and `DemoWarehouseWorld` are never accessed
- `ExecutionIntent` snapshot is captured **before** the write at `registry.begin()`
  time, so reconciliation never depends on mutable post-write state
- `ReconciliationStrategy` is a Protocol — the same `ReconciliationService` works
  against any provider (simulation, SAP EWM, Manhattan, etc.) by swapping the
  strategy at the demo router layer, keeping `maiw-execution` free of
  `maiw-skills` dependency

**Postcondition comparison** (capability-specific `expected_effect` in `ExecutionIntent`):

| Domain | Target | Expected effect checked |
|--------|--------|------------------------|
| `warehouse.labor.allocate` | task_id | `status == "in_progress"` for the specific task |
| `warehouse.equipment.assign` | asset_id | `status == "assigned"` + `owner_user == assignee` |
| `warehouse.equipment.release` | asset_id | `status == "available"` |
| `warehouse.equipment.schedule_maintenance` | asset_id | `status == "maintenance"` |
| `warehouse.wave.reprioritize` | wave_id / zone | task priority matches `new_priority` in relevant zone |

**Command Center UI** — reconciliation events appear in the Live Activity feed under
the `RECONCILE` category (amber) with operator-facing labels:

| SSE event message | UI label |
|---|---|
| `reconciliation.started` | `CHECKING AUTHORITATIVE STATE` |
| `reconciliation.confirmed_executed` | `MUTATION CONFIRMED` |
| `reconciliation.confirmed_not_executed` | `NO MUTATION CONFIRMED` |
| `reconciliation.indeterminate` | `MANUAL REVIEW REQUIRED` |

**Reconciliation Safety:**

```
✓ ExecutionOutcome.UNKNOWN preserved — original write history is immutable
✓ ExecutionIntent snapshot captured before write — postcondition always verifiable
✓ Read path: MCP read skills only — never DemoWarehouseWorld or provider internals
✓ No automatic retry — CONFIRMED_NOT_EXECUTED is safe for higher-level re-evaluation
✓ No new proposal/decision/approval created during reconciliation
✓ INDETERMINATE is the safe default when read or postcondition check fails
✓ POST /demo/reconcile endpoint wired; publishes RECONCILE SSE event
✗ Automated reconciliation trigger: not yet implemented (operator-initiated only)
✗ Distributed reconciliation state: single-process only (same as registry)
```

#### Request Deadline Hierarchy (Phase 10E Batch 4)

Every request that enters the MAIW pipeline now carries an explicit, bounded time
budget. Deadlines are monotonic-clock values set once at the API boundary and never
extended — child operations can only reduce them.

```
/demo/analyze  ──── analyze_deadline  (MAIW_ANALYZE_TIMEOUT_SECONDS, default 60s)
    │
    ├── state_provider.get_state()          ← analyze_deadline propagated
    │       ├── EquipmentStatusSkill MCP
    │       ├── LaborCapacitySkill MCP
    │       └── WaveGetSkill MCP
    │
    ├── operations_agent.analyze_disruption()  ← analyze_deadline propagated
    │       └── ModelGateway.generate()
    │               └── NIMClient.generate_response()  ← effective_timeout = min(local, remaining)
    │
    └── executor.execute()  ── execution_deadline  (MAIW_EXECUTION_TIMEOUT_SECONDS, default 30s)
            └── MCP write call

/demo/reconcile  ─── reconciliation_deadline  (MAIW_RECONCILIATION_TIMEOUT_SECONDS, default 30s)
    └── ReconciliationService.reconcile()
            └── strategy.read_current_state()

API startup  ─── asyncio.wait_for(MAIW_STARTUP_TIMEOUT_SECONDS, default 30s)
```

The execution deadline is **independent** of the analyze deadline — a long analysis
phase does not eat into the budget available for the resulting write.

**Typed failure → HTTP mapping:**

| Exception | HTTP | UI label |
|-----------|------|----------|
| `RequestDeadlineExceeded` | `504` | `REQUEST DEADLINE` |
| `ModelTimeout` | `504` | `MODEL TIMEOUT` |
| `MCPTimeout` | `504` | `CAPABILITY TIMEOUT` |
| `ModelUnavailable` | `503` | `MODEL UNAVAILABLE` |
| `MCPUnavailable` | `503` | `MCP UNAVAILABLE` |

`ExecutionOutcome.UNKNOWN` is **never converted to a 504** — it is always returned
as a structured body (`status: "unknown"`) for operator reconciliation.

**Batch 4 Safety:**

```
✓ Deadline originates at /demo/analyze ingress — not inside the agent or executor
✓ analyze_deadline propagated through state_provider → agent → ModelGateway → NIM
✓ Execution deadline is a fresh budget, independent of the analyze budget
✓ Reconciliation deadline is a fresh budget, independent of both
✓ Startup bounded — hung NIM/DB cannot block startup indefinitely
✓ Lifespan cleanup fixed — NIM httpx clients closed; mcp_client.aclose() removed
  (MAIWMCPClient is per-call/context-managed and has no persistent connection)
✓ /live returns 200 regardless of NIM or MCP availability
✓ RequestDeadlineExceeded/ModelTimeout/MCPTimeout → 504; Unavailable → 503
✓ ExecutionOutcome.UNKNOWN preserved as structured body — never 500/504
✗ Distributed deadline propagation across replicas: out of scope for 10E
✗ Per-capability deadline budgets: deferred to production-scoped work
```

---

## MCP v2 Capability Plane

MAIW uses the official MCP Python SDK (`mcp>=2.0.0,<3`, protocol version `2026-07-28`). Each
warehouse domain runs as an independently deployable MCP server.

### Architecture

```
ActionExecutor
    │
    └── MAIWMCPClient.invoke("warehouse.equipment.assign", params)
              │
              └── EquipmentMCPServer  (mcp_servers/equipment/server.py)
                        │
                        ├── MAIWEquipmentAdapter  (adapters/)
                        │
                        └── EquipmentAssetTools  → PostgreSQL
```

- Servers are **stateless HTTP** in production (`streamable-http` transport)
- Each server exposes exactly the tools in its domain contract
- MCP write tools are **not exposed to the LLM** — only the executor layer calls them
- Read tools are called by skills during state assembly

See [docs/architecture/MCP_V2_ARCHITECTURE.md](docs/architecture/MCP_V2_ARCHITECTURE.md).

---

## Implemented Warehouse Domains

MAIW implements 12 capabilities across 4 domains (7 read, 5 write):

| Domain | Capability | Name | Type |
|--------|-----------|------|------|
| **Inventory** | Get item metadata | `warehouse.inventory.get_metadata` | read |
| **Inventory** | Get stock levels | `warehouse.inventory.get_stock_levels` | read |
| **Equipment** | Get equipment status | `warehouse.equipment.get_status` | read |
| **Equipment** | Assign equipment | `warehouse.equipment.assign` | write |
| **Equipment** | Release equipment | `warehouse.equipment.release` | write |
| **Equipment** | Schedule maintenance | `warehouse.equipment.schedule_maintenance` | write |
| **Labor** | Get labor capacity | `warehouse.labor.get_capacity` | read |
| **Labor** | Get labor allocation | `warehouse.labor.get_allocation` | read |
| **Labor** | Allocate labor | `warehouse.labor.allocate` | write |
| **Wave** | Get wave status | `warehouse.wave.get` | read |
| **Wave** | Get wave risk | `warehouse.wave.get_risk` | read |
| **Wave** | Reprioritize wave | `warehouse.wave.reprioritize` | write |

See [docs/architecture/CAPABILITY_MATRIX.md](docs/architecture/CAPABILITY_MATRIX.md).

---

## Repository Structure

```
Multi-Agent-Intelligent-Warehouse/
│
├── packages/                      # Canonical Python packages (uv workspace)
│   ├── maiw-models/               # ModelGateway, NIMProvider, NIMClient, enums
│   ├── maiw-mcp/                  # Capability contracts, ActionProposal, MCP client
│   ├── maiw-state/                # WarehouseState, StateSnapshot, StateFreshness
│   ├── maiw-skills/               # Domain skills (read + write proposal factories)
│   ├── maiw-decision/             # DecisionEngine, DecisionResult, constraints
│   ├── maiw-execution/            # BaseActionExecutor, domain executors, error types
│   └── maiw-agents/               # EquipmentAssetOperationsAgent, OperationsCoordinationAgent,
│                                  #   SafetyComplianceAgent
│
├── mcp_servers/                   # Independently deployable MCP v2 servers
│   ├── inventory/                 # Inventory capability server
│   ├── equipment/                 # Equipment capability server
│   ├── labor/                     # Labor capability server
│   └── wave/                      # Wave capability server
│
├── src/api/                       # Legacy FastAPI layer (routers being migrated to apps/api)
│   ├── app.py                     # Legacy entrypoint (superseded by maiw_api.app)
│   ├── routers/                   # HTTP route handlers (canonical ones moved to apps/api)
│   ├── agents/                    # Legacy agent layer (superseded by packages/maiw-agents)
│   └── services/                  # Services: auth, DB, monitoring, legacy shims
│
├── apps/api/maiw_api/             # Canonical FastAPI entrypoint (Phase 9B)
│   ├── app.py                     # ASGI entrypoint: uvicorn maiw_api.app:app
│   ├── bootstrap.py               # MAIWRuntime composition root
│   ├── config.py                  # Application settings
│   ├── dependencies.py            # FastAPI dependency helpers
│   ├── lifespan.py                # Startup / shutdown
│   └── routers/                   # Canonical routers (health, equipment, operations, safety, mcp)
│
├── connectors/                    # Data source adapters
│   └── generic/                   # Generic WMS connector (implemented)
│
├── integrations/                  # Non-core optional subsystems
│   ├── forecasting/               # Demand forecasting (partially implemented)
│   └── document/                  # Document processing / OCR (partially implemented)
│
├── tests/
│   ├── unit/                      # Pure Python, no infrastructure (CORE CI)
│   ├── contract/                  # MCP capability contract tests (CORE CI)
│   ├── mcp/                       # MCP protocol tests, in-memory server (CORE CI)
│   └── integration/               # Requires running MAIW server + PostgreSQL
│
├── docs/architecture/             # Architecture decision records and guides
└── deploy/compose/                # Docker Compose deployment stack
```

### Package Responsibilities

| Package | Canonical import | Owns |
|---------|----------------|------|
| `maiw-models` | `from maiw_models import ModelGateway` | LLM gateway, routing, NIM provider, telemetry |
| `maiw-mcp` | `from maiw_mcp.contracts.equipment import ...` | Capability contracts, ActionProposal, MCP client |
| `maiw-state` | `from maiw_state import WarehouseState` | State assembly, snapshots, freshness, provenance |
| `maiw-skills` | `from maiw_skills.equipment import EquipmentAssignmentSkill` | Read skills, write proposal factories |
| `maiw-decision` | `from maiw_decision import DecisionEngine` | Constraint evaluation, DecisionResult |
| `maiw-execution` | `from maiw_execution import EquipmentActionExecutor, ExecutionOutcome` | 4-guard executor, `ExecutionOutcome` enum, `ExecutionRegistry` (single-process idempotency), `AmbiguousWriteError` |
| `maiw-agents` | `from maiw_agents.equipment import EquipmentAssetOperationsAgent` | Agent orchestration, state assembly coordination |

---

## MCP Servers

Each MCP server is independently deployable and stateless.

```
mcp_servers/<domain>/
├── server.py      # FastMCP app, tool registration
├── provider.py    # Domain data provider (queries PostgreSQL)
└── adapters/      # Data adapters and transformation
```

### Starting MCP Servers

**Development (stdio transport):**

```bash
python -m mcp_servers.inventory.server
python -m mcp_servers.equipment.server
python -m mcp_servers.labor.server
python -m mcp_servers.wave.server
```

**Production (stateless HTTP):**

```bash
MAIW_MCP_TRANSPORT=streamable-http MAIW_MCP_EQUIPMENT_PORT=8766 \
    python -m mcp_servers.equipment.server

MAIW_MCP_TRANSPORT=streamable-http MAIW_MCP_LABOR_PORT=8767 \
    python -m mcp_servers.labor.server

MAIW_MCP_TRANSPORT=streamable-http MAIW_MCP_WAVE_PORT=8768 \
    python -m mcp_servers.wave.server
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 14+ (or Docker)
- NVIDIA API key — get one at [build.nvidia.com](https://build.nvidia.com/)
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Install

```bash
git clone https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse.git
cd Multi-Agent-Intelligent-Warehouse

# Install all workspace packages in editable mode
pip install -r requirements.txt
pip install -e packages/maiw-models
pip install -e packages/maiw-mcp
pip install -e packages/maiw-state
pip install -e packages/maiw-skills
pip install -e packages/maiw-decision
pip install -e packages/maiw-execution
pip install -e packages/maiw-agents
```

Or with uv (workspace-aware):

```bash
uv sync
```

### Docker (full stack)

```bash
cp .env.example deploy/compose/.env
# Edit deploy/compose/.env — set NVIDIA_API_KEY and POSTGRES_PASSWORD at minimum
docker compose -f deploy/compose/docker-compose.yml up
```

The stack brings up: TimescaleDB, Redis, Kafka, etcd, MinIO, Milvus, nginx, and the MAIW API.
A NIM inference server (`nvidia/nemotron-3-super-120b-a12b`) is started when a GPU profile is
active.

---

## Configuration

Copy `.env.example` to `.env` and set the required variables:

```bash
cp .env.example .env
```

### Required

| Variable | Description |
|----------|-------------|
| `NVIDIA_API_KEY` | NVIDIA API key (`nvapi-...`), from [build.nvidia.com](https://build.nvidia.com/) |
| `POSTGRES_PASSWORD` | PostgreSQL password |
| `JWT_SECRET_KEY` | JWT signing secret (min 32 chars) |

### Model Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_NIM_URL` | `https://integrate.api.nvidia.com/v1` | NIM inference endpoint |
| `LLM_MODEL` | `nvidia/nemotron-3-super-120b-a12b` | Default model ID |
| `MAIW_MODEL_LIGHTNING` | `nvidia/nemotron-3.5-lightning-30b-a3b` | Lightning role override |
| `MAIW_MODEL_NANO` | `nvidia/nemotron-3-nano-30b-a3b` | Nano role override |
| `MAIW_MODEL_SUPER` | `nvidia/nemotron-3-super-120b-a12b` | Super role override |
| `MAIW_MODEL_ULTRA` | `nvidia/nemotron-3-ultra-550b-a55b` | Ultra role override (slow, opt-in) |

### Infrastructure

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `5435` | PostgreSQL port |
| `REDIS_HOST` | `localhost` | Redis host |
| `MILVUS_HOST` | `localhost` | Milvus vector DB host |

---
```
.
├─ packages/               # Canonical Python packages (import from these, not src.*)
│  ├─ maiw-mcp/            # MCP contracts, capability registry, action proposals
│  ├─ maiw-state/          # WarehouseState, domain state models (Equipment/Labor/Wave)
│  ├─ maiw-decision/       # DecisionEngine — APPROVED/REJECTED/DEFERRED outcomes
│  ├─ maiw-models/         # ModelGateway, NIM provider, ModelRequest/ReasoningLevel
│  ├─ maiw-skills/         # Inventory, Equipment, Labor, Wave skill implementations
│  ├─ maiw-execution/      # BaseActionExecutor (4-guard pattern), domain executors
│  └─ maiw-agents/         # Equipment, Operations, Safety reasoning agents
├─ apps/api/               # FastAPI application composition root (bootstrap.py)
├─ mcp_servers/            # Standalone MCP 2.0 servers (Inventory, Equipment, Labor, Wave)
├─ src/                    # Legacy source code (being migrated to packages/ above)
│  ├─ api/                 # FastAPI application (routers, agents, services)
│  ├─ retrieval/           # Retrieval services
│  ├─ memory/              # Memory services
│  ├─ adapters/            # External system adapters
│  └─ ui/                  # React web dashboard
├─ data/                   # SQL DDL/migrations, sample data
├─ deploy/                 # Deployment configurations
│  ├─ compose/             # Docker Compose files
│  ├─ helm/                # Helm charts
│  └─ scripts/             # Deployment scripts
├─ scripts/                # Utility scripts
│  ├─ setup/               # Setup scripts
│  ├─ forecasting/         # Forecasting scripts
│  └─ data/                # Data generation scripts
├─ tests/                  # Test suite
├─ docs/                   # Documentation
│  └─ architecture/        # Architecture documentation
└─ monitoring/             # Prometheus/Grafana configs
```

## Running MAIW

### API Server

```bash
uvicorn maiw_api.app:app --reload --port 8001
```

The API is available at `http://localhost:8001`. Key endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/health` | System health |
| `POST` | `/api/v1/chat` | Natural-language chat interface |
| `GET` | `/api/v1/equipment/status/{id}` | Equipment status (read) |
| `POST` | `/api/v1/equipment/assign` | Assign equipment (write, may require approval) |
| `POST` | `/api/v1/equipment/release` | Release equipment (write, auto-executes) |
| `POST` | `/api/v1/equipment/maintenance` | Schedule maintenance (write) |
| `GET` | `/api/v1/inventory/{sku}` | Inventory lookup (read) |
| `GET` | `/api/v1/labor/capacity` | Labor capacity (read) |
| `POST` | `/api/v1/labor/allocate` | Labor allocation (write) |
| `GET` | `/api/v1/wave/status` | Wave status (read) |
| `POST` | `/api/v1/wave/reprioritize` | Wave reprioritization (write) |

### React UI

```bash
cd src/ui/web
npm install
npm start
```

---

## Testing

MAIW uses a three-tier test structure. **CORE CI** requires no running services:

```bash
python -m pytest tests/unit/ tests/contract/ tests/mcp/ \
  --ignore=tests/unit/test_all_agents.py \
  --ignore=tests/unit/test_basic.py \
  --ignore=tests/unit/test_nvidia_llm.py \
  --ignore=tests/unit/test_caching_demo.py \
  --ignore=tests/unit/test_response_quality_demo.py \
  --ignore=tests/unit/test_mcp_integrated_planner_graph.py \
  --ignore=tests/unit/test_chunking_demo.py \
  --ignore=tests/unit/test_db_connection.py \
  --ignore=tests/unit/test_enhanced_retrieval.py \
  --ignore=tests/unit/test_evidence_scoring_demo.py \
  --ignore=tests/unit/test_mcp_system.py \
  --ignore=tests/unit/test_guardrails.py \
  --ignore=tests/unit/test_guardrails_sdk.py \
  --ignore=tests/unit/test_mcp_planner_integration.py \
  --ignore=tests/unit/test_nvidia_integration.py \
  --ignore=tests/unit/test_document_action_tools.py \
  --ignore=tests/unit/test_document_pipeline.py \
  --ignore=tests/unit/test_embedding.py \
  --ignore=tests/unit/test_reasoning_evaluation.py \
  --ignore=tests/unit/test_prompt_injection_protection.py \
  --ignore=tests/unit/test_prompt_injection_simple.py
```

**Baseline (Phase 9A): 528 passed, 1 skipped, 0 failed**
**Phase 10E Batch 1 adds 85 reliability tests in `tests/unit/reliability/`** (ambiguous write, capability semantics, execution outcome, idempotency, trace)

| Test tier | Command | Requires |
|-----------|---------|---------|
| CORE CI | Command above | Python packages only |
| Integration | `pytest tests/integration/` | Running MAIW server + PostgreSQL |
| External service | Set `NVIDIA_API_KEY`, remove `--ignore` flags | NVIDIA API key + NIM endpoint |

See [docs/architecture/TEST_STRATEGY.md](docs/architecture/TEST_STRATEGY.md) for per-file
exclusion rationale and historical baselines by phase.

---

## Deterministic Counterfactual Evaluation

### MAIW Evaluation Scenario 001 — Labor Constraint + Wave Risk

Two warehouse worlds were initialized from the same scenario definition (`labor_constraint_wave_risk`) and random seed, then advanced through the same disruption timeline. The control world received no MAIW intervention; the MAIW world executed governed actions through the standard pipeline:

```
State → Agent → ModelGateway (Nemotron 3 Super) → Proposal → Decision → Approval → ActionExecutor → MCP
```

Results within the 1,800-second (30 sim-minute) evaluation horizon:

| Metric | Control | MAIW |
|--------|---------|------|
| Time to recovery | not reached | 300s (5 sim-min) |
| Peak backlog | 5 tasks | 5 tasks (pre-action) → 0 |
| Backlog exposure (AUC) | 9,000 task·sec | 720 task·sec |
| Wave-risk exposure (AUC) | reduction baseline | **−86.7%** |
| Backlog AUC reduction | — | **−92%** |
| MAIW cycles | 0 | 6 |

The control run did not reach the configured recovery threshold (`wave_risk_max_score ≤ 25`, `backlog ≤ 1`) within the 30-minute horizon. The MAIW run recovered after 300 simulated seconds.

> **Caveat:** These results are generated in MAIW's deterministic synthetic warehouse environment and demonstrate comparative behavior under the modeled scenario; they are not measurements from a production warehouse.

Evaluation artifacts (machine-readable, first-class evaluation evidence):

```
artifacts/demo/
├── labor_constraint_wave_risk_trace.json   # full MAIW pipeline trace
├── labor_constraint_wave_risk_trace.md     # human-readable trace
├── labor_wave_control_vs_maiw.json         # counterfactual comparison data
└── labor_wave_control_vs_maiw.md           # counterfactual comparison report
```

Reproduce with:

```bash
MAIW_DEMO_MODE=true env/bin/python -m uvicorn maiw_api.app:app --port 8001
env/bin/python scripts/counterfactual_eval.py   # generates artifacts/demo/labor_wave_control_vs_maiw.*
env/bin/python scripts/trace_capture.py          # generates artifacts/demo/labor_constraint_wave_risk_trace.*
```

---

## Architecture Invariants

These invariants are enforced by the test suite and must not be broken:

| Invariant | Enforcement |
|-----------|------------|
| LLM cannot call MCP write tools directly | No MCP write tool in any agent tool registry |
| Proposals are built locally, never via MCP | `ActionProposal` factories have no MCP client |
| DecisionEngine is synchronous, no I/O | `evaluate()` has no `await`, no client dependencies |
| Only `ActionExecutor.execute()` reaches MCP writes | Single call-site per domain executor |
| Action names are statically allowlisted | `_ALLOWED_ACTIONS` is a `frozenset` literal |
| No canonical package imports from `src.*` | AST scanner in `test_package_imports.py` |
| No canonical package imports heavy infra deps | AST scanner: `asyncpg`, `pymilvus`, `redis`, `fastapi` forbidden |
| `maiw-execution` does not import `maiw-agents` | Cycle prevention enforced in test suite |
| `UNKNOWN` outcome is never auto-retried | `ExecutionRegistry.mark_unknown()` blocks subsequent attempts |
| Post-mutation timeout produces `UNKNOWN`, not `FAILED` | `AmbiguousWriteError` → distinct outcome path in `BaseActionExecutor` |
| Same idempotency key cannot produce multiple physical mutations | `ExecutionRegistry` capability:key compound dedup |
| `execution_id` is generated before the write and propagated through MCP | `BaseActionExecutor.execute()` generates UUID pre-write; forwarded in all write-request contracts |

---

## Modernization Status

MAIW is in active modernization from a legacy LangGraph/monolith architecture to a typed,
package-based, MCP v2 system.

| Area | Status | Notes |
|------|--------|-------|
| **ModelGateway** (`maiw-models`) | ✅ Done | Nemotron 3 roles, routing policy, NIM provider, telemetry |
| **WarehouseState** (`maiw-state`) | ✅ Done | Snapshot sealing, freshness, provenance, all 4 domains |
| **Skills** (`maiw-skills`) | ✅ Done | Read skills, write proposal factories, all 4 domains |
| **DecisionEngine** (`maiw-decision`) | ✅ Done | All constraint rules, APPROVED/REJECTED/DEFERRED |
| **Executors** (`maiw-execution`) | ✅ Done | 4-guard BaseActionExecutor, Equipment + Labor + Wave |
| **Reliable Execution** (Phase 10E Batch 1) | ✅ Done | `ExecutionOutcome` enum, `ExecutionRegistry` (single-process), `AmbiguousWriteError`, `execution_id` propagation, idempotent replay metadata |
| **Approval Governance** (Phase 10E Batch 2) | ✅ Done | `ApprovalState` machine (PENDING/APPROVED/REJECTED/EXPIRED/CONSUMED), `InMemoryApprovalStore`, single-use consume, proposal/decision/warehouse binding, 300s default TTL, audit chain preserved |
| **Reconciliation** (Phase 10E Batch 3) | ✅ Done | `ExecutionIntent` snapshot, `ReconciliationOutcome` (CONFIRMED_EXECUTED/CONFIRMED_NOT_EXECUTED/INDETERMINATE), `ReconciliationService`, `effective_status` derived property, UNKNOWN history preserved, capability-specific postcondition strategies |
| **Request Deadlines** (Phase 10E Batch 4) | ✅ Done | `RequestDeadline` hierarchy at API boundary; analyze/execution/reconciliation/startup budgets; typed failure→HTTP map; lifespan cleanup; UNKNOWN preserved as structured outcome |
| **Agents** (`maiw-agents`) | ✅ Done | Equipment, Operations, Safety agents in canonical packages |
| **MCP v2 servers** | ✅ Done | Inventory, Equipment, Labor, Wave — stateless HTTP |
| **Capability contracts** | ✅ Done | All 12 capabilities defined, contract-tested |
| **Compatibility shims** | ⚠️ Remove in Phase 10 | `src/api/services/model_gateway/__init__.py`, `src/api/skills/*.py` |
| **Forecasting integration** | 🔄 Partial | `integrations/forecasting/` — multi-model ensemble, not wired to agents |
| **Document processing** | 🔄 Partial | `integrations/document/` — OCR + extraction, not wired to agents |
| **Simulation** | 🔲 Future | `integrations/simulation/` — placeholder only |
| **Optimization** | 🔲 Future | `integrations/optimization/` — placeholder only |
| **Training / flywheel** | 🔲 Future | `integrations/training/` — placeholder only |
| **SAP EWM connector** | 🔲 Future | `connectors/` — generic connector implemented; SAP planned |
| **Manhattan / Blue Yonder** | 🔲 Future | Planned WMS connectors |
| **apps/api as entrypoint** | ✅ Phase 9B | `maiw_api.app:app` is the canonical entrypoint; `MAIWRuntime` is the composition root |

---

## Documentation

| Document | Description |
|----------|------------|
| [MODEL_GATEWAY.md](docs/architecture/MODEL_GATEWAY.md) | Nemotron roles, routing policy, telemetry |
| [WAREHOUSE_STATE.md](docs/architecture/WAREHOUSE_STATE.md) | State assembly, freshness, provenance |
| [CAPABILITY_MATRIX.md](docs/architecture/CAPABILITY_MATRIX.md) | All 12 capabilities, read/write classification |
| [DECISION_ENGINE.md](docs/architecture/DECISION_ENGINE.md) | Constraint rules, outcome model |
| [RUNTIME_EXECUTION_FLOW.md](docs/architecture/RUNTIME_EXECUTION_FLOW.md) | Full pipeline sequence diagrams |
| [MCP_V2_ARCHITECTURE.md](docs/architecture/MCP_V2_ARCHITECTURE.md) | MCP SDK, protocol version, deployment |
| [DEPENDENCY_BOUNDARIES.md](docs/architecture/DEPENDENCY_BOUNDARIES.md) | Package boundary rules |
| [PACKAGE_OWNERSHIP.md](docs/architecture/PACKAGE_OWNERSHIP.md) | Module-to-package ownership map |
| [TEST_STRATEGY.md](docs/architecture/TEST_STRATEGY.md) | CORE CI command, exclusion rationale, baselines |

---

## Contributing

1. Fork the repository and create a feature branch.
2. All changes must keep CORE CI green: current baseline 971 passed (Phase 9A 528 + 214 Phase 10E Batches 1–3 + 18 Batch 4D + remainder of CORE suite); zero new failures.
3. New canonical code goes in `packages/`, never in `src.*` for business logic.
4. No `src.*` imports in any `packages/` code — enforced by the test suite.
5. Commit messages must follow [Conventional Commits](https://www.conventionalcommits.org/).

---

## License

Apache License 2.0. See [LICENSE](LICENSE) for full text.

Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
