/**
 * Phase 12G — Expert overlay tests.
 * Updated for Phase 13E: ExpertOverlay now has TRACE | RUNTIME | RAW EVENTS tabs.
 * Runtime and SSE sections are only rendered when their respective tab is active.
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { ThemeProvider } from '@mui/material/styles';
import { nvidiaTheme } from '../../theme/nvidiaTheme';
import { SSEEvent } from '../../hooks/useDemoSSE';
import ExpertOverlay from '../../components/demo/ExpertOverlay';

function makeSSE(overrides: Partial<SSEEvent>): SSEEvent {
  return {
    id: '1', ts: '2026-08-28T10:00:00Z', category: 'OBSERVE',
    message: 'snapshot', detail: null, asset_id: null, task_id: null, worker_id: null,
    ...overrides,
  };
}

const baseRuntime = {
  runtime_initialized: true,
  uptime_seconds: 125,
  model_gateway_available: true,
  decision_engine_available: true,
  state_provider_available: true,
  inventory_mcp_configured: true,
  equipment_mcp_configured: true,
  labor_mcp_configured: true,
  wave_mcp_configured: false,
  operations_agent_available: true,
  equipment_agent_available: true,
  safety_agent_available: false,
  equipment_executor_available: true,
  labor_executor_available: true,
  wave_executor_available: false,
  maiw_operational_status: 'HEALTHY',
  model_gateway_status: 'HEALTHY',
  domain_health: { inventory: 'HEALTHY', equipment: 'HEALTHY', labor: 'HEALTHY', wave: 'DEGRADED' },
};

const baseDemoStatus = { scenario: { name: 'labor_constraint_wave_risk' }, world: { elapsed_seconds: 300 }, active: true };

function wrap(ui: React.ReactElement) {
  return render(<ThemeProvider theme={nvidiaTheme}>{ui}</ThemeProvider>);
}

/** Switch ExpertOverlay to the Runtime tab. */
function switchToRuntime() {
  fireEvent.click(screen.getByText('Runtime'));
}

/** Switch ExpertOverlay to the Raw Events tab. */
function switchToRawEvents() {
  fireEvent.click(screen.getByText('Raw Events'));
}

describe('ExpertOverlay', () => {
  it('renders the overlay', () => {
    wrap(<ExpertOverlay runtime={baseRuntime as any} demoStatus={baseDemoStatus as any} sseEvents={[]} />);
    expect(screen.getByTestId('expert-overlay')).toBeInTheDocument();
  });

  it('shows scenario name and elapsed in header', () => {
    wrap(<ExpertOverlay runtime={baseRuntime as any} demoStatus={baseDemoStatus as any} sseEvents={[]} />);
    // Header shows both scenario name and elapsed — use the combined pattern for uniqueness
    expect(screen.getByText(/300s elapsed/)).toBeInTheDocument();
    // Scenario name may appear multiple times (header + trace panel) — just verify it's present
    expect(screen.getAllByText(/labor_constraint_wave_risk/).length).toBeGreaterThan(0);
  });

  // Runtime section — requires switching to Runtime tab
  it('shows maiw_operational_status', () => {
    wrap(<ExpertOverlay runtime={baseRuntime as any} demoStatus={baseDemoStatus as any} sseEvents={[]} />);
    switchToRuntime();
    expect(screen.getByTestId('expert-runtime')).toBeInTheDocument();
    expect(screen.getAllByText('HEALTHY').length).toBeGreaterThan(0);
  });

  it('shows uptime formatted', () => {
    wrap(<ExpertOverlay runtime={baseRuntime as any} demoStatus={baseDemoStatus as any} sseEvents={[]} />);
    switchToRuntime();
    expect(screen.getByText('2m 5s')).toBeInTheDocument();
  });

  it('shows uptime dash when not available', () => {
    wrap(<ExpertOverlay runtime={{ ...baseRuntime, uptime_seconds: undefined } as any} demoStatus={baseDemoStatus as any} sseEvents={[]} />);
    switchToRuntime();
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });

  // MCP section — requires switching to Runtime tab
  it('renders MCP domain section', () => {
    wrap(<ExpertOverlay runtime={baseRuntime as any} demoStatus={baseDemoStatus as any} sseEvents={[]} />);
    switchToRuntime();
    expect(screen.getByTestId('expert-mcp')).toBeInTheDocument();
  });

  it('shows all 4 MCP domains', () => {
    wrap(<ExpertOverlay runtime={baseRuntime as any} demoStatus={baseDemoStatus as any} sseEvents={[]} />);
    switchToRuntime();
    const mcp = screen.getByTestId('expert-mcp');
    expect(mcp).toHaveTextContent('inventory');
    expect(mcp).toHaveTextContent('equipment');
    expect(mcp).toHaveTextContent('labor');
    expect(mcp).toHaveTextContent('wave');
  });

  it('shows domain health status', () => {
    wrap(<ExpertOverlay runtime={baseRuntime as any} demoStatus={baseDemoStatus as any} sseEvents={[]} />);
    switchToRuntime();
    expect(screen.getByTestId('expert-mcp')).toHaveTextContent('DEGRADED');
  });

  // Agents section — requires switching to Runtime tab
  it('renders agents section', () => {
    wrap(<ExpertOverlay runtime={baseRuntime as any} demoStatus={baseDemoStatus as any} sseEvents={[]} />);
    switchToRuntime();
    expect(screen.getByTestId('expert-agents')).toBeInTheDocument();
  });

  it('shows all 3 agents and 3 executors', () => {
    wrap(<ExpertOverlay runtime={baseRuntime as any} demoStatus={baseDemoStatus as any} sseEvents={[]} />);
    switchToRuntime();
    const ag = screen.getByTestId('expert-agents');
    expect(ag).toHaveTextContent('Operations agent');
    expect(ag).toHaveTextContent('Equipment agent');
    expect(ag).toHaveTextContent('Safety agent');
    expect(ag).toHaveTextContent('Equipment executor');
    expect(ag).toHaveTextContent('Labor executor');
    expect(ag).toHaveTextContent('Wave executor');
  });

  // SSE section — requires switching to Raw Events tab
  it('renders SSE section', () => {
    wrap(<ExpertOverlay runtime={baseRuntime as any} demoStatus={baseDemoStatus as any} sseEvents={[]} />);
    switchToRawEvents();
    expect(screen.getByTestId('expert-sse')).toBeInTheDocument();
    expect(screen.getByText(/No events yet/)).toBeInTheDocument();
  });

  it('shows SSE events with category and message', () => {
    const events = [
      makeSSE({ category: 'EXECUTE', message: 'labor.allocate', ts: '2026-08-28T10:01:00Z' }),
      makeSSE({ category: 'OBSERVE', message: 'snapshot taken', ts: '2026-08-28T10:00:00Z' }),
    ];
    wrap(<ExpertOverlay runtime={baseRuntime as any} demoStatus={baseDemoStatus as any} sseEvents={events} />);
    switchToRawEvents();
    expect(screen.getByTestId('expert-sse')).toHaveTextContent('EXECUTE');
    expect(screen.getByTestId('expert-sse')).toHaveTextContent('labor.allocate');
  });

  it('shows show-more button when events exceed 10', () => {
    const events = Array.from({ length: 15 }, (_, i) =>
      makeSSE({ id: String(i), category: 'OBSERVE', message: `event-${i}` })
    );
    wrap(<ExpertOverlay runtime={baseRuntime as any} demoStatus={baseDemoStatus as any} sseEvents={events} />);
    switchToRawEvents();
    expect(screen.getByText(/\+5 more/)).toBeInTheDocument();
  });

  it('expands to show all events on click', () => {
    const events = Array.from({ length: 15 }, (_, i) =>
      makeSSE({ id: String(i), category: 'OBSERVE', message: `event-${i}` })
    );
    wrap(<ExpertOverlay runtime={baseRuntime as any} demoStatus={baseDemoStatus as any} sseEvents={events} />);
    switchToRawEvents();
    fireEvent.click(screen.getByText(/\+5 more/));
    expect(screen.getByText('show less')).toBeInTheDocument();
  });

  it('renders with null runtime gracefully', () => {
    wrap(<ExpertOverlay runtime={null} demoStatus={baseDemoStatus as any} sseEvents={[]} />);
    expect(screen.getByTestId('expert-overlay')).toBeInTheDocument();
  });
});
