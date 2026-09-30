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
from ..contracts.capability_policy import (
    CapabilityDeniedError,
    RuntimeCapabilityPolicy,
    authorize_step,
    build_capability_policy,
)
from ..contracts.delegation import AgentDelegationRequest, AgentDelegationResult
from ..contracts.procedure_state import ProcedureExecutionState, ProcedureStatus
from ..contracts.registry import CapabilityClass, SKILL_REGISTRY
from ..contracts.runtime import (
    AgentExecutionContext,
    AgentRuntime,
    AgentTaskResult,
    check_capability_alignment,
)
from ..contracts.sop import SOPDefinition, SOPStep
from ..contracts.sop_v2 import EscalationReasonCode
from ..contracts.step_result import EvidenceRef, StepResult, StepStatus
from ..contracts.task import AgentTaskState, AgentTaskStatus, is_valid_transition
from ..sop_engine import SOPEngine, ValidatorRegistry

logger = logging.getLogger(__name__)

# Step action types that must never appear in an SOP. validate_sop() rejects
# write capabilities, but the runtime keeps its own belt-and-suspenders check.
_FORBIDDEN_WRITE_ACTIONS = ("write", "execute", "mutate")

# Terminal actions whose job is to surface the specialist's assessment.
_RETURN_ACTIONS = (
    "return_labor_assessment",
    "return_wave_assessment",
    "return_assessment",
)


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

    RUNTIME_NAME = "deterministic"

    def __init__(
        self,
        validator_registry: ValidatorRegistry | None = None,
        *,
        store: Any | None = None,
    ) -> None:
        self._validator_registry = validator_registry
        self._store = store
        # Set per run_task(). The step executor reads it to authorize each step,
        # so it is never supplied by a caller and never widened mid-procedure.
        self._policy: RuntimeCapabilityPolicy | None = None

    # ── SOPStepExecutor implementation ────────────────────────────────────────

    async def execute_step(
        self,
        *,
        definition: AgentDefinition,
        step: SOPStep,
        procedure_state: ProcedureExecutionState,
        context: AgentExecutionContext,
        attempt: int,
    ) -> StepResult:
        """
        Implement SOPStepExecutor for the deterministic runtime.

        Fulfils exactly one step and reports what it produced. It does NOT
        decide whether the step is complete and does NOT choose the next step —
        the SOP Engine owns both. The ``status`` returned here is a claim that
        the engine's validator then confirms or rejects.
        """
        started_at = datetime.now(timezone.utc)
        action = step.action

        # Belt-and-suspenders write guard. validate_sop() should already have
        # rejected this, so reaching it means a hand-built SOPDefinition.
        if action in _FORBIDDEN_WRITE_ACTIONS:
            return StepResult(
                step_id=step.id,
                status=StepStatus.FAILED,
                output={},
                runtime=self.RUNTIME_NAME,
                attempt=attempt,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                error=(
                    f"Deterministic runtime rejects action {action!r} — "
                    "write actions not permitted"
                ),
                escalation_reason=EscalationReasonCode.POLICY_CONFLICT,
                escalation_message=(
                    f"Step {step.id!r} has forbidden write action {action!r}."
                ),
            )

        # Deny-by-default capability gate, immediately before the step does
        # anything. This runs per step, not once at load time: a load-time check
        # says the SOP was well-formed when it was read, which is a different
        # claim from "this invocation is permitted right now".
        if self._policy is not None:
            try:
                await authorize_step(self._policy, step)
            except CapabilityDeniedError as denied:
                logger.warning(
                    "MAIWDeterministicRuntime: step %s denied by policy %s — %s",
                    step.id, self._policy.policy_id, denied.reason,
                )
                return StepResult(
                    step_id=step.id,
                    status=StepStatus.ESCALATED,
                    output={},
                    runtime=self.RUNTIME_NAME,
                    attempt=attempt,
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc),
                    error=str(denied),
                    escalation_reason=EscalationReasonCode.CAPABILITY_DENIED,
                    escalation_message=str(denied),
                )

        logger.debug(
            "MAIWDeterministicRuntime.execute_step: sop=%s step=%s action=%s attempt=%d",
            procedure_state.sop_id, step.id, action, attempt,
        )

        bounded = context.bounded_context or {}
        output: dict[str, Any] = {}

        # The deterministic runtime's execution model: specialist agents
        # pre-load their results into bounded_context before run_task().
        # A step's declared completion criteria are satisfied from that context.
        if step.completion is not None and step.completion.schema_fields:
            for field_name in step.completion.schema_fields:
                if field_name in bounded:
                    output[field_name] = bounded[field_name]

        if step.completion is not None and step.completion.required_capability_result:
            cap_id = step.completion.required_capability_result
            for key in (cap_id, f"skill_result_{cap_id}"):
                if key in bounded:
                    output[cap_id] = bounded[key]
                    break

        # Terminal "return the assessment" steps surface the specialist result.
        if action in _RETURN_ACTIONS:
            agent_result = bounded.get("_agent_result")
            if agent_result is not None:
                if hasattr(agent_result, "model_dump"):
                    result_dict = agent_result.model_dump()
                else:
                    result_dict = dict(agent_result)
                output["result"] = result_dict
                raw_candidates = result_dict.get("candidate_actions", [])
                output["candidate_actions"] = (
                    raw_candidates if isinstance(raw_candidates, list) else []
                )

        evidence = [
            EvidenceRef(
                type="step_execution",
                source=self.RUNTIME_NAME,
                reference_id=context.trace_id or None,
                timestamp=datetime.now(timezone.utc),
                summary=f"deterministic execution of step {step.id!r} (action={action})",
                metadata={
                    "step_id": step.id,
                    "action": action,
                    "sop_id": procedure_state.sop_id,
                    "agent_id": definition.agent_id,
                    "attempt": attempt,
                },
            )
        ]

        return StepResult(
            step_id=step.id,
            status=StepStatus.COMPLETED,
            output=output,
            evidence=evidence,
            runtime=self.RUNTIME_NAME,
            attempt=attempt,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            metadata={
                "action": action,
                "sop_id": procedure_state.sop_id,
                "agent_id": definition.agent_id,
                "trace_id": context.trace_id,
            },
        )

    # ── AgentRuntime implementation ───────────────────────────────────────────

    async def run_task(
        self,
        definition: AgentDefinition,
        sop: SOPDefinition,
        state: AgentTaskState,
        context: AgentExecutionContext,
    ) -> AgentTaskResult:
        """
        Execute an agent task following the given SOP.

        Procedure control is delegated to the SOP Engine, with this runtime
        acting as the SOPStepExecutor. See AgentRuntime Protocol docstring for
        invariants.
        """
        logger.info(
            "MAIWDeterministicRuntime.run_task: agent=%s sop=%s task=%s trace=%s",
            definition.agent_id,
            sop.id,
            state.task_id,
            context.trace_id,
        )

        # Validate capability alignment (delegated to shared contracts.runtime guard)
        check_capability_alignment(definition, sop)

        # Issue the runtime's capability policy for this task. Built from the
        # AgentDefinition, the SOP and the capability registry — never from
        # model output, a prompt, or the environment. Immutable once issued.
        self._policy = build_capability_policy(
            definition=definition,
            sop=sop,
            agent_task_id=state.task_id,
            runtime=self.RUNTIME_NAME,
        )

        if not sop.steps:
            return self._terminal(state, AgentTaskStatus.FAILED, "SOP has no steps.")

        max_iterations = definition.termination_policy.max_iterations
        remaining_budget = max(max_iterations - state.iteration, 0)
        if remaining_budget == 0:
            reason = f"Max iterations ({max_iterations}) reached."
            logger.warning(
                "MAIWDeterministicRuntime: %s — escalating. task=%s", reason, state.task_id
            )
            status = (
                AgentTaskStatus.ESCALATED
                if definition.termination_policy.escalate_on_max_iterations
                else AgentTaskStatus.FAILED
            )
            return self._terminal(state, status, reason)

        engine = SOPEngine(
            executor=self,
            validator_registry=self._validator_registry,
            trace_id=context.trace_id,
            max_transitions=remaining_budget,
            store=self._store,
        )

        proc_state = await engine.run_procedure(
            definition=definition,
            sop=sop,
            agent_task_id=state.task_id,
            context=context,
            warehouse_state_snapshot=(context.bounded_context or {}).get(
                "_warehouse_state_snapshot"
            ),
        )

        return self._to_task_result(state, definition, sop, context, proc_state)

    # ── ProcedureExecutionState → AgentTaskResult bridge ──────────────────────

    def _to_task_result(
        self,
        state: AgentTaskState,
        definition: AgentDefinition,
        sop: SOPDefinition,
        context: AgentExecutionContext,
        proc_state: ProcedureExecutionState,
    ) -> AgentTaskResult:
        """Project the SOP Engine's procedure state back onto the task contract."""
        observations: list[dict[str, Any]] = []
        candidate_actions: list[dict[str, Any]] = []
        assessment: dict[str, Any] = {}

        for step_id in proc_state.branch_history:
            result = proc_state.step_results.get(step_id)
            meta = result.metadata if result else {}
            observations.append({
                "step_id": step_id,
                "action": meta.get("action"),
                "sop_id": sop.id,
                "agent_id": definition.agent_id,
                "trace_id": context.trace_id,
                "status": result.status.value if result else "skipped",
                "attempt": result.attempt if result else 0,
                "validator": (
                    result.validation_result.validator_type.value
                    if result and result.validation_result
                    else None
                ),
                "timestamp": (
                    result.completed_at or result.started_at
                ).isoformat() if result else datetime.now(timezone.utc).isoformat(),
            })
            if result is None:
                continue
            if "result" in result.output:
                assessment["result"] = result.output["result"]
            raw_candidates = result.output.get("candidate_actions")
            if isinstance(raw_candidates, list):
                candidate_actions.extend(raw_candidates)

        iterations = state.iteration + len(proc_state.branch_history)

        # Surface the first typed escalation reason we recorded, if any.
        escalation_message: str | None = None
        for result in proc_state.step_results.values():
            if result.escalation_reason is not None:
                escalation_message = (
                    result.escalation_message
                    or f"{result.escalation_reason.value} at step {result.step_id}"
                )
                break

        if proc_state.status == ProcedureStatus.COMPLETED:
            final_status = AgentTaskStatus.COMPLETED
            stop_reason: str | None = "OBJECTIVE_MET"
        elif proc_state.status == ProcedureStatus.WAITING_FOR_GOVERNANCE:
            final_status = AgentTaskStatus.WAITING_FOR_GOVERNANCE
            stop_reason = "WAITING_FOR_GOVERNANCE"
        elif proc_state.status == ProcedureStatus.ESCALATED:
            final_status = AgentTaskStatus.ESCALATED
            stop_reason = None
        else:
            final_status = AgentTaskStatus.FAILED
            stop_reason = None

        return AgentTaskResult(
            task_id=state.task_id,
            agent_id=definition.agent_id,
            sop_id=sop.id,
            sop_version=sop.version,
            final_status=final_status,
            assessment=assessment or None,
            candidate_actions=candidate_actions,
            observations=observations,
            iterations=iterations,
            stop_reason=stop_reason,
            escalation_reason=(
                escalation_message
                if final_status in (AgentTaskStatus.ESCALATED, AgentTaskStatus.FAILED)
                else None
            ),
            completed_at=datetime.now(timezone.utc),
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
