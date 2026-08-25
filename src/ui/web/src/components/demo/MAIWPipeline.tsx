import React from 'react';
import { Box, Typography } from '@mui/material';
import { AnalysisResult, LifecycleRecord } from '../../services/demoAPI';

type StepStatus = 'ok' | 'warn' | 'error' | 'pending';

const STEP_STATUS_COLOR: Record<StepStatus, string> = {
  ok: '#3FB950',
  warn: '#D29922',
  error: '#F85149',
  pending: '#21262D',
};

const STEP_STATUS_ICON: Record<StepStatus, string> = {
  ok: '✓',
  warn: '●',
  error: '✕',
  pending: '○',
};

const SEVERITY_COLOR: Record<string, string> = {
  critical: '#F85149',
  high: '#D29922',
  medium: '#58A6FF',
  low: '#3FB950',
};

const PRIORITY_COLOR: Record<string, string> = {
  critical: '#F85149',
  high: '#D29922',
  medium: '#58A6FF',
  low: '#3FB950',
};

const PROPOSAL_STATUS_COLOR: Record<string, string> = {
  executed: '#3FB950',
  approved: '#3FB950',
  requires_human_approval: '#D29922',
  requires_fresh_state: '#58A6FF',
  rejected: '#F85149',
  error: '#F85149',
};

function getStepStatus(result: AnalysisResult, step: string): StepStatus {
  if (step === 'OBSERVE' || step === 'REASON') return 'ok';
  if (step === 'PROPOSE') {
    return result.lifecycle.some(l => l.phase === 'PROPOSE') ? 'ok' : 'pending';
  }
  if (step === 'DECIDE') {
    const statuses = result.proposal_results.map(p => p.status);
    if (statuses.some(s => s === 'requires_human_approval')) return 'warn';
    if (statuses.some(s => s === 'rejected')) return 'error';
    if (statuses.length > 0) return 'ok';
    return 'pending';
  }
  if (step === 'EXECUTE') {
    const statuses = result.proposal_results.map(p => p.status);
    if (statuses.some(s => s === 'requires_fresh_state')) return 'error';
    if (statuses.some(s => s === 'requires_human_approval')) return 'warn';
    if (statuses.some(s => s === 'error')) return 'error';
    if (statuses.length > 0 && statuses.every(s => s === 'executed' || s === 'approved')) return 'ok';
    return 'pending';
  }
  return 'pending';
}

function modelShortName(modelId: string): string {
  const lower = modelId.toLowerCase();
  if (lower.includes('super')) return 'Nemotron Super';
  if (lower.includes('ultra')) return 'Nemotron Ultra';
  if (lower.includes('nano')) return 'Nemotron Nano';
  if (lower.includes('lightning')) return 'Nemotron Lightning';
  const parts = modelId.split('/');
  return parts[parts.length - 1] ?? modelId;
}

function getSkillsConsulted(lifecycle: LifecycleRecord[]): string[] {
  return lifecycle
    .filter(l => l.phase === 'SKILL')
    .map(l => String(l.skill ?? l.capability ?? l.name ?? ''))
    .filter(Boolean)
    .filter((v, i, a) => a.indexOf(v) === i);
}

function getProposalRisk(lifecycle: LifecycleRecord[], proposalId: string | undefined, idx: number): string {
  if (proposalId) {
    const rec = lifecycle.find(l => l.phase === 'PROPOSE' && l.proposal_id === proposalId);
    if (rec) return String(rec.risk_level ?? rec.risk ?? 'medium');
  }
  const propRecs = lifecycle.filter(l => l.phase === 'PROPOSE');
  const rec = propRecs[idx];
  if (rec) return String(rec.risk_level ?? rec.risk ?? 'medium');
  return 'medium';
}

interface StepCardProps {
  num: string;
  label: string;
  status: StepStatus;
  sub1?: string;
  sub2?: string;
}

function StepCard({ num, label, status, sub1, sub2 }: StepCardProps) {
  const color = STEP_STATUS_COLOR[status];
  return (
    <Box sx={{
      flex: 1,
      backgroundColor: '#0D1117',
      border: '1px solid #1C2128',
      borderLeft: status !== 'pending' ? `2px solid ${color}` : '1px solid #1C2128',
      borderRadius: 0.5,
      px: 1,
      py: 0.75,
      display: 'flex',
      flexDirection: 'column',
      gap: 0.25,
      minWidth: 0,
    }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58', flexShrink: 0 }}>{num}</Typography>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', fontWeight: 700, color: '#C9D1D9', flexGrow: 1 }}>{label}</Typography>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.7rem', color, flexShrink: 0 }}>{STEP_STATUS_ICON[status]}</Typography>
      </Box>
      {sub1 && (
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#6E7681', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {sub1}
        </Typography>
      )}
      {sub2 && (
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {sub2}
        </Typography>
      )}
    </Box>
  );
}

interface Props {
  result: AnalysisResult | null;
}

const MAIWPipeline: React.FC<Props> = ({ result }) => {
  const panelSx = {
    backgroundColor: '#0D1117',
    border: '1px solid #1C2128',
    borderRadius: 1,
    overflow: 'hidden',
  };

  const headerSx = {
    px: 1.5,
    py: 0.75,
    borderBottom: '1px solid #1C2128',
    backgroundColor: '#080C10',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexShrink: 0,
  };

  if (!result) {
    return (
      <Box sx={{ ...panelSx, flex: 1, display: 'flex', flexDirection: 'column' }}>
        <Box sx={headerSx}>
          <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.65rem', color: '#8B949E', letterSpacing: '0.1em' }}>
            MAIW INTELLIGENCE PIPELINE
          </Typography>
        </Box>
        <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 0.75, py: 3 }}>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', color: '#30363D', letterSpacing: '0.08em' }}>
            ── MAIW INTELLIGENCE PIPELINE ──
          </Typography>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', color: '#484F58' }}>
            No analysis run this session.
          </Typography>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#30363D' }}>
            Use RUN MAIW to observe agent reasoning over the active scenario.
          </Typography>
        </Box>
      </Box>
    );
  }

  const a = result.assessment;
  const observeStatus = getStepStatus(result, 'OBSERVE');
  const reasonStatus = getStepStatus(result, 'REASON');
  const proposeStatus = getStepStatus(result, 'PROPOSE');
  const decideStatus = getStepStatus(result, 'DECIDE');
  const executeStatus = getStepStatus(result, 'EXECUTE');

  const proposeCount = result.lifecycle.filter(l => l.phase === 'PROPOSE').length;
  const actionCount = proposeCount > 0 ? proposeCount : result.proposal_results.length;
  const distinctDomains = Array.from(new Set(a.recommendations.map(r => r.domain)));

  const evaluatedCount = result.proposal_results.length;
  const approvedCount = result.proposal_results.filter(p => p.status === 'executed' || p.status === 'approved').length;

  const skillsConsulted = getSkillsConsulted(result.lifecycle);

  const hasBlocked = result.proposal_results.some(p => p.status === 'requires_fresh_state');
  const hasApprovalPending = result.proposal_results.some(p => p.status === 'requires_human_approval');

  const executeLabel =
    executeStatus === 'error' ? 'BLOCKED' :
    executeStatus === 'ok' ? 'COMPLETED' :
    executeStatus === 'warn' ? 'PENDING APPROVAL' : '—';

  return (
    <Box sx={{ ...panelSx, flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'auto' }}>
      <Box sx={headerSx}>
        <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.65rem', color: '#8B949E', letterSpacing: '0.1em' }}>
          MAIW INTELLIGENCE PIPELINE
        </Typography>
        <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'center' }}>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58' }}>
            trace:{result.trace_id.slice(0, 8)}
          </Typography>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58' }}>
            {a.latency_ms}ms
          </Typography>
        </Box>
      </Box>

      <Box sx={{ px: 1.5, py: 1, borderBottom: '1px solid #1C2128', display: 'flex', gap: 1 }}>
        <StepCard
          num="01"
          label="OBSERVE"
          status={observeStatus}
          sub1={`snap ${a.snapshot_id.slice(0, 8)}`}
          sub2={a.warehouse_id}
        />
        <StepCard
          num="02"
          label="REASON"
          status={reasonStatus}
          sub1={modelShortName(a.model_id)}
          sub2={`${a.latency_ms}ms`}
        />
        <StepCard
          num="03"
          label="PROPOSE"
          status={proposeStatus}
          sub1={`${actionCount} action${actionCount !== 1 ? 's' : ''}`}
          sub2={distinctDomains.length > 0 ? distinctDomains.join('+') : undefined}
        />
        <StepCard
          num="04"
          label="DECIDE"
          status={decideStatus}
          sub1={`${evaluatedCount} evaluated`}
          sub2={`${approvedCount} approved`}
        />
        <StepCard
          num="05"
          label="EXECUTE"
          status={executeStatus}
          sub1={executeLabel}
        />
      </Box>

      <Box sx={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <Box sx={{ flex: 1, px: 1.5, py: 1, borderRight: '1px solid #1C2128', overflow: 'auto' }}>
          <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.6rem', color: '#484F58', letterSpacing: '0.12em', mb: 0.75 }}>
            OPERATIONAL ASSESSMENT
          </Typography>

          <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1, mb: 0.75 }}>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.72rem', color: '#C9D1D9', lineHeight: 1.5, flex: 1 }}>
              {a.summary}
            </Typography>
            <Box sx={{ px: 0.75, py: 0.2, flexShrink: 0, border: `1px solid ${SEVERITY_COLOR[a.severity] ?? '#484F58'}`, borderRadius: 0.5 }}>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', fontWeight: 700, color: SEVERITY_COLOR[a.severity] ?? '#484F58' }}>
                {a.severity.toUpperCase()}
              </Typography>
            </Box>
          </Box>

          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58', letterSpacing: '0.08em', mb: 0.5 }}>
            FACTS OBSERVED
          </Typography>
          {a.facts_observed.map((f, i) => (
            <Box key={i} sx={{ display: 'flex', gap: 0.75, mb: 0.25 }}>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#484F58', flexShrink: 0 }}>·</Typography>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#8B949E', lineHeight: 1.5 }}>{f}</Typography>
            </Box>
          ))}

          {skillsConsulted.length > 0 && (
            <>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58', letterSpacing: '0.08em', mt: 0.75, mb: 0.5 }}>
                SKILLS CONSULTED
              </Typography>
              {skillsConsulted.map((s, i) => (
                <Box key={i} sx={{ display: 'flex', gap: 0.75, mb: 0.25 }}>
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#484F58', flexShrink: 0 }}>·</Typography>
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#8B949E' }}>{s}</Typography>
                </Box>
              ))}
            </>
          )}

          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#30363D', mt: 0.75 }}>
            {modelShortName(a.model_id)} · {a.latency_ms}ms
          </Typography>
        </Box>

        <Box sx={{ flex: 1, px: 1.5, py: 1, overflow: 'auto' }}>
          <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.6rem', color: '#484F58', letterSpacing: '0.12em', mb: 0.75 }}>
            RECOMMENDED ACTIONS
          </Typography>

          {a.recommendations.length === 0 && (
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.7rem', color: '#3FB950' }}>
              ✓ No disruptive conditions detected.
            </Typography>
          )}

          {a.recommendations.map((rec, i) => {
            const proposal = result.proposal_results[i];
            const risk = proposal
              ? getProposalRisk(result.lifecycle, proposal.proposal_id as string | undefined, i)
              : 'unknown';
            const status = proposal?.status ?? 'unknown';
            const statusColor = PROPOSAL_STATUS_COLOR[status] ?? '#484F58';
            const priorityColor = PRIORITY_COLOR[rec.priority] ?? '#484F58';
            const isExecuted = status === 'executed' || status === 'approved';
            const isBlocked = status === 'requires_fresh_state';
            const isApproval = status === 'requires_human_approval';

            return (
              <Box key={i} sx={{ mb: 1.5, pb: 1.5, borderBottom: '1px solid #1C2128' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#484F58' }}>[{i + 1}]</Typography>
                  <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.62rem', color: '#C9D1D9', flexGrow: 1 }}>
                    AI RECOMMENDATION
                  </Typography>
                  <Box sx={{ px: 0.75, py: 0.15, border: `1px solid ${priorityColor}`, borderRadius: 0.5 }}>
                    <Typography sx={{ fontFamily: 'monospace', fontSize: '0.52rem', fontWeight: 700, color: priorityColor }}>
                      {rec.priority.toUpperCase()}
                    </Typography>
                  </Box>
                </Box>

                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#76B900', mb: 0.25 }}>
                  {rec.capability} → {rec.target}
                </Typography>
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#8B949E', mb: 0.75, lineHeight: 1.4 }}>
                  {rec.objective}
                </Typography>

                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#30363D', mb: 0.5 }}>
                  ↓ CANONICAL PROPOSAL BUILDER
                </Typography>

                {proposal && (
                  <Box sx={{ pl: 1, borderLeft: '2px solid #1C2128' }}>
                    <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#6E7681', mb: 0.2 }}>
                      {proposal.action ?? rec.capability}
                    </Typography>
                    {proposal.proposal_id && (
                      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58', mb: 0.2 }}>
                        proposal: {String(proposal.proposal_id).slice(0, 8)}
                      </Typography>
                    )}
                    <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58', mb: 0.5 }}>
                      risk: {risk}
                    </Typography>

                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.25 }}>
                      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58' }}>DECIDE:</Typography>
                      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', fontWeight: 700, color: statusColor }}>
                        {status.toUpperCase().replace(/_/g, ' ')}
                      </Typography>
                    </Box>

                    {isExecuted && (
                      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#3FB950' }}>
                        EXECUTE: ✓ MCP WRITE
                      </Typography>
                    )}
                    {isBlocked && (
                      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#F85149' }}>
                        BLOCKED: NO WAREHOUSE WRITE
                      </Typography>
                    )}
                    {isApproval && (
                      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#D29922' }}>
                        EXECUTE: AWAITING OPERATOR
                      </Typography>
                    )}
                  </Box>
                )}
              </Box>
            );
          })}
        </Box>
      </Box>

      {hasBlocked && (
        <Box sx={{ borderTop: '1px solid #1C2128', px: 1.5, py: 0.75, backgroundColor: 'rgba(248,81,73,0.06)' }}>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#F85149', flexShrink: 0 }}>⚠</Typography>
            <Box>
              <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.62rem', color: '#F85149', mb: 0.25 }}>
                EXECUTION BLOCKED — STATE DRIFT DETECTED
              </Typography>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#8B949E', lineHeight: 1.4 }}>
                Snapshot declared asset AVAILABLE but current world state shows ASSIGNED.
              </Typography>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#6E7681' }}>
                ActionExecutor rejected execution. NO WAREHOUSE WRITE PERFORMED.
              </Typography>
            </Box>
          </Box>
        </Box>
      )}

      {!hasBlocked && hasApprovalPending && (
        <Box sx={{ borderTop: '1px solid #1C2128', px: 1.5, py: 0.75, backgroundColor: 'rgba(210,153,34,0.06)' }}>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#D29922', flexShrink: 0 }}>●</Typography>
            <Box>
              <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.62rem', color: '#D29922', mb: 0.25 }}>
                REQUIRES HUMAN APPROVAL
              </Typography>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#8B949E' }}>
                Action was proposed and decided. Execution is gated on operator approval.
              </Typography>
            </Box>
          </Box>
        </Box>
      )}

      {result.pre_kpis && result.post_kpis && result.kpi_delta && (
        <Box sx={{ borderTop: '1px solid #1C2128', px: 1.5, py: 1 }}>
          <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.6rem', color: '#484F58', letterSpacing: '0.12em', mb: 0.75 }}>
            OPERATIONAL IMPACT OF THIS DECISION
          </Typography>
          <Box sx={{ display: 'grid', gridTemplateColumns: '1.8fr 1fr 1fr 1fr', gap: 0, borderTop: '1px solid #1C2128' }}>
            {/* Header */}
            {['METRIC', 'BEFORE', 'AFTER', 'Δ'].map((h, i) => (
              <Typography key={h} sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58', fontWeight: 700, py: 0.5, px: 0.5, borderBottom: '1px solid #1C2128', borderRight: i < 3 ? '1px solid #1C2128' : 'none' }}>
                {h}
              </Typography>
            ))}
            {/* Rows — show exact metrics only */}
            {[
              { label: 'Equip Operational', pre: `${result.pre_kpis.equipment_operational_pct}%`, post: `${result.post_kpis.equipment_operational_pct}%`, delta: result.kpi_delta.equipment_operational_pct, higher_is_better: true },
              { label: 'Labor Utilization', pre: `${result.pre_kpis.labor_utilization_pct}%`, post: `${result.post_kpis.labor_utilization_pct}%`, delta: result.kpi_delta.labor_utilization_pct, higher_is_better: true },
              { label: 'Pending Backlog', pre: String(result.pre_kpis.pending_backlog), post: String(result.post_kpis.pending_backlog), delta: result.kpi_delta.pending_backlog, higher_is_better: false },
              { label: 'Wave Risk Score', pre: `${result.pre_kpis.wave_risk_score}`, post: `${result.post_kpis.wave_risk_score}`, delta: result.kpi_delta.wave_risk_score, higher_is_better: false },
            ].map((row, i) => {
              const improved = row.higher_is_better ? row.delta > 0 : row.delta < 0;
              const neutral = row.delta === 0;
              const deltaColor = neutral ? '#484F58' : improved ? '#3FB950' : '#F85149';
              const deltaPrefix = row.delta > 0 ? '+' : '';
              const borderB = i < 3 ? '1px solid #1C2128' : 'none';
              return (
                <React.Fragment key={row.label}>
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#8B949E', py: 0.4, px: 0.5, borderBottom: borderB, borderRight: '1px solid #1C2128' }}>{row.label}</Typography>
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#6E7681', py: 0.4, px: 0.5, borderBottom: borderB, borderRight: '1px solid #1C2128' }}>{row.pre}</Typography>
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#C9D1D9', py: 0.4, px: 0.5, borderBottom: borderB, borderRight: '1px solid #1C2128' }}>{row.post}</Typography>
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', fontWeight: 700, color: deltaColor, py: 0.4, px: 0.5, borderBottom: borderB }}>{neutral ? '—' : `${deltaPrefix}${row.delta}`}</Typography>
                </React.Fragment>
              );
            })}
          </Box>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#21262D', mt: 0.5 }}>
            Pre-intervention vs. post-execution snapshot · not a MAIW-vs-control comparison
          </Typography>
        </Box>
      )}
    </Box>
  );
};

export default MAIWPipeline;
