# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.0.1 round 2 — NEW-P1-01: final physical model identity.

Recreates the independent re-audit's fake-provider matrix against the
canonical shipped app (``maiw_api.app:app``, real lifespan, real
ModelGateway → ModelRouter/PolicyFilter → DeploymentResolver → NIMProvider →
NIMClient chain).  The provider is a local fake OpenAI-compatible server that
records the ``model`` field of every request it receives; nothing is
forwarded anywhere.

    A  approved role + approved physical model          → 200, 1 provider call
    B  approved role + unapproved physical model (env)  → 503, 0 provider calls
    C  approved generation label + mismatched model ID  → 503, 0 provider calls
    D  provider substitutes a different model           → 502, response discarded
    E  unknown model ID                                 → 503, 0 provider calls
"""

from __future__ import annotations

import json

import pytest

from tests.api.canonical_harness import (
    FakeNIM,
    canonical_env,
    install_gateway,
    running_canonical_app,
)

SUPER = "nvidia/nemotron-3-super-120b-a12b"
LIGHTNING = "nvidia/nemotron-3.5-lightning-30b-a3b"
NANO = "nvidia/nemotron-3-nano-30b-a3b"
UNAPPROVED_X = "example-org/unapproved-model-x"
SUBSTITUTED_Y = "example-org/substituted-model-y"

_ROLE_ENVS = (
    "NEMOTRON_LIGHTNING_MODEL",
    "NEMOTRON_NANO_MODEL",
    "NEMOTRON_SUPER_MODEL",
    "NEMOTRON_ULTRA_MODEL",
    "NEMOTRON_LIGHTNING_ENABLED",
    "NEMOTRON_NANO_ENABLED",
    "NEMOTRON_SUPER_ENABLED",
    "NEMOTRON_ULTRA_ENABLED",
    "LLM_MODEL",
    "MAIW_NIM_MODEL",
)


@pytest.fixture
def fake():
    f = FakeNIM(content="FAKE-PROVIDER-RESPONSE")
    yield f
    f.close()


@pytest.fixture
def app_env(monkeypatch, tmp_path, fake):
    """Canonical env with a clean model-binding environment."""
    for key in _ROLE_ENVS:
        monkeypatch.delenv(key, raising=False)
    token = canonical_env(monkeypatch, tmp_path, fake)
    yield token, monkeypatch
    from maiw_models import reset_model_gateway

    reset_model_gateway()


async def _infer(client, token, reasoning="high", task="round2_identity_probe"):
    return await client.post(
        "/api/v1/inference",
        json={
            "task": task,
            "messages": [{"role": "user", "content": "say ok"}],
            "reasoning": reasoning,
        },
        headers={"X-Maiw-Internal-Token": token},
    )


async def _run(fake, token, reasoning="high", task="round2_identity_probe"):
    install_gateway(fake)
    async with running_canonical_app() as (_, client):
        response = await _infer(client, token, reasoning=reasoning, task=task)
        ready = await client.get("/api/v1/ready")
        live = await client.get("/api/v1/live")
    return response, ready, live


def _provider_models(fake):
    return [r["model"] for r in fake.chat_requests()]


# ── A: approved role + approved physical model → allowed ─────────────────────


@pytest.mark.parametrize(
    "reasoning,role,model_id,generation",
    [
        ("high", "super", SUPER, "nemotron-3"),
        ("low", "lightning", LIGHTNING, "nemotron-3.5"),
    ],
)
async def test_a_approved_role_and_physical_model_allowed(
    app_env, fake, reasoning, role, model_id, generation
):
    token, _ = app_env
    response, ready, _ = await _run(fake, token, reasoning=reasoning)
    assert response.status_code == 200, response.text
    body = response.json()
    route = body["route"]
    assert route["selected_role"] == role
    assert route["selected_model_id"] == model_id == body["model_id"]
    assert route["generation"] == generation
    assert route["approved_family"] is True
    assert route["provider_reported_model_id"] == model_id
    assert route["identity_verified"] is True
    assert _provider_models(fake) == [model_id]  # provider_calls == 1
    assert ready.status_code == 200, ready.json()


async def test_a_medium_reasoning_falls_back_to_super_with_nano_disabled_by_default(
    app_env, fake
):
    """§13: Nano is not enabled by default (hosted Nano retired, HTTP 410)."""
    token, _ = app_env
    response, _, _ = await _run(fake, token, reasoning="medium")
    assert response.status_code == 200, response.text
    route = response.json()["route"]
    assert route["selected_role"] == "super"
    assert route["fallback_used"] is True
    assert _provider_models(fake) == [SUPER]
    assert NANO not in _provider_models(fake)


# ── B: approved role bound to an unapproved physical model → rejected ────────


@pytest.mark.parametrize(
    "env,reasoning,role",
    [
        ({"NEMOTRON_SUPER_MODEL": UNAPPROVED_X}, "high", "super"),
        (
            {"NEMOTRON_LIGHTNING_MODEL": "example-org/unapproved-model-z"},
            "low",
            "lightning",
        ),
        # re-audit config D: fallback nano→super lands on an unapproved Super
        (
            {"NEMOTRON_NANO_ENABLED": "false", "NEMOTRON_SUPER_MODEL": UNAPPROVED_X},
            "medium",
            "super",
        ),
    ],
)
async def test_b_unapproved_physical_model_rejected_before_provider(
    app_env, fake, env, reasoning, role
):
    token, monkeypatch = app_env
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    response, ready, live = await _run(fake, token, reasoning=reasoning)
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["code"] == "MODEL_POLICY_VIOLATION"
    assert "content" not in body
    assert fake.chat_requests() == []  # provider_calls == 0
    # The misconfiguration is also visible to readiness, never "READY".
    assert ready.status_code == 503
    rbody = ready.json()
    assert "model_gateway" in rbody["failed_components"]
    violations = rbody["components"]["model_gateway"]["binding_violations"]
    assert any(v["role"] == role for v in violations)
    assert live.status_code == 200


# ── C: approved generation label + mismatched model ID → rejected ────────────


@pytest.mark.parametrize(
    "env,reasoning",
    [
        # an APPROVED nemotron-3.5 ID bound to the nemotron-3 Super role
        ({"NEMOTRON_SUPER_MODEL": LIGHTNING}, "high"),
        # an APPROVED nemotron-3 ID bound to the nemotron-3.5 Lightning role
        ({"NEMOTRON_LIGHTNING_MODEL": SUPER}, "low"),
        # look-alike IDs that "look like" the approved family
        ({"NEMOTRON_SUPER_MODEL": SUPER + "-v2"}, "high"),
        ({"NEMOTRON_SUPER_MODEL": "nvidia/nemotron-3-super"}, "high"),
        ({"NEMOTRON_SUPER_MODEL": " " + SUPER}, "high"),
    ],
)
async def test_c_generation_label_with_mismatched_model_id_rejected(
    app_env, fake, env, reasoning
):
    token, monkeypatch = app_env
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    response, ready, _ = await _run(fake, token, reasoning=reasoning)
    assert response.status_code == 503, response.text
    assert response.json()["code"] == "MODEL_POLICY_VIOLATION"
    assert fake.chat_requests() == []  # provider_calls == 0
    assert ready.status_code == 503


# ── D: provider substitutes a different model in its response → rejected ─────


async def test_d_provider_model_substitution_fails_closed(app_env, fake):
    token, _ = app_env
    fake.return_model = SUBSTITUTED_Y
    response, ready, _ = await _run(fake, token, reasoning="high")
    assert response.status_code == 502, response.text
    body = response.json()
    assert body["code"] == "MODEL_IDENTITY_MISMATCH"
    assert "content" not in body and "FAKE-PROVIDER-RESPONSE" not in response.text
    assert SUBSTITUTED_Y in body["message"] and SUPER in body["message"]
    # the approved model WAS dispatched (provider_calls == 1) — the answer is
    # what failed the identity check
    assert _provider_models(fake) == [SUPER]
    # a lying provider is a per-request failure, not process un-readiness
    assert ready.status_code == 200


async def test_d_substitution_to_another_approved_model_also_fails(app_env, fake):
    """Even an approved model is rejected if it is not the one dispatched."""
    token, _ = app_env
    fake.return_model = LIGHTNING
    response, _, _ = await _run(fake, token, reasoning="high")
    assert response.status_code == 502
    assert response.json()["code"] == "MODEL_IDENTITY_MISMATCH"


# ── E: unknown model ID → rejected ───────────────────────────────────────────


async def test_e_unknown_model_id_rejected(app_env, fake):
    token, monkeypatch = app_env
    monkeypatch.setenv("NEMOTRON_ULTRA_ENABLED", "true")
    monkeypatch.setenv("NEMOTRON_ULTRA_MODEL", "totally-unknown/model-e")
    # judge/eval task names route to the Ultra role
    response, ready, _ = await _run(fake, token, reasoning="high", task="judge_task")
    assert response.status_code == 503, response.text
    assert response.json()["code"] == "MODEL_POLICY_VIOLATION"
    assert "UNAPPROVED_MODEL_ID" in response.json()["message"]
    assert fake.chat_requests() == []
    assert ready.status_code == 503


# ── §6: other selectors cannot change the dispatched physical model ──────────


@pytest.mark.parametrize("var", ["LLM_MODEL", "MAIW_NIM_MODEL"])
async def test_llm_model_selectors_do_not_change_dispatch(app_env, fake, var):
    token, monkeypatch = app_env
    monkeypatch.setenv(var, UNAPPROVED_X)
    response, _, _ = await _run(fake, token, reasoning="high")
    assert response.status_code == 200
    assert _provider_models(fake) == [SUPER]
    assert UNAPPROVED_X not in json.dumps(response.json())


async def test_provider_with_no_reported_model_is_not_relabelled(app_env, fake):
    """A provider that reports no model: dispatched ID returned, unverified."""
    token, _ = app_env
    fake.omit_model = True
    response, _, _ = await _run(fake, token, reasoning="high")
    assert response.status_code == 200
    route = response.json()["route"]
    assert route["selected_model_id"] == SUPER
    assert route["provider_reported_model_id"] is None
    assert route["identity_verified"] is False
