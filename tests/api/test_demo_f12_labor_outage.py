# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
F12 (Labor MCP circuit open) through the LIVE demo path.

``POST /demo/inject {"event_type": "mcp_outage", "payload": {"domain": "labor"}}``
makes the labor MCP server unreachable for the API's MCP client; the labor
circuit breaker trips through its own state machine.  Checked here on the
canonical shipped app (real lifespan, in-memory MCP servers, real circuit
breakers, DecisionEngine and executors; only the model's answer is scripted):

* /runtime/status reports labor CIRCUIT OPEN, the other domains HEALTHY and
  MAIW DEGRADED, and the CIRCUIT_OPEN event is published;
* analysis and approval need every domain's state, so while labor is out
  MAIW refuses to decide: 503 MCP CIRCUIT OPEN, no model call, no write.  The
  other domains' circuits stay closed;
* a labor write that reaches the MCP client is rejected before dispatch
  (MCPCircuitOpen, a not-dispatched error: execution outcome FAILED);
* mcp_restore, scenario reset and scenario start end the outage; a new
  analysis and approval then execute.  (An approval attempted during the
  outage is used up: approve marks it APPROVED before reading state, as for
  any state-read failure.)
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

SCENARIO = "healthy_baseline"
OUTAGE = {"event_type": "mcp_outage", "payload": {"domain": "labor"}}
RESTORE = {"event_type": "mcp_restore", "payload": {"domain": "labor"}}


def _assessment(domain: str, capability: str, target: str) -> str:
    """The fake model's analyze_disruption answer: one recommendation."""
    return json.dumps(
        {
            "summary": f"{domain} recommendation",
            "recommendations": [
                {
                    "domain": domain,
                    "capability": capability,
                    "target": target,
                    "objective": "Cover the at-risk pick wave",
                    "rationale": "Two operators absent; carrier cutoff in 45 min",
                    "priority": "high",
                    "subtype": "task",
                }
            ],
        }
    )


LABOR = _assessment("labor", "warehouse.labor.allocate", "wave_pending_tasks")
EQUIPMENT = _assessment("equipment", "warehouse.equipment.assign", "agv-000")


@pytest.fixture
def fake_nim():
    fake = FakeNIM(content=LABOR)
    yield fake
    fake.close()


@pytest.fixture
def demo_app_env(monkeypatch, tmp_path, fake_nim):
    """Canonical app in demo mode with an operator credential."""
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


def _drain(queue) -> list[dict]:
    out = []
    while not queue.empty():
        event = queue.get_nowait()
        if event is not None:
            out.append(json.loads(json.dumps(event.to_sse_dict(), default=str)))
    return out


async def _start(client) -> None:
    r = await client.post(f"/api/v1/demo/scenario/{SCENARIO}/start")
    assert r.status_code == 200, r.text


async def _domain_health(client) -> tuple[dict, str]:
    r = await client.get("/api/v1/runtime/status")
    assert r.status_code == 200, r.text
    body = r.json()
    return body["domain_health"], body["maiw_operational_status"]


async def _analyze_pending(client, ctrl) -> dict:
    r = await client.post("/api/v1/demo/analyze")
    assert r.status_code == 200, r.text
    statuses = [p["status"] for p in r.json()["proposal_results"]]
    assert statuses == ["requires_human_approval"], r.json()["proposal_results"]
    pending = ctrl.status()["pending_approvals"]
    assert len(pending) == 1, pending
    return pending[0]


async def test_outage_trips_labor_circuit_and_isolates_other_domains(demo_app_env):
    async with running_canonical_app() as (app, client):
        await _start(client)
        ctrl = app.state.runtime.demo_controller
        sse = ctrl.bus.subscribe()
        assert await _domain_health(client) == (
            {
                "equipment": "HEALTHY",
                "labor": "HEALTHY",
                "wave": "HEALTHY",
                "inventory": "HEALTHY",
            },
            "HEALTHY",
        )

        r = await client.post("/api/v1/demo/inject", json=OUTAGE)
        assert r.status_code == 200, r.text
        result = r.json()["result"]
        breaker = app.state.runtime.circuit_registry.get("labor")
        assert result["domain"] == "labor"
        assert result["circuit_state"] == "open"
        assert result["refused_connections"] == breaker.failure_threshold
        assert "warehouse.labor.allocate" in result["capabilities"]

        health, overall = await _domain_health(client)
        assert health == {
            "equipment": "HEALTHY",
            "labor": "CIRCUIT OPEN",
            "wave": "HEALTHY",
            "inventory": "HEALTHY",
        }
        assert overall == "DEGRADED"

        circuit = [e for e in _drain(sse) if e["category"] == "CIRCUIT_OPEN"]
        assert len(circuit) == 1
        assert circuit[0]["domain"] == "labor"
        assert "rejected before dispatch" in circuit[0]["message"]

        # A second outage request keeps the circuit open; it does not stack.
        r = await client.post("/api/v1/demo/inject", json=OUTAGE)
        assert r.status_code == 200, r.text
        assert r.json()["result"]["circuit_state"] == "open"

        r = await client.post("/api/v1/demo/inject", json=RESTORE)
        assert r.status_code == 200, r.text
        assert r.json()["result"] == {
            "domain": "labor",
            "circuit_state": "closed",
            "was_out": True,
        }
        assert (await _domain_health(client))[1] == "HEALTHY"
        assert app.state.runtime.demo_mcp_outages == {}


def _circuit_open_detail(r) -> dict:
    assert r.status_code == 503, r.text
    detail = r.json()["message"]
    assert detail["error"] == "MCP CIRCUIT OPEN", detail
    assert detail["domain"] == "labor"
    return detail


async def test_decisions_are_refused_while_labor_is_out_then_resume(
    demo_app_env, fake_nim
):
    async with running_canonical_app() as (app, client):
        await _start(client)
        runtime = app.state.runtime
        ctrl = runtime.demo_controller
        labor_provider = ctrl.providers.labor
        equipment_provider = ctrl.providers.equipment

        pending = await _analyze_pending(client, ctrl)
        assert pending["domain"] == "labor"
        model_calls = len(fake_nim.chat_requests())

        r = await client.post("/api/v1/demo/inject", json=OUTAGE)
        assert r.status_code == 200, r.text

        # Approval re-reads state: refused, nothing executed.
        r = await client.post(
            "/api/v1/demo/approve", json={"pending_id": pending["pending_id"]}
        )
        assert "nothing was executed" in _circuit_open_detail(r)["message"]
        # A new analysis is refused before the model is called.
        fake_nim.content = EQUIPMENT
        r = await client.post("/api/v1/demo/analyze")
        _circuit_open_detail(r)
        assert len(fake_nim.chat_requests()) == model_calls
        assert labor_provider._mutation_count == 0
        assert equipment_provider._mutation_count == 0
        for domain in ("equipment", "wave", "inventory"):
            assert runtime.circuit_registry.get(domain).get_stats()["state"] == "closed"

        assert ctrl.status()["pending_approvals"] == []  # used up, not executed

        # Restore → MAIW decides again and the labor write executes.
        r = await client.post("/api/v1/demo/inject", json=RESTORE)
        assert r.status_code == 200, r.text
        fake_nim.content = LABOR
        pending = await _analyze_pending(client, ctrl)
        r = await client.post(
            "/api/v1/demo/approve", json={"pending_id": pending["pending_id"]}
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "executed", r.json()
        assert labor_provider._mutation_count == 1


async def test_labor_write_is_rejected_before_dispatch(demo_app_env):
    """The labor MCP client call itself: refused by the open circuit, not sent."""
    from maiw_mcp.errors import MCPCircuitOpen, MCPNotDispatched

    async with running_canonical_app() as (app, client):
        await _start(client)
        runtime = app.state.runtime
        r = await client.post("/api/v1/demo/inject", json=OUTAGE)
        assert r.status_code == 200, r.text
        breaker = runtime.circuit_registry.get("labor")
        calls_before = breaker.get_stats()["total_calls"]

        with pytest.raises(MCPCircuitOpen) as excinfo:
            await runtime.mcp_client.invoke(
                "warehouse.labor.allocate",
                {"task_id": "task-000001", "worker_ids": ["worker-000001"]},
            )
        assert isinstance(excinfo.value, MCPNotDispatched)
        stats = breaker.get_stats()
        assert stats["total_calls"] == calls_before  # rejected, never run
        assert stats["total_rejected"] >= 1
        assert runtime.demo_controller.providers.labor._mutation_count == 0


@pytest.mark.parametrize("restart", ["reset", "start"])
async def test_scenario_reset_or_start_ends_the_outage(demo_app_env, restart):
    from maiw_api.demo.mcp_outage import UnreachableMCPServer

    async with running_canonical_app() as (app, client):
        await _start(client)
        runtime = app.state.runtime
        original = runtime.mcp_registry.resolve("warehouse.labor.allocate")
        r = await client.post("/api/v1/demo/inject", json=OUTAGE)
        assert r.status_code == 200, r.text
        assert isinstance(
            runtime.mcp_registry.resolve("warehouse.labor.allocate"),
            UnreachableMCPServer,
        )

        if restart == "reset":
            r = await client.post("/api/v1/demo/scenario/reset")
        else:
            r = await client.post(f"/api/v1/demo/scenario/{SCENARIO}/start")
        assert r.status_code == 200, r.text

        assert runtime.mcp_registry.resolve("warehouse.labor.allocate") is original
        assert runtime.demo_mcp_outages == {}
        assert await _domain_health(client) == (
            {
                "equipment": "HEALTHY",
                "labor": "HEALTHY",
                "wave": "HEALTHY",
                "inventory": "HEALTHY",
            },
            "HEALTHY",
        )


async def test_outage_requires_an_active_scenario_and_a_known_domain(demo_app_env):
    async with running_canonical_app() as (app, client):
        r = await client.post("/api/v1/demo/inject", json=OUTAGE)
        assert r.status_code == 409, r.text

        await _start(client)
        r = await client.post(
            "/api/v1/demo/inject",
            json={"event_type": "mcp_outage", "payload": {"domain": "billing"}},
        )
        assert r.status_code == 422, r.text
        assert r.json()["code"] == "UNKNOWN_MCP_DOMAIN"
        r = await client.post(
            "/api/v1/demo/inject", json={"event_type": "mcp_outage", "payload": {}}
        )
        assert r.status_code == 422, r.text
        assert app.state.runtime.demo_mcp_outages == {}
