# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW Agent Contracts — Phase 18H: SOP-Driven Agent Foundation.

This package defines the canonical contracts for MAIW agents:

    AgentDefinition     — what an agent is (objective, domain, capabilities, SOP)
    AgentTaskState      — runtime state for one agent task execution
    AgentTaskStatus     — enumeration of valid task statuses
    AgentObservation    — a structured observation recorded during SOP execution
    SOPDefinition       — a versioned Standard Operating Procedure
    SOPStep             — one step in an SOP
    SkillRegistryEntry  — metadata for a registered MAIW skill
    CapabilityClass     — read/write/proposal/emergency classification
    AgentDelegationRequest / AgentDelegationResult — delegation contracts
    GovernanceOutcome   — result returned after governance + execution
    AgentRuntime        — Protocol for SOP execution runtime

Framework independence:
    No LangGraph, LangChain, Deep Agents, or NemoClaw imports.
    MAIW owns its operational semantics; frameworks are adapters.
"""

from .agent import (
    AgentDefinition,
    AgentTrigger,
    GovernanceBoundary,
    TerminationPolicy,
    TerminationCondition,
)
from .task import (
    AgentTaskState,
    AgentTaskStatus,
    AgentObservation,
    SkillResultRef,
    AgentResultRef,
    StepResult,
    StepStatus,
)
from .sop import (
    SOPDefinition,
    SOPStep,
    StepCondition,
    EscalationRule,
    SOPValidationError,
    load_sop,
    validate_sop,
)
from .delegation import (
    AgentDelegationRequest,
    AgentDelegationResult,
    GovernanceOutcome,
)
from .registry import (
    CapabilityClass,
    SkillRegistryEntry,
    SKILL_REGISTRY,
    get_skill,
    get_skills_by_domain,
)
from .runtime import (
    AgentExecutionContext,
    AgentRuntime,
    AgentTaskResult,
)
from .definitions import (
    AGENT_DEFINITIONS,
    OPERATIONS_COORDINATION_DEFINITION,
    LABOR_AGENT_DEFINITION,
    WAVE_AGENT_DEFINITION,
    EQUIPMENT_AGENT_DEFINITION,
    SAFETY_COMPLIANCE_DEFINITION,
    get_agent_definition,
)

__all__ = [
    # Agent contract
    "AgentDefinition",
    "AgentTrigger",
    "GovernanceBoundary",
    "TerminationPolicy",
    "TerminationCondition",
    # Task state
    "AgentTaskState",
    "AgentTaskStatus",
    "AgentObservation",
    "SkillResultRef",
    "AgentResultRef",
    "StepResult",
    "StepStatus",
    # SOP
    "SOPDefinition",
    "SOPStep",
    "StepCondition",
    "EscalationRule",
    "SOPValidationError",
    "load_sop",
    "validate_sop",
    # Delegation
    "AgentDelegationRequest",
    "AgentDelegationResult",
    "GovernanceOutcome",
    # Registry
    "CapabilityClass",
    "SkillRegistryEntry",
    "SKILL_REGISTRY",
    "get_skill",
    "get_skills_by_domain",
    # Runtime
    "AgentExecutionContext",
    "AgentRuntime",
    "AgentTaskResult",
    # Canonical definitions
    "AGENT_DEFINITIONS",
    "OPERATIONS_COORDINATION_DEFINITION",
    "LABOR_AGENT_DEFINITION",
    "WAVE_AGENT_DEFINITION",
    "EQUIPMENT_AGENT_DEFINITION",
    "SAFETY_COMPLIANCE_DEFINITION",
    "get_agent_definition",
]
