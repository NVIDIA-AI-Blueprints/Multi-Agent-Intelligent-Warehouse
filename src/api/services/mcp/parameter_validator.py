"""
MCP Tool Parameter Validation Service

Provides comprehensive parameter validation for MCP tools to prevent
invalid tool calls and provide clear error messages.
"""

import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from enum import Enum
import re
from datetime import datetime

logger = logging.getLogger(__name__)


class ValidationLevel(Enum):
    """Validation severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ParameterType(Enum):
    """Parameter types for validation."""

    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    EMAIL = "email"
    URL = "url"
    DATE = "date"
    DATETIME = "datetime"
    UUID = "uuid"
    EQUIPMENT_ID = "equipment_id"
    ZONE_ID = "zone_id"
    TASK_ID = "task_id"
    USER_ID = "user_id"


@dataclass
class ValidationIssue:
    """Individual validation issue."""

    parameter: str
    level: ValidationLevel
    message: str
    suggestion: Optional[str] = None
    provided_value: Optional[Any] = None
    expected_type: Optional[str] = None


@dataclass
class ValidationResult:
    """Complete validation result."""

    is_valid: bool
    issues: List[ValidationIssue]
    warnings: List[ValidationIssue]
    errors: List[ValidationIssue]
    validated_arguments: Dict[str, Any]
    suggestions: List[str]


class MCPParameterValidator:
    """Comprehensive parameter validation service for MCP tools."""

    def __init__(self):
        self.validation_patterns = self._setup_validation_patterns()
        self.business_rules = self._setup_business_rules()

    def _setup_validation_patterns(self) -> Dict[str, re.Pattern]:
        """Setup validation patterns for different parameter types."""
        return {
            ParameterType.EMAIL.value: re.compile(
                r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
            ),
            ParameterType.URL.value: re.compile(r"^https?://[^\s/$.?#].[^\s]*$"),
            ParameterType.UUID.value: re.compile(
                r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                re.IGNORECASE,
            ),
            ParameterType.EQUIPMENT_ID.value: re.compile(
                r"^[A-Z]{2}-\d{2,3}$"
            ),  # FL-01, SC-123
            ParameterType.ZONE_ID.value: re.compile(r"^Zone [A-Z]$"),  # Zone A, Zone B
            ParameterType.TASK_ID.value: re.compile(r"^T-\d{3,6}$"),  # T-123, T-123456
            ParameterType.USER_ID.value: re.compile(
                r"^[a-zA-Z0-9_]{3,20}$"
            ),  # alphanumeric, 3-20 chars
            ParameterType.DATE.value: re.compile(r"^\d{4}-\d{2}-\d{2}$"),  # YYYY-MM-DD
            ParameterType.DATETIME.value: re.compile(
                r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
            ),  # ISO format
        }

    def _setup_business_rules(self) -> Dict[str, Dict[str, Any]]:
        """Setup business rules for parameter validation."""
        return {
            "equipment_status": {
                "valid_values": [
                    "available",
                    "assigned",
                    "maintenance",
                    "charging",
                    "offline",
                ],
                "required_for": ["assign_equipment", "get_equipment_status"],
            },
            "equipment_type": {
                "valid_values": [
                    "forklift",
                    "scanner",
                    "amr",
                    "agv",
                    "conveyor",
                    "charger",
                ],
                "required_for": ["get_equipment_status", "get_equipment_utilization"],
            },
            "assignment_type": {
                "valid_values": ["task", "user", "maintenance", "emergency"],
                "required_for": ["assign_equipment"],
            },
            "time_period": {
                "valid_values": ["hour", "day", "week", "month", "quarter", "year"],
                "required_for": ["get_equipment_utilization"],
            },
            "priority": {
                "valid_values": ["low", "normal", "high", "urgent", "critical"],
                "required_for": ["create_task", "assign_task"],
            },
        }

    async def validate_tool_parameters(
        self, tool_name: str, tool_schema: Dict[str, Any], arguments: Dict[str, Any]
    ) -> ValidationResult:
        """
        Validate tool parameters against schema and business rules.

        Args:
            tool_name: Name of the tool being validated
            tool_schema: Tool parameter schema
            arguments: Arguments to validate

        Returns:
            ValidationResult with validation details
        """
        issues = []
        warnings = []
        errors = []
        validated_arguments = {}
        suggestions = []

        try:
            # Get parameter properties
            properties = tool_schema.get("properties", {})
            required_params = tool_schema.get("required", [])

            # Check required parameters
            for param in required_params:
                if param not in arguments:
                    error = ValidationIssue(
                        parameter=param,
                        level=ValidationLevel.ERROR,
                        message=f"Required parameter '{param}' is missing",
                        suggestion=f"Provide the required parameter '{param}'",
                    )
                    errors.append(error)
                    issues.append(error)

            # Validate provided parameters
            for param_name, param_value in arguments.items():
                if param_name in properties:
                    param_schema = properties[param_name]
                    validation_result = await self._validate_parameter(
                        param_name, param_value, param_schema, tool_name
                    )

                    if validation_result["valid"]:
                        validated_arguments[param_name] = validation_result["value"]
                    else:
                        issue = validation_result["issue"]
                        issues.append(issue)

                        if issue.level == ValidationLevel.ERROR:
                            errors.append(issue)
                        elif issue.level == ValidationLevel.WARNING:
                            warnings.append(issue)

                        if issue.suggestion:
                            suggestions.append(issue.suggestion)

            # Apply business rules
            business_issues = await self._validate_business_rules(
                tool_name, validated_arguments
            )
            issues.extend(business_issues)

            for issue in business_issues:
                if issue.level == ValidationLevel.ERROR:
                    errors.append(issue)
                elif issue.level == ValidationLevel.WARNING:
                    warnings.append(issue)

                if issue.suggestion:
                    suggestions.append(issue.suggestion)

            # Determine overall validity
            is_valid = len(errors) == 0

            return ValidationResult(
                is_valid=is_valid,
                issues=issues,
                warnings=warnings,
                errors=errors,
                validated_arguments=validated_arguments,
                suggestions=suggestions,
            )

        except Exception as e:
            logger.error(f"Error validating tool parameters: {e}")
            return ValidationResult(
                is_valid=False,
                issues=[
                    ValidationIssue(
                        parameter="validation_system",
                        level=ValidationLevel.CRITICAL,
                        message=f"Validation system error: {str(e)}",
                    )
                ],
                warnings=[],
                errors=[],
                validated_arguments={},
                suggestions=["Fix validation system error"],
            )

    async def _validate_parameter(
        self,
        param_name: str,
        param_value: Any,
        param_schema: Dict[str, Any],
        tool_name: str,
    ) -> Dict[str, Any]:
        """Validate a single parameter."""
        try:
            # Get parameter type
            param_type = param_schema.get("type", "string")

            # Type validation
            if not self._validate_type(param_value, param_type):
                return {
                    "valid": False,
                    "value": param_value,
                    "issue": ValidationIssue(
                        parameter=param_name,
                        level=ValidationLevel.ERROR,
                        message=f"Parameter '{param_name}' has invalid type",
                        suggestion=f"Expected {param_type}, got {type(param_value).__name__}",
                        provided_value=param_value,
                        expected_type=param_type,
                    ),
                }

            # Format validation
            if param_type == "string":
                format_validation = self._validate_string_format(
                    param_name, param_value, param_schema
                )
                if not format_validation["valid"]:
                    return format_validation

            # Range validation
            if param_type in ["integer", "number"]:
                range_validation = self._validate_range(
                    param_name, param_value, param_schema
                )
                if not range_validation["valid"]:
                    return range_validation

            # Length validation
            if param_type == "string":
                length_validation = self._validate_length(
                    param_name, param_value, param_schema
                )
                if not length_validation["valid"]:
                    return length_validation

            # Enum validation
            if "enum" in param_schema:
                enum_validation = self._validate_enum(
                    param_name, param_value, param_schema
                )
                if not enum_validation["valid"]:
                    return enum_validation

            return {"valid": True, "value": param_value, "issue": None}

        except Exception as e:
            logger.error(f"Error validating parameter {param_name}: {e}")
            return {
                "valid": False,
                "value": param_value,
                "issue": ValidationIssue(
                    parameter=param_name,
                    level=ValidationLevel.ERROR,
                    message=f"Parameter validation error: {str(e)}",
                ),
            }

    def _validate_type(self, value: Any, expected_type: str) -> bool:
        """Validate parameter type."""
        type_mapping = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }

        if expected_type not in type_mapping:
            return True  # Unknown type, skip validation

        expected_python_type = type_mapping[expected_type]

        if expected_type == "number":
            return isinstance(value, expected_python_type)
        else:
            return isinstance(value, expected_python_type)

    def _validate_string_format(
        self, param_name: str, value: str, schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate string format."""
        format_type = schema.get("format")

        if format_type and format_type in self.validation_patterns:
            pattern = self.validation_patterns[format_type]
            if not pattern.match(value):
                return {
                    "valid": False,
                    "value": value,
                    "issue": ValidationIssue(
                        parameter=param_name,
                        level=ValidationLevel.ERROR,
                        message=f"Parameter '{param_name}' has invalid format",
                        suggestion=f"Expected {format_type} format",
                        provided_value=value,
                        expected_type=format_type,
                    ),
                }

        return {"valid": True, "value": value, "issue": None}

    def _validate_range(
        self, param_name: str, value: Union[int, float], schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate numeric range."""
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")

        if minimum is not None and value < minimum:
            return {
                "valid": False,
                "value": value,
                "issue": ValidationIssue(
                    parameter=param_name,
                    level=ValidationLevel.ERROR,
                    message=f"Parameter '{param_name}' is below minimum value",
                    suggestion=f"Value must be at least {minimum}",
                    provided_value=value,
                ),
            }

        if maximum is not None and value > maximum:
            return {
                "valid": False,
                "value": value,
                "issue": ValidationIssue(
                    parameter=param_name,
                    level=ValidationLevel.ERROR,
                    message=f"Parameter '{param_name}' exceeds maximum value",
                    suggestion=f"Value must be at most {maximum}",
                    provided_value=value,
                ),
            }

        return {"valid": True, "value": value, "issue": None}

    def _validate_length(
        self, param_name: str, value: str, schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate string length."""
        min_length = schema.get("minLength")
        max_length = schema.get("maxLength")

        if min_length is not None and len(value) < min_length:
            return {
                "valid": False,
                "value": value,
                "issue": ValidationIssue(
                    parameter=param_name,
                    level=ValidationLevel.ERROR,
                    message=f"Parameter '{param_name}' is too short",
                    suggestion=f"Minimum length is {min_length} characters",
                    provided_value=value,
                ),
            }

        if max_length is not None and len(value) > max_length:
            return {
                "valid": False,
                "value": value,
                "issue": ValidationIssue(
                    parameter=param_name,
                    level=ValidationLevel.ERROR,
                    message=f"Parameter '{param_name}' is too long",
                    suggestion=f"Maximum length is {max_length} characters",
                    provided_value=value,
                ),
            }

        return {"valid": True, "value": value, "issue": None}

    def _validate_enum(
        self, param_name: str, value: Any, schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate enum values."""
        enum_values = schema.get("enum", [])

        if enum_values and value not in enum_values:
            return {
                "valid": False,
                "value": value,
                "issue": ValidationIssue(
                    parameter=param_name,
                    level=ValidationLevel.ERROR,
                    message=f"Parameter '{param_name}' has invalid value",
                    suggestion=f"Valid values are: {', '.join(map(str, enum_values))}",
                    provided_value=value,
                ),
            }

        return {"valid": True, "value": value, "issue": None}

    async def _validate_business_rules(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> List[ValidationIssue]:
        """Validate business rules for the tool."""
        issues = []

        try:
            # Check equipment-specific business rules
            if "equipment" in tool_name.lower():
                equipment_issues = await self._validate_equipment_business_rules(
                    tool_name, arguments
                )
                issues.extend(equipment_issues)

            # Check task-specific business rules
            if "task" in tool_name.lower():
                task_issues = await self._validate_task_business_rules(
                    tool_name, arguments
                )
                issues.extend(task_issues)

            # Check safety-specific business rules
            if "safety" in tool_name.lower():
                safety_issues = await self._validate_safety_business_rules(
                    tool_name, arguments
                )
                issues.extend(safety_issues)

        except Exception as e:
            logger.error(f"Error validating business rules: {e}")
            issues.append(
                ValidationIssue(
                    parameter="business_rules",
                    level=ValidationLevel.ERROR,
                    message=f"Business rule validation error: {str(e)}",
                )
            )

        return issues

    async def _validate_equipment_business_rules(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> List[ValidationIssue]:
        """Validate equipment-specific business rules."""
        issues = []

        # Equipment ID format validation
        if "asset_id" in arguments:
            asset_id = arguments["asset_id"]
            if not self.validation_patterns[ParameterType.EQUIPMENT_ID.value].match(
                asset_id
            ):
                issues.append(
                    ValidationIssue(
                        parameter="asset_id",
                        level=ValidationLevel.WARNING,
                        message=f"Equipment ID '{asset_id}' doesn't follow standard format",
                        suggestion="Use format like FL-01, SC-123, etc.",
                        provided_value=asset_id,
                    )
                )

        # Equipment status validation
        if "status" in arguments:
            status = arguments["status"]
            valid_statuses = self.business_rules["equipment_status"]["valid_values"]
            if status not in valid_statuses:
                issues.append(
                    ValidationIssue(
                        parameter="status",
                        level=ValidationLevel.ERROR,
                        message=f"Invalid equipment status '{status}'",
                        suggestion=f"Valid statuses are: {', '.join(valid_statuses)}",
                        provided_value=status,
                    )
                )

        return issues

    async def _validate_task_business_rules(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> List[ValidationIssue]:
        """Validate task-specific business rules."""
        issues = []

        # Task ID format validation
        if "task_id" in arguments:
            task_id = arguments["task_id"]
            if not self.validation_patterns[ParameterType.TASK_ID.value].match(task_id):
                issues.append(
                    ValidationIssue(
                        parameter="task_id",
                        level=ValidationLevel.WARNING,
                        message=f"Task ID '{task_id}' doesn't follow standard format",
                        suggestion="Use format like T-123, T-123456, etc.",
                        provided_value=task_id,
                    )
                )

        return issues

    async def _validate_safety_business_rules(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> List[ValidationIssue]:
        """Validate safety-specific business rules."""
        issues = []

        # Priority validation for safety tools
        if "priority" in arguments:
            priority = arguments["priority"]
            valid_priorities = self.business_rules["priority"]["valid_values"]
            if priority not in valid_priorities:
                issues.append(
                    ValidationIssue(
                        parameter="priority",
                        level=ValidationLevel.ERROR,
                        message=f"Invalid priority '{priority}'",
                        suggestion=f"Valid priorities are: {', '.join(valid_priorities)}",
                        provided_value=priority,
                    )
                )

        return issues

    def get_validation_summary(self, result: ValidationResult) -> str:
        """Generate a human-readable validation summary."""
        if result.is_valid:
            if result.warnings:
                return f"✅ Validation passed with {len(result.warnings)} warnings"
            else:
                return "✅ Validation passed"
        else:
            return f"❌ Validation failed with {len(result.errors)} errors"

    def get_improvement_suggestions(self, result: ValidationResult) -> List[str]:
        """Generate improvement suggestions based on validation results."""
        suggestions = []

        # Add suggestions from validation issues
        suggestions.extend(result.suggestions)

        # Add general suggestions based on errors
        if result.errors:
            suggestions.append("Review and fix validation errors")

        if len(result.warnings) > 2:
            suggestions.append("Address validation warnings to improve data quality")

        # Remove duplicates and limit
        unique_suggestions = list(dict.fromkeys(suggestions))
        return unique_suggestions[:5]


# Global instance
_parameter_validator: Optional[MCPParameterValidator] = None


async def get_parameter_validator() -> MCPParameterValidator:
    """Get the global parameter validator instance."""
    global _parameter_validator
    if _parameter_validator is None:
        _parameter_validator = MCPParameterValidator()
    return _parameter_validator
