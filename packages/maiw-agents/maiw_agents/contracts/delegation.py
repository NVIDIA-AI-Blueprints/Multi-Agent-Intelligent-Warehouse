# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW Agent Delegation Contracts — Phase 18H.

Defines:
    AgentDelegationRequest  — a parent agent delegating a bounded question to a specialist
    AgentDelegationResult   — the specialist's response
    GovernanceOutcome       — result returned after governance + execution completes

Delegation semantics:
    - Parent may delegate a bounded domain question to a specialist.
    - Specialist receives bounded context (not full parent state).
    - Specialist cannot invoke writes directly.
    - Specialist returns an assessment and candidate actions — not executions.
    - Parent integrates results and emits a final recommendation.

No autonomous scheduling implemented in Phase 18H — delegation is
coordinated by the deterministic SOP runtime.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


# ── Delegation request ────────────────────────────────────────────────────────

class AgentDelegationRequest(BaseModel):
    """
    A parent agent delegating a bounded domain question to a specialist agent.

    The specialist receives ONLY what it needs to answer the question —
    not the full parent task state or world snapshot.
    """

    delegation_id: str = Field(description="Unique ID for this delegation.")
    parent_task_id: str
    requesting_agent: str
    target_agent: str

    objective: str = Field(
        description="Plain-English statement of what the specialist should assess."
    )
    context_snapshot_id: str | None = Field(
        default=None,
        description=(
            "ID of the OperationalContextSnapshot the specialist should use. "
            "Bounded context — not the full parent task state."
        ),
    )
    bounded_context: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Extracted facts from the parent context relevant to this delegation. "
            "Do not pass the full world state — pass only what the specialist needs."
        ),
    )
    requested_output: str = Field(
        default="",
        description="What the parent expects back (e.g. 'LaborAssessment', 'WaveAssessment')."
    )
    trace_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Delegation result ─────────────────────────────────────────────────────────

class AgentDelegationResult(BaseModel):
    """
    The specialist agent's response to a delegation request.

    Contains the assessment and candidate actions, but NOT execution.
    """

    delegation_id: str
    child_task_id: str
    requesting_agent: str
    responding_agent: str

    status: str = Field(
        description="Terminal status of the child task (COMPLETED, ESCALATED, FAILED)."
    )
    assessment: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured domain assessment (LaborAssessment, WaveAssessment, etc.).",
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="Supporting evidence observed by the specialist.",
    )
    candidate_actions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Candidate interventions proposed by the specialist. Not executed.",
    )
    escalation_reason: str | None = None
    trace_id: str | None = None
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Governance outcome ────────────────────────────────────────────────────────

class GovernanceOutcome(BaseModel):
    """
    Result returned to the agent after governance + execution completes.

    This is the signal that transitions an agent from WAITING_FOR_GOVERNANCE
    to OBSERVING_OUTCOME.
    """

    proposal_id: str
    decision_outcome: str = Field(
        description=(
            "One of: APPROVED, REJECTED, REQUIRES_HUMAN_APPROVAL, "
            "REQUIRES_FRESH_STATE, ERROR."
        )
    )
    approval_status: str | None = Field(
        default=None,
        description="If REQUIRES_HUMAN_APPROVAL: PENDING, APPROVED, REJECTED, EXPIRED.",
    )
    execution_id: str | None = None
    execution_status: str | None = Field(
        default=None,
        description="If executed: EXECUTED, UNKNOWN, NO_OP, CONFLICT.",
    )
    resulting_context_snapshot_id: str | None = Field(
        default=None,
        description=(
            "ID of the OperationalContextSnapshot captured after execution. "
            "The agent should read the new world state from this snapshot."
        ),
    )
    trace_id: str | None = None
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
