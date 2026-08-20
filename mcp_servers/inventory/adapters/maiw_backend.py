# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW Backend Adapter — wraps the existing InventoryQueries + SQLRetriever.

This is the connector between the vendor-neutral MCP server and the MAIW
PostgreSQL inventory backend.  It reuses the existing business logic entirely;
no new inventory implementation is introduced.

Runtime path
------------
    MCP tool (warehouse.inventory.get)
        ↓
    MAIWInventoryAdapter.get_inventory()
        ↓
    InventoryQueries.get_item_by_sku()  ← existing MAIW code, unchanged
        ↓
    SQLRetriever.execute_query()
        ↓
    PostgreSQL inventory_items table
"""

from __future__ import annotations

import logging
from datetime import datetime

from maiw_mcp.contracts.inventory import (
    InventoryLocation,
    InventoryLookupRequest,
    InventoryLookupResult,
)
from maiw_mcp.errors import BackendUnavailable

logger = logging.getLogger(__name__)


class MAIWInventoryAdapter:
    """
    Adapts existing ``InventoryQueries`` to the ``InventoryProvider`` Protocol.

    Parameters
    ----------
    queries:
        An initialised ``InventoryQueries`` instance.  The adapter does not
        call ``sql_retriever.initialize()`` — the caller is responsible.
    """

    def __init__(self, queries: object) -> None:
        self._queries = queries

    async def get_inventory(
        self, request: InventoryLookupRequest
    ) -> InventoryLookupResult:
        """
        Look up a SKU via the existing MAIW SQL backend.

        Raises
        ------
        BackendUnavailable
            SKU is not found in the inventory_items table, or the SQL query fails.
        """
        try:
            item = await self._queries.get_item_by_sku(request.sku)
        except Exception as exc:
            logger.error(
                "MAIWInventoryAdapter: SQL error for SKU=%s: %s",
                request.sku,
                exc,
            )
            raise BackendUnavailable(
                f"Inventory backend error for SKU {request.sku!r}: {exc}"
            ) from exc

        if item is None:
            raise BackendUnavailable(
                f"SKU {request.sku!r} not found in warehouse {request.warehouse_id!r}"
            )

        # Apply location filter if requested
        item_location = item.location or "UNKNOWN"
        if request.location and item_location != request.location:
            raise BackendUnavailable(
                f"SKU {request.sku!r} not found at location {request.location!r}"
            )

        location = InventoryLocation(
            location_id=item_location,
            quantity_available=item.quantity,
            quantity_reserved=0,
            reorder_point=item.reorder_point,
        )

        observed_at = _parse_datetime(item.updated_at)

        return InventoryLookupResult(
            warehouse_id=request.warehouse_id,
            sku=item.sku,
            name=item.name,
            locations=[location],
            total_available=item.quantity,
            is_low_stock=item.quantity <= item.reorder_point,
            observed_at=observed_at,
            source="maiw-backend",
        )


def _parse_datetime(value: object) -> datetime:
    """Parse updated_at from InventoryItem (str or datetime or None)."""
    if value is None:
        return datetime.utcnow()
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return datetime.utcnow()
