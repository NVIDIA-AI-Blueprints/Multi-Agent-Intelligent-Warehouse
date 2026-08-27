import React, { useState, useCallback } from 'react';
import { Box, Typography } from '@mui/material';
import { useQueryClient } from '@tanstack/react-query';
import { useDemoStatus } from '../hooks/useDemoStatus';
import { useRuntimeStatus } from '../hooks/useRuntimeStatus';
import { demoAPI } from '../services/demoAPI';
import ScenarioSelector from '../components/demo/ScenarioSelector';

// ── Phase 12A: Shell + Scenario Selection ─────────────────────────────────────
// 12B will replace <ActiveDemoPlaceholder> with the full lifecycle layout.

const WAREHOUSE_ID = process.env.REACT_APP_WAREHOUSE_ID || 'DC-47';

type DemoMode = 'operations' | 'reliability';

// ── Sub-components ─────────────────────────────────────────────────────────────

function ModeSwitcher({ mode, onChange }: { mode: DemoMode; onChange: (m: DemoMode) => void }) {
  return (
    <Box sx={{ display: 'flex', gap: 0 }}>
      {(['operations', 'reliability'] as DemoMode[]).map((m, i) => (
        <Box
          key={m}
          component="button"
          onClick={() => onChange(m)}
          sx={{
            background: mode === m ? '#1C2128' : 'transparent',
            border: '1px solid #21262D',
            borderRight: i === 0 ? 'none' : '1px solid #21262D',
            borderRadius: i === 0 ? '4px 0 0 4px' : '0 4px 4px 0',
            px: '10px', py: '4px',
            fontFamily: 'monospace',
            fontSize: '0.65rem',
            fontWeight: mode === m ? 700 : 400,
            color: mode === m ? '#C9D1D9' : '#6E7681',
            cursor: 'pointer',
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            '&:hover': { color: '#C9D1D9' },
          }}
        >
          {m}
        </Box>
      ))}
    </Box>
  );
}

function ExpertToggle({ on, onToggle }: { on: boolean; onToggle: () => void }) {
  return (
    <Box
      component="button"
      onClick={onToggle}
      sx={{
        display: 'flex', alignItems: 'center', gap: 0.75,
        background: on ? '#0d2146' : 'transparent',
        border: on ? '1px solid #1F6FEB' : '1px solid #30363D',
        borderRadius: '4px',
        px: '10px', py: '4px',
        fontFamily: 'monospace',
        fontSize: '0.65rem',
        color: on ? '#58A6FF' : '#6E7681',
        cursor: 'pointer',
        letterSpacing: '0.06em',
        textTransform: 'uppercase',
        '&:hover': { color: on ? '#58A6FF' : '#C9D1D9' },
      }}
    >
      Expert
      <Box sx={{
        width: 8, height: 8, borderRadius: '50%',
        background: on ? '#58A6FF' : '#30363D',
        flexShrink: 0,
      }} />
    </Box>
  );
}

function StateDot({ color, glow }: { color: string; glow?: boolean }) {
  return (
    <Box sx={{
      width: 6, height: 6, borderRadius: '50%',
      background: color,
      flexShrink: 0,
      boxShadow: glow ? `0 0 5px ${color}` : 'none',
    }} />
  );
}

function StateStrip({ wareId, stateLabel, systemLabel, systemColor }: {
  wareId: string;
  stateLabel: string;
  systemLabel: string;
  systemColor: string;
}) {
  return (
    <Box sx={{
      display: 'flex', alignItems: 'center', gap: 2,
      px: 2, py: '5px',
      borderBottom: '1px solid #21262D',
      background: '#0D1117',
    }}>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58', letterSpacing: '0.06em' }}>
        {wareId}
      </Typography>
      <Box sx={{ width: '1px', height: 10, background: '#21262D' }} />
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
        <StateDot color="#3FB950" glow />
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#6E7681', letterSpacing: '0.06em' }}>
          STATE
        </Typography>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#C9D1D9', fontWeight: 700 }}>
          {stateLabel}
        </Typography>
      </Box>
      <Box sx={{ width: '1px', height: 10, background: '#21262D' }} />
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
        <StateDot color={systemColor} glow={systemColor === '#3FB950'} />
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#6E7681', letterSpacing: '0.06em' }}>
          SYSTEM
        </Typography>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#C9D1D9', fontWeight: 700 }}>
          {systemLabel}
        </Typography>
      </Box>
    </Box>
  );
}

// ── Active demo placeholder (replaced in 12B) ──────────────────────────────────

function ActiveDemoPlaceholder({ scenarioName }: { scenarioName: string }) {
  return (
    <Box sx={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      height: 260, gap: 1,
    }}>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.72rem', color: '#3FB950' }}>
        ● {scenarioName.replace(/_/g, ' ').toUpperCase()} — RUNNING
      </Typography>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58' }}>
        Lifecycle rail, stage content pane, and operational context strip coming in Phase 12B.
      </Typography>
    </Box>
  );
}

// ── Shell ──────────────────────────────────────────────────────────────────────

export default function DemoShell() {
  const [mode, setMode] = useState<DemoMode>('operations');
  const [expertMode, setExpertMode] = useState(false);
  const queryClient = useQueryClient();

  const { status: demoStatus, isLoading: demoLoading } = useDemoStatus();
  const { data: runtime } = useRuntimeStatus();

  const scenarioActive = demoStatus?.active === true;
  const scenarioName = demoStatus?.scenario?.display_name ?? demoStatus?.scenario?.name ?? '';

  // State freshness: use state_freshness_seconds from current_kpis
  const freshnessSecs = demoStatus?.current_kpis?.state_freshness_seconds;
  const stateLabel = freshnessSecs != null && freshnessSecs < 120 ? 'FRESH' : 'STALE';

  // System health from runtime status
  const sysStatus = runtime?.maiw_operational_status ?? 'UNKNOWN';
  const systemColor =
    sysStatus === 'HEALTHY' ? '#3FB950' :
    sysStatus === 'DEGRADED' ? '#D29922' : '#484F58';

  const handleStart = useCallback(async (name: string) => {
    await demoAPI.startScenario(name);
    await queryClient.invalidateQueries({ queryKey: ['demo-status'] });
  }, [queryClient]);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100%', background: '#0D1117' }}>
      {/* Top nav */}
      <Box sx={{
        display: 'flex', alignItems: 'center', gap: 2,
        px: 2, py: '7px',
        borderBottom: '1px solid #21262D',
        background: '#0D1117',
      }}>
        <Typography sx={{
          fontFamily: 'monospace', fontSize: '0.72rem', fontWeight: 700,
          color: '#C9D1D9', letterSpacing: '0.08em', textTransform: 'uppercase',
          flexShrink: 0,
        }}>
          MAIW Command Center
        </Typography>

        <Box sx={{
          width: '1px', height: 14, background: '#21262D', flexShrink: 0,
        }} />

        <Box sx={{
          background: '#0d2146',
          border: '1px solid #21262D',
          borderRadius: '4px',
          px: '6px', py: '1px',
          fontFamily: 'monospace',
          fontSize: '0.6rem',
          color: '#58A6FF',
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
          flexShrink: 0,
        }}>
          Synthetic demo
        </Box>

        <Box sx={{ flexGrow: 1 }} />

        <ModeSwitcher mode={mode} onChange={setMode} />

        <Box sx={{ width: '1px', height: 14, background: '#21262D', flexShrink: 0 }} />

        <ExpertToggle on={expertMode} onToggle={() => setExpertMode(e => !e)} />
      </Box>

      {/* State strip */}
      <StateStrip
        wareId={WAREHOUSE_ID}
        stateLabel={stateLabel}
        systemLabel={sysStatus}
        systemColor={systemColor}
      />

      {/* Content area */}
      <Box sx={{ flexGrow: 1, overflow: 'auto' }}>
        {demoLoading && !demoStatus && (
          <Box sx={{ p: 3 }}>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.72rem', color: '#484F58' }}>
              Connecting to demo backend...
            </Typography>
          </Box>
        )}

        {!demoLoading && !scenarioActive && (
          <ScenarioSelector onStart={handleStart} />
        )}

        {scenarioActive && mode === 'operations' && (
          <ActiveDemoPlaceholder scenarioName={scenarioName} />
        )}

        {scenarioActive && mode === 'reliability' && (
          <Box sx={{ p: 3 }}>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.72rem', color: '#484F58' }}>
              Reliability demo mode — coming in Phase 12F.
            </Typography>
          </Box>
        )}

        {/* Expert overlay: shown as bottom panel for now; 12G will style it properly */}
        {expertMode && (
          <Box sx={{
            mx: 3, mb: 2,
            background: '#161B22',
            border: '1px solid #1F6FEB33',
            borderRadius: '6px',
            p: 2,
          }}>
            <Typography sx={{
              fontFamily: 'monospace', fontSize: '0.6rem', fontWeight: 700,
              color: '#58A6FF', letterSpacing: '0.1em', textTransform: 'uppercase', mb: 1,
            }}>
              Expert view — system details (12G: full layout)
            </Typography>
            <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 2 }}>
              <Box>
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#484F58', mb: 0.5, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Runtime</Typography>
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', color: '#8B949E' }}>
                  maiw_operational_status: {runtime?.maiw_operational_status ?? '—'}<br />
                  model_gateway_status: {runtime?.model_gateway_status ?? '—'}
                </Typography>
              </Box>
              <Box>
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#484F58', mb: 0.5, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Domain health</Typography>
                {runtime?.domain_health ? (
                  Object.entries(runtime.domain_health).map(([k, v]) => (
                    <Typography key={k} sx={{ fontFamily: 'monospace', fontSize: '0.68rem', color: '#8B949E' }}>
                      {k}: {v}
                    </Typography>
                  ))
                ) : (
                  <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', color: '#484F58' }}>—</Typography>
                )}
              </Box>
              <Box>
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#484F58', mb: 0.5, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Scenario</Typography>
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', color: '#8B949E' }}>
                  active: {String(demoStatus?.active ?? false)}<br />
                  name: {demoStatus?.scenario?.name ?? '—'}<br />
                  elapsed: {demoStatus?.world?.elapsed_seconds ?? 0}s
                </Typography>
              </Box>
            </Box>
          </Box>
        )}
      </Box>

      {/* System footer */}
      <Box sx={{
        display: 'flex', alignItems: 'center', gap: 2,
        px: 2, py: '5px',
        borderTop: '1px solid #21262D',
        background: '#0D1117',
      }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
          <StateDot color={systemColor} />
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#484F58', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            System
          </Typography>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#6E7681', fontWeight: 700 }}>
            {sysStatus}
          </Typography>
        </Box>
        <Box sx={{ width: '1px', height: 10, background: '#21262D' }} />
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#484F58', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          Safety
        </Typography>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#3FB950' }}>
          ✓ All invariants hold
        </Typography>
        <Box sx={{ flexGrow: 1 }} />
        <Typography sx={{
          fontFamily: 'monospace', fontSize: '0.62rem', color: '#484F58',
          cursor: 'pointer',
          '&:hover': { color: '#8B949E' },
        }}>
          Details ›
        </Typography>
      </Box>
    </Box>
  );
}
