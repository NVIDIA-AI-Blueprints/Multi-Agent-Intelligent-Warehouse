# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Health router — Batch B.

Endpoints preserved from src/api/routers/health.py:
    GET /api/v1/live             — liveness probe
    GET /api/v1/ready            — readiness probe (persistence, ModelGateway,
                                   governed write path, MCP, DB — v2.0.1)
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

# Bound for every database probe (readiness and /health). A paused or
# unreachable database must fail the probe, not hang it.
_READINESS_DB_TIMEOUT_S = 3.0


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
        conn = await asyncpg.connect(url, timeout=_READINESS_DB_TIMEOUT_S)
        try:
            await conn.execute("SELECT 1", timeout=_READINESS_DB_TIMEOUT_S)
        finally:
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


def _database_required() -> bool:
    """
    Whether the backing Postgres is a critical readiness dependency.

    ``MAIW_READINESS_REQUIRE_DATABASE`` (true/false) decides explicitly. When it
    is unset the database is required unless ``MAIW_DEMO_MODE`` is on: in the
    reference profile the mounted read routes (equipment, operations, safety,
    inventory, auth) and the document workflow all depend on it, while demo mode
    serves the operational flows from in-memory simulation providers.
    """
    explicit = os.getenv("MAIW_READINESS_REQUIRE_DATABASE")
    if explicit is not None and explicit.strip():
        return explicit.strip().lower() in ("1", "true", "yes")
    demo = os.getenv("MAIW_DEMO_MODE", "false").strip().lower() in ("1", "true", "yes")
    return not demo


async def _probe_database_for_readiness() -> dict:
    """SELECT 1 against the configured database, bounded by a short timeout."""
    try:
        result = await asyncio.wait_for(
            _check_database(), timeout=_READINESS_DB_TIMEOUT_S + 2.0
        )
    except asyncio.TimeoutError:
        return {"status": "failed", "reason": "database probe timed out"}
    if result.get("status") == "healthy":
        return {"status": "ready"}
    return {"status": "failed", "reason": str(result.get("message", ""))[:200]}


@router.get("/ready")
async def readiness_check(request: Request):
    """
    Readiness probe — can the canonical shipped app safely accept work?

    v2.0.1 (audit P1-04): readiness is computed from the dependencies the
    shipped app actually needs, and every component is reported:

    Critical (any failure → HTTP 503, ``status: NOT_READY``):
        runtime              MAIW runtime assembled by the lifespan
        persistence          durable ProcedureStateStore + GovernanceInbox —
                             directories exist, are listable and accept an
                             fsynced write/read/delete probe
        model_gateway        canonical ModelGateway constructed
        governed_write_path  DecisionEngine + MCP client + equipment agent
        mcp_domains          not every configured MCP domain CIRCUIT OPEN
        database             SELECT 1 succeeds (when required; see
                             ``_database_required``)

    Reported, not critical (the API can still accept work; affected requests
    fail individually with typed errors):
        model_provider       NIM circuit state — an unreachable provider makes
                             inference return 503 PROVIDER_FAILURE per request;
                             it does not make the process un-ready
        sandbox_runtime      OpenShell is not a dependency of this process: the
                             sandbox calls the API, not the reverse

    Liveness (``/api/v1/live``) never depends on any of these.
    """
    from fastapi.responses import JSONResponse

    from maiw_api.persistence import probe_persistence

    rt = getattr(request.app.state, "runtime", None)
    components: dict = {}

    if rt is None:
        components["runtime"] = {"status": "failed", "reason": "not initialized"}
        return JSONResponse(
            status_code=503,
            content={
                "status": "NOT_READY",
                "timestamp": datetime.utcnow().isoformat(),
                "failed_components": ["runtime"],
                "components": components,
            },
        )
    components["runtime"] = {"status": "ready"}

    # ── Durable persistence (P1-03 / P1-04) ───────────────────────────────────
    components["persistence"] = probe_persistence(getattr(rt, "persistence", None))
    if getattr(rt, "procedure_host", None) is None:
        components["persistence"]["status"] = "failed"
        components["persistence"].setdefault("errors", []).append(
            "procedure_host not constructed"
        )

    # ── Canonical ModelGateway ────────────────────────────────────────────────
    components["model_gateway"] = (
        {"status": "ready"}
        if rt.model_gateway is not None
        else {"status": "failed", "reason": "ModelGateway not initialized"}
    )

    # ── Governed write path ───────────────────────────────────────────────────
    missing: list[str] = []
    if rt.decision_engine is None:
        missing.append("decision_engine")
    if rt.mcp_client is None:
        missing.append("mcp_client")
    if rt.equipment_agent is None:
        missing.append("equipment_agent")
    components["governed_write_path"] = (
        {"status": "failed", "missing": missing} if missing else {"status": "ready"}
    )

    # ── MCP domains ───────────────────────────────────────────────────────────
    domain_status: dict = {}
    if rt.circuit_registry is not None:
        domain_status = rt.circuit_registry.operational_status()
    open_domains = [d for d, s in domain_status.items() if s == "CIRCUIT OPEN"]
    all_open = len(open_domains) > 0 and len(open_domains) == len(domain_status)
    components["mcp_domains"] = {
        "status": "failed" if all_open else "ready",
        "domain_health": domain_status,
        "circuit_open_domains": open_domains,
    }

    # ── Database ──────────────────────────────────────────────────────────────
    if _database_required():
        components["database"] = await _probe_database_for_readiness()
    else:
        components["database"] = {"status": "not_required"}

    # ── Reported, non-critical ────────────────────────────────────────────────
    nim_state = "unknown"
    if getattr(rt, "nim_circuit", None) is not None:
        try:
            nim_state = rt.nim_circuit.get_stats().get("state", "unknown")
        except Exception:  # pragma: no cover - defensive
            nim_state = "unknown"
    components["model_provider"] = {
        "status": "degraded" if nim_state == "open" else "ready",
        "nim_circuit": nim_state,
        "critical": False,
    }
    components["sandbox_runtime"] = {
        "status": "external",
        "mode": os.getenv("MAIW_SANDBOX_MODE", "disabled"),
        "critical": False,
    }

    critical = (
        "runtime",
        "persistence",
        "model_gateway",
        "governed_write_path",
        "mcp_domains",
        "database",
    )
    failed = [c for c in critical if components[c].get("status") == "failed"]

    body = {
        "status": "NOT_READY" if failed else "READY",
        "timestamp": datetime.utcnow().isoformat(),
        "version": _version_display(),
        "failed_components": failed,
        "components": components,
        # Backward-compatible fields (pre-v2.0.1 consumers)
        "domain_health": domain_status,
        "healthy_domains": [d for d, s in domain_status.items() if s == "HEALTHY"],
        "degraded_domains": [d for d, s in domain_status.items() if s == "DEGRADED"],
        "circuit_open_domains": open_domains,
    }
    return JSONResponse(status_code=503 if failed else 200, content=body)


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
