# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Canonical MAIW FastAPI entrypoint — the ONLY release composition root.

Entrypoint:
    uvicorn maiw_api.app:app --host 0.0.0.0 --port 8001

``src/api/app.py`` is a legacy development server and is not part of any
release, deployment or qualification path.

Router ownership and mutation policy (v2.0.1 — see maiw_api.route_policy and
docs/audits/MAIW_V2.0.1_REMEDIATION_AUDIT.md for the full authority graph):

    Canonical (this package)
        health        GET only (/live, /ready, /health, /version)
        equipment     GET + governed POST (agent proposal → DecisionEngine →
                      EquipmentActionExecutor only when APPROVED)
        operations    GET only in the shipped app (SQL task writes unmounted)
        safety        GET only in the shipped app (SQL incident writes unmounted)
        mcp_status, runtime_status, world, model_lab, agent_tasks,
        procedures    GET only
        demo          simulation controls (MAIW_DEMO_MODE only) + governed
                      approve/reject/reconcile
        copilot       POST /turn — ACT goes through GovernedActionOrchestrator
        inference     POST /api/v1/inference — bounded ModelGateway endpoint,
                      fail-closed internal token, no governance below it

    Legacy (src.api.routers) — mounted READ-ONLY unless listed
        auth                       full (identity; own auth dependencies)
        document                   read-only + POST /upload (bounded inference
                                   via ModelGateway; document-workflow state)
                                   + POST /approve|/reject (document-workflow
                                   state only; no warehouse mutation)
        inventory, wms, iot, erp, scanning, attendance, migration,
        advanced_forecasting, training
                                   GET/HEAD routes only

    Not mounted in the shipped app (v2.0.1)
        chat        legacy LLM agent → ToolDiscoveryService → direct SQL writes
                    (audit P1-01); use POST /api/v1/copilot/turn
        reasoning   legacy NIM client outside ModelGateway
        src.api.routers.mcp (retired; replaced by mcp_status)
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

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
from maiw_api.routers.copilot import router as copilot_router
from maiw_api.routers.world import router as world_router

from maiw_api.routers.model_lab import router as model_lab_router
from maiw_api.routers.agent_tasks import router as agent_tasks_router
from maiw_api.routers.procedures import router as procedures_router
from maiw_api.route_policy import curated_view, read_only_view

# Bounded sandbox inference endpoint (one implementation, shared with the
# legacy dev server): POST /api/v1/inference → canonical ModelGateway.
from src.api.routers.inference import router as inference_router

# ── Legacy routers (mounted through route_policy views only) ─────────────────
from src.api.routers.auth import router as auth_router
from src.api.routers.inventory import router as inventory_router
from src.api.routers.wms import router as wms_router
from src.api.routers.iot import router as iot_router
from src.api.routers.erp import router as erp_router
from src.api.routers.scanning import router as scanning_router
from src.api.routers.attendance import router as attendance_router
from src.api.routers.migration import router as migration_router
from src.api.routers.document import router as document_router
from src.api.routers.advanced_forecasting import router as forecasting_router
from src.api.routers.training import router as training_router

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

# Canonical routers
app.include_router(health_router)
app.include_router(equipment_router)
# operations / safety: the SQL task/incident writes have no governed path, so
# only their read routes ship (v2.0.1, audit P1-01 / §29).
app.include_router(read_only_view(operations_router))
app.include_router(read_only_view(safety_router))
app.include_router(mcp_status_router)
app.include_router(runtime_status_router)
app.include_router(demo_router)
app.include_router(copilot_router)
app.include_router(world_router)

app.include_router(model_lab_router)
app.include_router(agent_tasks_router)
app.include_router(procedures_router)

# Bounded inference boundary (v2.0.1, audit P1-02)
app.include_router(inference_router)

# Legacy — identity management keeps its own auth dependencies.
app.include_router(auth_router)

# Legacy — document workflow. Upload runs model inference only through
# ModelGateway (audit P1-05); approve/reject record document-workflow state.
# /search, /validate and /analytics returned fabricated data and are not shipped.
app.include_router(
    curated_view(
        document_router,
        allow_mutations={
            ("POST", "/api/v1/document/upload"),
            ("POST", "/api/v1/document/approve/{document_id}"),
            ("POST", "/api/v1/document/reject/{document_id}"),
        },
    )
)

# Legacy — read-only. Every POST/PUT/PATCH/DELETE route of these routers
# (inventory/WMS/IoT/ERP/scanner/attendance writes, DB migrate/rollback,
# forecasting batch jobs, training subprocess start) is NOT mounted.
for _legacy_router in (
    inventory_router,
    wms_router,
    iot_router,
    erp_router,
    scanning_router,
    attendance_router,
    migration_router,
    forecasting_router,
    training_router,
):
    app.include_router(read_only_view(_legacy_router))

# NOT mounted (v2.0.1): src.api.routers.chat (P1-01 ungoverned write path),
# src.api.routers.reasoning (direct NIM client outside ModelGateway).


@app.get("/")
async def root():
    return {
        "service": settings.app_title,
        "version": settings.app_version,
        "pipeline": "STATE → REASON → PROPOSE → DECIDE → EXECUTE → MCP → BACKEND",
        "docs": "/docs",
        "health": "/api/v1/health",
    }
