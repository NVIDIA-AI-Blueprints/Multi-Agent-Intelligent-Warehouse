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

from maiw_mcp.deadline import RequestDeadlineExceeded

from .errors import ModelGatewayError, ModelUnavailable
from .models import ModelRequest, ModelResponse, ModelRouteDecision
from .providers.nim import NIMProvider
from .registry import ModelRegistry
from .router import ModelRouter
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
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._router = router
        self._telemetry = telemetry or GatewayTelemetry()

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

            # 3. Call provider
            llm_response = await self._provider.call(
                model_id=decision.selected_model_id,
                request=request,
                capability=capability,
            )

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
