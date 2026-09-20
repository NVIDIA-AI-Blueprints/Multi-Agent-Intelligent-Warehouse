# MAIW Live Agent Continuity

> Feature: UX-1C  
> Status: Implemented  
> Date: 2026-09-20

---

## Overview

UX-1C turns the static agent/SOP components from UX-1B into a real-time operator
journey across the full MAIW lifecycle. The operator can watch one MAIW task move
continuously from reasoning, through governance, into execution and outcome
verification without manually stitching together separate screens.

---

## Agent Task Lifecycle

MAIW agent tasks move through these states in order:

```
PENDING → RUNNING → WAITING_FOR_GOVERNANCE → OBSERVING_OUTCOME → COMPLETED
                                                                 → ESCALATED
                                                                 → FAILED
```

| State | Meaning |
|-------|---------|
| `PENDING` | Task created, not yet started |
| `RUNNING` | Agent is actively processing the SOP |
| `WAITING_FOR_GOVERNANCE` | Agent work is paused — governance is evaluating the proposed action |
| `OBSERVING_OUTCOME` | Governance approved; MAIW is re-reading warehouse state to verify objective |
| `COMPLETED` | Objective verified as achieved |
| `ESCALATED` | Human attention required; MAIW could not autonomously resolve |
| `FAILED` | System or tool error prevented completion |

---

## CopilotAgentStatus Component

The `CopilotAgentStatus` component (`src/ui/web/src/components/copilot/CopilotAgentStatus.tsx`)
renders inline in the CopilotDrawer after ACT and OBSERVE_OUTCOME turns when an
`agent_task_id` is present in the turn response.

### Live Updates

- Polls `/api/v1/agent-tasks/{task_id}` every 3 seconds (configurable via `pollIntervalMs`)
- Uses a `setTimeout` chain (not `setInterval`) to avoid overlapping requests
- Stops automatically when task reaches a terminal state (COMPLETED/ESCALATED/FAILED)
- Stops on 404 (task no longer available)
- Cleanup runs on unmount and when `agentTaskId` prop changes

### State Labels and Operator Guidance

| State | Label | Operator Text |
|-------|-------|---------------|
| `WAITING_FOR_GOVERNANCE` | GOVERNANCE PAUSE | "Agent work is paused while MAIW governance evaluates the proposed action." |
| `OBSERVING_OUTCOME` | VERIFYING OUTCOME | "MAIW is re-reading the warehouse state to determine whether the objective was achieved." |
| `ESCALATED` | ESCALATED (amber) | "Human attention required. MAIW could not autonomously resolve this situation." |
| `FAILED` | FAILED (red) | "A system or tool error prevented completion. Review reliability panel for details." |
| `COMPLETED/ESCALATED/FAILED` | — | Historical badge shown; polling stopped |

### Expert Mode

When `expertMode=true`, the component also shows:
- `task_id`, `agent_id`, `sop_id`, `sop_version`
- `iteration` count
- `trace_id`, `context_snapshot_id`

---

## Backend Integration

### CopilotTurnResponse.agent_task_id

ACT turns now return an `agent_task_id` field linking the Copilot turn to the
exact `AgentTaskState` entry:

```json
{
  "intent": "ACT",
  "agent_task_id": "copilot-act-<uuid>",
  ...
}
```

OBSERVE_OUTCOME turns inherit the `agent_task_id` from the conversation's
`last_agent_task_id` to show the same task's final state.

### _register_copilot_act_task()

The `_register_copilot_act_task()` helper in `copilot/service.py` derives the
initial `AgentTaskStatus` from the governance outcome:

| Governance outcome | AgentTaskStatus |
|-------------------|-----------------|
| `REQUIRES_HUMAN_APPROVAL` | `WAITING_FOR_GOVERNANCE` |
| `APPROVED` + execution confirmed | `OBSERVING_OUTCOME` |
| `APPROVED` + mutation unknown | `WAITING_FOR_GOVERNANCE` |
| `REJECTED` / `ERROR` / `NOT_IMPLEMENTED` | `FAILED` |
| `STALE_STATE` / `CLARIFICATION_REQUIRED` | `ESCALATED` |

---

## Design Invariants

These invariants must never be violated:

1. **Governance pause semantics**: When status is `WAITING_FOR_GOVERNANCE`, the
   agent is NEVER shown as the execution authority. Governance is always the
   authority until approval is confirmed.

2. **No optimistic completion**: A SOP step or delegation is never marked complete
   until backend `AgentTaskState` confirms it.

3. **Execution confirmed ≠ Objective achieved**: `observe_execution_confirmed` and
   `observe_operational_improved` are separate independent fields. A confirmed
   execution does not imply the objective was met.

4. **No LLM narration**: Outcome narratives use deterministic string templates
   only — no LLM calls for outcome text.

5. **No autonomous event triggering**: UI updates come only from polling real
   `AgentTaskState`. No timers simulate state progression.

6. **Runtime-neutral language**: No LangGraph, ReAct, or deepagents terminology
   is exposed in operator-facing UI.

---

## Test Coverage

| File | Tests | Coverage |
|------|-------|----------|
| `tests/unit/test_copilot_task_linkage_ux1c.py` | 18 | Backend: agent_task_id linkage, governance outcome mapping, schema compatibility |
| `src/ui/web/src/__tests__/ux1c.test.tsx` | 40 | Frontend: all task states, governance/outcome/delegation panels, live polling |

---

## Related Documents

- `docs/ux/MAIW_AGENT_SOP_UX.md` — UX-1B agent/SOP progress baseline
- `docs/ux/MAIW_AUTHORITY_UX.md` — Authority state definitions
- `docs/ux/MAIW_INFORMATION_ARCHITECTURE.md` — Navigation and surface map
- `docs/audits/uiux/screenshots/ux1c/README.md` — Screenshot manifest
