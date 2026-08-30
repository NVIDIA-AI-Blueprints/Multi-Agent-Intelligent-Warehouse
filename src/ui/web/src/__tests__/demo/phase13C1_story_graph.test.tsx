/**
 * Phase 13C.1 tests — semanticZoom pure function + StoryDecisionGraph rendering + DecisionGraph mode toggle.
 *
 * semanticZoom tests (5):
 *   1.  scale 0.4  → OVERVIEW
 *   2.  scale 0.59 → OVERVIEW
 *   3.  scale 0.6  → STANDARD
 *   4.  scale 0.85 → STANDARD
 *   5.  scale 1.01 → DETAIL
 *
 * StoryDecisionGraph rendering tests (12):
 *   6.  OBSERVE stage: SITUATION region rendered; INTELLIGENCE/RESPONSE/GOVERNANCE/ACTION/OUTCOME absent
 *   7.  REASON stage: SITUATION + INTELLIGENCE regions both rendered
 *   8.  PROPOSE stage: RESPONSE region rendered
 *   9.  DECIDE stage: GOVERNANCE region rendered
 *  10.  APPROVE stage: approval card ("HUMAN AUTHORITY REQUIRED") in GOVERNANCE region
 *  11.  EXECUTE stage: ACTION region + "EXECUTION BOUNDARY" text visible
 *  12.  OUTCOME stage: OUTCOME region rendered
 *  13.  OVERVIEW zoom (0.4): individual skill names absent; region summaries present
 *  14.  STANDARD zoom (0.85): Assessment summary text visible
 *  15.  Skills collapsed by default at STANDARD: collapsed summary visible, individual skill name absent
 *  16.  Skills expandable: clicking toggle reveals individual skill names
 *  17.  UNKNOWN execution: "ReconciliationService" text visible at STANDARD zoom
 *
 * DecisionGraph component tests (3):
 *  18.  Default graphMode is 'story' → story-decision-graph testid present
 *  19.  Clicking TRACE tab → decision-graph-trace testid present
 *  20.  Clicking FIT → story mode restored (story-decision-graph testid present)
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { ThemeProvider } from '@mui/material/styles';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

import { getSemanticZoomLevel } from '../../components/demo/decision-graph/semanticZoom';
import { buildDecisionGraph, BuildDecisionGraphParams } from '../../components/demo/decision-graph/buildDecisionGraph';
import { DemoStatus, AnalysisResult, PendingApproval, KPISnapshot } from '../../services/demoAPI';
import { nvidiaTheme } from '../../theme/nvidiaTheme';
import StoryDecisionGraph from '../../components/demo/decision-graph/StoryDecisionGraph';
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

// ── Test helpers ──────────────────────────────────────────────────────────────

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function wrap(el: React.ReactElement) {
  const { MemoryRouter: MR } = require('react-router-dom');
  return render(
    <MR>
      <QueryClientProvider client={makeQC()}>
        <ThemeProvider theme={nvidiaTheme}>{el}</ThemeProvider>
      </QueryClientProvider>
    </MR>,
  );
}

// ── semanticZoom pure function tests ──────────────────────────────────────────

describe('getSemanticZoomLevel — thresholds', () => {
  it('scale 0.4 → OVERVIEW', () => {
    expect(getSemanticZoomLevel(0.4)).toBe('OVERVIEW');
  });

  it('scale 0.59 → OVERVIEW', () => {
    expect(getSemanticZoomLevel(0.59)).toBe('OVERVIEW');
  });

  it('scale 0.6 → STANDARD', () => {
    expect(getSemanticZoomLevel(0.6)).toBe('STANDARD');
  });

  it('scale 0.85 → STANDARD', () => {
    expect(getSemanticZoomLevel(0.85)).toBe('STANDARD');
  });

  it('scale 1.01 → DETAIL', () => {
    expect(getSemanticZoomLevel(1.01)).toBe('DETAIL');
  });
});

// ── StoryDecisionGraph — stage-based region visibility ────────────────────────

describe('StoryDecisionGraph — OBSERVE stage', () => {
  it('renders SITUATION region and not INTELLIGENCE/RESPONSE/GOVERNANCE/ACTION/OUTCOME', () => {
    const graph = buildDecisionGraph(makeParams({ currentStage: 'OBSERVE' }));
    wrap(
      <StoryDecisionGraph
        graph={graph}
        zoomLevel="STANDARD"
        selectedNodeId={null}
        onNodeClick={() => undefined}
      />,
    );
    expect(screen.getByTestId('story-region-situation')).toBeInTheDocument();
    expect(screen.queryByTestId('story-region-intelligence')).not.toBeInTheDocument();
    expect(screen.queryByTestId('story-region-response')).not.toBeInTheDocument();
    expect(screen.queryByTestId('story-region-governance')).not.toBeInTheDocument();
    expect(screen.queryByTestId('story-region-action')).not.toBeInTheDocument();
    expect(screen.queryByTestId('story-region-outcome')).not.toBeInTheDocument();
  });
});

describe('StoryDecisionGraph — REASON stage', () => {
  it('renders SITUATION and INTELLIGENCE regions', () => {
    const graph = buildDecisionGraph(makeParams({ currentStage: 'REASON', analysisResult: baseAnalysis }));
    wrap(
      <StoryDecisionGraph
        graph={graph}
        zoomLevel="STANDARD"
        selectedNodeId={null}
        onNodeClick={() => undefined}
      />,
    );
    expect(screen.getByTestId('story-region-situation')).toBeInTheDocument();
    expect(screen.getByTestId('story-region-intelligence')).toBeInTheDocument();
  });
});

describe('StoryDecisionGraph — PROPOSE stage', () => {
  it('renders RESPONSE region', () => {
    const graph = buildDecisionGraph(makeParams({ currentStage: 'PROPOSE', analysisResult: baseAnalysis }));
    wrap(
      <StoryDecisionGraph
        graph={graph}
        zoomLevel="STANDARD"
        selectedNodeId={null}
        onNodeClick={() => undefined}
      />,
    );
    expect(screen.getByTestId('story-region-response')).toBeInTheDocument();
  });
});

describe('StoryDecisionGraph — DECIDE stage', () => {
  it('renders GOVERNANCE region', () => {
    const graph = buildDecisionGraph(makeParams({ currentStage: 'DECIDE', analysisResult: baseAnalysis }));
    wrap(
      <StoryDecisionGraph
        graph={graph}
        zoomLevel="STANDARD"
        selectedNodeId={null}
        onNodeClick={() => undefined}
      />,
    );
    expect(screen.getByTestId('story-region-governance')).toBeInTheDocument();
  });
});

describe('StoryDecisionGraph — APPROVE stage', () => {
  it('shows HUMAN AUTHORITY REQUIRED card in GOVERNANCE region', () => {
    const approvalAnalysis: AnalysisResult = {
      ...baseAnalysis,
      lifecycle: [
        ...baseAnalysis.lifecycle.filter(r => r.phase !== 'DECIDE'),
        { phase: 'DECIDE', index: 0, outcome: 'REQUIRES_HUMAN_APPROVAL', proposal_id: 'prop-001', decision_id: 'dec-001', violations: [], trace_id: 'trace-test-001' },
      ],
    };
    const graph = buildDecisionGraph(makeParams({
      currentStage: 'APPROVE',
      analysisResult: approvalAnalysis,
      pendingApprovals: [basePendingApproval],
    }));
    wrap(
      <StoryDecisionGraph
        graph={graph}
        zoomLevel="STANDARD"
        selectedNodeId={null}
        onNodeClick={() => undefined}
      />,
    );
    expect(screen.getByText('HUMAN AUTHORITY REQUIRED')).toBeInTheDocument();
  });
});

describe('StoryDecisionGraph — EXECUTE stage', () => {
  it('renders ACTION region and shows EXECUTION BOUNDARY text', () => {
    const graph = buildDecisionGraph(makeParams({ currentStage: 'EXECUTE', analysisResult: baseAnalysis }));
    wrap(
      <StoryDecisionGraph
        graph={graph}
        zoomLevel="STANDARD"
        selectedNodeId={null}
        onNodeClick={() => undefined}
      />,
    );
    expect(screen.getByTestId('story-region-action')).toBeInTheDocument();
    expect(screen.getByText('EXECUTION BOUNDARY')).toBeInTheDocument();
  });
});

describe('StoryDecisionGraph — OUTCOME stage', () => {
  it('renders OUTCOME region', () => {
    const graph = buildDecisionGraph(makeParams({ currentStage: 'OUTCOME', analysisResult: baseAnalysis }));
    wrap(
      <StoryDecisionGraph
        graph={graph}
        zoomLevel="STANDARD"
        selectedNodeId={null}
        onNodeClick={() => undefined}
      />,
    );
    expect(screen.getByTestId('story-region-outcome')).toBeInTheDocument();
  });
});

describe('StoryDecisionGraph — OVERVIEW zoom', () => {
  it('does not show individual skill names; shows capabilities summary instead', () => {
    const graph = buildDecisionGraph(makeParams({ currentStage: 'REASON', analysisResult: baseAnalysis }));
    wrap(
      <StoryDecisionGraph
        graph={graph}
        zoomLevel="OVERVIEW"
        selectedNodeId={null}
        onNodeClick={() => undefined}
      />,
    );
    // Individual skill name should NOT appear in OVERVIEW
    expect(screen.queryByText('reassign_labor_from_equipment')).not.toBeInTheDocument();
    // But a capabilities summary should be present
    expect(screen.getByText(/capabilities/i)).toBeInTheDocument();
  });
});

describe('StoryDecisionGraph — STANDARD zoom assessment summary', () => {
  it('shows assessment summary text at STANDARD zoom', () => {
    const graph = buildDecisionGraph(makeParams({ currentStage: 'REASON', analysisResult: baseAnalysis }));
    wrap(
      <StoryDecisionGraph
        graph={graph}
        zoomLevel="STANDARD"
        selectedNodeId={null}
        onNodeClick={() => undefined}
      />,
    );
    expect(screen.getByText('High wave risk due to labor shortage.')).toBeInTheDocument();
  });
});

describe('StoryDecisionGraph — skills collapse', () => {
  it('skills collapsed by default: summary visible, individual skill name absent', () => {
    const graph = buildDecisionGraph(makeParams({ currentStage: 'REASON', analysisResult: baseAnalysis }));
    wrap(
      <StoryDecisionGraph
        graph={graph}
        zoomLevel="STANDARD"
        selectedNodeId={null}
        onNodeClick={() => undefined}
      />,
    );
    // Collapsed summary should be present
    expect(screen.getByText(/1 capabilities:/)).toBeInTheDocument();
    // Individual skill name should NOT be visible (not rendered in collapsed state)
    expect(screen.queryByText('reassign_labor_from_equipment')).not.toBeInTheDocument();
  });

  it('skills expandable: clicking toggle reveals individual skill names', () => {
    const graph = buildDecisionGraph(makeParams({ currentStage: 'REASON', analysisResult: baseAnalysis }));
    wrap(
      <StoryDecisionGraph
        graph={graph}
        zoomLevel="STANDARD"
        selectedNodeId={null}
        onNodeClick={() => undefined}
      />,
    );
    // Click the collapsed summary row to expand
    const toggle = screen.getByText(/1 capabilities:/);
    fireEvent.click(toggle);
    // Skill name should now be visible
    expect(screen.getByText('reassign_labor_from_equipment')).toBeInTheDocument();
  });
});

describe('StoryDecisionGraph — UNKNOWN execution reconciliation', () => {
  it('shows ReconciliationService text at STANDARD zoom for unknown execution', () => {
    const unknownAnalysis: AnalysisResult = {
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
    const graph = buildDecisionGraph(makeParams({
      currentStage: 'EXECUTE',
      analysisResult: unknownAnalysis,
    }));
    wrap(
      <StoryDecisionGraph
        graph={graph}
        zoomLevel="STANDARD"
        selectedNodeId={null}
        onNodeClick={() => undefined}
      />,
    );
    expect(screen.getByText(/ReconciliationService/)).toBeInTheDocument();
  });
});

// ── DecisionGraph component — mode toggle tests ───────────────────────────────

describe('DecisionGraph — graphMode', () => {
  it('default mode is story: story-decision-graph container is rendered', () => {
    const graph = buildDecisionGraph(makeParams({ currentStage: 'OBSERVE' }));
    wrap(<DecisionGraph graph={graph} />);
    expect(screen.getByTestId('story-decision-graph')).toBeInTheDocument();
    expect(screen.queryByTestId('decision-graph-trace')).not.toBeInTheDocument();
  });

  it('clicking TRACE tab shows the trace graph container', () => {
    const graph = buildDecisionGraph(makeParams({ currentStage: 'OBSERVE' }));
    wrap(<DecisionGraph graph={graph} />);
    fireEvent.click(screen.getByText('TRACE'));
    expect(screen.getByTestId('decision-graph-trace')).toBeInTheDocument();
    expect(screen.queryByTestId('story-decision-graph')).not.toBeInTheDocument();
  });

  it('clicking FIT restores story mode', () => {
    const graph = buildDecisionGraph(makeParams({ currentStage: 'OBSERVE' }));
    wrap(<DecisionGraph graph={graph} />);
    // Switch to trace
    fireEvent.click(screen.getByText('TRACE'));
    expect(screen.getByTestId('decision-graph-trace')).toBeInTheDocument();
    // Click FIT
    fireEvent.click(screen.getByTestId('fit-btn'));
    expect(screen.getByTestId('story-decision-graph')).toBeInTheDocument();
    expect(screen.queryByTestId('decision-graph-trace')).not.toBeInTheDocument();
  });
});
