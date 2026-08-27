import React from 'react';
import { Box, Typography } from '@mui/material';

export type ExecutionOutcome =
  | 'EXECUTED'
  | 'NO_OP'
  | 'DEFERRED'
  | 'CONFLICT'
  | 'UNKNOWN'
  | 'FAILED';

export type ReconciliationOutcome =
  | 'CONFIRMED_EXECUTED'
  | 'CONFIRMED_NOT_EXECUTED'
  | 'INDETERMINATE'
  | 'RECONCILING';

const OUTCOME_META: Record<ExecutionOutcome, { label: string; color: string; desc: string }> = {
  EXECUTED:  { label: 'EXECUTED',  color: '#3FB950', desc: 'Mutation confirmed' },
  NO_OP:     { label: 'NO-OP',     color: '#58A6FF', desc: 'Idempotent replay — no new mutation' },
  DEFERRED:  { label: 'DEFERRED',  color: '#D29922', desc: 'Awaiting human approval' },
  CONFLICT:  { label: 'CONFLICT',  color: '#E3B341', desc: 'State drift blocked execution' },
  UNKNOWN:   { label: 'UNKNOWN',   color: '#F0883E', desc: 'Mutation may have occurred — reconcile before retry' },
  FAILED:    { label: 'FAILED',    color: '#F85149', desc: 'No mutation — safe to re-evaluate' },
};

const RECONCILE_META: Record<ReconciliationOutcome, { label: string; color: string; desc: string }> = {
  RECONCILING:           { label: 'RECONCILING',        color: '#58A6FF', desc: 'Checking authoritative state…' },
  CONFIRMED_EXECUTED:    { label: 'CONFIRMED EXECUTED',  color: '#3FB950', desc: 'Mutation confirmed present' },
  CONFIRMED_NOT_EXECUTED:{ label: 'NOT EXECUTED',        color: '#8B949E', desc: 'No mutation found — safe to retry' },
  INDETERMINATE:         { label: 'INDETERMINATE',       color: '#D29922', desc: 'Cannot determine — manual review required' },
};

interface Props {
  outcome: ExecutionOutcome;
  reconciliation?: ReconciliationOutcome;
  compact?: boolean;
}

export default function ExecutionOutcomeBadge({ outcome, reconciliation, compact = false }: Props) {
  const meta = OUTCOME_META[outcome];

  return (
    <Box sx={{ display: 'inline-flex', flexDirection: 'column', gap: 0.5 }}>
      <Box sx={{
        display: 'inline-flex', alignItems: 'center', gap: 0.5,
        px: compact ? 0.5 : 0.75, py: compact ? 0.1 : 0.25,
        borderRadius: 0.5,
        border: `1px solid ${meta.color}33`,
        backgroundColor: `${meta.color}11`,
      }}>
        <Box sx={{ width: 5, height: 5, borderRadius: '50%', backgroundColor: meta.color, flexShrink: 0 }} />
        <Typography sx={{
          fontFamily: 'monospace', fontSize: compact ? '0.6rem' : '0.68rem',
          fontWeight: 700, color: meta.color, letterSpacing: '0.06em',
        }}>
          {meta.label}
        </Typography>
      </Box>

      {!compact && (
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#6E7681' }}>
          {meta.desc}
        </Typography>
      )}

      {reconciliation && (
        <Box sx={{
          display: 'inline-flex', alignItems: 'center', gap: 0.5,
          px: compact ? 0.5 : 0.75, py: compact ? 0.1 : 0.25,
          borderRadius: 0.5,
          border: `1px solid ${RECONCILE_META[reconciliation].color}33`,
          backgroundColor: `${RECONCILE_META[reconciliation].color}11`,
        }}>
          <Typography sx={{
            fontFamily: 'monospace', fontSize: compact ? '0.55rem' : '0.62rem',
            color: RECONCILE_META[reconciliation].color, letterSpacing: '0.04em',
          }}>
            → {RECONCILE_META[reconciliation].label}
          </Typography>
        </Box>
      )}
    </Box>
  );
}
