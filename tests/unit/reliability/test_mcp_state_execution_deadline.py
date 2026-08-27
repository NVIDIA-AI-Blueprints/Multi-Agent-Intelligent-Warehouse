# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Checkpoint C — deadline propagation through MCP, WarehouseState, and ActionExecutor.

Test groups
-----------
    TestMAIWMCPClientDeadline         (5 tests)  — invoke() deadline guard + effective timeout
    TestWarehouseStateProviderDeadline (9 tests)  — shared deadline, expired-before-read,
                                                    skill timeout → RequestDeadlineExceeded
    TestBaseActionExecutorDeadline     (7 tests)  — Guard 6, NoOpActionExecutor, no-deadline compat

All tests are synchronous (asyncio.new_event_loop() where async needed).
FakeClock allows deterministic control of deadline.expired without real sleeps.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maiw_mcp.deadline import RequestDeadline, RequestDeadlineExceeded
from maiw_mcp.errors import MCPTimeout, MCPUnavailable

# ---------------------------------------------------------------------------
# FakeClock — reused from Checkpoint A/B conventions
# ---------------------------------------------------------------------------


class FakeClock:
    def __init__(self, now: float = 1000.0) -> None:
        self._now = now

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# MAIWMCPClient deadline tests
# ---------------------------------------------------------------------------


class TestMAIWMCPClientDeadline:
    """invoke() rejects before any network call when deadline is expired."""

    def _make_client(self):
        from maiw_mcp.client.client import MAIWMCPClient
        from maiw_mcp.registry.registry import CapabilityRegistry

        registry = MagicMock(spec=CapabilityRegistry)
        registry.resolve.return_value = "http://mcp-server:8080"
        return MAIWMCPClient(registry=registry)

    def test_expired_deadline_raises_before_network_call(self):
        clock = FakeClock(1000.0)
        deadline = RequestDeadline.from_timeout(5.0, clock=clock)
        clock.advance(10.0)  # now expired by 5s

        client = self._make_client()

        async def run():
            return await client.invoke("warehouse.inventory.get", {}, deadline=deadline)

        with pytest.raises(RequestDeadlineExceeded) as exc_info:
            _run(run())
        assert exc_info.value.expired_by_ms > 0
        # Registry.resolve should never be called — the guard fires first
        client._registry.resolve.assert_not_called()

    def test_valid_deadline_uses_effective_timeout(self):
        """When deadline has 8s remaining and local timeout is 30s, effective = 8s."""
        clock = FakeClock(1000.0)
        deadline = RequestDeadline.from_timeout(8.0, clock=clock)
        # 2s elapsed; 6s remaining
        clock.advance(2.0)

        client = self._make_client()

        captured_timeouts = []

        async def fake_call_tool(cap, payload, server_url, timeout_seconds):
            captured_timeouts.append(timeout_seconds)
            return {"status": "ok"}

        async def run():
            with patch.object(client, "_call_tool", side_effect=fake_call_tool):
                return await client.invoke(
                    "warehouse.inventory.get",
                    {},
                    timeout_seconds=30.0,
                    deadline=deadline,
                )

        _run(run())
        assert len(captured_timeouts) == 1
        # effective = min(30, 6) = 6s (approximately)
        assert captured_timeouts[0] <= 6.5
        assert captured_timeouts[0] >= 5.0

    def test_unlimited_deadline_uses_local_timeout(self):
        """Unlimited deadline passes local timeout unchanged."""
        clock = FakeClock(1000.0)
        deadline = RequestDeadline.unlimited(clock=clock)
        client = self._make_client()

        captured_timeouts = []

        async def fake_call_tool(cap, payload, server_url, timeout_seconds):
            captured_timeouts.append(timeout_seconds)
            return {"status": "ok"}

        async def run():
            with patch.object(client, "_call_tool", side_effect=fake_call_tool):
                return await client.invoke(
                    "warehouse.inventory.get",
                    {},
                    timeout_seconds=15.0,
                    deadline=deadline,
                )

        _run(run())
        assert captured_timeouts[0] == 15.0

    def test_no_deadline_uses_local_timeout(self):
        """No deadline → fallback to timeout_seconds exactly."""
        client = self._make_client()
        captured_timeouts = []

        async def fake_call_tool(cap, payload, server_url, timeout_seconds):
            captured_timeouts.append(timeout_seconds)
            return {"status": "ok"}

        async def run():
            with patch.object(client, "_call_tool", side_effect=fake_call_tool):
                return await client.invoke(
                    "warehouse.inventory.get", {}, timeout_seconds=25.0
                )

        _run(run())
        assert captured_timeouts[0] == 25.0

    def test_deadline_exceeded_not_wrapped_as_mcp_unavailable(self):
        """RequestDeadlineExceeded from inside _call_tool must not be wrapped as MCPUnavailable."""
        clock = FakeClock(1000.0)
        # deadline with 30s, but we'll make call_tool raise RequestDeadlineExceeded
        deadline = RequestDeadline.from_timeout(30.0, clock=clock)
        client = self._make_client()

        async def fake_call_tool(cap, payload, server_url, timeout_seconds):
            raise RequestDeadlineExceeded(expired_by_ms=50.0)

        async def run():
            with patch.object(client, "_call_tool", side_effect=fake_call_tool):
                return await client.invoke(
                    "warehouse.inventory.get", {}, deadline=deadline
                )

        with pytest.raises(RequestDeadlineExceeded):
            _run(run())


# ---------------------------------------------------------------------------
# WarehouseStateProvider deadline tests
# ---------------------------------------------------------------------------


class _MockResult:
    """Minimal duck-type mock for skill result objects."""

    total_count = 0
    summary = {}
    equipment = []
    items = []
    workers = []
    waves = []
    allocated = 0
    available = 0
    zones = {}
    status = "ok"


def _make_equipment_skill(result=None, side_effect=None):
    skill = MagicMock()
    if side_effect is not None:
        skill.execute = AsyncMock(side_effect=side_effect)
    else:
        r = result or _MockResult()
        skill.execute = AsyncMock(return_value=r)
    return skill


def _make_inventory_skill(result=None, side_effect=None):
    skill = MagicMock()
    if side_effect is not None:
        skill.execute = AsyncMock(side_effect=side_effect)
    else:
        r = result or _MockResult()
        skill.execute = AsyncMock(return_value=r)
    return skill


def _make_labor_skill(result=None, side_effect=None):
    skill = MagicMock()
    if side_effect is not None:
        skill.execute = AsyncMock(side_effect=side_effect)
    else:
        r = result or _MockResult()
        skill.execute = AsyncMock(return_value=r)
    return skill


def _make_wave_skill(result=None, side_effect=None):
    skill = MagicMock()
    if side_effect is not None:
        skill.execute = AsyncMock(side_effect=side_effect)
    else:
        r = result or _MockResult()
        skill.execute = AsyncMock(return_value=r)
    return skill


class TestWarehouseStateProviderDeadline:

    def _make_provider(
        self,
        equipment_skill=None,
        inventory_skill=None,
        labor_skill=None,
        wave_skill=None,
    ):
        from maiw_state import WarehouseStateProvider

        return WarehouseStateProvider(
            equipment_status_skill=equipment_skill,
            inventory_skill=inventory_skill,
            labor_capacity_skill=labor_skill,
            wave_get_skill=wave_skill,
        )

    def _make_reqs(self, *, inventory=False, equipment=False, labor=False, waves=False):
        from maiw_state import StateRequirements

        return StateRequirements(
            inventory=inventory,
            inventory_sku="SKU-001" if inventory else None,
            equipment=equipment,
            labor=labor,
            waves=waves,
        )

    def test_no_deadline_equipment_succeeds(self):
        """Baseline: no deadline, equipment domain read works."""
        from maiw_state import WarehouseStateProvider, StateRequirements
        from maiw_mcp.contracts.equipment import EquipmentStatusResult

        mock_result = MagicMock(spec=EquipmentStatusResult)
        mock_result.total_count = 0
        mock_result.summary = {}
        mock_result.equipment = []
        skill = _make_equipment_skill(result=mock_result)
        provider = self._make_provider(equipment_skill=skill)
        reqs = self._make_reqs(equipment=True)

        state = _run(provider.get_state("wh-1", reqs))
        assert skill.execute.call_count == 1
        assert state.warehouse_id == "wh-1"

    def test_expired_deadline_before_inventory_read(self):
        """Expired deadline before first read → RequestDeadlineExceeded; skill never called."""
        from maiw_state import StateRequirements

        clock = FakeClock(1000.0)
        deadline = RequestDeadline.from_timeout(5.0, clock=clock)
        clock.advance(10.0)  # expired by 5s

        skill = _make_inventory_skill()
        provider = self._make_provider(inventory_skill=skill)
        reqs = self._make_reqs(inventory=True)

        with pytest.raises(RequestDeadlineExceeded):
            _run(provider.get_state("wh-1", reqs, deadline=deadline))

        skill.execute.assert_not_called()

    def test_expired_deadline_before_equipment_read(self):
        """Expired deadline before equipment read → RequestDeadlineExceeded."""
        clock = FakeClock(1000.0)
        deadline = RequestDeadline.from_timeout(5.0, clock=clock)
        clock.advance(10.0)  # expired

        from maiw_mcp.contracts.equipment import EquipmentStatusResult

        mock_result = MagicMock(spec=EquipmentStatusResult)
        mock_result.total_count = 0
        mock_result.summary = {}
        mock_result.equipment = []
        skill = _make_equipment_skill(result=mock_result)
        provider = self._make_provider(equipment_skill=skill)
        reqs = self._make_reqs(equipment=True)

        with pytest.raises(RequestDeadlineExceeded):
            _run(provider.get_state("wh-1", reqs, deadline=deadline))

        skill.execute.assert_not_called()

    def test_deadline_expires_between_domain_reads(self):
        """Deadline expires after inventory completes but before equipment check."""
        clock = FakeClock(1000.0)
        # 6 second budget; inventory takes 4s (advances clock) → 2s left → equipment check: expired
        deadline = RequestDeadline.from_timeout(6.0, clock=clock)

        from maiw_mcp.contracts.equipment import EquipmentStatusResult

        inv_result = MagicMock()
        inv_result.sku = "SKU-001"
        inv_result.name = "Widget"
        inv_result.total_available = 10
        inv_result.is_low_stock = False
        inv_result.locations = []

        eq_result = MagicMock(spec=EquipmentStatusResult)
        eq_result.total_count = 0
        eq_result.summary = {}
        eq_result.equipment = []

        async def slow_inventory(*args, **kwargs):
            clock.advance(7.0)  # consume 7s > 6s budget → deadline expired
            return inv_result

        inv_skill = MagicMock()
        inv_skill.execute = AsyncMock(side_effect=slow_inventory)
        eq_skill = _make_equipment_skill(result=eq_result)

        provider = self._make_provider(
            inventory_skill=inv_skill, equipment_skill=eq_skill
        )
        reqs = self._make_reqs(inventory=True, equipment=True)

        with pytest.raises(RequestDeadlineExceeded):
            _run(provider.get_state("wh-1", reqs, deadline=deadline))

        # Inventory was called; equipment never reached
        inv_skill.execute.assert_called_once()
        eq_skill.execute.assert_not_called()

    def test_shared_deadline_not_reset_between_reads(self):
        """All domain reads share the SAME deadline object — not reset between them."""
        clock = FakeClock(1000.0)
        deadline = RequestDeadline.from_timeout(30.0, clock=clock)

        from maiw_mcp.contracts.equipment import EquipmentStatusResult

        inv_result = MagicMock()
        inv_result.sku = "SKU-001"
        inv_result.name = "Widget"
        inv_result.total_available = 5
        inv_result.is_low_stock = False
        inv_result.locations = []

        eq_result = MagicMock(spec=EquipmentStatusResult)
        eq_result.total_count = 0
        eq_result.summary = {}
        eq_result.equipment = []

        remaining_at_inventory: list[float] = []
        remaining_at_equipment: list[float] = []

        async def record_inv(*args, **kwargs):
            clock.advance(5.0)
            remaining_at_inventory.append(deadline.remaining_seconds)
            return inv_result

        async def record_eq(*args, **kwargs):
            remaining_at_equipment.append(deadline.remaining_seconds)
            return eq_result

        inv_skill = MagicMock()
        inv_skill.execute = AsyncMock(side_effect=record_inv)
        eq_skill = MagicMock()
        eq_skill.execute = AsyncMock(side_effect=record_eq)

        provider = self._make_provider(
            inventory_skill=inv_skill, equipment_skill=eq_skill
        )
        reqs = self._make_reqs(inventory=True, equipment=True)

        _run(provider.get_state("wh-1", reqs, deadline=deadline))

        # After inventory consumed 5s, equipment sees ~25s remaining (shared deadline)
        # If deadline had been reset, equipment would see ~30s — which would be wrong
        assert remaining_at_equipment[0] < remaining_at_inventory[0] + 0.1
        # Specifically: equipment sees less time than initial budget
        assert remaining_at_equipment[0] < 30.0

    def test_skill_asyncio_timeout_raises_deadline_exceeded(self):
        """asyncio.wait_for timeout from a hanging skill → RequestDeadlineExceeded (not StateAssemblyError)."""
        clock = FakeClock(1000.0)
        # deadline has 0.01s remaining — tight enough to trigger wait_for timeout
        deadline = RequestDeadline.from_timeout(30.0, clock=clock)
        # advance to leave only a tiny slice
        clock.advance(29.999)

        from maiw_mcp.contracts.equipment import EquipmentStatusResult

        async def hanging_skill(*args, **kwargs):
            await asyncio.sleep(10.0)  # will be cancelled by wait_for
            return MagicMock(spec=EquipmentStatusResult)

        skill = MagicMock()
        skill.execute = AsyncMock(side_effect=hanging_skill)

        provider = self._make_provider(equipment_skill=skill)
        reqs = self._make_reqs(equipment=True)

        with pytest.raises(RequestDeadlineExceeded):
            _run(provider.get_state("wh-1", reqs, deadline=deadline))

    def test_non_deadline_skill_exception_wraps_as_state_assembly_error(self):
        """A skill raising a regular exception wraps as StateAssemblyError (no deadline in play)."""
        from maiw_state import StateAssemblyError

        skill = MagicMock()
        skill.execute = AsyncMock(side_effect=RuntimeError("mcp connection refused"))

        provider = self._make_provider(equipment_skill=skill)
        reqs = self._make_reqs(equipment=True)

        with pytest.raises(StateAssemblyError) as exc_info:
            _run(provider.get_state("wh-1", reqs))

        assert "equipment" in exc_info.value.domain

    def test_deadline_not_expired_skill_succeeds(self):
        """Valid unexpired deadline: skill executes normally and state is returned."""
        clock = FakeClock(1000.0)
        deadline = RequestDeadline.from_timeout(10.0, clock=clock)

        from maiw_mcp.contracts.equipment import EquipmentStatusResult

        eq_result = MagicMock(spec=EquipmentStatusResult)
        eq_result.total_count = 1
        eq_result.summary = {}
        eq_result.equipment = []

        skill = _make_equipment_skill(result=eq_result)
        provider = self._make_provider(equipment_skill=skill)
        reqs = self._make_reqs(equipment=True)

        state = _run(provider.get_state("wh-1", reqs, deadline=deadline))
        assert state.warehouse_id == "wh-1"
        skill.execute.assert_called_once()

    def test_unlimited_deadline_passes_through(self):
        """Unlimited deadline: no expiry check fires, skill runs normally."""
        clock = FakeClock(1000.0)
        deadline = RequestDeadline.unlimited(clock=clock)

        from maiw_mcp.contracts.equipment import EquipmentStatusResult

        eq_result = MagicMock(spec=EquipmentStatusResult)
        eq_result.total_count = 0
        eq_result.summary = {}
        eq_result.equipment = []

        skill = _make_equipment_skill(result=eq_result)
        provider = self._make_provider(equipment_skill=skill)
        reqs = self._make_reqs(equipment=True)

        state = _run(provider.get_state("wh-1", reqs, deadline=deadline))
        assert state.warehouse_id == "wh-1"
        skill.execute.assert_called_once()


# ---------------------------------------------------------------------------
# BaseActionExecutor deadline tests
# ---------------------------------------------------------------------------


def _make_proposal(action: str = "test.action") -> "ActionProposal":
    from maiw_mcp.contracts.actions import ActionProposal, RiskLevel

    return ActionProposal(
        action=action,
        domain="test",
        parameters={"warehouse_id": "wh-1"},
        risk_level=RiskLevel.LOW,
        reason="unit test",
    )


def _approved_decision(proposal_id: str, age_seconds: float = 0.0) -> "DecisionResult":
    from maiw_decision.models import DecisionOutcome, DecisionResult

    evaluated_at = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    return DecisionResult(
        request_id="req-1",
        proposal_id=proposal_id,
        outcome=DecisionOutcome.APPROVED,
        evaluated_at=evaluated_at,
    )


class _StubExecutor:
    """Minimal concrete executor for Guard 6 testing."""

    _ALLOWED_ACTIONS = frozenset(["test.action"])

    def __init__(self, *, max_decision_age_seconds: int = 300, registry=None) -> None:
        from maiw_execution.base import BaseActionExecutor

        # Build via BaseActionExecutor
        self._base = _BaseExecutorSubclass(
            max_decision_age_seconds=max_decision_age_seconds,
            registry=registry,
        )

    async def execute(self, proposal, decision, *, trace_id=None, deadline=None):
        return await self._base.execute(
            proposal, decision, trace_id=trace_id, deadline=deadline
        )

    @property
    def write_called(self):
        return self._base.write_called


from maiw_execution.base import BaseActionExecutor
from maiw_execution.outcome import ExecutionOutcome


class _BaseExecutorSubclass(BaseActionExecutor):
    _ALLOWED_ACTIONS = frozenset(["test.action"])

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.write_called = False

    async def _do_execute(self, proposal, decision, execution_id):
        self.write_called = True
        return {"ok": True}, "ref-001", ExecutionOutcome.EXECUTED


class TestBaseActionExecutorDeadline:

    def _make_executor(self, **kwargs) -> _BaseExecutorSubclass:
        return _BaseExecutorSubclass(**kwargs)

    def test_guard6_fires_when_deadline_expired_before_write(self):
        """Guard 6: expired deadline raises RequestDeadlineExceeded; _do_execute never called."""
        clock = FakeClock(1000.0)
        deadline = RequestDeadline.from_timeout(5.0, clock=clock)
        clock.advance(10.0)  # expired

        executor = self._make_executor()
        proposal = _make_proposal()
        decision = _approved_decision(proposal.proposal_id)

        with pytest.raises(RequestDeadlineExceeded):
            _run(executor.execute(proposal, decision, deadline=deadline))

        assert executor.write_called is False

    def test_guard6_does_not_fire_when_deadline_valid(self):
        """Guard 6: valid unexpired deadline passes; _do_execute is called."""
        clock = FakeClock(1000.0)
        deadline = RequestDeadline.from_timeout(30.0, clock=clock)

        executor = self._make_executor()
        proposal = _make_proposal()
        decision = _approved_decision(proposal.proposal_id)

        result = _run(executor.execute(proposal, decision, deadline=deadline))
        assert result.outcome == ExecutionOutcome.EXECUTED
        assert executor.write_called is True

    def test_guard6_no_deadline_no_effect(self):
        """No deadline → Guard 6 is skipped; write proceeds normally."""
        executor = self._make_executor()
        proposal = _make_proposal()
        decision = _approved_decision(proposal.proposal_id)

        result = _run(executor.execute(proposal, decision))
        assert result.outcome == ExecutionOutcome.EXECUTED
        assert executor.write_called is True

    def test_guard6_fires_after_guard5_not_before(self):
        """Guard 6 (deadline) fires after Guard 5 (additional guards), not before."""
        clock = FakeClock(1000.0)
        deadline = RequestDeadline.from_timeout(5.0, clock=clock)
        clock.advance(10.0)  # deadline expired

        # Guard 3 fires first for unsupported action — should take precedence over guard 6
        from maiw_execution.base import ActionUnsupported

        executor = self._make_executor()
        proposal = _make_proposal(action="unsupported.action")
        decision = _approved_decision(proposal.proposal_id)
        # Adjust proposal_id to match decision
        decision = _approved_decision(proposal.proposal_id)

        with pytest.raises(ActionUnsupported):
            _run(executor.execute(proposal, decision, deadline=deadline))

        assert executor.write_called is False

    def test_guard1_fires_before_guard6(self):
        """Non-APPROVED decision raises ActionNotApproved before Guard 6 checks deadline."""
        from maiw_decision.models import DecisionOutcome, DecisionResult
        from maiw_execution.base import ActionNotApproved

        clock = FakeClock(1000.0)
        deadline = RequestDeadline.from_timeout(5.0, clock=clock)
        clock.advance(10.0)  # deadline expired

        executor = self._make_executor()
        proposal = _make_proposal()
        rejected = DecisionResult(
            request_id="req-1",
            proposal_id=proposal.proposal_id,
            outcome=DecisionOutcome.REQUIRES_HUMAN_APPROVAL,
        )

        with pytest.raises(ActionNotApproved):
            _run(executor.execute(proposal, rejected, deadline=deadline))

    def test_noopexecutor_deadline_expired_raises(self):
        """NoOpActionExecutor: expired deadline raises RequestDeadlineExceeded before approval check."""
        from maiw_execution.base import NoOpActionExecutor

        clock = FakeClock(1000.0)
        deadline = RequestDeadline.from_timeout(5.0, clock=clock)
        clock.advance(10.0)  # expired

        executor = NoOpActionExecutor()
        proposal = _make_proposal()
        decision = _approved_decision(proposal.proposal_id)

        with pytest.raises(RequestDeadlineExceeded):
            _run(executor.execute(proposal, decision, deadline=deadline))

    def test_unlimited_deadline_does_not_block_write(self):
        """Unlimited deadline: guard 6 never fires; write proceeds."""
        clock = FakeClock(1000.0)
        deadline = RequestDeadline.unlimited(clock=clock)
        clock.advance(9999.0)  # massive time advance — should not matter for unlimited

        executor = self._make_executor()
        proposal = _make_proposal()
        decision = _approved_decision(proposal.proposal_id)

        result = _run(executor.execute(proposal, decision, deadline=deadline))
        assert result.outcome == ExecutionOutcome.EXECUTED
        assert executor.write_called is True
