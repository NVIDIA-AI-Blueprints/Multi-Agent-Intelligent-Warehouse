# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 6 unit tests — EquipmentActionExecutor.

Covers the executor guards and routing without infrastructure deps.
All tests use asyncio.run() (no pytest-asyncio required).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from maiw_decision.models import DecisionOutcome, DecisionResult
from maiw_mcp.contracts.actions import ActionProposal, RiskLevel
from maiw_mcp.contracts.equipment import (
    EquipmentExecuteAssignResult,
    EquipmentExecuteReleaseResult,
    EquipmentExecuteMaintenanceResult,
)

from src.api.agents.inventory.action_executor import (
    ActionConflict,
    ActionDecisionMismatch,
    ActionExecutionError,
    ActionExecutionResult,
    ActionExpired,
    ActionNotApproved,
    ActionUnsupported,
    EquipmentActionExecutor,
    NoOpActionExecutor,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _approved_decision(proposal_id: str, age_seconds: float = 0.0) -> DecisionResult:
    evaluated_at = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    return DecisionResult(
        request_id="req-1",
        proposal_id=proposal_id,
        outcome=DecisionOutcome.APPROVED,
        evaluated_at=evaluated_at,
    )


def _rejected_decision(proposal_id: str) -> DecisionResult:
    return DecisionResult(
        request_id="req-1",
        proposal_id=proposal_id,
        outcome=DecisionOutcome.REQUIRES_HUMAN_APPROVAL,
    )


def _assign_proposal(asset_id: str = "FL-001") -> ActionProposal:
    return ActionProposal.for_equipment_assign(
        asset_id=asset_id,
        assignee="worker-42",
        assignment_type="task",
        task_id="T-1",
        duration_hours=4,
        notes="test",
        reason="test",
        requested_by="worker-42",
    )


def _release_proposal(asset_id: str = "FL-001") -> ActionProposal:
    return ActionProposal.for_equipment_release(
        asset_id=asset_id,
        released_by="worker-42",
        notes=None,
        requested_by="worker-42",
    )


def _maintenance_proposal(asset_id: str = "FL-001") -> ActionProposal:
    return ActionProposal.for_schedule_maintenance(
        asset_id=asset_id,
        maintenance_type="preventive",
        description="Quarterly check",
        scheduled_by="ops-manager",
        scheduled_for="2026-09-01T08:00:00+00:00",
        requested_by="ops-manager",
    )


def _assign_skill_mock(success: bool = True) -> MagicMock:
    skill = MagicMock()
    skill.execute = AsyncMock(
        return_value=EquipmentExecuteAssignResult(
            assignment_id=42 if success else None,
            success=success,
            proposal_id="p-1",
            decision_id="d-1",
            source="mock",
            message="ok" if success else "failed",
        )
    )
    return skill


def _release_skill_mock(success: bool = True) -> MagicMock:
    skill = MagicMock()
    skill.execute = AsyncMock(
        return_value=EquipmentExecuteReleaseResult(
            success=success,
            proposal_id="p-1",
            decision_id="d-1",
            source="mock",
        )
    )
    return skill


def _maintenance_skill_mock(success: bool = True) -> MagicMock:
    skill = MagicMock()
    skill.execute = AsyncMock(
        return_value=EquipmentExecuteMaintenanceResult(
            maintenance_id=99 if success else None,
            success=success,
            proposal_id="p-1",
            decision_id="d-1",
            source="mock",
        )
    )
    return skill


# ---------------------------------------------------------------------------
# TestApprovedGate
# ---------------------------------------------------------------------------


class TestApprovedGate:
    def test_approved_decision_executes_assign(self):
        proposal = _assign_proposal()
        decision = _approved_decision(proposal.proposal_id)
        executor = EquipmentActionExecutor(assign_skill=_assign_skill_mock())

        async def run():
            return await executor.execute(proposal, decision)

        result = asyncio.run(run())
        assert result.executed is True
        assert result.success is True
        assert result.proposal_id == proposal.proposal_id
        assert result.execution_id is not None

    def test_non_approved_raises_action_not_approved(self):
        proposal = _assign_proposal()
        decision = _rejected_decision(proposal.proposal_id)
        executor = EquipmentActionExecutor(assign_skill=_assign_skill_mock())

        async def run():
            return await executor.execute(proposal, decision)

        with pytest.raises(ActionNotApproved):
            asyncio.run(run())

    def test_action_not_approved_is_value_error_subclass(self):
        proposal = _assign_proposal()
        decision = _rejected_decision(proposal.proposal_id)
        executor = EquipmentActionExecutor(assign_skill=_assign_skill_mock())

        async def run():
            return await executor.execute(proposal, decision)

        with pytest.raises(ValueError):
            asyncio.run(run())


# ---------------------------------------------------------------------------
# TestDecisionProposalMismatch
# ---------------------------------------------------------------------------


class TestDecisionProposalMismatch:
    def test_mismatched_proposal_id_raises(self):
        proposal = _assign_proposal()
        decision = _approved_decision("completely-different-uuid")
        executor = EquipmentActionExecutor(assign_skill=_assign_skill_mock())

        async def run():
            return await executor.execute(proposal, decision)

        with pytest.raises(ActionDecisionMismatch):
            asyncio.run(run())


# ---------------------------------------------------------------------------
# TestActionAllowlist
# ---------------------------------------------------------------------------


class TestActionAllowlist:
    def test_unsupported_action_raises(self):
        proposal = ActionProposal(
            action="warehouse.inventory.write",
            parameters={"item_id": "SKU-1"},
            domain="inventory",
            risk_level=RiskLevel.MEDIUM,
            requested_by="test",
            requires_approval=True,
        )
        decision = _approved_decision(proposal.proposal_id)
        executor = EquipmentActionExecutor(assign_skill=_assign_skill_mock())

        async def run():
            return await executor.execute(proposal, decision)

        with pytest.raises(ActionUnsupported):
            asyncio.run(run())


# ---------------------------------------------------------------------------
# TestStaleDecision
# ---------------------------------------------------------------------------


class TestStaleDecision:
    def test_expired_decision_raises_action_expired(self):
        proposal = _assign_proposal()
        # Decision was evaluated 10 minutes ago; max age is 5 minutes
        decision = _approved_decision(proposal.proposal_id, age_seconds=600)
        executor = EquipmentActionExecutor(
            assign_skill=_assign_skill_mock(),
            max_decision_age_seconds=300,
        )

        async def run():
            return await executor.execute(proposal, decision)

        with pytest.raises(ActionExpired):
            asyncio.run(run())

    def test_fresh_decision_passes(self):
        proposal = _assign_proposal()
        decision = _approved_decision(proposal.proposal_id, age_seconds=10)
        executor = EquipmentActionExecutor(
            assign_skill=_assign_skill_mock(),
            max_decision_age_seconds=300,
        )

        async def run():
            return await executor.execute(proposal, decision)

        result = asyncio.run(run())
        assert result.executed is True


# ---------------------------------------------------------------------------
# TestStateDrift
# ---------------------------------------------------------------------------


class TestStateDrift:
    def test_offline_asset_raises_conflict(self):
        from maiw_mcp.contracts.equipment import (
            EquipmentAssetInfo,
            EquipmentStatusResult,
        )
        from maiw_state import WarehouseStateProvider

        offline_asset = EquipmentAssetInfo(
            asset_id="FL-001",
            equipment_type="forklift",
            model="FL-3000",
            zone="ZONE-A",
            status="offline",
        )
        status_result = EquipmentStatusResult(
            equipment=[offline_asset],
            total_count=1,
            source="mock",
            summary={},
        )
        status_skill = MagicMock()
        status_skill.execute = AsyncMock(return_value=status_result)
        state_provider = WarehouseStateProvider(equipment_status_skill=status_skill)

        proposal = _assign_proposal("FL-001")
        decision = _approved_decision(proposal.proposal_id)
        executor = EquipmentActionExecutor(
            assign_skill=_assign_skill_mock(),
            state_provider=state_provider,
        )

        async def run():
            return await executor.execute(proposal, decision)

        with pytest.raises(ActionConflict):
            asyncio.run(run())


# ---------------------------------------------------------------------------
# TestSkillRouting
# ---------------------------------------------------------------------------


class TestSkillRouting:
    def test_assign_skill_called_with_correct_params(self):
        proposal = _assign_proposal("FL-002")
        decision = _approved_decision(proposal.proposal_id)
        assign_skill = _assign_skill_mock()
        executor = EquipmentActionExecutor(assign_skill=assign_skill)

        asyncio.run(executor.execute(proposal, decision))

        assign_skill.execute.assert_called_once()
        call_arg = assign_skill.execute.call_args[0][0]
        assert call_arg.asset_id == "FL-002"
        assert call_arg.proposal_id == proposal.proposal_id

    def test_release_skill_called_correctly(self):
        proposal = _release_proposal("FL-003")
        decision = _approved_decision(proposal.proposal_id)
        release_skill = _release_skill_mock()
        executor = EquipmentActionExecutor(
            assign_skill=_assign_skill_mock(),
            release_skill=release_skill,
        )

        asyncio.run(executor.execute(proposal, decision))

        release_skill.execute.assert_called_once()
        call_arg = release_skill.execute.call_args[0][0]
        assert call_arg.asset_id == "FL-003"
        assert call_arg.proposal_id == proposal.proposal_id

    def test_maintenance_skill_called_correctly(self):
        proposal = _maintenance_proposal("FL-004")
        # Override risk to LOW so engine would approve (for testing routing only)
        approved_proposal = ActionProposal(
            proposal_id=proposal.proposal_id,
            action="warehouse.equipment.schedule_maintenance",
            parameters=proposal.parameters,
            domain="equipment",
            risk_level=RiskLevel.LOW,
            requested_by="test",
            requires_approval=False,
        )
        decision = _approved_decision(approved_proposal.proposal_id)
        maintenance_skill = _maintenance_skill_mock()
        executor = EquipmentActionExecutor(
            assign_skill=_assign_skill_mock(),
            maintenance_skill=maintenance_skill,
        )

        asyncio.run(executor.execute(approved_proposal, decision))

        maintenance_skill.execute.assert_called_once()
        call_arg = maintenance_skill.execute.call_args[0][0]
        assert call_arg.asset_id == "FL-004"


# ---------------------------------------------------------------------------
# TestBackendError
# ---------------------------------------------------------------------------


class TestBackendError:
    def test_backend_exception_wrapped_in_action_execution_error(self):
        proposal = _assign_proposal()
        decision = _approved_decision(proposal.proposal_id)

        failing_skill = MagicMock()
        failing_skill.execute = AsyncMock(
            side_effect=RuntimeError("DB connection lost")
        )
        executor = EquipmentActionExecutor(assign_skill=failing_skill)

        async def run():
            return await executor.execute(proposal, decision)

        with pytest.raises(ActionExecutionError, match="DB connection lost"):
            asyncio.run(run())


# ---------------------------------------------------------------------------
# TestNoOpExecutor (backward compat)
# ---------------------------------------------------------------------------


class TestNoOpExecutorBackwardCompat:
    def test_no_op_approved_returns_not_executed(self):
        proposal = _assign_proposal()
        decision = _approved_decision(proposal.proposal_id)
        executor = NoOpActionExecutor()

        result = asyncio.run(executor.execute(proposal, decision))

        assert result.executed is False
        assert result.proposal_id == proposal.proposal_id

    def test_no_op_non_approved_raises_value_error(self):
        proposal = _assign_proposal()
        decision = _rejected_decision(proposal.proposal_id)
        executor = NoOpActionExecutor()

        with pytest.raises(ValueError, match="non-APPROVED"):
            asyncio.run(executor.execute(proposal, decision))
