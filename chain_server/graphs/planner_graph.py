"""
Warehouse Operational Assistant - Planner/Router Graph
Based on NVIDIA AI Blueprint patterns for multi-agent orchestration.

This module implements the main planner/router agent that:
1. Analyzes user intents
2. Routes to appropriate specialized agents
3. Coordinates multi-agent workflows
4. Synthesizes responses from multiple agents
"""

from typing import Dict, List, Optional, TypedDict, Annotated, Any
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
import logging
import asyncio
import threading

logger = logging.getLogger(__name__)

class WarehouseState(TypedDict):
    """State management for warehouse assistant workflow."""
    messages: Annotated[List[BaseMessage], "Chat messages"]
    user_intent: Optional[str]
    routing_decision: Optional[str]
    agent_responses: Dict[str, str]
    final_response: Optional[str]
    context: Dict[str, any]
    session_id: str

class IntentClassifier:
    """Classifies user intents for warehouse operations."""
    
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
        "how many", "roles", "team members"
    ]
    
    SAFETY_KEYWORDS = [
        "safety", "incident", "compliance", "policy", "checklist", 
        "hazard", "accident", "protocol", "training", "audit"
    ]
    
    @classmethod
    def classify_intent(cls, message: str) -> str:
        """Classify user intent based on message content."""
        message_lower = message.lower()
        
        # Check for equipment-related keywords
        if any(keyword in message_lower for keyword in cls.EQUIPMENT_KEYWORDS):
            return "equipment"
        
        # Check for operations-related keywords
        if any(keyword in message_lower for keyword in cls.OPERATIONS_KEYWORDS):
            return "operations"
        
        # Check for safety-related keywords
        if any(keyword in message_lower for keyword in cls.SAFETY_KEYWORDS):
            return "safety"
        
        # Default to general inquiry
        return "general"

def route_intent(state: WarehouseState) -> WarehouseState:
    """Route user message to appropriate agent based on intent classification."""
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
        
        # Classify intent
        intent = IntentClassifier.classify_intent(message_text)
        state["user_intent"] = intent
        state["routing_decision"] = intent
        
        logger.info(f"Intent classified as: {intent} for message: {message_text[:100]}...")
        
    except Exception as e:
        logger.error(f"Error in intent routing: {e}")
        state["user_intent"] = "general"
        state["routing_decision"] = "general"
    
    return state

async def equipment_agent(state: WarehouseState) -> WarehouseState:
    """Handle equipment-related queries using the Equipment & Asset Operations Agent."""
    try:
        from chain_server.agents.inventory.equipment_agent import get_equipment_agent
        
        # Get the latest user message
        if not state["messages"]:
            state["agent_responses"]["inventory"] = "No message to process"
            return state
            
        latest_message = state["messages"][-1]
        if isinstance(latest_message, HumanMessage):
            message_text = latest_message.content
        else:
            message_text = str(latest_message.content)
        
        # Get session ID from context
        session_id = state.get("session_id", "default")
        
        # Process with Equipment & Asset Operations Agent (sync wrapper)
        response = await _process_equipment_query(
            query=message_text,
            session_id=session_id,
            context=state.get("context", {})
        )
        
        # Store the response dict directly
        state["agent_responses"]["equipment"] = response
        
        logger.info(f"Equipment agent processed request with confidence: {response.get('confidence', 0)}")
        
    except Exception as e:
        logger.error(f"Error in equipment agent: {e}")
        state["agent_responses"]["equipment"] = {
            "natural_language": f"Error processing equipment request: {str(e)}",
            "structured_data": {"error": str(e)},
            "recommendations": [],
            "confidence": 0.0,
            "response_type": "error"
        }
    
    return state

async def operations_agent(state: WarehouseState) -> WarehouseState:
    """Handle operations-related queries using the Operations Coordination Agent."""
    try:
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
        
        # Process with Operations Coordination Agent (sync wrapper)
        response = await _process_operations_query(
            query=message_text,
            session_id=session_id,
            context=state.get("context", {})
        )
        
        # Store the response dict directly
        state["agent_responses"]["operations"] = response
        
        logger.info(f"Operations agent processed request with confidence: {response.get('confidence', 0)}")
        
    except Exception as e:
        logger.error(f"Error in operations agent: {e}")
        state["agent_responses"]["operations"] = {
            "natural_language": f"Error processing operations request: {str(e)}",
            "structured_data": {"error": str(e)},
            "recommendations": [],
            "confidence": 0.0,
            "response_type": "error"
        }
    
    return state

async def safety_agent(state: WarehouseState) -> WarehouseState:
    """Handle safety and compliance queries using the Safety & Compliance Agent."""
    try:
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
        
        # Process with Safety & Compliance Agent (sync wrapper)
        response = await _process_safety_query(
            query=message_text,
            session_id=session_id,
            context=state.get("context", {})
        )
        
        # Store the response dict directly
        state["agent_responses"]["safety"] = response
        
        logger.info(f"Safety agent processed request with confidence: {response.get('confidence', 0)}")
        
    except Exception as e:
        logger.error(f"Error in safety agent: {e}")
        state["agent_responses"]["safety"] = {
            "natural_language": f"Error processing safety request: {str(e)}",
            "structured_data": {"error": str(e)},
            "recommendations": [],
            "confidence": 0.0,
            "response_type": "error"
        }
    
    return state

def general_agent(state: WarehouseState) -> WarehouseState:
    """Handle general queries that don't fit specific categories."""
    try:
        # Placeholder for general agent logic
        response = "[GENERAL AGENT] Processing general query... (stub implementation)"
        
        state["agent_responses"]["general"] = response
        logger.info("General agent processed request")
        
    except Exception as e:
        logger.error(f"Error in general agent: {e}")
        state["agent_responses"]["general"] = f"Error processing general request: {str(e)}"
    
    return state

def synthesize_response(state: WarehouseState) -> WarehouseState:
    """Synthesize final response from agent outputs."""
    try:
        routing_decision = state.get("routing_decision", "general")
        agent_responses = state.get("agent_responses", {})
        
        # Get the response from the appropriate agent
        if routing_decision in agent_responses:
            agent_response = agent_responses[routing_decision]
            
            # Handle new structured response format
            if isinstance(agent_response, dict) and "natural_language" in agent_response:
                final_response = agent_response["natural_language"]
                # Store structured data in context for API response
                state["context"]["structured_response"] = agent_response
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
        
        logger.info(f"Response synthesized for routing decision: {routing_decision}")
        
    except Exception as e:
        logger.error(f"Error synthesizing response: {e}")
        state["final_response"] = "I encountered an error processing your request. Please try again."
    
    return state

def route_to_agent(state: WarehouseState) -> str:
    """Route to the appropriate agent based on intent classification."""
    routing_decision = state.get("routing_decision", "general")
    return routing_decision

def create_planner_graph() -> StateGraph:
    """Create the main planner/router graph for warehouse operations."""
    
    # Initialize the state graph
    workflow = StateGraph(WarehouseState)
    
    # Add nodes
    workflow.add_node("route_intent", route_intent)
    workflow.add_node("equipment", equipment_agent)
    workflow.add_node("operations", operations_agent)
    workflow.add_node("safety", safety_agent)
    workflow.add_node("general", general_agent)
    workflow.add_node("synthesize", synthesize_response)
    
    # Set entry point
    workflow.set_entry_point("route_intent")
    
    # Add conditional edges for routing
    workflow.add_conditional_edges(
        "route_intent",
        route_to_agent,
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

# Global graph instance
planner_graph = create_planner_graph()

async def process_warehouse_query(
    message: str, 
    session_id: str = "default",
    context: Optional[Dict] = None
) -> Dict[str, any]:
    """
    Process a warehouse query through the planner graph.
    
    Args:
        message: User's message/query
        session_id: Session identifier for context
        context: Additional context for the query
        
    Returns:
        Dictionary containing the response and metadata
    """
    try:
        # Initialize state
        initial_state = WarehouseState(
            messages=[HumanMessage(content=message)],
            user_intent=None,
            routing_decision=None,
            agent_responses={},
            final_response=None,
            context=context or {},
            session_id=session_id
        )
        
        # Run the graph asynchronously
        result = await planner_graph.ainvoke(initial_state)
        
        return {
            "response": result.get("final_response", "No response generated"),
            "intent": result.get("user_intent", "unknown"),
            "route": result.get("routing_decision", "unknown"),
            "session_id": session_id,
            "context": result.get("context", {})
        }
        
    except Exception as e:
        logger.error(f"Error processing warehouse query: {e}")
        return {
            "response": f"I encountered an error processing your request: {str(e)}",
            "intent": "error",
            "route": "error",
            "session_id": session_id,
            "context": {}
        }

# Legacy function for backward compatibility
def route_intent(text: str) -> str:
    """Legacy function for simple intent routing."""
    return IntentClassifier.classify_intent(text)

async def _process_safety_query(query: str, session_id: str, context: Dict) -> Any:
    """Async safety agent processing."""
    try:
        from chain_server.agents.safety.safety_agent import get_safety_agent
        
        # Get safety agent
        safety_agent = await get_safety_agent()
        
        # Process query
        response = await safety_agent.process_query(
            query=query,
            session_id=session_id,
            context=context
        )
        
        # Convert SafetyResponse to dict
        from dataclasses import asdict
        return asdict(response)
        
    except Exception as e:
        logger.error(f"Safety processing failed: {e}")
        # Return a fallback response
        from chain_server.agents.safety.safety_agent import SafetyResponse
        return SafetyResponse(
            response_type="error",
            data={"error": str(e)},
            natural_language=f"Error processing safety query: {str(e)}",
            recommendations=[],
            confidence=0.0
        )

async def _process_operations_query(query: str, session_id: str, context: Dict) -> Any:
    """Async operations agent processing."""
    try:
        from chain_server.agents.operations.operations_agent import get_operations_agent
        
        # Get operations agent
        operations_agent = await get_operations_agent()
        
        # Process query
        response = await operations_agent.process_query(
            query=query,
            session_id=session_id,
            context=context
        )
        
        # Convert OperationsResponse to dict
        from dataclasses import asdict
        return asdict(response)
        
    except Exception as e:
        logger.error(f"Operations processing failed: {e}")
        # Return a fallback response
        from chain_server.agents.operations.operations_agent import OperationsResponse
        return OperationsResponse(
            response_type="error",
            data={"error": str(e)},
            natural_language=f"Error processing operations query: {str(e)}",
            recommendations=[],
            confidence=0.0
        )

async def _process_equipment_query(query: str, session_id: str, context: Dict) -> Any:
    """Async equipment agent processing."""
    try:
        from chain_server.agents.inventory.equipment_agent import get_equipment_agent
        
        # Get equipment agent
        equipment_agent = await get_equipment_agent()
        
        # Process query
        response = await equipment_agent.process_query(
            query=query,
            session_id=session_id,
            context=context
        )
        
        # Convert EquipmentResponse to dict
        from dataclasses import asdict
        return asdict(response)
        
    except Exception as e:
        logger.error(f"Equipment processing failed: {e}")
        # Return a fallback response
        from chain_server.agents.inventory.equipment_agent import EquipmentResponse
        return EquipmentResponse(
            response_type="error",
            data={"error": str(e)},
            natural_language=f"Error processing equipment query: {str(e)}",
            recommendations=[],
            confidence=0.0
        )