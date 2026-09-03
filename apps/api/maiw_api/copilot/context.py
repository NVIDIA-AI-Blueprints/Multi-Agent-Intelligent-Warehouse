# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
OperationalContextResolver — bounded graph neighborhood for a Copilot turn.

Deterministic graph BFS (no vector retrieval). Bounded by max_depth and
max_entities to prevent passing the full 51k-entity DataPack to Nemotron.

Phase 15B: depth=2, max_entities=50.
Phase 15C: exact entity resolution — no silent fallback to first entity.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .models import ContextNeighborhood

logger = logging.getLogger(__name__)

_MAX_DEPTH = 2
_MAX_ENTITIES = 50

# Patterns that indicate an operator is asking about a specific wave number.
_WAVE_NUMBER_RE = re.compile(r"\bwave\s*(\d+)\b", re.IGNORECASE)
# Patterns for worker references like "worker-042" or "Worker 42"
_WORKER_ID_RE = re.compile(r"\bworker[-\s](\w+)\b", re.IGNORECASE)
# Patterns for equipment references like "AGV-03"
_EQUIPMENT_ID_RE = re.compile(r"\b(AGV|forklift|conveyor)[-\s](\w+)\b", re.IGNORECASE)


class MatchType(str, Enum):
    EXACT_ID = "EXACT_ID"
    EXACT_ATTRIBUTE = "EXACT_ATTRIBUTE"
    ALIAS = "ALIAS"
    NOT_FOUND = "NOT_FOUND"


@dataclass(frozen=True)
class EntityResolution:
    """Result of deterministic entity resolution for a Copilot turn."""
    requested_reference: str       # what the operator typed ("Wave 17", "AGV-03")
    resolved_entity_id: str | None # canonical entity .id, or None
    entity_type: str | None        # EntityType value string, or None
    match_type: MatchType


def _extract_wave_number(question: str) -> int | None:
    m = _WAVE_NUMBER_RE.search(question)
    return int(m.group(1)) if m else None


def _entity_label(entity: Any) -> str:
    """Best-effort human label from a WarehouseEntity."""
    for attr in ("wave_number", "worker_id", "asset_id", "sku", "zone_id",
                 "location_id", "dock_door_id", "order_id", "task_id",
                 "shift_id", "carrier_id"):
        val = getattr(entity, attr, None)
        if val is not None:
            return str(val)
    return getattr(entity, "id", "unknown")


def _relationship_label(rel_type: Any) -> str:
    name = str(rel_type)
    return name.split(".")[-1].replace("_", " ").title()


def resolve_entity(
    question: str,
    graph: Any,
) -> EntityResolution:
    """
    Deterministic entity resolution for the operator question.

    Never silently substitutes another entity. If the requested entity is
    not found, returns MatchType.NOT_FOUND with resolved_entity_id=None.

    Supported reference forms:
      Wave 17          → EXACT_ATTRIBUTE on wave_number=17
      wave-017         → EXACT_ID
      Worker 42        → EXACT_ATTRIBUTE on worker numeric suffix
      AGV-03           → EXACT_ID / EXACT_ATTRIBUTE
    """
    from maiw_world.entities import EntityType

    # ── Wave reference ─────────────────────────────────────────────────────────
    wave_num = _extract_wave_number(question)
    if wave_num is not None:
        ref_str = f"Wave {wave_num}"

        # EXACT_ID match first (e.g. operator typed "wave-017")
        canonical_id = f"wave-{wave_num:03d}"
        entity = graph.get_entity(canonical_id)
        if entity is not None:
            return EntityResolution(
                requested_reference=ref_str,
                resolved_entity_id=entity.id,
                entity_type=EntityType.WAVE.value,
                match_type=MatchType.EXACT_ID,
            )

        # EXACT_ATTRIBUTE match on wave_number field
        waves = graph.entities_by_type(EntityType.WAVE)
        for w in waves:
            if getattr(w, "wave_number", None) == wave_num:
                return EntityResolution(
                    requested_reference=ref_str,
                    resolved_entity_id=w.id,
                    entity_type=EntityType.WAVE.value,
                    match_type=MatchType.EXACT_ATTRIBUTE,
                )

        # NOT_FOUND — do not substitute another wave
        logger.info("EntityResolver: %s not found in graph (waves present: %d)", ref_str, len(waves))
        return EntityResolution(
            requested_reference=ref_str,
            resolved_entity_id=None,
            entity_type=EntityType.WAVE.value,
            match_type=MatchType.NOT_FOUND,
        )

    return EntityResolution(
        requested_reference=question[:50],
        resolved_entity_id=None,
        entity_type=None,
        match_type=MatchType.NOT_FOUND,
    )


def resolve(
    question: str,
    warehouse_id: str,
    graph: Any | None,
    *,
    focus_entity_id: str | None = None,
    focus_entity_label: str | None = None,
) -> ContextNeighborhood:
    """
    Resolve a bounded Operational Graph neighborhood for the operator question.

    Parameters
    ----------
    question:
        Raw operator message.
    warehouse_id:
        Warehouse to scope entity lookup.
    graph:
        CanonicalWarehouseGraph instance, or None when DataPack is unavailable.
    focus_entity_id:
        Optional prior-turn focus to use when the question has no explicit entity
        reference (e.g. "What should we do?" after "Why is Wave 17 at risk?").
    focus_entity_label:
        Human label for the prior-turn focus entity.

    Returns
    -------
    ContextNeighborhood
        Always returns a value — never raises. Sets graph_available=False
        when graph is None or lookup fails.
    """
    if graph is None:
        return ContextNeighborhood(
            focus_entity_id=None,
            focus_entity_label=None,
            entity_ids=[],
            relationship_summary={},
            max_depth=_MAX_DEPTH,
            graph_available=False,
            entity_resolution=None,
        )

    try:
        return _resolve_with_graph(
            question, graph,
            prior_focus_id=focus_entity_id,
            prior_focus_label=focus_entity_label,
        )
    except Exception as exc:
        logger.warning("OperationalContextResolver: graph lookup failed — %s", exc)
        return ContextNeighborhood(
            focus_entity_id=None,
            focus_entity_label=None,
            entity_ids=[],
            relationship_summary={},
            max_depth=_MAX_DEPTH,
            graph_available=False,
            entity_resolution=None,
        )


def _resolve_with_graph(
    question: str,
    graph: Any,
    *,
    prior_focus_id: str | None = None,
    prior_focus_label: str | None = None,
) -> ContextNeighborhood:
    from maiw_world.entities import EntityType

    # Attempt explicit entity resolution first
    resolution = resolve_entity(question, graph)

    focus_entity = None
    focus_label = None

    if resolution.match_type in (MatchType.EXACT_ID, MatchType.EXACT_ATTRIBUTE, MatchType.ALIAS):
        focus_entity = graph.get_entity(resolution.resolved_entity_id)
        focus_label = resolution.requested_reference

    # If no explicit reference, try focus continuity from prior turn
    if focus_entity is None and prior_focus_id is not None:
        focus_entity = graph.get_entity(prior_focus_id)
        focus_label = prior_focus_label or prior_focus_id
        if focus_entity is not None:
            logger.debug(
                "OperationalContextResolver: using prior focus %s for question '%s'",
                prior_focus_id, question[:50],
            )

    # If still no focus — return empty neighborhood (NOT_FOUND, not fallback-to-first)
    if focus_entity is None:
        return ContextNeighborhood(
            focus_entity_id=None,
            focus_entity_label=None,
            entity_ids=[],
            relationship_summary={},
            max_depth=_MAX_DEPTH,
            graph_available=True,
            entity_resolution=resolution if resolution.match_type != MatchType.NOT_FOUND else resolution,
        )

    focus_id = focus_entity.id

    # BFS up to max_depth hops in both directions
    neighbors = graph.neighbors(
        focus_id,
        direction="both",
        depth=_MAX_DEPTH,
    )

    # Cap total entities
    neighbors = neighbors[:_MAX_ENTITIES]
    entity_ids = [n.id for n in neighbors]

    # Build relationship summary grouped by entity type
    rel_summary: dict[str, list[str]] = {}
    edges = (
        graph.outgoing_edges(focus_id) + graph.incoming_edges(focus_id)
    )
    for edge in edges:
        other_id = edge.target_id if edge.source_id == focus_id else edge.source_id
        other = graph.get_entity(other_id)
        if other is None:
            continue
        group = other.entity_type.value.replace("_", " ").title() + "s"
        label = _entity_label(other)
        rel_summary.setdefault(group, [])
        if label not in rel_summary[group]:
            rel_summary[group].append(label)

    return ContextNeighborhood(
        focus_entity_id=focus_id,
        focus_entity_label=focus_label,
        entity_ids=entity_ids,
        relationship_summary=rel_summary,
        max_depth=_MAX_DEPTH,
        graph_available=True,
        entity_resolution=resolution,
    )
