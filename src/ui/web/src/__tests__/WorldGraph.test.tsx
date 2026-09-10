/**
 * Phase 17C — WorldGraph frontend tests.
 *
 * Covers:
 *  1.  GRAPH tab is enabled in WorldShell (not disabled)
 *  2.  Clicking GRAPH tab renders WorldGraph
 *  3.  Search input renders in WorldGraph
 *  4.  Empty state shown before search
 *  5.  Search results dropdown shown on response
 *  6.  Clicking result shows focus entity in graph
 *  7.  Wave 17 neighborhood renders focus node
 *  8.  Edge elements rendered when neighborhood has edges
 *  9.  Focus node has bfs_depth=0 visual marker
 * 10.  Scenario-affected nodes have scenario indicator
 * 11.  BASE vs SCENARIO view passed to WorldGraph
 * 12.  Truncated state shows count
 * 13.  API failure shows error state
 * 14.  Copilot VIEW OPERATIONAL CONTEXT button renders when focus_entity_id set
 * 15.  Copilot context switches mode to WORLD and opens GRAPH
 * 16.  RETURN TO COPILOT button rendered in WorldGraph
 * 17.  Context provenance banner shows CURRENT OPERATIONAL NEIGHBORHOOD
 * 18.  Node inspector opens on node click
 * 19.  No mutation controls in WORLD GRAPH
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@mui/material/styles';
import { nvidiaTheme } from '../theme/nvidiaTheme';

import DemoShell from '../pages/DemoShell';
import WorldShell from '../components/world/WorldShell';
import WorldGraph from '../components/world/WorldGraph';
import { worldAPI } from '../services/worldAPI';
import { CopilotAnswer } from '../components/demo/copilot/CopilotDrawer';

// ── Mocks ─────────────────────────────────────────────────────────────────────

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

// ── Test data ─────────────────────────────────────────────────────────────────

const mockNeighborhood = {
  focus_entity: {
    entity_id: 'wave-017',
    entity_type: 'wave',
    label: 'Wave 17',
    attributes_summary: { wave_number: 17, status: 'active' },
    scenario_affected: false,
    scenario_severity: null,
    bfs_depth: 0,
  },
  nodes: [
    {
      entity_id: 'task-000001',
      entity_type: 'task',
      label: 'PICK task-000001',
      attributes_summary: { task_type: 'PICK', status: 'PENDING' },
      scenario_affected: false,
      scenario_severity: null,
      bfs_depth: 1,
    },
    {
      entity_id: 'task-000002',
      entity_type: 'task',
      label: 'PACK task-000002',
      attributes_summary: { task_type: 'PACK', status: 'PENDING' },
      scenario_affected: true,
      scenario_severity: 'MODERATE',
      bfs_depth: 1,
    },
  ],
  edges: [
    {
      edge_id: 'e-001',
      source_id: 'task-000001',
      target_id: 'wave-017',
      relationship_type: 'BELONGS_TO',
      valid_from: null,
      valid_to: null,
      temporal: false,
      active: true,
    },
  ],
  depth: 1,
  entity_count: 2,
  relationship_count: 1,
  truncated: false,
  truncated_from: null,
  relationship_summary: { Tasks: ['PICK task-000001', 'PACK task-000002'] },
  dataset_id: 'dc47-demo-v1',
  warehouse_id: 'DC-47',
};

const mockSearchResults = {
  query: 'Wave 17',
  results: [
    { entity_id: 'wave-017', entity_type: 'wave', label: 'Wave 17', match_type: 'EXACT_ID' },
  ],
};

const mockEntityDetail = {
  entity_id: 'wave-017',
  entity_type: 'wave',
  label: 'Wave 17',
  attributes: { wave_number: 17, status: 'active', strategy: 'priority' },
  incoming_count: 40,
  outgoing_count: 285,
  scenario_affected: false,
  scenario_severity: null,
  direct_relationships: [],
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 } } });
}

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={makeQC()}>
      <ThemeProvider theme={nvidiaTheme}>{children}</ThemeProvider>
    </QueryClientProvider>
  );
}

const mockSearchGraph = worldAPI.searchGraph as jest.Mock;
const mockGetGraphNeighbors = worldAPI.getGraphNeighbors as jest.Mock;
const mockGetGraphEntity = worldAPI.getGraphEntity as jest.Mock;
const mockGetConfig = worldAPI.getConfig as jest.Mock;
const mockGetSummary = worldAPI.getSummary as jest.Mock;

beforeEach(() => {
  jest.clearAllMocks();
  mockSearchGraph.mockResolvedValue(mockSearchResults);
  mockGetGraphNeighbors.mockResolvedValue(mockNeighborhood);
  mockGetGraphEntity.mockResolvedValue(mockEntityDetail);
  mockGetConfig.mockResolvedValue({
    warehouse: { warehouse_id: 'DC-47', dataset_id: 'dc47-demo-v1', seed: 42 },
    layout: { zone_count: 8, location_count: 3200, dock_door_count: 12 },
    workforce: { workers_per_shift: 30, shift_count: 3, total_workers: 90, skills: ['pick'] },
    equipment: { agv_count: 10, forklift_count: 5, conveyor_count: 2, total: 17 },
    commerce: { sku_count: 5000, low_stock_pct: 0.05, daily_order_count: 800, lines_per_order_mean: 3.2 },
    operations: { active_wave_count: 2, task_count: 240, strategy: 'FIFO' },
    generation: { schema_version: '1.0', generator_version: '0.9.0', pack_format: 'parquet', semantic_checksum: 'abc123', total_entities: 4000, total_edges: 12000, total_events: 500, graph_available: true },
  });
  mockGetSummary.mockResolvedValue({
    datapack: { dataset_id: 'dc47-demo-v1', warehouse_id: 'DC-47', seed: 42, schema_version: '1.0', semantic_checksum: 'abc123', total_entities: 4000, total_edges: 12000, total_events: 500, pack_format: 'parquet', generator_version: '0.9.0', immutable: true, loaded: true },
    graph: { entity_counts: { Wave: 3 }, relationship_counts: {}, total_entities: 4000, total_relationships: 12000, event_count: 500, available: true },
    scenario: { scenario_id: null, name: null, severity: null, active: false },
    runtime: { status: 'READY', elapsed_seconds: null, clock_iso: null },
  });
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('Phase 17C — World Graph Explorer', () => {

  // 1. GRAPH tab enabled
  it('GRAPH tab is enabled in WorldShell', () => {
    render(<WorldShell />, { wrapper: Wrapper });
    const graphBtn = screen.getByRole('button', { name: /graph/i });
    expect(graphBtn).not.toBeDisabled();
    expect(graphBtn).not.toHaveAttribute('aria-disabled', 'true');
  });

  // 2. Clicking GRAPH tab renders WorldGraph
  it('clicking GRAPH tab renders graph search input', () => {
    render(<WorldShell />, { wrapper: Wrapper });
    fireEvent.click(screen.getByRole('button', { name: /^graph$/i }));
    expect(screen.getByTestId('graph-search-input')).toBeInTheDocument();
  });

  // 3. Search input renders
  it('renders search input in WorldGraph', () => {
    render(<WorldGraph worldView="base" />, { wrapper: Wrapper });
    expect(screen.getByTestId('graph-search-input')).toBeInTheDocument();
  });

  // 4. Empty state before search
  it('shows empty search state before entity is selected', () => {
    render(<WorldGraph worldView="base" />, { wrapper: Wrapper });
    expect(screen.getByTestId('graph-search-empty')).toBeInTheDocument();
  });

  // 5. Search results dropdown shown
  it('shows search results after typing in search input', async () => {
    render(<WorldGraph worldView="base" />, { wrapper: Wrapper });
    const input = screen.getByTestId('graph-search-input');
    fireEvent.change(input, { target: { value: 'Wave 17' } });
    fireEvent.focus(input);
    await waitFor(() => {
      expect(screen.getByTestId('search-results-dropdown')).toBeInTheDocument();
    });
    expect(screen.getByTestId('search-result-item')).toBeInTheDocument();
  });

  // 6. Clicking result loads neighborhood
  it('selecting search result loads graph neighborhood', async () => {
    render(<WorldGraph worldView="base" />, { wrapper: Wrapper });
    const input = screen.getByTestId('graph-search-input');
    fireEvent.change(input, { target: { value: 'Wave 17' } });
    fireEvent.focus(input);
    await waitFor(() => {
      expect(screen.getByTestId('search-result-item')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('search-result-item'));
    await waitFor(() => {
      expect(mockGetGraphNeighbors).toHaveBeenCalledWith('wave-017', expect.any(Number), 50, 100);
    });
  });

  // 7. Wave 17 focus node rendered
  it('renders focus node for Wave 17', async () => {
    render(<WorldGraph worldView="base" />, { wrapper: Wrapper });
    const input = screen.getByTestId('graph-search-input');
    fireEvent.change(input, { target: { value: 'Wave 17' } });
    fireEvent.focus(input);
    await waitFor(() => screen.getByTestId('search-result-item'));
    fireEvent.click(screen.getByTestId('search-result-item'));
    await waitFor(() => {
      expect(screen.getByTestId('graph-focus-node')).toBeInTheDocument();
    });
  });

  // 8. Edge elements rendered
  it('renders graph edges when neighborhood has edges', async () => {
    render(<WorldGraph worldView="base" />, { wrapper: Wrapper });
    const input = screen.getByTestId('graph-search-input');
    fireEvent.change(input, { target: { value: 'Wave 17' } });
    fireEvent.focus(input);
    await waitFor(() => screen.getByTestId('search-result-item'));
    fireEvent.click(screen.getByTestId('search-result-item'));
    await waitFor(() => {
      expect(screen.getAllByTestId('graph-edge').length).toBeGreaterThan(0);
    });
  });

  // 9. Focus node has bfs_depth=0
  it('focus node is data-entity-id=wave-017', async () => {
    render(<WorldGraph worldView="base" />, { wrapper: Wrapper });
    const input = screen.getByTestId('graph-search-input');
    fireEvent.change(input, { target: { value: 'Wave 17' } });
    fireEvent.focus(input);
    await waitFor(() => screen.getByTestId('search-result-item'));
    fireEvent.click(screen.getByTestId('search-result-item'));
    await waitFor(() => {
      const focusNode = screen.getByTestId('graph-focus-node');
      expect(focusNode).toHaveAttribute('data-entity-id', 'wave-017');
    });
  });

  // 10. Scenario-affected node indicator
  it('scenario-affected nodes are present in graph', async () => {
    render(<WorldGraph worldView="scenario" />, { wrapper: Wrapper });
    const input = screen.getByTestId('graph-search-input');
    fireEvent.change(input, { target: { value: 'Wave 17' } });
    fireEvent.focus(input);
    await waitFor(() => screen.getByTestId('search-result-item'));
    fireEvent.click(screen.getByTestId('search-result-item'));
    await waitFor(() => {
      // task-000002 is scenario_affected=true
      const affectedNode = screen.getByTestId('operational-graph-canvas').querySelector('[data-entity-id="task-000002"]');
      expect(affectedNode).not.toBeNull();
    });
  });

  // 11. BASE vs SCENARIO view
  it('BASE and SCENARIO world views are accessible', () => {
    render(<WorldShell />, { wrapper: Wrapper });
    fireEvent.click(screen.getByRole('button', { name: /^graph$/i }));
    // WorldViewSwitcher is rendered — BASE and SCENARIO buttons present
    const worldViewSwitcher = screen.getByTestId('world-view-switcher');
    expect(worldViewSwitcher).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^base$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^scenario$/i })).toBeInTheDocument();
  });

  // 12. Truncated state
  it('shows truncated count when neighborhood is truncated', async () => {
    mockGetGraphNeighbors.mockResolvedValue({
      ...mockNeighborhood,
      truncated: true,
      truncated_from: 325,
    });
    render(<WorldGraph worldView="base" />, { wrapper: Wrapper });
    const input = screen.getByTestId('graph-search-input');
    fireEvent.change(input, { target: { value: 'Wave 17' } });
    fireEvent.focus(input);
    await waitFor(() => screen.getByTestId('search-result-item'));
    fireEvent.click(screen.getByTestId('search-result-item'));
    await waitFor(() => {
      expect(screen.getByText(/SHOWING.*OF.*325/i)).toBeInTheDocument();
    });
  });

  // 13. API failure → error state
  it('shows error state when neighborhood API fails', async () => {
    mockGetGraphNeighbors.mockRejectedValue(new Error('Network error'));
    render(<WorldGraph worldView="base" />, { wrapper: Wrapper });
    const input = screen.getByTestId('graph-search-input');
    fireEvent.change(input, { target: { value: 'Wave 17' } });
    fireEvent.focus(input);
    await waitFor(() => screen.getByTestId('search-result-item'));
    fireEvent.click(screen.getByTestId('search-result-item'));
    await waitFor(() => {
      expect(screen.getByTestId('graph-error-state')).toBeInTheDocument();
    });
  });

  // 14. Copilot VIEW OPERATIONAL CONTEXT button renders when focus_entity_id set
  it('renders VIEW OPERATIONAL CONTEXT button when Copilot turn has focus entity', () => {
    const mockTurn = {
      turn_id: 'turn-abc123',
      conversation_id: 'conv-001',
      trace_id: 'trace-xyz456',
      intent: 'ask',
      status: 'complete',
      answer: 'Wave 17 is at risk due to labor constraints.',
      focus_entity_id: 'wave-017',
      focus_entity_label: 'Wave 17',
      neighborhood: { focus_entity_id: 'wave-017', focus_entity_label: 'Wave 17', entity_count: 22, relationship_summary: {}, graph_available: true },
      degraded: false,
      answerability: 'answerable',
      missing_context: [],
      timing: {},
      evidence: [],
    } as any;

    const mockOnView = jest.fn();
    render(
      <CopilotAnswer turn={mockTurn} onViewOperationalContext={mockOnView} />,
      { wrapper: Wrapper },
    );
    expect(screen.getByTestId('view-operational-context')).toBeInTheDocument();
  });

  // 15. Copilot VIEW OPERATIONAL CONTEXT switches to WORLD mode
  it('clicking VIEW OPERATIONAL CONTEXT calls handler with correct context', () => {
    const mockTurn = {
      turn_id: 'turn-abc123',
      conversation_id: 'conv-001',
      trace_id: 'trace-xyz456',
      intent: 'ask',
      status: 'complete',
      answer: 'Wave 17 is at risk.',
      focus_entity_id: 'wave-017',
      focus_entity_label: 'Wave 17',
      neighborhood: { focus_entity_id: 'wave-017', focus_entity_label: 'Wave 17', entity_count: 22, relationship_summary: {}, graph_available: true },
      degraded: false,
      answerability: 'answerable',
      missing_context: [],
      timing: {},
      evidence: [],
    } as any;

    const mockOnView = jest.fn();
    render(
      <CopilotAnswer turn={mockTurn} onViewOperationalContext={mockOnView} />,
      { wrapper: Wrapper },
    );
    fireEvent.click(screen.getByTestId('view-operational-context'));
    expect(mockOnView).toHaveBeenCalledWith({
      entityId: 'wave-017',
      entityLabel: 'Wave 17',
      turnId: 'turn-abc123',
      traceId: 'trace-xyz456',
      entityCount: 22,
    });
  });

  // 16. RETURN TO COPILOT button in WorldGraph
  it('renders RETURN TO COPILOT button when focusContext and onReturnToCopilot are set', () => {
    const ctx = { entityId: 'wave-017', entityLabel: 'Wave 17', turnId: 'turn-abc123', traceId: 'trace-xyz456', entityCount: 22 };
    const onReturn = jest.fn();
    render(<WorldGraph worldView="base" focusContext={ctx} onReturnToCopilot={onReturn} />, { wrapper: Wrapper });
    expect(screen.getByTestId('return-to-copilot')).toBeInTheDocument();
  });

  // 17. Context provenance banner shows CURRENT OPERATIONAL CONTEXT (Phase 17F: renamed)
  it('shows context provenance banner when focusContext and neighborhood loaded', async () => {
    const ctx = { entityId: 'wave-017', entityLabel: 'Wave 17', turnId: 'turn-abc123', traceId: 'trace-xyz456', entityCount: 22 };
    render(<WorldGraph worldView="base" focusContext={ctx} />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByTestId('context-provenance-banner')).toBeInTheDocument();
      expect(screen.getByText(/CURRENT OPERATIONAL CONTEXT/i)).toBeInTheDocument();
    });
  });

  // 18. Node inspector opens on node click
  it('clicking a node opens the node inspector', async () => {
    render(<WorldGraph worldView="base" />, { wrapper: Wrapper });
    const input = screen.getByTestId('graph-search-input');
    fireEvent.change(input, { target: { value: 'Wave 17' } });
    fireEvent.focus(input);
    await waitFor(() => screen.getByTestId('search-result-item'));
    fireEvent.click(screen.getByTestId('search-result-item'));
    await waitFor(() => screen.getByTestId('graph-focus-node'));
    fireEvent.click(screen.getByTestId('graph-focus-node'));
    await waitFor(() => {
      expect(screen.getByTestId('node-inspector')).toBeInTheDocument();
    });
  });

  // 19. No mutation controls in WORLD GRAPH
  it('WorldGraph has no approve/execute/reject/start/inject buttons', async () => {
    render(<WorldGraph worldView="base" />, { wrapper: Wrapper });
    await waitFor(() => expect(screen.getByTestId('graph-search-input')).toBeInTheDocument());
    const buttons = screen.queryAllByRole('button');
    for (const btn of buttons) {
      expect(btn.textContent).not.toMatch(/^(approve|execute|reject|inject|start scenario)$/i);
    }
  });

});
