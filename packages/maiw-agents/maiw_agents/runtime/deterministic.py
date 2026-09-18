# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIWDeterministicRuntime — Phase 18H.8.

The minimal MAIW agent runtime that implements the AgentRuntime Protocol.
Executes an agent task by following SOP steps in order, deterministically.

NOT a Deep Agents runtime — no LLM loop, no tool-call autonomy.
The agent produces an assessment or recommendation by running a fixed,
auditable sequence of steps.

Deep Agents integration seam:
    A future DeepAgentsRuntime will implement the same AgentRuntime Protocol.
    MAIW operational semantics (AgentDefinition, SOPDefinition, AgentTaskState,
    delegation contracts, output contracts) are unchanged — only the runtime
    implementation changes.

Architecture position:
    AgentRuntime.run_task() is called by the parent system (CopilotService or
    OperationsCoordinationAgent._delegate_to_specialist()), NOT by any external
    framework. The runtime does NOT call ActionExecutor or DecisionEngine.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ..contracts.agent import AgentDefinition
from ..contracts.delegation import AgentDelegationRequest, AgentDelegationResult
from ..contracts.registry import CapabilityClass, SKILL_REGISTRY
from ..contracts.runtime import AgentExecutionContext, AgentRuntime, AgentTaskResult
from ..contracts.sop import SOPDefinition
from ..contracts.task import AgentTaskState, AgentTaskStatus, is_valid_transition

logger = logging.getLogger(__name__)


class MAIWDeterministicRuntime:
    """
    Deterministic MAIW agent runtime.

    Implements AgentRuntime Protocol.

    Execution model:
        1. Validate definition and SOP are compatible.
        2. For each SOP step, in order:
           a. Check iteration limit.
           b. Evaluate step condition (skip if condition not met).
           c. Run step action (currently: log and advance — specialists
              inject results via bounded_context pre-loaded before run_task).
           d. Advance to next_step_id.
        3. On terminal step, transition state to COMPLETED.
        4. Return AgentTaskResult.

    Governance invariant:
        This runtime NEVER calls ActionExecutor, DecisionEngine, or MCP write tools.
        Steps with action type WRITE are rejected at runtime (they should never
        appear in an SOP — validate_sop() would reject them).

    Phase 18H implementation note:
        The step executor for specialist agents (LaborAgent, WaveAgent) is provided
        by the specialist agent classes themselves via handle_delegation(). The runtime
        coordinates delegation by routing delegate_to steps to the appropriate
        specialist registered in the context skill_registry.
    """

    def __init__(self) -> None:
        pass

    async def run_task(
        self,
        definition: AgentDefinition,
        sop: SOPDefinition,
        state: AgentTaskState,
        context: AgentExecutionContext,
    ) -> AgentTaskResult:
        """
        Execute an agent task following the given SOP.

        See AgentRuntime Protocol docstring for invariants.
        """
        logger.info(
            "MAIWDeterministicRuntime.run_task: agent=%s sop=%s task=%s trace=%s",
            definition.agent_id,
            sop.id,
            state.task_id,
            context.trace_id,
        )

        # Validate capability alignment
        self._check_capability_alignment(definition, sop)

        # Build step index
        steps = {s.id: s for s in sop.steps}
        if not steps:
            return self._terminal(state, AgentTaskStatus.FAILED, "SOP has no steps.")

        current_step_id = sop.steps[0].id
        observations: list[dict[str, Any]] = []
        candidate_actions: list[dict[str, Any]] = []
        assessment: dict[str, Any] = {}
        iteration = state.iteration

        while current_step_id is not None:
            # Iteration guard
            if iteration >= definition.termination_policy.max_iterations:
                reason = f"Max iterations ({definition.termination_policy.max_iterations}) reached."
                logger.warning(
                    "MAIWDeterministicRuntime: %s — escalating. task=%s",
                    reason,
                    state.task_id,
                )
                if definition.termination_policy.escalate_on_max_iterations:
                    return self._terminal(state, AgentTaskStatus.ESCALATED, reason, observations=observations)
                return self._terminal(state, AgentTaskStatus.FAILED, reason, observations=observations)

            step = steps.get(current_step_id)
            if step is None:
                return self._terminal(
                    state, AgentTaskStatus.FAILED,
                    f"Unknown step_id: {current_step_id!r}",
                    observations=observations,
                )

            # Reject WRITE step actions (must never appear in SOP — belt-and-suspenders)
            if step.action in ("write", "execute", "mutate"):
                return self._terminal(
                    state, AgentTaskStatus.FAILED,
                    f"Step {step.id!r} has forbidden write action {step.action!r}.",
                    observations=observations,
                )

            logger.debug(
                "MAIWDeterministicRuntime: executing step %s.%s action=%s task=%s",
                sop.id, step.id, step.action, state.task_id,
            )

            # Evaluate step condition (skip if condition not met)
            if step.condition is not None:
                condition_facts = {
                    **context.bounded_context,
                    **assessment,
                }
                condition_met = step.condition.evaluate(condition_facts)
                if not condition_met:
                    logger.debug(
                        "MAIWDeterministicRuntime: step %s condition not met, skipping. task=%s",
                        step.id, state.task_id,
                    )
                    current_step_id = step.next_step_id
                    iteration += 1
                    continue

            # Run the step — dispatch to action handlers
            step_obs, step_candidates, step_assessment = await self._run_step(
                step_id=step.id,
                action=step.action,
                definition=definition,
                sop=sop,
                context=context,
                accumulated_assessment=assessment,
            )
            observations.extend(step_obs)
            candidate_actions.extend(step_candidates)
            assessment.update(step_assessment)
            iteration += 1

            # Terminal step check — if no next_step_id, we're done
            next_step = step.next_step_id
            current_step_id = next_step

        # All steps complete — objective met
        return AgentTaskResult(
            task_id=state.task_id,
            agent_id=definition.agent_id,
            sop_id=sop.id,
            sop_version=sop.version,
            final_status=AgentTaskStatus.COMPLETED,
            assessment=assessment or None,
            candidate_actions=candidate_actions,
            observations=observations,
            iterations=iteration,
            stop_reason="OBJECTIVE_MET",
            completed_at=datetime.now(timezone.utc),
        )

    async def _run_step(
        self,
        *,
        step_id: str,
        action: str,
        definition: AgentDefinition,
        sop: SOPDefinition,
        context: AgentExecutionContext,
        accumulated_assessment: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
        """
        Dispatch a single SOP step to the appropriate executor.

        Returns: (observations, candidate_actions, assessment_update)

        For the deterministic runtime, most steps are handled by the
        specialist agent pre-loading results into bounded_context.
        This method records the step execution and extracts results.
        """
        obs: list[dict[str, Any]] = [
            {
                "step_id": step_id,
                "action": action,
                "sop_id": sop.id,
                "agent_id": definition.agent_id,
                "trace_id": context.trace_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ]
        candidates: list[dict[str, Any]] = []
        assessment_update: dict[str, Any] = {}

        # For return/terminal steps, extract candidate_actions from context
        if action in ("return_labor_assessment", "return_wave_assessment", "return_assessment"):
            result = context.bounded_context.get("_agent_result")
            if result is not None:
                # Pydantic model → dict
                if hasattr(result, "model_dump"):
                    result_dict = result.model_dump()
                else:
                    result_dict = dict(result)
                assessment_update["result"] = result_dict
                raw_candidates = result_dict.get("candidate_actions", [])
                candidates = raw_candidates if isinstance(raw_candidates, list) else []

        return obs, candidates, assessment_update

    def _check_capability_alignment(
        self,
        definition: AgentDefinition,
        sop: SOPDefinition,
    ) -> None:
        """
        Verify the SOP's allowed_capabilities are a subset of the definition's.
        Raise ValueError if they diverge (should have been caught by validate_sop).
        """
        definition_caps = set(definition.allowed_capabilities)
        sop_caps = set(sop.allowed_capabilities)
        extra = sop_caps - definition_caps
        if extra:
            raise ValueError(
                f"SOP {sop.id!r} declares capabilities not in AgentDefinition {definition.agent_id!r}: "
                f"{sorted(extra)}"
            )
        # Reject WRITE capabilities (belt-and-suspenders)
        for cap_id in sop_caps:
            skill = SKILL_REGISTRY.get(cap_id)
            if skill and skill.capability_class in (CapabilityClass.WRITE, CapabilityClass.EMERGENCY_WRITE):
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
    ) -> AgentTaskResult:
        return AgentTaskResult(
            task_id=state.task_id,
            agent_id=state.agent_id,
            sop_id=state.sop_id or "",
            sop_version=state.sop_version or "",
            final_status=status,
            stop_reason=reason if status == AgentTaskStatus.COMPLETED else None,
            escalation_reason=reason if status == AgentTaskStatus.ESCALATED else None,
            observations=observations or [],
            candidate_actions=candidate_actions or [],
            iterations=state.iteration,
            completed_at=datetime.now(timezone.utc),
        )


async def handle_delegation(
    request: AgentDelegationRequest,
    *,
    labor_agent: Any | None = None,
    wave_agent: Any | None = None,
) -> AgentDelegationResult:
    """
    Top-level delegation handler for Phase 18H.

    Routes a delegation request to the appropriate specialist agent and
    returns an AgentDelegationResult.

    This is the deterministic implementation of the delegation contract.
    A future Deep Agents runtime will replace this with an autonomous agent loop.

    Called by OperationsCoordinationAgent.gather_specialist_evidence().

    Governance invariant: No specialist agent called here may invoke
    ActionExecutor, DecisionEngine, or write MCP tools.
    """
    target = request.target_agent
    bounded = request.bounded_context or {}
    trace_id = request.trace_id or ""
    task_id = f"{request.delegation_id}-child"

    result_assessment: dict[str, Any] = {}
    result_candidates: list[dict[str, Any]] = []
    status = "completed"
    escalation_reason: str | None = None

    try:
        if target == "labor" and labor_agent is not None:
            assessment = await labor_agent.assess_labor_constraint(
                task_id=task_id,
                trace_id=trace_id,
                bounded_context=bounded,
            )
            result_assessment = assessment.model_dump()
            result_candidates = [c.model_dump() for c in assessment.candidate_actions]

        elif target == "wave" and wave_agent is not None:
            assessment = await wave_agent.assess_wave_risk(
                task_id=task_id,
                trace_id=trace_id,
                bounded_context=bounded,
            )
            result_assessment = assessment.model_dump()
            result_candidates = [c.model_dump() for c in assessment.candidate_actions]

        else:
            logger.warning(
                "handle_delegation: no specialist found for target=%s delegation=%s",
                target, request.delegation_id,
            )
            status = "escalated"
            escalation_reason = f"No specialist agent registered for target={target!r}."

    except Exception as exc:
        logger.exception(
            "handle_delegation: specialist failed for target=%s delegation=%s",
            target, request.delegation_id,
        )
        status = "failed"
        escalation_reason = f"Specialist agent raised exception: {exc}"

    return AgentDelegationResult(
        delegation_id=request.delegation_id,
        child_task_id=task_id,
        requesting_agent=request.requesting_agent,
        responding_agent=target,
        status=status,
        assessment=result_assessment,
        evidence=result_assessment.get("facts_observed", []),
        candidate_actions=result_candidates,
        escalation_reason=escalation_reason,
        trace_id=trace_id,
        completed_at=datetime.now(timezone.utc),
    )
