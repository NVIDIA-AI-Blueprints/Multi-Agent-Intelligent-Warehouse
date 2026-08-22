import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Box, Typography } from '@mui/material';
import { format } from 'date-fns';
import { useRuntimeStatus } from '../hooks/useRuntimeStatus';
import { useQuery } from '@tanstack/react-query';
import { healthAPI, mcpAPI } from '../services/api';

type Category = 'STATE' | 'AGENT' | 'MODEL' | 'SKILL' | 'PROPOSE' | 'DECIDE' | 'EXECUTE' | 'MCP' | 'API';

interface LogEntry {
  id: string;
  ts: string;
  category: Category;
  message: string;
  detail?: string;
}

const STORAGE_KEY = 'maiw_activity_feed';
const MAX_ENTRIES = 200;

const CAT_COLOR: Record<Category, string> = {
  STATE: '#58A6FF',
  AGENT: '#76B900',
  MODEL: '#58A6FF',
  SKILL: '#76B900',
  PROPOSE: '#D29922',
  DECIDE: '#D29922',
  EXECUTE: '#3FB950',
  MCP: '#8B949E',
  API: '#484F58',
};

function makeEntry(category: Category, message: string, detail?: string): LogEntry {
  return { id: `${Date.now()}-${Math.random()}`, ts: new Date().toISOString(), category, message, detail };
}

function usePersistentLog() {
  const [entries, setEntries] = useState<LogEntry[]>(() => {
    try {
      const stored = sessionStorage.getItem(STORAGE_KEY);
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  });

  const add = useCallback((entry: LogEntry) => {
    setEntries((prev) => {
      const next = [entry, ...prev].slice(0, MAX_ENTRIES);
      try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next)); } catch {}
      return next;
    });
  }, []);

  const clear = useCallback(() => {
    setEntries([]);
    sessionStorage.removeItem(STORAGE_KEY);
  }, []);

  return { entries, add, clear };
}

type FilterCat = 'ALL' | Category;
const FILTERS: FilterCat[] = ['ALL', 'STATE', 'AGENT', 'MODEL', 'PROPOSE', 'DECIDE', 'EXECUTE', 'MCP', 'API'];

const ActivityFeed: React.FC = () => {
  const { entries, add, clear } = usePersistentLog();
  const [filter, setFilter] = useState<FilterCat>('ALL');
  const [live, setLive] = useState(true);
  const feedRef = useRef<HTMLDivElement>(null);
  const prevRuntimeRef = useRef<any>(null);
  const liveRef = useRef<any>(null);
  const mcpRef = useRef<any>(null);

  const { data: runtime } = useRuntimeStatus();
  const { data: liveData } = useQuery({
    queryKey: ['live'],
    queryFn: healthAPI.getLive,
    refetchInterval: live ? 15000 : false,
    retry: 0,
    staleTime: 10000,
  });
  const { data: mcpStatus } = useQuery({
    queryKey: ['mcp-status'],
    queryFn: mcpAPI.getStatus,
    refetchInterval: live ? 30000 : false,
    retry: 0,
    staleTime: 15000,
  });

  useEffect(() => {
    if (liveData && liveData?.status !== liveRef.current?.status) {
      const ok = liveData.status === 'alive';
      add(makeEntry('API', `liveness probe → ${ok ? 'alive' : liveData.status}`, ok ? undefined : 'OFFLINE'));
      liveRef.current = liveData;
    }
  }, [liveData, add]);

  useEffect(() => {
    if (!runtime) return;
    const prev = prevRuntimeRef.current;
    if (!prev) {
      const mcpUp = [runtime.inventory_mcp_configured, runtime.equipment_mcp_configured, runtime.labor_mcp_configured, runtime.wave_mcp_configured].filter(Boolean).length;
      add(makeEntry('STATE', `runtime snapshot assembled`, `MCP ${mcpUp}/4 · model:${runtime.model_gateway_available ? 'up' : 'down'}`));
    } else {
      if (prev.model_gateway_available !== runtime.model_gateway_available) {
        add(makeEntry('MODEL', `gateway ${runtime.model_gateway_available ? 'available' : 'unavailable'}`));
      }
      if (prev.decision_engine_available !== runtime.decision_engine_available) {
        add(makeEntry('STATE', `decision engine → ${runtime.decision_engine_available ? 'UP' : 'DOWN'}`));
      }
    }
    prevRuntimeRef.current = runtime;
  }, [runtime, add]);

  useEffect(() => {
    if (!mcpStatus) return;
    if (JSON.stringify(mcpStatus) !== JSON.stringify(mcpRef.current)) {
      const domains = mcpStatus.domains ?? {};
      const up = Object.entries(domains).filter(([, v]: [string, any]) => v.available).map(([k]) => k);
      const down = Object.entries(domains).filter(([, v]: [string, any]) => !v.available).map(([k]) => k);
      const detail = up.length > 0 ? `up: ${up.join(' ')}` : undefined;
      add(makeEntry('MCP', `domain poll · ${up.length}/${Object.keys(domains).length} available`, down.length > 0 ? `down: ${down.join(' ')}` : detail));
      mcpRef.current = mcpStatus;
    }
  }, [mcpStatus, add]);

  useEffect(() => {
    if (feedRef.current) feedRef.current.scrollTop = 0;
  }, [entries]);

  const filtered = filter === 'ALL' ? entries : entries.filter((e) => e.category === filter);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', p: 1.5, gap: 1.5 }}>

      {/* Controls bar */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexShrink: 0 }}>
        {/* Live toggle */}
        <Box
          onClick={() => setLive(!live)}
          sx={{ display: 'flex', alignItems: 'center', gap: 0.75, cursor: 'pointer' }}
        >
          <Box sx={{
            width: 7, height: 7, borderRadius: '50%',
            backgroundColor: live ? '#F85149' : '#30363D',
            animation: live ? 'pulse 1.5s ease infinite' : 'none',
            '@keyframes pulse': { '0%,100%': { opacity: 1 }, '50%': { opacity: 0.3 } },
          }} />
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', fontWeight: 700, color: live ? '#F85149' : '#30363D', letterSpacing: '0.08em' }}>
            {live ? 'LIVE' : 'PAUSED'}
          </Typography>
        </Box>

        <Box sx={{ width: 1, height: 14, backgroundColor: '#1C2128', flexShrink: 0 }} />

        {/* Category filters */}
        {FILTERS.map(f => (
          <Box
            key={f}
            onClick={() => setFilter(f)}
            sx={{
              fontFamily: 'monospace', fontSize: '0.65rem', fontWeight: 700,
              letterSpacing: '0.08em', cursor: 'pointer',
              color: filter === f ? (f === 'ALL' ? '#C9D1D9' : CAT_COLOR[f as Category] ?? '#C9D1D9') : '#30363D',
              '&:hover': { color: f === 'ALL' ? '#8B949E' : CAT_COLOR[f as Category] ?? '#8B949E' },
              pb: 0.25,
              borderBottom: filter === f ? `1px solid ${f === 'ALL' ? '#C9D1D9' : CAT_COLOR[f as Category] ?? '#C9D1D9'}` : '1px solid transparent',
            }}
          >
            {f}
          </Box>
        ))}

        <Box sx={{ flexGrow: 1 }} />
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.63rem', color: '#30363D' }}>
          {filtered.length} events
        </Typography>
        <Box
          onClick={clear}
          sx={{ fontFamily: 'monospace', fontSize: '0.63rem', color: '#484F58', cursor: 'pointer', '&:hover': { color: '#8B949E' } }}
        >
          [CLEAR]
        </Box>
      </Box>

      {/* Terminal feed */}
      <Box
        ref={feedRef}
        sx={{
          flex: 1,
          backgroundColor: '#0D1117',
          border: '1px solid #1C2128',
          borderRadius: 1,
          overflow: 'auto',
          p: 1.5,
          fontFamily: 'monospace',
          '&::-webkit-scrollbar': { width: 3 },
          '&::-webkit-scrollbar-track': { background: 'transparent' },
          '&::-webkit-scrollbar-thumb': { background: '#21262D' },
        }}
      >
        {filtered.length === 0 ? (
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.75rem', color: '#30363D' }}>
            — no activity yet — probe events will appear as the system polls —
          </Typography>
        ) : (
          filtered.map((entry) => (
            <Box
              key={entry.id}
              sx={{
                display: 'flex', gap: 1.5, lineHeight: 1.85,
                '&:hover': { backgroundColor: 'rgba(255,255,255,0.02)' },
                borderRadius: 0.5,
              }}
            >
              <Typography component="span" sx={{ fontFamily: 'monospace', fontSize: '0.7rem', color: '#30363D', flexShrink: 0, userSelect: 'none' }}>
                {format(new Date(entry.ts), 'HH:mm:ss')}
              </Typography>
              <Typography component="span" sx={{
                fontFamily: 'monospace', fontSize: '0.7rem',
                color: CAT_COLOR[entry.category] ?? '#484F58',
                fontWeight: 700, width: 60, flexShrink: 0,
              }}>
                {entry.category}
              </Typography>
              <Typography component="span" sx={{ fontFamily: 'monospace', fontSize: '0.7rem', color: '#8B949E', flexGrow: 1 }}>
                {entry.message}
              </Typography>
              {entry.detail && (
                <Typography component="span" sx={{ fontFamily: 'monospace', fontSize: '0.67rem', color: '#484F58', flexShrink: 0 }}>
                  {entry.detail}
                </Typography>
              )}
            </Box>
          ))
        )}
      </Box>

      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.63rem', color: '#21262D' }}>
        Session-scoped · clears on refresh · events from API polling (not WebSocket)
      </Typography>
    </Box>
  );
};

export default ActivityFeed;
