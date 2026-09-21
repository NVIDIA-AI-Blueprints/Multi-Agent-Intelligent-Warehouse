/**
 * DeveloperJourneyRail.tsx — 7-stage orientation nav for the ExpertOverlay JOURNEY tab.
 *
 * Renders stage pills (CONTEXT → OUTCOME) with availability status.
 * Clicking or pressing Enter/Space on an available stage fires onStageSelect.
 * Never shows chain-of-thought or hidden reasoning state.
 */

import React, { KeyboardEvent } from 'react';
import { Box, Typography } from '@mui/material';
import {
  JOURNEY_STAGES,
  JOURNEY_STAGE_LABEL,
  JourneyStage,
  JourneyStageStatus,
} from '../../constants/journeyIdentity';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface JourneyStageInfo {
  stage: JourneyStage;
  status: JourneyStageStatus;
  /** Short artifact ID to display in the pill (e.g. first 8 chars of trace_id). */
  artifactIdHint?: string;
}

interface DeveloperJourneyRailProps {
  stages: JourneyStageInfo[];
  activeStage: JourneyStage | null;
  onStageSelect: (stage: JourneyStage) => void;
}

// ── Colors ────────────────────────────────────────────────────────────────────

const STATUS_COLORS: Record<JourneyStageStatus, { pill: string; text: string; border: string }> = {
  available:   { pill: 'transparent', text: '#58A6FF', border: '#1F6FEB44' },
  current:     { pill: '#1F6FEB22',   text: '#79C0FF', border: '#1F6FEB' },
  pending:     { pill: 'transparent', text: '#6E7681',  border: '#21262D' },
  unavailable: { pill: 'transparent', text: '#484F58',  border: '#21262D' },
};

// ── Single stage pill ─────────────────────────────────────────────────────────

function StagePill({
  info,
  isActive,
  isFirst,
  isLast,
  onSelect,
}: {
  info: JourneyStageInfo;
  isActive: boolean;
  isFirst: boolean;
  isLast: boolean;
  onSelect: () => void;
}) {
  const clickable = info.status === 'available' || info.status === 'current';
  const disabled = info.status === 'unavailable' || info.status === 'pending';
  const colors = isActive ? STATUS_COLORS.current : STATUS_COLORS[info.status];

  const stageLabel = JOURNEY_STAGE_LABEL[info.stage];
  const statusDescription = isActive
    ? 'current'
    : info.status === 'available'
    ? 'available'
    : info.status === 'pending'
    ? 'pending'
    : 'unavailable';
  const ariaLabel = `${stageLabel} stage — ${statusDescription}${info.artifactIdHint ? `, artifact ${info.artifactIdHint}` : ''}`;

  function handleKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (!clickable) { return; }
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onSelect();
    }
  }

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        flex: 1,
        position: 'relative',
      }}
    >
      {/* Connector line — left half */}
      {!isFirst && (
        <Box
          aria-hidden="true"
          sx={{
            position: 'absolute',
            top: '12px',
            left: 0,
            width: '50%',
            height: '1px',
            background: disabled ? '#21262D' : '#1F6FEB44',
          }}
        />
      )}
      {/* Connector line — right half */}
      {!isLast && (
        <Box
          aria-hidden="true"
          sx={{
            position: 'absolute',
            top: '12px',
            right: 0,
            width: '50%',
            height: '1px',
            background: disabled ? '#21262D' : '#1F6FEB44',
          }}
        />
      )}

      {/* Dot — keyboard accessible button */}
      <Box
        data-testid={`journey-stage-${info.stage}`}
        role="button"
        tabIndex={clickable ? 0 : -1}
        aria-label={ariaLabel}
        aria-current={isActive ? 'step' : undefined}
        aria-disabled={disabled ? true : undefined}
        onClick={clickable ? onSelect : undefined}
        onKeyDown={handleKeyDown}
        sx={{
          width: 24,
          height: 24,
          borderRadius: '50%',
          background: isActive ? '#1F6FEB' : colors.pill,
          border: `1.5px solid ${isActive ? '#58A6FF' : colors.border}`,
          cursor: clickable ? 'pointer' : 'default',
          zIndex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transition: 'background 0.15s, border-color 0.15s',
          outline: 'none',
          '&:focus-visible': clickable ? {
            outline: '2px solid #58A6FF',
            outlineOffset: '3px',
          } : {},
          '&:hover': clickable ? {
            background: '#1F6FEB33',
            borderColor: '#58A6FF',
          } : {},
        }}
      >
        {info.status === 'available' && !isActive && (
          <Box
            aria-hidden="true"
            sx={{ width: 6, height: 6, borderRadius: '50%', background: '#58A6FF' }}
          />
        )}
        {(info.status === 'current' || isActive) && (
          <Box
            aria-hidden="true"
            sx={{ width: 8, height: 8, borderRadius: '50%', background: '#79C0FF' }}
          />
        )}
      </Box>

      {/* Label — hidden from a11y tree (stage info is on the button aria-label) */}
      <Typography
        aria-hidden="true"
        sx={{
          fontFamily: 'monospace',
          fontSize: '0.6rem',
          fontWeight: isActive ? 700 : 400,
          color: isActive ? '#C9D1D9' : colors.text,
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
          mt: '4px',
          textAlign: 'center',
          lineHeight: 1.2,
          whiteSpace: 'nowrap',
        }}
      >
        {stageLabel}
      </Typography>

      {/* Artifact ID hint — visible when active */}
      {info.artifactIdHint && (isActive || info.status === 'current') && (
        <Typography
          aria-hidden="true"
          sx={{
            fontFamily: 'monospace',
            fontSize: '0.5rem',
            color: '#6E7681',
            mt: '1px',
            textAlign: 'center',
            letterSpacing: '0.04em',
            maxWidth: 64,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {info.artifactIdHint}
        </Typography>
      )}
    </Box>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function DeveloperJourneyRail({
  stages,
  activeStage,
  onStageSelect,
}: DeveloperJourneyRailProps) {
  const stageMap = new Map<JourneyStage, JourneyStageInfo>();
  for (const s of stages) { stageMap.set(s.stage, s); }

  const orderedStages = JOURNEY_STAGES.map(s => stageMap.get(s) ?? {
    stage: s,
    status: 'unavailable' as JourneyStageStatus,
  });

  return (
    <Box
      data-testid="developer-journey-rail"
      role="group"
      aria-label="Developer journey stages"
      sx={{
        display: 'flex',
        flexDirection: 'row',
        alignItems: 'flex-start',
        width: '100%',
        minWidth: 0,
        overflowX: 'auto',
        py: 1.5,
        px: 0.5,
        background: '#0D1117',
        borderBottom: '1px solid #21262D',
        scrollbarWidth: 'thin',
        scrollbarColor: '#21262D transparent',
        '&::-webkit-scrollbar': { height: 3 },
        '&::-webkit-scrollbar-thumb': { background: '#21262D', borderRadius: 2 },
      }}
    >
      {orderedStages.map((info, idx) => (
        <StagePill
          key={info.stage}
          info={info}
          isActive={info.stage === activeStage}
          isFirst={idx === 0}
          isLast={idx === orderedStages.length - 1}
          onSelect={() => onStageSelect(info.stage)}
        />
      ))}
    </Box>
  );
}
