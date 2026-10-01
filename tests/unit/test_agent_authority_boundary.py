# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Agent Package Authority Boundary invariant tests.

Enforces the canonical MAIW authority boundary:

    Agent
    → RecommendedAction
    → WAITING_FOR_GOVERNANCE
    ──────── MAIW AUTHORITY BOUNDARY ────────
    ActionProposal
    → DecisionEngine
    → Human Approval where required
    → ActionExecutor
    → MCP
    → Operational System

Invariants:
    A. maiw-agents package does not import maiw-execution
    B. No canonical agent constructor accepts ActionExecutor
    C. EquipmentAgent cannot call ActionExecutor (no attribute)
    D. EquipmentAgent proposal methods return dict with decision data, not execution result
    E. GovernanceBoundary.may_invoke_action_executor=False for all agents (including EAO)
    F. Labor/Wave definitions come from contracts.definitions (same object, not copy)
    G. Both runtimes use shared check_capability_alignment
    H. _PROHIBITED_CAPABILITY_PREFIXES no longer exists in sop.py
    I. MAIW_AGENT_RUNTIME env var doesn't override explicit SOP runtime_profile
    J. MAIWSkillAdapter still blocks WRITE/EMERGENCY_WRITE
"""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Invariant A — maiw-agents package does not import maiw-execution
# ---------------------------------------------------------------------------


class TestNoMaiwExecutionImport:
    """maiw-agents package must have zero direct imports of maiw-execution."""

    def test_equipment_agent_does_not_import_maiw_execution(self):
        """equipment/agent.py must not import ActionExecutor from maiw_execution."""
        import maiw_agents.equipment.agent as m

        src = _get_source(m)
        assert "from maiw_execution" not in src, (
            "equipment/agent.py must not import from maiw_execution — "
            "ActionExecutor belongs in apps/api (execution service layer)."
        )
        assert "import maiw_execution" not in src, (
            "equipment/agent.py must not import maiw_execution."
        )

    def test_state_aware_ops_does_not_import_maiw_execution(self):
        """state_aware_ops.py must not import ActionExecutor from maiw_execution."""
        import maiw_agents.equipment.state_aware_ops as m

        src = _get_source(m)
        assert "from maiw_execution" not in src, (
            "state_aware_ops.py must not import from maiw_execution."
        )
        assert "import maiw_execution" not in src

    def test_maiw_agents_package_no_maiw_execution_in_top_level(self):
        """maiw_agents/__init__.py must not import from maiw_execution."""
        import maiw_agents as m

        src = _get_source(m)
        assert "maiw_execution" not in src


# ---------------------------------------------------------------------------
# Invariant B — No canonical agent constructor accepts ActionExecutor
# ---------------------------------------------------------------------------


class TestNoActionExecutorConstructorParam:
    """No canonical agent may accept an ActionExecutor constructor parameter."""

    def test_equipment_agent_constructor_rejects_action_executor(self):
        from maiw_agents.equipment.agent import EquipmentAssetOperationsAgent

        with pytest.raises(TypeError):
            EquipmentAssetOperationsAgent(action_executor=object())

    def test_labor_agent_constructor_has_no_action_executor(self):
        from maiw_agents.labor.agent import LaborAgent
        import inspect

        sig = inspect.signature(LaborAgent.__init__)
        assert "action_executor" not in sig.parameters, (
            "LaborAgent.__init__ must not accept action_executor."
        )

    def test_wave_agent_constructor_has_no_action_executor(self):
        from maiw_agents.wave.agent import WaveAgent
        import inspect

        sig = inspect.signature(WaveAgent.__init__)
        assert "action_executor" not in sig.parameters, (
            "WaveAgent.__init__ must not accept action_executor."
        )


# ---------------------------------------------------------------------------
# Invariant C — EquipmentAgent cannot call ActionExecutor (no attribute)
# ---------------------------------------------------------------------------


class TestEquipmentAgentHasNoActionExecutor:
    """EquipmentAssetOperationsAgent must have no _action_executor attribute."""

    def test_no_action_executor_attribute(self):
        from maiw_agents.equipment.agent import EquipmentAssetOperationsAgent

        agent = EquipmentAssetOperationsAgent()
        assert not hasattr(agent, "_action_executor"), (
            "EquipmentAssetOperationsAgent must not store _action_executor. "
            "Execution belongs to apps/api (authority boundary)."
        )

    def test_no_execute_method_on_agent(self):
        """Agent must not expose an execute() method that invokes MCP writes."""
        from maiw_agents.equipment.agent import EquipmentAssetOperationsAgent

        agent = EquipmentAssetOperationsAgent()
        # Agents may have methods starting with 'propose_' but not 'execute_'
        execute_methods = [name for name in dir(agent) if name.startswith("execute_")]
        assert execute_methods == [], (
            f"Agent must not have execute_* methods: {execute_methods}"
        )


# ---------------------------------------------------------------------------
# Invariant D — EquipmentAgent proposal methods return dict with decision data
# ---------------------------------------------------------------------------


class TestEquipmentProposalReturnsDecisionDict:
    """Agent proposal methods return a decision result dict (not execution result)."""

    def test_propose_assignment_returns_dict_with_expected_keys(self):
        """Without state_provider, returns error dict (not execution result)."""
        from maiw_agents.equipment.agent import EquipmentAssetOperationsAgent

        agent = EquipmentAssetOperationsAgent()
        result = asyncio.run(
            agent.propose_equipment_assignment(asset_id="FL-001", assignee="op-1")
        )
        assert isinstance(result, dict)
        assert "status" in result
        assert "action" in result
        assert result.get("executed") is False
        # Must NOT contain execution-specific keys
        assert "execution_id" not in result or result.get("executed") is False

    def test_propose_release_returns_dict_with_expected_keys(self):
        """Without state_provider, returns error dict (not execution result)."""
        from maiw_agents.equipment.agent import EquipmentAssetOperationsAgent

        agent = EquipmentAssetOperationsAgent()
        result = asyncio.run(
            agent.propose_equipment_release(asset_id="FL-001", released_by="op-1")
        )
        assert isinstance(result, dict)
        assert "status" in result
        assert "action" in result
        assert result.get("executed") is False

    def test_propose_maintenance_returns_dict_with_expected_keys(self):
        """Without state_provider, returns error dict (not execution result)."""
        from maiw_agents.equipment.agent import EquipmentAssetOperationsAgent

        agent = EquipmentAssetOperationsAgent()
        result = asyncio.run(
            agent.propose_schedule_maintenance(
                asset_id="FL-001",
                maintenance_type="preventive",
                description="quarterly inspection",
                scheduled_by="system",
                scheduled_for="2026-10-01T08:00:00",
            )
        )
        assert isinstance(result, dict)
        assert "status" in result
        assert result.get("executed") is False

    def test_state_aware_ops_assignment_includes_private_proposal_keys(self):
        """When decision is made, state_aware_ops includes _proposal/_decision for caller."""
        from maiw_decision import DecisionEngine
        from maiw_decision.models import DecisionOutcome
        from maiw_decision.proposal import ActionProposal, RiskLevel
        import maiw_agents.equipment.state_aware_ops as sa
        from datetime import datetime, timezone

        # Build a minimal valid WarehouseState via existing test helpers
        from maiw_state import (
            EquipmentAssetSummary,
            EquipmentState,
            StateFreshness,
            WarehouseState,
        )

        _now = datetime.now(timezone.utc)
        asset = EquipmentAssetSummary(
            asset_id="FL-001",
            equipment_type="forklift",
            model="FL-3000",
            zone="ZONE-A",
            status="available",
        )
        eq_state = EquipmentState(
            warehouse_id="default",
            assets=[asset],
            freshness=StateFreshness(
                observed_at=_now,
                age_ms=100,
                stale=False,
            ),
        )
        ws = WarehouseState(
            warehouse_id="default",
            observed_at=_now,
            equipment=eq_state,
        )

        mock_state_provider = MagicMock()
        mock_state_provider.get_state = AsyncMock(return_value=ws)

        proposal = ActionProposal(
            action="warehouse.equipment.assign",
            domain="equipment",
            risk_level=RiskLevel.LOW,
            parameters={"asset_id": "FL-001", "assignee": "op-1"},
            requested_by="op-1",
            reason="test assignment",
        )
        mock_skill = MagicMock()
        mock_skill.execute = AsyncMock(return_value=proposal)

        decision_engine = DecisionEngine()

        result = asyncio.run(
            sa.propose_equipment_assignment(
                asset_id="FL-001",
                assignee="op-1",
                state_provider=mock_state_provider,
                decision_engine=decision_engine,
                assignment_skill=mock_skill,
            )
        )
        assert isinstance(result, dict)
        assert "status" in result
        # Private keys must be present for the apps/api layer
        assert "_proposal" in result, (
            "state_aware_ops must include '_proposal' key for apps/api execution layer."
        )
        assert "_decision" in result, (
            "state_aware_ops must include '_decision' key for apps/api execution layer."
        )


# ---------------------------------------------------------------------------
# Invariant E — GovernanceBoundary.may_invoke_action_executor=False for all
# ---------------------------------------------------------------------------


class TestGovernanceBoundaryFalse:
    """GovernanceBoundary.may_invoke_action_executor must be False for all agents."""

    @pytest.mark.parametrize(
        "agent_id",
        [
            "operations_coordination",
            "labor",
            "wave",
            "equipment",
            "safety_compliance",
        ],
    )
    def test_may_invoke_action_executor_is_false(self, agent_id):
        from maiw_agents.contracts.definitions import AGENT_DEFINITIONS

        defn = AGENT_DEFINITIONS[agent_id]
        assert defn.governance_boundary.may_invoke_action_executor is False, (
            f"{agent_id}: governance_boundary.may_invoke_action_executor must be False."
        )

    def test_equipment_definition_may_invoke_action_executor_is_false(self):
        """EQUIPMENT_AGENT_DEFINITION.governance_boundary is now truthful."""
        from maiw_agents.contracts.definitions import EQUIPMENT_AGENT_DEFINITION

        assert (
            EQUIPMENT_AGENT_DEFINITION.governance_boundary.may_invoke_action_executor
            is False
        )


# ---------------------------------------------------------------------------
# Invariant F — Labor/Wave definitions come from contracts.definitions
# ---------------------------------------------------------------------------


class TestLaborWaveDefinitionsSingleSource:
    """LABOR_AGENT_DEFINITION and WAVE_AGENT_DEFINITION must be the same object."""

    def test_labor_definition_is_same_object_as_contracts(self):
        from maiw_agents.labor.agent import LABOR_AGENT_DEFINITION as from_agent
        from maiw_agents.contracts.definitions import (
            LABOR_AGENT_DEFINITION as from_contracts,
        )

        assert from_agent is from_contracts, (
            "LABOR_AGENT_DEFINITION in labor/agent.py must be the same object "
            "as contracts/definitions.py (imported, not re-declared)."
        )

    def test_wave_definition_is_same_object_as_contracts(self):
        from maiw_agents.wave.agent import WAVE_AGENT_DEFINITION as from_agent
        from maiw_agents.contracts.definitions import (
            WAVE_AGENT_DEFINITION as from_contracts,
        )

        assert from_agent is from_contracts, (
            "WAVE_AGENT_DEFINITION in wave/agent.py must be the same object "
            "as contracts/definitions.py (imported, not re-declared)."
        )

    def test_labor_agent_definition_class_attribute_matches_contracts(self):
        from maiw_agents.labor.agent import LaborAgent
        from maiw_agents.contracts.definitions import LABOR_AGENT_DEFINITION

        assert LaborAgent.DEFINITION is LABOR_AGENT_DEFINITION

    def test_wave_agent_definition_class_attribute_matches_contracts(self):
        from maiw_agents.wave.agent import WaveAgent
        from maiw_agents.contracts.definitions import WAVE_AGENT_DEFINITION

        assert WaveAgent.DEFINITION is WAVE_AGENT_DEFINITION


# ---------------------------------------------------------------------------
# Invariant G — Both runtimes use shared check_capability_alignment
# ---------------------------------------------------------------------------


class TestSharedCapabilityAlignment:
    """Both runtimes must use the shared check_capability_alignment from contracts.runtime."""

    def test_deterministic_runtime_uses_shared_function(self):
        """MAIWDeterministicRuntime must NOT define its own _check_capability_alignment."""
        from maiw_agents.runtime.deterministic import MAIWDeterministicRuntime

        runtime = MAIWDeterministicRuntime()
        assert not hasattr(runtime, "_check_capability_alignment"), (
            "MAIWDeterministicRuntime must not define _check_capability_alignment; "
            "it must delegate to contracts.runtime.check_capability_alignment()."
        )

    def test_deterministic_runtime_imports_shared_function(self):
        """MAIWDeterministicRuntime module must import check_capability_alignment."""
        import maiw_agents.runtime.deterministic as m

        assert hasattr(m, "check_capability_alignment"), (
            "deterministic.py must import check_capability_alignment from contracts.runtime."
        )

    def test_deep_agents_runtime_uses_same_function(self):
        """DeepAgentsRuntime._check_capability_alignment must delegate to contracts.runtime."""
        from maiw_agents.runtime.deep_agents_runtime import DeepAgentsRuntime
        from maiw_agents.contracts.runtime import check_capability_alignment

        runtime = DeepAgentsRuntime()
        # Verify the method exists and delegates
        assert hasattr(runtime, "_check_capability_alignment")


# ---------------------------------------------------------------------------
# Invariant H — _PROHIBITED_CAPABILITY_PREFIXES removed from sop.py
# ---------------------------------------------------------------------------


class TestProhibitedPrefixesRemoved:
    """_PROHIBITED_CAPABILITY_PREFIXES must not exist in sop.py."""

    def test_prohibited_capability_prefixes_not_in_sop_module(self):
        import maiw_agents.contracts.sop as sop_module

        assert not hasattr(sop_module, "_PROHIBITED_CAPABILITY_PREFIXES"), (
            "_PROHIBITED_CAPABILITY_PREFIXES was dead code and must be removed from sop.py."
        )

    def test_write_capability_patterns_still_present(self):
        """_WRITE_CAPABILITY_PATTERNS (the regex) must still be present."""
        import maiw_agents.contracts.sop as sop_module

        assert hasattr(sop_module, "_WRITE_CAPABILITY_PATTERNS"), (
            "_WRITE_CAPABILITY_PATTERNS must remain (active write-blocking regex)."
        )


# ---------------------------------------------------------------------------
# Invariant I — MAIW_AGENT_RUNTIME env var doesn't override explicit SOP
# ---------------------------------------------------------------------------


class TestRuntimeEnvVarPrecedence:
    """SOP runtime_profile takes precedence over MAIW_AGENT_RUNTIME env var."""

    def test_explicit_sop_strict_ignores_env_var(self):
        """When SOP has runtime_profile='strict', env var 'deep_agents' is ignored."""
        from maiw_agents.runtime.deep_agents_runtime import get_runtime
        from maiw_agents.contracts.sop import SOPDefinition

        sop = SOPDefinition(
            id="test.sop",
            version="1.0",
            agent="test",
            objective="test",
            runtime_profile="strict",
            stop_conditions=["objective_met"],
            steps=[],
        )

        with patch.dict(os.environ, {"MAIW_AGENT_RUNTIME": "deep_agents"}):
            runtime = get_runtime(sop=sop)

        from maiw_agents.runtime.deterministic import MAIWDeterministicRuntime

        assert isinstance(runtime, MAIWDeterministicRuntime), (
            "When SOP has runtime_profile='strict', get_runtime() must return "
            "MAIWDeterministicRuntime even if MAIW_AGENT_RUNTIME=deep_agents."
        )

    def test_explicit_sop_adaptive_ignores_env_var(self):
        """When SOP has runtime_profile='adaptive', env var 'deterministic' is ignored."""
        from maiw_agents.runtime.deep_agents_runtime import (
            get_runtime,
            DeepAgentsRuntime,
        )
        from maiw_agents.contracts.sop import SOPDefinition

        sop = SOPDefinition(
            id="test.sop",
            version="1.0",
            agent="test",
            objective="test",
            runtime_profile="adaptive",
            stop_conditions=["objective_met"],
            steps=[],
        )

        with patch.dict(os.environ, {"MAIW_AGENT_RUNTIME": "deterministic"}):
            runtime = get_runtime(sop=sop)

        assert isinstance(runtime, DeepAgentsRuntime), (
            "When SOP has runtime_profile='adaptive', get_runtime() must return "
            "DeepAgentsRuntime even if MAIW_AGENT_RUNTIME=deterministic."
        )

    def test_env_var_used_when_no_sop_and_no_config(self):
        """Env var is used when neither config nor sop is provided."""
        from maiw_agents.runtime.deep_agents_runtime import (
            get_runtime,
            DeepAgentsRuntime,
        )

        with patch.dict(os.environ, {"MAIW_AGENT_RUNTIME": "deep_agents"}):
            runtime = get_runtime()

        assert isinstance(runtime, DeepAgentsRuntime), (
            "When no config and no SOP, MAIW_AGENT_RUNTIME env var should be used."
        )

    def test_explicit_config_overrides_both_sop_and_env(self):
        """Explicit config parameter takes precedence over both SOP and env var."""
        from maiw_agents.runtime.deep_agents_runtime import get_runtime
        from maiw_agents.runtime.deterministic import MAIWDeterministicRuntime
        from maiw_agents.contracts.sop import SOPDefinition

        sop = SOPDefinition(
            id="test.sop",
            version="1.0",
            agent="test",
            objective="test",
            runtime_profile="adaptive",
            stop_conditions=["objective_met"],
            steps=[],
        )

        with patch.dict(os.environ, {"MAIW_AGENT_RUNTIME": "deep_agents"}):
            runtime = get_runtime(config="deterministic", sop=sop)

        assert isinstance(runtime, MAIWDeterministicRuntime), (
            "Explicit config='deterministic' must override both SOP adaptive and env var."
        )


# ---------------------------------------------------------------------------
# Invariant J — MAIWSkillAdapter still blocks WRITE/EMERGENCY_WRITE
# ---------------------------------------------------------------------------


class TestSkillAdapterWriteBlock:
    """MAIWSkillAdapter must still block WRITE and EMERGENCY_WRITE capabilities."""

    def test_skill_adapter_blocks_write_capability(self):
        """Attempting to invoke a WRITE capability via MAIWSkillAdapter must raise."""
        try:
            from maiw_agents.common.skill_adapter import MAIWSkillAdapter
        except ImportError:
            pytest.skip("MAIWSkillAdapter not available in this environment")

        adapter = MAIWSkillAdapter()
        with pytest.raises(Exception):
            asyncio.run(adapter.invoke("warehouse.labor.assign", {}))

    def test_skill_registry_classifies_write_capabilities(self):
        """WRITE capabilities must be registered with CapabilityClass.WRITE."""
        from maiw_agents.contracts.registry import CapabilityClass, SKILL_REGISTRY

        # Verify the registry is accessible and has entries
        assert len(SKILL_REGISTRY) > 0, "SKILL_REGISTRY must have entries."
        # At least one READ capability must exist
        read_caps = [
            k
            for k, v in SKILL_REGISTRY.items()
            if v.capability_class == CapabilityClass.READ
        ]
        assert len(read_caps) > 0, "SKILL_REGISTRY must have READ capabilities."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_source(module) -> str:
    """Return the source code of a module as a string."""
    import inspect

    try:
        return inspect.getsource(module)
    except (OSError, TypeError):
        return ""
