"""
Error Handler Utilities

Provides secure error handling that prevents information disclosure.
"""

import logging
import traceback
from typing import Optional, Dict, Any
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import os

logger = logging.getLogger(__name__)

# Environment variable to control error detail level
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
DEBUG_MODE = ENVIRONMENT == "development"


def sanitize_error_message(error: Exception, operation: str = "Operation") -> str:
    """
    Sanitize error messages to prevent information disclosure.
    
    In production, returns generic error messages.
    In development, returns more detailed error messages.
    
    Args:
        error: The exception that occurred
        operation: Description of the operation that failed
        
    Returns:
        Sanitized error message safe for user consumption
    """
    error_type = type(error).__name__
    error_str = str(error)
    
    # Always log full error details server-side
    logger.error(f"{operation} failed: {error_type}: {error_str}", exc_info=True)
    
    # In production, return generic messages
    if not DEBUG_MODE:
        # Map specific error types to generic messages
        if isinstance(error, ValueError):
            return f"{operation} failed: Invalid input provided."
        elif isinstance(error, KeyError):
            return f"{operation} failed: Required information is missing."
        elif isinstance(error, PermissionError):
            return f"{operation} failed: Access denied."
        elif isinstance(error, ConnectionError):
            # Check for specific LLM service errors
            if "llm" in error_str.lower() or "language processing" in error_str.lower():
                return f"{operation} failed: Language processing service is unavailable. Please try again later."
            elif "endpoint not found" in error_str.lower() or "404" in error_str.lower():
                return f"{operation} failed: Service endpoint not found. Please check system configuration."
            else:
                return f"{operation} failed: Service temporarily unavailable. Please try again later."
        elif isinstance(error, TimeoutError):
            return f"{operation} failed: Request timed out. Please try again."
        elif "database" in error_str.lower() or "sql" in error_str.lower():
            return f"{operation} failed: Data service error. Please try again later."
        elif "authentication" in error_str.lower() or "authorization" in error_str.lower() or "401" in error_str or "403" in error_str:
            return f"{operation} failed: Authentication error. Please check your credentials."
        elif "validation" in error_str.lower():
            return f"{operation} failed: Invalid request format. Please check your input."
        elif "404" in error_str or "not found" in error_str.lower():
            return f"{operation} failed: Service endpoint not found. Please check system configuration."
        elif "rate" in error_str.lower() and "limit" in error_str.lower():
            return f"{operation} failed: Service is currently busy. Please try again in a moment."
        else:
            # Generic fallback for unknown errors
            return f"{operation} failed. Please try again or contact support if the issue persists."
    
    # In development, return more detailed messages
    return f"{operation} failed: {error_str}"


def create_error_response(
    status_code: int,
    message: str,
    error_type: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    """
    Create a standardized error response.
    
    Args:
        status_code: HTTP status code
        message: User-friendly error message
        error_type: Type of error (optional)
        details: Additional error details (only in development)
        
    Returns:
        JSONResponse with error information
    """
    error_response = {
        "error": True,
        "message": message,
        "status_code": status_code,
    }
    
    # Only include error type and details in development
    if DEBUG_MODE:
        if error_type:
            error_response["error_type"] = error_type
        if details:
            error_response["details"] = details
    
    return JSONResponse(
        status_code=status_code,
        content=error_response,
    )


async def handle_validation_error(
    request, exc: RequestValidationError
) -> JSONResponse:
    """
    Handle Pydantic validation errors securely.
    
    Args:
        request: FastAPI request object
        exc: Validation error exception
        
    Returns:
        JSONResponse with validation error details
    """
    # Log full validation errors server-side
    logger.warning(f"Validation error: {exc.errors()}")
    
    # In production, return generic message
    if not DEBUG_MODE:
        return create_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            message="Invalid request format. Please check your input and try again.",
        )
    
    # In development, return detailed validation errors
    return create_error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        message="Validation error",
        error_type="ValidationError",
        details={"errors": exc.errors()},
    )


async def handle_http_exception(request, exc: HTTPException) -> JSONResponse:
    """
    Handle HTTP exceptions securely.
    
    Args:
        request: FastAPI request object
        exc: HTTP exception
        
    Returns:
        JSONResponse with error information
    """
    # Log HTTP exceptions
    logger.warning(f"HTTP {exc.status_code}: {exc.detail}")
    
    # Sanitize error message if needed
    message = exc.detail
    if not DEBUG_MODE and exc.status_code >= 500:
        # For 5xx errors in production, use generic message
        message = "An internal server error occurred. Please try again later."
    
    return create_error_response(
        status_code=exc.status_code,
        message=message,
        error_type=type(exc).__name__ if DEBUG_MODE else None,
    )


async def handle_generic_exception(request, exc: Exception) -> JSONResponse:
    """
    Handle generic exceptions securely.
    
    Args:
        request: FastAPI request object
        exc: Generic exception
        
    Returns:
        JSONResponse with error information
    """
    # Sanitize error message
    message = sanitize_error_message(exc, "Request processing")
    
    return create_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message=message,
        error_type=type(exc).__name__ if DEBUG_MODE else None,
    )

