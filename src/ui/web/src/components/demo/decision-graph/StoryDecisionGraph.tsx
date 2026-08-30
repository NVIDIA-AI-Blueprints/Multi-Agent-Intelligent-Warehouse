/**
 * StoryDecisionGraph — horizontal lane-based "Story Graph" view for the Decision Graph (Phase 13C.1).
 *
 * Maps buildDecisionGraph() output onto 6 semantic regions rendered as CSS flex lanes:
 *
 *   SITUATION → INTELLIGENCE → RESPONSE → GOVERNANCE → ACTION → OUTCOME
 *
 * No SVG positioning. Simple CSS flex layout with right-arrow connectors between lanes.
 *
 * Rendering varies by SemanticZoomLevel:
 *   OVERVIEW  (<0.6)   : Header + one-line summary per lane only
 *   STANDARD  (0.6–1.0): Structured semantic cards; skills collapsed by default
 *   DETAIL    (>1.0)   : All individual node cards with IDs + full metadata
 */

import React, { useState, useMemo } from 'react';
import { Box, Typography } from '@mui/material';
import { DecisionGraph, DecisionGraphNode, DecisionGraphNodeType } from './graphTypes';
import { SemanticZoomLevel } from './semanticZoom';

// ── Design tokens ─────────────────────────────────────────────────────────────

const LANE_WIDTH        = 220;
const ARROW_WIDTH       = 40;
const LANE_BG           = '#0D1117';
const LANE_HEADER_BG    = '#161B22';
const INACTIVE_BORDER   = '#21262D';

// ── Region definitions ─────────────────────────────────────────────────────────

interface RegionDef {
  id: string;
  index: number;
  title: string;
  accentColor: string;
  nodeTypes: DecisionGraphNodeType[];
}

const REGION_DEFS: RegionDef[] = [
  {
    id: 'situation',
    index: 1,
    title: 'SITUATION',
    accentColor: '#A371F7',
    nodeTypes: ['evidence'],
  },
  {
    id: 'intelligence',
    index: 2,
    title: 'INTELLIGENCE',
    accentColor: '#3FB950',
    nodeTypes: ['agent', 'model_gateway', 'model', 'skill', 'assessment'],
  },
  {
    id: 'response',
    index: 3,
    title: 'RESPONSE',
    accentColor: '#58A6FF',
    nodeTypes: ['recommendation', 'proposal'],
  },
  {
    id: 'governance',
    index: 4,
    title: 'GOVERNANCE',
    accentColor: '#D29922',
    nodeTypes: ['decision_engine', 'decision', 'approval'],
  },
  {
    id: 'action',
    index: 5,
    title: 'ACTION',
    accentColor: '#F85149',
    nodeTypes: ['executor', 'mcp', 'execution', 'reconciliation'],
  },
  {
    id: 'outcome',
    index: 6,
    title: 'OUTCOME',
    accentColor: '#3FB950',
    nodeTypes: ['outcome'],
  },
];

interface StoryRegion extends RegionDef {
  nodes: DecisionGraphNode[];
  isActive: boolean;
}

// ── Utility helpers ───────────────────────────────────────────────────────────

function truncate(s: string | null | undefined, maxLen: number): string {
  if (!s) return '';
  return s.length > maxLen ? s.slice(0, maxLen) + '…' : s;
}

function nodesByType(nodes: DecisionGraphNode[], type: DecisionGraphNodeType): DecisionGraphNode[] {
  return nodes.filter(n => n.type === type);
}

function metaStr(node: DecisionGraphNode, key: string): string {
  const v = node.metadata?.[key];
  return v !== null && v !== undefined ? String(v) : '';
}

// ── Shared mini-components ────────────────────────────────────────────────────

interface MiniCardProps {
  label: string;
  typeLabel?: string;
  accentColor?: string;
  selected?: boolean;
  onClick?: () => void;
  testId?: string;
}

function MiniCard({ label, typeLabel, accentColor = '#484F58', selected = false, onClick, testId }: MiniCardProps) {
  return (
    <Box
      data-testid={testId}
      onClick={onClick}
      sx={{
        background: '#161B22',
        border: `1px solid ${selected ? accentColor : INACTIVE_BORDER}`,
        borderRadius: '4px',
        px: '8px',
        py: '5px',
        mb: '4px',
        cursor: onClick ? 'pointer' : 'default',
        '&:hover': onClick ? { borderColor: accentColor } : {},
      }}
    >
      {typeLabel && (
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.42rem', color: accentColor, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          {typeLabel}
        </Typography>
      )}
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: '#C9D1D9', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {label}
      </Typography>
    </Box>
  );
}

function StatusBadge({ status }: { status: string }) {
  const color = status === 'executed' || status === 'done' ? '#3FB950'
    : status === 'failed' || status === 'error'  ? '#F85149'
    : status === 'unknown'                        ? '#D29922'
    : '#484F58';
  return (
    <Box component="span" sx={{
      fontFamily: 'monospace',
      fontSize: '0.42rem',
      fontWeight: 700,
      color,
      border: `1px solid ${color}44`,
      borderRadius: '3px',
      px: '4px',
      py: '1px',
      textTransform: 'uppercase',
      letterSpacing: '0.06em',
    }}>
      {status}
    </Box>
  );
}

// ── Per-region content renderers ───────────────────────────────────────────────

interface ContentProps {
  region: StoryRegion;
  zoomLevel: SemanticZoomLevel;
  skillsExpanded: boolean;
  onToggleSkills: () => void;
  approvalsExpanded: boolean;
  onToggleApprovals: () => void;
  selectedNodeId: string | null;
  onNodeClick: (nodeId: string) => void;
}

// ── SITUATION ─────────────────────────────────────────────────────────────────

function SituationContent({ region, zoomLevel, selectedNodeId, onNodeClick }: ContentProps) {
  const { nodes } = region;
  const kpiNodes  = nodes.filter(n => n.label !== 'observed_fact');
  const factNodes = nodes.filter(n => n.label === 'observed_fact');

  if (zoomLevel === 'OVERVIEW') {
    return (
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#8B949E' }}>
        {nodes.length} evidence node{nodes.length !== 1 ? 's' : ''}
      </Typography>
    );
  }

  // STANDARD + DETAIL
  return (
    <Box>
      <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px', mb: '6px' }}>
        {kpiNodes.map(n => (
          <Box
            key={n.id}
            onClick={() => onNodeClick(n.id)}
            sx={{
              background: '#161B22',
              border: `1px solid ${selectedNodeId === n.id ? '#A371F7' : INACTIVE_BORDER}`,
              borderRadius: '4px',
              px: '6px',
              py: '5px',
              cursor: 'pointer',
              '&:hover': { borderColor: '#A371F7' },
            }}
          >
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.42rem', color: '#484F58', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              {n.label.replace(/_/g, ' ')}
            </Typography>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#C9D1D9', fontWeight: 700 }}>
              {n.subtitle ?? '—'}
            </Typography>
          </Box>
        ))}
      </Box>
      {factNodes.slice(0, 2).map(n => (
        <Typography key={n.id} sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#484F58', mt: '2px' }}>
          • {n.subtitle}
        </Typography>
      ))}
    </Box>
  );
}

// ── INTELLIGENCE ───────────────────────────────────────────────────────────────

function IntelligenceContent({ region, zoomLevel, skillsExpanded, onToggleSkills, selectedNodeId, onNodeClick }: ContentProps) {
  const { nodes } = region;
  const agentNode      = nodesByType(nodes, 'agent')[0]        ?? null;
  const mgwNode        = nodesByType(nodes, 'model_gateway')[0] ?? null;
  const modelNode      = nodesByType(nodes, 'model')[0]        ?? null;
  const skillNodes     = nodesByType(nodes, 'skill');
  const assessmentNode = nodesByType(nodes, 'assessment')[0]   ?? null;

  const skillDomains = skillNodes
    .map(n => n.subtitle ?? n.label)
    .filter(Boolean)
    .join(', ');

  if (zoomLevel === 'OVERVIEW') {
    return (
      <Box>
        {agentNode && (
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#8B949E', mb: '2px' }}>
            {agentNode.label}
          </Typography>
        )}
        {skillNodes.length > 0 && (
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#39D2C0' }}>
            {skillNodes.length} capabilities: {skillDomains}
          </Typography>
        )}
        {assessmentNode && (
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#8B949E', mt: '2px' }}>
            assessment: {assessmentNode.subtitle}
          </Typography>
        )}
      </Box>
    );
  }

  // STANDARD + DETAIL
  return (
    <Box>
      {agentNode && (
        <MiniCard
          label={agentNode.label}
          typeLabel="agent"
          accentColor="#3FB950"
          selected={selectedNodeId === agentNode.id}
          onClick={() => onNodeClick(agentNode.id)}
          testId={`graph-node-${agentNode.id}`}
        />
      )}
      {mgwNode && (
        <MiniCard
          label={mgwNode.label}
          typeLabel="model gateway"
          accentColor="#58A6FF"
          selected={selectedNodeId === mgwNode.id}
          onClick={() => onNodeClick(mgwNode.id)}
          testId={`graph-node-${mgwNode.id}`}
        />
      )}
      {modelNode && (
        <MiniCard
          label={truncate(modelNode.label, 26)}
          typeLabel="model"
          accentColor="#58A6FF"
          selected={selectedNodeId === modelNode.id}
          onClick={() => onNodeClick(modelNode.id)}
          testId={`graph-node-${modelNode.id}`}
        />
      )}

      {/* Skills — collapsed by default */}
      {skillNodes.length > 0 && (
        <Box sx={{ mb: '4px' }}>
          <Box
            onClick={onToggleSkills}
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              cursor: 'pointer',
              background: '#0D1E1D',
              border: `1px solid #39D2C044`,
              borderRadius: '4px',
              px: '8px',
              py: '4px',
              '&:hover': { borderColor: '#39D2C0' },
            }}
          >
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.45rem', color: '#39D2C0' }}>
              {skillsExpanded ? '▾' : '▸'}
            </Typography>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#39D2C0' }}>
              {skillNodes.length} capabilities: {skillDomains}
            </Typography>
          </Box>
          {skillsExpanded && skillNodes.map(n => (
            <Box
              key={n.id}
              onClick={() => onNodeClick(n.id)}
              sx={{
                fontFamily: 'monospace',
                fontSize: '0.5rem',
                color: '#C9D1D9',
                pl: '12px',
                py: '2px',
                cursor: 'pointer',
                '&:hover': { color: '#39D2C0' },
              }}
            >
              {n.label}
            </Box>
          ))}
        </Box>
      )}

      {/* Assessment */}
      {assessmentNode && (
        <Box
          onClick={() => onNodeClick(assessmentNode.id)}
          sx={{
            cursor: 'pointer',
            background: '#161B22',
            border: `1px solid ${selectedNodeId === assessmentNode.id ? '#8B949E' : INACTIVE_BORDER}`,
            borderRadius: '4px',
            px: '8px',
            py: '6px',
            '&:hover': { borderColor: '#8B949E' },
          }}
        >
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.42rem', color: '#8B949E', textTransform: 'uppercase', letterSpacing: '0.08em', mb: '2px' }}>
            ASSESSMENT
          </Typography>
          {metaStr(assessmentNode, 'summary') && (
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#C9D1D9', lineHeight: 1.3 }}>
              {truncate(metaStr(assessmentNode, 'summary'), 80)}
            </Typography>
          )}
          {assessmentNode.subtitle && (
            <Box sx={{ mt: '4px' }}>
              <StatusBadge status={assessmentNode.subtitle} />
            </Box>
          )}
        </Box>
      )}
    </Box>
  );
}

// ── RESPONSE ───────────────────────────────────────────────────────────────────

function ResponseContent({ region, zoomLevel, selectedNodeId, onNodeClick }: ContentProps) {
  const { nodes } = region;
  const recNodes  = nodesByType(nodes, 'recommendation');
  const propNodes = nodesByType(nodes, 'proposal');

  if (zoomLevel === 'OVERVIEW') {
    return (
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#8B949E' }}>
        {propNodes.length} proposal{propNodes.length !== 1 ? 's' : ''}
      </Typography>
    );
  }

  // Pair recs and proposals by column
  const pairs = recNodes.map(rec => ({
    rec,
    prop: propNodes.find(p => p.column === rec.column) ?? null,
  }));
  // Also include proposals with no matching rec
  const unpairedProps = propNodes.filter(p => !recNodes.some(r => r.column === p.column));

  return (
    <Box>
      {pairs.map(({ rec, prop }) => (
        <Box key={rec.id} sx={{ mb: '6px' }}>
          <Box
            onClick={() => onNodeClick(rec.id)}
            sx={{
              cursor: 'pointer',
              background: '#0D1829',
              border: `1px solid ${selectedNodeId === rec.id ? '#58A6FF' : '#21262D'}`,
              borderRadius: '4px 4px 0 0',
              px: '8px',
              py: '5px',
              '&:hover': { borderColor: '#58A6FF' },
            }}
          >
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.42rem', color: '#388BFD', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              AI RECOMMENDATION
            </Typography>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#C9D1D9', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {rec.label}
            </Typography>
          </Box>
          {prop && (
            <Box
              onClick={() => onNodeClick(prop.id)}
              sx={{
                cursor: 'pointer',
                background: '#1E1805',
                border: `1px solid ${selectedNodeId === prop.id ? '#D29922' : '#21262D'}`,
                borderTop: 'none',
                borderRadius: '0 0 4px 4px',
                px: '8px',
                py: '5px',
                '&:hover': { borderColor: '#D29922' },
              }}
            >
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: '2px' }}>
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.42rem', color: '#D29922', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                  ACTION PROPOSAL
                </Typography>
                {prop.subtitle && <StatusBadge status={prop.subtitle} />}
              </Box>
              {prop.artifact_id && (
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.42rem', color: '#484F58', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {prop.artifact_id.slice(0, 12)}
                </Typography>
              )}
            </Box>
          )}
        </Box>
      ))}
      {unpairedProps.map(prop => (
        <MiniCard
          key={prop.id}
          label={prop.label}
          typeLabel="proposal"
          accentColor="#D29922"
          selected={selectedNodeId === prop.id}
          onClick={() => onNodeClick(prop.id)}
        />
      ))}
    </Box>
  );
}

// ── GOVERNANCE ─────────────────────────────────────────────────────────────────

function GovernanceContent({ region, zoomLevel, approvalsExpanded, onToggleApprovals, selectedNodeId, onNodeClick }: ContentProps) {
  const { nodes } = region;
  const decEngineNodes = nodesByType(nodes, 'decision_engine');
  const decisionNodes  = nodesByType(nodes, 'decision');
  const approvalNodes  = nodesByType(nodes, 'approval');

  if (zoomLevel === 'OVERVIEW') {
    const hasApprovals = approvalNodes.length > 0;
    return (
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#8B949E' }}>
        {hasApprovals ? 'REQUIRES APPROVAL' : `${decisionNodes.length} decision${decisionNodes.length !== 1 ? 's' : ''}`}
      </Typography>
    );
  }

  return (
    <Box>
      {/* Decision engine */}
      {decEngineNodes.map(n => (
        <Box
          key={n.id}
          onClick={() => onNodeClick(n.id)}
          sx={{
            cursor: 'pointer',
            background: '#200D0C',
            border: `1px solid ${selectedNodeId === n.id ? '#F85149' : '#F8514944'}`,
            borderRadius: '4px',
            px: '8px',
            py: '5px',
            mb: '4px',
            '&:hover': { borderColor: '#F85149' },
          }}
        >
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.42rem', color: '#F85149', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            DECISION ENGINE
          </Typography>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#8B949E' }}>
            Policy · Risk · State
          </Typography>
        </Box>
      ))}

      {/* Decision outcome badges */}
      {decisionNodes.map(n => (
        <Box
          key={n.id}
          onClick={() => onNodeClick(n.id)}
          sx={{
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: '#161B22',
            border: `1px solid ${selectedNodeId === n.id ? '#8B949E' : INACTIVE_BORDER}`,
            borderRadius: '4px',
            px: '8px',
            py: '4px',
            mb: '4px',
            '&:hover': { borderColor: '#8B949E' },
          }}
        >
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.42rem', color: '#484F58', textTransform: 'uppercase' }}>
            decision
          </Typography>
          <StatusBadge status={n.label} />
        </Box>
      ))}

      {/* Approvals */}
      {approvalNodes.length > 0 && (
        <Box>
          {approvalNodes.length === 1 ? (
            <Box
              onClick={() => onNodeClick(approvalNodes[0].id)}
              sx={{
                cursor: 'pointer',
                background: '#1E1805',
                border: `1px solid ${selectedNodeId === approvalNodes[0].id ? '#D29922' : '#D2992244'}`,
                borderRadius: '4px',
                px: '8px',
                py: '6px',
                '&:hover': { borderColor: '#D29922' },
              }}
            >
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.45rem', color: '#D29922', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', mb: '2px' }}>
                HUMAN AUTHORITY REQUIRED
              </Typography>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#C9D1D9', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {approvalNodes[0].label}
              </Typography>
              {metaStr(approvalNodes[0], 'risk_level') && (
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.42rem', color: '#D29922' }}>
                  risk: {metaStr(approvalNodes[0], 'risk_level')}
                </Typography>
              )}
            </Box>
          ) : (
            <Box>
              <Box
                onClick={onToggleApprovals}
                sx={{
                  cursor: 'pointer',
                  background: '#1E1805',
                  border: `1px solid #D2992244`,
                  borderRadius: '4px',
                  px: '8px',
                  py: '5px',
                  '&:hover': { borderColor: '#D29922' },
                }}
              >
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.45rem', color: '#D29922', fontWeight: 700, textTransform: 'uppercase' }}>
                  {approvalsExpanded ? '▾' : '▸'} HUMAN AUTHORITY REQUIRED
                </Typography>
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#8B949E' }}>
                  {approvalNodes.length} pending approvals
                </Typography>
              </Box>
              {approvalsExpanded && approvalNodes.map(n => (
                <Box
                  key={n.id}
                  onClick={() => onNodeClick(n.id)}
                  sx={{ cursor: 'pointer', pl: '12px', py: '2px', fontFamily: 'monospace', fontSize: '0.5rem', color: '#C9D1D9', '&:hover': { color: '#D29922' } }}
                >
                  {n.label}
                </Box>
              ))}
            </Box>
          )}
        </Box>
      )}
    </Box>
  );
}

// ── ACTION ─────────────────────────────────────────────────────────────────────

function ActionContent({ region, zoomLevel, selectedNodeId, onNodeClick }: ContentProps) {
  const { nodes } = region;
  const executorNodes = nodesByType(nodes, 'executor');
  const mcpNodes      = nodesByType(nodes, 'mcp');
  const execNodes     = nodesByType(nodes, 'execution');
  const reconNodes    = nodesByType(nodes, 'reconciliation');

  if (zoomLevel === 'OVERVIEW') {
    return (
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#8B949E' }}>
        {execNodes.length} execution{execNodes.length !== 1 ? 's' : ''}
      </Typography>
    );
  }

  return (
    <Box>
      {/* Execution boundary divider */}
      <Box sx={{ borderBottom: '1px solid #F85149', mb: '8px', pb: '4px' }}>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.42rem', color: '#F85149', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
          EXECUTION BOUNDARY
        </Typography>
      </Box>

      {/* ActionExecutor */}
      {executorNodes.map(n => (
        <MiniCard
          key={n.id}
          label={n.label}
          typeLabel="executor"
          accentColor="#3FB950"
          selected={selectedNodeId === n.id}
          onClick={() => onNodeClick(n.id)}
        />
      ))}

      {/* MCP */}
      {mcpNodes.map(n => (
        <MiniCard
          key={n.id}
          label={n.label}
          typeLabel="mcp"
          accentColor="#58A6FF"
          selected={selectedNodeId === n.id}
          onClick={() => onNodeClick(n.id)}
        />
      ))}

      {/* Execution results */}
      {execNodes.map(n => (
        <Box
          key={n.id}
          onClick={() => onNodeClick(n.id)}
          sx={{
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: '#161B22',
            border: `1px solid ${selectedNodeId === n.id ? '#8B949E' : INACTIVE_BORDER}`,
            borderRadius: '4px',
            px: '8px',
            py: '4px',
            mb: '4px',
            '&:hover': { borderColor: '#8B949E' },
          }}
        >
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#484F58', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flexGrow: 1, mr: '4px' }}>
            {n.subtitle ?? 'execution'}
          </Typography>
          <StatusBadge status={n.label} />
        </Box>
      ))}

      {/* Reconciliation — always shown explicitly at STANDARD (not collapsed) */}
      {reconNodes.map(n => (
        <Box
          key={n.id}
          onClick={() => onNodeClick(n.id)}
          sx={{
            cursor: 'pointer',
            background: '#1E1805',
            border: `1px solid ${selectedNodeId === n.id ? '#D29922' : '#D2992244'}`,
            borderRadius: '4px',
            px: '8px',
            py: '5px',
            mb: '4px',
            '&:hover': { borderColor: '#D29922' },
          }}
        >
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.45rem', color: '#D29922', fontWeight: 700 }}>
            UNKNOWN → ReconciliationService
          </Typography>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.42rem', color: '#484F58' }}>
            execution status unconfirmed
          </Typography>
        </Box>
      ))}
    </Box>
  );
}

// ── OUTCOME ────────────────────────────────────────────────────────────────────

function OutcomeContent({ region, zoomLevel, selectedNodeId, onNodeClick }: ContentProps) {
  const { nodes } = region;
  const outcomeNode = nodes[0] ?? null;

  if (zoomLevel === 'OVERVIEW') {
    return (
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#8B949E' }}>
        {outcomeNode ? 'outcome recorded' : 'awaiting'}
      </Typography>
    );
  }

  if (!outcomeNode) {
    return (
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#484F58', fontStyle: 'italic' }}>
        AWAITING OBSERVED OUTCOME
      </Typography>
    );
  }

  const meta = outcomeNode.metadata ?? {};

  const kpiRows: Array<{ key: string; label: string; pre: string; post: string; delta: string | null }> = [
    {
      key: 'wave_risk_score',
      label: 'wave risk',
      pre:   meta.pre_wave_risk_score   !== null && meta.pre_wave_risk_score   !== undefined ? String(meta.pre_wave_risk_score)   : '—',
      post:  meta.post_wave_risk_score  !== null && meta.post_wave_risk_score  !== undefined ? String(meta.post_wave_risk_score)  : '—',
      delta: meta.delta_wave_risk_score !== null && meta.delta_wave_risk_score !== undefined ? String(meta.delta_wave_risk_score) : null,
    },
    {
      key: 'pending_backlog',
      label: 'backlog',
      pre:   meta.pre_pending_backlog   !== null && meta.pre_pending_backlog   !== undefined ? String(meta.pre_pending_backlog)   : '—',
      post:  meta.post_pending_backlog  !== null && meta.post_pending_backlog  !== undefined ? String(meta.post_pending_backlog)  : '—',
      delta: meta.delta_pending_backlog !== null && meta.delta_pending_backlog !== undefined ? String(meta.delta_pending_backlog) : null,
    },
    {
      key: 'labor_availability_pct',
      label: 'labor avail',
      pre:   meta.pre_labor_availability_pct   !== null && meta.pre_labor_availability_pct   !== undefined ? String(meta.pre_labor_availability_pct)   : '—',
      post:  meta.post_labor_availability_pct  !== null && meta.post_labor_availability_pct  !== undefined ? String(meta.post_labor_availability_pct)  : '—',
      delta: meta.delta_labor_availability_pct !== null && meta.delta_labor_availability_pct !== undefined ? String(meta.delta_labor_availability_pct) : null,
    },
  ];

  return (
    <Box
      onClick={() => onNodeClick(outcomeNode.id)}
      sx={{ cursor: 'pointer' }}
    >
      <Box sx={{ mb: '8px' }}>
        {kpiRows.map(row => {
          const deltaNum = row.delta !== null ? parseFloat(row.delta) : null;
          const deltaColor = deltaNum !== null
            ? (deltaNum < 0 ? '#3FB950' : deltaNum > 0 ? '#F85149' : '#484F58')
            : '#484F58';
          return (
            <Box key={row.key} sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', py: '2px', borderBottom: `1px solid #1C2128` }}>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.42rem', color: '#484F58', minWidth: 50 }}>
                {row.label}
              </Typography>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: '#8B949E' }}>
                {row.pre} → {row.post}
              </Typography>
              {row.delta !== null && (
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.5rem', color: deltaColor, fontWeight: 700, ml: '4px' }}>
                  {deltaNum !== null && deltaNum > 0 ? '+' : ''}{row.delta}
                </Typography>
              )}
            </Box>
          );
        })}
      </Box>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.42rem', color: '#30363D', textTransform: 'uppercase', letterSpacing: '0.08em', mt: '4px' }}>
        Next Observe →
      </Typography>
    </Box>
  );
}

// ── Dispatcher ─────────────────────────────────────────────────────────────────

function RegionContent(props: ContentProps) {
  switch (props.region.id) {
    case 'situation':    return <SituationContent    {...props} />;
    case 'intelligence': return <IntelligenceContent {...props} />;
    case 'response':     return <ResponseContent     {...props} />;
    case 'governance':   return <GovernanceContent   {...props} />;
    case 'action':       return <ActionContent       {...props} />;
    case 'outcome':      return <OutcomeContent      {...props} />;
    default:             return null;
  }
}

// ── Main component ─────────────────────────────────────────────────────────────

export interface StoryDecisionGraphProps {
  graph: DecisionGraph;
  zoomLevel: SemanticZoomLevel;
  selectedNodeId: string | null;
  onNodeClick: (nodeId: string) => void;
  currentStage?: string;
}

export default function StoryDecisionGraph({
  graph,
  zoomLevel,
  selectedNodeId,
  onNodeClick,
}: StoryDecisionGraphProps) {
  const [skillsExpanded, setSkillsExpanded]       = useState(false);
  const [approvalsExpanded, setApprovalsExpanded] = useState(false);

  const regions: StoryRegion[] = useMemo(() => {
    return REGION_DEFS.map(def => {
      const nodes = graph.nodes.filter(n => (def.nodeTypes as string[]).includes(n.type));
      return { ...def, nodes, isActive: nodes.length > 0 };
    });
  }, [graph.nodes]);

  const activeRegions = regions.filter(r => r.isActive);

  return (
    <Box
      data-testid="story-decision-graph"
      sx={{
        display: 'flex',
        alignItems: 'flex-start',
        overflowX: 'auto',
        pb: 1,
      }}
    >
      {activeRegions.map((region, idx) => (
        <React.Fragment key={region.id}>
          {/* Arrow connector between lanes */}
          {idx > 0 && (
            <Box sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: ARROW_WIDTH,
              flexShrink: 0,
              color: '#30363D',
              fontSize: '1.1rem',
              userSelect: 'none',
            }}>
              →
            </Box>
          )}

          {/* Lane */}
          <Box
            data-testid={`story-region-${region.id}`}
            sx={{
              width: LANE_WIDTH,
              flexShrink: 0,
              background: LANE_BG,
              border: `2px solid ${region.accentColor}`,
              borderRadius: '8px',
              overflow: 'hidden',
            }}
          >
            {/* Lane header */}
            <Box sx={{
              background: LANE_HEADER_BG,
              px: 1.5,
              py: '8px',
              borderBottom: `1px solid ${region.accentColor}44`,
            }}>
              <Typography sx={{
                fontFamily: 'monospace',
                fontSize: '0.5rem',
                fontWeight: 700,
                color: region.accentColor,
                textTransform: 'uppercase',
                letterSpacing: '0.1em',
              }}>
                {String(region.index).padStart(2, '0')} {region.title}
              </Typography>
            </Box>

            {/* Lane content */}
            <Box sx={{ p: 1.5 }}>
              <RegionContent
                region={region}
                zoomLevel={zoomLevel}
                skillsExpanded={skillsExpanded}
                onToggleSkills={() => setSkillsExpanded(prev => !prev)}
                approvalsExpanded={approvalsExpanded}
                onToggleApprovals={() => setApprovalsExpanded(prev => !prev)}
                selectedNodeId={selectedNodeId}
                onNodeClick={onNodeClick}
              />
            </Box>
          </Box>
        </React.Fragment>
      ))}
    </Box>
  );
}
