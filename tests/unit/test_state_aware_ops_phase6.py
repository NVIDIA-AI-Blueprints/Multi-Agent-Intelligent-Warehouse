# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 6 unit tests — state_aware_ops execution paths and new proposal functions.

Covers:
  - propose_equipment_assignment: APPROVED + executor → executed=True
  - propose_equipment_assignment: APPROVED + no executor → executed=False
  - propose_equipment_assignment: executor error → error status
  - propose_equipment_release: LOW risk → APPROVED
  - propose_equipment_release: with executor → executed=True
  - propose_schedule_maintenance: MEDIUM risk → requires_human_approval
  - warehouse_id explicit in state assembly
  - trace_id propagated through execution response

All tests use asyncio.run() (no pytest-asyncio required).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from maiw_decision import DecisionEngine
from maiw_mcp.contracts.actions import ActionProposal, RiskLevel
from maiw_mcp.contracts.equipment import (
    EquipmentAssetInfo,
    EquipmentExecuteAssignResult,
    EquipmentExecuteReleaseResult,
    EquipmentStatusResult,
)
from maiw_state import (
    EquipmentAssetSummary,
    EquipmentState,
    StateFreshness,
    WarehouseState,
    WarehouseStateProvider,
)

from src.api.agents.inventory import state_aware_ops
from src.api.agents.inventory.action_executor import (
    ActionExecutionResult,
    EquipmentActionExecutor,
    NoOpActionExecutor,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_asset(asset_id: str, status: str = "available") -> EquipmentAssetInfo:
    return EquipmentAssetInfo(
        asset_id=asset_id,
        equipment_type="forklift",
        model="FL-3000",
        zone="ZONE-A",
        status=status,
    )


def _make_status_result(*assets: EquipmentAssetInfo) -> EquipmentStatusResult:
    return EquipmentStatusResult(
        equipment=list(assets),
        total_count=len(assets),
        source="mock",
        summary={"forklift": {"available": len(assets)}},
    )


def _mock_status_skill(result: EquipmentStatusResult) -> MagicMock:
    skill = MagicMock()
    skill.execute = AsyncMock(return_value=result)
    return skill


def _mock_assignment_skill(proposal: ActionProposal) -> MagicMock:
    skill = MagicMock()
    skill.execute = AsyncMock(return_value=proposal)
    return skill


def _make_assign_proposal(asset_id: str = "FL-001") -> ActionProposal:
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


def _mock_executor_approved() -> MagicMock:
    executor = MagicMock()
    execution_result = ActionExecutionResult(
        execution_id="exec-uuid-1",
        executed=True,
        success=True,
        action="warehouse.equipment.assign",
        proposal_id="p-1",
        decision_id="d-1",
        provider_reference="42",
        backend_response={"assignment_id": 42},
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    executor.execute = AsyncMock(return_value=execution_result)
    return executor


def _mock_release_executor() -> MagicMock:
    executor = MagicMock()
    execution_result = ActionExecutionResult(
        execution_id="exec-release-1",
        executed=True,
        success=True,
        action="warehouse.equipment.release",
        proposal_id="p-r",
        decision_id="d-r",
        provider_reference=None,
        backend_response={"released": True},
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    executor.execute = AsyncMock(return_value=execution_result)
    return executor


# ---------------------------------------------------------------------------
# TestApprovedExecution — APPROVED + executor → executed: true
# ---------------------------------------------------------------------------


class TestApprovedExecution:
    def test_approved_with_executor_sets_executed_true(self):
        assets = [_make_asset("FL-001")]
        provider = WarehouseStateProvider(
            equipment_status_skill=_mock_status_skill(_make_status_result(*assets))
        )
        # Use a LOW risk proposal that will auto-approve
        low_risk_proposal = ActionProposal(
            action="warehouse.equipment.assign",
            parameters={"asset_id": "FL-001", "assignee": "w", "assignment_type": "task"},
            domain="equipment",
            risk_level=RiskLevel.LOW,
            requested_by="test",
            requires_approval=False,
        )
        assignment_skill = _mock_assignment_skill(low_risk_proposal)
        engine = DecisionEngine()
        executor = _mock_executor_approved()

        async def run():
            return await state_aware_ops.propose_equipment_assignment(
                asset_id="FL-001",
                assignee="w",
                state_provider=provider,
                decision_engine=engine,
                assignment_skill=assignment_skill,
                action_executor=executor,
            )

        response = asyncio.run(run())

        assert response["status"] == "executed"
        assert response["executed"] is True
        assert response["success"] is True
        assert "execution_id" in response
        executor.execute.assert_called_once()

    def test_approved_without_executor_executed_false(self):
        """APPROVED decision with no executor → proposal-only response."""
        assets = [_make_asset("FL-001")]
        provider = WarehouseStateProvider(
            equipment_status_skill=_mock_status_skill(_make_status_result(*assets))
        )
        low_risk_proposal = ActionProposal(
            action="warehouse.equipment.assign",
            parameters={"asset_id": "FL-001", "assignee": "w", "assignment_type": "task"},
            domain="equipment",
            risk_level=RiskLevel.LOW,
            requested_by="test",
            requires_approval=False,
        )
        assignment_skill = _mock_assignment_skill(low_risk_proposal)
        engine = DecisionEngine()

        async def run():
            return await state_aware_ops.propose_equipment_assignment(
                asset_id="FL-001",
                assignee="w",
                state_provider=provider,
                decision_engine=engine,
                assignment_skill=assignment_skill,
                # No action_executor
            )

        response = asyncio.run(run())

        assert response["status"] == "approved"
        assert response["executed"] is False
        assert "execution_id" not in response

    def test_executor_error_returns_error_status(self):
        assets = [_make_asset("FL-001")]
        provider = WarehouseStateProvider(
            equipment_status_skill=_mock_status_skill(_make_status_result(*assets))
        )
        low_risk_proposal = ActionProposal(
            action="warehouse.equipment.assign",
            parameters={"asset_id": "FL-001", "assignee": "w", "assignment_type": "task"},
            domain="equipment",
            risk_level=RiskLevel.LOW,
            requested_by="test",
            requires_approval=False,
        )
        assignment_skill = _mock_assignment_skill(low_risk_proposal)
        engine = DecisionEngine()
        failing_executor = MagicMock()
        failing_executor.execute = AsyncMock(side_effect=RuntimeError("DB down"))

        async def run():
            return await state_aware_ops.propose_equipment_assignment(
                asset_id="FL-001",
                assignee="w",
                state_provider=provider,
                decision_engine=engine,
                assignment_skill=assignment_skill,
                action_executor=failing_executor,
            )

        response = asyncio.run(run())

        assert response["status"] == "error"
        assert response["executed"] is False
        assert "DB down" in response["reason"]


# ---------------------------------------------------------------------------
# TestReleaseProposal
# ---------------------------------------------------------------------------


class TestReleaseProposal:
    def test_low_risk_release_approved_by_engine(self):
        assets = [_make_asset("FL-005")]
        provider = WarehouseStateProvider(
            equipment_status_skill=_mock_status_skill(_make_status_result(*assets))
        )
        engine = DecisionEngine()

        async def run():
            return await state_aware_ops.propose_equipment_release(
                asset_id="FL-005",
                released_by="worker-99",
                state_provider=provider,
                decision_engine=engine,
            )

        response = asyncio.run(run())

        # LOW risk, no executor → approved but not executed
        assert response["status"] == "approved"
        assert response["executed"] is False
        assert response["action"] == "warehouse.equipment.release"
        assert "proposal_id" in response
        assert "decision_id" in response

    def test_release_with_executor_sets_executed_true(self):
        assets = [_make_asset("FL-005")]
        provider = WarehouseStateProvider(
            equipment_status_skill=_mock_status_skill(_make_status_result(*assets))
        )
        engine = DecisionEngine()
        executor = _mock_release_executor()

        async def run():
            return await state_aware_ops.propose_equipment_release(
                asset_id="FL-005",
                released_by="worker-99",
                state_provider=provider,
                decision_engine=engine,
                action_executor=executor,
            )

        response = asyncio.run(run())

        assert response["status"] == "executed"
        assert response["executed"] is True
        executor.execute.assert_called_once()

    def test_release_stale_state_requires_fresh(self):
        from datetime import timedelta
        from maiw_state import EquipmentAssetSummary, EquipmentState, StateFreshness, WarehouseState

        old_ts = datetime.now(timezone.utc) - timedelta(seconds=60)
        stale_eq = EquipmentState(
            warehouse_id="default",
            assets=[
                EquipmentAssetSummary(
                    asset_id="FL-005",
                    equipment_type="forklift",
                    model="FL-3000",
                    zone="ZONE-A",
                    status="available",
                )
            ],
            total_count=1,
            freshness=StateFreshness.from_observed_at(old_ts, stale_after_ms=30_000),
        )
        state = WarehouseState(
            warehouse_id="default",
            observed_at=datetime.now(timezone.utc),
            equipment=stale_eq,
        )
        provider = MagicMock()
        provider.get_state = AsyncMock(return_value=state)
        engine = DecisionEngine()

        async def run():
            return await state_aware_ops.propose_equipment_release(
                asset_id="FL-005",
                released_by="worker-99",
                state_provider=provider,
                decision_engine=engine,
            )

        response = asyncio.run(run())
        assert response["status"] == "requires_fresh_state"
        assert response["executed"] is False


# ---------------------------------------------------------------------------
# TestMaintenanceProposal
# ---------------------------------------------------------------------------


class TestMaintenanceProposal:
    def test_medium_risk_maintenance_requires_human_approval(self):
        assets = [_make_asset("FL-006")]
        provider = WarehouseStateProvider(
            equipment_status_skill=_mock_status_skill(_make_status_result(*assets))
        )
        engine = DecisionEngine()

        async def run():
            return await state_aware_ops.propose_schedule_maintenance(
                asset_id="FL-006",
                maintenance_type="preventive",
                description="Quarterly check",
                scheduled_by="ops",
                scheduled_for="2026-09-01T08:00:00+00:00",
                state_provider=provider,
                decision_engine=engine,
            )

        response = asyncio.run(run())

        assert response["status"] == "requires_human_approval"
        assert response["executed"] is False
        assert response["action"] == "warehouse.equipment.schedule_maintenance"
        assert "proposal_id" in response

    def test_maintenance_executor_never_called_even_if_provided(self):
        """MEDIUM risk: executor is never called regardless of what's passed."""
        assets = [_make_asset("FL-006")]
        provider = WarehouseStateProvider(
            equipment_status_skill=_mock_status_skill(_make_status_result(*assets))
        )
        engine = DecisionEngine()
        executor = MagicMock()
        executor.execute = AsyncMock()

        async def run():
            return await state_aware_ops.propose_schedule_maintenance(
                asset_id="FL-006",
                maintenance_type="preventive",
                description="Test",
                scheduled_by="ops",
                scheduled_for="2026-09-01T08:00:00+00:00",
                state_provider=provider,
                decision_engine=engine,
                action_executor=executor,
            )

        asyncio.run(run())
        executor.execute.assert_not_called()


# ---------------------------------------------------------------------------
# TestWarehouseIdPropagation
# ---------------------------------------------------------------------------


class TestWarehouseIdPropagation:
    def test_warehouse_id_passed_to_state_provider(self):
        from maiw_state import WarehouseState

        assets = [_make_asset("FL-007")]
        status_result = _make_status_result(*assets)
        status_skill = _mock_status_skill(status_result)

        # Wrap real provider with a spy so we can assert the call argument
        real_provider = WarehouseStateProvider(equipment_status_skill=status_skill)
        original_get_state = real_provider.get_state

        captured_warehouse_id = []

        async def spy_get_state(warehouse_id, requirements, *, trace_id=None):
            captured_warehouse_id.append(warehouse_id)
            return await original_get_state(warehouse_id, requirements, trace_id=trace_id)

        real_provider.get_state = spy_get_state

        assignment_skill = _mock_assignment_skill(_make_assign_proposal("FL-007"))
        engine = DecisionEngine()

        async def run():
            return await state_aware_ops.propose_equipment_assignment(
                asset_id="FL-007",
                assignee="w",
                warehouse_id="WH-99",
                state_provider=real_provider,
                decision_engine=engine,
                assignment_skill=assignment_skill,
            )

        asyncio.run(run())
        assert captured_warehouse_id == ["WH-99"]


# ---------------------------------------------------------------------------
# TestTraceIdPropagation
# ---------------------------------------------------------------------------


class TestTraceIdPropagation:
    def test_trace_id_in_execution_response(self):
        assets = [_make_asset("FL-008")]
        provider = WarehouseStateProvider(
            equipment_status_skill=_mock_status_skill(_make_status_result(*assets))
        )
        proposal = _make_assign_proposal("FL-008")
        assignment_skill = _mock_assignment_skill(proposal)
        engine = DecisionEngine()

        async def run():
            return await state_aware_ops.propose_equipment_assignment(
                asset_id="FL-008",
                assignee="w",
                trace_id="test-trace-phase6",
                state_provider=provider,
                decision_engine=engine,
                assignment_skill=assignment_skill,
            )

        response = asyncio.run(run())
        assert response["trace_id"] == "test-trace-phase6"
