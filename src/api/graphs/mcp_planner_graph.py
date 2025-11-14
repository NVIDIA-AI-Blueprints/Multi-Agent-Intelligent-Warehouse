"""
MCP-Enabled Planner/Router Graph for Warehouse Operations
Phase 2 Implementation: Integrating MCP framework into main agent workflow

This module implements an MCP-enhanced planner/router that:
1. Uses MCP tool discovery for dynamic agent capabilities
2. Leverages MCP tool binding for intelligent tool selection
3. Implements MCP-based routing for enhanced decision making
4. Provides MCP tool validation and error handling
5. Enables dynamic tool execution across agents
"""

from typing import Dict, List, Optional, TypedDict, Annotated, Any
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
import logging
import asyncio
from dataclasses import asdict

from src.api.services.mcp import (
    ToolDiscoveryService,
    ToolBindingService,
    ToolRoutingService,
    ToolValidationService,
    ErrorHandlingService,
    MCPManager,
    ExecutionContext,
    RoutingContext,
    QueryComplexity,
)

logger = logging.getLogger(__name__)


class MCPWarehouseState(TypedDict):
    """Enhanced state management with MCP integration."""

    messages: Annotated[List[BaseMessage], "Chat messages"]
    user_intent: Optional[str]
    routing_decision: Optional[str]
    agent_responses: Dict[str, str]
    final_response: Optional[str]
    context: Dict[str, Any]
    session_id: str

    # MCP-specific state
    mcp_tools_discovered: List[Dict[str, Any]]
    mcp_execution_plan: Optional[Dict[str, Any]]
    mcp_tool_results: Dict[str, Any]
    mcp_validation_results: Dict[str, Any]


class MCPIntentClassifier:
    """MCP-enhanced intent classifier with tool discovery integration."""

    def __init__(self, tool_discovery: ToolDiscoveryService):
        self.tool_discovery = tool_discovery
        self.tool_routing = None
        self._setup_keywords()

    def _setup_keywords(self):
        """Setup keyword mappings for intent classification."""
        self.EQUIPMENT_KEYWORDS = [
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

        self.OPERATIONS_KEYWORDS = [
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

        self.SAFETY_KEYWORDS = [
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
            "equipment",
            "helmet",
            "gloves",
            "boots",
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

    async def classify_intent_with_mcp(self, message: str) -> Dict[str, Any]:
        """Classify intent using both keyword matching and MCP tool discovery."""
        try:
            # Basic keyword classification
            basic_intent = self._classify_intent_basic(message)

            # MCP-enhanced classification
            mcp_context = RoutingContext(
                query=message,
                complexity=self._assess_query_complexity(message),
                available_tools=await self.tool_discovery.get_available_tools(),
                user_context={},
                session_context={},
            )

            # Get MCP routing suggestions
            if self.tool_routing:
                routing_suggestions = await self.tool_routing.route_query(mcp_context)
                mcp_intent = (
                    routing_suggestions.primary_agent
                    if routing_suggestions
                    else basic_intent
                )
            else:
                mcp_intent = basic_intent

            return {
                "intent": mcp_intent,
                "confidence": 0.8 if mcp_intent == basic_intent else 0.9,
                "basic_intent": basic_intent,
                "mcp_intent": mcp_intent,
                "routing_context": mcp_context,
                "discovered_tools": await self.tool_discovery.get_tools_for_intent(
                    mcp_intent
                ),
            }

        except Exception as e:
            logger.error(f"Error in MCP intent classification: {e}")
            return {
                "intent": self._classify_intent_basic(message),
                "confidence": 0.5,
                "error": str(e),
            }

    def _classify_intent_basic(self, message: str) -> str:
        """Basic keyword-based intent classification."""
        message_lower = message.lower()

        # Check for safety-related keywords first (highest priority)
        if any(keyword in message_lower for keyword in self.SAFETY_KEYWORDS):
            return "safety"

        # Check for equipment dispatch/assignment keywords (high priority)
        if any(
            term in message_lower for term in ["dispatch", "assign", "deploy"]
        ) and any(
            term in message_lower
            for term in ["forklift", "equipment", "conveyor", "truck", "amr", "agv"]
        ):
            return "equipment"

        # Check for operations-related keywords
        operations_score = sum(
            1 for keyword in self.OPERATIONS_KEYWORDS if keyword in message_lower
        )
        equipment_score = sum(
            1 for keyword in self.EQUIPMENT_KEYWORDS if keyword in message_lower
        )

        if (
            operations_score > 0
            and any(
                term in message_lower
                for term in ["wave", "order", "create", "pick", "pack"]
            )
            and not any(
                term in message_lower for term in ["dispatch", "assign", "deploy"]
            )
        ):
            return "operations"

        if equipment_score > 0:
            return "equipment"

        if operations_score > 0:
            return "operations"

        return "general"

    def _assess_query_complexity(self, message: str) -> QueryComplexity:
        """Assess query complexity for MCP routing."""
        message_lower = message.lower()

        # Simple queries
        if len(message.split()) <= 5 and not any(
            word in message_lower
            for word in ["and", "or", "but", "also", "additionally"]
        ):
            return QueryComplexity.SIMPLE

        # Complex queries with multiple intents or conditions
        if any(
            word in message_lower
            for word in [
                "and",
                "or",
                "but",
                "also",
                "additionally",
                "however",
                "while",
                "when",
                "if",
            ]
        ):
            return QueryComplexity.COMPLEX

        # Medium complexity
        return QueryComplexity.MEDIUM


class MCPPlannerGraph:
    """MCP-enhanced planner graph for warehouse operations."""

    def __init__(self):
        self.mcp_manager = MCPManager()
        self.tool_discovery = None
        self.tool_binding = None
        self.tool_routing = None
        self.tool_validation = None
        self.error_handling = None
        self.intent_classifier = None
        self.graph = None
        self.initialized = False

    async def initialize(self) -> None:
        """Initialize MCP components and create the graph."""
        try:
            # Initialize MCP services (simplified for Phase 2 Step 1)
            self.tool_discovery = ToolDiscoveryService()
            self.tool_binding = ToolBindingService(self.tool_discovery)
            # Skip complex routing for now - will implement in next step
            self.tool_routing = None
            self.tool_validation = ToolValidationService(self.tool_discovery)
            self.error_handling = ErrorHandlingService(self.tool_discovery)

            # Start tool discovery
            await self.tool_discovery.start_discovery()

            # Initialize intent classifier with MCP (simplified)
            self.intent_classifier = MCPIntentClassifier(self.tool_discovery)
            self.intent_classifier.tool_routing = None  # Skip routing for now

            # Create the graph
            self.graph = self._create_graph()

            self.initialized = True
            logger.info("MCP Planner Graph initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize MCP Planner Graph: {e}")
            raise

    def _create_graph(self) -> StateGraph:
        """Create the MCP-enhanced state graph."""
        workflow = StateGraph(MCPWarehouseState)

        # Add nodes
        workflow.add_node("mcp_route_intent", self._mcp_route_intent)
        workflow.add_node("mcp_equipment", self._mcp_equipment_agent)
        workflow.add_node("mcp_operations", self._mcp_operations_agent)
        workflow.add_node("mcp_safety", self._mcp_safety_agent)
        workflow.add_node("mcp_general", self._mcp_general_agent)
        workflow.add_node("mcp_synthesize", self._mcp_synthesize_response)

        # Set entry point
        workflow.set_entry_point("mcp_route_intent")

        # Add conditional edges for routing
        workflow.add_conditional_edges(
            "mcp_route_intent",
            self._route_to_mcp_agent,
            {
                "equipment": "mcp_equipment",
                "operations": "mcp_operations",
                "safety": "mcp_safety",
                "general": "mcp_general",
            },
        )

        # Add edges from agents to synthesis
        workflow.add_edge("mcp_equipment", "mcp_synthesize")
        workflow.add_edge("mcp_operations", "mcp_synthesize")
        workflow.add_edge("mcp_safety", "mcp_synthesize")
        workflow.add_edge("mcp_general", "mcp_synthesize")

        # Add edge from synthesis to end
        workflow.add_edge("mcp_synthesize", END)

        return workflow.compile()

    async def _mcp_route_intent(self, state: MCPWarehouseState) -> MCPWarehouseState:
        """MCP-enhanced intent routing."""
        try:
            if not state["messages"]:
                state["user_intent"] = "general"
                state["routing_decision"] = "general"
                return state

            latest_message = state["messages"][-1]
            if isinstance(latest_message, HumanMessage):
                message_text = latest_message.content
            else:
                message_text = str(latest_message.content)

            # Use MCP-enhanced intent classification
            intent_result = await self.intent_classifier.classify_intent_with_mcp(
                message_text
            )

            state["user_intent"] = intent_result["intent"]
            state["routing_decision"] = intent_result["intent"]
            state["mcp_tools_discovered"] = intent_result.get("discovered_tools", [])
            state["context"]["routing_context"] = intent_result.get("routing_context")

            logger.info(
                f"MCP Intent classified as: {intent_result['intent']} with confidence: {intent_result['confidence']}"
            )

        except Exception as e:
            logger.error(f"Error in MCP intent routing: {e}")
            state["user_intent"] = "general"
            state["routing_decision"] = "general"
            state["mcp_tools_discovered"] = []

        return state

    async def _mcp_equipment_agent(self, state: MCPWarehouseState) -> MCPWarehouseState:
        """MCP-enhanced equipment agent."""
        try:
            if not state["messages"]:
                state["agent_responses"]["equipment"] = "No message to process"
                return state

            latest_message = state["messages"][-1]
            message_text = (
                latest_message.content
                if isinstance(latest_message, HumanMessage)
                else str(latest_message.content)
            )
            session_id = state.get("session_id", "default")

            # Create execution context for MCP
            execution_context = ExecutionContext(
                session_id=session_id,
                agent_id="equipment",
                query=message_text,
                intent=state.get("user_intent", "equipment"),
                entities={},
                context=state.get("context", {}),
            )

            # Create execution plan using MCP tool binding
            execution_plan = await self.tool_binding.create_execution_plan(
                execution_context
            )
            state["mcp_execution_plan"] = asdict(execution_plan)

            # Execute the plan
            execution_result = await self.tool_binding.execute_plan(execution_plan)
            state["mcp_tool_results"] = asdict(execution_result)

            # Process with MCP-enabled equipment agent
            response = await self._process_mcp_equipment_query(
                query=message_text,
                session_id=session_id,
                context=state.get("context", {}),
                mcp_results=execution_result,
            )

            state["agent_responses"]["equipment"] = response

            logger.info(
                f"MCP Equipment agent processed request with confidence: {response.get('confidence', 0)}"
            )

        except Exception as e:
            logger.error(f"Error in MCP equipment agent: {e}")
            state["agent_responses"]["equipment"] = {
                "natural_language": f"Error processing equipment request: {str(e)}",
                "structured_data": {"error": str(e)},
                "recommendations": [],
                "confidence": 0.0,
                "response_type": "error",
            }

        return state

    async def _mcp_operations_agent(
        self, state: MCPWarehouseState
    ) -> MCPWarehouseState:
        """MCP-enhanced operations agent."""
        try:
            if not state["messages"]:
                state["agent_responses"]["operations"] = "No message to process"
                return state

            latest_message = state["messages"][-1]
            message_text = (
                latest_message.content
                if isinstance(latest_message, HumanMessage)
                else str(latest_message.content)
            )
            session_id = state.get("session_id", "default")

            # Create execution context for MCP
            execution_context = ExecutionContext(
                session_id=session_id,
                agent_id="operations",
                query=message_text,
                intent=state.get("user_intent", "operations"),
                entities={},
                context=state.get("context", {}),
            )

            # Create execution plan using MCP tool binding
            execution_plan = await self.tool_binding.create_execution_plan(
                execution_context
            )
            state["mcp_execution_plan"] = asdict(execution_plan)

            # Execute the plan
            execution_result = await self.tool_binding.execute_plan(execution_plan)
            state["mcp_tool_results"] = asdict(execution_result)

            # Process with MCP-enabled operations agent
            response = await self._process_mcp_operations_query(
                query=message_text,
                session_id=session_id,
                context=state.get("context", {}),
                mcp_results=execution_result,
            )

            state["agent_responses"]["operations"] = response

            logger.info(
                f"MCP Operations agent processed request with confidence: {response.get('confidence', 0)}"
            )

        except Exception as e:
            logger.error(f"Error in MCP operations agent: {e}")
            state["agent_responses"]["operations"] = {
                "natural_language": f"Error processing operations request: {str(e)}",
                "structured_data": {"error": str(e)},
                "recommendations": [],
                "confidence": 0.0,
                "response_type": "error",
            }

        return state

    async def _mcp_safety_agent(self, state: MCPWarehouseState) -> MCPWarehouseState:
        """MCP-enhanced safety agent."""
        try:
            if not state["messages"]:
                state["agent_responses"]["safety"] = "No message to process"
                return state

            latest_message = state["messages"][-1]
            message_text = (
                latest_message.content
                if isinstance(latest_message, HumanMessage)
                else str(latest_message.content)
            )
            session_id = state.get("session_id", "default")

            # Create execution context for MCP
            execution_context = ExecutionContext(
                session_id=session_id,
                agent_id="safety",
                query=message_text,
                intent=state.get("user_intent", "safety"),
                entities={},
                context=state.get("context", {}),
            )

            # Create execution plan using MCP tool binding
            execution_plan = await self.tool_binding.create_execution_plan(
                execution_context
            )
            state["mcp_execution_plan"] = asdict(execution_plan)

            # Execute the plan
            execution_result = await self.tool_binding.execute_plan(execution_plan)
            state["mcp_tool_results"] = asdict(execution_result)

            # Process with MCP-enabled safety agent
            response = await self._process_mcp_safety_query(
                query=message_text,
                session_id=session_id,
                context=state.get("context", {}),
                mcp_results=execution_result,
            )

            state["agent_responses"]["safety"] = response

            logger.info(
                f"MCP Safety agent processed request with confidence: {response.get('confidence', 0)}"
            )

        except Exception as e:
            logger.error(f"Error in MCP safety agent: {e}")
            state["agent_responses"]["safety"] = {
                "natural_language": f"Error processing safety request: {str(e)}",
                "structured_data": {"error": str(e)},
                "recommendations": [],
                "confidence": 0.0,
                "response_type": "error",
            }

        return state

    async def _mcp_general_agent(self, state: MCPWarehouseState) -> MCPWarehouseState:
        """MCP-enhanced general agent."""
        try:
            response = "[MCP GENERAL AGENT] Processing general query with MCP tool discovery..."
            state["agent_responses"]["general"] = response
            logger.info("MCP General agent processed request")

        except Exception as e:
            logger.error(f"Error in MCP general agent: {e}")
            state["agent_responses"][
                "general"
            ] = f"Error processing general request: {str(e)}"

        return state

    async def _mcp_synthesize_response(
        self, state: MCPWarehouseState
    ) -> MCPWarehouseState:
        """MCP-enhanced response synthesis."""
        try:
            routing_decision = state.get("routing_decision", "general")
            agent_responses = state.get("agent_responses", {})

            # Get the response from the appropriate agent
            if routing_decision in agent_responses:
                agent_response = agent_responses[routing_decision]

                # Handle structured response format
                if (
                    isinstance(agent_response, dict)
                    and "natural_language" in agent_response
                ):
                    final_response = agent_response["natural_language"]
                    # Store structured data in context for API response
                    state["context"]["structured_response"] = agent_response
                    state["context"]["mcp_results"] = state.get("mcp_tool_results", {})
                else:
                    final_response = str(agent_response)
            else:
                final_response = "I'm sorry, I couldn't process your request. Please try rephrasing your question."

            state["final_response"] = final_response

            # Add AI message to conversation
            if state["messages"]:
                ai_message = AIMessage(content=final_response)
                state["messages"].append(ai_message)

            logger.info(
                f"MCP Response synthesized for routing decision: {routing_decision}"
            )

        except Exception as e:
            logger.error(f"Error synthesizing MCP response: {e}")
            state["final_response"] = (
                "I encountered an error processing your request. Please try again."
            )

        return state

    def _route_to_mcp_agent(self, state: MCPWarehouseState) -> str:
        """Route to the appropriate MCP-enhanced agent."""
        routing_decision = state.get("routing_decision", "general")
        return routing_decision

    async def _process_mcp_equipment_query(
        self, query: str, session_id: str, context: Dict, mcp_results: Any
    ) -> Dict[str, Any]:
        """Process equipment query with MCP integration."""
        try:
            # Import MCP-enabled equipment agent
            from src.api.agents.inventory.mcp_equipment_agent import (
                get_mcp_equipment_agent,
            )

            # Get MCP equipment agent
            mcp_equipment_agent = await get_mcp_equipment_agent()

            # Process query with MCP results
            response = await mcp_equipment_agent.process_query(
                query=query,
                session_id=session_id,
                context=context,
                mcp_results=mcp_results,
            )

            return asdict(response)

        except Exception as e:
            logger.error(f"MCP Equipment processing failed: {e}")
            return {
                "response_type": "error",
                "data": {"error": str(e)},
                "natural_language": f"Error processing equipment query: {str(e)}",
                "recommendations": [],
                "confidence": 0.0,
                "actions_taken": [],
            }

    async def _process_mcp_operations_query(
        self, query: str, session_id: str, context: Dict, mcp_results: Any
    ) -> Dict[str, Any]:
        """Process operations query with MCP integration."""
        try:
            # Import MCP-enabled operations agent
            from src.api.agents.operations.mcp_operations_agent import (
                get_mcp_operations_agent,
            )

            # Get MCP operations agent
            mcp_operations_agent = await get_mcp_operations_agent()

            # Process query with MCP results
            response = await mcp_operations_agent.process_query(
                query=query,
                session_id=session_id,
                context=context,
                mcp_results=mcp_results,
            )

            return asdict(response)

        except Exception as e:
            logger.error(f"MCP Operations processing failed: {e}")
            return {
                "response_type": "error",
                "data": {"error": str(e)},
                "natural_language": f"Error processing operations query: {str(e)}",
                "recommendations": [],
                "confidence": 0.0,
                "actions_taken": [],
            }

    async def _process_mcp_safety_query(
        self, query: str, session_id: str, context: Dict, mcp_results: Any
    ) -> Dict[str, Any]:
        """Process safety query with MCP integration."""
        try:
            # Import MCP-enabled safety agent
            from src.api.agents.safety.mcp_safety_agent import get_mcp_safety_agent

            # Get MCP safety agent
            mcp_safety_agent = await get_mcp_safety_agent()

            # Process query with MCP results
            response = await mcp_safety_agent.process_query(
                query=query,
                session_id=session_id,
                context=context,
                mcp_results=mcp_results,
            )

            return asdict(response)

        except Exception as e:
            logger.error(f"MCP Safety processing failed: {e}")
            return {
                "response_type": "error",
                "data": {"error": str(e)},
                "natural_language": f"Error processing safety query: {str(e)}",
                "recommendations": [],
                "confidence": 0.0,
                "actions_taken": [],
            }

    async def process_warehouse_query(
        self, message: str, session_id: str = "default", context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Process a warehouse query through the MCP-enhanced planner graph.

        Args:
            message: User's message/query
            session_id: Session identifier for context
            context: Additional context for the query

        Returns:
            Dictionary containing the response and metadata
        """
        try:
            if not self.initialized:
                await self.initialize()

            # Initialize state
            initial_state = MCPWarehouseState(
                messages=[HumanMessage(content=message)],
                user_intent=None,
                routing_decision=None,
                agent_responses={},
                final_response=None,
                context=context or {},
                session_id=session_id,
                mcp_tools_discovered=[],
                mcp_execution_plan=None,
                mcp_tool_results={},
                mcp_validation_results={},
            )

            # Run the graph asynchronously
            result = await self.graph.ainvoke(initial_state)

            return {
                "response": result.get("final_response", "No response generated"),
                "intent": result.get("user_intent", "unknown"),
                "route": result.get("routing_decision", "unknown"),
                "session_id": session_id,
                "context": result.get("context", {}),
                "mcp_tools_discovered": result.get("mcp_tools_discovered", []),
                "mcp_execution_plan": result.get("mcp_execution_plan"),
                "mcp_tool_results": result.get("mcp_tool_results", {}),
            }

        except Exception as e:
            logger.error(f"Error processing MCP warehouse query: {e}")
            return {
                "response": f"I encountered an error processing your request: {str(e)}",
                "intent": "error",
                "route": "error",
                "session_id": session_id,
                "context": {},
                "mcp_tools_discovered": [],
                "mcp_execution_plan": None,
                "mcp_tool_results": {},
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
) -> Dict[str, Any]:
    """
    Process a warehouse query through the MCP-enhanced planner graph.

    Args:
        message: User's message/query
        session_id: Session identifier for context
        context: Additional context for the query

    Returns:
        Dictionary containing the response and metadata
    """
    mcp_graph = await get_mcp_planner_graph()
    return await mcp_graph.process_warehouse_query(message, session_id, context)
