# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for Phase 17B — /world/changes endpoint.

Invariants:
  C1. No active scenario returns scenario_active=False, empty events.
  C2. Labor scenario returns correct event kinds and affected entities.
  C3. Equipment-failure scenario returns EQUIPMENT_FAILURE events.
  C4. Events are returned in deterministic temporal order.
  C5. DataPack checksum is unchanged by scenario activation (immutability proof).
  C6. Endpoint returns no full entity list or edge list.
  C7. Endpoint is GET-only.
  C8. Legacy YAML path (no ScenarioWorld) returns degraded response, not 500.
  C9. Affected entities are deduplicated by entity_id.
  C10. Severity is derived from ScenarioWorld, not from frontend.
  C11. before_state and after_state are present for canonical event kinds.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock

import pytest

REPO_ROOT = Path(__file__).parents[2]


def _make_overlay_event(event_id, kind, entity_id, offset, label=""):
    from maiw_world.scenario import OverlayEvent, OverlayEventKind

    return OverlayEvent(
        event_id=event_id,
        kind=OverlayEventKind[kind],
        entity_id=entity_id,
        sim_time_offset_seconds=offset,
        label=label,
    )


def _make_overlay(scenario_id, name, events):
    from maiw_world.scenario import ScenarioOverlay

    return ScenarioOverlay(
        scenario_id=scenario_id,
        name=name,
        description="test",
        dataset_id="test-dataset",
        events=events,
    )


def _make_scenario_world(overlay, graph=None):
    sw = MagicMock()
    sw.overlay = overlay
    sw.disruption_severity.return_value = "HIGH"
    sw.absent_workers.return_value = []
    sw.failed_equipment.return_value = []
    sw.blocked_tasks.return_value = []
    return sw


def _make_runtime(
    scenario_world=None, active=True, checksum="abc123", elapsed=0.0, graph=None
):
    rt = MagicMock()
    rt.world_datapack_manifest = {
        "semantic_checksum": checksum,
        "warehouse_id": "DC-47",
        "dataset_id": "dc47-demo-v1",
    }
    rt.world_graph = graph

    if scenario_world is not None or active:
        ctrl = MagicMock()
        ctrl.active = active
        ctrl.scenario_name = "test-scenario"
        world = MagicMock()
        world.clock.elapsed_seconds = elapsed
        world._scenario_world = scenario_world
        ctrl.world = world
        rt.demo_controller = ctrl
    else:
        rt.demo_controller = None

    return rt


class TestWorldChangesGETOnly:
    """C7: GET-only endpoint."""

    def test_changes_endpoint_is_get_only(self):
        from maiw_api.routers import world as world_module
        from fastapi.routing import APIRoute

        changes_route = next(
            (
                r
                for r in world_module.router.routes
                if isinstance(r, APIRoute) and "/changes" in r.path
            ),
            None,
        )
        assert changes_route is not None, "/world/changes route must exist"
        assert changes_route.methods == {"GET"}, "Must be GET-only"


class TestWorldChangesNoScenario:
    """C1: No active scenario."""

    def test_no_scenario_returns_not_active(self):
        from maiw_api.routers.world import get_world_changes

        rt = _make_runtime(active=False, scenario_world=None)
        result = asyncio.run(get_world_changes(runtime=rt))
        assert result.scenario_active is False
        assert result.events == []
        assert result.affected_entities == []
        assert result.overlay_event_count == 0

    def test_no_controller_returns_not_active(self):
        from maiw_api.routers.world import get_world_changes

        rt = MagicMock()
        rt.world_datapack_manifest = {
            "semantic_checksum": "x",
            "warehouse_id": "DC-47",
            "dataset_id": "ds1",
        }
        rt.world_graph = None
        rt.demo_controller = None
        result = asyncio.run(get_world_changes(runtime=rt))
        assert result.scenario_active is False

    def test_no_scenario_severity_is_nominal(self):
        from maiw_api.routers.world import get_world_changes

        rt = _make_runtime(active=False)
        result = asyncio.run(get_world_changes(runtime=rt))
        assert result.scenario_severity == "NOMINAL"


class TestWorldChangesLaborScenario:
    """C2: Labor constraint scenario."""

    def _make_labor_overlay(self):
        events = [
            _make_overlay_event(
                "e1", "WORKER_ABSENCE", "worker-001", 0.0, "Worker 001 absent"
            ),
            _make_overlay_event(
                "e2", "WORKER_ABSENCE", "worker-002", 30.0, "Worker 002 absent"
            ),
            _make_overlay_event(
                "e3", "TASK_BLOCK", "task-001", 300.0, "Task 001 blocked"
            ),
            _make_overlay_event(
                "e4", "CARRIER_CUTOFF_MISS", "cutoff-001", 1800.0, "Cutoff missed"
            ),
        ]
        return _make_overlay(
            "labor-constraint-wave-risk", "Labor Constraint + Wave Risk", events
        )

    def test_labor_scenario_returns_active(self):
        from maiw_api.routers.world import get_world_changes

        overlay = self._make_labor_overlay()
        sw = _make_scenario_world(overlay)
        rt = _make_runtime(scenario_world=sw)
        result = asyncio.run(get_world_changes(runtime=rt))
        assert result.scenario_active is True
        assert result.scenario_id == "labor-constraint-wave-risk"

    def test_labor_scenario_event_count(self):
        from maiw_api.routers.world import get_world_changes

        overlay = self._make_labor_overlay()
        sw = _make_scenario_world(overlay)
        rt = _make_runtime(scenario_world=sw)
        result = asyncio.run(get_world_changes(runtime=rt))
        assert result.overlay_event_count == 4
        assert len(result.events) == 4

    def test_labor_scenario_affected_entities_deduplicated(self):
        from maiw_api.routers.world import get_world_changes

        # Two events for same worker should still be one affected entity
        events = [
            _make_overlay_event("e1", "WORKER_ABSENCE", "worker-001", 0.0),
            _make_overlay_event("e2", "WORKER_RETURN", "worker-001", 3600.0),
        ]
        overlay = _make_overlay("test", "Test", events)
        sw = _make_scenario_world(overlay)
        rt = _make_runtime(scenario_world=sw)
        result = asyncio.run(get_world_changes(runtime=rt))
        assert result.affected_entity_count == 1  # C9: deduplication

    def test_labor_scenario_worker_absence_has_before_after(self):
        from maiw_api.routers.world import get_world_changes

        events = [_make_overlay_event("e1", "WORKER_ABSENCE", "worker-001", 0.0)]
        overlay = _make_overlay("test", "Test", events)
        sw = _make_scenario_world(overlay)
        rt = _make_runtime(scenario_world=sw)
        result = asyncio.run(get_world_changes(runtime=rt))
        absence_event = next(
            e for e in result.events if e.event_type == "WORKER_ABSENCE"
        )
        assert absence_event.before_state == "ACTIVE"  # C11
        assert absence_event.after_state == "ABSENT"


class TestWorldChangesEquipmentScenario:
    """C3: Equipment failure scenario."""

    def test_equipment_failure_events_present(self):
        from maiw_api.routers.world import get_world_changes

        events = [
            _make_overlay_event(
                "e1", "EQUIPMENT_FAILURE", "agv-001", 0.0, "AGV offline"
            ),
            _make_overlay_event(
                "e2", "EQUIPMENT_RESTORED", "agv-001", 1800.0, "AGV restored"
            ),
        ]
        overlay = _make_overlay("agv-fleet-failure", "AGV Fleet Failure", events)
        sw = _make_scenario_world(overlay)
        rt = _make_runtime(scenario_world=sw)
        result = asyncio.run(get_world_changes(runtime=rt))
        kinds = {e.event_type for e in result.events}
        assert "EQUIPMENT_FAILURE" in kinds
        assert "EQUIPMENT_RESTORED" in kinds

    def test_equipment_failure_has_before_after(self):
        from maiw_api.routers.world import get_world_changes

        events = [_make_overlay_event("e1", "EQUIPMENT_FAILURE", "agv-001", 0.0)]
        overlay = _make_overlay("test", "Test", events)
        sw = _make_scenario_world(overlay)
        rt = _make_runtime(scenario_world=sw)
        result = asyncio.run(get_world_changes(runtime=rt))
        failure_event = next(
            e for e in result.events if e.event_type == "EQUIPMENT_FAILURE"
        )
        assert failure_event.before_state == "AVAILABLE"
        assert failure_event.after_state == "FAILED"


class TestWorldChangesOrdering:
    """C4: Deterministic temporal order."""

    def test_events_ordered_by_offset(self):
        from maiw_api.routers.world import get_world_changes

        events = [
            _make_overlay_event("e3", "CARRIER_CUTOFF_MISS", "cutoff-001", 1800.0),
            _make_overlay_event("e1", "WORKER_ABSENCE", "worker-001", 0.0),
            _make_overlay_event("e2", "TASK_BLOCK", "task-001", 300.0),
        ]
        overlay = _make_overlay("test", "Test", events)
        sw = _make_scenario_world(overlay)
        rt = _make_runtime(scenario_world=sw)
        result = asyncio.run(get_world_changes(runtime=rt))
        offsets = [e.sim_time_offset_seconds for e in result.events]
        assert offsets == sorted(offsets)


class TestWorldChangesChecksumInvariant:
    """C5: DataPack checksum unchanged by scenario activation."""

    def test_base_checksum_matches_manifest_checksum(self):
        from maiw_api.routers.world import get_world_changes

        events = [_make_overlay_event("e1", "WORKER_ABSENCE", "worker-001", 0.0)]
        overlay = _make_overlay("test", "Test", events)
        sw = _make_scenario_world(overlay)
        manifest_checksum = "immutable-checksum-never-changes"
        rt = _make_runtime(scenario_world=sw, checksum=manifest_checksum)
        result = asyncio.run(get_world_changes(runtime=rt))
        # The base_checksum comes from manifest — never from scenario overlay
        assert result.base_checksum == manifest_checksum

    def test_checksum_same_with_and_without_scenario(self):
        from maiw_api.routers.world import get_world_changes

        checksum = "test-checksum-xyz"
        # With scenario
        events = [_make_overlay_event("e1", "WORKER_ABSENCE", "w1", 0.0)]
        overlay = _make_overlay("s1", "Test", events)
        sw = _make_scenario_world(overlay)
        rt_with = _make_runtime(scenario_world=sw, checksum=checksum)
        result_with = asyncio.run(get_world_changes(runtime=rt_with))
        # Without scenario
        rt_without = _make_runtime(active=False, checksum=checksum)
        result_without = asyncio.run(get_world_changes(runtime=rt_without))
        assert result_with.base_checksum == result_without.base_checksum == checksum


class TestWorldChangesNoFullGraph:
    """C6: No full entity/edge serialization."""

    def test_response_has_no_entities_field(self):
        from maiw_api.routers.world import WorldChangesResponse

        assert "entities" not in WorldChangesResponse.model_fields

    def test_response_has_no_edges_field(self):
        from maiw_api.routers.world import WorldChangesResponse

        assert "edges" not in WorldChangesResponse.model_fields


class TestWorldChangesLegacyPath:
    """C8: Legacy YAML path returns degraded response."""

    def test_legacy_path_no_scenario_world(self):
        from maiw_api.routers.world import get_world_changes

        # scenario_world=None but active=True simulates legacy YAML path
        rt = _make_runtime(active=True, scenario_world=None)
        result = asyncio.run(get_world_changes(runtime=rt))
        # Should not raise; should return degraded response
        assert result.events == []
        assert result.overlay_event_count == 0
