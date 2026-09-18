# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW Agent Task State — Phase 18H.

AgentTaskState is the structured runtime state for one agent task execution.
It tracks the lifecycle from PENDING through COMPLETED/ESCALATED/FAILED.

Key invariants:
- State is structured (no raw LLM scratchpad text)
- IDs are stable and distinct from: Copilot turn ID, conversation ID,
  trace ID, context snapshot ID, proposal ID, execution ID
- Observations store facts and evidence, not chain-of-thought
- iteration is a hard-bounded counter (governed by TerminationPolicy.max_iterations)
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Task status ───────────────────────────────────────────────────────────────

class AgentTaskStatus(str, Enum):
    """All valid lifecycle states for an agent task."""

    PENDING = "PENDING"
    """Task created but not yet started."""

    RUNNING = "RUNNING"
    """SOP is actively executing."""

    WAITING_FOR_INPUT = "WAITING_FOR_INPUT"
    """Agent paused waiting for additional input from operator."""

    WAITING_FOR_SUBAGENT = "WAITING_FOR_SUBAGENT"
    """Agent paused waiting for a delegated subagent to return."""

    WAITING_FOR_GOVERNANCE = "WAITING_FOR_GOVERNANCE"
    """Agent emitted a RecommendedAction and is waiting for governance/execution result."""

    OBSERVING_OUTCOME = "OBSERVING_OUTCOME"
    """Agent received governance/execution result and is reading resulting world state."""

    COMPLETED = "COMPLETED"
    """Objective met — terminal."""

    ESCALATED = "ESCALATED"
    """No safe action or human intervention required — terminal."""

    FAILED = "FAILED"
    """Unrecoverable error — terminal."""


# Valid status transitions (from → to)
_VALID_TRANSITIONS: dict[AgentTaskStatus, set[AgentTaskStatus]] = {
    AgentTaskStatus.PENDING: {AgentTaskStatus.RUNNING, AgentTaskStatus.FAILED},
    AgentTaskStatus.RUNNING: {
        AgentTaskStatus.WAITING_FOR_INPUT,
        AgentTaskStatus.WAITING_FOR_SUBAGENT,
        AgentTaskStatus.WAITING_FOR_GOVERNANCE,
        AgentTaskStatus.OBSERVING_OUTCOME,
        AgentTaskStatus.COMPLETED,
        AgentTaskStatus.ESCALATED,
        AgentTaskStatus.FAILED,
    },
    AgentTaskStatus.WAITING_FOR_INPUT: {
        AgentTaskStatus.RUNNING,
        AgentTaskStatus.ESCALATED,
        AgentTaskStatus.FAILED,
    },
    AgentTaskStatus.WAITING_FOR_SUBAGENT: {
        AgentTaskStatus.RUNNING,
        AgentTaskStatus.ESCALATED,
        AgentTaskStatus.FAILED,
    },
    AgentTaskStatus.WAITING_FOR_GOVERNANCE: {
        AgentTaskStatus.OBSERVING_OUTCOME,
        AgentTaskStatus.ESCALATED,
        AgentTaskStatus.FAILED,
    },
    AgentTaskStatus.OBSERVING_OUTCOME: {
        AgentTaskStatus.RUNNING,
        AgentTaskStatus.COMPLETED,
        AgentTaskStatus.ESCALATED,
        AgentTaskStatus.FAILED,
    },
    AgentTaskStatus.COMPLETED: set(),
    AgentTaskStatus.ESCALATED: set(),
    AgentTaskStatus.FAILED: set(),
}


def is_valid_transition(
    current: AgentTaskStatus, next_: AgentTaskStatus
) -> bool:
    """Return True if transitioning from current to next_ is allowed."""
    return next_ in _VALID_TRANSITIONS.get(current, set())


def is_terminal(status: AgentTaskStatus) -> bool:
    """Return True if this is a terminal status (no further transitions)."""
    return status in {
        AgentTaskStatus.COMPLETED,
        AgentTaskStatus.ESCALATED,
        AgentTaskStatus.FAILED,
    }


# ── Observation ───────────────────────────────────────────────────────────────

ObservationSource = Literal["skill", "subagent", "world_state", "operator", "governance"]


class AgentObservation(BaseModel):
    """
    A structured observation recorded during SOP execution.

    Stores facts and evidence — not raw LLM chain-of-thought.
    """

    observation_id: str
    observation_type: str = Field(
        description="What kind of observation this is (e.g. 'labor_capacity', 'wave_status', 'equipment_offline')."
    )
    source: ObservationSource
    entity_ids: list[str] = Field(default_factory=list)
    facts: dict[str, Any] = Field(
        default_factory=dict,
        description="Key-value facts extracted from this observation.",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    context_snapshot_id: str | None = None
    step_id: str | None = None


# ── Step/skill result refs ────────────────────────────────────────────────────

class SkillResultRef(BaseModel):
    """A reference to the result of a skill invocation."""

    skill_id: str
    step_id: str
    outcome: str  # "success" | "error" | "no_data"
    summary: str
    trace_id: str | None = None
    latency_ms: float | None = None


class AgentResultRef(BaseModel):
    """A reference to the result of a delegated subagent task."""

    child_task_id: str
    agent_id: str
    status: str
    assessment_summary: str | None = None
    candidate_action_count: int = 0


# ── Step result ───────────────────────────────────────────────────────────────

StepStatus = Literal[
    "completed",
    "escalate",
    "stop",
    "continue",
    "delegate",
    "wait_governance",
    "error",
]


class StepResult(BaseModel):
    """
    Structured result of executing one SOP step.

    Returned by SOPStepExecutor.execute().
    """

    status: StepStatus
    observations: list[AgentObservation] = Field(default_factory=list)
    skill_results: list[SkillResultRef] = Field(default_factory=list)
    subagent_requests: list[dict[str, Any]] = Field(default_factory=list)
    candidate_actions: list[dict[str, Any]] = Field(default_factory=list)
    next_step_id: str | None = None
    escalation_reason: str | None = None
    stop_reason: str | None = None
    recommendation: dict[str, Any] | None = None


# ── Agent task state ──────────────────────────────────────────────────────────

class AgentTaskState(BaseModel):
    """
    Runtime state for one agent task execution.

    Lifecycle: PENDING → RUNNING → ... → COMPLETED | ESCALATED | FAILED

    IDs are distinct from Copilot turn ID, conversation ID, trace ID,
    context snapshot ID, proposal ID, and execution ID. They are linked
    through provenance fields.
    """

    task_id: str = Field(description="Stable unique ID for this agent task.")
    agent_id: str
    sop_id: str
    sop_version: str
    objective: str

    status: AgentTaskStatus = AgentTaskStatus.PENDING
    current_step_id: str | None = None
    completed_steps: list[str] = Field(default_factory=list)
    iteration: int = 0

    # Provenance links (not the same objects, just reference IDs)
    conversation_id: str | None = None
    copilot_turn_id: str | None = None
    trace_id: str | None = None
    context_snapshot_id: str | None = None

    observations: list[AgentObservation] = Field(default_factory=list)
    skill_results: list[SkillResultRef] = Field(default_factory=list)
    subagent_results: list[AgentResultRef] = Field(default_factory=list)

    recommendation_id: str | None = None
    stop_reason: str | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def transition(self, new_status: AgentTaskStatus) -> "AgentTaskState":
        """
        Return a new AgentTaskState with the updated status.

        Raises ValueError if the transition is not permitted.
        """
        if not is_valid_transition(self.status, new_status):
            raise ValueError(
                f"Invalid AgentTaskState transition: {self.status!r} → {new_status!r}"
            )
        return self.model_copy(
            update={
                "status": new_status,
                "updated_at": datetime.now(timezone.utc),
            }
        )

    def increment_iteration(self, max_iterations: int) -> tuple["AgentTaskState", bool]:
        """
        Increment the iteration counter.

        Returns (updated_state, limit_reached).
        If limit_reached is True, the caller should escalate.
        """
        new_iteration = self.iteration + 1
        limit_reached = new_iteration >= max_iterations
        state = self.model_copy(
            update={
                "iteration": new_iteration,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        return state, limit_reached

    def record_step_completed(self, step_id: str) -> "AgentTaskState":
        new_steps = list(self.completed_steps) + [step_id]
        return self.model_copy(
            update={
                "completed_steps": new_steps,
                "current_step_id": None,
                "updated_at": datetime.now(timezone.utc),
            }
        )
