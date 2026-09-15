/**
 * Phase 17B — WorldChanges component tests.
 *
 * Covers:
 *  1. CHANGES tab is enabled in WorldShell
 *  2. BASE selector renders in WorldShell
 *  3. SCENARIO selector renders in WorldShell
 *  4. LIVE selector is enabled (Phase 17D)
 *  5. WorldChanges shows no-scenario state when scenario_active=false
 *  6. WorldChanges shows scenario identity when active
 *  7. WorldChanges shows event timeline when scenario active
 *  8. WorldChanges shows affected entity cards
 *  9. BASE view shows immutable datapack message
 * 10. Switching modes preserves state (no resetScenario call)
 * 11. Checksum shown in BASE view
 * 12. No mutation controls in WorldChanges
 * 13. API error shows error state
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@mui/material/styles';
import { nvidiaTheme } from '../theme/nvidiaTheme';

import DemoShell from '../pages/DemoShell';
import WorldShell from '../components/world/WorldShell';
import WorldChanges from '../components/world/WorldChanges';
import { worldAPI, WorldChangesResponse } from '../services/worldAPI';

// Recharts uses ResizeObserver which is not available in jsdom
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// ── Mock all dependencies ─────────────────────────────────────────────────────

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

function buildChanges(overrides: Partial<WorldChangesResponse> = {}): WorldChangesResponse {
  return {
    warehouse_id: 'DC-47',
    dataset_id: 'dc47-demo-v1',
    scenario_id: null,
    scenario_name: null,
    scenario_active: false,
    scenario_severity: 'NOMINAL',
    base_checksum: 'abcdef1234567890',
    world_clock_seconds: 0,
    overlay_event_count: 0,
    affected_entity_count: 0,
    events: [],
    affected_entities: [],
    ...overrides,
  };
}

const mockGetConfig = worldAPI.getConfig as jest.Mock;
const mockGetSummary = worldAPI.getSummary as jest.Mock;
const mockGetChanges = worldAPI.getChanges as jest.Mock;

beforeEach(() => {
  jest.clearAllMocks();
  mockGetConfig.mockResolvedValue({
    warehouse: { warehouse_id: 'DC-47', dataset_id: 'dc47-demo-v1', seed: 42 },
    layout: { zone_count: 8, location_count: 3200, dock_door_count: 12 },
    workforce: { workers_per_shift: 30, shift_count: 3, total_workers: 90, skills: ['pick', 'pack'] },
    equipment: { agv_count: 10, forklift_count: 5, conveyor_count: 2, total: 17 },
    commerce: { sku_count: 5000, low_stock_pct: 0.05, daily_order_count: 800, lines_per_order_mean: 3.2 },
    operations: { active_wave_count: 2, task_count: 240, strategy: 'FIFO' },
    generation: {
      schema_version: '1.0',
      generator_version: '0.9.0',
      pack_format: 'parquet',
      semantic_checksum: 'abcdef1234567890',
      total_entities: 4000,
      total_edges: 12000,
      total_events: 500,
      graph_available: true,
    },
  });
  mockGetSummary.mockResolvedValue({
    datapack: {
      dataset_id: 'dc47-demo-v1',
      warehouse_id: 'DC-47',
      seed: 42,
      schema_version: '1.0',
      semantic_checksum: 'abcdef1234567890',
      total_entities: 4000,
      total_edges: 12000,
      total_events: 500,
      pack_format: 'parquet',
      generator_version: '0.9.0',
      immutable: true,
      loaded: true,
    },
    graph: {
      entity_counts: { Worker: 90, Location: 3200 },
      relationship_counts: { ASSIGNED_TO: 200 },
      total_entities: 4000,
      total_relationships: 12000,
      event_count: 500,
      available: true,
    },
    scenario: { scenario_id: null, name: null, severity: null, active: false },
    runtime: { status: 'READY', elapsed_seconds: null, clock_iso: null },
  });
  mockGetChanges.mockResolvedValue(buildChanges());
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('Phase 17B — WorldChanges', () => {
  // 1. CHANGES tab is enabled
  it('CHANGES tab is enabled in WorldShell', () => {
    render(<WorldShell />, { wrapper: Wrapper });
    const changesBtn = screen.getByRole('button', { name: /changes/i });
    expect(changesBtn).not.toBeDisabled();
  });

  // 2. BASE selector renders
  it('BASE selector renders in WorldShell', () => {
    render(<WorldShell />, { wrapper: Wrapper });
    expect(screen.getByRole('button', { name: /base/i })).toBeInTheDocument();
  });

  // 3. SCENARIO selector renders
  it('SCENARIO selector renders in WorldShell', () => {
    render(<WorldShell />, { wrapper: Wrapper });
    expect(screen.getByRole('button', { name: /scenario/i })).toBeInTheDocument();
  });

  // 4. LIVE selector is enabled (Phase 17D: LIVE view implemented)
  it('LIVE selector is enabled', () => {
    render(<WorldShell />, { wrapper: Wrapper });
    const liveBtn = screen.getByRole('button', { name: /live/i });
    expect(liveBtn).not.toBeDisabled();
  });

  // 5. No-scenario state when scenario_active=false
  it('WorldChanges shows no-scenario state when scenario_active=false', async () => {
    mockGetChanges.mockResolvedValue(buildChanges({ scenario_active: false }));
    render(<WorldChanges worldView="scenario" />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByTestId('no-scenario-state')).toBeInTheDocument();
    });
  });

  // 6. Scenario identity shown when active
  it('WorldChanges shows scenario identity when active', async () => {
    mockGetChanges.mockResolvedValue(
      buildChanges({
        scenario_active: true,
        scenario_id: 'scen-001',
        scenario_name: 'labor-constraint-wave-risk',
        scenario_severity: 'HIGH',
        world_clock_seconds: 300,
      }),
    );
    render(<WorldChanges worldView="scenario" />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByText(/labor-constraint-wave-risk/i)).toBeInTheDocument();
    });
  });

  // 7. Event timeline shown when scenario active
  it('WorldChanges shows event timeline when scenario active', async () => {
    mockGetChanges.mockResolvedValue(
      buildChanges({
        scenario_active: true,
        scenario_name: 'test-scenario',
        scenario_severity: 'MODERATE',
        overlay_event_count: 2,
        events: [
          {
            event_id: 'evt-001',
            event_type: 'WORKER_ABSENCE',
            entity_id: 'w-001',
            entity_type: 'worker',
            entity_label: 'Alice Smith',
            sim_time_offset_seconds: 0,
            before_state: 'ACTIVE',
            after_state: 'ABSENT',
            label: 'Worker absence',
            payload: {},
          },
          {
            event_id: 'evt-002',
            event_type: 'EQUIPMENT_FAILURE',
            entity_id: 'eq-005',
            entity_type: 'equipment',
            entity_label: 'AGV-05',
            sim_time_offset_seconds: 300,
            before_state: 'OPERATIONAL',
            after_state: 'FAILED',
            label: 'Equipment failure',
            payload: {},
          },
        ],
      }),
    );
    render(<WorldChanges worldView="scenario" />, { wrapper: Wrapper });
    await waitFor(() => {
      const items = screen.getAllByTestId('scenario-event-item');
      expect(items.length).toBeGreaterThanOrEqual(1);
    });
  });

  // 8. Affected entity cards shown
  it('WorldChanges shows affected entity cards', async () => {
    mockGetChanges.mockResolvedValue(
      buildChanges({
        scenario_active: true,
        scenario_name: 'test-scenario',
        scenario_severity: 'HIGH',
        affected_entity_count: 1,
        affected_entities: [
          {
            entity_id: 'w-001',
            entity_type: 'worker',
            entity_label: 'Alice Smith',
            disruption_type: 'ABSENCE',
            before_state: 'ACTIVE',
            after_state: 'ABSENT',
            severity: 'HIGH',
          },
        ],
      }),
    );
    render(<WorldChanges worldView="scenario" />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByTestId('affected-entity-card')).toBeInTheDocument();
    });
  });

  // 9. BASE view shows IMMUTABLE
  it('BASE view shows immutable datapack message', async () => {
    mockGetChanges.mockResolvedValue(buildChanges({ base_checksum: 'deadbeef1234abcd' }));
    render(<WorldChanges worldView="base" />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByText(/IMMUTABLE/i)).toBeInTheDocument();
    });
  });

  // 10. Switching modes preserves state (no resetScenario call)
  it('switching to WORLD and back does not call resetScenario', () => {
    const { demoAPI: mockDemoAPI } = require('../services/demoAPI');
    render(<DemoShell />, { wrapper: Wrapper });
    fireEvent.click(screen.getByRole('button', { name: /world/i }));
    fireEvent.click(screen.getByRole('button', { name: /operations/i }));
    expect(mockDemoAPI.resetScenario).not.toHaveBeenCalled();
  });

  // 11. Checksum shown in BASE view
  it('checksum shown in BASE view', async () => {
    mockGetChanges.mockResolvedValue(buildChanges({ base_checksum: 'deadbeef1234abcd' }));
    render(<WorldChanges worldView="base" />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByText(/deadbeef/i)).toBeInTheDocument();
    });
  });

  // 12. No mutation controls in WorldChanges
  it('no mutation controls in WorldChanges', async () => {
    mockGetChanges.mockResolvedValue(buildChanges());
    render(<WorldChanges worldView="base" />, { wrapper: Wrapper });
    await waitFor(() => {
      const buttons = screen.queryAllByRole('button');
      for (const btn of buttons) {
        expect(btn.textContent).not.toMatch(/approve|execute|reject/i);
      }
    });
  });

  // 13. API error shows error state
  it('API error shows error state', async () => {
    mockGetChanges.mockRejectedValue(new Error('Network error'));
    render(<WorldChanges worldView="scenario" />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByTestId('world-changes-error')).toBeInTheDocument();
    });
  });
});
