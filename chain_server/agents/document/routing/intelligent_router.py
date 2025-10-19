"""
Stage 6: Intelligent Routing based on Quality Scores
Quality-based routing system for document processing decisions.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass

from chain_server.agents.document.models.document_models import (
    RoutingAction,
    QualityDecision,
)

logger = logging.getLogger(__name__)


@dataclass
class RoutingDecision:
    """Represents a routing decision."""

    action: RoutingAction
    reason: str
    confidence: float
    next_steps: List[str]
    estimated_processing_time: Optional[str] = None
    requires_human_review: bool = False
    priority: str = "normal"


class IntelligentRouter:
    """
    Stage 6: Intelligent Routing based on quality scores.

    Routing Logic:
    - Score ≥ 4.5 (Excellent): Auto-approve & integrate to WMS
    - Score 3.5-4.4 (Good with minor issues): Flag for quick human review
    - Score 2.5-3.4 (Needs attention): Queue for expert review
    - Score < 2.5 (Poor quality): Re-scan or request better image
    """

    def __init__(self):
        self.routing_thresholds = {
            "excellent": 4.5,
            "good": 3.5,
            "needs_attention": 2.5,
            "poor": 0.0,
        }

        self.routing_actions = {
            "excellent": RoutingAction.AUTO_APPROVE,
            "good": RoutingAction.FLAG_REVIEW,
            "needs_attention": RoutingAction.EXPERT_REVIEW,
            "poor": RoutingAction.REJECT,
        }

    async def initialize(self):
        """Initialize the intelligent router."""
        logger.info("Intelligent Router initialized successfully")

    async def route_document(
        self, llm_result: Any, judge_result: Any, document_type: str
    ) -> RoutingDecision:
        """
        Route document based on LLM result and judge evaluation.

        Args:
            llm_result: Result from Small LLM processing
            judge_result: Result from Large LLM Judge
            document_type: Type of document

        Returns:
            Routing decision with action and reasoning
        """
        try:
            logger.info(
                f"Routing {document_type} document based on LLM and judge results"
            )

            # Get overall quality score from judge result
            overall_score = self._get_value(judge_result, "overall_score", 0.0)
            judge_decision = self._get_value(
                judge_result, "decision", "REVIEW_REQUIRED"
            )

            # Determine quality level
            quality_level = self._determine_quality_level(overall_score)

            # Make routing decision
            routing_decision = await self._make_routing_decision(
                overall_score,
                quality_level,
                judge_decision,
                llm_result,
                judge_result,
                document_type,
            )

            logger.info(
                f"Routing decision: {routing_decision.action.value} (Score: {overall_score:.2f})"
            )
            return routing_decision

        except Exception as e:
            logger.error(f"Document routing failed: {e}")
            raise

    def _get_value(self, obj, key: str, default=None):
        """Get value from object (dict or object with attributes)."""
        if hasattr(obj, key):
            return getattr(obj, key)
        elif hasattr(obj, "get"):
            return obj.get(key, default)
        else:
            return default

    def _get_dict_value(self, obj, key: str, default=None):
        """Get value from object treating it as a dictionary."""
        if hasattr(obj, "get"):
            return obj.get(key, default)
        elif hasattr(obj, key):
            return getattr(obj, key)
        else:
            return default

    def _determine_quality_level(self, overall_score: float) -> str:
        """Determine quality level based on overall score."""
        if overall_score >= self.routing_thresholds["excellent"]:
            return "excellent"
        elif overall_score >= self.routing_thresholds["good"]:
            return "good"
        elif overall_score >= self.routing_thresholds["needs_attention"]:
            return "needs_attention"
        else:
            return "poor"

    async def _make_routing_decision(
        self,
        overall_score: float,
        quality_level: str,
        judge_decision: str,
        llm_result: Any,
        judge_result: Any,
        document_type: str,
    ) -> RoutingDecision:
        """Make the actual routing decision."""

        if quality_level == "excellent":
            return await self._route_excellent_quality(
                overall_score, llm_result, judge_result, document_type
            )
        elif quality_level == "good":
            return await self._route_good_quality(
                overall_score, llm_result, judge_result, document_type
            )
        elif quality_level == "needs_attention":
            return await self._route_needs_attention(
                overall_score, llm_result, judge_result, document_type
            )
        else:  # poor
            return await self._route_poor_quality(
                overall_score, llm_result, judge_result, document_type
            )

    async def _route_excellent_quality(
        self,
        overall_score: float,
        llm_result: Any,
        judge_result: Any,
        document_type: str,
    ) -> RoutingDecision:
        """Route excellent quality documents."""

        # Check if judge also approves
        judge_decision = self._get_value(judge_result, "decision", "REVIEW_REQUIRED")

        if judge_decision == "APPROVE":
            return RoutingDecision(
                action=RoutingAction.AUTO_APPROVE,
                reason=f"Excellent quality document (Score: {overall_score:.2f}) with judge approval",
                confidence=0.95,
                next_steps=[
                    "Auto-approve document",
                    "Integrate data to WMS system",
                    "Notify stakeholders of successful processing",
                    "Archive document for future reference",
                ],
                estimated_processing_time="Immediate",
                requires_human_review=False,
                priority="high",
            )
        else:
            # Even with excellent quality, if judge doesn't approve, send for review
            return RoutingDecision(
                action=RoutingAction.FLAG_REVIEW,
                reason=f"Excellent quality document (Score: {overall_score:.2f}) but judge requires review",
                confidence=0.85,
                next_steps=[
                    "Send to expert reviewer",
                    "Provide judge analysis to reviewer",
                    "Highlight specific areas of concern",
                    "Expedite review process",
                ],
                estimated_processing_time="2-4 hours",
                requires_human_review=True,
                priority="high",
            )

    async def _route_good_quality(
        self,
        overall_score: float,
        llm_result: Any,
        judge_result: Any,
        document_type: str,
    ) -> RoutingDecision:
        """Route good quality documents with minor issues."""

        # Identify specific issues
        issues = self._identify_specific_issues(llm_result, judge_result)

        return RoutingDecision(
            action=RoutingAction.FLAG_REVIEW,
            reason=f"Good quality document (Score: {overall_score:.2f}) with minor issues requiring review",
            confidence=0.80,
            next_steps=[
                "Flag specific fields for quick human review",
                "Show judge's reasoning and suggested fixes",
                "Provide semi-automated correction options",
                "Monitor review progress",
            ],
            estimated_processing_time="1-2 hours",
            requires_human_review=True,
            priority="normal",
        )

    async def _route_needs_attention(
        self,
        overall_score: float,
        llm_result: Any,
        judge_result: Any,
        document_type: str,
    ) -> RoutingDecision:
        """Route documents that need attention."""

        # Identify major issues
        issues = self._identify_specific_issues(llm_result, judge_result)

        return RoutingDecision(
            action=RoutingAction.EXPERT_REVIEW,
            reason=f"Document needs attention (Score: {overall_score:.2f}) - multiple issues identified",
            confidence=0.70,
            next_steps=[
                "Queue for expert review",
                "Provide comprehensive judge analysis to reviewer",
                "Use as training data for model improvement",
                "Consider alternative processing strategies",
            ],
            estimated_processing_time="4-8 hours",
            requires_human_review=True,
            priority="normal",
        )

    async def _route_poor_quality(
        self,
        overall_score: float,
        llm_result: Any,
        judge_result: Any,
        document_type: str,
    ) -> RoutingDecision:
        """Route poor quality documents."""

        # Identify critical issues
        issues = self._identify_specific_issues(llm_result, judge_result)

        return RoutingDecision(
            action=RoutingAction.REJECT,
            reason=f"Poor quality document (Score: {overall_score:.2f}) - critical issues require specialist attention",
            confidence=0.60,
            next_steps=[
                "Escalate to specialist team",
                "Consider re-scanning document",
                "Request better quality image",
                "Implement alternative processing strategy",
                "Document issues for system improvement",
            ],
            estimated_processing_time="8-24 hours",
            requires_human_review=True,
            priority="low",
        )

    def _identify_specific_issues(
        self, llm_result: Any, judge_result: Any
    ) -> List[str]:
        """Identify specific issues from quality scores and judge result."""
        issues = []

        # Check individual quality scores
        if self._get_value(llm_result, "completeness_score", 5.0) < 4.0:
            issues.append("Incomplete data extraction")

        if self._get_value(llm_result, "accuracy_score", 5.0) < 4.0:
            issues.append("Accuracy concerns")

        if self._get_value(llm_result, "consistency_score", 5.0) < 4.0:
            issues.append("Data consistency issues")

        if self._get_value(llm_result, "readability_score", 5.0) < 4.0:
            issues.append("Readability problems")

        # Check judge issues
        judge_issues = self._get_value(judge_result, "issues_found", [])
        issues.extend(judge_issues)

        # Check completeness issues
        completeness = self._get_value(judge_result, "completeness", {})
        if self._get_value(completeness, "missing_fields"):
            issues.append(
                f"Missing fields: {', '.join(completeness['missing_fields'])}"
            )

        # Check accuracy issues
        accuracy = self._get_value(judge_result, "accuracy", {})
        if self._get_value(accuracy, "calculation_errors"):
            issues.append(
                f"Calculation errors: {', '.join(accuracy['calculation_errors'])}"
            )

        # Check compliance issues
        compliance = self._get_value(judge_result, "compliance", {})
        if self._get_value(compliance, "compliance_issues"):
            issues.append(
                f"Compliance issues: {', '.join(compliance['compliance_issues'])}"
            )

        return issues

    async def get_routing_statistics(self) -> Dict[str, Any]:
        """Get routing statistics for monitoring."""
        return {
            "routing_thresholds": self.routing_thresholds,
            "routing_actions": {k: v.value for k, v in self.routing_actions.items()},
            "last_updated": datetime.now().isoformat(),
        }

    async def update_routing_thresholds(self, new_thresholds: Dict[str, float]) -> bool:
        """Update routing thresholds based on performance data."""
        try:
            # Validate thresholds
            if not self._validate_thresholds(new_thresholds):
                return False

            # Update thresholds
            self.routing_thresholds.update(new_thresholds)

            logger.info(f"Updated routing thresholds: {new_thresholds}")
            return True

        except Exception as e:
            logger.error(f"Failed to update routing thresholds: {e}")
            return False

    def _validate_thresholds(self, thresholds: Dict[str, float]) -> bool:
        """Validate that thresholds are in correct order."""
        try:
            values = [
                thresholds.get(key, 0.0)
                for key in ["excellent", "good", "needs_attention", "poor"]
            ]

            # Check descending order
            for i in range(len(values) - 1):
                if values[i] < values[i + 1]:
                    return False

            # Check valid range
            for value in values:
                if not (0.0 <= value <= 5.0):
                    return False

            return True

        except Exception:
            return False

    async def get_routing_recommendations(
        self, llm_result: Dict[str, float], document_type: str
    ) -> List[str]:
        """Get routing recommendations based on quality scores."""
        recommendations = []

        overall_score = self._get_value(llm_result, "overall_score", 0.0)

        if overall_score >= 4.5:
            recommendations.append("Document is ready for automatic processing")
            recommendations.append("Consider implementing auto-approval workflow")
        elif overall_score >= 3.5:
            recommendations.append("Document requires minor review before processing")
            recommendations.append(
                "Implement quick review workflow for similar documents"
            )
        elif overall_score >= 2.5:
            recommendations.append("Document needs comprehensive review")
            recommendations.append(
                "Consider improving OCR quality for similar documents"
            )
        else:
            recommendations.append("Document requires specialist attention")
            recommendations.append(
                "Consider re-scanning or alternative processing methods"
            )

        # Add specific recommendations based on individual scores
        if self._get_value(llm_result, "completeness_score", 5.0) < 4.0:
            recommendations.append("Improve field extraction completeness")

        if self._get_value(llm_result, "accuracy_score", 5.0) < 4.0:
            recommendations.append("Enhance data validation and accuracy checks")

        if self._get_value(llm_result, "consistency_score", 5.0) < 4.0:
            recommendations.append("Implement consistency validation rules")

        if self._get_value(llm_result, "readability_score", 5.0) < 4.0:
            recommendations.append("Improve document quality and OCR preprocessing")

        return recommendations
