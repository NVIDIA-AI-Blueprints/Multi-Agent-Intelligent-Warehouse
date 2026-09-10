/**
 * WorldGraph — GRAPH tab for the Warehouse World Explorer.
 *
 * Search-first UX: user searches for an entity (or receives a focus from
 * a Copilot turn), the bounded neighborhood is loaded, and the SVG canvas
 * renders a radial layout.
 *
 * Copilot integration:
 *   When focusContext is set (VIEW OPERATIONAL CONTEXT clicked in Copilot),
 *   the graph auto-loads the entity from that turn's focus_entity_id.
 *   The context provenance banner shows CURRENT OPERATIONAL NEIGHBORHOOD
 *   (not "exact context used" — the API stores entity_count/summary but
 *   not exact node/edge IDs at time of turn).
 */

import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Box, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { worldAPI, GraphSearchResultDTO, GraphNodeDTO, GraphFocusContext, ChangedEntityDTO } from '../../services/worldAPI';
import { WorldView } from './WorldShell';
import OperationalGraph from './OperationalGraph';
import NodeInspector from './NodeInspector';

// ── Entity type badge colors ──────────────────────────────────────────────────

const ENTITY_COLORS: Record<string, string> = {
  wave: '#58A6FF', worker: '#3FB950', equipment: '#F0883E', task: '#A371F7',
  carrier_cutoff: '#D29922', order: '#BC8CFF', sku: '#DB6D28',
  warehouse: '#C9D1D9', zone: '#8B949E', location: '#6E7681',
};

function typeColor(t: string) { return ENTITY_COLORS[t] ?? '#8B949E'; }

// ── Search result item ────────────────────────────────────────────────────────

function SearchResultItem({
  result,
  onSelect,
}: {
  result: GraphSearchResultDTO;
  onSelect: (r: GraphSearchResultDTO) => void;
}) {
  return (
    <Box
      component="button"
      onClick={() => onSelect(result)}
      data-testid="search-result-item"
      data-entity-id={result.entity_id}
      sx={{
        display: 'flex', alignItems: 'center', gap: '8px',
        background: 'transparent', border: 'none', cursor: 'pointer',
        px: '8px', py: '5px', width: '100%', textAlign: 'left',
        borderBottom: '1px solid #161B22',
        '&:hover': { background: '#161B22' },
      }}
    >
      <Box sx={{
        width: 8, height: 8, borderRadius: '50%',
        background: typeColor(result.entity_type), flexShrink: 0,
      }} />
      <Box sx={{ flexGrow: 1, minWidth: 0 }}>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', color: '#C9D1D9' }}>
          {result.label}
        </Typography>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58' }}>
          {result.entity_type} · {result.entity_id}
        </Typography>
      </Box>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#30363D', flexShrink: 0 }}>
        {result.match_type}
      </Typography>
    </Box>
  );
}

// ── Context provenance banner ─────────────────────────────────────────────────

function ContextProvenanceBanner({
  focusContext,
  entityLabel,
  entityCount,
  depth,
  relCount,
}: {
  focusContext: GraphFocusContext;
  entityLabel: string;
  entityCount: number;
  depth: number;
  relCount: number;
}) {
  return (
    <Box
      data-testid="context-provenance-banner"
      sx={{
        background: '#0F1923', border: '1px solid #1F3A5A',
        borderRadius: '4px', px: '10px', py: '6px',
        display: 'flex', flexWrap: 'wrap', gap: '12px', alignItems: 'center',
      }}
    >
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', fontWeight: 700, color: '#58A6FF', letterSpacing: '0.1em' }}>
        CURRENT OPERATIONAL CONTEXT
      </Typography>
      {[
        ['Turn', focusContext.turnId.slice(0, 8)],
        ['Trace', focusContext.traceId.slice(0, 8)],
        ['Focus', entityLabel],
        ['Entities', String(entityCount)],
        ['Relationships', String(relCount)],
        ['Depth', String(depth)],
      ].map(([k, v]) => (
        <Box key={k} sx={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58' }}>{k}</Typography>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#8B949E' }}>{v}</Typography>
        </Box>
      ))}
      <Box sx={{ flexGrow: 1 }} />
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#1F3A5A', fontStyle: 'italic' }}>
        CURRENT OPERATIONAL NEIGHBORHOOD
      </Typography>
    </Box>
  );
}

// ── Empty / search state ──────────────────────────────────────────────────────

function SearchEmptyState({ onSearch }: { onSearch: (q: string) => void }) {
  return (
    <Box
      data-testid="graph-search-empty"
      sx={{
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        minHeight: 320, gap: '8px',
      }}
    >
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.75rem', color: '#30363D', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
        OPERATIONAL GRAPH
      </Typography>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#21262D' }}>
        Search for an entity to explore its neighborhood
      </Typography>
      <Box sx={{ mt: '8px', display: 'flex', flexWrap: 'wrap', gap: '6px', justifyContent: 'center' }}>
        {['Wave 17', 'worker', 'agv', 'task'].map((ex) => (
          <Box
            key={ex}
            component="button"
            onClick={() => onSearch(ex)}
            sx={{
              fontFamily: 'monospace', fontSize: '0.58rem', color: '#6E7681',
              border: '1px solid #30363D', borderRadius: '3px', px: '6px', py: '2px',
              background: 'transparent', cursor: 'pointer',
              '&:hover': { color: '#C9D1D9', borderColor: '#58A6FF' },
            }}
          >
            {ex}
          </Box>
        ))}
      </Box>
    </Box>
  );
}

// ── WorldGraph ────────────────────────────────────────────────────────────────

interface WorldGraphProps {
  worldView: WorldView;
  focusContext?: GraphFocusContext | null;
  onReturnToCopilot?: () => void;
}

export default function WorldGraph({ worldView, focusContext, onReturnToCopilot }: WorldGraphProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [showResults, setShowResults] = useState(false);
  const [focusEntityId, setFocusEntityId] = useState<string | null>(null);
  const [focusEntityLabel, setFocusEntityLabel] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [graphDepth, setGraphDepth] = useState(1);
  const searchRef = useRef<HTMLDivElement>(null);

  // Auto-load from Copilot focus context
  useEffect(() => {
    if (focusContext?.entityId) {
      setFocusEntityId(focusContext.entityId);
      setFocusEntityLabel(focusContext.entityLabel ?? focusContext.entityId);
      setSelectedNodeId(null);
      setSearchQuery(focusContext.entityLabel ?? focusContext.entityId);
      setShowResults(false);
    }
  }, [focusContext]);

  // Search query
  const { data: searchResults, isLoading: searchLoading } = useQuery({
    queryKey: ['worldGraphSearch', searchQuery],
    queryFn: () => worldAPI.searchGraph(searchQuery, 10),
    enabled: searchQuery.trim().length >= 1 && showResults,
    staleTime: 30_000,
  });

  // Neighborhood query
  const { data: neighborhood, isLoading: neighborhoodLoading, isError: neighborhoodError } = useQuery({
    queryKey: ['worldGraphNeighbors', focusEntityId, graphDepth, worldView],
    queryFn: () => worldAPI.getGraphNeighbors(focusEntityId!, graphDepth, 50, 100),
    enabled: !!focusEntityId,
    staleTime: 15_000,
    refetchInterval: focusEntityId ? 15_000 : false,
  });

  // Phase 17D: LIVE data for graph annotations (only when worldView === 'live')
  const { data: liveData } = useQuery({
    queryKey: ['world-live-graph'],
    queryFn: () => worldAPI.getLive(),
    enabled: worldView === 'live',
    refetchInterval: worldView === 'live' ? 15_000 : false,
    staleTime: 10_000,
  });

  // Build entity_id → ChangedEntityDTO map for OperationalGraph
  const liveChangedEntities = useMemo<Map<string, ChangedEntityDTO> | undefined>(() => {
    if (worldView !== 'live' || !liveData) return undefined;
    const m = new Map<string, ChangedEntityDTO>();
    for (const e of liveData.changed_entities) {
      m.set(e.entity_id, e);
    }
    return m;
  }, [worldView, liveData]);

  const handleSearchChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchQuery(e.target.value);
    setShowResults(true);
    if (!e.target.value.trim()) {
      setFocusEntityId(null);
      setFocusEntityLabel(null);
    }
  }, []);

  const handleSelectResult = useCallback((r: GraphSearchResultDTO) => {
    setFocusEntityId(r.entity_id);
    setFocusEntityLabel(r.label);
    setSearchQuery(r.label);
    setShowResults(false);
    setSelectedNodeId(null);
  }, []);

  const handleNodeClick = useCallback((id: string) => {
    setSelectedNodeId((prev) => (prev === id ? null : id));
  }, []);

  // Scenario annotation: in SCENARIO view, affected nodes have visual markers
  // (handled by the GraphNodeDTO.scenario_affected field from the API)
  const allNodes = neighborhood ? neighborhood.nodes : [];
  const focusNode = neighborhood?.focus_entity ?? null;

  const selectedNode = focusNode && selectedNodeId
    ? (selectedNodeId === focusNode.entity_id
        ? focusNode
        : allNodes.find((n) => n.entity_id === selectedNodeId) ?? null)
    : null;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: '8px', p: 2, height: '100%' }}>
      {/* Copilot return nav */}
      {focusContext && onReturnToCopilot && (
        <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Box
            component="button"
            onClick={onReturnToCopilot}
            data-testid="return-to-copilot"
            sx={{
              background: 'transparent', border: '1px solid #21262D', borderRadius: '3px',
              px: '8px', py: '3px', fontFamily: 'monospace', fontSize: '0.6rem',
              color: '#484F58', cursor: 'pointer',
              '&:hover': { color: '#58A6FF', borderColor: '#58A6FF44' },
            }}
          >
            ← RETURN TO COPILOT
          </Box>
        </Box>
      )}

      {/* Context provenance banner */}
      {focusContext && neighborhood && (
        <ContextProvenanceBanner
          focusContext={focusContext}
          entityLabel={focusEntityLabel ?? focusContext.entityLabel ?? focusContext.entityId}
          entityCount={neighborhood.entity_count}
          depth={neighborhood.depth}
          relCount={neighborhood.relationship_count}
        />
      )}

      {/* Search bar */}
      <Box ref={searchRef} sx={{ position: 'relative' }}>
        <input
          value={searchQuery}
          onChange={handleSearchChange}
          onFocus={() => { if (searchQuery.trim()) setShowResults(true); }}
          placeholder="Search entities…  (Wave 17, worker, agv, sku)"
          data-testid="graph-search-input"
          style={{
            width: '100%',
            background: '#161B22',
            border: '1px solid #21262D',
            borderRadius: 4,
            padding: '7px 10px',
            fontFamily: 'monospace',
            fontSize: '0.7rem',
            color: '#C9D1D9',
            outline: 'none',
            boxSizing: 'border-box',
          }}
        />
        {searchLoading && (
          <Typography sx={{ position: 'absolute', right: '10px', top: '8px', fontFamily: 'monospace', fontSize: '0.6rem', color: '#484F58' }}>
            …
          </Typography>
        )}

        {/* Dropdown results */}
        {showResults && searchResults && searchResults.results.length > 0 && (
          <Box
            data-testid="search-results-dropdown"
            sx={{
              position: 'absolute', zIndex: 100, top: '100%', left: 0, right: 0,
              background: '#161B22', border: '1px solid #21262D', borderRadius: '0 0 4px 4px',
              maxHeight: 240, overflow: 'auto', boxShadow: '0 4px 12px #00000080',
            }}
          >
            {searchResults.results.map((r) => (
              <SearchResultItem key={r.entity_id} result={r} onSelect={handleSelectResult} />
            ))}
          </Box>
        )}
      </Box>

      {/* Depth selector */}
      {focusEntityId && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58' }}>DEPTH</Typography>
          {[1, 2].map((d) => (
            <Box
              key={d}
              component="button"
              onClick={() => setGraphDepth(d)}
              data-testid={`depth-${d}`}
              sx={{
                background: graphDepth === d ? '#1C2128' : 'transparent',
                border: `1px solid ${graphDepth === d ? '#58A6FF' : '#21262D'}`,
                borderRadius: '3px', px: '8px', py: '2px',
                fontFamily: 'monospace', fontSize: '0.6rem',
                color: graphDepth === d ? '#58A6FF' : '#6E7681',
                cursor: 'pointer',
              }}
            >
              {d}
            </Box>
          ))}
          {focusEntityLabel && (
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#58A6FF', ml: '6px' }}>
              {focusEntityLabel}
            </Typography>
          )}
        </Box>
      )}

      {/* Main content */}
      {neighborhoodLoading && (
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 200 }}>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58' }}>
            Loading neighborhood…
          </Typography>
        </Box>
      )}

      {neighborhoodError && !neighborhoodLoading && (
        <Box
          data-testid="graph-error-state"
          sx={{
            background: '#1A0808', border: '1px solid #F8514944', borderRadius: '4px',
            p: '10px',
          }}
        >
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#F85149' }}>
            Failed to load graph neighborhood
          </Typography>
        </Box>
      )}

      {!focusEntityId && !neighborhoodLoading && (
        <SearchEmptyState onSearch={(q) => { setSearchQuery(q); setShowResults(true); }} />
      )}

      {focusNode && neighborhood && !neighborhoodLoading && (
        <Box sx={{ display: 'flex', gap: '8px', flexGrow: 1, minHeight: 0 }}>
          {/* Graph canvas */}
          <Box sx={{ flexGrow: 1, minWidth: 0 }}>
            <OperationalGraph
              focusNode={focusNode}
              nodes={worldView === 'base' ? allNodes : allNodes}
              edges={neighborhood.edges}
              truncated={neighborhood.truncated}
              truncatedFrom={neighborhood.truncated_from}
              selectedNodeId={selectedNodeId}
              onNodeClick={handleNodeClick}
              liveChangedEntities={liveChangedEntities}
            />
          </Box>

          {/* Node inspector */}
          {selectedNode && (
            <NodeInspector
              selectedNode={selectedNode}
              onClose={() => setSelectedNodeId(null)}
            />
          )}
        </Box>
      )}
    </Box>
  );
}
