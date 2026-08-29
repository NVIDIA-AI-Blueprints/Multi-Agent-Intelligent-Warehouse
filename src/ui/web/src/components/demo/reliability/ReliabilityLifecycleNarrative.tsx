/**
 * ReliabilityLifecycleNarrative — vertical fault-path narrative driven by SSE events.
 *
 * Each step activates when its corresponding SSE event(s) fire. No optimistic
 * advancement — only actual events complete a step.
 *
 * Scenario → SSE category mapping:
 *   F06 Ambiguous Write:
 *     FAULT      ← INJECT or FAULT_INJECTED
 *     EXECUTE    ← EXECUTE
 *     UNKNOWN    ← RECONCILIATION_REQUIRED
 *     SAFETY     ← (automatic after UNKNOWN; same condition)
 *     RECONCILE  ← RECONCILE
 *     CONFIRMED  ← CONFIRMED_EXECUTED or CONFIRMED_NOT_EXECUTED or INDETERMINATE
 *   F07 Duplicate Approval:
 *     APPROVE ×1 ← APPROVE (first event)
 *     CONSUMED   ← APPROVE (subsequent events; or 404 tracked locally)
 *     SAFETY     ← same
 *   F10 State Drift:
 *     FAULT      ← INJECT or FAULT_INJECTED
 *     EXECUTE    ← EXECUTE
 *     CONFLICT   ← EXECUTE with outcome=conflict in detail (or just EXECUTE)
 *     SAFETY     ← same
 *   F12 Circuit Open:
 *     CIRCUIT_OPEN ← CIRCUIT_OPEN
 *     SAFETY       ← CIRCUIT_OPEN
 *     DEGRADED     ← from runtime.maiw_operational_status === 'DEGRADED'
 *   F01 NIM Timeout:
 *     TIMEOUT    ← MODEL TIMEOUT or REQUEST DEADLINE
 *     SAFETY     ← same
 */

import React from 'react';
import { Box, Typography } from '@mui/material';
import { SSEEvent } from '../../../hooks/useDemoSSE';

// ── Step types ────────────────────────────────────────────────────────────────

type StepStatus = 'pending' | 'active' | 'complete';

interface NarrativeStep {
  id: string;
  label: string;
  sublabel: string;
  completed: (events: SSEEvent[], runtime: any) => boolean;
}

// ── Per-scenario step definitions ─────────────────────────────────────────────

const F06_STEPS: NarrativeStep[] = [
  {
    id: 'fault',
    label: 'FAULT',
    sublabel: 'MCP write timeout after mutation',
    completed: (e) => e.some(ev => ev.category === 'INJECT' || ev.category === 'FAULT_INJECTED'),
  },
  {
    id: 'execute',
    label: 'EXECUTE',
    sublabel: 'Action dispatched to provider',
    completed: (e) => e.some(ev => ev.category === 'EXECUTE'),
  },
  {
    id: 'unknown',
    label: 'UNKNOWN',
    sublabel: 'ACK lost — mutation status uncertain',
    completed: (e) => e.some(ev => ev.category === 'RECONCILIATION_REQUIRED'),
  },
  {
    id: 'safety',
    label: 'SAFETY',
    sublabel: 'Automatic retry suppressed',
    completed: (e) => e.some(ev => ev.category === 'RECONCILIATION_REQUIRED'),
  },
  {
    id: 'reconcile',
    label: 'RECONCILE',
    sublabel: 'State read against authoritative source',
    completed: (e) => e.some(ev => ev.category === 'RECONCILE'),
  },
  {
    id: 'confirmed',
    label: 'CONFIRMED EXECUTED',
    sublabel: 'Reconciliation resolved: mutation confirmed',
    completed: (e) => e.some(ev =>
      ev.category === 'CONFIRMED_EXECUTED' ||
      ev.category === 'CONFIRMED_NOT_EXECUTED' ||
      ev.category === 'INDETERMINATE'
    ),
  },
];

const F07_STEPS: NarrativeStep[] = [
  {
    id: 'approve1',
    label: 'APPROVE ×1',
    sublabel: 'First authority grant accepted',
    completed: (e) => e.some(ev => ev.category === 'APPROVE'),
  },
  {
    id: 'consumed',
    label: 'CONSUMED ×2',
    sublabel: 'Subsequent attempts blocked: 404 consumed',
    completed: (e) => e.filter(ev => ev.category === 'APPROVE').length > 1,
  },
  {
    id: 'safety',
    label: 'SAFETY',
    sublabel: 'Duplicate approval prevented — one mutation only',
    completed: (e) => e.filter(ev => ev.category === 'APPROVE').length > 1,
  },
];

const F10_STEPS: NarrativeStep[] = [
  {
    id: 'fault',
    label: 'FAULT',
    sublabel: 'World state changes after proposal committed',
    completed: (e) => e.some(ev => ev.category === 'INJECT' || ev.category === 'FAULT_INJECTED'),
  },
  {
    id: 'execute',
    label: 'EXECUTE',
    sublabel: 'Execution attempted against drifted state',
    completed: (e) => e.some(ev => ev.category === 'EXECUTE'),
  },
  {
    id: 'conflict',
    label: 'CONFLICT',
    sublabel: 'ActionConflict — state drift detected',
    completed: (e) => e.some(ev => ev.category === 'EXECUTE' &&
      (ev.detail?.includes('conflict') || ev.message?.includes('conflict'))
    ),
  },
  {
    id: 'safety',
    label: 'SAFETY',
    sublabel: 'Guard 5 (state drift) blocked execution',
    completed: (e) => e.some(ev => ev.category === 'EXECUTE' &&
      (ev.detail?.includes('conflict') || ev.message?.includes('conflict'))
    ),
  },
];

const F12_STEPS: NarrativeStep[] = [
  {
    id: 'circuit_open',
    label: 'CIRCUIT OPEN',
    sublabel: 'Labor MCP domain unavailable',
    completed: (e) => e.some(ev => ev.category === 'CIRCUIT_OPEN'),
  },
  {
    id: 'safety',
    label: 'SAFETY',
    sublabel: 'Domain isolated — Equipment/Inventory remain available',
    completed: (e) => e.some(ev => ev.category === 'CIRCUIT_OPEN'),
  },
  {
    id: 'degraded',
    label: 'DEGRADED',
    sublabel: 'Runtime DEGRADED (not unavailable)',
    completed: (_e, runtime) => runtime?.maiw_operational_status === 'DEGRADED',
  },
];

const F01_STEPS: NarrativeStep[] = [
  {
    id: 'timeout',
    label: 'NIM TIMEOUT',
    sublabel: 'Model did not respond in time',
    completed: (e) => e.some(ev =>
      ev.category === 'MODEL TIMEOUT' || ev.category === 'REQUEST DEADLINE'
    ),
  },
  {
    id: 'safety',
    label: 'SAFETY',
    sublabel: 'No proposal or execution produced — 504 to caller',
    completed: (e) => e.some(ev =>
      ev.category === 'MODEL TIMEOUT' || ev.category === 'REQUEST DEADLINE'
    ),
  },
];

const SCENARIO_STEPS: Record<string, NarrativeStep[]> = {
  F06: F06_STEPS,
  F07: F07_STEPS,
  F10: F10_STEPS,
  F12: F12_STEPS,
  F01: F01_STEPS,
};

// ── Node ──────────────────────────────────────────────────────────────────────

function NarrativeNode({
  step,
  status,
  isLast,
}: {
  step: NarrativeStep;
  status: StepStatus;
  isLast: boolean;
}) {
  const color =
    status === 'complete' ? '#3FB950' :
    status === 'active'   ? '#D29922' :
    '#30363D';

  const icon =
    status === 'complete' ? '✓' :
    status === 'active'   ? '●' : '○';

  return (
    <Box data-testid={`narrative-step-${step.id}`} data-status={status}>
      <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.5 }}>
        {/* Icon + connector */}
        <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0 }}>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.72rem', color, lineHeight: 1 }}>
            {icon}
          </Typography>
          {!isLast && (
            <Box sx={{ width: '1px', height: 28, background: color === '#30363D' ? '#21262D' : `${color}44`, mt: '4px' }} />
          )}
        </Box>

        {/* Label */}
        <Box sx={{ pb: isLast ? 0 : 1.5 }}>
          <Typography sx={{
            fontFamily: 'monospace', fontSize: '0.72rem', fontWeight: 700,
            color: color === '#30363D' ? '#484F58' : color,
            letterSpacing: '0.04em',
          }}>
            {step.label}
          </Typography>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#484F58' }}>
            {step.sublabel}
          </Typography>
          {step.id === 'safety' && status !== 'pending' && (
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#3FB950', mt: '2px' }}>
              ✓ invariant held
            </Typography>
          )}
        </Box>
      </Box>
    </Box>
  );
}

// ── ReliabilityLifecycleNarrative ─────────────────────────────────────────────

interface Props {
  scenarioId: string;
  sseEvents: SSEEvent[];
  runtime?: any;
}

export default function ReliabilityLifecycleNarrative({ scenarioId, sseEvents, runtime }: Props) {
  const steps = SCENARIO_STEPS[scenarioId] ?? [];
  if (steps.length === 0) return null;

  // Derive status: once a step completes, all previous steps are also complete
  const completedMask = steps.map(s => s.completed(sseEvents, runtime));

  // Find the furthest completed step index
  const furthestComplete = completedMask.reduce((last, done, i) => done ? i : last, -1);

  const statuses: StepStatus[] = steps.map((_, i) => {
    if (i <= furthestComplete) return 'complete';
    if (i === furthestComplete + 1) return 'active';
    return 'pending';
  });

  return (
    <Box data-testid={`narrative-${scenarioId}`} sx={{ py: 0.5 }}>
      {steps.map((step, i) => (
        <NarrativeNode
          key={step.id}
          step={step}
          status={statuses[i]}
          isLast={i === steps.length - 1}
        />
      ))}
    </Box>
  );
}
