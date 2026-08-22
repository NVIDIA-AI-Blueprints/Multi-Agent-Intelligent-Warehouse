import React from 'react';
import {
  Box,
  Grid,
  Typography,
  Chip,
  CircularProgress,
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useRuntimeStatus } from '../hooks/useRuntimeStatus';
import { equipmentAPI, operationsAPI, safetyAPI, mcpAPI } from '../services/api';

interface NavCard {
  label: string;
  description: string;
  path: string;
  tag: string;
}

const NAV_CARDS: NavCard[] = [
  { label: 'STATE', description: 'Equipment · Operations · Safety — live warehouse state with freshness indicators', path: '/state', tag: 'READ' },
  { label: 'DECISIONS', description: 'Full decision lifecycle — trigger actions, view approve/reject results', path: '/decisions', tag: 'WRITE' },
  { label: 'MODELS', description: 'ModelGateway · Nemotron role registry · DecisionEngine availability', path: '/models', tag: 'INFO' },
  { label: 'CAPABILITIES', description: 'MCP v2 domain capability plane — READ / PROPOSAL / EXECUTION per skill', path: '/capabilities', tag: 'INFO' },
  { label: 'ACTIVITY', description: 'Live session activity feed — terminal view of all API interactions', path: '/activity', tag: 'LIVE' },
  { label: 'HEALTH', description: 'System health grid: API · Runtime · MCP domains · Database · Redis', path: '/health', tag: 'OPS' },
];

const TAG_COLORS: Record<string, string> = {
  READ: '#58A6FF',
  WRITE: '#3FB950',
  INFO: '#76B900',
  LIVE: '#F85149',
  OPS: '#D29922',
};

function Panel({ children, title, tag }: { children: React.ReactNode; title?: string; tag?: string }) {
  return (
    <Box
      sx={{
        backgroundColor: '#0D1117',
        border: '1px solid #21262D',
        borderRadius: 1,
        overflow: 'hidden',
      }}
    >
      {title && (
        <Box
          sx={{
            px: 1.5,
            py: 0.75,
            borderBottom: '1px solid #21262D',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            backgroundColor: '#080C10',
          }}
        >
          <Typography
            sx={{
              fontFamily: 'monospace',
              fontSize: '0.68rem',
              fontWeight: 700,
              color: '#8B949E',
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
            }}
          >
            {title}
          </Typography>
          {tag && (
            <Typography
              sx={{
                fontFamily: 'monospace',
                fontSize: '0.6rem',
                color: TAG_COLORS[tag] ?? '#484F58',
                fontWeight: 700,
                letterSpacing: '0.06em',
              }}
            >
              {tag}
            </Typography>
          )}
        </Box>
      )}
      <Box sx={{ p: 1.5 }}>{children}</Box>
    </Box>
  );
}

function StatRow({ label, value, ok }: { label: string; value: string | number; ok?: boolean }) {
  return (
    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', py: 0.4 }}>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.72rem', color: '#6E7681' }}>{label}</Typography>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.72rem', color: ok === false ? '#D29922' : '#C9D1D9', fontWeight: 600 }}>
        {value}
      </Typography>
    </Box>
  );
}

function BoolRow({ label, value }: { label: string; value: boolean | undefined }) {
  return (
    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', py: 0.3 }}>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.7rem', color: '#6E7681' }}>{label}</Typography>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
        <Box sx={{
          width: 5, height: 5, borderRadius: '50%',
          backgroundColor: value === undefined ? '#30363D' : value ? '#3FB950' : '#484F58',
          boxShadow: value ? '0 0 3px #3FB950' : 'none',
        }} />
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.7rem', color: value ? '#3FB950' : '#484F58' }}>
          {value === undefined ? 'unknown' : value ? 'ready' : 'unavailable'}
        </Typography>
      </Box>
    </Box>
  );
}

const CommandCenter: React.FC = () => {
  const navigate = useNavigate();
  const { data: runtime, isLoading: runtimeLoading } = useRuntimeStatus();

  const { data: equipment } = useQuery({ queryKey: ['equipment'], queryFn: equipmentAPI.getAllAssets, retry: 1, staleTime: 30000 });
  const { data: tasks } = useQuery({ queryKey: ['tasks'], queryFn: operationsAPI.getTasks, retry: 1, staleTime: 30000 });
  const { data: incidents } = useQuery({ queryKey: ['incidents'], queryFn: safetyAPI.getIncidents, retry: 1, staleTime: 30000 });
  const { data: mcpStatus } = useQuery({ queryKey: ['mcp-status'], queryFn: mcpAPI.getStatus, retry: 1, staleTime: 30000 });

  const maintenanceCount = equipment?.filter(a => a.status === 'maintenance' || (a.next_pm_due && new Date(a.next_pm_due) <= new Date())).length ?? 0;
  const pendingTaskCount = tasks?.filter(t => t.status === 'pending').length ?? 0;
  const openIncidentCount = incidents?.length ?? 0;
  const mcpDomainCount = runtime ? [runtime.inventory_mcp_configured, runtime.equipment_mcp_configured, runtime.labor_mcp_configured, runtime.wave_mcp_configured].filter(Boolean).length : 0;

  return (
    <Box sx={{ pb: 2 }}>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 2, mb: 2 }}>
        <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '1.1rem', color: '#76B900', letterSpacing: '0.04em' }}>
          COMMAND CENTER
        </Typography>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.7rem', color: '#484F58' }}>
          Multi-Agent Intelligent Warehouse · v2
        </Typography>
        {runtimeLoading && <CircularProgress size={12} sx={{ color: '#484F58' }} />}
      </Box>

      {/* Pipeline banner */}
      <Box
        sx={{
          backgroundColor: '#080C10',
          border: '1px solid #1C2128',
          borderLeft: '3px solid #76B900',
          borderRadius: 1,
          px: 2,
          py: 1,
          mb: 2,
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          overflowX: 'auto',
        }}
      >
        {['STATE', 'REASON', 'PROPOSE', 'DECIDE', 'EXECUTE', 'MCP', 'BACKEND'].map((step, i, arr) => (
          <React.Fragment key={step}>
            <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.7rem', color: step === 'DECIDE' ? '#76B900' : '#484F58', letterSpacing: '0.06em', whiteSpace: 'nowrap' }}>
              {step}
            </Typography>
            {i < arr.length - 1 && <Typography sx={{ color: '#21262D', fontFamily: 'monospace', fontSize: '0.75rem' }}>→</Typography>}
          </React.Fragment>
        ))}
        <Box sx={{ flexGrow: 1 }} />
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
          <Box sx={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: runtime?.runtime_initialized ? '#3FB950' : '#484F58', boxShadow: runtime?.runtime_initialized ? '0 0 4px #3FB950' : 'none' }} />
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: runtime?.runtime_initialized ? '#3FB950' : '#484F58' }}>
            {runtime?.runtime_initialized ? 'PIPELINE READY' : 'PIPELINE NOT READY'}
          </Typography>
        </Box>
      </Box>

      <Grid container spacing={1.5}>
        {/* Left column */}
        <Grid item xs={12} md={4}>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
            {/* Warehouse summary */}
            <Panel title="Warehouse State" tag="READ">
              <StatRow label="equipment assets" value={equipment?.length ?? '—'} />
              <StatRow label="maintenance needed" value={maintenanceCount} ok={maintenanceCount === 0} />
              <StatRow label="pending tasks" value={pendingTaskCount} ok={pendingTaskCount === 0} />
              <StatRow label="open incidents" value={openIncidentCount} ok={openIncidentCount === 0} />
              <StatRow label="mcp domains" value={`${mcpDomainCount}/4`} ok={mcpDomainCount === 4} />
            </Panel>

            {/* Pipeline components */}
            <Panel title="AI Pipeline Components" tag="STATUS">
              <BoolRow label="ModelGateway" value={runtime?.model_gateway_available} />
              <BoolRow label="DecisionEngine" value={runtime?.decision_engine_available} />
              <BoolRow label="StateProvider" value={runtime?.state_provider_available} />
              <BoolRow label="Equipment Agent" value={runtime?.equipment_agent_available} />
              <BoolRow label="Operations Agent" value={runtime?.operations_agent_available} />
              <BoolRow label="Safety Agent" value={runtime?.safety_agent_available} />
              <BoolRow label="Equip. Executor" value={runtime?.equipment_executor_available} />
              <BoolRow label="Labor Executor" value={runtime?.labor_executor_available} />
              <BoolRow label="Wave Executor" value={runtime?.wave_executor_available} />
            </Panel>

            {/* MCP */}
            <Panel title="MCP Domain Servers" tag="MCP">
              <BoolRow label="Inventory :8765" value={runtime?.inventory_mcp_configured} />
              <BoolRow label="Equipment :8766" value={runtime?.equipment_mcp_configured} />
              <BoolRow label="Labor :8767" value={runtime?.labor_mcp_configured} />
              <BoolRow label="Wave :8768" value={runtime?.wave_mcp_configured} />
              {mcpStatus?.domains && (
                <Box sx={{ mt: 1, pt: 1, borderTop: '1px solid #21262D' }}>
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58' }}>
                    {mcpStatus.client_ready ? '● client ready' : '○ client not ready'}
                  </Typography>
                </Box>
              )}
            </Panel>
          </Box>
        </Grid>

        {/* Right column — view cards */}
        <Grid item xs={12} md={8}>
          <Grid container spacing={1.5}>
            {NAV_CARDS.map(({ label, description, path, tag }) => (
              <Grid item xs={12} sm={6} key={label}>
                <Box
                  onClick={() => navigate(path)}
                  sx={{
                    backgroundColor: '#0D1117',
                    border: '1px solid #21262D',
                    borderRadius: 1,
                    overflow: 'hidden',
                    cursor: 'pointer',
                    transition: 'border-color 0.15s ease',
                    '&:hover': { borderColor: '#76B900' },
                    height: '100%',
                    display: 'flex',
                    flexDirection: 'column',
                  }}
                >
                  <Box sx={{ px: 1.5, py: 0.75, borderBottom: '1px solid #21262D', backgroundColor: '#080C10', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <Typography sx={{ fontFamily: 'monospace', fontSize: '0.75rem', fontWeight: 700, color: '#E6EDF3', letterSpacing: '0.06em' }}>
                      {label}
                    </Typography>
                    <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: TAG_COLORS[tag] ?? '#484F58', fontWeight: 700 }}>
                      {tag}
                    </Typography>
                  </Box>
                  <Box sx={{ p: 1.5, flexGrow: 1 }}>
                    <Typography sx={{ fontSize: '0.78rem', color: '#6E7681', lineHeight: 1.5 }}>
                      {description}
                    </Typography>
                  </Box>
                </Box>
              </Grid>
            ))}
          </Grid>

          {/* Terminal-style runtime log */}
          <Box sx={{ mt: 1.5 }}>
            <Panel title="Runtime Info" tag="LIVE">
              <Box sx={{ fontFamily: 'monospace', fontSize: '0.72rem', color: '#6E7681', lineHeight: 2 }}>
                {runtime ? (
                  <>
                    <Box component="span" sx={{ color: '#76B900' }}>$ </Box>
                    <Box component="span" sx={{ color: '#8B949E' }}>GET /api/v1/runtime/status </Box>
                    <Box component="span" sx={{ color: '#3FB950' }}>200 OK</Box>
                    <br />
                    <Box component="span" sx={{ color: '#484F58' }}>  runtime_initialized: </Box>
                    <Box component="span" sx={{ color: runtime.runtime_initialized ? '#3FB950' : '#F85149' }}>
                      {String(runtime.runtime_initialized)}
                    </Box>
                    <br />
                    <Box component="span" sx={{ color: '#484F58' }}>  model_gateway_available: </Box>
                    <Box component="span" sx={{ color: runtime.model_gateway_available ? '#3FB950' : '#F85149' }}>
                      {String(runtime.model_gateway_available)}
                    </Box>
                    <br />
                    <Box component="span" sx={{ color: '#484F58' }}>  decision_engine_available: </Box>
                    <Box component="span" sx={{ color: runtime.decision_engine_available ? '#3FB950' : '#F85149' }}>
                      {String(runtime.decision_engine_available)}
                    </Box>
                    <br />
                    <Box component="span" sx={{ color: '#484F58' }}>  uptime: </Box>
                    <Box component="span" sx={{ color: '#8B949E' }}>{runtime.uptime_seconds}s</Box>
                  </>
                ) : (
                  <>
                    <Box component="span" sx={{ color: '#76B900' }}>$ </Box>
                    <Box component="span" sx={{ color: '#8B949E' }}>GET /api/v1/runtime/status </Box>
                    <Box component="span" sx={{ color: '#D29922' }}>polling…</Box>
                  </>
                )}
              </Box>
            </Panel>
          </Box>
        </Grid>
      </Grid>
    </Box>
  );
};

export default CommandCenter;
