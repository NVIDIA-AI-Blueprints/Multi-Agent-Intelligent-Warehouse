import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Box, Typography, Grid } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRuntimeStatus } from '../hooks/useRuntimeStatus';
import { useDemoStatus } from '../hooks/useDemoStatus';
import { equipmentAPI, operationsAPI, safetyAPI, mcpAPI } from '../services/api';
import DemoControlBar from '../components/demo/DemoControlBar';
import DecisionLifecycle from '../components/demo/DecisionLifecycle';
import { format } from 'date-fns';

// ── shared primitives ──────────────────────────────────────────────────────

const WAREHOUSE_ID = process.env.REACT_APP_WAREHOUSE_ID || 'DC-47';

function Dot({ color, glow }: { color: string; glow?: boolean }) {
  return (
    <Box sx={{
      width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
      backgroundColor: color,
      boxShadow: glow ? `0 0 5px ${color}` : 'none',
    }} />
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <Typography sx={{
      fontFamily: 'monospace', fontWeight: 700, fontSize: '0.6rem',
      color: '#484F58', letterSpacing: '0.12em', textTransform: 'uppercase',
      mb: 0.75,
    }}>
      {children}
    </Typography>
  );
}

function DomainRow({ label, ok, port }: { label: string; ok: boolean | undefined; port?: string }) {
  const c = ok === undefined ? '#30363D' : ok ? '#3FB950' : '#484F58';
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, py: 0.35 }}>
      <Dot color={c} glow={ok === true} />
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.72rem', color: ok ? '#C9D1D9' : '#484F58', flexGrow: 1 }}>
        {label}
      </Typography>
      {port && <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#30363D' }}>:{port}</Typography>}
    </Box>
  );
}

function KpiRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', py: 0.4, borderBottom: '1px solid #1C2128' }}>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.72rem', color: '#6E7681' }}>{label}</Typography>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.82rem', fontWeight: 700, color: color ?? '#C9D1D9' }}>{value}</Typography>
    </Box>
  );
}

function RiskRow({ icon, text, color }: { icon: string; text: string; color: string }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 0.35 }}>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.75rem', color }}>{icon}</Typography>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.72rem', color: '#8B949E' }}>{text}</Typography>
    </Box>
  );
}

const DECISION_STORAGE = 'maiw_decision_history';

interface DecisionRecord {
  id: string;
  action: string;
  request: Record<string, any>;
  result: any;
  timestamp: string;
}

function getDecisionStatus(r: DecisionRecord) {
  const s = r.result?.decision?.status ?? r.result?.decision_result?.status ?? r.result?.status;
  if (s) return s as string;
  if (r.result?.success === true) return 'approved';
  if (r.result?.success === false) return 'rejected';
  if (r.result?.error) return 'error';
  return 'unknown';
}

const STATUS_LABEL: Record<string, string> = {
  approved: 'EXECUTED',
  rejected: 'REJECTED',
  requires_human_approval: 'APPROVAL',
  requires_fresh_state: 'BLOCKED',
  error: 'ERROR',
  unknown: '—',
};
const STATUS_COLOR: Record<string, string> = {
  approved: '#3FB950',
  rejected: '#F85149',
  requires_human_approval: '#D29922',
  requires_fresh_state: '#58A6FF',
  error: '#F85149',
  unknown: '#484F58',
};
const STATUS_DOT: Record<string, string> = {
  approved: '✓',
  rejected: '✕',
  requires_human_approval: '●',
  requires_fresh_state: '◌',
  error: '✕',
  unknown: '—',
};

// ── activity log (session) ─────────────────────────────────────────────────

const ACTIVITY_KEY = 'maiw_activity_feed';

interface LogEntry {
  id: string;
  ts: string;
  category: 'STATE' | 'AGENT' | 'MODEL' | 'SKILL' | 'PROPOSE' | 'DECIDE' | 'EXECUTE' | 'MCP' | 'API';
  message: string;
  detail?: string;
}

const CAT_COLOR: Record<string, string> = {
  STATE: '#58A6FF',
  AGENT: '#76B900',
  MODEL: '#58A6FF',
  SKILL: '#76B900',
  PROPOSE: '#D29922',
  DECIDE: '#D29922',
  EXECUTE: '#3FB950',
  MCP: '#8B949E',
  API: '#484F58',
};

function readActivity(): LogEntry[] {
  try {
    const raw = sessionStorage.getItem(ACTIVITY_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch { return []; }
}

// ── main component ─────────────────────────────────────────────────────────

const CommandCenter: React.FC = () => {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: runtime } = useRuntimeStatus();
  const { isDemoMode, status: demoStatus } = useDemoStatus();
  const [decisions, setDecisions] = useState<DecisionRecord[]>([]);
  const [activity, setActivity] = useState<LogEntry[]>([]);
  const activityRef = useRef<HTMLDivElement>(null);

  const handleDemoStatusChange = useCallback(() => {
    qc.invalidateQueries({ queryKey: ['equipment'] });
    qc.invalidateQueries({ queryKey: ['tasks'] });
    qc.invalidateQueries({ queryKey: ['workforce'] });
  }, [qc]);

  const { data: equipment } = useQuery({ queryKey: ['equipment'], queryFn: equipmentAPI.getAllAssets, retry: 1, staleTime: 30000 });
  const { data: tasks } = useQuery({ queryKey: ['tasks'], queryFn: operationsAPI.getTasks, retry: 1, staleTime: 30000 });
  const { data: workforce } = useQuery({ queryKey: ['workforce'], queryFn: operationsAPI.getWorkforceStatus, retry: 1, staleTime: 30000 });
  const { data: incidents } = useQuery({ queryKey: ['incidents'], queryFn: safetyAPI.getIncidents, retry: 1, staleTime: 30000 });
  const { data: mcpStatus } = useQuery({ queryKey: ['mcp-status'], queryFn: mcpAPI.getStatus, retry: 1, staleTime: 30000 });

  // Refresh session data every 3s
  useEffect(() => {
    const tick = () => {
      try { setDecisions(JSON.parse(sessionStorage.getItem(DECISION_STORAGE) ?? '[]')); } catch {}
      setActivity(readActivity().slice(0, 40));
    };
    tick();
    const id = setInterval(tick, 3000);
    return () => clearInterval(id);
  }, []);

  // scroll activity to bottom on new entries
  useEffect(() => {
    if (activityRef.current) {
      activityRef.current.scrollTop = activityRef.current.scrollHeight;
    }
  }, [activity]);

  // ── derived metrics ──────────────────────────────────────────────────────

  const totalAssets = equipment?.length ?? 0;
  const activeAssets = equipment?.filter(a => a.status === 'active' || a.status === 'operational').length ?? 0;
  const maintenanceAssets = equipment?.filter(a => a.status === 'maintenance' || (a.next_pm_due && new Date(a.next_pm_due) <= new Date())).length ?? 0;
  const equipPct = totalAssets ? Math.round((activeAssets / totalAssets) * 100) : 0;

  const totalWorkers = workforce?.total_workers ?? workforce?.total ?? 0;
  const activeWorkers = workforce?.active_workers ?? workforce?.active ?? 0;
  const laborPct = totalWorkers ? Math.round((activeWorkers / totalWorkers) * 100) : 0;

  const pendingTasks = tasks?.filter(t => t.status === 'pending').length ?? 0;
  const openIncidents = incidents?.length ?? 0;

  // Decision counts
  const decisionCounts = decisions.reduce<Record<string, number>>((acc, r) => {
    const s = getDecisionStatus(r);
    acc[s] = (acc[s] ?? 0) + 1;
    return acc;
  }, {});
  const pendingApprovals = decisionCounts['requires_human_approval'] ?? 0;
  const blockedCount = decisionCounts['requires_fresh_state'] ?? 0;
  const approvedCount = decisionCounts['approved'] ?? 0;

  const mostRecentPending = decisions.find(r => getDecisionStatus(r) === 'requires_human_approval');

  // Operational risks (derived, no fabrication)
  const risks: { icon: string; text: string; color: string }[] = [];
  if (maintenanceAssets > 0) risks.push({ icon: '⚠', text: `${maintenanceAssets} equipment item${maintenanceAssets > 1 ? 's' : ''} need maintenance`, color: '#D29922' });
  if (pendingTasks > 3) risks.push({ icon: '⚠', text: `${pendingTasks} tasks pending — operations backlog`, color: '#D29922' });
  if (openIncidents > 0) risks.push({ icon: '⚠', text: `${openIncidents} open safety incident${openIncidents > 1 ? 's' : ''}`, color: '#F85149' });
  if (pendingApprovals > 0) risks.push({ icon: '⚠', text: `${pendingApprovals} action${pendingApprovals > 1 ? 's' : ''} awaiting human approval`, color: '#D29922' });
  if (laborPct > 0 && laborPct < 70) risks.push({ icon: '⚠', text: `Labor utilization low (${laborPct}%)`, color: '#D29922' });
  if (equipPct > 0 && equipPct >= 90) risks.push({ icon: '✓', text: `Equipment capacity healthy (${equipPct}%)`, color: '#3FB950' });
  if (risks.length === 0 && totalAssets > 0) risks.push({ icon: '✓', text: 'No active operational risks detected', color: '#3FB950' });

  // ── panels ───────────────────────────────────────────────────────────────

  const panelSx = {
    backgroundColor: '#0D1117',
    border: '1px solid #1C2128',
    borderRadius: 1,
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column' as const,
  };

  const panelHeaderSx = {
    px: 1.5,
    py: 0.75,
    borderBottom: '1px solid #1C2128',
    backgroundColor: '#080C10',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexShrink: 0,
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', p: 1.5, gap: 1.5 }}>

      {/* ── SYNTHETIC DEMO CONTROL BAR (only in demo mode) ── */}
      {isDemoMode && (
        <DemoControlBar status={demoStatus} onStatusChange={handleDemoStatusChange} />
      )}

      {/* Main 3-column area */}
      <Box sx={{ display: 'flex', gap: 1.5, flex: 1, overflow: 'hidden', minHeight: 0 }}>

        {/* ── LEFT COLUMN ── */}
        <Box sx={{ flex: '0 0 22%', minWidth: 200, maxWidth: 280, display: 'flex', flexDirection: 'column', gap: 1.5, overflow: 'auto' }}>

          {/* Row 1: Warehouse + MCP side by side */}
          <Box sx={{ display: 'flex', gap: 1.5 }}>
            <Box sx={{ ...panelSx, flex: 1 }}>
              <Box sx={panelHeaderSx}>
                <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.6rem', color: '#8B949E', letterSpacing: '0.1em' }}>
                  WAREHOUSE
                </Typography>
              </Box>
              <Box sx={{ p: 1 }}>
                <DomainRow label="Inventory" ok={runtime?.inventory_mcp_configured !== false} />
                <DomainRow label="Equipment" ok={!!equipment?.length} />
                <DomainRow label="Labor" ok={!!workforce} />
                <DomainRow label="Waves" ok={!!tasks?.length} />
              </Box>
            </Box>
            <Box sx={{ ...panelSx, flex: 1 }}>
              <Box sx={panelHeaderSx}>
                <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.6rem', color: '#8B949E', letterSpacing: '0.1em' }}>
                  MCP
                </Typography>
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: mcpStatus?.client_ready ? '#3FB950' : '#484F58' }}>
                  {mcpStatus?.client_ready ? '●' : '○'}
                </Typography>
              </Box>
              <Box sx={{ p: 1 }}>
                <DomainRow label="Inventory" ok={runtime?.inventory_mcp_configured} port="8765" />
                <DomainRow label="Equipment" ok={runtime?.equipment_mcp_configured} port="8766" />
                <DomainRow label="Labor" ok={runtime?.labor_mcp_configured} port="8767" />
                <DomainRow label="Wave" ok={runtime?.wave_mcp_configured} port="8768" />
              </Box>
            </Box>
          </Box>

          {/* Row 2: Model Gateway + Agents side by side */}
          <Box sx={{ display: 'flex', gap: 1.5 }}>
            <Box sx={{ ...panelSx, flex: 1 }}>
              <Box sx={panelHeaderSx}>
                <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.6rem', color: '#8B949E', letterSpacing: '0.1em' }}>
                  MODELS
                </Typography>
              </Box>
              <Box sx={{ p: 1 }}>
                <DomainRow label="Lightning" ok={runtime?.model_gateway_available} />
                <DomainRow label="Nano" ok={runtime?.model_gateway_available} />
                <DomainRow label="Super" ok={runtime?.model_gateway_available} />
                <DomainRow label="Ultra" ok={runtime?.model_gateway_available} />
                <Box sx={{ mt: 0.5, pt: 0.5, borderTop: '1px solid #1C2128' }}>
                  <DomainRow label="Decision" ok={runtime?.decision_engine_available} />
                  <DomainRow label="State" ok={runtime?.state_provider_available} />
                </Box>
              </Box>
            </Box>
            <Box sx={{ ...panelSx, flex: 1 }}>
              <Box sx={panelHeaderSx}>
                <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.6rem', color: '#8B949E', letterSpacing: '0.1em' }}>
                  AGENTS
                </Typography>
              </Box>
              <Box sx={{ p: 1 }}>
                <DomainRow label="Equipment" ok={runtime?.equipment_agent_available} />
                <DomainRow label="Operations" ok={runtime?.operations_agent_available} />
                <DomainRow label="Safety" ok={runtime?.safety_agent_available} />
              </Box>
            </Box>
          </Box>
        </Box>

        {/* ── CENTER COLUMN ── */}
        <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 1.5, overflow: 'auto', minWidth: 0 }}>

          {/* Location header */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexShrink: 0 }}>
            <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.85rem', color: '#E6EDF3', letterSpacing: '0.04em' }}>
              {WAREHOUSE_ID} — LIVE OPERATIONAL STATE
            </Typography>
            <Box sx={{ flexGrow: 1, height: '1px', backgroundColor: '#1C2128' }} />
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.63rem', color: '#484F58' }}>
              {format(new Date(), 'HH:mm:ss')}
            </Typography>
          </Box>

          {/* KPI metrics */}
          <Box sx={{ ...panelSx, flexShrink: 0 }}>
            <Box sx={panelHeaderSx}>
              <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.65rem', color: '#8B949E', letterSpacing: '0.1em' }}>
                OPERATIONAL METRICS
              </Typography>
            </Box>
            <Box sx={{ p: 1.5 }}>
              <Grid container spacing={1.5}>
                <Grid item xs={6} sm={3}>
                  <KpiRow label="Equipment" value={totalAssets ? `${equipPct}%` : '—'} color={equipPct >= 90 ? '#3FB950' : equipPct >= 70 ? '#D29922' : '#F85149'} />
                </Grid>
                <Grid item xs={6} sm={3}>
                  <KpiRow label="Labor" value={laborPct ? `${laborPct}%` : '—'} color={laborPct >= 80 ? '#3FB950' : laborPct >= 60 ? '#D29922' : '#F85149'} />
                </Grid>
                <Grid item xs={6} sm={3}>
                  <KpiRow label="Pending Tasks" value={pendingTasks.toString()} color={pendingTasks > 5 ? '#D29922' : '#3FB950'} />
                </Grid>
                <Grid item xs={6} sm={3}>
                  <KpiRow label="Open Incidents" value={openIncidents.toString()} color={openIncidents > 0 ? '#F85149' : '#3FB950'} />
                </Grid>
              </Grid>
            </Box>
          </Box>

          {/* Operational Risks */}
          <Box sx={{ ...panelSx, flex: 1 }}>
            <Box sx={panelHeaderSx}>
              <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.65rem', color: '#8B949E', letterSpacing: '0.1em' }}>
                CURRENT OPERATIONAL RISKS
              </Typography>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: risks.some(r => r.icon === '⚠') ? '#D29922' : '#3FB950' }}>
                {risks.filter(r => r.icon === '⚠').length} ACTIVE
              </Typography>
            </Box>
            <Box sx={{ p: 1.5, flex: 1, overflow: 'auto' }}>
              {risks.length === 0 ? (
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.72rem', color: '#484F58' }}>
                  — loading state data —
                </Typography>
              ) : (
                risks.map((r, i) => <RiskRow key={i} {...r} />)
              )}
            </Box>
          </Box>

          {/* Asset summary */}
          {equipment && equipment.length > 0 && (
            <Box sx={{ ...panelSx, flexShrink: 0 }}>
              <Box sx={panelHeaderSx}>
                <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.65rem', color: '#8B949E', letterSpacing: '0.1em' }}>
                  EQUIPMENT SUMMARY
                </Typography>
                <Typography
                  onClick={() => navigate('/state')}
                  sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#58A6FF', cursor: 'pointer', '&:hover': { color: '#79C0FF' } }}
                >
                  VIEW ALL →
                </Typography>
              </Box>
              <Box sx={{ p: 1.25 }}>
                {equipment.slice(0, 4).map(a => (
                  <Box key={a.asset_id} sx={{ display: 'flex', gap: 1.5, py: 0.3, borderBottom: '1px solid #0D1117' }}>
                    <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', color: '#484F58', width: 90, flexShrink: 0 }}>{a.asset_id}</Typography>
                    <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', color: '#6E7681', flexGrow: 1 }}>{a.type}</Typography>
                    <Typography sx={{
                      fontFamily: 'monospace', fontSize: '0.65rem', fontWeight: 700,
                      color: a.status === 'active' ? '#3FB950' : a.status === 'maintenance' ? '#D29922' : '#484F58',
                    }}>
                      {a.status.toUpperCase()}
                    </Typography>
                  </Box>
                ))}
                {equipment.length > 4 && (
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#30363D', mt: 0.5 }}>
                    + {equipment.length - 4} more
                  </Typography>
                )}
              </Box>
            </Box>
          )}
        </Box>

        {/* ── RIGHT COLUMN ── */}
        <Box sx={{ flex: '0 0 26%', minWidth: 220, maxWidth: 320, display: 'flex', flexDirection: 'column', gap: 1.5, overflow: 'auto' }}>
          <Box sx={panelSx}>
            <Box sx={panelHeaderSx}>
              <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.65rem', color: '#8B949E', letterSpacing: '0.1em' }}>
                DECISION CENTER
              </Typography>
              <Typography
                onClick={() => navigate('/decisions')}
                sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#58A6FF', cursor: 'pointer', '&:hover': { color: '#79C0FF' } }}
              >
                OPEN →
              </Typography>
            </Box>
            <Box sx={{ p: 1.25 }}>
              {/* Status counts */}
              {[
                { key: 'approved', label: 'APPROVED' },
                { key: 'requires_human_approval', label: 'PENDING' },
                { key: 'requires_fresh_state', label: 'BLOCKED' },
                { key: 'rejected', label: 'REJECTED' },
              ].map(({ key, label }) => {
                const count = decisionCounts[key] ?? 0;
                return (
                  <Box key={key} sx={{ display: 'flex', alignItems: 'center', gap: 0.75, py: 0.35 }}>
                    <Dot color={STATUS_COLOR[key]} glow={count > 0 && key !== 'rejected'} />
                    <Typography sx={{ fontFamily: 'monospace', fontSize: '0.72rem', color: count > 0 ? STATUS_COLOR[key] : '#30363D', flexGrow: 1, fontWeight: count > 0 ? 700 : 400 }}>
                      {label}
                    </Typography>
                    <Typography sx={{ fontFamily: 'monospace', fontSize: '0.72rem', color: count > 0 ? STATUS_COLOR[key] : '#30363D', fontWeight: 700 }}>
                      {count}
                    </Typography>
                  </Box>
                );
              })}

              {/* Most recent pending */}
              {mostRecentPending && (
                <>
                  <Box sx={{ mt: 1.25, pt: 1.25, borderTop: '1px solid #1C2128' }}>
                    <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58', mb: 0.5 }}>LATEST PENDING</Typography>
                    <Typography sx={{ fontFamily: 'monospace', fontSize: '0.75rem', color: '#C9D1D9', fontWeight: 700 }}>
                      {mostRecentPending.action.toUpperCase()}
                    </Typography>
                    <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', color: '#6E7681', mt: 0.25 }}>
                      {mostRecentPending.request.asset_id ?? '—'}
                    </Typography>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.75 }}>
                      <Dot color="#D29922" glow />
                      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', color: '#D29922', fontWeight: 700 }}>
                        Requires Human Approval
                      </Typography>
                    </Box>
                  </Box>
                  <Box
                    onClick={() => navigate('/decisions')}
                    sx={{
                      mt: 1, py: 0.75, textAlign: 'center',
                      border: '1px solid #30363D', borderRadius: 1, cursor: 'pointer',
                      '&:hover': { borderColor: '#58A6FF', backgroundColor: 'rgba(88,166,255,0.04)' },
                    }}
                  >
                    <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', color: '#58A6FF', fontWeight: 700, letterSpacing: '0.06em' }}>
                      [VIEW DECISION]
                    </Typography>
                  </Box>
                </>
              )}

              {decisions.length === 0 && (
                <Box sx={{ mt: 1.25, pt: 1.25, borderTop: '1px solid #1C2128' }}>
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', color: '#30363D' }}>
                    No decisions this session.
                    <br />Use Decisions view to trigger equipment actions.
                  </Typography>
                </Box>
              )}
            </Box>
          </Box>

          {/* Decision lifecycle pipeline (demo mode highlight) */}
          <DecisionLifecycle />

          {/* Recent decisions mini-queue */}
          {decisions.length > 0 && (
            <Box sx={panelSx}>
              <Box sx={panelHeaderSx}>
                <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.65rem', color: '#8B949E', letterSpacing: '0.1em' }}>
                  RECENT ACTIONS
                </Typography>
              </Box>
              <Box sx={{ p: 1.25 }}>
                {decisions.slice(0, 5).map((r) => {
                  const s = getDecisionStatus(r);
                  return (
                    <Box key={r.id} sx={{ py: 0.4, borderBottom: '1px solid #0D1117', display: 'flex', gap: 0.75, alignItems: 'center' }}>
                      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.7rem', color: STATUS_COLOR[s] ?? '#484F58', width: 14, flexShrink: 0 }}>
                        {STATUS_DOT[s] ?? '—'}
                      </Typography>
                      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', color: '#6E7681', flexGrow: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {r.action} {r.request.asset_id ?? ''}
                      </Typography>
                      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: STATUS_COLOR[s] ?? '#484F58', flexShrink: 0, fontWeight: 700 }}>
                        {STATUS_LABEL[s] ?? '—'}
                      </Typography>
                    </Box>
                  );
                })}
              </Box>
            </Box>
          )}
        </Box>
      </Box>

      {/* ── LIVE ACTIVITY ── */}
      <Box sx={{ ...panelSx, flexShrink: 0, height: 148 }}>
        <Box sx={{ ...panelHeaderSx }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
            <Box sx={{ width: 5, height: 5, borderRadius: '50%', backgroundColor: '#F85149', animation: 'livePulse 1.5s ease-in-out infinite', '@keyframes livePulse': { '0%,100%': { opacity: 1 }, '50%': { opacity: 0.3 } } }} />
            <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.65rem', color: '#8B949E', letterSpacing: '0.1em' }}>
              LIVE ACTIVITY
            </Typography>
          </Box>
          <Typography
            onClick={() => navigate('/activity')}
            sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#484F58', cursor: 'pointer', '&:hover': { color: '#8B949E' } }}
          >
            FULL LOG →
          </Typography>
        </Box>
        <Box
          ref={activityRef}
          sx={{
            flex: 1,
            overflow: 'auto',
            px: 1.5,
            py: 0.75,
            fontFamily: 'monospace',
            fontSize: '0.7rem',
            '&::-webkit-scrollbar': { width: 3 },
            '&::-webkit-scrollbar-track': { background: 'transparent' },
            '&::-webkit-scrollbar-thumb': { background: '#21262D' },
          }}
        >
          {activity.length === 0 ? (
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.7rem', color: '#30363D' }}>
              — session activity will appear here —
            </Typography>
          ) : (
            activity.slice(-12).map((e) => (
              <Box key={e.id} sx={{ display: 'flex', gap: 1.5, lineHeight: 1.8 }}>
                <Typography component="span" sx={{ fontFamily: 'monospace', fontSize: '0.67rem', color: '#30363D', flexShrink: 0 }}>
                  {format(new Date(e.ts), 'HH:mm:ss')}
                </Typography>
                <Typography component="span" sx={{ fontFamily: 'monospace', fontSize: '0.67rem', color: CAT_COLOR[e.category] ?? '#484F58', fontWeight: 700, width: 52, flexShrink: 0 }}>
                  {e.category}
                </Typography>
                <Typography component="span" sx={{ fontFamily: 'monospace', fontSize: '0.67rem', color: '#8B949E', flexGrow: 1 }}>
                  {e.message}
                </Typography>
                {e.detail && (
                  <Typography component="span" sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58', flexShrink: 0 }}>
                    {e.detail}
                  </Typography>
                )}
              </Box>
            ))
          )}
        </Box>
      </Box>
    </Box>
  );
};

export default CommandCenter;
