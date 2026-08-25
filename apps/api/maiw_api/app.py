# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Canonical MAIW FastAPI entrypoint — Phase 9B.

Entrypoint:
    uvicorn maiw_api.app:app --host 0.0.0.0 --port 8001

Router ownership:
    Canonical (this package)
        health       → maiw_api.routers.health
        equipment    → maiw_api.routers.equipment     (canonical pipeline)
        operations   → maiw_api.routers.operations    (SQL CRUD, bug-fixed)
        safety       → maiw_api.routers.safety        (SQL CRUD)
        mcp_status   → maiw_api.routers.mcp_status    (canonical MCP v2)

    Keep temporarily (from src.api.routers)
        auth, inventory, wms, iot, erp, scanning, attendance,
        reasoning, migration, document, advanced_forecasting, training, chat

    Removed (legacy custom MCP)
        src.api.routers.mcp                           (replaced by mcp_status)
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from maiw_api.config import settings
from maiw_api.lifespan import lifespan

# ── Canonical routers ─────────────────────────────────────────────────────────
from maiw_api.routers.health import router as health_router
from maiw_api.routers.equipment import router as equipment_router
from maiw_api.routers.operations import router as operations_router
from maiw_api.routers.safety import router as safety_router
from maiw_api.routers.mcp_status import router as mcp_status_router
from maiw_api.routers.runtime_status import router as runtime_status_router
from maiw_api.routers.demo import router as demo_router

# ── Legacy routers (keep temporarily) ────────────────────────────────────────
from src.api.routers.auth import router as auth_router
from src.api.routers.inventory import router as inventory_router
from src.api.routers.wms import router as wms_router
from src.api.routers.iot import router as iot_router
from src.api.routers.erp import router as erp_router
from src.api.routers.scanning import router as scanning_router
from src.api.routers.attendance import router as attendance_router
from src.api.routers.reasoning import router as reasoning_router
from src.api.routers.migration import router as migration_router
from src.api.routers.document import router as document_router
from src.api.routers.advanced_forecasting import router as forecasting_router
from src.api.routers.training import router as training_router
from src.api.routers.chat import router as chat_router

# ── Shared middleware / monitoring (from src, no migration needed) ─────────────
from src.api.middleware.security_headers import SecurityHeadersMiddleware
from src.api.services.monitoring.metrics import record_request_metrics
from src.api.services.security.rate_limiter import get_rate_limiter
from src.api.utils.error_handler import (
    handle_generic_exception,
    handle_http_exception,
    handle_validation_error,
)

logger = logging.getLogger(__name__)


def _safe_int_env(key: str, default: int) -> int:
    value = os.getenv(key, str(default)).split("#")[0].strip()
    try:
        return int(value)
    except ValueError:
        return default


_MAX_REQUEST_SIZE = _safe_int_env("MAX_REQUEST_SIZE", 10_485_760)  # 10 MB
_MAX_UPLOAD_SIZE = _safe_int_env("MAX_UPLOAD_SIZE", 52_428_800)  # 50 MB

# ── Application ───────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    description=settings.app_description,
    lifespan=lifespan,
    max_request_size=_MAX_REQUEST_SIZE,
)

# ── Exception handlers ────────────────────────────────────────────────────────


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return await handle_validation_error(request, exc)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return await handle_http_exception(request, exc)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    error_msg = str(exc)
    # Preserve legacy chat-endpoint circular-reference guard
    if "circular" in error_msg.lower() and request.url.path == "/api/v1/chat":
        logger.error("Circular reference error in chat: %s", error_msg)
        try:
            return JSONResponse(
                status_code=200,
                content={
                    "reply": (
                        "I received your request, but there was an issue formatting "
                        "the response. Please try again with a simpler question."
                    ),
                    "route": "error",
                    "intent": "error",
                    "session_id": "default",
                    "confidence": 0.0,
                    "error": "Response serialization failed",
                    "error_type": "circular_reference",
                },
            )
        except Exception:
            return Response(
                status_code=200,
                content='{"reply":"Error processing request","route":"error","intent":"error","session_id":"default","confidence":0.0}',
                media_type="application/json",
            )
    return await handle_generic_exception(request, exc)


# ── Middleware (order matters — first added = outermost) ──────────────────────

app.add_middleware(SecurityHeadersMiddleware)

_cors_origins = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3001,http://localhost:3000,"
        "http://127.0.0.1:3001,http://127.0.0.1:3000",
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

_RATE_LIMIT_SKIP = frozenset(
    {
        "/health",
        "/api/v1/health",
        "/api/v1/health/simple",
        "/api/v1/metrics",
        "/docs",
        "/openapi.json",
        "/",
    }
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path not in _RATE_LIMIT_SKIP:
        try:
            limiter = await get_rate_limiter()
            await limiter.check_rate_limit(request)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Rate limiting error: %s", exc)
    return await call_next(request)


@app.middleware("http")
async def request_size_middleware(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            size = int(content_length)
            max_size = (
                _MAX_UPLOAD_SIZE
                if (
                    "/document/upload" in request.url.path
                    or "/upload" in request.url.path
                )
                else _MAX_REQUEST_SIZE
            )
            if size > max_size:
                raise HTTPException(
                    status_code=413,
                    detail=f"Request too large: {size} bytes (max {max_size})",
                )
        except ValueError:
            pass
    return await call_next(request)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    import time

    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    try:
        record_request_metrics(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration=duration,
        )
    except Exception:
        pass
    return response


# ── Routers ───────────────────────────────────────────────────────────────────

# Canonical (Phase 9B)
app.include_router(health_router)
app.include_router(equipment_router)
app.include_router(operations_router)
app.include_router(safety_router)
app.include_router(mcp_status_router)
app.include_router(runtime_status_router)
app.include_router(demo_router)

# Legacy (keep temporarily)
app.include_router(auth_router)
app.include_router(inventory_router)
app.include_router(wms_router)
app.include_router(iot_router)
app.include_router(erp_router)
app.include_router(scanning_router)
app.include_router(attendance_router)
app.include_router(reasoning_router)
app.include_router(migration_router)
app.include_router(document_router)
app.include_router(forecasting_router)
app.include_router(training_router)
app.include_router(chat_router)


@app.get("/")
async def root():
    return {
        "service": settings.app_title,
        "version": settings.app_version,
        "pipeline": "STATE → REASON → PROPOSE → DECIDE → EXECUTE → MCP → BACKEND",
        "docs": "/docs",
        "health": "/api/v1/health",
    }
