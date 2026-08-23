import React, { useState } from 'react';
import {
  Box,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  CircularProgress,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { format, parseISO, differenceInMinutes } from 'date-fns';
import { equipmentAPI, operationsAPI, safetyAPI } from '../services/api';

// ── design tokens (match CommandCenter) ───────────────────────────────────

const C = {
  bg: '#080C10',
  panel: '#0D1117',
  border: '#1C2128',
  borderMid: '#30363D',
  text: '#E6EDF3',
  textSub: '#C9D1D9',
  textMuted: '#8B949E',
  textDim: '#484F58',
  green: '#3FB950',
  yellow: '#D29922',
  red: '#F85149',
  blue: '#58A6FF',
  nvidia: '#76B900',
};

const STALE_THRESHOLD_MINUTES = 10;

// ── shared primitives ─────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <Typography sx={{
      fontFamily: 'monospace', fontWeight: 700, fontSize: '0.6rem',
      color: C.textDim, letterSpacing: '0.12em', textTransform: 'uppercase',
    }}>
      {children}
    </Typography>
  );
}

function StatusBadge({ status }: { status: string }) {
  const s = status.toLowerCase();
  let color = C.textMuted;
  let bg = 'rgba(139,148,158,0.08)';
  let border = C.borderMid;

  if (['active', 'available', 'operational', 'resolved', 'online'].includes(s)) {
    color = C.green; bg = 'rgba(63,185,80,0.08)'; border = 'rgba(63,185,80,0.3)';
  } else if (['maintenance', 'pending', 'charging', 'assigned'].includes(s)) {
    color = C.yellow; bg = 'rgba(210,153,34,0.08)'; border = 'rgba(210,153,34,0.3)';
  } else if (['critical', 'open', 'offline', 'error', 'on_leave'].includes(s)) {
    color = C.red; bg = 'rgba(248,81,73,0.08)'; border = 'rgba(248,81,73,0.3)';
  } else if (['inactive'].includes(s)) {
    color = C.textDim; bg = 'transparent'; border = C.border;
  }

  return (
    <Box component="span" sx={{
      display: 'inline-block',
      px: 0.75, py: '2px',
      fontFamily: 'monospace', fontSize: '0.65rem', fontWeight: 700,
      letterSpacing: '0.04em',
      color, backgroundColor: bg,
      border: '1px solid', borderColor: border,
      borderRadius: '3px',
      lineHeight: 1.6,
    }}>
      {status}
    </Box>
  );
}

function FreshnessTag({ updatedAt }: { updatedAt: string | undefined }) {
  if (!updatedAt) return <span style={{ color: C.textDim, fontFamily: 'monospace', fontSize: '0.65rem' }}>—</span>;
  const ageMin = differenceInMinutes(new Date(), parseISO(updatedAt));
  const isStale = ageMin > STALE_THRESHOLD_MINUTES;
  return (
    <Tooltip title={`Last updated ${ageMin}m ago`} arrow>
      <Box component="span" sx={{
        display: 'inline-flex', alignItems: 'center', gap: 0.4,
        px: 0.75, py: '2px',
        fontFamily: 'monospace', fontSize: '0.65rem', fontWeight: 600,
        color: isStale ? C.yellow : C.green,
        backgroundColor: isStale ? 'rgba(210,153,34,0.08)' : 'rgba(63,185,80,0.08)',
        border: '1px solid', borderColor: isStale ? 'rgba(210,153,34,0.3)' : 'rgba(63,185,80,0.3)',
        borderRadius: '3px',
        lineHeight: 1.6,
      }}>
        {isStale ? `⚠ ${ageMin}m ago` : '✓ Fresh'}
      </Box>
    </Tooltip>
  );
}

// ── table chrome ──────────────────────────────────────────────────────────

const TH = ({ children }: { children: React.ReactNode }) => (
  <TableCell sx={{
    fontFamily: 'monospace', fontSize: '0.6rem', fontWeight: 700,
    color: C.textDim, letterSpacing: '0.1em', textTransform: 'uppercase',
    borderBottom: `1px solid ${C.border}`,
    py: 0.75, px: 1.5,
    whiteSpace: 'nowrap',
    backgroundColor: C.panel,
  }}>
    {children}
  </TableCell>
);

const TD = ({ children, mono, muted, warn }: {
  children: React.ReactNode;
  mono?: boolean;
  muted?: boolean;
  warn?: boolean;
}) => (
  <TableCell sx={{
    fontFamily: mono ? 'monospace' : 'inherit',
    fontSize: '0.78rem',
    color: warn ? C.yellow : muted ? C.textMuted : C.textSub,
    borderBottom: `1px solid ${C.border}`,
    py: 0.75, px: 1.5,
  }}>
    {children}
  </TableCell>
);

function EmptyRow({ cols, message }: { cols: number; message: string }) {
  return (
    <TableRow>
      <TableCell colSpan={cols} sx={{ textAlign: 'center', py: 4, color: C.textDim, fontFamily: 'monospace', fontSize: '0.75rem', borderBottom: 'none' }}>
        {message}
      </TableCell>
    </TableRow>
  );
}

function LoadingRow({ cols }: { cols: number }) {
  return (
    <TableRow>
      <TableCell colSpan={cols} sx={{ textAlign: 'center', py: 4, borderBottom: 'none' }}>
        <CircularProgress size={18} sx={{ color: C.textDim }} />
      </TableCell>
    </TableRow>
  );
}

// ── tab panels ────────────────────────────────────────────────────────────

function EquipmentTab() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['equipment'],
    queryFn: equipmentAPI.getAllAssets,
    staleTime: 30000,
  });

  const pmOverdue = (asset: any) => {
    const d = asset.next_pm_due ? parseISO(asset.next_pm_due) : null;
    return d && d <= new Date();
  };

  return (
    <TableContainer>
      <Table size="small" sx={{ tableLayout: 'fixed' }}>
        <TableHead>
          <TableRow>
            <TH>Asset ID</TH>
            <TH>Type</TH>
            <TH>Status</TH>
            <TH>Zone</TH>
            <TH>Assignee</TH>
            <TH>Next PM</TH>
            <TH>Freshness</TH>
          </TableRow>
        </TableHead>
        <TableBody>
          {isLoading && <LoadingRow cols={7} />}
          {error && <EmptyRow cols={7} message="Failed to load equipment" />}
          {!isLoading && !error && !data?.length && <EmptyRow cols={7} message="No equipment assets found" />}
          {data?.map((asset) => {
            const overdue = pmOverdue(asset);
            const pmDue = asset.next_pm_due ? parseISO(asset.next_pm_due) : null;
            return (
              <TableRow
                key={asset.asset_id}
                sx={{
                  '&:hover': { backgroundColor: 'rgba(255,255,255,0.025)' },
                  borderLeft: overdue ? `2px solid ${C.yellow}` : `2px solid transparent`,
                }}
              >
                <TD mono>{asset.asset_id}</TD>
                <TD muted>{asset.type}</TD>
                <TD><StatusBadge status={asset.status} /></TD>
                <TD muted>{asset.zone ?? '—'}</TD>
                <TD muted>{asset.owner_user ?? '—'}</TD>
                <TD mono warn={!!overdue}>{pmDue ? format(pmDue, 'MM/dd HH:mm') : '—'}</TD>
                <TD><FreshnessTag updatedAt={asset.updated_at} /></TD>
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

  return (
    <TableContainer>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TH>ID</TH>
            <TH>Type</TH>
            <TH>Status</TH>
            <TH>Assignee</TH>
            <TH>Created</TH>
            <TH>Freshness</TH>
          </TableRow>
        </TableHead>
        <TableBody>
          {isLoading && <LoadingRow cols={6} />}
          {error && <EmptyRow cols={6} message="Failed to load tasks" />}
          {!isLoading && !error && !data?.length && <EmptyRow cols={6} message="No tasks found" />}
          {data?.map((task) => (
            <TableRow key={task.id} sx={{ '&:hover': { backgroundColor: 'rgba(255,255,255,0.025)' } }}>
              <TD mono>{task.id}</TD>
              <TD muted>{task.kind}</TD>
              <TD><StatusBadge status={task.status} /></TD>
              <TD muted>{task.assignee || '—'}</TD>
              <TD mono muted>{task.created_at ? format(parseISO(task.created_at), 'MM/dd HH:mm') : '—'}</TD>
              <TD><FreshnessTag updatedAt={task.updated_at} /></TD>
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

  if (isLoading) return (
    <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
      <CircularProgress size={18} sx={{ color: C.textDim }} />
    </Box>
  );
  if (error) return (
    <Box sx={{ p: 2 }}>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.75rem', color: C.red }}>Failed to load workforce</Typography>
    </Box>
  );
  if (!data) return (
    <Box sx={{ p: 2 }}>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.75rem', color: C.textDim }}>No workforce data</Typography>
    </Box>
  );

  const metrics = [
    { label: 'Total', value: data.total_workers ?? data.total },
    { label: 'Active', value: data.active_workers ?? data.active },
    { label: 'Available', value: data.available_workers ?? data.available },
    { label: 'Shift', value: data.shift },
  ];

  return (
    <Box sx={{ p: 2 }}>
      <Box sx={{ display: 'flex', gap: 2, mb: 3, flexWrap: 'wrap' }}>
        {metrics.map(({ label, value }) => (
          <Box key={label} sx={{
            px: 2, py: 1.5, minWidth: 100,
            backgroundColor: C.panel,
            border: `1px solid ${C.border}`,
            borderRadius: '4px',
          }}>
            <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '1.4rem', color: C.text, lineHeight: 1.2 }}>
              {value ?? '—'}
            </Typography>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: C.textDim, textTransform: 'uppercase', letterSpacing: '0.1em', mt: 0.25 }}>
              {label}
            </Typography>
          </Box>
        ))}
      </Box>

      {data.zone_allocations && (
        <>
          <SectionLabel>Zone Allocations</SectionLabel>
          <Box sx={{ mt: 1, p: 1.5, backgroundColor: C.panel, border: `1px solid ${C.border}`, borderRadius: '4px' }}>
            <pre style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: C.textMuted, margin: 0, whiteSpace: 'pre-wrap' }}>
              {JSON.stringify(data.zone_allocations, null, 2)}
            </pre>
          </Box>
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

  return (
    <TableContainer>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TH>ID</TH>
            <TH>Severity</TH>
            <TH>Description</TH>
            <TH>Reported By</TH>
            <TH>Occurred At</TH>
          </TableRow>
        </TableHead>
        <TableBody>
          {isLoading && <LoadingRow cols={5} />}
          {error && <EmptyRow cols={5} message="Failed to load incidents" />}
          {!isLoading && !error && !data?.length && (
            <TableRow>
              <TableCell colSpan={5} sx={{ textAlign: 'center', py: 4, borderBottom: 'none' }}>
                <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.75 }}>
                  <Box component="span" sx={{ color: C.green, fontSize: '0.8rem' }}>✓</Box>
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.75rem', color: C.textMuted }}>No safety incidents on record</Typography>
                </Box>
              </TableCell>
            </TableRow>
          )}
          {data?.map((incident) => (
            <TableRow key={incident.id} sx={{ '&:hover': { backgroundColor: 'rgba(255,255,255,0.025)' } }}>
              <TD mono>{incident.id}</TD>
              <TD><StatusBadge status={incident.severity} /></TD>
              <TD muted>{incident.description}</TD>
              <TD muted>{incident.reported_by}</TD>
              <TD mono muted>{incident.occurred_at ? format(parseISO(incident.occurred_at), 'MM/dd HH:mm') : '—'}</TD>
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

  return (
    <TableContainer>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TH>Domain</TH>
            <TH>Rule</TH>
            <TH>Status</TH>
          </TableRow>
        </TableHead>
        <TableBody>
          {isLoading && <LoadingRow cols={3} />}
          {error && <EmptyRow cols={3} message="Failed to load policies" />}
          {!isLoading && !error && !data?.length && <EmptyRow cols={3} message="No safety policies found" />}
          {data?.map((policy: any, i: number) => (
            <TableRow key={i} sx={{ '&:hover': { backgroundColor: 'rgba(255,255,255,0.025)' } }}>
              <TD mono muted>{policy.domain}</TD>
              <TD>{policy.rule}</TD>
              <TD><StatusBadge status={policy.active ? 'active' : 'inactive'} /></TD>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

// ── page ──────────────────────────────────────────────────────────────────

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
    <Box sx={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
      backgroundColor: C.bg,
    }}>
      {/* Page header */}
      <Box sx={{
        px: 2.5, py: 1.5,
        borderBottom: `1px solid ${C.border}`,
        flexShrink: 0,
        display: 'flex',
        alignItems: 'baseline',
        gap: 2,
      }}>
        <Typography sx={{
          fontFamily: 'monospace', fontWeight: 700, fontSize: '0.72rem',
          color: C.text, letterSpacing: '0.06em', textTransform: 'uppercase',
        }}>
          Warehouse State
        </Typography>
        <Typography sx={{
          fontFamily: 'monospace', fontSize: '0.65rem', color: C.textDim,
        }}>
          live operational state across all domains · amber = stale (&gt;{STALE_THRESHOLD_MINUTES}min)
        </Typography>
      </Box>

      {/* Domain tabs */}
      <Box sx={{
        display: 'flex',
        alignItems: 'stretch',
        borderBottom: `1px solid ${C.border}`,
        flexShrink: 0,
        px: 1,
        backgroundColor: C.panel,
      }}>
        {TABS.map(({ label }, i) => {
          const active = tab === i;
          return (
            <Box
              key={label}
              onClick={() => setTab(i)}
              sx={{
                px: 2, py: 1,
                cursor: 'pointer',
                position: 'relative',
                fontFamily: 'monospace',
                fontSize: '0.68rem',
                fontWeight: active ? 700 : 500,
                letterSpacing: '0.07em',
                textTransform: 'uppercase',
                color: active ? C.text : C.textDim,
                transition: 'color 0.15s',
                '&:hover': { color: active ? C.text : C.textMuted },
                '&::after': active ? {
                  content: '""',
                  position: 'absolute',
                  bottom: 0, left: 0, right: 0,
                  height: '2px',
                  backgroundColor: C.nvidia,
                } : {},
              }}
            >
              {label}
            </Box>
          );
        })}
      </Box>

      {/* Content */}
      <Box sx={{ flex: 1, overflow: 'auto' }}>
        <Component />
      </Box>
    </Box>
  );
};

export default WarehouseStatePage;
