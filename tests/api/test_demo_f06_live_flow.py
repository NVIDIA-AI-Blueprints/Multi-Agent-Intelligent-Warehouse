# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
F06 (ambiguous write) through the LIVE demo path: inject → /demo/analyze →
/demo/approve → UNKNOWN → RECONCILIATION_REQUIRED → no retry → reconcile.

Regressions for three demo bugs that kept the Reliability → F06 flow from
working in the live UI:

1. /demo/analyze built equipment proposals with ``warehouse_id="default"``
   while the approval was bound to the active world's warehouse (DC-47), so
   /demo/approve rejected them with ``approval.warehouse_mismatch``.
2. /demo/approve hard-coded ``"status": "executed"`` even when the execution
   outcome was UNKNOWN (``success: false``).
3. Nothing published RECONCILIATION_REQUIRED, so RECONCILE NOW never enabled.

Drives the canonical shipped app ``maiw_api.app:app`` (real lifespan, real
in-memory MCP transport, real DecisionEngine, EquipmentActionExecutor and
execution journal).  The model is a local fake OpenAI-compatible provider
reached through the real ModelGateway chain; only its answer (one
recommendation) is scripted.
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

SCENARIO = "labor_constraint_wave_risk"


def _assessment(target: str, capability: str = "warehouse.equipment.assign") -> str:
    """The fake model's analyze_disruption answer: one equipment recommendation."""
    return json.dumps(
        {
            "summary": f"Cover the wave risk with {target}",
            "recommendations": [
                {
                    "domain": "equipment",
                    "capability": capability,
                    "target": target,
                    "objective": f"Put {target} on the at-risk pick wave",
                    "rationale": "Two operators absent; carrier cutoff in 45 min",
                    "priority": "high",
                    "subtype": "task",
                }
            ],
        }
    )


@pytest.fixture
def fake_nim():
    fake = FakeNIM(content=_assessment("agv-000"))
    yield fake
    fake.close()


@pytest.fixture
def demo_app_env(monkeypatch, tmp_path, fake_nim):
    """Canonical app in demo mode with an operator credential."""
    import maiw_api.bootstrap as bootstrap
    from maiw_api.demo.controller import reset_demo_controller

    canonical_env(monkeypatch, tmp_path, fake_nim)
    operator = secrets.token_hex(32)
    monkeypatch.setenv("MAIW_DEMO_MODE", "true")
    monkeypatch.setenv("MAIW_DEPLOYMENT_PROFILE", "demo")
    monkeypatch.setenv("MAIW_OPERATOR_WRITE_TOKEN", operator)
    monkeypatch.setattr(bootstrap, "_DEMO_MODE", True)
    reset_demo_controller()
    install_gateway(fake_nim)
    yield {"X-Maiw-Operator-Token": operator}
    from maiw_models import reset_model_gateway

    reset_model_gateway()
    reset_demo_controller()


@pytest.fixture
def yaml_fallback(monkeypatch):
    """Force the legacy YAML world (DataPack path unavailable for SCENARIO)."""
    import maiw_api.demo.world_loader as world_loader

    monkeypatch.setattr(world_loader, "SCENARIO_OVERLAYS", {})


def _drain(queue) -> list[dict]:
    """SSE payloads (exactly what /events/stream serializes) queued so far."""
    out = []
    while not queue.empty():
        event = queue.get_nowait()
        if event is not None:
            out.append(json.loads(json.dumps(event.to_sse_dict(), default=str)))
    return out


def _of(events: list[dict], category: str) -> list[dict]:
    return [e for e in events if e["category"] == category]


async def _analyze_pending(client, ctrl) -> dict:
    """Run /demo/analyze; return the single pending approval it queued."""
    r = await client.post("/api/v1/demo/analyze")
    assert r.status_code == 200, r.text
    body = r.json()
    statuses = [p["status"] for p in body["proposal_results"]]
    assert statuses == ["requires_human_approval"], body["proposal_results"]
    pending = ctrl.status()["pending_approvals"]
    assert len(pending) == 1, pending
    return pending[0]


# ── Bug 1: analyze binds proposals to the active world's warehouse ────────────


async def test_analyze_binds_equipment_proposal_to_datapack_warehouse(demo_app_env):
    async with running_canonical_app() as (app, client):
        r = await client.post(f"/api/v1/demo/scenario/{SCENARIO}/start")
        assert r.status_code == 200, r.text
        ctrl = app.state.runtime.demo_controller
        assert ctrl.world._scenario_world is not None  # DataPack world
        assert ctrl.world.WAREHOUSE_ID == "DC-47"

        pending = await _analyze_pending(client, ctrl)
        assert pending["warehouse_id"] == "DC-47"
        assert pending["proposal_data"]["parameters"]["warehouse_id"] == "DC-47"
        approval = ctrl.approval_store.get(pending["approval_id"])
        assert approval.warehouse_id == "DC-47"

        r = await client.post(
            "/api/v1/demo/approve", json={"pending_id": pending["pending_id"]}
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # accepted by authorize_with_approval (no approval.warehouse_mismatch)
        assert "violations" not in body, body
        assert body["ok"] is True
        assert body["status"] == "executed"
        assert body["executed"] is True
        assert body["reconciliation_required"] is False
        assert ctrl.world.equipment["agv-000"].status == "assigned"


async def test_analyze_binds_proposal_to_yaml_fallback_warehouse(
    demo_app_env, yaml_fallback, fake_nim, monkeypatch
):
    """YAML fallback: the binding is the YAML world's own WAREHOUSE_ID."""
    from maiw_api.demo.world import DemoWarehouseWorld

    # A distinct id proves the binding is read from the active world, not a literal.
    monkeypatch.setattr(DemoWarehouseWorld, "WAREHOUSE_ID", "WH-YAML-FALLBACK")
    fake_nim.content = _assessment("AGV-01")
    async with running_canonical_app() as (app, client):
        r = await client.post(f"/api/v1/demo/scenario/{SCENARIO}/start")
        assert r.status_code == 200, r.text
        ctrl = app.state.runtime.demo_controller
        assert ctrl.world._scenario_world is None  # YAML world
        assert "AGV-01" in ctrl.world.equipment

        pending = await _analyze_pending(client, ctrl)
        assert pending["warehouse_id"] == "WH-YAML-FALLBACK"
        assert (
            pending["proposal_data"]["parameters"]["warehouse_id"] == "WH-YAML-FALLBACK"
        )

        r = await client.post(
            "/api/v1/demo/approve", json={"pending_id": pending["pending_id"]}
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "executed"
        assert ctrl.world.equipment["AGV-01"].status == "assigned"


async def test_approval_warehouse_binding_is_still_enforced(demo_app_env):
    """The fix binds proposals correctly; it does not weaken the check."""
    async with running_canonical_app() as (app, client):
        await client.post(f"/api/v1/demo/scenario/{SCENARIO}/start")
        ctrl = app.state.runtime.demo_controller
        pending = await _analyze_pending(client, ctrl)
        # Tamper: the queued proposal now claims another warehouse.
        for pa in ctrl._pending_approvals:
            pa["proposal_data"]["parameters"]["warehouse_id"] = "default"
        writes_before = ctrl.providers.equipment._mutation_count

        r = await client.post(
            "/api/v1/demo/approve", json={"pending_id": pending["pending_id"]}
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is False
        assert [v["rule"] for v in body["violations"]] == [
            "approval.warehouse_mismatch"
        ]
        assert ctrl.providers.equipment._mutation_count == writes_before


# ── Bugs 2 + 3: the full F06 flow on the DataPack world ───────────────────────


async def test_f06_live_flow_inject_analyze_approve_unknown_reconcile(demo_app_env):
    auth = demo_app_env
    async with running_canonical_app() as (app, client):
        r = await client.post(f"/api/v1/demo/scenario/{SCENARIO}/start")
        assert r.status_code == 200, r.text
        ctrl = app.state.runtime.demo_controller
        provider = ctrl.providers.equipment
        sse = ctrl.bus.subscribe()  # what /events/stream reads
        try:
            # ── inject F06 exactly as the Reliability panel does ─────────────
            r = await client.post(
                "/api/v1/demo/inject",
                json={
                    "event_type": "equipment_fault",
                    "payload": {
                        "equipment_type": "agv",
                        "simulate_ambiguous_write": True,
                    },
                },
            )
            assert r.status_code == 200, r.text
            target = r.json()["result"]["asset_id"]
            assert target == "agv-000"

            # ── analyze (fake model recommends assigning the faulted AGV) ─────
            pending = await _analyze_pending(client, ctrl)
            assert pending["target"] == target
            assert pending["warehouse_id"] == "DC-47"
            assert provider._mutation_count == 0
            assert _of(_drain(sse), "RECONCILIATION_REQUIRED") == []

            # ── approve → the write lands, its response is lost → UNKNOWN ─────
            r = await client.post(
                "/api/v1/demo/approve", json={"pending_id": pending["pending_id"]}
            )
            assert r.status_code == 202, r.text
            body = r.json()
            exec_id = body["execution_id"]
            assert body["ok"] is False
            assert body["status"] == "unknown"
            assert body["outcome"] == "unknown"
            assert body["executed"] is None  # never "executed", never "not executed"
            assert body["success"] is False
            assert body["reconciliation_required"] is True
            assert body["retried"] is False
            assert body["target"] == target
            assert body["domain"] == "equipment"
            assert body["reconcile"] == {
                "method": "POST",
                "path": "/api/v1/demo/reconcile",
                "body": {"execution_id": exec_id, "domain": "equipment"},
            }
            assert provider._mutation_count == 1  # the mutation DID land
            assert ctrl._pending_approval_outcomes[pending["pending_id"]] == "unknown"

            # ── RECONCILIATION_REQUIRED published exactly once, with the ids ──
            events = _drain(sse)
            required = _of(events, "RECONCILIATION_REQUIRED")
            assert len(required) == 1, required
            ev = required[0]
            assert ev["execution_id"] == exec_id
            assert ev["domain"] == "equipment"
            assert ev["asset_id"] == target
            detail = json.loads(ev["detail"])
            assert detail["execution_id"] == exec_id
            assert detail["domain"] == "equipment"
            assert detail["target"] == target
            assert detail["proposal_id"] == body["proposal_id"]
            assert detail["approval_id"] == body["approval_id"]
            assert detail["outcome"] == "unknown"
            assert detail["reconcile"]["path"] == "/api/v1/demo/reconcile"
            execute = _of(events, "EXECUTE")
            assert any("outcome=unknown" in (e["detail"] or "") for e in execute)

            # ── no blind retry ────────────────────────────────────────────────
            r = await client.post(
                "/api/v1/demo/approve", json={"pending_id": pending["pending_id"]}
            )
            assert r.status_code == 404, r.text  # approval is single-use
            r = await client.post(
                "/api/v1/equipment/assign",
                json={"asset_id": target, "assignee": "op-1", "task_id": "f06"},
                headers=auth,
            )
            assert r.status_code == 409, r.text
            assert r.json()["code"] == "RECONCILIATION_REQUIRED"
            assert r.json()["execution_id"] == exec_id
            # a NEW governed demo write to the same asset is refused as well
            pending_release = await _queue_release(app, target)
            r = await client.post(
                "/api/v1/demo/approve", json={"pending_id": pending_release}
            )
            assert r.status_code == 409, r.text
            assert r.json()["code"] == "RECONCILIATION_REQUIRED"
            assert r.json()["execution_id"] == exec_id
            assert provider._mutation_count == 1  # no second write
            # the refused attempts are not new UNKNOWNs — no further event
            assert _of(_drain(sse), "RECONCILIATION_REQUIRED") == []

            # ── reconcile (RECONCILE NOW) ─────────────────────────────────────
            r = await client.post(
                "/api/v1/demo/reconcile",
                json={"execution_id": exec_id, "domain": "equipment"},
            )
            assert r.status_code == 200, r.text
            assert r.json()["reconciliation_outcome"] == "confirmed_executed"
            assert r.json()["effective_status"] == "effectively_executed"
            events = _drain(sse)
            assert len(_of(events, "RECONCILE")) == 1
            confirmed = _of(events, "CONFIRMED_EXECUTED")
            assert len(confirmed) == 1
            assert confirmed[0]["execution_id"] == exec_id
            assert json.loads(confirmed[0]["detail"])["reconciliation_outcome"] == (
                "confirmed_executed"
            )
            assert _of(events, "RECONCILIATION_REQUIRED") == []

            r = await client.get(f"/api/v1/executions/{exec_id}", headers=auth)
            record = r.json()
            assert record["outcome"] == "unknown"  # original UNKNOWN preserved
            assert record["reconciliation"]["outcome"] == "confirmed_executed"
            assert provider._mutation_count == 1  # exactly one backend write
        finally:
            ctrl.bus.unsubscribe(sse)


async def _queue_release(app, target: str) -> str:
    """Queue an equipment.release on ``target`` bound to the active warehouse."""
    from maiw_decision.models import DecisionOutcome, DecisionRequest
    from maiw_decision.proposal import ActionProposal
    from maiw_state import StateRequirements, WarehouseStateSnapshot

    runtime = app.state.runtime
    ctrl = runtime.demo_controller
    warehouse_id = ctrl.world.WAREHOUSE_ID
    state = await runtime.state_provider.get_state(
        warehouse_id, StateRequirements(equipment=True, labor=True, waves=True)
    )
    proposal = ActionProposal.for_equipment_release(
        asset_id=target,
        released_by="operations-agent",
        reason="F06 retry probe",
        requested_by="operations-agent",
        warehouse_id=warehouse_id,
        trace_id="f06-live-retry",
    )
    decision, _audit = runtime.decision_engine.evaluate(
        DecisionRequest(
            proposal=proposal,
            state=WarehouseStateSnapshot.seal(state),
            requested_by="operations-agent",
            trace_id="f06-live-retry",
        )
    )
    # release is low risk (auto-APPROVED by policy); it is queued for approval
    # here only to drive a second governed write through /demo/approve.
    assert decision.outcome in (
        DecisionOutcome.APPROVED,
        DecisionOutcome.REQUIRES_HUMAN_APPROVAL,
    ), decision
    return ctrl.add_pending_approval(
        proposal_id=proposal.proposal_id,
        decision_id=decision.result_id,
        trace_id="f06-live-retry",
        capability=proposal.action,
        target=target,
        domain="equipment",
        priority="high",
        objective="release",
        rationale="F06 retry probe",
        risk_level="low",
        warehouse_id=warehouse_id,
        proposal_data=proposal.model_dump(mode="json"),
    )


async def test_reconciliation_required_is_published_once_per_execution(
    demo_app_env,
):
    """The publish helper is idempotent per execution_id (any demo route)."""
    from maiw_api.routers.demo import _publish_reconciliation_required

    async with running_canonical_app() as (app, client):
        await client.post(f"/api/v1/demo/scenario/{SCENARIO}/start")
        ctrl = app.state.runtime.demo_controller
        sse = ctrl.bus.subscribe()
        try:
            kwargs = dict(
                domain="equipment",
                capability="warehouse.equipment.assign",
                target="agv-000",
                proposal_id="p-1",
                decision_id="d-1",
                approval_id="a-1",
                trace_id="t-1",
                error_code=None,
            )
            first = await _publish_reconciliation_required(
                ctrl, execution_id="exec-1", **kwargs
            )
            again = await _publish_reconciliation_required(
                ctrl, execution_id="exec-1", **kwargs
            )
            other = await _publish_reconciliation_required(
                ctrl, execution_id="exec-2", **kwargs
            )
            assert (first, again, other) == (True, False, True)
            ids = [
                e["execution_id"] for e in _of(_drain(sse), "RECONCILIATION_REQUIRED")
            ]
            assert ids == ["exec-1", "exec-2"]
        finally:
            ctrl.bus.unsubscribe(sse)


async def test_analyze_auto_executed_unknown_publishes_reconciliation_required():
    """An APPROVED proposal executed inside /demo/analyze that ends UNKNOWN
    publishes RECONCILIATION_REQUIRED too, and reports executed=None."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from maiw_decision.models import DecisionOutcome
    from maiw_execution.base import ActionExecutionResult
    from maiw_execution.outcome import ExecutionOutcome

    import maiw_api.routers.demo as demo_mod
    from maiw_api.demo.controller import DemoScenarioController

    ctrl = DemoScenarioController()
    await ctrl.start(SCENARIO)
    sse = ctrl.bus.subscribe()

    exec_result = ActionExecutionResult(
        outcome=ExecutionOutcome.UNKNOWN,
        action="warehouse.equipment.assign",
        proposal_id="prop-1",
        decision_id="dec-1",
        error_code="AMBIGUOUS_WRITE",
    )
    executor = MagicMock()
    executor.execute = AsyncMock(return_value=exec_result)
    decision = MagicMock(outcome=DecisionOutcome.APPROVED, result_id="dec-1")
    decision.violations = []
    runtime = MagicMock()
    runtime.decision_engine.evaluate = MagicMock(return_value=(decision, None))
    proposal = MagicMock(proposal_id="prop-1", action="warehouse.equipment.assign")
    proposal.parameters = {"asset_id": "agv-000", "warehouse_id": "DC-47"}
    rec = MagicMock(capability="warehouse.equipment.assign", domain="equipment")
    rec.target = "agv-000"

    with (
        patch.object(demo_mod, "_build_proposal", AsyncMock(return_value=proposal)),
        patch.object(demo_mod, "_get_executor", return_value=executor),
        patch("maiw_decision.models.DecisionRequest", MagicMock()),
    ):
        result = await demo_mod._build_and_execute_proposal(
            rec=rec,
            snapshot=MagicMock(warehouse_id="DC-47"),
            runtime=runtime,
            trace_id="t-analyze",
            bus=MagicMock(publish_propose=AsyncMock(), publish_decide=AsyncMock()),
            lifecycle=[],
            index=0,
            ctrl=ctrl,
            warehouse_id="DC-47",
        )
    assert result["status"] == "unknown"
    assert result["executed"] is None
    assert result["reconciliation_required"] is True
    required = _of(_drain(sse), "RECONCILIATION_REQUIRED")
    assert [e["execution_id"] for e in required] == [exec_result.execution_id]
    assert required[0]["asset_id"] == "agv-000"
    ctrl.bus.unsubscribe(sse)
