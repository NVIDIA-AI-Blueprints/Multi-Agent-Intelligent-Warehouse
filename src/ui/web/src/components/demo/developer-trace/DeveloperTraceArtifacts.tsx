/**
 * DeveloperTraceArtifacts.tsx — Artifact lineage visualization for the developer trace.
 *
 * Shows the chain:
 *   snapshot_id → proposal_id(s) → decision_id(s) → approval_id(s) → execution_id(s)
 *
 * All IDs truncated to first 8 chars with full ID on hover (title attribute).
 * Multi-branch proposals are labeled [A], [B], etc.
 */

import React from 'react';
import { Box, Typography } from '@mui/material';
import { TraceArtifactLineage } from './developerTraceTypes';

// ── Props ──────────────────────────────────────────────────────────────────────

interface DeveloperTraceArtifactsProps {
  artifacts: TraceArtifactLineage;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

const BRANCH_LABELS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('');

function truncId(id: string): string {
  return id.length > 8 ? `${id.slice(0, 8)}…` : id;
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function LayerLabel({ label }: { label: string }) {
  return (
    <Typography sx={{
      fontFamily: 'monospace',
      fontSize: '0.55rem',
      color: '#484F58',
      textTransform: 'uppercase',
      letterSpacing: '0.1em',
      mb: '2px',
      mt: '2px',
    }}>
      {label}
    </Typography>
  );
}

function Arrow() {
  return (
    <Typography sx={{
      fontFamily: 'monospace',
      fontSize: '0.75rem',
      color: '#30363D',
      textAlign: 'center',
      my: '2px',
      userSelect: 'none',
    }}>
      ↓
    </Typography>
  );
}

function IdEntry({
  branchLabel,
  id,
  action,
  suffix,
  color = '#8B949E',
}: {
  branchLabel?: string;
  id: string;
  action?: string | null;
  suffix?: string;
  color?: string;
}) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 0.75, mb: '2px' }}>
      {branchLabel && (
        <Typography sx={{
          fontFamily: 'monospace',
          fontSize: '0.6rem',
          color: '#58A6FF',
          flexShrink: 0,
        }}>
          [{branchLabel}]
        </Typography>
      )}
      {action && (
        <Typography sx={{
          fontFamily: 'monospace',
          fontSize: '0.6rem',
          color: '#6E7681',
          flexShrink: 0,
          maxWidth: 160,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}>
          {action}
        </Typography>
      )}
      <Typography
        title={id}
        sx={{
          fontFamily: 'monospace',
          fontSize: '0.6rem',
          color,
          letterSpacing: '0.04em',
          cursor: 'help',
        }}
      >
        {truncId(id)}
      </Typography>
      {suffix && (
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58' }}>
          {suffix}
        </Typography>
      )}
    </Box>
  );
}

function EmptyLayer() {
  return (
    <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#30363D', mb: '2px' }}>
      —
    </Typography>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function DeveloperTraceArtifacts({ artifacts }: DeveloperTraceArtifactsProps) {
  const multiProposal = artifacts.proposalIds.length > 1;

  return (
    <Box>
      {/* snapshot_id */}
      <LayerLabel label="snapshot_id" />
      {artifacts.snapshotId ? (
        <IdEntry id={artifacts.snapshotId} color="#3FB950" />
      ) : (
        <EmptyLayer />
      )}

      <Arrow />

      {/* proposal_id(s) */}
      <LayerLabel label="proposal_id(s)" />
      {artifacts.proposalIds.length === 0 ? (
        <EmptyLayer />
      ) : (
        artifacts.proposalIds.map((p, i) => (
          <IdEntry
            key={p.proposalId}
            branchLabel={multiProposal ? BRANCH_LABELS[i] : undefined}
            id={p.proposalId}
            action={p.action}
            color="#D29922"
          />
        ))
      )}

      <Arrow />

      {/* decision_id(s) */}
      <LayerLabel label="decision_id(s)" />
      {artifacts.decisionIds.length === 0 ? (
        <EmptyLayer />
      ) : (
        artifacts.decisionIds.map((d, i) => (
          <IdEntry
            key={d.decisionId}
            branchLabel={multiProposal ? BRANCH_LABELS[i] : undefined}
            id={d.decisionId}
            suffix={d.outcome ?? undefined}
            color="#D29922"
          />
        ))
      )}

      <Arrow />

      {/* approval_id(s) */}
      <LayerLabel label="approval_id(s)" />
      {artifacts.approvalIds.length === 0 ? (
        <EmptyLayer />
      ) : (
        artifacts.approvalIds.map((a, i) => (
          <IdEntry
            key={a.approvalId}
            branchLabel={multiProposal ? BRANCH_LABELS[i] : undefined}
            id={a.approvalId}
            suffix={a.state}
            color="#58A6FF"
          />
        ))
      )}

      <Arrow />

      {/* execution_id(s) */}
      <LayerLabel label="execution_id(s)" />
      {artifacts.executionIds.length === 0 ? (
        <EmptyLayer />
      ) : (
        artifacts.executionIds.map((e, i) => (
          <IdEntry
            key={e.executionId}
            branchLabel={multiProposal ? BRANCH_LABELS[i] : undefined}
            id={e.executionId}
            suffix={e.status ?? undefined}
            color={e.status === 'UNKNOWN' ? '#D29922' : '#3FB950'}
          />
        ))
      )}
    </Box>
  );
}
