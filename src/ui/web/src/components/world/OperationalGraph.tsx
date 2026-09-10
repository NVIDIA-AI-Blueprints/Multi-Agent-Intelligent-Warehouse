/**
 * OperationalGraph — pure SVG canvas with deterministic radial layout.
 *
 * No external graph library. Zero new dependencies.
 * Same pattern as DecisionGraph (pure SVG + CSS transform zoom).
 *
 * Layout:
 *   Focus node at canvas center.
 *   Depth-1 neighbors on inner ring (radius R1).
 *   Depth-2 neighbors on outer ring (radius R2).
 *   Nodes sorted by (entity_type, entity_id) within each ring for determinism.
 *   Edges rendered as SVG lines between node centers.
 */

import React, { useMemo, useCallback, useState } from 'react';
import { Box, Typography } from '@mui/material';
import { GraphNodeDTO, GraphEdgeDTO, ChangedEntityDTO } from '../../services/worldAPI';
import { getSemanticZoomLevel } from '../demo/decision-graph/semanticZoom';

// ── Constants ────────────────────────────────────────────────────────────────

const CANVAS_W = 740;
const CANVAS_H = 520;
const CX = CANVAS_W / 2;
const CY = CANVAS_H / 2;

const FOCUS_W = 96;
const FOCUS_H = 44;
const NODE_W = 72;
const NODE_H = 32;

const ZOOM_MIN = 0.4;
const ZOOM_MAX = 1.6;
const ZOOM_STEP = 0.15;
const ZOOM_DEFAULT = 0.85;

// ── Entity type colors (MAIW dark palette) ────────────────────────────────────

const ENTITY_COLORS: Record<string, string> = {
  warehouse: '#C9D1D9',
  zone: '#8B949E',
  location: '#6E7681',
  worker: '#3FB950',
  shift: '#2EA043',
  equipment: '#F0883E',
  wave: '#58A6FF',
  task: '#A371F7',
  carrier_cutoff: '#D29922',
  order: '#BC8CFF',
  sku: '#DB6D28',
  inventory_position: '#6E7681',
};

function entityColor(type: string): string {
  return ENTITY_COLORS[type] ?? '#8B949E';
}

// ── Layout ────────────────────────────────────────────────────────────────────

type Pos = { x: number; y: number };

function computeLayout(
  focus: GraphNodeDTO,
  nodes: GraphNodeDTO[],
): Map<string, Pos> {
  const positions = new Map<string, Pos>();
  positions.set(focus.entity_id, { x: CX, y: CY });

  if (nodes.length === 0) return positions;

  const depth1 = nodes.filter((n) => n.bfs_depth <= 1);
  const depth2 = nodes.filter((n) => n.bfs_depth >= 2);

  const sorted1 = [...depth1].sort(
    (a, b) =>
      a.entity_type !== b.entity_type
        ? a.entity_type.localeCompare(b.entity_type)
        : a.entity_id.localeCompare(b.entity_id),
  );
  const sorted2 = [...depth2].sort(
    (a, b) =>
      a.entity_type !== b.entity_type
        ? a.entity_type.localeCompare(b.entity_type)
        : a.entity_id.localeCompare(b.entity_id),
  );

  const hasTwo = sorted2.length > 0;
  const r1 = hasTwo ? 155 : Math.min(195, Math.max(120, sorted1.length * 14));
  const r2 = 260;

  sorted1.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / sorted1.length - Math.PI / 2;
    positions.set(n.entity_id, { x: CX + r1 * Math.cos(angle), y: CY + r1 * Math.sin(angle) });
  });
  sorted2.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / sorted2.length - Math.PI / 2;
    positions.set(n.entity_id, { x: CX + r2 * Math.cos(angle), y: CY + r2 * Math.sin(angle) });
  });

  return positions;
}

// ── Relationship label abbreviations ─────────────────────────────────────────

const REL_SHORT: Record<string, string> = {
  CONTAINS: 'CONT',
  EMPLOYS: 'EMP',
  OPERATES: 'OPS',
  STORES: 'STOR',
  ASSIGNED_TO: 'ASGN',
  SUPPORTS: 'SUPP',
  BELONGS_TO: 'BLNG',
  REQUIRES: 'REQ',
  FULFILLS: 'FLFL',
  CONSTRAINED_BY: 'CSTR',
};

function relShort(rel: string): string {
  return REL_SHORT[rel] ?? rel.slice(0, 4);
}

// ── Scenario badge ────────────────────────────────────────────────────────────

function ScenarioBadge({ x, y }: { x: number; y: number }) {
  return (
    <circle cx={x} cy={y} r={5} fill="#F85149" stroke="#0D1117" strokeWidth={1} />
  );
}

// ── LIVE changed badge ────────────────────────────────────────────────────────

function LiveChangedBadge({ x, y, w }: { x: number; y: number; w: number }) {
  return (
    <g>
      <rect
        x={x + w - 28}
        y={y - 6}
        width={26}
        height={10}
        rx={2}
        fill="#E3B34122"
        stroke="#E3B341"
        strokeWidth={0.8}
      />
      <text
        x={x + w - 15}
        y={y - 1}
        textAnchor="middle"
        dominantBaseline="middle"
        fill="#E3B341"
        fontFamily="monospace"
        fontSize={5}
        fontWeight="bold"
      >
        CHANGED
      </text>
    </g>
  );
}

// ── Node card ─────────────────────────────────────────────────────────────────

interface NodeCardProps {
  node: GraphNodeDTO;
  isFocus: boolean;
  isSelected: boolean;
  pos: Pos;
  zoom: number;
  zoomLevel: string;
  onClick: (id: string) => void;
  liveChange?: ChangedEntityDTO | null;
}

function NodeCard({ node, isFocus, isSelected, pos, zoom, zoomLevel, onClick, liveChange }: NodeCardProps) {
  const color = entityColor(node.entity_type);
  const w = isFocus ? FOCUS_W : NODE_W;
  const h = isFocus ? FOCUS_H : NODE_H;
  const x = pos.x - w / 2;
  const y = pos.y - h / 2;

  const isLiveChanged = !!liveChange;
  // Border priority: selected (blue) > live-changed (yellow) > scenario-affected (red) > type color
  const borderColor = isSelected
    ? '#58A6FF'
    : isLiveChanged
    ? '#E3B341'
    : node.scenario_affected
    ? '#F85149'
    : color;
  const bgColor = isFocus ? '#1C2128' : '#161B22';
  const borderWidth = isSelected ? 1.5 : isLiveChanged ? 1.5 : 1;

  const labelFontSize = isFocus ? 8 : 7;
  const typeFontSize = 5.5;

  const shortLabel = node.label.length > (isFocus ? 16 : 12)
    ? node.label.slice(0, isFocus ? 15 : 11) + '…'
    : node.label;

  return (
    <g
      onClick={() => onClick(node.entity_id)}
      style={{ cursor: 'pointer' }}
      data-testid={isFocus ? 'graph-focus-node' : 'graph-node'}
      data-entity-id={node.entity_id}
      data-entity-type={node.entity_type}
    >
      <rect
        x={x} y={y} width={w} height={h}
        rx={3} ry={3}
        fill={bgColor}
        stroke={borderColor}
        strokeWidth={borderWidth}
        opacity={isSelected ? 1 : 0.9}
      />
      {/* Type stripe */}
      <rect
        x={x} y={y} width={w} height={4}
        rx={3} ry={0}
        fill={color}
        opacity={0.8}
      />
      {/* Label */}
      {zoomLevel !== 'OVERVIEW' && (
        <text
          x={pos.x}
          y={pos.y - (isFocus ? 4 : 3)}
          textAnchor="middle"
          dominantBaseline="middle"
          fill="#C9D1D9"
          fontFamily="monospace"
          fontSize={labelFontSize}
          fontWeight={isFocus ? 700 : 400}
        >
          {shortLabel}
        </text>
      )}
      {/* Entity type */}
      {zoomLevel === 'DETAIL' && (
        <text
          x={pos.x}
          y={pos.y + (isFocus ? 9 : 7)}
          textAnchor="middle"
          dominantBaseline="middle"
          fill={color}
          fontFamily="monospace"
          fontSize={typeFontSize}
          opacity={0.7}
        >
          {node.entity_type.toUpperCase()}
        </text>
      )}
      {node.scenario_affected && !isLiveChanged && (
        <ScenarioBadge x={x + w - 3} y={y + 3} />
      )}
      {isLiveChanged && (
        <LiveChangedBadge x={x} y={y} w={w} />
      )}
      {/* LIVE state transition — show BASE→LIVE for status field when changed */}
      {isLiveChanged && zoomLevel === 'DETAIL' && liveChange && (() => {
        const statusField = liveChange.changed_fields.find((cf) => cf.field === 'status');
        if (!statusField) return null;
        return (
          <text
            x={pos.x}
            y={pos.y + (isFocus ? 16 : 12)}
            textAnchor="middle"
            dominantBaseline="middle"
            fill="#E3B341"
            fontFamily="monospace"
            fontSize={4.5}
            opacity={0.85}
          >
            {String(statusField.before_value ?? '?').toUpperCase()}
            {' → '}
            {String(statusField.after_value ?? '?').toUpperCase()}
          </text>
        );
      })()}
    </g>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

interface OperationalGraphProps {
  focusNode: GraphNodeDTO;
  nodes: GraphNodeDTO[];
  edges: GraphEdgeDTO[];
  truncated?: boolean;
  truncatedFrom?: number | null;
  selectedNodeId?: string | null;
  onNodeClick?: (id: string) => void;
  /** Phase 17D: LIVE changed entities by entity_id. Non-null when worldView=live. */
  liveChangedEntities?: Map<string, ChangedEntityDTO>;
}

export default function OperationalGraph({
  focusNode,
  nodes,
  edges,
  truncated,
  truncatedFrom,
  selectedNodeId,
  onNodeClick,
  liveChangedEntities,
}: OperationalGraphProps) {
  const [zoom, setZoom] = useState(ZOOM_DEFAULT);
  const zoomLevel = getSemanticZoomLevel(zoom);

  const zoomIn = useCallback(() => setZoom((z) => Math.min(ZOOM_MAX, +(z + ZOOM_STEP).toFixed(2))), []);
  const zoomOut = useCallback(() => setZoom((z) => Math.max(ZOOM_MIN, +(z - ZOOM_STEP).toFixed(2))), []);
  const zoomReset = useCallback(() => setZoom(ZOOM_DEFAULT), []);

  const positions = useMemo(() => computeLayout(focusNode, nodes), [focusNode, nodes]);

  const handleNodeClick = useCallback(
    (id: string) => { if (onNodeClick) onNodeClick(id); },
    [onNodeClick],
  );

  const allNodes: GraphNodeDTO[] = [focusNode, ...nodes];

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      {/* Zoom controls */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: '4px', px: '2px' }}>
        {[
          { label: '−', action: zoomOut, disabled: zoom <= ZOOM_MIN },
          { label: `${Math.round(zoom * 100)}%`, action: zoomReset, disabled: false },
          { label: '+', action: zoomIn, disabled: zoom >= ZOOM_MAX },
        ].map(({ label, action, disabled }) => (
          <Box
            key={label}
            component="button"
            onClick={action}
            disabled={disabled}
            data-testid={`zoom-${label === '−' ? 'out' : label === '+' ? 'in' : 'reset'}`}
            sx={{
              background: 'transparent', border: '1px solid #21262D',
              borderRadius: '3px', px: '6px', py: '2px',
              fontFamily: 'monospace', fontSize: label === '%' ? '0.58rem' : '0.8rem',
              color: disabled ? '#30363D' : '#6E7681', cursor: disabled ? 'default' : 'pointer',
              '&:hover:not(:disabled)': { color: '#8B949E', borderColor: '#30363D' },
            }}
          >
            {label}
          </Box>
        ))}
        {truncated && (
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#D29922', ml: '6px' }}>
            SHOWING {nodes.length} OF {truncatedFrom ?? '?'} NEIGHBORS
          </Typography>
        )}
        <Box sx={{ flexGrow: 1 }} />
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#30363D' }}>
          CANONICAL OPERATIONAL GRAPH
        </Typography>
      </Box>

      {/* Graph canvas */}
      <Box
        data-testid="operational-graph-canvas"
        sx={{ overflow: 'auto', border: '1px solid #161B22', borderRadius: '4px', background: '#0D1117' }}
      >
        <Box
          sx={{
            transformOrigin: 'top left',
            transform: `scale(${zoom})`,
            display: 'inline-block',
            width: Math.round(CANVAS_W * zoom),
            height: Math.round(CANVAS_H * zoom),
          }}
        >
          <svg
            width={CANVAS_W}
            height={CANVAS_H}
            style={{ display: 'block' }}
            aria-label="Operational graph"
            role="img"
          >
            {/* Radial ring guides */}
            <circle cx={CX} cy={CY} r={155} fill="none" stroke="#161B22" strokeWidth={1} />
            {nodes.some((n) => n.bfs_depth >= 2) && (
              <circle cx={CX} cy={CY} r={260} fill="none" stroke="#161B22" strokeWidth={1} />
            )}

            {/* Edges */}
            {edges.map((edge) => {
              const src = positions.get(edge.source_id);
              const tgt = positions.get(edge.target_id);
              if (!src || !tgt) return null;
              const isHighlighted =
                edge.source_id === selectedNodeId || edge.target_id === selectedNodeId;
              const edgeColor = isHighlighted ? '#58A6FF' : '#21262D';
              const midX = (src.x + tgt.x) / 2;
              const midY = (src.y + tgt.y) / 2;
              return (
                <g key={edge.edge_id} data-testid="graph-edge" data-rel={edge.relationship_type}>
                  <line
                    x1={src.x} y1={src.y} x2={tgt.x} y2={tgt.y}
                    stroke={edgeColor}
                    strokeWidth={isHighlighted ? 1.5 : 0.8}
                    opacity={isHighlighted ? 0.7 : 0.35}
                  />
                  {zoomLevel === 'DETAIL' && (
                    <text
                      x={midX} y={midY - 3}
                      textAnchor="middle"
                      fill="#484F58"
                      fontFamily="monospace"
                      fontSize={4.5}
                    >
                      {relShort(edge.relationship_type)}
                    </text>
                  )}
                </g>
              );
            })}

            {/* Nodes */}
            {allNodes.map((node) => {
              const pos = positions.get(node.entity_id);
              if (!pos) return null;
              const isFocus = node.entity_id === focusNode.entity_id;
              const liveChange = liveChangedEntities?.get(node.entity_id) ?? null;
              return (
                <NodeCard
                  key={node.entity_id}
                  node={node}
                  isFocus={isFocus}
                  isSelected={node.entity_id === selectedNodeId}
                  pos={pos}
                  zoom={zoom}
                  zoomLevel={zoomLevel}
                  onClick={handleNodeClick}
                  liveChange={liveChange}
                />
              );
            })}
          </svg>
        </Box>
      </Box>
    </Box>
  );
}
