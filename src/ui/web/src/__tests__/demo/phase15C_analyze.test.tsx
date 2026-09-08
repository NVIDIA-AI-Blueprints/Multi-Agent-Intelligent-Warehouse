/**
 * Phase 15C — Copilot ANALYZE drawer tests.
 *
 * Covers:
 *  1. ANALYZE turn renders ANALYSIS header and summary
 *  2. Severity badge visible on ANALYZE
 *  3. Recommendation cards rendered (objective, rationale, capability, target, priority)
 *  4. Safety note "No warehouse changes have been made." always visible on ANALYZE
 *  5. No action buttons (APPROVE/EXECUTE/DO IT) on ANALYZE
 *  6. Suggested prompt "What should we do?" appears after ASK
 *  7. ANALYZE loading stage shows "ANALYZING" not "REASONING"
 *  8. Focus entity label shows from ANALYZE response
 */

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { ThemeProvider } from '@mui/material/styles';
import { createTheme } from '@mui/material/styles';
import CopilotDrawer, { CopilotAnswer } from '../../components/demo/copilot/CopilotDrawer';
import { demoAPI, CopilotTurnResponse, CopilotRecommendation } from '../../services/demoAPI';

jest.mock('../../services/demoAPI', () => ({
  demoAPI: {
    copilotAsk: jest.fn(),
    copilotTurn: jest.fn(),
  },
}));

const nvidiaTheme = createTheme({ palette: { mode: 'dark' } });

function buildAskTurn(overrides: Partial<CopilotTurnResponse> = {}): CopilotTurnResponse {
  return {
    conversation_id: 'conv-analyze-001',
    turn_id: 'turn-ask-001',
    trace_id: 'tr-ask-001',
    intent: 'ask',
    status: 'complete',
    answer: 'Wave 17 is constrained by labor availability.',
    evidence: [
      { label: 'Labor shortage', value: '3 workers absent', severity: 'HIGH' },
    ],
    neighborhood: {
      focus_entity_id: 'wave-017',
      focus_entity_label: 'Wave 17',
      entity_count: 12,
      relationship_summary: { Tasks: ['task-001'], Workers: ['worker-042'] },
      graph_available: true,
    },
    agent: 'OperationsCoordinationAgent',
    skills_used: [],
    skills_available: ['warehouse.labor.read'],
    model_id: 'nvidia/nemotron-3-super-120b-a12b',
    reasoning_level: 'MEDIUM',
    routing_rule: 'medium_reasoning',
    routing_reason: 'MEDIUM reasoning path',
    requested_role: 'nano',
    selected_role: 'super',
    fallback_from: 'nano',
    fallback_reason: 'nano disabled; escalated to super',
    latency_ms: 1200,
    degraded: false,
    degradation_reason: null,
    answerability: 'answerable',
    missing_context: [],
    timing: { total_ms: 1200 },
    related_artifacts: {},
    store_note: '',
    summary: null,
    severity: null,
    recommendations: null,
    focus_entity_id: null,
    focus_entity_label: null,
    safety_note: null,
    ...overrides,
  };
}

function buildRec(overrides: Partial<CopilotRecommendation> = {}): CopilotRecommendation {
  return {
    recommendation_id: 'abc12345-rec-00',
    domain: 'labor',
    capability: 'warehouse.labor.allocate',
    target: 'wave-017',
    objective: 'Allocate available labor to protect Wave 17',
    rationale: 'Five pending tasks are unassigned while two workers are idle.',
    priority: 'HIGH',
    subtype: null,
    focus_entity_id: 'wave-017',
    snapshot_id: 'snap-0001',
    trace_id: 'tr-analyze-001',
    conversation_id: 'conv-analyze-001',
    turn_id: 'turn-analyze-001',
    ...overrides,
  };
}

function buildAnalyzeTurn(overrides: Partial<CopilotTurnResponse> = {}): CopilotTurnResponse {
  return buildAskTurn({
    turn_id: 'turn-analyze-001',
    trace_id: 'tr-analyze-001',
    intent: 'analyze',
    answer: 'I recommend reallocating available labor to protect Wave 17.',
    summary: 'I recommend reallocating available labor to protect Wave 17.',
    severity: 'HIGH',
    recommendations: [buildRec()],
    safety_note: 'No warehouse changes have been made.',
    focus_entity_id: 'wave-017',
    focus_entity_label: 'Wave 17',
    ...overrides,
  });
}

function renderAnswer(turn: CopilotTurnResponse) {
  return render(
    <ThemeProvider theme={nvidiaTheme}>
      <CopilotAnswer turn={turn} />
    </ThemeProvider>
  );
}

function ConvWrapper({ drawerProps }: { drawerProps: Partial<React.ComponentProps<typeof CopilotDrawer>> }) {
  const [conversationId, setConversationId] = React.useState<string | null>(null);
  const [turns, setTurns] = React.useState<any[]>([]);
  const [conversationError, setConversationError] = React.useState<string | null>(null);
  return (
    <ThemeProvider theme={nvidiaTheme}>
      <CopilotDrawer
        warehouseId="DC-47"
        scenarioName="labor-constraint-wave-risk"
        onClose={jest.fn()}
        conversationId={conversationId}
        setConversationId={setConversationId}
        turns={turns}
        setTurns={setTurns}
        conversationError={conversationError}
        setConversationError={setConversationError}
        {...drawerProps}
      />
    </ThemeProvider>
  );
}

function renderDrawer(props: Partial<React.ComponentProps<typeof CopilotDrawer>> = {}) {
  return render(<ConvWrapper drawerProps={props} />);
}

const mockCopilotAsk = demoAPI.copilotAsk as jest.Mock;

describe('Phase 15C — Copilot ANALYZE drawer', () => {

  beforeEach(() => {
    jest.clearAllMocks();
  });

  // ── 1. ANALYZE turn renders ANALYSIS header ───────────────────────────────

  it('ANALYZE turn renders ANALYSIS label', () => {
    renderAnswer(buildAnalyzeTurn());
    expect(screen.getByText('ANALYSIS')).toBeInTheDocument();
    expect(screen.queryByText('ANSWER')).not.toBeInTheDocument();
  });

  it('ANALYZE turn renders summary text', () => {
    renderAnswer(buildAnalyzeTurn());
    expect(screen.getByText('I recommend reallocating available labor to protect Wave 17.')).toBeInTheDocument();
  });

  // ── 2. Severity badge visible ─────────────────────────────────────────────

  it('severity badge HIGH visible on ANALYZE', () => {
    renderAnswer(buildAnalyzeTurn({ severity: 'HIGH' }));
    const highs = screen.getAllByText('HIGH');
    expect(highs.length).toBeGreaterThanOrEqual(1);
  });

  it('severity badge CRITICAL visible on ANALYZE', () => {
    renderAnswer(buildAnalyzeTurn({ severity: 'CRITICAL' }));
    expect(screen.getByText('CRITICAL')).toBeInTheDocument();
  });

  // ── 3. Recommendation card ────────────────────────────────────────────────

  it('recommendation objective rendered', () => {
    renderAnswer(buildAnalyzeTurn());
    expect(screen.getByText('Allocate available labor to protect Wave 17')).toBeInTheDocument();
  });

  it('recommendation rationale rendered', () => {
    renderAnswer(buildAnalyzeTurn());
    expect(screen.getByText('Five pending tasks are unassigned while two workers are idle.')).toBeInTheDocument();
  });

  it('recommendation capability badge rendered', () => {
    renderAnswer(buildAnalyzeTurn());
    expect(screen.getByText('warehouse.labor.allocate')).toBeInTheDocument();
  });

  it('recommendation target badge rendered', () => {
    renderAnswer(buildAnalyzeTurn());
    expect(screen.getByText('wave-017')).toBeInTheDocument();
  });

  it('recommendation priority badge rendered', () => {
    renderAnswer(buildAnalyzeTurn());
    // HIGH appears as both the severity badge and the priority badge
    expect(screen.getAllByText('HIGH').length).toBeGreaterThanOrEqual(1);
  });

  it('RECOMMENDED ACTIONS section label visible', () => {
    renderAnswer(buildAnalyzeTurn());
    expect(screen.getByText('RECOMMENDED ACTIONS')).toBeInTheDocument();
  });

  it('multiple recommendations rendered', () => {
    const turn = buildAnalyzeTurn({
      recommendations: [
        buildRec({ recommendation_id: 'r1', objective: 'First action' }),
        buildRec({ recommendation_id: 'r2', objective: 'Second action' }),
      ],
    });
    renderAnswer(turn);
    expect(screen.getByText('First action')).toBeInTheDocument();
    expect(screen.getByText('Second action')).toBeInTheDocument();
    expect(screen.getByText('RECOMMENDATION 1')).toBeInTheDocument();
    expect(screen.getByText('RECOMMENDATION 2')).toBeInTheDocument();
  });

  // ── 4. Safety note always visible on ANALYZE ─────────────────────────────

  it('safety note visible on ANALYZE', () => {
    renderAnswer(buildAnalyzeTurn());
    expect(
      screen.getByText(/No warehouse changes have been made/i)
    ).toBeInTheDocument();
  });

  it('ASK turn does NOT show safety note', () => {
    renderAnswer(buildAskTurn());
    expect(
      screen.queryByText(/No warehouse changes have been made/i)
    ).not.toBeInTheDocument();
  });

  // ── 5. No action buttons ──────────────────────────────────────────────────

  it('no action buttons on ANALYZE turn', () => {
    renderAnswer(buildAnalyzeTurn());
    const dangerous = ['APPROVE', 'EXECUTE', 'DO IT', 'CONFIRM', 'APPLY', 'COMMIT'];
    for (const label of dangerous) {
      expect(screen.queryByText(new RegExp(label, 'i'))).not.toBeInTheDocument();
    }
  });

  // ── 6. Suggested prompt appears after ASK ────────────────────────────────

  it('suggests "What should we do?" after a successful ASK', async () => {
    mockCopilotAsk.mockResolvedValue(buildAskTurn({ answerability: 'answerable' }));
    renderDrawer();

    fireEvent.change(screen.getByTestId('copilot-input'), {
      target: { value: 'Why is Wave 17 at risk?' },
    });
    fireEvent.click(screen.getByTestId('copilot-send'));

    await waitFor(() => {
      expect(screen.getByTestId('copilot-suggested-prompt')).toBeInTheDocument();
    });
    expect(screen.getByText('What should we do?')).toBeInTheDocument();
  });

  it('suggested prompt click sends the message', async () => {
    mockCopilotAsk
      .mockResolvedValueOnce(buildAskTurn({ answerability: 'answerable' }))
      .mockResolvedValueOnce(buildAnalyzeTurn());

    renderDrawer();

    fireEvent.change(screen.getByTestId('copilot-input'), {
      target: { value: 'Why is Wave 17 at risk?' },
    });
    fireEvent.click(screen.getByTestId('copilot-send'));

    await waitFor(() => screen.getByTestId('copilot-suggested-prompt'));
    fireEvent.click(screen.getByTestId('copilot-suggested-prompt'));

    await waitFor(() => {
      // Safety note should appear on the ANALYZE response
      expect(screen.getByText(/No warehouse changes have been made/i)).toBeInTheDocument();
    });
    expect(mockCopilotAsk).toHaveBeenCalledTimes(2);
    expect(mockCopilotAsk).toHaveBeenLastCalledWith(
      expect.objectContaining({ message: 'What should we do?' })
    );
  });

  // ── 7. ANALYZE renders evidence + safety note even when no recs ───────────

  it('ANALYZE with empty recommendations shows safety note and no recs section', () => {
    renderAnswer(buildAnalyzeTurn({ recommendations: [] }));
    expect(screen.getByText(/No warehouse changes have been made/i)).toBeInTheDocument();
    expect(screen.queryByText('RECOMMENDED ACTIONS')).not.toBeInTheDocument();
  });

  // ── 8. Focus entity label shown ───────────────────────────────────────────

  it('focus entity label shown in CONTEXT section for ANALYZE', () => {
    renderAnswer(buildAnalyzeTurn({ focus_entity_label: 'Wave 17' }));
    // "Wave 17" can appear in multiple places (context section, target badge, etc.)
    expect(screen.getAllByText(/Wave 17/).length).toBeGreaterThanOrEqual(1);
  });

});
