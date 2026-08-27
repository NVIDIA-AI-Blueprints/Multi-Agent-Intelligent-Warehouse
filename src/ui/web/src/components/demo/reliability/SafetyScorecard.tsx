/**
 * SafetyScorecard — per-scenario Batch 6 validated evidence.
 *
 * VALIDATED BATCH 6 label: artifacts from Phase 10E Batch 6 test run.
 * Static data only. No API calls.
 *
 * Each scenario shows:
 *   - Invariants exercised
 *   - Batch 6 test result
 *   - Observed behavior
 */

import React from 'react';
import { Box, Typography } from '@mui/material';

interface ScorecardEntry {
  invariant: string;
  invariantLabel: string;
  result: 'PASS';
  observed: string;
}

interface ScenarioScorecard {
  id: string;
  entries: ScorecardEntry[];
}

const SCORECARDS: Record<string, ScenarioScorecard> = {
  F06: {
    id: 'F06',
    entries: [
      {
        invariant: 'D',
        invariantLabel: 'Ambiguous Write Safety',
        result: 'PASS',
        observed: 'UNKNOWN raised, retry suppressed, reconcile resolved CONFIRMED_EXECUTED',
      },
      {
        invariant: 'E',
        invariantLabel: 'Idempotency Guard',
        result: 'PASS',
        observed: 'No duplicate mutation applied during UNKNOWN window',
      },
    ],
  },
  F07: {
    id: 'F07',
    entries: [
      {
        invariant: 'C',
        invariantLabel: 'Duplicate Approval Prevention',
        result: 'PASS',
        observed: 'Second and third APPROVE attempts returned 404 consumed; one execution only',
      },
    ],
  },
  F10: {
    id: 'F10',
    entries: [
      {
        invariant: 'B',
        invariantLabel: 'State Drift Detection',
        result: 'PASS',
        observed: 'ActionConflict raised on execution; guard 5 blocked write to stale state',
      },
    ],
  },
  F12: {
    id: 'F12',
    entries: [
      {
        invariant: 'F',
        invariantLabel: 'Circuit Open Isolation',
        result: 'PASS',
        observed: 'Labor domain circuit opened; Equipment and Inventory remained HEALTHY',
      },
      {
        invariant: 'A',
        invariantLabel: 'Graceful Degradation',
        result: 'PASS',
        observed: 'Runtime status → DEGRADED (not UNAVAILABLE); partial service continued',
      },
    ],
  },
  F01: {
    id: 'F01',
    entries: [
      {
        invariant: 'A',
        invariantLabel: 'NIM Timeout Safety',
        result: 'PASS',
        observed: 'Model gateway timeout returned 504; no proposal produced; no execution attempted',
      },
    ],
  },
};

interface Props {
  scenarioId: string | null;
}

export default function SafetyScorecard({ scenarioId }: Props) {
  const scorecard = scenarioId ? SCORECARDS[scenarioId] : null;

  return (
    <Box data-testid="safety-scorecard">
      {/* VALIDATED BATCH 6 header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
        <Box sx={{
          fontFamily: 'monospace', fontSize: '0.58rem', fontWeight: 700,
          color: '#3FB950', border: '1px solid #3FB95044', borderRadius: '3px',
          px: '5px', py: '2px', letterSpacing: '0.08em', textTransform: 'uppercase',
          flexShrink: 0,
        }}>
          VALIDATED BATCH 6
        </Box>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58' }}>
          Phase 10E reliability test run
        </Typography>
      </Box>

      {!scorecard && (
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58' }}>
          Select a scenario to view Batch 6 evidence.
        </Typography>
      )}

      {scorecard && (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
          {scorecard.entries.map(entry => (
            <Box
              key={entry.invariant}
              data-testid={`scorecard-invariant-${entry.invariant}`}
              sx={{
                background: '#0d1a0d',
                border: '1px solid #3FB95022',
                borderRadius: '4px',
                px: 1.25,
                py: 0.75,
              }}
            >
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: '3px' }}>
                <Typography sx={{
                  fontFamily: 'monospace', fontSize: '0.6rem', fontWeight: 700,
                  color: '#3FB950', letterSpacing: '0.06em',
                }}>
                  ✓ INVARIANT {entry.invariant}
                </Typography>
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#6E7681' }}>
                  {entry.invariantLabel}
                </Typography>
                <Box sx={{
                  fontFamily: 'monospace', fontSize: '0.55rem', fontWeight: 700,
                  color: '#3FB950', border: '1px solid #3FB95044', borderRadius: '2px',
                  px: '3px', py: '1px', letterSpacing: '0.08em',
                  ml: 'auto',
                }}>
                  {entry.result}
                </Box>
              </Box>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#484F58' }}>
                {entry.observed}
              </Typography>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
}
