# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.0.1 canonical shipped-app suite.

Every test here exercises ``maiw_api.app:app`` — the composition root started by
``scripts/start_reference_deployment.sh``, ``Dockerfile.backend`` and the
runbook — through its real lifespan. Nothing is qualified through the legacy
``src/api/app.py``. The tests are permanent regressions for the five P1
findings of the v2.0.0 independent audit (PR #142):

    P1-01  legacy /api/v1/chat could mutate the warehouse without governance
    P1-02  POST /api/v1/inference was not mounted on the shipped app
    P1-03  durable ProcedureStateStore / GovernanceInbox never constructed
    P1-04  /api/v1/ready reported READY with persistence / DB unavailable
    P1-05  document pipeline bypassed ModelGateway and mocked APPROVE

Spec §31 required tests → test names:
     1 inference exists                      test_p1_02_inference_route_is_mounted
     2 inference auth fail-closed            test_p1_02_inference_auth_*
     3 forbidden routing fields rejected     test_p1_02_forbidden_routing_field_rejected_422
     4 valid inference reaches ModelGateway  test_p1_02_valid_inference_reaches_canonical_gateway
     5 chat cannot directly mutate           test_p1_01_audit_chat_scenario_cannot_mutate
     6 operational mutation governed         test_p1_01_mutating_route_inventory_is_exactly_classified
                                             test_p1_01_operational_writes_go_through_decision_engine
     7 ProcedureStateStore file-backed       test_p1_03_reference_profile_is_file_backed
     8 GovernanceInbox file-backed           test_p1_03_reference_profile_is_file_backed
     9 restart preserves procedure           test_p1_03_restart_preserves_procedure_*
    10 restart preserves governance state    test_p1_03_governance_replay_after_restart_is_dropped
    11 /ready degrades on persistence loss   test_p1_04_ready_fails_when_*
    12 /ready degrades on DB loss            test_p1_04_ready_fails_when_database_unreachable
    13 document path uses ModelGateway       test_p1_05_document_judge_uses_canonical_gateway
    14 provider failure ≠ mock approval      test_p1_05_*_never_approve
    15 approved family applies to documents  test_p1_05_document_vision_has_no_eligible_model
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests.api.canonical_harness import (
    APPROVED_GENERATIONS,
    FakeNIM,
    FakeWaveWorld,
    ProofSopAExecutor,
    canonical_env,
    governance_input_for,
    install_gateway,
    proof_sop_a_inputs,
    running_canonical_app,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
READ_ONLY = {"GET", "HEAD", "OPTIONS"}


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def fake_nim():
    fake = FakeNIM(
        content=json.dumps(
            {
                "overall_score": 3.9,
                "decision": "REVIEW_REQUIRED",
                "confidence": 0.7,
                "issues_found": [],
                "reasoning": "fake judge reply",
            }
        )
    )
    yield fake
    fake.close()


@pytest.fixture
def canonical(monkeypatch, tmp_path, fake_nim):
    """Environment for one canonical-app test; returns (token, fake, root)."""
    token = canonical_env(monkeypatch, tmp_path, fake_nim)
    install_gateway(fake_nim)
    yield token, fake_nim, tmp_path / "maiw"
    from maiw_models import reset_model_gateway

    reset_model_gateway()


@pytest.fixture
def real_asyncpg(monkeypatch):
    """
    tests/api/conftest.py stubs asyncpg with a MagicMock for infra-free tests.
    The opt-in Postgres tests need the real driver: drop the stub for the
    duration of the test (monkeypatch restores it afterwards).
    """
    import importlib

    if isinstance(sys.modules.get("asyncpg"), MagicMock):
        monkeypatch.delitem(sys.modules, "asyncpg")
    try:
        module = importlib.import_module("asyncpg")
    except ImportError:  # pragma: no cover
        pytest.skip("asyncpg not installed")
    if isinstance(module, MagicMock):  # pragma: no cover
        pytest.skip("asyncpg is stubbed in this interpreter")
    return module


def _mounted():
    from maiw_api.app import app
    from maiw_api.route_policy import iter_mounted_routes

    return [(m, p, e) for m, p, e in iter_mounted_routes(app)]


# ═════════════════════════════════════════════════════════════════════════════
# Composition root identity
# ═════════════════════════════════════════════════════════════════════════════


def test_shipped_entrypoint_is_maiw_api_app():
    """Deployment surfaces start maiw_api.app:app — never src.api.app:app."""
    from maiw_api.app import app
    from maiw_api.lifespan import lifespan

    assert app.router.lifespan_context is not None
    assert lifespan.__module__ == "maiw_api.lifespan"
    for rel in (
        "Dockerfile.backend",
        "scripts/start_reference_deployment.sh",
        "scripts/restart_reference_deployment.sh",
    ):
        text = (REPO_ROOT / rel).read_text()
        assert "src.api.app:app" not in text, rel
    assert "maiw_api.app:app" in (REPO_ROOT / "Dockerfile.backend").read_text()
    assert (
        "maiw_api.app:app"
        in (REPO_ROOT / "scripts/start_reference_deployment.sh").read_text()
    )


# ═════════════════════════════════════════════════════════════════════════════
# P1-01 — no ungoverned mutation path in the shipped app
# ═════════════════════════════════════════════════════════════════════════════

# Independent, reviewed classification of EVERY non-read-only route the shipped
# app may expose. A new mutating route fails this test until it is classified.
EXPECTED_MUTATING_ROUTES: dict[tuple[str, str], str] = {
    # governed: agent PROPOSES → DecisionEngine → ActionExecutor only if APPROVED
    ("POST", "/api/v1/equipment/assign"): "governed",
    ("POST", "/api/v1/equipment/release"): "governed",
    ("POST", "/api/v1/equipment/maintenance"): "governed",
    ("POST", "/api/v1/demo/analyze"): "governed",
    ("POST", "/api/v1/demo/approve"): "governed",
    ("POST", "/api/v1/demo/reject"): "governed",
    ("POST", "/api/v1/demo/reconcile"): "governed-reconcile-read-only",
    ("POST", "/api/v1/copilot/turn"): "governed",
    # simulation controls — 503 unless MAIW_DEMO_MODE (no real warehouse)
    ("POST", "/api/v1/demo/scenario/{name}/start"): "demo-simulation",
    ("POST", "/api/v1/demo/scenario/pause"): "demo-simulation",
    ("POST", "/api/v1/demo/scenario/resume"): "demo-simulation",
    ("POST", "/api/v1/demo/scenario/reset"): "demo-simulation",
    ("POST", "/api/v1/demo/tick"): "demo-simulation",
    ("POST", "/api/v1/demo/inject"): "demo-simulation",
    # bounded inference — ModelGateway only, internal token, no governance below
    ("POST", "/api/v1/inference"): "bounded-inference",
    # identity management — own auth dependencies (admin / current user)
    ("POST", "/api/v1/auth/register"): "identity",
    ("POST", "/api/v1/auth/login"): "identity",
    ("POST", "/api/v1/auth/refresh"): "identity",
    ("PUT", "/api/v1/auth/me"): "identity",
    ("POST", "/api/v1/auth/change-password"): "identity",
    ("PUT", "/api/v1/auth/users/{user_id}"): "identity",
    # document workflow state — no warehouse mutation; inference via ModelGateway
    ("POST", "/api/v1/document/upload"): "document-workflow",
    ("POST", "/api/v1/document/approve/{document_id}"): "document-workflow",
    ("POST", "/api/v1/document/reject/{document_id}"): "document-workflow",
}


def test_p1_01_mutating_route_inventory_is_exactly_classified():
    mutating = {(m, p) for m, p, _ in _mounted() if m not in READ_ONLY}
    unexpected = mutating - set(EXPECTED_MUTATING_ROUTES)
    missing = set(EXPECTED_MUTATING_ROUTES) - mutating
    assert not unexpected, f"unclassified mutating routes: {sorted(unexpected)}"
    assert not missing, f"classified routes no longer mounted: {sorted(missing)}"


def test_p1_01_legacy_chat_and_reasoning_not_mounted():
    paths = {p for _, p, _ in _mounted()}
    modules = {getattr(e, "__module__", "") for _, _, e in _mounted()}
    assert not any(p == "/api/v1/chat" or p.startswith("/api/v1/chat/") for p in paths)
    assert not any(p.startswith("/api/v1/reasoning") for p in paths)
    assert not any(p.startswith("/api/v1/mcp/tools") for p in paths)
    for forbidden in (
        "src.api.routers.chat",
        "src.api.routers.reasoning",
        "src.api.routers.mcp",
    ):
        assert forbidden not in modules


def test_p1_01_legacy_routers_mounted_read_only():
    """Legacy src.api.routers expose only GET/HEAD, except reviewed routes."""
    allowed_legacy_mutations = {
        k
        for k, v in EXPECTED_MUTATING_ROUTES.items()
        if v in {"bounded-inference", "identity", "document-workflow"}
    }
    for method, path, endpoint in _mounted():
        module = getattr(endpoint, "__module__", "")
        if module.startswith("src.api.routers") and method not in READ_ONLY:
            assert (method, path) in allowed_legacy_mutations, (method, path, module)


def test_p1_01_import_graph_excludes_legacy_agent_tool_layer():
    """
    Importing the shipped app must not import the legacy chat stack
    (planner graph → MCP equipment agent → ToolDiscoveryService).
    Checked in a fresh interpreter so other tests cannot mask it.
    """
    code = (
        "import sys, maiw_api.app\n"
        "bad=[m for m in ('src.api.routers.chat','src.api.routers.reasoning',"
        "'src.api.graphs.mcp_integrated_planner_graph',"
        "'src.api.agents.inventory.mcp_equipment_agent',"
        "'src.api.services.mcp.tool_discovery') if m in sys.modules]\n"
        "print('BAD=' + ','.join(bad))\n"
    )
    env = {
        **os.environ,
        "DATABASE_URL": "postgresql://warehouse:ci_placeholder@127.0.0.1:1/warehouse",
    }
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    line = [ln for ln in proc.stdout.splitlines() if ln.startswith("BAD=")][-1]
    assert line == "BAD=", line


class _FakeAssetTools:
    """Stateful stand-in for the SQL EquipmentAssetTools adapter."""

    def __init__(self):
        self.state = {"FL-01": "available"}
        self.writes: list[tuple] = []

    async def get_equipment_status(self, asset_id=None, **_kw):
        return {
            "equipment": [
                {"asset_id": a, "status": s, "type": "forklift", "zone": "A"}
                for a, s in self.state.items()
                if asset_id in (None, a)
            ]
        }

    async def get_equipment_telemetry(self, *a, **k):
        return {"telemetry": []}

    async def get_maintenance_schedule(self, *a, **k):
        return {"maintenance_schedule": []}

    async def assign_equipment(self, asset_id, assignee, *a, **k):
        self.writes.append(("assign", asset_id, assignee))
        self.state[asset_id] = "assigned"
        return {"success": True}

    async def release_equipment(self, asset_id, *a, **k):
        self.writes.append(("release", asset_id))
        self.state[asset_id] = "available"
        return {"success": True}


async def test_p1_01_audit_chat_scenario_cannot_mutate(canonical, monkeypatch):
    """
    §5 reproduction of the audit scenario against the shipped app: FL-01 is
    available; the exact audit question (and an explicit assignment request)
    is sent to every chat-like surface. Nothing may assign equipment.
    """
    import src.api.agents.inventory.equipment_asset_tools as eat
    import src.api.services.mcp.tool_discovery as td

    fake = _FakeAssetTools()

    async def _factory():
        return fake

    monkeypatch.setattr(eat, "get_equipment_asset_tools", _factory)

    class_calls: list = []

    async def _spy_assign(self, *a, **k):  # any real SQL adapter instance
        class_calls.append(("EquipmentAssetTools.assign_equipment", a, k))
        return {"success": False}

    async def _spy_execute_tool(self, *a, **k):
        class_calls.append(("ToolDiscoveryService.execute_tool", a, k))
        return None

    monkeypatch.setattr(eat.EquipmentAssetTools, "assign_equipment", _spy_assign)
    monkeypatch.setattr(td.ToolDiscoveryService, "execute_tool", _spy_execute_tool)

    question = "Show me the status of forklift FL-01"
    command = "Assign forklift FL-01 to operator J-17 now"
    async with running_canonical_app() as (app, client):
        r_chat = await client.post(
            "/api/v1/chat", json={"message": question, "session_id": "audit"}
        )
        r_chat2 = await client.post(
            "/api/v1/chat", json={"message": command, "session_id": "audit"}
        )
        r_cop = await client.post("/api/v1/copilot/turn", json={"message": question})
        r_cop2 = await client.post("/api/v1/copilot/turn", json={"message": command})
        r_reason = await client.post(
            "/api/v1/reasoning/chat-with-reasoning", json={"query": command}
        )
        await asyncio.sleep(0.5)  # legacy planner used to finish in background

    assert r_chat.status_code == 404
    assert r_chat2.status_code == 404
    assert r_reason.status_code == 404
    assert r_cop.status_code in (200, 503)
    assert r_cop2.status_code in (200, 503)
    assert fake.state["FL-01"] == "available", fake.writes
    assert fake.writes == []
    assert class_calls == []


@pytest.mark.skipif(
    not os.getenv("MAIW_TEST_PG_DSN"),
    reason="set MAIW_TEST_PG_DSN to a DISPOSABLE Postgres loaded with the MAIW schema",
)
async def test_p1_01_audit_chat_scenario_against_postgres(
    canonical, monkeypatch, real_asyncpg
):
    """
    The audit's exact P1-01 reproduction with the real SQL adapter: FL-01 is
    set to 'available' in a disposable database, the audit question and an
    explicit assignment request are sent to the shipped app, and the
    equipment_assets / equipment_assignments rows must be unchanged.
    """
    from urllib.parse import urlparse

    asyncpg = real_asyncpg

    dsn = os.environ["MAIW_TEST_PG_DSN"]
    u = urlparse(dsn)
    for key, value in {
        "DATABASE_URL": dsn,
        "POSTGRES_HOST": u.hostname or "127.0.0.1",
        "POSTGRES_PORT": str(u.port or 5432),
        "POSTGRES_USER": u.username or "warehouse",
        "POSTGRES_PASSWORD": u.password or "",
        "POSTGRES_DB": (u.path or "/warehouse").lstrip("/"),
        "PGHOST": u.hostname or "127.0.0.1",
        "PGPORT": str(u.port or 5432),
    }.items():
        monkeypatch.setenv(key, value)

    conn = await asyncpg.connect(dsn)
    try:
        if not await conn.fetchval(
            "select to_regclass('public.equipment_assets') is not null"
        ):
            pytest.skip("MAIW schema not loaded in MAIW_TEST_PG_DSN")
        await conn.execute(
            "update equipment_assets set status='available', owner_user=null "
            "where asset_id='FL-01'"
        )

        async def snapshot():
            row = await conn.fetchrow(
                "select status, owner_user from equipment_assets where asset_id='FL-01'"
            )
            n = await conn.fetchval("select count(*) from equipment_assignments")
            return (dict(row) if row else None, n)

        before = await snapshot()
        assert before[0] is not None and before[0]["status"] == "available"
        async with running_canonical_app() as (_, client):
            for msg in (
                "Show me the status of forklift FL-01",
                "Assign forklift FL-01 to operator J-17 now",
            ):
                r = await client.post(
                    "/api/v1/chat", json={"message": msg, "session_id": "audit"}
                )
                assert r.status_code == 404
                await client.post("/api/v1/copilot/turn", json={"message": msg})
            await asyncio.sleep(5)  # the legacy planner wrote asynchronously
        after = await snapshot()
    finally:
        await conn.close()
    assert after == before, f"warehouse state changed: {before} -> {after}"


async def test_p1_01_operational_writes_go_through_decision_engine(
    canonical, monkeypatch
):
    """
    The shipped equipment write route (POST /api/v1/equipment/assign) only
    proposes; the ActionExecutor runs only for a DecisionEngine APPROVED
    result, with exactly the proposal/decision the agent produced. The SQL
    adapter is never the write path. (Agent-level DecisionEngine behaviour is
    covered by tests/api/test_equipment_router.py and the package suites.)
    """
    import src.api.agents.inventory.equipment_asset_tools as eat

    fake = _FakeAssetTools()

    async def _factory():
        return fake

    monkeypatch.setattr(eat, "get_equipment_asset_tools", _factory)

    proposal, decision = object(), object()
    executed: list = []

    class _Outcome:
        value = "EXECUTED"

    class _ExecResult:
        executed = True
        execution_id = "exec-1"
        outcome = _Outcome()

    class _SpyExecutor:
        async def execute(self, p, d, **kw):
            executed.append((p, d))
            return _ExecResult()

    class _StubAgent:
        def __init__(self, status):
            self.status = status

        async def propose_equipment_assignment(self, **kw):
            return {
                "status": self.status,
                "proposal_id": "p-1",
                "decision_id": "d-1",
                "_proposal": proposal,
                "_decision": decision,
            }

    async with running_canonical_app() as (app, client):
        rt = app.state.runtime
        rt.equipment_executor = _SpyExecutor()
        for status in ("requires_human_approval", "rejected", "requires_fresh_state"):
            rt.equipment_agent = _StubAgent(status)
            r = await client.post(
                "/api/v1/equipment/assign",
                json={"asset_id": "FL-01", "assignee": "J-17"},
            )
            assert r.status_code == 200, r.text
            assert executed == [], status
        rt.equipment_agent = _StubAgent("approved")
        r = await client.post(
            "/api/v1/equipment/assign", json={"asset_id": "FL-01", "assignee": "J-17"}
        )
    assert r.status_code == 200
    assert executed == [(proposal, decision)]
    assert fake.writes == []


async def test_p1_01_demo_simulation_routes_inactive_outside_demo_mode(canonical):
    from maiw_api.demo.controller import reset_demo_controller

    reset_demo_controller()
    async with running_canonical_app() as (_, client):
        r1 = await client.post("/api/v1/demo/inject", json={"event_type": "low_stock"})
        r2 = await client.post("/api/v1/demo/tick", json={"seconds": 60})
    assert r1.status_code == 503
    assert r2.status_code == 503


async def test_p1_01_legacy_write_routes_not_reachable(canonical):
    """Representative legacy writes the audit listed now 404/405."""
    async with running_canonical_app() as (_, client):
        cases = [
            ("POST", "/api/v1/inventory/items", {"sku": "X"}),
            ("PUT", "/api/v1/inventory/items/X", {"quantity": 1}),
            ("POST", "/api/v1/operations/tasks", {"kind": "pick"}),
            ("POST", "/api/v1/operations/tasks/1/assign", {"assignee": "x"}),
            ("POST", "/api/v1/safety/incidents", {"severity": "low"}),
            ("POST", "/api/v1/wms/connections", {"connection_id": "x"}),
            ("POST", "/api/v1/migrations/migrate", None),
            ("POST", "/api/v1/migrations/rollback/001", None),
            ("POST", "/api/v1/training/start", {"training_type": "basic"}),
            ("POST", "/api/v1/mcp/tools/execute", {"tool": "assign_equipment"}),
            ("POST", "/api/v1/document/search", {"query": "x"}),
            ("POST", "/api/v1/document/validate/abc", {}),
        ]
        for method, path, payload in cases:
            r = await client.request(method, path, json=payload)
            assert r.status_code in (404, 405), (method, path, r.status_code)


# ═════════════════════════════════════════════════════════════════════════════
# P1-02 — bounded inference endpoint on the shipped app
# ═════════════════════════════════════════════════════════════════════════════

_VALID = {
    "task": "canonical_inference_probe",
    "messages": [{"role": "user", "content": "Say OK."}],
    "deadline_ms": 20000,
}


def test_p1_02_inference_route_is_mounted():
    from maiw_api.app import app

    assert ("POST", "/api/v1/inference") in {(m, p) for m, p, _ in _mounted()}
    assert "/api/v1/inference" in app.openapi()["paths"]


@pytest.mark.parametrize(
    "header",
    [None, "wrong-token-" + "0" * 20, ""],
    ids=["no-token", "wrong-token", "empty-token"],
)
async def test_p1_02_inference_auth_rejects_bad_token(canonical, header):
    token, fake, _ = canonical
    headers = {} if header is None else {"X-Maiw-Internal-Token": header}
    async with running_canonical_app() as (_, client):
        r = await client.post("/api/v1/inference", json=_VALID, headers=headers)
    assert r.status_code == 401
    assert fake.chat_requests() == []


async def test_p1_02_inference_auth_fail_closed_when_unconfigured(
    canonical, monkeypatch
):
    _, fake, _ = canonical
    monkeypatch.delenv("MAIW_INFERENCE_INTERNAL_TOKEN", raising=False)
    monkeypatch.delenv("MAIW_INFERENCE_ALLOW_UNAUTHENTICATED", raising=False)
    async with running_canonical_app() as (_, client):
        r = await client.post("/api/v1/inference", json=_VALID)
    assert r.status_code == 503
    assert fake.chat_requests() == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("provider_url", "http://evil.invalid/v1"),
        ("base_url", "http://evil.invalid"),
        ("api_key", "x"),
        ("api_key_env_var", "HOME"),
        ("deployment_endpoint", "http://evil.invalid"),
        ("force_model_id", "meta/llama-3.1-8b-instruct"),
        ("model_id", "meta/llama-3.1-8b-instruct"),
        ("deployment_mode", "local_nim"),
    ],
)
async def test_p1_02_forbidden_routing_field_rejected_422(canonical, field, value):
    token, fake, _ = canonical
    async with running_canonical_app() as (_, client):
        r = await client.post(
            "/api/v1/inference",
            json={**_VALID, field: value},
            headers={"X-Maiw-Internal-Token": token},
        )
    assert r.status_code == 422, r.text
    assert fake.chat_requests() == []


@pytest.mark.parametrize(
    "field", ["model", "provider", "routing_hints", "endpoint", "modelId"]
)
async def test_p1_02_unknown_field_rejected_422(canonical, field):
    token, fake, _ = canonical
    async with running_canonical_app() as (_, client):
        r = await client.post(
            "/api/v1/inference",
            json={**_VALID, field: "meta/llama-3.1-70b-instruct"},
            headers={"X-Maiw-Internal-Token": token},
        )
    assert r.status_code == 422, r.text
    assert fake.chat_requests() == []


async def test_p1_02_valid_inference_reaches_canonical_gateway(canonical):
    token, fake, _ = canonical
    async with running_canonical_app() as (app, client):
        r = await client.post(
            "/api/v1/inference", json=_VALID, headers={"X-Maiw-Internal-Token": token}
        )
        gateway = app.state.runtime.model_gateway
        body = r.json()
        assert r.status_code == 200, body
        sent = fake.chat_requests()
        assert len(sent) == 1
        # The provider received the model PolicyFilter selected from the registry.
        assert sent[0]["model"] == body["model_id"]
        cap = gateway.registry.get_by_id(body["model_id"])
        assert cap is not None and cap.generation in APPROVED_GENERATIONS
        assert body["route"]["approved_family"] is True
        assert body["route"]["generation"] in APPROVED_GENERATIONS
        assert body["content"] == fake.content
        assert sent[0]["auth_present"] is True
        # The canonical route uses the runtime's gateway singleton.
        from maiw_models import get_model_gateway

        assert await get_model_gateway() is gateway


async def test_p1_02_provider_failure_is_typed_not_mocked(canonical):
    token, fake, _ = canonical
    fake.mode = "fail"
    async with running_canonical_app() as (_, client):
        r = await client.post(
            "/api/v1/inference", json=_VALID, headers={"X-Maiw-Internal-Token": token}
        )
    assert r.status_code == 503
    assert r.json()["code"] in ("PROVIDER_FAILURE", "MODEL_UNAVAILABLE")


async def test_p1_02_image_request_has_no_eligible_approved_model(canonical):
    token, fake, _ = canonical
    async with running_canonical_app() as (_, client):
        r = await client.post(
            "/api/v1/inference",
            json={**_VALID, "modality": "image"},
            headers={"X-Maiw-Internal-Token": token},
        )
    assert r.status_code == 503
    assert r.json()["code"] == "MODEL_UNAVAILABLE"
    assert fake.chat_requests() == []


# ═════════════════════════════════════════════════════════════════════════════
# P1-03 — durable persistence wired into the runtime
# ═════════════════════════════════════════════════════════════════════════════


async def test_p1_03_reference_profile_is_file_backed(canonical):
    from integrations.nemoclaw.boundary_contracts import JsonFileGovernanceInbox
    from maiw_agents.sop_engine.state_store import JsonFileProcedureStateStore

    _, _, root = canonical
    async with running_canonical_app() as (app, _):
        rt = app.state.runtime
        assert isinstance(rt.procedure_store, JsonFileProcedureStateStore)
        assert isinstance(rt.governance_inbox, JsonFileGovernanceInbox)
        assert rt.procedure_host is not None
        assert rt.procedure_host.store is rt.procedure_store
        assert rt.procedure_host.inbox is rt.governance_inbox
        assert rt.persistence.config.procedures_dir == root / "procedures"
        assert rt.persistence.config.governance_dir == root / "governance"
    assert (root / "procedures").is_dir()
    assert (root / "governance").is_dir()


async def test_p1_03_memory_profile_requires_explicit_opt_in(canonical, monkeypatch):
    from maiw_agents.sop_engine.state_store import InMemoryProcedureStateStore

    monkeypatch.setenv("MAIW_PERSISTENCE_MODE", "memory")
    async with running_canonical_app() as (app, client):
        assert isinstance(
            app.state.runtime.procedure_store, InMemoryProcedureStateStore
        )
        ready = (await client.get("/api/v1/ready")).json()
    assert ready["components"]["persistence"]["durable"] is False


async def test_p1_03_persistence_root_is_consumed_by_runtime(canonical):
    """A procedure run through the runtime writes under MAIW_PERSISTENCE_ROOT."""
    _, _, root = canonical
    definition, sop, context = proof_sop_a_inputs(REPO_ROOT)
    async with running_canonical_app() as (app, client):
        state = await app.state.runtime.procedure_host.start(
            definition=definition,
            sop=sop,
            agent_task_id="task-root-probe",
            context=context,
            executor=ProofSopAExecutor(),
            warehouse_state_snapshot=FakeWaveWorld(),
        )
        listed = (await client.get("/api/v1/procedures")).json()
    path = root / "procedures" / f"{state.procedure_execution_id}.json"
    assert path.is_file()
    assert json.loads(path.read_text())["status"] == "waiting_for_governance"
    assert listed["count"] == 1
    assert listed["procedures"][0]["procedure_execution_id"] == (
        state.procedure_execution_id
    )


async def test_p1_03_restart_preserves_procedure_in_process(canonical):
    """start → WAITING_FOR_GOVERNANCE → stop → start: same state, no replay."""
    definition, sop, context = proof_sop_a_inputs(REPO_ROOT)
    async with running_canonical_app() as (app, _):
        paused = await app.state.runtime.procedure_host.start(
            definition=definition,
            sop=sop,
            agent_task_id="task-restart",
            context=context,
            executor=ProofSopAExecutor(fail_first=("establish_state",)),
            warehouse_state_snapshot=FakeWaveWorld(),
        )
    assert paused.status.value == "waiting_for_governance"
    assert paused.attempt_by_step["establish_state"] == 2

    async with running_canonical_app() as (app, client):
        host = app.state.runtime.procedure_host
        restored = await host.load(paused.procedure_execution_id)
        assert restored is not None
        assert restored.status.value == "waiting_for_governance"
        assert restored.revision == paused.revision
        assert restored.current_step_id == "submit"
        assert restored.attempt_by_step == paused.attempt_by_step
        # A waiting procedure is not re-run on resume (no duplicate recommendation)
        executor = ProofSopAExecutor()
        same = await host.resume(
            paused.procedure_execution_id,
            definition=definition,
            sop=sop,
            context=context,
            executor=executor,
        )
        assert executor.steps == []
        assert same.revision == paused.revision
        got = await client.get(f"/api/v1/procedures/{paused.procedure_execution_id}")
        assert got.status_code == 200
        assert got.json()["waiting_for_governance"] is True


async def test_p1_03_governance_replay_after_restart_is_dropped(canonical):
    """Governance accepted once; a replay after restart is a recorded duplicate."""
    _, _, root = canonical
    definition, sop, context = proof_sop_a_inputs(REPO_ROOT)
    async with running_canonical_app() as (app, _):
        paused = await app.state.runtime.procedure_host.start(
            definition=definition,
            sop=sop,
            agent_task_id="task-governance",
            context=context,
            executor=ProofSopAExecutor(),
            warehouse_state_snapshot=FakeWaveWorld(),
        )
    gov = governance_input_for(paused)
    world = FakeWaveWorld()
    world.resolve_risk(remaining=0)

    async with running_canonical_app() as (app, _):
        host = app.state.runtime.procedure_host
        first = await host.apply_governance(
            gov,
            definition=definition,
            sop=sop,
            context=context,
            executor=ProofSopAExecutor(),
            warehouse_state_snapshot=world,
        )
        assert first.applied and not first.duplicate
        executor = ProofSopAExecutor()
        done = await host.resume(
            paused.procedure_execution_id,
            definition=definition,
            sop=sop,
            context=context,
            executor=executor,
            warehouse_state_snapshot=world,
        )
        assert done.status.value == "completed"
        assert executor.steps == ["observe"]

    async with running_canonical_app() as (app, _):
        host = app.state.runtime.procedure_host
        executor = ProofSopAExecutor()
        replay = await host.apply_governance(
            gov,
            definition=definition,
            sop=sop,
            context=context,
            executor=executor,
            warehouse_state_snapshot=world,
        )
        assert replay.applied is False and replay.duplicate is True
        assert executor.steps == []
        assert replay.state.status.value == "completed"
        assert replay.state.revision == done.revision

    ledger = (root / "governance" / "governance_inbox.jsonl").read_text().splitlines()
    assert len([ln for ln in ledger if ln.strip()]) == 1


def test_p1_03_restart_across_separate_processes(tmp_path):
    """
    Real process restart: three separate interpreters each run one lifetime of
    maiw_api.app:app against the same MAIW_PERSISTENCE_ROOT.
    """
    root = tmp_path / "maiw"
    env = {
        **os.environ,
        "MAIW_PERSISTENCE_ROOT": str(root),
        "MAIW_READINESS_REQUIRE_DATABASE": "false",
        "MAIW_DEMO_MODE": "false",
        "DATABASE_URL": "postgresql://warehouse:ci_placeholder@127.0.0.1:1/warehouse",
        "REDIS_PORT": "1",
        "MILVUS_PORT": "1",
        "PYTHONPATH": str(REPO_ROOT),
    }
    env.pop("MAIW_PERSISTENCE_MODE", None)

    def run(*args):
        proc = subprocess.run(
            [sys.executable, "-m", "tests.api.canonical_restart_probe", *args],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert proc.returncode == 0, proc.stderr[-3000:]
        return json.loads(proc.stdout.strip().splitlines()[-1])

    first = run("start")
    assert first["store_backend"] == "JsonFileProcedureStateStore"
    assert first["inbox_backend"] == "JsonFileGovernanceInbox"
    st = first["state"]
    assert st["status"] == "waiting_for_governance"
    assert st["attempt_by_step"]["establish_state"] == 2  # retry counter
    pid, rev = st["procedure_execution_id"], str(st["revision"])

    second = run("govern", pid, rev)
    assert second["http_get_status"] == 200
    assert second["before"]["status"] == "waiting_for_governance"
    assert second["before"]["revision"] == st["revision"]
    assert second["before"]["attempt_by_step"]["establish_state"] == 2
    assert second["applied"] is True and second["duplicate"] is False
    assert second["executor_steps"] == ["observe"]
    assert second["state"]["status"] == "completed"

    third = run("replay", pid, rev)
    assert third["applied"] is False and third["duplicate"] is True
    assert third["executor_steps"] == []
    assert third["state"]["revision"] == second["state"]["revision"]


# ═════════════════════════════════════════════════════════════════════════════
# P1-04 — readiness reflects real critical dependencies
# ═════════════════════════════════════════════════════════════════════════════


async def test_p1_04_ready_when_dependencies_healthy(canonical):
    async with running_canonical_app() as (_, client):
        r = await client.get("/api/v1/ready")
        live = await client.get("/api/v1/live")
    body = r.json()
    assert r.status_code == 200, body
    assert body["status"] == "READY"
    assert body["components"]["persistence"]["status"] == "ready"
    assert body["components"]["persistence"]["durable"] is True
    assert body["components"]["model_gateway"]["status"] == "ready"
    assert live.status_code == 200


async def _ready_after(mutate) -> tuple[int, dict, int]:
    async with running_canonical_app() as (app, client):
        mutate(app)
        r = await client.get("/api/v1/ready")
        live = await client.get("/api/v1/live")
    return r.status_code, r.json(), live.status_code


async def test_p1_04_ready_fails_when_procedures_dir_deleted(canonical):
    import shutil

    _, _, root = canonical
    code, body, live = await _ready_after(
        lambda app: shutil.rmtree(root / "procedures")
    )
    assert code == 503 and body["status"] == "NOT_READY"
    assert "persistence" in body["failed_components"]
    assert body["components"]["persistence"]["procedure_store"]["status"] == "failed"
    assert live == 200  # liveness unaffected


async def test_p1_04_ready_fails_when_governance_dir_deleted(canonical):
    import shutil

    _, _, root = canonical
    code, body, _ = await _ready_after(lambda app: shutil.rmtree(root / "governance"))
    assert code == 503
    assert body["components"]["persistence"]["governance_inbox"]["status"] == "failed"


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root bypasses directory permissions",
)
async def test_p1_04_ready_fails_when_persistence_unwritable(canonical):
    _, _, root = canonical
    try:
        code, body, _ = await _ready_after(
            lambda app: [os.chmod(root / d, 0) for d in ("procedures", "governance")]
        )
    finally:
        for d in ("procedures", "governance"):
            if (root / d).exists():
                os.chmod(root / d, 0o700)
    assert code == 503
    assert "persistence" in body["failed_components"]


async def test_p1_04_ready_fails_when_persistence_unconstructible(
    canonical, monkeypatch, tmp_path
):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    monkeypatch.setenv("MAIW_PERSISTENCE_ROOT", str(blocker))
    async with running_canonical_app() as (app, client):
        assert app.state.runtime.procedure_host is None
        r = await client.get("/api/v1/ready")
        procs = await client.get("/api/v1/procedures")
    assert r.status_code == 503
    assert "persistence" in r.json()["failed_components"]
    assert procs.status_code == 503


async def test_p1_04_ready_fails_when_model_gateway_unavailable(canonical, monkeypatch):
    import maiw_models

    async def _boom(*a, **k):
        raise RuntimeError("gateway construction failed")

    monkeypatch.setattr(maiw_models, "get_model_gateway", _boom)
    async with running_canonical_app() as (_, client):
        r = await client.get("/api/v1/ready")
        live = await client.get("/api/v1/live")
    assert r.status_code == 503
    assert "model_gateway" in r.json()["failed_components"]
    assert live.status_code == 200


async def test_p1_04_ready_fails_when_database_unreachable(canonical, monkeypatch):
    monkeypatch.setenv("MAIW_READINESS_REQUIRE_DATABASE", "true")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://warehouse:unused@127.0.0.1:1/warehouse"
    )
    async with running_canonical_app() as (_, client):
        r = await client.get("/api/v1/ready")
    body = r.json()
    assert r.status_code == 503, body
    assert "database" in body["failed_components"]


async def test_p1_04_provider_down_does_not_fail_readiness(canonical):
    """Provider outage is per-request (typed 503), not process un-readiness."""
    token, fake, _ = canonical
    fake.mode = "fail"
    async with running_canonical_app() as (_, client):
        inf = await client.post(
            "/api/v1/inference", json=_VALID, headers={"X-Maiw-Internal-Token": token}
        )
        r = await client.get("/api/v1/ready")
    assert inf.status_code == 503
    assert r.status_code == 200
    assert r.json()["components"]["model_provider"]["critical"] is False


@pytest.mark.skipif(
    not os.getenv("MAIW_TEST_PG_DSN"),
    reason="set MAIW_TEST_PG_DSN to a disposable Postgres to run",
)
async def test_p1_04_ready_with_reachable_database(
    canonical, monkeypatch, real_asyncpg
):
    monkeypatch.setenv("MAIW_READINESS_REQUIRE_DATABASE", "true")
    monkeypatch.setenv("DATABASE_URL", os.environ["MAIW_TEST_PG_DSN"])
    async with running_canonical_app() as (_, client):
        r = await client.get("/api/v1/ready")
    assert r.status_code == 200, r.json()
    assert r.json()["components"]["database"]["status"] == "ready"


# ═════════════════════════════════════════════════════════════════════════════
# P1-05 — document pipeline: ModelGateway only, typed failure, never APPROVE
# ═════════════════════════════════════════════════════════════════════════════


async def test_p1_05_document_judge_uses_canonical_gateway(canonical):
    from src.api.agents.document.validation.large_llm_judge import LargeLLMJudge

    _, fake, _ = canonical
    async with running_canonical_app() as (app, _):
        result = await LargeLLMJudge().evaluate_document(
            {"extracted_fields": {"invoice_number": "INV-1"}}, {}, "invoice"
        )
        gateway = app.state.runtime.model_gateway
    sent = fake.chat_requests()
    assert len(sent) == 1
    cap = gateway.registry.get_by_id(sent[0]["model"])
    assert cap is not None and cap.generation in APPROVED_GENERATIONS
    assert result.judge_model == sent[0]["model"]
    assert result.decision == "REVIEW_REQUIRED"
    assert result.decision_kind == "model_quality_classification"
    assert result.model_route["via"] == "maiw_models.ModelGateway"


async def test_p1_05_document_provider_failure_never_approve(canonical):
    from src.api.agents.document.model_gateway_adapter import (
        DocumentInferenceUnavailable,
    )
    from src.api.agents.document.validation.large_llm_judge import LargeLLMJudge

    _, fake, _ = canonical
    fake.mode = "fail"
    async with running_canonical_app():
        with pytest.raises(DocumentInferenceUnavailable) as exc:
            await LargeLLMJudge().evaluate_document({}, {}, "invoice")
    assert exc.value.code in ("PROVIDER_FAILURE", "MODEL_UNAVAILABLE")


async def test_p1_05_document_missing_credential_never_approve(canonical):
    from src.api.agents.document.model_gateway_adapter import (
        DocumentInferenceUnavailable,
    )
    from src.api.agents.document.validation.large_llm_judge import LargeLLMJudge

    _, fake, _ = canonical
    install_gateway(fake, api_key="")  # the audit's "no key" case
    async with running_canonical_app():
        with pytest.raises(DocumentInferenceUnavailable) as exc:
            await LargeLLMJudge().evaluate_document({}, {}, "invoice")
    assert exc.value.code in ("PROVIDER_FAILURE", "MODEL_UNAVAILABLE")
    assert all(r["auth_present"] is False for r in fake.chat_requests())


@pytest.mark.parametrize(
    "reply",
    [
        "I approve this document.",  # v2.0.0 heuristic turned this into APPROVE
        json.dumps({"overall_score": 4.9, "decision": "LGTM"}),
        json.dumps({"decision": "APPROVE"}),  # no score
    ],
)
async def test_p1_05_malformed_judge_reply_never_approve(canonical, reply):
    from src.api.agents.document.model_gateway_adapter import (
        DocumentInferenceUnavailable,
    )
    from src.api.agents.document.validation.large_llm_judge import LargeLLMJudge

    _, fake, _ = canonical
    fake.content = reply
    async with running_canonical_app():
        with pytest.raises(DocumentInferenceUnavailable) as exc:
            await LargeLLMJudge().evaluate_document({}, {}, "invoice")
    assert exc.value.code == "MALFORMED_RESPONSE"


async def test_p1_05_document_vision_has_no_eligible_model(canonical):
    """Vision OCR needs IMAGE modality; no approved model → typed failure,
    and the provider is never called (policy not widened, no substitute)."""
    from PIL import Image

    from src.api.agents.document.model_gateway_adapter import (
        DocumentInferenceUnavailable,
    )
    from src.api.agents.document.ocr.nemo_ocr import NeMoOCRService
    from src.api.agents.document.processing.small_llm_processor import (
        SmallLLMProcessor,
    )

    _, fake, _ = canonical
    img = Image.new("RGB", (64, 32), "white")
    async with running_canonical_app():
        with pytest.raises(DocumentInferenceUnavailable) as ocr_exc:
            await NeMoOCRService().extract_text([img], {})
        with pytest.raises(DocumentInferenceUnavailable) as llm_exc:
            await SmallLLMProcessor().process_document([img], "", "invoice")
    assert ocr_exc.value.code == "MODEL_UNAVAILABLE"
    assert llm_exc.value.code == "MODEL_UNAVAILABLE"
    assert fake.chat_requests() == []


async def test_p1_05_document_upload_end_to_end_fails_typed(
    canonical, monkeypatch, tmp_path
):
    """
    HTTP E2E through the shipped app: upload an image; the pipeline reaches
    the OCR (IMAGE) stage, gets MODEL_UNAVAILABLE from the ModelGateway, and
    the document is FAILED with that code. Results carry no fabricated data
    and no APPROVE. The provider is never called.
    """
    from PIL import Image

    import src.api.routers.document as doc_router

    _, fake, _ = canonical
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)  # uploads/ + status file land in tmp, not the repo
    doc_router.DocumentToolsSingleton._instance = None
    doc_router.DocumentToolsSingleton._initialized = False
    img_path = work / "invoice.png"
    Image.new("RGB", (200, 100), "white").save(img_path)
    try:
        async with running_canonical_app() as (_, client):
            with img_path.open("rb") as fh:
                up = await client.post(
                    "/api/v1/document/upload",
                    files={"file": ("invoice.png", fh, "image/png")},
                    data={"document_type": "invoice"},
                )
            assert up.status_code == 200, up.text
            doc_id = up.json()["document_id"]
            status = (await client.get(f"/api/v1/document/status/{doc_id}")).json()
            results = await client.get(f"/api/v1/document/results/{doc_id}")
    finally:
        doc_router.DocumentToolsSingleton._instance = None
        doc_router.DocumentToolsSingleton._initialized = False

    assert status["status"] == "failed", status
    errors = " ".join(str(s.get("error_message") or "") for s in status["stages"])
    assert "MODEL_UNAVAILABLE" in errors, status
    assert results.status_code == 200
    rbody = results.json()
    text = json.dumps(rbody)
    assert (
        '"APPROVE"' not in text
        and "approve" not in str((rbody.get("quality_score") or {})).lower()
    )
    assert rbody.get("quality_score") is None
    assert rbody["processing_summary"]["is_mock_data"] is False
    assert rbody["processing_summary"]["extracted_fields"] in ({}, None)
    assert fake.chat_requests() == []


def test_p1_05_document_path_has_no_direct_provider_calls():
    """Static guard: no provider client, URL, key or hard-coded model id in
    the shipped document pipeline modules."""
    modules = [
        "src/api/routers/document.py",
        "src/api/agents/document/action_tools.py",
        "src/api/agents/document/preprocessing/nemo_retriever.py",
        "src/api/agents/document/ocr/nemo_ocr.py",
        "src/api/agents/document/processing/small_llm_processor.py",
        "src/api/agents/document/validation/large_llm_judge.py",
        "src/api/agents/document/routing/intelligent_router.py",
    ]
    banned = [
        "import httpx",
        "httpx.AsyncClient",
        "chat/completions",
        "get_nim_client",
        "NIMClient(",
        "meta/llama",
        "_mock_judge_evaluation",
        "_mock_llm_processing",
        "_mock_ocr_extraction",
        "_get_mock_extraction_data",
        "integrate.api.nvidia.com",
    ]
    for rel in modules:
        text = (REPO_ROOT / rel).read_text()
        for needle in banned:
            assert needle not in text, f"{rel} contains {needle!r}"
