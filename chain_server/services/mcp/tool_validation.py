"""
Validation and Error Handling for MCP Tool Execution

This module provides comprehensive validation and error handling capabilities
for MCP tool execution, ensuring robust and reliable tool operations.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Union, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json
import traceback
from functools import wraps

from .tool_discovery import ToolDiscoveryService, DiscoveredTool
from .tool_binding import ToolBindingService, ExecutionResult, ExecutionContext

logger = logging.getLogger(__name__)


class ValidationLevel(Enum):
    """Validation levels."""

    BASIC = "basic"
    STANDARD = "standard"
    STRICT = "strict"
    PARANOID = "paranoid"


class ErrorSeverity(Enum):
    """Error severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories."""

    VALIDATION = "validation"
    EXECUTION = "execution"
    TIMEOUT = "timeout"
    PERMISSION = "permission"
    RESOURCE = "resource"
    NETWORK = "network"
    DATA = "data"
    SYSTEM = "system"


@dataclass
class ValidationResult:
    """Result of tool validation."""

    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    validation_level: ValidationLevel = ValidationLevel.STANDARD
    validated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ErrorInfo:
    """Information about an error."""

    error_id: str
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    stack_trace: Optional[str] = None
    occurred_at: datetime = field(default_factory=datetime.utcnow)
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ErrorHandlingResult:
    """Result of error handling."""

    handled: bool
    recovery_action: Optional[str] = None
    fallback_result: Optional[Any] = None
    retry_recommended: bool = False
    retry_delay: float = 0.0
    error_info: Optional[ErrorInfo] = None


@dataclass
class ValidationRule:
    """Validation rule definition."""

    rule_id: str
    name: str
    description: str
    validator: Callable
    error_message: str
    warning_message: Optional[str] = None
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
    enabled: bool = True


class ToolValidationService:
    """
    Service for validating MCP tool execution.

    This service provides:
    - Input validation for tool parameters
    - Tool capability validation
    - Execution context validation
    - Result validation and verification
    - Performance and resource validation
    """

    def __init__(self, tool_discovery: ToolDiscoveryService):
        self.tool_discovery = tool_discovery
        self.validation_rules: Dict[str, ValidationRule] = {}
        self.validation_history: List[Dict[str, Any]] = []
        self._setup_default_rules()

    def _setup_default_rules(self) -> None:
        """Setup default validation rules."""
        # Parameter validation rules
        self.add_validation_rule(
            ValidationRule(
                rule_id="param_required",
                name="Required Parameters",
                description="Validate that all required parameters are provided",
                validator=self._validate_required_parameters,
                error_message="Missing required parameters",
                severity=ErrorSeverity.HIGH,
            )
        )

        self.add_validation_rule(
            ValidationRule(
                rule_id="param_types",
                name="Parameter Types",
                description="Validate parameter types match expected types",
                validator=self._validate_parameter_types,
                error_message="Invalid parameter types",
                severity=ErrorSeverity.MEDIUM,
            )
        )

        self.add_validation_rule(
            ValidationRule(
                rule_id="param_values",
                name="Parameter Values",
                description="Validate parameter values are within acceptable ranges",
                validator=self._validate_parameter_values,
                error_message="Invalid parameter values",
                severity=ErrorSeverity.MEDIUM,
            )
        )

        # Tool capability validation rules
        self.add_validation_rule(
            ValidationRule(
                rule_id="tool_availability",
                name="Tool Availability",
                description="Validate that the tool is available and accessible",
                validator=self._validate_tool_availability,
                error_message="Tool is not available",
                severity=ErrorSeverity.CRITICAL,
            )
        )

        self.add_validation_rule(
            ValidationRule(
                rule_id="tool_permissions",
                name="Tool Permissions",
                description="Validate that the tool has required permissions",
                validator=self._validate_tool_permissions,
                error_message="Insufficient permissions for tool execution",
                severity=ErrorSeverity.HIGH,
            )
        )

        # Execution context validation rules
        self.add_validation_rule(
            ValidationRule(
                rule_id="execution_context",
                name="Execution Context",
                description="Validate execution context is valid",
                validator=self._validate_execution_context,
                error_message="Invalid execution context",
                severity=ErrorSeverity.MEDIUM,
            )
        )

        self.add_validation_rule(
            ValidationRule(
                rule_id="resource_limits",
                name="Resource Limits",
                description="Validate resource usage is within limits",
                validator=self._validate_resource_limits,
                error_message="Resource usage exceeds limits",
                severity=ErrorSeverity.HIGH,
            )
        )

    def add_validation_rule(self, rule: ValidationRule) -> None:
        """Add a validation rule."""
        self.validation_rules[rule.rule_id] = rule

    def remove_validation_rule(self, rule_id: str) -> None:
        """Remove a validation rule."""
        if rule_id in self.validation_rules:
            del self.validation_rules[rule_id]

    async def validate_tool_execution(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        context: ExecutionContext,
        validation_level: ValidationLevel = ValidationLevel.STANDARD,
    ) -> ValidationResult:
        """
        Validate tool execution before running.

        Args:
            tool_id: ID of the tool to validate
            arguments: Tool arguments
            context: Execution context
            validation_level: Validation level to apply

        Returns:
            Validation result
        """
        try:
            # Get tool information
            tool = self.tool_discovery.discovered_tools.get(tool_id)
            if not tool:
                return ValidationResult(
                    is_valid=False,
                    errors=[f"Tool {tool_id} not found"],
                    validation_level=validation_level,
                )

            # Run validation rules
            errors = []
            warnings = []
            suggestions = []

            for rule_id, rule in self.validation_rules.items():
                if not rule.enabled:
                    continue

                try:
                    rule_result = await rule.validator(tool, arguments, context)

                    if not rule_result["valid"]:
                        if rule.severity in [
                            ErrorSeverity.HIGH,
                            ErrorSeverity.CRITICAL,
                        ]:
                            errors.append(rule.error_message)
                        else:
                            warnings.append(rule.warning_message or rule.error_message)

                    if rule_result.get("suggestions"):
                        suggestions.extend(rule_result["suggestions"])

                except Exception as e:
                    logger.error(f"Error in validation rule {rule_id}: {e}")
                    errors.append(f"Validation rule {rule_id} failed: {str(e)}")

            # Determine overall validity
            is_valid = len(errors) == 0

            # Create validation result
            result = ValidationResult(
                is_valid=is_valid,
                errors=errors,
                warnings=warnings,
                suggestions=suggestions,
                validation_level=validation_level,
            )

            # Record validation
            self._record_validation(tool_id, arguments, context, result)

            return result

        except Exception as e:
            logger.error(f"Error validating tool execution: {e}")
            return ValidationResult(
                is_valid=False,
                errors=[f"Validation failed: {str(e)}"],
                validation_level=validation_level,
            )

    async def _validate_required_parameters(
        self, tool: DiscoveredTool, arguments: Dict[str, Any], context: ExecutionContext
    ) -> Dict[str, Any]:
        """Validate required parameters are provided."""
        missing_params = []

        for param_name, param_schema in tool.parameters.items():
            if param_schema.get("required", False) and param_name not in arguments:
                missing_params.append(param_name)

        return {
            "valid": len(missing_params) == 0,
            "suggestions": [
                f"Provide required parameter: {param}" for param in missing_params
            ],
        }

    async def _validate_parameter_types(
        self, tool: DiscoveredTool, arguments: Dict[str, Any], context: ExecutionContext
    ) -> Dict[str, Any]:
        """Validate parameter types."""
        type_errors = []

        for param_name, param_value in arguments.items():
            if param_name in tool.parameters:
                expected_type = tool.parameters[param_name].get("type", "string")
                actual_type = type(param_value).__name__

                if not self._is_type_compatible(actual_type, expected_type):
                    type_errors.append(
                        f"{param_name}: expected {expected_type}, got {actual_type}"
                    )

        return {"valid": len(type_errors) == 0, "suggestions": type_errors}

    def _is_type_compatible(self, actual_type: str, expected_type: str) -> bool:
        """Check if actual type is compatible with expected type."""
        type_mapping = {
            "string": ["str"],
            "integer": ["int"],
            "number": ["int", "float"],
            "boolean": ["bool"],
            "array": ["list"],
            "object": ["dict"],
        }

        expected_types = type_mapping.get(expected_type, [expected_type])
        return actual_type in expected_types

    async def _validate_parameter_values(
        self, tool: DiscoveredTool, arguments: Dict[str, Any], context: ExecutionContext
    ) -> Dict[str, Any]:
        """Validate parameter values."""
        value_errors = []

        for param_name, param_value in arguments.items():
            if param_name in tool.parameters:
                param_schema = tool.parameters[param_name]

                # Check minimum/maximum values
                if "minimum" in param_schema and param_value < param_schema["minimum"]:
                    value_errors.append(
                        f"{param_name}: value {param_value} below minimum {param_schema['minimum']}"
                    )

                if "maximum" in param_schema and param_value > param_schema["maximum"]:
                    value_errors.append(
                        f"{param_name}: value {param_value} above maximum {param_schema['maximum']}"
                    )

                # Check enum values
                if "enum" in param_schema and param_value not in param_schema["enum"]:
                    value_errors.append(
                        f"{param_name}: value {param_value} not in allowed values {param_schema['enum']}"
                    )

        return {"valid": len(value_errors) == 0, "suggestions": value_errors}

    async def _validate_tool_availability(
        self, tool: DiscoveredTool, arguments: Dict[str, Any], context: ExecutionContext
    ) -> Dict[str, Any]:
        """Validate tool availability."""
        # Check if tool is in discovered tools
        if tool.tool_id not in self.tool_discovery.discovered_tools:
            return {"valid": False, "suggestions": ["Tool is not available"]}

        # Check tool status
        if tool.status.value == "unavailable":
            return {"valid": False, "suggestions": ["Tool is currently unavailable"]}

        return {"valid": True}

    async def _validate_tool_permissions(
        self, tool: DiscoveredTool, arguments: Dict[str, Any], context: ExecutionContext
    ) -> Dict[str, Any]:
        """Validate tool permissions."""
        # This would check actual permissions
        # For now, assume all tools are accessible
        return {"valid": True}

    async def _validate_execution_context(
        self, tool: DiscoveredTool, arguments: Dict[str, Any], context: ExecutionContext
    ) -> Dict[str, Any]:
        """Validate execution context."""
        context_errors = []

        # Check session validity
        if not context.session_id:
            context_errors.append("Invalid session ID")

        # Check agent validity
        if not context.agent_id:
            context_errors.append("Invalid agent ID")

        # Check timeout validity
        if context.timeout <= 0:
            context_errors.append("Invalid timeout value")

        return {"valid": len(context_errors) == 0, "suggestions": context_errors}

    async def _validate_resource_limits(
        self, tool: DiscoveredTool, arguments: Dict[str, Any], context: ExecutionContext
    ) -> Dict[str, Any]:
        """Validate resource limits."""
        # This would check actual resource usage
        # For now, assume resources are available
        return {"valid": True}

    def _record_validation(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        context: ExecutionContext,
        result: ValidationResult,
    ) -> None:
        """Record validation result."""
        self.validation_history.append(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "tool_id": tool_id,
                "arguments": arguments,
                "context": context,
                "result": result,
            }
        )

        # Keep only last 1000 validations
        if len(self.validation_history) > 1000:
            self.validation_history = self.validation_history[-1000:]


class ErrorHandlingService:
    """
    Service for handling errors in MCP tool execution.

    This service provides:
    - Error detection and classification
    - Error recovery strategies
    - Fallback mechanisms
    - Error reporting and logging
    - Retry logic and backoff strategies
    """

    def __init__(self, tool_discovery: ToolDiscoveryService):
        self.tool_discovery = tool_discovery
        self.error_handlers: Dict[ErrorCategory, Callable] = {}
        self.error_history: List[ErrorInfo] = []
        self.retry_strategies: Dict[ErrorCategory, Dict[str, Any]] = {}
        self._setup_default_handlers()
        self._setup_retry_strategies()

    def _setup_default_handlers(self) -> None:
        """Setup default error handlers."""
        self.error_handlers[ErrorCategory.VALIDATION] = self._handle_validation_error
        self.error_handlers[ErrorCategory.EXECUTION] = self._handle_execution_error
        self.error_handlers[ErrorCategory.TIMEOUT] = self._handle_timeout_error
        self.error_handlers[ErrorCategory.PERMISSION] = self._handle_permission_error
        self.error_handlers[ErrorCategory.RESOURCE] = self._handle_resource_error
        self.error_handlers[ErrorCategory.NETWORK] = self._handle_network_error
        self.error_handlers[ErrorCategory.DATA] = self._handle_data_error
        self.error_handlers[ErrorCategory.SYSTEM] = self._handle_system_error

    def _setup_retry_strategies(self) -> None:
        """Setup retry strategies for different error categories."""
        self.retry_strategies = {
            ErrorCategory.VALIDATION: {"max_retries": 0, "backoff_factor": 1.0},
            ErrorCategory.EXECUTION: {"max_retries": 3, "backoff_factor": 2.0},
            ErrorCategory.TIMEOUT: {"max_retries": 2, "backoff_factor": 1.5},
            ErrorCategory.PERMISSION: {"max_retries": 0, "backoff_factor": 1.0},
            ErrorCategory.RESOURCE: {"max_retries": 2, "backoff_factor": 2.0},
            ErrorCategory.NETWORK: {"max_retries": 5, "backoff_factor": 2.0},
            ErrorCategory.DATA: {"max_retries": 1, "backoff_factor": 1.0},
            ErrorCategory.SYSTEM: {"max_retries": 1, "backoff_factor": 1.0},
        }

    async def handle_error(
        self,
        error: Exception,
        tool_id: str,
        context: ExecutionContext,
        execution_result: Optional[ExecutionResult] = None,
    ) -> ErrorHandlingResult:
        """
        Handle an error in tool execution.

        Args:
            error: The error that occurred
            tool_id: ID of the tool that failed
            context: Execution context
            execution_result: Execution result if available

        Returns:
            Error handling result
        """
        try:
            # Classify error
            error_info = self._classify_error(error, tool_id, context, execution_result)

            # Get error handler
            handler = self.error_handlers.get(error_info.category)
            if not handler:
                handler = self._handle_generic_error

            # Handle error
            result = await handler(error_info, tool_id, context, execution_result)

            # Record error
            self._record_error(error_info)

            return result

        except Exception as e:
            logger.error(f"Error in error handling: {e}")
            return ErrorHandlingResult(
                handled=False,
                error_info=ErrorInfo(
                    error_id="error_handling_failed",
                    category=ErrorCategory.SYSTEM,
                    severity=ErrorSeverity.CRITICAL,
                    message=f"Error handling failed: {str(e)}",
                ),
            )

    def _classify_error(
        self,
        error: Exception,
        tool_id: str,
        context: ExecutionContext,
        execution_result: Optional[ExecutionResult],
    ) -> ErrorInfo:
        """Classify an error."""
        error_message = str(error)
        error_type = type(error).__name__

        # Determine category and severity
        if isinstance(error, ValueError):
            category = ErrorCategory.VALIDATION
            severity = ErrorSeverity.MEDIUM
        elif isinstance(error, PermissionError):
            category = ErrorCategory.PERMISSION
            severity = ErrorSeverity.HIGH
        elif isinstance(error, TimeoutError) or "timeout" in error_message.lower():
            category = ErrorCategory.TIMEOUT
            severity = ErrorSeverity.MEDIUM
        elif isinstance(error, ConnectionError) or "network" in error_message.lower():
            category = ErrorCategory.NETWORK
            severity = ErrorSeverity.HIGH
        elif isinstance(error, MemoryError) or "resource" in error_message.lower():
            category = ErrorCategory.RESOURCE
            severity = ErrorSeverity.HIGH
        elif isinstance(error, KeyError) or "data" in error_message.lower():
            category = ErrorCategory.DATA
            severity = ErrorSeverity.MEDIUM
        else:
            category = ErrorCategory.SYSTEM
            severity = ErrorSeverity.HIGH

        return ErrorInfo(
            error_id=f"{category.value}_{tool_id}_{datetime.utcnow().timestamp()}",
            category=category,
            severity=severity,
            message=error_message,
            details={"error_type": error_type, "tool_id": tool_id, "context": context},
            stack_trace=traceback.format_exc(),
            context={"execution_result": execution_result},
        )

    async def _handle_validation_error(
        self,
        error_info: ErrorInfo,
        tool_id: str,
        context: ExecutionContext,
        execution_result: Optional[ExecutionResult],
    ) -> ErrorHandlingResult:
        """Handle validation errors."""
        return ErrorHandlingResult(
            handled=True,
            recovery_action="Fix validation errors and retry",
            retry_recommended=False,
            error_info=error_info,
        )

    async def _handle_execution_error(
        self,
        error_info: ErrorInfo,
        tool_id: str,
        context: ExecutionContext,
        execution_result: Optional[ExecutionResult],
    ) -> ErrorHandlingResult:
        """Handle execution errors."""
        return ErrorHandlingResult(
            handled=True,
            recovery_action="Check tool implementation and retry",
            retry_recommended=True,
            retry_delay=1.0,
            error_info=error_info,
        )

    async def _handle_timeout_error(
        self,
        error_info: ErrorInfo,
        tool_id: str,
        context: ExecutionContext,
        execution_result: Optional[ExecutionResult],
    ) -> ErrorHandlingResult:
        """Handle timeout errors."""
        return ErrorHandlingResult(
            handled=True,
            recovery_action="Increase timeout and retry",
            retry_recommended=True,
            retry_delay=2.0,
            error_info=error_info,
        )

    async def _handle_permission_error(
        self,
        error_info: ErrorInfo,
        tool_id: str,
        context: ExecutionContext,
        execution_result: Optional[ExecutionResult],
    ) -> ErrorHandlingResult:
        """Handle permission errors."""
        return ErrorHandlingResult(
            handled=True,
            recovery_action="Check permissions and access rights",
            retry_recommended=False,
            error_info=error_info,
        )

    async def _handle_resource_error(
        self,
        error_info: ErrorInfo,
        tool_id: str,
        context: ExecutionContext,
        execution_result: Optional[ExecutionResult],
    ) -> ErrorHandlingResult:
        """Handle resource errors."""
        return ErrorHandlingResult(
            handled=True,
            recovery_action="Free up resources and retry",
            retry_recommended=True,
            retry_delay=5.0,
            error_info=error_info,
        )

    async def _handle_network_error(
        self,
        error_info: ErrorInfo,
        tool_id: str,
        context: ExecutionContext,
        execution_result: Optional[ExecutionResult],
    ) -> ErrorHandlingResult:
        """Handle network errors."""
        return ErrorHandlingResult(
            handled=True,
            recovery_action="Check network connectivity and retry",
            retry_recommended=True,
            retry_delay=3.0,
            error_info=error_info,
        )

    async def _handle_data_error(
        self,
        error_info: ErrorInfo,
        tool_id: str,
        context: ExecutionContext,
        execution_result: Optional[ExecutionResult],
    ) -> ErrorHandlingResult:
        """Handle data errors."""
        return ErrorHandlingResult(
            handled=True,
            recovery_action="Validate data format and retry",
            retry_recommended=True,
            retry_delay=1.0,
            error_info=error_info,
        )

    async def _handle_system_error(
        self,
        error_info: ErrorInfo,
        tool_id: str,
        context: ExecutionContext,
        execution_result: Optional[ExecutionResult],
    ) -> ErrorHandlingResult:
        """Handle system errors."""
        return ErrorHandlingResult(
            handled=True,
            recovery_action="Check system status and retry",
            retry_recommended=True,
            retry_delay=10.0,
            error_info=error_info,
        )

    async def _handle_generic_error(
        self,
        error_info: ErrorInfo,
        tool_id: str,
        context: ExecutionContext,
        execution_result: Optional[ExecutionResult],
    ) -> ErrorHandlingResult:
        """Handle generic errors."""
        return ErrorHandlingResult(
            handled=True,
            recovery_action="Investigate error and retry if appropriate",
            retry_recommended=True,
            retry_delay=5.0,
            error_info=error_info,
        )

    def _record_error(self, error_info: ErrorInfo) -> None:
        """Record error information."""
        self.error_history.append(error_info)

        # Keep only last 1000 errors
        if len(self.error_history) > 1000:
            self.error_history = self.error_history[-1000:]

    async def get_error_statistics(self) -> Dict[str, Any]:
        """Get error statistics."""
        if not self.error_history:
            return {"total_errors": 0}

        # Count errors by category
        category_counts = {}
        severity_counts = {}

        for error in self.error_history:
            category_counts[error.category.value] = (
                category_counts.get(error.category.value, 0) + 1
            )
            severity_counts[error.severity.value] = (
                severity_counts.get(error.severity.value, 0) + 1
            )

        return {
            "total_errors": len(self.error_history),
            "category_counts": category_counts,
            "severity_counts": severity_counts,
            "recent_errors": len(
                [
                    e
                    for e in self.error_history
                    if (datetime.utcnow() - e.occurred_at).hours < 24
                ]
            ),
        }


def validate_tool_execution(
    validation_level: ValidationLevel = ValidationLevel.STANDARD,
):
    """Decorator for validating tool execution."""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # This would be implemented to validate tool execution
            # before calling the actual function
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def handle_errors(error_category: ErrorCategory = ErrorCategory.SYSTEM):
    """Decorator for handling errors in tool execution."""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # This would be implemented to handle errors
                # using the ErrorHandlingService
                raise

        return wrapper

    return decorator
