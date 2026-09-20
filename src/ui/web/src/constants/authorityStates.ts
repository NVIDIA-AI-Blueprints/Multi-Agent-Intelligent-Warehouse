/**
 * MAIW Canonical Authority-State Vocabulary
 *
 * These are the single source-of-truth labels for every lifecycle state.
 * CRITICAL INVARIANT: approved !== executed — these are architecturally
 * distinct states and must never share a display label.
 *
 * - OPERATOR_LABELS: human-readable, plain-English, non-technical
 * - DEVELOPER_LABELS: canonical backend/architecture terms
 *
 * See docs/ux/MAIW_AUTHORITY_UX.md for the full authority-state model.
 */

// ── Operator-facing labels ────────────────────────────────────────────────────

export const OPERATOR_LABELS = {
  // AI reasoning phase
  recommendation_ready: 'AI Recommendation',
  waiting_for_governance: 'Waiting for Governance',

  // Governance phase
  policy_approved: 'Approved by Policy',
  human_approval_required: 'Human Approval Required',
  approved: 'Approved',             // NEVER 'Executed' — approved ≠ executed
  rejected: 'Rejected',
  deferred: 'Deferred',
  requires_fresh_state: 'State Refresh Required',

  // Execution phase
  execution_starting: 'Execution Starting',
  executing: 'Executing',
  executed: 'Executed',             // Only after ActionExecutor confirms
  failed: 'Failed',
  error: 'Error',

  // Reliability / reconciliation phase
  unknown: 'Outcome Unknown',
  reconciling: 'Reconciling',
  confirmed_executed: 'Confirmed Executed',
  confirmed_not_executed: 'Confirmed Not Executed',
  indeterminate: 'Indeterminate',
} as const;

export type OperatorStateKey = keyof typeof OPERATOR_LABELS;

// ── Developer-facing labels ───────────────────────────────────────────────────

export const DEVELOPER_LABELS = {
  recommendation_ready: 'RecommendedAction',
  waiting_for_governance: 'WAITING_FOR_GOVERNANCE',
  policy_approved: 'POLICY_APPROVED',
  human_approval_required: 'REQUIRES_HUMAN_APPROVAL',
  approved: 'APPROVED',             // DecisionEngine/Approval state — not execution
  rejected: 'REJECTED',
  deferred: 'DEFERRED',
  requires_fresh_state: 'REQUIRES_FRESH_STATE',
  execution_starting: 'EXECUTION_STARTING',
  executing: 'EXECUTING',
  executed: 'EXECUTED',             // ActionExecutor confirmed — distinct from APPROVED
  failed: 'FAILED',
  error: 'ERROR',
  unknown: 'UNKNOWN',
  reconciling: 'RECONCILING',
  confirmed_executed: 'CONFIRMED_EXECUTED',
  confirmed_not_executed: 'CONFIRMED_NOT_EXECUTED',
  indeterminate: 'INDETERMINATE',
} as const;

export type DeveloperStateKey = keyof typeof DEVELOPER_LABELS;

// ── Status label map for CommandCenter decision history display ───────────────
// Maps raw backend decision status strings → operator-facing display labels.
// This replaces the previous STATUS_LABEL object which incorrectly mapped
// approved → 'EXECUTED'. approved and executed are distinct MAIW states.

export const DECISION_STATUS_LABEL: Record<string, string> = {
  approved: OPERATOR_LABELS.approved,                               // 'Approved' (NOT 'EXECUTED')
  rejected: OPERATOR_LABELS.rejected,                               // 'Rejected'
  requires_human_approval: OPERATOR_LABELS.human_approval_required, // 'Human Approval Required'
  requires_fresh_state: OPERATOR_LABELS.requires_fresh_state,       // 'State Refresh Required'
  error: OPERATOR_LABELS.error,                                     // 'Error'
  unknown: OPERATOR_LABELS.unknown,                                 // 'Outcome Unknown'
};

// Status colors (unchanged — these were semantically correct)
export const DECISION_STATUS_COLOR: Record<string, string> = {
  approved: '#3FB950',
  rejected: '#F85149',
  requires_human_approval: '#D29922',
  requires_fresh_state: '#58A6FF',
  error: '#F85149',
  unknown: '#484F58',
};

export const DECISION_STATUS_DOT: Record<string, string> = {
  approved: '✓',
  rejected: '✕',
  requires_human_approval: '●',
  requires_fresh_state: '◌',
  error: '✕',
  unknown: '—',
};

// ── Pre-execution authority text ──────────────────────────────────────────────

/** Shown in recommendation and governance stages before any execution occurs. */
export const PRE_EXECUTION_NOTICE =
  'No warehouse action has executed yet.';

/** Shown after policy auto-approval (no human gate). */
export const POLICY_APPROVED_NOTICE =
  'This action did not require human authorization under current governance policy.';

/** Authority boundary label. */
export const AUTHORITY_BOUNDARY_LABEL = 'MAIW AUTHORITY BOUNDARY';

/** Authority boundary subtext. */
export const AUTHORITY_BOUNDARY_SUBTEXT =
  'AI can recommend. Operational actions require governance.';
