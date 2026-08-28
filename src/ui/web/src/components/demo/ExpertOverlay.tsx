/**
 * ExpertOverlay — Phase 12G expert panel for the demo shell.
 *
 * Four sections rendered in a 2×2 grid:
 *   1. Runtime health     — maiw_operational_status, model_gateway, decision_engine, state_provider, uptime
 *   2. MCP domains        — inventory/equipment/labor/wave configured + domain health
 *   3. Agent / executor   — operations/equipment/safety agents + 3 executors
 *   4. SSE stream         — last 30 events from live buffer, newest first
 */

import React, { useState } from 'react';
import { Box, Typography } from '@mui/material';
import { RuntimeStatus } from '../../services/api';
import { SSEEvent } from '../../hooks/useDemoSSE';

// ── Shared primitives ─────────────────────────────────────────────────────────

function SectionHeader({ label }: { label: string }) {
  return (
    <Typography sx={{
      fontFamily: 'monospace', fontSize: '0.58rem', fontWeight: 700,
      color: '#484F58', letterSpacing: '0.12em', textTransform: 'uppercase', mb: 1,
    }}>
      {label}
    </Typography>
  );
}

function StatusRow({ label, value, ok }: { label: string; value: string; ok?: boolean }) {
  const valueColor =
    ok === true  ? '#3FB950' :
    ok === false ? '#F85149' :
    '#8B949E';
  return (
    <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1, mb: '3px' }}>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#484F58', flexShrink: 0, minWidth: 160 }}>
        {label}
      </Typography>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: valueColor, fontWeight: ok !== undefined ? 700 : 400 }}>
        {value}
      </Typography>
    </Box>
  );
}

function Dot({ ok }: { ok: boolean | undefined }) {
  const color = ok === true ? '#3FB950' : ok === false ? '#F85149' : '#484F58';
  return (
    <Box sx={{ width: 6, height: 6, borderRadius: '50%', background: color, flexShrink: 0, mt: '1px' }} />
  );
}

// ── Section 1: Runtime health ─────────────────────────────────────────────────

function RuntimeSection({ runtime }: { runtime: any }) {
  const uptime = runtime?.uptime_seconds;
  const uptimeLabel = uptime != null
    ? uptime >= 3600 ? `${Math.floor(uptime / 3600)}h ${Math.floor((uptime % 3600) / 60)}m`
    : uptime >= 60   ? `${Math.floor(uptime / 60)}m ${uptime % 60}s`
    : `${uptime}s`
    : '—';

  return (
    <Box data-testid="expert-runtime">
      <SectionHeader label="Runtime" />
      <StatusRow
        label="maiw_operational_status"
        value={runtime?.maiw_operational_status ?? '—'}
        ok={runtime?.maiw_operational_status === 'HEALTHY' ? true : runtime?.maiw_operational_status ? false : undefined}
      />
      <StatusRow
        label="model_gateway"
        value={runtime?.model_gateway_available ? 'available' : runtime?.model_gateway_available === false ? 'unavailable' : '—'}
        ok={runtime?.model_gateway_available}
      />
      <StatusRow
        label="decision_engine"
        value={runtime?.decision_engine_available ? 'available' : runtime?.decision_engine_available === false ? 'unavailable' : '—'}
        ok={runtime?.decision_engine_available}
      />
      <StatusRow
        label="state_provider"
        value={runtime?.state_provider_available ? 'available' : runtime?.state_provider_available === false ? 'unavailable' : '—'}
        ok={runtime?.state_provider_available}
      />
      <StatusRow
        label="runtime_initialized"
        value={runtime?.runtime_initialized != null ? String(runtime.runtime_initialized) : '—'}
        ok={runtime?.runtime_initialized}
      />
      <StatusRow label="uptime" value={uptimeLabel} />
    </Box>
  );
}

// ── Section 2: MCP domains ────────────────────────────────────────────────────

const MCP_DOMAINS = ['inventory', 'equipment', 'labor', 'wave'] as const;

function McpSection({ runtime }: { runtime: any }) {
  return (
    <Box data-testid="expert-mcp">
      <SectionHeader label="MCP Domains" />
      {MCP_DOMAINS.map(d => {
        const configured: boolean | undefined = runtime?.[`${d}_mcp_configured`];
        const health: string | undefined = runtime?.domain_health?.[d];
        const healthOk = health === 'HEALTHY' ? true : health ? false : undefined;

        return (
          <Box key={d} sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: '4px' }}>
            <Dot ok={configured && healthOk !== false} />
            <Typography sx={{
              fontFamily: 'monospace', fontSize: '0.62rem', color: '#8B949E',
              textTransform: 'uppercase', minWidth: 72,
            }}>
              {d}
            </Typography>
            <Typography sx={{
              fontFamily: 'monospace', fontSize: '0.6rem',
              color: configured ? '#6E7681' : '#484F58',
            }}>
              {configured ? 'configured' : 'not configured'}
            </Typography>
            {health && (
              <Typography sx={{
                fontFamily: 'monospace', fontSize: '0.6rem',
                color: health === 'HEALTHY' ? '#3FB950' : '#F85149',
                ml: 'auto',
              }}>
                {health}
              </Typography>
            )}
          </Box>
        );
      })}
    </Box>
  );
}

// ── Section 3: Agents & executors ─────────────────────────────────────────────

const AGENTS = [
  { key: 'operations_agent_available', label: 'Operations agent' },
  { key: 'equipment_agent_available',  label: 'Equipment agent' },
  { key: 'safety_agent_available',     label: 'Safety agent' },
] as const;

const EXECUTORS = [
  { key: 'equipment_executor_available', label: 'Equipment executor' },
  { key: 'labor_executor_available',     label: 'Labor executor' },
  { key: 'wave_executor_available',      label: 'Wave executor' },
] as const;

function AgentSection({ runtime }: { runtime: any }) {
  return (
    <Box data-testid="expert-agents">
      <SectionHeader label="Agents &amp; Executors" />
      {[...AGENTS, ...EXECUTORS].map(({ key, label }) => {
        const available: boolean | undefined = runtime?.[key];
        return (
          <Box key={key} sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: '4px' }}>
            <Dot ok={available} />
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#8B949E', flexGrow: 1 }}>
              {label}
            </Typography>
            <Typography sx={{
              fontFamily: 'monospace', fontSize: '0.6rem',
              color: available === true ? '#3FB950' : available === false ? '#F85149' : '#484F58',
            }}>
              {available === true ? 'available' : available === false ? 'unavailable' : '—'}
            </Typography>
          </Box>
        );
      })}
    </Box>
  );
}

// ── Section 4: SSE stream ─────────────────────────────────────────────────────

const CATEGORY_COLORS: Record<string, string> = {
  OBSERVE: '#58A6FF',
  REASON: '#58A6FF',
  PROPOSE: '#D29922',
  DECIDE: '#D29922',
  APPROVE: '#3FB950',
  EXECUTE: '#3FB950',
  RECONCILIATION_REQUIRED: '#F85149',
  CONFIRMED_EXECUTED: '#3FB950',
  CONFIRMED_NOT_EXECUTED: '#F85149',
  CIRCUIT_OPEN: '#F0883E',
  FAULT_INJECTED: '#F0883E',
  INJECT: '#F0883E',
  RECONCILE: '#58A6FF',
  INDETERMINATE: '#D29922',
};

function SseSection({ events }: { events: SSEEvent[] }) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? events : events.slice(0, 10);

  return (
    <Box data-testid="expert-sse">
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
        <SectionHeader label={`SSE Stream (${events.length})`} />
        {events.length > 10 && (
          <Box
            component="button"
            onClick={() => setExpanded(e => !e)}
            sx={{
              background: 'transparent', border: 'none', cursor: 'pointer',
              fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58',
              mb: 1, '&:hover': { color: '#8B949E' },
            }}
          >
            {expanded ? 'show less' : `+${events.length - 10} more`}
          </Box>
        )}
      </Box>

      {events.length === 0 && (
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#30363D' }}>
          No events yet.
        </Typography>
      )}

      <Box sx={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
        {shown.map((ev, i) => {
          const catColor = CATEGORY_COLORS[ev.category] ?? '#484F58';
          const ts = ev.ts ? ev.ts.split('T')[1]?.slice(0, 8) : '';
          return (
            <Box key={`${ev.id}-${i}`} sx={{ display: 'flex', alignItems: 'baseline', gap: 1 }}>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#30363D', flexShrink: 0, minWidth: 64 }}>
                {ts}
              </Typography>
              <Typography sx={{
                fontFamily: 'monospace', fontSize: '0.58rem', color: catColor,
                flexShrink: 0, minWidth: 80, letterSpacing: '0.04em',
              }}>
                {ev.category}
              </Typography>
              <Typography sx={{
                fontFamily: 'monospace', fontSize: '0.58rem', color: '#6E7681',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {ev.message ?? ''}
              </Typography>
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}

// ── ExpertOverlay ─────────────────────────────────────────────────────────────

interface Props {
  runtime: RuntimeStatus | undefined | null;
  demoStatus: any;
  sseEvents: SSEEvent[];
}

export default function ExpertOverlay({ runtime, demoStatus, sseEvents }: Props) {
  return (
    <Box
      data-testid="expert-overlay"
      sx={{
        mx: 2, mb: 2,
        background: '#0D1117',
        border: '1px solid #1F6FEB33',
        borderRadius: '6px',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <Box sx={{
        display: 'flex', alignItems: 'center', gap: 1.5,
        px: 2, py: '8px',
        borderBottom: '1px solid #1F6FEB22',
        background: '#0d1930',
      }}>
        <Typography sx={{
          fontFamily: 'monospace', fontSize: '0.6rem', fontWeight: 700,
          color: '#58A6FF', letterSpacing: '0.1em', textTransform: 'uppercase',
        }}>
          Expert view
        </Typography>
        <Box sx={{ width: '1px', height: 10, background: '#1F6FEB33', flexShrink: 0 }} />
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#30363D' }}>
          {demoStatus?.scenario?.name ?? 'no scenario'} · {demoStatus?.world?.elapsed_seconds ?? 0}s elapsed
        </Typography>
      </Box>

      {/* Grid */}
      <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 2fr', gap: 0 }}>
        {[
          { id: 'runtime', content: <RuntimeSection runtime={runtime} /> },
          { id: 'mcp',     content: <McpSection runtime={runtime} /> },
          { id: 'agents',  content: <AgentSection runtime={runtime} /> },
          { id: 'sse',     content: <SseSection events={sseEvents} /> },
        ].map(({ id, content }, i) => (
          <Box
            key={id}
            sx={{
              p: 1.5,
              borderRight: i < 3 ? '1px solid #1F6FEB1A' : 'none',
            }}
          >
            {content}
          </Box>
        ))}
      </Box>
    </Box>
  );
}
