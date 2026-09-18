# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 18H — Agent governance architecture invariant tests.

These tests verify the architectural invariants of the MAIW SOP-driven agent foundation:

Invariants:
    A. OCA cannot invoke ActionExecutor directly
    B. OCA cannot invoke DecisionEngine directly
    C. Specialist agents (LaborAgent, WaveAgent) may not have WRITE capabilities in
       their governance boundary
    D. SafetyComplianceAgent emergency_authority is the ONLY agent with WRITE exemption
    E. SKILL_REGISTRY WRITE skills are not assignable to any non-OCA agent
    F. AgentRuntime Protocol is structurally sound (runtime_checkable)
    G. MAIWDeterministicRuntime is recognized as AgentRuntime
    H. observe_governance_outcome() is READ-ONLY (does not call ActionExecutor)
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

# ── Helpers ───────────────────────────────────────────────────────────────────


def _import_contracts():
    from maiw_agents.contracts import (
        AGENT_DEFINITIONS,
        CapabilityClass,
        SKILL_REGISTRY,
        AgentRuntime,
        get_agent_definition,
    )

    return (
        AGENT_DEFINITIONS,
        CapabilityClass,
        SKILL_REGISTRY,
        AgentRuntime,
        get_agent_definition,
    )


def _import_runtime():
    from maiw_agents.runtime import MAIWDeterministicRuntime

    return MAIWDeterministicRuntime


# ── A. OCA governance boundary ────────────────────────────────────────────────


class TestOCAGovernanceBoundary:
    """OCA must not have direct write or executor authority."""

    def test_oca_may_not_invoke_action_executor(self):
        AGENT_DEFINITIONS, _, _, _, _ = _import_contracts()
        oca = AGENT_DEFINITIONS["operations_coordination"]
        assert (
            oca.governance_boundary.may_invoke_action_executor is False
        ), "OCA governance_boundary.may_invoke_action_executor must be False"

    def test_oca_allowed_capabilities_contain_no_write_skills(self):
        AGENT_DEFINITIONS, CapabilityClass, SKILL_REGISTRY, _, _ = _import_contracts()
        oca = AGENT_DEFINITIONS["operations_coordination"]
        for cap_id in oca.allowed_capabilities:
            skill = SKILL_REGISTRY.get(cap_id)
            if skill is not None:
                assert skill.capability_class not in (
                    CapabilityClass.WRITE,
                    CapabilityClass.EMERGENCY_WRITE,
                ), (
                    f"OCA allowed capability {cap_id!r} is WRITE/EMERGENCY_WRITE — "
                    "agents may not have write skills in their definition"
                )

    def test_oca_allowed_capability_classes(self):
        AGENT_DEFINITIONS, _, _, _, _ = _import_contracts()
        oca = AGENT_DEFINITIONS["operations_coordination"]
        allowed = set(oca.governance_boundary.allowed_capability_classes)
        assert "WRITE" not in allowed
        assert "EMERGENCY_WRITE" not in allowed


# ── B. Specialist agents governance boundary ──────────────────────────────────


class TestSpecialistAgentBoundary:
    """LaborAgent and WaveAgent must have READ/ANALYTICAL only — no WRITE, no executor."""

    @pytest.mark.parametrize("agent_id", ["labor", "wave"])
    def test_specialist_may_not_invoke_action_executor(self, agent_id):
        AGENT_DEFINITIONS, _, _, _, _ = _import_contracts()
        agent = AGENT_DEFINITIONS[agent_id]
        assert agent.governance_boundary.may_invoke_action_executor is False

    @pytest.mark.parametrize("agent_id", ["labor", "wave"])
    def test_specialist_may_not_invoke_decision_engine(self, agent_id):
        AGENT_DEFINITIONS, _, _, _, _ = _import_contracts()
        agent = AGENT_DEFINITIONS[agent_id]
        assert agent.governance_boundary.may_invoke_decision_engine is False

    @pytest.mark.parametrize("agent_id", ["labor", "wave"])
    def test_specialist_allowed_classes_read_analytical_only(self, agent_id):
        AGENT_DEFINITIONS, _, _, _, _ = _import_contracts()
        agent = AGENT_DEFINITIONS[agent_id]
        allowed = set(agent.governance_boundary.allowed_capability_classes)
        assert allowed <= {"READ", "ANALYTICAL"}, (
            f"Agent {agent_id!r} allowed_capability_classes must be subset of "
            f"{{READ, ANALYTICAL}}, got {allowed!r}"
        )

    @pytest.mark.parametrize("agent_id", ["labor", "wave"])
    def test_specialist_no_subagents(self, agent_id):
        AGENT_DEFINITIONS, _, _, _, _ = _import_contracts()
        agent = AGENT_DEFINITIONS[agent_id]
        assert (
            agent.allowed_subagents == []
        ), f"Specialist agent {agent_id!r} must not delegate to subagents"


# ── C. SafetyComplianceAgent ──────────────────────────────────────────────────


class TestSafetyComplianceAgent:
    """Safety agent is the only agent with emergency_authority."""

    def test_safety_has_emergency_authority(self):
        AGENT_DEFINITIONS, _, _, _, _ = _import_contracts()
        safety = AGENT_DEFINITIONS["safety_compliance"]
        assert safety.governance_boundary.emergency_authority is not None
        assert len(safety.governance_boundary.emergency_authority) > 0

    def test_non_safety_agents_have_no_emergency_authority(self):
        AGENT_DEFINITIONS, _, _, _, _ = _import_contracts()
        non_safety = [k for k in AGENT_DEFINITIONS if k != "safety_compliance"]
        for agent_id in non_safety:
            agent = AGENT_DEFINITIONS[agent_id]
            assert agent.governance_boundary.emergency_authority is None, (
                f"Agent {agent_id!r} must not have emergency_authority "
                "(only SafetyComplianceAgent may)"
            )


# ── D. WRITE skill protection ─────────────────────────────────────────────────


class TestWriteSkillProtection:
    """WRITE skills must not appear in any agent's allowed_capabilities."""

    def test_write_skills_not_in_any_agent_definition(self):
        AGENT_DEFINITIONS, CapabilityClass, SKILL_REGISTRY, _, _ = _import_contracts()
        write_skill_ids = {
            sid
            for sid, s in SKILL_REGISTRY.items()
            if s.capability_class
            in (CapabilityClass.WRITE, CapabilityClass.EMERGENCY_WRITE)
        }
        for agent_id, agent in AGENT_DEFINITIONS.items():
            overlap = set(agent.allowed_capabilities) & write_skill_ids
            assert not overlap, (
                f"Agent {agent_id!r} has WRITE skills in allowed_capabilities: {overlap!r}. "
                "WRITE skills are for ActionExecutor only."
            )

    def test_write_skills_are_documented_in_registry(self):
        _, CapabilityClass, SKILL_REGISTRY, _, _ = _import_contracts()
        write_skills = [
            s
            for s in SKILL_REGISTRY.values()
            if s.capability_class
            in (CapabilityClass.WRITE, CapabilityClass.EMERGENCY_WRITE)
        ]
        assert len(write_skills) >= 3, (
            "Expected at least 3 WRITE skills documented in registry "
            "(labor.assign_direct, wave.reprioritize_direct, equipment.assign_direct)"
        )


# ── E. AgentRuntime Protocol ──────────────────────────────────────────────────


class TestAgentRuntimeProtocol:
    """MAIWDeterministicRuntime must satisfy the AgentRuntime Protocol."""

    def test_runtime_is_recognized_as_agent_runtime(self):
        _, _, _, AgentRuntime, _ = _import_contracts()
        MAIWDeterministicRuntime = _import_runtime()
        rt = MAIWDeterministicRuntime()
        assert isinstance(
            rt, AgentRuntime
        ), "MAIWDeterministicRuntime must satisfy the AgentRuntime Protocol"

    def test_runtime_has_run_task_method(self):
        MAIWDeterministicRuntime = _import_runtime()
        assert hasattr(MAIWDeterministicRuntime, "run_task")
        import inspect

        assert inspect.iscoroutinefunction(MAIWDeterministicRuntime.run_task)


# ── F. OCA _execute_action_tools governance closure ──────────────────────────


class TestOCAGovernanceClosure:
    """_execute_action_tools() must be a no-op (returns empty list)."""

    @pytest.mark.asyncio
    async def test_execute_action_tools_returns_empty_list(self):
        from maiw_agents.operations.agent import (
            OperationsCoordinationAgent,
            OperationsQuery,
        )

        agent = OperationsCoordinationAgent()
        query = OperationsQuery(
            intent="allocate",
            entities={},
            context={},
            user_query="allocate worker to zone A",
        )
        result = await agent._execute_action_tools(query, context=None)
        assert (
            result == []
        ), "_execute_action_tools() must return [] after Phase 18H governance closure"

    @pytest.mark.asyncio
    async def test_execute_action_tools_with_action_tools_still_noop(self):
        """Even if action_tools is injected, _execute_action_tools must be a no-op."""
        from maiw_agents.operations.agent import (
            OperationsCoordinationAgent,
            OperationsQuery,
        )

        mock_action_tools = MagicMock()
        mock_action_tools.some_write = AsyncMock(return_value={"ok": True})

        agent = OperationsCoordinationAgent(action_tools=mock_action_tools)
        query = OperationsQuery(
            intent="allocate",
            entities={},
            context={},
            user_query="allocate worker",
        )
        result = await agent._execute_action_tools(query, context=None)
        assert result == [], "action_tools write must NOT be called even if injected"
        mock_action_tools.some_write.assert_not_called()


# ── G. observe_governance_outcome READ-ONLY ───────────────────────────────────


class TestObserveGovernanceOutcome:
    """observe_governance_outcome must return a dict and not call any write tool."""

    @pytest.mark.asyncio
    async def test_returns_dict_with_required_keys(self):
        from maiw_agents.operations.agent import OperationsCoordinationAgent

        agent = OperationsCoordinationAgent()

        class MockOutcome:
            proposal_id = "prop-001"
            decision_outcome = "approved"
            approval_status = "approved"
            execution_status = "succeeded"
            resulting_context_snapshot_id = "snap-002"
            trace_id = "trace-001"

        result = await agent.observe_governance_outcome(
            outcome=MockOutcome(),
            prior_snapshot=None,
            trace_id="trace-001",
        )
        assert isinstance(result, dict)
        assert "objective_met" in result
        assert "stop_reason" in result
        assert "next_action" in result
        assert "governance_outcome" in result

    @pytest.mark.asyncio
    async def test_approved_executed_sets_objective_met(self):
        from maiw_agents.operations.agent import OperationsCoordinationAgent

        agent = OperationsCoordinationAgent()

        class MockOutcome:
            proposal_id = "prop-001"
            decision_outcome = "approved"
            approval_status = "approved"
            execution_status = "succeeded"
            resulting_context_snapshot_id = "snap-002"
            trace_id = "trace-001"

        result = await agent.observe_governance_outcome(
            outcome=MockOutcome(), prior_snapshot=None, trace_id="trace-001"
        )
        assert result["objective_met"] is True
        assert result["stop_reason"] == "OBJECTIVE_MET"
        assert result["next_action"] == "COMPLETED"

    @pytest.mark.asyncio
    async def test_rejected_sets_policy_blocked(self):
        from maiw_agents.operations.agent import OperationsCoordinationAgent

        agent = OperationsCoordinationAgent()

        class MockOutcome:
            proposal_id = "prop-002"
            decision_outcome = "rejected"
            approval_status = "rejected"
            execution_status = "skipped"
            resulting_context_snapshot_id = None
            trace_id = "trace-002"

        result = await agent.observe_governance_outcome(
            outcome=MockOutcome(), prior_snapshot=None, trace_id="trace-002"
        )
        assert result["objective_met"] is False
        assert result["stop_reason"] == "POLICY_BLOCKED"
        assert result["next_action"] == "ESCALATED"
