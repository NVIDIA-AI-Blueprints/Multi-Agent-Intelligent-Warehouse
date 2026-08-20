# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 5 unit tests — state-aware equipment operations.

Tests are written against ``state_aware_ops`` (the lightweight module that
contains the state/decision logic) rather than ``EquipmentAssetOperationsAgent``
(which pulls in asyncpg/redis/pymilvus through the retrieval layer).

This is the correct unit-testing boundary: the functions under test are the
pure state-assembly-and-decision functions; the agent class is an
integration-layer thin wrapper that delegates to them.

Covers (Parts 17–20 of the Phase 5 spec):
  Part 17 — Read path: assembles WarehouseStateSnapshot, not raw backend
  Part 18 — Write path: assignment → ActionProposal → DecisionEngine →
             REQUIRES_HUMAN_APPROVAL; write backend never invoked
  Part 19 — Stale state: REQUIRES_FRESH_STATE, no execution
  Part 20 — Missing asset: REJECTED, no execution

All tests use asyncio.run() (no pytest-asyncio required).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from maiw_decision import DecisionEngine, DecisionOutcome
from maiw_mcp.contracts.actions import ActionProposal, RiskLevel
from maiw_mcp.contracts.equipment import EquipmentAssetInfo, EquipmentStatusResult
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


def _make_proposal(asset_id: str) -> ActionProposal:
    return ActionProposal.for_equipment_assign(
        asset_id=asset_id,
        assignee="worker-42",
        assignment_type="picking",
        task_id="TASK-001",
        duration_hours=4.0,
        notes="test",
        reason="phase 5 test",
        requested_by="worker-42",
    )


def _stale_equipment_state(asset_id: str) -> EquipmentState:
    old_ts = datetime.now(timezone.utc) - timedelta(seconds=60)
    return EquipmentState(
        warehouse_id="default",
        assets=[
            EquipmentAssetSummary(
                asset_id=asset_id,
                equipment_type="forklift",
                model="FL-3000",
                zone="ZONE-A",
                status="available",
            )
        ],
        total_count=1,
        freshness=StateFreshness.from_observed_at(old_ts, stale_after_ms=30_000),
    )


def _state_with(equipment: EquipmentState | None) -> WarehouseState:
    return WarehouseState(
        warehouse_id="default",
        observed_at=datetime.now(timezone.utc),
        equipment=equipment,
    )


def _mock_provider(state: WarehouseState) -> MagicMock:
    p = MagicMock()
    p.get_state = AsyncMock(return_value=state)
    return p


# ---------------------------------------------------------------------------
# Part 17 — Read path
# ---------------------------------------------------------------------------


class TestReadPath:
    def test_returns_structured_snapshot_context(self):
        assets = [_make_asset("FL-001"), _make_asset("FL-002", "assigned")]
        skill = _mock_status_skill(_make_status_result(*assets))
        provider = WarehouseStateProvider(equipment_status_skill=skill)

        async def run():
            return await state_aware_ops.get_equipment_state_snapshot(
                asset_id="FL-001",
                state_provider=provider,
            )

        ctx = asyncio.run(run())

        assert ctx is not None
        assert "snapshot_id" in ctx
        assert "observed_at" in ctx
        assert ctx["equipment"]["total_count"] == 2
        assert ctx["equipment"]["available_count"] == 1

    def test_read_does_not_call_assignment_skill(self):
        skill = _mock_status_skill(_make_status_result(_make_asset("FL-001")))
        provider = WarehouseStateProvider(equipment_status_skill=skill)
        assign_skill = _mock_assignment_skill(_make_proposal("FL-001"))

        async def run():
            return await state_aware_ops.get_equipment_state_snapshot(
                asset_id="FL-001",
                state_provider=provider,
            )

        asyncio.run(run())
        skill.execute.assert_called_once()
        assign_skill.execute.assert_not_called()

    def test_provenance_in_snapshot(self):
        skill = _mock_status_skill(_make_status_result(_make_asset("FL-001")))
        provider = WarehouseStateProvider(equipment_status_skill=skill)

        async def run():
            return await state_aware_ops.get_equipment_state_snapshot(
                state_provider=provider
            )

        ctx = asyncio.run(run())
        assert len(ctx["provenance"]) == 1
        assert ctx["provenance"][0]["domain"] == "equipment"
        assert ctx["provenance"][0]["source"] == "mcp"

    def test_freshness_metadata_present(self):
        skill = _mock_status_skill(_make_status_result(_make_asset("FL-001")))
        provider = WarehouseStateProvider(equipment_status_skill=skill)

        async def run():
            return await state_aware_ops.get_equipment_state_snapshot(
                state_provider=provider
            )

        ctx = asyncio.run(run())
        assert ctx["equipment"]["freshness"]["age_ms"] == 0
        assert ctx["equipment"]["freshness"]["stale"] is False

    def test_returns_none_on_provider_error(self):
        provider = MagicMock()
        provider.get_state = AsyncMock(side_effect=RuntimeError("network down"))

        async def run():
            return await state_aware_ops.get_equipment_state_snapshot(
                state_provider=provider
            )

        result = asyncio.run(run())
        assert result is None


# ---------------------------------------------------------------------------
# Part 18 — Write path (assignment → REQUIRES_HUMAN_APPROVAL)
# ---------------------------------------------------------------------------


class TestWritePath:
    def test_requires_human_approval_for_medium_risk_assignment(self):
        assets = [_make_asset("FL-001")]
        provider = WarehouseStateProvider(
            equipment_status_skill=_mock_status_skill(_make_status_result(*assets))
        )
        proposal = _make_proposal("FL-001")
        assignment_skill = _mock_assignment_skill(proposal)
        engine = DecisionEngine()

        async def run():
            return await state_aware_ops.propose_equipment_assignment(
                asset_id="FL-001",
                assignee="worker-42",
                state_provider=provider,
                decision_engine=engine,
                assignment_skill=assignment_skill,
            )

        response = asyncio.run(run())

        assert response["status"] == "requires_human_approval"
        assert response["executed"] is False
        assert response["action"] == "warehouse.equipment.assign"
        assert "proposal_id" in response
        assert "decision_id" in response
        assert "snapshot_id" in response

    def test_proposal_id_matches_skill_output(self):
        assets = [_make_asset("FL-001")]
        provider = WarehouseStateProvider(
            equipment_status_skill=_mock_status_skill(_make_status_result(*assets))
        )
        proposal = _make_proposal("FL-001")
        assignment_skill = _mock_assignment_skill(proposal)
        engine = DecisionEngine()

        async def run():
            return await state_aware_ops.propose_equipment_assignment(
                asset_id="FL-001",
                assignee="w-1",
                state_provider=provider,
                decision_engine=engine,
                assignment_skill=assignment_skill,
            )

        response = asyncio.run(run())
        assert response["proposal_id"] == proposal.proposal_id
        assert response["proposal_id"] != response["decision_id"]

    def test_trace_id_propagated(self):
        assets = [_make_asset("FL-001")]
        provider = WarehouseStateProvider(
            equipment_status_skill=_mock_status_skill(_make_status_result(*assets))
        )
        assignment_skill = _mock_assignment_skill(_make_proposal("FL-001"))
        engine = DecisionEngine()

        async def run():
            return await state_aware_ops.propose_equipment_assignment(
                asset_id="FL-001",
                assignee="w-1",
                trace_id="trace-phase5",
                state_provider=provider,
                decision_engine=engine,
                assignment_skill=assignment_skill,
            )

        response = asyncio.run(run())
        assert response["trace_id"] == "trace-phase5"

    def test_violations_list_on_requires_human_approval(self):
        assets = [_make_asset("FL-001")]
        provider = WarehouseStateProvider(
            equipment_status_skill=_mock_status_skill(_make_status_result(*assets))
        )
        assignment_skill = _mock_assignment_skill(_make_proposal("FL-001"))
        engine = DecisionEngine()

        async def run():
            return await state_aware_ops.propose_equipment_assignment(
                asset_id="FL-001",
                assignee="w-1",
                state_provider=provider,
                decision_engine=engine,
                assignment_skill=assignment_skill,
            )

        response = asyncio.run(run())
        assert isinstance(response["violations"], list)
        assert any(v["rule"] == "approval.required" for v in response["violations"])

    def test_assignment_skill_called_once(self):
        assets = [_make_asset("FL-001")]
        provider = WarehouseStateProvider(
            equipment_status_skill=_mock_status_skill(_make_status_result(*assets))
        )
        assignment_skill = _mock_assignment_skill(_make_proposal("FL-001"))
        engine = DecisionEngine()

        async def run():
            await state_aware_ops.propose_equipment_assignment(
                asset_id="FL-001",
                assignee="w-1",
                state_provider=provider,
                decision_engine=engine,
                assignment_skill=assignment_skill,
            )

        asyncio.run(run())
        assignment_skill.execute.assert_called_once()


# ---------------------------------------------------------------------------
# Part 19 — Stale state → REQUIRES_FRESH_STATE
# ---------------------------------------------------------------------------


class TestStaleStatePath:
    def test_stale_state_returns_requires_fresh_state(self):
        stale_eq = _stale_equipment_state("FL-001")
        provider = _mock_provider(_state_with(stale_eq))
        assignment_skill = _mock_assignment_skill(_make_proposal("FL-001"))
        engine = DecisionEngine()

        async def run():
            return await state_aware_ops.propose_equipment_assignment(
                asset_id="FL-001",
                assignee="w-1",
                state_provider=provider,
                decision_engine=engine,
                assignment_skill=assignment_skill,
            )

        response = asyncio.run(run())

        assert response["status"] == "requires_fresh_state"
        assert response["executed"] is False

    def test_stale_state_violation_rule(self):
        stale_eq = _stale_equipment_state("FL-001")
        provider = _mock_provider(_state_with(stale_eq))
        assignment_skill = _mock_assignment_skill(_make_proposal("FL-001"))
        engine = DecisionEngine()

        async def run():
            return await state_aware_ops.propose_equipment_assignment(
                asset_id="FL-001",
                assignee="w-1",
                state_provider=provider,
                decision_engine=engine,
                assignment_skill=assignment_skill,
            )

        response = asyncio.run(run())
        rules = [v["rule"] for v in response.get("violations", [])]
        assert "state.equipment_stale" in rules

    def test_state_assembly_error_returns_error_status(self):
        provider = MagicMock()
        provider.get_state = AsyncMock(side_effect=RuntimeError("DB down"))
        assignment_skill = _mock_assignment_skill(_make_proposal("FL-001"))
        engine = DecisionEngine()

        async def run():
            return await state_aware_ops.propose_equipment_assignment(
                asset_id="FL-001",
                assignee="w-1",
                state_provider=provider,
                decision_engine=engine,
                assignment_skill=assignment_skill,
            )

        response = asyncio.run(run())
        assert response["status"] == "error"
        assert response["executed"] is False


# ---------------------------------------------------------------------------
# Part 20 — Missing asset → REJECTED
# ---------------------------------------------------------------------------


class TestMissingAssetPath:
    def test_asset_not_in_snapshot_rejected(self):
        # State has FL-002; request targets FL-001
        assets = [_make_asset("FL-002")]
        provider = WarehouseStateProvider(
            equipment_status_skill=_mock_status_skill(_make_status_result(*assets))
        )
        assignment_skill = _mock_assignment_skill(_make_proposal("FL-001"))
        engine = DecisionEngine()

        async def run():
            return await state_aware_ops.propose_equipment_assignment(
                asset_id="FL-001",
                assignee="w-1",
                state_provider=provider,
                decision_engine=engine,
                assignment_skill=assignment_skill,
            )

        response = asyncio.run(run())

        assert response["status"] == "rejected"
        assert response["executed"] is False

    def test_missing_asset_violation_rule(self):
        assets = [_make_asset("FL-002")]
        provider = WarehouseStateProvider(
            equipment_status_skill=_mock_status_skill(_make_status_result(*assets))
        )
        assignment_skill = _mock_assignment_skill(_make_proposal("FL-001"))
        engine = DecisionEngine()

        async def run():
            return await state_aware_ops.propose_equipment_assignment(
                asset_id="FL-001",
                assignee="w-1",
                state_provider=provider,
                decision_engine=engine,
                assignment_skill=assignment_skill,
            )

        response = asyncio.run(run())
        rules = [v["rule"] for v in response.get("violations", [])]
        assert "equipment.asset_not_found" in rules

    def test_empty_fleet_also_rejected(self):
        provider = WarehouseStateProvider(
            equipment_status_skill=_mock_status_skill(_make_status_result())
        )
        assignment_skill = _mock_assignment_skill(_make_proposal("FL-001"))
        engine = DecisionEngine()

        async def run():
            return await state_aware_ops.propose_equipment_assignment(
                asset_id="FL-001",
                assignee="w-1",
                state_provider=provider,
                decision_engine=engine,
                assignment_skill=assignment_skill,
            )

        response = asyncio.run(run())
        assert response["status"] == "rejected"


# ---------------------------------------------------------------------------
# ActionExecutor boundary (Part 11)
# ---------------------------------------------------------------------------


class TestActionExecutorBoundary:
    def test_no_op_executor_does_not_raise_on_approved(self):
        from maiw_decision.models import DecisionOutcome, DecisionResult

        executor = NoOpActionExecutor()
        proposal = _make_proposal("FL-001")
        result = DecisionResult(
            request_id="req-1",
            proposal_id=proposal.proposal_id,
            outcome=DecisionOutcome.APPROVED,
        )

        async def run():
            return await executor.execute(proposal, result)

        exec_result = asyncio.run(run())
        assert exec_result.executed is False
        assert exec_result.proposal_id == proposal.proposal_id

    def test_no_op_executor_raises_on_non_approved(self):
        from maiw_decision.models import DecisionOutcome, DecisionResult

        executor = NoOpActionExecutor()
        proposal = _make_proposal("FL-001")
        result = DecisionResult(
            request_id="req-1",
            proposal_id=proposal.proposal_id,
            outcome=DecisionOutcome.REQUIRES_HUMAN_APPROVAL,
        )

        async def run():
            return await executor.execute(proposal, result)

        with pytest.raises(ValueError, match="non-APPROVED"):
            asyncio.run(run())
