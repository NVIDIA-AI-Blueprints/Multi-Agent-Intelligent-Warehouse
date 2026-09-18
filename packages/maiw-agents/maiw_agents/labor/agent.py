# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
LaborAgent — Phase 18H: SOP-Driven Agent Foundation.

Objective:
    Determine whether labor is constraining an operational objective
    and produce feasible labor interventions for the parent agent to consider.

Contract:
    Input:  bounded_context (workers, pending tasks, carrier cutoff, zone)
    Output: LaborAssessment + CandidateLaborAction[]

Governance invariant:
    LaborAgent NEVER directly invokes WRITE capabilities.
    It NEVER calls ActionExecutor, DecisionEngine, or MCP write tools.
    All interventions are CandidateLaborAction objects that the parent agent
    (OperationsCoordinationAgent) includes in a RecommendedAction for governance.

SOP reference: labor.labor_constraint_assessment v1.0

Agent vs Skill distinction:
    LaborAgent is a real agent (not a skill) because it:
    - owns a domain-specific objective
    - has task state
    - follows an SOP
    - reasons across multiple steps (read workers, read tasks, evaluate, rank)
    - has escalation and termination semantics
    - produces a structured assessment — not a single bounded capability
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from pydantic import BaseModel, Field

from ..contracts.agent import (
    AgentDefinition,
    AgentTrigger,
    GovernanceBoundary,
    TerminationPolicy,
    TerminationCondition,
)

logger = logging.getLogger(__name__)

# ── LaborAgent definition ─────────────────────────────────────────────────────

LABOR_AGENT_DEFINITION = AgentDefinition(
    agent_id="labor",
    version="1.0",
    objective=(
        "Determine whether labor is constraining an operational objective "
        "and produce feasible labor interventions."
    ),
    domain="labor",
    triggers=[
        AgentTrigger(
            trigger_id="labor_constraint_detected",
            trigger_type="labor_constraint_detected",
            description="Labor utilization or idle-worker state indicates a constraint.",
        ),
        AgentTrigger(
            trigger_id="delegated_by_oca",
            trigger_type="operator_requests_resolution",
            description="OperationsCoordinationAgent delegated a labor assessment.",
        ),
    ],
    required_context=["worker", "task"],
    allowed_capabilities=[
        "warehouse.labor.capacity",
        "warehouse.labor.inspect_workers",
        "warehouse.labor.inspect_tasks",
        "warehouse.labor.evaluate_reallocation",
    ],
    allowed_subagents=[],
    sop_id="labor.labor_constraint_assessment",
    output_contract=(
        "LaborAssessment containing idle/active worker counts, unassigned task count, "
        "primary constraint classification, and CandidateLaborAction[] ordered by priority. "
        "Never a write action."
    ),
    governance_boundary=GovernanceBoundary(
        allowed_capability_classes=["READ", "ANALYTICAL"],
        may_invoke_action_executor=False,
        may_invoke_decision_engine=False,
    ),
    termination_policy=TerminationPolicy(
        max_iterations=5,
        stop_conditions=[
            TerminationCondition(condition_id="OBJECTIVE_MET", description="LaborAssessment produced."),
            TerminationCondition(condition_id="NO_SAFE_ACTION", description="No feasible reallocation found."),
            TerminationCondition(condition_id="INSUFFICIENT_CONTEXT", description="Labor state unavailable."),
            TerminationCondition(condition_id="MAX_ITERATIONS", description="Iteration limit reached."),
        ],
    ),
)


# ── Output models ─────────────────────────────────────────────────────────────

class CandidateLaborAction(BaseModel):
    """
    A candidate labor intervention proposed by the LaborAgent.

    NOT an execution — a proposal for the parent agent to include in
    a RecommendedAction for governance evaluation.
    """

    action_id: str
    task_id: str
    worker_id: str
    zone: str | None = None
    task_type: str | None = None
    priority: str = "medium"
    rationale: str
    feasible: bool = True
    constraint_notes: str | None = None


class LaborAssessment(BaseModel):
    """
    Structured assessment produced by the LaborAgent.

    This is the output contract of the LaborAgent.
    It is returned to the parent OperationsCoordinationAgent
    via the delegation result.
    """

    task_id: str = Field(description="Agent task ID that produced this assessment.")
    trace_id: str | None = None

    total_workers: int
    idle_workers: int
    active_workers: int
    pending_task_count: int
    unassigned_task_count: int

    primary_constraint: str = Field(
        description=(
            "One of: idle_workers_available | skill_gap | zone_mismatch | "
            "no_idle_workers | no_constraint."
        )
    )
    constraint_summary: str

    candidate_actions: list[CandidateLaborAction] = Field(default_factory=list)

    # Evidence
    facts_observed: list[str] = Field(default_factory=list)
    skills_consulted: list[str] = Field(default_factory=list)


# ── LaborAgent ────────────────────────────────────────────────────────────────

class LaborAgent:
    """
    Labor domain agent — SOP-driven, governance-bounded.

    Objective: determine whether labor is constraining an operational objective
    and produce feasible labor interventions.

    Output: LaborAssessment + CandidateLaborAction[]

    The LaborAgent NEVER:
    - calls ActionExecutor
    - calls DecisionEngine
    - invokes write MCP tools
    - produces a direct write action

    Dependencies are injected at construction time (same pattern as all MAIW agents).
    """

    DEFINITION = LABOR_AGENT_DEFINITION
    SOP_ID = "labor.labor_constraint_assessment"
    SOP_VERSION = "1.0"

    def __init__(
        self,
        *,
        labor_skill: Optional[Any] = None,
        model_gateway: Optional[Any] = None,
    ) -> None:
        self._labor_skill = labor_skill
        self._model_gateway = model_gateway

    async def assess_labor_constraint(
        self,
        *,
        task_id: str,
        trace_id: str,
        bounded_context: dict[str, Any],
        warehouse_id: str = "default",
    ) -> LaborAssessment:
        """
        Main entry point: assess the labor constraint in the given bounded context.

        Follows the labor_constraint_assessment SOP:
        1. Read workers from bounded_context
        2. Read pending tasks from bounded_context
        3. Evaluate assignment imbalance
        4. Identify capacity deficit
        5. Check worker/zone/skill constraints
        6. Generate feasible interventions
        7. Rank interventions
        8. Return LaborAssessment
        STOP.

        Parameters
        ----------
        task_id:       Agent task ID (from AgentTaskState).
        trace_id:      Propagated correlation ID.
        bounded_context:
            Extracted facts from the parent context. Must contain:
            - workers: list of worker state dicts
            - pending_tasks: list of pending task dicts
            May contain: carrier_cutoff, zone_focus.
        """
        facts: list[str] = []
        skills_consulted: list[str] = []

        # ── Step 1: read workers ──────────────────────────────────────────────
        workers: list[dict[str, Any]] = bounded_context.get("workers", [])
        total_workers = len(workers)
        idle_workers = [
            w for w in workers
            if w.get("status") == "active" and w.get("current_task_id") is None
        ]
        active_workers = [
            w for w in workers
            if w.get("status") == "active" and w.get("current_task_id") is not None
        ]
        facts.append(
            f"Labor: {total_workers} total workers, "
            f"{len(idle_workers)} idle, {len(active_workers)} assigned."
        )
        skills_consulted.append("warehouse.labor.capacity")

        # ── Step 2: read tasks ────────────────────────────────────────────────
        pending_tasks: list[dict[str, Any]] = bounded_context.get("pending_tasks", [])
        unassigned = [
            t for t in pending_tasks
            if t.get("status") == "pending" and t.get("assigned_to") is None
        ]
        facts.append(
            f"Tasks: {len(pending_tasks)} pending, {len(unassigned)} unassigned."
        )
        skills_consulted.append("warehouse.labor.inspect_tasks")

        # ── Step 3: evaluate imbalance ────────────────────────────────────────
        if not idle_workers and unassigned:
            primary_constraint = "no_idle_workers"
            constraint_summary = (
                f"{len(unassigned)} tasks are unassigned but no idle workers are available."
            )
        elif idle_workers and unassigned:
            primary_constraint = "idle_workers_available"
            constraint_summary = (
                f"{len(idle_workers)} idle workers can be allocated to "
                f"{len(unassigned)} unassigned tasks."
            )
        elif not unassigned:
            primary_constraint = "no_constraint"
            constraint_summary = "All pending tasks have worker assignments."
        else:
            primary_constraint = "no_constraint"
            constraint_summary = "No labor constraint detected."

        facts.append(f"Primary constraint: {primary_constraint}.")
        skills_consulted.append("warehouse.labor.evaluate_reallocation")

        # ── Steps 4-7: generate and rank interventions ────────────────────────
        candidate_actions: list[CandidateLaborAction] = []

        if idle_workers and unassigned:
            # Sort tasks by priority then deadline
            def _task_sort_key(t: dict[str, Any]) -> tuple:
                priority_order = {"high": 0, "medium": 1, "low": 2}
                p = priority_order.get(str(t.get("priority", "medium")).lower(), 1)
                deadline = str(t.get("deadline") or "9999")
                return (p, deadline)

            sorted_tasks = sorted(unassigned, key=_task_sort_key)
            sorted_workers = sorted(
                idle_workers,
                key=lambda w: (
                    # prefer same-zone workers
                    0 if sorted_tasks[0].get("zone") and w.get("zone") == sorted_tasks[0].get("zone") else 1,
                    w.get("worker_id", ""),
                ),
            )

            for i, task in enumerate(sorted_tasks[:3]):
                if i >= len(sorted_workers):
                    break
                worker = sorted_workers[i]
                task_id_val = str(task.get("task_id") or task.get("id") or f"task_{i}")
                worker_id = str(worker.get("worker_id") or worker.get("id") or f"worker_{i}")
                zone = str(task.get("zone") or "")
                worker_zone = str(worker.get("zone") or "")

                feasible = True
                constraint_note = None
                if zone and worker_zone and zone != worker_zone:
                    feasible = True  # cross-zone is still feasible, note it
                    constraint_note = f"Worker zone ({worker_zone}) differs from task zone ({zone}) — cross-zone allocation."

                candidate_actions.append(CandidateLaborAction(
                    action_id=f"{task_id}-labor-candidate-{i:02d}",
                    task_id=task_id_val,
                    worker_id=worker_id,
                    zone=zone or None,
                    task_type=str(task.get("task_type") or task.get("kind") or ""),
                    priority=str(task.get("priority") or "medium"),
                    rationale=(
                        f"Worker {worker_id} is idle and can be allocated to "
                        f"{task.get('task_type', 'task')} task {task_id_val}"
                        + (f" in zone {zone}" if zone else "")
                        + "."
                    ),
                    feasible=feasible,
                    constraint_notes=constraint_note,
                ))

        return LaborAssessment(
            task_id=task_id,
            trace_id=trace_id,
            total_workers=total_workers,
            idle_workers=len(idle_workers),
            active_workers=len(active_workers),
            pending_task_count=len(pending_tasks),
            unassigned_task_count=len(unassigned),
            primary_constraint=primary_constraint,
            constraint_summary=constraint_summary,
            candidate_actions=candidate_actions,
            facts_observed=facts,
            skills_consulted=skills_consulted,
        )
