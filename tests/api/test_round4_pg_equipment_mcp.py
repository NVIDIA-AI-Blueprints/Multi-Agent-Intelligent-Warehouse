# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.0.1 round 4 — the SHIPPED equipment MCP server + PostgreSQL adapter serve
the governed profile (opt-in: ``MAIW_TEST_PG_DSN``).

Fourth re-audit NEW4-P2-03: the shipped server's default provider was never
initialised and ``get_status`` failed contract validation (``metadata``
returned as the string ``'{}'``), so the auditor had to run its own backend.
These tests run ``mcp_servers.equipment.server`` with its own default provider
against a disposable PostgreSQL loaded with the MAIW schema
(``tests/api/round4_pg_mcp_backend.py`` adds only a post-commit fault switch)
and prove, over real streamable HTTP:

* §31 get_status satisfies the canonical contract; release through the full
  canonical HTTP pipeline; assign and maintenance through the governed
  executor; a precondition rejection is the typed NOT_APPLIED → FAILED;
* §20 a transaction that COMMITS followed by a server error → UNKNOWN →
  identical retry 409 → reconciliation CONFIRMED_EXECUTED → one write.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import pytest

from tests.api.canonical_harness import (
    FakeNIM,
    canonical_env,
    install_gateway,
    running_canonical_app,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("MAIW_TEST_PG_DSN"),
    reason="set MAIW_TEST_PG_DSN to a DISPOSABLE Postgres loaded with the MAIW schema",
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = Path(__file__).with_name("round4_pg_mcp_backend.py")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _pg_env(dsn: str) -> dict[str, str]:
    u = urlparse(dsn)
    return {
        "PGHOST": u.hostname or "127.0.0.1",
        "PGPORT": str(u.port or 5432),
        "POSTGRES_USER": u.username or "warehouse",
        "POSTGRES_PASSWORD": u.password or "",
        "POSTGRES_DB": (u.path or "/warehouse").lstrip("/"),
    }


@pytest.fixture
def real_asyncpg(monkeypatch):
    import importlib
    from unittest.mock import MagicMock

    if isinstance(sys.modules.get("asyncpg"), MagicMock):
        monkeypatch.delitem(sys.modules, "asyncpg")
    module = importlib.import_module("asyncpg")
    if isinstance(module, MagicMock):  # pragma: no cover
        pytest.skip("asyncpg is stubbed in this interpreter")
    return module


@pytest.fixture
async def pg(real_asyncpg):
    dsn = os.environ["MAIW_TEST_PG_DSN"]
    conn = await real_asyncpg.connect(dsn)
    if not await conn.fetchval(
        "select to_regclass('public.equipment_assets') is not null"
    ):
        await conn.close()
        pytest.skip("MAIW schema not loaded in MAIW_TEST_PG_DSN")
    tag = uuid.uuid4().hex[:6].upper()
    ids = {k: f"R4MCP{tag}-{k}" for k in ("REL", "ASG", "MNT", "AVL")}
    await conn.execute(
        "insert into equipment_assets (asset_id, type, model, zone, status, metadata) "
        "values ($1,'forklift','r4','A','assigned','{\"r4\": true}'::jsonb), "
        "($2,'forklift','r4','A','available','{}'::jsonb), "
        "($3,'forklift','r4','A','available','{}'::jsonb), "
        "($4,'forklift','r4','A','available','{}'::jsonb)",
        ids["REL"],
        ids["ASG"],
        ids["MNT"],
        ids["AVL"],
    )
    await conn.execute(
        "insert into equipment_assignments (asset_id, assignee, assignment_type) "
        "values ($1, 'J-R4', 'task')",
        ids["REL"],
    )
    try:
        yield conn, ids
    finally:
        await conn.execute(
            "delete from equipment_assets where asset_id like $1", f"R4MCP{tag}-%"
        )
        await conn.close()


class ShippedBackend:
    def __init__(self, workdir: Path, dsn: str) -> None:
        workdir.mkdir(parents=True, exist_ok=True)
        self.port = _free_port()
        self.url = f"http://127.0.0.1:{self.port}/mcp"
        self.write_log = workdir / "writes.jsonl"
        self.control = workdir / "control"
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/tmp"),
            "PYTHON_DOTENV_DISABLED": "1",
            **_pg_env(dsn),
        }
        self.proc = subprocess.Popen(
            [
                sys.executable,
                str(BACKEND),
                str(self.port),
                str(self.write_log),
                str(self.control),
            ],
            cwd=str(workdir),  # never the repo root: no .env can be picked up
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("shipped equipment MCP server exited")
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", self.port)) == 0:
                    return
            time.sleep(0.1)
        raise RuntimeError("shipped equipment MCP server did not start")

    def arm(self, mode: str) -> None:
        self.control.write_text(mode)

    def committed(self) -> list[dict]:
        if not self.write_log.exists():
            return []
        return [json.loads(x) for x in self.write_log.read_text().splitlines() if x]

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()


@pytest.fixture
def shipped(tmp_path):
    b = ShippedBackend(tmp_path / "shipped", os.environ["MAIW_TEST_PG_DSN"])
    yield b
    b.stop()


@pytest.fixture
def governed(monkeypatch, tmp_path, shipped):
    fake = FakeNIM()
    canonical_env(monkeypatch, tmp_path, fake)
    operator = secrets.token_hex(32)
    monkeypatch.setenv("MAIW_DEPLOYMENT_PROFILE", "reference_governed")
    monkeypatch.setenv("MAIW_REQUIRED_MCP_DOMAINS", "equipment")
    monkeypatch.setenv("MAIW_MCP_SERVER_EQUIPMENT_URL", shipped.url)
    monkeypatch.setenv("MAIW_OPERATOR_WRITE_TOKEN", operator)
    install_gateway(fake)
    yield {"X-Maiw-Operator-Token": operator}
    fake.close()
    from maiw_models import reset_model_gateway

    reset_model_gateway()


def _client(url: str):
    from maiw_mcp.client.client import MAIWMCPClient
    from maiw_mcp.registry.registry import CapabilityRegistry

    from maiw_api.bootstrap import _EQUIPMENT_CAPABILITIES

    registry = CapabilityRegistry()
    registry.register_domain(_EQUIPMENT_CAPABILITIES, url)
    return MAIWMCPClient(registry)


def _approved(proposal):
    from maiw_decision.models import DecisionOutcome, DecisionResult

    return DecisionResult(
        request_id="r4-pg",
        proposal_id=proposal.proposal_id,
        outcome=DecisionOutcome.APPROVED,
        evaluated_at=datetime.now(timezone.utc),
    )


async def _asset(conn, asset_id):
    return dict(
        await conn.fetchrow(
            "select status, owner_user from equipment_assets where asset_id=$1",
            asset_id,
        )
    )


async def test_shipped_server_serves_the_governed_profile(pg, shipped, tmp_path):
    from maiw_contracts.equipment import EquipmentStatusRequest
    from maiw_decision.proposal import ActionProposal
    from maiw_execution import EquipmentActionExecutor, JsonFileExecutionRegistry
    from maiw_skills.equipment.skills import (
        EquipmentStatusSkill,
        ExecuteEquipmentAssignmentSkill,
        ExecuteEquipmentMaintenanceSkill,
        ExecuteEquipmentReleaseSkill,
    )

    conn, ids = pg
    client = _client(shipped.url)

    # get_status validates against the canonical contract (metadata is a dict)
    status = await EquipmentStatusSkill(client).execute(
        EquipmentStatusRequest(asset_id=ids["REL"])
    )
    assert status.source == "maiw-backend"
    assert status.equipment[0].metadata == {"r4": True}

    executor = EquipmentActionExecutor(
        assign_skill=ExecuteEquipmentAssignmentSkill(client),
        release_skill=ExecuteEquipmentReleaseSkill(client),
        maintenance_skill=ExecuteEquipmentMaintenanceSkill(client),
        registry=JsonFileExecutionRegistry(tmp_path / "journal"),
    )

    assign = ActionProposal.for_equipment_assign(
        asset_id=ids["ASG"],
        assignee="J-R4A",
        assignment_type="task",
        task_id=None,
        duration_hours=None,
        notes=None,
        reason="r4 smoke",
        requested_by="op",
    )
    r = await executor.execute(assign, _approved(assign))
    assert r.outcome.value == "executed", r
    assert await _asset(conn, ids["ASG"]) == {
        "status": "assigned",
        "owner_user": "J-R4A",
    }

    release = ActionProposal.for_equipment_release(
        asset_id=ids["ASG"], released_by="op"
    )
    r = await executor.execute(release, _approved(release))
    assert r.outcome.value == "executed", r
    assert (await _asset(conn, ids["ASG"]))["status"] == "available"

    maint = ActionProposal.for_schedule_maintenance(
        asset_id=ids["MNT"],
        maintenance_type="emergency",
        description="r4 smoke",
        scheduled_by="op",
        scheduled_for=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    )
    r = await executor.execute(maint, _approved(maint))
    assert r.outcome.value == "executed", r
    assert (await _asset(conn, ids["MNT"]))["status"] == "maintenance"

    # precondition rejection (nothing to release) → typed NOT_APPLIED → FAILED
    reject = ActionProposal.for_equipment_release(asset_id=ids["AVL"], released_by="op")
    r = await executor.execute(reject, _approved(reject))
    assert r.outcome.value == "failed"
    assert r.error_code == "MCP_TOOL_NOT_APPLIED"
    assert r.physical_mutation_occurred is False
    assert (await _asset(conn, ids["AVL"]))["status"] == "available"
    assert len(shipped.committed()) == 3


async def test_commit_then_server_error_is_unknown_and_reconciles_executed(
    pg, shipped, governed
):
    conn, ids = pg
    auth = governed
    body = {"asset_id": ids["REL"], "released_by": "operator-1"}
    async with running_canonical_app() as (_, client):
        shipped.arm("error_after_commit")
        r = await client.post("/api/v1/equipment/release", json=body, headers=auth)
        assert r.status_code == 202, r.text
        out = r.json()
        assert out["status"] == "unknown"
        assert out["executed"] is None
        assert out["error_code"] == "MCP_TOOL_ERROR"
        # the transaction committed: the release is in the database
        assert (await _asset(conn, ids["REL"]))["status"] == "available"
        assert len(shipped.committed()) == 1

        retry = await client.post("/api/v1/equipment/release", json=body, headers=auth)
        assert retry.status_code == 409
        assert len(shipped.committed()) == 1

        rec = await client.post(
            f"/api/v1/executions/{out['execution_id']}/reconcile", headers=auth
        )
        assert rec.status_code == 200, rec.text
        assert rec.json()["reconciliation_outcome"] == "confirmed_executed"
    released = await conn.fetchval(
        "select count(*) from equipment_assignments "
        "where asset_id=$1 and released_at is not null",
        ids["REL"],
    )
    assert released == 1
    assert len(shipped.committed()) == 1
