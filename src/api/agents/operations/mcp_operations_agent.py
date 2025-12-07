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

from src.api.services.llm.nim_client import get_nim_client, LLMResponse
from src.retrieval.hybrid_retriever import get_hybrid_retriever, SearchContext
from src.memory.memory_manager import get_memory_manager
from src.api.services.mcp.tool_discovery import (
    ToolDiscoveryService,
    DiscoveredTool,
    ToolCategory,
)
from src.api.services.mcp.base import MCPManager
from src.api.services.reasoning import (
    get_reasoning_engine,
    ReasoningType,
    ReasoningChain,
)
from src.api.utils.log_utils import sanitize_prompt_input
from src.api.services.agent_config import load_agent_config, AgentConfig
from src.api.services.validation import get_response_validator
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
    reasoning_chain: Optional[ReasoningChain] = None  # Advanced reasoning chain
    reasoning_steps: Optional[List[Dict[str, Any]]] = None  # Individual reasoning steps


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
        self.reasoning_engine = None
        self.conversation_context = {}
        self.mcp_tools_cache = {}
        self.tool_execution_history = []
        self.config: Optional[AgentConfig] = None  # Agent configuration

    async def initialize(self) -> None:
        """Initialize the agent with required services including MCP."""
        try:
            # Load agent configuration
            self.config = load_agent_config("operations")
            logger.info(f"Loaded agent configuration: {self.config.name}")
            
            self.nim_client = await get_nim_client()
            self.hybrid_retriever = await get_hybrid_retriever()
            self.operations_tools = await get_operations_action_tools()

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
                "MCP-enabled Operations Coordination Agent initialized successfully"
            )
        except Exception as e:
            logger.error(f"Failed to initialize MCP Operations Coordination Agent: {e}")
            raise

    async def _register_mcp_sources(self) -> None:
        """Register MCP sources for tool discovery."""
        try:
            # Import and register the operations MCP adapter
            from src.api.services.mcp.adapters.operations_adapter import (
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
        enable_reasoning: bool = False,
        reasoning_types: Optional[List[str]] = None,
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
                logger.info(f"Discovered {len(available_tools)} tools for intent '{parsed_query.intent}': {[tool.name for tool in available_tools[:5]]}")

                # Create tool execution plan
                execution_plan = await self._create_tool_execution_plan(
                    parsed_query, available_tools
                )
                parsed_query.tool_execution_plan = execution_plan
                if execution_plan:
                    logger.info(f"Created execution plan with {len(execution_plan)} tools: {[step.get('tool_name') for step in execution_plan]}")

                # Execute tools and gather results
                if execution_plan:
                    logger.info(f"Executing {len(execution_plan)} tools for intent '{parsed_query.intent}': {[step.get('tool_name') for step in execution_plan]}")
                    tool_results = await self._execute_tool_plan(execution_plan)
                    logger.info(f"Tool execution completed: {len([r for r in tool_results.values() if r.get('success')])} successful, {len([r for r in tool_results.values() if not r.get('success')])} failed")
                else:
                    logger.warning(f"No tools found for intent '{parsed_query.intent}' - query will be processed without tool execution")
                    tool_results = {}

            # Generate response using LLM with tool results (include reasoning chain)
            response = await self._generate_response_with_tools(
                parsed_query, tool_results, reasoning_chain
            )

            # Update conversation context
            self.conversation_context[session_id]["queries"].append(parsed_query)
            self.conversation_context[session_id]["responses"].append(response)

            return response

        except Exception as e:
            logger.error(f"Error processing operations query: {e}")
            return self._create_error_response(str(e), "processing your request")

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
                "wave_creation": ToolCategory.OPERATIONS,
                "equipment_dispatch": ToolCategory.OPERATIONS,
                "order_management": ToolCategory.OPERATIONS,
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

    def _add_tools_to_execution_plan(
        self,
        execution_plan: List[Dict[str, Any]],
        tools: List[DiscoveredTool],
        category: ToolCategory,
        limit: int,
        query: MCPOperationsQuery,
    ) -> None:
        """
        Add tools of a specific category to execution plan.
        
        Args:
            execution_plan: Execution plan list to append to
            tools: List of available tools
            category: Tool category to filter
            limit: Maximum number of tools to add
            query: Query object for argument preparation
        """
        filtered_tools = [t for t in tools if t.category == category]
        for tool in filtered_tools[:limit]:
            execution_plan.append(
                {
                    "tool_id": tool.tool_id,
                    "tool_name": tool.name,
                    "arguments": self._prepare_tool_arguments(tool, query),
                    "priority": 1,
                    "required": True,
                }
            )
    
    async def _create_tool_execution_plan(
        self, query: MCPOperationsQuery, tools: List[DiscoveredTool]
    ) -> List[Dict[str, Any]]:
        """Create a plan for executing MCP tools."""
        try:
            execution_plan = []

            # Create execution steps based on query intent
            intent_config = {
                "workforce_management": (ToolCategory.OPERATIONS, 3),
                "task_assignment": (ToolCategory.OPERATIONS, 2),
                "kpi_analysis": (ToolCategory.ANALYSIS, 2),
                "shift_planning": (ToolCategory.OPERATIONS, 3),
                "wave_creation": (ToolCategory.OPERATIONS, 2),  # For creating pick waves
                "equipment_dispatch": (ToolCategory.OPERATIONS, 2),  # For dispatching equipment
                "order_management": (ToolCategory.OPERATIONS, 2),
                "resource_allocation": (ToolCategory.OPERATIONS, 2),
            }
            
            category, limit = intent_config.get(
                query.intent, (ToolCategory.OPERATIONS, 2)
            )
            self._add_tools_to_execution_plan(
                execution_plan, tools, category, limit, query
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
        """Prepare arguments for tool execution based on query entities and intelligent extraction."""
        arguments = {}
        query_lower = query.user_query.lower()

        # Extract parameter properties - handle JSON Schema format
        # Parameters are stored as: {"type": "object", "properties": {...}, "required": [...]}
        if isinstance(tool.parameters, dict) and "properties" in tool.parameters:
            param_properties = tool.parameters.get("properties", {})
            required_params = tool.parameters.get("required", [])
        elif isinstance(tool.parameters, dict):
            # Fallback: treat as flat dict if no "properties" key
            param_properties = tool.parameters
            required_params = []
        else:
            param_properties = {}
            required_params = []

        # Map query entities to tool parameters
        for param_name, param_schema in param_properties.items():
            # Direct entity mapping
            if param_name in query.entities:
                arguments[param_name] = query.entities[param_name]
            # Special parameter mappings
            elif param_name == "query" or param_name == "search_term":
                arguments[param_name] = query.user_query
            elif param_name == "context":
                arguments[param_name] = query.context
            elif param_name == "intent":
                arguments[param_name] = query.intent
            # Intelligent parameter extraction for create_task
            elif param_name == "task_type" and tool.name == "create_task":
                # Extract task type from query or intent
                if "task_type" in query.entities:
                    arguments[param_name] = query.entities["task_type"]
                elif "pick" in query_lower or "wave" in query_lower or query.intent == "wave_creation":
                    arguments[param_name] = "pick"
                elif "pack" in query_lower:
                    arguments[param_name] = "pack"
                elif "putaway" in query_lower or "put away" in query_lower:
                    arguments[param_name] = "putaway"
                elif "receive" in query_lower or "receiving" in query_lower:
                    arguments[param_name] = "receive"
                else:
                    arguments[param_name] = "pick"  # Default for wave creation
            # Intelligent parameter extraction for create_task - sku
            elif param_name == "sku" and tool.name == "create_task":
                # Extract SKU from entities or use a default
                if "sku" in query.entities:
                    arguments[param_name] = query.entities["sku"]
                elif "order" in query_lower or "orders" in query_lower:
                    # For wave creation, we don't need a specific SKU
                    # Extract order IDs if available
                    import re
                    order_matches = re.findall(r'\b(\d{4,})\b', query.user_query)
                    if order_matches:
                        arguments[param_name] = f"ORDER_{order_matches[0]}"
                    else:
                        arguments[param_name] = "WAVE_ITEMS"  # Placeholder for wave items
                else:
                    arguments[param_name] = "GENERAL"
            # Intelligent parameter extraction for create_task - quantity
            elif param_name == "quantity" and tool.name == "create_task":
                if "quantity" in query.entities:
                    arguments[param_name] = query.entities["quantity"]
                else:
                    import re
                    qty_matches = re.findall(r'\b(\d+)\b', query.user_query)
                    if qty_matches:
                        arguments[param_name] = int(qty_matches[0])
                    else:
                        arguments[param_name] = 1
            # Intelligent parameter extraction for create_task - zone
            elif param_name == "zone" and tool.name == "create_task":
                if "zone" in query.entities:
                    arguments[param_name] = query.entities["zone"]
                else:
                    import re
                    zone_match = re.search(r'zone\s+([A-Za-z])', query_lower)
                    if zone_match:
                        arguments[param_name] = f"Zone {zone_match.group(1).upper()}"
                    else:
                        arguments[param_name] = query.entities.get("zone", "Zone A")
            # Intelligent parameter extraction for create_task - priority
            elif param_name == "priority" and tool.name == "create_task":
                if "priority" in query.entities:
                    arguments[param_name] = query.entities["priority"]
                elif "urgent" in query_lower or "high" in query_lower:
                    arguments[param_name] = "high"
                elif "low" in query_lower:
                    arguments[param_name] = "low"
                else:
                    arguments[param_name] = "medium"
            # Intelligent parameter extraction for assign_task - task_id
            elif param_name == "task_id" and tool.name == "assign_task":
                if "task_id" in query.entities:
                    arguments[param_name] = query.entities["task_id"]
                # For wave creation queries, task_id will be generated by create_task
                # This should be handled by chaining tool executions
                else:
                    # Try to extract from context if this is a follow-up
                    arguments[param_name] = query.context.get("task_id") or query.entities.get("task_id")
            # Intelligent parameter extraction for assign_task - worker_id
            elif param_name == "worker_id" and tool.name == "assign_task":
                if "worker_id" in query.entities:
                    arguments[param_name] = query.entities["worker_id"]
                elif "operator" in query.entities:
                    arguments[param_name] = query.entities["operator"]
                elif "assignee" in query.entities:
                    arguments[param_name] = query.entities["assignee"]
                else:
                    # Will be assigned automatically if not specified
                    arguments[param_name] = None

        return arguments

    async def _execute_tool_plan(
        self, execution_plan: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Execute the tool execution plan, handling dependencies between tools."""
        results = {}
        
        if not execution_plan:
            logger.warning("Tool execution plan is empty - no tools to execute")
            return results

        # Define tool dependencies: tools that depend on other tools
        tool_dependencies = {
            "assign_task": ["create_task"],  # assign_task needs task_id from create_task
        }

        async def execute_single_tool(step: Dict[str, Any], previous_results: Dict[str, Any] = None) -> tuple:
            """Execute a single tool and return (tool_id, result_dict)."""
            tool_id = step["tool_id"]
            tool_name = step["tool_name"]
            arguments = step["arguments"].copy()  # Make a copy to avoid modifying original
            
            # If this tool has dependencies, extract values from previous results
            if previous_results and tool_name in tool_dependencies:
                dependencies = tool_dependencies[tool_name]
                for dep_tool_name in dependencies:
                    # Find the result from the dependent tool
                    for prev_tool_id, prev_result in previous_results.items():
                        if prev_result.get("tool_name") == dep_tool_name and prev_result.get("success"):
                            dep_result = prev_result.get("result", {})
                            
                            # Extract task_id from create_task result
                            if dep_tool_name == "create_task" and tool_name == "assign_task":
                                if isinstance(dep_result, dict):
                                    task_id = dep_result.get("task_id") or dep_result.get("taskId")
                                    if task_id and arguments.get("task_id") is None:
                                        arguments["task_id"] = task_id
                                        logger.info(f"Extracted task_id '{task_id}' from {dep_tool_name} result for {tool_name}")
                            
                            break
            
            try:
                logger.info(
                    f"Executing MCP tool: {tool_name} with arguments: {arguments}"
                )

                # Execute the tool
                result = await self.tool_discovery.execute_tool(tool_id, arguments)

                result_dict = {
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
                
                return (tool_id, result_dict)

            except Exception as e:
                logger.error(f"Error executing tool {tool_name}: {e}")
                result_dict = {
                    "tool_name": tool_name,
                    "success": False,
                    "error": str(e),
                    "execution_time": datetime.utcnow().isoformat(),
                }
                return (tool_id, result_dict)

        # Separate tools into dependent and independent groups
        independent_tools = []
        dependent_tools = []
        
        for step in execution_plan:
            tool_name = step["tool_name"]
            if tool_name in tool_dependencies:
                dependent_tools.append(step)
            else:
                independent_tools.append(step)
        
        # Execute independent tools in parallel first
        if independent_tools:
            execution_tasks = [execute_single_tool(step) for step in independent_tools]
            execution_results = await asyncio.gather(*execution_tasks, return_exceptions=True)
            
            # Process independent tool results
            for result in execution_results:
                if isinstance(result, Exception):
                    logger.error(f"Unexpected error in tool execution: {result}")
                    continue
                
                tool_id, result_dict = result
                results[tool_id] = result_dict
        
        # Execute dependent tools sequentially, using results from previous tools
        for step in dependent_tools:
            tool_id, result_dict = await execute_single_tool(step, previous_results=results)
            results[tool_id] = result_dict

        successful_count = len([r for r in results.values() if r.get('success')])
        logger.info(f"Executed {len(execution_plan)} tools ({len(independent_tools)} parallel, {len(dependent_tools)} sequential), {successful_count} successful")
        return results

    async def _generate_response_with_tools(
        self, query: MCPOperationsQuery, tool_results: Dict[str, Any], reasoning_chain: Optional[ReasoningChain] = None
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
            
            logger.info(f"Generating response with {len(successful_results)} successful tool results and {len(failed_results)} failed results")
            if successful_results:
                logger.info(f"Successful tool results: {list(successful_results.keys())}")
                for tool_id, result in list(successful_results.items())[:3]:  # Log first 3
                    logger.info(f"  Tool {tool_id} ({result.get('tool_name', 'unknown')}): {str(result.get('result', {}))[:200]}")

            # Load response prompt from configuration
            if self.config is None:
                self.config = load_agent_config("operations")
            
            response_prompt_template = self.config.persona.response_prompt
            system_prompt = self.config.persona.system_prompt
            
            # Format the response prompt with actual values
            formatted_response_prompt = response_prompt_template.format(
                user_query=sanitize_prompt_input(query.user_query),
                intent=sanitize_prompt_input(query.intent),
                entities=json.dumps(query.entities, default=str),
                retrieved_data=json.dumps(successful_results, indent=2, default=str),
                actions_taken=json.dumps(tool_results, indent=2, default=str),
                conversation_history="",
                dispatch_instructions=""
            )
            
            # Create response prompt
            response_prompt = [
                {
                    "role": "system",
                    "content": system_prompt + "\n\nIMPORTANT: You MUST return ONLY valid JSON. Do not include any text before or after the JSON.",
                },
                {
                    "role": "user",
                    "content": formatted_response_prompt,
                },
            ]

            # Use slightly higher temperature for more natural language (0.3 instead of default 0.2)
            # This balances consistency with natural, fluent language
            response = await self.nim_client.generate_response(
                response_prompt, 
                temperature=0.3
            )

            # Parse JSON response
            try:
                response_data = json.loads(response.content)
                logger.info(f"Successfully parsed LLM response: {response_data}")
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse LLM response as JSON: {e}")
                logger.warning(f"Raw LLM response: {response.content}")
                
                # Try to extract JSON from markdown code blocks
                import re
                json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response.content, re.DOTALL)
                if json_match:
                    try:
                        response_data = json.loads(json_match.group(1))
                        logger.info(f"Successfully extracted JSON from code block: {response_data}")
                    except json.JSONDecodeError:
                        logger.warning("Failed to parse JSON from code block")
                        response_data = None
                else:
                    response_data = None
                
                # If still no valid JSON, generate natural language from tool results using LLM
                if response_data is None:
                    logger.info(f"Generating natural language response from tool results: {len(successful_results)} successful, {len(failed_results)} failed")
                    
                    # Use LLM to generate natural language from tool results
                    if successful_results:
                        # Prepare tool results summary for LLM
                        tool_results_summary = []
                        for tool_id, result in successful_results.items():
                            tool_name = result.get("tool_name", tool_id)
                            tool_result = result.get("result", {})
                            tool_results_summary.append({
                                "tool": tool_name,
                                "result": tool_result
                            })
                        
                        # Ask LLM to generate natural language response
                        natural_lang_prompt = [
                            {
                                "role": "system",
                                "content": """You are a warehouse operations expert. Generate a clear, natural, conversational response 
that explains what was accomplished based on tool execution results. Write in a professional but friendly tone, 
as if explaining to a colleague. Use complete sentences, vary your sentence structure, and make it sound natural and fluent."""
                            },
                            {
                                "role": "user",
                                "content": f"""The user asked: "{query.user_query}"

The following tools were executed successfully:
{json.dumps(tool_results_summary, indent=2, default=str)[:1500]}

Generate a natural, conversational response (2-4 sentences) that:
1. Confirms what was accomplished
2. Includes specific details (IDs, names, statuses) naturally woven into the explanation
3. Sounds like a human expert explaining the results
4. Is clear, professional, and easy to read

Return ONLY the natural language response text (no JSON, no formatting, just the response)."""
                            }
                        ]
                        
                        try:
                            natural_lang_response = await self.nim_client.generate_response(
                                natural_lang_prompt,
                                temperature=0.4  # Slightly higher for more natural language
                            )
                            natural_language = natural_lang_response.content.strip()
                            logger.info(f"Generated natural language from LLM: {natural_language[:200]}...")
                        except Exception as e:
                            logger.warning(f"Failed to generate natural language from LLM: {e}, using fallback")
                            # Fallback to structured summary
                            summaries = []
                            for tool_id, result in successful_results.items():
                                tool_name = result.get("tool_name", tool_id)
                                tool_result = result.get("result", {})
                                if isinstance(tool_result, dict):
                                    if "wave_id" in tool_result:
                                        summaries.append(f"I've created wave {tool_result['wave_id']} for orders {', '.join(map(str, tool_result.get('order_ids', [])))} in {tool_result.get('zone', 'the specified zone')}.")
                                    elif "task_id" in tool_result:
                                        summaries.append(f"I've created task {tool_result['task_id']} of type {tool_result.get('task_type', 'unknown')}.")
                                    elif "equipment_id" in tool_result:
                                        summaries.append(f"I've dispatched {tool_result.get('equipment_id')} to {tool_result.get('zone', 'the specified location')} for {tool_result.get('task_type', 'operations')}.")
                                    else:
                                        summaries.append(f"I've successfully executed {tool_name}.")
                                else:
                                    summaries.append(f"I've successfully executed {tool_name}.")
                            
                            natural_language = " ".join(summaries) if summaries else "I've completed your request successfully."
                    else:
                        # No successful results - use the raw LLM response if it looks reasonable
                        if response.content and len(response.content.strip()) > 50:
                            natural_language = response.content.strip()
                        else:
                            natural_language = f"I processed your request regarding {query.intent.replace('_', ' ')}, but I wasn't able to execute the requested actions. Please check the system status and try again."
                    
                    # Calculate confidence based on tool execution success rate
                    total_tools = len(tool_results)
                    successful_count = len(successful_results)
                    failed_count = len(failed_results)
                    
                    if total_tools == 0:
                        confidence = 0.5  # No tools executed
                    elif successful_count == total_tools:
                        confidence = 0.95  # All tools succeeded - very high confidence
                    elif successful_count > 0:
                        # Calculate based on success rate, with bonus for having some successes
                        success_rate = successful_count / total_tools
                        confidence = 0.75 + (success_rate * 0.2)  # Range: 0.75 to 0.95
                    else:
                        confidence = 0.3  # All tools failed - low confidence
                    
                    logger.info(f"Calculated confidence: {confidence:.2f} (successful: {successful_count}/{total_tools})")
                    
                    # Create fallback response with tool results
                    response_data = {
                        "response_type": "operations_info",
                        "data": {"results": successful_results, "failed": failed_results},
                        "natural_language": natural_language,
                        "recommendations": [
                            "Please review the operations status and take appropriate action if needed."
                        ] if not successful_results else [],
                        "confidence": confidence,
                        "actions_taken": [
                            {
                                "action": tool_result.get("tool_name", tool_id),
                                "status": "success" if tool_result.get("success") else "failed",
                                "details": tool_result.get("result", {})
                            }
                            for tool_id, tool_result in tool_results.items()
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
            
            # Extract and potentially enhance natural language
            natural_language = response_data.get("natural_language", "")
            
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
                response_data["confidence"] = max(current_confidence, calculated_confidence)
            else:
                # If no tools or all failed, use calculated confidence
                response_data["confidence"] = calculated_confidence
            
            logger.info(f"Final confidence: {response_data['confidence']:.2f} (LLM: {current_confidence:.2f}, Calculated: {calculated_confidence:.2f})")
            
            # If natural language is too short or seems incomplete, enhance it
            if natural_language and len(natural_language.strip()) < 50:
                logger.warning(f"Natural language seems too short ({len(natural_language)} chars), attempting enhancement")
                # Try to enhance with LLM
                try:
                    enhance_prompt = [
                        {
                            "role": "system",
                            "content": "You are a warehouse operations expert. Expand and improve the given response to make it more natural, detailed, and conversational while keeping the same meaning."
                        },
                        {
                            "role": "user",
                            "content": f"""Original response: "{natural_language}"

User query: "{query.user_query}"

Tool results: {len(successful_results)} tools executed successfully

Expand this into a natural, conversational response (2-4 sentences) that explains what was accomplished in a clear, professional tone. Return ONLY the enhanced response text."""
                        }
                    ]
                    enhanced_response = await self.nim_client.generate_response(
                        enhance_prompt,
                        temperature=0.4
                    )
                    natural_language = enhanced_response.content.strip()
                    logger.info(f"Enhanced natural language: {natural_language[:200]}...")
                except Exception as e:
                    logger.warning(f"Failed to enhance natural language: {e}")
            
            # Validate response quality
            try:
                validator = get_response_validator()
                validation_result = validator.validate(
                    response=response_data,
                    query=query.user_query,
                    tool_results=tool_results,
                )
                
                if not validation_result.is_valid:
                    logger.warning(f"Response validation failed: {validation_result.issues}")
                    if validation_result.warnings:
                        logger.warning(f"Validation warnings: {validation_result.warnings}")
                else:
                    logger.info(f"Response validation passed (score: {validation_result.score:.2f})")
                
                # Log suggestions for improvement
                if validation_result.suggestions:
                    logger.info(f"Validation suggestions: {validation_result.suggestions}")
            except Exception as e:
                logger.warning(f"Response validation error: {e}")
            
            return MCPOperationsResponse(
                response_type=response_data.get("response_type", "operations_info"),
                data=response_data.get("data", {}),
                natural_language=natural_language,
                recommendations=response_data.get("recommendations", []),
                confidence=response_data.get("confidence", 0.85 if successful_results else 0.5),
                actions_taken=response_data.get("actions_taken", []),
                mcp_tools_used=list(successful_results.keys()),
                tool_execution_results=tool_results,
                reasoning_chain=reasoning_chain,
                reasoning_steps=reasoning_steps,
            )

        except Exception as e:
            logger.error(f"Error generating response: {e}")
            error_response = self._create_error_response(str(e), "generating a response")
            error_response.tool_execution_results = tool_results
            return error_response

    def _check_tool_discovery(self) -> bool:
        """Check if tool discovery is available."""
        return self.tool_discovery is not None
    
    async def get_available_tools(self) -> List[DiscoveredTool]:
        """Get all available MCP tools."""
        if not self._check_tool_discovery():
            return []
        return list(self.tool_discovery.discovered_tools.values())

    async def get_tools_by_category(
        self, category: ToolCategory
    ) -> List[DiscoveredTool]:
        """Get tools by category."""
        if not self._check_tool_discovery():
            return []
        return await self.tool_discovery.get_tools_by_category(category)

    async def search_tools(self, query: str) -> List[DiscoveredTool]:
        """Search for tools by query."""
        if not self._check_tool_discovery():
            return []
        return await self.tool_discovery.search_tools(query)

    def _create_error_response(
        self, error_message: str, operation: str
    ) -> MCPOperationsResponse:
        """
        Create standardized error response.
        
        Args:
            error_message: Error message
            operation: Description of the operation that failed
            
        Returns:
            MCPOperationsResponse with error details
        """
        recommendations = [
            "Please try rephrasing your question or contact support if the issue persists."
        ]
        if "generating" in operation:
            recommendations = ["Please try again or contact support."]
        
        return MCPOperationsResponse(
            response_type="error",
            data={"error": error_message},
            natural_language=f"I encountered an error {operation}: {error_message}",
            recommendations=recommendations,
            confidence=0.0,
            actions_taken=[],
            mcp_tools_used=[],
            tool_execution_results={},
            reasoning_chain=None,
            reasoning_steps=None,
        )
    
    def get_agent_status(self) -> Dict[str, Any]:
        """Get agent status and statistics."""
        return {
            "initialized": self._check_tool_discovery(),
            "available_tools": (
                len(self.tool_discovery.discovered_tools) if self._check_tool_discovery() else 0
            ),
            "tool_execution_history": len(self.tool_execution_history),
            "conversation_contexts": len(self.conversation_context),
            "mcp_discovery_status": (
                self.tool_discovery.get_discovery_status()
                if self._check_tool_discovery()
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
            "option",
        ]
        return any(keyword in query_lower for keyword in complex_keywords)
    
    def _check_keywords_in_query(self, query_lower: str, keywords: List[str]) -> bool:
        """
        Check if any keywords are present in the query.
        
        Args:
            query_lower: Lowercase query string
            keywords: List of keywords to check
            
        Returns:
            True if any keyword is found, False otherwise
        """
        return any(keyword in query_lower for keyword in keywords)
    
    def _determine_reasoning_types(
        self, query: str, context: Optional[Dict[str, Any]]
    ) -> List[ReasoningType]:
        """Determine appropriate reasoning types based on query complexity and context."""
        reasoning_types = [ReasoningType.CHAIN_OF_THOUGHT]  # Always include chain-of-thought
        query_lower = query.lower()
        
        # Define keyword mappings for each reasoning type
        reasoning_keywords = {
            ReasoningType.MULTI_HOP: [
                "analyze", "compare", "relationship", "connection", "across", "multiple"
            ],
            ReasoningType.SCENARIO_ANALYSIS: [
                "what if", "scenario", "alternative", "option", "if", "when", "suppose"
            ],
            ReasoningType.CAUSAL: [
                "why", "cause", "effect", "because", "result", "consequence", "due to", "leads to"
            ],
            ReasoningType.PATTERN_RECOGNITION: [
                "pattern", "trend", "learn", "insight", "recommendation", "optimize", "improve"
            ],
        }
        
        # Check each reasoning type
        for reasoning_type, keywords in reasoning_keywords.items():
            if self._check_keywords_in_query(query_lower, keywords):
                if reasoning_type not in reasoning_types:
                    reasoning_types.append(reasoning_type)
        
        # For operations queries, always include scenario analysis for workflow optimization
        workflow_keywords = ["optimize", "improve", "efficiency", "workflow", "strategy"]
        if self._check_keywords_in_query(query_lower, workflow_keywords):
            if ReasoningType.SCENARIO_ANALYSIS not in reasoning_types:
                reasoning_types.append(ReasoningType.SCENARIO_ANALYSIS)
        
        return reasoning_types


# Global MCP operations agent instance
_mcp_operations_agent = None


async def get_mcp_operations_agent() -> MCPOperationsCoordinationAgent:
    """Get the global MCP operations agent instance."""
    global _mcp_operations_agent
    if _mcp_operations_agent is None:
        _mcp_operations_agent = MCPOperationsCoordinationAgent()
        await _mcp_operations_agent.initialize()
    return _mcp_operations_agent
