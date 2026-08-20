# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Vendor-neutral inventory capability contracts.

These types are independent of:
  - SAP EWM
  - Manhattan Associates WMS
  - Blue Yonder
  - The MAIW database schema
  - Any specific backend implementation

Agents and skills depend only on these types.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .common import CapabilityMetadata


# ── Requests ──────────────────────────────────────────────────────────────────


class InventoryLookupRequest(BaseModel):
    """
    Request to get current inventory levels for a SKU.

    ``warehouse_id`` defaults to ``"default"`` so single-warehouse deployments
    do not need to specify it.  Multi-warehouse deployments must provide it.
    """

    warehouse_id: str = Field(default="default", description="Warehouse identifier")
    sku: str = Field(..., min_length=1, description="Stock-keeping unit identifier")
    location: str | None = Field(
        default=None,
        description="Filter to a specific location code; None returns all locations",
    )


class InventoryLocateRequest(BaseModel):
    """Request to locate a SKU across all warehouse zones."""

    warehouse_id: str = Field(default="default", description="Warehouse identifier")
    sku: str = Field(..., min_length=1, description="Stock-keeping unit identifier")


# ── Result fragments ───────────────────────────────────────────────────────────


class InventoryLocation(BaseModel):
    """Inventory at a single physical location."""

    location_id: str = Field(..., description="Location code, e.g. 'A-01-03'")
    quantity_available: int = Field(..., ge=0)
    quantity_reserved: int = Field(default=0, ge=0)
    reorder_point: int = Field(..., ge=0, description="Replenishment trigger threshold")

    @property
    def quantity_on_hand(self) -> int:
        return self.quantity_available + self.quantity_reserved


# ── Results ────────────────────────────────────────────────────────────────────


class InventoryLookupResult(BaseModel):
    """
    Current inventory state for a SKU.

    ``source`` identifies the backend that served the data so callers can
    reason about data freshness and provenance without inspecting internals.
    """

    warehouse_id: str
    sku: str
    name: str = Field(description="Human-readable item name")
    locations: list[InventoryLocation]
    total_available: int = Field(ge=0, description="Sum of available quantity across all locations")
    is_low_stock: bool = Field(description="True when any location is at or below reorder_point")
    observed_at: datetime = Field(description="When this data was last updated in the source system")
    source: str = Field(
        description="Backend identifier: 'maiw-backend', 'sap-ewm', 'manhattan', 'mock', …"
    )


# ── Capability metadata ────────────────────────────────────────────────────────

INVENTORY_GET_METADATA = CapabilityMetadata(
    name="warehouse.inventory.get",
    version=1,
    domain="inventory",
    side_effect="read",
    risk="low",
    idempotent=True,
    timeout_seconds=10,
    required_permission="inventory:read",
    description=(
        "Get current inventory levels for a SKU across all warehouse locations. "
        "Returns quantity available, quantity reserved, reorder point, and low-stock flag."
    ),
)

INVENTORY_LOCATE_METADATA = CapabilityMetadata(
    name="warehouse.inventory.locate",
    version=1,
    domain="inventory",
    side_effect="read",
    risk="low",
    idempotent=True,
    timeout_seconds=10,
    required_permission="inventory:read",
    description=(
        "Locate a SKU across all warehouse zones and return a ranked list of "
        "locations ordered by quantity descending."
    ),
)
