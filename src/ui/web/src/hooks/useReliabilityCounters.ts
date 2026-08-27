import { useMemo } from 'react';
import { SSEEvent } from './useDemoSSE';

export interface SafetyCounters {
  unauthorized_writes: number;
  duplicate_writes: number;
  false_successes: number;
  unknown_executions: number;
  reconciled: number;
  stale_blocks: number;
  drift_blocks: number;
}

// Batch 6 validated baseline — all golden invariants pass under 13 fault profiles.
// These are the expected values from artifacts/reliability/summary.json.
export const BATCH6_BASELINE: SafetyCounters = {
  unauthorized_writes: 0,
  duplicate_writes: 0,
  false_successes: 0,
  unknown_executions: 1,   // F06 ambiguous write (correctly classified UNKNOWN, not FAILED)
  reconciled: 1,            // F06 reconciled to CONFIRMED_EXECUTED
  stale_blocks: 1,          // F09 stale decision correctly blocked
  drift_blocks: 1,          // F10 state drift correctly blocked
};

export function useReliabilityCounters(events: SSEEvent[]): SafetyCounters {
  return useMemo(() => {
    const counters: SafetyCounters = {
      unauthorized_writes: 0,
      duplicate_writes: 0,
      false_successes: 0,
      unknown_executions: 0,
      reconciled: 0,
      stale_blocks: 0,
      drift_blocks: 0,
    };

    for (const ev of events) {
      const cat = ev.category?.toUpperCase();
      const msg = ev.message?.toLowerCase() ?? '';

      if (cat === 'FAULT' || cat === 'FAULT_INJECTED') {
        if (msg.includes('unauthorized')) counters.unauthorized_writes++;
        if (msg.includes('duplicate')) counters.duplicate_writes++;
        if (msg.includes('false_success') || msg.includes('false success')) counters.false_successes++;
      }

      if (cat === 'EXECUTE' || cat === 'SAFETY') {
        if (msg.includes('unknown')) counters.unknown_executions++;
        if (msg.includes('stale') || msg.includes('expired')) counters.stale_blocks++;
        if (msg.includes('drift') || msg.includes('conflict')) counters.drift_blocks++;
      }

      if (cat === 'RECONCILE' || cat === 'CONFIRMED_EXECUTED' || cat === 'CONFIRMED_NOT_EXECUTED') {
        if (
          msg.includes('confirmed') ||
          cat === 'CONFIRMED_EXECUTED' ||
          cat === 'CONFIRMED_NOT_EXECUTED'
        ) {
          counters.reconciled++;
        }
      }
    }

    return counters;
  }, [events]);
}
