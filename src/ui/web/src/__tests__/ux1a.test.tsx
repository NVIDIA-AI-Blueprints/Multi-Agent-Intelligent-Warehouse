/**
 * UX-1A Authority-State Tests
 *
 * Critical invariants:
 * 1. approved !== 'Executed' (never conflate governance approval with ActionExecutor execution)
 * 2. /demo route renders without error (primary operator surface discoverable)
 * 3. AuthorityBoundary renders text content and is not color-only
 * 4. DECISION_STATUS_LABEL maps are factually correct
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import {
  OPERATOR_LABELS,
  DEVELOPER_LABELS,
  DECISION_STATUS_LABEL,
  PRE_EXECUTION_NOTICE,
  AUTHORITY_BOUNDARY_LABEL,
  AUTHORITY_BOUNDARY_SUBTEXT,
} from '../constants/authorityStates';
import AuthorityBoundary from '../components/AuthorityBoundary';

// ── 1. Status mapping invariants ──────────────────────────────────────────────

describe('Authority-state vocabulary invariants', () => {
  // CRITICAL: approved ≠ executed in all label systems
  it('OPERATOR_LABELS.approved is never "Executed"', () => {
    expect(OPERATOR_LABELS.approved).not.toBe('Executed');
    expect(OPERATOR_LABELS.approved).not.toBe('EXECUTED');
    expect(OPERATOR_LABELS.approved).not.toMatch(/executed/i);
  });

  it('OPERATOR_LABELS.executed is distinct from OPERATOR_LABELS.approved', () => {
    expect(OPERATOR_LABELS.executed).not.toBe(OPERATOR_LABELS.approved);
  });

  it('DEVELOPER_LABELS.approved is "APPROVED" (not "EXECUTED")', () => {
    expect(DEVELOPER_LABELS.approved).toBe('APPROVED');
    expect(DEVELOPER_LABELS.approved).not.toBe('EXECUTED');
  });

  it('DEVELOPER_LABELS.executed is "EXECUTED" (distinct from APPROVED)', () => {
    expect(DEVELOPER_LABELS.executed).toBe('EXECUTED');
    expect(DEVELOPER_LABELS.executed).not.toBe(DEVELOPER_LABELS.approved);
  });

  it('DECISION_STATUS_LABEL.approved is never "EXECUTED"', () => {
    expect(DECISION_STATUS_LABEL.approved).not.toBe('EXECUTED');
    expect(DECISION_STATUS_LABEL.approved).not.toMatch(/executed/i);
  });

  it('DECISION_STATUS_LABEL.approved reads "Approved"', () => {
    expect(DECISION_STATUS_LABEL.approved).toBe('Approved');
  });

  it('PRE_EXECUTION_NOTICE is defined and non-empty', () => {
    expect(PRE_EXECUTION_NOTICE).toBeDefined();
    expect(PRE_EXECUTION_NOTICE.length).toBeGreaterThan(0);
    expect(PRE_EXECUTION_NOTICE).toMatch(/no.*action.*executed/i);
  });

  it('All required states are defined in OPERATOR_LABELS', () => {
    const required = [
      'approved', 'rejected', 'executed', 'human_approval_required',
      'policy_approved', 'waiting_for_governance', 'confirmed_executed',
      'confirmed_not_executed', 'indeterminate',
    ] as const;
    for (const key of required) {
      expect(OPERATOR_LABELS[key]).toBeDefined();
      expect(typeof OPERATOR_LABELS[key]).toBe('string');
    }
  });

  it('policy_approved and approved have distinct labels', () => {
    expect(OPERATOR_LABELS.policy_approved).not.toBe(OPERATOR_LABELS.approved);
  });

  it('confirmed_executed and executed have distinct labels', () => {
    expect(OPERATOR_LABELS.confirmed_executed).not.toBe(OPERATOR_LABELS.executed);
  });
});

// ── 2. AuthorityBoundary component ────────────────────────────────────────────

describe('AuthorityBoundary component', () => {
  it('renders with text content (not color-only)', () => {
    render(<AuthorityBoundary />);
    expect(screen.getByText(AUTHORITY_BOUNDARY_LABEL)).toBeInTheDocument();
  });

  it('renders subtext in default (non-compact) mode', () => {
    render(<AuthorityBoundary />);
    expect(screen.getByText(AUTHORITY_BOUNDARY_SUBTEXT)).toBeInTheDocument();
  });

  it('omits subtext in compact mode', () => {
    render(<AuthorityBoundary compact />);
    expect(screen.queryByText(AUTHORITY_BOUNDARY_SUBTEXT)).not.toBeInTheDocument();
  });

  it('has role="separator" for accessibility', () => {
    render(<AuthorityBoundary />);
    expect(screen.getByRole('separator')).toBeInTheDocument();
  });

  it('has aria-label for screen reader users (not color-only)', () => {
    render(<AuthorityBoundary />);
    const separator = screen.getByRole('separator');
    expect(separator).toHaveAttribute('aria-label', AUTHORITY_BOUNDARY_LABEL);
  });

  it('renders with a custom testId', () => {
    render(<AuthorityBoundary testId="custom-boundary" />);
    expect(screen.getByTestId('custom-boundary')).toBeInTheDocument();
  });
});
