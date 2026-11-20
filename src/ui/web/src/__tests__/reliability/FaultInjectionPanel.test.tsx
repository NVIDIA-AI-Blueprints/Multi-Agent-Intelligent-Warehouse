import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { ThemeProvider } from '@mui/material/styles';
import { nvidiaTheme } from '../../theme/nvidiaTheme';
import FaultInjectionPanel from '../../components/reliability/FaultInjectionPanel';
import { demoAPI } from '../../services/demoAPI';

jest.mock('../../services/demoAPI', () => ({
  demoAPI: {
    inject: jest.fn().mockResolvedValue({ ok: true }),
  },
}));

function wrap(scenarioActive = true) {
  return render(
    <ThemeProvider theme={nvidiaTheme}>
      <FaultInjectionPanel scenarioActive={scenarioActive} />
    </ThemeProvider>
  );
}

describe('FaultInjectionPanel', () => {
  beforeEach(() => jest.clearAllMocks());

  it('renders all 5 fault profiles', () => {
    wrap();
    expect(screen.getByText('F01')).toBeInTheDocument();
    expect(screen.getByText('F06')).toBeInTheDocument();
    expect(screen.getByText('F08')).toBeInTheDocument();
    expect(screen.getByText('F10')).toBeInTheDocument();
    expect(screen.getByText('F12')).toBeInTheDocument();
  });

  it('shows DEMO FAULT INJECTION header', () => {
    wrap();
    expect(screen.getByText(/DEMO FAULT INJECTION/i)).toBeInTheDocument();
  });

  it('shows TEST ONLY for non-injectable profiles (F01, F06, F08, F12)', () => {
    wrap();
    const testOnlyLabels = screen.getAllByText('TEST ONLY');
    expect(testOnlyLabels.length).toBe(4);
  });

  it('shows an INJECT button only for F10', () => {
    wrap();
    const injectButtons = screen.getAllByText('INJECT');
    expect(injectButtons.length).toBe(1);
  });

  it('F12 is test-only: Demo Mode has no event that trips a domain circuit', () => {
    wrap(true);
    const f12Row = screen.getByText('F12').parentElement as HTMLElement;
    expect(f12Row).toHaveTextContent('CIRCUIT OPEN');
    expect(f12Row).toHaveTextContent('TEST ONLY');
    expect(f12Row.querySelector('button')).toBeNull();
  });

  it('calls demoAPI.inject when INJECT clicked for F10 — backend resolves the asset', async () => {
    wrap(true);
    const injectButtons = screen.getAllByText('INJECT');
    fireEvent.click(injectButtons[0]);
    await waitFor(() => {
      expect(demoAPI.inject).toHaveBeenCalledWith(
        'equipment_fault',
        expect.objectContaining({ fault_code: 'E_STATE_DRIFT_SIM' }),
      );
    });
    const payload = (demoAPI.inject as jest.Mock).mock.calls[0][1];
    expect(payload).not.toHaveProperty('asset_id');
  });

  it('shows "Start a scenario" hint when scenario not active', () => {
    wrap(false);
    expect(screen.getByText(/Start a scenario/i)).toBeInTheDocument();
  });

  it('disables INJECT buttons when scenario is not active', () => {
    wrap(false);
    const buttons = screen.queryAllByText('INJECT');
    buttons.forEach(btn => {
      expect(btn.closest('button')).toBeDisabled();
    });
  });
});
