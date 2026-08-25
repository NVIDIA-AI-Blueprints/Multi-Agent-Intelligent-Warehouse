# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Equipment router — Batch C.

Key change from src/api/routers/equipment.py:
- Write paths (assign, release, maintenance) use ``runtime.equipment_agent``
  from MAIWRuntime instead of the legacy ``get_equipment_agent()`` factory.
- Read-list / filter paths still use SQLRetriever directly (no agent needed).
- The live status path uses ``runtime.equipment_agent`` for the state snapshot.

All write paths go through the canonical STATE → REASON → PROPOSE → DECIDE pipeline.
Reads are always direct DB queries — no pipeline, no latency.

If ``runtime.equipment_agent`` is None at startup (MCP server not configured),
write endpoints return 503 rather than 500.
"""

from __future__ import annotations

import ast
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from maiw_api.dependencies import get_runtime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Equipment"])

# Lazy-init: deferred import so importing this module does not require asyncpg.
# asyncpg is only pulled in when the first request initialises the connection.
_sql = None


def _get_sql():
    global _sql
    if _sql is None:
        from src.retrieval.structured import SQLRetriever

        _sql = SQLRetriever()
    return _sql


# ── Request / Response models ─────────────────────────────────────────────────


class EquipmentAsset(BaseModel):
    asset_id: str
    type: str
    model: Optional[str] = None
    zone: Optional[str] = None
    status: str
    owner_user: Optional[str] = None
    next_pm_due: Optional[str] = None
    last_maintenance: Optional[str] = None
    created_at: str
    updated_at: str
    metadata: Dict[str, Any] = {}


class EquipmentAssignment(BaseModel):
    id: int
    asset_id: str
    task_id: Optional[str] = None
    assignee: str
    assignment_type: str
    assigned_at: str
    released_at: Optional[str] = None
    notes: Optional[str] = None


class EquipmentTelemetry(BaseModel):
    timestamp: str
    asset_id: str
    metric: str
    value: float
    unit: str
    quality_score: float


class MaintenanceRecord(BaseModel):
    id: int
    asset_id: str
    maintenance_type: str
    description: str
    performed_by: str
    performed_at: str
    duration_minutes: int
    cost: Optional[float] = None
    notes: Optional[str] = None


class AssignmentRequest(BaseModel):
    asset_id: str
    assignee: str
    assignment_type: str = "task"
    task_id: Optional[str] = None
    duration_hours: Optional[int] = None
    notes: Optional[str] = None
    warehouse_id: Optional[str] = None


class ReleaseRequest(BaseModel):
    asset_id: str
    released_by: str
    notes: Optional[str] = None
    warehouse_id: Optional[str] = None


class MaintenanceRequest(BaseModel):
    asset_id: str
    maintenance_type: str
    description: str
    scheduled_by: str
    scheduled_for: str
    estimated_duration_minutes: int = 60
    priority: str = "medium"
    warehouse_id: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_metadata(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if raw and raw != "{}":
        try:
            return ast.literal_eval(raw)
        except Exception:
            return {}
    return {}


def _row_to_asset(row: dict) -> EquipmentAsset:
    return EquipmentAsset(
        asset_id=row["asset_id"],
        type=row["type"],
        model=row["model"],
        zone=row["zone"],
        status=row["status"],
        owner_user=row["owner_user"],
        next_pm_due=row["next_pm_due"].isoformat() if row["next_pm_due"] else None,
        last_maintenance=(
            row["last_maintenance"].isoformat() if row["last_maintenance"] else None
        ),
        created_at=row["created_at"].isoformat(),
        updated_at=row["updated_at"].isoformat(),
        metadata=_parse_metadata(row["metadata"]),
    )


def _require_agent(runtime, name: str = "equipment_agent"):
    agent = getattr(runtime, name, None)
    if agent is None:
        raise HTTPException(
            status_code=503,
            detail=(
                f"{name} is not available — MCP server may not be configured. "
                "Check MAIW_MCP_SERVER_EQUIPMENT_URL."
            ),
        )
    return agent


# ── Read endpoints (SQL, no agent) ────────────────────────────────────────────


@router.get("/equipment", response_model=List[EquipmentAsset])
async def get_all_equipment(
    equipment_type: Optional[str] = None,
    zone: Optional[str] = None,
    status: Optional[str] = None,
):
    """List equipment assets with optional filtering."""
    try:
        sql = _get_sql()
        await sql.initialize()

        conditions, params, n = [], [], 1
        if equipment_type:
            conditions.append(f"type = ${n}")
            params.append(equipment_type)
            n += 1
        if zone:
            conditions.append(f"zone = ${n}")
            params.append(zone)
            n += 1
        if status:
            conditions.append(f"status = ${n}")
            params.append(status)
            n += 1

        where = " AND ".join(conditions) if conditions else "1=1"
        query = f"""
            SELECT asset_id, type, model, zone, status, owner_user,
                   next_pm_due, last_maintenance, created_at, updated_at, metadata
            FROM equipment_assets
            WHERE {where}
            ORDER BY asset_id
        """
        rows = await sql.execute_query(query, tuple(params))
        return [_row_to_asset(r) for r in rows]
    except Exception as exc:
        logger.error("Failed to list equipment assets: %s", exc)
        raise HTTPException(
            status_code=500, detail="Failed to retrieve equipment assets"
        )


@router.get("/equipment/assignments", response_model=List[EquipmentAssignment])
async def get_equipment_assignments(
    asset_id: Optional[str] = None,
    assignee: Optional[str] = None,
    active_only: bool = True,
):
    """List equipment assignments with optional filters."""
    try:
        sql = _get_sql()
        await sql.initialize()

        parts = [
            "SELECT id, asset_id, task_id, assignee, assignment_type, "
            "assigned_at, released_at, notes FROM equipment_assignments"
        ]
        conditions, params, n = [], [], 0
        if asset_id:
            n += 1
            conditions.append(f"asset_id = ${n}")
            params.append(asset_id)
        if assignee:
            n += 1
            conditions.append(f"assignee = ${n}")
            params.append(assignee)
        if active_only:
            conditions.append("released_at IS NULL")
        if conditions:
            parts.append("WHERE " + " AND ".join(conditions))
        parts.append("ORDER BY assigned_at DESC")

        rows = await sql.execute_query(" ".join(parts), tuple(params))
        return [
            EquipmentAssignment(
                id=r["id"],
                asset_id=r["asset_id"],
                task_id=r["task_id"],
                assignee=r["assignee"],
                assignment_type=r["assignment_type"],
                assigned_at=r["assigned_at"].isoformat() if r["assigned_at"] else None,
                released_at=r["released_at"].isoformat() if r["released_at"] else None,
                notes=r["notes"],
            )
            for r in rows
        ]
    except Exception as exc:
        logger.error("Failed to list equipment assignments: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve equipment assignments: {exc}",
        )


@router.get("/equipment/maintenance/schedule", response_model=List[MaintenanceRecord])
async def get_maintenance_schedule(
    asset_id: Optional[str] = None,
    maintenance_type: Optional[str] = None,
    days_ahead: int = 30,
    runtime=Depends(get_runtime),
):
    """Get upcoming maintenance schedule."""
    agent = _require_agent(runtime)
    try:
        result = await agent.asset_tools.get_maintenance_schedule(
            asset_id=asset_id,
            maintenance_type=maintenance_type,
            days_ahead=days_ahead,
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return [
            MaintenanceRecord(
                id=r["id"],
                asset_id=r["asset_id"],
                maintenance_type=r["maintenance_type"],
                description=r["description"],
                performed_by=r["performed_by"],
                performed_at=r["performed_at"],
                duration_minutes=r["duration_minutes"],
                cost=r.get("cost"),
                notes=r.get("notes"),
            )
            for r in result.get("maintenance_schedule", [])
        ]
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to get maintenance schedule: %s", exc)
        raise HTTPException(
            status_code=500, detail="Failed to retrieve maintenance schedule"
        )


@router.get("/equipment/{asset_id}", response_model=EquipmentAsset)
async def get_equipment_by_id(asset_id: str):
    """Get a single equipment asset by ID."""
    try:
        sql = _get_sql()
        await sql.initialize()
        rows = await sql.execute_query(
            """
            SELECT asset_id, type, model, zone, status, owner_user,
                   next_pm_due, last_maintenance, created_at, updated_at, metadata
            FROM equipment_assets WHERE asset_id = $1
            """,
            (asset_id,),
        )
        if not rows:
            raise HTTPException(
                status_code=404, detail=f"Equipment asset {asset_id} not found"
            )
        return _row_to_asset(rows[0])
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to get equipment %s: %s", asset_id, exc)
        raise HTTPException(
            status_code=500, detail="Failed to retrieve equipment asset"
        )


@router.get("/equipment/{asset_id}/telemetry", response_model=List[EquipmentTelemetry])
async def get_equipment_telemetry(
    asset_id: str,
    metric: Optional[str] = None,
    hours_back: int = 168,
    runtime=Depends(get_runtime),
):
    """Get equipment telemetry from asset tools."""
    agent = _require_agent(runtime)
    try:
        result = await agent.asset_tools.get_equipment_telemetry(
            asset_id=asset_id, metric=metric, hours_back=hours_back
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return [
            EquipmentTelemetry(
                timestamp=dp["timestamp"],
                asset_id=dp["asset_id"],
                metric=dp["metric"],
                value=dp["value"],
                unit=dp["unit"],
                quality_score=dp["quality_score"],
            )
            for dp in result.get("telemetry_data", [])
        ]
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to get telemetry for %s: %s", asset_id, exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve telemetry data")


# ── State-aware read (agent + state provider) ─────────────────────────────────


@router.get("/equipment/{asset_id}/status", response_model=Dict[str, Any])
async def get_equipment_status(asset_id: str, runtime=Depends(get_runtime)):
    """
    Get live equipment status including a WarehouseState snapshot.

    Read-only: uses the canonical state pipeline (STATE phase only).
    The ``state_snapshot`` block is present when the MCP equipment server
    is configured; omitted otherwise.
    """
    agent = _require_agent(runtime)
    try:
        state_context = await agent.get_equipment_state_snapshot(asset_id=asset_id)
        status_result = await agent.asset_tools.get_equipment_status(asset_id=asset_id)
        telemetry_result = await agent.asset_tools.get_equipment_telemetry(
            asset_id=asset_id, hours_back=1
        )
        response: Dict[str, Any] = {
            "equipment_status": status_result,
            "telemetry_data": telemetry_result,
            "timestamp": datetime.now().isoformat(),
        }
        if state_context:
            response["state_snapshot"] = state_context
        return response
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to get equipment status for %s: %s", asset_id, exc)
        raise HTTPException(
            status_code=500, detail="Failed to retrieve equipment status"
        )


# ── Write endpoints (full pipeline: PROPOSE → DECIDE → EXECUTE) ───────────────


@router.post("/equipment/assign", response_model=Dict[str, Any])
async def assign_equipment(request: AssignmentRequest, runtime=Depends(get_runtime)):
    """
    Propose an equipment assignment through the canonical pipeline.

    Response shape::

        {
            "status": "requires_human_approval" | "approved" | "rejected"
                      | "requires_fresh_state" | "error",
            "action": "warehouse.equipment.assign",
            "proposal_id": "<uuid>",
            "decision_id": "<uuid>",
            "reason": "<explanation>",
            "executed": false | true,
        }
    """
    agent = _require_agent(runtime)
    try:
        result = await agent.propose_equipment_assignment(
            asset_id=request.asset_id,
            assignee=request.assignee,
            assignment_type=request.assignment_type,
            task_id=request.task_id,
            duration_hours=(
                float(request.duration_hours) if request.duration_hours else None
            ),
            notes=request.notes,
            warehouse_id=request.warehouse_id or "default",
        )
        if result.get("status") == "error":
            raise HTTPException(
                status_code=400,
                detail=result.get("reason", "Assignment proposal failed"),
            )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to propose assignment for %s: %s", request.asset_id, exc)
        raise HTTPException(
            status_code=500, detail="Failed to process assignment proposal"
        )


@router.post("/equipment/release", response_model=Dict[str, Any])
async def release_equipment(request: ReleaseRequest, runtime=Depends(get_runtime)):
    """
    Propose and (if approved) execute releasing equipment from its current assignment.

    LOW risk: DecisionEngine auto-approves unless equipment state is stale/absent.
    """
    agent = _require_agent(runtime)
    try:
        result = await agent.propose_equipment_release(
            asset_id=request.asset_id,
            released_by=request.released_by,
            notes=request.notes,
            warehouse_id=request.warehouse_id or "default",
        )
        if result.get("status") == "error":
            raise HTTPException(
                status_code=400,
                detail=result.get("reason", "Release failed"),
            )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to release equipment %s: %s", request.asset_id, exc)
        raise HTTPException(status_code=500, detail="Failed to release equipment")


@router.post("/equipment/maintenance", response_model=Dict[str, Any])
async def schedule_maintenance(
    request: MaintenanceRequest, runtime=Depends(get_runtime)
):
    """
    Propose scheduling maintenance for equipment.

    MEDIUM risk: DecisionEngine always returns requires_human_approval.
    """
    agent = _require_agent(runtime)
    try:
        result = await agent.propose_schedule_maintenance(
            asset_id=request.asset_id,
            maintenance_type=request.maintenance_type,
            description=request.description,
            scheduled_by=request.scheduled_by,
            scheduled_for=request.scheduled_for,
            estimated_duration_minutes=request.estimated_duration_minutes,
            priority=request.priority,
            warehouse_id=request.warehouse_id or "default",
        )
        if result.get("status") == "error":
            raise HTTPException(
                status_code=400,
                detail=result.get("reason", "Maintenance scheduling failed"),
            )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to schedule maintenance for %s: %s", request.asset_id, exc)
        raise HTTPException(status_code=500, detail="Failed to schedule maintenance")
