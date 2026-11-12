/**
 * routingFallback.test.tsx — the UI shows when RUN MAIW ANALYSIS fell back to
 * another model.
 *
 * HIGH reasoning prefers Super, which is disabled by default, so the router
 * serves the request with Ultra. routing_reason names the preferred role
 * ("reasoning=HIGH requires Super"), so on its own it reads as if Super
 * answered. /demo/analyze now returns fallback_from and fallback_reason; the
 * Developer Trace and the journey MODEL panel show them.
 */

import React from 'react';
import { render, screen, within } from '@testing-library/react';
import '@testing-library/jest-dom';
import { buildDeveloperTrace } from '../../components/demo/developer-trace/buildDeveloperTrace';
import DeveloperJourneyPanel from '../../components/developer-journey/DeveloperJourneyPanel';
import { AnalysisResult } from '../../services/demoAPI';

const FALLBACK_REASON = 'role=super is disabled or policy-ineligible; escalated to ultra';

function analysis(fallback: boolean): AnalysisResult {
  const route = {
    model_id: 'nvidia/nemotron-3-ultra-550b-a55b',
    routing_rule: 'high_reasoning',
    routing_reason: 'reasoning=HIGH requires Super',
    fallback_from: fallback ? 'super' : null,
    fallback_reason: fallback ? FALLBACK_REASON : null,
    latency_ms: 29142,
  };
  return {
    ok: true,
    trace_id: 'trace-1',
    assessment: {
      snapshot_id: 'snap-1',
      warehouse_id: 'DC-47',
      assessed_at: '2026-11-12T20:02:36Z',
      summary: '40 idle workers, 4 unassigned wave tasks',
      severity: 'critical',
      domains_affected: ['labor', 'wave'],
      facts_observed: [],
      recommendations: [],
      ...route,
    },
    proposal_results: [],
    lifecycle: [{ phase: 'REASON', summary: '40 idle workers', ...route }],
  };
}

const EMPTY = { pendingApprovals: [], demoStatus: null, sseEvents: [], graph: null };

describe('Developer Trace — MODEL_ROUTING event', () => {
  test('shows the fallback next to the routing reason', () => {
    const trace = buildDeveloperTrace({ ...EMPTY, analysisResult: analysis(true) });
    const routing = trace.events.find(e => e.category === 'MODEL_ROUTING');
    expect(routing!.detail).toBe('reason=reasoning=HIGH requires Super · fallback_from=super');
    expect(routing!.metadata).toMatchObject({
      fallback_from: 'super',
      fallback_reason: FALLBACK_REASON,
    });
  });

  test('keeps only the reason when the preferred role served the request', () => {
    const trace = buildDeveloperTrace({ ...EMPTY, analysisResult: analysis(false) });
    const routing = trace.events.find(e => e.category === 'MODEL_ROUTING');
    expect(routing!.detail).toBe('reason=reasoning=HIGH requires Super');
    expect(routing!.metadata).toMatchObject({ fallback_from: null, fallback_reason: null });
  });
});

describe('Developer journey MODEL panel', () => {
  test('shows the analysis fallback when there is no Copilot turn', () => {
    render(
      <DeveloperJourneyPanel
        activeStage="MODEL"
        identity={{ model_id: 'nvidia/nemotron-3-ultra-550b-a55b' } as any}
        analysisResult={analysis(true)}
        copilotTurn={null}
        demoStatus={null}
        agentTask={null}
      />
    );
    const panel = screen.getByTestId('journey-panel-MODEL');
    expect(within(panel).getByText('reasoning=HIGH requires Super')).toBeInTheDocument();
    expect(within(panel).getByText('super')).toBeInTheDocument();
    expect(within(panel).getByText(FALLBACK_REASON)).toBeInTheDocument();
  });
});
