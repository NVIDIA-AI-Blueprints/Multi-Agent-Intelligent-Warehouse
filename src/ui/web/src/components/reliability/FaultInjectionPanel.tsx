import React, { useState } from 'react';
import { Box, Typography, Button } from '@mui/material';
import { demoAPI, InjectEventType } from '../../services/demoAPI';

interface FaultProfile {
  id: string;
  name: string;
  desc: string;
  safetyBehavior: string;
  injectEventType: InjectEventType | null;
  injectPayload?: Record<string, any>;
}

const PROFILES: FaultProfile[] = [
  {
    id: 'F01',
    name: 'NIM TIMEOUT',
    desc: 'Model provider times out — no proposal produced',
    safetyBehavior: 'ModelTimeout raised. Unauthorized writes: 0.',
    injectEventType: null, // test-infrastructure only
  },
  {
    id: 'F06',
    name: 'AMBIGUOUS WRITE',
    desc: 'MCP mutation sent, ACK lost — UNKNOWN outcome, no retry',
    safetyBehavior: 'UNKNOWN → reconcile → CONFIRMED_EXECUTED. False successes: 0.',
    injectEventType: null, // test-infrastructure only
  },
  {
    id: 'F08',
    name: 'DUPLICATE EXECUTION',
    desc: 'Same idempotency_key submitted twice',
    safetyBehavior: '1 mutation. Second call returns NO_OP (replayed=True). Duplicate writes: 0.',
    injectEventType: null, // test-infrastructure only
  },
  {
    id: 'F10',
    name: 'STATE DRIFT',
    desc: 'World state changed between assessment and execution',
    safetyBehavior: 'ActionConflict blocks write. Drift blocks: 1. Unauthorized writes: 0.',
    injectEventType: 'equipment_fault' as InjectEventType,
    injectPayload: { asset_id: 'AGV-01', fault_code: 'E_STATE_DRIFT_SIM' },
  },
  {
    id: 'F12',
    name: 'CIRCUIT OPEN',
    desc: 'Labor MCP domain circuit breaker trips',
    safetyBehavior: 'Labor: CIRCUIT OPEN. Equipment/Inventory: HEALTHY (domain isolation).',
    injectEventType: 'worker_absence' as InjectEventType,
    injectPayload: { worker_id: 'w-fault-sim' },
  },
];

interface Props {
  scenarioActive: boolean;
}

export default function FaultInjectionPanel({ scenarioActive }: Props) {
  const [injecting, setInjecting] = useState<string | null>(null);
  const [lastInjected, setLastInjected] = useState<string | null>(null);

  async function handleInject(profile: FaultProfile) {
    if (!profile.injectEventType || !scenarioActive) return;
    setInjecting(profile.id);
    try {
      await demoAPI.inject(profile.injectEventType, profile.injectPayload ?? {});
      setLastInjected(profile.id);
    } catch (e) {
      console.error('Fault inject failed', e);
    } finally {
      setInjecting(null);
    }
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.75 }}>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#F85149', letterSpacing: '0.08em', fontWeight: 700 }}>
          ⚠ DEMO FAULT INJECTION
        </Typography>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#484F58' }}>
          BATCH 6 VALIDATED · SAFE TO RE-RUN
        </Typography>
      </Box>

      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
        {PROFILES.map((p) => {
          const canInject = !!p.injectEventType && scenarioActive;
          const wasInjected = lastInjected === p.id;
          return (
            <Box key={p.id} sx={{
              display: 'flex', alignItems: 'flex-start', gap: 0.75,
              p: 0.75,
              border: '1px solid #1C2128',
              borderRadius: 0.5,
              backgroundColor: '#080C10',
            }}>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#F0883E', fontWeight: 700, width: 28, flexShrink: 0, mt: 0.1 }}>
                {p.id}
              </Typography>
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', fontWeight: 700, color: '#C9D1D9' }}>
                  {p.name}
                </Typography>
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#6E7681', mt: 0.1 }}>
                  {p.desc}
                </Typography>
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.57rem', color: '#3FB950', mt: 0.1 }}>
                  {p.safetyBehavior}
                </Typography>
              </Box>
              {canInject ? (
                <Button
                  size="small"
                  variant="outlined"
                  disabled={injecting === p.id}
                  onClick={() => handleInject(p)}
                  sx={{
                    fontSize: '0.5rem', fontFamily: 'monospace', fontWeight: 700,
                    py: 0.15, px: 0.5, minWidth: 0, flexShrink: 0,
                    borderColor: wasInjected ? '#3FB950' : '#F85149',
                    color: wasInjected ? '#3FB950' : '#F85149',
                    '&:hover': { borderColor: '#F85149', background: '#F8514911' },
                    '&:disabled': { borderColor: '#30363D', color: '#30363D' },
                  }}
                >
                  {wasInjected ? 'SENT' : injecting === p.id ? '…' : 'INJECT'}
                </Button>
              ) : (
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#484F58', flexShrink: 0, mt: 0.25 }}>
                  TEST ONLY
                </Typography>
              )}
            </Box>
          );
        })}
      </Box>

      {!scenarioActive && (
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58', mt: 0.5 }}>
          Start a scenario to enable injectable faults
        </Typography>
      )}
    </Box>
  );
}
