# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
EquipmentState — projected operational equipment context.

``EquipmentState`` is NOT a raw database mirror.  It contains the fields
relevant for agent reasoning and DecisionEngine evaluation:

    - Which assets are in scope and their availability
    - Fleet-level summary (count by type/status)
    - Freshness of the data

The ``WarehouseStateProvider`` populates this by calling
``EquipmentStatusSkill`` and projecting the result.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from maiw_state.freshness import StateFreshness


class EquipmentAssetSummary(BaseModel):
    """Operational summary for a single equipment asset."""

    asset_id: str
    equipment_type: str
    model: str
    zone: str
    status: str = Field(
        description="available | assigned | charging | maintenance | offline"
    )
    owner_user: str | None = None


class EquipmentState(BaseModel):
    """
    Operational equipment snapshot for a warehouse.

    Represents what the agent knows about equipment at a point in time.
    Populated through ``warehouse.equipment.get_status`` capability calls.
    """

    warehouse_id: str
    assets: list[EquipmentAssetSummary] = Field(default_factory=list)
    total_count: int = Field(ge=0, default=0)
    available_count: int = Field(ge=0, default=0)
    summary: dict[str, dict[str, int]] = Field(
        default_factory=dict,
        description="summary[equipment_type][status] = count",
    )
    freshness: StateFreshness

    def find_asset(self, asset_id: str) -> EquipmentAssetSummary | None:
        """Look up a specific asset by ID."""
        for asset in self.assets:
            if asset.asset_id == asset_id:
                return asset
        return None

    @classmethod
    def from_status_result(
        cls,
        warehouse_id: str,
        result: object,  # EquipmentStatusResult — duck-typed to avoid circular dep
        *,
        freshness: StateFreshness,
    ) -> EquipmentState:
        """
        Project an ``EquipmentStatusResult`` into ``EquipmentState``.

        Accepts any object with .equipment (list), .total_count, .summary
        attributes (structural duck-typing).
        """
        assets = [
            EquipmentAssetSummary(
                asset_id=a.asset_id,
                equipment_type=a.equipment_type,
                model=a.model,
                zone=a.zone,
                status=a.status,
                owner_user=a.owner_user,
            )
            for a in result.equipment
        ]
        available = sum(1 for a in assets if a.status == "available")
        return cls(
            warehouse_id=warehouse_id,
            assets=assets,
            total_count=result.total_count,
            available_count=available,
            summary=result.summary,
            freshness=freshness,
        )
