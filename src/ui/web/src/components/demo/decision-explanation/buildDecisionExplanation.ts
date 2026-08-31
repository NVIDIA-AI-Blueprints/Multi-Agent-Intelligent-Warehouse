/**
 * buildDecisionExplanation.ts — pure function that builds a DecisionExplanation
 * from a focused node/stage and the current runtime data (Phase 13D).
 *
 * No React. No side effects. Safe to unit-test without a DOM.
 * Does NOT call any AI model or expose chain-of-thought fields.
 */

import {
  DecisionGraph,
  DecisionGraphNode,
  DecisionGraphNodeType,
} from '../decision-graph/graphTypes';
import {
  AnalysisResult,
  PendingApproval,
  DemoStatus,
} from '../../../services/demoAPI';
import {
  ExplanationFocus,
  DecisionExplanation,
  ExplanationEvidence,
  ExplanationRecommendation,
  ExplanationProposal,
  ExplanationPolicy,
  ExplanationApproval,
  ExplanationExecution,
  ExplanationOutcome,
  ExplanationAssessment,
  ExplanationTraceIds,
} from './explanationTypes';

export interface BuildExplanationParams {
  focus: ExplanationFocus;
  graph: DecisionGraph;
  analysisResult: AnalysisResult | null;
  pendingApprovals: PendingApproval[];
  demoStatus: DemoStatus | null;
}

export function buildDecisionExplanation(params: BuildExplanationParams): DecisionExplanation | null {
  const { focus, graph, analysisResult, pendingApprovals } = params;

  // Resolve which node to explain
  let targetNode: DecisionGraphNode | null = null;

  if (focus.kind === 'node') {
    targetNode = graph.nodes.find(n => n.id === focus.nodeId) ?? null;
  } else {
    // Stage-based: find the most representative node
    const stageNodeTypeMap: Record<string, DecisionGraphNodeType[]> = {
      PROPOSE: ['recommendation', 'proposal'],
      DECIDE: ['decision', 'decision_engine'],
      APPROVE: ['approval'],
      OUTCOME: ['outcome'],
    };
    const types = stageNodeTypeMap[focus.stage] ?? [];
    const idx = focus.proposalIndex ?? 0;
    for (const t of types) {
      const found = graph.nodes.filter(n => n.type === t);
      if (found.length > 0) {
        targetNode = found[Math.min(idx, found.length - 1)];
        break;
      }
    }
  }

  if (!targetNode) return null;

  // Helper to build evidence from KPI evidence nodes
  function getKpiEvidence(): ExplanationEvidence[] {
    return graph.nodes
      .filter(n => n.type === 'evidence' && n.metadata?.source_field === 'current_kpis')
      .map(n => {
        const meta = n.metadata ?? {};
        const key = Object.keys(meta).find(k => k !== 'source_field') ?? '';
        const val = key ? meta[key] : null;
        return {
          label: n.label,
          value: val != null ? val : '—',
          source: n.source,
        } as ExplanationEvidence;
      });
  }

  function getFactsEvidence(): ExplanationEvidence[] {
    const facts = analysisResult?.assessment?.facts_observed ?? [];
    return facts.slice(0, 3).map(f => ({
      label: 'Observed',
      value: f,
      source: 'LIVE' as const,
    }));
  }

  function getAssessmentExplanation(): ExplanationAssessment | undefined {
    const assess = analysisResult?.assessment;
    if (!assess) return undefined;
    return {
      summary: assess.summary,
      severity: assess.severity,
      snapshotId: assess.snapshot_id,
      supportingEvidence: [...getKpiEvidence(), ...getFactsEvidence()],
      modelId: assess.model_id,
      routingRule: assess.routing_rule,
      routingReason: assess.routing_reason,
      latencyMs: assess.latency_ms,
    };
  }

  function getRecommendationByIndex(idx: number): ExplanationRecommendation | undefined {
    const recs = analysisResult?.assessment?.recommendations ?? [];
    const rec = recs[idx];
    if (!rec) return undefined;
    return {
      capability: rec.capability,
      target: rec.target ?? null,
      rationale: rec.rationale ?? null,
      priority: rec.priority ?? null,
      domain: rec.domain ?? null,
    };
  }

  function getRecommendationFromNode(node: DecisionGraphNode): ExplanationRecommendation | undefined {
    const m = node.metadata ?? {};
    if (!m.capability) return undefined;
    return {
      capability: String(m.capability),
      target: m.target != null ? String(m.target) : null,
      rationale: m.rationale != null ? String(m.rationale) : null,
      priority: m.priority != null ? String(m.priority) : null,
      domain: m.domain != null ? String(m.domain) : null,
    };
  }

  function getProposalFromNode(node: DecisionGraphNode): ExplanationProposal | undefined {
    const m = node.metadata ?? {};
    if (!m.proposal_id && !m.action) return undefined;
    const idx = m.index != null ? Number(m.index) : 0;
    const sourceRec = getRecommendationByIndex(idx);
    const pa = pendingApprovals.find(p => p.proposal_id === m.proposal_id);
    return {
      proposalId: m.proposal_id != null ? String(m.proposal_id) : null,
      action: m.action != null ? String(m.action) : null,
      riskLevel: m.risk_level != null ? String(m.risk_level) : null,
      objective: pa?.objective ?? null,
      sourceRecommendation: sourceRec,
    };
  }

  function getPolicyFromDecisionNode(node: DecisionGraphNode): ExplanationPolicy | undefined {
    const m = node.metadata ?? {};
    const outcome = m.outcome ?? m.status;
    if (!outcome) return undefined;
    return {
      outcome: String(outcome),
      riskLevel: null,
      violations: m.violations != null ? String(m.violations) : null,
      decisionId: m.decision_id != null ? String(m.decision_id) : null,
      proposalId: m.proposal_id != null ? String(m.proposal_id) : null,
      approvalRequired: String(outcome) === 'REQUIRES_HUMAN_APPROVAL',
    };
  }

  function getApprovalFromNode(node: DecisionGraphNode): ExplanationApproval | undefined {
    const m = node.metadata ?? {};
    const pid = m.pending_id != null ? String(m.pending_id) : null;
    const pa = pid ? pendingApprovals.find(p => p.pending_id === pid) : null;
    let state: ExplanationApproval['state'] = 'PENDING';
    if (pa) {
      const ageMs = pa.queued_at ? Date.now() - new Date(pa.queued_at).getTime() : 0;
      if (ageMs > 10 * 60 * 1000) state = 'EXPIRED';
    } else {
      const pr = analysisResult?.proposal_results?.find(
        p => p.proposal_id === (m.proposal_id != null ? String(m.proposal_id) : null),
      );
      if (pr) {
        if (pr.status === 'EXECUTED' || pr.status === 'APPROVED') state = 'CONSUMED';
        else if (pr.status === 'REJECTED') state = 'REJECTED';
        else state = 'UNKNOWN';
      } else {
        state = 'UNKNOWN';
      }
    }
    return {
      pendingId: pid,
      proposalId: m.proposal_id != null ? String(m.proposal_id) : null,
      decisionId: m.decision_id != null ? String(m.decision_id) : null,
      capability: pa?.capability ?? (m.capability != null ? String(m.capability) : null),
      target: pa?.target ?? (m.target != null ? String(m.target) : null),
      riskLevel: pa?.risk_level ?? (m.risk_level != null ? String(m.risk_level) : null),
      objective: pa?.objective ?? null,
      rationale: pa?.rationale ?? null,
      priority: pa?.priority ?? (m.priority != null ? String(m.priority) : null),
      queuedAt: pa?.queued_at ?? (m.queued_at != null ? String(m.queued_at) : null),
      state,
    };
  }

  function getExecutionFromNode(node: DecisionGraphNode): ExplanationExecution | undefined {
    const m = node.metadata ?? {};
    const status = m.status != null ? String(m.status) : null;
    return {
      executionId: m.execution_id != null ? String(m.execution_id) : null,
      status,
      capability: m.capability != null ? String(m.capability) : null,
      proposalId: m.proposal_id != null ? String(m.proposal_id) : null,
      isUnknown: status === 'UNKNOWN' || status === 'unknown',
    };
  }

  function getOutcomeFromNode(node: DecisionGraphNode): ExplanationOutcome {
    const m = node.metadata ?? {};
    return {
      preWaveRisk: m.pre_wave_risk_score != null ? Number(m.pre_wave_risk_score) : null,
      postWaveRisk: m.post_wave_risk_score != null ? Number(m.post_wave_risk_score) : null,
      deltaWaveRisk: m.delta_wave_risk_score != null ? Number(m.delta_wave_risk_score) : null,
      prePendingBacklog: m.pre_pending_backlog != null ? Number(m.pre_pending_backlog) : null,
      postPendingBacklog: m.post_pending_backlog != null ? Number(m.post_pending_backlog) : null,
      deltaPendingBacklog: m.delta_pending_backlog != null ? Number(m.delta_pending_backlog) : null,
      preLaborAvailability: m.pre_labor_availability_pct != null ? Number(m.pre_labor_availability_pct) : null,
      postLaborAvailability: m.post_labor_availability_pct != null ? Number(m.post_labor_availability_pct) : null,
      deltaLaborAvailability: m.delta_labor_availability_pct != null ? Number(m.delta_labor_availability_pct) : null,
    };
  }

  function buildTraceIds(node: DecisionGraphNode): ExplanationTraceIds {
    const m = node.metadata ?? {};
    return {
      traceId: analysisResult?.trace_id ?? null,
      snapshotId: m.snapshot_id != null ? String(m.snapshot_id) : (analysisResult?.assessment?.snapshot_id ?? null),
      proposalId: m.proposal_id != null ? String(m.proposal_id) : null,
      decisionId: m.decision_id != null ? String(m.decision_id) : null,
      approvalId: m.pending_id != null ? String(m.pending_id) : null,
      executionId: m.execution_id != null ? String(m.execution_id) : null,
    };
  }

  const BREADCRUMBS: Partial<Record<DecisionGraphNodeType, string[]>> = {
    evidence:         ['Evidence'],
    agent:            ['Evidence', 'Intelligence'],
    model_gateway:    ['Evidence', 'Intelligence'],
    model:            ['Evidence', 'Intelligence'],
    skill:            ['Evidence', 'Intelligence'],
    assessment:       ['Evidence', 'Assessment'],
    recommendation:   ['Evidence', 'Assessment', 'Recommendation'],
    proposal:         ['Evidence', 'Assessment', 'Recommendation', 'Proposal'],
    decision_engine:  ['Proposal', 'Decision'],
    decision:         ['Proposal', 'Decision'],
    approval:         ['Proposal', 'Decision', 'Approval'],
    executor:         ['Approval', 'Execution'],
    mcp:              ['Approval', 'Execution'],
    execution:        ['Proposal', 'Decision', 'Approval', 'Execution'],
    reconciliation:   ['Proposal', 'Decision', 'Approval', 'Execution', 'Reconciliation'],
    outcome:          ['Proposal', 'Decision', 'Approval', 'Execution', 'Outcome'],
  };

  const node = targetNode;
  const meta = node.metadata ?? {};

  switch (node.type) {
    case 'evidence': {
      const factVal = meta.fact;
      const kpiKey = Object.keys(meta).find(k => k !== 'source_field');
      const kpiVal = kpiKey ? meta[kpiKey] : null;
      return {
        title: 'WHY THIS EVIDENCE?',
        artifactType: 'Evidence',
        source: node.source,
        summary: factVal != null ? String(factVal) : (kpiVal != null ? `${node.label}: ${kpiVal}` : node.label),
        supportingEvidence: [],
        breadcrumb: BREADCRUMBS.evidence ?? [],
        traceIds: buildTraceIds(node),
      };
    }

    case 'assessment': {
      const assess = getAssessmentExplanation();
      return {
        title: 'WHY THIS ASSESSMENT?',
        artifactType: 'Assessment',
        source: node.source,
        summary: assess?.summary,
        supportingEvidence: assess?.supportingEvidence ?? [],
        assessment: assess,
        breadcrumb: BREADCRUMBS.assessment ?? [],
        traceIds: buildTraceIds(node),
      };
    }

    case 'recommendation': {
      const rec = getRecommendationFromNode(node);
      return {
        title: 'WHY THIS RECOMMENDATION?',
        artifactType: 'Recommendation',
        source: node.source,
        summary: rec?.rationale ?? rec?.capability,
        supportingEvidence: getKpiEvidence(),
        recommendation: rec,
        breadcrumb: BREADCRUMBS.recommendation ?? [],
        traceIds: buildTraceIds(node),
      };
    }

    case 'proposal': {
      const proposal = getProposalFromNode(node);
      return {
        title: 'WHY THIS PROPOSAL?',
        artifactType: 'ActionProposal',
        source: node.source,
        summary: proposal?.action ?? proposal?.proposalId ?? undefined,
        supportingEvidence: [],
        recommendation: proposal?.sourceRecommendation,
        proposal,
        breadcrumb: BREADCRUMBS.proposal ?? [],
        traceIds: buildTraceIds(node),
      };
    }

    case 'decision_engine':
    case 'decision': {
      const policy = getPolicyFromDecisionNode(node);
      const propNode = policy?.proposalId
        ? graph.nodes.find(n => n.type === 'proposal' && n.metadata?.proposal_id === policy.proposalId)
        : null;
      const proposal = propNode ? getProposalFromNode(propNode) : undefined;
      return {
        title: 'WHY THIS DECISION?',
        artifactType: 'Decision',
        source: node.source,
        summary: policy ? `Outcome: ${policy.outcome}` : undefined,
        supportingEvidence: getKpiEvidence(),
        proposal,
        policyEvaluation: policy ?? undefined,
        breadcrumb: BREADCRUMBS.decision ?? [],
        traceIds: buildTraceIds(node),
      };
    }

    case 'approval': {
      const approval = getApprovalFromNode(node);
      const policy = approval?.decisionId
        ? (() => {
            const dn = graph.nodes.find(n => n.type === 'decision' && n.metadata?.decision_id === approval.decisionId);
            return dn ? getPolicyFromDecisionNode(dn) : undefined;
          })()
        : undefined;
      return {
        title: 'WHY IS APPROVAL REQUIRED?',
        artifactType: 'Approval',
        source: node.source,
        summary: approval?.objective ?? (approval?.capability ? `${approval.capability} → ${approval.target}` : undefined),
        supportingEvidence: [],
        policyEvaluation: policy ?? undefined,
        approval,
        breadcrumb: BREADCRUMBS.approval ?? [],
        traceIds: buildTraceIds(node),
      };
    }

    case 'execution': {
      const exec = getExecutionFromNode(node);
      return {
        title: 'WHAT EXECUTED?',
        artifactType: 'Execution',
        source: node.source,
        summary: exec?.capability ?? undefined,
        supportingEvidence: [],
        execution: exec,
        breadcrumb: BREADCRUMBS.execution ?? [],
        traceIds: buildTraceIds(node),
      };
    }

    case 'reconciliation': {
      const execNode = graph.nodes.find(n => n.type === 'execution' && n.metadata?.execution_id === meta.execution_id);
      const exec = execNode
        ? getExecutionFromNode(execNode)
        : { isUnknown: true, executionId: meta.execution_id != null ? String(meta.execution_id) : null };
      return {
        title: 'WHY RECONCILIATION?',
        artifactType: 'Reconciliation',
        source: node.source,
        summary: 'Original execution outcome was UNKNOWN. Automatic retry was suppressed.',
        supportingEvidence: [],
        execution: exec as ExplanationExecution,
        breadcrumb: BREADCRUMBS.reconciliation ?? [],
        traceIds: buildTraceIds(node),
      };
    }

    case 'outcome': {
      const outcome = getOutcomeFromNode(node);
      return {
        title: 'WHY THIS OUTCOME?',
        artifactType: 'Outcome',
        source: node.source,
        summary: 'Observed operational impact after execution.',
        supportingEvidence: [],
        outcome,
        breadcrumb: BREADCRUMBS.outcome ?? [],
        traceIds: buildTraceIds(node),
      };
    }

    default: {
      // DERIVED nodes (agent, model_gateway, model, skill, executor, mcp)
      return {
        title: node.label,
        artifactType: node.type,
        source: node.source,
        summary: node.subtitle ?? undefined,
        supportingEvidence: [],
        breadcrumb: BREADCRUMBS[node.type as DecisionGraphNodeType] ?? [],
        traceIds: buildTraceIds(node),
      };
    }
  }
}

// For stage-based focus without needing graph nodes (fallback)
export function buildStageExplanation(
  stage: 'PROPOSE' | 'DECIDE' | 'APPROVE' | 'OUTCOME',
  analysisResult: AnalysisResult | null,
  pendingApprovals: PendingApproval[],
  proposalIndex: number = 0,
): DecisionExplanation | null {
  if (!analysisResult) return null;
  const { assessment } = analysisResult;

  if (stage === 'PROPOSE') {
    const rec = assessment?.recommendations?.[proposalIndex];
    if (!rec) return null;
    const prec: ExplanationRecommendation = {
      capability: rec.capability,
      target: rec.target ?? null,
      rationale: rec.rationale ?? null,
      priority: rec.priority ?? null,
      domain: rec.domain ?? null,
    };
    const pr = analysisResult.proposal_results?.[proposalIndex];
    const pa = pr?.proposal_id ? pendingApprovals.find(p => p.proposal_id === pr.proposal_id) : null;
    const proposal: ExplanationProposal = {
      proposalId: pr?.proposal_id ?? null,
      action: pr?.action ?? rec.capability,
      riskLevel: pr?.risk_level ?? null,
      objective: pa?.objective ?? null,
      sourceRecommendation: prec,
    };
    return {
      title: 'WHY THIS RECOMMENDATION?',
      artifactType: 'Recommendation',
      source: 'LIVE',
      summary: rec.rationale ?? rec.capability,
      supportingEvidence: (assessment?.facts_observed ?? []).slice(0, 3).map(f => ({
        label: 'Observed', value: f, source: 'LIVE' as const,
      })),
      recommendation: prec,
      proposal,
      breadcrumb: ['Evidence', 'Assessment', 'Recommendation', 'Proposal'],
      traceIds: { traceId: analysisResult.trace_id, snapshotId: assessment?.snapshot_id ?? null, proposalId: pr?.proposal_id ?? null },
    };
  }

  if (stage === 'DECIDE') {
    const pr = analysisResult.proposal_results?.[proposalIndex];
    if (!pr) return null;
    const policy: ExplanationPolicy = {
      outcome: pr.status ?? 'UNKNOWN',
      riskLevel: pr.risk_level ?? null,
      violations: null,
      decisionId: pr.decision_id ?? null,
      proposalId: pr.proposal_id ?? null,
      approvalRequired: pr.status === 'REQUIRES_HUMAN_APPROVAL',
    };
    return {
      title: 'WHY THIS DECISION?',
      artifactType: 'Decision',
      source: 'LIVE',
      summary: `Outcome: ${pr.status}`,
      supportingEvidence: (assessment?.facts_observed ?? []).slice(0, 2).map(f => ({
        label: 'Observed', value: f, source: 'LIVE' as const,
      })),
      policyEvaluation: policy,
      breadcrumb: ['Proposal', 'Decision'],
      traceIds: { traceId: analysisResult.trace_id, proposalId: pr.proposal_id ?? null, decisionId: pr.decision_id ?? null },
    };
  }

  if (stage === 'APPROVE') {
    const pa = pendingApprovals[proposalIndex];
    if (!pa) return null;
    const approval: ExplanationApproval = {
      pendingId: pa.pending_id,
      proposalId: pa.proposal_id,
      decisionId: pa.decision_id,
      capability: pa.capability,
      target: pa.target,
      riskLevel: pa.risk_level,
      objective: pa.objective,
      rationale: pa.rationale,
      priority: pa.priority,
      queuedAt: pa.queued_at,
      state: 'PENDING',
    };
    return {
      title: 'WHY IS APPROVAL REQUIRED?',
      artifactType: 'Approval',
      source: 'LIVE',
      summary: pa.objective,
      supportingEvidence: [],
      approval,
      breadcrumb: ['Proposal', 'Decision', 'Approval'],
      traceIds: { traceId: pa.trace_id, proposalId: pa.proposal_id, decisionId: pa.decision_id, approvalId: pa.pending_id },
    };
  }

  if (stage === 'OUTCOME') {
    const outcome: ExplanationOutcome = {
      preWaveRisk: analysisResult.pre_kpis?.wave_risk_score ?? null,
      postWaveRisk: analysisResult.post_kpis?.wave_risk_score ?? null,
      deltaWaveRisk: analysisResult.kpi_delta?.wave_risk_score ?? null,
      prePendingBacklog: analysisResult.pre_kpis?.pending_backlog ?? null,
      postPendingBacklog: analysisResult.post_kpis?.pending_backlog ?? null,
      deltaPendingBacklog: analysisResult.kpi_delta?.pending_backlog ?? null,
      preLaborAvailability: analysisResult.pre_kpis?.labor_availability_pct ?? null,
      postLaborAvailability: analysisResult.post_kpis?.labor_availability_pct ?? null,
      deltaLaborAvailability: analysisResult.kpi_delta?.labor_availability_pct ?? null,
    };
    return {
      title: 'WHY DID THIS CHANGE?',
      artifactType: 'Outcome',
      source: 'LIVE',
      summary: 'Observed operational impact after execution.',
      supportingEvidence: [],
      outcome,
      breadcrumb: ['Proposal', 'Decision', 'Approval', 'Execution', 'Outcome'],
      traceIds: { traceId: analysisResult.trace_id },
    };
  }

  return null;
}
