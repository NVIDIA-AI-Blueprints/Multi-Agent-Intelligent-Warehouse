# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW Agent Runtime Protocol — Phase 18H.

AgentRuntime is the integration seam for a future Deep Agents implementation.
The minimal MAIW runtime (MAIWDeterministicRuntime) runs agents deterministically
following the SOP step sequence.

Deep Agents can later implement the AgentRuntime Protocol without changing
MAIW's operational semantics: AgentDefinition, SOPDefinition, AgentTaskState,
delegation contracts, and output contracts are framework-independent.

Architecture of seam:
    AgentRuntime.run_task(definition, sop, state, context) → AgentTaskResult
    ↑
    MAIWDeterministicRuntime (Phase 18H — deterministic step execution)
    ↑
    DeepAgentsRuntime (Phase 19+ — POC; implements same Protocol)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from .agent import AgentDefinition
from .registry import CapabilityClass, SKILL_REGISTRY
from .sop import SOPDefinition
from .task import AgentTaskState, AgentTaskStatus


# ── Agent execution context ───────────────────────────────────────────────────

@dataclass
class AgentExecutionContext:
    """
    Runtime context injected into a SOP step executor.

    Carries: model_gateway, warehouse state, conversation provenance,
    skill references, and the clock. Does NOT carry ActionExecutor or
    DecisionEngine — those are governance components.
    """

    warehouse_id: str
    trace_id: str
    conversation_id: str | None = None
    copilot_turn_id: str | None = None
    context_snapshot_id: str | None = None

    model_gateway: Any = None
    state_provider: Any = None
    skill_registry: dict[str, Any] = field(default_factory=dict)
    bounded_context: dict[str, Any] = field(default_factory=dict)

    started_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ── Agent task result ─────────────────────────────────────────────────────────

@dataclass
class AgentTaskResult:
    """Result returned by AgentRuntime.run_task()."""

    task_id: str
    agent_id: str
    sop_id: str
    sop_version: str
    final_status: AgentTaskStatus
    recommendation: dict[str, Any] | None = None
    assessment: dict[str, Any] | None = None
    candidate_actions: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str | None = None
    escalation_reason: str | None = None
    observations: list[dict[str, Any]] = field(default_factory=list)
    iterations: int = 0
    completed_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ── AgentRuntime Protocol ─────────────────────────────────────────────────────

@runtime_checkable
class AgentRuntime(Protocol):
    """
    Integration seam for SOP execution runtimes.

    The initial MAIW implementation (MAIWDeterministicRuntime) is deterministic
    and minimal. Deep Agents can later implement this Protocol without
    modifying MAIW operational semantics.

    Framework independence:
        This Protocol must NOT import Deep Agents, LangChain, LangGraph,
        NemoClaw, or any external agent framework.
    """

    async def run_task(
        self,
        definition: AgentDefinition,
        sop: SOPDefinition,
        state: AgentTaskState,
        context: AgentExecutionContext,
    ) -> AgentTaskResult:
        """
        Execute an agent task following the given SOP.

        The runtime is responsible for:
        - SOP step sequencing
        - Condition evaluation
        - Skill invocation
        - Subagent delegation
        - Iteration guard enforcement
        - Termination condition detection

        The runtime must NOT:
        - Call ActionExecutor
        - Call DecisionEngine directly
        - Mutate warehouse operational state
        - Import LangGraph, LangChain, Deep Agents, NemoClaw
        """
        ...


# ── Shared guard (extracted from runtimes) ────────────────────────────────────

def check_capability_alignment(
    definition: AgentDefinition,
    sop: SOPDefinition,
) -> None:
    """
    Verify that SOP capabilities are a subset of AgentDefinition capabilities,
    and that no WRITE or EMERGENCY_WRITE capabilities are present.

    Extracted from both DeepAgentsRuntime and MAIWDeterministicRuntime for
    consolidation — this is a MAIW-owned guard, not a runtime-specific concern.

    Raises ValueError if any invariant is violated.
    """
    definition_caps = set(definition.allowed_capabilities)
    sop_caps = set(sop.allowed_capabilities)
    extra = sop_caps - definition_caps
    if extra:
        raise ValueError(
            f"SOP {sop.id!r} declares capabilities not in AgentDefinition "
            f"{definition.agent_id!r}: {sorted(extra)}"
        )
    # Belt-and-suspenders: reject any write capabilities
    for cap_id in sop_caps:
        skill = SKILL_REGISTRY.get(cap_id)
        if skill and skill.capability_class in (
            CapabilityClass.WRITE, CapabilityClass.EMERGENCY_WRITE
        ):
            raise ValueError(
                f"SOP {sop.id!r} contains WRITE capability {cap_id!r} — "
                "agents may not invoke write capabilities directly."
            )
