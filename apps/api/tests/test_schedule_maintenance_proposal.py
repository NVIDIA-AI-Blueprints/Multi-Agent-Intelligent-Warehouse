# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
schedule_maintenance proposals carry the required ``scheduled_for``.

``ActionProposal.for_schedule_maintenance()`` takes ``scheduled_for`` as a
required keyword-only argument. Both proposal builders — the copilot
GovernedActionOrchestrator and the demo analyze route — must supply it, or
every ``warehouse.equipment.schedule_maintenance`` recommendation fails with a
TypeError before it reaches the DecisionEngine.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from maiw_api.copilot.models import GovernedActionRequest
from maiw_api.copilot.orchestrator import GovernedActionOrchestrator
from maiw_api.routers import demo as demo_mod

_CAP = "warehouse.equipment.schedule_maintenance"


def _assert_proposal(proposal, *, warehouse_id: str) -> None:
    assert proposal.action == _CAP
    assert proposal.parameters["asset_id"] == "FL-01"
    assert proposal.parameters["warehouse_id"] == warehouse_id

    # An ISO-8601 datetime (the equipment contract and the demo provider both
    # parse it with datetime.fromisoformat) that lies in the future.
    scheduled_for = datetime.fromisoformat(proposal.parameters["scheduled_for"])
    now = datetime.now(timezone.utc)
    assert scheduled_for.tzinfo is not None
    assert now < scheduled_for <= now + timedelta(days=2)


@pytest.mark.asyncio
async def test_copilot_orchestrator_builds_schedule_maintenance_proposal():
    orch = GovernedActionOrchestrator(
        decision_engine=None, demo_controller=None, runtime=None
    )
    request = GovernedActionRequest(
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

    proposal = await orch._build_proposal(request, "trace-1", warehouse_id="DC-47")

    _assert_proposal(proposal, warehouse_id="DC-47")


@pytest.mark.asyncio
async def test_demo_route_builds_schedule_maintenance_proposal():
    rec = SimpleNamespace(
        capability=_CAP,
        target="FL-01",
        subtype=None,
        objective="Inspect forklift FL-01",
        priority="medium",
        rationale="Hydraulic fault.",
    )

    proposal = await demo_mod._build_proposal(
        rec, "trace-1", None, warehouse_id="DC-47"
    )

    _assert_proposal(proposal, warehouse_id="DC-47")
