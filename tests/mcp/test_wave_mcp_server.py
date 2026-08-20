# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Wave MCP server protocol tests.

Validates that the server:
- Exposes exactly 3 tools with the correct semantic names
- Exposes NO proposal-generation tools
- Read tools return well-formed responses
- Risk tool identifies OTIF risk
- Write tool requires proposal_id and decision_id
- Write tool executes and echoes audit IDs
"""

from __future__ import annotations

import asyncio
import json

import pytest

from mcp.client import Client

from mcp_servers.wave.provider import MockWaveProvider
from mcp_servers.wave.server import configure_server, mcp_server


@pytest.fixture(autouse=True)
def _setup_mock_provider():
    configure_server(MockWaveProvider())


# ── Tool discovery ─────────────────────────────────────────────────────────────


class TestWaveServerToolDiscovery:
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
        assert "warehouse.wave.get" in names
        assert "warehouse.wave.get_risk" in names
        assert "warehouse.wave.reprioritize" in names

    def test_no_proposal_tools_exposed(self):
        async def run():
            async with Client(mcp_server) as client:
                result = await client.list_tools()
                return [t.name for t in result.tools]

        names = asyncio.run(run())
        assert not any("propose" in n for n in names)

    def test_write_tool_schema_requires_audit_ids(self):
        async def run():
            async with Client(mcp_server) as client:
                result = await client.list_tools()
                tools = {t.name: t for t in result.tools}
                props = tools["warehouse.wave.reprioritize"].input_schema.get(
                    "properties", {}
                )
                return props

        props = asyncio.run(run())
        assert "proposal_id" in props
        assert "decision_id" in props


# ── Read tools ────────────────────────────────────────────────────────────────


class TestWaveGetTool:
    def test_get_returns_tasks(self):
        async def run():
            async with Client(mcp_server) as client:
                raw = await client.call_tool(
                    "warehouse.wave.get", {"warehouse_id": "wh-1"}
                )
                return json.loads(raw.content[0].text)

        result = asyncio.run(run())
        assert "tasks" in result
        assert isinstance(result["tasks"], list)
        assert result["total_tasks"] >= 0

    def test_get_zone_filter(self):
        async def run():
            async with Client(mcp_server) as client:
                raw = await client.call_tool(
                    "warehouse.wave.get", {"warehouse_id": "wh-1", "zone": "A1"}
                )
                return json.loads(raw.content[0].text)

        result = asyncio.run(run())
        for t in result["tasks"]:
            assert t["zone"] == "A1"

    def test_get_returns_zone_summary(self):
        async def run():
            async with Client(mcp_server) as client:
                raw = await client.call_tool(
                    "warehouse.wave.get", {"warehouse_id": "wh-1"}
                )
                return json.loads(raw.content[0].text)

        result = asyncio.run(run())
        assert "zones_active" in result
        assert "summary" in result


class TestWaveRiskTool:
    def test_risk_returns_otif_assessment(self):
        async def run():
            async with Client(mcp_server) as client:
                raw = await client.call_tool(
                    "warehouse.wave.get_risk", {"warehouse_id": "wh-1"}
                )
                return json.loads(raw.content[0].text)

        result = asyncio.run(run())
        assert "otif_at_risk" in result
        assert "risk_level" in result
        assert "at_risk_task_count" in result
        assert "risk_factors" in result

    def test_mock_has_unassigned_tasks_causing_risk(self):
        """MockWaveProvider has unassigned pending tasks → otif_at_risk=True."""

        async def run():
            async with Client(mcp_server) as client:
                raw = await client.call_tool(
                    "warehouse.wave.get_risk", {"warehouse_id": "wh-1"}
                )
                return json.loads(raw.content[0].text)

        result = asyncio.run(run())
        assert result["otif_at_risk"] is True
        assert result["at_risk_task_count"] > 0

    def test_risk_recommendation_present_when_at_risk(self):
        async def run():
            async with Client(mcp_server) as client:
                raw = await client.call_tool(
                    "warehouse.wave.get_risk", {"warehouse_id": "wh-1"}
                )
                return json.loads(raw.content[0].text)

        result = asyncio.run(run())
        if result["otif_at_risk"]:
            assert result["recommendation"] != ""


# ── Write tool ────────────────────────────────────────────────────────────────


class TestWaveReprioritizeTool:
    def test_reprioritize_returns_success(self):
        async def run():
            async with Client(mcp_server) as client:
                raw = await client.call_tool(
                    "warehouse.wave.reprioritize",
                    {
                        "warehouse_id": "wh-1",
                        "new_priority": "high",
                        "proposal_id": "prop-001",
                        "decision_id": "dec-001",
                        "reason": "OTIF at risk",
                    },
                )
                return json.loads(raw.content[0].text)

        result = asyncio.run(run())
        assert result["success"] is True
        assert result["new_priority"] == "high"
        assert result["tasks_updated"] >= 0

    def test_reprioritize_echoes_audit_ids(self):
        async def run():
            async with Client(mcp_server) as client:
                raw = await client.call_tool(
                    "warehouse.wave.reprioritize",
                    {
                        "warehouse_id": "wh-1",
                        "new_priority": "critical",
                        "proposal_id": "prop-abc",
                        "decision_id": "dec-abc",
                    },
                )
                return json.loads(raw.content[0].text)

        result = asyncio.run(run())
        assert result["proposal_id"] == "prop-abc"
        assert result["decision_id"] == "dec-abc"

    def test_reprioritize_zone_filter(self):
        async def run():
            async with Client(mcp_server) as client:
                raw = await client.call_tool(
                    "warehouse.wave.reprioritize",
                    {
                        "warehouse_id": "wh-1",
                        "zone": "A1",
                        "new_priority": "high",
                        "proposal_id": "p-z",
                        "decision_id": "d-z",
                    },
                )
                return json.loads(raw.content[0].text)

        result = asyncio.run(run())
        assert result["success"] is True
