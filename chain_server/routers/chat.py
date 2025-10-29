from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import logging
import asyncio
from chain_server.graphs.mcp_integrated_planner_graph import get_mcp_planner_graph
from chain_server.services.guardrails.guardrails_service import guardrails_service
from chain_server.services.evidence.evidence_integration import (
    get_evidence_integration_service,
)
from chain_server.services.quick_actions.smart_quick_actions import (
    get_smart_quick_actions_service,
)
from chain_server.services.memory.context_enhancer import get_context_enhancer
from chain_server.services.memory.conversation_memory import (
    get_conversation_memory_service,
)
from chain_server.services.validation import (
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
    try:
        # Check input safety with guardrails
        input_safety = await guardrails_service.check_input_safety(
            req.message, req.context
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

        # Process the query through the MCP planner graph with error handling
        # Add timeout to prevent hanging on slow queries
        MAIN_QUERY_TIMEOUT = 30  # seconds for main query processing
        
        try:
            logger.info(f"Processing chat query: {req.message[:50]}...")
            mcp_planner = await get_mcp_planner_graph()
            
            # Create task with timeout protection
            query_task = asyncio.create_task(
                mcp_planner.process_warehouse_query(
                    message=req.message,
                    session_id=req.session_id or "default",
                    context=req.context,
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
                    await query_task
                except asyncio.CancelledError:
                    pass
                # Re-raise to be caught by outer exception handler
                raise
            
            # Determine if enhancements should be skipped for simple queries
            # Simple queries: short messages, greetings, or basic status checks
            skip_enhancements = (
                len(req.message.split()) <= 3 or  # Very short queries
                req.message.lower().startswith(("hi", "hello", "hey")) or  # Greetings
                "?" not in req.message or  # Not a question
                result.get("intent") == "greeting"  # Intent is just greeting
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
            # Skip enhancements for simple queries to improve response time
            if skip_enhancements:
                logger.info(f"Skipping enhancements for simple query: {req.message[:50]}")
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
                        from chain_server.services.quick_actions.smart_quick_actions import ActionContext
                        
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
            output_safety = await asyncio.wait_for(
                guardrails_service.check_output_safety(result["response"], req.context),
                timeout=5.0  # 5 second timeout for safety check
            )
            if not output_safety.is_safe:
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
        structured_response = result.get("structured_response", {})

        # Extract MCP tool execution results
        mcp_tools_used = result.get("mcp_tools_used", [])
        tool_execution_results = result.get("context", {}).get(
            "tool_execution_results", {}
        )

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
        formatted_reply = _format_user_response(
            result["response"],
            structured_response,
            confidence,
            result.get("recommendations", []),
        )

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
                intent=result.get("intent"),
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

        return ChatResponse(
            reply=formatted_reply,
            route=result.get("route", "general"),
            intent=result.get("intent", "unknown"),
            session_id=result.get("session_id", req.session_id or "default"),
            context=result.get("context"),
            structured_data=structured_response.get("data"),
            recommendations=result.get(
                "recommendations", structured_response.get("recommendations")
            ),
            confidence=confidence,  # Use the confidence we calculated above
            actions_taken=structured_response.get("actions_taken"),
            # Evidence enhancement fields
            evidence_summary=result.get("evidence_summary"),
            source_attributions=result.get("source_attributions"),
            evidence_count=result.get("evidence_count"),
            key_findings=result.get("key_findings"),
            # Quick actions fields
            quick_actions=result.get("quick_actions"),
            action_suggestions=result.get("action_suggestions"),
            # Conversation memory fields
            context_info=result.get("context_info"),
            conversation_enhanced=result.get("context_info") is not None,
            # Response validation fields
            validation_score=validation_score,
            validation_passed=validation_passed,
            validation_issues=validation_issues,
            enhancement_applied=enhancement_applied,
            enhancement_summary=enhancement_summary,
            # MCP tool execution fields
            mcp_tools_used=mcp_tools_used,
            tool_execution_results=tool_execution_results,
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
