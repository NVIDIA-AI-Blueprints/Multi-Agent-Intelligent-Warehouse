/**
 * DeveloperJourneyRail.tsx — 7-stage orientation nav for the ExpertOverlay JOURNEY tab.
 *
 * Renders stage pills (CONTEXT → OUTCOME) with availability status.
 * Clicking an available stage fires onStageSelect.
 * Never shows chain-of-thought or hidden reasoning state.
 */

import React from 'react';
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
  pending:     { pill: 'transparent', text: '#484F58',  border: '#21262D' },
  unavailable: { pill: 'transparent', text: '#30363D',  border: '#21262D' },
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
  const colors = isActive
    ? STATUS_COLORS.current
    : STATUS_COLORS[info.status];

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flex: 1, position: 'relative' }}>
      {/* Connector line — left half */}
      {!isFirst && (
        <Box sx={{
          position: 'absolute',
          top: '12px',
          left: 0,
          width: '50%',
          height: '1px',
          background: info.status === 'pending' || info.status === 'unavailable' ? '#21262D' : '#1F6FEB44',
        }} />
      )}
      {/* Connector line — right half */}
      {!isLast && (
        <Box sx={{
          position: 'absolute',
          top: '12px',
          right: 0,
          width: '50%',
          height: '1px',
          background: info.status === 'pending' || info.status === 'unavailable' ? '#21262D' : '#1F6FEB44',
        }} />
      )}

      {/* Dot */}
      <Box
        data-testid={`journey-stage-${info.stage}`}
        onClick={clickable ? onSelect : undefined}
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
          '&:hover': clickable ? {
            background: '#1F6FEB33',
            borderColor: '#58A6FF',
          } : {},
        }}
      >
        {info.status === 'available' && !isActive && (
          <Box sx={{ width: 6, height: 6, borderRadius: '50%', background: '#58A6FF' }} />
        )}
        {(info.status === 'current' || isActive) && (
          <Box sx={{ width: 8, height: 8, borderRadius: '50%', background: '#79C0FF' }} />
        )}
      </Box>

      {/* Label */}
      <Typography sx={{
        fontFamily: 'monospace',
        fontSize: '0.52rem',
        fontWeight: isActive ? 700 : 400,
        color: isActive ? '#C9D1D9' : colors.text,
        letterSpacing: '0.06em',
        textTransform: 'uppercase',
        mt: '4px',
        textAlign: 'center',
        lineHeight: 1.2,
        whiteSpace: 'nowrap',
      }}>
        {JOURNEY_STAGE_LABEL[info.stage]}
      </Typography>

      {/* Artifact ID hint */}
      {info.artifactIdHint && (isActive || info.status === 'current') && (
        <Typography sx={{
          fontFamily: 'monospace',
          fontSize: '0.44rem',
          color: '#484F58',
          mt: '1px',
          textAlign: 'center',
          letterSpacing: '0.04em',
          maxWidth: 64,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}>
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
  // Build a lookup for fast status access
  const stageMap = new Map<JourneyStage, JourneyStageInfo>();
  for (const s of stages) stageMap.set(s.stage, s);

  const orderedStages = JOURNEY_STAGES.map(s => stageMap.get(s) ?? {
    stage: s,
    status: 'unavailable' as JourneyStageStatus,
  });

  return (
    <Box
      data-testid="developer-journey-rail"
      sx={{
        display: 'flex',
        flexDirection: 'row',
        alignItems: 'flex-start',
        width: '100%',
        py: 1.5,
        px: 0.5,
        background: '#0D1117',
        borderBottom: '1px solid #21262D',
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
