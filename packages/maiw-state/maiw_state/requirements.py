# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
StateRequirements — selective state assembly specification.

Agents declare exactly which state components they need.  The
WarehouseStateProvider assembles only what is requested, avoiding
unnecessary capability calls.

Example
-------
    # Equipment agent needs equipment context only
    req = StateRequirements(equipment=True)

    # Operations agent needs both for cross-domain reasoning
    req = StateRequirements(
        inventory=True,
        inventory_sku="SKU-001",
        equipment=True,
        equipment_type="forklift",
    )
"""

from __future__ import annotations

from pydantic import BaseModel, Field

_DEFAULT_STALE_MS = 30_000  # 30 seconds


class StateRequirements(BaseModel):
    """
    Specification of which state components the caller needs.

    Fields
    ------
    inventory:
        Whether to populate InventoryState.
    inventory_sku:
        Specific SKU to fetch; None means any/all available.
    inventory_warehouse_id:
        Warehouse ID for inventory lookup (defaults to "default").
    equipment:
        Whether to populate EquipmentState.
    equipment_asset_id:
        Specific asset to fetch; None means the full fleet.
    equipment_type:
        Filter equipment by type (e.g. "forklift", "amr").
    equipment_zone:
        Filter equipment by zone.
    equipment_status_filter:
        Filter by status (e.g. "available").
    max_age_ms:
        Maximum acceptable age for state components in milliseconds.
        Components older than this will be flagged as stale.
    """

    inventory: bool = False
    inventory_sku: str | None = None
    inventory_warehouse_id: str = "default"

    equipment: bool = False
    equipment_asset_id: str | None = None
    equipment_type: str | None = None
    equipment_zone: str | None = None
    equipment_status_filter: str | None = None

    labor: bool = False
    labor_zone: str | None = None
    labor_shift: str | None = None
    labor_status_filter: str = "active"

    waves: bool = False
    waves_zone: str | None = None
    waves_status_filter: str | None = None
    waves_task_type: str | None = None

    max_age_ms: int = Field(
        default=_DEFAULT_STALE_MS,
        ge=0,
        description="Staleness threshold applied to all populated components",
    )
