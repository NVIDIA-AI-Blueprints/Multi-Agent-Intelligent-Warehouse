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
Thin HTTP client for reaching the host-side MAIW ModelGateway from a sandbox.

This client is the ONLY way inference flows from inside an OpenShell/NemoClaw
sandbox to the canonical ModelGateway on the host. It has a single
responsibility: transport.

WHAT THIS CLIENT DOES NOT DO
    - Route requests to any model or provider
    - Apply model family policy  (PolicyFilter on the host handles that)
    - Select fallback models     (ModelRouter on the host handles that)
    - Hold NVIDIA or NIM credentials  (host ModelGateway holds those)
    - Cache or retry with a different provider
    - Access a NIM endpoint directly

WHAT THIS CLIENT DOES
    - Serialize a ModelRequest subset to InferenceRequest JSON
    - Call POST /api/v1/inference on the configured host endpoint
    - Deserialize InferenceResponse into a ModelResponse
    - Translate structured HTTP error codes into typed ModelGatewayError
    - Propagate the deadline budget (remaining milliseconds, not a new deadline)
    - Forward trace correlation IDs

NO TRANSPORT FALLBACK
    If the HTTP call fails (connection error, non-2xx status, structured error),
    the failure is surfaced as a typed ModelGatewayError subclass.  This client
    NEVER falls back to a local in-process gateway, a direct NIM endpoint, or
    a mock inference response.  Failure stays failure.

TRUST ASSUMPTION
    This client runs inside the sandbox. It presents the pre-configured
    MAIW_INFERENCE_INTERNAL_TOKEN (if set) as the X-Maiw-Internal-Token header.
    The token value must be injected at sandbox launch time via the host; the
    sandbox itself cannot derive or change it.  No provider credential is held
    or transmitted.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Import guard: ModelGateway types must come from the host package ──────────
try:
    from maiw_models import (
        ModelRequest,
        ModelResponse,
        ModelRouteDecision,
        ModelUnavailable,
        ModelGatewayError,
    )
    from maiw_mcp.deadline import RequestDeadlineExceeded

    _MAIW_MODELS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _MAIW_MODELS_AVAILABLE = False


# ── Error codes matching the host endpoint ─────────────────────────────────────

_CODE_TO_EXCEPTION: dict[str, type] = {}
if _MAIW_MODELS_AVAILABLE:
    from maiw_models.errors import ModelGatewayError, ModelUnavailable

    _CODE_TO_EXCEPTION = {
        "MODEL_UNAVAILABLE": ModelUnavailable,
        "CIRCUIT_OPEN": ModelUnavailable,
        # DEADLINE_EXCEEDED: raise as RequestDeadlineExceeded
        # PROVIDER_FAILURE: raise as ModelGatewayError
    }


class SandboxInferenceError(Exception):
    """Raised when the HTTP transport itself fails (network / parse / unexpected status)."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class MAIWHTTPModelGatewayClient:
    """
    Thin HTTP transport client for sandbox → host ModelGateway inference.

    Instantiate once per sandbox runtime session.  The endpoint is the
    value of SandboxConfig.model_gateway_endpoint.

    Parameters
    ----------
    endpoint:
        Full URL of the host MAIW ModelGateway inference endpoint.
        Example: ``http://maiw-api:8000/api/v1/inference``
        MUST be the value configured in SandboxConfig.model_gateway_endpoint.
        MUST NOT be localhost, a private-subnet wildcard, or a NIM endpoint.
    internal_token:
        Value of MAIW_INFERENCE_INTERNAL_TOKEN if set on the host.  The
        sandbox receives this at launch; it does not derive or store it beyond
        the session.
    timeout_s:
        Per-request HTTP timeout in seconds.  The sandbox-supplied deadline_ms
        is forwarded to the host endpoint and is the authoritative budget.
        This timeout is a safety net for the transport layer only.
    """

    def __init__(
        self,
        endpoint: str,
        internal_token: str | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        if not endpoint.startswith(("http://", "https://")):
            raise ValueError(
                f"MAIWHTTPModelGatewayClient: endpoint {endpoint!r} must be "
                "http or https."
            )
        # Reject localhost/loopback — the sandbox is not on the same host.
        _lower = endpoint.lower()
        if any(sub in _lower for sub in ("localhost", "127.0.0.1", "::1", "0.0.0.0")):
            raise ValueError(
                f"MAIWHTTPModelGatewayClient: endpoint {endpoint!r} must not be "
                "localhost or loopback.  The sandbox calls the host endpoint over "
                "the sanctioned network — direct loopback access is not permitted."
            )
        self._endpoint = endpoint
        self._internal_token = internal_token
        self._timeout_s = timeout_s

    async def generate(self, request: "ModelRequest") -> "ModelResponse":
        """
        Serialize request, POST to host endpoint, deserialize response.

        Raises
        ------
        RequestDeadlineExceeded
            When the host returns HTTP 504 (deadline exceeded).
        ModelUnavailable
            When the host returns 503 MODEL_UNAVAILABLE or CIRCUIT_OPEN.
        ModelGatewayError
            For all other structured error responses from the host.
        SandboxInferenceError
            For transport failures (network error, unexpected HTTP status,
            unparseable response body).
        """
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise SandboxInferenceError(
                "httpx is required for sandbox HTTP inference. "
                "Install it: pip install httpx"
            ) from exc

        # ── Serialize request ─────────────────────────────────────────────
        deadline_ms = 0
        if request.deadline is not None and not request.deadline.expired:
            deadline_ms = max(0, int(request.deadline.remaining_seconds * 1000))

        payload: dict[str, Any] = {
            "task": request.task,
            "messages": [
                {"role": m["role"], "content": m.get("content", "")}
                for m in request.messages
                if isinstance(m, dict) and "role" in m
            ],
            "reasoning": request.reasoning.value,
            "risk_level": request.risk_level.value,
            "modality": request.modality.value,
            "deadline_ms": deadline_ms,
        }

        # Propagate trace IDs.
        if request.trace_id:
            payload["trace_id"] = request.trace_id
        meta = request.metadata or {}
        for field in ("agent_task_id", "procedure_execution_id", "step_execution_id"):
            if field in meta:
                payload[field] = meta[field]

        # ── Build headers ─────────────────────────────────────────────────
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._internal_token:
            headers["X-Maiw-Internal-Token"] = self._internal_token

        # ── HTTP call ─────────────────────────────────────────────────────
        try:
            async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                resp = await client.post(
                    self._endpoint,
                    json=payload,
                    headers=headers,
                )
        except httpx.TimeoutException as exc:
            raise SandboxInferenceError(
                f"HTTP timeout calling MAIW inference endpoint {self._endpoint!r}: {exc}"
            ) from exc
        except httpx.RequestError as exc:
            raise SandboxInferenceError(
                f"Network error calling MAIW inference endpoint {self._endpoint!r}: {exc}"
            ) from exc

        # ── Deserialize response ──────────────────────────────────────────
        if resp.status_code == 200:
            return self._parse_success(resp, request)

        # Structured error response.
        return self._raise_structured_error(resp)

    def _parse_success(self, resp: Any, request: "ModelRequest") -> "ModelResponse":
        """Parse a successful inference response.

        Parameters
        ----------
        resp:
            The raw httpx response object.
        request:
            The original ModelRequest — used to preserve routing provenance
            (task identity, requested_reasoning, requested_risk_level).
        """
        try:
            data = resp.json()
        except Exception as exc:
            raise SandboxInferenceError(
                "Failed to parse inference response JSON.", status_code=resp.status_code
            ) from exc

        # Reconstruct ModelRouteDecision from route metadata.
        # Provenance fields (task, reasoning, risk_level) are taken from the
        # ORIGINAL request, not from the response body — the response echoes the
        # model's view, but the authoritative intent is the caller's request.
        route = data.get("route", {})
        selected_model_id = route.get("selected_model_id", data.get("model_id", ""))
        route_decision = ModelRouteDecision(
            selected_model_id=selected_model_id,
            selected_role=route.get("selected_role", ""),
            requested_role=route.get("selected_role", ""),
            routing_rule=route.get("routing_rule", ""),
            routing_reason=f"Sandbox HTTP transport: {route.get('routing_rule', '')}",
            fallback_from=None,
            fallback_reason=None,
            # Preserve request identity — NOT hard-coded defaults.
            task=request.task,
            requested_reasoning=request.reasoning,
            requested_risk_level=request.risk_level,
            routing_strategy="http_sandbox",
            routing_latency_ms=0.0,
            candidate_models=[selected_model_id],
        )

        return ModelResponse(
            content=data["content"],
            model_id=data["model_id"],
            model_family="nemotron",
            latency_ms=data.get("latency_ms", 0.0),
            finish_reason=data.get("finish_reason", ""),
            usage={},
            route_decision=route_decision,
        )

    def _raise_structured_error(self, resp: Any) -> "ModelResponse":
        """Parse a structured error response and raise the appropriate exception."""
        status_code = resp.status_code
        try:
            data = resp.json()
            code = data.get("code", "UNKNOWN")
            message = data.get("message", str(data))
        except Exception:
            code = "UNKNOWN"
            message = resp.text or f"HTTP {status_code}"

        logger.error(
            "inference HTTP error: status=%d code=%s message=%s",
            status_code,
            code,
            message,
        )

        if status_code == 504 or code == "DEADLINE_EXCEEDED":
            raise RequestDeadlineExceeded(expired_by_ms=0)

        if status_code == 401:
            raise SandboxInferenceError(
                f"Unauthorized: {message}", status_code=status_code
            )

        exc_class = _CODE_TO_EXCEPTION.get(code, ModelGatewayError)
        raise exc_class(message)


__all__ = [
    "MAIWHTTPModelGatewayClient",
    "SandboxInferenceError",
]
