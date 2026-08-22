import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Chip,
  Button,
  Switch,
  FormControlLabel,
  Divider,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
} from '@mui/material';
import {
  Circle as DotIcon,
  DeleteOutline as ClearIcon,
  FiberManualRecord as RecordIcon,
} from '@mui/icons-material';
import { format } from 'date-fns';
import { useRuntimeStatus } from '../hooks/useRuntimeStatus';
import { useQuery } from '@tanstack/react-query';
import { healthAPI, mcpAPI } from '../services/api';

interface LogEntry {
  id: string;
  ts: string;
  level: 'INFO' | 'WARN' | 'ERROR' | 'OK';
  source: string;
  message: string;
}

const STORAGE_KEY = 'maiw_activity_feed';
const MAX_ENTRIES = 200;

function levelColor(level: LogEntry['level']) {
  return { INFO: '#58A6FF', WARN: '#D29922', ERROR: '#F85149', OK: '#3FB950' }[level];
}

function makeEntry(level: LogEntry['level'], source: string, message: string): LogEntry {
  return { id: `${Date.now()}-${Math.random()}`, ts: new Date().toISOString(), level, source, message };
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

const ActivityFeed: React.FC = () => {
  const { entries, add, clear } = usePersistentLog();
  const [autoScroll, setAutoScroll] = useState(true);
  const [filter, setFilter] = useState<'ALL' | 'INFO' | 'WARN' | 'ERROR' | 'OK'>('ALL');
  const [live, setLive] = useState(true);
  const feedRef = useRef<HTMLDivElement>(null);
  const prevRuntimeRef = useRef<any>(null);

  const { data: runtime } = useRuntimeStatus();
  const { data: live_ } = useQuery({
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

  // Log when live probe returns
  const liveRef = useRef<any>(null);
  useEffect(() => {
    if (live_ && live_?.status !== liveRef.current?.status) {
      const ok = live_.status === 'alive';
      add(makeEntry(ok ? 'OK' : 'ERROR', '/api/v1/live', ok ? 'API liveness probe: alive' : `API liveness probe: ${live_.status}`));
      liveRef.current = live_;
    }
  }, [live_, add]);

  // Log runtime status changes
  useEffect(() => {
    if (!runtime) return;
    const prev = prevRuntimeRef.current;
    if (!prev) {
      add(makeEntry('INFO', 'runtime/status', `Runtime initialized: ${runtime.runtime_initialized} · ModelGateway: ${runtime.model_gateway_available} · DecisionEngine: ${runtime.decision_engine_available}`));
    } else {
      if (prev.runtime_initialized !== runtime.runtime_initialized) {
        add(makeEntry(runtime.runtime_initialized ? 'OK' : 'WARN', 'runtime/status', `Runtime initialized changed → ${runtime.runtime_initialized}`));
      }
      if (prev.model_gateway_available !== runtime.model_gateway_available) {
        add(makeEntry(runtime.model_gateway_available ? 'OK' : 'WARN', 'runtime/status', `ModelGateway available changed → ${runtime.model_gateway_available}`));
      }
    }
    prevRuntimeRef.current = runtime;
  }, [runtime, add]);

  // Log MCP status changes
  const mcpRef = useRef<any>(null);
  useEffect(() => {
    if (!mcpStatus) return;
    if (JSON.stringify(mcpStatus) !== JSON.stringify(mcpRef.current)) {
      const domains = mcpStatus.domains ?? {};
      const domainSummary = Object.entries(domains)
        .map(([k, v]: [string, any]) => `${k}:${v.available ? 'up' : 'down'}`)
        .join(' ');
      add(makeEntry('INFO', 'mcp/status', `MCP domain poll · ${domainSummary || 'no domains reported'}`));
      mcpRef.current = mcpStatus;
    }
  }, [mcpStatus, add]);

  useEffect(() => {
    if (autoScroll && feedRef.current) {
      feedRef.current.scrollTop = 0;
    }
  }, [entries, autoScroll]);

  const filtered = filter === 'ALL' ? entries : entries.filter((e) => e.level === filter);

  return (
    <Box sx={{ pb: 4 }}>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" sx={{ fontWeight: 700, color: 'text.primary', letterSpacing: '-0.02em' }}>
          Activity Feed
        </Typography>
        <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
          Live session log of API probe results and runtime state changes
        </Typography>
      </Box>

      {/* Controls */}
      <Card sx={{ backgroundColor: 'background.paper', mb: 2 }}>
        <CardContent sx={{ py: 1.5, display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
            <RecordIcon sx={{ fontSize: 10, color: live ? '#F85149' : '#484F58', animation: live ? 'pulse 1.5s ease infinite' : 'none',
              '@keyframes pulse': { '0%,100%': { opacity: 1 }, '50%': { opacity: 0.3 } } }} />
            <FormControlLabel
              control={<Switch checked={live} onChange={(e) => setLive(e.target.checked)} size="small" />}
              label={<Typography variant="caption" sx={{ fontFamily: 'monospace', color: 'text.secondary' }}>LIVE</Typography>}
              sx={{ m: 0 }}
            />
          </Box>
          <FormControlLabel
            control={<Switch checked={autoScroll} onChange={(e) => setAutoScroll(e.target.checked)} size="small" />}
            label={<Typography variant="caption" sx={{ color: 'text.secondary' }}>Auto-scroll</Typography>}
            sx={{ m: 0 }}
          />
          <FormControl size="small" sx={{ minWidth: 100 }}>
            <InputLabel sx={{ fontSize: '0.8rem' }}>Level</InputLabel>
            <Select
              value={filter}
              onChange={(e) => setFilter(e.target.value as any)}
              label="Level"
              sx={{ fontSize: '0.8rem' }}
            >
              {(['ALL', 'OK', 'INFO', 'WARN', 'ERROR'] as const).map((l) => (
                <MenuItem key={l} value={l} sx={{ fontSize: '0.8rem', fontFamily: 'monospace' }}>{l}</MenuItem>
              ))}
            </Select>
          </FormControl>
          <Box sx={{ flexGrow: 1 }} />
          <Typography variant="caption" sx={{ color: '#484F58', fontFamily: 'monospace' }}>
            {filtered.length} / {MAX_ENTRIES} entries
          </Typography>
          <Button size="small" startIcon={<ClearIcon />} onClick={clear} sx={{ color: 'text.secondary', fontSize: '0.75rem' }}>
            Clear
          </Button>
        </CardContent>
      </Card>

      {/* Terminal feed */}
      <Box
        ref={feedRef}
        sx={{
          backgroundColor: '#0D1117',
          border: '1px solid #21262D',
          borderRadius: 2,
          p: 1.5,
          height: 'calc(100vh - 340px)',
          minHeight: 300,
          overflowY: 'auto',
          fontFamily: 'monospace',
          fontSize: '0.78rem',
          lineHeight: 1.7,
        }}
      >
        {filtered.length === 0 ? (
          <Typography sx={{ color: '#484F58', fontFamily: 'monospace', fontSize: '0.8rem', p: 1 }}>
            — no activity yet — polling will begin automatically when live probes complete —
          </Typography>
        ) : (
          filtered.map((entry) => (
            <Box key={entry.id} sx={{ display: 'flex', gap: 1.5, py: 0.15, '&:hover': { backgroundColor: 'rgba(255,255,255,0.02)' }, borderRadius: 0.5 }}>
              <Typography component="span" sx={{ color: '#484F58', fontFamily: 'monospace', fontSize: '0.73rem', flexShrink: 0, lineHeight: 1.7 }}>
                {format(new Date(entry.ts), 'HH:mm:ss.SSS')}
              </Typography>
              <Typography component="span" sx={{ color: levelColor(entry.level), fontFamily: 'monospace', fontSize: '0.73rem', flexShrink: 0, fontWeight: 700, width: 40, lineHeight: 1.7 }}>
                {entry.level}
              </Typography>
              <Typography component="span" sx={{ color: '#58A6FF', fontFamily: 'monospace', fontSize: '0.73rem', flexShrink: 0, width: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', lineHeight: 1.7 }}>
                {entry.source}
              </Typography>
              <Typography component="span" sx={{ color: '#E6EDF3', fontFamily: 'monospace', fontSize: '0.73rem', lineHeight: 1.7, flexGrow: 1 }}>
                {entry.message}
              </Typography>
            </Box>
          ))
        )}
      </Box>

      <Typography variant="caption" sx={{ color: '#484F58', mt: 1, display: 'block' }}>
        Activity is session-scoped — clears on page refresh. Events are sourced from API probe polling, not a WebSocket stream.
      </Typography>
    </Box>
  );
};

export default ActivityFeed;
