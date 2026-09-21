/**
 * DeveloperJourneyPanel.tsx — Per-stage artifact detail panels for the JOURNEY tab.
 *
 * Each stage sub-panel reads from the canonical ArtifactIdentity extracted from
 * analysisResult / copilotTurn / demoStatus. It shows exact IDs, artifact fields,
 * and cross-links to adjacent stages.
 *
 * SECURITY INVARIANT: No chain-of-thought, scratchpad, hidden_reasoning,
 * reasoning_tokens, or any excluded field from CHAIN_OF_THOUGHT_EXCLUDED_FIELDS
 * may appear in any panel render path.
 */

import React from 'react';
import { Box, Typography } from '@mui/material';
import { JourneyStage, ArtifactIdentity } from '../../constants/journeyIdentity';
import { AnalysisResult, CopilotTurnResponse, DemoStatus } from '../../services/demoAPI';
import { AgentTaskView } from '../../types/agentTask';

export type { AgentTaskView };

interface DeveloperJourneyPanelProps {
  activeStage: JourneyStage;
  identity: ArtifactIdentity;
  analysisResult: AnalysisResult | null;
  copilotTurn: CopilotTurnResponse | null;
  demoStatus: DemoStatus | null;
  agentTask: AgentTaskView | null;
  onNavigateToStage?: (stage: JourneyStage) => void;
}

// ── UI helpers ────────────────────────────────────────────────────────────────

function PanelSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Box sx={{ mb: 2 }}>
      <Typography sx={{
        fontFamily: 'monospace',
        fontSize: '0.55rem',
        fontWeight: 700,
        color: '#484F58',
        letterSpacing: '0.12em',
        textTransform: 'uppercase',
        mb: 0.75,
      }}>
        {title}
      </Typography>
      {children}
    </Box>
  );
}

function FieldRow({ label, value, mono = true }: { label: string; value: string | null | undefined; mono?: boolean }) {
  if (!value) { return null; }
  return (
    <Box sx={{ display: 'flex', gap: 1, mb: '4px', alignItems: 'flex-start' }}>
      <Typography sx={{
        fontFamily: 'monospace',
        fontSize: '0.58rem',
        color: '#6E7681',
        minWidth: 120,
        flexShrink: 0,
      }}>
        {label}
      </Typography>
      <Typography sx={{
        fontFamily: mono ? 'monospace' : 'inherit',
        fontSize: '0.58rem',
        color: '#C9D1D9',
        wordBreak: 'break-all',
      }}>
        {value}
      </Typography>
    </Box>
  );
}

function CrossLink({ label, onClick }: { label: string; onClick: () => void }) {
  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onClick();
    }
  }
  return (
    <Typography
      role="button"
      tabIndex={0}
      aria-label={`Navigate to ${label} stage`}
      onClick={onClick}
      onKeyDown={handleKeyDown}
      sx={{
        fontFamily: 'monospace',
        fontSize: '0.55rem',
        color: '#58A6FF',
        cursor: 'pointer',
        letterSpacing: '0.04em',
        display: 'inline-block',
        mr: 1.5,
        outline: 'none',
        '&:hover': { textDecoration: 'underline' },
        '&:focus-visible': {
          outline: '2px solid #58A6FF',
          outlineOffset: '2px',
          borderRadius: '2px',
        },
      }}
    >
      {label} <span aria-hidden="true">→</span>
    </Typography>
  );
}

function EmptyPanel({ stage }: { stage: JourneyStage }) {
  return (
    <Box sx={{ py: 3, textAlign: 'center' }}>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#484F58' }}>
        No {stage} artifact available for this interaction.
      </Typography>
    </Box>
  );
}

// ── Per-stage panels ──────────────────────────────────────────────────────────

function ContextPanel({ identity, copilotTurn, demoStatus, onNavigate }: {
  identity: ArtifactIdentity;
  copilotTurn: CopilotTurnResponse | null;
  demoStatus: DemoStatus | null;
  onNavigate?: (s: JourneyStage) => void;
}) {
  const snapshotId = identity.context_snapshot_id
    ?? copilotTurn?.context_snapshot_id
    ?? copilotTurn?.act_source_snapshot_id
    ?? null;

  if (!snapshotId && !identity.warehouse_id) { return <EmptyPanel stage="CONTEXT" />; }

  const world = demoStatus?.world;
  return (
    <Box>
      <PanelSection title="Operational Context Snapshot">
        <FieldRow label="snapshot_id" value={snapshotId} />
        <FieldRow label="warehouse_id" value={identity.warehouse_id ?? world?.warehouse_id} />
        <FieldRow label="clock" value={world?.clock_iso} />
        <FieldRow label="scenario" value={demoStatus?.scenario?.display_name ?? demoStatus?.scenario?.name} mono={false} />
      </PanelSection>
      {world && (
        <PanelSection title="World State">
          <FieldRow label="equipment total" value={String(world.equipment.total)} />
          <FieldRow label="equipment available" value={String(world.equipment.available)} />
          <FieldRow label="tasks in progress" value={String(world.tasks.in_progress)} />
          <FieldRow label="tasks pending" value={String(world.tasks.pending)} />
          <FieldRow label="workers active" value={String(world.workers.active)} />
          <FieldRow label="low stock SKUs" value={String(world.inventory.low_stock)} />
        </PanelSection>
      )}
      {onNavigate && (
        <Box sx={{ mt: 1 }}>
          <CrossLink label="AGENT/SOP" onClick={() => onNavigate('AGENT')} />
          <CrossLink label="MODEL" onClick={() => onNavigate('MODEL')} />
        </Box>
      )}
    </Box>
  );
}

function AgentPanel({ identity, agentTask, copilotTurn, onNavigate }: {
  identity: ArtifactIdentity;
  agentTask: AgentTaskView | null;
  copilotTurn: CopilotTurnResponse | null;
  onNavigate?: (s: JourneyStage) => void;
}) {
  const taskId = identity.agent_task_id ?? copilotTurn?.agent_task_id ?? agentTask?.task_id ?? null;
  const sopId = identity.sop_id ?? agentTask?.sop_id ?? null;

  if (!taskId && !sopId) { return <EmptyPanel stage="AGENT" />; }

  return (
    <Box>
      <PanelSection title="Agent Task">
        <FieldRow label="task_id" value={taskId} />
        <FieldRow label="agent_id" value={identity.agent_id ?? agentTask?.agent_id ?? copilotTurn?.agent} />
        <FieldRow label="status" value={agentTask?.status} />
        <FieldRow label="current_step" value={agentTask?.current_step_id} />
        <FieldRow label="runtime" value={identity.runtime} />
      </PanelSection>
      <PanelSection title="SOP">
        <FieldRow label="sop_id" value={sopId} />
        <FieldRow label="sop_version" value={identity.sop_version ?? agentTask?.sop_version} />
      </PanelSection>
      {onNavigate && (
        <Box sx={{ mt: 1 }}>
          <CrossLink label="CONTEXT" onClick={() => onNavigate('CONTEXT')} />
          <CrossLink label="MODEL" onClick={() => onNavigate('MODEL')} />
          <CrossLink label="SKILLS" onClick={() => onNavigate('SKILLS')} />
        </Box>
      )}
    </Box>
  );
}

function ModelPanel({ identity, analysisResult, copilotTurn, onNavigate }: {
  identity: ArtifactIdentity;
  analysisResult: AnalysisResult | null;
  copilotTurn: CopilotTurnResponse | null;
  onNavigate?: (s: JourneyStage) => void;
}) {
  const modelId = identity.model_id
    ?? copilotTurn?.model_id
    ?? analysisResult?.assessment?.model_id
    ?? null;

  if (!modelId) { return <EmptyPanel stage="MODEL" />; }

  const routingRule = identity.routing_rule
    ?? copilotTurn?.routing_rule
    ?? analysisResult?.assessment?.routing_rule
    ?? null;

  const routingReason = copilotTurn?.routing_reason
    ?? analysisResult?.assessment?.routing_reason
    ?? null;

  const latencyMs = copilotTurn?.latency_ms ?? analysisResult?.assessment?.latency_ms ?? null;

  const fallbackFrom = copilotTurn?.fallback_from ?? null;
  const fallbackReason = copilotTurn?.fallback_reason ?? null;
  const selectedRole = copilotTurn?.selected_role ?? null;
  const requestedRole = copilotTurn?.requested_role ?? null;

  return (
    <Box>
      <PanelSection title="ModelGateway Route">
        <FieldRow label="model_id" value={modelId} />
        <FieldRow label="routing_rule" value={routingRule} />
        <FieldRow label="routing_reason" value={routingReason} />
        <FieldRow label="requested_role" value={requestedRole} />
        <FieldRow label="selected_role" value={selectedRole} />
        <FieldRow label="latency_ms" value={latencyMs !== null ? String(latencyMs) : undefined} />
        {fallbackFrom && (
          <>
            <FieldRow label="fallback_from" value={fallbackFrom} />
            <FieldRow label="fallback_reason" value={fallbackReason} />
          </>
        )}
        <FieldRow label="reasoning_level" value={copilotTurn?.reasoning_level} />
      </PanelSection>
      {onNavigate && (
        <Box sx={{ mt: 1 }}>
          <CrossLink label="CONTEXT" onClick={() => onNavigate('CONTEXT')} />
          <CrossLink label="AGENT/SOP" onClick={() => onNavigate('AGENT')} />
          <CrossLink label="SKILLS" onClick={() => onNavigate('SKILLS')} />
        </Box>
      )}
    </Box>
  );
}

function SkillsPanel({ copilotTurn, onNavigate }: {
  copilotTurn: CopilotTurnResponse | null;
  onNavigate?: (s: JourneyStage) => void;
}) {
  const skillsUsed = copilotTurn?.skills_used ?? [];
  const skillsAvail = copilotTurn?.skills_available ?? [];

  if (!skillsUsed.length && !skillsAvail.length) { return <EmptyPanel stage="SKILLS" />; }

  return (
    <Box>
      {skillsUsed.length > 0 && (
        <PanelSection title="Skills Invoked">
          {skillsUsed.map(skill => (
            <Typography key={skill} sx={{
              fontFamily: 'monospace',
              fontSize: '0.58rem',
              color: '#3FB950',
              mb: '2px',
            }}>
              ✓ {skill}
            </Typography>
          ))}
        </PanelSection>
      )}
      {skillsAvail.length > 0 && (
        <PanelSection title="Skills Available">
          {skillsAvail.map(skill => (
            <Typography key={skill} sx={{
              fontFamily: 'monospace',
              fontSize: '0.58rem',
              color: '#484F58',
              mb: '2px',
            }}>
              · {skill}
            </Typography>
          ))}
        </PanelSection>
      )}
      {onNavigate && (
        <Box sx={{ mt: 1 }}>
          <CrossLink label="MODEL" onClick={() => onNavigate('MODEL')} />
          <CrossLink label="DECISION" onClick={() => onNavigate('DECISION')} />
        </Box>
      )}
    </Box>
  );
}

function DecisionPanel({ identity, copilotTurn, analysisResult, onNavigate }: {
  identity: ArtifactIdentity;
  copilotTurn: CopilotTurnResponse | null;
  analysisResult: AnalysisResult | null;
  onNavigate?: (s: JourneyStage) => void;
}) {
  const proposalId = identity.proposal_id ?? copilotTurn?.act_proposal_id ?? null;
  const decisionId = identity.decision_id ?? copilotTurn?.act_decision_id ?? null;

  const recs = copilotTurn?.recommendations ?? analysisResult?.assessment?.recommendations ?? [];

  if (!proposalId && !decisionId && !recs.length) { return <EmptyPanel stage="DECISION" />; }

  return (
    <Box>
      <PanelSection title="Decision Artifacts">
        <FieldRow label="proposal_id" value={proposalId} />
        <FieldRow label="decision_id" value={decisionId} />
        <FieldRow label="pending_approval_id" value={copilotTurn?.act_pending_approval_id} />
        <FieldRow label="decision_outcome" value={copilotTurn?.act_decision_outcome} />
        <FieldRow label="approval_required" value={
          copilotTurn?.act_approval_required !== undefined
            ? String(copilotTurn.act_approval_required)
            : undefined
        } />
      </PanelSection>
      {recs.length > 0 && (
        <PanelSection title={`Recommendations (${recs.length})`}>
          {recs.slice(0, 3).map((r, i) => (
            <Box key={i} sx={{ mb: 0.75, pl: 1, borderLeft: '2px solid #21262D' }}>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#8B949E' }}>
                {r.domain.toUpperCase()} · {r.capability}
              </Typography>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#6E7681' }}>
                {r.target}
              </Typography>
            </Box>
          ))}
          {recs.length > 3 && (
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.52rem', color: '#484F58' }}>
              +{recs.length - 3} more
            </Typography>
          )}
        </PanelSection>
      )}
      {onNavigate && (
        <Box sx={{ mt: 1 }}>
          <CrossLink label="SKILLS" onClick={() => onNavigate('SKILLS')} />
          <CrossLink label="EXECUTION" onClick={() => onNavigate('EXECUTION')} />
        </Box>
      )}
    </Box>
  );
}

function ExecutionPanel({ identity, copilotTurn, onNavigate }: {
  identity: ArtifactIdentity;
  copilotTurn: CopilotTurnResponse | null;
  onNavigate?: (s: JourneyStage) => void;
}) {
  const executionId = identity.execution_id ?? copilotTurn?.act_execution_id ?? null;

  if (!executionId) { return <EmptyPanel stage="EXECUTION" />; }

  return (
    <Box>
      <PanelSection title="Execution Record">
        <FieldRow label="execution_id" value={executionId} />
        <FieldRow label="execution_status" value={copilotTurn?.act_execution_status} />
        <FieldRow label="mutation_state" value={copilotTurn?.act_mutation_state} />
        {(copilotTurn?.act_violations ?? []).length > 0 && (
          <Box sx={{ mt: 0.5 }}>
            {(copilotTurn!.act_violations ?? []).map((v, i) => (
              <Typography key={i} sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#F85149' }}>
                VIOLATION [{v.code}]: {v.message}
              </Typography>
            ))}
          </Box>
        )}
      </PanelSection>
      {onNavigate && (
        <Box sx={{ mt: 1 }}>
          <CrossLink label="DECISION" onClick={() => onNavigate('DECISION')} />
          <CrossLink label="OUTCOME" onClick={() => onNavigate('OUTCOME')} />
        </Box>
      )}
    </Box>
  );
}

function OutcomePanel({ copilotTurn, analysisResult, onNavigate }: {
  copilotTurn: CopilotTurnResponse | null;
  analysisResult: AnalysisResult | null;
  onNavigate?: (s: JourneyStage) => void;
}) {
  const confirmed = copilotTurn?.observe_execution_confirmed;
  const improved = copilotTurn?.observe_operational_improved;
  const summary = copilotTurn?.observe_operational_summary;
  const delta = analysisResult?.kpi_delta ?? null;

  if (confirmed === undefined && !summary && !delta) { return <EmptyPanel stage="OUTCOME" />; }

  return (
    <Box>
      <PanelSection title="Operational Outcome">
        {confirmed !== undefined && (
          <FieldRow label="execution_confirmed" value={String(confirmed)} />
        )}
        {improved !== undefined && (
          <FieldRow label="operational_improved" value={String(improved)} />
        )}
        {summary && (
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#C9D1D9', mb: 1 }}>
            {summary}
          </Typography>
        )}
      </PanelSection>
      {delta && (
        <PanelSection title="KPI Delta">
          {(Object.entries(delta) as [string, number][])
            .filter(([, v]) => v !== 0 && v !== null)
            .slice(0, 6)
            .map(([k, v]) => (
              <FieldRow
                key={k}
                label={k}
                value={`${v > 0 ? '+' : ''}${typeof v === 'number' ? v.toFixed(2) : v}`}
              />
            ))}
        </PanelSection>
      )}
      {onNavigate && (
        <Box sx={{ mt: 1 }}>
          <CrossLink label="EXECUTION" onClick={() => onNavigate('EXECUTION')} />
          <CrossLink label="CONTEXT" onClick={() => onNavigate('CONTEXT')} />
        </Box>
      )}
    </Box>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function DeveloperJourneyPanel({
  activeStage,
  identity,
  analysisResult,
  copilotTurn,
  demoStatus,
  agentTask,
  onNavigateToStage,
}: DeveloperJourneyPanelProps) {
  return (
    <Box
      data-testid={`journey-panel-${activeStage}`}
      sx={{
        flex: 1,
        overflow: 'auto',
        px: 1.5,
        py: 1,
      }}
    >
      {activeStage === 'CONTEXT' && (
        <ContextPanel
          identity={identity}
          copilotTurn={copilotTurn}
          demoStatus={demoStatus}
          onNavigate={onNavigateToStage}
        />
      )}
      {activeStage === 'AGENT' && (
        <AgentPanel
          identity={identity}
          agentTask={agentTask}
          copilotTurn={copilotTurn}
          onNavigate={onNavigateToStage}
        />
      )}
      {activeStage === 'MODEL' && (
        <ModelPanel
          identity={identity}
          analysisResult={analysisResult}
          copilotTurn={copilotTurn}
          onNavigate={onNavigateToStage}
        />
      )}
      {activeStage === 'SKILLS' && (
        <SkillsPanel
          copilotTurn={copilotTurn}
          onNavigate={onNavigateToStage}
        />
      )}
      {activeStage === 'DECISION' && (
        <DecisionPanel
          identity={identity}
          copilotTurn={copilotTurn}
          analysisResult={analysisResult}
          onNavigate={onNavigateToStage}
        />
      )}
      {activeStage === 'EXECUTION' && (
        <ExecutionPanel
          identity={identity}
          copilotTurn={copilotTurn}
          onNavigate={onNavigateToStage}
        />
      )}
      {activeStage === 'OUTCOME' && (
        <OutcomePanel
          copilotTurn={copilotTurn}
          analysisResult={analysisResult}
          onNavigate={onNavigateToStage}
        />
      )}
    </Box>
  );
}
