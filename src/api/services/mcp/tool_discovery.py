"""
Dynamic Tool Discovery and Registration System

This module provides dynamic tool discovery and registration capabilities
for the MCP system, allowing agents to automatically discover and use
tools from various MCP servers and adapters.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Set, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json
import uuid

from .server import MCPServer, MCPTool, MCPToolType
from .client import MCPClient, MCPConnectionType
from .base import MCPAdapter, MCPManager, AdapterType

logger = logging.getLogger(__name__)


class ToolDiscoveryStatus(Enum):
    """Tool discovery status."""

    DISCOVERING = "discovering"
    DISCOVERED = "discovered"
    REGISTERED = "registered"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class ToolCategory(Enum):
    """Tool categories for organization."""

    DATA_ACCESS = "data_access"
    DATA_MODIFICATION = "data_modification"
    ANALYSIS = "analysis"
    REPORTING = "reporting"
    INTEGRATION = "integration"
    UTILITY = "utility"
    SAFETY = "safety"
    EQUIPMENT = "equipment"
    OPERATIONS = "operations"
    FORECASTING = "forecasting"


@dataclass
class DiscoveredTool:
    """Represents a discovered tool."""

    name: str
    description: str
    category: ToolCategory
    source: str  # server name or adapter name
    source_type: str  # "mcp_server", "mcp_adapter", "external"
    parameters: Dict[str, Any]
    capabilities: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    discovery_time: datetime = field(default_factory=datetime.utcnow)
    last_used: Optional[datetime] = None
    usage_count: int = 0
    success_rate: float = 0.0
    average_response_time: float = 0.0
    status: ToolDiscoveryStatus = ToolDiscoveryStatus.DISCOVERED
    tool_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class ToolDiscoveryConfig:
    """Configuration for tool discovery."""

    discovery_interval: int = 30  # seconds
    max_discovery_attempts: int = 3
    discovery_timeout: int = 10  # seconds
    cache_duration: int = 300  # seconds
    enable_auto_registration: bool = True
    enable_usage_tracking: bool = True
    enable_performance_monitoring: bool = True
    categories_to_discover: List[ToolCategory] = field(
        default_factory=lambda: list(ToolCategory)
    )


class ToolDiscoveryService:
    """
    Service for dynamic tool discovery and registration.

    This service provides:
    - Automatic tool discovery from MCP servers and adapters
    - Tool registration and management
    - Usage tracking and performance monitoring
    - Tool categorization and filtering
    - Dynamic tool binding and execution
    """

    def __init__(self, config: ToolDiscoveryConfig = None):
        self.config = config or ToolDiscoveryConfig()
        self.discovered_tools: Dict[str, DiscoveredTool] = {}
        self.tool_categories: Dict[ToolCategory, List[str]] = {
            cat: [] for cat in ToolCategory
        }
        self.discovery_sources: Dict[str, Any] = {}
        self.discovery_tasks: Dict[str, asyncio.Task] = {}
        self.usage_stats: Dict[str, Dict[str, Any]] = {}
        self.performance_metrics: Dict[str, Dict[str, Any]] = {}
        self._discovery_lock = asyncio.Lock()
        self._running = False

    async def start_discovery(self) -> None:
        """Start the tool discovery service."""
        if self._running:
            logger.warning("Tool discovery service is already running")
            return

        self._running = True
        logger.info("Starting tool discovery service")

        # Start discovery tasks
        asyncio.create_task(self._discovery_loop())
        asyncio.create_task(self._cleanup_loop())

        # Initial discovery
        await self.discover_all_tools()

    async def stop_discovery(self) -> None:
        """Stop the tool discovery service."""
        self._running = False

        # Cancel all discovery tasks
        for task in self.discovery_tasks.values():
            task.cancel()

        self.discovery_tasks.clear()
        logger.info("Tool discovery service stopped")

    async def register_discovery_source(
        self, name: str, source: Any, source_type: str
    ) -> bool:
        """
        Register a discovery source (MCP server, adapter, etc.).

        Args:
            name: Source name
            source: Source object (MCP server, adapter, etc.)
            source_type: Type of source ("mcp_server", "mcp_adapter", "external")

        Returns:
            bool: True if registration successful, False otherwise
        """
        try:
            self.discovery_sources[name] = {
                "source": source,
                "type": source_type,
                "registered_at": datetime.utcnow(),
                "last_discovery": None,
                "discovery_count": 0,
            }

            logger.info(f"Registered discovery source: {name} ({source_type})")

            # Trigger immediate discovery for this source
            await self.discover_tools_from_source(name)

            return True

        except Exception as e:
            logger.error(f"Failed to register discovery source '{name}': {e}")
            return False

    async def discover_all_tools(self) -> Dict[str, int]:
        """
        Discover tools from all registered sources.

        Returns:
            Dict[str, int]: Discovery results by source
        """
        results = {}

        async with self._discovery_lock:
            for source_name in self.discovery_sources:
                try:
                    count = await self.discover_tools_from_source(source_name)
                    results[source_name] = count
                except Exception as e:
                    logger.error(
                        f"Failed to discover tools from source '{source_name}': {e}"
                    )
                    results[source_name] = 0

        total_discovered = sum(results.values())
        logger.info(
            f"Tool discovery completed: {total_discovered} tools discovered from {len(results)} sources"
        )

        return results

    async def discover_tools_from_source(self, source_name: str) -> int:
        """
        Discover tools from a specific source.

        Args:
            source_name: Name of the source to discover from

        Returns:
            int: Number of tools discovered
        """
        if source_name not in self.discovery_sources:
            logger.warning(f"Discovery source '{source_name}' not found")
            return 0

        source_info = self.discovery_sources[source_name]
        source = source_info["source"]
        source_type = source_info["type"]

        try:
            tools_discovered = 0

            if source_type == "mcp_server":
                tools_discovered = await self._discover_from_mcp_server(
                    source_name, source
                )
            elif source_type == "mcp_adapter":
                tools_discovered = await self._discover_from_mcp_adapter(
                    source_name, source
                )
            elif source_type == "external":
                tools_discovered = await self._discover_from_external_source(
                    source_name, source
                )
            else:
                logger.warning(f"Unknown source type: {source_type}")
                return 0

            # Update source info
            source_info["last_discovery"] = datetime.utcnow()
            source_info["discovery_count"] += 1

            logger.info(
                f"Discovered {tools_discovered} tools from source '{source_name}'"
            )
            return tools_discovered

        except Exception as e:
            logger.error(f"Failed to discover tools from source '{source_name}': {e}")
            return 0

    async def _discover_from_mcp_server(
        self, source_name: str, server: MCPServer
    ) -> int:
        """Discover tools from an MCP server."""
        tools_discovered = 0

        try:
            # Get tools from server
            tools = server.list_tools()

            for tool_info in tools:
                tool = server.get_tool(tool_info["name"])
                if tool:
                    discovered_tool = DiscoveredTool(
                        name=tool.name,
                        description=tool.description,
                        category=self._categorize_tool(tool.name, tool.description),
                        source=source_name,
                        source_type="mcp_server",
                        parameters=tool.parameters,
                        capabilities=self._extract_capabilities(tool),
                        metadata={
                            "tool_type": tool.tool_type.value,
                            "handler_available": tool.handler is not None,
                        },
                    )

                    await self._register_discovered_tool(discovered_tool)
                    tools_discovered += 1

        except Exception as e:
            logger.error(
                f"Failed to discover tools from MCP server '{source_name}': {e}"
            )

        return tools_discovered

    async def _discover_from_mcp_adapter(
        self, source_name: str, adapter: MCPAdapter
    ) -> int:
        """Discover tools from an MCP adapter."""
        tools_discovered = 0

        try:
            logger.info(f"Discovering tools from MCP adapter '{source_name}'")
            logger.info(f"Adapter type: {type(adapter)}")
            logger.info(f"Adapter has tools attribute: {hasattr(adapter, 'tools')}")

            if hasattr(adapter, "tools"):
                logger.info(f"Adapter tools count: {len(adapter.tools)}")
                logger.info(f"Adapter tools keys: {list(adapter.tools.keys())}")
            else:
                logger.error(f"Adapter '{source_name}' does not have 'tools' attribute")
                return 0

            # Get tools from adapter
            for tool_name, tool in adapter.tools.items():
                discovered_tool = DiscoveredTool(
                    name=tool.name,
                    description=tool.description,
                    category=self._categorize_tool(tool.name, tool.description),
                    source=source_name,
                    source_type="mcp_adapter",
                    parameters=tool.parameters,
                    capabilities=self._extract_capabilities(tool),
                    metadata={
                        "tool_type": tool.tool_type.value,
                        "adapter_type": adapter.config.adapter_type.value,
                        "handler_available": tool.handler is not None,
                    },
                )

                await self._register_discovered_tool(discovered_tool)
                tools_discovered += 1

        except Exception as e:
            logger.error(
                f"Failed to discover tools from MCP adapter '{source_name}': {e}"
            )

        return tools_discovered

    async def _discover_from_external_source(
        self, source_name: str, source: Any
    ) -> int:
        """Discover tools from an external source."""
        tools_discovered = 0

        try:
            # This would be implemented based on the specific external source
            # For now, we'll just log that external discovery is not implemented
            logger.info(
                f"External source discovery not implemented for '{source_name}'"
            )

        except Exception as e:
            logger.error(
                f"Failed to discover tools from external source '{source_name}': {e}"
            )

        return tools_discovered

    async def _register_discovered_tool(self, tool: DiscoveredTool) -> None:
        """Register a discovered tool."""
        tool_key = tool.tool_id

        # Update existing tool or add new one
        if tool_key in self.discovered_tools:
            existing_tool = self.discovered_tools[tool_key]
            existing_tool.description = tool.description
            existing_tool.parameters = tool.parameters
            existing_tool.capabilities = tool.capabilities
            existing_tool.metadata = tool.metadata
            existing_tool.discovery_time = tool.discovery_time
            existing_tool.status = ToolDiscoveryStatus.DISCOVERED
        else:
            self.discovered_tools[tool_key] = tool

        # Update category index
        if tool.category not in self.tool_categories:
            self.tool_categories[tool.category] = []

        if tool_key not in self.tool_categories[tool.category]:
            self.tool_categories[tool.category].append(tool_key)

        # Initialize usage stats
        if tool_key not in self.usage_stats:
            self.usage_stats[tool_key] = {
                "total_calls": 0,
                "successful_calls": 0,
                "failed_calls": 0,
                "total_response_time": 0.0,
                "last_called": None,
            }

        # Initialize performance metrics
        if tool_key not in self.performance_metrics:
            self.performance_metrics[tool_key] = {
                "average_response_time": 0.0,
                "success_rate": 0.0,
                "availability": 1.0,
                "last_health_check": None,
            }

    def _categorize_tool(self, name: str, description: str) -> ToolCategory:
        """Categorize a tool based on its name and description."""
        name_lower = name.lower()
        desc_lower = description.lower()

        # Safety tools
        if any(
            keyword in name_lower or keyword in desc_lower
            for keyword in [
                "safety",
                "incident",
                "alert",
                "emergency",
                "compliance",
                "sds",
                "loto",
            ]
        ):
            return ToolCategory.SAFETY

        # Equipment tools
        if any(
            keyword in name_lower or keyword in desc_lower
            for keyword in [
                "equipment",
                "forklift",
                "conveyor",
                "crane",
                "scanner",
                "charger",
                "battery",
            ]
        ):
            return ToolCategory.EQUIPMENT

        # Operations tools
        if any(
            keyword in name_lower or keyword in desc_lower
            for keyword in [
                "task",
                "workforce",
                "schedule",
                "pick",
                "wave",
                "dock",
                "kpi",
            ]
        ):
            return ToolCategory.OPERATIONS

        # Data access tools
        if any(
            keyword in name_lower or keyword in desc_lower
            for keyword in [
                "get",
                "retrieve",
                "fetch",
                "read",
                "list",
                "search",
                "find",
            ]
        ):
            return ToolCategory.DATA_ACCESS

        # Data modification tools
        if any(
            keyword in name_lower or keyword in desc_lower
            for keyword in [
                "create",
                "update",
                "modify",
                "delete",
                "add",
                "remove",
                "change",
            ]
        ):
            return ToolCategory.DATA_MODIFICATION

        # Analysis tools
        if any(
            keyword in name_lower or keyword in desc_lower
            for keyword in [
                "analyze",
                "analyze",
                "report",
                "summary",
                "statistics",
                "metrics",
            ]
        ):
            return ToolCategory.ANALYSIS

        # Integration tools
        if any(
            keyword in name_lower or keyword in desc_lower
            for keyword in ["sync", "integrate", "connect", "bridge", "link"]
        ):
            return ToolCategory.INTEGRATION

        # Default to utility
        return ToolCategory.UTILITY

    def _extract_capabilities(self, tool: MCPTool) -> List[str]:
        """Extract capabilities from a tool."""
        capabilities = []

        if tool.handler:
            capabilities.append("executable")

        if tool.parameters:
            capabilities.append("parameterized")

        if tool.tool_type == MCPToolType.FUNCTION:
            capabilities.append("function")
        elif tool.tool_type == MCPToolType.RESOURCE:
            capabilities.append("resource")
        elif tool.tool_type == MCPToolType.PROMPT:
            capabilities.append("prompt")

        return capabilities

    async def get_tools_by_category(
        self, category: ToolCategory
    ) -> List[DiscoveredTool]:
        """Get tools by category."""
        if category not in self.tool_categories:
            return []

        tools = []
        for tool_key in self.tool_categories[category]:
            if tool_key in self.discovered_tools:
                tools.append(self.discovered_tools[tool_key])

        return tools

    async def get_tools_by_source(self, source: str) -> List[DiscoveredTool]:
        """Get tools by source."""
        tools = []
        for tool in self.discovered_tools.values():
            if tool.source == source:
                tools.append(tool)

        return tools

    async def search_tools(
        self, query: str, category: Optional[ToolCategory] = None
    ) -> List[DiscoveredTool]:
        """Search tools by query."""
        query_lower = query.lower()
        results = []

        for tool in self.discovered_tools.values():
            if category and tool.category != category:
                continue

            if (
                query_lower in tool.name.lower()
                or query_lower in tool.description.lower()
                or any(query_lower in cap.lower() for cap in tool.capabilities)
            ):
                results.append(tool)

        # Sort by relevance (name matches first, then description)
        results.sort(
            key=lambda t: (
                query_lower not in t.name.lower(),
                query_lower not in t.description.lower(),
            )
        )

        return results

    async def get_available_tools(self) -> List[Dict[str, Any]]:
        """
        Get all available tools as dictionaries.

        Returns:
            List of tool dictionaries
        """
        try:
            tools = []
            for tool in self.discovered_tools.values():
                tools.append(
                    {
                        "tool_id": tool.tool_id,
                        "name": tool.name,
                        "description": tool.description,
                        "category": tool.category.value,
                        "source": tool.source,
                        "capabilities": tool.capabilities,
                        "metadata": tool.metadata,
                        "parameters": tool.parameters,  # Include parameters for UI
                    }
                )

            logger.info(f"Retrieved {len(tools)} available tools")
            return tools

        except Exception as e:
            logger.error(f"Error getting available tools: {e}")
            return []

    async def execute_tool(self, tool_key: str, arguments: Dict[str, Any]) -> Any:
        """Execute a discovered tool."""
        if tool_key not in self.discovered_tools:
            raise ValueError(f"Tool '{tool_key}' not found")

        tool = self.discovered_tools[tool_key]
        source_info = self.discovery_sources.get(tool.source)

        if not source_info:
            raise ValueError(f"Source '{tool.source}' not found")

        start_time = datetime.utcnow()

        try:
            # Execute tool based on source type
            if tool.source_type == "mcp_server":
                result = await source_info["source"].execute_tool(tool.name, arguments)
            elif tool.source_type == "mcp_adapter":
                result = await source_info["source"].execute_tool(tool.name, arguments)
            else:
                raise ValueError(f"Unsupported source type: {tool.source_type}")

            # Update usage stats
            await self._update_usage_stats(tool_key, True, start_time)

            return result

        except Exception as e:
            # Update usage stats
            await self._update_usage_stats(tool_key, False, start_time)
            raise

    async def _update_usage_stats(
        self, tool_key: str, success: bool, start_time: datetime
    ) -> None:
        """Update usage statistics for a tool."""
        if tool_key not in self.usage_stats:
            return

        stats = self.usage_stats[tool_key]
        response_time = (datetime.utcnow() - start_time).total_seconds()

        stats["total_calls"] += 1
        stats["total_response_time"] += response_time
        stats["last_called"] = datetime.utcnow()

        if success:
            stats["successful_calls"] += 1
        else:
            stats["failed_calls"] += 1

        # Update performance metrics
        if tool_key in self.performance_metrics:
            perf = self.performance_metrics[tool_key]
            perf["average_response_time"] = (
                stats["total_response_time"] / stats["total_calls"]
            )
            perf["success_rate"] = stats["successful_calls"] / stats["total_calls"]
            perf["last_health_check"] = datetime.utcnow()

    async def _discovery_loop(self) -> None:
        """Main discovery loop."""
        while self._running:
            try:
                await asyncio.sleep(self.config.discovery_interval)
                if self._running:
                    await self.discover_all_tools()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in discovery loop: {e}")

    async def _cleanup_loop(self) -> None:
        """Cleanup loop for old tools and stats."""
        while self._running:
            try:
                await asyncio.sleep(300)  # 5 minutes
                if self._running:
                    await self._cleanup_old_data()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

    async def _cleanup_old_data(self) -> None:
        """Clean up old data and tools."""
        cutoff_time = datetime.utcnow() - timedelta(seconds=self.config.cache_duration)

        # Remove old tools that haven't been discovered recently
        tools_to_remove = []
        for tool_key, tool in self.discovered_tools.items():
            if tool.discovery_time < cutoff_time and tool.usage_count == 0:
                tools_to_remove.append(tool_key)

        for tool_key in tools_to_remove:
            tool = self.discovered_tools[tool_key]
            if tool.category in self.tool_categories:
                self.tool_categories[tool.category] = [
                    t for t in self.tool_categories[tool.category] if t != tool_key
                ]
            del self.discovered_tools[tool_key]

        if tools_to_remove:
            logger.info(f"Cleaned up {len(tools_to_remove)} old tools")

    def get_discovery_status(self) -> Dict[str, Any]:
        """Get discovery service status."""
        return {
            "running": self._running,
            "total_tools": len(self.discovered_tools),
            "sources": len(self.discovery_sources),
            "categories": {
                cat.value: len(tools) for cat, tools in self.tool_categories.items()
            },
            "config": {
                "discovery_interval": self.config.discovery_interval,
                "max_discovery_attempts": self.config.max_discovery_attempts,
                "cache_duration": self.config.cache_duration,
            },
        }

    def get_tool_statistics(self) -> Dict[str, Any]:
        """Get tool usage statistics."""
        total_tools = len(self.discovered_tools)
        total_calls = sum(stats["total_calls"] for stats in self.usage_stats.values())
        successful_calls = sum(
            stats["successful_calls"] for stats in self.usage_stats.values()
        )

        return {
            "total_tools": total_tools,
            "total_calls": total_calls,
            "successful_calls": successful_calls,
            "success_rate": successful_calls / total_calls if total_calls > 0 else 0.0,
            "average_response_time": (
                sum(stats["total_response_time"] for stats in self.usage_stats.values())
                / total_calls
                if total_calls > 0
                else 0.0
            ),
            "tools_by_category": {
                cat.value: len(tools) for cat, tools in self.tool_categories.items()
            },
        }
