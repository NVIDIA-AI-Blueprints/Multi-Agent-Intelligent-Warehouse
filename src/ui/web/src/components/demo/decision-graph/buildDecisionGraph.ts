/**
 * buildDecisionGraph.ts — pure function that builds a DecisionGraph from runtime data.
 *
 * No React dependencies. No side effects. Safe to unit-test without a DOM.
 *
 * Progressive logic: only nodes for stages ≤ currentStage are included.
 * Future stages are never rendered as placeholders.
 */

import { RailStage, STAGE_ORDER } from '../../../hooks/useDemoLifecycle';
import { DemoStatus, AnalysisResult, PendingApproval } from '../../../services/demoAPI';
import {
  DecisionGraph,
  DecisionGraphNode,
  DecisionGraphEdge,
  NodeSource,
  NodeStatus,
  DecisionGraphNodeType,
  EdgeRelationship,
} from './graphTypes';

// ── Layer constants ────────────────────────────────────────────────────────────

const LAYER_EVIDENCE       = 0;
const LAYER_AGENT          = 1;
const LAYER_MODEL_GATEWAY  = 2;
const LAYER_MODEL          = 3;
const LAYER_SKILLS         = 4;
const LAYER_ASSESSMENT     = 5;
const LAYER_RECOMMENDATION = 6;
const LAYER_PROPOSAL       = 7;
const LAYER_DECISION_ENGINE = 8;
const LAYER_DECISION       = 9;
const LAYER_APPROVAL       = 10;
// Layer 11 = execution boundary visual (no nodes)
const LAYER_EXECUTOR       = 12;
const LAYER_MCP            = 13;
const LAYER_EXECUTION      = 14;
const LAYER_OUTCOME        = 15;
const LAYER_RECONCILIATION = 15; // same as outcome when no reconciliation
const LAYER_OUTCOME_WITH_RECON = 16; // outcome shifts down when reconciliation node present

// ── Stage ordering helper ──────────────────────────────────────────────────────

function stageIndex(stage: RailStage): number {
  return STAGE_ORDER.indexOf(stage);
}

function reachedStage(currentStage: RailStage, target: RailStage): boolean {
  return stageIndex(currentStage) >= stageIndex(target);
}

// ── Node/edge ID helpers ───────────────────────────────────────────────────────

let _idCounter = 0;
function nextId(prefix: string): string {
  return `${prefix}-${++_idCounter}`;
}

function makeNode(
  id: string,
  type: DecisionGraphNodeType,
  label: string,
  source: NodeSource,
  layer: number,
  column: number,
  opts: {
    subtitle?: string;
    status?: NodeStatus;
    artifact_id?: string;
    metadata?: Record<string, string | number | null | undefined>;
  } = {},
): DecisionGraphNode {
  return { id, type, label, source, layer, column, ...opts };
}

function makeEdge(
  sourceId: string,
  targetId: string,
  relationship: EdgeRelationship,
  status?: NodeStatus,
): DecisionGraphEdge {
  const id = `edge-${sourceId}-${targetId}`;
  return { id, source: sourceId, target: targetId, relationship, status };
}

// ── Main export ────────────────────────────────────────────────────────────────

export interface BuildDecisionGraphParams {
  currentStage: RailStage;
  demoStatus: DemoStatus | null;
  analysisResult: AnalysisResult | null;
  pendingApprovals: PendingApproval[];
}

export function buildDecisionGraph(params: BuildDecisionGraphParams): DecisionGraph {
  // Reset counter for deterministic IDs in tests
  _idCounter = 0;

  const { currentStage, demoStatus, analysisResult, pendingApprovals } = params;
  const nodes: DecisionGraphNode[] = [];
  const edges: DecisionGraphEdge[] = [];

  const assessment = analysisResult?.assessment ?? null;
  const lifecycle  = analysisResult?.lifecycle  ?? [];

  // ── OBSERVE: evidence nodes ──────────────────────────────────────────────────

  const kpis = demoStatus?.current_kpis ?? null;
  const evidenceNodeIds: string[] = [];

  if (kpis) {
    const kpiFields: Array<[string, string | number]> = [
      ['wave_risk_score',         kpis.wave_risk_score],
      ['labor_availability_pct',  kpis.labor_availability_pct],
      ['pending_backlog',         kpis.pending_backlog],
      ['equipment_operational_pct', kpis.equipment_operational_pct],
    ];

    kpiFields.forEach(([key, val], col) => {
      const id = `evidence-kpi-${col}`;
      nodes.push(makeNode(
        id, 'evidence', key, 'LIVE', LAYER_EVIDENCE, col,
        {
          subtitle: String(val),
          status: 'done',
          metadata: { [key]: val, source_field: 'current_kpis' },
        },
      ));
      evidenceNodeIds.push(id);
    });
  }

  // Add one summary evidence node from facts_observed (first fact only)
  if (assessment?.facts_observed?.length) {
    const col = evidenceNodeIds.length;
    const id = 'evidence-fact-0';
    nodes.push(makeNode(
      id, 'evidence', 'observed_fact', 'LIVE', LAYER_EVIDENCE, col,
      {
        subtitle: assessment.facts_observed[0],
        status: 'done',
        metadata: { fact: assessment.facts_observed[0], source_field: 'assessment.facts_observed' },
      },
    ));
    evidenceNodeIds.push(id);
  }

  // If no data at all yet, add a placeholder evidence node
  if (evidenceNodeIds.length === 0) {
    const id = 'evidence-placeholder';
    nodes.push(makeNode(
      id, 'evidence', 'warehouse_state', 'LOCAL', LAYER_EVIDENCE, 0,
      { subtitle: 'awaiting snapshot', status: 'pending' },
    ));
    evidenceNodeIds.push(id);
  }

  // ── REASON: agent, model_gateway, model, skills, assessment ─────────────────

  if (!reachedStage(currentStage, 'REASON')) {
    return { nodes, edges };
  }

  // Agent node (DERIVED — only one agent in this system)
  const agentId = 'agent-0';
  nodes.push(makeNode(
    agentId, 'agent', 'OperationsCoordinationAgent', 'DERIVED', LAYER_AGENT, 0,
    {
      subtitle: 'coordination agent',
      status: 'done',
      metadata: { note: 'single-agent system' },
    },
  ));

  // Edges: all evidence → agent
  evidenceNodeIds.forEach(evId => {
    edges.push(makeEdge(evId, agentId, 'OBSERVED_BY', 'done'));
  });

  // ModelGateway node (DERIVED — no canonical backend field)
  const mgwId = 'model-gateway-0';
  nodes.push(makeNode(
    mgwId, 'model_gateway', 'ModelGateway', 'DERIVED', LAYER_MODEL_GATEWAY, 0,
    {
      subtitle: 'model routing',
      status: 'done',
      metadata: { routing_rule: assessment?.routing_rule ?? null },
    },
  ));
  edges.push(makeEdge(agentId, mgwId, 'ROUTED_THROUGH', 'done'));

  // Model node (LIVE from assessment.model_id)
  const modelId = 'model-0';
  nodes.push(makeNode(
    modelId, 'model', assessment?.model_id ?? 'model', 'LIVE', LAYER_MODEL, 0,
    {
      subtitle: assessment?.routing_rule ?? undefined,
      status: 'done',
      metadata: {
        model_id:      assessment?.model_id ?? null,
        routing_rule:  assessment?.routing_rule ?? null,
        routing_reason: assessment?.routing_reason ?? null,
        latency_ms:    assessment?.latency_ms ?? null,
      },
    },
  ));
  edges.push(makeEdge(mgwId, modelId, 'ROUTED_THROUGH', 'done'));

  // Skill nodes from lifecycle[phase=SKILL]
  const skillRecords = lifecycle.filter(r => r.phase === 'SKILL');
  const skillNodeIds: string[] = [];
  skillRecords.forEach((rec, i) => {
    const id = `skill-${i}`;
    nodes.push(makeNode(
      id, 'skill', rec.capability ?? `skill-${i}`, 'LIVE', LAYER_SKILLS, i,
      {
        subtitle: rec.domain ?? undefined,
        status: 'done',
        metadata: {
          capability: rec.capability ?? null,
          target:     rec.target    ?? null,
          domain:     rec.domain    ?? null,
          priority:   rec.priority  ?? null,
        },
      },
    ));
    skillNodeIds.push(id);
    edges.push(makeEdge(modelId, id, 'USED_SKILL', 'done'));
  });

  // Assessment node (LIVE from assessment.summary + severity)
  const assessmentId = 'assessment-0';
  nodes.push(makeNode(
    assessmentId, 'assessment', 'Assessment', 'LIVE', LAYER_ASSESSMENT, 0,
    {
      subtitle: assessment?.severity ?? undefined,
      status: 'done',
      artifact_id: assessment?.snapshot_id ?? undefined,
      metadata: {
        summary:     assessment?.summary  ?? null,
        severity:    assessment?.severity ?? null,
        snapshot_id: assessment?.snapshot_id ?? null,
        assessed_at: assessment?.assessed_at ?? null,
      },
    },
  ));

  // Assessment connects from all skills (or directly from model if no skills)
  if (skillNodeIds.length > 0) {
    skillNodeIds.forEach(skId => {
      edges.push(makeEdge(skId, assessmentId, 'SUPPORTS', 'done'));
    });
  } else {
    edges.push(makeEdge(modelId, assessmentId, 'GENERATED', 'done'));
  }

  // ── PROPOSE: recommendations + proposals ─────────────────────────────────────

  if (!reachedStage(currentStage, 'PROPOSE')) {
    return { nodes, edges };
  }

  const recommendations = assessment?.recommendations ?? [];
  const proposeRecords  = lifecycle.filter(r => r.phase === 'PROPOSE');

  const recNodeIds: string[]      = [];
  const propNodeIds: string[]     = [];
  const propNodeCols: number[]    = [];
  const propIdToNodeId = new Map<string, string>();

  recommendations.forEach((rec, i) => {
    const recNodeId = `recommendation-${i}`;
    nodes.push(makeNode(
      recNodeId, 'recommendation', rec.capability, 'LIVE', LAYER_RECOMMENDATION, i,
      {
        subtitle: rec.priority,
        status: 'done',
        metadata: {
          capability: rec.capability,
          target:     rec.target     ?? null,
          rationale:  rec.rationale  ?? null,
          priority:   rec.priority   ?? null,
          domain:     rec.domain     ?? null,
        },
      },
    ));
    recNodeIds.push(recNodeId);
    edges.push(makeEdge(assessmentId, recNodeId, 'GENERATED', 'done'));

    // Match proposal: by index field if available, else array position
    const matchedProp = proposeRecords.find(p => p.index === i) ?? proposeRecords[i];
    if (matchedProp) {
      const propNodeId = `proposal-${i}`;
      nodes.push(makeNode(
        propNodeId, 'proposal', matchedProp.action ?? `proposal-${i}`, 'LIVE', LAYER_PROPOSAL, i,
        {
          subtitle: matchedProp.risk_level ?? undefined,
          status: 'done',
          artifact_id: matchedProp.proposal_id ?? undefined,
          metadata: {
            proposal_id: matchedProp.proposal_id ?? null,
            action:      matchedProp.action      ?? null,
            risk_level:  matchedProp.risk_level  ?? null,
            index:       matchedProp.index       ?? null,
          },
        },
      ));
      propNodeIds.push(propNodeId);
      propNodeCols.push(i);
      edges.push(makeEdge(recNodeId, propNodeId, 'GENERATED', 'done'));

      if (matchedProp.proposal_id) {
        propIdToNodeId.set(matchedProp.proposal_id, propNodeId);
      }
    }
  });

  // Fallback: proposals without matching recommendations
  proposeRecords.forEach((rec, i) => {
    const matchedByIndex = recNodeIds[rec.index ?? i];
    if (!matchedByIndex) {
      const propNodeId = `proposal-extra-${i}`;
      const col = recommendations.length + i;
      nodes.push(makeNode(
        propNodeId, 'proposal', rec.action ?? `proposal-${i}`, 'LIVE', LAYER_PROPOSAL, col,
        {
          subtitle: rec.risk_level ?? undefined,
          status: 'done',
          artifact_id: rec.proposal_id ?? undefined,
          metadata: {
            proposal_id: rec.proposal_id ?? null,
            action:      rec.action      ?? null,
            risk_level:  rec.risk_level  ?? null,
          },
        },
      ));
      propNodeIds.push(propNodeId);
      propNodeCols.push(col);
      edges.push(makeEdge(assessmentId, propNodeId, 'GENERATED', 'done'));

      if (rec.proposal_id) {
        propIdToNodeId.set(rec.proposal_id, propNodeId);
      }
    }
  });

  // ── DECIDE: decision_engine + decisions ───────────────────────────────────────

  if (!reachedStage(currentStage, 'DECIDE')) {
    return { nodes, edges };
  }

  const decideRecords = lifecycle.filter(r => r.phase === 'DECIDE');

  // Decision engine: center of all proposal columns
  const centerCol = propNodeCols.length > 0
    ? Math.floor((Math.min(...propNodeCols) + Math.max(...propNodeCols)) / 2)
    : 0;

  const decEngineId = 'decision-engine-0';
  nodes.push(makeNode(
    decEngineId, 'decision_engine', 'DecisionEngine', 'DERIVED', LAYER_DECISION_ENGINE, centerCol,
    {
      subtitle: 'governance boundary',
      status: 'done',
      metadata: { note: 'deterministic policy check' },
    },
  ));

  // All proposals → decision_engine
  propNodeIds.forEach(pId => {
    edges.push(makeEdge(pId, decEngineId, 'EVALUATED_BY', 'done'));
  });

  const decNodeIds: string[]   = [];
  const decNodeCols: number[]  = [];
  const decIdToNodeId = new Map<string, string>();

  decideRecords.forEach((rec, i) => {
    // Match to proposal node by proposal_id, then by index
    let col = i;
    if (rec.proposal_id && propIdToNodeId.has(rec.proposal_id)) {
      const matchedPropNode = nodes.find(n => n.id === propIdToNodeId.get(rec.proposal_id));
      if (matchedPropNode) col = matchedPropNode.column;
    } else if (typeof rec.index === 'number' && propNodeCols[rec.index] !== undefined) {
      col = propNodeCols[rec.index];
    }

    const outcome = rec.outcome ?? 'unknown';
    const decNodeId = `decision-${i}`;
    nodes.push(makeNode(
      decNodeId, 'decision', outcome, 'LIVE', LAYER_DECISION, col,
      {
        subtitle: rec.decision_id ?? undefined,
        status:   outcome === 'APPROVED' ? 'done' : outcome === 'REJECTED' ? 'error' : 'pending',
        artifact_id: rec.decision_id ?? undefined,
        metadata: {
          decision_id:   rec.decision_id  ?? null,
          proposal_id:   rec.proposal_id  ?? null,
          outcome:       outcome,
          violations:    rec.violations?.join(', ') ?? null,
        },
      },
    ));
    decNodeIds.push(decNodeId);
    decNodeCols.push(col);
    edges.push(makeEdge(decEngineId, decNodeId, 'GENERATED', 'done'));

    if (rec.decision_id) {
      decIdToNodeId.set(rec.decision_id, decNodeId);
    }
  });

  // Also handle proposal_results decision fallback (when no lifecycle DECIDE records)
  if (decideRecords.length === 0 && analysisResult?.proposal_results?.length) {
    analysisResult.proposal_results.forEach((pr, i) => {
      const col = propNodeCols[i] ?? i;
      const decNodeId = `decision-pr-${i}`;
      nodes.push(makeNode(
        decNodeId, 'decision', pr.status ?? 'unknown', 'LIVE', LAYER_DECISION, col,
        {
          subtitle: pr.decision_id ?? undefined,
          status: pr.status === 'executed' ? 'done' : pr.status === 'failed' ? 'error' : 'pending',
          artifact_id: pr.decision_id ?? undefined,
          metadata: {
            status:      pr.status      ?? null,
            capability:  pr.capability  ?? null,
            proposal_id: pr.proposal_id ?? null,
            decision_id: pr.decision_id ?? null,
          },
        },
      ));
      decNodeIds.push(decNodeId);
      decNodeCols.push(col);
      edges.push(makeEdge(decEngineId, decNodeId, 'GENERATED', 'done'));

      if (pr.decision_id) {
        decIdToNodeId.set(pr.decision_id, decNodeId);
      }
    });
  }

  // ── APPROVE: approval nodes ───────────────────────────────────────────────────

  if (!reachedStage(currentStage, 'APPROVE')) {
    return { nodes, edges };
  }

  if (pendingApprovals.length > 0) {
    pendingApprovals.forEach((pa, i) => {
      // Find matching decision node by decision_id
      let col = i;
      if (pa.decision_id && decIdToNodeId.has(pa.decision_id)) {
        const matchedDecNode = nodes.find(n => n.id === decIdToNodeId.get(pa.decision_id));
        if (matchedDecNode) col = matchedDecNode.column;
      }

      const approvalId = `approval-${i}`;
      nodes.push(makeNode(
        approvalId, 'approval', pa.capability, 'LIVE', LAYER_APPROVAL, col,
        {
          // Gap G7: approval_id not in pending_approvals listing — use pending_id
          subtitle: `pending: ${pa.pending_id}`,
          status: 'pending',
          artifact_id: pa.pending_id,
          metadata: {
            pending_id:  pa.pending_id  ?? null,
            proposal_id: pa.proposal_id ?? null,
            decision_id: pa.decision_id ?? null,
            capability:  pa.capability  ?? null,
            risk_level:  pa.risk_level  ?? null,
            priority:    pa.priority    ?? null,
            target:      pa.target      ?? null,
            queued_at:   pa.queued_at   ?? null,
          },
        },
      ));

      // Edge from matching decision node
      const matchedDecNodeId = pa.decision_id ? decIdToNodeId.get(pa.decision_id) : undefined;
      const fromDecId = matchedDecNodeId ?? (decNodeIds[i] ?? decEngineId);
      edges.push(makeEdge(fromDecId, approvalId, 'REQUIRES', 'pending'));
    });
  }

  // ── EXECUTE: executor, mcp, execution nodes ───────────────────────────────────

  if (!reachedStage(currentStage, 'EXECUTE')) {
    return { nodes, edges };
  }

  const proposalResults = analysisResult?.proposal_results ?? [];

  const executorId = 'executor-0';
  nodes.push(makeNode(
    executorId, 'executor', 'ActionExecutor', 'DERIVED', LAYER_EXECUTOR, 0,
    {
      subtitle: 'execution boundary',
      status: 'done',
      metadata: { note: 'post-governance executor' },
    },
  ));

  const mcpId = 'mcp-0';
  nodes.push(makeNode(
    mcpId, 'mcp', 'MCP Capability', 'DERIVED', LAYER_MCP, 0,
    {
      subtitle: 'tool invocation',
      status: 'done',
      metadata: { note: 'model context protocol' },
    },
  ));
  edges.push(makeEdge(executorId, mcpId, 'INVOKED', 'done'));

  // Connect approved decision nodes to executor
  // If no decision nodes, connect from engine
  const approvedDecIds = decNodeIds.length > 0 ? decNodeIds : [decEngineId];
  approvedDecIds.forEach(decId => {
    edges.push(makeEdge(decId, executorId, 'AUTHORIZED', 'done'));
  });

  let hasReconciliation = false;
  const execNodeIds: string[] = [];

  proposalResults.forEach((pr, i) => {
    // Match column to proposal node by proposal_id or index
    let col = i;
    if (pr.proposal_id && propIdToNodeId.has(pr.proposal_id)) {
      const matchedProp = nodes.find(n => n.id === propIdToNodeId.get(pr.proposal_id));
      if (matchedProp) col = matchedProp.column;
    } else if (propNodeCols[i] !== undefined) {
      col = propNodeCols[i];
    }

    const execId = `execution-${i}`;
    const status = pr.status?.toLowerCase() as NodeStatus | undefined;
    nodes.push(makeNode(
      execId, 'execution', pr.status ?? 'unknown', 'LIVE', LAYER_EXECUTION, col,
      {
        subtitle: pr.capability ?? undefined,
        status:   pr.status === 'executed' ? 'done' : pr.status === 'failed' ? 'error' : 'pending',
        artifact_id: pr.execution_id ?? undefined,
        metadata: {
          execution_id: pr.execution_id ?? null,
          status:       pr.status       ?? null,
          capability:   pr.capability   ?? null,
          proposal_id:  pr.proposal_id  ?? null,
        },
      },
    ));
    execNodeIds.push(execId);
    edges.push(makeEdge(mcpId, execId, 'PRODUCED', 'done'));

    // UNKNOWN reconciliation
    if (pr.status === 'unknown' || pr.status === 'UNKNOWN') {
      hasReconciliation = true;
      const reconId = `reconciliation-${i}`;
      nodes.push(makeNode(
        reconId, 'reconciliation', 'reconciliation', 'LIVE', LAYER_RECONCILIATION, col,
        {
          subtitle: 'status unknown',
          status: 'unknown',
          metadata: {
            execution_id: pr.execution_id ?? null,
            note:         'execution status unconfirmed',
          },
        },
      ));
      // No retry edge — just produced
      edges.push(makeEdge(execId, reconId, 'PRODUCED', 'unknown'));
    }
  });

  // If no proposal results, add a placeholder execution
  if (proposalResults.length === 0) {
    const execId = 'execution-placeholder';
    nodes.push(makeNode(
      execId, 'execution', 'pending', 'LOCAL', LAYER_EXECUTION, 0,
      { subtitle: 'awaiting execution', status: 'pending' },
    ));
    execNodeIds.push(execId);
    edges.push(makeEdge(mcpId, execId, 'PRODUCED', 'pending'));
  }

  // ── OUTCOME: KPI delta node ───────────────────────────────────────────────────

  if (!reachedStage(currentStage, 'OUTCOME')) {
    return { nodes, edges };
  }

  const preKpis  = analysisResult?.pre_kpis  ?? null;
  const postKpis = analysisResult?.post_kpis ?? null;
  const kpiDelta = analysisResult?.kpi_delta ?? null;

  // Outcome layer shifts if reconciliation nodes are present
  const outcomeLayer = hasReconciliation ? LAYER_OUTCOME_WITH_RECON : LAYER_OUTCOME;

  // Center column relative to all execution nodes
  const allExecCols = execNodeIds
    .map(id => nodes.find(n => n.id === id)?.column ?? 0);
  const outcomeCenterCol = allExecCols.length > 0
    ? Math.floor((Math.min(...allExecCols) + Math.max(...allExecCols)) / 2)
    : 0;

  const outcomeId = 'outcome-0';
  nodes.push(makeNode(
    outcomeId, 'outcome', 'Observed Outcome', 'LIVE', outcomeLayer, outcomeCenterCol,
    {
      subtitle: kpiDelta ? 'KPI delta available' : 'post-execution state',
      status: 'done',
      metadata: {
        pre_wave_risk_score:        preKpis?.wave_risk_score         ?? null,
        post_wave_risk_score:       postKpis?.wave_risk_score        ?? null,
        delta_wave_risk_score:      kpiDelta?.wave_risk_score        ?? null,
        pre_pending_backlog:        preKpis?.pending_backlog         ?? null,
        post_pending_backlog:       postKpis?.pending_backlog        ?? null,
        delta_pending_backlog:      kpiDelta?.pending_backlog        ?? null,
        pre_labor_availability_pct: preKpis?.labor_availability_pct ?? null,
        post_labor_availability_pct: postKpis?.labor_availability_pct ?? null,
        delta_labor_availability_pct: kpiDelta?.labor_availability_pct ?? null,
      },
    },
  ));

  // Edges: all execution nodes → outcome (or reconciliation nodes if present)
  execNodeIds.forEach(execId => {
    edges.push(makeEdge(execId, outcomeId, 'OBSERVED_AS', 'done'));
  });

  return { nodes, edges };
}
