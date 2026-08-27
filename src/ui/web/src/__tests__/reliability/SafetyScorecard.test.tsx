import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import { ThemeProvider } from '@mui/material/styles';
import { nvidiaTheme } from '../../theme/nvidiaTheme';
import SafetyScorecard from '../../components/reliability/SafetyScorecard';
import { BATCH6_BASELINE } from '../../hooks/useReliabilityCounters';

function wrap(ui: React.ReactElement) {
  return render(<ThemeProvider theme={nvidiaTheme}>{ui}</ThemeProvider>);
}

describe('SafetyScorecard', () => {
  it('renders ALL SAFE when no counters provided (uses Batch 6 baseline)', () => {
    wrap(<SafetyScorecard />);
    expect(screen.getByText('ALL SAFE')).toBeInTheDocument();
  });

  it('shows VALIDATED BATCH 6 badge when using baseline data', () => {
    wrap(<SafetyScorecard />);
    expect(screen.getByText(/VALIDATED BATCH 6/i)).toBeInTheDocument();
  });

  it('shows all five counter labels', () => {
    wrap(<SafetyScorecard />);
    expect(screen.getByText('Unauthorized writes')).toBeInTheDocument();
    expect(screen.getByText('Duplicate writes')).toBeInTheDocument();
    expect(screen.getByText('False successes')).toBeInTheDocument();
    expect(screen.getByText('UNKNOWN executions')).toBeInTheDocument();
    expect(screen.getByText('Reconciled')).toBeInTheDocument();
  });

  it('shows Batch 6 baseline values', () => {
    wrap(<SafetyScorecard />);
    // unauthorized/duplicate/false = 0
    const zeros = screen.getAllByText('0');
    expect(zeros.length).toBeGreaterThanOrEqual(3);
  });

  it('shows VIOLATION when unauthorized_writes > 0', () => {
    const bad = { ...BATCH6_BASELINE, unauthorized_writes: 1 };
    wrap(<SafetyScorecard counters={bad} />);
    expect(screen.getByText('VIOLATION')).toBeInTheDocument();
  });

  it('shows validated badge via showValidatedBadge prop', () => {
    const live = { ...BATCH6_BASELINE };
    wrap(<SafetyScorecard counters={live} showValidatedBadge />);
    expect(screen.getByText(/VALIDATED BATCH 6/i)).toBeInTheDocument();
  });
});
