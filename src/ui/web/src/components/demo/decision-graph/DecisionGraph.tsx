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

// ── Layout constants ──────────────────────────────────────────────────────────

const NODE_WIDTH   = 176;
const NODE_HEIGHT  = 72;
const LAYER_GAP    = 80;   // vertical gap between layer tops
const COL_GAP      = 24;   // horizontal gap between columns
const PADDING_X    = 24;
const PADDING_Y    = 24;

// Layer 11 = EXECUTION BOUNDARY (visual only, no nodes)
// We allocate extra space for it by shifting layers 12+ down an extra row
const EXEC_BOUNDARY_LAYER = 11;
const EXEC_BOUNDARY_EXTRA = 40; // extra vertical px for the boundary line

function layerToY(layer: number): number {
  const base = PADDING_Y + layer * (NODE_HEIGHT + LAYER_GAP);
  // Shift everything below the boundary line down by EXEC_BOUNDARY_EXTRA
  return layer > EXEC_BOUNDARY_LAYER ? base + EXEC_BOUNDARY_EXTRA : base;
}

function colToX(col: number): number {
  return PADDING_X + col * (NODE_WIDTH + COL_GAP);
}

function nodeCenterX(col: number): number {
  return colToX(col) + NODE_WIDTH / 2;
}

function nodeBottomY(layer: number): number {
  return layerToY(layer) + NODE_HEIGHT;
}

function nodeTopY(layer: number): number {
  return layerToY(layer);
}

// ── Edge SVG path ─────────────────────────────────────────────────────────────

function edgePath(
  sourceNode: DecisionGraphNode,
  targetNode: DecisionGraphNode,
): string {
  const x1 = nodeCenterX(sourceNode.column);
  const y1 = nodeBottomY(sourceNode.layer);
  const x2 = nodeCenterX(targetNode.column);
  const y2 = nodeTopY(targetNode.layer);

  const midY = (y1 + y2) / 2;

  return `M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`;
}

// ── Canvas size ───────────────────────────────────────────────────────────────

function computeCanvasSize(nodes: DecisionGraphNode[]): { width: number; height: number } {
  if (nodes.length === 0) return { width: 400, height: 300 };

  const maxLayer  = Math.max(...nodes.map(n => n.layer));
  const maxCol    = Math.max(...nodes.map(n => n.column));

  const width  = colToX(maxCol) + NODE_WIDTH + PADDING_X;
  const height = layerToY(maxLayer) + NODE_HEIGHT + PADDING_Y + 48;

  return { width, height };
}

// ── Execution boundary Y ──────────────────────────────────────────────────────

function execBoundaryY(): number {
  // Draw between layer 10 (APPROVAL) and layer 12 (EXECUTOR)
  const y10 = nodeBottomY(10);
  const y12 = nodeTopY(12);
  return (y10 + y12) / 2;
}

// ── Component ─────────────────────────────────────────────────────────────────

interface DecisionGraphProps {
  graph: DecisionGraphData;
}

export default function DecisionGraph({ graph }: DecisionGraphProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const handleNodeClick = useCallback((nodeId: string) => {
    setSelectedNodeId(prev => prev === nodeId ? null : nodeId);
  }, []);

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
            {/* Execution boundary marker */}
            {showExecBoundary && (
              <g>
                <line
                  x1={0}
                  y1={execBoundaryY()}
                  x2={canvasWidth}
                  y2={execBoundaryY()}
                  stroke="#F85149"
                  strokeWidth={1}
                  strokeDasharray="4 4"
                  opacity={0.4}
                />
                <text
                  x={canvasWidth / 2}
                  y={execBoundaryY() - 6}
                  textAnchor="middle"
                  fill="#F85149"
                  opacity={0.5}
                  style={{ fontFamily: 'monospace', fontSize: '9px', letterSpacing: '0.12em' }}
                >
                  ─── EXECUTION BOUNDARY ───
                </text>
              </g>
            )}

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
                left: colToX(node.column),
                top:  layerToY(node.layer),
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

      {/* Detail panel */}
      {selectedNode && (
        <DecisionGraphDetails
          selectedNode={selectedNode}
          artifact={artifact}
          onClose={() => setSelectedNodeId(null)}
        />
      )}
    </Box>
  );
}
