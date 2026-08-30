/**
 * graphTypes.ts — TypeScript types for the progressive DecisionGraph (Phase 13C).
 *
 * Node sources:
 *   LIVE              — field directly from backend response
 *   DERIVED           — node has no canonical backend field; label is presentational
 *   VALIDATED_ARTIFACT — node represents an artifact validated by the governance layer
 *   LOCAL             — node assembled client-side from multiple backend fields
 */

export type NodeSource = 'LIVE' | 'DERIVED' | 'VALIDATED_ARTIFACT' | 'LOCAL';

export type NodeStatus = 'active' | 'pending' | 'done' | 'error' | 'unknown';

export type DecisionGraphNodeType =
  | 'evidence'
  | 'agent'
  | 'model_gateway'
  | 'model'
  | 'skill'
  | 'assessment'
  | 'recommendation'
  | 'proposal'
  | 'decision_engine'
  | 'decision'
  | 'approval'
  | 'executor'
  | 'mcp'
  | 'execution'
  | 'reconciliation'
  | 'outcome';

export type EdgeRelationship =
  | 'OBSERVED_BY'
  | 'ROUTED_THROUGH'
  | 'USED_SKILL'
  | 'SUPPORTS'
  | 'GENERATED'
  | 'EVALUATED_BY'
  | 'REQUIRES'
  | 'AUTHORIZED'
  | 'EXECUTED_BY'
  | 'INVOKED'
  | 'PRODUCED'
  | 'OBSERVED_AS';

export interface DecisionGraphNode {
  id: string;
  type: DecisionGraphNodeType;
  label: string;
  subtitle?: string;
  status?: NodeStatus;
  source: NodeSource;
  artifact_id?: string;
  metadata?: Record<string, string | number | null | undefined>;
  /** Vertical position (0 = top). */
  layer: number;
  /** Horizontal position within layer (0-based). */
  column: number;
}

export interface DecisionGraphEdge {
  id: string;
  /** node id */
  source: string;
  /** node id */
  target: string;
  relationship: EdgeRelationship;
  status?: NodeStatus;
}

export interface DecisionGraph {
  nodes: DecisionGraphNode[];
  edges: DecisionGraphEdge[];
}

export interface SelectedNodeState {
  selectedNodeId: string | null;
  selectedNode: DecisionGraphNode | null;
  artifact: Record<string, any> | null;
}
