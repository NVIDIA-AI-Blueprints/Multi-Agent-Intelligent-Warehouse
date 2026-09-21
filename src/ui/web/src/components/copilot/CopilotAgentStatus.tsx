/**
 * CopilotAgentStatus.tsx — UX-1C.3
 *
 * Compact agent task status panel shown inside CopilotDrawer when a turn
 * includes an agent_task_id. Shows what the agent is doing without exposing
 * chain-of-thought, LangGraph internals, or framework state.
 *
 * States handled:
 *   no task         → render nothing
 *   RUNNING         → "● Working" + current step
 *   WAITING_FOR_SUBAGENT → "Consulting specialist"
 *   WAITING_FOR_GOVERNANCE → "Waiting for governance"
 *   OBSERVING_OUTCOME → "Verifying outcome"
 *   COMPLETED       → "Completed" + historical badge
 *   ESCALATED       → "Needs attention"
 *   FAILED          → "Could not complete"
 *   unavailable     → "This agent task is no longer available"
 *
 * Architecture invariants:
 * - Runtime-neutral: no LangGraph/ReAct/deepagents terminology
 * - Only consumes AgentTaskView types from MAIW API
 * - Expert mode shows runtime_profile / agent_id (never internal node state)
 * - No chain_of_thought, scratchpad, or hidden reasoning exposed
 */

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { Box, Typography, Link } from '@mui/material';
import { AgentTaskView } from '../../types/agentTask';
import { agentTaskAPI } from '../../services/agentTaskAPI';
import {
  AGENT_TASK_STATUS_LABEL,
  getAgentDisplayName,
  getSopDisplayName,
} from '../../constants/agentTaskStates';

// ── Status colors ─────────────────────────────────────────────────────────────

const STATUS_COLOR: Record<string, string> = {
  PENDING:                '#8B949E',
  RUNNING:                '#58A6FF',
  WAITING_FOR_INPUT:      '#D29922',
  WAITING_FOR_SUBAGENT:   '#58A6FF',
  WAITING_FOR_GOVERNANCE: '#D29922',
  OBSERVING_OUTCOME:      '#3FB950',
  COMPLETED:              '#3FB950',
  ESCALATED:              '#D29922',
  FAILED:                 '#F85149',
};

// ── Compact status label per state ────────────────────────────────────────────

function getCompactStatusLabel(task: AgentTaskView): string {
  switch (task.status) {
    case 'RUNNING':
      return '● Working';
    case 'WAITING_FOR_SUBAGENT':
      return '◑ Consulting specialist';
    case 'WAITING_FOR_GOVERNANCE':
      return '⏸ Waiting for governance';
    case 'OBSERVING_OUTCOME':
      return '◎ Verifying outcome';
    case 'COMPLETED':
      return '✓ Completed';
    case 'ESCALATED':
      return '! Needs attention';
    case 'FAILED':
      return '✕ Could not complete';
    default:
      return AGENT_TASK_STATUS_LABEL[task.status] ?? task.status;
  }
}

function getCurrentStepLabel(task: AgentTaskView): string | null {
  if (!task.current_step_id) return null;
  const step = task.sop_steps.find(s => s.id === task.current_step_id);
  return step?.description ?? step?.id ?? task.current_step_id;
}

// ── Props ─────────────────────────────────────────────────────────────────────

export interface CopilotAgentStatusProps {
  /** Agent task ID from CopilotTurnResponse.agent_task_id. Null/undefined = render nothing. */
  agentTaskId: string | null | undefined;
  /** Expert mode: shows agent_id, task_id, sop_id, runtime, iteration, context_snapshot_id. */
  expertMode?: boolean;
  /** Called when "View activity" is clicked. Receives exact task_id. */
  onViewActivity?: (taskId: string) => void;
  /** Live polling interval in ms. Default 3000. Stops on terminal state. */
  pollIntervalMs?: number;
}

// ── Main component ────────────────────────────────────────────────────────────

const CopilotAgentStatus: React.FC<CopilotAgentStatusProps> = ({
  agentTaskId,
  expertMode = false,
  onViewActivity,
  pollIntervalMs = 3000,
}) => {
  const [task, setTask] = useState<AgentTaskView | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const cleanupRef = useRef<(() => void) | null>(null);

  const handleTaskUpdate = useCallback((updated: AgentTaskView) => {
    setTask(updated);
    setUnavailable(false);
  }, []);

  useEffect(() => {
    if (cleanupRef.current) {
      cleanupRef.current();
      cleanupRef.current = null;
    }

    if (!agentTaskId) {
      setTask(null);
      setUnavailable(false);
      return;
    }

    setUnavailable(false);

    // Initial fetch
    agentTaskAPI.getTask(agentTaskId).then(initial => {
      if (initial === null) {
        setUnavailable(true);
        return;
      }
      setTask(initial);
    }).catch(() => {
      setUnavailable(true);
    });

    // Subscribe to live updates via polling
    const cleanup = agentTaskAPI.subscribeToTask(
      agentTaskId,
      handleTaskUpdate,
      pollIntervalMs,
    );
    cleanupRef.current = cleanup;

    return () => {
      if (cleanupRef.current) {
        cleanupRef.current();
        cleanupRef.current = null;
      }
    };
  }, [agentTaskId, pollIntervalMs, handleTaskUpdate]);

  if (!agentTaskId) return null;

  if (unavailable) {
    return (
      <Box
        data-testid="copilot-agent-status-unavailable"
        sx={{
          mt: 1.5, p: 1.5,
          background: 'rgba(248, 81, 73, 0.06)',
          border: '1px solid rgba(248, 81, 73, 0.2)',
          borderRadius: '4px',
        }}
      >
        <Typography sx={{ fontSize: '0.7rem', color: '#8B949E', fontFamily: 'monospace' }}>
          This agent task is no longer available in the current runtime session.
        </Typography>
      </Box>
    );
  }

  if (!task) {
    return (
      <Box data-testid="copilot-agent-status-loading" sx={{ mt: 1.5, p: 1, opacity: 0.5 }}>
        <Typography sx={{ fontSize: '0.65rem', color: '#484F58', fontFamily: 'monospace' }}>
          Loading agent activity...
        </Typography>
      </Box>
    );
  }

  const statusColor = STATUS_COLOR[task.status] ?? '#8B949E';
  const statusLabel = getCompactStatusLabel(task);
  const currentStepLabel = getCurrentStepLabel(task);
  const agentDisplayName = getAgentDisplayName(task.agent_id);
  const sopDisplayName = getSopDisplayName(task.sop_id);
  const isTerminal = ['COMPLETED', 'ESCALATED', 'FAILED'].includes(task.status);
  const isActive = !isTerminal;

  return (
    <Box
      data-testid="copilot-agent-status"
      data-task-status={task.status}
      sx={{
        mt: 1.5, p: 1.5,
        background: 'rgba(22, 27, 34, 0.8)',
        border: `1px solid ${isActive ? 'rgba(88, 166, 255, 0.15)' : 'rgba(72, 79, 88, 0.3)'}`,
        borderRadius: '4px',
      }}
    >
      {/* Section header */}
      <Typography
        sx={{
          fontSize: '0.6rem', color: '#484F58', fontFamily: 'monospace',
          letterSpacing: '0.08em', textTransform: 'uppercase', mb: 0.75,
        }}
      >
        Agent Activity
        {isTerminal && (
          <Box
            component="span"
            data-testid="copilot-agent-status-historical-badge"
            sx={{
              ml: 1, px: 0.75, py: 0.1, fontSize: '0.55rem',
              background: 'rgba(72, 79, 88, 0.3)', borderRadius: '2px', color: '#8B949E',
            }}
          >
            HISTORICAL
          </Box>
        )}
      </Typography>

      {/* Agent name */}
      <Typography sx={{ fontSize: '0.75rem', color: '#E6EDF3', fontWeight: 600, lineHeight: 1.3 }}>
        {agentDisplayName}
      </Typography>

      {/* SOP name */}
      <Typography sx={{ fontSize: '0.65rem', color: '#8B949E', mb: 0.5 }}>
        {sopDisplayName}
      </Typography>

      {/* Status indicator */}
      <Typography
        data-testid={`copilot-agent-status-label-${task.status}`}
        sx={{ fontSize: '0.7rem', color: statusColor, fontFamily: 'monospace', fontWeight: 600 }}
      >
        {statusLabel}
      </Typography>

      {/* Current step (active tasks only) */}
      {currentStepLabel && isActive && (
        <Typography
          data-testid="copilot-agent-status-current-step"
          sx={{ fontSize: '0.65rem', color: '#8B949E', mt: 0.5 }}
        >
          Current: {currentStepLabel}
        </Typography>
      )}

      {/* WAITING_FOR_GOVERNANCE: governance pause message */}
      {task.status === 'WAITING_FOR_GOVERNANCE' && (
        <Typography
          data-testid="copilot-agent-status-governance-wait"
          sx={{ fontSize: '0.65rem', color: '#D29922', mt: 0.5, lineHeight: 1.4 }}
        >
          Agent work is paused while MAIW governance evaluates the proposed action.
        </Typography>
      )}

      {/* OBSERVING_OUTCOME: outcome observation phase */}
      {task.status === 'OBSERVING_OUTCOME' && (
        <Typography
          data-testid="copilot-agent-status-observing-outcome"
          sx={{ fontSize: '0.65rem', color: '#3FB950', mt: 0.5, lineHeight: 1.4 }}
        >
          MAIW is re-reading the warehouse state to determine whether the objective was achieved.
        </Typography>
      )}

      {/* ESCALATED: amber badge (distinct from FAILED which is red) */}
      {task.status === 'ESCALATED' && (
        <Typography
          data-testid="copilot-agent-status-escalated"
          sx={{ fontSize: '0.65rem', color: '#D29922', mt: 0.5 }}
        >
          Human attention required. MAIW has escalated this situation for review.
        </Typography>
      )}

      {/* FAILED: red badge (distinct from ESCALATED which is amber) */}
      {task.status === 'FAILED' && (
        <Typography
          data-testid="copilot-agent-status-failed"
          sx={{ fontSize: '0.65rem', color: '#F85149', mt: 0.5 }}
        >
          A system or tool error prevented completion. Review reliability panel for details.
        </Typography>
      )}

      {/* Expert mode: developer-visible IDs */}
      {expertMode && (
        <Box
          data-testid="copilot-agent-status-expert"
          sx={{ mt: 1, pt: 1, borderTop: '1px solid rgba(72, 79, 88, 0.2)' }}
        >
          {([
            ['task_id', task.task_id],
            ['agent_id', task.agent_id],
            ['sop_id', task.sop_id],
            ['sop_version', task.sop_version],
            ['iteration', String(task.iteration)],
            ['trace_id', task.trace_id ?? null],
            ['context_snapshot_id', task.context_snapshot_id ?? null],
          ] as [string, string | null][]).map(([label, value]) => value ? (
            <Box key={label} sx={{ display: 'flex', gap: 0.5, mb: 0.25 }}>
              <Typography sx={{ fontSize: '0.6rem', color: '#484F58', fontFamily: 'monospace' }}>
                {label}:
              </Typography>
              <Typography sx={{ fontSize: '0.6rem', color: '#8B949E', fontFamily: 'monospace', wordBreak: 'break-all' }}>
                {value}
              </Typography>
            </Box>
          ) : null)}
        </Box>
      )}

      {/* View activity link — links to exact task, not generic list */}
      {onViewActivity && (
        <Box sx={{ mt: 1 }}>
          <Link
            component="button"
            data-testid="copilot-agent-status-view-activity"
            onClick={() => onViewActivity(task.task_id)}
            sx={{
              fontSize: '0.65rem', color: '#58A6FF', textDecoration: 'none',
              cursor: 'pointer', background: 'none', border: 'none', p: 0,
              '&:hover': { textDecoration: 'underline' },
            }}
          >
            [View activity]
          </Link>
        </Box>
      )}
    </Box>
  );
};

export default CopilotAgentStatus;
