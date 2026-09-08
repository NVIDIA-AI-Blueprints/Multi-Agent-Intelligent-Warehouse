import React, { useState, useCallback, useEffect } from 'react';
import { Box, CircularProgress, Typography } from '@mui/material';
import { useQueryClient } from '@tanstack/react-query';
import { useDemoStatus } from '../hooks/useDemoStatus';
import { useRuntimeStatus } from '../hooks/useRuntimeStatus';
import { useDemoSSE } from '../hooks/useDemoSSE';
import { useDemoLifecycle, RailStage } from '../hooks/useDemoLifecycle';
import { demoAPI, AnalysisResult } from '../services/demoAPI';
import ScenarioSelector from '../components/demo/ScenarioSelector';
import LifecycleRail from '../components/demo/LifecycleRail';
import OperationalContextStrip from '../components/demo/OperationalContextStrip';
import StageContentPane from '../components/demo/StageContentPane';
import ReliabilityPanel from '../components/demo/reliability/ReliabilityPanel';
import ExpertOverlay from '../components/demo/ExpertOverlay';
import CopilotDrawer from '../components/demo/copilot/CopilotDrawer';
import { useCopilotConversation, CopilotSystemCard } from '../hooks/useCopilotConversation';

const WAREHOUSE_ID = process.env.REACT_APP_WAREHOUSE_ID || 'DC-47';

type DemoMode = 'operations' | 'reliability';

// ── Chrome sub-components ──────────────────────────────────────────────────────

function ModeSwitcher({ mode, onChange }: { mode: DemoMode; onChange: (m: DemoMode) => void }) {
  return (
    <Box sx={{ display: 'flex', gap: 0 }} role="group" aria-label="Demo mode">
      {(['operations', 'reliability'] as DemoMode[]).map((m, i) => (
        <Box
          key={m}
          component="button"
          onClick={() => onChange(m)}
          aria-pressed={mode === m}
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
      aria-pressed={on}
      aria-label={on ? 'Expert view on' : 'Expert view off'}
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

/**
 * Phase15CopilotButton — Phase 15B: functional Copilot ASK entry point.
 * Enabled when a scenario is active; disabled otherwise.
 */
function Phase15CopilotButton({
  active,
  open,
  onClick,
}: {
  active: boolean;
  open: boolean;
  onClick: () => void;
}) {
  return (
    <Box
      component="button"
      disabled={!active}
      aria-disabled={!active}
      aria-label={active ? 'Open Copilot ASK panel' : 'Start a scenario to use Copilot'}
      data-testid="phase15-copilot-button"
      title={active ? 'Open Copilot ASK panel' : 'Start a scenario to use Copilot'}
      onClick={active ? onClick : undefined}
      sx={{
        display: 'flex', alignItems: 'center', gap: 0.75,
        background: open ? '#0d2146' : 'transparent',
        border: open ? '1px solid #58A6FF' : '1px solid #21262D',
        borderRadius: '4px',
        px: '10px', py: '4px',
        fontFamily: 'monospace',
        fontSize: '0.65rem',
        color: active ? (open ? '#58A6FF' : '#8B949E') : '#30363D',
        cursor: active ? 'pointer' : 'not-allowed',
        letterSpacing: '0.06em',
        textTransform: 'uppercase',
        opacity: active ? 1 : 0.5,
        '&:hover': active ? { color: '#58A6FF', borderColor: '#58A6FF44' } : {},
      }}
    >
      Copilot
      <Box component="span" sx={{
        fontFamily: 'monospace', fontSize: '0.52rem',
        color: active ? (open ? '#58A6FF' : '#6E7681') : '#484F58',
        border: '1px solid #21262D', borderRadius: '3px',
        px: '4px', py: '0px', ml: 0.25, lineHeight: 1.6,
      }}>
        ASK
      </Box>
    </Box>
  );
}

/**
 * SSEStatusChip — shows SSE connection state when a scenario is active.
 * Only renders during active scenario to avoid noise on idle screen.
 */
function SSEStatusChip({ connected, error }: { connected: boolean; error: string | null }) {
  if (connected) {
    return (
      <Box
        data-testid="sse-status-connected"
        sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}
      >
        <Box sx={{ width: 5, height: 5, borderRadius: '50%', background: '#3FB950', flexShrink: 0, boxShadow: '0 0 4px #3FB950' }} />
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
          Live
        </Typography>
      </Box>
    );
  }
  return (
    <Box
      data-testid="sse-status-disconnected"
      sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}
    >
      <Box sx={{ width: 5, height: 5, borderRadius: '50%', background: '#D29922', flexShrink: 0 }} />
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#D29922', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
        {error ? 'Reconnecting' : 'Connecting'}
      </Typography>
    </Box>
  );
}

/**
 * BackendErrorBanner — shown when backend returns null/unavailable and initial load is done.
 */
function BackendErrorBanner({ onRetry }: { onRetry: () => void }) {
  return (
    <Box
      data-testid="backend-error-banner"
      role="alert"
      sx={{
        m: 3,
        p: 2,
        background: '#1A0A0A',
        border: '1px solid #F8514944',
        borderRadius: '6px',
        display: 'flex',
        flexDirection: 'column',
        gap: 1,
        maxWidth: 480,
      }}
    >
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.72rem', fontWeight: 700, color: '#F85149', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
        Backend unavailable
      </Typography>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', color: '#8B949E', lineHeight: 1.5 }}>
        Cannot reach the MAIW demo API. Confirm the backend is running on port 8000 and the proxy is configured.
      </Typography>
      <Box
        component="button"
        onClick={onRetry}
        data-testid="backend-retry-button"
        sx={{
          alignSelf: 'flex-start',
          background: 'transparent',
          border: '1px solid #30363D',
          borderRadius: '4px',
          px: '12px', py: '6px',
          fontFamily: 'monospace', fontSize: '0.65rem',
          color: '#8B949E', cursor: 'pointer',
          '&:hover': { color: '#C9D1D9', borderColor: '#484F58' },
        }}
      >
        ↺ Retry connection
      </Box>
    </Box>
  );
}

function StateDot({ color, glow }: { color: string; glow?: boolean }) {
  return (
    <Box sx={{
      width: 6, height: 6, borderRadius: '50%',
      background: color, flexShrink: 0,
      boxShadow: glow ? `0 0 5px ${color}` : 'none',
    }} />
  );
}

function StateStrip({
  wareId,
  stateLabel,
  systemLabel,
  systemColor,
}: {
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

// ── Scenario header ────────────────────────────────────────────────────────────

function ScenarioHeader({
  displayName,
  elapsedSeconds,
  onReset,
  onPause,
  isPaused,
}: {
  displayName: string;
  elapsedSeconds: number;
  onReset: () => void;
  onPause: () => void;
  isPaused: boolean;
}) {
  return (
    <Box sx={{
      display: 'flex', alignItems: 'center', gap: 1.5,
      px: 2, py: '6px',
      borderBottom: '1px solid #21262D',
      background: '#0D1117',
    }}>
      <Typography sx={{
        fontFamily: 'monospace', fontSize: '0.72rem', fontWeight: 700,
        color: '#C9D1D9', textTransform: 'uppercase', letterSpacing: '0.04em',
      }}>
        {displayName}
      </Typography>
      <Typography sx={{
        fontFamily: 'monospace', fontSize: '0.65rem',
        color: '#484F58',
        background: '#161B22',
        border: '1px solid #21262D',
        borderRadius: '4px',
        px: '6px', py: '1px',
      }}>
        t={elapsedSeconds}s
      </Typography>
      <Box sx={{ flexGrow: 1 }} />
      <Box
        component="button"
        onClick={onPause}
        sx={{
          background: 'transparent', border: '1px solid #21262D', borderRadius: '4px',
          px: '8px', py: '3px', fontFamily: 'monospace', fontSize: '0.62rem',
          color: '#6E7681', cursor: 'pointer',
          '&:hover': { color: '#C9D1D9', borderColor: '#30363D' },
        }}
      >
        {isPaused ? 'Resume' : 'Pause'}
      </Box>
      <Box
        component="button"
        onClick={onReset}
        data-testid="reset-button"
        sx={{
          background: 'transparent', border: '1px solid #21262D', borderRadius: '4px',
          px: '8px', py: '3px', fontFamily: 'monospace', fontSize: '0.62rem',
          color: '#6E7681', cursor: 'pointer',
          '&:hover': { color: '#F85149', borderColor: '#6e1111' },
        }}
      >
        Reset
      </Box>
    </Box>
  );
}


// ── DemoShell ──────────────────────────────────────────────────────────────────

export default function DemoShell() {
  const [mode, setMode] = useState<DemoMode>('operations');
  const [expertMode, setExpertMode] = useState(false);
  const [expertDefaultTab, setExpertDefaultTab] = useState<'trace' | 'runtime' | 'raw'>('trace');
  // showSelector overrides demoStatus.active — set true on reset so ScenarioSelector
  // appears immediately without waiting for the status poll to confirm active:false.
  const [showSelector, setShowSelector] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [selectedStage, setSelectedStage] = useState<RailStage | null>(null);
  const [selectedApprovalId, setSelectedApprovalId] = useState<string | null>(null);
  const conversation = useCopilotConversation();
  const queryClient = useQueryClient();

  const { status: demoStatus, isLoading: demoLoading } = useDemoStatus();
  const { data: runtime } = useRuntimeStatus();

  const scenarioActive = demoStatus?.active === true && !showSelector;

  // SSE enabled only while a scenario is running — clear() on reset wipes stale events.
  const sseState = useDemoSSE(scenarioActive);

  // Derive rail state from SSE events + pending approvals (pure, no side-effects).
  const pendingApprovals = demoStatus?.pending_approvals ?? [];
  const { currentStage, completedStages, waitingForApproval } = useDemoLifecycle(
    sseState.events,
    pendingApprovals,
  );

  // Clear stage override once the lifecycle naturally reaches or passes the selected stage
  useEffect(() => {
    if (selectedStage && currentStage === selectedStage) {
      setSelectedStage(null);
    }
  }, [currentStage, selectedStage]);

  const effectiveStage: RailStage = selectedStage ?? currentStage;

  const handleReviewApproval = useCallback((pendingApprovalId: string) => {
    setCopilotOpen(false);
    setSelectedStage('APPROVE');
    setSelectedApprovalId(pendingApprovalId);
  }, []);

  const handleReturnToCopilot = useCallback((card: CopilotSystemCard) => {
    conversation.addSystemCard(card);
    setCopilotOpen(true);
  }, [conversation]);

  // System health indicators
  const sysStatus = runtime?.maiw_operational_status ?? 'UNKNOWN';
  const systemColor =
    sysStatus === 'HEALTHY' ? '#3FB950' :
    sysStatus === 'DEGRADED' ? '#D29922' : '#484F58';

  const freshnessSecs = demoStatus?.current_kpis?.state_freshness_seconds;
  const stateLabel = freshnessSecs != null && freshnessSecs < 120 ? 'FRESH' : 'STALE';

  // Detect backend unavailable: load done, no data
  const backendUnavailable = !demoLoading && demoStatus === null;

  // ── Handlers ────────────────────────────────────────────────────────────────

  const handleStart = useCallback(async (name: string) => {
    await demoAPI.startScenario(name);
    setShowSelector(false);
    sseState.clear();
    setSelectedStage(null);
    setSelectedApprovalId(null);
    conversation.reset();
    await queryClient.invalidateQueries({ queryKey: ['demo-status'] });
  }, [queryClient, sseState, conversation]);

  const handleReset = useCallback(async () => {
    setShowSelector(true);       // show selector immediately
    sseState.clear();            // wipe SSE buffer so no stale events leak
    setAnalysisResult(null);     // clear pipeline result from previous run
    setAnalyzing(false);
    setSelectedStage(null);
    setSelectedApprovalId(null);
    conversation.reset();
    await demoAPI.resetScenario();
    await queryClient.invalidateQueries({ queryKey: ['demo-status'] });
  }, [queryClient, sseState, conversation]);

  const handleAnalyze = useCallback(async () => {
    if (analyzing) return;
    setAnalyzing(true);
    try {
      const result = await demoAPI.analyze();
      setAnalysisResult(result);
      await queryClient.invalidateQueries({ queryKey: ['demo-status'] });
    } finally {
      setAnalyzing(false);
    }
  }, [analyzing, queryClient]);

  const handlePause = useCallback(async () => {
    if (demoStatus?.paused) {
      await demoAPI.resumeScenario();
    } else {
      await demoAPI.pauseScenario();
    }
    await queryClient.invalidateQueries({ queryKey: ['demo-status'] });
  }, [demoStatus, queryClient]);

  const handleViewFullTrace = useCallback(() => {
    setExpertDefaultTab('trace');
    setExpertMode(true);
  }, []);

  // ── Render ───────────────────────────────────────────────────────────────────

  const displayName = demoStatus?.scenario?.display_name ?? demoStatus?.scenario?.name ?? '';
  const elapsedSeconds = demoStatus?.world?.elapsed_seconds ?? 0;
  const isPaused = demoStatus?.paused ?? false;

  return (
    <Box
      data-testid="demo-shell"
      sx={{ display: 'flex', flexDirection: 'column', minHeight: '100%', background: '#0D1117' }}
    >
      {/* Top navigation */}
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
        <Box sx={{ width: '1px', height: 14, background: '#21262D', flexShrink: 0 }} />
        <Box sx={{
          background: '#0d2146', border: '1px solid #21262D', borderRadius: '4px',
          px: '6px', py: '1px',
          fontFamily: 'monospace', fontSize: '0.6rem', color: '#58A6FF',
          letterSpacing: '0.06em', textTransform: 'uppercase', flexShrink: 0,
        }}>
          Synthetic demo
        </Box>
        <Box sx={{ flexGrow: 1 }} />
        <Phase15CopilotButton
          active={scenarioActive}
          open={copilotOpen}
          onClick={() => setCopilotOpen(o => !o)}
        />
        <Box sx={{ width: '1px', height: 14, background: '#21262D', flexShrink: 0 }} />
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

      {/* Content */}
      <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', overflow: 'auto' }}>
        {/* ── Loading: initial connection ── */}
        {demoLoading && !demoStatus && (
          <Box
            data-testid="demo-loading"
            role="status"
            aria-label="Connecting to demo backend"
            sx={{ p: 3, display: 'flex', alignItems: 'center', gap: 1.5 }}
          >
            <CircularProgress size={14} sx={{ color: '#484F58' }} />
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.72rem', color: '#484F58' }}>
              Connecting to demo backend...
            </Typography>
          </Box>
        )}

        {/* ── Backend unavailable ── */}
        {backendUnavailable && (
          <BackendErrorBanner onRetry={() => queryClient.invalidateQueries({ queryKey: ['demo-status'] })} />
        )}

        {/* ── First-run: scenario selection ── */}
        {(!scenarioActive) && !demoLoading && !backendUnavailable && (
          <ScenarioSelector onStart={handleStart} />
        )}

        {/* ── Active scenario: lifecycle layout ── */}
        {scenarioActive && mode === 'operations' && (
          <>
            {/* Scenario header with controls */}
            <ScenarioHeader
              displayName={displayName}
              elapsedSeconds={elapsedSeconds}
              onReset={handleReset}
              onPause={handlePause}
              isPaused={isPaused}
            />

            {/* Lifecycle rail — driven by SSE events */}
            <LifecycleRail
              currentStage={effectiveStage}
              completedStages={completedStages}
              waitingForApproval={waitingForApproval}
            />

            {/* Persistent operational context — driven by current_kpis */}
            <OperationalContextStrip kpis={demoStatus?.current_kpis ?? null} />

            {/* Stage content — SSE-driven per-stage narrative */}
            <StageContentPane
              currentStage={effectiveStage}
              sseEvents={sseState.events}
              demoStatus={demoStatus}
              analysisResult={analysisResult}
              pendingApprovals={pendingApprovals}
              analyzing={analyzing}
              onAnalyze={handleAnalyze}
              onReset={handleReset}
              onViewFullTrace={handleViewFullTrace}
              selectedApprovalId={selectedApprovalId}
              onReturnToCopilot={handleReturnToCopilot}
            />
          </>
        )}

        {scenarioActive && mode === 'reliability' && (
          <>
            <ScenarioHeader
              displayName={displayName}
              elapsedSeconds={elapsedSeconds}
              onReset={handleReset}
              onPause={handlePause}
              isPaused={isPaused}
            />
            <ReliabilityPanel sseEvents={sseState.events} runtime={runtime} />
          </>
        )}

        {/* Expert overlay */}
        {expertMode && (
          <ExpertOverlay
            runtime={runtime}
            demoStatus={demoStatus}
            sseEvents={sseState.events}
            defaultTab={expertDefaultTab}
            analysisResult={analysisResult}
            pendingApprovals={pendingApprovals}
          />
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
        {(() => {
          const unresolvedUnknown = sseState.events.some(e => e.category === 'RECONCILIATION_REQUIRED') &&
            !sseState.events.some(e => e.category === 'CONFIRMED_EXECUTED' || e.category === 'CONFIRMED_NOT_EXECUTED' || e.category === 'INDETERMINATE');
          return unresolvedUnknown ? (
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#D29922' }}>
              ! Review required
            </Typography>
          ) : (
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#3FB950' }}>
              ✓ All invariants hold
            </Typography>
          );
        })()}
        {scenarioActive && (
          <>
            <Box sx={{ width: '1px', height: 10, background: '#21262D' }} />
            <SSEStatusChip connected={sseState.connected} error={sseState.error} />
          </>
        )}
        <Box sx={{ flexGrow: 1 }} />
        <Typography sx={{
          fontFamily: 'monospace', fontSize: '0.62rem', color: '#484F58',
          cursor: 'pointer', '&:hover': { color: '#8B949E' },
        }}>
          Details ›
        </Typography>
      </Box>

      {/* ── Phase 15B: Copilot ASK drawer ───────────────────────────────────── */}
      {copilotOpen && scenarioActive && (
        <CopilotDrawer
          warehouseId={WAREHOUSE_ID}
          scenarioName={demoStatus?.scenario?.name ?? ''}
          onClose={() => setCopilotOpen(false)}
          onReviewApproval={handleReviewApproval}
          conversationId={conversation.conversationId}
          setConversationId={conversation.setConversationId}
          turns={conversation.turns}
          setTurns={conversation.setTurns}
          conversationError={conversation.conversationError}
          setConversationError={conversation.setConversationError}
        />
      )}
    </Box>
  );
}
