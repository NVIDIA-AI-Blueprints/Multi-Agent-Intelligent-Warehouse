/**
 * DecisionGraph — main render component for the progressive decision graph (Phase 13C).
 *
 * Renders:
 *   - Absolutely-positioned node cards (DecisionGraphNode)
 *   - SVG overlay for bezier edges
 *   - Execution boundary marker between APPROVAL and EXECUTOR layers
 *   - Selected-node detail panel (DecisionGraphDetails) sliding in from right
 *
 * No external graph library. Pure SVG + positioned divs.
 *
 * Layer-to-Y mapping:
 *   Layer 0..N map to Y positions. Layer 11 is the EXECUTION BOUNDARY visual
 *   (no nodes), rendered as a special SVG line between layers 10 and 12.
 */

import React, { useState, useMemo, useCallback } from 'react';
import { Box, Typography } from '@mui/material';
import { DecisionGraph as DecisionGraphData, DecisionGraphNode, DecisionGraphEdge } from './graphTypes';
import DecisionGraphNodeCard from './DecisionGraphNode';
import DecisionGraphDetails from './DecisionGraphDetails';
import StoryDecisionGraph from './StoryDecisionGraph';
import { getSemanticZoomLevel } from './semanticZoom';
import { ExplanationFocus } from '../decision-explanation/explanationTypes';
import { AnalysisResult, PendingApproval, DemoStatus } from '../../../services/demoAPI';

// ── Zoom constants ────────────────────────────────────────────────────────────

const ZOOM_MIN  = 0.4;
const ZOOM_MAX  = 1.5;
const ZOOM_STEP = 0.15;
const ZOOM_DEFAULT = 0.85;

// ── Layout constants ──────────────────────────────────────────────────────────
// Horizontal layout: layers flow LEFT → RIGHT, columns flow TOP → BOTTOM

const NODE_WIDTH   = 160;
const NODE_HEIGHT  = 64;
const LAYER_GAP    = 32;   // horizontal gap between layers
const COL_GAP      = 16;   // vertical gap between column rows
const PADDING_X    = 24;
const PADDING_Y    = 24;

// Layer 11 = EXECUTION BOUNDARY (visual only, no nodes)
const EXEC_BOUNDARY_LAYER = 11;
const EXEC_BOUNDARY_EXTRA = 36; // extra horizontal px for the boundary line

function layerToX(layer: number): number {
  const base = PADDING_X + layer * (NODE_WIDTH + LAYER_GAP);
  return layer > EXEC_BOUNDARY_LAYER ? base + EXEC_BOUNDARY_EXTRA : base;
}

function colToY(col: number): number {
  return PADDING_Y + col * (NODE_HEIGHT + COL_GAP);
}

function nodeRightX(layer: number): number {
  return layerToX(layer) + NODE_WIDTH;
}

function nodeLeftX(layer: number): number {
  return layerToX(layer);
}

function nodeCenterY(col: number): number {
  return colToY(col) + NODE_HEIGHT / 2;
}

// ── Edge SVG path (horizontal bezier: right-center → left-center) ─────────────

function edgePath(
  sourceNode: DecisionGraphNode,
  targetNode: DecisionGraphNode,
): string {
  const x1 = nodeRightX(sourceNode.layer);
  const y1 = nodeCenterY(sourceNode.column);
  const x2 = nodeLeftX(targetNode.layer);
  const y2 = nodeCenterY(targetNode.column);

  const midX = (x1 + x2) / 2;

  return `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`;
}

// ── Canvas size ───────────────────────────────────────────────────────────────

function computeCanvasSize(nodes: DecisionGraphNode[]): { width: number; height: number } {
  if (nodes.length === 0) return { width: 600, height: 300 };

  const maxLayer = Math.max(...nodes.map(n => n.layer));
  const maxCol   = Math.max(...nodes.map(n => n.column));

  const width  = layerToX(maxLayer) + NODE_WIDTH + PADDING_X;
  const height = colToY(maxCol) + NODE_HEIGHT + PADDING_Y + 16;

  return { width, height };
}

// ── Execution boundary X ──────────────────────────────────────────────────────

function execBoundaryX(canvasHeight: number): { x: number; h: number } {
  // Draw a vertical line between layer 10 (APPROVAL) and layer 12 (EXECUTOR)
  const x10 = nodeRightX(10);
  const x12 = nodeLeftX(12);
  return { x: (x10 + x12) / 2, h: canvasHeight };
}

// ── Component ─────────────────────────────────────────────────────────────────

interface DecisionGraphProps {
  graph: DecisionGraphData;
  analysisResult?: AnalysisResult | null;
  pendingApprovals?: PendingApproval[];
  demoStatus?: DemoStatus | null;
  onOpenExplanation?: (focus: ExplanationFocus) => void;
}

type GraphMode = 'story' | 'trace';

export default function DecisionGraph({ graph, onOpenExplanation }: DecisionGraphProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [zoom, setZoom] = useState(ZOOM_DEFAULT);
  const [graphMode, setGraphMode] = useState<GraphMode>('story');

  const zoomLevel = getSemanticZoomLevel(zoom);

  const zoomIn  = useCallback(() => setZoom(z => Math.min(ZOOM_MAX, +(z + ZOOM_STEP).toFixed(2))), []);
  const zoomOut = useCallback(() => setZoom(z => Math.max(ZOOM_MIN, +(z - ZOOM_STEP).toFixed(2))), []);
  const zoomReset = useCallback(() => setZoom(ZOOM_DEFAULT), []);
  const fitStory = useCallback(() => { setZoom(ZOOM_DEFAULT); setGraphMode('story'); }, []);

  const handleNodeClick = useCallback((nodeId: string) => {
    if (onOpenExplanation) {
      onOpenExplanation({ kind: 'node', nodeId });
    } else {
      setSelectedNodeId(prev => prev === nodeId ? null : nodeId);
    }
  }, [onOpenExplanation]);

  const selectedNode = useMemo(
    () => graph.nodes.find(n => n.id === selectedNodeId) ?? null,
    [graph.nodes, selectedNodeId],
  );

  // Artifact: reconstruct from metadata for Phase 13D consumption
  const artifact = useMemo(() => {
    if (!selectedNode?.metadata) return null;
    return { ...selectedNode.metadata };
  }, [selectedNode]);

  const nodeMap = useMemo(() => {
    const m = new Map<string, DecisionGraphNode>();
    graph.nodes.forEach(n => m.set(n.id, n));
    return m;
  }, [graph.nodes]);

  const { width: canvasWidth, height: canvasHeight } = useMemo(
    () => computeCanvasSize(graph.nodes),
    [graph.nodes],
  );

  // Determine if any nodes are at layer >= EXECUTOR (12) — show boundary line
  const hasExecutionLayers = graph.nodes.some(n => n.layer >= 12);

  // Determine if any nodes exist at approval layer (10) — show boundary from that side
  const hasApprovalLayer = graph.nodes.some(n => n.layer === 10);
  const showExecBoundary = hasExecutionLayers || hasApprovalLayer;

  return (
    <Box
      data-testid="decision-graph"
      sx={{
        display: 'flex',
        gap: 2,
        alignItems: 'flex-start',
      }}
    >
      {/* Graph canvas — scrollable */}
      <Box
        sx={{
          flex: 1,
          overflow: 'auto',
          minWidth: 0,
        }}
      >
        {/* Control bar: [STORY] [TRACE]   [−] [85%] [+] [FIT] */}
        <Box sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 0.5,
          mb: 1.5,
          userSelect: 'none',
        }}>
          {/* Mode toggle: STORY */}
          <Box
            component="button"
            onClick={() => setGraphMode('story')}
            title="Story Graph view"
            sx={{
              background: graphMode === 'story' ? '#161B22' : 'transparent',
              border: `1px solid ${graphMode === 'story' ? '#58A6FF' : '#30363D'}`,
              borderRadius: '4px',
              color: graphMode === 'story' ? '#58A6FF' : '#484F58',
              cursor: 'pointer',
              fontFamily: 'monospace',
              fontSize: '0.6rem',
              fontWeight: graphMode === 'story' ? 700 : 400,
              letterSpacing: '0.06em',
              px: '8px',
              py: '3px',
              '&:hover': { borderColor: '#58A6FF', color: '#58A6FF' },
            }}
          >
            STORY
          </Box>

          {/* Mode toggle: TRACE */}
          <Box
            component="button"
            onClick={() => setGraphMode('trace')}
            title="Trace Graph view"
            sx={{
              background: graphMode === 'trace' ? '#161B22' : 'transparent',
              border: `1px solid ${graphMode === 'trace' ? '#58A6FF' : '#30363D'}`,
              borderRadius: '4px',
              color: graphMode === 'trace' ? '#58A6FF' : '#484F58',
              cursor: 'pointer',
              fontFamily: 'monospace',
              fontSize: '0.6rem',
              fontWeight: graphMode === 'trace' ? 700 : 400,
              letterSpacing: '0.06em',
              px: '8px',
              py: '3px',
              '&:hover': { borderColor: '#58A6FF', color: '#58A6FF' },
            }}
          >
            TRACE
          </Box>

          {/* Spacer */}
          <Box sx={{ flexGrow: 1 }} />

          {/* Zoom out */}
          <Box
            component="button"
            onClick={zoomOut}
            disabled={zoom <= ZOOM_MIN}
            title="Zoom out"
            sx={{
              background: 'transparent',
              border: '1px solid #30363D',
              borderRadius: '4px',
              color: zoom <= ZOOM_MIN ? '#30363D' : '#8B949E',
              cursor: zoom <= ZOOM_MIN ? 'default' : 'pointer',
              fontFamily: 'monospace',
              fontSize: '1rem',
              lineHeight: 1,
              px: '8px',
              py: '3px',
              '&:hover:not(:disabled)': { borderColor: '#58A6FF', color: '#58A6FF' },
            }}
          >
            −
          </Box>

          {/* Zoom level — click to reset */}
          <Box
            component="button"
            onClick={zoomReset}
            title="Reset zoom"
            sx={{
              background: 'transparent',
              border: '1px solid #21262D',
              borderRadius: '4px',
              color: '#484F58',
              cursor: 'pointer',
              fontFamily: 'monospace',
              fontSize: '0.6rem',
              px: '8px',
              py: '3px',
              minWidth: 44,
              letterSpacing: '0.04em',
              '&:hover': { borderColor: '#30363D', color: '#8B949E' },
            }}
          >
            {Math.round(zoom * 100)}%
          </Box>

          {/* Zoom in */}
          <Box
            component="button"
            onClick={zoomIn}
            disabled={zoom >= ZOOM_MAX}
            title="Zoom in"
            sx={{
              background: 'transparent',
              border: '1px solid #30363D',
              borderRadius: '4px',
              color: zoom >= ZOOM_MAX ? '#30363D' : '#8B949E',
              cursor: zoom >= ZOOM_MAX ? 'default' : 'pointer',
              fontFamily: 'monospace',
              fontSize: '1rem',
              lineHeight: 1,
              px: '8px',
              py: '3px',
              '&:hover:not(:disabled)': { borderColor: '#58A6FF', color: '#58A6FF' },
            }}
          >
            +
          </Box>

          {/* FIT — resets zoom to default and switches to story mode */}
          <Box
            component="button"
            onClick={fitStory}
            data-testid="fit-btn"
            title="Fit to story"
            sx={{
              background: 'transparent',
              border: '1px solid #30363D',
              borderRadius: '4px',
              color: '#8B949E',
              cursor: 'pointer',
              fontFamily: 'monospace',
              fontSize: '0.6rem',
              letterSpacing: '0.06em',
              px: '8px',
              py: '3px',
              '&:hover': { borderColor: '#58A6FF', color: '#58A6FF' },
            }}
          >
            FIT
          </Box>
        </Box>

        {/* Story Graph mode */}
        {graphMode === 'story' && (
          <Box sx={{ overflow: 'auto', width: '100%' }}>
            <StoryDecisionGraph
              graph={graph}
              zoomLevel={zoomLevel}
              selectedNodeId={selectedNodeId}
              onNodeClick={handleNodeClick}
            />
          </Box>
        )}

        {/* Trace Graph mode — original SVG + positioned-div canvas */}
        {graphMode === 'trace' && (
        <Box
          data-testid="decision-graph-trace"
          sx={{
            overflow: 'auto',
            width: '100%',
          }}
        >
          <Box
            sx={{
              transformOrigin: 'top left',
              transform: `scale(${zoom})`,
              display: 'inline-block',
              // Reserve scaled dimensions so scrollbar appears correctly
              width:  Math.round(canvasWidth  * zoom),
              height: Math.round(canvasHeight * zoom),
            }}
          >
        <Box
          sx={{
            position: 'relative',
            width: canvasWidth,
            height: canvasHeight,
            flexShrink: 0,
          }}
        >
          {/* SVG edge overlay */}
          <svg
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: canvasWidth,
              height: canvasHeight,
              pointerEvents: 'none',
              overflow: 'visible',
            }}
          >
            {/* Execution boundary marker — vertical line between APPROVAL and EXECUTOR */}
            {showExecBoundary && (() => {
              const { x, h } = execBoundaryX(canvasHeight);
              return (
                <g>
                  <line
                    x1={x} y1={0}
                    x2={x} y2={h}
                    stroke="#F85149"
                    strokeWidth={1}
                    strokeDasharray="4 4"
                    opacity={0.35}
                  />
                  <text
                    x={x + 5}
                    y={20}
                    textAnchor="start"
                    fill="#F85149"
                    opacity={0.5}
                    style={{ fontFamily: 'monospace', fontSize: '8px', letterSpacing: '0.1em' }}
                  >
                    EXECUTION BOUNDARY
                  </text>
                </g>
              );
            })()}

            {/* Edges */}
            {graph.edges.map((edge: DecisionGraphEdge) => {
              const srcNode = nodeMap.get(edge.source);
              const tgtNode = nodeMap.get(edge.target);
              if (!srcNode || !tgtNode) return null;

              const isSelected =
                edge.source === selectedNodeId || edge.target === selectedNodeId;

              const strokeColor =
                edge.status === 'error'   ? '#F85149' :
                edge.status === 'pending' ? '#D29922' :
                edge.status === 'unknown' ? '#D29922' :
                '#30363D';

              return (
                <path
                  key={edge.id}
                  d={edgePath(srcNode, tgtNode)}
                  fill="none"
                  stroke={isSelected ? '#58A6FF' : strokeColor}
                  strokeWidth={isSelected ? 1.5 : 1}
                  opacity={isSelected ? 0.8 : 0.5}
                  markerEnd={undefined}
                />
              );
            })}
          </svg>

          {/* Node cards */}
          {graph.nodes.map((node: DecisionGraphNode) => (
            <Box
              key={node.id}
              sx={{
                position: 'absolute',
                left: layerToX(node.layer),
                top:  colToY(node.column),
              }}
            >
              <DecisionGraphNodeCard
                node={node}
                selected={node.id === selectedNodeId}
                onClick={handleNodeClick}
                width={NODE_WIDTH}
                height={NODE_HEIGHT}
              />
            </Box>
          ))}
        </Box>
          </Box>
        </Box>
        )}

      </Box>

      {/* Detail panel — shown only in standalone mode (when onOpenExplanation not provided) */}
      {selectedNode && !onOpenExplanation && (
        <DecisionGraphDetails
          selectedNode={selectedNode}
          artifact={artifact}
          onClose={() => setSelectedNodeId(null)}
        />
      )}
    </Box>
  );
}
