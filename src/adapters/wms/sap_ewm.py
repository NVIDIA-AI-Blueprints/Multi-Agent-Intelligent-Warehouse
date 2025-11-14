"""
SAP Extended Warehouse Management (EWM) Adapter.

Provides integration with SAP EWM system using RFC connections
and REST API endpoints for warehouse operations.
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

class SAPEWMAdapter(BaseWMSAdapter):
    """
    SAP EWM Adapter for warehouse operations.
    
    Supports both RFC and REST API connections to SAP EWM.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize SAP EWM adapter.
        
        Args:
            config: Configuration containing:
                - host: SAP EWM host
                - port: SAP EWM port
                - client: SAP client
                - user: SAP user
                - password: SAP password
                - system_id: SAP system ID
                - warehouse_number: EWM warehouse number
                - use_rfc: Whether to use RFC (default: False, uses REST)
        """
        super().__init__(config)
        self.host = config.get('host')
        self.port = config.get('port', 8000)
        self.client = config.get('client')
        self.user = config.get('user')
        self.password = config.get('password')
        self.system_id = config.get('system_id')
        self.warehouse_number = config.get('warehouse_number')
        self.use_rfc = config.get('use_rfc', False)
        
        self.base_url = f"http://{self.host}:{self.port}/sap/opu/odata/sap"
        self.session: Optional[httpx.AsyncClient] = None
        
        # SAP EWM specific endpoints
        self.endpoints = {
            'inventory': '/EWM_INVENTORY_SRV',
            'tasks': '/EWM_TASK_SRV',
            'orders': '/EWM_ORDER_SRV',
            'locations': '/EWM_LOCATION_SRV'
        }
    
    async def connect(self) -> bool:
        """Establish connection to SAP EWM."""
        try:
            if not self._validate_config(['host', 'user', 'password', 'warehouse_number']):
                return False
            
            if self.use_rfc:
                return await self._connect_rfc()
            else:
                return await self._connect_rest()
                
        except Exception as e:
            self.logger.error(f"Failed to connect to SAP EWM: {e}")
            raise WMSConnectionError(f"SAP EWM connection failed: {e}")
    
    async def _connect_rest(self) -> bool:
        """Connect using REST API."""
        try:
            self.session = httpx.AsyncClient(
                base_url=self.base_url,
                auth=(self.user, self.password),
                timeout=30.0,
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            )
            
            # Test connection with a simple request
            response = await self.session.get(f"{self.endpoints['inventory']}/$metadata")
            if response.status_code == 200:
                self.connected = True
                self.logger.info("Successfully connected to SAP EWM via REST API")
                return True
            else:
                self.logger.error(f"SAP EWM connection test failed: {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.error(f"REST API connection failed: {e}")
            return False
    
    async def _connect_rfc(self) -> bool:
        """Connect using RFC (placeholder for RFC implementation)."""
        # RFC implementation would go here
        # For now, we'll use REST API as fallback
        self.logger.warning("RFC connection not implemented, falling back to REST API")
        return await self._connect_rest()
    
    async def disconnect(self) -> bool:
        """Disconnect from SAP EWM."""
        try:
            if self.session:
                await self.session.aclose()
                self.session = None
            self.connected = False
            self.logger.info("Disconnected from SAP EWM")
            return True
        except Exception as e:
            self.logger.error(f"Error disconnecting from SAP EWM: {e}")
            return False
    
    async def get_inventory(self, location: Optional[str] = None, 
                          sku: Optional[str] = None) -> List[InventoryItem]:
        """Retrieve inventory from SAP EWM."""
        try:
            if not self.connected:
                raise WMSConnectionError("Not connected to SAP EWM")
            
            # Build OData query
            query_params = []
            if location:
                query_params.append(f"WarehouseNumber eq '{self.warehouse_number}' and StorageBin eq '{location}'")
            if sku:
                query_params.append(f"ProductCode eq '{sku}'")
            
            filter_param = " and ".join(query_params) if query_params else f"WarehouseNumber eq '{self.warehouse_number}'"
            
            url = f"{self.endpoints['inventory']}/InventorySet?$filter={filter_param}"
            
            response = await self.session.get(url)
            response.raise_for_status()
            
            data = response.json()
            items = []
            
            for item_data in data.get('d', {}).get('results', []):
                item = InventoryItem(
                    sku=item_data.get('ProductCode', ''),
                    name=item_data.get('ProductDescription', ''),
                    quantity=int(item_data.get('UnrestrictedStock', 0)),
                    available_quantity=int(item_data.get('AvailableStock', 0)),
                    reserved_quantity=int(item_data.get('BlockedStock', 0)),
                    location=item_data.get('StorageBin', ''),
                    zone=item_data.get('StorageSection', ''),
                    lot_number=item_data.get('BatchNumber', ''),
                    status=item_data.get('StockStatus', 'active'),
                    last_updated=datetime.now()
                )
                items.append(item)
            
            self._log_operation("get_inventory", {"count": len(items)})
            return items
            
        except Exception as e:
            self.logger.error(f"Failed to get inventory from SAP EWM: {e}")
            raise WMSDataError(f"Inventory retrieval failed: {e}")
    
    async def update_inventory(self, items: List[InventoryItem]) -> bool:
        """Update inventory in SAP EWM."""
        try:
            if not self.connected:
                raise WMSConnectionError("Not connected to SAP EWM")
            
            # SAP EWM inventory updates typically require specific transactions
            # This is a simplified implementation
            for item in items:
                # Create inventory adjustment document
                adjustment_data = {
                    "WarehouseNumber": self.warehouse_number,
                    "ProductCode": item.sku,
                    "StorageBin": item.location,
                    "Quantity": item.quantity,
                    "UnitOfMeasure": "EA",
                    "MovementType": "311"  # Inventory adjustment
                }
                
                url = f"{self.endpoints['inventory']}/InventoryAdjustmentSet"
                response = await self.session.post(url, json=adjustment_data)
                response.raise_for_status()
            
            self._log_operation("update_inventory", {"count": len(items)})
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update inventory in SAP EWM: {e}")
            raise WMSDataError(f"Inventory update failed: {e}")
    
    async def get_tasks(self, status: Optional[TaskStatus] = None,
                       assigned_to: Optional[str] = None) -> List[Task]:
        """Retrieve tasks from SAP EWM."""
        try:
            if not self.connected:
                raise WMSConnectionError("Not connected to SAP EWM")
            
            # Build OData query
            query_params = [f"WarehouseNumber eq '{self.warehouse_number}'"]
            
            if status:
                sap_status = self._map_task_status_to_sap(status)
                query_params.append(f"TaskStatus eq '{sap_status}'")
            
            if assigned_to:
                query_params.append(f"AssignedUser eq '{assigned_to}'")
            
            filter_param = " and ".join(query_params)
            url = f"{self.endpoints['tasks']}/TaskSet?$filter={filter_param}"
            
            response = await self.session.get(url)
            response.raise_for_status()
            
            data = response.json()
            tasks = []
            
            for task_data in data.get('d', {}).get('results', []):
                task = Task(
                    task_id=task_data.get('TaskNumber', ''),
                    task_type=self._map_sap_task_type(task_data.get('TaskType', '')),
                    priority=int(task_data.get('Priority', 1)),
                    status=self._map_sap_task_status(task_data.get('TaskStatus', '')),
                    assigned_to=task_data.get('AssignedUser', ''),
                    location=task_data.get('SourceStorageBin', ''),
                    destination=task_data.get('DestinationStorageBin', ''),
                    created_at=self._parse_sap_datetime(task_data.get('CreationDate')),
                    notes=task_data.get('TaskDescription', '')
                )
                tasks.append(task)
            
            self._log_operation("get_tasks", {"count": len(tasks)})
            return tasks
            
        except Exception as e:
            self.logger.error(f"Failed to get tasks from SAP EWM: {e}")
            raise WMSDataError(f"Task retrieval failed: {e}")
    
    async def create_task(self, task: Task) -> str:
        """Create a new task in SAP EWM."""
        try:
            if not self.connected:
                raise WMSConnectionError("Not connected to SAP EWM")
            
            task_data = {
                "WarehouseNumber": self.warehouse_number,
                "TaskType": self._map_task_type_to_sap(task.task_type),
                "Priority": task.priority,
                "SourceStorageBin": task.location,
                "DestinationStorageBin": task.destination,
                "AssignedUser": task.assigned_to,
                "TaskDescription": task.notes
            }
            
            url = f"{self.endpoints['tasks']}/TaskSet"
            response = await self.session.post(url, json=task_data)
            response.raise_for_status()
            
            result = response.json()
            task_id = result.get('d', {}).get('TaskNumber', '')
            
            self._log_operation("create_task", {"task_id": task_id})
            return task_id
            
        except Exception as e:
            self.logger.error(f"Failed to create task in SAP EWM: {e}")
            raise WMSDataError(f"Task creation failed: {e}")
    
    async def update_task_status(self, task_id: str, status: TaskStatus,
                                notes: Optional[str] = None) -> bool:
        """Update task status in SAP EWM."""
        try:
            if not self.connected:
                raise WMSConnectionError("Not connected to SAP EWM")
            
            update_data = {
                "TaskStatus": self._map_task_status_to_sap(status)
            }
            
            if notes:
                update_data["TaskDescription"] = notes
            
            url = f"{self.endpoints['tasks']}/TaskSet('{task_id}')"
            response = await self.session.patch(url, json=update_data)
            response.raise_for_status()
            
            self._log_operation("update_task_status", {"task_id": task_id, "status": status.value})
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update task status in SAP EWM: {e}")
            raise WMSDataError(f"Task status update failed: {e}")
    
    async def get_orders(self, status: Optional[str] = None,
                        order_type: Optional[str] = None) -> List[Order]:
        """Retrieve orders from SAP EWM."""
        try:
            if not self.connected:
                raise WMSConnectionError("Not connected to SAP EWM")
            
            # Build OData query
            query_params = [f"WarehouseNumber eq '{self.warehouse_number}'"]
            
            if status:
                query_params.append(f"OrderStatus eq '{status}'")
            
            if order_type:
                query_params.append(f"OrderType eq '{order_type}'")
            
            filter_param = " and ".join(query_params)
            url = f"{self.endpoints['orders']}/OrderSet?$filter={filter_param}"
            
            response = await self.session.get(url)
            response.raise_for_status()
            
            data = response.json()
            orders = []
            
            for order_data in data.get('d', {}).get('results', []):
                order = Order(
                    order_id=order_data.get('OrderNumber', ''),
                    order_type=order_data.get('OrderType', ''),
                    status=order_data.get('OrderStatus', ''),
                    priority=int(order_data.get('Priority', 1)),
                    created_at=self._parse_sap_datetime(order_data.get('CreationDate')),
                    required_date=self._parse_sap_datetime(order_data.get('RequiredDate'))
                )
                orders.append(order)
            
            self._log_operation("get_orders", {"count": len(orders)})
            return orders
            
        except Exception as e:
            self.logger.error(f"Failed to get orders from SAP EWM: {e}")
            raise WMSDataError(f"Order retrieval failed: {e}")
    
    async def create_order(self, order: Order) -> str:
        """Create a new order in SAP EWM."""
        try:
            if not self.connected:
                raise WMSConnectionError("Not connected to SAP EWM")
            
            order_data = {
                "WarehouseNumber": self.warehouse_number,
                "OrderType": order.order_type,
                "Priority": order.priority,
                "RequiredDate": order.required_date.isoformat() if order.required_date else None
            }
            
            url = f"{self.endpoints['orders']}/OrderSet"
            response = await self.session.post(url, json=order_data)
            response.raise_for_status()
            
            result = response.json()
            order_id = result.get('d', {}).get('OrderNumber', '')
            
            self._log_operation("create_order", {"order_id": order_id})
            return order_id
            
        except Exception as e:
            self.logger.error(f"Failed to create order in SAP EWM: {e}")
            raise WMSDataError(f"Order creation failed: {e}")
    
    async def get_locations(self, zone: Optional[str] = None,
                           location_type: Optional[str] = None) -> List[Location]:
        """Retrieve locations from SAP EWM."""
        try:
            if not self.connected:
                raise WMSConnectionError("Not connected to SAP EWM")
            
            # Build OData query
            query_params = [f"WarehouseNumber eq '{self.warehouse_number}'"]
            
            if zone:
                query_params.append(f"StorageSection eq '{zone}'")
            
            if location_type:
                query_params.append(f"StorageBinType eq '{location_type}'")
            
            filter_param = " and ".join(query_params)
            url = f"{self.endpoints['locations']}/LocationSet?$filter={filter_param}"
            
            response = await self.session.get(url)
            response.raise_for_status()
            
            data = response.json()
            locations = []
            
            for loc_data in data.get('d', {}).get('results', []):
                location = Location(
                    location_id=loc_data.get('StorageBin', ''),
                    name=loc_data.get('StorageBinDescription', ''),
                    zone=loc_data.get('StorageSection', ''),
                    location_type=loc_data.get('StorageBinType', 'storage'),
                    capacity=int(loc_data.get('Capacity', 0)),
                    status=loc_data.get('StorageBinStatus', 'active')
                )
                locations.append(location)
            
            self._log_operation("get_locations", {"count": len(locations)})
            return locations
            
        except Exception as e:
            self.logger.error(f"Failed to get locations from SAP EWM: {e}")
            raise WMSDataError(f"Location retrieval failed: {e}")
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get SAP EWM system status."""
        try:
            if not self.connected:
                return {"status": "disconnected", "connected": False}
            
            # Test connection with a simple metadata request
            response = await self.session.get(f"{self.endpoints['inventory']}/$metadata")
            
            return {
                "status": "connected" if response.status_code == 200 else "error",
                "connected": response.status_code == 200,
                "warehouse_number": self.warehouse_number,
                "system_id": self.system_id,
                "response_time_ms": response.elapsed.total_seconds() * 1000 if hasattr(response, 'elapsed') else None
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get system status: {e}")
            return {"status": "error", "connected": False, "error": str(e)}
    
    def _map_task_status_to_sap(self, status: TaskStatus) -> str:
        """Map internal task status to SAP EWM status."""
        mapping = {
            TaskStatus.PENDING: "P",
            TaskStatus.IN_PROGRESS: "I",
            TaskStatus.COMPLETED: "C",
            TaskStatus.FAILED: "F",
            TaskStatus.CANCELLED: "X"
        }
        return mapping.get(status, "P")
    
    def _map_sap_task_status(self, sap_status: str) -> TaskStatus:
        """Map SAP EWM status to internal task status."""
        mapping = {
            "P": TaskStatus.PENDING,
            "I": TaskStatus.IN_PROGRESS,
            "C": TaskStatus.COMPLETED,
            "F": TaskStatus.FAILED,
            "X": TaskStatus.CANCELLED
        }
        return mapping.get(sap_status, TaskStatus.PENDING)
    
    def _map_task_type_to_sap(self, task_type: TaskType) -> str:
        """Map internal task type to SAP EWM task type."""
        mapping = {
            TaskType.PICK: "PICK",
            TaskType.PACK: "PACK",
            TaskType.SHIP: "SHIP",
            TaskType.RECEIVE: "RECEIVE",
            TaskType.PUTAWAY: "PUTAWAY",
            TaskType.CYCLE_COUNT: "COUNT",
            TaskType.TRANSFER: "TRANSFER"
        }
        return mapping.get(task_type, "PICK")
    
    def _map_sap_task_type(self, sap_task_type: str) -> TaskType:
        """Map SAP EWM task type to internal task type."""
        mapping = {
            "PICK": TaskType.PICK,
            "PACK": TaskType.PACK,
            "SHIP": TaskType.SHIP,
            "RECEIVE": TaskType.RECEIVE,
            "PUTAWAY": TaskType.PUTAWAY,
            "COUNT": TaskType.CYCLE_COUNT,
            "TRANSFER": TaskType.TRANSFER
        }
        return mapping.get(sap_task_type, TaskType.PICK)
    
    def _parse_sap_datetime(self, datetime_str: Optional[str]) -> Optional[datetime]:
        """Parse SAP datetime string to Python datetime."""
        if not datetime_str:
            return None
        
        try:
            # SAP datetime format: YYYY-MM-DDTHH:MM:SS
            return datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
        except ValueError:
            self.logger.warning(f"Failed to parse datetime: {datetime_str}")
            return None
