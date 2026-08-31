# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Operational events for the canonical warehouse world.

Events are distinct from edges:
- Edges describe structure/state relationships (what IS)
- Events describe what occurred over time (what HAPPENED)

A TASK_ASSIGNMENT event may cause the creation of an ASSIGNED_TO edge,
but they are separate records with different semantics.

event_time may be simulation time or wall-clock time — the caller chooses,
but it must always be timezone-aware.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator


class OperationalEventType(str, Enum):
    WORKER_ABSENCE = "WORKER_ABSENCE"
    WORKER_RETURN = "WORKER_RETURN"
    EQUIPMENT_FAILURE = "EQUIPMENT_FAILURE"
    EQUIPMENT_RESTORED = "EQUIPMENT_RESTORED"
    INVENTORY_ADJUSTMENT = "INVENTORY_ADJUSTMENT"
    TASK_ASSIGNMENT = "TASK_ASSIGNMENT"
    TASK_COMPLETION = "TASK_COMPLETION"
    TASK_BLOCKED = "TASK_BLOCKED"
    WAVE_RELEASE = "WAVE_RELEASE"
    WAVE_COMPLETION = "WAVE_COMPLETION"
    CARRIER_CUTOFF_MISSED = "CARRIER_CUTOFF_MISSED"


class OperationalEvent(BaseModel):
    """
    An immutable record of something that occurred in warehouse operations.

    Distinct from WarehouseEdge: edges describe structural relationships,
    events describe temporal occurrences. A TASK_ASSIGNMENT event may produce
    an ASSIGNED_TO edge, but they are separate.
    """

    model_config = ConfigDict(frozen=True)

    event_id: str
    event_type: OperationalEventType
    event_time: datetime  # must be timezone-aware; simulation or wall-clock
    entity_id: str        # primary target entity
    secondary_entity_id: str | None = None  # e.g. worker ID in TASK_ASSIGNMENT
    payload: dict[str, str | int | float | bool | None] = {}
    source: str = "system"  # "system" | "scenario" | "inject" | "generated"

    @field_validator("event_time")
    @classmethod
    def event_time_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError(
                "event_time must be timezone-aware. "
                "Use datetime(..., tzinfo=timezone.utc) or similar."
            )
        return v

    @field_validator("event_id")
    @classmethod
    def event_id_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("event_id must be non-empty")
        return v
