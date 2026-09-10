/**
 * WorldContextSnapshot.tsx — Phase 17E
 *
 * OPERATIONAL CONTEXT AT DECISION TIME panel.
 *
 * Displays the exact bounded graph context that MAIW assembled for a specific
 * historical Copilot turn — captured BEFORE the model call, never reconstructed.
 *
 * Terminology (precise):
 *   OPERATIONAL CONTEXT AT DECISION TIME — historical snapshot (this view)
 *   CURRENT OPERATIONAL CONTEXT          — live reconstruction from canonical graph
 *
 * Architecture constraints:
 *   - Read-only: no governance or execution symbols
 *   - Does NOT call graph/neighbors or reconstruct the context
 *   - Uses GET /api/v1/world/context/by-turn/{turn_id} exclusively
 */

import React, { useState, useEffect } from 'react';
import { Box, Typography, CircularProgress } from '@mui/material';
import { worldAPI, OperationalContextSnapshotResponse } from '../../services/worldAPI';

// ── Props ──────────────────────────────────────────────────────────────────────

export interface SnapshotViewContext {
  turnId: string;
  traceId: string;
  entityLabel: string | null;
  conversationId?: string;
}

interface WorldContextSnapshotProps {
  ctx: SnapshotViewContext;
  onViewDecisionTrace?: (traceId: string) => void;
  onViewCurrentContext?: (entityId: string, entityLabel: string | null) => void;
  onReturnToCopilot?: () => void;
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function MetaRow({ label, value }: { label: string; value: string | number | boolean | null | undefined }) {
  if (value == null || value === '') return null;
  return (
    <Box sx={{ display: 'flex', gap: '10px', alignItems: 'baseline' }}>
      <Typography sx={{
        fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58',
        textTransform: 'uppercase', letterSpacing: '0.08em',
        minWidth: '120px', flexShrink: 0,
      }}>
        {label}
      </Typography>
      <Typography sx={{
        fontFamily: 'monospace', fontSize: '0.68rem', color: '#8B949E',
        wordBreak: 'break-all',
      }}>
        {String(value)}
      </Typography>
    </Box>
  );
}

function EntityTypeChip({ type }: { type: string }) {
  return (
    <Box component="span" sx={{
      fontFamily: 'monospace', fontSize: '0.55rem', color: '#58A6FF',
      border: '1px solid #1F6FEB33', borderRadius: '3px',
      px: '4px', py: '1px',
    }}>
      {type}
    </Box>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function WorldContextSnapshot({
  ctx,
  onViewDecisionTrace,
  onViewCurrentContext,
  onReturnToCopilot,
}: WorldContextSnapshotProps) {
  const [snapshot, setSnapshot] = useState<OperationalContextSnapshotResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    setSnapshot(null);
    worldAPI.getContextByTurn(ctx.turnId).then(s => {
      setSnapshot(s);
      setLoading(false);
    }).catch(err => {
      const msg = err?.response?.status === 404
        ? 'No context snapshot was captured for this turn (turn may have been degraded or ungrounded).'
        : `Failed to load context snapshot: ${err?.message ?? 'Unknown error'}`;
      setError(msg);
      setLoading(false);
    });
  }, [ctx.turnId]);

  return (
    <Box
      data-testid="world-context-snapshot"
      sx={{ display: 'flex', flexDirection: 'column', gap: 2, p: 2 }}
    >
      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Typography sx={{
          fontFamily: 'monospace', fontSize: '0.62rem', fontWeight: 700,
          color: '#58A6FF', textTransform: 'uppercase', letterSpacing: '0.12em',
        }}>
          Operational Context at Decision Time
        </Typography>
        {onReturnToCopilot && (
          <Box
            component="button"
            data-testid="return-to-copilot"
            onClick={onReturnToCopilot}
            sx={{
              background: 'transparent', border: '1px solid #21262D',
              borderRadius: '3px', px: '8px', py: '3px',
              fontFamily: 'monospace', fontSize: '0.58rem',
              color: '#484F58', cursor: 'pointer',
              '&:hover': { color: '#C9D1D9', borderColor: '#484F58' },
            }}
          >
            RETURN TO COPILOT
          </Box>
        )}
      </Box>

      {/* ── Loading ──────────────────────────────────────────────────────────── */}
      {loading && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 2 }}>
          <CircularProgress size={16} sx={{ color: '#484F58' }} />
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', color: '#484F58' }}>
            Loading historical context…
          </Typography>
        </Box>
      )}

      {/* ── Error / not found ─────────────────────────────────────────────────── */}
      {error && (
        <Box sx={{
          background: '#160B0B', border: '1px solid #F8514944',
          borderRadius: '4px', p: '12px',
        }}>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.7rem', color: '#F85149' }}>
            {error}
          </Typography>
          <Typography sx={{
            fontFamily: 'monospace', fontSize: '0.62rem', color: '#484F58', mt: '6px',
          }}>
            CURRENT OPERATIONAL CONTEXT is still available via VIEW OPERATIONAL CONTEXT.
          </Typography>
        </Box>
      )}

      {/* ── Snapshot loaded ──────────────────────────────────────────────────── */}
      {snapshot && (
        <>
          {/* ── Historical context banner ──────────────────────────────────── */}
          <Box
            data-testid="historical-context-banner"
            sx={{
              background: '#0D1420',
              border: '1px solid #1F6FEB44',
              borderLeft: '3px solid #58A6FF',
              borderRadius: '4px',
              p: '12px',
              display: 'flex',
              flexDirection: 'column',
              gap: '5px',
            }}
          >
            <Typography sx={{
              fontFamily: 'monospace', fontSize: '0.58rem', fontWeight: 700,
              color: '#58A6FF', textTransform: 'uppercase', letterSpacing: '0.12em',
              mb: '4px',
            }}>
              Operational Context at Decision Time
            </Typography>

            <MetaRow label="Turn" value={snapshot.turn_id} />
            <MetaRow label="Trace" value={snapshot.trace_id} />
            <MetaRow label="Focus" value={snapshot.focus_label} />
            <MetaRow label="Focus Type" value={snapshot.focus_entity_type} />
            <MetaRow label="Warehouse State" value={snapshot.warehouse_state_snapshot_id ?? 'not recorded'} />
            <MetaRow label="DataPack" value={snapshot.dataset_id} />
            <MetaRow label="Checksum" value={snapshot.datapack_checksum} />
            <MetaRow label="Entities" value={snapshot.entity_count} />
            <MetaRow label="Relationships" value={snapshot.relationship_count} />
            <MetaRow label="Depth" value={snapshot.depth} />
            <MetaRow label="Truncated" value={snapshot.truncated ? 'YES — capped at 50 entities' : 'no'} />
            <MetaRow label="Captured At" value={snapshot.captured_at} />

            {/* ── Action buttons ─────────────────────────────────────────── */}
            <Box sx={{ display: 'flex', gap: '8px', mt: '6px', flexWrap: 'wrap' }}>
              {onViewDecisionTrace && (
                <Box
                  component="button"
                  data-testid="view-decision-trace"
                  onClick={() => onViewDecisionTrace(snapshot.trace_id)}
                  sx={{
                    background: 'transparent',
                    border: '1px solid #3FB95044',
                    borderRadius: '3px', px: '8px', py: '3px',
                    fontFamily: 'monospace', fontSize: '0.58rem',
                    color: '#3FB950', cursor: 'pointer',
                    '&:hover': { background: '#0D1B0D', borderColor: '#3FB950' },
                  }}
                >
                  VIEW DECISION TRACE
                </Box>
              )}
              {onViewCurrentContext && snapshot.focus_entity_id && (
                <Box
                  component="button"
                  data-testid="view-current-context"
                  onClick={() => onViewCurrentContext(snapshot.focus_entity_id, snapshot.focus_label)}
                  sx={{
                    background: 'transparent',
                    border: '1px solid #1F6FEB33',
                    borderRadius: '3px', px: '8px', py: '3px',
                    fontFamily: 'monospace', fontSize: '0.58rem',
                    color: '#8B949E', cursor: 'pointer',
                    '&:hover': { color: '#58A6FF', borderColor: '#58A6FF44' },
                  }}
                >
                  VIEW CURRENT CONTEXT
                </Box>
              )}
            </Box>
          </Box>

          {/* ── Current context banner ─────────────────────────────────────── */}
          <Box
            data-testid="current-context-banner"
            sx={{
              background: '#0D1117',
              border: '1px solid #21262D',
              borderLeft: '3px solid #484F58',
              borderRadius: '4px',
              p: '10px',
              display: 'flex',
              flexDirection: 'column',
              gap: '4px',
            }}
          >
            <Typography sx={{
              fontFamily: 'monospace', fontSize: '0.58rem', fontWeight: 700,
              color: '#484F58', textTransform: 'uppercase', letterSpacing: '0.12em',
              mb: '4px',
            }}>
              Current Operational Context
            </Typography>
            <MetaRow label="Focus" value={snapshot.focus_label} />
            <Typography sx={{
              fontFamily: 'monospace', fontSize: '0.62rem', color: '#484F58', mt: '2px',
            }}>
              Current LIVE state is available via VIEW OPERATIONAL CONTEXT in the Copilot panel,
              or via GRAPH tab with LIVE view.
            </Typography>
          </Box>

          {/* ── Node list ────────────────────────────────────────────────────── */}
          <Box>
            <Typography sx={{
              fontFamily: 'monospace', fontSize: '0.58rem', fontWeight: 700,
              color: '#484F58', textTransform: 'uppercase', letterSpacing: '0.1em',
              mb: '6px',
            }}>
              Entities in Context ({snapshot.entity_count})
            </Typography>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {snapshot.nodes.map((node, i) => (
                <Box
                  key={node.entity_id}
                  sx={{
                    background: i === 0 ? '#0D1420' : '#0D1117',
                    border: i === 0 ? '1px solid #1F6FEB33' : '1px solid #21262D',
                    borderRadius: '3px',
                    p: '7px 10px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                  }}
                >
                  {i === 0 && (
                    <Box component="span" sx={{
                      fontFamily: 'monospace', fontSize: '0.52rem', color: '#58A6FF',
                      border: '1px solid #1F6FEB44', borderRadius: '3px',
                      px: '3px', flexShrink: 0,
                    }}>
                      FOCUS
                    </Box>
                  )}
                  <EntityTypeChip type={node.entity_type} />
                  <Typography sx={{
                    fontFamily: 'monospace', fontSize: '0.68rem', color: '#C9D1D9',
                    flexGrow: 1,
                  }}>
                    {node.label}
                  </Typography>
                  <Typography sx={{
                    fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58',
                    wordBreak: 'break-all',
                  }}>
                    {node.entity_id}
                  </Typography>
                </Box>
              ))}
            </Box>
          </Box>

          {/* ── Relationship summary ──────────────────────────────────────────── */}
          {Object.keys(snapshot.relationship_summary).length > 0 && (
            <Box>
              <Typography sx={{
                fontFamily: 'monospace', fontSize: '0.58rem', fontWeight: 700,
                color: '#484F58', textTransform: 'uppercase', letterSpacing: '0.1em',
                mb: '6px',
              }}>
                Relationships ({snapshot.relationship_count})
              </Typography>
              {Object.entries(snapshot.relationship_summary).map(([group, labels]) => (
                <Box key={group} sx={{ mb: '4px' }}>
                  <Typography sx={{
                    fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58',
                    textTransform: 'uppercase', letterSpacing: '0.06em',
                  }}>
                    {group} ({labels.length})
                  </Typography>
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: '4px', mt: '3px' }}>
                    {labels.slice(0, 10).map(label => (
                      <Box
                        key={label}
                        component="span"
                        sx={{
                          fontFamily: 'monospace', fontSize: '0.6rem', color: '#8B949E',
                          border: '1px solid #21262D', borderRadius: '3px',
                          px: '5px', py: '1px',
                        }}
                      >
                        {label}
                      </Box>
                    ))}
                    {labels.length > 10 && (
                      <Box component="span" sx={{
                        fontFamily: 'monospace', fontSize: '0.6rem', color: '#484F58',
                      }}>
                        +{labels.length - 10} more
                      </Box>
                    )}
                  </Box>
                </Box>
              ))}
            </Box>
          )}

          {/* ── Store note ───────────────────────────────────────────────────── */}
          <Typography sx={{
            fontFamily: 'monospace', fontSize: '0.58rem', color: '#30363D', mt: '4px',
          }}>
            {snapshot.store_note}
          </Typography>
        </>
      )}
    </Box>
  );
}
