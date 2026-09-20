/**
 * MAIW Post-Execution Semantic Layers — UX-1D
 *
 * Three distinct semantic layers covering what happens after an action is approved
 * and dispatched to the ActionExecutor. Never conflate these layers.
 *
 * Backend sources:
 *   - Execution state  → packages/maiw-execution/maiw_execution/reconciliation.py (ReconciliationOutcome)
 *   - Reliability state → same ReconciliationOutcome + ExecutionOutcome (wire: executed/unknown/failed)
 *   - AgentTask state  → packages/maiw-agents/maiw_agents/contracts/task.py (AgentTaskStatus)
 *   - Operational outcome → derived from pre/post state comparison in OBSERVE_OUTCOME copilot turn
 *
 * Key invariants:
 *   - EXECUTION != OUTCOME: execution confirmed does NOT imply objective achieved
 *   - UNKNOWN != FAILED: UNKNOWN means unconfirmed; FAILED means confirmed non-execution
 *   - INDETERMINATE means "cannot resolve" — never implies success or retry safety
 *   - Agent COMPLETED != execution CONFIRMED_EXECUTED — these are separate
 */

// ─── A. EXECUTION STATE ───────────────────────────────────────────────────────
// "Did the requested operation execute?"
// Wire values from ActionExecutor (lowercase): executed | no_op | deferred | conflict | unknown | failed

/** Operator-facing labels for the ActionExecutor's execution outcome. */
export const EXECUTION_STATE_LABEL: Record<string, string> = {
  executed:  'Execution confirmed',
  no_op:     'No operation performed',
  deferred:  'Awaiting approval',
  conflict:  'Blocked by state conflict',
  unknown:   'Execution confirmation unavailable',
  failed:    'Execution failed',
} as const;

/** One-sentence operator explanation for each execution state. */
export const EXECUTION_STATE_EXPLANATION: Record<string, string> = {
  executed:  'The ActionExecutor confirmed that the operation was dispatched.',
  no_op:     'The operation was idempotent — the warehouse was already in the correct state.',
  deferred:  'Execution is pending governance approval.',
  conflict:  'A state conflict blocked the operation. No mutation occurred.',
  unknown:   'The ActionExecutor could not confirm whether the operation occurred. MAIW will reconcile authoritative state before taking further action.',
  failed:    'The operation did not complete. No mutation occurred — it is safe to re-evaluate.',
} as const;

/** Styling tier for each execution state (for color/icon selection). */
export const EXECUTION_STATE_SEVERITY: Record<string, 'success' | 'warning' | 'attention' | 'error' | 'neutral'> = {
  executed:  'success',
  no_op:     'neutral',
  deferred:  'warning',
  conflict:  'attention',
  unknown:   'warning',   // NOT error — unconfirmed ≠ failed
  failed:    'error',
} as const;

// ─── B. RELIABILITY / RECONCILIATION STATE ────────────────────────────────────
// "Is MAIW certain that it executed?"
// Backend enum: ReconciliationOutcome in maiw_execution.reconciliation
// Values: confirmed_executed | confirmed_not_executed | indeterminate
// UX adds RECONCILING (in-progress) derived from SSE phase

/** Operator-facing labels for reconciliation/reliability outcomes. */
export const RELIABILITY_STATE_LABEL: Record<string, string> = {
  CONFIRMED_EXECUTED:     'Execution confirmed',
  CONFIRMED_NOT_EXECUTED: 'Confirmed not executed',
  INDETERMINATE:          'Operator review required',
  RECONCILING:            'Verifying execution',
  UNKNOWN:                'Execution confirmation unavailable',
} as const;

/** Operator explanation for each reliability state. */
export const RELIABILITY_STATE_EXPLANATION: Record<string, string> = {
  CONFIRMED_EXECUTED:     'MAIW verified from authoritative warehouse state that the operation occurred.',
  CONFIRMED_NOT_EXECUTED: 'MAIW verified that the requested operation did not occur. It is safe to re-evaluate.',
  INDETERMINATE:          'MAIW could not determine with confidence whether the action occurred. No automatic retry will be issued. Manual review is required.',
  RECONCILING:            'MAIW is comparing authoritative warehouse state. No operator action required.',
  UNKNOWN:                'MAIW has not yet confirmed execution. The system will reconcile authoritative state before taking further action.',
} as const;

/** "What happens next?" for each reliability state. */
export const RELIABILITY_NEXT_ACTION: Record<string, string> = {
  CONFIRMED_EXECUTED:     'MAIW will proceed to observe the operational outcome.',
  CONFIRMED_NOT_EXECUTED: 'MAIW will re-evaluate the recommendation with updated state.',
  INDETERMINATE:          'Operator review is required before MAIW can proceed.',
  RECONCILING:            'MAIW is reading authoritative state. No operator action required.',
  UNKNOWN:                'MAIW will re-read warehouse state before taking further action.',
} as const;

/** Whether operator must act for each reliability state. */
export const RELIABILITY_OPERATOR_ACTION_REQUIRED: Record<string, boolean> = {
  CONFIRMED_EXECUTED:     false,
  CONFIRMED_NOT_EXECUTED: false,
  INDETERMINATE:          true,
  RECONCILING:            false,
  UNKNOWN:                false,
} as const;

/** Styling tier for reliability state. UNKNOWN is warning (amber), not error (red). */
export const RELIABILITY_STATE_SEVERITY: Record<string, 'success' | 'warning' | 'attention' | 'error' | 'neutral'> = {
  CONFIRMED_EXECUTED:     'success',
  CONFIRMED_NOT_EXECUTED: 'neutral',
  INDETERMINATE:          'attention',
  RECONCILING:            'warning',
  UNKNOWN:                'warning',   // NOT error
} as const;

// ─── C. OPERATIONAL OUTCOME ───────────────────────────────────────────────────
// "Did the warehouse move toward the objective?"
// Derived in OBSERVE_OUTCOME copilot turn from pre/post state deltas + objective.
// No explicit backend enum — inferred from operational_improved flag + delta analysis.

/** Operator-facing labels for operational outcome. */
export const OUTCOME_STATE_LABEL: Record<string, string> = {
  OBJECTIVE_ACHIEVED:    'Objective achieved',
  PARTIALLY_ACHIEVED:    'Partially achieved',
  NOT_ACHIEVED:          'Objective not achieved',
  INCONCLUSIVE:          'Outcome inconclusive',
  PENDING:               'Outcome assessment pending',
} as const;

/** Operator explanation for each outcome state. */
export const OUTCOME_STATE_EXPLANATION: Record<string, string> = {
  OBJECTIVE_ACHIEVED:    'The warehouse state moved toward the stated operational objective.',
  PARTIALLY_ACHIEVED:    'Some but not all objective criteria were met. MAIW is reassessing.',
  NOT_ACHIEVED:          'The warehouse state did not improve toward the objective despite successful execution.',
  INCONCLUSIVE:          'Insufficient state data to determine whether the objective was achieved.',
  PENDING:               'Awaiting execution confirmation before assessing the operational outcome.',
} as const;

/** Styling tier for outcome. Green ONLY when objective achieved. */
export const OUTCOME_STATE_SEVERITY: Record<string, 'success' | 'warning' | 'attention' | 'error' | 'neutral'> = {
  OBJECTIVE_ACHIEVED:    'success',
  PARTIALLY_ACHIEVED:    'warning',   // amber — not green
  NOT_ACHIEVED:          'attention',
  INCONCLUSIVE:          'neutral',
  PENDING:               'neutral',
} as const;

// ─── D. AGENT TASK STATE ─────────────────────────────────────────────────────
// "What should the agent do next?" — reused from agentTaskStates.ts
// See src/ui/web/src/constants/agentTaskStates.ts for full vocabulary.
// Key states: OBSERVING_OUTCOME / COMPLETED / RUNNING / ESCALATED / FAILED
// AGENT COMPLETED ≠ EXECUTION CONFIRMED_EXECUTED (separate layers)

export const AGENT_TASK_TO_EXECUTION_RELATION: Record<string, string> = {
  OBSERVING_OUTCOME:      'Agent is awaiting execution confirmation and outcome data',
  COMPLETED:              'Agent task finished — check execution/outcome layers for operational result',
  FAILED:                 'Agent runtime error — separate from execution failure',
  ESCALATED:              'Human review required — separate from INDETERMINATE reliability',
} as const;

// ─── E. CANONICAL SEMANTIC MATRIX ────────────────────────────────────────────
// Maps operator questions to their source of truth and surface.

export const CANONICAL_SEMANTIC_MATRIX = [
  {
    question:      'Did it execute?',
    sourceOfTruth: 'ExecutionRecord (ActionExecutor)',
    operatorSurface: 'OutcomeSummary / ExecutionReliabilityPanel',
    developerSurface: 'DeveloperTrace',
  },
  {
    question:      'Are we certain it executed?',
    sourceOfTruth: 'ReconciliationOutcome (ReconciliationEngine)',
    operatorSurface: 'ExecutionReliabilityPanel',
    developerSurface: 'DeveloperTrace',
  },
  {
    question:      'Did it help?',
    sourceOfTruth: 'LIVE world state (OBSERVE_OUTCOME delta)',
    operatorSurface: 'OutcomeSummary',
    developerSurface: 'World / DeveloperTrace',
  },
  {
    question:      'Why did we act?',
    sourceOfTruth: 'Decision provenance (trace_id)',
    operatorSurface: 'Recommendation panel',
    developerSurface: 'DecisionGraph',
  },
  {
    question:      'What happens next?',
    sourceOfTruth: 'AgentTaskState',
    operatorSurface: 'AgentActivity / CopilotAgentStatus',
    developerSurface: 'DeveloperTrace',
  },
] as const;
