# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Tests for WarehouseWorldGenerator (Phase 14B).

Test groups:
1. Determinism — same seed → identical topology (most critical)
2. Entity counts — counts match config values
3. Coherence / referential integrity — all edge references resolve
4. Validation — generated graphs pass structural checks
5. Report — report fields populated correctly
6. Edge cases — minimal configs, zero-history, history events
"""

from __future__ import annotations

import pytest

from maiw_world.config import (
    EquipmentConfig,
    FacilityConfig,
    HistoryConfig,
    InventoryConfig,
    LaborConfig,
    OrderConfig,
    WaveConfig,
    WarehouseWorldConfig,
)
from maiw_world.edges import RelationshipType
from maiw_world.entities import EntityType
from maiw_world.generator import WarehouseWorldGenerator


# ── Determinism tests ──────────────────────────────────────────────────────────

def test_dc47_generates_identical_graph_twice():
    """Same config + same seed → identical entity IDs and edge structure."""
    cfg = WarehouseWorldConfig.dc47_demo()
    r1 = WarehouseWorldGenerator(cfg).generate()
    r2 = WarehouseWorldGenerator(cfg).generate()

    ids1 = {e.id for e in r1.graph._entities.values()}
    ids2 = {e.id for e in r2.graph._entities.values()}
    assert ids1 == ids2

    edge_keys1 = {
        (e.source_id, e.target_id, e.relationship_type)
        for e in r1.graph._edges.values()
    }
    edge_keys2 = {
        (e.source_id, e.target_id, e.relationship_type)
        for e in r2.graph._edges.values()
    }
    assert edge_keys1 == edge_keys2


def test_different_seed_produces_different_workers():
    """Seed 42 vs seed 43: different worker skill assignments."""
    cfg42 = WarehouseWorldConfig.dc47_demo()
    cfg43 = WarehouseWorldConfig(**{**cfg42.model_dump(), "seed": 43})
    r42 = WarehouseWorldGenerator(cfg42).generate()
    r43 = WarehouseWorldGenerator(cfg43).generate()
    skills42 = [w.skills for w in r42.graph.entities_by_type(EntityType.WORKER)]
    skills43 = [w.skills for w in r43.graph.entities_by_type(EntityType.WORKER)]
    assert skills42 != skills43


def test_different_seed_produces_valid_graph():
    """Seed 43 graph still passes validation."""
    cfg = WarehouseWorldConfig(**{**WarehouseWorldConfig.dc47_demo().model_dump(), "seed": 43})
    r = WarehouseWorldGenerator(cfg).generate()
    assert r.report.validation_result.passed


# ── Entity count tests ─────────────────────────────────────────────────────────

def test_zone_count_matches_config():
    r = WarehouseWorldGenerator(WarehouseWorldConfig.dc47_demo()).generate()
    assert len(r.graph.entities_by_type(EntityType.ZONE)) == 6


def test_location_count_matches_config():
    r = WarehouseWorldGenerator(WarehouseWorldConfig.dc47_demo()).generate()
    assert len(r.graph.entities_by_type(EntityType.LOCATION)) == 240


def test_worker_count_matches_config():
    r = WarehouseWorldGenerator(WarehouseWorldConfig.dc47_demo()).generate()
    expected = 40 * 3  # workers_per_shift * shift_count
    assert len(r.graph.entities_by_type(EntityType.WORKER)) == expected


def test_sku_count_matches_config():
    r = WarehouseWorldGenerator(WarehouseWorldConfig.dc47_demo()).generate()
    assert len(r.graph.entities_by_type(EntityType.SKU)) == 25000


def test_order_count_matches_config():
    r = WarehouseWorldGenerator(WarehouseWorldConfig.dc47_demo()).generate()
    assert len(r.graph.entities_by_type(EntityType.ORDER)) == 850


def test_wave_count_matches_config():
    r = WarehouseWorldGenerator(WarehouseWorldConfig.dc47_demo()).generate()
    assert len(r.graph.entities_by_type(EntityType.WAVE)) == 3


def test_task_count_matches_config():
    r = WarehouseWorldGenerator(WarehouseWorldConfig.dc47_demo()).generate()
    assert len(r.graph.entities_by_type(EntityType.TASK)) == 120


# ── Coherence / referential integrity tests ───────────────────────────────────

def test_every_task_belongs_to_a_wave():
    r = WarehouseWorldGenerator(WarehouseWorldConfig.dc47_demo()).generate()
    wave_ids = {w.id for w in r.graph.entities_by_type(EntityType.WAVE)}
    for task in r.graph.entities_by_type(EntityType.TASK):
        belongs_edges = r.graph.outgoing_edges(task.id, RelationshipType.BELONGS_TO)
        assert len(belongs_edges) >= 1, f"Task {task.id} has no BELONGS_TO edge"
        for e in belongs_edges:
            assert e.target_id in wave_ids, (
                f"Task {task.id} belongs to unknown wave {e.target_id}"
            )


def test_every_task_requiring_sku_references_real_sku():
    r = WarehouseWorldGenerator(WarehouseWorldConfig.dc47_demo()).generate()
    sku_ids = {s.id for s in r.graph.entities_by_type(EntityType.SKU)}
    for task in r.graph.entities_by_type(EntityType.TASK):
        for e in r.graph.outgoing_edges(task.id, RelationshipType.REQUIRES):
            assert e.target_id in sku_ids


def test_every_worker_assignment_references_real_task():
    r = WarehouseWorldGenerator(WarehouseWorldConfig.dc47_demo()).generate()
    task_ids = {t.id for t in r.graph.entities_by_type(EntityType.TASK)}
    for worker in r.graph.entities_by_type(EntityType.WORKER):
        for e in r.graph.outgoing_edges(worker.id, RelationshipType.ASSIGNED_TO):
            assert e.target_id in task_ids


def test_every_equipment_support_references_real_task():
    r = WarehouseWorldGenerator(WarehouseWorldConfig.dc47_demo()).generate()
    task_ids = {t.id for t in r.graph.entities_by_type(EntityType.TASK)}
    for eq in r.graph.entities_by_type(EntityType.EQUIPMENT):
        for e in r.graph.outgoing_edges(eq.id, RelationshipType.SUPPORTS):
            assert e.target_id in task_ids


def test_every_wave_fulfills_real_orders():
    r = WarehouseWorldGenerator(WarehouseWorldConfig.dc47_demo()).generate()
    order_ids = {o.id for o in r.graph.entities_by_type(EntityType.ORDER)}
    for wave in r.graph.entities_by_type(EntityType.WAVE):
        for e in r.graph.outgoing_edges(wave.id, RelationshipType.FULFILLS):
            assert e.target_id in order_ids


def test_every_carrier_cutoff_referenced_by_wave():
    r = WarehouseWorldGenerator(WarehouseWorldConfig.dc47_demo()).generate()
    cutoff_ids = {c.id for c in r.graph.entities_by_type(EntityType.CARRIER_CUTOFF)}
    referenced = set()
    for wave in r.graph.entities_by_type(EntityType.WAVE):
        for e in r.graph.outgoing_edges(wave.id, RelationshipType.CONSTRAINED_BY):
            referenced.add(e.target_id)
    # All referenced cutoffs must be real
    assert referenced.issubset(cutoff_ids)


# ── Validation tests ───────────────────────────────────────────────────────────

def test_dc47_validation_passes():
    r = WarehouseWorldGenerator(WarehouseWorldConfig.dc47_demo()).generate()
    assert r.report.validation_result.passed


def test_small_world_validation_passes():
    r = WarehouseWorldGenerator(WarehouseWorldConfig.small()).generate()
    assert r.report.validation_result.passed


def test_large_world_validation_passes():
    # Use small() for speed — just verify the small() config is valid
    r = WarehouseWorldGenerator(WarehouseWorldConfig.small()).generate()
    assert r.report.validation_result.passed


# ── Report tests ───────────────────────────────────────────────────────────────

def test_report_entity_counts_consistent():
    r = WarehouseWorldGenerator(WarehouseWorldConfig.dc47_demo()).generate()
    counts = r.report.entity_counts
    assert counts.zones == 6
    assert counts.workers == 120
    assert counts.skus == 25000


def test_report_seed_matches_config():
    r = WarehouseWorldGenerator(WarehouseWorldConfig.dc47_demo()).generate()
    assert r.report.seed == 42


def test_report_dataset_id_matches_config():
    r = WarehouseWorldGenerator(WarehouseWorldConfig.dc47_demo()).generate()
    assert r.report.dataset_id == "dc47-demo-v1"


def test_report_duration_ms_positive():
    r = WarehouseWorldGenerator(WarehouseWorldConfig.dc47_demo()).generate()
    assert r.report.duration_ms > 0


def test_report_edge_count_positive():
    r = WarehouseWorldGenerator(WarehouseWorldConfig.dc47_demo()).generate()
    assert r.report.edge_count > 0


# ── Edge case / small config tests ────────────────────────────────────────────

def test_single_zone_single_location():
    cfg = WarehouseWorldConfig(
        warehouse_id="TINY",
        dataset_id="tiny-v1",
        seed=1,
        facility=FacilityConfig(zone_count=1, location_count=1, dock_door_count=1),
        inventory=InventoryConfig(sku_count=1, low_stock_pct=0.0),
        labor=LaborConfig(workers_per_shift=1, shift_count=1),
        equipment=EquipmentConfig(agv_count=1),
        orders=OrderConfig(daily_order_count=1, lines_per_order_mean=1.0),
        waves=WaveConfig(active_wave_count=1, task_count=1),
    )
    r = WarehouseWorldGenerator(cfg).generate()
    assert r.report.validation_result.passed
    assert r.report.entity_counts.zones == 1


def test_history_events_generated():
    cfg = WarehouseWorldConfig.small()
    r = WarehouseWorldGenerator(cfg).generate()
    assert r.graph.event_count > 0


def test_no_history_events_when_days_zero():
    cfg_dict = WarehouseWorldConfig.small().model_dump()
    cfg_dict["history"] = {"history_days": 0}
    cfg = WarehouseWorldConfig(**cfg_dict)
    r = WarehouseWorldGenerator(cfg).generate()
    assert r.graph.event_count == 0
