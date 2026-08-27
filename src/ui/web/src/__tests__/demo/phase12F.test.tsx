/**
 * Phase 12F — Reliability demo mode tests.
 *
 * Scope:
 *   - ReliabilityScenarioSelector: 5 cards, F06 recommended badge, selection
 *   - SafetyContextStrip: counter derivation from SSE events
 *   - ReliabilityLifecycleNarrative: F06 hero flow, F07 duplicate, F12 circuit-open, F01 NIM timeout, F10 state drift
 *   - ReconciliationStatus: phases from SSE categories
 *   - FaultInjectionPanel: reconcile button enable/disable, inject buttons present
 *   - SafetyScorecard: VALIDATED BATCH 6 label, per-scenario invariants
 *   - ReliabilityPanel: integration — renders selector, strip, narrative
 *
 * All 209 prior tests unaffected (no shared state, no file modifications except DemoShell wiring).
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { ThemeProvider } from '@mui/material/styles';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { nvidiaTheme } from '../../theme/nvidiaTheme';
import { SSEEvent } from '../../hooks/useDemoSSE';

import ReliabilityScenarioSelector from '../../components/demo/reliability/ReliabilityScenarioSelector';
import SafetyContextStrip, { deriveSafetyCounters } from '../../components/demo/reliability/SafetyContextStrip';
import ReliabilityLifecycleNarrative from '../../components/demo/reliability/ReliabilityLifecycleNarrative';
import ReconciliationStatus from '../../components/demo/reliability/ReconciliationStatus';
import FaultInjectionPanel from '../../components/demo/reliability/FaultInjectionPanel';
import SafetyScorecard from '../../components/demo/reliability/SafetyScorecard';
import ReliabilityPanel from '../../components/demo/reliability/ReliabilityPanel';

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeSSE(overrides: Partial<SSEEvent>): SSEEvent {
  return {
    id: '1',
    ts: '2026-08-27T10:00:00Z',
    category: 'OBSERVE',
    message: 'test',
    detail: null,
    asset_id: null,
    task_id: null,
    worker_id: null,
    ...overrides,
  };
}

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeProvider theme={nvidiaTheme}>{ui}</ThemeProvider>
    </QueryClientProvider>
  );
}

// ── ReliabilityScenarioSelector ───────────────────────────────────────────────

describe('ReliabilityScenarioSelector', () => {
  it('renders all 5 scenario cards', () => {
    wrap(<ReliabilityScenarioSelector selectedId={null} onSelect={() => {}} />);
    for (const id of ['F06', 'F07', 'F10', 'F12', 'F01']) {
      expect(screen.getByTestId(`fault-scenario-${id}`)).toBeInTheDocument();
    }
  });

  it('marks F06 as recommended with star badge', () => {
    wrap(<ReliabilityScenarioSelector selectedId={null} onSelect={() => {}} />);
    expect(screen.getByTestId('fault-scenario-F06-recommended')).toBeInTheDocument();
    expect(screen.queryByTestId('fault-scenario-F07-recommended')).not.toBeInTheDocument();
  });

  it('calls onSelect with the correct id when a card is clicked', () => {
    const onSelect = jest.fn();
    wrap(<ReliabilityScenarioSelector selectedId={null} onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId('fault-scenario-F10'));
    expect(onSelect).toHaveBeenCalledWith('F10');
  });

  it('marks the selected card with aria-pressed=true', () => {
    wrap(<ReliabilityScenarioSelector selectedId="F07" onSelect={() => {}} />);
    expect(screen.getByTestId('fault-scenario-F07')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('fault-scenario-F06')).toHaveAttribute('aria-pressed', 'false');
  });
});

// ── SafetyContextStrip ─────────────────────────────────────────────────────────

describe('deriveSafetyCounters', () => {
  it('returns all zeros for empty events', () => {
    const c = deriveSafetyCounters([]);
    expect(c).toEqual({ unauthorized: 0, duplicate: 0, falseSuccess: 0, unknown: 0, reconciled: 0 });
  });

  it('counts RECONCILIATION_REQUIRED as unknown', () => {
    const events = [makeSSE({ category: 'RECONCILIATION_REQUIRED' }), makeSSE({ category: 'RECONCILIATION_REQUIRED' })];
    expect(deriveSafetyCounters(events).unknown).toBe(2);
  });

  it('counts CONFIRMED_NOT_EXECUTED as falseSuccess and reconciled', () => {
    const events = [makeSSE({ category: 'CONFIRMED_NOT_EXECUTED' })];
    const c = deriveSafetyCounters(events);
    expect(c.falseSuccess).toBe(1);
    expect(c.reconciled).toBe(1);
  });

  it('counts CONFIRMED_EXECUTED and INDETERMINATE toward reconciled only', () => {
    const events = [
      makeSSE({ category: 'CONFIRMED_EXECUTED' }),
      makeSSE({ category: 'INDETERMINATE' }),
    ];
    const c = deriveSafetyCounters(events);
    expect(c.reconciled).toBe(2);
    expect(c.falseSuccess).toBe(0);
  });

  it('unauthorized and duplicate are always 0', () => {
    const events = [makeSSE({ category: 'CONFIRMED_EXECUTED' })];
    const c = deriveSafetyCounters(events);
    expect(c.unauthorized).toBe(0);
    expect(c.duplicate).toBe(0);
  });
});

describe('SafetyContextStrip', () => {
  it('renders the strip', () => {
    wrap(<SafetyContextStrip sseEvents={[]} />);
    expect(screen.getByTestId('safety-context-strip')).toBeInTheDocument();
  });

  it('shows all 5 counter testids', () => {
    wrap(<SafetyContextStrip sseEvents={[]} />);
    for (const id of ['unauthorized', 'duplicate', 'false-success', 'unknown', 'reconciled']) {
      expect(screen.getByTestId(`counter-${id}`)).toBeInTheDocument();
    }
  });

  it('reflects live SSE unknown count', () => {
    const events = [
      makeSSE({ category: 'RECONCILIATION_REQUIRED' }),
      makeSSE({ category: 'RECONCILIATION_REQUIRED' }),
    ];
    wrap(<SafetyContextStrip sseEvents={events} />);
    expect(screen.getByTestId('counter-unknown')).toHaveTextContent('2');
  });
});

// ── ReliabilityLifecycleNarrative ─────────────────────────────────────────────

describe('ReliabilityLifecycleNarrative — F06 Ambiguous Write', () => {
  it('renders all 6 F06 steps', () => {
    wrap(<ReliabilityLifecycleNarrative scenarioId="F06" sseEvents={[]} />);
    for (const id of ['fault', 'execute', 'unknown', 'safety', 'reconcile', 'confirmed']) {
      expect(screen.getByTestId(`narrative-step-${id}`)).toBeInTheDocument();
    }
  });

  it('first step is active and rest are pending with no SSE events', () => {
    wrap(<ReliabilityLifecycleNarrative scenarioId="F06" sseEvents={[]} />);
    // First step advances to active (no completed steps → step 0 is the next)
    expect(screen.getByTestId('narrative-step-fault')).toHaveAttribute('data-status', 'active');
    expect(screen.getByTestId('narrative-step-execute')).toHaveAttribute('data-status', 'pending');
    expect(screen.getByTestId('narrative-step-confirmed')).toHaveAttribute('data-status', 'pending');
  });

  it('completes fault step on FAULT_INJECTED event', () => {
    const events = [makeSSE({ category: 'FAULT_INJECTED' })];
    wrap(<ReliabilityLifecycleNarrative scenarioId="F06" sseEvents={events} />);
    expect(screen.getByTestId('narrative-step-fault')).toHaveAttribute('data-status', 'complete');
  });

  it('completes through SAFETY on RECONCILIATION_REQUIRED', () => {
    const events = [
      makeSSE({ category: 'RECONCILIATION_REQUIRED' }),
      makeSSE({ category: 'EXECUTE' }),
      makeSSE({ category: 'FAULT_INJECTED' }),
    ];
    wrap(<ReliabilityLifecycleNarrative scenarioId="F06" sseEvents={events} />);
    expect(screen.getByTestId('narrative-step-safety')).toHaveAttribute('data-status', 'complete');
    expect(screen.getByTestId('narrative-step-reconcile')).toHaveAttribute('data-status', 'active');
  });

  it('completes full flow on CONFIRMED_EXECUTED', () => {
    const events = [
      makeSSE({ category: 'CONFIRMED_EXECUTED' }),
      makeSSE({ category: 'RECONCILE' }),
      makeSSE({ category: 'RECONCILIATION_REQUIRED' }),
      makeSSE({ category: 'EXECUTE' }),
      makeSSE({ category: 'FAULT_INJECTED' }),
    ];
    wrap(<ReliabilityLifecycleNarrative scenarioId="F06" sseEvents={events} />);
    expect(screen.getByTestId('narrative-step-confirmed')).toHaveAttribute('data-status', 'complete');
  });
});

describe('ReliabilityLifecycleNarrative — F07 Duplicate Approval', () => {
  it('renders F07 steps', () => {
    wrap(<ReliabilityLifecycleNarrative scenarioId="F07" sseEvents={[]} />);
    expect(screen.getByTestId('narrative-step-approve1')).toBeInTheDocument();
    expect(screen.getByTestId('narrative-step-consumed')).toBeInTheDocument();
    expect(screen.getByTestId('narrative-step-safety')).toBeInTheDocument();
  });

  it('completes approve1 on first APPROVE event', () => {
    const events = [makeSSE({ category: 'APPROVE' })];
    wrap(<ReliabilityLifecycleNarrative scenarioId="F07" sseEvents={events} />);
    expect(screen.getByTestId('narrative-step-approve1')).toHaveAttribute('data-status', 'complete');
    expect(screen.getByTestId('narrative-step-consumed')).toHaveAttribute('data-status', 'active');
  });

  it('completes through SAFETY on two APPROVE events', () => {
    const events = [makeSSE({ category: 'APPROVE', id: '2' }), makeSSE({ category: 'APPROVE', id: '1' })];
    wrap(<ReliabilityLifecycleNarrative scenarioId="F07" sseEvents={events} />);
    expect(screen.getByTestId('narrative-step-safety')).toHaveAttribute('data-status', 'complete');
  });
});

describe('ReliabilityLifecycleNarrative — F12 Circuit Open', () => {
  it('renders F12 steps', () => {
    wrap(<ReliabilityLifecycleNarrative scenarioId="F12" sseEvents={[]} />);
    expect(screen.getByTestId('narrative-step-circuit_open')).toBeInTheDocument();
    expect(screen.getByTestId('narrative-step-safety')).toBeInTheDocument();
    expect(screen.getByTestId('narrative-step-degraded')).toBeInTheDocument();
  });

  it('completes through safety on CIRCUIT_OPEN event', () => {
    const events = [makeSSE({ category: 'CIRCUIT_OPEN' })];
    wrap(<ReliabilityLifecycleNarrative scenarioId="F12" sseEvents={events} />);
    expect(screen.getByTestId('narrative-step-circuit_open')).toHaveAttribute('data-status', 'complete');
    expect(screen.getByTestId('narrative-step-safety')).toHaveAttribute('data-status', 'complete');
    expect(screen.getByTestId('narrative-step-degraded')).toHaveAttribute('data-status', 'active');
  });

  it('completes DEGRADED step from runtime status', () => {
    const runtime = { maiw_operational_status: 'DEGRADED' };
    wrap(<ReliabilityLifecycleNarrative scenarioId="F12" sseEvents={[makeSSE({ category: 'CIRCUIT_OPEN' })]} runtime={runtime} />);
    expect(screen.getByTestId('narrative-step-degraded')).toHaveAttribute('data-status', 'complete');
  });
});

describe('ReliabilityLifecycleNarrative — F01 NIM Timeout', () => {
  it('renders F01 steps', () => {
    wrap(<ReliabilityLifecycleNarrative scenarioId="F01" sseEvents={[]} />);
    expect(screen.getByTestId('narrative-step-timeout')).toBeInTheDocument();
    expect(screen.getByTestId('narrative-step-safety')).toBeInTheDocument();
  });

  it('completes on MODEL TIMEOUT event', () => {
    const events = [makeSSE({ category: 'MODEL TIMEOUT' })];
    wrap(<ReliabilityLifecycleNarrative scenarioId="F01" sseEvents={events} />);
    expect(screen.getByTestId('narrative-step-timeout')).toHaveAttribute('data-status', 'complete');
    expect(screen.getByTestId('narrative-step-safety')).toHaveAttribute('data-status', 'complete');
  });

  it('also completes on REQUEST DEADLINE event', () => {
    const events = [makeSSE({ category: 'REQUEST DEADLINE' })];
    wrap(<ReliabilityLifecycleNarrative scenarioId="F01" sseEvents={events} />);
    expect(screen.getByTestId('narrative-step-timeout')).toHaveAttribute('data-status', 'complete');
  });
});

describe('ReliabilityLifecycleNarrative — F10 State Drift', () => {
  it('renders F10 steps', () => {
    wrap(<ReliabilityLifecycleNarrative scenarioId="F10" sseEvents={[]} />);
    expect(screen.getByTestId('narrative-step-fault')).toBeInTheDocument();
    expect(screen.getByTestId('narrative-step-execute')).toBeInTheDocument();
    expect(screen.getByTestId('narrative-step-conflict')).toBeInTheDocument();
    expect(screen.getByTestId('narrative-step-safety')).toBeInTheDocument();
  });

  it('completes conflict on EXECUTE event with conflict in detail', () => {
    const events = [makeSSE({ category: 'EXECUTE', detail: 'state drift conflict detected' })];
    wrap(<ReliabilityLifecycleNarrative scenarioId="F10" sseEvents={events} />);
    expect(screen.getByTestId('narrative-step-conflict')).toHaveAttribute('data-status', 'complete');
    expect(screen.getByTestId('narrative-step-safety')).toHaveAttribute('data-status', 'complete');
  });
});

// ── ReconciliationStatus ───────────────────────────────────────────────────────

describe('ReconciliationStatus', () => {
  it('renders nothing when no relevant events', () => {
    const { container } = wrap(<ReconciliationStatus sseEvents={[]} />);
    expect(container.querySelector('[data-testid="reconciliation-status"]')).not.toBeInTheDocument();
  });

  it('shows required phase on RECONCILIATION_REQUIRED', () => {
    const events = [makeSSE({ category: 'RECONCILIATION_REQUIRED', detail: { execution_id: 'exec-42', domain: 'equipment' } as any })];
    wrap(<ReconciliationStatus sseEvents={events} />);
    expect(screen.getByTestId('reconciliation-status')).toHaveAttribute('data-phase', 'required');
    expect(screen.getAllByText(/RECONCILIATION REQUIRED/i).length).toBeGreaterThan(0);
  });

  it('shows RECONCILE NOW button when onReconcile provided', () => {
    const events = [makeSSE({ category: 'RECONCILIATION_REQUIRED', detail: { execution_id: 'exec-42', domain: 'equipment' } as any })];
    const onReconcile = jest.fn();
    wrap(<ReconciliationStatus sseEvents={events} onReconcile={onReconcile} />);
    expect(screen.getByTestId('reconcile-status-button')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('reconcile-status-button'));
    expect(onReconcile).toHaveBeenCalledWith('exec-42', 'equipment');
  });

  it('shows in_progress phase on RECONCILE event', () => {
    const events = [
      makeSSE({ category: 'RECONCILE' }),
      makeSSE({ category: 'RECONCILIATION_REQUIRED' }),
    ];
    wrap(<ReconciliationStatus sseEvents={events} />);
    expect(screen.getByTestId('reconciliation-status')).toHaveAttribute('data-phase', 'in_progress');
  });

  it('shows confirmed_executed phase', () => {
    const events = [
      makeSSE({ category: 'CONFIRMED_EXECUTED', detail: { execution_id: 'exec-1' } as any }),
      makeSSE({ category: 'RECONCILE' }),
      makeSSE({ category: 'RECONCILIATION_REQUIRED' }),
    ];
    wrap(<ReconciliationStatus sseEvents={events} />);
    expect(screen.getByTestId('reconciliation-status')).toHaveAttribute('data-phase', 'confirmed_executed');
  });

  it('shows confirmed_not_executed phase', () => {
    const events = [makeSSE({ category: 'CONFIRMED_NOT_EXECUTED' })];
    wrap(<ReconciliationStatus sseEvents={events} />);
    expect(screen.getByTestId('reconciliation-status')).toHaveAttribute('data-phase', 'confirmed_not_executed');
  });

  it('shows indeterminate phase', () => {
    const events = [makeSSE({ category: 'INDETERMINATE' })];
    wrap(<ReconciliationStatus sseEvents={events} />);
    expect(screen.getByTestId('reconciliation-status')).toHaveAttribute('data-phase', 'indeterminate');
  });
});

// ── FaultInjectionPanel ────────────────────────────────────────────────────────

describe('FaultInjectionPanel', () => {
  it('shows F06 inject button', () => {
    wrap(<FaultInjectionPanel scenarioId="F06" sseEvents={[]} />);
    expect(screen.getByTestId('inject-fault-F06')).toBeInTheDocument();
  });

  it('shows reconcile button as disabled with no RECONCILIATION_REQUIRED event', () => {
    wrap(<FaultInjectionPanel scenarioId="F06" sseEvents={[]} />);
    expect(screen.getByTestId('reconcile-button')).toBeDisabled();
  });

  it('enables reconcile button when RECONCILIATION_REQUIRED event fires', () => {
    const events = [makeSSE({ category: 'RECONCILIATION_REQUIRED', detail: { execution_id: 'exec-1', domain: 'equipment' } as any })];
    wrap(<FaultInjectionPanel scenarioId="F06" sseEvents={events} />);
    expect(screen.getByTestId('reconcile-button')).not.toBeDisabled();
  });

  it('shows F07 inject button', () => {
    wrap(<FaultInjectionPanel scenarioId="F07" sseEvents={[]} />);
    expect(screen.getByTestId('inject-fault-F07')).toBeInTheDocument();
  });

  it('shows F12 inject button', () => {
    wrap(<FaultInjectionPanel scenarioId="F12" sseEvents={[]} />);
    expect(screen.getByTestId('inject-fault-F12')).toBeInTheDocument();
  });

  it('shows F01 inject button', () => {
    wrap(<FaultInjectionPanel scenarioId="F01" sseEvents={[]} />);
    expect(screen.getByTestId('inject-fault-F01')).toBeInTheDocument();
  });

  it('shows F10 inject button', () => {
    wrap(<FaultInjectionPanel scenarioId="F10" sseEvents={[]} />);
    expect(screen.getByTestId('inject-fault-F10')).toBeInTheDocument();
  });

  it('shows fallback text when no scenario selected', () => {
    wrap(<FaultInjectionPanel scenarioId={null} sseEvents={[]} />);
    expect(screen.getByText(/Select a scenario/)).toBeInTheDocument();
  });
});

// ── SafetyScorecard ────────────────────────────────────────────────────────────

describe('SafetyScorecard', () => {
  it('renders VALIDATED BATCH 6 label always', () => {
    wrap(<SafetyScorecard scenarioId={null} />);
    expect(screen.getByText(/VALIDATED BATCH 6/)).toBeInTheDocument();
  });

  it('shows F06 invariants D and E', () => {
    wrap(<SafetyScorecard scenarioId="F06" />);
    expect(screen.getByTestId('scorecard-invariant-D')).toBeInTheDocument();
    expect(screen.getByTestId('scorecard-invariant-E')).toBeInTheDocument();
  });

  it('shows F07 invariant C', () => {
    wrap(<SafetyScorecard scenarioId="F07" />);
    expect(screen.getByTestId('scorecard-invariant-C')).toBeInTheDocument();
  });

  it('shows F10 invariant B', () => {
    wrap(<SafetyScorecard scenarioId="F10" />);
    expect(screen.getByTestId('scorecard-invariant-B')).toBeInTheDocument();
  });

  it('shows F12 invariants F and A', () => {
    wrap(<SafetyScorecard scenarioId="F12" />);
    expect(screen.getByTestId('scorecard-invariant-F')).toBeInTheDocument();
    expect(screen.getByTestId('scorecard-invariant-A')).toBeInTheDocument();
  });

  it('shows F01 invariant A', () => {
    wrap(<SafetyScorecard scenarioId="F01" />);
    expect(screen.getByTestId('scorecard-invariant-A')).toBeInTheDocument();
  });

  it('shows select message when no scenario', () => {
    wrap(<SafetyScorecard scenarioId={null} />);
    expect(screen.getByText(/Select a scenario/)).toBeInTheDocument();
  });
});

// ── ReliabilityPanel integration ───────────────────────────────────────────────

describe('ReliabilityPanel', () => {
  it('renders the panel', () => {
    wrap(<ReliabilityPanel sseEvents={[]} />);
    expect(screen.getByTestId('reliability-panel')).toBeInTheDocument();
  });

  it('shows safety context strip', () => {
    wrap(<ReliabilityPanel sseEvents={[]} />);
    expect(screen.getByTestId('safety-context-strip')).toBeInTheDocument();
  });

  it('shows reliability scenario selector', () => {
    wrap(<ReliabilityPanel sseEvents={[]} />);
    expect(screen.getByTestId('reliability-scenario-selector')).toBeInTheDocument();
  });

  it('defaults to F06 selected', () => {
    wrap(<ReliabilityPanel sseEvents={[]} />);
    expect(screen.getByTestId('fault-scenario-F06')).toHaveAttribute('aria-pressed', 'true');
  });

  it('shows F06 narrative by default', () => {
    wrap(<ReliabilityPanel sseEvents={[]} />);
    expect(screen.getByTestId('narrative-F06')).toBeInTheDocument();
  });

  it('shows fault injection panel', () => {
    wrap(<ReliabilityPanel sseEvents={[]} />);
    expect(screen.getByTestId('fault-injection-panel')).toBeInTheDocument();
  });

  it('shows safety scorecard with VALIDATED BATCH 6', () => {
    wrap(<ReliabilityPanel sseEvents={[]} />);
    expect(screen.getByTestId('safety-scorecard')).toBeInTheDocument();
    expect(screen.getByText(/VALIDATED BATCH 6/)).toBeInTheDocument();
  });

  it('switches narrative on scenario card click', () => {
    wrap(<ReliabilityPanel sseEvents={[]} />);
    fireEvent.click(screen.getByTestId('fault-scenario-F12'));
    expect(screen.getByTestId('narrative-F12')).toBeInTheDocument();
  });

  it('reflects live SSE in safety counters', () => {
    const events = [
      makeSSE({ category: 'RECONCILIATION_REQUIRED' }),
      makeSSE({ category: 'CONFIRMED_EXECUTED' }),
    ];
    wrap(<ReliabilityPanel sseEvents={events} />);
    expect(screen.getByTestId('counter-unknown')).toHaveTextContent('1');
    expect(screen.getByTestId('counter-reconciled')).toHaveTextContent('1');
  });
});
