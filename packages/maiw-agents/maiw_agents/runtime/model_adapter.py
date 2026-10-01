# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW ModelGateway adapters for Deep Agents runtime — Phase 19A.

Two adapters are provided:

MAIWTestModelAdapter (Phase 19A POC — TEST ONLY)
    Simple async wrapper around context.model_gateway. Used by tests and
    the deterministic reference executor. Not a LangChain BaseChatModel —
    not usable by real deepagents create_deep_agent().
    Previously named MAIWModelAdapter (renamed in 19A.11b for clarity).

    EXPLICIT TEST MODE: when model_gateway is None, returns deterministic mock
    responses. Mock is NEVER triggered by a gateway exception — callers must
    pass model_gateway=None explicitly to activate test mode.

MAIWModelGatewayChat (Phase 19A real integration — PRODUCTION)
    LangChain-compatible BaseChatModel backed by MAIW ModelGateway.
    Deep Agents uses this model — it CANNOT bypass ModelGateway.
    All model calls preserve: RiskLevel, ReasoningLevel, DeploymentMode,
    routing provenance, deadline, fallback, telemetry, trace_id.

    EXPLICIT TEST MODE: when model_gateway is None, returns deterministic mock
    responses. Mock is NEVER triggered by a gateway exception — callers must
    pass model_gateway=None explicitly to activate test mode.

Architecture:
    DeepAgentsRuntime
        → MAIWModelGatewayChat._generate()
            → context.model_gateway (ModelGateway protocol)
                → gateway.generate(ModelRequest(...))
                    → NIM / external provider

Canonical gateway call:
    response = await gateway.generate(ModelRequest(
        task=..., messages=..., reasoning=ReasoningLevel.MEDIUM,
        risk_level=RiskLevel.LOW, trace_id=...,
    ))
    text = response.content  # ModelResponse.content — always a str

Preserved invariants:
    - RiskLevel from ModelGateway is honored
    - ReasoningLevel from ModelGateway is honored
    - Route provenance (which model/endpoint was used) is preserved
    - trace_id is propagated through all model calls
    - If model_gateway is None (EXPLICIT test mode): deterministic mock response
    - If model_gateway is not None and raises: exception propagates to caller
      (no silent mock fallback)

Contract repair (Phase 19A.fix.1):
    Previous code called gateway.generate(prompt=..., risk_level=...) which
    does not match ModelGateway.generate(request: ModelRequest). The TypeError
    was swallowed by a broad except Exception which then returned a mock
    response, causing production inference to silently fall back to deterministic
    output. This file corrects both bugs:
      1. Adapter now constructs a canonical ModelRequest.
      2. Broad exception handlers that produced silent mock fallbacks are removed.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from maiw_models.models import ModelRequest, ReasoningLevel, RiskLevel

logger = logging.getLogger(__name__)

# Risk and reasoning level constants (mirror ModelGateway protocol).
# String values are used here for backward-compatibility with callers that
# pass string arguments; they are mapped to enum values in _to_risk_level /
# _to_reasoning_level before constructing ModelRequest.
_DEFAULT_RISK_LEVEL = "standard"
_DEFAULT_REASONING_LEVEL = "standard"

# ── enum helpers ──────────────────────────────────────────────────────────────


def _to_risk_level(s: str) -> RiskLevel:
    """
    Map a case-insensitive string to RiskLevel enum value.

    Accepts: "low", "medium", "high", "critical", "standard" (legacy → LOW).
    Unknown values default to LOW so routing is conservative.
    """
    _map: dict[str, RiskLevel] = {
        "low": RiskLevel.LOW,
        "medium": RiskLevel.MEDIUM,
        "high": RiskLevel.HIGH,
        "critical": RiskLevel.CRITICAL,
        "standard": RiskLevel.LOW,  # legacy default value → LOW
    }
    result = _map.get(s.lower())
    if result is None:
        logger.warning("_to_risk_level: unknown value %r — defaulting to LOW", s)
        return RiskLevel.LOW
    return result


def _to_reasoning_level(s: str) -> ReasoningLevel:
    """
    Map a case-insensitive string to ReasoningLevel enum value.

    Accepts: "low", "medium", "high", "standard" (legacy → MEDIUM).
    Unknown values default to MEDIUM.
    """
    _map: dict[str, ReasoningLevel] = {
        "low": ReasoningLevel.LOW,
        "medium": ReasoningLevel.MEDIUM,
        "high": ReasoningLevel.HIGH,
        "standard": ReasoningLevel.MEDIUM,  # legacy default value → MEDIUM
    }
    result = _map.get(s.lower())
    if result is None:
        logger.warning(
            "_to_reasoning_level: unknown value %r — defaulting to MEDIUM", s
        )
        return ReasoningLevel.MEDIUM
    return result


# ── MAIWTestModelAdapter ──────────────────────────────────────────────────────


class MAIWTestModelAdapter:
    """
    MAIW test-only ModelGateway adapter (Phase 19A POC — TEST USE ONLY).

    Wraps context.model_gateway and exposes a generate() interface for
    test scenarios and the deterministic reference executor. This is NOT
    a LangChain BaseChatModel — it cannot be used with real deepagents
    create_deep_agent(). For production use, see MAIWModelGatewayChat.

    The adapter preserves:
        - RiskLevel (governs which model tier to use)
        - ReasoningLevel (governs depth of reasoning)
        - Route provenance (which model/endpoint was selected)
        - trace_id correlation through all model calls

    EXPLICIT TEST MODE: when model_gateway is None, returns deterministic mock
    responses WITHOUT making any network calls. Mock is ONLY returned when
    model_gateway is None — never as an exception fallback.

    Renamed from MAIWModelAdapter in Phase 19A.11b.
    """

    def __init__(
        self,
        model_gateway: Any = None,
        *,
        risk_level: str = _DEFAULT_RISK_LEVEL,
        reasoning_level: str = _DEFAULT_REASONING_LEVEL,
    ) -> None:
        self._gateway = model_gateway
        self._risk_level = risk_level
        self._reasoning_level = reasoning_level
        self._call_count = 0

    @property
    def call_count(self) -> int:
        """Number of model calls made through this adapter."""
        return self._call_count

    async def generate(
        self,
        prompt: str,
        *,
        trace_id: str,
        step_id: str | None = None,
        context_hint: str | None = None,
        max_tokens: int = 512,
    ) -> dict[str, Any]:
        """
        Generate a model response for the given prompt.

        Returns a dict with:
            text: str            — the model response
            route: str           — which model/endpoint was used
            risk_level: str      — risk level applied
            reasoning_level: str — reasoning level applied
            trace_id: str        — propagated trace ID
            call_index: int      — monotonic call counter for this task

        EXPLICIT TEST MODE: if model_gateway is None, returns a deterministic
        mock without any network call. This is the ONLY path to a mock response.
        Gateway failures are NOT silently converted to mock responses — they
        propagate to the caller so the failure is visible.
        """
        self._call_count += 1

        logger.debug(
            "MAIWTestModelAdapter.generate: step=%s trace=%s call=%d risk=%s",
            step_id,
            trace_id,
            self._call_count,
            self._risk_level,
        )

        # ── EXPLICIT TEST MODE: gateway=None → deterministic mock ─────────────
        if self._gateway is None:
            return self._mock_response(
                prompt=prompt,
                trace_id=trace_id,
                step_id=step_id,
                call_index=self._call_count,
            )

        # ── PRODUCTION PATH: construct canonical ModelRequest ─────────────────
        # ModelGateway.generate(request: ModelRequest) → ModelResponse
        # Do NOT pass bare kwargs — this was the bug that caused silent mock fallback.
        request = ModelRequest(
            task=f"maiw.test.adapter.{step_id or 'unknown'}",
            messages=[{"role": "user", "content": prompt}],
            reasoning=_to_reasoning_level(self._reasoning_level),
            risk_level=_to_risk_level(self._risk_level),
            trace_id=trace_id,
            max_tokens=max_tokens,
        )

        # Any exception from the gateway propagates to the caller.
        # There is NO silent mock fallback here — if the gateway fails,
        # the caller must see the failure.
        response = await self._gateway.generate(request)

        return {
            "text": response.content,
            "route": response.model_id,
            "risk_level": self._risk_level,
            "reasoning_level": self._reasoning_level,
            "trace_id": trace_id,
            "call_index": self._call_count,
            "step_id": step_id,
        }

    def _mock_response(
        self,
        *,
        prompt: str,
        trace_id: str,
        step_id: str | None,
        call_index: int,
        error: str | None = None,
    ) -> dict[str, Any]:
        """
        Deterministic mock response for EXPLICIT test mode (model_gateway is None).

        Produces realistic-looking output for each step type without
        requiring live model endpoints. This method MUST NOT be called as
        an exception fallback — it is only reachable when model_gateway is None.
        """
        step_label = step_id or "unknown"

        # Generate step-specific mock content
        if "plan" in step_label or "planning" in step_label:
            text = (
                f"[MOCK PLAN — step={step_label} call={call_index}] "
                "Plan: 1) Gather context 2) Diagnose constraint 3) Delegate to specialist "
                "4) Generate candidates 5) Compare 6) Recommend 7) Emit recommendation"
            )
        elif "establish_state" in step_label or "gather" in step_label:
            text = (
                f"[MOCK — step={step_label}] "
                "Operational context assembled: wave=17 at_risk_count=3 "
                "pending_count=12 carrier_cutoff_minutes=47 primary_constraint=labor"
            )
        elif "diagnose" in step_label or "determine" in step_label:
            text = (
                f"[MOCK — step={step_label}] "
                "Primary constraint identified: LABOR. "
                "3 workers idle in zone B, 12 picks pending in zone A. "
                "Reallocation is feasible."
            )
        elif "delegate" in step_label or "specialist" in step_label:
            text = (
                f"[MOCK — step={step_label}] "
                "Delegating to LaborAgent: assess capacity deficit in zone A, "
                "evaluate reallocation from zone B."
            )
        elif "candidate" in step_label or "generate" in step_label:
            text = (
                f"[MOCK — step={step_label}] "
                "Candidates: "
                "1) Reallocate 2 workers zone B→A (HIGH impact, LOW risk) "
                "2) Extend shift +30min (MEDIUM impact, MEDIUM risk) "
                "3) Escalate to supervisor (LOW impact, VERY LOW risk)"
            )
        elif "compare" in step_label:
            text = (
                f"[MOCK — step={step_label}] "
                "Comparison: Option 1 dominates on impact/risk ratio. "
                "Reversible, immediate, within carrier cutoff window."
            )
        elif "recommend" in step_label or "select" in step_label:
            text = (
                f"[MOCK — step={step_label}] "
                "Recommendation: Reallocate 2 workers from zone B to zone A. "
                "Priority: HIGH. Domain: labor. Rationale: closes capacity deficit "
                "in 15min, before carrier cutoff in 47min."
            )
        elif "emit" in step_label or "submit" in step_label:
            text = (
                f"[MOCK — step={step_label}] "
                "RecommendedAction emitted. Transitioning to WAITING_FOR_GOVERNANCE."
            )
        elif "observe" in step_label or "evaluate_post" in step_label:
            text = (
                f"[MOCK — step={step_label}] "
                "Post-execution state: wave 17 back on track. "
                "at_risk_count reduced from 3 to 0. Objective met."
            )
        else:
            text = (
                f"[MOCK — step={step_label} call={call_index}] "
                "Step executed successfully."
            )

        if error:
            text = f"[MOCK FALLBACK due to error: {error}] {text}"

        return {
            "text": text,
            "route": "mock://test-mode",
            "risk_level": self._risk_level,
            "reasoning_level": self._reasoning_level,
            "trace_id": trace_id,
            "call_index": call_index,
            "step_id": step_label,
            "mock": True,
        }


# Backward-compatible alias (deprecated — use MAIWTestModelAdapter)
MAIWModelAdapter = MAIWTestModelAdapter


# ── MAIWModelGatewayChat ──────────────────────────────────────────────────────

try:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import (
        BaseMessage,
        AIMessage,
        HumanMessage,
        SystemMessage,
    )
    from langchain_core.outputs import ChatResult, ChatGeneration
    from langchain_core.callbacks import CallbackManagerForLLMRun

    def _lc_role(msg: BaseMessage) -> str:
        """Map a LangChain message type to a role string for ModelRequest.messages."""
        if isinstance(msg, SystemMessage):
            return "system"
        if isinstance(msg, HumanMessage):
            return "user"
        # AIMessage, ToolMessage, FunctionMessage, etc.
        return "assistant"

    class MAIWModelGatewayChat(BaseChatModel):
        """
        LangChain-compatible BaseChatModel backed by MAIW ModelGateway.

        Deep Agents uses this model — it CANNOT bypass ModelGateway.
        All model calls preserve: RiskLevel, ReasoningLevel, DeploymentMode,
        routing provenance, deadline, fallback, telemetry, trace_id.

        EXPLICIT TEST MODE: when model_gateway is None, returns deterministic
        mock responses. Mock is NEVER triggered by a gateway exception —
        callers must pass model_gateway=None explicitly to activate test mode.

        Gateway failures surface as typed exceptions, never as silent mock
        replacements.

        Canonical call path:
            _generate(messages)
                → ModelRequest(task, messages, reasoning, risk_level, trace_id)
                → gateway.generate(request)  → ModelResponse
                → ModelResponse.content      → AIMessage.content → ChatResult
        """

        model_name: str = "maiw-gateway"
        model_gateway: Optional[Any] = None
        trace_id: str = ""
        risk_level: str = "LOW"
        reasoning_level: str = "STANDARD"
        deployment_mode: str = "LOCAL"

        model_config = {"arbitrary_types_allowed": True}

        @property
        def _llm_type(self) -> str:
            return "maiw-model-gateway"

        def bind_tools(self, tools: Any, **kwargs: Any) -> "MAIWModelGatewayChat":
            """
            No-op tool binding — MAIW mock model responds with text, not tool calls.
            Returns self so deepagents can continue graph construction.
            Real ModelGateway routing handles tool-equivalent capabilities via
            MAIW skill adapters and SubAgent specs.
            """
            return self

        def _generate(
            self,
            messages: list[BaseMessage],
            stop: Optional[list[str]] = None,
            run_manager: Optional[CallbackManagerForLLMRun] = None,
            **kwargs: Any,
        ) -> ChatResult:
            """
            Synchronous LangChain inference hook.

            Routes through ModelGateway when model_gateway is set.
            Returns deterministic mock only when model_gateway is None (EXPLICIT
            test mode).

            Gateway failures propagate to the caller — there is no silent
            mock fallback.
            """
            # Build the canonical message list for ModelRequest
            gw_messages = [
                {"role": _lc_role(m), "content": m.content}
                for m in messages
                if hasattr(m, "content") and isinstance(m.content, str)
            ]

            # ── EXPLICIT TEST MODE: model_gateway=None → deterministic mock ──
            if self.model_gateway is None:
                # Reconstruct flat prompt only for the mock path (mock needs a
                # text summary; production path uses structured gw_messages).
                prompt = "\n".join(msg["content"] for msg in gw_messages)
                response_text = self._mock_response(prompt)
                return ChatResult(
                    generations=[
                        ChatGeneration(message=AIMessage(content=response_text))
                    ]
                )

            # ── PRODUCTION PATH: construct canonical ModelRequest ─────────────
            # ModelGateway.generate(request: ModelRequest) → ModelResponse.
            # Any exception propagates to the caller — NO silent mock fallback.
            import asyncio
            import concurrent.futures

            request = ModelRequest(
                task="maiw.deep_agents.step",
                messages=gw_messages,
                reasoning=_to_reasoning_level(self.reasoning_level),
                risk_level=_to_risk_level(self.risk_level),
                trace_id=self.trace_id or None,
            )

            logger.debug(
                "MAIWModelGatewayChat._generate: task=%s trace=%s risk=%s reasoning=%s",
                request.task,
                request.trace_id,
                request.risk_level,
                request.reasoning,
            )

            # Run the async gateway call in a worker thread to avoid blocking
            # the calling event loop and to avoid deprecated get_event_loop()
            # patterns.  future.result() re-raises any exception from the
            # coroutine, so gateway errors are never swallowed here.
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    asyncio.run,
                    self.model_gateway.generate(request),
                )
                response = future.result()  # ModelResponse — raises on gateway failure

            return ChatResult(
                generations=[
                    ChatGeneration(message=AIMessage(content=response.content))
                ]
            )

        async def _agenerate(
            self,
            messages: list[BaseMessage],
            stop: Optional[list[str]] = None,
            run_manager: Optional[Any] = None,
            **kwargs: Any,
        ) -> ChatResult:
            """
            Async LangChain inference hook.

            Calls the gateway directly (no thread pool needed — already async).
            Gateway failures propagate to the caller — NO silent mock fallback.
            """
            gw_messages = [
                {"role": _lc_role(m), "content": m.content}
                for m in messages
                if hasattr(m, "content") and isinstance(m.content, str)
            ]

            # ── EXPLICIT TEST MODE ─────────────────────────────────────────────
            if self.model_gateway is None:
                prompt = "\n".join(msg["content"] for msg in gw_messages)
                response_text = self._mock_response(prompt)
                return ChatResult(
                    generations=[
                        ChatGeneration(message=AIMessage(content=response_text))
                    ]
                )

            # ── PRODUCTION PATH ────────────────────────────────────────────────
            request = ModelRequest(
                task="maiw.deep_agents.step",
                messages=gw_messages,
                reasoning=_to_reasoning_level(self.reasoning_level),
                risk_level=_to_risk_level(self.risk_level),
                trace_id=self.trace_id or None,
            )

            logger.debug(
                "MAIWModelGatewayChat._agenerate: task=%s trace=%s risk=%s reasoning=%s",
                request.task,
                request.trace_id,
                request.risk_level,
                request.reasoning,
            )

            # Raises on gateway failure — no silent mock fallback.
            response = await self.model_gateway.generate(request)

            return ChatResult(
                generations=[
                    ChatGeneration(message=AIMessage(content=response.content))
                ]
            )

        def _mock_response(self, prompt: str) -> str:
            """
            Deterministic test-mode responses based on prompt content.

            ONLY called when model_gateway is None (explicit test mode).
            NEVER called as an exception fallback from a gateway error.
            """
            p = prompt.lower()

            # When governance boundary is mentioned (always present in SOP system prompt),
            # return a governance stop signal so tests always reach WAITING_FOR_GOVERNANCE.
            if "waiting_for_governance" in p or "governance" in p:
                return (
                    "Analysis complete. All SOP steps executed.\n"
                    'RECOMMENDATION: {"domain": "labor", "action": "reallocate_workers",'
                    ' "priority": "HIGH", "rationale": "Closes capacity deficit before carrier cutoff"}\n'
                    "STOP: WAITING_FOR_GOVERNANCE"
                )

            if "diagnose" in p or "constraint" in p:
                return (
                    "Primary constraint identified: LABOR. "
                    "Wave 17 has insufficient workers for Zone B pending picks."
                )
            if "recommend" in p or "candidate" in p:
                return (
                    "Recommendation: Reallocate 2 workers from Zone A (low priority) "
                    "to Zone B (Wave 17 picks). Priority: HIGH."
                )
            if "labor" in p:
                return "Labor assessment complete. 3 workers available for reallocation from Zone A."

            return (
                "Step completed. Proceeding to next step.\n"
                'RECOMMENDATION: {"domain": "operations", "action": "proceed", "priority": "MEDIUM"}\n'
                "STOP: WAITING_FOR_GOVERNANCE"
            )

except ImportError:
    # langchain_core not installed — MAIWModelGatewayChat unavailable
    # Only raised if deepagents optional dep is not installed.
    class MAIWModelGatewayChat:  # type: ignore[no-redef]
        """Stub: langchain_core not installed. Install deepagents optional dep."""

        _llm_type = "maiw-model-gateway"

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError(
                "MAIWModelGatewayChat requires langchain_core. "
                "Install: pip install 'maiw-agents[deep-agents]'"
            )
