# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MCP Protocol Conformance Tests — MAIW Inventory Server (MCP SDK v2).

MCP protocol version: 2026-07-28
MCP SDK version: 2.x (tested against 2.1.1+)

These tests exercise the REAL MCP protocol path using the official v2 in-memory
transport.  No network is required.  ``mcp.client.Client(server_instance)``
replaces the v1 ``create_connected_server_and_client_session`` utility and runs
the full MCP 2026-07-28 initialize → tools/list → tools/call sequence.

MCP v1 → v2 changes in this file
----------------------------------
- ``create_connected_server_and_client_session(server)`` →
  ``async with Client(server) as client:``
- ``result.isError`` → ``result.is_error``
- ``tool.inputSchema`` → ``tool.input_schema``
- FastMCP server → MCPServer (in _get_configured_server)
- Added: TestMCPStatelessBehavior — proves no sticky-session assumption
- Added: TestMCPV2Protocol — SDK/protocol version assertions

Every test here proves a MCP protocol property, not just a Python function call.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from maiw_mcp.contracts.inventory import InventoryLookupRequest
from maiw_mcp.errors import BackendUnavailable
from maiw_mcp.testing.conformance import run_inventory_conformance
from maiw_mcp.testing.mock_server import MockInventoryServer
from maiw_mcp.testing.fixtures import make_inventory_result
from mcp.client import Client

# ── Helpers ────────────────────────────────────────────────────────────────────


def _get_configured_server():
    """Return the real MAIW inventory MCP server with a mock provider (no DB needed)."""
    from mcp_servers.inventory.server import mcp_server, configure_server
    from mcp_servers.inventory.provider import MockInventoryProvider

    configure_server(MockInventoryProvider())
    return mcp_server


# ── Protocol: MCP v2 version assertions ───────────────────────────────────────


class TestMCPV2Protocol:
    """Verify the MAIW stack uses MCP SDK v2 / protocol 2026-07-28."""

    def test_mcp_sdk_version_is_v2(self):
        from importlib.metadata import version

        sdk_ver = version("mcp")
        major = int(sdk_ver.split(".")[0])
        assert major >= 2, f"Expected MCP SDK v2+, got {sdk_ver}"

    def test_protocol_version_is_2026(self):
        from mcp.types import LATEST_PROTOCOL_VERSION

        assert (
            "2026" in LATEST_PROTOCOL_VERSION
        ), f"Expected 2026-07-28 protocol, got {LATEST_PROTOCOL_VERSION}"

    def test_mcp_server_import_from_v2_path(self):
        from mcp.server import MCPServer

        assert MCPServer is not None

    def test_fastmcp_not_importable(self):
        """FastMCP was removed in v2; confirm MAIW does not depend on it."""
        with pytest.raises(ImportError):
            from mcp.server.fastmcp import FastMCP  # noqa: F401

    def test_telemetry_records_sdk_version(self):
        from maiw_mcp.telemetry.telemetry import CapabilityCallRecord, _MCP_SDK_VERSION

        record = CapabilityCallRecord(
            trace_id=None,
            capability_name="warehouse.inventory.get",
            capability_version=1,
            mcp_server="http://test",
            transport="in-memory",
            latency_ms=1.0,
            success=True,
            backend=None,
            error_class=None,
            error_message=None,
        )
        assert record.mcp_sdk_version == _MCP_SDK_VERSION
        assert record.mcp_sdk_version.startswith("2."), record.mcp_sdk_version

    def test_telemetry_records_protocol_version(self):
        from maiw_mcp.telemetry.telemetry import CapabilityCallRecord

        record = CapabilityCallRecord(
            trace_id=None,
            capability_name="warehouse.inventory.get",
            capability_version=1,
            mcp_server="http://test",
            transport="in-memory",
            latency_ms=1.0,
            success=True,
            backend=None,
            error_class=None,
            error_message=None,
        )
        assert record.mcp_protocol_version == "2026-07-28"


# ── Protocol: server initializes ──────────────────────────────────────────────


class TestMCPServerInitialization:
    def test_server_creates_without_error(self):
        server = _get_configured_server()
        assert server is not None

    def test_server_has_name(self):
        server = _get_configured_server()
        assert "Inventory" in server.name

    def test_in_memory_client_connects(self):
        """Full MCP initialize handshake via Client in-memory transport."""
        server = _get_configured_server()

        async def run():
            async with Client(server) as client:
                return client.server_info

        info = asyncio.run(run())
        assert info is not None
        assert "Inventory" in info.name


# ── Protocol: tool discovery ───────────────────────────────────────────────────


class TestMCPToolDiscovery:
    def test_tools_list_returns_inventory_get(self):
        server = _get_configured_server()

        async def run():
            async with Client(server) as client:
                tools = await client.list_tools()
                return [t.name for t in tools.tools]

        tool_names = asyncio.run(run())
        assert (
            "warehouse.inventory.get" in tool_names
        ), f"Expected 'warehouse.inventory.get' in {tool_names}"

    def test_tools_list_returns_inventory_locate(self):
        server = _get_configured_server()

        async def run():
            async with Client(server) as client:
                tools = await client.list_tools()
                return [t.name for t in tools.tools]

        tool_names = asyncio.run(run())
        assert "warehouse.inventory.locate" in tool_names

    def test_inventory_get_has_sku_in_schema(self):
        server = _get_configured_server()

        async def run():
            async with Client(server) as client:
                tools = await client.list_tools()
                return next(
                    (t for t in tools.tools if t.name == "warehouse.inventory.get"),
                    None,
                )

        tool = asyncio.run(run())
        assert tool is not None
        # v2: input_schema (snake_case), not inputSchema (camelCase)
        props = tool.input_schema.get("properties", {})
        assert (
            "sku" in props
        ), f"'sku' not in input_schema.properties: {list(props.keys())}"

    def test_inventory_get_has_description(self):
        server = _get_configured_server()

        async def run():
            async with Client(server) as client:
                tools = await client.list_tools()
                return next(
                    (t for t in tools.tools if t.name == "warehouse.inventory.get"),
                    None,
                )

        tool = asyncio.run(run())
        assert tool is not None
        assert tool.description and len(tool.description) > 0


# ── Protocol: valid tool calls ────────────────────────────────────────────────


class TestMCPInventoryGetTool:
    def test_valid_request_returns_success(self):
        server = _get_configured_server()

        async def run():
            async with Client(server) as client:
                return await client.call_tool(
                    "warehouse.inventory.get",
                    {"sku": "SKU-001", "warehouse_id": "default"},
                )

        result = asyncio.run(run())
        # v2: is_error (snake_case), not isError
        assert not result.is_error, f"is_error=True: {result.content}"

    def test_valid_request_returns_json(self):
        server = _get_configured_server()

        async def run():
            async with Client(server) as client:
                result = await client.call_tool(
                    "warehouse.inventory.get",
                    {"sku": "SKU-001"},
                )
                text = result.content[0].text
                return json.loads(text)

        data = asyncio.run(run())
        assert isinstance(data, dict)
        assert "sku" in data
        assert data["sku"] == "SKU-001"

    def test_result_has_required_fields(self):
        server = _get_configured_server()

        async def run():
            async with Client(server) as client:
                result = await client.call_tool(
                    "warehouse.inventory.get",
                    {"sku": "TEST-SKU"},
                )
                return json.loads(result.content[0].text)

        data = asyncio.run(run())
        required = {
            "sku",
            "name",
            "locations",
            "total_available",
            "is_low_stock",
            "source",
        }
        missing = required - set(data.keys())
        assert not missing, f"Missing required fields: {missing}"

    def test_result_source_is_set(self):
        server = _get_configured_server()

        async def run():
            async with Client(server) as client:
                result = await client.call_tool(
                    "warehouse.inventory.get",
                    {"sku": "SKU-001"},
                )
                return json.loads(result.content[0].text)

        data = asyncio.run(run())
        assert data.get("source"), "source field must be non-empty"

    def test_result_locations_is_list(self):
        server = _get_configured_server()

        async def run():
            async with Client(server) as client:
                result = await client.call_tool(
                    "warehouse.inventory.get",
                    {"sku": "SKU-001"},
                )
                return json.loads(result.content[0].text)

        data = asyncio.run(run())
        assert isinstance(data.get("locations"), list)

    def test_configured_sku_returns_configured_data(self):
        """Server uses configured provider data — not a default fixture."""
        from mcp_servers.inventory.server import mcp_server, configure_server
        from mcp_servers.inventory.provider import MockInventoryProvider

        fixture = make_inventory_result(sku="SPECIAL-SKU", quantity=999)
        provider = MockInventoryProvider(data={"SPECIAL-SKU": fixture})
        configure_server(provider)

        async def run():
            async with Client(mcp_server) as client:
                result = await client.call_tool(
                    "warehouse.inventory.get",
                    {"sku": "SPECIAL-SKU"},
                )
                return json.loads(result.content[0].text)

        data = asyncio.run(run())
        assert data["total_available"] == 999

    def test_locate_tool_returns_success(self):
        server = _get_configured_server()

        async def run():
            async with Client(server) as client:
                return await client.call_tool(
                    "warehouse.inventory.locate",
                    {"sku": "SKU-001"},
                )

        result = asyncio.run(run())
        assert not result.is_error, f"is_error=True: {result.content}"


# ── Protocol: error handling ──────────────────────────────────────────────────


class TestMCPErrorHandling:
    def test_backend_unavailable_propagates_as_tool_error(self):
        """BackendUnavailable from the provider surfaces as MCP tool error (is_error=True)."""
        from mcp_servers.inventory.server import mcp_server, configure_server
        from unittest.mock import AsyncMock, MagicMock

        provider = MagicMock()
        provider.get_inventory = AsyncMock(
            side_effect=BackendUnavailable("SKU not found: MISSING-SKU")
        )
        configure_server(provider)

        async def run():
            async with Client(mcp_server) as client:
                return await client.call_tool(
                    "warehouse.inventory.get",
                    {"sku": "MISSING-SKU"},
                )

        result = asyncio.run(run())
        # v2: is_error (snake_case)
        assert (
            result.is_error is True
        ), "BackendUnavailable should produce is_error=True in CallToolResult"

    def test_empty_sku_handled_gracefully(self):
        """Server does not crash when sku is empty string."""
        server = _get_configured_server()

        async def run():
            async with Client(server) as client:
                try:
                    result = await client.call_tool(
                        "warehouse.inventory.get",
                        {"sku": ""},
                    )
                    return result
                except Exception:
                    return None

        result = asyncio.run(run())
        assert result is not None


# ── Protocol: stateless / horizontal scaling ──────────────────────────────────


class TestMCPStatelessBehavior:
    """
    Proves the MAIW MCP architecture does not depend on per-connection session state.

    Each Client(server) is an independent connection.  Two clients to the same
    MCPServer instance must return consistent, independent results — matching the
    behaviour expected when K8s routes requests to different pod instances.
    """

    def test_two_independent_clients_return_consistent_results(self):
        """Independent Client instances return the same data for the same SKU."""
        server = _get_configured_server()

        async def run():
            async with Client(server) as client1:
                r1 = await client1.call_tool(
                    "warehouse.inventory.get", {"sku": "SHARED-SKU"}
                )

            async with Client(server) as client2:
                r2 = await client2.call_tool(
                    "warehouse.inventory.get", {"sku": "SHARED-SKU"}
                )

            return r1, r2

        r1, r2 = asyncio.run(run())
        assert not r1.is_error and not r2.is_error
        d1 = json.loads(r1.content[0].text)
        d2 = json.loads(r2.content[0].text)
        assert d1["sku"] == d2["sku"] == "SHARED-SKU"

    def test_client_per_request_pattern_is_supported(self):
        """Each request can use a fresh Client — no persistent session required."""
        server = _get_configured_server()

        async def single_request(sku: str) -> dict:
            """Simulates a stateless handler: open client, call tool, close."""
            async with Client(server) as client:
                result = await client.call_tool("warehouse.inventory.get", {"sku": sku})
            return json.loads(result.content[0].text)

        async def run():
            # Three independent requests with separate Client lifetimes
            results = []
            for sku in ["SKU-A", "SKU-B", "SKU-C"]:
                results.append(await single_request(sku))
            return results

        results = asyncio.run(run())
        assert len(results) == 3
        assert [r["sku"] for r in results] == ["SKU-A", "SKU-B", "SKU-C"]

    def test_sequential_clients_do_not_share_state(self):
        """A second Client sees the server state at the time of connection, not earlier."""
        from mcp_servers.inventory.server import mcp_server, configure_server
        from mcp_servers.inventory.provider import MockInventoryProvider

        # First request: provider returns quantity 10
        configure_server(
            MockInventoryProvider(
                data={"SKU-STATE": make_inventory_result(sku="SKU-STATE", quantity=10)}
            )
        )

        async def run():
            async with Client(mcp_server) as client:
                r1 = await client.call_tool(
                    "warehouse.inventory.get", {"sku": "SKU-STATE"}
                )

            # Provider updated between requests — second client sees new state
            configure_server(
                MockInventoryProvider(
                    data={
                        "SKU-STATE": make_inventory_result(sku="SKU-STATE", quantity=99)
                    }
                )
            )

            async with Client(mcp_server) as client:
                r2 = await client.call_tool(
                    "warehouse.inventory.get", {"sku": "SKU-STATE"}
                )

            return (
                json.loads(r1.content[0].text)["total_available"],
                json.loads(r2.content[0].text)["total_available"],
            )

        qty1, qty2 = asyncio.run(run())
        assert qty1 == 10
        assert qty2 == 99


# ── Full conformance suite via testing utility ────────────────────────────────


class TestMCPConformanceSuite:
    def test_conformance_suite_passes(self):
        """Run the full MCP v2 conformance suite from maiw_mcp.testing.conformance."""
        server = _get_configured_server()

        async def run():
            return await run_inventory_conformance(server, sku="CONF-001")

        report = asyncio.run(run())
        print(f"\n{report}")
        assert report.all_passed, f"MCP conformance failures:\n{report}"


# ── MockInventoryServer tests (in-memory, no real server) ────────────────────


class TestMockInventoryServer:
    def test_mock_server_responds_to_tool_call(self):
        mock = MockInventoryServer()

        async def run():
            async with mock.client() as client:
                return await client.call_tool(
                    "warehouse.inventory.get",
                    {"sku": "SKU-001"},
                )

        result = asyncio.run(run())
        assert not result.is_error

    def test_mock_server_returns_configured_data(self):
        fixture = make_inventory_result(sku="SKU-CUSTOM", quantity=77)
        mock = MockInventoryServer(responses={"default:SKU-CUSTOM": fixture})

        async def run():
            async with mock.client() as client:
                result = await client.call_tool(
                    "warehouse.inventory.get",
                    {"sku": "SKU-CUSTOM", "warehouse_id": "default"},
                )
                return json.loads(result.content[0].text)

        data = asyncio.run(run())
        assert data["total_available"] == 77

    def test_mock_server_exposes_both_tools(self):
        mock = MockInventoryServer()

        async def run():
            async with mock.client() as client:
                tools = await client.list_tools()
                return [t.name for t in tools.tools]

        names = asyncio.run(run())
        assert "warehouse.inventory.get" in names
        assert "warehouse.inventory.locate" in names

    def test_mock_server_telemetry_transparent(self):
        """Both tools respond without error for any SKU."""
        mock = MockInventoryServer()

        async def run():
            async with mock.client() as client:
                results = []
                for capability in [
                    "warehouse.inventory.get",
                    "warehouse.inventory.locate",
                ]:
                    r = await client.call_tool(capability, {"sku": "ANY-SKU"})
                    results.append(r.is_error)
                return results

        errors = asyncio.run(run())
        assert all(not e for e in errors)

    def test_mock_server_session_alias_works(self):
        """Legacy session() alias still works for backward compatibility."""
        mock = MockInventoryServer()

        async def run():
            async with mock.session() as client:
                result = await client.call_tool(
                    "warehouse.inventory.get", {"sku": "SKU-001"}
                )
                return result

        result = asyncio.run(run())
        assert not result.is_error
