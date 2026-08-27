/**
 * StageContentPane — routes to the active stage's detail component.
 *
 * OBSERVE / REASON / PROPOSE / DECIDE have full implementations (Phase 12C).
 * APPROVE / EXECUTE / OUTCOME are placeholders until 12D / 12E.
 */

import React from 'react';
import { Box, Typography } from '@mui/material';
import { RailStage } from '../../hooks/useDemoLifecycle';
import { SSEEvent } from '../../hooks/useDemoSSE';
import { DemoStatus, AnalysisResult, PendingApproval } from '../../services/demoAPI';

import ObserveStage  from './stages/ObserveStage';
import ReasonStage   from './stages/ReasonStage';
import ProposeStage  from './stages/ProposeStage';
import DecideStage   from './stages/DecideStage';
import ApproveStage  from './stages/ApproveStage';

// ── Shared utilities exported for stage components ─────────────────────────────

/** Parse "key=value key2=value2" SSE detail strings. */
export function parseDetail(detail: string | null | undefined): Record<string, string> {
  if (!detail) return {};
  const out: Record<string, string> = {};
  for (const token of detail.split(' ')) {
    const eq = token.indexOf('=');
    if (eq > 0) out[token.slice(0, eq)] = token.slice(eq + 1);
  }
  return out;
}

/** Extract events for the current run window and filter by category. */
export function runWindowEvents(
  sseEvents: SSEEvent[],
  categories: string[],
): SSEEvent[] {
  const observeIdx = sseEvents.findIndex(ev => ev.category === 'OBSERVE');
  const window = observeIdx >= 0 ? sseEvents.slice(0, observeIdx + 1) : sseEvents;
  // Filter and reverse to chronological order for display
  return window.filter(ev => categories.includes(ev.category)).reverse();
}

// ── Shared sub-components ──────────────────────────────────────────────────────

export function SectionHeader({ children }: { children: React.ReactNode }) {
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
      {children}
    </Typography>
  );
}

export function StageSection({ children, last }: { children: React.ReactNode; last?: boolean }) {
  return (
    <Box sx={{
      pb: last ? 0 : 2,
      mb: last ? 0 : 2,
      borderBottom: last ? 'none' : '1px solid #21262D',
    }}>
      {children}
    </Box>
  );
}

export function MonoText({
  children,
  color = '#C9D1D9',
  size = '0.75rem',
  weight = 400,
}: {
  children: React.ReactNode;
  color?: string;
  size?: string;
  weight?: number;
}) {
  return (
    <Typography sx={{ fontFamily: 'monospace', fontSize: size, color, fontWeight: weight, lineHeight: 1.5 }}>
      {children}
    </Typography>
  );
}

const RISK_COLOR: Record<string, string> = {
  none:     '#484F58',
  low:      '#3FB950',
  medium:   '#D29922',
  high:     '#F85149',
  critical: '#F85149',
};

export function RiskBadge({ level }: { level: string }) {
  const color = RISK_COLOR[level?.toLowerCase()] ?? '#484F58';
  return (
    <Box component="span" sx={{
      fontFamily: 'monospace',
      fontSize: '0.62rem',
      fontWeight: 700,
      color,
      border: `1px solid ${color}44`,
      borderRadius: '3px',
      px: '5px',
      py: '1px',
      textTransform: 'uppercase',
      letterSpacing: '0.08em',
    }}>
      {level}
    </Box>
  );
}

export function OutcomeBadge({ outcome }: { outcome: string }) {
  const color =
    outcome === 'APPROVED'               ? '#3FB950' :
    outcome === 'REQUIRES_HUMAN_APPROVAL'? '#D29922' :
    outcome === 'REJECTED'               ? '#F85149' : '#484F58';
  const label =
    outcome === 'REQUIRES_HUMAN_APPROVAL' ? 'REQUIRES APPROVAL' : outcome;

  return (
    <Box component="span" sx={{
      fontFamily: 'monospace',
      fontSize: '0.62rem',
      fontWeight: 700,
      color,
      border: `1px solid ${color}44`,
      borderRadius: '3px',
      px: '5px',
      py: '1px',
      textTransform: 'uppercase',
      letterSpacing: '0.08em',
    }}>
      {label}
    </Box>
  );
}

export function IdText({ label, value }: { label: string; value: string }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 0.75 }}>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
        {label}
      </Typography>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#8B949E', letterSpacing: '0.04em' }}>
        {value}
      </Typography>
    </Box>
  );
}

// ── Placeholder for phases not yet implemented ─────────────────────────────────

function ComingSoonPane({ stage, phase }: { stage: string; phase: string }) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 1, py: 6 }}>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.72rem', color: '#484F58' }}>
        {stage}
      </Typography>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#30363D' }}>
        Stage details arrive in {phase}.
      </Typography>
    </Box>
  );
}

// ── StageContentPaneProps ─────────────────────────────────────────────────────

export interface StageContentPaneProps {
  currentStage: RailStage;
  sseEvents: SSEEvent[];
  demoStatus: DemoStatus;
  analysisResult: AnalysisResult | null;
  pendingApprovals: PendingApproval[];
  analyzing: boolean;
  onAnalyze: () => Promise<void>;
}

// ── Router ─────────────────────────────────────────────────────────────────────

export default function StageContentPane(props: StageContentPaneProps) {
  const { currentStage } = props;

  return (
    <Box
      data-testid="stage-content-pane"
      sx={{
        flexGrow: 1,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'auto',
        background: '#0D1117',
      }}
    >
      <Box sx={{ maxWidth: 880, width: '100%', mx: 'auto', px: 3, py: 2.5 }}>
        {currentStage === 'OBSERVE'  && <ObserveStage  {...props} />}
        {currentStage === 'REASON'   && <ReasonStage   {...props} />}
        {currentStage === 'PROPOSE'  && <ProposeStage  {...props} />}
        {currentStage === 'DECIDE'   && <DecideStage   {...props} />}
        {currentStage === 'APPROVE'  && <ApproveStage   {...props} />}
        {currentStage === 'EXECUTE'  && <ComingSoonPane stage="EXECUTE" phase="Phase 12E" />}
        {currentStage === 'OUTCOME'  && <ComingSoonPane stage="OUTCOME" phase="Phase 12E" />}
      </Box>
    </Box>
  );
}
