# MAIW Information Architecture

> Version: UX-1C  
> Date: 2026-09-20  
> Status: Implemented

---

## Personas

| Persona | Role | Primary Questions | Primary Surface |
|---------|------|-------------------|-----------------|
| **Operator (OPR)** | Warehouse supervisor making real-time decisions | What is at risk? What should I do? Did it work? | `/demo` (Operations) |
| **Developer (DEV)** | NVIDIA/partner engineer verifying the pipeline | Which SOP ran? What model was used? Full trace? | ExpertOverlay, Model Lab, Activity |
| **GSI/Architect** | Systems integrator deploying MAIW | What to connect? What to configure? What's replaceable? | Capabilities, Documentation |

---

## Canonical Navigation

After UX-1A, the global navigation is:

```
MAIW OPERATIONS  [SIMULATED WAREHOUSE indicator when active]
OPERATIONS | WORLD | RELIABILITY | MODELS | CAPABILITIES | ACTIVITY
```

| Nav Label | Route | Persona | Description |
|-----------|-------|---------|-------------|
| **OPERATIONS** | `/demo` | OPR | Primary operator lifecycle — scenario, analyze, propose, approve, execute, outcome |
| **WORLD** | `/world` | OPR/DEV | Warehouse World Explorer — entity graph, context snapshots, BASE/SCENARIO/LIVE views |
| **RELIABILITY** | `/command` | DEV/OPR | Governance & system overview — KPI trend, pipeline, fault injection, decision history |
| **MODELS** | `/models` | DEV/GSI | Model Gateway — policy, model roles, status. Link to Model Lab sub-route |
| **CAPABILITIES** | `/capabilities` | GSI | MCP capability catalogue |
| **ACTIVITY** | `/activity` | DEV | Full session event log |

**Not in primary nav (accessible via URL):**
- `/models/lab` — Model Gateway Evaluation Lab (developer-only; VIEW ONLY, no live inference)
- `/state` — Warehouse entity inspector (developer/GSI)
- `/decisions` — Decision history and manual action trigger
- `/health` — System health
- `/documentation/*` — Documentation hub

**Legacy routes (not MAIW v2 core):**
- `/chat`, `/equipment`, `/operations`, `/safety`, `/forecasting`, `/analytics`, `/documents`

---

## Route Ownership Table

| Route | Visible Name | Persona | Canonical? | Role | Future Action |
|-------|-------------|---------|-----------|------|---------------|
| `/demo` | Operations | OPR | YES — PRIMARY | Lifecycle orchestration shell | Promote. This is the canonical operator home. |
| `/world` | World Explorer | OPR/DEV | YES | Warehouse state inspection | Keep. Phase 17 foundation. |
| `/command` | Governance Overview | DEV/OPR | SECONDARY | System dashboard, KPI, fault injection | Retain. Not the operator home. Renamed from "Command Center" in nav to "Reliability". |
| `/models` | Model Gateway | DEV/GSI | YES | Model policy & status | Keep. |
| `/models/lab` | Model Gateway Lab | DEV | YES | Read-only evaluation artifact viewer | Keep VIEW ONLY. Add link from /models nav. |
| `/capabilities` | Capabilities | GSI | YES | MCP skill catalogue | Keep. |
| `/activity` | Activity Feed | DEV | YES | Session event log | Keep. |
| `/decisions` | Decision Center | OPR/DEV | SECONDARY | Decision history + manual trigger | Keep. Not primary. |
| `/state` | Warehouse State | DEV/GSI | SECONDARY | Entity inspector | Keep. Not primary. |

---

## Operator Journey

1. Navigate to **OPERATIONS** (`/demo`)
2. Select a scenario (ScenarioSelector)
3. Observe warehouse state (OBSERVE stage — WorldGrid, KPI strip, state freshness)
4. Trigger analysis → agent reasons (REASON stage — structured reasoning arc)
5. Review proposed action (PROPOSE stage — ProposalCard, WHY THIS RECOMMENDATION?, AuthorityBoundary, pre-execution notice)
6. Governance evaluation (DECIDE stage — DecisionEngine outcome, violations, policy approval notice or human approval routing)
7. Human approval if required (APPROVE stage — ApprovalCard, HUMAN APPROVAL REQUIRED hero, APPROVE ACTION button, pre-execution notice)
8. Execution (EXECUTE stage — ActionExecutor via MCP, outcome label)
9. Outcome verification (OUTCOME stage — KPI delta, reconciliation status)

At every stage, the operator can open the **Copilot** (ASK) for evidence-grounded answers and can switch to **WORLD** mode to inspect the warehouse state.

---

## Developer Journey

1. Navigate to **OPERATIONS** → enable **Expert Mode** (toggle, top-right)
2. Observe technical detail: model_id, routing_rule, snapshot_id, trace_id, execution_id
3. Open **ExpertOverlay → JOURNEY** for end-to-end provenance navigation across all 7 stages
   (Context → Agent/SOP → Model → Skills → Decision → Execution → Outcome)
4. Open **ExpertOverlay → TRACE** for full developer trace timeline and forensic artifacts
5. Open **ExpertOverlay → RUNTIME** for runtime health, MCP domain status, agent availability
6. Navigate to **WORLD → CONTEXT** to view OperationalContextSnapshot at decision time
7. Navigate to **MODELS / LAB** to inspect model evaluation runs (VIEW ONLY)
8. Navigate to **ACTIVITY** for full SSE event log

See [MAIW_DEVELOPER_JOURNEY.md](MAIW_DEVELOPER_JOURNEY.md) for stage definitions,
partial journey maps, exact artifact IDs, and chain-of-thought exclusion invariants.

---

## Shared Surfaces

| Surface | Used by Operator | Used by Developer | Notes |
|---------|-----------------|-------------------|-------|
| DemoShell modes (operations/world/reliability) | YES | YES | Mode switcher in top nav |
| WorldShell OVERVIEW | YES | YES | Operator: entity counts. Developer: CHANGES, CONTEXT, RAW tabs |
| CopilotDrawer | YES | YES | Developer gets model_id/routing_rule in expert panel |
| ApproveStage | YES | NO | Operator-facing card with governance semantics |
| ExpertOverlay | NO | YES | Gated behind Expert toggle |

---

## Authority Boundary

The MAIW Authority Boundary separates AI reasoning from governed operational execution.

Visual placement:
- **ProposeStage**: AuthorityBoundary component appears below the pre-execution notice and above the proposal cards
- **ApproveStage**: Pre-execution notice appears before the APPROVE ACTION button is available

See `docs/ux/MAIW_AUTHORITY_UX.md` for the full authority-state model.

---

## Progressive Disclosure

| Information Level | Default View | Expert Mode |
|------------------|-------------|-------------|
| Operational conclusion | VISIBLE | VISIBLE |
| Evidence / facts_observed | VISIBLE | VISIBLE |
| Risk level | VISIBLE | VISIBLE |
| Recommended action | VISIBLE | VISIBLE |
| Expected outcome | VISIBLE | VISIBLE |
| Authority state (current phase) | VISIBLE | VISIBLE |
| State freshness (FRESH/AGING/STALE) | VISIBLE | VISIBLE |
| model_id | HIDDEN | VISIBLE |
| routing_rule | HIDDEN | VISIBLE |
| snapshot_id | HIDDEN | VISIBLE |
| execution_id | HIDDEN | VISIBLE |
| proposal_id / decision_id | HIDDEN | VISIBLE |
| latency_ms | HIDDEN | VISIBLE |
| Raw MCP payload | HIDDEN | VISIBLE (ExpertOverlay) |
| trace_id timeline | HIDDEN | VISIBLE (ExpertOverlay → TRACE) |

---

## Deferred Consolidation (UX-2+)

| Issue | Priority | Rationale for Deferral |
|-------|----------|----------------------|
| Two ReliabilityPanel implementations | Medium | Structural — consolidate in UX-2 |
| DecisionGraph + DeveloperTraceView overlap | Low | Both serve developer need; consolidate later |
| WorldShell CONTEXT empty state references Copilot | Low | UX copy fix only |
| `/state` and `/decisions` not in primary nav | Low | Secondary surfaces; URL access sufficient |
| CommandCenter approval UI vs DemoShell approval UI | Medium | CommandCenter provides less context; block or redirect in UX-2 |

---

## UX-1B / UX-1C Implementation Status

**UX-1B** (complete — feat/ux-1b-agent-sop-progress):
- SOP step visibility in REASON stage (which SOP ran, step sequence, iteration count)
- Subagent delegation chain with DelegationCard
- INDETERMINATE / UNKNOWN outcome operator guidance in AgentActivity
- OUTCOME stage narrative via OutcomeContinuation deterministic templates
- DelegationCard status-aware subtitles for RUNNING/COMPLETED/FAILED/ESCALATED

**UX-1C** (complete — feat/ux-1b-agent-sop-progress):
- CopilotAgentStatus component — live task state polling in CopilotDrawer
- `agent_task_id` linkage: ACT turns → exact AgentTaskState entry
- `subscribeToTask()` — bounded polling (3s), stops on terminal state or 404
- WAITING_FOR_GOVERNANCE: governance pause semantics surfaced in CopilotDrawer
- OBSERVING_OUTCOME: outcome semantics text in CopilotDrawer
- Expert mode: task_id, agent_id, sop_id, sop_version, iteration, trace_id
- AgentActivity: REVIEW GOVERNANCE button, INDETERMINATE/UNKNOWN panels
- AgentActivity OutcomeContinuation: VIEW LIVE WORLD button + semantics text
- DelegationCard: live delegation state with pulsing animation for RUNNING

See `docs/ux/MAIW_LIVE_AGENT_CONTINUITY.md` for the full UX-1C specification and
design invariants.

## Canonical Post-Execution Surfaces (UX-1D)

UX-1D adds three semantic layers that must never be conflated. Each layer answers
a distinct operator question with a distinct source of truth and surface.

| Question | Source of Truth | Operator Surface | Developer Surface |
|---|---|---|---|
| Did it execute? | ExecutionRecord (ActionExecutor) | OutcomeSummary / ExecutionReliabilityPanel | DeveloperTrace |
| Are we certain? | ReconciliationOutcome (ReconciliationEngine) | ExecutionReliabilityPanel | DeveloperTrace |
| Did it help? | LIVE world state (OBSERVE_OUTCOME delta) | OutcomeSummary | World / DeveloperTrace |
| Why did we act? | Decision provenance (trace_id) | Recommendation panel | DecisionGraph |
| What happens next? | AgentTaskState | AgentActivity / CopilotAgentStatus | DeveloperTrace |

### New Surfaces (UX-1D)

- **ExecutionReliabilityPanel** (`components/outcome/`) — Execution certainty view with operator and
  expert mode. UNKNOWN/RECONCILING shown in amber (not red). INDETERMINATE shows operator action badge.
- **OutcomeSummary** (`components/outcome/`) — Four-layer summary: EXECUTION / RELIABILITY / OUTCOME /
  AGENT STATUS. All deterministic templating, no LLM calls. Green outcome only when OBJECTIVE_ACHIEVED.
- **StateDelta** (`components/outcome/`) — Entity before/after diff. Shows only changed fields.
- **KPIDelta** (`components/outcome/`) — KPI before/after for metrics relevant to the intervention.

### DecisionGraph vs DeveloperTrace Role Separation (UX-1D)

| | DecisionGraph | DeveloperTrace |
|---|---|---|
| Purpose | Visual lifecycle | Forensic provenance |
| Shows | Evidence → Outcome flow | IDs, timestamps, latencies, model routes |
| Cross-links | VIEW DEVELOPER TRACE, CONTEXT, LIVE WORLD | VIEW DECISION GRAPH, CONTEXT, LIVE WORLD |

See `docs/ux/MAIW_OUTCOME_RELIABILITY_UX.md` for full UX-1D specification.

## Deferred
