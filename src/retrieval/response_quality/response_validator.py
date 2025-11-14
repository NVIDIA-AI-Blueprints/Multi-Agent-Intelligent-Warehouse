"""
Response Quality Control System for Warehouse Operational Assistant

Provides comprehensive response validation, quality assessment, and user experience
enhancements including confidence indicators, source attribution, and consistency checks.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
import re
import json

logger = logging.getLogger(__name__)

class ConfidenceLevel(Enum):
    """Confidence levels for responses."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    VERY_LOW = "very_low"

class ResponseQuality(Enum):
    """Response quality levels."""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    INSUFFICIENT = "insufficient"

class UserRole(Enum):
    """User roles for personalization."""
    OPERATOR = "operator"
    SUPERVISOR = "supervisor"
    MANAGER = "manager"
    ADMIN = "admin"
    GUEST = "guest"

@dataclass
class SourceAttribution:
    """Source attribution information."""
    source_type: str  # "database", "vector_search", "knowledge_base", "api"
    source_name: str  # "PostgreSQL", "Milvus", "SAP EWM", etc.
    source_id: Optional[str] = None
    confidence: float = 0.0
    timestamp: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class ConfidenceIndicator:
    """Confidence indicator for responses."""
    level: ConfidenceLevel
    score: float  # 0.0 to 1.0
    factors: List[str]  # Reasons for confidence level
    evidence_quality: float = 0.0
    source_reliability: float = 0.0
    data_freshness: float = 0.0

@dataclass
class ResponseValidation:
    """Response validation results."""
    is_valid: bool
    quality: ResponseQuality
    confidence: ConfidenceIndicator
    completeness_score: float  # 0.0 to 1.0
    consistency_score: float  # 0.0 to 1.0
    source_attributions: List[SourceAttribution]
    validation_errors: List[str]
    warnings: List[str]
    suggestions: List[str]

@dataclass
class EnhancedResponse:
    """Enhanced response with quality control information."""
    original_response: str
    enhanced_response: str
    validation: ResponseValidation
    follow_up_suggestions: List[str]
    user_role: UserRole
    personalization_applied: bool
    response_metadata: Dict[str, Any]

class ResponseValidator:
    """
    Comprehensive response validation and quality control system.
    
    Features:
    - Evidence quality validation
    - Source attribution tracking
    - Confidence level assessment
    - Response consistency checks
    - Completeness validation
    - User experience enhancements
    """
    
    def __init__(self):
        self.quality_thresholds = {
            "excellent": 0.9,
            "good": 0.7,
            "fair": 0.5,
            "poor": 0.3,
            "insufficient": 0.0
        }
        
        self.confidence_thresholds = {
            "high": 0.8,
            "medium": 0.6,
            "low": 0.4,
            "very_low": 0.0
        }
        
        self.source_reliability_scores = {
            "database": 0.95,
            "vector_search": 0.85,
            "knowledge_base": 0.80,
            "api": 0.75,
            "user_input": 0.60,
            "estimated": 0.40
        }
    
    def validate_response(
        self,
        response: str,
        evidence_data: Optional[Dict[str, Any]] = None,
        query_context: Optional[Dict[str, Any]] = None,
        user_role: UserRole = UserRole.OPERATOR
    ) -> ResponseValidation:
        """
        Validate response quality and generate comprehensive validation results.
        
        Args:
            response: The response text to validate
            evidence_data: Evidence data used to generate the response
            query_context: Context about the original query
            user_role: User role for personalization
            
        Returns:
            ResponseValidation with comprehensive quality assessment
        """
        try:
            # Initialize validation results
            validation_errors = []
            warnings = []
            suggestions = []
            
            # 1. Evidence Quality Validation
            evidence_quality = self._assess_evidence_quality(evidence_data)
            
            # 2. Source Attribution Analysis
            source_attributions = self._extract_source_attributions(evidence_data, query_context)
            
            # 3. Confidence Assessment
            confidence = self._assess_confidence(response, evidence_quality, source_attributions)
            
            # 4. Completeness Validation
            completeness_score = self._validate_completeness(response, query_context)
            
            # 5. Consistency Checks
            consistency_score = self._validate_consistency(response, evidence_data)
            
            # 6. Quality Assessment
            overall_quality = self._calculate_overall_quality(
                evidence_quality, completeness_score, consistency_score, confidence.score
            )
            
            # 7. Generate validation errors and warnings
            overall_score = (
                evidence_quality * 0.3 +
                completeness_score * 0.25 +
                consistency_score * 0.25 +
                confidence.score * 0.2
            )
            
            if overall_score < self.quality_thresholds["good"]:
                validation_errors.append("Response quality below acceptable threshold")
            
            if confidence.score < self.confidence_thresholds["medium"]:
                warnings.append("Low confidence in response accuracy")
            
            if completeness_score < 0.7:
                warnings.append("Response may be incomplete")
            
            if not source_attributions:
                warnings.append("No source attribution available")
            
            # 8. Generate suggestions
            suggestions = self._generate_improvement_suggestions(
                response, evidence_quality, completeness_score, consistency_score, confidence
            )
            
            return ResponseValidation(
                is_valid=len(validation_errors) == 0,
                quality=overall_quality,
                confidence=confidence,
                completeness_score=completeness_score,
                consistency_score=consistency_score,
                source_attributions=source_attributions,
                validation_errors=validation_errors,
                warnings=warnings,
                suggestions=suggestions
            )
            
        except Exception as e:
            logger.error(f"Error validating response: {e}")
            return ResponseValidation(
                is_valid=False,
                quality=ResponseQuality.INSUFFICIENT,
                confidence=ConfidenceIndicator(
                    level=ConfidenceLevel.VERY_LOW,
                    score=0.0,
                    factors=["Validation error occurred"]
                ),
                completeness_score=0.0,
                consistency_score=0.0,
                source_attributions=[],
                validation_errors=[f"Validation error: {str(e)}"],
                warnings=[],
                suggestions=["Please try rephrasing your query"]
            )
    
    def enhance_response(
        self,
        response: str,
        validation: ResponseValidation,
        user_role: UserRole = UserRole.OPERATOR,
        query_context: Optional[Dict[str, Any]] = None
    ) -> EnhancedResponse:
        """
        Enhance response with quality control information and user experience improvements.
        
        Args:
            response: Original response text
            validation: Response validation results
            user_role: User role for personalization
            query_context: Original query context
            
        Returns:
            Enhanced response with quality indicators and improvements
        """
        try:
            # 1. Add confidence indicators
            enhanced_response = self._add_confidence_indicators(response, validation.confidence)
            
            # 2. Add source attributions
            enhanced_response = self._add_source_attributions(enhanced_response, validation.source_attributions)
            
            # 3. Add quality indicators
            enhanced_response = self._add_quality_indicators(enhanced_response, validation.quality)
            
            # 4. Add warnings if necessary
            if validation.warnings:
                enhanced_response = self._add_warnings(enhanced_response, validation.warnings)
            
            # 5. Personalize based on user role
            enhanced_response = self._personalize_response(enhanced_response, user_role, query_context)
            
            # 6. Generate follow-up suggestions
            follow_up_suggestions = self._generate_follow_up_suggestions(
                response, query_context, user_role, validation
            )
            
            # 7. Add response explanations for complex queries
            if validation.confidence.score < 0.7 or validation.quality in [ResponseQuality.FAIR, ResponseQuality.POOR]:
                enhanced_response = self._add_response_explanation(enhanced_response, validation, query_context)
            
            return EnhancedResponse(
                original_response=response,
                enhanced_response=enhanced_response,
                validation=validation,
                follow_up_suggestions=follow_up_suggestions,
                user_role=user_role,
                personalization_applied=True,
                response_metadata={
                    "enhancement_timestamp": datetime.now().isoformat(),
                    "quality_score": validation.quality.value,
                    "confidence_score": validation.confidence.score,
                    "completeness_score": validation.completeness_score,
                    "consistency_score": validation.consistency_score
                }
            )
            
        except Exception as e:
            logger.error(f"Error enhancing response: {e}")
            return EnhancedResponse(
                original_response=response,
                enhanced_response=response,
                validation=validation,
                follow_up_suggestions=[],
                user_role=user_role,
                personalization_applied=False,
                response_metadata={"error": str(e)}
            )
    
    def _assess_evidence_quality(self, evidence_data: Optional[Dict[str, Any]]) -> float:
        """Assess the quality of evidence data."""
        if not evidence_data:
            return 0.0
        
        try:
            quality_factors = []
            
            # Check for evidence score
            if "evidence_score" in evidence_data:
                evidence_score = evidence_data["evidence_score"]
                if isinstance(evidence_score, dict):
                    quality_factors.append(evidence_score.get("overall_score", 0.0))
                else:
                    quality_factors.append(float(evidence_score))
            
            # Check for source diversity
            if "sources" in evidence_data:
                sources = evidence_data["sources"]
                if isinstance(sources, list) and len(sources) > 1:
                    quality_factors.append(0.8)  # Multiple sources
                elif len(sources) == 1:
                    quality_factors.append(0.6)  # Single source
                else:
                    quality_factors.append(0.2)  # No sources
            
            # Check for data freshness
            if "timestamp" in evidence_data:
                # Simple freshness check (would be more sophisticated in production)
                quality_factors.append(0.9)  # Recent data
            
            # Check for completeness
            if "completeness" in evidence_data:
                quality_factors.append(evidence_data["completeness"])
            
            return sum(quality_factors) / len(quality_factors) if quality_factors else 0.0
            
        except Exception as e:
            logger.error(f"Error assessing evidence quality: {e}")
            return 0.0
    
    def _extract_source_attributions(
        self, 
        evidence_data: Optional[Dict[str, Any]], 
        query_context: Optional[Dict[str, Any]]
    ) -> List[SourceAttribution]:
        """Extract source attribution information."""
        attributions = []
        
        try:
            if not evidence_data:
                return attributions
            
            # Extract from evidence data
            if "sources" in evidence_data:
                for source in evidence_data["sources"]:
                    attribution = SourceAttribution(
                        source_type=source.get("type", "unknown"),
                        source_name=source.get("name", "Unknown Source"),
                        source_id=source.get("id"),
                        confidence=source.get("confidence", 0.0),
                        timestamp=datetime.now(),
                        metadata=source.get("metadata", {})
                    )
                    attributions.append(attribution)
            
            # Extract from query context
            if query_context and "route" in query_context:
                route = query_context["route"]
                if route == "sql":
                    attributions.append(SourceAttribution(
                        source_type="database",
                        source_name="PostgreSQL/TimescaleDB",
                        confidence=0.95,
                        timestamp=datetime.now()
                    ))
                elif route == "vector":
                    attributions.append(SourceAttribution(
                        source_type="vector_search",
                        source_name="Milvus Vector Database",
                        confidence=0.85,
                        timestamp=datetime.now()
                    ))
            
            return attributions
            
        except Exception as e:
            logger.error(f"Error extracting source attributions: {e}")
            return attributions
    
    def _assess_confidence(
        self, 
        response: str, 
        evidence_quality: float, 
        source_attributions: List[SourceAttribution]
    ) -> ConfidenceIndicator:
        """Assess confidence level for the response."""
        try:
            factors = []
            confidence_score = 0.0
            
            # Evidence quality factor
            evidence_factor = evidence_quality
            confidence_score += evidence_factor * 0.4
            factors.append(f"Evidence quality: {evidence_factor:.2f}")
            
            # Source reliability factor
            if source_attributions:
                source_scores = [
                    self.source_reliability_scores.get(attr.source_type, 0.5) 
                    for attr in source_attributions
                ]
                source_factor = sum(source_scores) / len(source_scores)
                confidence_score += source_factor * 0.3
                factors.append(f"Source reliability: {source_factor:.2f}")
            else:
                factors.append("No source attribution")
            
            # Response completeness factor
            completeness_factor = min(1.0, len(response.split()) / 20)  # Simple word count heuristic
            confidence_score += completeness_factor * 0.2
            factors.append(f"Response completeness: {completeness_factor:.2f}")
            
            # Data freshness factor
            freshness_factor = 0.8  # Assume recent data
            confidence_score += freshness_factor * 0.1
            factors.append(f"Data freshness: {freshness_factor:.2f}")
            
            # Determine confidence level
            if confidence_score >= self.confidence_thresholds["high"]:
                level = ConfidenceLevel.HIGH
            elif confidence_score >= self.confidence_thresholds["medium"]:
                level = ConfidenceLevel.MEDIUM
            elif confidence_score >= self.confidence_thresholds["low"]:
                level = ConfidenceLevel.LOW
            else:
                level = ConfidenceLevel.VERY_LOW
            
            return ConfidenceIndicator(
                level=level,
                score=confidence_score,
                factors=factors,
                evidence_quality=evidence_quality,
                source_reliability=source_factor if source_attributions else 0.0,
                data_freshness=freshness_factor
            )
            
        except Exception as e:
            logger.error(f"Error assessing confidence: {e}")
            return ConfidenceIndicator(
                level=ConfidenceLevel.VERY_LOW,
                score=0.0,
                factors=[f"Assessment error: {str(e)}"]
            )
    
    def _validate_completeness(self, response: str, query_context: Optional[Dict[str, Any]]) -> float:
        """Validate response completeness."""
        try:
            if not response or len(response.strip()) < 10:
                return 0.0
            
            completeness_factors = []
            
            # Length factor
            word_count = len(response.split())
            if word_count >= 50:
                completeness_factors.append(1.0)
            elif word_count >= 20:
                completeness_factors.append(0.7)
            elif word_count >= 10:
                completeness_factors.append(0.4)
            else:
                completeness_factors.append(0.1)
            
            # Content structure factor
            has_numbers = bool(re.search(r'\d+', response))
            has_specifics = bool(re.search(r'(SKU|ID|count|total|status)', response, re.IGNORECASE))
            
            if has_numbers and has_specifics:
                completeness_factors.append(1.0)
            elif has_numbers or has_specifics:
                completeness_factors.append(0.6)
            else:
                completeness_factors.append(0.3)
            
            # Query context matching
            if query_context and "intent" in query_context:
                intent = query_context["intent"]
                if intent in ["workforce", "task_management"] and "workers" in response.lower():
                    completeness_factors.append(1.0)
                elif intent in ["equipment_lookup", "atp_lookup"] and any(word in response.lower() for word in ["sku", "quantity", "available"]):
                    completeness_factors.append(1.0)
                else:
                    completeness_factors.append(0.5)
            
            return sum(completeness_factors) / len(completeness_factors)
            
        except Exception as e:
            logger.error(f"Error validating completeness: {e}")
            return 0.0
    
    def _validate_consistency(self, response: str, evidence_data: Optional[Dict[str, Any]]) -> float:
        """Validate response consistency with evidence."""
        try:
            if not evidence_data:
                return 0.5  # Neutral score when no evidence available
            
            consistency_factors = []
            
            # Check for numerical consistency
            if "data" in evidence_data and isinstance(evidence_data["data"], dict):
                data = evidence_data["data"]
                
                # Extract numbers from response
                response_numbers = re.findall(r'\d+', response)
                
                # Check if numbers in response match evidence
                if "total_workers" in data and str(data["total_workers"]) in response_numbers:
                    consistency_factors.append(1.0)
                elif "quantity" in data and str(data["quantity"]) in response_numbers:
                    consistency_factors.append(1.0)
                else:
                    consistency_factors.append(0.7)  # Partial match
            
            # Check for status consistency
            if "status" in evidence_data:
                status = evidence_data["status"]
                if status.lower() in response.lower():
                    consistency_factors.append(1.0)
                else:
                    consistency_factors.append(0.5)
            
            return sum(consistency_factors) / len(consistency_factors) if consistency_factors else 0.5
            
        except Exception as e:
            logger.error(f"Error validating consistency: {e}")
            return 0.5
    
    def _calculate_overall_quality(
        self, 
        evidence_quality: float, 
        completeness_score: float, 
        consistency_score: float, 
        confidence_score: float
    ) -> ResponseQuality:
        """Calculate overall response quality."""
        try:
            overall_score = (
                evidence_quality * 0.3 +
                completeness_score * 0.25 +
                consistency_score * 0.25 +
                confidence_score * 0.2
            )
            
            if overall_score >= self.quality_thresholds["excellent"]:
                return ResponseQuality.EXCELLENT
            elif overall_score >= self.quality_thresholds["good"]:
                return ResponseQuality.GOOD
            elif overall_score >= self.quality_thresholds["fair"]:
                return ResponseQuality.FAIR
            elif overall_score >= self.quality_thresholds["poor"]:
                return ResponseQuality.POOR
            else:
                return ResponseQuality.INSUFFICIENT
                
        except Exception as e:
            logger.error(f"Error calculating overall quality: {e}")
            return ResponseQuality.INSUFFICIENT
    
    def _generate_improvement_suggestions(
        self,
        response: str,
        evidence_quality: float,
        completeness_score: float,
        consistency_score: float,
        confidence: ConfidenceIndicator
    ) -> List[str]:
        """Generate suggestions for response improvement."""
        suggestions = []
        
        try:
            if evidence_quality < 0.7:
                suggestions.append("Consider providing more specific evidence or data sources")
            
            if completeness_score < 0.7:
                suggestions.append("Add more details to make the response more comprehensive")
            
            if consistency_score < 0.7:
                suggestions.append("Verify data consistency with source information")
            
            if confidence.score < 0.6:
                suggestions.append("Consider adding confidence qualifiers or seeking additional verification")
            
            if not suggestions:
                suggestions.append("Response quality is good - no specific improvements needed")
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Error generating suggestions: {e}")
            return ["Unable to generate improvement suggestions"]
    
    def _add_confidence_indicators(self, response: str, confidence: ConfidenceIndicator) -> str:
        """Add confidence indicators to response."""
        try:
            confidence_emoji = {
                ConfidenceLevel.HIGH: "🟢",
                ConfidenceLevel.MEDIUM: "🟡", 
                ConfidenceLevel.LOW: "🟠",
                ConfidenceLevel.VERY_LOW: "🔴"
            }
            
            emoji = confidence_emoji.get(confidence.level, "⚪")
            confidence_text = f"{emoji} **Confidence: {confidence.level.value.upper()}** ({confidence.score:.1%})"
            
            return f"{response}\n\n---\n{confidence_text}"
            
        except Exception as e:
            logger.error(f"Error adding confidence indicators: {e}")
            return response
    
    def _add_source_attributions(self, response: str, attributions: List[SourceAttribution]) -> str:
        """Add source attributions to response."""
        try:
            if not attributions:
                return response
            
            attribution_text = "\n\n**Sources:**\n"
            for attr in attributions:
                attribution_text += f"• {attr.source_name} ({attr.source_type})"
                if attr.confidence > 0:
                    attribution_text += f" - {attr.confidence:.1%} confidence"
                attribution_text += "\n"
            
            return response + attribution_text
            
        except Exception as e:
            logger.error(f"Error adding source attributions: {e}")
            return response
    
    def _add_quality_indicators(self, response: str, quality: ResponseQuality) -> str:
        """Add quality indicators to response."""
        try:
            quality_emoji = {
                ResponseQuality.EXCELLENT: "⭐",
                ResponseQuality.GOOD: "✅",
                ResponseQuality.FAIR: "⚠️",
                ResponseQuality.POOR: "❌",
                ResponseQuality.INSUFFICIENT: "🚫"
            }
            
            emoji = quality_emoji.get(quality, "❓")
            quality_text = f"\n{emoji} **Quality: {quality.value.upper()}**"
            
            return response + quality_text
            
        except Exception as e:
            logger.error(f"Error adding quality indicators: {e}")
            return response
    
    def _add_warnings(self, response: str, warnings: List[str]) -> str:
        """Add warnings to response."""
        try:
            if not warnings:
                return response
            
            warning_text = "\n\n**⚠️ Warnings:**\n"
            for warning in warnings:
                warning_text += f"• {warning}\n"
            
            return response + warning_text
            
        except Exception as e:
            logger.error(f"Error adding warnings: {e}")
            return response
    
    def _personalize_response(
        self, 
        response: str, 
        user_role: UserRole, 
        query_context: Optional[Dict[str, Any]]
    ) -> str:
        """Personalize response based on user role."""
        try:
            if user_role == UserRole.OPERATOR:
                # Add operational context
                if "workers" in response.lower():
                    response += "\n\n💡 **For Operators:** Focus on immediate task completion and safety protocols."
                elif "equipment" in response.lower():
                    response += "\n\n💡 **For Operators:** Check equipment status before use and report any issues."
            
            elif user_role == UserRole.SUPERVISOR:
                # Add supervisory context
                if "workers" in response.lower():
                    response += "\n\n📊 **For Supervisors:** Monitor team performance and ensure workload balance."
                elif "tasks" in response.lower():
                    response += "\n\n📊 **For Supervisors:** Review task priorities and resource allocation."
            
            elif user_role == UserRole.MANAGER:
                # Add management context
                if "performance" in response.lower() or "metrics" in response.lower():
                    response += "\n\n📈 **For Managers:** Use this data for strategic planning and resource optimization."
            
            return response
            
        except Exception as e:
            logger.error(f"Error personalizing response: {e}")
            return response
    
    def _generate_follow_up_suggestions(
        self,
        response: str,
        query_context: Optional[Dict[str, Any]],
        user_role: UserRole,
        validation: ResponseValidation
    ) -> List[str]:
        """Generate follow-up suggestions for related queries."""
        try:
            suggestions = []
            
            # Role-based suggestions
            if user_role == UserRole.OPERATOR:
                if "workers" in response.lower():
                    suggestions.extend([
                        "Show me my current tasks",
                        "What equipment do I need for today's work?",
                        "Are there any safety alerts I should know about?"
                    ])
                elif "equipment" in response.lower():
                    suggestions.extend([
                        "Show me equipment maintenance schedule",
                        "What's the status of all forklifts?",
                        "Are there any equipment issues to report?"
                    ])
            
            elif user_role == UserRole.SUPERVISOR:
                if "workers" in response.lower():
                    suggestions.extend([
                        "Show me team performance metrics",
                        "What tasks need reassignment?",
                        "Are there any scheduling conflicts?"
                    ])
                elif "tasks" in response.lower():
                    suggestions.extend([
                        "Show me task completion rates",
                        "What are the priority tasks for today?",
                        "How can I optimize the workflow?"
                    ])
            
            # General suggestions based on response content
            if "SKU" in response or "inventory" in response.lower():
                suggestions.extend([
                    "Show me inventory levels for all items",
                    "What items need restocking?",
                    "Are there any inventory discrepancies?"
                ])
            
            if "safety" in response.lower() or "incident" in response.lower():
                suggestions.extend([
                    "Show me recent safety incidents",
                    "What safety protocols should I follow?",
                    "Are there any safety training requirements?"
                ])
            
            return suggestions[:5]  # Limit to 5 suggestions
            
        except Exception as e:
            logger.error(f"Error generating follow-up suggestions: {e}")
            return []
    
    def _add_response_explanation(
        self, 
        response: str, 
        validation: ResponseValidation, 
        query_context: Optional[Dict[str, Any]]
    ) -> str:
        """Add explanation for complex or low-confidence responses."""
        try:
            explanation = "\n\n**📝 Explanation:**\n"
            
            if validation.confidence.score < 0.7:
                explanation += "This response is based on available data, but confidence is moderate. "
            
            if validation.quality in [ResponseQuality.FAIR, ResponseQuality.POOR]:
                explanation += "The response quality may be limited due to data availability. "
            
            if validation.source_attributions:
                explanation += f"Data sources include: {', '.join([attr.source_name for attr in validation.source_attributions])}. "
            
            explanation += "For critical decisions, please verify with additional sources or consult with a supervisor."
            
            return response + explanation
            
        except Exception as e:
            logger.error(f"Error adding response explanation: {e}")
            return response

# Global response validator instance
_response_validator: Optional[ResponseValidator] = None

def get_response_validator() -> ResponseValidator:
    """Get or create the global response validator instance."""
    global _response_validator
    if _response_validator is None:
        _response_validator = ResponseValidator()
    return _response_validator
