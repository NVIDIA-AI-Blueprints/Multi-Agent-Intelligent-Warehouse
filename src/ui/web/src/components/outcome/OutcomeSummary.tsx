/**
 * OutcomeSummary — UX-1D.3
 *
 * Answers, at a glance: Did the action happen? Is MAIW certain? Did the
 * warehouse improve? Is MAIW done or continuing?
 *
 * Four semantically separate sections — never conflated:
 *   1. EXECUTION  — "Did the requested operation execute?"
 *   2. RELIABILITY — "Is MAIW certain that it executed?"
 *   3. OUTCOME    — "Did the warehouse move toward the objective?"
 *   4. AGENT STATUS — "What should the agent do next?"
 *
 * All data from structured props. No LLM call. Deterministic templating only.
 *
 * Color rule: Green outcome section ONLY when OBJECTIVE_ACHIEVED.
 *   Execution confirmed + objective not achieved → amber outcome (not green).
 */

import React from 'react';
import { Box, Typography } from '@mui/material';
import {
  EXECUTION_STATE_LABEL,
  EXECUTION_STATE_SEVERITY,
  RELIABILITY_STATE_LABEL,
  RELIABILITY_STATE_SEVERITY,
  RELIABILITY_OPERATOR_ACTION_REQUIRED,
  OUTCOME_STATE_LABEL,
  OUTCOME_STATE_SEVERITY,
} from '../../constants/postExecutionStates';
import { AGENT_TASK_STATUS_LABEL } from '../../constants/agentTaskStates';
import StateDelta, { StateDeltaProps } from './StateDelta';
import KPIDelta, { KPIDeltaProps } from './KPIDelta';

// ── Types ─────────────────────────────────────────────────────────────────────

export type ExecutionState =
  | 'executed'
  | 'no_op'
  | 'deferred'
  | 'conflict'
  | 'unknown'
  | 'failed';

export type ReliabilityState =
  | 'CONFIRMED_EXECUTED'
  | 'CONFIRMED_NOT_EXECUTED'
  | 'INDETERMINATE'
  | 'RECONCILING'
  | 'UNKNOWN';

export type OutcomeState =
  | 'OBJECTIVE_ACHIEVED'
  | 'PARTIALLY_ACHIEVED'
  | 'NOT_ACHIEVED'
  | 'INCONCLUSIVE'
  | 'PENDING';

export interface OutcomeSummaryProps {
  /** ActionExecutor execution outcome (wire value, lowercase). */
  executionState: ExecutionState;
  /** Reconciliation/reliability certainty state. */
  reliabilityState: ReliabilityState;
  /** Operational outcome (warehouse improvement). */
  outcomeState: OutcomeState;
  /** Agent task terminal status. */
  agentTaskStatus: string;
  /**
   * Deterministic narrative summary string.
   * Built from entity/KPI deltas + objective result — no LLM.
   * If absent: "Outcome could not be determined from the available state."
   */
  summary?: string;
  /** Entity-level state changes to show as StateDelta rows. */
  entityDeltas?: StateDeltaProps[];
  /** KPI changes relevant to the intervention objective. */
  kpiDeltas?: KPIDeltaProps[];
  /** Optional: link to developer trace. */
  onViewTrace?: () => void;
  /** Optional: link to reliability panel. */
  onViewReliability?: () => void;
}

// ── Severity colours ──────────────────────────────────────────────────────────

const SEVERITY_COLOR: Record<string, string> = {
  success:   '#3FB950',
  warning:   '#D29922',
  attention: '#F0883E',
  error:     '#F85149',
  neutral:   '#6E7681',
};

// ── Section ───────────────────────────────────────────────────────────────────

function Section({
  label,
  children,
  severity,
  testId,
}: {
  label: string;
  children: React.ReactNode;
  severity?: string;
  testId?: string;
}) {
  const borderColor = severity ? (SEVERITY_COLOR[severity] ?? '#21262D') : '#21262D';
  return (
    <Box
      data-testid={testId}
      sx={{
        borderLeft: `3px solid ${borderColor}`,
        pl: 1.25,
        py: 0.5,
      }}
    >
      <Typography sx={{
        fontFamily: 'monospace',
        fontSize: '0.55rem',
        fontWeight: 700,
        color: '#484F58',
        letterSpacing: '0.12em',
        textTransform: 'uppercase',
        mb: 0.35,
      }}>
        {label}
      </Typography>
      {children}
    </Box>
  );
}

function SectionValue({
  value,
  severity,
  testId,
}: {
  value: string;
  severity: string;
  testId?: string;
}) {
  const color = SEVERITY_COLOR[severity] ?? '#8B949E';
  return (
    <Typography
      data-testid={testId}
      sx={{ fontFamily: 'monospace', fontSize: '0.72rem', fontWeight: 700, color }}
    >
      {value}
    </Typography>
  );
}

// ── Pending outcome banner ────────────────────────────────────────────────────

function PendingOutcomeBanner({ reliabilityState }: { reliabilityState: ReliabilityState }) {
  const messages: Partial<Record<ReliabilityState, string>> = {
    UNKNOWN:       'Verifying execution — outcome assessment pending.',
    RECONCILING:   'Verifying execution — outcome assessment pending.',
    INDETERMINATE: 'MAIW could not determine execution certainty. Operator review required before outcome can be assessed.',
  };
  const msg = messages[reliabilityState];
  if (!msg) {return null;}

  const isIndeterminate = reliabilityState === 'INDETERMINATE';
  const color = isIndeterminate ? '#F0883E' : '#D29922';

  return (
    <Box
      data-testid="outcome-pending-banner"
      sx={{
        p: 1,
        background: `${color}11`,
        border: `1px solid ${color}44`,
        borderRadius: '4px',
      }}
    >
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.63rem', color }}>
        {msg}
      </Typography>
    </Box>
  );
}

// ── Deterministic summary template ────────────────────────────────────────────

function buildSummary(
  outcomeState: OutcomeState,
  summary?: string,
): string {
  if (summary) {return summary;}
  const FALLBACKS: Record<OutcomeState, string> = {
    OBJECTIVE_ACHIEVED:    'The warehouse state moved toward the operational objective.',
    PARTIALLY_ACHIEVED:    'Some objective criteria were met. MAIW is reassessing the remaining gap.',
    NOT_ACHIEVED:          'The warehouse state did not improve toward the objective despite confirmed execution.',
    INCONCLUSIVE:          'Outcome could not be determined from the available state.',
    PENDING:               'Outcome assessment is pending execution confirmation.',
  };
  return FALLBACKS[outcomeState];
}

// ── Main component ────────────────────────────────────────────────────────────

export default function OutcomeSummary({
  executionState,
  reliabilityState,
  outcomeState,
  agentTaskStatus,
  summary,
  entityDeltas,
  kpiDeltas,
  onViewTrace,
  onViewReliability,
}: OutcomeSummaryProps) {
  const execSeverity    = EXECUTION_STATE_SEVERITY[executionState]  ?? 'neutral';
  const relSeverity     = RELIABILITY_STATE_SEVERITY[reliabilityState] ?? 'neutral';
  const outcomeSeverity = OUTCOME_STATE_SEVERITY[outcomeState] ?? 'neutral';
  const agentLabel      = AGENT_TASK_STATUS_LABEL[agentTaskStatus] ?? agentTaskStatus;

  // Show outcome section only if execution is sufficiently resolved
  const executionResolved = ['executed', 'no_op'].includes(executionState)
    || reliabilityState === 'CONFIRMED_EXECUTED';
  const outcomeBlocked = !executionResolved
    || reliabilityState === 'INDETERMINATE'
    || reliabilityState === 'RECONCILING'
    || reliabilityState === 'UNKNOWN';

  const operatorActionRequired = RELIABILITY_OPERATOR_ACTION_REQUIRED[reliabilityState] ?? false;

  return (
    <Box data-testid="outcome-summary" sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Typography sx={{
          fontFamily: 'monospace',
          fontSize: '0.58rem',
          fontWeight: 700,
          color: '#484F58',
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
        }}>
          Outcome Summary
        </Typography>
        <Box sx={{ display: 'flex', gap: 1 }}>
          {onViewReliability && (
            <Typography
              data-testid="view-reliability-link"
              onClick={onViewReliability}
              sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#58A6FF', cursor: 'pointer', '&:hover': { textDecoration: 'underline' } }}
            >
              VIEW RELIABILITY
            </Typography>
          )}
          {onViewTrace && (
            <Typography
              data-testid="view-trace-link"
              onClick={onViewTrace}
              sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#58A6FF', cursor: 'pointer', '&:hover': { textDecoration: 'underline' } }}
            >
              VIEW TRACE
            </Typography>
          )}
        </Box>
      </Box>

      {/* 1. EXECUTION */}
      <Section label="Execution" severity={execSeverity} testId="outcome-execution-section">
        <SectionValue
          value={EXECUTION_STATE_LABEL[executionState] ?? executionState}
          severity={execSeverity}
          testId="outcome-execution-value"
        />
      </Section>

      {/* 2. RELIABILITY */}
      <Section label="Reliability" severity={relSeverity} testId="outcome-reliability-section">
        <SectionValue
          value={RELIABILITY_STATE_LABEL[reliabilityState] ?? reliabilityState}
          severity={relSeverity}
          testId="outcome-reliability-value"
        />
        {operatorActionRequired && (
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#F0883E', mt: 0.25 }}>
            Operator review required — no automatic retry will be issued.
          </Typography>
        )}
      </Section>

      {/* Pending/blocked outcome banner */}
      {outcomeBlocked && <PendingOutcomeBanner reliabilityState={reliabilityState} />}

      {/* 3. OUTCOME — shown always but content varies */}
      <Section label="Outcome" severity={outcomeSeverity} testId="outcome-operational-section">
        <SectionValue
          value={OUTCOME_STATE_LABEL[outcomeState] ?? outcomeState}
          severity={outcomeSeverity}
          testId="outcome-operational-value"
        />
        {outcomeState === 'NOT_ACHIEVED' && (
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#8B949E', mt: 0.25 }}>
            MAIW is reassessing the operational state.
          </Typography>
        )}
      </Section>

      {/* 4. SUMMARY — deterministic narrative */}
      {!outcomeBlocked && (
        <Section label="Summary" testId="outcome-summary-section">
          <Typography
            data-testid="outcome-summary-text"
            sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#8B949E', lineHeight: 1.5 }}
          >
            {buildSummary(outcomeState, summary)}
          </Typography>
        </Section>
      )}

      {/* Entity deltas */}
      {!outcomeBlocked && entityDeltas && entityDeltas.length > 0 && (
        <Box data-testid="outcome-entity-deltas">
          <Typography sx={{
            fontFamily: 'monospace',
            fontSize: '0.55rem',
            fontWeight: 700,
            color: '#484F58',
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
            mb: 0.5,
          }}>
            Key Changes
          </Typography>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
            {entityDeltas.map((d) => (
              <StateDelta key={d.entityId} {...d} />
            ))}
          </Box>
        </Box>
      )}

      {/* KPI deltas */}
      {!outcomeBlocked && kpiDeltas && kpiDeltas.length > 0 && (
        <Box data-testid="outcome-kpi-deltas">
          <Typography sx={{
            fontFamily: 'monospace',
            fontSize: '0.55rem',
            fontWeight: 700,
            color: '#484F58',
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
            mb: 0.5,
          }}>
            KPI Impact
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
            {kpiDeltas.map((k) => (
              <KPIDelta key={k.label} {...k} />
            ))}
          </Box>
        </Box>
      )}

      {/* 5. AGENT STATUS */}
      <Section label="Agent Status" testId="outcome-agent-status-section">
        <Typography
          data-testid="outcome-agent-status-value"
          sx={{ fontFamily: 'monospace', fontSize: '0.7rem', fontWeight: 700, color: '#8B949E' }}
        >
          {agentLabel}
        </Typography>
      </Section>
    </Box>
  );
}
