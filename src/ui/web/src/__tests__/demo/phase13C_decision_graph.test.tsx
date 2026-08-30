/**
 * Phase 13C tests — buildDecisionGraph pure function + DecisionGraph rendering.
 *
 * Pure-function tests (18 tests) cover:
 *   1.  OBSERVE stage: evidence nodes, no proposal/decision/approval/execution
 *   2.  REASON stage: agent, model_gateway, model, skill, assessment nodes
 *   3.  PROPOSE stage: recommendation and proposal nodes (distinct types)
 *   4.  DECIDE stage: decision_engine and decision nodes
 *   5.  APPROVE stage: approval node connected to correct decision
 *   6.  EXECUTE stage: executor, mcp, execution nodes
 *   7.  OUTCOME stage: outcome node from pre/post KPIs
 *   8.  UNKNOWN reconciliation: reconciliation node appears, no retry edge
 *   9.  Branching: 2 recommendations → 2 proposals in separate columns
 *  10.  No hardcoded values: no label contains literal KPI strings
 *  11.  Source classification: every node has a valid source
 *  12.  No chain-of-thought: no metadata key contains disallowed fields
 *  13.  Proposal correlation: proposal node matches recommendation via index
 *  14.  Stage isolation: REASON stage has no proposal/decision/approval/execution/outcome nodes
 *  15.  Evidence sourced from current_kpis values
 *  16.  Model node uses assessment.model_id (LIVE)
 *  17.  Decision node outcome-colored by lifecycle DECIDE outcome
 *  18.  Edges connect correct source → target node IDs
 *
 * Render tests (3 tests) for DecisionGraph component — see bottom of file.
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { ThemeProvider } from '@mui/material/styles';

import { buildDecisionGraph, BuildDecisionGraphParams } from '../../components/demo/decision-graph/buildDecisionGraph';
import { NodeSource, DecisionGraphNode } from '../../components/demo/decision-graph/graphTypes';
import { DemoStatus, AnalysisResult, PendingApproval, KPISnapshot } from '../../services/demoAPI';
import { nvidiaTheme } from '../../theme/nvidiaTheme';
import DecisionGraph from '../../components/demo/decision-graph/DecisionGraph';

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
  scenario: { name: 'test', display_name: 'Test Scenario', description: '', tags: [] },
  world: {
    warehouse_id: 'DC-01',
    clock_iso: '2026-08-29T08:00:00Z',
    elapsed_seconds: 100,
    equipment: { total: 10, available: 9, assigned: 1, maintenance: 0, offline: 0 },
    workers: { total: 8, active: 5, inactive: 3 },
    tasks: { total: 20, pending: 14, in_progress: 3, completed: 3 },
    inventory: { total_skus: 8, low_stock: 2 },
  },
  current_kpis: baseKPIs,
  kpi_history: [],
  pending_approvals: [],
};

const baseAnalysis: AnalysisResult = {
  ok: true,
  trace_id: 'trace-test-001',
  assessment: {
    snapshot_id: 'snap-test-001',
    warehouse_id: 'DC-01',
    assessed_at: '2026-08-29T08:00:01Z',
    summary: 'High wave risk due to labor shortage.',
    severity: 'high',
    domains_affected: ['labor', 'wave'],
    facts_observed: [
      '3 workers absent unplanned',
      'Wave risk score elevated',
    ],
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
    ],
    model_id: 'nvidia/llama-3.1-nemotron-70b-instruct',
    routing_rule: 'labor_wave_risk',
    routing_reason: 'Labor + wave domain reasoning=HIGH',
    latency_ms: 980,
  },
  proposal_results: [
    {
      status: 'executed',
      capability: 'reassign_labor_from_equipment',
      execution_id: 'exec-001',
      proposal_id: 'prop-001',
      decision_id: 'dec-001',
    },
  ],
  lifecycle: [
    { phase: 'OBSERVE', snapshot_id: 'snap-test-001', warehouse_id: 'DC-01', trace_id: 'trace-test-001' },
    { phase: 'REASON', summary: 'High wave risk', severity: 'high', model_id: 'nvidia/llama-3.1-nemotron-70b-instruct', routing_rule: 'labor_wave_risk', routing_reason: 'Labor + wave', latency_ms: 980, recommendations_count: 1, trace_id: 'trace-test-001' },
    { phase: 'SKILL', index: 0, capability: 'reassign_labor_from_equipment', target: 'AGV-01', domain: 'labor', priority: 'high', objective: 'Restore wave processing', trace_id: 'trace-test-001' },
    { phase: 'PROPOSE', index: 0, action: 'Reassign 2 workers from equipment', proposal_id: 'prop-001', risk_level: 'medium', trace_id: 'trace-test-001' },
    { phase: 'DECIDE', index: 0, outcome: 'APPROVED', proposal_id: 'prop-001', decision_id: 'dec-001', violations: [], trace_id: 'trace-test-001' },
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
  pending_id: 'pa-test-001',
  proposal_id: 'prop-001',
  decision_id: 'dec-001',
  trace_id: 'trace-test-001',
  capability: 'reassign_labor_from_equipment',
  target: 'AGV-01',
  domain: 'labor',
  risk_level: 'medium',
  objective: 'Restore wave processing',
  rationale: 'Equipment load reducible.',
  priority: 'high',
  queued_at: '2026-08-29T08:00:05Z',
};

function makeParams(overrides: Partial<BuildDecisionGraphParams> = {}): BuildDecisionGraphParams {
  return {
    currentStage: 'OBSERVE',
    demoStatus: baseStatus,
    analysisResult: null,
    pendingApprovals: [],
    ...overrides,
  };
}

const VALID_SOURCES: NodeSource[] = ['LIVE', 'DERIVED', 'VALIDATED_ARTIFACT', 'LOCAL'];
const FORBIDDEN_METADATA_KEYS = ['chain_of_thought', 'scratchpad', 'reasoning_tokens', 'raw_prompt'];

// ── Test helpers ──────────────────────────────────────────────────────────────

function nodesByType(nodes: DecisionGraphNode[], type: string) {
  return nodes.filter(n => n.type === type);
}

function hasEdge(edges: ReturnType<typeof buildDecisionGraph>['edges'], srcId: string, tgtId: string) {
  return edges.some(e => e.source === srcId && e.target === tgtId);
}

// ── Pure-function tests ───────────────────────────────────────────────────────

describe('buildDecisionGraph — OBSERVE stage', () => {
  it('has evidence nodes from current_kpis', () => {
    const { nodes } = buildDecisionGraph(makeParams({ currentStage: 'OBSERVE' }));
    const evNodes = nodesByType(nodes, 'evidence');
    expect(evNodes.length).toBeGreaterThanOrEqual(1);
  });

  it('has no proposal, decision, approval, execution, or outcome nodes', () => {
    const { nodes } = buildDecisionGraph(makeParams({ currentStage: 'OBSERVE' }));
    const forbidden = ['proposal', 'decision', 'approval', 'executor', 'mcp', 'execution', 'outcome'];
    for (const type of forbidden) {
      expect(nodesByType(nodes, type)).toHaveLength(0);
    }
  });

  it('has no edges at OBSERVE stage', () => {
    const { edges } = buildDecisionGraph(makeParams({ currentStage: 'OBSERVE' }));
    expect(edges).toHaveLength(0);
  });
});

describe('buildDecisionGraph — REASON stage', () => {
  it('includes agent, model_gateway, model, skill, assessment nodes', () => {
    const { nodes } = buildDecisionGraph(makeParams({
      currentStage: 'REASON',
      analysisResult: baseAnalysis,
    }));
    expect(nodesByType(nodes, 'agent')).toHaveLength(1);
    expect(nodesByType(nodes, 'model_gateway')).toHaveLength(1);
    expect(nodesByType(nodes, 'model')).toHaveLength(1);
    expect(nodesByType(nodes, 'skill')).toHaveLength(1);
    expect(nodesByType(nodes, 'assessment')).toHaveLength(1);
  });

  it('model node has source=LIVE and uses assessment.model_id', () => {
    const { nodes } = buildDecisionGraph(makeParams({
      currentStage: 'REASON',
      analysisResult: baseAnalysis,
    }));
    const modelNode = nodesByType(nodes, 'model')[0];
    expect(modelNode.source).toBe('LIVE');
    expect(modelNode.label).toBe('nvidia/llama-3.1-nemotron-70b-instruct');
  });

  it('agent node has source=DERIVED', () => {
    const { nodes } = buildDecisionGraph(makeParams({
      currentStage: 'REASON',
      analysisResult: baseAnalysis,
    }));
    const agentNode = nodesByType(nodes, 'agent')[0];
    expect(agentNode.source).toBe('DERIVED');
    expect(agentNode.label).toBe('OperationsCoordinationAgent');
  });

  it('model_gateway node has source=DERIVED', () => {
    const { nodes } = buildDecisionGraph(makeParams({
      currentStage: 'REASON',
      analysisResult: baseAnalysis,
    }));
    expect(nodesByType(nodes, 'model_gateway')[0].source).toBe('DERIVED');
  });

  it('stage isolation: no proposal/decision/approval/execution/outcome at REASON', () => {
    const { nodes } = buildDecisionGraph(makeParams({
      currentStage: 'REASON',
      analysisResult: baseAnalysis,
    }));
    const absent = ['proposal', 'decision_engine', 'decision', 'approval', 'executor', 'mcp', 'execution', 'outcome'];
    for (const type of absent) {
      expect(nodesByType(nodes, type)).toHaveLength(0);
    }
  });
});

describe('buildDecisionGraph — PROPOSE stage', () => {
  it('has recommendation and proposal nodes as distinct types', () => {
    const { nodes } = buildDecisionGraph(makeParams({
      currentStage: 'PROPOSE',
      analysisResult: baseAnalysis,
    }));
    expect(nodesByType(nodes, 'recommendation')).toHaveLength(1);
    expect(nodesByType(nodes, 'proposal')).toHaveLength(1);
  });

  it('proposal node correlates to recommendation via index', () => {
    const { nodes } = buildDecisionGraph(makeParams({
      currentStage: 'PROPOSE',
      analysisResult: baseAnalysis,
    }));
    const rec  = nodesByType(nodes, 'recommendation')[0];
    const prop = nodesByType(nodes, 'proposal')[0];
    // Both should be in the same column (correlated by index)
    expect(rec.column).toBe(prop.column);
  });

  it('proposal node has artifact_id from proposal_id', () => {
    const { nodes } = buildDecisionGraph(makeParams({
      currentStage: 'PROPOSE',
      analysisResult: baseAnalysis,
    }));
    const prop = nodesByType(nodes, 'proposal')[0];
    expect(prop.artifact_id).toBe('prop-001');
  });
});

describe('buildDecisionGraph — DECIDE stage', () => {
  it('has decision_engine (DERIVED) and decision (LIVE) nodes', () => {
    const { nodes } = buildDecisionGraph(makeParams({
      currentStage: 'DECIDE',
      analysisResult: baseAnalysis,
    }));
    const de  = nodesByType(nodes, 'decision_engine');
    const dec = nodesByType(nodes, 'decision');
    expect(de).toHaveLength(1);
    expect(de[0].source).toBe('DERIVED');
    expect(dec).toHaveLength(1);
    expect(dec[0].source).toBe('LIVE');
  });

  it('decision node label reflects lifecycle DECIDE outcome', () => {
    const { nodes } = buildDecisionGraph(makeParams({
      currentStage: 'DECIDE',
      analysisResult: baseAnalysis,
    }));
    const dec = nodesByType(nodes, 'decision')[0];
    expect(dec.label).toBe('APPROVED');
  });

  it('all proposal nodes have edge to decision_engine', () => {
    const { nodes, edges } = buildDecisionGraph(makeParams({
      currentStage: 'DECIDE',
      analysisResult: baseAnalysis,
    }));
    const propNodes = nodesByType(nodes, 'proposal');
    const deNode    = nodesByType(nodes, 'decision_engine')[0];
    for (const p of propNodes) {
      expect(hasEdge(edges, p.id, deNode.id)).toBe(true);
    }
  });
});

describe('buildDecisionGraph — APPROVE stage', () => {
  it('has approval node when pendingApprovals non-empty', () => {
    const { nodes } = buildDecisionGraph(makeParams({
      currentStage: 'APPROVE',
      analysisResult: {
        ...baseAnalysis,
        lifecycle: [
          ...baseAnalysis.lifecycle.filter(r => r.phase !== 'DECIDE'),
          { phase: 'DECIDE', index: 0, outcome: 'REQUIRES_HUMAN_APPROVAL', proposal_id: 'prop-001', decision_id: 'dec-001', violations: [], trace_id: 'trace-test-001' },
        ],
      },
      pendingApprovals: [basePendingApproval],
    }));
    expect(nodesByType(nodes, 'approval')).toHaveLength(1);
  });

  it('approval node has pending_id as artifact_id (Gap G7 workaround)', () => {
    const { nodes } = buildDecisionGraph(makeParams({
      currentStage: 'APPROVE',
      analysisResult: baseAnalysis,
      pendingApprovals: [basePendingApproval],
    }));
    const approvalNode = nodesByType(nodes, 'approval')[0];
    expect(approvalNode.artifact_id).toBe('pa-test-001');
  });

  it('no approval nodes when pendingApprovals is empty', () => {
    const { nodes } = buildDecisionGraph(makeParams({
      currentStage: 'APPROVE',
      analysisResult: baseAnalysis,
      pendingApprovals: [],
    }));
    expect(nodesByType(nodes, 'approval')).toHaveLength(0);
  });
});

describe('buildDecisionGraph — EXECUTE stage', () => {
  it('has executor, mcp, and execution nodes', () => {
    const { nodes } = buildDecisionGraph(makeParams({
      currentStage: 'EXECUTE',
      analysisResult: baseAnalysis,
    }));
    expect(nodesByType(nodes, 'executor')).toHaveLength(1);
    expect(nodesByType(nodes, 'mcp')).toHaveLength(1);
    expect(nodesByType(nodes, 'execution')).toHaveLength(1);
  });

  it('executor and mcp nodes are DERIVED', () => {
    const { nodes } = buildDecisionGraph(makeParams({
      currentStage: 'EXECUTE',
      analysisResult: baseAnalysis,
    }));
    expect(nodesByType(nodes, 'executor')[0].source).toBe('DERIVED');
    expect(nodesByType(nodes, 'mcp')[0].source).toBe('DERIVED');
  });

  it('execution node has artifact_id from execution_id', () => {
    const { nodes } = buildDecisionGraph(makeParams({
      currentStage: 'EXECUTE',
      analysisResult: baseAnalysis,
    }));
    const execNode = nodesByType(nodes, 'execution')[0];
    expect(execNode.artifact_id).toBe('exec-001');
  });
});

describe('buildDecisionGraph — OUTCOME stage', () => {
  it('has outcome node sourced from pre/post KPIs', () => {
    const { nodes } = buildDecisionGraph(makeParams({
      currentStage: 'OUTCOME',
      analysisResult: baseAnalysis,
    }));
    const outcomeNodes = nodesByType(nodes, 'outcome');
    expect(outcomeNodes).toHaveLength(1);
    expect(outcomeNodes[0].source).toBe('LIVE');
  });

  it('outcome node metadata includes KPI delta fields', () => {
    const { nodes } = buildDecisionGraph(makeParams({
      currentStage: 'OUTCOME',
      analysisResult: baseAnalysis,
    }));
    const meta = nodesByType(nodes, 'outcome')[0].metadata ?? {};
    expect(meta).toHaveProperty('delta_wave_risk_score');
    expect(meta).toHaveProperty('delta_pending_backlog');
  });
});

describe('buildDecisionGraph — UNKNOWN reconciliation', () => {
  it('adds reconciliation node when execution status is unknown', () => {
    const analysisWithUnknown: AnalysisResult = {
      ...baseAnalysis,
      proposal_results: [
        {
          status: 'unknown',
          capability: 'reassign_labor_from_equipment',
          execution_id: 'exec-unknown-001',
          proposal_id: 'prop-001',
        },
      ],
    };
    const { nodes } = buildDecisionGraph(makeParams({
      currentStage: 'EXECUTE',
      analysisResult: analysisWithUnknown,
    }));
    expect(nodesByType(nodes, 'reconciliation')).toHaveLength(1);
  });

  it('reconciliation node is connected from execution node (no retry edge)', () => {
    const analysisWithUnknown: AnalysisResult = {
      ...baseAnalysis,
      proposal_results: [
        { status: 'unknown', capability: 'reassign_labor_from_equipment', execution_id: 'exec-u', proposal_id: 'prop-001' },
      ],
    };
    const { nodes, edges } = buildDecisionGraph(makeParams({
      currentStage: 'EXECUTE',
      analysisResult: analysisWithUnknown,
    }));
    const execNode  = nodesByType(nodes, 'execution')[0];
    const reconNode = nodesByType(nodes, 'reconciliation')[0];
    expect(hasEdge(edges, execNode.id, reconNode.id)).toBe(true);
    // No retry edge back to execution
    expect(hasEdge(edges, reconNode.id, execNode.id)).toBe(false);
  });
});

describe('buildDecisionGraph — branching (2 recommendations)', () => {
  const branchAnalysis: AnalysisResult = {
    ...baseAnalysis,
    assessment: {
      ...baseAnalysis.assessment,
      recommendations: [
        {
          domain: 'labor',
          capability: 'reassign_labor_from_equipment',
          target: 'AGV-01',
          objective: 'Restore wave capacity',
          rationale: 'R1',
          priority: 'high',
          subtype: null,
        },
        {
          domain: 'wave',
          capability: 'expedite_wave_tasks',
          target: 'WAVE-04',
          objective: 'Expedite critical picks',
          rationale: 'R2',
          priority: 'medium',
          subtype: null,
        },
      ],
    },
    lifecycle: [
      ...baseAnalysis.lifecycle.filter(r => r.phase !== 'PROPOSE' && r.phase !== 'DECIDE'),
      { phase: 'PROPOSE', index: 0, action: 'Reassign workers', proposal_id: 'prop-001', risk_level: 'medium', trace_id: 'trace-test-001' },
      { phase: 'PROPOSE', index: 1, action: 'Expedite picks',   proposal_id: 'prop-002', risk_level: 'low',    trace_id: 'trace-test-001' },
      { phase: 'DECIDE', index: 0, outcome: 'APPROVED', proposal_id: 'prop-001', decision_id: 'dec-001', violations: [], trace_id: 'trace-test-001' },
      { phase: 'DECIDE', index: 1, outcome: 'APPROVED', proposal_id: 'prop-002', decision_id: 'dec-002', violations: [], trace_id: 'trace-test-001' },
    ],
  };

  it('has 2 recommendation nodes in separate columns', () => {
    const { nodes } = buildDecisionGraph(makeParams({
      currentStage: 'PROPOSE',
      analysisResult: branchAnalysis,
    }));
    const recNodes = nodesByType(nodes, 'recommendation');
    expect(recNodes).toHaveLength(2);
    expect(recNodes[0].column).not.toBe(recNodes[1].column);
  });

  it('has 2 proposal nodes in separate columns', () => {
    const { nodes } = buildDecisionGraph(makeParams({
      currentStage: 'PROPOSE',
      analysisResult: branchAnalysis,
    }));
    const propNodes = nodesByType(nodes, 'proposal');
    expect(propNodes).toHaveLength(2);
    expect(propNodes[0].column).not.toBe(propNodes[1].column);
  });

  it('has 2 decision nodes in separate columns', () => {
    const { nodes } = buildDecisionGraph(makeParams({
      currentStage: 'DECIDE',
      analysisResult: branchAnalysis,
    }));
    const decNodes = nodesByType(nodes, 'decision');
    expect(decNodes).toHaveLength(2);
    expect(decNodes[0].column).not.toBe(decNodes[1].column);
  });
});

describe('buildDecisionGraph — no hardcoded values', () => {
  it('no node label contains literal KPI percentage strings', () => {
    const { nodes } = buildDecisionGraph(makeParams({
      currentStage: 'OUTCOME',
      analysisResult: baseAnalysis,
    }));
    // Node labels should not contain formatted percentages like "80%" or raw scores like "0.78"
    for (const node of nodes) {
      expect(node.label).not.toMatch(/^\d+(\.\d+)?%$/);
    }
  });

  it('no node label is a raw KPI number string', () => {
    const { nodes } = buildDecisionGraph(makeParams({ currentStage: 'OBSERVE' }));
    const kpiValues = ['80', '62.5', '14', '0.78'];
    for (const node of nodes) {
      for (const val of kpiValues) {
        // Labels should be field names, not raw values
        expect(node.label).not.toBe(val);
      }
    }
  });
});

describe('buildDecisionGraph — source classification', () => {
  it('every node has a valid NodeSource', () => {
    const { nodes } = buildDecisionGraph(makeParams({
      currentStage: 'OUTCOME',
      analysisResult: baseAnalysis,
    }));
    for (const node of nodes) {
      expect(VALID_SOURCES).toContain(node.source);
    }
  });

  it('no node has a null or undefined source', () => {
    const { nodes } = buildDecisionGraph(makeParams({
      currentStage: 'OUTCOME',
      analysisResult: baseAnalysis,
    }));
    for (const node of nodes) {
      expect(node.source).toBeDefined();
      expect(node.source).not.toBeNull();
    }
  });
});

describe('buildDecisionGraph — no chain-of-thought', () => {
  it('no node metadata key contains forbidden internal fields', () => {
    const { nodes } = buildDecisionGraph(makeParams({
      currentStage: 'OUTCOME',
      analysisResult: baseAnalysis,
    }));
    for (const node of nodes) {
      const keys = Object.keys(node.metadata ?? {});
      for (const key of keys) {
        for (const forbidden of FORBIDDEN_METADATA_KEYS) {
          expect(key).not.toContain(forbidden);
        }
      }
    }
  });
});

describe('buildDecisionGraph — edge connectivity', () => {
  it('evidence nodes connect to agent node', () => {
    const { nodes, edges } = buildDecisionGraph(makeParams({
      currentStage: 'REASON',
      analysisResult: baseAnalysis,
    }));
    const evNodes   = nodesByType(nodes, 'evidence');
    const agentNode = nodesByType(nodes, 'agent')[0];
    for (const ev of evNodes) {
      expect(hasEdge(edges, ev.id, agentNode.id)).toBe(true);
    }
  });

  it('agent → model_gateway → model edges exist', () => {
    const { nodes, edges } = buildDecisionGraph(makeParams({
      currentStage: 'REASON',
      analysisResult: baseAnalysis,
    }));
    const agentNode = nodesByType(nodes, 'agent')[0];
    const mgwNode   = nodesByType(nodes, 'model_gateway')[0];
    const modelNode = nodesByType(nodes, 'model')[0];
    expect(hasEdge(edges, agentNode.id, mgwNode.id)).toBe(true);
    expect(hasEdge(edges, mgwNode.id, modelNode.id)).toBe(true);
  });

  it('executor → mcp edge exists', () => {
    const { nodes, edges } = buildDecisionGraph(makeParams({
      currentStage: 'EXECUTE',
      analysisResult: baseAnalysis,
    }));
    const executorNode = nodesByType(nodes, 'executor')[0];
    const mcpNode      = nodesByType(nodes, 'mcp')[0];
    expect(hasEdge(edges, executorNode.id, mcpNode.id)).toBe(true);
  });
});

describe('buildDecisionGraph — evidence from current_kpis', () => {
  it('evidence nodes use field names from current_kpis (not raw values)', () => {
    const { nodes } = buildDecisionGraph(makeParams({ currentStage: 'OBSERVE' }));
    const evNodes = nodesByType(nodes, 'evidence');
    const kpiFieldNames = [
      'wave_risk_score', 'labor_availability_pct', 'pending_backlog', 'equipment_operational_pct',
    ];
    const labels = evNodes.map(n => n.label);
    for (const fieldName of kpiFieldNames) {
      expect(labels).toContain(fieldName);
    }
  });

  it('evidence node metadata includes source_field pointer', () => {
    const { nodes } = buildDecisionGraph(makeParams({ currentStage: 'OBSERVE' }));
    const evNodes = nodesByType(nodes, 'evidence');
    for (const ev of evNodes) {
      expect(ev.metadata).toHaveProperty('source_field');
    }
  });
});

// ── Rendering tests ───────────────────────────────────────────────────────────

function wrapGraph(el: React.ReactElement) {
  return render(<ThemeProvider theme={nvidiaTheme}>{el}</ThemeProvider>);
}

describe('DecisionGraph component — rendering', () => {
  it('renders canvas container', () => {
    const graph = buildDecisionGraph(makeParams({ currentStage: 'OBSERVE' }));
    wrapGraph(<DecisionGraph graph={graph} />);
    expect(screen.getByTestId('decision-graph')).toBeInTheDocument();
  });

  it('shows node labels in the graph', () => {
    const graph = buildDecisionGraph(makeParams({
      currentStage: 'REASON',
      analysisResult: baseAnalysis,
    }));
    wrapGraph(<DecisionGraph graph={graph} />);
    expect(screen.getByText('OperationsCoordinationAgent')).toBeInTheDocument();
    expect(screen.getByText('ModelGateway')).toBeInTheDocument();
  });

  it('clicking a node opens the details panel', () => {
    const graph = buildDecisionGraph(makeParams({
      currentStage: 'REASON',
      analysisResult: baseAnalysis,
    }));
    wrapGraph(<DecisionGraph graph={graph} />);
    // Click agent node
    const agentCard = screen.getByTestId('graph-node-agent-0');
    fireEvent.click(agentCard);
    expect(screen.getByTestId('decision-graph-details')).toBeInTheDocument();
    // Label appears in both the node card and the details panel
    expect(screen.getAllByText('OperationsCoordinationAgent').length).toBeGreaterThanOrEqual(1);
  });
});
