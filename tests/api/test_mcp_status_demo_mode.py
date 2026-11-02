# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
GET /api/v1/mcp/status in Demo Mode.

Demo Mode registers in-process ``MCPServer`` instances in the
CapabilityRegistry (in-memory transport).  The status router used to return
``registry.resolve(cap)`` as each domain's ``url``, so the response carried
``MCPServer`` objects and failed with ``PydanticSerializationError`` (HTTP 500).

``url`` must be a URL string for HTTP transports and ``None`` for in-memory
ones, with ``transport`` worded as /api/v1/ready's ``mcp_domains`` reports it.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from tests.api.canonical_harness import (
    FakeNIM,
    canonical_env,
    install_gateway,
    running_canonical_app,
)

DOMAINS = ("inventory", "equipment", "labor", "wave")


@pytest.fixture
def fake_nim():
    fake = FakeNIM(content="{}")
    yield fake
    fake.close()


@pytest.fixture
def demo_app_env(monkeypatch, tmp_path, fake_nim):
    """Canonical app in demo mode (in-memory MCP transport)."""
    import maiw_api.bootstrap as bootstrap
    from maiw_api.demo.controller import reset_demo_controller

    canonical_env(monkeypatch, tmp_path, fake_nim)
    monkeypatch.setenv("MAIW_DEMO_MODE", "true")
    monkeypatch.setenv("MAIW_DEPLOYMENT_PROFILE", "demo")
    monkeypatch.setattr(bootstrap, "_DEMO_MODE", True)
    reset_demo_controller()
    install_gateway(fake_nim)
    yield
    from maiw_models import reset_model_gateway

    reset_model_gateway()
    reset_demo_controller()


async def test_mcp_status_demo_mode_is_json_serializable(demo_app_env):
    async with running_canonical_app() as (app, client):
        resp = await client.get("/api/v1/mcp/status")
        assert resp.status_code == 200, resp.text
        body = resp.json()

        endpoints = app.state.runtime.mcp_domain_endpoints
        assert {endpoints[d][0] for d in DOMAINS} == {"in-memory"}

        ready = await client.get("/api/v1/ready")
        ready_domains = ready.json()["components"]["mcp_domains"]["domains"]

    json.dumps(body)
    assert set(body["domains"]) == set(DOMAINS)
    for domain in DOMAINS:
        entry = body["domains"][domain]
        assert entry["available"] is True
        assert entry["url"] is None
        assert entry["transport"] == "in-memory"
        assert entry["transport"] == ready_domains[domain]["transport"]
    assert body["registered_capabilities"]
    assert all(isinstance(c, str) for c in body["registered_capabilities"])


async def test_mcp_status_reports_http_url_and_transport():
    """HTTP transports keep their URL string; unconfigured domains report null."""
    from maiw_api.routers.mcp_status import get_mcp_status

    url = "http://mcp-inventory:9100/mcp"

    class _Registry:
        def all_capabilities(self):
            return ["warehouse.inventory.get"]

        def resolve(self, cap):
            return url

    runtime = SimpleNamespace(
        mcp_registry=_Registry(),
        mcp_client=object(),
        mcp_inventory_available=True,
        mcp_equipment_available=False,
        mcp_labor_available=False,
        mcp_wave_available=False,
        mcp_domain_endpoints={"inventory": ("url", url)},
    )

    body = await get_mcp_status(runtime=runtime)

    json.dumps(body)
    assert body["domains"]["inventory"] == {
        "available": True,
        "transport": "url",
        "url": url,
    }
    assert body["domains"]["equipment"] == {
        "available": False,
        "transport": None,
        "url": None,
    }
