"""
Security utilities for MCP tool discovery and execution.

This module provides security checks and validation to prevent unauthorized
code execution and ensure only safe tools are registered and executed.
"""

import logging
import re
from typing import List, Set, Optional, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


class SecurityViolationError(Exception):
    """Raised when a security violation is detected."""

    pass


class ToolSecurityLevel(Enum):
    """Security levels for tools."""

    SAFE = "safe"  # Safe to execute in production
    RESTRICTED = "restricted"  # Requires explicit opt-in
    BLOCKED = "blocked"  # Never allowed


# Blocked tool patterns that indicate code execution capabilities
BLOCKED_TOOL_PATTERNS: List[str] = [
    # Python REPL and code execution
    r"python.*repl",
    r"python.*exec",
    r"python.*eval",
    r"python.*code",
    r"repl.*python",
    r"exec.*python",
    r"eval.*python",
    r"code.*exec",
    r"code.*eval",
    # PAL Chain (Program-Aided Language)
    r"pal.*chain",
    r"palchain",
    r"program.*aid",
    # Code execution patterns
    r"execute.*code",
    r"run.*code",
    r"exec.*code",
    r"eval.*code",
    r"compile.*code",
    r"interpret.*code",
    # Shell execution
    r"shell.*exec",
    r"bash.*exec",
    r"sh.*exec",
    r"command.*exec",
    r"system.*exec",
    # Dangerous imports
    r"__import__",
    r"importlib",
    r"subprocess",
    r"os\.system",
    r"os\.popen",
    r"eval\(",
    r"exec\(",
    r"compile\(",
    # LangChain Experimental components
    r"langchain.*experimental",
    r"experimental.*python",
    r"sympy.*sympify",
    r"vector.*sql.*chain",
]


# Blocked tool names (exact matches)
BLOCKED_TOOL_NAMES: Set[str] = {
    "python_repl",
    "python_repl_tool",
    "python_exec",
    "python_eval",
    "pal_chain",
    "palchain",
    "code_executor",
    "code_runner",
    "shell_executor",
    "command_executor",
    "python_interpreter",
    "code_interpreter",
}


# Blocked capabilities that indicate code execution
BLOCKED_CAPABILITIES: Set[str] = {
    "code_execution",
    "python_execution",
    "code_evaluation",
    "shell_execution",
    "command_execution",
    "program_execution",
    "script_execution",
    "repl_access",
    "python_repl",
    "code_interpreter",
}


# Blocked parameter names that might indicate code execution
BLOCKED_PARAMETER_NAMES: Set[str] = {
    "code",
    "python_code",
    "script",
    "command",
    "exec_code",
    "eval_code",
    "compile_code",
    "repl_input",
    "python_input",
}

# Blocked path patterns for directory traversal
PATH_TRAVERSAL_PATTERNS: List[str] = [
    r"\.\./",  # Directory traversal
    r"\.\.\\",  # Windows directory traversal
    r"\.\.",  # Any parent directory reference
    r"^/",  # Absolute paths (Unix)
    r"^[A-Za-z]:",  # Absolute paths (Windows drive letters)
    r"^\\\\",  # UNC paths (Windows network)
]


def validate_chain_path(path: str, allow_lc_hub: bool = False) -> tuple[bool, Optional[str]]:
    """
    Validate a LangChain Hub path to prevent directory traversal attacks.
    
    This function prevents CVE-2024-28088 (directory traversal in load_chain).
    
    Args:
        path: Path to validate (e.g., "lc://chains/my_chain" or user input)
        allow_lc_hub: If True, only allow lc:// hub paths
        
    Returns:
        Tuple of (is_valid: bool, reason: Optional[str])
    """
    if not path or not isinstance(path, str):
        return False, "Path must be a non-empty string"
    
    # Check for path traversal patterns
    for pattern in PATH_TRAVERSAL_PATTERNS:
        if re.search(pattern, path):
            return False, f"Path contains directory traversal pattern: {pattern}"
    
    # If allowing only LangChain Hub paths, validate format
    if allow_lc_hub:
        if not path.startswith("lc://"):
            return False, "Only lc:// hub paths are allowed"
        
        # Extract path after lc://
        hub_path = path[5:]  # Remove "lc://" prefix
        
        # Validate hub path format (should be like "chains/name" or "prompts/name")
        if not re.match(r"^[a-zA-Z0-9_-]+/[a-zA-Z0-9_/-]+$", hub_path):
            return False, "Invalid hub path format"
        
        # Additional check: no double slashes or traversal
        if "//" in hub_path or ".." in hub_path:
            return False, "Path contains invalid sequences"
    
    return True, None


def safe_load_chain_path(user_input: str, allowed_chains: Optional[Dict[str, str]] = None) -> str:
    """
    Safely convert user input to a LangChain Hub chain path using allowlist.
    
    This function implements defense-in-depth for CVE-2024-28088 by using
    an allowlist mapping instead of directly using user input.
    
    Args:
        user_input: User-provided chain name
        allowed_chains: Dictionary mapping user-friendly names to hub paths
        
    Returns:
        Validated hub path
        
    Raises:
        SecurityViolationError: If user_input is not in allowlist or path is invalid
    """
    if allowed_chains is None:
        allowed_chains = {}
    
    # Check allowlist first
    if user_input not in allowed_chains:
        raise SecurityViolationError(
            f"Chain '{user_input}' is not in the allowed list. "
            f"Allowed chains: {list(allowed_chains.keys())}"
        )
    
    hub_path = allowed_chains[user_input]
    
    # Validate the hub path
    is_valid, reason = validate_chain_path(hub_path, allow_lc_hub=True)
    if not is_valid:
        raise SecurityViolationError(f"Invalid hub path: {reason}")
    
    return hub_path


def is_tool_blocked(
    tool_name: str,
    tool_description: str = "",
    tool_capabilities: Optional[List[str]] = None,
    tool_parameters: Optional[Dict[str, Any]] = None,
) -> tuple[bool, Optional[str]]:
    """
    Check if a tool should be blocked based on security policies.
    
    Args:
        tool_name: Name of the tool
        tool_description: Description of the tool
        tool_capabilities: List of tool capabilities
        tool_parameters: Dictionary of tool parameters
        
    Returns:
        Tuple of (is_blocked: bool, reason: Optional[str])
    """
    tool_name_lower = tool_name.lower()
    description_lower = tool_description.lower()
    
    # Check exact name matches
    if tool_name_lower in BLOCKED_TOOL_NAMES:
        return True, f"Tool name '{tool_name}' is in blocked list"
    
    # Check pattern matches in name
    for pattern in BLOCKED_TOOL_PATTERNS:
        if re.search(pattern, tool_name_lower, re.IGNORECASE):
            return True, f"Tool name '{tool_name}' matches blocked pattern: {pattern}"
    
    # Check pattern matches in description
    for pattern in BLOCKED_TOOL_PATTERNS:
        if re.search(pattern, description_lower, re.IGNORECASE):
            return True, f"Tool description matches blocked pattern: {pattern}"
    
    # Check capabilities
    if tool_capabilities:
        for capability in tool_capabilities:
            capability_lower = capability.lower()
            if capability_lower in BLOCKED_CAPABILITIES:
                return True, f"Tool has blocked capability: {capability}"
            
            # Check capability patterns
            for pattern in BLOCKED_TOOL_PATTERNS:
                if re.search(pattern, capability_lower, re.IGNORECASE):
                    return True, f"Tool capability '{capability}' matches blocked pattern: {pattern}"
    
    # Check parameter names
    if tool_parameters:
        for param_name in tool_parameters.keys():
            param_lower = param_name.lower()
            if param_lower in BLOCKED_PARAMETER_NAMES:
                return True, f"Tool has blocked parameter: {param_name}"
            
            # Check parameter name patterns
            for pattern in BLOCKED_TOOL_PATTERNS:
                if re.search(pattern, param_lower, re.IGNORECASE):
                    return True, f"Tool parameter '{param_name}' matches blocked pattern: {pattern}"
    
    return False, None


def validate_tool_security(
    tool_name: str,
    tool_description: str = "",
    tool_capabilities: Optional[List[str]] = None,
    tool_parameters: Optional[Dict[str, Any]] = None,
    raise_on_violation: bool = True,
) -> bool:
    """
    Validate tool security and raise exception if blocked.
    
    Args:
        tool_name: Name of the tool
        tool_description: Description of the tool
        tool_capabilities: List of tool capabilities
        tool_parameters: Dictionary of tool parameters
        raise_on_violation: Whether to raise exception on violation
        
    Returns:
        True if tool is safe, False if blocked
        
    Raises:
        SecurityViolationError: If tool is blocked and raise_on_violation is True
    """
    is_blocked, reason = is_tool_blocked(
        tool_name, tool_description, tool_capabilities, tool_parameters
    )
    
    if is_blocked:
        error_msg = f"Security violation: Tool '{tool_name}' is blocked. Reason: {reason}"
        logger.error(error_msg)
        
        if raise_on_violation:
            raise SecurityViolationError(error_msg)
        
        return False
    
    return True


def get_security_level(
    tool_name: str,
    tool_description: str = "",
    tool_capabilities: Optional[List[str]] = None,
) -> ToolSecurityLevel:
    """
    Determine the security level of a tool.
    
    Args:
        tool_name: Name of the tool
        tool_description: Description of the tool
        tool_capabilities: List of tool capabilities
        
    Returns:
        ToolSecurityLevel enum value
    """
    is_blocked, _ = is_tool_blocked(tool_name, tool_description, tool_capabilities)
    
    if is_blocked:
        return ToolSecurityLevel.BLOCKED
    
    # Check for restricted patterns (tools that need explicit opt-in)
    restricted_patterns = [
        r"file.*write",
        r"file.*delete",
        r"database.*write",
        r"database.*delete",
        r"network.*request",
        r"http.*request",
        r"api.*call",
    ]
    
    tool_name_lower = tool_name.lower()
    description_lower = tool_description.lower()
    
    for pattern in restricted_patterns:
        if re.search(pattern, tool_name_lower, re.IGNORECASE) or re.search(
            pattern, description_lower, re.IGNORECASE
        ):
            return ToolSecurityLevel.RESTRICTED
    
    return ToolSecurityLevel.SAFE


def log_security_event(
    event_type: str,
    tool_name: str,
    reason: str,
    additional_info: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Log a security event for audit purposes.
    
    Args:
        event_type: Type of security event (e.g., "tool_blocked", "tool_registered")
        tool_name: Name of the tool
        reason: Reason for the event
        additional_info: Additional information to log
    """
    log_data = {
        "event_type": event_type,
        "tool_name": tool_name,
        "reason": reason,
        "timestamp": str(logging.Formatter().formatTime(logging.LogRecord(
            name="", level=0, pathname="", lineno=0, msg="", args=(), exc_info=None
        ))),
    }
    
    if additional_info:
        log_data.update(additional_info)
    
    logger.warning(f"SECURITY EVENT: {log_data}")

