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
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.api.services.reasoning import (
    get_reasoning_engine,
    ReasoningType,
    ReasoningChain,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/reasoning", tags=["reasoning"])


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
        reasoning_engine = await get_reasoning_engine()

        # Convert string reasoning types to enum
        reasoning_types = []
        if request.reasoning_types:
            for rt in request.reasoning_types:
                try:
                    reasoning_types.append(ReasoningType(rt))
                except ValueError:
                    logger.warning(f"Invalid reasoning type: {rt}")
        else:
            # Use all reasoning types if none specified
            reasoning_types = list(ReasoningType)

        # Process with reasoning
        reasoning_chain = await reasoning_engine.process_with_reasoning(
            query=request.query,
            context=request.context or {},
            reasoning_types=reasoning_types,
            session_id=request.session_id,
        )

        # Convert to response format
        steps = []
        for step in reasoning_chain.steps:
            steps.append(
                {
                    "step_id": step.step_id,
                    "step_type": step.step_type,
                    "description": step.description,
                    "reasoning": step.reasoning,
                    "input_data": step.input_data,
                    "output_data": step.output_data,
                    "confidence": step.confidence,
                    "timestamp": step.timestamp.isoformat(),
                    "dependencies": step.dependencies or [],
                }
            )

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
        logger.error(f"Reasoning analysis failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Reasoning analysis failed: {str(e)}"
        )


@router.get("/insights/{session_id}", response_model=ReasoningInsightsResponse)
async def get_reasoning_insights(session_id: str):
    """Get reasoning insights for a session."""
    try:
        reasoning_engine = await get_reasoning_engine()
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
        logger.error(f"Failed to get reasoning insights: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get reasoning insights: {str(e)}"
        )


@router.get("/types")
async def get_reasoning_types():
    """Get available reasoning types."""
    return {
        "reasoning_types": [
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
        reasoning_engine = await get_reasoning_engine()

        # Convert string reasoning types to enum
        reasoning_types = []
        if request.reasoning_types:
            for rt in request.reasoning_types:
                try:
                    reasoning_types.append(ReasoningType(rt))
                except ValueError:
                    logger.warning(f"Invalid reasoning type: {rt}")
        else:
            # Use all reasoning types if none specified
            reasoning_types = list(ReasoningType)

        # Process with reasoning
        reasoning_chain = await reasoning_engine.process_with_reasoning(
            query=request.query,
            context=request.context or {},
            reasoning_types=reasoning_types,
            session_id=request.session_id,
        )

        # Generate enhanced response with reasoning
        enhanced_response = {
            "query": request.query,
            "reasoning_chain": {
                "chain_id": reasoning_chain.chain_id,
                "reasoning_type": reasoning_chain.reasoning_type.value,
                "overall_confidence": reasoning_chain.overall_confidence,
                "execution_time": reasoning_chain.execution_time,
            },
            "reasoning_steps": [],
            "final_conclusion": reasoning_chain.final_conclusion,
            "insights": {
                "total_steps": len(reasoning_chain.steps),
                "reasoning_types_used": [rt.value for rt in reasoning_types],
                "confidence_level": (
                    "High"
                    if reasoning_chain.overall_confidence > 0.8
                    else "Medium" if reasoning_chain.overall_confidence > 0.6 else "Low"
                ),
            },
        }

        # Add reasoning steps
        for step in reasoning_chain.steps:
            enhanced_response["reasoning_steps"].append(
                {
                    "step_id": step.step_id,
                    "step_type": step.step_type,
                    "description": step.description,
                    "reasoning": step.reasoning,
                    "confidence": step.confidence,
                    "timestamp": step.timestamp.isoformat(),
                }
            )

        return enhanced_response

    except Exception as e:
        logger.error(f"Chat with reasoning failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Chat with reasoning failed: {str(e)}"
        )
