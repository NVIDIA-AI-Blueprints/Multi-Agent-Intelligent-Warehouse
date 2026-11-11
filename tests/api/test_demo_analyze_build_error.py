# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
One proposal build error no longer drops the remaining recommendations (#260).

``POST /api/v1/demo/analyze`` builds a proposal for each recommendation in
turn. When a build failed it ``break``-ed out of the loop, so the later
recommendations (possibly independent, in other domains) were never proposed,
decided or executed, and did not appear in ``proposal_results`` or the
lifecycle. A build error happens before the DecisionEngine and changes nothing,
while execution errors, which can change the warehouse, never stopped the loop.

Now the failure is reported at its index (``status: "error"`` with the
reason, in ``proposal_results`` and the lifecycle), every other recommendation
is still proposed and decided on its own, and ``proposal_summary`` counts the
outcome. These tests drive the shipped app in demo mode with a scripted model
answer; only the proposal builder for one sentinel target is made to fail.
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

# Runs on the DataPack world; the scripted scenarios run on their YAML worlds (#308).
SCENARIO = "healthy_baseline"
BROKEN = "asset-that-cannot-be-proposed"


def _rec(target: str) -> dict:
    return {
        "domain": "equipment",
        "capability": "warehouse.equipment.assign",
        "target": target,
        "objective": f"Put {target} on the at-risk pick wave",
        "rationale": "Two operators absent; carrier cutoff in 45 min",
        "priority": "high",
        "subtype": "task",
    }


def _assessment(*targets: str) -> str:
    return json.dumps(
        {
            "summary": "Cover the wave risk",
            "recommendations": [_rec(t) for t in targets],
        }
    )


@pytest.fixture
def fake_nim():
    fake = FakeNIM(content=_assessment(BROKEN, "agv-000"))
    yield fake
    fake.close()


@pytest.fixture
def demo_app_env(monkeypatch, tmp_path, fake_nim):
    import maiw_api.bootstrap as bootstrap
    from maiw_api.demo.controller import reset_demo_controller

    canonical_env(monkeypatch, tmp_path, fake_nim)
    monkeypatch.setenv("MAIW_DEMO_MODE", "true")
    monkeypatch.setenv("MAIW_DEPLOYMENT_PROFILE", "demo")
    monkeypatch.setenv("MAIW_OPERATOR_WRITE_TOKEN", secrets.token_hex(32))
    monkeypatch.setattr(bootstrap, "_DEMO_MODE", True)
    reset_demo_controller()
    install_gateway(fake_nim)
    yield
    from maiw_models import reset_model_gateway

    reset_model_gateway()
    reset_demo_controller()


@pytest.fixture
def broken_builder(monkeypatch):
    """The real proposal builder, except for the BROKEN target."""
    import maiw_api.routers.demo as demo_mod

    real = demo_mod._build_proposal
    calls: list[str] = []

    async def build(rec, *args, **kwargs):
        calls.append(rec.target)
        if rec.target == BROKEN:
            raise ValueError("no valid (task, worker) pair for the recommendation")
        return await real(rec, *args, **kwargs)

    monkeypatch.setattr(demo_mod, "_build_proposal", build)
    return calls


async def _analyze(client) -> dict:
    r = await client.post(f"/api/v1/demo/scenario/{SCENARIO}/start")
    assert r.status_code == 200, r.text
    r = await client.post("/api/v1/demo/analyze")
    assert r.status_code == 200, r.text
    return r.json()


async def test_a_failed_first_build_does_not_stop_the_rest(
    demo_app_env, broken_builder
):
    async with running_canonical_app() as (app, client):
        body = await _analyze(client)
        ctrl = app.state.runtime.demo_controller

    assert broken_builder == [BROKEN, "agv-000"]
    results = body["proposal_results"]
    assert [r["index"] for r in results] == [0, 1]

    failed, proposed = results
    assert failed["status"] == "error"
    assert failed["capability"] == "warehouse.equipment.assign"
    assert "no valid (task, worker) pair" in failed["reason"]
    # The second recommendation went through the DecisionEngine as usual.
    assert proposed["status"] == "requires_human_approval", proposed
    pending = ctrl.status()["pending_approvals"]
    assert [p["proposal_data"]["parameters"]["asset_id"] for p in pending] == [
        "agv-000"
    ]

    propose = [l for l in body["lifecycle"] if l["phase"] == "PROPOSE"]
    assert [(l["index"], l.get("status")) for l in propose] == [
        (0, "error"),
        (1, None),
    ]
    assert propose[1]["proposal_id"]
    decide = [l for l in body["lifecycle"] if l["phase"] == "DECIDE"]
    assert len(decide) == 1

    assert body["proposal_summary"] == {
        "recommendations": 2,
        "proposed": 1,
        "build_errors": 1,
        "build_error_indices": [0],
        "executed": 0,
        "awaiting_approval": 1,
    }


async def test_every_failure_is_reported_at_its_index(
    demo_app_env, broken_builder, fake_nim
):
    fake_nim.content = _assessment("agv-000", BROKEN, BROKEN)
    async with running_canonical_app() as (_, client):
        body = await _analyze(client)

    assert broken_builder == ["agv-000", BROKEN, BROKEN]
    statuses = [(r["index"], r["status"]) for r in body["proposal_results"]]
    assert statuses == [
        (0, "requires_human_approval"),
        (1, "error"),
        (2, "error"),
    ]
    summary = body["proposal_summary"]
    assert summary["build_error_indices"] == [1, 2]
    assert summary["proposed"] == 1


async def test_summary_without_failures(demo_app_env, fake_nim):
    fake_nim.content = _assessment("agv-000")
    async with running_canonical_app() as (_, client):
        body = await _analyze(client)

    assert [r["status"] for r in body["proposal_results"]] == [
        "requires_human_approval"
    ]
    assert body["proposal_results"][0]["index"] == 0
    assert body["proposal_summary"] == {
        "recommendations": 1,
        "proposed": 1,
        "build_errors": 0,
        "build_error_indices": [],
        "executed": 0,
        "awaiting_approval": 1,
    }
