# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW Inventory MCP Server — official MCP Python SDK v2 (mcp 2.0.0).

MCP protocol version: 2026-07-28

Exposes vendor-neutral warehouse inventory capabilities as MCP tools:

    warehouse.inventory.get     — get stock levels for a SKU
    warehouse.inventory.locate  — locate a SKU across warehouse zones

Architecture
------------
    MCP Client (MAIWMCPClient using mcp.client.Client)
      ↓ [Streamable HTTP or in-memory transport]
    MCPServer (this file)
      ↓
    InventoryProvider (configurable backend)
      ↓
    MAIWInventoryAdapter → InventoryQueries → PostgreSQL
    OR  MockInventoryProvider (for testing)

Running
-------
    # Development (stdio)
    python -m mcp_servers.inventory.server

    # Production (Streamable HTTP, stateless mode for K8s horizontal scaling)
    MAIW_MCP_TRANSPORT=streamable-http MAIW_MCP_INVENTORY_PORT=8765 \\
        python -m mcp_servers.inventory.server

    # In tests — use Client(mcp_server) for in-memory transport (no network)
    async with Client(mcp_server) as client:
        result = await client.call_tool("warehouse.inventory.get", {"sku": "SKU-001"})
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from mcp.server import MCPServer

from maiw_mcp.contracts.inventory import (
    INVENTORY_GET_METADATA,
    INVENTORY_LOCATE_METADATA,
    InventoryLookupRequest,
)
from maiw_mcp.errors import BackendUnavailable

logger = logging.getLogger(__name__)

# ── Server instance ───────────────────────────────────────────────────────────

mcp_server = MCPServer(
    "MAIW Inventory Server",
    instructions=(
        "Provides vendor-neutral warehouse inventory capabilities. "
        "Use warehouse.inventory.get to look up stock levels for a SKU. "
        "Use warehouse.inventory.locate to find all locations holding a SKU."
    ),
)

# ── Provider registry ─────────────────────────────────────────────────────────

_provider = None  # type: Any  # InventoryProvider | None


def configure_server(provider: Any) -> None:
    """
    Set the backend provider used by this server.

    Must be called before the first tool invocation.
    In production, called once at startup with MAIWInventoryAdapter.
    In tests, called with MockInventoryProvider.
    """
    global _provider
    _provider = provider
    logger.info(
        "InventoryMCPServer: configured with provider %s",
        type(provider).__name__,
    )


def _get_provider() -> Any:
    """Return the configured provider, lazily initialising the MAIW backend if needed."""
    global _provider
    if _provider is None:
        _provider = _build_default_provider()
    return _provider


def _build_default_provider() -> Any:
    """Build the default MAIW backend provider (requires DB access)."""
    from mcp_servers.inventory.adapters.maiw_backend import MAIWInventoryAdapter
    from src.retrieval.structured.inventory_queries import InventoryQueries
    from src.retrieval.structured.sql_retriever import SQLRetriever

    sql = SQLRetriever()
    queries = InventoryQueries(sql)
    logger.info("InventoryMCPServer: using MAIWInventoryAdapter (PostgreSQL backend)")
    return MAIWInventoryAdapter(queries)


# ── Tools ─────────────────────────────────────────────────────────────────────


@mcp_server.tool(
    name=INVENTORY_GET_METADATA.name,
    description=INVENTORY_GET_METADATA.description,
)
async def warehouse_inventory_get(
    sku: str,
    warehouse_id: str = "default",
    location: str | None = None,
) -> str:
    """
    Get current inventory levels for a SKU.

    Returns a JSON object with ``sku``, ``name``, ``locations``,
    ``total_available``, ``is_low_stock``, ``observed_at``, and ``source``.
    """
    try:
        request = InventoryLookupRequest(
            warehouse_id=warehouse_id,
            sku=sku,
            location=location,
        )
    except Exception as exc:
        error_resp = {"error": f"Invalid request: {exc}", "sku": sku}
        return json.dumps(error_resp)

    provider = _get_provider()
    try:
        result = await provider.get_inventory(request)
    except BackendUnavailable as exc:
        logger.warning("warehouse.inventory.get: BackendUnavailable for SKU=%s: %s", sku, exc)
        raise  # MCPServer converts unhandled exceptions to is_error=True

    return json.dumps(result.model_dump(mode="json"), default=str)


@mcp_server.tool(
    name=INVENTORY_LOCATE_METADATA.name,
    description=INVENTORY_LOCATE_METADATA.description,
)
async def warehouse_inventory_locate(
    sku: str,
    warehouse_id: str = "default",
) -> str:
    """
    Locate a SKU across all warehouse zones.

    Returns the same JSON format as ``warehouse.inventory.get`` but with all
    locations included (no location filter).
    """
    try:
        request = InventoryLookupRequest(
            warehouse_id=warehouse_id,
            sku=sku,
            location=None,
        )
    except Exception as exc:
        error_resp = {"error": f"Invalid request: {exc}", "sku": sku}
        return json.dumps(error_resp)

    provider = _get_provider()
    try:
        result = await provider.get_inventory(request)
    except BackendUnavailable as exc:
        logger.warning("warehouse.inventory.locate: BackendUnavailable for SKU=%s: %s", sku, exc)
        raise

    return json.dumps(result.model_dump(mode="json"), default=str)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    transport = os.getenv("MAIW_MCP_TRANSPORT", "stdio")
    port = int(os.getenv("MAIW_MCP_INVENTORY_PORT", "8765"))
    host = os.getenv("MAIW_MCP_INVENTORY_HOST", "0.0.0.0")

    if transport == "streamable-http":
        # stateless_http=True: no session affinity required — supports K8s horizontal scaling
        mcp_server.run("streamable-http", host=host, port=port, stateless_http=True)
    elif transport == "sse":
        mcp_server.run("sse", host=host, port=port)
    else:
        mcp_server.run("stdio")
