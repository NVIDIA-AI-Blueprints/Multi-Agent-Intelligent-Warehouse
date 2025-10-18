"""
MCP-Enabled Operations Coordination Agent

This agent integrates with the Model Context Protocol (MCP) system to provide
dynamic tool discovery and execution for operations coordination and workforce management.
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
from .action_tools import get_operations_action_tools

logger = logging.getLogger(__name__)


@dataclass
class MCPOperationsQuery:
    """MCP-enabled operations query."""

    intent: str
    entities: Dict[str, Any]
    context: Dict[str, Any]
    user_query: str
    mcp_tools: List[str] = None  # Available MCP tools for this query
    tool_execution_plan: List[Dict[str, Any]] = None  # Planned tool executions


@dataclass
class MCPOperationsResponse:
    """MCP-enabled operations response."""

    response_type: str
    data: Dict[str, Any]
    natural_language: str
    recommendations: List[str]
    confidence: float
    actions_taken: List[Dict[str, Any]]
    mcp_tools_used: List[str] = None
    tool_execution_results: Dict[str, Any] = None


class MCPOperationsCoordinationAgent:
    """
    MCP-enabled Operations Coordination Agent.

    This agent integrates with the Model Context Protocol (MCP) system to provide:
    - Dynamic tool discovery and execution for operations management
    - MCP-based tool binding and routing for workforce coordination
    - Enhanced tool selection and validation for task management
    - Comprehensive error handling and fallback mechanisms
    """

    def __init__(self):
        self.nim_client = None
        self.hybrid_retriever = None
        self.operations_tools = None
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
            self.operations_tools = await get_operations_action_tools()

            # Initialize MCP components
            self.mcp_manager = MCPManager()
            self.tool_discovery = ToolDiscoveryService()

            # Start tool discovery
            await self.tool_discovery.start_discovery()

            # Register MCP sources
            await self._register_mcp_sources()

            logger.info(
                "MCP-enabled Operations Coordination Agent initialized successfully"
            )
        except Exception as e:
            logger.error(f"Failed to initialize MCP Operations Coordination Agent: {e}")
            raise

    async def _register_mcp_sources(self) -> None:
        """Register MCP sources for tool discovery."""
        try:
            # Import and register the operations MCP adapter
            from chain_server.services.mcp.adapters.operations_adapter import (
                get_operations_adapter,
            )

            # Register the operations adapter as an MCP source
            operations_adapter = await get_operations_adapter()
            await self.tool_discovery.register_discovery_source(
                "operations_action_tools", operations_adapter, "mcp_adapter"
            )

            logger.info("MCP sources registered successfully")
        except Exception as e:
            logger.error(f"Failed to register MCP sources: {e}")

    async def process_query(
        self,
        query: str,
        session_id: str = "default",
        context: Optional[Dict[str, Any]] = None,
        mcp_results: Optional[Any] = None,
    ) -> MCPOperationsResponse:
        """
        Process an operations coordination query with MCP integration.

        Args:
            query: User's operations query
            session_id: Session identifier for context
            context: Additional context
            mcp_results: Optional MCP execution results from planner graph

        Returns:
            MCPOperationsResponse with MCP tool execution results
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
            parsed_query = await self._parse_operations_query(query, context)

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
            logger.error(f"Error processing operations query: {e}")
            return MCPOperationsResponse(
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

    async def _parse_operations_query(
        self, query: str, context: Optional[Dict[str, Any]]
    ) -> MCPOperationsQuery:
        """Parse operations query and extract intent and entities."""
        try:
            # Use LLM to parse the query
            parse_prompt = [
                {
                    "role": "system",
                    "content": """You are an operations coordination expert. Parse warehouse operations queries and extract intent, entities, and context.

Return JSON format:
{
    "intent": "workforce_management",
    "entities": {"worker_id": "W001", "zone": "A"},
    "context": {"priority": "high", "shift": "morning"}
}

Intent options: workforce_management, task_assignment, shift_planning, kpi_analysis, performance_monitoring, resource_allocation, wave_creation, order_management, workflow_optimization

Examples:
- "Create a wave for orders 1001-1010" → {"intent": "wave_creation", "entities": {"order_range": "1001-1010", "zone": "A"}, "context": {"priority": "normal"}}
- "Assign workers to Zone A" → {"intent": "workforce_management", "entities": {"zone": "A"}, "context": {"priority": "normal"}}
- "Schedule pick operations" → {"intent": "task_assignment", "entities": {"operation_type": "pick"}, "context": {"priority": "normal"}}

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
                    "intent": "workforce_management",
                    "entities": {},
                    "context": {},
                }

            return MCPOperationsQuery(
                intent=parsed_data.get("intent", "workforce_management"),
                entities=parsed_data.get("entities", {}),
                context=parsed_data.get("context", {}),
                user_query=query,
            )

        except Exception as e:
            logger.error(f"Error parsing operations query: {e}")
            return MCPOperationsQuery(
                intent="workforce_management", entities={}, context={}, user_query=query
            )

    async def _discover_relevant_tools(
        self, query: MCPOperationsQuery
    ) -> List[DiscoveredTool]:
        """Discover MCP tools relevant to the operations query."""
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
                "workforce_management": ToolCategory.OPERATIONS,
                "task_assignment": ToolCategory.OPERATIONS,
                "shift_planning": ToolCategory.OPERATIONS,
                "kpi_analysis": ToolCategory.ANALYSIS,
                "performance_monitoring": ToolCategory.ANALYSIS,
                "resource_allocation": ToolCategory.OPERATIONS,
            }

            intent_category = category_mapping.get(
                query.intent, ToolCategory.OPERATIONS
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
        self, query: MCPOperationsQuery, tools: List[DiscoveredTool]
    ) -> List[Dict[str, Any]]:
        """Create a plan for executing MCP tools."""
        try:
            execution_plan = []

            # Create execution steps based on query intent
            if query.intent == "workforce_management":
                # Look for operations tools
                ops_tools = [t for t in tools if t.category == ToolCategory.OPERATIONS]
                for tool in ops_tools[:3]:  # Limit to 3 tools
                    execution_plan.append(
                        {
                            "tool_id": tool.tool_id,
                            "tool_name": tool.name,
                            "arguments": self._prepare_tool_arguments(tool, query),
                            "priority": 1,
                            "required": True,
                        }
                    )

            elif query.intent == "task_assignment":
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

            elif query.intent == "kpi_analysis":
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

            elif query.intent == "shift_planning":
                # Look for operations tools
                ops_tools = [t for t in tools if t.category == ToolCategory.OPERATIONS]
                for tool in ops_tools[:3]:
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
        self, tool: DiscoveredTool, query: MCPOperationsQuery
    ) -> Dict[str, Any]:
        """Prepare arguments for tool execution based on query entities."""
        arguments = {}

        # Map query entities to tool parameters
        for param_name, param_schema in tool.parameters.items():
            if param_name in query.entities:
                arguments[param_name] = query.entities[param_name]
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
        self, query: MCPOperationsQuery, tool_results: Dict[str, Any]
    ) -> MCPOperationsResponse:
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
                    "content": """You are an Operations Coordination Agent. Generate comprehensive responses based on user queries and tool execution results.

IMPORTANT: You MUST return ONLY valid JSON. Do not include any text before or after the JSON.

Return JSON format:
{
    "response_type": "operations_info",
    "data": {"workforce": [], "tasks": [], "kpis": {}},
    "natural_language": "Based on the tool results...",
    "recommendations": ["Recommendation 1", "Recommendation 2"],
    "confidence": 0.85,
    "actions_taken": [{"action": "tool_execution", "tool": "get_workforce_status"}]
}

Response types based on intent:
- wave_creation: "wave_creation" with wave details and order information
- order_management: "order_management" with order status and processing info
- workforce_management: "workforce_management" with worker assignments and status
- task_assignment: "task_assignment" with task details and assignments
- workflow_optimization: "workflow_optimization" with optimization recommendations

Include:
1. Natural language explanation of results
2. Structured data summary appropriate for the intent
3. Actionable recommendations
4. Confidence assessment

CRITICAL: Return ONLY the JSON object, no other text.""",
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
                logger.info(f"Successfully parsed LLM response: {response_data}")
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse LLM response as JSON: {e}")
                logger.warning(f"Raw LLM response: {response.content}")
                # Fallback response
                response_data = {
                    "response_type": "operations_info",
                    "data": {"results": successful_results},
                    "natural_language": f"Based on the available data, here's what I found regarding your operations query: {query.user_query}",
                    "recommendations": [
                        "Please review the operations status and take appropriate action if needed."
                    ],
                    "confidence": 0.7,
                    "actions_taken": [
                        {
                            "action": "mcp_tool_execution",
                            "tools_used": len(successful_results),
                        }
                    ],
                }

            return MCPOperationsResponse(
                response_type=response_data.get("response_type", "operations_info"),
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
            return MCPOperationsResponse(
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


# Global MCP operations agent instance
_mcp_operations_agent = None


async def get_mcp_operations_agent() -> MCPOperationsCoordinationAgent:
    """Get the global MCP operations agent instance."""
    global _mcp_operations_agent
    if _mcp_operations_agent is None:
        _mcp_operations_agent = MCPOperationsCoordinationAgent()
        await _mcp_operations_agent.initialize()
    return _mcp_operations_agent
