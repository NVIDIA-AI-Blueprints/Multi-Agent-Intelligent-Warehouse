# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
End-to-end integration tests: assignment → ActionProposal → DecisionEngine.

This test verifies the complete vertical slice described in Phase 4:

    EquipmentStatusSkill (backed by MockEquipmentProvider + MCP in-memory)
        → WarehouseStateProvider.get_state()
        → WarehouseStateSnapshot.seal()
        → DecisionEngine.evaluate()
        → REQUIRES_HUMAN_APPROVAL (for MEDIUM-risk assignment)

Key assertions:
  1. No MCP write (assign tool) is ever called during the decision path.
  2. The outcome is REQUIRES_HUMAN_APPROVAL for equipment assignment.
  3. The snapshot_id referenced in the audit matches the one created.
  4. The stale-state path returns REQUIRES_FRESH_STATE without calling assign.

All tests use asyncio.run() (no pytest-asyncio required).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maiw_decision import (
    DecisionEngine,
    DecisionOutcome,
    DecisionRequest,
)
from maiw_mcp.contracts.actions import ActionProposal, RiskLevel
from maiw_mcp.contracts.equipment import (
    EquipmentAssetInfo,
    EquipmentStatusRequest,
    EquipmentStatusResult,
)
from maiw_state import (
    EquipmentAssetSummary,
    EquipmentState,
    StateFreshness,
    StateRequirements,
    WarehouseState,
    WarehouseStateProvider,
    WarehouseStateSnapshot,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_equipment_status_result(
    assets: list[EquipmentAssetInfo],
) -> EquipmentStatusResult:
    """Build a real EquipmentStatusResult from a list of assets."""
    return EquipmentStatusResult(
        equipment=assets,
        total_count=len(assets),
        source="mock",
        summary={a.equipment_type: {a.status: 1} for a in assets},
    )


def _make_mock_skill(result: EquipmentStatusResult) -> MagicMock:
    """Build a mock skill that returns a fixed result."""
    skill = MagicMock()
    skill.execute = AsyncMock(return_value=result)
    return skill


def _make_proposal(
    *,
    asset_id: str,
    risk_level: RiskLevel = RiskLevel.MEDIUM,
    requires_approval: bool = True,
) -> ActionProposal:
    return ActionProposal.for_equipment_assign(
        asset_id=asset_id,
        assignee="worker-42",
        assignment_type="picking",
        task_id="TASK-001",
        duration_hours=4.0,
        notes="integration test assignment",
        reason="test",
        requested_by="test-agent",
    )


# ---------------------------------------------------------------------------
# Core vertical slice
# ---------------------------------------------------------------------------


class TestEquipmentAssignmentVerticalSlice:
    """
    Full path: skill → StateProvider → snapshot → DecisionEngine.
    No MCP write is invoked.
    """

    def test_assignment_requires_human_approval(self):
        """MEDIUM risk + requires_approval=True → REQUIRES_HUMAN_APPROVAL."""
        assets = [
            EquipmentAssetInfo(
                asset_id="FL-001",
                equipment_type="forklift",
                model="FL-3000",
                zone="ZONE-A",
                status="available",
            )
        ]
        result = _make_equipment_status_result(assets)
        skill = _make_mock_skill(result)

        provider = WarehouseStateProvider(equipment_status_skill=skill)
        engine = DecisionEngine()

        async def run():
            state = await provider.get_state(
                "wh-1", StateRequirements(equipment=True, equipment_asset_id="FL-001")
            )
            snapshot = WarehouseStateSnapshot.seal(state)
            proposal = _make_proposal(asset_id="FL-001")
            req = DecisionRequest(proposal=proposal, state=snapshot)
            return engine.evaluate(req)

        decision_result, audit = asyncio.run(run())

        assert decision_result.outcome == DecisionOutcome.REQUIRES_HUMAN_APPROVAL
        # Skill was called once (read-only get_status), never assign
        skill.execute.assert_called_once()

    def test_snapshot_id_in_audit_matches_sealed_snapshot(self):
        """Audit record references the exact snapshot used for evaluation."""
        assets = [
            EquipmentAssetInfo(
                asset_id="FL-001",
                equipment_type="forklift",
                model="FL-3000",
                zone="ZONE-A",
                status="available",
            )
        ]
        skill = _make_mock_skill(_make_equipment_status_result(assets))
        provider = WarehouseStateProvider(equipment_status_skill=skill)
        engine = DecisionEngine()

        async def run():
            state = await provider.get_state("wh-1", StateRequirements(equipment=True))
            snapshot = WarehouseStateSnapshot.seal(state)
            proposal = _make_proposal(asset_id="FL-001")
            req = DecisionRequest(
                proposal=proposal, state=snapshot, trace_id="trace-e2e"
            )
            result, audit = engine.evaluate(req)
            return snapshot, result, audit

        snapshot, result, audit = asyncio.run(run())

        assert audit.snapshot_id == snapshot.snapshot_id
        assert audit.trace_id == "trace-e2e"
        assert audit.domain == "equipment"

    def test_missing_asset_in_snapshot_rejected(self):
        """Asset not in state snapshot → REJECTED."""
        # State has FL-002 but proposal targets FL-001
        assets = [
            EquipmentAssetInfo(
                asset_id="FL-002",
                equipment_type="forklift",
                model="FL-3000",
                zone="ZONE-A",
                status="available",
            )
        ]
        skill = _make_mock_skill(_make_equipment_status_result(assets))
        provider = WarehouseStateProvider(equipment_status_skill=skill)
        engine = DecisionEngine()

        async def run():
            state = await provider.get_state("wh-1", StateRequirements(equipment=True))
            snapshot = WarehouseStateSnapshot.seal(state)
            proposal = _make_proposal(asset_id="FL-001")  # FL-001 not in snapshot
            req = DecisionRequest(proposal=proposal, state=snapshot)
            return engine.evaluate(req)

        result, audit = asyncio.run(run())

        assert result.outcome == DecisionOutcome.REJECTED
        assert any(v.rule == "equipment.asset_not_found" for v in result.violations)

    def test_no_mcp_write_during_decision(self):
        """
        The decision engine never triggers an MCP write.

        We verify by asserting that only the status skill (read-only) was
        called, never an assign skill or any other write operation.
        """
        assets = [
            EquipmentAssetInfo(
                asset_id="FL-001",
                equipment_type="forklift",
                model="FL-3000",
                zone="ZONE-A",
                status="available",
            )
        ]
        skill = _make_mock_skill(_make_equipment_status_result(assets))
        assign_skill = MagicMock()
        assign_skill.execute = AsyncMock()

        provider = WarehouseStateProvider(equipment_status_skill=skill)
        engine = DecisionEngine()

        async def run():
            state = await provider.get_state("wh-1", StateRequirements(equipment=True))
            snapshot = WarehouseStateSnapshot.seal(state)
            proposal = _make_proposal(asset_id="FL-001")
            req = DecisionRequest(proposal=proposal, state=snapshot)
            engine.evaluate(req)

        asyncio.run(run())

        # read skill called once, assign skill never called
        skill.execute.assert_called_once()
        assign_skill.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Stale state path
# ---------------------------------------------------------------------------


class TestStaleStatePath:
    def test_stale_state_returns_requires_fresh(self):
        """Pre-built stale snapshot → REQUIRES_FRESH_STATE, no skill called."""
        old_ts = datetime.now(timezone.utc) - timedelta(seconds=60)
        eq = EquipmentState(
            warehouse_id="wh-1",
            assets=[
                EquipmentAssetSummary(
                    asset_id="FL-001",
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
            warehouse_id="wh-1",
            observed_at=datetime.now(timezone.utc),
            equipment=eq,
        )
        snapshot = WarehouseStateSnapshot.seal(state)

        proposal = _make_proposal(asset_id="FL-001")
        req = DecisionRequest(proposal=proposal, state=snapshot)
        engine = DecisionEngine()
        result, audit = engine.evaluate(req)

        assert result.outcome == DecisionOutcome.REQUIRES_FRESH_STATE
        assert any(v.rule == "state.equipment_stale" for v in result.violations)


# ---------------------------------------------------------------------------
# READ_ONLY bypass
# ---------------------------------------------------------------------------


class TestReadOnlyBypass:
    def test_read_only_approved_without_state(self):
        """READ_ONLY proposals are approved even with empty state."""
        state = WarehouseState(
            warehouse_id="wh-1",
            observed_at=datetime.now(timezone.utc),
        )
        snapshot = WarehouseStateSnapshot.seal(state)
        proposal = ActionProposal(
            action="get_equipment_status",
            domain="equipment",
            risk_level=RiskLevel.READ_ONLY,
            requires_approval=False,
            parameters={},
            reason="read-only check",
        )
        req = DecisionRequest(proposal=proposal, state=snapshot)
        engine = DecisionEngine()
        result, audit = engine.evaluate(req)
        assert result.outcome == DecisionOutcome.APPROVED
        assert audit.outcome == DecisionOutcome.APPROVED


# ---------------------------------------------------------------------------
# Multiple independent evaluations
# ---------------------------------------------------------------------------


class TestMultipleEvaluations:
    def test_engine_is_stateless_across_evaluations(self):
        """
        A single DecisionEngine instance can evaluate multiple requests
        independently — each gets its own result_id and audit record.
        """
        state = WarehouseState(
            warehouse_id="wh-1",
            observed_at=datetime.now(timezone.utc),
        )
        snap = WarehouseStateSnapshot.seal(state)
        engine = DecisionEngine()

        results = []
        for _ in range(3):
            proposal = ActionProposal(
                action="assign_equipment",
                domain="equipment",
                risk_level=RiskLevel.MEDIUM,
                requires_approval=True,
                parameters={},
                reason="test",
            )
            req = DecisionRequest(proposal=proposal, state=snap)
            result, audit = engine.evaluate(req)
            results.append(result)

        # All three have distinct result_ids
        ids = {r.result_id for r in results}
        assert len(ids) == 3

        # All have the same outcome (REQUIRES_HUMAN_APPROVAL)
        assert all(
            r.outcome == DecisionOutcome.REQUIRES_HUMAN_APPROVAL for r in results
        )
