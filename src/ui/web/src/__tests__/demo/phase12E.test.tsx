/**
 * Phase 12E tests — ExecuteStage + OutcomeStage.
 *
 * Spec contracts verified:
 *  - EXECUTED outcome shown
 *  - NO_OP outcome shown
 *  - DEFERRED outcome shown (including approved_no_executor mapping)
 *  - CONFLICT outcome shown
 *  - UNKNOWN outcome shown with reconciliation text
 *  - FAILED outcome shown
 *  - execution_id visible when present
 *  - atomic pre/post KPI data used (analysisResult.pre_kpis / post_kpis)
 *  - no polling-derived before/after values
 *  - correct delta rendering (sign, direction)
 *  - OBSERVED OPERATIONAL IMPACT label — not "projected impact"
 *  - recovery reached (time_to_recovery_seconds shown in seconds/minutes)
 *  - recovery not reached (RECOVERY NOT YET REACHED shown)
 *  - counterfactual button shows / hides CounterfactualPanel inline
 *  - RUN ANOTHER SCENARIO calls onReset
 *  - StageContentPane routes EXECUTE → execute-stage testid
 *  - StageContentPane routes OUTCOME → outcome-stage testid
 *  - execution result section is distinct from operational outcome section
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { ThemeProvider } from '@mui/material/styles';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { nvidiaTheme } from '../../theme/nvidiaTheme';

import StageContentPane, { StageContentPaneProps } from '../../components/demo/StageContentPane';
import ExecuteStage from '../../components/demo/stages/ExecuteStage';
import OutcomeStage from '../../components/demo/stages/OutcomeStage';
import { DemoStatus, AnalysisResult, KPISnapshot, KPIDelta } from '../../services/demoAPI';
import { SSEEvent } from '../../hooks/useDemoSSE';

// ── Mocks ──────────────────────────────────────────────────────────────────────

jest.mock('../../services/demoAPI', () => ({
  demoAPI: {
    listScenarios: jest.fn(),
    startScenario: jest.fn(),
    getStatusSafe: jest.fn(),
    analyze: jest.fn(),
    approvePending: jest.fn(),
    rejectPending: jest.fn(),
    getCounterfactualResult: jest.fn().mockResolvedValue(null),
  },
}));

jest.mock('../../hooks/useDemoSSE', () => ({
  useDemoSSE: () => ({ events: [], connected: false, error: null, clear: jest.fn() }),
}));

jest.mock('../../hooks/useRuntimeStatus', () => ({
  useRuntimeStatus: () => ({
    data: { maiw_operational_status: 'HEALTHY', model_gateway_status: 'HEALTHY', domain_health: {} },
    isLoading: false,
  }),
}));

jest.mock('../../hooks/useDemoStatus', () => ({
  useDemoStatus: jest.fn(),
}));

// ── Fixtures ───────────────────────────────────────────────────────────────────

const baseKPISnapshot: KPISnapshot = {
  sim_time_seconds: 120,
  clock_iso: '2026-08-27T10:02:00Z',
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

const postKPISnapshot: KPISnapshot = {
  ...baseKPISnapshot,
  sim_time_seconds: 180,
  clock_iso: '2026-08-27T10:03:00Z',
  equipment_operational_pct: 87.5,
  labor_utilization_pct: 90,
  pending_backlog: 4,
  wave_risk_score: 0.55,
  wave_risk_level: 'medium',
  wave_completion_pct: 52,
  time_to_recovery_seconds: 240,
};

const baseKPIDelta: KPIDelta = {
  equipment_operational_pct: 0,
  labor_availability_pct: 0,
  labor_utilization_pct: 10,
  pending_backlog: -3,
  wave_risk_score: -0.37,
  low_stock_count: 0,
  service_risk_index: -0.1,
  capacity_throughput_proxy: 20,
  wave_completion_pct: 18,
  simulated_throughput: 50,
  projected_service_level: 8,
};

const baseStatus: DemoStatus = {
  active: true,
  paused: false,
  scenario: { name: 'labor_constraint_wave_risk', display_name: 'Labor + Wave Risk', description: '', tags: [] },
  world: {
    warehouse_id: 'DC-47', clock_iso: '2026-08-27T10:02:00Z', elapsed_seconds: 120,
    equipment: { total: 8, available: 7, assigned: 1, maintenance: 0, offline: 0 },
    workers: { total: 6, active: 3, inactive: 3 },
    tasks: { total: 10, pending: 4, in_progress: 3, completed: 3 },
    inventory: { total_skus: 5, low_stock: 1 },
  },
  current_kpis: postKPISnapshot,
  kpi_history: [baseKPISnapshot, postKPISnapshot],
  pending_approvals: [],
};

const baseAnalysis: AnalysisResult = {
  ok: true,
  trace_id: 'trace-phase12E',
  assessment: {
    snapshot_id: 'snap-E01',
    warehouse_id: 'DC-47',
    assessed_at: '2026-08-27T10:00:48Z',
    summary: 'Labor shortfall on zone B.',
    severity: 'critical',
    domains_affected: ['labor', 'wave'],
    facts_observed: ['3 workers absent', 'wave risk critical'],
    recommendations: [],
    model_id: 'nvidia/llama-3.1-nemotron-70b-instruct',
    routing_rule: 'labor_wave_risk',
    routing_reason: '',
    latency_ms: 1200,
  },
  proposal_results: [
    {
      status: 'executed',
      capability: 'allocate_labor',
      proposal_id: 'prop-001',
      decision_id: 'dec-001',
      execution_id: 'exec-abc-001',
      success: true,
      outcome: 'executed',
    },
  ],
  lifecycle: [
    {
      phase: 'EXECUTE',
      index: 0,
      status: 'executed',
      action: 'labor.allocate',
      execution_id: 'exec-abc-001',
      success: true,
      trace_id: 'trace-phase12E',
    },
  ],
  pre_kpis: baseKPISnapshot,
  post_kpis: postKPISnapshot,
  kpi_delta: baseKPIDelta,
};

function makeSSEEvent(overrides: Partial<SSEEvent>): SSEEvent {
  return {
    id: '1',
    ts: '2026-08-27T10:02:00Z',
    category: 'EXECUTE',
    message: 'labor.allocate',
    detail: null,
    asset_id: null,
    task_id: null,
    worker_id: null,
    ...overrides,
  };
}

// ── Test helpers ───────────────────────────────────────────────────────────────

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

function makeExecuteProps(overrides: Partial<StageContentPaneProps> = {}): StageContentPaneProps {
  return {
    currentStage: 'EXECUTE',
    sseEvents: [],
    demoStatus: baseStatus,
    analysisResult: baseAnalysis,
    pendingApprovals: [],
    analyzing: false,
    onAnalyze: async () => {},
    onReset: jest.fn(),
    ...overrides,
  };
}

function makeOutcomeProps(overrides: Partial<StageContentPaneProps> = {}): StageContentPaneProps {
  return {
    currentStage: 'OUTCOME',
    sseEvents: [],
    demoStatus: baseStatus,
    analysisResult: baseAnalysis,
    pendingApprovals: [],
    analyzing: false,
    onAnalyze: async () => {},
    onReset: jest.fn(),
    ...overrides,
  };
}

// ══════════════════════════════════════════════════════════════════════════════
// ExecuteStage tests
// ══════════════════════════════════════════════════════════════════════════════

describe('ExecuteStage — routing', () => {
  it('StageContentPane routes EXECUTE → execute-stage', () => {
    wrap(<StageContentPane {...makeExecuteProps()} />);
    expect(screen.getByTestId('execute-stage')).toBeInTheDocument();
  });
});

describe('ExecuteStage — outcomes from lifecycle records', () => {
  function withOutcome(status: string, executionId?: string) {
    const analysis: AnalysisResult = {
      ...baseAnalysis,
      lifecycle: [{ phase: 'EXECUTE', index: 0, status, execution_id: executionId, success: true, trace_id: 'trace-E' }],
      proposal_results: [{ status, capability: 'allocate_labor', execution_id: executionId }],
    };
    return makeExecuteProps({ analysisResult: analysis });
  }

  it('shows EXECUTED outcome badge', () => {
    wrap(<ExecuteStage {...withOutcome('executed', 'exec-001')} />);
    expect(screen.getByTestId('outcome-badge-executed')).toBeInTheDocument();
  });

  it('shows NO_OP outcome badge', () => {
    wrap(<ExecuteStage {...withOutcome('no_op')} />);
    expect(screen.getByTestId('outcome-badge-no_op')).toBeInTheDocument();
  });

  it('shows DEFERRED outcome badge', () => {
    wrap(<ExecuteStage {...withOutcome('deferred')} />);
    expect(screen.getByTestId('outcome-badge-deferred')).toBeInTheDocument();
  });

  it('maps approved_no_executor to DEFERRED badge', () => {
    wrap(<ExecuteStage {...withOutcome('approved_no_executor')} />);
    expect(screen.getByTestId('outcome-badge-deferred')).toBeInTheDocument();
  });

  it('shows CONFLICT outcome badge', () => {
    wrap(<ExecuteStage {...withOutcome('conflict')} />);
    expect(screen.getByTestId('outcome-badge-conflict')).toBeInTheDocument();
  });

  it('shows UNKNOWN outcome badge with reconciliation notice', () => {
    wrap(<ExecuteStage {...withOutcome('unknown')} />);
    expect(screen.getByTestId('outcome-badge-unknown')).toBeInTheDocument();
    expect(screen.getByTestId('reconciliation-notice')).toBeInTheDocument();
  });

  it('UNKNOWN notice contains all three required lines', () => {
    wrap(<ExecuteStage {...withOutcome('unknown')} />);
    const notice = screen.getByTestId('reconciliation-notice');
    expect(notice).toHaveTextContent('may have accepted this action');
    expect(notice).toHaveTextContent('Automatic retry suppressed');
    expect(notice).toHaveTextContent('Reconciliation required');
  });

  it('shows FAILED outcome badge', () => {
    wrap(<ExecuteStage {...withOutcome('failed')} />);
    expect(screen.getByTestId('outcome-badge-failed')).toBeInTheDocument();
  });

  it('maps execution_error to FAILED badge', () => {
    wrap(<ExecuteStage {...withOutcome('execution_error')} />);
    expect(screen.getByTestId('outcome-badge-failed')).toBeInTheDocument();
  });

  it('execution_id is visible when present', () => {
    wrap(<ExecuteStage {...withOutcome('executed', 'exec-abc-001')} />);
    expect(screen.getByText('exec-abc-001')).toBeInTheDocument();
  });

  it('does not show reconciliation notice for EXECUTED', () => {
    wrap(<ExecuteStage {...withOutcome('executed', 'exec-001')} />);
    expect(screen.queryByTestId('reconciliation-notice')).not.toBeInTheDocument();
  });
});

describe('ExecuteStage — SSE fallback', () => {
  it('shows SSE EXECUTE events when no lifecycle data', () => {
    // SSE buffer is newest-first: EXECUTE (newer) before OBSERVE (anchor, older)
    const sseEvents = [
      makeSSEEvent({ id: '1', message: 'labor.allocate', detail: 'workers=w-1,w-2', ts: '2026-08-27T10:01:00Z' }),
      makeSSEEvent({ category: 'OBSERVE', id: '0', message: 'snapshot taken', ts: '2026-08-27T10:00:00Z' }),
    ];
    const analysis: AnalysisResult = { ...baseAnalysis, lifecycle: [], proposal_results: [] };
    wrap(<ExecuteStage {...makeExecuteProps({ sseEvents, analysisResult: analysis })} />);
    expect(screen.getByText('labor.allocate')).toBeInTheDocument();
  });

  it('shows waiting message when no data at all', () => {
    const analysis: AnalysisResult = { ...baseAnalysis, lifecycle: [], proposal_results: [] };
    wrap(<ExecuteStage {...makeExecuteProps({ analysisResult: analysis, sseEvents: [] })} />);
    expect(screen.getByTestId('execute-waiting')).toBeInTheDocument();
  });
});

// ══════════════════════════════════════════════════════════════════════════════
// OutcomeStage tests
// ══════════════════════════════════════════════════════════════════════════════

describe('OutcomeStage — routing', () => {
  it('StageContentPane routes OUTCOME → outcome-stage', () => {
    wrap(<StageContentPane {...makeOutcomeProps()} />);
    expect(screen.getByTestId('outcome-stage')).toBeInTheDocument();
  });
});

describe('OutcomeStage — observed impact label', () => {
  it('shows OBSERVED OPERATIONAL IMPACT header', () => {
    wrap(<OutcomeStage {...makeOutcomeProps()} />);
    expect(screen.getByText(/OBSERVED OPERATIONAL IMPACT/i)).toBeInTheDocument();
  });

  it('does not contain "Projected impact" wording anywhere', () => {
    wrap(<OutcomeStage {...makeOutcomeProps()} />);
    expect(screen.queryByText(/projected impact/i)).not.toBeInTheDocument();
  });
});

describe('OutcomeStage — atomic pre/post KPI data', () => {
  it('uses pre_kpis value for "before" column (wave risk)', () => {
    wrap(<OutcomeStage {...makeOutcomeProps()} />);
    // pre wave_risk_score = 0.92; post = 0.55
    expect(screen.getByText('0.9')).toBeInTheDocument();   // pre (1 dp)
    expect(screen.getByText('0.6')).toBeInTheDocument();   // post (1 dp)
  });

  it('uses pre_kpis value for "before" column (pending backlog)', () => {
    wrap(<OutcomeStage {...makeOutcomeProps()} />);
    // pre = 7, post = 4
    expect(screen.getByText('7.0')).toBeInTheDocument();
    expect(screen.getByText('4.0')).toBeInTheDocument();
  });

  it('shows negative delta for pending backlog (improvement)', () => {
    wrap(<OutcomeStage {...makeOutcomeProps()} />);
    // kpi_delta.pending_backlog = -3
    expect(screen.getByText('-3.0')).toBeInTheDocument();
  });

  it('shows positive delta for wave completion (improvement)', () => {
    wrap(<OutcomeStage {...makeOutcomeProps()} />);
    // kpi_delta.wave_completion_pct = +18
    expect(screen.getByText('+18.0%')).toBeInTheDocument();
  });

  it('shows positive delta for labor utilization (improvement)', () => {
    wrap(<OutcomeStage {...makeOutcomeProps()} />);
    // kpi_delta.labor_utilization_pct = +10
    expect(screen.getByText('+10.0%')).toBeInTheDocument();
  });

  it('renders before/after column headers', () => {
    wrap(<OutcomeStage {...makeOutcomeProps()} />);
    expect(screen.getByText('BEFORE')).toBeInTheDocument();
    expect(screen.getByText('AFTER')).toBeInTheDocument();
    expect(screen.getByText('DELTA')).toBeInTheDocument();
  });
});

describe('OutcomeStage — time to recovery', () => {
  it('shows recovery time when post_kpis.time_to_recovery_seconds is set', () => {
    // postKPISnapshot has time_to_recovery_seconds: 240
    wrap(<OutcomeStage {...makeOutcomeProps()} />);
    expect(screen.getByTestId('recovery-time')).toBeInTheDocument();
    // 240s = 4m
    expect(screen.getByTestId('recovery-time')).toHaveTextContent('4m');
  });

  it('shows RECOVERY NOT YET REACHED when time_to_recovery_seconds is null', () => {
    const post = { ...postKPISnapshot, time_to_recovery_seconds: null };
    const analysis = { ...baseAnalysis, post_kpis: post };
    wrap(<OutcomeStage {...makeOutcomeProps({ analysisResult: analysis })} />);
    expect(screen.getByTestId('recovery-not-reached')).toBeInTheDocument();
    expect(screen.getByTestId('recovery-not-reached')).toHaveTextContent('RECOVERY NOT YET REACHED');
  });

  it('shows recovery in seconds when < 60s', () => {
    const post = { ...postKPISnapshot, time_to_recovery_seconds: 45 };
    const analysis = { ...baseAnalysis, post_kpis: post };
    wrap(<OutcomeStage {...makeOutcomeProps({ analysisResult: analysis })} />);
    expect(screen.getByTestId('recovery-time')).toHaveTextContent('45s');
  });
});

describe('OutcomeStage — execution result section', () => {
  it('shows execution result section when proposal_results exist', () => {
    wrap(<OutcomeStage {...makeOutcomeProps()} />);
    expect(screen.getByText(/Execution Result/i)).toBeInTheDocument();
  });

  it('execution result section is distinct from operational outcome section', () => {
    wrap(<OutcomeStage {...makeOutcomeProps()} />);
    // Both sections must be present and independently identifiable
    expect(screen.getByText(/Execution Result/i)).toBeInTheDocument();
    expect(screen.getByText(/Observed Operational Impact/i)).toBeInTheDocument();
  });
});

describe('OutcomeStage — KPI history chart', () => {
  it('renders KPI history chart area', () => {
    wrap(<OutcomeStage {...makeOutcomeProps()} />);
    // KPITrendChart renders an SVG when history.length >= 2
    const svgOrBox = document.querySelector('svg, [role="img"]');
    expect(svgOrBox).toBeTruthy();
  });

  it('shows no-kpi-data message when analysisResult lacks pre/post KPIs', () => {
    const analysis = { ...baseAnalysis, pre_kpis: undefined, post_kpis: undefined, kpi_delta: undefined };
    wrap(<OutcomeStage {...makeOutcomeProps({ analysisResult: analysis })} />);
    expect(screen.getByTestId('no-kpi-data')).toBeInTheDocument();
  });
});

describe('OutcomeStage — end-state actions', () => {
  it('shows VIEW CONTROL vs MAIW button', () => {
    wrap(<OutcomeStage {...makeOutcomeProps()} />);
    expect(screen.getByTestId('counterfactual-button')).toBeInTheDocument();
    expect(screen.getByTestId('counterfactual-button')).toHaveTextContent('VIEW CONTROL vs MAIW');
  });

  it('clicking VIEW CONTROL vs MAIW shows counterfactual panel', () => {
    wrap(<OutcomeStage {...makeOutcomeProps()} />);
    fireEvent.click(screen.getByTestId('counterfactual-button'));
    expect(screen.getByTestId('counterfactual-panel-inline')).toBeInTheDocument();
  });

  it('clicking VIEW CONTROL vs MAIW a second time hides the panel', () => {
    wrap(<OutcomeStage {...makeOutcomeProps()} />);
    fireEvent.click(screen.getByTestId('counterfactual-button'));
    expect(screen.getByTestId('counterfactual-panel-inline')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('counterfactual-button'));
    expect(screen.queryByTestId('counterfactual-panel-inline')).not.toBeInTheDocument();
  });

  it('shows RUN ANOTHER SCENARIO button', () => {
    wrap(<OutcomeStage {...makeOutcomeProps()} />);
    expect(screen.getByTestId('run-another-scenario-button')).toBeInTheDocument();
  });

  it('RUN ANOTHER SCENARIO calls onReset', () => {
    const onReset = jest.fn();
    wrap(<OutcomeStage {...makeOutcomeProps({ onReset })} />);
    fireEvent.click(screen.getByTestId('run-another-scenario-button'));
    expect(onReset).toHaveBeenCalledTimes(1);
  });
});
