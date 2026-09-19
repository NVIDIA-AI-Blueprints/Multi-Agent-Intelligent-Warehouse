# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 19A architecture invariant tests for DeepAgentsRuntime.

These tests verify that the MAIW agent architecture invariants hold across
the Phase 19A POC implementation. They are CI-permanent — must pass on every
commit to confirm that the architecture seam remains clean.

Invariants tested:
    1.  DeepAgentsRuntime has no imports from deep_agents, langchain, langgraph, nemoagent
    2.  MAIW contracts have ZERO imports from any agent framework
    3.  DeepAgentsRuntime cannot receive WRITE-classified skills
    4.  DeepAgentsRuntime cannot receive EMERGENCY_WRITE-classified skills
    5.  DeepAgentsRuntime uses ModelGateway adapter (not direct provider)
    6.  DeepAgentsRuntime uses MAIW AgentTaskState (not opaque framework state)
    7.  DeepAgentsRuntime uses MAIW SOPDefinition
    8.  Skill adapter blocks WRITE/EMERGENCY_WRITE skills
    9.  Skill adapter allows READ/ANALYTICAL skills
    10. PROPOSAL skills are allowed for recommendation building (not write execution)
    11. SOP conformance — mandatory governance handoff step not skippable
    12. State transitions follow MAIW valid transition map
    13. MAIW_AGENT_RUNTIME=deterministic uses MAIWDeterministicRuntime
    14. MAIW_AGENT_RUNTIME=deep_agents uses DeepAgentsRuntime
"""

from __future__ import annotations

import ast
import importlib
import inspect
import os
import sys
from pathlib import Path
from typing import Any

import pytest

# Ensure packages are importable
_REPO = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_REPO / "packages" / "maiw-agents"))

# ── Helpers ────────────────────────────────────────────────────────────────────

_FORBIDDEN_FRAMEWORKS = frozenset({"deep_agents", "langchain", "langgraph", "nemoagent"})

_RUNTIME_MODULE = _REPO / "packages" / "maiw-agents" / "maiw_agents" / "runtime"
_CONTRACTS_MODULE = _REPO / "packages" / "maiw-agents" / "maiw_agents" / "contracts"


def _get_imports(filepath: Path) -> set[str]:
    """Parse Python file and return all top-level import module names."""
    source = filepath.read_text()
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split(".")[0])
    return imports


def _check_no_forbidden_imports(filepath: Path, label: str) -> None:
    """Assert that no forbidden framework imports appear in the file."""
    imports = _get_imports(filepath)
    found = imports & _FORBIDDEN_FRAMEWORKS
    assert not found, (
        f"{label} ({filepath.name}) contains forbidden framework imports: {found}. "
        "MAIW architecture invariant violated: no LangChain/LangGraph/deep_agents/NemoClaw."
    )


# ── Invariant 1: DeepAgentsRuntime has no forbidden framework imports ──────────

def test_deep_agents_runtime_has_no_framework_imports():
    """DeepAgentsRuntime must NOT import deep_agents, langchain, langgraph, nemoagent."""
    filepath = _RUNTIME_MODULE / "deep_agents_runtime.py"
    assert filepath.exists(), f"Runtime file not found: {filepath}"
    _check_no_forbidden_imports(filepath, "DeepAgentsRuntime")


def test_model_adapter_has_no_framework_imports():
    """MAIWModelAdapter must NOT import deep_agents, langchain, langgraph, nemoagent."""
    filepath = _RUNTIME_MODULE / "model_adapter.py"
    assert filepath.exists(), f"Model adapter not found: {filepath}"
    _check_no_forbidden_imports(filepath, "MAIWModelAdapter")


def test_skill_adapter_has_no_framework_imports():
    """MAIWSkillAdapter must NOT import deep_agents, langchain, langgraph, nemoagent."""
    filepath = _RUNTIME_MODULE / "skill_adapter.py"
    assert filepath.exists(), f"Skill adapter not found: {filepath}"
    _check_no_forbidden_imports(filepath, "MAIWSkillAdapter")


# ── Invariant 2: MAIW contracts have ZERO framework imports ───────────────────

@pytest.mark.parametrize("contract_file", [
    "runtime.py", "agent.py", "task.py", "sop.py", "registry.py", "delegation.py"
])
def test_contracts_have_no_framework_imports(contract_file: str):
    """MAIW contract files must have ZERO imports from any agent framework."""
    filepath = _CONTRACTS_MODULE / contract_file
    assert filepath.exists(), f"Contract file not found: {filepath}"
    _check_no_forbidden_imports(filepath, f"contracts/{contract_file}")


# ── Invariant 3 & 4: WRITE/EMERGENCY_WRITE skills blocked ─────────────────────

def test_skill_adapter_blocks_write_skills():
    """MAIWSkillAdapter.get_agent_callable_tools() must not return WRITE skills."""
    from maiw_agents.runtime.skill_adapter import MAIWSkillAdapter
    from maiw_agents.contracts.registry import CapabilityClass

    adapter = MAIWSkillAdapter()
    tools = adapter.get_agent_callable_tools()

    write_tools = [
        t for t in tools
        if t.capability_class == CapabilityClass.WRITE
    ]
    assert len(write_tools) == 0, (
        f"Expected no WRITE tools, found: {[t.skill_id for t in write_tools]}"
    )


def test_skill_adapter_blocks_emergency_write_skills():
    """MAIWSkillAdapter must not return EMERGENCY_WRITE skills."""
    from maiw_agents.runtime.skill_adapter import MAIWSkillAdapter
    from maiw_agents.contracts.registry import CapabilityClass

    adapter = MAIWSkillAdapter()
    tools = adapter.get_agent_callable_tools()

    emergency_write_tools = [
        t for t in tools
        if t.capability_class == CapabilityClass.EMERGENCY_WRITE
    ]
    assert len(emergency_write_tools) == 0, (
        f"Expected no EMERGENCY_WRITE tools, found: {[t.skill_id for t in emergency_write_tools]}"
    )


def test_skill_adapter_blocks_write_even_when_explicitly_requested():
    """WRITE is blocked even if caller passes CapabilityClass.WRITE in allowed set."""
    from maiw_agents.runtime.skill_adapter import MAIWSkillAdapter
    from maiw_agents.contracts.registry import CapabilityClass

    adapter = MAIWSkillAdapter()
    # Attempt to include WRITE in allowed classes — must still be blocked
    tools = adapter.get_agent_callable_tools(
        allowed_capability_classes={
            CapabilityClass.READ,
            CapabilityClass.ANALYTICAL,
            CapabilityClass.WRITE,           # should be silently removed
            CapabilityClass.EMERGENCY_WRITE,  # should be silently removed
        }
    )
    write_tools = [
        t for t in tools
        if t.capability_class in (CapabilityClass.WRITE, CapabilityClass.EMERGENCY_WRITE)
    ]
    assert len(write_tools) == 0, (
        f"WRITE/EMERGENCY_WRITE blocked even when explicitly requested: "
        f"{[t.skill_id for t in write_tools]}"
    )


def test_skill_adapter_is_blocked_method_identifies_write():
    """MAIWSkillAdapter.is_blocked() must return True for WRITE skills."""
    from maiw_agents.runtime.skill_adapter import MAIWSkillAdapter

    adapter = MAIWSkillAdapter()
    # Known WRITE skill from SKILL_REGISTRY
    assert adapter.is_blocked("warehouse.labor.assign_direct"), (
        "warehouse.labor.assign_direct is WRITE — must be blocked"
    )
    assert adapter.is_blocked("warehouse.wave.reprioritize_direct"), (
        "warehouse.wave.reprioritize_direct is WRITE — must be blocked"
    )
    assert adapter.is_blocked("warehouse.equipment.assign_direct"), (
        "warehouse.equipment.assign_direct is WRITE — must be blocked"
    )


# ── Invariant 5: Uses ModelGateway adapter ────────────────────────────────────

def test_deep_agents_runtime_uses_model_adapter():
    """DeepAgentsRuntime must use MAIWModelGatewayChat (LangChain BaseChatModel → ModelGateway)."""
    from maiw_agents.runtime.deep_agents_runtime import DeepAgentsRuntime
    from maiw_agents.runtime.model_adapter import MAIWModelGatewayChat

    # Source inspection: run_task must instantiate MAIWModelGatewayChat
    source = inspect.getsource(DeepAgentsRuntime.run_task)
    assert "MAIWModelGatewayChat" in source, (
        "DeepAgentsRuntime.run_task must use MAIWModelGatewayChat — "
        "a LangChain BaseChatModel that routes all calls through MAIW ModelGateway"
    )


def test_model_adapter_wraps_context_gateway():
    """MAIWModelAdapter must wrap model_gateway from context, not instantiate providers."""
    from maiw_agents.runtime.model_adapter import MAIWModelAdapter

    # In test mode (model_gateway=None), should return mock
    import asyncio

    async def _run() -> dict:
        adapter = MAIWModelAdapter(model_gateway=None)
        response = await adapter.generate("test prompt", trace_id="trace-test")
        assert response.get("mock") is True
        assert response.get("trace_id") == "trace-test"
        assert adapter.call_count == 1
        return response

    asyncio.run(_run())


# ── Invariant 6: Uses MAIW AgentTaskState ────────────────────────────────────

def test_deep_agents_runtime_accepts_agent_task_state():
    """DeepAgentsRuntime.run_task signature must accept AgentTaskState."""
    from maiw_agents.runtime.deep_agents_runtime import DeepAgentsRuntime
    from maiw_agents.contracts.task import AgentTaskState

    sig = inspect.signature(DeepAgentsRuntime.run_task)
    params = list(sig.parameters.keys())
    assert "state" in params, "run_task must accept 'state' parameter"

    # Verify type annotation references AgentTaskState
    source = inspect.getsource(DeepAgentsRuntime.run_task)
    assert "AgentTaskState" in source, (
        "run_task must use MAIW AgentTaskState, not opaque framework state"
    )


def test_agent_task_state_transition_is_validated():
    """AgentTaskState.transition() must enforce the valid transition map."""
    from maiw_agents.contracts.task import AgentTaskState, AgentTaskStatus

    state = AgentTaskState(
        task_id="test-inv-1",
        agent_id="test_agent",
        sop_id="test.sop",
        sop_version="1.0",
        objective="test",
    )

    # Valid transition
    state2 = state.transition(AgentTaskStatus.RUNNING)
    assert state2.status == AgentTaskStatus.RUNNING

    # Invalid transition — PENDING → WAITING_FOR_GOVERNANCE (not allowed)
    with pytest.raises(ValueError, match="Invalid AgentTaskState transition"):
        state.transition(AgentTaskStatus.WAITING_FOR_GOVERNANCE)


def test_agent_task_state_terminal_states_have_no_transitions():
    """Terminal states (COMPLETED, ESCALATED, FAILED) must not allow further transitions."""
    from maiw_agents.contracts.task import AgentTaskState, AgentTaskStatus

    state = AgentTaskState(
        task_id="test-inv-terminal",
        agent_id="test_agent",
        sop_id="test.sop",
        sop_version="1.0",
        objective="test",
        status=AgentTaskStatus.COMPLETED,
    )

    with pytest.raises(ValueError):
        state.transition(AgentTaskStatus.RUNNING)


# ── Invariant 7: Uses MAIW SOPDefinition ─────────────────────────────────────

def test_deep_agents_runtime_accepts_sop_definition():
    """DeepAgentsRuntime.run_task signature must accept SOPDefinition."""
    from maiw_agents.runtime.deep_agents_runtime import DeepAgentsRuntime

    sig = inspect.signature(DeepAgentsRuntime.run_task)
    params = list(sig.parameters.keys())
    assert "sop" in params, "run_task must accept 'sop' (SOPDefinition) parameter"

    source = inspect.getsource(DeepAgentsRuntime.run_task)
    assert "SOPDefinition" in source or "sop.steps" in source, (
        "run_task must use MAIW SOPDefinition"
    )


# ── Invariant 8 & 9: Skill adapter READ/ANALYTICAL allowed ───────────────────

def test_skill_adapter_allows_read_skills():
    """MAIWSkillAdapter must expose READ-classified skills."""
    from maiw_agents.runtime.skill_adapter import MAIWSkillAdapter
    from maiw_agents.contracts.registry import CapabilityClass

    adapter = MAIWSkillAdapter()
    tools = adapter.get_agent_callable_tools()

    read_tools = [t for t in tools if t.capability_class == CapabilityClass.READ]
    assert len(read_tools) >= 1, (
        f"Expected READ skills to be exposed, found zero. Total tools: {len(tools)}"
    )


def test_skill_adapter_allows_analytical_skills():
    """MAIWSkillAdapter must expose ANALYTICAL-classified skills."""
    from maiw_agents.runtime.skill_adapter import MAIWSkillAdapter
    from maiw_agents.contracts.registry import CapabilityClass

    adapter = MAIWSkillAdapter()
    tools = adapter.get_agent_callable_tools()

    analytical_tools = [t for t in tools if t.capability_class == CapabilityClass.ANALYTICAL]
    assert len(analytical_tools) >= 1, (
        f"Expected ANALYTICAL skills to be exposed, found zero. Total tools: {len(tools)}"
    )


# ── Invariant 10: PROPOSAL skills allowed for recommendation ──────────────────

def test_skill_adapter_allows_proposal_skills_when_opted_in():
    """PROPOSAL skills are allowed when explicitly included in capability classes."""
    from maiw_agents.runtime.skill_adapter import MAIWSkillAdapter
    from maiw_agents.contracts.registry import CapabilityClass

    adapter = MAIWSkillAdapter()
    tools = adapter.get_agent_callable_tools(
        allowed_capability_classes={
            CapabilityClass.READ,
            CapabilityClass.ANALYTICAL,
            CapabilityClass.PROPOSAL,
        }
    )

    proposal_tools = [t for t in tools if t.capability_class == CapabilityClass.PROPOSAL]
    assert len(proposal_tools) >= 1, (
        "PROPOSAL skills should be accessible when explicitly included"
    )
    # Verify none are write
    for t in proposal_tools:
        assert not t.is_write, f"PROPOSAL skill {t.skill_id} must not be marked as write"


def test_skill_adapter_excludes_proposal_by_default():
    """PROPOSAL skills are NOT included in the default (READ+ANALYTICAL only) set."""
    from maiw_agents.runtime.skill_adapter import MAIWSkillAdapter
    from maiw_agents.contracts.registry import CapabilityClass

    adapter = MAIWSkillAdapter()
    default_tools = adapter.get_agent_callable_tools()  # default: READ+ANALYTICAL

    proposal_tools = [t for t in default_tools if t.capability_class == CapabilityClass.PROPOSAL]
    assert len(proposal_tools) == 0, (
        "PROPOSAL skills should not appear in default READ+ANALYTICAL tool set"
    )


# ── Invariant 11: SOP conformance — governance handoff mandatory ──────────────

@pytest.mark.asyncio
async def test_governance_handoff_cannot_be_skipped():
    """
    The emit_recommended_action step must ALWAYS transition to WAITING_FOR_GOVERNANCE.
    It cannot be bypassed, skipped, or auto-approved.
    """
    from pathlib import Path
    from maiw_agents.contracts.sop import load_sop
    from maiw_agents.contracts.agent import AgentDefinition, TerminationPolicy
    from maiw_agents.contracts.task import AgentTaskState, AgentTaskStatus
    from maiw_agents.contracts.runtime import AgentExecutionContext
    from maiw_agents.runtime import DeepAgentsRuntime

    sop_path = _REPO / "agents" / "sops" / "operations_coordination" / "wave_risk_resolution.v1.yaml"
    if not sop_path.exists():
        pytest.skip("SOP file not found")

    sop = load_sop(sop_path)
    runtime = DeepAgentsRuntime()

    definition = AgentDefinition(
        agent_id="operations_coordination",
        version="1.0",
        objective="test governance invariant",
        domain="operations",
        allowed_capabilities=[
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
        ],
        allowed_subagents=["labor", "wave", "equipment"],
        output_contract="RecommendedAction",
        termination_policy=TerminationPolicy(max_iterations=30),
    )
    state = AgentTaskState(
        task_id="task-gov-invariant",
        agent_id="operations_coordination",
        sop_id=sop.id,
        sop_version=sop.version,
        objective="governance handoff invariant test",
    )
    context = AgentExecutionContext(
        warehouse_id="wh-test",
        trace_id="trace-gov-invariant",
        model_gateway=None,
        bounded_context={
            "wave_id": "wave-17",
            "at_risk_count": 3,
            "carrier_cutoff_minutes": 47,
            "primary_constraint": "labor",
            "domains_affected": "labor",
        },
    )

    result = await runtime.run_task(definition, sop, state, context)

    assert result.final_status == AgentTaskStatus.WAITING_FOR_GOVERNANCE, (
        f"Governance handoff must be mandatory — got {result.final_status.value} instead. "
        "The emit_recommended_action step cannot be skipped or auto-approved."
    )


# ── Invariant 12: State transitions follow MAIW valid transition map ──────────

def test_maiw_valid_transitions_are_enforced():
    """
    The MAIW _VALID_TRANSITIONS map must reject all invalid transitions.
    Spot-check key invalid transitions.
    """
    from maiw_agents.contracts.task import is_valid_transition, AgentTaskStatus

    # Valid transitions
    assert is_valid_transition(AgentTaskStatus.PENDING, AgentTaskStatus.RUNNING)
    assert is_valid_transition(AgentTaskStatus.RUNNING, AgentTaskStatus.WAITING_FOR_GOVERNANCE)
    assert is_valid_transition(AgentTaskStatus.WAITING_FOR_GOVERNANCE, AgentTaskStatus.OBSERVING_OUTCOME)
    assert is_valid_transition(AgentTaskStatus.OBSERVING_OUTCOME, AgentTaskStatus.COMPLETED)

    # Invalid transitions
    assert not is_valid_transition(AgentTaskStatus.PENDING, AgentTaskStatus.WAITING_FOR_GOVERNANCE)
    assert not is_valid_transition(AgentTaskStatus.COMPLETED, AgentTaskStatus.RUNNING)
    assert not is_valid_transition(AgentTaskStatus.ESCALATED, AgentTaskStatus.RUNNING)
    assert not is_valid_transition(AgentTaskStatus.FAILED, AgentTaskStatus.COMPLETED)
    assert not is_valid_transition(AgentTaskStatus.WAITING_FOR_GOVERNANCE, AgentTaskStatus.COMPLETED)


# ── Invariant 13: MAIW_AGENT_RUNTIME=deterministic → MAIWDeterministicRuntime ─

def test_get_runtime_default_is_deterministic():
    """get_runtime() with no args returns MAIWDeterministicRuntime."""
    from maiw_agents.runtime.deep_agents_runtime import get_runtime
    from maiw_agents.runtime import MAIWDeterministicRuntime

    # Unset env var to test default
    os.environ.pop("MAIW_AGENT_RUNTIME", None)
    rt = get_runtime()
    assert isinstance(rt, MAIWDeterministicRuntime), (
        f"Default runtime should be MAIWDeterministicRuntime, got {type(rt).__name__}"
    )


def test_get_runtime_env_deterministic():
    """MAIW_AGENT_RUNTIME=deterministic → MAIWDeterministicRuntime."""
    from maiw_agents.runtime.deep_agents_runtime import get_runtime
    from maiw_agents.runtime import MAIWDeterministicRuntime

    os.environ["MAIW_AGENT_RUNTIME"] = "deterministic"
    try:
        rt = get_runtime()
        assert isinstance(rt, MAIWDeterministicRuntime)
    finally:
        os.environ.pop("MAIW_AGENT_RUNTIME", None)


# ── Invariant 14: MAIW_AGENT_RUNTIME=deep_agents → DeepAgentsRuntime ──────────

def test_get_runtime_env_deep_agents():
    """MAIW_AGENT_RUNTIME=deep_agents → DeepAgentsRuntime."""
    from maiw_agents.runtime.deep_agents_runtime import get_runtime, DeepAgentsRuntime

    os.environ["MAIW_AGENT_RUNTIME"] = "deep_agents"
    try:
        rt = get_runtime()
        assert isinstance(rt, DeepAgentsRuntime), (
            f"Expected DeepAgentsRuntime, got {type(rt).__name__}"
        )
    finally:
        os.environ.pop("MAIW_AGENT_RUNTIME", None)


def test_get_runtime_explicit_deep_agents():
    """get_runtime('deep_agents') returns DeepAgentsRuntime."""
    from maiw_agents.runtime.deep_agents_runtime import get_runtime, DeepAgentsRuntime

    os.environ.pop("MAIW_AGENT_RUNTIME", None)
    rt = get_runtime("deep_agents")
    assert isinstance(rt, DeepAgentsRuntime)


def test_get_runtime_explicit_deterministic():
    """get_runtime('deterministic') returns MAIWDeterministicRuntime."""
    from maiw_agents.runtime.deep_agents_runtime import get_runtime
    from maiw_agents.runtime import MAIWDeterministicRuntime

    os.environ.pop("MAIW_AGENT_RUNTIME", None)
    rt = get_runtime("deterministic")
    assert isinstance(rt, MAIWDeterministicRuntime)


# ── Additional: AgentRuntime Protocol compliance ──────────────────────────────

def test_deep_agents_runtime_satisfies_agent_runtime_protocol():
    """DeepAgentsRuntime must satisfy the AgentRuntime Protocol (runtime_checkable)."""
    from maiw_agents.runtime.deep_agents_runtime import DeepAgentsRuntime
    from maiw_agents.contracts.runtime import AgentRuntime

    rt = DeepAgentsRuntime()
    assert isinstance(rt, AgentRuntime), (
        "DeepAgentsRuntime must satisfy the AgentRuntime Protocol"
    )


def test_deterministic_runtime_satisfies_agent_runtime_protocol():
    """MAIWDeterministicRuntime must also satisfy the AgentRuntime Protocol."""
    from maiw_agents.runtime import MAIWDeterministicRuntime
    from maiw_agents.contracts.runtime import AgentRuntime

    rt = MAIWDeterministicRuntime()
    assert isinstance(rt, AgentRuntime), (
        "MAIWDeterministicRuntime must satisfy the AgentRuntime Protocol"
    )


# ── Phase 19A Real Integration Invariants (19A.6–19A.9) ─────────────────────

def test_deepagents_real_package_is_installed():
    """deepagents (real PyPI package) must be installed for Phase 19A real integration."""
    import importlib.util
    spec = importlib.util.find_spec("deepagents")
    assert spec is not None, (
        "deepagents package not found. Install: pip install 'maiw-agents[deep-agents]' "
        "or pip install deepagents==0.7.15"
    )


def test_deep_agents_runtime_does_not_import_openai_or_anthropic_directly():
    """
    DeepAgentsRuntime must NOT directly import openai or anthropic.
    All model calls go through MAIWModelGatewayChat → MAIW ModelGateway.
    """
    filepath = _RUNTIME_MODULE / "deep_agents_runtime.py"
    assert filepath.exists()
    source = filepath.read_text()
    tree = ast.parse(source)
    direct_imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                direct_imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                direct_imports.add(node.module.split(".")[0])
    forbidden_direct = frozenset({"openai", "anthropic"})
    found = direct_imports & forbidden_direct
    assert not found, (
        f"DeepAgentsRuntime must NOT directly import {found}. "
        "All model calls route through MAIWModelGatewayChat → MAIW ModelGateway."
    )


def test_maiw_model_gateway_chat_llm_type():
    """MAIWModelGatewayChat._llm_type must be 'maiw-model-gateway'."""
    from maiw_agents.runtime.model_adapter import MAIWModelGatewayChat
    chat = MAIWModelGatewayChat(model_gateway=None)
    assert chat._llm_type == "maiw-model-gateway", (
        f"Expected _llm_type='maiw-model-gateway', got {chat._llm_type!r}"
    )


def test_build_maiw_tools_blocks_write_capabilities():
    """
    _build_maiw_tools() must return zero tools when called with only WRITE capability IDs.
    WRITE skills are hard-blocked at the adapter layer, not prompt-only.
    """
    from maiw_agents.runtime.deep_agents_runtime import _build_maiw_tools
    from maiw_agents.contracts.runtime import AgentExecutionContext

    write_caps = [
        "warehouse.labor.assign_direct",
        "warehouse.wave.reprioritize_direct",
        "warehouse.equipment.assign_direct",
    ]

    context = AgentExecutionContext(
        warehouse_id="wh-test",
        trace_id="trace-write-block-test",
        bounded_context={},
    )

    tools = _build_maiw_tools(context, write_caps)
    assert len(tools) == 0, (
        f"Expected 0 tools from WRITE-only capability list, got {len(tools)}: "
        f"{[getattr(t, 'name', str(t)) for t in tools]}"
    )


def test_simulated_runtime_is_preserved_as_private():
    """_SimulatedDeepAgentsRuntime must still exist as private (backward compat / reference)."""
    from maiw_agents.runtime.deep_agents_runtime import _SimulatedDeepAgentsRuntime
    assert _SimulatedDeepAgentsRuntime is not None
    rt = _SimulatedDeepAgentsRuntime()
    assert hasattr(rt, "run_task")
    assert hasattr(rt, "resume_after_governance")


def test_model_adapter_has_no_framework_imports_updated():
    """
    model_adapter.py may import langchain_core (for MAIWModelGatewayChat)
    but must NOT import deep_agents, langchain (base), langgraph, nemoagent.
    """
    filepath = _RUNTIME_MODULE / "model_adapter.py"
    assert filepath.exists()
    imports = _get_imports(filepath)
    # langchain_core is allowed (BaseChatModel for real integration)
    # deep_agents, langchain (base), langgraph, nemoagent are forbidden
    still_forbidden = frozenset({"deep_agents", "langchain", "langgraph", "nemoagent"})
    found = imports & still_forbidden
    assert not found, (
        f"model_adapter.py contains still-forbidden framework imports: {found}"
    )
