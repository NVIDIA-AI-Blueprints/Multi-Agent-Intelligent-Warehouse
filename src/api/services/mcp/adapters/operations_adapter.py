"""
MCP Adapter for Operations Action Tools

This adapter wraps the OperationsActionTools class to make it compatible
with the MCP (Model Context Protocol) system for tool discovery and execution.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, field

from src.api.services.mcp.base import (
    MCPAdapter,
    AdapterConfig,
    AdapterType,
    MCPTool,
    MCPToolType,
)
from src.api.services.mcp.client import MCPConnectionType
from src.api.agents.operations.action_tools import get_operations_action_tools

logger = logging.getLogger(__name__)


class OperationsAdapterConfig(AdapterConfig):
    """Configuration for Operations MCP Adapter."""

    adapter_type: AdapterType = field(default=AdapterType.OPERATIONS)
    name: str = field(default="operations_action_tools")
    endpoint: str = field(default="local://operations_tools")
    connection_type: MCPConnectionType = field(default=MCPConnectionType.STDIO)
    description: str = "Operations and task management tools"
    version: str = "1.0.0"
    enabled: bool = True
    timeout_seconds: int = 30
    retry_attempts: int = 3
    batch_size: int = 100


class OperationsMCPAdapter(MCPAdapter):
    """MCP Adapter for Operations Action Tools."""

    def __init__(self, config: OperationsAdapterConfig = None):
        super().__init__(config or OperationsAdapterConfig())
        self.operations_tools = None

    async def initialize(self) -> bool:
        """Initialize the adapter."""
        try:
            self.operations_tools = await get_operations_action_tools()
            await self._register_tools()
            logger.info("Operations MCP Adapter initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Operations MCP Adapter: {e}")
            return False

    async def connect(self) -> bool:
        """Connect to the operations tools service."""
        try:
            if self.operations_tools:
                self.connected = True
                logger.info("Operations MCP Adapter connected")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to connect Operations MCP Adapter: {e}")
            return False

    async def disconnect(self) -> bool:
        """Disconnect from the operations tools service."""
        try:
            self.connected = False
            logger.info("Operations MCP Adapter disconnected")
            return True
        except Exception as e:
            logger.error(f"Failed to disconnect Operations MCP Adapter: {e}")
            return False

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on the adapter."""
        try:
            if self.operations_tools:
                return {
                    "status": "healthy",
                    "timestamp": datetime.utcnow().isoformat(),
                    "tools_count": len(self.tools),
                    "connected": self.connected,
                }
            else:
                return {
                    "status": "unhealthy",
                    "timestamp": datetime.utcnow().isoformat(),
                    "error": "Operations tools not initialized",
                }
        except Exception as e:
            return {
                "status": "unhealthy",
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e),
            }

    async def _register_tools(self) -> None:
        """Register operations tools as MCP tools."""
        if not self.operations_tools:
            return

        # Register create_task tool
        self.tools["create_task"] = MCPTool(
            name="create_task",
            description="Create a new task for warehouse operations",
            tool_type=MCPToolType.FUNCTION,
            parameters={
                "type": "object",
                "properties": {
                    "task_type": {
                        "type": "string",
                        "description": "Type of task (pick, pack, putaway, etc.)",
                    },
                    "sku": {"type": "string", "description": "SKU for the task"},
                    "quantity": {
                        "type": "integer",
                        "description": "Quantity for the task",
                    },
                    "priority": {
                        "type": "string",
                        "description": "Task priority (high, medium, low)",
                    },
                    "zone": {"type": "string", "description": "Zone for the task"},
                },
                "required": ["task_type", "sku"],
            },
            handler=self._handle_create_task,
        )

        # Register assign_task tool
        self.tools["assign_task"] = MCPTool(
            name="assign_task",
            description="Assign a task to a worker",
            tool_type=MCPToolType.FUNCTION,
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID to assign"},
                    "worker_id": {
                        "type": "string",
                        "description": "Worker ID to assign task to",
                    },
                    "assignment_type": {
                        "type": "string",
                        "description": "Type of assignment (manual, automatic)",
                    },
                },
                "required": ["task_id", "worker_id"],
            },
            handler=self._handle_assign_task,
        )

        # Register get_task_status tool
        self.tools["get_task_status"] = MCPTool(
            name="get_task_status",
            description="Get status of tasks",
            tool_type=MCPToolType.FUNCTION,
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Specific task ID to check",
                    },
                    "worker_id": {
                        "type": "string",
                        "description": "Worker ID to get tasks for",
                    },
                    "status": {
                        "type": "string",
                        "description": "Filter by task status",
                    },
                    "task_type": {
                        "type": "string",
                        "description": "Filter by task type",
                    },
                },
            },
            handler=self._handle_get_task_status,
        )

        # Register get_workforce_status tool
        self.tools["get_workforce_status"] = MCPTool(
            name="get_workforce_status",
            description="Get workforce status and availability",
            tool_type=MCPToolType.FUNCTION,
            parameters={
                "type": "object",
                "properties": {
                    "worker_id": {
                        "type": "string",
                        "description": "Specific worker ID to check",
                    },
                    "shift": {
                        "type": "string",
                        "description": "Shift to check (day, night, etc.)",
                    },
                    "status": {
                        "type": "string",
                        "description": "Filter by worker status",
                    },
                },
            },
            handler=self._handle_get_workforce_status,
        )

        logger.info(f"Registered {len(self.tools)} operations tools")

    async def _handle_create_task(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle create_task tool execution."""
        try:
            result = await self.operations_tools.create_task(
                task_type=arguments["task_type"],
                sku=arguments["sku"],
                quantity=arguments.get("quantity", 1),
                priority=arguments.get("priority", "medium"),
                zone=arguments.get("zone"),
            )
            return result
        except Exception as e:
            logger.error(f"Error executing create_task: {e}")
            return {"error": str(e)}

    async def _handle_assign_task(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle assign_task tool execution."""
        try:
            result = await self.operations_tools.assign_task(
                task_id=arguments["task_id"],
                worker_id=arguments["worker_id"],
                assignment_type=arguments.get("assignment_type", "manual"),
            )
            return result
        except Exception as e:
            logger.error(f"Error executing assign_task: {e}")
            return {"error": str(e)}

    async def _handle_get_task_status(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle get_task_status tool execution."""
        try:
            result = await self.operations_tools.get_task_status(
                task_id=arguments.get("task_id"),
                worker_id=arguments.get("worker_id"),
                status=arguments.get("status"),
                task_type=arguments.get("task_type"),
            )
            return result
        except Exception as e:
            logger.error(f"Error executing get_task_status: {e}")
            return {"error": str(e)}

    async def _handle_get_workforce_status(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle get_workforce_status tool execution."""
        try:
            result = await self.operations_tools.get_workforce_status(
                worker_id=arguments.get("worker_id"),
                shift=arguments.get("shift"),
                status=arguments.get("status"),
            )
            return result
        except Exception as e:
            logger.error(f"Error executing get_workforce_status: {e}")
            return {"error": str(e)}


# Global instance
_operations_adapter: Optional[OperationsMCPAdapter] = None


async def get_operations_adapter() -> OperationsMCPAdapter:
    """Get the global operations adapter instance."""
    global _operations_adapter
    if _operations_adapter is None:
        config = OperationsAdapterConfig()
        _operations_adapter = OperationsMCPAdapter(config)
        await _operations_adapter.initialize()
    return _operations_adapter
