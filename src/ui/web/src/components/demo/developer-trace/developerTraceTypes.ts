/**
 * developerTraceTypes.ts — Types for Phase 13E Developer Trace.
 *
 * Three distinct clocks, never mixed:
 *   - Trace wall clock: from SSE ts, relative to first event
 *   - Component latency: from assessment.latency_ms, timing.* fields
 *   - Simulation time: from SSE sim_time_seconds or post_kpis.sim_time_seconds
 */

import { NodeSource } from '../decision-graph/graphTypes';
import { ExplanationFocus } from '../decision-explanation/explanationTypes';

export type TraceTimingSource = 'LIVE' | 'DERIVED' | 'NOT_INSTRUMENTED';

export type DeveloperTraceStatus =
  | 'IN_PROGRESS'
  | 'WAITING_FOR_APPROVAL'
  | 'EXECUTING'
  | 'RECONCILIATION_REQUIRED'
  | 'COMPLETE'
  | 'FAILED'
  | 'UNKNOWN';

export type TraceEventCategory =
  | 'OBSERVE'
  | 'STATE'
  | 'AGENT'
  | 'MODEL_ROUTING'
  | 'MODEL'
  | 'SKILL'
  | 'ASSESSMENT'
  | 'RECOMMENDATION'
  | 'PROPOSAL'
  | 'DECISION'
  | 'APPROVAL_WAIT'
  | 'APPROVAL'
  | 'EXECUTION_BOUNDARY'
  | 'EXECUTION'
  | 'MCP'
  | 'PROVIDER'
  | 'RECONCILIATION'
  | 'OUTCOME'
  | 'ERROR';

export type TraceClockKind = 'TRACE' | 'COMPONENT' | 'SIMULATION';

export interface TraceClock {
  kind: TraceClockKind;
  /** "TRACE TIME" | "MODEL LATENCY" | "SIMULATION TIME" */
  label: string;
  /** "+3.72s" | "3.61s" | "00:05:00" */
  display: string;
}

export interface DeveloperTraceEvent {
  id: string;
  category: TraceEventCategory;
  label: string;
  detail?: string;
  actor?: string;
  actorSource: NodeSource;

  // Timing — may be absent
  wallTs?: string;         // ISO-8601 UTC from SSE ts
  relativeMs?: number;     // ms since first event (only if timingSource === 'LIVE')
  timingSource: TraceTimingSource;
  timingNote?: string;     // shown when NOT_INSTRUMENTED

  // Clock display (only set when available — NEVER mixed)
  traceClock?: TraceClock;       // trace wall clock relative timing
  componentLatency?: TraceClock; // measured component latency
  simulationClock?: TraceClock;  // simulation time

  // Artifact IDs for lineage
  artifactId?: string;
  metadata?: Record<string, string | number | null | undefined>;

  // Click-through to 13D explanation
  explanationFocus?: ExplanationFocus;

  // Special rendering
  isGap?: boolean;         // for "─── WAITING FOR OPERATOR ───" separator
  isExecutionBoundary?: boolean;
}

export interface TraceArtifactLineage {
  snapshotId?: string | null;
  proposalIds: Array<{ proposalId: string; action?: string | null }>;
  decisionIds: Array<{ decisionId: string; proposalId?: string | null; outcome?: string | null }>;
  approvalIds: Array<{ approvalId: string; decisionId?: string | null; state: string }>;
  executionIds: Array<{ executionId: string; proposalId?: string | null; status?: string | null }>;
}

export interface TraceTiming {
  label: string;
  value: string;         // formatted display string
  kind: TraceClockKind;
  available: boolean;
  unavailableReason?: string;  // shown when !available
}

export interface DeveloperTrace {
  traceId?: string | null;
  warehouseId?: string | null;
  scenarioName?: string | null;
  status: DeveloperTraceStatus;
  firstEventWallTs?: string;   // for relative time calculation
  events: DeveloperTraceEvent[];
  artifacts: TraceArtifactLineage;
  timings: TraceTiming[];
  // Known limitation note for UI
  scenarioRunIdNote: string;
}
