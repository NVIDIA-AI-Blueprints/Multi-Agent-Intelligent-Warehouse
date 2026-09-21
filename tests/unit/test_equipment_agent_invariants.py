# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Equipment agent architecture invariant tests — pre-UX-1G hardening.

Enforces the write-path invariant:
    RecommendedAction → Governance → ActionProposal → DecisionEngine → ActionExecutor → MCP

Invariants verified:
    A.  Agent with no decision_engine returns error (no direct write) on assignment
    B.  Agent with no decision_engine returns error (no direct write) on release
    C.  Agent with no decision_engine returns error (no direct write) on maintenance
    D.  Agent with decision_engine routes to governed path, never to asset_tools
    E.  NoOpActionExecutor is wired by default (agent cannot execute without executor)
    F.  No _legacy_assign method exists on EquipmentAssetOperationsAgent
    G.  agent.asset_tools read-only methods (get_status, get_telemetry) are not blocked
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maiw_agents.equipment.agent import EquipmentAssetOperationsAgent
from maiw_execution import NoOpActionExecutor

# ---------------------------------------------------------------------------
# Invariant A — assignment with no decision_engine returns error, no write
# ---------------------------------------------------------------------------


class TestAssignmentWithoutGovernance:
    """Without DecisionEngine, assignment must return error — no direct write."""

    def test_propose_assignment_no_decision_engine_returns_error(self):
        agent = EquipmentAssetOperationsAgent()  # no decision_engine, no state_provider

        async def run():
            return await agent.propose_equipment_assignment(
                asset_id="FL-001",
                assignee="op-1",
            )

        result = asyncio.run(run())
        assert result["status"] == "error"
        assert result["executed"] is False
        reason = result["reason"].lower()
        assert "decision_engine" in reason or "state_provider" in reason

    def test_propose_assignment_no_decision_engine_never_calls_asset_tools(self):
        mock_asset_tools = MagicMock()
        mock_asset_tools.assign_equipment = AsyncMock()
        agent = EquipmentAssetOperationsAgent(
            asset_tools=mock_asset_tools
        )  # no decision_engine

        asyncio.run(
            agent.propose_equipment_assignment(asset_id="FL-001", assignee="op-1")
        )

        mock_asset_tools.assign_equipment.assert_not_called()

    def test_propose_assignment_partial_config_returns_error(self):
        """Even with state_provider but no decision_engine, must return error."""
        mock_state_provider = MagicMock()
        agent = EquipmentAssetOperationsAgent(state_provider=mock_state_provider)

        result = asyncio.run(
            agent.propose_equipment_assignment(asset_id="FL-002", assignee="op-2")
        )
        assert result["status"] == "error"
        assert result["executed"] is False


# ---------------------------------------------------------------------------
# Invariant B — release with no decision_engine returns error, no write
# ---------------------------------------------------------------------------


class TestReleaseWithoutGovernance:
    """Without DecisionEngine, release must return error — no direct write."""

    def test_propose_release_no_decision_engine_returns_error(self):
        agent = EquipmentAssetOperationsAgent()

        result = asyncio.run(
            agent.propose_equipment_release(asset_id="FL-001", released_by="op-1")
        )
        assert result["status"] == "error"
        assert result["executed"] is False

    def test_propose_release_no_decision_engine_never_calls_asset_tools(self):
        mock_asset_tools = MagicMock()
        mock_asset_tools.release_equipment = AsyncMock()
        agent = EquipmentAssetOperationsAgent(asset_tools=mock_asset_tools)

        asyncio.run(
            agent.propose_equipment_release(asset_id="FL-001", released_by="op-1")
        )

        mock_asset_tools.release_equipment.assert_not_called()


# ---------------------------------------------------------------------------
# Invariant C — maintenance with no decision_engine returns error, no write
# ---------------------------------------------------------------------------


class TestMaintenanceWithoutGovernance:
    """Without DecisionEngine, maintenance scheduling must return error — no direct write."""

    def test_propose_maintenance_no_decision_engine_returns_error(self):
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
        assert result["status"] == "error"
        assert result["executed"] is False

    def test_propose_maintenance_no_decision_engine_never_calls_asset_tools(self):
        mock_asset_tools = MagicMock()
        mock_asset_tools.schedule_maintenance = AsyncMock()
        agent = EquipmentAssetOperationsAgent(asset_tools=mock_asset_tools)

        asyncio.run(
            agent.propose_schedule_maintenance(
                asset_id="FL-001",
                maintenance_type="preventive",
                description="quarterly inspection",
                scheduled_by="system",
                scheduled_for="2026-10-01T08:00:00",
            )
        )

        mock_asset_tools.schedule_maintenance.assert_not_called()


# ---------------------------------------------------------------------------
# Invariant D — with decision_engine, assignment never touches asset_tools
# ---------------------------------------------------------------------------


class TestAssignmentWithGovernanceRoutes:
    """With full state-aware stack, assignment goes through state_aware_ops."""

    def test_propose_assignment_with_decision_engine_never_calls_asset_tools(self):
        """When DecisionEngine is wired, state_aware_ops handles assignment, not asset_tools."""
        from maiw_decision import DecisionEngine

        mock_state_provider = MagicMock()
        mock_assignment_skill = MagicMock()
        decision_engine = DecisionEngine()

        # Provide asset_tools — its write method must NOT be called
        mock_asset_tools = MagicMock()
        mock_asset_tools.assign_equipment = AsyncMock()

        agent = EquipmentAssetOperationsAgent(
            asset_tools=mock_asset_tools,
            state_provider=mock_state_provider,
            decision_engine=decision_engine,
            assignment_skill=mock_assignment_skill,
        )

        # Patch the state_aware_ops module so we don't need real MCP/DB
        stub_result = {
            "status": "APPROVED",
            "action": "warehouse.equipment.assign",
            "executed": False,
        }
        with patch(
            "maiw_agents.equipment.agent.state_aware_ops.propose_equipment_assignment",
            new=AsyncMock(return_value=stub_result),
        ) as mock_sa:
            result = asyncio.run(
                agent.propose_equipment_assignment(asset_id="FL-001", assignee="op-1")
            )
            mock_sa.assert_called_once()

        # The direct-write tool must never have been called — governance holds
        mock_asset_tools.assign_equipment.assert_not_called()
        assert result["status"] == "APPROVED"


# ---------------------------------------------------------------------------
# Invariant E — NoOpActionExecutor is default
# ---------------------------------------------------------------------------


class TestNoOpExecutorDefault:
    """EquipmentAssetOperationsAgent defaults to NoOpActionExecutor."""

    def test_default_executor_is_noop(self):
        agent = EquipmentAssetOperationsAgent()
        assert isinstance(agent._action_executor, NoOpActionExecutor)

    def test_custom_executor_is_stored(self):
        custom = NoOpActionExecutor()
        agent = EquipmentAssetOperationsAgent(action_executor=custom)
        assert agent._action_executor is custom


# ---------------------------------------------------------------------------
# Invariant F — _legacy_assign does not exist
# ---------------------------------------------------------------------------


class TestNoLegacyAssign:
    """_legacy_assign must not exist on EquipmentAssetOperationsAgent."""

    def test_legacy_assign_removed(self):
        agent = EquipmentAssetOperationsAgent()
        assert not hasattr(agent, "_legacy_assign"), (
            "EquipmentAssetOperationsAgent._legacy_assign must not exist; "
            "it provided a direct-write bypass that circumvents DecisionEngine governance"
        )

    def test_no_direct_write_method_names(self):
        """No method names may suggest an ungoverned direct write."""
        agent = EquipmentAssetOperationsAgent()
        bad_names = [
            name
            for name in dir(agent)
            if "legacy" in name.lower() or "direct_write" in name.lower()
        ]
        assert bad_names == [], f"Unexpected direct-write methods found: {bad_names}"


# ---------------------------------------------------------------------------
# Invariant G — read-only asset_tools calls are not blocked
# ---------------------------------------------------------------------------


class TestReadOnlyToolsNotBlocked:
    """Read-only asset_tools methods (get_status, get_telemetry) are not blocked."""

    def test_execute_action_tools_lookup_calls_get_equipment_status(self):
        from maiw_agents.equipment.agent import EquipmentQuery

        mock_asset_tools = MagicMock()
        mock_asset_tools.get_equipment_status = AsyncMock(
            return_value={"asset_id": "FL-001", "status": "available"}
        )

        agent = EquipmentAssetOperationsAgent(asset_tools=mock_asset_tools)

        eq_query = EquipmentQuery(
            intent="equipment_lookup",
            entities={"asset_id": "FL-001"},
            context={},
            user_query="status of FL-001",
        )

        asyncio.run(agent._execute_action_tools(eq_query, None))

        mock_asset_tools.get_equipment_status.assert_called_once()
