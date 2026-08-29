/**
 * ReasonStage — shows the OperationsCoordinationAgent's assessment.
 *
 * Data sources:
 *   1. SSE REASON events: message=assessment.summary, detail="model=X rule=Y"
 *   2. SSE SKILL events:  message=capability, detail="target=T" — shown as subordinates
 *   3. analysisResult.assessment: severity, model_id, routing_reason, latency_ms (post-analysis)
 */

import React from 'react';
import { Box, Typography } from '@mui/material';
import {
  SectionHeader,
  StageSection,
  MonoText,
  RiskBadge,
  IdText,
  parseDetail,
  runWindowEvents,
  StageContentPaneProps,
} from '../StageContentPane';

// ── Severity badge ─────────────────────────────────────────────────────────────

const SEVERITY_COLOR: Record<string, string> = {
  critical: '#F85149',
  high:     '#F85149',
  medium:   '#D29922',
  low:      '#3FB950',
};

function SeverityBadge({ severity }: { severity: string }) {
  const color = SEVERITY_COLOR[severity?.toLowerCase()] ?? '#484F58';
  return (
    <Box component="span" sx={{
      fontFamily: 'monospace',
      fontSize: '0.62rem',
      fontWeight: 700,
      color,
      border: `1px solid ${color}44`,
      borderRadius: '3px',
      px: '5px',
      py: '1px',
      textTransform: 'uppercase',
      letterSpacing: '0.08em',
    }}>
      {severity}
    </Box>
  );
}

// ── Skill chip ─────────────────────────────────────────────────────────────────

function SkillChip({ capability, target }: { capability: string; target?: string }) {
  return (
    <Box sx={{
      display: 'flex',
      alignItems: 'center',
      gap: 1,
      background: '#161B22',
      border: '1px solid #21262D',
      borderRadius: '4px',
      px: 1.25,
      py: '5px',
    }}>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#58A6FF', letterSpacing: '0.08em', textTransform: 'uppercase', flexShrink: 0 }}>
        skill
      </Typography>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', color: '#C9D1D9', fontWeight: 500 }}>
        {capability}
      </Typography>
      {target && (
        <>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#484F58' }}>→</Typography>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#8B949E' }}>
            {target}
          </Typography>
        </>
      )}
    </Box>
  );
}

// ── ReasonStage ───────────────────────────────────────────────────────────────

export default function ReasonStage({ sseEvents, analysisResult }: StageContentPaneProps) {
  const reasonEvents = runWindowEvents(sseEvents, ['REASON']);
  const skillEvents  = runWindowEvents(sseEvents, ['SKILL']);

  // Primary REASON event (latest, now in chronological order = last in array)
  const primaryReason = reasonEvents[reasonEvents.length - 1] ?? null;
  const reasonDetail  = parseDetail(primaryReason?.detail);

  const assessment = analysisResult?.assessment;

  // SKILL lifecycle records (structured) take precedence over SSE SKILL events
  const skillRecords = analysisResult?.lifecycle?.filter(r => r.phase === 'SKILL') ?? [];

  // Model + routing from: analysisResult (preferred) → SSE detail (fallback)
  const modelId      = assessment?.model_id  ?? reasonDetail.model ?? null;
  const routingRule  = assessment?.routing_rule ?? reasonDetail.rule ?? null;
  const routingReason = assessment?.routing_reason ?? null;
  const latencyMs    = assessment?.latency_ms ?? null;
  const summary      = assessment?.summary ?? primaryReason?.message ?? null;
  const severity     = assessment?.severity ?? null;

  return (
    <Box data-testid="reason-stage">
      {/* Stage header */}
      <StageSection>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Typography sx={{
            fontFamily: 'monospace', fontSize: '0.72rem', fontWeight: 700,
            color: '#58A6FF', textTransform: 'uppercase', letterSpacing: '0.06em',
          }}>
            Reason
          </Typography>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58' }}>
            OperationsCoordinationAgent
          </Typography>
          {latencyMs != null && (
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#484F58', ml: 'auto' }}>
              {latencyMs}ms
            </Typography>
          )}
        </Box>
      </StageSection>

      {/* Model + routing */}
      {(modelId || routingRule) && (
        <StageSection>
          <SectionHeader>Model selection</SectionHeader>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
            {modelId && <IdText label="Model" value={modelId} />}
            {routingRule && <IdText label="Rule" value={routingRule} />}
            {routingReason && (
              <MonoText color="#484F58" size="0.62rem">{routingReason}</MonoText>
            )}
          </Box>
        </StageSection>
      )}

      {/* Assessment */}
      {(summary || severity) && (
        <StageSection>
          <SectionHeader>Assessment</SectionHeader>
          {severity && (
            <Box sx={{ mb: 1 }}>
              <SeverityBadge severity={severity} />
            </Box>
          )}
          {summary && (
            <Box sx={{
              background: '#161B22',
              border: '1px solid #21262D',
              borderRadius: '4px',
              px: 1.5,
              py: 1.25,
            }}>
              <MonoText color="#8B949E" size="0.7rem">{summary}</MonoText>
            </Box>
          )}
        </StageSection>
      )}

      {/* Skills consulted */}
      {(skillRecords.length > 0 || skillEvents.length > 0) && (
        <StageSection last>
          <SectionHeader>Skills consulted</SectionHeader>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
            {/* Prefer structured lifecycle records */}
            {skillRecords.length > 0
              ? skillRecords.map((rec, i) => (
                  <SkillChip key={i} capability={rec.capability} target={rec.target} />
                ))
              : skillEvents.map(ev => {
                  const d = parseDetail(ev.detail);
                  return (
                    <SkillChip key={ev.id} capability={ev.message} target={d.target} />
                  );
                })
            }
          </Box>
        </StageSection>
      )}

      {/* Waiting for model response */}
      {!primaryReason && !assessment && (
        <StageSection last>
          <MonoText color="#484F58" size="0.65rem">
            Waiting for OperationsCoordinationAgent response...
          </MonoText>
        </StageSection>
      )}
    </Box>
  );
}
