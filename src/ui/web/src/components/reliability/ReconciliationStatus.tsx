import React from 'react';
import { Box, Typography } from '@mui/material';
import { ReconciliationOutcome } from './ExecutionOutcomeBadge';

interface Step {
  label: string;
  desc: string;
  color: string;
  active?: boolean;
  done?: boolean;
}

const F06_STEPS: Step[] = [
  { label: 'UNKNOWN',      desc: 'Mutation sent — ACK lost',          color: '#F0883E' },
  { label: 'RECONCILING',  desc: 'Reading authoritative state',        color: '#58A6FF' },
  { label: 'CONFIRMED',    desc: 'Mutation present — effectively done', color: '#3FB950' },
];

type FlowState = 'UNKNOWN' | 'RECONCILING' | 'CONFIRMED_EXECUTED' | 'CONFIRMED_NOT_EXECUTED' | 'INDETERMINATE';

function mapToStep(state: FlowState): number {
  if (state === 'UNKNOWN') return 0;
  if (state === 'RECONCILING') return 1;
  return 2;
}

interface Props {
  state?: FlowState;
  reconciliationOutcome?: ReconciliationOutcome;
  compact?: boolean;
}

export default function ReconciliationStatus({ state = 'CONFIRMED_EXECUTED', compact = false }: Props) {
  const activeStep = mapToStep(state);
  const isIndeterminate = state === 'INDETERMINATE';
  const isNotExecuted = state === 'CONFIRMED_NOT_EXECUTED';

  const steps = F06_STEPS.map((s, i) => ({
    ...s,
    done: !isIndeterminate && i < activeStep,
    active: i === activeStep,
  }));

  const finalLabel = isIndeterminate
    ? 'INDETERMINATE — manual review required'
    : isNotExecuted
    ? 'NOT EXECUTED — safe to retry'
    : state === 'CONFIRMED_EXECUTED'
    ? 'CONFIRMED EXECUTED'
    : null;

  const finalColor = isIndeterminate ? '#D29922' : isNotExecuted ? '#8B949E' : '#3FB950';

  return (
    <Box>
      {/* Step flow */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
        {steps.map((step, i) => (
          <React.Fragment key={step.label}>
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0.25 }}>
              <Box sx={{
                px: compact ? 0.5 : 0.75, py: compact ? 0.1 : 0.2,
                borderRadius: 0.5,
                border: `1px solid ${(step.done || step.active) ? step.color + '66' : '#1C2128'}`,
                backgroundColor: step.active ? step.color + '22' : step.done ? step.color + '11' : 'transparent',
              }}>
                <Typography sx={{
                  fontFamily: 'monospace',
                  fontSize: compact ? '0.58rem' : '0.65rem',
                  fontWeight: (step.done || step.active) ? 700 : 400,
                  color: step.done ? step.color : step.active ? step.color : '#30363D',
                  letterSpacing: '0.04em',
                }}>
                  {step.label}
                </Typography>
              </Box>
              {!compact && (
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58', textAlign: 'center', maxWidth: 80 }}>
                  {step.desc}
                </Typography>
              )}
            </Box>
            {i < steps.length - 1 && (
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#30363D', flexShrink: 0, mb: compact ? 0 : 1.5 }}>
                →
              </Typography>
            )}
          </React.Fragment>
        ))}
      </Box>

      {/* Final verdict label */}
      {finalLabel && (
        <Box sx={{ mt: 0.5 }}>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: finalColor, fontWeight: 700 }}>
            {finalLabel}
          </Typography>
          {!compact && (
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58', mt: 0.25 }}>
              ExecutionRecord.outcome = UNKNOWN (immutable history preserved)
            </Typography>
          )}
        </Box>
      )}
    </Box>
  );
}
