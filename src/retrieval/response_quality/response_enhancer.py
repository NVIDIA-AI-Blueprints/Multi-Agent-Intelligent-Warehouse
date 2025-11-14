"""
Response Enhancement Service for Warehouse Operational Assistant

Integrates response quality control with existing agents to provide enhanced
user experience with confidence indicators, source attribution, and personalization.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from datetime import datetime
import json

from .response_validator import (
    ResponseValidator, EnhancedResponse, ResponseValidation,
    UserRole, ConfidenceLevel, ResponseQuality,
    get_response_validator
)

logger = logging.getLogger(__name__)

@dataclass
class AgentResponse:
    """Standard agent response format."""
    response: str
    agent_name: str
    intent: str
    confidence: float
    data: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class EnhancedAgentResponse:
    """Enhanced agent response with quality control."""
    original_response: AgentResponse
    enhanced_response: EnhancedResponse
    user_experience_score: float
    personalization_applied: bool
    follow_up_queries: List[str]
    response_time_ms: float

class ResponseEnhancementService:
    """
    Service for enhancing agent responses with quality control and user experience improvements.
    
    Features:
    - Response validation and quality assessment
    - Confidence indicators and source attribution
    - User role-based personalization
    - Follow-up suggestions generation
    - Response consistency checks
    - User experience scoring
    """
    
    def __init__(self):
        self.validator = get_response_validator()
        self.user_experience_weights = {
            "confidence": 0.3,
            "completeness": 0.25,
            "clarity": 0.2,
            "personalization": 0.15,
            "source_attribution": 0.1
        }
    
    async def enhance_agent_response(
        self,
        agent_response: AgentResponse,
        user_role: UserRole = UserRole.OPERATOR,
        query_context: Optional[Dict[str, Any]] = None,
        evidence_data: Optional[Dict[str, Any]] = None
    ) -> EnhancedAgentResponse:
        """
        Enhance an agent response with quality control and user experience improvements.
        
        Args:
            agent_response: Original agent response
            user_role: User role for personalization
            query_context: Original query context
            evidence_data: Evidence data used for the response
            
        Returns:
            Enhanced agent response with quality control information
        """
        start_time = datetime.now()
        
        try:
            # 1. Validate the response
            validation = self.validator.validate_response(
                response=agent_response.response,
                evidence_data=evidence_data or agent_response.data,
                query_context=query_context,
                user_role=user_role
            )
            
            # 2. Enhance the response
            enhanced_response = self.validator.enhance_response(
                response=agent_response.response,
                validation=validation,
                user_role=user_role,
                query_context=query_context
            )
            
            # 3. Calculate user experience score
            ux_score = self._calculate_user_experience_score(
                validation, enhanced_response, user_role
            )
            
            # 4. Generate follow-up queries
            follow_up_queries = self._generate_follow_up_queries(
                agent_response, validation, user_role, query_context
            )
            
            # 5. Calculate response time
            response_time_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            return EnhancedAgentResponse(
                original_response=agent_response,
                enhanced_response=enhanced_response,
                user_experience_score=ux_score,
                personalization_applied=True,
                follow_up_queries=follow_up_queries,
                response_time_ms=response_time_ms
            )
            
        except Exception as e:
            logger.error(f"Error enhancing agent response: {e}")
            # Return fallback enhanced response
            return self._create_fallback_response(agent_response, user_role, str(e))
    
    async def enhance_chat_response(
        self,
        response_text: str,
        agent_name: str,
        user_role: UserRole = UserRole.OPERATOR,
        query_context: Optional[Dict[str, Any]] = None,
        evidence_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Enhance a chat response with quality control information.
        
        Args:
            response_text: Original response text
            agent_name: Name of the agent that generated the response
            user_role: User role for personalization
            query_context: Original query context
            evidence_data: Evidence data used for the response
            
        Returns:
            Enhanced response dictionary with quality control information
        """
        try:
            # Create agent response object
            agent_response = AgentResponse(
                response=response_text,
                agent_name=agent_name,
                intent=query_context.get("intent", "general") if query_context else "general",
                confidence=query_context.get("confidence", 0.8) if query_context else 0.8,
                data=evidence_data,
                metadata=query_context
            )
            
            # Enhance the response
            enhanced_response = await self.enhance_agent_response(
                agent_response=agent_response,
                user_role=user_role,
                query_context=query_context,
                evidence_data=evidence_data
            )
            
            # Convert to dictionary format for API response
            return {
                "response": enhanced_response.enhanced_response.enhanced_response,
                "original_response": enhanced_response.original_response.response,
                "agent_name": agent_name,
                "quality_control": {
                    "confidence_level": enhanced_response.enhanced_response.validation.confidence.level.value,
                    "confidence_score": enhanced_response.enhanced_response.validation.confidence.score,
                    "quality_level": enhanced_response.enhanced_response.validation.quality.value,
                    "completeness_score": enhanced_response.enhanced_response.validation.completeness_score,
                    "consistency_score": enhanced_response.enhanced_response.validation.consistency_score,
                    "is_valid": enhanced_response.enhanced_response.validation.is_valid
                },
                "source_attribution": [
                    {
                        "source_type": attr.source_type,
                        "source_name": attr.source_name,
                        "confidence": attr.confidence
                    }
                    for attr in enhanced_response.enhanced_response.validation.source_attributions
                ],
                "user_experience": {
                    "score": enhanced_response.user_experience_score,
                    "personalization_applied": enhanced_response.personalization_applied,
                    "follow_up_queries": enhanced_response.follow_up_queries
                },
                "warnings": enhanced_response.enhanced_response.validation.warnings,
                "suggestions": enhanced_response.enhanced_response.validation.suggestions,
                "response_time_ms": enhanced_response.response_time_ms,
                "metadata": enhanced_response.enhanced_response.response_metadata
            }
            
        except Exception as e:
            logger.error(f"Error enhancing chat response: {e}")
            return {
                "response": response_text,
                "original_response": response_text,
                "agent_name": agent_name,
                "quality_control": {
                    "confidence_level": "low",
                    "confidence_score": 0.0,
                    "quality_level": "insufficient",
                    "completeness_score": 0.0,
                    "consistency_score": 0.0,
                    "is_valid": False
                },
                "source_attribution": [],
                "user_experience": {
                    "score": 0.0,
                    "personalization_applied": False,
                    "follow_up_queries": []
                },
                "warnings": [f"Enhancement error: {str(e)}"],
                "suggestions": ["Please try rephrasing your query"],
                "response_time_ms": 0.0,
                "metadata": {"error": str(e)}
            }
    
    def _calculate_user_experience_score(
        self,
        validation: ResponseValidation,
        enhanced_response: EnhancedResponse,
        user_role: UserRole
    ) -> float:
        """Calculate user experience score based on multiple factors."""
        try:
            scores = {}
            
            # Confidence score
            scores["confidence"] = validation.confidence.score
            
            # Completeness score
            scores["completeness"] = validation.completeness_score
            
            # Clarity score (based on response length and structure)
            response_length = len(enhanced_response.enhanced_response.split())
            if response_length >= 20:
                scores["clarity"] = 1.0
            elif response_length >= 10:
                scores["clarity"] = 0.7
            else:
                scores["clarity"] = 0.4
            
            # Personalization score
            scores["personalization"] = 1.0 if enhanced_response.personalization_applied else 0.0
            
            # Source attribution score
            scores["source_attribution"] = min(1.0, len(validation.source_attributions) / 3)
            
            # Calculate weighted average
            ux_score = sum(
                scores[factor] * weight 
                for factor, weight in self.user_experience_weights.items()
            )
            
            return min(1.0, max(0.0, ux_score))
            
        except Exception as e:
            logger.error(f"Error calculating user experience score: {e}")
            return 0.0
    
    def _generate_follow_up_queries(
        self,
        agent_response: AgentResponse,
        validation: ResponseValidation,
        user_role: UserRole,
        query_context: Optional[Dict[str, Any]]
    ) -> List[str]:
        """Generate follow-up queries based on the response and user role."""
        try:
            follow_ups = []
            
            # Role-based follow-ups
            if user_role == UserRole.OPERATOR:
                if "workers" in agent_response.response.lower():
                    follow_ups.extend([
                        "What are my assigned tasks for today?",
                        "Show me equipment I need to use",
                        "Are there any safety alerts?"
                    ])
                elif "equipment" in agent_response.response.lower():
                    follow_ups.extend([
                        "What's the maintenance schedule?",
                        "Show me equipment status dashboard",
                        "Report equipment issue"
                    ])
                elif "tasks" in agent_response.response.lower():
                    follow_ups.extend([
                        "Show me task details",
                        "What's my next priority?",
                        "Mark task as complete"
                    ])
            
            elif user_role == UserRole.SUPERVISOR:
                if "workers" in agent_response.response.lower():
                    follow_ups.extend([
                        "Show me team performance metrics",
                        "Reassign tasks to team members",
                        "Generate shift report"
                    ])
                elif "tasks" in agent_response.response.lower():
                    follow_ups.extend([
                        "Show me task completion rates",
                        "Optimize task assignments",
                        "Generate productivity report"
                    ])
            
            # Intent-based follow-ups
            if query_context and "intent" in query_context:
                intent = query_context["intent"]
                
                if intent == "workforce":
                    follow_ups.extend([
                        "Show me shift schedules",
                        "What's the team productivity?",
                        "Generate workforce report"
                    ])
                elif intent == "task_management":
                    follow_ups.extend([
                        "Show me pending tasks",
                        "What tasks are overdue?",
                        "Generate task summary"
                    ])
                elif intent == "equipment_lookup":
                    follow_ups.extend([
                        "Show me all equipment status",
                        "What equipment needs maintenance?",
                        "Generate equipment report"
                    ])
            
            # Quality-based follow-ups
            if validation.quality in [ResponseQuality.FAIR, ResponseQuality.POOR]:
                follow_ups.extend([
                    "Can you provide more details?",
                    "Show me additional sources",
                    "Verify this information"
                ])
            
            return follow_ups[:5]  # Limit to 5 follow-up queries
            
        except Exception as e:
            logger.error(f"Error generating follow-up queries: {e}")
            return []
    
    def _create_fallback_response(
        self, 
        agent_response: AgentResponse, 
        user_role: UserRole, 
        error_message: str
    ) -> EnhancedAgentResponse:
        """Create a fallback enhanced response when enhancement fails."""
        try:
            # Create minimal validation
            validation = ResponseValidation(
                is_valid=False,
                quality=ResponseQuality.INSUFFICIENT,
                confidence=ConfidenceIndicator(
                    level=ConfidenceLevel.VERY_LOW,
                    score=0.0,
                    factors=[f"Enhancement error: {error_message}"]
                ),
                completeness_score=0.0,
                consistency_score=0.0,
                source_attributions=[],
                validation_errors=[error_message],
                warnings=[],
                suggestions=["Please try rephrasing your query"]
            )
            
            # Create minimal enhanced response
            enhanced_response = EnhancedResponse(
                original_response=agent_response.response,
                enhanced_response=agent_response.response,
                validation=validation,
                follow_up_suggestions=[],
                user_role=user_role,
                personalization_applied=False,
                response_metadata={"error": error_message}
            )
            
            return EnhancedAgentResponse(
                original_response=agent_response,
                enhanced_response=enhanced_response,
                user_experience_score=0.0,
                personalization_applied=False,
                follow_up_queries=[],
                response_time_ms=0.0
            )
            
        except Exception as e:
            logger.error(f"Error creating fallback response: {e}")
            # Return minimal response
            return EnhancedAgentResponse(
                original_response=agent_response,
                enhanced_response=EnhancedResponse(
                    original_response=agent_response.response,
                    enhanced_response=agent_response.response,
                    validation=ResponseValidation(
                        is_valid=False,
                        quality=ResponseQuality.INSUFFICIENT,
                        confidence=ConfidenceIndicator(
                            level=ConfidenceLevel.VERY_LOW,
                            score=0.0,
                            factors=["System error"]
                        ),
                        completeness_score=0.0,
                        consistency_score=0.0,
                        source_attributions=[],
                        validation_errors=["System error"],
                        warnings=[],
                        suggestions=[]
                    ),
                    follow_up_suggestions=[],
                    user_role=user_role,
                    personalization_applied=False,
                    response_metadata={}
                ),
                user_experience_score=0.0,
                personalization_applied=False,
                follow_up_queries=[],
                response_time_ms=0.0
            )

# Global response enhancement service instance
_response_enhancer: Optional[ResponseEnhancementService] = None

async def get_response_enhancer() -> ResponseEnhancementService:
    """Get or create the global response enhancement service instance."""
    global _response_enhancer
    if _response_enhancer is None:
        _response_enhancer = ResponseEnhancementService()
    return _response_enhancer
