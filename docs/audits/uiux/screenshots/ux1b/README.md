# UX-1B Screenshots Manifest

**Feature:** MAIW Agent/SOP Progress + Delegation Experience
**Branch:** feat/ux-1b-agent-sop-progress
**Date:** 2026-09-20

## Required Screenshots

The following 12 screenshots must be captured after deploying and running a demo scenario:

1. **ux1b-01-agent-running-compact.png**
   - State: REASON stage, analysis complete, AgentActivity compact panel visible
   - Shows: Operations Coordination Agent name, status "Working", procedure "Wave Risk Resolution v1.0", collapsed step view
   - Verify: No chain-of-thought, no LangGraph internals

2. **ux1b-02-sop-progress-steps.png**
   - State: REASON stage, AgentActivity expanded with SOPProgress
   - Shows: ✓ completed steps, → current step (highlighted), ○ pending steps
   - Verify: Step labels from SOP YAML descriptions, not hardcoded

3. **ux1b-03-delegation-operator-view.png**
   - State: REASON stage, DelegationSection showing Labor Agent consultation
   - Shows: "Labor Agent · Specialist consultation · Consulted to assess labor capacity"
   - Shows: Finding, Evidence items
   - Verify: No "subagent", "ReAct", "LangGraph" text

4. **ux1b-04-delegation-expert-view.png**
   - State: DelegationCard expanded in expert mode
   - Shows: child_task_id, parent_task_id, requesting_agent, responding_agent, context_snapshot_id
   - Shows: VIEW CONTEXT and VIEW DEVELOPER TRACE links

5. **ux1b-05-recommendation-generated.png**
   - State: PROPOSE stage with agentTask present
   - Shows: "Agent procedure complete — Recommendation generated" banner above proposals

6. **ux1b-06-waiting-governance.png**
   - State: DECIDE/APPROVE stage (WAITING_FOR_GOVERNANCE)
   - Shows: "Agent procedure complete", "Recommendation generated", "↓", AuthorityBoundary
   - Shows: "The agent has completed its recommendation and is waiting for MAIW governance."
   - Verify: NO "waiting to execute" text

7. **ux1b-07-observing-outcome.png**
   - State: EXECUTE stage (OBSERVING_OUTCOME)
   - Shows: "Governance complete", "↓", "Verifying outcome" box with ◎ icon

8. **ux1b-08-completed-state.png**
   - State: OUTCOME stage (COMPLETED)
   - Shows: "Governance complete", "↓", "✓ Objective achieved" (green box)
   - Shows: "Historical agent task" badge

9. **ux1b-09-escalated-state.png**
   - State: ESCALATED terminal state
   - Shows: "! Needs attention" (amber box, distinct from red FAILED)
   - Shows: stop_reason text, "Human review required to proceed."
   - Verify: Does NOT show red error styling

10. **ux1b-10-strict-sop-runtime.png**
    - State: AgentActivity in expert mode, strict runtime SOP
    - Shows: "Runtime: Strict SOP runtime" (operator)
    - Shows: "(MAIWDeterministicRuntime)" in parentheses (expert)

11. **ux1b-11-adaptive-runtime.png**
    - State: AgentActivity in expert mode, adaptive runtime (Deep Agents)
    - Shows: "Runtime: Adaptive runtime" (operator)
    - Shows: "(DeepAgentsRuntime)" in parentheses (expert)

12. **ux1b-12-expert-detail-all-fields.png**
    - State: AgentActivity in expert mode, all fields visible
    - Shows: task_id, agent_id, sop_id, sop_version, iteration, context_snapshot_id, trace_id, conversation_id, copilot_turn_id, stop_reason, recommendation_id, completed_steps

## Screenshot Instructions

1. Start the MAIW demo server: `docker compose up`
2. Open `http://localhost:3000/demo`
3. Start the "wave_risk" scenario
4. Click ANALYZE
5. Navigate through stages using the lifecycle rail
6. Toggle Expert mode using the Expert button (top-right)
7. Capture each screenshot as described above

## Status

All screenshots are PENDING — captured manually after deployment.
