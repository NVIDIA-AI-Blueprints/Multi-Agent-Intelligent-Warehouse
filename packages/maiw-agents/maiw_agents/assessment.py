# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Canonical MAIW agent assessment contracts.

OperationalAssessment is the structured output of an agent that has observed
warehouse state and produced recommendations. It is NOT a demo contract.

Architecture
------------
  WarehouseStateSnapshot (sealed, immutable)
      ↓
  OperationsCoordinationAgent.analyze_disruption()
      ↓
  ModelGateway → LLM
      ↓
  OperationalAssessment  (LLM recommends via RecommendedAction)
      ↓
  Proposal builders (construct ActionProposal from RecommendedAction)
      ↓
  DecisionEngine → ActionExecutor → MCP write

Invariants
----------
- LLM populates RecommendedAction fields; it never constructs ActionProposal or MCP params.
- RecommendedAction.capability is a semantic name, not an MCP tool name.
- All fields are optional except domain, capability, target, objective, rationale, priority.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

# ── RecommendedAction ──────────────────────────────────────────────────────────

CapabilityName = Literal[
    # Equipment
    "warehouse.equipment.assign",
    "warehouse.equipment.release",
    "warehouse.equipment.schedule_maintenance",
    # Labor
    "warehouse.labor.allocate",
    # Wave
    "warehouse.wave.reprioritize",
]

DomainName = Literal["equipment", "labor", "wave", "inventory"]

Priority = Literal["critical", "high", "medium", "low"]


class RecommendedAction(BaseModel):
    """
    A single operational recommendation produced by the LLM.

    The LLM identifies WHAT to do (domain, capability, target, objective) and
    WHY (rationale, priority). It never specifies HOW (MCP parameters) —
    that is the responsibility of the canonical proposal builders.

    Fields
    ------
    domain:
        Operational domain: equipment | labor | wave | inventory.
    capability:
        Semantic capability name (matches MCP tool name but is not a call).
    target:
        The primary entity to act on: asset_id, task_id, zone, or wave_id.
    objective:
        Plain-English description of the intended outcome.
    rationale:
        Why this action is needed — derived from observed facts.
    priority:
        Urgency of this recommendation.
    subtype:
        Optional hint for proposal builders (e.g. 'emergency' for maintenance).
    """

    domain: DomainName
    capability: CapabilityName
    target: str
    objective: str
    rationale: str
    priority: Priority
    subtype: str | None = None


# ── OperationalAssessment ──────────────────────────────────────────────────────


class OperationalAssessment(BaseModel):
    """
    Structured output of OperationsCoordinationAgent.analyze_disruption().

    One assessment per analyze_disruption() call. All fields are populated
    by the agent — never by calling code or the LLM response parser directly.

    Fields
    ------
    trace_id:
        Correlation ID propagated through State → Model → Proposal → Decision
        → Execution → SSE. Set by the caller of analyze_disruption().
    snapshot_id:
        UUID of the WarehouseStateSnapshot that was analyzed.
    warehouse_id:
        Warehouse the snapshot belongs to.
    assessed_at:
        UTC timestamp when the assessment was produced.
    summary:
        One or two sentences describing the situation (no chain-of-thought).
    severity:
        Overall severity of the observed disruption.
    domains_affected:
        Which operational domains are involved.
    facts_observed:
        Key factual observations extracted from the snapshot (not LLM reasoning).
    skills_consulted:
        Semantic capability names read during state assembly.
    recommendations:
        Ordered list of recommended actions (most urgent first).
    model_id:
        Model that produced the assessment (from ModelResponse).
    routing_rule:
        Routing rule that selected the model (from ModelRouteDecision).
    routing_reason:
        Human-readable routing rationale.
    latency_ms:
        End-to-end model call latency.
    """

    trace_id: str
    snapshot_id: str
    warehouse_id: str
    assessed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    summary: str
    severity: Priority
    domains_affected: list[DomainName] = Field(default_factory=list)
    facts_observed: list[str] = Field(default_factory=list)
    skills_consulted: list[str] = Field(default_factory=list)
    recommendations: list[RecommendedAction] = Field(default_factory=list)

    model_id: str
    routing_rule: str
    routing_reason: str
    latency_ms: float
