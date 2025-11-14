"""
Base WMS Adapter - Common interface and functionality for all WMS adapters.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from datetime import datetime
import logging
from enum import Enum

logger = logging.getLogger(__name__)

class WMSConnectionError(Exception):
    """Raised when WMS connection fails."""
    pass

class WMSDataError(Exception):
    """Raised when WMS data processing fails."""
    pass

class TaskStatus(Enum):
    """Task status enumeration."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskType(Enum):
    """Task type enumeration."""
    PICK = "pick"
    PACK = "pack"
    SHIP = "ship"
    RECEIVE = "receive"
    PUTAWAY = "putaway"
    CYCLE_COUNT = "cycle_count"
    TRANSFER = "transfer"

@dataclass
class InventoryItem:
    """Inventory item data structure."""
    sku: str
    name: str
    description: Optional[str] = None
    quantity: int = 0
    available_quantity: int = 0
    reserved_quantity: int = 0
    location: Optional[str] = None
    zone: Optional[str] = None
    lot_number: Optional[str] = None
    serial_number: Optional[str] = None
    expiry_date: Optional[datetime] = None
    status: str = "active"
    last_updated: Optional[datetime] = None

@dataclass
class Task:
    """Task data structure."""
    task_id: str
    task_type: TaskType
    priority: int = 1
    status: TaskStatus = TaskStatus.PENDING
    assigned_to: Optional[str] = None
    location: Optional[str] = None
    destination: Optional[str] = None
    items: List[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    notes: Optional[str] = None

@dataclass
class Order:
    """Order data structure."""
    order_id: str
    order_type: str
    status: str
    priority: int = 1
    customer_id: Optional[str] = None
    items: List[Dict[str, Any]] = None
    shipping_address: Optional[Dict[str, str]] = None
    created_at: Optional[datetime] = None
    required_date: Optional[datetime] = None
    shipped_at: Optional[datetime] = None

@dataclass
class Location:
    """Location data structure."""
    location_id: str
    name: str
    zone: str
    aisle: Optional[str] = None
    rack: Optional[str] = None
    level: Optional[str] = None
    position: Optional[str] = None
    location_type: str = "storage"
    capacity: Optional[int] = None
    current_utilization: Optional[int] = None
    status: str = "active"

class BaseWMSAdapter(ABC):
    """
    Base class for all WMS adapters.
    
    Provides common interface and functionality for integrating with
    external WMS systems like SAP EWM, Manhattan, and Oracle WMS.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the WMS adapter.
        
        Args:
            config: Configuration dictionary containing connection details
        """
        self.config = config
        self.connected = False
        self.logger = logging.getLogger(f"{self.__class__.__module__}.{self.__class__.__name__}")
    
    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish connection to the WMS system.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> bool:
        """
        Disconnect from the WMS system.
        
        Returns:
            bool: True if disconnection successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def get_inventory(self, location: Optional[str] = None, 
                          sku: Optional[str] = None) -> List[InventoryItem]:
        """
        Retrieve inventory information.
        
        Args:
            location: Optional location filter
            sku: Optional SKU filter
            
        Returns:
            List[InventoryItem]: List of inventory items
        """
        pass
    
    @abstractmethod
    async def update_inventory(self, items: List[InventoryItem]) -> bool:
        """
        Update inventory information.
        
        Args:
            items: List of inventory items to update
            
        Returns:
            bool: True if update successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def get_tasks(self, status: Optional[TaskStatus] = None,
                       assigned_to: Optional[str] = None) -> List[Task]:
        """
        Retrieve tasks from the WMS.
        
        Args:
            status: Optional task status filter
            assigned_to: Optional worker filter
            
        Returns:
            List[Task]: List of tasks
        """
        pass
    
    @abstractmethod
    async def create_task(self, task: Task) -> str:
        """
        Create a new task in the WMS.
        
        Args:
            task: Task object to create
            
        Returns:
            str: Task ID of created task
        """
        pass
    
    @abstractmethod
    async def update_task_status(self, task_id: str, status: TaskStatus,
                                notes: Optional[str] = None) -> bool:
        """
        Update task status in the WMS.
        
        Args:
            task_id: ID of task to update
            status: New status
            notes: Optional notes
            
        Returns:
            bool: True if update successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def get_orders(self, status: Optional[str] = None,
                        order_type: Optional[str] = None) -> List[Order]:
        """
        Retrieve orders from the WMS.
        
        Args:
            status: Optional order status filter
            order_type: Optional order type filter
            
        Returns:
            List[Order]: List of orders
        """
        pass
    
    @abstractmethod
    async def create_order(self, order: Order) -> str:
        """
        Create a new order in the WMS.
        
        Args:
            order: Order object to create
            
        Returns:
            str: Order ID of created order
        """
        pass
    
    @abstractmethod
    async def get_locations(self, zone: Optional[str] = None,
                           location_type: Optional[str] = None) -> List[Location]:
        """
        Retrieve location information.
        
        Args:
            zone: Optional zone filter
            location_type: Optional location type filter
            
        Returns:
            List[Location]: List of locations
        """
        pass
    
    @abstractmethod
    async def get_system_status(self) -> Dict[str, Any]:
        """
        Get WMS system status and health information.
        
        Returns:
            Dict[str, Any]: System status information
        """
        pass
    
    def _validate_config(self, required_fields: List[str]) -> bool:
        """
        Validate configuration has required fields.
        
        Args:
            required_fields: List of required configuration fields
            
        Returns:
            bool: True if valid, False otherwise
        """
        missing_fields = [field for field in required_fields if field not in self.config]
        if missing_fields:
            self.logger.error(f"Missing required configuration fields: {missing_fields}")
            return False
        return True
    
    def _log_operation(self, operation: str, details: Optional[Dict[str, Any]] = None):
        """
        Log WMS operation for audit purposes.
        
        Args:
            operation: Operation name
            details: Optional operation details
        """
        log_data = {
            "adapter": self.__class__.__name__,
            "operation": operation,
            "timestamp": datetime.now().isoformat()
        }
        if details:
            log_data.update(details)
        
        self.logger.info(f"WMS Operation: {operation}", extra=log_data)
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on the WMS connection.
        
        Returns:
            Dict[str, Any]: Health check results
        """
        try:
            status = await self.get_system_status()
            return {
                "status": "healthy" if self.connected else "disconnected",
                "connected": self.connected,
                "system_status": status,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "connected": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
