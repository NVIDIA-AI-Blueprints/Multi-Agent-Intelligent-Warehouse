# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.0.1 round 2 — NEW-P1-03: profile-aware readiness on the canonical shipped
app (``maiw_api.app:app``, real lifespan).

Readiness matrix (spec §30):
    all required healthy                 → 200
    required persistence unavailable     → 503
    required DB unavailable              → 503
    required MCP unconfigured            → 503
    required MCP circuit-open            → 503
    required MCP unreachable             → 503
    optional MCP unconfigured            → 200 + NOT_CONFIGURED
    required sandbox unavailable         → 503
    optional sandbox unavailable         → 200 + degraded / not_configured
    provider temporarily unavailable     → 200 (non-critical, every profile)
and /api/v1/live stays 200 in every case.

MCP "servers" here are this test's own TCP listeners on 127.0.0.1:<ephemeral>;
the sandbox CLI is a fake ``openshell`` script in the test's tmp dir.
"""

from __future__ import annotations

import json
import secrets
import socket
import stat
import threading

import pytest

from tests.api.canonical_harness import (
    FakeNIM,
    canonical_env,
    install_gateway,
    running_canonical_app,
)

WRITE_DOMAINS = ("equipment", "labor", "wave")


class _Listener:
    """A local TCP listener that accepts and closes (an MCP 'server' stub)."""

    def __init__(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(16)
        self.port = self.sock.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}/mcp"
        self._stop = False
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()

    def _loop(self) -> None:
        self.sock.settimeout(0.2)
        while not self._stop:
            try:
                conn, _ = self.sock.accept()
                conn.close()
            except OSError:
                continue

    def close(self) -> None:
        self._stop = True
        self._t.join(timeout=2)
        self.sock.close()


def _closed_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def fake():
    f = FakeNIM()
    yield f
    f.close()


@pytest.fixture
def env(monkeypatch, tmp_path, fake):
    for key in (
        "MAIW_DEPLOYMENT_PROFILE",
        "MAIW_REQUIRED_MCP_DOMAINS",
        "MAIW_SANDBOX_MODE",
        "MAIW_SANDBOX_NAME",
        "MAIW_OPENSHELL_BIN",
        "MAIW_MCP_SERVER_EQUIPMENT_URL",
        "MAIW_MCP_SERVER_LABOR_URL",
        "MAIW_MCP_SERVER_WAVE_URL",
        "MAIW_MCP_SERVER_INVENTORY_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    canonical_env(monkeypatch, tmp_path, fake)
    install_gateway(fake)
    yield monkeypatch
    from maiw_models import reset_model_gateway

    reset_model_gateway()


@pytest.fixture
def mcp_servers():
    servers = {d: _Listener() for d in WRITE_DOMAINS}
    yield servers
    for s in servers.values():
        s.close()


def _governed(monkeypatch, servers=None):
    monkeypatch.setenv("MAIW_DEPLOYMENT_PROFILE", "reference_governed")
    # v2.0.1 round 3: the governed write path also needs the operator write
    # credential (tests/api/test_round3_write_auth.py covers its absence).
    monkeypatch.setenv("MAIW_OPERATOR_WRITE_TOKEN", secrets.token_hex(32))
    for domain, server in (servers or {}).items():
        monkeypatch.setenv(f"MAIW_MCP_SERVER_{domain.upper()}_URL", server.url)


def _fake_openshell(tmp_path, sandboxes):
    script = tmp_path / "fake_openshell"
    data = tmp_path / "sandboxes.json"
    data.write_text(json.dumps(sandboxes))
    script.write_text(f'#!/bin/sh\ncat "{data}"\n')
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return str(script)


async def _ready(**_):
    async with running_canonical_app() as (_, client):
        ready = await client.get("/api/v1/ready")
        live = await client.get("/api/v1/live")
    assert live.status_code == 200  # §31 liveness stays independent
    return ready.status_code, ready.json()


# ── reference profile (no governed writes): optional MCP ─────────────────────


async def test_reference_profile_optional_mcp_unconfigured_is_ready(env):
    code, body = await _ready()
    assert code == 200, body
    assert body["profile"] == "reference"
    mcp = body["components"]["mcp_domains"]
    assert mcp["status"] == "ready" and mcp["required"] == []
    for domain in ("equipment", "labor", "wave", "inventory"):
        assert mcp["domains"][domain]["state"] == "NOT_CONFIGURED"
        assert body["domain_health"][domain] == "NOT_CONFIGURED"
    # never HEALTHY for an unconfigured domain (re-audit NEW-P1-03)
    assert body["healthy_domains"] == []
    assert body["components"]["governed_write_path"]["status"] == "not_offered"


async def test_runtime_status_reports_not_configured(env):
    async with running_canonical_app() as (_, client):
        status = (await client.get("/api/v1/runtime/status")).json()
    assert set(status["domain_health"].values()) == {"NOT_CONFIGURED"}
    assert status["maiw_operational_status"] == "HEALTHY"


# ── reference_governed: required MCP write domains ───────────────────────────


async def test_governed_all_required_healthy_is_ready(env, mcp_servers):
    _governed(env, mcp_servers)
    code, body = await _ready()
    assert code == 200, body
    mcp = body["components"]["mcp_domains"]
    assert mcp["required"] == sorted(WRITE_DOMAINS)
    for domain in WRITE_DOMAINS:
        assert mcp["domains"][domain]["state"] == "READY"
        assert mcp["domains"][domain]["reachable"] is True
    assert mcp["domains"]["inventory"]["state"] == "NOT_CONFIGURED"  # optional
    assert body["components"]["governed_write_path"]["status"] == "ready"


async def test_governed_required_mcp_unconfigured_is_not_ready(env):
    _governed(env)
    code, body = await _ready()
    assert code == 503
    assert "mcp_domains" in body["failed_components"]
    assert "governed_write_path" in body["failed_components"]
    assert body["components"]["mcp_domains"]["required_unusable"] == sorted(
        WRITE_DOMAINS
    )


async def test_governed_one_required_domain_missing_is_not_ready(env, mcp_servers):
    _governed(env, {d: s for d, s in mcp_servers.items() if d != "wave"})
    code, body = await _ready()
    assert code == 503
    assert body["components"]["mcp_domains"]["required_unusable"] == ["wave"]


async def test_governed_required_mcp_circuit_open_is_not_ready(env, mcp_servers):
    _governed(env, mcp_servers)

    async def _boom():
        raise RuntimeError("mcp down")

    async with running_canonical_app() as (app, client):
        breaker = app.state.runtime.circuit_registry.get("equipment")
        for _ in range(50):
            if breaker.get_stats()["state"] == "open":
                break
            with pytest.raises(Exception):
                await breaker.call(_boom())
        assert breaker.get_stats()["state"] == "open"
        ready = await client.get("/api/v1/ready")
        live = await client.get("/api/v1/live")
    body = ready.json()
    assert ready.status_code == 503, body
    assert live.status_code == 200
    assert body["components"]["mcp_domains"]["domains"]["equipment"]["state"] == (
        "CIRCUIT_OPEN"
    )
    assert body["components"]["mcp_domains"]["required_unusable"] == ["equipment"]


async def test_governed_required_mcp_unreachable_is_not_ready(env, mcp_servers):
    servers = dict(mcp_servers)
    _governed(env, servers)
    env.setenv("MAIW_MCP_SERVER_LABOR_URL", f"http://127.0.0.1:{_closed_port()}/mcp")
    code, body = await _ready()
    assert code == 503
    labor = body["components"]["mcp_domains"]["domains"]["labor"]
    assert labor["state"] == "FAILED" and labor["reachable"] is False


async def test_custom_required_domain_set(env, mcp_servers):
    _governed(env, {"equipment": mcp_servers["equipment"]})
    env.setenv("MAIW_REQUIRED_MCP_DOMAINS", "equipment")
    code, body = await _ready()
    assert code == 200, body
    assert body["components"]["mcp_domains"]["required"] == ["equipment"]


async def test_unknown_profile_is_not_ready(env):
    env.setenv("MAIW_DEPLOYMENT_PROFILE", "production-ish")
    code, body = await _ready()
    assert code == 503
    assert "profile" in body["failed_components"]


# ── persistence / database ───────────────────────────────────────────────────


async def test_required_persistence_unavailable_is_not_ready(env, tmp_path):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    env.setenv("MAIW_PERSISTENCE_ROOT", str(blocker / "maiw"))
    code, body = await _ready()
    assert code == 503
    assert "persistence" in body["failed_components"]


async def test_required_db_unavailable_is_not_ready(env, monkeypatch):
    """Readiness probes the DATA-PATH database (PGHOST/PGPORT), not DATABASE_URL."""
    import importlib
    import sys
    from unittest.mock import MagicMock

    if isinstance(sys.modules.get("asyncpg"), MagicMock):
        monkeypatch.delitem(sys.modules, "asyncpg")
    try:
        importlib.import_module("asyncpg")
    except ImportError:  # pragma: no cover
        pytest.skip("asyncpg not installed")
    env.setenv("MAIW_READINESS_REQUIRE_DATABASE", "true")
    env.setenv("PGHOST", "127.0.0.1")
    env.setenv("PGPORT", str(_closed_port()))
    env.delenv("DATABASE_URL", raising=False)
    code, body = await _ready()
    assert code == 503
    db = body["components"]["database"]
    assert db["status"] == "failed"
    assert db["target"].startswith("127.0.0.1:")


async def test_database_url_must_match_data_path(env):
    env.setenv("MAIW_READINESS_REQUIRE_DATABASE", "true")
    env.setenv("PGHOST", "127.0.0.1")
    env.setenv("PGPORT", "5435")
    env.setenv("DATABASE_URL", "postgresql://warehouse:x@127.0.0.1:55999/warehouse")
    code, body = await _ready()
    assert code == 503
    assert "DATABASE_URL targets" in body["components"]["database"]["reason"]


# ── sandbox ──────────────────────────────────────────────────────────────────


async def test_required_sandbox_unavailable_is_not_ready(env, tmp_path):
    env.setenv("MAIW_SANDBOX_MODE", "required")
    env.setenv("MAIW_SANDBOX_NAME", "maiw-test-sbx")
    env.setenv("MAIW_OPENSHELL_BIN", _fake_openshell(tmp_path, []))
    code, body = await _ready()
    assert code == 503
    sbx = body["components"]["sandbox_runtime"]
    assert sbx["status"] == "failed" and sbx["critical"] is True


async def test_required_sandbox_not_named_is_not_ready(env):
    env.setenv("MAIW_SANDBOX_MODE", "required")
    code, body = await _ready()
    assert code == 503
    assert "sandbox_runtime" in body["failed_components"]


async def test_required_sandbox_ready_is_ready(env, tmp_path):
    env.setenv("MAIW_SANDBOX_MODE", "required")
    env.setenv("MAIW_SANDBOX_NAME", "maiw-test-sbx")
    env.setenv(
        "MAIW_OPENSHELL_BIN",
        _fake_openshell(tmp_path, [{"name": "maiw-test-sbx", "phase": "Ready"}]),
    )
    code, body = await _ready()
    assert code == 200, body
    assert body["components"]["sandbox_runtime"]["status"] == "ready"


async def test_optional_sandbox_unavailable_is_ready_and_degraded(env, tmp_path):
    env.setenv("MAIW_SANDBOX_MODE", "disabled")
    env.setenv("MAIW_SANDBOX_NAME", "maiw-test-sbx")
    env.setenv(
        "MAIW_OPENSHELL_BIN",
        _fake_openshell(tmp_path, [{"name": "maiw-test-sbx", "phase": "Stopped"}]),
    )
    code, body = await _ready()
    assert code == 200, body
    sbx = body["components"]["sandbox_runtime"]
    assert sbx["status"] == "degraded" and sbx["critical"] is False


async def test_optional_sandbox_not_configured_is_ready(env):
    code, body = await _ready()
    assert code == 200
    assert body["components"]["sandbox_runtime"]["status"] == "not_configured"


# ── provider ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("profile", ["reference", "reference_governed"])
async def test_provider_unavailable_is_non_critical(env, fake, mcp_servers, profile):
    if profile == "reference_governed":
        _governed(env, mcp_servers)
    fake.mode = "fail"
    code, body = await _ready()
    assert code == 200, body
    assert body["components"]["model_provider"]["critical"] is False


# ── model binding violation surfaces in readiness (NEW-P1-01 link) ───────────


async def test_unapproved_model_binding_is_not_ready(env, fake):
    env.setenv("NEMOTRON_SUPER_MODEL", "example-org/unapproved-model-x")
    install_gateway(fake)  # rebuild the registry from the new env
    code, body = await _ready()
    assert code == 503
    assert "model_gateway" in body["failed_components"]
