/**
 * ReliabilityScenarioSelector — five fault scenarios.
 * F06 (Ambiguous Write) is the recommended / hero scenario.
 *
 * Static definitions — no API call needed. Fault IDs and expected behaviors
 * come from Phase 10E Batch 6 validated artifacts.
 */

import React from 'react';
import { Box, Typography } from '@mui/material';

// ── Scenario definitions ──────────────────────────────────────────────────────

export interface FaultScenario {
  id: string;
  recommended?: boolean;
  title: string;
  subtitle: string;
  expected: string;
  narrative: string[];
  domain?: string;
}

export const FAULT_SCENARIOS: FaultScenario[] = [
  {
    id: 'F06',
    recommended: true,
    title: 'Ambiguous Write',
    subtitle: 'MCP write timeout AFTER mutation',
    expected: 'UNKNOWN → no retry → reconciliation → CONFIRMED EXECUTED',
    narrative: ['FAULT', 'EXECUTE', 'UNKNOWN', 'SAFETY', 'RECONCILE', 'CONFIRMED'],
    domain: 'equipment',
  },
  {
    id: 'F07',
    title: 'Duplicate Approval',
    subtitle: 'Three APPROVE attempts for one pending_id',
    expected: 'one authority grant → one execution → one mutation',
    narrative: ['APPROVE ×1', 'CONSUMED ×2', 'SAFETY'],
  },
  {
    id: 'F10',
    title: 'State Drift',
    subtitle: 'World state changes between propose and execute',
    expected: 'valid approval → changed state → execution blocked',
    narrative: ['FAULT', 'EXECUTE', 'CONFLICT', 'SAFETY'],
    domain: 'equipment',
  },
  {
    id: 'F12',
    title: 'Labor MCP Circuit Open',
    subtitle: 'Labor domain unavailable; others healthy',
    expected: 'Labor unavailable → runtime DEGRADED; Equipment/Inventory remain available',
    narrative: ['CIRCUIT_OPEN', 'SAFETY', 'DEGRADED'],
    domain: 'labor',
  },
  {
    id: 'F01',
    title: 'NIM Timeout',
    subtitle: 'Model does not respond in time',
    expected: 'no assessment → no proposal → no execution',
    narrative: ['TIMEOUT', 'SAFETY'],
  },
];

// ── Card ──────────────────────────────────────────────────────────────────────

function ScenarioCard({
  scenario,
  selected,
  onSelect,
}: {
  scenario: FaultScenario;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  const { id, recommended, title, subtitle, expected, narrative } = scenario;
  const accent = recommended ? '#D29922' : '#484F58';
  const borderColor = selected ? '#1F6FEB' : recommended ? `${accent}55` : '#21262D';

  return (
    <Box
      component="button"
      onClick={() => onSelect(id)}
      data-testid={`fault-scenario-${id}`}
      aria-pressed={selected}
      sx={{
        display: 'block',
        width: '100%',
        textAlign: 'left',
        background: selected ? '#0d2146' : '#161B22',
        border: `1.5px solid ${borderColor}`,
        borderRadius: '6px',
        px: 1.75,
        py: 1.25,
        cursor: 'pointer',
        position: 'relative',
        transition: 'all 0.1s ease',
        '&:hover': { borderColor: '#388BFD', background: '#0d1930' },
      }}
    >
      {/* Badges */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58', letterSpacing: '0.1em' }}>
          {id}
        </Typography>
        {recommended && (
          <Box component="span" sx={{
            fontFamily: 'monospace', fontSize: '0.58rem', fontWeight: 700,
            color: '#D29922', border: '1px solid #D2992244', borderRadius: '3px',
            px: '4px', py: '1px', letterSpacing: '0.08em', textTransform: 'uppercase',
          }}
          data-testid={`fault-scenario-${id}-recommended`}
          >
            ★ Recommended
          </Box>
        )}
      </Box>

      <Typography sx={{
        fontFamily: 'monospace', fontSize: '0.78rem', fontWeight: 700,
        color: '#C9D1D9', mb: '2px',
      }}>
        {title}
      </Typography>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#6E7681', mb: 0.75 }}>
        {subtitle}
      </Typography>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#484F58', mb: 0.75 }}>
        Expected: {expected}
      </Typography>

      {/* Narrative preview */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, flexWrap: 'wrap' }}>
        {narrative.map((step, i) => (
          <React.Fragment key={step}>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: accent, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
              {step}
            </Typography>
            {i < narrative.length - 1 && (
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#30363D' }}>→</Typography>
            )}
          </React.Fragment>
        ))}
      </Box>
    </Box>
  );
}

// ── ReliabilityScenarioSelector ───────────────────────────────────────────────

interface Props {
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export default function ReliabilityScenarioSelector({ selectedId, onSelect }: Props) {
  return (
    <Box data-testid="reliability-scenario-selector">
      <Typography sx={{
        fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58',
        letterSpacing: '0.12em', textTransform: 'uppercase', mb: 0.75,
      }}>
        Reliability scenario
      </Typography>
      <Typography sx={{
        fontFamily: 'monospace', fontSize: '0.82rem', fontWeight: 700,
        color: '#C9D1D9', mb: 1.5,
      }}>
        Choose a reliability scenario
      </Typography>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {FAULT_SCENARIOS.map(s => (
          <ScenarioCard
            key={s.id}
            scenario={s}
            selected={selectedId === s.id}
            onSelect={onSelect}
          />
        ))}
      </Box>
    </Box>
  );
}
