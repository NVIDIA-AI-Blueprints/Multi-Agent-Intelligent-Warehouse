import React, { useState } from 'react';
import { Box, Typography, CircularProgress } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { demoAPI, ScenarioMeta } from '../../services/demoAPI';

// The canonical first scenario for the MAIW demo narrative
const RECOMMENDED = 'labor_constraint_wave_risk';

interface Props {
  onStart: (scenarioName: string) => Promise<void>;
}

function TagChip({ label }: { label: string }) {
  return (
    <Box sx={{
      display: 'inline-block',
      px: '6px', py: '1px',
      border: '1px solid #21262D',
      borderRadius: '4px',
      fontFamily: 'monospace',
      fontSize: '0.62rem',
      color: '#484F58',
      textTransform: 'uppercase',
      letterSpacing: '0.04em',
    }}>
      {label}
    </Box>
  );
}

function ScenarioCard({ scenario, onStart }: { scenario: ScenarioMeta; onStart: (name: string) => Promise<void> }) {
  const [starting, setStarting] = useState(false);
  const isRec = scenario.name === RECOMMENDED;

  async function handleStart() {
    setStarting(true);
    try {
      await onStart(scenario.name);
    } finally {
      setStarting(false);
    }
  }

  return (
    <Box sx={{
      background: '#161B22',
      border: isRec ? '1.5px solid #1F6FEB' : '1px solid #21262D',
      borderRadius: '8px',
      p: 2,
      display: 'flex',
      flexDirection: 'column',
      gap: 1,
      position: 'relative',
    }}>
      {isRec && (
        <Box sx={{
          position: 'absolute', top: 10, right: 10,
          background: '#0d2146',
          border: '1px solid #1F6FEB',
          borderRadius: '4px',
          px: '6px', py: '1px',
          fontFamily: 'monospace',
          fontSize: '0.6rem',
          color: '#58A6FF',
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
        }}>
          Recommended
        </Box>
      )}

      <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
        {scenario.tags.map(t => <TagChip key={t} label={t} />)}
      </Box>

      <Typography sx={{
        fontFamily: 'monospace',
        fontSize: '0.82rem',
        fontWeight: 700,
        color: '#C9D1D9',
        letterSpacing: '0.02em',
        pr: isRec ? 8 : 0,
      }}>
        {scenario.display_name}
      </Typography>

      <Typography sx={{
        fontFamily: 'monospace',
        fontSize: '0.72rem',
        color: '#6E7681',
        lineHeight: 1.55,
        flexGrow: 1,
      }}>
        {scenario.description}
      </Typography>

      <Box
        component="button"
        onClick={handleStart}
        disabled={starting}
        sx={{
          mt: 0.5,
          alignSelf: 'flex-start',
          background: isRec ? '#1F6FEB' : 'transparent',
          border: isRec ? '1px solid #1F6FEB' : '1px solid #30363D',
          borderRadius: '4px',
          px: '14px', py: '5px',
          fontFamily: 'monospace',
          fontSize: '0.72rem',
          fontWeight: 700,
          color: isRec ? '#fff' : '#8B949E',
          cursor: starting ? 'default' : 'pointer',
          opacity: starting ? 0.6 : 1,
          display: 'flex',
          alignItems: 'center',
          gap: 0.75,
          '&:hover:not(:disabled)': {
            background: isRec ? '#388bfd' : '#21262D',
            color: isRec ? '#fff' : '#C9D1D9',
          },
        }}
      >
        {starting && <CircularProgress size={10} sx={{ color: 'inherit' }} />}
        {starting ? 'Starting...' : 'Start scenario'}
      </Box>
    </Box>
  );
}

export default function ScenarioSelector({ onStart }: Props) {
  const { data: scenarios, isLoading, error } = useQuery<ScenarioMeta[]>({
    queryKey: ['demo-scenarios'],
    queryFn: demoAPI.listScenarios,
    staleTime: 60_000,
  });

  // Put recommended first
  const ordered = scenarios
    ? [
        ...scenarios.filter(s => s.name === RECOMMENDED),
        ...scenarios.filter(s => s.name !== RECOMMENDED),
      ]
    : [];

  return (
    <Box sx={{ p: 3, maxWidth: 760, mx: 'auto' }}>
      <Box sx={{ mb: 3 }}>
        <Typography sx={{
          fontFamily: 'monospace',
          fontSize: '0.6rem',
          color: '#484F58',
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          mb: 0.75,
        }}>
          Demo scenario
        </Typography>
        <Typography sx={{
          fontFamily: 'monospace',
          fontSize: '1rem',
          fontWeight: 700,
          color: '#C9D1D9',
          mb: 0.5,
        }}>
          Select a scenario to begin
        </Typography>
        <Typography sx={{
          fontFamily: 'monospace',
          fontSize: '0.72rem',
          color: '#6E7681',
        }}>
          No database or MCP servers required. Each scenario runs a complete MAIW pipeline in simulation.
        </Typography>
      </Box>

      {isLoading && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, py: 4 }}>
          <CircularProgress size={14} sx={{ color: '#484F58' }} />
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.72rem', color: '#484F58' }}>
            Loading scenarios...
          </Typography>
        </Box>
      )}

      {error && (
        <Box sx={{
          background: '#1a0f0f',
          border: '1px solid #6e1111',
          borderRadius: '6px',
          p: 2,
        }}>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.72rem', color: '#F85149' }}>
            Could not load scenarios. Is the demo backend running?
          </Typography>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58', mt: 0.5 }}>
            Expected: ./scripts/start_demo_mode.sh
          </Typography>
        </Box>
      )}

      {ordered.length > 0 && (
        <Box sx={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 1.5,
        }}>
          {ordered.map(s => (
            <ScenarioCard key={s.name} scenario={s} onStart={onStart} />
          ))}
        </Box>
      )}

      <Box sx={{
        mt: 3,
        pt: 2,
        borderTop: '1px solid #21262D',
        display: 'flex',
        alignItems: 'center',
        gap: 1,
      }}>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58' }}>
          ✓
        </Typography>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58' }}>
          For fault injection and circuit breaker testing, switch to{' '}
          <Box component="span" sx={{ color: '#6E7681' }}>Reliability demo</Box>{' '}
          mode using the toggle above.
        </Typography>
      </Box>
    </Box>
  );
}
