# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
CORS and security headers wrap every response of the shipped app.

Starlette makes the last middleware added the outermost.  ``maiw_api.app``
added the security-headers and CORS middleware first (its comment said "first
added = outermost"), so they were the two innermost layers: the 403 of the
origin guard, the 413 of the body-size limit and the 429 of the rate limiter
went out without security headers, and an allowed browser origin could not
read the 413 or 429.  CORS is now the outermost layer and security headers the
next (SonarQube python:S8414 requires CORSMiddleware to be added last).
"""

from __future__ import annotations

import pytest
from fastapi.middleware.cors import CORSMiddleware

from maiw_api.origin_guard import CrossOriginWriteGuardMiddleware
from src.api.middleware.security_headers import SecurityHeadersMiddleware
from tests.api.canonical_harness import (
    FakeNIM,
    canonical_env,
    install_gateway,
    running_canonical_app,
)

ALLOWED = "http://localhost:3001"  # in the default CORS_ORIGINS
FOREIGN = "http://evil.example"


@pytest.fixture
def canonical(monkeypatch, tmp_path):
    fake = FakeNIM()
    canonical_env(monkeypatch, tmp_path, fake)
    install_gateway(fake)
    yield
    fake.close()
    from maiw_models import reset_model_gateway

    reset_model_gateway()


def _assert_security_headers(resp) -> None:
    assert resp.headers.get("x-content-type-options") == "nosniff", resp.headers
    assert resp.headers.get("x-frame-options") == "DENY"
    assert "content-security-policy" in resp.headers


def test_cors_then_security_headers_are_the_outermost_layers():
    from maiw_api.app import app

    stack = [m.cls for m in app.user_middleware]  # outermost first
    assert stack[0] is CORSMiddleware
    assert stack[1] is SecurityHeadersMiddleware
    assert stack[-1] is CrossOriginWriteGuardMiddleware


async def test_body_size_413_is_readable_by_an_allowed_origin(canonical):
    import maiw_api.app as app_module

    async with running_canonical_app() as (_, client):
        resp = await client.post(
            "/api/v1/copilot/turn",
            content=b"x" * (app_module._MAX_REQUEST_SIZE + 1),
            headers={"content-type": "application/json", "origin": ALLOWED},
        )
    assert resp.status_code == 413
    assert resp.headers.get("access-control-allow-origin") == ALLOWED
    _assert_security_headers(resp)


async def test_origin_guard_403_carries_security_headers(canonical):
    async with running_canonical_app() as (_, client):
        resp = await client.post(
            "/api/v1/demo/scenario/healthy_baseline/start",
            json={},
            headers={"origin": FOREIGN},
        )
    assert resp.status_code == 403
    assert "access-control-allow-origin" not in resp.headers
    _assert_security_headers(resp)


async def test_rate_limit_429_is_readable_by_an_allowed_origin(canonical):
    async with running_canonical_app() as (_, client):
        for _ in range(12):
            resp = await client.post(
                "/api/v1/document/upload",
                json={},
                headers={"origin": ALLOWED},
            )
            if resp.status_code == 429:
                break
    assert resp.status_code == 429
    assert resp.headers.get("access-control-allow-origin") == ALLOWED
    _assert_security_headers(resp)


async def test_preflight_is_answered_by_cors_for_an_allowed_origin(canonical):
    async with running_canonical_app() as (_, client):
        resp = await client.options(
            "/api/v1/copilot/turn",
            headers={
                "origin": ALLOWED,
                "access-control-request-method": "POST",
                "access-control-request-headers": "content-type",
            },
        )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == ALLOWED
    assert "POST" in resp.headers.get("access-control-allow-methods", "")


async def test_actual_response_to_an_allowed_origin_carries_both(canonical):
    async with running_canonical_app() as (_, client):
        resp = await client.get("/api/v1/health", headers={"origin": ALLOWED})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == ALLOWED
    _assert_security_headers(resp)
