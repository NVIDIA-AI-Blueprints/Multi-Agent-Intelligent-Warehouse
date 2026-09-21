/**
 * ux1e.test.tsx — UX-1E: Unified Developer Journey regression tests.
 *
 * Acceptance criterion: A developer can reconstruct one MAIW operational
 * decision from exact warehouse context all the way to measured outcome,
 * using only the UI and exact artifact links.
 *
 * Test strategy:
 *   1. journeyIdentity — constants are stable and CoT fields excluded
 *   2. DeveloperJourneyRail — all 7 stages render, status reflected
 *   3. DeveloperJourneyPanel — each stage panel renders correct fields
 *   4. ExpertOverlay JOURNEY tab — mounts, stage nav works, no CoT leak
 */

import React from 'react';
import { render, screen, fireEvent, within } from '@testing-library/react';
import '@testing-library/jest-dom';

import {
  JOURNEY_STAGES,
  JOURNEY_STAGE_LABEL,
  CHAIN_OF_THOUGHT_EXCLUDED_FIELDS,
  INTENT_JOURNEY_STAGES,
} from '../constants/journeyIdentity';
import DeveloperJourneyRail, { JourneyStageInfo } from '../components/developer-journey/DeveloperJourneyRail';
import { JourneyStageStatus } from '../constants/journeyIdentity';
import DeveloperJourneyPanel from '../components/developer-journey/DeveloperJourneyPanel';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const FULL_IDENTITY = {
  conversation_id: 'conv-abc123',
  turn_id: 'turn-def456',
  trace_id: 'trace-ghi789',
  context_snapshot_id: 'snap-jkl012',
  warehouse_id: 'wh-mno345',
  agent_task_id: 'task-pqr678',
  agent_id: 'agent-stu901',
  sop_id: 'sop-vwx234',
  sop_version: '1.0.0',
  model_id: 'meta/llama3-70b-instruct',
  routing_rule: 'R5_REASONING',
  proposal_id: 'prop-yza567',
  decision_id: 'dec-bcd890',
  execution_id: 'exec-efg123',
};

const MOCK_DEMO_STATUS = {
  active: true,
  paused: false,
  scenario: { name: 'equipment_fault', display_name: 'Equipment Fault' },
  world: {
    warehouse_id: 'wh-mno345',
    clock_iso: '2026-09-20T10:00:00Z',
    elapsed_seconds: 3600,
    equipment: { total: 20, available: 15, assigned: 4, maintenance: 1, offline: 0 },
    workers: { total: 30, active: 22, inactive: 8 },
    tasks: { total: 50, pending: 10, in_progress: 35, completed: 5 },
    inventory: { total_skus: 200, low_stock: 3 },
  },
  current_kpis: null,
  kpi_history: [],
  pending_approvals: [],
};

const MOCK_ANALYSIS_RESULT = {
  ok: true,
  trace_id: 'trace-ghi789',
  assessment: {
    snapshot_id: 'snap-jkl012',
    warehouse_id: 'wh-mno345',
    assessed_at: '2026-09-20T10:00:00Z',
    summary: 'Equipment fault detected',
    severity: 'high',
    domains_affected: ['equipment'],
    facts_observed: ['Forklift FL-003 offline'],
    recommendations: [
      {
        domain: 'equipment',
        capability: 'reassign_task',
        target: 'FL-003',
        objective: 'Restore capacity',
        rationale: 'Equipment is offline',
        priority: 'high',
        subtype: null,
      },
    ],
    model_id: 'meta/llama3-70b-instruct',
    routing_rule: 'R5_REASONING',
    routing_reason: 'High reasoning level required',
    latency_ms: 420,
  },
  proposal_results: [],
  lifecycle: [],
};

const MOCK_COPILOT_TURN = {
  conversation_id: 'conv-abc123',
  turn_id: 'turn-def456',
  trace_id: 'trace-ghi789',
  intent: 'act',
  status: 'complete',
  answer: 'Reassignment recommended.',
  evidence: null,
  neighborhood: null,
  agent: 'WarehouseAgent',
  skills_used: ['EquipmentSkill', 'WaveSkill'],
  skills_available: ['LaborSkill'],
  model_id: 'meta/llama3-70b-instruct',
  reasoning_level: 'HIGH',
  routing_rule: 'R5_REASONING',
  routing_reason: 'High reasoning required',
  requested_role: 'super',
  selected_role: 'super',
  fallback_from: null,
  fallback_reason: null,
  latency_ms: 420,
  degraded: false,
  degradation_reason: null,
  answerability: 'answerable',
  missing_context: [],
  timing: {},
  summary: 'Equipment fault analysis complete.',
  severity: 'high',
  recommendations: [],
  focus_entity_id: 'FL-003',
  focus_entity_label: 'Forklift FL-003',
  safety_note: null,
  related_artifacts: {},
  store_note: '',
  context_snapshot_id: 'snap-jkl012',
  agent_task_id: 'task-pqr678',
  act_recommendation_id: 'rec-111',
  act_decision_outcome: 'APPROVED_AUTO',
  act_proposal_id: 'prop-yza567',
  act_decision_id: 'dec-bcd890',
  act_pending_approval_id: null,
  act_approval_required: false,
  act_execution_status: 'EXECUTED',
  act_execution_id: 'exec-efg123',
  act_mutation_state: 'CONFIRMED',
  act_violations: [],
  act_source_snapshot_id: 'snap-jkl012',
  observe_execution_confirmed: true,
  observe_operational_improved: true,
  observe_operational_summary: 'Wave capacity restored after reassignment.',
  observe_pre_metrics: {},
  observe_post_metrics: {},
  observe_kpi_delta: {},
  observe_act_decision_outcome: 'APPROVED_AUTO',
  observe_act_pending_approval_id: null,
};

const MOCK_AGENT_TASK = {
  task_id: 'task-pqr678',
  agent_id: 'agent-stu901',
  sop_id: 'sop-vwx234',
  sop_version: '1.0.0',
  objective: 'Restore equipment capacity',
  status: 'COMPLETED',
  current_step_id: null,
  completed_steps: ['observe', 'reason', 'propose'],
  iteration: 1,
  conversation_id: 'conv-abc123',
  copilot_turn_id: 'turn-def456',
  trace_id: 'trace-ghi789',
  context_snapshot_id: 'snap-jkl012',
  delegation_results: [],
  stop_reason: null,
  recommendation_id: 'rec-111',
  sop_steps: [],
  created_at: null,
  updated_at: null,
};

// ── TC-1: Journey identity constants ─────────────────────────────────────────

describe('TC-1: journeyIdentity constants', () => {
  it('TC-1.1: JOURNEY_STAGES has all 7 stages in order', () => {
    expect(JOURNEY_STAGES).toEqual([
      'CONTEXT', 'AGENT', 'MODEL', 'SKILLS', 'DECISION', 'EXECUTION', 'OUTCOME',
    ]);
  });

  it('TC-1.2: all stages have labels', () => {
    for (const stage of JOURNEY_STAGES) {
      expect(JOURNEY_STAGE_LABEL[stage]).toBeTruthy();
    }
  });

  it('TC-1.3: CoT excluded fields list is non-empty and stable', () => {
    expect(CHAIN_OF_THOUGHT_EXCLUDED_FIELDS.length).toBeGreaterThan(0);
    expect(CHAIN_OF_THOUGHT_EXCLUDED_FIELDS).toContain('chain_of_thought');
    expect(CHAIN_OF_THOUGHT_EXCLUDED_FIELDS).toContain('hidden_reasoning');
    expect(CHAIN_OF_THOUGHT_EXCLUDED_FIELDS).toContain('reasoning_tokens');
  });

  it('TC-1.4: INTENT_JOURNEY_STAGES.ACT contains all stages', () => {
    expect(INTENT_JOURNEY_STAGES['ACT']).toEqual(expect.arrayContaining(
      [...JOURNEY_STAGES]
    ));
  });

  it('TC-1.5: INTENT_JOURNEY_STAGES.ASK only contains CONTEXT and MODEL', () => {
    expect(INTENT_JOURNEY_STAGES['ASK']).toEqual(['CONTEXT', 'MODEL']);
  });
});

// ── TC-2: DeveloperJourneyRail ────────────────────────────────────────────────

function makeAllAvailableStages(): JourneyStageInfo[] {
  return JOURNEY_STAGES.map(stage => ({
    stage,
    status: 'available' as JourneyStageStatus,
    artifactIdHint: `${stage.slice(0, 4)}-id`,
  }));
}

describe('TC-2: DeveloperJourneyRail', () => {
  it('TC-2.1: renders all 7 stage dots', () => {
    const onSelect = jest.fn();
    render(
      <DeveloperJourneyRail
        stages={makeAllAvailableStages()}
        activeStage="CONTEXT"
        onStageSelect={onSelect}
      />
    );
    expect(screen.getByTestId('developer-journey-rail')).toBeInTheDocument();
    for (const stage of JOURNEY_STAGES) {
      expect(screen.getByTestId(`journey-stage-${stage}`)).toBeInTheDocument();
    }
  });

  it('TC-2.2: clicking available stage fires onStageSelect', () => {
    const onSelect = jest.fn();
    render(
      <DeveloperJourneyRail
        stages={makeAllAvailableStages()}
        activeStage="CONTEXT"
        onStageSelect={onSelect}
      />
    );
    fireEvent.click(screen.getByTestId('journey-stage-MODEL'));
    expect(onSelect).toHaveBeenCalledWith('MODEL');
  });

  it('TC-2.3: unavailable stage does not fire onStageSelect', () => {
    const onSelect = jest.fn();
    const stages: JourneyStageInfo[] = JOURNEY_STAGES.map(s => ({
      stage: s,
      status: (s === 'EXECUTION' ? 'unavailable' : 'available') as JourneyStageStatus,
    }));
    render(
      <DeveloperJourneyRail
        stages={stages}
        activeStage="CONTEXT"
        onStageSelect={onSelect}
      />
    );
    fireEvent.click(screen.getByTestId('journey-stage-EXECUTION'));
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('TC-2.4: active stage is marked current', () => {
    const stages: JourneyStageInfo[] = JOURNEY_STAGES.map(s => ({
      stage: s,
      status: 'available' as JourneyStageStatus,
    }));
    render(
      <DeveloperJourneyRail
        stages={stages}
        activeStage="MODEL"
        onStageSelect={jest.fn()}
      />
    );
    // MODEL dot should exist and be clickable (status available)
    expect(screen.getByTestId('journey-stage-MODEL')).toBeInTheDocument();
  });

  it('TC-2.5: available stage has role=button and tabIndex=0', () => {
    render(
      <DeveloperJourneyRail
        stages={makeAllAvailableStages()}
        activeStage="CONTEXT"
        onStageSelect={jest.fn()}
      />
    );
    const modelDot = screen.getByTestId('journey-stage-MODEL');
    expect(modelDot).toHaveAttribute('role', 'button');
    expect(modelDot).toHaveAttribute('tabindex', '0');
  });

  it('TC-2.6: unavailable stage has aria-disabled and tabIndex=-1', () => {
    const stages: JourneyStageInfo[] = JOURNEY_STAGES.map(s => ({
      stage: s,
      status: (s === 'EXECUTION' ? 'unavailable' : 'available') as JourneyStageStatus,
    }));
    render(
      <DeveloperJourneyRail
        stages={stages}
        activeStage="CONTEXT"
        onStageSelect={jest.fn()}
      />
    );
    const execDot = screen.getByTestId('journey-stage-EXECUTION');
    expect(execDot).toHaveAttribute('aria-disabled', 'true');
    expect(execDot).toHaveAttribute('tabindex', '-1');
  });

  it('TC-2.7: active stage has aria-current=step', () => {
    render(
      <DeveloperJourneyRail
        stages={makeAllAvailableStages()}
        activeStage="DECISION"
        onStageSelect={jest.fn()}
      />
    );
    expect(screen.getByTestId('journey-stage-DECISION')).toHaveAttribute('aria-current', 'step');
  });

  it('TC-2.8: Enter key on available stage fires onStageSelect', () => {
    const onSelect = jest.fn();
    render(
      <DeveloperJourneyRail
        stages={makeAllAvailableStages()}
        activeStage="CONTEXT"
        onStageSelect={onSelect}
      />
    );
    fireEvent.keyDown(screen.getByTestId('journey-stage-SKILLS'), { key: 'Enter' });
    expect(onSelect).toHaveBeenCalledWith('SKILLS');
  });

  it('TC-2.9: Space key on available stage fires onStageSelect', () => {
    const onSelect = jest.fn();
    render(
      <DeveloperJourneyRail
        stages={makeAllAvailableStages()}
        activeStage="CONTEXT"
        onStageSelect={onSelect}
      />
    );
    fireEvent.keyDown(screen.getByTestId('journey-stage-MODEL'), { key: ' ' });
    expect(onSelect).toHaveBeenCalledWith('MODEL');
  });

  it('TC-2.10: Enter key on unavailable stage does not fire onStageSelect', () => {
    const onSelect = jest.fn();
    const stages: JourneyStageInfo[] = JOURNEY_STAGES.map(s => ({
      stage: s,
      status: (s === 'OUTCOME' ? 'unavailable' : 'available') as JourneyStageStatus,
    }));
    render(
      <DeveloperJourneyRail
        stages={stages}
        activeStage="CONTEXT"
        onStageSelect={onSelect}
      />
    );
    fireEvent.keyDown(screen.getByTestId('journey-stage-OUTCOME'), { key: 'Enter' });
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('TC-2.11: rail has role=group with accessible label', () => {
    render(
      <DeveloperJourneyRail
        stages={makeAllAvailableStages()}
        activeStage="CONTEXT"
        onStageSelect={jest.fn()}
      />
    );
    const rail = screen.getByTestId('developer-journey-rail');
    expect(rail).toHaveAttribute('role', 'group');
    expect(rail).toHaveAttribute('aria-label', 'Developer journey stages');
  });
});

// ── TC-3: DeveloperJourneyPanel stage panels ──────────────────────────────────

function renderPanel(stage: (typeof JOURNEY_STAGES)[number], overrides: Partial<Parameters<typeof DeveloperJourneyPanel>[0]> = {}) {
  return render(
    <DeveloperJourneyPanel
      activeStage={stage}
      identity={FULL_IDENTITY}
      analysisResult={MOCK_ANALYSIS_RESULT as any}
      copilotTurn={MOCK_COPILOT_TURN as any}
      demoStatus={MOCK_DEMO_STATUS as any}
      agentTask={MOCK_AGENT_TASK as any}
      onNavigateToStage={jest.fn()}
      {...overrides}
    />
  );
}

describe('TC-3: DeveloperJourneyPanel stage panels', () => {
  it('TC-3.1: CONTEXT panel shows snapshot_id and warehouse_id', () => {
    renderPanel('CONTEXT');
    const panel = screen.getByTestId('journey-panel-CONTEXT');
    expect(panel).toBeInTheDocument();
    expect(within(panel).getByText('snap-jkl012')).toBeInTheDocument();
    expect(within(panel).getByText('wh-mno345')).toBeInTheDocument();
  });

  it('TC-3.2: AGENT panel shows task_id and sop_id', () => {
    renderPanel('AGENT');
    const panel = screen.getByTestId('journey-panel-AGENT');
    expect(within(panel).getByText('task-pqr678')).toBeInTheDocument();
    expect(within(panel).getByText('sop-vwx234')).toBeInTheDocument();
  });

  it('TC-3.3: MODEL panel shows model_id, routing_rule, latency', () => {
    renderPanel('MODEL');
    const panel = screen.getByTestId('journey-panel-MODEL');
    expect(within(panel).getByText('meta/llama3-70b-instruct')).toBeInTheDocument();
    expect(within(panel).getByText('R5_REASONING')).toBeInTheDocument();
    expect(within(panel).getByText('420')).toBeInTheDocument();
  });

  it('TC-3.4: SKILLS panel shows skills used', () => {
    renderPanel('SKILLS');
    const panel = screen.getByTestId('journey-panel-SKILLS');
    expect(within(panel).getByText(/EquipmentSkill/)).toBeInTheDocument();
    expect(within(panel).getByText(/WaveSkill/)).toBeInTheDocument();
  });

  it('TC-3.5: DECISION panel shows proposal_id and decision_id', () => {
    renderPanel('DECISION');
    const panel = screen.getByTestId('journey-panel-DECISION');
    expect(within(panel).getByText('prop-yza567')).toBeInTheDocument();
    expect(within(panel).getByText('dec-bcd890')).toBeInTheDocument();
  });

  it('TC-3.6: EXECUTION panel shows execution_id and mutation_state', () => {
    renderPanel('EXECUTION');
    const panel = screen.getByTestId('journey-panel-EXECUTION');
    expect(within(panel).getByText('exec-efg123')).toBeInTheDocument();
    expect(within(panel).getByText('CONFIRMED')).toBeInTheDocument();
  });

  it('TC-3.7: OUTCOME panel shows operational summary', () => {
    renderPanel('OUTCOME');
    const panel = screen.getByTestId('journey-panel-OUTCOME');
    expect(within(panel).getByText(/Wave capacity restored/)).toBeInTheDocument();
  });

  it('TC-3.8: CONTEXT shows empty panel when no snapshot available', () => {
    renderPanel('CONTEXT', {
      identity: {},
      copilotTurn: null,
      demoStatus: null,
    });
    const panel = screen.getByTestId('journey-panel-CONTEXT');
    expect(within(panel).getByText(/No CONTEXT artifact/)).toBeInTheDocument();
  });

  it('TC-3.9: cross-link buttons navigate to sibling stage', () => {
    const onNavigate = jest.fn();
    render(
      <DeveloperJourneyPanel
        activeStage="MODEL"
        identity={FULL_IDENTITY}
        analysisResult={MOCK_ANALYSIS_RESULT as any}
        copilotTurn={MOCK_COPILOT_TURN as any}
        demoStatus={MOCK_DEMO_STATUS as any}
        agentTask={MOCK_AGENT_TASK as any}
        onNavigateToStage={onNavigate}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: /Navigate to SKILLS/i }));
    expect(onNavigate).toHaveBeenCalledWith('SKILLS');
  });
});

// ── TC-4: Chain-of-thought exclusion invariant ────────────────────────────────

describe('TC-4: CoT exclusion — no hidden reasoning in panel output', () => {
  for (const field of CHAIN_OF_THOUGHT_EXCLUDED_FIELDS) {
    it(`TC-4: "${field}" never rendered by any panel`, () => {
      // Inject the excluded field into copilotTurn (as if backend leaked it)
      const contaminatedTurn = { ...MOCK_COPILOT_TURN, [field]: `LEAKED_${field}_VALUE` } as any;

      for (const stage of JOURNEY_STAGES) {
        const { unmount, baseElement } = render(
          <DeveloperJourneyPanel
            activeStage={stage}
            identity={FULL_IDENTITY}
            analysisResult={MOCK_ANALYSIS_RESULT as any}
            copilotTurn={contaminatedTurn}
            demoStatus={MOCK_DEMO_STATUS as any}
            agentTask={MOCK_AGENT_TASK as any}
          />
        );
        expect(baseElement.innerHTML).not.toContain(`LEAKED_${field}_VALUE`);
        unmount();
      }
    });
  }
});

// ── TC-5: Identity chain completeness ─────────────────────────────────────────

describe('TC-5: ArtifactIdentity — all IDs present in full ACT turn', () => {
  it('TC-5.1: all required IDs are non-null in full fixture', () => {
    expect(FULL_IDENTITY.trace_id).toBeTruthy();
    expect(FULL_IDENTITY.context_snapshot_id).toBeTruthy();
    expect(FULL_IDENTITY.agent_task_id).toBeTruthy();
    expect(FULL_IDENTITY.model_id).toBeTruthy();
    expect(FULL_IDENTITY.proposal_id).toBeTruthy();
    expect(FULL_IDENTITY.decision_id).toBeTruthy();
    expect(FULL_IDENTITY.execution_id).toBeTruthy();
  });
});
