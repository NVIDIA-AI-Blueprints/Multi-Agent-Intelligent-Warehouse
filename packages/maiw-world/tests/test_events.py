# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for maiw_world.events (8 tests)."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from maiw_world.entities import Warehouse
from maiw_world.events import OperationalEvent, OperationalEventType
from maiw_world.graph import CanonicalWarehouseGraph

_UTC = timezone.utc
_T0 = datetime(2026, 9, 1, 8, 0, 0, tzinfo=_UTC)


def _make_event(**kwargs) -> OperationalEvent:
    defaults = {
        "event_id": "evt-001",
        "event_type": OperationalEventType.WORKER_ABSENCE,
        "event_time": _T0,
        "entity_id": "worker-001",
        "source": "system",
    }
    defaults.update(kwargs)
    return OperationalEvent(**defaults)


# ── 1. Valid OperationalEvent round-trips ─────────────────────────────────────

def test_valid_event_roundtrip():
    event = _make_event()
    assert event.event_id == "evt-001"
    assert event.event_type == OperationalEventType.WORKER_ABSENCE
    assert event.event_time == _T0
    assert event.entity_id == "worker-001"


# ── 2. add_event with unknown entity_id raises ValueError ─────────────────────

def test_add_event_unknown_entity_raises():
    g = CanonicalWarehouseGraph()
    # No entities added — entity_id won't be found
    event = _make_event(entity_id="unknown-entity")
    with pytest.raises(ValueError, match="entity_id"):
        g.add_event(event)


# ── 3. events_for_entity returns correct events ───────────────────────────────

def test_events_for_entity():
    g = CanonicalWarehouseGraph()
    g.add_entity(Warehouse(id="DC-47", name="DC-47"))

    e1 = _make_event(event_id="evt-001", entity_id="DC-47", event_type=OperationalEventType.WAVE_RELEASE)
    e2 = _make_event(event_id="evt-002", entity_id="DC-47", event_type=OperationalEventType.WAVE_COMPLETION)

    g.add_event(e1)
    g.add_event(e2)

    events = g.events_for_entity("DC-47")
    assert len(events) == 2
    event_ids = {e.event_id for e in events}
    assert "evt-001" in event_ids
    assert "evt-002" in event_ids


# ── 4. OperationalEventType.WORKER_ABSENCE serializes to string ───────────────

def test_event_type_serialization():
    # .value gives the raw string; serialization (e.g. JSON) also produces the string value
    assert OperationalEventType.WORKER_ABSENCE.value == "WORKER_ABSENCE"
    # Pydantic serializes str-enum to its value
    event = _make_event()
    data = event.model_dump()
    assert data["event_type"] == "WORKER_ABSENCE"


# ── 5. Event with secondary_entity_id stores correctly ───────────────────────

def test_event_secondary_entity_id():
    event = _make_event(
        event_id="evt-assign-001",
        event_type=OperationalEventType.TASK_ASSIGNMENT,
        entity_id="worker-001",
        secondary_entity_id="task-000001",
        payload={"priority": "high"},
    )
    assert event.secondary_entity_id == "task-000001"
    assert event.payload["priority"] == "high"


# ── 6. Frozen event cannot be mutated ─────────────────────────────────────────

def test_event_is_frozen():
    event = _make_event()
    with pytest.raises(Exception):  # ValidationError or TypeError for frozen model
        event.event_id = "different-id"  # type: ignore[misc]


# ── 7. source field defaults to "system" ─────────────────────────────────────

def test_event_source_default():
    event = OperationalEvent(
        event_id="evt-default",
        event_type=OperationalEventType.EQUIPMENT_FAILURE,
        event_time=_T0,
        entity_id="agv-001",
        # source not provided — should default to "system"
    )
    assert event.source == "system"


# ── 8. event_time must be timezone-aware ─────────────────────────────────────

def test_event_time_must_be_aware():
    with pytest.raises(ValidationError, match="timezone-aware"):
        OperationalEvent(
            event_id="evt-naive",
            event_type=OperationalEventType.EQUIPMENT_FAILURE,
            event_time=datetime(2026, 9, 1, 8, 0, 0),  # naive — no tzinfo
            entity_id="agv-001",
        )
