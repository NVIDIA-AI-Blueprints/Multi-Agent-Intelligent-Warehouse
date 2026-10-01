# MAIW Package Ownership

This document maps every canonical module to its owning package and dependency tier.
It describes the current-state architecture; migration status codes are not used.

---

## Canonical Packages (`packages/`)

| Package | Owns | Depends on |
|---|---|---|
| `maiw-contracts` | `ActionProposal`, `DecisionResult`, `ExecutionResult`, `ApprovalRecord`, domain value objects | *(none)* |
| `maiw-mcp` | `MAIWMCPClient`, `CapabilityRegistry`, MCP transport config | `maiw-contracts` |
| `maiw-models` | `ModelGateway`, `PolicyFilter`, `ModelRouter`, `DeploymentResolver`, `ModelRegistry` | `maiw-contracts` |
| `maiw-state` | `WarehouseStateProvider`, `WarehouseStateSnapshot`, `StateRequirements`, domain state models | `maiw-contracts`, `maiw-mcp` |
| `maiw-skills` | Proposal skills, execution skills, read skills per domain | `maiw-state`, `maiw-mcp`, `maiw-models` |
| `maiw-decision` | `DecisionEngine`, constraint rules, `ApprovalStore` | `maiw-contracts`, `maiw-skills`, `maiw-state` |
| `maiw-execution` | `BaseActionExecutor`, domain executors, `ExecutionRegistry` | `maiw-decision`, `maiw-skills`, `maiw-mcp` |
| `maiw-world` | `WarehouseWorldGenerator`, BASE/SCENARIO/LIVE world states, `OperationalContextSnapshot` | `maiw-state` |
| `maiw-agents` | `AgentRuntime`, `MAIWDeterministicRuntime`, `DeepAgentsRuntime`, `AgentDefinition`, `SOPDefinition`, SOP Engine V2 | `maiw-skills`, `maiw-state`, `maiw-models` |

`maiw-agents` does **not** depend on `maiw-execution`. The dependency was removed when operational write authority was taken out of the agent package; a test asserts the absence of any `maiw_execution` or `ActionExecutor` import rather than trusting this table.

### `maiw-agents` internal ownership

| Module | Owns |
|---|---|
| `sop_engine/engine.py` | Procedure lifecycle: step progression, branching, retry, bounded loops, escalation, checkpointing. Domain-neutral — asserted by an AST import test. |
| `sop_engine/validators.py` | Step completion validators (`SCHEMA`, `STATE_PREDICATE`, `CAPABILITY_RESULT`, `LEGACY_SUCCESS`) and `EvidenceRequirementsValidator`. Holds the code-registered state predicate registry. |
| `sop_engine/state_store.py` | `ProcedureStateStore` protocol; `InMemoryProcedureStateStore`; `JsonFileProcedureStateStore`. Record keeper only — `save` / `load` / `delete` and nothing else. |
| `sop_engine/executor.py` | `SOPStepExecutor` — the per-step runtime seam. |
| `contracts/procedure_state.py` | `ProcedureExecutionState`, the unit a store persists, including `revision`. |
| `contracts/capability_policy.py` | `RuntimeCapabilityPolicy`, `build_capability_policy`, and the deny-by-default `authorize_*` seam shared by both runtimes. |
| `contracts/sop_v2.py` | Declarative step semantics: `StepCompletionSpec`, `RetryPolicy`, `LoopPolicy`, `EvidenceRequirement`, escalation reason codes. |
| `{wave,equipment,inventory}/predicates.py` | Domain-owned state predicates, registered into the engine's registry at import. The engine never imports these. |

What `maiw-agents` deliberately does not own: `ActionExecutor`, `DecisionEngine`, MCP write clients, and warehouse credentials. Persisting procedure state did not change that — a `ProcedureStateStore` cannot act, only record.

---

## Application Shell (`apps/api/`)

| Module | Role |
|---|---|
| `maiw_api.app` | FastAPI application factory; registers all routers |
| `maiw_api.routers.*` | REST API endpoints; delegates to canonical packages |
| `maiw_api.services.*` | Thin adapters (DB sessions, monitoring, security); no business logic |

The API shell imports from all canonical packages. No canonical package imports from `apps/api/`.

---

## Known Migration Boundary

Some runtime code still resides in `src/api/services/` and is imported by `apps/api/maiw_api/app.py`.  
This is a tracked implementation migration boundary, not dead code.  
Do not remove without preserving all ModelGateway invariants (PolicyFilter, ModelRouter, Deployment Resolver, routing provenance).

See [ARCHITECTURE.md § Known Modernization Boundary](ARCHITECTURE.md#known-modernization-boundary).

---

## MCP Domain Servers (`mcp_servers/`)

| Server | Capabilities served | Port |
|---|---|---|
| `mcp_servers/inventory` | `warehouse.inventory.get`, `warehouse.inventory.locate` | 8765 |
| `mcp_servers/equipment` | `warehouse.equipment.get_status`, `warehouse.equipment.get_telemetry`, `.assign`, `.release`, `.schedule_maintenance` | 8766 |
| `mcp_servers/labor` | `warehouse.labor.get_capacity`, `warehouse.labor.get_allocation`, `warehouse.labor.allocate` | 8767 |
| `mcp_servers/wave` | `warehouse.wave.get`, `warehouse.wave.get_risk`, `warehouse.wave.reprioritize` | 8768 |

MCP servers are stateless HTTP (`stateless_http=True`). They are internal infrastructure — not exposed through the ingress.

See [MCP.md](MCP.md) for transport, protocol, and SDK version details.  
See [CAPABILITY_MATRIX.md](CAPABILITY_MATRIX.md) for the full capability catalog.
