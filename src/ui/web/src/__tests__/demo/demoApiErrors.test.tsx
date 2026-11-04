/**
 * Demo API failures are shown to the operator instead of being swallowed.
 *
 * Before: "Start scenario" did nothing on a 403 from the origin guard, and a
 * 503 MODEL UNAVAILABLE from /demo/analyze left REASON on "Awaiting model
 * response..." forever. The response bodies below are the ones the API sent.
 */

import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import { ThemeProvider } from '@mui/material/styles';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { nvidiaTheme } from '../../theme/nvidiaTheme';

import StageContentPane from '../../components/demo/StageContentPane';
import ObserveStage from '../../components/demo/stages/ObserveStage';
import ReasonStage from '../../components/demo/stages/ReasonStage';
import ScenarioSelector from '../../components/demo/ScenarioSelector';
import { describeDemoApiError } from '../../components/demo/injectFeedback';
import { DemoStatus } from '../../services/demoAPI';

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

function httpError(status: number, data: unknown) {
  return Object.assign(new Error(`Request failed with status code ${status}`), { response: { status, data } });
}

const ORIGIN_403 = httpError(403, {
  error: 'CROSS_ORIGIN_REQUEST_FORBIDDEN',
  message: "Requests from origin 'http://127.0.0.1:3011' may not change state. Serve the UI from an origin listed in CORS_ORIGINS.",
  status_code: 403,
});

const MODEL_503 = httpError(503, {
  error: true,
  message: {
    error: 'MODEL UNAVAILABLE',
    message: 'agent analysis: no enabled model can serve the request',
    model_id: 'nvidia/nemotron-3-ultra-550b-a55b',
  },
  status_code: 503,
  error_type: 'HTTPException',
});

const NO_SCENARIO_409 = httpError(409, {
  error: true,
  message: 'No active scenario',
  status_code: 409,
  error_type: 'HTTPException',
});

const baseStatus: DemoStatus = {
  active: true,
  paused: false,
  scenario: { name: 'labor_constraint_wave_risk', display_name: 'Labor + Wave Risk', description: '', tags: [] },
  world: null,
  current_kpis: null,
  kpi_history: [],
  pending_approvals: [],
};

function wrap(el: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ThemeProvider theme={nvidiaTheme}>{el}</ThemeProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

function makeProps(overrides: Partial<Parameters<typeof StageContentPane>[0]> = {}): Parameters<typeof StageContentPane>[0] {
  return {
    currentStage: 'OBSERVE',
    sseEvents: [],
    demoStatus: baseStatus,
    analysisResult: null,
    pendingApprovals: [],
    analyzing: false,
    onAnalyze: async () => {},
    ...overrides,
  };
}

beforeEach(() => jest.clearAllMocks());

// ── describeDemoApiError ───────────────────────────────────────────────────────

describe('describeDemoApiError', () => {
  it('formats the origin guard 403', () => {
    expect(describeDemoApiError(ORIGIN_403)).toBe(
      "CROSS_ORIGIN_REQUEST_FORBIDDEN: Requests from origin 'http://127.0.0.1:3011' may not change state. "
        + 'Serve the UI from an origin listed in CORS_ORIGINS.',
    );
  });

  it('formats a dict detail nested in message (503 MODEL UNAVAILABLE)', () => {
    expect(describeDemoApiError(MODEL_503)).toBe(
      'MODEL UNAVAILABLE: agent analysis: no enabled model can serve the request',
    );
  });

  it('uses a plain string message', () => {
    expect(describeDemoApiError(NO_SCENARIO_409)).toBe('No active scenario');
  });

  it('keeps typed, legacy and network formats', () => {
    expect(describeDemoApiError(httpError(409, { error: true, code: 'NO_ELIGIBLE_ASSET', message: 'none' })))
      .toBe('NO_ELIGIBLE_ASSET: none');
    expect(describeDemoApiError(httpError(400, { detail: 'bad' }))).toBe('bad');
    expect(describeDemoApiError(new Error('Network Error'))).toBe('Network Error');
  });
});

// ── ScenarioSelector ───────────────────────────────────────────────────────────

describe('ScenarioSelector start failure', () => {
  beforeEach(() => {
    demoAPI.listScenarios.mockResolvedValue([
      { name: 'labor_constraint_wave_risk', display_name: 'Labor Constraint + Wave Risk', description: 'd', tags: [] },
    ]);
  });

  it('shows the API error and re-enables the button', async () => {
    const onStart = jest.fn().mockRejectedValue(ORIGIN_403);
    wrap(<ScenarioSelector onStart={onStart} />);
    const button = await screen.findByText('Start scenario');
    await act(async () => { fireEvent.click(button); });

    const alert = await screen.findByTestId('scenario-start-error');
    expect(alert).toHaveAttribute('role', 'alert');
    expect(alert).toHaveTextContent('Could not start scenario');
    expect(alert).toHaveTextContent('CROSS_ORIGIN_REQUEST_FORBIDDEN');
    expect(screen.getByText('Start scenario').closest('button')).not.toBeDisabled();
  });

  it('clears the error when a retry succeeds', async () => {
    const onStart = jest.fn().mockRejectedValueOnce(ORIGIN_403).mockResolvedValueOnce(undefined);
    wrap(<ScenarioSelector onStart={onStart} />);
    const button = await screen.findByText('Start scenario');
    await act(async () => { fireEvent.click(button); });
    expect(await screen.findByTestId('scenario-start-error')).toBeInTheDocument();

    await act(async () => { fireEvent.click(screen.getByText('Start scenario')); });
    expect(screen.queryByTestId('scenario-start-error')).not.toBeInTheDocument();
  });
});

// ── Stages ─────────────────────────────────────────────────────────────────────

describe('analysis error in stages', () => {
  const message = 'MODEL UNAVAILABLE: agent analysis: no enabled model can serve the request';

  it('REASON shows the failure instead of only awaiting the model', () => {
    wrap(<ReasonStage {...makeProps({ currentStage: 'REASON', analysisError: message })} />);
    const alert = screen.getByTestId('analysis-error');
    expect(alert).toHaveTextContent('Analysis failed');
    expect(alert).toHaveTextContent(message);
  });

  it('OBSERVE shows the failure next to the Run Analysis button', () => {
    wrap(<ObserveStage {...makeProps({ analysisError: message })} />);
    expect(screen.getByTestId('analysis-error')).toHaveTextContent(message);
    expect(screen.getByTestId('run-analysis-button')).toBeInTheDocument();
  });

  it('shows nothing when there is no error', () => {
    wrap(<ReasonStage {...makeProps({ currentStage: 'REASON' })} />);
    wrap(<ObserveStage {...makeProps()} />);
    expect(screen.queryByTestId('analysis-error')).not.toBeInTheDocument();
  });
});

// ── DemoShell ──────────────────────────────────────────────────────────────────

describe('DemoShell analyze failure', () => {
  it('surfaces a 503 from /demo/analyze', async () => {
    useDemoStatus.mockReturnValue({ status: baseStatus, isLoading: false, isDemoMode: true, refetch: jest.fn() });
    demoAPI.analyze.mockRejectedValue(MODEL_503);

    const DemoShell = require('../../pages/DemoShell').default;
    wrap(<DemoShell />);
    await act(async () => { fireEvent.click(screen.getByTestId('run-analysis-button')); });

    expect(await screen.findByTestId('analysis-error')).toHaveTextContent(
      'MODEL UNAVAILABLE: agent analysis: no enabled model can serve the request',
    );
    expect(screen.getByTestId('run-analysis-button')).not.toBeDisabled();
  });
});
