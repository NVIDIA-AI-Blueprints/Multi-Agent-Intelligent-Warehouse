/**
 * MAIW Agent Task Status Vocabulary — UX-1B
 *
 * These are the single source-of-truth labels for AgentTaskStatus lifecycle states.
 *
 * Key invariants:
 * - WAITING_FOR_GOVERNANCE → "Waiting for governance" (NOT "waiting to execute")
 * - Agents NEVER appear as execution authority
 * - No status maps to "Executing" (the agent does not execute)
 * - FAILED (system/runtime error) is visually distinct from ESCALATED (intentional human escalation)
 *
 * Backend enum values match maiw_agents.contracts.task.AgentTaskStatus exactly.
 * See packages/maiw-agents/maiw_agents/contracts/task.py
 */

// ── Operator-facing labels ────────────────────────────────────────────────────

/** Human-readable, plain-English labels for AgentTaskStatus. */
export const AGENT_TASK_STATUS_LABEL: Record<string, string> = {
  PENDING:                  'Preparing',
  RUNNING:                  'Working',
  WAITING_FOR_INPUT:        'Waiting for input',
  WAITING_FOR_SUBAGENT:     'Consulting specialist',
  WAITING_FOR_GOVERNANCE:   'Waiting for governance',
  OBSERVING_OUTCOME:        'Verifying outcome',
  COMPLETED:                'Completed',
  ESCALATED:                'Needs attention',
  FAILED:                   'Could not complete',
} as const;

// ── Developer-facing labels ───────────────────────────────────────────────────

/** Canonical backend enum values for developer/expert view. */
export const AGENT_TASK_STATUS_DEV_LABEL: Record<string, string> = {
  PENDING:                  'PENDING',
  RUNNING:                  'RUNNING',
  WAITING_FOR_INPUT:        'WAITING_FOR_INPUT',
  WAITING_FOR_SUBAGENT:     'WAITING_FOR_SUBAGENT',
  WAITING_FOR_GOVERNANCE:   'WAITING_FOR_GOVERNANCE',
  OBSERVING_OUTCOME:        'OBSERVING_OUTCOME',
  COMPLETED:                'COMPLETED',
  ESCALATED:                'ESCALATED',
  FAILED:                   'FAILED',
} as const;

// ── Terminal states ───────────────────────────────────────────────────────────

/** Statuses where the agent task lifecycle is complete. */
export const AGENT_TASK_TERMINAL_STATUSES = new Set([
  'COMPLETED',
  'ESCALATED',
  'FAILED',
]);

export function isTerminal(status: string): boolean {
  return AGENT_TASK_TERMINAL_STATUSES.has(status);
}

// ── Runtime profile labels ────────────────────────────────────────────────────

/**
 * Maps SOP runtime_profile → operator-friendly label.
 * "adaptive" = DeepAgentsRuntime; "strict" = MAIWDeterministicRuntime.
 * Framework internals are hidden behind expert disclosure.
 */
export const RUNTIME_PROFILE_LABEL: Record<string, string> = {
  adaptive: 'Adaptive runtime',
  strict:   'Strict SOP runtime',
} as const;

/** Developer labels for runtime profiles (shown in expert mode only). */
export const RUNTIME_PROFILE_DEV_LABEL: Record<string, string> = {
  adaptive: 'DeepAgentsRuntime',
  strict:   'MAIWDeterministicRuntime',
} as const;

// ── SOP step state icons ──────────────────────────────────────────────────────

/** Icon characters for SOP step states. NOT color-only — always paired with text. */
export const SOP_STEP_ICONS = {
  completed:       '✓',   // ✓
  current:         '→',   // →
  pending:         '○',   // ○
  escalated:       '!',
  governance_wait: '⏸',   // ⏸
  skipped:         '⊘',   // ⊘
} as const;

// ── Agent name display ────────────────────────────────────────────────────────

/** Maps canonical agent_id → operator-friendly display name. */
export const AGENT_DISPLAY_NAME: Record<string, string> = {
  operations_coordination: 'Operations Coordination Agent',
  labor:                   'Labor Agent',
  wave:                    'Wave Agent',
  equipment:               'Equipment Agent',
} as const;

export function getAgentDisplayName(agentId: string): string {
  return AGENT_DISPLAY_NAME[agentId] ?? agentId;
}

// ── SOP display name ──────────────────────────────────────────────────────────

/** Maps sop_id → operator-friendly display name. */
export const SOP_DISPLAY_NAME: Record<string, string> = {
  'operations_coordination.wave_risk_resolution': 'Wave Risk Resolution',
  'labor.labor_constraint_assessment':            'Labor Constraint Assessment',
  'wave.wave_risk_assessment':                    'Wave Risk Assessment',
} as const;

export function getSopDisplayName(sopId: string): string {
  return SOP_DISPLAY_NAME[sopId] ?? sopId;
}
