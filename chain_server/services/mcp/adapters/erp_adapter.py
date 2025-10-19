"""
MCP-Enabled ERP Adapter

This module implements an ERP adapter that integrates with the Model Context Protocol (MCP)
system, providing tools for ERP system integration.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import json

from ..base import (
    MCPAdapter,
    AdapterConfig,
    AdapterType,
    ToolConfig,
    ToolCategory,
    MCPConnectionType,
)
from adapters.erp.base import BaseERPAdapter

logger = logging.getLogger(__name__)


class MCPERPAdapter(MCPAdapter):
    """
    MCP-enabled ERP adapter for Warehouse Operational Assistant.

    This adapter provides MCP tools for ERP system integration including:
    - Customer data access
    - Order management
    - Inventory synchronization
    - Financial data retrieval
    """

    def __init__(self, config: AdapterConfig, mcp_client: Optional[Any] = None):
        super().__init__(config, mcp_client)
        self.erp_adapter: Optional[BaseERPAdapter] = None
        self._setup_tools()
        self._setup_resources()
        self._setup_prompts()

    def _setup_tools(self):
        """Setup MCP tools for ERP operations."""
        # Customer data tools
        self.add_tool(
            ToolConfig(
                name="get_customer_info",
                description="Get customer information by ID",
                category=ToolCategory.DATA_ACCESS,
                parameters={
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "string", "description": "Customer ID"}
                    },
                    "required": ["customer_id"],
                },
                handler=self._handle_get_customer_info,
            )
        )

        self.add_tool(
            ToolConfig(
                name="search_customers",
                description="Search customers by criteria",
                category=ToolCategory.DATA_ACCESS,
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results",
                            "default": 50,
                        },
                    },
                    "required": ["query"],
                },
                handler=self._handle_search_customers,
            )
        )

        # Order management tools
        self.add_tool(
            ToolConfig(
                name="get_order_info",
                description="Get order information by ID",
                category=ToolCategory.DATA_ACCESS,
                parameters={
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string", "description": "Order ID"}
                    },
                    "required": ["order_id"],
                },
                handler=self._handle_get_order_info,
            )
        )

        self.add_tool(
            ToolConfig(
                name="create_order",
                description="Create a new order",
                category=ToolCategory.DATA_MODIFICATION,
                parameters={
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "string", "description": "Customer ID"},
                        "items": {
                            "type": "array",
                            "description": "Order items",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "product_id": {"type": "string"},
                                    "quantity": {"type": "number"},
                                    "price": {"type": "number"},
                                },
                            },
                        },
                        "notes": {"type": "string", "description": "Order notes"},
                    },
                    "required": ["customer_id", "items"],
                },
                handler=self._handle_create_order,
            )
        )

        self.add_tool(
            ToolConfig(
                name="update_order_status",
                description="Update order status",
                category=ToolCategory.DATA_MODIFICATION,
                parameters={
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string", "description": "Order ID"},
                        "status": {
                            "type": "string",
                            "description": "New status",
                            "enum": [
                                "pending",
                                "confirmed",
                                "shipped",
                                "delivered",
                                "cancelled",
                            ],
                        },
                    },
                    "required": ["order_id", "status"],
                },
                handler=self._handle_update_order_status,
            )
        )

        # Inventory synchronization tools
        self.add_tool(
            ToolConfig(
                name="sync_inventory",
                description="Synchronize inventory with ERP system",
                category=ToolCategory.INTEGRATION,
                parameters={
                    "type": "object",
                    "properties": {
                        "item_ids": {
                            "type": "array",
                            "description": "Item IDs to sync (empty for all)",
                            "items": {"type": "string"},
                        }
                    },
                },
                handler=self._handle_sync_inventory,
            )
        )

        self.add_tool(
            ToolConfig(
                name="get_inventory_levels",
                description="Get current inventory levels from ERP",
                category=ToolCategory.DATA_ACCESS,
                parameters={
                    "type": "object",
                    "properties": {
                        "warehouse_id": {
                            "type": "string",
                            "description": "Warehouse ID (optional)",
                        }
                    },
                },
                handler=self._handle_get_inventory_levels,
            )
        )

        # Financial data tools
        self.add_tool(
            ToolConfig(
                name="get_financial_summary",
                description="Get financial summary for a period",
                category=ToolCategory.DATA_ACCESS,
                parameters={
                    "type": "object",
                    "properties": {
                        "start_date": {
                            "type": "string",
                            "description": "Start date (YYYY-MM-DD)",
                        },
                        "end_date": {
                            "type": "string",
                            "description": "End date (YYYY-MM-DD)",
                        },
                    },
                    "required": ["start_date", "end_date"],
                },
                handler=self._handle_get_financial_summary,
            )
        )

        self.add_tool(
            ToolConfig(
                name="get_sales_report",
                description="Get sales report for a period",
                category=ToolCategory.REPORTING,
                parameters={
                    "type": "object",
                    "properties": {
                        "start_date": {
                            "type": "string",
                            "description": "Start date (YYYY-MM-DD)",
                        },
                        "end_date": {
                            "type": "string",
                            "description": "End date (YYYY-MM-DD)",
                        },
                        "group_by": {
                            "type": "string",
                            "description": "Group by field",
                            "enum": ["day", "week", "month", "customer", "product"],
                        },
                    },
                    "required": ["start_date", "end_date"],
                },
                handler=self._handle_get_sales_report,
            )
        )

    def _setup_resources(self):
        """Setup MCP resources for ERP data."""
        self.add_resource(
            "erp_config",
            {
                "endpoint": self.config.endpoint,
                "connection_type": self.config.connection_type.value,
                "timeout": self.config.timeout,
                "retry_attempts": self.config.retry_attempts,
            },
            "ERP system configuration",
        )

        self.add_resource(
            "supported_operations",
            [
                "customer_management",
                "order_management",
                "inventory_sync",
                "financial_reporting",
                "sales_analytics",
            ],
            "Supported ERP operations",
        )

    def _setup_prompts(self):
        """Setup MCP prompts for ERP operations."""
        self.add_prompt(
            "customer_query_prompt",
            "Find customer information for: {query}. Include customer ID, name, contact details, and order history.",
            "Prompt for customer data queries",
            ["query"],
        )

        self.add_prompt(
            "order_analysis_prompt",
            "Analyze order data for period {start_date} to {end_date}. Focus on: {analysis_type}. Provide insights and recommendations.",
            "Prompt for order analysis",
            ["start_date", "end_date", "analysis_type"],
        )

        self.add_prompt(
            "inventory_sync_prompt",
            "Synchronize inventory data for items: {item_ids}. Check for discrepancies and update warehouse system accordingly.",
            "Prompt for inventory synchronization",
            ["item_ids"],
        )

    async def initialize(self) -> bool:
        """Initialize the ERP adapter."""
        try:
            # Initialize base ERP adapter
            self.erp_adapter = BaseERPAdapter(
                endpoint=self.config.endpoint,
                credentials=self.config.credentials,
                timeout=self.config.timeout,
            )

            # Initialize base adapter
            if not await self.erp_adapter.initialize():
                logger.error("Failed to initialize base ERP adapter")
                return False

            logger.info(f"Initialized MCP ERP adapter: {self.config.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize ERP adapter: {e}")
            return False

    async def connect(self) -> bool:
        """Connect to the ERP system."""
        try:
            if not self.erp_adapter:
                logger.error("ERP adapter not initialized")
                return False

            if await self.erp_adapter.connect():
                self.connected = True
                self.health_status = "healthy"
                logger.info(f"Connected to ERP system: {self.config.name}")
                return True
            else:
                logger.error(f"Failed to connect to ERP system: {self.config.name}")
                return False

        except Exception as e:
            logger.error(f"Failed to connect to ERP system: {e}")
            return False

    async def disconnect(self) -> bool:
        """Disconnect from the ERP system."""
        try:
            if self.erp_adapter:
                await self.erp_adapter.disconnect()

            self.connected = False
            self.health_status = "disconnected"
            logger.info(f"Disconnected from ERP system: {self.config.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to disconnect from ERP system: {e}")
            return False

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on the ERP adapter."""
        try:
            if not self.erp_adapter:
                return {
                    "status": "unhealthy",
                    "message": "ERP adapter not initialized",
                    "timestamp": datetime.utcnow().isoformat(),
                }

            # Perform health check
            health_result = await self.erp_adapter.health_check()

            self.last_health_check = datetime.utcnow().isoformat()
            self.health_status = health_result.get("status", "unknown")

            return {
                "status": self.health_status,
                "message": health_result.get("message", "Health check completed"),
                "timestamp": self.last_health_check,
                "adapter": self.config.name,
                "tools_count": len(self.tools),
                "resources_count": len(self.resources),
            }

        except Exception as e:
            logger.error(f"Health check failed for ERP adapter: {e}")
            return {
                "status": "unhealthy",
                "message": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    # Tool handlers
    async def _handle_get_customer_info(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle get customer info tool."""
        try:
            customer_id = arguments["customer_id"]
            customer_info = await self.erp_adapter.get_customer(customer_id)

            return {
                "success": True,
                "data": customer_info,
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to get customer info: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def _handle_search_customers(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle search customers tool."""
        try:
            query = arguments["query"]
            limit = arguments.get("limit", 50)

            customers = await self.erp_adapter.search_customers(query, limit=limit)

            return {
                "success": True,
                "data": customers,
                "count": len(customers),
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to search customers: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def _handle_get_order_info(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle get order info tool."""
        try:
            order_id = arguments["order_id"]
            order_info = await self.erp_adapter.get_order(order_id)

            return {
                "success": True,
                "data": order_info,
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to get order info: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def _handle_create_order(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle create order tool."""
        try:
            customer_id = arguments["customer_id"]
            items = arguments["items"]
            notes = arguments.get("notes", "")

            order_data = {
                "customer_id": customer_id,
                "items": items,
                "notes": notes,
                "created_at": datetime.utcnow().isoformat(),
            }

            order_id = await self.erp_adapter.create_order(order_data)

            return {
                "success": True,
                "order_id": order_id,
                "data": order_data,
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to create order: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def _handle_update_order_status(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle update order status tool."""
        try:
            order_id = arguments["order_id"]
            status = arguments["status"]

            success = await self.erp_adapter.update_order_status(order_id, status)

            return {
                "success": success,
                "order_id": order_id,
                "new_status": status,
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to update order status: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def _handle_sync_inventory(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle sync inventory tool."""
        try:
            item_ids = arguments.get("item_ids", [])

            sync_result = await self.erp_adapter.sync_inventory(item_ids)

            return {
                "success": True,
                "data": sync_result,
                "items_synced": len(sync_result.get("synced_items", [])),
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to sync inventory: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def _handle_get_inventory_levels(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle get inventory levels tool."""
        try:
            warehouse_id = arguments.get("warehouse_id")

            inventory_levels = await self.erp_adapter.get_inventory_levels(warehouse_id)

            return {
                "success": True,
                "data": inventory_levels,
                "count": len(inventory_levels),
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to get inventory levels: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def _handle_get_financial_summary(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle get financial summary tool."""
        try:
            start_date = arguments["start_date"]
            end_date = arguments["end_date"]

            financial_data = await self.erp_adapter.get_financial_summary(
                start_date, end_date
            )

            return {
                "success": True,
                "data": financial_data,
                "period": f"{start_date} to {end_date}",
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to get financial summary: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def _handle_get_sales_report(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle get sales report tool."""
        try:
            start_date = arguments["start_date"]
            end_date = arguments["end_date"]
            group_by = arguments.get("group_by", "day")

            sales_report = await self.erp_adapter.get_sales_report(
                start_date, end_date, group_by
            )

            return {
                "success": True,
                "data": sales_report,
                "period": f"{start_date} to {end_date}",
                "group_by": group_by,
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to get sales report: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
