import React from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Grid,
  CircularProgress,
} from '@mui/material';
import {
  CheckCircle as GreenIcon,
  Warning as AmberIcon,
  Error as RedIcon,
  HelpOutline as UnknownIcon,
} from '@mui/icons-material';
import { useQuery } from '@tanstack/react-query';
import { useRuntimeStatus } from '../hooks/useRuntimeStatus';
import { healthAPI } from '../services/api';

type HealthStatus = 'green' | 'amber' | 'red' | 'unknown';

interface HealthItem {
  label: string;
  status: HealthStatus;
  detail?: string;
}

function statusIcon(status: HealthStatus) {
  const sz = { fontSize: 20 };
  return {
    green: <GreenIcon sx={{ ...sz, color: '#3FB950' }} />,
    amber: <AmberIcon sx={{ ...sz, color: '#D29922' }} />,
    red: <RedIcon sx={{ ...sz, color: '#F85149' }} />,
    unknown: <UnknownIcon sx={{ ...sz, color: '#484F58' }} />,
  }[status];
}

function boolToStatus(val: boolean | undefined, falseIsRed = true): HealthStatus {
  if (val === undefined) return 'unknown';
  if (val) return 'green';
  return falseIsRed ? 'red' : 'amber';
}

function serviceStatus(svc: any): HealthStatus {
  if (!svc) return 'unknown';
  const s = svc.status ?? svc;
  if (s === 'healthy' || s === 'ok' || s === true) return 'green';
  if (s === 'degraded' || s === 'warning') return 'amber';
  if (s === 'unhealthy' || s === false) return 'red';
  return 'unknown';
}

function HealthCell({ item }: { item: HealthItem }) {
  const borderColor = { green: '#3FB95033', amber: '#D2992233', red: '#F8514933', unknown: '#21262D' }[item.status];
  return (
    <Grid item xs={12} sm={6} md={4} lg={3}>
      <Box
        sx={{
          backgroundColor: '#0D1117',
          border: `1px solid ${borderColor}`,
          borderRadius: 2,
          p: 2,
          display: 'flex',
          alignItems: 'flex-start',
          gap: 1.5,
          height: '100%',
        }}
      >
        <Box sx={{ flexShrink: 0, mt: 0.25 }}>{statusIcon(item.status)}</Box>
        <Box>
          <Typography variant="body2" sx={{ fontWeight: 700, color: 'text.primary', fontSize: '0.85rem' }}>
            {item.label}
          </Typography>
          {item.detail && (
            <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mt: 0.25 }}>
              {item.detail}
            </Typography>
          )}
        </Box>
      </Box>
    </Grid>
  );
}

const SystemHealth: React.FC = () => {
  const { data: runtime, isLoading: runtimeLoading } = useRuntimeStatus();

  const { data: live, isLoading: liveLoading } = useQuery({
    queryKey: ['live'],
    queryFn: healthAPI.getLive,
    refetchInterval: 15000,
    retry: 0,
    staleTime: 10000,
  });

  const { data: fullHealth, isLoading: healthLoading } = useQuery({
    queryKey: ['full-health'],
    queryFn: healthAPI.getFull,
    refetchInterval: 30000,
    retry: 1,
    staleTime: 20000,
  });

  const isLoading = runtimeLoading || liveLoading || healthLoading;

  const apiStatus: HealthStatus = live === undefined ? 'unknown' : live.status === 'alive' ? 'green' : 'red';
  const dbStatus = serviceStatus(fullHealth?.services?.database);
  const redisStatus = serviceStatus(fullHealth?.services?.redis);
  const milvusStatus = serviceStatus(fullHealth?.services?.milvus);

  const coreItems: HealthItem[] = [
    { label: 'API Process', status: apiStatus, detail: 'GET /api/v1/live' },
    { label: 'MAIWRuntime', status: boolToStatus(runtime?.runtime_initialized), detail: 'runtime_initialized' },
    { label: 'ModelGateway', status: boolToStatus(runtime?.model_gateway_available), detail: 'model_gateway_available' },
    { label: 'DecisionEngine', status: boolToStatus(runtime?.decision_engine_available), detail: 'decision_engine_available' },
    { label: 'StateProvider', status: boolToStatus(runtime?.state_provider_available, false), detail: 'state_provider_available' },
  ];

  const mcpItems: HealthItem[] = [
    { label: 'MCP Inventory', status: boolToStatus(runtime?.inventory_mcp_configured, false), detail: ':8765 · streamable-http' },
    { label: 'MCP Equipment', status: boolToStatus(runtime?.equipment_mcp_configured, false), detail: ':8766 · streamable-http' },
    { label: 'MCP Labor', status: boolToStatus(runtime?.labor_mcp_configured, false), detail: ':8767 · streamable-http' },
    { label: 'MCP Wave', status: boolToStatus(runtime?.wave_mcp_configured, false), detail: ':8768 · streamable-http' },
  ];

  const agentItems: HealthItem[] = [
    { label: 'Equipment Agent', status: boolToStatus(runtime?.equipment_agent_available, false), detail: 'Equipment Asset Operations' },
    { label: 'Operations Agent', status: boolToStatus(runtime?.operations_agent_available, false), detail: 'Operations Coordination' },
    { label: 'Safety Agent', status: boolToStatus(runtime?.safety_agent_available, false), detail: 'Safety Compliance' },
    { label: 'Equipment Executor', status: boolToStatus(runtime?.equipment_executor_available, false), detail: 'ActionExecutor · equipment' },
    { label: 'Labor Executor', status: boolToStatus(runtime?.labor_executor_available, false), detail: 'ActionExecutor · labor' },
    { label: 'Wave Executor', status: boolToStatus(runtime?.wave_executor_available, false), detail: 'ActionExecutor · wave' },
  ];

  const infraItems: HealthItem[] = [
    { label: 'Database', status: dbStatus, detail: fullHealth?.services?.database?.message ?? 'TimescaleDB / PostgreSQL' },
    { label: 'Redis', status: redisStatus, detail: fullHealth?.services?.redis?.message ?? 'Cache / session store' },
    { label: 'Milvus', status: milvusStatus, detail: fullHealth?.services?.milvus?.message ?? 'Vector database' },
  ];

  function Section({ title, items }: { title: string; items: HealthItem[] }) {
    return (
      <Box sx={{ mb: 3 }}>
        <Typography variant="subtitle2" sx={{ color: 'text.secondary', mb: 1.5, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', fontSize: '0.7rem' }}>
          {title}
        </Typography>
        <Grid container spacing={1.5}>
          {items.map((item) => <HealthCell key={item.label} item={item} />)}
        </Grid>
      </Box>
    );
  }

  return (
    <Box sx={{ pb: 4 }}>
      <Box sx={{ mb: 3, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 700, color: 'text.primary', letterSpacing: '-0.02em' }}>
            System Health
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
            All component status · Refreshes automatically every 15–30s
          </Typography>
        </Box>
        {isLoading && <CircularProgress size={20} sx={{ mt: 0.5 }} />}
      </Box>

      {/* Status legend */}
      <Box sx={{ display: 'flex', gap: 2, mb: 3, flexWrap: 'wrap' }}>
        {([['green', 'Healthy'], ['amber', 'Degraded'], ['red', 'Unavailable'], ['unknown', 'Unknown']] as [HealthStatus, string][]).map(([s, label]) => (
          <Box key={s} sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
            {statusIcon(s)}
            <Typography variant="caption" sx={{ color: 'text.secondary' }}>{label}</Typography>
          </Box>
        ))}
      </Box>

      <Section title="Core Pipeline" items={coreItems} />
      <Section title="MCP Domain Servers" items={mcpItems} />
      <Section title="Reasoning Agents & Executors" items={agentItems} />
      <Section title="Infrastructure" items={infraItems} />

      <Typography variant="caption" sx={{ color: '#484F58', display: 'block', mt: 2 }}>
        Amber = configured but not required for core function · Red = unavailable when expected · This is not a full monitoring platform — use Grafana for alerting.
      </Typography>
    </Box>
  );
};

export default SystemHealth;
