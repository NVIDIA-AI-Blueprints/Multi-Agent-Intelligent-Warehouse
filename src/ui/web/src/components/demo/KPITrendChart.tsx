import React, { useMemo } from 'react';
import { Box, Typography } from '@mui/material';
import { KPISnapshot } from '../../services/demoAPI';

interface LifecycleMarker {
  sim_time_seconds: number;
  category: string;
  label: string;
}

interface Props {
  history: KPISnapshot[];
  lifecycleEvents?: LifecycleMarker[];
  height?: number;
}

const SERIES: Array<{ key: keyof KPISnapshot; color: string; label: string; dashed?: boolean }> = [
  { key: 'wave_risk_score',           color: '#F85149', label: 'Wave Risk',       dashed: false },
  { key: 'wave_completion_pct',       color: '#3FB950', label: 'Wave Completion', dashed: false },
  { key: 'equipment_operational_pct', color: '#58A6FF', label: 'Equip Oper.',     dashed: true  },
  { key: 'labor_availability_pct',    color: '#D29922', label: 'Labor Avail.',    dashed: true  },
];

const MARKER_COLORS: Record<string, string> = {
  INJECT: '#F85149',
  OBSERVE: '#58A6FF',
  REASON: '#76B900',
  PROPOSE: '#D29922',
  DECIDE: '#D29922',
  EXECUTE: '#3FB950',
};

const KPITrendChart: React.FC<Props> = React.memo(({ history, lifecycleEvents = [], height = 140 }) => {
  // Chart drawing area dimensions (logical SVG units)
  const W = 1000;
  const H = height;
  const PAD_L = 28;
  const PAD_R = 12;
  const PAD_T = 8;
  const PAD_B = 20;
  const PLOT_W = W - PAD_L - PAD_R;
  const PLOT_H = H - PAD_T - PAD_B;

  const { points, markers } = useMemo(() => {
    if (history.length < 2) return { points: [], markers: [] };
    const times = history.map(p => p.sim_time_seconds);
    const minT = Math.min(...times);
    const maxT = Math.max(...times);
    const rangeT = maxT - minT || 1;

    const toX = (t: number) => PAD_L + ((t - minT) / rangeT) * PLOT_W;
    const toY = (v: number) => PAD_T + PLOT_H - (Math.min(100, Math.max(0, v)) / 100) * PLOT_H;

    const points = SERIES.map(s => ({
      ...s,
      path: history
        .map((p, i) => `${i === 0 ? 'M' : 'L'} ${toX(p.sim_time_seconds).toFixed(1)} ${toY(Number(p[s.key]) || 0).toFixed(1)}`)
        .join(' '),
    }));

    const markers = lifecycleEvents
      .filter(e => e.sim_time_seconds >= minT && e.sim_time_seconds <= maxT && e.category !== 'KPI' && MARKER_COLORS[e.category])
      .map(e => ({ ...e, x: toX(e.sim_time_seconds) }));

    return { points, markers };
  }, [history, lifecycleEvents, PLOT_W, PLOT_H]);

  const showEmpty = history.length < 2;

  return (
    <Box sx={{ width: '100%' }}>
      {showEmpty ? (
        <Box sx={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#080C10', borderRadius: 0.5 }}>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#30363D' }}>
            — tick or analyze to populate trend —
          </Typography>
        </Box>
      ) : (
        <svg
          viewBox={`0 0 ${W} ${H}`}
          style={{ width: '100%', height, display: 'block', backgroundColor: '#080C10', borderRadius: '4px' }}
          preserveAspectRatio="none"
        >
          {/* Gridlines at 0, 25, 50, 75, 100 */}
          {[0, 25, 50, 75, 100].map(v => {
            const y = PAD_T + PLOT_H - (v / 100) * PLOT_H;
            return (
              <g key={v}>
                <line x1={PAD_L} y1={y} x2={W - PAD_R} y2={y} stroke="#1C2128" strokeWidth="0.8" />
                <text x={PAD_L - 4} y={y + 3} textAnchor="end" fontSize="8" fill="#30363D" fontFamily="monospace">{v}</text>
              </g>
            );
          })}

          {/* Lifecycle event markers (vertical dashed lines) */}
          {markers.map((m, i) => (
            <line
              key={i}
              x1={m.x} y1={PAD_T}
              x2={m.x} y2={PAD_T + PLOT_H}
              stroke={MARKER_COLORS[m.category] || '#484F58'}
              strokeWidth="1.2"
              strokeDasharray="3,3"
              opacity="0.7"
            />
          ))}

          {/* Series polylines */}
          {points.map(s => (
            <path
              key={s.key}
              d={s.path}
              fill="none"
              stroke={s.color}
              strokeWidth="1.8"
              strokeLinejoin="round"
              strokeDasharray={s.dashed ? '6 3' : undefined}
            />
          ))}
        </svg>
      )}

      {/* Legend */}
      <Box sx={{ display: 'flex', gap: 1.5, mt: 0.5, flexWrap: 'wrap', alignItems: 'center' }}>
        {SERIES.map(s => (
          <Box key={s.key} sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            {s.dashed ? (
              <svg width="12" height="6" style={{ flexShrink: 0 }}>
                <line x1="0" y1="3" x2="12" y2="3" stroke={s.color} strokeWidth="1.5" strokeDasharray="4 2" />
              </svg>
            ) : (
              <Box sx={{ width: 12, height: 2, backgroundColor: s.color, borderRadius: 1, flexShrink: 0 }} />
            )}
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58' }}>{s.label}</Typography>
          </Box>
        ))}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Box sx={{ width: 10, height: 1, borderTop: '1px dashed #F85149', opacity: 0.7 }} />
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58' }}>INJECT</Typography>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Box sx={{ width: 10, height: 1, borderTop: '1px dashed #76B900', opacity: 0.7 }} />
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58' }}>MAIW</Typography>
        </Box>
      </Box>
    </Box>
  );
});

export default KPITrendChart;
