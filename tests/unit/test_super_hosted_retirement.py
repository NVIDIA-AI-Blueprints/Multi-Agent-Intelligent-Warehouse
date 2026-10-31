# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.1.0 — hosted Nemotron 3 Super retired (2026-10-19, HTTP 404).

Default routing with Super and Nano disabled and Ultra enabled, at the
ModelGateway level with a recording fake provider:

  LOW               → Lightning
  MEDIUM            → Lightning (Nano and Super disabled)
  HIGH / CRITICAL   → Ultra, never below a high-capability role
  self-hosted Super → the pre-retirement routing is unchanged
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from maiw_models import (
    ModelGateway,
    ModelRegistry,
    ModelRequest,
    ModelUnavailable,
    ReasoningLevel,
    RiskLevel,
)
from maiw_models.providers.nim_client import LLMResponse
from maiw_models.router import ModelRouter

SUPER = "nvidia/nemotron-3-super-120b-a12b"
ULTRA = "nvidia/nemotron-3-ultra-550b-a55b"
LIGHTNING = "nvidia/nemotron-3.5-lightning-30b-a3b"
NANO = "nvidia/nemotron-3-nano-30b-a3b"


class RecordingProvider:
    """Records every dispatched model ID and answers as that model."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def call(self, *, model_id, request, capability):
        self.calls.append(model_id)
        return LLMResponse(
            content="ok",
            usage={},
            model=model_id,
            finish_reason="stop",
            provider_model=model_id,
        )


def _gateway(
    env: dict[str, str], provider: RecordingProvider
) -> tuple[ModelGateway, ModelRegistry]:
    """Gateway over the shipped defaults (no NEMOTRON_* in the environment) + env."""
    clean = {k: v for k, v in os.environ.items() if not k.startswith("NEMOTRON_")}
    clean.update(env)
    with patch.dict(os.environ, clean, clear=True):
        registry = ModelRegistry()
    gw = ModelGateway(
        provider=provider, registry=registry, router=ModelRouter(registry)
    )
    return gw, registry


def _req(reasoning=ReasoningLevel.MEDIUM, risk=RiskLevel.LOW, task="t"):
    return ModelRequest(
        task=task,
        messages=[{"role": "user", "content": "x"}],
        reasoning=reasoning,
        risk_level=risk,
    )


# ── defaults ─────────────────────────────────────────────────────────────────


def test_default_enabled_roles():
    _, registry = _gateway({}, RecordingProvider())
    enabled = {c.role: c.model_id for c in registry.all_enabled()}
    assert enabled == {"lightning": LIGHTNING, "ultra": ULTRA}


async def test_low_reasoning_uses_lightning():
    provider = RecordingProvider()
    gw, _ = _gateway({}, provider)
    resp = await gw.generate(_req(ReasoningLevel.LOW))
    assert provider.calls == [LIGHTNING]
    assert resp.route_decision.selected_role == "lightning"
    assert resp.route_decision.fallback_from is None
    assert resp.identity_verified is True


async def test_medium_reasoning_falls_back_to_lightning():
    provider = RecordingProvider()
    gw, _ = _gateway({}, provider)
    resp = await gw.generate(_req(ReasoningLevel.MEDIUM))
    assert provider.calls == [LIGHTNING]
    decision = resp.route_decision
    assert decision.requested_role == "nano"
    assert decision.selected_role == "lightning"
    assert decision.fallback_from == "nano"
    assert resp.identity_verified is True


async def test_high_reasoning_falls_back_to_ultra():
    provider = RecordingProvider()
    gw, _ = _gateway({}, provider)
    resp = await gw.generate(_req(ReasoningLevel.HIGH))
    assert provider.calls == [ULTRA]
    decision = resp.route_decision
    assert decision.requested_role == "super"
    assert decision.selected_role == "ultra"
    assert decision.fallback_from == "super"
    assert resp.generation == "nemotron-3"
    assert resp.identity_verified is True


async def test_critical_risk_falls_back_to_ultra():
    provider = RecordingProvider()
    gw, _ = _gateway({}, provider)
    resp = await gw.generate(_req(ReasoningLevel.MEDIUM, RiskLevel.CRITICAL))
    assert provider.calls == [ULTRA]
    assert resp.route_decision.routing_rule == "critical_risk"
    assert resp.route_decision.selected_role == "ultra"


@pytest.mark.parametrize(
    "reasoning,risk",
    [
        (ReasoningLevel.HIGH, RiskLevel.LOW),
        (ReasoningLevel.MEDIUM, RiskLevel.CRITICAL),
    ],
)
async def test_high_capability_requests_never_downgrade_to_lightning(reasoning, risk):
    """With Super and Ultra both off, HIGH/CRITICAL fail closed — no provider call."""
    provider = RecordingProvider()
    gw, _ = _gateway({"NEMOTRON_ULTRA_ENABLED": "false"}, provider)
    with pytest.raises(ModelUnavailable):
        await gw.generate(_req(reasoning, risk))
    assert provider.calls == []


# ── self-hosted Super keeps the pre-retirement routing ───────────────────────


@pytest.mark.parametrize(
    "reasoning,risk",
    [
        (ReasoningLevel.HIGH, RiskLevel.LOW),
        (ReasoningLevel.MEDIUM, RiskLevel.LOW),
        (ReasoningLevel.MEDIUM, RiskLevel.CRITICAL),
    ],
)
async def test_super_enabled_serves_high_medium_and_critical(reasoning, risk):
    provider = RecordingProvider()
    gw, _ = _gateway({"NEMOTRON_SUPER_ENABLED": "true"}, provider)
    resp = await gw.generate(_req(reasoning, risk))
    assert provider.calls == [SUPER]
    assert resp.route_decision.selected_role == "super"


async def test_judge_task_still_prefers_ultra():
    provider = RecordingProvider()
    gw, _ = _gateway({}, provider)
    resp = await gw.generate(_req(ReasoningLevel.HIGH, task="judge_answer"))
    assert provider.calls == [ULTRA]
    assert resp.route_decision.routing_rule == "judge_task"
    assert resp.route_decision.fallback_from is None
