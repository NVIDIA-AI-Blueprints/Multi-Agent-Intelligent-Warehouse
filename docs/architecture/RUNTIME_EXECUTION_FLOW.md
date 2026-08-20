# Runtime Execution Flow — Phase 6B

## Overview

Phase 6B hardens the architecture boundary so that MCP exposes only execution capabilities — never proposal generation. The platform boundary is:

```
STATE → REASON → PROPOSE → DECIDE → EXECUTE → MCP → BACKEND
```

Phase 6 completed the equipment action lifecycle (PROPOSE → DECIDE → EXECUTE → RESULT). Phase 6B enforces the layer contract:

- **Proposals are built locally** in the agent/skill layer — `ActionProposal` factories require no MCP call.
- **MCP exposes exactly 5 tools**: 2 read-only, 3 write-execution (semantic names: `warehouse.equipment.assign/release/schedule_maintenance`).
- **`EquipmentActionExecutor` is the only gateway** to MCP write tools; it enforces 5 guards before any write reaches MCP.
- **`warehouse_id` propagates** from factory → proposal.parameters → `_check_state_drift`; no write silently uses a hardcoded default.

### Architecture Invariants (permanent)

| Invariant | Enforcement |
|-----------|-------------|
| LLM cannot execute MCP writes directly | No MCP write tool in agent's tool registry |
| Proposal skill cannot execute MCP writes | `EquipmentAssignmentSkill` has no MCP client |
| DecisionEngine cannot execute MCP writes | `evaluate()` is synchronous, no I/O |
| Only ActionExecutor reaches MCP write capabilities | Single call-site: `ActionExecutor.execute()` |
| No dynamic dispatch of model-produced capability names | `_ALLOWED_ACTIONS` frozenset |
| No Equipment write silently uses `warehouse_id="default"` | `warehouse_id` required in all factory methods |

## Implemented Runtime Paths

### Equipment Assignment (Write Path — MEDIUM risk, requires approval)

```
POST /api/v1/equipment/assign
    │
    ▼
src/api/routers/equipment.py:assign_equipment()
    │
    ▼
EquipmentAssetOperationsAgent.propose_equipment_assignment()
    │   (delegates to state_aware_ops.propose_equipment_assignment())
    │
    ├── 1. WarehouseStateProvider.get_state(StateRequirements(equipment=True, asset_id=...))
    │         │
    │         └── EquipmentStatusSkill.execute()
    │                   │
    │                   └── MAIWMCPClient.invoke("warehouse.equipment.get_status")
    │                               │
    │                               └── EquipmentMCPServer → MAIWEquipmentAdapter
    │                                               → EquipmentAssetTools → PostgreSQL
    │
    ├── 2. WarehouseStateSnapshot.seal(state)  ← UUID-identified, immutable
    │
    ├── 3. EquipmentAssignmentSkill.execute()  ← builds ActionProposal locally
    │         │                                    NO MCP CALL — pure factory, no I/O
    │         └── ActionProposal.for_equipment_assign()  ← local, synchronous
    │
    └── 4. DecisionEngine.evaluate(DecisionRequest(proposal, snapshot))
                │
                └── DecisionResult(outcome=REQUIRES_HUMAN_APPROVAL)
                        │   [MEDIUM risk → never auto-executes]
                        ▼
                   API response:
                   {
                     "status": "requires_human_approval",
                     "action": "warehouse.equipment.assign",
                     "proposal_id": "...",
                     "decision_id": "...",
                     "reason": "...",
                     "executed": false,
                     "snapshot_id": "...",
                     "violations": [...]
                   }
```

**Invariant**: Assignment `executed` is always `false`. MEDIUM risk → human approval gate.

### Equipment Release (Write Path — LOW risk, auto-executes)

```
POST /api/v1/equipment/release
    │
    ▼
src/api/routers/equipment.py:release_equipment()
    │
    ▼
EquipmentAssetOperationsAgent.propose_equipment_release()
    │   (delegates to state_aware_ops.propose_equipment_release())
    │
    ├── 1. WarehouseStateProvider.get_state(StateRequirements(equipment=True, asset_id=...))
    │
    ├── 2. WarehouseStateSnapshot.seal(state)
    │
    ├── 3. ActionProposal.for_equipment_release()  ← risk_level=LOW, requires_approval=False
    │         (built directly in state_aware_ops, no MCP call)
    │
    ├── 4. DecisionEngine.evaluate() → DecisionResult(outcome=APPROVED)
    │         [Rule 5: LOW risk + requires_approval=False → APPROVED immediately]
    │
    └── 5. EquipmentActionExecutor.execute(proposal, decision)
                │
                ├── Guard 1: outcome == APPROVED ✓
                ├── Guard 2: decision.proposal_id == proposal.proposal_id ✓
                ├── Guard 3: action in _ALLOWED_ACTIONS ✓
                ├── Guard 4: decision age ≤ max_decision_age_seconds ✓
                ├── Guard 5: state-drift check (best-effort)
                │
                └── ExecuteEquipmentReleaseSkill.execute()
                          │
                          └── MAIWMCPClient.invoke("warehouse.equipment.release")
                                      │
                                      └── EquipmentMCPServer → MAIWEquipmentAdapter
                                                      → EquipmentAssetTools → PostgreSQL
                        │
                        ▼
                   ActionExecutionResult(executed=True, success=True, execution_id=...)
                        │
                        ▼
                   API response:
                   {
                     "status": "executed",
                     "action": "warehouse.equipment.release",
                     "proposal_id": "...",
                     "decision_id": "...",
                     "execution_id": "...",
                     "executed": true,
                     "success": true,
                     "snapshot_id": "...",
                   }
```

### Equipment Maintenance Schedule (Write Path — MEDIUM risk, requires approval)

```
POST /api/v1/equipment/maintenance
    │
    ▼
EquipmentAssetOperationsAgent.propose_schedule_maintenance()
    │
    ├── ActionProposal.for_schedule_maintenance()  ← risk_level=MEDIUM, requires_approval=True
    │
    ├── DecisionEngine.evaluate() → REQUIRES_HUMAN_APPROVAL
    │
    └── executor is NEVER called for MEDIUM risk proposals
                        │
                        ▼
                   API response:
                   {
                     "status": "requires_human_approval",
                     "action": "warehouse.equipment.schedule_maintenance",
                     "executed": false,
                     "proposal_id": "...",
                     "decision_id": "...",
                   }
```

### Equipment Status (Read Path)

```
GET /api/v1/equipment/{asset_id}/status
    │
    ▼
src/api/routers/equipment.py:get_equipment_status()
    │
    ├── EquipmentAssetOperationsAgent.get_equipment_state_snapshot()  ← optional, non-blocking
    │         │  (state_aware_ops.get_equipment_state_snapshot())
    │         │
    │         └── WarehouseStateProvider.get_state(StateRequirements(equipment=True))
    │                   └── EquipmentStatusSkill → MCP → PostgreSQL
    │
    ├── equipment_agent.asset_tools.get_equipment_status()  ← existing path, always present
    └── equipment_agent.asset_tools.get_equipment_telemetry()
    │
    ▼
    {
        "equipment_status": {...},
        "telemetry_data": {...},
        "timestamp": "...",
        "state_snapshot": {   ← present only when MCP server is configured
            "snapshot_id": "...",
            "equipment": { "total_count": ..., "freshness": {...} },
            "provenance": [{ "domain": "equipment", "source": "mcp", ... }]
        }
    }
```

**Invariant**: Read path never routes through DecisionEngine.

### Chat Path (Phase 6 — ModelGateway migration complete)

```
POST /api/v1/chat
    │
    ▼
MCPIntegratedPlannerGraph
    │  keyword intent routing
    └── MCPEquipmentAssetOperationsAgent
              └── _llm_generate()  ← routes to ModelGateway or NIM based on env
                  │  (is_model_gateway_enabled() → True → ModelGateway.generate(ModelRequest))
                  │  (is_model_gateway_enabled() → False → nim_client.generate_response())
                  └── ToolDiscoveryService → EquipmentMCPAdapter
```

`MCPEquipmentAssetOperationsAgent` now routes all LLM calls through `_llm_generate()`. When `MAIW_MODEL_GATEWAY_ENABLED=true`, it uses `ModelGateway`; otherwise falls back to direct NIM. `WarehouseStateProvider` and `EquipmentActionExecutor` are wired into the chat agent's `_initialize_state_path()` when `MAIW_MCP_SERVER_EQUIPMENT_URL` is set.

**Architectural debt (Phase 6B):** The chat agent still uses `ToolDiscoveryService` (legacy) for assignment (line ~615) and maintenance (line ~674) intents in `mcp_equipment_agent.py`. These bypass the `STATE → PROPOSE → DECIDE → EXECUTE` lifecycle. Equipment writes initiated via chat do NOT currently go through `EquipmentActionExecutor`. Tracked for Phase 7.

## Decision Outcomes and API Behavior

| DecisionOutcome | HTTP status | `executed` | What happened |
|-----------------|-------------|------------|---------------|
| `requires_human_approval` | 200 | `false` | MEDIUM risk / requires_approval=True — a human must approve |
| `rejected` | 200 | `false` | Asset not found in snapshot — proposal cannot proceed |
| `requires_fresh_state` | 200 | `false` | Equipment state stale or absent — caller should refresh |
| `approved` | 200 | `false` | APPROVED but no executor wired — proposal-only mode |
| `executed` | 200 | `true` | APPROVED + executor wired → write succeeded |
| `error` | 400 | `false` | State assembly, skill invocation, or execution failed |

Decision outcomes are **not** HTTP errors — they are classification results. Only `status == "error"` maps to HTTP 400.

## Dependency Injection

`EquipmentAssetOperationsAgent` accepts injected state-aware components:

```python
agent = EquipmentAssetOperationsAgent(
    state_provider=WarehouseStateProvider(equipment_status_skill=skill),
    decision_engine=DecisionEngine(),
    assignment_skill=EquipmentAssignmentSkill(),  # no client — builds proposals locally
)
```

When not injected, `initialize()` builds them from process-level skill singletons if `MAIW_MCP_SERVER_EQUIPMENT_URL` is set. When the env var is absent the agent falls back to the legacy `asset_tools.assign_equipment()` path.

## Telemetry Correlation

Every state-aware request carries a `trace_id` through the full chain:

```
API request → agent → state_provider.get_state(trace_id) → skill → MCP client
                    → assignment_skill.execute(trace_id)
                    → DecisionRequest(trace_id)
                    → DecisionAuditRecord(trace_id)
                    → API response(trace_id)
```

Structured log fields per request:
- `snapshot_id` — identifies the exact state version used
- `proposal_id` — identifies the ActionProposal
- `decision_id` — identifies the DecisionResult
- `trace_id` — correlates across the full span

## EquipmentActionExecutor Guards (Phase 6)

`EquipmentActionExecutor.execute(proposal, decision)` applies five guards in order before routing to the appropriate skill:

```
DecisionResult(APPROVED)
    ↓
Guard 1: outcome == APPROVED           → ActionNotApproved(ValueError) if not
Guard 2: decision.proposal_id matches  → ActionDecisionMismatch(ValueError) if not
Guard 3: action in _ALLOWED_ACTIONS    → ActionUnsupported(ValueError) if not
Guard 4: decision age ≤ max_age        → ActionExpired(ValueError) if stale
Guard 5: state-drift check (best-effort)
           asset.status in {offline, maintenance}
                                       → ActionConflict(RuntimeError) if drifted
    ↓
Route: assign / release / maintenance skill
    ↓
ActionExecutionResult(executed=True, success=True, execution_id=<uuid>)
```

**Allowed actions** (`_ALLOWED_ACTIONS` frozenset):
- `warehouse.equipment.assign`
- `warehouse.equipment.release`
- `warehouse.equipment.schedule_maintenance`

**Error types** (all in `src/api/agents/inventory/action_executor.py`):

| Exception | Base | Meaning |
|-----------|------|---------|
| `ActionNotApproved` | `ValueError` | Decision outcome is not APPROVED |
| `ActionDecisionMismatch` | `ValueError` | Decision's proposal_id doesn't match the proposal |
| `ActionUnsupported` | `ValueError` | Action not in the executor's allowlist |
| `ActionExpired` | `ValueError` | Decision is older than `max_decision_age_seconds` |
| `ActionConflict` | `RuntimeError` | Asset state has drifted since decision was made |
| `ActionExecutionError` | `RuntimeError` | Skill/backend threw an unexpected exception |

## Capability Audit (Phase 6B)

MCP exposes exactly 5 tools. Proposals are never built in MCP — they are built locally by agent/skill layer factories.

| MCP Tool Name | Layer | Risk | Side-effect | Notes |
|---------------|-------|------|-------------|-------|
| `warehouse.inventory.get` | MCP READ | low | none | Inventory lookup |
| `warehouse.inventory.locate` | MCP READ | low | none | Location lookup |
| `warehouse.equipment.get_status` | MCP READ | low | none | Status query |
| `warehouse.equipment.get_telemetry` | MCP READ | low | none | Telemetry query |
| `warehouse.equipment.assign` | MCP WRITE | medium | write | Requires `proposal_id` + `decision_id`; called only by ActionExecutor |
| `warehouse.equipment.release` | MCP WRITE | low | write | Requires `proposal_id` + `decision_id`; called only by ActionExecutor |
| `warehouse.equipment.schedule_maintenance` | MCP WRITE | medium | write | Requires `proposal_id` + `decision_id`; called only by ActionExecutor |

**Agent/skill layer capabilities** (not MCP tools — local computation only):

| Capability | Class | Layer | Output |
|------------|-------|-------|--------|
| Build assignment proposal | `EquipmentAssignmentSkill.execute()` | PROPOSE | `ActionProposal` (pure factory) |
| Build release proposal | `ActionProposal.for_equipment_release()` | PROPOSE | `ActionProposal` (pure factory) |
| Build maintenance proposal | `ActionProposal.for_schedule_maintenance()` | PROPOSE | `ActionProposal` (pure factory) |
| Evaluate risk | `DecisionEngine.evaluate()` | DECIDE | `DecisionResult` (synchronous, no I/O) |
| Execute assignment | `ExecuteEquipmentAssignmentSkill` | EXECUTE | Calls `warehouse.equipment.assign` MCP tool |
| Execute release | `ExecuteEquipmentReleaseSkill` | EXECUTE | Calls `warehouse.equipment.release` MCP tool |
| Execute maintenance | `ExecuteEquipmentMaintenanceSkill` | EXECUTE | Calls `warehouse.equipment.schedule_maintenance` MCP tool |

## Legacy Path Status

| Component | Status | Notes |
|-----------|--------|-------|
| `EquipmentAssetTools.assign_equipment()` | KEEP (fallback) | Called only when `MAIW_MCP_SERVER_EQUIPMENT_URL` is absent |
| `EquipmentMCPAdapter` | KEEP | Still used by `MCPEquipmentAssetOperationsAgent` in chat path |
| `MCPEquipmentAssetOperationsAgent` | MIGRATED (Phase 6) | LLM calls now route through `_llm_generate()` → ModelGateway or NIM |
| `equipment_action_tools.py` | DELETED (Phase 3) | Zero importers confirmed |
| `wms_adapter.py`, `iot_adapter.py`, `erp_adapter.py` | DELETED (Phase 3) | Never registered |
