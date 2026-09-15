/**
 * Phase 17D — WorldLive component tests.
 *
 * Covers:
 *  1.  LIVE selector is enabled in WorldViewSwitcher
 *  2.  Runtime summary panel renders when LIVE view is active
 *  3.  No-action empty state (no changed entities, no execution)
 *  4.  Successful delta — last_execution with EXECUTED outcome shown
 *  5.  Changed entity card renders entity label and type
 *  6.  KPI delta panel renders when execution record exists
 *  7.  DataPack immutability indicator always shown
 *  8a. Pending outcome shows NO RUNTIME MUTATION banner
 *  8b. Rejected outcome shows NO RUNTIME MUTATION banner
 *  8c. UNKNOWN outcome shows RUNTIME STATE UNCERTAIN banner
 *  9.  No mutation controls rendered in WorldLive
 * 10.  API failure shows error state, not exception
 */

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@mui/material/styles';
import { nvidiaTheme } from '../theme/nvidiaTheme';

import WorldShell from '../components/world/WorldShell';
import WorldLive from '../components/world/WorldLive';
import { worldAPI, WorldLiveResponse } from '../services/worldAPI';

// ── Polyfill ──────────────────────────────────────────────────────────────────

global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// ── Mock worldAPI ─────────────────────────────────────────────────────────────

jest.mock('../services/worldAPI', () => ({
  worldAPI: {
    getConfig: jest.fn(),
    getSummary: jest.fn(),
    getChanges: jest.fn(),
    searchGraph: jest.fn(),
    getGraphEntity: jest.fn(),
    getGraphNeighbors: jest.fn(),
    getLive: jest.fn(),
  },
}));

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

function buildLive(overrides: Partial<WorldLiveResponse> = {}): WorldLiveResponse {
  return {
    warehouse_id: 'DC-47',
    dataset_id: 'dc47-demo-v1',
    base_checksum: 'abcdef1234567890abcd',
    scenario_id: 'labor-constraint-wave-risk',
    scenario_active: true,
    runtime_status: 'ACTIVE',
    world_clock: '2026-08-23T10:30:00+00:00',
    summary: {
      workers: 90,
      idle_workers: 12,
      equipment: 17,
      available_equipment: 9,
      tasks: 240,
      pending_tasks: 80,
      in_progress_tasks: 45,
    },
    changed_entities: [],
    last_execution: null,
    ...overrides,
  };
}

const mockGetLive = worldAPI.getLive as jest.Mock;
const mockGetConfig = worldAPI.getConfig as jest.Mock;
const mockGetSummary = worldAPI.getSummary as jest.Mock;
const mockGetChanges = worldAPI.getChanges as jest.Mock;

const baseConfig = {
  warehouse: { warehouse_id: 'DC-47', dataset_id: 'dc47-demo-v1', seed: 42 },
  layout: { zone_count: 8, location_count: 3200, dock_door_count: 12 },
  workforce: { workers_per_shift: 30, shift_count: 3, total_workers: 90, skills: ['pick', 'pack'] },
  equipment: { agv_count: 10, forklift_count: 5, conveyor_count: 2, total: 17 },
  commerce: { sku_count: 5000, low_stock_pct: 0.05, daily_order_count: 800, lines_per_order_mean: 3.2 },
  operations: { active_wave_count: 2, task_count: 240, strategy: 'FIFO' },
  generation: {
    schema_version: '1.0', generator_version: '0.9.0', pack_format: 'parquet',
    semantic_checksum: 'abcdef1234567890abcd', total_entities: 4000,
    total_edges: 12000, total_events: 500, graph_available: true,
  },
};

const baseSummary = {
  datapack: {
    dataset_id: 'dc47-demo-v1', warehouse_id: 'DC-47', seed: 42, schema_version: '1.0',
    semantic_checksum: 'abcdef1234567890abcd', total_entities: 4000, total_edges: 12000,
    total_events: 500, pack_format: 'parquet', generator_version: '0.9.0',
    immutable: true, loaded: true,
  },
  graph: {
    entity_counts: { worker: 90 }, relationship_counts: { ASSIGNED_TO: 200 },
    total_entities: 4000, total_relationships: 12000, event_count: 500, available: true,
  },
  scenario: { scenario_id: null, name: null, severity: null, active: false },
  runtime: { status: 'READY', elapsed_seconds: null, clock_iso: null },
};

beforeEach(() => {
  jest.clearAllMocks();
  mockGetConfig.mockResolvedValue(baseConfig);
  mockGetSummary.mockResolvedValue(baseSummary);
  mockGetChanges.mockResolvedValue({
    warehouse_id: 'DC-47', dataset_id: 'dc47-demo-v1',
    scenario_id: null, scenario_name: null, scenario_active: false,
    scenario_severity: 'NOMINAL', base_checksum: 'abcdef1234567890abcd',
    world_clock_seconds: 0, overlay_event_count: 0, affected_entity_count: 0,
    events: [], affected_entities: [],
  });
  mockGetLive.mockResolvedValue(buildLive());
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('Phase 17D — WorldLive', () => {
  // 1. LIVE selector enabled
  it('LIVE selector is enabled in WorldViewSwitcher', () => {
    render(<WorldShell />, { wrapper: Wrapper });
    const liveBtn = screen.getByRole('button', { name: /live/i });
    expect(liveBtn).not.toBeDisabled();
    expect(liveBtn).toHaveAttribute('aria-disabled', 'false');
  });

  // 2. Runtime summary renders
  it('renders runtime summary when LIVE view is active', async () => {
    render(<WorldShell />, { wrapper: Wrapper });
    const liveBtn = screen.getByRole('button', { name: /live/i });
    fireEvent.click(liveBtn);
    await waitFor(() => {
      expect(screen.getByTestId('live-runtime-summary')).toBeInTheDocument();
    });
  });

  // 3. No-action empty state
  it('shows no-changed-entities state when changed_entities is empty', async () => {
    mockGetLive.mockResolvedValue(buildLive({ changed_entities: [], last_execution: null }));
    render(<WorldLive />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByTestId('no-changed-entities')).toBeInTheDocument();
    });
  });

  // 4. Successful delta — EXECUTED outcome
  it('shows EXECUTED outcome when last_execution outcome is EXECUTED', async () => {
    mockGetLive.mockResolvedValue(buildLive({
      last_execution: {
        execution_id: 'exec-001',
        trace_id: 'trace-abc',
        outcome: 'EXECUTED',
        pre_kpi: { pending_backlog: 10 },
        post_kpi: { pending_backlog: 7 },
        kpi_delta: { labor_utilization_pct: 15.0 },  // positive delta → IMPROVED
      },
    }));
    render(<WorldLive />, { wrapper: Wrapper });
    await waitFor(() => {
      // Badge shows "EXECUTED + IMPROVED" (positive delta) — getAllByText avoids multi-match error
      const badges = screen.getAllByText(/EXECUTED/i);
      expect(badges.length).toBeGreaterThan(0);
    });
  });

  // 5. Changed entity card
  it('renders changed entity card with label and type', async () => {
    mockGetLive.mockResolvedValue(buildLive({
      changed_entities: [{
        entity_id: 'worker-001',
        entity_type: 'worker',
        label: 'Alice Smith',
        changed_fields: [{ field: 'status', before_value: 'active', after_value: 'on_leave' }],
        note: 'changed from scenario initial state',
      }],
    }));
    render(<WorldLive />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByTestId('changed-entity-card')).toBeInTheDocument();
      expect(screen.getByText('Alice Smith')).toBeInTheDocument();
    });
  });

  // 6. KPI delta panel
  it('renders KPI delta panel when execution record exists', async () => {
    mockGetLive.mockResolvedValue(buildLive({
      last_execution: {
        execution_id: 'exec-002',
        trace_id: 'trace-def',
        outcome: 'EXECUTED',
        pre_kpi: { labor_utilization_pct: 65.0 },
        post_kpi: { labor_utilization_pct: 82.0 },
        kpi_delta: { labor_utilization_pct: 17.0 },
      },
    }));
    render(<WorldLive />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByTestId('kpi-delta-panel')).toBeInTheDocument();
    });
  });

  // 7. DataPack immutability indicator
  it('always shows DataPack immutability indicator', async () => {
    render(<WorldLive />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByTestId('datapack-immutable-indicator')).toBeInTheDocument();
      expect(screen.getByText(/DATAPACK IMMUTABLE/i)).toBeInTheDocument();
    });
  });

  // 8a. Pending → NO RUNTIME MUTATION banner
  it('shows NO RUNTIME MUTATION banner for PENDING outcome', async () => {
    mockGetLive.mockResolvedValue(buildLive({
      last_execution: {
        execution_id: null,
        trace_id: null,
        outcome: 'PENDING',
        pre_kpi: null,
        post_kpi: null,
        kpi_delta: null,
      },
    }));
    render(<WorldLive />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByTestId('outcome-banner')).toBeInTheDocument();
      expect(screen.getByText(/NO RUNTIME MUTATION/i)).toBeInTheDocument();
    });
  });

  // 8b. Rejected → NO RUNTIME MUTATION banner
  it('shows NO RUNTIME MUTATION banner for REJECTED outcome', async () => {
    mockGetLive.mockResolvedValue(buildLive({
      last_execution: {
        execution_id: 'exec-rej',
        trace_id: 'trace-rej',
        outcome: 'REJECTED',
        pre_kpi: null,
        post_kpi: null,
        kpi_delta: null,
      },
    }));
    render(<WorldLive />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByTestId('outcome-banner')).toBeInTheDocument();
      expect(screen.getByText(/NO RUNTIME MUTATION/i)).toBeInTheDocument();
    });
  });

  // 8c. UNKNOWN → RUNTIME STATE UNCERTAIN banner
  it('shows RUNTIME STATE UNCERTAIN banner for UNKNOWN outcome', async () => {
    mockGetLive.mockResolvedValue(buildLive({
      last_execution: {
        execution_id: 'exec-unk',
        trace_id: 'trace-unk',
        outcome: 'UNKNOWN',
        pre_kpi: null,
        post_kpi: null,
        kpi_delta: null,
      },
    }));
    render(<WorldLive />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByTestId('outcome-banner')).toBeInTheDocument();
      expect(screen.getByText(/RUNTIME STATE UNCERTAIN/i)).toBeInTheDocument();
    });
  });

  // 9. No mutation controls
  it('renders no mutation controls (no buttons that could modify state)', async () => {
    render(<WorldLive />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByTestId('world-live')).toBeInTheDocument();
    });
    // WorldLive should only have read-only content — no approve/reject/execute buttons
    expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /execute/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /reject/i })).not.toBeInTheDocument();
  });

  // 10. API failure
  it('shows error state when API fails instead of throwing', async () => {
    mockGetLive.mockRejectedValue(new Error('Network error'));
    render(<WorldLive />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByText(/LIVE data unavailable/i)).toBeInTheDocument();
    });
    // Must not show unhandled exception
    expect(screen.queryByText(/TypeError/)).not.toBeInTheDocument();
    expect(screen.queryByText(/undefined/)).not.toBeInTheDocument();
  });

  // Bonus: live counter grid shows correct counts
  it('renders live summary counters with correct values', async () => {
    mockGetLive.mockResolvedValue(buildLive({
      summary: {
        workers: 90, idle_workers: 12, equipment: 17, available_equipment: 9,
        tasks: 240, pending_tasks: 80, in_progress_tasks: 45,
      },
    }));
    render(<WorldLive />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByTestId('live-counters')).toBeInTheDocument();
      // Workers total
      expect(screen.getByText('90')).toBeInTheDocument();
    });
  });

  // Bonus: changed entity before/after values shown
  it('renders before and after values for changed fields', async () => {
    mockGetLive.mockResolvedValue(buildLive({
      changed_entities: [{
        entity_id: 'worker-001',
        entity_type: 'worker',
        label: 'Bob Jones',
        changed_fields: [{ field: 'status', before_value: 'active', after_value: 'on_leave' }],
        note: 'changed from scenario initial state',
      }],
    }));
    render(<WorldLive />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByText('active')).toBeInTheDocument();
      expect(screen.getByText('on_leave')).toBeInTheDocument();
    });
  });
});
