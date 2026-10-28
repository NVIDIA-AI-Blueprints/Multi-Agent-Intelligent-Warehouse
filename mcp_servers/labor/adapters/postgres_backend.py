# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
PostgreSQL labor provider — the shipped default for the labor MCP server.

Reads and writes the MAIW warehouse database directly:

    workers      ``users`` rows with an operational role (operator /
                 supervisor / manager); ``worker_id`` is the username
    tasks        ``tasks`` rows; ``assignee`` holds the allocated worker,
                 ``payload->>'zone'`` / ``payload->>'priority'`` the task context

``MAIWLaborAdapter`` (WMS integration) remains available with
``MAIW_MCP_LABOR_BACKEND=wms`` but needs a connected external WMS, which the
MCP server process never has.

Write semantics (v2.0.1 round 4, same rules as the equipment backend)
---------------------------------------------------------------------
``execute_labor_allocation`` runs in ONE transaction with the task row locked
(``FOR UPDATE``).  Request validation and precondition checks happen before
any write statement and raise ``WriteNotApplied`` (certified NOT_APPLIED).
Any other failure raises ``BackendUnavailable`` — the write may or may not
have committed, so the executor must treat it as UNKNOWN.  Repeating a call
with the same ``execution_id`` after it committed returns the recorded
allocation without writing again.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from maiw_contracts.labor import (
    LaborAllocateRequest,
    LaborAllocateResult,
    LaborAllocationRequest,
    LaborAllocationResult,
    LaborCapacityRequest,
    LaborCapacityResult,
    LaborTaskInfo,
    LaborWorkerInfo,
)
from maiw_mcp.errors import BackendUnavailable, WriteNotApplied
from maiw_mcp.write_disposition import (
    REJECTION_INVALID_REQUEST,
    REJECTION_NOT_FOUND,
    REJECTION_PRECONDITION_FAILED,
)

logger = logging.getLogger(__name__)

SOURCE = "maiw-postgres"
WORKER_ROLES = ("operator", "supervisor", "manager")
OPEN_TASK_STATUSES = ("pending", "in_progress")
CLOSED_TASK_STATUSES = ("completed", "failed", "cancelled")


def _payload(row: Any) -> dict:
    raw = row["payload"]
    if isinstance(raw, str):
        return json.loads(raw or "{}")
    return dict(raw or {})


def task_info(row: Any) -> LaborTaskInfo:
    payload = _payload(row)
    return LaborTaskInfo(
        task_id=str(row["id"]),
        task_type=row["kind"],
        zone=payload.get("zone"),
        status=row["status"],
        assigned_to=row["assignee"],
        priority=payload.get("priority", "medium"),
    )


class PostgresLaborProvider:
    """``LaborProvider`` backed by the MAIW PostgreSQL ``users`` / ``tasks`` tables."""

    def __init__(self, sql: Any | None = None) -> None:
        self._sql = sql
        self._lock: asyncio.Lock | None = None

    async def _db(self) -> Any:
        # The asyncpg pool is bound to the event loop that creates it, so build
        # it lazily inside the serving loop (see MAIWEquipmentAdapter._ready).
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

    # ── Reads ────────────────────────────────────────────────────────────────

    async def get_labor_capacity(
        self, request: LaborCapacityRequest
    ) -> LaborCapacityResult:
        try:
            db = await self._db()
            workers = await db.fetch_all(
                "SELECT id, username, full_name, role::text AS role, "
                "status::text AS status FROM users "
                "WHERE role::text = ANY($1::text[]) AND status::text = $2 "
                "ORDER BY username",
                list(WORKER_ROLES),
                request.status_filter,
            )
            busy_rows = await db.fetch_all(
                "SELECT DISTINCT assignee FROM tasks "
                "WHERE assignee IS NOT NULL AND status = 'in_progress'"
            )
        except Exception as exc:
            raise BackendUnavailable(f"Labor capacity read failed: {exc}") from exc

        busy = {r["assignee"] for r in busy_rows}
        infos = [
            LaborWorkerInfo(
                worker_id=w["username"],
                username=w["username"],
                full_name=w["full_name"],
                role=w["role"],
                status=w["status"],
            )
            for w in workers
        ]
        total = len(infos)
        engaged = sum(1 for w in infos if w.username in busy)
        return LaborCapacityResult(
            workers=infos,
            total_workers=total,
            available_workers=total - engaged,
            utilization_pct=round(100.0 * engaged / total, 1) if total else 0.0,
            zone=request.zone,
            shift=request.shift,
            source=SOURCE,
        )

    async def get_labor_allocation(
        self, request: LaborAllocationRequest
    ) -> LaborAllocationResult:
        clauses, params = [], []
        for column, value in (
            ("assignee", request.worker_id),
            ("payload->>'zone'", request.zone),
            ("kind", request.task_type),
            ("status", request.status_filter),
        ):
            if value:
                params.append(value)
                clauses.append(f"{column} = ${len(params)}")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        try:
            db = await self._db()
            rows = await db.fetch_all(
                "SELECT id, kind, status, assignee, payload FROM tasks "
                f"{where} ORDER BY id",
                *params,
            )
        except Exception as exc:
            raise BackendUnavailable(f"Labor allocation read failed: {exc}") from exc

        tasks = [task_info(r) for r in rows]
        return LaborAllocationResult(
            allocations=tasks,
            total_tasks=len(tasks),
            in_progress_count=sum(1 for t in tasks if t.status == "in_progress"),
            pending_count=sum(1 for t in tasks if t.status == "pending"),
            source=SOURCE,
        )

    # ── Write ────────────────────────────────────────────────────────────────

    async def execute_labor_allocation(
        self, request: LaborAllocateRequest
    ) -> LaborAllocateResult:
        workers = list(dict.fromkeys(w for w in request.worker_ids if w))
        if not workers:
            raise WriteNotApplied(
                "worker_ids is empty", rejection_code=REJECTION_INVALID_REQUEST
            )
        try:
            task_pk = int(request.task_id)
        except (TypeError, ValueError):
            raise WriteNotApplied(
                f"Task {request.task_id!r} not found",
                rejection_code=REJECTION_NOT_FOUND,
            ) from None

        try:
            db = await self._db()
        except Exception as exc:
            # No connection was obtained, so nothing was written.
            raise WriteNotApplied(
                f"Labor database unavailable: {exc}",
                rejection_code=REJECTION_PRECONDITION_FAILED,
            ) from exc

        allocation_id = str(uuid.uuid4())
        try:
            async with db.transaction() as conn:
                row = await conn.fetchrow(
                    "SELECT id, kind, status, assignee, payload FROM tasks "
                    "WHERE id = $1 FOR UPDATE",
                    task_pk,
                )
                if row is None:
                    raise WriteNotApplied(
                        f"Task {request.task_id} not found",
                        rejection_code=REJECTION_NOT_FOUND,
                    )
                payload = _payload(row)
                previous = payload.get("last_allocation") or {}
                if (
                    request.execution_id
                    and previous.get("execution_id") == request.execution_id
                ):
                    return self._result(
                        request, previous.get("allocation_id"), workers, replay=True
                    )
                if row["status"] in CLOSED_TASK_STATUSES:
                    raise WriteNotApplied(
                        f"Task {request.task_id} is {row['status']}",
                        rejection_code=REJECTION_PRECONDITION_FAILED,
                    )
                found = await conn.fetch(
                    "SELECT username FROM users WHERE username = ANY($1::text[]) "
                    "AND status::text = 'active' AND role::text = ANY($2::text[])",
                    workers,
                    list(WORKER_ROLES),
                )
                missing = sorted(set(workers) - {r["username"] for r in found})
                if missing:
                    raise WriteNotApplied(
                        f"Unknown or inactive worker(s): {', '.join(missing)}",
                        rejection_code=REJECTION_PRECONDITION_FAILED,
                    )

                record = {
                    "allocation_id": allocation_id,
                    "worker_ids": workers,
                    "proposal_id": request.proposal_id,
                    "decision_id": request.decision_id,
                    "execution_id": request.execution_id,
                }
                update = {"assigned_workers": workers, "last_allocation": record}
                if request.priority:
                    update["priority"] = request.priority
                if request.notes:
                    update["allocation_notes"] = request.notes
                await conn.execute(
                    "UPDATE tasks SET assignee = $1, "
                    "payload = COALESCE(payload, '{}'::jsonb) || $2::jsonb, "
                    "updated_at = now() WHERE id = $3",
                    workers[0],
                    json.dumps(update),
                    task_pk,
                )
        except BackendUnavailable:
            raise
        except Exception as exc:
            raise BackendUnavailable(
                f"Labor allocation write failed for task {request.task_id}: {exc}"
            ) from exc

        logger.info(
            "PostgresLaborProvider: task=%s allocated to %s allocation_id=%s proposal_id=%s",
            request.task_id,
            workers,
            allocation_id,
            request.proposal_id,
        )
        return self._result(request, allocation_id, workers)

    @staticmethod
    def _result(
        request: LaborAllocateRequest,
        allocation_id: str | None,
        workers: list[str],
        replay: bool = False,
    ) -> LaborAllocateResult:
        return LaborAllocateResult(
            success=True,
            allocation_id=allocation_id,
            task_id=request.task_id,
            worker_ids=workers,
            proposal_id=request.proposal_id,
            decision_id=request.decision_id,
            execution_id=request.execution_id,
            source=SOURCE,
            message=(
                f"Allocation for task {request.task_id} already recorded (replay)"
                if replay
                else f"Allocated {len(workers)} worker(s) to task {request.task_id}"
            ),
        )
