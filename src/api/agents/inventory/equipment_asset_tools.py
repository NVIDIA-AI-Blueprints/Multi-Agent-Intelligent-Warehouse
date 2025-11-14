"""
Equipment & Asset Operations Agent Action Tools

Provides comprehensive action tools for equipment and asset management including:
- Equipment availability and assignment tracking
- Asset utilization and performance monitoring
- Maintenance scheduling and work order management
- Equipment telemetry and status monitoring
- Compliance and safety integration
"""

import logging
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import asyncio
import json

from src.api.services.llm.nim_client import get_nim_client
from src.retrieval.structured.sql_retriever import SQLRetriever
from src.api.services.wms.integration_service import get_wms_service
from src.api.services.erp.integration_service import get_erp_service
from src.api.services.scanning.integration_service import get_scanning_service

logger = logging.getLogger(__name__)


@dataclass
class EquipmentAsset:
    """Equipment asset information."""

    asset_id: str
    type: str
    model: str
    zone: str
    status: str
    owner_user: Optional[str]
    next_pm_due: Optional[datetime]
    last_maintenance: Optional[datetime]
    metadata: Dict[str, Any]


@dataclass
class EquipmentAssignment:
    """Equipment assignment information."""

    id: int
    asset_id: str
    task_id: Optional[str]
    assignee: str
    assignment_type: str
    assigned_at: datetime
    released_at: Optional[datetime]
    notes: Optional[str]


@dataclass
class EquipmentTelemetry:
    """Equipment telemetry data."""

    ts: datetime
    asset_id: str
    metric: str
    value: float
    unit: str
    quality_score: float


@dataclass
class MaintenanceRecord:
    """Equipment maintenance record."""

    id: int
    asset_id: str
    maintenance_type: str
    description: str
    performed_by: str
    performed_at: datetime
    duration_minutes: int
    cost: float
    notes: Optional[str]


class EquipmentAssetTools:
    """Action tools for equipment and asset operations."""

    def __init__(self):
        self.sql_retriever = None
        self.nim_client = None
        self.wms_service = None
        self.erp_service = None
        self.scanning_service = None

    async def initialize(self) -> None:
        """Initialize the action tools with required services."""
        try:
            self.sql_retriever = SQLRetriever()
            self.nim_client = await get_nim_client()
            self.wms_service = await get_wms_service()
            self.erp_service = await get_erp_service()
            self.scanning_service = await get_scanning_service()
            logger.info("Equipment Asset Tools initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Equipment Asset Tools: {e}")
            raise

    async def get_equipment_status(
        self,
        asset_id: Optional[str] = None,
        equipment_type: Optional[str] = None,
        zone: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get equipment status and availability.

        Args:
            asset_id: Specific equipment asset ID
            equipment_type: Filter by equipment type (forklift, amr, agv, etc.)
            zone: Filter by zone
            status: Filter by status (available, assigned, charging, etc.)

        Returns:
            Dictionary containing equipment status information
        """
        logger.info(
            f"Getting equipment status for asset_id: {asset_id}, type: {equipment_type}, zone: {zone}"
        )

        try:
            # Build query based on filters
            where_conditions = []
            params = []

            param_count = 1
            if asset_id:
                where_conditions.append(f"asset_id = ${param_count}")
                params.append(asset_id)
                param_count += 1
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

            # Build safe WHERE clause
            if where_conditions:
                where_clause = " AND ".join(where_conditions)
                query = f"""
                    SELECT 
                        asset_id, type, model, zone, status, owner_user, 
                        next_pm_due, last_maintenance, created_at, updated_at, metadata
                    FROM equipment_assets 
                    WHERE {where_clause}
                    ORDER BY asset_id
                """  # nosec B608 - Safe: using parameterized queries
            else:
                query = """
                    SELECT 
                        asset_id, type, model, zone, status, owner_user, 
                        next_pm_due, last_maintenance, created_at, updated_at, metadata
                    FROM equipment_assets 
                    ORDER BY asset_id
                """

            if params:
                results = await self.sql_retriever.fetch_all(query, *params)
            else:
                results = await self.sql_retriever.fetch_all(query)

            equipment_list = []
            for row in results:
                equipment_list.append(
                    {
                        "asset_id": row["asset_id"],
                        "type": row["type"],
                        "model": row["model"],
                        "zone": row["zone"],
                        "status": row["status"],
                        "owner_user": row["owner_user"],
                        "next_pm_due": (
                            row["next_pm_due"].isoformat()
                            if row["next_pm_due"]
                            else None
                        ),
                        "last_maintenance": (
                            row["last_maintenance"].isoformat()
                            if row["last_maintenance"]
                            else None
                        ),
                        "created_at": row["created_at"].isoformat(),
                        "updated_at": row["updated_at"].isoformat(),
                        "metadata": row["metadata"] if row["metadata"] else {},
                    }
                )

            # Get summary statistics
            if where_conditions:
                summary_query = f"""
                    SELECT 
                        type,
                        status,
                        COUNT(*) as count
                    FROM equipment_assets 
                    WHERE {where_clause}
                    GROUP BY type, status
                    ORDER BY type, status
                """  # nosec B608 - Safe: using parameterized queries
            else:
                summary_query = """
                    SELECT 
                        type,
                        status,
                        COUNT(*) as count
                    FROM equipment_assets 
                    GROUP BY type, status
                    ORDER BY type, status
                """

            if params:
                summary_results = await self.sql_retriever.fetch_all(
                    summary_query, *params
                )
            else:
                summary_results = await self.sql_retriever.fetch_all(summary_query)
            summary = {}
            for row in summary_results:
                equipment_type = row["type"]
                status = row["status"]
                count = row["count"]

                if equipment_type not in summary:
                    summary[equipment_type] = {}
                summary[equipment_type][status] = count

            return {
                "equipment": equipment_list,
                "summary": summary,
                "total_count": len(equipment_list),
                "query_filters": {
                    "asset_id": asset_id,
                    "equipment_type": equipment_type,
                    "zone": zone,
                    "status": status,
                },
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error getting equipment status: {e}")
            return {
                "error": f"Failed to get equipment status: {str(e)}",
                "equipment": [],
                "summary": {},
                "total_count": 0,
            }

    async def assign_equipment(
        self,
        asset_id: str,
        assignee: str,
        assignment_type: str = "task",
        task_id: Optional[str] = None,
        duration_hours: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Assign equipment to a user, task, or zone.

        Args:
            asset_id: Equipment asset ID to assign
            assignee: User or system assigning the equipment
            assignment_type: Type of assignment (task, user, zone, maintenance)
            task_id: Optional task ID if assignment is task-related
            duration_hours: Optional duration in hours
            notes: Optional assignment notes

        Returns:
            Dictionary containing assignment result
        """
        logger.info(
            f"Assigning equipment {asset_id} to {assignee} for {assignment_type}"
        )

        try:
            # Check if equipment is available
            status_query = (
                "SELECT status, owner_user FROM equipment_assets WHERE asset_id = $1"
            )
            status_result = await self.sql_retriever.fetch_all(status_query, asset_id)

            if not status_result:
                return {
                    "success": False,
                    "error": f"Equipment {asset_id} not found",
                    "assignment_id": None,
                }

            current_status = status_result[0]["status"]
            current_owner = status_result[0]["owner_user"]

            if current_status != "available":
                return {
                    "success": False,
                    "error": f"Equipment {asset_id} is not available (current status: {current_status})",
                    "assignment_id": None,
                }

            # Create assignment
            assignment_query = """
                INSERT INTO equipment_assignments 
                (asset_id, task_id, assignee, assignment_type, notes)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
            """

            assignment_result = await self.sql_retriever.fetch_all(
                assignment_query, asset_id, task_id, assignee, assignment_type, notes
            )

            assignment_id = assignment_result[0]["id"] if assignment_result else None

            # Update equipment status
            update_query = """
                UPDATE equipment_assets 
                SET status = 'assigned', owner_user = $1, updated_at = now()
                WHERE asset_id = $2
            """

            await self.sql_retriever.execute_command(update_query, assignee, asset_id)

            return {
                "success": True,
                "assignment_id": assignment_id,
                "asset_id": asset_id,
                "assignee": assignee,
                "assignment_type": assignment_type,
                "assigned_at": datetime.now().isoformat(),
                "message": f"Equipment {asset_id} successfully assigned to {assignee}",
            }

        except Exception as e:
            logger.error(f"Error assigning equipment: {e}")
            return {
                "success": False,
                "error": f"Failed to assign equipment: {str(e)}",
                "assignment_id": None,
            }

    async def release_equipment(
        self, asset_id: str, released_by: str, notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Release equipment from current assignment.

        Args:
            asset_id: Equipment asset ID to release
            released_by: User releasing the equipment
            notes: Optional release notes

        Returns:
            Dictionary containing release result
        """
        logger.info(f"Releasing equipment {asset_id} by {released_by}")

        try:
            # Get current assignment
            assignment_query = """
                SELECT id, assignee, assignment_type 
                FROM equipment_assignments 
                WHERE asset_id = $1 AND released_at IS NULL
                ORDER BY assigned_at DESC
                LIMIT 1
            """

            assignment_result = await self.sql_retriever.fetch_all(
                assignment_query, asset_id
            )

            if not assignment_result:
                return {
                    "success": False,
                    "error": f"No active assignment found for equipment {asset_id}",
                    "assignment_id": None,
                }

            assignment_id, assignee, assignment_type = assignment_result[0]

            # Update assignment with release info
            release_query = """
                UPDATE equipment_assignments 
                SET released_at = now(), notes = COALESCE(notes || ' | ', '') || $1
                WHERE id = $2
            """

            release_notes = f"Released by {released_by}"
            if notes:
                release_notes += f": {notes}"

            await self.sql_retriever.execute_command(
                release_query, release_notes, assignment_id
            )

            # Update equipment status
            update_query = """
                UPDATE equipment_assets 
                SET status = 'available', owner_user = NULL, updated_at = now()
                WHERE asset_id = %s
            """

            await self.sql_retriever.execute_command(update_query, asset_id)

            return {
                "success": True,
                "assignment_id": assignment_id,
                "asset_id": asset_id,
                "released_by": released_by,
                "released_at": datetime.now().isoformat(),
                "message": f"Equipment {asset_id} successfully released from {assignee}",
            }

        except Exception as e:
            logger.error(f"Error releasing equipment: {e}")
            return {
                "success": False,
                "error": f"Failed to release equipment: {str(e)}",
                "assignment_id": None,
            }

    async def get_equipment_telemetry(
        self, asset_id: str, metric: Optional[str] = None, hours_back: int = 24
    ) -> Dict[str, Any]:
        """
        Get equipment telemetry data.

        Args:
            asset_id: Equipment asset ID
            metric: Specific metric to retrieve (optional)
            hours_back: Hours of historical data to retrieve

        Returns:
            Dictionary containing telemetry data
        """
        logger.info(
            f"Getting telemetry for equipment {asset_id}, metric: {metric}, hours_back: {hours_back}"
        )

        try:
            # Build query with PostgreSQL parameter style
            where_conditions = ["equipment_id = $1", "ts >= $2"]
            params = [asset_id, datetime.now() - timedelta(hours=hours_back)]
            param_count = 3

            if metric:
                where_conditions.append(f"metric = ${param_count}")
                params.append(metric)
                param_count += 1

            where_clause = " AND ".join(where_conditions)

            query = f"""
                SELECT ts, metric, value
                FROM equipment_telemetry 
                WHERE {where_clause}
                ORDER BY ts DESC
            """  # nosec B608 - Safe: using parameterized queries

            results = await self.sql_retriever.execute_query(query, tuple(params))

            telemetry_data = []
            for row in results:
                telemetry_data.append(
                    {
                        "timestamp": row["ts"].isoformat(),
                        "asset_id": asset_id,
                        "metric": row["metric"],
                        "value": row["value"],
                        "unit": "unknown",  # Default unit since column doesn't exist
                        "quality_score": 1.0,  # Default quality score since column doesn't exist
                    }
                )

            # Get available metrics
            metrics_query = """
                SELECT DISTINCT metric
                FROM equipment_telemetry 
                WHERE equipment_id = $1 AND ts >= $2
                ORDER BY metric
            """

            metrics_result = await self.sql_retriever.execute_query(
                metrics_query, (asset_id, datetime.now() - timedelta(hours=hours_back))
            )

            available_metrics = [
                {"metric": row["metric"], "unit": "unknown"} for row in metrics_result
            ]

            return {
                "asset_id": asset_id,
                "telemetry_data": telemetry_data,
                "available_metrics": available_metrics,
                "hours_back": hours_back,
                "data_points": len(telemetry_data),
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error getting equipment telemetry: {e}")
            return {
                "error": f"Failed to get telemetry data: {str(e)}",
                "asset_id": asset_id,
                "telemetry_data": [],
                "available_metrics": [],
            }

    async def schedule_maintenance(
        self,
        asset_id: str,
        maintenance_type: str,
        description: str,
        scheduled_by: str,
        scheduled_for: datetime,
        estimated_duration_minutes: int = 60,
        priority: str = "medium",
    ) -> Dict[str, Any]:
        """
        Schedule maintenance for equipment.

        Args:
            asset_id: Equipment asset ID
            maintenance_type: Type of maintenance (preventive, corrective, emergency, inspection)
            description: Maintenance description
            scheduled_by: User scheduling the maintenance
            scheduled_for: When maintenance should be performed
            estimated_duration_minutes: Estimated duration in minutes
            priority: Priority level (low, medium, high, critical)

        Returns:
            Dictionary containing maintenance scheduling result
        """
        logger.info(
            f"Scheduling {maintenance_type} maintenance for equipment {asset_id}"
        )

        try:
            # Check if equipment exists
            equipment_query = (
                "SELECT asset_id, type, model FROM equipment_assets WHERE asset_id = $1"
            )
            equipment_result = await self.sql_retriever.fetch_all(
                equipment_query, asset_id
            )

            if not equipment_result:
                return {
                    "success": False,
                    "error": f"Equipment {asset_id} not found",
                    "maintenance_id": None,
                }

            # Create maintenance record
            maintenance_query = """
                INSERT INTO equipment_maintenance 
                (asset_id, maintenance_type, description, performed_by, performed_at, 
                 duration_minutes, notes)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id
            """

            notes = f"Scheduled by {scheduled_by}, Priority: {priority}, Duration: {estimated_duration_minutes} minutes"

            maintenance_result = await self.sql_retriever.fetch_all(
                maintenance_query,
                asset_id,
                maintenance_type,
                description,
                scheduled_by,
                scheduled_for,
                estimated_duration_minutes,
                notes,
            )

            maintenance_id = maintenance_result[0][0] if maintenance_result else None

            # Update equipment status if it's emergency maintenance
            if maintenance_type == "emergency":
                update_query = """
                    UPDATE equipment_assets 
                    SET status = 'maintenance', updated_at = now()
                    WHERE asset_id = %s
                """
                await self.sql_retriever.execute_command(update_query, asset_id)

            return {
                "success": True,
                "maintenance_id": maintenance_id,
                "asset_id": asset_id,
                "maintenance_type": maintenance_type,
                "scheduled_for": scheduled_for.isoformat(),
                "scheduled_by": scheduled_by,
                "priority": priority,
                "message": f"Maintenance scheduled for equipment {asset_id}",
            }

        except Exception as e:
            logger.error(f"Error scheduling maintenance: {e}")
            return {
                "success": False,
                "error": f"Failed to schedule maintenance: {str(e)}",
                "maintenance_id": None,
            }

    async def get_maintenance_schedule(
        self,
        asset_id: Optional[str] = None,
        maintenance_type: Optional[str] = None,
        days_ahead: int = 30,
    ) -> Dict[str, Any]:
        """
        Get maintenance schedule for equipment.

        Args:
            asset_id: Specific equipment asset ID (optional)
            maintenance_type: Filter by maintenance type (optional)
            days_ahead: Days ahead to look for scheduled maintenance

        Returns:
            Dictionary containing maintenance schedule
        """
        logger.info(
            f"Getting maintenance schedule for asset_id: {asset_id}, type: {maintenance_type}"
        )

        try:
            # Build query with PostgreSQL parameter style - look for maintenance within the specified days ahead
            end_date = datetime.now() + timedelta(days=days_ahead)
            where_conditions = ["performed_at >= $1 AND performed_at <= $2"]
            params = [
                datetime.now() - timedelta(days=30),
                end_date,
            ]  # Look back 30 days and ahead
            param_count = 3

            if asset_id:
                where_conditions.append(f"asset_id = ${param_count}")
                params.append(asset_id)
                param_count += 1
            if maintenance_type:
                where_conditions.append(f"maintenance_type = ${param_count}")
                params.append(maintenance_type)
                param_count += 1

            where_clause = " AND ".join(where_conditions)

            query = f"""
                SELECT 
                    m.id, m.asset_id, e.type, e.model, e.zone,
                    m.maintenance_type, m.description, m.performed_by,
                    m.performed_at, m.duration_minutes, m.cost, m.notes
                FROM equipment_maintenance m
                JOIN equipment_assets e ON m.asset_id = e.asset_id
                WHERE {where_clause}
                ORDER BY m.performed_at ASC
            """  # nosec B608 - Safe: using parameterized queries

            results = await self.sql_retriever.execute_query(query, tuple(params))

            maintenance_schedule = []
            for row in results:
                maintenance_schedule.append(
                    {
                        "id": row["id"],
                        "asset_id": row["asset_id"],
                        "equipment_type": row["type"],
                        "model": row["model"],
                        "zone": row["zone"],
                        "maintenance_type": row["maintenance_type"],
                        "description": row["description"],
                        "performed_by": row["performed_by"],
                        "performed_at": (
                            row["performed_at"].isoformat()
                            if row["performed_at"]
                            else None
                        ),
                        "duration_minutes": row["duration_minutes"],
                        "cost": float(row["cost"]) if row["cost"] else None,
                        "notes": row["notes"],
                    }
                )

            return {
                "maintenance_schedule": maintenance_schedule,
                "total_scheduled": len(maintenance_schedule),
                "query_filters": {
                    "asset_id": asset_id,
                    "maintenance_type": maintenance_type,
                    "days_ahead": days_ahead,
                },
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error getting maintenance schedule: {e}")
            return {
                "error": f"Failed to get maintenance schedule: {str(e)}",
                "maintenance_schedule": [],
                "total_scheduled": 0,
            }

    async def get_equipment_utilization(
        self,
        asset_id: Optional[str] = None,
        equipment_type: Optional[str] = None,
        time_period: str = "day",
    ) -> Dict[str, Any]:
        """
        Get equipment utilization metrics and performance data.

        Args:
            asset_id: Specific equipment asset ID (optional)
            equipment_type: Type of equipment (optional)
            time_period: Time period for utilization data (day, week, month)

        Returns:
            Dictionary containing utilization metrics
        """
        logger.info(
            f"Getting equipment utilization for asset_id: {asset_id}, type: {equipment_type}, period: {time_period}"
        )

        try:
            # Calculate time range based on period
            now = datetime.now()
            if time_period == "day":
                start_time = now - timedelta(days=1)
            elif time_period == "week":
                start_time = now - timedelta(weeks=1)
            elif time_period == "month":
                start_time = now - timedelta(days=30)
            else:
                start_time = now - timedelta(days=1)

            # Build query conditions
            where_conditions = ["a.assigned_at >= $1 AND a.assigned_at <= $2"]
            params = [start_time, now]
            param_count = 3

            if asset_id:
                where_conditions.append(f"a.asset_id = ${param_count}")
                params.append(asset_id)
                param_count += 1

            if equipment_type:
                where_conditions.append(f"e.type = ${param_count}")
                params.append(equipment_type)
                param_count += 1

            where_clause = " AND ".join(where_conditions)

            # Get utilization data
            utilization_query = f"""
                SELECT 
                    a.asset_id,
                    e.type as equipment_type,
                    e.model,
                    e.zone,
                    COUNT(a.id) as total_assignments,
                    SUM(EXTRACT(EPOCH FROM (COALESCE(a.released_at, NOW()) - a.assigned_at))/3600) as total_hours_used,
                    AVG(EXTRACT(EPOCH FROM (COALESCE(a.released_at, NOW()) - a.assigned_at))/3600) as avg_hours_per_assignment,
                    MAX(a.assigned_at) as last_assigned,
                    MIN(a.assigned_at) as first_assigned
                FROM equipment_assignments a
                JOIN equipment_assets e ON a.asset_id = e.asset_id
                WHERE {where_clause}
                GROUP BY a.asset_id, e.type, e.model, e.zone
                ORDER BY total_hours_used DESC
            """  # nosec B608 - Safe: using parameterized queries

            results = await self.sql_retriever.execute_query(
                utilization_query, tuple(params)
            )

            utilization_data = []
            total_hours = 0
            total_assignments = 0

            for row in results:
                hours_used = (
                    float(row["total_hours_used"]) if row["total_hours_used"] else 0
                )
                total_hours += hours_used
                total_assignments += int(row["total_assignments"])

                # Calculate utilization percentage (assuming 8 hours per day as standard)
                max_possible_hours = 8 * (
                    1 if time_period == "day" else 7 if time_period == "week" else 30
                )
                utilization_percentage = (
                    min((hours_used / max_possible_hours) * 100, 100)
                    if max_possible_hours > 0
                    else 0
                )

                utilization_data.append(
                    {
                        "asset_id": row["asset_id"],
                        "equipment_type": row["equipment_type"],
                        "model": row["model"],
                        "zone": row["zone"],
                        "total_assignments": int(row["total_assignments"]),
                        "total_hours_used": round(hours_used, 2),
                        "avg_hours_per_assignment": round(
                            (
                                float(row["avg_hours_per_assignment"])
                                if row["avg_hours_per_assignment"]
                                else 0
                            ),
                            2,
                        ),
                        "utilization_percentage": round(utilization_percentage, 1),
                        "last_assigned": (
                            row["last_assigned"].isoformat()
                            if row["last_assigned"]
                            else None
                        ),
                        "first_assigned": (
                            row["first_assigned"].isoformat()
                            if row["first_assigned"]
                            else None
                        ),
                    }
                )

            # Calculate overall metrics
            avg_utilization = (
                sum(item["utilization_percentage"] for item in utilization_data)
                / len(utilization_data)
                if utilization_data
                else 0
            )

            return {
                "utilization_data": utilization_data,
                "summary": {
                    "total_equipment": len(utilization_data),
                    "total_hours_used": round(total_hours, 2),
                    "total_assignments": total_assignments,
                    "average_utilization_percentage": round(avg_utilization, 1),
                    "time_period": time_period,
                    "period_start": start_time.isoformat(),
                    "period_end": now.isoformat(),
                },
                "query_filters": {
                    "asset_id": asset_id,
                    "equipment_type": equipment_type,
                    "time_period": time_period,
                },
                "timestamp": now.isoformat(),
            }

        except Exception as e:
            logger.error(f"Error getting equipment utilization: {e}")
            return {
                "error": f"Failed to get equipment utilization: {str(e)}",
                "utilization_data": [],
                "summary": {
                    "total_equipment": 0,
                    "total_hours_used": 0,
                    "total_assignments": 0,
                    "average_utilization_percentage": 0,
                },
            }


# Global instance
_equipment_asset_tools: Optional[EquipmentAssetTools] = None


async def get_equipment_asset_tools() -> EquipmentAssetTools:
    """Get the global equipment asset tools instance."""
    global _equipment_asset_tools
    if _equipment_asset_tools is None:
        _equipment_asset_tools = EquipmentAssetTools()
        await _equipment_asset_tools.initialize()
    return _equipment_asset_tools
