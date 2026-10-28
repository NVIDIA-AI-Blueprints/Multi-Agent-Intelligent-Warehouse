# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
RATE_LIMIT_FAIL_MODE — what the rate limiter does when it fails internally
(e.g. Redis goes away): ``open`` (default) allows the request, ``closed``
answers 503 RATE_LIMITER_UNAVAILABLE.  An invalid value logs a warning and
falls back to ``open``.  The limiter's own 429 is unaffected by the mode.
"""

from __future__ import annotations

import logging

import pytest
from fastapi import HTTPException

from src.api.services.security import rate_limiter
from src.api.services.security.rate_limiter import (
    RateLimiter,
    RateLimiterUnavailable,
    resolve_fail_mode,
)
from tests.api.canonical_harness import (
    FakeNIM,
    canonical_env,
    install_gateway,
    running_canonical_app,
)


class _Req:
    client = type("C", (), {"host": "10.0.0.7"})()
    url = type("U", (), {"path": "/api/v1/auth/login"})()


async def _boom(self, *a, **kw):
    raise RuntimeError("limiter storage unavailable")


class _BrokenRedisPipeline:
    def zremrangebyscore(self, *a):
        pass

    def zcard(self, *a):
        pass

    def zadd(self, *a):
        pass

    def expire(self, *a):
        pass

    async def execute(self):
        raise ConnectionError("redis went away")


class _BrokenRedis:
    def pipeline(self):
        return _BrokenRedisPipeline()


@pytest.fixture
def canonical(monkeypatch, tmp_path):
    fake = FakeNIM()
    canonical_env(monkeypatch, tmp_path, fake)
    install_gateway(fake)
    yield
    fake.close()
    from maiw_models import reset_model_gateway

    reset_model_gateway()


# ── Setting resolution ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, "open"),
        ("", "open"),
        ("open", "open"),
        ("closed", "closed"),
        (" CLOSED ", "closed"),
        ("closed  # reject when the limiter is down", "closed"),
    ],
)
def test_resolve_fail_mode(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("RATE_LIMIT_FAIL_MODE", raising=False)
    else:
        monkeypatch.setenv("RATE_LIMIT_FAIL_MODE", raw)
    assert resolve_fail_mode() == expected


def test_invalid_fail_mode_warns_and_uses_open(monkeypatch, caplog):
    monkeypatch.setenv("RATE_LIMIT_FAIL_MODE", "sometimes")
    with caplog.at_level(logging.WARNING, logger=rate_limiter.__name__):
        assert resolve_fail_mode() == "open"
        assert RateLimiter().fail_mode == "open"
    assert any(
        "RATE_LIMIT_FAIL_MODE" in r.getMessage() and r.levelno == logging.WARNING
        for r in caplog.records
    )


# ── Limiter behaviour per mode ────────────────────────────────────────────────


async def test_open_mode_allows_on_internal_error(monkeypatch):
    monkeypatch.delenv("RATE_LIMIT_FAIL_MODE", raising=False)
    monkeypatch.setattr(RateLimiter, "_check_memory_rate_limit", _boom)
    limiter = RateLimiter()
    assert limiter.fail_mode == "open"
    assert await limiter.check_rate_limit(_Req()) is True


async def test_closed_mode_raises_503_on_internal_error(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_FAIL_MODE", "closed")
    monkeypatch.setattr(RateLimiter, "_check_memory_rate_limit", _boom)
    limiter = RateLimiter()
    with pytest.raises(RateLimiterUnavailable) as info:
        await limiter.check_rate_limit(_Req())
    assert info.value.status_code == 503
    assert info.value.as_body()["code"] == "RATE_LIMITER_UNAVAILABLE"


@pytest.mark.parametrize(("mode", "allowed"), [("open", True), ("closed", False)])
async def test_redis_backend_failure_follows_fail_mode(monkeypatch, mode, allowed):
    """A Redis error mid-flight (after a successful initialize) obeys the mode."""
    monkeypatch.setenv("RATE_LIMIT_FAIL_MODE", mode)
    limiter = RateLimiter()
    limiter.redis_available = True
    limiter.redis_client = _BrokenRedis()
    if allowed:
        assert await limiter.check_rate_limit(_Req()) is True
    else:
        with pytest.raises(RateLimiterUnavailable):
            await limiter.check_rate_limit(_Req())


@pytest.mark.parametrize("mode", ["open", "closed"])
async def test_limiters_own_429_propagates_in_every_mode(monkeypatch, mode):
    monkeypatch.setenv("RATE_LIMIT_FAIL_MODE", mode)
    limiter = RateLimiter()  # in-memory
    for _ in range(5):
        assert await limiter.check_rate_limit(_Req()) is True
    with pytest.raises(HTTPException) as info:
        await limiter.check_rate_limit(_Req())
    assert info.value.status_code == 429
    assert not isinstance(info.value, RateLimiterUnavailable)
    assert "Retry-After" in info.value.headers


# ── Through the shipped app ───────────────────────────────────────────────────


async def test_app_closed_mode_answers_503_rate_limiter_unavailable(
    canonical, monkeypatch
):
    monkeypatch.setenv("RATE_LIMIT_FAIL_MODE", "closed")
    monkeypatch.setattr(RateLimiter, "_check_memory_rate_limit", _boom)
    async with running_canonical_app() as (_, client):
        resp = await client.get("/api/v1/live")
        health = await client.get("/api/v1/health")  # skip-listed: not limited
    assert resp.status_code == 503
    body = resp.json()
    assert body["code"] == "RATE_LIMITER_UNAVAILABLE"
    assert body["status_code"] == 503
    assert health.json().get("code") != "RATE_LIMITER_UNAVAILABLE"


async def test_app_closed_mode_when_limiter_cannot_be_obtained(canonical, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_FAIL_MODE", "closed")

    async def _no_limiter():
        raise RuntimeError("limiter construction failed")

    monkeypatch.setattr("maiw_api.app.get_rate_limiter", _no_limiter)
    async with running_canonical_app() as (_, client):
        resp = await client.get("/api/v1/live")
    assert resp.status_code == 503
    assert resp.json()["code"] == "RATE_LIMITER_UNAVAILABLE"


async def test_app_open_mode_allows_on_internal_error(canonical, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_FAIL_MODE", "open")
    monkeypatch.setattr(RateLimiter, "_check_memory_rate_limit", _boom)
    async with running_canonical_app() as (_, client):
        codes = [(await client.get("/api/v1/live")).status_code for _ in range(3)]
    assert codes == [200, 200, 200]


async def test_app_invalid_mode_allows_on_internal_error(canonical, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_FAIL_MODE", "maybe")
    monkeypatch.setattr(RateLimiter, "_check_memory_rate_limit", _boom)
    async with running_canonical_app() as (_, client):
        resp = await client.get("/api/v1/live")
    assert resp.status_code == 200


async def test_app_closed_mode_still_answers_real_429(canonical, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_FAIL_MODE", "closed")
    async with running_canonical_app() as (_, client):
        responses = [
            await client.post(
                "/api/v1/auth/login", json={"username": "x", "password": "y"}
            )
            for _ in range(7)
        ]
    codes = [r.status_code for r in responses]
    assert 429 not in codes[:5], codes
    assert codes[5:] == [429, 429], codes
    assert responses[5].json()["detail"].startswith("Rate limit exceeded")
    # The login endpoint itself may answer 503 (no database in CORE CI), but
    # never the limiter: a healthy limiter does not trip the closed mode.
    assert all(
        r.json().get("code") != "RATE_LIMITER_UNAVAILABLE" for r in responses
    ), codes
