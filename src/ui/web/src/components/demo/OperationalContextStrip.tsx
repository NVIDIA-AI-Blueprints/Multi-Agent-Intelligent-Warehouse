import React from 'react';
import { Box, Typography } from '@mui/material';
import { KPISnapshot } from '../../services/demoAPI';

// ── Risk level color ───────────────────────────────────────────────────────────

const RISK_COLOR: Record<string, string> = {
  none:     '#484F58',
  low:      '#3FB950',
  medium:   '#D29922',
  high:     '#D29922',
  critical: '#F85149',
};

function riskColor(level: string | null | undefined): string {
  return RISK_COLOR[level ?? 'none'] ?? '#484F58';
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function pctColor(pct: number): string {
  if (pct >= 80) return '#3FB950';
  if (pct >= 50) return '#D29922';
  return '#F85149';
}

function backlogColor(count: number): string {
  if (count === 0) return '#484F58';
  if (count <= 3)  return '#D29922';
  return '#F85149';
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function Divider() {
  return (
    <Box
      aria-hidden="true"
      sx={{ width: '1px', height: 24, background: '#21262D', flexShrink: 0 }}
    />
  );
}

interface KpiCellProps {
  label: string;
  value: string;
  color: string;
  testId?: string;
}

function KpiCell({ label, value, color, testId }: KpiCellProps) {
  return (
    <Box
      data-testid={testId}
      sx={{ display: 'flex', flexDirection: 'column', gap: '2px', flexShrink: 0 }}
    >
      <Typography
        sx={{
          fontFamily: 'monospace',
          fontSize: '0.52rem',
          color: '#484F58',
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
          lineHeight: 1,
        }}
      >
        {label}
      </Typography>
      <Typography
        sx={{
          fontFamily: 'monospace',
          fontSize: '0.82rem',
          fontWeight: 700,
          color,
          lineHeight: 1,
        }}
      >
        {value}
      </Typography>
    </Box>
  );
}

// ── OperationalContextStrip ────────────────────────────────────────────────────

interface Props {
  kpis: KPISnapshot | null;
}

export default function OperationalContextStrip({ kpis }: Props) {
  if (!kpis) {
    return (
      <Box
        role="region"
        aria-label="Operational context loading"
        data-testid="operational-context-strip"
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 2,
          px: 2,
          py: '7px',
          background: '#161B22',
          borderBottom: '1px solid #21262D',
        }}
      >
        <Typography
          sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58' }}
        >
          Warehouse state — loading...
        </Typography>
      </Box>
    );
  }

  const equipPct   = Math.round(kpis.equipment_operational_pct);
  const laborPct   = Math.round(kpis.labor_availability_pct);
  const backlog    = kpis.pending_backlog;
  const riskLevel  = kpis.wave_risk_level ?? 'none';

  return (
    <Box
      role="region"
      aria-label={`Warehouse: Equipment ${equipPct}%, Labor ${laborPct}%, Backlog ${backlog}, Wave risk ${riskLevel}`}
      data-testid="operational-context-strip"
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 2,
        px: 2,
        py: '7px',
        background: '#161B22',
        borderBottom: '1px solid #21262D',
      }}
    >
      <Typography
        aria-hidden="true"
        sx={{
          fontFamily: 'monospace',
          fontSize: '0.52rem',
          color: '#484F58',
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
          flexShrink: 0,
          alignSelf: 'center',
        }}
      >
        Warehouse
      </Typography>

      <Divider />

      <KpiCell
        label="Equipment"
        value={`${equipPct}%`}
        color={pctColor(equipPct)}
        testId="kpi-equipment"
      />

      <Divider />

      <KpiCell
        label="Labor"
        value={`${laborPct}%`}
        color={pctColor(laborPct)}
        testId="kpi-labor"
      />

      <Divider />

      <KpiCell
        label="Backlog"
        value={String(backlog)}
        color={backlogColor(backlog)}
        testId="kpi-backlog"
      />

      <Divider />

      <KpiCell
        label="Wave risk"
        value={riskLevel.toUpperCase()}
        color={riskColor(riskLevel)}
        testId="kpi-wave-risk"
      />
    </Box>
  );
}
