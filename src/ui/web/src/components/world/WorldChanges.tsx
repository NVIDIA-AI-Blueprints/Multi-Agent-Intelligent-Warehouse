import React, { useState } from 'react';
import { Box, Typography, Skeleton } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { worldAPI, WorldChangesResponse, AffectedEntityDTO, OverlayEventDTO } from '../../services/worldAPI';
import { WorldView } from './WorldShell';

// ── Colour tokens ──────────────────────────────────────────────────────────────

const C = {
  bg: '#0D1117',
  card: '#161B22',
  border: '#21262D',
  text: '#C9D1D9',
  muted: '#8B949E',
  dim: '#484F58',
  accent: '#58A6FF',
  green: '#3FB950',
  yellow: '#E3B341',
  orange: '#D29922',
  red: '#F85149',
  mono: 'monospace' as const,
};

// ── Helpers ────────────────────────────────────────────────────────────────────

function severityColor(sev: string | null): string {
  switch ((sev ?? 'NOMINAL').toUpperCase()) {
    case 'CRITICAL': return C.red;
    case 'HIGH': return C.orange;
    case 'MODERATE': return C.yellow;
    default: return C.green;
  }
}

function formatOffset(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `+${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

function formatClock(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) {
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function SectionHeading({ label }: { label: string }) {
  return (
    <Typography
      sx={{
        fontFamily: C.mono,
        fontSize: '0.6rem',
        fontWeight: 700,
        color: C.accent,
        textTransform: 'uppercase',
        letterSpacing: '0.1em',
        mb: 1,
      }}
    >
      {label}
    </Typography>
  );
}

function Badge({
  children,
  color = C.muted,
}: {
  children: React.ReactNode;
  color?: string;
}) {
  return (
    <Box
      component="span"
      sx={{
        fontFamily: C.mono,
        fontSize: '0.58rem',
        fontWeight: 700,
        color,
        border: `1px solid ${color}44`,
        borderRadius: '3px',
        px: '5px',
        py: '1px',
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        display: 'inline-block',
      }}
    >
      {children}
    </Box>
  );
}

function ChecksumCell({ checksum }: { checksum: string | null }) {
  const [expanded, setExpanded] = useState(false);
  if (!checksum) {
    return (
      <Typography sx={{ fontFamily: C.mono, fontSize: '0.65rem', color: C.muted }}>
        &mdash;
      </Typography>
    );
  }
  const short = checksum.slice(0, 8);
  return (
    <Box
      component="span"
      sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5, cursor: 'pointer' }}
      onClick={() => setExpanded((e) => !e)}
      title={expanded ? 'Click to collapse' : 'Click to expand checksum'}
    >
      <Typography sx={{ fontFamily: C.mono, fontSize: '0.65rem', color: C.text }}>
        {expanded ? checksum : `${short}...`}
      </Typography>
      <Typography sx={{ fontFamily: C.mono, fontSize: '0.55rem', color: C.accent }}>
        {expanded ? '[collapse]' : '[expand]'}
      </Typography>
    </Box>
  );
}

// ── Loading skeleton ───────────────────────────────────────────────────────────

function ChangesLoadingSkeleton() {
  return (
    <Box sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 1 }}>
      <Skeleton variant="text" width="30%" sx={{ bgcolor: '#21262D' }} />
      <Skeleton variant="rectangular" height={60} sx={{ bgcolor: '#21262D', borderRadius: '4px' }} />
      <Skeleton variant="rectangular" height={80} sx={{ bgcolor: '#21262D', borderRadius: '4px' }} />
    </Box>
  );
}

// ── Error state ────────────────────────────────────────────────────────────────

function ChangesErrorState() {
  return (
    <Box
      data-testid="world-changes-error"
      sx={{
        m: 2,
        p: 2.5,
        background: '#1A0A0A',
        border: `1px solid #F8514944`,
        borderRadius: '6px',
        display: 'flex',
        flexDirection: 'column',
        gap: 1,
        maxWidth: 480,
      }}
    >
      <Typography
        sx={{
          fontFamily: C.mono,
          fontSize: '0.72rem',
          fontWeight: 700,
          color: C.red,
          textTransform: 'uppercase',
          letterSpacing: '0.04em',
        }}
      >
        Changes API unavailable
      </Typography>
      <Typography sx={{ fontFamily: C.mono, fontSize: '0.68rem', color: C.muted, lineHeight: 1.5 }}>
        Cannot reach /api/v1/world/changes. Confirm the backend world service is running.
      </Typography>
    </Box>
  );
}

// ── BASE view ──────────────────────────────────────────────────────────────────

function BaseView({ changes }: { changes: WorldChangesResponse | undefined }) {
  const statusLabel = changes ? (changes.base_checksum ? 'VALID' : 'NOT LOADED') : 'LOADING';
  const statusColor = changes?.base_checksum ? C.green : C.red;

  return (
    <Box sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 2, maxWidth: 560 }}>
      <Typography
        sx={{
          fontFamily: C.mono,
          fontSize: '0.8rem',
          fontWeight: 700,
          color: C.text,
          textTransform: 'uppercase',
          letterSpacing: '0.1em',
        }}
      >
        Canonical Base World
      </Typography>

      <Box
        sx={{
          background: C.card,
          border: `1px solid ${C.border}`,
          borderRadius: '6px',
          p: 2,
          display: 'flex',
          flexDirection: 'column',
          gap: 1,
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
          <Badge color={C.accent}>IMMUTABLE DATAPACK</Badge>
        </Box>
        <Typography sx={{ fontFamily: C.mono, fontSize: '0.68rem', color: C.muted, lineHeight: 1.6 }}>
          No scenario overlay applied.{'\n'}The canonical DataPack is the ground truth for all warehouse state.
        </Typography>

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75, mt: 1 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <Typography sx={{ fontFamily: C.mono, fontSize: '0.65rem', color: C.muted }}>
              Checksum
            </Typography>
            <ChecksumCell checksum={changes?.base_checksum ?? null} />
          </Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <Typography sx={{ fontFamily: C.mono, fontSize: '0.65rem', color: C.muted }}>
              Dataset
            </Typography>
            <Typography sx={{ fontFamily: C.mono, fontSize: '0.65rem', color: C.text, fontWeight: 600 }}>
              {changes?.dataset_id ?? '—'}
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography sx={{ fontFamily: C.mono, fontSize: '0.65rem', color: C.muted }}>
              Status
            </Typography>
            <Badge color={statusColor}>{statusLabel}</Badge>
          </Box>
        </Box>

        <Typography
          sx={{
            fontFamily: C.mono,
            fontSize: '0.62rem',
            color: C.dim,
            mt: 1.5,
            lineHeight: 1.6,
            fontStyle: 'italic',
          }}
        >
          To inspect scenario changes, select SCENARIO from the world view switcher.
        </Typography>
      </Box>
    </Box>
  );
}

// ── No-scenario empty state ────────────────────────────────────────────────────

function NoScenarioState({ changes }: { changes: WorldChangesResponse | undefined }) {
  return (
    <Box
      data-testid="no-scenario-state"
      sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 2, maxWidth: 560 }}
    >
      <Typography
        sx={{
          fontFamily: C.mono,
          fontSize: '0.8rem',
          fontWeight: 700,
          color: C.text,
          textTransform: 'uppercase',
          letterSpacing: '0.1em',
        }}
      >
        No Active Scenario
      </Typography>
      <Box
        sx={{
          background: C.card,
          border: `1px solid ${C.border}`,
          borderRadius: '6px',
          p: 2,
          display: 'flex',
          flexDirection: 'column',
          gap: 1,
        }}
      >
        <Typography sx={{ fontFamily: C.mono, fontSize: '0.68rem', color: C.muted, lineHeight: 1.6 }}>
          BASE warehouse world is loaded.{'\n'}Start a scenario from Operations to inspect its overlay here.
        </Typography>
        {changes?.base_checksum && (
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', mt: 1 }}>
            <Typography sx={{ fontFamily: C.mono, fontSize: '0.65rem', color: C.muted }}>
              Base Checksum
            </Typography>
            <ChecksumCell checksum={changes.base_checksum} />
          </Box>
        )}
      </Box>
    </Box>
  );
}

// ── Affected entity card ───────────────────────────────────────────────────────

function AffectedEntityCard({ entity }: { entity: AffectedEntityDTO }) {
  const sevColor = severityColor(entity.severity);
  return (
    <Box
      data-testid="affected-entity-card"
      sx={{
        background: C.card,
        border: `1px solid ${C.border}`,
        borderRadius: '6px',
        p: 1.5,
        display: 'flex',
        flexDirection: 'column',
        gap: 0.75,
      }}
    >
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography
          sx={{
            fontFamily: C.mono,
            fontSize: '0.68rem',
            fontWeight: 700,
            color: C.text,
          }}
        >
          {entity.entity_label}
        </Typography>
        <Badge color={sevColor}>{entity.severity ?? 'NOMINAL'}</Badge>
      </Box>
      <Typography
        sx={{
          fontFamily: C.mono,
          fontSize: '0.6rem',
          color: C.muted,
          textTransform: 'uppercase',
          letterSpacing: '0.04em',
        }}
      >
        {entity.entity_type}
      </Typography>
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          pt: 0.5,
          borderTop: `1px solid ${C.border}`,
        }}
      >
        <Box sx={{ flex: 1 }}>
          <Typography sx={{ fontFamily: C.mono, fontSize: '0.55rem', color: C.dim, textTransform: 'uppercase', mb: 0.25 }}>
            Base
          </Typography>
          <Typography sx={{ fontFamily: C.mono, fontSize: '0.65rem', color: C.muted }}>
            {entity.before_state ?? '—'}
          </Typography>
        </Box>
        <Typography sx={{ fontFamily: C.mono, fontSize: '0.65rem', color: C.dim }}>
          &rarr;
        </Typography>
        <Box sx={{ flex: 1, textAlign: 'right' }}>
          <Typography sx={{ fontFamily: C.mono, fontSize: '0.55rem', color: C.dim, textTransform: 'uppercase', mb: 0.25 }}>
            Scenario
          </Typography>
          <Typography sx={{ fontFamily: C.mono, fontSize: '0.65rem', color: C.text, fontWeight: 600 }}>
            {entity.after_state ?? '—'}
          </Typography>
        </Box>
      </Box>
    </Box>
  );
}

// ── Scenario event row ─────────────────────────────────────────────────────────

function ScenarioEventRow({ event }: { event: OverlayEventDTO }) {
  return (
    <Box
      data-testid="scenario-event-item"
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 1.5,
        py: '5px',
        borderBottom: `1px solid ${C.border}`,
        '&:last-child': { borderBottom: 'none' },
      }}
    >
      <Typography
        sx={{
          fontFamily: C.mono,
          fontSize: '0.62rem',
          color: C.dim,
          flexShrink: 0,
          minWidth: 48,
        }}
      >
        {formatOffset(event.sim_time_offset_seconds)}
      </Typography>
      <Typography
        sx={{
          fontFamily: C.mono,
          fontSize: '0.62rem',
          color: C.accent,
          flexShrink: 0,
          minWidth: 160,
        }}
      >
        {event.event_type}
      </Typography>
      <Typography
        sx={{
          fontFamily: C.mono,
          fontSize: '0.62rem',
          color: C.muted,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {event.entity_label}
      </Typography>
    </Box>
  );
}

// ── Active scenario view ───────────────────────────────────────────────────────

function ActiveScenarioView({ changes }: { changes: WorldChangesResponse }) {
  const sevColor = severityColor(changes.scenario_severity);
  const sortedEvents = [...changes.events].sort(
    (a, b) => a.sim_time_offset_seconds - b.sim_time_offset_seconds,
  );

  return (
    <Box sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
      {/* Header */}
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
        <Typography
          sx={{
            fontFamily: C.mono,
            fontSize: '0.8rem',
            fontWeight: 700,
            color: C.text,
            textTransform: 'uppercase',
            letterSpacing: '0.1em',
          }}
        >
          Scenario: {changes.scenario_name}
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <Typography sx={{ fontFamily: C.mono, fontSize: '0.62rem', color: C.muted }}>Severity</Typography>
            <Badge color={sevColor}>{changes.scenario_severity}</Badge>
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <Typography sx={{ fontFamily: C.mono, fontSize: '0.62rem', color: C.muted }}>Clock</Typography>
            <Typography sx={{ fontFamily: C.mono, fontSize: '0.62rem', color: C.text, fontWeight: 600 }}>
              +{formatClock(changes.world_clock_seconds)}
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <Typography sx={{ fontFamily: C.mono, fontSize: '0.62rem', color: C.muted }}>Base Checksum</Typography>
            <ChecksumCell checksum={changes.base_checksum} />
            <Badge color={C.accent}>IMMUTABLE</Badge>
          </Box>
        </Box>
        <Typography sx={{ fontFamily: C.mono, fontSize: '0.62rem', color: C.muted, mt: 0.5 }}>
          {changes.overlay_event_count} events&nbsp;&nbsp;&middot;&nbsp;&nbsp;
          {changes.affected_entity_count} entities affected
        </Typography>
      </Box>

      {/* Affected entities */}
      {changes.affected_entities.length > 0 && (
        <Box>
          <SectionHeading label="Changed / Affected Entities" />
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
              gap: 1.5,
            }}
          >
            {changes.affected_entities.map((entity) => (
              <AffectedEntityCard key={entity.entity_id} entity={entity} />
            ))}
          </Box>
        </Box>
      )}

      {/* Scenario events */}
      {sortedEvents.length > 0 && (
        <Box>
          <SectionHeading label="Scenario Events" />
          <Box
            sx={{
              background: C.card,
              border: `1px solid ${C.border}`,
              borderRadius: '6px',
              px: 1.5,
              py: 0.5,
            }}
          >
            {sortedEvents.map((event) => (
              <ScenarioEventRow key={event.event_id} event={event} />
            ))}
          </Box>
        </Box>
      )}
    </Box>
  );
}

// ── WorldChanges ───────────────────────────────────────────────────────────────

export default function WorldChanges({ worldView }: { worldView: WorldView }) {
  const { data: changes, isLoading, error } = useQuery({
    queryKey: ['world', 'changes'],
    queryFn: () => worldAPI.getChanges(),
    refetchInterval: 5_000,
  });

  if (error) {
    return <ChangesErrorState />;
  }

  if (isLoading && !changes) {
    return <ChangesLoadingSkeleton />;
  }

  if (worldView === 'base') {
    return <BaseView changes={changes} />;
  }

  // scenario view
  if (!changes || !changes.scenario_active) {
    return <NoScenarioState changes={changes} />;
  }

  return <ActiveScenarioView changes={changes} />;
}
