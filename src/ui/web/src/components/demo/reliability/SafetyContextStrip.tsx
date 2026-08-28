/**
 * SafetyContextStrip — compact safety counter strip for reliability mode.
 *
 * Replaces OperationalContextStrip when in reliability demo.
 *
 * Counter derivation (all from live SSE events):
 *   UNAUTHORIZED  — no SSE category yet; always 0 from live data
 *   DUPLICATE     — no SSE category yet; always 0 from live data
 *   FALSE SUCCESS — CONFIRMED_NOT_EXECUTED events (mutation thought to succeed but didn't)
 *   UNKNOWN       — RECONCILIATION_REQUIRED events (mutation status uncertain)
 *   RECONCILED    — CONFIRMED_EXECUTED + CONFIRMED_NOT_EXECUTED + INDETERMINATE events
 */

import React from 'react';
import { Box, Typography } from '@mui/material';
import { SSEEvent } from '../../../hooks/useDemoSSE';

export interface SafetyCounters {
  unauthorized: number;
  duplicate: number;
  falseSuccess: number;
  unknown: number;
  reconciled: number;
}

export function deriveSafetyCounters(sseEvents: SSEEvent[]): SafetyCounters {
  return {
    unauthorized: 0, // No SSE category for unauthorized writes in current event system
    duplicate: 0,    // 409 responses from approve — not surfaced as SSE
    falseSuccess: sseEvents.filter(e => e.category === 'CONFIRMED_NOT_EXECUTED').length,
    unknown: sseEvents.filter(e => e.category === 'RECONCILIATION_REQUIRED').length,
    reconciled: sseEvents.filter(e =>
      e.category === 'CONFIRMED_EXECUTED' ||
      e.category === 'CONFIRMED_NOT_EXECUTED' ||
      e.category === 'INDETERMINATE'
    ).length,
  };
}

interface CounterPill {
  label: string;
  value: number;
  alertColor?: string;
  testId: string;
}

function Pill({ label, value, alertColor, testId }: CounterPill) {
  const color = value > 0 && alertColor ? alertColor : '#484F58';
  const valColor = value > 0 && alertColor ? alertColor : '#6E7681';
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }} data-testid={testId}>
      <Typography sx={{
        fontFamily: 'monospace', fontSize: '0.6rem', color,
        letterSpacing: '0.08em', textTransform: 'uppercase',
      }}>
        {label}
      </Typography>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.72rem', fontWeight: 700, color: valColor }}>
        {value}
      </Typography>
    </Box>
  );
}

function Divider() {
  return <Box sx={{ width: '1px', height: 12, background: '#21262D', flexShrink: 0 }} />;
}

interface Props {
  sseEvents: SSEEvent[];
}

export default function SafetyContextStrip({ sseEvents }: Props) {
  const c = deriveSafetyCounters(sseEvents);

  return (
    <Box
      data-testid="safety-context-strip"
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 2,
        px: 2,
        py: '6px',
        borderBottom: '1px solid #21262D',
        background: '#0D1117',
        flexWrap: 'wrap',
      }}
    >
      <Typography sx={{
        fontFamily: 'monospace', fontSize: '0.58rem', color: '#30363D',
        letterSpacing: '0.1em', textTransform: 'uppercase', flexShrink: 0,
      }}>
        Safety
      </Typography>
      <Divider />
      <Pill label="Unauthorized" value={c.unauthorized} testId="counter-unauthorized" />
      <Divider />
      <Pill label="Duplicate" value={c.duplicate} testId="counter-duplicate" />
      <Divider />
      <Pill label="False Success" value={c.falseSuccess} alertColor="#F85149" testId="counter-false-success" />
      <Divider />
      <Pill label="Unknown" value={c.unknown} alertColor="#D29922" testId="counter-unknown" />
      <Divider />
      <Pill label="Reconciled" value={c.reconciled} alertColor="#3FB950" testId="counter-reconciled" />
    </Box>
  );
}
