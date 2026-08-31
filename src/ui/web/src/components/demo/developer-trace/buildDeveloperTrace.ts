/**
 * buildDeveloperTrace.ts — Pure function that builds a DeveloperTrace from all
 * available demo state. No React, no side effects.
 *
 * KNOWN LIMITATION: scenario_run_id exists in the backend controller but is not
 * part of the public trace contract. Trace boundary is established from
 * trace_id + active demo state. This becomes relevant when multi-trace
 * scenarios are introduced (Copilot layer).
 *
 * SSE correlation strategy (Refinement 1):
 *   - LIVE: match uses at least one artifact ID found in SSE detail string
 *   - DERIVED: match by phase/category + index only (no artifact ID)
 *   - NOT_INSTRUMENTED: no SSE match found
 *
 * Three distinct clocks, never mixed (Refinement 3):
 *   - traceClock: from SSE ts relative to first event → "+3.72s" (TRACE TIME)
 *   - componentLatency: from assessment.latency_ms, timing.* → "3.61s" (MODEL LATENCY etc.)
 *   - simulationClock: from SSE sim_time_seconds → "00:05:00" (SIMULATION TIME)
 */

import { AnalysisResult, PendingApproval, DemoStatus } from '../../../services/demoAPI';
import { SSEEvent } from '../../../hooks/useDemoSSE';
import { DecisionGraph } from '../decision-graph/graphTypes';
import {
  DeveloperTrace,
  DeveloperTraceEvent,
  DeveloperTraceStatus,
  TraceArtifactLineage,
  TraceTiming,
  TraceTimingSource,
  TraceClock,
} from './developerTraceTypes';

// ── Public inputs ──────────────────────────────────────────────────────────────

export interface BuildDeveloperTraceParams {
  analysisResult: AnalysisResult | null;
  pendingApprovals: PendingApproval[];
  demoStatus: DemoStatus | null;
  sseEvents: SSEEvent[];
  graph: DecisionGraph | null;
}

// ── Time helpers ───────────────────────────────────────────────────────────────

function msFrom(base: string, ts: string): number {
  return new Date(ts).getTime() - new Date(base).getTime();
}

function formatRelative(ms: number): string {
  return `+${(ms / 1000).toFixed(2)}s`;
}

function formatSimTime(secs: number): string {
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = Math.floor(secs % 60);
  if (h > 0) {
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

// ── Detail string parser ───────────────────────────────────────────────────────

function parseDetailStr(detail: string | null | undefined): Record<string, string> {
  if (!detail) return {};
  const out: Record<string, string> = {};
  for (const token of detail.split(' ')) {
    const eq = token.indexOf('=');
    if (eq > 0) out[token.slice(0, eq)] = token.slice(eq + 1);
  }
  return out;
}

// ── SSE index builder ─────────────────────────────────────────────────────────

function buildSseIndex(sseEvents: SSEEvent[]): Map<string, SSEEvent[]> {
  const idx = new Map<string, SSEEvent[]>();
  // SSE events arrive newest-first in the buffer (useDemoSSE prepends), so reverse for chrono order
  const chrono = [...sseEvents].reverse();
  for (const ev of chrono) {
    const cat = (ev.category ?? '').toUpperCase();
    if (!idx.has(cat)) idx.set(cat, []);
    idx.get(cat)!.push(ev);
  }
  return idx;
}

function findSseMatch(
  sseByCategory: Map<string, SSEEvent[]>,
  category: string,
  index?: number,
  artifactId?: string,
): { ev: SSEEvent; source: TraceTimingSource } | null {
  const evs = sseByCategory.get(category.toUpperCase()) ?? [];
  if (evs.length === 0) return null;

  // Try artifact ID match first (LIVE)
  if (artifactId) {
    for (const ev of evs) {
      const parsed = parseDetailStr(ev.detail);
      const detailValues = Object.values(parsed);
      if (detailValues.some(v => v === artifactId || String(v).includes(artifactId))) {
        return { ev, source: 'LIVE' };
      }
      // Also check raw detail string
      if (ev.detail && ev.detail.includes(artifactId)) {
        return { ev, source: 'LIVE' };
      }
    }
  }

  // Index-based match (DERIVED)
  if (index !== undefined && index >= 0 && index < evs.length) {
    return { ev: evs[index], source: 'DERIVED' };
  }

  // If no index, try first event
  if (index === undefined && evs.length > 0) {
    return { ev: evs[0], source: 'DERIVED' };
  }

  return null;
}

// ── Status derivation ──────────────────────────────────────────────────────────

function deriveStatus(
  analysisResult: AnalysisResult | null,
  pendingApprovals: PendingApproval[],
  demoStatus: DemoStatus | null,
): DeveloperTraceStatus {
  if (!analysisResult && !demoStatus?.active) return 'UNKNOWN';

  const lifecycle = analysisResult?.lifecycle ?? [];

  // Check for ERROR (cast to string since LifecycleRecord.phase doesn't include 'ERROR' in schema)
  const hasError = lifecycle.some(r => (r.phase as string) === 'ERROR');
  if (hasError) return 'FAILED';

  // Check for RECONCILIATION_REQUIRED
  const hasUnknownExecution = lifecycle.some(
    r => r.phase === 'EXECUTE' && r.status === 'UNKNOWN',
  );
  if (hasUnknownExecution) return 'RECONCILIATION_REQUIRED';

  // Check for COMPLETE
  const hasOutcome = lifecycle.some(r => r.phase === 'OBSERVE_OUTCOME');
  if (hasOutcome) return 'COMPLETE';

  // Check for EXECUTING (has EXECUTE records in progress)
  const hasExecute = lifecycle.some(r => r.phase === 'EXECUTE');
  if (hasExecute) return 'EXECUTING';

  // Check for WAITING_FOR_APPROVAL
  if (pendingApprovals.length > 0 && !hasExecute) return 'WAITING_FOR_APPROVAL';

  // Check for IN_PROGRESS
  if (lifecycle.length > 0) return 'IN_PROGRESS';

  return 'UNKNOWN';
}

// ── ID generator ───────────────────────────────────────────────────────────────

let _idCounter = 0;
function nextId(): string {
  return `dte-${++_idCounter}`;
}

// ── Main build function ────────────────────────────────────────────────────────

export function buildDeveloperTrace(params: BuildDeveloperTraceParams): DeveloperTrace {
  const { analysisResult, pendingApprovals, demoStatus, sseEvents } = params;

  const lifecycle = analysisResult?.lifecycle ?? [];
  const assessment = analysisResult?.assessment;
  const timing = analysisResult?.timing;

  const sseByCategory = buildSseIndex(sseEvents);

  // First event timestamp (earliest SSE event in chrono order)
  const chronoEvents = [...sseEvents].reverse();
  const firstEventWallTs = chronoEvents.length > 0 ? chronoEvents[0].ts : undefined;

  // Helper to build traceClock from SSE event
  function makeTraceClock(ev: SSEEvent, base: string): TraceClock {
    const ms = msFrom(base, ev.ts);
    return {
      kind: 'TRACE',
      label: 'TRACE TIME',
      display: formatRelative(ms),
    };
  }

  // Build events list
  const events: DeveloperTraceEvent[] = [];

  // Collect APPROVE SSE events for gap calculation
  const approveSseEvents = sseByCategory.get('APPROVE') ?? [];
  const decideSseEvents = sseByCategory.get('DECIDE') ?? [];

  // Track propose/decide indices separately
  let observeIdx = 0;
  let skillIdx = 0;
  let proposeIdx = 0;
  let decideIdx = 0;
  let executeIdx = 0;

  // Track snapshot_id from OBSERVE lifecycle for artifact lineage
  let snapshotId: string | null = null;
  const proposalIds: TraceArtifactLineage['proposalIds'] = [];
  const decisionIds: TraceArtifactLineage['decisionIds'] = [];
  const executionIds: TraceArtifactLineage['executionIds'] = [];

  // Process lifecycle in order
  for (const rec of lifecycle) {
    const phase = rec.phase as string;

    if (phase === 'OBSERVE') {
      if (!rec.snapshot_id) {
        // First observe — no artifact ID yet
        const match = findSseMatch(sseByCategory, 'OBSERVE', observeIdx);
        const timingSource: TraceTimingSource = match ? match.source : 'NOT_INSTRUMENTED';

        const ev: DeveloperTraceEvent = {
          id: nextId(),
          category: 'OBSERVE',
          label: 'Warehouse state observation initiated',
          actor: 'WarehouseStateProvider (DERIVED)',
          actorSource: 'DERIVED',
          timingSource,
        };

        if (match && firstEventWallTs) {
          ev.wallTs = match.ev.ts;
          ev.relativeMs = msFrom(firstEventWallTs, match.ev.ts);
          ev.traceClock = makeTraceClock(match.ev, firstEventWallTs);
          if (match.ev.sim_time_seconds != null) {
            ev.simulationClock = {
              kind: 'SIMULATION',
              label: 'SIMULATION TIME',
              display: formatSimTime(match.ev.sim_time_seconds),
            };
          }
        } else {
          ev.timingNote = 'Not instrumented';
        }

        events.push(ev);
        observeIdx++;
      } else {
        // OBSERVE with snapshot_id
        snapshotId = rec.snapshot_id;
        const match = findSseMatch(sseByCategory, 'OBSERVE', observeIdx, rec.snapshot_id);
        const timingSource: TraceTimingSource = match ? match.source : 'NOT_INSTRUMENTED';

        const ev: DeveloperTraceEvent = {
          id: nextId(),
          category: 'STATE',
          label: 'Warehouse snapshot captured',
          actor: 'WarehouseStateProvider (DERIVED)',
          actorSource: 'DERIVED',
          artifactId: rec.snapshot_id,
          metadata: { snapshot_id: rec.snapshot_id },
          timingSource,
        };

        if (match && firstEventWallTs) {
          ev.wallTs = match.ev.ts;
          ev.relativeMs = msFrom(firstEventWallTs, match.ev.ts);
          ev.traceClock = makeTraceClock(match.ev, firstEventWallTs);
        } else {
          ev.timingNote = 'Not instrumented';
        }

        events.push(ev);
        observeIdx++;
      }
    } else if (phase === 'REASON') {
      const match = findSseMatch(sseByCategory, 'REASON', undefined);

      if (rec.message && String(rec.message).includes('started')) {
        // AGENT event
        const timingSource: TraceTimingSource = match ? match.source : 'NOT_INSTRUMENTED';

        const agentEv: DeveloperTraceEvent = {
          id: nextId(),
          category: 'AGENT',
          label: 'OperationsCoordinationAgent started',
          actor: 'OperationsCoordinationAgent (DERIVED)',
          actorSource: 'DERIVED',
          timingSource,
        };

        if (match && firstEventWallTs) {
          agentEv.wallTs = match.ev.ts;
          agentEv.relativeMs = msFrom(firstEventWallTs, match.ev.ts);
          agentEv.traceClock = makeTraceClock(match.ev, firstEventWallTs);
        } else {
          agentEv.timingNote = 'Not instrumented';
        }

        events.push(agentEv);

        // Synthetic MODEL_ROUTING event
        const routingEv: DeveloperTraceEvent = {
          id: nextId(),
          category: 'MODEL_ROUTING',
          label: 'Model routing rule evaluation',
          detail: 'routing_rule not yet available (arrives with REASON complete)',
          actor: 'ModelGateway (DERIVED)',
          actorSource: 'DERIVED',
          timingSource: 'DERIVED',
          timingNote: 'Routing rule available after REASON completion',
        };

        if (match && firstEventWallTs) {
          routingEv.wallTs = match.ev.ts;
          routingEv.relativeMs = msFrom(firstEventWallTs, match.ev.ts);
          routingEv.traceClock = makeTraceClock(match.ev, firstEventWallTs);
        }

        events.push(routingEv);
      } else if (rec.summary != null || assessment) {
        // REASON complete — three events
        const latency_ms = rec.latency_ms ?? assessment?.latency_ms;
        const model_id = rec.model_id ?? assessment?.model_id;
        const routing_rule = rec.routing_rule ?? assessment?.routing_rule;
        const routing_reason = rec.routing_reason ?? assessment?.routing_reason;

        // 1. MODEL_ROUTING
        const routingEv: DeveloperTraceEvent = {
          id: nextId(),
          category: 'MODEL_ROUTING',
          label: `Routing rule: ${routing_rule ?? 'unknown'}`,
          detail: routing_reason ? `reason=${routing_reason}` : undefined,
          actor: 'ModelGateway (DERIVED)',
          actorSource: 'DERIVED',
          timingSource: match ? match.source : 'NOT_INSTRUMENTED',
          metadata: {
            routing_rule: routing_rule ?? null,
            routing_reason: routing_reason ?? null,
          },
        };

        if (match && firstEventWallTs) {
          routingEv.wallTs = match.ev.ts;
          routingEv.relativeMs = msFrom(firstEventWallTs, match.ev.ts);
          routingEv.traceClock = makeTraceClock(match.ev, firstEventWallTs);
        } else {
          routingEv.timingNote = 'Not instrumented';
        }
        events.push(routingEv);

        // 2. MODEL (LIVE — has model_id)
        const modelEv: DeveloperTraceEvent = {
          id: nextId(),
          category: 'MODEL',
          label: model_id ?? 'Model inference',
          actor: model_id ?? 'Model (DERIVED)',
          actorSource: model_id ? 'LIVE' : 'DERIVED',
          timingSource: model_id ? 'LIVE' : (match ? match.source : 'NOT_INSTRUMENTED'),
          metadata: {
            model_id: model_id ?? null,
            latency_ms: latency_ms ?? null,
          },
        };

        if (match && firstEventWallTs) {
          modelEv.wallTs = match.ev.ts;
          modelEv.relativeMs = msFrom(firstEventWallTs, match.ev.ts);
          modelEv.traceClock = makeTraceClock(match.ev, firstEventWallTs);
        }

        if (latency_ms != null) {
          modelEv.componentLatency = {
            kind: 'COMPONENT',
            label: 'MODEL LATENCY',
            display: `${(latency_ms / 1000).toFixed(2)}s`,
          };
        }

        if (match?.ev.sim_time_seconds != null) {
          modelEv.simulationClock = {
            kind: 'SIMULATION',
            label: 'SIMULATION TIME',
            display: formatSimTime(match.ev.sim_time_seconds),
          };
        }

        events.push(modelEv);

        // 3. ASSESSMENT
        const assessEv: DeveloperTraceEvent = {
          id: nextId(),
          category: 'ASSESSMENT',
          label: rec.summary ?? assessment?.summary ?? 'Assessment complete',
          detail: assessment?.severity ? `severity=${assessment.severity}` : undefined,
          actor: 'OperationsCoordinationAgent (DERIVED)',
          actorSource: 'DERIVED',
          timingSource: match ? match.source : 'NOT_INSTRUMENTED',
          metadata: {
            severity: assessment?.severity ?? null,
            snapshot_id: assessment?.snapshot_id ?? null,
          },
          explanationFocus: { kind: 'stage', stage: 'PROPOSE' },
        };

        if (match && firstEventWallTs) {
          assessEv.wallTs = match.ev.ts;
          assessEv.relativeMs = msFrom(firstEventWallTs, match.ev.ts);
          assessEv.traceClock = makeTraceClock(match.ev, firstEventWallTs);
        } else {
          assessEv.timingNote = 'Not instrumented';
        }

        events.push(assessEv);
      }
    } else if (phase === 'SKILL') {
      const i = skillIdx;
      const match = findSseMatch(sseByCategory, 'SKILL', i, rec.capability);
      const timingSource: TraceTimingSource = 'NOT_INSTRUMENTED'; // Skills are never SSE-instrumented

      const ev: DeveloperTraceEvent = {
        id: nextId(),
        category: 'SKILL',
        label: rec.capability ?? `skill[${i}]`,
        detail: [
          rec.domain ? `domain=${rec.domain}` : null,
          rec.target ? `target=${rec.target}` : null,
        ].filter(Boolean).join(' ') || undefined,
        actor: `${rec.domain ?? 'unknown'}Skill (DERIVED)`,
        actorSource: 'DERIVED',
        timingSource,
        timingNote: 'Not instrumented',
        metadata: {
          capability: rec.capability ?? null,
          domain: rec.domain ?? null,
          priority: rec.priority ?? null,
          objective: rec.objective ?? null,
          index: i,
        },
      };

      // If SSE match exists (unlikely for SKILL), use it
      if (match && match.source === 'LIVE' && firstEventWallTs) {
        ev.wallTs = match.ev.ts;
        ev.relativeMs = msFrom(firstEventWallTs, match.ev.ts);
        ev.traceClock = makeTraceClock(match.ev, firstEventWallTs);
        (ev as any).timingSource = 'LIVE';
        delete ev.timingNote;
      }

      events.push(ev);
      skillIdx++;
    } else if (phase === 'PROPOSE') {
      const i = proposeIdx;
      const proposalId = rec.proposal_id;
      if (proposalId) {
        proposalIds.push({ proposalId, action: rec.action ?? rec.capability ?? null });
      }

      const match = findSseMatch(sseByCategory, 'PROPOSE', i, proposalId);
      const timingSource: TraceTimingSource = match ? match.source : 'NOT_INSTRUMENTED';

      const ev: DeveloperTraceEvent = {
        id: nextId(),
        category: 'PROPOSAL',
        label: rec.action ?? rec.capability ?? `proposal[${i}]`,
        detail: proposalId ? `proposal_id=${proposalId}` : undefined,
        actor: 'DecisionEngine (DERIVED)',
        actorSource: 'DERIVED',
        artifactId: proposalId,
        timingSource,
        metadata: {
          proposal_id: proposalId ?? null,
          action: rec.action ?? null,
          risk_level: rec.risk_level ?? null,
          index: i,
        },
        explanationFocus: { kind: 'stage', stage: 'PROPOSE', proposalIndex: i },
      };

      if (match && firstEventWallTs) {
        ev.wallTs = match.ev.ts;
        ev.relativeMs = msFrom(firstEventWallTs, match.ev.ts);
        ev.traceClock = makeTraceClock(match.ev, firstEventWallTs);
      } else {
        ev.timingNote = 'Not instrumented';
      }

      events.push(ev);
      proposeIdx++;
    } else if (phase === 'DECIDE') {
      const i = decideIdx;
      const decisionId = rec.decision_id;
      const proposalId = rec.proposal_id;
      const outcome = rec.outcome;

      if (decisionId) {
        decisionIds.push({ decisionId, proposalId: proposalId ?? null, outcome: outcome ?? null });
      }

      const match = findSseMatch(sseByCategory, 'DECIDE', i, decisionId ?? proposalId);
      const timingSource: TraceTimingSource = match ? match.source : 'NOT_INSTRUMENTED';

      const ev: DeveloperTraceEvent = {
        id: nextId(),
        category: 'DECISION',
        label: outcome ?? `decision[${i}]`,
        detail: [
          decisionId ? `decision_id=${decisionId}` : null,
          proposalId ? `proposal_id=${proposalId}` : null,
        ].filter(Boolean).join(' ') || undefined,
        actor: 'DecisionEngine (DERIVED)',
        actorSource: 'DERIVED',
        artifactId: decisionId,
        timingSource,
        metadata: {
          decision_id: decisionId ?? null,
          proposal_id: proposalId ?? null,
          outcome: outcome ?? null,
          violations: rec.violations ?? null,
          index: i,
        },
        explanationFocus: { kind: 'stage', stage: 'DECIDE', proposalIndex: i },
      };

      if (match && firstEventWallTs) {
        ev.wallTs = match.ev.ts;
        ev.relativeMs = msFrom(firstEventWallTs, match.ev.ts);
        ev.traceClock = makeTraceClock(match.ev, firstEventWallTs);
      } else {
        ev.timingNote = 'Not instrumented';
      }

      events.push(ev);
      decideIdx++;

      // APPROVAL_WAIT gap event for REQUIRES_HUMAN_APPROVAL outcomes
      if (outcome === 'REQUIRES_HUMAN_APPROVAL') {
        const decideTs = match?.ev.ts;
        const approveTs = approveSseEvents.length > 0 ? approveSseEvents[0].ts : null;

        let gapDisplay: string | undefined;
        let gapTimingNote: string;

        if (decideTs && approveTs && firstEventWallTs) {
          const gapMs = msFrom(decideTs, approveTs);
          gapDisplay = `~${(gapMs / 1000).toFixed(1)}s`;
          gapTimingNote = 'Trace-observed — approval resolution timestamp not emitted by backend';
        } else {
          gapTimingNote = 'Not available — approval resolution timestamp not emitted';
        }

        const gapEv: DeveloperTraceEvent = {
          id: nextId(),
          category: 'APPROVAL_WAIT',
          label: 'WAITING FOR OPERATOR',
          detail: gapDisplay ? `trace_observed_wait=${gapDisplay}` : undefined,
          actor: undefined,
          actorSource: 'DERIVED',
          timingSource: 'NOT_INSTRUMENTED',
          timingNote: gapTimingNote,
          isGap: true,
        };

        events.push(gapEv);
      }
    } else if (phase === 'EXECUTE') {
      const i = executeIdx;
      const executionId = rec.execution_id;
      const proposalId = rec.proposal_id;
      const status = rec.status;

      if (executionId) {
        executionIds.push({ executionId, proposalId: proposalId ?? null, status: status ?? null });
      }

      const match = findSseMatch(sseByCategory, 'EXECUTE', i, executionId);
      const timingSource: TraceTimingSource = match ? match.source : 'NOT_INSTRUMENTED';

      const ev: DeveloperTraceEvent = {
        id: nextId(),
        category: 'EXECUTION',
        label: rec.action ?? rec.capability ?? `execution[${i}]`,
        detail: [
          executionId ? `execution_id=${executionId}` : null,
          status ? `status=${status}` : null,
        ].filter(Boolean).join(' ') || undefined,
        actor: 'ActionExecutor (DERIVED)',
        actorSource: 'DERIVED',
        artifactId: executionId,
        timingSource,
        metadata: {
          execution_id: executionId ?? null,
          proposal_id: proposalId ?? null,
          status: status ?? null,
          action: rec.action ?? null,
          index: i,
        },
      };

      if (match && firstEventWallTs) {
        ev.wallTs = match.ev.ts;
        ev.relativeMs = msFrom(firstEventWallTs, match.ev.ts);
        ev.traceClock = makeTraceClock(match.ev, firstEventWallTs);
      } else {
        ev.timingNote = 'Not instrumented';
      }

      if (status === 'UNKNOWN') {
        ev.timingNote = 'Execution outcome unconfirmed — automatic retry suppressed';
      }

      events.push(ev);

      // Synthetic MCP sub-entry
      const mcpEv: DeveloperTraceEvent = {
        id: nextId(),
        category: 'MCP',
        label: `MCP dispatch → ${rec.domain ?? 'unknown'} domain`,
        actor: 'ActionExecutor (DERIVED)',
        actorSource: 'DERIVED',
        timingSource: 'DERIVED',
        timingNote: 'Not independently instrumented',
      };

      if (match && firstEventWallTs) {
        mcpEv.wallTs = match.ev.ts;
        mcpEv.relativeMs = msFrom(firstEventWallTs, match.ev.ts);
        mcpEv.traceClock = makeTraceClock(match.ev, firstEventWallTs);
      }

      events.push(mcpEv);
      executeIdx++;
    } else if (phase === 'OBSERVE_OUTCOME') {
      const match = findSseMatch(sseByCategory, 'OBSERVE', observeIdx);
      const timingSource: TraceTimingSource = match ? match.source : 'NOT_INSTRUMENTED';

      const postKpis = analysisResult?.post_kpis;
      const detail = rec.summary
        ? `summary=${encodeURIComponent(rec.summary).slice(0, 80)}`
        : undefined;

      const ev: DeveloperTraceEvent = {
        id: nextId(),
        category: 'OUTCOME',
        label: rec.summary ?? 'Operational outcome observed',
        detail,
        actor: 'WarehouseStateProvider (DERIVED)',
        actorSource: 'DERIVED',
        timingSource,
        metadata: {
          summary: rec.summary ?? null,
        },
        explanationFocus: { kind: 'stage', stage: 'OUTCOME' },
      };

      if (match && firstEventWallTs) {
        ev.wallTs = match.ev.ts;
        ev.relativeMs = msFrom(firstEventWallTs, match.ev.ts);
        ev.traceClock = makeTraceClock(match.ev, firstEventWallTs);
      } else {
        ev.timingNote = 'Not instrumented';
      }

      if (postKpis?.sim_time_seconds != null) {
        ev.simulationClock = {
          kind: 'SIMULATION',
          label: 'SIMULATION TIME',
          display: formatSimTime(postKpis.sim_time_seconds),
        };
      }

      events.push(ev);
    }
  }

  // Inject RECOMMENDATIONS (between SKILL and PROPOSE) — derived from assessment
  // Use a manual findLastIndex since Array.prototype.findLastIndex is not in all targets
  let lastSkillIdx = -1;
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].category === 'SKILL') { lastSkillIdx = i; break; }
  }
  const firstProposalIdx = events.findIndex(e => e.category === 'PROPOSAL');
  const insertAt = lastSkillIdx >= 0
    ? lastSkillIdx + 1
    : (firstProposalIdx >= 0 ? firstProposalIdx : events.length);

  if (assessment?.recommendations && assessment.recommendations.length > 0) {
    const recEvents: DeveloperTraceEvent[] = assessment.recommendations.map((rec, i) => ({
      id: nextId(),
      category: 'RECOMMENDATION' as const,
      label: `${rec.capability} → ${rec.target}`,
      detail: `domain=${rec.domain} priority=${rec.priority}`,
      actor: 'OperationsCoordinationAgent (DERIVED)',
      actorSource: 'DERIVED' as const,
      timingSource: 'DERIVED' as const,
      metadata: {
        capability: rec.capability,
        target: rec.target,
        domain: rec.domain,
        priority: rec.priority,
        index: i,
      },
      timingNote: 'No warehouse mutation at this stage',
    }));

    events.splice(insertAt, 0, ...recEvents);
  }

  // Inject EXECUTION_BOUNDARY before first EXECUTION event
  const firstExecutionIdx = events.findIndex(e => e.category === 'EXECUTION');
  if (firstExecutionIdx >= 0) {
    const boundaryEv: DeveloperTraceEvent = {
      id: nextId(),
      category: 'EXECUTION_BOUNDARY',
      label: 'EXECUTION BOUNDARY',
      detail: 'Post-boundary actions may mutate warehouse state',
      actor: undefined,
      actorSource: 'DERIVED',
      timingSource: 'DERIVED',
      isExecutionBoundary: true,
    };
    events.splice(firstExecutionIdx, 0, boundaryEv);
  }

  // Build approval lineage from pendingApprovals
  const approvalIds: TraceArtifactLineage['approvalIds'] = pendingApprovals.map(pa => ({
    approvalId: pa.pending_id,
    decisionId: pa.decision_id ?? null,
    state: 'PENDING',
  }));

  const artifacts: TraceArtifactLineage = {
    snapshotId,
    proposalIds,
    decisionIds,
    approvalIds,
    executionIds,
  };

  // Build timings array (Refinement 3 — three distinct clocks)
  const latency_ms = assessment?.latency_ms;
  const timings: TraceTiming[] = [
    {
      label: 'Model reasoning',
      value: latency_ms != null ? `${(latency_ms / 1000).toFixed(2)}s` : '—',
      kind: 'COMPONENT',
      available: latency_ms != null,
      unavailableReason: latency_ms == null ? 'Not available' : undefined,
    },
    {
      label: 'Time to detect',
      value: timing?.time_to_detect_ms != null
        ? `${(timing.time_to_detect_ms / 1000).toFixed(2)}s`
        : '—',
      kind: 'COMPONENT',
      available: timing?.time_to_detect_ms != null,
      unavailableReason: timing?.time_to_detect_ms == null ? 'Not available' : undefined,
    },
    {
      label: 'Time to decision',
      value: timing?.time_to_decision_ms != null
        ? `${(timing.time_to_decision_ms / 1000).toFixed(2)}s`
        : '—',
      kind: 'COMPONENT',
      available: timing?.time_to_decision_ms != null,
      unavailableReason: timing?.time_to_decision_ms == null ? 'Not available' : undefined,
    },
    {
      label: 'Time to execution',
      value: timing?.time_to_execution_ms != null
        ? `${(timing.time_to_execution_ms / 1000).toFixed(2)}s`
        : '—',
      kind: 'COMPONENT',
      available: timing?.time_to_execution_ms != null,
      unavailableReason: timing?.time_to_execution_ms == null ? 'Not available' : undefined,
    },
    // Refinement 4 — show missing telemetry explicitly
    {
      label: 'Human approval wait',
      value: '—',
      kind: 'TRACE',
      available: false,
      unavailableReason: 'Not available — approval resolution timestamp not emitted',
    },
  ];

  const status = deriveStatus(analysisResult, pendingApprovals, demoStatus);

  return {
    traceId: analysisResult?.trace_id ?? pendingApprovals[0]?.trace_id ?? null,
    warehouseId: assessment?.warehouse_id ?? demoStatus?.world?.warehouse_id ?? null,
    scenarioName: demoStatus?.scenario?.display_name ?? demoStatus?.scenario?.name ?? null,
    status,
    firstEventWallTs,
    events,
    artifacts,
    timings,
    scenarioRunIdNote: [
      'KNOWN LIMITATION: scenario_run_id exists in the backend controller but is not',
      'part of the public trace contract. Trace boundary is established from',
      'trace_id + active demo state. This becomes relevant when multi-trace',
      'scenarios are introduced (Copilot layer).',
    ].join(' '),
  };
}
