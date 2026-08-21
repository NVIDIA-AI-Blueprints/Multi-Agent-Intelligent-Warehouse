# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
In-process mock MCP server for testing agents and skills (MCP SDK v2).

Uses the official MCP v2 ``Client(server_instance)`` in-memory transport.
Exercises the full MCP protocol path: initialize → tools/list → tools/call.

MCP v1 → v2 changes in this module
------------------------------------
- ``FastMCP`` removed; replaced with ``MCPServer``
- ``create_connected_server_and_client_session(server)`` removed;
  replaced with ``Client(server)`` which handles the same in-memory path
- Session context manager now yields ``Client`` not ``ClientSession``
- ``result.isError`` → ``result.is_error``

Usage in tests
--------------
    from maiw_mcp.testing.mock_server import MockInventoryServer
    from maiw_mcp.contracts.inventory import InventoryLookupRequest

    mock = MockInventoryServer()

    async def test_something():
        async with mock.client() as client:
            result = await client.call_tool(
                "warehouse.inventory.get",
                {"warehouse_id": "default", "sku": "SKU-001"},
            )
            assert not result.is_error
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Any

from mcp.client import Client
from mcp.server import MCPServer

from maiw_mcp.contracts.inventory import InventoryLookupResult
from maiw_mcp.testing.fixtures import make_inventory_result


class MockInventoryServer:
    """
    In-process mock inventory MCP server.

    Provides configurable responses for ``warehouse.inventory.get`` and
    ``warehouse.inventory.locate`` without connecting to any database.

    Parameters
    ----------
    responses:
        Maps ``"{warehouse_id}:{sku}"`` keys to ``InventoryLookupResult``
        objects (or plain dicts).  Keys not present use the default fixture.
    """

    def __init__(
        self,
        responses: dict[str, InventoryLookupResult | dict[str, Any]] | None = None,
    ) -> None:
        self._responses: dict[str, dict[str, Any]] = {}
        for key, val in (responses or {}).items():
            if isinstance(val, InventoryLookupResult):
                self._responses[key] = val.model_dump(mode="json")
            else:
                self._responses[key] = val

        self._mcp = MCPServer("Mock MAIW Inventory Server")
        self._register_tools()

    def _register_tools(self) -> None:
        responses = self._responses

        @self._mcp.tool(name="warehouse.inventory.get")
        async def inventory_get(
            warehouse_id: str = "default",
            sku: str = "",
            location: str | None = None,
        ) -> str:
            """Get current inventory for a SKU (mock)."""
            key = f"{warehouse_id}:{sku}"
            if key in responses:
                data = responses[key]
            else:
                data = make_inventory_result(
                    sku=sku, warehouse_id=warehouse_id, source="mock"
                ).model_dump(mode="json")
            return json.dumps(data, default=str)

        @self._mcp.tool(name="warehouse.inventory.locate")
        async def inventory_locate(
            warehouse_id: str = "default",
            sku: str = "",
        ) -> str:
            """Locate a SKU across warehouse zones (mock)."""
            key = f"{warehouse_id}:{sku}"
            if key in responses:
                data = responses[key]
            else:
                data = make_inventory_result(
                    sku=sku, warehouse_id=warehouse_id, source="mock"
                ).model_dump(mode="json")
            return json.dumps(data, default=str)

    @property
    def server(self) -> MCPServer:
        """Expose the underlying MCPServer for direct Client(server) usage in tests."""
        return self._mcp

    @asynccontextmanager
    async def client(self) -> AsyncGenerator[Client, None]:
        """
        Return a connected MCP v2 Client using the official in-memory transport.

        Yields a ``mcp.client.Client`` connected to this mock server via
        in-memory transport.  The Client lifecycle is managed by the context
        manager — no manual initialization or teardown needed.

        Replaces the v1 ``session()`` method which yielded ``ClientSession``
        via ``create_connected_server_and_client_session``.
        """
        async with Client(self._mcp) as mcp_client:
            yield mcp_client

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[Client, None]:
        """Backward-compatible alias for ``client()``.  Use ``client()`` in new code."""
        async with self.client() as c:
            yield c
