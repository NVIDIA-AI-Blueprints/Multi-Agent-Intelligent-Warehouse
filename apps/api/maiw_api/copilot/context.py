# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
OperationalContextResolver — bounded graph neighborhood for a Copilot turn.

Deterministic graph BFS (no vector retrieval). Bounded by max_depth and
max_entities to prevent passing the full 51k-entity DataPack to Nemotron.

Phase 15B: depth=2, max_entities=50.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .models import ContextNeighborhood

logger = logging.getLogger(__name__)

_MAX_DEPTH = 2
_MAX_ENTITIES = 50

# Patterns that indicate an operator is asking about a specific wave number.
_WAVE_NUMBER_RE = re.compile(r"\bwave\s*(\d+)\b", re.IGNORECASE)


def _extract_wave_number(question: str) -> int | None:
    m = _WAVE_NUMBER_RE.search(question)
    return int(m.group(1)) if m else None


def _entity_label(entity: Any) -> str:
    """Best-effort human label from a WarehouseEntity."""
    for attr in ("wave_number", "worker_id", "asset_id", "sku", "zone_id",
                 "location_id", "dock_door_id", "order_id", "task_id",
                 "shift_id", "carrier_id", "entity_id"):
        val = getattr(entity, attr, None)
        if val is not None:
            return str(val)
    return getattr(entity, "entity_id", "unknown")


def _relationship_label(rel_type: Any) -> str:
    name = str(rel_type)
    return name.split(".")[-1].replace("_", " ").title()


def resolve(
    question: str,
    warehouse_id: str,
    graph: Any | None,
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
        )

    try:
        return _resolve_with_graph(question, graph)
    except Exception as exc:
        logger.warning("OperationalContextResolver: graph lookup failed — %s", exc)
        return ContextNeighborhood(
            focus_entity_id=None,
            focus_entity_label=None,
            entity_ids=[],
            relationship_summary={},
            max_depth=_MAX_DEPTH,
            graph_available=False,
        )


def _resolve_with_graph(question: str, graph: Any) -> ContextNeighborhood:
    from maiw_world.entities import EntityType

    focus_entity = None
    focus_label = None

    # Try to find a specific wave entity
    wave_num = _extract_wave_number(question)
    if wave_num is not None:
        waves = graph.entities_by_type(EntityType.WAVE)
        for w in waves:
            if getattr(w, "wave_number", None) == wave_num:
                focus_entity = w
                focus_label = f"Wave {wave_num}"
                break
        if focus_entity is None and waves:
            # Fallback: use the first wave (demo scenario always has waves)
            focus_entity = waves[0]
            focus_label = f"Wave {getattr(focus_entity, 'wave_number', '?')}"

    # Fallback: no specific entity — use first at-risk wave if identifiable
    if focus_entity is None:
        waves = graph.entities_by_type(EntityType.WAVE)
        if waves:
            focus_entity = waves[0]
            focus_label = f"Wave {getattr(focus_entity, 'wave_number', '?')}"

    if focus_entity is None:
        return ContextNeighborhood(
            focus_entity_id=None,
            focus_entity_label=None,
            entity_ids=[],
            relationship_summary={},
            max_depth=_MAX_DEPTH,
            graph_available=True,
        )

    focus_id = focus_entity.entity_id

    # BFS up to max_depth hops in both directions
    neighbors = graph.neighbors(
        focus_id,
        direction="both",
        depth=_MAX_DEPTH,
    )

    # Cap total entities
    neighbors = neighbors[:_MAX_ENTITIES]
    entity_ids = [n.entity_id for n in neighbors]

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
    )
