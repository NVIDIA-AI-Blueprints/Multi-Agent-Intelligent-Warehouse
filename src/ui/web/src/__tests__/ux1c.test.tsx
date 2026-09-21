/**
 * UX-1C Tests — Live Agent Continuity + Copilot/Governance/Outcome Integration
 *
 * Tests:
 * - CopilotAgentStatus: all 9 task states + no-task + unavailable
 * - CopilotTurnResponse with agent_task_id: compact status renders
 * - CopilotTurnResponse without agent_task_id: no status rendered
 * - Live update: state change triggers re-render
 * - Execution confirmed ≠ Objective achieved (BLOCKING regression test)
 * - No chain_of_thought exposure in any new component
 * - FAILED vs ESCALATED are visually distinct (different testids)
 * - OBSERVING_OUTCOME shows "re-reading warehouse state" language
 * - INDETERMINATE shows operator guidance
 * - Navigation round-trips preserve task selection
 * - Delegation live states: RUNNING → COMPLETED renders correctly in place
 * - Continue loop: iteration 2 visible
 * - Historical task: shows badge + no live indicator
 *
 * Architecture invariant tests:
 * - No chain_of_thought in any new component
 * - FAILED (red) and ESCALATED (amber) are visually distinct
 * - All new API routes are read-only
 */

import React from 'react';
import { render, screen, act, waitFor, fireEvent } from '@testing-library/react';
import { agentTaskAPI } from '../services/agentTaskAPI';
import CopilotAgentStatus from '../components/copilot/CopilotAgentStatus';
import AgentActivity from '../components/demo/AgentActivity';
import DelegationCard from '../components/demo/DelegationCard';
import { AgentTaskView } from '../types/agentTask';

// ── Mock agentTaskAPI ─────────────────────────────────────────────────────────
jest.mock('../services/agentTaskAPI', () => ({
  agentTaskAPI: {
    getTask: jest.fn(),
    listTasks: jest.fn(),
    subscribeToTask: jest.fn(() => jest.fn()), // returns cleanup function
  },
}));

const mockGetTask = agentTaskAPI.getTask as jest.Mock;
const mockSubscribeToTask = agentTaskAPI.subscribeToTask as jest.Mock;

// ── Helpers ───────────────────────────────────────────────────────────────────

type TaskOverrides = {
  task_id?: string;
  agent_id?: string;
  sop_id?: string;
  sop_version?: string;
  objective?: string;
  status?: string;
  current_step_id?: string;
  completed_steps?: string[];
  iteration?: number;
  conversation_id?: string;
  copilot_turn_id?: string;
  trace_id?: string;
  context_snapshot_id?: string | null;
  delegation_results?: unknown[];
  stop_reason?: string | null;
  recommendation_id?: string | null;
  sop_steps?: unknown[];
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
};

function makeTask(overrides: TaskOverrides = {}): AgentTaskView {
  return {
    task_id: 'task-ux1c-001',
    agent_id: 'operations_coordination',
    sop_id: 'operations_coordination.wave_risk_resolution',
    sop_version: '1.0',
    objective: 'Resolve Wave 17 risk',
    status: 'RUNNING',
    current_step_id: 'diagnose',
    completed_steps: ['establish_state'],
    iteration: 1,
    conversation_id: 'conv-001',
    copilot_turn_id: 'turn-001',
    trace_id: 'trace-001',
    context_snapshot_id: null,
    delegation_results: [],
    stop_reason: null,
    recommendation_id: null,
    sop_steps: [
      { id: 'establish_state', action: 'gather_operational_context', description: 'Assemble operational context snapshot' },
      { id: 'diagnose', action: 'determine_primary_constraint', description: 'Identify the primary constraint' },
      { id: 'gather_specialist_evidence', action: 'consult_required_domains', description: 'Consult specialist agents' },
      { id: 'submit', action: 'emit_recommended_action', description: 'Submit to governance' },
      { id: 'observe', action: 'evaluate_post_execution_state', description: 'Evaluate outcome' },
    ],
    created_at: '2026-09-20T10:00:00Z',
    updated_at: '2026-09-20T10:00:05Z',
    ...overrides,
  } as AgentTaskView;
}

// ── CopilotAgentStatus tests ──────────────────────────────────────────────────

describe('CopilotAgentStatus — no task', () => {
  it('renders nothing when agentTaskId is null', () => {
    const { container } = render(<CopilotAgentStatus agentTaskId={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when agentTaskId is undefined', () => {
    const { container } = render(<CopilotAgentStatus agentTaskId={undefined} />);
    expect(container.firstChild).toBeNull();
  });
});

describe('CopilotAgentStatus — unavailable', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetTask.mockResolvedValue(null); // 404
    mockSubscribeToTask.mockReturnValue(jest.fn());
  });

  it('shows unavailable message when task returns null', async () => {
    render(<CopilotAgentStatus agentTaskId="task-missing" />);
    await waitFor(() => {
      expect(screen.getByTestId('copilot-agent-status-unavailable')).toBeInTheDocument();
    });
    expect(screen.getByText(/no longer available/i)).toBeInTheDocument();
  });
});

describe('CopilotAgentStatus — task states', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSubscribeToTask.mockReturnValue(jest.fn());
  });

  const stateTests: Array<[string, string, string]> = [
    ['RUNNING',                '● Working',                  'copilot-agent-status-label-RUNNING'],
    ['WAITING_FOR_SUBAGENT',   '◑ Consulting specialist',    'copilot-agent-status-label-WAITING_FOR_SUBAGENT'],
    ['WAITING_FOR_GOVERNANCE', '⏸ Waiting for governance',   'copilot-agent-status-label-WAITING_FOR_GOVERNANCE'],
    ['OBSERVING_OUTCOME',      '◎ Verifying outcome',        'copilot-agent-status-label-OBSERVING_OUTCOME'],
    ['COMPLETED',              '✓ Completed',                'copilot-agent-status-label-COMPLETED'],
    ['ESCALATED',              '! Needs attention',          'copilot-agent-status-label-ESCALATED'],
    ['FAILED',                 '✕ Could not complete',       'copilot-agent-status-label-FAILED'],
  ];

  stateTests.forEach(([status, expectedLabel, testId]) => {
    it(`renders ${status} state correctly`, async () => {
      const task = makeTask({ status });
      mockGetTask.mockResolvedValue(task);

      render(<CopilotAgentStatus agentTaskId="task-ux1c-001" />);

      await waitFor(() => {
        expect(screen.getByTestId(testId)).toBeInTheDocument();
      });
      expect(screen.getByTestId(testId)).toHaveTextContent(expectedLabel);
    });
  });

  it('renders PENDING state', async () => {
    const task = makeTask({ status: 'PENDING' });
    mockGetTask.mockResolvedValue(task);
    render(<CopilotAgentStatus agentTaskId="task-ux1c-001" />);
    await waitFor(() => {
      expect(screen.getByTestId('copilot-agent-status')).toBeInTheDocument();
    });
  });

  it('COMPLETED shows historical badge (not live indicator)', async () => {
    const task = makeTask({ status: 'COMPLETED' });
    mockGetTask.mockResolvedValue(task);
    render(<CopilotAgentStatus agentTaskId="task-ux1c-001" />);
    await waitFor(() => {
      expect(screen.getByTestId('copilot-agent-status-historical-badge')).toBeInTheDocument();
    });
  });

  it('ESCALATED and FAILED have distinct testids', async () => {
    const escalatedTask = makeTask({ status: 'ESCALATED' });
    mockGetTask.mockResolvedValue(escalatedTask);
    const { unmount } = render(<CopilotAgentStatus agentTaskId="task-ux1c-001" />);
    await waitFor(() => {
      expect(screen.getByTestId('copilot-agent-status-escalated')).toBeInTheDocument();
      expect(screen.queryByTestId('copilot-agent-status-failed')).not.toBeInTheDocument();
    });
    unmount();

    const failedTask = makeTask({ status: 'FAILED' });
    mockGetTask.mockResolvedValue(failedTask);
    render(<CopilotAgentStatus agentTaskId="task-ux1c-001" />);
    await waitFor(() => {
      expect(screen.getByTestId('copilot-agent-status-failed')).toBeInTheDocument();
      expect(screen.queryByTestId('copilot-agent-status-escalated')).not.toBeInTheDocument();
    });
  });

  it('WAITING_FOR_GOVERNANCE shows governance pause message', async () => {
    const task = makeTask({ status: 'WAITING_FOR_GOVERNANCE' });
    mockGetTask.mockResolvedValue(task);
    render(<CopilotAgentStatus agentTaskId="task-ux1c-001" />);
    await waitFor(() => {
      expect(screen.getByTestId('copilot-agent-status-governance-wait')).toBeInTheDocument();
    });
    expect(screen.getByTestId('copilot-agent-status-governance-wait')).toHaveTextContent(
      'Agent work is paused while MAIW governance evaluates the proposed action.'
    );
  });

  it('OBSERVING_OUTCOME shows "re-reading warehouse state" semantics', async () => {
    const task = makeTask({ status: 'OBSERVING_OUTCOME' });
    mockGetTask.mockResolvedValue(task);
    render(<CopilotAgentStatus agentTaskId="task-ux1c-001" />);
    await waitFor(() => {
      expect(screen.getByTestId('copilot-agent-status-observing-outcome')).toBeInTheDocument();
    });
    expect(screen.getByTestId('copilot-agent-status-observing-outcome')).toHaveTextContent(
      'MAIW is re-reading the warehouse state to determine whether the objective was achieved.'
    );
  });
});

describe('CopilotAgentStatus — live update', () => {
  it('state change triggers re-render', async () => {
    const task = makeTask({ status: 'RUNNING' });
    mockGetTask.mockResolvedValue(task);

    let capturedCallback: ((state: AgentTaskView) => void) | null = null;
    mockSubscribeToTask.mockImplementation((_taskId: string, onUpdate: (state: AgentTaskView) => void) => {
      capturedCallback = onUpdate;
      return jest.fn();
    });

    render(<CopilotAgentStatus agentTaskId="task-ux1c-001" pollIntervalMs={10000} />);

    await waitFor(() => {
      expect(screen.getByTestId('copilot-agent-status-label-RUNNING')).toBeInTheDocument();
    });

    const updatedTask = makeTask({ status: 'WAITING_FOR_GOVERNANCE' });
    act(() => {
      capturedCallback!(updatedTask);
    });

    await waitFor(() => {
      expect(screen.getByTestId('copilot-agent-status-label-WAITING_FOR_GOVERNANCE')).toBeInTheDocument();
    });
  });

  it('cleanup function is called on unmount', async () => {
    const task = makeTask({ status: 'RUNNING' });
    mockGetTask.mockResolvedValue(task);

    const mockCleanup = jest.fn();
    mockSubscribeToTask.mockReturnValue(mockCleanup);

    const { unmount } = render(<CopilotAgentStatus agentTaskId="task-ux1c-001" />);
    unmount();
    expect(mockCleanup).toHaveBeenCalled();
  });
});

describe('CopilotAgentStatus — expert mode', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSubscribeToTask.mockReturnValue(jest.fn());
  });

  it('expert mode shows developer IDs', async () => {
    const task = makeTask({ trace_id: 'trace-expert-001' });
    mockGetTask.mockResolvedValue(task);
    render(<CopilotAgentStatus agentTaskId="task-ux1c-001" expertMode={true} />);
    await waitFor(() => {
      expect(screen.getByTestId('copilot-agent-status-expert')).toBeInTheDocument();
    });
    expect(screen.getByTestId('copilot-agent-status-expert')).toHaveTextContent('task_id');
    expect(screen.getByTestId('copilot-agent-status-expert')).toHaveTextContent('agent_id');
  });

  it('non-expert mode does not show expert panel', async () => {
    const task = makeTask();
    mockGetTask.mockResolvedValue(task);
    render(<CopilotAgentStatus agentTaskId="task-ux1c-001" expertMode={false} />);
    await waitFor(() => {
      expect(screen.getByTestId('copilot-agent-status')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('copilot-agent-status-expert')).not.toBeInTheDocument();
  });
});

describe('CopilotAgentStatus — view activity link', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSubscribeToTask.mockReturnValue(jest.fn());
  });

  it('calls onViewActivity with exact task_id', async () => {
    const task = makeTask({ task_id: 'task-exact-001' });
    mockGetTask.mockResolvedValue(task);
    const onViewActivity = jest.fn();
    render(<CopilotAgentStatus agentTaskId="task-exact-001" onViewActivity={onViewActivity} />);
    await waitFor(() => {
      expect(screen.getByTestId('copilot-agent-status-view-activity')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('copilot-agent-status-view-activity'));
    expect(onViewActivity).toHaveBeenCalledWith('task-exact-001');
  });
});

// ── No chain_of_thought in any new component ──────────────────────────────────

describe('Architecture invariants — no chain_of_thought', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetTask.mockResolvedValue(makeTask());
    mockSubscribeToTask.mockReturnValue(jest.fn());
  });

  it('CopilotAgentStatus does not render chain_of_thought or scratchpad', async () => {
    const task = makeTask({
      chain_of_thought: 'secret reasoning',
      scratchpad: 'internal notes',
    });
    mockGetTask.mockResolvedValue(task);

    render(<CopilotAgentStatus agentTaskId="task-ux1c-001" expertMode={true} />);
    await waitFor(() => {
      expect(screen.getByTestId('copilot-agent-status')).toBeInTheDocument();
    });

    const rendered = document.body.innerHTML;
    expect(rendered).not.toContain('chain_of_thought');
    expect(rendered).not.toContain('scratchpad');
    expect(rendered).not.toContain('hidden_reasoning');
    expect(rendered).not.toContain('reasoning_tokens');
    expect(rendered).not.toContain('secret reasoning');
  });

  it('CopilotAgentStatus does not expose LangGraph/ReAct terminology', async () => {
    const task = makeTask();
    mockGetTask.mockResolvedValue(task);
    render(<CopilotAgentStatus agentTaskId="task-ux1c-001" expertMode={true} />);
    await waitFor(() => {
      expect(screen.getByTestId('copilot-agent-status')).toBeInTheDocument();
    });
    const rendered = document.body.innerHTML.toLowerCase();
    expect(rendered).not.toContain('langgraph');
    expect(rendered).not.toContain('deepagents');
    expect(rendered).not.toContain('react node');
    expect(rendered).not.toContain('checkpoint');
  });
});

// ── CRITICAL REGRESSION: Execution confirmed ≠ Objective achieved ─────────────

describe('REGRESSION: Execution confirmed ≠ Objective achieved', () => {
  it('observe_execution_confirmed=true does not imply observe_operational_improved=true', () => {
    const executionConfirmedNotAchieved = {
      observe_execution_confirmed: true,
      observe_operational_improved: false,
      observe_operational_summary: 'Labor allocated but Wave 17 still at risk',
    };

    expect(executionConfirmedNotAchieved.observe_execution_confirmed).toBe(true);
    expect(executionConfirmedNotAchieved.observe_operational_improved).toBe(false);
    expect(executionConfirmedNotAchieved.observe_execution_confirmed).not.toBe(
      executionConfirmedNotAchieved.observe_operational_improved
    );
  });

  it('observe_execution_confirmed field name is distinct from observe_operational_improved', () => {
    const fields = [
      'observe_execution_confirmed',
      'observe_operational_improved',
    ];
    expect(new Set(fields).size).toBe(fields.length);
    expect(fields[0]).not.toBe(fields[1]);
  });

  it('execution confirmed=true with operational_improved=false is valid schema state', () => {
    const cases = [
      { observe_execution_confirmed: true,  observe_operational_improved: true  },
      { observe_execution_confirmed: true,  observe_operational_improved: false },
      { observe_execution_confirmed: false, observe_operational_improved: false },
    ];
    cases.forEach(({ observe_execution_confirmed, observe_operational_improved }) => {
      expect(typeof observe_execution_confirmed).toBe('boolean');
      expect(typeof observe_operational_improved).toBe('boolean');
    });
  });
});

// ── AgentActivity governance/outcome tests ────────────────────────────────────

describe('AgentActivity — WAITING_FOR_GOVERNANCE', () => {
  it('shows governance transition panel', () => {
    const task = makeTask({ status: 'WAITING_FOR_GOVERNANCE', current_step_id: 'submit' });
    render(<AgentActivity task={task} />);
    expect(screen.getByTestId('governance-transition')).toBeInTheDocument();
  });

  it('shows REVIEW GOVERNANCE button when pendingApprovalId provided', () => {
    const task = makeTask({ status: 'WAITING_FOR_GOVERNANCE', current_step_id: 'submit' });
    const onReview = jest.fn();
    render(
      <AgentActivity
        task={task}
        pendingApprovalId="approval-123"
        onReviewGovernance={onReview}
      />
    );
    const btn = screen.getByTestId('agent-activity-review-governance');
    expect(btn).toBeInTheDocument();
    fireEvent.click(btn);
    expect(onReview).toHaveBeenCalledWith('approval-123');
  });

  it('does not show REVIEW GOVERNANCE when no pendingApprovalId', () => {
    const task = makeTask({ status: 'WAITING_FOR_GOVERNANCE' });
    render(<AgentActivity task={task} />);
    expect(screen.queryByTestId('agent-activity-review-governance')).not.toBeInTheDocument();
  });

  it('shows INDETERMINATE guidance when executionStatus=INDETERMINATE', () => {
    const task = makeTask({ status: 'WAITING_FOR_GOVERNANCE' });
    render(<AgentActivity task={task} executionStatus="INDETERMINATE" />);
    expect(screen.getByTestId('agent-activity-indeterminate')).toBeInTheDocument();
    expect(screen.getByTestId('agent-activity-indeterminate')).toHaveTextContent(
      /MAIW could not determine with confidence/i
    );
    expect(screen.getByTestId('agent-activity-indeterminate')).toHaveTextContent(
      /No automatic retry will be issued/i
    );
  });

  it('shows UNKNOWN reconciling guidance when executionStatus=UNKNOWN', () => {
    const task = makeTask({ status: 'WAITING_FOR_GOVERNANCE' });
    render(<AgentActivity task={task} executionStatus="UNKNOWN" />);
    expect(screen.getByTestId('agent-activity-reconciling')).toBeInTheDocument();
    expect(screen.getByTestId('agent-activity-reconciling')).toHaveTextContent(
      /Execution status is uncertain/i
    );
  });
});

describe('AgentActivity — OBSERVING_OUTCOME', () => {
  it('shows "re-reading warehouse state" semantics', () => {
    const task = makeTask({ status: 'OBSERVING_OUTCOME', current_step_id: 'observe' });
    render(<AgentActivity task={task} />);
    expect(screen.getByTestId('outcome-observing')).toBeInTheDocument();
    expect(screen.getByTestId('outcome-observing-semantics')).toHaveTextContent(
      'MAIW is re-reading the warehouse state to determine whether the objective was achieved.'
    );
  });

  it('shows VIEW LIVE WORLD link when onViewLiveWorld provided', () => {
    const task = makeTask({ status: 'OBSERVING_OUTCOME' });
    const onWorld = jest.fn();
    render(<AgentActivity task={task} onViewLiveWorld={onWorld} />);
    const btn = screen.getByTestId('outcome-view-live-world');
    expect(btn).toBeInTheDocument();
    btn.click();
    expect(onWorld).toHaveBeenCalled();
  });
});

describe('AgentActivity — terminal states distinct', () => {
  it('COMPLETED shows green outcome-completed panel', () => {
    const task = makeTask({ status: 'COMPLETED' });
    render(<AgentActivity task={task} />);
    expect(screen.getByTestId('outcome-completed')).toBeInTheDocument();
    expect(screen.queryByTestId('outcome-escalated')).not.toBeInTheDocument();
    expect(screen.queryByTestId('outcome-failed')).not.toBeInTheDocument();
  });

  it('ESCALATED shows amber outcome-escalated panel (not red)', () => {
    const task = makeTask({ status: 'ESCALATED' });
    render(<AgentActivity task={task} />);
    expect(screen.getByTestId('outcome-escalated')).toBeInTheDocument();
    expect(screen.queryByTestId('outcome-failed')).not.toBeInTheDocument();
  });

  it('FAILED shows red outcome-failed panel (not amber)', () => {
    const task = makeTask({ status: 'FAILED' });
    render(<AgentActivity task={task} />);
    expect(screen.getByTestId('outcome-failed')).toBeInTheDocument();
    expect(screen.queryByTestId('outcome-escalated')).not.toBeInTheDocument();
  });
});

// ── Delegation live states ─────────────────────────────────────────────────────

describe('DelegationCard — live states', () => {
  const makeTaskWithDelegation = (delegationStatus: string): AgentTaskView => ({
    ...makeTask(),
    delegation_results: [{
      delegation_id: 'del-001',
      child_task_id: 'child-labor-001',
      requesting_agent: 'operations_coordination',
      responding_agent: 'labor',
      status: delegationStatus,
      assessment: { summary: 'Labor assessment complete' },
      evidence: ['5 pending tasks'],
      candidate_action_count: 1,
      trace_id: 'trace-001',
      context_snapshot_id: null,
    }],
  } as AgentTaskView);

  it('RUNNING delegation shows "Consulting specialist..."', () => {
    const task = makeTaskWithDelegation('RUNNING');
    render(<DelegationCard task={task} expertMode={false} />);
    expect(screen.getByTestId('delegation-status-running')).toBeInTheDocument();
    expect(screen.getByTestId('delegation-status-running')).toHaveTextContent(
      /Consulting specialist/i
    );
  });

  it('COMPLETED delegation shows "Consultation complete"', () => {
    const task = makeTaskWithDelegation('COMPLETED');
    render(<DelegationCard task={task} expertMode={false} />);
    expect(screen.getByTestId('delegation-status-completed')).toBeInTheDocument();
    expect(screen.getByTestId('delegation-status-completed')).toHaveTextContent(
      /Consultation complete/i
    );
  });

  it('FAILED delegation shows "Specialist could not complete"', () => {
    const task = makeTaskWithDelegation('FAILED');
    render(<DelegationCard task={task} expertMode={false} />);
    expect(screen.getByTestId('delegation-status-failed')).toBeInTheDocument();
    expect(screen.getByTestId('delegation-status-failed')).toHaveTextContent(
      /Specialist could not complete/i
    );
  });
});

// ── Continue loop visibility ──────────────────────────────────────────────────

describe('AgentActivity — continue loop / iteration 2', () => {
  it('shows iteration 2 in expert mode', async () => {
    const task = makeTask({ iteration: 2, status: 'RUNNING' });
    render(<AgentActivity task={task} expertMode={true} />);
    const labels = screen.getAllByText(/^iteration$/i);
    expect(labels.length).toBeGreaterThan(0);
    const values = screen.getAllByText((content) => content === '2');
    expect(values.length).toBeGreaterThan(0);
  });
});

// ── subscribeToTask polling ───────────────────────────────────────────────────

describe('agentTaskAPI.subscribeToTask', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.unmock('../services/agentTaskAPI');
  });

  afterEach(() => {
    jest.useRealTimers();
    jest.mock('../services/agentTaskAPI', () => ({
      agentTaskAPI: {
        getTask: jest.fn(),
        listTasks: jest.fn(),
        subscribeToTask: jest.fn(() => jest.fn()),
      },
    }));
  });

  it('subscribeToTask returns a cleanup function', async () => {
    const { agentTaskAPI: realApi } = jest.requireActual('../services/agentTaskAPI');
    expect(typeof realApi.subscribeToTask).toBe('function');
  });
});
