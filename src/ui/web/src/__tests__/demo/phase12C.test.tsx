/**
 * Phase 12C tests — StageContentPane, ObserveStage, ReasonStage, ProposeStage, DecideStage.
 *
 * Covers:
 *  - StageContentPane routes to correct stage component
 *  - ObserveStage: shows warehouse world, KPIs, facts_observed, run-analysis button
 *  - ObserveStage: re-run button after analysisResult available
 *  - ReasonStage: model + routing from SSE detail, summary from SSE message
 *  - ReasonStage: SKILL sub-events from lifecycle records (preferred) / SSE fallback
 *  - ProposeStage: action + risk from lifecycle records; rationale from recommendations
 *  - ProposeStage: SSE fallback when no lifecycle records
 *  - ProposeStage: no projected-impact numbers
 *  - DecideStage: authority chain visible
 *  - DecideStage: APPROVED outcome from lifecycle records
 *  - DecideStage: REQUIRES_HUMAN_APPROVAL shows handoff notice
 *  - DecideStage: pending approvals list rendered
 *  - parseDetail and runWindowEvents utility functions
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import { ThemeProvider } from '@mui/material/styles';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { nvidiaTheme } from '../../theme/nvidiaTheme';

import StageContentPane, { parseDetail, runWindowEvents } from '../../components/demo/StageContentPane';
import ObserveStage  from '../../components/demo/stages/ObserveStage';
import ReasonStage   from '../../components/demo/stages/ReasonStage';
import ProposeStage  from '../../components/demo/stages/ProposeStage';
import DecideStage   from '../../components/demo/stages/DecideStage';
import { SSEEvent } from '../../hooks/useDemoSSE';
import { DemoStatus, AnalysisResult, PendingApproval } from '../../services/demoAPI';

// ── Fixtures ───────────────────────────────────────────────────────────────────

function makeSSEEvent(category: string, message: string, detail: string | null = null, idx = 0): SSEEvent {
  return {
    id: `evt-${idx}-${category}`,
    ts: new Date(1000000 + idx * 1000).toISOString(),
    category,
    message,
    detail,
    asset_id: null,
    task_id: null,
    worker_id: null,
  };
}

// Newest-first (as useDemoSSE stores them)
function makeEvents(...pairs: [string, string, string?][]): SSEEvent[] {
  return [...pairs].reverse().map(([cat, msg, detail], i) => makeSSEEvent(cat, msg, detail ?? null, i));
}

const baseWorld: DemoStatus['world'] = {
  warehouse_id: 'DC-47',
  clock_iso: '2026-08-27T10:00:47Z',
  elapsed_seconds: 47,
  equipment: { total: 8, available: 7, assigned: 1, maintenance: 0, offline: 0 },
  workers: { total: 6, active: 3, inactive: 3 },
  tasks: { total: 10, pending: 7, in_progress: 2, completed: 1 },
  inventory: { total_skus: 5, low_stock: 1 },
};

const baseKPIs: DemoStatus['current_kpis'] = {
  sim_time_seconds: 47,
  clock_iso: '2026-08-27T10:00:47Z',
  equipment_total: 8,
  equipment_operational_pct: 87.5,
  labor_total: 6,
  labor_availability_pct: 50,
  labor_utilization_pct: 80,
  pending_backlog: 7,
  wave_risk_score: 0.92,
  wave_risk_level: 'critical',
  low_stock_count: 1,
  state_freshness_seconds: 12,
  service_risk_index: 0.7,
  capacity_throughput_proxy: 300,
  wave_completion_pct: 34,
  simulated_throughput: 312,
  projected_service_level: 71,
  time_to_recovery_seconds: null,
};

const baseStatus: DemoStatus = {
  active: true,
  paused: false,
  scenario: { name: 'labor_constraint_wave_risk', display_name: 'Labor + Wave Risk', description: '', tags: [] },
  world: baseWorld,
  current_kpis: baseKPIs,
  kpi_history: [],
  pending_approvals: [],
};

const baseAnalysis: AnalysisResult = {
  ok: true,
  trace_id: 'trace-001',
  assessment: {
    snapshot_id: 'snap-abc12345',
    warehouse_id: 'DC-47',
    assessed_at: '2026-08-27T10:00:48Z',
    summary: '3 workers on unplanned absence causing labor shortage and wave risk.',
    severity: 'critical',
    domains_affected: ['labor', 'wave'],
    facts_observed: [
      '3 workers on unplanned absence',
      'Wave risk score: 0.92 (critical)',
      '7 pending pick tasks with approaching deadlines',
    ],
    recommendations: [
      {
        domain: 'labor',
        capability: 'reassign_labor_from_equipment',
        target: 'AGV-03',
        objective: 'Restore wave processing capacity',
        rationale: 'Equipment load can be reduced without service impact to free workers.',
        priority: 'critical',
        subtype: null,
      },
    ],
    model_id: 'nvidia/llama-3.1-nemotron-70b-instruct',
    routing_rule: 'labor_wave_risk',
    routing_reason: 'Labor + wave domain combination triggers Nemotron-70B routing.',
    latency_ms: 1240,
  },
  proposal_results: [
    { status: 'REQUIRES_HUMAN_APPROVAL', capability: 'reassign_labor_from_equipment', proposal_id: 'prop-001', decision_id: 'dec-001' },
  ],
  lifecycle: [
    { phase: 'OBSERVE', snapshot_id: 'snap-abc12345', warehouse_id: 'DC-47', equipment_total: 8, labor_total: 6, wave_tasks: 10, trace_id: 'trace-001' },
    { phase: 'REASON', summary: '3 workers on unplanned absence...', severity: 'critical', model_id: 'nvidia/llama-3.1-nemotron-70b-instruct', routing_rule: 'labor_wave_risk', routing_reason: 'Labor + wave domain...', latency_ms: 1240, recommendations_count: 1, trace_id: 'trace-001' },
    { phase: 'SKILL', index: 0, capability: 'reassign_labor_from_equipment', target: 'AGV-03', domain: 'labor', priority: 'critical', objective: 'Restore wave processing capacity', trace_id: 'trace-001' },
    { phase: 'PROPOSE', index: 0, action: 'Reassign 2 workers from equipment to wave operations', proposal_id: 'prop-full-001', risk_level: 'medium', trace_id: 'trace-001' },
    { phase: 'DECIDE', index: 0, outcome: 'REQUIRES_HUMAN_APPROVAL', proposal_id: 'prop-full-001', decision_id: 'dec-full-001', violations: [], trace_id: 'trace-001' },
  ],
  pre_kpis: baseKPIs,
  post_kpis: baseKPIs,
};

const basePendingApproval: PendingApproval = {
  pending_id: 'pa-001',
  proposal_id: 'prop-full-001',
  decision_id: 'dec-full-001',
  trace_id: 'trace-001',
  capability: 'reassign_labor_from_equipment',
  target: 'AGV-03',
  domain: 'labor',
  risk_level: 'medium',
  objective: 'Restore wave processing capacity',
  rationale: 'Equipment load can be reduced without service impact.',
  priority: 'critical',
  queued_at: '2026-08-27T10:00:50Z',
};

// ── Render helpers ─────────────────────────────────────────────────────────────

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function wrap(el: React.ReactElement) {
  return render(
    <MemoryRouter>
      <QueryClientProvider client={makeQC()}>
        <ThemeProvider theme={nvidiaTheme}>{el}</ThemeProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

const noop = async () => {};

function makeProps(overrides: Partial<Parameters<typeof StageContentPane>[0]> = {}): Parameters<typeof StageContentPane>[0] {
  return {
    currentStage: 'OBSERVE',
    sseEvents: [],
    demoStatus: baseStatus,
    analysisResult: null,
    pendingApprovals: [],
    analyzing: false,
    onAnalyze: noop,
    ...overrides,
  };
}

// ── parseDetail utility ────────────────────────────────────────────────────────

describe('parseDetail', () => {
  it('parses key=value pairs', () => {
    expect(parseDetail('model=nvidia/llama rule=labor_wave_risk')).toEqual({
      model: 'nvidia/llama',
      rule: 'labor_wave_risk',
    });
  });

  it('parses proposal and decision IDs', () => {
    expect(parseDetail('proposal=abc12345 decision=def67890')).toEqual({
      proposal: 'abc12345',
      decision: 'def67890',
    });
  });

  it('returns empty object for null/empty', () => {
    expect(parseDetail(null)).toEqual({});
    expect(parseDetail('')).toEqual({});
  });

  it('handles single token', () => {
    expect(parseDetail('target=AGV-03')).toEqual({ target: 'AGV-03' });
  });
});

// ── runWindowEvents utility ────────────────────────────────────────────────────

describe('runWindowEvents', () => {
  it('returns empty when no OBSERVE anchor and no matching events', () => {
    const events = makeEvents(['PIPELINE', 'some message']);
    expect(runWindowEvents(events, ['REASON'])).toHaveLength(0);
  });

  it('returns matching events in chronological order', () => {
    // Timeline: OBSERVE, REASON, SKILL (chronological)
    // Stored newest-first: SKILL, REASON, OBSERVE
    const events = makeEvents(
      ['OBSERVE', 'State assembled'],
      ['REASON', 'Assessment complete', 'model=nemotron rule=labor'],
      ['SKILL', 'reassign_labor', 'target=AGV-03'],
    );
    const result = runWindowEvents(events, ['REASON']);
    expect(result).toHaveLength(1);
    expect(result[0].category).toBe('REASON');
  });

  it('includes only events within current run window (stops at OBSERVE anchor)', () => {
    // Second run: just OBSERVE. First run had SKILL events.
    const events: SSEEvent[] = [
      makeSSEEvent('OBSERVE', 'new run', null, 10),   // new run anchor (idx 0 in newest-first)
      makeSSEEvent('SKILL', 'old skill', null, 9),     // from prior run — must be excluded
      makeSSEEvent('OBSERVE', 'first run', null, 5),   // first run anchor
    ];
    // events are already in newest-first order here
    const result = runWindowEvents(events, ['SKILL']);
    // Only the second run window (events[0] to events[0]) contains OBSERVE, no SKILL → empty
    expect(result).toHaveLength(0);
  });

  it('returns multiple matching events in chronological order', () => {
    const events = makeEvents(
      ['OBSERVE', 'start'],
      ['SKILL', 'skill1', 'target=A'],
      ['SKILL', 'skill2', 'target=B'],
    );
    const result = runWindowEvents(events, ['SKILL']);
    expect(result).toHaveLength(2);
    expect(result[0].message).toBe('skill1');
    expect(result[1].message).toBe('skill2');
  });
});

// ── StageContentPane routing ───────────────────────────────────────────────────

describe('StageContentPane — stage routing', () => {
  it('renders observe-stage for OBSERVE', () => {
    wrap(<StageContentPane {...makeProps({ currentStage: 'OBSERVE' })} />);
    expect(screen.getByTestId('observe-stage')).toBeInTheDocument();
  });

  it('renders reason-stage for REASON', () => {
    wrap(<StageContentPane {...makeProps({ currentStage: 'REASON' })} />);
    expect(screen.getByTestId('reason-stage')).toBeInTheDocument();
  });

  it('renders propose-stage for PROPOSE', () => {
    wrap(<StageContentPane {...makeProps({ currentStage: 'PROPOSE' })} />);
    expect(screen.getByTestId('propose-stage')).toBeInTheDocument();
  });

  it('renders decide-stage for DECIDE', () => {
    wrap(<StageContentPane {...makeProps({ currentStage: 'DECIDE' })} />);
    expect(screen.getByTestId('decide-stage')).toBeInTheDocument();
  });

  it('renders approve-stage for APPROVE (Phase 12D implemented)', () => {
    wrap(<StageContentPane {...makeProps({ currentStage: 'APPROVE' })} />);
    // APPROVE now has a real implementation — no placeholder
    expect(screen.getByTestId('approve-stage')).toBeInTheDocument();
    expect(screen.queryByText(/Phase 12D/i)).not.toBeInTheDocument();
    expect(screen.queryByTestId('observe-stage')).not.toBeInTheDocument();
  });

  it('renders outcome-stage for OUTCOME (Phase 12E complete)', () => {
    wrap(<StageContentPane {...makeProps({ currentStage: 'OUTCOME' })} />);
    expect(screen.getByTestId('outcome-stage')).toBeInTheDocument();
  });

  it('renders stage-content-pane testid on root', () => {
    wrap(<StageContentPane {...makeProps()} />);
    expect(screen.getByTestId('stage-content-pane')).toBeInTheDocument();
  });
});

// ── ObserveStage ───────────────────────────────────────────────────────────────

describe('ObserveStage', () => {
  it('renders warehouse world stats from demoStatus.world', () => {
    wrap(<ObserveStage {...makeProps()} />);
    expect(screen.getByTestId('observe-stage')).toBeInTheDocument();
    // Workers: 3 active / 6 total
    expect(screen.getByText('3 / 6')).toBeInTheDocument();
    // Equipment: 7 / 8
    expect(screen.getByText('7 / 8')).toBeInTheDocument();
    // Pending tasks: 7
    expect(screen.getAllByText('7')[0]).toBeInTheDocument();
  });

  it('shows scenario display_name', () => {
    wrap(<ObserveStage {...makeProps()} />);
    expect(screen.getByText('Labor + Wave Risk')).toBeInTheDocument();
  });

  it('shows elapsed time', () => {
    wrap(<ObserveStage {...makeProps()} />);
    expect(screen.getByText(/t=47s/)).toBeInTheDocument();
  });

  it('shows Run MAIW Analysis button when no analysisResult', () => {
    wrap(<ObserveStage {...makeProps({ analysisResult: null })} />);
    expect(screen.getByTestId('run-analysis-button')).toBeInTheDocument();
  });

  it('calls onAnalyze when Run Analysis clicked', async () => {
    const onAnalyze = jest.fn().mockResolvedValue(undefined);
    wrap(<ObserveStage {...makeProps({ onAnalyze, analyzing: false, analysisResult: null })} />);
    fireEvent.click(screen.getByTestId('run-analysis-button'));
    await waitFor(() => expect(onAnalyze).toHaveBeenCalledTimes(1));
  });

  it('disables Run Analysis button while analyzing', () => {
    wrap(<ObserveStage {...makeProps({ analyzing: true, analysisResult: null })} />);
    expect(screen.getByTestId('run-analysis-button')).toBeDisabled();
  });

  it('shows facts_observed from analysisResult', () => {
    wrap(<ObserveStage {...makeProps({ analysisResult: baseAnalysis })} />);
    expect(screen.getByText('3 workers on unplanned absence')).toBeInTheDocument();
    expect(screen.getByText('7 pending pick tasks with approaching deadlines')).toBeInTheDocument();
  });

  it('shows snapshot_id post-analysis', () => {
    wrap(<ObserveStage {...makeProps({ analysisResult: baseAnalysis })} />);
    expect(screen.getByText('snap-abc12345')).toBeInTheDocument();
  });

  it('shows re-run button (not primary CTA) after analysis', () => {
    wrap(<ObserveStage {...makeProps({ analysisResult: baseAnalysis })} />);
    expect(screen.queryByTestId('run-analysis-button')).not.toBeInTheDocument();
    expect(screen.getByTestId('rerun-analysis-button')).toBeInTheDocument();
  });

  it('shows state freshness from current_kpis', () => {
    wrap(<ObserveStage {...makeProps()} />);
    expect(screen.getByText(/12s old/)).toBeInTheDocument();
  });
});

// ── ReasonStage ───────────────────────────────────────────────────────────────

describe('ReasonStage', () => {
  it('shows model ID from analysisResult', () => {
    wrap(<ReasonStage {...makeProps({ currentStage: 'REASON', analysisResult: baseAnalysis })} />);
    expect(screen.getByText('nvidia/llama-3.1-nemotron-70b-instruct')).toBeInTheDocument();
  });

  it('shows routing rule from analysisResult', () => {
    wrap(<ReasonStage {...makeProps({ currentStage: 'REASON', analysisResult: baseAnalysis })} />);
    expect(screen.getByText('labor_wave_risk')).toBeInTheDocument();
  });

  it('shows routing reason from analysisResult', () => {
    wrap(<ReasonStage {...makeProps({ currentStage: 'REASON', analysisResult: baseAnalysis })} />);
    expect(screen.getByText(/Labor \+ wave domain/)).toBeInTheDocument();
  });

  it('shows assessment summary', () => {
    wrap(<ReasonStage {...makeProps({ currentStage: 'REASON', analysisResult: baseAnalysis })} />);
    expect(screen.getByText(/3 workers on unplanned absence/)).toBeInTheDocument();
  });

  it('shows latency', () => {
    wrap(<ReasonStage {...makeProps({ currentStage: 'REASON', analysisResult: baseAnalysis })} />);
    expect(screen.getByText('1240ms')).toBeInTheDocument();
  });

  it('shows SKILL chips from lifecycle records', () => {
    wrap(<ReasonStage {...makeProps({ currentStage: 'REASON', analysisResult: baseAnalysis })} />);
    expect(screen.getByText('reassign_labor_from_equipment')).toBeInTheDocument();
    expect(screen.getByText('AGV-03')).toBeInTheDocument();
  });

  it('falls back to SSE SKILL events when no lifecycle records', () => {
    const events = makeEvents(
      ['OBSERVE', 'start'],
      ['REASON', 'Summary text', 'model=test-model rule=labor'],
      ['SKILL', 'some_capability', 'target=WORKER-01'],
    );
    // analysisResult has no lifecycle SKILL records (empty lifecycle)
    const analysisNoSkill: AnalysisResult = {
      ...baseAnalysis,
      lifecycle: [
        { phase: 'REASON', summary: 'Summary text', severity: 'high', model_id: 'test-model', routing_rule: 'labor', routing_reason: '', latency_ms: 500, recommendations_count: 1, trace_id: 'trace-001' },
      ],
    };
    wrap(<ReasonStage {...makeProps({ currentStage: 'REASON', sseEvents: events, analysisResult: analysisNoSkill })} />);
    expect(screen.getByText('some_capability')).toBeInTheDocument();
    expect(screen.getByText('WORKER-01')).toBeInTheDocument();
  });

  it('shows model from SSE detail when no analysisResult', () => {
    const events = makeEvents(
      ['OBSERVE', 'start'],
      ['REASON', 'Assessment via SSE', 'model=sse-model rule=sse-rule'],
    );
    wrap(<ReasonStage {...makeProps({ currentStage: 'REASON', sseEvents: events, analysisResult: null })} />);
    expect(screen.getByText('sse-model')).toBeInTheDocument();
    expect(screen.getByText('sse-rule')).toBeInTheDocument();
    expect(screen.getByText('Assessment via SSE')).toBeInTheDocument();
  });

  it('does not expose chain-of-thought — no raw LLM output label', () => {
    wrap(<ReasonStage {...makeProps({ currentStage: 'REASON', analysisResult: baseAnalysis })} />);
    expect(screen.queryByText(/chain.of.thought/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/raw prompt/i)).not.toBeInTheDocument();
  });
});

// ── ProposeStage ──────────────────────────────────────────────────────────────

describe('ProposeStage', () => {
  it('shows action from PROPOSE lifecycle record', () => {
    wrap(<ProposeStage {...makeProps({ currentStage: 'PROPOSE', analysisResult: baseAnalysis })} />);
    expect(screen.getByText('Reassign 2 workers from equipment to wave operations')).toBeInTheDocument();
  });

  it('shows capability and target from SKILL lifecycle record', () => {
    wrap(<ProposeStage {...makeProps({ currentStage: 'PROPOSE', analysisResult: baseAnalysis })} />);
    expect(screen.getByText('reassign_labor_from_equipment')).toBeInTheDocument();
    expect(screen.getByText('AGV-03')).toBeInTheDocument();
  });

  it('shows rationale from assessment.recommendations', () => {
    wrap(<ProposeStage {...makeProps({ currentStage: 'PROPOSE', analysisResult: baseAnalysis })} />);
    expect(screen.getByText(/Equipment load can be reduced/)).toBeInTheDocument();
  });

  it('shows risk level badge', () => {
    wrap(<ProposeStage {...makeProps({ currentStage: 'PROPOSE', analysisResult: baseAnalysis })} />);
    expect(screen.getByText('medium')).toBeInTheDocument();
  });

  it('shows proposal ID', () => {
    wrap(<ProposeStage {...makeProps({ currentStage: 'PROPOSE', analysisResult: baseAnalysis })} />);
    expect(screen.getByText('prop-full-001')).toBeInTheDocument();
  });

  it('never shows numerical projected impact claims', () => {
    wrap(<ProposeStage {...makeProps({ currentStage: 'PROPOSE', analysisResult: baseAnalysis })} />);
    // The component may display an explanatory note, but must not show numerical projected-impact figures
    // like "+12% throughput" or "projected backlog reduction: 3"
    expect(screen.queryByText(/projected backlog/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/estimated impact/i)).not.toBeInTheDocument();
    // kpi_delta values must not appear in the proposal pane
    expect(screen.queryByText(/kpi.delta/i)).not.toBeInTheDocument();
  });

  it('falls back to SSE PROPOSE events when no lifecycle records', () => {
    const events = makeEvents(
      ['OBSERVE', 'start'],
      ['PROPOSE', 'Reassign worker via SSE', 'proposal=ssepropl'],
    );
    wrap(<ProposeStage {...makeProps({ currentStage: 'PROPOSE', sseEvents: events, analysisResult: null })} />);
    expect(screen.getByText('Reassign worker via SSE')).toBeInTheDocument();
  });

  it('shows waiting message when no events or lifecycle records', () => {
    wrap(<ProposeStage {...makeProps({ currentStage: 'PROPOSE', analysisResult: null })} />);
    expect(screen.getByText(/Waiting for ProposalBuilder/i)).toBeInTheDocument();
  });
});

// ── DecideStage ───────────────────────────────────────────────────────────────

describe('DecideStage', () => {
  it('renders authority chain', () => {
    wrap(<DecideStage {...makeProps({ currentStage: 'DECIDE' })} />);
    expect(screen.getByText('Nemotron recommends')).toBeInTheDocument();
    expect(screen.getByText('MAIW proposes')).toBeInTheDocument();
    expect(screen.getByText('DecisionEngine decides')).toBeInTheDocument();
  });

  it('shows REQUIRES APPROVAL outcome badge from lifecycle records', () => {
    wrap(<DecideStage {...makeProps({ currentStage: 'DECIDE', analysisResult: baseAnalysis })} />);
    expect(screen.getByText('REQUIRES APPROVAL')).toBeInTheDocument();
  });

  it('shows decision and proposal IDs', () => {
    wrap(<DecideStage {...makeProps({ currentStage: 'DECIDE', analysisResult: baseAnalysis })} />);
    expect(screen.getByText('prop-full-001')).toBeInTheDocument();
    expect(screen.getByText('dec-full-001')).toBeInTheDocument();
  });

  it('shows APPROVE handoff notice when REQUIRES_HUMAN_APPROVAL', () => {
    wrap(<DecideStage {...makeProps({ currentStage: 'DECIDE', analysisResult: baseAnalysis })} />);
    expect(screen.getByText(/Advancing to APPROVE/i)).toBeInTheDocument();
  });

  it('does NOT show handoff notice when APPROVED', () => {
    const approvedAnalysis: AnalysisResult = {
      ...baseAnalysis,
      lifecycle: [
        ...baseAnalysis.lifecycle.filter(r => r.phase !== 'DECIDE'),
        { phase: 'DECIDE', index: 0, outcome: 'APPROVED', proposal_id: 'prop-001', decision_id: 'dec-001', violations: [], trace_id: 'trace-001' },
      ],
    };
    wrap(<DecideStage {...makeProps({ currentStage: 'DECIDE', analysisResult: approvedAnalysis })} />);
    expect(screen.getByText('APPROVED')).toBeInTheDocument();
    expect(screen.queryByText(/Advancing to APPROVE/i)).not.toBeInTheDocument();
  });

  it('shows pending approvals list', () => {
    wrap(<DecideStage {...makeProps({
      currentStage: 'DECIDE',
      analysisResult: baseAnalysis,
      pendingApprovals: [basePendingApproval],
    })} />);
    expect(screen.getByText('reassign_labor_from_equipment')).toBeInTheDocument();
    expect(screen.getAllByText('AGV-03').length).toBeGreaterThan(0);
  });

  it('shows pending count in handoff notice', () => {
    wrap(<DecideStage {...makeProps({
      currentStage: 'DECIDE',
      analysisResult: baseAnalysis,
      pendingApprovals: [basePendingApproval],
    })} />);
    expect(screen.getByText(/1 approval queued/i)).toBeInTheDocument();
  });

  it('falls back to SSE DECIDE events when no lifecycle records', () => {
    const events = makeEvents(
      ['OBSERVE', 'start'],
      ['DECIDE', 'APPROVED', 'proposal=abc12345 decision=def67890'],
    );
    wrap(<DecideStage {...makeProps({ currentStage: 'DECIDE', sseEvents: events, analysisResult: null })} />);
    expect(screen.getByText('APPROVED')).toBeInTheDocument();
  });

  it('shows waiting message when no events or lifecycle', () => {
    wrap(<DecideStage {...makeProps({ currentStage: 'DECIDE', analysisResult: null })} />);
    expect(screen.getByText(/Waiting for DecisionEngine/i)).toBeInTheDocument();
  });
});

// ── DemoShell integration: analyze trigger ─────────────────────────────────────

describe('DemoShell — analyze integration', () => {
  const { MemoryRouter } = require('react-router-dom');
  const { QueryClient, QueryClientProvider } = require('@tanstack/react-query');

  jest.mock('../../services/demoAPI', () => ({
    demoAPI: {
      listScenarios: jest.fn(),
      startScenario: jest.fn(),
      pauseScenario: jest.fn(),
      resumeScenario: jest.fn(),
      resetScenario: jest.fn(),
      getStatusSafe: jest.fn(),
      analyze: jest.fn(),
      approvePending: jest.fn(),
      rejectPending: jest.fn(),
    },
  }));

  jest.mock('../../hooks/useDemoSSE', () => ({
    useDemoSSE: () => ({ events: [], connected: false, error: null, clear: jest.fn() }),
  }));

  jest.mock('../../hooks/useRuntimeStatus', () => ({
    useRuntimeStatus: () => ({ data: { maiw_operational_status: 'HEALTHY', model_gateway_status: 'HEALTHY', domain_health: {} }, isLoading: false }),
  }));

  jest.mock('../../hooks/useDemoStatus', () => ({
    useDemoStatus: jest.fn(),
  }));

  const { useDemoStatus } = require('../../hooks/useDemoStatus');
  const { demoAPI } = require('../../services/demoAPI');

  beforeEach(() => jest.clearAllMocks());

  it('replaces stage-workspace with stage-content-pane when scenario active', () => {
    useDemoStatus.mockReturnValue({
      status: baseStatus,
      isLoading: false,
      isDemoMode: true,
      refetch: jest.fn(),
    });

    const DemoShell = require('../../pages/DemoShell').default;
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ThemeProvider theme={nvidiaTheme}>
            <DemoShell />
          </ThemeProvider>
        </QueryClientProvider>
      </MemoryRouter>
    );
    expect(screen.getByTestId('stage-content-pane')).toBeInTheDocument();
    expect(screen.queryByTestId('stage-workspace')).not.toBeInTheDocument();
  });

  it('shows Run Analysis button in observe pane by default', () => {
    useDemoStatus.mockReturnValue({
      status: baseStatus,
      isLoading: false,
      isDemoMode: true,
      refetch: jest.fn(),
    });

    const DemoShell = require('../../pages/DemoShell').default;
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ThemeProvider theme={nvidiaTheme}>
            <DemoShell />
          </ThemeProvider>
        </QueryClientProvider>
      </MemoryRouter>
    );
    expect(screen.getByTestId('run-analysis-button')).toBeInTheDocument();
  });
});
