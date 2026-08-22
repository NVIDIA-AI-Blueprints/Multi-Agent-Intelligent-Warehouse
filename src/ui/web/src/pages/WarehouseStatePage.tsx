import React, { useState } from 'react';
import {
  Box,
  Typography,
  Tabs,
  Tab,
  Card,
  CardContent,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  Alert,
  CircularProgress,
  Tooltip,
} from '@mui/material';
import {
  Warning as StaleIcon,
  CheckCircle as FreshIcon,
} from '@mui/icons-material';
import { useQuery } from '@tanstack/react-query';
import { format, parseISO, differenceInMinutes } from 'date-fns';
import { equipmentAPI, operationsAPI, safetyAPI } from '../services/api';

const STALE_THRESHOLD_MINUTES = 10;

function freshnessChip(updatedAt: string | undefined) {
  if (!updatedAt) return null;
  const ageMin = differenceInMinutes(new Date(), parseISO(updatedAt));
  const isStale = ageMin > STALE_THRESHOLD_MINUTES;
  return (
    <Tooltip title={`Last updated ${ageMin}m ago`} arrow>
      <Chip
        icon={isStale ? <StaleIcon sx={{ fontSize: '12px !important' }} /> : <FreshIcon sx={{ fontSize: '12px !important' }} />}
        label={isStale ? `${ageMin}m ago` : 'Fresh'}
        size="small"
        sx={{
          backgroundColor: isStale ? 'rgba(210, 153, 34, 0.15)' : 'rgba(63, 185, 80, 0.1)',
          color: isStale ? 'warning.main' : 'success.main',
          border: '1px solid',
          borderColor: isStale ? 'warning.main' : 'success.main',
          fontSize: '0.65rem',
          height: 20,
        }}
      />
    </Tooltip>
  );
}

function statusChip(status: string) {
  const colors: Record<string, 'success' | 'error' | 'warning' | 'info' | 'default'> = {
    active: 'success',
    available: 'success',
    operational: 'success',
    maintenance: 'warning',
    pending: 'warning',
    critical: 'error',
    inactive: 'default',
    resolved: 'success',
    open: 'error',
  };
  return <Chip label={status} size="small" color={colors[status.toLowerCase()] ?? 'default'} variant="outlined" />;
}

function EquipmentTab() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['equipment'],
    queryFn: equipmentAPI.getAllAssets,
    staleTime: 30000,
  });

  if (isLoading) return <CircularProgress sx={{ m: 3 }} />;
  if (error) return <Alert severity="error" sx={{ m: 2 }}>Failed to load equipment state</Alert>;
  if (!data?.length) return <Alert severity="info" sx={{ m: 2 }}>No equipment assets found</Alert>;

  return (
    <TableContainer>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Asset ID</TableCell>
            <TableCell>Type</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Zone</TableCell>
            <TableCell>Assignee</TableCell>
            <TableCell>Next PM</TableCell>
            <TableCell>Freshness</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {data.map((asset) => {
            const pmDue = asset.next_pm_due ? parseISO(asset.next_pm_due) : null;
            const pmOverdue = pmDue && pmDue <= new Date();
            return (
              <TableRow
                key={asset.asset_id}
                sx={{
                  '&:hover': { backgroundColor: 'rgba(255,255,255,0.03)' },
                  borderLeft: pmOverdue ? '3px solid' : '3px solid transparent',
                  borderLeftColor: pmOverdue ? 'warning.main' : 'transparent',
                }}
              >
                <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{asset.asset_id}</TableCell>
                <TableCell>{asset.type}</TableCell>
                <TableCell>{statusChip(asset.status)}</TableCell>
                <TableCell>{asset.zone ?? '—'}</TableCell>
                <TableCell>{asset.owner_user ?? '—'}</TableCell>
                <TableCell sx={{ color: pmOverdue ? 'warning.main' : 'text.secondary', fontSize: '0.8rem' }}>
                  {pmDue ? format(pmDue, 'MM/dd HH:mm') : '—'}
                </TableCell>
                <TableCell>{freshnessChip(asset.updated_at)}</TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function TasksTab() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['tasks'],
    queryFn: operationsAPI.getTasks,
    staleTime: 30000,
  });

  if (isLoading) return <CircularProgress sx={{ m: 3 }} />;
  if (error) return <Alert severity="error" sx={{ m: 2 }}>Failed to load operations tasks</Alert>;
  if (!data?.length) return <Alert severity="info" sx={{ m: 2 }}>No tasks found</Alert>;

  return (
    <TableContainer>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>ID</TableCell>
            <TableCell>Type</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Assignee</TableCell>
            <TableCell>Created</TableCell>
            <TableCell>Freshness</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {data.map((task) => (
            <TableRow key={task.id} sx={{ '&:hover': { backgroundColor: 'rgba(255,255,255,0.03)' } }}>
              <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{task.id}</TableCell>
              <TableCell>{task.kind}</TableCell>
              <TableCell>{statusChip(task.status)}</TableCell>
              <TableCell>{task.assignee || '—'}</TableCell>
              <TableCell sx={{ color: 'text.secondary', fontSize: '0.8rem' }}>
                {task.created_at ? format(parseISO(task.created_at), 'MM/dd HH:mm') : '—'}
              </TableCell>
              <TableCell>{freshnessChip(task.updated_at)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function WorkforceTab() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['workforce'],
    queryFn: operationsAPI.getWorkforceStatus,
    staleTime: 30000,
  });

  if (isLoading) return <CircularProgress sx={{ m: 3 }} />;
  if (error) return <Alert severity="error" sx={{ m: 2 }}>Failed to load workforce status</Alert>;
  if (!data) return <Alert severity="info" sx={{ m: 2 }}>No workforce data available</Alert>;

  return (
    <Box sx={{ p: 2 }}>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, mb: 2 }}>
        {[
          { label: 'Total Workers', value: data.total_workers ?? data.total },
          { label: 'Active', value: data.active_workers ?? data.active },
          { label: 'Available', value: data.available_workers ?? data.available },
          { label: 'Shift', value: data.shift ?? '—' },
        ].map(({ label, value }) => (
          <Card key={label} sx={{ minWidth: 120, backgroundColor: '#0D1117' }}>
            <CardContent sx={{ py: 1.5, px: 2, '&:last-child': { pb: 1.5 } }}>
              <Typography variant="h5" sx={{ fontWeight: 700, color: 'text.primary' }}>{value ?? '—'}</Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>{label}</Typography>
            </CardContent>
          </Card>
        ))}
      </Box>
      {data.zone_allocations && (
        <>
          <Typography variant="subtitle2" sx={{ color: 'text.secondary', mb: 1, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Zone Allocations
          </Typography>
          <pre style={{ fontFamily: 'monospace', fontSize: '0.8rem', color: '#8B949E', margin: 0 }}>
            {JSON.stringify(data.zone_allocations, null, 2)}
          </pre>
        </>
      )}
    </Box>
  );
}

function IncidentsTab() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['incidents'],
    queryFn: safetyAPI.getIncidents,
    staleTime: 30000,
  });

  if (isLoading) return <CircularProgress sx={{ m: 3 }} />;
  if (error) return <Alert severity="error" sx={{ m: 2 }}>Failed to load safety incidents</Alert>;
  if (!data?.length) return <Alert severity="success" sx={{ m: 2 }}>No safety incidents on record</Alert>;

  return (
    <TableContainer>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>ID</TableCell>
            <TableCell>Severity</TableCell>
            <TableCell>Description</TableCell>
            <TableCell>Reported By</TableCell>
            <TableCell>Occurred At</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {data.map((incident) => (
            <TableRow key={incident.id} sx={{ '&:hover': { backgroundColor: 'rgba(255,255,255,0.03)' } }}>
              <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{incident.id}</TableCell>
              <TableCell>{statusChip(incident.severity)}</TableCell>
              <TableCell sx={{ maxWidth: 300 }}>{incident.description}</TableCell>
              <TableCell>{incident.reported_by}</TableCell>
              <TableCell sx={{ color: 'text.secondary', fontSize: '0.8rem' }}>
                {incident.occurred_at ? format(parseISO(incident.occurred_at), 'MM/dd HH:mm') : '—'}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function PoliciesTab() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['safety-policies'],
    queryFn: safetyAPI.getPolicies,
    staleTime: 60000,
  });

  if (isLoading) return <CircularProgress sx={{ m: 3 }} />;
  if (error) return <Alert severity="error" sx={{ m: 2 }}>Failed to load safety policies</Alert>;
  if (!data?.length) return <Alert severity="info" sx={{ m: 2 }}>No safety policies found</Alert>;

  return (
    <TableContainer>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Domain</TableCell>
            <TableCell>Rule</TableCell>
            <TableCell>Active</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {data.map((policy: any, i: number) => (
            <TableRow key={i} sx={{ '&:hover': { backgroundColor: 'rgba(255,255,255,0.03)' } }}>
              <TableCell>{policy.domain}</TableCell>
              <TableCell sx={{ maxWidth: 400 }}>{policy.rule}</TableCell>
              <TableCell>
                <Chip label={policy.active ? 'Active' : 'Inactive'} size="small" color={policy.active ? 'success' : 'default'} variant="outlined" />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

const TABS = [
  { label: 'Equipment', component: EquipmentTab },
  { label: 'Tasks', component: TasksTab },
  { label: 'Workforce', component: WorkforceTab },
  { label: 'Incidents', component: IncidentsTab },
  { label: 'Policies', component: PoliciesTab },
];

const WarehouseStatePage: React.FC = () => {
  const [tab, setTab] = useState(0);
  const Component = TABS[tab].component;

  return (
    <Box sx={{ pb: 4 }}>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" sx={{ fontWeight: 700, color: 'text.primary', letterSpacing: '-0.02em' }}>
          Warehouse State
        </Typography>
        <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
          Live operational state across all domains · Amber border = stale data ({STALE_THRESHOLD_MINUTES}+ min)
        </Typography>
      </Box>

      <Card sx={{ backgroundColor: 'background.paper' }}>
        <Box sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
          <Tabs
            value={tab}
            onChange={(_, v) => setTab(v)}
            sx={{ px: 2 }}
          >
            {TABS.map(({ label }) => (
              <Tab key={label} label={label} sx={{ textTransform: 'none', fontWeight: 600, fontSize: '0.875rem' }} />
            ))}
          </Tabs>
        </Box>
        <Component />
      </Card>
    </Box>
  );
};

export default WarehouseStatePage;
