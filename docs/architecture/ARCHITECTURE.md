# MAIW Architecture — Full Reference

**Version:** MAIW v2
**Status:** AUTHORITATIVE
**Diagram:** [docs/architecture/diagrams/maiw-runtime-pipeline.png](diagrams/maiw-runtime-pipeline.png)

---

## Overview

MAIW is a governed operational intelligence architecture for warehouse AI. It connects
adaptive agent reasoning to safe, observable, traceable, and measurable warehouse action
through a strict authority boundary.

The canonical architecture diagram (`maiw-runtime-pipeline.png`) expresses the full system:

```
Operator / Human Authority
    ↓
MAIW Copilot (ASK / ANALYZE / ACT / OBSERVE_OUTCOME)
    ↓
MAIW Agent Runtime
  ├─ AgentDefinition     (identity, allowed capabilities, termination policy)
  ├─ SOPDefinition       (versioned procedure, step sequence, policy envelope)
  └─ AgentTaskState      (execution state for one SOP run)
    ↓
  ┌─────────────────────────────────────────────────┐
  │  MAIWDeterministicRuntime  |  DeepAgentsRuntime │
  └─────────────────────────────────────────────────┘
    ↓                              ↓
  Canonical Agents          ModelGateway
  (Operations / Labor /     (PolicyFilter → ModelRouter
   Wave / Equipment /        → Deployment Resolver
   Safety)                   → NVIDIA NIM)
    ↓
  RecommendedAction   ← ABOVE MAIW AUTHORITY BOUNDARY
─────────────────────────────────────────────────────────
  ActionProposal      ← BELOW MAIW AUTHORITY BOUNDARY
    ↓
  DecisionEngine
  (synchronous, deterministic, no I/O)
    → APPROVED / REJECTED / DEFERRED
    ↓
  Human Approval
  (explicit, expirable, single-use)
    ↓
  ActionExecutor
  (6-guard pattern)
    ↓
  MCP Interoperability Layer
  (mcp.client.Client → mcp.server.MCPServer)
    ↓
  Warehouse Systems (WMS / WES / Simulation)
    ↓
  Observability & Trace → LIVE World & Outcome
    ↓
  Closed-Loop Outcome Observation
```

---

## Core Principle

> **AI may be adaptive in how it reasons, but operational authority remains explicit,
> deterministic, and auditable.**

---

## Layer Ownership

| Layer | Owns |
|-------|------|
| **MAIW** | Warehouse semantics, SOPs, task state, permissions, governance, execution, outcome |
| **Deep Agents** | Adaptive runtime loop, tool/subagent scheduling, working context |
| **ModelGateway** | Model access, eligibility, routing, deployment |
| **MCP** | Standardized interoperability |
| **WMS / WES / etc.** | Operational systems of record |

---

## Core Lifecycle

```
Observe → Reason → Recommend → Govern → Approve → Execute → Observe Outcome
```

| Stage | Component | Description |
|-------|-----------|-------------|
| Observe | `WarehouseStateProvider` | Assembles `WarehouseState` from all domains via MCP read capabilities |
| Reason | `AgentRuntime` + `ModelGateway` | SOP-driven reasoning; model selected by `PolicyFilter` + `ModelRouter` |
| Recommend | Agent → `RecommendedAction` | Semantic intent — not MCP parameters, not write commands |
| Govern | `DecisionEngine` | Deterministic policy evaluation → `APPROVED / REJECTED / DEFERRED` |
| Approve | `ApprovalStore` | Human approval — explicit, expirable, single-use, proposal-bound |
| Execute | `ActionExecutor` | 6-guard write path → MCP write capability |
| Observe Outcome | Reconciliation + `OBSERVE_OUTCOME` | `CONFIRMED_EXECUTED / CONFIRMED_NOT_EXECUTED / INDETERMINATE` |

---

## Package Dependency Flow

Packages have strictly one-way dependencies. Nothing canonical imports from `src.*`.

```
maiw-contracts    (no dependencies)
maiw-mcp          (→ maiw-contracts)
maiw-models       (→ maiw-contracts)
maiw-state        (→ maiw-contracts, maiw-mcp)
maiw-skills       (→ maiw-state, maiw-mcp, maiw-models)
maiw-decision     (→ maiw-contracts, maiw-skills, maiw-state)
maiw-execution    (→ maiw-decision, maiw-skills, maiw-mcp)
maiw-world        (→ maiw-state)
maiw-agents       (→ maiw-execution, maiw-skills, maiw-state, maiw-models)
apps/api          (→ all canonical packages)
```

`maiw-execution` does not import `maiw-agents`. Cycle prevention is enforced by the test suite.

---

## Known Modernization Boundary

MAIW v2 uses the `packages/` layout as the target modular architecture, but portions of the live runtime still reside under `src/` and are actively imported by `apps/api/maiw_api/`. In particular, `apps/api/maiw_api/app.py` imports routers, middleware, and services directly from `src.api.*` (e.g., `src.api.routers`, `src.api.middleware.security_headers`, `src.api.services.monitoring`, `src.api.services.security`). Additionally, some ModelGateway-related runtime code has not yet been fully migrated from `src/api/services/model_gateway/` into `packages/maiw-models/` — both directories contain parallel implementations.

These paths are **not dead legacy code** and must not be removed without an explicit migration that preserves all ModelGateway invariants (single inference boundary, PolicyFilter, ModelRouter, Deployment Resolver, routing provenance).

The architectural source of truth remains the current MAIW v2 contracts, ownership boundaries, and runtime invariants documented in this directory. The remaining `src/` dependency is a known implementation migration boundary, not a bug or obsolete code. See [PACKAGE_OWNERSHIP.md](PACKAGE_OWNERSHIP.md) for current ownership boundaries.

---

## Key Invariants

| Invariant | Enforcement |
|-----------|------------|
| LLM cannot call MCP write tools directly | No write tool in any agent tool registry |
| Proposals are built locally, never via MCP | `ActionProposal` factories have no MCP client |
| `DecisionEngine` is synchronous, no I/O | `evaluate()` has no `await` |
| Only `ActionExecutor.execute()` reaches MCP writes | Single call-site per domain executor |
| `UNKNOWN` outcome is never auto-retried | `ExecutionRegistry.mark_unknown()` blocks retry |
| `execution_id` generated before write | `BaseActionExecutor` generates UUID pre-write |

---

## Sub-Architecture Documents

| Document | Scope |
|----------|-------|
| [AGENT_RUNTIME.md](AGENT_RUNTIME.md) | Deterministic vs. adaptive runtimes, SOP envelope, authority boundary |
| [GOVERNANCE.md](GOVERNANCE.md) | DecisionEngine, approval lifecycle, ActionExecutor guards |
| [MODEL_GATEWAY.md](MODEL_GATEWAY.md) | PolicyFilter, ModelRouter, Deployment Resolver, Nemotron roles |
| [MCP.md](MCP.md) | Official MCP SDK, Streamable HTTP, capability registry |
| [WAREHOUSE_WORLD.md](WAREHOUSE_WORLD.md) | BASE/SCENARIO/LIVE, OperationalContextSnapshot |
| [DECISION_ENGINE.md](DECISION_ENGINE.md) | Constraint rules, APPROVED/REJECTED/DEFERRED |
| [CAPABILITY_MATRIX.md](CAPABILITY_MATRIX.md) | All 13 capabilities, read/write classification |
| [RUNTIME_EXECUTION_FLOW.md](RUNTIME_EXECUTION_FLOW.md) | Full pipeline sequence diagrams |
| [DEPENDENCY_BOUNDARIES.md](DEPENDENCY_BOUNDARIES.md) | Package boundary enforcement |
| [TEST_STRATEGY.md](TEST_STRATEGY.md) | CORE CI structure, exclusion rationale |
