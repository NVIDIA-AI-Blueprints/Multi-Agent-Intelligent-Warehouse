/**
 * ReliabilityPanel — orchestrates the reliability demo experience.
 *
 * Layout:
 *   Left column (30%): ReliabilityScenarioSelector
 *   Right column (70%):
 *     Top: SafetyContextStrip (replaces OperationalContextStrip in reliability mode)
 *     Main: ReliabilityLifecycleNarrative + ReconciliationStatus + FaultInjectionPanel
 *     Bottom: SafetyScorecard (VALIDATED BATCH 6 evidence)
 *
 * All counters from live SSE. Scorecard is static Batch 6 evidence.
 */

import React, { useState, useCallback } from 'react';
import { Box, Typography } from '@mui/material';
import { SSEEvent } from '../../../hooks/useDemoSSE';
import { FAULT_SCENARIOS } from './ReliabilityScenarioSelector';
import ReliabilityScenarioSelector from './ReliabilityScenarioSelector';
import ReliabilityLifecycleNarrative from './ReliabilityLifecycleNarrative';
import FaultInjectionPanel from './FaultInjectionPanel';
import SafetyScorecard from './SafetyScorecard';
import ReconciliationStatus from './ReconciliationStatus';
import SafetyContextStrip from './SafetyContextStrip';
import { demoAPI } from '../../../services/demoAPI';

interface Props {
  sseEvents: SSEEvent[];
  runtime?: any;
}

export default function ReliabilityPanel({ sseEvents, runtime }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>('F06');

  const selectedScenario = FAULT_SCENARIOS.find(s => s.id === selectedId) ?? null;

  const handleReconcile = useCallback(async (executionId: string, domain: string) => {
    try {
      await demoAPI.reconcile(executionId, domain);
    } catch {
      // ReconciliationStatus reads outcome from SSE; errors surface there
    }
  }, []);

  return (
    <Box data-testid="reliability-panel" sx={{ display: 'flex', flexDirection: 'column', flexGrow: 1, overflow: 'hidden' }}>
      {/* Safety context strip — replaces OperationalContextStrip */}
      <SafetyContextStrip sseEvents={sseEvents} />

      {/* Body */}
      <Box sx={{ display: 'flex', flexGrow: 1, overflow: 'auto' }}>
        {/* Left: scenario selector */}
        <Box sx={{
          width: '30%',
          minWidth: 200,
          maxWidth: 300,
          borderRight: '1px solid #21262D',
          p: 2,
          flexShrink: 0,
          overflowY: 'auto',
        }}>
          <ReliabilityScenarioSelector
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        </Box>

        {/* Right: content */}
        <Box sx={{ flexGrow: 1, p: 2, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 2 }}>
          {selectedScenario ? (
            <>
              {/* Scenario header */}
              <Box>
                <Typography sx={{
                  fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58',
                  letterSpacing: '0.12em', textTransform: 'uppercase', mb: 0.25,
                }}>
                  {selectedScenario.id}
                </Typography>
                <Typography sx={{
                  fontFamily: 'monospace', fontSize: '0.9rem', fontWeight: 700,
                  color: '#C9D1D9', mb: '2px',
                }}>
                  {selectedScenario.title}
                </Typography>
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', color: '#6E7681' }}>
                  {selectedScenario.subtitle}
                </Typography>
              </Box>

              {/* Two-column: narrative + controls */}
              <Box sx={{ display: 'flex', gap: 2 }}>
                {/* Lifecycle narrative */}
                <Box sx={{
                  width: '40%',
                  background: '#161B22',
                  border: '1px solid #21262D',
                  borderRadius: '6px',
                  p: 1.5,
                }}>
                  <Typography sx={{
                    fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58',
                    letterSpacing: '0.12em', textTransform: 'uppercase', mb: 1,
                  }}>
                    Fault lifecycle
                  </Typography>
                  <ReliabilityLifecycleNarrative
                    scenarioId={selectedId!}
                    sseEvents={sseEvents}
                    runtime={runtime}
                  />
                </Box>

                {/* Controls */}
                <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                  {/* Reconciliation status — only visible if relevant SSE fired */}
                  <ReconciliationStatus
                    sseEvents={sseEvents}
                    onReconcile={handleReconcile}
                  />

                  {/* Fault injection */}
                  <Box sx={{
                    background: '#161B22',
                    border: '1px solid #21262D',
                    borderRadius: '6px',
                    p: 1.5,
                  }}>
                    <FaultInjectionPanel
                      scenarioId={selectedId}
                      sseEvents={sseEvents}
                    />
                  </Box>
                </Box>
              </Box>

              {/* Batch 6 scorecard */}
              <Box sx={{
                background: '#161B22',
                border: '1px solid #21262D',
                borderRadius: '6px',
                p: 1.5,
              }}>
                <SafetyScorecard scenarioId={selectedId} />
              </Box>
            </>
          ) : (
            <Box sx={{ p: 2 }}>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.72rem', color: '#484F58' }}>
                Select a reliability scenario from the left panel.
              </Typography>
            </Box>
          )}
        </Box>
      </Box>
    </Box>
  );
}
