# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Health router — Batch B.

Endpoints preserved from src/api/routers/health.py:
    GET /api/v1/live             — liveness probe
    GET /api/v1/ready            — readiness probe (checks DB)
    GET /api/v1/health           — comprehensive health (DB + Redis + Milvus)
    GET /api/v1/health/simple    — lightweight health for frontend
    GET /api/v1/version          — version info
    GET /api/v1/version/detailed — detailed build info

Changes from src/ version:
    - Adds MAIW runtime status block to /health response
    - Imports runtime via FastAPI Depends rather than a module-level import
    - Uses src.api.services.version for version info (unchanged)
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from maiw_api.dependencies import get_runtime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Health"])

_start_time = datetime.utcnow()


def _uptime() -> str:
    total = int((datetime.utcnow() - _start_time).total_seconds())
    d, rem = divmod(total, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    if d:
        return f"{d}d {h}h {m}m {s}s"
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


async def _check_database() -> dict:
    try:
        import asyncpg
        from dotenv import load_dotenv

        load_dotenv()
        url = os.getenv(
            "DATABASE_URL",
            "postgresql://{user}:{pw}@localhost:5435/{db}".format(
                user=os.getenv("POSTGRES_USER", "warehouse"),
                pw=os.getenv("POSTGRES_PASSWORD", ""),
                db=os.getenv("POSTGRES_DB", "warehouse"),
            ),
        )
        conn = await asyncpg.connect(url)
        await conn.execute("SELECT 1")
        await conn.close()
        return {"status": "healthy", "message": "Database connection successful"}
    except Exception as exc:
        logger.error("Database health check failed: %s", exc)
        return {"status": "unhealthy", "message": str(exc)}


async def _check_redis() -> dict:
    try:
        import redis

        client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
        )
        client.ping()
        return {"status": "healthy", "message": "Redis connection successful"}
    except Exception as exc:
        logger.warning("Redis health check failed: %s", exc)
        return {"status": "unhealthy", "message": str(exc)}


async def _check_milvus() -> dict:
    try:
        from pymilvus import connections, utility

        connections.connect(
            alias="default",
            host=os.getenv("MILVUS_HOST", "localhost"),
            port=os.getenv("MILVUS_PORT", "19530"),
        )
        utility.get_server_version()
        return {"status": "healthy", "message": "Milvus connection successful"}
    except Exception as exc:
        logger.warning("Milvus health check failed: %s", exc)
        return {"status": "unhealthy", "message": str(exc)}


def _version_display() -> str:
    try:
        from src.api.services.version import version_service

        return version_service.get_version_display()
    except Exception:
        return "0.0.0-dev"


@router.get("/live")
async def liveness_check():
    return {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat(),
        "uptime": _uptime(),
        "version": _version_display(),
    }


@router.get("/ready")
async def readiness_check(request: Request):
    """
    Capability-aware readiness probe.

    Returns 200 if at least one MAIW operational path is available.
    A single domain being CIRCUIT OPEN does NOT fail readiness — only that
    domain's workflows are affected; others remain available.

    Returns 503 only when:
        - MAIW runtime is not initialized, OR
        - ALL MCP domains are CIRCUIT OPEN (total loss of MCP capability)
    """
    rt = getattr(request.app.state, "runtime", None)

    if rt is None:
        raise HTTPException(status_code=503, detail="MAIW runtime not initialized")

    # Check per-domain circuit states
    domain_status: dict = {}
    if rt.circuit_registry is not None:
        domain_status = rt.circuit_registry.operational_status()

    open_domains = [d for d, s in domain_status.items() if s == "CIRCUIT OPEN"]
    all_open = len(open_domains) > 0 and len(open_domains) == len(domain_status)

    if all_open:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "All MCP domains CIRCUIT OPEN",
                "open_domains": open_domains,
            },
        )

    healthy_domains = [d for d, s in domain_status.items() if s == "HEALTHY"]
    degraded_domains = [d for d, s in domain_status.items() if s == "DEGRADED"]

    return {
        "status": "ready",
        "timestamp": datetime.utcnow().isoformat(),
        "version": _version_display(),
        "domain_health": domain_status,
        "healthy_domains": healthy_domains,
        "degraded_domains": degraded_domains,
        "circuit_open_domains": open_domains,
    }


@router.get("/health/simple")
async def health_simple():
    try:
        import asyncpg
        from dotenv import load_dotenv

        load_dotenv()
        url = os.getenv(
            "DATABASE_URL",
            "postgresql://{user}:{pw}@localhost:5435/{db}".format(
                user=os.getenv("POSTGRES_USER", "warehouse"),
                pw=os.getenv("POSTGRES_PASSWORD", ""),
                db=os.getenv("POSTGRES_DB", "warehouse"),
            ),
        )
        conn = await asyncpg.connect(url)
        await conn.execute("SELECT 1")
        await conn.close()
        return {"ok": True, "status": "healthy"}
    except Exception as exc:
        logger.error("Simple health check failed: %s", exc)
        return {"ok": False, "status": "unhealthy", "error": str(exc)}


@router.get("/health")
async def health_check(request: Request):
    runtime = request.app.state.runtime

    data: dict = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "uptime": _uptime(),
        "version": _version_display(),
        "environment": os.getenv("ENVIRONMENT", "development"),
    }

    services: dict = {}
    for name, coro in [
        ("database", _check_database()),
        ("redis", _check_redis()),
        ("milvus", _check_milvus()),
    ]:
        try:
            services[name] = await coro
        except Exception as exc:
            services[name] = {"status": "error", "message": str(exc)}

    # MAIW runtime status
    if runtime is not None:
        data["maiw_runtime"] = {
            "equipment_agent": runtime.equipment_agent is not None,
            "operations_agent": runtime.operations_agent is not None,
            "safety_agent": runtime.safety_agent is not None,
            "mcp_inventory": runtime.mcp_inventory_available,
            "mcp_equipment": runtime.mcp_equipment_available,
            "mcp_labor": runtime.mcp_labor_available,
            "mcp_wave": runtime.mcp_wave_available,
        }

    data["services"] = services

    unhealthy = [
        n for n, s in services.items() if s.get("status") in ("unhealthy", "error")
    ]
    if unhealthy:
        data["status"] = "degraded"
        data["unhealthy_services"] = unhealthy

    return data


@router.get("/version")
async def get_version():
    _fallback = {
        "status": "ok",
        "version": "0.0.0-dev",
        "git_sha": "unknown",
        "build_time": datetime.utcnow().isoformat(),
        "environment": os.getenv("ENVIRONMENT", "development"),
    }
    try:
        from src.api.services.version import version_service

        info = await asyncio.wait_for(
            asyncio.to_thread(version_service.get_version_info),
            timeout=2.0,
        )
        return {"status": "ok", **info}
    except asyncio.TimeoutError:
        logger.warning("Version service timed out")
        return _fallback
    except Exception as exc:
        logger.error("Version endpoint failed: %s", exc)
        return _fallback


@router.get("/version/detailed")
async def get_detailed_version():
    _fallback = {
        "status": "ok",
        "version": "0.0.0-dev",
        "git_sha": "unknown",
        "git_branch": "unknown",
        "build_time": datetime.utcnow().isoformat(),
        "commit_count": 0,
        "python_version": "unknown",
        "environment": os.getenv("ENVIRONMENT", "development"),
        "docker_image": "unknown",
        "build_host": os.getenv("HOSTNAME", "unknown"),
        "build_user": os.getenv("USER", "unknown"),
    }
    try:
        from src.api.services.version import version_service

        info = await asyncio.wait_for(
            asyncio.to_thread(version_service.get_detailed_info),
            timeout=3.0,
        )
        return {"status": "ok", **info}
    except asyncio.TimeoutError:
        logger.warning("Detailed version service timed out")
        return _fallback
    except Exception as exc:
        logger.error("Detailed version endpoint failed: %s", exc)
        return _fallback
