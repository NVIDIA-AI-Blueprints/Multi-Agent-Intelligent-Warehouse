# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.1.0 — thinking-mode fields on the wire for Nemotron models.

Hosted Nemotron 3 Ultra (the default HIGH/CRITICAL model since the hosted
Super retirement) answers HTTP 400 to any ``reasoning_budget`` ("thinking_token_budget
is not yet supported by the V2 model runner") but accepts
``chat_template_kwargs.enable_thinking``.  Both NIM clients therefore switch
thinking explicitly and send a budget only when one is configured (> 0).
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

ULTRA = "nvidia/nemotron-3-ultra-550b-a55b"


def _maiw_models_client(budget: int):
    from maiw_models.providers.nim_client import NIMClient, NIMConfig

    config = NIMConfig(llm_api_key="test-key", llm_model=ULTRA)
    config.default_reasoning_budget = budget
    return NIMClient(config=config, enable_cache=False)


def _legacy_client(budget: int):
    from src.api.services.llm.nim_client import NIMClient, NIMConfig

    config = NIMConfig(llm_api_key="test-key", llm_model=ULTRA)
    config.default_reasoning_budget = budget
    return NIMClient(config=config, enable_cache=False)


CLIENTS = [_maiw_models_client, _legacy_client]


def _payload(client, **kwargs) -> dict:
    captured: dict = {}

    async def fake_post(path, json=None, **_):
        captured.update(json or {})
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "model": captured.get("model"),
            "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
            "usage": {},
        }
        return resp

    client.llm_client.post = fake_post
    asyncio.run(
        client.generate_response(
            messages=[{"role": "user", "content": "hi"}], max_retries=1, **kwargs
        )
    )
    return captured


@pytest.mark.parametrize("make", CLIENTS)
def test_thinking_on_default_budget_sends_no_budget(make):
    """HIGH reasoning with the default budget (0): the request Ultra accepts."""
    body = _payload(make(0), enable_thinking=True)
    assert body["chat_template_kwargs"] == {"enable_thinking": True}
    assert "reasoning_budget" not in body


@pytest.mark.parametrize("make", CLIENTS)
def test_thinking_on_configured_budget_is_sent(make):
    body = _payload(make(0), enable_thinking=True, reasoning_budget=1024)
    assert body["chat_template_kwargs"] == {"enable_thinking": True}
    assert body["reasoning_budget"] == 1024


@pytest.mark.parametrize("make", CLIENTS)
def test_configured_default_budget_is_sent(make):
    body = _payload(make(2048), enable_thinking=True)
    assert body["reasoning_budget"] == 2048


@pytest.mark.parametrize("make", CLIENTS)
def test_thinking_off_sends_disable_and_no_budget(make):
    body = _payload(make(2048), enable_thinking=False)
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert "reasoning_budget" not in body


@pytest.mark.parametrize("make", CLIENTS)
def test_non_nemotron_model_gets_no_thinking_fields(make):
    body = _payload(
        make(2048), enable_thinking=True, model_override="example-org/other"
    )
    assert "chat_template_kwargs" not in body
    assert "reasoning_budget" not in body
