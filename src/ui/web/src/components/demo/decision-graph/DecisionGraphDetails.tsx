/**
 * DecisionGraphDetails — selected-node detail panel for the progressive DecisionGraph.
 *
 * Renders when a node is selected. Exposes the selected node and its artifact
 * as clean state for Phase 13D "Why This Decision?" consumption.
 *
 * Layout: slides in from the right alongside the graph, or renders below on
 * narrow containers.
 */

import React from 'react';
import { Box, Typography } from '@mui/material';
import { DecisionGraphNode, NodeSource } from './graphTypes';

// ── Source badge ──────────────────────────────────────────────────────────────

const SOURCE_COLOR: Record<NodeSource, string> = {
  LIVE:               '#3FB950',
  DERIVED:            '#484F58',
  VALIDATED_ARTIFACT: '#388BFD',
  LOCAL:              '#8B949E',
};

const SOURCE_LABEL: Record<NodeSource, string> = {
  LIVE:               'LIVE',
  DERIVED:            'DERIVED',
  VALIDATED_ARTIFACT: 'VALIDATED ARTIFACT',
  LOCAL:              'LOCAL',
};

function SourceBadge({ source }: { source: NodeSource }) {
  const color = SOURCE_COLOR[source] ?? '#484F58';
  return (
    <Box component="span" sx={{
      fontFamily: 'monospace',
      fontSize: '0.55rem',
      fontWeight: 700,
      color,
      border: `1px solid ${color}44`,
      borderRadius: '3px',
      px: '5px',
      py: '1px',
      textTransform: 'uppercase',
      letterSpacing: '0.08em',
    }}>
      {SOURCE_LABEL[source]}
    </Box>
  );
}

function KVRow({ k, v }: { k: string; v: string | number | null | undefined }) {
  if (v === null || v === undefined) return null;
  const display = String(v);
  if (!display) return null;
  return (
    <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1, py: '3px', borderBottom: '1px solid #1C2128' }}>
      <Typography sx={{
        fontFamily: 'monospace',
        fontSize: '0.55rem',
        color: '#484F58',
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
        flexShrink: 0,
        minWidth: 120,
      }}>
        {k}
      </Typography>
      <Typography sx={{
        fontFamily: 'monospace',
        fontSize: '0.65rem',
        color: '#8B949E',
        wordBreak: 'break-all',
      }}>
        {display}
      </Typography>
    </Box>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

interface DecisionGraphDetailsProps {
  /** The selected node — null if nothing selected. */
  selectedNode: DecisionGraphNode | null;
  /** Artifact object reconstructed from node metadata — for Phase 13D consumption. */
  artifact: Record<string, any> | null;
  onClose: () => void;
}

export default function DecisionGraphDetails({
  selectedNode,
  artifact: _artifact,
  onClose,
}: DecisionGraphDetailsProps) {
  if (!selectedNode) return null;

  const metadata = selectedNode.metadata ?? {};

  return (
    <Box
      data-testid="decision-graph-details"
      sx={{
        width: 280,
        flexShrink: 0,
        background: '#161B22',
        border: '1px solid #21262D',
        borderRadius: '6px',
        p: 2,
        display: 'flex',
        flexDirection: 'column',
        gap: 1.5,
        overflow: 'auto',
        maxHeight: '100%',
      }}
    >
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <Box>
          <Typography sx={{
            fontFamily: 'monospace',
            fontSize: '0.52rem',
            fontWeight: 700,
            color: '#484F58',
            textTransform: 'uppercase',
            letterSpacing: '0.1em',
          }}>
            {selectedNode.type.replace(/_/g, ' ')}
          </Typography>
          <Typography sx={{
            fontFamily: 'monospace',
            fontSize: '0.78rem',
            fontWeight: 700,
            color: '#C9D1D9',
            mt: '2px',
          }}>
            {selectedNode.label}
          </Typography>
        </Box>
        <Box
          component="button"
          onClick={onClose}
          sx={{
            background: 'transparent',
            border: 'none',
            cursor: 'pointer',
            fontFamily: 'monospace',
            fontSize: '0.75rem',
            color: '#484F58',
            p: 0,
            '&:hover': { color: '#8B949E' },
          }}
        >
          ✕
        </Box>
      </Box>

      {/* Source badge */}
      <Box>
        <SourceBadge source={selectedNode.source} />
      </Box>

      {/* Artifact ID */}
      {selectedNode.artifact_id && (
        <Box>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.52rem', color: '#484F58', textTransform: 'uppercase', letterSpacing: '0.08em', mb: '4px' }}>
            Artifact ID
          </Typography>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#58A6FF', wordBreak: 'break-all' }}>
            {selectedNode.artifact_id}
          </Typography>
        </Box>
      )}

      {/* Metadata key-value pairs */}
      {Object.keys(metadata).length > 0 && (
        <Box>
          <Typography sx={{
            fontFamily: 'monospace',
            fontSize: '0.52rem',
            fontWeight: 700,
            color: '#484F58',
            textTransform: 'uppercase',
            letterSpacing: '0.1em',
            mb: '6px',
          }}>
            Fields
          </Typography>
          <Box>
            {Object.entries(metadata).map(([k, v]) => (
              <KVRow key={k} k={k} v={v} />
            ))}
          </Box>
        </Box>
      )}

      {/* Layer / column for debugging */}
      <Box sx={{ mt: 'auto', pt: 1, borderTop: '1px solid #1C2128' }}>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#30363D' }}>
          layer {selectedNode.layer} · col {selectedNode.column} · id {selectedNode.id}
        </Typography>
      </Box>
    </Box>
  );
}
