/**
 * MAIW Agent Task API service — UX-1B.1.
 *
 * Wraps GET /api/v1/agent-tasks/* endpoints.
 * Also provides demo-mode synthetic task construction from AnalysisResult.
 *
 * Architecture invariant:
 * - Only calls MAIW API endpoints (/api/v1/agent-tasks/*)
 * - Does NOT import from deepagents, LangGraph, or provider packages
 */

import { AgentTaskView } from '../types/agentTask';
import { AnalysisResult } from './demoAPI';

// ── HTTP client (re-use the same base from demoAPI) ───────────────────────────

import axios from 'axios';

const http = axios.create({
  baseURL: '/api/v1',
  timeout: 15_000,
});

// ── API methods ───────────────────────────────────────────────────────────────

export const agentTaskAPI = {
  /** Get agent task state by ID. Returns null if not found (404). */
  async getTask(taskId: string): Promise<AgentTaskView | null> {
    try {
      const r = await http.get(`/agent-tasks/${taskId}`);
      return r.data as AgentTaskView;
    } catch (e: any) {
      if (e?.response?.status === 404) return null;
      throw e;
    }
  },

  /** List recent agent tasks. */
  async listTasks(): Promise<AgentTaskView[]> {
    const r = await http.get('/agent-tasks');
    return r.data as AgentTaskView[];
  },

  /**
   * Subscribe to live updates for a specific agent task.
   * Uses bounded polling (3-5s interval) since no task-specific SSE stream exists.
   * Polling stops automatically when task reaches a terminal state.
   *
   * UX-1C.2: Live AgentTaskState updates.
   *
   * @returns cleanup function — call to stop polling
   */
  subscribeToTask(
    taskId: string,
    onUpdate: (state: AgentTaskView) => void,
    intervalMs: number = 3000,
  ): () => void {
    const TERMINAL_STATUSES = new Set([
      'COMPLETED', 'ESCALATED', 'FAILED',
    ]);

    let active = true;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;

    const poll = async () => {
      if (!active) return;
      try {
        const r = await http.get(`/agent-tasks/${taskId}`);
        const state = r.data as AgentTaskView;
        if (active) {
          onUpdate(state);
          // Stop polling on terminal states
          if (TERMINAL_STATUSES.has(state.status)) {
            active = false;
            return;
          }
        }
      } catch (e: any) {
        // 404 = task no longer available (e.g., server restart)
        if (e?.response?.status === 404) {
          active = false;
          return;
        }
        // Other errors: log and continue polling
        console.warn('[agentTaskAPI] subscribeToTask poll error:', e?.message);
      }
      if (active) {
        timeoutId = setTimeout(poll, intervalMs);
      }
    };

    // Start polling
    poll();

    // Return cleanup function
    return () => {
      active = false;
      if (timeoutId !== null) {
        clearTimeout(timeoutId);
        timeoutId = null;
      }
    };
  },
};

// ── Demo-mode synthetic task construction ─────────────────────────────────────

/**
 * Wave Risk Resolution SOP steps (from agents/sops/operations_coordination/wave_risk_resolution.v1.yaml).
 * Inline for demo mode — no backend call needed.
 */
const WAVE_RISK_RESOLUTION_STEPS = [
  {
    id: 'establish_state',
    action: 'gather_operational_context',
    description: 'Assemble a fresh operational context snapshot from the current warehouse state.',
  },
  {
    id: 'diagnose',
    action: 'determine_primary_constraint',
    description: 'Determine whether the primary constraint is labor, wave sequencing, or equipment.',
  },
  {
    id: 'gather_specialist_evidence',
    action: 'consult_required_domains',
    description: 'Delegate bounded assessment to specialist agents based on the primary constraint.',
  },
  {
    id: 'generate_candidates',
    action: 'produce_candidate_interventions',
    description: 'Integrate specialist assessments and generate 1–3 candidate interventions.',
  },
  {
    id: 'compare',
    action: 'compare_candidates',
    description: 'Compare candidates by urgency, operational impact, risk, and reversibility.',
  },
  {
    id: 'recommend',
    action: 'select_recommendation',
    description: 'Select the top recommendation and emit a RecommendedAction.',
  },
  {
    id: 'submit',
    action: 'emit_recommended_action',
    description: 'Submit to governance and wait for authorization.',
  },
  {
    id: 'observe',
    action: 'evaluate_post_execution_state',
    description: 'Read the resulting warehouse state after governance and determine whether objective is met.',
  },
];

/**
 * Build a synthetic AgentTaskView for demo mode from an AnalysisResult.
 *
 * This is used in the REASON stage to show the agent activity UX when
 * the actual AgentTaskState is not returned directly by the analysis endpoint.
 *
 * The status is inferred from which lifecycle phases have completed.
 */
export function buildDemoAgentTask(
  analysisResult: AnalysisResult,
  currentStage: string,
): AgentTaskView {
  const traceId = analysisResult.trace_id;
  const assessment = analysisResult.assessment;
  const domains = assessment?.domains_affected ?? [];

  // Determine status from stage
  let status: string;
  let currentStepId: string | null = null;
  const completedSteps: string[] = [];

  switch (currentStage) {
    case 'OBSERVE':
      status = 'RUNNING';
      currentStepId = 'establish_state';
      break;
    case 'REASON':
      status = 'RUNNING';
      completedSteps.push('establish_state', 'diagnose');
      currentStepId = 'gather_specialist_evidence';
      break;
    case 'PROPOSE':
      status = 'RUNNING';
      completedSteps.push('establish_state', 'diagnose', 'gather_specialist_evidence', 'generate_candidates', 'compare');
      currentStepId = 'recommend';
      break;
    case 'DECIDE':
    case 'APPROVE':
      status = 'WAITING_FOR_GOVERNANCE';
      completedSteps.push('establish_state', 'diagnose', 'gather_specialist_evidence', 'generate_candidates', 'compare', 'recommend', 'submit');
      currentStepId = 'submit';
      break;
    case 'EXECUTE':
      status = 'OBSERVING_OUTCOME';
      completedSteps.push('establish_state', 'diagnose', 'gather_specialist_evidence', 'generate_candidates', 'compare', 'recommend', 'submit');
      currentStepId = 'observe';
      break;
    case 'OUTCOME':
      status = 'COMPLETED';
      completedSteps.push('establish_state', 'diagnose', 'gather_specialist_evidence', 'generate_candidates', 'compare', 'recommend', 'submit', 'observe');
      currentStepId = null;
      break;
    default:
      status = 'PENDING';
  }

  // Build delegation results from domains_affected
  const delegationResults = domains
    .filter((d: string) => ['labor', 'wave', 'equipment'].includes(d))
    .map((domain: string) => ({
      delegation_id: `${domain}-${traceId?.slice(0, 8) ?? 'demo'}`,
      child_task_id: `child-${domain}-${traceId?.slice(0, 8) ?? 'demo'}`,
      requesting_agent: 'operations_coordination',
      responding_agent: domain,
      status: 'COMPLETED',
      assessment: { summary: `${domain} assessment complete` },
      evidence: assessment?.facts_observed?.slice(0, 2) ?? [],
      candidate_action_count: 1,
      trace_id: traceId ?? null,
      context_snapshot_id: assessment?.snapshot_id ?? null,
    }));

  const objective = assessment?.recommendations?.[0]?.objective
    ?? assessment?.summary
    ?? 'Restore wave to on-track completion before carrier cutoff';

  return {
    task_id: `demo-task-${traceId?.slice(0, 12) ?? 'current'}`,
    agent_id: 'operations_coordination',
    sop_id: 'operations_coordination.wave_risk_resolution',
    sop_version: '1.0',
    objective,
    status,
    current_step_id: currentStepId,
    completed_steps: completedSteps,
    iteration: 1,
    conversation_id: null,
    copilot_turn_id: null,
    trace_id: traceId ?? null,
    context_snapshot_id: assessment?.snapshot_id ?? null,
    delegation_results: delegationResults,
    stop_reason: null,
    recommendation_id: null,
    sop_steps: WAVE_RISK_RESOLUTION_STEPS,
    created_at: assessment?.assessed_at ?? null,
    updated_at: assessment?.assessed_at ?? null,
  };
}
