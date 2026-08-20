# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Labor MCP server protocol tests.

Validates that the server:
- Exposes exactly 3 tools with the correct semantic names
- Exposes NO proposal-generation tools
- Read tools return well-formed responses
- Write tool requires proposal_id and decision_id in schema
- Write tool executes allocation and echoes audit IDs
"""

from __future__ import annotations

import asyncio
import json

import pytest

from mcp.client import Client

from mcp_servers.labor.provider import MockLaborProvider
from mcp_servers.labor.server import configure_server, mcp_server


@pytest.fixture(autouse=True)
def _setup_mock_provider():
    configure_server(MockLaborProvider())


# ── Tool discovery ─────────────────────────────────────────────────────────────


class TestLaborServerToolDiscovery:
    def test_server_exposes_three_tools(self):
        async def run():
            async with Client(mcp_server) as client:
                result = await client.list_tools()
                return result.tools

        tools = asyncio.run(run())
        assert len(tools) == 3

    def test_tool_names_are_semantic(self):
        async def run():
            async with Client(mcp_server) as client:
                result = await client.list_tools()
                return {t.name for t in result.tools}

        names = asyncio.run(run())
        assert "warehouse.labor.get_capacity" in names
        assert "warehouse.labor.get_allocation" in names
        assert "warehouse.labor.allocate" in names

    def test_no_proposal_tools_exposed(self):
        async def run():
            async with Client(mcp_server) as client:
                result = await client.list_tools()
                return [t.name for t in result.tools]

        names = asyncio.run(run())
        assert not any("propose" in n for n in names)
        assert not any("suggest" in n for n in names)

    def test_write_tool_schema_requires_audit_ids(self):
        async def run():
            async with Client(mcp_server) as client:
                result = await client.list_tools()
                tools = {t.name: t for t in result.tools}
                props = tools["warehouse.labor.allocate"].input_schema.get("properties", {})
                return props

        props = asyncio.run(run())
        assert "proposal_id" in props
        assert "decision_id" in props


# ── Read tools ────────────────────────────────────────────────────────────────


class TestLaborCapacityTool:
    def test_get_capacity_returns_workers(self):
        async def run():
            async with Client(mcp_server) as client:
                raw = await client.call_tool(
                    "warehouse.labor.get_capacity",
                    {"warehouse_id": "wh-1", "status_filter": "active"},
                )
                return json.loads(raw.content[0].text)

        result = asyncio.run(run())
        assert "workers" in result
        assert isinstance(result["workers"], list)
        assert result["total_workers"] >= 0

    def test_get_capacity_zone_filter(self):
        async def run():
            async with Client(mcp_server) as client:
                raw = await client.call_tool(
                    "warehouse.labor.get_capacity",
                    {"warehouse_id": "wh-1", "zone": "A1", "status_filter": "active"},
                )
                return json.loads(raw.content[0].text)

        result = asyncio.run(run())
        assert result["zone"] == "A1"
        for w in result["workers"]:
            assert w["zone"] == "A1"

    def test_get_capacity_source_is_mock(self):
        async def run():
            async with Client(mcp_server) as client:
                raw = await client.call_tool(
                    "warehouse.labor.get_capacity", {"warehouse_id": "wh-1"}
                )
                return json.loads(raw.content[0].text)

        result = asyncio.run(run())
        assert result["source"] == "mock"


class TestLaborAllocationTool:
    def test_get_allocation_returns_tasks(self):
        async def run():
            async with Client(mcp_server) as client:
                raw = await client.call_tool(
                    "warehouse.labor.get_allocation", {"warehouse_id": "wh-1"}
                )
                return json.loads(raw.content[0].text)

        result = asyncio.run(run())
        assert "allocations" in result
        assert isinstance(result["allocations"], list)
        assert "total_tasks" in result


# ── Write tool ────────────────────────────────────────────────────────────────


class TestLaborAllocateExecutionTool:
    def test_allocate_returns_success(self):
        async def run():
            async with Client(mcp_server) as client:
                raw = await client.call_tool(
                    "warehouse.labor.allocate",
                    {
                        "warehouse_id": "wh-1",
                        "task_id": "task-001",
                        "task_type": "PICK",
                        "worker_ids": ["w-001", "w-002"],
                        "proposal_id": "prop-001",
                        "decision_id": "dec-001",
                    },
                )
                return json.loads(raw.content[0].text)

        result = asyncio.run(run())
        assert result["success"] is True
        assert result["task_id"] == "task-001"
        assert result["worker_ids"] == ["w-001", "w-002"]

    def test_allocate_echoes_audit_ids(self):
        async def run():
            async with Client(mcp_server) as client:
                raw = await client.call_tool(
                    "warehouse.labor.allocate",
                    {
                        "warehouse_id": "wh-1",
                        "task_id": "task-002",
                        "task_type": "PACK",
                        "worker_ids": ["w-003"],
                        "proposal_id": "prop-xyz",
                        "decision_id": "dec-xyz",
                    },
                )
                return json.loads(raw.content[0].text)

        result = asyncio.run(run())
        assert result["proposal_id"] == "prop-xyz"
        assert result["decision_id"] == "dec-xyz"

    def test_allocate_result_has_no_action_proposal(self):
        """Result of execute tool must not contain an ActionProposal."""
        async def run():
            async with Client(mcp_server) as client:
                raw = await client.call_tool(
                    "warehouse.labor.allocate",
                    {
                        "warehouse_id": "wh-1",
                        "task_id": "t-001",
                        "task_type": "PICK",
                        "worker_ids": ["w-001"],
                        "proposal_id": "p-1",
                        "decision_id": "d-1",
                    },
                )
                return json.loads(raw.content[0].text)

        result = asyncio.run(run())
        assert "proposal_id" in result  # audit echo is OK
        assert "action" not in result  # must not be an ActionProposal
        assert "risk_level" not in result
