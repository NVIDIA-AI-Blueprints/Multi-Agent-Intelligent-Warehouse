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
import re

from src.api.services.llm.nim_client import get_nim_client, LLMResponse
from src.retrieval.hybrid_retriever import get_hybrid_retriever, SearchContext
from src.memory.memory_manager import get_memory_manager
from src.api.services.mcp.tool_discovery import (
    ToolDiscoveryService,
    DiscoveredTool,
    ToolCategory,
)
from src.api.services.mcp.base import MCPManager

# Import SecurityViolationError if available, otherwise define a placeholder
try:
    from src.api.services.mcp.security import SecurityViolationError
except ImportError:
    # Define a placeholder if security module doesn't exist
    class SecurityViolationError(Exception):
        """Security violation error."""
        pass
from src.api.services.reasoning import (
    get_reasoning_engine,
    ReasoningType,
    ReasoningChain,
)
from src.api.utils.log_utils import sanitize_prompt_input
from src.api.services.agent_config import load_agent_config, AgentConfig
from src.api.services.validation import get_response_validator
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
    reasoning_chain: Optional[ReasoningChain] = None  # Advanced reasoning chain
    reasoning_steps: Optional[List[Dict[str, Any]]] = None  # Individual reasoning steps


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
        self.reasoning_engine = None
        self.conversation_context = {}
        self.mcp_tools_cache = {}
        self.tool_execution_history = []
        self.config: Optional[AgentConfig] = None  # Agent configuration

    async def initialize(self) -> None:
        """Initialize the agent with required services including MCP."""
        try:
            # Load agent configuration
            self.config = load_agent_config("equipment")
            logger.info(f"Loaded agent configuration: {self.config.name}")
            
            self.nim_client = await get_nim_client()
            self.hybrid_retriever = await get_hybrid_retriever()
            self.asset_tools = await get_equipment_asset_tools()

            # Initialize MCP components
            self.mcp_manager = MCPManager()
            self.tool_discovery = ToolDiscoveryService()

            # Start tool discovery
            await self.tool_discovery.start_discovery()

            # Initialize reasoning engine
            self.reasoning_engine = await get_reasoning_engine()

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
            from src.api.services.mcp.adapters.equipment_adapter import (
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
        enable_reasoning: bool = False,
        reasoning_types: Optional[List[str]] = None,
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

            # Step 1: Advanced Reasoning Analysis (if enabled and query is complex)
            reasoning_chain = None
            if enable_reasoning and self.reasoning_engine and self._is_complex_query(query):
                try:
                    # Convert string reasoning types to ReasoningType enum if provided
                    reasoning_type_enums = None
                    if reasoning_types:
                        reasoning_type_enums = []
                        for rt_str in reasoning_types:
                            try:
                                rt_enum = ReasoningType(rt_str)
                                reasoning_type_enums.append(rt_enum)
                            except ValueError:
                                logger.warning(f"Invalid reasoning type: {rt_str}, skipping")
                    
                    # Determine reasoning types if not provided
                    if reasoning_type_enums is None:
                        reasoning_type_enums = self._determine_reasoning_types(query, context)

                    reasoning_chain = await self.reasoning_engine.process_with_reasoning(
                        query=query,
                        context=context or {},
                        reasoning_types=reasoning_type_enums,
                        session_id=session_id,
                    )
                    logger.info(f"Advanced reasoning completed: {len(reasoning_chain.steps)} steps")
                except Exception as e:
                    logger.warning(f"Advanced reasoning failed, continuing with standard processing: {e}")
            else:
                logger.info("Skipping advanced reasoning for simple query or reasoning disabled")

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
                logger.info(f"Discovered {len(available_tools)} tools for query: {query[:100]}, intent: {parsed_query.intent}")
                
                # If no tools discovered, try to get all available tools
                if not available_tools:
                    logger.warning(f"No tools discovered via _discover_relevant_tools, trying to get all available tools")
                    all_tools = await self.get_available_tools()
                    logger.info(f"Got {len(all_tools)} total available tools")
                    if all_tools:
                        # Use all available tools as fallback
                        available_tools = all_tools[:5]  # Limit to 5 tools
                        logger.info(f"Using {len(available_tools)} tools as fallback")
                
                parsed_query.mcp_tools = [tool.tool_id for tool in available_tools]

                # Create tool execution plan
                execution_plan = await self._create_tool_execution_plan(
                    parsed_query, available_tools
                )
                parsed_query.tool_execution_plan = execution_plan
                
                logger.info(f"Created tool execution plan with {len(execution_plan)} tools for query: {query[:100]}")

                # Execute tools and gather results
                tool_results = await self._execute_tool_plan(execution_plan)
                
                logger.info(f"Tool execution completed: {len([r for r in tool_results.values() if r.get('success')])} successful, {len([r for r in tool_results.values() if not r.get('success')])} failed")

            # Generate response using LLM with tool results (include reasoning chain)
            response = await self._generate_response_with_tools(
                parsed_query, tool_results, reasoning_chain
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
                reasoning_chain=None,
                reasoning_steps=None,
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
                "equipment_availability": ToolCategory.EQUIPMENT,
                "equipment_telemetry": ToolCategory.EQUIPMENT,
                "equipment_utilization": ToolCategory.EQUIPMENT,
                "equipment_maintenance": ToolCategory.OPERATIONS,
                "equipment_dispatch": ToolCategory.OPERATIONS,
                "equipment_assignment": ToolCategory.OPERATIONS,
                "equipment_safety": ToolCategory.SAFETY,
                "assignment": ToolCategory.OPERATIONS,
                "utilization": ToolCategory.ANALYSIS,
                "maintenance": ToolCategory.OPERATIONS,
                "availability": ToolCategory.EQUIPMENT,
                "telemetry": ToolCategory.EQUIPMENT,
                "safety": ToolCategory.SAFETY,
                "equipment": ToolCategory.EQUIPMENT,  # Generic equipment intent
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
            # If no specific intent matches, default to equipment_lookup
            # Also handle variations like "equipment" as intent
            intent_matches = query.intent in ["equipment_lookup", "equipment_availability", "equipment_telemetry", "equipment"]
            query_has_equipment_keywords = any(keyword in query.user_query.lower() for keyword in ["status", "availability", "forklift", "equipment", "show", "list"])
            
            if intent_matches or query_has_equipment_keywords:
                # Look for equipment tools
                equipment_tools = [
                    t for t in tools if t.category == ToolCategory.EQUIPMENT
                ]
                # If no equipment tools found, use any available tools
                if not equipment_tools and tools:
                    logger.warning(f"No EQUIPMENT category tools found, using any available tools: {[t.tool_id for t in tools[:3]]}")
                    equipment_tools = tools[:3]
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

            elif query.intent in ["utilization", "equipment_utilization"]:
                # Look for equipment utilization tools first, then analysis tools
                equipment_tools = [
                    t for t in tools if t.category == ToolCategory.EQUIPMENT
                ]
                # Prefer get_equipment_utilization tool if available
                utilization_tools = [t for t in equipment_tools if "utilization" in t.name.lower()]
                if utilization_tools:
                    for tool in utilization_tools[:2]:
                        execution_plan.append(
                            {
                                "tool_id": tool.tool_id,
                                "tool_name": tool.name,
                                "arguments": self._prepare_tool_arguments(tool, query),
                                "priority": 1,
                                "required": True,
                            }
                        )
                # Also include other equipment tools for context
                other_equipment_tools = [t for t in equipment_tools if "utilization" not in t.name.lower()]
                for tool in other_equipment_tools[:2]:
                    execution_plan.append(
                        {
                            "tool_id": tool.tool_id,
                            "tool_name": tool.name,
                            "arguments": self._prepare_tool_arguments(tool, query),
                            "priority": 2,
                            "required": False,
                        }
                    )
                # Look for analysis tools as fallback
                analysis_tools = [
                    t for t in tools if t.category == ToolCategory.ANALYSIS
                ]
                for tool in analysis_tools[:2]:
                    execution_plan.append(
                        {
                            "tool_id": tool.tool_id,
                            "tool_name": tool.name,
                            "arguments": self._prepare_tool_arguments(tool, query),
                            "priority": 3,
                            "required": False,
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

            # If no execution plan was created, create a default plan with available tools
            if not execution_plan and tools:
                logger.warning(f"Tool execution plan is empty - creating default plan with available tools: {[t.tool_id for t in tools[:3]]}")
                # Use first 3 available tools as fallback
                for tool in tools[:3]:
                    execution_plan.append(
                        {
                            "tool_id": tool.tool_id,
                            "tool_name": tool.name,
                            "arguments": self._prepare_tool_arguments(tool, query),
                            "priority": 2,  # Lower priority for fallback
                            "required": False,
                        }
                    )
            elif not execution_plan:
                logger.warning("Tool execution plan is empty - no tools available to execute")

            return execution_plan

        except Exception as e:
            logger.error(f"Error creating tool execution plan: {e}")
            # Return empty plan on error - will be handled by caller
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
        """Execute the tool execution plan in parallel where possible with retry logic."""
        results = {}
        
        if not execution_plan:
            logger.warning("Tool execution plan is empty - no tools to execute")
            return results

        async def execute_single_tool_with_retry(
            step: Dict[str, Any], max_retries: int = 3
        ) -> tuple:
            """Execute a single tool with retry logic and return (tool_id, result_dict)."""
            tool_id = step["tool_id"]
            tool_name = step["tool_name"]
            arguments = step["arguments"]
            required = step.get("required", False)
            
            # Retry configuration
            retry_delays = [1.0, 2.0, 4.0]  # Exponential backoff: 1s, 2s, 4s
            last_error = None
            
            for attempt in range(max_retries):
                try:
                    logger.info(
                        f"Executing MCP tool: {tool_name} (attempt {attempt + 1}/{max_retries}) with arguments: {arguments}"
                    )

                    # Execute the tool with timeout
                    tool_timeout = 15.0  # 15 second timeout per tool execution
                    try:
                        result = await asyncio.wait_for(
                            self.tool_discovery.execute_tool(tool_id, arguments),
                            timeout=tool_timeout
                        )
                    except asyncio.TimeoutError:
                        error_msg = f"Tool execution timeout after {tool_timeout}s"
                        logger.warning(f"{error_msg} for {tool_name} (attempt {attempt + 1}/{max_retries})")
                        last_error = TimeoutError(error_msg)
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delays[attempt])
                            continue
                        else:
                            raise last_error

                    # Success - record result
                    result_dict = {
                        "tool_name": tool_name,
                        "success": True,
                        "result": result,
                        "execution_time": datetime.utcnow().isoformat(),
                        "attempts": attempt + 1,
                    }

                    # Record in execution history
                    self.tool_execution_history.append(
                        {
                            "tool_id": tool_id,
                            "tool_name": tool_name,
                            "arguments": arguments,
                            "result": result,
                            "timestamp": datetime.utcnow().isoformat(),
                            "attempts": attempt + 1,
                        }
                    )
                    
                    logger.info(f"Successfully executed tool {tool_name} after {attempt + 1} attempt(s)")
                    return (tool_id, result_dict)

                except asyncio.TimeoutError as e:
                    last_error = e
                    error_type = "timeout"
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Tool {tool_name} timed out (attempt {attempt + 1}/{max_retries}), retrying in {retry_delays[attempt]}s..."
                        )
                        await asyncio.sleep(retry_delays[attempt])
                        continue
                    else:
                        logger.error(f"Tool {tool_name} timed out after {max_retries} attempts")
                        
                except ValueError as e:
                    # Tool not found or invalid arguments - don't retry
                    last_error = e
                    error_type = "validation_error"
                    logger.error(f"Tool {tool_name} validation error: {e} (not retrying)")
                    break
                    
                except SecurityViolationError as e:
                    # Security violation - don't retry
                    last_error = e
                    error_type = "security_error"
                    logger.error(f"Tool {tool_name} security violation: {e} (not retrying)")
                    break
                    
                except ConnectionError as e:
                    # Connection error - retry
                    last_error = e
                    error_type = "connection_error"
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Tool {tool_name} connection error (attempt {attempt + 1}/{max_retries}): {e}, retrying in {retry_delays[attempt]}s..."
                        )
                        await asyncio.sleep(retry_delays[attempt])
                        continue
                    else:
                        logger.error(f"Tool {tool_name} connection error after {max_retries} attempts: {e}")
                        
                except Exception as e:
                    # Other errors - retry for transient errors
                    last_error = e
                    error_type = type(e).__name__
                    
                    # Check if error is retryable (transient errors)
                    retryable_errors = [
                        "ConnectionError",
                        "TimeoutError",
                        "asyncio.TimeoutError",
                        "ServiceUnavailable",
                    ]
                    is_retryable = any(err in error_type for err in retryable_errors)
                    
                    if is_retryable and attempt < max_retries - 1:
                        logger.warning(
                            f"Tool {tool_name} transient error (attempt {attempt + 1}/{max_retries}): {e}, retrying in {retry_delays[attempt]}s..."
                        )
                        await asyncio.sleep(retry_delays[attempt])
                        continue
                    else:
                        logger.error(f"Tool {tool_name} error after {attempt + 1} attempt(s): {e}")
                        if not is_retryable:
                            # Non-retryable error - don't retry
                            break
            
            # All retries exhausted or non-retryable error
            error_msg = str(last_error) if last_error else "Unknown error"
            result_dict = {
                "tool_name": tool_name,
                "success": False,
                "error": error_msg,
                "error_type": error_type if 'error_type' in locals() else "unknown",
                "execution_time": datetime.utcnow().isoformat(),
                "attempts": max_retries,
                "required": required,
            }
            
            # Log detailed error information
            logger.error(
                f"Failed to execute tool {tool_name} after {max_retries} attempts. "
                f"Error: {error_msg}, Type: {error_type if 'error_type' in locals() else 'unknown'}, "
                f"Required: {required}"
            )
            
            return (tool_id, result_dict)

        # Execute all tools in parallel
        execution_tasks = [
            execute_single_tool_with_retry(step) for step in execution_plan
        ]
        execution_results = await asyncio.gather(*execution_tasks, return_exceptions=True)
        
        # Process results
        successful_count = 0
        failed_count = 0
        failed_required = []
        
        for result in execution_results:
            if isinstance(result, Exception):
                logger.error(f"Unexpected error in tool execution: {result}")
                failed_count += 1
                continue
            
            tool_id, result_dict = result
            results[tool_id] = result_dict
            
            if result_dict.get("success"):
                successful_count += 1
            else:
                failed_count += 1
                if result_dict.get("required", False):
                    failed_required.append(result_dict.get("tool_name", tool_id))

        logger.info(
            f"Executed {len(execution_plan)} tools in parallel: "
            f"{successful_count} successful, {failed_count} failed. "
            f"Failed required tools: {failed_required if failed_required else 'none'}"
        )
        
        # Log warning if required tools failed
        if failed_required:
            logger.warning(
                f"Required tools failed: {failed_required}. This may impact response quality."
            )
        
        return results

    def _build_user_prompt_content(
        self,
        query: MCPEquipmentQuery,
        successful_results: Dict[str, Any],
        failed_results: Dict[str, Any],
        reasoning_chain: Optional[ReasoningChain],
    ) -> str:
        """Build the user prompt content for response generation."""
        # Build reasoning chain section if available
        reasoning_section = ""
        if reasoning_chain:
            try:
                reasoning_type_str = (
                    reasoning_chain.reasoning_type.value
                    if hasattr(reasoning_chain.reasoning_type, "value")
                    else str(reasoning_chain.reasoning_type)
                )
                reasoning_data = {
                    "reasoning_type": reasoning_type_str,
                    "final_conclusion": reasoning_chain.final_conclusion,
                    "steps": [
                        {
                            "step_id": step.step_id,
                            "description": step.description,
                            "reasoning": step.reasoning,
                            "confidence": step.confidence,
                        }
                        for step in (reasoning_chain.steps or [])
                    ],
                }
                reasoning_section = f"""
Reasoning Chain Analysis:
{json.dumps(reasoning_data, indent=2)}
"""
            except Exception as e:
                logger.warning(f"Error building reasoning chain section: {e}")
                reasoning_section = ""

        # Sanitize user input to prevent template injection
        safe_user_query = sanitize_prompt_input(query.user_query)
        safe_intent = sanitize_prompt_input(query.intent)
        safe_entities = sanitize_prompt_input(query.entities)
        safe_context = sanitize_prompt_input(query.context)

        # Build the full prompt content
        content = f"""User Query: "{safe_user_query}"
Intent: {safe_intent}
Entities: {safe_entities}
Context: {safe_context}

Tool Execution Results:
{json.dumps(successful_results, indent=2)}

Failed Tool Executions:
{json.dumps(failed_results, indent=2)}
{reasoning_section}
IMPORTANT: Use the tool execution results to provide a comprehensive answer. The reasoning chain provides analysis context, but the actual data comes from the tool results. Always include structured data from tool results in the response."""
        
        return content

    async def _generate_response_with_tools(
        self, query: MCPEquipmentQuery, tool_results: Dict[str, Any], reasoning_chain: Optional[ReasoningChain] = None
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

            # Load response prompt from configuration
            if self.config is None:
                self.config = load_agent_config("equipment")
            
            response_prompt_template = self.config.persona.response_prompt
            system_prompt = self.config.persona.system_prompt
            
            # Format the response prompt with actual values
            formatted_response_prompt = response_prompt_template.format(
                user_query=query.user_query,
                intent=query.intent,
                entities=json.dumps(query.entities, default=str),
                retrieved_data=json.dumps(successful_results, indent=2, default=str),
                actions_taken=json.dumps(tool_results, indent=2, default=str)
            )
            
            # Create response prompt with very explicit instructions
            enhanced_system_prompt = system_prompt + """

CRITICAL JSON FORMAT REQUIREMENTS:
1. Return ONLY a valid JSON object - no markdown, no code blocks, no explanations before or after
2. Your response must start with { and end with }
3. The 'natural_language' field is MANDATORY and must contain a detailed, informative response
4. Do NOT put equipment data at the top level - all data must be inside the 'data' field
5. The 'natural_language' field must directly answer the user's question with specific details

REQUIRED JSON STRUCTURE:
{
    "response_type": "equipment_info",
    "data": {
        "equipment": [...],
        "status": "...",
        "availability": "..."
    },
    "natural_language": "Based on your query about [user query], I found the following equipment: [specific details including asset IDs, types, statuses, zones, etc.]. [Additional context and recommendations].",
    "recommendations": ["Recommendation 1", "Recommendation 2"],
    "confidence": 0.85,
    "actions_taken": [...]
}

ABSOLUTELY CRITICAL:
- The 'natural_language' field is REQUIRED and must not be empty
- Include specific equipment details (asset IDs, types, statuses, zones) in natural_language
- Return valid JSON only - no other text
"""
            
            # Create response prompt
            response_prompt = [
                {
                    "role": "system",
                    "content": enhanced_system_prompt,
                },
                {
                    "role": "user",
                    "content": formatted_response_prompt + "\n\nRemember: Return ONLY the JSON object with the 'natural_language' field populated with a detailed response.",
                },
            ]

            # Use lower temperature for more deterministic JSON responses
            response = await self.nim_client.generate_response(
                response_prompt,
                temperature=0.0,  # Lower temperature for more consistent JSON format
                max_tokens=2000  # Allow more tokens for detailed responses
            )

            # Parse JSON response - try to extract JSON from response if it contains extra text
            response_text = response.content.strip()
            
            # Try to extract JSON if response contains extra text
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text, re.DOTALL)
            if json_match:
                response_text = json_match.group(0)
            
            try:
                response_data = json.loads(response_text)
                logger.info(f"Successfully parsed LLM response for equipment query")
                # Log if natural_language is empty
                if not response_data.get("natural_language") or response_data.get("natural_language", "").strip() == "":
                    logger.warning(f"LLM returned empty natural_language field. Response data keys: {list(response_data.keys())}")
                    logger.warning(f"Response data (first 1000 chars): {json.dumps(response_data, indent=2, default=str)[:1000]}")
                    logger.warning(f"Raw LLM response (first 500 chars): {response.content[:500]}")
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse LLM response as JSON: {e}")
                logger.warning(f"Raw LLM response (first 500 chars): {response.content[:500]}")
                # Fallback response - use the text content but clean it
                natural_lang = response.content
                # Remove any JSON-like structures from the text
                natural_lang = re.sub(r"\{[^{}]*'tool_execution_results'[^{}]*\}", "", natural_lang)
                natural_lang = re.sub(r"'tool_execution_results':\s*\{\}", "", natural_lang)
                natural_lang = re.sub(r"tool_execution_results:\s*\{\}", "", natural_lang)
                natural_lang = natural_lang.strip()
                
                response_data = {
                    "response_type": "equipment_info",
                    "data": {"results": successful_results},
                    "natural_language": natural_lang if natural_lang else f"Based on the available data, here's what I found regarding your equipment query: {sanitize_prompt_input(query.user_query)}",
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

            # Convert reasoning chain to dict for response
            reasoning_steps = None
            if reasoning_chain:
                reasoning_steps = [
                    {
                        "step_id": step.step_id,
                        "step_type": step.step_type,
                        "description": step.description,
                        "reasoning": step.reasoning,
                        "confidence": step.confidence,
                    }
                    for step in reasoning_chain.steps
                ]
            
            # Extract and validate recommendations - ensure they're strings
            recommendations_raw = response_data.get("recommendations", [])
            recommendations = []
            if isinstance(recommendations_raw, list):
                for rec in recommendations_raw:
                    if isinstance(rec, str):
                        recommendations.append(rec)
                    elif isinstance(rec, dict):
                        # Extract text from dict if it's a dict
                        rec_text = rec.get("recommendation") or rec.get("text") or rec.get("message") or str(rec)
                        if rec_text:
                            recommendations.append(str(rec_text))
                    else:
                        recommendations.append(str(rec))
            
            # Ensure natural_language is not empty
            natural_language = response_data.get("natural_language", "")
            
            # Check if response_data has equipment-related keys directly (wrong structure)
            equipment_keys = ["equipment", "status", "availability", "asset_id", "type", "model", "zone", "owner_user", "next_pm_due"]
            has_equipment_data = any(key in response_data for key in equipment_keys)
            
            # Extract equipment from tool results first (most reliable source)
            all_equipment = []
            equipment_summary = {}
            by_status = {}  # Initialize here for use later
            
            for tool_id, result_data in successful_results.items():
                result = result_data.get("result", {})
                if isinstance(result, dict):
                    # Check for equipment list in result
                    if "equipment" in result and isinstance(result["equipment"], list):
                        all_equipment.extend(result["equipment"])
                    # Check for summary data
                    if "summary" in result and isinstance(result["summary"], dict):
                        equipment_summary.update(result["summary"])
            
            # Group equipment by status (do this once for use in multiple places)
            if all_equipment:
                for eq in all_equipment:
                    status = eq.get("status", "unknown")
                    if status not in by_status:
                        by_status[status] = []
                    by_status[status].append(eq)
            
            # Prepare equipment data summary for LLM generation (used in both natural_language and recommendations)
            equipment_data_summary = {
                "equipment": all_equipment[:10],  # Limit to first 10 for prompt size
                "summary_by_status": {status: len(items) for status, items in by_status.items()},
                "total_count": len(all_equipment)
            }
            
            # If natural_language is missing, ask LLM to generate it from the response data
            if not natural_language or natural_language.strip() == "":
                logger.warning("LLM did not return natural_language field. Requesting LLM to generate it from the response data.")
                
                # Also include response_data
                data_for_generation = response_data.copy()
                
                # Ask LLM to generate natural_language from the equipment data
                generation_prompt = [
                    {
                        "role": "system",
                        "content": """You are a certified equipment and asset operations expert. 
Generate a comprehensive, expert-level natural language response based on the provided equipment data.

CRITICAL: Write in a clear, natural, conversational tone:
- Use fluent, natural English that reads like a human expert speaking
- Avoid robotic or template-like language
- Be specific and detailed, but keep it readable
- Use active voice when possible
- Vary sentence structure for better readability
- Make it sound like you're explaining to a colleague, not a machine
- Include context and reasoning, not just facts
- Write complete, well-formed sentences and paragraphs

CRITICAL ANTI-ECHOING RULES - YOU MUST FOLLOW THESE:
- NEVER start with phrases like "You asked", "You requested", "I'll", "Let me", "As you requested", "Here's what you asked for"
- NEVER echo or repeat the user's query - start directly with the information or action result
- Start with the actual information or what was accomplished (e.g., "I found 3 forklifts..." or "FL-01 is available...")
- Write as if explaining to a colleague, not referencing the query
- DO NOT say "Here's the response:" or "Here's what I found:" - just provide the information directly

Your response must be detailed, informative, and directly answer the user's query WITHOUT echoing it.
Include specific equipment details (asset IDs, statuses, zones, models, etc.) naturally woven into the explanation.
Provide expert-level analysis of equipment availability, utilization, and recommendations."""
                    },
                    {
                        "role": "user",
                        "content": f"""The user asked: "{query.user_query}"

The system retrieved the following equipment data:
{json.dumps(equipment_data_summary, indent=2, default=str)[:2000]}

Response data structure:
{json.dumps(data_for_generation, indent=2, default=str)[:1000]}

Tool execution results summary:
{len(successful_results)} tools executed successfully

Generate a comprehensive, expert-level natural language response that:
1. Directly answers the user's query about equipment status and availability WITHOUT echoing the query
2. Starts immediately with the information (e.g., "I found 3 forklifts..." or "FL-01 is available...")
3. NEVER starts with "You asked", "You requested", "I'll", "Let me", "Here's the response", etc.
4. Includes specific details from the equipment data (asset IDs, statuses, zones, models) naturally woven into the explanation
5. Provides expert analysis of equipment availability and utilization with context
6. Offers actionable recommendations based on the equipment status
7. Is written in a clear, natural, conversational tone - like explaining to a colleague
8. Uses varied sentence structure and flows naturally
9. Is comprehensive but concise (typically 2-4 well-formed paragraphs)

Write in a way that sounds natural and human, not robotic or template-like. Return ONLY the natural language response text (no JSON, no formatting, just the response text)."""
                    }
                ]
                
                try:
                    generation_response = await self.nim_client.generate_response(
                        generation_prompt,
                        temperature=0.4,  # Higher temperature for more natural, fluent language
                        max_tokens=1000
                    )
                    natural_language = generation_response.content.strip()
                    logger.info(f"LLM generated natural_language: {natural_language[:200]}...")
                except Exception as e:
                    logger.error(f"Failed to generate natural_language from LLM: {e}", exc_info=True)
                    # If LLM generation fails, we still need to provide a response
                    # This is a fallback, but we should log the error for debugging
                    natural_language = f"I've processed your equipment query: {sanitize_prompt_input(query.user_query)}. Please review the structured data for details."
            
            # Populate data field with equipment information
            data = response_data.get("data", {})
            if not data or (isinstance(data, dict) and len(data) == 0):
                # Build data from tool results
                data = {}
                if all_equipment:
                    data["equipment"] = all_equipment
                    data["total_count"] = len(all_equipment)
                    # Add summary by status
                    if by_status:
                        data["summary"] = {status: len(items) for status, items in by_status.items()}
                elif has_equipment_data:
                    # Move top-level equipment data into data field (fallback)
                    for key in equipment_keys:
                        if key in response_data:
                            data[key] = response_data[key]
                # Always include tool_results in data
                if successful_results:
                    data["tool_results"] = successful_results
            
            # Generate recommendations if missing - ask LLM to generate them
            if not recommendations or (isinstance(recommendations, list) and len(recommendations) == 0):
                logger.info("LLM did not return recommendations. Requesting LLM to generate expert recommendations.")
                
                # Ask LLM to generate recommendations based on the query and equipment data
                recommendations_prompt = [
                    {
                        "role": "system",
                        "content": """You are a certified equipment and asset operations expert. 
Generate actionable, expert-level recommendations based on the user's query and equipment data.
Recommendations should be specific, practical, and based on equipment management best practices."""
                    },
                    {
                        "role": "user",
                        "content": f"""The user asked: "{query.user_query}"
Query intent: {query.intent}
Query entities: {json.dumps(query.entities, default=str)}

Equipment data:
{json.dumps(equipment_data_summary, indent=2, default=str)[:1500]}

Response data:
{json.dumps(response_data, indent=2, default=str)[:1000]}

Generate 3-5 actionable, expert-level recommendations that:
1. Are specific to the user's query and the equipment data
2. Follow equipment management best practices
3. Are practical and implementable
4. Address equipment availability, utilization, maintenance, or assignment needs

Return ONLY a JSON array of recommendation strings, for example:
["Recommendation 1", "Recommendation 2", "Recommendation 3"]

Do not include any other text, just the JSON array."""
                    }
                ]
                
                try:
                    rec_response = await self.nim_client.generate_response(
                        recommendations_prompt,
                        temperature=0.3,
                        max_tokens=500
                    )
                    rec_text = rec_response.content.strip()
                    # Try to extract JSON array
                    json_match = re.search(r'\[.*?\]', rec_text, re.DOTALL)
                    if json_match:
                        recommendations = json.loads(json_match.group(0))
                    else:
                        # Fallback: split by lines if not JSON
                        recommendations = [line.strip() for line in rec_text.split('\n') if line.strip() and (line.strip().startswith('-') or line.strip().startswith('•'))]
                        if not recommendations:
                            recommendations = [rec_text]
                    logger.info(f"LLM generated {len(recommendations)} recommendations")
                except Exception as e:
                    logger.error(f"Failed to generate recommendations from LLM: {e}", exc_info=True)
                    recommendations = []  # Empty rather than hardcoded
            
            # Validate response quality
            try:
                validator = get_response_validator()
                validation_result = validator.validate(
                    response={
                        "natural_language": natural_language,
                        "confidence": response_data.get("confidence", 0.7),
                        "response_type": response_data.get("response_type", "equipment_info"),
                        "recommendations": recommendations,
                        "actions_taken": response_data.get("actions_taken", []),
                        "mcp_tools_used": list(successful_results.keys()),
                        "tool_execution_results": tool_results,
                    },
                    query=query.user_query if hasattr(query, 'user_query') else str(query),
                    tool_results=tool_results,
                )
                
                if not validation_result.is_valid:
                    logger.warning(f"Response validation failed: {validation_result.issues}")
                else:
                    logger.info(f"Response validation passed (score: {validation_result.score:.2f})")
            except Exception as e:
                logger.warning(f"Response validation error: {e}")
            
            # Improved confidence calculation based on tool execution results
            current_confidence = response_data.get("confidence", 0.7)
            total_tools = len(tool_results)
            successful_count = len(successful_results)
            failed_count = len(failed_results)
            
            # Calculate confidence based on tool execution success
            if total_tools == 0:
                # No tools executed - use LLM confidence or default
                calculated_confidence = current_confidence if current_confidence > 0.5 else 0.5
            elif successful_count == total_tools:
                # All tools succeeded - very high confidence
                calculated_confidence = 0.95
                logger.info(f"All {total_tools} tools succeeded - setting confidence to 0.95")
            elif successful_count > 0:
                # Some tools succeeded - confidence based on success rate
                success_rate = successful_count / total_tools
                # Base confidence: 0.75, plus bonus for success rate (up to 0.2)
                calculated_confidence = 0.75 + (success_rate * 0.2)  # Range: 0.75 to 0.95
                logger.info(f"Partial success ({successful_count}/{total_tools}) - setting confidence to {calculated_confidence:.2f}")
            else:
                # All tools failed - low confidence
                calculated_confidence = 0.3
                logger.info(f"All {total_tools} tools failed - setting confidence to 0.3")
            
            # Use the higher of LLM confidence and calculated confidence (but don't go below calculated if tools succeeded)
            if successful_count > 0:
                # If tools succeeded, use calculated confidence (which is based on actual results)
                final_confidence = max(current_confidence, calculated_confidence)
            else:
                # If no tools or all failed, use calculated confidence
                final_confidence = calculated_confidence
            
            logger.info(f"Final confidence: {final_confidence:.2f} (LLM: {current_confidence:.2f}, Calculated: {calculated_confidence:.2f})")
            
            return MCPEquipmentResponse(
                response_type=response_data.get("response_type", "equipment_info"),
                data=data if data else response_data.get("data", {}),
                natural_language=natural_language,
                recommendations=recommendations,
                confidence=final_confidence,
                actions_taken=response_data.get("actions_taken", []),
                mcp_tools_used=list(successful_results.keys()),
                tool_execution_results=tool_results,
                reasoning_chain=reasoning_chain,
                reasoning_steps=reasoning_steps,
            )

        except Exception as e:
            logger.error(f"Error generating response: {e}", exc_info=True)
            # Provide user-friendly error message without exposing internal errors
            error_message = "I encountered an error while processing your equipment query. Please try rephrasing your question or contact support if the issue persists."
            return MCPEquipmentResponse(
                response_type="error",
                data={"error": str(e)},
                natural_language=error_message,
                recommendations=["Please try rephrasing your question", "Contact support if the issue persists"],
                confidence=0.0,
                actions_taken=[],
                mcp_tools_used=[],
                tool_execution_results=tool_results,
                reasoning_chain=None,
                reasoning_steps=None,
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
    
    def _is_complex_query(self, query: str) -> bool:
        """Determine if a query is complex enough to require reasoning."""
        query_lower = query.lower()
        complex_keywords = [
            "analyze",
            "compare",
            "relationship",
            "why",
            "how",
            "explain",
            "investigate",
            "evaluate",
            "optimize",
            "improve",
            "what if",
            "scenario",
            "pattern",
            "trend",
            "cause",
            "effect",
            "because",
            "result",
            "consequence",
            "due to",
            "leads to",
            "recommendation",
            "suggestion",
            "strategy",
            "plan",
            "alternative",
            "increase",
            "decrease",
            "enhance",
            "productivity",
            "impact",
            "if we",
            "would",
            "should",
            "option",
        ]
        return any(keyword in query_lower for keyword in complex_keywords)
    
    def _determine_reasoning_types(
        self, query: str, context: Optional[Dict[str, Any]]
    ) -> List[ReasoningType]:
        """Determine appropriate reasoning types based on query complexity and context."""
        reasoning_types = [ReasoningType.CHAIN_OF_THOUGHT]  # Always include chain-of-thought
        
        query_lower = query.lower()
        
        # Multi-hop reasoning for complex queries
        if any(
            keyword in query_lower
            for keyword in [
                "analyze",
                "compare",
                "relationship",
                "connection",
                "across",
                "multiple",
            ]
        ):
            reasoning_types.append(ReasoningType.MULTI_HOP)
        
        # Scenario analysis for what-if questions
        if any(
            keyword in query_lower
            for keyword in [
                "what if",
                "scenario",
                "alternative",
                "option",
                "if",
                "when",
                "suppose",
            ]
        ):
            reasoning_types.append(ReasoningType.SCENARIO_ANALYSIS)
        
        # Causal reasoning for cause-effect questions
        if any(
            keyword in query_lower
            for keyword in [
                "why",
                "cause",
                "effect",
                "because",
                "result",
                "consequence",
                "due to",
                "leads to",
            ]
        ):
            reasoning_types.append(ReasoningType.CAUSAL)
        
        # Pattern recognition for learning queries
        if any(
            keyword in query_lower
            for keyword in [
                "pattern",
                "trend",
                "learn",
                "insight",
                "recommendation",
                "optimize",
                "improve",
            ]
        ):
            reasoning_types.append(ReasoningType.PATTERN_RECOGNITION)
        
        # For equipment queries, always include multi-hop if analyzing utilization or performance
        if any(
            keyword in query_lower
            for keyword in ["utilization", "performance", "efficiency", "optimize"]
        ):
            if ReasoningType.MULTI_HOP not in reasoning_types:
                reasoning_types.append(ReasoningType.MULTI_HOP)
        
        return reasoning_types


# Global MCP equipment agent instance
_mcp_equipment_agent = None


async def get_mcp_equipment_agent() -> MCPEquipmentAssetOperationsAgent:
    """Get the global MCP equipment agent instance."""
    global _mcp_equipment_agent
    if _mcp_equipment_agent is None:
        _mcp_equipment_agent = MCPEquipmentAssetOperationsAgent()
        await _mcp_equipment_agent.initialize()
    return _mcp_equipment_agent
