# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Safety router — Batch D.

Incident CRUD uses SQLRetriever directly.  The canonical SafetyComplianceAgent
is a reasoning agent wired into the chat router — it is not used for CRUD.

Policies are static reference data (no DB table) — preserved as-is from src/.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.retrieval.structured import SQLRetriever

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Safety"])

_sql = SQLRetriever()


class SafetyIncident(BaseModel):
    id: int
    severity: str
    description: str
    reported_by: str
    occurred_at: str


class SafetyIncidentCreate(BaseModel):
    severity: str
    description: str
    reported_by: str


class SafetyPolicy(BaseModel):
    id: str
    name: str
    category: str
    last_updated: str
    status: str
    summary: str


_POLICIES: List[SafetyPolicy] = [
    SafetyPolicy(
        id="POL-001",
        name="Personal Protective Equipment (PPE) Policy",
        category="Safety Equipment",
        last_updated="2024-01-15",
        status="Active",
        summary="All personnel must wear appropriate PPE in designated areas",
    ),
    SafetyPolicy(
        id="POL-002",
        name="Forklift Operation Safety Guidelines",
        category="Equipment Safety",
        last_updated="2024-01-10",
        status="Active",
        summary="Comprehensive guidelines for safe forklift operation",
    ),
    SafetyPolicy(
        id="POL-003",
        name="Emergency Evacuation Procedures",
        category="Emergency Response",
        last_updated="2024-01-05",
        status="Active",
        summary="Step-by-step emergency evacuation procedures",
    ),
    SafetyPolicy(
        id="POL-004",
        name="Chemical Handling Safety Protocol",
        category="Chemical Safety",
        last_updated="2024-01-12",
        status="Active",
        summary="Safe handling and storage procedures for chemicals",
    ),
    SafetyPolicy(
        id="POL-005",
        name="Ladder and Elevated Work Safety",
        category="Fall Prevention",
        last_updated="2024-01-08",
        status="Active",
        summary="Safety requirements for working at heights",
    ),
]


@router.get("/safety/incidents", response_model=List[SafetyIncident])
async def get_incidents():
    """List all safety incidents ordered by occurrence time."""
    try:
        await _sql.initialize()
        rows = await _sql.fetch_all(
            "SELECT id, severity, description, reported_by, occurred_at "
            "FROM safety_incidents ORDER BY occurred_at DESC"
        )
        return [
            SafetyIncident(
                id=r["id"],
                severity=r["severity"],
                description=r["description"],
                reported_by=r["reported_by"],
                occurred_at=r["occurred_at"].isoformat() if r["occurred_at"] else "",
            )
            for r in rows
        ]
    except Exception as exc:
        logger.error("Failed to get safety incidents: %s", exc)
        raise HTTPException(
            status_code=500, detail="Failed to retrieve safety incidents"
        )


@router.get("/safety/incidents/{incident_id}", response_model=SafetyIncident)
async def get_incident(incident_id: int):
    """Get a specific safety incident by ID."""
    try:
        await _sql.initialize()
        row = await _sql.fetch_one(
            "SELECT id, severity, description, reported_by, occurred_at "
            "FROM safety_incidents WHERE id = $1",
            incident_id,
        )
        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"Safety incident {incident_id} not found",
            )
        return SafetyIncident(
            id=row["id"],
            severity=row["severity"],
            description=row["description"],
            reported_by=row["reported_by"],
            occurred_at=row["occurred_at"].isoformat() if row["occurred_at"] else "",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to get safety incident %s: %s", incident_id, exc)
        raise HTTPException(
            status_code=500, detail="Failed to retrieve safety incident"
        )


@router.post("/safety/incidents", response_model=SafetyIncident)
async def create_incident(incident: SafetyIncidentCreate):
    """Create a new safety incident record."""
    try:
        await _sql.initialize()
        result = await _sql.fetch_one(
            """
            INSERT INTO safety_incidents (severity, description, reported_by, occurred_at)
            VALUES ($1, $2, $3, NOW())
            RETURNING id, severity, description, reported_by, occurred_at
            """,
            incident.severity,
            incident.description,
            incident.reported_by,
        )
        return SafetyIncident(
            id=result["id"],
            severity=result["severity"],
            description=result["description"],
            reported_by=result["reported_by"],
            occurred_at=(
                result["occurred_at"].isoformat() if result["occurred_at"] else ""
            ),
        )
    except Exception as exc:
        logger.error("Failed to create safety incident: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create safety incident")


@router.get("/safety/policies", response_model=List[SafetyPolicy])
async def get_policies():
    """List all safety policies (static reference data)."""
    return _POLICIES


@router.get("/safety/policies/{policy_id}", response_model=SafetyPolicy)
async def get_policy(policy_id: str):
    """Get a specific safety policy by ID."""
    for policy in _POLICIES:
        if policy.id == policy_id:
            return policy
    raise HTTPException(status_code=404, detail=f"Safety policy {policy_id} not found")
