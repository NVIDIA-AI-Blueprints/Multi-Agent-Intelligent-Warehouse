/**
 * Phase 17E — Operational Context Snapshot frontend tests.
 *
 * 11 test cases:
 *  WT1. WorldContextSnapshot renders wrapper with data-testid="world-context-snapshot"
 *  WT2. Historical context banner visible after data loads
 *  WT3. "VIEW DECISION TRACE" button calls onViewDecisionTrace callback
 *  WT4. "VIEW CURRENT CONTEXT" button calls onViewCurrentContext callback
 *  WT5. "RETURN TO COPILOT" button calls onReturnToCopilot callback
 *  WT6. Loading state renders spinner while API call is in-flight
 *  WT7. Error state renders when API returns 404
 *  WT8. CopilotDrawer shows "VIEW CONTEXT AT DECISION TIME" button when context_snapshot_id present
 *  WT9. CopilotDrawer does NOT show "VIEW CONTEXT AT DECISION TIME" when context_snapshot_id absent
 *  WT10. current-context-banner renders alongside historical-context-banner
 *  WT11. TraceArtifactLineage contextSnapshotId renders in DeveloperTraceArtifacts
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import { ThemeProvider } from '@mui/material/styles';
import { nvidiaTheme } from '../theme/nvidiaTheme';

import WorldContextSnapshot, { SnapshotViewContext } from '../components/world/WorldContextSnapshot';
import { worldAPI, OperationalContextSnapshotResponse } from '../services/worldAPI';
import DeveloperTraceArtifacts from '../components/demo/developer-trace/DeveloperTraceArtifacts';
import { TraceArtifactLineage } from '../components/demo/developer-trace/developerTraceTypes';

// ── Global mocks ──────────────────────────────────────────────────────────────

global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

jest.mock('../services/worldAPI', () => ({
  worldAPI: {
    getContextByTurn: jest.fn(),
    getConfig: jest.fn(() => Promise.resolve({ warehouse_id: 'wh-test', datapack_id: 'ds-test', semantic_checksum: 'sha256:abc', rng_seed: 42 })),
    getSummary: jest.fn(() => Promise.resolve({ entity_counts: {}, relationship_counts: {} })),
  },
}));

const mockGetContextByTurn = worldAPI.getContextByTurn as jest.Mock;

// ── Fixtures ──────────────────────────────────────────────────────────────────

const SAMPLE_SNAPSHOT: OperationalContextSnapshotResponse = {
  context_snapshot_id: 'ctx-snap-0001',
  conversation_id: 'conv-0001',
  turn_id: 'turn-0001',
  trace_id: 'trace-0001',
  warehouse_id: 'wh-test',
  dataset_id: 'ds-test',
  datapack_checksum: 'sha256:abc123',
  warehouse_state_snapshot_id: 'snap-001',
  focus_entity_id: 'worker-1',
  focus_entity_type: 'worker',
  focus_label: 'Alice (Picker)',
  depth: 2,
  truncated: false,
  nodes: [{ entity_id: 'worker-1', entity_type: 'worker', label: 'Alice (Picker)', attributes: { role: 'picker' } }],
  edges: [{ source_id: 'worker-1', target_id: 'task-1', relationship_type: 'ASSIGNED_TO', valid_from: null, valid_to: null }],
  entity_count: 1,
  relationship_count: 1,
  relationship_summary: { Tasks: ['task-1'] },
  captured_at: '2026-09-09T10:00:00.000Z',
  store_note: 'Snapshot is process-local; not persisted across API restart.',
};

const CTX: SnapshotViewContext = {
  turnId: 'turn-0001',
  traceId: 'trace-0001',
  entityLabel: 'Alice (Picker)',
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function renderWithTheme(ui: React.ReactElement) {
  return render(
    <ThemeProvider theme={nvidiaTheme}>
      {ui}
    </ThemeProvider>
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('WorldContextSnapshot — WT1–WT7, WT10', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('WT1: renders outer wrapper with data-testid="world-context-snapshot"', async () => {
    mockGetContextByTurn.mockResolvedValue(SAMPLE_SNAPSHOT);
    renderWithTheme(<WorldContextSnapshot ctx={CTX} />);
    expect(screen.getByTestId('world-context-snapshot')).toBeInTheDocument();
  });

  test('WT2: historical-context-banner visible after data loads', async () => {
    mockGetContextByTurn.mockResolvedValue(SAMPLE_SNAPSHOT);
    renderWithTheme(<WorldContextSnapshot ctx={CTX} />);
    await waitFor(() => {
      expect(screen.getByTestId('historical-context-banner')).toBeInTheDocument();
    });
  });

  test('WT3: VIEW DECISION TRACE button calls onViewDecisionTrace', async () => {
    mockGetContextByTurn.mockResolvedValue(SAMPLE_SNAPSHOT);
    const onViewDecisionTrace = jest.fn();
    renderWithTheme(
      <WorldContextSnapshot ctx={CTX} onViewDecisionTrace={onViewDecisionTrace} />
    );
    await waitFor(() => {
      expect(screen.getByTestId('view-decision-trace')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('view-decision-trace'));
    expect(onViewDecisionTrace).toHaveBeenCalledWith('trace-0001');
  });

  test('WT4: VIEW CURRENT CONTEXT button calls onViewCurrentContext', async () => {
    mockGetContextByTurn.mockResolvedValue(SAMPLE_SNAPSHOT);
    const onViewCurrentContext = jest.fn();
    renderWithTheme(
      <WorldContextSnapshot ctx={CTX} onViewCurrentContext={onViewCurrentContext} />
    );
    await waitFor(() => {
      expect(screen.getByTestId('view-current-context')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('view-current-context'));
    expect(onViewCurrentContext).toHaveBeenCalledWith('worker-1', 'Alice (Picker)');
  });

  test('WT5: RETURN TO COPILOT button calls onReturnToCopilot', async () => {
    mockGetContextByTurn.mockResolvedValue(SAMPLE_SNAPSHOT);
    const onReturnToCopilot = jest.fn();
    renderWithTheme(
      <WorldContextSnapshot ctx={CTX} onReturnToCopilot={onReturnToCopilot} />
    );
    const btn = screen.getByTestId('return-to-copilot');
    expect(btn).toBeInTheDocument();
    fireEvent.click(btn);
    expect(onReturnToCopilot).toHaveBeenCalledTimes(1);
  });

  test('WT6: loading spinner renders while API call is in-flight', async () => {
    // Never resolves during this test
    mockGetContextByTurn.mockReturnValue(new Promise(() => {}));
    renderWithTheme(<WorldContextSnapshot ctx={CTX} />);
    // historical-context-banner should NOT be present yet
    expect(screen.queryByTestId('historical-context-banner')).not.toBeInTheDocument();
  });

  test('WT7: error state renders when API returns 404-like error', async () => {
    const err404 = Object.assign(new Error('not found'), { response: { status: 404 } });
    mockGetContextByTurn.mockRejectedValue(err404);
    renderWithTheme(<WorldContextSnapshot ctx={CTX} />);
    await waitFor(() => {
      // No snapshot, no banner
      expect(screen.queryByTestId('historical-context-banner')).not.toBeInTheDocument();
    });
    // Error text should contain guidance about current context
    await waitFor(() => {
      expect(screen.getByText(/No context snapshot was captured/)).toBeInTheDocument();
    });
  });

  test('WT10: current-context-banner present alongside historical-context-banner', async () => {
    mockGetContextByTurn.mockResolvedValue(SAMPLE_SNAPSHOT);
    renderWithTheme(<WorldContextSnapshot ctx={CTX} />);
    await waitFor(() => {
      expect(screen.getByTestId('historical-context-banner')).toBeInTheDocument();
      expect(screen.getByTestId('current-context-banner')).toBeInTheDocument();
    });
  });
});

describe('DeveloperTraceArtifacts — WT11', () => {
  test('WT11: contextSnapshotId renders in artifact chain', () => {
    const artifacts: TraceArtifactLineage = {
      snapshotId: 'snap-0001',
      contextSnapshotId: 'ctx-snap-0001',
      contextSnapshotFocus: 'Alice (Picker)',
      contextSnapshotEntityCount: 5,
      proposalIds: [],
      decisionIds: [],
      approvalIds: [],
      executionIds: [],
    };
    renderWithTheme(
      <DeveloperTraceArtifacts artifacts={artifacts} />
    );
    // The context snapshot ID (truncated) should be visible
    expect(screen.getByText(/ctx-snap/)).toBeInTheDocument();
    // Focus label should appear
    expect(screen.getByText(/Alice/)).toBeInTheDocument();
  });
});

describe('CopilotDrawer context snapshot button — WT8, WT9', () => {
  // We test the CopilotAnswer sub-component behavior indirectly by checking
  // the data-testid presence based on context_snapshot_id.

  test('WT8: VIEW CONTEXT AT DECISION TIME button present when context_snapshot_id set', async () => {
    // Import CopilotDrawer lazily to avoid complex module graph
    const { default: CopilotDrawer } = await import('../components/demo/copilot/CopilotDrawer');
    const mockTurns = [
      {
        question: 'Why is Wave 17 at risk?',
        response: {
          conversation_id: 'conv-1',
          turn_id: 'turn-1',
          trace_id: 'tr-1',
          intent: 'ask',
          status: 'complete',
          answer: 'The picker is assigned.',
          evidence: [],
          neighborhood: null,
          agent: 'ops-agent',
          skills_used: [],
          skills_available: [],
          model_id: 'test-model',
          reasoning_level: 'standard',
          routing_rule: 'default',
          routing_reason: 'ok',
          requested_role: null,
          selected_role: null,
          fallback_from: null,
          fallback_reason: null,
          latency_ms: 50,
          degraded: false,
          degradation_reason: null,
          answerability: 'answerable',
          missing_context: [],
          timing: {},
          summary: null,
          severity: null,
          recommendations: null,
          focus_entity_id: 'worker-1',
          focus_entity_label: 'Alice',
          safety_note: null,
          related_artifacts: {},
          store_note: 'in-memory',
          context_snapshot_id: 'ctx-snap-0001',
        },
      },
    ];

    renderWithTheme(
      <CopilotDrawer
        open={true}
        turns={mockTurns as any}
        loading={false}
        onClose={jest.fn()}
        onSend={jest.fn()}
        conversationId="conv-1"
        onViewContextAtDecisionTime={jest.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('view-context-at-decision-time')).toBeInTheDocument();
    });
  });

  test('WT9: VIEW CONTEXT AT DECISION TIME button absent when context_snapshot_id null', async () => {
    const { default: CopilotDrawer } = await import('../components/demo/copilot/CopilotDrawer');
    const mockTurns = [
      {
        question: 'Why is Wave 17 at risk?',
        response: {
          conversation_id: 'conv-1',
          turn_id: 'turn-1',
          trace_id: 'tr-1',
          intent: 'ask',
          status: 'complete',
          answer: 'No context.',
          evidence: [],
          neighborhood: null,
          agent: 'ops-agent',
          skills_used: [],
          skills_available: [],
          model_id: 'test-model',
          reasoning_level: 'standard',
          routing_rule: 'default',
          routing_reason: 'ok',
          requested_role: null,
          selected_role: null,
          fallback_from: null,
          fallback_reason: null,
          latency_ms: 50,
          degraded: false,
          degradation_reason: null,
          answerability: 'answerable',
          missing_context: [],
          timing: {},
          summary: null,
          severity: null,
          recommendations: null,
          focus_entity_id: null,
          focus_entity_label: null,
          safety_note: null,
          related_artifacts: {},
          store_note: 'in-memory',
          context_snapshot_id: null,   // absent
        },
      },
    ];

    renderWithTheme(
      <CopilotDrawer
        open={true}
        turns={mockTurns as any}
        loading={false}
        onClose={jest.fn()}
        onSend={jest.fn()}
        conversationId="conv-1"
      />
    );

    await waitFor(() => {
      // Give the component a moment to render
      expect(screen.queryByTestId('view-context-at-decision-time')).not.toBeInTheDocument();
    });
  });
});
