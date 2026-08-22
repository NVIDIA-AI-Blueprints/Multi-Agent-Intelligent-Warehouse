# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
tests/api/test_app_startup.py

Infrastructure-free tests that verify the MAIW API app can be constructed
and that its canonical routers are registered.  No database, Redis, or MCP
server is required.

Strategy:
    1. Stub the lifespan so it doesn't try to connect to any external service.
    2. Pre-populate ``app.state.runtime`` with a minimal MAIWRuntime mock.
    3. Use httpx.AsyncClient (ASGI transport) — no real HTTP port opened.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_mock_runtime():
    rt = MagicMock()
    rt.equipment_agent = None
    rt.operations_agent = None
    rt.safety_agent = None
    rt.mcp_client = None
    rt.mcp_registry = None
    rt.mcp_inventory_available = False
    rt.mcp_equipment_available = False
    rt.mcp_labor_available = False
    rt.mcp_wave_available = False
    return rt


@asynccontextmanager
async def _noop_lifespan(app: FastAPI):
    app.state.runtime = _make_mock_runtime()
    yield


@pytest.fixture()
def test_app():
    """MAIW app with a no-op lifespan and mocked middleware deps."""
    with (
        patch("maiw_api.app.lifespan", _noop_lifespan),
        patch(
            "src.api.services.security.rate_limiter.get_rate_limiter",
            return_value=AsyncMock(check_rate_limit=AsyncMock()),
        ),
        patch(
            "src.api.services.monitoring.metrics.record_request_metrics",
        ),
    ):
        import importlib
        import maiw_api.app as app_module

        importlib.reload(app_module)
        app = app_module.app
        # ASGITransport does not run the ASGI lifespan events, so set state
        # directly so that get_runtime(request) can find it.
        app.state.runtime = _make_mock_runtime()
        return app


# ── Helpers ───────────────────────────────────────────────────────────────────


def _collect_paths(app) -> set:
    """
    Collect all route paths from the app.

    Newer Starlette flattens include_router() calls so every item in
    app.routes is an APIRoute with a .path attribute.  Older versions
    (and some edge cases) leave _IncludedRouter wrapper objects that
    expose .routes but not .path.  This helper handles both.
    """
    paths: set = set()
    for route in app.routes:
        if hasattr(route, "path"):
            paths.add(route.path)
        if hasattr(route, "routes"):
            for subroute in route.routes:
                if hasattr(subroute, "path"):
                    paths.add(subroute.path)
    return paths


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_app_is_fastapi_instance(test_app):
    from fastapi import FastAPI

    assert isinstance(test_app, FastAPI)


def test_canonical_routes_registered(test_app):
    """Canonical routers must register their paths on the app."""
    paths = _collect_paths(test_app)

    expected = {
        "/api/v1/live",
        "/api/v1/ready",
        "/api/v1/health",
        "/api/v1/health/simple",
        "/api/v1/version",
        "/api/v1/equipment",
        "/api/v1/equipment/assign",
        "/api/v1/equipment/release",
        "/api/v1/equipment/maintenance",
        "/api/v1/operations/tasks",
        "/api/v1/operations/workforce",
        "/api/v1/safety/incidents",
        "/api/v1/safety/policies",
        "/api/v1/mcp/status",
        "/api/v1/mcp/capabilities",
    }
    missing = expected - paths
    assert not missing, f"Missing routes: {missing}"


def test_root_endpoint(test_app):
    paths = _collect_paths(test_app)
    assert "/" in paths


def test_legacy_mcp_router_not_registered(test_app):
    """The retired legacy MCP router must NOT appear in the new app."""
    paths = _collect_paths(test_app)
    assert "/api/v1/mcp/plan" not in paths
    assert "/api/v1/mcp/bind" not in paths
    assert "/api/v1/mcp/route" not in paths


def test_app_title_set(test_app):
    assert "Warehouse" in test_app.title or "MAIW" in test_app.title


@pytest.mark.anyio
async def test_health_live_without_infrastructure(test_app):
    """GET /api/v1/live must return 200 without any external connections."""
    import httpx
    from httpx import ASGITransport

    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as client:
        resp = await client.get("/api/v1/live")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "alive"


@pytest.mark.anyio
async def test_mcp_status_without_server(test_app):
    """GET /api/v1/mcp/status must return 200 even when no MCP server is configured."""
    import httpx
    from httpx import ASGITransport

    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as client:
        resp = await client.get("/api/v1/mcp/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "domains" in body
    assert "client_ready" in body
