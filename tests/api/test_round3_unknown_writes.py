# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.0.1 round 3 — NEW3-P1-02: an ambiguous real MCP write is UNKNOWN, is never
blindly retried, and is reconciled outside demo mode.

Third independent re-audit (PR #143 @ 86f3004), ``reference_governed`` with a
real streamable-HTTP equipment MCP server: a release whose write LANDED before
the server crashed was returned as ``failed, executed: false``;
``/api/v1/demo/reconcile`` answered 503 outside demo mode; an identical
operator retry executed a SECOND write; ``execution_id`` was null at the
backend.

These tests drive the canonical shipped app ``maiw_api.app:app`` (real
lifespan, real MCP client, real streamable-HTTP transport) against the
repository's own equipment MCP server module run as a separate process with a
durable recording backend (``tests/api/round3_mcp_backend.py``) that applies
each write and can crash before answering.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.api.canonical_harness import (
    FakeNIM,
    canonical_env,
    install_gateway,
    running_canonical_app,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = Path(__file__).with_name("round3_mcp_backend.py")
RELEASE = {"asset_id": "FL-01", "released_by": "operator-1", "notes": "r3"}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Backend:
    """The repo's equipment MCP server + durable recording backend, as a process."""

    def __init__(self, workdir: Path) -> None:
        self.dir = workdir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.port = _free_port()
        self.url = f"http://127.0.0.1:{self.port}/mcp"
        self.state = self.dir / "state.json"
        self.write_log = self.dir / "writes.jsonl"
        self.control = self.dir / "control"
        self.proc: subprocess.Popen | None = None

    def start(self) -> None:
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/tmp"),
            "PYTHON_DOTENV_DISABLED": "1",
        }
        self.proc = subprocess.Popen(
            [
                sys.executable,
                str(BACKEND),
                str(self.port),
                str(self.state),
                str(self.write_log),
                str(self.control),
            ],
            cwd=str(REPO_ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("MCP backend exited during startup")
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", self.port)) == 0:
                    return
            time.sleep(0.1)
        raise RuntimeError("MCP backend did not start")

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def wait_dead(self, timeout: float = 10) -> None:
        if self.proc is not None:
            self.proc.wait(timeout=timeout)

    def stop(self) -> None:
        if self.alive():
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()

    def arm(self, mode: str) -> None:
        self.control.write_text(mode)

    def entries(self) -> list[dict]:
        if not self.write_log.exists():
            return []
        return [json.loads(x) for x in self.write_log.read_text().splitlines() if x]

    def applied(self) -> list[dict]:
        return [e for e in self.entries() if e["event"] == "write_applied"]

    def asset(self, asset_id: str) -> dict:
        rows = json.loads(self.state.read_text())
        return next(r for r in rows if r["asset_id"] == asset_id)


@pytest.fixture
def fake_nim():
    fake = FakeNIM()
    yield fake
    fake.close()


@pytest.fixture
def backend(tmp_path):
    b = Backend(tmp_path / "mcp")
    b.start()
    yield b
    b.stop()


@pytest.fixture
def governed(monkeypatch, tmp_path, fake_nim, backend):
    canonical_env(monkeypatch, tmp_path, fake_nim)
    operator = secrets.token_hex(32)
    monkeypatch.setenv("MAIW_DEPLOYMENT_PROFILE", "reference_governed")
    monkeypatch.setenv("MAIW_REQUIRED_MCP_DOMAINS", "equipment")
    monkeypatch.setenv("MAIW_MCP_SERVER_EQUIPMENT_URL", backend.url)
    monkeypatch.setenv("MAIW_OPERATOR_WRITE_TOKEN", operator)
    install_gateway(fake_nim)
    yield {"X-Maiw-Operator-Token": operator}, tmp_path / "maiw"
    from maiw_models import reset_model_gateway

    reset_model_gateway()


def _count_proposals(rt) -> dict:
    counter = {"n": 0}
    original = rt.equipment_agent.propose_equipment_release

    async def wrapper(*a, **kw):
        counter["n"] += 1
        return await original(*a, **kw)

    rt.equipment_agent.propose_equipment_release = wrapper
    return counter


async def _release(client, auth, **extra):
    return await client.post(
        "/api/v1/equipment/release", json=RELEASE, headers={**auth, **extra}
    )


# ── §19 lost response → UNKNOWN → no retry → reread → CONFIRMED_EXECUTED ─────


async def test_lost_response_is_unknown_never_retried_and_reconciles_executed(
    governed, backend
):
    auth, root = governed
    async with running_canonical_app() as (app, client):
        proposals = _count_proposals(app.state.runtime)
        backend.arm("crash_after_write")
        r = await _release(client, auth, **{"X-Trace-Id": "r3-trace-lost-response"})
        backend.wait_dead()

        # initial result UNKNOWN — executed is NOT false
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["status"] == "unknown"
        assert body["executed"] is None
        assert body["reconciliation_required"] is True
        assert body["retried"] is False
        assert body["error_code"] == "MCP_RESPONSE_LOST"
        exec_id = body["execution_id"]

        # the write landed exactly once, carrying MAIW's identity chain
        applied = backend.applied()
        assert len(applied) == 1
        assert applied[0]["execution_id"] == exec_id
        assert applied[0]["proposal_id"] == body["proposal_id"]
        assert applied[0]["decision_id"] == body["decision_id"]
        assert backend.asset("FL-01")["status"] == "available"

        # no automatic retry
        await asyncio.sleep(1.0)
        assert len(backend.applied()) == 1

        # identical request before reconciliation: refused before governance
        r2 = await _release(client, auth)
        assert r2.status_code == 409, r2.text
        assert r2.json()["code"] == "RECONCILIATION_REQUIRED"
        assert r2.json()["execution_id"] == exec_id
        assert proposals["n"] == 1
        assert len(backend.applied()) == 1

        pending = (await client.get("/api/v1/executions", headers=auth)).json()
        assert [e["execution_id"] for e in pending["executions"]] == [exec_id]
        assert pending["executions"][0]["trace_id"] == "r3-trace-lost-response"

        # authoritative re-read (backend back up with its durable state)
        backend.start()
        rec = await client.post(f"/api/v1/executions/{exec_id}/reconcile", headers=auth)
        assert rec.status_code == 200, rec.text
        out = rec.json()
        assert out["reconciliation_outcome"] == "confirmed_executed"
        assert out["outcome"] == "unknown"  # history is never rewritten
        assert out["effective_status"] == "effectively_executed"
        assert out["execution_id"] == exec_id
        assert out["proposal_id"] == body["proposal_id"]
        assert out["decision_id"] == body["decision_id"]
        assert out["retried"] is False
        assert len(backend.applied()) == 1

        empty = (await client.get("/api/v1/executions", headers=auth)).json()
        assert empty["count"] == 0

    record = json.loads((root / "executions/equipment" / f"{exec_id}.json").read_text())
    assert record["outcome"] == "unknown"
    assert record["reconciliation"]["outcome"] == "confirmed_executed"


# ── §20-adjacent: response lost but the write was NOT applied ────────────────


async def test_lost_response_without_write_reconciles_not_executed(governed, backend):
    auth, _ = governed
    async with running_canonical_app() as (_, client):
        backend.arm("crash_before_write")
        r = await _release(client, auth)
        backend.wait_dead()
        assert r.status_code == 202
        exec_id = r.json()["execution_id"]
        assert backend.applied() == []
        backend.start()
        rec = await client.post(f"/api/v1/executions/{exec_id}/reconcile", headers=auth)
        assert rec.json()["reconciliation_outcome"] == "confirmed_not_executed"
        assert rec.json()["expected_effect"]["pre_status"] == "assigned"
        assert backend.asset("FL-01")["status"] == "assigned"
        assert backend.applied() == []


# ── §21 reread unavailable → INDETERMINATE, still blocked, no retry ──────────


async def test_inconclusive_reread_is_indeterminate_and_keeps_blocking(
    governed, backend
):
    auth, _ = governed
    async with running_canonical_app() as (_, client):
        backend.arm("crash_after_write")
        r = await _release(client, auth)
        backend.wait_dead()
        exec_id = r.json()["execution_id"]

        # backend still down: the authoritative read fails
        rec = await client.post(f"/api/v1/executions/{exec_id}/reconcile", headers=auth)
        assert rec.status_code == 200
        assert rec.json()["reconciliation_outcome"] == "indeterminate"
        assert rec.json()["effective_status"] == "unknown"
        assert rec.json()["unresolved"] is True

        retry = await _release(client, auth)
        assert retry.status_code == 409  # no false success, no false failure
        assert len(backend.applied()) == 1

        # once the backend is readable, the same execution resolves
        backend.start()
        rec2 = await client.post(
            f"/api/v1/executions/{exec_id}/reconcile", headers=auth
        )
        assert rec2.json()["reconciliation_outcome"] == "confirmed_executed"
        assert len(backend.applied()) == 1


# ── §22 crash / restart after UNKNOWN ────────────────────────────────────────


async def test_restart_after_unknown_keeps_identity_blocks_and_reconciles(
    governed, backend
):
    auth, _ = governed
    async with running_canonical_app() as (_, client):
        backend.arm("crash_after_write")
        r = await _release(client, auth)
        backend.wait_dead()
        first = r.json()
    # process gone; the journal on disk is all that survives
    async with running_canonical_app() as (app, client):
        proposals = _count_proposals(app.state.runtime)
        pending = (await client.get("/api/v1/executions", headers=auth)).json()
        assert [e["execution_id"] for e in pending["executions"]] == [
            first["execution_id"]
        ]
        assert pending["executions"][0]["proposal_id"] == first["proposal_id"]
        assert pending["executions"][0]["decision_id"] == first["decision_id"]

        retry = await _release(client, auth)
        assert retry.status_code == 409
        assert proposals["n"] == 0

        backend.start()
        rec = await client.post(
            f"/api/v1/executions/{first['execution_id']}/reconcile", headers=auth
        )
        assert rec.json()["reconciliation_outcome"] == "confirmed_executed"
        ready = (await client.get("/api/v1/ready")).json()
        journal = ready["components"]["governed_write_path"]["execution_journal"]
        assert journal["equipment"] == {"durable": True, "unresolved": 0}
    assert len(backend.applied()) == 1


async def test_idempotency_key_replay_never_writes_twice(governed, backend):
    """§18: the same Idempotency-Key after a completed write replays it (no write)."""
    auth, _ = governed
    key = {"Idempotency-Key": "r3-idem-1"}
    async with running_canonical_app() as (_, client):
        first = await _release(client, auth, **key)
        assert first.status_code == 200, first.text
        assert first.json()["status"] == "executed"
        second = await _release(client, auth, **key)
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["status"] == "no_op"
    assert body["execution_id"] == first.json()["execution_id"]
    assert len(backend.applied()) == 1


def test_write_in_flight_at_crash_is_unknown_after_restart(tmp_path):
    """A record persisted at begin() with no outcome = the process died mid-write."""
    from maiw_execution import ExecutionIntent, JsonFileExecutionRegistry

    journal = tmp_path / "executions" / "equipment"
    reg = JsonFileExecutionRegistry(journal)
    intent = ExecutionIntent(
        capability="warehouse.equipment.release",
        proposal_id="p-1",
        decision_id="d-1",
        target="FL-01",
        expected_effect={"expected_status": "available", "pre_status": "assigned"},
        trace_id="t-1",
    )
    assert reg.begin("e-1", None, "warehouse.equipment.release", "p-1", intent) is None
    del reg  # crash: no complete() / mark_unknown()

    restarted = JsonFileExecutionRegistry(journal)
    record = restarted.get_by_execution_id("e-1")
    assert record.outcome.value == "unknown"
    assert record.recovered_after_restart is True
    assert restarted.recovered_in_flight == ["e-1"]
    assert record.intent.trace_id == "t-1" and record.proposal_id == "p-1"
    # a new write to the same asset is refused (returns the blocking record)
    blocker = restarted.begin(
        "e-2",
        None,
        "warehouse.equipment.assign",
        "p-2",
        ExecutionIntent(
            capability="warehouse.equipment.assign",
            proposal_id="p-2",
            decision_id="d-2",
            target="FL-01",
        ),
    )
    assert blocker is not None and blocker.execution_id == "e-1"


def test_unreadable_journal_fails_closed(tmp_path):
    from maiw_execution import ExecutionJournalError, JsonFileExecutionRegistry

    journal = tmp_path / "executions" / "equipment"
    journal.mkdir(parents=True)
    (journal / "broken.json").write_text("{not json")
    with pytest.raises(ExecutionJournalError):
        JsonFileExecutionRegistry(journal)


# ── §20 definitely never sent → FAILED (confirmed not executed) ───────────────


def _executor(url: str, circuit_registry=None):
    from maiw_execution import EquipmentActionExecutor, ExecutionRegistry
    from maiw_mcp.client.client import MAIWMCPClient
    from maiw_mcp.registry.registry import CapabilityRegistry
    from maiw_skills.equipment.skills import ExecuteEquipmentReleaseSkill

    registry = CapabilityRegistry()
    registry.register_domain(
        ["warehouse.equipment.get_status", "warehouse.equipment.release"], url
    )
    client = MAIWMCPClient(registry, circuit_registry=circuit_registry)
    journal = ExecutionRegistry()
    return (
        EquipmentActionExecutor(
            assign_skill=None,
            release_skill=ExecuteEquipmentReleaseSkill(client),
            registry=journal,
        ),
        journal,
        client,
    )


def _approved_release():
    from datetime import datetime, timezone

    from maiw_decision.models import DecisionOutcome, DecisionResult
    from maiw_decision.proposal import ActionProposal

    proposal = ActionProposal.for_equipment_release(
        asset_id="FL-01", released_by="operator-1"
    )
    decision = DecisionResult(
        request_id="r3-test",
        proposal_id=proposal.proposal_id,
        outcome=DecisionOutcome.APPROVED,
        evaluated_at=datetime.now(timezone.utc),
    )
    return proposal, decision


async def test_never_dispatched_write_is_definite_failure():
    """Connection refused before tools/call → FAILED, not executed, not blocking."""
    closed = f"http://127.0.0.1:{_free_port()}/mcp"
    executor, journal, _ = _executor(closed)
    proposal, decision = _approved_release()
    result = await executor.execute(proposal, decision)
    assert result.outcome.value == "failed"
    assert result.error_code == "MCP_NOT_DISPATCHED"
    assert result.physical_mutation_occurred is False
    assert journal.unresolved_for_target("warehouse.equipment.release", "FL-01") is None


async def test_open_circuit_is_not_dispatched(backend):
    from maiw_mcp.circuit_registry import DomainCircuitRegistry

    circuits = DomainCircuitRegistry.for_domains(
        domains=["equipment"], failure_threshold=1, cooldown_seconds=300
    )

    async def _boom():
        raise RuntimeError("trip")

    with pytest.raises(RuntimeError):
        await circuits.get("equipment").call(_boom())
    assert circuits.get("equipment").get_stats()["state"] == "open"
    executor, _, _ = _executor(backend.url, circuit_registry=circuits)
    proposal, decision = _approved_release()
    result = await executor.execute(proposal, decision)
    assert result.outcome.value == "failed"
    assert result.error_code == "MCP_NOT_DISPATCHED"
    assert backend.entries() == []


async def test_read_timeout_after_dispatch_is_unknown(backend):
    """The real client tags a post-dispatch timeout; the executor maps it UNKNOWN."""
    from maiw_execution import classify_write_failure
    from maiw_mcp.errors import MCPTimeoutAfterDispatch

    _, _, client = _executor(backend.url)
    backend.arm("hang_after_write")
    with pytest.raises(MCPTimeoutAfterDispatch) as info:
        await client.invoke(
            "warehouse.equipment.release",
            {
                "asset_id": "FL-01",
                "released_by": "t",
                "proposal_id": "p",
                "decision_id": "d",
                "execution_id": "e-timeout",
            },
            timeout_seconds=2.0,
        )
    outcome, code, mutation = classify_write_failure(info.value)
    assert (outcome.value, code, mutation) == ("unknown", "MCP_RESPONSE_LOST", None)
    assert [e["execution_id"] for e in backend.applied()] == ["e-timeout"]


def test_failure_classification_table():
    from maiw_execution import AmbiguousWriteError, classify_write_failure
    from maiw_mcp.deadline import RequestDeadlineExceeded
    from maiw_mcp.errors import (
        CapabilityNotFound,
        MCPCircuitOpen,
        MCPConnectFailed,
        MCPConnectTimeout,
        MCPContractError,
        MCPResponseLost,
        MCPTimeout,
        MCPTimeoutAfterDispatch,
        MCPToolError,
    )

    table = {
        AmbiguousWriteError("x"): ("unknown", True),
        MCPResponseLost("x"): ("unknown", None),
        MCPTimeoutAfterDispatch("x"): ("unknown", None),
        MCPTimeout("x"): ("unknown", None),
        MCPContractError("x"): ("unknown", None),
        MCPConnectFailed("x"): ("failed", False),
        MCPConnectTimeout("x"): ("failed", False),
        MCPCircuitOpen("x"): ("failed", False),
        MCPToolError("x"): ("failed", False),
        CapabilityNotFound("x"): ("failed", False),
        RequestDeadlineExceeded(expired_by_ms=1.0): ("failed", False),
        RuntimeError("x"): ("failed", False),
    }
    for exc, (outcome, mutation) in table.items():
        got_outcome, _, got_mutation = classify_write_failure(exc)
        assert (got_outcome.value, got_mutation) == (outcome, mutation), exc


def test_mcp_write_tools_forward_execution_id():
    """The backend receives MAIW's execution_id (it was null in the audit)."""
    import inspect

    from mcp_servers.equipment import server as eq
    from mcp_servers.labor import server as lab
    from mcp_servers.wave import server as wave

    for fn in (
        eq.warehouse_equipment_assign,
        eq.warehouse_equipment_release,
        eq.warehouse_equipment_schedule_maintenance,
        lab.warehouse_labor_allocate,
        wave.warehouse_wave_reprioritize,
    ):
        target = getattr(fn, "fn", fn)
        assert "execution_id" in inspect.signature(target).parameters, fn
