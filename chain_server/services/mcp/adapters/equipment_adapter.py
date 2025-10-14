"""
MCP Adapter for Equipment Asset Tools

This adapter wraps the EquipmentAssetTools class to make it compatible
with the MCP (Model Context Protocol) system for tool discovery and execution.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

from chain_server.services.mcp.base import MCPAdapter, AdapterConfig, AdapterType, MCPTool, ToolType
from chain_server.agents.inventory.equipment_asset_tools import get_equipment_asset_tools

logger = logging.getLogger(__name__)

class EquipmentAdapterConfig(AdapterConfig):
    """Configuration for Equipment MCP Adapter."""
    adapter_type: AdapterType = AdapterType.EQUIPMENT
    name: str = "equipment_asset_tools"
    description: str = "Equipment and asset management tools"
    version: str = "1.0.0"
    enabled: bool = True
    timeout_seconds: int = 30
    retry_attempts: int = 3
    batch_size: int = 100

class EquipmentMCPAdapter(MCPAdapter):
    """MCP Adapter for Equipment Asset Tools."""
    
    def __init__(self, config: EquipmentAdapterConfig = None):
        super().__init__(config or EquipmentAdapterConfig())
        self.equipment_tools = None
        
    async def initialize(self) -> bool:
        """Initialize the adapter."""
        try:
            self.equipment_tools = await get_equipment_asset_tools()
            await self._register_tools()
            logger.info("Equipment MCP Adapter initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Equipment MCP Adapter: {e}")
            return False
    
    async def connect(self) -> bool:
        """Connect to the equipment tools service."""
        try:
            if self.equipment_tools:
                self.connected = True
                logger.info("Equipment MCP Adapter connected")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to connect Equipment MCP Adapter: {e}")
            return False
    
    async def disconnect(self) -> bool:
        """Disconnect from the equipment tools service."""
        try:
            self.connected = False
            logger.info("Equipment MCP Adapter disconnected")
            return True
        except Exception as e:
            logger.error(f"Failed to disconnect Equipment MCP Adapter: {e}")
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on the adapter."""
        try:
            if self.equipment_tools:
                return {
                    "status": "healthy",
                    "timestamp": datetime.utcnow().isoformat(),
                    "tools_count": len(self.tools),
                    "connected": self.connected
                }
            else:
                return {
                    "status": "unhealthy",
                    "timestamp": datetime.utcnow().isoformat(),
                    "error": "Equipment tools not initialized"
                }
        except Exception as e:
            return {
                "status": "unhealthy",
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e)
            }
    
    async def _register_tools(self) -> None:
        """Register equipment tools as MCP tools."""
        if not self.equipment_tools:
            return
            
        # Register get_equipment_status tool
        self.tools["get_equipment_status"] = MCPTool(
            name="get_equipment_status",
            description="Get equipment status and availability information",
            tool_type=ToolType.FUNCTION,
            parameters={
                "type": "object",
                "properties": {
                    "asset_id": {
                        "type": "string",
                        "description": "Specific equipment asset ID to check"
                    },
                    "equipment_type": {
                        "type": "string",
                        "description": "Type of equipment to check (forklift, scanner, etc.)"
                    },
                    "zone": {
                        "type": "string",
                        "description": "Zone to check equipment in"
                    },
                    "status": {
                        "type": "string",
                        "description": "Filter by equipment status"
                    }
                }
            },
            handler=self._handle_get_equipment_status
        )
        
        # Register assign_equipment tool
        self.tools["assign_equipment"] = MCPTool(
            name="assign_equipment",
            description="Assign equipment to a user or task",
            tool_type=ToolType.FUNCTION,
            parameters={
                "type": "object",
                "properties": {
                    "asset_id": {
                        "type": "string",
                        "description": "Equipment asset ID to assign"
                    },
                    "user_id": {
                        "type": "string",
                        "description": "User ID to assign equipment to"
                    },
                    "task_id": {
                        "type": "string",
                        "description": "Task ID to assign equipment to"
                    },
                    "assignment_type": {
                        "type": "string",
                        "description": "Type of assignment (user, task, maintenance)"
                    }
                },
                "required": ["asset_id"]
            },
            handler=self._handle_assign_equipment
        )
        
        # Register get_equipment_utilization tool
        self.tools["get_equipment_utilization"] = MCPTool(
            name="get_equipment_utilization",
            description="Get equipment utilization metrics and performance data",
            tool_type=ToolType.FUNCTION,
            parameters={
                "type": "object",
                "properties": {
                    "asset_id": {
                        "type": "string",
                        "description": "Specific equipment asset ID"
                    },
                    "equipment_type": {
                        "type": "string",
                        "description": "Type of equipment"
                    },
                    "time_period": {
                        "type": "string",
                        "description": "Time period for utilization data (day, week, month)"
                    }
                }
            },
            handler=self._handle_get_equipment_utilization
        )
        
        # Register get_maintenance_schedule tool
        self.tools["get_maintenance_schedule"] = MCPTool(
            name="get_maintenance_schedule",
            description="Get maintenance schedule and upcoming maintenance tasks",
            tool_type=ToolType.FUNCTION,
            parameters={
                "type": "object",
                "properties": {
                    "asset_id": {
                        "type": "string",
                        "description": "Specific equipment asset ID"
                    },
                    "maintenance_type": {
                        "type": "string",
                        "description": "Type of maintenance (preventive, corrective, emergency)"
                    },
                    "days_ahead": {
                        "type": "integer",
                        "description": "Number of days ahead to look for maintenance"
                    }
                }
            },
            handler=self._handle_get_maintenance_schedule
        )
        
        logger.info(f"Registered {len(self.tools)} equipment tools")
    
    async def _handle_get_equipment_status(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle get_equipment_status tool execution."""
        try:
            result = await self.equipment_tools.get_equipment_status(
                asset_id=arguments.get("asset_id"),
                equipment_type=arguments.get("equipment_type"),
                zone=arguments.get("zone"),
                status=arguments.get("status")
            )
            return result
        except Exception as e:
            logger.error(f"Error executing get_equipment_status: {e}")
            return {"error": str(e)}
    
    async def _handle_assign_equipment(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle assign_equipment tool execution."""
        try:
            result = await self.equipment_tools.assign_equipment(
                asset_id=arguments["asset_id"],
                user_id=arguments.get("user_id"),
                task_id=arguments.get("task_id"),
                assignment_type=arguments.get("assignment_type", "user")
            )
            return result
        except Exception as e:
            logger.error(f"Error executing assign_equipment: {e}")
            return {"error": str(e)}
    
    async def _handle_get_equipment_utilization(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle get_equipment_utilization tool execution."""
        try:
            result = await self.equipment_tools.get_equipment_utilization(
                asset_id=arguments.get("asset_id"),
                equipment_type=arguments.get("equipment_type"),
                time_period=arguments.get("time_period", "day")
            )
            return result
        except Exception as e:
            logger.error(f"Error executing get_equipment_utilization: {e}")
            return {"error": str(e)}
    
    async def _handle_get_maintenance_schedule(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle get_maintenance_schedule tool execution."""
        try:
            result = await self.equipment_tools.get_maintenance_schedule(
                asset_id=arguments.get("asset_id"),
                maintenance_type=arguments.get("maintenance_type"),
                days_ahead=arguments.get("days_ahead", 30)
            )
            return result
        except Exception as e:
            logger.error(f"Error executing get_maintenance_schedule: {e}")
            return {"error": str(e)}

# Global instance
_equipment_adapter: Optional[EquipmentMCPAdapter] = None

async def get_equipment_adapter() -> EquipmentMCPAdapter:
    """Get the global equipment adapter instance."""
    global _equipment_adapter
    if _equipment_adapter is None:
        _equipment_adapter = EquipmentMCPAdapter()
        await _equipment_adapter.initialize()
    return _equipment_adapter
