# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
WarehouseState and WarehouseStateSnapshot.

WarehouseState
--------------
The operational context for one warehouse at a point in time.  Agents
receive a WarehouseState (or snapshot) before reasoning rather than
querying backends directly.  Only domains explicitly requested by the
agent are populated — absent fields are ``None``.

WarehouseStateSnapshot
----------------------
An immutable, identified snapshot of WarehouseState used by the
DecisionEngine.  Each snapshot has a UUID so that:

    1. Decisions reference a known, stable version of state.
    2. Audit records can reference the exact state that drove a decision.
    3. The DecisionEngine never operates against mutable shared state.

Extension points
----------------
Additional domains (waves, labor, orders, docks) are represented as
``None`` fields with ``# future`` comments.  Adding a domain requires:

    1. A new model in ``maiw_state/models/<domain>.py``
    2. A field in ``WarehouseState``
    3. A population step in ``WarehouseStateProvider``
    4. A ``StateRequirements`` flag
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .freshness import StateFreshness
from .models.equipment import EquipmentState
from .models.inventory import InventoryState
from .models.labor import LaborState
from .models.wave import WaveState
from .provenance import StateProvenance


class WarehouseState(BaseModel):
    """
    Operational context for one warehouse at a point in time.

    Fields
    ------
    warehouse_id:
        Identifies the warehouse instance.
    observed_at:
        UTC timestamp when this state was assembled (the most recent
        ``observed_at`` across all populated components).
    inventory:
        Inventory context; ``None`` when not requested or unavailable.
    equipment:
        Equipment fleet context; ``None`` when not requested or unavailable.
    provenance:
        One entry per state component describing its origin.
    """

    warehouse_id: str
    observed_at: datetime = Field(description="When this state was assembled (UTC)")
    inventory: InventoryState | None = None
    equipment: EquipmentState | None = None
    labor: LaborState | None = None
    waves: WaveState | None = None
    # future: orders: OrderState | None = None
    # future: docks: DockState | None = None
    provenance: list[StateProvenance] = Field(default_factory=list)

    def is_empty(self) -> bool:
        """True when no domain data has been populated."""
        return (
            self.inventory is None
            and self.equipment is None
            and self.labor is None
            and self.waves is None
        )


class WarehouseStateSnapshot(BaseModel):
    """
    Immutable, identified snapshot of WarehouseState.

    The DecisionEngine receives a snapshot, not a live state object.
    This ensures that a decision is always evaluated against a consistent,
    timestamped version of reality.

    Fields
    ------
    snapshot_id:
        UUID assigned at snapshot creation.
    warehouse_id:
        Redundant with state.warehouse_id for convenient access.
    created_at:
        UTC timestamp when this snapshot was sealed.
    state:
        The warehouse state at snapshot creation time.
    """

    snapshot_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    warehouse_id: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    state: WarehouseState

    @classmethod
    def seal(cls, state: WarehouseState) -> WarehouseStateSnapshot:
        """
        Seal a WarehouseState into an immutable snapshot.

        Sets ``created_at`` to the current UTC moment and assigns a UUID.
        """
        return cls(
            warehouse_id=state.warehouse_id,
            created_at=datetime.now(timezone.utc),
            state=state,
        )

    def equipment_age_ms(self) -> int | None:
        """Return equipment state age in ms, or None if equipment is absent."""
        if self.state.equipment is None:
            return None
        return self.state.equipment.freshness.age_ms

    def is_equipment_stale(self) -> bool:
        """True when equipment state is present but stale."""
        if self.state.equipment is None:
            return False
        return self.state.equipment.freshness.stale
