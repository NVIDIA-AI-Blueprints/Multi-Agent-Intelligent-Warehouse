# UX-1C Screenshot Manifest

> Feature: MAIW Live Agent Continuity + Copilot/Governance/Outcome Integration  
> Spec: UX-1C  
> Date: 2026-09-20  
> Branch: feat/ux-1c-live-agent-continuity

## Purpose

This directory holds reference screenshots for UX-1C acceptance verification.
Screenshots document the full operator journey from ACT turn through governance
through outcome — without switching screens.

## Required Captures

| ID | Surface | Trigger | What to capture |
|----|---------|---------|-----------------|
| `ux1c-01-copilot-act-task-linked.png` | CopilotDrawer | After an ACT turn with governance wait | CopilotAgentStatus showing WAITING_FOR_GOVERNANCE badge |
| `ux1c-02-copilot-act-governance-text.png` | CopilotDrawer | WAITING_FOR_GOVERNANCE state | "Agent work is paused while MAIW governance evaluates the proposed action." |
| `ux1c-03-copilot-observing-outcome.png` | CopilotDrawer | After governance approval → OBSERVING_OUTCOME | Status badge + outcome semantics text |
| `ux1c-04-copilot-completed.png` | CopilotDrawer | Task terminal: COMPLETED | Historical badge, no polling |
| `ux1c-05-copilot-escalated.png` | CopilotDrawer | Task terminal: ESCALATED | Amber badge, "Human attention required." |
| `ux1c-06-copilot-failed.png` | CopilotDrawer | Task terminal: FAILED | Red badge, "Review reliability panel." |
| `ux1c-07-copilot-expert-mode.png` | CopilotDrawer | Expert mode on, RUNNING state | task_id, agent_id, sop_id, sop_version, iteration, trace_id shown |
| `ux1c-08-agent-activity-governance-pause.png` | AgentActivity | WAITING_FOR_GOVERNANCE state | REVIEW GOVERNANCE button visible |
| `ux1c-09-agent-activity-indeterminate.png` | AgentActivity | INDETERMINATE executionStatus | Indeterminate execution panel |
| `ux1c-10-outcome-view-live-world.png` | AgentActivity OutcomeContinuation | OBSERVING_OUTCOME | VIEW LIVE WORLD button + outcome semantics text |
| `ux1c-11-delegation-running.png` | DelegationCard | Delegation RUNNING | Pulsing status icon, "Delegation in progress" subtitle |
| `ux1c-12-delegation-completed.png` | DelegationCard | Delegation COMPLETED | "Assessment delivered" subtitle |

## Acceptance Criteria Cross-Reference

Screenshots map to acceptance criteria in the UX-1C spec:

- AC-1 (task linkage): `ux1c-01`
- AC-2 (governance pause text): `ux1c-02`
- AC-3 (observing outcome): `ux1c-03`
- AC-4 (terminal state no polling): `ux1c-04`, `ux1c-05`, `ux1c-06`
- AC-5 (expert metadata): `ux1c-07`
- AC-6 (governance review button): `ux1c-08`
- AC-7 (indeterminate): `ux1c-09`
- AC-8 (view live world): `ux1c-10`
- AC-9 (delegation live states): `ux1c-11`, `ux1c-12`

## Status

Pending capture — run MAIW demo at `/demo` with a Wave Risk scenario to produce screenshots.
