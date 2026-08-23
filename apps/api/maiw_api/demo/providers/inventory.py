# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
SimulationInventoryProvider — implements InventoryProvider against DemoWarehouseWorld.

Reads inventory state from the shared world.  There are no write operations in
the inventory domain contract; write mutations (e.g. adjustments injected via
/demo/inject) are applied directly to the world by DemoScenarioController.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from maiw_mcp.contracts.inventory import (
    InventoryLocation,
    InventoryLookupRequest,
    InventoryLookupResult,
)
from maiw_mcp.errors import BackendUnavailable

if TYPE_CHECKING:
    from maiw_api.demo.world import DemoWarehouseWorld


class SimulationInventoryProvider:
    """Implements InventoryProvider against the shared DemoWarehouseWorld."""

    def __init__(self, world: "DemoWarehouseWorld") -> None:
        self._world = world

    async def get_inventory(
        self, request: InventoryLookupRequest
    ) -> InventoryLookupResult:
        item = self._world.inventory.get(request.sku)
        if item is None:
            raise BackendUnavailable(
                f"SKU '{request.sku}' not found in simulation world"
            )
        if request.location and item.location_id != request.location:
            raise BackendUnavailable(
                f"SKU '{request.sku}' not at location '{request.location}' in simulation"
            )
        location = InventoryLocation(
            location_id=item.location_id,
            quantity_available=item.quantity_available,
            quantity_reserved=item.quantity_reserved,
            reorder_point=item.reorder_point,
        )
        return InventoryLookupResult(
            warehouse_id=self._world.WAREHOUSE_ID,
            sku=item.sku,
            name=item.name,
            locations=[location],
            total_available=item.quantity_available,
            is_low_stock=item.is_low_stock,
            observed_at=self._world.clock.now(),
            source=self._world.SOURCE,
        )
