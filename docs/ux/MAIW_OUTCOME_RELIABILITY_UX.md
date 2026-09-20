# MAIW Outcome, Reliability & Decision Trace UX

UX-1D: Outcome, Reliability & Decision Trace Consolidation

> A warehouse operator should be able to tell, at a glance, **whether the action happened,
> whether MAIW is certain it happened, whether the warehouse actually improved, and whether
> MAIW is done or continuing**.

---

## Three Semantic Layers (Never Conflate)

### Layer A — Execution State
**Question: "Did the requested operation execute?"**

Source of truth: `ExecutionRecord` produced by `ActionExecutor`.

| Wire value | Operator label | Severity | Notes |
|---|---|---|---|
| `executed` | Execution confirmed | Green | ActionExecutor confirmed dispatch |
| `no_op` | No operation performed | Neutral | Idempotent — already in correct state |
| `deferred` | Awaiting approval | Amber | Pending governance |
| `conflict` | Blocked by state conflict | Attention | No mutation occurred |
| `unknown` | Execution confirmation unavailable | **Amber (NOT red)** | Unconfirmed ≠ failed |
| `failed` | Execution failed | Red | No mutation — safe to re-evaluate |

**Key invariant:** `unknown` is amber, not red. Unconfirmed does not mean failed.

### Layer B — Reliability / Reconciliation State
**Question: "Is MAIW certain that it executed?"**

Source of truth: `ReconciliationOutcome` from `ReconciliationEngine`.

| Backend value | Operator label | Severity | Operator action? |
|---|---|---|---|
| `confirmed_executed` | Execution confirmed | Green | No |
| `confirmed_not_executed` | Confirmed not executed | Neutral | No |
| `indeterminate` | Operator review required | Attention (orange) | **Yes** |
| _(in-progress)_ | Verifying execution | Amber | No |
| _(not started)_ | Execution confirmation unavailable | Amber | No |

**INDETERMINATE:** MAIW could not determine whether the action occurred. No automatic retry is issued. Manual review required.

**UNKNOWN / RECONCILING:** Not a failure — MAIW is reading authoritative warehouse state before proceeding.

### Layer C — Operational Outcome
**Question: "Did the warehouse move toward the objective?"**

Source of truth: Pre/post state comparison in `OBSERVE_OUTCOME` copilot turn.

| State | Operator label | Severity | Notes |
|---|---|---|---|
| `OBJECTIVE_ACHIEVED` | Objective achieved | **Green** | Only state that earns green |
| `PARTIALLY_ACHIEVED` | Partially achieved | Amber | Some criteria met; reassessing |
| `NOT_ACHIEVED` | Objective not achieved | Attention | Confirmed execution, no improvement |
| `INCONCLUSIVE` | Outcome inconclusive | Neutral | Insufficient data |
| `PENDING` | Outcome assessment pending | Neutral | Awaiting execution resolution |

**Critical color rule:** Green styling on the outcome section appears ONLY when `OBJECTIVE_ACHIEVED`.
Execution confirmed + objective not achieved → amber outcome (not green). Never conflate execution success with operational improvement.

### Layer D — Agent Task State
**Question: "What should the agent do next?"**

Source of truth: `AgentTaskStatus` in `maiw_agents.contracts.task`.

See `src/ui/web/src/constants/agentTaskStates.ts` for full vocabulary.

Key distinction: `COMPLETED` (agent task finished) ≠ `CONFIRMED_EXECUTED` (execution verified). These are always rendered in separate UI fields.

---

## Progressive Disclosure

### Operator view (default)
- Execution state label
- One-sentence explanation
- Whether operator action is required
- What MAIW will do next

### Expert / Developer view (toggle required)
- Exact backend enum value
- `execution_id`
- Timestamps (executed_at, reconciled_at)
- Retry suppression note
- Source (authoritative state vs. SSE)

---

## Reconciliation UX

When execution is `UNKNOWN`:
- Show amber (warning) indicator — not red
- Explain: "MAIW will reconcile authoritative state before taking further action"
- No outcome assessment rendered until reconciliation completes
- No automatic retry

When reconciliation is `RECONCILING`:
- Show "Verifying execution" in amber
- "MAIW is comparing authoritative warehouse state. No operator action required."

When reconciliation is `INDETERMINATE`:
- Show orange attention indicator
- "MAIW could not determine with confidence whether the action occurred."
- "No automatic retry will be issued."
- Show `OPERATOR ACTION REQUIRED` badge
- Do not render outcome summary

---

## OutcomeSummary Structure

```
EXECUTION
  Execution confirmed

RELIABILITY
  Execution confirmed from authoritative state

OUTCOME
  Objective achieved            ← green only here

SUMMARY
  Wave 17 risk decreased after the approved labor reallocation.

KEY CHANGES
  TASK TASK-000001
    Status: PENDING → IN_PROGRESS
    Assigned worker: None → WORKER-000005

KPI IMPACT
  LABOR UTILIZATION
    42.1% → 42.9%
    +0.8%

AGENT STATUS
  Completed
```

All content is from structured props. No LLM call. No inference. Deterministic templating only.

Fallback when no summary provided: "Outcome could not be determined from the available state."

---

## Entity Deltas (StateDelta)

- Shows only changed fields
- Before value: grey with strikethrough
- After value: blue bold
- Unchanged fields: omitted entirely
- Only shown when execution is sufficiently resolved

## KPI Deltas (KPIDelta)

- Shows only KPIs relevant to the intervention objective
- Improvement direction encoded: green delta = improved toward objective, amber = moved away
- Computed delta shown (e.g., "+0.8%", "-1 task")
- Only shown when execution is sufficiently resolved

---

## DecisionGraph Role

**Purpose:** Visual lifecycle — semantic flow of the decision

Shows: Evidence → Agent/SOP → Recommendation → ActionProposal → Decision → Approval → Execution → Outcome

Does NOT show: forensic IDs, runtime latencies, model call counts, execution_id details, chain-of-thought

**Cross-links from DecisionGraph:**
- VIEW DEVELOPER TRACE → forensic detail
- VIEW CONTEXT AT DECISION TIME → exact context snapshot
- VIEW LIVE WORLD → current world state

---

## DeveloperTrace Role

**Purpose:** Forensic provenance — exact evidence chain with IDs and timestamps

Shows: `trace_id`, `turn_id`, `context_snapshot_id`, `agent_task_id`, model route, SOP, skill/delegation calls, governance IDs, `execution_id`, reliability history, outcome links, latencies

Does NOT show: chain-of-thought, scratchpad, hidden reasoning

**Cross-links from DeveloperTrace:**
- VIEW DECISION GRAPH → lifecycle visualization
- VIEW CONTEXT AT DECISION TIME → exact context snapshot
- VIEW LIVE WORLD → current world state

---

## Cross-Link Map

```
Copilot turn
  └─► AgentTask (trace_id)
        └─► DecisionGraph (lifecycle visual)
              └─► DeveloperTrace (forensic detail)
                    ├─► ExecutionRecord (execution_id)
                    ├─► ReconciliationRecord (reliability)
                    └─► OutcomeSummary (operational result)
```

All surfaces share `trace_id`. An operator can reconstruct the full lifecycle from any surface.

---

## Decision History Ownership

- **Canonical:** `DecisionCenter` (/decisions route) — full session decision history, filterable, browsable
- **Summary:** `CommandCenter` (/command route) — latest decision lifecycle via `DecisionLifecycle` component
- Both read from `maiw_decision_history` sessionStorage

---

## Canonical Semantic Matrix

| Question | Source of Truth | Operator Surface | Developer Surface |
|---|---|---|---|
| Did it execute? | ExecutionRecord (ActionExecutor) | OutcomeSummary / ExecutionReliabilityPanel | DeveloperTrace |
| Are we certain? | ReconciliationOutcome (ReconciliationEngine) | ExecutionReliabilityPanel | DeveloperTrace |
| Did it help? | LIVE world state (OBSERVE_OUTCOME delta) | OutcomeSummary | World / DeveloperTrace |
| Why did we act? | Decision provenance (trace_id) | Recommendation panel | DecisionGraph |
| What happens next? | AgentTaskState | AgentActivity / CopilotAgentStatus | DeveloperTrace |

---

## Files

| File | Role |
|---|---|
| `src/ui/web/src/constants/postExecutionStates.ts` | Canonical semantic layer constants |
| `src/ui/web/src/components/outcome/ExecutionReliabilityPanel.tsx` | Execution certainty panel |
| `src/ui/web/src/components/outcome/OutcomeSummary.tsx` | Four-layer outcome summary |
| `src/ui/web/src/components/outcome/StateDelta.tsx` | Entity before/after delta |
| `src/ui/web/src/components/outcome/KPIDelta.tsx` | KPI before/after delta |
| `src/ui/web/src/components/demo/decision-graph/DecisionGraph.tsx` | + cross-links (UX-1D.4) |
| `src/ui/web/src/components/demo/developer-trace/DeveloperTraceView.tsx` | + cross-links (UX-1D.4) |
| `src/ui/web/src/__tests__/ux1d.test.tsx` | 85 semantic separation regression tests |
