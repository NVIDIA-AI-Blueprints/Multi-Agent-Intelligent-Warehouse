/**
 * ObserveStage — shows the current warehouse snapshot and triggers MAIW analysis.
 *
 * Data sources (in priority order):
 *   1. demoStatus.world / demoStatus.current_kpis  — always available when scenario active
 *   2. SSE OBSERVE events                           — live during analysis
 *   3. analysisResult.assessment.facts_observed     — available post-analysis
 */

import React from 'react';
import { Box, CircularProgress, Typography } from '@mui/material';
import {
  SectionHeader,
  StageSection,
  MonoText,
  RiskBadge,
  IdText,
  parseDetail,
  runWindowEvents,
  StageContentPaneProps,
} from '../StageContentPane';

// ── Warehouse world grid ───────────────────────────────────────────────────────

function WorldGrid({ world }: { world: NonNullable<StageContentPaneProps['demoStatus']['world']> }) {
  const cells: Array<{ label: string; primary: string; secondary?: string }> = [
    {
      label: 'Equipment',
      primary: `${world.equipment.available} / ${world.equipment.total}`,
      secondary: world.equipment.offline > 0 ? `${world.equipment.offline} offline` : undefined,
    },
    {
      label: 'Workers',
      primary: `${world.workers.active} / ${world.workers.total}`,
      secondary: world.workers.inactive > 0 ? `${world.workers.inactive} inactive` : undefined,
    },
    {
      label: 'Pending tasks',
      primary: String(world.tasks.pending),
      secondary: world.tasks.in_progress > 0 ? `${world.tasks.in_progress} in-progress` : undefined,
    },
    {
      label: 'Inventory SKUs',
      primary: String(world.inventory.total_skus),
      secondary: world.inventory.low_stock > 0 ? `${world.inventory.low_stock} low-stock` : undefined,
    },
  ];

  return (
    <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 1.5 }}>
      {cells.map(c => (
        <Box
          key={c.label}
          sx={{
            background: '#161B22',
            border: '1px solid #21262D',
            borderRadius: '4px',
            px: 1.5,
            py: 1,
          }}
        >
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58', textTransform: 'uppercase', letterSpacing: '0.1em', mb: '3px' }}>
            {c.label}
          </Typography>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.82rem', fontWeight: 700, color: '#C9D1D9' }}>
            {c.primary}
          </Typography>
          {c.secondary && (
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58', mt: '2px' }}>
              {c.secondary}
            </Typography>
          )}
        </Box>
      ))}
    </Box>
  );
}

// ── State freshness indicator ──────────────────────────────────────────────────

function FreshnessTag({ seconds }: { seconds: number | null | undefined }) {
  if (seconds == null) return null;
  const color = seconds < 60 ? '#3FB950' : seconds < 120 ? '#D29922' : '#F85149';
  const label = seconds < 60 ? `${Math.round(seconds)}s old` : `${Math.round(seconds / 60)}m old`;
  return (
    <Box component="span" sx={{
      fontFamily: 'monospace',
      fontSize: '0.58rem',
      color,
      border: `1px solid ${color}33`,
      borderRadius: '3px',
      px: '4px',
      py: '1px',
    }}>
      state {label}
    </Box>
  );
}

// ── SSE event list (live feed during analysis) ─────────────────────────────────

function ObserveEventList({ events }: { events: ReturnType<typeof runWindowEvents> }) {
  if (events.length === 0) return null;
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
      {events.map(ev => {
        const detail = parseDetail(ev.detail);
        return (
          <Box key={ev.id} sx={{ display: 'flex', alignItems: 'baseline', gap: 1.5 }}>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58', flexShrink: 0 }}>
              {detail.snapshot ? `snapshot=${detail.snapshot}` : (detail.trace ? `trace=${detail.trace}` : '')}
            </Typography>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', color: '#8B949E' }}>
              {ev.message}
            </Typography>
          </Box>
        );
      })}
    </Box>
  );
}

// ── Run Analysis button ────────────────────────────────────────────────────────

function AnalyzeCTA({ onAnalyze, analyzing }: { onAnalyze: () => Promise<void>; analyzing: boolean }) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 1.5 }}>
      <Box
        component="button"
        onClick={() => { if (!analyzing) onAnalyze(); }}
        disabled={analyzing}
        data-testid="run-analysis-button"
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1.25,
          background: analyzing ? '#0d2146' : '#1C2128',
          border: `1px solid ${analyzing ? '#1F6FEB66' : '#1F6FEB'}`,
          borderRadius: '5px',
          px: '14px',
          py: '8px',
          fontFamily: 'monospace',
          fontSize: '0.72rem',
          fontWeight: 700,
          color: analyzing ? '#58A6FF88' : '#58A6FF',
          cursor: analyzing ? 'wait' : 'pointer',
          letterSpacing: '0.04em',
          textTransform: 'uppercase',
          transition: 'all 0.15s ease',
          '&:hover:not(:disabled)': {
            background: '#162032',
            borderColor: '#388BFD',
          },
        }}
      >
        {analyzing && <CircularProgress size={12} sx={{ color: '#58A6FF66' }} />}
        {analyzing ? 'MAIW Analyzing...' : '▶ Run MAIW Analysis'}
      </Box>
      {!analyzing && (
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#484F58' }}>
          Triggers observe → reason → propose → decide pipeline
        </Typography>
      )}
    </Box>
  );
}

// ── ObserveStage ──────────────────────────────────────────────────────────────

export default function ObserveStage({
  demoStatus,
  sseEvents,
  analysisResult,
  analyzing,
  onAnalyze,
}: StageContentPaneProps) {
  const { world, current_kpis, scenario } = demoStatus;
  const observeEvents = runWindowEvents(sseEvents, ['OBSERVE']);
  const assessment = analysisResult?.assessment;
  const observeLifecycle = analysisResult?.lifecycle?.find(
    r => r.phase === 'OBSERVE' && r.snapshot_id,
  );

  return (
    <Box data-testid="observe-stage">
      {/* Stage header */}
      <StageSection>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.5 }}>
          <Typography sx={{
            fontFamily: 'monospace', fontSize: '0.72rem', fontWeight: 700,
            color: '#58A6FF', textTransform: 'uppercase', letterSpacing: '0.06em',
          }}>
            Observe
          </Typography>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58' }}>
            Warehouse State Assembly
          </Typography>
          {current_kpis && (
            <Box sx={{ ml: 'auto' }}>
              <FreshnessTag seconds={current_kpis.state_freshness_seconds} />
            </Box>
          )}
        </Box>
        {scenario && (
          <MonoText color="#484F58" size="0.62rem">
            {scenario.display_name ?? scenario.name}
          </MonoText>
        )}
      </StageSection>

      {/* Warehouse snapshot */}
      {world && (
        <StageSection>
          <SectionHeader>Warehouse snapshot — t={world.elapsed_seconds}s</SectionHeader>
          <WorldGrid world={world} />
        </StageSection>
      )}

      {/* KPI context */}
      {current_kpis && (
        <StageSection>
          <SectionHeader>Operational context</SectionHeader>
          <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
            <Box>
              <MonoText color="#484F58" size="0.58rem">Equipment</MonoText>
              <MonoText color="#C9D1D9" weight={700}>
                {Math.round(current_kpis.equipment_operational_pct)}%
              </MonoText>
            </Box>
            <Box>
              <MonoText color="#484F58" size="0.58rem">Labor</MonoText>
              <MonoText color="#C9D1D9" weight={700}>
                {Math.round(current_kpis.labor_availability_pct)}%
              </MonoText>
            </Box>
            <Box>
              <MonoText color="#484F58" size="0.58rem">Backlog</MonoText>
              <MonoText color="#C9D1D9" weight={700}>
                {current_kpis.pending_backlog}
              </MonoText>
            </Box>
            <Box>
              <MonoText color="#484F58" size="0.58rem">Wave risk</MonoText>
              <Box sx={{ mt: '2px' }}>
                <RiskBadge level={current_kpis.wave_risk_level} />
              </Box>
            </Box>
          </Box>
        </StageSection>
      )}

      {/* Snapshot metadata (post-analysis) */}
      {observeLifecycle && (
        <StageSection>
          <SectionHeader>Snapshot</SectionHeader>
          <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
            <IdText label="ID" value={observeLifecycle.snapshot_id ?? '—'} />
            <IdText label="Warehouse" value={observeLifecycle.warehouse_id ?? '—'} />
            <Box>
              <MonoText color="#484F58" size="0.58rem">Domains</MonoText>
              <MonoText color="#8B949E" size="0.65rem">equipment · labor · waves</MonoText>
            </Box>
          </Box>
        </StageSection>
      )}

      {/* Facts observed (post-analysis) */}
      {assessment?.facts_observed && assessment.facts_observed.length > 0 && (
        <StageSection>
          <SectionHeader>Facts observed</SectionHeader>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
            {assessment.facts_observed.map((fact, i) => (
              <Box key={i} sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58', flexShrink: 0, mt: '1px' }}>
                  ·
                </Typography>
                <MonoText color="#8B949E" size="0.68rem">{fact}</MonoText>
              </Box>
            ))}
          </Box>
        </StageSection>
      )}

      {/* SSE live events */}
      {observeEvents.length > 0 && (
        <StageSection>
          <SectionHeader>Pipeline events</SectionHeader>
          <ObserveEventList events={observeEvents} />
        </StageSection>
      )}

      {/* Run analysis CTA — shown when not yet analyzed */}
      {!analysisResult && (
        <StageSection last>
          <AnalyzeCTA onAnalyze={onAnalyze} analyzing={analyzing} />
        </StageSection>
      )}

      {/* Re-run option after analysis (compact) */}
      {analysisResult && (
        <StageSection last>
          <Box
            component="button"
            onClick={() => { if (!analyzing) onAnalyze(); }}
            disabled={analyzing}
            data-testid="rerun-analysis-button"
            sx={{
              background: 'transparent',
              border: '1px solid #21262D',
              borderRadius: '4px',
              px: '10px',
              py: '4px',
              fontFamily: 'monospace',
              fontSize: '0.62rem',
              color: '#484F58',
              cursor: analyzing ? 'wait' : 'pointer',
              '&:hover:not(:disabled)': { color: '#8B949E', borderColor: '#30363D' },
            }}
          >
            {analyzing ? 'Analyzing...' : '↺ Re-run analysis'}
          </Box>
        </StageSection>
      )}
    </Box>
  );
}
