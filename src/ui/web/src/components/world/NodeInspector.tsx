/**
 * NodeInspector — side panel for a selected entity in the Operational Graph.
 * Shows entity type, ID, label, attributes, relationships, and scenario impact.
 */

import React from 'react';
import { Box, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { worldAPI, GraphNodeDTO, GraphEntityDetailResponse } from '../../services/worldAPI';

interface NodeInspectorProps {
  selectedNode: GraphNodeDTO;
  onClose: () => void;
}

const ENTITY_COLORS: Record<string, string> = {
  warehouse: '#C9D1D9', zone: '#8B949E', location: '#6E7681',
  worker: '#3FB950', shift: '#2EA043', equipment: '#F0883E',
  wave: '#58A6FF', task: '#A371F7', carrier_cutoff: '#D29922',
  order: '#BC8CFF', sku: '#DB6D28', inventory_position: '#6E7681',
};

function Row({ label, value }: { label: string; value: string | number | boolean | null | undefined }) {
  if (value === null || value === undefined || value === '') return null;
  return (
    <Box sx={{ display: 'flex', gap: '8px', mb: '3px' }}>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#484F58', minWidth: 80, flexShrink: 0 }}>
        {label}
      </Typography>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#8B949E', wordBreak: 'break-word' }}>
        {String(value)}
      </Typography>
    </Box>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Box sx={{ mb: '10px' }}>
      <Typography sx={{
        fontFamily: 'monospace', fontSize: '0.55rem', fontWeight: 700,
        color: '#484F58', letterSpacing: '0.12em', textTransform: 'uppercase', mb: '5px',
      }}>
        {title}
      </Typography>
      {children}
    </Box>
  );
}

function EntityDetailPanel({ detail }: { detail: GraphEntityDetailResponse }) {
  const color = ENTITY_COLORS[detail.entity_type] ?? '#8B949E';

  return (
    <>
      <Section title="State">
        <Row label="Type" value={detail.entity_type.toUpperCase()} />
        <Row label="ID" value={detail.entity_id} />
        {detail.scenario_affected && (
          <Box sx={{
            mt: '5px', px: '6px', py: '3px',
            background: '#1A0A0A', border: '1px solid #F8514944',
            borderRadius: '3px',
          }}>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#F85149' }}>
              ⚠ SCENARIO AFFECTED{detail.scenario_severity ? ` — ${detail.scenario_severity}` : ''}
            </Typography>
          </Box>
        )}
      </Section>

      <Section title="Relationships">
        <Row label="Outgoing" value={detail.outgoing_count} />
        <Row label="Incoming" value={detail.incoming_count} />
        {detail.direct_relationships.slice(0, 8).map((edge) => (
          <Box key={edge.edge_id} sx={{
            display: 'flex', gap: '4px', mb: '2px', alignItems: 'center',
          }}
            data-testid="inspector-relationship-row"
          >
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: color, opacity: 0.8, minWidth: 50 }}>
              {edge.relationship_type}
            </Typography>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58' }}>
              →
            </Typography>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#6E7681', wordBreak: 'break-all' }}>
              {edge.target_id === detail.entity_id ? edge.source_id : edge.target_id}
            </Typography>
            {edge.temporal && (
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#D29922', ml: 'auto', flexShrink: 0 }}>
                {edge.active ? 'ACTIVE' : 'EXP'}
              </Typography>
            )}
          </Box>
        ))}
        {detail.direct_relationships.length > 8 && (
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#30363D', mt: '2px' }}>
            +{detail.direct_relationships.length - 8} more
          </Typography>
        )}
      </Section>

      <Section title="Attributes">
        {Object.entries(detail.attributes).map(([k, v]) => (
          <Row key={k} label={k} value={v} />
        ))}
      </Section>
    </>
  );
}

export default function NodeInspector({ selectedNode, onClose }: NodeInspectorProps) {
  const color = ENTITY_COLORS[selectedNode.entity_type] ?? '#8B949E';

  const { data: detail, isLoading, isError } = useQuery({
    queryKey: ['worldGraphEntity', selectedNode.entity_id],
    queryFn: () => worldAPI.getGraphEntity(selectedNode.entity_id),
    staleTime: 30_000,
    retry: 1,
  });

  return (
    <Box
      data-testid="node-inspector"
      sx={{
        width: 220,
        flexShrink: 0,
        background: '#0D1117',
        border: '1px solid #21262D',
        borderRadius: '4px',
        p: '10px',
        overflow: 'auto',
        maxHeight: 480,
      }}
    >
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: '8px' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Box sx={{ width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0 }} />
          <Typography sx={{
            fontFamily: 'monospace', fontSize: '0.7rem', fontWeight: 700, color: '#C9D1D9',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 150,
          }}>
            {selectedNode.label}
          </Typography>
        </Box>
        <Box
          component="button"
          onClick={onClose}
          data-testid="inspector-close"
          sx={{
            background: 'transparent', border: 'none', cursor: 'pointer',
            color: '#484F58', fontFamily: 'monospace', fontSize: '0.7rem', p: 0,
            '&:hover': { color: '#8B949E' },
          }}
        >
          ✕
        </Box>
      </Box>

      {/* Summary from node DTO (always available) */}
      <Section title="Identity">
        <Row label="Type" value={selectedNode.entity_type.toUpperCase()} />
        <Row label="ID" value={selectedNode.entity_id} />
        <Row label="Depth" value={selectedNode.bfs_depth === 0 ? 'FOCUS' : selectedNode.bfs_depth} />
      </Section>

      {/* Detailed attributes from entity endpoint */}
      {isLoading && (
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#484F58' }}>
          Loading…
        </Typography>
      )}
      {isError && (
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#F85149' }}
          data-testid="inspector-error"
        >
          Failed to load entity detail
        </Typography>
      )}
      {detail && <EntityDetailPanel detail={detail} />}
    </Box>
  );
}
