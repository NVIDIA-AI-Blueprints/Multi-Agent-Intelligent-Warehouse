/**
 * UX-1B Agent/SOP Progress + Delegation Experience Tests
 *
 * Critical invariants:
 * 1. WAITING_FOR_GOVERNANCE maps to "Waiting for governance" (not "waiting to execute")
 * 2. No status maps to "Executing" (agent does not execute)
 * 3. No chain_of_thought, scratchpad, hidden_reasoning exposed
 * 4. No WRITE skill class in AgentActivity UI
 * 5. No "subagent", "ReAct", "LangGraph" in operator view
 * 6. Expert mode off: developer fields hidden
 * 7. Expert mode on: all developer fields visible
 * 8. FAILED visually distinct from ESCALATED
 * 9. Empty state: "No agent procedure is active"
 * 10. Historical shows badge for terminal states
 * 11. SOPProgress step states: completed/current/pending/escalated/governance_wait
 * 12. AuthorityBoundary shown for WAITING_FOR_GOVERNANCE
 * 13. Runtime: adaptive maps to "Adaptive runtime", strict to "Strict SOP runtime"
 * 14. DelegationCard does not expose internal framework terms
 */

import React from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  AGENT_TASK_STATUS_LABEL,
  AGENT_TASK_STATUS_DEV_LABEL,
  RUNTIME_PROFILE_LABEL,
  RUNTIME_PROFILE_DEV_LABEL,
  isTerminal,
  getAgentDisplayName,
  getSopDisplayName,
} from '../constants/agentTaskStates';
import { computeSOPStepDisplays, AgentTaskView } from '../types/agentTask';
import SOPProgress from '../components/demo/SOPProgress';
import AgentActivity from '../components/demo/AgentActivity';
import DelegationSection from '../components/demo/DelegationCard';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const SOP_STEPS = [
  { id: 'establish_state', action: 'gather_operational_context', description: 'Establish current state of the warehouse.' },
  { id: 'diagnose', action: 'determine_primary_constraint', description: 'Diagnose primary constraint.' },
  { id: 'gather_specialist_evidence', action: 'consult_required_domains', description: 'Compare interventions from specialist agents.' },
  { id: 'generate_candidates', action: 'produce_candidate_interventions', description: 'Generate recommendation candidates.' },
  { id: 'submit', action: 'emit_recommended_action', description: 'Submit recommendation to governance.' },
];

function makeTask(overrides: Partial<AgentTaskView> = {}): AgentTaskView {
  return {
    task_id: 'task-abc123',
    agent_id: 'operations_coordination',
    sop_id: 'operations_coordination.wave_risk_resolution',
    sop_version: '1.0',
    objective: 'Recover Wave 17 before carrier cutoff',
    status: 'RUNNING',
    current_step_id: 'gather_specialist_evidence',
    completed_steps: ['establish_state', 'diagnose'],
    iteration: 1,
    conversation_id: null,
    copilot_turn_id: null,
    trace_id: 'trace-xyz',
    context_snapshot_id: 'snap-001',
    delegation_results: [],
    stop_reason: null,
    recommendation_id: null,
    sop_steps: SOP_STEPS,
    created_at: '2026-09-20T10:00:00Z',
    updated_at: '2026-09-20T10:01:00Z',
    ...overrides,
  };
}

// ── 1. Status label invariants ────────────────────────────────────────────────

describe('AgentTaskStatus operator label invariants', () => {
  it('WAITING_FOR_GOVERNANCE maps to "Waiting for governance"', () => {
    expect(AGENT_TASK_STATUS_LABEL['WAITING_FOR_GOVERNANCE']).toBe('Waiting for governance');
  });

  it('WAITING_FOR_GOVERNANCE does not say "waiting to execute"', () => {
    expect(AGENT_TASK_STATUS_LABEL['WAITING_FOR_GOVERNANCE']).not.toMatch(/execut/i);
  });

  it('no status maps to "Executing"', () => {
    for (const label of Object.values(AGENT_TASK_STATUS_LABEL)) {
      expect(label).not.toBe('Executing');
      expect(label).not.toBe('EXECUTING');
    }
  });

  it('PENDING maps to Preparing', () => {
    expect(AGENT_TASK_STATUS_LABEL['PENDING']).toBe('Preparing');
  });

  it('RUNNING maps to Working', () => {
    expect(AGENT_TASK_STATUS_LABEL['RUNNING']).toBe('Working');
  });

  it('WAITING_FOR_SUBAGENT maps to Consulting specialist', () => {
    expect(AGENT_TASK_STATUS_LABEL['WAITING_FOR_SUBAGENT']).toBe('Consulting specialist');
  });

  it('OBSERVING_OUTCOME maps to Verifying outcome', () => {
    expect(AGENT_TASK_STATUS_LABEL['OBSERVING_OUTCOME']).toBe('Verifying outcome');
  });

  it('COMPLETED maps to Completed', () => {
    expect(AGENT_TASK_STATUS_LABEL['COMPLETED']).toBe('Completed');
  });

  it('ESCALATED maps to Needs attention (not generic error)', () => {
    expect(AGENT_TASK_STATUS_LABEL['ESCALATED']).toBe('Needs attention');
    expect(AGENT_TASK_STATUS_LABEL['ESCALATED']).not.toMatch(/error/i);
  });

  it('FAILED maps to Could not complete (distinct from ESCALATED)', () => {
    expect(AGENT_TASK_STATUS_LABEL['FAILED']).toBe('Could not complete');
    expect(AGENT_TASK_STATUS_LABEL['FAILED']).not.toBe(AGENT_TASK_STATUS_LABEL['ESCALATED']);
  });

  it('all 9 backend statuses have operator labels', () => {
    const EXPECTED_STATUSES = [
      'PENDING', 'RUNNING', 'WAITING_FOR_INPUT', 'WAITING_FOR_SUBAGENT',
      'WAITING_FOR_GOVERNANCE', 'OBSERVING_OUTCOME', 'COMPLETED', 'ESCALATED', 'FAILED',
    ];
    for (const s of EXPECTED_STATUSES) {
      expect(AGENT_TASK_STATUS_LABEL[s]).toBeDefined();
      expect(typeof AGENT_TASK_STATUS_LABEL[s]).toBe('string');
    }
  });
});

// ── 2. Developer label invariants ─────────────────────────────────────────────

describe('AgentTaskStatus developer labels', () => {
  it('dev labels use canonical backend enum values', () => {
    expect(AGENT_TASK_STATUS_DEV_LABEL['WAITING_FOR_GOVERNANCE']).toBe('WAITING_FOR_GOVERNANCE');
    expect(AGENT_TASK_STATUS_DEV_LABEL['COMPLETED']).toBe('COMPLETED');
    expect(AGENT_TASK_STATUS_DEV_LABEL['ESCALATED']).toBe('ESCALATED');
  });
});

// ── 3. Terminal state helpers ─────────────────────────────────────────────────

describe('isTerminal', () => {
  it('COMPLETED, ESCALATED, FAILED are terminal', () => {
    expect(isTerminal('COMPLETED')).toBe(true);
    expect(isTerminal('ESCALATED')).toBe(true);
    expect(isTerminal('FAILED')).toBe(true);
  });

  it('RUNNING, PENDING are not terminal', () => {
    expect(isTerminal('RUNNING')).toBe(false);
    expect(isTerminal('PENDING')).toBe(false);
    expect(isTerminal('WAITING_FOR_GOVERNANCE')).toBe(false);
  });
});

// ── 4. Runtime profile labels ─────────────────────────────────────────────────

describe('Runtime profile vocabulary', () => {
  it('adaptive runtime has operator label "Adaptive runtime"', () => {
    expect(RUNTIME_PROFILE_LABEL['adaptive']).toBe('Adaptive runtime');
  });

  it('strict runtime has operator label "Strict SOP runtime"', () => {
    expect(RUNTIME_PROFILE_LABEL['strict']).toBe('Strict SOP runtime');
  });

  it('adaptive maps to DeepAgentsRuntime in developer label', () => {
    expect(RUNTIME_PROFILE_DEV_LABEL['adaptive']).toBe('DeepAgentsRuntime');
  });

  it('strict maps to MAIWDeterministicRuntime in developer label', () => {
    expect(RUNTIME_PROFILE_DEV_LABEL['strict']).toBe('MAIWDeterministicRuntime');
  });
});

// ── 5. computeSOPStepDisplays ─────────────────────────────────────────────────

describe('computeSOPStepDisplays', () => {
  it('marks completed steps as completed', () => {
    const task = makeTask();
    const displays = computeSOPStepDisplays(task);
    expect(displays.find(d => d.step.id === 'establish_state')?.state).toBe('completed');
    expect(displays.find(d => d.step.id === 'diagnose')?.state).toBe('completed');
  });

  it('marks current step as current', () => {
    const task = makeTask();
    const displays = computeSOPStepDisplays(task);
    expect(displays.find(d => d.step.id === 'gather_specialist_evidence')?.state).toBe('current');
  });

  it('marks future steps as pending', () => {
    const task = makeTask();
    const displays = computeSOPStepDisplays(task);
    expect(displays.find(d => d.step.id === 'generate_candidates')?.state).toBe('pending');
    expect(displays.find(d => d.step.id === 'submit')?.state).toBe('pending');
  });

  it('marks current step as governance_wait when status is WAITING_FOR_GOVERNANCE', () => {
    const task = makeTask({
      status: 'WAITING_FOR_GOVERNANCE',
      current_step_id: 'submit',
      completed_steps: ['establish_state', 'diagnose', 'gather_specialist_evidence', 'generate_candidates'],
    });
    const displays = computeSOPStepDisplays(task);
    expect(displays.find(d => d.step.id === 'submit')?.state).toBe('governance_wait');
  });

  it('marks current step as escalated when status is ESCALATED', () => {
    const task = makeTask({
      status: 'ESCALATED',
      current_step_id: 'diagnose',
      completed_steps: ['establish_state'],
    });
    const displays = computeSOPStepDisplays(task);
    expect(displays.find(d => d.step.id === 'diagnose')?.state).toBe('escalated');
  });
});

// ── 6. SOPProgress component ──────────────────────────────────────────────────

describe('SOPProgress component', () => {
  it('renders step labels from SOP description, not hardcoded', () => {
    const task = makeTask();
    render(<SOPProgress task={task} />);
    expect(screen.getByText(/Establish current state/i)).toBeInTheDocument();
    expect(screen.getByText(/Diagnose primary constraint/i)).toBeInTheDocument();
    expect(screen.getByText(/Compare interventions/i)).toBeInTheDocument();
  });

  it('uses role="list" with role="listitem" per step', () => {
    const task = makeTask();
    render(<SOPProgress task={task} />);
    expect(screen.getByRole('list')).toBeInTheDocument();
    const items = screen.getAllByRole('listitem');
    expect(items.length).toBe(SOP_STEPS.length);
  });

  it('current step has aria-label "Current step: ..."', () => {
    const task = makeTask();
    render(<SOPProgress task={task} />);
    const currentItem = screen.getByRole('listitem', { name: /Current step:/i });
    expect(currentItem).toBeInTheDocument();
  });

  it('current step has aria-current="step"', () => {
    const task = makeTask();
    render(<SOPProgress task={task} />);
    const currentItem = screen.getByRole('listitem', { name: /Current step:/i });
    expect(currentItem).toHaveAttribute('aria-current', 'step');
  });

  it('governance_wait step renders with governance wait state label', () => {
    const task = makeTask({
      status: 'WAITING_FOR_GOVERNANCE',
      current_step_id: 'submit',
      completed_steps: ['establish_state', 'diagnose', 'gather_specialist_evidence', 'generate_candidates'],
    });
    render(<SOPProgress task={task} />);
    expect(screen.getByText(/Awaiting approval/i)).toBeInTheDocument();
  });

  it('escalated step renders with ! marker and Escalated label', () => {
    const task = makeTask({
      status: 'ESCALATED',
      current_step_id: 'diagnose',
      completed_steps: ['establish_state'],
    });
    render(<SOPProgress task={task} />);
    // The ! icon and "Escalated" text label
    expect(screen.getByText(/Escalated/i)).toBeInTheDocument();
  });

  it('does not render WRITE capability text', () => {
    const task = makeTask();
    const { container } = render(<SOPProgress task={task} />);
    expect(container.textContent).not.toMatch(/warehouse\.write\./);
    expect(container.textContent).not.toMatch(/action_executor\./);
  });

  it('renders SOP version in header', () => {
    const task = makeTask();
    render(<SOPProgress task={task} />);
    expect(screen.getByText(/Wave Risk Resolution v1\.0/i)).toBeInTheDocument();
  });

  it('shows expert fields when expertMode=true', () => {
    const task = makeTask();
    render(<SOPProgress task={task} expertMode={true} />);
    expect(screen.getByText(/sop_id/i)).toBeInTheDocument();
  });

  it('does not show expert fields when expertMode=false', () => {
    const task = makeTask();
    render(<SOPProgress task={task} expertMode={false} />);
    expect(screen.queryByText(/sop_id/i)).not.toBeInTheDocument();
  });

  it('shows empty message when no steps', () => {
    const task = makeTask({ sop_steps: [] });
    render(<SOPProgress task={task} />);
    expect(screen.getByText(/No procedure steps recorded/i)).toBeInTheDocument();
  });
});

// ── 7. AgentActivity component ────────────────────────────────────────────────

describe('AgentActivity component', () => {
  it('renders agent name and objective', () => {
    const task = makeTask();
    render(<AgentActivity task={task} />);
    expect(screen.getByText(/Operations Coordination Agent/i)).toBeInTheDocument();
    expect(screen.getByText(/Recover Wave 17 before carrier cutoff/i)).toBeInTheDocument();
  });

  it('renders procedure name', () => {
    const task = makeTask();
    render(<AgentActivity task={task} />);
    // May appear multiple times (AgentActivity header + SOPProgress header)
    expect(screen.getAllByText(/Wave Risk Resolution/i).length).toBeGreaterThanOrEqual(1);
  });

  it('expert mode off: does not show agent_id, task_id, sop_version, context_snapshot_id', () => {
    const task = makeTask();
    render(<AgentActivity task={task} expertMode={false} />);
    expect(screen.queryByText('agent_id')).not.toBeInTheDocument();
    expect(screen.queryByText('task_id')).not.toBeInTheDocument();
    expect(screen.queryByText('context_snapshot_id')).not.toBeInTheDocument();
  });

  it('expert mode on: shows all developer fields', () => {
    const task = makeTask();
    render(<AgentActivity task={task} expertMode={true} />);
    const detail = screen.getByTestId('expert-detail');
    expect(within(detail).getByText('task_id')).toBeInTheDocument();
    expect(within(detail).getByText('agent_id')).toBeInTheDocument();
    expect(within(detail).getByText('sop_id')).toBeInTheDocument();
    expect(within(detail).getByText('trace_id')).toBeInTheDocument();
    expect(within(detail).getByText('context_snapshot_id')).toBeInTheDocument();
    expect(within(detail).getByText('iteration')).toBeInTheDocument();
    expect(within(detail).getByText('stop_reason')).toBeInTheDocument();
  });

  it('empty state renders "No agent procedure is active"', () => {
    render(<AgentActivity task={null} />);
    expect(screen.getByTestId('agent-activity-empty')).toBeInTheDocument();
    expect(screen.getByText(/No agent procedure is active/i)).toBeInTheDocument();
  });

  it('historical badge shown for COMPLETED tasks', () => {
    const task = makeTask({ status: 'COMPLETED', completed_steps: [...SOP_STEPS.map(s => s.id)] });
    render(<AgentActivity task={task} />);
    expect(screen.getByTestId('historical-badge')).toBeInTheDocument();
    expect(screen.getByText(/Historical agent task/i)).toBeInTheDocument();
  });

  it('historical badge shown for ESCALATED tasks', () => {
    const task = makeTask({ status: 'ESCALATED' });
    render(<AgentActivity task={task} />);
    expect(screen.getByTestId('historical-badge')).toBeInTheDocument();
  });

  it('historical badge shown for FAILED tasks', () => {
    const task = makeTask({ status: 'FAILED' });
    render(<AgentActivity task={task} />);
    expect(screen.getByTestId('historical-badge')).toBeInTheDocument();
  });

  it('no WRITE skill class text in operator view', () => {
    const task = makeTask();
    const { container } = render(<AgentActivity task={task} />);
    expect(container.textContent).not.toMatch(/warehouse\.write\./);
    expect(container.textContent).not.toMatch(/action_executor\./);
  });

  it('no chain_of_thought field exposed', () => {
    const task = makeTask();
    const { container } = render(<AgentActivity task={task} expertMode={true} />);
    expect(container.textContent).not.toMatch(/chain_of_thought/i);
    expect(container.textContent).not.toMatch(/scratchpad/i);
    expect(container.textContent).not.toMatch(/hidden_reasoning/i);
  });

  it('WAITING_FOR_GOVERNANCE renders governance-transition with AuthorityBoundary', () => {
    const task = makeTask({
      status: 'WAITING_FOR_GOVERNANCE',
      current_step_id: 'submit',
      completed_steps: ['establish_state', 'diagnose', 'gather_specialist_evidence', 'generate_candidates'],
    });
    render(<AgentActivity task={task} />);
    expect(screen.getByTestId('governance-transition')).toBeInTheDocument();
    expect(screen.getByTestId('authority-boundary')).toBeInTheDocument();
  });

  it('WAITING_FOR_GOVERNANCE text includes governance reference, not execution', () => {
    const task = makeTask({
      status: 'WAITING_FOR_GOVERNANCE',
      current_step_id: 'submit',
      completed_steps: ['establish_state', 'diagnose'],
    });
    const { container } = render(<AgentActivity task={task} />);
    expect(container.textContent).toMatch(/governance/i);
    expect(container.textContent).not.toMatch(/waiting to execute/i);
  });

  it('WAITING_FOR_GOVERNANCE text says agent "completed its recommendation"', () => {
    const task = makeTask({ status: 'WAITING_FOR_GOVERNANCE' });
    render(<AgentActivity task={task} />);
    expect(screen.getByText(/completed its recommendation/i)).toBeInTheDocument();
  });

  it('COMPLETED shows outcome-completed', () => {
    const task = makeTask({ status: 'COMPLETED' });
    render(<AgentActivity task={task} />);
    expect(screen.getByTestId('outcome-completed')).toBeInTheDocument();
    expect(screen.getByText(/Objective achieved/i)).toBeInTheDocument();
  });

  it('ESCALATED shows outcome-escalated (distinct from FAILED)', () => {
    const task = makeTask({ status: 'ESCALATED', stop_reason: 'Conflicting evidence' });
    render(<AgentActivity task={task} />);
    const escalatedBox = screen.getByTestId('outcome-escalated');
    expect(escalatedBox).toBeInTheDocument();
    // "Needs attention" appears in header and in outcome box
    expect(screen.getAllByText(/Needs attention/i).length).toBeGreaterThanOrEqual(1);
    // outcome-failed must not appear
    expect(screen.queryByTestId('outcome-failed')).not.toBeInTheDocument();
    // Shows stop reason
    expect(within(escalatedBox).getByText(/Conflicting evidence/i)).toBeInTheDocument();
    // Shows human review message
    expect(within(escalatedBox).getByText(/Human review required/i)).toBeInTheDocument();
  });

  it('FAILED shows outcome-failed (distinct from ESCALATED)', () => {
    const task = makeTask({ status: 'FAILED', stop_reason: 'Network timeout' });
    render(<AgentActivity task={task} />);
    const failedBox = screen.getByTestId('outcome-failed');
    expect(failedBox).toBeInTheDocument();
    expect(within(failedBox).getByText(/Could not complete/i)).toBeInTheDocument();
    // outcome-escalated must not appear
    expect(screen.queryByTestId('outcome-escalated')).not.toBeInTheDocument();
    // Shows stop reason
    expect(within(failedBox).getByText(/Network timeout/i)).toBeInTheDocument();
    // Shows system error message
    expect(within(failedBox).getByText(/system or tool error/i)).toBeInTheDocument();
  });

  it('OBSERVING_OUTCOME shows outcome-observing state', () => {
    const task = makeTask({ status: 'OBSERVING_OUTCOME' });
    render(<AgentActivity task={task} />);
    const observingBox = screen.getByTestId('outcome-observing');
    expect(observingBox).toBeInTheDocument();
    expect(within(observingBox).getByText(/Verifying outcome/i)).toBeInTheDocument();
  });

  it('stale freshness shows FreshnessTag', () => {
    const staleTime = new Date(Date.now() - 200_000).toISOString();
    const task = makeTask({ updated_at: staleTime });
    render(<AgentActivity task={task} />);
    expect(screen.getByTestId('freshness-tag')).toBeInTheDocument();
  });
});

// ── 8. DelegationCard (DelegationSection) ────────────────────────────────────

const DELEGATION_RESULT = {
  delegation_id: 'labor-del-001',
  child_task_id: 'child-labor-001',
  requesting_agent: 'operations_coordination',
  responding_agent: 'labor',
  status: 'COMPLETED',
  assessment: { summary: 'Labor is the dominant constraint.' },
  evidence: ['5 pending tasks', '4 idle workers'],
  candidate_action_count: 2,
  trace_id: 'trace-xyz',
  context_snapshot_id: 'snap-001',
};

describe('DelegationSection (DelegationCard)', () => {
  it('renders specialist name in operator-friendly language', () => {
    const task = makeTask({ delegation_results: [DELEGATION_RESULT] });
    render(<DelegationSection task={task} expertMode={false} />);
    // May appear in chain tree and card header
    expect(screen.getAllByText(/Labor Agent/i).length).toBeGreaterThanOrEqual(1);
  });

  it('renders "Specialist consultation" text, not "subagent invocation"', () => {
    const task = makeTask({ delegation_results: [DELEGATION_RESULT] });
    const { container } = render(<DelegationSection task={task} expertMode={false} />);
    expect(container.textContent).toMatch(/Specialist consultation/i);
    expect(container.textContent).not.toMatch(/subagent invocation/i);
  });

  it('does not say "subagent", "ReAct", "LangGraph" in operator view', () => {
    const task = makeTask({ delegation_results: [DELEGATION_RESULT] });
    const { container } = render(<DelegationSection task={task} expertMode={false} />);
    expect(container.textContent).not.toMatch(/\bsubagent\b/i);
    expect(container.textContent).not.toMatch(/ReAct/);
    expect(container.textContent).not.toMatch(/LangGraph/);
    expect(container.textContent).not.toMatch(/checkpoint/i);
    expect(container.textContent).not.toMatch(/tool invocation/i);
  });

  it('shows assessment finding', () => {
    const task = makeTask({ delegation_results: [DELEGATION_RESULT] });
    render(<DelegationSection task={task} expertMode={false} />);
    expect(screen.getByText(/Labor is the dominant constraint/i)).toBeInTheDocument();
  });

  it('shows evidence items', () => {
    const task = makeTask({ delegation_results: [DELEGATION_RESULT] });
    render(<DelegationSection task={task} expertMode={false} />);
    expect(screen.getByText(/5 pending tasks/i)).toBeInTheDocument();
    expect(screen.getByText(/4 idle workers/i)).toBeInTheDocument();
  });

  it('expert mode shows child_task_id and parent_task_id', async () => {
    const task = makeTask({ delegation_results: [DELEGATION_RESULT] });
    render(<DelegationSection task={task} expertMode={true} />);
    // Click to expand
    const header = screen.getByRole('button', { name: /Specialist consultation/i });
    await userEvent.click(header);
    const detail = screen.getByTestId('delegation-expert-detail');
    expect(within(detail).getByText('child_task_id')).toBeInTheDocument();
    expect(within(detail).getByText('parent_task_id')).toBeInTheDocument();
  });

  it('does not expose chain_of_thought in delegation', () => {
    const task = makeTask({ delegation_results: [DELEGATION_RESULT] });
    const { container } = render(<DelegationSection task={task} expertMode={true} />);
    expect(container.textContent).not.toMatch(/chain_of_thought/i);
    expect(container.textContent).not.toMatch(/scratchpad/i);
  });

  it('renders delegation chain tree for multiple specialists', () => {
    const waveDelegation = {
      ...DELEGATION_RESULT,
      delegation_id: 'wave-del-001',
      child_task_id: 'child-wave-001',
      responding_agent: 'wave',
    };
    const task = makeTask({ delegation_results: [DELEGATION_RESULT, waveDelegation] });
    render(<DelegationSection task={task} />);
    expect(screen.getByTestId('delegation-chain')).toBeInTheDocument();
    // Both agents in chain
    const chain = screen.getByTestId('delegation-chain');
    expect(within(chain).getByText(/Labor Agent/i)).toBeInTheDocument();
    expect(within(chain).getByText(/Wave Agent/i)).toBeInTheDocument();
  });

  it('renders nothing for task with no delegations', () => {
    const task = makeTask({ delegation_results: [] });
    const { container } = render(<DelegationSection task={task} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing for null task', () => {
    const { container } = render(<DelegationSection task={null} />);
    expect(container.firstChild).toBeNull();
  });
});

// ── 9. Architecture invariant — no WRITE capabilities ────────────────────────

describe('Architecture invariant: no WRITE skill class in agent UI', () => {
  const WRITE_PATTERNS = [
    'warehouse.write.',
    'warehouse.labor.assign',
    'warehouse.wave.assign',
    'warehouse.equipment.assign',
    'action_executor.',
    'exec.',
  ];

  it('SOPProgress does not render write capability text', () => {
    const task = makeTask();
    const { container } = render(<SOPProgress task={task} expertMode={true} />);
    for (const pattern of WRITE_PATTERNS) {
      expect(container.textContent).not.toContain(pattern);
    }
  });

  it('AgentActivity does not render write capability text', () => {
    const task = makeTask();
    const { container } = render(<AgentActivity task={task} expertMode={true} />);
    for (const pattern of WRITE_PATTERNS) {
      expect(container.textContent).not.toContain(pattern);
    }
  });
});

// ── 10. Chain-of-thought exclusion ────────────────────────────────────────────

describe('Chain-of-thought exclusion invariant', () => {
  const FORBIDDEN_FIELDS = [
    'chain_of_thought',
    'scratchpad',
    'hidden_reasoning',
    'raw_prompt',
    'system_prompt',
  ];

  it('AgentActivity does not expose forbidden fields', () => {
    const task = makeTask();
    const { container } = render(<AgentActivity task={task} expertMode={true} />);
    for (const field of FORBIDDEN_FIELDS) {
      expect(container.textContent).not.toMatch(new RegExp(field, 'i'));
    }
  });

  it('DelegationSection does not expose forbidden fields', () => {
    const task = makeTask({ delegation_results: [DELEGATION_RESULT] });
    const { container } = render(<DelegationSection task={task} expertMode={true} />);
    for (const field of FORBIDDEN_FIELDS) {
      expect(container.textContent).not.toMatch(new RegExp(field, 'i'));
    }
  });
});

// ── 11. Agent display names ───────────────────────────────────────────────────

describe('Agent display names', () => {
  it('operations_coordination → "Operations Coordination Agent"', () => {
    expect(getAgentDisplayName('operations_coordination')).toBe('Operations Coordination Agent');
  });

  it('labor → "Labor Agent"', () => {
    expect(getAgentDisplayName('labor')).toBe('Labor Agent');
  });

  it('wave → "Wave Agent"', () => {
    expect(getAgentDisplayName('wave')).toBe('Wave Agent');
  });

  it('equipment → "Equipment Agent"', () => {
    expect(getAgentDisplayName('equipment')).toBe('Equipment Agent');
  });

  it('unknown agent returns the raw id as fallback', () => {
    expect(getAgentDisplayName('some_new_agent')).toBe('some_new_agent');
  });
});

// ── 12. SOP display names ─────────────────────────────────────────────────────

describe('SOP display names', () => {
  it('operations_coordination.wave_risk_resolution → "Wave Risk Resolution"', () => {
    expect(getSopDisplayName('operations_coordination.wave_risk_resolution')).toBe('Wave Risk Resolution');
  });

  it('labor.labor_constraint_assessment → "Labor Constraint Assessment"', () => {
    expect(getSopDisplayName('labor.labor_constraint_assessment')).toBe('Labor Constraint Assessment');
  });
});
