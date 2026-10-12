# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.0.1 round 2 — DeploymentResolver / approved physical deployment table
(NEW-P1-01) at the ModelGateway level, with a recording fake provider.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from maiw_models import (
    APPROVED_DEPLOYMENTS,
    APPROVED_MODEL_GENERATIONS,
    ApprovedDeployment,
    DeploymentResolver,
    ModelGateway,
    ModelIdentityMismatch,
    ModelIdentityUnverifiable,
    ModelPolicyViolation,
    ModelRegistry,
    ModelRequest,
    PolicyFilter,
    ReasoningLevel,
    default_resolver,
)
from maiw_models.providers.nim_client import LLMResponse
from maiw_models.router import ModelRouter

SUPER = "nvidia/nemotron-3-super-120b-a12b"
LIGHTNING = "nvidia/nemotron-3.5-lightning-30b-a3b"


class RecordingProvider:
    """Records every dispatched model ID; answers as ``answer_as`` or echoes."""

    def __init__(self, answer_as: str | None = None) -> None:
        self.calls: list[str] = []
        self.answer_as = answer_as

    async def call(self, *, model_id, request, capability):
        self.calls.append(model_id)
        reported = self.answer_as if self.answer_as is not None else model_id
        return LLMResponse(
            content="ok",
            usage={},
            model=reported,
            finish_reason="stop",
            provider_model=reported,
        )


def _gateway(env: dict[str, str], provider: RecordingProvider) -> ModelGateway:
    clean = {k: v for k, v in os.environ.items() if not k.startswith("NEMOTRON_")}
    clean.update(env)
    with patch.dict(os.environ, clean, clear=True):
        registry = ModelRegistry()
    return ModelGateway(
        provider=provider, registry=registry, router=ModelRouter(registry)
    )


def _req(reasoning=ReasoningLevel.HIGH, task="t"):
    return ModelRequest(
        task=task, messages=[{"role": "user", "content": "x"}], reasoning=reasoning
    )


# ── the table ────────────────────────────────────────────────────────────────


def test_approved_family_is_not_widened():
    assert APPROVED_MODEL_GENERATIONS == frozenset({"nemotron-3", "nemotron-3.5"})
    assert PolicyFilter.APPROVED_MODEL_GENERATIONS == APPROVED_MODEL_GENERATIONS
    for entry in APPROVED_DEPLOYMENTS:
        assert entry.generation in APPROVED_MODEL_GENERATIONS


def test_table_binds_physical_id_to_generation_and_role():
    by_id = {e.model_id: e for e in APPROVED_DEPLOYMENTS}
    assert by_id[SUPER].role == "super" and by_id[SUPER].generation == "nemotron-3"
    assert by_id[LIGHTNING].role == "lightning"
    assert by_id[LIGHTNING].generation == "nemotron-3.5"
    # no multimodal model is approved → vision fails closed
    assert not [e for e in APPROVED_DEPLOYMENTS if e.role == "nano-omni"]


def test_resolver_cannot_be_built_with_unapproved_generation():
    with pytest.raises(ValueError):
        DeploymentResolver(
            [
                ApprovedDeployment(
                    role="super", model_id="meta/llama-x", generation="llama-3"
                )
            ]
        )


def test_default_resolver_is_the_canonical_table():
    assert default_resolver().approved_model_ids() == frozenset(
        e.model_id for e in APPROVED_DEPLOYMENTS
    )


@pytest.mark.parametrize(
    "role,model_id,reason",
    [
        ("super", "example-org/unapproved-model-x", "UNAPPROVED_MODEL_ID"),
        ("super", LIGHTNING, "ROLE_MISMATCH"),
        ("lightning", SUPER, "ROLE_MISMATCH"),
        ("super", SUPER.upper(), "UNAPPROVED_MODEL_ID"),
        ("super", "", "EMPTY_MODEL_ID"),
        (
            "nano-omni",
            "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
            "UNAPPROVED_MODEL_ID",
        ),
    ],
)
def test_resolver_rejects(role, model_id, reason):
    with pytest.raises(ModelPolicyViolation) as exc:
        default_resolver().resolve(role, model_id)
    assert exc.value.reason == reason


def test_resolver_response_identity():
    resolved = default_resolver().resolve("super", SUPER)
    assert DeploymentResolver.verify_response_identity(resolved, SUPER) is True
    # v2.0.1 round 3: no usable identity fails closed (was: False / accepted)
    for missing in (None, "", "   "):
        with pytest.raises(ModelIdentityUnverifiable) as info:
            DeploymentResolver.verify_response_identity(resolved, missing)
        assert info.value.reason == "MISSING"
    for malformed in (123, ["x"], {"id": SUPER}):
        with pytest.raises(ModelIdentityUnverifiable) as info:
            DeploymentResolver.verify_response_identity(resolved, malformed)
        assert info.value.reason == "MALFORMED"
    for other in ("x/y", SUPER.upper(), f" {SUPER}", LIGHTNING):
        with pytest.raises(ModelIdentityMismatch):
            DeploymentResolver.verify_response_identity(resolved, other)


# ── gateway: matrix A–E with provider call counts ────────────────────────────


async def test_matrix_a_approved_dispatches_resolved_id():
    provider = RecordingProvider()
    gw = _gateway({}, provider)
    resp = await gw.generate(_req())
    assert provider.calls == [SUPER]
    assert resp.model_id == SUPER
    assert resp.generation == "nemotron-3"
    assert resp.identity_verified is True
    assert resp.provider_reported_model_id == SUPER


async def test_matrix_b_unapproved_env_binding_zero_provider_calls():
    provider = RecordingProvider()
    gw = _gateway({"NEMOTRON_SUPER_MODEL": "example-org/unapproved-model-x"}, provider)
    with pytest.raises(ModelPolicyViolation):
        await gw.generate(_req())
    assert provider.calls == []
    assert gw.registry.binding_violations()[0]["role"] == "super"


async def test_matrix_b_fallback_chain_does_not_silently_skip_violation():
    """A violating role in the fallback chain is a hard stop, not a skip."""
    provider = RecordingProvider()
    gw = _gateway(
        {
            "NEMOTRON_LIGHTNING_MODEL": "example-org/unapproved-model-z",
            "NEMOTRON_NANO_ENABLED": "true",
        },
        provider,
    )
    with pytest.raises(ModelPolicyViolation):
        await gw.generate(_req(ReasoningLevel.LOW))
    assert provider.calls == []


async def test_matrix_c_role_mismatch_zero_provider_calls():
    provider = RecordingProvider()
    gw = _gateway({"NEMOTRON_SUPER_MODEL": LIGHTNING}, provider)
    with pytest.raises(ModelPolicyViolation) as exc:
        await gw.generate(_req())
    assert exc.value.reason == "ROLE_MISMATCH"
    assert provider.calls == []


async def test_matrix_d_substitution_raises_after_one_call():
    provider = RecordingProvider(answer_as="example-org/substituted-model-y")
    gw = _gateway({}, provider)
    with pytest.raises(ModelIdentityMismatch):
        await gw.generate(_req())
    assert provider.calls == [SUPER]


async def test_matrix_e_unknown_id_zero_provider_calls():
    provider = RecordingProvider()
    gw = _gateway(
        {"NEMOTRON_ULTRA_ENABLED": "true", "NEMOTRON_ULTRA_MODEL": "unknown/model"},
        provider,
    )
    with pytest.raises(ModelPolicyViolation):
        await gw.generate(_req(task="judge_this"))
    assert provider.calls == []


async def test_policy_filter_excludes_violating_candidates():
    provider = RecordingProvider()
    gw = _gateway({"NEMOTRON_LIGHTNING_MODEL": "x/y"}, provider)
    pf = PolicyFilter(gw.registry)
    ids = pf.candidate_model_ids(_req(ReasoningLevel.LOW), _req().deployment_mode)
    assert "x/y" not in ids


async def test_nim_provider_refuses_empty_model_id():
    from maiw_models import NIMProvider

    class _Client:
        called = False

        async def generate_response(self, **kwargs):  # pragma: no cover
            _Client.called = True

    prov = NIMProvider(_Client())  # type: ignore[arg-type]
    with pytest.raises(ModelPolicyViolation):
        await prov.call(model_id="", request=_req(), capability=None)
    assert _Client.called is False


async def test_evaluate_with_model_in_policy_rejects_unapproved_binding():
    provider = RecordingProvider()
    gw = _gateway({"NEMOTRON_SUPER_MODEL": "example-org/unapproved-model-x"}, provider)
    result = await gw.evaluate_with_model(_req(), "example-org/unapproved-model-x")
    assert result.response_content is None
    assert provider.calls == []


def test_nano_disabled_by_default():
    with patch.dict(
        os.environ,
        {k: v for k, v in os.environ.items() if not k.startswith("NEMOTRON_")},
        clear=True,
    ):
        registry = ModelRegistry()
    assert registry.get_enabled_by_role("nano") is None
    assert registry.binding_violations() == []
