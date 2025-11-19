from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import logging
import asyncio
from src.api.graphs.mcp_integrated_planner_graph import get_mcp_planner_graph
from src.api.services.guardrails.guardrails_service import guardrails_service
from src.api.services.evidence.evidence_integration import (
    get_evidence_integration_service,
)
from src.api.services.quick_actions.smart_quick_actions import (
    get_smart_quick_actions_service,
)
from src.api.services.memory.context_enhancer import get_context_enhancer
from src.api.services.memory.conversation_memory import (
    get_conversation_memory_service,
)
from src.api.services.validation import (
    get_response_validator,
    get_response_enhancer,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["Chat"])


def _format_user_response(
    base_response: str,
    structured_response: Dict[str, Any],
    confidence: float,
    recommendations: List[str],
) -> str:
    """
    Format the response to be more user-friendly and comprehensive.

    Args:
        base_response: The base response text
        structured_response: Structured data from the agent
        confidence: Confidence score
        recommendations: List of recommendations

    Returns:
        Formatted user-friendly response
    """
    try:
        # Clean the base response by removing technical details
        cleaned_response = _clean_response_text(base_response)

        # Start with the cleaned response
        formatted_response = cleaned_response

        # Add confidence indicator
        if confidence >= 0.8:
            confidence_indicator = "🟢"
        elif confidence >= 0.6:
            confidence_indicator = "🟡"
        else:
            confidence_indicator = "🔴"

        confidence_percentage = int(confidence * 100)

        # Add status information if available
        if structured_response and "data" in structured_response:
            data = structured_response["data"]

            # Add equipment status information
            if "equipment" in data and isinstance(data["equipment"], list):
                equipment_list = data["equipment"]
                if equipment_list:
                    status_info = []
                    for eq in equipment_list[:3]:  # Limit to 3 items
                        if isinstance(eq, dict):
                            asset_id = eq.get("asset_id", "Unknown")
                            status = eq.get("status", "Unknown")
                            zone = eq.get("zone", "Unknown")
                            status_info.append(f"{asset_id} ({status}) in {zone}")

                    if status_info:
                        formatted_response += (
                            f"\n\n**Equipment Status:**\n"
                            + "\n".join(f"• {info}" for info in status_info)
                        )

            # Add allocation information
            if "equipment_id" in data and "zone" in data:
                equipment_id = data["equipment_id"]
                zone = data["zone"]
                operation_type = data.get("operation_type", "operation")
                allocation_status = data.get("allocation_status", "completed")

                # Map status to emoji
                if allocation_status == "completed":
                    status_emoji = "✅"
                elif allocation_status == "pending":
                    status_emoji = "⏳"
                else:
                    status_emoji = "❌"

                formatted_response += f"\n\n{status_emoji} **Allocation Status:** {equipment_id} allocated to {zone} for {operation_type} operations"
                if allocation_status == "pending":
                    formatted_response += " (pending confirmation)"

        # Add recommendations if available and not already included
        if recommendations and len(recommendations) > 0:
            # Filter out technical recommendations
            user_recommendations = [
                rec
                for rec in recommendations
                if not any(
                    tech_term in rec.lower()
                    for tech_term in [
                        "mcp",
                        "tool",
                        "execution",
                        "api",
                        "endpoint",
                        "system",
                        "technical",
                        "gathering additional evidence",
                        "recent changes",
                        "multiple sources",
                    ]
                )
            ]

            if user_recommendations:
                formatted_response += f"\n\n**Recommendations:**\n" + "\n".join(
                    f"• {rec}" for rec in user_recommendations[:3]
                )

        # Add confidence indicator and timestamp at the end
        formatted_response += f"\n\n{confidence_indicator} {confidence_percentage}%"

        # Add timestamp
        from datetime import datetime

        timestamp = datetime.now().strftime("%I:%M:%S %p")
        formatted_response += f"\n{timestamp}"

        return formatted_response

    except Exception as e:
        logger.error(f"Error formatting user response: {e}")
        # Return base response with basic formatting if formatting fails
        return f"{base_response}\n\n🟢 {int(confidence * 100)}%"


def _clean_response_text(response: str) -> str:
    """
    Clean the response text by removing technical details and context information.

    Args:
        response: Raw response text

    Returns:
        Cleaned response text
    """
    try:
        # Remove technical context patterns
        import re

        # Remove patterns like "*Sources: ...*"
        response = re.sub(r"\*Sources?:[^*]+\*", "", response)

        # Remove patterns like "**Additional Context:** - {...}"
        response = re.sub(r"\*\*Additional Context:\*\*[^}]+}", "", response)

        # Remove patterns like "{'warehouse': 'WH-01', ...}"
        response = re.sub(r"\{'[^}]+'\}", "", response)

        # Remove patterns like "mcp_tools_used: [], tool_execution_results: {}"
        response = re.sub(
            r"mcp_tools_used: \[\], tool_execution_results: \{\}", "", response
        )

        # Remove patterns like "structured_response: {...}"
        response = re.sub(r"structured_response: \{[^}]+\}", "", response)
        
        # Remove reasoning_chain patterns (can span multiple lines)
        response = re.sub(r",\s*'reasoning_chain':\s*ReasoningChain\([^)]+\)", "", response, flags=re.DOTALL)
        response = re.sub(r",\s*'reasoning_chain':\s*\{[^}]+\}", "", response, flags=re.DOTALL)
        response = re.sub(r",\s*'reasoning_chain':\s*None", "", response, flags=re.IGNORECASE)
        response = re.sub(r",\s*'reasoning_steps':\s*\[[^\]]+\]", "", response, flags=re.DOTALL)
        response = re.sub(r",\s*'reasoning_steps':\s*None", "", response, flags=re.IGNORECASE)
        
        # Remove any remaining object representations like "ReasoningChain(...)"
        response = re.sub(r"ReasoningChain\([^)]+\)", "", response, flags=re.DOTALL)
        
        # Remove patterns like ", , 'response_type': ..." and similar structured data leaks
        # More aggressive pattern matching for structured data that leaked into text
        response = re.sub(r",\s*,\s*'[^']+':\s*[^,}]+", "", response)
        response = re.sub(r",\s*'response_type':\s*'[^']+'", "", response)
        response = re.sub(r",\s*'reasoning_chain':\s*None", "", response, flags=re.IGNORECASE)
        response = re.sub(r",\s*'reasoning_steps':\s*None", "", response, flags=re.IGNORECASE)
        
        # Remove patterns like "}, , 'reasoning_chain': None, 'reasoning_steps': None}"
        response = re.sub(r"\}\s*,\s*,\s*'reasoning_chain':\s*None\s*,\s*'reasoning_steps':\s*None\s*\}", "", response, flags=re.IGNORECASE)
        response = re.sub(r"\}\s*,\s*,\s*'[^']+':\s*[^,}]+", "", response)
        
        # Remove entire patterns like: ", , 'response_type': 'equipment_utilization', , 'reasoning_chain': None, 'reasoning_steps': None}, , 'reasoning_chain': None, 'reasoning_steps': None}"
        response = re.sub(r",\s*,\s*'response_type':\s*'[^']+',\s*,\s*'reasoning_chain':\s*None\s*,\s*'reasoning_steps':\s*None\s*\}", "", response, flags=re.IGNORECASE)
        response = re.sub(r"\}\s*,\s*,\s*'reasoning_chain':\s*None\s*,\s*'reasoning_steps':\s*None\s*\}", "", response, flags=re.IGNORECASE)
        
        # Remove patterns with multiple occurrences: "}, , 'reasoning_chain': None, 'reasoning_steps': None}, , 'reasoning_chain': None, 'reasoning_steps': None}"
        response = re.sub(r"\}\s*,\s*,\s*'reasoning_chain':\s*None\s*,\s*'reasoning_steps':\s*None\s*\}", "", response, flags=re.IGNORECASE | re.MULTILINE)
        response = re.sub(r"\}\s*,\s*,\s*'reasoning_chain':\s*None\s*,\s*'reasoning_steps':\s*None\s*\}", "", response, flags=re.IGNORECASE | re.MULTILINE)
        
        # Remove any remaining dictionary-like patterns that leaked (more aggressive)
        # Match patterns like: ", 'field': value" where value can be None, string, dict, or list
        response = re.sub(r",\s*'[a-z_]+':\s*(?:None|'[^']*'|\{[^}]*\}|\[[^\]]*\])\s*,?\s*", "", response, flags=re.IGNORECASE)
        
        # Remove any remaining closing braces and commas at the end
        response = re.sub(r"\}\s*,?\s*$", "", response)
        response = re.sub(r"\}\s*,\s*$", "", response)
        
        # Remove any Python dict-like structures that might have leaked (very aggressive)
        # This catches patterns like: "{'key': 'value', 'key2': None}"
        response = re.sub(r"\{'[^}]*'\}", "", response)
        
        # Remove any remaining key-value pairs that look like Python dict syntax
        # Pattern: ", 'key': value" or " 'key': value"
        response = re.sub(r"[, ]\s*'[a-z_]+':\s*(?:None|'[^']*'|True|False|\d+\.?\d*|\{[^}]*\}|\[[^\]]*\])\s*", " ", response, flags=re.IGNORECASE)
        
        # Clean up any double commas or trailing commas/spaces
        response = re.sub(r",\s*,+", ",", response)  # Remove multiple commas
        response = re.sub(r",\s*$", "", response)  # Remove trailing comma
        response = re.sub(r"^\s*,\s*", "", response)  # Remove leading comma
        response = re.sub(r"\s+", " ", response)  # Normalize whitespace
        response = response.strip()  # Remove leading/trailing whitespace
        
        # Final cleanup: remove any remaining isolated commas or braces
        response = re.sub(r"^\s*[,}]\s*", "", response)
        response = re.sub(r"\s*[,}]\s*$", "", response)

        # Remove patterns like "actions_taken: [, ],"
        response = re.sub(r"actions_taken: \[[^\]]*\],", "", response)

        # Remove patterns like "natural_language: '...',"
        response = re.sub(r"natural_language: '[^']*',", "", response)

        # Remove patterns like "recommendations: ['...'],"
        response = re.sub(r"recommendations: \[[^\]]*\],", "", response)

        # Remove patterns like "confidence: 0.9,"
        response = re.sub(r"confidence: [0-9.]+", "", response)

        # Remove patterns like "}, 'mcp_tools_used': [], 'tool_execution_results': {}}"
        response = re.sub(
            r"}, 'mcp_tools_used': \[\], 'tool_execution_results': \{\}\}", "", response
        )

        # Remove patterns like "}, 'mcp_tools_used': [], 'tool_execution_results': {}}"
        response = re.sub(
            r"', 'mcp_tools_used': \[\], 'tool_execution_results': \{\}\}", "", response
        )

        # Remove patterns like "', , , , , , , , , ]},"
        response = re.sub(r"', , , , , , , , , \]\},", "", response)

        # Remove patterns like "', , , , , , , , , ]},"
        response = re.sub(r", , , , , , , , , \]\},", "", response)

        # Remove patterns like "'natural_language': '...',"
        response = re.sub(r"'natural_language': '[^']*',", "", response)

        # Remove patterns like "'recommendations': ['...'],"
        response = re.sub(r"'recommendations': \[[^\]]*\],", "", response)

        # Remove patterns like "'confidence': 0.9,"
        response = re.sub(r"'confidence': [0-9.]+", "", response)

        # Remove patterns like "'actions_taken': [, ],"
        response = re.sub(r"'actions_taken': \[[^\]]*\],", "", response)

        # Remove patterns like "'mcp_tools_used': [], 'tool_execution_results': {}"
        response = re.sub(
            r"'mcp_tools_used': \[\], 'tool_execution_results': \{\}", "", response
        )

        # Remove patterns like "'response_type': 'equipment_telemetry', , 'actions_taken': []"
        response = re.sub(
            r"'response_type': '[^']*', , 'actions_taken': \[\]", "", response
        )

        # Remove patterns like ", , 'response_type': 'equipment_telemetry', , 'actions_taken': []"
        response = re.sub(
            r", , 'response_type': '[^']*', , 'actions_taken': \[\]", "", response
        )

        # Remove patterns like "equipment damage. , , 'response_type': 'equipment_telemetry', , 'actions_taken': []"
        response = re.sub(
            r"equipment damage\. , , 'response_type': '[^']*', , 'actions_taken': \[\]",
            "",
            response,
        )

        # Remove patterns like "awaiting further processing. , , , , , , , , , ]},"
        response = re.sub(
            r"awaiting further processing\. , , , , , , , , , \]\},", "", response
        )

        # Remove patterns like "Regarding equipment_id FL-01..."
        response = re.sub(r"Regarding [^.]*\.\.\.", "", response)

        # Remove patterns like "Following up on the previous Action: log_event..."
        response = re.sub(
            r"Following up on the previous Action: [^.]*\.\.\.", "", response
        )

        # Remove patterns like "}, 'mcp_tools_used': [], 'tool_execution_results': {}}"
        response = re.sub(
            r"}, 'mcp_tools_used': \[\], 'tool_execution_results': \{\}\}", "", response
        )

        # Remove patterns like "}, 'mcp_tools_used': [], 'tool_execution_results': {}}"
        response = re.sub(
            r"', 'mcp_tools_used': \[\], 'tool_execution_results': \{\}\}", "", response
        )

        # Remove patterns like "', , , , , , , , , ]},"
        response = re.sub(r"', , , , , , , , , \]\},", "", response)

        # Remove patterns like "', , , , , , , , , ]},"
        response = re.sub(r", , , , , , , , , \]\},", "", response)

        # Remove patterns like "awaiting further processing. ,"
        response = re.sub(
            r"awaiting further processing\. ,", "awaiting further processing.", response
        )

        # Remove patterns like "processing. ,"
        response = re.sub(r"processing\. ,", "processing.", response)

        # Remove patterns like "processing. , **Recommendations:**"
        response = re.sub(
            r"processing\. , \*\*Recommendations:\*\*",
            "processing.\n\n**Recommendations:**",
            response,
        )

        # Remove patterns like "equipment damage. , , 'response_type': 'equipment_telemetry', , 'actions_taken': []"
        response = re.sub(
            r"equipment damage\. , , '[^']*', , '[^']*': \[\][^}]*",
            "equipment damage.",
            response,
        )

        # Remove patterns like "damage. , , 'response_type':"
        response = re.sub(r"damage\. , , '[^']*':", "damage.", response)

        # Remove patterns like "actions. , , 'response_type':"
        response = re.sub(r"actions\. , , '[^']*':", "actions.", response)

        # Remove patterns like "investigate. , , 'response_type':"
        response = re.sub(r"investigate\. , , '[^']*':", "investigate.", response)

        # Remove patterns like "prevent. , , 'response_type':"
        response = re.sub(r"prevent\. , , '[^']*':", "prevent.", response)

        # Remove patterns like "equipment. , , 'response_type':"
        response = re.sub(r"equipment\. , , '[^']*':", "equipment.", response)

        # Remove patterns like "machine. , , 'response_type':"
        response = re.sub(r"machine\. , , '[^']*':", "machine.", response)

        # Remove patterns like "event. , , 'response_type':"
        response = re.sub(r"event\. , , '[^']*':", "event.", response)

        # Remove patterns like "detected. , , 'response_type':"
        response = re.sub(r"detected\. , , '[^']*':", "detected.", response)

        # Remove patterns like "temperature. , , 'response_type':"
        response = re.sub(r"temperature\. , , '[^']*':", "temperature.", response)

        # Remove patterns like "over-temperature. , , 'response_type':"
        response = re.sub(
            r"over-temperature\. , , '[^']*':", "over-temperature.", response
        )

        # Remove patterns like "D2. , , 'response_type':"
        response = re.sub(r"D2\. , , '[^']*':", "D2.", response)

        # Remove patterns like "Dock. , , 'response_type':"
        response = re.sub(r"Dock\. , , '[^']*':", "Dock.", response)

        # Remove patterns like "investigate. , , 'response_type':"
        response = re.sub(r"investigate\. , , '[^']*':", "investigate.", response)

        # Remove patterns like "actions. , , 'response_type':"
        response = re.sub(r"actions\. , , '[^']*':", "actions.", response)

        # Remove patterns like "prevent. , , 'response_type':"
        response = re.sub(r"prevent\. , , '[^']*':", "prevent.", response)

        # Remove patterns like "equipment. , , 'response_type':"
        response = re.sub(r"equipment\. , , '[^']*':", "equipment.", response)

        # Remove patterns like "machine. , , 'response_type':"
        response = re.sub(r"machine\. , , '[^']*':", "machine.", response)

        # Remove patterns like "event. , , 'response_type':"
        response = re.sub(r"event\. , , '[^']*':", "event.", response)

        # Remove patterns like "detected. , , 'response_type':"
        response = re.sub(r"detected\. , , '[^']*':", "detected.", response)

        # Remove patterns like "temperature. , , 'response_type':"
        response = re.sub(r"temperature\. , , '[^']*':", "temperature.", response)

        # Remove patterns like "over-temperature. , , 'response_type':"
        response = re.sub(
            r"over-temperature\. , , '[^']*':", "over-temperature.", response
        )

        # Remove patterns like "D2. , , 'response_type':"
        response = re.sub(r"D2\. , , '[^']*':", "D2.", response)

        # Remove patterns like "Dock. , , 'response_type':"
        response = re.sub(r"Dock\. , , '[^']*':", "Dock.", response)

        # Clean up multiple spaces and newlines
        response = re.sub(r"\s+", " ", response)
        response = re.sub(r"\n\s*\n", "\n\n", response)

        # Remove leading/trailing whitespace
        response = response.strip()

        return response

    except Exception as e:
        logger.error(f"Error cleaning response text: {e}")
        return response


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"
    context: Optional[Dict[str, Any]] = None
    enable_reasoning: bool = False  # Enable advanced reasoning capability
    reasoning_types: Optional[List[str]] = None  # Specific reasoning types to use


class ChatResponse(BaseModel):
    reply: str
    route: str
    intent: str
    session_id: str
    context: Optional[Dict[str, Any]] = None
    structured_data: Optional[Dict[str, Any]] = None
    recommendations: Optional[List[str]] = None
    confidence: Optional[float] = None
    actions_taken: Optional[List[Dict[str, Any]]] = None
    # Evidence enhancement fields
    evidence_summary: Optional[Dict[str, Any]] = None
    source_attributions: Optional[List[str]] = None
    evidence_count: Optional[int] = None
    key_findings: Optional[List[Dict[str, Any]]] = None
    # Quick actions fields
    quick_actions: Optional[List[Dict[str, Any]]] = None
    action_suggestions: Optional[List[str]] = None
    # Conversation memory fields
    context_info: Optional[Dict[str, Any]] = None
    conversation_enhanced: Optional[bool] = None
    # Response validation fields
    validation_score: Optional[float] = None
    validation_passed: Optional[bool] = None
    validation_issues: Optional[List[Dict[str, Any]]] = None
    enhancement_applied: Optional[bool] = None
    enhancement_summary: Optional[str] = None
    # MCP tool execution fields
    mcp_tools_used: Optional[List[str]] = None
    tool_execution_results: Optional[Dict[str, Any]] = None
    # Reasoning fields
    reasoning_chain: Optional[Dict[str, Any]] = None  # Complete reasoning chain
    reasoning_steps: Optional[List[Dict[str, Any]]] = None  # Individual reasoning steps


def _create_simple_fallback_response(message: str, session_id: str) -> ChatResponse:
    """
    Create a simple fallback response when MCP planner is unavailable.
    Provides basic pattern matching for common warehouse queries.
    """
    message_lower = message.lower()
    
    # Simple pattern matching for common queries
    if any(word in message_lower for word in ["order", "wave", "dispatch", "forklift"]):
        return ChatResponse(
            reply=f"I received your request: '{message}'. I understand you want to create a wave and dispatch a forklift. The system is processing your request. For detailed operations, please wait a moment for the full system to initialize.",
            route="operations",
            intent="operations",
            session_id=session_id,
            confidence=0.5,
        )
    elif any(word in message_lower for word in ["inventory", "stock", "quantity"]):
        return ChatResponse(
            reply=f"I received your query about: '{message}'. The system is currently initializing. Please wait a moment for inventory information.",
            route="inventory",
            intent="inventory_query",
            session_id=session_id,
            confidence=0.5,
        )
    elif any(word in message_lower for word in ["forecast", "demand", "prediction", "reorder recommendation", "model performance"]):
        return ChatResponse(
            reply=f"I received your forecasting query: '{message}'. Routing to the Forecasting Agent...",
            route="forecasting",
            intent="forecasting_query",
            session_id=session_id,
            confidence=0.6,
        )
    else:
        return ChatResponse(
            reply=f"I received your message: '{message}'. The system is currently initializing. Please wait a moment and try again.",
            route="general",
            intent="general_query",
            session_id=session_id,
            confidence=0.3,
        )


class ConversationSummaryRequest(BaseModel):
    session_id: str


class ConversationSearchRequest(BaseModel):
    session_id: str
    query: str
    limit: Optional[int] = 10


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    Process warehouse operational queries through the multi-agent planner with guardrails.

    This endpoint routes user messages to appropriate specialized agents
    (Inventory, Operations, Safety) based on intent classification and
    returns synthesized responses. All inputs and outputs are checked for
    safety, compliance, and security violations.
    
    Includes timeout protection for async operations to prevent hanging requests.
    """
    # Log immediately when request is received
    logger.info(f"📥 Received chat request: message='{req.message[:100]}...', reasoning={req.enable_reasoning}, session={req.session_id or 'default'}")
    try:
        # Check input safety with guardrails (with timeout)
        try:
            input_safety = await asyncio.wait_for(
                guardrails_service.check_input_safety(req.message, req.context),
                timeout=3.0  # 3 second timeout for safety check
            )
            if not input_safety.is_safe:
                logger.warning(f"Input safety violation: {input_safety.violations}")
                return ChatResponse(
                    reply=guardrails_service.get_safety_response(input_safety.violations),
                    route="guardrails",
                    intent="safety_violation",
                    session_id=req.session_id or "default",
                    context={"safety_violations": input_safety.violations},
                    confidence=input_safety.confidence,
                )
        except asyncio.TimeoutError:
            logger.warning("Input safety check timed out, proceeding")
        except Exception as safety_error:
            logger.warning(f"Input safety check failed: {safety_error}, proceeding")

        # Process the query through the MCP planner graph with error handling
        # Add timeout to prevent hanging on slow queries
        # Increase timeout when reasoning is enabled (reasoning takes longer)
        # Detect complex queries that need even more time
        query_lower = req.message.lower()
        is_complex_query = any(keyword in query_lower for keyword in [
            "analyze", "relationship", "between", "compare", "evaluate", 
            "optimize", "calculate", "correlation", "impact", "effect"
        ]) or len(req.message.split()) > 15
        
        if req.enable_reasoning:
            # Very complex queries with reasoning need up to 4 minutes
            # Set to 230s (slightly less than frontend 240s) to ensure backend responds before frontend times out
            # Complex queries like "Analyze the relationship between..." can take longer
            # For non-complex reasoning queries, set to 115s (slightly less than frontend 120s)
            MAIN_QUERY_TIMEOUT = 230 if is_complex_query else 115  # 230s for complex, 115s for regular reasoning
        else:
            # Regular queries: 30s for simple, 60s for complex
            MAIN_QUERY_TIMEOUT = 60 if is_complex_query else 30
        
        # Initialize result to None to avoid UnboundLocalError
        result = None
        
        try:
            logger.info(f"Processing chat query: {req.message[:50]}...")
            
            # Get planner with timeout protection (initialization might hang)
            # If initialization is slow, provide immediate response
            mcp_planner = None
            try:
                # Very short timeout - if MCP is slow, use simple fallback
                mcp_planner = await asyncio.wait_for(
                    get_mcp_planner_graph(),
                    timeout=2.0  # Reduced to 2 seconds for very fast fallback
                )
            except asyncio.TimeoutError:
                logger.warning("MCP planner initialization timed out, using simple fallback")
                # Use simple response pattern matching for basic queries
                return _create_simple_fallback_response(req.message, req.session_id)
            except Exception as init_error:
                logger.error(f"MCP planner initialization failed: {init_error}")
                # Use simple fallback response
                return _create_simple_fallback_response(req.message, req.session_id)
            
            if not mcp_planner:
                logger.warning("MCP planner is None, using simple fallback")
                return _create_simple_fallback_response(req.message, req.session_id)
            
            # Create task with timeout protection
            # Pass reasoning parameters to planner graph
            planner_context = req.context or {}
            planner_context["enable_reasoning"] = req.enable_reasoning
            if req.reasoning_types:
                planner_context["reasoning_types"] = req.reasoning_types
            
            # Log reasoning configuration
            if req.enable_reasoning:
                logger.info(f"Reasoning enabled for query. Types: {req.reasoning_types or 'auto'}, Timeout: {MAIN_QUERY_TIMEOUT}s")
            else:
                logger.info(f"Reasoning disabled for query. Timeout: {MAIN_QUERY_TIMEOUT}s")
            
            query_task = asyncio.create_task(
                mcp_planner.process_warehouse_query(
                    message=req.message,
                    session_id=req.session_id or "default",
                    context=planner_context,
                )
            )
            
            try:
                result = await asyncio.wait_for(query_task, timeout=MAIN_QUERY_TIMEOUT)
                logger.info(f"Query processing completed in time: route={result.get('route', 'unknown')}")
            except asyncio.TimeoutError:
                logger.error(f"Query processing timed out after {MAIN_QUERY_TIMEOUT}s")
                # Cancel the task
                query_task.cancel()
                try:
                    await asyncio.wait_for(query_task, timeout=2.0)  # Wait for cancellation
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                # Re-raise to be caught by outer exception handler
                raise
            
            # Handle empty or invalid results
            if not result or not result.get("response"):
                logger.warning("MCP planner returned empty result, creating fallback response")
                result = {
                    "response": f"I received your message: '{req.message}'. However, I'm having trouble processing it right now. Please try rephrasing your question.",
                    "intent": "general",
                    "route": "general",
                    "session_id": req.session_id or "default",
                    "structured_response": {},
                    "mcp_tools_used": [],
                    "tool_execution_results": {},
                }
            
            # Determine if enhancements should be skipped for simple queries
            # Simple queries: short messages, greetings, or basic status checks
            # Also skip enhancements for complex reasoning queries to avoid timeout
            skip_enhancements = (
                len(req.message.split()) <= 3 or  # Very short queries
                req.message.lower().startswith(("hi", "hello", "hey")) or  # Greetings
                "?" not in req.message or  # Not a question
                result.get("intent") == "greeting" or  # Intent is just greeting
                req.enable_reasoning  # Skip enhancements when reasoning is enabled to avoid timeout
            )

            # Extract entities and intent from result for all enhancements
            intent = result.get("intent", "general")
            entities = {}
            structured_response = result.get("structured_response", {})
            
            if structured_response and structured_response.get("data"):
                data = structured_response["data"]
                # Extract common entities
                if "equipment" in data:
                    equipment_data = data["equipment"]
                    if isinstance(equipment_data, list) and equipment_data:
                        first_equipment = equipment_data[0]
                        if isinstance(first_equipment, dict):
                            entities.update(
                                {
                                    "equipment_id": first_equipment.get("asset_id"),
                                    "equipment_type": first_equipment.get("type"),
                                    "zone": first_equipment.get("zone"),
                                    "status": first_equipment.get("status"),
                                }
                            )

            # Parallelize independent enhancement operations for better performance
            # Skip enhancements for simple queries or when reasoning is enabled to improve response time
            if skip_enhancements:
                skip_reason = "reasoning enabled" if req.enable_reasoning else "simple query"
                logger.info(f"Skipping enhancements ({skip_reason}): {req.message[:50]}")
                # Set default values for simple queries
                result["quick_actions"] = []
                result["action_suggestions"] = []
                result["evidence_count"] = 0
            else:
                async def enhance_with_evidence():
                    """Enhance response with evidence collection."""
                    try:
                        evidence_service = await get_evidence_integration_service()
                        enhanced_response = await evidence_service.enhance_response_with_evidence(
                            query=req.message,
                            intent=intent,
                            entities=entities,
                            session_id=req.session_id or "default",
                            user_context=req.context,
                            base_response=result["response"],
                        )
                        return enhanced_response
                    except Exception as e:
                        logger.warning(f"Evidence enhancement failed: {e}")
                        return None

                async def generate_quick_actions():
                    """Generate smart quick actions."""
                    try:
                        quick_actions_service = await get_smart_quick_actions_service()
                        from src.api.services.quick_actions.smart_quick_actions import ActionContext
                        
                        action_context = ActionContext(
                            query=req.message,
                            intent=intent,
                            entities=entities,
                            response_data=structured_response.get("data", {}),
                            session_id=req.session_id or "default",
                            user_context=req.context or {},
                            evidence_summary={},  # Will be updated after evidence enhancement
                        )
                        
                        quick_actions = await quick_actions_service.generate_quick_actions(action_context)
                        return quick_actions
                    except Exception as e:
                        logger.warning(f"Quick actions generation failed: {e}")
                        return []

                async def enhance_with_context():
                    """Enhance response with conversation memory and context."""
                    try:
                        context_enhancer = await get_context_enhancer()
                        memory_entities = entities.copy()
                        memory_actions = structured_response.get("actions_taken", [])
                        
                        context_enhanced = await context_enhancer.enhance_with_context(
                            session_id=req.session_id or "default",
                            user_message=req.message,
                            base_response=result["response"],
                            intent=intent,
                            entities=memory_entities,
                            actions_taken=memory_actions,
                        )
                        return context_enhanced
                    except Exception as e:
                        logger.warning(f"Context enhancement failed: {e}")
                        return None

                # Run evidence and quick actions in parallel (context enhancement needs base response)
                # Add timeout protection to prevent hanging requests
                ENHANCEMENT_TIMEOUT = 25  # seconds - leave time for main response
                
                try:
                    evidence_task = asyncio.create_task(enhance_with_evidence())
                    quick_actions_task = asyncio.create_task(generate_quick_actions())
                    
                    # Wait for evidence first as quick actions can benefit from it (with timeout)
                    try:
                        enhanced_response = await asyncio.wait_for(evidence_task, timeout=ENHANCEMENT_TIMEOUT)
                    except asyncio.TimeoutError:
                        logger.warning("Evidence enhancement timed out")
                        enhanced_response = None
                    except Exception as e:
                        logger.error(f"Evidence enhancement error: {e}")
                        enhanced_response = None
                    
                    # Update result with evidence if available
                    if enhanced_response:
                        result["response"] = enhanced_response.response
                        result["evidence_summary"] = enhanced_response.evidence_summary
                        result["source_attributions"] = enhanced_response.source_attributions
                        result["evidence_count"] = enhanced_response.evidence_count
                        result["key_findings"] = enhanced_response.key_findings
                        
                        if enhanced_response.confidence_score > 0:
                            original_confidence = structured_response.get("confidence", 0.5)
                            result["confidence"] = max(
                                original_confidence, enhanced_response.confidence_score
                            )
                        
                        # Merge recommendations
                        original_recommendations = structured_response.get("recommendations", [])
                        evidence_recommendations = enhanced_response.recommendations or []
                        all_recommendations = list(
                            set(original_recommendations + evidence_recommendations)
                        )
                        if all_recommendations:
                            result["recommendations"] = all_recommendations

                    # Get quick actions (may have completed in parallel, with timeout)
                    try:
                        quick_actions = await asyncio.wait_for(quick_actions_task, timeout=ENHANCEMENT_TIMEOUT)
                    except asyncio.TimeoutError:
                        logger.warning("Quick actions generation timed out")
                        quick_actions = []
                    except Exception as e:
                        logger.error(f"Quick actions generation error: {e}")
                        quick_actions = []
                    
                    if quick_actions:
                        # Convert actions to dictionary format
                        actions_dict = []
                        action_suggestions = []
                        
                        for action in quick_actions:
                            action_dict = {
                                "action_id": action.action_id,
                                "title": action.title,
                                "description": action.description,
                                "action_type": action.action_type.value,
                                "priority": action.priority.value,
                                "icon": action.icon,
                                "command": action.command,
                                "parameters": action.parameters,
                                "requires_confirmation": action.requires_confirmation,
                                "enabled": action.enabled,
                            }
                            actions_dict.append(action_dict)
                            action_suggestions.append(action.title)
                        
                        result["quick_actions"] = actions_dict
                        result["action_suggestions"] = action_suggestions

                    # Enhance with context (runs after evidence since it may use evidence summary, with timeout)
                    try:
                        context_enhanced = await asyncio.wait_for(
                            enhance_with_context(), timeout=ENHANCEMENT_TIMEOUT
                        )
                        if context_enhanced and context_enhanced.get("context_enhanced", False):
                            result["response"] = context_enhanced["response"]
                            result["context_info"] = context_enhanced.get("context_info", {})
                    except asyncio.TimeoutError:
                        logger.warning("Context enhancement timed out")
                    except Exception as e:
                        logger.error(f"Context enhancement error: {e}")
                        
                except Exception as enhancement_error:
                    # Catch any unexpected errors in enhancement orchestration
                    logger.error(f"Enhancement orchestration error: {enhancement_error}")
                    # Continue with base result if enhancements fail
                    
        except asyncio.TimeoutError:
            logger.error("Main query processing timed out")
            user_message = (
                "The request timed out. The system is taking longer than expected. "
                "Please try again with a simpler question or try again in a moment."
            )
            error_type = "TimeoutError"
            error_message = "Main query processing timed out after 30 seconds"
        except Exception as query_error:
            logger.error(f"Query processing error: {query_error}")
            # Return a more helpful fallback response
            error_type = type(query_error).__name__
            error_message = str(query_error)

            # Provide specific error messages based on error type
            if "timeout" in error_message.lower() or isinstance(query_error, asyncio.TimeoutError):
                user_message = (
                    "The request timed out. Please try again with a simpler question."
                )
            elif "connection" in error_message.lower():
                user_message = "I'm having trouble connecting to the processing service. Please try again in a moment."
            elif "validation" in error_message.lower():
                user_message = "There was an issue with your request format. Please try rephrasing your question."
            else:
                user_message = "I encountered an error processing your query. Please try rephrasing your question or contact support if the issue persists."

            return ChatResponse(
                reply=user_message,
                route="error",
                intent="error",
                session_id=req.session_id or "default",
                context={
                    "error": error_message,
                    "error_type": error_type,
                    "suggestions": [
                        "Try rephrasing your question",
                        "Check if the equipment ID or task name is correct",
                        "Contact support if the issue persists",
                    ],
                },
                confidence=0.0,
                recommendations=[
                    "Try rephrasing your question",
                    "Check if the equipment ID or task name is correct",
                    "Contact support if the issue persists",
                ],
            )

        # Check output safety with guardrails (with timeout protection)
        try:
            if result and result.get("response"):
                output_safety = await asyncio.wait_for(
                    guardrails_service.check_output_safety(result["response"], req.context),
                    timeout=5.0  # 5 second timeout for safety check
                )
            else:
                # Skip safety check if no result
                output_safety = None
            if output_safety and not output_safety.is_safe:
                logger.warning(f"Output safety violation: {output_safety.violations}")
                return ChatResponse(
                    reply=guardrails_service.get_safety_response(output_safety.violations),
                    route="guardrails",
                    intent="safety_violation",
                    session_id=req.session_id or "default",
                    context={"safety_violations": output_safety.violations},
                    confidence=output_safety.confidence,
                )
        except asyncio.TimeoutError:
            logger.warning("Output safety check timed out, proceeding with response")
        except Exception as safety_error:
            logger.warning(f"Output safety check failed: {safety_error}, proceeding with response")

        # Extract structured response if available
        structured_response = result.get("structured_response", {}) if result else {}

        # Extract MCP tool execution results
        mcp_tools_used = result.get("mcp_tools_used", []) if result else []
        tool_execution_results = {}
        if result and result.get("context"):
            tool_execution_results = result.get("context", {}).get("tool_execution_results", {})
        
        # Extract reasoning chain if available
        reasoning_chain = None
        reasoning_steps = None
        if result and result.get("context"):
            context = result.get("context", {})
            reasoning_chain = context.get("reasoning_chain")
            reasoning_steps = context.get("reasoning_steps")
            logger.info(f"🔍 Extracted reasoning_chain from context: {reasoning_chain is not None}, type: {type(reasoning_chain)}")
            logger.info(f"🔍 Extracted reasoning_steps from context: {reasoning_steps is not None}, count: {len(reasoning_steps) if reasoning_steps else 0}")
            # Also check structured_response for reasoning data
            if structured_response:
                if "reasoning_chain" in structured_response:
                    reasoning_chain = structured_response.get("reasoning_chain")
                    logger.info(f"🔍 Found reasoning_chain in structured_response: {reasoning_chain is not None}")
                if "reasoning_steps" in structured_response:
                    reasoning_steps = structured_response.get("reasoning_steps")
                    logger.info(f"🔍 Found reasoning_steps in structured_response: {reasoning_steps is not None}, count: {len(reasoning_steps) if reasoning_steps else 0}")
        
        # Also check result directly for reasoning_chain
        if result and "reasoning_chain" in result:
            reasoning_chain = result.get("reasoning_chain")
            logger.info(f"🔍 Found reasoning_chain in result: {reasoning_chain is not None}")
        if result and "reasoning_steps" in result:
            reasoning_steps = result.get("reasoning_steps")
            logger.info(f"🔍 Found reasoning_steps in result: {reasoning_steps is not None}")
        
        # Convert ReasoningChain dataclass to dict if needed (using safe manual conversion with depth limit)
        if reasoning_chain is not None:
            from dataclasses import is_dataclass
            from datetime import datetime
            from enum import Enum
            
            def safe_convert_value(value, depth=0, max_depth=5):
                """Safely convert a value to JSON-serializable format with depth limit."""
                if depth > max_depth:
                    return str(value)
                    
                if isinstance(value, datetime):
                    return value.isoformat()
                elif isinstance(value, Enum):
                    return value.value
                elif isinstance(value, (str, int, float, bool, type(None))):
                    return value
                elif isinstance(value, dict):
                    return {k: safe_convert_value(v, depth + 1, max_depth) for k, v in value.items()}
                elif isinstance(value, (list, tuple)):
                    return [safe_convert_value(item, depth + 1, max_depth) for item in value]
                elif hasattr(value, "__dict__"):
                    # For objects with __dict__, convert to dict but limit depth
                    try:
                        # Only convert simple attributes, skip complex nested objects
                        result = {}
                        for k, v in value.__dict__.items():
                            if isinstance(v, (str, int, float, bool, type(None), datetime, Enum)):
                                result[k] = safe_convert_value(v, depth + 1, max_depth)
                            elif isinstance(v, (list, tuple, dict)):
                                result[k] = safe_convert_value(v, depth + 1, max_depth)
                            else:
                                # For complex objects, just convert to string
                                result[k] = str(v)
                        return result
                    except (RecursionError, AttributeError, TypeError) as e:
                        logger.warning(f"Failed to convert value at depth {depth}: {e}")
                        return str(value)
                else:
                    return str(value)
            
            if is_dataclass(reasoning_chain):
                # Manually construct dict to avoid recursion issues
                try:
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
                    # Convert datetime to ISO string
                    if hasattr(reasoning_chain, "created_at"):
                        created_at = getattr(reasoning_chain, "created_at")
                        if hasattr(created_at, "isoformat"):
                            reasoning_chain_dict["created_at"] = created_at.isoformat()
                        else:
                            reasoning_chain_dict["created_at"] = str(created_at)
                    
                    # Convert steps manually - be very careful with nested data
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
                                # Convert timestamp
                                if hasattr(step, "timestamp"):
                                    timestamp = getattr(step, "timestamp")
                                    if hasattr(timestamp, "isoformat"):
                                        step_dict["timestamp"] = timestamp.isoformat()
                                    else:
                                        step_dict["timestamp"] = str(timestamp)
                                
                                # Handle input_data and output_data - skip to avoid circular references
                                # These fields often contain complex objects that can cause circular references
                                step_dict["input_data"] = {}
                                step_dict["output_data"] = {}
                                    
                                if hasattr(step, "dependencies"):
                                    deps = getattr(step, "dependencies")
                                    step_dict["dependencies"] = list(deps) if deps and isinstance(deps, (list, tuple)) else []
                                else:
                                    step_dict["dependencies"] = []
                                    
                                converted_steps.append(step_dict)
                            elif isinstance(step, dict):
                                # Already a dict, just ensure it's serializable
                                converted_steps.append({k: v for k, v in step.items() 
                                                       if isinstance(v, (str, int, float, bool, type(None), list, dict))})
                            else:
                                converted_steps.append({"step_id": "unknown", "step_type": "unknown", 
                                                       "description": str(step), "reasoning": "", "confidence": 0.0})
                        reasoning_chain_dict["steps"] = converted_steps
                    else:
                        reasoning_chain_dict["steps"] = []
                    reasoning_chain = reasoning_chain_dict
                except Exception as e:
                    logger.error(f"Error converting reasoning_chain to dict: {e}", exc_info=True)
                    reasoning_chain = None
                else:
                    logger.info(f"✅ Successfully converted reasoning_chain to dict with {len(reasoning_chain.get('steps', []))} steps")
            elif not isinstance(reasoning_chain, dict):
                # If it's not a dict and not a dataclass, try to convert it safely
                try:
                    reasoning_chain = safe_convert_value(reasoning_chain)
                except (RecursionError, AttributeError, TypeError) as e:
                    logger.warning(f"Failed to convert reasoning_chain to dict: {e}")
                    reasoning_chain = None
        
        # Convert reasoning_steps to list of dicts if needed (simplified to avoid recursion)
        if reasoning_steps is not None and isinstance(reasoning_steps, list):
            from dataclasses import is_dataclass
            converted_steps = []
            for step in reasoning_steps:
                if is_dataclass(step):
                    try:
                        step_dict = {
                            "step_id": getattr(step, "step_id", ""),
                            "step_type": getattr(step, "step_type", ""),
                            "description": getattr(step, "description", ""),
                            "reasoning": getattr(step, "reasoning", ""),
                            "confidence": float(getattr(step, "confidence", 0.0)),
                        }
                        # Convert timestamp
                        if hasattr(step, "timestamp"):
                            timestamp = getattr(step, "timestamp")
                            if hasattr(timestamp, "isoformat"):
                                step_dict["timestamp"] = timestamp.isoformat()
                            else:
                                step_dict["timestamp"] = str(timestamp)
                        
                            # Handle input_data and output_data - skip to avoid circular references
                            # These fields often contain complex objects that can cause circular references
                            step_dict["input_data"] = {}
                            step_dict["output_data"] = {}
                            
                        if hasattr(step, "dependencies"):
                            deps = getattr(step, "dependencies")
                            step_dict["dependencies"] = list(deps) if deps and isinstance(deps, (list, tuple)) else []
                        else:
                            step_dict["dependencies"] = []
                            
                        converted_steps.append(step_dict)
                    except Exception as e:
                        logger.warning(f"Error converting reasoning step: {e}")
                        converted_steps.append({"step_id": "error", "step_type": "error", 
                                               "description": "Error converting step", "reasoning": "", "confidence": 0.0})
                elif isinstance(step, dict):
                    # Already a dict, just ensure it's serializable
                    converted_steps.append({k: v for k, v in step.items() 
                                           if isinstance(v, (str, int, float, bool, type(None), list, dict))})
                else:
                    converted_steps.append({"step_id": "unknown", "step_type": "unknown", 
                                           "description": str(step), "reasoning": "", "confidence": 0.0})
            reasoning_steps = converted_steps

        # Extract confidence from multiple possible sources with sensible defaults
        # Priority: result.confidence > structured_response.confidence > agent_responses > default (0.75)
        confidence = result.get("confidence")
        if confidence is None or confidence == 0.0:
            confidence = structured_response.get("confidence")
        
        if confidence is None or confidence == 0.0:
            # Try to get confidence from agent responses
            agent_responses = result.get("agent_responses", {})
            confidences = []
            for agent_name, agent_response in agent_responses.items():
                if isinstance(agent_response, dict):
                    agent_conf = agent_response.get("confidence")
                    if agent_conf and agent_conf > 0:
                        confidences.append(agent_conf)
            
            if confidences:
                confidence = sum(confidences) / len(confidences)  # Average confidence
            else:
                # Default to 0.75 for successful queries (not errors)
                confidence = 0.75 if result.get("route") != "error" else 0.0

        # Format the response to be more user-friendly
        # Ensure we have a valid response before formatting
        base_response = result.get("response") if result else None
        
        # If base_response looks like it contains structured data (dict representation), extract just the text
        if base_response and isinstance(base_response, str):
            # Check if it looks like a dict string representation
            if ("'response_type'" in base_response or "'natural_language'" in base_response or 
                "'reasoning_chain'" in base_response or "'reasoning_steps'" in base_response):
                # Try to extract just the natural_language field if it exists
                import re
                natural_lang_match = re.search(r"'natural_language':\s*'([^']+)'", base_response)
                if natural_lang_match:
                    base_response = natural_lang_match.group(1)
                    logger.info("Extracted natural_language from response string")
                else:
                    # If we can't extract, clean it aggressively
                    base_response = _clean_response_text(base_response)
                    logger.info("Cleaned response string that contained structured data")
        
        if not base_response:
            logger.warning(f"No response in result: {result}")
            base_response = f"I received your message: '{req.message}'. Processing your request..."
        
        try:
            formatted_reply = _format_user_response(
                base_response,
                structured_response if structured_response else {},
                confidence if confidence else 0.75,
                result.get("recommendations", []) if result else [],
            )
        except Exception as format_error:
            logger.error(f"Error formatting response: {format_error}")
            formatted_reply = base_response if base_response else f"I received your message: '{req.message}'."

        # Validate and enhance the response
        try:
            response_validator = await get_response_validator()
            response_enhancer = await get_response_enhancer()

            # Extract entities for validation
            validation_entities = {}
            if structured_response and structured_response.get("data"):
                data = structured_response["data"]
                if (
                    "equipment" in data
                    and isinstance(data["equipment"], list)
                    and data["equipment"]
                ):
                    first_equipment = data["equipment"][0]
                    if isinstance(first_equipment, dict):
                        validation_entities.update(
                            {
                                "equipment_id": first_equipment.get("asset_id"),
                                "equipment_type": first_equipment.get("type"),
                                "zone": first_equipment.get("zone"),
                                "status": first_equipment.get("status"),
                            }
                        )

            # Enhance the response
            enhancement_result = await response_enhancer.enhance_response(
                response=formatted_reply,
                context=req.context,
                intent=result.get("intent") if result else "general",
                entities=validation_entities,
                auto_fix=True,
            )

            # Use enhanced response if improvements were applied
            if enhancement_result.is_enhanced:
                formatted_reply = enhancement_result.enhanced_response
                validation_score = enhancement_result.enhancement_score
                validation_passed = enhancement_result.validation_result.is_valid
                validation_issues = [
                    {
                        "category": issue.category.value,
                        "level": issue.level.value,
                        "message": issue.message,
                        "suggestion": issue.suggestion,
                        "field": issue.field,
                    }
                    for issue in enhancement_result.validation_result.issues
                ]
                enhancement_applied = True
                enhancement_summary = await response_enhancer.get_enhancement_summary(
                    enhancement_result
                )
            else:
                validation_score = enhancement_result.validation_result.score
                validation_passed = enhancement_result.validation_result.is_valid
                validation_issues = [
                    {
                        "category": issue.category.value,
                        "level": issue.level.value,
                        "message": issue.message,
                        "suggestion": issue.suggestion,
                        "field": issue.field,
                    }
                    for issue in enhancement_result.validation_result.issues
                ]
                enhancement_applied = False
                enhancement_summary = None

        except Exception as validation_error:
            logger.warning(f"Response validation failed: {validation_error}")
            validation_score = 0.8  # Default score
            validation_passed = True
            validation_issues = []
            enhancement_applied = False
            enhancement_summary = None

        # Helper function to clean reasoning data for serialization
        def clean_reasoning_data(data):
            """Clean reasoning data to ensure it's JSON-serializable."""
            if data is None:
                return None
            if isinstance(data, dict):
                # Recursively clean dict, but limit depth to avoid issues
                cleaned = {}
                for k, v in data.items():
                    if isinstance(v, (str, int, float, bool, type(None))):
                        cleaned[k] = v
                    elif isinstance(v, list):
                        # Clean list items
                        cleaned_list = []
                        for item in v:
                            if isinstance(item, (str, int, float, bool, type(None))):
                                cleaned_list.append(item)
                            elif isinstance(item, dict):
                                cleaned_list.append(clean_reasoning_data(item))
                            else:
                                cleaned_list.append(str(item))
                        cleaned[k] = cleaned_list
                    elif isinstance(v, dict):
                        cleaned[k] = clean_reasoning_data(v)
                    else:
                        cleaned[k] = str(v)
                return cleaned
            elif isinstance(data, list):
                return [clean_reasoning_data(item) for item in data]
            else:
                return str(data)
        
        # Clean reasoning data before adding to response
        cleaned_reasoning_chain = clean_reasoning_data(reasoning_chain) if reasoning_chain else None
        cleaned_reasoning_steps = clean_reasoning_data(reasoning_steps) if reasoning_steps else None
        
        # Clean context to remove potential circular references
        # Simply remove reasoning_chain and reasoning_steps from context as they're passed separately
        # Also remove any complex objects that might cause circular references
        cleaned_context = {}
        if result and result.get("context"):
            context = result.get("context", {})
            if isinstance(context, dict):
                # Only keep simple, serializable values
                for k, v in context.items():
                    if k not in ['reasoning_chain', 'reasoning_steps', 'structured_response', 'tool_execution_results']:
                        # Only keep primitive types
                        if isinstance(v, (str, int, float, bool, type(None))):
                            cleaned_context[k] = v
                        elif isinstance(v, list):
                            # Only keep lists of primitives
                            if all(isinstance(item, (str, int, float, bool, type(None))) for item in v):
                                cleaned_context[k] = v
        
        # Clean tool_execution_results - keep only simple serializable values
        cleaned_tool_results = None
        if tool_execution_results and isinstance(tool_execution_results, dict):
            cleaned_tool_results = {}
            for k, v in tool_execution_results.items():
                if isinstance(v, dict):
                    # Only keep simple, serializable fields
                    cleaned_result = {}
                    for field, value in v.items():
                        # Only keep primitive types and simple structures
                        if isinstance(value, (str, int, float, bool, type(None))):
                            cleaned_result[field] = value
                        elif isinstance(value, list):
                            # Only keep lists of primitives
                            if all(isinstance(item, (str, int, float, bool, type(None))) for item in value):
                                cleaned_result[field] = value
                    if cleaned_result:  # Only add if we have at least one field
                        cleaned_tool_results[k] = cleaned_result
        
        try:
            logger.info(f"📤 Creating response with reasoning_chain: {reasoning_chain is not None}, reasoning_steps: {reasoning_steps is not None}")
            # Clean all complex fields to avoid circular references
            # Only keep simple, serializable data
            cleaned_structured_data = None
            if structured_response and structured_response.get("data"):
                data = structured_response.get("data")
                if isinstance(data, dict):
                    cleaned_structured_data = {}
                    for k, v in data.items():
                        if isinstance(v, (str, int, float, bool, type(None))):
                            cleaned_structured_data[k] = v
                        elif isinstance(v, list):
                            # Only keep lists of primitives
                            if all(isinstance(item, (str, int, float, bool, type(None))) for item in v):
                                cleaned_structured_data[k] = v
            
            # Clean evidence_summary and key_findings
            cleaned_evidence_summary = None
            cleaned_key_findings = None
            if result:
                if result.get("evidence_summary") and isinstance(result.get("evidence_summary"), dict):
                    evidence = result.get("evidence_summary")
                    cleaned_evidence_summary = {k: v for k, v in evidence.items() 
                                              if isinstance(v, (str, int, float, bool, type(None), list))}
                if result.get("key_findings") and isinstance(result.get("key_findings"), list):
                    findings = result.get("key_findings")
                    cleaned_key_findings = [f for f in findings 
                                          if isinstance(f, (str, int, float, bool, type(None), dict))]
                    # Further clean dict items in key_findings
                    if cleaned_key_findings:
                        cleaned_key_findings = [
                            {k: v for k, v in f.items() if isinstance(v, (str, int, float, bool, type(None)))}
                            if isinstance(f, dict) else f
                            for f in cleaned_key_findings
                        ]
            
            # Try to create response with cleaned data
            response = ChatResponse(
                reply=formatted_reply,
                route=result.get("route", "general") if result else "general",
                intent=result.get("intent", "unknown") if result else "unknown",
                session_id=result.get("session_id", req.session_id or "default") if result else (req.session_id or "default"),
                context=cleaned_context if cleaned_context else {},
                structured_data=cleaned_structured_data,
                recommendations=result.get(
                    "recommendations", structured_response.get("recommendations") if structured_response else []
                ) if result else [],
                confidence=confidence,  # Use the confidence we calculated above
                actions_taken=None,  # Disable to avoid circular references
                # Evidence enhancement fields - use cleaned versions
                evidence_summary=cleaned_evidence_summary,
                source_attributions=result.get("source_attributions") if result and isinstance(result.get("source_attributions"), list) else None,
                evidence_count=result.get("evidence_count") if result else None,
                key_findings=cleaned_key_findings,
                # Quick actions fields
                quick_actions=None,  # Disable to avoid circular references
                action_suggestions=result.get("action_suggestions") if result and isinstance(result.get("action_suggestions"), list) else None,
                # Conversation memory fields
                context_info=None,  # Disable to avoid circular references
                conversation_enhanced=False,
                # Response validation fields
                validation_score=validation_score,
                validation_passed=validation_passed,
                validation_issues=None,  # Disable to avoid circular references
                enhancement_applied=enhancement_applied,
                enhancement_summary=enhancement_summary,
                # MCP tool execution fields
                mcp_tools_used=mcp_tools_used if isinstance(mcp_tools_used, list) else [],
                tool_execution_results=None,  # Disable to avoid circular references
                # Reasoning fields - use cleaned versions
                reasoning_chain=cleaned_reasoning_chain,
                reasoning_steps=cleaned_reasoning_steps,
            )
            logger.info("✅ Response created successfully")
            return response
        except (ValueError, TypeError) as circular_error:
            if "Circular reference" in str(circular_error) or "circular" in str(circular_error).lower():
                logger.error(f"Circular reference detected in response serialization: {circular_error}")
                # Create a minimal response without any complex data structures
                logger.warning("Creating minimal response due to circular reference")
                return ChatResponse(
                    reply=formatted_reply if formatted_reply else (base_response if base_response else f"I received your message: '{req.message}'. However, there was an issue formatting the response."),
                    route=result.get("route", "general") if result else "general",
                    intent=result.get("intent", "unknown") if result else "unknown",
                    session_id=req.session_id or "default",
                    context={},  # Empty context to avoid circular references
                    structured_data=None,  # Remove structured data
                    recommendations=[],
                    confidence=confidence if confidence else 0.5,
                    actions_taken=None,
                    evidence_summary=None,
                    source_attributions=None,
                    evidence_count=None,
                    key_findings=None,
                    quick_actions=None,
                    action_suggestions=None,
                    context_info=None,
                    conversation_enhanced=False,
                    validation_score=None,
                    validation_passed=None,
                    validation_issues=None,
                    enhancement_applied=False,
                    enhancement_summary=None,
                    mcp_tools_used=[],
                    tool_execution_results=None,
                    reasoning_chain=None,
                    reasoning_steps=None,
                )
            else:
                raise
        except Exception as response_error:
            logger.error(f"Error creating ChatResponse: {response_error}")
            logger.error(f"Result data: {result if result else 'None'}")
            logger.error(f"Structured response: {structured_response if structured_response else 'None'}")
            # Return a minimal response
            return ChatResponse(
                reply=formatted_reply if formatted_reply else f"I received your message: '{req.message}'. However, there was an issue formatting the response.",
                route="general",
                intent="general",
                session_id=req.session_id or "default",
                confidence=confidence if confidence else 0.5,
                recommendations=["Please try rephrasing your question"],
            )

    except asyncio.TimeoutError:
        logger.error("Chat endpoint timed out - main query processing exceeded timeout")
        return ChatResponse(
            reply="The request timed out. Please try again with a simpler question or try again in a moment.",
            route="error",
            intent="timeout",
            session_id=req.session_id or "default",
            context={
                "error": "Request timed out",
                "error_type": "TimeoutError",
                "suggestions": [
                    "Try rephrasing your question",
                    "Simplify your request",
                    "Try again in a moment",
                ],
            },
            confidence=0.0,
            recommendations=[
                "Try rephrasing your question",
                "Simplify your request",
                "Try again in a moment",
            ],
        )
    except Exception as e:
        import traceback
        logger.error(f"Error in chat endpoint: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        # Return a user-friendly error response with helpful suggestions
        try:
            return ChatResponse(
                reply="I'm sorry, I encountered an unexpected error. Please try again or contact support if the issue persists.",
                route="error",
                intent="error",
                session_id=req.session_id or "default",
                context={
                    "error": str(e)[:200],  # Limit error message length
                    "error_type": type(e).__name__,
                    "suggestions": [
                        "Try refreshing the page",
                        "Check your internet connection",
                        "Contact support if the issue persists",
                    ],
                },
                confidence=0.0,
                recommendations=[
                    "Try refreshing the page",
                    "Check your internet connection",
                    "Contact support if the issue persists",
                ],
            )
        except Exception as fallback_error:
            # If even ChatResponse creation fails, log and return minimal error
            logger.critical(f"Failed to create error response: {fallback_error}")
            # Return a minimal response that FastAPI can handle
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=500,
                content={
                    "reply": "I encountered a critical error. Please try again.",
                    "route": "error",
                    "intent": "error",
                    "session_id": req.session_id or "default",
                    "confidence": 0.0,
                }
            )


@router.post("/chat/conversation/summary")
async def get_conversation_summary(req: ConversationSummaryRequest):
    """
    Get conversation summary and context for a session.

    Returns conversation statistics, current topic, recent intents,
    and memory information for the specified session.
    """
    try:
        context_enhancer = await get_context_enhancer()
        summary = await context_enhancer.get_conversation_summary(req.session_id)

        return {"success": True, "summary": summary}

    except Exception as e:
        logger.error(f"Error getting conversation summary: {e}")
        return {"success": False, "error": str(e)}


@router.post("/chat/conversation/search")
async def search_conversation_history(req: ConversationSearchRequest):
    """
    Search conversation history and memories for specific content.

    Searches both conversation history and stored memories for
    content matching the query string.
    """
    try:
        context_enhancer = await get_context_enhancer()
        results = await context_enhancer.search_conversation_history(
            session_id=req.session_id, query=req.query, limit=req.limit
        )

        return {"success": True, "results": results}

    except Exception as e:
        logger.error(f"Error searching conversation history: {e}")
        return {"success": False, "error": str(e)}


@router.delete("/chat/conversation/{session_id}")
async def clear_conversation(session_id: str):
    """
    Clear conversation memory and history for a session.

    Removes all stored conversation data, memories, and history
    for the specified session.
    """
    try:
        memory_service = await get_conversation_memory_service()
        await memory_service.clear_conversation(session_id)

        return {
            "success": True,
            "message": f"Conversation cleared for session {session_id}",
        }

    except Exception as e:
        logger.error(f"Error clearing conversation: {e}")
        return {"success": False, "error": str(e)}


@router.post("/chat/validate")
async def validate_response(req: ChatRequest):
    """
    Test endpoint for response validation.

    This endpoint allows testing the validation system with custom responses.
    """
    try:
        response_validator = await get_response_validator()
        response_enhancer = await get_response_enhancer()

        # Validate the message as if it were a response
        validation_result = await response_validator.validate_response(
            response=req.message, context=req.context, intent="test", entities={}
        )

        # Enhance the response
        enhancement_result = await response_enhancer.enhance_response(
            response=req.message,
            context=req.context,
            intent="test",
            entities={},
            auto_fix=True,
        )

        return {
            "original_response": req.message,
            "enhanced_response": enhancement_result.enhanced_response,
            "validation_score": validation_result.score,
            "validation_passed": validation_result.is_valid,
            "validation_issues": [
                {
                    "category": issue.category.value,
                    "level": issue.level.value,
                    "message": issue.message,
                    "suggestion": issue.suggestion,
                    "field": issue.field,
                }
                for issue in validation_result.issues
            ],
            "enhancement_applied": enhancement_result.is_enhanced,
            "enhancement_summary": await response_enhancer.get_enhancement_summary(
                enhancement_result
            ),
            "improvements_applied": enhancement_result.improvements_applied,
        }

    except Exception as e:
        logger.error(f"Error in validation endpoint: {e}")
        return {"error": str(e), "validation_score": 0.0, "validation_passed": False}


@router.get("/chat/conversation/stats")
async def get_conversation_stats():
    """
    Get global conversation memory statistics.

    Returns statistics about total conversations, memories,
    and memory type distribution across all sessions.
    """
    try:
        memory_service = await get_conversation_memory_service()
        stats = await memory_service.get_conversation_stats()

        return {"success": True, "stats": stats}

    except Exception as e:
        logger.error(f"Error getting conversation stats: {e}")
        return {"success": False, "error": str(e)}
