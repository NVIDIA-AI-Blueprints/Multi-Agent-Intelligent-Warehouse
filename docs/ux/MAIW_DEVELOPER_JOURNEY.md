# MAIW Developer Journey — Unified Provenance Navigation

**UX-1E** adds a **JOURNEY tab** to `ExpertOverlay` that lets a developer
reconstruct one MAIW operational decision from exact warehouse context all
the way to measured outcome, using only the UI and exact artifact cross-links,
without reading source code or manually searching for IDs.

---

## 7 Stages

| Stage | Source of Truth | Canonical ID |
|---|---|---|
| **CONTEXT** | `OperationalContextSnapshot` | `context_snapshot_id` |
| **AGENT/SOP** | `AgentTaskState` + `SOPDefinition` | `agent_task_id`, `sop_id` |
| **MODEL** | `ModelRouteDecision` (ModelGateway) | `model_id`, `routing_rule` |
| **SKILLS** | Skill / Delegation records | skill names from `skills_used` |
| **DECISION** | `RecommendedAction` + `ActionProposal` + `DecisionEngine` + Approval | `proposal_id`, `decision_id` |
| **EXECUTION** | `ExecutionRecord` + reliability reconciliation | `execution_id` |
| **OUTCOME** | LIVE world state / post-execution KPI delta | `observe_*` fields |

---

## Partial Journeys

Not every interaction traverses all 7 stages. The rail shows only
stages that exist for the current `CopilotTurnResponse.intent`:

| Intent | Active Stages |
|---|---|
| `ask` | CONTEXT, MODEL |
| `analyze` | CONTEXT, AGENT, MODEL, SKILLS, DECISION |
| `act` | All 7 |
| `observe_outcome` | EXECUTION, OUTCOME |

Unavailable stages are visually disabled — clicking them does nothing.

---

## Exact Artifact IDs

All IDs are taken from the **selected `CopilotTurnResponse`** (the last
completed Copilot turn). Cascading fallbacks to `AnalysisResult` are used
only for fields not surfaced by the Copilot API:

| `ArtifactIdentity` field | Primary source | Fallback |
|---|---|---|
| `trace_id` | `CopilotTurnResponse.trace_id` | `AnalysisResult.trace_id` |
| `context_snapshot_id` | `turn.context_snapshot_id` | `turn.act_source_snapshot_id` → `assessment.snapshot_id` |
| `agent_task_id` | `turn.agent_task_id` | `AgentTaskView.task_id` |
| `model_id` | `turn.model_id` | `assessment.model_id` |
| `proposal_id` | `turn.act_proposal_id` | — |
| `decision_id` | `turn.act_decision_id` | — |
| `execution_id` | `turn.act_execution_id` | — |
| `sop_id` | `AgentTaskView.sop_id` | — |
| `warehouse_id` | `assessment.warehouse_id` | `DemoStatus.world.warehouse_id` |

No "latest" heuristic is used. No array[-1] or global-last-item lookup.

---

## Cross-Links

Each stage panel shows **→ links** to adjacent stages. Click navigates
within the same JOURNEY tab (no full-page reload, no conversation reset).

Additional UX-1D cross-links visible in the TRACE tab:

- **VIEW DECISION GRAPH** → semantic provenance graph (DecisionGraph)
- **VIEW CONTEXT AT DECISION TIME** → historical OperationalContextSnapshot
  in World view (only visible when a completed Copilot turn exists)
- **VIEW LIVE WORLD** → current world state

---

## Chain-of-Thought Exclusion

The following fields must NEVER appear in any developer journey panel.
Tests in `ux1e.test.tsx` TC-4 verify this for all 7 stages:

- `chain_of_thought`
- `scratchpad`
- `hidden_reasoning`
- `reasoning_tokens`
- `raw_react_messages`
- `langraph_private_state`
- `hidden_prompts`

---

## Role Separation

| Surface | Role |
|---|---|
| **Developer Journey** (JOURNEY tab) | Orientation and navigation across artifacts |
| **Developer Trace** (TRACE tab) | Forensic structured timeline detail |
| **Decision Graph** (separate pane) | Visual semantic provenance |

The JOURNEY tab is not a third trace implementation — it is a navigation
layer that cross-links to the existing Trace and Graph surfaces.

---

## Runtime Neutrality

The Developer Journey works identically for both:

- `MAIWDeterministicRuntime` (default)
- `DeepAgentsRuntime` (optional)

It reads from `CopilotTurnResponse` structured fields only. It never
accesses LangGraph checkpoint schema, ReAct internals, or private agent
state. The runtime name may appear in the AGENT stage's identity fields
but only as a string label.

---

## Decision / Approval Distinction

The DECISION stage shows four distinct artifacts:

1. `RecommendedAction` — what the agent recommends
2. `ActionProposal` — the structured proposal derived from the recommendation
3. `DecisionEngine` outcome (`decision_id`, `decision_outcome`)
4. Human approval (`pending_approval_id`, `act_approval_required`)

`APPROVED` ≠ `EXECUTED`. An approved proposal that has not been executed
shows `execution_id: null` in the EXECUTION panel.

---

## Execution / Outcome Separation

**EXECUTION**: Did the action execute? (`execution_id`, `execution_status`, `mutation_state`)

**OUTCOME**: Did it help? (`observe_operational_improved`, `observe_operational_summary`, KPI delta)

A confirmed execution with a failed operational objective shows:
- EXECUTION: `mutation_state = CONFIRMED`
- OUTCOME: `observe_operational_improved = false`

---

## World / Context Distinction

| Stage | Time reference |
|---|---|
| CONTEXT stage | Historical snapshot at decision time |
| OUTCOME stage + LIVE WORLD link | Current post-execution world state |

Labels and UX must never conflate "Context at Decision Time" with "Current Operational Context."

---

## Files

| File | Purpose |
|---|---|
| `src/constants/journeyIdentity.ts` | Stage constants, ArtifactIdentity interface, CoT exclusion list |
| `src/components/developer-journey/DeveloperJourneyRail.tsx` | 7-stage horizontal nav rail |
| `src/components/developer-journey/DeveloperJourneyPanel.tsx` | Per-stage artifact detail panels |
| `src/components/demo/ExpertOverlay.tsx` | Hosts JOURNEY tab, derives ArtifactIdentity |
| `src/pages/DemoShell.tsx` | Wires cross-link callbacks and turn state |
| `src/ui/web/src/__tests__/ux1e.test.tsx` | 26 regression tests |
