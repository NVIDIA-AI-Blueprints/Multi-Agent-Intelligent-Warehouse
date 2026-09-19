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

Phase 19A.11b: _SimulatedDeepAgentsRuntime (the original POC integration-seam
prototype with ZERO external framework imports) was removed in this commit.
It represented ~600 LOC of generic orchestration that is now provided by the
real deepagents==0.7.15 SDK. See docs/audits/PHASE_19A_11_OWNERSHIP_MATRIX.md.
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
from ..contracts.registry import CapabilityClass, SKILL_REGISTRY
from ..contracts.runtime import AgentExecutionContext, AgentTaskResult, check_capability_alignment
from ..contracts.sop import SOPDefinition
from ..contracts.task import AgentTaskState, AgentTaskStatus

logger = logging.getLogger(__name__)

# Runtime version tags
_RUNTIME_VERSION_REAL = "0.7.15"
_PLANNING_STEPS = 7


# ── Public factory ─────────────────────────────────────────────────────────────

def get_runtime(config: str | None = None, sop: SOPDefinition | None = None) -> "Any":
    """
    Factory function for MAIW agent runtimes.

    Config values:
        "deterministic" (default) — MAIWDeterministicRuntime
        "deep_agents" — DeepAgentsRuntime (real deepagents==0.7.15)

    If config is None and sop is provided, sop.runtime_profile is used:
        "strict"   → MAIWDeterministicRuntime
        "adaptive" → DeepAgentsRuntime

    Environment variable: MAIW_AGENT_RUNTIME (overrides sop.runtime_profile)
    """
    from .deterministic import MAIWDeterministicRuntime

    selected = config or os.environ.get("MAIW_AGENT_RUNTIME")
    if selected is None and sop is not None:
        selected = "deep_agents" if sop.runtime_profile == "adaptive" else "deterministic"
    selected = selected or "deterministic"

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
        """Verify SOP capabilities are subset of definition capabilities.
        Delegates to the consolidated contracts.runtime.check_capability_alignment().
        """
        check_capability_alignment(definition, sop)

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
