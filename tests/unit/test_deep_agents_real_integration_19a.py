# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 19A real deepagents integration tests (Tests A–H).

Validates the real DeepAgentsRuntime (deepagents==0.7.15) with:
- MAIWModelGatewayChat in test mode (model_gateway=None, deterministic mock)
- Wave 17 bounded context (canonical scenario)
- Real deepagents create_deep_agent() + LangGraph graph execution

Test coverage:
    A. Basic SOP run with real deepagents (result has task_id)
    B. READ skill result injected via bounded_context is accessible
    C. SubAgent specs are built from SOP allowed_subagents
    D. WRITE skills are absent from built tools
    E. Runtime returns WAITING_FOR_GOVERNANCE status (governance mock)
    F. resume_after_governance with approved outcome → COMPLETED
    G. Max recursion limit behavior (large iterations still terminates)
    H. Missing context → runtime still terminates gracefully
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure packages are importable
_REPO = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_REPO / "packages" / "maiw-agents"))

from maiw_agents.contracts.agent import (
    AgentDefinition,
    TerminationPolicy,
    GovernanceBoundary,
)
from maiw_agents.contracts.runtime import AgentExecutionContext, AgentTaskResult
from maiw_agents.contracts.sop import load_sop, SOPDefinition
from maiw_agents.contracts.task import AgentTaskState, AgentTaskStatus
from maiw_agents.runtime.deep_agents_runtime import (
    DeepAgentsRuntime,
    _build_maiw_tools,
    _build_subagent_specs,
)
from maiw_agents.runtime.model_adapter import MAIWModelGatewayChat

# ── Fixtures ──────────────────────────────────────────────────────────────────

_SOP_PATH = (
    _REPO
    / "agents"
    / "sops"
    / "operations_coordination"
    / "wave_risk_resolution.v1.yaml"
)

_WAVE17_CONTEXT = {
    "wave_id": "wave-17",
    "at_risk_count": 3,
    "pending_count": 12,
    "completed_count": 45,
    "carrier_cutoff_minutes": 47,
    "primary_constraint": "labor",
    "domains_affected": "labor,wave",
    "zone_a_workers": 8,
    "zone_b_workers": 12,
    "idle_workers": 5,
    "labor_deficit": True,
}

_ALLOWED_CAPS = [
    "warehouse.inventory.lookup",
    "warehouse.equipment.status",
    "warehouse.equipment.telemetry",
    "warehouse.labor.capacity",
    "warehouse.labor.inspect_workers",
    "warehouse.labor.inspect_tasks",
    "warehouse.labor.evaluate_reallocation",
    "warehouse.wave.status",
    "warehouse.wave.inspect_tasks",
    "warehouse.wave.evaluate_critical_path",
    "warehouse.wave.evaluate_reprioritization",
]


def _load_sop() -> SOPDefinition:
    if not _SOP_PATH.exists():
        pytest.skip(f"SOP file not found: {_SOP_PATH}")
    return load_sop(_SOP_PATH)


def _make_definition(max_iterations: int = 20) -> AgentDefinition:
    return AgentDefinition(
        agent_id="operations_coordination",
        version="1.0",
        objective="Resolve wave-at-risk scenario",
        domain="operations",
        allowed_capabilities=_ALLOWED_CAPS,
        allowed_subagents=["labor", "wave", "equipment"],
        sop_id="operations_coordination.wave_risk_resolution",
        output_contract="RecommendedAction",
        governance_boundary=GovernanceBoundary(),
        termination_policy=TerminationPolicy(
            max_iterations=max_iterations,
            escalate_on_max_iterations=True,
        ),
    )


def _make_state(task_id: str = "task-real-wave17") -> AgentTaskState:
    return AgentTaskState(
        task_id=task_id,
        agent_id="operations_coordination",
        sop_id="operations_coordination.wave_risk_resolution",
        sop_version="1.0",
        objective="Resolve Wave 17 labor constraint before carrier cutoff",
        status=AgentTaskStatus.PENDING,
        trace_id="trace-real-wave17",
        context_snapshot_id="snap-wave17-real",
    )


def _make_context(
    bounded_context: dict[str, Any] | None = None,
    model_gateway: Any = None,
) -> AgentExecutionContext:
    return AgentExecutionContext(
        warehouse_id="wh-test",
        trace_id="trace-real-wave17",
        conversation_id="conv-real-wave17",
        context_snapshot_id="snap-wave17-real",
        model_gateway=model_gateway,  # None = test mode (deterministic mock)
        bounded_context=bounded_context or _WAVE17_CONTEXT,
    )


# ── Test A: Basic SOP run ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_A_real_runtime_basic_sop_run():
    """
    Test A: DeepAgentsRuntime can run a basic SOP using real deepagents SDK.
    Uses MAIWModelGatewayChat in test mode (model_gateway=None).
    Verifies result has task_id, agent_id, sop_id, sop_version.
    """
    sop = _load_sop()
    runtime = DeepAgentsRuntime()
    definition = _make_definition()
    state = _make_state("task-A-basic")
    context = _make_context()

    result = await runtime.run_task(definition, sop, state, context)

    assert (
        result.task_id == "task-A-basic"
    ), f"Expected task_id='task-A-basic', got {result.task_id!r}"
    assert result.agent_id == definition.agent_id
    assert result.sop_id == sop.id
    assert result.sop_version == sop.version
    assert result.final_status in (
        AgentTaskStatus.WAITING_FOR_GOVERNANCE,
        AgentTaskStatus.COMPLETED,
        AgentTaskStatus.ESCALATED,
        AgentTaskStatus.FAILED,
    )
    assert result.completed_at is not None


# ── Test B: READ skill result injected via bounded_context ────────────────────


@pytest.mark.asyncio
async def test_B_read_skill_injected_via_bounded_context():
    """
    Test B: Real runtime can access READ skill result pre-loaded in bounded_context.
    The _build_maiw_tools adapter checks bounded_context for 'skill_result_<skill_id>'.
    """
    sop = _load_sop()
    runtime = DeepAgentsRuntime()
    definition = _make_definition()
    state = _make_state("task-B-skill")

    # Pre-load labor capacity skill result in bounded_context
    bounded_with_skill = dict(_WAVE17_CONTEXT)
    bounded_with_skill["skill_result_warehouse_labor_capacity"] = (
        '{"worker_count": 20, "available": 5, "constrained_zone": "A"}'
    )
    context = _make_context(bounded_context=bounded_with_skill)

    result = await runtime.run_task(definition, sop, state, context)

    # Runtime should complete (skill result available in bounded_context)
    assert result.task_id == "task-B-skill"
    assert result.final_status in (
        AgentTaskStatus.WAITING_FOR_GOVERNANCE,
        AgentTaskStatus.COMPLETED,
    )


# ── Test C: SubAgent specs built from SOP allowed_subagents ──────────────────


def test_C_subagent_specs_from_sop():
    """
    Test C: _build_subagent_specs builds SubAgent TypedDict entries from
    SOP allowed_subagents (labor, wave, equipment).
    """
    from maiw_agents.contracts.sop import SOPDefinition, SOPStep

    sop = SOPDefinition.model_construct(
        id="test.sop",
        version="1.0",
        agent="test_agent",
        objective="test",
        steps=[SOPStep(id="step1", action="no_op")],
        stop_conditions=["done"],
        allowed_capabilities=[],
        allowed_subagents=["labor", "wave", "equipment"],
        triggers=[],
        escalation=[],
        required_context=[],
    )

    context = _make_context()
    subagents = _build_subagent_specs(sop, context)

    assert len(subagents) == 3, f"Expected 3 SubAgent specs, got {len(subagents)}"

    names = {s["name"] if isinstance(s, dict) else s.name for s in subagents}
    assert "labor" in names
    assert "wave" in names
    assert "equipment" in names

    # Each SubAgent should have mode="isolated"
    for sa in subagents:
        mode = sa["mode"] if isinstance(sa, dict) else sa.mode
        assert mode == "isolated", f"SubAgent {sa!r} must have mode='isolated'"


# ── Test D: WRITE skills absent from built tools ──────────────────────────────


def test_D_write_skills_absent_from_tools():
    """
    Test D: _build_maiw_tools with WRITE-only capability IDs returns empty list.
    WRITE skills are hard-blocked at the adapter layer.
    """
    write_only_caps = [
        "warehouse.labor.assign_direct",
        "warehouse.wave.reprioritize_direct",
        "warehouse.equipment.assign_direct",
    ]
    context = _make_context()
    tools = _build_maiw_tools(context, write_only_caps)

    assert len(tools) == 0, (
        f"Expected 0 tools from WRITE-only cap list, got {len(tools)}: "
        f"{[getattr(t, 'name', str(t)) for t in tools]}"
    )


# ── Test E: WAITING_FOR_GOVERNANCE status ─────────────────────────────────────


@pytest.mark.asyncio
async def test_E_waiting_for_governance_status():
    """
    Test E: Real runtime returns WAITING_FOR_GOVERNANCE when mock model
    returns 'STOP: WAITING_FOR_GOVERNANCE' in its response.

    The MAIWModelGatewayChat mock always includes the governance stop signal
    when the SOP system prompt (which always contains 'WAITING_FOR_GOVERNANCE')
    is part of the messages.
    """
    sop = _load_sop()
    runtime = DeepAgentsRuntime()
    definition = _make_definition()
    state = _make_state("task-E-governance")
    context = _make_context()

    result = await runtime.run_task(definition, sop, state, context)

    assert result.final_status == AgentTaskStatus.WAITING_FOR_GOVERNANCE, (
        f"Expected WAITING_FOR_GOVERNANCE, got {result.final_status.value}. "
        "MAIWModelGatewayChat mock should trigger governance stop signal."
    )
    assert result.stop_reason == "WAITING_FOR_GOVERNANCE"
    assert result.task_id == "task-E-governance"


# ── Test F: resume_after_governance approved → COMPLETED ─────────────────────


@pytest.mark.asyncio
async def test_F_resume_after_governance_approved():
    """
    Test F: resume_after_governance with approved outcome → COMPLETED.
    """
    sop = _load_sop()
    runtime = DeepAgentsRuntime()
    definition = _make_definition()
    context = _make_context()

    # Build valid WAITING_FOR_GOVERNANCE state
    state = _make_state("task-F-resume")
    running_state = state.transition(AgentTaskStatus.RUNNING)
    waiting_state = running_state.transition(AgentTaskStatus.WAITING_FOR_GOVERNANCE)

    governance_outcome = {
        "proposal_id": "prop-F-001",
        "decision_outcome": "APPROVED",
        "execution_status": "EXECUTED",
        "resulting_context_snapshot_id": "snap-wave17-post",
    }

    result = await runtime.resume_after_governance(
        definition,
        sop,
        waiting_state,
        context,
        governance_outcome=governance_outcome,
    )

    assert (
        result.final_status == AgentTaskStatus.COMPLETED
    ), f"Expected COMPLETED after APPROVED governance, got {result.final_status.value}"
    assert result.stop_reason == "OBJECTIVE_MET"
    assert result.task_id == "task-F-resume"


# ── Test G: Large max_iterations — still terminates ───────────────────────────


@pytest.mark.asyncio
async def test_G_large_max_iterations_terminates():
    """
    Test G: With large max_iterations (50), runtime still terminates.
    Mock model terminates in 1 step → no recursion limit hit.
    """
    sop = _load_sop()
    runtime = DeepAgentsRuntime()
    definition = _make_definition(max_iterations=50)
    state = _make_state("task-G-large-iter")
    context = _make_context()

    result = await runtime.run_task(definition, sop, state, context)

    # Should terminate with a valid status
    assert result.final_status in (
        AgentTaskStatus.WAITING_FOR_GOVERNANCE,
        AgentTaskStatus.COMPLETED,
        AgentTaskStatus.ESCALATED,
        AgentTaskStatus.FAILED,
    )
    assert result.task_id == "task-G-large-iter"


# ── Test H: Missing context → runtime terminates gracefully ──────────────────


@pytest.mark.asyncio
async def test_H_missing_context_terminates_gracefully():
    """
    Test H: Empty bounded_context → runtime still terminates gracefully.
    No KeyError or AttributeError should escape.
    """
    sop = _load_sop()
    runtime = DeepAgentsRuntime()
    definition = _make_definition()
    state = _make_state("task-H-missing-ctx")
    context = _make_context(bounded_context={})

    # Should not raise — must return a valid AgentTaskResult
    result = await runtime.run_task(definition, sop, state, context)

    assert result.task_id == "task-H-missing-ctx"
    assert result.final_status in (
        AgentTaskStatus.WAITING_FOR_GOVERNANCE,
        AgentTaskStatus.COMPLETED,
        AgentTaskStatus.ESCALATED,
        AgentTaskStatus.FAILED,
    ), f"Unexpected terminal status: {result.final_status}"


# ── Additional: MAIWModelGatewayChat test-mode verification ──────────────────


def test_maiw_model_gateway_chat_test_mode_mock():
    """
    MAIWModelGatewayChat with model_gateway=None must return deterministic mock.
    When SOP system prompt is present (contains 'governance'), mock returns
    governance stop signal.
    """
    from langchain_core.messages import SystemMessage, HumanMessage

    chat = MAIWModelGatewayChat(model_gateway=None, trace_id="test-trace-mock")
    assert chat._llm_type == "maiw-model-gateway"

    # Simulate messages with governance keyword (from SOP system prompt)
    messages = [
        SystemMessage(content="GOVERNANCE BOUNDARY: WAITING_FOR_GOVERNANCE required."),
        HumanMessage(content="TASK ID: task-test"),
    ]
    result = chat._generate(messages)
    content = result.generations[0].message.content
    assert (
        "WAITING_FOR_GOVERNANCE" in content or "GOVERNANCE" in content.upper()
    ), f"Expected governance signal in mock response, got: {content!r}"


def test_maiw_model_gateway_chat_is_langchain_base_chat_model():
    """MAIWModelGatewayChat must inherit from langchain_core BaseChatModel."""
    from langchain_core.language_models import BaseChatModel

    chat = MAIWModelGatewayChat(model_gateway=None)
    assert isinstance(chat, BaseChatModel), (
        "MAIWModelGatewayChat must be a LangChain BaseChatModel "
        "for deepagents create_deep_agent(model=...) compatibility"
    )


def test_maiw_model_gateway_chat_bind_tools_returns_self():
    """
    bind_tools() must be implemented and return self (no-op for test mode).
    deepagents calls bind_tools to register tools with the model.
    """
    from langchain_core.tools import StructuredTool

    chat = MAIWModelGatewayChat(model_gateway=None)
    result = chat.bind_tools([])
    assert (
        result is chat
    ), "bind_tools() must return self (no-op) — MAIW mock model uses text output, not tool calls"
