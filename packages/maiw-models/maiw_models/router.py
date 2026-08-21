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
Deterministic model routing policy.

The router selects a Nemotron model role given a ModelRequest.
It does not perform ML-based routing — policy is explicit and auditable.

Routing decisions are always recorded in the ModelRouteDecision and
surfaced in ModelResponse so that every selection is observable.

Routing rules (priority order):
  1. multimodal_input     — non-TEXT modality → nano-omni
  2. judge_task           — task name contains judge/eval keywords → ultra
  3. critical_risk        — risk_level=CRITICAL → super (minimum)
  4. high_reasoning       — reasoning=HIGH → super
  5. medium_reasoning     — reasoning=MEDIUM → nano
  6. low_reasoning        — reasoning=LOW → lightning

Fallback chain (when preferred role is disabled):
  lightning → nano → super
  nano → super
  super → (none; ModelUnavailable raised)
  ultra → super
  nano-omni → super (degrades to text-only)

Telemetry fields:
  requested_role  — ideal role from routing policy before fallbacks
  selected_role   — role that actually serves the request
  routing_rule    — machine-readable rule name (e.g. "medium_reasoning")
  routing_reason  — human-readable description of why requested_role was chosen
  fallback_from   — set when selected_role != requested_role
  fallback_reason — why the preferred role was unavailable
"""

from __future__ import annotations

import logging

from .errors import ModelUnavailable
from .models import (
    ModelCapability,
    ModelRequest,
    ModelRouteDecision,
    Modality,
    ReasoningLevel,
    RiskLevel,
)
from .registry import ModelRegistry

logger = logging.getLogger(__name__)

# Tasks whose names signal judge / teacher / offline-eval workloads
_JUDGE_TASK_KEYWORDS = frozenset({"judge", "teacher", "eval", "offline", "score", "grade"})

# Fallback chain: role → ordered list of roles to try if preferred is unavailable
_FALLBACK_CHAIN: dict[str, list[str]] = {
    "lightning": ["nano", "super"],
    "nano": ["super"],
    "super": [],
    "ultra": ["super"],
    "nano-omni": ["super"],
}


class ModelRouter:
    """
    Deterministic model router.

    Accepts a ModelRequest and a populated ModelRegistry.
    Returns a ModelRouteDecision (selected model + reason) or raises ModelUnavailable.
    """

    def __init__(self, registry: ModelRegistry) -> None:
        self._registry = registry

    def route(self, request: ModelRequest) -> ModelRouteDecision:
        """Select a model and record the full routing decision."""
        preferred_role, routing_rule, routing_reason = self._select_role(request)
        capability, final_role, fallback_from, fallback_reason = self._resolve_with_fallback(
            preferred_role
        )

        decision = ModelRouteDecision(
            selected_model_id=capability.model_id,
            selected_role=final_role,
            requested_role=preferred_role,
            routing_rule=routing_rule,
            routing_reason=routing_reason,
            fallback_from=fallback_from,
            fallback_reason=fallback_reason,
            task=request.task,
            requested_reasoning=request.reasoning,
            requested_risk_level=request.risk_level,
        )

        logger.info(
            "ModelRouter: task=%s requested_role=%s selected_role=%s "
            "model=%s rule=%s fallback_from=%s",
            request.task,
            preferred_role,
            final_role,
            capability.model_id,
            routing_rule,
            fallback_from,
        )
        return decision

    # ── Private helpers ────────────────────────────────────────────────────────

    def _select_role(self, request: ModelRequest) -> tuple[str, str, str]:
        """
        Return (preferred_role, routing_rule, human_readable_reason).

        routing_rule is a machine-readable slug used in telemetry.
        routing_reason is a human-readable string explaining the preferred role.
        """
        # 1. Multimodal input → Nano Omni
        if request.modality != Modality.TEXT:
            return (
                "nano-omni",
                "multimodal_input",
                f"modality={request.modality.value} requires multimodal model (Nano Omni)",
            )

        # 2. Judge / teacher / offline-eval task → Ultra
        task_lower = request.task.lower()
        if any(kw in task_lower for kw in _JUDGE_TASK_KEYWORDS):
            return (
                "ultra",
                "judge_task",
                f"task '{request.task}' requires teacher/judge capability (Ultra)",
            )

        # 3. Critical-risk action → Super minimum (model alone does not authorize)
        if request.risk_level == RiskLevel.CRITICAL:
            return (
                "super",
                "critical_risk",
                "risk_level=CRITICAL requires high-capability model (Super minimum)",
            )

        # 4. High reasoning → Super
        if request.reasoning == ReasoningLevel.HIGH:
            return (
                "super",
                "high_reasoning",
                "reasoning=HIGH requires Super",
            )

        # 5. Medium reasoning → Nano
        if request.reasoning == ReasoningLevel.MEDIUM:
            return (
                "nano",
                "medium_reasoning",
                "reasoning=MEDIUM prefers Nano",
            )

        # 6. Low reasoning → Lightning
        return (
            "lightning",
            "low_reasoning",
            "reasoning=LOW prefers Lightning",
        )

    def _resolve_with_fallback(
        self, preferred_role: str
    ) -> tuple[ModelCapability, str, str | None, str | None]:
        """
        Walk the fallback chain until an enabled model is found.

        Returns (capability, final_role, fallback_from, fallback_reason).
        fallback_from is set only when the final role differs from preferred_role.
        Raises ModelUnavailable when the chain is exhausted.
        """
        chain = [preferred_role] + _FALLBACK_CHAIN.get(preferred_role, [])

        for role in chain:
            cap = self._registry.get_enabled_by_role(role)
            if cap is not None:
                if role != preferred_role:
                    fallback_from = preferred_role
                    fallback_reason = (
                        f"role={preferred_role} is disabled; escalated to {role}"
                    )
                    logger.warning(
                        "ModelRouter: fallback triggered preferred=%s selected=%s reason=%s",
                        preferred_role,
                        role,
                        fallback_reason,
                    )
                    return cap, role, fallback_from, fallback_reason
                return cap, role, None, None

        raise ModelUnavailable(
            f"No enabled model available. Tried roles: {chain}. "
            f"Enable at least one Nemotron model via environment variables.",
        )
