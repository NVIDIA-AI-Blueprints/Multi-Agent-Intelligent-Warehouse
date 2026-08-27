/**
 * ApproveStage — first-class APPROVE stage with full-width ApprovalCard hero.
 *
 * Data sources:
 *   - pendingApprovals: PendingApproval[]  — live from demoStatus (backend truth)
 *   - analysisResult?.assessment.facts_observed — facts block context
 *   - demoStatus.current_kpis — state freshness indicator
 *
 * Design contracts:
 *   - Never shows projected numeric impact (kpi_delta reserved for 12E / OUTCOME)
 *   - Rail advances only via SSE/backend events — never optimistically from UI
 *   - APPROVED (api ok) vs CONSUMED (404 / disappeared) are distinct states
 *   - Expired approvals (> 10 min old) are non-actionable
 *   - If approval disappears from queue without local action, resolves from backend truth
 */

import React, { useState } from 'react';
import { Box, CircularProgress, Typography } from '@mui/material';
import { useQueryClient } from '@tanstack/react-query';
import { demoAPI, PendingApproval } from '../../../services/demoAPI';
import {
  SectionHeader,
  StageSection,
  MonoText,
  RiskBadge,
  IdText,
  StageContentPaneProps,
} from '../StageContentPane';

// ── Constants ──────────────────────────────────────────────────────────────────

const EXPIRE_MS = 10 * 60 * 1000; // 10 minutes

// ── Types ──────────────────────────────────────────────────────────────────────

type ActionStatus = 'approving' | 'rejecting';

interface CardResult {
  outcome: 'approved' | 'rejected' | 'consumed' | 'error';
  message: string;
  ok: boolean;
}

// ── Freshness tag (inline, smaller variant for card) ──────────────────────────

function FreshnessTag({ seconds }: { seconds: number | null | undefined }) {
  if (seconds == null) return null;
  const color  = seconds < 60 ? '#3FB950' : seconds < 120 ? '#D29922' : '#F85149';
  const label  = seconds < 60 ? `${Math.round(seconds)}s` : `${Math.round(seconds / 60)}m`;
  const status = seconds < 60 ? 'FRESH' : seconds < 120 ? 'AGING' : 'STALE';
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
      <Box component="span" sx={{
        fontFamily: 'monospace', fontSize: '0.6rem', color,
        border: `1px solid ${color}33`, borderRadius: '3px', px: '4px', py: '1px',
        fontWeight: 700, letterSpacing: '0.06em',
      }}>
        {status}
      </Box>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#484F58' }}>
        {label} old
      </Typography>
    </Box>
  );
}

// ── Result badge (post-action) ─────────────────────────────────────────────────

function ResultBadge({ result }: { result: CardResult }) {
  const COLOR: Record<CardResult['outcome'], string> = {
    approved: '#3FB950',
    rejected: '#6E7681',
    consumed: '#D29922',
    error:    '#F85149',
  };
  const LABEL: Record<CardResult['outcome'], string> = {
    approved: 'APPROVED',
    rejected: 'REJECTED',
    consumed: 'CONSUMED',
    error:    'ERROR',
  };
  const color = COLOR[result.outcome];
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
      <Box component="span" sx={{
        fontFamily: 'monospace', fontSize: '0.65rem', fontWeight: 700,
        color, border: `1px solid ${color}44`, borderRadius: '3px',
        px: '6px', py: '2px', textTransform: 'uppercase', letterSpacing: '0.08em',
        alignSelf: 'flex-start',
      }}>
        {LABEL[result.outcome]}
      </Box>
      <MonoText color="#484F58" size="0.62rem">{result.message}</MonoText>
    </Box>
  );
}

// ── ApprovalCard ──────────────────────────────────────────────────────────────

interface ApprovalCardProps {
  approval: PendingApproval;
  actionStatus: ActionStatus | undefined;
  result: CardResult | undefined;
  factsObserved: string[];
  stateAgeSeconds: number | null | undefined;
  onApprove: (pending_id: string) => void;
  onReject: (pending_id: string) => void;
}

function ApprovalCard({
  approval,
  actionStatus,
  result,
  factsObserved,
  stateAgeSeconds,
  onApprove,
  onReject,
}: ApprovalCardProps) {
  const { pending_id, capability, target, domain, risk_level, objective, rationale, proposal_id, decision_id, priority, queued_at } = approval;

  const approvalAgeMs = Date.now() - new Date(queued_at).getTime();
  const expired = approvalAgeMs > EXPIRE_MS;
  const inFlight = actionStatus != null;
  const actioned = result != null;
  const disableActions = inFlight || actioned || expired;

  return (
    <Box
      data-testid="approval-card"
      sx={{
        background: '#161B22',
        border: `1px solid ${expired ? '#484F58' : '#D2992244'}`,
        borderRadius: '6px',
        overflow: 'hidden',
      }}
    >
      {/* Hero header */}
      <Box sx={{
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'space-between',
        px: 2,
        py: 1.5,
        borderBottom: '1px solid #21262D',
        background: '#0D1117',
      }}>
        <Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.5 }}>
            <Typography sx={{
              fontFamily: 'monospace', fontSize: '0.58rem', color: '#D29922',
              letterSpacing: '0.12em', textTransform: 'uppercase', fontWeight: 700,
            }}>
              05 APPROVE
            </Typography>
            {expired && (
              <Box component="span" sx={{
                fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58',
                border: '1px solid #30363D', borderRadius: '3px', px: '4px', py: '1px',
              }}>
                EXPIRED
              </Box>
            )}
          </Box>
          <Typography sx={{
            fontFamily: 'monospace', fontSize: '0.85rem', fontWeight: 700,
            color: '#C9D1D9', letterSpacing: '0.04em',
          }}>
            HUMAN APPROVAL REQUIRED
          </Typography>
        </Box>
        <Box sx={{ textAlign: 'right' }}>
          <RiskBadge level={risk_level} />
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58', mt: '4px' }}>
            {priority} priority
          </Typography>
        </Box>
      </Box>

      {/* Card body */}
      <Box sx={{ px: 2, py: 1.75, display: 'flex', flexDirection: 'column', gap: 1.75 }}>

        {/* Proposed Action */}
        <StageSection>
          <SectionHeader>Proposed Action</SectionHeader>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
            <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1 }}>
              <MonoText color="#C9D1D9" weight={700}>{capability}</MonoText>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58' }}>→</Typography>
              <MonoText color="#8B949E">{target}</MonoText>
            </Box>
            <MonoText color="#8B949E" size="0.7rem">{objective}</MonoText>
            <MonoText color="#484F58" size="0.6rem">domain: {domain}</MonoText>
          </Box>
        </StageSection>

        {/* Why (rationale) */}
        <StageSection>
          <SectionHeader>Why</SectionHeader>
          <Box sx={{
            background: '#0D1117',
            border: '1px solid #21262D',
            borderRadius: '4px',
            px: 1.5,
            py: 1,
          }}>
            <MonoText color="#8B949E" size="0.7rem">{rationale || '—'}</MonoText>
          </Box>
        </StageSection>

        {/* Facts supporting this decision */}
        {factsObserved.length > 0 && (
          <StageSection>
            <SectionHeader>Facts supporting this decision</SectionHeader>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
              {factsObserved.map((fact, i) => (
                <Box key={i} sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58', flexShrink: 0, mt: '1px' }}>
                    ·
                  </Typography>
                  <MonoText color="#8B949E" size="0.68rem">{fact}</MonoText>
                </Box>
              ))}
            </Box>
          </StageSection>
        )}

        {/* State validity */}
        <StageSection>
          <SectionHeader>State validity</SectionHeader>
          <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap', alignItems: 'center' }}>
            <FreshnessTag seconds={stateAgeSeconds} />
            <IdText label="Proposal" value={proposal_id} />
            <IdText label="Decision" value={decision_id} />
          </Box>
        </StageSection>

        {/* Action buttons or result */}
        {actioned ? (
          <Box data-testid="approval-result">
            <ResultBadge result={result} />
            {result.outcome === 'approved' && (
              <MonoText color="#484F58" size="0.6rem" >
                Rail advances to EXECUTE when SSE confirms.
              </MonoText>
            )}
          </Box>
        ) : (
          <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', pt: 0.5 }}>
            {/* REJECT */}
            <Box
              component="button"
              onClick={() => !disableActions && onReject(pending_id)}
              disabled={disableActions}
              data-testid="reject-button"
              sx={{
                display: 'flex', alignItems: 'center', gap: 0.75,
                background: 'transparent',
                border: `1px solid ${disableActions ? '#21262D' : '#30363D'}`,
                borderRadius: '4px',
                px: '12px', py: '7px',
                fontFamily: 'monospace', fontSize: '0.68rem', fontWeight: 600,
                color: disableActions ? '#30363D' : '#6E7681',
                cursor: disableActions ? 'not-allowed' : 'pointer',
                letterSpacing: '0.04em',
                transition: 'all 0.12s ease',
                '&:hover:not(:disabled)': { color: '#F85149', borderColor: '#6e1111' },
              }}
            >
              {actionStatus === 'rejecting' && <CircularProgress size={10} sx={{ color: '#6E7681' }} />}
              REJECT
            </Box>

            {/* APPROVE & EXECUTE */}
            <Box
              component="button"
              onClick={() => !disableActions && onApprove(pending_id)}
              disabled={disableActions}
              data-testid="approve-execute-button"
              sx={{
                display: 'flex', alignItems: 'center', gap: 0.75,
                background: disableActions ? '#0d1f0d' : '#162032',
                border: `1px solid ${disableActions ? '#21262D' : '#1F6FEB'}`,
                borderRadius: '4px',
                px: '16px', py: '7px',
                fontFamily: 'monospace', fontSize: '0.68rem', fontWeight: 700,
                color: disableActions ? '#30363D' : '#58A6FF',
                cursor: disableActions ? 'not-allowed' : 'pointer',
                letterSpacing: '0.04em',
                transition: 'all 0.12s ease',
                '&:hover:not(:disabled)': { background: '#1a2d48', borderColor: '#388BFD' },
              }}
            >
              {actionStatus === 'approving' && <CircularProgress size={10} sx={{ color: '#58A6FF66' }} />}
              APPROVE &amp; EXECUTE
            </Box>

            {expired && (
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#484F58' }}>
                Approval expired — action not available
              </Typography>
            )}
          </Box>
        )}
      </Box>
    </Box>
  );
}

// ── ResolvedCard — shown when approval was resolved externally ─────────────────

function ResolvedCard({ pendingId }: { pendingId: string }) {
  return (
    <Box
      data-testid="resolved-card"
      sx={{
        background: '#161B22',
        border: '1px solid #21262D',
        borderRadius: '5px',
        px: 2,
        py: 1.5,
        display: 'flex',
        alignItems: 'center',
        gap: 1.5,
      }}
    >
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#484F58' }}>
        {pendingId.slice(0, 8)}…
      </Typography>
      <MonoText color="#484F58" size="0.65rem">
        Approval resolved — awaiting backend state update
      </MonoText>
    </Box>
  );
}

// ── ApproveStage ──────────────────────────────────────────────────────────────

export default function ApproveStage({
  pendingApprovals,
  demoStatus,
  analysisResult,
}: StageContentPaneProps) {
  const queryClient = useQueryClient();

  // Per-pending-id action status (in-flight only)
  const [statuses, setStatuses] = useState<Record<string, ActionStatus>>({});
  // Per-pending-id result (persists for display after approval disappears from list)
  const [results, setResults] = useState<Record<string, CardResult>>({});

  const handleApprove = async (pending_id: string) => {
    setStatuses(s => ({ ...s, [pending_id]: 'approving' }));
    try {
      const r = await demoAPI.approvePending(pending_id, 'operator');
      const outcome: CardResult['outcome'] = r.ok ? 'approved' : 'error';
      const message =
        r.status === 'executed'           ? `Executed — exec_id: ${r.execution_id ?? '?'}` :
        r.status === 'approved_no_executor'? 'Approved — no executor available' :
        r.status === 'CAPACITY_UNAVAILABLE'? `Capacity unavailable: ${r.reason ?? ''}` :
        r.status ?? 'Unknown status';
      setResults(res => ({ ...res, [pending_id]: { outcome, message, ok: r.ok } }));
      await queryClient.invalidateQueries({ queryKey: ['demo-status'] });
    } catch (e: any) {
      const consumed = e?.response?.status === 404;
      setResults(res => ({
        ...res,
        [pending_id]: {
          outcome: consumed ? 'consumed' : 'error',
          message: consumed
            ? 'Approval already consumed by another session'
            : (e?.message ?? 'Request failed'),
          ok: false,
        },
      }));
    } finally {
      setStatuses(s => { const n = { ...s }; delete n[pending_id]; return n; });
    }
  };

  const handleReject = async (pending_id: string) => {
    setStatuses(s => ({ ...s, [pending_id]: 'rejecting' }));
    try {
      await demoAPI.rejectPending(pending_id, 'operator');
      setResults(res => ({
        ...res,
        [pending_id]: { outcome: 'rejected', message: 'Rejected by operator', ok: true },
      }));
      await queryClient.invalidateQueries({ queryKey: ['demo-status'] });
    } catch (e: any) {
      const consumed = e?.response?.status === 404;
      setResults(res => ({
        ...res,
        [pending_id]: {
          outcome: consumed ? 'consumed' : 'error',
          message: consumed
            ? 'Approval already consumed'
            : (e?.message ?? 'Request failed'),
          ok: false,
        },
      }));
    } finally {
      setStatuses(s => { const n = { ...s }; delete n[pending_id]; return n; });
    }
  };

  // IDs that are live (in pending_approvals from backend)
  const liveIds = new Set(pendingApprovals.map(p => p.pending_id));

  // IDs that were actioned locally but have since disappeared from backend
  const resolvedExternallyIds = Object.keys(results).filter(id => !liveIds.has(id));

  // Facts to surface in the "facts supporting this decision" block
  const factsObserved = analysisResult?.assessment?.facts_observed ?? [];
  const stateAgeSeconds = demoStatus?.current_kpis?.state_freshness_seconds;

  return (
    <Box data-testid="approve-stage">
      {/* Stage header */}
      <StageSection>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Typography sx={{
            fontFamily: 'monospace', fontSize: '0.72rem', fontWeight: 700,
            color: '#D29922', textTransform: 'uppercase', letterSpacing: '0.06em',
          }}>
            Approve
          </Typography>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58' }}>
            Human Governance
          </Typography>
        </Box>
      </StageSection>

      {/* Live approval cards */}
      {pendingApprovals.map(approval => (
        <StageSection key={approval.pending_id}>
          <ApprovalCard
            approval={approval}
            actionStatus={statuses[approval.pending_id]}
            result={results[approval.pending_id]}
            factsObserved={factsObserved}
            stateAgeSeconds={stateAgeSeconds}
            onApprove={handleApprove}
            onReject={handleReject}
          />
        </StageSection>
      ))}

      {/* Resolved externally (disappeared without local action) */}
      {resolvedExternallyIds.map(id => {
        const r = results[id];
        return r ? (
          <StageSection key={id}>
            <ResultBadge result={r} />
          </StageSection>
        ) : (
          <StageSection key={id}>
            <ResolvedCard pendingId={id} />
          </StageSection>
        );
      })}

      {/* Empty state — no pending approvals and nothing in-flight */}
      {pendingApprovals.length === 0 && Object.keys(results).length === 0 && (
        <StageSection last>
          <MonoText color="#484F58" size="0.65rem" data-testid="no-approval-message">
            No pending approvals — waiting for backend approval record...
          </MonoText>
        </StageSection>
      )}
    </Box>
  );
}
