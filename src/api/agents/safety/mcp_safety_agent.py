"""
MCP-Enabled Safety & Compliance Agent

This agent integrates with the Model Context Protocol (MCP) system to provide
dynamic tool discovery and execution for safety and compliance management.
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
from .action_tools import get_safety_action_tools

logger = logging.getLogger(__name__)


@dataclass
class MCPSafetyQuery:
    """MCP-enabled safety query."""

    intent: str
    entities: Dict[str, Any]
    context: Dict[str, Any]
    user_query: str
    mcp_tools: List[str] = None  # Available MCP tools for this query
    tool_execution_plan: List[Dict[str, Any]] = None  # Planned tool executions


@dataclass
class MCPSafetyResponse:
    """MCP-enabled safety response."""

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


class MCPSafetyComplianceAgent:
    """
    MCP-enabled Safety & Compliance Agent.

    This agent integrates with the Model Context Protocol (MCP) system to provide:
    - Dynamic tool discovery and execution for safety management
    - MCP-based tool binding and routing for compliance monitoring
    - Enhanced tool selection and validation for incident reporting
    - Comprehensive error handling and fallback mechanisms
    """

    def __init__(self):
        self.nim_client = None
        self.hybrid_retriever = None
        self.safety_tools = None
        self.mcp_manager = None
        self.tool_discovery = None
        self.reasoning_engine = None
        self.conversation_context = {}
        self.mcp_tools_cache = {}
        self.tool_execution_history = []

    async def initialize(self) -> None:
        """Initialize the agent with required services including MCP."""
        try:
            self.nim_client = await get_nim_client()
            self.hybrid_retriever = await get_hybrid_retriever()
            self.safety_tools = await get_safety_action_tools()

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
                "MCP-enabled Safety & Compliance Agent initialized successfully"
            )
        except Exception as e:
            logger.error(f"Failed to initialize MCP Safety & Compliance Agent: {e}")
            raise

    async def _register_mcp_sources(self) -> None:
        """Register MCP sources for tool discovery."""
        try:
            # Import and register the safety MCP adapter
            from src.api.services.mcp.adapters.safety_adapter import (
                get_safety_adapter,
            )

            # Register the safety adapter as an MCP source
            safety_adapter = await get_safety_adapter()
            await self.tool_discovery.register_discovery_source(
                "safety_action_tools", safety_adapter, "mcp_adapter"
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
    ) -> MCPSafetyResponse:
        """
        Process a safety and compliance query with MCP integration.

        Args:
            query: User's safety query
            session_id: Session identifier for context
            context: Additional context
            mcp_results: Optional MCP execution results from planner graph

        Returns:
            MCPSafetyResponse with MCP tool execution results
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
            parsed_query = await self._parse_safety_query(query, context)

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

            # Generate response using LLM with tool results (include reasoning chain)
            response = await self._generate_response_with_tools(
                parsed_query, tool_results, reasoning_chain
            )

            # Update conversation context
            self.conversation_context[session_id]["queries"].append(parsed_query)
            self.conversation_context[session_id]["responses"].append(response)

            return response

        except Exception as e:
            logger.error(f"Error processing safety query: {e}")
            return MCPSafetyResponse(
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

    async def _parse_safety_query(
        self, query: str, context: Optional[Dict[str, Any]]
    ) -> MCPSafetyQuery:
        """Parse safety query and extract intent and entities."""
        try:
            # Use LLM to parse the query
            parse_prompt = [
                {
                    "role": "system",
                    "content": """You are a safety and compliance expert. Parse warehouse safety queries and extract intent, entities, and context.

Return JSON format:
{
    "intent": "incident_reporting",
    "entities": {"incident_type": "safety", "location": "Zone A"},
    "context": {"priority": "high", "severity": "critical"}
}

Intent options: incident_reporting, compliance_check, safety_audit, hazard_identification, policy_lookup, training_tracking

Examples:
- "Report a safety incident in Zone A" → {"intent": "incident_reporting", "entities": {"location": "Zone A"}, "context": {"priority": "high"}}
- "Check compliance for forklift operations" → {"intent": "compliance_check", "entities": {"equipment": "forklift"}, "context": {"priority": "normal"}}
- "Identify hazards in warehouse" → {"intent": "hazard_identification", "entities": {"location": "warehouse"}, "context": {"priority": "high"}}

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
                    "intent": "incident_reporting",
                    "entities": {},
                    "context": {},
                }

            return MCPSafetyQuery(
                intent=parsed_data.get("intent", "incident_reporting"),
                entities=parsed_data.get("entities", {}),
                context=parsed_data.get("context", {}),
                user_query=query,
            )

        except Exception as e:
            logger.error(f"Error parsing safety query: {e}")
            return MCPSafetyQuery(
                intent="incident_reporting", entities={}, context={}, user_query=query
            )

    async def _discover_relevant_tools(
        self, query: MCPSafetyQuery
    ) -> List[DiscoveredTool]:
        """Discover MCP tools relevant to the safety query."""
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
                "incident_reporting": ToolCategory.SAFETY,
                "compliance_check": ToolCategory.SAFETY,
                "safety_audit": ToolCategory.SAFETY,
                "hazard_identification": ToolCategory.SAFETY,
                "policy_lookup": ToolCategory.DATA_ACCESS,
                "training_tracking": ToolCategory.SAFETY,
            }

            intent_category = category_mapping.get(query.intent, ToolCategory.SAFETY)
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
        self, query: MCPSafetyQuery, tools: List[DiscoveredTool]
    ) -> List[Dict[str, Any]]:
        """Create a plan for executing MCP tools."""
        try:
            execution_plan = []

            # Create execution steps based on query intent
            if query.intent == "incident_reporting":
                # Look for safety tools
                safety_tools = [t for t in tools if t.category == ToolCategory.SAFETY]
                for tool in safety_tools[:3]:  # Limit to 3 tools
                    execution_plan.append(
                        {
                            "tool_id": tool.tool_id,
                            "tool_name": tool.name,
                            "arguments": self._prepare_tool_arguments(tool, query),
                            "priority": 1,
                            "required": True,
                        }
                    )

            elif query.intent == "compliance_check":
                # Look for safety and data access tools
                compliance_tools = [
                    t
                    for t in tools
                    if t.category in [ToolCategory.SAFETY, ToolCategory.DATA_ACCESS]
                ]
                for tool in compliance_tools[:2]:
                    execution_plan.append(
                        {
                            "tool_id": tool.tool_id,
                            "tool_name": tool.name,
                            "arguments": self._prepare_tool_arguments(tool, query),
                            "priority": 1,
                            "required": True,
                        }
                    )

            elif query.intent == "safety_audit":
                # Look for safety tools
                audit_tools = [t for t in tools if t.category == ToolCategory.SAFETY]
                for tool in audit_tools[:3]:
                    execution_plan.append(
                        {
                            "tool_id": tool.tool_id,
                            "tool_name": tool.name,
                            "arguments": self._prepare_tool_arguments(tool, query),
                            "priority": 1,
                            "required": True,
                        }
                    )

            elif query.intent == "hazard_identification":
                # Look for safety tools
                hazard_tools = [t for t in tools if t.category == ToolCategory.SAFETY]
                for tool in hazard_tools[:2]:
                    execution_plan.append(
                        {
                            "tool_id": tool.tool_id,
                            "tool_name": tool.name,
                            "arguments": self._prepare_tool_arguments(tool, query),
                            "priority": 1,
                            "required": True,
                        }
                    )

            elif query.intent == "policy_lookup":
                # Look for data access tools
                policy_tools = [
                    t for t in tools if t.category == ToolCategory.DATA_ACCESS
                ]
                for tool in policy_tools[:2]:
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
        self, tool: DiscoveredTool, query: MCPSafetyQuery
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
        self, query: MCPSafetyQuery, tool_results: Dict[str, Any], reasoning_chain: Optional[ReasoningChain] = None
    ) -> MCPSafetyResponse:
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
                    "content": """You are a Safety & Compliance Agent. Generate comprehensive responses based on user queries and tool execution results.

IMPORTANT: You MUST return ONLY valid JSON. Do not include any text before or after the JSON.

Return JSON format:
{
    "response_type": "safety_info",
    "data": {"incidents": [], "compliance": {}, "hazards": []},
    "natural_language": "Based on the tool results...",
    "recommendations": ["Recommendation 1", "Recommendation 2"],
    "confidence": 0.85,
    "actions_taken": [{"action": "tool_execution", "tool": "report_incident"}]
}

Response types based on intent:
- incident_reporting: "incident_reporting" with incident details and reporting status
- compliance_check: "compliance_check" with compliance status and violations
- safety_audit: "safety_audit" with audit results and findings
- hazard_identification: "hazard_identification" with identified hazards and risk levels
- policy_lookup: "policy_lookup" with policy details and requirements
- training_tracking: "training_tracking" with training status and completion

Include:
1. Natural language explanation of results
2. Structured data summary appropriate for the intent
3. Actionable recommendations
4. Confidence assessment

CRITICAL: Return ONLY the JSON object, no other text.""",
                },
                {
                    "role": "user",
                    "content": f"""User Query: "{sanitize_prompt_input(query.user_query)}"
Intent: {sanitize_prompt_input(query.intent)}
Entities: {sanitize_prompt_input(query.entities)}
Context: {sanitize_prompt_input(query.context)}

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
                    "response_type": "safety_info",
                    "data": {"results": successful_results},
                    "natural_language": f"Based on the available data, here's what I found regarding your safety query: {sanitize_prompt_input(query.user_query)}",
                    "recommendations": [
                        "Please review the safety status and take appropriate action if needed."
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
            
            return MCPSafetyResponse(
                response_type=response_data.get("response_type", "safety_info"),
                data=response_data.get("data", {}),
                natural_language=response_data.get("natural_language", ""),
                recommendations=response_data.get("recommendations", []),
                confidence=response_data.get("confidence", 0.7),
                actions_taken=response_data.get("actions_taken", []),
                mcp_tools_used=list(successful_results.keys()),
                tool_execution_results=tool_results,
                reasoning_chain=reasoning_chain,
                reasoning_steps=reasoning_steps,
            )

        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return MCPSafetyResponse(
                response_type="error",
                data={"error": str(e)},
                natural_language=f"I encountered an error generating a response: {str(e)}",
                recommendations=["Please try again or contact support."],
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
        
        # Causal reasoning for cause-effect questions (very important for safety)
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
        
        # For safety queries, always include causal reasoning
        if any(
            keyword in query_lower
            for keyword in ["safety", "incident", "hazard", "risk", "compliance", "accident"]
        ):
            if ReasoningType.CAUSAL not in reasoning_types:
                reasoning_types.append(ReasoningType.CAUSAL)
        
        return reasoning_types


# Global MCP safety agent instance
_mcp_safety_agent = None


async def get_mcp_safety_agent() -> MCPSafetyComplianceAgent:
    """Get the global MCP safety agent instance."""
    global _mcp_safety_agent
    if _mcp_safety_agent is None:
        _mcp_safety_agent = MCPSafetyComplianceAgent()
        await _mcp_safety_agent.initialize()
    return _mcp_safety_agent
