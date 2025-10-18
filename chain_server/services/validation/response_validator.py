"""
Response Validation Service

Provides comprehensive validation of chat responses to ensure quality,
consistency, and compliance with warehouse operational standards.
"""

import re
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import json

logger = logging.getLogger(__name__)


class ValidationLevel(Enum):
    """Validation severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ValidationCategory(Enum):
    """Categories of validation checks."""

    CONTENT_QUALITY = "content_quality"
    FORMATTING = "formatting"
    COMPLIANCE = "compliance"
    SECURITY = "security"
    COMPLETENESS = "completeness"
    ACCURACY = "accuracy"


@dataclass
class ValidationIssue:
    """Individual validation issue."""

    category: ValidationCategory
    level: ValidationLevel
    message: str
    suggestion: Optional[str] = None
    field: Optional[str] = None
    line_number: Optional[int] = None


@dataclass
class ValidationResult:
    """Complete validation result."""

    is_valid: bool
    score: float  # 0.0 to 1.0
    issues: List[ValidationIssue]
    warnings: List[ValidationIssue]
    errors: List[ValidationIssue]
    suggestions: List[str]
    metadata: Dict[str, Any]


class ResponseValidator:
    """Comprehensive response validation service."""

    def __init__(self):
        self.min_response_length = 10
        self.max_response_length = 2000
        self.max_recommendations = 5
        self.max_technical_details = 3

        # Define validation patterns
        self._setup_validation_patterns()

    def _setup_validation_patterns(self):
        """Setup validation patterns and rules."""

        # Technical detail patterns to flag
        self.technical_patterns = [
            r"\*Sources?:[^*]+\*",
            r"\*\*Additional Context:\*\*[^}]+}",
            r"\{'[^}]+'\}",
            r"mcp_tools_used: \[\], tool_execution_results: \{\}",
            r"structured_response: \{[^}]+\}",
            r"actions_taken: \[.*?\]",
            r"natural_language: '[^']*'",
            r"confidence: \d+\.\d+",
            r"tool_execution_results: \{\}",
            r"mcp_tools_used: \[\]",
        ]

        # Compliance patterns
        self.compliance_patterns = {
            "safety_violations": [
                r"ignore.*safety",
                r"bypass.*protocol",
                r"skip.*check",
                r"override.*safety",
            ],
            "security_violations": [
                r"password.*plain",
                r"secret.*exposed",
                r"admin.*access",
                r"root.*privileges",
            ],
            "operational_violations": [
                r"unauthorized.*access",
                r"modify.*without.*permission",
                r"delete.*critical.*data",
            ],
        }

        # Quality patterns
        self.quality_patterns = {
            "repetition": r"(.{10,})\1{2,}",  # Repeated phrases
            "incomplete_sentences": r"[^.!?]\s*$",
            "excessive_punctuation": r"[!]{3,}|[?]{3,}|[.]{3,}",
            "missing_spaces": r"[a-zA-Z][a-zA-Z]",
            "excessive_caps": r"[A-Z]{5,}",
        }

    async def validate_response(
        self,
        response: str,
        context: Dict[str, Any] = None,
        intent: str = None,
        entities: Dict[str, Any] = None,
    ) -> ValidationResult:
        """
        Perform comprehensive validation of a response.

        Args:
            response: The response text to validate
            context: Additional context for validation
            intent: Detected intent for context-aware validation
            entities: Extracted entities for validation

        Returns:
            ValidationResult with detailed validation information
        """
        issues = []
        warnings = []
        errors = []
        suggestions = []

        try:
            # Basic content validation
            issues.extend(await self._validate_content_quality(response))

            # Formatting validation
            issues.extend(await self._validate_formatting(response))

            # Compliance validation
            issues.extend(await self._validate_compliance(response))

            # Security validation
            issues.extend(await self._validate_security(response))

            # Completeness validation
            issues.extend(await self._validate_completeness(response, context, intent))

            # Accuracy validation
            issues.extend(await self._validate_accuracy(response, entities))

            # Categorize issues
            for issue in issues:
                if issue.level == ValidationLevel.ERROR:
                    errors.append(issue)
                elif issue.level == ValidationLevel.WARNING:
                    warnings.append(issue)

                if issue.suggestion:
                    suggestions.append(issue.suggestion)

            # Calculate validation score
            score = self._calculate_validation_score(
                len(issues), len(errors), len(warnings)
            )

            # Determine overall validity
            is_valid = len(errors) == 0 and score >= 0.7

            return ValidationResult(
                is_valid=is_valid,
                score=score,
                issues=issues,
                warnings=warnings,
                errors=errors,
                suggestions=suggestions,
                metadata={
                    "response_length": len(response),
                    "word_count": len(response.split()),
                    "validation_timestamp": "2025-10-15T13:20:00Z",
                    "intent": intent,
                    "entity_count": len(entities) if entities else 0,
                },
            )

        except Exception as e:
            logger.error(f"Error during response validation: {e}")
            return ValidationResult(
                is_valid=False,
                score=0.0,
                issues=[
                    ValidationIssue(
                        category=ValidationCategory.CONTENT_QUALITY,
                        level=ValidationLevel.CRITICAL,
                        message=f"Validation error: {str(e)}",
                    )
                ],
                warnings=[],
                errors=[],
                suggestions=["Fix validation system error"],
                metadata={"error": str(e)},
            )

    async def _validate_content_quality(self, response: str) -> List[ValidationIssue]:
        """Validate content quality aspects."""
        issues = []

        # Check response length
        if len(response) < self.min_response_length:
            issues.append(
                ValidationIssue(
                    category=ValidationCategory.CONTENT_QUALITY,
                    level=ValidationLevel.WARNING,
                    message="Response is too short",
                    suggestion="Provide more detailed information",
                    field="response_length",
                )
            )
        elif len(response) > self.max_response_length:
            issues.append(
                ValidationIssue(
                    category=ValidationCategory.CONTENT_QUALITY,
                    level=ValidationLevel.WARNING,
                    message="Response is too long",
                    suggestion="Consider breaking into multiple responses",
                    field="response_length",
                )
            )

        # Check for repetition
        repetition_match = re.search(
            self.quality_patterns["repetition"], response, re.IGNORECASE
        )
        if repetition_match:
            issues.append(
                ValidationIssue(
                    category=ValidationCategory.CONTENT_QUALITY,
                    level=ValidationLevel.WARNING,
                    message="Detected repetitive content",
                    suggestion="Remove repetitive phrases",
                    field="content_repetition",
                )
            )

        # Check for excessive punctuation
        excessive_punct = re.search(
            self.quality_patterns["excessive_punctuation"], response
        )
        if excessive_punct:
            issues.append(
                ValidationIssue(
                    category=ValidationCategory.CONTENT_QUALITY,
                    level=ValidationLevel.INFO,
                    message="Excessive punctuation detected",
                    suggestion="Use standard punctuation",
                    field="punctuation",
                )
            )

        # Check for excessive caps
        excessive_caps = re.search(self.quality_patterns["excessive_caps"], response)
        if excessive_caps:
            issues.append(
                ValidationIssue(
                    category=ValidationCategory.CONTENT_QUALITY,
                    level=ValidationLevel.WARNING,
                    message="Excessive capitalization detected",
                    suggestion="Use proper capitalization",
                    field="capitalization",
                )
            )

        return issues

    async def _validate_formatting(self, response: str) -> List[ValidationIssue]:
        """Validate formatting aspects."""
        issues = []

        # Check for technical details that should be hidden
        technical_count = 0
        for pattern in self.technical_patterns:
            matches = re.findall(pattern, response)
            technical_count += len(matches)

        if technical_count > self.max_technical_details:
            issues.append(
                ValidationIssue(
                    category=ValidationCategory.FORMATTING,
                    level=ValidationLevel.WARNING,
                    message=f"Too many technical details ({technical_count})",
                    suggestion="Remove technical implementation details",
                    field="technical_details",
                )
            )

        # Check for proper markdown formatting
        if "**" in response and not re.search(r"\*\*[^*]+\*\*", response):
            issues.append(
                ValidationIssue(
                    category=ValidationCategory.FORMATTING,
                    level=ValidationLevel.INFO,
                    message="Incomplete markdown formatting",
                    suggestion="Complete markdown formatting",
                    field="markdown",
                )
            )

        # Check for proper list formatting
        if "•" in response and not re.search(r"•\s+[^•]", response):
            issues.append(
                ValidationIssue(
                    category=ValidationCategory.FORMATTING,
                    level=ValidationLevel.INFO,
                    message="Incomplete list formatting",
                    suggestion="Ensure proper list item formatting",
                    field="list_formatting",
                )
            )

        return issues

    async def _validate_compliance(self, response: str) -> List[ValidationIssue]:
        """Validate compliance with warehouse operational standards."""
        issues = []

        # Check for safety violations
        for pattern in self.compliance_patterns["safety_violations"]:
            if re.search(pattern, response, re.IGNORECASE):
                issues.append(
                    ValidationIssue(
                        category=ValidationCategory.COMPLIANCE,
                        level=ValidationLevel.ERROR,
                        message="Potential safety violation detected",
                        suggestion="Review safety protocols",
                        field="safety_compliance",
                    )
                )
                break

        # Check for operational violations
        for pattern in self.compliance_patterns["operational_violations"]:
            if re.search(pattern, response, re.IGNORECASE):
                issues.append(
                    ValidationIssue(
                        category=ValidationCategory.COMPLIANCE,
                        level=ValidationLevel.ERROR,
                        message="Potential operational violation detected",
                        suggestion="Review operational procedures",
                        field="operational_compliance",
                    )
                )
                break

        return issues

    async def _validate_security(self, response: str) -> List[ValidationIssue]:
        """Validate security aspects."""
        issues = []

        # Check for security violations
        for pattern in self.compliance_patterns["security_violations"]:
            if re.search(pattern, response, re.IGNORECASE):
                issues.append(
                    ValidationIssue(
                        category=ValidationCategory.SECURITY,
                        level=ValidationLevel.CRITICAL,
                        message="Security violation detected",
                        suggestion="Remove sensitive information",
                        field="security",
                    )
                )
                break

        # Check for potential data exposure
        sensitive_patterns = [
            r"\b\d{4}-\d{4}-\d{4}-\d{4}\b",  # Credit card pattern
            r"\b\d{3}-\d{2}-\d{4}\b",  # SSN pattern
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",  # Email pattern
        ]

        for pattern in sensitive_patterns:
            if re.search(pattern, response):
                issues.append(
                    ValidationIssue(
                        category=ValidationCategory.SECURITY,
                        level=ValidationLevel.WARNING,
                        message="Potential sensitive data detected",
                        suggestion="Remove or mask sensitive information",
                        field="data_privacy",
                    )
                )
                break

        return issues

    async def _validate_completeness(
        self, response: str, context: Dict[str, Any], intent: str
    ) -> List[ValidationIssue]:
        """Validate response completeness."""
        issues = []

        if not intent:
            return issues

        # Check for intent-specific completeness
        if intent == "equipment":
            if not re.search(
                r"\b(available|assigned|maintenance|status)\b", response, re.IGNORECASE
            ):
                issues.append(
                    ValidationIssue(
                        category=ValidationCategory.COMPLETENESS,
                        level=ValidationLevel.WARNING,
                        message="Equipment response missing status information",
                        suggestion="Include equipment status information",
                        field="equipment_status",
                    )
                )

        elif intent == "operations":
            if not re.search(
                r"\b(wave|order|task|priority)\b", response, re.IGNORECASE
            ):
                issues.append(
                    ValidationIssue(
                        category=ValidationCategory.COMPLETENESS,
                        level=ValidationLevel.WARNING,
                        message="Operations response missing key operational terms",
                        suggestion="Include operational details",
                        field="operational_details",
                    )
                )

        elif intent == "safety":
            if not re.search(
                r"\b(safety|incident|hazard|protocol)\b", response, re.IGNORECASE
            ):
                issues.append(
                    ValidationIssue(
                        category=ValidationCategory.COMPLETENESS,
                        level=ValidationLevel.WARNING,
                        message="Safety response missing safety-related terms",
                        suggestion="Include safety-specific information",
                        field="safety_details",
                    )
                )

        # Check for recommendations
        if "**Recommendations:**" in response:
            recommendations = re.findall(r"•\s+([^•\n]+)", response)
            if len(recommendations) > self.max_recommendations:
                issues.append(
                    ValidationIssue(
                        category=ValidationCategory.COMPLETENESS,
                        level=ValidationLevel.INFO,
                        message=f"Too many recommendations ({len(recommendations)})",
                        suggestion=f"Limit to {self.max_recommendations} recommendations",
                        field="recommendations_count",
                    )
                )

        return issues

    async def _validate_accuracy(
        self, response: str, entities: Dict[str, Any]
    ) -> List[ValidationIssue]:
        """Validate response accuracy."""
        issues = []

        if not entities:
            return issues

        # Check if mentioned entities are consistent
        for entity_type, entity_value in entities.items():
            if isinstance(entity_value, str):
                if entity_value.lower() not in response.lower():
                    issues.append(
                        ValidationIssue(
                            category=ValidationCategory.ACCURACY,
                            level=ValidationLevel.INFO,
                            message=f"Entity {entity_type} not mentioned in response",
                            suggestion=f"Include reference to {entity_value}",
                            field=f"entity_{entity_type}",
                        )
                    )

        # Check for contradictory information
        contradictions = [
            (r"\b(available|ready)\b", r"\b(assigned|busy|occupied)\b"),
            (r"\b(completed|finished)\b", r"\b(pending|in progress)\b"),
            (r"\b(high|urgent)\b", r"\b(low|normal)\b"),
        ]

        for pos_pattern, neg_pattern in contradictions:
            if re.search(pos_pattern, response, re.IGNORECASE) and re.search(
                neg_pattern, response, re.IGNORECASE
            ):
                issues.append(
                    ValidationIssue(
                        category=ValidationCategory.ACCURACY,
                        level=ValidationLevel.WARNING,
                        message="Potential contradictory information detected",
                        suggestion="Review for consistency",
                        field="contradiction",
                    )
                )
                break

        return issues

    def _calculate_validation_score(
        self, total_issues: int, errors: int, warnings: int
    ) -> float:
        """Calculate validation score based on issues."""
        if total_issues == 0:
            return 1.0

        # Weight different issue types
        error_weight = 0.5
        warning_weight = 0.3
        info_weight = 0.1

        # Calculate penalty
        penalty = (
            errors * error_weight
            + warnings * warning_weight
            + (total_issues - errors - warnings) * info_weight
        )

        # Normalize to 0-1 scale
        max_penalty = 10.0  # Maximum penalty for severe issues
        score = max(0.0, 1.0 - (penalty / max_penalty))

        return round(score, 2)

    async def get_validation_summary(self, result: ValidationResult) -> str:
        """Generate a human-readable validation summary."""
        if result.is_valid and result.score >= 0.9:
            return "✅ Response validation passed with excellent quality"
        elif result.is_valid and result.score >= 0.7:
            return f"✅ Response validation passed (Score: {result.score})"
        elif result.score >= 0.5:
            return f"⚠️ Response validation passed with warnings (Score: {result.score})"
        else:
            return f"❌ Response validation failed (Score: {result.score})"

    async def suggest_improvements(self, result: ValidationResult) -> List[str]:
        """Generate improvement suggestions based on validation results."""
        suggestions = []

        # Add suggestions from validation issues
        suggestions.extend(result.suggestions)

        # Add general suggestions based on score
        if result.score < 0.7:
            suggestions.append("Consider improving response clarity and completeness")

        if len(result.errors) > 0:
            suggestions.append("Address critical validation errors")

        if len(result.warnings) > 2:
            suggestions.append("Reduce number of validation warnings")

        # Remove duplicates and limit
        unique_suggestions = list(dict.fromkeys(suggestions))
        return unique_suggestions[:5]


# Global instance
_response_validator: Optional[ResponseValidator] = None


async def get_response_validator() -> ResponseValidator:
    """Get the global response validator instance."""
    global _response_validator
    if _response_validator is None:
        _response_validator = ResponseValidator()
    return _response_validator
