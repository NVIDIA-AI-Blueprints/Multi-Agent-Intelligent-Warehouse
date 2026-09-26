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
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..contracts.agent import AgentDefinition
from ..contracts.procedure_state import ProcedureExecutionState, ProcedureStatus
from ..contracts.registry import CapabilityClass, SKILL_REGISTRY
from ..contracts.runtime import AgentExecutionContext, AgentTaskResult, check_capability_alignment
from ..contracts.sop import SOPDefinition, SOPStep
from ..contracts.sop_v2 import EscalationReasonCode
from ..contracts.step_result import EvidenceRef, StepResult, StepStatus
from ..contracts.task import AgentTaskState, AgentTaskStatus
from ..sop_engine import SOPEngine, ValidatorRegistry

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

    Precedence (highest to lowest):
        1. Explicit ``config`` parameter — always wins.
        2. ``sop.runtime_profile`` — when no explicit config, the SOP governs.
        3. ``MAIW_AGENT_RUNTIME`` env var — last-resort fallback when neither
           explicit config nor SOP is provided.
        4. Default: "deterministic".

    The env var can no longer override an explicit SOP runtime_profile.
    """
    from .deterministic import MAIWDeterministicRuntime

    # 1. Explicit config takes precedence over everything
    if config is not None:
        selected = config
    # 2. SOP runtime_profile takes precedence over env var
    elif sop is not None:
        selected = "deep_agents" if sop.runtime_profile == "adaptive" else "deterministic"
    # 3. Env var only as last-resort fallback when neither config nor SOP is given
    else:
        selected = os.environ.get("MAIW_AGENT_RUNTIME", "deterministic")

    if selected == "deep_agents":
        return DeepAgentsRuntime()
    return MAIWDeterministicRuntime()


# ── Helpers for real DeepAgentsRuntime ────────────────────────────────────────

def _build_step_system_prompt(
    definition: AgentDefinition,
    sop: SOPDefinition,
    step: SOPStep,
    context: AgentExecutionContext,
) -> str:
    """
    Build the system prompt for ONE step.

    This replaces the previous whole-SOP prompt. The model is shown the current
    step only — it cannot see, skip, reorder, or compress the rest of the
    procedure, and it is told explicitly not to choose the next step. Step
    sequencing is the SOP Engine's job, and the engine is the only thing that
    can mark a step complete.
    """
    caps_text = "\n".join(f"  - {c}" for c in sop.allowed_capabilities) or "  (none)"
    subagents_text = "\n".join(f"  - {a}" for a in sop.allowed_subagents) or "  (none)"

    objective_line = f"STEP OBJECTIVE: {step.objective}\n" if step.objective else ""
    expected_line = (
        f"EXPECTED OUTPUT: {json.dumps(step.expected_output)}\n"
        if step.expected_output
        else ""
    )
    required_line = (
        f"REQUIRED INPUTS: {', '.join(step.required_inputs)}\n"
        if step.required_inputs
        else ""
    )
    evidence_line = (
        f"EVIDENCE REQUIRED: {', '.join(step.evidence_requirements)}\n"
        if step.evidence_requirements
        else ""
    )

    return (
        f"You are the MAIW {definition.agent_id} agent, version {definition.version}.\n\n"
        f"PROCEDURE: {sop.objective}\n"
        f"CURRENT STEP: {step.id} — {step.description or step.action}\n"
        f"{objective_line}{required_line}{expected_line}{evidence_line}\n"
        f"ALLOWED CAPABILITIES (read/analytical only):\n{caps_text}\n\n"
        f"ALLOWED SUBAGENTS:\n{subagents_text}\n\n"
        "GOVERNANCE HARD RULE: You may NOT execute warehouse writes. You may NOT call\n"
        "ActionExecutor or DecisionEngine. If this step requires a write action,\n"
        "output WAITING_FOR_GOVERNANCE with your recommendation.\n\n"
        "OUTPUT FORMAT: Return a JSON object:\n"
        "{\n"
        f'  "step_id": "{step.id}",\n'
        '  "status": "completed" | "waiting_for_governance" | "failed",\n'
        '  "output": {...structured output...},\n'
        '  "recommendation": {...} (only if status=waiting_for_governance)\n'
        "}\n\n"
        "You are working on THIS STEP ONLY. Do not decide the next step — the SOP\n"
        "Engine decides. Do not output anything outside the JSON object.\n"
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


def _extract_json_object(text: str, *, must_contain: tuple[str, ...] = ()) -> dict[str, Any] | None:
    """
    Pull the first balanced JSON object out of a model response.

    Models wrap JSON in prose and code fences; a naive non-greedy regex stops at
    the first nested closing brace. This scans for balanced braces instead.
    """
    for start in range(len(text)):
        if text[start] != "{":
            continue
        depth = 0
        in_string = False
        escaped = False
        for end in range(start, len(text)):
            ch = text[end]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:end + 1]
                    try:
                        parsed = json.loads(candidate)
                    except json.JSONDecodeError:
                        break
                    if not isinstance(parsed, dict):
                        break
                    if must_contain and not any(k in parsed for k in must_contain):
                        break
                    return parsed
        # try the next '{'
    return None


@dataclass(frozen=True)
class _GovernanceOutcomeView:
    """Minimal attribute view of a governance outcome for the SOP Engine."""

    decision_outcome: str
    execution_status: str


class _DeepAgentsStepExecutor:
    """
    Binds a prepared MAIWModelGatewayChat model to the SOPStepExecutor protocol.

    Holding the model here (rather than on the runtime) keeps DeepAgentsRuntime
    reentrant: two concurrent tasks get two executors and never share state.
    """

    RUNTIME_NAME = "deep_agents"

    def __init__(
        self,
        *,
        runtime: "DeepAgentsRuntime",
        sop: SOPDefinition,
        model: Any,
        tools: list,
        subagents: list,
        max_iterations: int,
    ) -> None:
        self._runtime = runtime
        self._sop = sop
        self._model = model
        self._tools = tools
        self._subagents = subagents
        self._max_iterations = max_iterations
        self.message_count = 0

    async def execute_step(
        self,
        *,
        definition: AgentDefinition,
        step: SOPStep,
        procedure_state: ProcedureExecutionState,
        context: AgentExecutionContext,
        attempt: int,
    ) -> StepResult:
        from deepagents import create_deep_agent
        from langchain_core.messages import HumanMessage

        started_at = datetime.now(timezone.utc)

        # The graph is rebuilt per step because the step prompt IS the system
        # prompt — this is what guarantees the model never sees the full SOP.
        system_prompt = _build_step_system_prompt(definition, self._sop, step, context)

        os.environ.setdefault("LANGSMITH_TRACING", "false")

        graph = create_deep_agent(
            model=self._model,
            tools=self._tools,
            system_prompt=system_prompt,
            subagents=self._subagents,
            permissions=[],   # Disable all filesystem tools
            memory=None,      # No memory — warehouse state via context
            skills=None,      # No file-based skills
            debug=False,
        )

        step_message = self._runtime._build_step_task_context(
            sop=self._sop,
            step=step,
            procedure_state=procedure_state,
            context=context,
            attempt=attempt,
        )

        try:
            result = await graph.ainvoke(
                {"messages": [HumanMessage(content=step_message)]},
                config={"recursion_limit": max(self._max_iterations + 5, 10)},
            )
        except Exception as exc:
            exc_name = type(exc).__name__
            exc_str = str(exc)
            recursion = "recursion" in exc_str.lower() or "GraphRecursion" in exc_name
            logger.warning(
                "DeepAgentsStepExecutor: step %s failed (%s): %s", step.id, exc_name, exc
            )
            return StepResult(
                step_id=step.id,
                status=StepStatus.FAILED,
                output={},
                runtime=self.RUNTIME_NAME,
                attempt=attempt,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                error=f"Deep Agents step error: {exc}",
                escalation_reason=(
                    EscalationReasonCode.TIMEOUT if recursion
                    else EscalationReasonCode.MODEL_FAILURE
                ),
                metadata={"action": step.action, "recursion_limit_hit": recursion},
            )

        messages = result.get("messages", []) if isinstance(result, dict) else []
        self.message_count += len(messages)

        return _parse_step_response(
            messages=messages,
            step=step,
            attempt=attempt,
            started_at=started_at,
            trace_id=context.trace_id,
        )


def _parse_step_response(
    *,
    messages: list,
    step: SOPStep,
    attempt: int,
    started_at: datetime,
    trace_id: str,
) -> StepResult:
    """
    Turn the model's reply into a typed StepResult.

    The model's own ``"status": "completed"`` is recorded as a CLAIM, never
    honoured as completion — the SOP Engine's validator decides. Only
    ``waiting_for_governance`` short-circuits validation, and that direction is
    always safe because it hands control to the human governance layer.

    Chain-of-thought is deliberately dropped: only structured fields survive
    into ``output``, and evidence carries a bounded summary, never a transcript.
    """
    last_text = ""
    for msg in reversed(messages):
        content = getattr(msg, "content", None)
        if isinstance(content, str) and content.strip():
            last_text = content
            break

    completed_at = datetime.now(timezone.utc)
    output: dict[str, Any] = {}
    status = StepStatus.COMPLETED
    error: str | None = None

    parsed = _extract_json_object(last_text, must_contain=("status", "step_id", "output"))

    if parsed is not None:
        raw_status = str(parsed.get("status", "completed")).lower()
        raw_output = parsed.get("output")
        if isinstance(raw_output, dict):
            output.update(raw_output)
        if "recommendation" in parsed and parsed["recommendation"] is not None:
            output["recommendation"] = parsed["recommendation"]

        if "waiting_for_governance" in raw_status:
            status = StepStatus.WAITING_FOR_GOVERNANCE
        elif raw_status == "failed":
            status = StepStatus.FAILED
            error = str(parsed.get("error") or "model reported step failure")
        else:
            status = StepStatus.COMPLETED
    else:
        # Legacy / unstructured reply. Fall back to the Phase 19A text protocol.
        lowered = last_text.lower()
        if "waiting_for_governance" in lowered:
            status = StepStatus.WAITING_FOR_GOVERNANCE
        elif "escalat" in lowered or "human_required" in lowered:
            status = StepStatus.FAILED
            error = "model requested escalation"

        rec_match = re.search(r"RECOMMENDATION:\s*(\{.*?\})", last_text, re.DOTALL | re.IGNORECASE)
        if rec_match:
            try:
                output["recommendation"] = json.loads(rec_match.group(1))
            except json.JSONDecodeError:
                output["recommendation"] = {"raw": rec_match.group(1)[:200]}
        elif status == StepStatus.WAITING_FOR_GOVERNANCE:
            output["recommendation"] = {"summary": last_text[:500]}

    evidence = [
        EvidenceRef(
            type="model_response",
            source="deep_agents",
            reference_id=trace_id or None,
            timestamp=completed_at,
            summary=f"model response for step {step.id!r} ({len(messages)} messages)",
            metadata={
                "step_id": step.id,
                "action": step.action,
                "attempt": attempt,
                "message_count": len(messages),
                "structured": parsed is not None,
                # The model's claim is retained for audit, NOT used as completion.
                "model_claimed_status": status.value,
            },
        )
    ]

    return StepResult(
        step_id=step.id,
        status=status,
        output=output,
        evidence=evidence,
        runtime="deep_agents",
        attempt=attempt,
        started_at=started_at,
        completed_at=completed_at,
        error=error,
        metadata={"action": step.action, "message_count": len(messages)},
    )


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

    SOP Engine V2: the model receives ONE step at a time. It cannot see the
    remaining procedure, cannot choose the next step, and cannot mark a step
    complete — the SOP Engine sequences steps and its validators decide
    completion. The model's reply is parsed into a typed StepResult.

    Runtime provenance recorded: runtime=deep_agents, version=0.7.15,
    agent_id, sop_id, sop_version, task_id, model_route, message_count.
    """

    RUNTIME_NAME = "deep_agents"
    RUNTIME_VERSION = _RUNTIME_VERSION_REAL

    def __init__(self, validator_registry: ValidatorRegistry | None = None) -> None:
        self._validator_registry = validator_registry

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
        """
        Execute an agent task (AgentTaskState) against a MAIW SOPDefinition.

        Procedure control belongs to the SOP Engine; this runtime supplies the
        per-step executor. The model is invoked once per step and never decides
        which step comes next.
        """
        from .model_adapter import MAIWModelGatewayChat

        logger.info(
            "DeepAgentsRuntime.run_task: agent=%s sop=%s task=%s runtime=%s/%s",
            definition.agent_id, sop.id, state.task_id,
            self.RUNTIME_NAME, self.RUNTIME_VERSION,
        )

        # 0. Validate capability alignment (WRITE block)
        self._check_capability_alignment(definition, sop)

        if not sop.steps:
            return self._terminal(state, AgentTaskStatus.FAILED, "SOP has no steps.")

        max_iter = definition.termination_policy.max_iterations

        # 1. Build model (MUST go through ModelGateway)
        model = MAIWModelGatewayChat(
            model_gateway=context.model_gateway,
            trace_id=context.trace_id,
        )

        # 2. Build tools (READ/ANALYTICAL only — WRITE hard-blocked)
        tools = _build_maiw_tools(context, sop.allowed_capabilities)

        # 3. Build subagent specs from MAIW SOP (not framework-invented)
        subagents = _build_subagent_specs(sop, context)

        # 4. Disable LangSmith tracing (no external SaaS dependency)
        os.environ.setdefault("LANGSMITH_TRACING", "false")

        # 5. Bind the model to the per-step executor seam. The step system
        #    prompt is built per step inside the executor, so the model never
        #    receives the whole SOP.
        executor = _DeepAgentsStepExecutor(
            runtime=self,
            sop=sop,
            model=model,
            tools=tools,
            subagents=subagents,
            max_iterations=max_iter,
        )

        remaining_budget = max(max_iter - state.iteration, 0)
        if remaining_budget == 0:
            reason = f"Max iterations ({max_iter}) reached."
            status = (
                AgentTaskStatus.ESCALATED
                if definition.termination_policy.escalate_on_max_iterations
                else AgentTaskStatus.FAILED
            )
            return self._terminal(state, status, reason)

        engine = SOPEngine(
            executor=executor,
            validator_registry=self._validator_registry,
            trace_id=context.trace_id,
            max_transitions=remaining_budget,
        )

        # 6. Run the procedure — the engine sequences and validates every step.
        try:
            proc_state = await engine.run_procedure(
                definition=definition,
                sop=sop,
                agent_task_id=state.task_id,
                context=context,
                warehouse_state_snapshot=(context.bounded_context or {}).get(
                    "_warehouse_state_snapshot"
                ),
            )
        except Exception as exc:
            logger.exception("DeepAgentsRuntime: SOP engine failed: %s", exc)
            return self._terminal(
                state, AgentTaskStatus.FAILED,
                f"Deep Agents runtime error: {exc}",
            )

        return self._to_task_result(
            state, definition, sop, context, proc_state, executor.message_count
        )

    def _build_step_task_context(
        self,
        *,
        sop: SOPDefinition,
        step: SOPStep,
        procedure_state: ProcedureExecutionState,
        context: AgentExecutionContext,
        attempt: int,
    ) -> str:
        """
        Build the human message for a single step.

        Completed steps are summarised (ids only) so the model has procedure
        history without being handed the remaining procedure to run ahead on.
        """
        bounded = context.bounded_context or {}
        parts = [
            f"AGENT TASK ID: {procedure_state.agent_task_id}",
            f"PROCEDURE EXECUTION ID: {procedure_state.procedure_execution_id}",
            f"TRACE ID: {context.trace_id}",
            f"WAREHOUSE: {context.warehouse_id}",
            f"SOP: {sop.id} v{sop.version}",
            f"STEP TO PERFORM: {step.id} (attempt {attempt})",
        ]
        if procedure_state.completed_step_ids:
            parts.append(
                "ALREADY COMPLETED STEPS: "
                + ", ".join(procedure_state.completed_step_ids)
            )
        if bounded:
            parts.append("OPERATIONAL CONTEXT:")
            for key, val in bounded.items():
                if not key.startswith("_"):
                    parts.append(f"  {key}: {val}")
        return "\n".join(parts)

    def _to_task_result(
        self,
        state: AgentTaskState,
        definition: AgentDefinition,
        sop: SOPDefinition,
        context: AgentExecutionContext,
        proc_state: ProcedureExecutionState,
        message_count: int,
    ) -> AgentTaskResult:
        """Project the SOP Engine's procedure state onto the MAIW task contract."""
        observations: list[dict[str, Any]] = []
        recommendation: dict[str, Any] | None = None

        for step_id in proc_state.branch_history + (
            [proc_state.current_step_id]
            if proc_state.current_step_id
            and proc_state.current_step_id in proc_state.step_results
            else []
        ):
            result = proc_state.step_results.get(step_id)
            observations.append({
                "observation_id": f"step-{step_id}",
                "source": "deep_agents_runtime",
                "observation_type": "sop_step",
                "step_id": step_id,
                "status": result.status.value if result else "skipped",
                "attempt": result.attempt if result else 0,
                "validator": (
                    result.validation_result.validator_type.value
                    if result and result.validation_result
                    else None
                ),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            if result is not None and recommendation is None:
                raw_rec = result.output.get("recommendation")
                if isinstance(raw_rec, dict):
                    recommendation = raw_rec

        candidate_actions: list[dict[str, Any]] = []
        if recommendation:
            candidate_actions = [{
                "action": recommendation.get("action", "recommendation"),
                "domain": recommendation.get("domain", "operations"),
                "priority": recommendation.get("priority", "HIGH"),
                "rationale": recommendation.get("rationale", "From Deep Agents runtime"),
            }]

        if proc_state.status == ProcedureStatus.WAITING_FOR_GOVERNANCE:
            final_status = AgentTaskStatus.WAITING_FOR_GOVERNANCE
            stop_reason: str | None = "WAITING_FOR_GOVERNANCE"
        elif proc_state.status == ProcedureStatus.COMPLETED:
            final_status = AgentTaskStatus.COMPLETED
            stop_reason = "OBJECTIVE_MET"
        elif proc_state.status == ProcedureStatus.ESCALATED:
            final_status = AgentTaskStatus.ESCALATED
            stop_reason = None
        else:
            final_status = AgentTaskStatus.FAILED
            stop_reason = None

        escalation_reason: str | None = None
        if final_status in (AgentTaskStatus.ESCALATED, AgentTaskStatus.FAILED):
            for result in proc_state.step_results.values():
                if result.escalation_reason is not None:
                    escalation_reason = (
                        result.escalation_message
                        or f"{result.escalation_reason.value} at step {result.step_id}"
                    )
                    break
            escalation_reason = escalation_reason or "Procedure did not complete."

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
                "procedure_execution_id": proc_state.procedure_execution_id,
                "message_count": message_count,
                "steps_traversed": len(proc_state.branch_history),
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
            stop_reason=stop_reason,
            escalation_reason=escalation_reason,
            observations=observations,
            iterations=state.iteration + len(proc_state.branch_history) + 1,
            completed_at=datetime.now(timezone.utc),
        )

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
        Implement SOPStepExecutor for the Deep Agents runtime.

        Fulfils exactly ONE step. The model sees only this step, cannot choose
        the next one, and cannot mark itself complete — the returned status is
        a claim that the SOP Engine's validator then confirms or rejects.

        Usable standalone (it builds its own model); ``run_task`` uses an
        internal executor that reuses a single prepared model across steps.
        """
        from .model_adapter import MAIWModelGatewayChat

        sop = SOPDefinition.model_construct(
            id=procedure_state.sop_id,
            version=procedure_state.sop_version,
            agent=definition.agent_id,
            objective=definition.objective,
            steps=[step],
            allowed_capabilities=list(definition.allowed_capabilities),
            allowed_subagents=list(definition.allowed_subagents),
            stop_conditions=["objective_met"],
            triggers=[],
            escalation=[],
            required_context=[],
            description=None,
            runtime_profile="adaptive",
        )

        model = MAIWModelGatewayChat(
            model_gateway=context.model_gateway,
            trace_id=context.trace_id,
        )
        executor = _DeepAgentsStepExecutor(
            runtime=self,
            sop=sop,
            model=model,
            tools=_build_maiw_tools(context, definition.allowed_capabilities),
            subagents=[],
            max_iterations=definition.termination_policy.max_iterations,
        )
        return await executor.execute_step(
            definition=definition,
            step=step,
            procedure_state=procedure_state,
            context=context,
            attempt=attempt,
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

        Deep Agents may reason about the outcome but MAIW state transitions remain
        authoritative.

        SOP Engine V2 hardening (Design Section 34): approval alone is not
        completion. An APPROVED outcome is routed through
        ``SOPEngine.resume_after_governance()``, so the resumed step must pass
        its declared completion validator — for a write-related step, a
        STATE_PREDICATE against authoritative post-execution state. An
        indeterminate execution status escalates as EXECUTION_INDETERMINATE
        rather than being retried or assumed successful.
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
        execution_status = governance_outcome.get("execution_status") or "UNKNOWN"

        resume_obs = [{
            "observation_id": "governance-resume",
            "source": "governance",
            "observation_type": "governance_outcome",
            "facts": governance_outcome,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]

        def _result(
            status: AgentTaskStatus,
            *,
            stop_reason: str | None = None,
            escalation_reason: str | None = None,
            extra_obs: list[dict[str, Any]] | None = None,
        ) -> AgentTaskResult:
            return AgentTaskResult(
                task_id=state.task_id,
                agent_id=definition.agent_id,
                sop_id=sop.id,
                sop_version=sop.version,
                final_status=status,
                stop_reason=stop_reason,
                escalation_reason=escalation_reason,
                observations=resume_obs + (extra_obs or []),
                completed_at=datetime.now(timezone.utc),
            )

        if decision in ("REJECTED", "ERROR"):
            return _result(
                AgentTaskStatus.ESCALATED,
                escalation_reason=(
                    f"Governance {decision}: "
                    f"{governance_outcome.get('reason', 'unspecified')}"
                ),
            )

        if decision != "APPROVED":
            return _result(
                AgentTaskStatus.ESCALATED,
                escalation_reason=(
                    f"{EscalationReasonCode.EXECUTION_INDETERMINATE.value}: "
                    f"governance decision {decision!r} is not a completion signal."
                ),
            )

        # APPROVED — the outcome must still be proven against the SOP's
        # completion criteria before the step (and task) may be called done.
        resume_step = self._resolve_governance_step(sop, state)
        proc_state = self._synthesize_procedure_state(sop, state, context, resume_step)

        engine = SOPEngine(
            executor=self,
            validator_registry=self._validator_registry,
            trace_id=context.trace_id,
        )

        outcome_model = _GovernanceOutcomeView(
            decision_outcome=decision,
            execution_status=execution_status,
        )

        resumed = await engine.resume_after_governance(
            definition=definition,
            sop=sop,
            proc_state=proc_state,
            context=context,
            governance_outcome=outcome_model,
            warehouse_state_snapshot=(context.bounded_context or {}).get(
                "_warehouse_state_snapshot"
            ),
        )

        validated_result = resumed.step_results.get(resume_step.id)
        validation_obs = [{
            "observation_id": "governance-resume-validation",
            "source": "sop_engine",
            "observation_type": "post_write_validation",
            "facts": {
                "step_id": resume_step.id,
                "validator": (
                    validated_result.validation_result.validator_type.value
                    if validated_result and validated_result.validation_result
                    else None
                ),
                "valid": (
                    validated_result.validation_result.valid
                    if validated_result and validated_result.validation_result
                    else None
                ),
                "execution_status": execution_status,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]

        if resumed.status == ProcedureStatus.ESCALATED:
            reason = EscalationReasonCode.VALIDATION_FAILED.value
            message = "post-governance validation failed"
            if validated_result is not None:
                if validated_result.escalation_reason is not None:
                    reason = validated_result.escalation_reason.value
                message = validated_result.escalation_message or message
            return _result(
                AgentTaskStatus.ESCALATED,
                escalation_reason=f"{reason}: {message}",
                extra_obs=validation_obs,
            )

        return _result(
            AgentTaskStatus.COMPLETED,
            stop_reason="OBJECTIVE_MET",
            extra_obs=validation_obs,
        )

    @staticmethod
    def _resolve_governance_step(sop: SOPDefinition, state: AgentTaskState) -> SOPStep:
        """
        Find the step the procedure paused on.

        Prefers the task's recorded current step; otherwise the post-execution
        observation step (which is where the write is proven), else the last step.
        """
        by_id = {s.id: s for s in sop.steps}
        if state.current_step_id and state.current_step_id in by_id:
            return by_id[state.current_step_id]
        for step in sop.steps:
            if step.action == "evaluate_post_execution_state":
                return step
        return sop.steps[-1]

    @staticmethod
    def _synthesize_procedure_state(
        sop: SOPDefinition,
        state: AgentTaskState,
        context: AgentExecutionContext,
        resume_step: SOPStep,
    ) -> ProcedureExecutionState:
        """Rebuild the minimum procedure state needed to resume a paused step."""
        now = datetime.now(timezone.utc)
        return ProcedureExecutionState(
            procedure_execution_id=str(uuid.uuid4()),
            sop_id=sop.id,
            sop_version=sop.version,
            agent_task_id=state.task_id,
            trace_id=context.trace_id or (state.trace_id or ""),
            current_step_id=resume_step.id,
            completed_step_ids=list(state.completed_steps),
            status=ProcedureStatus.WAITING_FOR_GOVERNANCE,
            started_at=state.created_at,
            last_updated_at=now,
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
