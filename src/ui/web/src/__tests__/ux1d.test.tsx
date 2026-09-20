/**
 * UX-1D Outcome, Reliability & Decision Trace Consolidation Tests
 *
 * Critical invariants (BLOCKING):
 * 1. EXECUTED != OBJECTIVE_ACHIEVED — execution confirmed does not imply objective achieved
 * 2. FAILED != ESCALATED — distinct test IDs and labels
 * 3. UNKNOWN != NOT_ACHIEVED — distinct operator text and styling
 * 4. CONFIRMED_EXECUTED != COMPLETED — separate fields
 * 5. UNKNOWN uses warning/amber styling, not red (not hard failure)
 * 6. INDETERMINATE provides operator guidance, no auto-retry implied
 * 7. Outcome section green only when OBJECTIVE_ACHIEVED
 * 8. OutcomeSummary: no green styling when execution confirmed but objective not achieved
 * 9. INDETERMINATE blocks outcome claim
 * 10. DecisionGraph has VIEW DEVELOPER TRACE cross-link
 * 11. DeveloperTrace has VIEW DECISION GRAPH cross-link
 * 12. Both have VIEW CONTEXT AT DECISION TIME and VIEW LIVE WORLD links
 * 13. Expert mode shows execution_id not visible in operator mode
 * 14. No chain_of_thought in any surface
 * 15. ReliabilityPanel: UNKNOWN → "Execution confirmation unavailable" (not "Failed")
 * 16. ReliabilityPanel: RECONCILING → "Verifying execution" + "No operator action required"
 * 17. ReliabilityPanel: INDETERMINATE → "Operator review required"
 * 18. ReliabilityPanel: CONFIRMED_NOT_EXECUTED → "Confirmed not executed"
 * 19. StateDelta hides unchanged fields, shows changed with before/after
 * 20. KPIDelta shows before/after and delta
 * 21. UNKNOWN task stays paused semantically (agent COMPLETED != execution CONFIRMED)
 */

import React from 'react';
import { render, screen, within, fireEvent } from '@testing-library/react';
import {
  EXECUTION_STATE_LABEL,
  EXECUTION_STATE_SEVERITY,
  RELIABILITY_STATE_LABEL,
  RELIABILITY_NEXT_ACTION,
  RELIABILITY_OPERATOR_ACTION_REQUIRED,
  RELIABILITY_STATE_SEVERITY,
  OUTCOME_STATE_LABEL,
  OUTCOME_STATE_SEVERITY,
  AGENT_TASK_TO_EXECUTION_RELATION,
  CANONICAL_SEMANTIC_MATRIX,
} from '../constants/postExecutionStates';
import ExecutionReliabilityPanel, { ReliabilityState } from '../components/outcome/ExecutionReliabilityPanel';
import OutcomeSummary from '../components/outcome/OutcomeSummary';
import StateDelta from '../components/outcome/StateDelta';
import KPIDelta from '../components/outcome/KPIDelta';
import DecisionGraph from '../components/demo/decision-graph/DecisionGraph';
import DeveloperTraceView from '../components/demo/developer-trace/DeveloperTraceView';

// ── Fixtures ──────────────────────────────────────────────────────────────────

import { DecisionGraph as DecisionGraphData } from '../components/demo/decision-graph/graphTypes';
import { DeveloperTrace } from '../components/demo/developer-trace/developerTraceTypes';

const MINIMAL_GRAPH: DecisionGraphData = {
  nodes: [
    { id: 'n1', type: 'evidence',        label: 'Evidence',       layer: 0, column: 0, source: 'LIVE' },
    { id: 'n2', type: 'recommendation',  label: 'Recommendation', layer: 2, column: 0, source: 'DERIVED' },
  ],
  edges: [{ id: 'e1', source: 'n1', target: 'n2', relationship: 'SUPPORTS' as const }],
};

const MINIMAL_TRACE: DeveloperTrace = {
  traceId: 'trace-0001-0002-0003-0004',
  scenarioName: 'Wave Risk F06',
  warehouseId: 'WH-001',
  status: 'COMPLETE',
  events: [],
  artifacts: { proposalIds: [], decisionIds: [], approvalIds: [], executionIds: [] },
  timings: [],
  scenarioRunIdNote: '',
};

// ── A. Semantic constants — never conflate ────────────────────────────────────

describe('UX-1D.1 — Post-execution semantic layers', () => {
  describe('Execution state vocabulary', () => {
    it('executed maps to "Execution confirmed" (not "Objective achieved")', () => {
      expect(EXECUTION_STATE_LABEL.executed).toBe('Execution confirmed');
      expect(EXECUTION_STATE_LABEL.executed).not.toContain('Objective');
    });

    it('unknown maps to "Execution confirmation unavailable" (not "Failed")', () => {
      expect(EXECUTION_STATE_LABEL.unknown).toBe('Execution confirmation unavailable');
      expect(EXECUTION_STATE_LABEL.unknown).not.toContain('failed');
      expect(EXECUTION_STATE_LABEL.unknown).not.toContain('Failed');
    });

    it('failed maps to "Execution failed"', () => {
      expect(EXECUTION_STATE_LABEL.failed).toBe('Execution failed');
    });

    it('unknown has warning severity (not error)', () => {
      expect(EXECUTION_STATE_SEVERITY.unknown).toBe('warning');
      expect(EXECUTION_STATE_SEVERITY.unknown).not.toBe('error');
    });

    it('failed has error severity', () => {
      expect(EXECUTION_STATE_SEVERITY.failed).toBe('error');
    });

    it('executed and failed are distinct', () => {
      expect(EXECUTION_STATE_LABEL.executed).not.toBe(EXECUTION_STATE_LABEL.failed);
      expect(EXECUTION_STATE_SEVERITY.executed).toBe('success');
      expect(EXECUTION_STATE_SEVERITY.failed).toBe('error');
    });
  });

  describe('Reliability state vocabulary', () => {
    it('UNKNOWN → "Execution confirmation unavailable" (not "Execution failed")', () => {
      expect(RELIABILITY_STATE_LABEL.UNKNOWN).toBe('Execution confirmation unavailable');
      expect(RELIABILITY_STATE_LABEL.UNKNOWN).not.toContain('failed');
    });

    it('RECONCILING → "Verifying execution"', () => {
      expect(RELIABILITY_STATE_LABEL.RECONCILING).toBe('Verifying execution');
    });

    it('CONFIRMED_EXECUTED → "Execution confirmed"', () => {
      expect(RELIABILITY_STATE_LABEL.CONFIRMED_EXECUTED).toBe('Execution confirmed');
    });

    it('CONFIRMED_NOT_EXECUTED → "Confirmed not executed"', () => {
      expect(RELIABILITY_STATE_LABEL.CONFIRMED_NOT_EXECUTED).toBe('Confirmed not executed');
    });

    it('INDETERMINATE → "Operator review required"', () => {
      expect(RELIABILITY_STATE_LABEL.INDETERMINATE).toBe('Operator review required');
    });

    it('UNKNOWN has warning severity (amber, not red)', () => {
      expect(RELIABILITY_STATE_SEVERITY.UNKNOWN).toBe('warning');
      expect(RELIABILITY_STATE_SEVERITY.UNKNOWN).not.toBe('error');
    });

    it('INDETERMINATE has attention severity', () => {
      expect(RELIABILITY_STATE_SEVERITY.INDETERMINATE).toBe('attention');
    });

    it('RECONCILING does not require operator action', () => {
      expect(RELIABILITY_OPERATOR_ACTION_REQUIRED.RECONCILING).toBe(false);
    });

    it('UNKNOWN does not require operator action', () => {
      expect(RELIABILITY_OPERATOR_ACTION_REQUIRED.UNKNOWN).toBe(false);
    });

    it('INDETERMINATE requires operator action', () => {
      expect(RELIABILITY_OPERATOR_ACTION_REQUIRED.INDETERMINATE).toBe(true);
    });

    it('RECONCILING next action: "No operator action required"', () => {
      expect(RELIABILITY_NEXT_ACTION.RECONCILING).toContain('No operator action required');
    });

    it('INDETERMINATE next action: operator review required', () => {
      expect(RELIABILITY_NEXT_ACTION.INDETERMINATE).toContain('Operator review');
    });
  });

  describe('Outcome state vocabulary', () => {
    it('OBJECTIVE_ACHIEVED has success severity (green)', () => {
      expect(OUTCOME_STATE_SEVERITY.OBJECTIVE_ACHIEVED).toBe('success');
    });

    it('PARTIALLY_ACHIEVED has warning severity (amber, not green)', () => {
      expect(OUTCOME_STATE_SEVERITY.PARTIALLY_ACHIEVED).toBe('warning');
      expect(OUTCOME_STATE_SEVERITY.PARTIALLY_ACHIEVED).not.toBe('success');
    });

    it('NOT_ACHIEVED has attention severity (not success)', () => {
      expect(OUTCOME_STATE_SEVERITY.NOT_ACHIEVED).toBe('attention');
      expect(OUTCOME_STATE_SEVERITY.NOT_ACHIEVED).not.toBe('success');
    });
  });

  describe('Canonical semantic matrix', () => {
    it('has 5 operator questions mapped', () => {
      expect(CANONICAL_SEMANTIC_MATRIX).toHaveLength(5);
    });

    it('maps "Did it execute?" to ExecutionRecord', () => {
      const row = CANONICAL_SEMANTIC_MATRIX.find(r => r.question === 'Did it execute?');
      expect(row).toBeDefined();
      expect(row?.sourceOfTruth).toContain('ExecutionRecord');
    });

    it('maps "Did it help?" to LIVE world state / OBSERVE_OUTCOME', () => {
      const row = CANONICAL_SEMANTIC_MATRIX.find(r => r.question === 'Did it help?');
      expect(row).toBeDefined();
      expect(row?.sourceOfTruth).toContain('OBSERVE_OUTCOME');
    });
  });

  describe('Agent task vs execution relation', () => {
    it('COMPLETED ≠ CONFIRMED_EXECUTED — documented relation', () => {
      const relation = AGENT_TASK_TO_EXECUTION_RELATION.COMPLETED;
      expect(relation).toContain('check execution');
    });

    it('FAILED agent task is separate from execution failure', () => {
      const relation = AGENT_TASK_TO_EXECUTION_RELATION.FAILED;
      expect(relation).toContain('separate from execution');
    });

    it('ESCALATED is separate from INDETERMINATE reliability', () => {
      const relation = AGENT_TASK_TO_EXECUTION_RELATION.ESCALATED;
      expect(relation).toContain('INDETERMINATE');
    });
  });
});

// ── B. ExecutionReliabilityPanel ──────────────────────────────────────────────

describe('UX-1D.2 — ExecutionReliabilityPanel', () => {
  const reliabilityStates: ReliabilityState[] = [
    'CONFIRMED_EXECUTED',
    'CONFIRMED_NOT_EXECUTED',
    'INDETERMINATE',
    'RECONCILING',
    'UNKNOWN',
  ];

  reliabilityStates.forEach((state) => {
    it(`renders without crash for state ${state}`, () => {
      render(<ExecutionReliabilityPanel reliabilityState={state} />);
      expect(screen.getByTestId('execution-reliability-panel')).toBeInTheDocument();
    });
  });

  it('UNKNOWN: shows "Execution confirmation unavailable" (not "Execution failed")', () => {
    render(<ExecutionReliabilityPanel reliabilityState="UNKNOWN" />);
    expect(screen.getByTestId('reliability-chip-UNKNOWN')).toHaveTextContent('Execution confirmation unavailable');
    // Must NOT contain "failed" or "Failed"
    const panel = screen.getByTestId('execution-reliability-panel');
    expect(panel).not.toHaveTextContent('Execution failed');
  });

  it('RECONCILING: shows "Verifying execution" + no operator action required', () => {
    render(<ExecutionReliabilityPanel reliabilityState="RECONCILING" />);
    expect(screen.getByTestId('reliability-chip-RECONCILING')).toHaveTextContent('Verifying execution');
    expect(screen.getByTestId('reliability-next-action')).toHaveTextContent('No operator action required');
    expect(screen.queryByTestId('operator-action-required-badge')).not.toBeInTheDocument();
  });

  it('CONFIRMED_EXECUTED: shows "Execution confirmed"', () => {
    render(<ExecutionReliabilityPanel reliabilityState="CONFIRMED_EXECUTED" />);
    expect(screen.getByTestId('reliability-chip-CONFIRMED_EXECUTED')).toHaveTextContent('Execution confirmed');
  });

  it('CONFIRMED_NOT_EXECUTED: shows "Confirmed not executed"', () => {
    render(<ExecutionReliabilityPanel reliabilityState="CONFIRMED_NOT_EXECUTED" />);
    expect(screen.getByTestId('reliability-chip-CONFIRMED_NOT_EXECUTED')).toHaveTextContent('Confirmed not executed');
  });

  it('INDETERMINATE: shows "Operator review required" + operator action badge', () => {
    render(<ExecutionReliabilityPanel reliabilityState="INDETERMINATE" />);
    expect(screen.getByTestId('reliability-chip-INDETERMINATE')).toHaveTextContent('Operator review required');
    expect(screen.getByTestId('operator-action-required-badge')).toBeInTheDocument();
  });

  it('INDETERMINATE: next action says review required (not retry)', () => {
    render(<ExecutionReliabilityPanel reliabilityState="INDETERMINATE" />);
    const nextAction = screen.getByTestId('reliability-next-action');
    expect(nextAction).toHaveTextContent('Operator review');
    expect(nextAction).not.toHaveTextContent('retry');
    expect(nextAction).not.toHaveTextContent('Retry');
  });

  describe('Expert mode', () => {
    it('execution_id visible only in expert mode', () => {
      const { rerender } = render(
        <ExecutionReliabilityPanel
          reliabilityState="CONFIRMED_EXECUTED"
          expertMode={false}
          executionId="exec-00000001"
        />
      );
      // Operator mode: execution_id not shown
      expect(screen.queryByTestId('reliability-execution-id')).not.toBeInTheDocument();

      rerender(
        <ExecutionReliabilityPanel
          reliabilityState="CONFIRMED_EXECUTED"
          expertMode={true}
          executionId="exec-00000001"
        />
      );
      // Expert mode: execution_id shown
      expect(screen.getByTestId('reliability-execution-id')).toHaveTextContent('exec-00000001');
    });

    it('expert details panel shown only in expert mode', () => {
      const { rerender } = render(
        <ExecutionReliabilityPanel reliabilityState="UNKNOWN" expertMode={false} />
      );
      expect(screen.queryByTestId('reliability-expert-details')).not.toBeInTheDocument();

      rerender(<ExecutionReliabilityPanel reliabilityState="UNKNOWN" expertMode={true} />);
      expect(screen.getByTestId('reliability-expert-details')).toBeInTheDocument();
    });

    it('UNKNOWN expert mode: no auto-retry note shown', () => {
      render(<ExecutionReliabilityPanel reliabilityState="UNKNOWN" expertMode={true} />);
      const expert = screen.getByTestId('reliability-expert-details');
      expect(expert).toHaveTextContent('No automatic retry');
    });
  });

  it('VIEW DEVELOPER TRACE link calls onViewTrace', () => {
    const mockFn = jest.fn();
    render(<ExecutionReliabilityPanel reliabilityState="CONFIRMED_EXECUTED" onViewTrace={mockFn} />);
    fireEvent.click(screen.getByTestId('view-reliability-link'));
    expect(mockFn).toHaveBeenCalledTimes(1);
  });
});

// ── C. OutcomeSummary ─────────────────────────────────────────────────────────

describe('UX-1D.3 — OutcomeSummary', () => {
  const BASE_PROPS = {
    executionState: 'executed' as const,
    reliabilityState: 'CONFIRMED_EXECUTED' as const,
    outcomeState: 'OBJECTIVE_ACHIEVED' as const,
    agentTaskStatus: 'COMPLETED',
  };

  it('renders all four sections', () => {
    render(<OutcomeSummary {...BASE_PROPS} />);
    expect(screen.getByTestId('outcome-summary')).toBeInTheDocument();
    expect(screen.getByTestId('outcome-execution-section')).toBeInTheDocument();
    expect(screen.getByTestId('outcome-reliability-section')).toBeInTheDocument();
    expect(screen.getByTestId('outcome-operational-section')).toBeInTheDocument();
    expect(screen.getByTestId('outcome-agent-status-section')).toBeInTheDocument();
  });

  it('OBJECTIVE_ACHIEVED: outcome section present with "Objective achieved"', () => {
    render(<OutcomeSummary {...BASE_PROPS} />);
    const outcomeSection = screen.getByTestId('outcome-operational-section');
    expect(outcomeSection).toHaveTextContent('Objective achieved');
  });

  it('CRITICAL: execution confirmed + objective NOT achieved → does NOT show green outcome claim', () => {
    render(
      <OutcomeSummary
        {...BASE_PROPS}
        outcomeState="NOT_ACHIEVED"
      />
    );
    // Outcome section exists but says NOT_ACHIEVED
    expect(screen.getByTestId('outcome-operational-value')).toHaveTextContent('Objective not achieved');
    // Must NOT claim objective achieved
    expect(screen.getByTestId('outcome-operational-value')).not.toHaveTextContent('Objective achieved');
  });

  it('PARTIALLY_ACHIEVED: outcome shows amber not green label', () => {
    render(
      <OutcomeSummary
        {...BASE_PROPS}
        outcomeState="PARTIALLY_ACHIEVED"
      />
    );
    expect(screen.getByTestId('outcome-operational-value')).toHaveTextContent('Partially achieved');
    expect(screen.getByTestId('outcome-operational-value')).not.toHaveTextContent('Objective achieved');
  });

  it('UNKNOWN execution: shows pending banner (no outcome claim)', () => {
    render(
      <OutcomeSummary
        executionState="unknown"
        reliabilityState="UNKNOWN"
        outcomeState="PENDING"
        agentTaskStatus="OBSERVING_OUTCOME"
      />
    );
    expect(screen.getByTestId('outcome-pending-banner')).toBeInTheDocument();
    // No positive outcome claim
    expect(screen.queryByTestId('outcome-summary-section')).not.toBeInTheDocument();
  });

  it('RECONCILING: shows pending banner, no outcome summary', () => {
    render(
      <OutcomeSummary
        executionState="unknown"
        reliabilityState="RECONCILING"
        outcomeState="PENDING"
        agentTaskStatus="OBSERVING_OUTCOME"
      />
    );
    expect(screen.getByTestId('outcome-pending-banner')).toBeInTheDocument();
    expect(screen.queryByTestId('outcome-summary-section')).not.toBeInTheDocument();
  });

  it('INDETERMINATE: guidance shown, no outcome claim', () => {
    render(
      <OutcomeSummary
        executionState="unknown"
        reliabilityState="INDETERMINATE"
        outcomeState="INCONCLUSIVE"
        agentTaskStatus="ESCALATED"
      />
    );
    const banner = screen.getByTestId('outcome-pending-banner');
    expect(banner).toHaveTextContent('Operator review required');
    expect(screen.queryByTestId('outcome-summary-section')).not.toBeInTheDocument();
  });

  it('FAILED: shows "Execution failed", no outcome claim', () => {
    render(
      <OutcomeSummary
        executionState="failed"
        reliabilityState="CONFIRMED_NOT_EXECUTED"
        outcomeState="INCONCLUSIVE"
        agentTaskStatus="FAILED"
      />
    );
    expect(screen.getByTestId('outcome-execution-value')).toHaveTextContent('Execution failed');
    expect(screen.queryByTestId('outcome-summary-section')).not.toBeInTheDocument();
  });

  it('OBJECTIVE_ACHIEVED: shows deterministic summary text', () => {
    render(
      <OutcomeSummary
        {...BASE_PROPS}
        summary="Wave 17 risk decreased after the approved labor reallocation."
      />
    );
    expect(screen.getByTestId('outcome-summary-text')).toHaveTextContent('Wave 17 risk decreased');
  });

  it('Missing summary: shows fallback text (not empty)', () => {
    render(<OutcomeSummary {...BASE_PROPS} />);
    const summaryText = screen.getByTestId('outcome-summary-text');
    expect(summaryText.textContent?.length).toBeGreaterThan(10);
  });

  it('Agent status shown as COMPLETED → "Completed"', () => {
    render(<OutcomeSummary {...BASE_PROPS} />);
    expect(screen.getByTestId('outcome-agent-status-value')).toHaveTextContent('Completed');
  });

  it('Agent COMPLETED ≠ Execution CONFIRMED_EXECUTED — rendered in separate sections', () => {
    render(<OutcomeSummary {...BASE_PROPS} />);
    const execSection  = screen.getByTestId('outcome-execution-section');
    const agentSection = screen.getByTestId('outcome-agent-status-section');
    // Confirm these are separate DOM elements
    expect(execSection).not.toBe(agentSection);
    // Execution section shows execution state
    expect(execSection).toHaveTextContent('Execution confirmed');
    // Agent section shows agent state
    expect(agentSection).toHaveTextContent('Completed');
  });

  describe('VIEW RELIABILITY link', () => {
    it('calls onViewReliability when clicked', () => {
      const mockFn = jest.fn();
      render(<OutcomeSummary {...BASE_PROPS} onViewReliability={mockFn} />);
      fireEvent.click(screen.getByTestId('view-reliability-link'));
      expect(mockFn).toHaveBeenCalledTimes(1);
    });
  });

  describe('Entity deltas', () => {
    it('shows entity deltas when execution resolved', () => {
      render(
        <OutcomeSummary
          {...BASE_PROPS}
          entityDeltas={[{
            entityId: 'TASK-000001',
            entityType: 'Task',
            deltas: [
              { label: 'Status', before: 'PENDING', after: 'IN_PROGRESS' },
              { label: 'Assigned worker', before: null, after: 'WORKER-000005' },
            ],
          }]}
        />
      );
      expect(screen.getByTestId('outcome-entity-deltas')).toBeInTheDocument();
      expect(screen.getByTestId('state-delta-TASK-000001')).toBeInTheDocument();
    });

    it('does NOT show entity deltas when execution UNKNOWN', () => {
      render(
        <OutcomeSummary
          executionState="unknown"
          reliabilityState="UNKNOWN"
          outcomeState="PENDING"
          agentTaskStatus="OBSERVING_OUTCOME"
          entityDeltas={[{
            entityId: 'TASK-000001',
            entityType: 'Task',
            deltas: [{ label: 'Status', before: 'PENDING', after: 'IN_PROGRESS' }],
          }]}
        />
      );
      expect(screen.queryByTestId('outcome-entity-deltas')).not.toBeInTheDocument();
    });
  });

  describe('KPI deltas', () => {
    it('shows KPI deltas when execution resolved', () => {
      render(
        <OutcomeSummary
          {...BASE_PROPS}
          kpiDeltas={[{ label: 'Labor utilization', before: 42.1, after: 42.9, unit: '%' }]}
        />
      );
      expect(screen.getByTestId('outcome-kpi-deltas')).toBeInTheDocument();
    });

    it('does NOT show KPI deltas when execution RECONCILING', () => {
      render(
        <OutcomeSummary
          executionState="unknown"
          reliabilityState="RECONCILING"
          outcomeState="PENDING"
          agentTaskStatus="OBSERVING_OUTCOME"
          kpiDeltas={[{ label: 'Labor utilization', before: 42.1, after: 42.9, unit: '%' }]}
        />
      );
      expect(screen.queryByTestId('outcome-kpi-deltas')).not.toBeInTheDocument();
    });
  });
});

// ── D. StateDelta ─────────────────────────────────────────────────────────────

describe('UX-1D.3 — StateDelta', () => {
  it('shows before and after for changed fields', () => {
    render(
      <StateDelta
        entityId="TASK-000001"
        entityType="Task"
        deltas={[
          { label: 'Status', before: 'PENDING', after: 'IN_PROGRESS' },
          { label: 'Assigned worker', before: null, after: 'WORKER-000005' },
        ]}
      />
    );
    expect(screen.getByTestId('state-delta-TASK-000001')).toBeInTheDocument();
    const statusRow = screen.getByTestId('state-delta-row-status');
    expect(statusRow).toBeInTheDocument();
    // Check before/after values exist
    const befores = within(statusRow).getAllByTestId('delta-before');
    const afters = within(statusRow).getAllByTestId('delta-after');
    expect(befores[0]).toHaveTextContent('PENDING');
    expect(afters[0]).toHaveTextContent('IN_PROGRESS');
  });

  it('renders null when no deltas', () => {
    const { container } = render(
      <StateDelta entityId="TASK-000001" deltas={[]} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('entity ID and type are displayed', () => {
    render(
      <StateDelta
        entityId="WORKER-000005"
        entityType="Worker"
        deltas={[{ label: 'Status', before: 'IDLE', after: 'ASSIGNED' }]}
      />
    );
    expect(screen.getByTestId('state-delta-WORKER-000005')).toHaveTextContent('WORKER-000005');
    expect(screen.getByTestId('state-delta-WORKER-000005')).toHaveTextContent('Worker');
  });
});

// ── E. KPIDelta ───────────────────────────────────────────────────────────────

describe('UX-1D.3 — KPIDelta', () => {
  it('shows label, before, after and computed delta', () => {
    render(
      <KPIDelta
        label="Labor utilization"
        before={42.1}
        after={42.9}
        unit="%"
        improvementDirection="increase"
      />
    );
    expect(screen.getByTestId('kpi-delta-labor-utilization')).toBeInTheDocument();
    expect(screen.getByTestId('kpi-before')).toHaveTextContent('42.1%');
    expect(screen.getByTestId('kpi-after')).toHaveTextContent('42.9%');
    expect(screen.getByTestId('kpi-delta')).toHaveTextContent('+0.8%');
  });

  it('uses explicit deltaLabel when provided', () => {
    render(
      <KPIDelta
        label="Pending backlog"
        before={119}
        after={118}
        deltaLabel="-1 task"
        improvementDirection="decrease"
      />
    );
    expect(screen.getByTestId('kpi-delta')).toHaveTextContent('-1 task');
  });

  it('renders negative delta for increase direction (bad outcome)', () => {
    render(
      <KPIDelta
        label="Labor utilization"
        before={42.9}
        after={42.1}
        unit="%"
        improvementDirection="increase"
      />
    );
    expect(screen.getByTestId('kpi-delta')).toHaveTextContent('-0.8%');
  });
});

// ── F. DecisionGraph cross-links ──────────────────────────────────────────────

describe('UX-1D.4 — DecisionGraph cross-links', () => {
  it('renders without cross-link props — no cross-link bar shown', () => {
    render(<DecisionGraph graph={MINIMAL_GRAPH} />);
    expect(screen.queryByTestId('decision-graph-view-developer-trace')).not.toBeInTheDocument();
    expect(screen.queryByTestId('decision-graph-view-context')).not.toBeInTheDocument();
    expect(screen.queryByTestId('decision-graph-view-live-world')).not.toBeInTheDocument();
  });

  it('VIEW DEVELOPER TRACE link calls onViewDeveloperTrace', () => {
    const mockFn = jest.fn();
    render(<DecisionGraph graph={MINIMAL_GRAPH} onViewDeveloperTrace={mockFn} />);
    const link = screen.getByTestId('decision-graph-view-developer-trace');
    expect(link).toHaveTextContent('VIEW DEVELOPER TRACE');
    fireEvent.click(link);
    expect(mockFn).toHaveBeenCalledTimes(1);
  });

  it('VIEW CONTEXT AT DECISION TIME link calls onViewContextAtDecision', () => {
    const mockFn = jest.fn();
    render(<DecisionGraph graph={MINIMAL_GRAPH} onViewContextAtDecision={mockFn} />);
    const link = screen.getByTestId('decision-graph-view-context');
    expect(link).toHaveTextContent('VIEW CONTEXT AT DECISION TIME');
    fireEvent.click(link);
    expect(mockFn).toHaveBeenCalledTimes(1);
  });

  it('VIEW LIVE WORLD link calls onViewLiveWorld', () => {
    const mockFn = jest.fn();
    render(<DecisionGraph graph={MINIMAL_GRAPH} onViewLiveWorld={mockFn} />);
    const link = screen.getByTestId('decision-graph-view-live-world');
    expect(link).toHaveTextContent('VIEW LIVE WORLD');
    fireEvent.click(link);
    expect(mockFn).toHaveBeenCalledTimes(1);
  });

  it('all three cross-links rendered when all callbacks provided', () => {
    render(
      <DecisionGraph
        graph={MINIMAL_GRAPH}
        onViewDeveloperTrace={jest.fn()}
        onViewContextAtDecision={jest.fn()}
        onViewLiveWorld={jest.fn()}
      />
    );
    expect(screen.getByTestId('decision-graph-view-developer-trace')).toBeInTheDocument();
    expect(screen.getByTestId('decision-graph-view-context')).toBeInTheDocument();
    expect(screen.getByTestId('decision-graph-view-live-world')).toBeInTheDocument();
  });
});

// ── G. DeveloperTraceView cross-links ─────────────────────────────────────────

describe('UX-1D.4 — DeveloperTraceView cross-links', () => {
  it('renders without cross-link props — no cross-links shown', () => {
    render(<DeveloperTraceView trace={MINIMAL_TRACE} />);
    expect(screen.queryByTestId('dev-trace-view-decision-graph')).not.toBeInTheDocument();
    expect(screen.queryByTestId('dev-trace-view-context')).not.toBeInTheDocument();
    expect(screen.queryByTestId('dev-trace-view-live-world')).not.toBeInTheDocument();
  });

  it('VIEW DECISION GRAPH link calls onViewDecisionGraph', () => {
    const mockFn = jest.fn();
    render(<DeveloperTraceView trace={MINIMAL_TRACE} onViewDecisionGraph={mockFn} />);
    const link = screen.getByTestId('dev-trace-view-decision-graph');
    expect(link).toHaveTextContent('VIEW DECISION GRAPH');
    fireEvent.click(link);
    expect(mockFn).toHaveBeenCalledTimes(1);
  });

  it('VIEW CONTEXT AT DECISION TIME link calls onViewContextAtDecision', () => {
    const mockFn = jest.fn();
    render(<DeveloperTraceView trace={MINIMAL_TRACE} onViewContextAtDecision={mockFn} />);
    const link = screen.getByTestId('dev-trace-view-context');
    expect(link).toHaveTextContent('VIEW CONTEXT AT DECISION TIME');
    fireEvent.click(link);
    expect(mockFn).toHaveBeenCalledTimes(1);
  });

  it('VIEW LIVE WORLD link calls onViewLiveWorld', () => {
    const mockFn = jest.fn();
    render(<DeveloperTraceView trace={MINIMAL_TRACE} onViewLiveWorld={mockFn} />);
    const link = screen.getByTestId('dev-trace-view-live-world');
    expect(link).toHaveTextContent('VIEW LIVE WORLD');
    fireEvent.click(link);
    expect(mockFn).toHaveBeenCalledTimes(1);
  });

  it('all three cross-links shown when all callbacks provided', () => {
    render(
      <DeveloperTraceView
        trace={MINIMAL_TRACE}
        onViewDecisionGraph={jest.fn()}
        onViewContextAtDecision={jest.fn()}
        onViewLiveWorld={jest.fn()}
      />
    );
    expect(screen.getByTestId('dev-trace-view-decision-graph')).toBeInTheDocument();
    expect(screen.getByTestId('dev-trace-view-context')).toBeInTheDocument();
    expect(screen.getByTestId('dev-trace-view-live-world')).toBeInTheDocument();
  });

  it('null trace: shows empty state, no cross-link bar', () => {
    render(
      <DeveloperTraceView
        trace={null}
        onViewDecisionGraph={jest.fn()}
        onViewContextAtDecision={jest.fn()}
        onViewLiveWorld={jest.fn()}
      />
    );
    expect(screen.getByTestId('dev-trace-empty')).toBeInTheDocument();
    // Cross-links not shown on empty state (no trace header to anchor to)
    expect(screen.queryByTestId('dev-trace-view-decision-graph')).not.toBeInTheDocument();
  });
});

// ── H. Trace privacy — no chain-of-thought ────────────────────────────────────

describe('UX-1D.4 — Trace privacy', () => {
  it('DeveloperTraceView: does not render chain_of_thought content', () => {
    render(<DeveloperTraceView trace={MINIMAL_TRACE} />);
    const panel = screen.getByTestId('dev-trace-view');
    expect(panel).not.toHaveTextContent('chain_of_thought');
    expect(panel).not.toHaveTextContent('scratchpad');
    expect(panel).not.toHaveTextContent('hidden_reasoning');
  });
});

// ── I. Semantic separation regression — BLOCKING ──────────────────────────────

describe('UX-1D — Semantic separation regression (BLOCKING)', () => {
  it('EXECUTED != OBJECTIVE_ACHIEVED — execution confirmed renders separately from outcome', () => {
    render(
      <OutcomeSummary
        executionState="executed"
        reliabilityState="CONFIRMED_EXECUTED"
        outcomeState="NOT_ACHIEVED"
        agentTaskStatus="COMPLETED"
      />
    );
    const execValue    = screen.getByTestId('outcome-execution-value');
    const outcomeValue = screen.getByTestId('outcome-operational-value');

    expect(execValue).toHaveTextContent('Execution confirmed');
    expect(outcomeValue).toHaveTextContent('Objective not achieved');
    // They are in different DOM elements
    expect(execValue).not.toBe(outcomeValue);
  });

  it('FAILED != ESCALATED — distinct labels', () => {
    // From constants
    const { AGENT_TASK_STATUS_LABEL } = require('../constants/agentTaskStates');
    expect(AGENT_TASK_STATUS_LABEL.FAILED).not.toBe(AGENT_TASK_STATUS_LABEL.ESCALATED);
    expect(AGENT_TASK_STATUS_LABEL.FAILED).toBe('Could not complete');
    expect(AGENT_TASK_STATUS_LABEL.ESCALATED).toBe('Needs attention');
  });

  it('UNKNOWN != NOT_ACHIEVED — distinct operator text', () => {
    // UNKNOWN is an execution/reliability state; NOT_ACHIEVED is an outcome state
    expect(RELIABILITY_STATE_LABEL.UNKNOWN).toBe('Execution confirmation unavailable');
    expect(OUTCOME_STATE_LABEL.NOT_ACHIEVED).toBe('Objective not achieved');
    expect(RELIABILITY_STATE_LABEL.UNKNOWN).not.toBe(OUTCOME_STATE_LABEL.NOT_ACHIEVED);
  });

  it('CONFIRMED_EXECUTED != COMPLETED — separate data (execution vs agent task)', () => {
    // CONFIRMED_EXECUTED is a reliability state; COMPLETED is an agent task state
    expect(RELIABILITY_STATE_LABEL.CONFIRMED_EXECUTED).toBe('Execution confirmed');
    const { AGENT_TASK_STATUS_LABEL } = require('../constants/agentTaskStates');
    expect(AGENT_TASK_STATUS_LABEL.COMPLETED).toBe('Completed');
    expect(RELIABILITY_STATE_LABEL.CONFIRMED_EXECUTED).not.toBe(AGENT_TASK_STATUS_LABEL.COMPLETED);
  });

  it('Execution section and Agent Status section are always separate DOM elements', () => {
    render(
      <OutcomeSummary
        executionState="executed"
        reliabilityState="CONFIRMED_EXECUTED"
        outcomeState="OBJECTIVE_ACHIEVED"
        agentTaskStatus="COMPLETED"
      />
    );
    const exec  = screen.getByTestId('outcome-execution-section');
    const agent = screen.getByTestId('outcome-agent-status-section');
    // Different DOM elements
    expect(exec).not.toBe(agent);
    // Different content
    expect(exec).toHaveTextContent('Execution');
    expect(agent).toHaveTextContent('Agent Status');
  });
});

// ── J. Reliability/task interaction invariants ────────────────────────────────

describe('UX-1D — Reliability/task interaction', () => {
  it('UNKNOWN reliability: no premature OBSERVING_OUTCOME — pending banner shown', () => {
    render(
      <OutcomeSummary
        executionState="unknown"
        reliabilityState="UNKNOWN"
        outcomeState="PENDING"
        agentTaskStatus="OBSERVING_OUTCOME"
      />
    );
    // Outcome is blocked — pending banner shown
    expect(screen.getByTestId('outcome-pending-banner')).toBeInTheDocument();
    // No outcome claim rendered
    expect(screen.queryByTestId('outcome-summary-section')).not.toBeInTheDocument();
  });

  it('CONFIRMED_EXECUTED: task may show OBSERVING_OUTCOME without pending banner', () => {
    render(
      <OutcomeSummary
        executionState="executed"
        reliabilityState="CONFIRMED_EXECUTED"
        outcomeState="OBJECTIVE_ACHIEVED"
        agentTaskStatus="OBSERVING_OUTCOME"
      />
    );
    // No pending banner — execution resolved
    expect(screen.queryByTestId('outcome-pending-banner')).not.toBeInTheDocument();
    // Outcome shown
    expect(screen.getByTestId('outcome-summary-section')).toBeInTheDocument();
  });

  it('INDETERMINATE: task does not falsely complete — no outcome claim', () => {
    render(
      <OutcomeSummary
        executionState="unknown"
        reliabilityState="INDETERMINATE"
        outcomeState="INCONCLUSIVE"
        agentTaskStatus="ESCALATED"
      />
    );
    // No summary section — operator must review
    expect(screen.queryByTestId('outcome-summary-section')).not.toBeInTheDocument();
    // No entity/KPI deltas shown
    expect(screen.queryByTestId('outcome-entity-deltas')).not.toBeInTheDocument();
    expect(screen.queryByTestId('outcome-kpi-deltas')).not.toBeInTheDocument();
  });
});
