# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 15 Copilot typed contracts.

Identity model
--------------
conversation_id  One operator Copilot session (drawer open → close / reset)
turn_id          One operator message + one Copilot response
trace_id         One MAIW reasoning trace (threaded to ModelGateway + proposals)

These are never the same value. A three-turn conversation has one
conversation_id and three (turn_id, trace_id) pairs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Intent ────────────────────────────────────────────────────────────────────

class CopilotIntent(str, Enum):
    ASK     = "ask"      # read-only explanation — no proposal, no execution
    ANALYZE = "analyze"  # assessment + recommendations — no mutation
    ACT     = "act"      # ActionProposal → DecisionEngine → governed lifecycle


class MutationState(str, Enum):
    NOT_ATTEMPTED = "NOT_ATTEMPTED"  # no write attempted (pre-approval or blocked)
    CONFIRMED     = "CONFIRMED"      # execution confirmed by ActionExecutor
    UNKNOWN       = "UNKNOWN"        # write may have occurred — reconciliation required


# ── Structured evidence ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class EvidenceFact:
    label: str
    value: str
    severity: str | None = None  # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | None


@dataclass(frozen=True)
class ContextNeighborhood:
    """Bounded Operational Graph neighborhood resolved for the turn."""
    focus_entity_id: str | None
    focus_entity_label: str | None
    entity_ids: list[str]
    relationship_summary: dict[str, list[str]]  # e.g. {"Tasks": [...], "Workers": [...]}
    max_depth: int
    graph_available: bool
    entity_resolution: Any | None = None  # EntityResolution from context.py


# ── ASK result ────────────────────────────────────────────────────────────────

@dataclass
class CopilotAskResult:
    """
    Structured result of a Copilot ASK turn.

    MUST contain zero ActionProposals, zero DecisionEngine evaluations,
    zero writes. These are enforced by architecture invariant tests.

    Answerability
    -------------
    answerability = "answerable"           — state present, answer grounded
    answerability = "insufficient_evidence" — state absent or all-zero; refused
    answerability = "partial"              — some domains missing; answer may be incomplete

    skills_used vs skills_available
    --------------------------------
    skills_used       — capabilities actually invoked during this turn (empty for ASK)
    skills_available  — capabilities the agent reported as reachable
    """
    answer: str
    evidence: list[EvidenceFact]
    neighborhood: ContextNeighborhood
    agent: str
    skills_used: list[str]           # actually invoked — always [] for ASK
    skills_available: list[str]      # agent-reported reachable capabilities
    model_id: str
    reasoning_level: str
    routing_rule: str
    routing_reason: str
    trace_id: str
    snapshot_id: str
    warehouse_id: str
    latency_ms: float
    degraded: bool = False
    degradation_reason: str | None = None
    requested_role: str | None = None
    selected_role: str | None = None
    fallback_from: str | None = None
    fallback_reason: str | None = None
    answerability: str = "answerable"          # "answerable" | "insufficient_evidence" | "partial"
    missing_context: list[str] = field(default_factory=list)  # e.g. ["wave_state", "labor_state"]
    timing: dict[str, float] = field(default_factory=dict)   # state_assembly_ms, graph_lookup_ms, model_inference_ms, total_ms


# ── ANALYZE result ────────────────────────────────────────────────────────────

@dataclass
class RecommendedActionResult:
    """
    A single recommendation from a Copilot ANALYZE turn.

    Carries all RecommendedAction fields plus provenance fields needed for
    future ACT stale-state detection. Does NOT contain ActionProposal,
    proposal_id, decision_id, approval_id, or execution_id.
    """
    recommendation_id: str              # durable ID within this conversation
    domain: str
    capability: str
    target: str
    objective: str
    rationale: str
    priority: str
    subtype: str | None
    # Provenance (needed for 15D ACT stale-state check)
    conversation_id: str
    turn_id: str
    trace_id: str
    snapshot_id: str
    focus_entity_id: str | None


@dataclass
class CopilotAnalyzeResult:
    """
    Structured result of a Copilot ANALYZE turn.

    MUST contain zero ActionProposals, zero DecisionEngine evaluations,
    zero writes. These are enforced by architecture invariant tests.

    The safety invariant 'No warehouse changes have been made.' must be
    communicated to the operator via the API response / UI.
    """
    summary: str
    severity: str
    evidence: list[EvidenceFact]
    recommendations: list[RecommendedActionResult]
    neighborhood: ContextNeighborhood
    agent: str
    skills_used: list[str]
    skills_available: list[str]
    model_id: str
    reasoning_level: str
    routing_rule: str
    routing_reason: str
    trace_id: str
    snapshot_id: str
    warehouse_id: str
    latency_ms: float
    degraded: bool = False
    degradation_reason: str | None = None
    requested_role: str | None = None
    selected_role: str | None = None
    fallback_from: str | None = None
    fallback_reason: str | None = None
    answerability: str = "answerable"
    missing_context: list[str] = field(default_factory=list)
    timing: dict[str, float] = field(default_factory=dict)
    focus_entity_id: str | None = None
    focus_entity_label: str | None = None


# ── ACT governed-action types ─────────────────────────────────────────────────

@dataclass(frozen=True)
class GovernedActionRequest:
    """
    Typed handoff from CopilotService to GovernedActionOrchestrator.

    This is NOT an ActionProposal. It is the intent-layer representation
    of what the operator requested, carrying full provenance for stale-state
    detection and audit.

    CopilotService creates this; GovernedActionOrchestrator consumes it.
    """
    recommendation_id: str
    capability: str
    target: str
    domain: str
    objective: str
    rationale: str
    priority: str
    subtype: str | None
    # ACT turn identity
    conversation_id: str
    turn_id: str       # ACT turn_id (fresh)
    trace_id: str      # ACT trace_id (fresh)
    # Source recommendation provenance (for stale-state detection)
    source_turn_id: str      # RecommendedActionResult.turn_id (ANALYZE turn)
    source_trace_id: str     # RecommendedActionResult.trace_id (ANALYZE turn)
    source_snapshot_id: str  # S1 — snapshot when recommendation was generated
    current_snapshot_id: str  # S2 — fresh snapshot used for proposal
    focus_entity_id: str | None


@dataclass
class CopilotActResult:
    """
    Structured result of a Copilot ACT turn.

    Captures the full governance decision: what was requested, what the
    DecisionEngine concluded, whether human approval is required, and
    the exact mutation state after execution (if any).

    mutation_state uses MutationState to avoid overloading a bool:
      NOT_ATTEMPTED — no write occurred (pending approval, rejected, stale)
      CONFIRMED     — ActionExecutor confirmed execution
      UNKNOWN       — write may have occurred; reconciliation required

    This type MUST NOT contain:
      - ActionProposal objects (it carries proposal_id by reference only)
      - DecisionEngine references
      - ApprovalStore references
      - Execution state beyond the typed mutation_state
    """
    message: str
    recommendation_id: str
    capability: str
    target: str
    decision_outcome: str  # "APPROVED" | "REJECTED" | "REQUIRES_HUMAN_APPROVAL" |
                           # "REQUIRES_FRESH_STATE" | "CLARIFICATION_REQUIRED" |
                           # "STALE_STATE" | "NOT_IMPLEMENTED" | "ERROR"
    # Governance references (IDs only — not the objects)
    proposal_id: str | None
    decision_id: str | None
    # Approval
    approval_required: bool
    pending_approval_id: str | None
    # Execution
    execution_status: str | None   # ExecutionOutcome.value if executed
    execution_id: str | None
    # Mutation
    mutation_state: MutationState
    # Safety copy — context-sensitive:
    #   "No warehouse changes have been made."
    #   "Execution confirmed."
    #   "Execution status uncertain — reconciliation required."
    safety_note: str
    violations: list[dict]         # from DecisionEngine, if any
    # Snapshot provenance
    source_recommendation_id: str  # same as recommendation_id (explicit for audit)
    source_snapshot_id: str        # S1 — ANALYZE turn snapshot
    snapshot_id: str               # S2 — current snapshot used for proposal
    # Turn identity
    conversation_id: str
    turn_id: str
    trace_id: str
    warehouse_id: str
    latency_ms: float
    degraded: bool = False
    degradation_reason: str | None = None


# ── Turn / Conversation store models ─────────────────────────────────────────

@dataclass
class CopilotTurn:
    """
    One operator message + one Copilot response.

    Do NOT store chain_of_thought, scratchpad, hidden_reasoning,
    reasoning_tokens — any field whose name suggests hidden model state.
    """
    turn_id: str
    conversation_id: str
    user_message: str
    intent: CopilotIntent
    created_at: datetime
    trace_id: str
    response_summary: str
    artifact_refs: dict[str, str | None] = field(default_factory=dict)
    # artifact_refs keys: proposal_id, decision_id, approval_id, execution_id
    parent_turn_id: str | None = None
    related_trace_ids: list[str] = field(default_factory=list)
    # Focus entity resolved during this turn (for continuity in subsequent turns)
    focus_entity_id: str | None = None
    focus_entity_type: str | None = None
    focus_entity_label: str | None = None


@dataclass
class CopilotConversation:
    """
    One operator Copilot session.

    Process-local: state is lost on API restart. This limitation is
    documented in every CopilotTurnResponse.
    """
    conversation_id: str
    warehouse_id: str
    scenario_name: str
    turns: list[CopilotTurn] = field(default_factory=list)
    last_recommendations: list[Any] = field(default_factory=list)
    related_trace_ids: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Focus continuity — updated on each turn that resolves an entity
    last_focus_entity_id: str | None = None
    last_focus_entity_type: str | None = None
    last_focus_entity_label: str | None = None

    def add_turn(self, turn: CopilotTurn) -> None:
        self.turns.append(turn)
        if turn.trace_id not in self.related_trace_ids:
            self.related_trace_ids.append(turn.trace_id)

    @property
    def last_turn(self) -> CopilotTurn | None:
        return self.turns[-1] if self.turns else None


# ── API request / response shapes (Pydantic for FastAPI) ─────────────────────

class CopilotTurnRequest(BaseModel):
    conversation_id: str | None = Field(
        default=None,
        description="Existing conversation ID; omit to start a new conversation.",
    )
    message: str = Field(..., min_length=1, max_length=2000)
    warehouse_id: str = Field(default="DC-47")
    scenario_name: str = Field(default="")


class CopilotTurnResponse(BaseModel):
    conversation_id: str
    turn_id: str
    trace_id: str
    intent: str
    status: str  # "complete" | "degraded" | "error"

    # ASK fields (present when intent=ask)
    answer: str | None = None
    evidence: list[dict] | None = None
    neighborhood: dict | None = None
    agent: str | None = None
    skills_used: list[str] | None = None       # actually invoked — [] for ASK
    skills_available: list[str] | None = None  # agent-reported reachable capabilities
    model_id: str | None = None
    reasoning_level: str | None = None
    routing_rule: str | None = None
    routing_reason: str | None = None
    requested_role: str | None = None
    selected_role: str | None = None
    fallback_from: str | None = None
    fallback_reason: str | None = None
    latency_ms: float | None = None
    degraded: bool = False
    degradation_reason: str | None = None
    answerability: str = "answerable"   # "answerable" | "insufficient_evidence" | "partial"
    missing_context: list[str] = Field(default_factory=list)
    timing: dict = Field(default_factory=dict)  # state_assembly_ms, graph_lookup_ms, model_inference_ms, total_ms

    # ANALYZE fields (present when intent=analyze)
    summary: str | None = None
    severity: str | None = None
    recommendations: list[dict] | None = None  # RecommendedActionResult as dicts
    focus_entity_id: str | None = None
    focus_entity_label: str | None = None
    safety_note: str | None = None  # dynamic per intent: ANALYZE/ACT-specific copy

    # ACT fields (present when intent=act)
    act_recommendation_id: str | None = None
    act_decision_outcome: str | None = None   # "REQUIRES_HUMAN_APPROVAL" | "REJECTED" | etc.
    act_proposal_id: str | None = None
    act_decision_id: str | None = None
    act_pending_approval_id: str | None = None
    act_approval_required: bool = False
    act_execution_status: str | None = None   # "EXECUTED" | "UNKNOWN" | "FAILED" | etc.
    act_execution_id: str | None = None
    act_mutation_state: str | None = None     # MutationState.value
    act_violations: list[dict] = Field(default_factory=list)
    act_source_snapshot_id: str | None = None  # S1 snapshot when recommendation was created

    related_artifacts: dict = Field(default_factory=dict)

    # Explicitly NOT present: proposal, decision, approval, execution shortcuts
    # See PHASE_15_COPILOT_ARCHITECTURE.md — trust boundary

    store_note: str = "Conversation state is process-local and will not survive API restart."
