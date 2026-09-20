/**
 * MAIW Agent Task API types — UX-1B.
 *
 * These types mirror the backend AgentTaskView schema from
 * apps/api/maiw_api/routers/agent_tasks.py.
 *
 * ARCHITECTURE INVARIANT:
 * These types MUST only describe MAIW AgentTaskState API responses.
 * They MUST NOT import from or reference deepagents, LangGraph, or any AI
 * provider package. Frontend components depend only on these types.
 *
 * See also: constants/agentTaskStates.ts for status vocabulary.
 */

// ── SOP step view ─────────────────────────────────────────────────────────────

export interface SOPStepView {
  /** Stable step identifier within this SOP (e.g. "establish_state"). */
  id: string;
  /** Action type (e.g. "gather_operational_context"). */
  action: string;
  /** Human-readable step description from the SOP YAML. */
  description: string | null;
}

// ── SOP metadata view ─────────────────────────────────────────────────────────

export interface SOPMetadataView {
  sop_id: string;
  sop_version: string;
  agent: string;
  objective: string;
  /** "strict" | "adaptive" — maps to runtime profile. */
  runtime_profile: string;
  steps: SOPStepView[];
}

// ── Delegation result view ────────────────────────────────────────────────────

export interface DelegationResultView {
  /** Unique ID for this delegation. */
  delegation_id: string;
  /** Child task ID of the specialist agent. */
  child_task_id: string;
  /** Agent ID that requested the delegation. */
  requesting_agent: string;
  /** Agent ID that performed the assessment. */
  responding_agent: string;
  /** Terminal status of the child task (COMPLETED, ESCALATED, FAILED). */
  status: string;
  /** Structured domain assessment result. */
  assessment: Record<string, unknown>;
  /** Supporting evidence strings. */
  evidence: string[];
  /** Number of candidate actions proposed. */
  candidate_action_count: number;
  /** Developer field: trace ID. */
  trace_id: string | null;
  /** Developer field: context snapshot used by specialist. */
  context_snapshot_id: string | null;
}

// ── Agent task view ───────────────────────────────────────────────────────────

/**
 * AgentTaskState as returned by GET /api/v1/agent-tasks/{task_id}.
 *
 * NEVER contains: chain_of_thought, scratchpad, raw prompts,
 * LangGraph nodes, deepagents checkpoints, or framework internals.
 * The UI controls which fields to show based on expertMode.
 */
export interface AgentTaskView {
  // ── Core identity ──────────────────────────────────────────────────────────
  task_id: string;
  agent_id: string;
  sop_id: string;
  sop_version: string;
  /** Plain-English statement of what this task is trying to accomplish. */
  objective: string;

  // ── Lifecycle ──────────────────────────────────────────────────────────────
  /** Current status: PENDING | RUNNING | WAITING_FOR_INPUT | WAITING_FOR_SUBAGENT |
   *  WAITING_FOR_GOVERNANCE | OBSERVING_OUTCOME | COMPLETED | ESCALATED | FAILED */
  status: string;
  /** Currently active step ID, or null if between steps. */
  current_step_id: string | null;
  /** Ordered list of step IDs that have completed. */
  completed_steps: string[];
  /** Current iteration count (bounded by TerminationPolicy). */
  iteration: number;

  // ── Provenance (developer-facing) ─────────────────────────────────────────
  conversation_id: string | null;
  copilot_turn_id: string | null;
  trace_id: string | null;
  context_snapshot_id: string | null;

  // ── Delegation results ─────────────────────────────────────────────────────
  /** Specialist agent consultation results for this task. */
  delegation_results: DelegationResultView[];

  // ── Terminal fields ────────────────────────────────────────────────────────
  stop_reason: string | null;
  recommendation_id: string | null;

  // ── SOP step metadata ──────────────────────────────────────────────────────
  /** Step definitions from the SOP YAML, in order. Used by SOPProgress. */
  sop_steps: SOPStepView[];

  // ── Timestamps ────────────────────────────────────────────────────────────
  created_at: string | null;
  updated_at: string | null;
}

// ── Step display state ────────────────────────────────────────────────────────

/**
 * Computed display state for one SOP step, used by SOPProgress.
 */
export type SOPStepState =
  | 'completed'
  | 'current'
  | 'pending'
  | 'escalated'
  | 'governance_wait'
  | 'skipped';

export interface SOPStepDisplay {
  step: SOPStepView;
  state: SOPStepState;
}

/**
 * Compute display state for each SOP step given the current task state.
 */
export function computeSOPStepDisplays(
  task: AgentTaskView,
): SOPStepDisplay[] {
  const completedSet = new Set(task.completed_steps);
  const isGovernanceWait = task.status === 'WAITING_FOR_GOVERNANCE';
  const isEscalated = task.status === 'ESCALATED';

  return task.sop_steps.map((step) => {
    let state: SOPStepState;

    if (completedSet.has(step.id)) {
      // Completed — unless the task is now escalated after this step
      state = 'completed';
    } else if (step.id === task.current_step_id) {
      // Currently executing
      if (isGovernanceWait) {
        state = 'governance_wait';
      } else if (isEscalated) {
        state = 'escalated';
      } else {
        state = 'current';
      }
    } else {
      // Not yet reached
      state = 'pending';
    }

    return { step, state };
  });
}
