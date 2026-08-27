/**
 * ExecuteStage — shows what the ActionExecutor dispatched and what outcome was recorded.
 *
 * Data priority:
 *   1. analysisResult.lifecycle phase=EXECUTE records  (canonical backend truth)
 *   2. analysisResult.proposal_results               (capability / proposal context)
 *   3. SSE EXECUTE events                            (live action feed fallback)
 *
 * Six canonical outcomes (ExecutionOutcome enum, lowercase wire values):
 *   executed | no_op | deferred | conflict | unknown | failed
 *
 * UNKNOWN surfaces the reconciliation notice — do not collapse into "error".
 */

import React from 'react';
import { Box, Typography } from '@mui/material';
import { LifecycleRecord } from '../../../services/demoAPI';
import {
  SectionHeader,
  StageSection,
  MonoText,
  IdText,
  StageContentPaneProps,
  runWindowEvents,
} from '../StageContentPane';

// ── Outcome display ───────────────────────────────────────────────────────────

type CanonicalOutcome = 'executed' | 'no_op' | 'deferred' | 'conflict' | 'unknown' | 'failed';

const OUTCOME_COLOR: Record<string, string> = {
  executed:  '#3FB950',
  no_op:     '#6E7681',
  deferred:  '#D29922',
  conflict:  '#F0883E',
  unknown:   '#D29922',
  failed:    '#F85149',
};

const OUTCOME_LABEL: Record<string, string> = {
  executed:  'EXECUTED',
  no_op:     'NO_OP',
  deferred:  'DEFERRED',
  conflict:  'CONFLICT',
  unknown:   'UNKNOWN',
  failed:    'FAILED',
};

function canonicalize(status: string | undefined): string {
  if (!status) return 'unknown';
  const s = status.toLowerCase();
  if (s === 'approved_no_executor' || s === 'deferred') return 'deferred';
  if (s === 'execution_error' || s === 'error') return 'failed';
  const known: string[] = ['executed', 'no_op', 'conflict', 'unknown', 'failed'];
  return known.includes(s) ? s : 'unknown';
}

function OutcomeBadge({ outcome }: { outcome: string }) {
  const color = OUTCOME_COLOR[outcome] ?? '#484F58';
  const label = OUTCOME_LABEL[outcome] ?? outcome.toUpperCase();
  return (
    <Box
      component="span"
      data-testid={`outcome-badge-${outcome}`}
      sx={{
        fontFamily: 'monospace',
        fontSize: '0.62rem',
        fontWeight: 700,
        color,
        border: `1px solid ${color}44`,
        borderRadius: '3px',
        px: '5px',
        py: '1px',
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
      }}
    >
      {label}
    </Box>
  );
}

// ── UNKNOWN reconciliation notice ─────────────────────────────────────────────

function ReconciliationNotice() {
  return (
    <Box
      data-testid="reconciliation-notice"
      sx={{
        mt: 1,
        background: '#1A1A0A',
        border: '1px solid #D2992244',
        borderRadius: '4px',
        px: 1.5,
        py: 1,
        display: 'flex',
        flexDirection: 'column',
        gap: 0.35,
      }}
    >
      <Typography sx={{
        fontFamily: 'monospace', fontSize: '0.6rem', fontWeight: 700,
        color: '#D29922', letterSpacing: '0.1em', textTransform: 'uppercase',
      }}>
        EXECUTION OUTCOME — UNKNOWN
      </Typography>
      <MonoText color="#8B949E" size="0.68rem">
        The warehouse may have accepted this action.
      </MonoText>
      <MonoText color="#8B949E" size="0.68rem">
        Automatic retry suppressed.
      </MonoText>
      <MonoText color="#8B949E" size="0.68rem">
        Reconciliation required.
      </MonoText>
    </Box>
  );
}

// ── Execution card (one per lifecycle EXECUTE record) ─────────────────────────

interface ExecCardProps {
  index: number;
  outcome: string;
  executionId: string | undefined;
  capability: string | undefined;
  action: string | undefined;
  provider: string | undefined;
}

function ExecCard({ index, outcome, executionId, capability, action, provider }: ExecCardProps) {
  return (
    <Box
      data-testid={`execution-card-${index}`}
      sx={{
        background: '#161B22',
        border: '1px solid #21262D',
        borderRadius: '5px',
        px: 1.75,
        py: 1.25,
        display: 'flex',
        flexDirection: 'column',
        gap: 0.75,
      }}
    >
      {/* Capability + outcome */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
        {capability && (
          <MonoText weight={700}>{capability}</MonoText>
        )}
        {action && capability !== action && (
          <MonoText color="#484F58" size="0.68rem">{action}</MonoText>
        )}
        <OutcomeBadge outcome={outcome} />
      </Box>

      {/* IDs */}
      <Box sx={{ display: 'flex', gap: 2.5, flexWrap: 'wrap', alignItems: 'center' }}>
        {executionId && (
          <IdText label="exec_id" value={executionId} />
        )}
        {provider && (
          <IdText label="provider" value={provider} />
        )}
      </Box>

      {/* UNKNOWN notice */}
      {outcome === 'unknown' && <ReconciliationNotice />}
    </Box>
  );
}

// ── SSE-based fallback row ─────────────────────────────────────────────────────

function SSEExecRow({ message, detail }: { message: string; detail: string | null }) {
  return (
    <Box sx={{ display: 'flex', gap: 1, alignItems: 'baseline' }}>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#3FB950', flexShrink: 0 }}>
        ↳
      </Typography>
      <MonoText color="#8B949E" size="0.68rem">{message}</MonoText>
      {detail && (
        <MonoText color="#484F58" size="0.62rem">{detail}</MonoText>
      )}
    </Box>
  );
}

// ── ExecuteStage ──────────────────────────────────────────────────────────────

export default function ExecuteStage({ sseEvents, analysisResult }: StageContentPaneProps) {
  // Primary: lifecycle EXECUTE records
  const lifecycleExecutions: LifecycleRecord[] =
    (analysisResult?.lifecycle ?? []).filter(r => r.phase === 'EXECUTE');

  // Enrichment: proposal_results keyed by index for capability lookup
  const proposalResults = analysisResult?.proposal_results ?? [];

  // Fallback: SSE EXECUTE events (newest-first → reversed to chronological)
  const sseExecEvents = runWindowEvents(sseEvents, ['EXECUTE']);

  const hasLifecycleData = lifecycleExecutions.length > 0;
  const hasSseData = sseExecEvents.length > 0;
  const hasAnyData = hasLifecycleData || hasSseData;

  return (
    <Box data-testid="execute-stage">
      {/* Stage header */}
      <StageSection>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Typography sx={{
            fontFamily: 'monospace', fontSize: '0.72rem', fontWeight: 700,
            color: '#3FB950', textTransform: 'uppercase', letterSpacing: '0.06em',
          }}>
            Execute
          </Typography>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58' }}>
            ActionExecutor → MCP capability → provider/backend → ActionExecutionResult
          </Typography>
        </Box>
      </StageSection>

      {/* Execution result */}
      <StageSection>
        <SectionHeader>Execution Result</SectionHeader>

        {hasLifecycleData ? (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            {lifecycleExecutions.map((rec, i) => {
              const outcome = canonicalize(rec.status as string);
              const pr = proposalResults[rec.index ?? i] ?? proposalResults[i];
              return (
                <ExecCard
                  key={i}
                  index={i}
                  outcome={outcome}
                  executionId={rec.execution_id as string | undefined}
                  capability={(pr?.capability ?? rec.capability) as string | undefined}
                  action={rec.action as string | undefined}
                  provider={rec.provider as string | undefined}
                />
              );
            })}
          </Box>
        ) : hasSseData ? (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
            {sseExecEvents.map((ev, i) => (
              <SSEExecRow key={i} message={ev.message} detail={ev.detail} />
            ))}
          </Box>
        ) : (
          <Box data-testid="execute-waiting">
            <MonoText color="#484F58" size="0.65rem">
              Waiting for execution dispatch…
            </MonoText>
          </Box>
        )}
      </StageSection>

      {/* Proposal-level summary when available and no lifecycle enrichment */}
      {!hasLifecycleData && proposalResults.length > 0 && (
        <StageSection last>
          <SectionHeader>Proposal Results</SectionHeader>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
            {proposalResults.map((pr, i) => (
              <Box key={i} sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                <MonoText color="#8B949E" size="0.68rem">{pr.capability}</MonoText>
                <OutcomeBadge outcome={canonicalize(pr.status)} />
                {pr.execution_id && (
                  <IdText label="exec_id" value={pr.execution_id} />
                )}
              </Box>
            ))}
          </Box>
        </StageSection>
      )}

      {!hasAnyData && proposalResults.length === 0 && (
        <StageSection last>
          <MonoText color="#484F58" size="0.65rem">
            No execution data yet — awaiting EXECUTE lifecycle record.
          </MonoText>
        </StageSection>
      )}
    </Box>
  );
}
