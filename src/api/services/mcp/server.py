"""
MCP (Model Context Protocol) Server Implementation

This module implements the MCP server for the Warehouse Operational Assistant,
providing tool registration, discovery, and execution capabilities.
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Callable, Union
from dataclasses import dataclass, asdict
from enum import Enum
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)


class MCPMessageType(Enum):
    """MCP message types."""

    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"


class MCPToolType(Enum):
    """MCP tool types."""

    FUNCTION = "function"
    RESOURCE = "resource"
    PROMPT = "prompt"


@dataclass
class MCPTool:
    """Represents an MCP tool."""

    name: str
    description: str
    tool_type: MCPToolType
    parameters: Dict[str, Any]
    handler: Optional[Callable] = None
    id: str = None

    def __post_init__(self):
        if self.id is None:
            self.id = str(uuid.uuid4())


@dataclass
class MCPRequest:
    """MCP request message."""

    id: str
    method: str
    params: Dict[str, Any] = None
    jsonrpc: str = "2.0"


@dataclass
class MCPResponse:
    """MCP response message."""

    id: str
    result: Any = None
    error: Dict[str, Any] = None
    jsonrpc: str = "2.0"


@dataclass
class MCPNotification:
    """MCP notification message."""

    method: str
    params: Dict[str, Any] = None
    jsonrpc: str = "2.0"


class MCPServer:
    """
    MCP Server implementation for Warehouse Operational Assistant.

    This server provides:
    - Tool registration and discovery
    - Tool execution and management
    - Protocol compliance with MCP specification
    - Error handling and validation
    """

    def __init__(self, name: str = "warehouse-assistant-mcp", version: str = "1.0.0"):
        self.name = name
        self.version = version
        self.tools: Dict[str, MCPTool] = {}
        self.resources: Dict[str, Any] = {}
        self.prompts: Dict[str, Any] = {}
        self.request_handlers: Dict[str, Callable] = {}
        self.notification_handlers: Dict[str, Callable] = {}
        self._setup_default_handlers()

    def _setup_default_handlers(self):
        """Setup default MCP protocol handlers."""
        self.request_handlers.update(
            {
                "tools/list": self._handle_tools_list,
                "tools/call": self._handle_tools_call,
                "resources/list": self._handle_resources_list,
                "resources/read": self._handle_resources_read,
                "prompts/list": self._handle_prompts_list,
                "prompts/get": self._handle_prompts_get,
                "initialize": self._handle_initialize,
                "ping": self._handle_ping,
            }
        )

        self.notification_handlers.update(
            {
                "notifications/initialized": self._handle_initialized,
                "tools/did_change": self._handle_tools_did_change,
            }
        )

    def register_tool(self, tool: MCPTool) -> bool:
        """
        Register a new tool with the MCP server.

        Args:
            tool: MCPTool instance to register

        Returns:
            bool: True if registration successful, False otherwise
        """
        try:
            if tool.name in self.tools:
                logger.warning(f"Tool '{tool.name}' already registered, updating...")

            self.tools[tool.name] = tool
            logger.info(f"Registered tool: {tool.name} ({tool.tool_type.value})")
            return True
        except Exception as e:
            logger.error(f"Failed to register tool '{tool.name}': {e}")
            return False

    def unregister_tool(self, tool_name: str) -> bool:
        """
        Unregister a tool from the MCP server.

        Args:
            tool_name: Name of the tool to unregister

        Returns:
            bool: True if unregistration successful, False otherwise
        """
        try:
            if tool_name in self.tools:
                del self.tools[tool_name]
                logger.info(f"Unregistered tool: {tool_name}")
                return True
            else:
                logger.warning(f"Tool '{tool_name}' not found for unregistration")
                return False
        except Exception as e:
            logger.error(f"Failed to unregister tool '{tool_name}': {e}")
            return False

    def register_resource(self, name: str, resource: Any) -> bool:
        """
        Register a resource with the MCP server.

        Args:
            name: Resource name
            resource: Resource data

        Returns:
            bool: True if registration successful, False otherwise
        """
        try:
            self.resources[name] = resource
            logger.info(f"Registered resource: {name}")
            return True
        except Exception as e:
            logger.error(f"Failed to register resource '{name}': {e}")
            return False

    def register_prompt(self, name: str, prompt: Any) -> bool:
        """
        Register a prompt with the MCP server.

        Args:
            name: Prompt name
            prompt: Prompt data

        Returns:
            bool: True if registration successful, False otherwise
        """
        try:
            self.prompts[name] = prompt
            logger.info(f"Registered prompt: {name}")
            return True
        except Exception as e:
            logger.error(f"Failed to register prompt '{name}': {e}")
            return False

    async def handle_message(self, message: Union[str, Dict]) -> Optional[str]:
        """
        Handle incoming MCP message.

        Args:
            message: MCP message (JSON string or dict)

        Returns:
            Optional[str]: Response message (JSON string) if applicable
        """
        try:
            if isinstance(message, str):
                data = json.loads(message)
            else:
                data = message

            # Determine message type
            if "id" in data and "method" in data:
                # Request message
                return await self._handle_request(data)
            elif "id" in data and ("result" in data or "error" in data):
                # Response message
                return await self._handle_response(data)
            elif "method" in data and "id" not in data:
                # Notification message
                return await self._handle_notification(data)
            else:
                raise ValueError("Invalid MCP message format")

        except Exception as e:
            logger.error(f"Failed to handle MCP message: {e}")
            error_response = MCPResponse(
                id="unknown",
                error={"code": -32600, "message": "Invalid Request", "data": str(e)},
            )
            return json.dumps(asdict(error_response))

    async def _handle_request(self, data: Dict) -> str:
        """Handle MCP request message."""
        request = MCPRequest(
            id=data["id"], method=data["method"], params=data.get("params", {})
        )

        handler = self.request_handlers.get(request.method)
        if not handler:
            error_response = MCPResponse(
                id=request.id, error={"code": -32601, "message": "Method not found"}
            )
            return json.dumps(asdict(error_response))

        try:
            result = await handler(request)
            response = MCPResponse(id=request.id, result=result)
            return json.dumps(asdict(response))
        except Exception as e:
            logger.error(f"Error handling request {request.method}: {e}")
            error_response = MCPResponse(
                id=request.id,
                error={"code": -32603, "message": "Internal error", "data": str(e)},
            )
            return json.dumps(asdict(error_response))

    async def _handle_response(self, data: Dict) -> None:
        """Handle MCP response message."""
        # For now, we don't handle responses in the server
        # This would be used in client implementations
        pass

    async def _handle_notification(self, data: Dict) -> None:
        """Handle MCP notification message."""
        notification = MCPNotification(
            method=data["method"], params=data.get("params", {})
        )

        handler = self.notification_handlers.get(notification.method)
        if handler:
            try:
                await handler(notification)
            except Exception as e:
                logger.error(f"Error handling notification {notification.method}: {e}")

    # Request handlers
    async def _handle_initialize(self, request: MCPRequest) -> Dict[str, Any]:
        """Handle initialize request."""
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": True},
                "resources": {"subscribe": True, "listChanged": True},
                "prompts": {"listChanged": True},
            },
            "serverInfo": {"name": self.name, "version": self.version},
        }

    async def _handle_ping(self, request: MCPRequest) -> str:
        """Handle ping request."""
        return "pong"

    async def _handle_tools_list(self, request: MCPRequest) -> Dict[str, Any]:
        """Handle tools/list request."""
        tools_list = []
        for tool in self.tools.values():
            tool_info = {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": {
                    "type": "object",
                    "properties": tool.parameters,
                    "required": list(tool.parameters.keys()),
                },
            }
            tools_list.append(tool_info)

        return {"tools": tools_list}

    async def _handle_tools_call(self, request: MCPRequest) -> Dict[str, Any]:
        """Handle tools/call request."""
        tool_name = request.params.get("name")
        arguments = request.params.get("arguments", {})

        if tool_name not in self.tools:
            raise ValueError(f"Tool '{tool_name}' not found")

        tool = self.tools[tool_name]
        if not tool.handler:
            raise ValueError(f"Tool '{tool_name}' has no handler")

        try:
            result = await tool.handler(arguments)
            return {"content": [{"type": "text", "text": str(result)}]}
        except Exception as e:
            logger.error(f"Error executing tool '{tool_name}': {e}")
            return {
                "content": [
                    {"type": "text", "text": f"Error executing tool: {str(e)}"}
                ],
                "isError": True,
            }

    async def _handle_resources_list(self, request: MCPRequest) -> Dict[str, Any]:
        """Handle resources/list request."""
        resources_list = []
        for name, resource in self.resources.items():
            resource_info = {
                "uri": f"warehouse://{name}",
                "name": name,
                "mimeType": "application/json",
            }
            resources_list.append(resource_info)

        return {"resources": resources_list}

    async def _handle_resources_read(self, request: MCPRequest) -> Dict[str, Any]:
        """Handle resources/read request."""
        uri = request.params.get("uri")
        if not uri.startswith("warehouse://"):
            raise ValueError("Invalid resource URI")

        resource_name = uri.replace("warehouse://", "")
        if resource_name not in self.resources:
            raise ValueError(f"Resource '{resource_name}' not found")

        resource = self.resources[resource_name]
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(resource, indent=2),
                }
            ]
        }

    async def _handle_prompts_list(self, request: MCPRequest) -> Dict[str, Any]:
        """Handle prompts/list request."""
        prompts_list = []
        for name, prompt in self.prompts.items():
            prompt_info = {
                "name": name,
                "description": prompt.get("description", ""),
                "arguments": prompt.get("arguments", []),
            }
            prompts_list.append(prompt_info)

        return {"prompts": prompts_list}

    async def _handle_prompts_get(self, request: MCPRequest) -> Dict[str, Any]:
        """Handle prompts/get request."""
        prompt_name = request.params.get("name")
        arguments = request.params.get("arguments", {})

        if prompt_name not in self.prompts:
            raise ValueError(f"Prompt '{prompt_name}' not found")

        prompt = self.prompts[prompt_name]
        # Process prompt with arguments
        prompt_text = prompt.get("template", "")
        for key, value in arguments.items():
            prompt_text = prompt_text.replace(f"{{{key}}}", str(value))

        return {
            "description": prompt.get("description", ""),
            "messages": [
                {"role": "user", "content": {"type": "text", "text": prompt_text}}
            ],
        }

    # Notification handlers
    async def _handle_initialized(self, notification: MCPNotification) -> None:
        """Handle initialized notification."""
        logger.info("MCP client initialized")

    async def _handle_tools_did_change(self, notification: MCPNotification) -> None:
        """Handle tools/did_change notification."""
        logger.info("Tools changed notification received")

    def get_server_info(self) -> Dict[str, Any]:
        """Get server information."""
        return {
            "name": self.name,
            "version": self.version,
            "tools_count": len(self.tools),
            "resources_count": len(self.resources),
            "prompts_count": len(self.prompts),
        }

    def list_tools(self) -> List[Dict[str, Any]]:
        """List all registered tools."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "type": tool.tool_type.value,
                "id": tool.id,
            }
            for tool in self.tools.values()
        ]

    def get_tool(self, name: str) -> Optional[MCPTool]:
        """Get a specific tool by name."""
        return self.tools.get(name)

    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a tool by name with arguments."""
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"Tool '{name}' not found")

        if not tool.handler:
            raise ValueError(f"Tool '{name}' has no handler")

        return await tool.handler(arguments)
