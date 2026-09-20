/**
 * KPIDelta — UX-1D.3
 *
 * Shows before/after for a single KPI relevant to the intervention objective.
 * Shows only KPIs relevant to the intervention. Direction arrow indicates
 * whether the change is positive (toward objective) or negative.
 *
 * All data from structured props. No LLM calls.
 */

import React from 'react';
import { Box, Typography } from '@mui/material';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface KPIDeltaProps {
  /** KPI display name (e.g., "Labor utilization", "Pending backlog"). */
  label: string;
  /** Value before the action (numeric or string). */
  before: number | string;
  /** Value after the action (numeric or string). */
  after: number | string;
  /** Optional unit suffix (e.g., "%", " tasks", " pp"). */
  unit?: string;
  /**
   * Direction of improvement.
   * 'increase' = higher after is better (e.g., utilization).
   * 'decrease' = lower after is better (e.g., pending backlog).
   * 'neutral'  = no directional preference.
   */
  improvementDirection?: 'increase' | 'decrease' | 'neutral';
  /** Optional: explicit delta string (e.g., "+0.8 pp"). Computed if not provided. */
  deltaLabel?: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function computeDelta(before: number | string, after: number | string, unit?: string): string | null {
  const b = typeof before === 'number' ? before : parseFloat(String(before));
  const a = typeof after  === 'number' ? after  : parseFloat(String(after));
  if (isNaN(b) || isNaN(a)) {return null;}
  const diff = a - b;
  const sign = diff > 0 ? '+' : '';
  return `${sign}${diff.toFixed(diff % 1 !== 0 ? 1 : 0)}${unit ?? ''}`;
}

function directionColor(
  before: number | string,
  after: number | string,
  dir: 'increase' | 'decrease' | 'neutral',
): string {
  const b = typeof before === 'number' ? before : parseFloat(String(before));
  const a = typeof after  === 'number' ? after  : parseFloat(String(after));
  if (isNaN(b) || isNaN(a) || dir === 'neutral') {return '#8B949E';}
  const improved = dir === 'increase' ? a > b : a < b;
  return improved ? '#3FB950' : '#D29922';
}

// ── Main component ────────────────────────────────────────────────────────────

export default function KPIDelta({
  label,
  before,
  after,
  unit,
  improvementDirection = 'neutral',
  deltaLabel,
}: KPIDeltaProps) {
  const delta = deltaLabel ?? computeDelta(before, after, unit);
  const deltaColor = directionColor(before, after, improvementDirection);

  return (
    <Box
      data-testid={`kpi-delta-${label.toLowerCase().replace(/\s+/g, '-')}`}
      sx={{
        p: 1,
        background: '#0D1117',
        border: '1px solid #21262D',
        borderRadius: '4px',
        display: 'flex',
        flexDirection: 'column',
        gap: 0.35,
      }}
    >
      {/* Label */}
      <Typography sx={{
        fontFamily: 'monospace',
        fontSize: '0.58rem',
        color: '#484F58',
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
      }}>
        {label}
      </Typography>

      {/* Before → After */}
      <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 0.75 }}>
        <Typography
          data-testid="kpi-before"
          sx={{ fontFamily: 'monospace', fontSize: '0.75rem', color: '#6E7681', textDecoration: 'line-through' }}
        >
          {before}{unit}
        </Typography>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#484F58' }}>→</Typography>
        <Typography
          data-testid="kpi-after"
          sx={{ fontFamily: 'monospace', fontSize: '0.85rem', fontWeight: 700, color: '#E6EDF3' }}
        >
          {after}{unit}
        </Typography>
      </Box>

      {/* Delta */}
      {delta && (
        <Typography
          data-testid="kpi-delta"
          sx={{ fontFamily: 'monospace', fontSize: '0.62rem', fontWeight: 700, color: deltaColor }}
        >
          {delta}
        </Typography>
      )}
    </Box>
  );
}
