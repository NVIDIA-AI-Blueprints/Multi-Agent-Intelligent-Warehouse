"""
Shared test utilities module for unit tests.

Provides common utility functions for test setup, cleanup, and helpers.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Optional, Callable

logger = logging.getLogger(__name__)


async def cleanup_async_resource(
    resource: Any, 
    close_method: str = "close",
    log_errors: bool = True
) -> bool:
    """
    Safely close async resources.
    
    Args:
        resource: The resource to close
        close_method: Name of the close method to call
        log_errors: Whether to log cleanup errors
        
    Returns:
        True if cleanup succeeded, False otherwise
    """
    if resource is None:
        return True
        
    if not hasattr(resource, close_method):
        return True
    
    try:
        close_func = getattr(resource, close_method)
        if asyncio.iscoroutinefunction(close_func):
            await close_func()
        else:
            close_func()
        return True
    except Exception as e:
        if log_errors:
            logger.warning(f"Error closing resource ({type(resource).__name__}): {e}")
        return False


async def cleanup_multiple_resources(
    resources: list[Any],
    close_method: str = "close",
    log_errors: bool = True
) -> int:
    """
    Cleanup multiple resources.
    
    Args:
        resources: List of resources to close
        close_method: Name of the close method to call
        log_errors: Whether to log cleanup errors
        
    Returns:
        Number of successfully closed resources
    """
    success_count = 0
    for resource in resources:
        if await cleanup_async_resource(resource, close_method, log_errors):
            success_count += 1
    return success_count


def get_test_file_path(filename: str, candidates: Optional[list[str]] = None) -> Optional[Path]:
    """
    Find test file in common locations.
    
    Args:
        filename: Name of the test file to find
        candidates: Optional list of candidate paths to check
        
    Returns:
        Path to the file if found, None otherwise
    """
    from tests.unit.test_config import TEST_DATA_DIR, SAMPLE_DATA_DIR, PROJECT_ROOT
    
    if candidates is None:
        candidates = [
            filename,
            str(TEST_DATA_DIR / filename),
            str(SAMPLE_DATA_DIR / filename),
            str(PROJECT_ROOT / filename),
            str(PROJECT_ROOT / "data" / "sample" / filename),
        ]
    
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return path
    
    return None


def require_env_var(var_name: str, default: Optional[str] = None) -> str:
    """
    Require an environment variable to be set.
    
    Args:
        var_name: Name of the environment variable
        default: Optional default value
        
    Returns:
        Value of the environment variable
        
    Raises:
        ValueError: If variable is not set and no default provided
    """
    import os
    
    value = os.getenv(var_name, default)
    if value is None:
        raise ValueError(
            f"Environment variable {var_name} is required but not set. "
            f"Please set it before running tests."
        )
    return value


def setup_test_logging(level: int = logging.INFO) -> logging.Logger:
    """
    Set up logging for tests.
    
    Args:
        level: Logging level
        
    Returns:
        Configured logger
    """
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


class AsyncContextManager:
    """
    Helper class to create async context managers for resources.
    """
    
    def __init__(self, resource: Any, close_method: str = "close"):
        self.resource = resource
        self.close_method = close_method
    
    async def __aenter__(self):
        return self.resource
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await cleanup_async_resource(self.resource, self.close_method)


def create_test_session_id(prefix: str = "test_session") -> str:
    """
    Create a unique test session ID.
    
    Args:
        prefix: Prefix for the session ID
        
    Returns:
        Unique session ID string
    """
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return f"{prefix}_{timestamp}"

