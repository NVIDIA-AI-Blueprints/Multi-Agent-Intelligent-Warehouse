# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
schedule_maintenance proposals carry the required ``scheduled_for`` (#219).

``ActionProposal.for_schedule_maintenance()`` takes ``scheduled_for`` as a
required keyword-only argument. Both proposal builders — the copilot
GovernedActionOrchestrator and the demo analyze route — must supply it, or
every ``warehouse.equipment.schedule_maintenance`` recommendation fails with a
TypeError before it reaches the DecisionEngine.

Demo mode runs on the world's SimulationClock (not wall time), so the default
slot is the simulated "now" + 1 day; without a simulation clock it falls back
to UTC wall time. The produced string must also be accepted downstream: the
equipment executor builds an ``EquipmentExecuteMaintenanceRequest`` from it and
the demo provider parses it into the asset's ``next_pm_due``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from maiw_api.copilot.models import GovernedActionRequest
from maiw_api.copilot.orchestrator import GovernedActionOrchestrator
from maiw_api.demo.events import ScenarioEventBus
from maiw_api.demo.providers.equipment import SimulationEquipmentProvider
from maiw_api.demo.world import DemoWarehouseWorld, SimulationClock
from maiw_api.routers import demo as demo_mod
from maiw_decision.models import DecisionOutcome, DecisionResult
from maiw_execution import EquipmentActionExecutor

_CAP = "warehouse.equipment.schedule_maintenance"
_SIM_OFFSET_SECONDS = 5 * 3600 + 17 * 60  # 13:17Z on the simulated shift day
_SIM_NOW = datetime(2026, 8, 23, 8, 0, tzinfo=timezone.utc) + timedelta(
    seconds=_SIM_OFFSET_SECONDS
)


def _world() -> DemoWarehouseWorld:
    world = DemoWarehouseWorld()
    world.seed(
        {
            "clock_offset_seconds": _SIM_OFFSET_SECONDS,
            "equipment": [
                {
                    "asset_id": "FL-01",
                    "equipment_type": "forklift",
                    "model": "TestLift",
                    "zone": "A1",
                    "status": "available",
                    "battery_pct": 80.0,
                }
            ],
        }
    )
    return world


def _copilot_request() -> GovernedActionRequest:
    return GovernedActionRequest(
        recommendation_id="r1",
        capability=_CAP,
        target="FL-01",
        domain="equipment",
        objective="Inspect forklift FL-01",
        rationale="Hydraulic fault.",
        priority="medium",
        subtype=None,
        conversation_id="conv-1",
        turn_id="turn-1",
        trace_id="trace-1",
        source_turn_id="src-turn",
        source_trace_id="src-trace",
        source_snapshot_id="snap-001",
        current_snapshot_id="snap-002",
        focus_entity_id="FL-01",
    )


def _demo_rec() -> SimpleNamespace:
    return SimpleNamespace(
        capability=_CAP,
        target="FL-01",
        subtype=None,
        objective="Inspect forklift FL-01",
        priority="medium",
        rationale="Hydraulic fault.",
    )


def _assert_proposal(proposal, *, warehouse_id: str) -> datetime:
    assert proposal.action == _CAP
    assert proposal.parameters["asset_id"] == "FL-01"
    assert proposal.parameters["warehouse_id"] == warehouse_id
    # An ISO-8601 datetime with a timezone (the demo provider and the MCP
    # adapter both parse it with datetime.fromisoformat).
    scheduled_for = datetime.fromisoformat(proposal.parameters["scheduled_for"])
    assert scheduled_for.tzinfo is not None
    return scheduled_for


def _assert_next_day_wall_clock(scheduled_for: datetime) -> None:
    now = datetime.now(timezone.utc)
    assert now < scheduled_for <= now + timedelta(days=2)


# ── Demo analyze route ─────────────────────────────────────────────────────────


async def test_demo_route_scheduled_for_is_sim_clock_plus_one_day():
    ctrl = SimpleNamespace(world=_world())

    proposal = await demo_mod._build_proposal(
        _demo_rec(), "trace-1", None, warehouse_id="DC-47", ctrl=ctrl
    )

    scheduled_for = _assert_proposal(proposal, warehouse_id="DC-47")
    assert scheduled_for == _SIM_NOW + timedelta(days=1)
    assert proposal.parameters["scheduled_for"] == "2026-08-24T13:17:00+00:00"


async def test_demo_route_scheduled_for_follows_clock_ticks():
    ctrl = SimpleNamespace(world=_world())
    ctrl.world.clock.tick(3 * 86400)

    proposal = await demo_mod._build_proposal(
        _demo_rec(), "trace-1", None, warehouse_id="DC-47", ctrl=ctrl
    )

    assert proposal.parameters["scheduled_for"] == "2026-08-27T13:17:00+00:00"


async def test_demo_route_without_sim_clock_falls_back_to_wall_clock():
    proposal = await demo_mod._build_proposal(
        _demo_rec(), "trace-1", None, warehouse_id="DC-47"
    )

    _assert_next_day_wall_clock(_assert_proposal(proposal, warehouse_id="DC-47"))


# ── Copilot orchestrator ───────────────────────────────────────────────────────


async def test_copilot_scheduled_for_is_sim_clock_plus_one_day():
    ctrl = SimpleNamespace(world=SimpleNamespace(clock=SimulationClock(3600)))
    orch = GovernedActionOrchestrator(
        decision_engine=None, demo_controller=ctrl, runtime=None
    )

    proposal = await orch._build_proposal(
        _copilot_request(), "trace-1", warehouse_id="DC-47"
    )

    scheduled_for = _assert_proposal(proposal, warehouse_id="DC-47")
    assert proposal.parameters["scheduled_for"] == "2026-08-24T09:00:00+00:00"
    assert scheduled_for == ctrl.world.clock.now() + timedelta(days=1)


async def test_copilot_without_sim_clock_falls_back_to_wall_clock():
    orch = GovernedActionOrchestrator(
        decision_engine=None, demo_controller=None, runtime=None
    )

    proposal = await orch._build_proposal(
        _copilot_request(), "trace-1", warehouse_id="DC-47"
    )

    _assert_next_day_wall_clock(_assert_proposal(proposal, warehouse_id="DC-47"))


# ── Downstream: executor + demo provider accept the produced string ───────────


class _ProviderMaintenanceSkill:
    """Routes the executor's maintenance request to the demo provider."""

    def __init__(self, provider: SimulationEquipmentProvider) -> None:
        self._provider = provider
        self.requests: list = []

    async def execute(self, request):
        self.requests.append(request)
        return await self._provider.execute_schedule_maintenance(request)


@pytest.mark.parametrize("builder", ["demo", "copilot"])
async def test_produced_scheduled_for_is_applied_by_executor_and_provider(builder):
    world = _world()
    ctrl = SimpleNamespace(world=world)
    if builder == "demo":
        proposal = await demo_mod._build_proposal(
            _demo_rec(), "trace-1", None, warehouse_id="DC-47", ctrl=ctrl
        )
    else:
        orch = GovernedActionOrchestrator(
            decision_engine=None, demo_controller=ctrl, runtime=None
        )
        proposal = await orch._build_proposal(
            _copilot_request(), "trace-1", warehouse_id="DC-47"
        )

    skill = _ProviderMaintenanceSkill(
        SimulationEquipmentProvider(world, ScenarioEventBus())
    )
    executor = EquipmentActionExecutor(assign_skill=None, maintenance_skill=skill)
    decision = DecisionResult(
        request_id="req-1",
        proposal_id=proposal.proposal_id,
        outcome=DecisionOutcome.APPROVED,
    )

    result = await executor.execute(proposal, decision)

    assert len(skill.requests) == 1
    assert skill.requests[0].scheduled_for == proposal.parameters["scheduled_for"]
    assert result.success is True
    asset = world.equipment["FL-01"]
    assert asset.status == "maintenance"
    # The provider swallows a ValueError from fromisoformat, so this is the
    # check that the string was actually parsed.
    assert asset.next_pm_due == _SIM_NOW + timedelta(days=1)
