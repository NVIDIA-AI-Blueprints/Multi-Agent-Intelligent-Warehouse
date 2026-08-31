/**
 * ExplanationSection.tsx — styled sub-components for the DecisionExplanationDrawer (Phase 13D).
 *
 * Named exports only — no default export.
 * Matches the MAIW dark terminal aesthetic.
 */

import React, { useState } from 'react';
import { Box, Typography } from '@mui/material';
import { NodeSource } from '../decision-graph/graphTypes';
import { ExplanationEvidence, ExplanationTraceIds } from './explanationTypes';

// ── BreadcrumbBar ──────────────────────────────────────────────────────────────

export function BreadcrumbBar({ steps }: { steps: string[] }) {
  if (steps.length === 0) return null;
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 0 }}>
      {steps.map((s, i) => (
        <React.Fragment key={s}>
          <Typography sx={{
            fontFamily: 'monospace',
            fontSize: '0.58rem',
            color: i === steps.length - 1 ? '#58A6FF' : '#484F58',
            fontWeight: i === steps.length - 1 ? 700 : 400,
            letterSpacing: '0.06em',
          }}>
            {s}
          </Typography>
          {i < steps.length - 1 && (
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#30363D', px: '4px' }}>
              →
            </Typography>
          )}
        </React.Fragment>
      ))}
    </Box>
  );
}

// ── SectionLabel ───────────────────────────────────────────────────────────────

export function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <Typography sx={{
      fontFamily: 'monospace',
      fontSize: '0.58rem',
      fontWeight: 700,
      color: '#484F58',
      letterSpacing: '0.12em',
      textTransform: 'uppercase',
      mb: 0.5,
    }}>
      {children}
    </Typography>
  );
}

// ── DrawerDivider ──────────────────────────────────────────────────────────────

export function DrawerDivider() {
  return <Box sx={{ borderBottom: '1px solid #21262D', my: 1.5 }} />;
}

// ── SourceBadge ────────────────────────────────────────────────────────────────

const SOURCE_COLOR: Record<NodeSource, string> = {
  LIVE:               '#3FB950',
  DERIVED:            '#D29922',
  VALIDATED_ARTIFACT: '#58A6FF',
  LOCAL:              '#484F58',
};

export function SourceBadge({ source }: { source: NodeSource }) {
  const color = SOURCE_COLOR[source] ?? '#484F58';
  return (
    <Box component="span" sx={{
      fontFamily: 'monospace',
      fontSize: '0.55rem',
      fontWeight: 700,
      color,
      border: `1px solid ${color}44`,
      borderRadius: '3px',
      px: '5px',
      py: '1px',
      textTransform: 'uppercase',
      letterSpacing: '0.08em',
    }}>
      {source.replace('_', ' ')}
    </Box>
  );
}

// ── EvidenceRow ────────────────────────────────────────────────────────────────

export function EvidenceRow({ label, value, suffix, source }: ExplanationEvidence) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1, py: '2px' }}>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58', minWidth: 80, flexShrink: 0 }}>
        {label}
      </Typography>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', color: '#C9D1D9', flex: 1 }}>
        {String(value)}{suffix ? ` ${suffix}` : ''}
      </Typography>
      <SourceBadge source={source} />
    </Box>
  );
}

// ── KPIDeltaRow ────────────────────────────────────────────────────────────────

interface KPIDeltaRowProps {
  label: string;
  pre: number | null | undefined;
  post: number | null | undefined;
  delta: number | null | undefined;
  suffix?: string;
  positiveIsBetter: boolean;
}

function fmtVal(v: number | null | undefined, suffix = ''): string {
  if (v == null) return '—';
  return `${v.toFixed(1)}${suffix}`;
}

function deltaColor(v: number | null | undefined, positiveIsBetter: boolean): string {
  if (v == null || v === 0) return '#6E7681';
  const good = positiveIsBetter ? v > 0 : v < 0;
  return good ? '#3FB950' : '#F85149';
}

export function KPIDeltaRow({ label, pre, post, delta, suffix = '', positiveIsBetter }: KPIDeltaRowProps) {
  const color = deltaColor(delta, positiveIsBetter);
  const deltaText = delta == null ? '—' : `${delta > 0 ? '+' : ''}${delta.toFixed(1)}${suffix}`;
  return (
    <Box sx={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr 1fr 1fr', gap: 0.5, py: '4px', borderBottom: '1px solid #1C2128' }}>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#6E7681' }}>{label}</Typography>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#8B949E' }}>{fmtVal(pre, suffix)}</Typography>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#C9D1D9' }}>{fmtVal(post, suffix)}</Typography>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color, fontWeight: delta ? 700 : 400 }}>{deltaText}</Typography>
    </Box>
  );
}

// ── TraceSection ───────────────────────────────────────────────────────────────

export function TraceSection({ traceIds }: { traceIds: ExplanationTraceIds }) {
  const [open, setOpen] = useState(false);

  const entries = Object.entries(traceIds).filter(([, v]) => v != null) as Array<[string, string]>;
  if (entries.length === 0) return null;

  return (
    <Box sx={{ mt: 0.5 }}>
      <Box
        component="button"
        onClick={() => setOpen(o => !o)}
        data-testid="trace-details-toggle"
        sx={{
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: 0.75,
          px: 0,
          py: '4px',
        }}
      >
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58' }}>
          {open ? '▾' : '▸'}
        </Typography>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
          TRACE DETAILS
        </Typography>
      </Box>
      {open && (
        <Box sx={{ mt: 0.5, pl: 1.5, display: 'flex', flexDirection: 'column', gap: 0.25 }}>
          {entries.map(([k, v]) => (
            <Box key={k} sx={{ display: 'flex', alignItems: 'baseline', gap: 0.75 }}>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58', minWidth: 84 }}>
                {k}:
              </Typography>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#6E7681', wordBreak: 'break-all' }}>
                {v}
              </Typography>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
}
