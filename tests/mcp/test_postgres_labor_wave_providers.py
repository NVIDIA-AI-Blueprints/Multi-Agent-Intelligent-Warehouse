"""
PostgreSQL labor / wave providers and the WMS adapters' write honesty.

The providers are exercised against a scripted fake connection that records
every statement, so each test asserts both the outcome class (success,
certified NOT_APPLIED with its rejection code, or UNKNOWN) and whether any
write statement was issued.  The live path against the Compose database is
covered by scripts/testing/smoke_e2e.py in the deployment workflow.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from maiw_contracts.labor import (
    LaborAllocateRequest,
    LaborAllocateResult,
    LaborAllocationRequest,
    LaborCapacityRequest,
)
from maiw_contracts.wave import (
    WaveGetRequest,
    WaveReprioritizeRequest,
    WaveRiskRequest,
)
from maiw_mcp.errors import BackendUnavailable, WriteNotApplied

from mcp_servers.labor.adapters.maiw_backend import MAIWLaborAdapter
from mcp_servers.labor.adapters.postgres_backend import PostgresLaborProvider
from mcp_servers.wave.adapters.maiw_backend import MAIWWaveAdapter
from mcp_servers.wave.adapters.postgres_backend import PostgresWaveProvider

GOV = {"proposal_id": "p-1", "decision_id": "d-1"}


def task(id_, status="pending", assignee=None, **payload):
    return {
        "id": id_,
        "kind": "pick",
        "status": status,
        "assignee": assignee,
        "payload": json.dumps(payload),
    }


class FakeConn:
    def __init__(self, db):
        self.db = db

    async def fetchrow(self, sql, *params):
        self.db.log.append(("fetchrow", sql, params))
        rows = self.db.answer(sql)
        return rows[0] if rows else None

    async def fetch(self, sql, *params):
        self.db.log.append(("fetch", sql, params))
        return self.db.answer(sql)

    async def execute(self, sql, *params):
        self.db.log.append(("execute", sql, params))
        if self.db.fail_writes:
            raise RuntimeError("connection reset during write")
        return "UPDATE 1"


class FakeSQL:
    """Answers by the first matching SQL fragment; records every statement."""

    def __init__(self, answers=None, fail_writes=False):
        self.answers = answers or {}
        self.fail_writes = fail_writes
        self.log = []

    def answer(self, sql):
        for fragment, rows in self.answers.items():
            if fragment in sql:
                return rows
        return []

    async def fetch_all(self, sql, *params):
        self.log.append(("fetch_all", sql, params))
        return self.answer(sql)

    @asynccontextmanager
    async def transaction(self):
        yield FakeConn(self)

    @property
    def writes(self):
        return [entry for entry in self.log if entry[0] == "execute"]


def allocate(task_id="7", workers=("op1",), execution_id=None):
    return LaborAllocateRequest(
        warehouse_id="default",
        task_id=task_id,
        task_type="pick",
        worker_ids=list(workers),
        execution_id=execution_id,
        **GOV,
    )


# ── Labor ────────────────────────────────────────────────────────────────────


async def test_labor_capacity_maps_users_and_busy_workers():
    sql = FakeSQL(
        {
            "FROM users": [
                {
                    "id": 1,
                    "username": "op1",
                    "full_name": "One",
                    "role": "operator",
                    "status": "active",
                },
                {
                    "id": 2,
                    "username": "op2",
                    "full_name": "Two",
                    "role": "operator",
                    "status": "active",
                },
            ],
            "DISTINCT assignee": [{"assignee": "op1"}],
        }
    )
    result = await PostgresLaborProvider(sql).get_labor_capacity(LaborCapacityRequest())
    assert [w.worker_id for w in result.workers] == ["op1", "op2"]
    assert (result.total_workers, result.available_workers, result.utilization_pct) == (
        2,
        1,
        50.0,
    )
    assert result.source == "maiw-postgres"


async def test_labor_allocation_read_filters_and_maps_tasks():
    sql = FakeSQL({"FROM tasks": [task(7, assignee="op1", zone="A", priority="high")]})
    result = await PostgresLaborProvider(sql).get_labor_allocation(
        LaborAllocationRequest(worker_id="op1", zone="A")
    )
    _, query, params = sql.log[0]
    assert "assignee = $1" in query and "payload->>'zone' = $2" in query
    assert params == ("op1", "A")
    info = result.allocations[0]
    assert (info.task_id, info.assigned_to, info.zone, info.priority) == (
        "7",
        "op1",
        "A",
        "high",
    )
    assert result.pending_count == 1


async def test_labor_allocate_writes_assignee_and_allocation_record():
    sql = FakeSQL(
        {"FROM tasks WHERE id": [task(7)], "FROM users": [{"username": "op1"}]}
    )
    result = await PostgresLaborProvider(sql).execute_labor_allocation(
        allocate(execution_id="e-1")
    )
    assert result.success and result.allocation_id and result.source == "maiw-postgres"
    [(_, statement, params)] = sql.writes
    assert statement.startswith("UPDATE tasks SET assignee = $1")
    assert params[0] == "op1" and params[2] == 7
    record = json.loads(params[1])["last_allocation"]
    assert record["allocation_id"] == result.allocation_id
    assert record["execution_id"] == "e-1" and record["proposal_id"] == "p-1"
    assert "priority" not in json.loads(params[1])


async def test_labor_allocate_overwrites_priority_only_when_requested():
    sql = FakeSQL(
        {"FROM tasks WHERE id": [task(7)], "FROM users": [{"username": "op1"}]}
    )
    request = LaborAllocateRequest(
        **allocate().model_dump(exclude={"priority"}), priority="high"
    )
    await PostgresLaborProvider(sql).execute_labor_allocation(request)
    [(_, _, params)] = sql.writes
    assert json.loads(params[1])["priority"] == "high"


@pytest.mark.parametrize(
    "request_, answers, code",
    [
        (allocate(task_id="abc"), {}, "NOT_FOUND"),
        (allocate(), {}, "NOT_FOUND"),
        (
            allocate(),
            {"FROM tasks WHERE id": [task(7, status="completed")]},
            "PRECONDITION_FAILED",
        ),
        (
            allocate(),
            {"FROM tasks WHERE id": [task(7)], "FROM users": []},
            "PRECONDITION_FAILED",
        ),
    ],
    ids=["non-numeric-task", "missing-task", "closed-task", "unknown-worker"],
)
async def test_labor_allocate_rejections_are_certified_and_write_nothing(
    request_, answers, code
):
    sql = FakeSQL(answers)
    with pytest.raises(WriteNotApplied) as err:
        await PostgresLaborProvider(sql).execute_labor_allocation(request_)
    assert err.value.rejection_code == code
    assert sql.writes == []


async def test_labor_allocate_empty_workers_is_invalid_request():
    request = allocate()
    request.worker_ids = []
    with pytest.raises(WriteNotApplied) as err:
        await PostgresLaborProvider(FakeSQL()).execute_labor_allocation(request)
    assert err.value.rejection_code == "INVALID_REQUEST"


async def test_labor_allocate_replay_with_same_execution_id_does_not_write():
    previous = {"allocation_id": "a-1", "execution_id": "e-1"}
    sql = FakeSQL(
        {"FROM tasks WHERE id": [task(7, assignee="op1", last_allocation=previous)]}
    )
    result = await PostgresLaborProvider(sql).execute_labor_allocation(
        allocate(execution_id="e-1")
    )
    assert (
        result.success and result.allocation_id == "a-1" and "replay" in result.message
    )
    assert sql.writes == []


async def test_labor_allocate_failure_during_write_is_unknown_not_certified():
    sql = FakeSQL(
        {"FROM tasks WHERE id": [task(7)], "FROM users": [{"username": "op1"}]},
        fail_writes=True,
    )
    with pytest.raises(BackendUnavailable) as err:
        await PostgresLaborProvider(sql).execute_labor_allocation(allocate())
    assert not isinstance(err.value, WriteNotApplied)


# ── Wave ─────────────────────────────────────────────────────────────────────


def reprioritize(**overrides):
    fields = {
        "warehouse_id": "default",
        "wave_id": "W1",
        "new_priority": "critical",
        **GOV,
    }
    fields.update(overrides)
    return WaveReprioritizeRequest(**fields)


async def test_wave_get_summarises_tasks_in_scope():
    sql = FakeSQL(
        {
            "FROM tasks": [
                task(1, wave_id="W1", zone="A"),
                task(2, status="in_progress", wave_id="W1", zone="B"),
            ]
        }
    )
    result = await PostgresWaveProvider(sql).get_wave(WaveGetRequest(wave_id="W1"))
    assert "payload->>'wave_id' = $1" in sql.log[0][1]
    assert result.total_tasks == 2 and result.zones_active == ["A", "B"]
    assert result.summary == {"pending": 1, "in_progress": 1}
    assert result.tasks[0].task_type == "PICK"


async def test_wave_risk_counts_deadlines_and_urgent_unassigned():
    soon = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    later = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()
    sql = FakeSQL(
        {
            "FROM tasks": [
                task(1, wave_id="W1", deadline=soon),
                task(2, wave_id="W1", deadline=later),
                task(3, wave_id="W1", priority="critical"),
                task(4, status="completed", wave_id="W1", deadline=soon),
            ]
        }
    )
    result = await PostgresWaveProvider(sql).get_wave_risk(
        WaveRiskRequest(wave_id="W1", cutoff_minutes=60)
    )
    assert (result.total_task_count, result.at_risk_task_count) == (3, 2)
    assert {f.factor for f in result.risk_factors} == {
        "deadline_within_cutoff",
        "urgent_unassigned",
    }
    assert result.otif_at_risk and result.risk_level == "high"


async def test_wave_reprioritize_updates_open_tasks_in_one_statement():
    sql = FakeSQL({"FOR UPDATE": [task(1, wave_id="W1"), task(2, wave_id="W1")]})
    result = await PostgresWaveProvider(sql).execute_wave_reprioritize(
        reprioritize(execution_id="e-9")
    )
    assert (
        result.success
        and result.tasks_updated == 2
        and result.new_priority == "critical"
    )
    [(_, statement, params)] = sql.writes
    assert statement.startswith("UPDATE tasks SET payload")
    update = json.loads(params[0])
    assert update["priority"] == "critical"
    assert update["last_reprioritize"]["execution_id"] == "e-9"
    assert params[1] == [1, 2]


@pytest.mark.parametrize(
    "request_, answers, code",
    [
        (reprioritize(new_priority="urgent"), {}, "INVALID_REQUEST"),
        (reprioritize(wave_id=None), {}, "INVALID_REQUEST"),
        (reprioritize(), {"FOR UPDATE": []}, "NOT_FOUND"),
    ],
    ids=["bad-priority", "no-scope", "no-open-tasks"],
)
async def test_wave_reprioritize_rejections_are_certified_and_write_nothing(
    request_, answers, code
):
    sql = FakeSQL(answers)
    with pytest.raises(WriteNotApplied) as err:
        await PostgresWaveProvider(sql).execute_wave_reprioritize(request_)
    assert err.value.rejection_code == code
    assert sql.writes == []


async def test_wave_reprioritize_replay_does_not_write():
    done = {"last_reprioritize": {"execution_id": "e-9"}}
    sql = FakeSQL(
        {"FOR UPDATE": [task(1, wave_id="W1", **done), task(2, wave_id="W1", **done)]}
    )
    result = await PostgresWaveProvider(sql).execute_wave_reprioritize(
        reprioritize(execution_id="e-9")
    )
    assert result.tasks_updated == 2 and "replay" in result.message
    assert sql.writes == []


async def test_wave_reprioritize_failure_during_write_is_unknown_not_certified():
    sql = FakeSQL({"FOR UPDATE": [task(1, wave_id="W1")]}, fail_writes=True)
    with pytest.raises(BackendUnavailable) as err:
        await PostgresWaveProvider(sql).execute_wave_reprioritize(reprioritize())
    assert not isinstance(err.value, WriteNotApplied)


# ── WMS adapters: no false success ──────────────────────────────────────────


class FakeOperationsTools:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def assign_task(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


async def test_wms_labor_adapter_no_wms_connection_is_not_applied():
    tools = FakeOperationsTools(
        {"success": False, "error": "No WMS connections available"}
    )
    with pytest.raises(WriteNotApplied) as err:
        await MAIWLaborAdapter(tools).execute_labor_allocation(allocate())
    assert err.value.rejection_code == "PRECONDITION_FAILED"


async def test_wms_labor_adapter_other_failure_is_unknown():
    tools = FakeOperationsTools({"success": False, "error": "timeout talking to WMS"})
    with pytest.raises(BackendUnavailable) as err:
        await MAIWLaborAdapter(tools).execute_labor_allocation(allocate())
    assert not isinstance(err.value, WriteNotApplied)


async def test_wms_labor_adapter_rejects_empty_workers_before_calling_wms():
    tools = FakeOperationsTools({"success": True})
    request = allocate()
    request.worker_ids = []
    with pytest.raises(WriteNotApplied):
        await MAIWLaborAdapter(tools).execute_labor_allocation(request)
    assert tools.calls == []


async def test_wms_wave_adapter_refuses_reprioritize_it_cannot_apply():
    with pytest.raises(WriteNotApplied) as err:
        await MAIWWaveAdapter(object()).execute_wave_reprioritize(reprioritize())
    assert err.value.rejection_code == "PRECONDITION_FAILED"


# ── Default provider selection ───────────────────────────────────────────────


@pytest.mark.parametrize("domain", ["labor", "wave"])
def test_servers_default_to_postgres_and_allow_wms(domain, monkeypatch):
    import importlib

    server = importlib.import_module(f"mcp_servers.{domain}.server")
    monkeypatch.delenv(server.BACKEND_ENV, raising=False)
    assert type(server._build_default_provider()).__name__.startswith("Postgres")
    monkeypatch.setenv(server.BACKEND_ENV, "wms")
    assert type(server._build_default_provider()).__name__.startswith("MAIW")
    monkeypatch.setenv(server.BACKEND_ENV, "oracle")
    with pytest.raises(ValueError):
        server._build_default_provider()


# ── Allocation must not reset the task's priority (deployment smoke finding) ──


class _RecordingProvider:
    def __init__(self):
        self.requests = []

    async def execute_labor_allocation(self, request):
        self.requests.append(request)
        return LaborAllocateResult(
            success=True, task_id=request.task_id, worker_ids=["op1"], **GOV
        )


@pytest.mark.parametrize("priority, expected", [(None, set()), ("high", {"priority"})])
async def test_labor_tool_forwards_priority_only_when_given(
    monkeypatch, priority, expected
):
    from mcp_servers.labor import server

    provider = _RecordingProvider()
    monkeypatch.setattr(server, "_provider", provider)
    kwargs = {"priority": priority} if priority else {}
    await server.warehouse_labor_allocate(
        warehouse_id="default",
        task_id="7",
        task_type="pick",
        worker_ids=["op1"],
        **GOV,
        **kwargs,
    )
    [request] = provider.requests
    assert request.model_fields_set & {"priority"} == expected


@pytest.mark.parametrize("priority, sent", [(None, False), ("high", True)])
async def test_labor_skill_omits_default_priority_from_mcp_payload(priority, sent):
    from maiw_skills.labor.skills import ExecuteLaborAllocationSkill

    class Client:
        payload = None

        async def invoke(self, name, payload):
            Client.payload = payload
            return {"success": True, "task_id": "7", "worker_ids": ["op1"], **GOV}

    request = allocate()
    if priority:
        request = LaborAllocateRequest(
            **allocate().model_dump(exclude={"priority"}), priority=priority
        )
    await ExecuteLaborAllocationSkill(Client()).execute(request)
    assert ("priority" in Client.payload) is sent


@pytest.mark.parametrize(
    "params, expected", [({}, set()), ({"priority": "high"}, {"priority"})]
)
async def test_labor_executor_forwards_priority_only_from_proposal(params, expected):
    from types import SimpleNamespace

    from src.api.agents.operations.labor_executor import LaborActionExecutor

    seen = []

    class Skill:
        async def execute(self, request):
            seen.append(request)
            return LaborAllocateResult(
                success=True, task_id=request.task_id, worker_ids=["op1"], **GOV
            )

    proposal = SimpleNamespace(
        parameters={"task_id": "7", "worker_ids": ["op1"], **params},
        proposal_id="p-1",
    )
    executor = LaborActionExecutor(allocate_skill=Skill())
    await executor._do_allocate(proposal, SimpleNamespace(result_id="d-1"))
    assert seen[0].model_fields_set & {"priority"} == expected
