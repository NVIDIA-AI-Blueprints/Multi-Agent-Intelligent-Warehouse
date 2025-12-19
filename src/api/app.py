from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from fastapi.exceptions import RequestValidationError
import time
import logging
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
from src.api.routers.health import router as health_router
from src.api.routers.chat import router as chat_router
from src.api.routers.equipment import router as equipment_router
from src.api.routers.operations import router as operations_router
from src.api.routers.safety import router as safety_router
from src.api.routers.auth import router as auth_router
from src.api.routers.wms import router as wms_router
from src.api.routers.iot import router as iot_router
from src.api.routers.erp import router as erp_router
from src.api.routers.scanning import router as scanning_router
from src.api.routers.attendance import router as attendance_router
from src.api.routers.reasoning import router as reasoning_router
from src.api.routers.migration import router as migration_router
from src.api.routers.mcp import router as mcp_router
from src.api.routers.document import router as document_router
from src.api.routers.inventory import router as inventory_router
from src.api.routers.advanced_forecasting import router as forecasting_router
from src.api.routers.training import router as training_router
from src.api.services.monitoring.metrics import (
    record_request_metrics,
    get_metrics_response,
)
from src.api.middleware.security_headers import SecurityHeadersMiddleware
from src.api.services.security.rate_limiter import get_rate_limiter
from src.api.utils.error_handler import (
    handle_validation_error,
    handle_http_exception,
    handle_generic_exception,
)
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown."""
    # Startup
    logger.info("Starting Warehouse Operational Assistant...")
    
    # Initialize rate limiter (will be initialized on first use if this fails)
    try:
        rate_limiter = await get_rate_limiter()
        logger.info("✅ Rate limiter initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize rate limiter during startup: {e}")
        logger.info("Rate limiter will be initialized on first request")
    
    # Start alert checker for performance monitoring
    try:
        from src.api.services.monitoring.performance_monitor import get_performance_monitor
        from src.api.services.monitoring.alert_checker import get_alert_checker
        
        performance_monitor = get_performance_monitor()
        alert_checker = get_alert_checker(performance_monitor)
        await alert_checker.start()
        logger.info("✅ Alert checker started")
    except Exception as e:
        logger.warning(f"Failed to start alert checker: {e}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Warehouse Operational Assistant...")
    
    # Stop rate limiter
    try:
        rate_limiter = await get_rate_limiter()
        await rate_limiter.close()
        logger.info("✅ Rate limiter stopped")
    except Exception as e:
        logger.warning(f"Failed to stop rate limiter: {e}")
    
    # Stop alert checker
    try:
        from src.api.services.monitoring.alert_checker import get_alert_checker
        from src.api.services.monitoring.performance_monitor import get_performance_monitor
        
        performance_monitor = get_performance_monitor()
        alert_checker = get_alert_checker(performance_monitor)
        await alert_checker.stop()
        logger.info("✅ Alert checker stopped")
    except Exception as e:
        logger.warning(f"Failed to stop alert checker: {e}")


# Request size limits (10MB for JSON, 50MB for file uploads)
def _safe_int_env(key: str, default: int) -> int:
    """Safely parse integer from environment variable, stripping comments."""
    value = os.getenv(key, str(default))
    value = value.split('#')[0].strip()
    try:
        return int(value)
    except ValueError:
        return default

MAX_REQUEST_SIZE = _safe_int_env("MAX_REQUEST_SIZE", 10485760)  # 10MB default
MAX_UPLOAD_SIZE = _safe_int_env("MAX_UPLOAD_SIZE", 52428800)  # 50MB default

app = FastAPI(
    title="Warehouse Operational Assistant",
    version="0.1.0",
    lifespan=lifespan,
    # Request size limits
    max_request_size=MAX_REQUEST_SIZE,
)

# Add exception handlers for secure error handling
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors securely."""
    return await handle_validation_error(request, exc)

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions securely."""
    return await handle_http_exception(request, exc)

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Handle generic exceptions securely."""
    # Special handling for circular reference errors (chat endpoint)
    error_msg = str(exc)
    if "circular reference" in error_msg.lower() or "circular" in error_msg.lower():
        logger.error(f"Circular reference error in {request.url.path}: {error_msg}")
        # Return a simple, serializable error response for chat endpoint
        if request.url.path == "/api/v1/chat":
            try:
                return JSONResponse(
                    status_code=200,  # Return 200 so frontend doesn't treat it as an error
                    content={
                        "reply": "I received your request, but there was an issue formatting the response. Please try again with a simpler question.",
                        "route": "error",
                        "intent": "error",
                        "session_id": "default",
                        "confidence": 0.0,
                        "error": "Response serialization failed",
                        "error_type": "circular_reference"
                    }
                )
            except Exception as e:
                logger.error(f"Failed to create error response: {e}")
                # Last resort - return plain text
                return Response(
                    status_code=200,
                    content='{"reply": "Error processing request", "route": "error", "intent": "error", "session_id": "default", "confidence": 0.0}',
                    media_type="application/json"
                )
    
    # Use generic exception handler for all other exceptions
    return await handle_generic_exception(request, exc)

# CORS Configuration - environment-based for security
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3001,http://localhost:3000,http://127.0.0.1:3001,http://127.0.0.1:3000")
cors_origins_list = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]

# Add security headers middleware (must be first)
app.add_middleware(SecurityHeadersMiddleware)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

# Add rate limiting middleware
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting middleware."""
    # Skip rate limiting for health checks and metrics
    if request.url.path in ["/health", "/api/v1/health", "/api/v1/health/simple", "/api/v1/metrics", "/docs", "/openapi.json", "/"]:
        return await call_next(request)
    
    try:
        rate_limiter = await get_rate_limiter()
        # check_rate_limit raises HTTPException if limit exceeded, returns True if allowed
        await rate_limiter.check_rate_limit(request)
    except HTTPException as http_exc:
        # Re-raise HTTP exceptions (429 Too Many Requests)
        raise http_exc
    except Exception as e:
        logger.error(f"Rate limiting error: {e}", exc_info=True)
        # Fail open - allow request if rate limiter fails
        pass
    
    return await call_next(request)

# Add request size limit middleware
@app.middleware("http")
async def request_size_middleware(request: Request, call_next):
    """Check request size limits."""
    # Check content-length header
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            size = int(content_length)
            # Different limits for different endpoints
            if "/document/upload" in request.url.path or "/upload" in request.url.path:
                max_size = MAX_UPLOAD_SIZE
            else:
                max_size = MAX_REQUEST_SIZE
            
            if size > max_size:
                from fastapi import HTTPException, status
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Request too large. Maximum size: {max_size / 1024 / 1024:.1f}MB"
                )
        except ValueError:
            # Invalid content-length, let it through (will be caught by FastAPI)
            pass
    
    return await call_next(request)

# Add metrics middleware
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    record_request_metrics(request, response, duration)
    return response


app.include_router(health_router)
app.include_router(chat_router)
app.include_router(equipment_router)
app.include_router(operations_router)
app.include_router(safety_router)
app.include_router(auth_router)
app.include_router(wms_router)
app.include_router(iot_router)
app.include_router(erp_router)
app.include_router(scanning_router)
app.include_router(attendance_router)
app.include_router(reasoning_router)
app.include_router(migration_router)
app.include_router(mcp_router)
app.include_router(document_router)
app.include_router(inventory_router)
app.include_router(forecasting_router)
app.include_router(training_router)


@app.get("/")
async def root():
    """Root endpoint providing API information and links."""
    return {
        "name": "Warehouse Operational Assistant API",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "health": "/api/v1/health",
        "health_simple": "/api/v1/health/simple",
    }


@app.get("/health")
async def health_check_simple():
    """
    Simple health check endpoint at root level for convenience.
    
    This endpoint provides a quick health check without the /api/v1 prefix.
    For comprehensive health information, use /api/v1/health instead.
    """
    try:
        # Quick database check
        import asyncpg
        import os
        from dotenv import load_dotenv

        load_dotenv()
        database_url = os.getenv(
            "DATABASE_URL",
            f"postgresql://{os.getenv('POSTGRES_USER', 'warehouse')}:{os.getenv('POSTGRES_PASSWORD', '')}@localhost:5435/{os.getenv('POSTGRES_DB', 'warehouse')}",
        )

        conn = await asyncpg.connect(database_url)
        await conn.execute("SELECT 1")
        await conn.close()

        return {"ok": True, "status": "healthy"}
    except Exception as e:
        logger.error(f"Simple health check failed: {e}")
        # Don't expose error details in health check
        from src.api.utils.error_handler import sanitize_error_message
        error_msg = sanitize_error_message(e, "Health check")
        return {"ok": False, "status": "unhealthy", "error": error_msg}


# Add metrics endpoint
@app.get("/api/v1/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return get_metrics_response()
