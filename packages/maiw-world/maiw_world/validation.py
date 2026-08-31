# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Structural integrity validation for CanonicalWarehouseGraph and WarehouseWorldConfig.

Validation checks are grouped by severity:
- FAIL: broken invariant that must be corrected
- WARN: suspicious configuration or missing best-practice relationships
- PASS: no issues found (only used for overall status when no findings)
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from .config import WarehouseWorldConfig
    from .graph import CanonicalWarehouseGraph


class FindingSeverity(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class ValidationFinding(BaseModel):
    severity: FindingSeverity
    code: str       # e.g. "DUPLICATE_ENTITY_ID", "DANGLING_EDGE_SOURCE"
    message: str
    entity_id: str | None = None
    edge_id: str | None = None


class ValidationReport(BaseModel):
    overall: FindingSeverity     # worst severity across all findings
    findings: list[ValidationFinding]

    @property
    def passed(self) -> bool:
        """True when no FAIL findings exist."""
        return self.overall != FindingSeverity.FAIL

    def findings_by_severity(
        self, severity: FindingSeverity
    ) -> list[ValidationFinding]:
        """Return all findings of the given severity."""
        return [f for f in self.findings if f.severity == severity]


def _worst_severity(findings: list[ValidationFinding]) -> FindingSeverity:
    """Compute the worst (most severe) severity across all findings."""
    if any(f.severity == FindingSeverity.FAIL for f in findings):
        return FindingSeverity.FAIL
    if any(f.severity == FindingSeverity.WARN for f in findings):
        return FindingSeverity.WARN
    return FindingSeverity.PASS


def validate_graph(graph: "CanonicalWarehouseGraph") -> ValidationReport:
    """
    Run all structural integrity checks on the graph.

    Checks performed:
    1. Duplicate entity IDs (FAIL) — caught by add_entity, but defensively checked
    2. Edge source entity exists (FAIL)
    3. Edge target entity exists (FAIL)
    4. Self-loop on any relationship (WARN)
    5. Invalid relationship/entity-type combination (FAIL) — re-verified
    6. valid_from > valid_to on edges (FAIL)
    7. Event target entity exists (FAIL)
    8. InventoryPosition.quantity_available < 0 (FAIL)
    9. Task with no BELONGS_TO edge (WARN)
    10. Orphaned Location (no CONTAINS edge pointing to it) (WARN)
    """
    from .edges import RELATIONSHIP_COMPATIBILITY, RelationshipType
    from .entities import EntityType, InventoryPosition, Task

    findings: list[ValidationFinding] = []

    # ── 1. Duplicate entity IDs ────────────────────────────────────────────────
    # The graph's add_entity prevents duplicates, but we verify defensively.
    seen_entity_ids: set[str] = set()
    for entity in graph._entities.values():
        if entity.id in seen_entity_ids:
            findings.append(ValidationFinding(
                severity=FindingSeverity.FAIL,
                code="DUPLICATE_ENTITY_ID",
                message=f"Entity id '{entity.id}' appears more than once.",
                entity_id=entity.id,
            ))
        seen_entity_ids.add(entity.id)

    # ── 2 & 3. Edge source/target existence ───────────────────────────────────
    for edge in graph._edges.values():
        if edge.source_id not in graph._entities:
            findings.append(ValidationFinding(
                severity=FindingSeverity.FAIL,
                code="DANGLING_EDGE_SOURCE",
                message=(
                    f"Edge '{edge.id}': source entity '{edge.source_id}' "
                    "is not present in the graph."
                ),
                edge_id=edge.id,
            ))
        if edge.target_id not in graph._entities:
            findings.append(ValidationFinding(
                severity=FindingSeverity.FAIL,
                code="DANGLING_EDGE_TARGET",
                message=(
                    f"Edge '{edge.id}': target entity '{edge.target_id}' "
                    "is not present in the graph."
                ),
                edge_id=edge.id,
            ))

    # ── 4. Self-loops ──────────────────────────────────────────────────────────
    for edge in graph._edges.values():
        if edge.is_self_loop():
            findings.append(ValidationFinding(
                severity=FindingSeverity.WARN,
                code="SELF_LOOP_EDGE",
                message=(
                    f"Edge '{edge.id}' ({edge.relationship_type.value}): "
                    f"source_id == target_id == '{edge.source_id}'."
                ),
                edge_id=edge.id,
            ))

    # ── 5. Invalid relationship/entity-type combination ────────────────────────
    for edge in graph._edges.values():
        source_entity = graph._entities.get(edge.source_id)
        target_entity = graph._entities.get(edge.target_id)
        if source_entity is None or target_entity is None:
            continue  # already reported in checks 2/3
        allowed_pairs = RELATIONSHIP_COMPATIBILITY.get(edge.relationship_type, set())
        pair = (source_entity.entity_type, target_entity.entity_type)
        if pair not in allowed_pairs:
            findings.append(ValidationFinding(
                severity=FindingSeverity.FAIL,
                code="INVALID_RELATIONSHIP_TYPE_PAIR",
                message=(
                    f"Edge '{edge.id}': {edge.relationship_type.value} "
                    f"is not valid between {source_entity.entity_type.value} "
                    f"and {target_entity.entity_type.value}."
                ),
                edge_id=edge.id,
            ))

    # ── 6. valid_from > valid_to ───────────────────────────────────────────────
    for edge in graph._edges.values():
        if edge.valid_from is not None and edge.valid_to is not None:
            if edge.valid_to <= edge.valid_from:
                findings.append(ValidationFinding(
                    severity=FindingSeverity.FAIL,
                    code="INVALID_TEMPORAL_INTERVAL",
                    message=(
                        f"Edge '{edge.id}': valid_to ({edge.valid_to}) "
                        f"must be strictly after valid_from ({edge.valid_from})."
                    ),
                    edge_id=edge.id,
                ))

    # ── 7. Event entity existence ──────────────────────────────────────────────
    for event in graph._events:
        if event.entity_id and event.entity_id not in graph._entities:
            findings.append(ValidationFinding(
                severity=FindingSeverity.FAIL,
                code="EVENT_ENTITY_NOT_FOUND",
                message=(
                    f"Event '{event.event_id}': entity_id '{event.entity_id}' "
                    "is not present in the graph."
                ),
            ))

    # ── 8. InventoryPosition non-negative quantities ───────────────────────────
    for entity in graph._entities.values():
        if isinstance(entity, InventoryPosition):
            if entity.quantity_available < 0:
                findings.append(ValidationFinding(
                    severity=FindingSeverity.FAIL,
                    code="NEGATIVE_INVENTORY_QUANTITY",
                    message=(
                        f"InventoryPosition '{entity.id}': "
                        f"quantity_available={entity.quantity_available} is negative."
                    ),
                    entity_id=entity.id,
                ))

    # ── 9. Task with no BELONGS_TO edge ───────────────────────────────────────
    for entity in graph._entities.values():
        if isinstance(entity, Task):
            outgoing = graph.outgoing_edges(entity.id, RelationshipType.BELONGS_TO)
            if not outgoing:
                findings.append(ValidationFinding(
                    severity=FindingSeverity.WARN,
                    code="TASK_NO_WAVE",
                    message=(
                        f"Task '{entity.id}' has no BELONGS_TO edge to a Wave. "
                        "Tasks should belong to a wave."
                    ),
                    entity_id=entity.id,
                ))

    # ── 10. Orphaned Location ──────────────────────────────────────────────────
    from .entities import Location
    for entity in graph._entities.values():
        if isinstance(entity, Location):
            incoming = graph.incoming_edges(entity.id, RelationshipType.CONTAINS)
            if not incoming:
                findings.append(ValidationFinding(
                    severity=FindingSeverity.WARN,
                    code="ORPHANED_LOCATION",
                    message=(
                        f"Location '{entity.id}' (code: {entity.location_code}) "
                        "is not connected to any Zone via a CONTAINS edge."
                    ),
                    entity_id=entity.id,
                ))

    return ValidationReport(
        overall=_worst_severity(findings),
        findings=findings,
    )


def validate_config(config: "WarehouseWorldConfig") -> ValidationReport:
    """
    Config-level validation beyond Pydantic field constraints.

    Checks:
    1. task_count >= active_wave_count (FAIL if not)
    2. location_count >= zone_count (FAIL if not — also enforced by FacilityConfig)
    3. low_stock_pct > 0.5 (WARN — unusual value)
    4. history_days > 365 (WARN — may generate large data)
    """
    findings: list[ValidationFinding] = []

    # ── 1. task_count >= active_wave_count ────────────────────────────────────
    if config.waves.task_count < config.waves.active_wave_count:
        findings.append(ValidationFinding(
            severity=FindingSeverity.FAIL,
            code="INSUFFICIENT_TASK_COUNT",
            message=(
                f"waves.task_count ({config.waves.task_count}) must be >= "
                f"waves.active_wave_count ({config.waves.active_wave_count}) "
                "so each wave has at least one task."
            ),
        ))

    # ── 2. location_count >= zone_count ───────────────────────────────────────
    if config.facility.location_count < config.facility.zone_count:
        findings.append(ValidationFinding(
            severity=FindingSeverity.FAIL,
            code="INSUFFICIENT_LOCATION_COUNT",
            message=(
                f"facility.location_count ({config.facility.location_count}) must be >= "
                f"facility.zone_count ({config.facility.zone_count}) "
                "so each zone has at least one location."
            ),
        ))

    # ── 3. Unusual low_stock_pct ───────────────────────────────────────────────
    if config.inventory.low_stock_pct > 0.5:
        findings.append(ValidationFinding(
            severity=FindingSeverity.WARN,
            code="HIGH_LOW_STOCK_PCT",
            message=(
                f"inventory.low_stock_pct={config.inventory.low_stock_pct:.2f} "
                "is unusually high (> 0.5). Verify this is intended."
            ),
        ))

    # ── 4. history_days > 365 ─────────────────────────────────────────────────
    if config.history.history_days > 365:
        findings.append(ValidationFinding(
            severity=FindingSeverity.WARN,
            code="LARGE_HISTORY_WINDOW",
            message=(
                f"history.history_days={config.history.history_days} "
                "exceeds 365 days and may generate a large dataset."
            ),
        ))

    return ValidationReport(
        overall=_worst_severity(findings),
        findings=findings,
    )
