# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.0.1 round 4 — NEW4-P1-01: a server-reported MCP tool error after dispatch is
NOT proof of non-execution.

Fourth independent re-audit (PR #143 @ 6ad2cbf), ``reference_governed`` with
the repository's equipment MCP server over real streamable HTTP: the backend
applied a release and then raised; MAIW answered ``200 failed executed=false
MCP_TOOL_ERROR``, the journal said ``physical_mutation_occurred=false,
unresolved=false``, reconciliation was refused (409 "UNKNOWN only") and the
operator retry wrote a SECOND time.

These tests drive the canonical shipped app (real lifespan, real
``MAIWMCPClient``, real streamable-HTTP transport, real error-result decoding,
real durable execution journal) against the repository's own equipment MCP
server module running as a separate process with the durable recording
backend ``tests/api/round3_mcp_backend.py`` (round-4 fault modes).

Rules proven here:

* isError after dispatch without ``execution_disposition = "NOT_APPLIED"`` in
  ``structuredContent`` → 202 UNKNOWN, ``executed: null``, journal
  unresolved, identical retry 409, write count unchanged, reconciliation
  resolves it (§11, §20, §21).
* The explicit typed ``NOT_APPLIED`` disposition → definite FAILED,
  ``executed: false``, not unresolved, reconciliation not needed (§12).
* Missing / malformed / unknown dispositions, and a NOT_APPLIED claim made only
  in the text content → UNKNOWN (§13).
* A NON-error result reporting failure without the disposition → UNKNOWN.
"""

from __future__ import annotations

import json
import secrets

import pytest

from tests.api.canonical_harness import (
    FakeNIM,
    canonical_env,
    install_gateway,
    running_canonical_app,
)
from tests.api.test_round3_unknown_writes import (
    Backend,
    _count_proposals,
    _release,
)


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


async def _unresolved(client, auth) -> list[dict]:
    body = (await client.get("/api/v1/executions", headers=auth)).json()
    return body["executions"]


async def _journal_unresolved_count(client) -> int:
    ready = (await client.get("/api/v1/ready")).json()
    journal = ready["components"]["governed_write_path"]["execution_journal"]
    return journal["equipment"]["unresolved"]


# ── §11 / §20: server error AFTER mutation → UNKNOWN → 409 → CONFIRMED_EXECUTED ─


async def test_server_error_after_mutation_is_unknown_blocks_retry_and_reconciles(
    governed, backend
):
    auth, root = governed
    async with running_canonical_app() as (app, client):
        proposals = _count_proposals(app.state.runtime)
        backend.arm("error_after_write")
        r = await _release(client, auth, **{"X-Trace-Id": "r4-server-error"})

        # the server applied the write and THEN reported isError
        assert backend.alive()
        applied = backend.applied()
        assert len(applied) == 1
        assert backend.asset("FL-01")["status"] == "available"

        # UNKNOWN — executed is NOT false, never "failed"
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["status"] == "unknown"
        assert body["executed"] is None
        assert body["error_code"] == "MCP_TOOL_ERROR"
        assert body["dispatch_status"] == "dispatched_server_error"
        assert body["server_disposition"] == "absent:no_structured_content"
        assert body["reconciliation_required"] is True
        assert body["retried"] is False
        exec_id = body["execution_id"]
        assert applied[0]["execution_id"] == exec_id

        # durable journal: unresolved, full identity + uncertainty evidence
        pending = await _unresolved(client, auth)
        assert [e["execution_id"] for e in pending] == [exec_id]
        rec = pending[0]
        assert rec["unresolved"] is True
        assert rec["outcome"] == "unknown"
        assert rec["physical_mutation_occurred"] is None
        assert rec["dispatch_status"] == "dispatched_server_error"
        assert "NOT_APPLIED" in rec["uncertainty_reason"]
        assert rec["trace_id"] == "r4-server-error"
        assert rec["proposal_id"] == body["proposal_id"]
        assert rec["decision_id"] == body["decision_id"]
        assert rec["target"] == "FL-01"
        assert rec["expected_effect"]["expected_status"] == "available"
        assert rec["expected_effect"]["pre_status"] == "assigned"
        assert await _journal_unresolved_count(client) == 1

        # identical operator retry: refused before governance, no new write
        retry = await _release(client, auth)
        assert retry.status_code == 409, retry.text
        assert retry.json()["code"] == "RECONCILIATION_REQUIRED"
        assert retry.json()["execution_id"] == exec_id
        assert proposals["n"] == 1
        assert len(backend.applied()) == 1

        # reconciliation is allowed (it was refused with 409 in the audit)
        out = await client.post(f"/api/v1/executions/{exec_id}/reconcile", headers=auth)
        assert out.status_code == 200, out.text
        assert out.json()["reconciliation_outcome"] == "confirmed_executed"
        assert out.json()["outcome"] == "unknown"  # history is not rewritten
        assert out.json()["retried"] is False
        assert len(backend.applied()) == 1
        assert await _journal_unresolved_count(client) == 0

    record = json.loads((root / "executions/equipment" / f"{exec_id}.json").read_text())
    assert record["outcome"] == "unknown"
    assert record["result"]["physical_mutation_occurred"] is None
    assert record["result"]["dispatch_status"] == "dispatched_server_error"
    assert record["reconciliation"]["outcome"] == "confirmed_executed"


# ── §21: server error → UNKNOWN persisted → process gone → restart ──────────


async def test_server_error_unknown_survives_restart_and_blocks_retry(
    governed, backend
):
    auth, _ = governed
    async with running_canonical_app() as (_, client):
        backend.arm("error_after_write")
        first = (await _release(client, auth)).json()
        assert first["status"] == "unknown"
    # the API process is gone; only the on-disk journal survives
    async with running_canonical_app() as (app, client):
        proposals = _count_proposals(app.state.runtime)
        pending = await _unresolved(client, auth)
        assert [e["execution_id"] for e in pending] == [first["execution_id"]]
        assert pending[0]["dispatch_status"] == "dispatched_server_error"
        retry = await _release(client, auth)
        assert retry.status_code == 409
        assert proposals["n"] == 0
        assert len(backend.applied()) == 1
        rec = await client.post(
            f"/api/v1/executions/{first['execution_id']}/reconcile", headers=auth
        )
        assert rec.json()["reconciliation_outcome"] == "confirmed_executed"
    assert len(backend.applied()) == 1


# ── generic error BEFORE mutation is still not certified → UNKNOWN ──────────


async def test_uncertified_error_without_mutation_is_unknown_then_not_executed(
    governed, backend
):
    auth, _ = governed
    async with running_canonical_app() as (_, client):
        backend.arm("error_before_write")
        r = await _release(client, auth)
        assert r.status_code == 202, r.text
        assert r.json()["status"] == "unknown"
        exec_id = r.json()["execution_id"]
        assert backend.applied() == []
        assert (await _release(client, auth)).status_code == 409
        rec = await client.post(f"/api/v1/executions/{exec_id}/reconcile", headers=auth)
        assert rec.json()["reconciliation_outcome"] == "confirmed_not_executed"
        assert backend.asset("FL-01")["status"] == "assigned"
        # the target is free again: a NEW operator request writes exactly once
        again = await _release(client, auth)
        assert again.status_code == 200, again.text
        assert again.json()["status"] == "executed"
    assert len(backend.applied()) == 1


# ── §12: explicit NOT_APPLIED → definite failure, no reconciliation ─────────


async def test_explicit_not_applied_is_definite_failure(governed, backend):
    auth, _ = governed
    async with running_canonical_app() as (_, client):
        backend.arm("reject_not_applied")
        r = await _release(client, auth)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "failed"
        assert body["executed"] is False
        assert body["error_code"] == "MCP_TOOL_NOT_APPLIED"
        assert body["server_disposition"] == "NOT_APPLIED"
        assert body["dispatch_status"] == "rejected_before_mutation"
        assert "reconciliation_required" not in body
        assert backend.applied() == []
        assert backend.asset("FL-01")["status"] == "assigned"

        assert await _unresolved(client, auth) == []
        assert await _journal_unresolved_count(client) == 0
        full = (
            await client.get(f"/api/v1/executions/{body['execution_id']}", headers=auth)
        ).json()
        assert full["outcome"] == "failed"
        assert full["unresolved"] is False
        assert full["physical_mutation_occurred"] is False
        # reconciliation is not needed (and not offered) for a definite failure
        rec = await client.post(
            f"/api/v1/executions/{body['execution_id']}/reconcile", headers=auth
        )
        assert rec.status_code == 409

        # a fresh request is not blocked and writes exactly once
        again = await _release(client, auth)
        assert again.status_code == 200
        assert again.json()["status"] == "executed"
    assert len(backend.applied()) == 1


async def test_not_applied_replay_by_idempotency_key_is_not_a_success(
    governed, backend
):
    """Fourth re-audit NEW4-P2-01: replaying a FAILED write must not say no_op."""
    auth, _ = governed
    key = {"Idempotency-Key": "r4-idem-not-applied"}
    async with running_canonical_app() as (_, client):
        backend.arm("reject_not_applied")
        first = await _release(client, auth, **key)
        assert first.json()["status"] == "failed"
        replay = await _release(client, auth, **key)
    assert replay.status_code == 200, replay.text
    body = replay.json()
    assert body["status"] == "failed"
    assert body["executed"] is False
    assert body["execution_id"] == first.json()["execution_id"]
    assert backend.applied() == []


# ── §13: malformed / missing / unknown dispositions → UNKNOWN ───────────────

# variant (see round3_mcp_backend.MALFORMED) → what the client observed
MALFORMED_VARIANTS = {
    "no_structured": "absent:no_structured_content",
    "no_field": "absent:no_execution_disposition",
    "null": "malformed:NoneType",
    "int": "malformed:int",
    "bool": "malformed:bool",
    "list": "malformed:list",
    "nested": "malformed:dict",
    "lowercase": "unrecognised:'not_applied'",
    "padded": "unrecognised:' NOT_APPLIED'",
    "unknown_value": "unrecognised:'REJECTED_BEFORE_MUTATION'",
    "applied": "unrecognised:'APPLIED'",
    "wrong_key": "absent:no_execution_disposition",
    "text_only_claim": "absent:no_structured_content",
}


@pytest.mark.parametrize("variant", sorted(MALFORMED_VARIANTS))
async def test_malformed_disposition_after_mutation_is_unknown(
    governed, backend, variant
):
    auth, root = governed
    async with running_canonical_app() as (_, client):
        backend.arm(f"malformed_after_write:{variant}")
        r = await _release(client, auth)
        assert r.status_code == 202, (variant, r.text)
        body = r.json()
        assert body["status"] == "unknown"
        assert body["executed"] is None
        assert body["error_code"] == "MCP_TOOL_ERROR"
        # the crafted disposition really reached the client, and was refused
        assert body["server_disposition"] == MALFORMED_VARIANTS[variant]
        assert len(backend.applied()) == 1
        retry = await _release(client, auth)
        assert retry.status_code == 409
    assert len(backend.applied()) == 1
    record = json.loads(
        (root / "executions/equipment" / f"{body['execution_id']}.json").read_text()
    )
    message = record["result"]["error_message"]
    if variant == "text_only_claim":
        # the server's TEXT claimed NOT_APPLIED — text is never trusted
        assert '"execution_disposition": "NOT_APPLIED"' in message
    else:
        assert "AFTER the mutation was applied" in message


# ── non-error result that reports failure without the disposition ──────────


async def test_non_error_failure_result_without_disposition_is_unknown(
    governed, backend
):
    auth, _ = governed
    async with running_canonical_app() as (_, client):
        backend.arm("soft_fail_after_write")
        r = await _release(client, auth)
        assert r.status_code == 202, r.text
        assert r.json()["status"] == "unknown"
        assert r.json()["error_code"] == "SERVER_FAILURE_UNCERTIFIED"
        assert len(backend.applied()) == 1
        assert (await _release(client, auth)).status_code == 409
    assert len(backend.applied()) == 1


async def test_non_error_conflict_with_not_applied_is_definite(governed, backend):
    auth, _ = governed
    async with running_canonical_app() as (_, client):
        backend.arm("conflict_not_applied")
        r = await _release(client, auth)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "conflict"
        assert r.json()["executed"] is False
        assert await _unresolved(client, auth) == []
    assert backend.applied() == []


# ── real transport, client + executor + JSON journal (no HTTP layer) ────────


async def test_real_client_decodes_error_results_by_disposition_only(backend, tmp_path):
    """The real ``MAIWMCPClient`` over streamable HTTP, typed per disposition."""
    from maiw_execution import (
        EquipmentActionExecutor,
        JsonFileExecutionRegistry,
    )
    from maiw_mcp.client.client import MAIWMCPClient
    from maiw_mcp.errors import (
        MCPToolError,
        MCPToolErrorOutcomeUnknown,
        MCPToolNotApplied,
    )
    from maiw_mcp.registry.registry import CapabilityRegistry
    from maiw_skills.equipment.skills import ExecuteEquipmentReleaseSkill

    from tests.api.test_round3_unknown_writes import _approved_release

    registry = CapabilityRegistry()
    registry.register_domain(
        ["warehouse.equipment.get_status", "warehouse.equipment.release"], backend.url
    )
    client = MAIWMCPClient(registry)
    payload = {
        "asset_id": "FL-02",
        "released_by": "t",
        "proposal_id": "p",
        "decision_id": "d",
        "execution_id": "e",
    }

    backend.arm("reject_not_applied")
    with pytest.raises(MCPToolNotApplied) as na:
        await client.invoke("warehouse.equipment.release", payload)
    assert na.value.rejection_code == "PRECONDITION_FAILED"

    backend.arm("error_after_write")
    with pytest.raises(MCPToolErrorOutcomeUnknown) as unk:
        await client.invoke("warehouse.equipment.release", payload)
    assert isinstance(unk.value, MCPToolError)
    assert unk.value.observed_disposition == "absent:no_structured_content"

    backend.arm("malformed_after_write:lowercase")
    with pytest.raises(MCPToolErrorOutcomeUnknown) as bad:
        await client.invoke("warehouse.equipment.release", payload)
    assert bad.value.observed_disposition.startswith("unrecognised:")

    # executor + durable journal
    journal_dir = tmp_path / "journal"
    journal = JsonFileExecutionRegistry(journal_dir)
    executor = EquipmentActionExecutor(
        assign_skill=None,
        release_skill=ExecuteEquipmentReleaseSkill(client),
        registry=journal,
    )
    proposal, decision = _approved_release()
    before = len(backend.applied())
    backend.arm("error_after_write")
    result = await executor.execute(proposal, decision, trace_id="r4-exec")
    assert result.outcome.value == "unknown"
    assert result.physical_mutation_occurred is None
    assert len(backend.applied()) == before + 1
    blocker = journal.unresolved_for_target("warehouse.equipment.release", "FL-01")
    assert blocker is not None and blocker.execution_id == result.execution_id
    # a crash-restart of the journal keeps the UNKNOWN unresolved
    reopened = JsonFileExecutionRegistry(journal_dir)
    assert [r.execution_id for r in reopened.unresolved()] == [result.execution_id]
