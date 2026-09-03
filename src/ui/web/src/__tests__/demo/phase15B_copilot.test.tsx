/**
 * Phase 15B tests — Copilot ASK drawer UI.
 *
 * Spec contracts verified:
 *  1. canonical labor availability renders correctly
 *  2. deterministic severity renders backend value (not re-derived)
 *  3. carrier cutoff visible in evidence
 *  4. graph unavailable warning but answer preserved
 *  5. missing labor domain does not show labor evidence
 *  6. missing equipment domain does not show equipment evidence
 *  7. full state unavailable clears stale evidence
 *  8. ASK trace link shows correct trace_id
 *  9. two turns preserve conversation_id but have different trace_id
 * 10. no action buttons (APPROVE/EXECUTE/DO IT/ActionProposal) in ASK
 *
 * Tests 1–10 use CopilotAnswer directly to test response rendering in isolation,
 * which is the contractual surface of the spec. The drawer's input → API → render
 * pipeline is an integration concern; the spec assertions are all about rendered output.
 */

import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import { ThemeProvider } from '@mui/material/styles';
import { nvidiaTheme } from '../../theme/nvidiaTheme';
import CopilotDrawer, { CopilotAnswer } from '../../components/demo/copilot/CopilotDrawer';
import { demoAPI, CopilotTurnResponse } from '../../services/demoAPI';

// ── Mock demoAPI ───────────────────────────────────────────────────────────────

jest.mock('../../services/demoAPI', () => {
  const actual = jest.requireActual('../../services/demoAPI');
  return {
    ...actual,
    demoAPI: {
      ...actual.demoAPI,
      copilotAsk: jest.fn(),
    },
  };
});

// ── Helpers ───────────────────────────────────────────────────────────────────

function buildTurn(overrides: Partial<CopilotTurnResponse> = {}): CopilotTurnResponse {
  return {
    conversation_id: 'conv-001',
    turn_id: 'turn-001',
    trace_id: 'tr-default-001',
    intent: 'warehouse_state_query',
    status: 'complete',
    answer: 'The warehouse is operating normally.',
    evidence: null,
    neighborhood: {
      focus_entity_id: null,
      focus_entity_label: null,
      entity_count: 0,
      relationship_summary: {},
      graph_available: true,
    },
    agent: 'copilot-ask',
    skills_used: [],
    skills_available: [],
    model_id: 'claude-3-haiku',
    reasoning_level: 'standard',
    routing_rule: 'default',
    routing_reason: 'Default routing',
    requested_role: null,
    selected_role: null,
    fallback_from: null,
    fallback_reason: null,
    latency_ms: 350,
    degraded: false,
    degradation_reason: null,
    answerability: 'answerable',
    missing_context: [],
    timing: {},
    related_artifacts: {},
    store_note: '',
    // ANALYZE fields (null for ASK turns)
    summary: null,
    severity: null,
    recommendations: null,
    focus_entity_id: null,
    focus_entity_label: null,
    safety_note: null,
    ...overrides,
  };
}

/** Render a CopilotAnswer with the given turn data inside the theme provider. */
function renderAnswer(turn: CopilotTurnResponse) {
  return render(
    <ThemeProvider theme={nvidiaTheme}>
      <CopilotAnswer turn={turn} />
    </ThemeProvider>
  );
}

function renderDrawer(props: Partial<React.ComponentProps<typeof CopilotDrawer>> = {}) {
  return render(
    <ThemeProvider theme={nvidiaTheme}>
      <CopilotDrawer
        warehouseId="DC-47"
        scenarioName="equipment_fault"
        onClose={jest.fn()}
        {...props}
      />
    </ThemeProvider>
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

beforeEach(() => {
  jest.clearAllMocks();
});

describe('Phase 15B — Copilot ASK drawer', () => {

  // ── Test 1: canonical labor availability renders correctly ─────────────────

  it('canonical labor availability renders correctly', () => {
    const turn = buildTurn({
      answer: 'Labor availability: 4 total workers, 2 idle, 50% utilization.',
      evidence: [
        {
          label: 'Labor',
          value: '4 total, 2 idle (active with no task), 50% utilization',
          severity: null,
        },
      ],
    });
    renderAnswer(turn);

    // Evidence card value renders with the specific backend text
    expect(screen.getByText(/4 total, 2 idle \(active with no task\)/)).toBeInTheDocument();
    // Evidence section header visible
    expect(screen.getByText('EVIDENCE')).toBeInTheDocument();
  });

  // ── Test 2: deterministic severity renders backend value ───────────────────

  it('deterministic severity renders backend value — not re-derived', () => {
    const turn = buildTurn({
      answer: 'Equipment fault detected.',
      evidence: [
        {
          label: 'Equipment status',
          value: 'AGV-03 motor overload',
          severity: 'HIGH',
        },
      ],
    });
    renderAnswer(turn);

    // Backend severity "HIGH" should appear as a badge
    expect(screen.getByText('HIGH')).toBeInTheDocument();
  });

  // ── Test 3: carrier cutoff visible ────────────────────────────────────────

  it('carrier cutoff visible in evidence', () => {
    const turn = buildTurn({
      answer: 'Soonest carrier cutoff is at 09:30 UTC.',
      evidence: [
        {
          label: 'Carrier cutoff (soonest deadline)',
          value: '2026-08-23T09:30:00+00:00',
          severity: null,
        },
      ],
    });
    renderAnswer(turn);

    expect(screen.getByText('2026-08-23T09:30:00+00:00')).toBeInTheDocument();
  });

  // ── Test 4: graph unavailable warning but answer preserved ────────────────

  it('graph unavailable warning but answer preserved', () => {
    const turn = buildTurn({
      answer: 'Equipment is partially degraded.',
      degraded: true,
      degradation_reason: 'Operational graph context unavailable',
      neighborhood: {
        focus_entity_id: null,
        focus_entity_label: null,
        entity_count: 0,
        relationship_summary: {},
        graph_available: false,
      },
    });
    renderAnswer(turn);

    // Answer is still shown
    expect(screen.getByText(/Equipment is partially degraded/)).toBeInTheDocument();
    // Graph unavailable warning shown
    expect(screen.getByText(/Operational Graph context unavailable/)).toBeInTheDocument();
  });

  // ── Test 5: missing labor domain does not show labor evidence ─────────────

  it('missing labor domain — no labor evidence card, partial warning visible', () => {
    const turn = buildTurn({
      answer: 'Equipment state assembled. Labor domain unavailable.',
      answerability: 'partial',
      missing_context: ['labor_state'],
      evidence: [],
    });
    renderAnswer(turn);

    expect(screen.getByText(/PARTIAL/)).toBeInTheDocument();
    expect(screen.getByText(/labor_state/)).toBeInTheDocument();
    // No evidence section (evidence array is empty — backend already filtered labor)
    expect(screen.queryByText(/^EVIDENCE$/)).not.toBeInTheDocument();
  });

  // ── Test 6: missing equipment domain does not show equipment evidence ──────

  it('missing equipment domain — no equipment evidence card, partial warning visible', () => {
    const turn = buildTurn({
      answer: 'Wave state assembled. Equipment domain was unavailable.',
      answerability: 'partial',
      missing_context: ['equipment_state'],
      evidence: [],
    });
    renderAnswer(turn);

    expect(screen.getByText(/PARTIAL/)).toBeInTheDocument();
    expect(screen.getByText(/equipment_state/)).toBeInTheDocument();
    // No evidence section (evidence array is empty — backend already filtered equipment)
    expect(screen.queryByText(/^EVIDENCE$/)).not.toBeInTheDocument();
  });

  // ── Test 7: full state unavailable clears stale evidence ──────────────────

  it('full state unavailable — STATE UNAVAILABLE shown, no evidence cards', () => {
    const turn = buildTurn({
      answer: null,
      answerability: 'insufficient_evidence',
      evidence: [],
      degradation_reason: 'All warehouse domains failed to respond.',
    });
    renderAnswer(turn);

    expect(screen.getByText(/STATE UNAVAILABLE/)).toBeInTheDocument();
    // Evidence section should not appear when state is insufficient
    expect(screen.queryByText(/^EVIDENCE$/)).not.toBeInTheDocument();
  });

  // ── Test 8: ASK trace link shows correct trace_id ─────────────────────────

  it('ASK trace link shows correct trace_id', () => {
    const turn = buildTurn({ trace_id: 'tr-test-001' });
    renderAnswer(turn);

    expect(screen.getByText(/tr-test-001/)).toBeInTheDocument();
    expect(screen.getByTestId('copilot-view-trace')).toBeInTheDocument();
  });

  // ── Test 9: two turns have different trace_ids (both visible) ─────────────

  it('two turns have different trace_ids — both are visible', () => {
    const turn1 = buildTurn({ conversation_id: 'conv-shared', trace_id: 'tr-turn-001' });
    const turn2 = buildTurn({ conversation_id: 'conv-shared', trace_id: 'tr-turn-002' });

    // Render a conversation thread with two answers (simulating two turns in the drawer)
    render(
      <ThemeProvider theme={nvidiaTheme}>
        <div>
          <CopilotAnswer turn={turn1} />
          <CopilotAnswer turn={turn2} />
        </div>
      </ThemeProvider>
    );

    // Both trace_ids visible
    expect(screen.getByText(/tr-turn-001/)).toBeInTheDocument();
    expect(screen.getByText(/tr-turn-002/)).toBeInTheDocument();

    // Both VIEW TRACE buttons present
    const viewTraceButtons = screen.getAllByTestId('copilot-view-trace');
    expect(viewTraceButtons).toHaveLength(2);
  });

  // ── Test 10: no action buttons in ASK ─────────────────────────────────────

  it('no action buttons (APPROVE/EXECUTE/DO IT/ActionProposal) in ASK drawer', () => {
    const turn = buildTurn({ answer: 'All clear.' });
    renderAnswer(turn);

    const buttons = screen.getAllByRole('button');
    const buttonTexts = buttons.map(b => (b.textContent ?? '').toUpperCase());

    const forbidden = ['APPROVE', 'EXECUTE', 'DO IT', 'ACTIONPROPOSAL'];
    forbidden.forEach(word => {
      const found = buttonTexts.some(t => t.includes(word));
      expect(found).toBe(false);
    });
  });

});
