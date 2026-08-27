/**
 * Phase 12B tests — LifecycleRail, OperationalContextStrip, DemoShell lifecycle layout.
 *
 * Covers:
 *  - All seven rail nodes render
 *  - SKILL SSE maps to REASON rail node (no eighth node)
 *  - OBSERVE_OUTCOME SSE maps to OUTCOME rail node
 *  - APPROVE is a first-class node, distinct from DECIDE
 *  - complete / current / upcoming / waiting state transitions
 *  - KPI values come from DemoStatus.current_kpis (no hardcoding)
 *  - No scenario → ScenarioSelector
 *  - Scenario active → lifecycle layout (rail + context strip + workspace)
 *  - Reset clears lifecycle state (no historical stage leakage)
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@mui/material/styles';
import { nvidiaTheme } from '../../theme/nvidiaTheme';

import LifecycleRail from '../../components/demo/LifecycleRail';
import OperationalContextStrip from '../../components/demo/OperationalContextStrip';
import { deriveRailState, STAGE_ORDER } from '../../hooks/useDemoLifecycle';
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
  useRuntimeStatus: () => ({ data: { maiw_operational_status: 'HEALTHY', model_gateway_status: 'HEALTHY', domain_health: { equipment: 'HEALTHY', labor: 'HEALTHY', wave: 'HEALTHY', inventory: 'HEALTHY' } }, isLoading: false }),
}));

jest.mock('../../hooks/useDemoStatus', () => ({
  useDemoStatus: jest.fn(),
}));

const { useDemoStatus } = require('../../hooks/useDemoStatus');
const { demoAPI } = require('../../services/demoAPI');

// ── Helpers ────────────────────────────────────────────────────────────────────

function makeSSEEvent(category: string, idx: number): SSEEvent {
  return {
    id: `evt-${idx}`,
    ts: new Date(Date.now() + idx * 1000).toISOString(),
    category,
    message: `test ${category}`,
    detail: null,
    asset_id: null,
    task_id: null,
    worker_id: null,
  };
}

// useDemoSSE events are newest-first; helper builds the array in that order.
function makeEvents(...categories: string[]): SSEEvent[] {
  // categories are in chronological order; reverse for newest-first storage
  return [...categories].reverse().map((c, i) => makeSSEEvent(c, i));
}

function renderRail(
  currentStage: string,
  completedStages: string[],
  waitingForApproval = false,
) {
  return render(
    <ThemeProvider theme={nvidiaTheme}>
      <LifecycleRail
        currentStage={currentStage as any}
        completedStages={new Set(completedStages) as any}
        waitingForApproval={waitingForApproval}
      />
    </ThemeProvider>
  );
}

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

// ── LifecycleRail component tests ──────────────────────────────────────────────

describe('LifecycleRail — node rendering', () => {
  it('renders all seven stage nodes', () => {
    renderRail('OBSERVE', []);
    expect(screen.getByTestId('lifecycle-stage-observe')).toBeInTheDocument();
    expect(screen.getByTestId('lifecycle-stage-reason')).toBeInTheDocument();
    expect(screen.getByTestId('lifecycle-stage-propose')).toBeInTheDocument();
    expect(screen.getByTestId('lifecycle-stage-decide')).toBeInTheDocument();
    expect(screen.getByTestId('lifecycle-stage-approve')).toBeInTheDocument();
    expect(screen.getByTestId('lifecycle-stage-execute')).toBeInTheDocument();
    expect(screen.getByTestId('lifecycle-stage-outcome')).toBeInTheDocument();
  });

  it('renders exactly seven nodes — no extra nodes', () => {
    renderRail('OBSERVE', []);
    // SKILL must NOT have its own node
    expect(screen.queryByTestId('lifecycle-stage-skill')).not.toBeInTheDocument();
    // Only seven lifecycle-stage-* elements
    const allNodes = document.querySelectorAll('[data-testid^="lifecycle-stage-"]');
    expect(allNodes).toHaveLength(7);
  });

  it('APPROVE renders as a separate node from DECIDE', () => {
    const { container } = renderRail('APPROVE', ['OBSERVE', 'REASON', 'PROPOSE', 'DECIDE'], true);
    const decideNode = screen.getByTestId('lifecycle-stage-decide');
    const approveNode = screen.getByTestId('lifecycle-stage-approve');
    expect(decideNode).toBeInTheDocument();
    expect(approveNode).toBeInTheDocument();
    // They must be different DOM elements
    expect(decideNode).not.toBe(approveNode);
  });

  it('shows OUTCOME label not OBSERVE_OUTCOME', () => {
    renderRail('OUTCOME', STAGE_ORDER.filter(s => s !== 'OUTCOME') as any);
    expect(screen.getByTestId('lifecycle-stage-outcome')).toBeInTheDocument();
    // The node label should say "Outcome", not "Observe_Outcome"
    expect(screen.queryByText(/observe_outcome/i)).not.toBeInTheDocument();
  });

  it('shows subtitle on OUTCOME node when active', () => {
    renderRail('OUTCOME', ['OBSERVE', 'REASON', 'PROPOSE', 'DECIDE', 'APPROVE', 'EXECUTE']);
    expect(screen.getByText(/observe operational effect/i)).toBeInTheDocument();
  });

  it('does not show OUTCOME subtitle when upcoming', () => {
    renderRail('OBSERVE', []);
    expect(screen.queryByText(/observe operational effect/i)).not.toBeInTheDocument();
  });
});

describe('LifecycleRail — state encoding', () => {
  it('OBSERVE is current on initial state', () => {
    renderRail('OBSERVE', []);
    const node = screen.getByTestId('lifecycle-stage-observe');
    expect(node).toHaveAttribute('aria-label', expect.stringContaining('current'));
  });

  it('completed stages are marked complete', () => {
    renderRail('REASON', ['OBSERVE']);
    expect(screen.getByTestId('lifecycle-stage-observe')).toHaveAttribute(
      'aria-label', expect.stringContaining('complete')
    );
    expect(screen.getByTestId('lifecycle-stage-reason')).toHaveAttribute(
      'aria-label', expect.stringContaining('current')
    );
    expect(screen.getByTestId('lifecycle-stage-propose')).toHaveAttribute(
      'aria-label', expect.stringContaining('upcoming')
    );
  });

  it('APPROVE shows waiting state when waitingForApproval=true', () => {
    renderRail('APPROVE', ['OBSERVE', 'REASON', 'PROPOSE', 'DECIDE'], true);
    expect(screen.getByTestId('lifecycle-stage-approve')).toHaveAttribute(
      'aria-label', expect.stringContaining('waiting')
    );
  });

  it('APPROVE shows current state when waitingForApproval=false', () => {
    renderRail('APPROVE', ['OBSERVE', 'REASON', 'PROPOSE', 'DECIDE'], false);
    expect(screen.getByTestId('lifecycle-stage-approve')).toHaveAttribute(
      'aria-label', expect.stringContaining('current')
    );
  });

  it('uses symbols not just color — ✓ for complete, ● for current, ○ for upcoming', () => {
    const { container } = renderRail('REASON', ['OBSERVE']);
    // Symbols must appear in the DOM (accessibility: not color-only)
    expect(container.textContent).toContain('✓');  // complete
    expect(container.textContent).toContain('●');  // current
    expect(container.textContent).toContain('○');  // upcoming
  });
});

// ── deriveRailState unit tests ─────────────────────────────────────────────────

describe('deriveRailState — SSE to rail stage mapping', () => {
  it('returns OBSERVE as current with empty event buffer', () => {
    const result = deriveRailState([], []);
    expect(result.currentStage).toBe('OBSERVE');
    expect(result.completedStages.size).toBe(0);
    expect(result.waitingForApproval).toBe(false);
  });

  it('SKILL SSE maps to REASON — does not create a separate stage', () => {
    const events = makeEvents('OBSERVE', 'REASON', 'SKILL');
    const result = deriveRailState(events, []);
    expect(result.currentStage).toBe('REASON');
    // SKILL should not be in completedStages as its own key
    expect(result.completedStages.has('REASON')).toBe(false); // REASON is current, not completed
  });

  it('OBSERVE_OUTCOME SSE maps to OUTCOME rail stage', () => {
    const events = makeEvents('OBSERVE', 'REASON', 'SKILL', 'PROPOSE', 'DECIDE', 'APPROVE', 'EXECUTE', 'OBSERVE_OUTCOME');
    const result = deriveRailState(events, []);
    expect(result.currentStage).toBe('OUTCOME');
  });

  it('pipeline advances through full sequence', () => {
    const events = makeEvents('OBSERVE', 'REASON', 'PROPOSE', 'DECIDE');
    const result = deriveRailState(events, []);
    expect(result.currentStage).toBe('DECIDE');
    expect(result.completedStages.has('OBSERVE')).toBe(true);
    expect(result.completedStages.has('REASON')).toBe(true);
    expect(result.completedStages.has('PROPOSE')).toBe(true);
    expect(result.completedStages.has('DECIDE')).toBe(false);
  });

  it('APPROVE becomes current when DECIDE is furthest and pendingApprovals is non-empty', () => {
    const events = makeEvents('OBSERVE', 'REASON', 'PROPOSE', 'DECIDE');
    const result = deriveRailState(events, [{ pending_id: 'p1' } as any]);
    expect(result.currentStage).toBe('APPROVE');
    expect(result.waitingForApproval).toBe(true);
    // DECIDE must be in completed when waiting for approval
    expect(result.completedStages.has('DECIDE')).toBe(true);
  });

  it('APPROVE stays at DECIDE when no pending approvals', () => {
    const events = makeEvents('OBSERVE', 'REASON', 'PROPOSE', 'DECIDE');
    const result = deriveRailState(events, []);
    expect(result.currentStage).toBe('DECIDE');
    expect(result.waitingForApproval).toBe(false);
  });

  it('new OBSERVE event resets current-run window — no historical leakage', () => {
    // First run: went all the way to EXECUTE
    // Then a new OBSERVE arrived (second run starting)
    // Events newest-first: new OBSERVE is at index 0, old events at higher indices
    const events = [
      makeSSEEvent('OBSERVE', 10),    // second run anchor (newest)
      makeSSEEvent('EXECUTE', 9),     // first run — MUST be ignored
      makeSSEEvent('APPROVE', 8),
      makeSSEEvent('DECIDE', 7),
      makeSSEEvent('PROPOSE', 6),
      makeSSEEvent('REASON', 5),
      makeSSEEvent('OBSERVE', 4),     // first run anchor
    ];
    const result = deriveRailState(events, []);
    // Only the second run's OBSERVE should count; first run's stages must NOT appear
    expect(result.currentStage).toBe('OBSERVE');
    expect(result.completedStages.size).toBe(0);
  });

  it('ignores non-lifecycle SSE categories', () => {
    const events = makeEvents('OBSERVE', 'PIPELINE', 'SNAPSHOT', 'RELIABILITY', 'REASON');
    const result = deriveRailState(events, []);
    expect(result.currentStage).toBe('REASON');
    expect(result.completedStages.has('OBSERVE')).toBe(true);
  });
});

// ── OperationalContextStrip tests ─────────────────────────────────────────────

describe('OperationalContextStrip', () => {
  function renderStrip(kpis: any) {
    return render(
      <ThemeProvider theme={nvidiaTheme}>
        <OperationalContextStrip kpis={kpis} />
      </ThemeProvider>
    );
  }

  const baseKpis = {
    sim_time_seconds: 60,
    clock_iso: '2026-08-27T10:00:00Z',
    equipment_total: 8,
    equipment_operational_pct: 100,
    labor_total: 6,
    labor_availability_pct: 67,
    labor_utilization_pct: 80,
    pending_backlog: 5,
    wave_risk_score: 0.95,
    wave_risk_level: 'critical',
    low_stock_count: 0,
    state_freshness_seconds: 10,
    service_risk_index: 0.7,
    capacity_throughput_proxy: 300,
    wave_completion_pct: 34,
    simulated_throughput: 312,
    projected_service_level: 71,
    time_to_recovery_seconds: 1080,
  };

  it('renders all four KPI cells', () => {
    renderStrip(baseKpis);
    expect(screen.getByTestId('kpi-equipment')).toBeInTheDocument();
    expect(screen.getByTestId('kpi-labor')).toBeInTheDocument();
    expect(screen.getByTestId('kpi-backlog')).toBeInTheDocument();
    expect(screen.getByTestId('kpi-wave-risk')).toBeInTheDocument();
  });

  it('displays equipment_operational_pct from kpis', () => {
    renderStrip({ ...baseKpis, equipment_operational_pct: 83 });
    expect(screen.getByTestId('kpi-equipment')).toHaveTextContent('83%');
  });

  it('displays labor_availability_pct from kpis', () => {
    renderStrip({ ...baseKpis, labor_availability_pct: 50 });
    expect(screen.getByTestId('kpi-labor')).toHaveTextContent('50%');
  });

  it('displays pending_backlog from kpis', () => {
    renderStrip({ ...baseKpis, pending_backlog: 5 });
    expect(screen.getByTestId('kpi-backlog')).toHaveTextContent('5');
  });

  it('displays wave_risk_level from kpis', () => {
    renderStrip({ ...baseKpis, wave_risk_level: 'critical' });
    expect(screen.getByTestId('kpi-wave-risk')).toHaveTextContent('CRITICAL');
  });

  it('shows loading state when kpis is null', () => {
    renderStrip(null);
    expect(screen.getByTestId('operational-context-strip')).toBeInTheDocument();
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('rounds equipment pct to integer', () => {
    renderStrip({ ...baseKpis, equipment_operational_pct: 83.7 });
    expect(screen.getByTestId('kpi-equipment')).toHaveTextContent('84%');
  });

  it('rounds labor pct to integer', () => {
    renderStrip({ ...baseKpis, labor_availability_pct: 66.6 });
    expect(screen.getByTestId('kpi-labor')).toHaveTextContent('67%');
  });
});

// ── DemoShell routing tests ────────────────────────────────────────────────────

describe('DemoShell — scenario routing', () => {
  const { MemoryRouter } = require('react-router-dom');

  function renderShell(demoStatusValue: any) {
    useDemoStatus.mockReturnValue({
      status: demoStatusValue,
      isLoading: false,
      isDemoMode: demoStatusValue != null,
      refetch: jest.fn(),
    });
    (demoAPI.listScenarios as jest.Mock).mockResolvedValue([
      { name: 'labor_constraint_wave_risk', display_name: 'Labor + Wave Risk', description: 'Test', tags: ['labor'] },
    ]);

    const DemoShell = require('../../pages/DemoShell').default;
    return render(
      <MemoryRouter>
        <QueryClientProvider client={makeQC()}>
          <ThemeProvider theme={nvidiaTheme}>
            <DemoShell />
          </ThemeProvider>
        </QueryClientProvider>
      </MemoryRouter>
    );
  }

  beforeEach(() => jest.clearAllMocks());

  it('shows ScenarioSelector when no scenario is active', async () => {
    renderShell({ active: false, paused: false, scenario: null, world: null, current_kpis: null, kpi_history: [], pending_approvals: [] });
    await waitFor(() => {
      expect(screen.getByText(/select a scenario to begin/i)).toBeInTheDocument();
    });
    expect(screen.queryByTestId('lifecycle-rail')).not.toBeInTheDocument();
  });

  it('shows lifecycle rail when scenario is active', () => {
    renderShell({
      active: true,
      paused: false,
      scenario: { name: 'labor_constraint_wave_risk', display_name: 'Labor + Wave Risk', description: '', tags: [] },
      world: { warehouse_id: 'DC-47', clock_iso: '2026-08-27T10:00:00Z', elapsed_seconds: 47, equipment: { total: 8, available: 8, assigned: 0, maintenance: 0, offline: 0 }, workers: { total: 6, active: 3, inactive: 3 }, tasks: { total: 5, pending: 5, in_progress: 0, completed: 0 }, inventory: { total_skus: 5, low_stock: 0 } },
      current_kpis: { sim_time_seconds: 47, clock_iso: '2026-08-27T10:00:47Z', equipment_total: 8, equipment_operational_pct: 100, labor_total: 6, labor_availability_pct: 50, labor_utilization_pct: 80, pending_backlog: 5, wave_risk_score: 0.95, wave_risk_level: 'critical', low_stock_count: 0, state_freshness_seconds: 10, service_risk_index: 0.7, capacity_throughput_proxy: 300, wave_completion_pct: 34, simulated_throughput: 312, projected_service_level: 71, time_to_recovery_seconds: null },
      kpi_history: [],
      pending_approvals: [],
    });
    expect(screen.getByTestId('lifecycle-rail')).toBeInTheDocument();
    expect(screen.queryByText(/select a scenario to begin/i)).not.toBeInTheDocument();
  });

  it('shows OperationalContextStrip when scenario is active', () => {
    renderShell({
      active: true,
      paused: false,
      scenario: { name: 'labor_constraint_wave_risk', display_name: 'Labor + Wave Risk', description: '', tags: [] },
      world: { warehouse_id: 'DC-47', clock_iso: '2026-08-27T10:00:00Z', elapsed_seconds: 47, equipment: { total: 8, available: 8, assigned: 0, maintenance: 0, offline: 0 }, workers: { total: 6, active: 3, inactive: 3 }, tasks: { total: 5, pending: 5, in_progress: 0, completed: 0 }, inventory: { total_skus: 5, low_stock: 0 } },
      current_kpis: { sim_time_seconds: 47, clock_iso: '2026-08-27T10:00:47Z', equipment_total: 8, equipment_operational_pct: 83, labor_total: 6, labor_availability_pct: 50, labor_utilization_pct: 80, pending_backlog: 5, wave_risk_score: 0.95, wave_risk_level: 'critical', low_stock_count: 0, state_freshness_seconds: 10, service_risk_index: 0.7, capacity_throughput_proxy: 300, wave_completion_pct: 34, simulated_throughput: 312, projected_service_level: 71, time_to_recovery_seconds: null },
      kpi_history: [],
      pending_approvals: [],
    });
    expect(screen.getByTestId('operational-context-strip')).toBeInTheDocument();
    // KPI values must come from current_kpis
    expect(screen.getByTestId('kpi-equipment')).toHaveTextContent('83%');
    expect(screen.getByTestId('kpi-labor')).toHaveTextContent('50%');
    expect(screen.getByTestId('kpi-backlog')).toHaveTextContent('5');
    expect(screen.getByTestId('kpi-wave-risk')).toHaveTextContent('CRITICAL');
  });

  it('shows stage workspace placeholder when scenario is active', () => {
    renderShell({
      active: true,
      paused: false,
      scenario: { name: 'labor_constraint_wave_risk', display_name: 'Labor + Wave Risk', description: '', tags: [] },
      world: { warehouse_id: 'DC-47', clock_iso: '', elapsed_seconds: 0, equipment: { total: 8, available: 8, assigned: 0, maintenance: 0, offline: 0 }, workers: { total: 6, active: 6, inactive: 0 }, tasks: { total: 0, pending: 0, in_progress: 0, completed: 0 }, inventory: { total_skus: 5, low_stock: 0 } },
      current_kpis: null,
      kpi_history: [],
      pending_approvals: [],
    });
    expect(screen.getByTestId('stage-workspace')).toBeInTheDocument();
  });

  it('reset returns to ScenarioSelector and clears lifecycle state', async () => {
    (demoAPI.resetScenario as jest.Mock).mockResolvedValue({ active: false });

    renderShell({
      active: true,
      paused: false,
      scenario: { name: 'labor_constraint_wave_risk', display_name: 'Labor + Wave Risk', description: '', tags: [] },
      world: { warehouse_id: 'DC-47', clock_iso: '', elapsed_seconds: 47, equipment: { total: 8, available: 8, assigned: 0, maintenance: 0, offline: 0 }, workers: { total: 6, active: 3, inactive: 3 }, tasks: { total: 5, pending: 5, in_progress: 0, completed: 0 }, inventory: { total_skus: 5, low_stock: 0 } },
      current_kpis: null,
      kpi_history: [],
      pending_approvals: [],
    });

    // Confirm lifecycle layout is shown
    expect(screen.getByTestId('lifecycle-rail')).toBeInTheDocument();

    // Click reset
    const resetBtn = screen.getByTestId('reset-button');
    await act(async () => { fireEvent.click(resetBtn); });

    // ScenarioSelector must appear; lifecycle rail must disappear
    await waitFor(() => {
      expect(screen.queryByTestId('lifecycle-rail')).not.toBeInTheDocument();
    });
    expect(demoAPI.resetScenario).toHaveBeenCalled();
  });
});
