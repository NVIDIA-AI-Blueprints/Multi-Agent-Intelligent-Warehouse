# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Copilot wave proposals are bound to the request's warehouse (#220).

The DecisionEngine rejects an approval whose ``warehouse_id`` differs from the
proposal's (``approval.warehouse_mismatch``, confused-deputy check 1c). The
copilot orchestrator must therefore build the wave proposal with the warehouse
it was asked to govern, not the skill's ``"default"`` fallback.
"""

from __future__ import annotations

import pytest

from maiw_api.copilot.models import GovernedActionRequest
from maiw_api.copilot.orchestrator import GovernedActionOrchestrator


def _wave_request(**overrides) -> GovernedActionRequest:
    fields = dict(
        recommendation_id="r1",
        capability="warehouse.wave.reprioritize",
        target="wave-017",
        domain="wave",
        objective="Reprioritize wave 17",
        rationale="Carrier cutoff at risk.",
        priority="HIGH",
        subtype=None,
        conversation_id="conv-1",
        turn_id="turn-1",
        trace_id="trace-1",
        source_turn_id="src-turn",
        source_trace_id="src-trace",
        source_snapshot_id="snap-001",
        current_snapshot_id="snap-002",
        focus_entity_id="wave-017",
    )
    fields.update(overrides)
    return GovernedActionRequest(**fields)


@pytest.mark.asyncio
@pytest.mark.parametrize("warehouse_id", ["DC-47", "DC-12"])
async def test_wave_proposal_is_bound_to_request_warehouse(warehouse_id):
    orch = GovernedActionOrchestrator(
        decision_engine=None, demo_controller=None, runtime=None
    )

    proposal = await orch._build_proposal(
        _wave_request(), "trace-1", warehouse_id=warehouse_id
    )

    assert proposal.action == "warehouse.wave.reprioritize"
    assert proposal.parameters["wave_id"] == "wave-017"
    assert proposal.parameters["warehouse_id"] == warehouse_id


@pytest.mark.asyncio
async def test_wave_proposal_binds_zone_targets_too():
    orch = GovernedActionOrchestrator(
        decision_engine=None, demo_controller=None, runtime=None
    )

    proposal = await orch._build_proposal(
        _wave_request(target="zoneA"), "trace-1", warehouse_id="DC-47"
    )

    assert proposal.parameters["zone"] == "zoneA"
    assert proposal.parameters["warehouse_id"] == "DC-47"
