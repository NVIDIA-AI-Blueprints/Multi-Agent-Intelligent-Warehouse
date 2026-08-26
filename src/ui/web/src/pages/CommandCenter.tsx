import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Box, Typography, Grid, Button } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRuntimeStatus } from '../hooks/useRuntimeStatus';
import { useDemoStatus } from '../hooks/useDemoStatus';
import { equipmentAPI, operationsAPI, safetyAPI, mcpAPI } from '../services/api';
import DemoControlBar from '../components/demo/DemoControlBar';
import DecisionLifecycle from '../components/demo/DecisionLifecycle';
import MAIWPipeline from '../components/demo/MAIWPipeline';
import KPITrendChart from '../components/demo/KPITrendChart';
import CounterfactualPanel from '../components/demo/CounterfactualPanel';
import { AnalysisResult, demoAPI } from '../services/demoAPI';
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

function getModelRole(modelId: string): string {
  const lower = modelId.toLowerCase();
  if (lower.includes('super')) return 'Super';
  if (lower.includes('ultra')) return 'Ultra';
  if (lower.includes('nano')) return 'Nano';
  if (lower.includes('lightning')) return 'Lightning';
  return '';
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
  category: 'STATE' | 'AGENT' | 'MODEL' | 'SKILL' | 'PROPOSE' | 'DECIDE' | 'EXECUTE' | 'RECONCILE' | 'MCP' | 'API';
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
  RECONCILE: '#E3B341',
  MCP: '#8B949E',
  API: '#484F58',
};

// Maps SSE reconciliation event messages to operator-facing labels.
const RECONCILE_MSG_LABEL: Record<string, string> = {
  'reconciliation.started':               'CHECKING AUTHORITATIVE STATE',
  'reconciliation.confirmed_executed':    'MUTATION CONFIRMED',
  'reconciliation.confirmed_not_executed':'NO MUTATION CONFIRMED',
  'reconciliation.indeterminate':         'MANUAL REVIEW REQUIRED',
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
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [lifecycleMarkers, setLifecycleMarkers] = useState<Array<{sim_time_seconds: number; category: string; label: string;}>>([]);
  const [showCounterfactual, setShowCounterfactual] = useState(false);
  const activityRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem('maiw_analysis_result');
      if (raw) setAnalysisResult(JSON.parse(raw));
    } catch {}
  }, []);

  // Collect lifecycle markers when analysis result arrives
  useEffect(() => {
    if (!analysisResult) return;
    const simT = analysisResult.pre_kpis?.sim_time_seconds ?? 0;
    const markers: Array<{sim_time_seconds: number; category: string; label: string;}> = [
      { sim_time_seconds: simT, category: 'OBSERVE', label: 'OBSERVE' },
      { sim_time_seconds: simT, category: 'REASON', label: 'REASON' },
      { sim_time_seconds: simT, category: 'DECIDE', label: 'DECIDE' },
      { sim_time_seconds: simT, category: 'EXECUTE', label: 'EXECUTE' },
    ];
    setLifecycleMarkers(prev => {
      const hasSim = prev.some(m => m.sim_time_seconds === simT && m.category === 'OBSERVE');
      return hasSim ? prev : [...prev, ...markers];
    });
  }, [analysisResult]);

  // Clear lifecycle markers when scenario changes
  useEffect(() => {
    setLifecycleMarkers([]);
  }, [demoStatus?.scenario?.name]);

  const handleDemoStatusChange = useCallback(() => {
    qc.invalidateQueries({ queryKey: ['equipment'] });
    qc.invalidateQueries({ queryKey: ['tasks'] });
    qc.invalidateQueries({ queryKey: ['workforce'] });
  }, [qc]);

  const handleApprove = async (pending_id: string) => {
    try {
      await demoAPI.approvePending(pending_id);
      const s = await demoAPI.getStatus();
      // Status polling in useDemoStatus will pick this up, but force a quick refresh
      qc.invalidateQueries({ queryKey: ['demo-status'] });
    } catch (e) {
      console.error('Approve failed', e);
    }
  };

  const handleReject = async (pending_id: string) => {
    try {
      await demoAPI.rejectPending(pending_id);
      qc.invalidateQueries({ queryKey: ['demo-status'] });
    } catch (e) {
      console.error('Reject failed', e);
    }
  };

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
  const activeAssets = equipment?.filter(a => a.status === 'available' || a.status === 'assigned' || a.status === 'active' || a.status === 'operational').length ?? 0;
  const maintenanceAssets = equipment?.filter(a => a.status === 'maintenance' || a.status === 'offline' || (a.next_pm_due && new Date(a.next_pm_due) <= new Date())).length ?? 0;
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

  const activeModelRole = analysisResult ? getModelRole(analysisResult.assessment.model_id) : null;

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
        <DemoControlBar status={demoStatus} onStatusChange={handleDemoStatusChange} onAnalysisComplete={setAnalysisResult} />
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
                {(['Lightning', 'Nano', 'Super', 'Ultra'] as const).map((role) => {
                  const isDisabled = role === 'Ultra';
                  const isActive = activeModelRole === role;
                  return (
                    <Box key={role} sx={{ display: 'flex', alignItems: 'center', py: 0.35, gap: 0.75 }}>
                      <Dot color={isDisabled ? '#21262D' : '#3FB950'} glow={isActive} />
                      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.72rem', color: isActive ? '#76B900' : isDisabled ? '#30363D' : '#C9D1D9', flexGrow: 1 }}>
                        {role}
                      </Typography>
                      {isActive && <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#76B900' }}>ACTIVE</Typography>}
                      {!isActive && !isDisabled && <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58' }}>READY</Typography>}
                      {isDisabled && <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#30363D' }}>DISABLED</Typography>}
                    </Box>
                  );
                })}
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
                {(['Operations', 'Equipment', 'Safety'] as const).map((agent) => {
                  const isActive = agent === 'Operations' && !!analysisResult;
                  return (
                    <Box key={agent} sx={{ display: 'flex', alignItems: 'center', py: 0.35, gap: 0.75 }}>
                      <Dot color={isActive ? '#3FB950' : '#21262D'} glow={isActive} />
                      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.72rem', color: isActive ? '#C9D1D9' : '#484F58', flexGrow: 1 }}>
                        {agent}
                      </Typography>
                      {isActive && <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#76B900' }}>ACTIVE</Typography>}
                      {!isActive && <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#30363D' }}>IDLE</Typography>}
                    </Box>
                  );
                })}
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

          {isDemoMode ? (
            <>
              <MAIWPipeline result={analysisResult} />

              {/* KPI Trend chart */}
              {(demoStatus?.kpi_history?.length ?? 0) > 0 && (
                <Box sx={{ ...panelSx, flexShrink: 0 }}>
                  <Box sx={panelHeaderSx}>
                    <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.65rem', color: '#8B949E', letterSpacing: '0.1em' }}>
                      OPERATIONAL RISK TREND
                    </Typography>
                    <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58' }}>
                      {demoStatus?.world?.clock_iso
                        ? `t=${demoStatus.world.elapsed_seconds}s`
                        : ''}
                    </Typography>
                  </Box>
                  <Box sx={{ px: 1.25, pt: 1, pb: 0.75 }}>
                    <KPITrendChart
                      history={demoStatus?.kpi_history ?? []}
                      lifecycleEvents={lifecycleMarkers}
                      height={130}
                    />
                  </Box>
                </Box>
              )}

              {/* Recovery Status bar — shown whenever demo is active */}
              {demoStatus?.active && (
                <Box sx={{ ...panelSx, flexShrink: 0 }}>
                  <Box sx={panelHeaderSx}>
                    <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.65rem', color: '#8B949E', letterSpacing: '0.1em' }}>
                      RECOVERY STATUS
                    </Typography>
                  </Box>
                  <Box sx={{ px: 1.5, py: 1, display: 'flex', alignItems: 'center', gap: 0 }}>
                    {(() => {
                      const kpis = demoStatus?.current_kpis;
                      const waveRiskLevel = kpis?.wave_risk_level;
                      const riskColor = waveRiskLevel === 'critical' || waveRiskLevel === 'high' ? '#F85149'
                        : waveRiskLevel === 'medium' ? '#D29922'
                        : waveRiskLevel === 'low' ? '#58A6FF'
                        : '#3FB950';
                      const steps = [
                        { label: 'DISRUPTED',    active: true,                                          color: '#F85149' },
                        { label: 'MAIW ACTION',  active: !!analysisResult,                              color: '#3FB950' },
                        { label: `RISK: ${(waveRiskLevel ?? '—').toUpperCase()}`, active: true,          color: riskColor },
                        { label: 'RECOVERED',    active: kpis?.time_to_recovery_seconds != null,        color: '#3FB950' },
                      ];
                      return steps.map((step, i) => (
                        <React.Fragment key={step.label}>
                          <Box sx={{
                            flex: 1,
                            px: 0.75,
                            py: 0.5,
                            textAlign: 'center',
                            backgroundColor: step.active ? `${step.color}18` : '#080C10',
                            border: `1px solid ${step.active ? step.color : '#1C2128'}`,
                            borderRadius: 0.5,
                          }}>
                            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', fontWeight: 700, color: step.active ? step.color : '#30363D', letterSpacing: '0.06em' }}>
                              {step.label}
                            </Typography>
                          </Box>
                          {i < steps.length - 1 && (
                            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#30363D', mx: 0.25, flexShrink: 0 }}>→</Typography>
                          )}
                        </React.Fragment>
                      ));
                    })()}
                  </Box>
                </Box>
              )}

              {/* MAIW Intelligence metrics — only after analysis */}
              {analysisResult?.timing && (
                <Box sx={{ ...panelSx, flexShrink: 0 }}>
                  <Box sx={panelHeaderSx}>
                    <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.65rem', color: '#8B949E', letterSpacing: '0.1em' }}>
                      MAIW INTELLIGENCE METRICS
                    </Typography>
                  </Box>
                  <Box sx={{ p: 1.25, display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 1 }}>
                    {[
                      { label: 'TIME TO DETECT', value: analysisResult.timing.time_to_detect_ms != null ? `${(analysisResult.timing.time_to_detect_ms / 1000).toFixed(1)}s` : '—', color: '#58A6FF' },
                      { label: 'TIME TO DECISION', value: `${(analysisResult.timing.time_to_decision_ms / 1000).toFixed(2)}s`, color: '#76B900' },
                      { label: 'TIME TO EXECUTION', value: `${analysisResult.timing.time_to_execution_ms.toFixed(0)}ms`, color: '#D29922' },
                      {
                        label: 'SCENARIO TTR',
                        value: demoStatus?.current_kpis?.time_to_recovery_seconds != null
                          ? `${demoStatus.current_kpis.time_to_recovery_seconds}s`
                          : '—',
                        color: demoStatus?.current_kpis?.time_to_recovery_seconds != null ? '#3FB950' : '#484F58',
                      },
                    ].map(m => (
                      <Box key={m.label} sx={{ backgroundColor: '#080C10', borderRadius: 0.5, px: 1, py: 0.75 }}>
                        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58', letterSpacing: '0.08em', mb: 0.25 }}>
                          {m.label}
                        </Typography>
                        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.9rem', fontWeight: 700, color: m.color }}>
                          {m.value}
                        </Typography>
                      </Box>
                    ))}
                  </Box>
                </Box>
              )}

              {/* Compact KPI metrics */}
              <Box sx={{ ...panelSx, flexShrink: 0 }}>
                <Box sx={panelHeaderSx}>
                  <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.65rem', color: '#8B949E', letterSpacing: '0.1em' }}>
                    OPERATIONAL METRICS
                  </Typography>
                </Box>
                <Box sx={{ p: 1.25 }}>
                  <Grid container spacing={1}>
                    <Grid item xs={6} sm={3}>
                      <KpiRow
                        label="Equip Oper."
                        value={demoStatus?.current_kpis?.equipment_operational_pct != null ? `${demoStatus.current_kpis.equipment_operational_pct}%` : (totalAssets ? `${equipPct}%` : '—')}
                        color={(() => { const v = demoStatus?.current_kpis?.equipment_operational_pct ?? equipPct; return v >= 90 ? '#3FB950' : v >= 70 ? '#D29922' : '#F85149'; })()}
                      />
                    </Grid>
                    <Grid item xs={6} sm={3}>
                      <KpiRow
                        label="Labor Avail."
                        value={demoStatus?.current_kpis?.labor_availability_pct != null ? `${demoStatus.current_kpis.labor_availability_pct}%` : (laborPct ? `${laborPct}%` : '—')}
                        color={(() => { const v = demoStatus?.current_kpis?.labor_availability_pct ?? laborPct; return v >= 80 ? '#3FB950' : v >= 60 ? '#D29922' : '#F85149'; })()}
                      />
                    </Grid>
                    <Grid item xs={6} sm={3}>
                      <KpiRow
                        label="WAVE COMPLETION"
                        value={demoStatus?.current_kpis?.wave_completion_pct != null ? `${demoStatus.current_kpis.wave_completion_pct.toFixed(0)}%` : '—'}
                        color={(() => { const v = demoStatus?.current_kpis?.wave_completion_pct ?? 0; return v >= 75 ? '#3FB950' : v >= 25 ? '#D29922' : '#F85149'; })()}
                      />
                    </Grid>
                    <Grid item xs={6} sm={3}>
                      <KpiRow
                        label="Wave Risk"
                        value={demoStatus?.current_kpis?.wave_risk_level?.toUpperCase() ?? '—'}
                        color={(() => {
                          const lvl = demoStatus?.current_kpis?.wave_risk_level;
                          if (lvl === 'critical' || lvl === 'high') return '#F85149';
                          if (lvl === 'medium') return '#D29922';
                          return '#3FB950';
                        })()}
                      />
                    </Grid>
                  </Grid>
                  {/* Second row: throughput + service level */}
                  <Grid container spacing={1} sx={{ mt: 0 }}>
                    <Grid item xs={6} sm={6}>
                      <KpiRow
                        label="SIMULATED THROUGHPUT"
                        value={demoStatus?.current_kpis?.simulated_throughput != null ? `${demoStatus.current_kpis.simulated_throughput.toFixed(0)} units/hr` : '—'}
                      />
                    </Grid>
                    <Grid item xs={6} sm={6}>
                      <KpiRow
                        label="PROJ SERVICE LEVEL"
                        value={demoStatus?.current_kpis?.projected_service_level != null ? `${demoStatus.current_kpis.projected_service_level.toFixed(0)}%` : '—'}
                        color={(() => { const v = demoStatus?.current_kpis?.projected_service_level ?? 0; return v >= 90 ? '#3FB950' : v >= 70 ? '#D29922' : '#F85149'; })()}
                      />
                    </Grid>
                  </Grid>
                </Box>
              </Box>

              {/* Compact risks */}
              <Box sx={{ ...panelSx, flexShrink: 0, maxHeight: 90, overflow: 'auto' }}>
                <Box sx={panelHeaderSx}>
                  <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.65rem', color: '#8B949E', letterSpacing: '0.1em' }}>
                    CURRENT OPERATIONAL RISKS
                  </Typography>
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: risks.some(r => r.icon === '⚠') ? '#D29922' : '#3FB950' }}>
                    {risks.filter(r => r.icon === '⚠').length} ACTIVE
                  </Typography>
                </Box>
                <Box sx={{ p: 1 }}>
                  {risks.length === 0 ? (
                    <Typography sx={{ fontFamily: 'monospace', fontSize: '0.72rem', color: '#484F58' }}>
                      — loading state data —
                    </Typography>
                  ) : (
                    risks.slice(0, 3).map((r, i) => <RiskRow key={i} {...r} />)
                  )}
                </Box>
              </Box>

              {/* Counterfactual evaluation panel */}
              <Box sx={{ ...panelSx, flexShrink: 0 }}>
                <Box
                  sx={{ ...panelHeaderSx, cursor: 'pointer', userSelect: 'none', '&:hover': { backgroundColor: '#0D1117' } }}
                  onClick={() => setShowCounterfactual(v => !v)}
                >
                  <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.65rem', color: showCounterfactual ? '#76B900' : '#484F58', letterSpacing: '0.1em' }}>
                    COUNTERFACTUAL EVALUATION
                  </Typography>
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#484F58' }}>
                    {showCounterfactual ? '▲ COLLAPSE' : '▼ EXPAND'}
                  </Typography>
                </Box>
                {showCounterfactual && (
                  <Box sx={{ p: 1.5, overflow: 'auto' }}>
                    <CounterfactualPanel />
                  </Box>
                )}
              </Box>
            </>
          ) : (
            <>
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
            </>
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

              {/* Pending approvals from demo analysis */}
              {(demoStatus?.pending_approvals ?? []).length > 0 && (
                <Box sx={{ mt: 1, display: 'flex', flexDirection: 'column', gap: 0.75 }}>
                  {(demoStatus?.pending_approvals ?? []).map((pa) => (
                    <Box key={pa.pending_id} sx={{
                      border: '1px solid #D29922',
                      borderRadius: 1,
                      p: 1,
                      background: '#161B1F',
                    }}>
                      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', fontWeight: 700, color: '#D29922', letterSpacing: '0.08em' }}>
                        AWAITING APPROVAL
                      </Typography>
                      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#C9D1D9', mt: 0.25 }}>
                        {pa.capability}
                      </Typography>
                      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#6E7681', mt: 0.25 }}>
                        {pa.objective}
                      </Typography>
                      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#8B949E', mt: 0.25 }}>
                        Risk: {pa.risk_level?.toUpperCase()}  ·  {pa.domain}
                      </Typography>
                      <Box sx={{ display: 'flex', gap: 0.5, mt: 0.75 }}>
                        <Button
                          size="small"
                          variant="outlined"
                          onClick={() => handleApprove(pa.pending_id)}
                          sx={{
                            fontSize: '0.55rem', fontFamily: 'monospace', fontWeight: 700,
                            py: 0.25, px: 0.75, minWidth: 0, borderColor: '#3FB950', color: '#3FB950',
                            '&:hover': { borderColor: '#3FB950', background: '#3FB95018' },
                          }}
                        >
                          APPROVE
                        </Button>
                        <Button
                          size="small"
                          variant="outlined"
                          onClick={() => handleReject(pa.pending_id)}
                          sx={{
                            fontSize: '0.55rem', fontFamily: 'monospace', fontWeight: 700,
                            py: 0.25, px: 0.75, minWidth: 0, borderColor: '#F85149', color: '#F85149',
                            '&:hover': { borderColor: '#F85149', background: '#F8514918' },
                          }}
                        >
                          REJECT
                        </Button>
                      </Box>
                    </Box>
                  ))}
                </Box>
              )}

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
            activity.slice(-12).map((e) => {
              const reconcileLabel = e.category === 'RECONCILE' ? (RECONCILE_MSG_LABEL[e.message] ?? e.message) : null;
              return (
                <Box key={e.id} sx={{ display: 'flex', gap: 1.5, lineHeight: 1.8 }}>
                  <Typography component="span" sx={{ fontFamily: 'monospace', fontSize: '0.67rem', color: '#30363D', flexShrink: 0 }}>
                    {format(new Date(e.ts), 'HH:mm:ss')}
                  </Typography>
                  <Typography component="span" sx={{ fontFamily: 'monospace', fontSize: '0.67rem', color: CAT_COLOR[e.category] ?? '#484F58', fontWeight: 700, width: 52, flexShrink: 0 }}>
                    {e.category}
                  </Typography>
                  <Typography component="span" sx={{ fontFamily: 'monospace', fontSize: '0.67rem', color: reconcileLabel ? CAT_COLOR['RECONCILE'] : '#8B949E', flexGrow: 1, fontWeight: reconcileLabel ? 600 : 400 }}>
                    {reconcileLabel ?? e.message}
                  </Typography>
                  {e.detail && (
                    <Typography component="span" sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58', flexShrink: 0 }}>
                      {e.detail}
                    </Typography>
                  )}
                </Box>
              );
            })
          )}
        </Box>
      </Box>
    </Box>
  );
};

export default CommandCenter;
