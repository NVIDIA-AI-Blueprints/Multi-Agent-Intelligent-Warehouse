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

    # Future: ANALYZE and ACT fields populated in 15C / 15D
    related_artifacts: dict = Field(default_factory=dict)

    # Explicitly NOT present: proposal, decision, approval, execution shortcuts
    # See PHASE_15_COPILOT_ARCHITECTURE.md — trust boundary

    store_note: str = "Conversation state is process-local and will not survive API restart."
