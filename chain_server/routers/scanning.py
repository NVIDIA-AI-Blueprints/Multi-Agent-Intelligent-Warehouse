"""
Scanning Integration API Router

This module provides REST API endpoints for RFID and barcode scanning devices.
"""

import logging
from typing import Dict, List, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from datetime import datetime

from chain_server.services.scanning.integration_service import scanning_service
from adapters.rfid_barcode.base import ScanResult, ScanType, ScanStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/scanning", tags=["Scanning Integration"])


# Pydantic models
class ScanningDeviceRequest(BaseModel):
    """Request model for creating scanning devices."""

    device_id: str = Field(..., description="Unique device identifier")
    device_type: str = Field(
        ..., description="Device type (zebra_rfid, honeywell_barcode, generic_scanner)"
    )
    connection_string: str = Field(..., description="Device connection string")
    timeout: int = Field(30, description="Request timeout in seconds")
    retry_count: int = Field(3, description="Number of retry attempts")
    scan_interval: float = Field(0.1, description="Scan interval in seconds")
    auto_connect: bool = Field(True, description="Auto-connect on startup")
    additional_params: Optional[Dict[str, Any]] = Field(
        None, description="Additional device parameters"
    )


class ScanResultModel(BaseModel):
    """Response model for scan results."""

    scan_id: str
    scan_type: str
    data: str
    status: str
    timestamp: datetime
    device_id: Optional[str] = None
    location: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class DeviceStatusModel(BaseModel):
    """Model for device status."""

    device_id: str
    connected: bool
    scanning: bool
    device_type: Optional[str] = None
    connection_string: Optional[str] = None
    error: Optional[str] = None


@router.get("/devices", response_model=Dict[str, DeviceStatusModel])
async def get_devices_status():
    """Get status of all scanning devices."""
    try:
        status = await scanning_service.get_all_devices_status()
        return {
            device_id: DeviceStatusModel(
                device_id=device_id,
                connected=info["connected"],
                scanning=info["scanning"],
                device_type=info.get("device_type"),
                connection_string=info.get("connection_string"),
                error=info.get("error"),
            )
            for device_id, info in status.items()
        }
    except Exception as e:
        logger.error(f"Failed to get devices status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/devices/{device_id}/status", response_model=DeviceStatusModel)
async def get_device_status(device_id: str):
    """Get status of specific scanning device."""
    try:
        status = await scanning_service.get_device_status(device_id)
        return DeviceStatusModel(
            device_id=device_id,
            connected=status["connected"],
            scanning=status["scanning"],
            device_type=status.get("device_type"),
            connection_string=status.get("connection_string"),
            error=status.get("error"),
        )
    except Exception as e:
        logger.error(f"Failed to get device status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/devices", response_model=Dict[str, str])
async def create_device(request: ScanningDeviceRequest):
    """Create a new scanning device."""
    try:
        from adapters.rfid_barcode.base import ScanningConfig

        config = ScanningConfig(
            device_type=request.device_type,
            connection_string=request.connection_string,
            timeout=request.timeout,
            retry_count=request.retry_count,
            scan_interval=request.scan_interval,
            auto_connect=request.auto_connect,
            additional_params=request.additional_params,
        )

        success = await scanning_service.add_device(request.device_id, config)

        if success:
            return {
                "message": f"Scanning device '{request.device_id}' created successfully"
            }
        else:
            raise HTTPException(
                status_code=400, detail="Failed to create scanning device"
            )

    except Exception as e:
        logger.error(f"Failed to create scanning device: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/devices/{device_id}", response_model=Dict[str, str])
async def delete_device(device_id: str):
    """Delete a scanning device."""
    try:
        success = await scanning_service.remove_device(device_id)

        if success:
            return {"message": f"Scanning device '{device_id}' deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Scanning device not found")

    except Exception as e:
        logger.error(f"Failed to delete scanning device: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/devices/{device_id}/connect", response_model=Dict[str, str])
async def connect_device(device_id: str):
    """Connect to a scanning device."""
    try:
        success = await scanning_service.connect_device(device_id)

        if success:
            return {"message": f"Connected to scanning device '{device_id}'"}
        else:
            raise HTTPException(
                status_code=400, detail="Failed to connect to scanning device"
            )

    except Exception as e:
        logger.error(f"Failed to connect to scanning device: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/devices/{device_id}/disconnect", response_model=Dict[str, str])
async def disconnect_device(device_id: str):
    """Disconnect from a scanning device."""
    try:
        success = await scanning_service.disconnect_device(device_id)

        if success:
            return {"message": f"Disconnected from scanning device '{device_id}'"}
        else:
            raise HTTPException(
                status_code=400, detail="Failed to disconnect from scanning device"
            )

    except Exception as e:
        logger.error(f"Failed to disconnect from scanning device: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/devices/{device_id}/start-scanning", response_model=Dict[str, str])
async def start_scanning(device_id: str):
    """Start continuous scanning on a device."""
    try:
        success = await scanning_service.start_scanning(device_id)

        if success:
            return {"message": f"Started scanning on device '{device_id}'"}
        else:
            raise HTTPException(status_code=400, detail="Failed to start scanning")

    except Exception as e:
        logger.error(f"Failed to start scanning: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/devices/{device_id}/stop-scanning", response_model=Dict[str, str])
async def stop_scanning(device_id: str):
    """Stop continuous scanning on a device."""
    try:
        success = await scanning_service.stop_scanning(device_id)

        if success:
            return {"message": f"Stopped scanning on device '{device_id}'"}
        else:
            raise HTTPException(status_code=400, detail="Failed to stop scanning")

    except Exception as e:
        logger.error(f"Failed to stop scanning: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/devices/{device_id}/single-scan", response_model=ScanResultModel)
async def single_scan(
    device_id: str,
    timeout: Optional[int] = Query(None, description="Scan timeout in seconds"),
):
    """Perform a single scan on a device."""
    try:
        result = await scanning_service.single_scan(device_id, timeout)

        if result:
            return ScanResultModel(
                scan_id=result.scan_id,
                scan_type=result.scan_type.value,
                data=result.data,
                status=result.status.value,
                timestamp=result.timestamp,
                device_id=result.device_id,
                location=result.location,
                metadata=result.metadata,
                error=result.error,
            )
        else:
            raise HTTPException(status_code=400, detail="Failed to perform scan")

    except Exception as e:
        logger.error(f"Failed to perform single scan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/devices/{device_id}/info", response_model=Dict[str, Any])
async def get_device_info(device_id: str):
    """Get device information."""
    try:
        info = await scanning_service.get_device_info(device_id)
        return info
    except Exception as e:
        logger.error(f"Failed to get device info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=Dict[str, Any])
async def health_check():
    """Health check for scanning integration service."""
    try:
        await scanning_service.initialize()
        devices_status = await scanning_service.get_all_devices_status()

        total_devices = len(devices_status)
        connected_devices = sum(
            1 for status in devices_status.values() if status["connected"]
        )
        scanning_devices = sum(
            1 for status in devices_status.values() if status["scanning"]
        )

        return {
            "status": "healthy",
            "total_devices": total_devices,
            "connected_devices": connected_devices,
            "scanning_devices": scanning_devices,
            "devices": devices_status,
        }
    except Exception as e:
        logger.error(f"Scanning health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}
