# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.0.1 round 4 — the rate limiter enforces its limits (fourth re-audit P2-04).

The audit sent 15 logins against a 5/min limit and got 15 × 401, 0 × 429:
``RateLimiter.check_rate_limit`` caught its own ``HTTPException(429)`` in a
fail-open ``except Exception`` and allowed the request.  Separately, an
exception raised from an HTTP middleware bypasses FastAPI's exception
handlers, so even a propagated 429 would have surfaced as a 500.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from tests.api.canonical_harness import (
    FakeNIM,
    canonical_env,
    install_gateway,
    running_canonical_app,
)


@pytest.fixture
def canonical(monkeypatch, tmp_path):
    fake = FakeNIM()
    canonical_env(monkeypatch, tmp_path, fake)
    install_gateway(fake)
    yield
    fake.close()
    from maiw_models import reset_model_gateway

    reset_model_gateway()


async def test_limiter_raises_its_own_429():
    from src.api.services.security.rate_limiter import RateLimiter

    limiter = RateLimiter()  # in-memory (no initialize → no Redis)

    class _Req:
        client = type("C", (), {"host": "10.0.0.9"})()
        url = type("U", (), {"path": "/api/v1/auth/login"})()

    for _ in range(5):
        assert await limiter.check_rate_limit(_Req()) is True
    with pytest.raises(HTTPException) as info:
        await limiter.check_rate_limit(_Req())
    assert info.value.status_code == 429
    assert "Retry-After" in info.value.headers


async def test_canonical_app_answers_429_beyond_the_login_limit(canonical):
    async with running_canonical_app() as (_, client):
        codes = []
        for _ in range(12):
            r = await client.post(
                "/api/v1/auth/login", json={"username": "x", "password": "y"}
            )
            codes.append(r.status_code)
            if r.status_code == 429:
                assert r.json()["detail"].startswith("Rate limit exceeded")
                assert int(r.headers["Retry-After"]) >= 0
    assert 429 not in codes[:5], codes
    assert codes[5:] == [429] * 7, codes
    assert 500 not in codes


async def test_limiter_internal_failure_still_fails_open(canonical, monkeypatch):
    """An unrelated limiter-backend failure does not block traffic."""
    from src.api.services.security.rate_limiter import RateLimiter

    async def _boom(self, *a, **kw):
        raise RuntimeError("limiter storage unavailable")

    monkeypatch.setattr(RateLimiter, "_check_memory_rate_limit", _boom)
    async with running_canonical_app() as (_, client):
        codes = [(await client.get("/api/v1/live")).status_code for _ in range(3)]
    assert codes == [200, 200, 200]


async def test_skip_listed_health_paths_are_not_limited(canonical, monkeypatch):
    from src.api.services.security import rate_limiter

    original = rate_limiter.RateLimiter.__init__

    def _tight(self):
        original(self)
        self.limits["default"] = {"requests": 2, "window_seconds": 60}

    monkeypatch.setattr(rate_limiter.RateLimiter, "__init__", _tight)
    async with running_canonical_app() as (_, client):
        health = [(await client.get("/api/v1/health")).status_code for _ in range(4)]
        live = [(await client.get("/api/v1/live")).status_code for _ in range(4)]
    assert 429 not in health
    assert live[:2] == [200, 200] and live[2:] == [429, 429]
