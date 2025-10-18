"""
MCP-Enabled Equipment & Asset Operations Agent

This agent integrates with the Model Context Protocol (MCP) system to provide
dynamic tool discovery and execution for equipment and asset operations.
"""

import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
import json
from datetime import datetime, timedelta
import asyncio

from chain_server.services.llm.nim_client import get_nim_client, LLMResponse
from inventory_retriever.hybrid_retriever import get_hybrid_retriever, SearchContext
from memory_retriever.memory_manager import get_memory_manager
from chain_server.services.mcp.tool_discovery import (
    ToolDiscoveryService,
    DiscoveredTool,
    ToolCategory,
)
from chain_server.services.mcp.base import MCPManager
from .equipment_asset_tools import get_equipment_asset_tools

logger = logging.getLogger(__name__)


@dataclass
class MCPEquipmentQuery:
    """MCP-enabled equipment query."""

    intent: str
    entities: Dict[str, Any]
    context: Dict[str, Any]
    user_query: str
    mcp_tools: List[str] = None  # Available MCP tools for this query
    tool_execution_plan: List[Dict[str, Any]] = None  # Planned tool executions


@dataclass
class MCPEquipmentResponse:
    """MCP-enabled equipment response."""

    response_type: str
    data: Dict[str, Any]
    natural_language: str
    recommendations: List[str]
    confidence: float
    actions_taken: List[Dict[str, Any]]
    mcp_tools_used: List[str] = None
    tool_execution_results: Dict[str, Any] = None


class MCPEquipmentAssetOperationsAgent:
    """
    MCP-enabled Equipment & Asset Operations Agent.

    This agent integrates with the Model Context Protocol (MCP) system to provide:
    - Dynamic tool discovery and execution
    - MCP-based tool binding and routing
    - Enhanced tool selection and validation
    - Comprehensive error handling and fallback mechanisms
    """

    def __init__(self):
        self.nim_client = None
        self.hybrid_retriever = None
        self.asset_tools = None
        self.mcp_manager = None
        self.tool_discovery = None
        self.conversation_context = {}
        self.mcp_tools_cache = {}
        self.tool_execution_history = []

    async def initialize(self) -> None:
        """Initialize the agent with required services including MCP."""
        try:
            self.nim_client = await get_nim_client()
            self.hybrid_retriever = await get_hybrid_retriever()
            self.asset_tools = await get_equipment_asset_tools()

            # Initialize MCP components
            self.mcp_manager = MCPManager()
            self.tool_discovery = ToolDiscoveryService()

            # Start tool discovery
            await self.tool_discovery.start_discovery()

            # Register MCP sources
            await self._register_mcp_sources()

            logger.info(
                "MCP-enabled Equipment & Asset Operations Agent initialized successfully"
            )
        except Exception as e:
            logger.error(
                f"Failed to initialize MCP Equipment & Asset Operations Agent: {e}"
            )
            raise

    async def _register_mcp_sources(self) -> None:
        """Register MCP sources for tool discovery."""
        try:
            # Import and register the equipment MCP adapter
            from chain_server.services.mcp.adapters.equipment_adapter import (
                get_equipment_adapter,
            )

            # Register the equipment adapter as an MCP source
            equipment_adapter = await get_equipment_adapter()
            await self.tool_discovery.register_discovery_source(
                "equipment_asset_tools", equipment_adapter, "mcp_adapter"
            )

            # Register any other MCP servers or adapters
            # This would be expanded based on available MCP sources

            logger.info("MCP sources registered successfully")
        except Exception as e:
            logger.error(f"Failed to register MCP sources: {e}")

    async def process_query(
        self,
        query: str,
        session_id: str = "default",
        context: Optional[Dict[str, Any]] = None,
        mcp_results: Optional[Any] = None,
    ) -> MCPEquipmentResponse:
        """
        Process an equipment/asset operations query with MCP integration.

        Args:
            query: User's equipment/asset query
            session_id: Session identifier for context
            context: Additional context
            mcp_results: Optional MCP execution results from planner graph

        Returns:
            MCPEquipmentResponse with MCP tool execution results
        """
        try:
            # Initialize if needed
            if (
                not self.nim_client
                or not self.hybrid_retriever
                or not self.tool_discovery
            ):
                await self.initialize()

            # Update conversation context
            if session_id not in self.conversation_context:
                self.conversation_context[session_id] = {
                    "queries": [],
                    "responses": [],
                    "context": {},
                }

            # Parse query and identify intent
            parsed_query = await self._parse_equipment_query(query, context)

            # Use MCP results if provided, otherwise discover tools
            if mcp_results and hasattr(mcp_results, "tool_results"):
                # Use results from MCP planner graph
                tool_results = mcp_results.tool_results
                parsed_query.mcp_tools = (
                    list(tool_results.keys()) if tool_results else []
                )
                parsed_query.tool_execution_plan = []
            else:
                # Discover available MCP tools for this query
                available_tools = await self._discover_relevant_tools(parsed_query)
                parsed_query.mcp_tools = [tool.tool_id for tool in available_tools]

                # Create tool execution plan
                execution_plan = await self._create_tool_execution_plan(
                    parsed_query, available_tools
                )
                parsed_query.tool_execution_plan = execution_plan

                # Execute tools and gather results
                tool_results = await self._execute_tool_plan(execution_plan)

            # Generate response using LLM with tool results
            response = await self._generate_response_with_tools(
                parsed_query, tool_results
            )

            # Update conversation context
            self.conversation_context[session_id]["queries"].append(parsed_query)
            self.conversation_context[session_id]["responses"].append(response)

            return response

        except Exception as e:
            logger.error(f"Error processing equipment query: {e}")
            return MCPEquipmentResponse(
                response_type="error",
                data={"error": str(e)},
                natural_language=f"I encountered an error processing your request: {str(e)}",
                recommendations=[
                    "Please try rephrasing your question or contact support if the issue persists."
                ],
                confidence=0.0,
                actions_taken=[],
                mcp_tools_used=[],
                tool_execution_results={},
            )

    async def _parse_equipment_query(
        self, query: str, context: Optional[Dict[str, Any]]
    ) -> MCPEquipmentQuery:
        """Parse equipment query and extract intent and entities."""
        try:
            # Use LLM to parse the query
            parse_prompt = [
                {
                    "role": "system",
                    "content": """You are an equipment operations expert. Parse warehouse queries and extract intent, entities, and context.

Return JSON format:
{
    "intent": "equipment_lookup",
    "entities": {"equipment_id": "EQ001", "equipment_type": "forklift"},
    "context": {"priority": "high", "zone": "A"}
}

Intent options: equipment_lookup, equipment_dispatch, equipment_assignment, equipment_utilization, equipment_maintenance, equipment_availability, equipment_telemetry, equipment_safety

Examples:
- "Show me forklift FL-001" → {"intent": "equipment_lookup", "entities": {"equipment_id": "FL-001", "equipment_type": "forklift"}}
- "Dispatch forklift FL-01 to Zone A" → {"intent": "equipment_dispatch", "entities": {"equipment_id": "FL-01", "equipment_type": "forklift", "destination": "Zone A"}}
- "Assign loader L-003 to task T-456" → {"intent": "equipment_assignment", "entities": {"equipment_id": "L-003", "equipment_type": "loader", "task_id": "T-456"}}

Return only valid JSON.""",
                },
                {
                    "role": "user",
                    "content": f'Query: "{query}"\nContext: {context or {}}',
                },
            ]

            response = await self.nim_client.generate_response(parse_prompt)

            # Parse JSON response
            try:
                parsed_data = json.loads(response.content)
            except json.JSONDecodeError:
                # Fallback parsing
                parsed_data = {
                    "intent": "equipment_lookup",
                    "entities": {},
                    "context": {},
                }

            return MCPEquipmentQuery(
                intent=parsed_data.get("intent", "equipment_lookup"),
                entities=parsed_data.get("entities", {}),
                context=parsed_data.get("context", {}),
                user_query=query,
            )

        except Exception as e:
            logger.error(f"Error parsing equipment query: {e}")
            return MCPEquipmentQuery(
                intent="equipment_lookup", entities={}, context={}, user_query=query
            )

    async def _discover_relevant_tools(
        self, query: MCPEquipmentQuery
    ) -> List[DiscoveredTool]:
        """Discover MCP tools relevant to the query."""
        try:
            # Search for tools based on query intent and entities
            search_terms = [query.intent]

            # Add entity-based search terms
            for entity_type, entity_value in query.entities.items():
                search_terms.append(f"{entity_type}_{entity_value}")

            # Search for tools
            relevant_tools = []

            # Search by category based on intent
            category_mapping = {
                "equipment_lookup": ToolCategory.EQUIPMENT,
                "assignment": ToolCategory.OPERATIONS,
                "utilization": ToolCategory.ANALYSIS,
                "maintenance": ToolCategory.OPERATIONS,
                "availability": ToolCategory.EQUIPMENT,
                "telemetry": ToolCategory.EQUIPMENT,
                "safety": ToolCategory.SAFETY,
            }

            intent_category = category_mapping.get(
                query.intent, ToolCategory.DATA_ACCESS
            )
            category_tools = await self.tool_discovery.get_tools_by_category(
                intent_category
            )
            relevant_tools.extend(category_tools)

            # Search by keywords
            for term in search_terms:
                keyword_tools = await self.tool_discovery.search_tools(term)
                relevant_tools.extend(keyword_tools)

            # Remove duplicates and sort by relevance
            unique_tools = {}
            for tool in relevant_tools:
                if tool.tool_id not in unique_tools:
                    unique_tools[tool.tool_id] = tool

            # Sort by usage count and success rate
            sorted_tools = sorted(
                unique_tools.values(),
                key=lambda t: (t.usage_count, t.success_rate),
                reverse=True,
            )

            return sorted_tools[:10]  # Return top 10 most relevant tools

        except Exception as e:
            logger.error(f"Error discovering relevant tools: {e}")
            return []

    async def _create_tool_execution_plan(
        self, query: MCPEquipmentQuery, tools: List[DiscoveredTool]
    ) -> List[Dict[str, Any]]:
        """Create a plan for executing MCP tools."""
        try:
            execution_plan = []

            # Create execution steps based on query intent
            if query.intent == "equipment_lookup":
                # Look for equipment tools
                equipment_tools = [
                    t for t in tools if t.category == ToolCategory.EQUIPMENT
                ]
                for tool in equipment_tools[:3]:  # Limit to 3 tools
                    execution_plan.append(
                        {
                            "tool_id": tool.tool_id,
                            "tool_name": tool.name,
                            "arguments": self._prepare_tool_arguments(tool, query),
                            "priority": 1,
                            "required": True,
                        }
                    )

            elif query.intent == "assignment":
                # Look for operations tools
                ops_tools = [t for t in tools if t.category == ToolCategory.OPERATIONS]
                for tool in ops_tools[:2]:
                    execution_plan.append(
                        {
                            "tool_id": tool.tool_id,
                            "tool_name": tool.name,
                            "arguments": self._prepare_tool_arguments(tool, query),
                            "priority": 1,
                            "required": True,
                        }
                    )

            elif query.intent == "utilization":
                # Look for analysis tools
                analysis_tools = [
                    t for t in tools if t.category == ToolCategory.ANALYSIS
                ]
                for tool in analysis_tools[:2]:
                    execution_plan.append(
                        {
                            "tool_id": tool.tool_id,
                            "tool_name": tool.name,
                            "arguments": self._prepare_tool_arguments(tool, query),
                            "priority": 1,
                            "required": True,
                        }
                    )

            elif query.intent == "maintenance":
                # Look for operations and safety tools
                maintenance_tools = [
                    t
                    for t in tools
                    if t.category in [ToolCategory.OPERATIONS, ToolCategory.SAFETY]
                ]
                for tool in maintenance_tools[:3]:
                    execution_plan.append(
                        {
                            "tool_id": tool.tool_id,
                            "tool_name": tool.name,
                            "arguments": self._prepare_tool_arguments(tool, query),
                            "priority": 1,
                            "required": True,
                        }
                    )

            elif query.intent == "safety":
                # Look for safety tools
                safety_tools = [t for t in tools if t.category == ToolCategory.SAFETY]
                for tool in safety_tools[:3]:
                    execution_plan.append(
                        {
                            "tool_id": tool.tool_id,
                            "tool_name": tool.name,
                            "arguments": self._prepare_tool_arguments(tool, query),
                            "priority": 1,
                            "required": True,
                        }
                    )

            # Sort by priority
            execution_plan.sort(key=lambda x: x["priority"])

            return execution_plan

        except Exception as e:
            logger.error(f"Error creating tool execution plan: {e}")
            return []

    def _prepare_tool_arguments(
        self, tool: DiscoveredTool, query: MCPEquipmentQuery
    ) -> Dict[str, Any]:
        """Prepare arguments for tool execution based on query entities."""
        arguments = {}

        # Get tool parameters from the properties section
        tool_params = tool.parameters.get("properties", {})

        # Map query entities to tool parameters
        for param_name, param_schema in tool_params.items():
            if param_name in query.entities and query.entities[param_name] is not None:
                arguments[param_name] = query.entities[param_name]
            elif param_name == "asset_id" and "equipment_id" in query.entities:
                # Map equipment_id to asset_id
                arguments[param_name] = query.entities["equipment_id"]
            elif param_name == "query" or param_name == "search_term":
                arguments[param_name] = query.user_query
            elif param_name == "context":
                arguments[param_name] = query.context
            elif param_name == "intent":
                arguments[param_name] = query.intent

        return arguments

    async def _execute_tool_plan(
        self, execution_plan: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Execute the tool execution plan."""
        results = {}

        for step in execution_plan:
            try:
                tool_id = step["tool_id"]
                tool_name = step["tool_name"]
                arguments = step["arguments"]

                logger.info(
                    f"Executing MCP tool: {tool_name} with arguments: {arguments}"
                )

                # Execute the tool
                result = await self.tool_discovery.execute_tool(tool_id, arguments)

                results[tool_id] = {
                    "tool_name": tool_name,
                    "success": True,
                    "result": result,
                    "execution_time": datetime.utcnow().isoformat(),
                }

                # Record in execution history
                self.tool_execution_history.append(
                    {
                        "tool_id": tool_id,
                        "tool_name": tool_name,
                        "arguments": arguments,
                        "result": result,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )

            except Exception as e:
                logger.error(f"Error executing tool {step['tool_name']}: {e}")
                results[step["tool_id"]] = {
                    "tool_name": step["tool_name"],
                    "success": False,
                    "error": str(e),
                    "execution_time": datetime.utcnow().isoformat(),
                }

        return results

    async def _generate_response_with_tools(
        self, query: MCPEquipmentQuery, tool_results: Dict[str, Any]
    ) -> MCPEquipmentResponse:
        """Generate response using LLM with tool execution results."""
        try:
            # Prepare context for LLM
            successful_results = {
                k: v for k, v in tool_results.items() if v.get("success", False)
            }
            failed_results = {
                k: v for k, v in tool_results.items() if not v.get("success", False)
            }

            # Create response prompt
            response_prompt = [
                {
                    "role": "system",
                    "content": """You are an Equipment & Asset Operations Agent. Generate comprehensive responses based on user queries and tool execution results.

CRITICAL INSTRUCTIONS:
1. Return ONLY the JSON object
2. Do NOT include any text before the JSON
3. Do NOT include any text after the JSON
4. Do NOT include explanatory text like "Here is the response"
5. Do NOT include markdown formatting like ```
6. Do NOT include notes or additional explanations

Return JSON format:
{
    "response_type": "equipment_info",
    "data": {"equipment": [], "status": "operational"},
    "natural_language": "Based on the tool results...",
    "recommendations": ["Recommendation 1", "Recommendation 2"],
    "confidence": 0.85,
    "actions_taken": [{"action": "tool_execution", "tool": "get_equipment_status"}]
}

Response types based on intent:
- equipment_lookup: "equipment_info" with equipment details
- equipment_dispatch: "equipment_dispatch" with dispatch status, location, and equipment details
- equipment_assignment: "equipment_assignment" with assignment details
- equipment_maintenance: "equipment_maintenance" with maintenance status
- equipment_availability: "equipment_availability" with availability status

For equipment_dispatch intent, generate specific dispatch information:
{
    "response_type": "equipment_dispatch",
    "data": {
        "equipment_id": "FL-02",
        "equipment_type": "forklift",
        "destination": "Zone A",
        "operation": "pick operations",
        "status": "dispatched",
        "dispatch_time": "2024-01-15T17:15:00Z",
        "estimated_arrival": "2024-01-15T17:20:00Z"
    },
    "natural_language": "Forklift FL-02 has been successfully dispatched to Zone A for pick operations. Estimated arrival time is 5 minutes.",
    "recommendations": ["Monitor forklift FL-02 progress to Zone A", "Ensure Zone A is ready for pick operations"],
    "confidence": 0.9,
    "actions_taken": [{"action": "dispatch_equipment", "equipment_id": "FL-02", "destination": "Zone A"}]
}

ABSOLUTELY CRITICAL: Your response must start with { and end with }. No other text.""",
                },
                {
                    "role": "user",
                    "content": f"""User Query: "{query.user_query}"
Intent: {query.intent}
Entities: {query.entities}
Context: {query.context}

Tool Execution Results:
{json.dumps(successful_results, indent=2)}

Failed Tool Executions:
{json.dumps(failed_results, indent=2)}""",
                },
            ]

            response = await self.nim_client.generate_response(response_prompt)

            # Parse JSON response
            try:
                response_data = json.loads(response.content)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse LLM response as JSON: {e}")
                logger.warning(f"Raw LLM response: {response.content}")
                # Fallback response
                response_data = {
                    "response_type": "equipment_info",
                    "data": {"results": successful_results},
                    "natural_language": f"Based on the available data, here's what I found regarding your equipment query: {query.user_query}",
                    "recommendations": [
                        "Please review the equipment status and take appropriate action if needed."
                    ],
                    "confidence": 0.7,
                    "actions_taken": [
                        {
                            "action": "mcp_tool_execution",
                            "tools_used": len(successful_results),
                        }
                    ],
                }

            return MCPEquipmentResponse(
                response_type=response_data.get("response_type", "equipment_info"),
                data=response_data.get("data", {}),
                natural_language=response_data.get("natural_language", ""),
                recommendations=response_data.get("recommendations", []),
                confidence=response_data.get("confidence", 0.7),
                actions_taken=response_data.get("actions_taken", []),
                mcp_tools_used=list(successful_results.keys()),
                tool_execution_results=tool_results,
            )

        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return MCPEquipmentResponse(
                response_type="error",
                data={"error": str(e)},
                natural_language=f"I encountered an error generating a response: {str(e)}",
                recommendations=["Please try again or contact support."],
                confidence=0.0,
                actions_taken=[],
                mcp_tools_used=[],
                tool_execution_results=tool_results,
            )

    async def get_available_tools(self) -> List[DiscoveredTool]:
        """Get all available MCP tools."""
        if not self.tool_discovery:
            return []

        return list(self.tool_discovery.discovered_tools.values())

    async def get_tools_by_category(
        self, category: ToolCategory
    ) -> List[DiscoveredTool]:
        """Get tools by category."""
        if not self.tool_discovery:
            return []

        return await self.tool_discovery.get_tools_by_category(category)

    async def search_tools(self, query: str) -> List[DiscoveredTool]:
        """Search for tools by query."""
        if not self.tool_discovery:
            return []

        return await self.tool_discovery.search_tools(query)

    def get_agent_status(self) -> Dict[str, Any]:
        """Get agent status and statistics."""
        return {
            "initialized": self.tool_discovery is not None,
            "available_tools": (
                len(self.tool_discovery.discovered_tools) if self.tool_discovery else 0
            ),
            "tool_execution_history": len(self.tool_execution_history),
            "conversation_contexts": len(self.conversation_context),
            "mcp_discovery_status": (
                self.tool_discovery.get_discovery_status()
                if self.tool_discovery
                else None
            ),
        }


# Global MCP equipment agent instance
_mcp_equipment_agent = None


async def get_mcp_equipment_agent() -> MCPEquipmentAssetOperationsAgent:
    """Get the global MCP equipment agent instance."""
    global _mcp_equipment_agent
    if _mcp_equipment_agent is None:
        _mcp_equipment_agent = MCPEquipmentAssetOperationsAgent()
        await _mcp_equipment_agent.initialize()
    return _mcp_equipment_agent
