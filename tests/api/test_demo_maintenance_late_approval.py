# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Late approval of a maintenance proposal through the LIVE demo path (#259).

/demo/analyze proposes ``schedule_maintenance`` with the default slot
(simulated now + 1 day), which always waits for a human. If the simulation
clock passes that slot before the operator approves, /demo/approve must not
execute it: the DecisionEngine, wired at bootstrap with the world's
SimulationClock, rejects it on re-check (``maintenance.scheduled_for_past``)
and the asset is untouched. Approved in time, it executes as before.

Drives the canonical shipped app ``maiw_api.app:app`` in demo mode (real
lifespan, real DecisionEngine, EquipmentActionExecutor and demo providers).
Only the fake model's answer (one maintenance recommendation) is scripted.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta

import pytest

from tests.api.canonical_harness import (
    FakeNIM,
    canonical_env,
    install_gateway,
    running_canonical_app,
)

SCENARIO = "labor_constraint_wave_risk"
TARGET = "agv-000"


def _assessment() -> str:
    return json.dumps(
        {
            "summary": f"Inspect {TARGET} before the next wave",
            "recommendations": [
                {
                    "domain": "equipment",
                    "capability": "warehouse.equipment.schedule_maintenance",
                    "target": TARGET,
                    "objective": f"Schedule preventive maintenance for {TARGET}",
                    "rationale": "Drive fault reported on the last shift",
                    "priority": "medium",
                    "subtype": None,
                }
            ],
        }
    )


@pytest.fixture
def demo_app_env(monkeypatch, tmp_path):
    import maiw_api.bootstrap as bootstrap
    from maiw_api.demo.controller import reset_demo_controller

    fake = FakeNIM(content=_assessment())
    canonical_env(monkeypatch, tmp_path, fake)
    monkeypatch.setenv("MAIW_DEMO_MODE", "true")
    monkeypatch.setenv("MAIW_DEPLOYMENT_PROFILE", "demo")
    monkeypatch.setenv("MAIW_OPERATOR_WRITE_TOKEN", secrets.token_hex(32))
    monkeypatch.setattr(bootstrap, "_DEMO_MODE", True)
    reset_demo_controller()
    install_gateway(fake)
    yield
    from maiw_models import reset_model_gateway

    reset_model_gateway()
    reset_demo_controller()
    fake.close()


async def _propose(client, ctrl) -> tuple[dict, datetime]:
    r = await client.post(f"/api/v1/demo/scenario/{SCENARIO}/start")
    assert r.status_code == 200, r.text
    r = await client.post("/api/v1/demo/analyze")
    assert r.status_code == 200, r.text
    statuses = [p["status"] for p in r.json()["proposal_results"]]
    assert statuses == ["requires_human_approval"], r.json()["proposal_results"]
    pending = ctrl.status()["pending_approvals"]
    assert len(pending) == 1, pending
    params = pending[0]["proposal_data"]["parameters"]
    slot = datetime.fromisoformat(params["scheduled_for"])
    assert slot == ctrl.world.clock.now() + timedelta(days=1)
    return pending[0], slot


async def _advance(client, seconds: int) -> None:
    while seconds > 0:
        step = min(seconds, 86400)
        r = await client.post("/api/v1/demo/tick", json={"seconds": step})
        assert r.status_code == 200, r.text
        seconds -= step


async def test_bootstrap_wires_the_simulation_clock_into_the_engine(demo_app_env):
    async with running_canonical_app() as (app, client):
        r = await client.post(f"/api/v1/demo/scenario/{SCENARIO}/start")
        assert r.status_code == 200, r.text
        runtime = app.state.runtime
        ctrl = runtime.demo_controller
        assert runtime.decision_engine._clock is not None
        assert runtime.decision_engine._clock() == ctrl.world.clock.now()
        await _advance(client, 120)
        assert runtime.decision_engine._clock() == ctrl.world.clock.now()


async def test_approval_after_the_slot_passed_does_not_execute(demo_app_env):
    async with running_canonical_app() as (app, client):
        ctrl = app.state.runtime.demo_controller
        pending, slot = await _propose(client, ctrl)
        asset_before = ctrl.world.equipment[TARGET]
        status_before = asset_before.status
        pm_before = asset_before.next_pm_due

        await _advance(client, 2 * 86400)
        assert ctrl.world.clock.now() > slot

        r = await client.post(
            "/api/v1/demo/approve", json={"pending_id": pending["pending_id"]}
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is False
        assert body["status"] == "rejected"
        assert [v["rule"] for v in body["violations"]] == [
            "maintenance.scheduled_for_past"
        ]
        assert "execution_id" not in body
        asset = ctrl.world.equipment[TARGET]
        assert asset.status == status_before
        assert asset.next_pm_due == pm_before


async def test_approval_before_the_slot_executes(demo_app_env):
    async with running_canonical_app() as (app, client):
        ctrl = app.state.runtime.demo_controller
        pending, slot = await _propose(client, ctrl)

        await _advance(client, 3600)  # an hour later, still before the slot

        r = await client.post(
            "/api/v1/demo/approve", json={"pending_id": pending["pending_id"]}
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "executed", body
        asset = ctrl.world.equipment[TARGET]
        assert asset.status == "maintenance"
        assert asset.next_pm_due == slot
