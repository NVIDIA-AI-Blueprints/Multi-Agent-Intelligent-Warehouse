# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW Agent Contract — Phase 18H.

AgentDefinition is the first-class MAIW agent descriptor. It is not
framework-specific: it describes WHAT an agent is (objective, domain,
capabilities, SOP, governance boundary, termination policy).

An AGENT (vs. a SKILL):
    - owns an objective
    - has task state
    - follows an SOP
    - may invoke multiple skills
    - may delegate to other agents
    - reasons across multiple steps
    - has escalation and termination semantics
    - produces a recommendation/proposal — NOT a direct write

A SKILL:
    - performs a bounded capability
    - no independent objective
    - no persistent task state
    - no planning loop
    - no delegation
    - no stop condition beyond completion
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ── Trigger types ─────────────────────────────────────────────────────────────

TriggerType = Literal[
    "wave_risk_detected",
    "operator_requests_resolution",
    "equipment_failure_detected",
    "equipment_constraint_detected",
    "labor_constraint_detected",
    "safety_alert",
    "safety_incident_reported",
    "governance_result_returned",
    "manual",
]


class AgentTrigger(BaseModel):
    """A named condition that can activate an agent task."""

    trigger_id: str
    trigger_type: TriggerType
    description: str
    condition_hint: str | None = None  # human-readable activation condition


# ── Governance boundary ───────────────────────────────────────────────────────

class GovernanceBoundary(BaseModel):
    """
    Defines what this agent is and is not permitted to do.

    All agents are prohibited from directly mutating operational state.
    The boundary enumerates allowed capability classes for this agent.
    """

    allowed_capability_classes: list[Literal[
        "READ", "ANALYTICAL", "PROPOSAL"
    ]] = Field(
        default=["READ", "ANALYTICAL", "PROPOSAL"],
        description=(
            "Capability classes this agent may invoke directly. "
            "WRITE and EMERGENCY_WRITE are never allowed directly by any normal agent."
        ),
    )
    may_invoke_action_executor: bool = Field(
        default=False,
        description="Always False for normal agents. ActionExecutor is a governance component.",
    )
    may_invoke_decision_engine: bool = Field(
        default=False,
        description=(
            "Normally False. Specialist proposal skills may build ActionProposals; "
            "DecisionEngine is invoked by the governance layer, not the agent."
        ),
    )
    emergency_authority: str | None = Field(
        default=None,
        description=(
            "If set, this agent has an explicit documented emergency authority. "
            "Must reference a specific capability and policy document."
        ),
    )


# ── Termination policy ────────────────────────────────────────────────────────

TerminationConditionId = Literal[
    "OBJECTIVE_MET",
    "NO_SAFE_ACTION",
    "HUMAN_REQUIRED",
    "INSUFFICIENT_CONTEXT",
    "MAX_ITERATIONS",
    "POLICY_BLOCKED",
    "ERROR",
]


class TerminationCondition(BaseModel):
    """A named condition under which the agent terminates its task."""

    condition_id: TerminationConditionId
    description: str


class TerminationPolicy(BaseModel):
    """Policy governing when and how an agent terminates a task."""

    max_iterations: int = Field(
        default=10,
        ge=1,
        le=50,
        description=(
            "Hard upper bound on SOP step iterations. "
            "Prevents infinite loops. Must be a small bounded value."
        ),
    )
    stop_conditions: list[TerminationCondition] = Field(default_factory=list)
    escalate_on_max_iterations: bool = Field(
        default=True,
        description="If True, transition to ESCALATED when max_iterations is reached.",
    )


# ── Agent definition ──────────────────────────────────────────────────────────

class AgentDefinition(BaseModel):
    """
    Canonical MAIW Agent Contract.

    Defines what an agent is: its objective, domain, allowed capabilities and
    subagents, SOP reference, output contract, governance boundary, and
    termination policy.

    This is not a runtime object — it is a descriptor used for validation,
    documentation, and agent registration.
    """

    agent_id: str = Field(
        description="Stable, unique agent identifier (e.g. 'operations_coordination')."
    )
    version: str = Field(
        description="Semantic version of this agent definition (e.g. '1.0')."
    )
    objective: str = Field(
        description="Plain-English description of what this agent exists to accomplish."
    )
    domain: str = Field(
        description="Primary operational domain (e.g. 'operations', 'labor', 'wave', 'equipment', 'safety')."
    )

    triggers: list[AgentTrigger] = Field(
        default_factory=list,
        description="Conditions that may activate a task for this agent.",
    )
    required_context: list[str] = Field(
        default_factory=list,
        description="Context items the agent requires before starting (e.g. 'wave', 'labor', 'equipment').",
    )
    allowed_capabilities: list[str] = Field(
        default_factory=list,
        description="Skill IDs this agent is allowed to invoke (READ, ANALYTICAL, PROPOSAL only).",
    )
    allowed_subagents: list[str] = Field(
        default_factory=list,
        description="Agent IDs this agent may delegate to.",
    )

    sop_id: str | None = Field(
        default=None,
        description="Reference to the SOP this agent follows (e.g. 'operations_coordination.wave_risk_resolution')."
    )
    output_contract: str = Field(
        description=(
            "Description of what this agent produces. "
            "Must be a structured output (assessment, recommendation, candidate actions). "
            "NEVER a write action."
        ),
    )

    governance_boundary: GovernanceBoundary = Field(
        default_factory=GovernanceBoundary,
        description="What this agent may and may not do.",
    )
    termination_policy: TerminationPolicy = Field(
        default_factory=TerminationPolicy,
        description="When and how this agent stops.",
    )

    model_config = ConfigDict(frozen=True)
