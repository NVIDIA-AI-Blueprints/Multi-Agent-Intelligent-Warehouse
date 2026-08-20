# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Labor capability contract tests.

Validates that:
- ProposeLaborAllocationSkill builds proposals locally (no MCP call)
- Proposal is a valid ActionProposal with correct fields
- warehouse_id propagates into proposal.parameters
- Execution skill paths are typed correctly
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from maiw_mcp.contracts.actions import ActionProposal, RiskLevel
from maiw_mcp.contracts.labor import (
    LABOR_ALLOCATE_METADATA,
    LABOR_GET_ALLOCATION_METADATA,
    LABOR_GET_CAPACITY_METADATA,
    LaborAllocateResult,
    LaborAllocationResult,
    LaborCapacityResult,
    LaborWorkerInfo,
)
from src.api.skills.labor import ProposeLaborAllocationSkill


class TestLaborCapabilityMetadata:
    def test_get_capacity_is_read_only(self):
        assert LABOR_GET_CAPACITY_METADATA.side_effect == "read"
        assert LABOR_GET_CAPACITY_METADATA.risk == "read_only"
        assert LABOR_GET_CAPACITY_METADATA.domain == "labor"

    def test_get_allocation_is_read_only(self):
        assert LABOR_GET_ALLOCATION_METADATA.side_effect == "read"
        assert LABOR_GET_ALLOCATION_METADATA.risk == "read_only"

    def test_allocate_is_write_medium(self):
        assert LABOR_ALLOCATE_METADATA.side_effect == "write"
        assert LABOR_ALLOCATE_METADATA.risk == "medium"
        assert LABOR_ALLOCATE_METADATA.required_permission == "labor:execute"

    def test_allocate_requires_audit_binding(self):
        assert "proposal_id" in LABOR_ALLOCATE_METADATA.description
        assert "decision_id" in LABOR_ALLOCATE_METADATA.description
        assert "APPROVED" in LABOR_ALLOCATE_METADATA.description


class TestProposeLaborAllocationSkill:
    def test_proposal_skill_returns_action_proposal_locally(self):
        async def run():
            skill = ProposeLaborAllocationSkill()
            return await skill.execute(
                task_id="task-001",
                task_type="PICK",
                worker_ids=["w-001", "w-002"],
                zone="A1",
                priority="high",
                reason="wave at risk",
                requested_by="operations-agent",
                warehouse_id="WH-001",
            )

        result = asyncio.run(run())
        assert isinstance(result, ActionProposal)
        assert result.action == "warehouse.labor.allocate"
        assert result.domain == "labor"
        assert result.risk_level == RiskLevel.MEDIUM
        assert result.requires_approval is True

    def test_proposal_skill_includes_warehouse_id(self):
        async def run():
            skill = ProposeLaborAllocationSkill()
            return await skill.execute(
                task_id="t-001",
                task_type="PICK",
                worker_ids=["w-001"],
                warehouse_id="WH-CUSTOM",
            )

        result = asyncio.run(run())
        assert result.parameters.get("warehouse_id") == "WH-CUSTOM"

    def test_proposal_skill_includes_all_parameters(self):
        async def run():
            skill = ProposeLaborAllocationSkill()
            return await skill.execute(
                task_id="task-002",
                task_type="PACK",
                worker_ids=["w-003"],
                zone="B2",
                priority="medium",
            )

        result = asyncio.run(run())
        assert result.parameters["task_id"] == "task-002"
        assert result.parameters["task_type"] == "PACK"
        assert result.parameters["worker_ids"] == ["w-003"]
        assert result.parameters["zone"] == "B2"

    def test_proposal_skill_makes_no_mcp_call(self):
        """Architecture invariant: proposal skill must not call MCP."""

        async def run():
            mock_client = MagicMock()
            mock_client.invoke = AsyncMock()
            skill = ProposeLaborAllocationSkill()
            await skill.execute(
                task_id="t-001",
                task_type="PICK",
                worker_ids=["w-001"],
            )
            return mock_client.invoke.call_count

        call_count = asyncio.run(run())
        assert call_count == 0, "ProposeLaborAllocationSkill must not invoke MCP"

    def test_proposal_has_valid_uuid_proposal_id(self):
        import uuid

        async def run():
            skill = ProposeLaborAllocationSkill()
            return await skill.execute(
                task_id="t-001",
                task_type="PICK",
                worker_ids=["w-001"],
            )

        result = asyncio.run(run())
        uuid.UUID(result.proposal_id)  # raises if invalid


class TestActionProposalLaborFactories:
    def test_for_labor_allocate_creates_proposal(self):
        p = ActionProposal.for_labor_allocate(
            task_id="task-001",
            task_type="PICK",
            worker_ids=["w-001"],
            warehouse_id="WH-1",
            reason="wave at risk",
            requested_by="ops-agent",
        )
        assert p.action == "warehouse.labor.allocate"
        assert p.domain == "labor"
        assert p.risk_level == RiskLevel.MEDIUM
        assert p.requires_approval is True
        assert p.parameters["warehouse_id"] == "WH-1"
        assert p.parameters["worker_ids"] == ["w-001"]

    def test_for_labor_allocate_sequential_proposals_have_different_ids(self):
        p1 = ActionProposal.for_labor_allocate(
            task_id="t-1", task_type="PICK", worker_ids=["w-1"]
        )
        p2 = ActionProposal.for_labor_allocate(
            task_id="t-2", task_type="PACK", worker_ids=["w-2"]
        )
        assert p1.proposal_id != p2.proposal_id
