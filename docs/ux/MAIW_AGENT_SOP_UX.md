# MAIW Agent/SOP Progress + Delegation Experience

**Feature:** UX-1B  
**Date:** 2026-09-20  
**Branch:** feat/ux-1b-agent-sop-progress  
**Status:** COMPLETE

---

## Overview

At any moment, a warehouse operator can answer:
- Which agent is working?
- What objective is it pursuing?
- Which SOP/procedure is it following, and where in that procedure?
- Which specialist agents were consulted?
- Is it still reasoning, waiting for governance, verifying outcome, completed, or escalated?

This document defines the canonical operator and developer experience for MAIW agent procedure visibility.

---

## Operator Experience

### What operators see

**REASON stage — compact AgentActivity panel:**
```
● Operations Coordination Agent                               Working
  Objective: Recover Wave 17 before carrier cutoff
  Procedure: Wave Risk Resolution v1.0
  Runtime: Strict SOP runtime
  [Expand ▼]
```

**Expanded AgentActivity:**
```
  Procedure progress
  Wave Risk Resolution v1.0    5/8 steps

  ✓ Establish current state                         Completed
  ✓ Diagnose primary constraint                     Completed
  → Compare interventions           [highlighted]   In progress
  ○ Generate recommendation                         Pending
  ○ Submit recommendation                           Pending
```

**Specialist consultation (DelegationCard):**
```
  ✓ Labor Agent
  Specialist consultation · Consulted to assess labor capacity

  Finding:
  Labor is the dominant constraint.

  Evidence:
  · 5 pending tasks
  · 4 idle workers
```

**Governance handoff (WAITING_FOR_GOVERNANCE):**
```
  Agent procedure complete
  Recommendation generated
  ↓
  ──────── MAIW AUTHORITY BOUNDARY ────────
  AI can recommend. Operational actions require governance.

  The agent has completed its recommendation and is waiting for MAIW governance.
```

**Outcome continuation (COMPLETED):**
```
  ↓
  Governance complete
  ↓
  ✓ Objective achieved
```

**ESCALATED state:**
```
  ↓
  ! Needs attention
  Conflicting evidence from specialist agents — human review required.
  Human review required to proceed.
```

### What operators NEVER see
- Model chain-of-thought or internal reasoning
- Raw system prompts or LLM messages
- Framework terms: "subagent", "ReAct", "LangGraph", "checkpoint", "tool invocation"
- The word "executing" in reference to agent actions (agent does not execute)
- Write capability names (warehouse.write.*, action_executor.*)

---

## Developer Experience

Expert mode (toggle: top-right "Expert" button) reveals:

**AgentActivity expert detail:**
```
Developer detail
task_id          task-abc123def456
agent_id         operations_coordination
sop_id           operations_coordination.wave_risk_resolution
sop_version      1.0
iteration        1
context_snapshot_id  snap-001abc
trace_id         trace-xyz789
conversation_id  —
copilot_turn_id  —
stop_reason      —
recommendation_id  —
completed_steps  establish_state, diagnose
```

**SOPProgress expert detail (per step):**
```
step_id: establish_state · action: gather_operational_context
```

**DelegationCard expert detail:**
```
delegation_id        labor-del-001
parent_task_id       task-abc123def456
child_task_id        child-labor-001
requesting_agent     operations_coordination
responding_agent     labor
status               COMPLETED
candidate_action_count  2
context_snapshot_id  snap-001abc
trace_id             trace-xyz789
VIEW CONTEXT
VIEW DEVELOPER TRACE
```

---

## Task Status Vocabulary

| Backend Enum | Operator Label | Developer Label |
|---|---|---|
| `PENDING` | Preparing | PENDING |
| `RUNNING` | Working | RUNNING |
| `WAITING_FOR_INPUT` | Waiting for input | WAITING_FOR_INPUT |
| `WAITING_FOR_SUBAGENT` | Consulting specialist | WAITING_FOR_SUBAGENT |
| `WAITING_FOR_GOVERNANCE` | Waiting for governance | WAITING_FOR_GOVERNANCE |
| `OBSERVING_OUTCOME` | Verifying outcome | OBSERVING_OUTCOME |
| `COMPLETED` | Completed | COMPLETED |
| `ESCALATED` | Needs attention | ESCALATED |
| `FAILED` | Could not complete | FAILED |

**Critical invariants:**
- `WAITING_FOR_GOVERNANCE` → "Waiting for governance" (NEVER "waiting to execute")
- No status maps to "Executing" (the agent does not execute warehouse actions)
- `FAILED` (system/runtime error) is visually distinct from `ESCALATED` (intentional human escalation)

---

## SOP Progress Semantics

Each SOP step displays one of these states:

| State | Icon | Text Label | Color | When |
|---|---|---|---|---|
| completed | ✓ | Completed | Green | step_id in `completed_steps` |
| current | → | In progress | Blue | step_id === `current_step_id` AND status is RUNNING |
| pending | ○ | Pending | Gray | not completed, not current |
| governance_wait | ⏸ | Waiting for governance | Amber | step_id === `current_step_id` AND status is WAITING_FOR_GOVERNANCE |
| escalated | ! | Escalated | Red | step_id === `current_step_id` AND status is ESCALATED |
| skipped | ⊘ | Skipped | Dark gray | step was bypassed (conditional step) |

**Data source:** Step labels come from `SOPDefinition.steps[].description` (SOP YAML files), never hardcoded in the UI.

**Accessibility:**
- Every step state has icon + text label (not color-only)
- `role="list"` with `role="listitem"` per step
- Current step: `aria-label="Current step: {description}"` and `aria-current="step"`

---

## Delegation (Specialist Consultation) Semantics

When the Operations Coordination Agent delegates to a specialist:
- **Operator sees:** Agent name, "Specialist consultation", reason consulted, finding, evidence
- **Developer sees:** delegation_id, parent/child task IDs, agent IDs, context_snapshot_id, trace link

**Delegation chain (multiple specialists):**
```
Operations Coordination Agent
   ├── Labor Agent ✓
   └── Wave Agent ✓
```

**Operator-friendly language:** "Consulted to assess labor capacity" (not "subagent invoked to evaluate labor constraint")

---

## Governance Transition

When `AgentTaskState.status === 'WAITING_FOR_GOVERNANCE'`:

1. AgentActivity body shows "Agent procedure complete" → "Recommendation generated" → "↓"
2. `AuthorityBoundary` component renders (reused from UX-1A)
3. Text: "The agent has completed its recommendation and is waiting for MAIW governance."

The agent activity panel terminates visually at the authority boundary — the agent does NOT appear as execution authority.

**NEVER shows:** "Agent waiting to execute" or any suggestion the agent controls execution.

---

## Outcome Continuation

After governance/execution, task transitions through:

**OBSERVING_OUTCOME:**
- "Governance complete" → "↓" → "◎ Verifying outcome" (blue/green)

**COMPLETED:**
- "Governance complete" → "↓" → "✓ Objective achieved" (green box)

**ESCALATED (intentional human handoff):**
- "! Needs attention" (amber box, NOT red)
- Shows: stop_reason, "Human review required to proceed."
- Visually distinct from FAILED

**FAILED (system/runtime error):**
- "✕ Could not complete" (red box)
- Shows: stop_reason, "A system or tool error prevented completion."
- Visually distinct from ESCALATED

---

## Chain-of-Thought Exclusion

The following are NEVER exposed through any UI component:
- `chain_of_thought` field
- `scratchpad` content
- `hidden_reasoning` text
- Raw LLM messages or prompts
- System prompt content
- LangGraph node state
- deepagents checkpoint data

**Why:** MAIW AgentTaskState is designed as a structured, scratchpad-free state machine. Observations store facts, not reasoning. See `packages/maiw-agents/maiw_agents/contracts/task.py`.

---

## Runtime-Neutral Architecture Invariant

```
AgentActivity → AgentTaskState API only
          NOT deepagents internal state
          NOT LangGraph state
          NOT provider clients
          NOT ActionExecutor
```

Frontend components (`SOPProgress.tsx`, `AgentActivity.tsx`, `DelegationCard.tsx`) import only from:
- `../../types/agentTask` — MAIW AgentTaskView types
- `../../constants/agentTaskStates` — status vocabulary
- `../AuthorityBoundary` — existing UX-1A component

They do NOT import from `deepagents`, `langgraph`, or any AI provider package.

---

## API Reference

### GET /api/v1/agent-tasks/{task_id}

Returns `AgentTaskView` with:
- All `AgentTaskState` fields (task_id, agent_id, sop_id, status, etc.)
- `sop_steps`: step metadata resolved from SOP YAML (id, action, description)
- `delegation_results`: specialist consultation results

NEVER returns:
- chain_of_thought, scratchpad, raw prompts
- LangGraph state, deepagents checkpoints
- Full conversation history

### GET /api/v1/agent-tasks/{task_id}/sop

Returns `SOPMetadataView` with step descriptions from the SOP YAML.

### GET /api/v1/agent-tasks

Lists recent active agent tasks.

All endpoints are **read-only (GET only)** — no mutations.

---

## Runtime Profiles

| SOP `runtime_profile` | Operator Label | Expert Label |
|---|---|---|
| `strict` | Strict SOP runtime | MAIWDeterministicRuntime |
| `adaptive` | Adaptive runtime | DeepAgentsRuntime |

Framework internals remain behind Expert disclosure. Operators see only the profile name.

---

## Deferred Findings

The following items were deferred from UX-1B and may be addressed in UX-1C or later:

1. **Copilot compact status** (Step 11): `task_id` is not currently included in Copilot turn data. Deferred until `CopilotTurnResponse` exposes `agent_task_id`.

2. **Actual API polling**: The `agentTaskAPI.getTask()` function exists but the demo shell currently constructs a synthetic task from `AnalysisResult`. Once the backend logs task state to the registry during analysis, polling can be wired.

3. **Step timestamps**: `AgentObservation.timestamp` exists in the backend but is not currently surfaced in `sop_steps`. Can be added when needed.

4. **Contextual snapshot view**: "VIEW CONTEXT" link in DelegationCard expert view links to `/world?snapshot={context_snapshot_id}`. The actual WorldShell routing for this URL param requires verification.

5. **Skipped step state**: The `skipped` step state icon (⊘) is defined in constants but not yet produced by `computeSOPStepDisplays` (no conditional step evaluation in the frontend).

---

## Files Changed

### New files
- `apps/api/maiw_api/routers/agent_tasks.py` — Read-only agent tasks API
- `src/ui/web/src/constants/agentTaskStates.ts` — Status vocabulary
- `src/ui/web/src/types/agentTask.ts` — TypeScript types
- `src/ui/web/src/components/demo/SOPProgress.tsx` — SOP step progress component
- `src/ui/web/src/components/demo/AgentActivity.tsx` — Agent activity panel
- `src/ui/web/src/components/demo/DelegationCard.tsx` — Specialist consultation card
- `src/ui/web/src/services/agentTaskAPI.ts` — API service + demo synthetic task builder
- `src/ui/web/src/__tests__/ux1b.test.tsx` — 73 tests
- `docs/audits/uiux/screenshots/ux1b/README.md` — Screenshots manifest
- `docs/ux/MAIW_AGENT_SOP_UX.md` — This document

### Modified files
- `apps/api/maiw_api/app.py` — Register agent_tasks router
- `src/ui/web/src/components/demo/StageContentPane.tsx` — Add `agentTask` prop
- `src/ui/web/src/components/demo/stages/ReasonStage.tsx` — Add AgentActivity
- `src/ui/web/src/components/demo/stages/ProposeStage.tsx` — Add procedure completion banner
- `src/ui/web/src/pages/DemoShell.tsx` — Build demo agentTask, pass to StageContentPane
