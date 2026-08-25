import React, { useMemo } from 'react';
import { Box, Typography, CircularProgress, Alert } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { demoAPI, CounterfactualRun, CounterfactualResult } from '../../services/demoAPI';

// ── Tiny primitives ───────────────────────────────────────────────────────────

function Mono({ children, color, size = '0.75rem' }: { children: React.ReactNode; color?: string; size?: string }) {
  return (
    <Typography sx={{ fontFamily: 'monospace', fontSize: size, color: color ?? '#C9D1D9', lineHeight: 1.5 }}>
      {children}
    </Typography>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <Typography sx={{
      fontFamily: 'monospace', fontWeight: 700, fontSize: '0.6rem',
      color: '#484F58', letterSpacing: '0.12em', textTransform: 'uppercase', mb: 0.5,
    }}>
      {children}
    </Typography>
  );
}

function Card({ children, sx }: { children: React.ReactNode; sx?: object }) {
  return (
    <Box sx={{ background: '#0D1117', border: '1px solid #21262D', borderRadius: 1, p: 1.5, ...sx }}>
      {children}
    </Box>
  );
}

// ── Summary tile ──────────────────────────────────────────────────────────────

function SummaryTile({
  title, ctrlLabel, ctrlValue, maiwLabel, maiwValue, delta, deltaColor,
}: {
  title: string;
  ctrlLabel: string; ctrlValue: string;
  maiwLabel: string; maiwValue: string;
  delta?: string; deltaColor?: string;
}) {
  return (
    <Card>
      <Label>{title}</Label>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.35 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <Mono color="#484F58" size="0.65rem">{ctrlLabel}</Mono>
          <Mono color="#8B949E" size="0.8rem">{ctrlValue}</Mono>
        </Box>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <Mono color="#3FB950" size="0.65rem">{maiwLabel}</Mono>
          <Mono color="#3FB950" size="0.8rem">{maiwValue}</Mono>
        </Box>
        {delta && (
          <Box sx={{ mt: 0.5, pt: 0.5, borderTop: '1px solid #1C2128' }}>
            <Mono color={deltaColor ?? '#3FB950'} size="0.75rem">{delta}</Mono>
          </Box>
        )}
      </Box>
    </Card>
  );
}

// ── Comparison row ────────────────────────────────────────────────────────────

function CmpRow({ label, ctrl, maiw, highlight }: {
  label: string; ctrl: string; maiw: string; highlight?: 'maiw' | 'none';
}) {
  return (
    <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 1, py: 0.4, borderBottom: '1px solid #1C2128' }}>
      <Mono color="#6E7681" size="0.68rem">{label}</Mono>
      <Mono color="#8B949E" size="0.72rem">{ctrl}</Mono>
      <Mono color={highlight === 'maiw' ? '#3FB950' : '#C9D1D9'} size="0.72rem">{maiw}</Mono>
    </Box>
  );
}

// ── Overlaid trajectory chart ─────────────────────────────────────────────────

interface SeriesDef {
  key: string;
  label: string;
  maxVal: number;
}

const CHART_SERIES: SeriesDef[] = [
  { key: 'wave_risk_score',     label: 'Wave Risk Score',   maxVal: 100 },
  { key: 'pending_backlog',     label: 'Pending Backlog',   maxVal: 10  },
  { key: 'wave_completion_pct', label: 'Wave Completion %', maxVal: 100 },
];

function MiniChart({
  ctrl, maiw, seriesDef, height = 90,
}: {
  ctrl: CounterfactualRun; maiw: CounterfactualRun;
  seriesDef: SeriesDef; height?: number;
}) {
  const W = 500; const H = height;
  const PL = 32; const PR = 8; const PT = 6; const PB = 18;
  const PW = W - PL - PR; const PH = H - PT - PB;

  const allElapsed = [...ctrl.trajectory, ...maiw.trajectory].map(t => t.elapsed_seconds);
  const maxElapsed = Math.max(...allElapsed, 1);

  const toX = (e: number) => PL + (e / maxElapsed) * PW;
  const toY = (v: number) => PT + PH - Math.min(PH, Math.max(0, (v / seriesDef.maxVal) * PH));

  function makePath(run: CounterfactualRun) {
    return run.trajectory
      .map((snap, i) => {
        const val = (snap.kpis as any)[seriesDef.key] ?? 0;
        return `${i === 0 ? 'M' : 'L'} ${toX(snap.elapsed_seconds).toFixed(1)} ${toY(val).toFixed(1)}`;
      })
      .join(' ');
  }

  const ctrlPath = makePath(ctrl);
  const maiwPath = makePath(maiw);
  const maiwRecovery = maiw.recovery;
  const yTicks = [0, 50, 100].filter(v => v <= seriesDef.maxVal);

  return (
    <Box>
      <Mono color="#8B949E" size="0.65rem">{seriesDef.label}</Mono>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height }} xmlns="http://www.w3.org/2000/svg">
        {yTicks.map((v, i) => {
          const y = toY(v / 100 * seriesDef.maxVal);
          return (
            <g key={i}>
              <line x1={PL} y1={y} x2={W - PR} y2={y} stroke="#21262D" strokeWidth="0.5" />
              <text x={PL - 3} y={y + 3} textAnchor="end" fill="#484F58" fontSize="7" fontFamily="monospace">
                {seriesDef.maxVal === 10 ? String(Math.round(v / 10)) : String(v)}
              </text>
            </g>
          );
        })}
        {/* CONTROL — dashed neutral */}
        <path d={ctrlPath} fill="none" stroke="#8B949E" strokeWidth="1.5" strokeDasharray="4 3" />
        {/* MAIW — solid green */}
        <path d={maiwPath} fill="none" stroke="#3FB950" strokeWidth="2" />
        {/* MAIW recovery marker */}
        {maiwRecovery && (
          <line
            x1={toX(maiwRecovery.sim_time_seconds)} y1={PT}
            x2={toX(maiwRecovery.sim_time_seconds)} y2={H - PB}
            stroke="#3FB950" strokeWidth="1" strokeDasharray="2 2"
          />
        )}
        {/* X axis */}
        {[0, 300, 600, 900, 1200, 1800].filter(t => t <= maxElapsed + 60).map(t => (
          <text key={t} x={toX(t)} y={H - 4} textAnchor="middle" fill="#484F58" fontSize="7" fontFamily="monospace">
            {t}s
          </text>
        ))}
      </svg>
    </Box>
  );
}

// ── Legend ────────────────────────────────────────────────────────────────────

function Legend() {
  return (
    <Box sx={{ display: 'flex', gap: 2, mb: 1.25, alignItems: 'center' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
        <svg width="24" height="8"><line x1="0" y1="4" x2="24" y2="4" stroke="#8B949E" strokeWidth="1.5" strokeDasharray="4 3" /></svg>
        <Mono color="#8B949E" size="0.65rem">CONTROL — no intervention</Mono>
      </Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
        <svg width="24" height="8"><line x1="0" y1="4" x2="24" y2="4" stroke="#3FB950" strokeWidth="2" /></svg>
        <Mono color="#3FB950" size="0.65rem">MAIW — governed AI intervention</Mono>
      </Box>
    </Box>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

const CounterfactualPanel: React.FC = () => {
  const { data, isLoading, error } = useQuery<CounterfactualResult>({
    queryKey: ['counterfactual'],
    queryFn: () => demoAPI.getCounterfactualResult(),
    retry: false,
    staleTime: 300_000,
  });

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, p: 2 }}>
        <CircularProgress size={14} sx={{ color: '#3FB950' }} />
        <Mono color="#6E7681">Loading evaluation data…</Mono>
      </Box>
    );
  }

  if (error || !data) {
    return (
      <Alert severity="info" sx={{ background: '#0D1117', border: '1px solid #21262D', color: '#8B949E', fontFamily: 'monospace', fontSize: '0.72rem' }}>
        No evaluation data. Run: <code style={{ color: '#76B900' }}>python scripts/counterfactual_eval.py</code>
      </Alert>
    );
  }

  const { control, maiw, comparison: cmp } = data;

  function fmtTTR(secs: number | null, never: boolean): string {
    if (never || secs === null) return `>${Math.round((data?.horizon_seconds ?? 1800) / 60)}m`;
    const m = Math.round(secs / 60);
    return m < 1 ? `${secs}s` : `${m} sim-min`;
  }

  function fmtNum(v: number | null | undefined, d = 1): string {
    if (v === null || v === undefined) return '—';
    return typeof v === 'number' ? v.toFixed(d) : String(v);
  }

  const maiwCycles = maiw.maiw_cycles?.length ?? 0;
  const maiwTTR = cmp.maiw_recovery_seconds;
  const ctrlNever = cmp.control_never_recovered;

  return (
    <Box>
      {/* Header: evaluation context */}
      <Box sx={{ mb: 1.5, pb: 1.25, borderBottom: '1px solid #1C2128' }}>
        <Box sx={{ display: 'flex', gap: 3 }}>
          <Box>
            <Mono color="#484F58" size="0.6rem">SAME SEED</Mono>
            <Mono color="#484F58" size="0.6rem">SAME INITIAL STATE</Mono>
            <Mono color="#484F58" size="0.6rem">SAME DISRUPTION SEQUENCE</Mono>
          </Box>
          <Box sx={{ borderLeft: '1px solid #1C2128', pl: 3 }}>
            <Box sx={{ display: 'flex', gap: 2 }}>
              <Box>
                <Mono color="#8B949E" size="0.65rem" >CONTROL</Mono>
                <Mono color="#6E7681" size="0.6rem">No MAIW intervention</Mono>
              </Box>
              <Mono color="#30363D" size="0.65rem">vs</Mono>
              <Box>
                <Mono color="#3FB950" size="0.65rem">MAIW</Mono>
                <Mono color="#6E7681" size="0.6rem">Governed AI intervention</Mono>
              </Box>
            </Box>
          </Box>
          <Box sx={{ borderLeft: '1px solid #1C2128', pl: 3, ml: 'auto' }}>
            <Mono color="#484F58" size="0.6rem">Scenario: {data.scenario}</Mono>
            <Mono color="#484F58" size="0.6rem">Horizon: {data.horizon_seconds}s · Tick: {data.tick_seconds}s</Mono>
            <Mono color="#484F58" size="0.6rem">Evaluated: {data.evaluated_at.slice(0, 19)}Z</Mono>
          </Box>
        </Box>
      </Box>

      {/* Three summary tiles */}
      <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 1.25, mb: 1.5 }}>
        <SummaryTile
          title="Time to Recovery"
          ctrlLabel="CONTROL"
          ctrlValue={fmtTTR(cmp.control_recovery_seconds, ctrlNever)}
          maiwLabel="MAIW"
          maiwValue={fmtTTR(maiwTTR, false)}
          delta={ctrlNever && maiwTTR !== null ? `MAIW recovered; Control did not` : undefined}
          deltaColor="#3FB950"
        />
        <SummaryTile
          title="Backlog Exposure"
          ctrlLabel="CONTROL (AUC)"
          ctrlValue={String(cmp.backlog_auc_control)}
          maiwLabel="MAIW (AUC)"
          maiwValue={String(cmp.backlog_auc_maiw)}
          delta={cmp.backlog_auc_reduction_pct !== null ? `${cmp.backlog_auc_reduction_pct}% reduction` : undefined}
          deltaColor="#3FB950"
        />
        <SummaryTile
          title="Wave Risk Exposure"
          ctrlLabel="CONTROL (AUC)"
          ctrlValue={String(cmp.wave_risk_auc_control)}
          maiwLabel="MAIW (AUC)"
          maiwValue={String(cmp.wave_risk_auc_maiw)}
          delta={cmp.wave_risk_auc_reduction_pct !== null ? `${cmp.wave_risk_auc_reduction_pct}% reduction` : undefined}
          deltaColor="#3FB950"
        />
      </Box>

      {/* Horizon comparison */}
      <Card sx={{ mb: 1.25 }}>
        <Label>KPI at Fixed Horizons</Label>
        <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 1, mb: 0.5 }}>
          <Mono color="#484F58" size="0.62rem">METRIC</Mono>
          <Mono color="#8B949E" size="0.62rem">CONTROL</Mono>
          <Mono color="#3FB950" size="0.62rem">MAIW</Mono>
        </Box>
        {['300s', '600s', '900s'].map(hKey => {
          const h = cmp.at_horizon[hKey];
          if (!h) return null;
          return (
            <Box key={hKey} sx={{ mb: 0.75, pb: 0.75, borderBottom: '1px solid #0D1117' }}>
              <Mono color="#484F58" size="0.6rem">@ {hKey}</Mono>
              <CmpRow label="wave risk score"   ctrl={fmtNum(h['wave_risk_score']?.control, 0)}       maiw={fmtNum(h['wave_risk_score']?.maiw, 0)}       highlight="maiw" />
              <CmpRow label="pending backlog"   ctrl={fmtNum(h['pending_backlog']?.control, 0)}       maiw={fmtNum(h['pending_backlog']?.maiw, 0)}       highlight="maiw" />
              <CmpRow label="wave completion %" ctrl={fmtNum(h['wave_completion_pct']?.control) + '%'} maiw={fmtNum(h['wave_completion_pct']?.maiw) + '%'} highlight="maiw" />
            </Box>
          );
        })}
        <Box sx={{ mt: 0.75 }}>
          <CmpRow label="MAIW cycles run" ctrl="0" maiw={String(maiwCycles)} />
        </Box>
      </Card>

      {/* Overlaid trajectory charts */}
      <Card sx={{ mb: 1.25 }}>
        <Label>Trajectory Comparison</Label>
        <Legend />
        <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 2 }}>
          {CHART_SERIES.map(s => (
            <MiniChart key={s.key} ctrl={control} maiw={maiw} seriesDef={s} height={90} />
          ))}
        </Box>
      </Card>

      {/* Caveat */}
      <Box sx={{ pt: 0.75, borderTop: '1px solid #1C2128' }}>
        <Mono color="#30363D" size="0.6rem">
          Results generated in MAIW's deterministic synthetic warehouse environment. Comparative behavior under the modeled scenario — not measurements from a production warehouse. Backlog AUC and wave-risk AUC are area-under-curve values (task·sec and risk-score·sec respectively) computed over the evaluation horizon.
        </Mono>
      </Box>
    </Box>
  );
};

export default CounterfactualPanel;
