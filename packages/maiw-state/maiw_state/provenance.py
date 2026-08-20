# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
StateProvenance — tracks where each state component came from.

Provenance lets agents (and the DecisionEngine) distinguish what they know
and where it came from, without understanding backend implementation:

    inventory
      → capability:  warehouse.inventory.get
      → server:      MAIW Inventory Server
      → provider:    maiw-backend (MAIWInventoryAdapter → PostgreSQL)

    equipment
      → capability:  warehouse.equipment.get_status
      → server:      MAIW Equipment Server
      → provider:    maiw-backend (MAIWEquipmentAdapter → EquipmentAssetTools)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class StateSource(str, Enum):
    """Where the state component data originated."""

    MCP = "mcp"           # via official MCP v2 capability
    DIRECT_DB = "direct_db"  # future: direct SQL (fallback path)
    CACHE = "cache"        # future: in-memory/Redis cache
    MOCK = "mock"          # test/development mock


class StateProvenance(BaseModel):
    """
    Lineage record for a single state component.

    One ``StateProvenance`` entry per state component assembled into a
    ``WarehouseStateSnapshot``.  Multiple entries when a snapshot combines
    data from several capability calls.
    """

    domain: str = Field(
        description="Warehouse domain: 'inventory', 'equipment', 'labor', …"
    )
    capability: str = Field(
        description="MCP capability name, e.g. 'warehouse.equipment.get_status'"
    )
    server: str = Field(
        description="MCP server name, e.g. 'MAIW Equipment Server'"
    )
    provider: str = Field(
        description="Backend adapter identifier, e.g. 'maiw-backend', 'mock'"
    )
    source: StateSource = Field(
        default=StateSource.MCP,
        description="Transport layer used to retrieve this component",
    )
    observed_at: datetime = Field(
        description="When this data was fetched from the source"
    )
    latency_ms: float | None = Field(
        default=None,
        description="Round-trip latency for the capability call in milliseconds",
    )
