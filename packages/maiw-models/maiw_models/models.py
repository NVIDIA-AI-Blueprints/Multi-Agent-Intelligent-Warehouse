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
Pydantic v2 boundary models for ModelGateway.

Agents express intent through ModelRequest.
Agents receive normalized results through ModelResponse.
Neither leaks provider-specific structures.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from maiw_mcp.deadline import (
    RequestDeadline,
)  # noqa: F401 — needed for Pydantic resolution

# ── Enumerations ──────────────────────────────────────────────────────────────


class Modality(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    MULTIMODAL = "multimodal"


class ReasoningLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class LatencyClass(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CostClass(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DeploymentStatus(str, Enum):
    """
    Deployment availability of a model on the configured NIM infrastructure.

    DEPLOYED             — endpoint validated, completions confirmed working.
    SUPPORTED_BY_ARCH    — model ID configured; endpoint not yet validated in
                           this environment.
    NOT_CURRENTLY_DEPLOYED — no verified model ID is available for this role
                           in the current NIM catalog.
    LEGACY               — model is available but pre-dates the Nemotron 3
                           generation; retained for compatibility only.
    """

    DEPLOYED = "deployed"
    SUPPORTED_BY_ARCH = "supported_by_architecture"
    NOT_CURRENTLY_DEPLOYED = "not_currently_deployed"
    LEGACY = "legacy"


# ── Capability ────────────────────────────────────────────────────────────────


class ModelCapability(BaseModel):
    """
    Registry entry describing a single deployed model.

    Agents never read this directly — they submit ModelRequests and get
    ModelResponses.  The registry and router use this to make routing decisions.

    All capability flags are set only from verified endpoint testing or official
    NVIDIA documentation.  If a property has not been confirmed, it is left at
    its conservative default and noted in a comment.
    """

    model_id: str
    role: str  # lightning | nano | super | ultra | nano-omni

    # Provenance — generation label follows the official NVIDIA Nemotron naming.
    family: str = "nemotron"
    generation: str = "unknown"  # e.g. "nemotron-3", "nemotron-3.5", "legacy"
    provider: str = "nvidia-nim"

    # Deployment availability — verified by endpoint probe where possible.
    deployment_status: DeploymentStatus = DeploymentStatus.SUPPORTED_BY_ARCH

    # Capability flags — only mark True when confirmed by endpoint test or docs.
    modalities: set[str] = Field(default_factory=lambda: {"text"})
    tool_use: bool = False  # conservative default; override when confirmed
    structured_output: bool = False  # conservative default; override when confirmed
    reasoning_level: ReasoningLevel = ReasoningLevel.MEDIUM

    # Operational profile
    latency_class: LatencyClass = LatencyClass.MEDIUM
    cost_class: CostClass = CostClass.MEDIUM

    # Special roles
    teacher_judge: bool = False

    # Deployment
    enabled: bool = True
    # When set, overrides the global LLM_NIM_URL for this model.
    deployment_endpoint: str | None = None
    # When set, names the env var that holds the API key for this model.
    api_key_env_var: str | None = None

    # Context window in tokens.
    # None = not confirmed from documentation or endpoint introspection.
    context_window: int | None = None


# ── Request ───────────────────────────────────────────────────────────────────


class ModelRequest(BaseModel):
    """
    Agent-facing request object.

    Agents describe *what they need*, not *which model to use*.
    The gateway owns routing.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    task: str
    messages: list[dict[str, Any]]
    reasoning: ReasoningLevel = ReasoningLevel.MEDIUM
    risk_level: RiskLevel = RiskLevel.LOW
    modality: Modality = Modality.TEXT
    latency_budget_ms: int | None = None
    tools: list[str] = Field(default_factory=list)
    required_capabilities: set[str] = Field(default_factory=set)
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Pass-through generation overrides — use sparingly.
    temperature: float | None = None
    max_tokens: int | None = None
    stream: bool = False
    # Caller-supplied correlation ID.  When set, the gateway emits this value
    # in telemetry instead of generating its own, enabling end-to-end tracing
    # across State → Agent → Model → Proposal → Decision → Execution.
    trace_id: str | None = None
    # Parent request deadline — bounds the entire model path including retries.
    # None preserves legacy behaviour (NIMClient config.timeout applies per attempt).
    deadline: RequestDeadline | None = Field(default=None, exclude=True)


# ── Route Decision (embedded in response for observability) ───────────────────


class ModelRouteDecision(BaseModel):
    """
    Records exactly how and why a model was selected.

    Always surfaced in ModelResponse.  Telemetry reads this struct directly.

    Distinction between fields:
        requested_role   — the ideal role chosen by routing policy before fallbacks
        selected_role    — the role that actually served the request (may differ)
        routing_rule     — machine-readable name of the policy rule that triggered
        routing_reason   — human-readable summary of why requested_role was chosen
        fallback_from    — set when selected_role != requested_role (the skipped role)
        fallback_reason  — human-readable reason the preferred role was unavailable
    """

    selected_model_id: str
    selected_role: str
    requested_role: str  # ideal role before fallback
    routing_rule: str  # machine-readable: e.g. "medium_reasoning"
    routing_reason: str  # human-readable description of the routing rule
    fallback_from: str | None = None
    fallback_reason: str | None = None
    task: str
    requested_reasoning: ReasoningLevel
    requested_risk_level: RiskLevel


# ── Response ──────────────────────────────────────────────────────────────────


class ModelResponse(BaseModel):
    """
    Normalized response returned to agents.

    Provider-specific metadata is retained in raw_provider_metadata
    for diagnostics but must not be used by agent business logic.
    """

    content: str
    model_id: str
    model_family: str
    latency_ms: float
    finish_reason: str
    usage: dict[str, int] = Field(default_factory=dict)
    route_decision: ModelRouteDecision
    structured_output: Any | None = None
    raw_provider_metadata: dict[str, Any] = Field(default_factory=dict)
