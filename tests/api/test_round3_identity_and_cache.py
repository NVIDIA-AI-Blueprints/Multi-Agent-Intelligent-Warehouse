# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.0.1 round 3 — adjacent release-critical gaps from the third re-audit.

N-1  A provider response with no ``model`` field was accepted: 200 with
     content and ``identity_verified=false``.  Now every answer whose model
     identity is missing or malformed is discarded (502
     MODEL_IDENTITY_UNVERIFIABLE); a successful answer is always verified.

N-2  The response cache key ignored the reasoning mode (a MEDIUM request was
     served HIGH's cached thinking-mode answer) and stripped timestamps /
     UUIDs / dates from prompts.  The key now covers the exact prompt, every
     sampling parameter, the dispatched physical model, the thinking mode and
     budget, and the routing intent.

All requests go through the canonical shipped app ``maiw_api.app:app`` and
its real ModelGateway → DeploymentResolver → NIMProvider → NIMClient chain
against a local fake OpenAI-compatible provider.
"""

from __future__ import annotations

import pytest

from tests.api.canonical_harness import (
    FakeNIM,
    canonical_env,
    install_gateway,
    running_canonical_app,
)

SUPER = "nvidia/nemotron-3-super-120b-a12b"
LIGHTNING = "nvidia/nemotron-3.5-lightning-30b-a3b"
_ROLE_ENVS = [
    f"NEMOTRON_{r}_{k}"
    for r in ("SUPER", "LIGHTNING", "NANO", "ULTRA", "NANO_OMNI")
    for k in ("MODEL", "ENABLED")
] + ["LLM_MODEL", "MAIW_NIM_MODEL"]


@pytest.fixture
def fake():
    f = FakeNIM(content="answer-from {model} thinking={thinking}")
    yield f
    f.close()


@pytest.fixture
def token(monkeypatch, tmp_path, fake):
    for key in _ROLE_ENVS:
        monkeypatch.delenv(key, raising=False)
    tok = canonical_env(monkeypatch, tmp_path, fake)
    yield tok
    from maiw_models import reset_model_gateway

    reset_model_gateway()


async def _infer(client, token, reasoning="high", content="say ok"):
    return await client.post(
        "/api/v1/inference",
        json={
            "task": "round3_probe",
            "messages": [{"role": "user", "content": content}],
            "reasoning": reasoning,
        },
        headers={"X-Maiw-Internal-Token": token},
    )


def _calls(fake):
    return [r["model"] for r in fake.chat_requests()]


# ── N-1: provider identity matrix (match / mismatch / missing / malformed) ───


async def test_identity_match_is_verified(token, fake):
    install_gateway(fake)
    async with running_canonical_app() as (_, client):
        r = await _infer(client, token)
    assert r.status_code == 200
    route = r.json()["route"]
    assert route["identity_verified"] is True
    assert route["provider_reported_model_id"] == SUPER == route["selected_model_id"]
    assert _calls(fake) == [SUPER]


@pytest.mark.parametrize(
    "reported",
    [LIGHTNING, "example-org/substituted-model-y", SUPER.upper(), SUPER + " "],
)
async def test_identity_mismatch_fails_closed(token, fake, reported):
    fake.return_model = reported
    install_gateway(fake)
    async with running_canonical_app() as (_, client):
        r = await _infer(client, token)
    assert r.status_code == 502
    assert r.json()["code"] == "MODEL_IDENTITY_MISMATCH"
    assert "content" not in r.json()
    assert _calls(fake) == [SUPER]


async def test_identity_missing_fails_closed(token, fake):
    fake.omit_model = True
    install_gateway(fake)
    async with running_canonical_app() as (_, client):
        r = await _infer(client, token)
    assert r.status_code == 502
    assert r.json()["code"] == "MODEL_IDENTITY_UNVERIFIABLE"
    assert "content" not in r.json()
    assert _calls(fake) == [SUPER]


@pytest.mark.parametrize("value", ["", "   ", None, 123, ["x"], {"id": SUPER}])
async def test_identity_malformed_fails_closed(token, fake, value):
    fake.model_field = value
    install_gateway(fake)
    async with running_canonical_app() as (_, client):
        r = await _infer(client, token)
    assert r.status_code == 502
    assert r.json()["code"] == "MODEL_IDENTITY_UNVERIFIABLE"
    assert _calls(fake) == [SUPER]


async def test_gateway_never_returns_an_unverified_success():
    """Library level: ModelGateway.generate raises instead of identity_verified=False."""
    from maiw_models import (
        ModelGateway,
        ModelIdentityUnverifiable,
        ModelRegistry,
        ModelRequest,
        ReasoningLevel,
    )
    from maiw_models.providers.nim_client import LLMResponse
    from maiw_models.router import ModelRouter

    class NoIdentityProvider:
        async def call(self, *, model_id, request, capability):
            return LLMResponse(
                content="x", usage={}, model=model_id, finish_reason="stop"
            )

    registry = ModelRegistry()
    gateway = ModelGateway(
        provider=NoIdentityProvider(), registry=registry, router=ModelRouter(registry)
    )
    with pytest.raises(ModelIdentityUnverifiable):
        await gateway.generate(
            ModelRequest(
                task="t",
                messages=[{"role": "user", "content": "x"}],
                reasoning=ReasoningLevel.HIGH,
            )
        )


async def test_nim_client_only_accepts_a_non_empty_string_identity():
    from unittest.mock import AsyncMock, MagicMock

    from maiw_models.providers.nim_client import NIMClient, NIMConfig

    client = NIMClient(
        config=NIMConfig(llm_base_url="http://127.0.0.1:1/v1", llm_api_key="x"),
        enable_cache=False,
    )
    cases = ((SUPER, SUPER), (123, None), ("", None), ("  ", None), (None, None))
    for value, expected in cases:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "choices": [{"message": {"content": "x"}, "finish_reason": "stop"}],
            "usage": {},
            "model": value,
        }
        client.llm_client.post = AsyncMock(return_value=resp)
        out = await client.generate_response(
            messages=[{"role": "user", "content": "x"}],
            model_override=SUPER,
            max_retries=1,
        )
        assert out.provider_model == expected, value
    await client.close()


# ── N-2: response cache isolation ────────────────────────────────────────────


@pytest.mark.parametrize(
    "first,second",
    [("high", "low"), ("low", "high")],
)
async def test_cache_high_and_low_never_share_an_entry(token, fake, first, second):
    install_gateway(fake, enable_cache=True)
    expected = {"high": SUPER, "low": LIGHTNING}
    async with running_canonical_app() as (_, client):
        r1 = await _infer(client, token, reasoning=first)
        r2 = await _infer(client, token, reasoning=second)
        # repeat both: now served from two DISTINCT cache entries
        r3 = await _infer(client, token, reasoning=first)
        r4 = await _infer(client, token, reasoning=second)
    for r, level in ((r1, first), (r2, second), (r3, first), (r4, second)):
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["route"]["selected_model_id"] == expected[level]
        assert body["route"]["identity_verified"] is True
        # the answer was produced by the model this request was routed to
        assert body["content"].startswith(f"answer-from {expected[level]}")
    assert _calls(fake) == [expected[first], expected[second]]  # 2 entries, 2 calls


async def test_cache_medium_never_reuses_high_thinking_answer(token, fake):
    """Same prompt, same Super model, different thinking mode → two entries."""
    install_gateway(fake, enable_cache=True)
    async with running_canonical_app() as (_, client):
        high = await _infer(client, token, reasoning="high")
        medium = await _infer(client, token, reasoning="medium")
    assert high.json()["content"] == f"answer-from {SUPER} thinking=budget"
    assert medium.json()["content"] == f"answer-from {SUPER} thinking=off"
    assert _calls(fake) == [SUPER, SUPER]


async def test_cache_does_not_strip_timestamps_or_ids(token, fake):
    install_gateway(fake, enable_cache=True)
    async with running_canonical_app() as (_, client):
        await _infer(client, token, content="state at 2026-10-11T03:00:00Z")
        await _infer(client, token, content="state at 2026-10-11T04:00:00Z")
        await _infer(client, token, content="task 1b4e28ba-2fa1-11d2-883f-0016d3cca427")
        await _infer(client, token, content="task 6fa459ea-ee8a-3ca4-894e-db77e160355e")
    assert len(_calls(fake)) == 4


async def test_cache_still_serves_identical_requests(token, fake):
    install_gateway(fake, enable_cache=True)
    async with running_canonical_app() as (_, client):
        a = await _infer(client, token, reasoning="low")
        b = await _infer(client, token, reasoning="low")
    assert a.json()["content"] == b.json()["content"]
    assert _calls(fake) == [LIGHTNING]


def test_cache_key_covers_every_routing_input():
    from maiw_models.providers.nim_client import NIMClient, NIMConfig

    client = NIMClient(
        config=NIMConfig(llm_base_url="http://127.0.0.1:1/v1", llm_api_key="x"),
        enable_cache=True,
    )
    msgs = [{"role": "user", "content": "x"}]
    base = dict(
        model=SUPER,
        enable_thinking=True,
        reasoning_budget=1024,
        cache_scope={
            "reasoning": "high",
            "risk_level": "low",
            "modality": "text",
            "deployment_mode": "nvidia_hosted",
            "role": "super",
            "generation": "nemotron-3",
            "model_id": SUPER,
        },
    )

    def key(messages=msgs, **over):
        kw = {**base, **over}
        return client._generate_cache_key(messages, 0.1, 100, 1.0, 0.0, 0.0, **kw)

    reference = key()
    variants = [
        key(model=LIGHTNING),
        key(enable_thinking=False),
        key(reasoning_budget=None),
        key(messages=[{"role": "user", "content": "x 2026-10-11T03:00:00Z"}]),
        key(messages=[{"role": "system", "content": "x"}]),
    ]
    for field, value in (
        ("reasoning", "medium"),
        ("risk_level", "high"),
        ("modality", "image"),
        ("role", "lightning"),
        ("generation", "nemotron-3.5"),
        ("model_id", LIGHTNING),
        ("deployment_mode", "self_hosted"),
    ):
        variants.append(key(cache_scope={**base["cache_scope"], field: value}))
    assert reference not in variants
    assert len(set(variants)) == len(variants)
    assert key() == reference  # deterministic
