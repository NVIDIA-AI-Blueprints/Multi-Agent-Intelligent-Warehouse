"""
IoT Integration API Router.

Provides REST API endpoints for IoT integration operations.
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import logging

from chain_server.services.iot.integration_service import iot_service
from adapters.iot.base import (
    SensorType,
    EquipmentStatus,
    SensorReading,
    Equipment,
    Alert,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/iot", tags=["IoT Integration"])


# Pydantic models for API requests/responses
class IoTConnectionConfig(BaseModel):
    iot_type: str = Field(
        ...,
        description="Type of IoT system (equipment_monitor, environmental, safety_sensors, asset_tracking)",
    )
    config: Dict[str, Any] = Field(..., description="IoT connection configuration")


class IoTConnectionResponse(BaseModel):
    connection_id: str
    iot_type: str
    connected: bool
    status: str


class SensorReadingsRequest(BaseModel):
    sensor_id: Optional[str] = None
    equipment_id: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class EquipmentStatusRequest(BaseModel):
    equipment_id: Optional[str] = None


class AlertsRequest(BaseModel):
    equipment_id: Optional[str] = None
    severity: Optional[str] = None
    resolved: Optional[bool] = None


class AlertAcknowledgeRequest(BaseModel):
    alert_id: str


@router.post("/connections/{connection_id}", response_model=IoTConnectionResponse)
async def add_iot_connection(
    connection_id: str, config: IoTConnectionConfig, background_tasks: BackgroundTasks
):
    """Add a new IoT connection."""
    try:
        success = await iot_service.add_iot_connection(
            config.iot_type, config.config, connection_id
        )

        if success:
            return IoTConnectionResponse(
                connection_id=connection_id,
                iot_type=config.iot_type,
                connected=True,
                status="connected",
            )
        else:
            raise HTTPException(
                status_code=400, detail="Failed to connect to IoT system"
            )

    except Exception as e:
        logger.error(f"Error adding IoT connection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/connections/{connection_id}")
async def remove_iot_connection(connection_id: str):
    """Remove an IoT connection."""
    try:
        success = await iot_service.remove_iot_connection(connection_id)
        if success:
            return {"message": f"IoT connection {connection_id} removed successfully"}
        else:
            raise HTTPException(status_code=404, detail="IoT connection not found")

    except Exception as e:
        logger.error(f"Error removing IoT connection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/connections")
async def list_iot_connections():
    """List all IoT connections."""
    try:
        connections = iot_service.list_connections()
        return {"connections": connections}

    except Exception as e:
        logger.error(f"Error listing IoT connections: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/connections/{connection_id}/status")
async def get_connection_status(connection_id: str):
    """Get IoT connection status."""
    try:
        status = await iot_service.get_connection_status(connection_id)
        return status

    except Exception as e:
        logger.error(f"Error getting connection status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/connections/status")
async def get_all_connection_status():
    """Get status of all IoT connections."""
    try:
        status = await iot_service.get_connection_status()
        return status

    except Exception as e:
        logger.error(f"Error getting all connection status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/connections/{connection_id}/sensor-readings")
async def get_sensor_readings(
    connection_id: str, request: SensorReadingsRequest = Depends()
):
    """Get sensor readings from a specific IoT connection."""
    try:
        readings = await iot_service.get_sensor_readings(
            connection_id,
            request.sensor_id,
            request.equipment_id,
            request.start_time,
            request.end_time,
        )

        return {
            "connection_id": connection_id,
            "readings": [
                {
                    "sensor_id": reading.sensor_id,
                    "sensor_type": reading.sensor_type.value,
                    "value": reading.value,
                    "unit": reading.unit,
                    "timestamp": reading.timestamp.isoformat(),
                    "location": reading.location,
                    "equipment_id": reading.equipment_id,
                    "quality": reading.quality,
                }
                for reading in readings
            ],
            "count": len(readings),
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting sensor readings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sensor-readings/aggregated")
async def get_aggregated_sensor_data(
    sensor_type: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
):
    """Get aggregated sensor data across all IoT connections."""
    try:
        sensor_type_enum = None
        if sensor_type:
            try:
                sensor_type_enum = SensorType(sensor_type.lower())
            except ValueError:
                raise HTTPException(
                    status_code=400, detail=f"Invalid sensor type: {sensor_type}"
                )

        aggregated = await iot_service.get_aggregated_sensor_data(
            sensor_type_enum, start_time, end_time
        )
        return aggregated

    except Exception as e:
        logger.error(f"Error getting aggregated sensor data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/connections/{connection_id}/equipment")
async def get_equipment_status(
    connection_id: str, request: EquipmentStatusRequest = Depends()
):
    """Get equipment status from a specific IoT connection."""
    try:
        equipment = await iot_service.get_equipment_status(
            connection_id, request.equipment_id
        )

        return {
            "connection_id": connection_id,
            "equipment": [
                {
                    "equipment_id": eq.equipment_id,
                    "name": eq.name,
                    "type": eq.type,
                    "location": eq.location,
                    "status": eq.status.value,
                    "last_seen": eq.last_seen.isoformat() if eq.last_seen else None,
                    "sensors": eq.sensors,
                    "metadata": eq.metadata,
                }
                for eq in equipment
            ],
            "count": len(equipment),
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting equipment status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/equipment/health-summary")
async def get_equipment_health_summary():
    """Get equipment health summary across all IoT connections."""
    try:
        summary = await iot_service.get_equipment_health_summary()
        return summary

    except Exception as e:
        logger.error(f"Error getting equipment health summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/connections/{connection_id}/alerts")
async def get_alerts(connection_id: str, request: AlertsRequest = Depends()):
    """Get alerts from a specific IoT connection."""
    try:
        alerts = await iot_service.get_alerts(
            connection_id, request.equipment_id, request.severity, request.resolved
        )

        return {
            "connection_id": connection_id,
            "alerts": [
                {
                    "alert_id": alert.alert_id,
                    "equipment_id": alert.equipment_id,
                    "sensor_id": alert.sensor_id,
                    "alert_type": alert.alert_type,
                    "severity": alert.severity,
                    "message": alert.message,
                    "value": alert.value,
                    "threshold": alert.threshold,
                    "timestamp": (
                        alert.timestamp.isoformat() if alert.timestamp else None
                    ),
                    "acknowledged": alert.acknowledged,
                    "resolved": alert.resolved,
                }
                for alert in alerts
            ],
            "count": len(alerts),
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts/all")
async def get_all_alerts(request: AlertsRequest = Depends()):
    """Get alerts from all IoT connections."""
    try:
        all_alerts = await iot_service.get_alerts_all(
            request.equipment_id, request.severity, request.resolved
        )

        return {
            "alerts_by_connection": all_alerts,
            "total_alerts": sum(len(alerts) for alerts in all_alerts.values()),
            "connections": list(all_alerts.keys()),
        }

    except Exception as e:
        logger.error(f"Error getting all alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/connections/{connection_id}/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(connection_id: str, alert_id: str):
    """Acknowledge an alert in a specific IoT connection."""
    try:
        success = await iot_service.acknowledge_alert(connection_id, alert_id)

        if success:
            return {
                "connection_id": connection_id,
                "alert_id": alert_id,
                "message": "Alert acknowledged successfully",
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to acknowledge alert")

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error acknowledging alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/monitoring/start")
async def start_real_time_monitoring():
    """Start real-time monitoring across all IoT connections."""
    try:
        # This would typically require a callback function
        # For now, we'll just return success
        return {
            "message": "Real-time monitoring started",
            "note": "Monitoring callbacks need to be configured separately",
        }

    except Exception as e:
        logger.error(f"Error starting real-time monitoring: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/monitoring/stop")
async def stop_real_time_monitoring():
    """Stop real-time monitoring across all IoT connections."""
    try:
        success = await iot_service.stop_real_time_monitoring()

        if success:
            return {"message": "Real-time monitoring stopped successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to stop monitoring")

    except Exception as e:
        logger.error(f"Error stopping real-time monitoring: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def iot_health_check():
    """Perform health check on all IoT connections."""
    try:
        status = await iot_service.get_connection_status()
        return {
            "status": (
                "healthy"
                if any(conn.get("connected", False) for conn in status.values())
                else "unhealthy"
            ),
            "connections": status,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error performing health check: {e}")
        raise HTTPException(status_code=500, detail=str(e))
