"""
WMS Integration API Router.

Provides REST API endpoints for WMS integration operations.
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
import logging

from chain_server.services.wms.integration_service import wms_service
from adapters.wms.base import TaskStatus, TaskType, InventoryItem, Task, Order, Location

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/wms", tags=["WMS Integration"])


# Pydantic models for API requests/responses
class WMSConnectionConfig(BaseModel):
    wms_type: str = Field(
        ..., description="Type of WMS system (sap_ewm, manhattan, oracle)"
    )
    config: Dict[str, Any] = Field(..., description="WMS connection configuration")


class WMSConnectionResponse(BaseModel):
    connection_id: str
    wms_type: str
    connected: bool
    status: str


class InventoryRequest(BaseModel):
    location: Optional[str] = None
    sku: Optional[str] = None


class TaskRequest(BaseModel):
    task_type: str
    priority: int = 1
    assigned_to: Optional[str] = None
    location: Optional[str] = None
    destination: Optional[str] = None
    notes: Optional[str] = None


class TaskStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None


class OrderRequest(BaseModel):
    order_type: str
    priority: int = 1
    customer_id: Optional[str] = None
    items: Optional[List[Dict[str, Any]]] = None
    required_date: Optional[datetime] = None


class SyncRequest(BaseModel):
    source_connection_id: str
    target_connection_id: str
    location: Optional[str] = None


@router.post("/connections", response_model=WMSConnectionResponse)
async def add_wms_connection(
    connection_id: str, config: WMSConnectionConfig, background_tasks: BackgroundTasks
):
    """Add a new WMS connection."""
    try:
        success = await wms_service.add_wms_connection(
            config.wms_type, config.config, connection_id
        )

        if success:
            return WMSConnectionResponse(
                connection_id=connection_id,
                wms_type=config.wms_type,
                connected=True,
                status="connected",
            )
        else:
            raise HTTPException(status_code=400, detail="Failed to connect to WMS")

    except Exception as e:
        logger.error(f"Error adding WMS connection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/connections/{connection_id}")
async def remove_wms_connection(connection_id: str):
    """Remove a WMS connection."""
    try:
        success = await wms_service.remove_wms_connection(connection_id)
        if success:
            return {"message": f"WMS connection {connection_id} removed successfully"}
        else:
            raise HTTPException(status_code=404, detail="WMS connection not found")

    except Exception as e:
        logger.error(f"Error removing WMS connection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/connections")
async def list_wms_connections():
    """List all WMS connections."""
    try:
        connections = wms_service.list_connections()
        return {"connections": connections}

    except Exception as e:
        logger.error(f"Error listing WMS connections: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/connections/{connection_id}/status")
async def get_connection_status(connection_id: str):
    """Get WMS connection status."""
    try:
        status = await wms_service.get_connection_status(connection_id)
        return status

    except Exception as e:
        logger.error(f"Error getting connection status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/connections/status")
async def get_all_connection_status():
    """Get status of all WMS connections."""
    try:
        status = await wms_service.get_connection_status()
        return status

    except Exception as e:
        logger.error(f"Error getting all connection status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/connections/{connection_id}/inventory")
async def get_inventory(connection_id: str, request: InventoryRequest = Depends()):
    """Get inventory from a specific WMS connection."""
    try:
        inventory = await wms_service.get_inventory(
            connection_id, request.location, request.sku
        )

        return {
            "connection_id": connection_id,
            "inventory": [
                {
                    "sku": item.sku,
                    "name": item.name,
                    "quantity": item.quantity,
                    "available_quantity": item.available_quantity,
                    "reserved_quantity": item.reserved_quantity,
                    "location": item.location,
                    "zone": item.zone,
                    "status": item.status,
                }
                for item in inventory
            ],
            "count": len(inventory),
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting inventory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inventory/aggregated")
async def get_aggregated_inventory(request: InventoryRequest = Depends()):
    """Get aggregated inventory across all WMS connections."""
    try:
        aggregated = await wms_service.get_aggregated_inventory(
            request.location, request.sku
        )
        return aggregated

    except Exception as e:
        logger.error(f"Error getting aggregated inventory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/connections/{connection_id}/tasks")
async def get_tasks(
    connection_id: str, status: Optional[str] = None, assigned_to: Optional[str] = None
):
    """Get tasks from a specific WMS connection."""
    try:
        task_status = None
        if status:
            try:
                task_status = TaskStatus(status.lower())
            except ValueError:
                raise HTTPException(
                    status_code=400, detail=f"Invalid task status: {status}"
                )

        tasks = await wms_service.get_tasks(connection_id, task_status, assigned_to)

        return {
            "connection_id": connection_id,
            "tasks": [
                {
                    "task_id": task.task_id,
                    "task_type": task.task_type.value,
                    "priority": task.priority,
                    "status": task.status.value,
                    "assigned_to": task.assigned_to,
                    "location": task.location,
                    "destination": task.destination,
                    "created_at": (
                        task.created_at.isoformat() if task.created_at else None
                    ),
                    "notes": task.notes,
                }
                for task in tasks
            ],
            "count": len(tasks),
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/connections/{connection_id}/tasks")
async def create_task(connection_id: str, request: TaskRequest):
    """Create a new task in a specific WMS connection."""
    try:
        # Map task type string to enum
        try:
            task_type = TaskType(request.task_type.lower())
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid task type: {request.task_type}"
            )

        task = Task(
            task_id="",  # Will be generated by WMS
            task_type=task_type,
            priority=request.priority,
            assigned_to=request.assigned_to,
            location=request.location,
            destination=request.destination,
            notes=request.notes,
            created_at=datetime.now(),
        )

        task_id = await wms_service.create_task(connection_id, task)

        return {
            "connection_id": connection_id,
            "task_id": task_id,
            "message": "Task created successfully",
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/connections/{connection_id}/tasks/{task_id}")
async def update_task_status(
    connection_id: str, task_id: str, request: TaskStatusUpdate
):
    """Update task status in a specific WMS connection."""
    try:
        # Map status string to enum
        try:
            status = TaskStatus(request.status.lower())
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid task status: {request.status}"
            )

        success = await wms_service.update_task_status(
            connection_id, task_id, status, request.notes
        )

        if success:
            return {
                "connection_id": connection_id,
                "task_id": task_id,
                "status": request.status,
                "message": "Task status updated successfully",
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to update task status")

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating task status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/connections/{connection_id}/orders")
async def get_orders(
    connection_id: str, status: Optional[str] = None, order_type: Optional[str] = None
):
    """Get orders from a specific WMS connection."""
    try:
        orders = await wms_service.get_orders(connection_id, status, order_type)

        return {
            "connection_id": connection_id,
            "orders": [
                {
                    "order_id": order.order_id,
                    "order_type": order.order_type,
                    "status": order.status,
                    "priority": order.priority,
                    "customer_id": order.customer_id,
                    "created_at": (
                        order.created_at.isoformat() if order.created_at else None
                    ),
                    "required_date": (
                        order.required_date.isoformat() if order.required_date else None
                    ),
                }
                for order in orders
            ],
            "count": len(orders),
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/connections/{connection_id}/orders")
async def create_order(connection_id: str, request: OrderRequest):
    """Create a new order in a specific WMS connection."""
    try:
        order = Order(
            order_id="",  # Will be generated by WMS
            order_type=request.order_type,
            priority=request.priority,
            customer_id=request.customer_id,
            items=request.items,
            required_date=request.required_date,
            created_at=datetime.now(),
        )

        order_id = await wms_service.create_order(connection_id, order)

        return {
            "connection_id": connection_id,
            "order_id": order_id,
            "message": "Order created successfully",
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating order: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/connections/{connection_id}/locations")
async def get_locations(
    connection_id: str, zone: Optional[str] = None, location_type: Optional[str] = None
):
    """Get locations from a specific WMS connection."""
    try:
        locations = await wms_service.get_locations(connection_id, zone, location_type)

        return {
            "connection_id": connection_id,
            "locations": [
                {
                    "location_id": loc.location_id,
                    "name": loc.name,
                    "zone": loc.zone,
                    "aisle": loc.aisle,
                    "rack": loc.rack,
                    "level": loc.level,
                    "position": loc.position,
                    "location_type": loc.location_type,
                    "capacity": loc.capacity,
                    "current_utilization": loc.current_utilization,
                    "status": loc.status,
                }
                for loc in locations
            ],
            "count": len(locations),
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting locations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/inventory")
async def sync_inventory(request: SyncRequest):
    """Synchronize inventory between two WMS connections."""
    try:
        result = await wms_service.sync_inventory(
            request.source_connection_id, request.target_connection_id, request.location
        )

        return result

    except Exception as e:
        logger.error(f"Error syncing inventory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def wms_health_check():
    """Perform health check on all WMS connections."""
    try:
        status = await wms_service.get_connection_status()
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
