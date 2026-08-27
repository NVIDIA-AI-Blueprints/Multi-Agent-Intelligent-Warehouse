/**
 * F06 hero fault guided flow: UNKNOWN → RECONCILING → CONFIRMED_EXECUTED.
 * Validates that the UI components correctly represent the ambiguous write lifecycle.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import { ThemeProvider } from '@mui/material/styles';
import { nvidiaTheme } from '../../theme/nvidiaTheme';
import ExecutionOutcomeBadge from '../../components/reliability/ExecutionOutcomeBadge';
import ReconciliationStatus from '../../components/reliability/ReconciliationStatus';

function wrap(ui: React.ReactElement) {
  return render(<ThemeProvider theme={nvidiaTheme}>{ui}</ThemeProvider>);
}

describe('F06 ambiguous write hero flow', () => {
  it('step 1: UNKNOWN outcome badge shown with reconcile description', () => {
    wrap(<ExecutionOutcomeBadge outcome="UNKNOWN" />);
    expect(screen.getByText('UNKNOWN')).toBeInTheDocument();
    expect(screen.getByText(/reconcile before retry/i)).toBeInTheDocument();
  });

  it('step 1: UNKNOWN outcome does NOT say FAILED', () => {
    wrap(<ExecutionOutcomeBadge outcome="UNKNOWN" />);
    expect(screen.queryByText('FAILED')).not.toBeInTheDocument();
  });

  it('step 2: RECONCILING state shown in flow', () => {
    wrap(<ReconciliationStatus state="RECONCILING" />);
    expect(screen.getByText('RECONCILING')).toBeInTheDocument();
  });

  it('step 3: CONFIRMED_EXECUTED shown as final verdict', () => {
    wrap(<ReconciliationStatus state="CONFIRMED_EXECUTED" />);
    expect(screen.getByText(/CONFIRMED EXECUTED/i)).toBeInTheDocument();
  });

  it('step 3: UNKNOWN history preserved note shown', () => {
    wrap(<ReconciliationStatus state="CONFIRMED_EXECUTED" />);
    expect(screen.getByText(/ExecutionRecord.outcome = UNKNOWN/i)).toBeInTheDocument();
  });

  it('INDETERMINATE path shown when reconciliation cannot resolve', () => {
    wrap(<ReconciliationStatus state="INDETERMINATE" />);
    expect(screen.getByText(/INDETERMINATE/i)).toBeInTheDocument();
    expect(screen.getByText(/manual review required/i)).toBeInTheDocument();
  });

  it('complete F06 trace: UNKNOWN badge + CONFIRMED_EXECUTED reconciliation', () => {
    wrap(<ExecutionOutcomeBadge outcome="UNKNOWN" reconciliation="CONFIRMED_EXECUTED" />);
    expect(screen.getByText('UNKNOWN')).toBeInTheDocument();
    expect(screen.getByText(/CONFIRMED EXECUTED/i)).toBeInTheDocument();
  });

  it('F06: no retry on UNKNOWN — badge does not say RETRYING', () => {
    wrap(<ExecutionOutcomeBadge outcome="UNKNOWN" />);
    expect(screen.queryByText(/RETRYING/i)).not.toBeInTheDocument();
  });
});
