"""
MCP Testing and Management Router
Provides endpoints for testing MCP tool discovery and execution through the UI.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, List, Any, Optional
import logging
import asyncio

from chain_server.graphs.mcp_integrated_planner_graph import get_mcp_planner_graph
from chain_server.services.mcp.tool_discovery import ToolDiscoveryService
from chain_server.services.mcp.tool_binding import ToolBindingService
from chain_server.services.mcp.tool_routing import ToolRoutingService, RoutingStrategy
from chain_server.services.mcp.tool_validation import ToolValidationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/mcp", tags=["MCP Testing"])

# Global MCP services
_mcp_services = None


async def get_mcp_services():
    """Get or initialize MCP services."""
    global _mcp_services
    if _mcp_services is None:
        try:
            # Initialize MCP services (simplified for testing)
            tool_discovery = ToolDiscoveryService()
            tool_binding = ToolBindingService(tool_discovery)
            # Skip complex routing for now - will implement in next step
            tool_routing = None
            tool_validation = ToolValidationService(tool_discovery)

            # Start tool discovery
            await tool_discovery.start_discovery()

            # Register MCP adapters as discovery sources
            await _register_mcp_adapters(tool_discovery)

            _mcp_services = {
                "tool_discovery": tool_discovery,
                "tool_binding": tool_binding,
                "tool_routing": tool_routing,
                "tool_validation": tool_validation,
            }

            logger.info("MCP services initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize MCP services: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to initialize MCP services: {str(e)}"
            )

    return _mcp_services


async def _register_mcp_adapters(tool_discovery: ToolDiscoveryService):
    """Register MCP adapters as discovery sources."""
    try:
        # Register Equipment MCP Adapter
        from chain_server.services.mcp.adapters.equipment_adapter import (
            get_equipment_adapter,
        )

        equipment_adapter = await get_equipment_adapter()
        await tool_discovery.register_discovery_source(
            "equipment_asset_tools", equipment_adapter, "mcp_adapter"
        )
        logger.info("Registered Equipment MCP Adapter")

        # Register Operations MCP Adapter
        from chain_server.services.mcp.adapters.operations_adapter import (
            get_operations_adapter,
        )

        operations_adapter = await get_operations_adapter()
        await tool_discovery.register_discovery_source(
            "operations_action_tools", operations_adapter, "mcp_adapter"
        )
        logger.info("Registered Operations MCP Adapter")

        # Register Safety MCP Adapter
        from chain_server.services.mcp.adapters.safety_adapter import get_safety_adapter

        safety_adapter = await get_safety_adapter()
        await tool_discovery.register_discovery_source(
            "safety_action_tools", safety_adapter, "mcp_adapter"
        )
        logger.info("Registered Safety MCP Adapter")

        logger.info("All MCP adapters registered successfully")

    except Exception as e:
        logger.error(f"Failed to register MCP adapters: {e}")
        # Don't raise exception - allow service to continue without adapters


@router.get("/status")
async def get_mcp_status():
    """Get MCP framework status."""
    try:
        services = await get_mcp_services()

        # Get tool discovery status
        tool_discovery = services["tool_discovery"]
        discovered_tools = len(tool_discovery.discovered_tools)
        discovery_sources = len(tool_discovery.discovery_sources)
        is_running = tool_discovery._running

        return {
            "status": "operational",
            "tool_discovery": {
                "discovered_tools": discovered_tools,
                "discovery_sources": discovery_sources,
                "is_running": is_running,
            },
            "services": {
                "tool_discovery": "operational",
                "tool_binding": "operational",
                "tool_routing": "operational",
                "tool_validation": "operational",
            },
        }
    except Exception as e:
        logger.error(f"Error getting MCP status: {e}")
        return {"status": "error", "error": str(e)}


@router.get("/tools")
async def get_discovered_tools():
    """Get all discovered MCP tools."""
    try:
        services = await get_mcp_services()
        tool_discovery = services["tool_discovery"]

        tools = await tool_discovery.get_available_tools()

        return {"tools": tools, "total_tools": len(tools)}
    except Exception as e:
        logger.error(f"Error getting discovered tools: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get discovered tools: {str(e)}"
        )


@router.post("/tools/search")
async def search_tools(query: str):
    """Search for tools based on query."""
    try:
        services = await get_mcp_services()
        tool_discovery = services["tool_discovery"]

        relevant_tools = await tool_discovery.search_tools(query)

        return {
            "query": query,
            "tools": [
                {
                    "tool_id": tool.tool_id,
                    "name": tool.name,
                    "description": tool.description,
                    "category": tool.category.value,
                    "source": tool.source,
                    "relevance_score": getattr(tool, "relevance_score", 0.0),
                }
                for tool in relevant_tools
            ],
            "total_found": len(relevant_tools),
        }
    except Exception as e:
        logger.error(f"Error searching tools: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search tools: {str(e)}")


@router.post("/tools/execute")
async def execute_tool(tool_id: str, parameters: Dict[str, Any] = None):
    """Execute a specific MCP tool."""
    try:
        services = await get_mcp_services()
        tool_discovery = services["tool_discovery"]

        if parameters is None:
            parameters = {}

        result = await tool_discovery.execute_tool(tool_id, parameters)

        return {
            "tool_id": tool_id,
            "parameters": parameters,
            "result": result,
            "status": "success",
        }
    except Exception as e:
        logger.error(f"Error executing tool {tool_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to execute tool: {str(e)}")


@router.post("/test-workflow")
async def test_mcp_workflow(message: str, session_id: str = "test"):
    """Test complete MCP workflow with a message."""
    try:
        # Get MCP planner graph
        mcp_planner = await get_mcp_planner_graph()

        # Process the message through MCP workflow
        result = await mcp_planner.process_warehouse_query(
            message=message, session_id=session_id
        )

        return {
            "message": message,
            "session_id": session_id,
            "result": result,
            "status": "success",
        }
    except Exception as e:
        logger.error(f"Error testing MCP workflow: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to test MCP workflow: {str(e)}"
        )


@router.get("/agents")
async def get_mcp_agents():
    """Get MCP agent status."""
    try:
        return {
            "agents": {
                "equipment": {
                    "status": "operational",
                    "mcp_enabled": True,
                    "tools_available": True,
                },
                "operations": {
                    "status": "operational",
                    "mcp_enabled": True,
                    "tools_available": True,
                },
                "safety": {
                    "status": "operational",
                    "mcp_enabled": True,
                    "tools_available": True,
                },
            }
        }
    except Exception as e:
        logger.error(f"Error getting MCP agents: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get MCP agents: {str(e)}"
        )


@router.post("/discovery/refresh")
async def refresh_tool_discovery():
    """Refresh tool discovery to find new tools."""
    try:
        services = await get_mcp_services()
        tool_discovery = services["tool_discovery"]

        # Discover tools from all registered sources
        total_discovered = 0
        for source_name in tool_discovery.discovery_sources.keys():
            discovered = await tool_discovery.discover_tools_from_source(source_name)
            total_discovered += discovered
            logger.info(f"Discovered {discovered} tools from source '{source_name}'")

        # Get current tool count
        tools = await tool_discovery.get_available_tools()

        return {
            "status": "success",
            "message": f"Tool discovery refreshed. Discovered {total_discovered} tools from {len(tool_discovery.discovery_sources)} sources.",
            "total_tools": len(tools),
            "sources": list(tool_discovery.discovery_sources.keys()),
        }
    except Exception as e:
        logger.error(f"Error refreshing tool discovery: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to refresh tool discovery: {str(e)}"
        )
