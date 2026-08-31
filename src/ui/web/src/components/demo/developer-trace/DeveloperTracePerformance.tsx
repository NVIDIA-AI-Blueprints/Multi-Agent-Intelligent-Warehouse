/**
 * DeveloperTracePerformance.tsx — Timing summary panel for the developer trace.
 *
 * Shows three distinct clock kinds (never mixed):
 *   - COMPONENT: measured component latencies from backend timing fields
 *   - TRACE: wall-clock derived values from SSE stream
 *   - SIMULATION: simulation time values
 *
 * When available === false, shows unavailableReason in dim text.
 * The [COMPONENT LATENCY] badge is shown for COMPONENT timings to clarify which clock.
 */

import React from 'react';
import { Box, Typography } from '@mui/material';
import { TraceTiming, TraceClockKind } from './developerTraceTypes';

// ── Props ──────────────────────────────────────────────────────────────────────

interface DeveloperTracePerformanceProps {
  timings: TraceTiming[];
}

// ── Clock kind badge ───────────────────────────────────────────────────────────

const KIND_LABELS: Record<TraceClockKind, string> = {
  COMPONENT: 'COMPONENT LATENCY',
  TRACE:     'TRACE CLOCK',
  SIMULATION: 'SIMULATION TIME',
};

const KIND_COLORS: Record<TraceClockKind, string> = {
  COMPONENT: '#30363D',
  TRACE:     '#30363D',
  SIMULATION: '#30363D',
};

// ── Main component ─────────────────────────────────────────────────────────────

export default function DeveloperTracePerformance({ timings }: DeveloperTracePerformanceProps) {
  return (
    <Box>
      {timings.map((t, i) => (
        <Box
          key={i}
          sx={{
            display: 'flex',
            alignItems: 'baseline',
            gap: 1,
            py: '4px',
            borderBottom: i < timings.length - 1 ? '1px solid #1C2128' : 'none',
          }}
        >
          {/* Label */}
          <Typography sx={{
            fontFamily: 'monospace',
            fontSize: '0.62rem',
            color: '#6E7681',
            minWidth: 140,
            flexShrink: 0,
          }}>
            {t.label}
          </Typography>

          {/* Value or unavailable reason */}
          {t.available ? (
            <>
              <Typography sx={{
                fontFamily: 'monospace',
                fontSize: '0.65rem',
                color: '#C9D1D9',
                fontWeight: 600,
                minWidth: 56,
              }}>
                {t.value}
              </Typography>
              {/* Clock kind badge — only for COMPONENT to disambiguate */}
              {t.kind === 'COMPONENT' && (
                <Typography sx={{
                  fontFamily: 'monospace',
                  fontSize: '0.52rem',
                  color: KIND_COLORS[t.kind],
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                }}>
                  [{KIND_LABELS[t.kind]}]
                </Typography>
              )}
            </>
          ) : (
            <Typography sx={{
              fontFamily: 'monospace',
              fontSize: '0.6rem',
              color: '#484F58',
              fontStyle: 'italic',
            }}>
              {t.unavailableReason ?? 'Not available'}
            </Typography>
          )}
        </Box>
      ))}
    </Box>
  );
}
