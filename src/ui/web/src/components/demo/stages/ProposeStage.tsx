/**
 * ProposeStage — shows the ActionProposal MAIW artifacts.
 *
 * Data sources:
 *   1. SSE PROPOSE events: message=proposal.action, detail="proposal=<id_prefix>"
 *   2. analysisResult.lifecycle PROPOSE records: action, proposal_id, risk_level
 *   3. analysisResult.assessment.recommendations[i]: capability, target, rationale
 *
 * No "projected impact" numbers — kpi_delta is post-execution only (Phase 12E).
 */

import React from 'react';
import { Box, Typography } from '@mui/material';
import {
  SectionHeader,
  StageSection,
  MonoText,
  RiskBadge,
  IdText,
  parseDetail,
  runWindowEvents,
  StageContentPaneProps,
} from '../StageContentPane';

// ── Proposal card ─────────────────────────────────────────────────────────────

interface ProposalCardProps {
  index: number;
  action: string;
  capability?: string;
  target?: string;
  riskLevel?: string;
  proposalId?: string;
  rationale?: string;
}

function ProposalCard({ index, action, capability, target, riskLevel, proposalId, rationale }: ProposalCardProps) {
  return (
    <Box sx={{
      background: '#161B22',
      border: '1px solid #21262D',
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
          Proposal {index + 1}
        </Typography>
        {riskLevel && (
          <Box sx={{ ml: 'auto' }}>
            <RiskBadge level={riskLevel} />
          </Box>
        )}
      </Box>

      {/* Card body */}
      <Box sx={{ px: 1.5, py: 1.25, display: 'flex', flexDirection: 'column', gap: 1 }}>
        {/* Action */}
        <Box>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58', textTransform: 'uppercase', letterSpacing: '0.08em', mb: '3px' }}>
            Action
          </Typography>
          <MonoText color="#C9D1D9" weight={500}>{action}</MonoText>
        </Box>

        {/* Capability / target row */}
        {(capability || target) && (
          <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
            {capability && <IdText label="Capability" value={capability} />}
            {target && <IdText label="Target" value={target} />}
          </Box>
        )}

        {/* Rationale */}
        {rationale && (
          <Box>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58', textTransform: 'uppercase', letterSpacing: '0.08em', mb: '3px' }}>
              Reason
            </Typography>
            <MonoText color="#8B949E" size="0.68rem">{rationale}</MonoText>
          </Box>
        )}

        {/* Proposal ID */}
        {proposalId && (
          <Box>
            <IdText label="Proposal ID" value={proposalId} />
          </Box>
        )}
      </Box>
    </Box>
  );
}

// ── ProposeStage ──────────────────────────────────────────────────────────────

export default function ProposeStage({ sseEvents, analysisResult }: StageContentPaneProps) {
  const proposeEvents = runWindowEvents(sseEvents, ['PROPOSE']);

  // Prefer structured lifecycle records when available
  const proposeRecords = analysisResult?.lifecycle?.filter(r => r.phase === 'PROPOSE') ?? [];
  const skillRecords   = analysisResult?.lifecycle?.filter(r => r.phase === 'SKILL') ?? [];
  const recommendations = analysisResult?.assessment?.recommendations ?? [];

  // Build card data from lifecycle records (structured, preferred)
  const cards: ProposalCardProps[] = proposeRecords.length > 0
    ? proposeRecords.map((pr, i) => {
        const rec = recommendations[pr.index ?? i];
        const skill = skillRecords.find(s => (s.index ?? i) === (pr.index ?? i));
        return {
          index: pr.index ?? i,
          action: pr.action ?? '—',
          capability: skill?.capability ?? rec?.capability,
          target: skill?.target ?? rec?.target,
          riskLevel: pr.risk_level,
          proposalId: pr.proposal_id,
          rationale: rec?.rationale ?? skill?.objective,
        };
      })
    // Fall back to SSE events when lifecycle records not yet available
    : proposeEvents.map((ev, i) => {
        const d = parseDetail(ev.detail);
        return {
          index: i,
          action: ev.message,
          proposalId: d.proposal ? `${d.proposal}…` : undefined,
        };
      });

  return (
    <Box data-testid="propose-stage">
      {/* Stage header */}
      <StageSection>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Typography sx={{
            fontFamily: 'monospace', fontSize: '0.72rem', fontWeight: 700,
            color: '#58A6FF', textTransform: 'uppercase', letterSpacing: '0.06em',
          }}>
            Propose
          </Typography>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58' }}>
            MAIW Action Proposal
          </Typography>
        </Box>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#30363D', mt: 0.5 }}>
          No projected impact numbers — actuals captured post-execution in Outcome
        </Typography>
      </StageSection>

      {/* Proposal cards */}
      {cards.length > 0 ? (
        <StageSection last>
          <SectionHeader>
            {cards.length === 1 ? '1 proposal' : `${cards.length} proposals`}
          </SectionHeader>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
            {cards.map(c => (
              <ProposalCard key={c.index} {...c} />
            ))}
          </Box>
        </StageSection>
      ) : (
        <StageSection last>
          <MonoText color="#484F58" size="0.65rem">
            Waiting for ProposalBuilder...
          </MonoText>
        </StageSection>
      )}
    </Box>
  );
}
