/**
 * ExecutionReliabilityPanel — UX-1D.2
 *
 * Answers the operator question: "Is MAIW certain that the action happened?"
 *
 * Distinct from:
 *   - system/ReliabilityPanel (system health — circuit breakers, domain health)
 *   - demo/reliability/ReliabilityPanel (fault injection demo orchestrator)
 *
 * Two modes:
 *   - Operator mode (default): plain-language label, explanation, next action,
 *     whether operator action is required
 *   - Expert mode: adds exact enum value, execution_id, timestamps, retry note
 *
 * Color semantics:
 *   - UNKNOWN / RECONCILING: amber (warning) — NOT red; unconfirmed ≠ failed
 *   - INDETERMINATE: orange (attention) — requires operator review
 *   - CONFIRMED_EXECUTED: green
 *   - CONFIRMED_NOT_EXECUTED: grey (neutral)
 *   - FAILED (execution): red
 */

import React from 'react';
import { Box, Typography } from '@mui/material';
import {
  RELIABILITY_STATE_LABEL,
  RELIABILITY_STATE_EXPLANATION,
  RELIABILITY_NEXT_ACTION,
  RELIABILITY_OPERATOR_ACTION_REQUIRED,
  RELIABILITY_STATE_SEVERITY,
} from '../../constants/postExecutionStates';

// ── Types ─────────────────────────────────────────────────────────────────────

export type ReliabilityState =
  | 'CONFIRMED_EXECUTED'
  | 'CONFIRMED_NOT_EXECUTED'
  | 'INDETERMINATE'
  | 'RECONCILING'
  | 'UNKNOWN';

export interface ExecutionReliabilityPanelProps {
  /** Reliability/reconciliation state. */
  reliabilityState: ReliabilityState;
  /** Expert mode: shows technical details. */
  expertMode?: boolean;
  /** Expert: execution ID from ActionExecutor. */
  executionId?: string;
  /** Expert: ISO timestamp of execution attempt. */
  executedAt?: string;
  /** Expert: ISO timestamp of reconciliation. */
  reconciledAt?: string;
  /** Optional callback to navigate to DeveloperTrace. */
  onViewTrace?: () => void;
}

// ── Severity colours ──────────────────────────────────────────────────────────

const SEVERITY_COLOR: Record<string, string> = {
  success:   '#3FB950',
  warning:   '#D29922',
  attention: '#F0883E',
  error:     '#F85149',
  neutral:   '#6E7681',
};

// ── Sub-components ────────────────────────────────────────────────────────────

function StateChip({ state, severity }: { state: string; severity: string }) {
  const color = SEVERITY_COLOR[severity] ?? '#484F58';
  return (
    <Box
      data-testid={`reliability-chip-${state}`}
      sx={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 0.5,
        px: 0.75,
        py: 0.25,
        borderRadius: 0.5,
        border: `1px solid ${color}44`,
        backgroundColor: `${color}11`,
      }}
    >
      <Box sx={{ width: 5, height: 5, borderRadius: '50%', backgroundColor: color, flexShrink: 0 }} />
      <Typography sx={{
        fontFamily: 'monospace',
        fontSize: '0.7rem',
        fontWeight: 700,
        color,
        letterSpacing: '0.06em',
      }}>
        {RELIABILITY_STATE_LABEL[state] ?? state}
      </Typography>
    </Box>
  );
}

function OperatorActionBadge() {
  return (
    <Box
      data-testid="operator-action-required-badge"
      sx={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 0.5,
        px: 0.75,
        py: 0.2,
        borderRadius: 0.5,
        border: '1px solid #F0883E44',
        backgroundColor: '#F0883E11',
      }}
    >
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', fontWeight: 700, color: '#F0883E', letterSpacing: '0.08em' }}>
        OPERATOR ACTION REQUIRED
      </Typography>
    </Box>
  );
}

function FieldRow({ label, value, testId }: { label: string; value: string; testId?: string }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1, py: 0.15 }}>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#484F58', width: 130, flexShrink: 0 }}>
        {label}
      </Typography>
      <Typography data-testid={testId} sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#8B949E', wordBreak: 'break-all' }}>
        {value}
      </Typography>
    </Box>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function ExecutionReliabilityPanel({
  reliabilityState,
  expertMode = false,
  executionId,
  executedAt,
  reconciledAt,
  onViewTrace,
}: ExecutionReliabilityPanelProps) {
  const severity = RELIABILITY_STATE_SEVERITY[reliabilityState] ?? 'neutral';
  const explanation = RELIABILITY_STATE_EXPLANATION[reliabilityState] ?? '';
  const nextAction = RELIABILITY_NEXT_ACTION[reliabilityState] ?? '';
  const operatorActionRequired = RELIABILITY_OPERATOR_ACTION_REQUIRED[reliabilityState] ?? false;

  return (
    <Box data-testid="execution-reliability-panel" sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1 }}>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', fontWeight: 700, color: '#484F58', letterSpacing: '0.12em', textTransform: 'uppercase' }}>
          Execution Certainty
        </Typography>
        {onViewTrace && (
          <Typography
            data-testid="view-reliability-link"
            onClick={onViewTrace}
            sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#58A6FF', cursor: 'pointer', '&:hover': { textDecoration: 'underline' } }}
          >
            VIEW DEVELOPER TRACE
          </Typography>
        )}
      </Box>

      {/* State chip */}
      <Box>
        <StateChip state={reliabilityState} severity={severity} />
      </Box>

      {/* Operator action badge — shown before explanation for INDETERMINATE */}
      {operatorActionRequired && <OperatorActionBadge />}

      {/* Explanation */}
      <Typography
        data-testid="reliability-explanation"
        sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#8B949E', lineHeight: 1.5 }}
      >
        {explanation}
      </Typography>

      {/* Next action */}
      <Box sx={{ borderLeft: '2px solid #21262D', pl: 1 }}>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58', letterSpacing: '0.08em', mb: 0.25 }}>
          WHAT HAPPENS NEXT
        </Typography>
        <Typography data-testid="reliability-next-action" sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#6E7681' }}>
          {nextAction}
        </Typography>
      </Box>

      {/* Expert mode: technical details */}
      {expertMode && (
        <Box
          data-testid="reliability-expert-details"
          sx={{
            mt: 0.5,
            p: 1,
            background: '#0D1117',
            border: '1px solid #21262D',
            borderRadius: '4px',
            display: 'flex',
            flexDirection: 'column',
            gap: 0.1,
          }}
        >
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58', letterSpacing: '0.1em', mb: 0.5 }}>
            EXPERT
          </Typography>
          <FieldRow
            label="Reliability state"
            value={reliabilityState}
            testId="reliability-expert-state"
          />
          {executionId && (
            <FieldRow
              label="Execution ID"
              value={executionId}
              testId="reliability-execution-id"
            />
          )}
          {executedAt && (
            <FieldRow
              label="Executed at"
              value={executedAt}
            />
          )}
          {reconciledAt && (
            <FieldRow
              label="Reconciled at"
              value={reconciledAt}
            />
          )}
          {(reliabilityState === 'INDETERMINATE' || reliabilityState === 'UNKNOWN') && (
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#D29922', mt: 0.5 }}>
              No automatic retry has been issued.
            </Typography>
          )}
        </Box>
      )}
    </Box>
  );
}
