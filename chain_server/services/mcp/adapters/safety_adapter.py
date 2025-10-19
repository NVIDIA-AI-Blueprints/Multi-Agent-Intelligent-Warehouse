"""
MCP Adapter for Safety Action Tools

This adapter wraps the SafetyActionTools class to make it compatible
with the MCP (Model Context Protocol) system for tool discovery and execution.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, field

from chain_server.services.mcp.base import (
    MCPAdapter,
    AdapterConfig,
    AdapterType,
    MCPTool,
    MCPToolType,
)
from chain_server.services.mcp.client import MCPConnectionType
from chain_server.agents.safety.action_tools import get_safety_action_tools

logger = logging.getLogger(__name__)


class SafetyAdapterConfig(AdapterConfig):
    """Configuration for Safety MCP Adapter."""

    adapter_type: AdapterType = field(default=AdapterType.SAFETY)
    name: str = field(default="safety_action_tools")
    endpoint: str = field(default="local://safety_tools")
    connection_type: MCPConnectionType = field(default=MCPConnectionType.STDIO)
    description: str = "Safety and compliance management tools"
    version: str = "1.0.0"
    enabled: bool = True
    timeout_seconds: int = 30
    retry_attempts: int = 3
    batch_size: int = 100


class SafetyMCPAdapter(MCPAdapter):
    """MCP Adapter for Safety Action Tools."""

    def __init__(self, config: SafetyAdapterConfig = None):
        super().__init__(config or SafetyAdapterConfig())
        self.safety_tools = None

    async def initialize(self) -> bool:
        """Initialize the adapter."""
        try:
            self.safety_tools = await get_safety_action_tools()
            await self._register_tools()
            logger.info("Safety MCP Adapter initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Safety MCP Adapter: {e}")
            return False

    async def connect(self) -> bool:
        """Connect to the safety tools service."""
        try:
            if self.safety_tools:
                self.connected = True
                logger.info("Safety MCP Adapter connected")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to connect Safety MCP Adapter: {e}")
            return False

    async def disconnect(self) -> bool:
        """Disconnect from the safety tools service."""
        try:
            self.connected = False
            logger.info("Safety MCP Adapter disconnected")
            return True
        except Exception as e:
            logger.error(f"Failed to disconnect Safety MCP Adapter: {e}")
            return False

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on the adapter."""
        try:
            if self.safety_tools:
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
                    "error": "Safety tools not initialized",
                }
        except Exception as e:
            return {
                "status": "unhealthy",
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e),
            }

    async def _register_tools(self) -> None:
        """Register safety tools as MCP tools."""
        if not self.safety_tools:
            return

        # Register log_incident tool
        self.tools["log_incident"] = MCPTool(
            name="log_incident",
            description="Log a safety incident",
            tool_type=MCPToolType.FUNCTION,
            parameters={
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "description": "Incident severity (low, medium, high, critical)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Description of the incident",
                    },
                    "location": {
                        "type": "string",
                        "description": "Location where incident occurred",
                    },
                    "reporter": {
                        "type": "string",
                        "description": "Person reporting the incident",
                    },
                    "attachments": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of attachment file paths",
                    },
                },
                "required": ["severity", "description", "location", "reporter"],
            },
            handler=self._handle_log_incident,
        )

        # Register start_checklist tool
        self.tools["start_checklist"] = MCPTool(
            name="start_checklist",
            description="Start a safety checklist",
            tool_type=MCPToolType.FUNCTION,
            parameters={
                "type": "object",
                "properties": {
                    "checklist_type": {
                        "type": "string",
                        "description": "Type of checklist (daily, weekly, monthly, pre-shift)",
                    },
                    "assignee": {
                        "type": "string",
                        "description": "Person assigned to complete the checklist",
                    },
                    "due_in": {
                        "type": "integer",
                        "description": "Hours until checklist is due",
                    },
                },
                "required": ["checklist_type", "assignee"],
            },
            handler=self._handle_start_checklist,
        )

        # Register broadcast_alert tool
        self.tools["broadcast_alert"] = MCPTool(
            name="broadcast_alert",
            description="Broadcast a safety alert",
            tool_type=MCPToolType.FUNCTION,
            parameters={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Alert message to broadcast",
                    },
                    "zone": {
                        "type": "string",
                        "description": "Zone to broadcast to (all, specific zone)",
                    },
                    "channels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Channels to broadcast on (PA, email, SMS)",
                    },
                },
                "required": ["message"],
            },
            handler=self._handle_broadcast_alert,
        )

        # Register get_safety_procedures tool
        self.tools["get_safety_procedures"] = MCPTool(
            name="get_safety_procedures",
            description="Get safety procedures and policies",
            tool_type=MCPToolType.FUNCTION,
            parameters={
                "type": "object",
                "properties": {
                    "procedure_type": {
                        "type": "string",
                        "description": "Type of procedure (lockout_tagout, emergency, general)",
                    },
                    "category": {
                        "type": "string",
                        "description": "Category of procedure (equipment, chemical, emergency)",
                    },
                },
            },
            handler=self._handle_get_safety_procedures,
        )

        logger.info(f"Registered {len(self.tools)} safety tools")

    async def _handle_log_incident(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle log_incident tool execution."""
        try:
            result = await self.safety_tools.log_incident(
                severity=arguments["severity"],
                description=arguments["description"],
                location=arguments["location"],
                reporter=arguments["reporter"],
                attachments=arguments.get("attachments", []),
            )
            return {
                "incident": (
                    result.__dict__ if hasattr(result, "__dict__") else str(result)
                )
            }
        except Exception as e:
            logger.error(f"Error executing log_incident: {e}")
            return {"error": str(e)}

    async def _handle_start_checklist(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle start_checklist tool execution."""
        try:
            result = await self.safety_tools.start_checklist(
                checklist_type=arguments["checklist_type"],
                assignee=arguments["assignee"],
                due_in=arguments.get("due_in", 24),
            )
            return {
                "checklist": (
                    result.__dict__ if hasattr(result, "__dict__") else str(result)
                )
            }
        except Exception as e:
            logger.error(f"Error executing start_checklist: {e}")
            return {"error": str(e)}

    async def _handle_broadcast_alert(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle broadcast_alert tool execution."""
        try:
            result = await self.safety_tools.broadcast_alert(
                message=arguments["message"],
                zone=arguments.get("zone", "all"),
                channels=arguments.get("channels", ["PA"]),
            )
            return {
                "alert": result.__dict__ if hasattr(result, "__dict__") else str(result)
            }
        except Exception as e:
            logger.error(f"Error executing broadcast_alert: {e}")
            return {"error": str(e)}

    async def _handle_get_safety_procedures(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle get_safety_procedures tool execution."""
        try:
            result = await self.safety_tools.get_safety_procedures(
                procedure_type=arguments.get("procedure_type"),
                category=arguments.get("category"),
            )
            return {"procedures": result}
        except Exception as e:
            logger.error(f"Error executing get_safety_procedures: {e}")
            return {"error": str(e)}


# Global instance
_safety_adapter: Optional[SafetyMCPAdapter] = None


async def get_safety_adapter() -> SafetyMCPAdapter:
    """Get the global safety adapter instance."""
    global _safety_adapter
    if _safety_adapter is None:
        config = SafetyAdapterConfig()
        _safety_adapter = SafetyMCPAdapter(config)
        await _safety_adapter.initialize()
    return _safety_adapter
