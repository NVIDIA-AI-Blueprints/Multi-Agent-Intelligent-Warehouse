/**
 * RELIABILITY page (CommandCenter) in Demo Mode.
 *
 * Demo Mode runs no PostgreSQL, so the legacy equipment/task/workforce routes
 * fail. The operational risks then come from the simulation KPIs instead of
 * staying on "loading state data" forever. The Models panel no longer
 * hard-codes Ultra as DISABLED: only the role that served the last analysis is
 * marked, and the gateway status comes from /runtime/status.
 */
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  deriveDemoRisks,
  emptyRisksText,
  getModelRole,
  LABOR_AVAILABILITY_RISK_PCT,
} from '../../pages/commandCenterState';
import type { KPISnapshot, PendingApproval } from '../../services/demoAPI';

const KPIS: KPISnapshot = {
  sim_time_seconds: 5400,
  clock_iso: '2026-11-19T10:30:00Z',
  equipment_total: 24,
  equipment_operational_pct: 100,
  labor_total: 120,
  labor_availability_pct: 98.3,
  labor_utilization_pct: 60,
  pending_backlog: 119,
  wave_risk_score: 0.9,
  wave_risk_level: 'critical',
  low_stock_count: 1007,
  state_freshness_seconds: 5,
  service_risk_index: 0.5,
  capacity_throughput_proxy: 0,
  wave_completion_pct: 0,
  simulated_throughput: 0,
  projected_service_level: 100,
  time_to_recovery_seconds: null,
};

const mockDemoStatus = {
  active: true,
  paused: false,
  scenario: { name: 'labor_constraint_wave_risk', display_name: 'Labor Constraint + Wave Risk' },
  world: null,
  current_kpis: KPIS,
  kpi_history: [],
  pending_approvals: [] as PendingApproval[],
};

jest.mock('../../hooks/useDemoStatus', () => ({
  useDemoStatus: () => ({ isDemoMode: true, status: mockDemoStatus, isLoading: false, refetch: jest.fn() }),
}));
jest.mock('../../hooks/useDemoSSE', () => ({
  useDemoSSE: () => ({ events: [], connected: false }),
}));
jest.mock('../../hooks/useRuntimeStatus', () => ({
  useRuntimeStatus: () => ({ data: { model_gateway_status: 'HEALTHY', maiw_operational_status: 'HEALTHY' } }),
}));
jest.mock('../../services/api', () => {
  const fail = () => Promise.reject(new Error('500: PostgreSQL not configured'));
  return {
    equipmentAPI: { getAllAssets: fail },
    operationsAPI: { getTasks: fail, getWorkforceStatus: fail },
    safetyAPI: { getIncidents: fail },
    mcpAPI: { getStatus: fail },
  };
});
jest.mock('../../components/demo/DemoControlBar', () => () => null);
jest.mock('../../components/demo/DecisionLifecycle', () => () => null);
jest.mock('../../components/demo/MAIWPipeline', () => () => null);
jest.mock('../../components/demo/KPITrendChart', () => () => null);
jest.mock('../../components/demo/CounterfactualPanel', () => () => null);
jest.mock('../../components/reliability/ReliabilityPanel', () => () => null);
jest.mock('../../components/reliability/SafetyScorecard', () => () => null);
jest.mock('../../components/reliability/FaultInjectionPanel', () => () => null);

// eslint-disable-next-line import/first
import CommandCenter from '../../pages/CommandCenter';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <CommandCenter />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('deriveDemoRisks', () => {
  it('lists the scenario risks most severe first', () => {
    const texts = deriveDemoRisks(KPIS, 1).map((r) => r.text);
    expect(texts).toEqual([
      'Wave risk CRITICAL',
      '1 action awaiting human approval',
      '119 tasks pending — operations backlog',
      '1007 SKUs low on stock',
    ]);
  });

  it('flags degraded equipment and labor', () => {
    const texts = deriveDemoRisks(
      { ...KPIS, equipment_operational_pct: 87.5, labor_availability_pct: LABOR_AVAILABILITY_RISK_PCT - 5 },
      0,
    ).map((r) => r.text);
    expect(texts).toContain('Equipment 88% operational');
    expect(texts).toContain('Labor availability 90.0%');
  });

  it('reports no risks for a healthy state', () => {
    const risks = deriveDemoRisks(
      { ...KPIS, wave_risk_level: 'none', pending_backlog: 0, low_stock_count: 0 },
      0,
    );
    expect(risks).toEqual([{ icon: '✓', text: 'No active operational risks detected', color: '#3FB950' }]);
  });
});

describe('emptyRisksText and getModelRole', () => {
  it('says unavailable, not loading, once the source failed', () => {
    expect(emptyRisksText(false)).toBe('— loading state data —');
    expect(emptyRisksText(true)).toBe('— state data unavailable —');
  });

  it('maps model IDs to roles', () => {
    expect(getModelRole('nvidia/nemotron-3-ultra-550b-a55b')).toBe('Ultra');
    expect(getModelRole('nvidia/nemotron-3-super-120b')).toBe('Super');
    expect(getModelRole('some/other-model')).toBeNull();
  });
});

describe('CommandCenter in Demo Mode', () => {
  beforeEach(() => sessionStorage.clear());

  it('shows KPI-derived risks although the legacy routes fail', async () => {
    renderPage();
    expect((await screen.findAllByText('Wave risk CRITICAL')).length).toBeGreaterThan(0);
    await waitFor(() => expect(screen.queryByText(/loading state data/)).not.toBeInTheDocument());
  });

  it('marks the model that served the last analysis and never shows DISABLED', async () => {
    sessionStorage.setItem(
      'maiw_analysis_result',
      JSON.stringify({
        ok: true,
        trace_id: 't-1',
        assessment: { model_id: 'nvidia/nemotron-3-ultra-550b-a55b' },
        proposal_results: [],
        lifecycle: [],
        pre_kpis: KPIS,
        post_kpis: KPIS,
        kpi_delta: {},
        timing: { time_to_detect_ms: null, time_to_decision_ms: 42000, time_to_execution_ms: 33 },
      }),
    );
    renderPage();
    const ultra = await screen.findByText('Ultra');
    expect(ultra.parentElement).toHaveTextContent('LAST USED');
    expect(screen.getAllByText('LAST USED')).toHaveLength(1);
    expect(screen.queryByText('DISABLED')).not.toBeInTheDocument();
    expect(screen.getAllByText('HEALTHY').length).toBeGreaterThan(0);
  });
});
