# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Agent Tasks read-only router — UX-1B.1.

Exposes structured AgentTaskState for operator and developer visibility
into agentic procedure progress.

Endpoints (all read-only GET):
    GET /api/v1/agent-tasks                    — list recent active tasks
    GET /api/v1/agent-tasks/{task_id}          — task state + SOP step metadata
    GET /api/v1/agent-tasks/{task_id}/sop      — SOP definition with step descriptions

Security invariants:
    - NEVER returns chain_of_thought, scratchpad, or raw prompts
    - NEVER returns framework internals (LangGraph nodes, deepagents checkpoints)
    - Returns structured MAIW state only (AgentTaskState fields)
    - Bounded response — no full conversation history
    - Read-only: no POST/PUT/DELETE
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent-tasks", tags=["agent-tasks"])

# ── SOP registry (file-based, read from YAML) ─────────────────────────────────

_SOP_DIR = Path(__file__).parents[4] / "agents" / "sops"


def _load_sop_metadata(sop_id: str) -> dict[str, Any] | None:
    """
    Load SOP step metadata for the given sop_id.
    Returns step list with id, description, action — not prompts or internals.
    """
    try:
        from maiw_agents.contracts.sop import load_sop
    except ImportError:
        return None

    # sop_id format: "domain.sop_name" → "domain/sop_name.v1.yaml"
    parts = sop_id.split(".", 1)
    if len(parts) != 2:
        return None

    domain, name = parts
    # Try common version suffixes
    for suffix in ["v1", "v2"]:
        path = _SOP_DIR / domain / f"{name}.{suffix}.yaml"
        if path.exists():
            try:
                sop = load_sop(path)
                return {
                    "id": sop.id,
                    "version": sop.version,
                    "agent": sop.agent,
                    "objective": sop.objective,
                    "runtime_profile": getattr(sop, "runtime_profile", "strict"),
                    "steps": [
                        {
                            "id": step.id,
                            "action": step.action,
                            "description": step.description,
                        }
                        for step in sop.steps
                    ],
                }
            except Exception as exc:
                logger.warning("Failed to load SOP %s: %s", sop_id, exc)
                return None

    return None


# ── In-memory task registry (demo mode only) ──────────────────────────────────

# Task states are stored by the demo controller during analysis runs.
# This router reads them; it never writes.
_TASK_REGISTRY: dict[str, Any] = {}


def register_agent_task(task_id: str, state: Any) -> None:
    """
    Called by the demo controller to register an agent task state.
    This is the only write path — external to this router.
    """
    _TASK_REGISTRY[task_id] = state


def get_registered_task(task_id: str) -> Any | None:
    return _TASK_REGISTRY.get(task_id)


def list_registered_tasks() -> list[Any]:
    return list(_TASK_REGISTRY.values())


def clear_task_registry() -> None:
    _TASK_REGISTRY.clear()


# ── Response schemas ───────────────────────────────────────────────────────────

class SOPStepView(BaseModel):
    """One SOP step as visible to the operator/developer."""
    id: str
    action: str
    description: str | None = None


class SOPMetadataView(BaseModel):
    """SOP metadata — operator and developer visible fields."""
    sop_id: str
    sop_version: str
    agent: str
    objective: str
    runtime_profile: str
    steps: list[SOPStepView] = Field(default_factory=list)


class DelegationResultView(BaseModel):
    """Specialist agent consultation result — operator-friendly."""
    delegation_id: str
    child_task_id: str
    requesting_agent: str
    responding_agent: str
    status: str
    assessment: dict[str, Any] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
    candidate_action_count: int = 0
    # Expert fields
    trace_id: str | None = None
    context_snapshot_id: str | None = None


class AgentTaskView(BaseModel):
    """
    AgentTaskState as visible through the MAIW API.

    Operator-facing fields are always present.
    Developer fields (agent_id, task_id, sop_id etc.) are always present
    — the UI layer controls which fields to show based on expertMode.

    NEVER includes: chain_of_thought, scratchpad, raw prompts,
    framework internals (LangGraph state, deepagents checkpoints).
    """
    # Core identity
    task_id: str
    agent_id: str
    sop_id: str
    sop_version: str
    objective: str

    # Lifecycle
    status: str
    current_step_id: str | None = None
    completed_steps: list[str] = Field(default_factory=list)
    iteration: int = 0

    # Provenance (developer-facing)
    conversation_id: str | None = None
    copilot_turn_id: str | None = None
    trace_id: str | None = None
    context_snapshot_id: str | None = None

    # Delegation results (specialist consultations)
    delegation_results: list[DelegationResultView] = Field(default_factory=list)

    # Terminal reason
    stop_reason: str | None = None
    recommendation_id: str | None = None

    # SOP step metadata (resolved from YAML)
    sop_steps: list[SOPStepView] = Field(default_factory=list)

    # Timestamps
    created_at: str | None = None
    updated_at: str | None = None


# ── Endpoint helpers ───────────────────────────────────────────────────────────

def _build_task_view(state: Any) -> AgentTaskView:
    """
    Build AgentTaskView from an AgentTaskState.
    Resolves SOP step metadata from YAML files.
    Excludes all internal/framework state.
    """
    sop_steps: list[SOPStepView] = []
    sop_meta = _load_sop_metadata(state.sop_id)
    if sop_meta:
        sop_steps = [
            SOPStepView(id=s["id"], action=s["action"], description=s.get("description"))
            for s in sop_meta.get("steps", [])
        ]

    # Build delegation result views from subagent_results (AgentResultRef list)
    delegation_results: list[DelegationResultView] = []
    for ref in getattr(state, "subagent_results", []):
        delegation_results.append(DelegationResultView(
            delegation_id=ref.agent_id + "-" + ref.child_task_id,
            child_task_id=ref.child_task_id,
            requesting_agent=state.agent_id,
            responding_agent=ref.agent_id,
            status=ref.status,
            assessment={},
            evidence=[],
            candidate_action_count=ref.candidate_action_count,
            trace_id=state.trace_id,
            context_snapshot_id=state.context_snapshot_id,
        ))

    return AgentTaskView(
        task_id=state.task_id,
        agent_id=state.agent_id,
        sop_id=state.sop_id,
        sop_version=state.sop_version,
        objective=state.objective,
        status=state.status.value if hasattr(state.status, "value") else str(state.status),
        current_step_id=state.current_step_id,
        completed_steps=list(state.completed_steps),
        iteration=state.iteration,
        conversation_id=state.conversation_id,
        copilot_turn_id=state.copilot_turn_id,
        trace_id=state.trace_id,
        context_snapshot_id=state.context_snapshot_id,
        delegation_results=delegation_results,
        stop_reason=state.stop_reason,
        recommendation_id=state.recommendation_id,
        sop_steps=sop_steps,
        created_at=state.created_at.isoformat() if state.created_at else None,
        updated_at=state.updated_at.isoformat() if state.updated_at else None,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[AgentTaskView])
async def list_agent_tasks() -> list[AgentTaskView]:
    """
    List recent agent tasks.

    Returns structured task state — no chain-of-thought, no framework internals.
    """
    tasks = list_registered_tasks()
    return [_build_task_view(t) for t in tasks]


@router.get("/{task_id}", response_model=AgentTaskView)
async def get_agent_task(task_id: str) -> AgentTaskView:
    """
    Get agent task state by ID.

    Returns structured task state with SOP step metadata resolved.
    NEVER returns chain_of_thought, scratchpad, or framework internals.
    """
    state = get_registered_task(task_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Agent task '{task_id}' not found")

    return _build_task_view(state)


@router.get("/{task_id}/sop", response_model=SOPMetadataView)
async def get_agent_task_sop(task_id: str) -> SOPMetadataView:
    """
    Get SOP definition for a given agent task.

    Returns step names and descriptions from the SOP YAML.
    NEVER returns prompt text, system instructions, or model internals.
    """
    state = get_registered_task(task_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Agent task '{task_id}' not found")

    sop_meta = _load_sop_metadata(state.sop_id)
    if sop_meta is None:
        raise HTTPException(
            status_code=404,
            detail=f"SOP '{state.sop_id}' not found in registry",
        )

    return SOPMetadataView(
        sop_id=sop_meta["id"],
        sop_version=sop_meta["version"],
        agent=sop_meta["agent"],
        objective=sop_meta["objective"],
        runtime_profile=sop_meta["runtime_profile"],
        steps=[
            SOPStepView(id=s["id"], action=s["action"], description=s.get("description"))
            for s in sop_meta["steps"]
        ],
    )
