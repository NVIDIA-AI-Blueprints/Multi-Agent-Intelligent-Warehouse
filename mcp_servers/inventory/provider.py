# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
InventoryProvider — vendor-neutral connector boundary.

This Protocol is the extension point for all inventory backends:

    MAIWInventoryAdapter   — wraps existing InventoryQueries + SQLRetriever
    (future) SAPEWMAdapter — wraps SAP EWM REST API
    (future) ManhattanAdapter
    (future) MockInventoryProvider — in-memory, for tests

The MCP server depends only on this Protocol.  It never knows which
backend is active.

The same contract (InventoryLookupRequest → InventoryLookupResult) is used
by the skill, the server, and all adapters.  No backend semantics leak out.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from maiw_mcp.contracts.inventory import InventoryLookupRequest, InventoryLookupResult


@runtime_checkable
class InventoryProvider(Protocol):
    """
    Vendor-neutral inventory data source.

    Any object implementing this interface can be registered as the backend
    for the MAIW Inventory MCP Server.
    """

    async def get_inventory(
        self, request: InventoryLookupRequest
    ) -> InventoryLookupResult:
        """
        Return current inventory state for a SKU.

        Raises
        ------
        maiw_mcp.errors.BackendUnavailable
            SKU not found or backend unreachable.
        """
        ...


class MockInventoryProvider:
    """
    Simple in-memory provider for development and testing.

    Accepts a dict of ``sku → InventoryLookupResult``.  Missing SKUs return
    a synthetic result.  Never raises ``BackendUnavailable``.
    """

    def __init__(
        self,
        data: dict[str, InventoryLookupResult] | None = None,
    ) -> None:
        self._data: dict[str, InventoryLookupResult] = data or {}

    def add(self, result: InventoryLookupResult) -> None:
        self._data[result.sku] = result

    async def get_inventory(self, request: InventoryLookupRequest) -> InventoryLookupResult:
        from maiw_mcp.testing.fixtures import make_inventory_result

        if request.sku in self._data:
            return self._data[request.sku]

        return make_inventory_result(
            sku=request.sku,
            warehouse_id=request.warehouse_id,
            source="mock",
        )
