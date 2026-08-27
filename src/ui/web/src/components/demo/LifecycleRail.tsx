import React from 'react';
import { Box, Typography } from '@mui/material';
import { STAGE_ORDER, RailStage } from '../../hooks/useDemoLifecycle';

// ── Stage metadata ─────────────────────────────────────────────────────────────

const STAGE_META: Record<RailStage, { num: string; label: string; subtitle?: string }> = {
  OBSERVE:  { num: '01', label: 'Observe' },
  REASON:   { num: '02', label: 'Reason' },
  PROPOSE:  { num: '03', label: 'Propose' },
  DECIDE:   { num: '04', label: 'Decide' },
  APPROVE:  { num: '05', label: 'Approve' },
  EXECUTE:  { num: '06', label: 'Execute' },
  OUTCOME:  { num: '07', label: 'Outcome', subtitle: 'Observe operational effect' },
};

// ── State encoding ─────────────────────────────────────────────────────────────
// Color is never the sole indicator of state — each state has a distinct symbol.

type StageState = 'complete' | 'current' | 'waiting' | 'upcoming';

const STATE_SYMBOL: Record<StageState, string> = {
  complete: '✓',
  current:  '●',
  waiting:  '●',   // same symbol, different color
  upcoming: '○',
};

const STATE_COLOR: Record<StageState, string> = {
  complete: '#3FB950',
  current:  '#58A6FF',
  waiting:  '#D29922',
  upcoming: '#30363D',
};

const STATE_LABEL: Record<StageState, string> = {
  complete: 'complete',
  current:  'current',
  waiting:  'waiting for approval',
  upcoming: 'upcoming',
};

// ── Helpers ────────────────────────────────────────────────────────────────────

function resolveState(
  stage: RailStage,
  currentStage: RailStage,
  completedStages: ReadonlySet<RailStage>,
  waitingForApproval: boolean,
): StageState {
  if (completedStages.has(stage)) return 'complete';
  if (stage === currentStage) {
    return stage === 'APPROVE' && waitingForApproval ? 'waiting' : 'current';
  }
  return 'upcoming';
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function Connector({ complete }: { complete: boolean }) {
  return (
    <Box
      aria-hidden="true"
      sx={{
        flex: 1,
        height: '1px',
        background: complete ? '#3FB950' : '#21262D',
        alignSelf: 'center',
        minWidth: 8,
        mx: 0.75,
      }}
    />
  );
}

function StageNode({
  stage,
  state,
  isCurrent,
}: {
  stage: RailStage;
  state: StageState;
  isCurrent: boolean;
}) {
  const meta = STAGE_META[stage];
  const color = STATE_COLOR[state];
  const symbol = STATE_SYMBOL[state];

  return (
    <Box
      data-testid={`lifecycle-stage-${stage.toLowerCase()}`}
      aria-label={`${meta.label}: ${STATE_LABEL[state]}`}
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '2px',
        flexShrink: 0,
        px: 0.25,
      }}
    >
      {/* Symbol — aria-hidden because the node aria-label carries the full state */}
      <Typography
        aria-hidden="true"
        sx={{
          fontFamily: 'monospace',
          fontSize: isCurrent ? '0.82rem' : '0.68rem',
          color,
          lineHeight: 1,
          fontWeight: isCurrent ? 700 : 400,
          transition: 'font-size 0.15s ease',
        }}
      >
        {symbol}
      </Typography>

      {/* Step number */}
      <Typography
        aria-hidden="true"
        sx={{
          fontFamily: 'monospace',
          fontSize: '0.52rem',
          color: '#484F58',
          letterSpacing: '0.05em',
          lineHeight: 1,
        }}
      >
        {meta.num}
      </Typography>

      {/* Stage name */}
      <Typography
        aria-hidden="true"
        sx={{
          fontFamily: 'monospace',
          fontSize: isCurrent ? '0.72rem' : '0.65rem',
          fontWeight: isCurrent ? 700 : 400,
          color: state === 'upcoming' ? '#30363D' : color,
          letterSpacing: '0.04em',
          textTransform: 'uppercase',
          lineHeight: 1,
        }}
      >
        {meta.label}
      </Typography>

      {/* Subtitle — only for OUTCOME and only when not upcoming */}
      {meta.subtitle && state !== 'upcoming' && (
        <Typography
          aria-hidden="true"
          sx={{
            fontFamily: 'monospace',
            fontSize: '0.5rem',
            color: '#484F58',
            letterSpacing: '0.02em',
            lineHeight: 1,
            textAlign: 'center',
            maxWidth: 68,
          }}
        >
          {meta.subtitle}
        </Typography>
      )}
    </Box>
  );
}

// ── LifecycleRail ──────────────────────────────────────────────────────────────

export interface LifecycleRailProps {
  currentStage: RailStage;
  completedStages: ReadonlySet<RailStage>;
  waitingForApproval: boolean;
}

export default function LifecycleRail({
  currentStage,
  completedStages,
  waitingForApproval,
}: LifecycleRailProps) {
  // Build a screen-reader summary of the pipeline state
  const srSummary = STAGE_ORDER.map(s => {
    const state = resolveState(s, currentStage, completedStages, waitingForApproval);
    return `${STAGE_META[s].label} ${STATE_LABEL[state]}`;
  }).join(', ');

  return (
    <Box
      role="region"
      aria-label={`MAIW pipeline: ${srSummary}`}
      data-testid="lifecycle-rail"
      sx={{
        display: 'flex',
        alignItems: 'center',
        px: 2,
        py: 1.25,
        background: '#0D1117',
        borderBottom: '1px solid #21262D',
        // Horizontal scroll on narrow viewports — stages never wrap
        overflowX: 'auto',
        overflowY: 'visible',
        scrollbarWidth: 'none',
        '&::-webkit-scrollbar': { display: 'none' },
      }}
    >
      {STAGE_ORDER.map((stage, idx) => {
        const state = resolveState(stage, currentStage, completedStages, waitingForApproval);
        const isCurrent = stage === currentStage;

        return (
          <React.Fragment key={stage}>
            <StageNode stage={stage} state={state} isCurrent={isCurrent} />
            {idx < STAGE_ORDER.length - 1 && (
              <Connector complete={state === 'complete'} />
            )}
          </React.Fragment>
        );
      })}
    </Box>
  );
}
