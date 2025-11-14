"""
MCP (Model Context Protocol) System for Warehouse Operational Assistant

This package provides MCP integration for the Warehouse Operational Assistant,
enabling tool discovery, execution, and communication between agents and external systems.
"""

from .server import (
    MCPServer,
    MCPTool,
    MCPToolType,
    MCPRequest,
    MCPResponse,
    MCPNotification,
)
from .client import (
    MCPClient,
    MCPConnectionType,
    MCPToolInfo,
    MCPResourceInfo,
    MCPPromptInfo,
)
from .base import (
    MCPAdapter,
    MCPToolBase,
    MCPManager,
    AdapterConfig,
    ToolConfig,
    AdapterType,
    ToolCategory,
)
from .tool_discovery import ToolDiscoveryService, DiscoveredTool, ToolDiscoveryConfig
from .tool_binding import (
    ToolBindingService,
    ToolBinding,
    ExecutionContext,
    ExecutionResult,
    ExecutionPlan,
    BindingStrategy,
    ExecutionMode,
)
from .tool_routing import (
    ToolRoutingService,
    RoutingContext,
    ToolScore,
    RoutingDecision,
    RoutingStrategy,
    QueryComplexity,
)
from .tool_validation import (
    ToolValidationService,
    ErrorHandlingService,
    ValidationResult,
    ErrorInfo,
    ErrorHandlingResult,
    ValidationLevel,
    ErrorSeverity,
    ErrorCategory,
)

__all__ = [
    # Server components
    "MCPServer",
    "MCPTool",
    "MCPToolType",
    "MCPRequest",
    "MCPResponse",
    "MCPNotification",
    # Client components
    "MCPClient",
    "MCPConnectionType",
    "MCPToolInfo",
    "MCPResourceInfo",
    "MCPPromptInfo",
    # Base classes
    "MCPAdapter",
    "MCPToolBase",
    "MCPManager",
    "AdapterConfig",
    "ToolConfig",
    "AdapterType",
    "ToolCategory",
    # Tool Discovery
    "ToolDiscoveryService",
    "DiscoveredTool",
    "ToolDiscoveryConfig",
    # Tool Binding
    "ToolBindingService",
    "ToolBinding",
    "ExecutionContext",
    "ExecutionResult",
    "ExecutionPlan",
    "BindingStrategy",
    "ExecutionMode",
    # Tool Routing
    "ToolRoutingService",
    "RoutingContext",
    "ToolScore",
    "RoutingDecision",
    "RoutingStrategy",
    "QueryComplexity",
    # Tool Validation
    "ToolValidationService",
    "ErrorHandlingService",
    "ValidationResult",
    "ErrorInfo",
    "ErrorHandlingResult",
    "ValidationLevel",
    "ErrorSeverity",
    "ErrorCategory",
]

__version__ = "1.0.0"
__author__ = "Warehouse Operational Assistant Team"
__description__ = "MCP system for warehouse operations management"
