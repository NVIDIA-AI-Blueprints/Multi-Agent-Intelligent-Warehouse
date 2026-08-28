/**
 * FaultInjectionPanel — inject fault events and trigger reconciliation.
 *
 * Inject buttons map fault scenarios to available /demo/inject event types.
 * Reconcile button calls /demo/reconcile for any pending UNKNOWN execution.
 *
 * Available inject types (from InjectEventType):
 *   equipment_fault, equipment_restore, low_stock, worker_absence,
 *   worker_return, task_deadline, wave_delay
 *
 * F06/F10 use equipment_fault as proxy (backend fault injection logic handles ambiguous write).
 * F12/F01 have no direct inject — operator notes walk through manual steps.
 */

import React, { useState } from 'react';
import { Box, Typography, CircularProgress } from '@mui/material';
import { demoAPI } from '../../../services/demoAPI';
import { SSEEvent, parseEventDetail } from '../../../hooks/useDemoSSE';

interface Props {
  scenarioId: string | null;
  sseEvents: SSEEvent[];
}

interface InjectionConfig {
  label: string;
  description: string;
  action: () => Promise<void>;
  color?: string;
  testId: string;
}

function ActionButton({
  label,
  description,
  onClick,
  disabled,
  loading,
  color,
  testId,
}: {
  label: string;
  description: string;
  onClick: () => void;
  disabled?: boolean;
  loading?: boolean;
  color?: string;
  testId: string;
}) {
  const borderColor = color ?? '#30363D';
  return (
    <Box
      component="button"
      onClick={onClick}
      disabled={disabled || loading}
      data-testid={testId}
      sx={{
        display: 'block',
        width: '100%',
        textAlign: 'left',
        background: disabled ? '#0D1117' : '#161B22',
        border: `1px solid ${disabled ? '#21262D' : borderColor}`,
        borderRadius: '4px',
        px: 1.5, py: 1,
        cursor: disabled ? 'default' : 'pointer',
        opacity: disabled ? 0.45 : 1,
        '&:hover:not(:disabled)': { borderColor: '#388BFD', background: '#0d1930' },
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        {loading && <CircularProgress size={10} sx={{ color: '#58A6FF', flexShrink: 0 }} />}
        <Typography sx={{
          fontFamily: 'monospace', fontSize: '0.7rem', fontWeight: 700,
          color: disabled ? '#484F58' : (color ?? '#C9D1D9'),
          letterSpacing: '0.04em',
        }}>
          {label}
        </Typography>
      </Box>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#484F58', mt: '2px' }}>
        {description}
      </Typography>
    </Box>
  );
}

export default function FaultInjectionPanel({ scenarioId, sseEvents }: Props) {
  const [injectLoading, setInjectLoading] = useState(false);
  const [reconcileLoading, setReconcileLoading] = useState(false);
  const [lastResult, setLastResult] = useState<string | null>(null);

  // Find an UNKNOWN execution pending reconciliation from SSE
  const unknownEvent = sseEvents.find(e => e.category === 'RECONCILIATION_REQUIRED');
  const unknownDetail = unknownEvent ? parseEventDetail(unknownEvent) : null;
  const executionId = unknownDetail?.execution_id ?? unknownEvent?.execution_id ?? null;
  const domain = unknownDetail?.domain ?? unknownEvent?.domain ?? 'equipment';

  const handleInject = async (fn: () => Promise<any>, label: string) => {
    if (injectLoading) return;
    setInjectLoading(true);
    setLastResult(null);
    try {
      await fn();
      setLastResult(`${label} → injected`);
    } catch (e: any) {
      setLastResult(`Error: ${e?.response?.data?.detail ?? e?.message ?? 'unknown'}`);
    } finally {
      setInjectLoading(false);
    }
  };

  const handleReconcile = async () => {
    if (!executionId || reconcileLoading) return;
    setReconcileLoading(true);
    setLastResult(null);
    try {
      await demoAPI.reconcile(executionId, domain);
      setLastResult(`Reconcile dispatched for ${executionId}`);
    } catch (e: any) {
      setLastResult(`Reconcile error: ${e?.response?.data?.detail ?? e?.message ?? 'unknown'}`);
    } finally {
      setReconcileLoading(false);
    }
  };

  const scenarioConfigs: Record<string, InjectionConfig[]> = {
    F06: [
      {
        label: 'INJECT FAULT',
        description: 'Trigger equipment fault → drives ambiguous write path',
        action: () => demoAPI.inject('equipment_fault', { asset_id: 'AGV-01', simulate_ambiguous_write: true }),
        color: '#D29922',
        testId: 'inject-fault-F06',
      },
    ],
    F07: [
      {
        label: 'TRIGGER DUPLICATE APPROVE',
        description: 'Rapid-fire 3 approvals for the same pending_id via separate calls',
        action: async () => {
          const pending = await demoAPI.getStatus().then(s => s.pending_approvals?.[0]);
          if (!pending) throw new Error('No pending approval — run OBSERVE first');
          await Promise.allSettled([
            demoAPI.approvePending(pending.pending_id, 'op-1'),
            demoAPI.approvePending(pending.pending_id, 'op-2'),
            demoAPI.approvePending(pending.pending_id, 'op-3'),
          ]);
        },
        color: '#D29922',
        testId: 'inject-fault-F07',
      },
    ],
    F10: [
      {
        label: 'INJECT STATE DRIFT',
        description: 'Inject equipment fault then restore → state changes during proposal window',
        action: async () => {
          await demoAPI.inject('equipment_fault', { asset_id: 'AGV-01' });
          await demoAPI.inject('equipment_restore', { asset_id: 'AGV-01' });
        },
        color: '#D29922',
        testId: 'inject-fault-F10',
      },
    ],
    F12: [
      {
        label: 'INJECT WORKER ABSENCE',
        description: 'Simulate labor domain stress → worker_absence burst',
        action: () => demoAPI.inject('worker_absence', { worker_id: 'w-003' }),
        color: '#D29922',
        testId: 'inject-fault-F12',
      },
    ],
    F01: [
      {
        label: 'INJECT TASK DEADLINE',
        description: 'Force urgent task — NIM timeout path triggered at capacity',
        action: () => demoAPI.inject('task_deadline', { task_id: 'task-001', deadline: '2026-08-23T10:00:00Z' }),
        color: '#D29922',
        testId: 'inject-fault-F01',
      },
    ],
  };

  const actions = scenarioId ? (scenarioConfigs[scenarioId] ?? []) : [];
  const canReconcile = !!executionId;

  return (
    <Box data-testid="fault-injection-panel" sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <Typography sx={{
        fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58',
        letterSpacing: '0.12em', textTransform: 'uppercase', mb: 0.5,
      }}>
        Fault controls
      </Typography>

      {scenarioId ? (
        <>
          {actions.map(cfg => (
            <ActionButton
              key={cfg.testId}
              label={cfg.label}
              description={cfg.description}
              onClick={() => handleInject(cfg.action, cfg.label)}
              disabled={false}
              loading={injectLoading}
              color={cfg.color}
              testId={cfg.testId}
            />
          ))}

          {/* Reconcile button — always shown; disabled until RECONCILIATION_REQUIRED fires */}
          <ActionButton
            label="RECONCILE NOW"
            description={canReconcile
              ? `Resolve UNKNOWN for execution ${executionId}`
              : 'Waiting for RECONCILIATION_REQUIRED event...'}
            onClick={handleReconcile}
            disabled={!canReconcile}
            loading={reconcileLoading}
            color="#3FB950"
            testId="reconcile-button"
          />
        </>
      ) : (
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58' }}>
          Select a scenario to see fault controls.
        </Typography>
      )}

      {lastResult && (
        <Box data-testid="inject-result" sx={{ mt: 0.5 }}>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#8B949E' }}>
            {lastResult}
          </Typography>
        </Box>
      )}
    </Box>
  );
}
