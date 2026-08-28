/**
 * DecideStage — shows DecisionEngine verdicts and the authority chain.
 *
 * Data sources:
 *   1. SSE DECIDE events: message=outcome, detail="proposal=<id> decision=<id>"
 *   2. analysisResult.lifecycle DECIDE records: outcome, proposal_id, decision_id, violations
 *   3. pendingApprovals: queued approvals when outcome=REQUIRES_HUMAN_APPROVAL
 *
 * Visual narrative:
 *   Nemotron recommends → MAIW proposes → DecisionEngine decides
 */

import React from 'react';
import { Box, Typography } from '@mui/material';
import {
  SectionHeader,
  StageSection,
  MonoText,
  OutcomeBadge,
  IdText,
  parseDetail,
  runWindowEvents,
  StageContentPaneProps,
} from '../StageContentPane';

// ── Authority chain ────────────────────────────────────────────────────────────

function AuthorityChain() {
  const steps = ['Nemotron recommends', 'MAIW proposes', 'DecisionEngine decides'];
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0, flexWrap: 'wrap' }}>
      {steps.map((s, i) => (
        <React.Fragment key={s}>
          <Box sx={{
            background: i === steps.length - 1 ? '#0d2146' : '#161B22',
            border: `1px solid ${i === steps.length - 1 ? '#1F6FEB44' : '#21262D'}`,
            borderRadius: '3px',
            px: '8px',
            py: '3px',
            flexShrink: 0,
          }}>
            <Typography sx={{
              fontFamily: 'monospace',
              fontSize: '0.6rem',
              color: i === steps.length - 1 ? '#58A6FF' : '#6E7681',
              fontWeight: i === steps.length - 1 ? 700 : 400,
              letterSpacing: '0.04em',
            }}>
              {s}
            </Typography>
          </Box>
          {i < steps.length - 1 && (
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58', px: '6px', flexShrink: 0 }}>
              →
            </Typography>
          )}
        </React.Fragment>
      ))}
    </Box>
  );
}

// ── Decision card ──────────────────────────────────────────────────────────────

interface DecisionCardProps {
  index: number;
  outcome: string;
  proposalId?: string;
  decisionId?: string;
  violations?: Array<{ rule?: string; message?: string }>;
  requiresApproval: boolean;
  pendingCount: number;
}

function DecisionCard({ index, outcome, proposalId, decisionId, violations, requiresApproval, pendingCount }: DecisionCardProps) {
  const borderColor =
    outcome === 'APPROVED' ? '#3FB95033' :
    outcome === 'REQUIRES_HUMAN_APPROVAL' ? '#D2992233' :
    '#F8514933';

  return (
    <Box sx={{
      background: '#161B22',
      border: `1px solid ${borderColor}`,
      borderRadius: '5px',
      overflow: 'hidden',
    }}>
      {/* Card header */}
      <Box sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 1.5,
        px: 1.5,
        py: '8px',
        borderBottom: '1px solid #21262D',
        background: '#0D1117',
      }}>
        <Typography sx={{
          fontFamily: 'monospace',
          fontSize: '0.55rem',
          color: '#484F58',
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
        }}>
          Decision {index + 1}
        </Typography>
        <Box sx={{ ml: 'auto' }}>
          <OutcomeBadge outcome={outcome} />
        </Box>
      </Box>

      {/* Card body */}
      <Box sx={{ px: 1.5, py: 1.25, display: 'flex', flexDirection: 'column', gap: 1 }}>
        {/* IDs */}
        <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
          {proposalId && <IdText label="Proposal" value={proposalId} />}
          {decisionId && <IdText label="Decision" value={decisionId} />}
        </Box>

        {/* Violations (if any) */}
        {violations && violations.length > 0 && (
          <Box>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58', textTransform: 'uppercase', letterSpacing: '0.08em', mb: '3px' }}>
              Policy violations
            </Typography>
            {violations.map((v, i) => (
              <MonoText key={i} color="#F85149" size="0.65rem">
                {v.rule ?? v.message ?? JSON.stringify(v)}
              </MonoText>
            ))}
          </Box>
        )}

        {/* Requires approval handoff */}
        {requiresApproval && (
          <Box sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            mt: 0.5,
            p: 1,
            background: '#0d1f0d',
            border: '1px solid #D2992233',
            borderRadius: '4px',
          }}>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#D29922' }}>
              ↓
            </Typography>
            <Box>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#D29922', fontWeight: 700 }}>
                Advancing to APPROVE
              </Typography>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#484F58' }}>
                {pendingCount > 0
                  ? `${pendingCount} approval${pendingCount > 1 ? 's' : ''} queued for human review`
                  : 'Waiting for pending approval record...'}
              </Typography>
            </Box>
          </Box>
        )}
      </Box>
    </Box>
  );
}

// ── DecideStage ───────────────────────────────────────────────────────────────

export default function DecideStage({ sseEvents, analysisResult, pendingApprovals }: StageContentPaneProps) {
  const decideEvents = runWindowEvents(sseEvents, ['DECIDE']);
  const decideRecords = analysisResult?.lifecycle?.filter(r => r.phase === 'DECIDE') ?? [];

  // Build card data from lifecycle records (structured, preferred)
  const cards: DecisionCardProps[] = decideRecords.length > 0
    ? decideRecords.map((dr, i) => ({
        index: dr.index ?? i,
        outcome: dr.outcome ?? '—',
        proposalId: dr.proposal_id,
        decisionId: dr.decision_id,
        violations: dr.violations ?? [],
        requiresApproval: dr.outcome === 'REQUIRES_HUMAN_APPROVAL',
        pendingCount: pendingApprovals.length,
      }))
    // Fall back to SSE events
    : decideEvents.map((ev, i) => {
        const d = parseDetail(ev.detail);
        const outcome = ev.message ?? '—';
        return {
          index: i,
          outcome,
          proposalId: d.proposal ? `${d.proposal}…` : undefined,
          decisionId: d.decision ? `${d.decision}…` : undefined,
          violations: [],
          requiresApproval: outcome === 'REQUIRES_HUMAN_APPROVAL',
          pendingCount: pendingApprovals.length,
        };
      });

  const hasApprovalNeeded = cards.some(c => c.requiresApproval);

  return (
    <Box data-testid="decide-stage">
      {/* Stage header + authority chain */}
      <StageSection>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1.25 }}>
          <Typography sx={{
            fontFamily: 'monospace', fontSize: '0.72rem', fontWeight: 700,
            color: '#58A6FF', textTransform: 'uppercase', letterSpacing: '0.06em',
          }}>
            Decide
          </Typography>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58' }}>
            DecisionEngine
          </Typography>
        </Box>
        <AuthorityChain />
      </StageSection>

      {/* Decision cards */}
      {cards.length > 0 ? (
        <StageSection last={!hasApprovalNeeded}>
          <SectionHeader>
            {cards.length === 1 ? '1 decision' : `${cards.length} decisions`}
          </SectionHeader>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
            {cards.map(c => (
              <DecisionCard key={c.index} {...c} />
            ))}
          </Box>
        </StageSection>
      ) : (
        <StageSection>
          <MonoText color="#484F58" size="0.65rem">
            Waiting for DecisionEngine evaluation...
          </MonoText>
        </StageSection>
      )}

      {/* Approval queue summary when multiple pending */}
      {pendingApprovals.length > 0 && (
        <StageSection last>
          <SectionHeader>Pending approval queue</SectionHeader>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
            {pendingApprovals.map(pa => (
              <Box key={pa.pending_id} sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 2,
                background: '#161B22',
                border: '1px solid #21262D',
                borderRadius: '4px',
                px: 1.25,
                py: '6px',
              }}>
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#D29922', fontWeight: 700 }}>
                  {pa.capability}
                </Typography>
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#484F58' }}>
                  {pa.target}
                </Typography>
                <Box sx={{ ml: 'auto' }}>
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                    {pa.priority}
                  </Typography>
                </Box>
              </Box>
            ))}
          </Box>
        </StageSection>
      )}
    </Box>
  );
}
