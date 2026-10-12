# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.0.1 round 4 — the shipped PostgreSQL equipment adapter is transactional.

Fourth independent re-audit (NEW4-P1-01 context): ``EquipmentAssetTools``
performed one logical equipment mutation as several independent statements
(assign = INSERT assignment + UPDATE asset; release = UPDATE assignment +
UPDATE asset) and turned any exception into ``success: false`` — a realistic
source of a partial write followed by a server error.

These CI-runnable tests drive the REAL ``SQLRetriever.transaction()`` and the
REAL ``EquipmentAssetTools`` write methods against a fake asyncpg pool /
connection that records BEGIN / COMMIT / ROLLBACK, rejects any write
statement issued outside a transaction, can fail the N-th write statement,
and restores its tables on ROLLBACK (the database's atomicity).  The same
behaviour against a real PostgreSQL is proven by the opt-in
``MAIW_TEST_PG_DSN`` tests at the end of this module.
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

# ── fake asyncpg pool / connection ────────────────────────────────────────────


class InjectedFailure(RuntimeError):
    pass


class FakeTransaction:
    def __init__(self, conn: "FakeConnection") -> None:
        self.conn = conn

    async def __aenter__(self):
        assert not self.conn.in_tx, "nested transaction"
        self.conn.events.append("BEGIN")
        self.conn.in_tx = True
        self.conn.snapshot = copy.deepcopy(self.conn.db)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.conn.in_tx = False
        if exc_type is not None:
            self.conn.events.append("ROLLBACK")
            self.conn.db = self.conn.snapshot
        else:
            self.conn.events.append("COMMIT")
        self.conn.snapshot = None
        return False


class FakeConnection:
    """Speaks the subset of asyncpg's Connection API the tools use."""

    def __init__(self, db: dict[str, Any]) -> None:
        self.db = db
        self.events: list[str] = []
        self.in_tx = False
        self.snapshot = None
        self.fail_on_write: int | None = None
        self.writes = 0

    def transaction(self):
        return FakeTransaction(self)

    def _write(self, label: str) -> None:
        if not self.in_tx:
            self.events.append(f"WRITE_OUTSIDE_TX:{label}")
            raise AssertionError(f"write statement outside a transaction: {label}")
        self.writes += 1
        self.events.append(f"WRITE{self.writes}:{label}")
        if self.fail_on_write == self.writes:
            raise InjectedFailure(f"injected failure on write statement {self.writes}")

    async def fetchrow(self, query: str, *args):
        q = " ".join(query.split())
        if q.startswith("SELECT status, owner_user FROM equipment_assets"):
            a = self.db["assets"].get(args[0])
            return dict(a) if a else None
        if q.startswith("SELECT status FROM equipment_assets"):
            a = self.db["assets"].get(args[0])
            return {"status": a["status"]} if a else None
        if q.startswith("SELECT asset_id, type, model FROM equipment_assets"):
            a = self.db["assets"].get(args[0])
            return (
                {"asset_id": args[0], "type": "forklift", "model": "m"} if a else None
            )
        if "FROM equipment_assignments" in q and q.startswith("SELECT"):
            active = [
                r
                for r in self.db["assignments"]
                if r["asset_id"] == args[0] and r["released_at"] is None
            ]
            return dict(active[-1]) if active else None
        if q.startswith("INSERT INTO equipment_assignments"):
            self._write("insert_assignment")
            row = {
                "id": len(self.db["assignments"]) + 1,
                "asset_id": args[0],
                "task_id": args[1],
                "assignee": args[2],
                "assignment_type": args[3],
                "notes": args[4],
                "released_at": None,
            }
            self.db["assignments"].append(row)
            return {"id": row["id"]}
        if q.startswith("INSERT INTO equipment_maintenance"):
            self._write("insert_maintenance")
            row = {"id": len(self.db["maintenance"]) + 1, "asset_id": args[0]}
            self.db["maintenance"].append(row)
            return {"id": row["id"]}
        raise AssertionError(f"unexpected fetchrow: {q}")

    async def execute(self, query: str, *args):
        q = " ".join(query.split())
        if q.startswith("UPDATE equipment_assignments SET released_at"):
            self._write("release_assignment")
            for r in self.db["assignments"]:
                if r["id"] == args[1]:
                    r["released_at"] = "now"
            return "UPDATE 1"
        if q.startswith("UPDATE equipment_assets SET status = 'assigned'"):
            self._write("asset_assigned")
            self.db["assets"][args[1]].update(status="assigned", owner_user=args[0])
            return "UPDATE 1"
        if q.startswith("UPDATE equipment_assets SET status = 'available'"):
            self._write("asset_available")
            self.db["assets"][args[0]].update(status="available", owner_user=None)
            return "UPDATE 1"
        if q.startswith("UPDATE equipment_assets SET status = 'maintenance'"):
            self._write("asset_maintenance")
            self.db["assets"][args[0]].update(status="maintenance")
            return "UPDATE 1"
        raise AssertionError(f"unexpected execute: {q}")


class FakePool:
    def __init__(self, conn: FakeConnection) -> None:
        self.conn = conn
        self.acquired = 0
        self.released = 0

    async def acquire(self):
        self.acquired += 1
        return self.conn

    async def release(self, conn):
        assert not conn.in_tx, "connection released inside a transaction"
        self.released += 1


def _db() -> dict[str, Any]:
    return {
        "assets": {
            "FL-AV": {"status": "available", "owner_user": None},
            "FL-AS": {"status": "assigned", "owner_user": "J-1"},
        },
        "assignments": [
            {
                "id": 1,
                "asset_id": "FL-AS",
                "task_id": None,
                "assignee": "J-1",
                "assignment_type": "task",
                "notes": None,
                "released_at": None,
            }
        ],
        "maintenance": [],
    }


@pytest.fixture
def tools():
    from src.retrieval.structured.sql_retriever import DatabaseConfig, SQLRetriever
    from src.api.agents.inventory.equipment_asset_tools import EquipmentAssetTools

    conn = FakeConnection(_db())
    pool = FakePool(conn)
    retriever = object.__new__(SQLRetriever)  # bypass the process singleton
    retriever.config = DatabaseConfig()
    retriever._pool = pool
    retriever._initialized = True
    t = EquipmentAssetTools()
    t.sql_retriever = retriever
    return t, conn, pool


def _sched():
    return datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc)


OPS = {
    "assign": (
        lambda t: t.assign_equipment(asset_id="FL-AV", assignee="J-9"),
        ["insert_assignment", "asset_assigned"],
    ),
    "release": (
        lambda t: t.release_equipment(asset_id="FL-AS", released_by="op"),
        ["release_assignment", "asset_available"],
    ),
    "emergency_maintenance": (
        lambda t: t.schedule_maintenance(
            asset_id="FL-AV",
            maintenance_type="emergency",
            description="d",
            scheduled_by="op",
            scheduled_for=_sched(),
        ),
        ["insert_maintenance", "asset_maintenance"],
    ),
}


@pytest.mark.parametrize("op", sorted(OPS))
async def test_multi_statement_write_commits_once_in_one_transaction(tools, op):
    t, conn, pool = tools
    run, statements = OPS[op]
    result = await run(t)
    assert result["success"] is True, result
    writes = [e for e in conn.events if e.startswith("WRITE")]
    assert [w.split(":", 1)[1] for w in writes] == statements
    assert conn.events[0] == "BEGIN" and conn.events[-1] == "COMMIT"
    assert conn.events.count("BEGIN") == 1 and conn.events.count("COMMIT") == 1
    assert "ROLLBACK" not in conn.events
    assert pool.acquired == pool.released == 1


@pytest.mark.parametrize("fail_on", [1, 2])
@pytest.mark.parametrize("op", sorted(OPS))
async def test_statement_failure_rolls_back_every_statement(tools, op, fail_on):
    t, conn, pool = tools
    run, statements = OPS[op]
    before = copy.deepcopy(conn.db)
    conn.fail_on_write = fail_on
    result = await run(t)
    assert result["success"] is False
    # NOT certified as not-applied: the adapter must report it as ambiguous
    assert "mutation_status" not in result
    assert "ROLLBACK" in conn.events and "COMMIT" not in conn.events
    assert conn.db == before, "a partially applied logical write survived"
    assert pool.acquired == pool.released == 1
    # the connection is reusable afterwards
    conn.fail_on_write = None
    conn.events.clear()
    conn.writes = 0
    again = await run(t)
    assert again["success"] is True
    assert conn.events[-1] == "COMMIT"


@pytest.mark.parametrize(
    "call,code",
    [
        (
            lambda t: t.assign_equipment(asset_id="FL-AS", assignee="J-9"),
            "PRECONDITION_FAILED",
        ),
        (lambda t: t.assign_equipment(asset_id="NOPE", assignee="J-9"), "NOT_FOUND"),
        (
            lambda t: t.release_equipment(asset_id="FL-AV", released_by="op"),
            "PRECONDITION_FAILED",
        ),
        (lambda t: t.release_equipment(asset_id="NOPE", released_by="op"), "NOT_FOUND"),
        (
            lambda t: t.schedule_maintenance(
                asset_id="NOPE",
                maintenance_type="emergency",
                description="d",
                scheduled_by="op",
                scheduled_for=_sched(),
            ),
            "NOT_FOUND",
        ),
    ],
)
async def test_precondition_rejection_runs_no_write_and_is_certified(tools, call, code):
    t, conn, _ = tools
    before = copy.deepcopy(conn.db)
    result = await call(t)
    assert result["success"] is False
    assert result["mutation_status"] == "not_applied"
    assert result["rejection_code"] == code
    assert not [e for e in conn.events if e.startswith("WRITE")]
    assert conn.db == before


async def test_retriever_transaction_uses_the_driver_transaction():
    """SQLRetriever.transaction() = pool connection + Connection.transaction()."""
    from src.retrieval.structured.sql_retriever import DatabaseConfig, SQLRetriever

    conn = FakeConnection(_db())
    pool = FakePool(conn)
    r = object.__new__(SQLRetriever)
    r.config = DatabaseConfig()
    r._pool = pool
    r._initialized = True
    with pytest.raises(InjectedFailure):
        async with r.transaction() as c:
            assert c is conn and conn.in_tx
            raise InjectedFailure("x")
    assert conn.events == ["BEGIN", "ROLLBACK"]
    async with r.transaction():
        pass
    assert conn.events[-2:] == ["BEGIN", "COMMIT"]
    assert pool.acquired == pool.released == 2


# ── the MCP adapter: only a certified rejection is NOT_APPLIED ───────────────


def _adapter(result: dict):
    from mcp_servers.equipment.adapters.maiw_backend import MAIWEquipmentAdapter

    tools = MagicMock()

    async def _ret(**_):
        return result

    tools.release_equipment = _ret
    tools.assign_equipment = _ret
    return MAIWEquipmentAdapter(tools)


async def test_adapter_maps_only_not_applied_to_write_not_applied():
    from maiw_contracts.equipment import EquipmentExecuteReleaseRequest
    from maiw_mcp.errors import BackendUnavailable, WriteNotApplied

    req = EquipmentExecuteReleaseRequest(
        asset_id="FL-1", released_by="op", proposal_id="p", decision_id="d"
    )
    with pytest.raises(WriteNotApplied) as na:
        await _adapter(
            {
                "success": False,
                "error": "no active",
                "mutation_status": "not_applied",
                "rejection_code": "PRECONDITION_FAILED",
            }
        ).execute_equipment_release(req)
    assert na.value.rejection_code == "PRECONDITION_FAILED"

    for generic in (
        {"success": False, "error": "Failed to release equipment: boom"},
        {"success": False, "error": "x", "mutation_status": "rolled_back"},
        {"success": False, "error": "x", "mutation_status": None},
    ):
        with pytest.raises(BackendUnavailable) as exc:
            await _adapter(generic).execute_equipment_release(req)
        assert not isinstance(exc.value, WriteNotApplied)


async def test_adapter_initialises_tools_once_on_first_use():
    """NEW4-P2-03: the shipped default provider never called initialize()."""
    from maiw_contracts.equipment import EquipmentStatusRequest
    from mcp_servers.equipment.adapters.maiw_backend import MAIWEquipmentAdapter

    class Tools:
        def __init__(self) -> None:
            self.sql_retriever = None
            self.init_calls = 0

        async def initialize(self):
            self.init_calls += 1
            await asyncio.sleep(0.01)
            self.sql_retriever = object()

        async def get_equipment_status(self, **_):
            assert self.sql_retriever is not None
            return {"equipment": [], "summary": {}, "total_count": 0}

    tools = Tools()
    adapter = MAIWEquipmentAdapter(tools)
    await asyncio.gather(
        *(adapter.get_equipment_status(EquipmentStatusRequest()) for _ in range(5))
    )
    assert tools.init_calls == 1


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("{}", {}),
        ('{"battery": 80}', {"battery": 80}),
        ({"battery": 80}, {"battery": 80}),
        (None, {}),
        ("[1, 2]", {}),
        ("not json", {}),
        (b'{"a": 1}', {"a": 1}),
    ],
)
async def test_get_status_metadata_satisfies_the_contract(raw, expected):
    """NEW4-P2-03: asyncpg returns JSONB as a string; the contract needs a dict."""
    from maiw_contracts.equipment import EquipmentStatusRequest, EquipmentStatusResult
    from mcp_servers.equipment.adapters.maiw_backend import MAIWEquipmentAdapter

    row = {
        "asset_id": "FL-01",
        "type": "forklift",
        "model": "m",
        "zone": "A",
        "status": "available",
        "owner_user": None,
        "next_pm_due": None,
        "last_maintenance": None,
        "metadata": raw,
    }
    tools = MagicMock()

    async def _status(**_):
        return {"equipment": [row], "summary": {}, "total_count": 1}

    tools.get_equipment_status = _status
    result = await MAIWEquipmentAdapter(tools).get_equipment_status(
        EquipmentStatusRequest(asset_id="FL-01")
    )
    assert result.equipment[0].metadata == expected
    # the wire form re-validates against the canonical contract
    EquipmentStatusResult.model_validate(json.loads(result.model_dump_json()))


# ── opt-in: the same guarantees against a REAL PostgreSQL ────────────────────

_PG = os.getenv("MAIW_TEST_PG_DSN")
_pg_only = pytest.mark.skipif(
    not _PG, reason="set MAIW_TEST_PG_DSN to a DISPOSABLE Postgres with the MAIW schema"
)


@pytest.fixture
async def real_pg(monkeypatch):
    """Real asyncpg + a SQLRetriever on MAIW_TEST_PG_DSN + an isolated trigger."""
    import importlib
    from urllib.parse import urlparse

    if isinstance(sys.modules.get("asyncpg"), MagicMock):
        monkeypatch.delitem(sys.modules, "asyncpg")
    asyncpg = importlib.import_module("asyncpg")
    if isinstance(asyncpg, MagicMock):  # pragma: no cover
        pytest.skip("asyncpg is stubbed in this interpreter")
    import src.retrieval.structured.sql_retriever as sqlmod

    monkeypatch.setattr(sqlmod, "asyncpg", asyncpg)
    u = urlparse(_PG)
    retriever = object.__new__(sqlmod.SQLRetriever)
    retriever.config = sqlmod.DatabaseConfig(
        host=u.hostname or "127.0.0.1",
        port=u.port or 5432,
        database=(u.path or "/warehouse").lstrip("/"),
        user=u.username or "warehouse",
        password=u.password or "",
    )
    retriever._pool = None
    retriever._initialized = True

    admin = await asyncpg.connect(_PG)
    if not await admin.fetchval(
        "select to_regclass('public.equipment_assets') is not null"
    ):
        await admin.close()
        pytest.skip("MAIW schema not loaded in MAIW_TEST_PG_DSN")
    tag = uuid.uuid4().hex[:8].upper()
    fail_prefix, ok_prefix = f"R4TXFAIL{tag}", f"R4TXOK{tag}"
    fn = f"r4_fail_second_{tag.lower()}"
    # The injected failure is a REAL SQL error raised by the database while
    # executing the SECOND statement of the logical write (the UPDATE of
    # equipment_assets), after the first statement already ran.
    await admin.execute(f"""
        CREATE FUNCTION {fn}() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.asset_id LIKE '{fail_prefix}%' THEN
            RAISE EXCEPTION 'r4 injected failure in the second statement';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER {fn} BEFORE UPDATE ON equipment_assets
          FOR EACH ROW EXECUTE FUNCTION {fn}();
        """)
    for prefix in (fail_prefix, ok_prefix):
        await admin.execute(
            "insert into equipment_assets (asset_id, type, model, zone, status) values "
            "($1,'forklift','r4','A','available'), ($2,'forklift','r4','A','assigned'), "
            "($3,'forklift','r4','A','available')",
            f"{prefix}-A",
            f"{prefix}-R",
            f"{prefix}-M",
        )
        await admin.execute(
            "insert into equipment_assignments (asset_id, assignee, assignment_type) "
            "values ($1, 'J-R4', 'task')",
            f"{prefix}-R",
        )
    try:
        yield retriever, admin, fail_prefix, ok_prefix
    finally:
        await admin.execute(f"DROP TRIGGER IF EXISTS {fn} ON equipment_assets")
        await admin.execute(f"DROP FUNCTION IF EXISTS {fn}()")
        for prefix in (fail_prefix, ok_prefix):
            await admin.execute(
                "delete from equipment_assets where asset_id like $1", f"{prefix}%"
            )
        await admin.close()
        if retriever._pool is not None:
            await retriever._pool.close()


async def _snapshot(admin, asset_id: str) -> dict:
    asset = await admin.fetchrow(
        "select status, owner_user from equipment_assets where asset_id=$1", asset_id
    )
    assignments = await admin.fetch(
        "select id, assignee, released_at, notes from equipment_assignments "
        "where asset_id=$1 order by id",
        asset_id,
    )
    maintenance = await admin.fetchval(
        "select count(*) from equipment_maintenance where asset_id=$1", asset_id
    )
    return {
        "asset": dict(asset),
        "assignments": [dict(a) for a in assignments],
        "maintenance": maintenance,
    }


def _pg_ops(prefix: str):
    from datetime import timedelta

    when = datetime.now(timezone.utc) + timedelta(days=1)
    return {
        "assign": (
            f"{prefix}-A",
            lambda t: t.assign_equipment(asset_id=f"{prefix}-A", assignee="J-NEW"),
        ),
        "release": (
            f"{prefix}-R",
            lambda t: t.release_equipment(asset_id=f"{prefix}-R", released_by="op"),
        ),
        "emergency_maintenance": (
            f"{prefix}-M",
            lambda t: t.schedule_maintenance(
                asset_id=f"{prefix}-M",
                maintenance_type="emergency",
                description="r4",
                scheduled_by="op",
                scheduled_for=when,
            ),
        ),
    }


@_pg_only
@pytest.mark.parametrize("op", ["assign", "release", "emergency_maintenance"])
async def test_pg_second_statement_failure_rolls_back_first(real_pg, op):
    from src.api.agents.inventory.equipment_asset_tools import EquipmentAssetTools

    retriever, admin, fail_prefix, ok_prefix = real_pg
    tools = EquipmentAssetTools()
    tools.sql_retriever = retriever

    asset_id, run = _pg_ops(fail_prefix)[op]
    before = await _snapshot(admin, asset_id)
    result = await run(tools)
    assert result["success"] is False
    assert "r4 injected failure" in result["error"]
    assert "mutation_status" not in result  # never certified NOT_APPLIED
    assert await _snapshot(admin, asset_id) == before

    # the pool connection is clean and reusable; a normal write commits fully
    ok_id, ok_run = _pg_ops(ok_prefix)[op]
    ok_before = await _snapshot(admin, ok_id)
    ok = await ok_run(tools)
    assert ok["success"] is True, ok
    after = await _snapshot(admin, ok_id)
    if op == "assign":
        assert after["asset"] == {"status": "assigned", "owner_user": "J-NEW"}
        assert len(after["assignments"]) == len(ok_before["assignments"]) + 1
    elif op == "release":
        assert after["asset"]["status"] == "available"
        assert after["assignments"][-1]["released_at"] is not None
    else:
        assert after["asset"]["status"] == "maintenance"
        assert after["maintenance"] == ok_before["maintenance"] + 1
