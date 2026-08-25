/**
 * Tests for DecisionLifecycle component.
 * Verifies safety outcomes are visually distinct and blocked states never show as executed.
 */

import React from 'react';
import { render, screen, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import { ThemeProvider } from '@mui/material/styles';
import { nvidiaTheme } from '../../theme/nvidiaTheme';
import DecisionLifecycle from '../../components/demo/DecisionLifecycle';

const STORAGE_KEY = 'maiw_decision_history';

function setDecisions(records: any[]) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(records));
}

function renderLifecycle() {
  return render(
    <ThemeProvider theme={nvidiaTheme}>
      <DecisionLifecycle />
    </ThemeProvider>
  );
}

beforeEach(() => {
  sessionStorage.clear();
  jest.useFakeTimers();
});

afterEach(() => {
  jest.useRealTimers();
  sessionStorage.clear();
});

describe('DecisionLifecycle', () => {
  it('renders the pipeline node labels', () => {
    renderLifecycle();
    // OBSERVE appears twice (start + end of pipeline)
    expect(screen.getAllByText('OBSERVE').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('REASON')).toBeInTheDocument();
    expect(screen.getByText('PROPOSE')).toBeInTheDocument();
    expect(screen.getByText('DECIDE')).toBeInTheDocument();
    expect(screen.getByText('EXECUTE')).toBeInTheDocument();
  });

  it('shows "No decisions" message when session is empty', () => {
    renderLifecycle();
    expect(screen.getByText(/No decisions this session/)).toBeInTheDocument();
  });

  it('shows EXECUTED label for approved decision', async () => {
    setDecisions([{
      id: 'test-1', action: 'assign', timestamp: new Date().toISOString(),
      request: { asset_id: 'AGV-01' },
      result: { status: 'approved', success: true },
    }]);
    renderLifecycle();
    act(() => { jest.advanceTimersByTime(2100); });
    expect(screen.getByText('EXECUTED')).toBeInTheDocument();
  });

  it('shows REJECTED label for rejected decision', async () => {
    setDecisions([{
      id: 'test-2', action: 'assign', timestamp: new Date().toISOString(),
      request: { asset_id: 'AGV-01' },
      result: { status: 'rejected' },
    }]);
    renderLifecycle();
    act(() => { jest.advanceTimersByTime(2100); });
    expect(screen.getByText('REJECTED')).toBeInTheDocument();
  });

  it('shows BLOCKED — STALE STATE for requires_fresh_state and never shows MCP WRITE', async () => {
    setDecisions([{
      id: 'test-3', action: 'assign', timestamp: new Date().toISOString(),
      request: { asset_id: 'AGV-01' },
      result: { status: 'requires_fresh_state' },
    }]);
    renderLifecycle();
    act(() => { jest.advanceTimersByTime(2100); });
    expect(screen.getByText('BLOCKED — STALE STATE')).toBeInTheDocument();
    expect(screen.queryByText('MCP WRITE')).not.toBeInTheDocument();
  });

  it('shows REQUIRES HUMAN APPROVAL and never shows MCP WRITE', async () => {
    setDecisions([{
      id: 'test-4', action: 'assign', timestamp: new Date().toISOString(),
      request: { asset_id: 'AGV-01' },
      result: { status: 'requires_human_approval' },
    }]);
    renderLifecycle();
    act(() => { jest.advanceTimersByTime(2100); });
    expect(screen.getByText('REQUIRES HUMAN APPROVAL')).toBeInTheDocument();
    expect(screen.queryByText('MCP WRITE')).not.toBeInTheDocument();
  });

  it('renders safety banner for requires_fresh_state', async () => {
    setDecisions([{
      id: 'test-5', action: 'assign', timestamp: new Date().toISOString(),
      request: {},
      result: { status: 'requires_fresh_state' },
    }]);
    renderLifecycle();
    act(() => { jest.advanceTimersByTime(2100); });
    expect(screen.getByText(/REQUIRES_FRESH_STATE/)).toBeInTheDocument();
    expect(screen.getByText(/execution blocked/)).toBeInTheDocument();
  });

  it('renders safety banner for requires_human_approval', async () => {
    setDecisions([{
      id: 'test-6', action: 'assign', timestamp: new Date().toISOString(),
      request: {},
      result: { status: 'requires_human_approval' },
    }]);
    renderLifecycle();
    act(() => { jest.advanceTimersByTime(2100); });
    expect(screen.getByText(/REQUIRES_HUMAN_APPROVAL/)).toBeInTheDocument();
    expect(screen.getByText(/no execution until operator approves/)).toBeInTheDocument();
  });

  it('renders safety banner for rejected with executed=false message', async () => {
    setDecisions([{
      id: 'test-7', action: 'assign', timestamp: new Date().toISOString(),
      request: {},
      result: { status: 'rejected' },
    }]);
    renderLifecycle();
    act(() => { jest.advanceTimersByTime(2100); });
    // Multiple REJECTED elements — check the banner specifically contains executed=false
    const banners = screen.getAllByText(/REJECTED/i);
    expect(banners.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/executed=false/)).toBeInTheDocument();
  });

  it('shows proposal action in pipeline for known decision', async () => {
    setDecisions([{
      id: 'test-8', action: 'maintenance', timestamp: new Date().toISOString(),
      request: { asset_id: 'FKL-01' },
      result: { status: 'approved' },
    }]);
    renderLifecycle();
    act(() => { jest.advanceTimersByTime(2100); });
    // PROPOSE node should show the action
    expect(screen.getByText('MAINTENANCE')).toBeInTheDocument();
  });

  it('shows OBSERVE OUTCOME node only when executed (approved)', async () => {
    // Approved → final OBSERVE node should be lit
    setDecisions([{
      id: 'test-9', action: 'assign', timestamp: new Date().toISOString(),
      request: {},
      result: { status: 'approved', success: true },
    }]);
    renderLifecycle();
    act(() => { jest.advanceTimersByTime(2100); });
    expect(screen.getByText('OUTCOME')).toBeInTheDocument();
  });

  it('does not show OUTCOME when blocked', async () => {
    setDecisions([{
      id: 'test-10', action: 'assign', timestamp: new Date().toISOString(),
      request: {},
      result: { status: 'requires_fresh_state' },
    }]);
    renderLifecycle();
    act(() => { jest.advanceTimersByTime(2100); });
    expect(screen.queryByText('OUTCOME')).not.toBeInTheDocument();
  });
});
