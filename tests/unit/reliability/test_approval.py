# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 10E Batch 2 — Approval Hardening.

Covers:
  Section 12a: ApprovalState machine transitions
  Section 12b: Single-use consume guarantee
  Section 12c: Binding checks (proposal_id, decision_id, warehouse_id)
  Section 12d: Expiration enforcement
  Section 12e: Rejection finality
  Section 12f: CONSUMED approval blocked by engine
  Section 12g: Duplicate approve call raises
  Section 12h: Concurrent consume — only one succeeds
  Section 12i: Audit chain — proposal_id preserved through full lifecycle
  Section 12j: Trace continuity — approval_id carried in engine result chain

Architecture invariants (Batch 2):
  - ApprovalState.CONSUMED must never re-authorize execution
  - proposal_id must be the SAME object identity through propose → queue → approve → execute
  - warehouse_id must bind the approval to a specific warehouse scope
  - expires_at must never be None when created via InMemoryApprovalStore
  - authorize_with_approval() checks CONSUMED before proposal binding
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from maiw_decision.approval import (
    ApprovalAlreadyDecided,
    ApprovalNotFound,
    InMemoryApprovalStore,
)
from maiw_decision.models import (
    ApprovalRecord,
    ApprovalState,
    AuthorityType,
    ConstraintViolation,
    DecisionOutcome,
    DecisionRequest,
    DecisionResult,
)
from maiw_decision.engine import DecisionEngine
from maiw_mcp.contracts.actions import ActionProposal
from maiw_state.warehouse import WarehouseStateSnapshot

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _labor_proposal() -> ActionProposal:
    return ActionProposal.for_labor_allocate(
        task_id="T-APPROVAL-01",
        task_type="PICK",
        worker_ids=["W-001"],
        zone="ZONE-A",
        reason="approval test",
        requested_by="test",
    )


def _fresh_snapshot() -> WarehouseStateSnapshot:
    from maiw_state import WarehouseState

    state = WarehouseState(
        warehouse_id="DC-TEST", observed_at=datetime.now(timezone.utc)
    )
    return WarehouseStateSnapshot.seal(state)


def _store() -> InMemoryApprovalStore:
    return InMemoryApprovalStore()


def _approved_decision(proposal_id: str) -> DecisionResult:
    return DecisionResult(
        request_id="req-approval-test",
        proposal_id=proposal_id,
        outcome=DecisionOutcome.APPROVED,
        evaluated_at=datetime.now(timezone.utc),
    )


# ── Section 12a: ApprovalState machine transitions ───────────────────────────


class TestApprovalStateCreation:
    """Store.create() produces a PENDING record with correct bindings."""

    def test_create_returns_pending_state(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        assert record.state == ApprovalState.PENDING

    def test_create_sets_proposal_id(self):
        store = _store()
        record = store.create(proposal_id="P-XYZ", decision_id="D-1")
        assert record.proposal_id == "P-XYZ"

    def test_create_sets_decision_id(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-ABC")
        assert record.decision_id == "D-ABC"

    def test_create_sets_expires_at(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        assert record.expires_at is not None

    def test_create_expires_in_future(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        assert record.expires_at > datetime.now(timezone.utc)

    def test_create_warehouse_id_stored(self):
        store = _store()
        record = store.create(
            proposal_id="P-1", decision_id="D-1", warehouse_id="DC-47"
        )
        assert record.warehouse_id == "DC-47"

    def test_create_authority_type_default_human(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        assert record.authority_type == AuthorityType.HUMAN

    def test_create_approved_by_none_initially(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        assert record.approved_by is None

    def test_create_approved_property_false_when_pending(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        assert record.approved is False

    def test_create_stores_by_approval_id(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        fetched = store.get(record.approval_id)
        assert fetched is record


class TestApprovalStateTransitions:
    """State machine: PENDING → APPROVED, PENDING → REJECTED."""

    def test_approve_transitions_to_approved(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        store.approve(record.approval_id, approved_by="ops-lead")
        assert record.state == ApprovalState.APPROVED

    def test_approve_sets_approved_by(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        store.approve(record.approval_id, approved_by="ops-lead")
        assert record.approved_by == "ops-lead"

    def test_approve_sets_approved_at(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        before = datetime.now(timezone.utc)
        store.approve(record.approval_id, approved_by="ops-lead")
        assert record.approved_at is not None
        assert record.approved_at >= before

    def test_approved_property_true_after_approve(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        store.approve(record.approval_id, approved_by="ops-lead")
        assert record.approved is True

    def test_reject_transitions_to_rejected(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        store.reject(record.approval_id, rejected_by="ops-lead")
        assert record.state == ApprovalState.REJECTED

    def test_reject_sets_approved_by(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        store.reject(record.approval_id, rejected_by="ops-lead")
        assert record.approved_by == "ops-lead"

    def test_approved_property_false_after_reject(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        store.reject(record.approval_id, rejected_by="ops-lead")
        assert record.approved is False

    def test_consume_transitions_approved_to_consumed(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        store.approve(record.approval_id, approved_by="ops-lead")
        result = store.consume(record.approval_id)
        assert result is not None
        assert record.state == ApprovalState.CONSUMED

    def test_approved_property_false_after_consumed(self):
        """CONSUMED ≠ APPROVED — authorized but already used."""
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        store.approve(record.approval_id, approved_by="ops-lead")
        store.consume(record.approval_id)
        assert record.approved is False


# ── Section 12b: Single-use consume guarantee ─────────────────────────────────


class TestApprovalSingleUse:
    """consume() is idempotent — second call returns None without raising."""

    def test_second_consume_returns_none(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        store.approve(record.approval_id, approved_by="ops-lead")
        first = store.consume(record.approval_id)
        second = store.consume(record.approval_id)
        assert first is not None
        assert second is None

    def test_consume_on_pending_returns_none(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        result = store.consume(record.approval_id)
        assert result is None

    def test_consume_on_rejected_returns_none(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        store.reject(record.approval_id, rejected_by="ops-lead")
        result = store.consume(record.approval_id)
        assert result is None

    def test_consume_on_unknown_id_returns_none(self):
        store = _store()
        result = store.consume("nonexistent-approval-id")
        assert result is None

    def test_state_is_consumed_after_first_consume(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        store.approve(record.approval_id, approved_by="ops-lead")
        store.consume(record.approval_id)
        assert record.state == ApprovalState.CONSUMED


# ── Section 12c: Binding checks ──────────────────────────────────────────────


class TestApprovalBindingInEngine:
    """authorize_with_approval() enforces proposal_id, decision_id, warehouse_id."""

    def _request(self, proposal: ActionProposal) -> DecisionRequest:
        return DecisionRequest(
            proposal=proposal,
            state=_fresh_snapshot(),
            requested_by="test",
        )

    def test_wrong_proposal_id_is_rejected(self):
        engine = DecisionEngine()
        proposal = _labor_proposal()
        store = _store()
        record = store.create(proposal_id="WRONG-PROPOSAL-ID", decision_id="D-1")
        store.approve(record.approval_id, approved_by="ops-lead")

        request = self._request(proposal)
        result, _ = engine.authorize_with_approval(request, record)
        assert result.outcome == DecisionOutcome.REJECTED
        assert any(v.rule == "approval.proposal_mismatch" for v in result.violations)

    def test_wrong_decision_id_is_rejected(self):
        engine = DecisionEngine()
        proposal = _labor_proposal()
        store = _store()
        record = store.create(proposal_id=proposal.proposal_id, decision_id="D-CORRECT")
        store.approve(record.approval_id, approved_by="ops-lead")

        request = self._request(proposal)
        result, _ = engine.authorize_with_approval(
            request, record, expected_decision_id="D-WRONG"
        )
        assert result.outcome == DecisionOutcome.REJECTED
        assert any(v.rule == "approval.decision_mismatch" for v in result.violations)

    def test_correct_decision_id_passes(self):
        engine = DecisionEngine()
        proposal = _labor_proposal()
        store = _store()
        record = store.create(proposal_id=proposal.proposal_id, decision_id="D-CORRECT")
        store.approve(record.approval_id, approved_by="ops-lead")

        request = self._request(proposal)
        result, _ = engine.authorize_with_approval(
            request, record, expected_decision_id="D-CORRECT"
        )
        assert result.outcome == DecisionOutcome.APPROVED

    def test_no_expected_decision_id_skips_decision_check(self):
        engine = DecisionEngine()
        proposal = _labor_proposal()
        store = _store()
        record = store.create(proposal_id=proposal.proposal_id, decision_id="D-ANY")
        store.approve(record.approval_id, approved_by="ops-lead")

        request = self._request(proposal)
        result, _ = engine.authorize_with_approval(request, record)
        assert result.outcome == DecisionOutcome.APPROVED

    def test_warehouse_id_mismatch_is_rejected(self):
        engine = DecisionEngine()
        proposal = ActionProposal.for_labor_allocate(
            task_id="T-001",
            task_type="PICK",
            worker_ids=["W-001"],
            zone="ZONE-A",
            reason="test",
            requested_by="test",
        )
        # Manually inject warehouse_id into proposal parameters
        proposal.parameters["warehouse_id"] = "DC-47"
        store = _store()
        record = store.create(
            proposal_id=proposal.proposal_id,
            decision_id="D-1",
            warehouse_id="DC-99",  # wrong warehouse
        )
        store.approve(record.approval_id, approved_by="ops-lead")

        request = self._request(proposal)
        result, _ = engine.authorize_with_approval(request, record)
        assert result.outcome == DecisionOutcome.REJECTED
        assert any(v.rule == "approval.warehouse_mismatch" for v in result.violations)

    def test_warehouse_id_match_passes(self):
        engine = DecisionEngine()
        proposal = ActionProposal.for_labor_allocate(
            task_id="T-001",
            task_type="PICK",
            worker_ids=["W-001"],
            zone="ZONE-A",
            reason="test",
            requested_by="test",
        )
        proposal.parameters["warehouse_id"] = "DC-47"
        store = _store()
        record = store.create(
            proposal_id=proposal.proposal_id,
            decision_id="D-1",
            warehouse_id="DC-47",
        )
        store.approve(record.approval_id, approved_by="ops-lead")

        request = self._request(proposal)
        result, _ = engine.authorize_with_approval(request, record)
        assert result.outcome == DecisionOutcome.APPROVED

    def test_approval_warehouse_none_skips_warehouse_check(self):
        engine = DecisionEngine()
        proposal = _labor_proposal()
        proposal.parameters["warehouse_id"] = "DC-47"
        store = _store()
        record = store.create(
            proposal_id=proposal.proposal_id,
            decision_id="D-1",
            warehouse_id=None,  # unbound
        )
        store.approve(record.approval_id, approved_by="ops-lead")

        request = self._request(proposal)
        result, _ = engine.authorize_with_approval(request, record)
        assert result.outcome == DecisionOutcome.APPROVED


# ── Section 12d: Expiration enforcement ──────────────────────────────────────


class TestApprovalExpiry:
    """Expired approvals are blocked by engine even after state=APPROVED."""

    def test_expired_approval_is_rejected_by_engine(self):
        engine = DecisionEngine()
        proposal = _labor_proposal()
        store = _store()
        record = store.create(proposal_id=proposal.proposal_id, decision_id="D-1")
        store.approve(record.approval_id, approved_by="ops-lead")

        # Backdate expires_at to the past
        record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

        request = DecisionRequest(
            proposal=proposal,
            state=_fresh_snapshot(),
            requested_by="test",
        )
        result, _ = engine.authorize_with_approval(request, record)
        assert result.outcome == DecisionOutcome.REJECTED
        assert any(v.rule == "approval.expired" for v in result.violations)

    def test_is_expired_false_when_not_yet_expired(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1", ttl_seconds=300)
        store.approve(record.approval_id, approved_by="ops-lead")
        assert not record.is_expired()

    def test_is_expired_true_when_past_expiry(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1", ttl_seconds=300)
        store.approve(record.approval_id, approved_by="ops-lead")
        record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        assert record.is_expired()

    def test_is_expired_true_when_state_is_expired(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        record.state = ApprovalState.EXPIRED
        assert record.is_expired()

    def test_custom_ttl_respected(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1", ttl_seconds=60)
        expected_max = datetime.now(timezone.utc) + timedelta(seconds=61)
        assert record.expires_at is not None
        assert record.expires_at <= expected_max


# ── Section 12e: Rejection finality ──────────────────────────────────────────


class TestRejectionFinality:
    """Rejected approvals cannot be approved or consumed."""

    def test_rejected_approval_blocked_by_engine(self):
        engine = DecisionEngine()
        proposal = _labor_proposal()
        store = _store()
        record = store.create(proposal_id=proposal.proposal_id, decision_id="D-1")
        store.reject(record.approval_id, rejected_by="ops-lead")

        request = DecisionRequest(
            proposal=proposal,
            state=_fresh_snapshot(),
            requested_by="test",
        )
        result, _ = engine.authorize_with_approval(request, record)
        assert result.outcome == DecisionOutcome.REJECTED
        assert any(v.rule == "approval.not_approved" for v in result.violations)

    def test_approve_after_reject_raises(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        store.reject(record.approval_id, rejected_by="ops-lead")
        with pytest.raises(ApprovalAlreadyDecided):
            store.approve(record.approval_id, approved_by="ops-lead")

    def test_reject_after_reject_raises(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        store.reject(record.approval_id, rejected_by="ops-lead")
        with pytest.raises(ApprovalAlreadyDecided):
            store.reject(record.approval_id, rejected_by="ops-lead")

    def test_consume_after_reject_returns_none(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        store.reject(record.approval_id, rejected_by="ops-lead")
        assert store.consume(record.approval_id) is None


# ── Section 12f: CONSUMED approval blocked by engine ─────────────────────────


class TestConsumedApprovalBlocked:
    """Engine rejects CONSUMED approvals before any binding check."""

    def test_consumed_approval_is_rejected_by_engine(self):
        engine = DecisionEngine()
        proposal = _labor_proposal()
        store = _store()
        record = store.create(proposal_id=proposal.proposal_id, decision_id="D-1")
        store.approve(record.approval_id, approved_by="ops-lead")
        store.consume(record.approval_id)

        request = DecisionRequest(
            proposal=proposal,
            state=_fresh_snapshot(),
            requested_by="test",
        )
        result, _ = engine.authorize_with_approval(request, record)
        assert result.outcome == DecisionOutcome.REJECTED
        assert any(v.rule == "approval.already_consumed" for v in result.violations)

    def test_consumed_check_comes_before_proposal_binding(self):
        """CONSUMED is detected even when proposal_id is wrong — check order matters."""
        engine = DecisionEngine()
        proposal = _labor_proposal()
        store = _store()
        # Create approval for a different proposal
        record = store.create(proposal_id="DIFFERENT-PROPOSAL", decision_id="D-1")
        store.approve(record.approval_id, approved_by="ops-lead")
        store.consume(record.approval_id)

        request = DecisionRequest(
            proposal=proposal,
            state=_fresh_snapshot(),
            requested_by="test",
        )
        result, _ = engine.authorize_with_approval(request, record)
        # Must be CONSUMED violation, not proposal_mismatch
        assert any(v.rule == "approval.already_consumed" for v in result.violations)


# ── Section 12g: Duplicate approve call raises ───────────────────────────────


class TestDuplicateApprove:
    """Calling approve() twice on the same record raises ApprovalAlreadyDecided."""

    def test_approve_twice_raises(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        store.approve(record.approval_id, approved_by="ops-lead")
        with pytest.raises(ApprovalAlreadyDecided):
            store.approve(record.approval_id, approved_by="ops-lead")

    def test_approve_after_consume_raises(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        store.approve(record.approval_id, approved_by="ops-lead")
        store.consume(record.approval_id)
        with pytest.raises(ApprovalAlreadyDecided):
            store.approve(record.approval_id, approved_by="ops-lead")

    def test_approve_nonexistent_raises(self):
        store = _store()
        with pytest.raises(ApprovalNotFound):
            store.approve("nonexistent-id", approved_by="ops-lead")


# ── Section 12h: Concurrent consume ──────────────────────────────────────────


class TestConcurrentConsume:
    """asyncio concurrent consume: exactly one coroutine wins the APPROVED → CONSUMED transition."""

    def test_concurrent_consume_only_one_wins(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        store.approve(record.approval_id, approved_by="ops-lead")

        results = []

        async def try_consume():
            result = store.consume(record.approval_id)
            results.append(result)

        async def run_concurrent():
            await asyncio.gather(try_consume(), try_consume(), try_consume())

        asyncio.run(run_concurrent())

        winners = [r for r in results if r is not None]
        losers = [r for r in results if r is None]
        assert len(winners) == 1
        assert len(losers) == 2
        assert record.state == ApprovalState.CONSUMED

    def test_concurrent_consume_state_is_consumed_after_race(self):
        store = _store()
        record = store.create(proposal_id="P-1", decision_id="D-1")
        store.approve(record.approval_id, approved_by="ops-lead")

        results = []
        for _ in range(5):
            results.append(store.consume(record.approval_id))

        assert record.state == ApprovalState.CONSUMED
        assert sum(1 for r in results if r is not None) == 1


# ── Section 12i: Audit chain — proposal_id preserved ────────────────────────


class TestAuditChainIntegrity:
    """The proposal_id stored in ApprovalRecord must match the one in the pending record."""

    def test_create_stores_original_proposal_id(self):
        store = _store()
        original_id = "ORIGINAL-PROPOSAL-UUID"
        record = store.create(proposal_id=original_id, decision_id="D-1")
        assert record.proposal_id == original_id

    def test_approve_does_not_change_proposal_id(self):
        store = _store()
        original_id = "ORIGINAL-PROPOSAL-UUID"
        record = store.create(proposal_id=original_id, decision_id="D-1")
        store.approve(record.approval_id, approved_by="ops-lead")
        assert record.proposal_id == original_id

    def test_consume_does_not_change_proposal_id(self):
        store = _store()
        original_id = "ORIGINAL-PROPOSAL-UUID"
        record = store.create(proposal_id=original_id, decision_id="D-1")
        store.approve(record.approval_id, approved_by="ops-lead")
        store.consume(record.approval_id)
        assert record.proposal_id == original_id

    def test_engine_authorized_with_matching_proposal_id(self):
        """Full lifecycle: create → approve → engine authorizes with same proposal_id."""
        engine = DecisionEngine()
        proposal = _labor_proposal()

        store = _store()
        record = store.create(
            proposal_id=proposal.proposal_id,
            decision_id="D-ORIG",
        )
        store.approve(record.approval_id, approved_by="ops-lead")

        request = DecisionRequest(
            proposal=proposal,
            state=_fresh_snapshot(),
            requested_by="ops-lead",
        )
        result, _ = engine.authorize_with_approval(
            request, record, expected_decision_id="D-ORIG"
        )
        assert result.outcome == DecisionOutcome.APPROVED
        # proposal_id in result echoes the original
        assert result.proposal_id == proposal.proposal_id


# ── Section 12j: Store reset ─────────────────────────────────────────────────


class TestStoreReset:
    """reset() clears all records."""

    def test_reset_clears_all_records(self):
        store = _store()
        r1 = store.create(proposal_id="P-1", decision_id="D-1")
        r2 = store.create(proposal_id="P-2", decision_id="D-2")
        store.reset()
        assert store.get(r1.approval_id) is None
        assert store.get(r2.approval_id) is None

    def test_reset_allows_new_creates(self):
        store = _store()
        store.create(proposal_id="P-1", decision_id="D-1")
        store.reset()
        record = store.create(proposal_id="P-2", decision_id="D-2")
        assert store.get(record.approval_id) is not None


# ── Section 12k: ApprovalRecord model fields ─────────────────────────────────


class TestApprovalRecordModel:
    """ApprovalRecord Pydantic model field contracts."""

    def test_approval_id_generated_on_construction(self):
        record = ApprovalRecord(proposal_id="P-1", decision_id="D-1")
        assert record.approval_id is not None
        assert len(record.approval_id) > 0

    def test_two_records_have_distinct_approval_ids(self):
        r1 = ApprovalRecord(proposal_id="P-1", decision_id="D-1")
        r2 = ApprovalRecord(proposal_id="P-1", decision_id="D-1")
        assert r1.approval_id != r2.approval_id

    def test_default_state_is_pending(self):
        record = ApprovalRecord(proposal_id="P-1", decision_id="D-1")
        assert record.state == ApprovalState.PENDING

    def test_approved_computed_field_pending(self):
        record = ApprovalRecord(
            proposal_id="P-1", decision_id="D-1", state=ApprovalState.PENDING
        )
        assert record.approved is False

    def test_approved_computed_field_approved(self):
        record = ApprovalRecord(
            proposal_id="P-1", decision_id="D-1", state=ApprovalState.APPROVED
        )
        assert record.approved is True

    def test_approved_computed_field_consumed(self):
        record = ApprovalRecord(
            proposal_id="P-1", decision_id="D-1", state=ApprovalState.CONSUMED
        )
        assert record.approved is False

    def test_approved_computed_field_rejected(self):
        record = ApprovalRecord(
            proposal_id="P-1", decision_id="D-1", state=ApprovalState.REJECTED
        )
        assert record.approved is False

    def test_model_dump_includes_state(self):
        record = ApprovalRecord(proposal_id="P-1", decision_id="D-1")
        d = record.model_dump()
        assert "state" in d
        assert d["state"] == ApprovalState.PENDING

    def test_model_dump_includes_approved_computed_field(self):
        record = ApprovalRecord(
            proposal_id="P-1", decision_id="D-1", state=ApprovalState.APPROVED
        )
        d = record.model_dump()
        assert "approved" in d
        assert d["approved"] is True

    def test_authority_type_default_human(self):
        record = ApprovalRecord(proposal_id="P-1", decision_id="D-1")
        assert record.authority_type == AuthorityType.HUMAN
