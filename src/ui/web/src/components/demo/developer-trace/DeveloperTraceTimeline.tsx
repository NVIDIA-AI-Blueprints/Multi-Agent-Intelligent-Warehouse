/**
 * DeveloperTraceTimeline.tsx — Chronological event list for the developer trace panel.
 *
 * Left column (48px): trace clock (+3.72s) or +?.??s if NOT_INSTRUMENTED — dim monospace
 * Right column: category badge + label + detail lines + timing notes
 *
 * Clock separation (Refinement 3):
 *   - traceClock shown in left gutter (TRACE TIME)
 *   - componentLatency shown as separate labeled row (MODEL LATENCY)
 *   - simulationClock shown as separate labeled row (SIMULATION TIME)
 *   — these three are never conflated
 */

import React, { useRef, useEffect } from 'react';
import { Box, Typography } from '@mui/material';
import { DeveloperTraceEvent, TraceEventCategory } from './developerTraceTypes';
import { ExplanationFocus } from '../decision-explanation/explanationTypes';
import { TraceReplayState, getPrimaryText } from './useTraceReplay';

// ── Category badge colors ──────────────────────────────────────────────────────

const CATEGORY_COLORS: Record<TraceEventCategory, string> = {
  OBSERVE:             '#484F58',
  STATE:               '#3FB950',
  AGENT:               '#58A6FF',
  MODEL_ROUTING:       '#A371F7',
  MODEL:               '#A371F7',
  SKILL:               '#3FB950',
  ASSESSMENT:          '#58A6FF',
  RECOMMENDATION:      '#58A6FF',
  PROPOSAL:            '#D29922',
  DECISION:            '#D29922',
  APPROVAL_WAIT:       '#484F58',
  APPROVAL:            '#3FB950',
  EXECUTION_BOUNDARY:  '#F85149',
  EXECUTION:           '#F85149',
  MCP:                 '#F85149',
  PROVIDER:            '#F85149',
  RECONCILIATION:      '#D29922',
  OUTCOME:             '#3FB950',
  ERROR:               '#F85149',
};

// ── Props ──────────────────────────────────────────────────────────────────────

interface DeveloperTraceTimelineProps {
  events: DeveloperTraceEvent[];
  onOpenExplanation?: (focus: ExplanationFocus) => void;
  // NEW: if provided, controls what's visible (replay animation)
  replayState?: TraceReplayState;
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function CategoryBadge({ category }: { category: TraceEventCategory }) {
  const color = CATEGORY_COLORS[category] ?? '#484F58';
  return (
    <Box
      component="span"
      sx={{
        fontFamily: 'monospace',
        fontSize: '0.55rem',
        fontWeight: 700,
        color,
        border: `1px solid ${color}44`,
        borderRadius: '3px',
        px: '4px',
        py: '1px',
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
        flexShrink: 0,
      }}
    >
      {category.replace(/_/g, ' ')}
    </Box>
  );
}

function ClockKindLabel({ label }: { label: string }) {
  return (
    <Typography
      component="span"
      sx={{
        fontFamily: 'monospace',
        fontSize: '0.52rem',
        color: '#30363D',
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        minWidth: 120,
        flexShrink: 0,
      }}
    >
      {label}
    </Typography>
  );
}

// ── Gap event (WAITING FOR OPERATOR) ─────────────────────────────────────────

function GapEvent({ event }: { event: DeveloperTraceEvent }) {
  const gapDisplay = event.detail?.replace('trace_observed_wait=', '');

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0, my: '4px' }}>
      <Box sx={{ flex: 1, height: '1px', background: '#21262D' }} />
      <Typography sx={{
        fontFamily: 'monospace',
        fontSize: '0.6rem',
        color: '#484F58',
        fontStyle: 'italic',
        px: 1.5,
        flexShrink: 0,
      }}>
        {event.label}
        {gapDisplay ? ` (~${gapDisplay} trace-observed)` : ''}
      </Typography>
      <Box sx={{ flex: 1, height: '1px', background: '#21262D' }} />
    </Box>
  );
}

// ── Execution boundary event ───────────────────────────────────────────────────

function ExecutionBoundaryEvent() {
  return (
    <Box sx={{ my: '6px' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0 }}>
        <Box sx={{ flex: 1, height: '1px', background: '#F8514988', borderTop: '1px dashed #F8514988' }} />
        <Typography sx={{
          fontFamily: 'monospace',
          fontSize: '0.6rem',
          color: '#F85149',
          px: 1.5,
          flexShrink: 0,
          opacity: 0.8,
          fontWeight: 700,
          letterSpacing: '0.1em',
        }}>
          EXECUTION BOUNDARY
        </Typography>
        <Box sx={{ flex: 1, height: '1px', borderTop: '1px dashed #F8514988' }} />
      </Box>
      <Typography sx={{
        fontFamily: 'monospace',
        fontSize: '0.58rem',
        color: '#484F58',
        textAlign: 'center',
        mt: '2px',
      }}>
        Post-boundary actions may mutate warehouse state
      </Typography>
    </Box>
  );
}

// ── Standard event row ─────────────────────────────────────────────────────────

function TraceEventRow({
  event,
  onOpenExplanation,
}: {
  event: DeveloperTraceEvent;
  onOpenExplanation?: (focus: ExplanationFocus) => void;
}) {
  const isClickable = !!event.explanationFocus && !!onOpenExplanation;
  const timeLabel = event.timingSource === 'NOT_INSTRUMENTED'
    ? '+?.??s'
    : event.traceClock?.display
    ?? (event.relativeMs === 0 ? '+0.00s' : undefined)
    ?? '+?.??s';

  const timeLabelDim = event.timingSource === 'NOT_INSTRUMENTED' || !event.traceClock;

  return (
    <Box
      onClick={isClickable ? () => onOpenExplanation!(event.explanationFocus!) : undefined}
      sx={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 1,
        py: '4px',
        px: '4px',
        borderRadius: '3px',
        cursor: isClickable ? 'pointer' : 'default',
        '&:hover': isClickable ? { background: '#161B22' } : undefined,
      }}
    >
      {/* Left column: trace clock */}
      <Typography sx={{
        fontFamily: 'monospace',
        fontSize: '0.62rem',
        color: timeLabelDim ? '#30363D' : '#6E7681',
        minWidth: 56,
        flexShrink: 0,
        mt: '2px',
        fontStyle: timeLabelDim ? 'italic' : 'normal',
      }}>
        {timeLabel}
      </Typography>

      {/* Right column */}
      <Box sx={{ flex: 1, minWidth: 0 }}>
        {/* Category + label row */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexWrap: 'wrap' }}>
          <CategoryBadge category={event.category} />
          <Typography sx={{
            fontFamily: 'monospace',
            fontSize: '0.65rem',
            color: '#C9D1D9',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            {event.label}
          </Typography>
          {isClickable && (
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#58A6FF', flexShrink: 0 }}>
              →
            </Typography>
          )}
        </Box>

        {/* Actor */}
        {event.actor && (
          <Typography sx={{
            fontFamily: 'monospace',
            fontSize: '0.58rem',
            color: '#484F58',
            fontStyle: 'italic',
            mt: '1px',
          }}>
            {event.actor}
          </Typography>
        )}

        {/* Detail */}
        {event.detail && (
          <Typography sx={{
            fontFamily: 'monospace',
            fontSize: '0.6rem',
            color: '#6E7681',
            mt: '2px',
            wordBreak: 'break-all',
          }}>
            {event.detail}
          </Typography>
        )}

        {/* Component latency (distinct from trace clock) */}
        {event.componentLatency && (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: '3px' }}>
            <ClockKindLabel label={event.componentLatency.label} />
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#A371F7', fontWeight: 700 }}>
              {event.componentLatency.display}
            </Typography>
          </Box>
        )}

        {/* Simulation clock (distinct from trace clock and component latency) */}
        {event.simulationClock && (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: '3px' }}>
            <ClockKindLabel label={event.simulationClock.label} />
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#58A6FF' }}>
              {event.simulationClock.display}
            </Typography>
          </Box>
        )}

        {/* Timing note (shown for NOT_INSTRUMENTED or special notes) */}
        {event.timingNote && (
          <Typography sx={{
            fontFamily: 'monospace',
            fontSize: '0.58rem',
            color: '#484F58',
            fontStyle: 'italic',
            mt: '2px',
          }}>
            Timing: {event.timingNote}
          </Typography>
        )}
      </Box>
    </Box>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

// ── In-progress row (typewriter cursor) ───────────────────────────────────────

function InProgressRow({
  event,
  charCount,
}: {
  event: DeveloperTraceEvent;
  charCount: number;
}) {
  const primaryText = getPrimaryText(event);
  const visibleText = primaryText.slice(0, charCount);
  const color = CATEGORY_COLORS[event.category] ?? '#484F58';

  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 0.75,
        py: '4px',
        px: '4px',
      }}
    >
      {/* Prompt indicator */}
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58', flexShrink: 0 }}>
        {'>'}
      </Typography>
      {/* Category badge */}
      <Box
        component="span"
        sx={{
          fontFamily: 'monospace',
          fontSize: '0.55rem',
          fontWeight: 700,
          color,
          border: `1px solid ${color}44`,
          borderRadius: '3px',
          px: '4px',
          py: '1px',
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          flexShrink: 0,
        }}
      >
        {event.category.replace(/_/g, ' ')}
      </Box>
      {/* Partially-typed text + cursor */}
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#8B949E' }}>
        {visibleText}
        <Box
          component="span"
          sx={{ color: '#484F58', fontSize: '0.7rem' }}
        >
          █
        </Box>
      </Typography>
    </Box>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function DeveloperTraceTimeline({ events, onOpenExplanation, replayState }: DeveloperTraceTimelineProps) {
  const inProgressRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll when activeEventIndex changes
  useEffect(() => {
    if (replayState && replayState.activeEventIndex >= 0 && inProgressRef.current) {
      inProgressRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [replayState?.activeEventIndex]); // eslint-disable-line react-hooks/exhaustive-deps

  // Determine which events to render
  const displayEvents = replayState ? replayState.visibleEvents : events;

  if (displayEvents.length === 0 && (!replayState || replayState.activeEventIndex < 0)) {
    return (
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#30363D' }}>
        No lifecycle events recorded yet.
      </Typography>
    );
  }

  // Active in-progress event
  const activeEvent =
    replayState && replayState.activeEventIndex >= 0
      ? events[replayState.activeEventIndex]
      : null;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      {displayEvents.map((ev) => {
        if (ev.isGap) {
          return <GapEvent key={ev.id} event={ev} />;
        }
        if (ev.isExecutionBoundary) {
          return <ExecutionBoundaryEvent key={ev.id} />;
        }
        return (
          <TraceEventRow
            key={ev.id}
            event={ev}
            onOpenExplanation={onOpenExplanation}
          />
        );
      })}
      {activeEvent && (
        <Box ref={inProgressRef}>
          <InProgressRow
            event={activeEvent}
            charCount={replayState!.activeCharCount}
          />
        </Box>
      )}
    </Box>
  );
}
