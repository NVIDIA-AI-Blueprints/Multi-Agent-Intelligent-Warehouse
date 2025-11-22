"""
Reasoning API endpoints for advanced reasoning capabilities.

Provides endpoints for:
- Chain-of-Thought Reasoning
- Multi-Hop Reasoning
- Scenario Analysis
- Causal Reasoning
- Pattern Recognition
"""

import logging
import base64
import re
from typing import Dict, List, Optional, Any, Union
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.api.services.reasoning import (
    get_reasoning_engine,
    ReasoningType,
    ReasoningChain,
)

logger = logging.getLogger(__name__)


def _sanitize_log_data(data: Union[str, Any], max_length: int = 500) -> str:
    """
    Sanitize data for safe logging to prevent log injection attacks.
    
    Removes newlines, carriage returns, and other control characters that could
    be used to forge log entries. For suspicious data, uses base64 encoding.
    
    Args:
        data: Data to sanitize (will be converted to string)
        max_length: Maximum length of sanitized string (truncates if longer)
        
    Returns:
        Sanitized string safe for logging
    """
    if data is None:
        return "None"
    
    # Convert to string
    data_str = str(data)
    
    # Truncate if too long
    if len(data_str) > max_length:
        data_str = data_str[:max_length] + "...[truncated]"
    
    # Check for newlines, carriage returns, or other control characters
    # \x00-\x1f covers all control characters including \r (0x0D), \n (0x0A), and \t (0x09)
    if re.search(r'[\x00-\x1f]', data_str):
        # Contains control characters - base64 encode for safety
        try:
            encoded = base64.b64encode(data_str.encode('utf-8')).decode('ascii')
            return f"[base64:{encoded}]"
        except Exception:
            # If encoding fails, remove control characters
            data_str = re.sub(r'[\x00-\x1f]', '', data_str)
    
    # Remove any remaining suspicious characters
    data_str = re.sub(r'[\r\n]', '', data_str)
    
    return data_str

router = APIRouter(prefix="/api/v1/reasoning", tags=["reasoning"])


def _convert_reasoning_types(reasoning_types: Optional[List[str]]) -> List[ReasoningType]:
    """
    Convert string reasoning types to ReasoningType enum list.
    
    Args:
        reasoning_types: List of string reasoning type names, or None
        
    Returns:
        List of ReasoningType enums
    """
    if not reasoning_types:
        return list(ReasoningType)
    
    converted_types = []
    for rt in reasoning_types:
        try:
            converted_types.append(ReasoningType(rt))
        except ValueError:
            logger.warning(f"Invalid reasoning type: {_sanitize_log_data(rt)}")
    
    return converted_types if converted_types else list(ReasoningType)


def _convert_reasoning_step_to_dict(step: Any, include_full_data: bool = False) -> Dict[str, Any]:
    """
    Convert a ReasoningStep to a dictionary.
    
    Args:
        step: ReasoningStep object
        include_full_data: If True, include input_data and output_data
        
    Returns:
        Dictionary representation of the step
    """
    step_dict = {
        "step_id": step.step_id,
        "step_type": step.step_type,
        "description": step.description,
        "reasoning": step.reasoning,
        "confidence": step.confidence,
        "timestamp": step.timestamp.isoformat(),
    }
    
    if include_full_data:
        step_dict["input_data"] = step.input_data
        step_dict["output_data"] = step.output_data
        step_dict["dependencies"] = step.dependencies or []
    
    return step_dict


def _handle_reasoning_error(operation: str, error: Exception) -> HTTPException:
    """
    Handle errors in reasoning endpoints with consistent logging and error response.
    
    Args:
        operation: Description of the operation that failed
        error: Exception that occurred
        
    Returns:
        HTTPException with appropriate error message
    """
    logger.error(f"{operation} failed: {_sanitize_log_data(str(error))}")
    return HTTPException(status_code=500, detail=f"{operation} failed: {str(error)}")


def _get_confidence_level(confidence: float) -> str:
    """
    Get confidence level string based on confidence score.
    
    Args:
        confidence: Confidence score (0.0 to 1.0)
        
    Returns:
        Confidence level string: "High", "Medium", or "Low"
    """
    if confidence > 0.8:
        return "High"
    elif confidence > 0.6:
        return "Medium"
    else:
        return "Low"


async def _get_reasoning_engine_instance():
    """
    Get reasoning engine instance (helper to reduce duplication).
    
    Returns:
        Reasoning engine instance
    """
    return await get_reasoning_engine()


async def _process_reasoning_request(
    reasoning_engine: Any,
    query: str,
    context: Dict[str, Any],
    reasoning_types: List[ReasoningType],
    session_id: str,
) -> ReasoningChain:
    """
    Process a reasoning request with the engine.
    
    Args:
        reasoning_engine: Reasoning engine instance
        query: Query string
        context: Context dictionary
        reasoning_types: List of reasoning types
        session_id: Session ID
        
    Returns:
        ReasoningChain result
    """
    return await reasoning_engine.process_with_reasoning(
        query=query,
        context=context or {},
        reasoning_types=reasoning_types,
        session_id=session_id,
    )


def _build_reasoning_chain_dict(reasoning_chain: ReasoningChain) -> Dict[str, Any]:
    """
    Build reasoning chain dictionary from ReasoningChain object.
    
    Args:
        reasoning_chain: ReasoningChain object
        
    Returns:
        Dictionary with chain_id, reasoning_type, overall_confidence, execution_time
    """
    return {
        "chain_id": reasoning_chain.chain_id,
        "reasoning_type": reasoning_chain.reasoning_type.value,
        "overall_confidence": reasoning_chain.overall_confidence,
        "execution_time": reasoning_chain.execution_time,
    }


def _get_reasoning_types_list() -> List[Dict[str, str]]:
    """
    Get list of available reasoning types with metadata.
    
    Returns:
        List of dictionaries with type, name, and description
    """
    return [
        {
            "type": "chain_of_thought",
            "name": "Chain-of-Thought Reasoning",
            "description": "Step-by-step thinking process with clear reasoning steps",
        },
        {
            "type": "multi_hop",
            "name": "Multi-Hop Reasoning",
            "description": "Connect information across different data sources",
        },
        {
            "type": "scenario_analysis",
            "name": "Scenario Analysis",
            "description": "What-if reasoning and alternative scenario analysis",
        },
        {
            "type": "causal",
            "name": "Causal Reasoning",
            "description": "Cause-and-effect analysis and relationship identification",
        },
        {
            "type": "pattern_recognition",
            "name": "Pattern Recognition",
            "description": "Learn from query patterns and user behavior",
        },
    ]


class ReasoningRequest(BaseModel):
    """Request for reasoning analysis."""

    query: str
    context: Optional[Dict[str, Any]] = None
    reasoning_types: Optional[List[str]] = None
    session_id: str = "default"
    enable_reasoning: bool = True


class ReasoningResponse(BaseModel):
    """Response from reasoning analysis."""

    chain_id: str
    query: str
    reasoning_type: str
    steps: List[Dict[str, Any]]
    final_conclusion: str
    overall_confidence: float
    execution_time: float
    created_at: str


class ReasoningInsightsResponse(BaseModel):
    """Response for reasoning insights."""

    session_id: str
    total_queries: int
    reasoning_types: Dict[str, int]
    average_confidence: float
    average_execution_time: float
    common_patterns: Dict[str, int]
    recommendations: List[str]


@router.post("/analyze", response_model=ReasoningResponse)
async def analyze_with_reasoning(request: ReasoningRequest):
    """
    Analyze a query with advanced reasoning capabilities.

    Supports:
    - Chain-of-Thought Reasoning
    - Multi-Hop Reasoning
    - Scenario Analysis
    - Causal Reasoning
    - Pattern Recognition
    """
    try:
        # Get reasoning engine
        reasoning_engine = await _get_reasoning_engine_instance()

        # Convert string reasoning types to enum
        reasoning_types = _convert_reasoning_types(request.reasoning_types)

        # Process with reasoning
        reasoning_chain = await _process_reasoning_request(
            reasoning_engine=reasoning_engine,
            query=request.query,
            context=request.context or {},
            reasoning_types=reasoning_types,
            session_id=request.session_id,
        )

        # Convert to response format
        steps = [
            _convert_reasoning_step_to_dict(step, include_full_data=True)
            for step in reasoning_chain.steps
        ]

        return ReasoningResponse(
            chain_id=reasoning_chain.chain_id,
            query=reasoning_chain.query,
            reasoning_type=reasoning_chain.reasoning_type.value,
            steps=steps,
            final_conclusion=reasoning_chain.final_conclusion,
            overall_confidence=reasoning_chain.overall_confidence,
            execution_time=reasoning_chain.execution_time,
            created_at=reasoning_chain.created_at.isoformat(),
        )

    except Exception as e:
        raise _handle_reasoning_error("Reasoning analysis", e)


@router.get("/insights/{session_id}", response_model=ReasoningInsightsResponse)
async def get_reasoning_insights(session_id: str):
    """Get reasoning insights for a session."""
    try:
        reasoning_engine = await _get_reasoning_engine_instance()
        insights = await reasoning_engine.get_reasoning_insights(session_id)

        return ReasoningInsightsResponse(
            session_id=session_id,
            total_queries=insights.get("total_queries", 0),
            reasoning_types=insights.get("reasoning_types", {}),
            average_confidence=insights.get("average_confidence", 0.0),
            average_execution_time=insights.get("average_execution_time", 0.0),
            common_patterns=insights.get("common_patterns", {}),
            recommendations=insights.get("recommendations", []),
        )

    except Exception as e:
        raise _handle_reasoning_error("Failed to get reasoning insights", e)


@router.get("/types")
async def get_reasoning_types():
    """Get available reasoning types."""
    return {
        "reasoning_types": _get_reasoning_types_list()
    }


@router.post("/chat-with-reasoning")
async def chat_with_reasoning(request: ReasoningRequest):
    """
    Process a chat query with advanced reasoning capabilities.

    This endpoint combines the standard chat processing with advanced reasoning
    to provide more intelligent and transparent responses.
    """
    try:
        # Get reasoning engine
        reasoning_engine = await _get_reasoning_engine_instance()

        # Convert string reasoning types to enum
        reasoning_types = _convert_reasoning_types(request.reasoning_types)

        # Process with reasoning
        reasoning_chain = await _process_reasoning_request(
            reasoning_engine=reasoning_engine,
            query=request.query,
            context=request.context or {},
            reasoning_types=reasoning_types,
            session_id=request.session_id,
        )

        # Generate enhanced response with reasoning
        confidence_level = _get_confidence_level(reasoning_chain.overall_confidence)
        
        enhanced_response = {
            "query": request.query,
            "reasoning_chain": _build_reasoning_chain_dict(reasoning_chain),
            "reasoning_steps": [
                _convert_reasoning_step_to_dict(step, include_full_data=False)
                for step in reasoning_chain.steps
            ],
            "final_conclusion": reasoning_chain.final_conclusion,
            "insights": {
                "total_steps": len(reasoning_chain.steps),
                "reasoning_types_used": [rt.value for rt in reasoning_types],
                "confidence_level": confidence_level,
            },
        }

        return enhanced_response

    except Exception as e:
        raise _handle_reasoning_error("Chat with reasoning", e)
