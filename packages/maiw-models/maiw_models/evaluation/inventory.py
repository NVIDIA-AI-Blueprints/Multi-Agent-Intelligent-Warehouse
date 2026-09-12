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
Phase 18C: Candidate model inventory.

Builds the actual benchmark candidate matrix from the live ModelRegistry and
PolicyFilter.  Does NOT hardcode model IDs or benchmark candidates — all data
comes from registry configuration (environment variables).

Usage:
    from maiw_models.evaluation.inventory import build_candidate_inventory

    inventory = build_candidate_inventory(registry, deployment_mode, request)
    for info in inventory:
        print(info.model_id, info.role, info.enabled, info.available)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models import DeploymentMode, DeploymentStatus, ModelCapability, ModelRequest
from ..registry import ModelRegistry
from ..routing import PolicyFilter

# ── Role metadata ─────────────────────────────────────────────────────────────

_ROLE_LOGICAL_NAMES: dict[str, str] = {
    "lightning": "Nemotron Lightning (fast path)",
    "nano": "Nemotron Nano (standard reasoning)",
    "super": "Nemotron Super (high-capability)",
    "ultra": "Nemotron Ultra (teacher/judge)",
    "nano-omni": "Nemotron Nano Omni (multimodal)",
}

_ROLE_REASONING_SUPPORT: dict[str, str] = {
    "lightning": "low",
    "nano": "medium",
    "super": "high",
    "ultra": "high (teacher/judge)",
    "nano-omni": "medium (multimodal)",
}

_ROLE_RISK_SUITABILITY: dict[str, list[str]] = {
    "lightning": ["low", "medium"],
    "nano": ["low", "medium"],
    "super": ["low", "medium", "high", "critical"],
    "ultra": ["low", "medium", "high", "critical"],
    "nano-omni": ["low", "medium"],
}


# ── Candidate info ────────────────────────────────────────────────────────────


@dataclass
class CandidateModelInfo:
    """
    Per-model inventory entry for the benchmark candidate matrix.

    Built from ModelRegistry at benchmark time — not hardcoded.
    All fields reflect current registry state (environment variables).
    """

    model_id: str
    role: str
    logical_role: str  # human-readable role description
    generation: str  # e.g. "nemotron-3", "nemotron-3.5"
    reasoning_support: str  # "low" | "medium" | "high" | "high (teacher/judge)"
    risk_suitability: list[str]  # risk levels this model can serve
    deployment_modes: list[str]  # supported deployment mode values
    provider: str
    enabled: bool
    available: bool  # True when deployment_status == DEPLOYED
    deployment_status: str  # raw deployment status value
    latency_class: str
    cost_class: str
    tool_use: bool
    structured_output: bool
    teacher_judge: bool
    context_window: int | None

    def to_dict(self) -> dict[str, Any]:
        """Serialise to JSON-compatible dict."""
        return {
            "model_id": self.model_id,
            "role": self.role,
            "logical_role": self.logical_role,
            "generation": self.generation,
            "reasoning_support": self.reasoning_support,
            "risk_suitability": self.risk_suitability,
            "deployment_modes": self.deployment_modes,
            "provider": self.provider,
            "enabled": self.enabled,
            "available": self.available,
            "deployment_status": self.deployment_status,
            "latency_class": self.latency_class,
            "cost_class": self.cost_class,
            "tool_use": self.tool_use,
            "structured_output": self.structured_output,
            "teacher_judge": self.teacher_judge,
            "context_window": self.context_window,
        }


# ── Inventory builder ─────────────────────────────────────────────────────────


def build_candidate_inventory(
    registry: ModelRegistry,
    deployment_mode: DeploymentMode = DeploymentMode.NVIDIA_HOSTED,
    request: ModelRequest | None = None,
) -> list[CandidateModelInfo]:
    """
    Build the full candidate model inventory from the live registry.

    When request is provided, the 'eligible_for_request' field (not stored
    in CandidateModelInfo but computed separately) reflects PolicyFilter
    eligibility for that specific request.

    Args:
        registry:        ModelRegistry instance (reflects current env vars).
        deployment_mode: Deployment context for provider compatibility check.
        request:         Optional request to check per-model policy eligibility.

    Returns:
        List of CandidateModelInfo, one per registered model, in registry order.
        Includes disabled and unavailable models so the report shows the full picture.
    """
    policy_filter = PolicyFilter(registry)
    eligible_ids: set[str] = set()
    if request is not None:
        eligible_ids = set(policy_filter.candidate_model_ids(request, deployment_mode))

    inventory: list[CandidateModelInfo] = []
    for cap in registry._capabilities.values():
        role = cap.role
        info = CandidateModelInfo(
            model_id=cap.model_id,
            role=role,
            logical_role=_ROLE_LOGICAL_NAMES.get(role, role),
            generation=cap.generation,
            reasoning_support=_ROLE_REASONING_SUPPORT.get(role, "unknown"),
            risk_suitability=_ROLE_RISK_SUITABILITY.get(role, []),
            deployment_modes=_deployment_modes_for_provider(cap.provider),
            provider=cap.provider,
            enabled=cap.enabled,
            available=(cap.deployment_status == DeploymentStatus.DEPLOYED),
            deployment_status=cap.deployment_status.value,
            latency_class=cap.latency_class.value,
            cost_class=cap.cost_class.value,
            tool_use=cap.tool_use,
            structured_output=cap.structured_output,
            teacher_judge=cap.teacher_judge,
            context_window=cap.context_window,
        )
        inventory.append(info)

    return inventory


def build_benchmark_candidates(
    registry: ModelRegistry,
    request: ModelRequest,
    deployment_mode: DeploymentMode = DeploymentMode.NVIDIA_HOSTED,
) -> list[str]:
    """
    Return model_ids that are eligible benchmark candidates for a given request.

    These are the models the benchmark runner will call.  Only enabled, policy-
    compliant models are included.  Local NIM is skipped if not configured.
    """
    policy_filter = PolicyFilter(registry)
    return policy_filter.candidate_model_ids(request, deployment_mode)


def _deployment_modes_for_provider(provider: str) -> list[str]:
    """Return deployment mode values that support this provider."""
    if provider == "nvidia-nim":
        return [
            DeploymentMode.NVIDIA_HOSTED.value,
            DeploymentMode.LOCAL_NIM.value,
            DeploymentMode.ENTERPRISE.value,
            DeploymentMode.OPENAI_COMPATIBLE.value,
        ]
    return []
