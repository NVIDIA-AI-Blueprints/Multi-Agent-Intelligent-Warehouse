# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
CanonicalWarehouseGraph — in-memory typed graph of warehouse world state.

IMPORTANT DISTINCTION:
- Operational Graph (this class): warehouse reality/context
  (equipment, labor, tasks, waves, orders, inventory)
- Decision Graph (Phase 13 DecisionGraph): MAIW reasoning/provenance
  (agents, skills, proposals, decisions)

They are linked by entity IDs, snapshot IDs, and trace IDs — never merged.

The graph supports:
- O(1) entity lookup by ID
- O(1) edge lookup by ID
- Adjacency indexes for outgoing/incoming edge traversal
- Temporal edge filtering (valid_from/valid_to)
- BFS neighbors up to configurable depth
- Structural integrity validation via validate()
"""

from __future__ import annotations

from collections import deque
from datetime import datetime

from .edges import RELATIONSHIP_COMPATIBILITY, RelationshipType, WarehouseEdge
from .entities import EntityType, WarehouseEntity
from .events import OperationalEvent


class CanonicalWarehouseGraph:
    """
    In-memory typed graph of a warehouse world.

    Entities and edges are immutable (Pydantic frozen models).
    The graph itself is mutable — entities, edges, and events can be added.
    Removal is not supported in Phase 14A (add-only log semantics).
    """

    def __init__(self) -> None:
        self._entities: dict[str, WarehouseEntity] = {}   # id → entity
        self._edges: dict[str, WarehouseEdge] = {}         # edge.id → edge
        self._events: list[OperationalEvent] = []

        # Adjacency indexes for O(1) neighbor lookups
        self._outgoing: dict[str, list[str]] = {}   # source_id → [edge_id]
        self._incoming: dict[str, list[str]] = {}   # target_id → [edge_id]

    # ── Entity operations ──────────────────────────────────────────────────────

    def add_entity(self, entity: WarehouseEntity) -> None:
        """
        Add an entity to the graph.

        Raises ValueError if entity.id already exists in the graph.
        """
        if entity.id in self._entities:
            raise ValueError(
                f"Entity with id '{entity.id}' already exists in the graph. "
                "Entity IDs must be unique."
            )
        self._entities[entity.id] = entity
        # Initialize adjacency index entries
        if entity.id not in self._outgoing:
            self._outgoing[entity.id] = []
        if entity.id not in self._incoming:
            self._incoming[entity.id] = []

    def get_entity(self, entity_id: str) -> WarehouseEntity | None:
        """Return the entity with the given ID, or None if not found."""
        return self._entities.get(entity_id)

    def has_entity(self, entity_id: str) -> bool:
        """Return True if an entity with the given ID exists in the graph."""
        return entity_id in self._entities

    def entities_by_type(self, entity_type: EntityType) -> list[WarehouseEntity]:
        """Return all entities of the given type."""
        return [e for e in self._entities.values() if e.entity_type == entity_type]

    @property
    def entity_count(self) -> int:
        """Total number of entities in the graph."""
        return len(self._entities)

    # ── Edge operations ────────────────────────────────────────────────────────

    def add_edge(self, edge: WarehouseEdge) -> None:
        """
        Add a typed relationship edge to the graph.

        Raises ValueError if:
        - edge.id already exists
        - source entity not in graph
        - target entity not in graph
        - relationship_type is incompatible with source/target entity types
        - self-loop on a relationship type (all current types prohibit self-loops)
        """
        if edge.id in self._edges:
            raise ValueError(
                f"Edge with id '{edge.id}' already exists in the graph."
            )

        # Ensure source entity exists
        source_entity = self._entities.get(edge.source_id)
        if source_entity is None:
            raise ValueError(
                f"Edge '{edge.id}': source entity '{edge.source_id}' not found in graph. "
                "Add the source entity before adding the edge."
            )

        # Ensure target entity exists
        target_entity = self._entities.get(edge.target_id)
        if target_entity is None:
            raise ValueError(
                f"Edge '{edge.id}': target entity '{edge.target_id}' not found in graph. "
                "Add the target entity before adding the edge."
            )

        # Validate relationship type compatibility
        allowed_pairs = RELATIONSHIP_COMPATIBILITY.get(edge.relationship_type, set())
        pair = (source_entity.entity_type, target_entity.entity_type)
        if pair not in allowed_pairs:
            raise ValueError(
                f"Edge '{edge.id}': relationship {edge.relationship_type.value} "
                f"is not valid between {source_entity.entity_type.value} "
                f"and {target_entity.entity_type.value}. "
                f"Allowed pairs: {allowed_pairs}"
            )

        # Self-loops are not permitted for any current relationship types
        if edge.is_self_loop():
            raise ValueError(
                f"Edge '{edge.id}': self-loop detected "
                f"(source_id == target_id == '{edge.source_id}'). "
                "Self-loops are not permitted."
            )

        self._edges[edge.id] = edge

        # Update adjacency indexes
        self._outgoing.setdefault(edge.source_id, []).append(edge.id)
        self._incoming.setdefault(edge.target_id, []).append(edge.id)

    def get_edge(self, edge_id: str) -> WarehouseEdge | None:
        """Return the edge with the given ID, or None if not found."""
        return self._edges.get(edge_id)

    def outgoing_edges(
        self,
        entity_id: str,
        relationship_type: RelationshipType | None = None,
        at: datetime | None = None,
    ) -> list[WarehouseEdge]:
        """
        Return edges where entity_id is the source.

        Optionally filter by relationship_type and/or temporal validity at ``at``.
        """
        edge_ids = self._outgoing.get(entity_id, [])
        edges = [self._edges[eid] for eid in edge_ids if eid in self._edges]

        if relationship_type is not None:
            edges = [e for e in edges if e.relationship_type == relationship_type]

        if at is not None:
            edges = [e for e in edges if e.is_active(at)]

        return edges

    def incoming_edges(
        self,
        entity_id: str,
        relationship_type: RelationshipType | None = None,
        at: datetime | None = None,
    ) -> list[WarehouseEdge]:
        """
        Return edges where entity_id is the target.

        Optionally filter by relationship_type and/or temporal validity at ``at``.
        """
        edge_ids = self._incoming.get(entity_id, [])
        edges = [self._edges[eid] for eid in edge_ids if eid in self._edges]

        if relationship_type is not None:
            edges = [e for e in edges if e.relationship_type == relationship_type]

        if at is not None:
            edges = [e for e in edges if e.is_active(at)]

        return edges

    def neighbors(
        self,
        entity_id: str,
        relationship_type: RelationshipType | None = None,
        direction: str = "outgoing",   # "outgoing" | "incoming" | "both"
        depth: int = 1,
        at: datetime | None = None,
    ) -> list[WarehouseEntity]:
        """
        BFS traversal up to ``depth`` hops from entity_id.

        Returns deduplicated entities reachable within depth hops,
        excluding the starting entity itself.

        direction:
          "outgoing" — follow source→target direction
          "incoming" — follow target→source direction
          "both"     — follow edges in either direction
        """
        if direction not in ("outgoing", "incoming", "both"):
            raise ValueError(
                f"direction must be 'outgoing', 'incoming', or 'both', got '{direction}'"
            )

        visited: set[str] = {entity_id}
        result: list[WarehouseEntity] = []
        # Queue of (current_id, remaining_depth)
        queue: deque[tuple[str, int]] = deque([(entity_id, depth)])

        while queue:
            current_id, remaining = queue.popleft()
            if remaining <= 0:
                continue

            # Collect neighbor entity IDs based on direction
            neighbor_ids: set[str] = set()

            if direction in ("outgoing", "both"):
                for edge in self.outgoing_edges(current_id, relationship_type, at):
                    neighbor_ids.add(edge.target_id)

            if direction in ("incoming", "both"):
                for edge in self.incoming_edges(current_id, relationship_type, at):
                    neighbor_ids.add(edge.source_id)

            for nid in neighbor_ids:
                if nid not in visited:
                    visited.add(nid)
                    entity = self._entities.get(nid)
                    if entity is not None:
                        result.append(entity)
                    queue.append((nid, remaining - 1))

        return result

    @property
    def edge_count(self) -> int:
        """Total number of edges in the graph."""
        return len(self._edges)

    # ── Event operations ───────────────────────────────────────────────────────

    def add_event(self, event: OperationalEvent) -> None:
        """
        Append an operational event to the event log.

        Raises ValueError if the event's entity_id is not found in the graph.
        """
        if event.entity_id not in self._entities:
            raise ValueError(
                f"Event '{event.event_id}': entity_id '{event.entity_id}' "
                "not found in graph. Add the entity before logging an event for it."
            )
        self._events.append(event)

    def events_for_entity(self, entity_id: str) -> list[OperationalEvent]:
        """Return all events where entity_id is the primary target."""
        return [e for e in self._events if e.entity_id == entity_id]

    @property
    def event_count(self) -> int:
        """Total number of events in the event log."""
        return len(self._events)

    # ── Validation ─────────────────────────────────────────────────────────────

    def validate(self) -> "ValidationReport":
        """Run all structural integrity checks and return a ValidationReport."""
        from .validation import validate_graph
        return validate_graph(self)

    # ── Summary ────────────────────────────────────────────────────────────────

    def summary(self) -> dict[str, int]:
        """
        Returns a flat count summary:
        - entity_{type} for each EntityType
        - edge_{relationship} for each RelationshipType present
        - event_count total
        """
        result: dict[str, int] = {}

        # Entity counts by type
        for et in EntityType:
            result[f"entity_{et.value}"] = 0
        for entity in self._entities.values():
            key = f"entity_{entity.entity_type.value}"
            result[key] = result.get(key, 0) + 1

        # Edge counts by relationship
        for rt in RelationshipType:
            result[f"edge_{rt.value}"] = 0
        for edge in self._edges.values():
            key = f"edge_{edge.relationship_type.value}"
            result[key] = result.get(key, 0) + 1

        result["entity_count"] = self.entity_count
        result["edge_count"] = self.edge_count
        result["event_count"] = self.event_count

        return result
