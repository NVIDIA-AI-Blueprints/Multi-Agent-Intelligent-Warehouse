"""
Time Attendance API Router

This module provides REST API endpoints for time attendance systems.
"""

import logging
from typing import Dict, List, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from datetime import datetime, date

from chain_server.services.attendance.integration_service import attendance_service
from adapters.time_attendance.base import (
    AttendanceRecord,
    BiometricData,
    AttendanceType,
    AttendanceStatus,
    BiometricType,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/attendance", tags=["Time Attendance"])


# Pydantic models
class AttendanceSystemRequest(BaseModel):
    """Request model for creating attendance systems."""

    system_id: str = Field(..., description="Unique system identifier")
    device_type: str = Field(
        ..., description="System type (biometric_system, card_reader, mobile_app)"
    )
    connection_string: str = Field(..., description="System connection string")
    timeout: int = Field(30, description="Request timeout in seconds")
    sync_interval: int = Field(300, description="Sync interval in seconds")
    auto_connect: bool = Field(True, description="Auto-connect on startup")
    additional_params: Optional[Dict[str, Any]] = Field(
        None, description="Additional system parameters"
    )


class AttendanceRecordModel(BaseModel):
    """Model for attendance records."""

    record_id: str
    employee_id: str
    attendance_type: str
    timestamp: datetime
    location: Optional[str] = None
    device_id: Optional[str] = None
    status: str
    notes: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class BiometricDataModel(BaseModel):
    """Model for biometric data."""

    employee_id: str
    biometric_type: str
    template_data: str
    quality_score: Optional[float] = None
    created_at: datetime
    metadata: Optional[Dict[str, Any]] = None


class SystemStatusModel(BaseModel):
    """Model for system status."""

    system_id: str
    connected: bool
    syncing: bool
    device_type: Optional[str] = None
    connection_string: Optional[str] = None
    error: Optional[str] = None


@router.get("/systems", response_model=Dict[str, SystemStatusModel])
async def get_systems_status():
    """Get status of all attendance systems."""
    try:
        status = await attendance_service.get_all_systems_status()
        return {
            system_id: SystemStatusModel(
                system_id=system_id,
                connected=info["connected"],
                syncing=info["syncing"],
                device_type=info.get("device_type"),
                connection_string=info.get("connection_string"),
                error=info.get("error"),
            )
            for system_id, info in status.items()
        }
    except Exception as e:
        logger.error(f"Failed to get systems status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/systems/{system_id}/status", response_model=SystemStatusModel)
async def get_system_status(system_id: str):
    """Get status of specific attendance system."""
    try:
        status = await attendance_service.get_system_status(system_id)
        return SystemStatusModel(
            system_id=system_id,
            connected=status["connected"],
            syncing=status["syncing"],
            device_type=status.get("device_type"),
            connection_string=status.get("connection_string"),
            error=status.get("error"),
        )
    except Exception as e:
        logger.error(f"Failed to get system status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/systems", response_model=Dict[str, str])
async def create_system(request: AttendanceSystemRequest):
    """Create a new attendance system."""
    try:
        from adapters.time_attendance.base import AttendanceConfig

        config = AttendanceConfig(
            device_type=request.device_type,
            connection_string=request.connection_string,
            timeout=request.timeout,
            sync_interval=request.sync_interval,
            auto_connect=request.auto_connect,
            additional_params=request.additional_params,
        )

        success = await attendance_service.add_system(request.system_id, config)

        if success:
            return {
                "message": f"Attendance system '{request.system_id}' created successfully"
            }
        else:
            raise HTTPException(
                status_code=400, detail="Failed to create attendance system"
            )

    except Exception as e:
        logger.error(f"Failed to create attendance system: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/systems/{system_id}", response_model=Dict[str, str])
async def delete_system(system_id: str):
    """Delete an attendance system."""
    try:
        success = await attendance_service.remove_system(system_id)

        if success:
            return {"message": f"Attendance system '{system_id}' deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Attendance system not found")

    except Exception as e:
        logger.error(f"Failed to delete attendance system: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/systems/{system_id}/records", response_model=List[AttendanceRecordModel])
async def get_attendance_records(
    system_id: str,
    employee_id: Optional[str] = Query(None, description="Employee ID filter"),
    start_date: Optional[date] = Query(None, description="Start date filter"),
    end_date: Optional[date] = Query(None, description="End date filter"),
):
    """Get attendance records from specified system."""
    try:
        records = await attendance_service.get_attendance_records(
            system_id, employee_id, start_date, end_date
        )

        return [
            AttendanceRecordModel(
                record_id=record.record_id,
                employee_id=record.employee_id,
                attendance_type=record.attendance_type.value,
                timestamp=record.timestamp,
                location=record.location,
                device_id=record.device_id,
                status=record.status.value,
                notes=record.notes,
                metadata=record.metadata,
            )
            for record in records
        ]
    except Exception as e:
        logger.error(f"Failed to get attendance records: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/systems/{system_id}/records", response_model=Dict[str, str])
async def create_attendance_record(system_id: str, record: AttendanceRecordModel):
    """Create a new attendance record."""
    try:
        attendance_record = AttendanceRecord(
            record_id=record.record_id,
            employee_id=record.employee_id,
            attendance_type=AttendanceType(record.attendance_type),
            timestamp=record.timestamp,
            location=record.location,
            device_id=record.device_id,
            status=AttendanceStatus(record.status),
            notes=record.notes,
            metadata=record.metadata,
        )

        success = await attendance_service.create_attendance_record(
            system_id, attendance_record
        )

        if success:
            return {"message": "Attendance record created successfully"}
        else:
            raise HTTPException(
                status_code=400, detail="Failed to create attendance record"
            )

    except Exception as e:
        logger.error(f"Failed to create attendance record: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/systems/{system_id}/records/{record_id}", response_model=Dict[str, str])
async def update_attendance_record(
    system_id: str, record_id: str, record: AttendanceRecordModel
):
    """Update an existing attendance record."""
    try:
        attendance_record = AttendanceRecord(
            record_id=record.record_id,
            employee_id=record.employee_id,
            attendance_type=AttendanceType(record.attendance_type),
            timestamp=record.timestamp,
            location=record.location,
            device_id=record.device_id,
            status=AttendanceStatus(record.status),
            notes=record.notes,
            metadata=record.metadata,
        )

        success = await attendance_service.update_attendance_record(
            system_id, attendance_record
        )

        if success:
            return {"message": "Attendance record updated successfully"}
        else:
            raise HTTPException(
                status_code=400, detail="Failed to update attendance record"
            )

    except Exception as e:
        logger.error(f"Failed to update attendance record: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/systems/{system_id}/records/{record_id}", response_model=Dict[str, str]
)
async def delete_attendance_record(system_id: str, record_id: str):
    """Delete an attendance record."""
    try:
        success = await attendance_service.delete_attendance_record(
            system_id, record_id
        )

        if success:
            return {"message": "Attendance record deleted successfully"}
        else:
            raise HTTPException(
                status_code=400, detail="Failed to delete attendance record"
            )

    except Exception as e:
        logger.error(f"Failed to delete attendance record: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/systems/{system_id}/employees/{employee_id}/summary",
    response_model=Dict[str, Any],
)
async def get_employee_attendance(
    system_id: str,
    employee_id: str,
    date: date = Query(..., description="Date for attendance summary"),
):
    """Get employee attendance summary for a specific date."""
    try:
        summary = await attendance_service.get_employee_attendance(
            system_id, employee_id, date
        )
        return summary
    except Exception as e:
        logger.error(f"Failed to get employee attendance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/systems/{system_id}/biometric", response_model=List[BiometricDataModel])
async def get_biometric_data(
    system_id: str,
    employee_id: Optional[str] = Query(None, description="Employee ID filter"),
):
    """Get biometric data from specified system."""
    try:
        biometric_data = await attendance_service.get_biometric_data(
            system_id, employee_id
        )

        return [
            BiometricDataModel(
                employee_id=bio.employee_id,
                biometric_type=bio.biometric_type.value,
                template_data=bio.template_data,
                quality_score=bio.quality_score,
                created_at=bio.created_at,
                metadata=bio.metadata,
            )
            for bio in biometric_data
        ]
    except Exception as e:
        logger.error(f"Failed to get biometric data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/systems/{system_id}/biometric/enroll", response_model=Dict[str, str])
async def enroll_biometric_data(system_id: str, biometric_data: BiometricDataModel):
    """Enroll new biometric data for an employee."""
    try:
        bio_data = BiometricData(
            employee_id=biometric_data.employee_id,
            biometric_type=BiometricType(biometric_data.biometric_type),
            template_data=biometric_data.template_data,
            quality_score=biometric_data.quality_score,
            created_at=biometric_data.created_at,
            metadata=biometric_data.metadata,
        )

        success = await attendance_service.enroll_biometric_data(system_id, bio_data)

        if success:
            return {"message": "Biometric data enrolled successfully"}
        else:
            raise HTTPException(
                status_code=400, detail="Failed to enroll biometric data"
            )

    except Exception as e:
        logger.error(f"Failed to enroll biometric data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/systems/{system_id}/biometric/verify", response_model=Dict[str, Any])
async def verify_biometric(
    system_id: str,
    biometric_type: str = Query(..., description="Biometric type"),
    template_data: str = Query(..., description="Template data to verify"),
):
    """Verify biometric data and return employee ID if match found."""
    try:
        employee_id = await attendance_service.verify_biometric(
            system_id, biometric_type, template_data
        )

        return {
            "success": employee_id is not None,
            "employee_id": employee_id,
            "message": (
                "Biometric verification successful" if employee_id else "No match found"
            ),
        }
    except Exception as e:
        logger.error(f"Failed to verify biometric: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=Dict[str, Any])
async def health_check():
    """Health check for attendance integration service."""
    try:
        await attendance_service.initialize()
        systems_status = await attendance_service.get_all_systems_status()

        total_systems = len(systems_status)
        connected_systems = sum(
            1 for status in systems_status.values() if status["connected"]
        )
        syncing_systems = sum(
            1 for status in systems_status.values() if status["syncing"]
        )

        return {
            "status": "healthy",
            "total_systems": total_systems,
            "connected_systems": connected_systems,
            "syncing_systems": syncing_systems,
            "systems": systems_status,
        }
    except Exception as e:
        logger.error(f"Attendance health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}
