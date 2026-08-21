# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
InventoryState — projected operational inventory context.

``InventoryState`` is NOT a raw database mirror.  It contains the fields
relevant for agent reasoning and DecisionEngine evaluation:

    - Which SKUs are in scope and their availability
    - Whether any SKU is at low-stock threshold
    - Freshness of the data

The ``WarehouseStateProvider`` populates this by calling
``InventoryLookupSkill`` and projecting the result.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from maiw_state.freshness import StateFreshness


class InventoryItemSummary(BaseModel):
    """Operational summary for a single inventory SKU."""

    sku: str
    name: str
    total_available: int = Field(ge=0)
    is_low_stock: bool
    location_count: int = Field(ge=0, description="Number of locations holding this SKU")


class InventoryState(BaseModel):
    """
    Operational inventory snapshot for a warehouse.

    Represents what the agent knows about inventory at a point in time.
    Populated through ``warehouse.inventory.get`` capability calls.
    """

    warehouse_id: str
    items: list[InventoryItemSummary] = Field(default_factory=list)
    total_items: int = Field(ge=0, default=0)
    low_stock_count: int = Field(
        ge=0,
        default=0,
        description="Number of SKUs at or below reorder point",
    )
    freshness: StateFreshness

    @classmethod
    def from_lookup_result(
        cls,
        warehouse_id: str,
        result: object,  # InventoryLookupResult — duck-typed to avoid circular dep
        *,
        freshness: StateFreshness,
    ) -> InventoryState:
        """
        Project an ``InventoryLookupResult`` into ``InventoryState``.

        Accepts any object with .sku, .name, .total_available, .is_low_stock,
        and .locations attributes (structural duck-typing).
        """
        item = InventoryItemSummary(
            sku=result.sku,
            name=result.name,
            total_available=result.total_available,
            is_low_stock=result.is_low_stock,
            location_count=len(result.locations),
        )
        return cls(
            warehouse_id=warehouse_id,
            items=[item],
            total_items=1,
            low_stock_count=1 if result.is_low_stock else 0,
            freshness=freshness,
        )
