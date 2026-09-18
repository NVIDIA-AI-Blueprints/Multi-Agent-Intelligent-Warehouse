# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
WaveAgent — Phase 18H: SOP-Driven Agent Foundation.

Objective:
    Protect wave completion before carrier cutoff by identifying task sequencing
    or reprioritization opportunities and producing candidate wave interventions.

Contract:
    Input:  bounded_context (wave tasks, orders, carrier_cutoff)
    Output: WaveAssessment + CandidateWaveAction[]

Governance invariant:
    WaveAgent NEVER directly invokes WRITE capabilities.
    It NEVER calls ActionExecutor, DecisionEngine, or MCP write tools.
    All interventions are CandidateWaveAction objects that the parent agent
    (OperationsCoordinationAgent) includes in a RecommendedAction for governance.

SOP reference: wave.wave_risk_assessment v1.0

Agent vs Skill distinction:
    WaveAgent is a real agent (not a skill) because it:
    - owns a domain-specific objective
    - has task state
    - follows an SOP
    - reasons across multiple steps (status → orders → cutoff → critical_path → at_risk → options)
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

# ── WaveAgent definition ──────────────────────────────────────────────────────

WAVE_AGENT_DEFINITION = AgentDefinition(
    agent_id="wave",
    version="1.0",
    objective=(
        "Protect wave completion before carrier cutoff by identifying task sequencing "
        "or reprioritization opportunities and producing candidate wave interventions."
    ),
    domain="wave",
    triggers=[
        AgentTrigger(
            trigger_id="wave_risk_detected",
            trigger_type="wave_risk_detected",
            description="Wave has at_risk_count > 0 or pending_count high with approaching cutoff.",
        ),
        AgentTrigger(
            trigger_id="delegated_by_oca",
            trigger_type="operator_requests_resolution",
            description="OperationsCoordinationAgent delegated a wave risk assessment.",
        ),
    ],
    required_context=["wave", "carrier_cutoff"],
    allowed_capabilities=[
        "warehouse.wave.status",
        "warehouse.wave.inspect_tasks",
        "warehouse.wave.evaluate_critical_path",
        "warehouse.wave.evaluate_reprioritization",
    ],
    allowed_subagents=[],
    sop_id="wave.wave_risk_assessment",
    output_contract=(
        "WaveAssessment containing at_risk_task_count, pending_task_count, "
        "time_to_cutoff (minutes), primary_constraint classification, and "
        "CandidateWaveAction[] ordered by urgency. "
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
            TerminationCondition(condition_id="OBJECTIVE_MET", description="WaveAssessment produced."),
            TerminationCondition(condition_id="NO_SAFE_ACTION", description="No feasible reprioritization found."),
            TerminationCondition(condition_id="INSUFFICIENT_CONTEXT", description="Wave state unavailable."),
            TerminationCondition(condition_id="MAX_ITERATIONS", description="Iteration limit reached."),
        ],
    ),
)


# ── Output models ─────────────────────────────────────────────────────────────

class CandidateWaveAction(BaseModel):
    """
    A candidate wave intervention proposed by the WaveAgent.

    NOT an execution — a proposal for the parent agent to include in
    a RecommendedAction for governance evaluation.
    """

    action_id: str
    wave_id: str | None = None
    zone: str | None = None
    task_ids: list[str] = Field(default_factory=list)
    intervention_type: str = Field(
        description="One of: reprioritize | resequence | defer_low_priority | escalate."
    )
    estimated_impact_minutes: int | None = None
    priority: str = "high"
    rationale: str
    feasible: bool = True
    risk_notes: str | None = None


class WaveAssessment(BaseModel):
    """
    Structured assessment produced by the WaveAgent.

    This is the output contract of the WaveAgent.
    It is returned to the parent OperationsCoordinationAgent
    via the delegation result.
    """

    task_id: str = Field(description="Agent task ID that produced this assessment.")
    trace_id: str | None = None

    total_wave_tasks: int
    at_risk_task_count: int
    pending_task_count: int
    in_progress_task_count: int
    completed_task_count: int

    time_to_cutoff_minutes: int | None = Field(
        default=None,
        description="Minutes until soonest carrier cutoff. None if unknown.",
    )

    primary_constraint: str = Field(
        description=(
            "One of: sequencing | capacity | equipment_dependency | "
            "no_constraint | insufficient_data."
        )
    )
    constraint_summary: str

    at_risk_task_ids: list[str] = Field(default_factory=list)
    candidate_actions: list[CandidateWaveAction] = Field(default_factory=list)

    # Evidence
    facts_observed: list[str] = Field(default_factory=list)
    skills_consulted: list[str] = Field(default_factory=list)


# ── WaveAgent ─────────────────────────────────────────────────────────────────

class WaveAgent:
    """
    Wave domain agent — SOP-driven, governance-bounded.

    Objective: protect wave completion before carrier cutoff by identifying
    task sequencing or reprioritization opportunities.

    Output: WaveAssessment + CandidateWaveAction[]

    The WaveAgent NEVER:
    - calls ActionExecutor
    - calls DecisionEngine
    - invokes write MCP tools
    - produces a direct write action

    Dependencies are injected at construction time (same pattern as all MAIW agents).
    """

    DEFINITION = WAVE_AGENT_DEFINITION
    SOP_ID = "wave.wave_risk_assessment"
    SOP_VERSION = "1.0"

    def __init__(
        self,
        *,
        wave_skill: Optional[Any] = None,
        model_gateway: Optional[Any] = None,
    ) -> None:
        self._wave_skill = wave_skill
        self._model_gateway = model_gateway

    async def assess_wave_risk(
        self,
        *,
        task_id: str,
        trace_id: str,
        bounded_context: dict[str, Any],
        warehouse_id: str = "default",
    ) -> WaveAssessment:
        """
        Main entry point: assess wave risk in the given bounded context.

        Follows the wave_risk_assessment SOP:
        1. Read wave status
        2. Read outstanding orders and pending wave tasks
        3. Identify carrier cutoff
        4. Calculate critical path
        5. Identify at-risk tasks
        6. Evaluate reprioritization options
        7. Return WaveAssessment
        STOP.

        Parameters
        ----------
        task_id:       Agent task ID (from AgentTaskState).
        trace_id:      Propagated correlation ID.
        bounded_context:
            Extracted facts from the parent context. Must contain:
            - wave_tasks: list of wave task dicts
            - carrier_cutoff_iso: ISO8601 string of soonest carrier cutoff
            May contain: wave_id, zone_focus, orders.
        """
        import datetime

        facts: list[str] = []
        skills_consulted: list[str] = []

        # ── Step 1: read wave status ──────────────────────────────────────────
        wave_tasks: list[dict[str, Any]] = bounded_context.get("wave_tasks", [])
        total_wave_tasks = len(wave_tasks)

        pending = [t for t in wave_tasks if t.get("status") == "pending"]
        in_progress = [t for t in wave_tasks if t.get("status") == "in_progress"]
        completed = [t for t in wave_tasks if t.get("status") in ("completed", "done")]
        at_risk = [t for t in wave_tasks if t.get("at_risk") is True]

        facts.append(
            f"Wave: {total_wave_tasks} total tasks — "
            f"{len(pending)} pending, {len(in_progress)} in-progress, "
            f"{len(completed)} completed, {len(at_risk)} at-risk."
        )
        skills_consulted.append("warehouse.wave.status")
        skills_consulted.append("warehouse.wave.inspect_tasks")

        # ── Step 3: identify cutoff ───────────────────────────────────────────
        cutoff_iso: str | None = bounded_context.get("carrier_cutoff_iso")
        time_to_cutoff: int | None = None
        if cutoff_iso:
            try:
                cutoff_dt = datetime.datetime.fromisoformat(cutoff_iso.replace("Z", "+00:00"))
                now_dt = datetime.datetime.now(tz=datetime.timezone.utc)
                delta = cutoff_dt - now_dt
                time_to_cutoff = max(0, int(delta.total_seconds() / 60))
                facts.append(f"Carrier cutoff in {time_to_cutoff} minutes ({cutoff_iso}).")
            except (ValueError, TypeError):
                facts.append(f"Carrier cutoff ISO parse failed: {cutoff_iso!r}.")
        else:
            facts.append("No carrier cutoff provided in bounded context.")

        # ── Step 4: calculate critical path ──────────────────────────────────
        skills_consulted.append("warehouse.wave.evaluate_critical_path")

        # Tasks are "critical path" if pending and high priority or low deadline
        def _task_sort_key(t: dict[str, Any]) -> tuple:
            priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            p = priority_order.get(str(t.get("priority", "medium")).lower(), 2)
            deadline = str(t.get("deadline") or t.get("cutoff") or "9999")
            return (p, deadline)

        sorted_pending = sorted(pending, key=_task_sort_key)
        critical_path_tasks = sorted_pending[:5]

        # ── Step 5: identify at-risk tasks ────────────────────────────────────
        at_risk_task_ids: list[str] = []
        for t in at_risk:
            tid = str(t.get("task_id") or t.get("id") or "")
            if tid:
                at_risk_task_ids.append(tid)

        # Also flag critical path tasks with imminent cutoff
        if time_to_cutoff is not None and time_to_cutoff < 60:
            for t in critical_path_tasks:
                tid = str(t.get("task_id") or t.get("id") or "")
                if tid and tid not in at_risk_task_ids:
                    at_risk_task_ids.append(tid)

        facts.append(f"At-risk task IDs: {at_risk_task_ids or 'none'}.")

        # ── Step 6: evaluate reprioritization ────────────────────────────────
        skills_consulted.append("warehouse.wave.evaluate_reprioritization")

        candidate_actions: list[CandidateWaveAction] = []
        at_risk_count = len(at_risk_task_ids)

        if at_risk_count == 0:
            primary_constraint = "no_constraint"
            constraint_summary = "No at-risk tasks detected. Wave is on track."
        elif pending and sorted_pending:
            # Classify constraint
            has_low_priority_tasks = any(
                str(t.get("priority", "medium")).lower() == "low" for t in pending
            )
            primary_constraint = "sequencing" if has_low_priority_tasks else "capacity"
            constraint_summary = (
                f"{at_risk_count} tasks at risk of missing carrier cutoff. "
                f"Primary constraint: {primary_constraint}."
            )

            # Generate reprioritization options
            wave_id = str(bounded_context.get("wave_id") or "wave-unknown")

            # Option 1: defer low-priority tasks
            if has_low_priority_tasks:
                low_prio = [t for t in pending if str(t.get("priority", "")).lower() == "low"]
                candidate_actions.append(CandidateWaveAction(
                    action_id=f"{task_id}-wave-candidate-00",
                    wave_id=wave_id,
                    task_ids=[str(t.get("task_id") or t.get("id") or "") for t in low_prio[:3]],
                    intervention_type="defer_low_priority",
                    estimated_impact_minutes=15,
                    priority="high",
                    rationale=(
                        f"Defer {len(low_prio)} low-priority task(s) to free sequencing capacity "
                        f"for {at_risk_count} at-risk tasks."
                    ),
                    feasible=True,
                ))

            # Option 2: reprioritize at-risk tasks
            if at_risk_task_ids:
                candidate_actions.append(CandidateWaveAction(
                    action_id=f"{task_id}-wave-candidate-01",
                    wave_id=wave_id,
                    task_ids=at_risk_task_ids[:3],
                    intervention_type="reprioritize",
                    estimated_impact_minutes=10,
                    priority="critical",
                    rationale=(
                        f"Elevate {len(at_risk_task_ids[:3])} at-risk task(s) to critical priority "
                        f"to ensure completion before cutoff."
                    ),
                    feasible=True,
                    risk_notes=(
                        f"Cutoff is {time_to_cutoff} minutes away. "
                        "Reprioritization may displace lower-priority tasks."
                        if time_to_cutoff is not None else None
                    ),
                ))
        else:
            primary_constraint = "insufficient_data"
            constraint_summary = "Insufficient wave task data to classify constraint."

        return WaveAssessment(
            task_id=task_id,
            trace_id=trace_id,
            total_wave_tasks=total_wave_tasks,
            at_risk_task_count=at_risk_count,
            pending_task_count=len(pending),
            in_progress_task_count=len(in_progress),
            completed_task_count=len(completed),
            time_to_cutoff_minutes=time_to_cutoff,
            primary_constraint=primary_constraint,
            constraint_summary=constraint_summary,
            at_risk_task_ids=at_risk_task_ids,
            candidate_actions=candidate_actions,
            facts_observed=facts,
            skills_consulted=skills_consulted,
        )
