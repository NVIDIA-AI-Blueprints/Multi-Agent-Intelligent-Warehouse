# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
F06 (ambiguous write) end to end on the DataPack-backed demo world.

Regression for the demo bug where the UI hard-coded ``asset_id: 'AGV-01'`` —
an id that exists only in the scenario YAMLs — while demo mode builds the
active world from the DC-47 DataPack, so every equipment injection failed with
``422 Asset 'AGV-01' not found``.

Drives the canonical shipped app ``maiw_api.app:app`` (real lifespan, real
in-memory MCP transport, real EquipmentActionExecutor + execution journal):

    inject F06 (no asset_id)  → backend resolves a real DataPack asset and arms
                                a one-shot ambiguous write scoped to it
    queue + /demo/approve     → mutation committed, response lost → UNKNOWN
    retries                   → approval single-use (404); operator write
                                409 RECONCILIATION_REQUIRED; no second write
    /demo/reconcile           → CONFIRMED_EXECUTED, never re-executes

The operator write credential rules are unchanged: without the header the
write is refused before any proposal or mutation.
"""

from __future__ import annotations

import secrets

import pytest

from tests.api.canonical_harness import (
    FakeNIM,
    canonical_env,
    install_gateway,
    running_canonical_app,
)

SCENARIO = "labor_constraint_wave_risk"


@pytest.fixture
def fake_nim():
    fake = FakeNIM()
    yield fake
    fake.close()


@pytest.fixture
def demo_app_env(monkeypatch, tmp_path, fake_nim):
    """Canonical app in demo mode (DataPack world) with an operator credential."""
    import maiw_api.bootstrap as bootstrap
    from maiw_api.demo.controller import reset_demo_controller

    canonical_env(monkeypatch, tmp_path, fake_nim)
    operator = secrets.token_hex(32)
    monkeypatch.setenv("MAIW_DEMO_MODE", "true")
    monkeypatch.setenv("MAIW_DEPLOYMENT_PROFILE", "demo")
    monkeypatch.setenv("MAIW_OPERATOR_WRITE_TOKEN", operator)
    # bootstrap reads MAIW_DEMO_MODE at import time
    monkeypatch.setattr(bootstrap, "_DEMO_MODE", True)
    reset_demo_controller()
    install_gateway(fake_nim)
    yield {"X-Maiw-Operator-Token": operator}
    from maiw_models import reset_model_gateway

    reset_model_gateway()
    reset_demo_controller()


async def _queue_assign(app, target: str) -> str:
    """
    Queue a pending equipment.assign on ``target`` the way /demo/analyze's
    DECIDE step does: real DecisionEngine evaluation → REQUIRES_HUMAN_APPROVAL
    → controller approval queue.  Only the model-produced recommendation is
    replaced by a fixed, DC-47-bound proposal.
    """
    from maiw_decision.models import DecisionOutcome, DecisionRequest
    from maiw_decision.proposal import ActionProposal
    from maiw_state import StateRequirements, WarehouseStateSnapshot

    runtime = app.state.runtime
    ctrl = runtime.demo_controller
    warehouse_id = ctrl.world.WAREHOUSE_ID
    state = await runtime.state_provider.get_state(
        warehouse_id, StateRequirements(equipment=True, labor=True, waves=True)
    )
    proposal = ActionProposal.for_equipment_assign(
        asset_id=target,
        assignee="operator-1",
        assignment_type="task",
        task_id="task-000000",
        duration_hours=None,
        notes=None,
        reason="F06 e2e",
        requested_by="operations-agent",
        warehouse_id=warehouse_id,
        trace_id="f06-e2e-trace",
    )
    decision, _audit = runtime.decision_engine.evaluate(
        DecisionRequest(
            proposal=proposal,
            state=WarehouseStateSnapshot.seal(state),
            requested_by="operations-agent",
            trace_id="f06-e2e-trace",
        )
    )
    assert decision.outcome == DecisionOutcome.REQUIRES_HUMAN_APPROVAL
    return ctrl.add_pending_approval(
        proposal_id=proposal.proposal_id,
        decision_id=decision.result_id,
        trace_id="f06-e2e-trace",
        capability=proposal.action,
        target=target,
        domain="equipment",
        priority="high",
        objective="cover wave risk",
        rationale="F06 e2e",
        risk_level="medium",
        warehouse_id=warehouse_id,
        proposal_data=proposal.model_dump(mode="json"),
    )


async def _operator_assign(client, auth, asset_id):
    return await client.post(
        "/api/v1/equipment/assign",
        json={"asset_id": asset_id, "assignee": "operator-1", "task_id": "f06"},
        headers=auth,
    )


async def test_f06_resolves_datapack_asset_unknown_no_retry_reconciles(demo_app_env):
    auth = demo_app_env
    async with running_canonical_app() as (app, client):
        r = await client.post(f"/api/v1/demo/scenario/{SCENARIO}/start")
        assert r.status_code == 200, r.text
        ctrl = app.state.runtime.demo_controller
        assert ctrl.world._scenario_world is not None  # DataPack is the world source
        assert "AGV-01" not in ctrl.world.equipment
        provider = ctrl.providers.equipment

        # ── inject F06 exactly as the UI does: no asset_id ───────────────────
        r = await client.post(
            "/api/v1/demo/inject",
            json={
                "event_type": "equipment_fault",
                "payload": {"equipment_type": "agv", "simulate_ambiguous_write": True},
            },
        )
        assert r.status_code == 200, r.text
        result = r.json()["result"]
        target = result["asset_id"]
        assert target == "agv-000"  # lowest available AGV — deterministic
        assert result["target_resolution"] == "resolved"
        assert result["ambiguous_write_armed"] is True
        # the fault is in the write path; the asset stays writable
        assert ctrl.world.equipment[target].status == "available"
        assert provider._mutation_count == 0

        # ── governed write on the resolved asset: analyze → queue → approve ───
        pending_id = await _queue_assign(app, target)
        r = await client.post("/api/v1/demo/approve", json={"pending_id": pending_id})
        assert r.status_code == 202, r.text  # UNKNOWN — never a false success
        assert r.json()["status"] == "unknown"
        assert r.json()["executed"] is None
        assert r.json()["reconciliation_required"] is True
        exec_id = r.json()["execution_id"]
        assert provider._mutation_count == 1  # the mutation DID land
        assert ctrl.world.equipment[target].status == "assigned"

        # the journal records UNKNOWN against the resolved asset
        r = await client.get(f"/api/v1/executions/{exec_id}", headers=auth)
        assert r.status_code == 200, r.text
        record = r.json()
        assert record["outcome"] == "unknown"
        assert record["target"] == target

        # ── no blind retry, no unauthorised write ─────────────────────────────
        r = await client.post("/api/v1/demo/approve", json={"pending_id": pending_id})
        assert r.status_code == 404, r.text  # approval is single-use
        r = await _operator_assign(client, {}, target)
        assert r.status_code == 403, r.text  # operator credential still required
        assert r.json()["code"] == "OPERATOR_WRITE_CREDENTIAL_REQUIRED"
        r = await _operator_assign(client, auth, target)
        assert r.status_code == 409, r.text
        assert r.json()["code"] == "RECONCILIATION_REQUIRED"
        assert r.json()["execution_id"] == exec_id
        assert provider._mutation_count == 1  # no duplicate write

        # ── reconcile (the UI's RECONCILE NOW call) ───────────────────────────
        r = await client.post(
            "/api/v1/demo/reconcile",
            json={"execution_id": exec_id, "domain": "equipment"},
        )
        assert r.status_code == 200, r.text
        r = await client.get(f"/api/v1/executions/{exec_id}", headers=auth)
        record = r.json()
        assert record["outcome"] == "unknown"  # original UNKNOWN preserved
        assert record["reconciliation"]["outcome"] == "confirmed_executed"
        assert provider._mutation_count == 1  # reconciliation never writes


async def test_f06_fault_is_scoped_to_the_resolved_asset(demo_app_env):
    """A write to another asset is not hijacked by the armed F06 fault."""
    auth = demo_app_env
    async with running_canonical_app() as (app, client):
        await client.post(f"/api/v1/demo/scenario/{SCENARIO}/start")
        ctrl = app.state.runtime.demo_controller
        provider = ctrl.providers.equipment
        r = await client.post(
            "/api/v1/demo/inject",
            json={
                "event_type": "equipment_fault",
                "payload": {"simulate_ambiguous_write": True},
            },
        )
        target = r.json()["result"]["asset_id"]
        other = "forklift-000"
        assert other != target

        pending_id = await _queue_assign(app, other)
        r = await client.post("/api/v1/demo/approve", json={"pending_id": pending_id})
        exec_id = r.json()["execution_id"]
        r = await client.get(f"/api/v1/executions/{exec_id}", headers=auth)
        assert r.json()["outcome"] == "executed"
        assert provider._mutation_count == 1
        assert provider._post_mutation_fault_asset_id == target  # still armed


async def test_inject_targeting_errors_are_typed(demo_app_env):
    """Unknown explicit asset / nothing eligible → typed non-2xx, not a raw 422."""
    async with running_canonical_app() as (app, client):
        await client.post(f"/api/v1/demo/scenario/{SCENARIO}/start")

        r = await client.post(
            "/api/v1/demo/inject",
            json={"event_type": "equipment_fault", "payload": {"asset_id": "AGV-01"}},
        )
        assert r.status_code == 404, r.text
        body = r.json()
        assert body["error"] is True
        assert body["code"] == "ASSET_NOT_IN_ACTIVE_WORLD"
        assert body["asset_id"] == "AGV-01"
        assert body["world_source"] == "datapack"
        assert "AGV-01" in body["message"]

        # nothing is faulted yet → nothing to restore
        r = await client.post(
            "/api/v1/demo/inject",
            json={"event_type": "equipment_restore", "payload": {}},
        )
        assert r.status_code == 409, r.text
        assert r.json()["code"] == "NO_ELIGIBLE_ASSET"

        # fault (resolved) then restore (resolved) round-trips the same asset
        r = await client.post(
            "/api/v1/demo/inject",
            json={"event_type": "equipment_fault", "payload": {}},
        )
        assert r.status_code == 200, r.text
        faulted = r.json()["result"]["asset_id"]
        r = await client.post(
            "/api/v1/demo/inject",
            json={"event_type": "equipment_restore", "payload": {}},
        )
        assert r.status_code == 200, r.text
        assert r.json()["result"]["asset_id"] == faulted
