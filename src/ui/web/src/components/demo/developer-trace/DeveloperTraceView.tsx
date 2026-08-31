/**
 * DeveloperTraceView.tsx — Combines Timeline + Artifacts + Performance panels
 * into the full developer trace view for Phase 13E.
 *
 * When trace is null: shows "NO ACTIVE TRACE" placeholder.
 * When trace exists: shows header + TIMELINE + ARTIFACT LINEAGE + TRACE PERFORMANCE.
 */

import React, { useMemo } from 'react';
import { Box, Typography } from '@mui/material';
import { DeveloperTrace, DeveloperTraceStatus } from './developerTraceTypes';
import { ExplanationFocus } from '../decision-explanation/explanationTypes';
import DeveloperTraceTimeline from './DeveloperTraceTimeline';
import DeveloperTraceArtifacts from './DeveloperTraceArtifacts';
import DeveloperTracePerformance from './DeveloperTracePerformance';
import { useTraceReplay } from './useTraceReplay';

// ── Props ──────────────────────────────────────────────────────────────────────

interface DeveloperTraceViewProps {
  trace: DeveloperTrace | null;
  onOpenExplanation?: (focus: ExplanationFocus) => void;
}

// ── Status badge ───────────────────────────────────────────────────────────────

const STATUS_COLORS: Record<DeveloperTraceStatus, string> = {
  IN_PROGRESS:             '#58A6FF',
  WAITING_FOR_APPROVAL:    '#D29922',
  EXECUTING:               '#D29922',
  RECONCILIATION_REQUIRED: '#F85149',
  COMPLETE:                '#3FB950',
  FAILED:                  '#F85149',
  UNKNOWN:                 '#484F58',
};

function StatusBadge({ status }: { status: DeveloperTraceStatus }) {
  const color = STATUS_COLORS[status] ?? '#484F58';
  return (
    <Box
      component="span"
      sx={{
        fontFamily: 'monospace',
        fontSize: '0.58rem',
        fontWeight: 700,
        color,
        border: `1px solid ${color}44`,
        borderRadius: '3px',
        px: '5px',
        py: '1px',
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
      }}
    >
      {status.replace(/_/g, ' ')}
    </Box>
  );
}

// ── Section divider ────────────────────────────────────────────────────────────

function SectionDivider() {
  return (
    <Box sx={{ height: '1px', background: '#1C2128', my: 1.5 }} />
  );
}

// ── Section header ─────────────────────────────────────────────────────────────

function SectionHeader({ label }: { label: string }) {
  return (
    <Typography sx={{
      fontFamily: 'monospace',
      fontSize: '0.58rem',
      fontWeight: 700,
      color: '#484F58',
      letterSpacing: '0.12em',
      textTransform: 'uppercase',
      mb: 0.75,
    }}>
      {label}
    </Typography>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

// ── Replay controls ────────────────────────────────────────────────────────────

function ReplayControls({
  mode,
  onSkip,
  onReplay,
}: {
  mode: 'REPLAYING' | 'LIVE' | 'COMPLETE';
  onSkip: () => void;
  onReplay: () => void;
}) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      {mode === 'REPLAYING' ? (
        <>
          <Typography sx={{
            fontFamily: 'monospace',
            fontSize: '0.62rem',
            color: '#D29922',
            letterSpacing: '0.08em',
          }}>
            REPLAYING TRACE
          </Typography>
          <Box
            component="button"
            onClick={onSkip}
            sx={{
              fontFamily: 'monospace',
              fontSize: '0.62rem',
              color: '#484F58',
              background: 'transparent',
              border: '1px solid #30363D',
              borderRadius: '3px',
              px: '6px',
              py: '1px',
              cursor: 'pointer',
              letterSpacing: '0.04em',
              '&:hover': { borderColor: '#484F58', color: '#8B949E' },
            }}
          >
            SKIP
          </Box>
        </>
      ) : (
        <>
          <Typography sx={{
            fontFamily: 'monospace',
            fontSize: '0.62rem',
            color: '#3FB950',
            letterSpacing: '0.08em',
          }}>
            ● LIVE
          </Typography>
          <Box
            component="button"
            onClick={onReplay}
            sx={{
              fontFamily: 'monospace',
              fontSize: '0.62rem',
              color: '#484F58',
              background: 'transparent',
              border: '1px solid #30363D',
              borderRadius: '3px',
              px: '6px',
              py: '1px',
              cursor: 'pointer',
              letterSpacing: '0.04em',
              '&:hover': { borderColor: '#484F58', color: '#8B949E' },
            }}
          >
            REPLAY
          </Box>
        </>
      )}
    </Box>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function DeveloperTraceView({ trace, onOpenExplanation }: DeveloperTraceViewProps) {
  if (!trace) {
    return (
      <Box
        data-testid="dev-trace-empty"
        sx={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          py: 6,
          gap: 1,
        }}
      >
        <Typography sx={{
          fontFamily: 'monospace',
          fontSize: '0.75rem',
          color: '#484F58',
          fontWeight: 700,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
        }}>
          NO ACTIVE TRACE
        </Typography>
        <Typography sx={{
          fontFamily: 'monospace',
          fontSize: '0.62rem',
          color: '#30363D',
        }}>
          Run a scenario to inspect its end-to-end execution trace.
        </Typography>
      </Box>
    );
  }

  const prefersReducedMotion = useMemo(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      // jsdom / SSR: skip animation, show all events immediately
      return true;
    }
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }, []);

  const replayState = useTraceReplay(trace.events, {
    charIntervalMs: 12,
    eventDelayMs: 100,
    reducedMotion: prefersReducedMotion,
  });

  const shortTraceId = trace.traceId
    ? `${trace.traceId.slice(0, 8)}…`
    : null;

  const showPreamble =
    replayState.mode === 'REPLAYING' &&
    replayState.visibleEvents.length === 0 &&
    replayState.activeEventIndex === 0;

  return (
    <Box data-testid="dev-trace-view" sx={{ display: 'flex', flexDirection: 'column' }}>
      {/* Trace header */}
      <Box sx={{ mb: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
          <Typography sx={{
            fontFamily: 'monospace',
            fontSize: '0.72rem',
            fontWeight: 700,
            color: '#C9D1D9',
            letterSpacing: '0.04em',
            textTransform: 'uppercase',
          }}>
            TRACE
          </Typography>
          {shortTraceId && (
            <Typography
              title={trace.traceId ?? undefined}
              sx={{
                fontFamily: 'monospace',
                fontSize: '0.65rem',
                color: '#8B949E',
                cursor: 'help',
              }}
            >
              {shortTraceId}
            </Typography>
          )}
          <Box sx={{ ml: 'auto' }}>
            <ReplayControls
              mode={replayState.mode}
              onSkip={replayState.skipReplay}
              onReplay={replayState.startReplay}
            />
          </Box>
        </Box>

        {trace.scenarioName && (
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#6E7681', mb: '2px' }}>
            {trace.scenarioName}
          </Typography>
        )}
        {trace.warehouseId && (
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58', mb: '4px' }}>
            {trace.warehouseId}
          </Typography>
        )}

        <StatusBadge status={trace.status} />
      </Box>

      <SectionDivider />

      {/* Timeline */}
      <SectionHeader label="Timeline" />

      {/* Opening animation preamble */}
      {showPreamble && (
        <Typography sx={{
          fontFamily: 'monospace',
          fontSize: '0.65rem',
          color: '#484F58',
          fontStyle: 'italic',
          mb: '4px',
        }}>
          TRACE INITIALIZING...
        </Typography>
      )}

      <DeveloperTraceTimeline
        events={trace.events}
        onOpenExplanation={onOpenExplanation}
        replayState={replayState}
      />

      <SectionDivider />

      {/* Artifact lineage */}
      <SectionHeader label="Artifact Lineage" />
      <DeveloperTraceArtifacts artifacts={trace.artifacts} />

      <SectionDivider />

      {/* Trace performance */}
      <SectionHeader label="Trace Performance" />
      <DeveloperTracePerformance timings={trace.timings} />
    </Box>
  );
}
