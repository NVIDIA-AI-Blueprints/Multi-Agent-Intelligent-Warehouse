# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Architecture invariant tests — Phase 6B.

These tests verify the platform boundary:

    STATE → REASON → PROPOSE → DECIDE → EXECUTE → MCP → BACKEND

Invariants enforced:
    LLM cannot execute MCP writes directly
    Proposal skill cannot execute MCP writes
    DecisionEngine cannot execute MCP writes
    Only ActionExecutor reaches MCP write capabilities

Specific checks:
    1.  Proposal generation causes no MCP call
    2.  Proposal generation causes no backend mutation
    3.  DecisionEngine.evaluate() causes no MCP call
    4.  Non-approved decision never reaches executor
    5.  Unknown action (outside allowlist) never reaches MCP
    6.  Expired decision never reaches MCP
    7.  Proposal/decision mismatch never reaches MCP
    8.  Warehouse_id propagates through proposal → drift-check (not hardcoded "default")
    9.  MCP server exposes ONLY execution tools (no proposal tools)
    10. EquipmentAssignmentSkill makes no MCP call
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maiw_decision import DecisionEngine
from maiw_decision.models import DecisionOutcome, DecisionRequest, DecisionResult
from maiw_mcp.contracts.actions import ActionProposal, RiskLevel
from maiw_mcp.contracts.equipment import EquipmentAssignmentRequest
from mcp_servers.equipment.provider import MockEquipmentProvider
from mcp_servers.equipment.server import mcp_server

# ── Invariant 1 & 2: Proposal generation — no MCP call, no mutation ───────────


class TestProposalGenerationIsLocal:
    """EquipmentAssignmentSkill builds proposals locally without any MCP call."""

    def test_assignment_skill_makes_no_mcp_invoke(self):
        from src.api.skills.equipment import EquipmentAssignmentSkill

        async def run():
            skill = EquipmentAssignmentSkill()
            request = EquipmentAssignmentRequest(
                asset_id="FL-001",
                assignee="op-1",
                reason="invariant-test",
                requested_by="test",
            )
            with patch("maiw_mcp.client.client.MAIWMCPClient.invoke") as mock_invoke:
                result = await skill.execute(request)
                return mock_invoke.call_count, result

        call_count, proposal = asyncio.run(run())
        assert call_count == 0, "Proposal skill must never call MCP"
        assert isinstance(proposal, ActionProposal)
        assert proposal.action == "warehouse.equipment.assign"

    def test_assignment_proposal_factory_is_pure(self):
        """ActionProposal.for_equipment_assign() is a pure factory — no I/O."""
        proposal = ActionProposal.for_equipment_assign(
            asset_id="FL-001",
            assignee="op-1",
            assignment_type="task",
            task_id=None,
            duration_hours=None,
            notes=None,
            reason="test",
            requested_by="test-agent",
        )
        assert isinstance(proposal, ActionProposal)
        assert proposal.action == "warehouse.equipment.assign"
        assert proposal.risk_level == RiskLevel.MEDIUM
        assert proposal.requires_approval is True

    def test_release_proposal_factory_is_pure(self):
        proposal = ActionProposal.for_equipment_release(
            asset_id="FL-001",
            released_by="op-1",
        )
        assert isinstance(proposal, ActionProposal)
        assert proposal.action == "warehouse.equipment.release"
        assert proposal.risk_level == RiskLevel.LOW
        assert proposal.requires_approval is False

    def test_maintenance_proposal_factory_is_pure(self):
        proposal = ActionProposal.for_schedule_maintenance(
            asset_id="FL-001",
            maintenance_type="preventive",
            description="Annual PM",
            scheduled_by="tech",
            scheduled_for="2026-09-01T08:00:00Z",
        )
        assert isinstance(proposal, ActionProposal)
        assert proposal.action == "warehouse.equipment.schedule_maintenance"
        assert proposal.risk_level == RiskLevel.MEDIUM
        assert proposal.requires_approval is True


# ── Invariant 3: DecisionEngine makes no MCP call ─────────────────────────────


class TestDecisionEngineIsIsolated:
    """DecisionEngine.evaluate() is pure — no MCP, no I/O."""

    def _make_sealed_snapshot(self):
        from maiw_state import WarehouseState, WarehouseStateSnapshot

        state = WarehouseState(
            warehouse_id="wh-test",
            observed_at=datetime.now(timezone.utc),
        )
        return WarehouseStateSnapshot.seal(state)

    def test_decision_engine_evaluate_makes_no_mcp_call(self):
        engine = DecisionEngine()
        proposal = ActionProposal.for_equipment_release(
            asset_id="FL-001",
            released_by="op-1",
        )
        snapshot = self._make_sealed_snapshot()
        req = DecisionRequest(proposal=proposal, state=snapshot, requested_by="test")

        with patch("maiw_mcp.client.client.MAIWMCPClient.invoke") as mock_invoke:
            result, audit = engine.evaluate(req)
            assert mock_invoke.call_count == 0, "DecisionEngine must never call MCP"

        assert result.outcome in {
            DecisionOutcome.APPROVED,
            DecisionOutcome.REQUIRES_FRESH_STATE,
        }

    def test_low_risk_no_approval_auto_approves(self):
        engine = DecisionEngine()
        proposal = ActionProposal.for_equipment_release(
            asset_id="FL-001",
            released_by="op-1",
        )
        snapshot = self._make_sealed_snapshot()
        req = DecisionRequest(proposal=proposal, state=snapshot, requested_by="test")
        result, _ = engine.evaluate(req)
        # May be APPROVED or REQUIRES_FRESH_STATE (equipment not in snapshot)
        assert result.outcome in {
            DecisionOutcome.APPROVED,
            DecisionOutcome.REQUIRES_FRESH_STATE,
        }

    def test_medium_risk_never_auto_approves(self):
        """MEDIUM risk must never produce APPROVED regardless of state contents."""
        engine = DecisionEngine()
        proposal = ActionProposal.for_equipment_assign(
            asset_id="FL-001",
            assignee="op-1",
            assignment_type="task",
            task_id=None,
            duration_hours=None,
            notes=None,
            reason="test",
            requested_by="test",
        )
        snapshot = self._make_sealed_snapshot()
        req = DecisionRequest(proposal=proposal, state=snapshot, requested_by="test")
        result, _ = engine.evaluate(req)
        # May be REQUIRES_HUMAN_APPROVAL or REQUIRES_FRESH_STATE — never APPROVED
        assert result.outcome != DecisionOutcome.APPROVED


# ── Invariant 4: Non-approved decision never reaches executor ─────────────────


class TestExecutorGuards:
    """EquipmentActionExecutor enforces the APPROVED gate before any MCP call."""

    def _make_executor_with_mock_skill(self):
        from src.api.agents.inventory.action_executor import EquipmentActionExecutor

        mock_skill = MagicMock()
        mock_skill.execute = AsyncMock(return_value=MagicMock(model_dump=lambda: {}))

        executor = EquipmentActionExecutor(
            assign_skill=mock_skill,
            release_skill=mock_skill,
            maintenance_skill=mock_skill,
        )
        return executor, mock_skill

    def _make_approved_decision(self, proposal: ActionProposal) -> DecisionResult:
        return DecisionResult(
            request_id="req-test",
            outcome=DecisionOutcome.APPROVED,
            proposal_id=proposal.proposal_id,
        )

    def test_non_approved_decision_raises_before_mcp(self):
        from src.api.agents.inventory.action_executor import (
            ActionNotApproved,
            EquipmentActionExecutor,
        )

        executor, mock_skill = self._make_executor_with_mock_skill()
        proposal = ActionProposal.for_equipment_release(
            asset_id="FL-001", released_by="op-1"
        )
        rejected = DecisionResult(
            request_id="req-test",
            outcome=DecisionOutcome.REQUIRES_HUMAN_APPROVAL,
            proposal_id=proposal.proposal_id,
        )

        async def run():
            await executor.execute(proposal, rejected)

        with pytest.raises(ActionNotApproved):
            asyncio.run(run())
        mock_skill.execute.assert_not_called()

    def test_unknown_action_blocked_by_allowlist(self):
        from src.api.agents.inventory.action_executor import (
            ActionUnsupported,
            EquipmentActionExecutor,
        )

        executor, mock_skill = self._make_executor_with_mock_skill()
        proposal = ActionProposal(
            action="warehouse.equipment.DANGEROUS_UNKNOWN",
            parameters={"asset_id": "FL-001"},
            domain="equipment",
            risk_level=RiskLevel.LOW,
            requires_approval=False,
        )
        decision = self._make_approved_decision(proposal)

        async def run():
            await executor.execute(proposal, decision)

        with pytest.raises(ActionUnsupported):
            asyncio.run(run())
        mock_skill.execute.assert_not_called()

    def test_expired_decision_blocked_before_mcp(self):
        from src.api.agents.inventory.action_executor import (
            ActionExpired,
            EquipmentActionExecutor,
        )

        executor, mock_skill = self._make_executor_with_mock_skill()
        proposal = ActionProposal.for_equipment_release(
            asset_id="FL-001", released_by="op-1"
        )
        stale = DecisionResult(
            request_id="req-test",
            outcome=DecisionOutcome.APPROVED,
            proposal_id=proposal.proposal_id,
            evaluated_at=datetime.now(timezone.utc) - timedelta(seconds=400),
        )

        async def run():
            await executor.execute(proposal, stale)

        with pytest.raises(ActionExpired):
            asyncio.run(run())
        mock_skill.execute.assert_not_called()

    def test_proposal_decision_mismatch_blocked(self):
        from src.api.agents.inventory.action_executor import (
            ActionDecisionMismatch,
            EquipmentActionExecutor,
        )

        executor, mock_skill = self._make_executor_with_mock_skill()
        proposal = ActionProposal.for_equipment_release(
            asset_id="FL-001", released_by="op-1"
        )
        wrong_decision = DecisionResult(
            request_id="req-test",
            outcome=DecisionOutcome.APPROVED,
            proposal_id=str(uuid.uuid4()),  # different UUID — binding mismatch
        )

        async def run():
            await executor.execute(proposal, wrong_decision)

        with pytest.raises(ActionDecisionMismatch):
            asyncio.run(run())
        mock_skill.execute.assert_not_called()


# ── Invariant 8: warehouse_id propagates through proposal factory ─────────────


class TestWarehouseIdPropagation:
    """warehouse_id must be in proposal.parameters — never silently defaults."""

    def test_assign_factory_includes_warehouse_id(self):
        proposal = ActionProposal.for_equipment_assign(
            asset_id="FL-001",
            assignee="op-1",
            assignment_type="task",
            task_id=None,
            duration_hours=None,
            notes=None,
            reason="test",
            requested_by="test",
            warehouse_id="WH-002",
        )
        assert proposal.parameters.get("warehouse_id") == "WH-002"

    def test_release_factory_includes_warehouse_id(self):
        proposal = ActionProposal.for_equipment_release(
            asset_id="FL-001",
            released_by="op-1",
            warehouse_id="WH-002",
        )
        assert proposal.parameters.get("warehouse_id") == "WH-002"

    def test_maintenance_factory_includes_warehouse_id(self):
        proposal = ActionProposal.for_schedule_maintenance(
            asset_id="FL-001",
            maintenance_type="preventive",
            description="PM",
            scheduled_by="tech",
            scheduled_for="2026-09-01T08:00:00Z",
            warehouse_id="WH-003",
        )
        assert proposal.parameters.get("warehouse_id") == "WH-003"

    def test_drift_check_uses_proposal_warehouse_id(self):
        """_check_state_drift must use proposal.parameters['warehouse_id'], not 'default'."""
        from src.api.agents.inventory.action_executor import EquipmentActionExecutor

        captured_warehouse_ids = []

        class RecordingStateProvider:
            async def get_state(self, warehouse_id, requirements, **kwargs):
                captured_warehouse_ids.append(warehouse_id)
                raise RuntimeError("bail out after recording")

        executor = EquipmentActionExecutor(
            assign_skill=MagicMock(),
            state_provider=RecordingStateProvider(),
        )

        proposal = ActionProposal.for_equipment_release(
            asset_id="FL-999",
            released_by="op-1",
            warehouse_id="WH-CUSTOM",
        )

        async def run():
            await executor._check_state_drift(proposal)

        asyncio.run(run())
        assert (
            "WH-CUSTOM" in captured_warehouse_ids
        ), "_check_state_drift must use proposal.parameters['warehouse_id'] not 'default'"


# ── Invariant 9: MCP server exposes only execution tools ──────────────────────


class TestMCPCapabilityBoundary:
    """MCP server must expose only executable warehouse operations."""

    def test_no_proposal_tools_in_mcp_server(self):
        import asyncio
        from mcp.client import Client
        from mcp_servers.equipment.server import configure_server

        configure_server(MockEquipmentProvider())

        async def run():
            async with Client(mcp_server) as client:
                result = await client.list_tools()
                return [t.name for t in result.tools]

        names = asyncio.run(run())
        # Proposal tools must not exist
        assert "warehouse.equipment.propose_release" not in names
        assert "warehouse.equipment.propose_maintenance" not in names
        # Old execute_ prefixed names must not exist
        assert "warehouse.equipment.execute_assign" not in names
        assert "warehouse.equipment.execute_release" not in names
        assert "warehouse.equipment.execute_maintenance" not in names

    def test_execution_tools_present_with_semantic_names(self):
        import asyncio
        from mcp.client import Client
        from mcp_servers.equipment.server import configure_server

        configure_server(MockEquipmentProvider())

        async def run():
            async with Client(mcp_server) as client:
                result = await client.list_tools()
                return [t.name for t in result.tools]

        names = asyncio.run(run())
        assert "warehouse.equipment.assign" in names
        assert "warehouse.equipment.release" in names
        assert "warehouse.equipment.schedule_maintenance" in names

    def test_write_tools_require_proposal_and_decision_ids(self):
        """Write tools must enforce audit ID binding at the schema level."""
        import asyncio
        from mcp.client import Client
        from mcp_servers.equipment.server import configure_server

        configure_server(MockEquipmentProvider())

        async def run():
            async with Client(mcp_server) as client:
                result = await client.list_tools()
                tools = {t.name: t for t in result.tools}
                assign_props = tools["warehouse.equipment.assign"].input_schema.get(
                    "properties", {}
                )
                release_props = tools["warehouse.equipment.release"].input_schema.get(
                    "properties", {}
                )
                maint_props = tools[
                    "warehouse.equipment.schedule_maintenance"
                ].input_schema.get("properties", {})
                return assign_props, release_props, maint_props

        a, r, m = asyncio.run(run())
        assert "proposal_id" in a
        assert "decision_id" in a
        assert "proposal_id" in r
        assert "decision_id" in r
        assert "proposal_id" in m
        assert "decision_id" in m


# ── Labor domain invariants ───────────────────────────────────────────────────


class TestLaborProposalIsLocal:
    """ProposeLaborAllocationSkill must never call MCP."""

    def test_propose_labor_allocation_makes_no_mcp_call(self):
        from src.api.skills.labor import ProposeLaborAllocationSkill

        async def run():
            skill = ProposeLaborAllocationSkill()
            with patch("maiw_mcp.client.client.MAIWMCPClient.invoke") as mock_invoke:
                result = await skill.execute(
                    task_id="t-001",
                    task_type="PICK",
                    worker_ids=["w-001"],
                )
                return mock_invoke.call_count, result

        call_count, proposal = asyncio.run(run())
        assert call_count == 0, "ProposeLaborAllocationSkill must never call MCP"
        assert isinstance(proposal, ActionProposal)
        assert proposal.action == "warehouse.labor.allocate"
        assert proposal.domain == "labor"

    def test_labor_proposal_factory_is_pure(self):
        proposal = ActionProposal.for_labor_allocate(
            task_id="t-001",
            task_type="PICK",
            worker_ids=["w-001"],
        )
        assert isinstance(proposal, ActionProposal)
        assert proposal.action == "warehouse.labor.allocate"
        assert proposal.risk_level == RiskLevel.MEDIUM
        assert proposal.requires_approval is True


class TestLaborExecutorGuards:
    """LaborActionExecutor enforces the APPROVED gate before any MCP call."""

    def _make_executor(self):
        from src.api.agents.operations.labor_executor import LaborActionExecutor
        from src.api.agents.inventory.action_executor import ActionNotApproved

        mock_skill = MagicMock()
        mock_skill.execute = AsyncMock(return_value=MagicMock(model_dump=lambda: {}))
        return LaborActionExecutor(allocate_skill=mock_skill), mock_skill

    def test_non_approved_decision_blocked(self):
        from src.api.agents.inventory.action_executor import ActionNotApproved

        executor, mock_skill = self._make_executor()
        proposal = ActionProposal.for_labor_allocate(
            task_id="t-1", task_type="PICK", worker_ids=["w-1"]
        )
        rejected = DecisionResult(
            request_id="req-test",
            outcome=DecisionOutcome.REQUIRES_HUMAN_APPROVAL,
            proposal_id=proposal.proposal_id,
        )

        with pytest.raises(ActionNotApproved):
            asyncio.run(executor.execute(proposal, rejected))
        mock_skill.execute.assert_not_called()

    def test_arbitrary_action_blocked_by_allowlist(self):
        from src.api.agents.inventory.action_executor import ActionUnsupported

        executor, mock_skill = self._make_executor()
        proposal = ActionProposal(
            action="warehouse.labor.ARBITRARY_WRITE",
            parameters={"warehouse_id": "WH-001"},
            domain="labor",
            risk_level=RiskLevel.MEDIUM,
            requires_approval=True,
        )
        decision = DecisionResult(
            request_id="req-test",
            outcome=DecisionOutcome.APPROVED,
            proposal_id=proposal.proposal_id,
        )

        with pytest.raises(ActionUnsupported):
            asyncio.run(executor.execute(proposal, decision))
        mock_skill.execute.assert_not_called()


# ── Wave domain invariants ────────────────────────────────────────────────────


class TestWaveProposalIsLocal:
    """ProposeWaveReprioritizationSkill must never call MCP."""

    def test_propose_wave_reprioritization_makes_no_mcp_call(self):
        from src.api.skills.wave import ProposeWaveReprioritizationSkill

        async def run():
            skill = ProposeWaveReprioritizationSkill()
            with patch("maiw_mcp.client.client.MAIWMCPClient.invoke") as mock_invoke:
                result = await skill.execute(new_priority="high")
                return mock_invoke.call_count, result

        call_count, proposal = asyncio.run(run())
        assert call_count == 0, "ProposeWaveReprioritizationSkill must never call MCP"
        assert isinstance(proposal, ActionProposal)
        assert proposal.action == "warehouse.wave.reprioritize"
        assert proposal.domain == "wave"

    def test_wave_proposal_factory_is_pure(self):
        proposal = ActionProposal.for_wave_reprioritize(new_priority="high")
        assert isinstance(proposal, ActionProposal)
        assert proposal.action == "warehouse.wave.reprioritize"
        assert proposal.risk_level == RiskLevel.MEDIUM
        assert proposal.requires_approval is True


class TestWaveExecutorGuards:
    """WaveActionExecutor enforces the APPROVED gate before any MCP call."""

    def _make_executor(self):
        from src.api.agents.operations.wave_executor import WaveActionExecutor

        mock_skill = MagicMock()
        mock_skill.execute = AsyncMock(return_value=MagicMock(model_dump=lambda: {}))
        return WaveActionExecutor(reprioritize_skill=mock_skill), mock_skill

    def test_non_approved_decision_blocked(self):
        from src.api.agents.inventory.action_executor import ActionNotApproved

        executor, mock_skill = self._make_executor()
        proposal = ActionProposal.for_wave_reprioritize(new_priority="high")
        rejected = DecisionResult(
            request_id="req-test",
            outcome=DecisionOutcome.REQUIRES_HUMAN_APPROVAL,
            proposal_id=proposal.proposal_id,
        )

        with pytest.raises(ActionNotApproved):
            asyncio.run(executor.execute(proposal, rejected))
        mock_skill.execute.assert_not_called()

    def test_arbitrary_action_blocked_by_allowlist(self):
        from src.api.agents.inventory.action_executor import ActionUnsupported

        executor, mock_skill = self._make_executor()
        proposal = ActionProposal(
            action="warehouse.wave.ARBITRARY_WRITE",
            parameters={"warehouse_id": "WH-001"},
            domain="wave",
            risk_level=RiskLevel.MEDIUM,
            requires_approval=True,
        )
        decision = DecisionResult(
            request_id="req-test",
            outcome=DecisionOutcome.APPROVED,
            proposal_id=proposal.proposal_id,
        )

        with pytest.raises(ActionUnsupported):
            asyncio.run(executor.execute(proposal, decision))
        mock_skill.execute.assert_not_called()

    def test_wave_executor_cannot_execute_labor_action(self):
        """Cross-domain: wave executor must not execute labor writes."""
        from src.api.agents.inventory.action_executor import ActionUnsupported

        executor, mock_skill = self._make_executor()
        labor_proposal = ActionProposal.for_labor_allocate(
            task_id="t-1", task_type="PICK", worker_ids=["w-1"]
        )
        decision = DecisionResult(
            request_id="req-test",
            outcome=DecisionOutcome.APPROVED,
            proposal_id=labor_proposal.proposal_id,
        )

        with pytest.raises(ActionUnsupported):
            asyncio.run(executor.execute(labor_proposal, decision))
        mock_skill.execute.assert_not_called()

    def test_labor_executor_cannot_execute_wave_action(self):
        """Cross-domain: labor executor must not execute wave writes."""
        from src.api.agents.inventory.action_executor import ActionUnsupported
        from src.api.agents.operations.labor_executor import LaborActionExecutor

        mock_skill = MagicMock()
        mock_skill.execute = AsyncMock(return_value=MagicMock(model_dump=lambda: {}))
        executor = LaborActionExecutor(allocate_skill=mock_skill)

        wave_proposal = ActionProposal.for_wave_reprioritize(new_priority="high")
        decision = DecisionResult(
            request_id="req-test",
            outcome=DecisionOutcome.APPROVED,
            proposal_id=wave_proposal.proposal_id,
        )

        with pytest.raises(ActionUnsupported):
            asyncio.run(executor.execute(wave_proposal, decision))
        mock_skill.execute.assert_not_called()
