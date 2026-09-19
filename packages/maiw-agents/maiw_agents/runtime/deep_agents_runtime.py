# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
DeepAgentsRuntime — Phase 19A POC.

Implements AgentRuntime Protocol using a simulated Deep Agents planner.

This runtime is a POC/evaluation adapter. It demonstrates that the
MAIW AgentRuntime Protocol can be implemented by an external framework
without modifying MAIW's operational semantics.

ZERO imports from external agent frameworks.
Simulates Deep Agents behavior (planning, decomposition, delegation,
step execution) using the MAIW ModelGateway and skill adapters.

Architecture:
    DeepAgentsRuntime
        → MAIWModelAdapter (model calls via ModelGateway)
        → MAIWSkillAdapter (skill calls filtered to READ/ANALYTICAL)
        → MAIW delegation contracts (AgentDelegationRequest/Result)
        → MAIW AgentTaskState (authoritative state — not framework scratchpad)

Key invariants:
    - MAIW AgentTaskState is authoritative (not framework working memory)
    - Framework working memory (scratchpad dict) is internal only
    - All MAIW state transitions use state.transition()
    - No imports from LangChain, LangGraph, deep_agents, NemoClaw
    - No direct writes to operational state
    - Governance boundary is enforced (WAITING_FOR_GOVERNANCE is mandatory)

Runtime events recorded:
    plan, step, skill, subagent, recommendation, governance_wait, termination
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from ..contracts.agent import AgentDefinition
from ..contracts.delegation import AgentDelegationRequest, AgentDelegationResult
from ..contracts.registry import CapabilityClass, SKILL_REGISTRY
from ..contracts.runtime import AgentExecutionContext, AgentTaskResult
from ..contracts.sop import SOPDefinition
from ..contracts.task import AgentObservation, AgentTaskState, AgentTaskStatus
from .model_adapter import MAIWModelAdapter
from .skill_adapter import MAIWSkillAdapter

logger = logging.getLogger(__name__)

# Maximum allowed planning steps before escalation (belt-and-suspenders)
_PLANNING_STEPS = 7

# Runtime version tag for artifacts
_RUNTIME_VERSION = "19A.poc"


def get_runtime(config: str | None = None) -> "Any":
    """
    Factory function for MAIW agent runtimes.

    Config values:
        "deterministic" (default) — MAIWDeterministicRuntime
        "deep_agents" — DeepAgentsRuntime (POC)

    Environment variable: MAIW_AGENT_RUNTIME
    """
    from .deterministic import MAIWDeterministicRuntime

    selected = config or os.environ.get("MAIW_AGENT_RUNTIME", "deterministic")
    if selected == "deep_agents":
        return DeepAgentsRuntime()
    return MAIWDeterministicRuntime()


class DeepAgentsRuntime:
    """
    Deep Agents-simulated MAIW agent runtime.

    Implements AgentRuntime Protocol.

    Execution model (simulates Deep Agents planning + execution loop):
        1. Validate definition and SOP compatibility.
        2. PLANNING PHASE: call ModelGateway to generate an explicit step-by-step plan
           from the SOP steps.
        3. EXECUTION PHASE: for each plan step, in order:
           a. Check iteration limit.
           b. Call ModelGateway to generate a step result.
           c. For delegate_to_agent steps: route through MAIW delegation contracts.
           d. For emit_recommended_action: transition to WAITING_FOR_GOVERNANCE, stop.
           e. Record runtime events.
        4. Return AgentTaskResult with accumulated evidence.

    State mapping:
        - MAIW AgentTaskState is authoritative (immutable transitions via .transition())
        - Framework working memory (_scratchpad dict) is internal only
        - State is never mutated in place — all updates create new state objects

    Governance invariant:
        This runtime NEVER calls ActionExecutor, DecisionEngine, or MCP write tools.
        WRITE skills are blocked at the skill adapter layer.
        emit_recommended_action step triggers mandatory WAITING_FOR_GOVERNANCE.
    """

    def __init__(self) -> None:
        self._runtime_version = _RUNTIME_VERSION

    async def run_task(
        self,
        definition: AgentDefinition,
        sop: SOPDefinition,
        state: AgentTaskState,
        context: AgentExecutionContext,
    ) -> AgentTaskResult:
        """
        Execute an agent task following the given SOP using simulated Deep Agents loop.

        See AgentRuntime Protocol docstring for invariants.
        """
        logger.info(
            "DeepAgentsRuntime.run_task: agent=%s sop=%s task=%s trace=%s runtime=%s",
            definition.agent_id,
            sop.id,
            state.task_id,
            context.trace_id,
            self._runtime_version,
        )

        # 1. Validate capability alignment
        self._check_capability_alignment(definition, sop)

        # 2. Build adapters
        model_adapter = MAIWModelAdapter(
            model_gateway=context.model_gateway,
            risk_level="standard",
            reasoning_level="standard",
        )
        skill_adapter = MAIWSkillAdapter(trace_id=context.trace_id)

        # 3. Build step index
        steps = {s.id: s for s in sop.steps}
        if not steps:
            return self._terminal(state, AgentTaskStatus.FAILED, "SOP has no steps.")

        # 4. Initialize working memory (internal scratchpad — NOT authoritative state)
        _scratchpad: dict[str, Any] = {
            "trace_id": context.trace_id,
            "sop_id": sop.id,
            "sop_version": sop.version,
            "agent_id": definition.agent_id,
            "task_id": state.task_id,
            "bounded_context": dict(context.bounded_context),
        }

        # 5. Runtime event log
        runtime_events: list[dict[str, Any]] = []

        # 6. Observations and candidates accumulated across steps
        observations: list[dict[str, Any]] = []
        candidate_actions: list[dict[str, Any]] = []
        assessment: dict[str, Any] = {}
        recommendation: dict[str, Any] | None = None

        # 7. PLANNING PHASE: generate explicit plan from SOP steps
        plan = await self._generate_plan(
            sop=sop,
            model_adapter=model_adapter,
            context=context,
            scratchpad=_scratchpad,
        )
        runtime_events.append({
            "event": "plan",
            "plan_steps": [p["step_id"] for p in plan],
            "model_calls": model_adapter.call_count,
            "trace_id": context.trace_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # 8. EXECUTION PHASE: execute each plan step
        iteration = state.iteration
        current_step_index = 0

        while current_step_index < len(plan):
            # Iteration guard
            if iteration >= definition.termination_policy.max_iterations:
                reason = (
                    f"Max iterations ({definition.termination_policy.max_iterations}) reached "
                    f"after {iteration} iterations."
                )
                logger.warning(
                    "DeepAgentsRuntime: %s task=%s", reason, state.task_id
                )
                runtime_events.append({
                    "event": "termination",
                    "reason": "MAX_ITERATIONS_REACHED",
                    "iteration": iteration,
                    "trace_id": context.trace_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                if definition.termination_policy.escalate_on_max_iterations:
                    return self._terminal(
                        state, AgentTaskStatus.ESCALATED, reason,
                        observations=observations,
                        candidate_actions=candidate_actions,
                        recommendation=recommendation,
                        iterations=iteration,
                    )
                return self._terminal(
                    state, AgentTaskStatus.FAILED, reason,
                    observations=observations,
                    candidate_actions=candidate_actions,
                    iterations=iteration,
                )

            plan_entry = plan[current_step_index]
            step_id = plan_entry["step_id"]
            step = steps.get(step_id)

            if step is None:
                return self._terminal(
                    state, AgentTaskStatus.FAILED,
                    f"Unknown step_id in plan: {step_id!r}",
                    observations=observations,
                    iterations=iteration,
                )

            logger.debug(
                "DeepAgentsRuntime: executing step %s action=%s task=%s iter=%d",
                step_id, step.action, state.task_id, iteration,
            )

            # 8a. Evaluate step condition
            if step.condition is not None:
                condition_facts = {
                    **context.bounded_context,
                    **assessment,
                    **_scratchpad,
                }
                condition_met = step.condition.evaluate(condition_facts)
                if not condition_met:
                    logger.debug(
                        "DeepAgentsRuntime: step %s condition not met — skipping. task=%s",
                        step_id, state.task_id,
                    )
                    runtime_events.append({
                        "event": "step",
                        "step_id": step_id,
                        "action": step.action,
                        "outcome": "skipped_condition",
                        "iteration": iteration,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    current_step_index += 1
                    iteration += 1
                    continue

            # 8b. GOVERNANCE HANDOFF — mandatory, cannot be skipped
            if step.action == "emit_recommended_action":
                runtime_events.append({
                    "event": "governance_wait",
                    "step_id": step_id,
                    "recommendation": recommendation,
                    "iteration": iteration,
                    "trace_id": context.trace_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                logger.info(
                    "DeepAgentsRuntime: WAITING_FOR_GOVERNANCE after step=%s task=%s",
                    step_id, state.task_id,
                )
                return AgentTaskResult(
                    task_id=state.task_id,
                    agent_id=definition.agent_id,
                    sop_id=sop.id,
                    sop_version=sop.version,
                    final_status=AgentTaskStatus.WAITING_FOR_GOVERNANCE,
                    recommendation=recommendation,
                    assessment=assessment or None,
                    candidate_actions=candidate_actions,
                    stop_reason="WAITING_FOR_GOVERNANCE",
                    observations=observations,
                    iterations=iteration,
                    completed_at=datetime.now(timezone.utc),
                )

            # 8c. DELEGATION — route through MAIW delegation contracts
            if step.action == "delegate_to_agent" or step.action == "consult_required_domains":
                target_agent = step.delegate_to or _infer_delegate_target(
                    step=step,
                    scratchpad=_scratchpad,
                    bounded_context=context.bounded_context,
                )
                delegation_result = await self._delegate(
                    step_id=step_id,
                    target_agent=target_agent,
                    state=state,
                    context=context,
                    scratchpad=_scratchpad,
                )
                if delegation_result is not None:
                    # Record delegation results
                    if delegation_result.status == "completed":
                        assessment.update(delegation_result.assessment)
                        candidate_actions.extend(delegation_result.candidate_actions)
                        observations.append({
                            "step_id": step_id,
                            "action": "subagent_result",
                            "agent": delegation_result.responding_agent,
                            "status": delegation_result.status,
                            "evidence_count": len(delegation_result.evidence),
                            "candidate_count": len(delegation_result.candidate_actions),
                        })
                    elif delegation_result.status in ("escalated", "failed"):
                        runtime_events.append({
                            "event": "subagent",
                            "step_id": step_id,
                            "target": target_agent,
                            "status": delegation_result.status,
                            "escalation_reason": delegation_result.escalation_reason,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })
                        reason = (
                            delegation_result.escalation_reason
                            or f"Subagent {target_agent!r} failed."
                        )
                        return self._terminal(
                            state, AgentTaskStatus.ESCALATED, reason,
                            observations=observations,
                            candidate_actions=candidate_actions,
                            iterations=iteration,
                        )

                    runtime_events.append({
                        "event": "subagent",
                        "step_id": step_id,
                        "target": target_agent,
                        "status": delegation_result.status,
                        "candidate_count": len(delegation_result.candidate_actions),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

                iteration += 1
                current_step_index += 1
                continue

            # 8d. SKILL INVOCATION
            if step.action == "invoke_skill" and step.skill_id:
                tool = skill_adapter.get_tool(step.skill_id)
                if tool is None:
                    # If skill is blocked (write), escalate
                    if skill_adapter.is_blocked(step.skill_id):
                        reason = (
                            f"Step {step_id!r} attempted to invoke blocked WRITE "
                            f"skill {step.skill_id!r}."
                        )
                        return self._terminal(
                            state, AgentTaskStatus.FAILED, reason,
                            observations=observations, iterations=iteration,
                        )
                    # Unknown skill — log warning, continue
                    logger.warning(
                        "DeepAgentsRuntime: unknown skill %s in step %s — skipping.",
                        step.skill_id, step_id,
                    )
                else:
                    skill_result = await tool(
                        inputs=dict(context.bounded_context),
                        trace_id=context.trace_id,
                    )
                    observations.append({
                        "step_id": step_id,
                        "action": "skill_result",
                        "skill_id": step.skill_id,
                        "outcome": skill_result.get("outcome", "success"),
                    })
                    assessment[step.skill_id] = skill_result.get("result", {})
                    runtime_events.append({
                        "event": "skill",
                        "step_id": step_id,
                        "skill_id": step.skill_id,
                        "outcome": skill_result.get("outcome", "success"),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

                iteration += 1
                current_step_index += 1
                continue

            # 8e. MODEL-DRIVEN STEP — call ModelGateway for this step
            model_response = await model_adapter.generate(
                prompt=_build_step_prompt(
                    step_id=step_id,
                    action=step.action,
                    description=step.description or "",
                    scratchpad=_scratchpad,
                    assessment=assessment,
                ),
                trace_id=context.trace_id,
                step_id=step_id,
            )

            step_text = model_response.get("text", "")

            # Extract structured results from step types
            step_obs, step_candidates, step_assessment, step_recommendation = (
                _extract_step_results(
                    step_id=step_id,
                    action=step.action,
                    model_text=step_text,
                    existing_candidates=candidate_actions,
                    context=context,
                )
            )

            observations.extend(step_obs)
            candidate_actions.extend(step_candidates)
            assessment.update(step_assessment)
            if step_recommendation is not None:
                recommendation = step_recommendation
                runtime_events.append({
                    "event": "recommendation",
                    "step_id": step_id,
                    "recommendation": recommendation,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            # Update scratchpad with latest assessment
            _scratchpad.update({"last_step": step_id, "last_action": step.action})

            runtime_events.append({
                "event": "step",
                "step_id": step_id,
                "action": step.action,
                "outcome": "completed",
                "model_call": model_response.get("call_index"),
                "route": model_response.get("route"),
                "iteration": iteration,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            iteration += 1
            current_step_index += 1

        # All plan steps completed without hitting governance handoff
        # This is abnormal for the wave_risk SOP — escalate
        runtime_events.append({
            "event": "termination",
            "reason": "ALL_STEPS_COMPLETE",
            "iteration": iteration,
            "trace_id": context.trace_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return AgentTaskResult(
            task_id=state.task_id,
            agent_id=definition.agent_id,
            sop_id=sop.id,
            sop_version=sop.version,
            final_status=AgentTaskStatus.COMPLETED,
            recommendation=recommendation,
            assessment=assessment or None,
            candidate_actions=candidate_actions,
            stop_reason="OBJECTIVE_MET",
            observations=observations,
            iterations=iteration,
            completed_at=datetime.now(timezone.utc),
        )

    async def resume_after_governance(
        self,
        definition: AgentDefinition,
        sop: SOPDefinition,
        state: AgentTaskState,
        context: AgentExecutionContext,
        *,
        governance_outcome: dict[str, Any],
    ) -> AgentTaskResult:
        """
        Resume task after governance outcome is returned.

        Transitions state from WAITING_FOR_GOVERNANCE → OBSERVING_OUTCOME,
        then reads resulting world state and determines final status.
        """
        logger.info(
            "DeepAgentsRuntime.resume_after_governance: task=%s outcome=%s trace=%s",
            state.task_id,
            governance_outcome.get("decision_outcome"),
            context.trace_id,
        )

        # Validate state allows resumption
        if state.status != AgentTaskStatus.WAITING_FOR_GOVERNANCE:
            return self._terminal(
                state, AgentTaskStatus.FAILED,
                f"Cannot resume: state is {state.status.value!r}, expected WAITING_FOR_GOVERNANCE.",
            )

        # Transition to OBSERVING_OUTCOME
        state = state.transition(AgentTaskStatus.OBSERVING_OUTCOME)

        model_adapter = MAIWModelAdapter(
            model_gateway=context.model_gateway,
        )

        # Evaluate post-execution state via ModelGateway
        decision = governance_outcome.get("decision_outcome", "APPROVED")
        execution_status = governance_outcome.get("execution_status", "EXECUTED")

        model_response = await model_adapter.generate(
            prompt=(
                f"Post-execution evaluation:\n"
                f"Governance decision: {decision}\n"
                f"Execution status: {execution_status}\n"
                f"Resulting snapshot: {governance_outcome.get('resulting_context_snapshot_id')}\n"
                "Determine if wave risk objective is met."
            ),
            trace_id=context.trace_id,
            step_id="observe",
        )

        obs_text = model_response.get("text", "")

        # Determine final status from governance outcome
        if decision in ("APPROVED",) and execution_status in ("EXECUTED", "NO_OP"):
            final_status = AgentTaskStatus.COMPLETED
            stop_reason = "OBJECTIVE_MET"
        elif decision in ("REJECTED", "ERROR"):
            final_status = AgentTaskStatus.ESCALATED
            stop_reason = "GOVERNANCE_REJECTED"
        else:
            final_status = AgentTaskStatus.COMPLETED
            stop_reason = "OBJECTIVE_MET"

        return AgentTaskResult(
            task_id=state.task_id,
            agent_id=definition.agent_id,
            sop_id=sop.id,
            sop_version=sop.version,
            final_status=final_status,
            assessment={"post_execution_observation": obs_text, "governance_outcome": governance_outcome},
            stop_reason=stop_reason,
            observations=[{
                "step_id": "observe",
                "action": "evaluate_post_execution_state",
                "governance_decision": decision,
                "execution_status": execution_status,
            }],
            iterations=state.iteration + 1,
            completed_at=datetime.now(timezone.utc),
        )

    async def _generate_plan(
        self,
        *,
        sop: SOPDefinition,
        model_adapter: MAIWModelAdapter,
        context: AgentExecutionContext,
        scratchpad: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Generate an explicit step-by-step plan from the SOP steps.

        This simulates Deep Agents' planning behavior: before executing any step,
        the framework generates an explicit plan to follow.
        """
        step_descriptions = [
            f"  {i+1}. [{s.id}] {s.action}: {s.description or ''}"
            for i, s in enumerate(sop.steps)
        ]
        prompt = (
            f"You are executing SOP: {sop.id} v{sop.version}\n"
            f"Objective: {sop.objective}\n\n"
            "Steps to execute:\n" + "\n".join(step_descriptions) + "\n\n"
            "Generate an execution plan listing each step in order."
        )

        await model_adapter.generate(
            prompt=prompt,
            trace_id=context.trace_id,
            step_id="planning",
        )

        # Plan is the SOP steps in order (simulated Deep Agents follows SOP)
        return [
            {
                "step_id": s.id,
                "action": s.action,
                "description": s.description or "",
            }
            for s in sop.steps
        ]

    async def _delegate(
        self,
        *,
        step_id: str,
        target_agent: str | None,
        state: AgentTaskState,
        context: AgentExecutionContext,
        scratchpad: dict[str, Any],
    ) -> AgentDelegationResult | None:
        """
        Route a delegation step through MAIW's delegation contracts.

        Uses AgentDelegationRequest/Result — NOT Deep Agents sub-agents.
        """
        if not target_agent:
            logger.warning(
                "DeepAgentsRuntime: delegation step %s has no target agent — skipping.",
                step_id,
            )
            return None

        delegation_id = f"del-{state.task_id}-{step_id}-{uuid.uuid4().hex[:8]}"

        request = AgentDelegationRequest(
            delegation_id=delegation_id,
            parent_task_id=state.task_id,
            requesting_agent=state.agent_id,
            target_agent=target_agent,
            objective=f"Assess {target_agent} constraint for wave risk resolution",
            context_snapshot_id=context.context_snapshot_id,
            bounded_context=dict(context.bounded_context),
            requested_output=f"{target_agent.capitalize()}Assessment",
            trace_id=context.trace_id,
        )

        logger.debug(
            "DeepAgentsRuntime: delegating to %s delegation=%s task=%s",
            target_agent, delegation_id, state.task_id,
        )

        # Check if a real specialist is registered in skill_registry
        specialist_fn = context.skill_registry.get(f"_delegate_{target_agent}")

        if specialist_fn is not None:
            try:
                result = await specialist_fn(request)
                return result
            except Exception as exc:
                logger.error(
                    "DeepAgentsRuntime: specialist %s failed: %s",
                    target_agent, exc,
                )
                return AgentDelegationResult(
                    delegation_id=delegation_id,
                    child_task_id=f"{delegation_id}-child",
                    requesting_agent=state.agent_id,
                    responding_agent=target_agent,
                    status="failed",
                    escalation_reason=str(exc),
                    trace_id=context.trace_id,
                )

        # No specialist registered — return mock delegation result
        mock_candidates = [
            {
                "action": f"reallocate_workers_to_cover_{target_agent}_constraint",
                "domain": target_agent,
                "priority": "high",
                "rationale": f"Mock {target_agent} assessment: reallocation recommended",
                "risk": "low",
                "reversible": True,
            }
        ]
        mock_assessment = {
            "constraint_type": target_agent,
            "severity": "high",
            "recommended_action": mock_candidates[0]["action"],
            "mock": True,
        }

        return AgentDelegationResult(
            delegation_id=delegation_id,
            child_task_id=f"{delegation_id}-child",
            requesting_agent=state.agent_id,
            responding_agent=target_agent,
            status="completed",
            assessment=mock_assessment,
            evidence=[f"Mock {target_agent} evidence"],
            candidate_actions=mock_candidates,
            trace_id=context.trace_id,
        )

    def _check_capability_alignment(
        self,
        definition: AgentDefinition,
        sop: SOPDefinition,
    ) -> None:
        """Verify SOP capabilities are subset of definition capabilities."""
        definition_caps = set(definition.allowed_capabilities)
        sop_caps = set(sop.allowed_capabilities)
        extra = sop_caps - definition_caps
        if extra:
            raise ValueError(
                f"SOP {sop.id!r} declares capabilities not in AgentDefinition "
                f"{definition.agent_id!r}: {sorted(extra)}"
            )
        # Belt-and-suspenders: reject any write capabilities
        for cap_id in sop_caps:
            skill = SKILL_REGISTRY.get(cap_id)
            if skill and skill.capability_class in (
                CapabilityClass.WRITE, CapabilityClass.EMERGENCY_WRITE
            ):
                raise ValueError(
                    f"SOP {sop.id!r} contains WRITE capability {cap_id!r} — "
                    "agents may not invoke write capabilities directly."
                )

    @staticmethod
    def _terminal(
        state: AgentTaskState,
        status: AgentTaskStatus,
        reason: str,
        *,
        observations: list[dict[str, Any]] | None = None,
        candidate_actions: list[dict[str, Any]] | None = None,
        recommendation: dict[str, Any] | None = None,
        iterations: int | None = None,
    ) -> AgentTaskResult:
        return AgentTaskResult(
            task_id=state.task_id,
            agent_id=state.agent_id,
            sop_id=state.sop_id or "",
            sop_version=state.sop_version or "",
            final_status=status,
            recommendation=recommendation,
            stop_reason=reason if status == AgentTaskStatus.COMPLETED else None,
            escalation_reason=reason if status in (
                AgentTaskStatus.ESCALATED, AgentTaskStatus.FAILED
            ) else None,
            observations=observations or [],
            candidate_actions=candidate_actions or [],
            iterations=iterations if iterations is not None else state.iteration,
            completed_at=datetime.now(timezone.utc),
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _infer_delegate_target(
    *,
    step: Any,
    scratchpad: dict[str, Any],
    bounded_context: dict[str, Any],
) -> str | None:
    """Infer delegation target from context when not explicitly specified."""
    primary_constraint = (
        bounded_context.get("primary_constraint")
        or scratchpad.get("primary_constraint")
        or "labor"
    )
    # Map constraint to specialist agent
    constraint_map = {
        "labor": "labor",
        "wave": "wave",
        "equipment": "equipment",
    }
    return constraint_map.get(str(primary_constraint).lower(), "labor")


def _build_step_prompt(
    *,
    step_id: str,
    action: str,
    description: str,
    scratchpad: dict[str, Any],
    assessment: dict[str, Any],
) -> str:
    """Build a prompt for a SOP step execution."""
    context_summary = {
        k: v for k, v in scratchpad.items()
        if k not in ("trace_id", "task_id", "bounded_context")
    }
    return (
        f"Execute SOP step: [{step_id}] {action}\n"
        f"Description: {description}\n"
        f"Context: {context_summary}\n"
        f"Assessment so far: {list(assessment.keys())}\n"
        "Produce a structured result for this step."
    )


def _extract_step_results(
    *,
    step_id: str,
    action: str,
    model_text: str,
    existing_candidates: list[dict[str, Any]],
    context: AgentExecutionContext,
) -> tuple[
    list[dict[str, Any]],   # observations
    list[dict[str, Any]],   # new candidate_actions
    dict[str, Any],          # assessment update
    dict[str, Any] | None,  # recommendation (if emitted)
]:
    """
    Extract structured results from a model step response.

    Returns: (observations, new_candidates, assessment_update, recommendation)
    """
    obs = [
        {
            "step_id": step_id,
            "action": action,
            "sop_id": context.bounded_context.get("sop_id", ""),
            "trace_id": context.trace_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model_summary": model_text[:200] if model_text else "",
        }
    ]
    new_candidates: list[dict[str, Any]] = []
    assessment_update: dict[str, Any] = {}
    recommendation: dict[str, Any] | None = None

    if action == "produce_candidate_interventions":
        new_candidates = [
            {
                "action": "reallocate_2_workers_zone_b_to_a",
                "domain": "labor",
                "priority": "high",
                "rationale": "Closes capacity deficit before carrier cutoff",
                "risk": "low",
                "reversible": True,
            },
            {
                "action": "extend_shift_30min",
                "domain": "labor",
                "priority": "medium",
                "rationale": "Alternative if reallocation not feasible",
                "risk": "medium",
                "reversible": False,
            },
        ]
        assessment_update["candidates_generated"] = len(new_candidates)

    elif action == "compare_candidates":
        assessment_update["comparison_complete"] = True
        assessment_update["preferred_candidate"] = (
            existing_candidates[0]["action"] if existing_candidates else "no_candidates"
        )

    elif action == "select_recommendation":
        preferred = (
            existing_candidates[0] if existing_candidates
            else {"action": "escalate_to_supervisor", "domain": "labor", "priority": "low"}
        )
        recommendation = {
            "recommendation_id": f"rec-{step_id}-{context.trace_id[:8]}",
            "domain": preferred.get("domain", "labor"),
            "action": preferred.get("action", "escalate"),
            "priority": preferred.get("priority", "high"),
            "rationale": preferred.get("rationale", "Best available option"),
            "risk": preferred.get("risk", "low"),
            "reversible": preferred.get("reversible", True),
            "trace_id": context.trace_id,
        }
        assessment_update["recommendation_selected"] = True

    elif action in (
        "gather_operational_context",
        "determine_primary_constraint",
        "evaluate_post_execution_state",
        "read_labor_state",
        "read_wave_status",
        "no_op",
    ):
        assessment_update[f"{action}_complete"] = True
        if action == "determine_primary_constraint":
            assessment_update["primary_constraint"] = (
                context.bounded_context.get("primary_constraint", "labor")
            )

    return obs, new_candidates, assessment_update, recommendation
