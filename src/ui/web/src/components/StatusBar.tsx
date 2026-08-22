import React from 'react';
import { Box, Typography, Tooltip } from '@mui/material';
import { useRuntimeStatus } from '../hooks/useRuntimeStatus';
import { useQuery } from '@tanstack/react-query';
import { healthAPI } from '../services/api';

function Dot({ ok, label }: { ok: boolean | undefined; label: string }) {
  const color = ok === undefined ? '#30363D' : ok ? '#3FB950' : '#F85149';
  return (
    <Tooltip title={`${label}: ${ok === undefined ? 'unknown' : ok ? 'ok' : 'unavailable'}`} arrow>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, cursor: 'default' }}>
        <Box sx={{ width: 5, height: 5, borderRadius: '50%', backgroundColor: color, boxShadow: ok ? `0 0 3px ${color}` : 'none' }} />
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.63rem', color: '#484F58' }}>{label}</Typography>
      </Box>
    </Tooltip>
  );
}

const StatusBar: React.FC = () => {
  const { data: runtime } = useRuntimeStatus();
  const { data: live } = useQuery({
    queryKey: ['live'],
    queryFn: healthAPI.getLive,
    refetchInterval: 15000,
    retry: 0,
    staleTime: 10000,
  });

  const apiOk = live?.status === 'alive';
  const mcpCount = runtime ? [
    runtime.inventory_mcp_configured,
    runtime.equipment_mcp_configured,
    runtime.labor_mcp_configured,
    runtime.wave_mcp_configured,
  ].filter(Boolean).length : 0;

  return (
    <Box
      sx={{
        height: 24,
        minHeight: 24,
        backgroundColor: '#0D1117',
        borderTop: '1px solid #1C2128',
        display: 'flex',
        alignItems: 'center',
        px: 2,
        gap: 2,
        flexShrink: 0,
        overflow: 'hidden',
      }}
    >
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#76B900', fontWeight: 700, letterSpacing: '0.06em' }}>
        MAIW v2
      </Typography>

      <Box sx={{ width: '1px', height: 10, backgroundColor: '#1C2128' }} />

      <Dot ok={apiOk} label="API" />
      <Dot ok={runtime?.runtime_initialized} label="Runtime" />
      <Dot ok={runtime?.model_gateway_available} label="Gateway" />
      <Dot ok={runtime?.decision_engine_available} label="Engine" />

      <Box sx={{ width: '1px', height: 10, backgroundColor: '#1C2128' }} />

      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#484F58' }}>
        MCP {mcpCount}/4
      </Typography>

      {runtime?.uptime_seconds !== undefined && (
        <>
          <Box sx={{ width: '1px', height: 10, backgroundColor: '#1C2128' }} />
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#484F58' }}>
            up {Math.floor(runtime.uptime_seconds / 60)}m {runtime.uptime_seconds % 60}s
          </Typography>
        </>
      )}

      <Box sx={{ flexGrow: 1 }} />

      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#30363D' }}>
        STATE → REASON → PROPOSE → DECIDE → EXECUTE → MCP → BACKEND
      </Typography>
    </Box>
  );
};

export default StatusBar;
