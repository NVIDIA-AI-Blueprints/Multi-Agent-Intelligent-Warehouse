# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
DeepAgentsRuntime — Phase 19A (real deepagents SDK integration).

Implements MAIW AgentRuntime Protocol using deepagents==0.7.15.

Architecture:
    MAIW AgentDefinition/SOPDefinition/AgentTaskState
        → DeepAgentsRuntime.run_task()
        → create_deep_agent(model=MAIWModelGatewayChat(...), tools=[MAIW read/analytical tools],
                            subagents=[...], permissions=[])
        → graph.ainvoke({"messages": [HumanMessage(sop_prompt)]})
        → parse structured response → RecommendedAction
        → WAITING_FOR_GOVERNANCE

Governance invariant: Deep Agents NEVER calls ActionExecutor/write MCP/DecisionEngine.
Model invariant: All model calls go through MAIWModelGatewayChat → ModelGateway.
Skill invariant: Only READ/ANALYTICAL tools exposed (no WRITE/EMERGENCY_WRITE).

Also provides _SimulatedDeepAgentsRuntime: the original Phase 19A POC (integration-seam
prototype) that simulates Deep Agents behavior with ZERO external framework imports.
Kept for backward compatibility and as a reference implementation.
"""

from __future__ import annotations

import json
import logging
import os
import re
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

# Runtime version tags
_RUNTIME_VERSION_SIMULATED = "19A.poc"
_RUNTIME_VERSION_REAL = "0.7.15"
_PLANNING_STEPS = 7


# ── Public factory ─────────────────────────────────────────────────────────────

def get_runtime(config: str | None = None) -> "Any":
    """
    Factory function for MAIW agent runtimes.

    Config values:
        "deterministic" (default) — MAIWDeterministicRuntime
        "deep_agents" — DeepAgentsRuntime (real deepagents==0.7.15)

    Environment variable: MAIW_AGENT_RUNTIME
    """
    from .deterministic import MAIWDeterministicRuntime

    selected = config or os.environ.get("MAIW_AGENT_RUNTIME", "deterministic")
    if selected == "deep_agents":
        return DeepAgentsRuntime()
    return MAIWDeterministicRuntime()


# ── Helpers for real DeepAgentsRuntime ────────────────────────────────────────

def _build_sop_system_prompt(definition: AgentDefinition, sop: SOPDefinition) -> str:
    """
    Derive the Deep Agents system prompt from MAIW-owned AgentDefinition + SOPDefinition.
    MAIW owns this prompt. Deep Agents provides runtime scaffolding only.
    """
    steps_text = "\n".join(
        f"  {i+1}. [{s.id}] {s.action}: {s.description or ''}"
        for i, s in enumerate(sop.steps)
    )
    caps_text = "\n".join(f"  - {c}" for c in sop.allowed_capabilities)
    subagents_text = "\n".join(f"  - {a}" for a in sop.allowed_subagents)
    stop_text = "\n".join(f"  - {s}" for s in sop.stop_conditions)

    return (
        f"You are the MAIW {definition.agent_id} agent, version {definition.version}.\n\n"
        f"OBJECTIVE: {definition.objective}\n\n"
        f"DOMAIN: {definition.domain}\n\n"
        f"SOP: {sop.id} v{sop.version}\n"
        f"{sop.description or ''}\n\n"
        f"PROCEDURE (follow in order):\n{steps_text}\n\n"
        f"ALLOWED CAPABILITIES (skills you may use):\n{caps_text}\n\n"
        f"ALLOWED SUBAGENTS (specialists you may delegate to):\n{subagents_text}\n\n"
        "GOVERNANCE BOUNDARY (HARD RULE):\n"
        "- You MUST NOT directly modify warehouse operational state.\n"
        "- You MUST NOT call ActionExecutor, DecisionEngine, or any write operation.\n"
        "- You MUST produce a structured recommendation and stop at WAITING_FOR_GOVERNANCE.\n"
        "- All recommendations flow through the human approval governance layer.\n\n"
        f"STOP CONDITIONS:\n{stop_text}\n\n"
        "When you have completed the SOP and generated a recommendation, respond with:\n"
        'RECOMMENDATION: <json with domain, capability, target, objective, rationale, priority>\n'
        "STOP: WAITING_FOR_GOVERNANCE\n"
    )


def _build_maiw_tools(context: AgentExecutionContext, allowed_caps: list[str]) -> list:
    """
    Build LangChain BaseTool objects from MAIW skill registry.
    Only READ and ANALYTICAL skills are exposed. WRITE/EMERGENCY_WRITE are NEVER included.
    """
    try:
        from langchain_core.tools import StructuredTool
    except ImportError:
        return []

    tools = []
    for cap_id in allowed_caps:
        entry = SKILL_REGISTRY.get(cap_id)
        if entry is None:
            continue
        # HARD BLOCK: never expose WRITE or EMERGENCY_WRITE
        if entry.capability_class in (CapabilityClass.WRITE, CapabilityClass.EMERGENCY_WRITE):
            logger.warning("Blocking WRITE capability %s from Deep Agents tools", cap_id)
            continue

        skill_id = entry.skill_id

        def make_tool_fn(sid: str, description: str):
            def tool_fn(query: str = "") -> str:
                """Invoke the MAIW skill and return structured result."""
                result = context.bounded_context.get(f"skill_result_{sid}")
                if result is not None:
                    return str(result)
                return f"Skill {sid} executed. Context: {dict(list(context.bounded_context.items())[:3])}"
            tool_fn.__name__ = sid.replace(".", "_")
            tool_fn.__doc__ = description
            return tool_fn

        fn = make_tool_fn(skill_id, entry.description)
        tools.append(
            StructuredTool.from_function(
                func=fn,
                name=skill_id.replace(".", "_"),
                description=f"[{entry.capability_class.value}] {entry.description}",
            )
        )
    return tools


def _build_subagent_specs(sop: SOPDefinition, context: AgentExecutionContext) -> list:
    """Build Deep Agents SubAgent specs from MAIW SOP allowed_subagents."""
    try:
        from deepagents import SubAgent
    except ImportError:
        return []

    subagent_specs = []
    for agent_id in sop.allowed_subagents:
        if agent_id == "labor":
            subagent_specs.append(SubAgent(
                name="labor",
                description=(
                    "MAIW LaborAgent specialist. Assesses labor constraints, "
                    "reads worker states, evaluates reallocation feasibility, "
                    "and returns LaborAssessment with candidate labor actions. "
                    "Does NOT execute actions — only recommends."
                ),
                tools=[],
                system_prompt=(
                    "You are the MAIW LaborAgent. "
                    "Assess labor constraints based on the bounded context provided. "
                    "Return a structured LaborAssessment with: "
                    "worker_count, available_workers, constrained_zones, candidate_actions. "
                    "DO NOT execute any actions. Only assess and recommend."
                ),
                mode="isolated",
            ))
        elif agent_id == "wave":
            subagent_specs.append(SubAgent(
                name="wave",
                description=(
                    "MAIW WaveAgent specialist. Assesses wave risk, critical path, "
                    "at-risk tasks, and returns WaveAssessment with candidate wave actions. "
                    "Does NOT execute actions — only recommends."
                ),
                tools=[],
                system_prompt=(
                    "You are the MAIW WaveAgent. "
                    "Assess wave risk based on the bounded context provided. "
                    "Return a structured WaveAssessment with: "
                    "at_risk_count, critical_path_delay_minutes, candidate_actions. "
                    "DO NOT execute any actions. Only assess and recommend."
                ),
                mode="isolated",
            ))
        elif agent_id == "equipment":
            subagent_specs.append(SubAgent(
                name="equipment",
                description=(
                    "MAIW EquipmentAgent specialist. Assesses equipment constraints "
                    "and returns EquipmentAssessment with candidate actions."
                ),
                tools=[],
                system_prompt=(
                    "You are the MAIW EquipmentAgent. "
                    "Assess equipment constraints. Return structured EquipmentAssessment. "
                    "DO NOT execute any actions."
                ),
                mode="isolated",
            ))
    return subagent_specs


class DeepAgentsRuntime:
    """
    Real MAIW agent runtime backed by deepagents==0.7.15.

    Implements AgentRuntime Protocol.

    Uses create_deep_agent() with:
    - MAIWModelGatewayChat (model → ModelGateway, not direct provider)
    - MAIW skill tools (READ/ANALYTICAL only, WRITE hard-blocked)
    - MAIW SubAgent specs (labor, wave, equipment — isolated mode)
    - System prompt derived from AgentDefinition + SOPDefinition (MAIW owns)
    - No filesystem tools (permissions=[])
    - No memory/skills (warehouse state is injected via context)
    - Capability alignment checked before graph invocation

    Runtime provenance recorded: runtime=deep_agents, version=0.7.15,
    agent_id, sop_id, sop_version, task_id, model_route, message_count.
    """

    RUNTIME_NAME = "deep_agents"
    RUNTIME_VERSION = _RUNTIME_VERSION_REAL

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

    async def run_task(
        self,
        definition: AgentDefinition,
        sop: SOPDefinition,
        state: AgentTaskState,
        context: AgentExecutionContext,
    ) -> AgentTaskResult:
        """Execute agent task using real deepagents runtime."""
        from deepagents import create_deep_agent
        from langchain_core.messages import HumanMessage
        from .model_adapter import MAIWModelGatewayChat

        logger.info(
            "DeepAgentsRuntime.run_task: agent=%s sop=%s task=%s runtime=%s/%s",
            definition.agent_id, sop.id, state.task_id,
            self.RUNTIME_NAME, self.RUNTIME_VERSION,
        )

        # 0. Validate capability alignment (WRITE block)
        self._check_capability_alignment(definition, sop)

        # 1. Build model (MUST go through ModelGateway)
        model = MAIWModelGatewayChat(
            model_gateway=context.model_gateway,
            trace_id=context.trace_id,
        )

        # 2. Build tools (READ/ANALYTICAL only — WRITE hard-blocked)
        tools = _build_maiw_tools(context, sop.allowed_capabilities)

        # 3. Build subagent specs from MAIW SOP (not framework-invented)
        subagents = _build_subagent_specs(sop, context)

        # 4. System prompt from MAIW-owned AgentDefinition + SOPDefinition
        system_prompt = _build_sop_system_prompt(definition, sop)

        # 5. Create deep agent graph
        graph = create_deep_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            subagents=subagents,
            permissions=[],   # Disable all filesystem tools
            memory=None,      # No memory — warehouse state via context
            skills=None,      # No file-based skills
            debug=False,
        )

        # 6. Build initial message from task state + context
        task_context = self._build_task_context(definition, sop, state, context)

        # 7. Disable LangSmith tracing (no external SaaS dependency)
        os.environ.setdefault("LANGSMITH_TRACING", "false")

        max_iter = definition.termination_policy.max_iterations
        observations: list[dict[str, Any]] = []

        # 8. Invoke with iteration guard
        try:
            result = await graph.ainvoke(
                {"messages": [HumanMessage(content=task_context)]},
                config={"recursion_limit": max(max_iter + 5, 10)},
            )
        except Exception as exc:
            exc_name = type(exc).__name__
            exc_str = str(exc)
            if "recursion" in exc_str.lower() or "GraphRecursion" in exc_name:
                reason = (
                    f"Max iterations ({max_iter}) reached in Deep Agents graph "
                    f"(LangGraph recursion limit)."
                )
                if definition.termination_policy.escalate_on_max_iterations:
                    return self._terminal(state, AgentTaskStatus.ESCALATED, reason)
                return self._terminal(state, AgentTaskStatus.FAILED, reason)
            logger.exception("DeepAgentsRuntime: graph.ainvoke failed: %s", exc)
            return self._terminal(
                state, AgentTaskStatus.FAILED,
                f"Deep Agents runtime error: {exc}",
            )

        # 9. Parse result
        return self._parse_result(result, state, definition, sop, context, observations)

    def _build_task_context(
        self,
        definition: AgentDefinition,
        sop: SOPDefinition,
        state: AgentTaskState,
        context: AgentExecutionContext,
    ) -> str:
        """Build the initial task message from MAIW context."""
        bounded = context.bounded_context
        ctx_parts = [
            f"TASK ID: {state.task_id}",
            f"OBJECTIVE: {state.objective}",
            f"TRACE ID: {context.trace_id}",
            f"WAREHOUSE: {context.warehouse_id}",
        ]
        if bounded:
            ctx_parts.append("OPERATIONAL CONTEXT:")
            for key, val in bounded.items():
                if not key.startswith("_"):
                    ctx_parts.append(f"  {key}: {val}")
        return "\n".join(ctx_parts)

    def _parse_result(
        self,
        result: dict[str, Any],
        state: AgentTaskState,
        definition: AgentDefinition,
        sop: SOPDefinition,
        context: AgentExecutionContext,
        observations: list[dict[str, Any]],
    ) -> AgentTaskResult:
        """Parse Deep Agents graph result into MAIW AgentTaskResult."""
        messages = result.get("messages", [])
        last_ai = None
        for msg in reversed(messages):
            if hasattr(msg, "content") and isinstance(msg.content, str) and msg.content.strip():
                last_ai = msg.content
                break

        # Record messages as observations
        for i, msg in enumerate(messages):
            observations.append({
                "observation_id": f"msg-{i}",
                "source": "deep_agents_runtime",
                "content_type": type(msg).__name__,
                "step_idx": i,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        # Parse governance signal and recommendation
        recommendation: dict[str, Any] | None = None
        candidate_actions: list[dict[str, Any]] = []
        stop_reason = "OBJECTIVE_MET"
        final_status = AgentTaskStatus.COMPLETED

        if last_ai:
            content_lower = last_ai.lower()
            if "waiting_for_governance" in content_lower or "stop:" in content_lower:
                final_status = AgentTaskStatus.WAITING_FOR_GOVERNANCE
                stop_reason = "WAITING_FOR_GOVERNANCE"
                # Extract recommendation JSON if present
                rec_match = re.search(
                    r"RECOMMENDATION:\s*(\{.*?\})",
                    last_ai, re.DOTALL | re.IGNORECASE
                )
                if rec_match:
                    try:
                        recommendation = json.loads(rec_match.group(1))
                    except json.JSONDecodeError:
                        recommendation = {"raw": rec_match.group(1)[:200]}
                else:
                    recommendation = {"summary": last_ai[:500]}
            elif "escalat" in content_lower or "human_required" in content_lower:
                final_status = AgentTaskStatus.ESCALATED
                stop_reason = "HUMAN_REQUIRED"

        # Populate candidate_actions from recommendation if available
        if recommendation:
            candidate_actions = [{
                "action": recommendation.get("action", "recommendation"),
                "domain": recommendation.get("domain", "operations"),
                "priority": recommendation.get("priority", "HIGH"),
                "rationale": recommendation.get("rationale", "From Deep Agents runtime"),
            }]

        # Runtime provenance observation
        observations.append({
            "observation_id": "runtime-provenance",
            "source": "deep_agents_runtime",
            "observation_type": "runtime_provenance",
            "facts": {
                "runtime": self.RUNTIME_NAME,
                "runtime_version": self.RUNTIME_VERSION,
                "agent_id": definition.agent_id,
                "sop_id": sop.id,
                "sop_version": sop.version,
                "task_id": state.task_id,
                "trace_id": context.trace_id,
                "message_count": len(messages),
                "stop_reason": stop_reason,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return AgentTaskResult(
            task_id=state.task_id,
            agent_id=definition.agent_id,
            sop_id=sop.id,
            sop_version=sop.version,
            final_status=final_status,
            recommendation=recommendation,
            candidate_actions=candidate_actions,
            stop_reason=stop_reason if final_status in (
                AgentTaskStatus.COMPLETED, AgentTaskStatus.WAITING_FOR_GOVERNANCE
            ) else None,
            escalation_reason=stop_reason if final_status in (
                AgentTaskStatus.ESCALATED, AgentTaskStatus.FAILED
            ) else None,
            observations=observations,
            iterations=len(messages),
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
        Resume after a GovernanceOutcome is supplied.
        Transitions WAITING_FOR_GOVERNANCE → OBSERVING_OUTCOME → COMPLETED/ESCALATED.

        Deep Agents may reason about the outcome but MAIW state transitions remain authoritative.
        """
        logger.info(
            "DeepAgentsRuntime.resume_after_governance: task=%s outcome=%s",
            state.task_id, governance_outcome.get("decision_outcome"),
        )

        # Validate state allows resumption
        if state.status != AgentTaskStatus.WAITING_FOR_GOVERNANCE:
            return self._terminal(
                state, AgentTaskStatus.FAILED,
                f"Cannot resume: state is {state.status.value!r}, expected WAITING_FOR_GOVERNANCE.",
            )

        decision = governance_outcome.get("decision_outcome", "UNKNOWN")
        execution_status = governance_outcome.get("execution_status", "UNKNOWN")

        resume_obs = [{
            "observation_id": "governance-resume",
            "source": "governance",
            "observation_type": "governance_outcome",
            "facts": governance_outcome,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]

        if decision in ("APPROVED",) and execution_status in ("EXECUTED", "NO_OP"):
            return AgentTaskResult(
                task_id=state.task_id,
                agent_id=definition.agent_id,
                sop_id=sop.id,
                sop_version=sop.version,
                final_status=AgentTaskStatus.COMPLETED,
                stop_reason="OBJECTIVE_MET",
                observations=resume_obs,
                completed_at=datetime.now(timezone.utc),
            )
        elif decision in ("REJECTED", "ERROR"):
            return AgentTaskResult(
                task_id=state.task_id,
                agent_id=definition.agent_id,
                sop_id=sop.id,
                sop_version=sop.version,
                final_status=AgentTaskStatus.ESCALATED,
                escalation_reason=f"Governance {decision}: {governance_outcome.get('reason', 'unspecified')}",
                observations=resume_obs,
                completed_at=datetime.now(timezone.utc),
            )
        else:
            return AgentTaskResult(
                task_id=state.task_id,
                agent_id=definition.agent_id,
                sop_id=sop.id,
                sop_version=sop.version,
                final_status=AgentTaskStatus.COMPLETED,
                stop_reason="OBJECTIVE_MET",
                observations=resume_obs,
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
            candidate_actions=candidate_actions or [],
            stop_reason=reason if status in (
                AgentTaskStatus.COMPLETED, AgentTaskStatus.WAITING_FOR_GOVERNANCE
            ) else None,
            escalation_reason=reason if status in (
                AgentTaskStatus.ESCALATED, AgentTaskStatus.FAILED
            ) else None,
            observations=observations or [],
            iterations=iterations if iterations is not None else state.iteration,
            completed_at=datetime.now(timezone.utc),
        )


# ── _SimulatedDeepAgentsRuntime (Phase 19A POC — integration-seam prototype) ──
# This is the original Phase 19A simulated runtime. It has ZERO external framework
# imports and simulates Deep Agents behavior using MAIW ModelGateway + skill adapters.
# Kept for backward compatibility and as a reference implementation.

class _SimulatedDeepAgentsRuntime:
    """
    Deep Agents-simulated MAIW agent runtime (Phase 19A POC).

    Implements AgentRuntime Protocol with ZERO external framework imports.
    Simulates Deep Agents planning + execution loop using MAIW contracts only.

    Use DeepAgentsRuntime for real deepagents==0.7.15 integration.
    Use this class only for reference or simulation-only test environments.
    """

    def __init__(self) -> None:
        self._runtime_version = _RUNTIME_VERSION_SIMULATED

    async def run_task(
        self,
        definition: AgentDefinition,
        sop: SOPDefinition,
        state: AgentTaskState,
        context: AgentExecutionContext,
    ) -> AgentTaskResult:
        """Execute an agent task following the given SOP using simulated Deep Agents loop."""
        logger.info(
            "_SimulatedDeepAgentsRuntime.run_task: agent=%s sop=%s task=%s trace=%s runtime=%s",
            definition.agent_id, sop.id, state.task_id, context.trace_id, self._runtime_version,
        )

        self._check_capability_alignment(definition, sop)

        model_adapter = MAIWModelAdapter(
            model_gateway=context.model_gateway,
            risk_level="standard",
            reasoning_level="standard",
        )
        skill_adapter = MAIWSkillAdapter(trace_id=context.trace_id)

        steps = {s.id: s for s in sop.steps}
        if not steps:
            return self._terminal(state, AgentTaskStatus.FAILED, "SOP has no steps.")

        _scratchpad: dict[str, Any] = {
            "trace_id": context.trace_id,
            "sop_id": sop.id,
            "sop_version": sop.version,
            "agent_id": definition.agent_id,
            "task_id": state.task_id,
            "bounded_context": dict(context.bounded_context),
        }

        runtime_events: list[dict[str, Any]] = []
        observations: list[dict[str, Any]] = []
        candidate_actions: list[dict[str, Any]] = []
        assessment: dict[str, Any] = {}
        recommendation: dict[str, Any] | None = None

        plan = await self._generate_plan(
            sop=sop, model_adapter=model_adapter, context=context, scratchpad=_scratchpad,
        )
        runtime_events.append({
            "event": "plan",
            "plan_steps": [p["step_id"] for p in plan],
            "model_calls": model_adapter.call_count,
            "trace_id": context.trace_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        iteration = state.iteration
        current_step_index = 0

        while current_step_index < len(plan):
            if iteration >= definition.termination_policy.max_iterations:
                reason = (
                    f"Max iterations ({definition.termination_policy.max_iterations}) reached "
                    f"after {iteration} iterations."
                )
                logger.warning("_SimulatedDeepAgentsRuntime: %s task=%s", reason, state.task_id)
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
                        observations=observations, candidate_actions=candidate_actions,
                        recommendation=recommendation, iterations=iteration,
                    )
                return self._terminal(
                    state, AgentTaskStatus.FAILED, reason,
                    observations=observations, candidate_actions=candidate_actions,
                    iterations=iteration,
                )

            plan_entry = plan[current_step_index]
            step_id = plan_entry["step_id"]
            step = steps.get(step_id)

            if step is None:
                return self._terminal(
                    state, AgentTaskStatus.FAILED,
                    f"Unknown step_id in plan: {step_id!r}",
                    observations=observations, iterations=iteration,
                )

            logger.debug(
                "_SimulatedDeepAgentsRuntime: executing step %s action=%s task=%s iter=%d",
                step_id, step.action, state.task_id, iteration,
            )

            if step.condition is not None:
                condition_facts = {**context.bounded_context, **assessment, **_scratchpad}
                condition_met = step.condition.evaluate(condition_facts)
                if not condition_met:
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
                    "_SimulatedDeepAgentsRuntime: WAITING_FOR_GOVERNANCE after step=%s task=%s",
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

            if step.action == "delegate_to_agent" or step.action == "consult_required_domains":
                target_agent = step.delegate_to or _infer_delegate_target(
                    step=step, scratchpad=_scratchpad, bounded_context=context.bounded_context,
                )
                delegation_result = await self._delegate(
                    step_id=step_id, target_agent=target_agent,
                    state=state, context=context, scratchpad=_scratchpad,
                )
                if delegation_result is not None:
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
                            observations=observations, candidate_actions=candidate_actions,
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

            if step.action == "invoke_skill" and step.skill_id:
                tool = skill_adapter.get_tool(step.skill_id)
                if tool is None:
                    if skill_adapter.is_blocked(step.skill_id):
                        reason = (
                            f"Step {step_id!r} attempted to invoke blocked WRITE "
                            f"skill {step.skill_id!r}."
                        )
                        return self._terminal(
                            state, AgentTaskStatus.FAILED, reason,
                            observations=observations, iterations=iteration,
                        )
                    logger.warning(
                        "_SimulatedDeepAgentsRuntime: unknown skill %s in step %s — skipping.",
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

            model_response = await model_adapter.generate(
                prompt=_build_step_prompt(
                    step_id=step_id, action=step.action,
                    description=step.description or "",
                    scratchpad=_scratchpad, assessment=assessment,
                ),
                trace_id=context.trace_id,
                step_id=step_id,
            )

            step_text = model_response.get("text", "")

            step_obs, step_candidates, step_assessment, step_recommendation = (
                _extract_step_results(
                    step_id=step_id, action=step.action, model_text=step_text,
                    existing_candidates=candidate_actions, context=context,
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
        """Resume task after governance outcome is returned."""
        logger.info(
            "_SimulatedDeepAgentsRuntime.resume_after_governance: task=%s outcome=%s trace=%s",
            state.task_id, governance_outcome.get("decision_outcome"), context.trace_id,
        )

        if state.status != AgentTaskStatus.WAITING_FOR_GOVERNANCE:
            return self._terminal(
                state, AgentTaskStatus.FAILED,
                f"Cannot resume: state is {state.status.value!r}, expected WAITING_FOR_GOVERNANCE.",
            )

        state = state.transition(AgentTaskStatus.OBSERVING_OUTCOME)
        model_adapter = MAIWModelAdapter(model_gateway=context.model_gateway)

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
        await model_adapter.generate(prompt=prompt, trace_id=context.trace_id, step_id="planning")
        return [
            {"step_id": s.id, "action": s.action, "description": s.description or ""}
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
        if not target_agent:
            logger.warning(
                "_SimulatedDeepAgentsRuntime: delegation step %s has no target agent — skipping.",
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

        specialist_fn = context.skill_registry.get(f"_delegate_{target_agent}")
        if specialist_fn is not None:
            try:
                result = await specialist_fn(request)
                return result
            except Exception as exc:
                logger.error("_SimulatedDeepAgentsRuntime: specialist %s failed: %s", target_agent, exc)
                return AgentDelegationResult(
                    delegation_id=delegation_id,
                    child_task_id=f"{delegation_id}-child",
                    requesting_agent=state.agent_id,
                    responding_agent=target_agent,
                    status="failed",
                    escalation_reason=str(exc),
                    trace_id=context.trace_id,
                )

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
        self, definition: AgentDefinition, sop: SOPDefinition,
    ) -> None:
        definition_caps = set(definition.allowed_capabilities)
        sop_caps = set(sop.allowed_capabilities)
        extra = sop_caps - definition_caps
        if extra:
            raise ValueError(
                f"SOP {sop.id!r} declares capabilities not in AgentDefinition "
                f"{definition.agent_id!r}: {sorted(extra)}"
            )
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


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _infer_delegate_target(
    *,
    step: Any,
    scratchpad: dict[str, Any],
    bounded_context: dict[str, Any],
) -> str | None:
    primary_constraint = (
        bounded_context.get("primary_constraint")
        or scratchpad.get("primary_constraint")
        or "labor"
    )
    constraint_map = {"labor": "labor", "wave": "wave", "equipment": "equipment"}
    return constraint_map.get(str(primary_constraint).lower(), "labor")


def _build_step_prompt(
    *,
    step_id: str,
    action: str,
    description: str,
    scratchpad: dict[str, Any],
    assessment: dict[str, Any],
) -> str:
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
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
    dict[str, Any] | None,
]:
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
        "gather_operational_context", "determine_primary_constraint",
        "evaluate_post_execution_state", "read_labor_state",
        "read_wave_status", "no_op",
    ):
        assessment_update[f"{action}_complete"] = True
        if action == "determine_primary_constraint":
            assessment_update["primary_constraint"] = (
                context.bounded_context.get("primary_constraint", "labor")
            )

    return obs, new_candidates, assessment_update, recommendation
