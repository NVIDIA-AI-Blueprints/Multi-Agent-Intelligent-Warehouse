# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.0.1 round 3 — NEW3-P1-01: the sandbox must not reach operational writes.

Third independent re-audit (PR #143 @ 86f3004): the sandbox, holding no
credential at all, called ``POST /api/v1/equipment/release``; the
DecisionEngine auto-approved it and the MCP write executed.  Root causes:
(1) the sandbox policy allowed every path on the API port, (2) the governed
write routes had no caller authentication, (3) executors were wired whenever
an MCP URL was set, even in the ``reference`` profile that reports governed
writes ``not_offered``.

Every test drives the canonical shipped app ``maiw_api.app:app`` through its
real lifespan.  Spies on the real runtime objects prove that a denied write
reaches neither the agent / DecisionEngine, nor the ActionExecutor, nor MCP.
"""

from __future__ import annotations

import json
import re
import secrets
from pathlib import Path

import pytest
import yaml

from tests.api.canonical_harness import (
    FakeNIM,
    canonical_env,
    install_gateway,
    running_canonical_app,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
WRITE_ROUTES = (
    "/api/v1/equipment/assign",
    "/api/v1/equipment/release",
    "/api/v1/equipment/maintenance",
)
BODIES = {
    "/api/v1/equipment/assign": {"asset_id": "FL-02", "assignee": "J-17"},
    "/api/v1/equipment/release": {"asset_id": "FL-01", "released_by": "sandbox"},
    "/api/v1/equipment/maintenance": {
        "asset_id": "FL-01",
        "maintenance_type": "preventive",
        "description": "x",
        "scheduled_by": "sandbox",
        "scheduled_for": "2026-12-01T09:00:00",
    },
}
# A closed local port: MCP is never actually contacted in these tests (and if
# it were, the spy below would record it before any connection attempt).
UNREACHABLE_MCP = "http://127.0.0.1:1/mcp"


@pytest.fixture
def fake_nim():
    fake = FakeNIM()
    yield fake
    fake.close()


@pytest.fixture
def governed_env(monkeypatch, tmp_path, fake_nim):
    """reference_governed + equipment MCP URL + fresh, distinct tokens."""
    inference_token = canonical_env(monkeypatch, tmp_path, fake_nim)
    operator_token = secrets.token_hex(32)
    monkeypatch.setenv("MAIW_DEPLOYMENT_PROFILE", "reference_governed")
    monkeypatch.setenv("MAIW_REQUIRED_MCP_DOMAINS", "equipment")
    monkeypatch.setenv("MAIW_MCP_SERVER_EQUIPMENT_URL", UNREACHABLE_MCP)
    monkeypatch.setenv("MAIW_OPERATOR_WRITE_TOKEN", operator_token)
    install_gateway(fake_nim)
    yield inference_token, operator_token, monkeypatch
    from maiw_models import reset_model_gateway

    reset_model_gateway()


class _Spies:
    """Count every call that would mean the write path was entered."""

    def __init__(self, rt) -> None:
        self.calls: dict[str, int] = {
            "agent": 0,
            "decision_engine": 0,
            "executor": 0,
            "mcp": 0,
        }
        agent = rt.equipment_agent
        for name in (
            "propose_equipment_assignment",
            "propose_equipment_release",
            "propose_schedule_maintenance",
        ):
            self._wrap(agent, name, "agent")
        self._wrap(rt.decision_engine, "evaluate", "decision_engine")
        if rt.equipment_executor is not None:
            self._wrap(rt.equipment_executor, "execute", "executor")
        if rt.mcp_client is not None:
            self._wrap(rt.mcp_client, "invoke", "mcp")

    def _wrap(self, obj, name, key) -> None:
        original = getattr(obj, name)
        spies = self

        if hasattr(original, "__call__"):
            import inspect

            if inspect.iscoroutinefunction(original):

                async def wrapper(*a, **kw):
                    spies.calls[key] += 1
                    return await original(*a, **kw)

            else:

                def wrapper(*a, **kw):
                    spies.calls[key] += 1
                    return original(*a, **kw)

            setattr(obj, name, wrapper)

    def total(self) -> int:
        return sum(self.calls.values())


# ── 1. Route inventory: every operational write route is authenticated ───────


def _routes():
    from maiw_api.app import app
    from maiw_api.route_policy import iter_mounted_routes

    return list(iter_mounted_routes(app))


def _route_dependencies(path: str, method: str = "POST") -> set[str]:
    """Names of the route-level dependency callables of a mounted route."""
    from fastapi.routing import APIRoute

    from maiw_api.app import app

    def walk(container, prefix=""):
        for route in getattr(container, "routes", []) or []:
            if isinstance(route, APIRoute):
                yield prefix + route.path, route
            elif hasattr(route, "original_router"):
                ctx = getattr(route, "include_context", None)
                yield from walk(
                    route.original_router, prefix + (getattr(ctx, "prefix", "") or "")
                )

    for full, route in walk(app):
        if full == path and method in route.methods:
            return {
                getattr(d.call, "__name__", "") for d in route.dependant.dependencies
            }
    raise AssertionError(f"route {method} {path} not mounted")


@pytest.mark.parametrize("path", WRITE_ROUTES)
def test_equipment_write_routes_require_operator_write_auth(path):
    deps = _route_dependencies(path)
    assert "require_operator_write" in deps
    assert "require_governed_writes_offered" in deps


def test_operator_auth_is_resolved_before_profile_gate_and_body():
    """Route dependencies run in declaration order, before body validation."""
    from fastapi.routing import APIRoute

    from maiw_api.routers.equipment import router

    for route in router.routes:
        if isinstance(route, APIRoute) and route.path in {
            p.replace("/api/v1", "/api/v1") for p in WRITE_ROUTES
        }:
            names = [d.call.__name__ for d in route.dependant.dependencies]
            assert names[:2] == [
                "require_operator_write",
                "require_governed_writes_offered",
            ], (route.path, names)


# ── 2. Sandbox credential matrix against the canonical app ───────────────────


def _variants(inference_token: str) -> dict[str, dict[str, str]]:
    return {
        "no_credential": {},
        "inference_token_internal_header": {"X-Maiw-Internal-Token": inference_token},
        "inference_token_as_operator_header": {
            "X-Maiw-Operator-Token": inference_token
        },
        "inference_token_as_bearer": {"Authorization": f"Bearer {inference_token}"},
        "wrong_operator_token": {"X-Maiw-Operator-Token": "x" * 64},
        "empty_operator_token": {"X-Maiw-Operator-Token": ""},
    }


_EXPECTED = {
    "no_credential": (403, "OPERATOR_WRITE_CREDENTIAL_REQUIRED"),
    "inference_token_internal_header": (403, "OPERATOR_WRITE_CREDENTIAL_REQUIRED"),
    "inference_token_as_operator_header": (401, "INVALID_OPERATOR_WRITE_CREDENTIAL"),
    "inference_token_as_bearer": (403, "OPERATOR_WRITE_CREDENTIAL_REQUIRED"),
    "wrong_operator_token": (401, "INVALID_OPERATOR_WRITE_CREDENTIAL"),
    "empty_operator_token": (403, "OPERATOR_WRITE_CREDENTIAL_REQUIRED"),
}


async def test_sandbox_credentials_cannot_reach_any_write_path(governed_env):
    """
    Every credential the sandbox holds (nothing; the inference token in every
    header) is denied on every equipment write route BEFORE the agent,
    DecisionEngine, ActionExecutor or MCP client is called.
    """
    inference_token, _, _ = governed_env
    async with running_canonical_app() as (app, client):
        rt = app.state.runtime
        assert rt.equipment_executor is not None  # governed profile: wired
        spies = _Spies(rt)
        for path in WRITE_ROUTES:
            for name, headers in _variants(inference_token).items():
                r = await client.post(path, json=BODIES[path], headers=headers)
                status, code = _EXPECTED[name]
                assert r.status_code == status, (path, name, r.text)
                assert r.json()["code"] == code, (path, name)
                # the token value is never echoed
                assert inference_token not in r.text
        # Invalid bodies are still denied by auth first (no 422 leak).
        r = await client.post(WRITE_ROUTES[1], content=b"not json")
        assert r.status_code == 403
    assert spies.calls == {"agent": 0, "decision_engine": 0, "executor": 0, "mcp": 0}


async def test_operator_credential_passes_auth_and_reaches_governance(governed_env):
    """The operator credential is accepted; the request then reaches the agent."""
    _, operator_token, _ = governed_env
    async with running_canonical_app() as (app, client):
        spies = _Spies(app.state.runtime)
        r = await client.post(
            "/api/v1/equipment/release",
            json=BODIES["/api/v1/equipment/release"],
            headers={"X-Maiw-Operator-Token": operator_token},
        )
        assert r.status_code not in (401, 403, 503), r.text
        # empty body with valid auth → 422 (auth passed, nothing proposed)
        r2 = await client.post(
            "/api/v1/equipment/release",
            json={},
            headers={"X-Maiw-Operator-Token": operator_token},
        )
        assert r2.status_code == 422
    assert spies.calls["agent"] == 1


# ── 3. Fail-closed configuration ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "setting", ["unset", "short", "placeholder", "equals_inference_token"]
)
async def test_write_auth_misconfiguration_fails_closed(governed_env, setting):
    inference_token, operator_token, monkeypatch = governed_env
    if setting == "unset":
        monkeypatch.delenv("MAIW_OPERATOR_WRITE_TOKEN", raising=False)
        presented = operator_token
    elif setting == "short":
        monkeypatch.setenv("MAIW_OPERATOR_WRITE_TOKEN", "short-token")
        presented = "short-token"
    elif setting == "placeholder":
        value = "your-strong-random-operator-write-token-min-32-chars"
        monkeypatch.setenv("MAIW_OPERATOR_WRITE_TOKEN", value)
        presented = value
    else:
        monkeypatch.setenv("MAIW_OPERATOR_WRITE_TOKEN", inference_token)
        presented = inference_token
    async with running_canonical_app() as (app, client):
        spies = _Spies(app.state.runtime)
        r = await client.post(
            "/api/v1/equipment/release",
            json=BODIES["/api/v1/equipment/release"],
            headers={"X-Maiw-Operator-Token": presented},
        )
        ready = await client.get("/api/v1/ready")
    assert r.status_code == 503
    assert r.json()["code"] == "OPERATOR_WRITE_AUTH_NOT_CONFIGURED"
    assert spies.total() == 0
    gwp = ready.json()["components"]["governed_write_path"]
    assert gwp["status"] == "failed"
    assert "operator_write_auth" in gwp["missing"]
    assert gwp["operator_write_auth"]["configured"] is False


# ── 4. Profile/behaviour agreement (reference + optional MCP URL) ────────────


async def test_reference_profile_with_mcp_url_builds_no_executor(
    monkeypatch, tmp_path, fake_nim
):
    """
    Audit residual: in ``reference`` with an equipment MCP URL set, writes
    executed while readiness said ``not_offered``.  Now no executor is built,
    and the write route refuses after authentication.
    """
    canonical_env(monkeypatch, tmp_path, fake_nim)
    operator_token = secrets.token_hex(32)
    monkeypatch.setenv("MAIW_DEPLOYMENT_PROFILE", "reference")
    monkeypatch.setenv("MAIW_MCP_SERVER_EQUIPMENT_URL", UNREACHABLE_MCP)
    monkeypatch.setenv("MAIW_MCP_SERVER_LABOR_URL", UNREACHABLE_MCP)
    monkeypatch.setenv("MAIW_MCP_SERVER_WAVE_URL", UNREACHABLE_MCP)
    monkeypatch.setenv("MAIW_OPERATOR_WRITE_TOKEN", operator_token)
    install_gateway(fake_nim)
    try:
        async with running_canonical_app() as (app, client):
            rt = app.state.runtime
            assert rt.mcp_equipment_available is True
            assert rt.equipment_executor is None
            assert rt.labor_executor is None
            assert rt.wave_executor is None
            spies = _Spies(rt)
            denied = await client.post(
                "/api/v1/equipment/release", json=BODIES["/api/v1/equipment/release"]
            )
            authed = await client.post(
                "/api/v1/equipment/release",
                json=BODIES["/api/v1/equipment/release"],
                headers={"X-Maiw-Operator-Token": operator_token},
            )
            ready = await client.get("/api/v1/ready")
    finally:
        from maiw_models import reset_model_gateway

        reset_model_gateway()
    assert denied.status_code == 403
    assert authed.status_code == 503
    assert authed.json()["code"] == "GOVERNED_WRITES_NOT_OFFERED"
    assert spies.total() == 0
    assert ready.json()["components"]["governed_write_path"]["status"] == "not_offered"


# ── 5. OpenShell policy: L7 rule restricts the API port to inference ─────────


def _rendered_policy() -> dict:
    tmpl = (
        REPO_ROOT / "deploy/openshell/maiw-inference-only.policy.yaml.tmpl"
    ).read_text()
    rendered = tmpl.replace("__MAIW_API_HOST_IP__", "10.0.0.5").replace(
        "__MAIW_API_PORT__", "18001"
    )
    return yaml.safe_load(rendered)


def test_sandbox_policy_allows_only_post_inference_on_api_port():
    policy = _rendered_policy()
    nets = policy["network_policies"]
    assert list(nets) == ["maiw_inference_only"]
    endpoints = nets["maiw_inference_only"]["endpoints"]
    assert len(endpoints) == 1
    ep = endpoints[0]
    assert ep["host"] == "10.0.0.5" and ep["port"] == 18001
    assert ep["protocol"] == "rest" and ep["enforcement"] == "enforce"
    # round 2 granted `access: full` (every path); round 3 must not
    assert "access" not in ep
    assert ep["rules"] == [{"allow": {"method": "POST", "path": "/api/v1/inference"}}]


def test_sandbox_policy_template_documents_layered_enforcement():
    text = (
        REPO_ROOT / "deploy/openshell/maiw-inference-only.policy.yaml.tmpl"
    ).read_text()
    active = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    assert not any("access:" in ln for ln in active)
    assert "X-Maiw-Operator-Token" in text


# ── 6. Credential isolation: tooling never hands the write token out ─────────


def test_sandbox_script_never_passes_operator_token_into_sandbox():
    script = (REPO_ROOT / "scripts/setup/reference_sandbox.sh").read_text()
    # The only value piped into the sandbox is the inference token.
    piped = re.findall(r"printf '%s\\n' \"\$(\w+)\"", script)
    assert piped == ["MAIW_INFERENCE_INTERNAL_TOKEN"]
    # MAIW_OPERATOR_WRITE_TOKEN appears only in the host-side digest check.
    for line in script.splitlines():
        if "MAIW_OPERATOR_WRITE_TOKEN" in line:
            assert "openshell" not in line


def test_in_sandbox_probe_checks_write_denial_and_exits_on_violation():
    probe = (
        REPO_ROOT / "scripts/qualification/in_sandbox_canonical_probe.py"
    ).read_text()
    for path in WRITE_ROUTES:
        assert path in probe
    assert "operational_writes_all_denied" in probe
    assert "env_value_digests" in probe
    assert "sys.exit(0 if ok else 1)" in probe


def test_ui_bundle_never_holds_the_operator_credential():
    web = REPO_ROOT / "src/ui/web"
    offenders = []
    for path in (web / "src").rglob("*"):
        if path.suffix in {".ts", ".tsx", ".js", ".jsx"} and path.is_file():
            text = path.read_text(errors="ignore")
            if re.search(r"REACT_APP_\w*(OPERATOR|WRITE)\w*TOKEN", text):
                offenders.append(str(path))
            # the header may be named in comments, but no browser code may set it
            sets_header = re.search(
                r"""["']x-maiw-operator-token["']\s*[:,\]]""", text, re.I
            )
            if sets_header and path.name != "setupProxy.js":
                offenders.append(str(path))
    assert offenders == []
    proxy = (web / "src/setupProxy.js").read_text()
    # the dev proxy strips any browser-supplied operator header
    assert "removeHeader('x-maiw-operator-token')" in proxy
    assert "process.env.MAIW_UI_OPERATOR_WRITE_TOKEN" in proxy


def test_env_example_documents_operator_write_token():
    text = (REPO_ROOT / ".env.example").read_text()
    assert re.search(r"^#\s*MAIW_OPERATOR_WRITE_TOKEN=", text, re.M)
    runbook = (
        REPO_ROOT / "docs/operations/REFERENCE_DEPLOYMENT_RUNBOOK.md"
    ).read_text()
    assert "MAIW_OPERATOR_WRITE_TOKEN" in runbook
    preflight = (REPO_ROOT / "scripts/preflight_reference_deployment.sh").read_text()
    assert "operator_write_auth_status" in preflight


def test_operator_write_auth_status_rules():
    from maiw_api.write_auth import operator_write_auth_status

    good = secrets.token_hex(32)
    assert operator_write_auth_status({}).configured is False
    assert (
        operator_write_auth_status({"MAIW_OPERATOR_WRITE_TOKEN": "x"}).configured
        is False
    )
    assert (
        operator_write_auth_status(
            {"MAIW_OPERATOR_WRITE_TOKEN": good, "MAIW_INFERENCE_INTERNAL_TOKEN": good}
        ).configured
        is False
    )
    status = operator_write_auth_status(
        {
            "MAIW_OPERATOR_WRITE_TOKEN": good,
            "MAIW_INFERENCE_INTERNAL_TOKEN": secrets.token_hex(32),
        }
    )
    assert status.configured is True
    assert good not in json.dumps(status.as_dict())
