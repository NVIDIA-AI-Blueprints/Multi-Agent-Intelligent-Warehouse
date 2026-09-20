# MAIW Authority UX

> Version: UX-1A  
> Date: 2026-09-20  
> Status: Implemented

---

## Overview

The MAIW Authority Boundary separates AI reasoning from governed operational execution.
Every screen must make it unambiguous whether MAIW has:
1. Only recommended something (AI reasoning phase)
2. Governance authorized it (approval phase)
3. Actually executed a warehouse action (execution phase)

This document is the canonical reference for all status labels, component placement, and
semantic rules for the MAIW authority model.

---

## Lifecycle States

| State | Backend Source | Operator Label | Developer Label | When Shown |
|-------|---------------|----------------|-----------------|------------|
| `recommendation_ready` | agent assessment | AI Recommendation | RecommendedAction | PROPOSE stage — AI has recommended, nothing executed |
| `waiting_for_governance` | SSE/lifecycle | Waiting for Governance | WAITING_FOR_GOVERNANCE | Transition to DECIDE — governance evaluation in progress |
| `policy_approved` | APPROVED + no human gate | Approved by Policy | POLICY_APPROVED | DECIDE stage with APPROVED outcome, no requiresApproval |
| `human_approval_required` | REQUIRES_HUMAN_APPROVAL | Human Approval Required | REQUIRES_HUMAN_APPROVAL | APPROVE stage hero header |
| `approved` | APPROVED (decision status) | Approved | APPROVED | DECIDE stage card, CommandCenter status |
| `rejected` | REJECTED | Rejected | REJECTED | DECIDE stage card |
| `requires_fresh_state` | REQUIRES_FRESH_STATE | State Refresh Required | REQUIRES_FRESH_STATE | DECIDE stage card |
| `executing` | SSE EXECUTE event | Executing | EXECUTING | EXECUTE stage in-flight |
| `executed` | ActionExecutor success | Executed | EXECUTED | EXECUTE stage confirmed |
| `confirmed_executed` | ReliabilityEngine | Confirmed Executed | CONFIRMED_EXECUTED | OUTCOME/Reliability |
| `confirmed_not_executed` | ReliabilityEngine | Confirmed Not Executed | CONFIRMED_NOT_EXECUTED | OUTCOME/Reliability |
| `indeterminate` | ReliabilityEngine | Indeterminate | INDETERMINATE | OUTCOME/Reliability — requires operator follow-up |

---

## Canonical Rules

### Rule 1: `approved` ≠ `executed`

`approved` is the outcome of a governance decision (DecisionEngine APPROVED verdict).
`executed` is the outcome of ActionExecutor running and confirming the MCP call.

These states are **architecturally distinct** in MAIW v2. An approved proposal may not execute
if:
- No executor is wired (`approved_no_executor` path)
- The executor fails after approval
- The demo route returns the approval-only path

**Never display `approved` state as "Executed", "EXECUTED", or any execution synonym.**

The single source of truth is `src/ui/web/src/constants/authorityStates.ts`.

### Rule 2: policy_approved ≠ human_approved

`policy_approved` (Approved by Policy) means the DecisionEngine approved the proposal
without requiring human authorization. The operator did not approve this.

`human_approval_required` (Human Approval Required) means the DecisionEngine routed
to the human operator for explicit authorization.

Never conflate these. The policy_approved notice must clarify that governance policy
(not the AI) authorized the action.

### Rule 3: AI recommendation is not an operational decision

The PROPOSE stage shows MAIW's recommended action. Nothing has executed.
This must be explicitly stated via `PRE_EXECUTION_NOTICE` constant wherever
recommendations are displayed without a clear execution confirmation.

### Rule 4: Operator must always know whether execution has occurred

Before execution:
- `PRE_EXECUTION_NOTICE` = "No warehouse action has executed yet."
- AuthorityBoundary visible at recommendation/governance transition

After execution:
- EXECUTE stage shows `Executed` (not `Approved`)
- OUTCOME stage shows `Confirmed Executed` or `Confirmed Not Executed` or `Indeterminate`

---

## AuthorityBoundary Component

**Location**: `src/ui/web/src/components/AuthorityBoundary.tsx`

**Purpose**: Visual separator at the transition between AI recommendation and governed
operational execution.

**Props**:
- `compact?: boolean` — omits subtext (default: false)
- `testId?: string` — data-testid override (default: "authority-boundary")

**Visual specification**:
- Amber color `#D29922` for label text and rule lines (consistent with PENDING/governance color)
- Text-based — not color-only (accessible: `role="separator"`, `aria-label`)
- Compact size — a structural marker, not a hero graphic
- Text: `MAIW AUTHORITY BOUNDARY`
- Subtext: `AI can recommend. Operational actions require governance.`

**Placement**:
- ProposeStage: between the pre-execution notice and the proposal cards (marks end of AI reasoning)
- NOT on APPROVE stage (the boundary is already crossed; the stage is about governance authorization)
- NOT on EXECUTE or OUTCOME stages (post-boundary)

---

## Auto-Approval Semantics

When a LOW-risk proposal is auto-approved by policy (APPROVED without REQUIRES_HUMAN_APPROVAL):

**Visible sequence to operator:**
1. PROPOSE stage — "AI Recommendation" + "No warehouse action has executed yet." + AuthorityBoundary
2. DECIDE stage — "Approved by Policy" card + "This action did not require human authorization under current governance policy."
3. EXECUTE stage — "Executing..." → "Executed"

**Never allowed:**
- PROPOSE stage → EXECUTE stage without visible DECIDE/governance transition
- Displaying APPROVED as EXECUTED at any point

---

## Status Mapping Tests

Critical tests in `src/ui/web/src/__tests__/ux1a.test.tsx`:

```typescript
// These must always pass:
OPERATOR_LABELS.approved !== 'Executed'
OPERATOR_LABELS.approved !== 'EXECUTED'
OPERATOR_LABELS.executed !== OPERATOR_LABELS.approved
DECISION_STATUS_LABEL.approved !== 'EXECUTED'
DECISION_STATUS_LABEL.approved === 'Approved'
DEVELOPER_LABELS.approved === 'APPROVED'
DEVELOPER_LABELS.executed === 'EXECUTED'
DEVELOPER_LABELS.executed !== DEVELOPER_LABELS.approved
```

---

## Pre-Execution Indicators

| Surface | Indicator | Implementation |
|---------|-----------|----------------|
| ProposeStage header | "No warehouse action has executed yet." | `PRE_EXECUTION_NOTICE` constant in box component |
| ApproveStage pre-approval area | "No warehouse action has executed yet." | `PRE_EXECUTION_NOTICE` constant, visible until actioned |
| ProposeStage | AuthorityBoundary component | Between pre-execution notice and proposal cards |

---

## Approval Button Semantics

**Before UX-1A**: `APPROVE & EXECUTE` — conflated governance approval with ActionExecutor execution.

**After UX-1A**: `APPROVE ACTION` with sub-label "Governance approval — execution follows automatically".

**Rationale**: The operator's action is a governance authorization, not an execution command.
Execution is a consequence performed by ActionExecutor. The button label must represent
the operator's actual act (governance approval) without implying simultaneous execution.

**File**: `src/ui/web/src/components/demo/stages/ApproveStage.tsx`
**data-testid**: `approve-execute-button` (kept for backward test compatibility)
