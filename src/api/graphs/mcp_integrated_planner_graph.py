"""
MCP-Enabled Warehouse Operational Assistant - Planner/Router Graph
Integrates MCP framework with main agent workflow for dynamic tool discovery and execution.

This module implements the MCP-enhanced planner/router agent that:
1. Analyzes user intents using MCP-based classification
2. Routes to appropriate MCP-enabled specialized agents
3. Coordinates multi-agent workflows with dynamic tool binding
4. Synthesizes responses from multiple agents with MCP tool results
"""

from typing import Dict, List, Optional, TypedDict, Annotated, Any
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from dataclasses import asdict
import logging
import asyncio
import threading

from src.api.services.mcp.tool_discovery import ToolDiscoveryService
from src.api.services.mcp.tool_binding import ToolBindingService
from src.api.services.mcp.tool_routing import ToolRoutingService, RoutingStrategy
from src.api.services.mcp.tool_validation import ToolValidationService
from src.api.services.mcp.base import MCPManager

logger = logging.getLogger(__name__)


class MCPWarehouseState(TypedDict):
    """Enhanced state management for MCP-enabled warehouse assistant workflow."""

    messages: Annotated[List[BaseMessage], "Chat messages"]
    user_intent: Optional[str]
    routing_decision: Optional[str]
    agent_responses: Dict[str, str]
    final_response: Optional[str]
    context: Dict[str, any]
    session_id: str
    mcp_results: Optional[Any]  # MCP execution results
    tool_execution_plan: Optional[List[Dict[str, Any]]]  # Planned tool executions
    available_tools: Optional[List[Dict[str, Any]]]  # Available MCP tools
    enable_reasoning: bool  # Enable advanced reasoning
    reasoning_types: Optional[List[str]]  # Specific reasoning types to use
    reasoning_chain: Optional[Dict[str, Any]]  # Reasoning chain from agents


class MCPIntentClassifier:
    """MCP-enhanced intent classifier with dynamic tool discovery."""

    def __init__(self, tool_discovery: ToolDiscoveryService):
        self.tool_discovery = tool_discovery
        self.tool_routing = None  # Will be set by MCP planner graph

    EQUIPMENT_KEYWORDS = [
        "equipment",
        "forklift",
        "conveyor",
        "scanner",
        "amr",
        "agv",
        "charger",
        "assignment",
        "utilization",
        "maintenance",
        "availability",
        "telemetry",
        "battery",
        "truck",
        "lane",
        "pm",
        "loto",
        "lockout",
        "tagout",
        "sku",
        "stock",
        "inventory",
        "quantity",
        "available",
        "atp",
        "on_hand",
    ]

    OPERATIONS_KEYWORDS = [
        "shift",
        "task",
        "tasks",
        "workforce",
        "pick",
        "pack",
        "putaway",
        "schedule",
        "assignment",
        "kpi",
        "performance",
        "equipment",
        "main",
        "today",
        "work",
        "job",
        "operation",
        "operations",
        "worker",
        "workers",
        "team",
        "team members",
        "staff",
        "employee",
        "employees",
        "active workers",
        "how many",
        "roles",
        "team members",
        "wave",
        "waves",
        "order",
        "orders",
        "zone",
        "zones",
        "line",
        "lines",
        "create",
        "generating",
        "pick wave",
        "pick waves",
        "order management",
        "zone a",
        "zone b",
        "zone c",
    ]

    SAFETY_KEYWORDS = [
        "safety",
        "incident",
        "compliance",
        "policy",
        "checklist",
        "hazard",
        "accident",
        "protocol",
        "training",
        "audit",
        "over-temp",
        "overtemp",
        "temperature",
        "event",
        "detected",
        "alert",
        "warning",
        "emergency",
        "malfunction",
        "failure",
        "ppe",
        "protective",
        "helmet",
        "gloves",
        "boots",
        "safety harness",
        "procedures",
        "guidelines",
        "standards",
        "regulations",
        "evacuation",
        "fire",
        "chemical",
        "lockout",
        "tagout",
        "loto",
        "injury",
        "report",
        "investigation",
        "corrective",
        "action",
        "issues",
        "problem",
        "concern",
        "violation",
        "breach",
    ]

    DOCUMENT_KEYWORDS = [
        "document",
        "upload",
        "scan",
        "extract",
        "process",
        "pdf",
        "image",
        "invoice",
        "receipt",
        "bol",
        "bill of lading",
        "purchase order",
        "po",
        "quality",
        "validation",
        "approve",
        "review",
        "ocr",
        "text extraction",
        "file",
        "photo",
        "picture",
        "documentation",
        "paperwork",
        "neural",
        "nemo",
        "retriever",
        "parse",
        "vision",
        "multimodal",
        "document processing",
        "document analytics",
        "document search",
        "document status",
    ]

    async def classify_intent_with_mcp(self, message: str) -> str:
        """Classify user intent using MCP tool discovery for enhanced accuracy."""
        try:
            # First, use traditional keyword-based classification
            base_intent = self.classify_intent(message)

            # If we have MCP tools available, use them to enhance classification
            # Only override if base_intent is "general" (uncertain) - don't override specific classifications
            if self.tool_discovery and len(self.tool_discovery.discovered_tools) > 0 and base_intent == "general":
                # Search for tools that might help with intent classification
                relevant_tools = await self.tool_discovery.search_tools(message)
                
                # If we found relevant tools, use them to refine the intent
                if relevant_tools:
                    # Use tool categories to refine intent when base classification is uncertain
                    for tool in relevant_tools[:3]:  # Check top 3 most relevant tools
                        if (
                            "equipment" in tool.name.lower()
                            or "equipment" in tool.description.lower()
                        ):
                            return "equipment"
                        elif (
                            "operations" in tool.name.lower()
                            or "workforce" in tool.description.lower()
                        ):
                            return "operations"
                        elif (
                            "safety" in tool.name.lower()
                            or "incident" in tool.description.lower()
                        ):
                            return "safety"

            return base_intent

        except Exception as e:
            logger.error(f"Error in MCP intent classification: {e}")
            return self.classify_intent(message)

    FORECASTING_KEYWORDS = [
        "forecast",
        "forecasting",
        "demand forecast",
        "demand prediction",
        "predict demand",
        "sales forecast",
        "inventory forecast",
        "reorder recommendation",
        "model performance",
        "forecast accuracy",
        "mape",
        "model metrics",
        "business intelligence",
        "forecast dashboard",
        "sku forecast",
        "demand planning",
        "predict",
        "prediction",
        "trend",
        "projection",
    ]

    @classmethod
    def classify_intent(cls, message: str) -> str:
        """Enhanced intent classification with better logic and ambiguity handling."""
        message_lower = message.lower()
        
        # Check for forecasting-related keywords (high priority)
        forecasting_score = sum(
            1 for keyword in cls.FORECASTING_KEYWORDS if keyword in message_lower
        )
        if forecasting_score > 0:
            return "forecasting"

        # Check for specific safety-related queries first (highest priority)
        # Safety queries should take precedence over equipment/operations
        safety_score = sum(
            1 for keyword in cls.SAFETY_KEYWORDS if keyword in message_lower
        )
        
        # Emergency/urgent safety keywords that should always route to safety
        emergency_keywords = [
            "flooding", "flood", "fire", "spill", "leak", "urgent", "critical", 
            "emergency", "evacuate", "evacuation", "issue", "problem", "malfunction",
            "failure", "accident", "injury", "hazard", "danger", "unsafe"
        ]
        has_emergency = any(keyword in message_lower for keyword in emergency_keywords)
        
        # Safety context indicators (broader list)
        safety_context_indicators = [
            "procedure", "procedures", "policy", "policies", "incident", "incidents",
            "compliance", "safety", "ppe", "hazard", "hazards", "report", "reporting",
            "training", "audit", "checklist", "protocol", "guidelines", "standards",
            "regulations", "lockout", "tagout", "loto", "corrective", "action",
            "investigation", "violation", "breach", "concern", "flooding", "flood",
            "issue", "issues", "problem", "problems", "emergency", "urgent", "critical"
        ]
        
        # Route to safety if:
        # 1. Has emergency keywords (highest priority)
        # 2. Has safety keywords AND safety context indicators
        # 3. Has high safety score (multiple safety keywords)
        if has_emergency or (safety_score > 0 and any(
            indicator in message_lower for indicator in safety_context_indicators
        )) or safety_score >= 2:
            return "safety"

        # Check for document-related keywords (but only if it's clearly document-related)
        document_indicators = [
            "document",
            "upload",
            "scan",
            "extract",
            "pdf",
            "image",
            "invoice",
            "receipt",
            "bol",
            "bill of lading",
            "purchase order",
            "po",
            "quality",
            "validation",
            "approve",
            "review",
            "ocr",
            "text extraction",
            "file",
            "photo",
            "picture",
            "documentation",
            "paperwork",
            "neural",
            "nemo",
            "retriever",
            "parse",
            "vision",
            "multimodal",
            "document processing",
            "document analytics",
            "document search",
            "document status",
        ]
        if any(keyword in message_lower for keyword in document_indicators):
            return "document"

        # Check for equipment-specific queries (availability, status, assignment)
        # But only if it's not a workflow operation AND not a safety issue
        equipment_indicators = [
            "available", "availability", "status", "utilization", "maintenance",
            "telemetry", "assignment", "assign", "dispatch", "deploy"
        ]
        equipment_objects = [
            "forklift", "forklifts", "scanner", "scanners", "conveyor", "conveyors",
            "truck", "trucks", "amr", "agv", "equipment", "machine", "machines",
            "asset", "assets"
        ]

        # Exclude safety-related equipment queries
        safety_equipment_terms = [
            "safety", "incident", "accident", "hazard", "danger", "unsafe",
            "issue", "problem", "malfunction", "failure", "emergency", "urgent"
        ]
        is_safety_equipment_query = any(term in message_lower for term in safety_equipment_terms)

        # Only route to equipment if it's a pure equipment query (not workflow-related, not safety-related)
        workflow_terms = ["wave", "order", "create", "pick", "pack", "task", "workflow"]
        is_workflow_query = any(term in message_lower for term in workflow_terms)

        if (
            not is_workflow_query
            and not is_safety_equipment_query
            and any(indicator in message_lower for indicator in equipment_indicators)
            and any(obj in message_lower for obj in equipment_objects)
        ):
            return "equipment"

        # Check for operations-related keywords (workflow, tasks, management)
        operations_score = sum(
            1 for keyword in cls.OPERATIONS_KEYWORDS if keyword in message_lower
        )
        if operations_score > 0:
            # Prioritize operations for workflow-related terms
            workflow_terms = [
                "task",
                "wave",
                "order",
                "create",
                "pick",
                "pack",
                "management",
                "workflow",
                "dispatch",
            ]
            if any(term in message_lower for term in workflow_terms):
                return "operations"

        # Check for equipment-related keywords (fallback)
        equipment_score = sum(
            1 for keyword in cls.EQUIPMENT_KEYWORDS if keyword in message_lower
        )
        if equipment_score > 0:
            return "equipment"

        # Handle ambiguous queries
        ambiguous_patterns = [
            "inventory",
            "management",
            "help",
            "assistance",
            "support",
        ]
        if any(pattern in message_lower for pattern in ambiguous_patterns):
            return "ambiguous"

        # Default to equipment for general queries
        return "equipment"


class MCPPlannerGraph:
    """MCP-enabled planner graph for warehouse operations."""

    def __init__(self):
        self.tool_discovery: Optional[ToolDiscoveryService] = None
        self.tool_binding: Optional[ToolBindingService] = None
        self.tool_routing: Optional[ToolRoutingService] = None
        self.tool_validation: Optional[ToolValidationService] = None
        self.mcp_manager: Optional[MCPManager] = None
        self.intent_classifier: Optional[MCPIntentClassifier] = None
        self.graph = None
        self.initialized = False

    async def initialize(self) -> None:
        """Initialize MCP components and create the graph."""
        try:
            # Initialize MCP services (simplified for Phase 2 Step 3)
            self.tool_discovery = ToolDiscoveryService()
            self.tool_binding = ToolBindingService(self.tool_discovery)
            # Skip complex routing for now - will implement in next step
            self.tool_routing = None
            self.tool_validation = ToolValidationService(self.tool_discovery)
            self.mcp_manager = MCPManager()

            # Start tool discovery with timeout
            try:
                await asyncio.wait_for(
                    self.tool_discovery.start_discovery(),
                    timeout=2.0  # 2 second timeout for tool discovery
                )
            except asyncio.TimeoutError:
                logger.warning("Tool discovery timed out, continuing without full discovery")
            except Exception as discovery_error:
                logger.warning(f"Tool discovery failed: {discovery_error}, continuing without full discovery")

            # Initialize intent classifier with MCP
            self.intent_classifier = MCPIntentClassifier(self.tool_discovery)
            self.intent_classifier.tool_routing = self.tool_routing

            # Create the graph
            self.graph = self._create_graph()

            self.initialized = True
            logger.info("MCP Planner Graph initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize MCP Planner Graph: {e}")
            # Don't raise - allow system to continue with limited functionality
            # Set initialized to False so it can be retried
            self.initialized = False
            # Still try to create a basic graph for fallback
            try:
                self.graph = self._create_graph()
            except:
                self.graph = None

    def _create_graph(self) -> StateGraph:
        """Create the MCP-enabled planner graph."""
        # Initialize the state graph
        workflow = StateGraph(MCPWarehouseState)

        # Add nodes
        workflow.add_node("route_intent", self._mcp_route_intent)
        workflow.add_node("equipment", self._mcp_equipment_agent)
        workflow.add_node("operations", self._mcp_operations_agent)
        workflow.add_node("safety", self._mcp_safety_agent)
        workflow.add_node("forecasting", self._mcp_forecasting_agent)
        workflow.add_node("document", self._mcp_document_agent)
        workflow.add_node("general", self._mcp_general_agent)
        workflow.add_node("ambiguous", self._handle_ambiguous_query)
        workflow.add_node("synthesize", self._mcp_synthesize_response)

        # Set entry point
        workflow.set_entry_point("route_intent")

        # Add conditional edges for routing
        workflow.add_conditional_edges(
            "route_intent",
            self._route_to_agent,
            {
                "equipment": "equipment",
                "operations": "operations",
                "safety": "safety",
                "forecasting": "forecasting",
                "document": "document",
                "general": "general",
                "ambiguous": "ambiguous",
            },
        )

        # Add edges from agents to synthesis
        workflow.add_edge("equipment", "synthesize")
        workflow.add_edge("operations", "synthesize")
        workflow.add_edge("safety", "synthesize")
        workflow.add_edge("forecasting", "synthesize")
        workflow.add_edge("document", "synthesize")
        workflow.add_edge("general", "synthesize")
        workflow.add_edge("ambiguous", "synthesize")

        # Add edge from synthesis to end
        workflow.add_edge("synthesize", END)

        return workflow.compile()

    async def _mcp_route_intent(self, state: MCPWarehouseState) -> MCPWarehouseState:
        """Route user message using MCP-enhanced intent classification with semantic routing."""
        try:
            # Get the latest user message
            if not state["messages"]:
                state["user_intent"] = "general"
                state["routing_decision"] = "general"
                return state

            latest_message = state["messages"][-1]
            if isinstance(latest_message, HumanMessage):
                message_text = latest_message.content
            else:
                message_text = str(latest_message.content)

            # Use MCP-enhanced intent classification (keyword-based)
            keyword_intent = await self.intent_classifier.classify_intent_with_mcp(message_text)
            
            # Enhance with semantic routing
            try:
                from src.api.services.routing.semantic_router import get_semantic_router
                semantic_router = await get_semantic_router()
                intent, confidence = await semantic_router.classify_intent_semantic(
                    message_text,
                    keyword_intent,
                    keyword_confidence=0.7  # Assume medium-high confidence for keyword match
                )
                logger.info(f"Semantic routing: keyword={keyword_intent}, semantic={intent}, confidence={confidence:.2f}")
            except Exception as e:
                logger.warning(f"Semantic routing failed, using keyword-based: {e}")
                intent = keyword_intent
                confidence = 0.7
            
            state["user_intent"] = intent
            state["routing_decision"] = intent
            state["routing_confidence"] = confidence

            # Discover available tools for this query
            if self.tool_discovery:
                available_tools = await self.tool_discovery.get_available_tools()
                state["available_tools"] = [
                    {
                        "tool_id": tool.tool_id,
                        "name": tool.name,
                        "description": tool.description,
                        "category": tool.category.value,
                    }
                    for tool in available_tools
                ]

            logger.info(
                f"🔀 MCP Intent classified as: {intent} for message: {message_text[:100]}..."
            )
            logger.debug(
                f"Routing decision details - Intent: {intent}, Message: {message_text}, "
                f"Safety keywords found: {sum(1 for kw in MCPIntentClassifier.SAFETY_KEYWORDS if kw in message_text.lower())}, "
                f"Equipment keywords found: {sum(1 for kw in MCPIntentClassifier.EQUIPMENT_KEYWORDS if kw in message_text.lower())}"
            )

            # Handle ambiguous queries with clarifying questions
            if intent == "ambiguous":
                return await self._handle_ambiguous_query(state)

        except Exception as e:
            logger.error(f"❌ Error in MCP intent routing: {e}", exc_info=True)
            state["user_intent"] = "general"
            state["routing_decision"] = "general"

        return state

    async def _handle_ambiguous_query(
        self, state: MCPWarehouseState
    ) -> MCPWarehouseState:
        """Handle ambiguous queries with clarifying questions."""
        try:
            if not state["messages"]:
                return state

            latest_message = state["messages"][-1]
            if isinstance(latest_message, HumanMessage):
                message_text = latest_message.content
            else:
                message_text = str(latest_message.content)

            message_lower = message_text.lower()

            # Define clarifying questions based on ambiguous patterns
            clarifying_responses = {
                "inventory": {
                    "question": "I can help with inventory management. Are you looking for:",
                    "options": [
                        "Equipment inventory and status",
                        "Product inventory management",
                        "Inventory tracking and reporting",
                    ],
                },
                "management": {
                    "question": "What type of management do you need help with?",
                    "options": [
                        "Equipment management",
                        "Task management",
                        "Safety management",
                    ],
                },
                "help": {
                    "question": "I'm here to help! What would you like to do?",
                    "options": [
                        "Check equipment status",
                        "Create a task",
                        "View safety procedures",
                        "Upload a document",
                    ],
                },
                "assistance": {
                    "question": "I can assist you with warehouse operations. What do you need?",
                    "options": [
                        "Equipment assistance",
                        "Task assistance",
                        "Safety assistance",
                        "Document assistance",
                    ],
                },
            }

            # Find matching pattern
            for pattern, response in clarifying_responses.items():
                if pattern in message_lower:
                    # Create clarifying question response
                    clarifying_message = AIMessage(content=response["question"])
                    state["messages"].append(clarifying_message)

                    # Store clarifying context
                    state["context"]["clarifying"] = {
                        "text": response["question"],
                        "options": response["options"],
                        "original_query": message_text,
                    }

                    state["agent_responses"]["clarifying"] = response["question"]
                    state["final_response"] = response["question"]
                    return state

            # Default clarifying question
            default_response = {
                "question": "I can help with warehouse operations. What would you like to do?",
                "options": [
                    "Check equipment status",
                    "Create a task",
                    "View safety procedures",
                    "Upload a document",
                ],
            }

            clarifying_message = AIMessage(content=default_response["question"])
            state["messages"].append(clarifying_message)

            state["context"]["clarifying"] = {
                "text": default_response["question"],
                "options": default_response["options"],
                "original_query": message_text,
            }

            state["agent_responses"]["clarifying"] = default_response["question"]
            state["final_response"] = default_response["question"]

        except Exception as e:
            logger.error(f"Error handling ambiguous query: {e}")
            state["final_response"] = (
                "I'm not sure how to help with that. Could you please be more specific?"
            )

        return state

    async def _mcp_equipment_agent(self, state: MCPWarehouseState) -> MCPWarehouseState:
        """Handle equipment queries using MCP-enabled Equipment Agent."""
        try:
            from src.api.agents.inventory.mcp_equipment_agent import (
                get_mcp_equipment_agent,
            )

            # Get the latest user message
            if not state["messages"]:
                state["agent_responses"]["equipment"] = {
                    "natural_language": "No message to process",
                    "data": {},
                    "recommendations": [],
                    "confidence": 0.0,
                    "response_type": "error",
                }
                return state

            latest_message = state["messages"][-1]
            if isinstance(latest_message, HumanMessage):
                message_text = latest_message.content
            else:
                message_text = str(latest_message.content)

            # Get session ID from context
            session_id = state.get("session_id", "default")

            # Get MCP equipment agent with timeout
            try:
                mcp_equipment_agent = await asyncio.wait_for(
                    get_mcp_equipment_agent(),
                    timeout=5.0  # 5 second timeout for agent initialization
                )
            except asyncio.TimeoutError:
                logger.error("MCP equipment agent initialization timed out")
                raise
            except Exception as init_error:
                logger.error(f"MCP equipment agent initialization failed: {init_error}")
                raise

            # Extract reasoning parameters from state
            enable_reasoning = state.get("enable_reasoning", False)
            reasoning_types = state.get("reasoning_types")
            
            # Detect complex queries that need more processing time
            message_lower = message_text.lower()
            # Detect complex queries: analysis keywords, multiple actions, or long queries
            is_complex_query = (
                any(keyword in message_lower for keyword in [
                    "optimize", "optimization", "optimizing", "analyze", "analysis", "analyzing",
                    "relationship", "between", "compare", "evaluate", "correlation", "impact",
                    "effect", "factors", "consider", "considering", "recommend", "recommendation",
                    "strategy", "strategies", "improve", "improvement", "best practices"
                ]) or 
                # Multiple action keywords (create + dispatch, show + list, etc.)
                (message_lower.count(" and ") > 0 and any(action in message_lower for action in ["create", "dispatch", "assign", "show", "list", "get", "check"])) or
                len(message_text.split()) > 15
            )
            
            # Process with MCP equipment agent with timeout
            # Increase timeout for complex queries and reasoning queries
            if enable_reasoning:
                agent_timeout = 90.0  # 90s for reasoning queries
            elif is_complex_query:
                agent_timeout = 50.0  # 50s for complex queries (was 20s)
            else:
                agent_timeout = 45.0  # 45s for simple queries (increased from 30s to prevent timeouts)
            
            logger.info(f"Equipment agent timeout: {agent_timeout}s (complex: {is_complex_query}, reasoning: {enable_reasoning})")
            
            try:
                response = await asyncio.wait_for(
                    mcp_equipment_agent.process_query(
                        query=message_text,
                        session_id=session_id,
                        context=state.get("context", {}),
                        mcp_results=state.get("mcp_results"),
                        enable_reasoning=enable_reasoning,
                        reasoning_types=reasoning_types,
                    ),
                    timeout=agent_timeout
                )
            except asyncio.TimeoutError:
                logger.error(f"MCP equipment agent process_query timed out after {agent_timeout}s")
                raise TimeoutError(f"Equipment agent processing timed out after {agent_timeout}s")
            except Exception as process_error:
                logger.error(f"MCP equipment agent process_query failed: {process_error}")
                raise

            # Store the response (handle both dict and object responses)
            if isinstance(response, dict):
                state["agent_responses"]["equipment"] = response
            else:
                # Convert response object to dict
                state["agent_responses"]["equipment"] = {
                    "natural_language": response.natural_language if hasattr(response, "natural_language") else str(response),
                    "data": response.data if hasattr(response, "data") else {},
                    "recommendations": response.recommendations if hasattr(response, "recommendations") else [],
                    "confidence": response.confidence if hasattr(response, "confidence") else 0.0,
                    "response_type": response.response_type if hasattr(response, "response_type") else "equipment_info",
                    "mcp_tools_used": response.mcp_tools_used or [] if hasattr(response, "mcp_tools_used") else [],
                    "tool_execution_results": response.tool_execution_results or {} if hasattr(response, "tool_execution_results") else {},
                    "actions_taken": response.actions_taken or [] if hasattr(response, "actions_taken") else [],
                    "reasoning_chain": response.reasoning_chain if hasattr(response, "reasoning_chain") else None,
                    "reasoning_steps": response.reasoning_steps if hasattr(response, "reasoning_steps") else None,
                }

            logger.info(
                f"MCP Equipment agent processed request with confidence: {response.confidence}"
            )

        except asyncio.TimeoutError as e:
            logger.error(f"Timeout in MCP equipment agent: {e}")
            state["agent_responses"]["equipment"] = {
                "natural_language": f"I received your equipment query: '{message_text}'. The system is taking longer than expected to process it. Please try again or rephrase your question.",
                "data": {"error": "timeout", "message": str(e)},
                "recommendations": [],
                "confidence": 0.3,
                "response_type": "timeout",
                "mcp_tools_used": [],
                "tool_execution_results": {},
            }
        except Exception as e:
            logger.error(f"Error in MCP equipment agent: {e}", exc_info=True)
            state["agent_responses"]["equipment"] = {
                "natural_language": f"I received your equipment query: '{message_text}'. However, I encountered an error processing it: {str(e)[:100]}. Please try rephrasing your question.",
                "data": {"error": str(e)[:200]},
                "recommendations": [],
                "confidence": 0.3,
                "response_type": "error",
                "mcp_tools_used": [],
                "tool_execution_results": {},
            }

        return state

    async def _mcp_operations_agent(
        self, state: MCPWarehouseState
    ) -> MCPWarehouseState:
        """Handle operations queries using MCP-enabled Operations Agent."""
        try:
            from src.api.agents.operations.mcp_operations_agent import (
                get_mcp_operations_agent,
            )

            # Get the latest user message
            if not state["messages"]:
                state["agent_responses"]["operations"] = "No message to process"
                return state

            latest_message = state["messages"][-1]
            if isinstance(latest_message, HumanMessage):
                message_text = latest_message.content
            else:
                message_text = str(latest_message.content)

            # Get session ID from context
            session_id = state.get("session_id", "default")

            # Get MCP operations agent with timeout
            try:
                mcp_operations_agent = await asyncio.wait_for(
                    get_mcp_operations_agent(),
                    timeout=5.0  # 5 second timeout for agent initialization
                )
            except asyncio.TimeoutError:
                logger.error("MCP operations agent initialization timed out")
                raise
            except Exception as init_error:
                logger.error(f"MCP operations agent initialization failed: {init_error}")
                raise

            # Extract reasoning parameters from state
            enable_reasoning = state.get("enable_reasoning", False)
            reasoning_types = state.get("reasoning_types")
            
            # Detect complex queries that need more processing time
            message_lower = message_text.lower()
            # Detect complex queries: analysis keywords, multiple actions, or long queries
            is_complex_query = (
                any(keyword in message_lower for keyword in [
                    "optimize", "optimization", "optimizing", "analyze", "analysis", "analyzing",
                    "relationship", "between", "compare", "evaluate", "correlation", "impact",
                    "effect", "factors", "consider", "considering", "recommend", "recommendation",
                    "strategy", "strategies", "improve", "improvement", "best practices"
                ]) or 
                # Multiple action keywords (create + dispatch, show + list, etc.)
                (message_lower.count(" and ") > 0 and any(action in message_lower for action in ["create", "dispatch", "assign", "show", "list", "get", "check"])) or
                len(message_text.split()) > 15
            )
            
            # Process with MCP operations agent with timeout
            # Increase timeout for complex queries and reasoning queries
            if enable_reasoning:
                agent_timeout = 90.0  # 90s for reasoning queries
            elif is_complex_query:
                agent_timeout = 50.0  # 50s for complex queries
            else:
                agent_timeout = 45.0  # 45s for simple queries (increased from 30s to prevent timeouts)
            
            logger.info(f"Operations agent timeout: {agent_timeout}s (complex: {is_complex_query}, reasoning: {enable_reasoning})")
            
            try:
                response = await asyncio.wait_for(
                    mcp_operations_agent.process_query(
                        query=message_text,
                        session_id=session_id,
                        context=state.get("context", {}),
                        mcp_results=state.get("mcp_results"),
                        enable_reasoning=enable_reasoning,
                        reasoning_types=reasoning_types,
                    ),
                    timeout=agent_timeout
                )
            except asyncio.TimeoutError:
                logger.error(f"MCP operations agent process_query timed out after {agent_timeout}s")
                raise TimeoutError(f"Operations agent processing timed out after {agent_timeout}s")
            except Exception as process_error:
                logger.error(f"MCP operations agent process_query failed: {process_error}")
                raise

            # Store the response (handle both dict and object responses)
            if isinstance(response, dict):
                state["agent_responses"]["operations"] = response
            else:
                # Convert response object to dict
                state["agent_responses"]["operations"] = {
                    "natural_language": response.natural_language if hasattr(response, "natural_language") else str(response),
                    "data": response.data if hasattr(response, "data") else {},
                    "recommendations": response.recommendations if hasattr(response, "recommendations") else [],
                    "confidence": response.confidence if hasattr(response, "confidence") else 0.0,
                    "response_type": response.response_type if hasattr(response, "response_type") else "operations_info",
                    "mcp_tools_used": response.mcp_tools_used or [] if hasattr(response, "mcp_tools_used") else [],
                    "tool_execution_results": response.tool_execution_results or {} if hasattr(response, "tool_execution_results") else {},
                    "actions_taken": response.actions_taken or [] if hasattr(response, "actions_taken") else [],
                    "reasoning_chain": response.reasoning_chain if hasattr(response, "reasoning_chain") else None,
                    "reasoning_steps": response.reasoning_steps if hasattr(response, "reasoning_steps") else None,
                }

            logger.info(
                f"MCP Operations agent processed request with confidence: {response.confidence}"
            )

        except Exception as e:
            logger.error(f"Error in MCP operations agent: {e}")
            state["agent_responses"]["operations"] = {
                "natural_language": f"Error processing operations request: {str(e)}",
                "data": {"error": str(e)},
                "recommendations": [],
                "confidence": 0.0,
                "response_type": "error",
                "mcp_tools_used": [],
                "tool_execution_results": {},
            }

        return state

    async def _mcp_safety_agent(self, state: MCPWarehouseState) -> MCPWarehouseState:
        """Handle safety queries using MCP-enabled Safety Agent."""
        try:
            from src.api.agents.safety.mcp_safety_agent import get_mcp_safety_agent

            # Get the latest user message
            if not state["messages"]:
                state["agent_responses"]["safety"] = {
                    "natural_language": "No message to process",
                    "data": {},
                    "recommendations": [],
                    "confidence": 0.0,
                    "response_type": "error",
                }
                return state

            latest_message = state["messages"][-1]
            if isinstance(latest_message, HumanMessage):
                message_text = latest_message.content
            else:
                message_text = str(latest_message.content)

            # Get session ID from context
            session_id = state.get("session_id", "default")

            # Get MCP safety agent with timeout
            try:
                mcp_safety_agent = await asyncio.wait_for(
                    get_mcp_safety_agent(),
                    timeout=5.0  # 5 second timeout for agent initialization
                )
            except asyncio.TimeoutError:
                logger.error("MCP safety agent initialization timed out")
                raise
            except Exception as init_error:
                logger.error(f"MCP safety agent initialization failed: {init_error}")
                raise

            # Extract reasoning parameters from state
            enable_reasoning = state.get("enable_reasoning", False)
            reasoning_types = state.get("reasoning_types")
            
            # Detect complex queries that need more processing time
            message_lower = message_text.lower()
            # Detect complex queries: analysis keywords, multiple actions, or long queries
            is_complex_query = (
                any(keyword in message_lower for keyword in [
                    "optimize", "optimization", "optimizing", "analyze", "analysis", "analyzing",
                    "relationship", "between", "compare", "evaluate", "correlation", "impact",
                    "effect", "factors", "consider", "considering", "recommend", "recommendation",
                    "strategy", "strategies", "improve", "improvement", "best practices"
                ]) or 
                # Multiple action keywords (create + dispatch, show + list, etc.)
                (message_lower.count(" and ") > 0 and any(action in message_lower for action in ["create", "dispatch", "assign", "show", "list", "get", "check"])) or
                len(message_text.split()) > 15
            )
            
            # Process with MCP safety agent with timeout
            # Increase timeout for complex queries and reasoning queries
            if enable_reasoning:
                agent_timeout = 90.0  # 90s for reasoning queries
            elif is_complex_query:
                agent_timeout = 50.0  # 50s for complex queries (was 20s)
            else:
                agent_timeout = 45.0  # 45s for simple queries (increased from 30s to prevent timeouts)
            
            logger.info(f"Safety agent timeout: {agent_timeout}s (complex: {is_complex_query}, reasoning: {enable_reasoning})")
            
            try:
                response = await asyncio.wait_for(
                    mcp_safety_agent.process_query(
                        query=message_text,
                        session_id=session_id,
                        context=state.get("context", {}),
                        mcp_results=state.get("mcp_results"),
                        enable_reasoning=enable_reasoning,
                        reasoning_types=reasoning_types,
                    ),
                    timeout=agent_timeout
                )
            except asyncio.TimeoutError:
                logger.error(f"MCP safety agent process_query timed out after {agent_timeout}s")
                raise TimeoutError(f"Safety agent processing timed out after {agent_timeout}s")
            except Exception as process_error:
                logger.error(f"MCP safety agent process_query failed: {process_error}")
                raise

            # Store the response (handle both dict and object responses)
            if isinstance(response, dict):
                state["agent_responses"]["safety"] = response
            else:
                # Convert response object to dict
                state["agent_responses"]["safety"] = {
                    "natural_language": response.natural_language if hasattr(response, "natural_language") else str(response),
                    "data": response.data if hasattr(response, "data") else {},
                    "recommendations": response.recommendations if hasattr(response, "recommendations") else [],
                    "confidence": response.confidence if hasattr(response, "confidence") else 0.0,
                    "response_type": response.response_type if hasattr(response, "response_type") else "safety_info",
                    "mcp_tools_used": response.mcp_tools_used or [] if hasattr(response, "mcp_tools_used") else [],
                    "tool_execution_results": response.tool_execution_results or {} if hasattr(response, "tool_execution_results") else {},
                    "actions_taken": response.actions_taken or [] if hasattr(response, "actions_taken") else [],
                    "reasoning_chain": response.reasoning_chain if hasattr(response, "reasoning_chain") else None,
                    "reasoning_steps": response.reasoning_steps if hasattr(response, "reasoning_steps") else None,
                }

            logger.info(
                f"MCP Safety agent processed request with confidence: {response.confidence}"
            )

        except asyncio.TimeoutError as e:
            logger.error(f"Timeout in MCP safety agent: {e}")
            state["agent_responses"]["safety"] = {
                "natural_language": f"I received your safety query: '{message_text}'. The system is taking longer than expected to process it. Please try again or rephrase your question.",
                "data": {"error": "timeout", "message": str(e)},
                "recommendations": [],
                "confidence": 0.3,
                "response_type": "timeout",
                "mcp_tools_used": [],
                "tool_execution_results": {},
            }
        except Exception as e:
            logger.error(f"Error in MCP safety agent: {e}", exc_info=True)
            state["agent_responses"]["safety"] = {
                "natural_language": f"I received your safety query: '{message_text}'. However, I encountered an error processing it: {str(e)[:100]}. Please try rephrasing your question.",
                "data": {"error": str(e)[:200]},
                "recommendations": [],
                "confidence": 0.3,
                "response_type": "error",
                "mcp_tools_used": [],
                "tool_execution_results": {},
            }

        return state

    async def _mcp_forecasting_agent(self, state: MCPWarehouseState) -> MCPWarehouseState:
        """Handle forecasting queries using MCP-enabled Forecasting Agent."""
        try:
            from src.api.agents.forecasting.forecasting_agent import (
                get_forecasting_agent,
            )

            # Get the latest user message
            if not state["messages"]:
                state["agent_responses"]["forecasting"] = "No message to process"
                return state

            latest_message = state["messages"][-1]
            if isinstance(latest_message, HumanMessage):
                message_text = latest_message.content
            else:
                message_text = str(latest_message.content)

            # Get session ID from context
            session_id = state.get("session_id", "default")

            # Get MCP forecasting agent
            forecasting_agent = await get_forecasting_agent()

            # Extract reasoning parameters from state
            enable_reasoning = state.get("enable_reasoning", False)
            reasoning_types = state.get("reasoning_types")
            
            # Process with MCP forecasting agent
            response = await forecasting_agent.process_query(
                query=message_text,
                session_id=session_id,
                context=state.get("context", {}),
                mcp_results=state.get("mcp_results"),
                enable_reasoning=enable_reasoning,
                reasoning_types=reasoning_types,
            )

            # Store the response
            state["agent_responses"]["forecasting"] = {
                "natural_language": response.natural_language,
                "data": response.data,
                "recommendations": response.recommendations,
                "confidence": response.confidence,
                "response_type": response.response_type,
                "mcp_tools_used": response.mcp_tools_used or [],
                "tool_execution_results": response.tool_execution_results or {},
                "actions_taken": response.actions_taken or [],
                "reasoning_chain": response.reasoning_chain,
                "reasoning_steps": response.reasoning_steps,
            }

            logger.info(
                f"MCP Forecasting agent processed request with confidence: {response.confidence}"
            )

        except Exception as e:
            logger.error(f"Error in MCP forecasting agent: {e}")
            state["agent_responses"]["forecasting"] = {
                "natural_language": f"Error processing forecasting request: {str(e)}",
                "data": {"error": str(e)},
                "recommendations": [],
                "confidence": 0.0,
                "response_type": "error",
                "mcp_tools_used": [],
                "tool_execution_results": {},
            }

        return state

    async def _mcp_document_agent(self, state: MCPWarehouseState) -> MCPWarehouseState:
        """Handle document-related queries with MCP tool discovery."""
        try:
            # Get the latest user message
            if not state["messages"]:
                state["agent_responses"]["document"] = "No message to process"
                return state

            latest_message = state["messages"][-1]
            if isinstance(latest_message, HumanMessage):
                message_text = latest_message.content
            else:
                message_text = str(latest_message.content)

            # Use MCP document agent
            try:
                from src.api.agents.document.mcp_document_agent import (
                    get_mcp_document_agent,
                )

                # Get document agent
                document_agent = await get_mcp_document_agent()

                # Extract reasoning parameters from state
                enable_reasoning = state.get("enable_reasoning", False)
                reasoning_types = state.get("reasoning_types")
                
                # Process query
                response = await document_agent.process_query(
                    query=message_text,
                    session_id=state.get("session_id", "default"),
                    context=state.get("context", {}),
                    mcp_results=state.get("mcp_results"),
                    enable_reasoning=enable_reasoning,
                    reasoning_types=reasoning_types,
                )

                # Store response with reasoning chain
                if hasattr(response, "natural_language"):
                    response_text = response.natural_language
                    # Store as dict with reasoning chain
                    state["agent_responses"]["document"] = {
                        "natural_language": response.natural_language,
                        "data": response.data if hasattr(response, "data") else {},
                        "recommendations": response.recommendations if hasattr(response, "recommendations") else [],
                        "confidence": response.confidence if hasattr(response, "confidence") else 0.0,
                        "response_type": response.response_type if hasattr(response, "response_type") else "document_info",
                        "actions_taken": response.actions_taken if hasattr(response, "actions_taken") else [],
                        "reasoning_chain": response.reasoning_chain if hasattr(response, "reasoning_chain") else None,
                        "reasoning_steps": response.reasoning_steps if hasattr(response, "reasoning_steps") else None,
                    }
                else:
                    response_text = str(response)
                    state["agent_responses"]["document"] = f"[MCP DOCUMENT AGENT] {response_text}"
                logger.info("MCP Document agent processed request")

            except Exception as e:
                logger.error(f"Error calling MCP document agent: {e}")
                state["agent_responses"][
                    "document"
                ] = f"[MCP DOCUMENT AGENT] Error processing document request: {str(e)}"

        except Exception as e:
            logger.error(f"Error in MCP document agent: {e}")
            state["agent_responses"][
                "document"
            ] = f"Error processing document request: {str(e)}"

        return state

    async def _mcp_general_agent(self, state: MCPWarehouseState) -> MCPWarehouseState:
        """Handle general queries with MCP tool discovery."""
        try:
            # Get the latest user message
            if not state["messages"]:
                state["agent_responses"]["general"] = "No message to process"
                return state

            latest_message = state["messages"][-1]
            if isinstance(latest_message, HumanMessage):
                message_text = latest_message.content
            else:
                message_text = str(latest_message.content)

            # Use MCP tools to help with general queries
            if self.tool_discovery and len(self.tool_discovery.discovered_tools) > 0:
                # Search for relevant tools
                relevant_tools = await self.tool_discovery.search_tools(message_text)

                if relevant_tools:
                    # Use the most relevant tool
                    best_tool = relevant_tools[0]
                    try:
                        # Execute the tool
                        result = await self.tool_discovery.execute_tool(
                            best_tool.tool_id, {"query": message_text}
                        )

                        response = f"[MCP GENERAL AGENT] Found relevant tool '{best_tool.name}' and executed it. Result: {str(result)[:200]}..."
                    except Exception as e:
                        response = f"[MCP GENERAL AGENT] Found relevant tool '{best_tool.name}' but execution failed: {str(e)}"
                else:
                    response = (
                        "[MCP GENERAL AGENT] No relevant tools found for this query."
                    )
            else:
                response = "[MCP GENERAL AGENT] No MCP tools available. Processing general query... (stub implementation)"

            state["agent_responses"]["general"] = response
            logger.info("MCP General agent processed request")

        except Exception as e:
            logger.error(f"Error in MCP general agent: {e}")
            state["agent_responses"][
                "general"
            ] = f"Error processing general request: {str(e)}"

        return state

    def _mcp_synthesize_response(self, state: MCPWarehouseState) -> MCPWarehouseState:
        """Synthesize final response from MCP agent outputs."""
        try:
            routing_decision = state.get("routing_decision", "general")
            agent_responses = state.get("agent_responses", {})

            logger.info(f"🔍 Synthesizing response for routing_decision: {routing_decision}")
            logger.info(f"🔍 Available agent_responses keys: {list(agent_responses.keys())}")

            # Get the response from the appropriate agent
            if routing_decision in agent_responses:
                agent_response = agent_responses[routing_decision]
                logger.info(f"🔍 Found agent_response for {routing_decision}, type: {type(agent_response)}")
                
                # Log response structure for debugging
                if isinstance(agent_response, dict):
                    logger.info(f"🔍 agent_response dict keys: {list(agent_response.keys())}")
                    logger.info(f"🔍 Has natural_language: {'natural_language' in agent_response}")
                    if "natural_language" in agent_response:
                        logger.info(f"🔍 natural_language value: {str(agent_response['natural_language'])[:100]}...")
                elif hasattr(agent_response, "__dict__"):
                    logger.info(f"🔍 agent_response object attributes: {list(agent_response.__dict__.keys())}")

                # Handle MCP response format
                if hasattr(agent_response, "natural_language"):
                    # Convert dataclass to dict
                    if hasattr(agent_response, "__dict__"):
                        agent_response_dict = agent_response.__dict__.copy()
                    else:
                        # Use asdict for dataclasses
                        from dataclasses import asdict

                        agent_response_dict = asdict(agent_response)
                    
                    # Log what fields are in the dict
                    logger.info(f"📋 agent_response_dict keys: {list(agent_response_dict.keys())}")
                    logger.info(f"📋 Has reasoning_chain: {'reasoning_chain' in agent_response_dict}, value: {agent_response_dict.get('reasoning_chain') is not None}")

                    # Extract natural_language and ensure it's a string (never a dict/object)
                    natural_lang = agent_response_dict.get("natural_language")
                    if isinstance(natural_lang, str) and natural_lang.strip():
                        final_response = natural_lang
                    else:
                        # If natural_language is missing or invalid, use fallback
                        # DO NOT try to extract from other fields as they may contain structured data
                        logger.warning(f"natural_language is missing or invalid in agent_response_dict, using fallback")
                        final_response = f"I processed your {routing_decision} query, but couldn't generate a detailed response. Please try rephrasing your question."
                    # Store structured data in context for API response
                    state["context"]["structured_response"] = agent_response_dict

                    # Add MCP tool information to context
                    if "mcp_tools_used" in agent_response_dict:
                        state["context"]["mcp_tools_used"] = agent_response_dict[
                            "mcp_tools_used"
                        ]
                    if "tool_execution_results" in agent_response_dict:
                        state["context"]["tool_execution_results"] = (
                            agent_response_dict["tool_execution_results"]
                        )
                    
                    # Add reasoning chain to context if available
                    if "reasoning_chain" in agent_response_dict:
                        reasoning_chain = agent_response_dict["reasoning_chain"]
                        logger.info(f"🔗 Found reasoning_chain in agent_response_dict: {reasoning_chain is not None}, type: {type(reasoning_chain)}")
                        state["context"]["reasoning_chain"] = reasoning_chain
                        state["reasoning_chain"] = reasoning_chain
                        # Convert ReasoningChain to dict if needed (avoid recursion)
                        from dataclasses import is_dataclass
                        if is_dataclass(reasoning_chain):
                            try:
                                # Manual conversion to avoid recursion
                                reasoning_chain_dict = {
                                    "chain_id": getattr(reasoning_chain, "chain_id", ""),
                                    "query": getattr(reasoning_chain, "query", ""),
                                    "reasoning_type": getattr(reasoning_chain, "reasoning_type", ""),
                                    "final_conclusion": getattr(reasoning_chain, "final_conclusion", ""),
                                    "overall_confidence": float(getattr(reasoning_chain, "overall_confidence", 0.0)),
                                    "execution_time": float(getattr(reasoning_chain, "execution_time", 0.0)),
                                }
                                # Convert enum to string
                                if hasattr(reasoning_chain_dict["reasoning_type"], "value"):
                                    reasoning_chain_dict["reasoning_type"] = reasoning_chain_dict["reasoning_type"].value
                                # Convert datetime
                                if hasattr(reasoning_chain, "created_at"):
                                    created_at = getattr(reasoning_chain, "created_at")
                                    if hasattr(created_at, "isoformat"):
                                        reasoning_chain_dict["created_at"] = created_at.isoformat()
                                    else:
                                        reasoning_chain_dict["created_at"] = str(created_at)
                                # Convert steps
                                if hasattr(reasoning_chain, "steps") and reasoning_chain.steps:
                                    converted_steps = []
                                    for step in reasoning_chain.steps:
                                        if is_dataclass(step):
                                            step_dict = {
                                                "step_id": getattr(step, "step_id", ""),
                                                "step_type": getattr(step, "step_type", ""),
                                                "description": getattr(step, "description", ""),
                                                "reasoning": getattr(step, "reasoning", ""),
                                                "confidence": float(getattr(step, "confidence", 0.0)),
                                            }
                                            if hasattr(step, "timestamp"):
                                                timestamp = getattr(step, "timestamp")
                                                if hasattr(timestamp, "isoformat"):
                                                    step_dict["timestamp"] = timestamp.isoformat()
                                                else:
                                                    step_dict["timestamp"] = str(timestamp)
                                            step_dict["input_data"] = {}
                                            step_dict["output_data"] = {}
                                            step_dict["dependencies"] = []
                                            converted_steps.append(step_dict)
                                        else:
                                            converted_steps.append(step)
                                    reasoning_chain_dict["steps"] = converted_steps
                                else:
                                    reasoning_chain_dict["steps"] = []
                                state["context"]["reasoning_chain"] = reasoning_chain_dict
                                logger.info(f"✅ Converted reasoning_chain to dict with {len(reasoning_chain_dict.get('steps', []))} steps")
                            except Exception as e:
                                logger.error(f"Error converting reasoning_chain to dict: {e}", exc_info=True)
                                state["context"]["reasoning_chain"] = reasoning_chain
                    if "reasoning_steps" in agent_response_dict:
                        reasoning_steps = agent_response_dict["reasoning_steps"]
                        logger.info(f"🔗 Found reasoning_steps in agent_response_dict: {reasoning_steps is not None}, count: {len(reasoning_steps) if reasoning_steps else 0}")
                        state["context"]["reasoning_steps"] = reasoning_steps

                elif (
                    isinstance(agent_response, dict)
                    and "natural_language" in agent_response
                ):
                    # Extract natural_language and ensure it's a string (never a dict/object)
                    natural_lang = agent_response.get("natural_language")
                    if isinstance(natural_lang, str) and natural_lang.strip():
                        final_response = natural_lang
                    else:
                        # If natural_language is missing or invalid, use fallback
                        # DO NOT try to extract from other fields as they may contain structured data
                        logger.warning(f"natural_language is missing or invalid in dict response, using fallback")
                        final_response = f"I processed your {routing_decision} query, but couldn't generate a detailed response. Please try rephrasing your question."
                    # Store structured data in context for API response
                    state["context"]["structured_response"] = agent_response

                    # Add MCP tool information to context
                    if "mcp_tools_used" in agent_response:
                        state["context"]["mcp_tools_used"] = agent_response[
                            "mcp_tools_used"
                        ]
                    if "tool_execution_results" in agent_response:
                        state["context"]["tool_execution_results"] = agent_response[
                            "tool_execution_results"
                        ]
                    
                    # Add reasoning chain to context if available
                    if "reasoning_chain" in agent_response:
                        reasoning_chain = agent_response["reasoning_chain"]
                        logger.info(f"🔗 Found reasoning_chain in agent_response dict: {reasoning_chain is not None}, type: {type(reasoning_chain)}")
                        # Convert if it's a dataclass
                        from dataclasses import is_dataclass
                        if is_dataclass(reasoning_chain):
                            try:
                                # Manual conversion to avoid recursion
                                reasoning_chain_dict = {
                                    "chain_id": getattr(reasoning_chain, "chain_id", ""),
                                    "query": getattr(reasoning_chain, "query", ""),
                                    "reasoning_type": getattr(reasoning_chain, "reasoning_type", ""),
                                    "final_conclusion": getattr(reasoning_chain, "final_conclusion", ""),
                                    "overall_confidence": float(getattr(reasoning_chain, "overall_confidence", 0.0)),
                                    "execution_time": float(getattr(reasoning_chain, "execution_time", 0.0)),
                                }
                                # Convert enum to string
                                if hasattr(reasoning_chain_dict["reasoning_type"], "value"):
                                    reasoning_chain_dict["reasoning_type"] = reasoning_chain_dict["reasoning_type"].value
                                # Convert datetime
                                if hasattr(reasoning_chain, "created_at"):
                                    created_at = getattr(reasoning_chain, "created_at")
                                    if hasattr(created_at, "isoformat"):
                                        reasoning_chain_dict["created_at"] = created_at.isoformat()
                                    else:
                                        reasoning_chain_dict["created_at"] = str(created_at)
                                # Convert steps
                                if hasattr(reasoning_chain, "steps") and reasoning_chain.steps:
                                    converted_steps = []
                                    for step in reasoning_chain.steps:
                                        if is_dataclass(step):
                                            step_dict = {
                                                "step_id": getattr(step, "step_id", ""),
                                                "step_type": getattr(step, "step_type", ""),
                                                "description": getattr(step, "description", ""),
                                                "reasoning": getattr(step, "reasoning", ""),
                                                "confidence": float(getattr(step, "confidence", 0.0)),
                                            }
                                            if hasattr(step, "timestamp"):
                                                timestamp = getattr(step, "timestamp")
                                                if hasattr(timestamp, "isoformat"):
                                                    step_dict["timestamp"] = timestamp.isoformat()
                                                else:
                                                    step_dict["timestamp"] = str(timestamp)
                                            step_dict["input_data"] = {}
                                            step_dict["output_data"] = {}
                                            step_dict["dependencies"] = []
                                            converted_steps.append(step_dict)
                                        else:
                                            converted_steps.append(step)
                                    reasoning_chain_dict["steps"] = converted_steps
                                else:
                                    reasoning_chain_dict["steps"] = []
                                state["context"]["reasoning_chain"] = reasoning_chain_dict
                                state["reasoning_chain"] = reasoning_chain_dict
                                logger.info(f"✅ Converted reasoning_chain to dict with {len(reasoning_chain_dict.get('steps', []))} steps")
                            except Exception as e:
                                logger.error(f"Error converting reasoning_chain to dict: {e}", exc_info=True)
                                state["context"]["reasoning_chain"] = reasoning_chain
                                state["reasoning_chain"] = reasoning_chain
                        else:
                            # Already a dict, use as-is
                            state["context"]["reasoning_chain"] = reasoning_chain
                            state["reasoning_chain"] = reasoning_chain
                    if "reasoning_steps" in agent_response:
                        reasoning_steps = agent_response["reasoning_steps"]
                        logger.info(f"🔗 Found reasoning_steps in agent_response dict: {reasoning_steps is not None}, count: {len(reasoning_steps) if reasoning_steps else 0}")
                        state["context"]["reasoning_steps"] = reasoning_steps
                else:
                    # Handle legacy string response format or unexpected types
                    if isinstance(agent_response, str):
                        final_response = agent_response
                    elif isinstance(agent_response, dict):
                        # Only extract natural_language if it's a string - never convert dict/object to string
                        natural_lang = agent_response.get("natural_language")
                        if isinstance(natural_lang, str) and natural_lang.strip():
                            final_response = natural_lang
                        else:
                            # Use fallback - do not try other fields as they may contain structured data
                            logger.warning(f"natural_language missing or invalid in unexpected dict format, using fallback")
                            final_response = "I received your request and processed it successfully."
                        # Store the dict as structured response if it looks like one
                        if not state["context"].get("structured_response"):
                            state["context"]["structured_response"] = agent_response
                    else:
                        # For other types, try to get a meaningful string representation
                        # but avoid showing the entire object structure
                        final_response = "I received your request and processed it successfully."
                        logger.warning(f"Unexpected agent_response type: {type(agent_response)}, using fallback message")
            else:
                logger.warning(f"⚠️ No agent_response found for routing_decision: {routing_decision}, using fallback")
                final_response = "I'm sorry, I couldn't process your request. Please try rephrasing your question."

            # Ensure final_response is set and not empty
            if not final_response or (isinstance(final_response, str) and final_response.strip() == ""):
                logger.error(f"❌ final_response is empty after synthesis, using fallback")
                logger.error(f"❌ agent_response type: {type(agent_response)}, keys: {list(agent_response.keys()) if isinstance(agent_response, dict) else 'N/A'}")
                # Try to extract any meaningful response from agent_response
                if isinstance(agent_response, dict):
                    # Only try natural_language field - never extract from other fields to avoid data leakage
                    natural_lang = agent_response.get("natural_language")
                    if isinstance(natural_lang, str) and natural_lang.strip():
                        final_response = natural_lang
                if not final_response or (isinstance(final_response, str) and final_response.strip() == ""):
                    final_response = "I'm sorry, I couldn't process your request. Please try rephrasing your question."

            state["final_response"] = final_response
            logger.info(f"✅ final_response set: {final_response[:100] if final_response else 'None'}...")

            # Add AI message to conversation
            if state["messages"]:
                ai_message = AIMessage(content=final_response)
                state["messages"].append(ai_message)

            logger.info(
                f"MCP Response synthesized for routing decision: {routing_decision}, final_response length: {len(final_response) if final_response else 0}"
            )

        except Exception as e:
            logger.error(f"Error synthesizing MCP response: {e}")
            state["final_response"] = (
                "I encountered an error processing your request. Please try again."
            )

        return state

    def _route_to_agent(self, state: MCPWarehouseState) -> str:
        """Route to the appropriate agent based on MCP intent classification."""
        routing_decision = state.get("routing_decision", "general")
        return routing_decision

    async def process_warehouse_query(
        self, message: str, session_id: str = "default", context: Optional[Dict] = None
    ) -> Dict[str, any]:
        """
        Process a warehouse query through the MCP-enabled planner graph.

        Args:
            message: User's message/query
            session_id: Session identifier for context
            context: Additional context for the query

        Returns:
            Dictionary containing the response and metadata
        """
        try:
            # Initialize if needed with timeout
            if not self.initialized:
                try:
                    await asyncio.wait_for(self.initialize(), timeout=2.0)
                except asyncio.TimeoutError:
                    logger.warning("Initialization timed out, using fallback")
                    return self._create_fallback_response(message, session_id)
                except Exception as init_err:
                    logger.warning(f"Initialization failed: {init_err}, using fallback")
                    return self._create_fallback_response(message, session_id)
            
            if not self.graph:
                logger.warning("Graph not available, using fallback")
                return self._create_fallback_response(message, session_id)

            # Initialize state
            # Extract reasoning parameters from context
            enable_reasoning = context.get("enable_reasoning", False) if context else False
            reasoning_types = context.get("reasoning_types") if context else None
            
            initial_state = MCPWarehouseState(
                messages=[HumanMessage(content=message)],
                user_intent=None,
                routing_decision=None,
                agent_responses={},
                final_response=None,
                context=context or {},
                session_id=session_id,
                mcp_results=None,
                tool_execution_plan=None,
                available_tools=None,
                enable_reasoning=enable_reasoning,
                reasoning_types=reasoning_types,
                reasoning_chain=None,
            )

            # Run the graph asynchronously with timeout
            # Increase timeout when reasoning is enabled (reasoning takes longer)
            # Detect complex queries that need even more time
            message_lower = message.lower()
            is_complex_query = any(keyword in message_lower for keyword in [
                "analyze", "relationship", "between", "compare", "evaluate", 
                "optimize", "calculate", "correlation", "impact", "effect"
            ]) or len(message.split()) > 15
            
            if enable_reasoning:
                # Very complex queries with reasoning need up to 4 minutes
                # Match the timeout in chat.py: 230s for complex, 115s for regular reasoning
                graph_timeout = 230.0 if is_complex_query else 115.0  # 230s for complex, 115s for regular reasoning
            else:
                # Regular queries: Match chat.py timeouts (60s for simple, 90s for complex)
                graph_timeout = 90.0 if is_complex_query else 60.0  # Increased from 30s to 60s for simple queries
            logger.info(f"Graph timeout set to {graph_timeout}s (complex: {is_complex_query}, reasoning: {enable_reasoning})")
            try:
                result = await asyncio.wait_for(
                    self.graph.ainvoke(initial_state),
                    timeout=graph_timeout
                )
                logger.info(f"✅ Graph execution completed in time: timeout={graph_timeout}s")
            except asyncio.TimeoutError:
                logger.error(
                    f"⏱️ TIMEOUT: Graph execution timed out after {graph_timeout}s | "
                    f"Message: {message[:100]} | Complex: {is_complex_query} | Reasoning: {enable_reasoning}"
                )
                return self._create_fallback_response(message, session_id)

            # Ensure structured response is properly included
            context = result.get("context", {})
            structured_response = context.get("structured_response", {})
            
            # Extract actions_taken from structured_response if available
            actions_taken = None
            if structured_response and isinstance(structured_response, dict):
                actions_taken = structured_response.get("actions_taken")
            if not actions_taken and context:
                actions_taken = context.get("actions_taken")

            return {
                "response": result.get("final_response", "No response generated"),
                "intent": result.get("user_intent", "unknown"),
                "route": result.get("routing_decision", "unknown"),
                "session_id": session_id,
                "context": context,
                "structured_response": structured_response,  # Explicitly include structured response
                "actions_taken": actions_taken,  # Include actions_taken if available
                "mcp_tools_used": context.get("mcp_tools_used", []),
                "tool_execution_results": context.get("tool_execution_results", {}),
                "available_tools": result.get("available_tools", []),
            }

        except Exception as e:
            logger.error(f"Error processing MCP warehouse query: {e}")
            return self._create_fallback_response(message, session_id)
    
    def _create_fallback_response(self, message: str, session_id: str) -> Dict[str, any]:
        """Create a fallback response when MCP graph is unavailable."""
        # Simple intent detection based on keywords
        message_lower = message.lower()
        if any(word in message_lower for word in ["order", "wave", "dispatch", "forklift", "create"]):
            route = "operations"
            intent = "operations"
            response_text = f"I received your request: '{message}'. I understand you want to create a wave and dispatch equipment. The system is processing your request."
        elif any(word in message_lower for word in ["inventory", "stock", "sku", "quantity"]):
            route = "inventory"
            intent = "inventory"
            response_text = f"I received your query: '{message}'. I can help with inventory questions."
        elif any(word in message_lower for word in ["equipment", "asset", "machine"]):
            route = "equipment"
            intent = "equipment"
            response_text = f"I received your question: '{message}'. I can help with equipment information."
        else:
            route = "general"
            intent = "general"
            response_text = f"I received your message: '{message}'. How can I help you?"
        
        return {
            "response": response_text,
            "intent": intent,
            "route": route,
            "session_id": session_id,
            "context": {},
            "structured_response": {
                "natural_language": response_text,
                "data": {},
                "recommendations": [],
                "confidence": 0.6,
            },
            "mcp_tools_used": [],
            "tool_execution_results": {},
            "available_tools": [],
        }


# Global MCP planner graph instance
_mcp_planner_graph = None


async def get_mcp_planner_graph() -> MCPPlannerGraph:
    """Get the global MCP planner graph instance."""
    global _mcp_planner_graph
    if _mcp_planner_graph is None:
        _mcp_planner_graph = MCPPlannerGraph()
        await _mcp_planner_graph.initialize()
    return _mcp_planner_graph


async def process_mcp_warehouse_query(
    message: str, session_id: str = "default", context: Optional[Dict] = None
) -> Dict[str, any]:
    """
    Process a warehouse query through the MCP-enabled planner graph.

    Args:
        message: User's message/query
        session_id: Session identifier for context
        context: Additional context for the query

    Returns:
        Dictionary containing the response and metadata
    """
    mcp_planner = await get_mcp_planner_graph()
    return await mcp_planner.process_warehouse_query(message, session_id, context)
