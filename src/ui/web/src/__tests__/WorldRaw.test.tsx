/**
 * Phase 17F — WorldRaw developer inspection surface tests.
 *
 * Covers:
 *  R1.  WorldRaw renders (data-testid="world-raw")
 *  R2.  MANIFEST section renders structured DataPack fields
 *  R3.  VIEW RAW JSON toggle reveals raw JSON block
 *  R4.  ENTITIES section renders with type selector
 *  R5.  Entity list renders when data loads
 *  R6.  Entity type selector triggers new query
 *  R7.  Pagination controls render when multiple pages exist
 *  R8.  Context snapshots section renders
 *  R9.  Snapshot list renders items from API
 *  R10. Error pane shown when config API fails
 *  R11. Error pane shown when entities API fails
 *  R12. Error pane shown when snapshots API fails
 *  R13. Clicking entity row marks it selected
 *  R14. Clicking snapshot row calls onSelectSnapshot
 *  R15. RAW tab is accessible from WorldShell (enabled in 17F)
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@mui/material/styles';
import { nvidiaTheme } from '../theme/nvidiaTheme';

import WorldRaw from '../components/world/WorldRaw';
import WorldShell from '../components/world/WorldShell';
import { worldAPI } from '../services/worldAPI';

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
    getContextByTurn: jest.fn(),
    getEntities: jest.fn(),
    getContextSnapshots: jest.fn(),
  },
}));

global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

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

const mockGetConfig = worldAPI.getConfig as jest.Mock;
const mockGetSummary = worldAPI.getSummary as jest.Mock;
const mockGetEntities = worldAPI.getEntities as jest.Mock;
const mockGetContextSnapshots = worldAPI.getContextSnapshots as jest.Mock;
const mockGetGraphEntity = worldAPI.getGraphEntity as jest.Mock;

function buildConfig() {
  return {
    warehouse: { warehouse_id: 'DC-47', dataset_id: 'dc47-demo-v1', seed: 42 },
    layout: { zone_count: 8, location_count: 3200, dock_door_count: 12 },
    workforce: { workers_per_shift: 30, shift_count: 3, total_workers: 90, skills: [] },
    equipment: { agv_count: 10, forklift_count: 5, conveyor_count: 2, total: 17 },
    commerce: { sku_count: 5000, low_stock_pct: 0.05, daily_order_count: 800, lines_per_order_mean: 3.2 },
    operations: { active_wave_count: 2, task_count: 240, strategy: 'FIFO' },
    generation: {
      schema_version: '1.0',
      generator_version: '0.1.0',
      pack_format: 'maiw-datapack-v1',
      semantic_checksum: 'sha256:abcdef1234567890',
      total_entities: 25000,
      total_edges: 80000,
      total_events: 1200,
      graph_available: true,
    },
  };
}

function buildEntityPage(count = 3, has_more = false) {
  return {
    items: Array.from({ length: count }, (_, i) => ({
      entity_id: `worker-${i.toString().padStart(4, '0')}`,
      entity_type: 'worker',
      label: `Worker ${i}`,
      key_state: { status: 'active', role: 'picker' },
    })),
    total: count,
    limit: 20,
    offset: 0,
    has_more,
    entity_type_filter: 'worker',
  };
}

function buildSnapshotList(count = 2) {
  return {
    snapshots: Array.from({ length: count }, (_, i) => ({
      context_snapshot_id: `ctx-${i}`,
      turn_id: `turn-${i}`,
      trace_id: `trace-${i}`,
      focus_entity_id: 'wave-017',
      focus_entity_type: 'wave',
      focus_label: 'Wave 17',
      entity_count: 12,
      captured_at: new Date(Date.now() - i * 60000).toISOString(),
      truncated: false,
    })),
    total: count,
    store_note: 'Process-local snapshots.',
  };
}

beforeEach(() => {
  jest.clearAllMocks();
  mockGetConfig.mockResolvedValue(buildConfig());
  mockGetSummary.mockResolvedValue({
    datapack: { dataset_id: 'dc47-demo-v1', warehouse_id: 'DC-47', seed: 42,
      schema_version: '1.0', semantic_checksum: 'sha256:abc', total_entities: 25000,
      total_edges: 80000, total_events: 1200, pack_format: 'maiw-datapack-v1',
      generator_version: '0.1.0', immutable: true, loaded: true },
    graph: { entity_counts: {}, relationship_counts: {}, total_entities: 25000,
      total_relationships: 80000, event_count: 1200, available: true },
    scenario: { scenario_id: null, name: null, severity: null, active: false },
    runtime: { status: 'READY', elapsed_seconds: null, clock_iso: null },
  });
  mockGetEntities.mockResolvedValue(buildEntityPage(3));
  mockGetContextSnapshots.mockResolvedValue(buildSnapshotList(2));
  mockGetGraphEntity.mockResolvedValue({
    entity_id: 'worker-0000',
    entity_type: 'worker',
    label: 'Worker 0',
    attributes: { role: 'picker', skills: '' },
    incoming_count: 1,
    outgoing_count: 2,
    scenario_affected: false,
    scenario_severity: null,
    direct_relationships: [],
  });
});

// ── R1. WorldRaw renders ──────────────────────────────────────────────────────

describe('Phase 17F — WorldRaw', () => {
  it('R1: renders world-raw root element', () => {
    render(<WorldRaw />, { wrapper: Wrapper });
    expect(screen.getByTestId('world-raw')).toBeInTheDocument();
  });

  // ── R2. Manifest renders ────────────────────────────────────────────────────

  it('R2: manifest section renders DataPack fields', async () => {
    render(<WorldRaw />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByTestId('manifest-section')).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByText('DC-47')).toBeInTheDocument();
      expect(screen.getByText('dc47-demo-v1')).toBeInTheDocument();
    });
  });

  // ── R3. Raw JSON toggle ─────────────────────────────────────────────────────

  it('R3: VIEW RAW JSON toggle reveals raw JSON block', async () => {
    render(<WorldRaw />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByTestId('manifest-raw-toggle')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('manifest-raw-json')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('manifest-raw-toggle'));
    expect(screen.getByTestId('manifest-raw-json')).toBeInTheDocument();
  });

  // ── R4. Entity type selector ────────────────────────────────────────────────

  it('R4: entity type selector renders with all types', async () => {
    render(<WorldRaw />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByTestId('entity-type-selector')).toBeInTheDocument();
    });
    const selector = screen.getByTestId('entity-type-selector') as HTMLSelectElement;
    expect(selector.options.length).toBeGreaterThan(5);
  });

  // ── R5. Entity list renders ─────────────────────────────────────────────────

  it('R5: entity list renders items from API', async () => {
    render(<WorldRaw />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByTestId('entity-list')).toBeInTheDocument();
    });
    expect(screen.getByText('Worker 0')).toBeInTheDocument();
    expect(screen.getByText('Worker 1')).toBeInTheDocument();
  });

  // ── R6. Entity type selector change triggers new query ──────────────────────

  it('R6: changing entity type selector calls getEntities with new type', async () => {
    render(<WorldRaw />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByTestId('entity-type-selector')).toBeInTheDocument();
    });
    mockGetEntities.mockResolvedValue(buildEntityPage(1));
    fireEvent.change(screen.getByTestId('entity-type-selector'), { target: { value: 'Wave' } });
    await waitFor(() => {
      expect(mockGetEntities).toHaveBeenCalledWith('Wave', expect.any(Number), 0);
    });
  });

  // ── R7. Pagination controls ─────────────────────────────────────────────────

  it('R7: pagination controls render when has_more is true', async () => {
    // 60 total, limit 20, so has_more = true
    mockGetEntities.mockResolvedValue({
      items: Array.from({ length: 20 }, (_, i) => ({
        entity_id: `worker-${i}`,
        entity_type: 'worker',
        label: `Worker ${i}`,
        key_state: {},
      })),
      total: 60,
      limit: 20,
      offset: 0,
      has_more: true,
      entity_type_filter: null,
    });
    render(<WorldRaw />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByTestId('pagination-controls')).toBeInTheDocument();
    });
    expect(screen.getByText(/NEXT/)).toBeInTheDocument();
    expect(screen.getByText(/PREV/)).toBeInTheDocument();
  });

  // ── R8. Context snapshots section renders ───────────────────────────────────

  it('R8: context snapshots section renders', async () => {
    render(<WorldRaw />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByTestId('context-snapshots-section')).toBeInTheDocument();
    });
  });

  // ── R9. Snapshot list renders items ────────────────────────────────────────

  it('R9: snapshot list renders items from API', async () => {
    render(<WorldRaw />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByTestId('snapshot-list')).toBeInTheDocument();
    });
    expect(screen.getAllByText('Wave 17').length).toBeGreaterThanOrEqual(1);
  });

  // ── R10–R12. Error states ───────────────────────────────────────────────────

  it('R10: manifest error pane shown when config API fails', async () => {
    mockGetConfig.mockRejectedValue(new Error('Config unavailable'));
    render(<WorldRaw />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByText(/DataPack manifest unavailable/i)).toBeInTheDocument();
    });
  });

  it('R11: entities error pane shown when entities API fails', async () => {
    mockGetEntities.mockRejectedValue(new Error('Graph unavailable'));
    render(<WorldRaw />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByText(/Operational graph unavailable/i)).toBeInTheDocument();
    });
  });

  it('R12: snapshots error pane shown when snapshots API fails', async () => {
    mockGetContextSnapshots.mockRejectedValue(new Error('Store unavailable'));
    render(<WorldRaw />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByText(/Context snapshot store unavailable/i)).toBeInTheDocument();
    });
  });

  // ── R13. Entity row selection ───────────────────────────────────────────────

  it('R13: clicking entity row marks it selected (aria-pressed or visual)', async () => {
    render(<WorldRaw />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByTestId('entity-list')).toBeInTheDocument();
    });
    const firstRow = screen.getByTestId('entity-row-worker-0000');
    fireEvent.click(firstRow);
    // After click, NodeInspector should appear
    await waitFor(() => {
      expect(screen.getByTestId('node-inspector')).toBeInTheDocument();
    });
  });

  // ── R14. Snapshot row calls onSelectSnapshot ────────────────────────────────

  it('R14: clicking snapshot row calls onSelectSnapshot', async () => {
    const onSelectSnapshot = jest.fn();
    render(<WorldRaw onSelectSnapshot={onSelectSnapshot} />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByTestId('snapshot-list')).toBeInTheDocument();
    });
    const firstRow = screen.getByTestId('snapshot-row-turn-0');
    fireEvent.click(firstRow);
    expect(onSelectSnapshot).toHaveBeenCalledWith('turn-0');
  });

  // ── R15. RAW tab accessible from WorldShell ─────────────────────────────────

  it('R15: RAW tab is clickable in WorldShell and renders world-raw', async () => {
    render(<WorldShell />, { wrapper: Wrapper });
    const rawBtn = screen.getByRole('button', { name: /raw/i });
    expect(rawBtn).not.toBeDisabled();
    fireEvent.click(rawBtn);
    await waitFor(() => {
      expect(screen.getByTestId('world-raw')).toBeInTheDocument();
    });
  });
});
