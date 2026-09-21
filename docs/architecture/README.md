# MAIW Architecture — Current State

This directory contains the authoritative current-state documentation for MAIW v2.
Every document here describes the system as it is today. Historical and migration
material lives in [`docs/history/`](../history/).

---

## Reading Order

**Start here** if you're new to MAIW:

1. **[ARCHITECTURE.md](ARCHITECTURE.md)** — Full reference: five-layer pipeline, authority boundary, package dependency flow
2. **[MCP.md](MCP.md)** — Official MCP SDK, Streamable HTTP, 13 capabilities, write-path authority chain
3. **[GOVERNANCE.md](GOVERNANCE.md)** — DecisionEngine, approval lifecycle, ActionExecutor 6-guard pattern
4. **[RUNTIME_EXECUTION_FLOW.md](RUNTIME_EXECUTION_FLOW.md)** — Read path + write path sequence diagrams, outcome reconciliation

**Domain reference:**

5. **[CAPABILITY_MATRIX.md](CAPABILITY_MATRIX.md)** — All 13 capabilities with risk tiers, side-effects, executors
6. **[PACKAGE_OWNERSHIP.md](PACKAGE_OWNERSHIP.md)** — Package → module ownership, MCP server map
7. **[DEPENDENCY_BOUNDARIES.md](DEPENDENCY_BOUNDARIES.md)** — Package boundary enforcement, MCP SDK version constraint

**Runtime components:**

8. **[AGENT_RUNTIME.md](AGENT_RUNTIME.md)** — Three-layer ownership, MAIWDeterministicRuntime vs DeepAgentsRuntime
9. **[MODEL_GATEWAY.md](MODEL_GATEWAY.md)** — PolicyFilter, ModelRouter, Deployment Resolver, Nemotron roles
10. **[DECISION_ENGINE.md](DECISION_ENGINE.md)** — Constraint rules, APPROVED/REJECTED/DEFERRED, audit records
11. **[WAREHOUSE_STATE.md](WAREHOUSE_STATE.md)** — WarehouseState assembly, StateRequirements, freshness, provenance
12. **[WAREHOUSE_WORLD.md](WAREHOUSE_WORLD.md)** — BASE/SCENARIO/LIVE worlds, OperationalContextSnapshot
13. **[DEPLOYMENT_ARCHITECTURE.md](DEPLOYMENT_ARCHITECTURE.md)** — Service boundaries, ports, env vars

**Testing:**

14. **[TEST_STRATEGY.md](TEST_STRATEGY.md)** — CORE CI command, test categories, exclusion rationale

---

## Documents in This Directory

| Document | Status | Scope |
|---|---|---|
| `ARCHITECTURE.md` | Authoritative | Full system reference |
| `MCP.md` | Authoritative | MCP layer |
| `GOVERNANCE.md` | Authoritative | Authority boundary + approval |
| `RUNTIME_EXECUTION_FLOW.md` | Authoritative | Pipeline sequence diagrams |
| `CAPABILITY_MATRIX.md` | Authoritative | 13 MCP capabilities |
| `PACKAGE_OWNERSHIP.md` | Authoritative | Module → package map |
| `DEPENDENCY_BOUNDARIES.md` | Authoritative | SDK version constraints |
| `AGENT_RUNTIME.md` | Authoritative | AgentRuntime interface |
| `MODEL_GATEWAY.md` | Authoritative | ModelGateway + routing |
| `DECISION_ENGINE.md` | Authoritative | DecisionEngine rules |
| `WAREHOUSE_STATE.md` | Authoritative | State assembly |
| `WAREHOUSE_WORLD.md` | Authoritative | Synthetic world layer |
| `DEPLOYMENT_ARCHITECTURE.md` | Authoritative | Deployment topology |
| `TEST_STRATEGY.md` | Authoritative | CI test strategy |
| `adr/` | Decision records | Accepted architectural decisions |
| `diagrams/` | Assets | Architecture diagrams |

---

> Historical documents (migration plans, phase specs, pre-v2 architecture) →
> [`docs/history/`](../history/)
