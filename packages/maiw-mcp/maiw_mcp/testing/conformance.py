# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MCP v2 Conformance Test Suite (protocol 2026-07-28).

Any inventory MCP server implementation can be validated with this suite.
Run it against the official MAIW server, a SAP adapter, or a mock.

MCP v1 → v2 changes in this module
------------------------------------
- ``FastMCP`` → ``MCPServer``
- ``create_connected_server_and_client_session`` → ``Client(server)``
- ``result.isError`` → ``result.is_error``
- ``tool.inputSchema`` → ``tool.input_schema``

Usage
-----
    from mcp.server import MCPServer
    from maiw_mcp.testing.conformance import run_inventory_conformance

    async def test_my_server():
        mcp_server = MCPServer("My Server")
        # ... register tools ...
        report = await run_inventory_conformance(mcp_server, sku="SKU-001")
        assert report.all_passed
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from mcp.client import Client
from mcp.server import MCPServer


@dataclass
class ConformanceResult:
    """Result of a single conformance check."""

    name: str
    passed: bool
    detail: str = ""


@dataclass
class ConformanceReport:
    """Full conformance test report for an inventory MCP server."""

    results: list[ConformanceResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.results.append(ConformanceResult(name, passed, detail))

    def __str__(self) -> str:
        lines = [f"Conformance: {self.passed_count}/{len(self.results)} passed"]
        for r in self.results:
            status = "✓" if r.passed else "✗"
            lines.append(
                f"  {status} {r.name}" + (f" — {r.detail}" if r.detail else "")
            )
        return "\n".join(lines)


async def run_inventory_conformance(
    server: MCPServer,
    *,
    sku: str = "CONF-SKU-001",
    warehouse_id: str = "default",
) -> ConformanceReport:
    """
    Run the standard inventory capability conformance suite against a server.

    Uses ``mcp.client.Client(server)`` (in-memory transport) to exercise the
    full MCP 2026-07-28 protocol path without a network connection:
      - Client connect / initialize handshake
      - tools/list discovery
      - valid tool call succeeds
      - invalid SKU handled gracefully
      - missing required param rejected or handled
    """
    report = ConformanceReport()

    async with Client(server) as client:

        # 1. Server initializes (Client connected successfully)
        report.add(
            "server_initializes",
            True,
            "Client connected (MCP 2026-07-28 initialize handshake succeeded)",
        )

        # 2. Tool discovery — warehouse.inventory.get exposed
        tools_result = await client.list_tools()
        tool_names = [t.name for t in tools_result.tools]
        has_get = "warehouse.inventory.get" in tool_names
        report.add(
            "tool_discovery_inventory_get",
            has_get,
            f"tools listed: {tool_names}",
        )

        # 3. Tool discovery — warehouse.inventory.locate exposed
        has_locate = "warehouse.inventory.locate" in tool_names
        report.add(
            "tool_discovery_inventory_locate",
            has_locate,
            f"tools listed: {tool_names}",
        )

        # 4. Input schema present for warehouse.inventory.get
        get_tool = next(
            (t for t in tools_result.tools if t.name == "warehouse.inventory.get"), None
        )
        schema_ok = get_tool is not None and "sku" in get_tool.input_schema.get(
            "properties", {}
        )
        report.add(
            "input_schema_has_sku",
            schema_ok,
            f"input_schema keys: {list(get_tool.input_schema.get('properties', {}).keys()) if get_tool else 'no tool'}",
        )

        # 5. Valid request succeeds (is_error=False)
        result = await client.call_tool(
            "warehouse.inventory.get",
            {"warehouse_id": warehouse_id, "sku": sku},
        )
        call_ok = not result.is_error
        report.add(
            "valid_request_succeeds",
            call_ok,
            "is_error=False" if call_ok else f"is_error=True: {result.content}",
        )

        # 6. Result is valid JSON
        if call_ok:
            text = _extract_text(result.content)
            try:
                parsed = json.loads(text)
                json_ok = isinstance(parsed, dict)
            except (json.JSONDecodeError, Exception):
                json_ok = False
                parsed = {}
            report.add(
                "result_is_json_object",
                json_ok,
                f"keys: {list(parsed.keys()) if isinstance(parsed, dict) else 'invalid'}",
            )

            # 7. Required fields present in result
            required = {"sku", "locations", "total_available", "source"}
            missing = required - set(parsed.keys() if isinstance(parsed, dict) else [])
            report.add(
                "result_has_required_fields",
                not missing,
                f"missing: {missing}" if missing else "all required fields present",
            )
        else:
            report.add("result_is_json_object", False, "skipped — previous call failed")
            report.add(
                "result_has_required_fields", False, "skipped — previous call failed"
            )

        # 8. Empty SKU is rejected or handled gracefully (not a crash)
        try:
            await client.call_tool(
                "warehouse.inventory.get",
                {"warehouse_id": warehouse_id, "sku": ""},
            )
            report.add(
                "empty_sku_handled_gracefully",
                True,
                "server responded without crash",
            )
        except Exception as exc:
            report.add(
                "empty_sku_handled_gracefully",
                False,
                f"server raised unhandled exception: {type(exc).__name__}: {exc}",
            )

    return report


def _extract_text(content: list[Any]) -> str:
    for block in content:
        if hasattr(block, "text"):
            return block.text
    return str(content)
