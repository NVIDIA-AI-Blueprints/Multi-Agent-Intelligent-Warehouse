/**
 * StageContentPane — routes to the active stage's detail component.
 *
 * OBSERVE / REASON / PROPOSE / DECIDE / APPROVE — complete (Phases 12C–12D).
 * EXECUTE / OUTCOME — complete (Phase 12E).
 * Phase 13C: STORY | DECISION GRAPH toggle for REASON through OUTCOME stages.
 */

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { Box, Typography } from '@mui/material';
import { RailStage } from '../../hooks/useDemoLifecycle';
import { SSEEvent } from '../../hooks/useDemoSSE';
import { DemoStatus, AnalysisResult, PendingApproval } from '../../services/demoAPI';
import DecisionGraph from './decision-graph/DecisionGraph';
import { buildDecisionGraph } from './decision-graph/buildDecisionGraph';
import DecisionExplanationDrawer from './decision-explanation/DecisionExplanationDrawer';
import { ExplanationFocus } from './decision-explanation/explanationTypes';

import ObserveStage  from './stages/ObserveStage';
import ReasonStage   from './stages/ReasonStage';
import ProposeStage  from './stages/ProposeStage';
import DecideStage   from './stages/DecideStage';
import ApproveStage  from './stages/ApproveStage';
import ExecuteStage  from './stages/ExecuteStage';
import OutcomeStage  from './stages/OutcomeStage';

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
  onReset?: () => void;
  /** Injected by StageContentPane — stage components may call this to open the explanation drawer. */
  onOpenExplanation?: (focus: ExplanationFocus) => void;
}

// ── Stages that support STORY/GRAPH toggle ────────────────────────────────────

const GRAPH_ENABLED_STAGES = new Set<RailStage>([
  'REASON', 'PROPOSE', 'DECIDE', 'APPROVE', 'EXECUTE', 'OUTCOME',
]);

// ── View-mode toggle ──────────────────────────────────────────────────────────

function ViewModeToggle({
  mode,
  onChange,
}: {
  mode: 'story' | 'graph';
  onChange: (m: 'story' | 'graph') => void;
}) {
  return (
    <Box sx={{ display: 'flex', gap: '2px', background: '#161B22', borderRadius: '5px', p: '3px', border: '1px solid #21262D' }}>
      {(['story', 'graph'] as const).map(m => (
        <Box
          key={m}
          component="button"
          data-testid={`view-mode-${m}`}
          onClick={() => onChange(m)}
          sx={{
            fontFamily: 'monospace',
            fontSize: '0.58rem',
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.1em',
            px: '10px',
            py: '4px',
            borderRadius: '3px',
            border: 'none',
            cursor: 'pointer',
            background: mode === m ? '#21262D' : 'transparent',
            color: mode === m ? '#C9D1D9' : '#484F58',
            transition: 'background 0.1s ease, color 0.1s ease',
          }}
        >
          {m === 'story' ? 'Story' : 'Decision Graph'}
        </Box>
      ))}
    </Box>
  );
}

// ── Router ─────────────────────────────────────────────────────────────────────

export default function StageContentPane(props: StageContentPaneProps) {
  const { currentStage, demoStatus, analysisResult, pendingApprovals } = props;

  // Reset to story mode whenever stage changes
  const [viewMode, setViewMode] = useState<'story' | 'graph'>('story');
  useEffect(() => { setViewMode('story'); }, [currentStage]);

  // Explanation drawer state
  const [explanationFocus, setExplanationFocus] = useState<ExplanationFocus | null>(null);
  const handleOpenExplanation = useCallback((focus: ExplanationFocus) => {
    setExplanationFocus(focus);
  }, []);
  const handleCloseExplanation = useCallback(() => {
    setExplanationFocus(null);
  }, []);
  // Reset explanation on stage change
  useEffect(() => { setExplanationFocus(null); }, [currentStage]);

  const showToggle = GRAPH_ENABLED_STAGES.has(currentStage);

  // Build graph lazily — only when graph mode is requested or about to be shown
  const graph = useMemo(() => {
    if (!showToggle) return null;
    return buildDecisionGraph({
      currentStage,
      demoStatus: demoStatus ?? null,
      analysisResult,
      pendingApprovals,
    });
  }, [currentStage, demoStatus, analysisResult, pendingApprovals, showToggle]);

  // Props enriched with explanation callback
  const stageProps = { ...props, onOpenExplanation: handleOpenExplanation };

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
      {/* Toggle bar — shown for REASON through OUTCOME */}
      {showToggle && (
        <Box sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-end',
          px: 3,
          pt: 2,
          pb: 0,
          maxWidth: viewMode === 'graph' ? 'none' : 880,
          width: '100%',
          mx: 'auto',
        }}>
          <ViewModeToggle mode={viewMode} onChange={setViewMode} />
        </Box>
      )}

      {/* Content area — position: relative for explanation drawer overlay */}
      <Box sx={{ position: 'relative', flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        {viewMode === 'graph' && showToggle && graph ? (
          <Box sx={{ px: 3, py: 2, overflow: 'auto', flex: 1 }}>
            <DecisionGraph
              graph={graph}
              analysisResult={analysisResult}
              pendingApprovals={pendingApprovals}
              demoStatus={demoStatus}
              onOpenExplanation={handleOpenExplanation}
            />
          </Box>
        ) : (
          <Box sx={{ maxWidth: 880, width: '100%', mx: 'auto', px: 3, py: 2.5, flex: 1 }}>
            {currentStage === 'OBSERVE'  && <ObserveStage  {...stageProps} />}
            {currentStage === 'REASON'   && <ReasonStage   {...stageProps} />}
            {currentStage === 'PROPOSE'  && <ProposeStage  {...stageProps} />}
            {currentStage === 'DECIDE'   && <DecideStage   {...stageProps} />}
            {currentStage === 'APPROVE'  && <ApproveStage  {...stageProps} />}
            {currentStage === 'EXECUTE'  && <ExecuteStage  {...stageProps} />}
            {currentStage === 'OUTCOME'  && <OutcomeStage  {...stageProps} />}
          </Box>
        )}

        {/* Explanation drawer overlay */}
        {explanationFocus !== null && graph && (
          <DecisionExplanationDrawer
            focus={explanationFocus}
            graph={graph}
            analysisResult={analysisResult}
            pendingApprovals={pendingApprovals}
            demoStatus={demoStatus}
            onClose={handleCloseExplanation}
          />
        )}
      </Box>
    </Box>
  );
}
