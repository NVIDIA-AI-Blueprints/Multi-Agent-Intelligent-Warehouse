"""
Oracle WMS Adapter.

Provides integration with Oracle WMS system using
REST API and database connections for warehouse operations.
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

class OracleWMSAdapter(BaseWMSAdapter):
    """
    Oracle WMS Adapter for warehouse operations.
    
    Supports REST API and database connections to Oracle WMS.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Oracle WMS adapter.
        
        Args:
            config: Configuration containing:
                - host: Oracle WMS host
                - port: Oracle WMS port (default: 8000)
                - username: Oracle username
                - password: Oracle password
                - organization_id: Oracle organization ID
                - warehouse_id: Oracle warehouse ID
                - use_ssl: Whether to use SSL (default: True)
                - database_config: Optional database connection config
        """
        super().__init__(config)
        self.host = config.get('host')
        self.port = config.get('port', 8000)
        self.username = config.get('username')
        self.password = config.get('password')
        self.organization_id = config.get('organization_id')
        self.warehouse_id = config.get('warehouse_id')
        self.use_ssl = config.get('use_ssl', True)
        self.database_config = config.get('database_config')
        
        protocol = "https" if self.use_ssl else "http"
        self.base_url = f"{protocol}://{self.host}:{self.port}/fscmRestApi/resources"
        self.session: Optional[httpx.AsyncClient] = None
        self.auth_token: Optional[str] = None
        
        # Oracle WMS API endpoints
        self.endpoints = {
            'auth': '/security/v1/oauth2/token',
            'inventory': '/11.13.18.05/inventoryOnHand',
            'tasks': '/11.13.18.05/warehouseTasks',
            'orders': '/11.13.18.05/salesOrders',
            'locations': '/11.13.18.05/warehouseLocations',
            'organizations': '/11.13.18.05/organizations'
        }
    
    async def connect(self) -> bool:
        """Establish connection to Oracle WMS."""
        try:
            if not self._validate_config(['host', 'username', 'password', 'organization_id']):
                return False
            
            return await self._authenticate()
                
        except Exception as e:
            self.logger.error(f"Failed to connect to Oracle WMS: {e}")
            raise WMSConnectionError(f"Oracle WMS connection failed: {e}")
    
    async def _authenticate(self) -> bool:
        """Authenticate with Oracle WMS."""
        try:
            self.session = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0,
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Accept': 'application/json'
                }
            )
            
            # Authenticate and get token
            auth_data = {
                "grant_type": "client_credentials",
                "username": self.username,
                "password": self.password
            }
            
            response = await self.session.post(self.endpoints['auth'], data=auth_data)
            response.raise_for_status()
            
            auth_result = response.json()
            self.auth_token = auth_result.get('access_token')
            
            if self.auth_token:
                # Update session headers with auth token
                self.session.headers.update({
                    'Authorization': f'Bearer {self.auth_token}',
                    'Content-Type': 'application/json'
                })
                
                self.connected = True
                self.logger.info("Successfully connected to Oracle WMS")
                return True
            else:
                self.logger.error("Failed to get authentication token")
                return False
                
        except Exception as e:
            self.logger.error(f"Oracle WMS authentication failed: {e}")
            return False
    
    async def disconnect(self) -> bool:
        """Disconnect from Oracle WMS."""
        try:
            if self.session:
                await self.session.aclose()
                self.session = None
            
            self.auth_token = None
            self.connected = False
            self.logger.info("Disconnected from Oracle WMS")
            return True
        except Exception as e:
            self.logger.error(f"Error disconnecting from Oracle WMS: {e}")
            return False
    
    async def get_inventory(self, location: Optional[str] = None, 
                          sku: Optional[str] = None) -> List[InventoryItem]:
        """Retrieve inventory from Oracle WMS."""
        try:
            if not self.connected:
                raise WMSConnectionError("Not connected to Oracle WMS")
            
            # Build query parameters
            params = {
                "q": f"OrganizationId={self.organization_id}"
            }
            
            if location:
                params["q"] += f" and LocationId='{location}'"
            if sku:
                params["q"] += f" and ItemId='{sku}'"
            
            response = await self.session.get(self.endpoints['inventory'], params=params)
            response.raise_for_status()
            
            data = response.json()
            items = []
            
            for item_data in data.get('items', []):
                item = InventoryItem(
                    sku=item_data.get('ItemId', ''),
                    name=item_data.get('ItemDescription', ''),
                    description=item_data.get('ItemLongDescription', ''),
                    quantity=int(item_data.get('QuantityOnHand', 0)),
                    available_quantity=int(item_data.get('QuantityAvailable', 0)),
                    reserved_quantity=int(item_data.get('QuantityReserved', 0)),
                    location=item_data.get('LocationId', ''),
                    zone=item_data.get('ZoneId', ''),
                    lot_number=item_data.get('LotNumber', ''),
                    serial_number=item_data.get('SerialNumber', ''),
                    expiry_date=self._parse_oracle_datetime(item_data.get('ExpirationDate')),
                    status=item_data.get('Status', 'active'),
                    last_updated=self._parse_oracle_datetime(item_data.get('LastUpdateDate'))
                )
                items.append(item)
            
            self._log_operation("get_inventory", {"count": len(items)})
            return items
            
        except Exception as e:
            self.logger.error(f"Failed to get inventory from Oracle WMS: {e}")
            raise WMSDataError(f"Inventory retrieval failed: {e}")
    
    async def update_inventory(self, items: List[InventoryItem]) -> bool:
        """Update inventory in Oracle WMS."""
        try:
            if not self.connected:
                raise WMSConnectionError("Not connected to Oracle WMS")
            
            for item in items:
                # Create inventory adjustment
                adjustment_data = {
                    "OrganizationId": self.organization_id,
                    "ItemId": item.sku,
                    "LocationId": item.location,
                    "Quantity": item.quantity,
                    "AdjustmentType": "MANUAL",
                    "ReasonCode": "SYSTEM_ADJUSTMENT"
                }
                
                response = await self.session.post(
                    f"{self.endpoints['inventory']}/adjustments",
                    json=adjustment_data
                )
                response.raise_for_status()
            
            self._log_operation("update_inventory", {"count": len(items)})
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update inventory in Oracle WMS: {e}")
            raise WMSDataError(f"Inventory update failed: {e}")
    
    async def get_tasks(self, status: Optional[TaskStatus] = None,
                       assigned_to: Optional[str] = None) -> List[Task]:
        """Retrieve tasks from Oracle WMS."""
        try:
            if not self.connected:
                raise WMSConnectionError("Not connected to Oracle WMS")
            
            # Build query parameters
            params = {
                "q": f"OrganizationId={self.organization_id}"
            }
            
            if status:
                oracle_status = self._map_task_status_to_oracle(status)
                params["q"] += f" and Status='{oracle_status}'"
            
            if assigned_to:
                params["q"] += f" and AssignedTo='{assigned_to}'"
            
            response = await self.session.get(self.endpoints['tasks'], params=params)
            response.raise_for_status()
            
            data = response.json()
            tasks = []
            
            for task_data in data.get('items', []):
                task = Task(
                    task_id=task_data.get('TaskId', ''),
                    task_type=self._map_oracle_task_type(task_data.get('TaskType', '')),
                    priority=int(task_data.get('Priority', 1)),
                    status=self._map_oracle_task_status(task_data.get('Status', '')),
                    assigned_to=task_data.get('AssignedTo', ''),
                    location=task_data.get('SourceLocationId', ''),
                    destination=task_data.get('DestinationLocationId', ''),
                    created_at=self._parse_oracle_datetime(task_data.get('CreationDate')),
                    started_at=self._parse_oracle_datetime(task_data.get('StartDate')),
                    completed_at=self._parse_oracle_datetime(task_data.get('CompletionDate')),
                    notes=task_data.get('Description', '')
                )
                tasks.append(task)
            
            self._log_operation("get_tasks", {"count": len(tasks)})
            return tasks
            
        except Exception as e:
            self.logger.error(f"Failed to get tasks from Oracle WMS: {e}")
            raise WMSDataError(f"Task retrieval failed: {e}")
    
    async def create_task(self, task: Task) -> str:
        """Create a new task in Oracle WMS."""
        try:
            if not self.connected:
                raise WMSConnectionError("Not connected to Oracle WMS")
            
            task_data = {
                "OrganizationId": self.organization_id,
                "TaskType": self._map_task_type_to_oracle(task.task_type),
                "Priority": task.priority,
                "SourceLocationId": task.location,
                "DestinationLocationId": task.destination,
                "AssignedTo": task.assigned_to,
                "Description": task.notes
            }
            
            response = await self.session.post(self.endpoints['tasks'], json=task_data)
            response.raise_for_status()
            
            result = response.json()
            task_id = result.get('TaskId', '')
            
            self._log_operation("create_task", {"task_id": task_id})
            return task_id
            
        except Exception as e:
            self.logger.error(f"Failed to create task in Oracle WMS: {e}")
            raise WMSDataError(f"Task creation failed: {e}")
    
    async def update_task_status(self, task_id: str, status: TaskStatus,
                                notes: Optional[str] = None) -> bool:
        """Update task status in Oracle WMS."""
        try:
            if not self.connected:
                raise WMSConnectionError("Not connected to Oracle WMS")
            
            update_data = {
                "Status": self._map_task_status_to_oracle(status)
            }
            
            if notes:
                update_data["Description"] = notes
            
            response = await self.session.patch(
                f"{self.endpoints['tasks']}/{task_id}",
                json=update_data
            )
            response.raise_for_status()
            
            self._log_operation("update_task_status", {"task_id": task_id, "status": status.value})
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update task status in Oracle WMS: {e}")
            raise WMSDataError(f"Task status update failed: {e}")
    
    async def get_orders(self, status: Optional[str] = None,
                        order_type: Optional[str] = None) -> List[Order]:
        """Retrieve orders from Oracle WMS."""
        try:
            if not self.connected:
                raise WMSConnectionError("Not connected to Oracle WMS")
            
            # Build query parameters
            params = {
                "q": f"OrganizationId={self.organization_id}"
            }
            
            if status:
                params["q"] += f" and Status='{status}'"
            
            if order_type:
                params["q"] += f" and OrderType='{order_type}'"
            
            response = await self.session.get(self.endpoints['orders'], params=params)
            response.raise_for_status()
            
            data = response.json()
            orders = []
            
            for order_data in data.get('items', []):
                order = Order(
                    order_id=order_data.get('OrderNumber', ''),
                    order_type=order_data.get('OrderType', ''),
                    status=order_data.get('Status', ''),
                    priority=int(order_data.get('Priority', 1)),
                    customer_id=order_data.get('CustomerId', ''),
                    created_at=self._parse_oracle_datetime(order_data.get('OrderDate')),
                    required_date=self._parse_oracle_datetime(order_data.get('RequestDate')),
                    shipped_at=self._parse_oracle_datetime(order_data.get('ShipDate'))
                )
                orders.append(order)
            
            self._log_operation("get_orders", {"count": len(orders)})
            return orders
            
        except Exception as e:
            self.logger.error(f"Failed to get orders from Oracle WMS: {e}")
            raise WMSDataError(f"Order retrieval failed: {e}")
    
    async def create_order(self, order: Order) -> str:
        """Create a new order in Oracle WMS."""
        try:
            if not self.connected:
                raise WMSConnectionError("Not connected to Oracle WMS")
            
            order_data = {
                "OrganizationId": self.organization_id,
                "OrderType": order.order_type,
                "Priority": order.priority,
                "CustomerId": order.customer_id,
                "RequestDate": order.required_date.isoformat() if order.required_date else None,
                "OrderLines": order.items or []
            }
            
            response = await self.session.post(self.endpoints['orders'], json=order_data)
            response.raise_for_status()
            
            result = response.json()
            order_id = result.get('OrderNumber', '')
            
            self._log_operation("create_order", {"order_id": order_id})
            return order_id
            
        except Exception as e:
            self.logger.error(f"Failed to create order in Oracle WMS: {e}")
            raise WMSDataError(f"Order creation failed: {e}")
    
    async def get_locations(self, zone: Optional[str] = None,
                           location_type: Optional[str] = None) -> List[Location]:
        """Retrieve locations from Oracle WMS."""
        try:
            if not self.connected:
                raise WMSConnectionError("Not connected to Oracle WMS")
            
            # Build query parameters
            params = {
                "q": f"OrganizationId={self.organization_id}"
            }
            
            if zone:
                params["q"] += f" and ZoneId='{zone}'"
            
            if location_type:
                params["q"] += f" and LocationType='{location_type}'"
            
            response = await self.session.get(self.endpoints['locations'], params=params)
            response.raise_for_status()
            
            data = response.json()
            locations = []
            
            for loc_data in data.get('items', []):
                location = Location(
                    location_id=loc_data.get('LocationId', ''),
                    name=loc_data.get('LocationName', ''),
                    zone=loc_data.get('ZoneId', ''),
                    aisle=loc_data.get('AisleId', ''),
                    rack=loc_data.get('RackId', ''),
                    level=loc_data.get('LevelId', ''),
                    position=loc_data.get('PositionId', ''),
                    location_type=loc_data.get('LocationType', 'storage'),
                    capacity=int(loc_data.get('Capacity', 0)),
                    current_utilization=int(loc_data.get('CurrentUtilization', 0)),
                    status=loc_data.get('Status', 'active')
                )
                locations.append(location)
            
            self._log_operation("get_locations", {"count": len(locations)})
            return locations
            
        except Exception as e:
            self.logger.error(f"Failed to get locations from Oracle WMS: {e}")
            raise WMSDataError(f"Location retrieval failed: {e}")
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get Oracle WMS system status."""
        try:
            if not self.connected:
                return {"status": "disconnected", "connected": False}
            
            # Test connection with a simple request
            response = await self.session.get(f"{self.endpoints['organizations']}/{self.organization_id}")
            
            return {
                "status": "connected" if response.status_code == 200 else "error",
                "connected": response.status_code == 200,
                "organization_id": self.organization_id,
                "warehouse_id": self.warehouse_id,
                "response_time_ms": response.elapsed.total_seconds() * 1000 if hasattr(response, 'elapsed') else None
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get system status: {e}")
            return {"status": "error", "connected": False, "error": str(e)}
    
    def _map_task_status_to_oracle(self, status: TaskStatus) -> str:
        """Map internal task status to Oracle WMS status."""
        mapping = {
            TaskStatus.PENDING: "PENDING",
            TaskStatus.IN_PROGRESS: "IN_PROGRESS",
            TaskStatus.COMPLETED: "COMPLETED",
            TaskStatus.FAILED: "FAILED",
            TaskStatus.CANCELLED: "CANCELLED"
        }
        return mapping.get(status, "PENDING")
    
    def _map_oracle_task_status(self, oracle_status: str) -> TaskStatus:
        """Map Oracle WMS status to internal task status."""
        mapping = {
            "PENDING": TaskStatus.PENDING,
            "IN_PROGRESS": TaskStatus.IN_PROGRESS,
            "COMPLETED": TaskStatus.COMPLETED,
            "FAILED": TaskStatus.FAILED,
            "CANCELLED": TaskStatus.CANCELLED
        }
        return mapping.get(oracle_status, TaskStatus.PENDING)
    
    def _map_task_type_to_oracle(self, task_type: TaskType) -> str:
        """Map internal task type to Oracle WMS task type."""
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
    
    def _map_oracle_task_type(self, oracle_task_type: str) -> TaskType:
        """Map Oracle WMS task type to internal task type."""
        mapping = {
            "PICK": TaskType.PICK,
            "PACK": TaskType.PACK,
            "SHIP": TaskType.SHIP,
            "RECEIVE": TaskType.RECEIVE,
            "PUTAWAY": TaskType.PUTAWAY,
            "CYCLE_COUNT": TaskType.CYCLE_COUNT,
            "TRANSFER": TaskType.TRANSFER
        }
        return mapping.get(oracle_task_type, TaskType.PICK)
    
    def _parse_oracle_datetime(self, datetime_str: Optional[str]) -> Optional[datetime]:
        """Parse Oracle datetime string to Python datetime."""
        if not datetime_str:
            return None
        
        try:
            # Oracle datetime format: YYYY-MM-DDTHH:MM:SS
            return datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
        except ValueError:
            self.logger.warning(f"Failed to parse datetime: {datetime_str}")
            return None
