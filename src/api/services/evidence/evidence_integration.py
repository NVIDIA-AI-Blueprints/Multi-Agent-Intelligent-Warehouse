"""
Evidence Integration Service

This module integrates evidence collection and context synthesis into the
chat system, providing enhanced response quality and source attribution.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import json
from datetime import datetime

from .evidence_collector import (
    get_evidence_collector,
    EvidenceCollector,
    EvidenceContext,
    EvidenceType,
    EvidenceSource,
    EvidenceQuality,
)

logger = logging.getLogger(__name__)


@dataclass
class EnhancedResponse:
    """Enhanced response with evidence and context."""

    response: str
    evidence_summary: Dict[str, Any]
    source_attributions: List[str]
    confidence_score: float
    key_findings: List[Dict[str, Any]]
    recommendations: List[str]
    evidence_count: int
    response_metadata: Dict[str, Any]


class EvidenceIntegrationService:
    """
    Service for integrating evidence collection into chat responses.

    This service provides:
    - Evidence-enhanced response generation
    - Source attribution and traceability
    - Confidence scoring based on evidence
    - Context-aware recommendations
    - Evidence-based response validation
    """

    def __init__(self):
        self.evidence_collector = None
        self.integration_stats = {
            "total_responses": 0,
            "evidence_enhanced_responses": 0,
            "average_evidence_count": 0.0,
            "average_confidence": 0.0,
        }

    async def initialize(self) -> None:
        """Initialize the evidence integration service."""
        try:
            self.evidence_collector = await get_evidence_collector()
            logger.info("Evidence Integration Service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Evidence Integration Service: {e}")
            raise

    async def enhance_response_with_evidence(
        self,
        query: str,
        intent: str,
        entities: Dict[str, Any],
        session_id: str,
        user_context: Optional[Dict[str, Any]] = None,
        system_context: Optional[Dict[str, Any]] = None,
        base_response: Optional[str] = None,
    ) -> EnhancedResponse:
        """
        Enhance a response with evidence collection and context synthesis.

        Args:
            query: User query
            intent: Classified intent
            entities: Extracted entities
            session_id: Session identifier
            user_context: User context data
            system_context: System context data
            base_response: Base response to enhance

        Returns:
            Enhanced response with evidence
        """
        try:
            # Create evidence collection context
            evidence_context = EvidenceContext(
                query=query,
                intent=intent,
                entities=entities,
                session_id=session_id,
                user_context=user_context or {},
                system_context=system_context or {},
                evidence_types=self._determine_evidence_types(intent),
                max_evidence=10,
            )

            # Collect evidence
            evidence_list = await self.evidence_collector.collect_evidence(
                evidence_context
            )

            # Synthesize evidence
            evidence_synthesis = await self.evidence_collector.synthesize_evidence(
                evidence_list, evidence_context
            )

            # Generate enhanced response
            enhanced_response = await self._generate_enhanced_response(
                query, intent, entities, evidence_synthesis, base_response
            )

            # Update statistics
            self._update_integration_stats(evidence_list, enhanced_response)

            logger.info(
                f"Enhanced response with {len(evidence_list)} pieces of evidence"
            )

            return enhanced_response

        except Exception as e:
            logger.error(f"Error enhancing response with evidence: {e}")
            return self._create_fallback_response(query, str(e))

    def _determine_evidence_types(self, intent: str) -> List[EvidenceType]:
        """Determine which evidence types to collect based on intent."""
        evidence_types = []

        intent_lower = intent.lower()

        if "equipment" in intent_lower:
            evidence_types.extend(
                [EvidenceType.EQUIPMENT_DATA, EvidenceType.REAL_TIME_DATA]
            )

        if "operation" in intent_lower or "task" in intent_lower:
            evidence_types.extend(
                [EvidenceType.OPERATIONS_DATA, EvidenceType.REAL_TIME_DATA]
            )

        if "safety" in intent_lower or "incident" in intent_lower:
            evidence_types.extend(
                [EvidenceType.SAFETY_DATA, EvidenceType.HISTORICAL_DATA]
            )

        if "document" in intent_lower:
            evidence_types.append(EvidenceType.DOCUMENT_DATA)

        # Always include user and system context
        evidence_types.extend([EvidenceType.USER_CONTEXT, EvidenceType.SYSTEM_CONTEXT])

        return evidence_types

    async def _generate_enhanced_response(
        self,
        query: str,
        intent: str,
        entities: Dict[str, Any],
        evidence_synthesis: Dict[str, Any],
        base_response: Optional[str],
    ) -> EnhancedResponse:
        """Generate an enhanced response using evidence synthesis."""
        try:
            # Extract key information from evidence synthesis
            evidence_summary = evidence_synthesis.get("evidence_summary", {})
            key_findings = evidence_synthesis.get("key_findings", [])
            source_attributions = evidence_synthesis.get("source_attributions", [])
            recommendations = evidence_synthesis.get("recommendations", [])

            # Calculate overall confidence score
            confidence_score = evidence_summary.get("average_confidence", 0.0)
            high_confidence_count = evidence_summary.get("high_confidence_count", 0)

            # Enhance confidence based on evidence quality
            if high_confidence_count >= 2:
                confidence_score = min(confidence_score + 0.1, 1.0)

            # Generate response text
            if base_response:
                response_text = self._enhance_base_response(
                    base_response, key_findings, source_attributions
                )
            else:
                response_text = await self._generate_response_from_evidence(
                    query, intent, entities, key_findings
                )

            # Create response metadata
            response_metadata = {
                "intent": intent,
                "entities": entities,
                "evidence_types": evidence_summary.get("evidence_by_type", {}),
                "evidence_sources": evidence_summary.get("evidence_by_source", {}),
                "processing_time": datetime.utcnow().isoformat(),
                "enhancement_applied": True,
            }

            return EnhancedResponse(
                response=response_text,
                evidence_summary=evidence_summary,
                source_attributions=source_attributions,
                confidence_score=confidence_score,
                key_findings=key_findings,
                recommendations=recommendations,
                evidence_count=evidence_summary.get("total_evidence", 0),
                response_metadata=response_metadata,
            )

        except Exception as e:
            logger.error(f"Error generating enhanced response: {e}")
            return self._create_fallback_response(query, str(e))

    def _enhance_base_response(
        self,
        base_response: str,
        key_findings: List[Dict[str, Any]],
        source_attributions: List[str],
    ) -> str:
        """Enhance a base response with evidence information."""
        try:
            enhanced_response = base_response

            # Add source attribution if available
            if source_attributions:
                unique_sources = list(set(source_attributions))
                if len(unique_sources) == 1:
                    enhanced_response += f"\n\n*Source: {unique_sources[0]}*"
                else:
                    enhanced_response += f"\n\n*Sources: {', '.join(unique_sources)}*"

            # Add key findings if they provide additional context
            if key_findings and len(key_findings) > 0:
                enhanced_response += "\n\n**Additional Context:**"
                for finding in key_findings[:3]:  # Limit to 3 findings
                    if finding.get("confidence", 0) >= 0.7:
                        enhanced_response += f"\n- {finding.get('content', '')}"

            return enhanced_response

        except Exception as e:
            logger.error(f"Error enhancing base response: {e}")
            return base_response

    async def _generate_response_from_evidence(
        self,
        query: str,
        intent: str,
        entities: Dict[str, Any],
        key_findings: List[Dict[str, Any]],
    ) -> str:
        """Generate a response directly from evidence."""
        try:
            # Create a prompt for LLM-based response generation
            prompt = [
                {
                    "role": "system",
                    "content": """You are a warehouse operations assistant. Generate a comprehensive response based on the provided evidence and context.

Guidelines:
1. Use the evidence to provide accurate, specific information
2. Include relevant details from the findings
3. Be clear about data sources when possible
4. Provide actionable recommendations
5. Maintain a professional, helpful tone

Format your response to be informative and actionable.""",
                },
                {
                    "role": "user",
                    "content": f"""Query: "{query}"
Intent: {intent}
Entities: {json.dumps(entities, indent=2)}

Evidence Findings:
{json.dumps(key_findings, indent=2)}

Generate a comprehensive response based on this evidence.""",
                },
            ]

            # Use LLM to generate response (if available)
            # For now, create a structured response
            response_parts = []

            # Add main response based on findings
            if key_findings:
                response_parts.append("Based on the available evidence:")

                for finding in key_findings[:3]:
                    if finding.get("confidence", 0) >= 0.7:
                        content = finding.get("content", "")
                        if isinstance(content, dict):
                            # Extract key information from structured data
                            if "equipment" in content:
                                equipment_data = content["equipment"]
                                if isinstance(equipment_data, list) and equipment_data:
                                    response_parts.append(
                                        f"- Found {len(equipment_data)} equipment items"
                                    )
                                    for item in equipment_data[:3]:
                                        if isinstance(item, dict):
                                            asset_id = item.get("asset_id", "Unknown")
                                            status = item.get("status", "Unknown")
                                            response_parts.append(
                                                f"  - {asset_id}: {status}"
                                            )
                        else:
                            response_parts.append(f"- {content}")
            else:
                response_parts.append("I found limited evidence for your query.")

            return "\n".join(response_parts)

        except Exception as e:
            logger.error(f"Error generating response from evidence: {e}")
            return f"I encountered an error processing your request: {str(e)}"

    def _create_fallback_response(self, query: str, error: str) -> EnhancedResponse:
        """Create a fallback response when evidence collection fails."""
        return EnhancedResponse(
            response=f"I'm having trouble gathering evidence for your query: {query}. Please try again.",
            evidence_summary={"total_evidence": 0, "error": error},
            source_attributions=[],
            confidence_score=0.0,
            key_findings=[],
            recommendations=[
                "Please try rephrasing your question",
                "Contact support if the issue persists",
            ],
            evidence_count=0,
            response_metadata={"error": error, "fallback": True},
        )

    def _update_integration_stats(
        self, evidence_list: List[Any], enhanced_response: EnhancedResponse
    ) -> None:
        """Update integration statistics."""
        try:
            self.integration_stats["total_responses"] += 1

            if enhanced_response.evidence_count > 0:
                self.integration_stats["evidence_enhanced_responses"] += 1

            # Update average evidence count
            total_evidence = self.integration_stats["average_evidence_count"] * (
                self.integration_stats["total_responses"] - 1
            )
            total_evidence += enhanced_response.evidence_count
            self.integration_stats["average_evidence_count"] = (
                total_evidence / self.integration_stats["total_responses"]
            )

            # Update average confidence
            total_confidence = self.integration_stats["average_confidence"] * (
                self.integration_stats["total_responses"] - 1
            )
            total_confidence += enhanced_response.confidence_score
            self.integration_stats["average_confidence"] = (
                total_confidence / self.integration_stats["total_responses"]
            )

        except Exception as e:
            logger.error(f"Error updating integration stats: {e}")

    def get_integration_stats(self) -> Dict[str, Any]:
        """Get evidence integration statistics."""
        return self.integration_stats.copy()

    async def validate_response_with_evidence(
        self, response: str, evidence_list: List[Any], query: str
    ) -> Dict[str, Any]:
        """Validate a response against collected evidence."""
        try:
            validation_result = {
                "is_valid": True,
                "confidence_score": 0.0,
                "evidence_support": 0.0,
                "warnings": [],
                "recommendations": [],
            }

            if not evidence_list:
                validation_result["warnings"].append(
                    "No evidence available for validation"
                )
                validation_result["is_valid"] = False
                return validation_result

            # Calculate evidence support score
            high_confidence_evidence = [e for e in evidence_list if e.confidence >= 0.8]
            evidence_support = len(high_confidence_evidence) / len(evidence_list)
            validation_result["evidence_support"] = evidence_support

            # Calculate overall confidence
            total_confidence = sum(e.confidence for e in evidence_list)
            average_confidence = total_confidence / len(evidence_list)
            validation_result["confidence_score"] = average_confidence

            # Check for inconsistencies
            if evidence_support < 0.5:
                validation_result["warnings"].append(
                    "Low evidence support for response"
                )
                validation_result["recommendations"].append(
                    "Gather additional evidence"
                )

            if average_confidence < 0.6:
                validation_result["warnings"].append(
                    "Low confidence in evidence quality"
                )
                validation_result["recommendations"].append("Verify evidence sources")

            # Overall validation
            validation_result["is_valid"] = (
                evidence_support >= 0.3
                and average_confidence >= 0.5
                and len(validation_result["warnings"]) <= 2
            )

            return validation_result

        except Exception as e:
            logger.error(f"Error validating response with evidence: {e}")
            return {
                "is_valid": False,
                "confidence_score": 0.0,
                "evidence_support": 0.0,
                "warnings": [f"Validation error: {str(e)}"],
                "recommendations": ["Contact support"],
            }


# Global evidence integration service instance
_evidence_integration_service = None


async def get_evidence_integration_service() -> EvidenceIntegrationService:
    """Get the global evidence integration service instance."""
    global _evidence_integration_service
    if _evidence_integration_service is None:
        _evidence_integration_service = EvidenceIntegrationService()
        await _evidence_integration_service.initialize()
    return _evidence_integration_service
