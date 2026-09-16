# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
ModelGateway — single entry point for all LLM calls in MAIW.

Agents call:
    response = await gateway.generate(ModelRequest(task=..., messages=..., reasoning=...))

The gateway owns:
  - routing (via ModelRouter)
  - provider dispatch (via NIMProvider)
  - error normalisation
  - structured telemetry

Agents must not instantiate NIMClient, select model names, or handle
provider-specific exceptions.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from maiw_mcp.circuit_breaker import CircuitBreaker, CircuitOpen
from maiw_mcp.deadline import RequestDeadlineExceeded

from .errors import ModelGatewayError, ModelUnavailable
from .evaluation.models import EvaluationCallResult
from .models import (
    ModelRequest,
    ModelResponse,
    ModelRouteDecision,
    RiskLevel,
    ReasoningLevel,
)
from .providers.nim import NIMProvider
from .registry import ModelRegistry
from .router import ModelRouter
from .routing import PolicyFilter
from .telemetry import GatewayTelemetry

logger = logging.getLogger(__name__)


class ModelGateway:
    """
    Central model access facade.

    Instantiate once per application via get_model_gateway() and share
    the instance across agents.  Not per-request.
    """

    def __init__(
        self,
        provider: NIMProvider,
        registry: ModelRegistry,
        router: ModelRouter,
        telemetry: Optional[GatewayTelemetry] = None,
        nim_circuit: Optional[CircuitBreaker] = None,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._router = router
        self._telemetry = telemetry or GatewayTelemetry()
        self._nim_circuit = nim_circuit

    async def generate(self, request: ModelRequest) -> ModelResponse:
        """
        Route and execute a model request.

        Returns a normalised ModelResponse.
        Never raises provider-specific exceptions — all errors are
        translated to ModelGatewayError subclasses.
        """
        trace_id = request.trace_id or GatewayTelemetry.new_trace_id()
        decision: ModelRouteDecision | None = None
        start = time.monotonic()

        try:
            # 0. Deadline guard — reject before any provider call (0 provider calls)
            if request.deadline is not None and request.deadline.expired:
                dl = request.deadline
                expired_by_ms = (dl._clock() - dl.deadline_at) * 1000.0  # type: ignore[operator]
                raise RequestDeadlineExceeded(expired_by_ms=expired_by_ms)

            # 1. Route
            decision = self._router.route(request)

            # 2. Resolve capability
            capability = self._registry.get_by_id(decision.selected_model_id)
            if capability is None:
                raise ModelUnavailable(
                    f"Routed to {decision.selected_model_id} but it is not in registry.",
                    model_id=decision.selected_model_id,
                )

            # 3. Call provider (wrapped in NIM circuit breaker if configured)
            async def _provider_call():
                return await self._provider.call(
                    model_id=decision.selected_model_id,
                    request=request,
                    capability=capability,
                )

            if self._nim_circuit is not None:
                try:
                    llm_response = await self._nim_circuit.call(_provider_call())
                except CircuitOpen as exc:
                    raise ModelUnavailable(
                        f"NIM circuit OPEN — cooldown {exc.cooldown_remaining_s:.1f}s remaining",
                        model_id=decision.selected_model_id,
                    ) from exc
            else:
                llm_response = await _provider_call()

            latency_ms = (time.monotonic() - start) * 1000

            # 4. Emit telemetry
            self._telemetry.record_success(
                trace_id=trace_id,
                request=request,
                decision=decision,
                latency_ms=latency_ms,
                usage=llm_response.usage,
                finish_reason=llm_response.finish_reason,
            )

            # 5. Return normalised response
            return ModelResponse(
                content=llm_response.content,
                model_id=llm_response.model,
                model_family="nemotron",
                latency_ms=latency_ms,
                finish_reason=llm_response.finish_reason,
                usage=llm_response.usage,
                route_decision=decision,
                raw_provider_metadata={
                    "provider": "nvidia-nim",
                },
            )

        except ModelGatewayError as exc:
            latency_ms = (time.monotonic() - start) * 1000
            self._telemetry.record_failure(
                trace_id=trace_id,
                request=request,
                decision=decision,
                latency_ms=latency_ms,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            raise

        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            self._telemetry.record_failure(
                trace_id=trace_id,
                request=request,
                decision=decision,
                latency_ms=latency_ms,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            raise

    async def evaluate_with_model(
        self,
        request: ModelRequest,
        model_id: str,
        allow_out_of_policy: bool = False,
    ) -> EvaluationCallResult:
        """
        Forced-model evaluation entry point (evaluation-only — not production routing).

        Evaluates the request against exactly the named model_id, bypassing the
        normal routing strategy.  Policy enforcement is still applied: if the
        model does not satisfy the current deployment/risk/reasoning policy, the
        call is refused unless allow_out_of_policy=True is explicitly set.

        Hard invariants:
          - NEVER silently falls back to another model.  If the forced model
            fails, the result has error set and response_content=None.
          - NEVER creates ActionProposal, approval, or MCP write.
          - NEVER modifies Copilot conversation or approval queues.
          - ALWAYS emits routing/provider telemetry.
          - ALWAYS checks RequestDeadline before calling the provider.

        Args:
            request:             Agent model request (task, messages, reasoning, risk).
            model_id:            The exact model_id to use; must be in registry.
            allow_out_of_policy: When False (default), raises ModelUnavailable if the
                                 forced model is not eligible under the current policy.
                                 When True, proceeds and marks result policy_compliant=False.
                                 Use ONLY for offline research experiments.

        Returns:
            EvaluationCallResult — never raises provider exceptions.
        """
        trace_id = request.trace_id or GatewayTelemetry.new_trace_id()
        policy_start = time.monotonic()

        # ── 1. Capability lookup ──────────────────────────────────────────────
        capability = self._registry.get_by_id(model_id)
        if capability is None:
            err = f"evaluate_with_model: model_id={model_id!r} not found in registry."
            logger.error(err)
            return EvaluationCallResult(
                forced_model_id=model_id,
                policy_compliant=False,
                response_content=None,
                routing_latency_ms=0.0,
                inference_latency_ms=0.0,
                total_latency_ms=0.0,
                candidate_models=[],
                error=err,
            )

        # ── 2. Policy eligibility check ───────────────────────────────────────
        policy_filter = PolicyFilter(self._registry)
        candidate_model_ids = policy_filter.candidate_model_ids(
            request, request.deployment_mode
        )
        policy_compliant = model_id in candidate_model_ids

        if not policy_compliant and not allow_out_of_policy:
            err = (
                f"evaluate_with_model: model_id={model_id!r} is NOT eligible under "
                f"current policy (deployment_mode={request.deployment_mode.value}, "
                f"risk={request.risk_level.value}, reasoning={request.reasoning.value}). "
                f"Eligible models: {candidate_model_ids}. "
                f"Set allow_out_of_policy=True for offline research experiments only."
            )
            logger.warning(err)
            return EvaluationCallResult(
                forced_model_id=model_id,
                policy_compliant=False,
                response_content=None,
                routing_latency_ms=(time.monotonic() - policy_start) * 1000,
                inference_latency_ms=0.0,
                total_latency_ms=(time.monotonic() - policy_start) * 1000,
                candidate_models=candidate_model_ids,
                error=err,
            )

        routing_latency_ms = (time.monotonic() - policy_start) * 1000

        # ── 3. Deadline guard ─────────────────────────────────────────────────
        if request.deadline is not None and request.deadline.expired:
            dl = request.deadline
            expired_by_ms = (dl._clock() - dl.deadline_at) * 1000.0  # type: ignore[operator]
            err = f"RequestDeadlineExceeded: expired {expired_by_ms:.1f}ms ago before provider call."
            return EvaluationCallResult(
                forced_model_id=model_id,
                policy_compliant=policy_compliant,
                response_content=None,
                routing_latency_ms=routing_latency_ms,
                inference_latency_ms=0.0,
                total_latency_ms=routing_latency_ms,
                candidate_models=candidate_model_ids,
                timed_out=True,
                error=err,
            )

        # ── 4. Synthetic route decision (evaluation override) ─────────────────
        synthetic_decision = ModelRouteDecision(
            selected_model_id=model_id,
            selected_role=capability.role,
            requested_role=capability.role,
            routing_rule="evaluation_override",
            routing_reason=(
                f"Forced evaluation: model_id={model_id!r} explicitly requested. "
                f"policy_compliant={policy_compliant}."
            ),
            fallback_from=None,
            fallback_reason=None,
            task=request.task,
            requested_reasoning=request.reasoning,
            requested_risk_level=request.risk_level,
            routing_strategy="forced_evaluation",
            routing_latency_ms=round(routing_latency_ms, 3),
            candidate_models=candidate_model_ids,
        )

        # ── 5. Provider call (no fallback) ────────────────────────────────────
        inference_start = time.monotonic()
        try:
            llm_response = await self._provider.call(
                model_id=model_id,
                request=request,
                capability=capability,
            )
            inference_latency_ms = (time.monotonic() - inference_start) * 1000
            total_latency_ms = routing_latency_ms + inference_latency_ms

            # Emit telemetry.
            self._telemetry.record_success(
                trace_id=trace_id,
                request=request,
                decision=synthetic_decision,
                latency_ms=total_latency_ms,
                usage=llm_response.usage,
                finish_reason=llm_response.finish_reason,
            )

            usage = llm_response.usage or {}
            return EvaluationCallResult(
                forced_model_id=model_id,
                policy_compliant=policy_compliant,
                response_content=llm_response.content,
                routing_latency_ms=round(routing_latency_ms, 3),
                inference_latency_ms=round(inference_latency_ms, 3),
                total_latency_ms=round(total_latency_ms, 3),
                candidate_models=candidate_model_ids,
                fallback_used=False,
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
                finish_reason=llm_response.finish_reason,
            )

        except RequestDeadlineExceeded as exc:
            inference_latency_ms = (time.monotonic() - inference_start) * 1000
            err = f"FORCED MODEL TIMED OUT: {exc}"
            self._telemetry.record_failure(
                trace_id=trace_id,
                request=request,
                decision=synthetic_decision,
                latency_ms=routing_latency_ms + inference_latency_ms,
                error_type="RequestDeadlineExceeded",
                error_message=err,
            )
            return EvaluationCallResult(
                forced_model_id=model_id,
                policy_compliant=policy_compliant,
                response_content=None,
                routing_latency_ms=round(routing_latency_ms, 3),
                inference_latency_ms=round(inference_latency_ms, 3),
                total_latency_ms=round(routing_latency_ms + inference_latency_ms, 3),
                candidate_models=candidate_model_ids,
                fallback_used=False,
                timed_out=True,
                error=err,
            )

        except Exception as exc:
            inference_latency_ms = (time.monotonic() - inference_start) * 1000
            err = f"FORCED MODEL FAILED: {type(exc).__name__}: {exc}"
            logger.error(
                "evaluate_with_model: model=%s failed — %s (fallback NOT attempted)",
                model_id,
                err,
            )
            self._telemetry.record_failure(
                trace_id=trace_id,
                request=request,
                decision=synthetic_decision,
                latency_ms=routing_latency_ms + inference_latency_ms,
                error_type=type(exc).__name__,
                error_message=err,
            )
            return EvaluationCallResult(
                forced_model_id=model_id,
                policy_compliant=policy_compliant,
                response_content=None,
                routing_latency_ms=round(routing_latency_ms, 3),
                inference_latency_ms=round(inference_latency_ms, 3),
                total_latency_ms=round(routing_latency_ms + inference_latency_ms, 3),
                candidate_models=candidate_model_ids,
                fallback_used=False,
                error=err,
            )
