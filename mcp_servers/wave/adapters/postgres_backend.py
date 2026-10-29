# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
PostgreSQL wave provider — the shipped default for the wave MCP server.

A wave is the set of ``tasks`` rows sharing ``payload->>'wave_id'``; without a
``wave_id`` the scope is every task (reads) or the tasks of one ``zone``
(writes).  Task priority lives in ``payload->>'priority'``, the deadline (ISO
8601) in ``payload->>'deadline'``.

``MAIWWaveAdapter`` (WMS integration) remains available with
``MAIW_MCP_WAVE_BACKEND=wms`` but needs a connected external WMS.

Write semantics (v2.0.1 round 4, same rules as the equipment backend)
---------------------------------------------------------------------
``execute_wave_reprioritize`` locks the open tasks in scope and updates them
in ONE transaction.  Validation and "nothing to reprioritize" are raised as
``WriteNotApplied`` before any write statement; any other failure raises
``BackendUnavailable`` (UNKNOWN).  A repeat with the same ``execution_id``
after it committed returns the recorded result without writing again.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from maiw_contracts.wave import (
    WaveGetRequest,
    WaveGetResult,
    WaveReprioritizeRequest,
    WaveReprioritizeResult,
    WaveRiskFactor,
    WaveRiskRequest,
    WaveRiskResult,
    WaveTaskInfo,
)
from maiw_mcp.errors import BackendUnavailable, WriteNotApplied
from maiw_mcp.write_disposition import (
    REJECTION_INVALID_REQUEST,
    REJECTION_NOT_FOUND,
    REJECTION_PRECONDITION_FAILED,
)

logger = logging.getLogger(__name__)

SOURCE = "maiw-postgres"
PRIORITIES = ("low", "medium", "high", "critical")
OPEN_TASK_STATUSES = ("pending", "in_progress")

_COLUMNS = "SELECT id, kind, status, assignee, payload FROM tasks"


def _payload(row: Any) -> dict:
    raw = row["payload"]
    if isinstance(raw, str):
        return json.loads(raw or "{}")
    return dict(raw or {})


def _scope(wave_id: str | None, zone: str | None) -> tuple[list[str], list[Any]]:
    clauses, params = [], []
    for column, value in (("payload->>'wave_id'", wave_id), ("payload->>'zone'", zone)):
        if value:
            params.append(value)
            clauses.append(f"{column} = ${len(params)}")
    return clauses, params


def task_info(row: Any) -> WaveTaskInfo:
    payload = _payload(row)
    return WaveTaskInfo(
        task_id=str(row["id"]),
        task_type=str(row["kind"]).upper(),
        zone=payload.get("zone"),
        status=row["status"],
        assigned_to=row["assignee"],
        priority=payload.get("priority", "medium"),
        deadline=payload.get("deadline"),
    )


def _deadline(task: WaveTaskInfo) -> datetime | None:
    if not task.deadline:
        return None
    try:
        parsed = datetime.fromisoformat(task.deadline.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class PostgresWaveProvider:
    """``WaveProvider`` backed by the MAIW PostgreSQL ``tasks`` table."""

    def __init__(self, sql: Any | None = None) -> None:
        self._sql = sql
        self._lock: asyncio.Lock | None = None

    async def _db(self) -> Any:
        if self._sql is not None:
            return self._sql
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            if self._sql is None:
                from src.retrieval.structured.sql_retriever import SQLRetriever

                sql = SQLRetriever()
                await sql.initialize()
                self._sql = sql
        return self._sql

    async def _tasks(self, clauses: list[str], params: list[Any]) -> list[WaveTaskInfo]:
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        try:
            db = await self._db()
            rows = await db.fetch_all(f"{_COLUMNS}{where} ORDER BY id", *params)
        except Exception as exc:
            raise BackendUnavailable(f"Wave read failed: {exc}") from exc
        return [task_info(r) for r in rows]

    # ── Reads ────────────────────────────────────────────────────────────────

    async def get_wave(self, request: WaveGetRequest) -> WaveGetResult:
        clauses, params = _scope(request.wave_id, request.zone)
        if request.status_filter:
            params.append(request.status_filter)
            clauses.append(f"status = ${len(params)}")
        if request.task_type:
            params.append(request.task_type)
            clauses.append(f"lower(kind) = lower(${len(params)})")
        tasks = await self._tasks(clauses, params)
        summary: dict[str, int] = {}
        for task in tasks:
            summary[task.status] = summary.get(task.status, 0) + 1
        return WaveGetResult(
            tasks=tasks,
            total_tasks=len(tasks),
            zones_active=sorted({t.zone for t in tasks if t.zone}),
            summary=summary,
            wave_id=request.wave_id,
            source=SOURCE,
        )

    async def get_wave_risk(self, request: WaveRiskRequest) -> WaveRiskResult:
        clauses, params = _scope(request.wave_id, request.zone)
        tasks = [
            t
            for t in await self._tasks(clauses, params)
            if t.status in OPEN_TASK_STATUSES
        ]
        horizon = datetime.now(timezone.utc) + timedelta(minutes=request.cutoff_minutes)
        due = [t for t in tasks if (d := _deadline(t)) is not None and d <= horizon]
        urgent_unassigned = [
            t
            for t in tasks
            if t.priority in ("high", "critical") and not t.assigned_to and t not in due
        ]
        at_risk = len(due) + len(urgent_unassigned)
        factors = []
        if due:
            factors.append(
                WaveRiskFactor(
                    factor="deadline_within_cutoff",
                    severity="high",
                    detail=f"{len(due)} open task(s) due within {request.cutoff_minutes} min",
                )
            )
        if urgent_unassigned:
            factors.append(
                WaveRiskFactor(
                    factor="urgent_unassigned",
                    severity="medium",
                    detail=f"{len(urgent_unassigned)} high/critical task(s) without a worker",
                )
            )
        ratio = at_risk / len(tasks) if tasks else 0.0
        if at_risk == 0:
            level = "none"
        elif ratio < 0.25:
            level = "low"
        elif ratio < 0.5:
            level = "medium"
        elif ratio < 0.75:
            level = "high"
        else:
            level = "critical"
        return WaveRiskResult(
            otif_at_risk=at_risk > 0,
            risk_level=level,
            at_risk_task_count=at_risk,
            total_task_count=len(tasks),
            risk_factors=factors,
            recommendation=(
                "Reprioritize or allocate labor to the at-risk tasks" if at_risk else ""
            ),
            wave_id=request.wave_id,
            source=SOURCE,
        )

    # ── Write ────────────────────────────────────────────────────────────────

    async def execute_wave_reprioritize(
        self, request: WaveReprioritizeRequest
    ) -> WaveReprioritizeResult:
        priority = (request.new_priority or "").lower()
        if priority not in PRIORITIES:
            raise WriteNotApplied(
                f"new_priority must be one of {', '.join(PRIORITIES)}",
                rejection_code=REJECTION_INVALID_REQUEST,
            )
        if not request.wave_id and not request.zone:
            raise WriteNotApplied(
                "wave_id or zone is required (refusing to reprioritize every task)",
                rejection_code=REJECTION_INVALID_REQUEST,
            )
        try:
            db = await self._db()
        except Exception as exc:
            raise WriteNotApplied(
                f"Wave database unavailable: {exc}",
                rejection_code=REJECTION_PRECONDITION_FAILED,
            ) from exc

        clauses, params = _scope(request.wave_id, request.zone)
        params.append(list(OPEN_TASK_STATUSES))
        clauses.append(f"status = ANY(${len(params)}::text[])")
        record = {
            "new_priority": priority,
            "reason": request.reason,
            "proposal_id": request.proposal_id,
            "decision_id": request.decision_id,
            "execution_id": request.execution_id,
        }
        try:
            async with db.transaction() as conn:
                rows = await conn.fetch(
                    f"{_COLUMNS} WHERE {' AND '.join(clauses)} ORDER BY id FOR UPDATE",
                    *params,
                )
                if not rows:
                    raise WriteNotApplied(
                        "No open tasks in scope "
                        f"(wave_id={request.wave_id!r}, zone={request.zone!r})",
                        rejection_code=REJECTION_NOT_FOUND,
                    )
                if request.execution_id and all(
                    (_payload(r).get("last_reprioritize") or {}).get("execution_id")
                    == request.execution_id
                    for r in rows
                ):
                    return self._result(request, priority, len(rows), replay=True)
                ids = [r["id"] for r in rows]
                await conn.execute(
                    "UPDATE tasks SET payload = COALESCE(payload, '{}'::jsonb) || $1::jsonb, "
                    "updated_at = now() WHERE id = ANY($2::int[])",
                    json.dumps({"priority": priority, "last_reprioritize": record}),
                    ids,
                )
        except BackendUnavailable:
            raise
        except Exception as exc:
            raise BackendUnavailable(
                f"Wave reprioritization write failed: {exc}"
            ) from exc

        logger.info(
            "PostgresWaveProvider: %d task(s) set to %s wave_id=%s zone=%s proposal_id=%s",
            len(ids),
            priority,
            request.wave_id,
            request.zone,
            request.proposal_id,
        )
        return self._result(request, priority, len(ids))

    @staticmethod
    def _result(
        request: WaveReprioritizeRequest,
        priority: str,
        count: int,
        replay: bool = False,
    ) -> WaveReprioritizeResult:
        return WaveReprioritizeResult(
            success=True,
            tasks_updated=count,
            wave_id=request.wave_id,
            new_priority=priority,
            proposal_id=request.proposal_id,
            decision_id=request.decision_id,
            execution_id=request.execution_id,
            source=SOURCE,
            message=(
                f"Reprioritization already recorded for {count} task(s) (replay)"
                if replay
                else f"Reprioritized {count} task(s) to '{priority}'"
            ),
        )
