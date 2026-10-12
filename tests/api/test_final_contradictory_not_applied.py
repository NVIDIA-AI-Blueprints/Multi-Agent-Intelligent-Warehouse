# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.0.1 final pre-merge — NEW5-P2-01: a contradictory ``NOT_APPLIED`` claim is
NOT a certification of non-execution.

Fifth independent re-audit (PR #143 @ 42b290f), ``reference_governed`` with
the repository's equipment MCP server over real streamable HTTP:

* an ``isError`` result whose ``structuredContent`` said
  ``execution_disposition=NOT_APPLIED`` next to ``outcome=executed``,
  ``mutation_status=applied`` and ``rejection_code=BOGUS``, and
* a NON-error result with ``success=true``, ``outcome=failed`` and
  ``NOT_APPLIED``

were both answered ``200 failed`` (definite non-execution) and the operator
retry wrote a SECOND time.

These tests drive the canonical shipped app (real lifespan, real
``MAIWMCPClient``, real streamable-HTTP transport, real durable journal)
against the repository's own equipment MCP server module run as a separate
process with the durable recording backend ``tests/api/round3_mcp_backend.py``
(``CONTRADICTORY`` variants), and prove the spec §4 cases:

* A  NOT_APPLIED + ``executed=true``                     → UNKNOWN
* B  NOT_APPLIED + mutation count / reference            → UNKNOWN
* C  NOT_APPLIED + success flag / applied outcome / post-state → UNKNOWN
* D  NOT_APPLIED + malformed / unknown rejection metadata or unknown field
                                                          → UNKNOWN
* E  a clean, explicit rejection before mutation          → definite FAILED /
                                                            CONFLICT

and, for every contradictory result: UNKNOWN persisted, identical retry 409,
no further MCP write (physical write count <= 1), and reconciliation to
CONFIRMED_EXECUTED / CONFIRMED_NOT_EXECUTED / INDETERMINATE from an
authoritative reread — also across an API restart.
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
from tests.api.round3_mcp_backend import CONTRADICTORY
from tests.api.test_round3_unknown_writes import (
    Backend,
    _approved_release,
    _count_proposals,
    _release,
)

ERROR_VARIANTS = sorted(v for v, (is_error, _) in CONTRADICTORY.items() if is_error)
RESULT_VARIANTS = sorted(
    v for v, (is_error, _) in CONTRADICTORY.items() if not is_error
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


async def _pending(client, auth) -> list[dict]:
    return (await client.get("/api/v1/executions", headers=auth)).json()["executions"]


async def _journal_unresolved_count(client) -> int:
    ready = (await client.get("/api/v1/ready")).json()
    return ready["components"]["governed_write_path"]["execution_journal"]["equipment"][
        "unresolved"
    ]


def _expected_error_code(variant: str) -> str:
    return (
        "MCP_TOOL_ERROR" if CONTRADICTORY[variant][0] else "SERVER_RESULT_CONTRADICTORY"
    )


def _expected_dispatch(variant: str) -> str:
    return (
        "dispatched_server_error"
        if CONTRADICTORY[variant][0]
        else "dispatched_response_received"
    )


# ── A–D: contradictory NOT_APPLIED after the write landed ───────────────────


@pytest.mark.parametrize("variant", ERROR_VARIANTS + RESULT_VARIANTS)
async def test_contradictory_not_applied_after_write_is_unknown_and_reconciles(
    governed, backend, variant
):
    auth, root = governed
    async with running_canonical_app() as (app, client):
        proposals = _count_proposals(app.state.runtime)
        backend.arm(f"contradict_after_write:{variant}")
        r = await _release(client, auth, **{"X-Trace-Id": f"r5-{variant}"})

        assert backend.alive()
        assert len(backend.applied()) == 1
        assert backend.asset("FL-01")["status"] == "available"

        # UNKNOWN — never "failed", executed is not false
        assert r.status_code == 202, (variant, r.text)
        body = r.json()
        assert body["status"] == "unknown"
        assert body["executed"] is None
        assert body["error_code"] == _expected_error_code(variant)
        assert body["dispatch_status"] == _expected_dispatch(variant)
        # the NOT_APPLIED claim really reached the client and was refused
        assert body["server_disposition"].startswith("untrusted_not_applied:"), body
        assert body["reconciliation_required"] is True
        assert body["retried"] is False
        exec_id = body["execution_id"]

        pending = await _pending(client, auth)
        assert [e["execution_id"] for e in pending] == [exec_id]
        assert pending[0]["unresolved"] is True
        assert pending[0]["physical_mutation_occurred"] is None
        assert pending[0]["uncertainty_reason"]
        assert await _journal_unresolved_count(client) == 1

        # identical operator retry: 409 before governance, no new MCP write
        retry = await _release(client, auth)
        assert retry.status_code == 409, retry.text
        assert retry.json()["code"] == "RECONCILIATION_REQUIRED"
        assert retry.json()["execution_id"] == exec_id
        assert proposals["n"] == 1
        assert len(backend.entries()) == 1

        # authoritative reread: the write landed
        rec = await client.post(f"/api/v1/executions/{exec_id}/reconcile", headers=auth)
        assert rec.status_code == 200, rec.text
        assert rec.json()["reconciliation_outcome"] == "confirmed_executed"
        assert rec.json()["outcome"] == "unknown"
        assert rec.json()["retried"] is False
        assert await _journal_unresolved_count(client) == 0

    assert len(backend.applied()) == 1
    record = json.loads((root / "executions/equipment" / f"{exec_id}.json").read_text())
    assert record["outcome"] == "unknown"
    assert record["reconciliation"]["outcome"] == "confirmed_executed"


# ── contradictory NOT_APPLIED where nothing was written ─────────────────────


@pytest.mark.parametrize(
    "variant", ["err_C_fifth_audit_exact", "ok_C_fifth_audit_success_true_failed"]
)
async def test_contradictory_not_applied_without_write_reconciles_not_executed(
    governed, backend, variant
):
    auth, _ = governed
    async with running_canonical_app() as (_, client):
        backend.arm(f"contradict_before_write:{variant}")
        r = await _release(client, auth)
        assert r.status_code == 202, r.text
        assert r.json()["status"] == "unknown"
        exec_id = r.json()["execution_id"]
        assert backend.applied() == []
        assert (await _release(client, auth)).status_code == 409
        assert len(backend.entries()) == 1

        rec = await client.post(f"/api/v1/executions/{exec_id}/reconcile", headers=auth)
        assert rec.json()["reconciliation_outcome"] == "confirmed_not_executed"
        assert backend.asset("FL-01")["status"] == "assigned"

        # the target is free again: a NEW request writes exactly once
        again = await _release(client, auth)
        assert again.status_code == 200, again.text
        assert again.json()["status"] == "executed"
    assert len(backend.applied()) == 1


# ── reread unavailable → INDETERMINATE, still blocked ───────────────────────


@pytest.mark.parametrize("variant", ["err_A_executed_true", "ok_B_rows_affected"])
async def test_contradictory_not_applied_inconclusive_reread_is_indeterminate(
    governed, backend, variant
):
    auth, _ = governed
    async with running_canonical_app() as (_, client):
        backend.arm(f"contradict_after_write:{variant}")
        r = await _release(client, auth)
        assert r.status_code == 202, r.text
        exec_id = r.json()["execution_id"]

        backend.stop()  # the authoritative read fails
        rec = await client.post(f"/api/v1/executions/{exec_id}/reconcile", headers=auth)
        assert rec.status_code == 200
        assert rec.json()["reconciliation_outcome"] == "indeterminate"
        assert rec.json()["unresolved"] is True
        assert (await _release(client, auth)).status_code == 409

        backend.start()
        rec2 = await client.post(
            f"/api/v1/executions/{exec_id}/reconcile", headers=auth
        )
        assert rec2.json()["reconciliation_outcome"] == "confirmed_executed"
    assert len(backend.applied()) == 1
    assert len(backend.entries()) == 1


# ── contradictory UNKNOWN persisted → API restart → still blocked ───────────


async def test_contradictory_not_applied_unknown_survives_restart(governed, backend):
    auth, _ = governed
    async with running_canonical_app() as (_, client):
        backend.arm("contradict_after_write:ok_C_fifth_audit_success_true_failed")
        first = (await _release(client, auth)).json()
        assert first["status"] == "unknown"
    async with running_canonical_app() as (app, client):
        proposals = _count_proposals(app.state.runtime)
        pending = await _pending(client, auth)
        assert [e["execution_id"] for e in pending] == [first["execution_id"]]
        retry = await _release(client, auth)
        assert retry.status_code == 409
        assert proposals["n"] == 0
        rec = await client.post(
            f"/api/v1/executions/{first['execution_id']}/reconcile", headers=auth
        )
        assert rec.json()["reconciliation_outcome"] == "confirmed_executed"
    assert len(backend.applied()) == 1
    assert len(backend.entries()) == 1


# ── E: clean, explicit rejection before mutation stays definite ─────────────


async def test_clean_error_not_applied_is_still_definite_failure(governed, backend):
    auth, _ = governed
    async with running_canonical_app() as (_, client):
        backend.arm("reject_not_applied")  # the shipped server's not_applied_result
        r = await _release(client, auth)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "failed"
        assert body["executed"] is False
        assert body["error_code"] == "MCP_TOOL_NOT_APPLIED"
        assert body["server_disposition"] == "NOT_APPLIED"
        assert await _pending(client, auth) == []
        again = await _release(client, auth)
        assert again.json()["status"] == "executed"
    assert len(backend.applied()) == 1


async def test_clean_non_error_not_applied_is_still_definite(governed, backend):
    auth, _ = governed
    async with running_canonical_app() as (_, client):
        backend.arm("conflict_not_applied")
        r = await _release(client, auth)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "conflict"
        assert r.json()["executed"] is False
        assert await _pending(client, auth) == []
    assert backend.applied() == []


# ── real client + executor + JSON journal (no HTTP layer) ───────────────────


async def test_real_client_types_contradictory_results_as_unknown(backend, tmp_path):
    from maiw_execution import EquipmentActionExecutor, JsonFileExecutionRegistry
    from maiw_mcp.client.client import MAIWMCPClient
    from maiw_mcp.errors import (
        MCPResultOutcomeUnknown,
        MCPToolErrorOutcomeUnknown,
        MCPToolNotApplied,
    )
    from maiw_mcp.registry.registry import CapabilityRegistry
    from maiw_skills.equipment.skills import ExecuteEquipmentReleaseSkill

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

    for variant in ERROR_VARIANTS:
        backend.arm(f"contradict_before_write:{variant}")
        with pytest.raises(MCPToolErrorOutcomeUnknown) as err:
            await client.invoke("warehouse.equipment.release", payload)
        assert not isinstance(err.value, MCPToolNotApplied)
        assert err.value.observed_disposition.startswith("untrusted_not_applied:")
    for variant in RESULT_VARIANTS:
        backend.arm(f"contradict_before_write:{variant}")
        with pytest.raises(MCPResultOutcomeUnknown) as res:
            await client.invoke("warehouse.equipment.release", payload)
        assert res.value.observed_disposition.startswith("untrusted_not_applied:")

    backend.arm("reject_not_applied")
    with pytest.raises(MCPToolNotApplied) as clean:
        await client.invoke("warehouse.equipment.release", payload)
    assert clean.value.rejection_code == "PRECONDITION_FAILED"

    journal_dir = tmp_path / "journal"
    journal = JsonFileExecutionRegistry(journal_dir)
    executor = EquipmentActionExecutor(
        assign_skill=None,
        release_skill=ExecuteEquipmentReleaseSkill(client),
        registry=journal,
    )
    proposal, decision = _approved_release()
    before = len(backend.applied())
    backend.arm("contradict_after_write:ok_C_fifth_audit_success_true_failed")
    result = await executor.execute(proposal, decision, trace_id="r5-exec")
    assert result.outcome.value == "unknown"
    assert result.error_code == "SERVER_RESULT_CONTRADICTORY"
    assert result.physical_mutation_occurred is None
    assert len(backend.applied()) == before + 1
    blocker = journal.unresolved_for_target("warehouse.equipment.release", "FL-01")
    assert blocker is not None and blocker.execution_id == result.execution_id
    reopened = JsonFileExecutionRegistry(journal_dir)
    assert [r.execution_id for r in reopened.unresolved()] == [result.execution_id]
