/**
 * F06 (ambiguous write) live-flow UI contracts.
 *
 *  - /demo/approve answering UNKNOWN (202, status 'unknown', executed null,
 *    reconciliation_required) is never rendered as success / "Executed".
 *  - 409 RECONCILIATION_REQUIRED from /demo/approve is rendered as blocked.
 *  - RECONCILE NOW stays disabled until the backend's RECONCILIATION_REQUIRED
 *    SSE event (exact payload shape published by the API), then calls
 *    /demo/reconcile with that execution id + domain and renders the outcome:
 *    CONFIRMED_EXECUTED / CONFIRMED_NOT_EXECUTED / INDETERMINATE.
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import { ThemeProvider } from '@mui/material/styles';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { nvidiaTheme } from '../../theme/nvidiaTheme';

import ApproveStage, { approveResultFor } from '../../components/demo/stages/ApproveStage';
import FaultInjectionPanel from '../../components/demo/reliability/FaultInjectionPanel';
import { DemoStatus, PendingApproval } from '../../services/demoAPI';
import { SSEEvent } from '../../hooks/useDemoSSE';

jest.mock('../../services/demoAPI', () => ({
  demoAPI: {
    approvePending: jest.fn(),
    rejectPending: jest.fn(),
    reconcile: jest.fn(),
    inject: jest.fn(),
    getStatus: jest.fn(),
  },
}));

const { demoAPI } = require('../../services/demoAPI');

const EXEC_ID = 'b33f4b16-4c4e-4c6a-9d1d-c001be097f47';

/** Exactly what the API publishes (ScenarioEvent.to_sse_dict) for an UNKNOWN. */
function reconciliationRequiredEvent(executionId = EXEC_ID): SSEEvent {
  return {
    id: `2026-10-14T20:55:29.264202+00:00-RECONCILIATION_REQUIRED-${executionId}`,
    ts: '2026-10-14T20:55:29.264202+00:00',
    category: 'RECONCILIATION_REQUIRED',
    message: 'reconciliation_required:warehouse.equipment.assign',
    detail: JSON.stringify({
      approval_id: 'appr-1',
      capability: 'warehouse.equipment.assign',
      decision_id: 'dec-1',
      domain: 'equipment',
      error_code: 'MCP_TOOL_ERROR',
      executed: null,
      execution_id: executionId,
      outcome: 'unknown',
      proposal_id: 'prop-1',
      reconcile: {
        body: { domain: 'equipment', execution_id: executionId },
        method: 'POST',
        path: '/api/v1/demo/reconcile',
      },
      retried: false,
      target: 'agv-000',
      trace_id: 'trace-1',
    }),
    asset_id: 'agv-000',
    task_id: null,
    worker_id: null,
    sim_time_seconds: 0,
    execution_id: executionId,
    domain: 'equipment',
  };
}

function confirmedEvent(executionId = EXEC_ID): SSEEvent {
  return {
    id: `x-CONFIRMED_EXECUTED-${executionId}`,
    ts: '2026-10-14T20:55:31+00:00',
    category: 'CONFIRMED_EXECUTED',
    message: 'reconciliation.confirmed_executed',
    detail: JSON.stringify({ execution_id: executionId, domain: 'equipment' }),
    asset_id: 'agv-000',
    task_id: null,
    worker_id: null,
    execution_id: executionId,
    domain: 'equipment',
  };
}

function reconcileResponse(outcome: 'confirmed_executed' | 'confirmed_not_executed' | 'indeterminate') {
  return {
    ok: true,
    execution_id: EXEC_ID,
    domain: 'equipment',
    reconciliation_id: 'rec-1',
    reconciliation_outcome: outcome,
    effective_status:
      outcome === 'confirmed_executed' ? 'effectively_executed'
        : outcome === 'confirmed_not_executed' ? 'effectively_not_executed'
        : 'unknown',
    proposal_id: 'prop-1',
    decision_id: 'dec-1',
    approval_id: 'appr-1',
    trace_id: 'trace-1',
    error: null,
  };
}

/** /demo/approve 202 body for an UNKNOWN execution. */
const UNKNOWN_APPROVE = {
  ok: false,
  status: 'unknown',
  outcome: 'unknown',
  executed: null,
  success: false,
  reconciliation_required: true,
  retried: false,
  capability: 'warehouse.equipment.assign',
  domain: 'equipment',
  target: 'agv-000',
  proposal_id: 'prop-1',
  original_decision_id: 'dec-1',
  approval_id: 'appr-1',
  execution_id: EXEC_ID,
  trace_id: 'trace-1',
  error_code: 'MCP_TOOL_ERROR',
  reconcile: {
    method: 'POST',
    path: '/api/v1/demo/reconcile',
    body: { execution_id: EXEC_ID, domain: 'equipment' },
  },
};

const approval: PendingApproval = {
  pending_id: 'pa-f06',
  proposal_id: 'prop-1',
  decision_id: 'dec-1',
  trace_id: 'trace-1',
  capability: 'warehouse.equipment.assign',
  target: 'agv-000',
  domain: 'equipment',
  risk_level: 'medium',
  objective: 'Put agv-000 on the at-risk pick wave',
  rationale: 'Two operators absent',
  priority: 'high',
  queued_at: new Date(Date.now() - 10_000).toISOString(),
};

const status: DemoStatus = {
  active: true,
  paused: false,
  scenario: { name: 'labor_constraint_wave_risk', display_name: 'Labor + Wave Risk', description: '', tags: [] },
  world: null as any,
  current_kpis: null as any,
  kpi_history: [],
  pending_approvals: [approval],
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

function approveStageProps() {
  return {
    currentStage: 'APPROVE' as const,
    sseEvents: [] as SSEEvent[],
    demoStatus: status,
    analysisResult: null,
    pendingApprovals: [approval],
    analyzing: false,
    onAnalyze: async () => {},
  };
}

// ── Approve: UNKNOWN is never a success ───────────────────────────────────────

describe('ApproveStage — UNKNOWN execution outcome', () => {
  beforeEach(() => jest.clearAllMocks());

  it('maps the UNKNOWN approve response to the unknown state, not success', () => {
    const r = approveResultFor(UNKNOWN_APPROVE);
    expect(r.outcome).toBe('unknown');
    expect(r.ok).toBe(false);
    expect(r.message).toContain('UNKNOWN');
    expect(r.message).toContain(EXEC_ID);
    expect(r.message).not.toMatch(/^Executed/);
  });

  it('a legacy body with status "executed" but reconciliation_required is still UNKNOWN', () => {
    expect(approveResultFor({ ...UNKNOWN_APPROVE, status: 'executed', ok: true }).outcome).toBe('unknown');
  });

  it('maps definite outcomes truthfully', () => {
    expect(approveResultFor({ ok: true, status: 'executed', execution_id: 'e' }).outcome).toBe('approved');
    expect(approveResultFor({ ok: true, status: 'no_op', execution_id: 'e' }).outcome).toBe('approved');
    const failed = approveResultFor({ ok: false, status: 'failed', execution_id: 'e' });
    expect(failed.outcome).toBe('error');
    expect(failed.message).toContain('Not executed (failed)');
  });

  it('renders UNKNOWN — RECONCILE (not APPROVED / Executed) after approve', async () => {
    (demoAPI.approvePending as jest.Mock).mockResolvedValue(UNKNOWN_APPROVE);
    wrap(<ApproveStage {...approveStageProps()} />);

    await act(async () => {
      fireEvent.click(screen.getByTestId('approve-execute-button'));
    });

    await waitFor(() => expect(screen.getByTestId('approval-result')).toBeInTheDocument());
    const result = screen.getByTestId('approval-result');
    expect(result).toHaveTextContent('UNKNOWN — RECONCILE');
    expect(result).toHaveTextContent(/Outcome UNKNOWN/);
    expect(result).not.toHaveTextContent('APPROVED');
    expect(result).not.toHaveTextContent(/Executed/);
    expect(screen.queryByText(/Rail advances to EXECUTE/)).not.toBeInTheDocument();
  });

  it('renders a 409 RECONCILIATION_REQUIRED approve as blocked, not executed', async () => {
    (demoAPI.approvePending as jest.Mock).mockRejectedValue({
      message: 'Request failed with status code 409',
      response: {
        status: 409,
        data: { error: true, code: 'RECONCILIATION_REQUIRED', message: 'unresolved', execution_id: EXEC_ID },
      },
    });
    wrap(<ApproveStage {...approveStageProps()} />);

    await act(async () => {
      fireEvent.click(screen.getByTestId('approve-execute-button'));
    });

    await waitFor(() => expect(screen.getByTestId('approval-result')).toBeInTheDocument());
    const result = screen.getByTestId('approval-result');
    expect(result).toHaveTextContent('ERROR');
    expect(result).toHaveTextContent(/earlier write to this target is UNKNOWN/);
    expect(result).toHaveTextContent(EXEC_ID);
  });
});

// ── Reliability panel: RECONCILE NOW ──────────────────────────────────────────

describe('FaultInjectionPanel — RECONCILE NOW on RECONCILIATION_REQUIRED', () => {
  beforeEach(() => jest.clearAllMocks());

  it('is disabled before the event and enabled by the API event payload', () => {
    const { rerender } = wrap(<FaultInjectionPanel scenarioId="F06" sseEvents={[]} />);
    expect(screen.getByTestId('reconcile-button')).toBeDisabled();
    expect(screen.getByText('Waiting for RECONCILIATION_REQUIRED event...')).toBeInTheDocument();

    rerender(
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient()}>
          <ThemeProvider theme={nvidiaTheme}>
            <FaultInjectionPanel scenarioId="F06" sseEvents={[reconciliationRequiredEvent()]} />
          </ThemeProvider>
        </QueryClientProvider>
      </MemoryRouter>
    );
    expect(screen.getByTestId('reconcile-button')).not.toBeDisabled();
    expect(screen.getByText(`Resolve UNKNOWN for execution ${EXEC_ID} (agv-000)`)).toBeInTheDocument();
  });

  it('enables from the top-level execution_id when detail is not JSON', () => {
    const ev = { ...reconciliationRequiredEvent(), detail: 'not json' };
    wrap(<FaultInjectionPanel scenarioId="F06" sseEvents={[ev]} />);
    expect(screen.getByTestId('reconcile-button')).not.toBeDisabled();
  });

  it('calls /demo/reconcile with the event ids and renders CONFIRMED_EXECUTED', async () => {
    (demoAPI.reconcile as jest.Mock).mockResolvedValue(reconcileResponse('confirmed_executed'));
    wrap(<FaultInjectionPanel scenarioId="F06" sseEvents={[reconciliationRequiredEvent()]} />);

    await act(async () => {
      fireEvent.click(screen.getByTestId('reconcile-button'));
    });

    expect(demoAPI.reconcile).toHaveBeenCalledWith(EXEC_ID, 'equipment');
    const result = await screen.findByTestId('reconcile-result');
    expect(result).toHaveAttribute('data-outcome', 'confirmed_executed');
    expect(result).toHaveTextContent('CONFIRMED_EXECUTED');
    expect(result).toHaveTextContent('effectively_executed');
    // resolved: no second reconcile for the same execution
    expect(screen.getByTestId('reconcile-button')).toBeDisabled();
  });

  it('renders CONFIRMED_NOT_EXECUTED', async () => {
    (demoAPI.reconcile as jest.Mock).mockResolvedValue(reconcileResponse('confirmed_not_executed'));
    wrap(<FaultInjectionPanel scenarioId="F06" sseEvents={[reconciliationRequiredEvent()]} />);
    await act(async () => {
      fireEvent.click(screen.getByTestId('reconcile-button'));
    });
    const result = await screen.findByTestId('reconcile-result');
    expect(result).toHaveTextContent('CONFIRMED_NOT_EXECUTED');
  });

  it('renders INDETERMINATE and keeps RECONCILE NOW available', async () => {
    (demoAPI.reconcile as jest.Mock).mockResolvedValue(reconcileResponse('indeterminate'));
    wrap(<FaultInjectionPanel scenarioId="F06" sseEvents={[reconciliationRequiredEvent()]} />);
    await act(async () => {
      fireEvent.click(screen.getByTestId('reconcile-button'));
    });
    const result = await screen.findByTestId('reconcile-result');
    expect(result).toHaveTextContent('INDETERMINATE');
    expect(result).toHaveTextContent(/Manual review required/);
    expect(screen.getByTestId('reconcile-button')).not.toBeDisabled();
  });

  it('a CONFIRMED_EXECUTED event for that execution disables RECONCILE NOW', () => {
    wrap(
      <FaultInjectionPanel
        scenarioId="F06"
        sseEvents={[confirmedEvent(), reconciliationRequiredEvent()]}
      />
    );
    expect(screen.getByTestId('reconcile-button')).toBeDisabled();
  });

  it('a newer unresolved UNKNOWN stays reconcilable after an older one resolved', () => {
    wrap(
      <FaultInjectionPanel
        scenarioId="F06"
        sseEvents={[reconciliationRequiredEvent('exec-new'), confirmedEvent(), reconciliationRequiredEvent()]}
      />
    );
    expect(screen.getByTestId('reconcile-button')).not.toBeDisabled();
    expect(screen.getByText(/Resolve UNKNOWN for execution exec-new/)).toBeInTheDocument();
  });

  it('renders a typed reconcile error', async () => {
    (demoAPI.reconcile as jest.Mock).mockRejectedValue({
      response: { status: 404, data: { detail: `No execution record found for execution_id='${EXEC_ID}'` } },
    });
    wrap(<FaultInjectionPanel scenarioId="F06" sseEvents={[reconciliationRequiredEvent()]} />);
    await act(async () => {
      fireEvent.click(screen.getByTestId('reconcile-button'));
    });
    expect(await screen.findByTestId('inject-result')).toHaveTextContent(/Reconcile error: No execution record found/);
  });
});
