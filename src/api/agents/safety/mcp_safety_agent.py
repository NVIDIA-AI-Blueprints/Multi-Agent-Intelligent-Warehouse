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
from src.api.services.reasoning import (
    get_reasoning_engine,
    ReasoningType,
    ReasoningChain,
)
from src.api.utils.log_utils import sanitize_prompt_input
from src.api.services.agent_config import load_agent_config, AgentConfig
from src.api.services.validation import get_response_validator
from .action_tools import get_safety_action_tools

logger = logging.getLogger(__name__)


@dataclass
class MCPSafetyQuery:
    """MCP-enabled safety query."""

    intent: str
    entities: Dict[str, Any]
    context: Dict[str, Any]
    user_query: str
    mcp_tools: Optional[List[str]] = None  # Available MCP tools for this query
    tool_execution_plan: Optional[List[Dict[str, Any]]] = None  # Planned tool executions


@dataclass
class MCPSafetyResponse:
    """MCP-enabled safety response."""

    response_type: str
    data: Dict[str, Any]
    natural_language: str
    recommendations: List[str]
    confidence: float
    actions_taken: List[Dict[str, Any]]
    mcp_tools_used: Optional[List[str]] = None
    tool_execution_results: Optional[Dict[str, Any]] = None
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
        self.config: Optional[AgentConfig] = None  # Agent configuration

    async def initialize(self) -> None:
        """Initialize the agent with required services including MCP."""
        try:
            # Load agent configuration
            self.config = load_agent_config("safety")
            logger.info(f"Loaded agent configuration: {self.config.name}")
            
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

                    # Skip reasoning for simple queries to improve performance
                    simple_query_indicators = ["procedure", "checklist", "what are", "show me", "safety"]
                    is_simple_query = any(indicator in query.lower() for indicator in simple_query_indicators) and len(query.split()) < 20
                    
                    if is_simple_query:
                        logger.info(f"Skipping reasoning for simple safety query to improve performance: {query[:50]}")
                        reasoning_chain = None
                    else:
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
            # Fast path: Try keyword-based parsing first for simple queries
            query_lower = query.lower()
            entities = {}
            intent = "incident_reporting"  # Default intent
            
            # Quick intent detection based on keywords
            if any(word in query_lower for word in ["procedure", "checklist", "policy", "what are"]):
                intent = "policy_lookup"
            elif any(word in query_lower for word in ["report", "incident", "alert", "issue"]):
                intent = "incident_reporting"
            elif any(word in query_lower for word in ["compliance", "audit"]):
                intent = "compliance_check"
            
            # Quick entity extraction using fallback parser
            fallback_entities = self._fallback_parse_safety_query(query)
            entities.update(fallback_entities)
            
            # For simple policy/procedure queries, use keyword-based parsing (faster, no LLM call)
            simple_query_indicators = [
                "procedure", "checklist", "what are", "show me", "safety"
            ]
            is_simple_query = (
                any(indicator in query_lower for indicator in simple_query_indicators) and
                len(query.split()) < 20 and  # Short queries
                intent == "policy_lookup"  # Only for policy lookups
            )
            
            if is_simple_query:
                logger.info(f"Using fast keyword-based parsing for simple safety query: {query[:50]}")
                # Ensure critical entities are present
                if not entities.get("description"):
                    entities["description"] = query
                if not entities.get("reporter"):
                    entities["reporter"] = "user"
                
                return MCPSafetyQuery(
                    intent=intent,
                    entities=entities,
                    context=context or {},
                    user_query=query,
                )
            
            # For complex queries, use LLM parsing
            # Use LLM to parse the query with better entity extraction
            parse_prompt = [
                {
                    "role": "system",
                    "content": """You are a safety and compliance expert. Parse warehouse safety queries and extract intent, entities, and context.

Return JSON format:
{
    "intent": "incident_reporting",
    "entities": {
        "incident_type": "flooding",
        "location": "Zone A",
        "severity": "critical",
        "description": "flooding in Zone A",
        "reporter": "user"
    },
    "context": {"priority": "high", "severity": "critical"}
}

Intent options: incident_reporting, compliance_check, safety_audit, hazard_identification, policy_lookup, training_tracking

CRITICAL: Extract ALL relevant entities from the query:
- incident_type: flooding, fire, spill, leak, accident, injury, hazard, etc.
- location: Zone A, Zone B, Dock D2, warehouse, etc.
- severity: critical, high, medium, low (infer from incident type - flooding/fire/spill = critical)
- description: full description of the issue
- reporter: "user" or "system"

Examples:
- "we have an issue with flooding in Zone A" → {"intent": "incident_reporting", "entities": {"incident_type": "flooding", "location": "Zone A", "severity": "critical", "description": "flooding in Zone A"}, "context": {"priority": "high", "severity": "critical"}}
- "Report a safety incident in Zone A" → {"intent": "incident_reporting", "entities": {"location": "Zone A", "severity": "high"}, "context": {"priority": "high"}}
- "What are the safety procedures for forklift operations?" → {"intent": "policy_lookup", "entities": {"equipment": "forklift", "query": "safety procedures for forklift operations"}, "context": {"priority": "normal"}}

Return only valid JSON.""",
                },
                {
                    "role": "user",
                    "content": f'Query: "{query}"\nContext: {context or {}}',
                },
            ]

            response = await self.nim_client.generate_response(parse_prompt, temperature=0.0)

            # Parse JSON response
            try:
                parsed_data = json.loads(response.content)
            except json.JSONDecodeError:
                # Fallback parsing with keyword extraction
                parsed_data = self._fallback_parse_safety_query(query)
            
            # Ensure critical entities are present
            entities = parsed_data.get("entities", {})
            if not entities.get("description"):
                entities["description"] = query
            if not entities.get("reporter"):
                entities["reporter"] = "user"
            
            # Infer severity from incident type if missing
            incident_type = entities.get("incident_type", "").lower()
            if not entities.get("severity"):
                if incident_type in ["flooding", "flood", "fire", "spill", "leak", "explosion"]:
                    entities["severity"] = "critical"
                elif incident_type in ["accident", "injury", "hazard"]:
                    entities["severity"] = "high"
                else:
                    entities["severity"] = "medium"

            return MCPSafetyQuery(
                intent=parsed_data.get("intent", "incident_reporting"),
                entities=entities,
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

    def _add_tools_to_execution_plan(
        self,
        execution_plan: List[Dict[str, Any]],
        tools: List[DiscoveredTool],
        categories: List[ToolCategory],
        limit: int,
        query: MCPSafetyQuery,
    ) -> None:
        """
        Add tools to execution plan based on categories and limit.
        
        Args:
            execution_plan: Execution plan list to append to
            tools: List of available tools
            categories: List of tool categories to filter
            limit: Maximum number of tools to add
            query: Query object for argument preparation
        """
        filtered_tools = [t for t in tools if t.category in categories]
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
        self, query: MCPSafetyQuery, tools: List[DiscoveredTool]
    ) -> List[Dict[str, Any]]:
        """Create a plan for executing MCP tools."""
        try:
            execution_plan = []

            # For incident reporting (flooding, fire, etc.), prioritize getting safety procedures first
            if query.intent == "incident_reporting":
                # First, get safety procedures for the incident type
                procedures_tool = next((t for t in tools if t.tool_id == "get_safety_procedures"), None)
                if procedures_tool:
                    execution_plan.append({
                        "tool_id": procedures_tool.tool_id,
                        "tool_name": procedures_tool.name,
                        "arguments": self._prepare_tool_arguments(procedures_tool, query),
                        "priority": 1,
                        "required": True,
                    })
                
                # Then, try to log the incident if we have required entities
                if query.entities.get("severity") and query.entities.get("description"):
                    log_incident_tool = next((t for t in tools if t.tool_id == "log_incident"), None)
                    if log_incident_tool:
                        execution_plan.append({
                            "tool_id": log_incident_tool.tool_id,
                            "tool_name": log_incident_tool.name,
                            "arguments": self._prepare_tool_arguments(log_incident_tool, query),
                            "priority": 2,
                            "required": False,  # Not required if missing entities
                        })
                
                # For critical incidents, also broadcast alert
                if query.entities.get("severity") == "critical" and query.entities.get("message"):
                    broadcast_tool = next((t for t in tools if t.tool_id == "broadcast_alert"), None)
                    if broadcast_tool:
                        execution_plan.append({
                            "tool_id": broadcast_tool.tool_id,
                            "tool_name": broadcast_tool.name,
                            "arguments": self._prepare_tool_arguments(broadcast_tool, query),
                            "priority": 3,
                            "required": False,
                        })
            elif query.intent == "policy_lookup":
                # For policy lookup, use get_safety_procedures
                procedures_tool = next((t for t in tools if t.tool_id == "get_safety_procedures"), None)
                if procedures_tool:
                    execution_plan.append({
                        "tool_id": procedures_tool.tool_id,
                        "tool_name": procedures_tool.name,
                        "arguments": self._prepare_tool_arguments(procedures_tool, query),
                        "priority": 1,
                        "required": True,
                    })
            else:
                # For other intents, use the original logic
                intent_config = {
                    "compliance_check": ([ToolCategory.SAFETY, ToolCategory.DATA_ACCESS], 2),
                    "safety_audit": ([ToolCategory.SAFETY], 3),
                    "hazard_identification": ([ToolCategory.SAFETY], 2),
                    "training_tracking": ([ToolCategory.SAFETY], 2),
                }
                
                categories, limit = intent_config.get(
                    query.intent, ([ToolCategory.SAFETY], 2)
                )
                self._add_tools_to_execution_plan(
                    execution_plan, tools, categories, limit, query
                )

            # If no tools were added, add any available safety tools as fallback
            if not execution_plan and tools:
                for tool in tools[:3]:
                    execution_plan.append({
                        "tool_id": tool.tool_id,
                        "tool_name": tool.name,
                        "arguments": self._prepare_tool_arguments(tool, query),
                        "priority": 5,
                        "required": False,
                    })

            # Sort by priority
            execution_plan.sort(key=lambda x: x["priority"])

            return execution_plan

        except Exception as e:
            logger.error(f"Error creating tool execution plan: {e}")
            return []

    def _prepare_tool_arguments(
        self, tool: DiscoveredTool, query: MCPSafetyQuery
    ) -> Dict[str, Any]:
        """Prepare arguments for tool execution based on query entities and intelligent extraction."""
        arguments = {}
        query_lower = query.user_query.lower()

        # Extract parameter properties - handle both JSON Schema format and flat dict format
        if isinstance(tool.parameters, dict) and "properties" in tool.parameters:
            # JSON Schema format: {"type": "object", "properties": {...}, "required": [...]}
            param_properties = tool.parameters.get("properties", {})
            required_params = tool.parameters.get("required", [])
        else:
            # Flat dict format: {param_name: param_schema, ...}
            param_properties = tool.parameters
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
            # Intelligent parameter extraction for severity
            elif param_name == "severity":
                if "severity" in query.entities:
                    arguments[param_name] = query.entities["severity"]
                else:
                    # Extract from query context
                    if any(word in query_lower for word in ["critical", "emergency", "urgent", "severe"]):
                        arguments[param_name] = "critical"
                    elif any(word in query_lower for word in ["high", "serious", "major"]):
                        arguments[param_name] = "high"
                    elif any(word in query_lower for word in ["low", "minor", "small"]):
                        arguments[param_name] = "low"
                    else:
                        arguments[param_name] = "medium"  # Default
            # Intelligent parameter extraction for checklist_type
            elif param_name == "checklist_type":
                if "checklist_type" in query.entities:
                    arguments[param_name] = query.entities["checklist_type"]
                else:
                    # Infer from incident type or query context
                    incident_type = query.entities.get("incident_type", "").lower()
                    if not incident_type:
                        # Try to infer from query
                        if any(word in query_lower for word in ["flooding", "flood", "water"]):
                            incident_type = "flooding"
                        elif any(word in query_lower for word in ["fire", "burning", "smoke"]):
                            incident_type = "fire"
                        elif any(word in query_lower for word in ["spill", "chemical", "hazardous"]):
                            incident_type = "spill"
                        elif any(word in query_lower for word in ["over-temp", "over temp", "temperature", "overheating"]):
                            incident_type = "over_temp"
                    
                    # Map incident type to checklist type
                    if incident_type in ["flooding", "flood", "water"]:
                        arguments[param_name] = "emergency_response"
                    elif incident_type in ["fire", "burning", "smoke"]:
                        arguments[param_name] = "fire_safety"
                    elif incident_type in ["spill", "chemical", "hazardous"]:
                        arguments[param_name] = "hazardous_material"
                    elif incident_type in ["over-temp", "over temp", "temperature", "overheating"]:
                        arguments[param_name] = "equipment_safety"
                    else:
                        arguments[param_name] = "general_safety"  # Default
            # Intelligent parameter extraction for message (broadcast_alert)
            elif param_name == "message":
                if "message" in query.entities:
                    arguments[param_name] = query.entities["message"]
                else:
                    # Generate message from query context
                    location = query.entities.get("location", "the facility")
                    incident_type = query.entities.get("incident_type", "incident")
                    severity = query.entities.get("severity", "medium")
                    
                    # Create a descriptive alert message
                    if "over-temp" in query_lower or "over temp" in query_lower or "temperature" in query_lower:
                        arguments[param_name] = f"Immediate Attention: Machine Over-Temp at {location} - Area Caution Advised"
                    elif "fire" in query_lower:
                        arguments[param_name] = f"URGENT: Fire Alert at {location} - Evacuate Immediately"
                    elif "flood" in query_lower or "water" in query_lower:
                        arguments[param_name] = f"URGENT: Flooding Alert at {location} - Secure Equipment and Evacuate"
                    elif "spill" in query_lower:
                        arguments[param_name] = f"URGENT: Chemical Spill at {location} - Secure Area and Follow Safety Protocols"
                    else:
                        # Generic alert message
                        severity_text = severity.upper() if severity else "MEDIUM"
                        arguments[param_name] = f"{severity_text} Severity Safety Alert at {location}: {query.user_query[:100]}"
            # Intelligent parameter extraction for description
            elif param_name == "description":
                if "description" in query.entities:
                    arguments[param_name] = query.entities["description"]
                else:
                    arguments[param_name] = query.user_query  # Use full query as description
            # Intelligent parameter extraction for assignee
            elif param_name == "assignee":
                if "assignee" in query.entities:
                    arguments[param_name] = query.entities["assignee"]
                elif "reported_by" in query.entities:
                    arguments[param_name] = query.entities["reported_by"]
                elif "employee_name" in query.entities:
                    arguments[param_name] = query.entities["employee_name"]
                else:
                    # Extract from query or use default
                    # Try to find employee/worker names in query
                    employee_match = re.search(r'(?:employee|worker|staff|personnel|operator)\s+([A-Za-z0-9_]+)', query_lower)
                    if employee_match:
                        arguments[param_name] = employee_match.group(1)
                    else:
                        # Default to "Safety Team" if not specified
                        arguments[param_name] = "Safety Team"
            # Intelligent parameter extraction for location
            elif param_name == "location":
                if "location" in query.entities:
                    arguments[param_name] = query.entities["location"]
                else:
                    # Extract location from query
                    zone_match = re.search(r'zone\s+([a-z])', query_lower)
                    if zone_match:
                        arguments[param_name] = f"Zone {zone_match.group(1).upper()}"
                    else:
                        dock_match = re.search(r'dock\s+([a-z0-9]+)', query_lower)
                        if dock_match:
                            arguments[param_name] = f"Dock {dock_match.group(1).upper()}"
                        else:
                            arguments[param_name] = "Unknown Location"
            # Intelligent parameter extraction for incident_type
            elif param_name == "incident_type":
                if "incident_type" in query.entities:
                    arguments[param_name] = query.entities["incident_type"]
                else:
                    # Infer from query
                    if any(word in query_lower for word in ["over-temp", "over temp", "temperature", "overheating"]):
                        arguments[param_name] = "over_temp"
                    elif any(word in query_lower for word in ["fire", "burning", "smoke"]):
                        arguments[param_name] = "fire"
                    elif any(word in query_lower for word in ["flood", "flooding", "water"]):
                        arguments[param_name] = "flooding"
                    elif any(word in query_lower for word in ["spill", "chemical"]):
                        arguments[param_name] = "spill"
                    else:
                        arguments[param_name] = "general"

        return arguments
    
    def _fallback_parse_safety_query(self, query: str) -> Dict[str, Any]:
        """Fallback parsing using keyword matching when LLM parsing fails."""
        query_lower = query.lower()
        entities = {}
        
        # Extract location (re is already imported at module level)
        zone_match = re.search(r'zone\s+([a-z])', query_lower)
        if zone_match:
            entities["location"] = f"Zone {zone_match.group(1).upper()}"
        
        dock_match = re.search(r'dock\s+([a-z0-9]+)', query_lower)
        if dock_match:
            entities["location"] = f"Dock {dock_match.group(1).upper()}"
        
        # Extract incident type
        if "flooding" in query_lower or "flood" in query_lower:
            entities["incident_type"] = "flooding"
            entities["severity"] = "critical"
        elif "fire" in query_lower:
            entities["incident_type"] = "fire"
            entities["severity"] = "critical"
        elif "spill" in query_lower:
            entities["incident_type"] = "spill"
            entities["severity"] = "critical"
        elif "issue" in query_lower or "problem" in query_lower:
            entities["incident_type"] = "general"
            entities["severity"] = "high"
        
        # Extract description
        entities["description"] = query
        
        # Determine intent
        if any(keyword in query_lower for keyword in ["issue", "problem", "flooding", "fire", "spill", "incident", "report"]):
            intent = "incident_reporting"
        elif any(keyword in query_lower for keyword in ["procedure", "policy", "guideline"]):
            intent = "policy_lookup"
        else:
            intent = "incident_reporting"
        
        return {
            "intent": intent,
            "entities": entities,
            "context": {"priority": "high" if entities.get("severity") == "critical" else "normal"}
        }

    async def _execute_tool_plan(
        self, execution_plan: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Execute the tool execution plan in parallel where possible."""
        results = {}
        
        if not execution_plan:
            logger.warning("Tool execution plan is empty - no tools to execute")
            return results

        async def execute_single_tool(step: Dict[str, Any]) -> tuple:
            """Execute a single tool and return (tool_id, result_dict)."""
            tool_id = step["tool_id"]
            tool_name = step["tool_name"]
            arguments = step["arguments"]
            
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

        # Execute all tools in parallel
        execution_tasks = [execute_single_tool(step) for step in execution_plan]
        execution_results = await asyncio.gather(*execution_tasks, return_exceptions=True)
        
        # Process results
        for result in execution_results:
            if isinstance(result, Exception):
                logger.error(f"Unexpected error in tool execution: {result}")
                continue
            
            tool_id, result_dict = result
            results[tool_id] = result_dict

        logger.info(f"Executed {len(execution_plan)} tools in parallel, {len([r for r in results.values() if r.get('success')])} successful")
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

            # Load response prompt from configuration
            if self.config is None:
                self.config = load_agent_config("safety")
            
            response_prompt_template = self.config.persona.response_prompt
            system_prompt = self.config.persona.system_prompt
            
            # Format the response prompt with actual values
            formatted_response_prompt = response_prompt_template.format(
                user_query=sanitize_prompt_input(query.user_query),
                intent=sanitize_prompt_input(query.intent),
                entities=json.dumps(query.entities, default=str),
                retrieved_data=json.dumps(successful_results, indent=2, default=str),
                actions_taken=json.dumps(tool_results, indent=2, default=str),
                reasoning_analysis="",
                conversation_history=""
            )
            
            # Create response prompt with very explicit instructions
            enhanced_system_prompt = system_prompt + """

CRITICAL JSON FORMAT REQUIREMENTS:
1. Return ONLY a valid JSON object - no markdown, no code blocks, no explanations before or after
2. Your response must start with { and end with }
3. The 'natural_language' field is MANDATORY and must contain a detailed, informative response
4. Do NOT put safety data at the top level - all data (policies, hazards, incidents) must be inside the 'data' field
5. The 'natural_language' field must directly answer the user's question with specific details

REQUIRED JSON STRUCTURE:
{
    "response_type": "safety_info",
    "data": {
        "policies": [...],
        "hazards": [...],
        "incidents": [...]
    },
    "natural_language": "Based on your query about [user query], I found the following safety information: [specific details including policy names, hazard types, incident details, etc.]. [Additional context and recommendations].",
    "recommendations": ["Recommendation 1", "Recommendation 2"],
    "confidence": 0.85,
    "actions_taken": [...]
}

ABSOLUTELY CRITICAL:
- The 'natural_language' field is REQUIRED and must not be empty
- Include specific safety details (policy names, hazard types, incident details) in natural_language
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
                logger.info(f"Successfully parsed LLM response: {response_data}")
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse LLM response as JSON: {e}")
                logger.warning(f"Raw LLM response: {response.content[:500]}")
                # Fallback response - use the text content but clean it
                natural_lang = response.content
                # Remove any JSON-like structures from the text
                natural_lang = re.sub(r"\{[^{}]*'tool_execution_results'[^{}]*\}", "", natural_lang)
                natural_lang = re.sub(r"'tool_execution_results':\s*\{\}", "", natural_lang)
                natural_lang = re.sub(r"tool_execution_results:\s*\{\}", "", natural_lang)
                natural_lang = natural_lang.strip()
                
                response_data = {
                    "response_type": "safety_info",
                    "data": {"results": successful_results},
                    "natural_language": natural_lang if natural_lang else f"Based on the available data, here's what I found regarding your safety query: {sanitize_prompt_input(query.user_query)}",
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
            
            # Ensure natural_language is not empty - if missing, ask LLM to generate it
            natural_language = response_data.get("natural_language", "")
            if not natural_language or natural_language.strip() == "":
                logger.warning("LLM did not return natural_language field. Requesting LLM to generate it from the response data.")
                
                # Prepare data for LLM to generate natural_language
                data_for_generation = response_data.copy()
                if "data" in data_for_generation and isinstance(data_for_generation["data"], dict):
                    # Include data field content
                    pass
                
                # Also include tool results in the prompt
                tool_results_summary = {}
                for tool_id, result_data in successful_results.items():
                    result = result_data.get("result", {})
                    if isinstance(result, dict):
                        tool_results_summary[tool_id] = {
                            "tool_name": result_data.get("tool_name", tool_id),
                            "result_summary": str(result)[:500]  # Limit length
                        }
                
                # Ask LLM to generate natural_language from the response data
                generation_prompt = [
                    {
                        "role": "system",
                        "content": """You are a certified warehouse safety and compliance expert. 
Generate a comprehensive, expert-level natural language response based on the provided data.

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
- Start with the actual information or what was accomplished (e.g., "Forklift operations require..." or "A high-severity incident has been logged...")
- Write as if explaining to a colleague, not referencing the query
- DO NOT say "Here's the response:" or "Here's what I found:" - just provide the information directly

Your response must be detailed, informative, and directly answer the user's query WITHOUT echoing it.
Include specific details from the data (policy names, requirements, hazard types, incident details, etc.) naturally woven into the explanation.
Provide expert-level analysis and context."""
                    },
                    {
                        "role": "user",
                        "content": f"""The user asked: "{query.user_query}"

The system retrieved the following data:
{json.dumps(data_for_generation, indent=2, default=str)[:2000]}

Tool execution results:
{json.dumps(tool_results_summary, indent=2, default=str)[:1000]}

Generate a comprehensive, expert-level natural language response that:
1. Directly answers the user's query WITHOUT echoing the query
2. Starts immediately with the information (e.g., "Forklift operations require..." or "A high-severity incident has been logged...")
3. NEVER starts with "You asked", "You requested", "I'll", "Let me", "Here's the response", etc.
4. Includes specific details from the retrieved data naturally woven into the explanation
5. Provides expert analysis and recommendations with context
6. Is written in a clear, natural, conversational tone - like explaining to a colleague
7. Uses varied sentence structure and flows naturally
8. Is comprehensive but concise (typically 2-4 well-formed paragraphs)

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
                    natural_language = f"I've processed your safety query: {sanitize_prompt_input(query.user_query)}. Please review the structured data for details."
            
            # Ensure recommendations are populated - if missing, ask LLM to generate them
            recommendations = response_data.get("recommendations", [])
            if not recommendations or (isinstance(recommendations, list) and len(recommendations) == 0):
                logger.info("LLM did not return recommendations. Requesting LLM to generate expert recommendations.")
                
                # Ask LLM to generate recommendations based on the query and data
                recommendations_prompt = [
                    {
                        "role": "system",
                        "content": """You are a certified warehouse safety and compliance expert. 
Generate actionable, expert-level recommendations based on the user's query and retrieved data.
Recommendations should be specific, practical, and based on safety best practices and regulatory requirements."""
                    },
                    {
                        "role": "user",
                        "content": f"""The user asked: "{query.user_query}"
Query intent: {query.intent}
Query entities: {json.dumps(query.entities, default=str)}

Retrieved data:
{json.dumps(response_data, indent=2, default=str)[:1500]}

Generate 3-5 actionable, expert-level recommendations that:
1. Are specific to the user's query and the retrieved data
2. Follow safety best practices and regulatory requirements
3. Are practical and implementable
4. Address the specific context (intent, entities, data)

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
                    # Try to extract JSON array (re is already imported at module level)
                    json_match = re.search(r'\[.*?\]', rec_text, re.DOTALL)
                    if json_match:
                        recommendations = json.loads(json_match.group(0))
                    else:
                        # Fallback: split by lines if not JSON
                        recommendations = [line.strip() for line in rec_text.split('\n') if line.strip() and line.strip().startswith('-') or line.strip().startswith('•')]
                        if not recommendations:
                            recommendations = [rec_text]
                    logger.info(f"LLM generated {len(recommendations)} recommendations")
                except Exception as e:
                    logger.error(f"Failed to generate recommendations from LLM: {e}", exc_info=True)
                    recommendations = []  # Empty rather than hardcoded
            
            # Ensure actions_taken are populated
            actions_taken = response_data.get("actions_taken", [])
            if not actions_taken or (isinstance(actions_taken, list) and len(actions_taken) == 0):
                # Generate actions_taken from tool execution
                actions_taken = []
                for tool_id, result_data in successful_results.items():
                    tool_name = result_data.get("tool_name", tool_id)
                    actions_taken.append({
                        "action": f"Executed {tool_name}",
                        "tool_id": tool_id,
                        "status": "success" if result_data.get("success") else "failed",
                        "details": f"Retrieved safety information using {tool_name}"
                    })
                if not actions_taken and successful_results:
                    actions_taken.append({
                        "action": "mcp_tool_execution",
                        "tools_used": len(successful_results),
                        "status": "success"
                    })
            
            # Ensure data field is populated
            data = response_data.get("data", {})
            if not data or (isinstance(data, dict) and len(data) == 0):
                # Populate data from tool results
                data = {"tool_results": successful_results}
                if query.intent == "incident_reporting":
                    data["incident"] = {
                        "type": query.entities.get("incident_type", "unknown"),
                        "location": query.entities.get("location", "unknown"),
                        "severity": query.entities.get("severity", "medium"),
                        "description": query.entities.get("description", query.user_query)
                    }
            
            # Validate response quality
            try:
                validator = get_response_validator()
                validation_result = validator.validate(
                    response={
                        "natural_language": natural_language,
                        "confidence": response_data.get("confidence", 0.7),
                        "response_type": response_data.get("response_type", "safety_info"),
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
            
            return MCPSafetyResponse(
                response_type=response_data.get("response_type", "safety_info"),
                data=data,
                natural_language=natural_language,
                recommendations=recommendations,
                confidence=final_confidence,
                actions_taken=actions_taken,
                mcp_tools_used=list(successful_results.keys()),
                tool_execution_results=tool_results,
                reasoning_chain=reasoning_chain,
                reasoning_steps=reasoning_steps,
            )

        except Exception as e:
            logger.error(f"Error generating response: {e}", exc_info=True)
            # Provide user-friendly error message without exposing internal errors
            error_message = "I encountered an error while processing your safety query. Please try rephrasing your question or contact support if the issue persists."
            return MCPSafetyResponse(
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
