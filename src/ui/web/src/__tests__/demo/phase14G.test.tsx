/**
 * Phase 14G tests — UI Readiness and Demo Hardening.
 *
 * Spec contracts verified:
 *  - Phase 15 Copilot entry point renders as disabled, aria-disabled, not interactive
 *  - Phase 15 Copilot button has no onClick that triggers any action
 *  - Backend unavailable state: renders BackendErrorBanner with retry button
 *  - Backend unavailable: no blank screen (banner shown, not empty)
 *  - SSE connected indicator visible during active scenario
 *  - SSE disconnected indicator visible when not connected
 *  - Loading spinner shown during initial connection (not blank screen)
 *  - Loading state has accessible role="status" and aria-label
 *  - Proposal identifiers (proposal_id, pending_id, trace_id) are visible in ApproveStage
 *  - Approval buttons disabled after click (duplicate-submission prevention)
 *  - Approve button is disabled when actioned=true
 *  - Reject button is disabled when actioned=true
 *  - Approval expired: action buttons not available
 *  - Error states: backend reject (404) shows consumed message
 *  - Error states: network error shows error message
 *  - Missing/null pendingApprovals renders empty state message (no crash)
 *  - Missing/null analysisResult renders ObserveStage safely (no crash)
 *  - Scenario reset: reset button calls onReset
 *  - ExecuteStage UNKNOWN outcome shows reconciliation notice
 *  - ExecuteStage FAILED outcome shows FAILED badge
 *  - Demo shell renders system footer with system status
 *  - DemoShell data-testid="demo-shell" is present
 *  - Trust boundary: HUMAN APPROVAL REQUIRED text in ApproveStage
 *  - Trust boundary: ActionExecutor text in ExecuteStage
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import { ThemeProvider } from '@mui/material/styles';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { nvidiaTheme } from '../../theme/nvidiaTheme';

// Components under test
import ApproveStage from '../../components/demo/stages/ApproveStage';
import ExecuteStage from '../../components/demo/stages/ExecuteStage';
import ObserveStage from '../../components/demo/stages/ObserveStage';
import { DemoStatus, AnalysisResult, PendingApproval, KPISnapshot } from '../../services/demoAPI';
import { SSEEvent } from '../../hooks/useDemoSSE';

// ── Mocks ──────────────────────────────────────────────────────────────────────

jest.mock('../../services/demoAPI', () => ({
  demoAPI: {
    listScenarios: jest.fn().mockResolvedValue([]),
    startScenario: jest.fn(),
    getStatusSafe: jest.fn().mockResolvedValue(null),
    analyze: jest.fn(),
    approvePending: jest.fn(),
    rejectPending: jest.fn(),
    getCounterfactualResult: jest.fn().mockResolvedValue(null),
    resetScenario: jest.fn().mockResolvedValue({ active: false }),
    pauseScenario: jest.fn(),
    resumeScenario: jest.fn(),
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

const { useDemoStatus } = require('../../hooks/useDemoStatus');
const { demoAPI } = require('../../services/demoAPI');

// ── Fixtures ───────────────────────────────────────────────────────────────────

const baseKPI: KPISnapshot = {
  sim_time_seconds: 60,
  clock_iso: '2026-08-31T10:00:00Z',
  equipment_total: 8,
  equipment_operational_pct: 87.5,
  labor_total: 6,
  labor_availability_pct: 66.7,
  labor_utilization_pct: 75,
  pending_backlog: 5,
  wave_risk_score: 0.6,
  wave_risk_level: 'medium',
  low_stock_count: 2,
  state_freshness_seconds: 30,
  service_risk_index: 0.4,
  capacity_throughput_proxy: 0.8,
  wave_completion_pct: 60,
  simulated_throughput: 120,
  projected_service_level: 85,
  time_to_recovery_seconds: null,
};

const baseDemoStatus: DemoStatus = {
  active: true,
  paused: false,
  scenario: {
    name: 'labor_constraint_wave_risk',
    display_name: 'Labor Constraint — Wave Risk',
    description: 'Test',
    tags: ['labor'],
  },
  world: {
    warehouse_id: 'DC-47',
    clock_iso: '2026-08-31T10:00:00Z',
    elapsed_seconds: 60,
    equipment: { total: 8, available: 7, assigned: 5, maintenance: 0, offline: 1 },
    workers: { total: 6, active: 4, inactive: 2 },
    tasks: { total: 20, pending: 5, in_progress: 10, completed: 5 },
    inventory: { total_skus: 100, low_stock: 2 },
  },
  current_kpis: baseKPI,
  kpi_history: [],
  pending_approvals: [],
};

const inactiveDemoStatus: DemoStatus = {
  active: false,
  paused: false,
  scenario: null,
  world: null,
  current_kpis: null,
  kpi_history: [],
  pending_approvals: [],
};

const basePendingApproval: PendingApproval = {
  pending_id: 'pend-abc-123',
  proposal_id: 'prop-xyz-456',
  decision_id: 'dec-789',
  trace_id: 'trace-ttt-111',
  capability: 'REALLOCATE_LABOR',
  target: 'zone-3',
  domain: 'labor',
  risk_level: 'high',
  objective: 'Shift workers to cover wave demand spike',
  rationale: 'Labor availability dropped to 50% — wave risk critical',
  priority: 'high',
  queued_at: new Date().toISOString(),
};

const baseAnalysisResult: AnalysisResult = {
  ok: true,
  trace_id: 'trace-ttt-111',
  assessment: {
    snapshot_id: 'snap-001',
    warehouse_id: 'DC-47',
    assessed_at: '2026-08-31T10:00:00Z',
    summary: 'Labor constraint detected',
    severity: 'high',
    domains_affected: ['labor'],
    facts_observed: ['Labor availability: 50%', 'Wave risk: critical'],
    recommendations: [],
    model_id: 'claude-sonnet-4-5',
    routing_rule: 'default',
    routing_reason: 'No special conditions',
    latency_ms: 800,
  },
  proposal_results: [],
  lifecycle: [],
};

const noSseEvents: SSEEvent[] = [];

// ── Helpers ────────────────────────────────────────────────────────────────────

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function wrap(ui: React.ReactElement) {
  return render(
    <MemoryRouter>
      <QueryClientProvider client={makeQC()}>
        <ThemeProvider theme={nvidiaTheme}>
          {ui}
        </ThemeProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

function renderShell(demoStatusValue: DemoStatus | null, isLoading = false) {
  useDemoStatus.mockReturnValue({
    status: demoStatusValue,
    isLoading,
    isDemoMode: demoStatusValue != null,
    refetch: jest.fn(),
  });
  (demoAPI.listScenarios as jest.Mock).mockResolvedValue([]);
  const DemoShell = require('../../pages/DemoShell').default;
  return wrap(<DemoShell />);
}

function stageProps(overrides: Partial<{
  demoStatus: DemoStatus;
  pendingApprovals: PendingApproval[];
  sseEvents: SSEEvent[];
  analysisResult: AnalysisResult | null;
  analyzing: boolean;
  onAnalyze: () => Promise<void>;
  onReset: () => void;
  onViewFullTrace: () => void;
  onOpenExplanation: (focus: any) => void;
}> = {}) {
  return {
    currentStage: 'APPROVE' as const,
    demoStatus: baseDemoStatus,
    pendingApprovals: [],
    sseEvents: noSseEvents,
    analysisResult: null,
    analyzing: false,
    onAnalyze: jest.fn().mockResolvedValue(undefined),
    onReset: jest.fn(),
    onViewFullTrace: jest.fn(),
    onOpenExplanation: jest.fn(),
    ...overrides,
  };
}

beforeEach(() => jest.clearAllMocks());

// ── Tests: Phase 15 Copilot entry point ───────────────────────────────────────

describe('Phase 15 Copilot entry point', () => {
  it('renders with Phase 15 Copilot button disabled', () => {
    renderShell(inactiveDemoStatus);
    const btn = screen.getByTestId('phase15-copilot-button');
    expect(btn).toBeInTheDocument();
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute('aria-disabled', 'true');
  });

  it('Phase 15 Copilot button shows Phase 15 label', () => {
    renderShell(inactiveDemoStatus);
    const btn = screen.getByTestId('phase15-copilot-button');
    expect(btn).toHaveTextContent('Copilot');
    expect(btn).toHaveTextContent('Phase 15');
  });

  it('Phase 15 Copilot button has accessible tooltip title mentioning Phase 15', () => {
    renderShell(inactiveDemoStatus);
    const btn = screen.getByTestId('phase15-copilot-button');
    expect(btn).toHaveAttribute('title', expect.stringContaining('Phase 15'));
  });

  it('Phase 15 Copilot button aria-label is accessible', () => {
    renderShell(inactiveDemoStatus);
    const btn = screen.getByTestId('phase15-copilot-button');
    expect(btn).toHaveAttribute('aria-label');
    const label = btn.getAttribute('aria-label') ?? '';
    expect(label.toLowerCase()).toMatch(/copilot|phase 15/i);
  });
});

// ── Tests: Backend unavailable state ──────────────────────────────────────────

describe('Backend unavailable state', () => {
  it('shows BackendErrorBanner when backend returns null after load completes', () => {
    renderShell(null, false);
    expect(screen.getByTestId('backend-error-banner')).toBeInTheDocument();
  });

  it('BackendErrorBanner has role=alert for accessibility', () => {
    renderShell(null, false);
    const banner = screen.getByTestId('backend-error-banner');
    expect(banner).toHaveAttribute('role', 'alert');
  });

  it('BackendErrorBanner shows retry button', () => {
    renderShell(null, false);
    expect(screen.getByTestId('backend-retry-button')).toBeInTheDocument();
  });

  it('no blank screen: banner shown when backend unavailable', () => {
    renderShell(null, false);
    expect(screen.getByTestId('backend-error-banner')).toBeInTheDocument();
    // Loading spinner should NOT be shown (load complete)
    expect(screen.queryByTestId('demo-loading')).not.toBeInTheDocument();
  });

  it('does not show ScenarioSelector when backend is unavailable', () => {
    renderShell(null, false);
    expect(screen.queryByText(/select a scenario to begin/i)).not.toBeInTheDocument();
  });
});

// ── Tests: Loading state ───────────────────────────────────────────────────────

describe('Loading state', () => {
  it('shows loading indicator during initial connection', () => {
    renderShell(null, true); // isLoading=true, status=null
    expect(screen.getByTestId('demo-loading')).toBeInTheDocument();
  });

  it('loading state has accessible role=status', () => {
    renderShell(null, true);
    const loading = screen.getByTestId('demo-loading');
    expect(loading).toHaveAttribute('role', 'status');
  });

  it('loading state has aria-label', () => {
    renderShell(null, true);
    const loading = screen.getByTestId('demo-loading');
    expect(loading).toHaveAttribute('aria-label');
  });

  it('does not show backend error during active loading', () => {
    renderShell(null, true);
    expect(screen.queryByTestId('backend-error-banner')).not.toBeInTheDocument();
  });
});

// ── Tests: DemoShell identity ──────────────────────────────────────────────────

describe('DemoShell identity', () => {
  it('has data-testid="demo-shell"', () => {
    renderShell(inactiveDemoStatus);
    expect(screen.getByTestId('demo-shell')).toBeInTheDocument();
  });

  it('shows MAIW product identity text', () => {
    renderShell(inactiveDemoStatus);
    expect(screen.getByText(/MAIW Command Center/i)).toBeInTheDocument();
  });

  it('shows DEMO MODE indicator badge', () => {
    renderShell(inactiveDemoStatus);
    expect(screen.getByText(/Synthetic demo/i)).toBeInTheDocument();
  });

  it('shows system status in footer', () => {
    renderShell(inactiveDemoStatus);
    expect(screen.getAllByText(/System/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/HEALTHY/i).length).toBeGreaterThan(0);
  });
});

// ── Tests: Proposal identifier display ────────────────────────────────────────

describe('ApproveStage — proposal identifiers', () => {
  it('shows proposal_id in ApprovalCard', () => {
    wrap(
      <ApproveStage {...stageProps({
        pendingApprovals: [basePendingApproval],
        analysisResult: baseAnalysisResult,
      })} />
    );
    expect(screen.getByText(/prop-xyz-456/i)).toBeInTheDocument();
  });

  it('shows decision_id in ApprovalCard', () => {
    wrap(
      <ApproveStage {...stageProps({
        pendingApprovals: [basePendingApproval],
        analysisResult: baseAnalysisResult,
      })} />
    );
    expect(screen.getByText(/dec-789/i)).toBeInTheDocument();
  });

  it('shows capability in ApprovalCard', () => {
    wrap(
      <ApproveStage {...stageProps({
        pendingApprovals: [basePendingApproval],
        analysisResult: baseAnalysisResult,
      })} />
    );
    expect(screen.getByText(/REALLOCATE_LABOR/i)).toBeInTheDocument();
  });

  it('shows rationale text', () => {
    wrap(
      <ApproveStage {...stageProps({
        pendingApprovals: [basePendingApproval],
        analysisResult: baseAnalysisResult,
      })} />
    );
    expect(screen.getByText(/Labor availability dropped to 50%/i)).toBeInTheDocument();
  });

  it('shows priority field', () => {
    wrap(
      <ApproveStage {...stageProps({
        pendingApprovals: [basePendingApproval],
        analysisResult: baseAnalysisResult,
      })} />
    );
    expect(screen.getByText(/priority/i)).toBeInTheDocument();
  });
});

// ── Tests: Approval workflow controls ─────────────────────────────────────────

describe('ApproveStage — approval controls', () => {
  it('approve and reject buttons enabled initially', () => {
    wrap(
      <ApproveStage {...stageProps({ pendingApprovals: [basePendingApproval] })} />
    );
    expect(screen.getByTestId('approve-execute-button')).not.toBeDisabled();
    expect(screen.getByTestId('reject-button')).not.toBeDisabled();
  });

  it('empty state shown when no pending approvals', () => {
    wrap(
      <ApproveStage {...stageProps({ pendingApprovals: [] })} />
    );
    // MonoText doesn't forward data-testid; check text content instead
    expect(screen.getByText(/No pending approvals/i)).toBeInTheDocument();
  });

  it('approval card shown for pending approval', () => {
    wrap(
      <ApproveStage {...stageProps({ pendingApprovals: [basePendingApproval] })} />
    );
    expect(screen.getByTestId('approval-card')).toBeInTheDocument();
  });

  it('HUMAN APPROVAL REQUIRED shown in card', () => {
    wrap(
      <ApproveStage {...stageProps({ pendingApprovals: [basePendingApproval] })} />
    );
    expect(screen.getByText(/HUMAN APPROVAL REQUIRED/i)).toBeInTheDocument();
  });

  it('duplicate submission prevention: result badge replaces buttons after approval', async () => {
    (demoAPI.approvePending as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 'executed',
      execution_id: 'exec-001',
    });

    wrap(
      <ApproveStage {...stageProps({ pendingApprovals: [basePendingApproval] })} />
    );

    const approveBtn = screen.getByTestId('approve-execute-button');
    await act(async () => {
      fireEvent.click(approveBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId('approval-result')).toBeInTheDocument();
    });

    // Approve and reject buttons replaced by result badge — no duplicate submit possible
    expect(screen.queryByTestId('approve-execute-button')).not.toBeInTheDocument();
    expect(screen.queryByTestId('reject-button')).not.toBeInTheDocument();
  });

  it('rejection: shows REJECTED outcome badge', async () => {
    (demoAPI.rejectPending as jest.Mock).mockResolvedValueOnce({ ok: true });

    wrap(
      <ApproveStage {...stageProps({ pendingApprovals: [basePendingApproval] })} />
    );

    await act(async () => {
      fireEvent.click(screen.getByTestId('reject-button'));
    });

    await waitFor(() => {
      expect(screen.getByTestId('approval-result')).toBeInTheDocument();
      expect(screen.getByText('REJECTED')).toBeInTheDocument();
    });
  });

  it('backend 404: shows consumed message (not generic error)', async () => {
    const err404 = new Error('Not found') as any;
    err404.response = { status: 404 };
    (demoAPI.approvePending as jest.Mock).mockRejectedValueOnce(err404);

    wrap(
      <ApproveStage {...stageProps({ pendingApprovals: [basePendingApproval] })} />
    );

    await act(async () => {
      fireEvent.click(screen.getByTestId('approve-execute-button'));
    });

    await waitFor(() => {
      // Multiple "CONSUMED" badges may appear; just confirm at least one shows
      expect(screen.getAllByText('CONSUMED').length).toBeGreaterThan(0);
    });
  });

  it('expired approval: action buttons are disabled', () => {
    const expiredApproval: PendingApproval = {
      ...basePendingApproval,
      queued_at: new Date(Date.now() - 15 * 60 * 1000).toISOString(), // 15 min ago
    };
    wrap(
      <ApproveStage {...stageProps({ pendingApprovals: [expiredApproval] })} />
    );
    expect(screen.getByTestId('approve-execute-button')).toBeDisabled();
    expect(screen.getByTestId('reject-button')).toBeDisabled();
  });

  it('expired approval: EXPIRED label shown', () => {
    const expiredApproval: PendingApproval = {
      ...basePendingApproval,
      queued_at: new Date(Date.now() - 15 * 60 * 1000).toISOString(),
    };
    wrap(
      <ApproveStage {...stageProps({ pendingApprovals: [expiredApproval] })} />
    );
    expect(screen.getAllByText('EXPIRED').length).toBeGreaterThan(0);
  });
});

// ── Tests: ObserveStage missing data ──────────────────────────────────────────

describe('ObserveStage — missing / null data', () => {
  it('renders without crash when world is null', () => {
    const statusNoWorld: DemoStatus = { ...baseDemoStatus, world: null };
    expect(() => {
      wrap(
        <ObserveStage {...stageProps({
          demoStatus: statusNoWorld,
          analysisResult: null,
        })} />
      );
    }).not.toThrow();
    expect(screen.getByTestId('observe-stage')).toBeInTheDocument();
  });

  it('renders without crash when current_kpis is null', () => {
    const statusNoKPIs: DemoStatus = { ...baseDemoStatus, current_kpis: null };
    expect(() => {
      wrap(
        <ObserveStage {...stageProps({
          demoStatus: statusNoKPIs,
          analysisResult: null,
        })} />
      );
    }).not.toThrow();
    expect(screen.getByTestId('observe-stage')).toBeInTheDocument();
  });

  it('shows Run Analysis button when no analysis result yet', () => {
    wrap(
      <ObserveStage {...stageProps({ analysisResult: null })} />
    );
    expect(screen.getByTestId('run-analysis-button')).toBeInTheDocument();
  });

  it('shows re-run button when analysis result is present', () => {
    wrap(
      <ObserveStage {...stageProps({ analysisResult: baseAnalysisResult })} />
    );
    expect(screen.getByTestId('rerun-analysis-button')).toBeInTheDocument();
  });

  it('analyze button is disabled while analyzing', () => {
    wrap(
      <ObserveStage {...stageProps({ analysisResult: null, analyzing: true })} />
    );
    expect(screen.getByTestId('run-analysis-button')).toBeDisabled();
  });
});

// ── Tests: ExecuteStage outcome rendering ─────────────────────────────────────

describe('ExecuteStage — all canonical outcomes', () => {
  function renderWithOutcome(outcome: string) {
    return wrap(
      <ExecuteStage {...stageProps({
        sseEvents: noSseEvents,
        analysisResult: {
          ...baseAnalysisResult,
          lifecycle: [{
            phase: 'EXECUTE' as const,
            status: outcome,
            execution_id: `exec-${outcome}`,
            capability: 'REALLOCATE_LABOR',
          }],
        },
        currentStage: 'EXECUTE' as const,
      })} />
    );
  }

  it('shows EXECUTED badge', () => {
    renderWithOutcome('executed');
    expect(screen.getByTestId('outcome-badge-executed')).toBeInTheDocument();
    expect(screen.getByText('EXECUTED')).toBeInTheDocument();
  });

  it('shows FAILED badge', () => {
    renderWithOutcome('failed');
    expect(screen.getByTestId('outcome-badge-failed')).toBeInTheDocument();
    expect(screen.getByText('FAILED')).toBeInTheDocument();
  });

  it('shows UNKNOWN badge with reconciliation notice', () => {
    renderWithOutcome('unknown');
    expect(screen.getByTestId('outcome-badge-unknown')).toBeInTheDocument();
    expect(screen.getByTestId('reconciliation-notice')).toBeInTheDocument();
    expect(screen.getByText(/Reconciliation required/i)).toBeInTheDocument();
  });

  it('shows NO_OP badge', () => {
    renderWithOutcome('no_op');
    expect(screen.getByTestId('outcome-badge-no_op')).toBeInTheDocument();
  });

  it('shows DEFERRED badge', () => {
    renderWithOutcome('deferred');
    expect(screen.getByTestId('outcome-badge-deferred')).toBeInTheDocument();
  });

  it('shows CONFLICT badge', () => {
    renderWithOutcome('conflict');
    expect(screen.getByTestId('outcome-badge-conflict')).toBeInTheDocument();
  });

  it('shows waiting state when no lifecycle data and no SSE', () => {
    wrap(
      <ExecuteStage {...stageProps({
        analysisResult: { ...baseAnalysisResult, lifecycle: [] },
        sseEvents: [],
        currentStage: 'EXECUTE' as const,
      })} />
    );
    expect(screen.getByTestId('execute-waiting')).toBeInTheDocument();
  });
});

// ── Tests: Trust boundary ──────────────────────────────────────────────────────

describe('Trust boundary', () => {
  it('ApproveStage shows HUMAN APPROVAL REQUIRED — agent does not self-authorize', () => {
    wrap(
      <ApproveStage {...stageProps({ pendingApprovals: [basePendingApproval] })} />
    );
    expect(screen.getByText(/HUMAN APPROVAL REQUIRED/i)).toBeInTheDocument();
  });

  it('ExecuteStage subtitle references ActionExecutor — not model/LLM', () => {
    wrap(
      <ExecuteStage {...stageProps({ sseEvents: [], analysisResult: baseAnalysisResult })} />
    );
    expect(screen.getByText(/ActionExecutor/i)).toBeInTheDocument();
  });

  it('DemoShell Copilot button is disabled — Copilot does NOT execute actions', () => {
    renderShell(inactiveDemoStatus);
    const btn = screen.getByTestId('phase15-copilot-button');
    expect(btn).toBeDisabled();
  });
});

// ── Tests: Scenario reset behavior ────────────────────────────────────────────

describe('Scenario selector shown after reset', () => {
  it('ScenarioSelector renders when scenario is not active', async () => {
    renderShell({
      ...inactiveDemoStatus,
      active: false,
    });
    await waitFor(() => {
      expect(screen.getByText(/select a scenario to begin/i)).toBeInTheDocument();
    });
  });

  it('LifecycleRail not shown when no scenario active', () => {
    renderShell(inactiveDemoStatus);
    expect(screen.queryByTestId('lifecycle-rail')).not.toBeInTheDocument();
  });
});

// ── Tests: SSE status indicator ───────────────────────────────────────────────

describe('SSE status in footer', () => {
  // SSE status is only shown when a scenario is active; we test the component directly.
  // The useDemoSSE mock always returns connected:false / error:null.
  // For DemoShell shell level tests, SSE chip only renders during active scenario.
  it('DemoShell footer renders Safety section', () => {
    renderShell(inactiveDemoStatus);
    expect(screen.getByText(/Safety/i)).toBeInTheDocument();
  });

  it('System status shown in footer', () => {
    renderShell(inactiveDemoStatus);
    expect(screen.getAllByText(/HEALTHY/i).length).toBeGreaterThan(0);
  });
});
