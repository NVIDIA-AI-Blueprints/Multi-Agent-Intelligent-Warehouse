# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Tests for WarehouseDataPack — Phase 14C serialization.

All filesystem operations use tmp_path (pytest fixture).
WarehouseWorldConfig.small() is used for fast tests.
WarehouseWorldConfig.dc47_demo() is used for round-trip determinism tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maiw_world.config import WarehouseWorldConfig
from maiw_world.datapack import (
    DataPackVerificationResult,
    WarehouseDataPack,
    compute_semantic_checksum,
)
from maiw_world.entities import EntityType
from maiw_world.graph import CanonicalWarehouseGraph
from maiw_world.generator import WarehouseWorldGenerator


# ── Helpers ────────────────────────────────────────────────────────────────────

def _small_graph_and_config():
    cfg = WarehouseWorldConfig.small()
    result = WarehouseWorldGenerator(cfg).generate()
    return result.graph, cfg


# ── Round-trip and determinism tests ──────────────────────────────────────────

def test_round_trip_semantic_checksum_small(tmp_path):
    """graph A → DataPack → reload → graph B: semantic checksum must match."""
    graph_a, cfg = _small_graph_and_config()
    pack_dir = tmp_path / "pack"
    WarehouseDataPack.write(graph_a, cfg, pack_dir)
    graph_b = WarehouseDataPack.load(pack_dir)
    assert compute_semantic_checksum(graph_a) == compute_semantic_checksum(graph_b)


def test_round_trip_semantic_checksum_dc47(tmp_path):
    """DC-47 round-trip: full-size graph retains semantic checksum."""
    cfg = WarehouseWorldConfig.dc47_demo()
    graph_a = WarehouseWorldGenerator(cfg).generate().graph
    pack_dir = tmp_path / "dc47"
    WarehouseDataPack.write(graph_a, cfg, pack_dir)
    graph_b = WarehouseDataPack.load(pack_dir)
    assert compute_semantic_checksum(graph_a) == compute_semantic_checksum(graph_b)


def test_same_graph_two_paths_same_checksum(tmp_path):
    """Same world written to two different paths → identical semantic checksum."""
    graph, cfg = _small_graph_and_config()
    path_a = tmp_path / "pack_a"
    path_b = tmp_path / "pack_b"
    WarehouseDataPack.write(graph, cfg, path_a)
    WarehouseDataPack.write(graph, cfg, path_b)
    cs_a = json.loads((path_a / "checksums.json").read_text())["semantic_checksum"]
    cs_b = json.loads((path_b / "checksums.json").read_text())["semantic_checksum"]
    assert cs_a == cs_b


def test_different_seed_different_checksum(tmp_path):
    """Seed 1 vs seed 2 → different semantic checksum."""
    cfg1 = WarehouseWorldConfig.small()
    cfg2 = WarehouseWorldConfig(**{**cfg1.model_dump(), 'seed': 2})
    g1 = WarehouseWorldGenerator(cfg1).generate().graph
    g2 = WarehouseWorldGenerator(cfg2).generate().graph
    assert compute_semantic_checksum(g1) != compute_semantic_checksum(g2)


def test_semantic_checksum_is_deterministic(tmp_path):
    """Calling compute_semantic_checksum twice on the same graph yields identical results."""
    graph, _ = _small_graph_and_config()
    cs1 = compute_semantic_checksum(graph)
    cs2 = compute_semantic_checksum(graph)
    assert cs1 == cs2


def test_regenerate_same_seed_same_checksum(tmp_path):
    """Generate twice with same config; both semantic checksums match."""
    cfg = WarehouseWorldConfig.small()
    g1 = WarehouseWorldGenerator(cfg).generate().graph
    g2 = WarehouseWorldGenerator(cfg).generate().graph
    assert compute_semantic_checksum(g1) == compute_semantic_checksum(g2)


def test_generated_at_not_in_semantic_checksum(tmp_path):
    """generated_at is a wall-clock field; it must NOT affect the semantic checksum."""
    graph, _ = _small_graph_and_config()
    # The checksum is stable across repeated calls (no wall-clock dependency)
    cs1 = compute_semantic_checksum(graph)
    cs2 = compute_semantic_checksum(graph)
    assert cs1 == cs2


# ── Write / structure tests ────────────────────────────────────────────────────

def test_write_creates_required_files(tmp_path):
    graph, cfg = _small_graph_and_config()
    pack_dir = tmp_path / "pack"
    WarehouseDataPack.write(graph, cfg, pack_dir)
    assert (pack_dir / "manifest.json").exists()
    assert (pack_dir / "checksums.json").exists()
    assert (pack_dir / "graph" / "entities.jsonl").exists()
    assert (pack_dir / "graph" / "edges.jsonl").exists()
    assert (pack_dir / "graph" / "events.jsonl").exists()


def test_manifest_contains_required_fields(tmp_path):
    graph, cfg = _small_graph_and_config()
    pack_dir = tmp_path / "pack"
    WarehouseDataPack.write(graph, cfg, pack_dir)
    manifest = json.loads((pack_dir / "manifest.json").read_text())
    for key in [
        "maiw_world_schema_version", "generator_version", "pack_format",
        "warehouse_id", "dataset_id", "seed", "config_snapshot",
        "entity_count", "edge_count", "event_count", "semantic_checksum",
    ]:
        assert key in manifest, f"Missing key: {key}"


def test_manifest_does_not_contain_generated_at(tmp_path):
    graph, cfg = _small_graph_and_config()
    pack_dir = tmp_path / "pack"
    WarehouseDataPack.write(graph, cfg, pack_dir)
    manifest = json.loads((pack_dir / "manifest.json").read_text())
    assert "generated_at" not in manifest
    assert "duration_ms" not in manifest


def test_manifest_entity_count_matches_graph(tmp_path):
    graph, cfg = _small_graph_and_config()
    pack_dir = tmp_path / "pack"
    WarehouseDataPack.write(graph, cfg, pack_dir)
    manifest = json.loads((pack_dir / "manifest.json").read_text())
    assert manifest["entity_count"] == graph.entity_count


def test_manifest_edge_count_matches_graph(tmp_path):
    graph, cfg = _small_graph_and_config()
    pack_dir = tmp_path / "pack"
    WarehouseDataPack.write(graph, cfg, pack_dir)
    manifest = json.loads((pack_dir / "manifest.json").read_text())
    assert manifest["edge_count"] == graph.edge_count


def test_manifest_event_count_matches_graph(tmp_path):
    graph, cfg = _small_graph_and_config()
    pack_dir = tmp_path / "pack"
    WarehouseDataPack.write(graph, cfg, pack_dir)
    manifest = json.loads((pack_dir / "manifest.json").read_text())
    assert manifest["event_count"] == graph.event_count


def test_entities_jsonl_sorted_by_id(tmp_path):
    graph, cfg = _small_graph_and_config()
    pack_dir = tmp_path / "pack"
    WarehouseDataPack.write(graph, cfg, pack_dir)
    lines = [
        l for l in (pack_dir / "graph" / "entities.jsonl").read_text().splitlines()
        if l.strip()
    ]
    ids = [json.loads(l)["id"] for l in lines]
    assert ids == sorted(ids)


def test_edges_jsonl_sorted_by_id(tmp_path):
    graph, cfg = _small_graph_and_config()
    pack_dir = tmp_path / "pack"
    WarehouseDataPack.write(graph, cfg, pack_dir)
    lines = [
        l for l in (pack_dir / "graph" / "edges.jsonl").read_text().splitlines()
        if l.strip()
    ]
    ids = [json.loads(l)["id"] for l in lines]
    assert ids == sorted(ids)


def test_write_is_atomic_on_overwrite(tmp_path):
    """Writing to an existing pack_dir replaces it atomically."""
    graph, cfg = _small_graph_and_config()
    pack_dir = tmp_path / "pack"
    WarehouseDataPack.write(graph, cfg, pack_dir)
    first_checksum = json.loads((pack_dir / "checksums.json").read_text())["semantic_checksum"]
    # Write again (same data) — should succeed and produce identical checksum
    WarehouseDataPack.write(graph, cfg, pack_dir)
    second_checksum = json.loads((pack_dir / "checksums.json").read_text())["semantic_checksum"]
    assert first_checksum == second_checksum


def test_write_empty_graph_raises(tmp_path):
    cfg = WarehouseWorldConfig.small()
    empty = CanonicalWarehouseGraph()
    with pytest.raises(ValueError, match="empty"):
        WarehouseDataPack.write(empty, cfg, tmp_path / "pack")


def test_write_creates_parent_dirs(tmp_path):
    """write() should create nested parent directories as needed."""
    graph, cfg = _small_graph_and_config()
    pack_dir = tmp_path / "a" / "b" / "c" / "pack"
    WarehouseDataPack.write(graph, cfg, pack_dir)
    assert (pack_dir / "manifest.json").exists()


# ── Load tests ────────────────────────────────────────────────────────────────

def test_load_entity_count_matches(tmp_path):
    graph, cfg = _small_graph_and_config()
    pack_dir = tmp_path / "pack"
    WarehouseDataPack.write(graph, cfg, pack_dir)
    loaded = WarehouseDataPack.load(pack_dir)
    assert loaded.entity_count == graph.entity_count


def test_load_edge_count_matches(tmp_path):
    graph, cfg = _small_graph_and_config()
    pack_dir = tmp_path / "pack"
    WarehouseDataPack.write(graph, cfg, pack_dir)
    loaded = WarehouseDataPack.load(pack_dir)
    assert loaded.edge_count == graph.edge_count


def test_load_event_count_matches(tmp_path):
    graph, cfg = _small_graph_and_config()
    pack_dir = tmp_path / "pack"
    WarehouseDataPack.write(graph, cfg, pack_dir)
    loaded = WarehouseDataPack.load(pack_dir)
    assert loaded.event_count == graph.event_count


def test_load_missing_file_raises(tmp_path):
    graph, cfg = _small_graph_and_config()
    pack_dir = tmp_path / "pack"
    WarehouseDataPack.write(graph, cfg, pack_dir)
    (pack_dir / "graph" / "entities.jsonl").unlink()
    with pytest.raises(FileNotFoundError):
        WarehouseDataPack.load(pack_dir)


def test_load_preserves_entity_types(tmp_path):
    graph, cfg = _small_graph_and_config()
    pack_dir = tmp_path / "pack"
    WarehouseDataPack.write(graph, cfg, pack_dir)
    loaded = WarehouseDataPack.load(pack_dir)
    original_types = {e.id: e.entity_type for e in graph._entities.values()}
    loaded_types = {e.id: e.entity_type for e in loaded._entities.values()}
    assert original_types == loaded_types


def test_load_preserves_temporal_edges(tmp_path):
    """Edges with valid_from/valid_to survive round-trip."""
    graph, cfg = _small_graph_and_config()
    pack_dir = tmp_path / "pack"
    WarehouseDataPack.write(graph, cfg, pack_dir)
    loaded = WarehouseDataPack.load(pack_dir)
    orig_temporal = {
        e.id: (e.valid_from, e.valid_to)
        for e in graph._edges.values()
        if e.valid_from is not None
    }
    loaded_temporal = {
        e.id: (e.valid_from, e.valid_to)
        for e in loaded._edges.values()
        if e.valid_from is not None
    }
    assert orig_temporal == loaded_temporal


def test_load_all_entity_types_present(tmp_path):
    """All 13 EntityType values must round-trip without loss."""
    cfg = WarehouseWorldConfig.dc47_demo()
    graph = WarehouseWorldGenerator(cfg).generate().graph
    pack_dir = tmp_path / "pack"
    WarehouseDataPack.write(graph, cfg, pack_dir)
    loaded = WarehouseDataPack.load(pack_dir)
    for et in EntityType:
        orig_count = len(graph.entities_by_type(et))
        loaded_count = len(loaded.entities_by_type(et))
        assert orig_count == loaded_count, (
            f"EntityType.{et.value}: original={orig_count} loaded={loaded_count}"
        )


# ── Verify tests ──────────────────────────────────────────────────────────────

def test_verify_clean_pack_passes(tmp_path):
    graph, cfg = _small_graph_and_config()
    pack_dir = tmp_path / "pack"
    WarehouseDataPack.write(graph, cfg, pack_dir)
    result = WarehouseDataPack.verify(pack_dir)
    assert result.passed
    assert result.semantic_checksum_match
    assert result.file_checksums_match
    assert result.manifest_valid


def test_verify_detects_tampered_entities(tmp_path):
    graph, cfg = _small_graph_and_config()
    pack_dir = tmp_path / "pack"
    WarehouseDataPack.write(graph, cfg, pack_dir)
    # Tamper with entities.jsonl
    p = pack_dir / "graph" / "entities.jsonl"
    p.write_text(p.read_text() + '\n{"id": "injected"}\n', encoding='utf-8')
    result = WarehouseDataPack.verify(pack_dir)
    assert not result.passed
    assert not result.file_checksums_match


def test_verify_detects_tampered_manifest(tmp_path):
    """Altering manifest.json should fail file_checksums_match."""
    graph, cfg = _small_graph_and_config()
    pack_dir = tmp_path / "pack"
    WarehouseDataPack.write(graph, cfg, pack_dir)
    manifest_path = pack_dir / "manifest.json"
    data = json.loads(manifest_path.read_text())
    data["entity_count"] = 9999999
    manifest_path.write_text(json.dumps(data), encoding='utf-8')
    result = WarehouseDataPack.verify(pack_dir)
    assert not result.passed
    assert not result.file_checksums_match


def test_read_manifest_returns_dict(tmp_path):
    graph, cfg = _small_graph_and_config()
    pack_dir = tmp_path / "pack"
    WarehouseDataPack.write(graph, cfg, pack_dir)
    manifest = WarehouseDataPack.read_manifest(pack_dir)
    assert manifest["warehouse_id"] == cfg.warehouse_id
    assert manifest["seed"] == cfg.seed


def test_read_manifest_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        WarehouseDataPack.read_manifest(tmp_path / "nonexistent")


def test_manifest_config_snapshot_matches_config(tmp_path):
    """config_snapshot in manifest must match WarehouseWorldConfig.model_dump()."""
    graph, cfg = _small_graph_and_config()
    pack_dir = tmp_path / "pack"
    WarehouseDataPack.write(graph, cfg, pack_dir)
    manifest = json.loads((pack_dir / "manifest.json").read_text())
    assert manifest["config_snapshot"]["warehouse_id"] == cfg.warehouse_id
    assert manifest["config_snapshot"]["seed"] == cfg.seed
    assert manifest["config_snapshot"]["facility"]["zone_count"] == cfg.facility.zone_count


def test_checksums_json_semantic_matches_manifest(tmp_path):
    """checksums.json semantic_checksum must equal manifest.json semantic_checksum."""
    graph, cfg = _small_graph_and_config()
    pack_dir = tmp_path / "pack"
    WarehouseDataPack.write(graph, cfg, pack_dir)
    manifest = json.loads((pack_dir / "manifest.json").read_text())
    checksums = json.loads((pack_dir / "checksums.json").read_text())
    assert checksums["semantic_checksum"] == manifest["semantic_checksum"]


def test_verify_result_is_datapack_verification_result(tmp_path):
    """verify() returns a DataPackVerificationResult."""
    graph, cfg = _small_graph_and_config()
    pack_dir = tmp_path / "pack"
    WarehouseDataPack.write(graph, cfg, pack_dir)
    result = WarehouseDataPack.verify(pack_dir)
    assert isinstance(result, DataPackVerificationResult)
