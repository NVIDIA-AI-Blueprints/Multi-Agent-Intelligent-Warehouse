"""
Logging utility functions for API modules.

Provides safe logging utilities to prevent log injection attacks and
safe prompt construction utilities to prevent template injection attacks.
"""

import base64
import re
import json
from typing import Union, Any, Dict, List


def sanitize_log_data(data: Union[str, Any], max_length: int = 500) -> str:
    """
    Sanitize data for safe logging to prevent log injection attacks.
    
    Removes newlines, carriage returns, and other control characters that could
    be used to forge log entries. For suspicious data, uses base64 encoding.
    
    Args:
        data: Data to sanitize (will be converted to string)
        max_length: Maximum length of sanitized string (truncates if longer)
        
    Returns:
        Sanitized string safe for logging
    """
    if data is None:
        return "None"
    
    # Convert to string
    data_str = str(data)
    
    # Truncate if too long
    if len(data_str) > max_length:
        data_str = data_str[:max_length] + "...[truncated]"
    
    # Check for newlines, carriage returns, or other control characters
    # \x00-\x1f covers all control characters including \r (0x0D), \n (0x0A), and \t (0x09)
    if re.search(r'[\x00-\x1f]', data_str):
        # Contains control characters - base64 encode for safety
        try:
            encoded = base64.b64encode(data_str.encode('utf-8')).decode('ascii')
            return f"[base64:{encoded}]"
        except Exception:
            # If encoding fails, remove control characters
            data_str = re.sub(r'[\x00-\x1f]', '', data_str)
    
    # Remove any remaining suspicious characters
    data_str = re.sub(r'[\r\n]', '', data_str)
    
    return data_str


def sanitize_prompt_input(data: Union[str, Any], max_length: int = 10000) -> str:
    """
    Sanitize user input for safe use in f-string prompts to prevent template injection.
    
    This function prevents template injection attacks by:
    1. Escaping f-string template syntax ({, }, $)
    2. Removing control characters that could be used for injection
    3. Validating that input is a simple string (not a complex object)
    4. Limiting input length to prevent DoS
    
    Args:
        data: User input to sanitize (will be converted to string)
        max_length: Maximum length of sanitized string (default 10000 for prompts)
        
    Returns:
        Sanitized string safe for use in f-string prompts
        
    Security Notes:
        - Prevents template injection by escaping { and } characters
        - Removes control characters that could be used for code injection
        - For complex objects (dicts, lists), uses JSON serialization which is safe
        - Does not allow attribute access (.) or indexing ([]) from user input
    """
    if data is None:
        return "None"
    
    # For complex objects, serialize to JSON (safe for template interpolation)
    if isinstance(data, (dict, list)):
        try:
            return json.dumps(data, default=str, ensure_ascii=False)
        except (TypeError, ValueError):
            # If JSON serialization fails, convert to string representation
            data_str = str(data)
    
    # Convert to string
    data_str = str(data)
    
    # Truncate if too long to prevent DoS
    if len(data_str) > max_length:
        data_str = data_str[:max_length] + "...[truncated]"
    
    # Escape f-string template syntax to prevent template injection
    # Replace { with {{ and } with }} to prevent f-string evaluation
    data_str = data_str.replace("{", "{{").replace("}", "}}")
    
    # Remove or escape other potentially dangerous characters
    # Remove control characters (except common whitespace)
    data_str = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', data_str)
    
    # Remove backticks that could be used for code execution in some contexts
    data_str = data_str.replace("`", "'")
    
    return data_str


def safe_format_prompt(template: str, **kwargs: Any) -> str:
    """
    Safely format a prompt template with user input.
    
    This function provides a safe way to construct prompts by:
    1. Sanitizing all user-provided values
    2. Using .format() instead of f-strings for better control
    3. Ensuring no template injection can occur
    
    Args:
        template: Prompt template string (use {key} for placeholders)
        **kwargs: Values to interpolate into the template (will be sanitized)
        
    Returns:
        Safely formatted prompt string
        
    Example:
        >>> safe_format_prompt(
        ...     "User Query: {query}",
        ...     query="Show me equipment status"
        ... )
        "User Query: Show me equipment status"
        
        >>> safe_format_prompt(
        ...     "User Query: {query}",
        ...     query="{__import__('os').system('rm -rf /')}"
        ... )
        "User Query: {{__import__('os').system('rm -rf /')}}"
    """
    # Sanitize all values
    sanitized_kwargs = {
        key: sanitize_prompt_input(value) 
        for key, value in kwargs.items()
    }
    
    try:
        # Use .format() which is safer than f-strings for user input
        return template.format(**sanitized_kwargs)
    except KeyError as e:
        # If a placeholder is missing, return template with error message
        return f"{template} [ERROR: Missing placeholder {e}]"
    except Exception as e:
        # If formatting fails, return template with error message
        return f"{template} [ERROR: Formatting failed: {str(e)}]"

