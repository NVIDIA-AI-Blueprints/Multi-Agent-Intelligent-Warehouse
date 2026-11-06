# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
A maintenance slot that has passed is never executed (#259).

A schedule_maintenance proposal with no explicit time gets ``scheduled_for =
now + 1 day``, fixed when the proposal is built, and always waits for a human.
An approval that arrived after the slot had passed executed it anyway, with a
``scheduled_for`` in the past. Now ``DecisionEngine(clock=...)`` rejects such a
proposal (rule ``maintenance.scheduled_for_past``) at evaluation and again in
``authorize_with_approval``; approval evidence cannot override it. Without a
clock (the default) no time-bound check runs, so existing callers are
unchanged. Slot-builder dedupe: both builders use
``maiw_api.demo.scheduling.default_scheduled_for``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from maiw_decision import DecisionEngine, DecisionOutcome, DecisionRequest
from maiw_decision.approval import InMemoryApprovalStore
from maiw_decision.proposal import ActionProposal
from maiw_state import (
    EquipmentAssetSummary,
    EquipmentState,
    StateFreshness,
    WarehouseState,
    WarehouseStateSnapshot,
)

_NOW = datetime(2026, 8, 24, 9, 30, tzinfo=timezone.utc)


class _Clock:
    """A settable clock, like the demo's SimulationClock."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _snapshot() -> WarehouseStateSnapshot:
    equipment = EquipmentState(
        warehouse_id="DC-47",
        assets=[
            EquipmentAssetSummary(
                asset_id="FL-01",
                equipment_type="forklift",
                model="TestLift",
                zone="A1",
                status="available",
            )
        ],
        total_count=1,
        freshness=StateFreshness.now(),
    )
    state = WarehouseState(
        warehouse_id="DC-47",
        observed_at=datetime.now(timezone.utc),
        equipment=equipment,
    )
    return WarehouseStateSnapshot.seal(state)


def _maintenance(scheduled_for) -> ActionProposal:
    return ActionProposal.for_schedule_maintenance(
        asset_id="FL-01",
        maintenance_type="preventive",
        description="Hydraulic check",
        scheduled_by="operations-agent",
        scheduled_for=scheduled_for,
        warehouse_id="DC-47",
    )


def _evaluate(engine: DecisionEngine, proposal: ActionProposal):
    result, _ = engine.evaluate(DecisionRequest(proposal=proposal, state=_snapshot()))
    return result


def _rules(result) -> list[str]:
    return [v.rule for v in result.violations]


# ── evaluate() ─────────────────────────────────────────────────────────────────


class TestEvaluate:
    @pytest.mark.parametrize(
        "slot",
        [
            (_NOW + timedelta(days=1)).isoformat(),
            _NOW.isoformat(),  # "now" is not in the past
            "2026-08-25T09:00:00Z",
            "2026-08-25T09:00:00",  # naive: read as UTC
            "2026-08-25 09:00:00",
        ],
    )
    def test_future_slot_goes_to_human_approval(self, slot):
        result = _evaluate(DecisionEngine(clock=_Clock(_NOW)), _maintenance(slot))
        assert result.outcome == DecisionOutcome.REQUIRES_HUMAN_APPROVAL
        assert _rules(result) == ["approval.required"]

    @pytest.mark.parametrize(
        "slot",
        [
            (_NOW - timedelta(seconds=1)).isoformat(),
            "2026-08-24T09:29:59Z",
            "2026-08-24T09:29:59",  # naive: read as UTC
            "2026-08-24T11:29:59+02:00",  # 09:29:59Z
        ],
    )
    def test_past_slot_is_rejected(self, slot):
        result = _evaluate(DecisionEngine(clock=_Clock(_NOW)), _maintenance(slot))
        assert result.outcome == DecisionOutcome.REJECTED
        assert _rules(result) == ["maintenance.scheduled_for_past"]
        details = result.violations[0].details
        assert datetime.fromisoformat(details["now"]) == _NOW

    @pytest.mark.parametrize("slot", ["", "tomorrow", "None", None])
    def test_unparseable_slot_is_rejected(self, slot):
        result = _evaluate(DecisionEngine(clock=_Clock(_NOW)), _maintenance(slot))
        assert result.outcome == DecisionOutcome.REJECTED
        assert _rules(result) == ["maintenance.scheduled_for_invalid"]

    def test_naive_clock_is_read_as_utc(self):
        engine = DecisionEngine(clock=lambda: _NOW.replace(tzinfo=None))
        past = _evaluate(engine, _maintenance("2026-08-24T09:00:00Z"))
        assert past.outcome == DecisionOutcome.REJECTED

    @pytest.mark.parametrize("slot", ["2020-01-01T00:00:00Z", "tomorrow"])
    def test_without_a_clock_nothing_changes(self, slot):
        result = _evaluate(DecisionEngine(), _maintenance(slot))
        assert result.outcome == DecisionOutcome.REQUIRES_HUMAN_APPROVAL

    def test_other_equipment_actions_are_not_time_checked(self):
        proposal = ActionProposal.for_equipment_assign(
            asset_id="FL-01",
            assignee="op-1",
            assignment_type="task",
            task_id=None,
            duration_hours=None,
            notes=None,
            reason="test",
            requested_by="test",
            warehouse_id="DC-47",
        )
        result = _evaluate(DecisionEngine(clock=_Clock(_NOW)), proposal)
        assert result.outcome != DecisionOutcome.REJECTED

    def test_engine_version_records_the_new_rule(self):
        engine = DecisionEngine(clock=_Clock(_NOW))
        assert engine.version == "1.1.0"
        assert _evaluate(engine, _maintenance("x")).engine_version == "1.1.0"


# ── authorize_with_approval(): the late-approval path ─────────────────────────


def _approved(proposal: ActionProposal, decision_id: str):
    store = InMemoryApprovalStore()
    record = store.create(
        proposal_id=proposal.proposal_id,
        decision_id=decision_id,
        warehouse_id="DC-47",
    )
    return store.approve(record.approval_id, approved_by="operator")


class TestAuthorizeWithApproval:
    def _propose(self, clock: _Clock):
        engine = DecisionEngine(clock=clock)
        proposal = _maintenance((clock() + timedelta(days=1)).isoformat())
        decision = _evaluate(engine, proposal)
        assert decision.outcome == DecisionOutcome.REQUIRES_HUMAN_APPROVAL
        return engine, proposal, _approved(proposal, decision.result_id), decision

    def _authorize(self, engine, proposal, approval, decision):
        result, _ = engine.authorize_with_approval(
            DecisionRequest(proposal=proposal, state=_snapshot()),
            approval,
            expected_decision_id=decision.result_id,
        )
        return result

    def test_on_time_approval_is_authorized(self):
        clock = _Clock(_NOW)
        engine, proposal, approval, decision = self._propose(clock)
        clock.now = _NOW + timedelta(hours=23)

        result = self._authorize(engine, proposal, approval, decision)

        assert result.outcome == DecisionOutcome.APPROVED

    def test_approval_after_the_slot_passed_is_rejected(self):
        clock = _Clock(_NOW)
        engine, proposal, approval, decision = self._propose(clock)
        clock.now = _NOW + timedelta(days=2)

        result = self._authorize(engine, proposal, approval, decision)

        assert result.outcome == DecisionOutcome.REJECTED
        assert _rules(result) == ["maintenance.scheduled_for_past"]
        # The proposal still carries the slot the human approved; nothing
        # moved it.
        assert (
            proposal.parameters["scheduled_for"]
            == (_NOW + timedelta(days=1)).isoformat()
        )


# ── The two slot builders share one helper ────────────────────────────────────


def test_both_builders_use_the_shared_slot_helper():
    from maiw_api.copilot import orchestrator
    from maiw_api.demo.scheduling import default_scheduled_for
    from maiw_api.routers import demo

    assert orchestrator._default_scheduled_for is default_scheduled_for
    assert demo._default_scheduled_for is default_scheduled_for
