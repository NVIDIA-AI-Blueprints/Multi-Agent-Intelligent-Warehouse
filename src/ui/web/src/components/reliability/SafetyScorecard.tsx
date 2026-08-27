import React from 'react';
import { Box, Typography } from '@mui/material';
import { SafetyCounters, BATCH6_BASELINE } from '../../hooks/useReliabilityCounters';

interface CounterRowProps {
  label: string;
  value: number;
  expected: number;
  invertPass?: boolean; // true = pass when value > 0 (blocks)
}

function CounterRow({ label, value, expected, invertPass }: CounterRowProps) {
  const pass = invertPass ? value >= expected : value === expected;
  const color = pass ? '#3FB950' : '#F85149';
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, py: 0.25 }}>
      <Box sx={{ width: 5, height: 5, borderRadius: '50%', flexShrink: 0, backgroundColor: color }} />
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', color: '#8B949E', flexGrow: 1 }}>
        {label}
      </Typography>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', fontWeight: 700, color }}>
        {value}
      </Typography>
    </Box>
  );
}

interface Props {
  counters?: SafetyCounters;
  showValidatedBadge?: boolean;
}

export default function SafetyScorecard({ counters, showValidatedBadge = false }: Props) {
  // Use live counters if provided and non-zero, otherwise show Batch 6 baseline
  const data = counters ?? BATCH6_BASELINE;
  const isBaseline = !counters;

  const allSafe =
    data.unauthorized_writes === 0 &&
    data.duplicate_writes === 0 &&
    data.false_successes === 0;

  return (
    <Box>
      {/* Header row */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.75 }}>
        <Box sx={{
          display: 'inline-flex', alignItems: 'center', gap: 0.5,
          px: 0.5, py: 0.15,
          border: `1px solid ${allSafe ? '#3FB95044' : '#F8514944'}`,
          borderRadius: 0.5,
          backgroundColor: allSafe ? '#3FB95011' : '#F8514911',
        }}>
          <Typography sx={{
            fontFamily: 'monospace', fontSize: '0.6rem', fontWeight: 700,
            color: allSafe ? '#3FB950' : '#F85149', letterSpacing: '0.06em',
          }}>
            {allSafe ? 'ALL SAFE' : 'VIOLATION'}
          </Typography>
        </Box>
        {(isBaseline || showValidatedBadge) && (
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58', letterSpacing: '0.06em' }}>
            VALIDATED BATCH 6
          </Typography>
        )}
      </Box>

      {/* Golden invariants */}
      <CounterRow label="Unauthorized writes" value={data.unauthorized_writes} expected={0} />
      <CounterRow label="Duplicate writes"    value={data.duplicate_writes}    expected={0} />
      <CounterRow label="False successes"     value={data.false_successes}     expected={0} />

      <Box sx={{ my: 0.5, borderTop: '1px solid #1C2128' }} />

      {/* Contextual counters */}
      <CounterRow label="UNKNOWN executions"  value={data.unknown_executions}  expected={0} />
      <CounterRow label="Reconciled"          value={data.reconciled}          expected={0} invertPass />
      <CounterRow label="Stale blocks"        value={data.stale_blocks}        expected={0} invertPass />
      <CounterRow label="Drift blocks"        value={data.drift_blocks}        expected={0} invertPass />
    </Box>
  );
}
