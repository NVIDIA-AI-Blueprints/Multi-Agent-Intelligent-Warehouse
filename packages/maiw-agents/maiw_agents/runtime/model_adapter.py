# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW ModelGateway adapter for Deep Agents runtime — Phase 19A.

Simulates a Deep Agents-compatible model adapter backed by ModelGateway.
Deep Agents MUST NOT instantiate its own provider clients — all model
calls route through this adapter.

Architecture:
    DeepAgentsRuntime
        → MAIWModelAdapter.generate()
            → context.model_gateway (ModelGateway protocol)
                → NIM / external provider

Preserved invariants:
    - RiskLevel from ModelGateway is honored
    - ReasoningLevel from ModelGateway is honored
    - Route provenance (which model/endpoint was used) is preserved
    - trace_id is propagated through all model calls
    - If model_gateway is None (test mode), returns deterministic mock response
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Risk and reasoning level constants (mirror ModelGateway protocol)
_DEFAULT_RISK_LEVEL = "standard"
_DEFAULT_REASONING_LEVEL = "standard"


class MAIWModelAdapter:
    """
    MAIW ModelGateway adapter for the DeepAgentsRuntime.

    Wraps context.model_gateway and exposes a generate() interface that
    the DeepAgentsRuntime calls for each planning/execution step.

    The adapter preserves:
        - RiskLevel (governs which model tier to use)
        - ReasoningLevel (governs depth of reasoning)
        - Route provenance (which model/endpoint was selected)
        - trace_id correlation through all model calls

    In test mode (model_gateway is None), returns deterministic mock responses
    without making any network calls.
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
            text: str           — the model response
            route: str          — which model/endpoint was used
            risk_level: str     — risk level applied
            reasoning_level: str — reasoning level applied
            trace_id: str       — propagated trace ID
            call_index: int     — monotonic call counter for this task

        If model_gateway is None (test mode), returns a deterministic mock.
        """
        self._call_count += 1

        logger.debug(
            "MAIWModelAdapter.generate: step=%s trace=%s call=%d risk=%s",
            step_id, trace_id, self._call_count, self._risk_level,
        )

        if self._gateway is None:
            return self._mock_response(
                prompt=prompt,
                trace_id=trace_id,
                step_id=step_id,
                call_index=self._call_count,
            )

        # Real ModelGateway invocation
        try:
            # ModelGateway exposes: generate(prompt, risk_level, reasoning_level, trace_id, ...)
            if hasattr(self._gateway, "generate"):
                raw = await self._gateway.generate(
                    prompt,
                    risk_level=self._risk_level,
                    reasoning_level=self._reasoning_level,
                    trace_id=trace_id,
                    max_tokens=max_tokens,
                )
            else:
                # Fallback: treat gateway as callable
                raw = await self._gateway(prompt)

            # Normalize raw response
            if isinstance(raw, str):
                text = raw
                route = "model_gateway"
            elif isinstance(raw, dict):
                text = raw.get("text", raw.get("content", str(raw)))
                route = raw.get("route", raw.get("model", "model_gateway"))
            else:
                text = str(raw)
                route = "model_gateway"

        except Exception as exc:
            logger.error(
                "MAIWModelAdapter: ModelGateway call failed: %s trace=%s",
                exc, trace_id,
            )
            # Fall back to mock on failure to preserve test isolation
            return self._mock_response(
                prompt=prompt,
                trace_id=trace_id,
                step_id=step_id,
                call_index=self._call_count,
                error=str(exc),
            )

        return {
            "text": text,
            "route": route,
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
        Deterministic mock response for test mode (model_gateway is None).

        Produces realistic-looking output for each step type without
        requiring live model endpoints.
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
