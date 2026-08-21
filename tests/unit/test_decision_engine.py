# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for DecisionEngine.

Covers:
  - READ_ONLY proposals are APPROVED immediately
  - LOW risk + requires_approval=False → APPROVED
  - MEDIUM risk → REQUIRES_HUMAN_APPROVAL
  - HIGH risk → REQUIRES_HUMAN_APPROVAL
  - requires_approval=True (any risk) → REQUIRES_HUMAN_APPROVAL
  - Stale equipment state → REQUIRES_FRESH_STATE
  - Absent equipment state + asset_id → REQUIRES_FRESH_STATE
  - Asset not found in snapshot → REJECTED
  - Asset found → passes freshness gate, proceeds to approval rule
  - DecisionAuditRecord: fields, to_log_dict
  - DecisionRequest: construction and field access
  - DecisionResult: construction and field access

All tests are synchronous (DecisionEngine.evaluate is not async).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from maiw_decision import (
    ConstraintViolation,
    DecisionAuditRecord,
    DecisionEngine,
    DecisionOutcome,
    DecisionRequest,
    DecisionResult,
)
from maiw_mcp.contracts.actions import ActionProposal, RiskLevel
from maiw_state import (
    EquipmentAssetSummary,
    EquipmentState,
    StateFreshness,
    WarehouseState,
    WarehouseStateSnapshot,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_snapshot(
    *,
    warehouse_id: str = "wh-1",
    with_equipment: bool = False,
    equipment_stale: bool = False,
    assets: list[EquipmentAssetSummary] | None = None,
) -> WarehouseStateSnapshot:
    equipment = None
    if with_equipment:
        if equipment_stale:
            old_ts = datetime.now(timezone.utc) - timedelta(seconds=60)
            freshness = StateFreshness.from_observed_at(old_ts, stale_after_ms=30_000)
        else:
            freshness = StateFreshness.now()
        equipment = EquipmentState(
            warehouse_id=warehouse_id,
            assets=assets or [],
            total_count=len(assets or []),
            freshness=freshness,
        )
    state = WarehouseState(
        warehouse_id=warehouse_id,
        observed_at=datetime.now(timezone.utc),
        equipment=equipment,
    )
    return WarehouseStateSnapshot.seal(state)


def _make_proposal(
    *,
    action: str = "assign_equipment",
    domain: str = "equipment",
    risk_level: RiskLevel = RiskLevel.MEDIUM,
    requires_approval: bool = True,
    parameters: dict | None = None,
) -> ActionProposal:
    return ActionProposal(
        action=action,
        domain=domain,
        risk_level=risk_level,
        requires_approval=requires_approval,
        parameters=parameters or {},
        reason="test",
        requested_by="test-agent",
    )


def _make_request(
    proposal: ActionProposal,
    snapshot: WarehouseStateSnapshot,
    *,
    trace_id: str | None = None,
) -> DecisionRequest:
    return DecisionRequest(
        proposal=proposal,
        state=snapshot,
        trace_id=trace_id,
    )


# ---------------------------------------------------------------------------
# READ_ONLY bypass
# ---------------------------------------------------------------------------


class TestReadOnlyBypass:
    def test_read_only_is_approved(self):
        engine = DecisionEngine()
        snap = _make_snapshot()
        proposal = _make_proposal(
            action="get_equipment_status",
            risk_level=RiskLevel.READ_ONLY,
            requires_approval=False,
            parameters={},
        )
        req = _make_request(proposal, snap)
        result, audit = engine.evaluate(req)
        assert result.outcome == DecisionOutcome.APPROVED
        assert result.violations == []

    def test_read_only_audit_has_correct_fields(self):
        engine = DecisionEngine()
        snap = _make_snapshot()
        proposal = _make_proposal(
            action="get_equipment_status",
            risk_level=RiskLevel.READ_ONLY,
            requires_approval=False,
        )
        req = _make_request(proposal, snap, trace_id="trace-001")
        result, audit = engine.evaluate(req)
        assert audit.outcome == DecisionOutcome.APPROVED
        assert audit.trace_id == "trace-001"
        assert audit.action == "get_equipment_status"


# ---------------------------------------------------------------------------
# LOW risk
# ---------------------------------------------------------------------------


class TestLowRisk:
    def test_low_risk_no_approval_approved(self):
        engine = DecisionEngine()
        snap = _make_snapshot()
        proposal = _make_proposal(
            risk_level=RiskLevel.LOW,
            requires_approval=False,
            parameters={},
        )
        req = _make_request(proposal, snap)
        result, audit = engine.evaluate(req)
        assert result.outcome == DecisionOutcome.APPROVED

    def test_low_risk_with_approval_requires_human(self):
        engine = DecisionEngine()
        snap = _make_snapshot()
        proposal = _make_proposal(
            risk_level=RiskLevel.LOW,
            requires_approval=True,
            parameters={},
        )
        req = _make_request(proposal, snap)
        result, audit = engine.evaluate(req)
        assert result.outcome == DecisionOutcome.REQUIRES_HUMAN_APPROVAL


# ---------------------------------------------------------------------------
# MEDIUM / HIGH / CRITICAL
# ---------------------------------------------------------------------------


class TestHighRisk:
    @pytest.mark.parametrize(
        "risk", [RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
    )
    def test_medium_high_critical_requires_human_approval(self, risk):
        engine = DecisionEngine()
        snap = _make_snapshot()
        proposal = _make_proposal(
            risk_level=risk,
            requires_approval=True,
            parameters={},
        )
        req = _make_request(proposal, snap)
        result, audit = engine.evaluate(req)
        assert result.outcome == DecisionOutcome.REQUIRES_HUMAN_APPROVAL
        assert len(result.violations) >= 1

    def test_medium_with_asset_requires_human_approval(self):
        asset = EquipmentAssetSummary(
            asset_id="FL-001",
            equipment_type="forklift",
            model="M",
            zone="A",
            status="available",
        )
        snap = _make_snapshot(with_equipment=True, assets=[asset])
        proposal = _make_proposal(
            risk_level=RiskLevel.MEDIUM,
            requires_approval=True,
            parameters={"asset_id": "FL-001"},
        )
        req = _make_request(proposal, snap)
        engine = DecisionEngine()
        result, _ = engine.evaluate(req)
        assert result.outcome == DecisionOutcome.REQUIRES_HUMAN_APPROVAL


# ---------------------------------------------------------------------------
# Freshness checks
# ---------------------------------------------------------------------------


class TestFreshnessChecks:
    def test_absent_equipment_state_with_asset_id_requires_fresh(self):
        snap = _make_snapshot(with_equipment=False)
        proposal = _make_proposal(
            parameters={"asset_id": "FL-001"},
            risk_level=RiskLevel.MEDIUM,
        )
        req = _make_request(proposal, snap)
        engine = DecisionEngine()
        result, _ = engine.evaluate(req)
        assert result.outcome == DecisionOutcome.REQUIRES_FRESH_STATE
        assert any(v.rule == "state.equipment_absent" for v in result.violations)

    def test_stale_equipment_state_requires_fresh(self):
        snap = _make_snapshot(with_equipment=True, equipment_stale=True)
        proposal = _make_proposal(
            parameters={"asset_id": "FL-001"},
            risk_level=RiskLevel.MEDIUM,
        )
        req = _make_request(proposal, snap)
        engine = DecisionEngine()
        result, _ = engine.evaluate(req)
        assert result.outcome == DecisionOutcome.REQUIRES_FRESH_STATE
        assert any(v.rule == "state.equipment_stale" for v in result.violations)

    def test_no_asset_id_skips_freshness_check(self):
        snap = _make_snapshot(with_equipment=False)
        proposal = _make_proposal(
            parameters={},
            risk_level=RiskLevel.MEDIUM,
            requires_approval=True,
        )
        req = _make_request(proposal, snap)
        engine = DecisionEngine()
        result, _ = engine.evaluate(req)
        # No asset_id → freshness not checked → falls through to approval rule
        assert result.outcome == DecisionOutcome.REQUIRES_HUMAN_APPROVAL


# ---------------------------------------------------------------------------
# Asset not found → REJECTED
# ---------------------------------------------------------------------------


class TestAssetNotFound:
    def test_asset_not_in_snapshot_rejected(self):
        snap = _make_snapshot(with_equipment=True, assets=[])
        proposal = _make_proposal(
            parameters={"asset_id": "FL-MISSING"},
            risk_level=RiskLevel.MEDIUM,
        )
        req = _make_request(proposal, snap)
        engine = DecisionEngine()
        result, audit = engine.evaluate(req)
        assert result.outcome == DecisionOutcome.REJECTED
        assert any(v.rule == "equipment.asset_not_found" for v in result.violations)
        assert audit.outcome == DecisionOutcome.REJECTED

    def test_asset_found_proceeds_past_asset_check(self):
        asset = EquipmentAssetSummary(
            asset_id="FL-001",
            equipment_type="forklift",
            model="M",
            zone="A",
            status="available",
        )
        snap = _make_snapshot(with_equipment=True, assets=[asset])
        proposal = _make_proposal(
            parameters={"asset_id": "FL-001"},
            risk_level=RiskLevel.MEDIUM,
            requires_approval=True,
        )
        req = _make_request(proposal, snap)
        engine = DecisionEngine()
        result, _ = engine.evaluate(req)
        # Asset found; outcome determined by risk/approval rule
        assert result.outcome == DecisionOutcome.REQUIRES_HUMAN_APPROVAL


# ---------------------------------------------------------------------------
# DecisionAuditRecord
# ---------------------------------------------------------------------------


class TestDecisionAuditRecord:
    def test_from_result_fields(self):
        engine = DecisionEngine()
        snap = _make_snapshot()
        proposal = _make_proposal(
            risk_level=RiskLevel.MEDIUM,
            requires_approval=True,
            parameters={},
        )
        req = _make_request(proposal, snap, trace_id="t-xyz")
        result, audit = engine.evaluate(req)
        assert audit.result_id == result.result_id
        assert audit.proposal_id == result.proposal_id
        assert audit.snapshot_id == snap.snapshot_id
        assert audit.domain == "equipment"
        assert audit.risk_level == "medium"
        assert audit.trace_id == "t-xyz"
        assert audit.engine_version == engine.version

    def test_to_log_dict_has_event_key(self):
        engine = DecisionEngine()
        snap = _make_snapshot()
        proposal = _make_proposal(risk_level=RiskLevel.MEDIUM, parameters={})
        req = _make_request(proposal, snap)
        _, audit = engine.evaluate(req)
        d = audit.to_log_dict()
        assert d["event"] == "decision_engine.evaluation"
        assert "outcome" in d
        assert "proposal_id" in d
        assert "snapshot_id" in d

    def test_violation_rules_in_log_dict(self):
        snap = _make_snapshot(with_equipment=True, assets=[])
        proposal = _make_proposal(
            parameters={"asset_id": "FL-MISSING"},
            risk_level=RiskLevel.MEDIUM,
        )
        req = _make_request(proposal, snap)
        engine = DecisionEngine()
        _, audit = engine.evaluate(req)
        d = audit.to_log_dict()
        assert "equipment.asset_not_found" in d["violation_rules"]
        assert d["violation_count"] == 1


# ---------------------------------------------------------------------------
# DecisionRequest / DecisionResult construction
# ---------------------------------------------------------------------------


class TestModels:
    def test_decision_request_gets_unique_id(self):
        snap = _make_snapshot()
        proposal = _make_proposal(parameters={})
        r1 = DecisionRequest(proposal=proposal, state=snap)
        r2 = DecisionRequest(proposal=proposal, state=snap)
        assert r1.request_id != r2.request_id

    def test_decision_result_echoes_ids(self):
        snap = _make_snapshot()
        proposal = _make_proposal(parameters={})
        req = DecisionRequest(proposal=proposal, state=snap)
        engine = DecisionEngine()
        result, _ = engine.evaluate(req)
        assert result.request_id == req.request_id
        assert result.proposal_id == proposal.proposal_id
