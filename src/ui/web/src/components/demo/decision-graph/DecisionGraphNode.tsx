/**
 * DecisionGraphNode — individual node card for the progressive DecisionGraph.
 *
 * Color scheme per node type matches the governance-chain semantics:
 *   evidence / agent / assessment → cool / neutral
 *   proposal / approval / reconciliation → amber (human-decision territory)
 *   decision_engine → red (deterministic policy boundary)
 *   execution / outcome → green (delivery confirmed)
 */

import React from 'react';
import { Box, Typography } from '@mui/material';
import { DecisionGraphNode } from './graphTypes';

// ── Color configuration ───────────────────────────────────────────────────────

interface NodeColors {
  border: string;
  accent: string;
  bg: string;
}

const NODE_COLORS: Record<string, NodeColors> = {
  evidence:        { border: '#A371F7', accent: '#A371F7', bg: '#1A1025' },
  agent:           { border: '#3FB950', accent: '#3FB950', bg: '#0F1A13' },
  model_gateway:   { border: '#58A6FF', accent: '#58A6FF', bg: '#0D1829' },
  model:           { border: '#58A6FF', accent: '#58A6FF', bg: '#0D1829' },
  skill:           { border: '#39D2C0', accent: '#39D2C0', bg: '#0D1E1D' },
  assessment:      { border: '#8B949E', accent: '#8B949E', bg: '#161B22' },
  recommendation:  { border: '#388BFD', accent: '#388BFD', bg: '#0D1829' },
  proposal:        { border: '#D29922', accent: '#D29922', bg: '#1E1805' },
  decision_engine: { border: '#F85149', accent: '#F85149', bg: '#200D0C' },
  decision:        { border: '#8B949E', accent: '#8B949E', bg: '#161B22' },   // overridden by outcome
  approval:        { border: '#D29922', accent: '#D29922', bg: '#1E1805' },
  executor:        { border: '#3FB950', accent: '#3FB950', bg: '#0F1A13' },
  mcp:             { border: '#58A6FF', accent: '#58A6FF', bg: '#0D1829' },
  execution:       { border: '#8B949E', accent: '#8B949E', bg: '#161B22' },   // overridden by status
  reconciliation:  { border: '#D29922', accent: '#D29922', bg: '#1E1805' },
  outcome:         { border: '#3FB950', accent: '#3FB950', bg: '#0F1A13' },
};

// Decision / execution outcome-based color override
function resolveColors(node: DecisionGraphNode): NodeColors {
  const base = NODE_COLORS[node.type] ?? { border: '#484F58', accent: '#484F58', bg: '#161B22' };

  if (node.type === 'decision') {
    const outcome = (node.label ?? '').toUpperCase();
    if (outcome === 'APPROVED')               return { border: '#3FB950', accent: '#3FB950', bg: '#0F1A13' };
    if (outcome === 'REQUIRES_HUMAN_APPROVAL') return { border: '#D29922', accent: '#D29922', bg: '#1E1805' };
    if (outcome === 'REJECTED')               return { border: '#F85149', accent: '#F85149', bg: '#200D0C' };
  }

  if (node.type === 'execution') {
    const status = (node.label ?? '').toLowerCase();
    if (status === 'executed')             return { border: '#3FB950', accent: '#3FB950', bg: '#0F1A13' };
    if (status === 'failed')               return { border: '#F85149', accent: '#F85149', bg: '#200D0C' };
    if (status === 'requires_human_approval') return { border: '#D29922', accent: '#D29922', bg: '#1E1805' };
  }

  if (node.type === 'approval') {
    const status = node.status;
    if (status === 'done')    return { border: '#3FB950', accent: '#3FB950', bg: '#0F1A13' };
    return base; // amber = pending
  }

  return base;
}

// ── Source badge ──────────────────────────────────────────────────────────────

const SOURCE_COLOR: Record<string, string> = {
  LIVE:               '#3FB950',
  DERIVED:            '#484F58',
  VALIDATED_ARTIFACT: '#388BFD',
  LOCAL:              '#8B949E',
};

// ── Component ─────────────────────────────────────────────────────────────────

interface DecisionGraphNodeProps {
  node: DecisionGraphNode;
  selected: boolean;
  onClick: (nodeId: string) => void;
  width: number;
  height: number;
}

export default function DecisionGraphNodeCard({
  node,
  selected,
  onClick,
  width,
  height,
}: DecisionGraphNodeProps) {
  const colors = resolveColors(node);
  const sourceColor = SOURCE_COLOR[node.source] ?? '#484F58';

  const borderColor = selected ? colors.accent : colors.border;
  const borderWidth = selected ? 2 : 1;
  const boxShadow   = selected ? `0 0 8px ${colors.accent}55` : 'none';

  return (
    <Box
      data-testid={`graph-node-${node.id}`}
      onClick={() => onClick(node.id)}
      sx={{
        width,
        height,
        background: colors.bg,
        border: `${borderWidth}px solid ${borderColor}`,
        borderRadius: '6px',
        cursor: 'pointer',
        boxShadow,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        px: '8px',
        py: '6px',
        userSelect: 'none',
        transition: 'box-shadow 0.15s ease, border-color 0.15s ease',
        '&:hover': {
          boxShadow: `0 0 6px ${colors.accent}44`,
          borderColor: colors.accent,
        },
      }}
    >
      {/* Top: node type label */}
      <Typography sx={{
        fontFamily: 'monospace',
        fontSize: '0.5rem',
        fontWeight: 700,
        color: colors.accent,
        textTransform: 'uppercase',
        letterSpacing: '0.1em',
        lineHeight: 1,
      }}>
        {node.type.replace(/_/g, ' ')}
      </Typography>

      {/* Center: label */}
      <Typography sx={{
        fontFamily: 'monospace',
        fontSize: '0.62rem',
        fontWeight: 600,
        color: '#C9D1D9',
        lineHeight: 1.2,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      }}>
        {node.label}
      </Typography>

      {/* Bottom: subtitle or source */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
        {node.subtitle && (
          <Typography sx={{
            fontFamily: 'monospace',
            fontSize: '0.5rem',
            color: '#484F58',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            flexGrow: 1,
          }}>
            {node.subtitle}
          </Typography>
        )}
        <Box sx={{
          fontFamily: 'monospace',
          fontSize: '0.45rem',
          color: sourceColor,
          border: `1px solid ${sourceColor}44`,
          borderRadius: '2px',
          px: '3px',
          py: '1px',
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
          flexShrink: 0,
        }}>
          {node.source === 'VALIDATED_ARTIFACT' ? 'VA' : node.source}
        </Box>
      </Box>
    </Box>
  );
}
