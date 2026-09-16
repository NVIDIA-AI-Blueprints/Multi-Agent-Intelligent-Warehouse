# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Phase 18B: OperationalContextSnapshot replay helper.

Converts a stored OperationalContextSnapshot into the same reduced model
context that was used during the original Copilot turn — deterministically,
without fresh graph traversal and without substituting LIVE current state.

This is the evaluation reproducibility contract:
  historical OperationalContextSnapshot → deterministic ModelRequest context

Design note on WS2 dependency:
  OperationalContextSnapshot is defined in apps/api/maiw_api/copilot/models.py
  (merged in Phase 17F / Workstream 2).  The import path is:
      from maiw_api.copilot.models import OperationalContextSnapshot
  This module uses TYPE_CHECKING guards so maiw-models stays importable even
  when maiw_api is not installed (e.g. unit tests that mock the snapshot).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Import only for type hints — avoids hard dependency on maiw_api at runtime.
    try:
        from maiw_api.copilot.models import OperationalContextSnapshot
    except ImportError:
        OperationalContextSnapshot = Any  # type: ignore[assignment, misc]


# ── Reduced context ───────────────────────────────────────────────────────────


@dataclass
class ReplayContext:
    """
    Reduced model context derived from a stored OperationalContextSnapshot.

    This is what was actually supplied to the model during the original turn.
    It contains only the bounded graph projection — no hidden reasoning,
    no chain-of-thought, no live state substitution.

    Fields:
        context_snapshot_id — links back to the original snapshot for tracing
        warehouse_id        — warehouse scope
        dataset_id          — DataPack dataset (immutable semantic content)
        datapack_checksum   — semantic checksum for content identity
        warehouse_state_snapshot_id — warehouse state at capture time (or None)
        focus_entity_id     — the entity that was the focus of the turn
        focus_entity_type   — type of the focus entity
        focus_label         — human-readable label for the focus entity
        node_summaries      — list of {"entity_id", "entity_type", "attributes"} dicts
        edge_summaries      — list of {"source_id", "target_id", "relationship"} dicts
        entity_count        — number of context nodes (bounded at capture time)
        relationship_count  — number of context edges
        truncated           — True when BFS was capped at max_entities during capture
        messages            — the system + user message list suitable for ModelRequest
    """

    context_snapshot_id: str
    warehouse_id: str
    dataset_id: str
    datapack_checksum: str
    warehouse_state_snapshot_id: str | None
    focus_entity_id: str
    focus_entity_type: str
    focus_label: str
    node_summaries: list[dict[str, Any]]
    edge_summaries: list[dict[str, Any]]
    entity_count: int
    relationship_count: int
    truncated: bool
    messages: list[dict[str, Any]]  # ready for ModelRequest.messages


# ── Replay helper ─────────────────────────────────────────────────────────────


def replay_context_from_snapshot(
    snapshot: "OperationalContextSnapshot",
    user_prompt: str,
    system_prompt: str | None = None,
) -> ReplayContext:
    """
    Convert a stored OperationalContextSnapshot into a ReplayContext.

    This reproduces the exact bounded context that was visible to the model
    during the original turn — no fresh graph traversal, no live state.

    Args:
        snapshot:      Stored OperationalContextSnapshot from WS2.
        user_prompt:   The user message to replay (from EvaluationCase.prompt).
        system_prompt: Optional system instruction override. When None, a
                       minimal warehouse-grounded system prompt is generated
                       from the snapshot metadata.

    Returns:
        ReplayContext with messages pre-formatted for ModelRequest.messages.
    """
    # Build node summaries from snapshot nodes (reduced projection).
    node_summaries = [
        {
            "entity_id": node.entity_id,
            "entity_type": node.entity_type,
            "label": node.label,
            "attributes": node.attributes,
        }
        for node in snapshot.nodes
    ]

    edge_summaries = [
        {
            "source_id": edge.source_id,
            "target_id": edge.target_id,
            "relationship": edge.relationship,
        }
        for edge in snapshot.edges
    ]

    # Build the system prompt from the snapshot if not overridden.
    if system_prompt is None:
        system_prompt = _build_system_prompt(snapshot, node_summaries, edge_summaries)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    return ReplayContext(
        context_snapshot_id=snapshot.context_snapshot_id,
        warehouse_id=snapshot.warehouse_id,
        dataset_id=snapshot.dataset_id,
        datapack_checksum=snapshot.datapack_checksum,
        warehouse_state_snapshot_id=snapshot.warehouse_state_snapshot_id,
        focus_entity_id=snapshot.focus_entity_id,
        focus_entity_type=snapshot.focus_entity_type,
        focus_label=snapshot.focus_label,
        node_summaries=node_summaries,
        edge_summaries=edge_summaries,
        entity_count=snapshot.entity_count,
        relationship_count=snapshot.relationship_count,
        truncated=snapshot.truncated,
        messages=messages,
    )


def _build_system_prompt(
    snapshot: "OperationalContextSnapshot",
    node_summaries: list[dict[str, Any]],
    edge_summaries: list[dict[str, Any]],
) -> str:
    """
    Build a minimal grounded system prompt from snapshot data.

    This mirrors what Copilot service builds during a live turn, but using
    only the stored bounded graph — no live lookups.

    The prompt is intentionally compact: evaluation graders test the model's
    ability to reason over the supplied context, not its parametric knowledge.
    """
    import json

    context_block = json.dumps(
        {
            "warehouse_id": snapshot.warehouse_id,
            "dataset_id": snapshot.dataset_id,
            "focus_entity": {
                "id": snapshot.focus_entity_id,
                "type": snapshot.focus_entity_type,
                "label": snapshot.focus_label,
            },
            "entities": node_summaries,
            "relationships": edge_summaries,
            "entity_count": snapshot.entity_count,
            "relationship_count": snapshot.relationship_count,
            "truncated": snapshot.truncated,
        },
        indent=2,
    )

    return (
        "You are MAIW Copilot, an AI assistant for warehouse operations.\n"
        "Answer questions using ONLY the operational context provided below.\n"
        "Do not fabricate entity IDs, names, or facts not present in the context.\n\n"
        f"OPERATIONAL CONTEXT (captured {snapshot.captured_at}):\n"
        f"{context_block}"
    )


# ── Mock snapshot (for tests without WS2 runtime) ────────────────────────────


@dataclass
class MockSnapshotNode:
    """Minimal node stub for unit tests that do not have maiw_api installed."""

    entity_id: str
    entity_type: str
    label: str
    attributes: dict[str, Any]


@dataclass
class MockSnapshotEdge:
    """Minimal edge stub for unit tests that do not have maiw_api installed."""

    source_id: str
    target_id: str
    relationship: str


@dataclass
class MockOperationalContextSnapshot:
    """
    Self-contained mock snapshot for evaluation unit tests.

    Use when maiw_api is not installed or when you need a deterministic
    test fixture that does not depend on the WS2 runtime.
    """

    context_snapshot_id: str
    conversation_id: str = "eval-test-conv"
    turn_id: str = "eval-test-turn"
    trace_id: str = "eval-test-trace"
    warehouse_id: str = "wh-test-001"
    dataset_id: str = "test-dataset-v1"
    datapack_checksum: str = "abc123def456"
    warehouse_state_snapshot_id: str | None = None
    focus_entity_id: str = "wave-17"
    focus_entity_type: str = "Wave"
    focus_label: str = "Wave 17"
    depth: int = 2
    truncated: bool = False
    nodes: list[MockSnapshotNode] = None  # type: ignore[assignment]
    edges: list[MockSnapshotEdge] = None  # type: ignore[assignment]
    entity_count: int = 0
    relationship_count: int = 0
    relationship_summary: dict = None  # type: ignore[assignment]
    captured_at: str = "2026-09-11T00:00:00Z"

    def __post_init__(self) -> None:
        if self.nodes is None:
            self.nodes = []
        if self.edges is None:
            self.edges = []
        if self.relationship_summary is None:
            self.relationship_summary = {}
        self.entity_count = len(self.nodes)
        self.relationship_count = len(self.edges)
