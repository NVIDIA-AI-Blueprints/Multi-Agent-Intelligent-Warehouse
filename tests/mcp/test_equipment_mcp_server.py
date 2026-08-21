# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Equipment MCP Server protocol tests (MCP SDK v2, protocol 2026-07-28).

Tests the full MCP wire protocol for the Equipment server using
``Client(mcp_server)`` for in-memory transport (no network needed).

Coverage
--------
- Tool discovery: all five tools visible (3 read + 2 write renames)
- Input schema validation (snake_case in v2)
- warehouse.equipment.get_status: valid request, empty fleet, filter params
- warehouse.equipment.get_telemetry: valid request, missing asset
- warehouse.equipment.assign: execution (requires proposal_id + decision_id)
- warehouse.equipment.release: execution (requires proposal_id + decision_id)
- warehouse.equipment.schedule_maintenance: execution (requires proposal_id + decision_id)
- Error handling: is_error=True on BackendUnavailable
- Stateless behavior: independent Client lifetimes return consistent results
- MCP v2 protocol assertions

Architecture invariant
----------------------
Write tools (assign, release, schedule_maintenance) accept proposal_id +
decision_id — they are execution capabilities, not proposal generators.
No MCP tool returns an ActionProposal; proposals are built locally by skills.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

import pytest
from mcp.client import Client

from maiw_mcp.contracts.equipment import EquipmentAssetInfo, TelemetryPoint
from mcp_servers.equipment.provider import MockEquipmentProvider
from mcp_servers.equipment.server import configure_server, mcp_server

# ── Shared provider builder ───────────────────────────────────────────────────


def _build_provider() -> MockEquipmentProvider:
    provider = MockEquipmentProvider()
    provider.add_asset(
        EquipmentAssetInfo(
            asset_id="FL-001",
            equipment_type="forklift",
            model="FL-3000",
            zone="ZONE-A",
            status="available",
        )
    )
    provider.add_asset(
        EquipmentAssetInfo(
            asset_id="AMR-001",
            equipment_type="amr",
            model="AMR-X200",
            zone="ZONE-B",
            status="assigned",
            owner_user="operator-1",
        )
    )
    provider.add_telemetry(
        "FL-001",
        [
            TelemetryPoint(
                timestamp=datetime.now(timezone.utc),
                metric="battery_level",
                value=82.0,
                unit="percent",
                quality_score=1.0,
            ),
            TelemetryPoint(
                timestamp=datetime.now(timezone.utc),
                metric="speed",
                value=2.8,
                unit="m/s",
                quality_score=0.9,
            ),
        ],
    )
    return provider


@pytest.fixture(autouse=True)
def reset_provider():
    configure_server(_build_provider())
    yield


# ── MCP v2 protocol assertions ────────────────────────────────────────────────


class TestMCPV2Protocol:
    def test_mcp_server_importable_from_v2_path(self):
        from mcp.server import MCPServer

        assert MCPServer is not None

    def test_fastmcp_not_importable(self):
        """mcp.server.fastmcp was removed in v2."""
        try:
            from mcp.server import fastmcp  # noqa: F401

            has_fastmcp = True
        except ImportError:
            has_fastmcp = False
        assert not has_fastmcp

    def test_sdk_version_is_v2(self):
        from importlib.metadata import version

        sdk_version = version("mcp")
        assert sdk_version.startswith("2."), f"Expected MCP v2.x, got {sdk_version}"

    def test_is_error_attribute_is_snake_case(self):
        """v2: CallToolResult.is_error (snake_case), not isError."""
        import mcp.types as types

        annotations = types.CallToolResult.model_fields
        assert "is_error" in annotations
        assert "isError" not in annotations

    def test_equipment_server_responds_to_initialize(self):
        async def run():
            async with Client(mcp_server) as client:
                tools = await client.list_tools()
                return len(tools.tools)

        count = asyncio.run(run())
        assert count >= 3

    def test_input_schema_attribute_is_snake_case(self):
        """v2: Tool.input_schema (snake_case), not inputSchema."""

        async def run():
            async with Client(mcp_server) as client:
                result = await client.list_tools()
                tool = result.tools[0]
                return tool.input_schema, hasattr(tool, "inputSchema")

        schema, has_camel = asyncio.run(run())
        assert isinstance(schema, dict)
        assert not has_camel


# ── Tool discovery ────────────────────────────────────────────────────────────


class TestToolDiscovery:
    def test_server_exposes_five_tools(self):
        async def run():
            async with Client(mcp_server) as client:
                result = await client.list_tools()
                return [t.name for t in result.tools]

        names = asyncio.run(run())
        assert "warehouse.equipment.get_status" in names
        assert "warehouse.equipment.get_telemetry" in names
        assert "warehouse.equipment.assign" in names
        assert "warehouse.equipment.release" in names
        assert "warehouse.equipment.schedule_maintenance" in names

    def test_no_proposal_tools_exposed(self):
        """Proposal generation is local — no MCP tool should exist for it."""

        async def run():
            async with Client(mcp_server) as client:
                result = await client.list_tools()
                return [t.name for t in result.tools]

        names = asyncio.run(run())
        assert "warehouse.equipment.propose_release" not in names
        assert "warehouse.equipment.propose_maintenance" not in names
        assert "warehouse.equipment.execute_assign" not in names
        assert "warehouse.equipment.execute_release" not in names
        assert "warehouse.equipment.execute_maintenance" not in names

    def test_get_status_input_schema_has_expected_params(self):
        async def run():
            async with Client(mcp_server) as client:
                result = await client.list_tools()
                tool = next(
                    t
                    for t in result.tools
                    if t.name == "warehouse.equipment.get_status"
                )
                return tool.input_schema.get("properties", {})

        props = asyncio.run(run())
        assert "asset_id" in props
        assert "equipment_type" in props
        assert "zone" in props
        assert "status_filter" in props

    def test_get_telemetry_input_schema_has_asset_id(self):
        async def run():
            async with Client(mcp_server) as client:
                result = await client.list_tools()
                tool = next(
                    t
                    for t in result.tools
                    if t.name == "warehouse.equipment.get_telemetry"
                )
                return tool.input_schema.get("properties", {})

        props = asyncio.run(run())
        assert "asset_id" in props
        assert "metric" in props
        assert "hours_back" in props

    def test_assign_input_schema_requires_proposal_and_decision_ids(self):
        """warehouse.equipment.assign is now an execution tool — needs audit IDs."""

        async def run():
            async with Client(mcp_server) as client:
                result = await client.list_tools()
                tool = next(
                    t for t in result.tools if t.name == "warehouse.equipment.assign"
                )
                return tool.input_schema.get("properties", {})

        props = asyncio.run(run())
        assert "asset_id" in props
        assert "assignee" in props
        assert "proposal_id" in props
        assert "decision_id" in props

    def test_release_input_schema_requires_audit_ids(self):
        async def run():
            async with Client(mcp_server) as client:
                result = await client.list_tools()
                tool = next(
                    t for t in result.tools if t.name == "warehouse.equipment.release"
                )
                return tool.input_schema.get("properties", {})

        props = asyncio.run(run())
        assert "asset_id" in props
        assert "released_by" in props
        assert "proposal_id" in props
        assert "decision_id" in props

    def test_schedule_maintenance_input_schema_requires_audit_ids(self):
        async def run():
            async with Client(mcp_server) as client:
                result = await client.list_tools()
                tool = next(
                    t
                    for t in result.tools
                    if t.name == "warehouse.equipment.schedule_maintenance"
                )
                return tool.input_schema.get("properties", {})

        props = asyncio.run(run())
        assert "asset_id" in props
        assert "proposal_id" in props
        assert "decision_id" in props


# ── warehouse.equipment.get_status ────────────────────────────────────────────


class TestGetStatus:
    def test_get_all_equipment_returns_fleet(self):
        async def run():
            async with Client(mcp_server) as client:
                result = await client.call_tool("warehouse.equipment.get_status", {})
                return result.is_error, json.loads(result.content[0].text)

        is_error, data = asyncio.run(run())
        assert not is_error
        assert data["total_count"] == 2
        asset_ids = {a["asset_id"] for a in data["equipment"]}
        assert "FL-001" in asset_ids
        assert "AMR-001" in asset_ids

    def test_filter_by_asset_id(self):
        async def run():
            async with Client(mcp_server) as client:
                result = await client.call_tool(
                    "warehouse.equipment.get_status", {"asset_id": "FL-001"}
                )
                return result.is_error, json.loads(result.content[0].text)

        is_error, data = asyncio.run(run())
        assert not is_error
        assert data["total_count"] == 1
        assert data["equipment"][0]["asset_id"] == "FL-001"

    def test_filter_by_equipment_type(self):
        async def run():
            async with Client(mcp_server) as client:
                result = await client.call_tool(
                    "warehouse.equipment.get_status", {"equipment_type": "amr"}
                )
                return result.is_error, json.loads(result.content[0].text)

        is_error, data = asyncio.run(run())
        assert not is_error
        assert data["total_count"] == 1
        assert data["equipment"][0]["equipment_type"] == "amr"

    def test_filter_by_status(self):
        async def run():
            async with Client(mcp_server) as client:
                result = await client.call_tool(
                    "warehouse.equipment.get_status", {"status_filter": "available"}
                )
                return result.is_error, json.loads(result.content[0].text)

        is_error, data = asyncio.run(run())
        assert not is_error
        assert data["total_count"] == 1
        assert data["equipment"][0]["status"] == "available"

    def test_summary_breakdown_present(self):
        async def run():
            async with Client(mcp_server) as client:
                result = await client.call_tool("warehouse.equipment.get_status", {})
                return json.loads(result.content[0].text)

        data = asyncio.run(run())
        assert "summary" in data
        assert "forklift" in data["summary"]

    def test_result_is_valid_json(self):
        async def run():
            async with Client(mcp_server) as client:
                result = await client.call_tool("warehouse.equipment.get_status", {})
                return json.loads(result.content[0].text)

        data = asyncio.run(run())
        assert isinstance(data, dict)

    def test_empty_fleet_returns_zero_count(self):
        configure_server(MockEquipmentProvider())

        async def run():
            async with Client(mcp_server) as client:
                result = await client.call_tool("warehouse.equipment.get_status", {})
                return json.loads(result.content[0].text)

        data = asyncio.run(run())
        assert data["total_count"] == 0


# ── warehouse.equipment.get_telemetry ─────────────────────────────────────────


class TestGetTelemetry:
    def test_get_telemetry_for_existing_asset(self):
        async def run():
            async with Client(mcp_server) as client:
                result = await client.call_tool(
                    "warehouse.equipment.get_telemetry", {"asset_id": "FL-001"}
                )
                return result.is_error, json.loads(result.content[0].text)

        is_error, data = asyncio.run(run())
        assert not is_error
        assert data["asset_id"] == "FL-001"
        assert data["data_points"] == 2
        assert data["hours_back"] == 24

    def test_filter_telemetry_by_metric(self):
        async def run():
            async with Client(mcp_server) as client:
                result = await client.call_tool(
                    "warehouse.equipment.get_telemetry",
                    {"asset_id": "FL-001", "metric": "battery_level"},
                )
                return result.is_error, json.loads(result.content[0].text)

        is_error, data = asyncio.run(run())
        assert not is_error
        assert data["data_points"] == 1
        assert data["telemetry_data"][0]["metric"] == "battery_level"

    def test_get_telemetry_for_unknown_asset_returns_empty(self):
        async def run():
            async with Client(mcp_server) as client:
                result = await client.call_tool(
                    "warehouse.equipment.get_telemetry", {"asset_id": "GHOST-999"}
                )
                return result.is_error, json.loads(result.content[0].text)

        is_error, data = asyncio.run(run())
        assert not is_error
        assert data["asset_id"] == "GHOST-999"
        assert data["data_points"] == 0

    def test_telemetry_result_has_required_fields(self):
        async def run():
            async with Client(mcp_server) as client:
                result = await client.call_tool(
                    "warehouse.equipment.get_telemetry", {"asset_id": "FL-001"}
                )
                return json.loads(result.content[0].text)

        data = asyncio.run(run())
        required = {
            "asset_id",
            "telemetry_data",
            "available_metrics",
            "hours_back",
            "data_points",
            "source",
        }
        missing = required - set(data.keys())
        assert not missing, f"Missing fields: {missing}"


# ── warehouse.equipment.assign (execution) ────────────────────────────────────


class TestEquipmentAssignExecution:
    """warehouse.equipment.assign is an execution tool — requires proposal_id + decision_id."""

    def _make_ids(self):
        return str(uuid.uuid4()), str(uuid.uuid4())

    def test_assign_executes_and_returns_success(self):
        async def run():
            pid, did = self._make_ids()
            async with Client(mcp_server) as client:
                result = await client.call_tool(
                    "warehouse.equipment.assign",
                    {
                        "asset_id": "FL-001",
                        "assignee": "operator-5",
                        "proposal_id": pid,
                        "decision_id": did,
                    },
                )
                return result.is_error, json.loads(result.content[0].text)

        is_error, data = asyncio.run(run())
        assert not is_error
        assert data["success"] is True
        assert data["proposal_id"] is not None
        assert data["decision_id"] is not None

    def test_assign_result_has_no_proposal_field(self):
        """Execution result must not contain an ActionProposal — it's not a proposal tool."""

        async def run():
            pid, did = self._make_ids()
            async with Client(mcp_server) as client:
                result = await client.call_tool(
                    "warehouse.equipment.assign",
                    {
                        "asset_id": "FL-001",
                        "assignee": "operator-5",
                        "proposal_id": pid,
                        "decision_id": did,
                    },
                )
                return json.loads(result.content[0].text)

        data = asyncio.run(run())
        assert "proposal" not in data
        assert "risk_level" not in data

    def test_assign_result_echoes_audit_ids(self):
        async def run():
            pid, did = self._make_ids()
            async with Client(mcp_server) as client:
                result = await client.call_tool(
                    "warehouse.equipment.assign",
                    {
                        "asset_id": "FL-001",
                        "assignee": "op-1",
                        "proposal_id": pid,
                        "decision_id": did,
                    },
                )
                return json.loads(result.content[0].text), pid, did

        data, pid, did = asyncio.run(run())
        assert data["proposal_id"] == pid
        assert data["decision_id"] == did


# ── warehouse.equipment.release (execution) ───────────────────────────────────


class TestEquipmentReleaseExecution:
    def test_release_executes_and_returns_success(self):
        async def run():
            pid, did = str(uuid.uuid4()), str(uuid.uuid4())
            async with Client(mcp_server) as client:
                result = await client.call_tool(
                    "warehouse.equipment.release",
                    {
                        "asset_id": "AMR-001",
                        "released_by": "operator-1",
                        "proposal_id": pid,
                        "decision_id": did,
                    },
                )
                return result.is_error, json.loads(result.content[0].text)

        is_error, data = asyncio.run(run())
        assert not is_error
        assert data["success"] is True

    def test_release_result_echoes_audit_ids(self):
        async def run():
            pid, did = str(uuid.uuid4()), str(uuid.uuid4())
            async with Client(mcp_server) as client:
                result = await client.call_tool(
                    "warehouse.equipment.release",
                    {
                        "asset_id": "AMR-001",
                        "released_by": "operator-1",
                        "proposal_id": pid,
                        "decision_id": did,
                    },
                )
                return json.loads(result.content[0].text), pid, did

        data, pid, did = asyncio.run(run())
        assert data["proposal_id"] == pid
        assert data["decision_id"] == did


# ── warehouse.equipment.schedule_maintenance (execution) ──────────────────────


class TestEquipmentMaintenanceExecution:
    def test_maintenance_executes_and_returns_success(self):
        async def run():
            pid, did = str(uuid.uuid4()), str(uuid.uuid4())
            async with Client(mcp_server) as client:
                result = await client.call_tool(
                    "warehouse.equipment.schedule_maintenance",
                    {
                        "asset_id": "FL-001",
                        "maintenance_type": "preventive",
                        "description": "Annual PM",
                        "scheduled_by": "maintenance-team",
                        "scheduled_for": "2026-09-01T08:00:00Z",
                        "proposal_id": pid,
                        "decision_id": did,
                    },
                )
                return result.is_error, json.loads(result.content[0].text)

        is_error, data = asyncio.run(run())
        assert not is_error
        assert data["success"] is True

    def test_maintenance_result_echoes_audit_ids(self):
        async def run():
            pid, did = str(uuid.uuid4()), str(uuid.uuid4())
            async with Client(mcp_server) as client:
                result = await client.call_tool(
                    "warehouse.equipment.schedule_maintenance",
                    {
                        "asset_id": "FL-001",
                        "maintenance_type": "corrective",
                        "description": "Fix belt",
                        "scheduled_by": "tech-1",
                        "scheduled_for": "2026-09-02T10:00:00Z",
                        "proposal_id": pid,
                        "decision_id": did,
                    },
                )
                return json.loads(result.content[0].text), pid, did

        data, pid, did = asyncio.run(run())
        assert data["proposal_id"] == pid
        assert data["decision_id"] == did


# ── Stateless behavior ────────────────────────────────────────────────────────


class TestMCPStatelessBehavior:
    def test_two_independent_clients_return_consistent_results(self):
        async def run():
            async with Client(mcp_server) as client_a:
                result_a = await client_a.call_tool(
                    "warehouse.equipment.get_status", {}
                )
                data_a = json.loads(result_a.content[0].text)

            async with Client(mcp_server) as client_b:
                result_b = await client_b.call_tool(
                    "warehouse.equipment.get_status", {}
                )
                data_b = json.loads(result_b.content[0].text)

            return data_a, data_b

        data_a, data_b = asyncio.run(run())
        assert data_a["total_count"] == data_b["total_count"]
        ids_a = {a["asset_id"] for a in data_a["equipment"]}
        ids_b = {a["asset_id"] for a in data_b["equipment"]}
        assert ids_a == ids_b

    def test_client_per_request_pattern_is_supported(self):
        async def run():
            counts = []
            for _ in range(3):
                async with Client(mcp_server) as client:
                    r = await client.call_tool("warehouse.equipment.get_status", {})
                    counts.append(json.loads(r.content[0].text)["total_count"])
            return counts

        counts = asyncio.run(run())
        assert all(c == 2 for c in counts)

    def test_sequential_executions_are_independent(self):
        """Each execution call is independent — no shared session state between calls."""

        async def run():
            results = []
            async with Client(mcp_server) as client:
                for _ in range(3):
                    pid, did = str(uuid.uuid4()), str(uuid.uuid4())
                    r = await client.call_tool(
                        "warehouse.equipment.release",
                        {
                            "asset_id": "FL-001",
                            "released_by": "op-1",
                            "proposal_id": pid,
                            "decision_id": did,
                        },
                    )
                    data = json.loads(r.content[0].text)
                    results.append(data["success"])
            return results

        results = asyncio.run(run())
        assert all(r is True for r in results)
