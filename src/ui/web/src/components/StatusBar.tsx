import React from 'react';
import { Box, Typography, Chip, Tooltip } from '@mui/material';
import {
  Circle as CircleIcon,
  Memory as MemoryIcon,
  Storage as StorageIcon,
  Hub as HubIcon,
} from '@mui/icons-material';
import { useRuntimeStatus } from '../hooks/useRuntimeStatus';
import { useQuery } from '@tanstack/react-query';
import { healthAPI } from '../services/api';

function StatusDot({ ok, label }: { ok: boolean | undefined; label: string }) {
  const color = ok === undefined ? '#484F58' : ok ? '#3FB950' : '#F85149';
  return (
    <Tooltip title={`${label}: ${ok === undefined ? 'unknown' : ok ? 'ok' : 'unavailable'}`} arrow>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, cursor: 'default' }}>
        <CircleIcon sx={{ fontSize: 8, color }} />
        <Typography variant="caption" sx={{ color: '#8B949E', fontSize: '0.7rem', lineHeight: 1 }}>
          {label}
        </Typography>
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
        position: 'fixed',
        bottom: 0,
        right: 0,
        left: { xs: 0, md: 240 },
        height: 28,
        backgroundColor: '#0D1117',
        borderTop: '1px solid #21262D',
        display: 'flex',
        alignItems: 'center',
        px: 2,
        gap: 2,
        zIndex: 1200,
        overflow: 'hidden',
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
        <HubIcon sx={{ fontSize: 11, color: '#58A6FF' }} />
        <Typography variant="caption" sx={{ color: '#58A6FF', fontSize: '0.7rem', fontWeight: 600, letterSpacing: '0.05em' }}>
          MAIW v2
        </Typography>
      </Box>

      <Box sx={{ width: '1px', height: 14, backgroundColor: '#21262D' }} />

      <StatusDot ok={apiOk} label="API" />
      <StatusDot ok={runtime?.runtime_initialized} label="Runtime" />
      <StatusDot ok={runtime?.model_gateway_available} label="ModelGateway" />
      <StatusDot ok={runtime?.decision_engine_available} label="DecisionEngine" />

      <Box sx={{ width: '1px', height: 14, backgroundColor: '#21262D' }} />

      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
        <StorageIcon sx={{ fontSize: 11, color: '#8B949E' }} />
        <Typography variant="caption" sx={{ color: '#8B949E', fontSize: '0.7rem' }}>
          MCP {mcpCount}/4
        </Typography>
      </Box>

      {runtime?.uptime_seconds !== undefined && (
        <>
          <Box sx={{ width: '1px', height: 14, backgroundColor: '#21262D' }} />
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <MemoryIcon sx={{ fontSize: 11, color: '#8B949E' }} />
            <Typography variant="caption" sx={{ color: '#8B949E', fontSize: '0.7rem' }}>
              up {Math.floor(runtime.uptime_seconds / 60)}m
            </Typography>
          </Box>
        </>
      )}

      <Box sx={{ flexGrow: 1 }} />

      <Typography variant="caption" sx={{ color: '#484F58', fontSize: '0.65rem' }}>
        STATE → REASON → PROPOSE → DECIDE → EXECUTE → MCP → BACKEND
      </Typography>
    </Box>
  );
};

export default StatusBar;
