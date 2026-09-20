/**
 * StateDelta — UX-1D.3
 *
 * Shows before/after for a single entity's changed fields.
 * Hides unchanged fields. Visual diff: changed values highlighted.
 *
 * All data from structured props. No LLM calls. No inference.
 */

import React from 'react';
import { Box, Typography } from '@mui/material';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface FieldDelta {
  /** Field name for display (e.g., "Status", "Assigned worker"). */
  label: string;
  /** Value before the action. Omit if field didn't exist before. */
  before?: string | number | null;
  /** Value after the action. Omit if field was removed. */
  after?: string | number | null;
}

export interface StateDeltaProps {
  /** Entity identifier (e.g., "TASK-000001"). */
  entityId: string;
  /** Entity type label (e.g., "Task", "Worker", "Wave"). */
  entityType?: string;
  /** Field-level deltas. Only changed fields should be included. */
  deltas: FieldDelta[];
}

// ── Sub-components ────────────────────────────────────────────────────────────

function DeltaRow({ field }: { field: FieldDelta }) {
  const before = field.before != null ? String(field.before) : '—';
  const after  = field.after  != null ? String(field.after)  : '—';
  const changed = before !== after;

  return (
    <Box
      data-testid={`state-delta-row-${field.label.toLowerCase().replace(/\s+/g, '-')}`}
      sx={{ display: 'flex', alignItems: 'baseline', gap: 0.75, py: 0.2 }}
    >
      {/* Field label */}
      <Typography sx={{
        fontFamily: 'monospace',
        fontSize: '0.6rem',
        color: '#484F58',
        width: 130,
        flexShrink: 0,
      }}>
        {field.label}
      </Typography>

      {/* Before */}
      <Typography
        data-testid="delta-before"
        sx={{
          fontFamily: 'monospace',
          fontSize: '0.63rem',
          color: changed ? '#6E7681' : '#8B949E',
          textDecoration: changed ? 'line-through' : 'none',
        }}
      >
        {before}
      </Typography>

      {changed && (
        <>
          {/* Arrow */}
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#484F58' }}>
            →
          </Typography>

          {/* After — highlighted when changed */}
          <Typography
            data-testid="delta-after"
            sx={{
              fontFamily: 'monospace',
              fontSize: '0.63rem',
              fontWeight: 700,
              color: '#58A6FF',
            }}
          >
            {after}
          </Typography>
        </>
      )}
    </Box>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function StateDelta({ entityId, entityType, deltas }: StateDeltaProps) {
  if (deltas.length === 0) {return null;}

  return (
    <Box
      data-testid={`state-delta-${entityId}`}
      sx={{
        p: 1,
        background: '#0D1117',
        border: '1px solid #21262D',
        borderRadius: '4px',
      }}
    >
      {/* Entity header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.5 }}>
        {entityType && (
          <Typography sx={{
            fontFamily: 'monospace',
            fontSize: '0.55rem',
            color: '#484F58',
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
          }}>
            {entityType}
          </Typography>
        )}
        <Typography sx={{
          fontFamily: 'monospace',
          fontSize: '0.65rem',
          fontWeight: 700,
          color: '#E6EDF3',
        }}>
          {entityId}
        </Typography>
      </Box>

      {/* Delta rows */}
      {deltas.map((field) => (
        <DeltaRow key={field.label} field={field} />
      ))}
    </Box>
  );
}
