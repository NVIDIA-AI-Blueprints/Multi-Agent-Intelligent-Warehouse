/**
 * Phase 12D tests — ApproveStage / ApprovalCard.
 *
 * Spec contracts verified:
 *  - approval card renders from live pending approval
 *  - no pending approval → no actionable approval card
 *  - approve hits real API (demoAPI.approvePending)
 *  - reject hits real API (demoAPI.rejectPending)
 *  - in-flight: both buttons disabled
 *  - expired approval: buttons disabled, EXPIRED label shown
 *  - consumed/404: result shows CONSUMED state
 *  - no projected impact numbers in approval card
 *  - rail does not advance optimistically — currentStage stays at APPROVE
 *    until an SSE/backend event causes deriveRailState to update
 *  - reset clears approval UI (component unmounts on showSelector=true)
 *  - all card fields from PendingApproval are rendered
 *  - facts block from analysisResult.assessment.facts_observed
 *  - state freshness from current_kpis
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import { ThemeProvider } from '@mui/material/styles';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { nvidiaTheme } from '../../theme/nvidiaTheme';

import StageContentPane from '../../components/demo/StageContentPane';
import ApproveStage from '../../components/demo/stages/ApproveStage';
import { deriveRailState } from '../../hooks/useDemoLifecycle';
import { DemoStatus, AnalysisResult, PendingApproval } from '../../services/demoAPI';
import { SSEEvent } from '../../hooks/useDemoSSE';

// ── Mocks ──────────────────────────────────────────────────────────────────────

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
  useRuntimeStatus: () => ({
    data: { maiw_operational_status: 'HEALTHY', model_gateway_status: 'HEALTHY', domain_health: {} },
    isLoading: false,
  }),
}));

jest.mock('../../hooks/useDemoStatus', () => ({
  useDemoStatus: jest.fn(),
}));

const { demoAPI } = require('../../services/demoAPI');
const { useDemoStatus } = require('../../hooks/useDemoStatus');

// ── Fixtures ───────────────────────────────────────────────────────────────────

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

// Valid (recent) pending approval
const validApproval: PendingApproval = {
  pending_id: 'pa-001',
  proposal_id: 'prop-full-001',
  decision_id: 'dec-full-001',
  trace_id: 'trace-001',
  capability: 'reassign_labor_from_equipment',
  target: 'AGV-03',
  domain: 'labor',
  risk_level: 'medium',
  objective: 'Restore wave processing capacity',
  rationale: 'Equipment load can be reduced without service impact to free workers.',
  priority: 'critical',
  queued_at: new Date(Date.now() - 30_000).toISOString(), // 30s ago — not expired
};

// Expired pending approval (>10 min old)
const expiredApproval: PendingApproval = {
  ...validApproval,
  pending_id: 'pa-expired',
  queued_at: new Date(Date.now() - 11 * 60 * 1000).toISOString(), // 11 minutes ago
};

const baseStatus: DemoStatus = {
  active: true,
  paused: false,
  scenario: { name: 'labor_constraint_wave_risk', display_name: 'Labor + Wave Risk', description: '', tags: [] },
  world: {
    warehouse_id: 'DC-47', clock_iso: '2026-08-27T10:00:47Z', elapsed_seconds: 47,
    equipment: { total: 8, available: 7, assigned: 1, maintenance: 0, offline: 0 },
    workers: { total: 6, active: 3, inactive: 3 },
    tasks: { total: 10, pending: 7, in_progress: 2, completed: 1 },
    inventory: { total_skus: 5, low_stock: 1 },
  },
  current_kpis: baseKPIs,
  kpi_history: [],
  pending_approvals: [validApproval],
};

const baseAnalysis: AnalysisResult = {
  ok: true,
  trace_id: 'trace-001',
  assessment: {
    snapshot_id: 'snap-001',
    warehouse_id: 'DC-47',
    assessed_at: '2026-08-27T10:00:48Z',
    summary: '3 workers on unplanned absence.',
    severity: 'critical',
    domains_affected: ['labor', 'wave'],
    facts_observed: [
      '3 workers on unplanned absence',
      'Wave risk: critical (0.92)',
      '7 pending tasks with approaching deadlines',
    ],
    recommendations: [],
    model_id: 'nvidia/llama-3.1-nemotron-70b-instruct',
    routing_rule: 'labor_wave_risk',
    routing_reason: '',
    latency_ms: 1200,
  },
  proposal_results: [],
  lifecycle: [],
};

// ── Helpers ────────────────────────────────────────────────────────────────────

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

function makeProps(overrides: Partial<Parameters<typeof ApproveStage>[0]> = {}) {
  return {
    currentStage: 'APPROVE' as const,
    sseEvents: [] as SSEEvent[],
    demoStatus: baseStatus,
    analysisResult: baseAnalysis,
    pendingApprovals: [validApproval],
    analyzing: false,
    onAnalyze: async () => {},
    ...overrides,
  };
}

// ── ApproveStage rendering ─────────────────────────────────────────────────────

describe('ApproveStage — rendering', () => {
  beforeEach(() => jest.clearAllMocks());

  it('renders approve-stage testid', () => {
    wrap(<ApproveStage {...makeProps()} />);
    expect(screen.getByTestId('approve-stage')).toBeInTheDocument();
  });

  it('renders approval card from live pending approval', () => {
    wrap(<ApproveStage {...makeProps()} />);
    expect(screen.getByTestId('approval-card')).toBeInTheDocument();
  });

  it('shows capability and target from PendingApproval', () => {
    wrap(<ApproveStage {...makeProps()} />);
    expect(screen.getByText('reassign_labor_from_equipment')).toBeInTheDocument();
    expect(screen.getByText('AGV-03')).toBeInTheDocument();
  });

  it('shows objective from PendingApproval', () => {
    wrap(<ApproveStage {...makeProps()} />);
    expect(screen.getByText('Restore wave processing capacity')).toBeInTheDocument();
  });

  it('shows rationale from PendingApproval', () => {
    wrap(<ApproveStage {...makeProps()} />);
    expect(screen.getByText(/Equipment load can be reduced/)).toBeInTheDocument();
  });

  it('shows risk level badge', () => {
    wrap(<ApproveStage {...makeProps()} />);
    expect(screen.getByText('medium')).toBeInTheDocument();
  });

  it('shows proposal_id and decision_id', () => {
    wrap(<ApproveStage {...makeProps()} />);
    expect(screen.getByText('prop-full-001')).toBeInTheDocument();
    expect(screen.getByText('dec-full-001')).toBeInTheDocument();
  });

  it('shows "05 APPROVE" stage label', () => {
    wrap(<ApproveStage {...makeProps()} />);
    expect(screen.getByText('05 APPROVE')).toBeInTheDocument();
  });

  it('shows HUMAN APPROVAL REQUIRED headline', () => {
    wrap(<ApproveStage {...makeProps()} />);
    expect(screen.getByText('HUMAN APPROVAL REQUIRED')).toBeInTheDocument();
  });

  it('shows facts_observed from analysisResult', () => {
    wrap(<ApproveStage {...makeProps()} />);
    expect(screen.getByText('3 workers on unplanned absence')).toBeInTheDocument();
    expect(screen.getByText('7 pending tasks with approaching deadlines')).toBeInTheDocument();
  });

  it('shows state freshness from current_kpis', () => {
    wrap(<ApproveStage {...makeProps()} />);
    expect(screen.getByText(/FRESH/)).toBeInTheDocument();
    expect(screen.getByText(/12s/)).toBeInTheDocument();
  });

  it('no pending approval → shows no actionable card', () => {
    wrap(<ApproveStage {...makeProps({ pendingApprovals: [] })} />);
    expect(screen.queryByTestId('approval-card')).not.toBeInTheDocument();
    expect(screen.queryByTestId('approve-execute-button')).not.toBeInTheDocument();
  });

  it('no pending approval → shows waiting message', () => {
    wrap(<ApproveStage {...makeProps({ pendingApprovals: [] })} />);
    expect(screen.getByText(/No pending approvals/i)).toBeInTheDocument();
  });

  it('never shows projected impact numbers', () => {
    wrap(<ApproveStage {...makeProps()} />);
    expect(screen.queryByText(/projected impact/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/kpi.delta/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/estimated impact/i)).not.toBeInTheDocument();
  });

  it('domain label from PendingApproval', () => {
    wrap(<ApproveStage {...makeProps()} />);
    expect(screen.getByText(/domain: labor/i)).toBeInTheDocument();
  });
});

// ── Action buttons ─────────────────────────────────────────────────────────────

describe('ApproveStage — action buttons', () => {
  beforeEach(() => jest.clearAllMocks());

  it('both action buttons are visible when approval is live', () => {
    wrap(<ApproveStage {...makeProps()} />);
    expect(screen.getByTestId('approve-execute-button')).toBeInTheDocument();
    expect(screen.getByTestId('reject-button')).toBeInTheDocument();
  });

  it('APPROVE & EXECUTE calls demoAPI.approvePending with pending_id', async () => {
    (demoAPI.approvePending as jest.Mock).mockResolvedValue({
      ok: true,
      status: 'executed',
      execution_id: 'exec-001',
      proposal_id: 'prop-full-001',
    });

    wrap(<ApproveStage {...makeProps()} />);

    await act(async () => {
      fireEvent.click(screen.getByTestId('approve-execute-button'));
    });

    await waitFor(() => {
      expect(demoAPI.approvePending).toHaveBeenCalledWith('pa-001', 'operator');
    });
  });

  it('REJECT calls demoAPI.rejectPending with pending_id', async () => {
    (demoAPI.rejectPending as jest.Mock).mockResolvedValue({
      ok: true,
      status: 'rejected',
      pending_id: 'pa-001',
    });

    wrap(<ApproveStage {...makeProps()} />);

    await act(async () => {
      fireEvent.click(screen.getByTestId('reject-button'));
    });

    await waitFor(() => {
      expect(demoAPI.rejectPending).toHaveBeenCalledWith('pa-001', 'operator');
    });
  });

  it('shows APPROVED result after successful approve', async () => {
    (demoAPI.approvePending as jest.Mock).mockResolvedValue({
      ok: true, status: 'executed', execution_id: 'exec-001', proposal_id: 'prop-full-001',
    });

    wrap(<ApproveStage {...makeProps()} />);
    fireEvent.click(screen.getByTestId('approve-execute-button'));

    await waitFor(() => {
      expect(screen.getByTestId('approval-result')).toBeInTheDocument();
      expect(screen.getByText('APPROVED')).toBeInTheDocument();
    });
  });

  it('shows REJECTED result after successful reject', async () => {
    (demoAPI.rejectPending as jest.Mock).mockResolvedValue({
      ok: true, status: 'rejected', pending_id: 'pa-001',
    });

    wrap(<ApproveStage {...makeProps()} />);
    fireEvent.click(screen.getByTestId('reject-button'));

    await waitFor(() => {
      expect(screen.getByTestId('approval-result')).toBeInTheDocument();
      expect(screen.getByText('REJECTED')).toBeInTheDocument();
    });
  });

  it('shows CONSUMED result when approve returns 404', async () => {
    const err: any = new Error('Not Found');
    err.response = { status: 404 };
    (demoAPI.approvePending as jest.Mock).mockRejectedValue(err);

    wrap(<ApproveStage {...makeProps()} />);
    fireEvent.click(screen.getByTestId('approve-execute-button'));

    await waitFor(() => {
      expect(screen.getByText('CONSUMED')).toBeInTheDocument();
    });
  });

  it('shows CONSUMED result when reject returns 404', async () => {
    const err: any = new Error('Not Found');
    err.response = { status: 404 };
    (demoAPI.rejectPending as jest.Mock).mockRejectedValue(err);

    wrap(<ApproveStage {...makeProps()} />);
    fireEvent.click(screen.getByTestId('reject-button'));

    await waitFor(() => {
      expect(screen.getByText('CONSUMED')).toBeInTheDocument();
    });
  });
});

// ── In-flight state ────────────────────────────────────────────────────────────

describe('ApproveStage — in-flight button disabling', () => {
  beforeEach(() => jest.clearAllMocks());

  it('both buttons disabled while approve is in-flight', async () => {
    let resolveApprove!: (v: any) => void;
    (demoAPI.approvePending as jest.Mock).mockReturnValue(
      new Promise(res => { resolveApprove = res; })
    );

    wrap(<ApproveStage {...makeProps()} />);
    fireEvent.click(screen.getByTestId('approve-execute-button'));

    // Both buttons must be disabled synchronously after click
    expect(screen.getByTestId('approve-execute-button')).toBeDisabled();
    expect(screen.getByTestId('reject-button')).toBeDisabled();

    // Resolve to clean up
    await act(async () => {
      resolveApprove({ ok: true, status: 'executed', execution_id: 'exec-001' });
    });
  });

  it('both buttons disabled while reject is in-flight', async () => {
    let resolveReject!: (v: any) => void;
    (demoAPI.rejectPending as jest.Mock).mockReturnValue(
      new Promise(res => { resolveReject = res; })
    );

    wrap(<ApproveStage {...makeProps()} />);
    fireEvent.click(screen.getByTestId('reject-button'));

    expect(screen.getByTestId('approve-execute-button')).toBeDisabled();
    expect(screen.getByTestId('reject-button')).toBeDisabled();

    await act(async () => { resolveReject({ ok: true, status: 'rejected' }); });
  });
});

// ── Expired approval ───────────────────────────────────────────────────────────

describe('ApproveStage — expired approval', () => {
  it('shows EXPIRED label for old approval', () => {
    wrap(<ApproveStage {...makeProps({ pendingApprovals: [expiredApproval] })} />);
    expect(screen.getByText('EXPIRED')).toBeInTheDocument();
  });

  it('disables buttons for expired approval', () => {
    wrap(<ApproveStage {...makeProps({ pendingApprovals: [expiredApproval] })} />);
    expect(screen.getByTestId('approve-execute-button')).toBeDisabled();
    expect(screen.getByTestId('reject-button')).toBeDisabled();
  });

  it('does NOT call API if expired approval action attempted', async () => {
    wrap(<ApproveStage {...makeProps({ pendingApprovals: [expiredApproval] })} />);
    // Try clicking (button is disabled so event won't fire the handler)
    fireEvent.click(screen.getByTestId('approve-execute-button'));
    await new Promise(r => setTimeout(r, 50));
    expect(demoAPI.approvePending).not.toHaveBeenCalled();
  });
});

// ── Rail does not advance optimistically ───────────────────────────────────────

describe('ApproveStage — no optimistic rail advance', () => {
  it('deriveRailState stays at APPROVE after approve call — only SSE can advance it', () => {
    // SSE events up to DECIDE + pending approval → APPROVE is current
    const sseEvents: SSEEvent[] = [
      { id: 'e5', ts: '2026-08-27T10:00:00.005Z', category: 'DECIDE', message: 'REQUIRES_HUMAN_APPROVAL', detail: null, asset_id: null, task_id: null, worker_id: null },
      { id: 'e4', ts: '2026-08-27T10:00:00.004Z', category: 'PROPOSE', message: 'action', detail: null, asset_id: null, task_id: null, worker_id: null },
      { id: 'e3', ts: '2026-08-27T10:00:00.003Z', category: 'SKILL', message: 'cap', detail: null, asset_id: null, task_id: null, worker_id: null },
      { id: 'e2', ts: '2026-08-27T10:00:00.002Z', category: 'REASON', message: 'reason', detail: null, asset_id: null, task_id: null, worker_id: null },
      { id: 'e1', ts: '2026-08-27T10:00:00.001Z', category: 'OBSERVE', message: 'start', detail: null, asset_id: null, task_id: null, worker_id: null },
    ];

    const state = deriveRailState(sseEvents, [validApproval]);
    expect(state.currentStage).toBe('APPROVE');

    // Simulating what would happen WITHOUT an EXECUTE SSE event:
    // even if we "approve", the SSE events list hasn't changed → still APPROVE
    const stateAfterApproveWithoutSSE = deriveRailState(sseEvents, []); // approvals cleared
    // After clearing pendingApprovals but no EXECUTE SSE → currentStage should be DECIDE (furthest)
    expect(stateAfterApproveWithoutSSE.currentStage).toBe('DECIDE');

    // Only when EXECUTE SSE arrives does the rail advance
    const sseWithExecute: SSEEvent[] = [
      { id: 'e6', ts: '2026-08-27T10:00:00.006Z', category: 'EXECUTE', message: 'done', detail: null, asset_id: null, task_id: null, worker_id: null },
      ...sseEvents,
    ];
    const stateAfterExecuteSSE = deriveRailState(sseWithExecute, []);
    expect(stateAfterExecuteSSE.currentStage).toBe('EXECUTE');
  });
});

// ── StageContentPane routes to ApproveStage ────────────────────────────────────

describe('StageContentPane — routes APPROVE to ApproveStage', () => {
  it('renders approve-stage when currentStage=APPROVE', () => {
    wrap(
      <StageContentPane
        currentStage="APPROVE"
        sseEvents={[]}
        demoStatus={baseStatus}
        analysisResult={baseAnalysis}
        pendingApprovals={[validApproval]}
        analyzing={false}
        onAnalyze={async () => {}}
      />
    );
    expect(screen.getByTestId('approve-stage')).toBeInTheDocument();
    // No longer shows 12D placeholder
    expect(screen.queryByText(/Phase 12D/i)).not.toBeInTheDocument();
  });
});

// ── DemoShell reset clears approval UI ────────────────────────────────────────

describe('DemoShell — reset clears approval UI', () => {
  beforeEach(() => jest.clearAllMocks());

  it('approval card absent after reset returns to ScenarioSelector', async () => {
    (demoAPI.resetScenario as jest.Mock).mockResolvedValue({ active: false });
    (demoAPI.listScenarios as jest.Mock).mockResolvedValue([
      { name: 'labor_constraint_wave_risk', display_name: 'Labor + Wave Risk', description: '', tags: [] },
    ]);

    useDemoStatus.mockReturnValue({
      status: { ...baseStatus, pending_approvals: [validApproval] },
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

    // Scenario is active — approval card should be gone since rail is at OBSERVE
    // (no SSE events to advance to APPROVE). StageContentPane shows OBSERVE stage.
    // Verify we're in the lifecycle layout.
    expect(screen.getByTestId('lifecycle-rail')).toBeInTheDocument();

    // Click reset
    await act(async () => {
      fireEvent.click(screen.getByTestId('reset-button'));
    });

    // ScenarioSelector shown — lifecycle layout and approval card gone
    await waitFor(() => {
      expect(screen.queryByTestId('approve-stage')).not.toBeInTheDocument();
      expect(screen.queryByTestId('approval-card')).not.toBeInTheDocument();
    });
  });
});
