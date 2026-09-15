/**
 * Phase 17A — Warehouse World Explorer frontend tests.
 *
 * Covers:
 *  1. WORLD appears in DemoShell navigation
 *  2. Clicking WORLD renders WorldShell
 *  3. Switching modes preserves demo state (no extra state calls)
 *  4. Configuration values come from API
 *  5. DataPack metadata renders (checksum prefix)
 *  6. Entity counts render
 *  7. Runtime/scenario renders — SCENARIO ACTIVE badge
 *  8. GRAPH, CHANGES, RAW tabs are disabled/deferred
 *  9. No mutation controls in WORLD
 * 10. API error shows error state
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@mui/material/styles';
import { nvidiaTheme } from '../theme/nvidiaTheme';

import DemoShell from '../pages/DemoShell';
import WorldShell from '../components/world/WorldShell';
import WorldOverview from '../components/world/WorldOverview';
import { worldAPI, WorldConfigResponse, WorldSummaryResponse } from '../services/worldAPI';

// Recharts uses ResizeObserver which is not available in jsdom
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// ── Mock all dependencies of DemoShell ────────────────────────────────────────

jest.mock('../services/demoAPI', () => ({
  demoAPI: {
    listScenarios: () => Promise.resolve([]),
    startScenario: jest.fn(),
    pauseScenario: jest.fn(),
    resumeScenario: jest.fn(),
    resetScenario: jest.fn(),
    getStatusSafe: () => Promise.resolve(null),
    analyze: jest.fn(),
    approvePending: jest.fn(),
    rejectPending: jest.fn(),
    copilotAsk: jest.fn(),
    copilotTurn: jest.fn(),
  },
}));

jest.mock('../services/worldAPI', () => ({
  worldAPI: {
    getConfig: jest.fn(),
    getSummary: jest.fn(),
    getChanges: jest.fn(),
    searchGraph: jest.fn(),
    getGraphEntity: jest.fn(),
    getGraphNeighbors: jest.fn(),
    getLive: jest.fn(),
    getContextByTurn: jest.fn(),
    getEntities: jest.fn(),           // Phase 17F
    getContextSnapshots: jest.fn(),   // Phase 17F
  },
}));

jest.mock('../hooks/useDemoSSE', () => ({
  useDemoSSE: () => ({ events: [], connected: false, error: null, clear: jest.fn() }),
}));

jest.mock('../hooks/useRuntimeStatus', () => ({
  useRuntimeStatus: () => ({
    data: {
      maiw_operational_status: 'HEALTHY',
      model_gateway_status: 'HEALTHY',
      domain_health: { equipment: 'HEALTHY', labor: 'HEALTHY', wave: 'HEALTHY', inventory: 'HEALTHY' },
    },
    isLoading: false,
  }),
}));

jest.mock('../hooks/useDemoStatus', () => ({
  useDemoStatus: () => ({ status: null, isLoading: false, isDemoMode: false, refetch: () => {} }),
}));

jest.mock('../hooks/useCopilotConversation', () => ({
  useCopilotConversation: () => ({
    conversationId: null,
    setConversationId: jest.fn(),
    turns: [],
    setTurns: jest.fn(),
    conversationError: null,
    setConversationError: jest.fn(),
    reset: jest.fn(),
    addSystemCard: jest.fn(),
  }),
}));

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeQC() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
}

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={makeQC()}>
      <ThemeProvider theme={nvidiaTheme}>{children}</ThemeProvider>
    </QueryClientProvider>
  );
}

function buildConfig(overrides: Partial<WorldConfigResponse> = {}): WorldConfigResponse {
  return {
    warehouse: { warehouse_id: 'DC-47', dataset_id: 'ds-abc-001', seed: 42 },
    layout: { zone_count: 8, location_count: 3200, dock_door_count: 12 },
    workforce: { workers_per_shift: 30, shift_count: 3, total_workers: 90, skills: ['pick', 'pack'] },
    equipment: { agv_count: 10, forklift_count: 5, conveyor_count: 2, total: 17 },
    commerce: { sku_count: 5000, low_stock_pct: 0.05, daily_order_count: 800, lines_per_order_mean: 3.2 },
    operations: { active_wave_count: 2, task_count: 240, strategy: 'FIFO' },
    generation: {
      schema_version: '1.0',
      generator_version: '0.9.0',
      pack_format: 'parquet',
      semantic_checksum: 'abcd1234efgh5678',
      total_entities: 4000,
      total_edges: 12000,
      total_events: 500,
      graph_available: true,
    },
    ...overrides,
  };
}

function buildSummary(overrides: Partial<WorldSummaryResponse> = {}): WorldSummaryResponse {
  return {
    datapack: {
      dataset_id: 'ds-abc-001',
      warehouse_id: 'DC-47',
      seed: 42,
      schema_version: '1.0',
      semantic_checksum: 'abcd1234efgh5678',
      total_entities: 4000,
      total_edges: 12000,
      total_events: 500,
      pack_format: 'parquet',
      generator_version: '0.9.0',
      immutable: true,
      loaded: true,
    },
    graph: {
      entity_counts: { Worker: 90, Location: 3200, Equipment: 17, Wave: 2, Task: 240 },
      relationship_counts: { ASSIGNED_TO: 200, LOCATED_IN: 3200 },
      total_entities: 4000,
      total_relationships: 12000,
      event_count: 500,
      available: true,
    },
    scenario: {
      scenario_id: null,
      name: null,
      severity: null,
      active: false,
    },
    runtime: {
      status: 'READY',
      elapsed_seconds: null,
      clock_iso: null,
    },
    ...overrides,
  };
}

const mockGetConfig = worldAPI.getConfig as jest.Mock;
const mockGetSummary = worldAPI.getSummary as jest.Mock;

beforeEach(() => {
  jest.clearAllMocks();
  mockGetConfig.mockResolvedValue(buildConfig());
  mockGetSummary.mockResolvedValue(buildSummary());
});

// ── 1. WORLD appears in DemoShell navigation ──────────────────────────────────

describe('Phase 17A — World Explorer', () => {
  it('WORLD button appears in DemoShell ModeSwitcher', () => {
    render(<DemoShell />, { wrapper: Wrapper });
    expect(screen.getByRole('button', { name: /world/i })).toBeInTheDocument();
  });

  // ── 2. Clicking WORLD renders WorldShell ─────────────────────────────────────

  it('clicking WORLD button renders WorldShell with OVERVIEW tab', () => {
    render(<DemoShell />, { wrapper: Wrapper });
    fireEvent.click(screen.getByRole('button', { name: /world/i }));
    expect(screen.getByTestId('world-shell')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /overview/i })).toBeInTheDocument();
  });

  // ── 3. Switching modes preserves demo state ───────────────────────────────────

  it('switching to WORLD does not call startScenario or resetScenario', () => {
    const { demoAPI: mockDemoAPI } = require('../services/demoAPI');
    render(<DemoShell />, { wrapper: Wrapper });
    fireEvent.click(screen.getByRole('button', { name: /world/i }));
    expect(mockDemoAPI.startScenario).not.toHaveBeenCalled();
    expect(mockDemoAPI.resetScenario).not.toHaveBeenCalled();
  });

  // ── 4. Configuration values come from API ────────────────────────────────────

  it('renders warehouse ID from config API', async () => {
    render(<WorldOverview />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getAllByText(/DC-47/).length).toBeGreaterThanOrEqual(1);
    });
  });

  // ── 5. DataPack metadata renders (checksum prefix) ───────────────────────────

  it('renders checksum prefix from summary API', async () => {
    render(<WorldOverview />, { wrapper: Wrapper });
    await waitFor(() => {
      // Checksum 'abcd1234efgh5678' should show as 'abcd1234...'
      expect(screen.getByText(/abcd1234\.\.\./)).toBeInTheDocument();
    });
  });

  // ── 6. Entity counts render ───────────────────────────────────────────────────

  it('renders total entity count from graph summary', async () => {
    render(<WorldOverview />, { wrapper: Wrapper });
    await waitFor(() => {
      // 4,000 total entities should appear
      expect(screen.getAllByText(/4,000/).length).toBeGreaterThanOrEqual(1);
    });
  });

  // ── 7. SCENARIO ACTIVE badge renders when scenario is active ─────────────────

  it('renders SCENARIO ACTIVE badge when scenario is active', async () => {
    mockGetSummary.mockResolvedValue(
      buildSummary({
        scenario: {
          scenario_id: 'scen-001',
          name: 'labor-constraint-wave-risk',
          severity: 'HIGH',
          active: true,
        },
      }),
    );
    render(<WorldOverview />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByText(/SCENARIO ACTIVE/i)).toBeInTheDocument();
    });
  });

  // ── 8. RAW tab is now enabled (Phase 17F); GRAPH and CHANGES remain enabled ──

  it('RAW tab is enabled in WorldShell (Phase 17F)', () => {
    const { worldAPI: mockWorldAPI } = require('../services/worldAPI');
    mockWorldAPI.getEntities.mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0, has_more: false, entity_type_filter: null });
    mockWorldAPI.getContextSnapshots.mockResolvedValue({ snapshots: [], total: 0, store_note: '' });
    render(<WorldShell />, { wrapper: Wrapper });
    const rawBtn = screen.getByRole('button', { name: /raw/i });
    expect(rawBtn).not.toBeDisabled();
    // GRAPH remains enabled
    const graphBtn = screen.getByRole('button', { name: /^graph$/i });
    expect(graphBtn).not.toBeDisabled();
  });

  // ── 9. No mutation controls in WORLD ─────────────────────────────────────────

  it('WorldOverview has no approve/execute/reject/start/inject buttons', async () => {
    render(<WorldOverview />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.queryByText(/^(approve|execute|reject|start|inject)$/i)).not.toBeInTheDocument();
    });
    // Check no buttons with mutation labels
    const buttons = screen.queryAllByRole('button');
    for (const btn of buttons) {
      expect(btn.textContent).not.toMatch(/approve|execute|reject|inject/i);
    }
  });

  // ── 10. API error shows error state ──────────────────────────────────────────

  it('shows error state when both world API calls fail', async () => {
    mockGetConfig.mockRejectedValue(new Error('Network error'));
    mockGetSummary.mockRejectedValue(new Error('Network error'));
    render(<WorldOverview />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByTestId('world-overview-error')).toBeInTheDocument();
    });
  });
});
