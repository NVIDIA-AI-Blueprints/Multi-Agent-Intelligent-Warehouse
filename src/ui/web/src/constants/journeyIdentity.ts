/**
 * journeyIdentity.ts — Canonical developer journey constants.
 *
 * The developer journey is the end-to-end provenance path:
 *   Context → Agent/SOP → Model → Skills → Decision → Execution → Outcome
 *
 * Each stage maps to a canonical artifact and an exact identifier.
 * Cross-links between stages must always carry exact IDs — no "latest" heuristics.
 *
 * SECURITY: This module never exposes credentials, bearer tokens, raw prompts,
 * chain-of-thought, or hidden reasoning state. Structured artifacts only.
 */

// ── Stage enumeration ─────────────────────────────────────────────────────────

export const JOURNEY_STAGES = [
  'CONTEXT',
  'AGENT',
  'MODEL',
  'SKILLS',
  'DECISION',
  'EXECUTION',
  'OUTCOME',
] as const;

export type JourneyStage = (typeof JOURNEY_STAGES)[number];

// Human-readable labels used in the rail.
export const JOURNEY_STAGE_LABEL: Record<JourneyStage, string> = {
  CONTEXT:   'Context',
  AGENT:     'Agent/SOP',
  MODEL:     'Model',
  SKILLS:    'Skills',
  DECISION:  'Decision',
  EXECUTION: 'Execution',
  OUTCOME:   'Outcome',
};

// ── Artifact availability ─────────────────────────────────────────────────────

export type JourneyStageStatus =
  | 'available'   // artifact present and viewable
  | 'current'     // the stage the developer is currently viewing
  | 'pending'     // lifecycle has not reached this stage yet
  | 'unavailable';// artifact does not exist for this interaction

// ── Artifact identity chain ───────────────────────────────────────────────────

/**
 * ArtifactIdentity — the canonical ID set for one developer journey instance.
 *
 * Every cross-link must include the relevant IDs from this record.
 * Absent IDs mean the artifact was not produced for this interaction.
 */
export interface ArtifactIdentity {
  // Copilot / conversation lineage
  conversation_id?: string;
  turn_id?: string;
  trace_id?: string;

  // Context
  context_snapshot_id?: string;
  warehouse_id?: string;

  // Agent / SOP
  agent_task_id?: string;
  agent_id?: string;
  sop_id?: string;
  sop_version?: string;
  runtime?: string;

  // Model
  model_id?: string;
  routing_rule?: string;

  // Decision
  proposal_id?: string;
  decision_id?: string;

  // Execution
  execution_id?: string;
}

// ── Intent-specific partial journey maps ─────────────────────────────────────

/**
 * Maps Copilot intent types to the journey stages they produce.
 * Stages not in this set are not available for that intent type.
 */
export const INTENT_JOURNEY_STAGES: Record<string, JourneyStage[]> = {
  // ASK: context-grounded Q&A — no SOP, no proposal, no execution
  ASK: ['CONTEXT', 'MODEL'],

  // ANALYZE: structured analysis — agent + SOP + model + skills, ends at recommendation
  ANALYZE: ['CONTEXT', 'AGENT', 'MODEL', 'SKILLS', 'DECISION'],

  // ACT: full lifecycle — all stages
  ACT: ['CONTEXT', 'AGENT', 'MODEL', 'SKILLS', 'DECISION', 'EXECUTION', 'OUTCOME'],

  // OBSERVE_OUTCOME: post-execution inspection
  OBSERVE_OUTCOME: ['EXECUTION', 'OUTCOME'],
};

// ── Chain-of-thought exclusion invariant ──────────────────────────────────────

/**
 * Fields that must NEVER appear in any developer journey panel.
 *
 * These are listed here as a documentation and test anchor — not enforced
 * by type system alone. Tests in ux1e.test.tsx verify these strings never
 * appear in rendered developer journey output.
 */
export const CHAIN_OF_THOUGHT_EXCLUDED_FIELDS = [
  'chain_of_thought',
  'scratchpad',
  'hidden_reasoning',
  'reasoning_tokens',
  'raw_react_messages',
  'langraph_private_state',
  'hidden_prompts',
] as const;

export type ExcludedCoTField = (typeof CHAIN_OF_THOUGHT_EXCLUDED_FIELDS)[number];
