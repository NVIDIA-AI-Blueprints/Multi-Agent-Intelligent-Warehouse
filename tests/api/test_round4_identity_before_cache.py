# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.0.1 round 4 — provider identity is verified BEFORE a response is cached
(fourth re-audit NEW4-P2-04).

The audit found that ``NIMClient`` cached every provider answer before
ModelGateway verified its model identity: after a substituted / unverifiable
answer the same prompt kept failing with 502 for the cache TTL even once the
provider was fixed.  Now only an answer whose reported model exactly equals
the dispatched model is cached; a failed identity is never served from cache.

Canonical shipped app → real ModelGateway → DeploymentResolver → NIMProvider
→ NIMClient (cache ENABLED) → local fake OpenAI-compatible provider.
"""

from __future__ import annotations

import pytest

from tests.api.canonical_harness import (
    _UNSET,
    install_gateway,
    running_canonical_app,
)
from tests.api.test_round3_identity_and_cache import (  # noqa: F401 - fixtures
    LIGHTNING,
    SUPER,
    _calls,
    _infer,
    fake,
    token,
)


def _break(fake, how: str) -> None:
    if how == "substituted":
        fake.return_model = "example-org/substituted-model-y"
    elif how == "cross_role":
        fake.return_model = LIGHTNING
    elif how == "missing":
        fake.omit_model = True
    elif how == "empty":
        fake.model_field = ""
    elif how == "malformed":
        fake.model_field = 123


def _fix(fake) -> None:
    fake.return_model = None
    fake.omit_model = False
    fake.model_field = _UNSET


@pytest.mark.parametrize(
    "how,code",
    [
        ("substituted", "MODEL_IDENTITY_MISMATCH"),
        ("cross_role", "MODEL_IDENTITY_MISMATCH"),
        ("missing", "MODEL_IDENTITY_UNVERIFIABLE"),
        ("empty", "MODEL_IDENTITY_UNVERIFIABLE"),
        ("malformed", "MODEL_IDENTITY_UNVERIFIABLE"),
    ],
)
async def test_identity_failure_is_never_cached(token, fake, how, code):
    install_gateway(fake, enable_cache=True)
    async with running_canonical_app() as (_, client):
        _break(fake, how)
        bad = await _infer(client, token, content="r4 poisoning probe")
        assert bad.status_code == 502, bad.text
        assert bad.json()["code"] == code
        # still broken: the provider is asked again (nothing was cached)
        bad2 = await _infer(client, token, content="r4 poisoning probe")
        assert bad2.status_code == 502
        assert len(_calls(fake)) == 2

        _fix(fake)
        good = await _infer(client, token, content="r4 poisoning probe")
        assert good.status_code == 200, good.text
        assert good.json()["route"]["identity_verified"] is True
        assert good.json()["route"]["provider_reported_model_id"] == SUPER
        # a fresh provider call, not a stale identity failure from cache
        assert len(_calls(fake)) == 3

        # the VERIFIED answer is cached and served for the identical request
        again = await _infer(client, token, content="r4 poisoning probe")
        assert again.status_code == 200
        assert again.json()["content"] == good.json()["content"]
        assert len(_calls(fake)) == 3


async def test_cache_stays_isolated_by_reasoning_level_after_a_failure(token, fake):
    """§28: LOW / MEDIUM / HIGH never share an entry; the physical model is keyed."""
    install_gateway(fake, enable_cache=True)
    async with running_canonical_app() as (_, client):
        fake.return_model = "example-org/substituted-model-y"
        assert (await _infer(client, token, reasoning="high")).status_code == 502
        _fix(fake)
        seen = {}
        for level in ("high", "medium", "low", "high", "medium", "low"):
            r = await _infer(client, token, reasoning=level)
            assert r.status_code == 200, r.text
            seen.setdefault(level, set()).add(r.json()["content"])
    assert {lvl: len(v) for lvl, v in seen.items()} == {
        "high": 1,
        "medium": 1,
        "low": 1,
    }
    assert seen["high"] == {f"answer-from {SUPER} thinking=budget"}
    assert seen["medium"] == {f"answer-from {SUPER} thinking=off"}
    assert seen["low"] == {f"answer-from {LIGHTNING} thinking=off"}
    # 1 failed HIGH + 1 call per level; the repeats were cache hits
    assert _calls(fake) == [SUPER, SUPER, SUPER, LIGHTNING]


async def test_nim_client_caches_only_identity_matching_answers(fake):
    """Library level: the NIMClient never stores an unverified answer."""
    from maiw_models.providers.nim_client import NIMClient, NIMConfig

    client = NIMClient(
        config=NIMConfig(llm_base_url=fake.base_url, llm_api_key="k", timeout=5),
        enable_cache=True,
    )
    try:
        msgs = [{"role": "user", "content": "x"}]
        fake.return_model = LIGHTNING
        r = await client.generate_response(msgs, model_override=SUPER)
        assert r.provider_model == LIGHTNING
        assert client.get_cache_stats()["cached_entries"] == 0
        _fix(fake)
        r = await client.generate_response(msgs, model_override=SUPER)
        assert r.provider_model == SUPER
        assert client.get_cache_stats()["cached_entries"] == 1
    finally:
        await client.close()
