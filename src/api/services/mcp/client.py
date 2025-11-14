"""
MCP (Model Context Protocol) Client Implementation

This module implements the MCP client for the Warehouse Operational Assistant,
providing tool discovery, execution, and communication capabilities.
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Callable, Union
from dataclasses import dataclass, asdict
from enum import Enum
import uuid
from datetime import datetime
import aiohttp
import websockets

logger = logging.getLogger(__name__)


class MCPConnectionType(Enum):
    """MCP connection types."""

    HTTP = "http"
    WEBSOCKET = "websocket"
    STDIO = "stdio"


@dataclass
class MCPToolInfo:
    """Information about an MCP tool."""

    name: str
    description: str
    input_schema: Dict[str, Any]
    server: str = None


@dataclass
class MCPResourceInfo:
    """Information about an MCP resource."""

    uri: str
    name: str
    mime_type: str
    server: str = None


@dataclass
class MCPPromptInfo:
    """Information about an MCP prompt."""

    name: str
    description: str
    arguments: List[Dict[str, Any]]
    server: str = None


class MCPClient:
    """
    MCP Client implementation for Warehouse Operational Assistant.

    This client provides:
    - Tool discovery and execution
    - Resource access
    - Prompt management
    - Multi-server communication
    """

    def __init__(
        self, client_name: str = "warehouse-assistant-client", version: str = "1.0.0"
    ):
        self.client_name = client_name
        self.version = version
        self.servers: Dict[str, Dict[str, Any]] = {}
        self.tools: Dict[str, MCPToolInfo] = {}
        self.resources: Dict[str, MCPResourceInfo] = {}
        self.prompts: Dict[str, MCPPromptInfo] = {}
        self.request_id_counter = 0
        self._pending_requests: Dict[str, asyncio.Future] = {}

    def _get_next_request_id(self) -> str:
        """Get next request ID."""
        self.request_id_counter += 1
        return str(self.request_id_counter)

    async def connect_server(
        self,
        server_name: str,
        connection_type: MCPConnectionType,
        endpoint: str,
        **kwargs,
    ) -> bool:
        """
        Connect to an MCP server.

        Args:
            server_name: Name identifier for the server
            connection_type: Type of connection (HTTP, WebSocket, STDIO)
            endpoint: Server endpoint URL
            **kwargs: Additional connection parameters

        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            server_info = {
                "name": server_name,
                "connection_type": connection_type,
                "endpoint": endpoint,
                "connected": False,
                "capabilities": {},
                "session": None,
                **kwargs,
            }

            if connection_type == MCPConnectionType.HTTP:
                server_info["session"] = aiohttp.ClientSession()
            elif connection_type == MCPConnectionType.WEBSOCKET:
                server_info["websocket"] = await websockets.connect(endpoint)

            # Initialize the connection
            init_result = await self._initialize_server(server_info)
            if init_result:
                server_info["connected"] = True
                self.servers[server_name] = server_info
                logger.info(f"Connected to MCP server: {server_name}")

                # Discover tools, resources, and prompts
                await self._discover_server_capabilities(server_name)
                return True
            else:
                logger.error(f"Failed to initialize server: {server_name}")
                return False

        except Exception as e:
            logger.error(f"Failed to connect to server '{server_name}': {e}")
            return False

    async def disconnect_server(self, server_name: str) -> bool:
        """
        Disconnect from an MCP server.

        Args:
            server_name: Name of the server to disconnect

        Returns:
            bool: True if disconnection successful, False otherwise
        """
        try:
            if server_name not in self.servers:
                logger.warning(f"Server '{server_name}' not found")
                return False

            server = self.servers[server_name]

            # Close connections
            if server["connection_type"] == MCPConnectionType.HTTP:
                if server["session"]:
                    await server["session"].close()
            elif server["connection_type"] == MCPConnectionType.WEBSOCKET:
                if server["websocket"]:
                    await server["websocket"].close()

            # Remove server
            del self.servers[server_name]

            # Remove tools, resources, and prompts from this server
            self.tools = {
                k: v for k, v in self.tools.items() if v.server != server_name
            }
            self.resources = {
                k: v for k, v in self.resources.items() if v.server != server_name
            }
            self.prompts = {
                k: v for k, v in self.prompts.items() if v.server != server_name
            }

            logger.info(f"Disconnected from MCP server: {server_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to disconnect from server '{server_name}': {e}")
            return False

    async def _initialize_server(self, server_info: Dict[str, Any]) -> bool:
        """Initialize connection with MCP server."""
        try:
            init_request = {
                "jsonrpc": "2.0",
                "id": self._get_next_request_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"roots": {"listChanged": True}, "sampling": {}},
                    "clientInfo": {"name": self.client_name, "version": self.version},
                },
            }

            response = await self._send_request(server_info, init_request)
            if response and "result" in response:
                server_info["capabilities"] = response["result"].get("capabilities", {})
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to initialize server: {e}")
            return False

    async def _discover_server_capabilities(self, server_name: str) -> None:
        """Discover tools, resources, and prompts from server."""
        try:
            # Discover tools
            await self._discover_tools(server_name)

            # Discover resources
            await self._discover_resources(server_name)

            # Discover prompts
            await self._discover_prompts(server_name)

        except Exception as e:
            logger.error(
                f"Failed to discover capabilities from server '{server_name}': {e}"
            )

    async def _discover_tools(self, server_name: str) -> None:
        """Discover tools from server."""
        try:
            request = {
                "jsonrpc": "2.0",
                "id": self._get_next_request_id(),
                "method": "tools/list",
                "params": {},
            }

            response = await self._send_request(self.servers[server_name], request)
            if response and "result" in response:
                tools = response["result"].get("tools", [])
                for tool_data in tools:
                    tool_info = MCPToolInfo(
                        name=tool_data["name"],
                        description=tool_data["description"],
                        input_schema=tool_data.get("inputSchema", {}),
                        server=server_name,
                    )
                    self.tools[tool_data["name"]] = tool_info

                logger.info(
                    f"Discovered {len(tools)} tools from server '{server_name}'"
                )

        except Exception as e:
            logger.error(f"Failed to discover tools from server '{server_name}': {e}")

    async def _discover_resources(self, server_name: str) -> None:
        """Discover resources from server."""
        try:
            request = {
                "jsonrpc": "2.0",
                "id": self._get_next_request_id(),
                "method": "resources/list",
                "params": {},
            }

            response = await self._send_request(self.servers[server_name], request)
            if response and "result" in response:
                resources = response["result"].get("resources", [])
                for resource_data in resources:
                    resource_info = MCPResourceInfo(
                        uri=resource_data["uri"],
                        name=resource_data["name"],
                        mime_type=resource_data.get("mimeType", "application/json"),
                        server=server_name,
                    )
                    self.resources[resource_data["name"]] = resource_info

                logger.info(
                    f"Discovered {len(resources)} resources from server '{server_name}'"
                )

        except Exception as e:
            logger.error(
                f"Failed to discover resources from server '{server_name}': {e}"
            )

    async def _discover_prompts(self, server_name: str) -> None:
        """Discover prompts from server."""
        try:
            request = {
                "jsonrpc": "2.0",
                "id": self._get_next_request_id(),
                "method": "prompts/list",
                "params": {},
            }

            response = await self._send_request(self.servers[server_name], request)
            if response and "result" in response:
                prompts = response["result"].get("prompts", [])
                for prompt_data in prompts:
                    prompt_info = MCPPromptInfo(
                        name=prompt_data["name"],
                        description=prompt_data["description"],
                        arguments=prompt_data.get("arguments", []),
                        server=server_name,
                    )
                    self.prompts[prompt_data["name"]] = prompt_info

                logger.info(
                    f"Discovered {len(prompts)} prompts from server '{server_name}'"
                )

        except Exception as e:
            logger.error(f"Failed to discover prompts from server '{server_name}': {e}")

    async def _send_request(
        self, server_info: Dict[str, Any], request: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Send request to MCP server."""
        try:
            request_id = request["id"]

            if server_info["connection_type"] == MCPConnectionType.HTTP:
                return await self._send_http_request(server_info, request)
            elif server_info["connection_type"] == MCPConnectionType.WEBSOCKET:
                return await self._send_websocket_request(server_info, request)
            else:
                raise ValueError(
                    f"Unsupported connection type: {server_info['connection_type']}"
                )

        except Exception as e:
            logger.error(f"Failed to send request: {e}")
            return None

    async def _send_http_request(
        self, server_info: Dict[str, Any], request: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Send HTTP request to MCP server."""
        try:
            session = server_info["session"]
            endpoint = server_info["endpoint"]

            async with session.post(endpoint, json=request) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"HTTP request failed with status {response.status}")
                    return None

        except Exception as e:
            logger.error(f"HTTP request failed: {e}")
            return None

    async def _send_websocket_request(
        self, server_info: Dict[str, Any], request: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Send WebSocket request to MCP server."""
        try:
            websocket = server_info["websocket"]

            # Send request
            await websocket.send(json.dumps(request))

            # Wait for response
            response_text = await websocket.recv()
            return json.loads(response_text)

        except Exception as e:
            logger.error(f"WebSocket request failed: {e}")
            return None

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Call a tool by name with arguments.

        Args:
            tool_name: Name of the tool to call
            arguments: Arguments to pass to the tool

        Returns:
            Any: Tool execution result
        """
        try:
            if tool_name not in self.tools:
                raise ValueError(f"Tool '{tool_name}' not found")

            tool_info = self.tools[tool_name]
            server_name = tool_info.server

            if server_name not in self.servers:
                raise ValueError(f"Server '{server_name}' not connected")

            request = {
                "jsonrpc": "2.0",
                "id": self._get_next_request_id(),
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            }

            response = await self._send_request(self.servers[server_name], request)
            if response and "result" in response:
                return response["result"]
            elif response and "error" in response:
                raise Exception(f"Tool execution error: {response['error']}")
            else:
                raise Exception("Invalid response from tool execution")

        except Exception as e:
            logger.error(f"Failed to call tool '{tool_name}': {e}")
            raise

    async def read_resource(self, resource_name: str) -> Any:
        """
        Read a resource by name.

        Args:
            resource_name: Name of the resource to read

        Returns:
            Any: Resource content
        """
        try:
            if resource_name not in self.resources:
                raise ValueError(f"Resource '{resource_name}' not found")

            resource_info = self.resources[resource_name]
            server_name = resource_info.server

            if server_name not in self.servers:
                raise ValueError(f"Server '{server_name}' not connected")

            request = {
                "jsonrpc": "2.0",
                "id": self._get_next_request_id(),
                "method": "resources/read",
                "params": {"uri": resource_info.uri},
            }

            response = await self._send_request(self.servers[server_name], request)
            if response and "result" in response:
                return response["result"]
            elif response and "error" in response:
                raise Exception(f"Resource read error: {response['error']}")
            else:
                raise Exception("Invalid response from resource read")

        except Exception as e:
            logger.error(f"Failed to read resource '{resource_name}': {e}")
            raise

    async def get_prompt(
        self, prompt_name: str, arguments: Dict[str, Any] = None
    ) -> Any:
        """
        Get a prompt by name with arguments.

        Args:
            prompt_name: Name of the prompt to get
            arguments: Arguments to pass to the prompt

        Returns:
            Any: Prompt content
        """
        try:
            if prompt_name not in self.prompts:
                raise ValueError(f"Prompt '{prompt_name}' not found")

            prompt_info = self.prompts[prompt_name]
            server_name = prompt_info.server

            if server_name not in self.servers:
                raise ValueError(f"Server '{server_name}' not connected")

            request = {
                "jsonrpc": "2.0",
                "id": self._get_next_request_id(),
                "method": "prompts/get",
                "params": {"name": prompt_name, "arguments": arguments or {}},
            }

            response = await self._send_request(self.servers[server_name], request)
            if response and "result" in response:
                return response["result"]
            elif response and "error" in response:
                raise Exception(f"Prompt get error: {response['error']}")
            else:
                raise Exception("Invalid response from prompt get")

        except Exception as e:
            logger.error(f"Failed to get prompt '{prompt_name}': {e}")
            raise

    def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "server": tool.server,
                "input_schema": tool.input_schema,
            }
            for tool in self.tools.values()
        ]

    def list_resources(self) -> List[Dict[str, Any]]:
        """List all available resources."""
        return [
            {
                "name": resource.name,
                "uri": resource.uri,
                "mime_type": resource.mime_type,
                "server": resource.server,
            }
            for resource in self.resources.values()
        ]

    def list_prompts(self) -> List[Dict[str, Any]]:
        """List all available prompts."""
        return [
            {
                "name": prompt.name,
                "description": prompt.description,
                "arguments": prompt.arguments,
                "server": prompt.server,
            }
            for prompt in self.prompts.values()
        ]

    def get_client_info(self) -> Dict[str, Any]:
        """Get client information."""
        return {
            "name": self.client_name,
            "version": self.version,
            "connected_servers": len(self.servers),
            "available_tools": len(self.tools),
            "available_resources": len(self.resources),
            "available_prompts": len(self.prompts),
        }
