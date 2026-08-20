# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Shared test fixtures for inventory capability tests.
"""

from __future__ import annotations

from datetime import datetime

from maiw_mcp.contracts.inventory import InventoryLocation, InventoryLookupResult


def make_inventory_result(
    sku: str = "SKU-001",
    name: str = "Test Widget",
    quantity: int = 100,
    location_id: str = "A-01-03",
    reorder_point: int = 10,
    warehouse_id: str = "default",
    source: str = "mock",
) -> InventoryLookupResult:
    """Build a deterministic InventoryLookupResult for use in tests."""
    loc = InventoryLocation(
        location_id=location_id,
        quantity_available=quantity,
        quantity_reserved=0,
        reorder_point=reorder_point,
    )
    return InventoryLookupResult(
        warehouse_id=warehouse_id,
        sku=sku,
        name=name,
        locations=[loc],
        total_available=quantity,
        is_low_stock=quantity <= reorder_point,
        observed_at=datetime(2026, 8, 20, 12, 0, 0),
        source=source,
    )
