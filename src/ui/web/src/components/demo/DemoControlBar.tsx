/**
 * DemoControlBar — synthetic demo control strip for the Command Center.
 *
 * Shown only when demo mode is active (MAIW_DEMO_MODE=true on the backend).
 * All state comes from /api/v1/demo/* endpoints — no synthetic client-side transitions.
 *
 * Layout:
 *   [SYNTHETIC DEMO badge] [scenario selector] [START|PAUSE|RESUME|RESET|TICK] [status pill] [CHAOS panel]
 */

import React, { useState, useCallback, useEffect } from 'react';
import { Box, Typography, Select, MenuItem, CircularProgress } from '@mui/material';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { demoAPI, ScenarioMeta, InjectEventType, DemoStatus } from '../../services/demoAPI';
import { format } from 'date-fns';

// ── Scenario objectives — demo narrative, not duplicating YAML description ────

const SCENARIO_OBJECTIVES: Record<string, string> = {
  healthy_baseline: 'Validate nominal operations — expect no unnecessary agent action.',
  equipment_failure: 'Observe asset fault propagation → equipment agent proposal → DECIDE.',
  labor_constraint_wave_risk: 'Cross-domain reasoning: labor shortage triggers wave reprioritization.',
  stale_state: 'Demonstrate REQUIRES_FRESH_STATE — blocked execution, no mutation.',
  state_drift: 'Conflict detection before execution — drift between world truth and MAIW perception.',
};

// ── Inject event definitions ──────────────────────────────────────────────────

interface InjectDef {
  type: InjectEventType;
  label: string;
  color: string;
  buildPayload: (world: DemoStatus['world']) => Record<string, any>;
}

const INJECT_EVENTS: InjectDef[] = [
  {
    type: 'equipment_fault',
    label: 'EQUIP FAULT',
    color: '#F85149',
    buildPayload: (w) => ({
      asset_id: w?.equipment?.available ? 'AGV-01' : 'AGV-01',
      fault_code: 'E_MOTOR_OVERTEMP',
      new_status: 'offline',
    }),
  },
  {
    type: 'equipment_restore',
    label: 'EQUIP RESTORE',
    color: '#3FB950',
    buildPayload: () => ({ asset_id: 'AGV-01', new_status: 'available', battery_pct: 85 }),
  },
  {
    type: 'worker_absence',
    label: 'LABOR SHORT',
    color: '#D29922',
    buildPayload: () => ({ worker_id: 'w-002' }),
  },
  {
    type: 'worker_return',
    label: 'LABOR RETURN',
    color: '#3FB950',
    buildPayload: () => ({ worker_id: 'w-002' }),
  },
  {
    type: 'low_stock',
    label: 'LOW STOCK',
    color: '#D29922',
    buildPayload: () => ({ sku: 'SKU-1001', quantity_available: 50 }),
  },
  {
    type: 'wave_delay',
    label: 'WAVE DELAY',
    color: '#F85149',
    buildPayload: () => ({
      new_priority: 'critical',
      deadline: new Date(Date.now() + 30 * 60 * 1000).toISOString(),
    }),
  },
];

// ── Primitives ────────────────────────────────────────────────────────────────

function Btn({
  label, color = '#58A6FF', disabled, onClick, loading,
}: {
  label: string; color?: string; disabled?: boolean; onClick: () => void; loading?: boolean;
}) {
  return (
    <Box
      onClick={disabled || loading ? undefined : onClick}
      sx={{
        fontFamily: 'monospace', fontSize: '0.63rem', fontWeight: 700,
        letterSpacing: '0.06em', px: 1.25, py: 0.5,
        border: `1px solid ${color}`,
        borderRadius: 0.5,
        color,
        cursor: disabled ? 'default' : 'pointer',
        userSelect: 'none',
        display: 'flex', alignItems: 'center', gap: 0.5,
        opacity: disabled ? 0.5 : 1,
        '&:hover': disabled ? {} : { backgroundColor: `${color}18` },
        transition: 'opacity 0.15s',
      }}
    >
      {loading && <CircularProgress size={8} sx={{ color }} />}
      {label}
    </Box>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

interface Props {
  status: DemoStatus | null;
  onStatusChange: () => void;
}

const DemoControlBar: React.FC<Props> = ({ status, onStatusChange }) => {
  const qc = useQueryClient();
  const [selectedScenario, setSelectedScenario] = useState<string>('');
  const [busy, setBusy] = useState<string | null>(null);
  const [injectMsg, setInjectMsg] = useState<string | null>(null);

  const { data: scenarios = [] } = useQuery<ScenarioMeta[]>({
    queryKey: ['demo-scenarios'],
    queryFn: demoAPI.listScenarios,
    staleTime: 60000,
  });

  // Sync selector with active scenario
  useEffect(() => {
    if (status?.scenario?.name && !selectedScenario) {
      setSelectedScenario(status.scenario.name);
    }
  }, [status?.scenario?.name, selectedScenario]);

  const invalidate = useCallback(() => {
    qc.invalidateQueries({ queryKey: ['demo-status'] });
    onStatusChange();
  }, [qc, onStatusChange]);

  const doStart = useCallback(async () => {
    if (!selectedScenario) return;
    setBusy('start');
    try { await demoAPI.startScenario(selectedScenario); invalidate(); }
    catch (e: any) { console.error('demo start:', e.message); }
    finally { setBusy(null); }
  }, [selectedScenario, invalidate]);

  const doPause = useCallback(async () => {
    setBusy('pause');
    try { await demoAPI.pauseScenario(); invalidate(); }
    catch (e: any) { console.error('demo pause:', e.message); }
    finally { setBusy(null); }
  }, [invalidate]);

  const doResume = useCallback(async () => {
    setBusy('resume');
    try { await demoAPI.resumeScenario(); invalidate(); }
    catch (e: any) { console.error('demo resume:', e.message); }
    finally { setBusy(null); }
  }, [invalidate]);

  const doReset = useCallback(async () => {
    setBusy('reset');
    try { await demoAPI.resetScenario(); invalidate(); }
    catch (e: any) { console.error('demo reset:', e.message); }
    finally { setBusy(null); }
  }, [invalidate]);

  const doTick = useCallback(async () => {
    setBusy('tick');
    try { await demoAPI.tick(60); invalidate(); }
    catch (e: any) { console.error('demo tick:', e.message); }
    finally { setBusy(null); }
  }, [invalidate]);

  const doInject = useCallback(async (def: InjectDef) => {
    setBusy(`inject:${def.type}`);
    setInjectMsg(null);
    try {
      await demoAPI.inject(def.type, def.buildPayload(status?.world ?? null));
      setInjectMsg(`✓ ${def.label}`);
      invalidate();
    } catch (e: any) {
      setInjectMsg(`✕ ${e?.response?.data?.detail ?? e.message}`);
    }
    finally { setBusy(null); }
  }, [status?.world, invalidate]);

  const active = status?.active ?? false;
  const paused = status?.paused ?? false;
  const simMeta = status?.scenario;
  const world = status?.world;
  const runLabel = active ? (paused ? 'PAUSED' : 'RUNNING') : 'STOPPED';
  const runColor = active ? (paused ? '#D29922' : '#3FB950') : '#6E7681';

  const clockDisplay = world?.clock_iso
    ? format(new Date(world.clock_iso), 'HH:mm:ss')
    : '—';

  const objective = simMeta ? (SCENARIO_OBJECTIVES[simMeta.name] ?? simMeta.description) : null;

  return (
    <Box
      data-testid="demo-control-bar"
      sx={{
        border: '1px solid #76B900',
        borderRadius: 1,
        overflow: 'hidden',
        flexShrink: 0,
        backgroundColor: '#080C10',
      }}
    >
      {/* ── Header row ─────────────────────────────────────────────────────── */}
      <Box sx={{
        display: 'flex', alignItems: 'center', gap: 2,
        px: 1.5, py: 1,
        borderBottom: '1px solid #1C2128',
        backgroundColor: '#0A110A',
        flexWrap: 'nowrap',
        minHeight: 44,
      }}>
        {/* Badge */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexShrink: 0 }}>
          <Box sx={{
            width: 6, height: 6, borderRadius: '50%',
            backgroundColor: '#76B900',
            boxShadow: '0 0 6px #76B900',
            animation: active && !paused ? 'demoPulse 2s ease-in-out infinite' : 'none',
            '@keyframes demoPulse': { '0%,100%': { opacity: 1 }, '50%': { opacity: 0.3 } },
          }} />
          <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.62rem', color: '#76B900', letterSpacing: '0.12em' }}>
            SYNTHETIC DEMO
          </Typography>
        </Box>

        <Box sx={{ width: 1, height: 20, backgroundColor: '#30363D', flexShrink: 0 }} />

        {/* Scenario selector */}
        <Select
          size="small"
          value={selectedScenario}
          onChange={(e) => setSelectedScenario(e.target.value as string)}
          displayEmpty
          data-testid="scenario-selector"
          sx={{
            fontFamily: 'monospace', fontSize: '0.68rem', color: '#E6EDF3',
            height: 30, minWidth: 220,
            '& .MuiOutlinedInput-notchedOutline': { borderColor: selectedScenario ? '#484F58' : '#76B900', borderWidth: selectedScenario ? 1 : 1 },
            '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: '#76B900' },
            '&.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: '#76B900' },
            '& .MuiSelect-select': { py: 0.5, px: 1.5 },
            '& .MuiSvgIcon-root': { color: '#76B900' },
            backgroundColor: '#0D1117',
          }}
        >
          <MenuItem value="" sx={{ fontFamily: 'monospace', fontSize: '0.68rem' }}>— select scenario —</MenuItem>
          {scenarios.map(s => (
            <MenuItem key={s.name} value={s.name} sx={{ fontFamily: 'monospace', fontSize: '0.68rem' }}>
              {s.display_name}
            </MenuItem>
          ))}
        </Select>

        {/* Controls */}
        <Btn label="START" color="#76B900" disabled={!selectedScenario || !!busy} onClick={doStart} loading={busy === 'start'} />
        <Btn label="PAUSE" disabled={!active || paused || !!busy} onClick={doPause} loading={busy === 'pause'} />
        <Btn label="RESUME" color="#3FB950" disabled={!active || !paused || !!busy} onClick={doResume} loading={busy === 'resume'} />
        <Btn label="RESET" color="#D29922" disabled={!active || !!busy} onClick={doReset} loading={busy === 'reset'} />
        <Btn label="+60s" color="#58A6FF" disabled={!active || paused || !!busy} onClick={doTick} loading={busy === 'tick'} />

        <Box sx={{ flexGrow: 1 }} />

        {/* Status pill */}
        <Box sx={{
          display: 'flex', alignItems: 'center', gap: 0.75,
          px: 1, py: 0.3,
          border: `1px solid ${runColor}`,
          borderRadius: 0.5,
          backgroundColor: `${runColor}10`,
        }}>
          <Box sx={{ width: 5, height: 5, borderRadius: '50%', backgroundColor: runColor }} />
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', fontWeight: 700, color: runColor }}>
            {runLabel}
          </Typography>
        </Box>

        {/* Sim clock */}
        {active && (
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#484F58' }}>
            SIM {clockDisplay} (+{world?.elapsed_seconds ?? 0}s)
          </Typography>
        )}
      </Box>

      {/* ── Body: narrative + world KPIs + chaos ───────────────────────────── */}
      {(active || objective) && (
        <Box sx={{ display: 'flex', gap: 0, minHeight: 0 }}>

          {/* Scenario narrative */}
          <Box sx={{ flex: 1, px: 1.5, py: 0.75, borderRight: '1px solid #1C2128' }}>
            {simMeta && (
              <>
                <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'baseline', mb: 0.5 }}>
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.7rem', fontWeight: 700, color: '#C9D1D9' }}>
                    {simMeta.display_name.toUpperCase()}
                  </Typography>
                  {simMeta.tags.map(t => (
                    <Typography key={t} sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58' }}>
                      [{t}]
                    </Typography>
                  ))}
                </Box>
                {objective && (
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', color: '#8B949E', lineHeight: 1.5 }}>
                    {objective}
                  </Typography>
                )}
              </>
            )}
            {!simMeta && (
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', color: '#30363D' }}>
                Select a scenario to begin.
              </Typography>
            )}
          </Box>

          {/* World KPIs (live from backend status) */}
          {world && (
            <Box sx={{ px: 1.5, py: 0.75, borderRight: '1px solid #1C2128', minWidth: 140 }}>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58', letterSpacing: '0.1em', mb: 0.5 }}>
                WORLD STATE
              </Typography>
              {[
                { label: 'Equipment', val: `${world.equipment.available}/${world.equipment.total} avail`, alarm: world.equipment.offline > 0 || world.equipment.maintenance > 0 },
                { label: 'Workers', val: `${world.workers.active}/${world.workers.total} active`, alarm: world.workers.active < world.workers.total },
                { label: 'Tasks', val: `${world.tasks.pending} pending`, alarm: world.tasks.pending > 3 },
                { label: 'Low stock', val: `${world.inventory.low_stock} SKUs`, alarm: world.inventory.low_stock > 0 },
              ].map(({ label, val, alarm }) => (
                <Box key={label} sx={{ display: 'flex', justifyContent: 'space-between', gap: 1.5, py: 0.25 }}>
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58' }}>{label}</Typography>
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', fontWeight: 700, color: alarm ? '#D29922' : '#6E7681' }}>
                    {val}
                  </Typography>
                </Box>
              ))}
            </Box>
          )}

          {/* Chaos injection */}
          <Box sx={{ px: 1.5, py: 0.75 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.75 }}>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58', letterSpacing: '0.1em' }}>
                CHAOS INJECT
              </Typography>
              {injectMsg && (
                <Typography sx={{
                  fontFamily: 'monospace', fontSize: '0.6rem',
                  color: injectMsg.startsWith('✓') ? '#3FB950' : '#F85149',
                }}>
                  {injectMsg}
                </Typography>
              )}
            </Box>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75 }}>
              {INJECT_EVENTS.map(def => (
                <Btn
                  key={def.type}
                  label={def.label}
                  color={def.color}
                  disabled={!active || !!busy}
                  onClick={() => doInject(def)}
                  loading={busy === `inject:${def.type}`}
                />
              ))}
            </Box>
          </Box>
        </Box>
      )}
    </Box>
  );
};

export default DemoControlBar;
