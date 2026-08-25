import React from 'react';
import { Box, Typography, Divider } from '@mui/material';
import { useRuntimeStatus } from '../hooks/useRuntimeStatus';
import { useQuery } from '@tanstack/react-query';
import { healthAPI } from '../services/api';

const STORAGE_KEY = 'maiw_decision_history';

function readDecisionCounts() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return { pending: 0, executed: 0 };
    const history: any[] = JSON.parse(raw);
    let pending = 0;
    let executed = 0;
    history.forEach((r) => {
      const status = r.result?.decision?.status ?? r.result?.decision_result?.status ?? r.result?.status;
      if (status === 'requires_human_approval') pending++;
      else if (status === 'approved' || r.result?.success === true) executed++;
    });
    return { pending, executed };
  } catch {
    return { pending: 0, executed: 0 };
  }
}

function Seg({ children }: { children: React.ReactNode }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexShrink: 0 }}>
      {children}
      <Divider orientation="vertical" flexItem sx={{ borderColor: '#1C2128', mx: 0.5 }} />
    </Box>
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

  const { pending, executed } = readDecisionCounts();
  const mcpCount = runtime ? [
    runtime.inventory_mcp_configured,
    runtime.equipment_mcp_configured,
    runtime.labor_mcp_configured,
    runtime.wave_mcp_configured,
  ].filter(Boolean).length : 0;

  const stateOk = live?.status === 'alive';
  const modelName = runtime?.model_gateway_available ? 'Super' : '—';

  return (
    <Box
      sx={{
        height: 28,
        minHeight: 28,
        backgroundColor: '#080C10',
        borderTop: '1px solid #1C2128',
        display: 'flex',
        alignItems: 'center',
        px: 2,
        gap: 0,
        flexShrink: 0,
        overflow: 'hidden',
        fontFamily: 'monospace',
        fontSize: '0.67rem',
      }}
    >
      <Seg>
        <Box sx={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: stateOk ? '#3FB950' : '#484F58', boxShadow: stateOk ? '0 0 4px #3FB950' : 'none' }} />
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.67rem', color: stateOk ? '#3FB950' : '#484F58', fontWeight: 700, letterSpacing: '0.04em' }}>
          STATE
        </Typography>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: stateOk ? '#3FB950' : '#484F58' }}>
          {stateOk ? '✓ FRESH' : '✗ STALE'}
        </Typography>
      </Seg>

      <Seg>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58' }}>MODEL</Typography>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.67rem', color: runtime?.model_gateway_available ? '#58A6FF' : '#484F58', fontWeight: 600 }}>
          {modelName}
        </Typography>
      </Seg>

      <Seg>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58' }}>MCP</Typography>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.67rem', color: mcpCount === 4 ? '#3FB950' : mcpCount > 0 ? '#D29922' : '#484F58', fontWeight: 600 }}>
          {mcpCount}/4
        </Typography>
      </Seg>

      <Seg>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58' }}>PENDING</Typography>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.67rem', color: pending > 0 ? '#D29922' : '#484F58', fontWeight: 600 }}>
          {pending}
        </Typography>
      </Seg>

      <Seg>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58' }}>EXECUTIONS</Typography>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.67rem', color: '#8B949E', fontWeight: 600 }}>
          {executed}
        </Typography>
      </Seg>

      {runtime?.uptime_seconds !== undefined && (
        <Seg>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58' }}>UP</Typography>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.67rem', color: '#484F58' }}>
            {Math.floor(runtime.uptime_seconds / 60)}m
          </Typography>
        </Seg>
      )}

      <Box sx={{ flexGrow: 1 }} />
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#21262D' }}>
        STATE → REASON → PROPOSE → DECIDE → EXECUTE
      </Typography>
    </Box>
  );
};

export default StatusBar;
