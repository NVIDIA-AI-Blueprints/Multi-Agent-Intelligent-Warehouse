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
Structured telemetry for ModelGateway.

Emits a single JSON log line per model call covering routing, latency,
token usage, and outcome.  Uses the repository's existing logging stack
(stdlib logging with structured dicts) so no additional observability
framework is introduced.

When OpenTelemetry is wired in at a later phase, this module is the
integration point — replace the logger calls with span attributes.

Key telemetry fields for routing observability:
  requested_role  — ideal role before fallbacks (tells you what the policy wanted)
  selected_role   — role that actually served the request (tells you what ran)
  routing_rule    — machine-readable rule slug (e.g. "medium_reasoning")
  routing_reason  — human-readable reason for the routing policy decision
  fallback_from   — populated when selected_role != requested_role
  fallback_reason — why the preferred role was skipped

Example log entry showing an accurate fallback scenario:
  {
    "requested_role": "nano",
    "selected_role": "super",
    "routing_rule": "medium_reasoning",
    "routing_reason": "reasoning=MEDIUM prefers Nano",
    "fallback_from": "nano",
    "fallback_reason": "role=nano is disabled; escalated to super"
  }
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from .models import ModelRequest, ModelRouteDecision

logger = logging.getLogger(__name__)


class GatewayTelemetry:
    """Emits structured telemetry for every ModelGateway call."""

    def record_success(
        self,
        *,
        trace_id: str,
        request: ModelRequest,
        decision: ModelRouteDecision,
        latency_ms: float,
        usage: dict[str, int],
        finish_reason: str,
    ) -> None:
        logger.info(
            "model_gateway_call",
            extra={
                "event": "model_gateway_call",
                "trace_id": trace_id,
                "task": request.task,
                # Request intent
                "requested_reasoning": request.reasoning.value,
                "requested_risk_level": request.risk_level.value,
                "modality": request.modality.value,
                # Routing — separate requested from actual for observability
                "requested_role": decision.requested_role,
                "selected_role": decision.selected_role,
                "routing_rule": decision.routing_rule,
                "routing_reason": decision.routing_reason,
                # Fallback tracing
                "fallback_from": decision.fallback_from,
                "fallback_reason": decision.fallback_reason,
                # Physical model
                "selected_model": decision.selected_model_id,
                # Outcome
                "latency_ms": round(latency_ms, 1),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "finish_reason": finish_reason,
                "success": True,
            },
        )

    def record_failure(
        self,
        *,
        trace_id: str,
        request: ModelRequest,
        decision: ModelRouteDecision | None,
        latency_ms: float,
        error_type: str,
        error_message: str,
    ) -> None:
        logger.error(
            "model_gateway_call_failed",
            extra={
                "event": "model_gateway_call_failed",
                "trace_id": trace_id,
                "task": request.task,
                "requested_reasoning": request.reasoning.value,
                "requested_risk_level": request.risk_level.value,
                "modality": request.modality.value,
                "requested_role": decision.requested_role if decision else None,
                "selected_role": decision.selected_role if decision else None,
                "routing_rule": decision.routing_rule if decision else None,
                "routing_reason": decision.routing_reason if decision else None,
                "fallback_from": decision.fallback_from if decision else None,
                "selected_model": decision.selected_model_id if decision else None,
                "latency_ms": round(latency_ms, 1),
                "error_type": error_type,
                "error_message": error_message,
                "success": False,
            },
        )

    @staticmethod
    def new_trace_id() -> str:
        return str(uuid.uuid4())
