"""
MCP-Enabled Base Classes for Warehouse Operational Assistant

This module provides base classes for adapters and tools that integrate
with the Model Context Protocol (MCP) system.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Callable, Union
from dataclasses import dataclass
from enum import Enum
import json
from datetime import datetime

from .server import MCPServer, MCPTool, MCPToolType
from .client import MCPClient, MCPConnectionType

logger = logging.getLogger(__name__)


class MCPError(Exception):
    """Base exception for MCP-related errors."""
    pass


class AdapterType(Enum):
    """Types of adapters."""

    ERP = "erp"
    WMS = "wms"
    IoT = "iot"
    RFID = "rfid"
    ATTENDANCE = "attendance"
    EQUIPMENT = "equipment"
    OPERATIONS = "operations"
    SAFETY = "safety"
    FORECASTING = "forecasting"
    CUSTOM = "custom"


class ToolCategory(Enum):
    """Categories of tools."""

    DATA_ACCESS = "data_access"
    DATA_MODIFICATION = "data_modification"
    ANALYSIS = "analysis"
    REPORTING = "reporting"
    INTEGRATION = "integration"
    UTILITY = "utility"


@dataclass
class AdapterConfig:
    """Configuration for an adapter."""

    name: str = ""
    adapter_type: AdapterType = AdapterType.CUSTOM
    endpoint: str = ""
    connection_type: MCPConnectionType = MCPConnectionType.STDIO
    credentials: Dict[str, Any] = None
    timeout: int = 30
    retry_attempts: int = 3
    enabled: bool = True
    metadata: Dict[str, Any] = None


@dataclass
class ToolConfig:
    """Configuration for a tool."""

    name: str
    description: str
    category: ToolCategory
    parameters: Dict[str, Any]
    handler: Optional[Callable] = None
    enabled: bool = True
    metadata: Dict[str, Any] = None


class MCPAdapter(ABC):
    """
    Base class for MCP-enabled adapters.

    This class provides the foundation for all adapters that integrate
    with the MCP system, including ERP, WMS, IoT, and other external systems.
    """

    def __init__(self, config: AdapterConfig, mcp_client: Optional[MCPClient] = None):
        self.config = config
        self.mcp_client = mcp_client
        self.tools: Dict[str, MCPTool] = {}
        self.resources: Dict[str, Any] = {}
        self.prompts: Dict[str, Any] = {}
        self.connected = False
        self.last_health_check = None
        self.health_status = "unknown"

    @abstractmethod
    async def initialize(self) -> bool:
        """
        Initialize the adapter.

        Returns:
            bool: True if initialization successful, False otherwise
        """
        pass

    @abstractmethod
    async def connect(self) -> bool:
        """
        Connect to the external system.

        Returns:
            bool: True if connection successful, False otherwise
        """
        pass

    @abstractmethod
    async def disconnect(self) -> bool:
        """
        Disconnect from the external system.

        Returns:
            bool: True if disconnection successful, False otherwise
        """
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on the adapter.

        Returns:
            Dict[str, Any]: Health status information
        """
        pass

    async def register_tools(self, mcp_server: MCPServer) -> bool:
        """
        Register adapter tools with MCP server.

        Args:
            mcp_server: MCP server instance

        Returns:
            bool: True if registration successful, False otherwise
        """
        try:
            for tool in self.tools.values():
                success = mcp_server.register_tool(tool)
                if not success:
                    logger.error(f"Failed to register tool: {tool.name}")
                    return False

            logger.info(
                f"Registered {len(self.tools)} tools from adapter: {self.config.name}"
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to register tools for adapter '{self.config.name}': {e}"
            )
            return False

    async def register_resources(self, mcp_server: MCPServer) -> bool:
        """
        Register adapter resources with MCP server.

        Args:
            mcp_server: MCP server instance

        Returns:
            bool: True if registration successful, False otherwise
        """
        try:
            for name, resource in self.resources.items():
                success = mcp_server.register_resource(name, resource)
                if not success:
                    logger.error(f"Failed to register resource: {name}")
                    return False

            logger.info(
                f"Registered {len(self.resources)} resources from adapter: {self.config.name}"
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to register resources for adapter '{self.config.name}': {e}"
            )
            return False

    async def register_prompts(self, mcp_server: MCPServer) -> bool:
        """
        Register adapter prompts with MCP server.

        Args:
            mcp_server: MCP server instance

        Returns:
            bool: True if registration successful, False otherwise
        """
        try:
            for name, prompt in self.prompts.items():
                success = mcp_server.register_prompt(name, prompt)
                if not success:
                    logger.error(f"Failed to register prompt: {name}")
                    return False

            logger.info(
                f"Registered {len(self.prompts)} prompts from adapter: {self.config.name}"
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to register prompts for adapter '{self.config.name}': {e}"
            )
            return False

    def add_tool(self, tool_config: ToolConfig) -> bool:
        """
        Add a tool to the adapter.

        Args:
            tool_config: Tool configuration

        Returns:
            bool: True if tool added successfully, False otherwise
        """
        try:
            tool = MCPTool(
                name=tool_config.name,
                description=tool_config.description,
                tool_type=MCPToolType.FUNCTION,
                parameters=tool_config.parameters,
                handler=tool_config.handler,
            )

            self.tools[tool_config.name] = tool
            logger.info(f"Added tool: {tool_config.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to add tool '{tool_config.name}': {e}")
            return False

    def add_resource(self, name: str, resource: Any, description: str = "") -> bool:
        """
        Add a resource to the adapter.

        Args:
            name: Resource name
            resource: Resource data
            description: Resource description

        Returns:
            bool: True if resource added successfully, False otherwise
        """
        try:
            self.resources[name] = {
                "data": resource,
                "description": description,
                "created_at": datetime.utcnow().isoformat(),
            }
            logger.info(f"Added resource: {name}")
            return True

        except Exception as e:
            logger.error(f"Failed to add resource '{name}': {e}")
            return False

    def add_prompt(
        self,
        name: str,
        template: str,
        description: str = "",
        arguments: List[str] = None,
    ) -> bool:
        """
        Add a prompt to the adapter.

        Args:
            name: Prompt name
            template: Prompt template
            description: Prompt description
            arguments: List of argument names

        Returns:
            bool: True if prompt added successfully, False otherwise
        """
        try:
            self.prompts[name] = {
                "template": template,
                "description": description,
                "arguments": arguments or [],
                "created_at": datetime.utcnow().isoformat(),
            }
            logger.info(f"Added prompt: {name}")
            return True

        except Exception as e:
            logger.error(f"Failed to add prompt '{name}': {e}")
            return False

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Execute a tool by name.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            Any: Tool execution result
        """
        try:
            if tool_name not in self.tools:
                raise ValueError(f"Tool '{tool_name}' not found")

            tool = self.tools[tool_name]
            if not tool.handler:
                raise ValueError(f"Tool '{tool_name}' has no handler")

            return await tool.handler(arguments)

        except Exception as e:
            logger.error(f"Failed to execute tool '{tool_name}': {e}")
            raise

    def get_adapter_info(self) -> Dict[str, Any]:
        """Get adapter information."""
        return {
            "name": self.config.name,
            "type": self.config.adapter_type.value,
            "connected": self.connected,
            "health_status": self.health_status,
            "last_health_check": self.last_health_check,
            "tools_count": len(self.tools),
            "resources_count": len(self.resources),
            "prompts_count": len(self.prompts),
        }


class MCPToolBase(ABC):
    """
    Base class for MCP-enabled tools.

    This class provides the foundation for all tools that integrate
    with the MCP system.
    """

    def __init__(self, config: ToolConfig):
        self.config = config
        self.execution_count = 0
        self.last_execution = None
        self.error_count = 0

    @abstractmethod
    async def execute(self, arguments: Dict[str, Any]) -> Any:
        """
        Execute the tool with given arguments.

        Args:
            arguments: Tool arguments

        Returns:
            Any: Tool execution result
        """
        pass

    async def validate_arguments(self, arguments: Dict[str, Any]) -> bool:
        """
        Validate tool arguments.

        Args:
            arguments: Arguments to validate

        Returns:
            bool: True if arguments are valid, False otherwise
        """
        try:
            required_params = self.config.parameters.get("required", [])

            for param in required_params:
                if param not in arguments:
                    logger.error(f"Missing required parameter: {param}")
                    return False

            return True

        except Exception as e:
            logger.error(f"Argument validation failed: {e}")
            return False

    async def safe_execute(self, arguments: Dict[str, Any]) -> Any:
        """
        Safely execute the tool with error handling.

        Args:
            arguments: Tool arguments

        Returns:
            Any: Tool execution result
        """
        try:
            # Validate arguments
            if not await self.validate_arguments(arguments):
                raise ValueError("Invalid arguments")

            # Execute tool
            result = await self.execute(arguments)

            # Update statistics
            self.execution_count += 1
            self.last_execution = datetime.utcnow().isoformat()

            return result

        except Exception as e:
            self.error_count += 1
            logger.error(f"Tool execution failed: {e}")
            raise

    def get_tool_info(self) -> Dict[str, Any]:
        """Get tool information."""
        return {
            "name": self.config.name,
            "description": self.config.description,
            "category": self.config.category.value,
            "enabled": self.config.enabled,
            "execution_count": self.execution_count,
            "last_execution": self.last_execution,
            "error_count": self.error_count,
        }


class MCPManager:
    """
    Manager class for MCP system components.

    This class coordinates MCP servers, clients, and adapters.
    """

    def __init__(self):
        self.servers: Dict[str, MCPServer] = {}
        self.clients: Dict[str, MCPClient] = {}
        self.adapters: Dict[str, MCPAdapter] = {}
        self.tools: Dict[str, MCPToolBase] = {}

    async def create_server(self, name: str, version: str = "1.0.0") -> MCPServer:
        """
        Create a new MCP server.

        Args:
            name: Server name
            version: Server version

        Returns:
            MCPServer: Created server instance
        """
        server = MCPServer(name=name, version=version)
        self.servers[name] = server
        logger.info(f"Created MCP server: {name}")
        return server

    async def create_client(self, name: str, version: str = "1.0.0") -> MCPClient:
        """
        Create a new MCP client.

        Args:
            name: Client name
            version: Client version

        Returns:
            MCPClient: Created client instance
        """
        client = MCPClient(client_name=name, version=version)
        self.clients[name] = client
        logger.info(f"Created MCP client: {name}")
        return client

    def register_adapter(self, adapter: MCPAdapter) -> bool:
        """
        Register an adapter with the manager.

        Args:
            adapter: Adapter instance

        Returns:
            bool: True if registration successful, False otherwise
        """
        try:
            self.adapters[adapter.config.name] = adapter
            logger.info(f"Registered adapter: {adapter.config.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to register adapter: {e}")
            return False

    def register_tool(self, tool: MCPToolBase) -> bool:
        """
        Register a tool with the manager.

        Args:
            tool: Tool instance

        Returns:
            bool: True if registration successful, False otherwise
        """
        try:
            self.tools[tool.config.name] = tool
            logger.info(f"Registered tool: {tool.config.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to register tool: {e}")
            return False

    async def initialize_all(self) -> bool:
        """
        Initialize all registered components.

        Returns:
            bool: True if all components initialized successfully, False otherwise
        """
        try:
            # Initialize adapters
            for adapter in self.adapters.values():
                if not await adapter.initialize():
                    logger.error(f"Failed to initialize adapter: {adapter.config.name}")
                    return False

            # Register adapter tools with servers
            for server in self.servers.values():
                for adapter in self.adapters.values():
                    await adapter.register_tools(server)
                    await adapter.register_resources(server)
                    await adapter.register_prompts(server)

            logger.info("All components initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            return False

    def get_system_status(self) -> Dict[str, Any]:
        """Get overall system status."""
        return {
            "servers": len(self.servers),
            "clients": len(self.clients),
            "adapters": len(self.adapters),
            "tools": len(self.tools),
            "adapter_status": {
                name: adapter.get_adapter_info()
                for name, adapter in self.adapters.items()
            },
        }
