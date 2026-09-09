import React, { useState } from 'react';
import { Box, Typography, Skeleton } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { worldAPI, WorldConfigResponse, WorldSummaryResponse } from '../../services/worldAPI';

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
  yellow: '#D29922',
  orange: '#E3652B',
  red: '#F85149',
  mono: 'monospace',
};

// ── helpers ────────────────────────────────────────────────────────────────────

function formatElapsed(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function severityColor(sev: string | null): string {
  switch ((sev ?? 'NOMINAL').toUpperCase()) {
    case 'CRITICAL': return C.red;
    case 'HIGH': return C.orange;
    case 'MODERATE': return C.yellow;
    case 'NOMINAL': return C.green;
    default: return C.muted;
  }
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function CardHeading({ label }: { label: string }) {
  return (
    <Typography
      sx={{
        fontFamily: C.mono,
        fontSize: '0.6rem',
        fontWeight: 700,
        color: C.accent,
        textTransform: 'uppercase',
        letterSpacing: '0.1em',
        mb: 1.5,
      }}
    >
      {label}
    </Typography>
  );
}

function Row({ label, value, mono = true }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', mb: 0.5 }}>
      <Typography sx={{ fontFamily: C.mono, fontSize: '0.65rem', color: C.muted }}>{label}</Typography>
      <Typography
        sx={{
          fontFamily: mono ? C.mono : 'inherit',
          fontSize: '0.65rem',
          color: C.text,
          fontWeight: 600,
          textAlign: 'right',
          ml: 1,
        }}
      >
        {value}
      </Typography>
    </Box>
  );
}

function Badge({ children, color = C.muted, bg = C.card }: { children: React.ReactNode; color?: string; bg?: string }) {
  return (
    <Box
      component="span"
      sx={{
        fontFamily: C.mono,
        fontSize: '0.58rem',
        fontWeight: 700,
        color,
        background: bg,
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

function Card({ children, gridArea }: { children: React.ReactNode; gridArea?: string }) {
  return (
    <Box
      sx={{
        background: C.card,
        border: `1px solid ${C.border}`,
        borderRadius: '6px',
        p: 2,
        gridArea,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {children}
    </Box>
  );
}

// ── Loading skeleton ───────────────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <Card>
      <Skeleton variant="text" width="40%" sx={{ bgcolor: '#21262D', mb: 1 }} />
      {[1, 2, 3, 4].map((i) => (
        <Skeleton key={i} variant="text" width="90%" sx={{ bgcolor: '#21262D', mb: 0.5 }} />
      ))}
    </Card>
  );
}

// ── Error state ────────────────────────────────────────────────────────────────

function ErrorCard({ onRetry }: { onRetry: () => void }) {
  return (
    <Box
      data-testid="world-overview-error"
      sx={{
        gridColumn: '1 / -1',
        background: '#1A0A0A',
        border: `1px solid #F8514944`,
        borderRadius: '6px',
        p: 2.5,
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
        World API unavailable
      </Typography>
      <Typography sx={{ fontFamily: C.mono, fontSize: '0.68rem', color: C.muted, lineHeight: 1.5 }}>
        Cannot reach /api/v1/world. Confirm the backend world service is running.
      </Typography>
      <Box
        component="button"
        onClick={onRetry}
        data-testid="world-error-retry"
        sx={{
          alignSelf: 'flex-start',
          background: 'transparent',
          border: `1px solid ${C.border}`,
          borderRadius: '4px',
          px: '12px',
          py: '6px',
          fontFamily: C.mono,
          fontSize: '0.65rem',
          color: C.muted,
          cursor: 'pointer',
          '&:hover': { color: C.text, borderColor: '#484F58' },
        }}
      >
        Retry
      </Box>
    </Box>
  );
}

// ── Journey strip ──────────────────────────────────────────────────────────────

const JOURNEY_STEPS = [
  { n: '01', label: 'CONFIGURE' },
  { n: '02', label: 'GENERATE' },
  { n: '03', label: 'VALIDATE' },
  { n: '04', label: 'EXPLORE' },
  { n: '05', label: 'DISRUPT' },
  { n: '06', label: 'OPERATE' },
  { n: '07', label: 'OBSERVE' },
];
// Steps 01-03 always complete; step 05 (index 4 = DISRUPT) highlighted when scenarioActive

function JourneyStrip({ scenarioActive }: { scenarioActive: boolean }) {
  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 0,
        flexWrap: 'nowrap',
        overflowX: 'auto',
        py: 1,
        px: 2,
        background: C.card,
        border: `1px solid ${C.border}`,
        borderRadius: '6px',
        mb: 2,
      }}
    >
      {JOURNEY_STEPS.map((step, i) => {
        // Steps 01-03 (indices 0-2) always highlighted; step 05 (index 4) highlighted when scenario active
        const done = i < 3 || (i === 4 && scenarioActive);
        return (
          <React.Fragment key={step.n}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, flexShrink: 0 }}>
              <Typography
                sx={{
                  fontFamily: C.mono,
                  fontSize: '0.58rem',
                  color: done ? C.dim : '#21262D',
                  letterSpacing: '0.04em',
                }}
              >
                {step.n}
              </Typography>
              <Typography
                sx={{
                  fontFamily: C.mono,
                  fontSize: '0.62rem',
                  fontWeight: done ? 700 : 400,
                  color: done ? C.accent : '#30363D',
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                }}
              >
                {step.label}
              </Typography>
            </Box>
            {i < JOURNEY_STEPS.length - 1 && (
              <Typography
                sx={{
                  fontFamily: C.mono,
                  fontSize: '0.6rem',
                  color: (i < 2) ? C.dim : '#21262D',
                  mx: 0.75,
                  flexShrink: 0,
                }}
              >
                →
              </Typography>
            )}
          </React.Fragment>
        );
      })}
    </Box>
  );
}

// ── Checksum cell ──────────────────────────────────────────────────────────────

function ChecksumCell({ checksum }: { checksum: string | null }) {
  const [expanded, setExpanded] = useState(false);
  if (!checksum) return <Typography sx={{ fontFamily: C.mono, fontSize: '0.65rem', color: C.muted }}>&mdash;</Typography>;
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

// ── Card 1: CONFIGURATION ─────────────────────────────────────────────────────

function ConfigurationCard({ config }: { config: WorldConfigResponse }) {
  const { warehouse, layout, workforce, equipment, commerce } = config;
  return (
    <Card>
      <CardHeading label="Configuration" />
      <Row label="Warehouse" value={warehouse.warehouse_id} />
      <Row label="Zones" value={layout.zone_count} />
      <Row label="Locations" value={layout.location_count.toLocaleString()} />
      <Row label="Dock Doors" value={layout.dock_door_count} />
      <Row
        label="Workers"
        value={`${workforce.total_workers} (${workforce.workers_per_shift}/shift × ${workforce.shift_count} shifts)`}
      />
      <Row
        label="Equipment"
        value={`${equipment.total} (${equipment.agv_count} AGVs, ${equipment.forklift_count} forklifts, ${equipment.conveyor_count} conveyors)`}
      />
      <Row label="SKUs" value={commerce.sku_count.toLocaleString()} />
      <Row label="Daily Orders" value={commerce.daily_order_count.toLocaleString()} />
      <Row label="Seed" value={warehouse.seed} />
    </Card>
  );
}

// ── Card 2: DATAPACK ───────────────────────────────────────────────────────────

function DataPackCard({ summary }: { summary: WorldSummaryResponse }) {
  const { datapack } = summary;
  const statusColor = datapack.loaded ? C.green : C.red;
  const statusLabel = datapack.loaded ? 'VALID' : 'NOT LOADED';
  return (
    <Card>
      <CardHeading label="DataPack" />
      <Row label="Dataset" value={datapack.dataset_id} />
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
        <Typography sx={{ fontFamily: C.mono, fontSize: '0.65rem', color: C.muted }}>Status</Typography>
        <Badge color={statusColor}>{statusLabel}</Badge>
      </Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', mb: 0.5 }}>
        <Typography sx={{ fontFamily: C.mono, fontSize: '0.65rem', color: C.muted }}>Checksum</Typography>
        <ChecksumCell checksum={datapack.semantic_checksum} />
      </Box>
      <Row label="Entities" value={datapack.total_entities.toLocaleString()} />
      <Row label="Relationships" value={datapack.total_edges.toLocaleString()} />
      <Row label="Events" value={datapack.total_events.toLocaleString()} />
      <Row label="Format" value={datapack.pack_format} />
      {datapack.immutable && (
        <Box sx={{ mt: 1 }}>
          <Badge color={C.accent}>IMMUTABLE</Badge>
        </Box>
      )}
    </Card>
  );
}

// ── Card 3: OPERATIONAL GRAPH ─────────────────────────────────────────────────

const CHART_ACCENT = '#58A6FF';

function GraphCard({ summary }: { summary: WorldSummaryResponse }) {
  const { graph } = summary;
  const entityTypeCount = Object.keys(graph.entity_counts).length;
  const relTypeCount = Object.keys(graph.relationship_counts).length;

  const chartData = Object.entries(graph.entity_counts)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 8)
    .map(([name, count]) => ({ name, count }));

  return (
    <Card>
      <CardHeading label="Operational Graph" />
      <Row label="Entity Types" value={entityTypeCount} />
      <Row label="Relationship Types" value={relTypeCount} />
      <Row label="Total Entities" value={graph.total_entities.toLocaleString()} />
      <Row label="Total Relationships" value={graph.total_relationships.toLocaleString()} />

      {chartData.length > 0 && (
        <Box sx={{ mt: 1.5, mb: 1 }}>
          <Typography
            sx={{ fontFamily: C.mono, fontSize: '0.58rem', color: C.dim, mb: 0.75, textTransform: 'uppercase', letterSpacing: '0.06em' }}
          >
            Entity Distribution
          </Typography>
          <ResponsiveContainer width="100%" height={120}>
            <BarChart
              data={chartData}
              layout="vertical"
              margin={{ top: 0, right: 8, left: 0, bottom: 0 }}
            >
              <XAxis type="number" hide />
              <YAxis
                type="category"
                dataKey="name"
                width={90}
                tick={{ fontFamily: 'monospace', fontSize: 9, fill: C.muted }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                contentStyle={{
                  background: C.card,
                  border: `1px solid ${C.border}`,
                  fontFamily: 'monospace',
                  fontSize: 11,
                  color: C.text,
                }}
                cursor={{ fill: '#21262D44' }}
              />
              <Bar dataKey="count" radius={[0, 2, 2, 0]}>
                {chartData.map((_, i) => (
                  <Cell key={i} fill={i === 0 ? CHART_ACCENT : '#30363D'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Box>
      )}

      <Box
        sx={{
          mt: 1,
          pt: 1,
          borderTop: `1px solid ${C.border}`,
          display: 'flex',
          flexDirection: 'column',
          gap: 0.25,
        }}
      >
        <Typography sx={{ fontFamily: C.mono, fontSize: '0.65rem', color: C.dim, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          Graph Explorer
        </Typography>
        <Typography sx={{ fontFamily: C.mono, fontSize: '0.58rem', color: '#30363D', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          Coming in Phase 17C
        </Typography>
      </Box>
    </Card>
  );
}

// ── Card 4: RUNTIME ────────────────────────────────────────────────────────────

function RuntimeCard({ summary }: { summary: WorldSummaryResponse }) {
  const { scenario, runtime } = summary;
  const sevColor = severityColor(scenario.severity);
  return (
    <Card>
      <CardHeading label="Runtime" />
      <Row label="Scenario" value={scenario.name ?? 'None'} />
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
        <Typography sx={{ fontFamily: C.mono, fontSize: '0.65rem', color: C.muted }}>Severity</Typography>
        <Badge color={sevColor}>{scenario.severity ?? 'NOMINAL'}</Badge>
      </Box>
      <Row label="Status" value={runtime.status} />
      <Row
        label="Elapsed"
        value={runtime.elapsed_seconds != null ? formatElapsed(runtime.elapsed_seconds) : '—'}
      />
      <Typography
        sx={{
          fontFamily: C.mono,
          fontSize: '0.6rem',
          color: C.dim,
          fontStyle: 'italic',
          mt: 1.5,
          lineHeight: 1.5,
        }}
      >
        Runtime World is mutable — DataPack never changes
      </Typography>
    </Card>
  );
}

// ── WorldOverview ──────────────────────────────────────────────────────────────

export default function WorldOverview() {
  const {
    data: config,
    isLoading: configLoading,
    error: configError,
    refetch: refetchConfig,
  } = useQuery({
    queryKey: ['world', 'config'],
    queryFn: () => worldAPI.getConfig(),
    staleTime: 60_000,
  });

  const {
    data: summary,
    isLoading: summaryLoading,
    error: summaryError,
    refetch: refetchSummary,
  } = useQuery({
    queryKey: ['world', 'summary'],
    queryFn: () => worldAPI.getSummary(),
    refetchInterval: 5_000,
  });

  const isLoading = configLoading || summaryLoading;
  const hasError = !!configError && !!summaryError;

  const handleRetry = () => {
    void refetchConfig();
    void refetchSummary();
  };

  // Header values (fall back gracefully when only one query has resolved)
  const warehouseId = config?.warehouse.warehouse_id ?? summary?.datapack.warehouse_id ?? '—';
  const datasetId = config?.warehouse.dataset_id ?? summary?.datapack.dataset_id ?? '—';
  const seed = config?.warehouse.seed ?? summary?.datapack.seed ?? null;
  const isLoaded = summary?.datapack.loaded ?? false;
  const scenarioActive = summary?.scenario.active ?? false;

  return (
    <Box
      data-testid="world-overview"
      sx={{
        background: C.bg,
        minHeight: '100%',
        p: 2,
        display: 'flex',
        flexDirection: 'column',
        gap: 0,
      }}
    >
      {/* Header */}
      <Box sx={{ mb: 2 }}>
        <Typography
          sx={{
            fontFamily: C.mono,
            fontSize: '0.8rem',
            fontWeight: 700,
            color: C.text,
            textTransform: 'uppercase',
            letterSpacing: '0.1em',
            mb: 0.5,
          }}
        >
          Warehouse World
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 0.5 }}>
          <Typography sx={{ fontFamily: C.mono, fontSize: '0.72rem', fontWeight: 700, color: C.text }}>
            {warehouseId}
          </Typography>
          <Badge color={isLoaded ? C.green : C.red}>{isLoaded ? 'VALID' : 'INVALID'}</Badge>
          <Badge color={C.accent}>IMMUTABLE DATAPACK</Badge>
          {scenarioActive && <Badge color={C.yellow}>SCENARIO ACTIVE</Badge>}
          {!scenarioActive && <Badge color={C.dim}>READY</Badge>}
        </Box>
        <Typography sx={{ fontFamily: C.mono, fontSize: '0.62rem', color: C.muted }}>
          Canonical operational environment&nbsp;&nbsp;·&nbsp;&nbsp;{datasetId}
          {seed != null && <>&nbsp;&nbsp;·&nbsp;&nbsp;Seed {seed}</>}
        </Typography>
      </Box>

      {/* Journey strip */}
      <JourneyStrip scenarioActive={scenarioActive} />

      {/* Error state */}
      {hasError && !isLoading && (
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: 2,
          }}
        >
          <ErrorCard onRetry={handleRetry} />
        </Box>
      )}

      {/* Loading / content */}
      {!hasError && (
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: 2,
          }}
        >
          {isLoading || !config ? <SkeletonCard /> : <ConfigurationCard config={config} />}
          {isLoading || !summary ? <SkeletonCard /> : <DataPackCard summary={summary} />}
          {isLoading || !summary ? <SkeletonCard /> : <GraphCard summary={summary} />}
          {isLoading || !summary ? <SkeletonCard /> : <RuntimeCard summary={summary} />}
        </Box>
      )}
    </Box>
  );
}
