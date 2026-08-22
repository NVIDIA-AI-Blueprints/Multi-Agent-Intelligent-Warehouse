import React from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Grid,
  Chip,
  Alert,
  CircularProgress,
  Divider,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from '@mui/material';
import {
  CheckCircle as OkIcon,
  Error as ErrorIcon,
  Visibility as ReadIcon,
  Send as ProposalIcon,
  PlayArrow as ExecutionIcon,
} from '@mui/icons-material';
import { useQuery } from '@tanstack/react-query';
import { useRuntimeStatus } from '../hooks/useRuntimeStatus';
import { mcpAPI } from '../services/api';

interface CapabilityInfo {
  domain: string;
  name: string;
  type: 'READ' | 'PROPOSAL' | 'EXECUTION';
  description: string;
  risk?: string;
}

const KNOWN_CAPABILITIES: CapabilityInfo[] = [
  { domain: 'inventory', name: 'warehouse.inventory.get', type: 'READ', description: 'Read inventory levels and SKU data' },
  { domain: 'inventory', name: 'warehouse.inventory.locate', type: 'READ', description: 'Locate inventory items by zone or SKU' },
  { domain: 'equipment', name: 'warehouse.equipment.get', type: 'READ', description: 'Read equipment asset state and telemetry' },
  { domain: 'equipment', name: 'warehouse.equipment.assign', type: 'EXECUTION', description: 'Assign equipment to a user or task', risk: 'medium' },
  { domain: 'equipment', name: 'warehouse.equipment.release', type: 'EXECUTION', description: 'Release equipment assignment', risk: 'low' },
  { domain: 'equipment', name: 'warehouse.equipment.maintenance', type: 'PROPOSAL', description: 'Schedule maintenance — triggers DecisionEngine', risk: 'low' },
  { domain: 'equipment', name: 'warehouse.equipment.status', type: 'READ', description: 'Read current equipment operational status' },
  { domain: 'labor', name: 'warehouse.labor.workforce', type: 'READ', description: 'Read workforce and shift status' },
  { domain: 'labor', name: 'warehouse.labor.assign_task', type: 'EXECUTION', description: 'Assign a task to a worker', risk: 'low' },
  { domain: 'labor', name: 'warehouse.labor.schedule', type: 'PROPOSAL', description: 'Propose shift schedule changes', risk: 'medium' },
  { domain: 'wave', name: 'warehouse.wave.status', type: 'READ', description: 'Read wave planning and fulfillment status' },
  { domain: 'wave', name: 'warehouse.wave.reprioritize', type: 'PROPOSAL', description: 'Propose wave reprioritization', risk: 'high' },
  { domain: 'wave', name: 'warehouse.wave.close', type: 'EXECUTION', description: 'Close a completed wave', risk: 'medium' },
];

const TYPE_CONFIG = {
  READ: { color: '#58A6FF', icon: <ReadIcon sx={{ fontSize: 12 }} />, label: 'READ' },
  PROPOSAL: { color: '#D29922', icon: <ProposalIcon sx={{ fontSize: 12 }} />, label: 'PROPOSAL' },
  EXECUTION: { color: '#3FB950', icon: <ExecutionIcon sx={{ fontSize: 12 }} />, label: 'EXECUTION' },
};

const RISK_CONFIG: Record<string, { color: 'success' | 'warning' | 'error' | 'default' }> = {
  low: { color: 'success' },
  medium: { color: 'warning' },
  high: { color: 'error' },
};

function TypeBadge({ type }: { type: 'READ' | 'PROPOSAL' | 'EXECUTION' }) {
  const cfg = TYPE_CONFIG[type];
  return (
    <Chip
      icon={cfg.icon as any}
      label={cfg.label}
      size="small"
      sx={{
        backgroundColor: `${cfg.color}1A`,
        color: cfg.color,
        border: `1px solid ${cfg.color}4D`,
        fontFamily: 'monospace',
        fontWeight: 700,
        fontSize: '0.65rem',
        letterSpacing: '0.04em',
        height: 22,
      }}
    />
  );
}

const DOMAINS = [
  { id: 'inventory', label: 'Inventory', portLabel: '8765', configuredField: 'inventory_mcp_configured' as const },
  { id: 'equipment', label: 'Equipment', portLabel: '8766', configuredField: 'equipment_mcp_configured' as const },
  { id: 'labor', label: 'Labor', portLabel: '8767', configuredField: 'labor_mcp_configured' as const },
  { id: 'wave', label: 'Wave', portLabel: '8768', configuredField: 'wave_mcp_configured' as const },
];

const CapabilityPlane: React.FC = () => {
  const { data: runtime } = useRuntimeStatus();
  const { data: mcpStatus, isLoading: statusLoading } = useQuery({
    queryKey: ['mcp-status'],
    queryFn: mcpAPI.getStatus,
    staleTime: 30000,
  });
  const { data: mcpCapabilities, isLoading: capsLoading } = useQuery({
    queryKey: ['mcp-capabilities'],
    queryFn: mcpAPI.getCapabilities,
    staleTime: 60000,
    retry: 1,
  });

  const isLoading = statusLoading || capsLoading;

  return (
    <Box sx={{ pb: 4 }}>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" sx={{ fontWeight: 700, color: 'text.primary', letterSpacing: '-0.02em' }}>
          Capability Plane
        </Typography>
        <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
          MCP v2 domain servers · Streamable HTTP · Stateless
        </Typography>
      </Box>

      {/* Type legend */}
      <Box sx={{ display: 'flex', gap: 1.5, mb: 3, flexWrap: 'wrap' }}>
        <TypeBadge type="READ" />
        <Typography variant="caption" sx={{ color: 'text.secondary', alignSelf: 'center' }}>Reads state — no action taken</Typography>
        <Divider orientation="vertical" flexItem />
        <TypeBadge type="PROPOSAL" />
        <Typography variant="caption" sx={{ color: 'text.secondary', alignSelf: 'center' }}>Proposes action — routes through DecisionEngine</Typography>
        <Divider orientation="vertical" flexItem />
        <TypeBadge type="EXECUTION" />
        <Typography variant="caption" sx={{ color: 'text.secondary', alignSelf: 'center' }}>Executes directly via ActionExecutor</Typography>
      </Box>

      {/* Domain status cards */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        {DOMAINS.map(({ id, label, portLabel, configuredField }) => {
          const configured = runtime?.[configuredField];
          const domainStatus = mcpStatus?.domains?.[id];
          return (
            <Grid item xs={12} sm={6} md={3} key={id}>
              <Card sx={{
                backgroundColor: 'background.paper',
                border: '1px solid',
                borderColor: configured ? 'rgba(63,185,80,0.3)' : '#21262D',
              }}>
                <CardContent sx={{ py: 2 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
                    <Typography variant="subtitle1" sx={{ fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', fontSize: '0.85rem' }}>
                      {label}
                    </Typography>
                    {configured ? (
                      <OkIcon sx={{ color: 'success.main', fontSize: 18 }} />
                    ) : (
                      <ErrorIcon sx={{ color: 'error.main', fontSize: 18 }} />
                    )}
                  </Box>
                  <Typography variant="caption" sx={{ color: 'text.secondary', fontFamily: 'monospace', display: 'block' }}>
                    :{portLabel} · streamable-http
                  </Typography>
                  {domainStatus && (
                    <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mt: 0.5 }}>
                      {domainStatus.tool_count ?? 0} tools discovered
                    </Typography>
                  )}
                  <Chip
                    label={configured ? 'Configured' : 'Not configured'}
                    size="small"
                    color={configured ? 'success' : 'default'}
                    variant="outlined"
                    sx={{ mt: 1, fontSize: '0.65rem', height: 20 }}
                  />
                </CardContent>
              </Card>
            </Grid>
          );
        })}
      </Grid>

      {/* Constraints notice */}
      <Alert severity="info" sx={{ mb: 3 }}>
        The UI calls only <code>apps/api</code> endpoints — never MCP servers directly. MCP servers are called by the ActionExecutor within the API process.
      </Alert>

      {/* Capability matrix */}
      <Card sx={{ backgroundColor: 'background.paper', mb: 3 }}>
        <CardContent>
          <Typography variant="subtitle2" sx={{ color: 'text.secondary', mb: 2, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', fontSize: '0.7rem' }}>
            Capability Matrix · Known Skills
          </Typography>
          {isLoading ? (
            <CircularProgress size={24} sx={{ m: 2 }} />
          ) : (
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 700, width: 100 }}>Domain</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>Capability</TableCell>
                    <TableCell sx={{ fontWeight: 700, width: 120 }}>Type</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>Description</TableCell>
                    <TableCell sx={{ fontWeight: 700, width: 90 }}>Risk</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {KNOWN_CAPABILITIES.map((cap) => (
                    <TableRow
                      key={cap.name}
                      sx={{
                        '&:hover': { backgroundColor: 'rgba(255,255,255,0.03)' },
                        opacity: runtime?.[`${cap.domain}_mcp_configured` as keyof typeof runtime] === false ? 0.4 : 1,
                      }}
                    >
                      <TableCell>
                        <Chip label={cap.domain} size="small" variant="outlined" sx={{ fontSize: '0.7rem', height: 20, textTransform: 'uppercase' }} />
                      </TableCell>
                      <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.75rem', color: '#8B949E' }}>{cap.name}</TableCell>
                      <TableCell><TypeBadge type={cap.type} /></TableCell>
                      <TableCell sx={{ color: 'text.secondary', fontSize: '0.8rem' }}>{cap.description}</TableCell>
                      <TableCell>
                        {cap.risk ? (
                          <Chip label={cap.risk} size="small" color={RISK_CONFIG[cap.risk]?.color ?? 'default'} variant="outlined" sx={{ fontSize: '0.65rem', height: 20 }} />
                        ) : (
                          <Typography variant="caption" sx={{ color: '#484F58' }}>—</Typography>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </CardContent>
      </Card>

      {/* Live capabilities from API */}
      {mcpCapabilities && (
        <Card sx={{ backgroundColor: 'background.paper' }}>
          <CardContent>
            <Typography variant="subtitle2" sx={{ color: 'text.secondary', mb: 2, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', fontSize: '0.7rem' }}>
              Live Capabilities from API
            </Typography>
            <Box
              component="pre"
              sx={{ fontFamily: 'monospace', fontSize: '0.75rem', color: '#8B949E', backgroundColor: '#0D1117', p: 2, borderRadius: 1, overflow: 'auto', maxHeight: 300 }}
            >
              {JSON.stringify(mcpCapabilities, null, 2)}
            </Box>
          </CardContent>
        </Card>
      )}
    </Box>
  );
};

export default CapabilityPlane;
