"""
Response validation service for agent responses.

Validates agent responses for quality, completeness, and correctness.
"""

import re
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of response validation."""
    
    is_valid: bool
    score: float  # 0.0 to 1.0
    issues: List[str]
    warnings: List[str]
    suggestions: List[str]


class ResponseValidator:
    """Validates agent responses for quality and completeness."""
    
    # Minimum thresholds
    MIN_NATURAL_LANGUAGE_LENGTH = 20
    MIN_CONFIDENCE = 0.3
    MAX_CONFIDENCE = 1.0
    
    # Quality indicators
    QUALITY_KEYWORDS = [
        "successfully", "completed", "created", "assigned", "dispatched",
        "status", "available", "queued", "in progress"
    ]
    
    # Anti-patterns (indicators of poor quality)
    ANTI_PATTERNS = [
        r"you asked me to",
        r"you requested",
        r"i will",
        r"i'm going to",
        r"let me",
        r"i'll",
        r"as you requested",
        r"as requested",
    ]
    
    def __init__(self):
        """Initialize the response validator."""
        self.anti_pattern_regex = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.ANTI_PATTERNS
        ]
    
    def validate(
        self,
        response: Dict[str, Any],
        query: Optional[str] = None,
        tool_results: Optional[Dict[str, Any]] = None,
    ) -> ValidationResult:
        """
        Validate an agent response.
        
        Args:
            response: The agent response dictionary
            query: The original user query (optional, for context)
            tool_results: Tool execution results (optional, for validation)
        
        Returns:
            ValidationResult with validation status and issues
        """
        issues = []
        warnings = []
        suggestions = []
        score = 1.0
        
        # Extract response fields
        natural_language = response.get("natural_language", "")
        confidence = response.get("confidence", 0.5)
        response_type = response.get("response_type", "")
        recommendations = response.get("recommendations", [])
        actions_taken = response.get("actions_taken", [])
        mcp_tools_used = response.get("mcp_tools_used", [])
        tool_execution_results = response.get("tool_execution_results", {})
        
        # 1. Validate natural language
        nl_validation = self._validate_natural_language(natural_language, query)
        issues.extend(nl_validation["issues"])
        warnings.extend(nl_validation["warnings"])
        suggestions.extend(nl_validation["suggestions"])
        score *= nl_validation["score"]
        
        # 2. Validate confidence score
        conf_validation = self._validate_confidence(confidence, tool_results)
        issues.extend(conf_validation["issues"])
        warnings.extend(conf_validation["warnings"])
        suggestions.extend(conf_validation["suggestions"])
        score *= conf_validation["score"]
        
        # 3. Validate response completeness
        completeness_validation = self._validate_completeness(
            response, tool_results, mcp_tools_used, tool_execution_results
        )
        issues.extend(completeness_validation["issues"])
        warnings.extend(completeness_validation["warnings"])
        suggestions.extend(completeness_validation["suggestions"])
        score *= completeness_validation["score"]
        
        # 4. Validate response structure
        structure_validation = self._validate_structure(response)
        issues.extend(structure_validation["issues"])
        warnings.extend(structure_validation["warnings"])
        suggestions.extend(structure_validation["suggestions"])
        score *= structure_validation["score"]
        
        # 5. Validate action reporting
        if actions_taken or tool_execution_results:
            action_validation = self._validate_action_reporting(
                natural_language, actions_taken, tool_execution_results
            )
            issues.extend(action_validation["issues"])
            warnings.extend(action_validation["warnings"])
            suggestions.extend(action_validation["suggestions"])
            score *= action_validation["score"]
        
        # Determine if response is valid
        is_valid = len(issues) == 0 and score >= 0.6
        
        return ValidationResult(
            is_valid=is_valid,
            score=score,
            issues=issues,
            warnings=warnings,
            suggestions=suggestions,
        )
    
    def _validate_natural_language(
        self, natural_language: str, query: Optional[str] = None
    ) -> Dict[str, Any]:
        """Validate natural language response."""
        issues = []
        warnings = []
        suggestions = []
        score = 1.0
        
        if not natural_language or not natural_language.strip():
            issues.append("Natural language response is empty")
            return {"issues": issues, "warnings": warnings, "suggestions": suggestions, "score": 0.0}
        
        nl_lower = natural_language.lower()
        nl_length = len(natural_language.strip())
        
        # Check minimum length
        if nl_length < self.MIN_NATURAL_LANGUAGE_LENGTH:
            issues.append(f"Natural language too short ({nl_length} chars, minimum {self.MIN_NATURAL_LANGUAGE_LENGTH})")
            score *= 0.5
        
        # Check for query echoing (anti-patterns)
        for pattern in self.anti_pattern_regex:
            if pattern.search(natural_language):
                issues.append(f"Response echoes query: contains '{pattern.pattern}'")
                score *= 0.3
                break
        
        # Check for quality indicators
        quality_count = sum(1 for keyword in self.QUALITY_KEYWORDS if keyword in nl_lower)
        if quality_count == 0 and nl_length > 50:
            warnings.append("Response lacks specific action/status keywords")
            score *= 0.9
        
        # Check if response starts with action (good) vs. query reference (bad)
        first_words = natural_language.strip().split()[:3]
        first_text = " ".join(first_words).lower()
        
        if any(word in first_text for word in ["you", "your", "requested", "asked"]):
            warnings.append("Response may start with query reference instead of action")
            score *= 0.85
        
        # Check for specific details (IDs, names, statuses)
        has_ids = bool(re.search(r'\b[A-Z]+[-_]?[A-Z0-9]+\b', natural_language))
        has_numbers = bool(re.search(r'\b\d+\b', natural_language))
        
        if not has_ids and not has_numbers and nl_length > 100:
            suggestions.append("Consider including specific IDs, names, or numbers for clarity")
        
        # Check sentence structure
        sentences = re.split(r'[.!?]+', natural_language)
        sentence_count = len([s for s in sentences if s.strip()])
        
        if sentence_count < 2 and nl_length > 100:
            suggestions.append("Consider breaking response into multiple sentences for readability")
        
        return {
            "issues": issues,
            "warnings": warnings,
            "suggestions": suggestions,
            "score": score,
        }
    
    def _validate_confidence(
        self, confidence: float, tool_results: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Validate confidence score."""
        issues = []
        warnings = []
        suggestions = []
        score = 1.0
        
        # Check confidence range
        if confidence < self.MIN_CONFIDENCE:
            issues.append(f"Confidence too low ({confidence:.2f}, minimum {self.MIN_CONFIDENCE})")
            score *= 0.5
        elif confidence > self.MAX_CONFIDENCE:
            issues.append(f"Confidence exceeds maximum ({confidence:.2f}, maximum {self.MAX_CONFIDENCE})")
            score *= 0.8
        
        # Validate confidence against tool results
        if tool_results:
            successful = sum(1 for r in tool_results.values() if r.get("success", False))
            total = len(tool_results)
            
            if total > 0:
                success_rate = successful / total
                
                # Expected confidence ranges based on success rate
                if success_rate == 1.0:  # All tools succeeded
                    expected_min = 0.85
                    expected_max = 0.95
                elif success_rate >= 0.5:  # Most tools succeeded
                    expected_min = 0.70
                    expected_max = 0.85
                elif success_rate > 0:  # Some tools succeeded
                    expected_min = 0.60
                    expected_max = 0.75
                else:  # All tools failed
                    expected_min = 0.30
                    expected_max = 0.50
                
                if confidence < expected_min:
                    warnings.append(
                        f"Confidence ({confidence:.2f}) seems low for success rate ({success_rate:.2f}). "
                        f"Expected range: {expected_min:.2f}-{expected_max:.2f}"
                    )
                    score *= 0.9
                elif confidence > expected_max:
                    warnings.append(
                        f"Confidence ({confidence:.2f}) seems high for success rate ({success_rate:.2f}). "
                        f"Expected range: {expected_min:.2f}-{expected_max:.2f}"
                    )
                    score *= 0.95
        
        return {
            "issues": issues,
            "warnings": warnings,
            "suggestions": suggestions,
            "score": score,
        }
    
    def _validate_completeness(
        self,
        response: Dict[str, Any],
        tool_results: Optional[Dict[str, Any]],
        mcp_tools_used: List[str],
        tool_execution_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Validate response completeness."""
        issues = []
        warnings = []
        suggestions = []
        score = 1.0
        
        # Check if tools were used but not reported
        if tool_results and len(tool_results) > 0:
            if not mcp_tools_used or len(mcp_tools_used) == 0:
                warnings.append("Tools were executed but not reported in mcp_tools_used")
                score *= 0.9
            
            if not tool_execution_results or len(tool_execution_results) == 0:
                warnings.append("Tools were executed but tool_execution_results is empty")
                score *= 0.9
        
        # Check if response type is set
        if not response.get("response_type"):
            warnings.append("Response type is not set")
            score *= 0.95
        
        # Check if recommendations are provided for complex queries
        natural_language = response.get("natural_language", "")
        if len(natural_language) > 200 and not response.get("recommendations"):
            suggestions.append("Consider adding recommendations for complex queries")
        
        return {
            "issues": issues,
            "warnings": warnings,
            "suggestions": suggestions,
            "score": score,
        }
    
    def _validate_structure(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Validate response structure."""
        issues = []
        warnings = []
        suggestions = []
        score = 1.0
        
        required_fields = ["natural_language", "confidence"]
        for field in required_fields:
            if field not in response:
                issues.append(f"Missing required field: {field}")
                score *= 0.5
        
        # Check data types
        if "confidence" in response:
            if not isinstance(response["confidence"], (int, float)):
                issues.append("Confidence must be a number")
                score *= 0.5
            elif not (0.0 <= response["confidence"] <= 1.0):
                issues.append("Confidence must be between 0.0 and 1.0")
                score *= 0.5
        
        if "recommendations" in response:
            if not isinstance(response["recommendations"], list):
                issues.append("Recommendations must be a list")
                score *= 0.7
        
        if "actions_taken" in response:
            if not isinstance(response["actions_taken"], list):
                issues.append("Actions taken must be a list")
                score *= 0.7
        
        return {
            "issues": issues,
            "warnings": warnings,
            "suggestions": suggestions,
            "score": score,
        }
    
    def _validate_action_reporting(
        self,
        natural_language: str,
        actions_taken: List[Dict[str, Any]],
        tool_execution_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Validate that actions are properly reported in natural language."""
        issues = []
        warnings = []
        suggestions = []
        score = 1.0
        
        if not actions_taken and not tool_execution_results:
            return {
                "issues": issues,
                "warnings": warnings,
                "suggestions": suggestions,
                "score": score,
            }
        
        # Check if natural language mentions actions
        nl_lower = natural_language.lower()
        action_keywords = ["created", "assigned", "dispatched", "completed", "executed", "processed"]
        has_action_keywords = any(keyword in nl_lower for keyword in action_keywords)
        
        if actions_taken and not has_action_keywords:
            warnings.append("Actions were taken but not clearly mentioned in natural language")
            score *= 0.85
        
        # Check if specific IDs/names from actions are mentioned
        if tool_execution_results:
            mentioned_ids = set()
            for result in tool_execution_results.values():
                if isinstance(result, dict):
                    result_str = str(result)
                    # Extract potential IDs
                    ids = re.findall(r'\b[A-Z]+[-_]?[A-Z0-9]+\b', result_str)
                    mentioned_ids.update(ids)
            
            if mentioned_ids:
                # Check if any IDs are mentioned in natural language
                ids_in_nl = any(id_val.lower() in nl_lower for id_val in mentioned_ids)
                if not ids_in_nl:
                    suggestions.append("Consider mentioning specific IDs or names from tool results in the response")
        
        return {
            "issues": issues,
            "warnings": warnings,
            "suggestions": suggestions,
            "score": score,
        }


def get_response_validator() -> ResponseValidator:
    """Get a singleton instance of ResponseValidator."""
    if not hasattr(get_response_validator, "_instance"):
        get_response_validator._instance = ResponseValidator()
    return get_response_validator._instance
