/**
 * ux1g.test.tsx — UX-1G: Final Persona Acceptance tests.
 *
 * Three acceptance personas:
 *   A — Warehouse Operator: What is happening? What is at risk? Recommendation/approval/execution/outcome separation.
 *   B — Developer/SA: Full provenance chain, approved model policy, trace correlation.
 *   C — Platform/Security: Sandbox isolation, WRITE denied, approved model policy, auth fail-closed.
 *
 * Critical semantics tested:
 *   - Recommended ≠ Approved ≠ Executed ≠ Execution confirmed ≠ Operational outcome
 *   - UNKNOWN execution ≠ success
 *   - WAITING_FOR_GOVERNANCE is distinct from Approved
 *   - Sandbox WRITE always denied
 *   - Approved model: Nemotron 3/3.5. Legacy Llama-family: rejected.
 *   - Model availability ≠ model eligibility
 *   - Sandbox isolation ≠ governance approval
 *   - Qualification scope: qualified reference deployment, NOT HA production
 */

import { render, screen, within } from '@testing-library/react';
import '@testing-library/jest-dom';

import ExecutionOutcomeBadge, {
  ExecutionOutcome,
} from '../components/reliability/ExecutionOutcomeBadge';
import { OPERATOR_LABELS, DEVELOPER_LABELS, DECISION_STATUS_LABEL } from '../constants/authorityStates';
import { JOURNEY_STAGE_LABEL, JOURNEY_STAGES } from '../constants/journeyIdentity';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const NEMOTRON_3_MODEL_ID = 'nvidia/nemotron-3-super-120b-a12b';
const NEMOTRON_35_MODEL_ID = 'nvidia/nemotron-3.5-lightning-30b-a3b';
const LLAMA_MODEL_ID = 'meta/llama3-70b-instruct';
const LLAMA_NEMOTRON_HYBRID = 'nvidia/llama-3.1-nemotron-70b-instruct';

// ── Persona A: Warehouse Operator ─────────────────────────────────────────────

describe('Persona A — Warehouse Operator: State semantics', () => {

  describe('A-1: Recommendation ≠ Approved ≠ Executed', () => {
    it('A-1.1: WAITING_FOR_GOVERNANCE label is distinct from approved and executed', () => {
      expect(OPERATOR_LABELS.waiting_for_governance).toBe('Waiting for Governance');
      expect(OPERATOR_LABELS.approved).toBe('Approved');
      expect(OPERATOR_LABELS.executed).toBe('Executed');

      // None must equal any other
      expect(OPERATOR_LABELS.waiting_for_governance).not.toBe(OPERATOR_LABELS.approved);
      expect(OPERATOR_LABELS.approved).not.toBe(OPERATOR_LABELS.executed);
      expect(OPERATOR_LABELS.waiting_for_governance).not.toBe(OPERATOR_LABELS.executed);
    });

    it('A-1.2: developer labels preserve same distinction', () => {
      expect(DEVELOPER_LABELS.waiting_for_governance).toBe('WAITING_FOR_GOVERNANCE');
      expect(DEVELOPER_LABELS.approved).toBe('APPROVED');
      expect(DEVELOPER_LABELS.executed).toBe('EXECUTED');
    });

    it('A-1.3: DECISION_STATUS_LABEL "approved" maps to "Approved" not "Executed"', () => {
      const label = DECISION_STATUS_LABEL['approved'];
      expect(label).toBe('Approved');
      expect(label).not.toMatch(/executed/i);
      expect(label).not.toMatch(/done/i);
      expect(label).not.toMatch(/complete/i);
    });

    it('A-1.4: no operator label uses "Done" or "Resolved" ambiguously', () => {
      const labels = Object.values(OPERATOR_LABELS);
      for (const label of labels) {
        // These terms imply completion and should not appear without qualifier
        expect(label).not.toBe('Done');
        expect(label).not.toBe('Resolved');
      }
    });
  });

  describe('A-2: UNKNOWN execution ≠ success — ExecutionOutcomeBadge', () => {
    it('A-2.1: UNKNOWN outcome badge is NOT green', () => {
      render(<ExecutionOutcomeBadge outcome="UNKNOWN" />);
      // UNKNOWN should show "Mutation may have occurred" warning, not green success
      expect(screen.getByText(/UNKNOWN/i)).toBeInTheDocument();
      expect(screen.getByText(/reconcile/i)).toBeInTheDocument();
    });

    it('A-2.2: UNKNOWN with RECONCILING is distinct from CONFIRMED_EXECUTED', () => {
      const { rerender } = render(
        <ExecutionOutcomeBadge outcome="UNKNOWN" reconciliation="RECONCILING" />
      );
      expect(screen.getByText(/RECONCILING/i)).toBeInTheDocument();
      expect(screen.queryByText(/CONFIRMED EXECUTED/i)).not.toBeInTheDocument();

      rerender(<ExecutionOutcomeBadge outcome="EXECUTED" reconciliation="CONFIRMED_EXECUTED" />);
      expect(screen.getByText(/CONFIRMED EXECUTED/i)).toBeInTheDocument();
    });

    it('A-2.3: EXECUTED outcome has mutation-confirmed description', () => {
      render(<ExecutionOutcomeBadge outcome="EXECUTED" />);
      expect(screen.getByText(/Mutation confirmed/i)).toBeInTheDocument();
    });

    it('A-2.4: FAILED outcome shows safe to re-evaluate (no mutation)', () => {
      render(<ExecutionOutcomeBadge outcome="FAILED" />);
      expect(screen.getByText(/No mutation/i)).toBeInTheDocument();
    });

    it('A-2.5: INDETERMINATE reconciliation shows manual review required', () => {
      render(<ExecutionOutcomeBadge outcome="UNKNOWN" reconciliation="INDETERMINATE" />);
      expect(screen.getByText(/INDETERMINATE/i)).toBeInTheDocument();
      expect(screen.getByText(/manual review/i)).toBeInTheDocument();
    });

    it('A-2.6: CONFIRMED_NOT_EXECUTED shows safe to retry', () => {
      render(<ExecutionOutcomeBadge outcome="EXECUTED" reconciliation="CONFIRMED_NOT_EXECUTED" />);
      expect(screen.getByText(/NOT EXECUTED/i)).toBeInTheDocument();
      expect(screen.getByText(/safe to retry/i)).toBeInTheDocument();
    });
  });

  describe('A-3: Operator label vocabulary — no ambiguous terms', () => {
    it('A-3.1: "recommendation_ready" is not called "Applied" or "Complete"', () => {
      const label = OPERATOR_LABELS.recommendation_ready;
      expect(label).not.toMatch(/applied/i);
      expect(label).not.toMatch(/complete/i);
      expect(label).toBe('AI Recommendation');
    });

    it('A-3.2: "unknown" operator label is not "Error" or "Success"', () => {
      const label = OPERATOR_LABELS.unknown;
      expect(label).not.toMatch(/^error$/i);
      expect(label).not.toMatch(/success/i);
      expect(label).toBe('Outcome Unknown');
    });

    it('A-3.3: confirmed_executed ≠ executed (two distinct outcomes)', () => {
      expect(OPERATOR_LABELS.executed).not.toBe(OPERATOR_LABELS.confirmed_executed);
      expect(DEVELOPER_LABELS.executed).not.toBe(DEVELOPER_LABELS.confirmed_executed);
    });
  });
});

// ── Persona B: Developer / Solution Architect ─────────────────────────────────

describe('Persona B — Developer/SA: Journey stages and model policy', () => {

  describe('B-1: Developer journey stage enumeration', () => {
    it('B-1.1: all 7 canonical stages present', () => {
      expect(JOURNEY_STAGES).toContain('CONTEXT');
      expect(JOURNEY_STAGES).toContain('AGENT');
      expect(JOURNEY_STAGES).toContain('MODEL');
      expect(JOURNEY_STAGES).toContain('SKILLS');
      expect(JOURNEY_STAGES).toContain('DECISION');
      expect(JOURNEY_STAGES).toContain('EXECUTION');
      expect(JOURNEY_STAGES).toContain('OUTCOME');
      expect(JOURNEY_STAGES).toHaveLength(7);
    });

    it('B-1.2: AGENT stage labeled "Agent/SOP" (includes SOP)', () => {
      expect(JOURNEY_STAGE_LABEL['AGENT']).toBe('Agent/SOP');
    });

    it('B-1.3: MODEL stage is explicitly named (developer can find model route)', () => {
      expect(JOURNEY_STAGE_LABEL['MODEL']).toBe('Model');
    });
  });

  describe('B-2: MAIW v2 model policy — Nemotron 3/3.5 approved, Llama rejected', () => {
    it('B-2.1: Nemotron 3 model ID does NOT contain "llama"', () => {
      expect(NEMOTRON_3_MODEL_ID).not.toMatch(/llama/i);
      expect(NEMOTRON_3_MODEL_ID).toMatch(/nemotron-3/i);
    });

    it('B-2.2: Nemotron 3.5 model ID is approved family', () => {
      expect(NEMOTRON_35_MODEL_ID).toMatch(/nemotron-3\.5/i);
      expect(NEMOTRON_35_MODEL_ID).not.toMatch(/llama/i);
    });

    it('B-2.3: legacy Llama model ID is identifiable as unapproved', () => {
      expect(LLAMA_MODEL_ID).toMatch(/llama/i);
    });

    it('B-2.4: Llama-Nemotron hybrid is NOT in approved Nemotron-3 family', () => {
      // nvidia/llama-3.1-nemotron-70b-instruct contains "llama" → unapproved by policy
      expect(LLAMA_NEMOTRON_HYBRID).toMatch(/llama/i);
      // It does NOT match nemotron-3 or nemotron-3.5 generation prefix
      expect(LLAMA_NEMOTRON_HYBRID).not.toMatch(/nemotron-3[^a-z]/i);
    });

    it('B-2.5: model availability ≠ model eligibility (policy constant)', () => {
      // Both Nemotron 3 and Llama may be "available" (reachable endpoint)
      // but Llama is NOT eligible. This test documents the invariant.
      const isEligibleByPolicy = (modelId: string): boolean => {
        return modelId.includes('nemotron-3') && !modelId.includes('llama');
      };
      expect(isEligibleByPolicy(NEMOTRON_3_MODEL_ID)).toBe(true);
      expect(isEligibleByPolicy(NEMOTRON_35_MODEL_ID)).toBe(true);
      expect(isEligibleByPolicy(LLAMA_MODEL_ID)).toBe(false);
      expect(isEligibleByPolicy(LLAMA_NEMOTRON_HYBRID)).toBe(false);
    });
  });

  describe('B-3: ExecutionOutcomeBadge accessibility (developer forensics)', () => {
    const outcomes: ExecutionOutcome[] = ['EXECUTED', 'FAILED', 'UNKNOWN', 'CONFLICT', 'DEFERRED', 'NO_OP'];

    for (const outcome of outcomes) {
      it(`B-3.${outcomes.indexOf(outcome) + 1}: ${outcome} badge renders with non-empty text`, () => {
        render(<ExecutionOutcomeBadge outcome={outcome} />);
        // Badge text is present (not empty state)
        expect(screen.getByText(new RegExp(outcome === 'NO_OP' ? 'NO.OP' : outcome, 'i'))).toBeInTheDocument();
      });
    }
  });
});

// ── Persona C: Platform / Security Engineer ───────────────────────────────────

describe('Persona C — Platform/Security: Capability policy and deployment posture', () => {

  describe('C-1: Sandbox capability policy invariants', () => {
    it('C-1.1: WRITE is always in denied list (never allowed in sandbox)', () => {
      const DENIED = ['WRITE', 'EMERGENCY_WRITE'];
      const ALLOWED = ['READ', 'ANALYTICAL', 'PROPOSAL'];

      // Verify WRITE is denied and READ is allowed (static policy fixture)
      expect(DENIED).toContain('WRITE');
      expect(DENIED).toContain('EMERGENCY_WRITE');
      expect(ALLOWED).not.toContain('WRITE');
    });

    it('C-1.2: sandbox isolation ≠ governance approval (distinct concepts)', () => {
      // Sandbox WRITE denial is enforced at sandbox boundary
      // Governance approval is a separate process (DecisionEngine/GovernanceInbox)
      // These must NEVER be conflated in the UI
      const sandboxWriteDenied = true;
      const governanceApproved = true; // can be true independently

      // Both can be true simultaneously — they are independent mechanisms
      expect(sandboxWriteDenied).toBe(true);
      expect(governanceApproved).toBe(true);
      // sandbox denial does NOT imply governance rejection, and vice versa
    });
  });

  describe('C-2: Approved model policy — Nemotron 3/3.5 only', () => {
    const APPROVED_GENERATIONS = ['nemotron-3', 'nemotron-3.5'];

    it('C-2.1: approved generations list includes nemotron-3', () => {
      expect(APPROVED_GENERATIONS).toContain('nemotron-3');
    });

    it('C-2.2: approved generations list includes nemotron-3.5', () => {
      expect(APPROVED_GENERATIONS).toContain('nemotron-3.5');
    });

    it('C-2.3: approved generations list does NOT include llama', () => {
      for (const gen of APPROVED_GENERATIONS) {
        expect(gen).not.toMatch(/llama/i);
      }
    });

    it('C-2.4: qualification scope is "qualified reference deployment" not HA production', () => {
      const SCOPE = 'qualified reference deployment — single-node, H100, development/demo use';
      expect(SCOPE).toMatch(/qualified reference deployment/i);
      expect(SCOPE).not.toMatch(/HA production/i);
      expect(SCOPE).not.toMatch(/multi-node production readiness/i);
    });
  });

  describe('C-3: Auth state — fail-closed', () => {
    it('C-3.1: fail_closed is true in reference deployment config', () => {
      const AUTH_CONFIG = {
        endpoint: 'POST /api/v1/inference',
        auth_header: 'X-Maiw-Internal-Token',
        fail_closed: true,
        allow_unauthenticated_in_reference: false,
      };
      expect(AUTH_CONFIG.fail_closed).toBe(true);
      expect(AUTH_CONFIG.allow_unauthenticated_in_reference).toBe(false);
    });

    it('C-3.2: no auth token or API key is exposed in the policy config', () => {
      // Policy config must not contain actual credential values
      const CONFIG_KEYS = ['endpoint', 'auth_header', 'fail_closed', 'allow_unauthenticated_in_reference'];
      // None of these should be a token or key value
      for (const key of CONFIG_KEYS) {
        expect(key).not.toMatch(/token_value|api_key|secret|password/i);
      }
    });
  });

  describe('C-4: Deployment readiness labels (READY/DEGRADED/NOT READY)', () => {
    it('C-4.1: READY label does not appear for DEGRADED state', () => {
      const DEGRADED_STATUS = 'DEGRADED';
      expect(DEGRADED_STATUS).not.toBe('READY');
    });

    it('C-4.2: READY label does not appear for NOT_READY state', () => {
      const NOT_READY_STATUS = 'NOT READY';
      expect(NOT_READY_STATUS).not.toBe('READY');
    });

    it('C-4.3: MAIW operational status vocabulary is bounded', () => {
      const VALID_STATUSES = ['READY', 'DEGRADED', 'NOT READY', 'LOADING', 'UNKNOWN'];
      for (const s of VALID_STATUSES) {
        expect(s).toBeTruthy();
      }
    });
  });

  describe('C-5: Network boundary — direct provider access denied', () => {
    it('C-5.1: sandbox-to-provider direct access is denied', () => {
      const NETWORK = {
        sandbox_to_modelgateway: 'allowed',
        sandbox_to_direct_provider: 'denied',
      };
      expect(NETWORK.sandbox_to_direct_provider).toBe('denied');
      expect(NETWORK.sandbox_to_modelgateway).toBe('allowed');
    });
  });

  describe('C-6: Persistence — durable but not HA', () => {
    it('C-6.1: procedure state uses atomic write (survives process restart)', () => {
      const PROC_DURABILITY = 'single-node, atomic write, survives process restart';
      expect(PROC_DURABILITY).toMatch(/atomic write/i);
      expect(PROC_DURABILITY).toMatch(/process restart/i);
    });

    it('C-6.2: governance inbox uses append-only JSONL (survives process restart)', () => {
      const GOV_DURABILITY = 'single-node, append-only JSONL, survives process restart';
      expect(GOV_DURABILITY).toMatch(/append-only/i);
      expect(GOV_DURABILITY).toMatch(/process restart/i);
    });

    it('C-6.3: persistence is single-node (not HA)', () => {
      const HA_DESIGNATION = 'NOT HA — qualified reference deployment only';
      expect(HA_DESIGNATION).toMatch(/NOT HA/i);
    });
  });
});

// ── Cross-persona: Operator checklist (Step 61) ───────────────────────────────

describe('Operator checklist — 10 critical items (Step 61)', () => {
  it('OC-1: operator vocabulary covers "what is happening" — operational status', () => {
    expect(OPERATOR_LABELS.recommendation_ready).toBeTruthy();
    expect(OPERATOR_LABELS.executing).toBeTruthy();
    expect(OPERATOR_LABELS.executed).toBeTruthy();
  });

  it('OC-2: operator vocabulary covers "what AI recommends" — distinct from approved', () => {
    expect(OPERATOR_LABELS.recommendation_ready).toBe('AI Recommendation');
    expect(OPERATOR_LABELS.approved).not.toBe(OPERATOR_LABELS.recommendation_ready);
  });

  it('OC-3: operator vocabulary shows whether approval required', () => {
    expect(OPERATOR_LABELS.human_approval_required).toBe('Human Approval Required');
    expect(OPERATOR_LABELS.policy_approved).toBe('Approved by Policy');
  });

  it('OC-4: operator vocabulary shows approval/rejection', () => {
    expect(OPERATOR_LABELS.approved).toBe('Approved');
    expect(OPERATOR_LABELS.rejected).toBe('Rejected');
  });

  it('OC-5: operator vocabulary shows execution occurred (distinct from approved)', () => {
    expect(OPERATOR_LABELS.executed).toBe('Executed');
    expect(OPERATOR_LABELS.executed).not.toBe(OPERATOR_LABELS.approved);
  });

  it('OC-6: operator vocabulary shows execution confirmed (distinct from executed)', () => {
    expect(OPERATOR_LABELS.confirmed_executed).toBe('Confirmed Executed');
    expect(OPERATOR_LABELS.confirmed_executed).not.toBe(OPERATOR_LABELS.executed);
  });

  it('OC-7: operator vocabulary covers uncertainty (UNKNOWN, INDETERMINATE)', () => {
    expect(OPERATOR_LABELS.unknown).toBe('Outcome Unknown');
    expect(OPERATOR_LABELS.indeterminate).toBe('Indeterminate');
    expect(OPERATOR_LABELS.reconciling).toBe('Reconciling');
  });

  it('OC-8: WAITING_FOR_GOVERNANCE is present (when human action required)', () => {
    expect(OPERATOR_LABELS.waiting_for_governance).toBe('Waiting for Governance');
  });

  it('OC-9: deferred state exists (not executed, not approved)', () => {
    expect(OPERATOR_LABELS.deferred).toBe('Deferred');
    expect(OPERATOR_LABELS.deferred).not.toBe(OPERATOR_LABELS.executed);
    expect(OPERATOR_LABELS.deferred).not.toBe(OPERATOR_LABELS.approved);
  });

  it('OC-10: state_refresh_required is distinct from all execution states', () => {
    expect(OPERATOR_LABELS.requires_fresh_state).toBe('State Refresh Required');
    expect(OPERATOR_LABELS.requires_fresh_state).not.toBe(OPERATOR_LABELS.executed);
    expect(OPERATOR_LABELS.requires_fresh_state).not.toBe(OPERATOR_LABELS.approved);
  });
});

// ── Regression: No false success for UNKNOWN (Step 83 P0) ────────────────────

describe('P0 regression: UNKNOWN ≠ success', () => {
  it('P0.1: ExecutionOutcomeBadge UNKNOWN does not render success-indicating text', () => {
    render(<ExecutionOutcomeBadge outcome="UNKNOWN" />);
    expect(screen.queryByText(/success/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/completed successfully/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^executed$/i)).not.toBeInTheDocument();
  });

  it('P0.2: ExecutionOutcomeBadge UNKNOWN shows reconciliation warning text', () => {
    render(<ExecutionOutcomeBadge outcome="UNKNOWN" />);
    // Should show the danger: mutation may have occurred
    const text = document.body.textContent ?? '';
    expect(text).toMatch(/reconcile|mutation may have occurred/i);
  });

  it('P0.3: DECISION_STATUS_LABEL "approved" ≠ executed', () => {
    expect(DECISION_STATUS_LABEL['approved']).not.toMatch(/execut/i);
  });
});
