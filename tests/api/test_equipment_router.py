# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
tests/api/test_equipment_router.py

Infrastructure-free unit tests for the canonical equipment router.
Uses httpx ASGI transport — no real HTTP port opened.

All DB and agent calls are patched at the transport level.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── App fixture (no external deps) ────────────────────────────────────────────


def _make_runtime(*, with_agent: bool = True):
    rt = MagicMock()
    rt.mcp_client = None
    rt.mcp_registry = None
    rt.mcp_inventory_available = False
    rt.mcp_equipment_available = bool(with_agent)
    rt.mcp_labor_available = False
    rt.mcp_wave_available = False

    if with_agent:
        agent = MagicMock()
        agent.propose_equipment_assignment = AsyncMock(
            return_value={
                "status": "requires_human_approval",
                "action": "warehouse.equipment.assign",
                "proposal_id": "p-001",
                "decision_id": "d-001",
                "reason": "Requires human approval",
                "executed": False,
            }
        )
        agent.propose_equipment_release = AsyncMock(
            return_value={
                "status": "approved",
                "action": "warehouse.equipment.release",
                "proposal_id": "p-002",
                "decision_id": "d-002",
                "reason": "Auto-approved",
                "executed": True,
                "execution_id": "e-002",
            }
        )
        agent.propose_schedule_maintenance = AsyncMock(
            return_value={
                "status": "requires_human_approval",
                "action": "warehouse.equipment.schedule_maintenance",
                "proposal_id": "p-003",
                "decision_id": "d-003",
                "reason": "Maintenance requires approval",
                "executed": False,
            }
        )
        asset_tools = MagicMock()
        asset_tools.get_equipment_status = AsyncMock(
            return_value={"asset_id": "AMR-001", "status": "idle"}
        )
        asset_tools.get_equipment_telemetry = AsyncMock(
            return_value={"telemetry_data": []}
        )
        agent.asset_tools = asset_tools
        agent.get_equipment_state_snapshot = AsyncMock(return_value=None)
        rt.equipment_agent = agent
    else:
        rt.equipment_agent = None

    rt.operations_agent = None
    rt.safety_agent = None
    return rt


@asynccontextmanager
async def _lifespan(app, *, with_agent: bool = True):
    app.state.runtime = _make_runtime(with_agent=with_agent)
    yield


@pytest.fixture()
def app_with_agent():
    @asynccontextmanager
    async def ls(app):
        async with _lifespan(app, with_agent=True):
            yield

    with (
        patch("maiw_api.app.lifespan", ls),
        patch(
            "src.api.services.security.rate_limiter.get_rate_limiter",
            return_value=AsyncMock(check_rate_limit=AsyncMock()),
        ),
        patch("src.api.services.monitoring.metrics.record_request_metrics"),
        patch("src.retrieval.structured.SQLRetriever.initialize", AsyncMock()),
        patch(
            "src.retrieval.structured.SQLRetriever.execute_query",
            AsyncMock(return_value=[]),
        ),
    ):
        import importlib
        import maiw_api.app as m

        importlib.reload(m)
        # ASGITransport does not trigger ASGI lifespan events; set state directly.
        m.app.state.runtime = _make_runtime(with_agent=True)
        yield m.app


@pytest.fixture()
def app_no_agent():
    @asynccontextmanager
    async def ls(app):
        async with _lifespan(app, with_agent=False):
            yield

    with (
        patch("maiw_api.app.lifespan", ls),
        patch(
            "src.api.services.security.rate_limiter.get_rate_limiter",
            return_value=AsyncMock(check_rate_limit=AsyncMock()),
        ),
        patch("src.api.services.monitoring.metrics.record_request_metrics"),
        patch("src.retrieval.structured.SQLRetriever.initialize", AsyncMock()),
        patch(
            "src.retrieval.structured.SQLRetriever.execute_query",
            AsyncMock(return_value=[]),
        ),
    ):
        import importlib
        import maiw_api.app as m

        importlib.reload(m)
        # ASGITransport does not trigger ASGI lifespan events; set state directly.
        m.app.state.runtime = _make_runtime(with_agent=False)
        yield m.app


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_get_all_equipment_returns_list(app_with_agent):
    import httpx
    from httpx import ASGITransport

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app_with_agent), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/equipment")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.anyio
async def test_assign_equipment_returns_decision(app_with_agent):
    import httpx
    from httpx import ASGITransport

    payload = {
        "asset_id": "AMR-001",
        "assignee": "worker-42",
        "assignment_type": "task",
        "task_id": "T-99",
    }
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app_with_agent), base_url="http://test"
    ) as client:
        resp = await client.post("/api/v1/equipment/assign", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "requires_human_approval"
    assert "proposal_id" in body
    assert "decision_id" in body


@pytest.mark.anyio
async def test_release_equipment_approved(app_with_agent):
    import httpx
    from httpx import ASGITransport

    payload = {"asset_id": "AMR-001", "released_by": "worker-42"}
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app_with_agent), base_url="http://test"
    ) as client:
        resp = await client.post("/api/v1/equipment/release", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "approved"
    assert body["executed"] is True


@pytest.mark.anyio
async def test_write_endpoint_returns_503_without_agent(app_no_agent):
    """Write endpoints must return 503 when equipment_agent is None."""
    import httpx
    from httpx import ASGITransport

    payload = {"asset_id": "AMR-001", "assignee": "worker-1"}
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app_no_agent), base_url="http://test"
    ) as client:
        resp = await client.post("/api/v1/equipment/assign", json=payload)
    assert resp.status_code == 503


@pytest.mark.anyio
async def test_schedule_maintenance_returns_decision(app_with_agent):
    import httpx
    from httpx import ASGITransport

    payload = {
        "asset_id": "AMR-001",
        "maintenance_type": "preventive",
        "description": "Quarterly check",
        "scheduled_by": "ops-team",
        "scheduled_for": "2026-09-01T09:00:00",
    }
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app_with_agent), base_url="http://test"
    ) as client:
        resp = await client.post("/api/v1/equipment/maintenance", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "requires_human_approval"
    assert body["executed"] is False
