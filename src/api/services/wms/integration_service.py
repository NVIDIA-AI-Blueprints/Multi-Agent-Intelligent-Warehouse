"""
WMS Integration Service - Manages WMS adapter connections and operations.
"""

import asyncio
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
import logging
from src.adapters.wms import WMSAdapterFactory, BaseWMSAdapter
from src.adapters.wms.base import InventoryItem, Task, Order, Location, TaskStatus, TaskType

logger = logging.getLogger(__name__)


class WMSIntegrationService:
    """
    Service for managing WMS integrations and operations.

    Provides a unified interface for working with multiple WMS systems
    and handles connection management, data synchronization, and error handling.
    """

    def __init__(self):
        self.adapters: Dict[str, BaseWMSAdapter] = {}
        self.logger = logging.getLogger(
            f"{self.__class__.__module__}.{self.__class__.__name__}"
        )

    async def add_wms_connection(
        self, wms_type: str, config: Dict[str, Any], connection_id: str
    ) -> bool:
        """
        Add a new WMS connection.

        Args:
            wms_type: Type of WMS system (sap_ewm, manhattan, oracle)
            config: Configuration for the WMS connection
            connection_id: Unique identifier for this connection

        Returns:
            bool: True if connection added successfully
        """
        try:
            adapter = WMSAdapterFactory.create_adapter(wms_type, config, connection_id)

            # Test connection
            connected = await adapter.connect()
            if connected:
                self.adapters[connection_id] = adapter
                self.logger.info(f"Added WMS connection: {connection_id} ({wms_type})")
                return True
            else:
                self.logger.error(f"Failed to connect to WMS: {connection_id}")
                return False

        except Exception as e:
            self.logger.error(f"Error adding WMS connection {connection_id}: {e}")
            return False

    async def remove_wms_connection(self, connection_id: str) -> bool:
        """
        Remove a WMS connection.

        Args:
            connection_id: Connection identifier to remove

        Returns:
            bool: True if connection removed successfully
        """
        try:
            if connection_id in self.adapters:
                adapter = self.adapters[connection_id]
                await adapter.disconnect()
                del self.adapters[connection_id]

                # Also remove from factory cache
                WMSAdapterFactory.remove_adapter(
                    adapter.__class__.__name__.lower().replace("adapter", ""),
                    connection_id,
                )

                self.logger.info(f"Removed WMS connection: {connection_id}")
                return True
            else:
                self.logger.warning(f"WMS connection not found: {connection_id}")
                return False

        except Exception as e:
            self.logger.error(f"Error removing WMS connection {connection_id}: {e}")
            return False

    async def get_connection_status(
        self, connection_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get connection status for WMS systems.

        Args:
            connection_id: Optional specific connection to check

        Returns:
            Dict[str, Any]: Connection status information
        """
        if connection_id:
            if connection_id in self.adapters:
                adapter = self.adapters[connection_id]
                return await adapter.health_check()
            else:
                return {"status": "not_found", "connected": False}
        else:
            # Check all connections
            status = {}
            for conn_id, adapter in self.adapters.items():
                status[conn_id] = await adapter.health_check()
            return status

    async def get_inventory(
        self,
        connection_id: str,
        location: Optional[str] = None,
        sku: Optional[str] = None,
    ) -> List[InventoryItem]:
        """
        Get inventory from a specific WMS connection.

        Args:
            connection_id: WMS connection identifier
            location: Optional location filter
            sku: Optional SKU filter

        Returns:
            List[InventoryItem]: Inventory items
        """
        if connection_id not in self.adapters:
            raise ValueError(f"WMS connection not found: {connection_id}")

        adapter = self.adapters[connection_id]
        return await adapter.get_inventory(location, sku)

    async def get_inventory_all(
        self, location: Optional[str] = None, sku: Optional[str] = None
    ) -> Dict[str, List[InventoryItem]]:
        """
        Get inventory from all WMS connections.

        Args:
            location: Optional location filter
            sku: Optional SKU filter

        Returns:
            Dict[str, List[InventoryItem]]: Inventory by connection ID
        """
        results = {}

        for connection_id, adapter in self.adapters.items():
            try:
                inventory = await adapter.get_inventory(location, sku)
                results[connection_id] = inventory
            except Exception as e:
                self.logger.error(f"Error getting inventory from {connection_id}: {e}")
                results[connection_id] = []

        return results

    async def update_inventory(
        self, connection_id: str, items: List[InventoryItem]
    ) -> bool:
        """
        Update inventory in a specific WMS connection.

        Args:
            connection_id: WMS connection identifier
            items: Inventory items to update

        Returns:
            bool: True if update successful
        """
        if connection_id not in self.adapters:
            raise ValueError(f"WMS connection not found: {connection_id}")

        adapter = self.adapters[connection_id]
        return await adapter.update_inventory(items)

    async def get_tasks(
        self,
        connection_id: str,
        status: Optional[TaskStatus] = None,
        assigned_to: Optional[str] = None,
    ) -> List[Task]:
        """
        Get tasks from a specific WMS connection.

        Args:
            connection_id: WMS connection identifier
            status: Optional task status filter
            assigned_to: Optional worker filter

        Returns:
            List[Task]: Tasks
        """
        if connection_id not in self.adapters:
            raise ValueError(f"WMS connection not found: {connection_id}")

        adapter = self.adapters[connection_id]
        return await adapter.get_tasks(status, assigned_to)

    async def get_tasks_all(
        self, status: Optional[TaskStatus] = None, assigned_to: Optional[str] = None
    ) -> Dict[str, List[Task]]:
        """
        Get tasks from all WMS connections.

        Args:
            status: Optional task status filter
            assigned_to: Optional worker filter

        Returns:
            Dict[str, List[Task]]: Tasks by connection ID
        """
        results = {}

        for connection_id, adapter in self.adapters.items():
            try:
                tasks = await adapter.get_tasks(status, assigned_to)
                results[connection_id] = tasks
            except Exception as e:
                self.logger.error(f"Error getting tasks from {connection_id}: {e}")
                results[connection_id] = []

        return results

    async def create_task(self, connection_id: str, task: Task) -> str:
        """
        Create a task in a specific WMS connection.

        Args:
            connection_id: WMS connection identifier
            task: Task to create

        Returns:
            str: Created task ID
        """
        if connection_id not in self.adapters:
            raise ValueError(f"WMS connection not found: {connection_id}")

        adapter = self.adapters[connection_id]
        return await adapter.create_task(task)

    async def create_work_queue_entry(
        self,
        task_id: str,
        task_type: str,
        quantity: int,
        assigned_workers: Optional[List[str]] = None,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a work queue entry (simplified interface for task creation).

        Args:
            task_id: Task identifier
            task_type: Type of task (pick, pack, putaway, etc.)
            quantity: Quantity for the task
            assigned_workers: List of worker IDs assigned to the task
            constraints: Additional constraints (zone, priority, etc.)

        Returns:
            Dict with success status and task information
        """
        try:
            # If no WMS connections are available, return a success response
            # This allows the system to work without a WMS connection
            if not self.adapters:
                self.logger.warning(
                    f"No WMS connections available - task {task_id} created locally only"
                )
                return {
                    "success": True,
                    "task_id": task_id,
                    "task_type": task_type,
                    "quantity": quantity,
                    "assigned_workers": assigned_workers or [],
                    "status": "pending",
                    "message": "Task created locally (no WMS connection available)",
                }

            # Try to create task in the first available WMS connection
            # In a production system, you might want to route to a specific connection
            connection_id = list(self.adapters.keys())[0]
            adapter = self.adapters[connection_id]

            # Create Task object from parameters
            task_type_enum = TaskType.PICK
            if task_type.lower() == "pack":
                task_type_enum = TaskType.PACK
            elif task_type.lower() == "putaway":
                task_type_enum = TaskType.PUTAWAY
            elif task_type.lower() == "receive":
                task_type_enum = TaskType.RECEIVE

            task = Task(
                task_id=task_id,
                task_type=task_type_enum,
                status=TaskStatus.PENDING,
                assigned_to=assigned_workers[0] if assigned_workers else None,
                location=constraints.get("zone") if constraints else None,
                priority=constraints.get("priority", "medium") if constraints else "medium",
                quantity=quantity,
                created_at=datetime.now(),
            )

            created_task_id = await adapter.create_task(task)

            return {
                "success": True,
                "task_id": created_task_id or task_id,
                "task_type": task_type,
                "quantity": quantity,
                "assigned_workers": assigned_workers or [],
                "status": "queued",
                "connection_id": connection_id,
            }

        except Exception as e:
            self.logger.error(f"Error creating work queue entry: {e}")
            # Return a graceful failure - task is still created locally
            return {
                "success": False,
                "task_id": task_id,
                "error": str(e),
                "status": "pending",
                "message": f"Task created locally but WMS integration failed: {str(e)}",
            }

    async def update_work_queue_entry(
        self,
        task_id: str,
        assigned_worker: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update a work queue entry.

        Args:
            task_id: Task identifier
            assigned_worker: Worker ID to assign
            status: New status for the task

        Returns:
            Dict with success status
        """
        try:
            if not self.adapters:
                return {
                    "success": False,
                    "error": "No WMS connections available",
                }

            # Try to update in the first available connection
            connection_id = list(self.adapters.keys())[0]
            adapter = self.adapters[connection_id]

            status_enum = None
            if status:
                status_map = {
                    "pending": TaskStatus.PENDING,
                    "assigned": TaskStatus.ASSIGNED,
                    "in_progress": TaskStatus.IN_PROGRESS,
                    "completed": TaskStatus.COMPLETED,
                    "cancelled": TaskStatus.CANCELLED,
                }
                status_enum = status_map.get(status.lower())

            result = await self.update_task_status(
                connection_id=connection_id,
                task_id=task_id,
                status=status_enum or TaskStatus.ASSIGNED,
                notes=f"Assigned to {assigned_worker}" if assigned_worker else None,
            )

            return {
                "success": result,
                "task_id": task_id,
                "assigned_worker": assigned_worker,
                "status": status,
            }

        except Exception as e:
            self.logger.error(f"Error updating work queue entry: {e}")
            return {
                "success": False,
                "task_id": task_id,
                "error": str(e),
            }

    async def get_work_queue_entries(
        self,
        task_id: Optional[str] = None,
        worker_id: Optional[str] = None,
        status: Optional[str] = None,
        task_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get work queue entries.

        Args:
            task_id: Specific task ID to retrieve
            worker_id: Filter by worker ID
            status: Filter by status
            task_type: Filter by task type

        Returns:
            List of work queue entries
        """
        try:
            if not self.adapters:
                return []

            status_enum = None
            if status:
                status_map = {
                    "pending": TaskStatus.PENDING,
                    "assigned": TaskStatus.ASSIGNED,
                    "in_progress": TaskStatus.IN_PROGRESS,
                    "completed": TaskStatus.COMPLETED,
                    "cancelled": TaskStatus.CANCELLED,
                }
                status_enum = status_map.get(status.lower())

            # Get tasks from all connections
            all_tasks = await self.get_tasks_all(status=status_enum, assigned_to=worker_id)

            # Convert to work queue entry format
            entries = []
            for connection_id, tasks in all_tasks.items():
                for task in tasks:
                    # Filter by task_id if specified
                    if task_id and task.task_id != task_id:
                        continue
                    # Filter by task_type if specified
                    if task_type and task.task_type.value.lower() != task_type.lower():
                        continue

                    entries.append({
                        "task_id": task.task_id,
                        "task_type": task.task_type.value,
                        "status": task.status.value,
                        "assigned_to": task.assigned_to,
                        "location": task.location,
                        "priority": task.priority,
                        "quantity": task.quantity,
                        "connection_id": connection_id,
                    })

            return entries

        except Exception as e:
            self.logger.error(f"Error getting work queue entries: {e}")
            return []

    async def update_task_status(
        self,
        connection_id: str,
        task_id: str,
        status: TaskStatus,
        notes: Optional[str] = None,
    ) -> bool:
        """
        Update task status in a specific WMS connection.

        Args:
            connection_id: WMS connection identifier
            task_id: Task ID to update
            status: New status
            notes: Optional notes

        Returns:
            bool: True if update successful
        """
        if connection_id not in self.adapters:
            raise ValueError(f"WMS connection not found: {connection_id}")

        adapter = self.adapters[connection_id]
        return await adapter.update_task_status(task_id, status, notes)

    async def get_orders(
        self,
        connection_id: str,
        status: Optional[str] = None,
        order_type: Optional[str] = None,
    ) -> List[Order]:
        """
        Get orders from a specific WMS connection.

        Args:
            connection_id: WMS connection identifier
            status: Optional order status filter
            order_type: Optional order type filter

        Returns:
            List[Order]: Orders
        """
        if connection_id not in self.adapters:
            raise ValueError(f"WMS connection not found: {connection_id}")

        adapter = self.adapters[connection_id]
        return await adapter.get_orders(status, order_type)

    async def create_order(self, connection_id: str, order: Order) -> str:
        """
        Create an order in a specific WMS connection.

        Args:
            connection_id: WMS connection identifier
            order: Order to create

        Returns:
            str: Created order ID
        """
        if connection_id not in self.adapters:
            raise ValueError(f"WMS connection not found: {connection_id}")

        adapter = self.adapters[connection_id]
        return await adapter.create_order(order)

    async def get_locations(
        self,
        connection_id: str,
        zone: Optional[str] = None,
        location_type: Optional[str] = None,
    ) -> List[Location]:
        """
        Get locations from a specific WMS connection.

        Args:
            connection_id: WMS connection identifier
            zone: Optional zone filter
            location_type: Optional location type filter

        Returns:
            List[Location]: Locations
        """
        if connection_id not in self.adapters:
            raise ValueError(f"WMS connection not found: {connection_id}")

        adapter = self.adapters[connection_id]
        return await adapter.get_locations(zone, location_type)

    async def sync_inventory(
        self,
        source_connection_id: str,
        target_connection_id: str,
        location: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Synchronize inventory between two WMS connections.

        Args:
            source_connection_id: Source WMS connection
            target_connection_id: Target WMS connection
            location: Optional location filter

        Returns:
            Dict[str, Any]: Synchronization results
        """
        try:
            # Get inventory from source
            source_inventory = await self.get_inventory(source_connection_id, location)

            # Update inventory in target
            success = await self.update_inventory(
                target_connection_id, source_inventory
            )

            return {
                "success": success,
                "items_synced": len(source_inventory),
                "source_connection": source_connection_id,
                "target_connection": target_connection_id,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.error(f"Error syncing inventory: {e}")
            return {
                "success": False,
                "error": str(e),
                "source_connection": source_connection_id,
                "target_connection": target_connection_id,
                "timestamp": datetime.now().isoformat(),
            }

    async def get_aggregated_inventory(
        self, location: Optional[str] = None, sku: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get aggregated inventory across all WMS connections.

        Args:
            location: Optional location filter
            sku: Optional SKU filter

        Returns:
            Dict[str, Any]: Aggregated inventory data
        """
        all_inventory = await self.get_inventory_all(location, sku)

        # Aggregate by SKU
        aggregated = {}
        total_items = 0

        for connection_id, inventory in all_inventory.items():
            for item in inventory:
                if item.sku not in aggregated:
                    aggregated[item.sku] = {
                        "sku": item.sku,
                        "name": item.name,
                        "total_quantity": 0,
                        "total_available": 0,
                        "total_reserved": 0,
                        "locations": {},
                        "connections": [],
                    }

                aggregated[item.sku]["total_quantity"] += item.quantity
                aggregated[item.sku]["total_available"] += item.available_quantity
                aggregated[item.sku]["total_reserved"] += item.reserved_quantity

                if item.location:
                    if item.location not in aggregated[item.sku]["locations"]:
                        aggregated[item.sku]["locations"][item.location] = 0
                    aggregated[item.sku]["locations"][item.location] += item.quantity

                if connection_id not in aggregated[item.sku]["connections"]:
                    aggregated[item.sku]["connections"].append(connection_id)

                total_items += 1

        return {
            "aggregated_inventory": list(aggregated.values()),
            "total_items": total_items,
            "total_skus": len(aggregated),
            "connections": list(self.adapters.keys()),
            "timestamp": datetime.now().isoformat(),
        }

    def list_connections(self) -> List[Dict[str, Any]]:
        """
        List all WMS connections.

        Returns:
            List[Dict[str, Any]]: Connection information
        """
        connections = []
        for connection_id, adapter in self.adapters.items():
            connections.append(
                {
                    "connection_id": connection_id,
                    "adapter_type": adapter.__class__.__name__,
                    "connected": adapter.connected,
                    "config_keys": list(adapter.config.keys()),
                }
            )
        return connections


# Global WMS integration service instance
wms_service = WMSIntegrationService()


async def get_wms_service() -> WMSIntegrationService:
    """Get the global WMS integration service instance."""
    return wms_service
