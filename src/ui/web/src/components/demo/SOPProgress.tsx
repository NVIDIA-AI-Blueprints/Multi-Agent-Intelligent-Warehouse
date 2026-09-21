/**
 * SOPProgress — UX-1B.2
 *
 * Shows the current progress through a Standard Operating Procedure (SOP).
 * Displays completed, current, pending, escalated, governance-wait, and skipped steps.
 *
 * Operator view:
 *   ✓ Establish current state
 *   ✓ Diagnose primary constraint
 *   → Compare interventions          ← current step (highlighted)
 *   ○ Generate recommendation
 *   ○ Wait for governance
 *
 * Expert expansion adds: sop_id, sop_version, step IDs, step timestamps.
 *
 * Accessibility:
 * - role="list" with role="listitem" per step
 * - aria-label on current step: "Current step: Compare interventions"
 * - NOT color-only: every state has icon + text label
 *
 * Architecture invariant:
 * - Step labels come from API (SOPStepView.description), never hardcoded
 * - Does NOT import from deepagents, LangGraph, or provider packages
 */

import React, { useState } from 'react';
import { Box, Typography, Collapse } from '@mui/material';
import { AgentTaskView, SOPStepDisplay, computeSOPStepDisplays } from '../../types/agentTask';
import { SOP_STEP_ICONS, getSopDisplayName } from '../../constants/agentTaskStates';

// ── Step state colors ─────────────────────────────────────────────────────────

const STEP_STATE_COLOR: Record<string, string> = {
  completed:       '#3FB950',
  current:         '#58A6FF',
  pending:         '#484F58',
  escalated:       '#F85149',
  governance_wait: '#D29922',
  skipped:         '#30363D',
};

const STEP_STATE_LABEL: Record<string, string> = {
  completed:       'Completed',
  current:         'In progress',
  pending:         'Pending',
  escalated:       'Escalated',
  governance_wait: 'Awaiting approval',
  skipped:         'Skipped',
};

// ── Step item ─────────────────────────────────────────────────────────────────

function SOPStepItem({
  display,
  expertMode,
}: {
  display: SOPStepDisplay;
  expertMode: boolean;
}) {
  const { step, state } = display;
  const isCurrent = state === 'current' || state === 'governance_wait';
  const color = STEP_STATE_COLOR[state] ?? '#484F58';
  const icon = SOP_STEP_ICONS[state] ?? '○';

  // Human-readable label: prefer description, fall back to step id
  const label = step.description
    ? step.description.trim().split('\n')[0].replace(/\s+/g, ' ').slice(0, 80)
    : step.id.replace(/_/g, ' ');

  return (
    <Box
      role="listitem"
      aria-label={isCurrent ? `Current step: ${label}` : undefined}
      aria-current={isCurrent ? 'step' : undefined}
      sx={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 1,
        py: 0.5,
        px: 0.75,
        borderRadius: '4px',
        background: isCurrent ? '#0d2146' : 'transparent',
        border: isCurrent ? '1px solid #1F6FEB22' : '1px solid transparent',
      }}
    >
      {/* State icon — text, never color-only */}
      <Typography
        aria-hidden="true"
        sx={{
          fontFamily: 'monospace',
          fontSize: '0.65rem',
          fontWeight: 700,
          color,
          flexShrink: 0,
          lineHeight: 1.4,
          width: '1rem',
          textAlign: 'center',
        }}
      >
        {icon}
      </Typography>

      {/* Step content */}
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography
          sx={{
            fontFamily: 'monospace',
            fontSize: '0.65rem',
            color: isCurrent ? '#C9D1D9' : state === 'completed' ? '#8B949E' : '#484F58',
            fontWeight: isCurrent ? 600 : 400,
            lineHeight: 1.4,
            wordBreak: 'break-word',
          }}
        >
          {label}
        </Typography>

        {/* State label (for screen readers and non-current steps) */}
        <Typography
          sx={{
            fontFamily: 'monospace',
            fontSize: '0.55rem',
            color,
            letterSpacing: '0.06em',
          }}
        >
          {STEP_STATE_LABEL[state] ?? state}
        </Typography>

        {/* Expert fields */}
        {expertMode && (
          <Typography
            sx={{
              fontFamily: 'monospace',
              fontSize: '0.5rem',
              color: '#30363D',
              mt: 0.25,
            }}
          >
            step_id: {step.id} · action: {step.action}
          </Typography>
        )}
      </Box>
    </Box>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface SOPProgressProps {
  task: AgentTaskView;
  expertMode?: boolean;
  /** Show collapsed (single-line summary) — expand on click */
  collapsible?: boolean;
}

const SOPProgress: React.FC<SOPProgressProps> = ({
  task,
  expertMode = false,
  collapsible = false,
}) => {
  const [expanded, setExpanded] = useState(!collapsible);
  const displays = computeSOPStepDisplays(task);
  const sopName = getSopDisplayName(task.sop_id);

  // Find current step for collapsed summary
  const currentDisplay = displays.find(
    (d) => d.state === 'current' || d.state === 'governance_wait',
  );
  const completedCount = displays.filter((d) => d.state === 'completed').length;

  if (task.sop_steps.length === 0) {
    return (
      <Typography
        sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#484F58' }}
      >
        No procedure steps recorded for this operation.
      </Typography>
    );
  }

  return (
    <Box data-testid="sop-progress">
      {/* Header */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          mb: 0.5,
          cursor: collapsible ? 'pointer' : 'default',
        }}
        onClick={collapsible ? () => setExpanded((e) => !e) : undefined}
        onKeyDown={
          collapsible
            ? (e) => { if (e.key === 'Enter' || e.key === ' ') setExpanded((v) => !v); }
            : undefined
        }
        tabIndex={collapsible ? 0 : undefined}
        role={collapsible ? 'button' : undefined}
        aria-expanded={collapsible ? expanded : undefined}
        aria-label={collapsible ? `Toggle SOP progress: ${sopName}` : undefined}
      >
        <Typography
          sx={{
            fontFamily: 'monospace',
            fontSize: '0.6rem',
            fontWeight: 700,
            color: '#C9D1D9',
            letterSpacing: '0.04em',
          }}
        >
          {sopName} v{task.sop_version}
        </Typography>

        {/* Progress summary */}
        <Typography
          sx={{
            fontFamily: 'monospace',
            fontSize: '0.55rem',
            color: '#484F58',
          }}
        >
          {completedCount}/{displays.length} steps
        </Typography>

        {collapsible && (
          <Typography
            aria-hidden="true"
            sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58', ml: 'auto' }}
          >
            {expanded ? '▲' : '▼'}
          </Typography>
        )}
      </Box>

      {/* Expert header */}
      {expertMode && (
        <Typography
          sx={{
            fontFamily: 'monospace',
            fontSize: '0.5rem',
            color: '#30363D',
            mb: 0.5,
          }}
        >
          sop_id: {task.sop_id} · version: {task.sop_version}
        </Typography>
      )}

      {/* Collapsed: just current step */}
      {collapsible && !expanded && currentDisplay && (
        <Typography
          sx={{
            fontFamily: 'monospace',
            fontSize: '0.6rem',
            color: '#58A6FF',
          }}
        >
          {SOP_STEP_ICONS.current}{' '}
          {currentDisplay.step.description
            ? currentDisplay.step.description.trim().split('\n')[0].slice(0, 60)
            : currentDisplay.step.id}
        </Typography>
      )}

      {/* Step list */}
      <Collapse in={!collapsible || expanded}>
        <Box role="list" aria-label={`Steps for ${sopName}`} sx={{ mt: 0.5 }}>
          {displays.map((d) => (
            <SOPStepItem
              key={d.step.id}
              display={d}
              expertMode={expertMode}
            />
          ))}
        </Box>
      </Collapse>
    </Box>
  );
};

export default SOPProgress;
