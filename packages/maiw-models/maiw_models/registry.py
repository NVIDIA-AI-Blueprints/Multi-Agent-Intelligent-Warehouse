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
Nemotron Model Registry.

═══════════════════════════════════════════════════════════════════════════════
MODEL AUDIT — Phase 1C (endpoint-validated 2026-08-20)
Endpoint: https://integrate.api.nvidia.com/v1
═══════════════════════════════════════════════════════════════════════════════

DEPLOYED — confirmed by live endpoint probe, simple completion returned:

  LIGHTNING  nvidia/nemotron-3.5-lightning-30b-a3b    279ms   tool_use=YES
  NANO       nvidia/nemotron-3-nano-30b-a3b            364ms   tool_use=NO
  SUPER      nvidia/nemotron-3-super-120b-a12b         275ms   tool_use=NO
  ULTRA      nvidia/nemotron-3-ultra-550b-a55b       31407ms  tool_use=untested(cost)

  All four are MoE (Mixture-of-Experts) reasoning models.
  Model name suffix "a3b/a12b/a55b" = active parameter count in billions.

  JSON structured output (response_format: json_object): NOT confirmed for any
  model — all return extended thinking traces rather than pure JSON.
  Capabilities will be updated when official documentation or endpoint support
  is confirmed.

NOT_CURRENTLY_DEPLOYED — not found on integrate.api.nvidia.com as of 2026-08-20:

  NANO-OMNI  (no Nemotron 3 multimodal/VL model ID verified)
  Candidate IDs probed and returned 404:
    nvidia/nemotron-3-nano-omni-7b
    nvidia/nemotron-3-nano-vl
    nvidia/nemotron-nano-vl-3b-v1
  Set NEMOTRON_NANO_OMNI_MODEL to a verified VL model ID when available.

LEGACY — no longer available on integrate.api.nvidia.com as of 2026-08-20:

  nvidia/llama-3.3-nemotron-super-49b-v1.5  — HTTP 200 but content=None (endpoint broken)
  nvidia/llama-3.1-nemotron-nano-4b-v1.1    — HTTP 404
  nvidia/llama-3.1-nemotron-ultra-253b-v1   — HTTP 404
  nvidia/llama-nemotron-nano-vl-8b-v1       — HTTP 404

  These models must NOT be used as defaults for Nemotron 3 roles.
  They are retained as LEGACY_* constants below for documentation and
  compatibility tooling only.

═══════════════════════════════════════════════════════════════════════════════

All model identifiers are configuration-driven via environment variables.
DO NOT hard-code model strings in agent code.  Agents resolve capabilities
through the registry; the registry resolves concrete IDs from environment.
"""

from __future__ import annotations

import logging
import os

from .models import (
    CostClass,
    DeploymentStatus,
    LatencyClass,
    ModelCapability,
    ReasoningLevel,
)

logger = logging.getLogger(__name__)

# ── Environment variable names ─────────────────────────────────────────────────

_LIGHTNING_MODEL_ENV = "NEMOTRON_LIGHTNING_MODEL"
_NANO_MODEL_ENV = "NEMOTRON_NANO_MODEL"
_SUPER_MODEL_ENV = "NEMOTRON_SUPER_MODEL"
_ULTRA_MODEL_ENV = "NEMOTRON_ULTRA_MODEL"
_NANO_OMNI_MODEL_ENV = "NEMOTRON_NANO_OMNI_MODEL"

_LIGHTNING_ENABLED_ENV = "NEMOTRON_LIGHTNING_ENABLED"
_NANO_ENABLED_ENV = "NEMOTRON_NANO_ENABLED"
_SUPER_ENABLED_ENV = "NEMOTRON_SUPER_ENABLED"
_ULTRA_ENABLED_ENV = "NEMOTRON_ULTRA_ENABLED"
_NANO_OMNI_ENABLED_ENV = "NEMOTRON_NANO_OMNI_ENABLED"

# ── Current Nemotron 3 / 3.5 model IDs ────────────────────────────────────────
# Verified on integrate.api.nvidia.com/v1 on 2026-08-20.
# Override via env vars for self-hosted or alternate deployments.

_DEFAULTS: dict[str, str] = {
    _LIGHTNING_MODEL_ENV: "nvidia/nemotron-3.5-lightning-30b-a3b",  # Nemotron 3.5
    _NANO_MODEL_ENV: "nvidia/nemotron-3-nano-30b-a3b",  # Nemotron 3
    _SUPER_MODEL_ENV: "nvidia/nemotron-3-super-120b-a12b",  # Nemotron 3
    _ULTRA_MODEL_ENV: "nvidia/nemotron-3-ultra-550b-a55b",  # Nemotron 3
    # Nano Omni: no verified model available.
    # Operator MUST set NEMOTRON_NANO_OMNI_MODEL to a confirmed VL model ID.
    _NANO_OMNI_MODEL_ENV: "OPERATOR_MUST_CONFIGURE_NEMOTRON_NANO_OMNI_MODEL",
}

# ── Legacy model ID constants ──────────────────────────────────────────────────
# DO NOT use these as defaults for Nemotron 3 roles.
# Retained here for documentation, migration tooling, and audit trails.
# As of 2026-08-20, all of these are unavailable on integrate.api.nvidia.com/v1.

LEGACY_SUPER_LLAMA33 = "nvidia/llama-3.3-nemotron-super-49b-v1.5"
LEGACY_NANO_LLAMA31 = "nvidia/llama-3.1-nemotron-nano-4b-v1.1"
LEGACY_ULTRA_LLAMA31 = "nvidia/llama-3.1-nemotron-ultra-253b-v1"
LEGACY_NANO_VL = "nvidia/llama-nemotron-nano-vl-8b-v1"

# ── Enabled defaults ───────────────────────────────────────────────────────────

_ENABLED_DEFAULTS: dict[str, bool] = {
    _LIGHTNING_ENABLED_ENV: True,  # validated DEPLOYED; fast path now available
    _NANO_ENABLED_ENV: True,   # validated DEPLOYED; enabled by default (same tier as Lightning/Super)
    _SUPER_ENABLED_ENV: True,  # validated DEPLOYED; primary deployment
    _ULTRA_ENABLED_ENV: False,  # validated DEPLOYED but ~31s latency; operator opt-in
    _NANO_OMNI_ENABLED_ENV: False,  # NOT_CURRENTLY_DEPLOYED; requires operator model config
}

_NANO_OMNI_SENTINEL = "OPERATOR_MUST_CONFIGURE_NEMOTRON_NANO_OMNI_MODEL"


def _getenv_bool(key: str, default: bool) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class ModelRegistry:
    """
    Central registry of Nemotron model capabilities.

    Populated at construction time from environment variables.
    Call reload() to pick up runtime changes (e.g. after hot-reload in tests).

    Capability flags reflect endpoint-validated results from 2026-08-20.
    Update after each new NIM catalog release.
    """

    def __init__(self) -> None:
        self._capabilities: dict[str, ModelCapability] = {}
        self._role_index: dict[str, str] = {}  # role → model_id
        self._build()

    def _build(self) -> None:
        nano_omni_model = os.getenv(
            _NANO_OMNI_MODEL_ENV, _DEFAULTS[_NANO_OMNI_MODEL_ENV]
        )
        nano_omni_enabled = _getenv_bool(
            _NANO_OMNI_ENABLED_ENV, _ENABLED_DEFAULTS[_NANO_OMNI_ENABLED_ENV]
        )

        if nano_omni_enabled and nano_omni_model == _NANO_OMNI_SENTINEL:
            logger.error(
                "ModelRegistry: Nano Omni role is enabled but NEMOTRON_NANO_OMNI_MODEL "
                "is not configured.  No verified Nemotron-3 Nano Omni model ID is "
                "currently available on NVIDIA NIM.  Set NEMOTRON_NANO_OMNI_MODEL to a "
                "confirmed VL/multimodal model ID.  Nano Omni will be DISABLED."
            )
            nano_omni_enabled = False

        entries = [
            ModelCapability(
                model_id=os.getenv(
                    _LIGHTNING_MODEL_ENV, _DEFAULTS[_LIGHTNING_MODEL_ENV]
                ),
                role="lightning",
                family="nemotron",
                generation="nemotron-3.5",
                provider="nvidia-nim",
                deployment_status=DeploymentStatus.DEPLOYED,
                modalities={"text"},
                # Endpoint-validated 2026-08-20: forced tool_choice=function succeeded.
                tool_use=True,
                # JSON mode returned thinking trace, not pure JSON — not confirmed.
                structured_output=False,
                reasoning_level=ReasoningLevel.LOW,
                latency_class=LatencyClass.LOW,
                cost_class=CostClass.LOW,
                teacher_judge=False,
                context_window=None,  # not confirmed from documentation
                enabled=_getenv_bool(
                    _LIGHTNING_ENABLED_ENV, _ENABLED_DEFAULTS[_LIGHTNING_ENABLED_ENV]
                ),
            ),
            ModelCapability(
                model_id=os.getenv(_NANO_MODEL_ENV, _DEFAULTS[_NANO_MODEL_ENV]),
                role="nano",
                family="nemotron",
                generation="nemotron-3",
                provider="nvidia-nim",
                deployment_status=DeploymentStatus.DEPLOYED,
                modalities={"text"},
                # Endpoint-validated 2026-08-20: forced tool_choice returned text, not tool call.
                tool_use=False,
                structured_output=False,
                reasoning_level=ReasoningLevel.MEDIUM,
                latency_class=LatencyClass.LOW,
                cost_class=CostClass.LOW,
                teacher_judge=False,
                context_window=None,
                enabled=_getenv_bool(
                    _NANO_ENABLED_ENV, _ENABLED_DEFAULTS[_NANO_ENABLED_ENV]
                ),
            ),
            ModelCapability(
                model_id=os.getenv(_SUPER_MODEL_ENV, _DEFAULTS[_SUPER_MODEL_ENV]),
                role="super",
                family="nemotron",
                generation="nemotron-3",
                provider="nvidia-nim",
                deployment_status=DeploymentStatus.DEPLOYED,
                modalities={"text"},
                # Endpoint-validated 2026-08-20: forced tool_choice returned text, not tool call.
                tool_use=False,
                structured_output=False,
                reasoning_level=ReasoningLevel.HIGH,
                latency_class=LatencyClass.MEDIUM,
                cost_class=CostClass.MEDIUM,
                teacher_judge=False,
                context_window=None,
                enabled=_getenv_bool(
                    _SUPER_ENABLED_ENV, _ENABLED_DEFAULTS[_SUPER_ENABLED_ENV]
                ),
            ),
            ModelCapability(
                model_id=os.getenv(_ULTRA_MODEL_ENV, _DEFAULTS[_ULTRA_MODEL_ENV]),
                role="ultra",
                family="nemotron",
                generation="nemotron-3",
                provider="nvidia-nim",
                deployment_status=DeploymentStatus.DEPLOYED,
                modalities={"text"},
                # tool_use: not tested due to ~31s latency cost; assume same as Super family.
                tool_use=False,
                structured_output=False,
                reasoning_level=ReasoningLevel.HIGH,
                latency_class=LatencyClass.HIGH,
                cost_class=CostClass.HIGH,
                teacher_judge=True,
                context_window=None,
                enabled=_getenv_bool(
                    _ULTRA_ENABLED_ENV, _ENABLED_DEFAULTS[_ULTRA_ENABLED_ENV]
                ),
            ),
            ModelCapability(
                model_id=nano_omni_model,
                role="nano-omni",
                family="nemotron",
                generation="unknown",
                provider="nvidia-nim",
                # No verified Nemotron-3 Nano Omni model ID found on NIM as of 2026-08-20.
                deployment_status=DeploymentStatus.NOT_CURRENTLY_DEPLOYED,
                modalities={"text", "image", "video", "audio"},
                tool_use=False,
                structured_output=False,
                reasoning_level=ReasoningLevel.MEDIUM,
                latency_class=LatencyClass.LOW,
                cost_class=CostClass.MEDIUM,
                teacher_judge=False,
                context_window=None,
                enabled=nano_omni_enabled,
            ),
        ]

        self._capabilities.clear()
        self._role_index.clear()
        for cap in entries:
            self._capabilities[cap.model_id] = cap
            self._role_index[cap.role] = cap.model_id
            status = "enabled" if cap.enabled else "disabled"
            logger.info(
                "ModelRegistry: role=%s model=%s generation=%s deployment=%s status=%s",
                cap.role,
                cap.model_id,
                cap.generation,
                cap.deployment_status.value,
                status,
            )

    def reload(self) -> None:
        """Re-read environment and rebuild the registry (useful in tests)."""
        self._build()

    def get_by_id(self, model_id: str) -> ModelCapability | None:
        return self._capabilities.get(model_id)

    def get_by_role(self, role: str) -> ModelCapability | None:
        model_id = self._role_index.get(role)
        if model_id is None:
            return None
        return self._capabilities.get(model_id)

    def get_enabled_by_role(self, role: str) -> ModelCapability | None:
        cap = self.get_by_role(role)
        if cap and cap.enabled:
            return cap
        return None

    def all_enabled(self) -> list[ModelCapability]:
        return [c for c in self._capabilities.values() if c.enabled]

    def all_roles(self) -> list[str]:
        return list(self._role_index.keys())
