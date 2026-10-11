# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Document pipeline → canonical ModelGateway seam (v2.0.1, audit P1-05).

Every model inference made by the document pipeline goes through exactly this
function:

    document stage → ModelRequest → ModelGateway → PolicyFilter → ModelRouter
                   → NIMProvider (provider credentials stay in the gateway)

There is no provider SDK, no provider URL, no API key and no model id in the
document pipeline. The stage states what it needs — a modality (``TEXT`` or
``IMAGE``) and a reasoning level — and the canonical PolicyFilter decides which
approved Nemotron 3 / 3.5 model (if any) may serve it.

Failure is typed and final. ``DocumentInferenceUnavailable`` is raised for:

    MODEL_UNAVAILABLE   no approved model satisfies the request (e.g. IMAGE
                        modality while no approved multimodal Nemotron model is
                        enabled), or the gateway circuit is open
    PROVIDER_FAILURE    provider error, timeout, missing/invalid credential
    DEADLINE_EXCEEDED   the stage deadline expired before the provider call
    MALFORMED_RESPONSE  the model returned no content / not the required JSON

There is no mock, canned, cached-substitute or alternative-family fallback: a
document whose inference cannot be served FAILS with one of these codes. In
particular a provider or key failure can never become a synthetic ``APPROVE``.
The approved-family policy is not widened to obtain vision support.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from maiw_models import (
    Modality,
    ModelGatewayError,
    ModelRequest,
    ModelUnavailable,
    ReasoningLevel,
    RiskLevel,
    get_model_gateway,
)
from maiw_mcp.deadline import RequestDeadline, RequestDeadlineExceeded

logger = logging.getLogger(__name__)

MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
PROVIDER_FAILURE = "PROVIDER_FAILURE"
DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
MALFORMED_RESPONSE = "MALFORMED_RESPONSE"


class DocumentInferenceUnavailable(RuntimeError):
    """A document-pipeline inference could not be served. Never retried into a mock."""

    def __init__(self, code: str, message: str, *, stage: str, modality: str) -> None:
        self.code = code
        self.stage = stage
        self.modality = modality
        super().__init__(f"[{code}] document stage {stage!r} ({modality}): {message}")


async def generate_for_document(
    *,
    stage: str,
    messages: list[dict[str, Any]],
    modality: Modality = Modality.TEXT,
    reasoning: ReasoningLevel = ReasoningLevel.MEDIUM,
    max_tokens: int = 2000,
    temperature: float = 0.1,
    timeout_s: float | None = None,
    trace_id: str | None = None,
) -> Any:
    """
    Run one document-stage inference through the canonical ModelGateway.

    Returns the ``ModelResponse`` (``content``, ``model_id``,
    ``route_decision``). Raises ``DocumentInferenceUnavailable`` on any failure.
    """
    request = ModelRequest(
        task=f"document.{stage}",
        messages=messages,
        reasoning=reasoning,
        risk_level=RiskLevel.LOW,
        modality=modality,
        max_tokens=max_tokens,
        temperature=temperature,
        trace_id=trace_id,
        deadline=(
            RequestDeadline.from_timeout(seconds=timeout_s) if timeout_s else None
        ),
        metadata={"surface": "document_pipeline", "stage": stage},
    )

    gateway = await get_model_gateway()
    try:
        response = await gateway.generate(request)
    except RequestDeadlineExceeded as exc:
        raise DocumentInferenceUnavailable(
            DEADLINE_EXCEEDED, str(exc), stage=stage, modality=modality.value
        ) from exc
    except ModelUnavailable as exc:
        raise DocumentInferenceUnavailable(
            MODEL_UNAVAILABLE, str(exc), stage=stage, modality=modality.value
        ) from exc
    except ModelGatewayError as exc:
        raise DocumentInferenceUnavailable(
            PROVIDER_FAILURE, str(exc), stage=stage, modality=modality.value
        ) from exc
    except Exception as exc:  # noqa: BLE001 — any other failure is still a failure
        raise DocumentInferenceUnavailable(
            PROVIDER_FAILURE,
            f"{type(exc).__name__}: {exc}",
            stage=stage,
            modality=modality.value,
        ) from exc

    content = getattr(response, "content", None)
    if not isinstance(content, str) or not content.strip():
        raise DocumentInferenceUnavailable(
            MALFORMED_RESPONSE,
            "model returned empty content",
            stage=stage,
            modality=modality.value,
        )
    logger.info(
        "document inference: stage=%s modality=%s model=%s",
        stage,
        modality.value,
        getattr(response, "model_id", "?"),
    )
    return response


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_json_object(content: str, *, stage: str, modality: str = "text") -> dict:
    """
    Parse a model reply that must be one JSON object (optionally fenced).

    Raises ``DocumentInferenceUnavailable(MALFORMED_RESPONSE)`` otherwise — a
    reply that is not the requested structure is never guessed at.
    """
    text = _FENCE.sub("", (content or "").strip()).strip()
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        start, end = text.find("{"), text.rfind("}")
        value = None
        if 0 <= start < end:
            try:
                value = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                value = None
    if not isinstance(value, dict):
        raise DocumentInferenceUnavailable(
            MALFORMED_RESPONSE,
            "model reply is not a JSON object",
            stage=stage,
            modality=modality,
        )
    return value


async def route_provenance(response: Any) -> dict[str, Any]:
    """Safe provenance for stored results: model id, role, registry generation."""
    rd = getattr(response, "route_decision", None)
    model_id = getattr(response, "model_id", None)
    # v2.0.1 round 2: the gateway stamps the generation bound to the approved
    # physical model it dispatched (DeploymentResolver).
    generation = getattr(response, "generation", None)
    if generation is None:
        try:
            gateway = await get_model_gateway()
            generation = gateway.registry.resolver.generation_for(model_id or "")
        except Exception:  # noqa: BLE001 — provenance is best-effort metadata
            generation = None
    return {
        "model_id": model_id,
        "selected_role": getattr(rd, "selected_role", None),
        "generation": generation,
        "routing_rule": getattr(rd, "routing_rule", None),
        "via": "maiw_models.ModelGateway",
    }


__all__ = [
    "DocumentInferenceUnavailable",
    "MODEL_UNAVAILABLE",
    "PROVIDER_FAILURE",
    "DEADLINE_EXCEEDED",
    "MALFORMED_RESPONSE",
    "generate_for_document",
    "parse_json_object",
    "route_provenance",
]
