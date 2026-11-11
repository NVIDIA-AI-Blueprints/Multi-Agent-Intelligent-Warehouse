/**
 * Fault injectors never hard-code an asset, worker, SKU or task id.
 *
 * Demo mode builds the active world from the DC-47 DataPack (ids such as
 * `agv-000`, `worker-000000`, `sku-000000`); `AGV-01`, `w-002` and `SKU-1001`
 * exist only in the scenario YAML fallback. Every injector omits its target so
 * the backend resolves an eligible one from the ACTIVE world, and renders the
 * resolved target (or the typed error) from the response.
 *
 * Covers: components/reliability/FaultInjectionPanel,
 *         components/demo/reliability/FaultInjectionPanel,
 *         components/demo/DemoControlBar.
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@mui/material/styles';
import { nvidiaTheme } from '../../theme/nvidiaTheme';
import ReliabilityFaultPanel from '../../components/reliability/FaultInjectionPanel';
import DemoFaultPanel from '../../components/demo/reliability/FaultInjectionPanel';
import DemoControlBar from '../../components/demo/DemoControlBar';
import { describeInjectError, describeInjectTarget } from '../../components/demo/injectFeedback';
import { demoAPI, DemoStatus } from '../../services/demoAPI';

jest.mock('../../services/demoAPI', () => ({
  demoAPI: {
    inject: jest.fn(),
    reconcile: jest.fn(),
    getStatus: jest.fn(),
    approvePending: jest.fn(),
    listScenarios: jest.fn(),
  },
}));

const injectMock = demoAPI.inject as jest.Mock;

const typedError = (status: number, code: string, message: string) =>
  Object.assign(new Error(`Request failed with status code ${status}`), {
    response: { status, data: { error: true, code, message, status_code: status } },
  });

function themed(ui: React.ReactElement) {
  return render(<ThemeProvider theme={nvidiaTheme}>{ui}</ThemeProvider>);
}

function renderBar() {
  const scenario = { name: 'labor_constraint_wave_risk', display_name: 'Labor + Wave Risk', description: '', tags: [] };
  (demoAPI.listScenarios as jest.Mock).mockResolvedValue([scenario]);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(['demo-scenarios'], [scenario]);
  const status: DemoStatus = {
    active: true,
    paused: false,
    scenario,
    world: null,
    current_kpis: null,
    kpi_history: [],
    pending_approvals: [],
  };
  return render(
    <QueryClientProvider client={qc}>
      <ThemeProvider theme={nvidiaTheme}>
        <DemoControlBar status={status} onStatusChange={jest.fn()} />
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

function expectNoHardCodedAsset() {
  expect(injectMock).toHaveBeenCalled();
  for (const [, payload] of injectMock.mock.calls) {
    expect(JSON.stringify(payload)).not.toContain('AGV-01');
  }
}

beforeEach(() => jest.clearAllMocks());

// ── helpers ─────────────────────────────────────────────────────────────────

describe('injectFeedback', () => {
  it('describes the resolved target', () => {
    expect(describeInjectTarget({ asset_id: 'agv-000', status: 'offline' })).toBe('Targeted agv-000');
    expect(describeInjectTarget({ worker_id: 'worker-000000', status: 'on_leave' })).toBe('Targeted worker-000000');
    expect(describeInjectTarget({ sku: 'sku-000000', quantity_available: 50 })).toBe('Targeted sku-000000');
    expect(describeInjectTarget({ task_id: 'task-000003', deadline: 'x' })).toBe('Targeted task-000003');
    expect(describeInjectTarget({ status: 'offline' })).toBeNull();
    expect(describeInjectTarget(undefined)).toBeNull();
  });

  it('formats typed, legacy and network errors', () => {
    expect(describeInjectError(typedError(409, 'NO_ELIGIBLE_ASSET', 'nothing eligible'))).toBe(
      'NO_ELIGIBLE_ASSET: nothing eligible',
    );
    expect(describeInjectError({ response: { data: { detail: 'No active scenario' } } })).toBe('No active scenario');
    expect(describeInjectError({ response: { data: { detail: { message: 'boom' } } } })).toBe('boom');
    expect(describeInjectError(new Error('Network Error'))).toBe('Network Error');
  });
});

// ── components/reliability/FaultInjectionPanel ───────────────────────────────

describe('reliability FaultInjectionPanel (F10 STATE DRIFT)', () => {
  it('sends no asset_id and renders the resolved target', async () => {
    injectMock.mockResolvedValue({ asset_id: 'agv-000', status: 'offline', target_resolution: 'resolved' });
    themed(<ReliabilityFaultPanel scenarioActive />);
    await act(async () => { fireEvent.click(screen.getAllByText('INJECT')[0]); });
    expect(await screen.findByTestId('fault-inject-feedback')).toHaveTextContent('F10 · Targeted agv-000');
    expect(injectMock).toHaveBeenCalledWith(
      'equipment_fault',
      { equipment_type: 'agv', fault_code: 'E_STATE_DRIFT_SIM' },
    );
    expectNoHardCodedAsset();
  });

  it('renders the typed error', async () => {
    const consoleError = jest.spyOn(console, 'error').mockImplementation(() => undefined);
    injectMock.mockRejectedValue(typedError(409, 'NO_ELIGIBLE_ASSET', 'no equipment asset eligible'));
    themed(<ReliabilityFaultPanel scenarioActive />);
    await act(async () => { fireEvent.click(screen.getAllByText('INJECT')[0]); });
    expect(await screen.findByTestId('fault-inject-feedback')).toHaveTextContent(
      'F10 · NO_ELIGIBLE_ASSET: no equipment asset eligible',
    );
    consoleError.mockRestore();
  });
});

// ── components/demo/reliability/FaultInjectionPanel ─────────────────────────

describe('demo reliability FaultInjectionPanel', () => {
  it('F06 sends the ambiguous-write flag without an asset_id and shows the target', async () => {
    injectMock.mockResolvedValue({ asset_id: 'agv-000', status: 'available', ambiguous_write_armed: true });
    themed(<DemoFaultPanel scenarioId="F06" sseEvents={[]} />);
    await act(async () => { fireEvent.click(screen.getByTestId('inject-fault-F06')); });
    expect(await screen.findByTestId('inject-result')).toHaveTextContent(
      'INJECT FAULT → injected · Targeted agv-000',
    );
    expect(injectMock).toHaveBeenCalledWith(
      'equipment_fault',
      { equipment_type: 'agv', simulate_ambiguous_write: true },
    );
    expectNoHardCodedAsset();
  });

  it('F06 renders the typed error instead of a raw detail', async () => {
    injectMock.mockRejectedValue(typedError(404, 'ASSET_NOT_IN_ACTIVE_WORLD', "asset 'x' is not in the active demo world"));
    themed(<DemoFaultPanel scenarioId="F06" sseEvents={[]} />);
    await act(async () => { fireEvent.click(screen.getByTestId('inject-fault-F06')); });
    expect(await screen.findByTestId('inject-result')).toHaveTextContent(
      "Error: ASSET_NOT_IN_ACTIVE_WORLD: asset 'x' is not in the active demo world",
    );
  });

  it('F10 restores the same asset the backend resolved for the fault', async () => {
    injectMock
      .mockResolvedValueOnce({ asset_id: 'agv-003', status: 'offline' })
      .mockResolvedValueOnce({ asset_id: 'agv-003', status: 'available' });
    themed(<DemoFaultPanel scenarioId="F10" sseEvents={[]} />);
    await act(async () => { fireEvent.click(screen.getByTestId('inject-fault-F10')); });
    expect(await screen.findByTestId('inject-result')).toHaveTextContent('Targeted agv-003');
    expect(injectMock).toHaveBeenNthCalledWith(1, 'equipment_fault', { equipment_type: 'agv' });
    expect(injectMock).toHaveBeenNthCalledWith(2, 'equipment_restore', { asset_id: 'agv-003' });
    expectNoHardCodedAsset();
  });

  it('F12 sends no worker_id and shows the resolved worker', async () => {
    injectMock.mockResolvedValue({ worker_id: 'worker-000001', status: 'on_leave' });
    themed(<DemoFaultPanel scenarioId="F12" sseEvents={[]} />);
    await act(async () => { fireEvent.click(screen.getByTestId('inject-fault-F12')); });
    expect(await screen.findByTestId('inject-result')).toHaveTextContent('Targeted worker-000001');
    expect(injectMock).toHaveBeenCalledWith('worker_absence', {});
  });

  it('F01 sends no task_id and shows the resolved task', async () => {
    injectMock.mockResolvedValue({ task_id: 'task-000003', deadline: '2026-08-23T10:00:00Z' });
    themed(<DemoFaultPanel scenarioId="F01" sseEvents={[]} />);
    await act(async () => { fireEvent.click(screen.getByTestId('inject-fault-F01')); });
    expect(await screen.findByTestId('inject-result')).toHaveTextContent('Targeted task-000003');
    expect(injectMock).toHaveBeenCalledWith('task_deadline', { deadline: '2026-08-23T10:00:00Z' });
  });
});

// ── components/demo/DemoControlBar ───────────────────────────────────────────

describe('DemoControlBar injectors', () => {
  it('EQUIP FAULT sends no asset_id and shows the resolved target', async () => {
    injectMock.mockResolvedValue({ asset_id: 'agv-000', status: 'offline' });
    renderBar();
    await act(async () => { fireEvent.click(screen.getByText('EQUIP FAULT')); });
    await waitFor(() => expect(screen.getByText('✓ EQUIP FAULT · Targeted agv-000')).toBeInTheDocument());
    const [type, payload] = injectMock.mock.calls[0];
    expect(type).toBe('equipment_fault');
    expect(payload).not.toHaveProperty('asset_id');
    expect(payload).toMatchObject({ equipment_type: 'agv', fault_code: 'E_MOTOR_OVERTEMP' });
    expectNoHardCodedAsset();
  });

  it('EQUIP RESTORE sends no asset_id and shows the resolved target', async () => {
    injectMock.mockResolvedValue({ asset_id: 'agv-000', status: 'available' });
    renderBar();
    await act(async () => { fireEvent.click(screen.getByText('EQUIP RESTORE')); });
    await waitFor(() => expect(screen.getByText('✓ EQUIP RESTORE · Targeted agv-000')).toBeInTheDocument());
    expect(injectMock).toHaveBeenCalledWith('equipment_restore', { new_status: 'available', battery_pct: 85 });
    expectNoHardCodedAsset();
  });

  it.each([
    ['LABOR SHORT', 'worker_absence', {}, { worker_id: 'worker-000001', status: 'on_leave' }, 'worker-000001'],
    ['LABOR RETURN', 'worker_return', {}, { worker_id: 'worker-000001', status: 'active' }, 'worker-000001'],
    ['LOW STOCK', 'low_stock', { quantity_available: 50 }, { sku: 'sku-000000', quantity_available: 50 }, 'sku-000000'],
  ])('%s sends no id and shows the resolved target', async (label, type, payload, result, target) => {
    injectMock.mockResolvedValue(result);
    renderBar();
    await act(async () => { fireEvent.click(screen.getByText(label)); });
    await waitFor(() => expect(screen.getByText(`✓ ${label} · Targeted ${target}`)).toBeInTheDocument());
    expect(injectMock).toHaveBeenCalledWith(type, payload);
  });

  it('renders the typed error', async () => {
    injectMock.mockRejectedValue(typedError(409, 'NO_ELIGIBLE_ASSET', 'nothing to restore'));
    renderBar();
    await act(async () => { fireEvent.click(screen.getByText('EQUIP RESTORE')); });
    await waitFor(() => expect(screen.getByText('✕ NO_ELIGIBLE_ASSET: nothing to restore')).toBeInTheDocument());
  });
});
