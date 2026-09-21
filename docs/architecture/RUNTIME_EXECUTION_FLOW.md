# Runtime Execution Flow — MAIW v2

## Platform Boundary

```
STATE → REASON → PROPOSE → DECIDE → EXECUTE → MCP → BACKEND
```

Every warehouse action passes this boundary exactly once. No step can be skipped.

---

## Read Path (any domain, no approval required)

```
Agent / Skill
    │
    └── WarehouseStateProvider.get_state(StateRequirements)
              │
              └── <Domain>Skill.execute()   ← e.g. EquipmentStatusSkill, WaveGetSkill
                        │
                        └── MAIWMCPClient.invoke("warehouse.<domain>.<read_tool>")
                                  │
                                  └── <Domain>MCPServer → <Domain>Adapter → PostgreSQL
```

Read capabilities (8 total, all `read_only` risk tier):

| Capability | Domain |
|---|---|
| `warehouse.inventory.get` | Inventory |
| `warehouse.inventory.locate` | Inventory |
| `warehouse.equipment.get_status` | Equipment |
| `warehouse.equipment.get_telemetry` | Equipment |
| `warehouse.labor.get_capacity` | Labor |
| `warehouse.labor.get_allocation` | Labor |
| `warehouse.wave.get` | Wave |
| `warehouse.wave.get_risk` | Wave |

---

## Write Path (all domains, requires approval gate)

```
POST /api/v1/<domain>/...
    │
    ▼
API Router → <Domain>Agent / SOP Step
    │
    ├── 1. WarehouseStateProvider.get_state()     ← reads current state via MCP read tools
    │         └── WarehouseStateSnapshot.seal()   ← UUID-stamped, immutable
    │
    ├── 2. <Propose>Skill.execute()               ← builds ActionProposal locally, NO MCP call
    │         └── ActionProposal.for_<action>()   ← pure factory, synchronous, no I/O
    │
    ├── 3. DecisionEngine.evaluate(DecisionRequest)   ← synchronous, no I/O, no MCP call
    │         └── DecisionResult → APPROVED / REJECTED / DEFERRED
    │
    ├── 4. [if APPROVED] ApprovalStore.submit()   ← creates approval record, awaits human
    │
    ├── 5. [on human approval] <Domain>ActionExecutor.execute()
    │         │
    │         └── BaseActionExecutor — 6-guard check:
    │               ①  decision_outcome == APPROVED
    │               ②  proposal_id matches decision_id
    │               ③  action_name in _ALLOWED_ACTIONS frozenset
    │               ④  WarehouseStateSnapshot age ≤ max_decision_age_seconds
    │               ⑤  _additional_guards() hook (domain-specific checks)
    │               ⑥  decision deadline not expired
    │
    └── 6. [all guards pass] MAIWMCPClient.invoke("warehouse.<domain>.<write_tool>")
                │
                └── <Domain>MCPServer → <Domain>Adapter → PostgreSQL
                          │
                          └── Reconciliation → ExecutionRegistry.mark_*()
```

Write capabilities (5 total):

| Capability | Risk | Executor |
|---|---|---|
| `warehouse.equipment.assign` | medium | `EquipmentActionExecutor` |
| `warehouse.equipment.release` | low | `EquipmentActionExecutor` |
| `warehouse.equipment.schedule_maintenance` | medium | `EquipmentActionExecutor` |
| `warehouse.labor.allocate` | medium | `LaborActionExecutor` |
| `warehouse.wave.reprioritize` | medium | `WaveActionExecutor` |

---

## 6-Guard Pattern

`BaseActionExecutor` enforces 6 sequential checks before any MCP write tool is called:

| # | Guard | Failure → |
|---|---|---|
| ① | `decision_outcome == APPROVED` | `NotApprovedError` |
| ② | `proposal_id == decision.proposal_id` | `ProposalMismatchError` |
| ③ | `action_name in _ALLOWED_ACTIONS` | `ActionNotAllowedError` |
| ④ | `snapshot.age ≤ max_decision_age_seconds` | `StaleDecisionError` |
| ⑤ | `_additional_guards()` hook passes | domain-specific `GuardError` |
| ⑥ | `decision.deadline` not expired | `DeadlineExpiredError` |

All guards are synchronous. None call MCP. None call the LLM.

---

## Outcome Reconciliation

After every write, the executor records the outcome in `ExecutionRegistry`:

| MCP result | Registry call | Reconciliation status |
|---|---|---|
| Success response | `mark_executed()` | `CONFIRMED_EXECUTED` |
| Error response | `mark_not_executed()` | `CONFIRMED_NOT_EXECUTED` |
| Timeout / network | `mark_unknown()` | `UNKNOWN` → `RECONCILING` |

`UNKNOWN` is never auto-retried. The `OBSERVE_OUTCOME` SOP step re-reads state and classifies to `CONFIRMED_EXECUTED`, `CONFIRMED_NOT_EXECUTED`, or `INDETERMINATE`.

---

## Architecture Invariants

| # | Invariant | Enforcement |
|---|---|---|
| 1 | LLM cannot call MCP write tools directly | No write tool in any agent tool registry |
| 2 | Proposals are built locally, never via MCP | `ActionProposal` factories have no MCP client |
| 3 | `DecisionEngine.evaluate()` makes no MCP call | Method is synchronous, no `await` |
| 4 | Non-APPROVED decision never reaches executor | 6-guard check ① |
| 5 | Unknown action outside `_ALLOWED_ACTIONS` never reaches MCP | 6-guard check ③ |
| 6 | Expired decision never reaches MCP | 6-guard checks ④ and ⑥ |
| 7 | `warehouse_id` propagates from factory → executor → MCP | Factory methods require `warehouse_id` |
| 8 | One executor per domain, one call-site per capability | `_ALLOWED_ACTIONS` frozenset, no cross-domain execution |

See [CAPABILITY_MATRIX.md](CAPABILITY_MATRIX.md) for the full capability catalog.  
See [GOVERNANCE.md](GOVERNANCE.md) for the approval lifecycle.  
See [MCP.md](MCP.md) for transport, server structure, and capability registry.
