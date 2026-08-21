# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Cross-domain WarehouseState snapshot tests.

Validates that a single WarehouseState can hold Equipment + Labor + Wave
state simultaneously, with per-domain freshness, and that sealing it into a
WarehouseStateSnapshot preserves all domains.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from maiw_state.models.equipment import (
    EquipmentAssetSummary,
    EquipmentState,
    StateFreshness,
)
from maiw_state.models.labor import LaborState, LaborWorkerSummary
from maiw_state.models.wave import WaveState, WaveTaskSummary
from maiw_state.warehouse import WarehouseState, WarehouseStateSnapshot


def _freshness() -> StateFreshness:
    return StateFreshness.now()


def _make_equipment_state(wh_id: str = "WH-001") -> EquipmentState:
    return EquipmentState(
        warehouse_id=wh_id,
        assets=[
            EquipmentAssetSummary(
                asset_id="eq-001",
                equipment_type="forklift",
                model="CAT-3000",
                zone="zone-A",
                status="available",
                owner_user=None,
            )
        ],
        total_count=1,
        available_count=1,
        summary={"forklift": {"available": 1}},
        freshness=_freshness(),
    )


def _make_labor_state(
    wh_id: str = "WH-001",
    total_workers: int = 4,
    available_workers: int = 4,
) -> LaborState:
    workers = [
        LaborWorkerSummary(
            worker_id=f"w-{i:03d}",
            username=f"user{i}",
            full_name=f"User {i}",
            role="picker",
            status="active",
            zone="A1",
        )
        for i in range(total_workers)
    ]
    return LaborState(
        warehouse_id=wh_id,
        workers=workers,
        total_workers=total_workers,
        available_workers=available_workers,
        utilization_pct=round((1 - available_workers / max(total_workers, 1)) * 100, 1),
        zone_summary=[],
        freshness=_freshness(),
    )


def _make_wave_state(
    wh_id: str = "WH-001",
    at_risk_count: int = 1,
) -> WaveState:
    tasks = [
        WaveTaskSummary(
            task_id="t-001",
            task_type="PICK",
            zone="A1",
            status="pending",
            priority="high",
            assigned_to=None,
        ),
        WaveTaskSummary(
            task_id="t-002",
            task_type="PACK",
            zone="B1",
            status="in_progress",
            priority="medium",
            assigned_to="w-001",
        ),
    ]
    return WaveState(
        warehouse_id=wh_id,
        tasks=tasks,
        total_tasks=2,
        pending_count=1,
        in_progress_count=1,
        completed_count=0,
        at_risk_count=at_risk_count,
        zones_active=["A1", "B1"],
        zone_summary=[],
        freshness=_freshness(),
    )


def _make_warehouse_state(
    wh_id: str = "WH-001",
    *,
    equipment: EquipmentState | None = None,
    labor: LaborState | None = None,
    waves: WaveState | None = None,
) -> WarehouseState:
    return WarehouseState(
        warehouse_id=wh_id,
        observed_at=datetime.now(timezone.utc),
        equipment=equipment,
        labor=labor,
        waves=waves,
    )


class TestWarehouseStateMultiDomain:
    def test_state_holds_all_three_domains(self):
        state = _make_warehouse_state(
            equipment=_make_equipment_state(),
            labor=_make_labor_state(),
            waves=_make_wave_state(),
        )
        assert state.equipment is not None
        assert state.labor is not None
        assert state.waves is not None

    def test_state_equipment_domain_is_independent(self):
        state = _make_warehouse_state(equipment=_make_equipment_state())
        assert state.equipment.available_count == 1
        assert state.labor is None
        assert state.waves is None

    def test_state_labor_domain_is_independent(self):
        state = _make_warehouse_state(labor=_make_labor_state())
        assert state.labor.total_workers == 4
        assert state.equipment is None
        assert state.waves is None

    def test_state_wave_domain_is_independent(self):
        state = _make_warehouse_state(waves=_make_wave_state())
        assert state.waves.total_tasks == 2
        assert state.equipment is None
        assert state.labor is None

    def test_warehouse_id_propagates_to_all_domains(self):
        wh_id = "WH-CROSS-TEST"
        state = _make_warehouse_state(
            wh_id,
            equipment=_make_equipment_state(wh_id),
            labor=_make_labor_state(wh_id),
            waves=_make_wave_state(wh_id),
        )
        assert state.warehouse_id == wh_id
        assert state.equipment.warehouse_id == wh_id
        assert state.labor.warehouse_id == wh_id
        assert state.waves.warehouse_id == wh_id

    def test_each_domain_has_independent_freshness(self):
        state = _make_warehouse_state(
            equipment=_make_equipment_state(),
            labor=_make_labor_state(),
            waves=_make_wave_state(),
        )
        assert state.equipment.freshness is not None
        assert state.labor.freshness is not None
        assert state.waves.freshness is not None
        assert state.equipment.freshness is not state.labor.freshness
        assert state.labor.freshness is not state.waves.freshness

    def test_state_is_empty_when_no_domains(self):
        state = _make_warehouse_state()
        assert state.is_empty()

    def test_state_is_not_empty_with_one_domain(self):
        state = _make_warehouse_state(labor=_make_labor_state())
        assert not state.is_empty()

    def test_state_is_not_empty_with_all_domains(self):
        state = _make_warehouse_state(
            equipment=_make_equipment_state(),
            labor=_make_labor_state(),
            waves=_make_wave_state(),
        )
        assert not state.is_empty()


class TestWarehouseStateSnapshotMultiDomain:
    """WarehouseStateSnapshot.seal() must preserve all domains."""

    def test_snapshot_seals_all_three_domains(self):
        state = _make_warehouse_state(
            equipment=_make_equipment_state(),
            labor=_make_labor_state(),
            waves=_make_wave_state(),
        )
        snapshot = WarehouseStateSnapshot.seal(state)
        assert snapshot.state.equipment is not None
        assert snapshot.state.labor is not None
        assert snapshot.state.waves is not None

    def test_snapshot_warehouse_id_matches_state(self):
        state = _make_warehouse_state(
            "WH-SNAP", equipment=_make_equipment_state("WH-SNAP")
        )
        snapshot = WarehouseStateSnapshot.seal(state)
        assert snapshot.warehouse_id == "WH-SNAP"

    def test_snapshot_is_equipment_stale_false_for_fresh_equipment(self):
        state = _make_warehouse_state(equipment=_make_equipment_state())
        snapshot = WarehouseStateSnapshot.seal(state)
        assert not snapshot.is_equipment_stale()

    def test_snapshot_equipment_age_ms_none_when_no_equipment(self):
        state = _make_warehouse_state(labor=_make_labor_state())
        snapshot = WarehouseStateSnapshot.seal(state)
        assert snapshot.equipment_age_ms() is None


class TestLaborStateDomainProperties:
    def test_is_constrained_false_when_above_threshold(self):
        labor = _make_labor_state(total_workers=10, available_workers=5)
        assert not labor.is_constrained

    def test_is_constrained_true_when_at_or_below_20_pct(self):
        labor = _make_labor_state(total_workers=10, available_workers=2)
        assert labor.is_constrained

    def test_is_constrained_true_when_severely_below(self):
        labor = _make_labor_state(total_workers=10, available_workers=1)
        assert labor.is_constrained

    def test_is_constrained_false_at_just_above_threshold(self):
        labor = _make_labor_state(total_workers=10, available_workers=3)
        assert not labor.is_constrained

    def test_is_constrained_true_when_no_workers(self):
        labor = LaborState(
            warehouse_id="WH-001",
            total_workers=0,
            available_workers=0,
            utilization_pct=0.0,
            zone_summary=[],
            freshness=_freshness(),
        )
        assert labor.is_constrained


class TestWaveStateDomainProperties:
    def test_otif_at_risk_true_when_at_risk_count_positive(self):
        wave = _make_wave_state(at_risk_count=1)
        assert wave.otif_at_risk

    def test_otif_at_risk_false_when_no_at_risk_tasks(self):
        wave = WaveState(
            warehouse_id="WH-001",
            tasks=[],
            total_tasks=0,
            pending_count=0,
            in_progress_count=0,
            completed_count=0,
            at_risk_count=0,
            zones_active=[],
            zone_summary=[],
            freshness=_freshness(),
        )
        assert not wave.otif_at_risk

    def test_wave_state_tracks_counts(self):
        wave = _make_wave_state(at_risk_count=1)
        assert wave.pending_count == 1
        assert wave.in_progress_count == 1
        assert wave.completed_count == 0
        assert wave.total_tasks == 2


class TestCrossDomainConstraintVisibility:
    """
    Verify that constraints in one domain are visible alongside state from
    other domains within the same WarehouseState — key for cross-domain
    decision-making.
    """

    def test_labor_constraint_visible_with_wave_otif_risk(self):
        state = _make_warehouse_state(
            labor=_make_labor_state(total_workers=10, available_workers=1),
            waves=_make_wave_state(at_risk_count=2),
        )
        assert state.labor.is_constrained
        assert state.waves.otif_at_risk

    def test_healthy_labor_with_healthy_wave(self):
        safe_wave = WaveState(
            warehouse_id="WH-001",
            tasks=[],
            total_tasks=0,
            pending_count=0,
            in_progress_count=0,
            completed_count=0,
            at_risk_count=0,
            zones_active=[],
            zone_summary=[],
            freshness=_freshness(),
        )
        state = _make_warehouse_state(
            labor=_make_labor_state(total_workers=10, available_workers=8),
            waves=safe_wave,
        )
        assert not state.labor.is_constrained
        assert not state.waves.otif_at_risk

    def test_equipment_and_labor_coexist_in_snapshot(self):
        state = _make_warehouse_state(
            equipment=_make_equipment_state(),
            labor=_make_labor_state(),
        )
        snapshot = WarehouseStateSnapshot.seal(state)
        assert snapshot.state.equipment is not None
        assert snapshot.state.labor is not None
        assert snapshot.state.waves is None
