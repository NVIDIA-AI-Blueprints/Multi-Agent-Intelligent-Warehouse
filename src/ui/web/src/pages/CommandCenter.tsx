import React from 'react';
import {
  Box,
  Grid,
  Typography,
  Card,
  CardContent,
  CardActionArea,
  Chip,
  Divider,
  Alert,
  CircularProgress,
} from '@mui/material';
import {
  Inventory2 as StateIcon,
  Gavel as DecisionIcon,
  Psychology as ModelIcon,
  Hub as CapabilityIcon,
  Timeline as ActivityIcon,
  MonitorHeart as HealthIcon,
  CheckCircle as OkIcon,
  Warning as WarnIcon,
  Error as ErrorIcon,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useRuntimeStatus } from '../hooks/useRuntimeStatus';
import { equipmentAPI, operationsAPI, safetyAPI, mcpAPI } from '../services/api';

interface NavCard {
  label: string;
  description: string;
  path: string;
  icon: React.ReactNode;
}

const NAV_CARDS: NavCard[] = [
  { label: 'STATE', description: 'Equipment · Operations · Safety — live warehouse state with freshness indicators', path: '/state', icon: <StateIcon sx={{ fontSize: 32 }} /> },
  { label: 'DECISIONS', description: 'Full decision lifecycle: OBSERVE → REASON → PROPOSE → DECIDE → EXECUTE', path: '/decisions', icon: <DecisionIcon sx={{ fontSize: 32 }} /> },
  { label: 'MODELS', description: 'ModelGateway · Nemotron role registry · DecisionEngine availability', path: '/models', icon: <ModelIcon sx={{ fontSize: 32 }} /> },
  { label: 'CAPABILITIES', description: 'MCP v2 domain capability plane — READ / PROPOSAL / EXECUTION per skill', path: '/capabilities', icon: <CapabilityIcon sx={{ fontSize: 32 }} /> },
  { label: 'ACTIVITY', description: 'Live session activity feed — terminal view of all API interactions', path: '/activity', icon: <ActivityIcon sx={{ fontSize: 32 }} /> },
  { label: 'HEALTH', description: 'System health grid: API · Runtime · MCP domains · Database · Redis', path: '/health', icon: <HealthIcon sx={{ fontSize: 32 }} /> },
];

function StatusChip({ ok, label }: { ok: boolean | undefined; label?: string }) {
  if (ok === undefined) return <Chip label={label || 'Unknown'} size="small" sx={{ backgroundColor: '#21262D', color: '#8B949E' }} />;
  return ok
    ? <Chip icon={<OkIcon sx={{ fontSize: '14px !important' }} />} label={label || 'OK'} size="small" color="success" variant="outlined" />
    : <Chip icon={<ErrorIcon sx={{ fontSize: '14px !important' }} />} label={label || 'Unavailable'} size="small" color="error" variant="outlined" />;
}

const CommandCenter: React.FC = () => {
  const navigate = useNavigate();
  const { data: runtime, isLoading: runtimeLoading } = useRuntimeStatus();

  const { data: equipment } = useQuery({
    queryKey: ['equipment'],
    queryFn: equipmentAPI.getAllAssets,
    retry: 1,
    staleTime: 30000,
  });

  const { data: tasks } = useQuery({
    queryKey: ['tasks'],
    queryFn: operationsAPI.getTasks,
    retry: 1,
    staleTime: 30000,
  });

  const { data: incidents } = useQuery({
    queryKey: ['incidents'],
    queryFn: safetyAPI.getIncidents,
    retry: 1,
    staleTime: 30000,
  });

  const { data: mcpStatus } = useQuery({
    queryKey: ['mcp-status'],
    queryFn: mcpAPI.getStatus,
    retry: 1,
    staleTime: 30000,
  });

  const maintenanceCount = equipment?.filter(
    (a) => a.status === 'maintenance' || (a.next_pm_due && new Date(a.next_pm_due) <= new Date())
  ).length ?? 0;

  const pendingTaskCount = tasks?.filter((t) => t.status === 'pending').length ?? 0;
  const openIncidentCount = incidents?.filter((i: any) => i.status !== 'resolved').length ?? incidents?.length ?? 0;

  const mcpDomainCount = runtime
    ? [runtime.inventory_mcp_configured, runtime.equipment_mcp_configured, runtime.labor_mcp_configured, runtime.wave_mcp_configured].filter(Boolean).length
    : 0;

  return (
    <Box sx={{ pb: 4 }}>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" sx={{ fontWeight: 700, color: 'text.primary', letterSpacing: '-0.02em' }}>
          Command Center
        </Typography>
        <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
          MAIW v2 · Multi-Agent Intelligent Warehouse · AI Decision Pipeline
        </Typography>
      </Box>

      {/* Pipeline status banner */}
      <Box
        sx={{
          backgroundColor: '#0D1117',
          border: '1px solid #21262D',
          borderRadius: 2,
          p: 2,
          mb: 3,
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          overflowX: 'auto',
        }}
      >
        {['OBSERVE', 'REASON', 'PROPOSE', 'DECIDE', 'EXECUTE', 'MCP', 'BACKEND'].map((step, i, arr) => (
          <React.Fragment key={step}>
            <Typography
              variant="caption"
              sx={{
                fontFamily: 'monospace',
                fontWeight: 600,
                fontSize: '0.75rem',
                color: step === 'DECIDE' ? '#76B900' : '#8B949E',
                letterSpacing: '0.08em',
                whiteSpace: 'nowrap',
              }}
            >
              {step}
            </Typography>
            {i < arr.length - 1 && (
              <Typography variant="caption" sx={{ color: '#484F58', fontFamily: 'monospace' }}>→</Typography>
            )}
          </React.Fragment>
        ))}
        <Box sx={{ flexGrow: 1 }} />
        {runtimeLoading ? (
          <CircularProgress size={14} />
        ) : (
          <StatusChip ok={runtime?.runtime_initialized} label={runtime?.runtime_initialized ? 'Pipeline Ready' : 'Pipeline Not Ready'} />
        )}
      </Box>

      {/* Summary stats */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        {[
          { label: 'Equipment Assets', value: equipment?.length ?? '—', sub: `${maintenanceCount} need maintenance`, warn: maintenanceCount > 0 },
          { label: 'Pending Tasks', value: pendingTaskCount, sub: `of ${tasks?.length ?? 0} total tasks`, warn: pendingTaskCount > 5 },
          { label: 'Open Incidents', value: openIncidentCount, sub: 'safety incidents', warn: openIncidentCount > 0 },
          { label: 'MCP Domains', value: `${mcpDomainCount}/4`, sub: 'configured', warn: mcpDomainCount < 4 },
        ].map(({ label, value, sub, warn }) => (
          <Grid item xs={6} md={3} key={label}>
            <Card sx={{ backgroundColor: 'background.paper', height: '100%' }}>
              <CardContent sx={{ py: 2, px: 2, '&:last-child': { pb: 2 } }}>
                <Typography variant="h4" sx={{ fontWeight: 700, color: warn ? 'warning.main' : 'text.primary', lineHeight: 1 }}>
                  {value}
                </Typography>
                <Typography variant="body2" sx={{ color: 'text.primary', fontWeight: 600, mt: 0.5, fontSize: '0.8rem' }}>
                  {label}
                </Typography>
                <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                  {sub}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      {/* Pipeline component status */}
      <Card sx={{ mb: 3, backgroundColor: 'background.paper' }}>
        <CardContent>
          <Typography variant="subtitle2" sx={{ color: 'text.secondary', mb: 1.5, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', fontSize: '0.7rem' }}>
            AI Pipeline Components
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
            <StatusChip ok={runtime?.model_gateway_available} label="ModelGateway" />
            <StatusChip ok={runtime?.decision_engine_available} label="DecisionEngine" />
            <StatusChip ok={runtime?.state_provider_available} label="StateProvider" />
            <StatusChip ok={runtime?.equipment_agent_available} label="Equipment Agent" />
            <StatusChip ok={runtime?.operations_agent_available} label="Operations Agent" />
            <StatusChip ok={runtime?.safety_agent_available} label="Safety Agent" />
            <StatusChip ok={runtime?.equipment_executor_available} label="Equipment Executor" />
            <StatusChip ok={runtime?.labor_executor_available} label="Labor Executor" />
            <StatusChip ok={runtime?.wave_executor_available} label="Wave Executor" />
          </Box>
          <Divider sx={{ my: 1.5 }} />
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
            <StatusChip ok={runtime?.inventory_mcp_configured} label="MCP Inventory" />
            <StatusChip ok={runtime?.equipment_mcp_configured} label="MCP Equipment" />
            <StatusChip ok={runtime?.labor_mcp_configured} label="MCP Labor" />
            <StatusChip ok={runtime?.wave_mcp_configured} label="MCP Wave" />
          </Box>
        </CardContent>
      </Card>

      {/* Navigation cards */}
      <Typography variant="subtitle2" sx={{ color: 'text.secondary', mb: 1.5, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', fontSize: '0.7rem' }}>
        Views
      </Typography>
      <Grid container spacing={2}>
        {NAV_CARDS.map(({ label, description, path, icon }) => (
          <Grid item xs={12} sm={6} md={4} key={label}>
            <Card sx={{ height: '100%', transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)' }}>
              <CardActionArea onClick={() => navigate(path)} sx={{ height: '100%', p: 0.5 }}>
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.5 }}>
                    <Box sx={{ color: 'primary.main', mt: 0.25, flexShrink: 0 }}>{icon}</Box>
                    <Box>
                      <Typography
                        variant="h6"
                        sx={{
                          fontWeight: 700,
                          fontSize: '1rem',
                          fontFamily: 'monospace',
                          color: 'text.primary',
                          letterSpacing: '0.06em',
                        }}
                      >
                        {label}
                      </Typography>
                      <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.25, fontSize: '0.8rem' }}>
                        {description}
                      </Typography>
                    </Box>
                  </Box>
                </CardContent>
              </CardActionArea>
            </Card>
          </Grid>
        ))}
      </Grid>
    </Box>
  );
};

export default CommandCenter;
