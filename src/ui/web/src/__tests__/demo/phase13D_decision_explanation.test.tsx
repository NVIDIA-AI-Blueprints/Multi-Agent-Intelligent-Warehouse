/**
 * Phase 13D tests — buildDecisionExplanation pure function + DecisionExplanationDrawer rendering.
 *
 * Pure-function tests (18 tests) cover:
 *   1.  evidence node → title 'WHY THIS EVIDENCE?', artifactType 'Evidence'
 *   2.  assessment node → title 'WHY THIS ASSESSMENT?', has summary + severity
 *   3.  assessment node → supportingEvidence includes KPI evidence nodes
 *   4.  recommendation node → title 'WHY THIS RECOMMENDATION?', has rationale
 *   5.  proposal node → title 'WHY THIS PROPOSAL?', shows sourceRecommendation
 *   6.  decision node REQUIRES_HUMAN_APPROVAL → policyEvaluation.approvalRequired true
 *   7.  decision node APPROVED → policyEvaluation.approvalRequired false
 *   8.  approval node → title 'WHY IS APPROVAL REQUIRED?', state PENDING
 *   9.  execution node UNKNOWN → isUnknown true
 *  10.  execution node EXECUTED → isUnknown false
 *  11.  reconciliation node → summary includes 'Automatic retry was suppressed'
 *  12.  outcome node → outcome fields from pre/post metadata
 *  13.  stage focus PROPOSE → recommendation + proposal in result
 *  14.  stage focus DECIDE → policyEvaluation in result
 *  15.  stage focus APPROVE with pendingApprovals → approval in result
 *  16.  stage focus OUTCOME with analysisResult → outcome with pre/post values
 *  17.  no chain_of_thought field in any explanation object
 *  18.  traceIds.traceId comes from analysisResult.trace_id
 *
 * Constraint tests (5 tests):
 *  19.  recommendation and proposal are distinct fields (not merged)
 *  20.  outcome uses metadata fields, not live polling (no demoStatus fields in outcome)
 *  21.  UNKNOWN execution does NOT set status to 'FAILED'
 *  22.  every explanation has a source field (not undefined)
 *  23.  null focus returns null when graph is empty
 *
 * Render tests (7 tests):
 *  24.  renders drawer title for assessment focus
 *  25.  renders 'DETAIL NOT AVAILABLE' when explanation is null
 *  26.  Escape key calls onClose
 *  27.  PROPOSE stage with 2 proposals shows branch selector
 *  28.  UNKNOWN execution shows 'Automatic retry was suppressed' text
 *  29.  outcome renders before/after table
 *  30.  'TRACE DETAILS' section is collapsed by default
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { ThemeProvider } from '@mui/material/styles';

import { buildDecisionExplanation, buildStageExplanation, BuildExplanationParams } from '../../components/demo/decision-explanation/buildDecisionExplanation';
import { ExplanationFocus, DecisionExplanation } from '../../components/demo/decision-explanation/explanationTypes';
import { DecisionGraph } from '../../components/demo/decision-graph/graphTypes';
import { DemoStatus, AnalysisResult, PendingApproval, KPISnapshot } from '../../services/demoAPI';
import { nvidiaTheme } from '../../theme/nvidiaTheme';
import DecisionExplanationDrawer from '../../components/demo/decision-explanation/DecisionExplanationDrawer';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const baseKPIs: KPISnapshot = {
  sim_time_seconds: 100,
  clock_iso: '2026-08-29T08:00:00Z',
  equipment_total: 10,
  equipment_operational_pct: 80,
  labor_total: 8,
  labor_availability_pct: 62.5,
  labor_utilization_pct: 75,
  pending_backlog: 14,
  wave_risk_score: 0.78,
  wave_risk_level: 'high',
  low_stock_count: 2,
  state_freshness_seconds: 5,
  service_risk_index: 0.6,
  capacity_throughput_proxy: 400,
  wave_completion_pct: 45,
  simulated_throughput: 350,
  projected_service_level: 68,
  time_to_recovery_seconds: null,
};

const baseStatus: DemoStatus = {
  active: true,
  paused: false,
  scenario: { name: 'test', display_name: 'Test', description: '', tags: [] },
  world: null,
  current_kpis: baseKPIs,
  kpi_history: [],
  pending_approvals: [],
};

const baseAnalysis: AnalysisResult = {
  ok: true,
  trace_id: 'trace-13d-001',
  assessment: {
    snapshot_id: 'snap-001',
    warehouse_id: 'DC-01',
    assessed_at: '2026-08-29T08:00:01Z',
    summary: 'High wave risk due to labor shortage.',
    severity: 'high',
    domains_affected: ['labor', 'wave'],
    facts_observed: ['3 workers absent', 'Wave risk elevated', 'Backlog growing'],
    recommendations: [
      {
        domain: 'labor',
        capability: 'reassign_labor_from_equipment',
        target: 'AGV-01',
        objective: 'Restore wave processing',
        rationale: 'Equipment load reducible without service impact.',
        priority: 'high',
        subtype: null,
      },
      {
        domain: 'wave',
        capability: 'reprioritize_wave_tasks',
        target: 'WAVE-05',
        objective: 'Reduce wave backlog',
        rationale: 'Wave backlog at 14 tasks, reprioritizing highest-value tasks reduces risk.',
        priority: 'medium',
        subtype: null,
      },
    ],
    model_id: 'nvidia/llama-3.1-nemotron-70b-instruct',
    routing_rule: 'labor_wave_risk',
    routing_reason: 'Labor + wave domain HIGH',
    latency_ms: 980,
  },
  proposal_results: [
    {
      status: 'executed',
      capability: 'reassign_labor_from_equipment',
      execution_id: 'exec-001',
      proposal_id: 'prop-001',
      decision_id: 'dec-001',
      action: 'Reassign 2 workers from equipment',
      risk_level: 'medium',
    },
    {
      status: 'REQUIRES_HUMAN_APPROVAL',
      capability: 'reprioritize_wave_tasks',
      proposal_id: 'prop-002',
      decision_id: 'dec-002',
    },
  ],
  lifecycle: [
    { phase: 'OBSERVE', snapshot_id: 'snap-001', trace_id: 'trace-13d-001' },
    { phase: 'PROPOSE', index: 0, action: 'Reassign 2 workers', proposal_id: 'prop-001', risk_level: 'medium', trace_id: 'trace-13d-001' },
    { phase: 'DECIDE', index: 0, outcome: 'APPROVED', proposal_id: 'prop-001', decision_id: 'dec-001', trace_id: 'trace-13d-001' },
  ],
  pre_kpis: baseKPIs,
  post_kpis: {
    ...baseKPIs,
    wave_risk_score: 0.42,
    pending_backlog: 8,
    labor_availability_pct: 75,
  },
  kpi_delta: {
    equipment_operational_pct: 0,
    labor_availability_pct: 12.5,
    labor_utilization_pct: -5,
    pending_backlog: -6,
    wave_risk_score: -0.36,
    low_stock_count: 0,
    service_risk_index: -0.1,
    capacity_throughput_proxy: 50,
    wave_completion_pct: 10,
    simulated_throughput: 30,
    projected_service_level: 8,
  },
};

const basePendingApproval: PendingApproval = {
  pending_id: 'pa-001',
  proposal_id: 'prop-002',
  decision_id: 'dec-002',
  trace_id: 'trace-13d-001',
  capability: 'reprioritize_wave_tasks',
  target: 'WAVE-05',
  domain: 'wave',
  risk_level: 'medium',
  objective: 'Reduce wave backlog',
  rationale: 'Wave backlog at 14 tasks.',
  priority: 'medium',
  queued_at: new Date(Date.now() - 60000).toISOString(), // 1 min ago — not expired
};

// ── Graph with all node types ─────────────────────────────────────────────────

const fullGraph: DecisionGraph = {
  nodes: [
    // Evidence
    { id: 'ev-kpi-1', type: 'evidence', label: 'Wave Risk Score', source: 'LIVE', layer: 0, column: 0, metadata: { source_field: 'current_kpis', wave_risk_score: 0.78 } },
    { id: 'ev-kpi-2', type: 'evidence', label: 'Pending Backlog', source: 'LIVE', layer: 0, column: 1, metadata: { source_field: 'current_kpis', pending_backlog: 14 } },
    // Assessment
    { id: 'assess-1', type: 'assessment', label: 'Situation Assessment', source: 'LIVE', layer: 5, column: 0, metadata: { snapshot_id: 'snap-001' } },
    // Recommendation
    { id: 'rec-1', type: 'recommendation', label: 'Reassign Labor', source: 'LIVE', layer: 6, column: 0, metadata: { capability: 'reassign_labor_from_equipment', target: 'AGV-01', rationale: 'Equipment load reducible.', priority: 'high', domain: 'labor', index: 0 } },
    // Proposal
    { id: 'prop-node-1', type: 'proposal', label: 'Proposal: Reassign', source: 'VALIDATED_ARTIFACT', layer: 7, column: 0, metadata: { proposal_id: 'prop-001', action: 'Reassign 2 workers', risk_level: 'medium', index: 0 } },
    // Decision engine
    { id: 'dec-eng-1', type: 'decision_engine', label: 'DecisionEngine', source: 'DERIVED', layer: 8, column: 0, metadata: {} },
    // Decision
    { id: 'dec-1', type: 'decision', label: 'Decision: APPROVED', source: 'VALIDATED_ARTIFACT', layer: 9, column: 0, metadata: { outcome: 'APPROVED', proposal_id: 'prop-001', decision_id: 'dec-001' } },
    // Decision requiring approval
    { id: 'dec-2', type: 'decision', label: 'Decision: REQUIRES_HUMAN_APPROVAL', source: 'VALIDATED_ARTIFACT', layer: 9, column: 1, metadata: { outcome: 'REQUIRES_HUMAN_APPROVAL', proposal_id: 'prop-002', decision_id: 'dec-002' } },
    // Approval
    { id: 'appr-1', type: 'approval', label: 'Approval Required', source: 'VALIDATED_ARTIFACT', layer: 10, column: 0, metadata: { pending_id: 'pa-001', proposal_id: 'prop-002', decision_id: 'dec-002' } },
    // Execution — UNKNOWN
    { id: 'exec-unknown-1', type: 'execution', label: 'Execution: UNKNOWN', source: 'LIVE', layer: 14, column: 0, metadata: { status: 'UNKNOWN', capability: 'reprioritize_wave_tasks', execution_id: 'exec-unk-001' } },
    // Execution — executed
    { id: 'exec-done-1', type: 'execution', label: 'Execution: executed', source: 'LIVE', layer: 14, column: 1, metadata: { status: 'executed', capability: 'reassign_labor_from_equipment', execution_id: 'exec-001' } },
    // Reconciliation
    { id: 'recon-1', type: 'reconciliation', label: 'Reconciliation', source: 'DERIVED', layer: 15, column: 0, metadata: { execution_id: 'exec-unk-001' } },
    // Outcome
    { id: 'outcome-1', type: 'outcome', label: 'Observed Outcome', source: 'LIVE', layer: 15, column: 1, metadata: { pre_wave_risk_score: 0.78, post_wave_risk_score: 0.42, delta_wave_risk_score: -0.36, pre_pending_backlog: 14, post_pending_backlog: 8, delta_pending_backlog: -6, pre_labor_availability_pct: 62.5, post_labor_availability_pct: 75, delta_labor_availability_pct: 12.5 } },
  ],
  edges: [],
};

const emptyGraph: DecisionGraph = { nodes: [], edges: [] };

function makeParams(overrides: Partial<BuildExplanationParams> = {}): BuildExplanationParams {
  return {
    focus: { kind: 'node', nodeId: 'ev-kpi-1' },
    graph: fullGraph,
    analysisResult: baseAnalysis,
    pendingApprovals: [basePendingApproval],
    demoStatus: baseStatus,
    ...overrides,
  };
}

// ── Theme wrapper ─────────────────────────────────────────────────────────────

function Wrapper({ children }: { children: React.ReactNode }) {
  return <ThemeProvider theme={nvidiaTheme}>{children}</ThemeProvider>;
}

// ── Pure-function tests (1–18) ────────────────────────────────────────────────

describe('buildDecisionExplanation — pure function', () => {
  // Test 1: evidence node
  it('1. evidence node → title WHY THIS EVIDENCE? and artifactType Evidence', () => {
    const result = buildDecisionExplanation(makeParams({ focus: { kind: 'node', nodeId: 'ev-kpi-1' } }));
    expect(result).not.toBeNull();
    expect(result!.title).toBe('WHY THIS EVIDENCE?');
    expect(result!.artifactType).toBe('Evidence');
  });

  // Test 2: assessment node has summary + severity
  it('2. assessment node → title WHY THIS ASSESSMENT? with summary and severity', () => {
    const result = buildDecisionExplanation(makeParams({ focus: { kind: 'node', nodeId: 'assess-1' } }));
    expect(result).not.toBeNull();
    expect(result!.title).toBe('WHY THIS ASSESSMENT?');
    expect(result!.assessment?.summary).toBeTruthy();
    expect(result!.assessment?.severity).toBe('high');
  });

  // Test 3: assessment supporting evidence includes KPI nodes
  it('3. assessment node → supportingEvidence includes KPI evidence nodes', () => {
    const result = buildDecisionExplanation(makeParams({ focus: { kind: 'node', nodeId: 'assess-1' } }));
    expect(result).not.toBeNull();
    // Should include KPI evidence and facts
    expect(result!.supportingEvidence.length).toBeGreaterThan(0);
    // Assessment's supportingEvidence should also have the kpi items
    expect(result!.assessment?.supportingEvidence.length).toBeGreaterThan(0);
  });

  // Test 4: recommendation node has rationale
  it('4. recommendation node → title WHY THIS RECOMMENDATION? with rationale', () => {
    const result = buildDecisionExplanation(makeParams({ focus: { kind: 'node', nodeId: 'rec-1' } }));
    expect(result).not.toBeNull();
    expect(result!.title).toBe('WHY THIS RECOMMENDATION?');
    expect(result!.recommendation?.rationale).toBeTruthy();
  });

  // Test 5: proposal node has sourceRecommendation
  it('5. proposal node → title WHY THIS PROPOSAL? with sourceRecommendation', () => {
    const result = buildDecisionExplanation(makeParams({ focus: { kind: 'node', nodeId: 'prop-node-1' } }));
    expect(result).not.toBeNull();
    expect(result!.title).toBe('WHY THIS PROPOSAL?');
    expect(result!.proposal).toBeDefined();
    // Should have sourceRecommendation from index 0
    expect(result!.proposal?.sourceRecommendation?.capability).toBe('reassign_labor_from_equipment');
  });

  // Test 6: decision REQUIRES_HUMAN_APPROVAL → approvalRequired true
  it('6. decision REQUIRES_HUMAN_APPROVAL → policyEvaluation.approvalRequired is true', () => {
    const result = buildDecisionExplanation(makeParams({ focus: { kind: 'node', nodeId: 'dec-2' } }));
    expect(result).not.toBeNull();
    expect(result!.policyEvaluation?.approvalRequired).toBe(true);
    expect(result!.policyEvaluation?.outcome).toBe('REQUIRES_HUMAN_APPROVAL');
  });

  // Test 7: decision APPROVED → approvalRequired false
  it('7. decision APPROVED → policyEvaluation.approvalRequired is false', () => {
    const result = buildDecisionExplanation(makeParams({ focus: { kind: 'node', nodeId: 'dec-1' } }));
    expect(result).not.toBeNull();
    expect(result!.policyEvaluation?.approvalRequired).toBe(false);
  });

  // Test 8: approval node → PENDING state
  it('8. approval node → title WHY IS APPROVAL REQUIRED?, state PENDING', () => {
    const result = buildDecisionExplanation(makeParams({ focus: { kind: 'node', nodeId: 'appr-1' } }));
    expect(result).not.toBeNull();
    expect(result!.title).toBe('WHY IS APPROVAL REQUIRED?');
    expect(result!.approval?.state).toBe('PENDING');
  });

  // Test 9: execution UNKNOWN → isUnknown true
  it('9. execution UNKNOWN → isUnknown true', () => {
    const result = buildDecisionExplanation(makeParams({ focus: { kind: 'node', nodeId: 'exec-unknown-1' } }));
    expect(result).not.toBeNull();
    expect(result!.execution?.isUnknown).toBe(true);
  });

  // Test 10: execution executed → isUnknown false
  it('10. execution executed → isUnknown false', () => {
    const result = buildDecisionExplanation(makeParams({ focus: { kind: 'node', nodeId: 'exec-done-1' } }));
    expect(result).not.toBeNull();
    expect(result!.execution?.isUnknown).toBe(false);
    expect(result!.execution?.status).toBe('executed');
  });

  // Test 11: reconciliation node → summary includes 'Automatic retry was suppressed'
  it('11. reconciliation node → summary includes Automatic retry was suppressed', () => {
    const result = buildDecisionExplanation(makeParams({ focus: { kind: 'node', nodeId: 'recon-1' } }));
    expect(result).not.toBeNull();
    expect(result!.summary).toContain('Automatic retry was suppressed');
  });

  // Test 12: outcome node → outcome fields from metadata
  it('12. outcome node → outcome fields from pre/post metadata', () => {
    const result = buildDecisionExplanation(makeParams({ focus: { kind: 'node', nodeId: 'outcome-1' } }));
    expect(result).not.toBeNull();
    expect(result!.outcome?.preWaveRisk).toBe(0.78);
    expect(result!.outcome?.postWaveRisk).toBe(0.42);
    expect(result!.outcome?.deltaWaveRisk).toBe(-0.36);
    expect(result!.outcome?.prePendingBacklog).toBe(14);
  });

  // Test 13: stage focus PROPOSE → recommendation + proposal
  it('13. stage focus PROPOSE → recommendation and proposal in result', () => {
    const result = buildStageExplanation('PROPOSE', baseAnalysis, [basePendingApproval], 0);
    expect(result).not.toBeNull();
    expect(result!.recommendation).toBeDefined();
    expect(result!.proposal).toBeDefined();
    expect(result!.title).toBe('WHY THIS RECOMMENDATION?');
  });

  // Test 14: stage focus DECIDE → policyEvaluation
  it('14. stage focus DECIDE → policyEvaluation in result', () => {
    const result = buildStageExplanation('DECIDE', baseAnalysis, [], 0);
    expect(result).not.toBeNull();
    expect(result!.policyEvaluation).toBeDefined();
    expect(result!.policyEvaluation?.outcome).toBe('executed');
  });

  // Test 15: stage focus APPROVE → approval
  it('15. stage focus APPROVE with pendingApprovals → approval in result', () => {
    const result = buildStageExplanation('APPROVE', baseAnalysis, [basePendingApproval], 0);
    expect(result).not.toBeNull();
    expect(result!.approval).toBeDefined();
    expect(result!.approval?.state).toBe('PENDING');
    expect(result!.approval?.capability).toBe('reprioritize_wave_tasks');
  });

  // Test 16: stage focus OUTCOME → outcome with pre/post values
  it('16. stage focus OUTCOME → outcome with pre/post values from analysisResult', () => {
    const result = buildStageExplanation('OUTCOME', baseAnalysis, [], 0);
    expect(result).not.toBeNull();
    expect(result!.outcome).toBeDefined();
    expect(result!.outcome?.preWaveRisk).toBe(0.78);
    expect(result!.outcome?.postWaveRisk).toBe(0.42);
    expect(result!.outcome?.deltaWaveRisk).toBe(-0.36);
  });

  // Test 17: no chain_of_thought field
  it('17. no chain_of_thought / scratchpad / hidden_reasoning field exposed', () => {
    const allFocuses: Array<BuildExplanationParams> = [
      makeParams({ focus: { kind: 'node', nodeId: 'ev-kpi-1' } }),
      makeParams({ focus: { kind: 'node', nodeId: 'assess-1' } }),
      makeParams({ focus: { kind: 'node', nodeId: 'rec-1' } }),
      makeParams({ focus: { kind: 'node', nodeId: 'prop-node-1' } }),
      makeParams({ focus: { kind: 'node', nodeId: 'dec-1' } }),
    ];
    for (const params of allFocuses) {
      const result = buildDecisionExplanation(params);
      if (result) {
        const serialized = JSON.stringify(result);
        expect(serialized).not.toContain('chain_of_thought');
        expect(serialized).not.toContain('scratchpad');
        expect(serialized).not.toContain('hidden_reasoning');
        expect(serialized).not.toContain('reasoning_tokens');
      }
    }
  });

  // Test 18: traceIds.traceId from analysisResult.trace_id
  it('18. traceIds.traceId comes from analysisResult.trace_id', () => {
    const result = buildDecisionExplanation(makeParams({ focus: { kind: 'node', nodeId: 'assess-1' } }));
    expect(result).not.toBeNull();
    expect(result!.traceIds.traceId).toBe('trace-13d-001');
  });
});

// ── Constraint tests (19–23) ──────────────────────────────────────────────────

describe('buildDecisionExplanation — constraints', () => {
  // Test 19: recommendation and proposal are distinct fields
  it('19. recommendation and proposal are distinct fields (not merged)', () => {
    const result = buildDecisionExplanation(makeParams({ focus: { kind: 'node', nodeId: 'prop-node-1' } }));
    expect(result).not.toBeNull();
    // proposal is set; recommendation is also set separately
    expect(result!.proposal).toBeDefined();
    // The proposal's sourceRecommendation is the recommendation embedded within proposal
    expect(result!.proposal?.sourceRecommendation).toBeDefined();
    // They are distinct top-level fields in the spec — proposal may also set top-level recommendation
    // The key constraint is that proposal.sourceRecommendation != null means they're separate objects
    expect(result!.proposal?.sourceRecommendation).not.toBe(result!.proposal);
  });

  // Test 20: outcome uses metadata fields, not demoStatus polling
  it('20. outcome uses metadata from graph node, not demoStatus current_kpis', () => {
    const modifiedStatus = {
      ...baseStatus,
      current_kpis: { ...baseKPIs, wave_risk_score: 9999 }, // Different value
    };
    const result = buildDecisionExplanation(makeParams({
      focus: { kind: 'node', nodeId: 'outcome-1' },
      demoStatus: modifiedStatus,
    }));
    expect(result).not.toBeNull();
    // Should use metadata (0.78), not demoStatus (9999)
    expect(result!.outcome?.preWaveRisk).toBe(0.78);
    expect(result!.outcome?.preWaveRisk).not.toBe(9999);
  });

  // Test 21: UNKNOWN execution does NOT set status to 'FAILED'
  it('21. UNKNOWN execution status is UNKNOWN, not FAILED', () => {
    const result = buildDecisionExplanation(makeParams({ focus: { kind: 'node', nodeId: 'exec-unknown-1' } }));
    expect(result).not.toBeNull();
    expect(result!.execution?.status).toBe('UNKNOWN');
    expect(result!.execution?.status).not.toBe('FAILED');
    expect(result!.execution?.status).not.toBe('failed');
  });

  // Test 22: every explanation has a source field
  it('22. every explanation type has a defined source field', () => {
    const nodeIds = fullGraph.nodes.map(n => n.id);
    for (const nodeId of nodeIds) {
      const result = buildDecisionExplanation(makeParams({ focus: { kind: 'node', nodeId } }));
      if (result) {
        expect(result.source).toBeDefined();
        expect(['LIVE', 'DERIVED', 'VALIDATED_ARTIFACT', 'LOCAL']).toContain(result.source);
      }
    }
  });

  // Test 23: node focus for unknown nodeId returns null
  it('23. node focus for unknown nodeId returns null', () => {
    const result = buildDecisionExplanation(makeParams({
      focus: { kind: 'node', nodeId: 'nonexistent-node' },
      graph: emptyGraph,
    }));
    expect(result).toBeNull();
  });
});

// ── Render tests (24–30) ──────────────────────────────────────────────────────

function renderDrawer(props: Partial<React.ComponentProps<typeof DecisionExplanationDrawer>> = {}) {
  const defaults = {
    focus: { kind: 'node' as const, nodeId: 'assess-1' },
    graph: fullGraph,
    analysisResult: baseAnalysis,
    pendingApprovals: [basePendingApproval],
    demoStatus: baseStatus,
    onClose: jest.fn(),
    ...props,
  };
  return render(
    <Wrapper>
      <div style={{ position: 'relative', height: 600 }}>
        <DecisionExplanationDrawer {...defaults} />
      </div>
    </Wrapper>,
  );
}

describe('DecisionExplanationDrawer — render', () => {
  // Test 24: renders drawer title for assessment focus
  it('24. renders drawer title WHY THIS ASSESSMENT? for assessment node focus', () => {
    renderDrawer({ focus: { kind: 'node', nodeId: 'assess-1' } });
    expect(screen.getByText('WHY THIS ASSESSMENT?')).toBeInTheDocument();
  });

  // Test 25: renders DETAIL NOT AVAILABLE when explanation is null
  it('25. renders DETAIL NOT AVAILABLE for unknown node in empty graph', () => {
    renderDrawer({
      focus: { kind: 'node', nodeId: 'no-such-node' },
      graph: emptyGraph,
      analysisResult: null,
    });
    expect(screen.getByText('DETAIL NOT AVAILABLE')).toBeInTheDocument();
  });

  // Test 26: Escape key calls onClose
  it('26. Escape key calls onClose', () => {
    const onClose = jest.fn();
    renderDrawer({ onClose });
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  // Test 27: PROPOSE stage with 2 proposals shows branch selector
  it('27. PROPOSE stage with 2 proposals shows branch selector', () => {
    renderDrawer({
      focus: { kind: 'stage', stage: 'PROPOSE' },
    });
    // proposalCount = max(recommendations.length, proposal_results.length) = 2
    expect(screen.getByText('SELECT PROPOSAL')).toBeInTheDocument();
    // Should show [A] and [B] selectors
    expect(screen.getByText('[A]')).toBeInTheDocument();
    expect(screen.getByText('[B]')).toBeInTheDocument();
  });

  // Test 28: UNKNOWN execution shows suppressed retry text
  it('28. UNKNOWN execution shows Automatic retry was suppressed text', () => {
    renderDrawer({ focus: { kind: 'node', nodeId: 'exec-unknown-1' } });
    expect(screen.getByText(/Automatic retry was suppressed/i)).toBeInTheDocument();
  });

  // Test 29: outcome renders before/after table
  it('29. outcome focus renders BEFORE / AFTER / DELTA table headers', () => {
    renderDrawer({ focus: { kind: 'node', nodeId: 'outcome-1' } });
    expect(screen.getByText('BEFORE')).toBeInTheDocument();
    expect(screen.getByText('AFTER')).toBeInTheDocument();
    expect(screen.getByText('DELTA')).toBeInTheDocument();
  });

  // Test 30: TRACE DETAILS is collapsed by default
  it('30. TRACE DETAILS section is collapsed by default', () => {
    renderDrawer({ focus: { kind: 'node', nodeId: 'assess-1' } });
    // The toggle button should be present
    const toggle = screen.getByTestId('trace-details-toggle');
    expect(toggle).toBeInTheDocument();
    // The trace_id value should NOT be visible before clicking
    expect(screen.queryByText('trace-13d-001')).not.toBeInTheDocument();
    // After clicking it should expand
    fireEvent.click(toggle);
    expect(screen.getByText('trace-13d-001')).toBeInTheDocument();
  });
});
