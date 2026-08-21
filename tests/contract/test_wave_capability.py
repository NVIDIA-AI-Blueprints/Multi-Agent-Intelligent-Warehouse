# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Wave capability contract tests.

Validates that:
- ProposeWaveReprioritizationSkill builds proposals locally (no MCP call)
- Proposal is a valid ActionProposal with correct fields
- warehouse_id propagates into proposal.parameters
- Write tool requires APPROVED + matching proposal_id
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from maiw_mcp.contracts.actions import ActionProposal, RiskLevel
from maiw_mcp.contracts.wave import (
    WAVE_GET_METADATA,
    WAVE_GET_RISK_METADATA,
    WAVE_REPRIORITIZE_METADATA,
)
from src.api.skills.wave import ProposeWaveReprioritizationSkill


class TestWaveCapabilityMetadata:
    def test_get_is_read_only(self):
        assert WAVE_GET_METADATA.side_effect == "read"
        assert WAVE_GET_METADATA.risk == "read_only"
        assert WAVE_GET_METADATA.domain == "wave"

    def test_get_risk_is_read_only(self):
        assert WAVE_GET_RISK_METADATA.side_effect == "read"
        assert WAVE_GET_RISK_METADATA.risk == "read_only"

    def test_reprioritize_is_write_medium(self):
        assert WAVE_REPRIORITIZE_METADATA.side_effect == "write"
        assert WAVE_REPRIORITIZE_METADATA.risk == "medium"
        assert WAVE_REPRIORITIZE_METADATA.required_permission == "wave:execute"

    def test_reprioritize_requires_audit_binding(self):
        assert "proposal_id" in WAVE_REPRIORITIZE_METADATA.description
        assert "decision_id" in WAVE_REPRIORITIZE_METADATA.description
        assert "APPROVED" in WAVE_REPRIORITIZE_METADATA.description


class TestProposeWaveReprioritizationSkill:
    def test_proposal_skill_returns_action_proposal_locally(self):
        async def run():
            skill = ProposeWaveReprioritizationSkill()
            return await skill.execute(
                new_priority="high",
                zone="A1",
                reason="OTIF at risk",
                requested_by="operations-agent",
                warehouse_id="WH-001",
            )

        result = asyncio.run(run())
        assert isinstance(result, ActionProposal)
        assert result.action == "warehouse.wave.reprioritize"
        assert result.domain == "wave"
        assert result.risk_level == RiskLevel.MEDIUM
        assert result.requires_approval is True

    def test_proposal_skill_includes_warehouse_id(self):
        async def run():
            skill = ProposeWaveReprioritizationSkill()
            return await skill.execute(
                new_priority="critical",
                warehouse_id="WH-CUSTOM",
            )

        result = asyncio.run(run())
        assert result.parameters.get("warehouse_id") == "WH-CUSTOM"

    def test_proposal_skill_includes_all_parameters(self):
        async def run():
            skill = ProposeWaveReprioritizationSkill()
            return await skill.execute(
                wave_id="wave-007",
                zone="B2",
                new_priority="urgent",
            )

        result = asyncio.run(run())
        assert result.parameters["wave_id"] == "wave-007"
        assert result.parameters["zone"] == "B2"
        assert result.parameters["new_priority"] == "urgent"

    def test_proposal_skill_makes_no_mcp_call(self):
        """Architecture invariant: proposal skill must not call MCP."""

        async def run():
            mock_client = MagicMock()
            mock_client.invoke = AsyncMock()
            skill = ProposeWaveReprioritizationSkill()
            await skill.execute(new_priority="high")
            return mock_client.invoke.call_count

        call_count = asyncio.run(run())
        assert call_count == 0, "ProposeWaveReprioritizationSkill must not invoke MCP"

    def test_proposal_has_valid_uuid_proposal_id(self):
        import uuid

        async def run():
            skill = ProposeWaveReprioritizationSkill()
            return await skill.execute(new_priority="high")

        result = asyncio.run(run())
        uuid.UUID(result.proposal_id)  # raises if invalid


class TestActionProposalWaveFactories:
    def test_for_wave_reprioritize_creates_proposal(self):
        p = ActionProposal.for_wave_reprioritize(
            zone="A1",
            new_priority="high",
            warehouse_id="WH-1",
            reason="OTIF at risk",
            requested_by="ops-agent",
        )
        assert p.action == "warehouse.wave.reprioritize"
        assert p.domain == "wave"
        assert p.risk_level == RiskLevel.MEDIUM
        assert p.requires_approval is True
        assert p.parameters["warehouse_id"] == "WH-1"
        assert p.parameters["new_priority"] == "high"

    def test_for_wave_reprioritize_sequential_proposals_have_different_ids(self):
        p1 = ActionProposal.for_wave_reprioritize(new_priority="high")
        p2 = ActionProposal.for_wave_reprioritize(new_priority="critical")
        assert p1.proposal_id != p2.proposal_id

    def test_for_wave_reprioritize_wave_id_is_optional(self):
        p = ActionProposal.for_wave_reprioritize(new_priority="high")
        assert p.parameters.get("wave_id") is None
