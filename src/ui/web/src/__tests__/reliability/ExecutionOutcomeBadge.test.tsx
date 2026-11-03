import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import { ThemeProvider } from '@mui/material/styles';
import { nvidiaTheme } from '../../theme/nvidiaTheme';
import ExecutionOutcomeBadge from '../../components/reliability/ExecutionOutcomeBadge';

function wrap(ui: React.ReactElement) {
  return render(<ThemeProvider theme={nvidiaTheme}>{ui}</ThemeProvider>);
}

describe('ExecutionOutcomeBadge', () => {
  it('renders EXECUTED state', () => {
    wrap(<ExecutionOutcomeBadge outcome="EXECUTED" />);
    expect(screen.getByText('EXECUTED')).toBeInTheDocument();
  });

  it('renders NO_OP state', () => {
    wrap(<ExecutionOutcomeBadge outcome="NO_OP" />);
    expect(screen.getByText('NO-OP')).toBeInTheDocument();
  });

  it('renders UNKNOWN with operator description', () => {
    wrap(<ExecutionOutcomeBadge outcome="UNKNOWN" />);
    expect(screen.getByText('UNKNOWN')).toBeInTheDocument();
    expect(screen.getByText(/reconcile before retry/i)).toBeInTheDocument();
  });

  it('renders FAILED with safe description', () => {
    wrap(<ExecutionOutcomeBadge outcome="FAILED" />);
    expect(screen.getByText('FAILED')).toBeInTheDocument();
    expect(screen.getByText(/safe to re-evaluate/i)).toBeInTheDocument();
  });

  it('renders reconciliation outcome alongside execution outcome', () => {
    wrap(<ExecutionOutcomeBadge outcome="UNKNOWN" reconciliation="CONFIRMED_EXECUTED" />);
    expect(screen.getByText('UNKNOWN')).toBeInTheDocument();
    expect(screen.getByText(/CONFIRMED EXECUTED/i)).toBeInTheDocument();
  });

  it('renders INDETERMINATE reconciliation', () => {
    wrap(<ExecutionOutcomeBadge outcome="UNKNOWN" reconciliation="INDETERMINATE" />);
    expect(screen.getByText(/INDETERMINATE/i)).toBeInTheDocument();
  });

  it('compact mode omits description', () => {
    wrap(<ExecutionOutcomeBadge outcome="UNKNOWN" compact />);
    expect(screen.getByText('UNKNOWN')).toBeInTheDocument();
    expect(screen.queryByText(/reconcile before retry/i)).not.toBeInTheDocument();
  });

  it('renders a label and description for all 6 outcome states', () => {
    const outcomes = [
      ['EXECUTED', 'EXECUTED', /mutation confirmed/i],
      ['NO_OP', 'NO-OP', /idempotent replay/i],
      ['DEFERRED', 'DEFERRED', /awaiting human approval/i],
      ['CONFLICT', 'CONFLICT', /state drift blocked execution/i],
      ['UNKNOWN', 'UNKNOWN', /reconcile before retry/i],
      ['FAILED', 'FAILED', /safe to re-evaluate/i],
    ] as const;
    outcomes.forEach(([outcome, label, desc]) => {
      const { unmount } = wrap(<ExecutionOutcomeBadge outcome={outcome} />);
      expect(screen.getByText(label)).toBeInTheDocument();
      expect(screen.getByText(desc)).toBeInTheDocument();
      unmount();
    });
  });
});
