from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
import logging
import ast

from src.api.agents.inventory.equipment_agent import (
    get_equipment_agent,
    EquipmentAssetOperationsAgent,
)
from src.retrieval.structured import SQLRetriever

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Equipment"])

# Initialize SQL retriever
sql_retriever = SQLRetriever()


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


class ReleaseRequest(BaseModel):
    asset_id: str
    released_by: str
    notes: Optional[str] = None


class MaintenanceRequest(BaseModel):
    asset_id: str
    maintenance_type: str
    description: str
    scheduled_by: str
    scheduled_for: str
    estimated_duration_minutes: int = 60
    priority: str = "medium"


@router.get("/equipment", response_model=List[EquipmentAsset])
async def get_all_equipment(
    equipment_type: Optional[str] = None,
    zone: Optional[str] = None,
    status: Optional[str] = None,
):
    """Get all equipment assets with optional filtering."""
    try:
        await sql_retriever.initialize()

        # Build query with filters
        where_conditions = []
        params = []

        param_count = 1
        if equipment_type:
            where_conditions.append(f"type = ${param_count}")
            params.append(equipment_type)
            param_count += 1
        if zone:
            where_conditions.append(f"zone = ${param_count}")
            params.append(zone)
            param_count += 1
        if status:
            where_conditions.append(f"status = ${param_count}")
            params.append(status)
            param_count += 1

        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

        query = f"""
            SELECT asset_id, type, model, zone, status, owner_user, 
                   next_pm_due, last_maintenance, created_at, updated_at, metadata
            FROM equipment_assets 
            WHERE {where_clause}
            ORDER BY asset_id
        """

        # Use execute_query for parameterized queries
        results = await sql_retriever.execute_query(query, tuple(params))

        equipment_list = []
        for row in results:
            equipment_list.append(
                EquipmentAsset(
                    asset_id=row["asset_id"],
                    type=row["type"],
                    model=row["model"],
                    zone=row["zone"],
                    status=row["status"],
                    owner_user=row["owner_user"],
                    next_pm_due=(
                        row["next_pm_due"].isoformat() if row["next_pm_due"] else None
                    ),
                    last_maintenance=(
                        row["last_maintenance"].isoformat()
                        if row["last_maintenance"]
                        else None
                    ),
                    created_at=row["created_at"].isoformat(),
                    updated_at=row["updated_at"].isoformat(),
                    metadata=(
                        row["metadata"]
                        if isinstance(row["metadata"], dict)
                        else (
                            ast.literal_eval(row["metadata"])
                            if row["metadata"] and row["metadata"] != "{}"
                            else {}
                        )
                    ),
                )
            )

        return equipment_list

    except Exception as e:
        logger.error(f"Failed to get equipment assets: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve equipment assets"
        )


@router.get("/equipment/assignments/test")
async def test_assignments():
    """Test assignments endpoint."""
    return {"message": "Assignments endpoint is working"}


@router.get("/equipment/assignments", response_model=List[EquipmentAssignment])
async def get_equipment_assignments(
    asset_id: Optional[str] = None,
    assignee: Optional[str] = None,
    active_only: bool = True,
):
    """Get equipment assignments."""
    try:
        await sql_retriever.initialize()

        # Build the query based on parameters
        query_parts = [
            "SELECT id, asset_id, task_id, assignee, assignment_type, assigned_at, released_at, notes FROM equipment_assignments"
        ]
        params = []
        param_count = 0

        conditions = []

        if asset_id:
            param_count += 1
            conditions.append(f"asset_id = ${param_count}")
            params.append(asset_id)

        if assignee:
            param_count += 1
            conditions.append(f"assignee = ${param_count}")
            params.append(assignee)

        if active_only:
            conditions.append("released_at IS NULL")

        if conditions:
            query_parts.append("WHERE " + " AND ".join(conditions))

        query_parts.append("ORDER BY assigned_at DESC")

        query = " ".join(query_parts)

        logger.info(f"Executing assignments query: {query}")
        logger.info(f"Query parameters: {params}")

        # Execute the query
        results = await sql_retriever.execute_query(query, tuple(params))

        # Convert results to EquipmentAssignment objects
        assignments = []
        for row in results:
            assignment = EquipmentAssignment(
                id=row["id"],
                asset_id=row["asset_id"],
                task_id=row["task_id"],
                assignee=row["assignee"],
                assignment_type=row["assignment_type"],
                assigned_at=(
                    row["assigned_at"].isoformat() if row["assigned_at"] else None
                ),
                released_at=(
                    row["released_at"].isoformat() if row["released_at"] else None
                ),
                notes=row["notes"],
            )
            assignments.append(assignment)

        logger.info(f"Found {len(assignments)} assignments")
        return assignments

    except Exception as e:
        logger.error(f"Failed to get equipment assignments: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve equipment assignments: {str(e)}",
        )


@router.get("/equipment/{asset_id}", response_model=EquipmentAsset)
async def get_equipment_by_id(asset_id: str):
    """Get a specific equipment asset by asset_id."""
    try:
        await sql_retriever.initialize()
        query = """
            SELECT asset_id, type, model, zone, status, owner_user, 
                   next_pm_due, last_maintenance, created_at, updated_at, metadata
            FROM equipment_assets 
            WHERE asset_id = $1
        """

        result = await sql_retriever.execute_query(query, (asset_id,))
        result = result[0] if result else None

        if not result:
            raise HTTPException(
                status_code=404, detail=f"Equipment asset {asset_id} not found"
            )

        return EquipmentAsset(
            asset_id=result["asset_id"],
            type=result["type"],
            model=result["model"],
            zone=result["zone"],
            status=result["status"],
            owner_user=result["owner_user"],
            next_pm_due=(
                result["next_pm_due"].isoformat() if result["next_pm_due"] else None
            ),
            last_maintenance=(
                result["last_maintenance"].isoformat()
                if result["last_maintenance"]
                else None
            ),
            created_at=result["created_at"].isoformat(),
            updated_at=result["updated_at"].isoformat(),
            metadata=(
                result["metadata"]
                if isinstance(result["metadata"], dict)
                else (
                    ast.literal_eval(result["metadata"])
                    if result["metadata"] and result["metadata"] != "{}"
                    else {}
                )
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get equipment asset {asset_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve equipment asset"
        )


@router.get("/equipment/{asset_id}/status", response_model=Dict[str, Any])
async def get_equipment_status(asset_id: str):
    """Get live equipment status including telemetry data."""
    try:
        equipment_agent = await get_equipment_agent()

        # Get equipment status
        status_result = await equipment_agent.asset_tools.get_equipment_status(
            asset_id=asset_id
        )

        # Get recent telemetry data
        telemetry_result = await equipment_agent.asset_tools.get_equipment_telemetry(
            asset_id=asset_id, hours_back=1
        )

        return {
            "equipment_status": status_result,
            "telemetry_data": telemetry_result,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to get equipment status for {asset_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve equipment status"
        )


@router.post("/equipment/assign", response_model=Dict[str, Any])
async def assign_equipment(request: AssignmentRequest):
    """Assign equipment to a user, task, or zone."""
    try:
        equipment_agent = await get_equipment_agent()

        result = await equipment_agent.asset_tools.assign_equipment(
            asset_id=request.asset_id,
            assignee=request.assignee,
            assignment_type=request.assignment_type,
            task_id=request.task_id,
            duration_hours=request.duration_hours,
            notes=request.notes,
        )

        if not result.get("success", False):
            raise HTTPException(
                status_code=400, detail=result.get("error", "Assignment failed")
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to assign equipment {request.asset_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to assign equipment")


@router.post("/equipment/release", response_model=Dict[str, Any])
async def release_equipment(request: ReleaseRequest):
    """Release equipment from current assignment."""
    try:
        equipment_agent = await get_equipment_agent()

        result = await equipment_agent.asset_tools.release_equipment(
            asset_id=request.asset_id,
            released_by=request.released_by,
            notes=request.notes,
        )

        if not result.get("success", False):
            raise HTTPException(
                status_code=400, detail=result.get("error", "Release failed")
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to release equipment {request.asset_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to release equipment")


@router.get("/equipment/{asset_id}/telemetry", response_model=List[EquipmentTelemetry])
async def get_equipment_telemetry(
    asset_id: str, metric: Optional[str] = None, hours_back: int = 168
):
    """Get equipment telemetry data."""
    try:
        equipment_agent = await get_equipment_agent()

        result = await equipment_agent.asset_tools.get_equipment_telemetry(
            asset_id=asset_id, metric=metric, hours_back=hours_back
        )

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        telemetry_list = []
        for data_point in result.get("telemetry_data", []):
            telemetry_list.append(
                EquipmentTelemetry(
                    timestamp=data_point["timestamp"],
                    asset_id=data_point["asset_id"],
                    metric=data_point["metric"],
                    value=data_point["value"],
                    unit=data_point["unit"],
                    quality_score=data_point["quality_score"],
                )
            )

        return telemetry_list

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get telemetry for equipment {asset_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve telemetry data")


@router.post("/equipment/maintenance", response_model=Dict[str, Any])
async def schedule_maintenance(request: MaintenanceRequest):
    """Schedule maintenance for equipment."""
    try:
        equipment_agent = await get_equipment_agent()

        # Parse scheduled_for datetime
        scheduled_for = datetime.fromisoformat(
            request.scheduled_for.replace("Z", "+00:00")
        )

        result = await equipment_agent.asset_tools.schedule_maintenance(
            asset_id=request.asset_id,
            maintenance_type=request.maintenance_type,
            description=request.description,
            scheduled_by=request.scheduled_by,
            scheduled_for=scheduled_for,
            estimated_duration_minutes=request.estimated_duration_minutes,
            priority=request.priority,
        )

        if not result.get("success", False):
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Maintenance scheduling failed"),
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to schedule maintenance for equipment {request.asset_id}: {e}"
        )
        raise HTTPException(status_code=500, detail="Failed to schedule maintenance")


@router.get("/equipment/maintenance/schedule", response_model=List[MaintenanceRecord])
async def get_maintenance_schedule(
    asset_id: Optional[str] = None,
    maintenance_type: Optional[str] = None,
    days_ahead: int = 30,
):
    """Get maintenance schedule for equipment."""
    try:
        equipment_agent = await get_equipment_agent()

        result = await equipment_agent.asset_tools.get_maintenance_schedule(
            asset_id=asset_id, maintenance_type=maintenance_type, days_ahead=days_ahead
        )

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        maintenance_list = []
        for record in result.get("maintenance_schedule", []):
            maintenance_list.append(
                MaintenanceRecord(
                    id=record["id"],
                    asset_id=record["asset_id"],
                    maintenance_type=record["maintenance_type"],
                    description=record["description"],
                    performed_by=record["performed_by"],
                    performed_at=record["performed_at"],
                    duration_minutes=record["duration_minutes"],
                    cost=record.get("cost"),
                    notes=record.get("notes"),
                )
            )

        return maintenance_list

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get maintenance schedule: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve maintenance schedule"
        )
