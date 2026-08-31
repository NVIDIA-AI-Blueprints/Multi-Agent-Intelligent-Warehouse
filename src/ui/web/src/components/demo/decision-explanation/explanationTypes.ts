/**
 * explanationTypes.ts — types for the "Why This Decision?" contextual artifact inspector (Phase 13D).
 */

import { NodeSource } from '../decision-graph/graphTypes';

export type ExplanationFocus =
  | { kind: 'node'; nodeId: string }
  | { kind: 'stage'; stage: 'PROPOSE' | 'DECIDE' | 'APPROVE' | 'OUTCOME'; proposalIndex?: number };

export interface ExplanationEvidence {
  label: string;
  value: string | number;
  suffix?: string;
  source: NodeSource;
}

export interface ExplanationAssessment {
  summary: string;
  severity: string;
  snapshotId?: string | null;
  supportingEvidence: ExplanationEvidence[];
  modelId?: string | null;
  routingRule?: string | null;
  routingReason?: string | null;
  latencyMs?: number | null;
}

export interface ExplanationRecommendation {
  capability: string;
  target?: string | null;
  rationale?: string | null;
  priority?: string | null;
  domain?: string | null;
}

export interface ExplanationProposal {
  proposalId?: string | null;
  action?: string | null;
  riskLevel?: string | null;
  objective?: string | null;
  sourceRecommendation?: ExplanationRecommendation;
}

export interface ExplanationPolicy {
  outcome: string;
  riskLevel?: string | null;
  violations?: string | null;
  decisionId?: string | null;
  proposalId?: string | null;
  approvalRequired: boolean;
}

export interface ExplanationApproval {
  pendingId?: string | null;
  proposalId?: string | null;
  decisionId?: string | null;
  capability?: string | null;
  target?: string | null;
  riskLevel?: string | null;
  objective?: string | null;
  rationale?: string | null;
  priority?: string | null;
  queuedAt?: string | null;
  state: 'PENDING' | 'APPROVED' | 'REJECTED' | 'EXPIRED' | 'CONSUMED' | 'UNKNOWN';
}

export interface ExplanationExecution {
  executionId?: string | null;
  status?: string | null;
  capability?: string | null;
  proposalId?: string | null;
  isUnknown: boolean;
}

export interface ExplanationOutcome {
  preWaveRisk?: number | null;
  postWaveRisk?: number | null;
  deltaWaveRisk?: number | null;
  prePendingBacklog?: number | null;
  postPendingBacklog?: number | null;
  deltaPendingBacklog?: number | null;
  preLaborAvailability?: number | null;
  postLaborAvailability?: number | null;
  deltaLaborAvailability?: number | null;
}

export interface ExplanationTraceIds {
  traceId?: string | null;
  snapshotId?: string | null;
  proposalId?: string | null;
  decisionId?: string | null;
  approvalId?: string | null;
  executionId?: string | null;
}

export interface DecisionExplanation {
  title: string;
  artifactType: string;
  source: NodeSource;
  summary?: string;
  supportingEvidence: ExplanationEvidence[];
  assessment?: ExplanationAssessment;
  recommendation?: ExplanationRecommendation;
  proposal?: ExplanationProposal;
  policyEvaluation?: ExplanationPolicy;
  approval?: ExplanationApproval;
  execution?: ExplanationExecution;
  outcome?: ExplanationOutcome;
  /** e.g. ['Evidence', 'Assessment', 'Recommendation', 'Proposal', 'Decision'] */
  breadcrumb: string[];
  traceIds: ExplanationTraceIds;
}
