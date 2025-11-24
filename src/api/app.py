from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from fastapi.exceptions import RequestValidationError
import time
import logging
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

app = FastAPI(title="Warehouse Operational Assistant", version="0.1.0")
logger = logging.getLogger(__name__)

# Add exception handler for serialization errors
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Handle ValueError exceptions, including circular reference errors."""
    error_msg = str(exc)
    if "circular reference" in error_msg.lower() or "circular" in error_msg.lower():
        logger.error(f"Circular reference error in {request.url.path}: {error_msg}")
        # Return a simple, serializable error response
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
    # Re-raise if it's not a circular reference error
    raise exc

# CORS Configuration - environment-based for security
import os
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3001,http://localhost:3000,http://127.0.0.1:3001,http://127.0.0.1:3000")
cors_origins_list = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)


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
        return {"ok": False, "status": "unhealthy", "error": str(e)}


# Add metrics endpoint
@app.get("/api/v1/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return get_metrics_response()
