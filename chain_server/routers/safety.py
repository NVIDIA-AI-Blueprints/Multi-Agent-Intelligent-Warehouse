from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from inventory_retriever.structured import SQLRetriever
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Safety"])

# Initialize SQL retriever
sql_retriever = SQLRetriever()


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


@router.get("/safety/incidents", response_model=List[SafetyIncident])
async def get_incidents():
    """Get all safety incidents."""
    try:
        await sql_retriever.initialize()
        query = """
            SELECT id, severity, description, reported_by, occurred_at 
            FROM safety_incidents 
            ORDER BY occurred_at DESC
        """
        results = await sql_retriever.fetch_all(query)

        incidents = []
        for row in results:
            incidents.append(
                SafetyIncident(
                    id=row["id"],
                    severity=row["severity"],
                    description=row["description"],
                    reported_by=row["reported_by"],
                    occurred_at=(
                        row["occurred_at"].isoformat() if row["occurred_at"] else ""
                    ),
                )
            )

        return incidents
    except Exception as e:
        logger.error(f"Failed to get safety incidents: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve safety incidents"
        )


@router.get("/safety/incidents/{incident_id}", response_model=SafetyIncident)
async def get_incident(incident_id: int):
    """Get a specific safety incident by ID."""
    try:
        await sql_retriever.initialize()
        query = """
            SELECT id, severity, description, reported_by, occurred_at 
            FROM safety_incidents 
            WHERE id = $1
        """
        result = await sql_retriever.fetch_one(query, incident_id)

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Safety incident with ID {incident_id} not found",
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get safety incident {incident_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve safety incident"
        )


@router.post("/safety/incidents", response_model=SafetyIncident)
async def create_incident(incident: SafetyIncidentCreate):
    """Create a new safety incident."""
    try:
        await sql_retriever.initialize()
        query = """
            INSERT INTO safety_incidents (severity, description, reported_by, occurred_at)
            VALUES ($1, $2, $3, NOW())
            RETURNING id, severity, description, reported_by, occurred_at
        """
        result = await sql_retriever.fetch_one(
            query, incident.severity, incident.description, incident.reported_by
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
    except Exception as e:
        logger.error(f"Failed to create safety incident: {e}")
        raise HTTPException(status_code=500, detail="Failed to create safety incident")


@router.get("/safety/policies", response_model=List[SafetyPolicy])
async def get_policies():
    """Get all safety policies."""
    try:
        # Return mock safety policies (in a real system, this would come from a policy management system)
        policies = [
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

        return policies
    except Exception as e:
        logger.error(f"Failed to get safety policies: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve safety policies"
        )


@router.get("/safety/policies/{policy_id}", response_model=SafetyPolicy)
async def get_policy(policy_id: str):
    """Get a specific safety policy by ID."""
    try:
        # Get all policies and find the one with matching ID
        policies = await get_policies()
        for policy in policies:
            if policy.id == policy_id:
                return policy

        raise HTTPException(
            status_code=404, detail=f"Safety policy with ID {policy_id} not found"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get safety policy {policy_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve safety policy")
