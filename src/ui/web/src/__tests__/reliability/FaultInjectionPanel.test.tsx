import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
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

  it('shows TEST ONLY for non-injectable profiles (F01, F06, F08)', () => {
    wrap();
    const testOnlyLabels = screen.getAllByText('TEST ONLY');
    expect(testOnlyLabels.length).toBe(3);
  });

  it('shows INJECT buttons for injectable profiles (F10, F12)', () => {
    wrap();
    const injectButtons = screen.getAllByText('INJECT');
    expect(injectButtons.length).toBe(2);
  });

  it('F12 opens the labor circuit (mcp_outage) and offers RESTORE (mcp_restore)', async () => {
    (demoAPI.inject as jest.Mock).mockResolvedValueOnce({ domain: 'labor', circuit_state: 'open' });
    wrap(true);
    const f12Row = screen.getByText('F12').parentElement as HTMLElement;
    fireEvent.click(within(f12Row).getByText('INJECT'));
    await waitFor(() => expect(demoAPI.inject).toHaveBeenCalledWith('mcp_outage', { domain: 'labor' }));
    expect(await screen.findByTestId('fault-inject-feedback')).toHaveTextContent('F12 · Targeted labor');

    fireEvent.click(within(f12Row).getByText('RESTORE'));
    await waitFor(() => expect(demoAPI.inject).toHaveBeenLastCalledWith('mcp_restore', { domain: 'labor' }));
    expect(await screen.findByTestId('fault-inject-feedback')).toHaveTextContent('F12 · restored');
    expect(within(f12Row).getByText('INJECT')).toBeInTheDocument();
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
