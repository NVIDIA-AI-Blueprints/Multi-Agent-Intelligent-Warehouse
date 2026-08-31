# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
WarehouseDataPack — portable, verifiable snapshot of a CanonicalWarehouseGraph.

Write:  WarehouseDataPack.write(graph, config, pack_dir)
Load:   WarehouseDataPack.load(pack_dir) → CanonicalWarehouseGraph
Verify: WarehouseDataPack.verify(pack_dir) → DataPackVerificationResult
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from pydantic import BaseModel

from .config import WarehouseWorldConfig
from .edges import WarehouseEdge
from .entities import (
    CarrierCutoff,
    Equipment,
    EntityType,
    InventoryPosition,
    Location,
    Order,
    SKU,
    Shift,
    Shipment,
    Task,
    WarehouseEntity,
    Warehouse,
    Wave,
    Worker,
    Zone,
)
from .events import OperationalEvent
from .graph import CanonicalWarehouseGraph
from .validation import FindingSeverity, ValidationReport

SCHEMA_VERSION = "1.0"
GENERATOR_VERSION = "0.1.0"
PACK_FORMAT = "maiw-datapack-v1"


# ── Checksum helpers ───────────────────────────────────────────────────────────

def _canonical_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), default=str)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def compute_semantic_checksum(graph: CanonicalWarehouseGraph) -> str:
    """
    Deterministic logical fingerprint of graph content.
    Same entities + edges + events → same checksum, regardless of
    generation time, file path, or machine.

    Includes: entity IDs/types/fields, edge IDs/fields, event IDs/fields,
    in sorted order.
    Excludes: generated_at, duration_ms, file paths, schema version strings.
    """
    parts = []
    for entity in sorted(graph._entities.values(), key=lambda e: e.id):
        parts.append(_canonical_json(entity.model_dump(mode='json')))
    for edge in sorted(graph._edges.values(), key=lambda e: e.id):
        parts.append(_canonical_json(edge.model_dump(mode='json')))
    for event in sorted(graph._events, key=lambda e: e.event_id):
        parts.append(_canonical_json(event.model_dump(mode='json')))
    payload = '\n'.join(parts).encode('utf-8')
    return _sha256_bytes(payload)


# ── Verification result ────────────────────────────────────────────────────────

class DataPackVerificationResult(BaseModel):
    passed: bool
    semantic_checksum_match: bool
    file_checksums_match: bool
    manifest_valid: bool
    graph_validation: ValidationReport | None = None
    errors: list[str] = []


# ── Entity round-trip helpers ──────────────────────────────────────────────────

_ENTITY_CLASS_MAP: dict[str, type] = {
    EntityType.WAREHOUSE.value: Warehouse,
    EntityType.ZONE.value: Zone,
    EntityType.LOCATION.value: Location,
    EntityType.WORKER.value: Worker,
    EntityType.SHIFT.value: Shift,
    EntityType.EQUIPMENT.value: Equipment,
    EntityType.SKU.value: SKU,
    EntityType.INVENTORY_POSITION.value: InventoryPosition,
    EntityType.ORDER.value: Order,
    EntityType.WAVE.value: Wave,
    EntityType.TASK.value: Task,
    EntityType.SHIPMENT.value: Shipment,
    EntityType.CARRIER_CUTOFF.value: CarrierCutoff,
}


def _entity_to_dict(entity: WarehouseEntity) -> dict:
    """Serialize entity to dict with discriminator field for reload."""
    d = entity.model_dump(mode='json')
    d['_entity_type'] = entity.entity_type.value
    return d


def _entity_from_dict(d: dict) -> WarehouseEntity:
    """Reconstruct the correct entity subclass from a serialized dict."""
    entity_type_str = d.pop('_entity_type')
    cls = _ENTITY_CLASS_MAP[entity_type_str]
    return cls(**d)


# ── Main DataPack class ────────────────────────────────────────────────────────

class WarehouseDataPack:

    @staticmethod
    def write(
        graph: CanonicalWarehouseGraph,
        config: WarehouseWorldConfig,
        pack_dir: str | Path,
    ) -> Path:
        """
        Serialize graph to pack_dir atomically.

        Writes to a temp directory in the same parent, then renames into place.
        If anything fails the temp dir is cleaned up and pack_dir is untouched.

        Returns the resolved pack_dir path.
        Raises ValueError if graph is empty.
        Raises OSError on filesystem errors.
        """
        pack_dir = Path(pack_dir).resolve()
        if graph.entity_count == 0:
            raise ValueError("Cannot write an empty graph to a DataPack")

        parent = pack_dir.parent
        parent.mkdir(parents=True, exist_ok=True)

        tmp_dir = Path(tempfile.mkdtemp(dir=parent, prefix=f".tmp-{pack_dir.name}-"))
        try:
            WarehouseDataPack._write_to_dir(graph, config, tmp_dir)
            if pack_dir.exists():
                shutil.rmtree(pack_dir)
            tmp_dir.rename(pack_dir)
        except Exception:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise

        return pack_dir

    @staticmethod
    def _write_to_dir(
        graph: CanonicalWarehouseGraph,
        config: WarehouseWorldConfig,
        target_dir: Path,
    ) -> None:
        graph_dir = target_dir / "graph"
        graph_dir.mkdir(parents=True)

        semantic_checksum = compute_semantic_checksum(graph)

        # entities.jsonl — sorted by id
        entities_path = graph_dir / "entities.jsonl"
        entities_sorted = sorted(graph._entities.values(), key=lambda e: e.id)
        entities_path.write_text(
            '\n'.join(_canonical_json(_entity_to_dict(e)) for e in entities_sorted) + '\n',
            encoding='utf-8',
        )

        # edges.jsonl — sorted by id
        edges_path = graph_dir / "edges.jsonl"
        edges_sorted = sorted(graph._edges.values(), key=lambda e: e.id)
        edges_path.write_text(
            '\n'.join(_canonical_json(e.model_dump(mode='json')) for e in edges_sorted) + '\n',
            encoding='utf-8',
        )

        # events.jsonl — sorted by event_id
        events_path = graph_dir / "events.jsonl"
        events_sorted = sorted(graph._events, key=lambda e: e.event_id)
        events_path.write_text(
            '\n'.join(_canonical_json(e.model_dump(mode='json')) for e in events_sorted) + '\n',
            encoding='utf-8',
        )

        # manifest.json — no generated_at or duration_ms
        manifest = {
            "maiw_world_schema_version": SCHEMA_VERSION,
            "generator_version": GENERATOR_VERSION,
            "pack_format": PACK_FORMAT,
            "warehouse_id": config.warehouse_id,
            "dataset_id": config.dataset_id,
            "seed": config.seed,
            "config_snapshot": config.model_dump(mode='json'),
            "entity_count": graph.entity_count,
            "edge_count": graph.edge_count,
            "event_count": graph.event_count,
            "semantic_checksum": semantic_checksum,
        }
        manifest_path = target_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True, default=str),
            encoding='utf-8',
        )

        # checksums.json
        checksums = {
            "semantic_checksum": semantic_checksum,
            "files": {
                "manifest.json":        _sha256_file(manifest_path),
                "graph/entities.jsonl": _sha256_file(entities_path),
                "graph/edges.jsonl":    _sha256_file(edges_path),
                "graph/events.jsonl":   _sha256_file(events_path),
            },
        }
        (target_dir / "checksums.json").write_text(
            json.dumps(checksums, indent=2, sort_keys=True),
            encoding='utf-8',
        )

    @staticmethod
    def load(pack_dir: str | Path) -> CanonicalWarehouseGraph:
        """
        Load a DataPack from disk and reconstruct a CanonicalWarehouseGraph.

        Does NOT re-validate file checksums on load (call verify() for that).
        Raises FileNotFoundError if required files are missing.
        Raises ValueError on malformed data.
        """
        pack_dir = Path(pack_dir).resolve()

        for required in [
            "manifest.json",
            "checksums.json",
            "graph/entities.jsonl",
            "graph/edges.jsonl",
            "graph/events.jsonl",
        ]:
            p = pack_dir / required
            if not p.exists():
                raise FileNotFoundError(f"DataPack missing required file: {required}")

        g = CanonicalWarehouseGraph()

        # Load entities
        entities_path = pack_dir / "graph" / "entities.jsonl"
        for line in entities_path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            entity = _entity_from_dict(d)
            g.add_entity(entity)

        # Load edges
        edges_path = pack_dir / "graph" / "edges.jsonl"
        for line in edges_path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            edge = WarehouseEdge(**d)
            g.add_edge(edge)

        # Load events
        events_path = pack_dir / "graph" / "events.jsonl"
        for line in events_path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            event = OperationalEvent(**d)
            g.add_event(event)

        return g

    @staticmethod
    def verify(pack_dir: str | Path) -> DataPackVerificationResult:
        """
        Full integrity check:
        1. Required files exist and manifest is parseable
        2. File content checksums match checksums.json
        3. Reloaded graph semantic_checksum matches manifest.semantic_checksum
        4. Reloaded graph passes validation

        Returns DataPackVerificationResult with passed=True only if all checks pass.
        """
        pack_dir = Path(pack_dir).resolve()
        errors: list[str] = []
        manifest_valid = False
        file_checksums_match = False
        semantic_checksum_match = False
        graph_validation = None

        # 1. Parse manifest
        try:
            manifest = json.loads((pack_dir / "manifest.json").read_text(encoding='utf-8'))
            manifest_valid = True
        except Exception as exc:
            errors.append(f"manifest.json unreadable: {exc}")
            return DataPackVerificationResult(
                passed=False,
                semantic_checksum_match=False,
                file_checksums_match=False,
                manifest_valid=False,
                errors=errors,
            )

        # 2. File checksums
        try:
            stored = json.loads((pack_dir / "checksums.json").read_text(encoding='utf-8'))
            file_ok = True
            for rel_path, expected_hash in stored.get("files", {}).items():
                actual = _sha256_file(pack_dir / rel_path)
                if actual != expected_hash:
                    errors.append(f"Checksum mismatch: {rel_path}")
                    file_ok = False
            file_checksums_match = file_ok
        except Exception as exc:
            errors.append(f"checksums.json error: {exc}")

        # 3. Semantic checksum via reload
        try:
            g = WarehouseDataPack.load(pack_dir)
            actual_checksum = compute_semantic_checksum(g)
            expected_checksum = manifest.get("semantic_checksum", "")
            semantic_checksum_match = (actual_checksum == expected_checksum)
            if not semantic_checksum_match:
                errors.append(
                    f"Semantic checksum mismatch: stored={expected_checksum[:16]}… "
                    f"actual={actual_checksum[:16]}…"
                )
            # 4. Graph validation
            graph_validation = g.validate()
            if not graph_validation.passed:
                fail_count = len(graph_validation.findings_by_severity(FindingSeverity.FAIL))
                errors.append(f"Reloaded graph has {fail_count} FAIL validation finding(s)")
        except Exception as exc:
            errors.append(f"Load/verify error: {exc}")

        passed = (
            manifest_valid
            and file_checksums_match
            and semantic_checksum_match
            and (graph_validation is None or graph_validation.passed)
        )
        return DataPackVerificationResult(
            passed=passed,
            semantic_checksum_match=semantic_checksum_match,
            file_checksums_match=file_checksums_match,
            manifest_valid=manifest_valid,
            graph_validation=graph_validation,
            errors=errors,
        )

    @staticmethod
    def read_manifest(pack_dir: str | Path) -> dict:
        """Return raw manifest dict without loading the full graph."""
        path = Path(pack_dir) / "manifest.json"
        if not path.exists():
            raise FileNotFoundError(f"No manifest.json in {pack_dir}")
        return json.loads(path.read_text(encoding='utf-8'))
