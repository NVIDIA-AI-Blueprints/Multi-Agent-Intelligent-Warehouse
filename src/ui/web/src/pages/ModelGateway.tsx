import React from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Grid,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Alert,
  Divider,
} from '@mui/material';
import {
  CheckCircle as OkIcon,
  Error as ErrorIcon,
  Psychology as ModelIcon,
} from '@mui/icons-material';
import { useRuntimeStatus } from '../hooks/useRuntimeStatus';

const MODEL_ROLES = [
  { role: 'Lightning', description: 'Fastest responses — latency-critical tasks', model: 'Nemotron Lightning', note: 'Least capable, highest throughput' },
  { role: 'Nano', description: 'Compact efficient reasoning', model: 'Nemotron Nano', note: 'Balance of speed and capability' },
  { role: 'Super', description: 'General warehouse reasoning', model: 'Nemotron Super', note: 'Default for most assessments' },
  { role: 'Ultra', description: 'Complex multi-domain analysis', model: 'Nemotron Ultra', note: 'Most capable, used for high-stakes decisions' },
];

const AGENT_ROLES = [
  {
    id: 'equipment_agent',
    name: 'Equipment Asset Operations Agent',
    domain: 'Equipment',
    uses: 'ModelGateway · WarehouseState · Equipment Skills',
    field: 'equipment_agent_available' as const,
  },
  {
    id: 'operations_agent',
    name: 'Operations Coordination Agent',
    domain: 'Labor / Wave',
    uses: 'ModelGateway · WarehouseState · Labor + Wave Skills',
    field: 'operations_agent_available' as const,
  },
  {
    id: 'safety_agent',
    name: 'Safety Compliance Agent',
    domain: 'Safety',
    uses: 'ModelGateway · WarehouseState · Safety Policies',
    field: 'safety_agent_available' as const,
  },
];

function AvailabilityChip({ available }: { available: boolean | undefined }) {
  if (available === undefined) return <Chip label="Unknown" size="small" sx={{ backgroundColor: '#21262D', color: '#8B949E' }} />;
  return available
    ? <Chip icon={<OkIcon sx={{ fontSize: '14px !important' }} />} label="Available" size="small" color="success" variant="outlined" />
    : <Chip icon={<ErrorIcon sx={{ fontSize: '14px !important' }} />} label="Unavailable" size="small" color="error" variant="outlined" />;
}

const ModelGateway: React.FC = () => {
  const { data: runtime, isLoading } = useRuntimeStatus();

  return (
    <Box sx={{ pb: 4 }}>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" sx={{ fontWeight: 700, color: 'text.primary', letterSpacing: '-0.02em' }}>
          Models
        </Typography>
        <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
          ModelGateway routing · Nemotron role registry · Reasoning agents
        </Typography>
      </Box>

      {/* Gateway availability */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={4}>
          <Card sx={{ backgroundColor: 'background.paper' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
                <ModelIcon sx={{ color: 'primary.main', fontSize: 28 }} />
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>ModelGateway</Typography>
              </Box>
              <AvailabilityChip available={runtime?.model_gateway_available} />
              <Typography variant="caption" sx={{ display: 'block', color: 'text.secondary', mt: 1 }}>
                Routes tasks to Nemotron models by role. All warehouse reasoning flows through this gateway.
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={4}>
          <Card sx={{ backgroundColor: 'background.paper' }}>
            <CardContent>
              <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>DecisionEngine</Typography>
              <AvailabilityChip available={runtime?.decision_engine_available} />
              <Typography variant="caption" sx={{ display: 'block', color: 'text.secondary', mt: 1 }}>
                Evaluates ActionProposals and returns approved / rejected / requires_human_approval / requires_fresh_state.
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={4}>
          <Card sx={{ backgroundColor: 'background.paper' }}>
            <CardContent>
              <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>StateProvider</Typography>
              <AvailabilityChip available={runtime?.state_provider_available} />
              <Typography variant="caption" sx={{ display: 'block', color: 'text.secondary', mt: 1 }}>
                Assembles WarehouseState snapshots used by agents and the DecisionEngine for freshness checks.
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Nemotron role registry */}
      <Card sx={{ backgroundColor: 'background.paper', mb: 3 }}>
        <CardContent>
          <Typography variant="subtitle2" sx={{ color: 'text.secondary', mb: 2, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', fontSize: '0.7rem' }}>
            Nemotron Model Registry · Roles
          </Typography>
          <Alert severity="info" sx={{ mb: 2 }}>
            Models are addressed by logical role, not by name. The ModelGateway selects the appropriate model at runtime. Role→model mapping is configured in ModelRegistry (not exposed via API in this release).
          </Alert>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 700 }}>Role</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Model</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Use Case</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Notes</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {MODEL_ROLES.map(({ role, description, model, note }) => (
                  <TableRow key={role} sx={{ '&:hover': { backgroundColor: 'rgba(255,255,255,0.03)' } }}>
                    <TableCell>
                      <Chip label={role} size="small" sx={{ fontFamily: 'monospace', fontWeight: 700, backgroundColor: 'rgba(118,185,0,0.12)', color: 'primary.light', border: '1px solid rgba(118,185,0,0.3)' }} />
                    </TableCell>
                    <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{model}</TableCell>
                    <TableCell sx={{ color: 'text.secondary', fontSize: '0.85rem' }}>{description}</TableCell>
                    <TableCell sx={{ color: 'text.secondary', fontSize: '0.8rem' }}>{note}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>

      {/* Reasoning agents */}
      <Card sx={{ backgroundColor: 'background.paper' }}>
        <CardContent>
          <Typography variant="subtitle2" sx={{ color: 'text.secondary', mb: 2, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', fontSize: '0.7rem' }}>
            Reasoning Agents · Decision Pipeline Roles
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', mb: 2 }}>
            Agents are reasoning roles within the decision pipeline — not capability owners. They use ModelGateway and WarehouseState to produce ActionProposals which flow to the DecisionEngine.
          </Typography>
          <Divider sx={{ mb: 2 }} />
          <Grid container spacing={2}>
            {AGENT_ROLES.map(({ name, domain, uses, field }) => (
              <Grid item xs={12} md={4} key={field}>
                <Box
                  sx={{
                    backgroundColor: '#0D1117',
                    border: '1px solid #21262D',
                    borderRadius: 2,
                    p: 2,
                  }}
                >
                  <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body2" sx={{ fontWeight: 700, fontSize: '0.85rem' }}>{name}</Typography>
                    <AvailabilityChip available={runtime?.[field]} />
                  </Box>
                  <Chip label={domain} size="small" variant="outlined" sx={{ mb: 1, fontSize: '0.7rem' }} />
                  <Typography variant="caption" sx={{ display: 'block', color: 'text.secondary', fontFamily: 'monospace', fontSize: '0.7rem' }}>
                    {uses}
                  </Typography>
                </Box>
              </Grid>
            ))}
          </Grid>
        </CardContent>
      </Card>
    </Box>
  );
};

export default ModelGateway;
