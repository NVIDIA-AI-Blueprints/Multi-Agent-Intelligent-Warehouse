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
Bounded HTTP inference endpoint — POST /api/v1/inference.

This is the ONLY surface through which a sandboxed MAIW agent runtime
(NemoClaw/OpenShell) reaches the canonical ModelGateway on the host.

Design constraints (Phase 20C-A):

  ALLOWLIST FIELDS ONLY
      The request body is a strict subset of ModelRequest fields.  Fields that
      could expose provider URLs, API keys, base URLs, arbitrary deployment
      endpoints, or raw model overrides are NOT accepted and are rejected with
      HTTP 422 if present in the body.

  CANONICAL GATEWAY
      Every inference call uses the process-level ModelGateway singleton from
      get_model_gateway().  A new gateway is never created per-request.

  POLICY FILTER IS AUTHORITATIVE
      Model selection is always performed by the canonical PolicyFilter inside
      ModelGateway.  The sandbox cannot name a model; it can only express a
      task intent, reasoning level, risk level, and modality.

  NO GOVERNANCE BELOW THIS LINE
      This endpoint calls ModelGateway.generate() only.  It does not create
      ActionProposal objects, invoke DecisionEngine, touch ApprovalStore, or
      execute ActionExecutor.  Governance remains entirely outside this surface.

  DEADLINE PROPAGATION
      Callers supply a deadline_ms field.  The host translates it to a
      RequestDeadline before calling ModelGateway, ensuring the full path
      (HTTP → ModelRequest → ModelGateway → NIMProvider) is bounded.

  TRACE PROPAGATION
      trace_id, agent_task_id, procedure_execution_id, step_execution_id are
      forwarded as ModelRequest.metadata and ModelRequest.trace_id to produce
      end-to-end correlated telemetry.

  ERROR VISIBILITY
      Failures are returned as structured JSON errors — never silently replaced
      with mock success or a fallback provider response.  Every error category
      has a distinct HTTP status and machine-readable code.

  TRUST ASSUMPTION
      This endpoint is deployed behind the MAIW API server, which is on a
      network that only the approved sandbox runtime and host processes can
      reach.  It does NOT issue provider credentials; it relies on the host
      ModelGateway holding those credentials.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

from maiw_models import (
    ModelRequest,
    ModelUnavailable,
    ModelGatewayError,
    ReasoningLevel,
    RiskLevel,
    Modality,
    DeploymentMode,
    get_model_gateway,
)
from maiw_mcp.deadline import RequestDeadline, RequestDeadlineExceeded

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Inference"])

# ── Input bounds ───────────────────────────────────────────────────────────────

_MAX_MESSAGE_COUNT = int(os.getenv("MAIW_INFERENCE_MAX_MESSAGES", "64"))
_MAX_CONTENT_BYTES = int(
    os.getenv("MAIW_INFERENCE_MAX_CONTENT_BYTES", str(32 * 1024))
)  # 32 KiB
_MAX_TASK_BYTES = 512
_MAX_DEADLINE_MS = 300_000  # 5 minutes

# ── Internal trust header ──────────────────────────────────────────────────────
# The sandbox presents this shared-secret header (configured per deployment).
# None disables the check (development mode only — not for production use).
_INFERENCE_INTERNAL_TOKEN_ENV = "MAIW_INFERENCE_INTERNAL_TOKEN"


# ── Request / Response contracts ───────────────────────────────────────────────


class InferenceMessage(BaseModel):
    """
    A single chat message.

    Equivalent to one element of ModelRequest.messages.
    Only role and content are accepted — no function call metadata.
    """

    role: Literal["user", "assistant", "system"]
    content: str = Field(..., max_length=_MAX_CONTENT_BYTES)


class InferenceRequest(BaseModel):
    """
    Sandbox-facing inference request.

    FIELD ALLOWLIST: only the following fields may be present.  Any field not
    listed here is rejected.  In particular, the following fields from
    ModelRequest are NOT exposed:

      - deployment_endpoint     (would bypass Deployment Resolver)
      - api_key_env_var         (credential surface)
      - provider_url            (SSRF risk; ModelGateway owns provider routing)
      - base_url                (same reason)
      - force_model_id          (sandbox cannot dictate model selection)
      - raw model override      (PolicyFilter is authoritative)

    The sandbox describes task *intent*.  ModelGateway decides the model.
    """

    task: str = Field(..., max_length=_MAX_TASK_BYTES, description="Agent task name.")
    messages: list[InferenceMessage] = Field(
        ...,
        min_length=1,
        max_length=_MAX_MESSAGE_COUNT,
        description="Conversation messages.",
    )
    reasoning: ReasoningLevel = Field(
        default=ReasoningLevel.MEDIUM,
        description="Required reasoning depth.",
    )
    risk_level: RiskLevel = Field(
        default=RiskLevel.LOW,
        description="Operational risk level of this inference call.",
    )
    modality: Modality = Field(
        default=Modality.TEXT,
        description="Required modality.",
    )
    # Deadline in wall-clock milliseconds from now.  0 or absent → no deadline.
    deadline_ms: int = Field(
        default=0,
        ge=0,
        le=_MAX_DEADLINE_MS,
        description=(
            "Wall-clock deadline for the entire request in milliseconds. "
            "0 = no deadline (provider default timeout applies)."
        ),
    )
    # Trace correlation IDs — passed through to telemetry, not used for routing.
    trace_id: str | None = Field(default=None, max_length=128)
    agent_task_id: str | None = Field(default=None, max_length=128)
    procedure_execution_id: str | None = Field(default=None, max_length=128)
    step_execution_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode="before")
    @classmethod
    def _reject_forbidden_fields(cls, data: Any) -> Any:
        """
        Hard-reject any field that could expose provider configuration or
        allow the sandbox to bypass model family policy.
        """
        if not isinstance(data, dict):
            return data
        forbidden = {
            "provider_url",
            "base_url",
            "api_key",
            "api_key_env_var",
            "deployment_endpoint",
            "force_model_id",
            "model_id",
            "deployment_mode",  # always NVIDIA_HOSTED for sandbox calls
        }
        found = forbidden & set(data.keys())
        if found:
            raise ValueError(
                f"Forbidden field(s) in inference request: {sorted(found)}. "
                "The sandbox may not influence provider selection, credentials, "
                "or deployment mode."
            )
        return data


class RouteMetadata(BaseModel):
    """
    Safe route provenance returned to the sandbox.

    Contains only the information needed for sandbox-side tracing and
    audit.  No provider URLs, API keys, or deployment details are included.
    """

    selected_model_id: str
    selected_role: str
    generation: str
    approved_family: bool
    routing_rule: str
    fallback_used: bool
    candidate_count: int


class InferenceResponse(BaseModel):
    """
    Sandbox-facing inference response.

    Only safe, non-secret fields are returned.
    """

    content: str
    model_id: str
    finish_reason: str
    latency_ms: float
    route: RouteMetadata
    trace_id: str | None
    agent_task_id: str | None
    procedure_execution_id: str | None
    step_execution_id: str | None


# ── Error response ────────────────────────────────────────────────────────────


class InferenceError(BaseModel):
    """Structured error returned on all non-2xx responses."""

    code: str
    message: str
    trace_id: str | None = None


# ── Auth dependency ───────────────────────────────────────────────────────────


def _verify_internal_token(
    x_maiw_internal_token: str | None = Header(default=None),
) -> None:
    """
    Verify the sandbox presents the shared internal token.

    This is a lightweight bearer-style check for the internal sandbox→host
    network.  It supplements (not replaces) network-level isolation.

    When MAIW_INFERENCE_INTERNAL_TOKEN is not configured, the check is
    skipped — suitable for development only.
    """
    from fastapi import HTTPException

    expected = os.getenv(_INFERENCE_INTERNAL_TOKEN_ENV)
    if not expected:
        # Development mode: no token configured.  Log but do not reject.
        logger.debug("inference: internal token check disabled (no token configured)")
        return
    if x_maiw_internal_token != expected:
        logger.warning("inference: rejected request with invalid internal token")
        raise HTTPException(status_code=401, detail="Invalid internal token.")


# ── Endpoint ──────────────────────────────────────────────────────────────────


@router.post(
    "/inference",
    response_model=InferenceResponse,
    summary="Sandbox inference via canonical ModelGateway",
    description=(
        "Execute an inference request through the canonical MAIW ModelGateway. "
        "Model selection, approved-family enforcement, and provider dispatch are "
        "all handled by the host-side ModelGateway. The sandbox supplies only "
        "task intent; it cannot name a model, provider, or endpoint."
    ),
    responses={
        400: {"model": InferenceError, "description": "Malformed request"},
        401: {"model": InferenceError, "description": "Unauthorized"},
        422: {
            "model": InferenceError,
            "description": "Validation error / forbidden field",
        },
        503: {
            "model": InferenceError,
            "description": "Model unavailable or circuit open",
        },
        504: {"model": InferenceError, "description": "Deadline exceeded"},
    },
)
async def sandbox_inference(
    body: InferenceRequest,
    _token: None = Depends(_verify_internal_token),
) -> InferenceResponse | JSONResponse:
    """
    Translate sandbox InferenceRequest → canonical ModelRequest →
    canonical ModelGateway.generate() → InferenceResponse.

    One deterministic translation: no hidden routing, no model override,
    no provider bypass.

    Deployment mode is always NVIDIA_HOSTED for sandbox calls; the sandbox
    cannot alter this.
    """
    t0 = time.monotonic()

    # ── 1. Build RequestDeadline ─────────────────────────────────────────────
    deadline: RequestDeadline | None = None
    if body.deadline_ms > 0:
        deadline = RequestDeadline.from_timeout(seconds=body.deadline_ms / 1000.0)

    # ── 2. Build canonical ModelRequest ─────────────────────────────────────
    # deployment_mode is always NVIDIA_HOSTED; the sandbox has no say in this.
    metadata: dict[str, Any] = {}
    if body.agent_task_id is not None:
        metadata["agent_task_id"] = body.agent_task_id
    if body.procedure_execution_id is not None:
        metadata["procedure_execution_id"] = body.procedure_execution_id
    if body.step_execution_id is not None:
        metadata["step_execution_id"] = body.step_execution_id

    model_request = ModelRequest(
        task=body.task,
        messages=[m.model_dump() for m in body.messages],
        reasoning=body.reasoning,
        risk_level=body.risk_level,
        modality=body.modality,
        deployment_mode=DeploymentMode.NVIDIA_HOSTED,
        trace_id=body.trace_id,
        deadline=deadline,
        metadata=metadata,
    )

    # ── 3. Obtain canonical gateway singleton ────────────────────────────────
    # get_model_gateway() returns the process-level singleton — never creates
    # a new gateway per request.
    gateway = await get_model_gateway()

    # ── 4. Call canonical ModelGateway.generate() ────────────────────────────
    try:
        response = await gateway.generate(model_request)
    except RequestDeadlineExceeded as exc:
        # Raised before the provider call when the deadline is already expired.
        logger.error("inference: deadline exceeded — %s", exc)
        return JSONResponse(
            status_code=504,
            content=InferenceError(
                code="DEADLINE_EXCEEDED",
                message="Inference deadline exceeded before provider call.",
                trace_id=body.trace_id,
            ).model_dump(),
        )
    except ModelUnavailable as exc:
        # Raised when circuit is open (re-raised as ModelUnavailable by gateway),
        # or when no eligible model is available after policy filtering.
        logger.error("inference: model unavailable — %s", exc)
        return JSONResponse(
            status_code=503,
            content=InferenceError(
                code="MODEL_UNAVAILABLE",
                message=str(exc),
                trace_id=body.trace_id,
            ).model_dump(),
        )
    except ModelGatewayError as exc:
        # All other gateway errors — provider failure, response parse error, etc.
        logger.error("inference: gateway error (%s) — %s", type(exc).__name__, exc)
        return JSONResponse(
            status_code=503,
            content=InferenceError(
                code="PROVIDER_FAILURE",
                message=str(exc),
                trace_id=body.trace_id,
            ).model_dump(),
        )

    # ── 5. Build safe route metadata ─────────────────────────────────────────
    # Retrieve the generation from the registry — the registry is the single
    # source of truth for which generation a model_id belongs to.
    cap = gateway._registry.get_by_id(response.model_id)
    generation = cap.generation if cap is not None else "unknown"
    from maiw_models.routing import PolicyFilter

    approved_family = generation in PolicyFilter.APPROVED_MODEL_GENERATIONS

    rd = response.route_decision
    route_meta = RouteMetadata(
        selected_model_id=response.model_id,
        selected_role=rd.selected_role,
        generation=generation,
        approved_family=approved_family,
        routing_rule=rd.routing_rule,
        fallback_used=rd.fallback_from is not None,
        candidate_count=len(rd.candidate_models),
    )

    latency = (time.monotonic() - t0) * 1000.0
    logger.info(
        "inference: ok model=%s role=%s approved=%s latency_ms=%.1f trace_id=%s",
        response.model_id,
        rd.selected_role,
        approved_family,
        latency,
        body.trace_id,
    )

    return InferenceResponse(
        content=response.content,
        model_id=response.model_id,
        finish_reason=response.finish_reason,
        latency_ms=response.latency_ms,
        route=route_meta,
        trace_id=body.trace_id,
        agent_task_id=body.agent_task_id,
        procedure_execution_id=body.procedure_execution_id,
        step_execution_id=body.step_execution_id,
    )


__all__ = [
    "router",
    "InferenceRequest",
    "InferenceResponse",
    "InferenceMessage",
    "InferenceError",
    "RouteMetadata",
]
