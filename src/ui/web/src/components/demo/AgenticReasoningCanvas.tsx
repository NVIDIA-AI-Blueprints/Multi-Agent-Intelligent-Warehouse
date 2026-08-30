/**
 * AgenticReasoningCanvas — Phase 13B
 *
 * Unified structured view of the agentic reasoning arc:
 *   OBSERVED EVIDENCE → AGENT INTERPRETATION → CAPABILITIES/SKILLS → RECOMMENDED RESPONSE
 *
 * Data sources (all from AnalysisResult — no invented fields):
 *   assessment.facts_observed          → OBSERVED EVIDENCE
 *   assessment.summary + model fields  → AGENT INTERPRETATION
 *   lifecycle[phase=SKILL]             → CAPABILITIES/SKILLS
 *   assessment.recommendations         → RECOMMENDED RESPONSE
 *
 * Gaps handled inline:
 *   reasoning_level — parsed from routing_reason string ("reasoning=HIGH …")
 *   agent_name      — hardcoded: single agent in this system
 */

import React, { useState } from 'react';
import { Box, Typography, Collapse } from '@mui/material';
import { AnalysisResult, LifecycleRecord, RecommendedAction } from '../../services/demoAPI';
import { SectionHeader, MonoText, IdText } from './StageContentPane';

// ── Parsing helpers ───────────────────────────────────────────────────────────

function parseReasoningLevel(routingReason: string | null | undefined): string | null {
  if (!routingReason) return null;
  const m = routingReason.match(/reasoning=(\w+)/i);
  return m ? m[1].toUpperCase() : null;
}

// ── Badge components ──────────────────────────────────────────────────────────

const SEVERITY_COLOR: Record<string, string> = {
  critical: '#F85149',
  high:     '#F85149',
  medium:   '#D29922',
  low:      '#3FB950',
  none:     '#3FB950',
};

const PRIORITY_COLOR: Record<string, string> = {
  critical: '#F85149',
  high:     '#F85149',
  medium:   '#D29922',
  low:      '#3FB950',
};

const REASONING_COLOR: Record<string, string> = {
  HIGH:   '#F85149',
  MEDIUM: '#D29922',
  LOW:    '#3FB950',
};

function Badge({ label, color }: { label: string; color: string }) {
  return (
    <Box component="span" sx={{
      fontFamily: 'monospace',
      fontSize: '0.6rem',
      fontWeight: 700,
      color,
      border: `1px solid ${color}44`,
      borderRadius: '3px',
      px: '5px',
      py: '1px',
      textTransform: 'uppercase',
      letterSpacing: '0.08em',
      flexShrink: 0,
    }}>
      {label}
    </Box>
  );
}

// ── Collapsible pillar ────────────────────────────────────────────────────────

interface PillarProps {
  index: number;
  title: string;
  accentColor: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  empty?: boolean;
}

function Pillar({ index, title, accentColor, children, defaultOpen = true, empty = false }: PillarProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <Box sx={{ mb: 1.5 }}>
      {/* Pillar header row */}
      <Box
        component="button"
        onClick={() => setOpen(o => !o)}
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          width: '100%',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          p: 0,
          mb: open ? 0.75 : 0,
        }}
      >
        {/* Step number */}
        <Box sx={{
          width: 18,
          height: 18,
          borderRadius: '50%',
          border: `1px solid ${empty ? '#30363D' : accentColor}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}>
          <Typography sx={{
            fontFamily: 'monospace',
            fontSize: '0.55rem',
            fontWeight: 700,
            color: empty ? '#30363D' : accentColor,
            lineHeight: 1,
          }}>
            {index}
          </Typography>
        </Box>

        {/* Title */}
        <Typography sx={{
          fontFamily: 'monospace',
          fontSize: '0.58rem',
          fontWeight: 700,
          color: empty ? '#30363D' : accentColor,
          textTransform: 'uppercase',
          letterSpacing: '0.12em',
          flexGrow: 1,
          textAlign: 'left',
        }}>
          {title}
        </Typography>

        {/* Chevron */}
        <Typography sx={{
          fontFamily: 'monospace',
          fontSize: '0.6rem',
          color: '#484F58',
        }}>
          {open ? '▾' : '▸'}
        </Typography>
      </Box>

      <Collapse in={open}>
        <Box sx={{
          borderLeft: `2px solid ${empty ? '#21262D' : accentColor}22`,
          ml: '8px',
          pl: 1.75,
          pb: 0.5,
        }}>
          {children}
        </Box>
      </Collapse>
    </Box>
  );
}

// ── Skill row ─────────────────────────────────────────────────────────────────

function SkillRow({ rec }: { rec: LifecycleRecord }) {
  const domainColor: Record<string, string> = {
    equipment: '#58A6FF',
    labor:     '#3FB950',
    wave:      '#D29922',
    inventory: '#A371F7',
  };
  const color = domainColor[rec.domain] ?? '#8B949E';

  return (
    <Box sx={{
      display: 'flex',
      alignItems: 'center',
      gap: 1,
      py: '5px',
      borderBottom: '1px solid #1C2128',
      flexWrap: 'wrap',
    }}>
      <Badge label={rec.domain ?? '—'} color={color} />
      <MonoText color="#C9D1D9" size="0.68rem" weight={500}>{rec.capability ?? '—'}</MonoText>
      {rec.target && (
        <>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#484F58' }}>→</Typography>
          <MonoText color="#8B949E" size="0.65rem">{rec.target}</MonoText>
        </>
      )}
      {rec.objective && (
        <MonoText color="#484F58" size="0.6rem">{rec.objective}</MonoText>
      )}
    </Box>
  );
}

// ── Recommendation row ────────────────────────────────────────────────────────

function RecommendationRow({ rec, index }: { rec: RecommendedAction; index: number }) {
  const pColor = PRIORITY_COLOR[rec.priority] ?? '#484F58';
  const [expanded, setExpanded] = useState(index === 0);

  return (
    <Box sx={{ borderBottom: '1px solid #1C2128', py: '6px' }}>
      <Box
        component="button"
        onClick={() => setExpanded(e => !e)}
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          width: '100%',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          p: 0,
          flexWrap: 'wrap',
        }}
      >
        <Badge label={rec.priority} color={pColor} />
        <MonoText color="#C9D1D9" size="0.68rem" weight={500}>{rec.capability}</MonoText>
        {rec.target && (
          <>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#484F58' }}>→</Typography>
            <MonoText color="#8B949E" size="0.65rem">{rec.target}</MonoText>
          </>
        )}
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#484F58', ml: 'auto' }}>
          {expanded ? '▾' : '▸'}
        </Typography>
      </Box>

      <Collapse in={expanded}>
        <Box sx={{ mt: 0.75, ml: 0.5 }}>
          <MonoText color="#6E7681" size="0.65rem">{rec.rationale}</MonoText>
        </Box>
      </Collapse>
    </Box>
  );
}

// ── AgenticReasoningCanvas ────────────────────────────────────────────────────

interface AgenticReasoningCanvasProps {
  analysisResult: AnalysisResult | null;
}

export default function AgenticReasoningCanvas({ analysisResult }: AgenticReasoningCanvasProps) {
  const assessment = analysisResult?.assessment ?? null;
  const lifecycle  = analysisResult?.lifecycle  ?? [];
  const skillRecords  = lifecycle.filter(r => r.phase === 'SKILL');
  const recommendations = assessment?.recommendations ?? [];

  const reasoningLevel = parseReasoningLevel(assessment?.routing_reason);
  const severityColor  = SEVERITY_COLOR[assessment?.severity ?? ''] ?? '#484F58';
  const reasoningColor = REASONING_COLOR[reasoningLevel ?? ''] ?? '#484F58';

  const hasEvidence        = (assessment?.facts_observed?.length ?? 0) > 0;
  const hasInterpretation  = !!assessment;
  const hasSkills          = skillRecords.length > 0;
  const hasRecommendations = recommendations.length > 0;

  return (
    <Box data-testid="agentic-reasoning-canvas">
      {/* Canvas header */}
      <Box sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 1.5,
        mb: 2,
        pb: 1.5,
        borderBottom: '1px solid #21262D',
        flexWrap: 'wrap',
      }}>
        <Typography sx={{
          fontFamily: 'monospace',
          fontSize: '0.6rem',
          fontWeight: 700,
          color: '#58A6FF',
          textTransform: 'uppercase',
          letterSpacing: '0.1em',
        }}>
          Agentic Reasoning Trace
        </Typography>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#484F58' }}>
          OperationsCoordinationAgent
        </Typography>
        {assessment?.model_id && (
          <Box sx={{ ml: 'auto', display: 'flex', alignItems: 'center', gap: 1 }}>
            <MonoText color="#484F58" size="0.58rem">{assessment.model_id}</MonoText>
            {assessment.latency_ms != null && (
              <MonoText color="#30363D" size="0.58rem">{Math.round(assessment.latency_ms)}ms</MonoText>
            )}
          </Box>
        )}
      </Box>

      {/* ── Pillar 1: OBSERVED EVIDENCE ────────────────────────────────── */}
      <Pillar
        index={1}
        title="Observed Evidence"
        accentColor="#58A6FF"
        defaultOpen
        empty={!hasEvidence}
      >
        {hasEvidence ? (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {assessment!.facts_observed.map((fact, i) => (
              <Box key={i} sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#484F58', mt: '1px', flexShrink: 0 }}>
                  ●
                </Typography>
                <MonoText color="#8B949E" size="0.68rem">{fact}</MonoText>
              </Box>
            ))}
          </Box>
        ) : (
          <MonoText color="#30363D" size="0.65rem">
            {analysisResult ? 'No facts recorded.' : 'Awaiting analysis...'}
          </MonoText>
        )}
      </Pillar>

      {/* ── Pillar 2: AGENT INTERPRETATION ─────────────────────────────── */}
      <Pillar
        index={2}
        title="Agent Interpretation"
        accentColor="#D29922"
        defaultOpen
        empty={!hasInterpretation}
      >
        {hasInterpretation ? (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            {/* Severity + reasoning level badges */}
            <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap' }}>
              {assessment!.severity && (
                <Badge label={`severity: ${assessment!.severity}`} color={severityColor} />
              )}
              {reasoningLevel && (
                <Badge label={`reasoning: ${reasoningLevel}`} color={reasoningColor} />
              )}
            </Box>

            {/* Summary */}
            {assessment!.summary && (
              <Box sx={{
                background: '#161B22',
                border: '1px solid #21262D',
                borderRadius: '4px',
                px: 1.5,
                py: 1,
              }}>
                <MonoText color="#8B949E" size="0.68rem">{assessment!.summary}</MonoText>
              </Box>
            )}

            {/* Routing rule + reason (model + latency shown in canvas header) */}
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
              {assessment!.routing_rule && (
                <IdText label="rule" value={assessment!.routing_rule} />
              )}
              {assessment!.routing_reason && (
                <MonoText color="#484F58" size="0.62rem">{assessment!.routing_reason}</MonoText>
              )}
            </Box>
          </Box>
        ) : (
          <MonoText color="#30363D" size="0.65rem">
            Awaiting model response...
          </MonoText>
        )}
      </Pillar>

      {/* ── Pillar 3: CAPABILITIES / SKILLS ────────────────────────────── */}
      <Pillar
        index={3}
        title="Capabilities / Skills Activated"
        accentColor="#3FB950"
        defaultOpen
        empty={!hasSkills}
      >
        {hasSkills ? (
          <Box>
            {skillRecords.map((rec, i) => (
              <SkillRow key={i} rec={rec} />
            ))}
          </Box>
        ) : (
          <MonoText color="#30363D" size="0.65rem">
            {analysisResult ? 'No skills activated.' : 'Awaiting skill dispatch...'}
          </MonoText>
        )}
      </Pillar>

      {/* ── Pillar 4: RECOMMENDED RESPONSE ─────────────────────────────── */}
      <Pillar
        index={4}
        title="Recommended Response"
        accentColor="#A371F7"
        defaultOpen
        empty={!hasRecommendations}
      >
        {hasRecommendations ? (
          <Box>
            {recommendations.map((rec, i) => (
              <RecommendationRow key={i} rec={rec} index={i} />
            ))}
          </Box>
        ) : (
          <MonoText color="#30363D" size="0.65rem">
            {analysisResult ? 'No recommendations generated.' : 'Awaiting recommendations...'}
          </MonoText>
        )}
      </Pillar>
    </Box>
  );
}
