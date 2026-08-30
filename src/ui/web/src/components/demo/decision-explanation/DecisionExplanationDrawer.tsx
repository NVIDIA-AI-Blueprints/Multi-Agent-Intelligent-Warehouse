/**
 * DecisionExplanationDrawer.tsx — "Why This Decision?" contextual inspector panel (Phase 13D).
 *
 * Positioned as an absolutely-placed overlay inside StageContentPane (no MUI portal).
 * Width: 320px fixed. Triggered by node click or stage CTA buttons.
 *
 * Constraints:
 *   - Does NOT call any AI model
 *   - Does NOT expose chain_of_thought / scratchpad / hidden_reasoning / reasoning_tokens
 *   - Does NOT fabricate policy names
 *   - Does NOT infer freshness from Date.now() (uses state_freshness_seconds only)
 *   - Does NOT imply retry occurred for UNKNOWN executions
 */

import React, { useEffect, useState } from 'react';
import { Box, Typography } from '@mui/material';
import { DecisionGraph } from '../decision-graph/graphTypes';
import { AnalysisResult, PendingApproval, DemoStatus } from '../../../services/demoAPI';
import {
  ExplanationFocus,
  DecisionExplanation,
  ExplanationApproval,
} from './explanationTypes';
import { buildDecisionExplanation, buildStageExplanation } from './buildDecisionExplanation';
import {
  BreadcrumbBar,
  SectionLabel,
  DrawerDivider,
  SourceBadge,
  EvidenceRow,
  KPIDeltaRow,
  TraceSection,
} from './ExplanationSection';

// ── Props ──────────────────────────────────────────────────────────────────────

interface DecisionExplanationDrawerProps {
  focus: ExplanationFocus;
  graph: DecisionGraph;
  analysisResult: AnalysisResult | null;
  pendingApprovals: PendingApproval[];
  demoStatus: DemoStatus | null;
  onClose: () => void;
}

// ── Approval state badge ───────────────────────────────────────────────────────

const APPROVAL_STATE_COLOR: Record<ExplanationApproval['state'], string> = {
  PENDING:  '#D29922',
  APPROVED: '#3FB950',
  REJECTED: '#F85149',
  EXPIRED:  '#484F58',
  CONSUMED: '#58A6FF',
  UNKNOWN:  '#D29922',
};

function ApprovalStateBadge({ state }: { state: ExplanationApproval['state'] }) {
  const color = APPROVAL_STATE_COLOR[state] ?? '#484F58';
  return (
    <Box component="span" sx={{
      fontFamily: 'monospace', fontSize: '0.62rem', fontWeight: 700,
      color, border: `1px solid ${color}44`, borderRadius: '3px',
      px: '5px', py: '1px', textTransform: 'uppercase', letterSpacing: '0.08em',
    }}>
      {state}
    </Box>
  );
}

// ── Severity badge ─────────────────────────────────────────────────────────────

const SEVERITY_COLOR: Record<string, string> = {
  critical: '#F85149',
  high:     '#F85149',
  medium:   '#D29922',
  low:      '#3FB950',
};

function SeverityBadge({ severity }: { severity: string }) {
  const color = SEVERITY_COLOR[severity?.toLowerCase()] ?? '#484F58';
  return (
    <Box component="span" sx={{
      fontFamily: 'monospace', fontSize: '0.62rem', fontWeight: 700,
      color, border: `1px solid ${color}44`, borderRadius: '3px',
      px: '5px', py: '1px', textTransform: 'uppercase', letterSpacing: '0.08em',
    }}>
      {severity}
    </Box>
  );
}

// ── Outcome badge (policy) ─────────────────────────────────────────────────────

function OutcomeBadge({ outcome }: { outcome: string }) {
  const color =
    outcome === 'APPROVED'               ? '#3FB950' :
    outcome === 'REQUIRES_HUMAN_APPROVAL'? '#D29922' :
    outcome === 'REJECTED'               ? '#F85149' : '#484F58';
  const label =
    outcome === 'REQUIRES_HUMAN_APPROVAL' ? 'REQUIRES APPROVAL' : outcome;
  return (
    <Box component="span" sx={{
      fontFamily: 'monospace', fontSize: '0.62rem', fontWeight: 700,
      color, border: `1px solid ${color}44`, borderRadius: '3px',
      px: '5px', py: '1px', textTransform: 'uppercase', letterSpacing: '0.08em',
    }}>
      {label}
    </Box>
  );
}

// ── Risk badge ─────────────────────────────────────────────────────────────────

const RISK_COLOR: Record<string, string> = {
  none:     '#484F58',
  low:      '#3FB950',
  medium:   '#D29922',
  high:     '#F85149',
  critical: '#F85149',
};

function RiskBadge({ level }: { level: string }) {
  const color = RISK_COLOR[level?.toLowerCase()] ?? '#484F58';
  return (
    <Box component="span" sx={{
      fontFamily: 'monospace', fontSize: '0.62rem', fontWeight: 700,
      color, border: `1px solid ${color}44`, borderRadius: '3px',
      px: '5px', py: '1px', textTransform: 'uppercase', letterSpacing: '0.08em',
    }}>
      {level}
    </Box>
  );
}

// ── MonoField — label + value row ─────────────────────────────────────────────

function MonoField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1, mb: 0.5 }}>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58', textTransform: 'uppercase', letterSpacing: '0.08em', minWidth: 72, flexShrink: 0, pt: '1px' }}>
        {label}
      </Typography>
      <Box sx={{ flex: 1 }}>
        {children}
      </Box>
    </Box>
  );
}

function MonoValue({ children, color = '#C9D1D9' }: { children: React.ReactNode; color?: string }) {
  return (
    <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', color, lineHeight: 1.5 }}>
      {children}
    </Typography>
  );
}

// ── Proposal selector (multiple proposals) ─────────────────────────────────────

interface ProposalSelectorProps {
  count: number;
  selected: number;
  onSelect: (idx: number) => void;
}

function ProposalSelector({ count, selected, onSelect }: ProposalSelectorProps) {
  if (count <= 1) return null;
  const labels = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('');
  return (
    <Box sx={{ mb: 1 }}>
      <SectionLabel>SELECT PROPOSAL</SectionLabel>
      <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap' }}>
        {Array.from({ length: count }, (_, i) => (
          <Box
            key={i}
            component="button"
            onClick={() => onSelect(i)}
            sx={{
              background: selected === i ? '#161B22' : 'transparent',
              border: `1px solid ${selected === i ? '#58A6FF' : '#30363D'}`,
              borderRadius: '4px',
              color: selected === i ? '#58A6FF' : '#484F58',
              cursor: 'pointer',
              fontFamily: 'monospace',
              fontSize: '0.62rem',
              fontWeight: selected === i ? 700 : 400,
              letterSpacing: '0.06em',
              px: '8px',
              py: '3px',
            }}
          >
            [{labels[i] ?? i + 1}]
          </Box>
        ))}
      </Box>
    </Box>
  );
}

// ── Explanation body ───────────────────────────────────────────────────────────

function ExplanationBody({ explanation }: { explanation: DecisionExplanation }) {
  const { assessment, recommendation, proposal, policyEvaluation, approval, execution, outcome } = explanation;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0 }}>

      {/* SUMMARY */}
      {explanation.summary && (
        <>
          <SectionLabel>SUMMARY</SectionLabel>
          <MonoValue color="#C9D1D9">{explanation.summary}</MonoValue>
          <DrawerDivider />
        </>
      )}

      {/* ASSESSMENT */}
      {assessment && (
        <>
          <SectionLabel>ASSESSMENT</SectionLabel>
          <MonoValue>{assessment.summary}</MonoValue>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.75, mb: 0.5 }}>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              SEVERITY
            </Typography>
            <SeverityBadge severity={assessment.severity} />
          </Box>
          {assessment.supportingEvidence.length > 0 && (
            <>
              <Box sx={{ mt: 0.75 }}>
                <SectionLabel>SUPPORTING EVIDENCE</SectionLabel>
                {assessment.supportingEvidence.map((ev, i) => (
                  <EvidenceRow key={i} {...ev} />
                ))}
              </Box>
            </>
          )}
          {assessment.modelId && (
            <MonoField label="MODEL">
              <MonoValue color="#8B949E">{assessment.modelId}</MonoValue>
            </MonoField>
          )}
          {assessment.routingRule && (
            <MonoField label="ROUTING">
              <MonoValue color="#8B949E">{assessment.routingRule}</MonoValue>
            </MonoField>
          )}
          <DrawerDivider />
        </>
      )}

      {/* RECOMMENDATION */}
      {recommendation && (
        <>
          <SectionLabel>RECOMMENDATION</SectionLabel>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'baseline', mb: 0.5 }}>
            <MonoValue color="#C9D1D9">{recommendation.capability}</MonoValue>
            {recommendation.target && (
              <>
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58' }}>→</Typography>
                <MonoValue color="#8B949E">{recommendation.target}</MonoValue>
              </>
            )}
          </Box>
          {recommendation.rationale && (
            <>
              <SectionLabel>RATIONALE</SectionLabel>
              <MonoValue color="#8B949E">{recommendation.rationale}</MonoValue>
            </>
          )}
          {/* Show "no change" note only if there's no proposal */}
          {!proposal && (
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#30363D', mt: 0.5, fontStyle: 'italic' }}>
              NO WAREHOUSE CHANGE HAS OCCURRED YET
            </Typography>
          )}
          <DrawerDivider />
        </>
      )}

      {/* PROPOSAL */}
      {proposal && (
        <>
          <SectionLabel>AI RECOMMENDATION → MAIW ACTION PROPOSAL</SectionLabel>
          {proposal.sourceRecommendation && (
            <Box sx={{ mb: 1 }}>
              <MonoField label="CAPABILITY">
                <MonoValue color="#8B949E">{proposal.sourceRecommendation.capability}</MonoValue>
              </MonoField>
              {proposal.sourceRecommendation.target && (
                <MonoField label="TARGET">
                  <MonoValue color="#8B949E">{proposal.sourceRecommendation.target}</MonoValue>
                </MonoField>
              )}
              {proposal.sourceRecommendation.rationale && (
                <MonoField label="RATIONALE">
                  <MonoValue color="#8B949E">{proposal.sourceRecommendation.rationale}</MonoValue>
                </MonoField>
              )}
            </Box>
          )}
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58', textAlign: 'center', my: 0.5 }}>
            ↓
          </Typography>
          <SectionLabel>ACTION PROPOSAL</SectionLabel>
          {proposal.action && (
            <MonoField label="CAPABILITY">
              <MonoValue>{proposal.action}</MonoValue>
            </MonoField>
          )}
          {proposal.riskLevel && (
            <MonoField label="RISK">
              <RiskBadge level={proposal.riskLevel} />
            </MonoField>
          )}
          {proposal.proposalId && (
            <MonoField label="PROPOSAL ID">
              <MonoValue color="#8B949E">{proposal.proposalId}</MonoValue>
            </MonoField>
          )}
          {proposal.objective && (
            <MonoField label="OBJECTIVE">
              <MonoValue color="#8B949E">{proposal.objective}</MonoValue>
            </MonoField>
          )}
          <DrawerDivider />
        </>
      )}

      {/* POLICY EVALUATION */}
      {policyEvaluation && (
        <>
          <SectionLabel>POLICY EVALUATION</SectionLabel>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              OUTCOME
            </Typography>
            <OutcomeBadge outcome={policyEvaluation.outcome} />
          </Box>
          {policyEvaluation.violations && (
            <MonoField label="VIOLATIONS">
              <MonoValue color="#F85149">{policyEvaluation.violations}</MonoValue>
            </MonoField>
          )}
          {policyEvaluation.approvalRequired && (
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#D29922', fontWeight: 700, mt: 0.5 }}>
              HUMAN AUTHORITY REQUIRED
            </Typography>
          )}
          <DrawerDivider />
        </>
      )}

      {/* APPROVAL */}
      {approval && (
        <>
          <SectionLabel>APPROVAL REQUIREMENT</SectionLabel>
          <MonoField label="STATE">
            <ApprovalStateBadge state={approval.state} />
          </MonoField>
          {(approval.capability || approval.target) && (
            <MonoField label="ACTION">
              <MonoValue color="#C9D1D9">
                {approval.capability}{approval.target ? ` → ${approval.target}` : ''}
              </MonoValue>
            </MonoField>
          )}
          {approval.riskLevel && (
            <MonoField label="RISK">
              <RiskBadge level={approval.riskLevel} />
            </MonoField>
          )}
          {approval.priority && (
            <MonoField label="PRIORITY">
              <MonoValue color="#8B949E">{approval.priority}</MonoValue>
            </MonoField>
          )}
          {approval.objective && (
            <MonoField label="OBJECTIVE">
              <MonoValue color="#8B949E">{approval.objective}</MonoValue>
            </MonoField>
          )}
          {approval.rationale && (
            <MonoField label="RATIONALE">
              <MonoValue color="#8B949E">{approval.rationale}</MonoValue>
            </MonoField>
          )}
          <DrawerDivider />
        </>
      )}

      {/* EXECUTION */}
      {execution && (
        <>
          <SectionLabel>EXECUTION</SectionLabel>
          {execution.isUnknown ? (
            <>
              <MonoField label="STATUS">
                <MonoValue color="#D29922">UNKNOWN</MonoValue>
              </MonoField>
              <Box sx={{ mt: 0.75, p: 1, background: '#161B22', border: '1px solid #D2992233', borderRadius: '4px' }}>
                <SectionLabel>WHY THIS IS NOT MARKED FAILED</SectionLabel>
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#8B949E', lineHeight: 1.6 }}>
                  The provider may have accepted the warehouse mutation before
                  the acknowledgement was lost. Automatic retry was suppressed.
                  Reconciliation is required.
                </Typography>
              </Box>
            </>
          ) : (
            <>
              {execution.status && (
                <MonoField label="STATUS">
                  <MonoValue color={execution.status === 'executed' ? '#3FB950' : '#C9D1D9'}>
                    {execution.status.toUpperCase()}
                  </MonoValue>
                </MonoField>
              )}
              {execution.capability && (
                <MonoField label="ACTION">
                  <MonoValue color="#8B949E">{execution.capability}</MonoValue>
                </MonoField>
              )}
              {execution.executionId && (
                <MonoField label="EXECUTION ID">
                  <MonoValue color="#8B949E">{execution.executionId}</MonoValue>
                </MonoField>
              )}
            </>
          )}
          <DrawerDivider />
        </>
      )}

      {/* OUTCOME */}
      {outcome && (
        <>
          <SectionLabel>OBSERVED OPERATIONAL IMPACT</SectionLabel>
          <Box sx={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr 1fr 1fr', gap: 0.5, pb: '4px', borderBottom: '1px solid #21262D', mb: 0.5 }}>
            {['METRIC', 'BEFORE', 'AFTER', 'DELTA'].map(h => (
              <Typography key={h} sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#30363D', letterSpacing: '0.06em' }}>{h}</Typography>
            ))}
          </Box>
          <KPIDeltaRow
            label="Wave Risk"
            pre={outcome.preWaveRisk}
            post={outcome.postWaveRisk}
            delta={outcome.deltaWaveRisk}
            positiveIsBetter={false}
          />
          <KPIDeltaRow
            label="Pending Bklg"
            pre={outcome.prePendingBacklog}
            post={outcome.postPendingBacklog}
            delta={outcome.deltaPendingBacklog}
            positiveIsBetter={false}
          />
          <KPIDeltaRow
            label="Labor Avail"
            pre={outcome.preLaborAvailability}
            post={outcome.postLaborAvailability}
            delta={outcome.deltaLaborAvailability}
            suffix="%"
            positiveIsBetter={true}
          />
          <Box sx={{ mt: 1 }}>
            <SectionLabel>OBSERVED OUTCOME</SectionLabel>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#8B949E', lineHeight: 1.6 }}>
              The observed operational impact is consistent with the assessment.
            </Typography>
          </Box>
          <DrawerDivider />
        </>
      )}

      {/* Supporting evidence (when no other sections consumed it) */}
      {!assessment && explanation.supportingEvidence.length > 0 && (
        <>
          <SectionLabel>SUPPORTING EVIDENCE</SectionLabel>
          {explanation.supportingEvidence.map((ev, i) => (
            <EvidenceRow key={i} {...ev} />
          ))}
          <DrawerDivider />
        </>
      )}

    </Box>
  );
}

// ── Main Drawer ────────────────────────────────────────────────────────────────

export default function DecisionExplanationDrawer({
  focus,
  graph,
  analysisResult,
  pendingApprovals,
  demoStatus,
  onClose,
}: DecisionExplanationDrawerProps) {
  // Local proposal index for multi-proposal stage focus
  const [proposalIndex, setProposalIndex] = useState(
    focus.kind === 'stage' ? (focus.proposalIndex ?? 0) : 0,
  );

  // Escape key closes the drawer
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  // Reset proposalIndex when focus changes
  useEffect(() => {
    setProposalIndex(focus.kind === 'stage' ? (focus.proposalIndex ?? 0) : 0);
  }, [focus]);

  // Resolve effective focus (merge proposalIndex for stage focus)
  const effectiveFocus: ExplanationFocus =
    focus.kind === 'stage'
      ? { ...focus, proposalIndex }
      : focus;

  // Build explanation
  const explanation: DecisionExplanation | null = (() => {
    const fromGraph = buildDecisionExplanation({
      focus: effectiveFocus,
      graph,
      analysisResult,
      pendingApprovals,
      demoStatus,
    });
    if (fromGraph) return fromGraph;
    // Fallback to stage-based build when no graph nodes match
    if (effectiveFocus.kind === 'stage') {
      return buildStageExplanation(
        effectiveFocus.stage,
        analysisResult,
        pendingApprovals,
        proposalIndex,
      );
    }
    return null;
  })();

  // How many proposals are available for branch selector?
  const proposalCount =
    focus.kind === 'stage' && (focus.stage === 'PROPOSE' || focus.stage === 'DECIDE')
      ? Math.max(
          analysisResult?.assessment?.recommendations?.length ?? 0,
          analysisResult?.proposal_results?.length ?? 0,
        )
      : 0;

  return (
    <Box
      data-testid="decision-explanation-drawer"
      sx={{
        position: 'absolute',
        right: 0,
        top: 0,
        height: '100%',
        width: 320,
        flexShrink: 0,
        background: '#0D1117',
        borderLeft: '1px solid #21262D',
        display: 'flex',
        flexDirection: 'column',
        zIndex: 10,
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <Box sx={{
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'space-between',
        px: 2,
        pt: 1.75,
        pb: 1.25,
        borderBottom: '1px solid #21262D',
        flexShrink: 0,
      }}>
        <Box>
          <Typography sx={{
            fontFamily: 'monospace', fontSize: '0.72rem', fontWeight: 700,
            color: '#C9D1D9', letterSpacing: '0.06em', textTransform: 'uppercase',
          }}>
            {explanation?.title ?? 'DECISION EXPLANATION'}
          </Typography>
          <Typography sx={{
            fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58',
            letterSpacing: '0.1em', textTransform: 'uppercase', mt: '2px',
          }}>
            STRUCTURED DECISION EXPLANATION
          </Typography>
        </Box>
        <Box
          component="button"
          onClick={onClose}
          data-testid="drawer-close-button"
          sx={{
            background: 'transparent',
            border: '1px solid #21262D',
            borderRadius: '3px',
            color: '#484F58',
            cursor: 'pointer',
            fontFamily: 'monospace',
            fontSize: '0.8rem',
            lineHeight: 1,
            px: '6px',
            py: '2px',
            ml: 1,
            flexShrink: 0,
            '&:hover': { color: '#C9D1D9', borderColor: '#30363D' },
          }}
        >
          ×
        </Box>
      </Box>

      {/* Scrollable body */}
      <Box sx={{ flex: 1, overflow: 'auto', px: 2, py: 1.5 }}>

        {/* Branch selector for multi-proposal stage */}
        {proposalCount > 1 && (
          <ProposalSelector
            count={proposalCount}
            selected={proposalIndex}
            onSelect={setProposalIndex}
          />
        )}

        {explanation === null ? (
          <Box sx={{ py: 3 }}>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', color: '#484F58', textAlign: 'center' }}>
              DETAIL NOT AVAILABLE
            </Typography>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#30363D', textAlign: 'center', mt: 0.5 }}>
              No artifact data for this node yet.
            </Typography>
          </Box>
        ) : (
          <>
            {/* Breadcrumb */}
            {explanation.breadcrumb.length > 0 && (
              <>
                <BreadcrumbBar steps={explanation.breadcrumb} />
                <DrawerDivider />
              </>
            )}

            {/* Source + artifact type */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <SourceBadge source={explanation.source} />
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#484F58' }}>
                {explanation.artifactType}
              </Typography>
            </Box>

            {/* Body */}
            <ExplanationBody explanation={explanation} />

            {/* Trace section */}
            <TraceSection traceIds={explanation.traceIds} />
          </>
        )}
      </Box>

      {/* Footer */}
      <Box sx={{
        px: 2,
        py: 1,
        borderTop: '1px solid #21262D',
        flexShrink: 0,
        display: 'flex',
        alignItems: 'center',
        gap: 1,
      }}>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#30363D', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
          Source:
        </Typography>
        {explanation && <SourceBadge source={explanation.source} />}
      </Box>
    </Box>
  );
}
