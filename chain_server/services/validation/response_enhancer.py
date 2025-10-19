"""
Response Enhancement Service

Enhances responses based on validation results and applies
automatic improvements to ensure high-quality output.
"""

import logging
import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from .response_validator import (
    get_response_validator,
    ResponseValidator,
    ValidationResult,
    ValidationIssue,
    ValidationCategory,
    ValidationLevel,
)

logger = logging.getLogger(__name__)


@dataclass
class EnhancementResult:
    """Result of response enhancement."""

    original_response: str
    enhanced_response: str
    validation_result: ValidationResult
    improvements_applied: List[str]
    enhancement_score: float
    is_enhanced: bool


class ResponseEnhancer:
    """Service for enhancing responses based on validation."""

    def __init__(self):
        self.validator: Optional[ResponseValidator] = None

    async def initialize(self):
        """Initialize the response enhancer."""
        self.validator = await get_response_validator()
        logger.info("Response enhancer initialized")

    async def enhance_response(
        self,
        response: str,
        context: Dict[str, Any] = None,
        intent: str = None,
        entities: Dict[str, Any] = None,
        auto_fix: bool = True,
    ) -> EnhancementResult:
        """
        Enhance a response based on validation results.

        Args:
            response: The response to enhance
            context: Additional context
            intent: Detected intent
            entities: Extracted entities
            auto_fix: Whether to automatically apply fixes

        Returns:
            EnhancementResult with enhanced response
        """
        try:
            if not self.validator:
                await self.initialize()

            # Validate the response
            validation_result = await self.validator.validate_response(
                response=response, context=context, intent=intent, entities=entities
            )

            # Apply enhancements if auto_fix is enabled
            enhanced_response = response
            improvements_applied = []

            if auto_fix and (
                not validation_result.is_valid
                or validation_result.score < 0.99
                or len(validation_result.issues) > 0
            ):
                enhanced_response, improvements = await self._apply_enhancements(
                    response, validation_result
                )
                improvements_applied = improvements

            # Calculate enhancement score
            enhancement_score = self._calculate_enhancement_score(
                validation_result, len(improvements_applied)
            )

            return EnhancementResult(
                original_response=response,
                enhanced_response=enhanced_response,
                validation_result=validation_result,
                improvements_applied=improvements_applied,
                enhancement_score=enhancement_score,
                is_enhanced=len(improvements_applied) > 0,
            )

        except Exception as e:
            logger.error(f"Error enhancing response: {e}")
            return EnhancementResult(
                original_response=response,
                enhanced_response=response,
                validation_result=None,
                improvements_applied=[],
                enhancement_score=0.0,
                is_enhanced=False,
            )

    async def _apply_enhancements(
        self, response: str, validation_result: ValidationResult
    ) -> Tuple[str, List[str]]:
        """Apply enhancements based on validation issues."""
        enhanced_response = response
        improvements = []

        # Sort issues by severity (errors first, then warnings)
        sorted_issues = sorted(
            validation_result.issues,
            key=lambda x: (x.level.value == "error", x.level.value == "warning"),
        )

        for issue in sorted_issues:
            try:
                if issue.category == ValidationCategory.FORMATTING:
                    enhanced_response, improvement = await self._fix_formatting_issue(
                        enhanced_response, issue
                    )
                    if improvement:
                        improvements.append(improvement)

                elif issue.category == ValidationCategory.CONTENT_QUALITY:
                    enhanced_response, improvement = await self._fix_content_issue(
                        enhanced_response, issue
                    )
                    if improvement:
                        improvements.append(improvement)

                elif issue.category == ValidationCategory.COMPLETENESS:
                    enhanced_response, improvement = await self._fix_completeness_issue(
                        enhanced_response, issue
                    )
                    if improvement:
                        improvements.append(improvement)

                elif issue.category == ValidationCategory.SECURITY:
                    enhanced_response, improvement = await self._fix_security_issue(
                        enhanced_response, issue
                    )
                    if improvement:
                        improvements.append(improvement)

            except Exception as e:
                logger.warning(
                    f"Error applying enhancement for issue {issue.message}: {e}"
                )

        return enhanced_response, improvements

    async def _fix_formatting_issue(
        self, response: str, issue: ValidationIssue
    ) -> Tuple[str, str]:
        """Fix formatting-related issues."""
        enhanced_response = response
        improvement = ""

        if issue.field == "technical_details":
            # Remove technical details
            technical_patterns = [
                r"\*Sources?:[^*]+\*",
                r"\*\*Additional Context:\*\*[^}]+}",
                r"\{'[^}]+'\}",
                r"mcp_tools_used: \[\], tool_execution_results: \{\}",
                r"structured_response: \{[^}]+\}",
                r"actions_taken: \[.*?\]",
                r"natural_language: '[^']*'",
                r"confidence: \d+\.\d+",
            ]

            for pattern in technical_patterns:
                enhanced_response = re.sub(pattern, "", enhanced_response)

            improvement = "Removed technical implementation details"

        elif issue.field == "markdown":
            # Fix incomplete markdown
            enhanced_response = re.sub(r"\*\*([^*]+)$", r"**\1**", enhanced_response)
            improvement = "Fixed incomplete markdown formatting"

        elif issue.field == "list_formatting":
            # Fix list formatting
            enhanced_response = re.sub(r"•\s*$", "", enhanced_response)
            improvement = "Fixed list formatting"

        return enhanced_response, improvement

    async def _fix_content_issue(
        self, response: str, issue: ValidationIssue
    ) -> Tuple[str, str]:
        """Fix content quality issues."""
        enhanced_response = response
        improvement = ""

        if issue.field == "content_repetition":
            # Remove repetitive phrases
            enhanced_response = re.sub(r"(.{10,})\1{2,}", r"\1", enhanced_response)
            improvement = "Removed repetitive content"

        elif issue.field == "punctuation":
            # Fix excessive punctuation
            enhanced_response = re.sub(r"[!]{3,}", "!", enhanced_response)
            enhanced_response = re.sub(r"[?]{3,}", "?", enhanced_response)
            enhanced_response = re.sub(r"[.]{3,}", "...", enhanced_response)
            improvement = "Fixed excessive punctuation"

        elif issue.field == "capitalization":
            # Fix excessive caps
            enhanced_response = re.sub(
                r"\b[A-Z]{5,}\b", lambda m: m.group(0).title(), enhanced_response
            )
            improvement = "Fixed excessive capitalization"

        return enhanced_response, improvement

    async def _fix_completeness_issue(
        self, response: str, issue: ValidationIssue
    ) -> Tuple[str, str]:
        """Fix completeness issues."""
        enhanced_response = response
        improvement = ""

        if issue.field == "recommendations_count":
            # Limit recommendations
            recommendations = re.findall(r"•\s+([^•\n]+)", response)
            if len(recommendations) > 5:
                # Keep only first 5 recommendations
                recommendations_text = "\n".join(
                    f"• {rec}" for rec in recommendations[:5]
                )
                enhanced_response = re.sub(
                    r"\*\*Recommendations:\*\*\n(?:•\s+[^•\n]+\n?)+",
                    f"**Recommendations:**\n{recommendations_text}",
                    enhanced_response,
                )
                improvement = "Limited recommendations to 5 items"

        return enhanced_response, improvement

    async def _fix_security_issue(
        self, response: str, issue: ValidationIssue
    ) -> Tuple[str, str]:
        """Fix security issues."""
        enhanced_response = response
        improvement = ""

        if issue.field == "data_privacy":
            # Mask sensitive data
            enhanced_response = re.sub(
                r"\b\d{4}-\d{4}-\d{4}-\d{4}\b", "****-****-****-****", enhanced_response
            )
            enhanced_response = re.sub(
                r"\b\d{3}-\d{2}-\d{4}\b", "***-**-****", enhanced_response
            )
            enhanced_response = re.sub(
                r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
                "***@***.***",
                enhanced_response,
            )
            improvement = "Masked sensitive data"

        return enhanced_response, improvement

    def _calculate_enhancement_score(
        self, validation_result: ValidationResult, improvements_count: int
    ) -> float:
        """Calculate enhancement score."""
        if not validation_result:
            return 0.0

        # Base score from validation
        base_score = validation_result.score

        # Bonus for improvements applied
        improvement_bonus = min(0.2, improvements_count * 0.05)

        # Final score
        final_score = min(1.0, base_score + improvement_bonus)

        return round(final_score, 2)

    async def get_enhancement_summary(self, result: EnhancementResult) -> str:
        """Generate enhancement summary."""
        if not result.is_enhanced:
            return "No enhancements applied"

        improvements_text = ", ".join(result.improvements_applied[:3])
        if len(result.improvements_applied) > 3:
            improvements_text += f" and {len(result.improvements_applied) - 3} more"

        return f"Enhanced response: {improvements_text} (Score: {result.enhancement_score})"


# Global instance
_response_enhancer: Optional[ResponseEnhancer] = None


async def get_response_enhancer() -> ResponseEnhancer:
    """Get the global response enhancer instance."""
    global _response_enhancer
    if _response_enhancer is None:
        _response_enhancer = ResponseEnhancer()
        await _response_enhancer.initialize()
    return _response_enhancer
