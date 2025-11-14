"""
Manhattan Associates WMS Adapter.

Provides integration with Manhattan Associates WMS system using
REST API and web services for warehouse operations.
"""
import asyncio
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
import httpx
import logging
from .base import (
    BaseWMSAdapter, InventoryItem, Task, Order, Location,
    TaskStatus, TaskType, WMSConnectionError, WMSDataError
)

logger = logging.getLogger(__name__)

class ManhattanAdapter(BaseWMSAdapter):
    """
    Manhattan Associates WMS Adapter for warehouse operations.
    
    Supports REST API and web service connections to Manhattan WMS.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Manhattan WMS adapter.
        
        Args:
            config: Configuration containing:
                - host: Manhattan WMS host
                - port: Manhattan WMS port (default: 8080)
                - username: Manhattan username
                - password: Manhattan password
                - facility_id: Manhattan facility ID
                - client_id: Manhattan client ID
                - use_ssl: Whether to use SSL (default: True)
        """
        super().__init__(config)
        self.host = config.get('host')
        self.port = config.get('port', 8080)
        self.username = config.get('username')
        self.password = config.get('password')
        self.facility_id = config.get('facility_id')
        self.client_id = config.get('client_id')
        self.use_ssl = config.get('use_ssl', True)
        
        protocol = "https" if self.use_ssl else "http"
        self.base_url = f"{protocol}://{self.host}:{self.port}/wms"
        self.session: Optional[httpx.AsyncClient] = None
        self.auth_token: Optional[str] = None
        
        # Manhattan WMS API endpoints
        self.endpoints = {
            'auth': '/auth/login',
            'inventory': '/api/v1/inventory',
            'tasks': '/api/v1/tasks',
            'orders': '/api/v1/orders',
            'locations': '/api/v1/locations',
            'warehouses': '/api/v1/warehouses'
        }
    
    async def connect(self) -> bool:
        """Establish connection to Manhattan WMS."""
        try:
            if not self._validate_config(['host', 'username', 'password', 'facility_id']):
                return False
            
            return await self._authenticate()
                
        except Exception as e:
            self.logger.error(f"Failed to connect to Manhattan WMS: {e}")
            raise WMSConnectionError(f"Manhattan WMS connection failed: {e}")
    
    async def _authenticate(self) -> bool:
        """Authenticate with Manhattan WMS."""
        try:
            self.session = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0,
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                }
            )
            
            # Authenticate and get token
            auth_data = {
                "username": self.username,
                "password": self.password,
                "facilityId": self.facility_id,
                "clientId": self.client_id
            }
            
            response = await self.session.post(self.endpoints['auth'], json=auth_data)
            response.raise_for_status()
            
            auth_result = response.json()
            self.auth_token = auth_result.get('token')
            
            if self.auth_token:
                # Update session headers with auth token
                self.session.headers.update({
                    'Authorization': f'Bearer {self.auth_token}'
                })
                
                self.connected = True
                self.logger.info("Successfully connected to Manhattan WMS")
                return True
            else:
                self.logger.error("Failed to get authentication token")
                return False
                
        except Exception as e:
            self.logger.error(f"Manhattan WMS authentication failed: {e}")
            return False
    
    async def disconnect(self) -> bool:
        """Disconnect from Manhattan WMS."""
        try:
            if self.session and self.auth_token:
                # Logout from Manhattan WMS
                await self.session.post('/auth/logout')
            
            if self.session:
                await self.session.aclose()
                self.session = None
            
            self.auth_token = None
            self.connected = False
            self.logger.info("Disconnected from Manhattan WMS")
            return True
        except Exception as e:
            self.logger.error(f"Error disconnecting from Manhattan WMS: {e}")
            return False
    
    async def get_inventory(self, location: Optional[str] = None, 
                          sku: Optional[str] = None) -> List[InventoryItem]:
        """Retrieve inventory from Manhattan WMS."""
        try:
            if not self.connected:
                raise WMSConnectionError("Not connected to Manhattan WMS")
            
            # Build query parameters
            params = {"facilityId": self.facility_id}
            if location:
                params["location"] = location
            if sku:
                params["sku"] = sku
            
            response = await self.session.get(self.endpoints['inventory'], params=params)
            response.raise_for_status()
            
            data = response.json()
            items = []
            
            for item_data in data.get('inventory', []):
                item = InventoryItem(
                    sku=item_data.get('sku', ''),
                    name=item_data.get('description', ''),
                    description=item_data.get('longDescription', ''),
                    quantity=int(item_data.get('quantityOnHand', 0)),
                    available_quantity=int(item_data.get('quantityAvailable', 0)),
                    reserved_quantity=int(item_data.get('quantityReserved', 0)),
                    location=item_data.get('location', ''),
                    zone=item_data.get('zone', ''),
                    lot_number=item_data.get('lotNumber', ''),
                    serial_number=item_data.get('serialNumber', ''),
                    expiry_date=self._parse_manhattan_datetime(item_data.get('expiryDate')),
                    status=item_data.get('status', 'active'),
                    last_updated=self._parse_manhattan_datetime(item_data.get('lastUpdated'))
                )
                items.append(item)
            
            self._log_operation("get_inventory", {"count": len(items)})
            return items
            
        except Exception as e:
            self.logger.error(f"Failed to get inventory from Manhattan WMS: {e}")
            raise WMSDataError(f"Inventory retrieval failed: {e}")
    
    async def update_inventory(self, items: List[InventoryItem]) -> bool:
        """Update inventory in Manhattan WMS."""
        try:
            if not self.connected:
                raise WMSConnectionError("Not connected to Manhattan WMS")
            
            for item in items:
                # Create inventory adjustment
                adjustment_data = {
                    "facilityId": self.facility_id,
                    "sku": item.sku,
                    "location": item.location,
                    "quantity": item.quantity,
                    "adjustmentType": "MANUAL",
                    "reasonCode": "SYSTEM_ADJUSTMENT"
                }
                
                response = await self.session.post(
                    f"{self.endpoints['inventory']}/adjustments",
                    json=adjustment_data
                )
                response.raise_for_status()
            
            self._log_operation("update_inventory", {"count": len(items)})
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update inventory in Manhattan WMS: {e}")
            raise WMSDataError(f"Inventory update failed: {e}")
    
    async def get_tasks(self, status: Optional[TaskStatus] = None,
                       assigned_to: Optional[str] = None) -> List[Task]:
        """Retrieve tasks from Manhattan WMS."""
        try:
            if not self.connected:
                raise WMSConnectionError("Not connected to Manhattan WMS")
            
            # Build query parameters
            params = {"facilityId": self.facility_id}
            if status:
                params["status"] = self._map_task_status_to_manhattan(status)
            if assigned_to:
                params["assignedTo"] = assigned_to
            
            response = await self.session.get(self.endpoints['tasks'], params=params)
            response.raise_for_status()
            
            data = response.json()
            tasks = []
            
            for task_data in data.get('tasks', []):
                task = Task(
                    task_id=task_data.get('taskId', ''),
                    task_type=self._map_manhattan_task_type(task_data.get('taskType', '')),
                    priority=int(task_data.get('priority', 1)),
                    status=self._map_manhattan_task_status(task_data.get('status', '')),
                    assigned_to=task_data.get('assignedTo', ''),
                    location=task_data.get('sourceLocation', ''),
                    destination=task_data.get('destinationLocation', ''),
                    created_at=self._parse_manhattan_datetime(task_data.get('createdDate')),
                    started_at=self._parse_manhattan_datetime(task_data.get('startedDate')),
                    completed_at=self._parse_manhattan_datetime(task_data.get('completedDate')),
                    notes=task_data.get('notes', '')
                )
                tasks.append(task)
            
            self._log_operation("get_tasks", {"count": len(tasks)})
            return tasks
            
        except Exception as e:
            self.logger.error(f"Failed to get tasks from Manhattan WMS: {e}")
            raise WMSDataError(f"Task retrieval failed: {e}")
    
    async def create_task(self, task: Task) -> str:
        """Create a new task in Manhattan WMS."""
        try:
            if not self.connected:
                raise WMSConnectionError("Not connected to Manhattan WMS")
            
            task_data = {
                "facilityId": self.facility_id,
                "taskType": self._map_task_type_to_manhattan(task.task_type),
                "priority": task.priority,
                "sourceLocation": task.location,
                "destinationLocation": task.destination,
                "assignedTo": task.assigned_to,
                "notes": task.notes
            }
            
            response = await self.session.post(self.endpoints['tasks'], json=task_data)
            response.raise_for_status()
            
            result = response.json()
            task_id = result.get('taskId', '')
            
            self._log_operation("create_task", {"task_id": task_id})
            return task_id
            
        except Exception as e:
            self.logger.error(f"Failed to create task in Manhattan WMS: {e}")
            raise WMSDataError(f"Task creation failed: {e}")
    
    async def update_task_status(self, task_id: str, status: TaskStatus,
                                notes: Optional[str] = None) -> bool:
        """Update task status in Manhattan WMS."""
        try:
            if not self.connected:
                raise WMSConnectionError("Not connected to Manhattan WMS")
            
            update_data = {
                "status": self._map_task_status_to_manhattan(status)
            }
            
            if notes:
                update_data["notes"] = notes
            
            response = await self.session.patch(
                f"{self.endpoints['tasks']}/{task_id}",
                json=update_data
            )
            response.raise_for_status()
            
            self._log_operation("update_task_status", {"task_id": task_id, "status": status.value})
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update task status in Manhattan WMS: {e}")
            raise WMSDataError(f"Task status update failed: {e}")
    
    async def get_orders(self, status: Optional[str] = None,
                        order_type: Optional[str] = None) -> List[Order]:
        """Retrieve orders from Manhattan WMS."""
        try:
            if not self.connected:
                raise WMSConnectionError("Not connected to Manhattan WMS")
            
            # Build query parameters
            params = {"facilityId": self.facility_id}
            if status:
                params["status"] = status
            if order_type:
                params["orderType"] = order_type
            
            response = await self.session.get(self.endpoints['orders'], params=params)
            response.raise_for_status()
            
            data = response.json()
            orders = []
            
            for order_data in data.get('orders', []):
                order = Order(
                    order_id=order_data.get('orderId', ''),
                    order_type=order_data.get('orderType', ''),
                    status=order_data.get('status', ''),
                    priority=int(order_data.get('priority', 1)),
                    customer_id=order_data.get('customerId', ''),
                    created_at=self._parse_manhattan_datetime(order_data.get('createdDate')),
                    required_date=self._parse_manhattan_datetime(order_data.get('requiredDate')),
                    shipped_at=self._parse_manhattan_datetime(order_data.get('shippedDate'))
                )
                orders.append(order)
            
            self._log_operation("get_orders", {"count": len(orders)})
            return orders
            
        except Exception as e:
            self.logger.error(f"Failed to get orders from Manhattan WMS: {e}")
            raise WMSDataError(f"Order retrieval failed: {e}")
    
    async def create_order(self, order: Order) -> str:
        """Create a new order in Manhattan WMS."""
        try:
            if not self.connected:
                raise WMSConnectionError("Not connected to Manhattan WMS")
            
            order_data = {
                "facilityId": self.facility_id,
                "orderType": order.order_type,
                "priority": order.priority,
                "customerId": order.customer_id,
                "requiredDate": order.required_date.isoformat() if order.required_date else None,
                "items": order.items or []
            }
            
            response = await self.session.post(self.endpoints['orders'], json=order_data)
            response.raise_for_status()
            
            result = response.json()
            order_id = result.get('orderId', '')
            
            self._log_operation("create_order", {"order_id": order_id})
            return order_id
            
        except Exception as e:
            self.logger.error(f"Failed to create order in Manhattan WMS: {e}")
            raise WMSDataError(f"Order creation failed: {e}")
    
    async def get_locations(self, zone: Optional[str] = None,
                           location_type: Optional[str] = None) -> List[Location]:
        """Retrieve locations from Manhattan WMS."""
        try:
            if not self.connected:
                raise WMSConnectionError("Not connected to Manhattan WMS")
            
            # Build query parameters
            params = {"facilityId": self.facility_id}
            if zone:
                params["zone"] = zone
            if location_type:
                params["locationType"] = location_type
            
            response = await self.session.get(self.endpoints['locations'], params=params)
            response.raise_for_status()
            
            data = response.json()
            locations = []
            
            for loc_data in data.get('locations', []):
                location = Location(
                    location_id=loc_data.get('locationId', ''),
                    name=loc_data.get('locationName', ''),
                    zone=loc_data.get('zone', ''),
                    aisle=loc_data.get('aisle', ''),
                    rack=loc_data.get('rack', ''),
                    level=loc_data.get('level', ''),
                    position=loc_data.get('position', ''),
                    location_type=loc_data.get('locationType', 'storage'),
                    capacity=int(loc_data.get('capacity', 0)),
                    current_utilization=int(loc_data.get('currentUtilization', 0)),
                    status=loc_data.get('status', 'active')
                )
                locations.append(location)
            
            self._log_operation("get_locations", {"count": len(locations)})
            return locations
            
        except Exception as e:
            self.logger.error(f"Failed to get locations from Manhattan WMS: {e}")
            raise WMSDataError(f"Location retrieval failed: {e}")
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get Manhattan WMS system status."""
        try:
            if not self.connected:
                return {"status": "disconnected", "connected": False}
            
            # Test connection with a simple request
            response = await self.session.get(f"{self.endpoints['warehouses']}/{self.facility_id}")
            
            return {
                "status": "connected" if response.status_code == 200 else "error",
                "connected": response.status_code == 200,
                "facility_id": self.facility_id,
                "client_id": self.client_id,
                "response_time_ms": response.elapsed.total_seconds() * 1000 if hasattr(response, 'elapsed') else None
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get system status: {e}")
            return {"status": "error", "connected": False, "error": str(e)}
    
    def _map_task_status_to_manhattan(self, status: TaskStatus) -> str:
        """Map internal task status to Manhattan WMS status."""
        mapping = {
            TaskStatus.PENDING: "PENDING",
            TaskStatus.IN_PROGRESS: "IN_PROGRESS",
            TaskStatus.COMPLETED: "COMPLETED",
            TaskStatus.FAILED: "FAILED",
            TaskStatus.CANCELLED: "CANCELLED"
        }
        return mapping.get(status, "PENDING")
    
    def _map_manhattan_task_status(self, manhattan_status: str) -> TaskStatus:
        """Map Manhattan WMS status to internal task status."""
        mapping = {
            "PENDING": TaskStatus.PENDING,
            "IN_PROGRESS": TaskStatus.IN_PROGRESS,
            "COMPLETED": TaskStatus.COMPLETED,
            "FAILED": TaskStatus.FAILED,
            "CANCELLED": TaskStatus.CANCELLED
        }
        return mapping.get(manhattan_status, TaskStatus.PENDING)
    
    def _map_task_type_to_manhattan(self, task_type: TaskType) -> str:
        """Map internal task type to Manhattan WMS task type."""
        mapping = {
            TaskType.PICK: "PICK",
            TaskType.PACK: "PACK",
            TaskType.SHIP: "SHIP",
            TaskType.RECEIVE: "RECEIVE",
            TaskType.PUTAWAY: "PUTAWAY",
            TaskType.CYCLE_COUNT: "CYCLE_COUNT",
            TaskType.TRANSFER: "TRANSFER"
        }
        return mapping.get(task_type, "PICK")
    
    def _map_manhattan_task_type(self, manhattan_task_type: str) -> TaskType:
        """Map Manhattan WMS task type to internal task type."""
        mapping = {
            "PICK": TaskType.PICK,
            "PACK": TaskType.PACK,
            "SHIP": TaskType.SHIP,
            "RECEIVE": TaskType.RECEIVE,
            "PUTAWAY": TaskType.PUTAWAY,
            "CYCLE_COUNT": TaskType.CYCLE_COUNT,
            "TRANSFER": TaskType.TRANSFER
        }
        return mapping.get(manhattan_task_type, TaskType.PICK)
    
    def _parse_manhattan_datetime(self, datetime_str: Optional[str]) -> Optional[datetime]:
        """Parse Manhattan datetime string to Python datetime."""
        if not datetime_str:
            return None
        
        try:
            # Manhattan datetime format: YYYY-MM-DDTHH:MM:SS
            return datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
        except ValueError:
            self.logger.warning(f"Failed to parse datetime: {datetime_str}")
            return None
