# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Operations router — Batch D.

All task CRUD endpoints use SQLRetriever directly — no canonical agent needed
for CRUD operations.  The canonical OperationsCoordinationAgent is a reasoning
agent that processes natural-language queries and is wired into the chat router.

Bug fixed from src/api/routers/operations.py:
    PUT /operations/tasks/{task_id} referenced undefined ``task_queries``.
    Fixed to use ``TaskQueries()``.
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.retrieval.structured import SQLRetriever, TaskQueries

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Operations"])

_sql = SQLRetriever()
_task_queries = TaskQueries()


class Task(BaseModel):
    id: int
    kind: str
    status: str
    assignee: Optional[str] = None
    payload: dict
    created_at: str
    updated_at: str


class TaskCreate(BaseModel):
    kind: str
    status: str = "pending"
    assignee: Optional[str] = None
    payload: dict = {}


class TaskUpdate(BaseModel):
    status: Optional[str] = None
    assignee: Optional[str] = None
    payload: Optional[dict] = None


class WorkforceStatus(BaseModel):
    total_workers: int
    active_workers: int
    available_workers: int
    tasks_in_progress: int
    tasks_pending: int


def _parse_payload(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def _row_to_task(row: dict) -> Task:
    return Task(
        id=row["id"],
        kind=row["kind"],
        status=row["status"],
        assignee=row["assignee"],
        payload=_parse_payload(row["payload"]),
        created_at=row["created_at"].isoformat() if row["created_at"] else "",
        updated_at=row["updated_at"].isoformat() if row["updated_at"] else "",
    )


@router.get("/operations/tasks", response_model=List[Task])
async def get_tasks():
    """List all tasks ordered by creation time."""
    try:
        await _sql.initialize()
        rows = await _sql.fetch_all(
            "SELECT id, kind, status, assignee, payload, created_at, updated_at "
            "FROM tasks ORDER BY created_at DESC"
        )
        return [_row_to_task(r) for r in rows]
    except Exception as exc:
        logger.error("Failed to get tasks: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve tasks")


@router.get("/operations/tasks/{task_id}", response_model=Task)
async def get_task(task_id: int):
    """Get a specific task by ID."""
    try:
        await _sql.initialize()
        task = await _task_queries.get_task_by_id(_sql, task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        return _row_to_task(task)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to get task %s: %s", task_id, exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve task")


@router.post("/operations/tasks", response_model=Task)
async def create_task(task: TaskCreate):
    """Create a new task."""
    try:
        await _sql.initialize()
        result = await _sql.fetch_one(
            """
            INSERT INTO tasks (kind, status, assignee, payload, created_at, updated_at)
            VALUES ($1, $2, $3, $4, NOW(), NOW())
            RETURNING id, kind, status, assignee, payload, created_at, updated_at
            """,
            task.kind,
            task.status,
            task.assignee,
            json.dumps(task.payload),
        )
        return _row_to_task(result)
    except Exception as exc:
        logger.error("Failed to create task: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create task")


@router.put("/operations/tasks/{task_id}", response_model=Task)
async def update_task(task_id: int, update: TaskUpdate):
    """Update status, assignee, or payload of an existing task."""
    try:
        await _sql.initialize()
        current = await _task_queries.get_task_by_id(_sql, task_id)
        if not current:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        new_status = update.status if update.status is not None else current["status"]
        new_assignee = (
            update.assignee if update.assignee is not None else current["assignee"]
        )
        new_payload = (
            update.payload if update.payload is not None else current["payload"]
        )
        if isinstance(new_payload, dict):
            new_payload = json.dumps(new_payload)
        elif new_payload is None:
            new_payload = json.dumps({})

        result = await _sql.fetch_one(
            """
            UPDATE tasks
            SET status = $1, assignee = $2, payload = $3, updated_at = NOW()
            WHERE id = $4
            RETURNING id, kind, status, assignee, payload, created_at, updated_at
            """,
            new_status,
            new_assignee,
            new_payload,
            task_id,
        )
        return _row_to_task(result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to update task %s: %s", task_id, exc)
        raise HTTPException(status_code=500, detail="Failed to update task")


@router.post("/operations/tasks/{task_id}/assign")
async def assign_task(task_id: int, assignee: str):
    """Assign a task to a worker."""
    try:
        await _sql.initialize()
        await _task_queries.assign_task(_sql, task_id, assignee)
        task = await _task_queries.get_task_by_id(_sql, task_id)
        return _row_to_task(task)
    except Exception as exc:
        logger.error("Failed to assign task %s: %s", task_id, exc)
        raise HTTPException(status_code=500, detail="Failed to assign task")


@router.get("/operations/workforce", response_model=WorkforceStatus)
async def get_workforce_status():
    """Get aggregate workforce and task statistics."""
    try:
        await _sql.initialize()

        task_stats = await _sql.fetch_one("""
            SELECT
                COUNT(*) AS total_tasks,
                COUNT(CASE WHEN status = 'in_progress' THEN 1 END) AS in_progress,
                COUNT(CASE WHEN status = 'pending' THEN 1 END) AS pending
            FROM tasks
            """)
        user_stats = await _sql.fetch_one("""
            SELECT
                COUNT(*) AS total_users,
                COUNT(CASE WHEN status = 'active' THEN 1 END) AS active_users,
                COUNT(CASE WHEN role IN ('operator', 'supervisor', 'manager')
                           AND status = 'active' THEN 1 END) AS operational_workers
            FROM users
            """)

        operational = user_stats.get("operational_workers") or 0
        in_progress = task_stats["in_progress"] or 0

        return WorkforceStatus(
            total_workers=user_stats.get("total_users") or 0,
            active_workers=user_stats.get("active_users") or 0,
            available_workers=max(0, operational - in_progress),
            tasks_in_progress=in_progress,
            tasks_pending=task_stats["pending"] or 0,
        )
    except Exception as exc:
        logger.error("Failed to get workforce status: %s", exc)
        raise HTTPException(
            status_code=500, detail="Failed to retrieve workforce status"
        )
