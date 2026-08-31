# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Typed relationship edges for the canonical warehouse world graph.

Design notes:
- ASSIGNED_TO (Worker→Task) and SUPPORTS (Equipment→Task) are temporal edges.
  Multiple edges may exist for the same task over time with different valid_from/valid_to.
- FULFILLS (Wave→Order) supports many-to-many: one wave can fulfill multiple orders
  and one order may be split across multiple waves.
- Compatibility matrix defines valid (source_type, target_type) pairs per relationship.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from .entities import EntityType


class RelationshipType(str, Enum):
    # Facility structure
    CONTAINS = "CONTAINS"           # Warehouse→Zone, Zone→Location
    # Labor
    EMPLOYS = "EMPLOYS"             # Warehouse→Worker
    MEMBER_OF = "MEMBER_OF"         # Worker→Shift
    # Equipment
    OPERATES = "OPERATES"           # Warehouse→Equipment
    # Inventory
    STORES = "STORES"               # Warehouse→SKU (catalog)
    STORED_AT = "STORED_AT"         # InventoryPosition→Location
    # Work
    ASSIGNED_TO = "ASSIGNED_TO"     # Worker→Task (temporal — multiple allowed)
    SUPPORTS = "SUPPORTS"           # Equipment→Task (temporal)
    BELONGS_TO = "BELONGS_TO"       # Task→Wave
    REQUIRES = "REQUIRES"           # Task→SKU
    # Orders
    FULFILLS = "FULFILLS"           # Wave→Order (many-to-many)
    CONSTRAINED_BY = "CONSTRAINED_BY"  # Wave→CarrierCutoff
    # Shipment
    SHIPPED_VIA = "SHIPPED_VIA"     # Order→Shipment


# Compatibility matrix: defines valid (source_type, target_type) pairs per relationship.
RELATIONSHIP_COMPATIBILITY: dict[RelationshipType, set[tuple[EntityType, EntityType]]] = {
    RelationshipType.CONTAINS: {
        (EntityType.WAREHOUSE, EntityType.ZONE),
        (EntityType.ZONE, EntityType.LOCATION),
    },
    RelationshipType.EMPLOYS: {
        (EntityType.WAREHOUSE, EntityType.WORKER),
    },
    RelationshipType.MEMBER_OF: {
        (EntityType.WORKER, EntityType.SHIFT),
    },
    RelationshipType.OPERATES: {
        (EntityType.WAREHOUSE, EntityType.EQUIPMENT),
    },
    RelationshipType.STORES: {
        (EntityType.WAREHOUSE, EntityType.SKU),
    },
    RelationshipType.STORED_AT: {
        (EntityType.INVENTORY_POSITION, EntityType.LOCATION),
    },
    RelationshipType.ASSIGNED_TO: {
        (EntityType.WORKER, EntityType.TASK),
    },
    RelationshipType.SUPPORTS: {
        (EntityType.EQUIPMENT, EntityType.TASK),
    },
    RelationshipType.BELONGS_TO: {
        (EntityType.TASK, EntityType.WAVE),
    },
    RelationshipType.REQUIRES: {
        (EntityType.TASK, EntityType.SKU),
    },
    RelationshipType.FULFILLS: {
        (EntityType.WAVE, EntityType.ORDER),
    },
    RelationshipType.CONSTRAINED_BY: {
        (EntityType.WAVE, EntityType.CARRIER_CUTOFF),
    },
    RelationshipType.SHIPPED_VIA: {
        (EntityType.ORDER, EntityType.SHIPMENT),
    },
}


class WarehouseEdge(BaseModel):
    """
    A directed typed relationship between two warehouse entities.

    Temporal edges (ASSIGNED_TO, SUPPORTS) use valid_from/valid_to to record
    when a relationship was active. Multiple edges of the same type may exist
    between the same pair of entities at different time windows.

    valid_from=None means the edge is valid from world creation.
    valid_to=None means the edge has no expiry (open-ended / currently active).
    """

    model_config = ConfigDict(frozen=True)

    id: str
    source_id: str
    target_id: str
    relationship_type: RelationshipType
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    metadata: dict[str, str | int | float | bool | None] = {}

    @model_validator(mode="after")
    def valid_interval(self) -> "WarehouseEdge":
        if self.valid_from is not None and self.valid_to is not None:
            if self.valid_to <= self.valid_from:
                raise ValueError(
                    f"valid_to ({self.valid_to}) must be strictly after "
                    f"valid_from ({self.valid_from})"
                )
        return self

    def is_active(self, at: datetime | None = None) -> bool:
        """
        Returns True if this edge is valid at the given time.
        If ``at`` is None, uses the current UTC time.
        """
        now = at if at is not None else datetime.now(tz=timezone.utc)
        if self.valid_from is not None and now < self.valid_from:
            return False
        if self.valid_to is not None and now >= self.valid_to:
            return False
        return True

    def is_self_loop(self) -> bool:
        """Returns True if source and target are the same entity."""
        return self.source_id == self.target_id
