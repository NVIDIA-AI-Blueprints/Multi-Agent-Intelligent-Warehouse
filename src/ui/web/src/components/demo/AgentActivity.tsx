/**
 * AgentActivity — UX-1B.2
 *
 * Shows what agent is working, what it's trying to accomplish, and
 * where it is in its SOP procedure. Integrates with SOPProgress.
 *
 * Compact operator view (for REASON stage):
 *   Operations Coordination Agent
 *   Objective: Recover Wave 17 before carrier cutoff
 *   Procedure: Wave Risk Resolution v1
 *   Status: Working
 *   [SOPProgress embedded]
 *
 * Expert disclosure (expertMode=true) adds:
 *   agent_id, task_id, sop_id, sop_version, runtime, iteration,
 *   context_snapshot_id, stop_reason, completed_step_ids
 *
 * STOP condition: "Waiting for governance" state shows AuthorityBoundary.
 * The agent is NEVER shown as execution authority.
 *
 * Architecture invariant:
 * - Does NOT import from deepagents, LangGraph, or provider packages
 * - Only consumes MAIW AgentTaskView types
 */

import React, { useState } from 'react';
import { Box, Typography, Collapse } from '@mui/material';
import { AgentTaskView } from '../../types/agentTask';
import {
  AGENT_TASK_STATUS_LABEL,
  AGENT_TASK_STATUS_DEV_LABEL,
  RUNTIME_PROFILE_LABEL,
  RUNTIME_PROFILE_DEV_LABEL,
  getAgentDisplayName,
  getSopDisplayName,
} from '../../constants/agentTaskStates';
import SOPProgress from './SOPProgress';
import AuthorityBoundary from '../AuthorityBoundary';

// ── Status indicator ──────────────────────────────────────────────────────────

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

const STATUS_DOT: Record<string, string> = {
  PENDING:                '○',
  RUNNING:                '●',
  WAITING_FOR_INPUT:      '◐',
  WAITING_FOR_SUBAGENT:   '◑',
  WAITING_FOR_GOVERNANCE: '⏸',
  OBSERVING_OUTCOME:      '◎',
  COMPLETED:              '✓',
  ESCALATED:              '!',
  FAILED:                 '✕',
};

// ── Freshness indicator ───────────────────────────────────────────────────────

function FreshnessTag({ updatedAt }: { updatedAt: string | null }) {
  if (!updatedAt) return null;
  const age = Date.now() - new Date(updatedAt).getTime();
  const ageStr =
    age < 5000 ? 'just now' :
    age < 60000 ? `${Math.round(age / 1000)}s ago` :
    `${Math.round(age / 60000)}m ago`;
  const isStale = age > 120000; // > 2 min

  return (
    <Typography
      data-testid="freshness-tag"
      sx={{
        fontFamily: 'monospace',
        fontSize: '0.5rem',
        color: isStale ? '#D29922' : '#484F58',
        letterSpacing: '0.04em',
      }}
    >
      {isStale ? `stale · ${ageStr}` : ageStr}
    </Typography>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyAgentActivity() {
  return (
    <Box
      data-testid="agent-activity-empty"
      sx={{
        py: 1,
        px: 1,
        background: '#0D1117',
        border: '1px solid #21262D',
        borderRadius: '5px',
      }}
    >
      <Typography
        sx={{
          fontFamily: 'monospace',
          fontSize: '0.6rem',
          color: '#484F58',
        }}
      >
        No agent procedure is active
      </Typography>
    </Box>
  );
}

// ── Historical badge ──────────────────────────────────────────────────────────

function HistoricalBadge({ task }: { task: AgentTaskView }) {
  if (!['COMPLETED', 'ESCALATED', 'FAILED'].includes(task.status)) return null;
  return (
    <Box
      data-testid="historical-badge"
      sx={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 0.5,
        background: '#161B22',
        border: '1px solid #30363D',
        borderRadius: '4px',
        px: '6px',
        py: '2px',
        mb: 0.5,
      }}
    >
      <Typography
        sx={{
          fontFamily: 'monospace',
          fontSize: '0.5rem',
          color: '#484F58',
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
        }}
      >
        Historical agent task
      </Typography>
    </Box>
  );
}

// ── Governance transition ─────────────────────────────────────────────────────

function GovernanceTransition() {
  return (
    <Box data-testid="governance-transition" sx={{ my: 1 }}>
      <Typography
        sx={{
          fontFamily: 'monospace',
          fontSize: '0.6rem',
          color: '#8B949E',
          mb: 0.75,
        }}
      >
        Agent procedure complete
      </Typography>
      <Typography
        sx={{
          fontFamily: 'monospace',
          fontSize: '0.6rem',
          color: '#8B949E',
          mb: 0.75,
        }}
      >
        Recommendation generated
      </Typography>
      <Box sx={{ display: 'flex', justifyContent: 'center', mb: 0.75 }}>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#30363D' }}>
          ↓
        </Typography>
      </Box>
      <AuthorityBoundary />
      <Typography
        sx={{
          fontFamily: 'monospace',
          fontSize: '0.6rem',
          color: '#8B949E',
          mt: 0.75,
          textAlign: 'center',
        }}
      >
        The agent has completed its recommendation and is waiting for MAIW governance.
      </Typography>
    </Box>
  );
}

// ── Outcome continuation ──────────────────────────────────────────────────────

function OutcomeContinuation({ task, onViewLiveWorld }: { task: AgentTaskView; onViewLiveWorld?: () => void }) {
  const isCompleted = task.status === 'COMPLETED';
  const isEscalated = task.status === 'ESCALATED';
  const isFailed = task.status === 'FAILED';

  return (
    <Box data-testid="outcome-continuation" sx={{ mt: 1 }}>
      <Box sx={{ display: 'flex', justifyContent: 'center', mb: 0.75 }}>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#30363D' }}>
          ↓
        </Typography>
      </Box>
      <Typography
        sx={{
          fontFamily: 'monospace',
          fontSize: '0.6rem',
          color: '#8B949E',
          mb: 0.5,
          textAlign: 'center',
        }}
      >
        Governance complete
      </Typography>
      <Box sx={{ display: 'flex', justifyContent: 'center', mb: 0.75 }}>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#30363D' }}>
          ↓
        </Typography>
      </Box>

      {isCompleted && (
        <Box
          data-testid="outcome-completed"
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            background: '#0d2b0d',
            border: '1px solid #3FB95044',
            borderRadius: '4px',
            px: 1.5,
            py: 0.75,
          }}
        >
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#3FB950', fontWeight: 700 }}>
            ✓
          </Typography>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#3FB950' }}>
            Objective achieved
          </Typography>
        </Box>
      )}

      {isEscalated && (
        <Box
          data-testid="outcome-escalated"
          sx={{
            background: '#1a1200',
            border: '1px solid #D2992244',
            borderRadius: '4px',
            px: 1.5,
            py: 0.75,
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#D29922', fontWeight: 700 }}>
              !
            </Typography>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#D29922', fontWeight: 600 }}>
              Needs attention
            </Typography>
          </Box>
          {task.stop_reason && (
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#8B949E' }}>
              {task.stop_reason}
            </Typography>
          )}
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#8B949E', mt: 0.5 }}>
            Human review required to proceed.
          </Typography>
        </Box>
      )}

      {isFailed && (
        <Box
          data-testid="outcome-failed"
          sx={{
            background: '#1a0000',
            border: '1px solid #F8514944',
            borderRadius: '4px',
            px: 1.5,
            py: 0.75,
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#F85149', fontWeight: 700 }}>
              ✕
            </Typography>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#F85149', fontWeight: 600 }}>
              Could not complete
            </Typography>
          </Box>
          {task.stop_reason && (
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#8B949E' }}>
              {task.stop_reason}
            </Typography>
          )}
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#8B949E', mt: 0.5 }}>
            A system or tool error prevented completion.
          </Typography>
        </Box>
      )}

      {task.status === 'OBSERVING_OUTCOME' && (
        <Box
          data-testid="outcome-observing"
          sx={{
            background: '#0d1117',
            border: '1px solid #21262D',
            borderRadius: '4px',
            px: 1.5,
            py: 0.75,
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#3FB950' }}>
              ◎
            </Typography>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#3FB950', fontWeight: 600 }}>
              Verifying outcome
            </Typography>
          </Box>
          <Typography
            data-testid="outcome-observing-semantics"
            sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#8B949E', lineHeight: 1.4, mb: 0.75 }}
          >
            MAIW is re-reading the warehouse state to determine whether the objective was achieved.
          </Typography>
          {onViewLiveWorld && (
            <Box
              component="button"
              data-testid="outcome-view-live-world"
              onClick={onViewLiveWorld}
              sx={{
                background: 'transparent', border: '1px solid #21262D',
                borderRadius: '3px', px: 1, py: 0.375,
                fontFamily: 'monospace', fontSize: '0.62rem',
                color: '#8B949E', cursor: 'pointer',
                '&:hover': { color: '#58A6FF', borderColor: '#58A6FF44' },
              }}
            >
              [VIEW LIVE WORLD]
            </Box>
          )}
        </Box>
      )}
    </Box>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export interface AgentActivityProps {
  /** The agent task to display. Pass null/undefined for empty state. */
  task: AgentTaskView | null | undefined;
  /** Show developer fields (agent_id, task_id, sop_id, etc.) */
  expertMode?: boolean;
  /** Compact display for REASON stage integration */
  compact?: boolean;
  // UX-1C.4: Governance and world navigation callbacks
  /** Called when operator clicks [REVIEW GOVERNANCE] — receives exact proposal_id */
  onReviewGovernance?: (pendingApprovalId: string) => void;
  /** Called when operator clicks [VIEW LIVE WORLD] */
  onViewLiveWorld?: () => void;
  /** Pending approval ID linked to this task — used for REVIEW GOVERNANCE link */
  pendingApprovalId?: string | null;
  /** Execution status from ActionExecutor — for INDETERMINATE/RECONCILING */
  executionStatus?: string | null;
}

const AgentActivity: React.FC<AgentActivityProps> = ({
  task,
  expertMode = false,
  compact = false,
  onReviewGovernance,
  onViewLiveWorld,
  pendingApprovalId,
  executionStatus,
}) => {
  const [expanded, setExpanded] = useState(!compact);

  if (!task) {
    return <EmptyAgentActivity />;
  }

  const status = task.status;
  const statusLabel = AGENT_TASK_STATUS_LABEL[status] ?? status;
  const statusColor = STATUS_COLOR[status] ?? '#484F58';
  const statusDot = STATUS_DOT[status] ?? '●';
  const agentName = getAgentDisplayName(task.agent_id);
  const sopName = getSopDisplayName(task.sop_id);
  const runtimeLabel = task.sop_steps.length > 0
    ? RUNTIME_PROFILE_LABEL['strict'] // default until SOP metadata includes runtime_profile
    : RUNTIME_PROFILE_LABEL['strict'];

  const isGovernanceWait = status === 'WAITING_FOR_GOVERNANCE';
  const isOutcomeState = ['OBSERVING_OUTCOME', 'COMPLETED', 'ESCALATED', 'FAILED'].includes(status);
  const isHistorical = ['COMPLETED', 'ESCALATED', 'FAILED'].includes(status);

  return (
    <Box
      data-testid="agent-activity"
      sx={{
        background: '#0D1117',
        border: '1px solid #21262D',
        borderRadius: '5px',
        overflow: 'hidden',
      }}
    >
      {/* Card header */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          px: 1.5,
          py: '8px',
          borderBottom: '1px solid #21262D',
          background: '#161B22',
          cursor: compact ? 'pointer' : 'default',
        }}
        onClick={compact ? () => setExpanded((e) => !e) : undefined}
        onKeyDown={compact
          ? (e) => { if (e.key === 'Enter' || e.key === ' ') setExpanded((v) => !v); }
          : undefined}
        tabIndex={compact ? 0 : undefined}
        role={compact ? 'button' : undefined}
        aria-expanded={compact ? expanded : undefined}
        aria-label={compact ? `Agent activity: ${agentName}` : undefined}
      >
        {/* Status dot */}
        <Typography
          aria-hidden="true"
          sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: statusColor, flexShrink: 0 }}
        >
          {statusDot}
        </Typography>

        {/* Agent name */}
        <Typography
          sx={{
            fontFamily: 'monospace',
            fontSize: '0.65rem',
            fontWeight: 700,
            color: '#C9D1D9',
            flex: 1,
          }}
        >
          {agentName}
        </Typography>

        {/* Status label */}
        <Typography
          aria-label={`Status: ${statusLabel}`}
          sx={{
            fontFamily: 'monospace',
            fontSize: '0.55rem',
            color: statusColor,
            letterSpacing: '0.06em',
          }}
        >
          {statusLabel}
        </Typography>

        {compact && (
          <Typography aria-hidden="true" sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58' }}>
            {expanded ? '▲' : '▼'}
          </Typography>
        )}
      </Box>

      {/* Historical badge */}
      {isHistorical && (
        <Box sx={{ px: 1.5, pt: 1 }}>
          <HistoricalBadge task={task} />
        </Box>
      )}

      {/* Body */}
      <Collapse in={!compact || expanded}>
        <Box sx={{ px: 1.5, py: 1 }}>
          {/* Objective */}
          <Box sx={{ mb: 1 }}>
            <Typography
              sx={{
                fontFamily: 'monospace',
                fontSize: '0.5rem',
                color: '#484F58',
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                mb: 0.25,
              }}
            >
              Objective
            </Typography>
            <Typography
              sx={{
                fontFamily: 'monospace',
                fontSize: '0.62rem',
                color: '#8B949E',
                lineHeight: 1.4,
              }}
            >
              {task.objective}
            </Typography>
          </Box>

          {/* Procedure */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
            <Typography
              sx={{
                fontFamily: 'monospace',
                fontSize: '0.5rem',
                color: '#484F58',
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                flexShrink: 0,
              }}
            >
              Procedure
            </Typography>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#8B949E' }}>
              {sopName} v{task.sop_version}
            </Typography>
          </Box>

          {/* Runtime */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
            <Typography
              sx={{
                fontFamily: 'monospace',
                fontSize: '0.5rem',
                color: '#484F58',
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                flexShrink: 0,
              }}
            >
              Runtime
            </Typography>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#8B949E' }}>
              {runtimeLabel}
            </Typography>
            {expertMode && (
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#30363D' }}>
                ({RUNTIME_PROFILE_DEV_LABEL['strict']})
              </Typography>
            )}
          </Box>

          {/* Freshness */}
          <FreshnessTag updatedAt={task.updated_at} />

          {/* Expert fields */}
          {expertMode && (
            <Box
              data-testid="expert-detail"
              sx={{
                mt: 1,
                pt: 1,
                borderTop: '1px solid #21262D',
              }}
            >
              <Typography
                sx={{
                  fontFamily: 'monospace',
                  fontSize: '0.5rem',
                  color: '#484F58',
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                  mb: 0.5,
                }}
              >
                Developer detail
              </Typography>
              {[
                ['task_id', task.task_id],
                ['agent_id', task.agent_id],
                ['sop_id', task.sop_id],
                ['sop_version', task.sop_version],
                ['iteration', String(task.iteration)],
                ['context_snapshot_id', task.context_snapshot_id ?? '—'],
                ['trace_id', task.trace_id ?? '—'],
                ['conversation_id', task.conversation_id ?? '—'],
                ['copilot_turn_id', task.copilot_turn_id ?? '—'],
                ['stop_reason', task.stop_reason ?? '—'],
                ['recommendation_id', task.recommendation_id ?? '—'],
                ['completed_steps', task.completed_steps.join(', ') || '—'],
              ].map(([k, v]) => (
                <Box key={k} sx={{ display: 'flex', gap: 1, mb: 0.125 }}>
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#484F58', flexShrink: 0, width: '10rem' }}>
                    {k}
                  </Typography>
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#8B949E', wordBreak: 'break-all' }}>
                    {v}
                  </Typography>
                </Box>
              ))}
            </Box>
          )}

          {/* Governance handoff — WAITING_FOR_GOVERNANCE */}
          {isGovernanceWait && (
            <>
              <GovernanceTransition />
              {/* UX-1C.4: REVIEW GOVERNANCE link to exact proposal */}
              {pendingApprovalId && onReviewGovernance && (
                <Box sx={{ mt: 0.75 }}>
                  <Box
                    component="button"
                    data-testid="agent-activity-review-governance"
                    onClick={() => onReviewGovernance(pendingApprovalId)}
                    sx={{
                      background: 'rgba(210, 153, 34, 0.08)',
                      border: '1px solid rgba(210, 153, 34, 0.3)',
                      borderRadius: '4px',
                      px: 1.5, py: 0.75,
                      fontFamily: 'monospace', fontSize: '0.65rem',
                      color: '#D29922', cursor: 'pointer',
                      '&:hover': { background: 'rgba(210, 153, 34, 0.15)' },
                    }}
                  >
                    [REVIEW GOVERNANCE]
                  </Box>
                </Box>
              )}
              {/* INDETERMINATE / RECONCILING execution status */}
              {executionStatus === 'INDETERMINATE' && (
                <Box
                  data-testid="agent-activity-indeterminate"
                  sx={{
                    mt: 0.75, p: 1.25,
                    background: 'rgba(248, 81, 73, 0.06)',
                    border: '1px solid rgba(248, 81, 73, 0.2)',
                    borderRadius: '4px',
                  }}
                >
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#F85149', fontWeight: 600, mb: 0.5 }}>
                    INDETERMINATE
                  </Typography>
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#8B949E', lineHeight: 1.4 }}>
                    MAIW could not determine with confidence whether the action occurred.
                    No automatic retry will be issued. Operator review is required.
                  </Typography>
                </Box>
              )}
              {executionStatus === 'UNKNOWN' && (
                <Box
                  data-testid="agent-activity-reconciling"
                  sx={{
                    mt: 0.75, p: 1.25,
                    background: 'rgba(210, 153, 34, 0.06)',
                    border: '1px solid rgba(210, 153, 34, 0.2)',
                    borderRadius: '4px',
                  }}
                >
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#D29922', mb: 0.5 }}>
                    Execution status is uncertain.
                  </Typography>
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#8B949E', lineHeight: 1.4 }}>
                    MAIW is reconciling before evaluating the outcome.
                  </Typography>
                </Box>
              )}
            </>
          )}

          {/* Outcome continuation */}
          {isOutcomeState && !isGovernanceWait && <OutcomeContinuation task={task} onViewLiveWorld={onViewLiveWorld} />}

          {/* SOP Progress */}
          {task.sop_steps.length > 0 && !isGovernanceWait && !isOutcomeState && (
            <Box sx={{ mt: 1, pt: 1, borderTop: '1px solid #21262D' }}>
              <Typography
                sx={{
                  fontFamily: 'monospace',
                  fontSize: '0.5rem',
                  color: '#484F58',
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                  mb: 0.5,
                }}
              >
                Procedure progress
              </Typography>
              <SOPProgress task={task} expertMode={expertMode} />
            </Box>
          )}
        </Box>
      </Collapse>
    </Box>
  );
};

export default AgentActivity;
