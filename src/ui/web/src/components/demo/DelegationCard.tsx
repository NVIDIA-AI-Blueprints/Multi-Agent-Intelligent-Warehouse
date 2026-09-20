/**
 * DelegationCard — UX-1B.3
 *
 * Shows a specialist agent consultation in operator-friendly language.
 * Never says "subagent", "ReAct", "LangGraph", "checkpoint", or "tool invocation".
 *
 * Operator view:
 *   Labor Agent
 *   Consulted to assess labor capacity
 *
 *   Finding:
 *   Labor is the dominant constraint.
 *
 *   Evidence:
 *   5 pending tasks, 4 idle workers, cutoff in 42 min
 *
 * Expert view adds:
 *   parent_task_id, child_task_id, requesting/responding agent IDs,
 *   context_snapshot_id, status, timestamps, candidate_action_count
 *
 * Delegation chain:
 *   Operations Coordination Agent
 *      ├── Labor Agent ✓
 *      └── Wave Agent ✓
 *
 * Architecture invariant:
 * - Does NOT import from deepagents, LangGraph, or provider packages
 * - Only consumes MAIW DelegationResultView types
 */

import React, { useState } from 'react';
import { Box, Typography, Collapse } from '@mui/material';
import { AgentTaskView, DelegationResultView } from '../../types/agentTask';
import { getAgentDisplayName } from '../../constants/agentTaskStates';

// ── Specialist status indicator ───────────────────────────────────────────────

const SPECIALIST_STATUS_ICON: Record<string, string> = {
  COMPLETED: '✓',
  ESCALATED: '!',
  FAILED:    '✕',
  RUNNING:   '●',
};

const SPECIALIST_STATUS_COLOR: Record<string, string> = {
  COMPLETED: '#3FB950',
  ESCALATED: '#D29922',
  FAILED:    '#F85149',
  RUNNING:   '#58A6FF',
};

// ── Operator-friendly reason text ─────────────────────────────────────────────

function getConsultReason(result: DelegationResultView): string {
  const agent = result.responding_agent;
  if (agent === 'labor') return 'to assess labor capacity';
  if (agent === 'wave') return 'to assess wave sequencing';
  if (agent === 'equipment') return 'to assess equipment availability';
  return 'to provide specialist assessment';
}

function getAssessmentSummary(result: DelegationResultView): string | null {
  const a = result.assessment;
  if (!a || Object.keys(a).length === 0) return null;
  // Try common assessment summary fields
  const summary =
    (a['summary'] as string) ??
    (a['primary_constraint'] as string) ??
    (a['finding'] as string) ??
    null;
  if (summary) return String(summary);
  // Fall back to stringifying if short
  const str = JSON.stringify(a);
  if (str.length < 120) return str;
  return null;
}

// ── Single delegation card ────────────────────────────────────────────────────

interface SingleDelegationCardProps {
  result: DelegationResultView;
  parentTaskId: string;
  expertMode: boolean;
}

function SingleDelegationCard({ result, parentTaskId, expertMode }: SingleDelegationCardProps) {
  const [expanded, setExpanded] = useState(false);
  const agentName = getAgentDisplayName(result.responding_agent);
  const statusIcon = SPECIALIST_STATUS_ICON[result.status] ?? '●';
  const statusColor = SPECIALIST_STATUS_COLOR[result.status] ?? '#484F58';
  const consultReason = getConsultReason(result);
  const assessmentSummary = getAssessmentSummary(result);

  return (
    <Box
      data-testid="delegation-card"
      sx={{
        background: '#0D1117',
        border: '1px solid #21262D',
        borderRadius: '5px',
        overflow: 'hidden',
        mb: 1,
      }}
    >
      {/* Header */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          px: 1.5,
          py: '8px',
          borderBottom: '1px solid #21262D',
          background: '#161B22',
          cursor: 'pointer',
        }}
        onClick={() => setExpanded((e) => !e)}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setExpanded((v) => !v); }}
        tabIndex={0}
        role="button"
        aria-expanded={expanded}
        aria-label={`Specialist consultation: ${agentName}`}
      >
        {/* Status icon — not color-only */}
        <Typography
          aria-hidden="true"
          sx={{
            fontFamily: 'monospace', fontSize: '0.65rem', color: statusColor, flexShrink: 0,
            // UX-1C.2: pulse animation for RUNNING live state
            ...(result.status === 'RUNNING' && {
              animation: 'pulse 1s ease-in-out infinite',
              '@keyframes pulse': { '0%, 100%': { opacity: 0.4 }, '50%': { opacity: 1 } },
            }),
          }}
        >
          {statusIcon}
        </Typography>

        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography
            sx={{
              fontFamily: 'monospace',
              fontSize: '0.65rem',
              fontWeight: 700,
              color: '#C9D1D9',
            }}
          >
            {agentName}
          </Typography>
          <Typography
            data-testid={`delegation-status-${result.status.toLowerCase()}`}
            sx={{
              fontFamily: 'monospace',
              fontSize: '0.55rem',
              color: result.status === 'RUNNING' ? '#58A6FF' : '#8B949E',
            }}
          >
            {result.status === 'RUNNING'
              ? `Consulting specialist... · ${consultReason}`
              : result.status === 'COMPLETED'
              ? `Consultation complete · ${consultReason}`
              : result.status === 'FAILED'
              ? `Specialist could not complete · ${consultReason}`
              : result.status === 'ESCALATED'
              ? `Specialist requires attention · ${consultReason}`
              : `Specialist consultation · Consulted ${consultReason}`
            }
          </Typography>
        </Box>

        <Typography aria-hidden="true" sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58' }}>
          {expanded ? '▲' : '▼'}
        </Typography>
      </Box>

      {/* Summary (always visible) */}
      {assessmentSummary && (
        <Box sx={{ px: 1.5, py: 0.75 }}>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#484F58', textTransform: 'uppercase', letterSpacing: '0.08em', mb: 0.25 }}>
            Finding
          </Typography>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#8B949E' }}>
            {assessmentSummary}
          </Typography>
        </Box>
      )}

      {/* Evidence */}
      {result.evidence.length > 0 && (
        <Box sx={{ px: 1.5, pb: 0.75 }}>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#484F58', textTransform: 'uppercase', letterSpacing: '0.08em', mb: 0.25 }}>
            Evidence
          </Typography>
          {result.evidence.map((ev, i) => (
            <Typography key={i} sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#8B949E' }}>
              · {ev}
            </Typography>
          ))}
        </Box>
      )}

      {/* Expert detail (collapsed by default) */}
      {expertMode && (
        <Collapse in={expanded}>
          <Box
            data-testid="delegation-expert-detail"
            sx={{
              px: 1.5,
              pb: 1,
              pt: 0.75,
              borderTop: '1px solid #21262D',
            }}
          >
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#484F58', textTransform: 'uppercase', letterSpacing: '0.08em', mb: 0.5 }}>
              Developer detail
            </Typography>
            {[
              ['delegation_id', result.delegation_id],
              ['parent_task_id', parentTaskId],
              ['child_task_id', result.child_task_id],
              ['requesting_agent', result.requesting_agent],
              ['responding_agent', result.responding_agent],
              ['status', result.status],
              ['candidate_action_count', String(result.candidate_action_count)],
              ['context_snapshot_id', result.context_snapshot_id ?? '—'],
              ['trace_id', result.trace_id ?? '—'],
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

            {/* Context link */}
            {result.context_snapshot_id && (
              <Typography
                component="a"
                href={`/world?snapshot=${result.context_snapshot_id}`}
                sx={{
                  fontFamily: 'monospace',
                  fontSize: '0.5rem',
                  color: '#58A6FF',
                  display: 'block',
                  mt: 0.5,
                  textDecoration: 'none',
                  '&:hover': { textDecoration: 'underline' },
                }}
              >
                VIEW CONTEXT
              </Typography>
            )}

            {/* Trace link */}
            {result.trace_id && (
              <Typography
                component="a"
                href={`/decision-center?trace=${result.trace_id}`}
                sx={{
                  fontFamily: 'monospace',
                  fontSize: '0.5rem',
                  color: '#58A6FF',
                  display: 'block',
                  mt: 0.25,
                  textDecoration: 'none',
                  '&:hover': { textDecoration: 'underline' },
                }}
              >
                VIEW DEVELOPER TRACE
              </Typography>
            )}
          </Box>
        </Collapse>
      )}
    </Box>
  );
}

// ── Delegation chain (list view) ──────────────────────────────────────────────

interface DelegationChainProps {
  task: AgentTaskView;
  expertMode: boolean;
}

function DelegationChain({ task, expertMode }: DelegationChainProps) {
  if (task.delegation_results.length === 0) return null;

  const parentName = getAgentDisplayName(task.agent_id);

  return (
    <Box data-testid="delegation-chain" sx={{ mt: 1 }}>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#484F58', textTransform: 'uppercase', letterSpacing: '0.08em', mb: 0.5 }}>
        Specialist consultations
      </Typography>

      {/* Chain visualization */}
      <Box sx={{ mb: 1 }}>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#C9D1D9', fontWeight: 600 }}>
          {parentName}
        </Typography>
        {task.delegation_results.map((result, i) => {
          const isLast = i === task.delegation_results.length - 1;
          const statusIcon = SPECIALIST_STATUS_ICON[result.status] ?? '●';
          const statusColor = SPECIALIST_STATUS_COLOR[result.status] ?? '#484F58';
          return (
            <Box key={result.delegation_id} sx={{ display: 'flex', alignItems: 'center', gap: 0.5, ml: 1.5, mt: 0.25 }}>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#30363D' }}>
                {isLast ? '└──' : '├──'}
              </Typography>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#8B949E' }}>
                {getAgentDisplayName(result.responding_agent)}
              </Typography>
              <Typography aria-label={`Status: ${result.status}`} sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: statusColor }}>
                {statusIcon}
              </Typography>
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export interface DelegationSectionProps {
  /** The parent agent task (contains delegation_results). */
  task: AgentTaskView | null | undefined;
  expertMode?: boolean;
}

const DelegationSection: React.FC<DelegationSectionProps> = ({
  task,
  expertMode = false,
}) => {
  if (!task || task.delegation_results.length === 0) {
    return null;
  }

  return (
    <Box data-testid="delegation-section">
      <DelegationChain task={task} expertMode={expertMode} />
      {task.delegation_results.map((result) => (
        <SingleDelegationCard
          key={result.delegation_id}
          result={result}
          parentTaskId={task.task_id}
          expertMode={expertMode}
        />
      ))}
    </Box>
  );
};

export default DelegationSection;
