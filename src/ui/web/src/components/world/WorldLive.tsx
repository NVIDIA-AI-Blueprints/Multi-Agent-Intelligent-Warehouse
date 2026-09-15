// SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0
/**
 * WorldLive — Phase 17D LIVE runtime view.
 *
 * Polls GET /api/v1/world/live every 15 seconds and renders:
 *  - Runtime status bar (status, clock, scenario, DataPack immutability)
 *  - Live summary counters (workers, equipment, tasks)
 *  - Changed entities panel (vs scenario initial state)
 *  - Aggregate KPI delta panel (from last execution)
 *  - Outcome semantics banners
 *
 * READ-ONLY — no mutation controls.
 */

import React from 'react';
import { Box, Typography, Skeleton } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import {
  worldAPI,
  WorldLiveResponse,
  ChangedEntityDTO,
  LastExecutionDTO,
} from '../../services/worldAPI';

// ── Colour tokens ──────────────────────────────────────────────────────────────

const C = {
  bg: '#0D1117',
  card: '#161B22',
  border: '#21262D',
  text: '#C9D1D9',
  muted: '#8B949E',
  dim: '#484F58',
  accent: '#58A6FF',
  green: '#3FB950',
  yellow: '#E3B341',
  orange: '#D29922',
  red: '#F85149',
  purple: '#A371F7',
  mono: 'monospace' as const,
};

// ── Small shared components ────────────────────────────────────────────────────

function SectionHeading({ label }: { label: string }) {
  return (
    <Typography
      sx={{
        fontFamily: C.mono,
        fontSize: '0.6rem',
        fontWeight: 700,
        color: C.accent,
        textTransform: 'uppercase',
        letterSpacing: '0.1em',
        mb: 1,
      }}
    >
      {label}
    </Typography>
  );
}

function Badge({
  children,
  color = C.muted,
}: {
  children: React.ReactNode;
  color?: string;
}) {
  return (
    <Box
      component="span"
      sx={{
        fontFamily: C.mono,
        fontSize: '0.58rem',
        fontWeight: 700,
        color,
        border: `1px solid ${color}44`,
        borderRadius: '3px',
        px: '5px',
        py: '1px',
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        display: 'inline-block',
      }}
    >
      {children}
    </Box>
  );
}

function Mono({
  children,
  color = C.text,
  size = '0.72rem',
}: {
  children: React.ReactNode;
  color?: string;
  size?: string;
}) {
  return (
    <Typography sx={{ fontFamily: C.mono, fontSize: size, color }}>
      {children}
    </Typography>
  );
}

function KV({ label, value, valueColor = C.text }: { label: string; value: React.ReactNode; valueColor?: string }) {
  return (
    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', py: '2px' }}>
      <Mono color={C.muted} size="0.68rem">{label}</Mono>
      <Mono color={valueColor} size="0.68rem">{value}</Mono>
    </Box>
  );
}

// ── Runtime status colour ──────────────────────────────────────────────────────

function runtimeColor(status: string): string {
  switch (status) {
    case 'ACTIVE': return C.green;
    case 'PAUSED': return C.yellow;
    default: return C.dim;
  }
}

// ── Outcome semantics ─────────────────────────────────────────────────────────

type OutcomeSemantics = {
  label: string;
  color: string;
  banner: string | null;
};

function outcomeSemantics(exec: LastExecutionDTO | null): OutcomeSemantics {
  if (exec === null) {
    return { label: 'NO EXECUTION', color: C.dim, banner: null };
  }
  switch (exec.outcome) {
    case 'EXECUTED': {
      // Check if any KPI delta shows improvement
      const delta = exec.kpi_delta ?? {};
      const improved = Object.values(delta).some((v) => typeof v === 'number' && v > 0);
      return {
        label: improved ? 'EXECUTED + IMPROVED' : 'EXECUTED + NO MEASURABLE CHANGE',
        color: improved ? C.green : C.muted,
        banner: null,
      };
    }
    case 'FAILED':
      return { label: 'FAILED', color: C.red, banner: null };
    case 'UNKNOWN':
      return { label: 'UNKNOWN', color: C.orange, banner: 'RUNTIME STATE UNCERTAIN' };
    case 'REJECTED':
      return { label: 'REJECTED', color: C.yellow, banner: 'NO RUNTIME MUTATION' };
    case 'PENDING':
      return { label: 'PENDING', color: C.yellow, banner: 'NO RUNTIME MUTATION' };
    default:
      return { label: exec.outcome, color: C.muted, banner: null };
  }
}

// ── Changed entity card ───────────────────────────────────────────────────────

function ChangedEntityCard({ entity }: { entity: ChangedEntityDTO }) {
  const typeColor = entity.entity_type === 'worker' ? C.green : C.purple;
  return (
    <Box
      data-testid="changed-entity-card"
      sx={{
        background: C.card,
        border: `1px solid ${C.border}`,
        borderLeft: `3px solid ${typeColor}`,
        borderRadius: '4px',
        p: 1,
        mb: '6px',
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: '6px', mb: '4px' }}>
        <Badge color={typeColor}>{entity.entity_type}</Badge>
        <Badge color={C.yellow}>CHANGED</Badge>
        <Mono color={C.text} size="0.7rem">{entity.label}</Mono>
      </Box>
      <Mono color={C.dim} size="0.6rem">{entity.entity_id}</Mono>
      {entity.changed_fields.map((cf, i) => (
        <Box
          key={i}
          sx={{
            display: 'flex',
            gap: '6px',
            alignItems: 'center',
            mt: '3px',
            pl: '4px',
          }}
        >
          <Mono color={C.muted} size="0.65rem">{cf.field}</Mono>
          <Mono color={C.muted} size="0.6rem">{'→'}</Mono>
          <Badge color={C.red}>{String(cf.before_value ?? 'null')}</Badge>
          <Mono color={C.muted} size="0.6rem">{'→'}</Mono>
          <Badge color={C.green}>{String(cf.after_value ?? 'null')}</Badge>
        </Box>
      ))}
      <Mono color={C.dim} size="0.58rem" >{entity.note}</Mono>
    </Box>
  );
}

// ── KPI delta panel ───────────────────────────────────────────────────────────

function KPIDeltaPanel({ exec }: { exec: LastExecutionDTO }) {
  const delta = exec.kpi_delta;

  const formatDelta = (v: number) => {
    const sign = v > 0 ? '+' : '';
    return `${sign}${v.toFixed(1)}`;
  };

  const deltaColor = (v: number) => (v > 0 ? C.green : v < 0 ? C.red : C.muted);

  return (
    <Box
      data-testid="kpi-delta-panel"
      sx={{
        background: C.card,
        border: `1px solid ${C.border}`,
        borderRadius: '4px',
        p: 1,
        mb: 1,
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: '6px', mb: '6px' }}>
        <SectionHeading label="KPI Delta" />
        <Box sx={{ ml: 'auto' }}>
          <Badge color={runtimeColor('ACTIVE')}>{exec.outcome}</Badge>
        </Box>
      </Box>

      {exec.pre_kpi && (
        <Box sx={{ mb: '6px' }}>
          <Mono color={C.dim} size="0.6rem">PRE-EXECUTION</Mono>
          {Object.entries(exec.pre_kpi).slice(0, 5).map(([k, v]) => (
            <KV key={k} label={k} value={typeof v === 'number' ? v.toFixed(1) : String(v)} />
          ))}
        </Box>
      )}

      {exec.post_kpi && (
        <Box sx={{ mb: '6px' }}>
          <Mono color={C.dim} size="0.6rem">POST-EXECUTION</Mono>
          {Object.entries(exec.post_kpi).slice(0, 5).map(([k, v]) => (
            <KV key={k} label={k} value={typeof v === 'number' ? v.toFixed(1) : String(v)} />
          ))}
        </Box>
      )}

      {delta && Object.keys(delta).length > 0 && (
        <Box>
          <Mono color={C.dim} size="0.6rem">DELTA</Mono>
          {Object.entries(delta).slice(0, 6).map(([k, v]) => (
            <KV
              key={k}
              label={k}
              value={typeof v === 'number' ? formatDelta(v) : String(v)}
              valueColor={typeof v === 'number' ? deltaColor(v) : C.text}
            />
          ))}
        </Box>
      )}

      {(!delta || Object.keys(delta).length === 0) && (
        <Mono color={C.dim} size="0.65rem">No KPI delta available</Mono>
      )}
    </Box>
  );
}

// ── Banner ────────────────────────────────────────────────────────────────────

function Banner({ message, color }: { message: string; color: string }) {
  return (
    <Box
      data-testid="outcome-banner"
      sx={{
        background: `${color}14`,
        border: `1px solid ${color}44`,
        borderRadius: '4px',
        px: 1,
        py: '6px',
        mb: 1,
        textAlign: 'center',
      }}
    >
      <Mono color={color} size="0.68rem">{message}</Mono>
    </Box>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function WorldLive() {
  const { data, isLoading, isError } = useQuery<WorldLiveResponse>({
    queryKey: ['world-live'],
    queryFn: () => worldAPI.getLive(),
    refetchInterval: 15_000,
    staleTime: 10_000,
  });

  if (isLoading) {
    return (
      <Box sx={{ p: 2 }}>
        <Skeleton variant="rectangular" height={32} sx={{ mb: 1, bgcolor: '#21262D' }} />
        <Skeleton variant="rectangular" height={80} sx={{ mb: 1, bgcolor: '#21262D' }} />
        <Skeleton variant="rectangular" height={120} sx={{ bgcolor: '#21262D' }} />
      </Box>
    );
  }

  if (isError || !data) {
    return (
      <Box sx={{ p: 2, textAlign: 'center' }}>
        <Mono color={C.red} size="0.72rem">LIVE data unavailable — API error</Mono>
      </Box>
    );
  }

  const live = data;
  const sem = outcomeSemantics(live.last_execution);

  return (
    <Box
      data-testid="world-live"
      sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 1 }}
    >
      {/* ── DataPack immutability indicator ──────────────────────────────────── */}
      <Box
        data-testid="datapack-immutable-indicator"
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          background: C.card,
          border: `1px solid ${C.border}`,
          borderRadius: '4px',
          px: 1,
          py: '6px',
        }}
      >
        <Mono color={C.green} size="0.65rem">DATAPACK IMMUTABLE</Mono>
        <Mono color={C.green} size="0.65rem">&#x2713;</Mono>
        <Mono color={C.dim} size="0.62rem">
          {live.base_checksum ? live.base_checksum.slice(0, 12) + '...' : 'no checksum'}
        </Mono>
      </Box>

      {/* ── Runtime status bar ────────────────────────────────────────────────── */}
      <Box
        data-testid="live-runtime-summary"
        sx={{
          background: C.card,
          border: `1px solid ${C.border}`,
          borderRadius: '4px',
          p: 1,
        }}
      >
        <SectionHeading label="Runtime Status" />
        <KV
          label="status"
          value={<Badge color={runtimeColor(live.runtime_status)}>{live.runtime_status}</Badge>}
        />
        {live.world_clock && (
          <KV label="sim clock" value={live.world_clock.replace('T', ' ').slice(0, 19)} />
        )}
        {live.scenario_id && (
          <KV label="scenario" value={live.scenario_id} />
        )}
        <KV label="scenario active" value={live.scenario_active ? 'YES' : 'NO'} valueColor={live.scenario_active ? C.green : C.muted} />
      </Box>

      {/* ── Live summary counters ─────────────────────────────────────────────── */}
      <Box
        data-testid="live-counters"
        sx={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: '6px',
        }}
      >
        {[
          { label: 'Workers', value: live.summary.workers, sub: `${live.summary.idle_workers} idle`, color: C.green },
          { label: 'Equipment', value: live.summary.equipment, sub: `${live.summary.available_equipment} avail`, color: C.orange },
          { label: 'Tasks', value: live.summary.tasks, sub: `${live.summary.pending_tasks} pending / ${live.summary.in_progress_tasks} active`, color: C.purple },
        ].map(({ label, value, sub, color }) => (
          <Box
            key={label}
            sx={{
              background: C.card,
              border: `1px solid ${C.border}`,
              borderTop: `2px solid ${color}`,
              borderRadius: '4px',
              p: 1,
              textAlign: 'center',
            }}
          >
            <Mono color={color} size="1.1rem">{value}</Mono>
            <Mono color={C.muted} size="0.6rem">{label}</Mono>
            <Mono color={C.dim} size="0.58rem">{sub}</Mono>
          </Box>
        ))}
      </Box>

      {/* ── Outcome / execution banner ────────────────────────────────────────── */}
      {sem.banner && <Banner message={sem.banner} color={C.orange} />}

      {/* ── Last execution outcome ────────────────────────────────────────────── */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          px: 1,
          py: '5px',
          background: C.card,
          border: `1px solid ${C.border}`,
          borderRadius: '4px',
        }}
      >
        <Mono color={C.dim} size="0.62rem">Last execution:</Mono>
        <Badge color={sem.color}>{sem.label}</Badge>
        {live.last_execution?.trace_id && (
          <Mono color={C.dim} size="0.58rem">trace {live.last_execution.trace_id.slice(0, 8)}</Mono>
        )}
      </Box>

      {/* ── KPI delta (only when execution record exists) ─────────────────────── */}
      {live.last_execution && (
        <KPIDeltaPanel exec={live.last_execution} />
      )}

      {/* ── Changed entities panel ────────────────────────────────────────────── */}
      <Box>
        <SectionHeading
          label={`Changed Entities (${live.changed_entities.length})`}
        />
        {live.changed_entities.length === 0 ? (
          <Box
            data-testid="no-changed-entities"
            sx={{
              background: C.card,
              border: `1px solid ${C.border}`,
              borderRadius: '4px',
              p: 1,
              textAlign: 'center',
            }}
          >
            <Mono color={C.dim} size="0.68rem">No entity changes from scenario initial state</Mono>
          </Box>
        ) : (
          live.changed_entities.map((e) => (
            <ChangedEntityCard key={e.entity_id} entity={e} />
          ))
        )}
      </Box>
    </Box>
  );
}
