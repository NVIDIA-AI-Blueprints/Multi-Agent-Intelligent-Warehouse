import { useMemo } from 'react';
import { SSEEvent } from './useDemoSSE';
import { PendingApproval } from '../services/demoAPI';

export const STAGE_ORDER = [
  'OBSERVE', 'REASON', 'PROPOSE', 'DECIDE', 'APPROVE', 'EXECUTE', 'OUTCOME',
] as const;

export type RailStage = typeof STAGE_ORDER[number];

// SSE category → rail stage.
// SKILL collapses under REASON (never becomes its own rail node).
// OBSERVE_OUTCOME maps to OUTCOME.
export const SSE_TO_RAIL: Readonly<Record<string, RailStage | undefined>> = {
  OBSERVE:         'OBSERVE',
  REASON:          'REASON',
  SKILL:           'REASON',
  PROPOSE:         'PROPOSE',
  DECIDE:          'DECIDE',
  APPROVE:         'APPROVE',
  EXECUTE:         'EXECUTE',
  OBSERVE_OUTCOME: 'OUTCOME',
};

export interface RailState {
  currentStage: RailStage;
  completedStages: ReadonlySet<RailStage>;
  waitingForApproval: boolean;
}

/**
 * Derive the canonical rail state from the SSE event buffer.
 *
 * Strategy: locate the most recent OBSERVE event — that is the anchor for the
 * current pipeline run. All events before that anchor (i.e. at lower array
 * indices in the newest-first buffer) belong to the current run. The furthest
 * rail stage seen in those events is the current stage.
 *
 * A new OBSERVE event resets the current-run window automatically, so stale
 * events from a previous run are ignored without requiring manual cleanup.
 *
 * This is a pure function — no side-effects, easy to unit-test.
 */
export function deriveRailState(
  sseEvents: SSEEvent[],
  pendingApprovals: PendingApproval[],
): RailState {
  // sseEvents is newest-first. Find the most recent OBSERVE event.
  const observeIdx = sseEvents.findIndex(ev => ev.category === 'OBSERVE');

  // Current-run window: events from index 0 up to (and including) the OBSERVE anchor.
  // If no OBSERVE yet, window is empty → initial state.
  const currentRunEvents: SSEEvent[] =
    observeIdx >= 0 ? sseEvents.slice(0, observeIdx + 1) : [];

  if (currentRunEvents.length === 0) {
    // No pipeline run has started yet — OBSERVE is the pending current stage.
    return {
      currentStage: 'OBSERVE',
      completedStages: new Set<RailStage>(),
      waitingForApproval: false,
    };
  }

  // Collect all rail stages seen in the current run.
  const seen = new Set<RailStage>();
  for (const ev of currentRunEvents) {
    const rs = SSE_TO_RAIL[ev.category];
    if (rs) seen.add(rs);
  }

  // The furthest stage (highest index in STAGE_ORDER) is the current stage.
  let furthestIdx = 0;
  for (let i = STAGE_ORDER.length - 1; i >= 0; i--) {
    if (seen.has(STAGE_ORDER[i])) {
      furthestIdx = i;
      break;
    }
  }

  const rawCurrentStage = STAGE_ORDER[furthestIdx];

  // APPROVE waiting: DECIDE is the furthest stage AND there are pending approvals.
  // The pipeline has paused for human input — current stage advances to APPROVE.
  const waitingForApproval =
    rawCurrentStage === 'DECIDE' && pendingApprovals.length > 0;

  const currentStage: RailStage = waitingForApproval ? 'APPROVE' : rawCurrentStage;
  const currentIdx = STAGE_ORDER.indexOf(currentStage);

  // All stages before the current stage are complete.
  const completedStages = new Set(STAGE_ORDER.slice(0, currentIdx)) as Set<RailStage>;

  return { currentStage, completedStages, waitingForApproval };
}

/** React hook wrapper — memoises the pure derivation. */
export function useDemoLifecycle(
  sseEvents: SSEEvent[],
  pendingApprovals: PendingApproval[],
): RailState {
  return useMemo(
    () => deriveRailState(sseEvents, pendingApprovals),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sseEvents, pendingApprovals],
  );
}
