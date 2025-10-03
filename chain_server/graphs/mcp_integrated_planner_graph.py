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
import logging
import asyncio
import threading

from chain_server.services.mcp.tool_discovery import ToolDiscoveryService
from chain_server.services.mcp.tool_binding import ToolBindingService
from chain_server.services.mcp.tool_routing import ToolRoutingService, RoutingStrategy
from chain_server.services.mcp.tool_validation import ToolValidationService
from chain_server.services.mcp.base import MCPManager

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

class MCPIntentClassifier:
    """MCP-enhanced intent classifier with dynamic tool discovery."""
    
    def __init__(self, tool_discovery: ToolDiscoveryService):
        self.tool_discovery = tool_discovery
        self.tool_routing = None  # Will be set by MCP planner graph
        
    EQUIPMENT_KEYWORDS = [
        "equipment", "forklift", "conveyor", "scanner", "amr", "agv", "charger", 
        "assignment", "utilization", "maintenance", "availability", "telemetry",
        "battery", "truck", "lane", "pm", "loto", "lockout", "tagout",
        "sku", "stock", "inventory", "quantity", "available", "atp", "on_hand"
    ]
    
    OPERATIONS_KEYWORDS = [
        "shift", "task", "tasks", "workforce", "pick", "pack", "putaway", 
        "schedule", "assignment", "kpi", "performance", "equipment", "main",
        "today", "work", "job", "operation", "operations", "worker", "workers",
        "team", "team members", "staff", "employee", "employees", "active workers",
        "how many", "roles", "team members", "wave", "waves", "order", "orders",
        "zone", "zones", "line", "lines", "create", "generating", "pick wave",
        "pick waves", "order management", "zone a", "zone b", "zone c"
    ]
    
    SAFETY_KEYWORDS = [
        "safety", "incident", "compliance", "policy", "checklist", 
        "hazard", "accident", "protocol", "training", "audit",
        "over-temp", "overtemp", "temperature", "event", "detected",
        "alert", "warning", "emergency", "malfunction", "failure",
        "ppe", "protective", "equipment", "helmet", "gloves", "boots",
        "procedures", "guidelines", "standards", "regulations",
        "evacuation", "fire", "chemical", "lockout", "tagout", "loto",
        "injury", "report", "investigation", "corrective", "action",
        "issues", "problem", "concern", "violation", "breach"
    ]
    
    async def classify_intent_with_mcp(self, message: str) -> str:
        """Classify user intent using MCP tool discovery for enhanced accuracy."""
        try:
            # First, use traditional keyword-based classification
            base_intent = self.classify_intent(message)
            
            # If we have MCP tools available, use them to enhance classification
            if self.tool_discovery and len(self.tool_discovery.discovered_tools) > 0:
                # Search for tools that might help with intent classification
                relevant_tools = await self.tool_discovery.search_tools(message)
                
                # If we found relevant tools, use them to refine the intent
                if relevant_tools:
                    # Use tool categories to refine intent
                    for tool in relevant_tools[:3]:  # Check top 3 most relevant tools
                        if "equipment" in tool.name.lower() or "equipment" in tool.description.lower():
                            if base_intent in ["general", "operations"]:
                                return "equipment"
                        elif "operations" in tool.name.lower() or "workforce" in tool.description.lower():
                            if base_intent in ["general", "equipment"]:
                                return "operations"
                        elif "safety" in tool.name.lower() or "incident" in tool.description.lower():
                            if base_intent in ["general", "equipment", "operations"]:
                                return "safety"
            
            return base_intent
            
        except Exception as e:
            logger.error(f"Error in MCP intent classification: {e}")
            return self.classify_intent(message)
    
    @classmethod
    def classify_intent(cls, message: str) -> str:
        """Classify user intent based on message content."""
        message_lower = message.lower()
        
        # Check for safety-related keywords first (highest priority)
        if any(keyword in message_lower for keyword in cls.SAFETY_KEYWORDS):
            return "safety"
        
        # Check for equipment dispatch/assignment keywords (high priority)
        if any(term in message_lower for term in ["dispatch", "assign", "deploy"]) and any(term in message_lower for term in ["forklift", "equipment", "conveyor", "truck", "amr", "agv"]):
            return "equipment"
        
        # Check for operations-related keywords (high priority for workflow tasks)
        operations_score = sum(1 for keyword in cls.OPERATIONS_KEYWORDS if keyword in message_lower)
        equipment_score = sum(1 for keyword in cls.EQUIPMENT_KEYWORDS if keyword in message_lower)
        
        # Prioritize operations if it has more keywords or contains workflow terms (but not equipment dispatch)
        if operations_score > 0 and any(term in message_lower for term in ["wave", "order", "create", "pick", "pack"]) and not any(term in message_lower for term in ["dispatch", "assign", "deploy"]):
            return "operations"
        
        # Check for equipment-related keywords
        if equipment_score > 0:
            return "equipment"
        
        # Check for operations-related keywords (fallback)
        if operations_score > 0:
            return "operations"
        
        # Default to general inquiry
        return "general"

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
            
            # Start tool discovery
            await self.tool_discovery.start_discovery()
            
            # Initialize intent classifier with MCP
            self.intent_classifier = MCPIntentClassifier(self.tool_discovery)
            self.intent_classifier.tool_routing = self.tool_routing
            
            # Create the graph
            self.graph = self._create_graph()
            
            self.initialized = True
            logger.info("MCP Planner Graph initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize MCP Planner Graph: {e}")
            raise

    def _create_graph(self) -> StateGraph:
        """Create the MCP-enabled planner graph."""
        # Initialize the state graph
        workflow = StateGraph(MCPWarehouseState)
        
        # Add nodes
        workflow.add_node("route_intent", self._mcp_route_intent)
        workflow.add_node("equipment", self._mcp_equipment_agent)
        workflow.add_node("operations", self._mcp_operations_agent)
        workflow.add_node("safety", self._mcp_safety_agent)
        workflow.add_node("general", self._mcp_general_agent)
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
                "general": "general"
            }
        )
        
        # Add edges from agents to synthesis
        workflow.add_edge("equipment", "synthesize")
        workflow.add_edge("operations", "synthesize")
        workflow.add_edge("safety", "synthesize")
        workflow.add_edge("general", "synthesize")
        
        # Add edge from synthesis to end
        workflow.add_edge("synthesize", END)
        
        return workflow.compile()

    async def _mcp_route_intent(self, state: MCPWarehouseState) -> MCPWarehouseState:
        """Route user message using MCP-enhanced intent classification."""
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
            
            # Use MCP-enhanced intent classification
            intent = await self.intent_classifier.classify_intent_with_mcp(message_text)
            state["user_intent"] = intent
            state["routing_decision"] = intent
            
            # Discover available tools for this query
            if self.tool_discovery:
                available_tools = await self.tool_discovery.get_available_tools()
                state["available_tools"] = [
                    {
                        "tool_id": tool.tool_id,
                        "name": tool.name,
                        "description": tool.description,
                        "category": tool.category.value
                    }
                    for tool in available_tools
                ]
            
            logger.info(f"MCP Intent classified as: {intent} for message: {message_text[:100]}...")
            
        except Exception as e:
            logger.error(f"Error in MCP intent routing: {e}")
            state["user_intent"] = "general"
            state["routing_decision"] = "general"
        
        return state

    async def _mcp_equipment_agent(self, state: MCPWarehouseState) -> MCPWarehouseState:
        """Handle equipment queries using MCP-enabled Equipment Agent."""
        try:
            from chain_server.agents.inventory.mcp_equipment_agent import get_mcp_equipment_agent
            
            # Get the latest user message
            if not state["messages"]:
                state["agent_responses"]["equipment"] = "No message to process"
                return state
                
            latest_message = state["messages"][-1]
            if isinstance(latest_message, HumanMessage):
                message_text = latest_message.content
            else:
                message_text = str(latest_message.content)
            
            # Get session ID from context
            session_id = state.get("session_id", "default")
            
            # Get MCP equipment agent
            mcp_equipment_agent = await get_mcp_equipment_agent()
            
            # Process with MCP equipment agent
            response = await mcp_equipment_agent.process_query(
                query=message_text,
                session_id=session_id,
                context=state.get("context", {}),
                mcp_results=state.get("mcp_results")
            )
            
            # Store the response
            state["agent_responses"]["equipment"] = {
                "natural_language": response.natural_language,
                "data": response.data,
                "recommendations": response.recommendations,
                "confidence": response.confidence,
                "response_type": response.response_type,
                "mcp_tools_used": response.mcp_tools_used or [],
                "tool_execution_results": response.tool_execution_results or {},
                "actions_taken": response.actions_taken or []
            }
            
            logger.info(f"MCP Equipment agent processed request with confidence: {response.confidence}")
            
        except Exception as e:
            logger.error(f"Error in MCP equipment agent: {e}")
            state["agent_responses"]["equipment"] = {
                "natural_language": f"Error processing equipment request: {str(e)}",
                "data": {"error": str(e)},
                "recommendations": [],
                "confidence": 0.0,
                "response_type": "error",
                "mcp_tools_used": [],
                "tool_execution_results": {}
            }
        
        return state

    async def _mcp_operations_agent(self, state: MCPWarehouseState) -> MCPWarehouseState:
        """Handle operations queries using MCP-enabled Operations Agent."""
        try:
            from chain_server.agents.operations.mcp_operations_agent import get_mcp_operations_agent
            
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
            
            # Get MCP operations agent
            mcp_operations_agent = await get_mcp_operations_agent()
            
            # Process with MCP operations agent
            response = await mcp_operations_agent.process_query(
                query=message_text,
                session_id=session_id,
                context=state.get("context", {}),
                mcp_results=state.get("mcp_results")
            )
            
            # Store the response
            state["agent_responses"]["operations"] = response
            
            logger.info(f"MCP Operations agent processed request with confidence: {response.confidence}")
            
        except Exception as e:
            logger.error(f"Error in MCP operations agent: {e}")
            state["agent_responses"]["operations"] = {
                "natural_language": f"Error processing operations request: {str(e)}",
                "data": {"error": str(e)},
                "recommendations": [],
                "confidence": 0.0,
                "response_type": "error",
                "mcp_tools_used": [],
                "tool_execution_results": {}
            }
        
        return state

    async def _mcp_safety_agent(self, state: MCPWarehouseState) -> MCPWarehouseState:
        """Handle safety queries using MCP-enabled Safety Agent."""
        try:
            from chain_server.agents.safety.mcp_safety_agent import get_mcp_safety_agent
            
            # Get the latest user message
            if not state["messages"]:
                state["agent_responses"]["safety"] = "No message to process"
                return state
                
            latest_message = state["messages"][-1]
            if isinstance(latest_message, HumanMessage):
                message_text = latest_message.content
            else:
                message_text = str(latest_message.content)
            
            # Get session ID from context
            session_id = state.get("session_id", "default")
            
            # Get MCP safety agent
            mcp_safety_agent = await get_mcp_safety_agent()
            
            # Process with MCP safety agent
            response = await mcp_safety_agent.process_query(
                query=message_text,
                session_id=session_id,
                context=state.get("context", {}),
                mcp_results=state.get("mcp_results")
            )
            
            # Store the response
            state["agent_responses"]["safety"] = response
            
            logger.info(f"MCP Safety agent processed request with confidence: {response.confidence}")
            
        except Exception as e:
            logger.error(f"Error in MCP safety agent: {e}")
            state["agent_responses"]["safety"] = {
                "natural_language": f"Error processing safety request: {str(e)}",
                "data": {"error": str(e)},
                "recommendations": [],
                "confidence": 0.0,
                "response_type": "error",
                "mcp_tools_used": [],
                "tool_execution_results": {}
            }
        
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
                            best_tool.tool_id, 
                            {"query": message_text}
                        )
                        
                        response = f"[MCP GENERAL AGENT] Found relevant tool '{best_tool.name}' and executed it. Result: {str(result)[:200]}..."
                    except Exception as e:
                        response = f"[MCP GENERAL AGENT] Found relevant tool '{best_tool.name}' but execution failed: {str(e)}"
                else:
                    response = "[MCP GENERAL AGENT] No relevant tools found for this query."
            else:
                response = "[MCP GENERAL AGENT] No MCP tools available. Processing general query... (stub implementation)"
            
            state["agent_responses"]["general"] = response
            logger.info("MCP General agent processed request")
            
        except Exception as e:
            logger.error(f"Error in MCP general agent: {e}")
            state["agent_responses"]["general"] = f"Error processing general request: {str(e)}"
        
        return state

    def _mcp_synthesize_response(self, state: MCPWarehouseState) -> MCPWarehouseState:
        """Synthesize final response from MCP agent outputs."""
        try:
            routing_decision = state.get("routing_decision", "general")
            agent_responses = state.get("agent_responses", {})
            
            # Get the response from the appropriate agent
            if routing_decision in agent_responses:
                agent_response = agent_responses[routing_decision]
                
                # Handle MCP response format
                if isinstance(agent_response, dict) and "natural_language" in agent_response:
                    final_response = agent_response["natural_language"]
                    # Store structured data in context for API response
                    state["context"]["structured_response"] = agent_response
                    
                    # Add MCP tool information to context
                    if "mcp_tools_used" in agent_response:
                        state["context"]["mcp_tools_used"] = agent_response["mcp_tools_used"]
                    if "tool_execution_results" in agent_response:
                        state["context"]["tool_execution_results"] = agent_response["tool_execution_results"]
                else:
                    # Handle legacy string response format
                    final_response = str(agent_response)
            else:
                final_response = "I'm sorry, I couldn't process your request. Please try rephrasing your question."
            
            state["final_response"] = final_response
            
            # Add AI message to conversation
            if state["messages"]:
                ai_message = AIMessage(content=final_response)
                state["messages"].append(ai_message)
            
            logger.info(f"MCP Response synthesized for routing decision: {routing_decision}")
            
        except Exception as e:
            logger.error(f"Error synthesizing MCP response: {e}")
            state["final_response"] = "I encountered an error processing your request. Please try again."
        
        return state

    def _route_to_agent(self, state: MCPWarehouseState) -> str:
        """Route to the appropriate agent based on MCP intent classification."""
        routing_decision = state.get("routing_decision", "general")
        return routing_decision

    async def process_warehouse_query(
        self,
        message: str, 
        session_id: str = "default",
        context: Optional[Dict] = None
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
            # Initialize if needed
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
                mcp_results=None,
                tool_execution_plan=None,
                available_tools=None
            )
            
            # Run the graph asynchronously
            result = await self.graph.ainvoke(initial_state)
            
            return {
                "response": result.get("final_response", "No response generated"),
                "intent": result.get("user_intent", "unknown"),
                "route": result.get("routing_decision", "unknown"),
                "session_id": session_id,
                "context": result.get("context", {}),
                "mcp_tools_used": result.get("context", {}).get("mcp_tools_used", []),
                "available_tools": result.get("available_tools", [])
            }
            
        except Exception as e:
            logger.error(f"Error processing MCP warehouse query: {e}")
            return {
                "response": f"I encountered an error processing your request: {str(e)}",
                "intent": "error",
                "route": "error",
                "session_id": session_id,
                "context": {},
                "mcp_tools_used": [],
                "available_tools": []
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
    message: str, 
    session_id: str = "default",
    context: Optional[Dict] = None
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
