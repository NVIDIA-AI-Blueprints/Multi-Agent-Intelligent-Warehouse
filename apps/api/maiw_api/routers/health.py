# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Health router — Batch B.

Endpoints preserved from src/api/routers/health.py:
    GET /api/v1/live             — liveness probe
    GET /api/v1/ready            — profile-aware readiness probe (persistence,
                                   ModelGateway + physical model bindings,
                                   governed write path, required MCP domains,
                                   DB, sandbox — v2.0.1 / round 2)
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


def _data_path_db_target() -> dict:
    """
    Connection parameters of the database the shipped app's data path uses.

    v2.0.1 round 2 (audit P2-19): readiness used to probe ``DATABASE_URL``
    while the SQL data path (``SQLRetriever`` → ``DatabaseConfig.from_env``)
    connects with ``PGHOST``/``PGPORT``/``POSTGRES_*``.  Readiness now probes
    exactly the data-path parameters (same variables, same defaults).
    """
    return {
        "host": os.getenv("PGHOST", "localhost"),
        "port": int(os.getenv("PGPORT", "5435")),
        "database": os.getenv("POSTGRES_DB", "warehouse"),
        "user": os.getenv("POSTGRES_USER", "warehouse"),
        "password": os.getenv("POSTGRES_PASSWORD", ""),
    }


def _norm_host(host: str | None) -> str:
    host = (host or "").strip().lower()
    return "127.0.0.1" if host in ("localhost", "::1", "") else host


def _database_url_mismatch(target: dict) -> str | None:
    """
    Reason string when ``DATABASE_URL`` is set but names a different database
    than the data path uses (the app would be split across two databases).
    """
    url = os.getenv("DATABASE_URL")
    if not url:
        return None
    from urllib.parse import urlparse

    try:
        u = urlparse(url)
        url_target = (
            _norm_host(u.hostname),
            int(u.port or 5432),
            (u.path or "/").lstrip("/"),
        )
    except Exception:  # noqa: BLE001 - malformed URL is itself a mismatch
        return "DATABASE_URL is not a valid postgresql:// URL"
    data_target = (_norm_host(target["host"]), target["port"], target["database"])
    if url_target != data_target:
        return (
            "DATABASE_URL targets {}:{}/{} but the data path (PGHOST/PGPORT/"
            "POSTGRES_DB) targets {}:{}/{}".format(*url_target, *data_target)
        )
    return None


async def _check_database() -> dict:
    try:
        import asyncpg

        target = _data_path_db_target()
        conn = await asyncpg.connect(
            host=target["host"],
            port=target["port"],
            user=target["user"],
            password=target["password"],
            database=target["database"],
            timeout=_READINESS_DB_TIMEOUT_S,
        )
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
    body = {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat(),
        "uptime": _uptime(),
        "version": _version_display(),
    }
    # v2.0.1 round 2: deployment identity.  start_reference_deployment.sh
    # launches the app with a random MAIW_INSTANCE_ID (non-secret) and the
    # lifecycle scripts only act on a port that answers with that id.
    instance_id = os.getenv("MAIW_INSTANCE_ID")
    if instance_id:
        body["instance_id"] = instance_id
    return body


def _database_required() -> bool:
    """
    Whether the backing Postgres is a critical readiness dependency.

    Decided by the deployment profile (``maiw_api.profile``):
    ``MAIW_READINESS_REQUIRE_DATABASE`` (true/false) decides explicitly;
    otherwise ``reference`` / ``reference_governed`` require it and ``demo``
    does not (demo serves operational flows from in-memory simulation).
    """
    from maiw_api.profile import resolve_profile

    return resolve_profile().database_required


async def _probe_database_for_readiness() -> dict:
    """SELECT 1 against the data-path database, bounded by a short timeout."""
    target = _data_path_db_target()
    where = f"{target['host']}:{target['port']}/{target['database']}"
    mismatch = _database_url_mismatch(target)
    if mismatch:
        return {"status": "failed", "target": where, "reason": mismatch}
    try:
        result = await asyncio.wait_for(
            _check_database(), timeout=_READINESS_DB_TIMEOUT_S + 2.0
        )
    except asyncio.TimeoutError:
        return {"status": "failed", "target": where, "reason": "database probe timed out"}
    if result.get("status") == "healthy":
        return {"status": "ready", "target": where}
    return {
        "status": "failed",
        "target": where,
        "reason": str(result.get("message", ""))[:200],
    }


# ── MCP domain readiness (v2.0.1 round 2, audit NEW-P1-03) ────────────────────
#
# Per-domain state, never "HEALTHY" for a domain that is not configured:
#   READY           configured, reachable, circuit closed, no recent failures
#   DEGRADED        configured, reachable, circuit closed, recent failures
#   CIRCUIT_OPEN    configured, circuit open or half-open
#   FAILED          configured but not reachable
#   NOT_CONFIGURED  no MCP server configured for the domain
_MCP_USABLE = ("READY", "DEGRADED")
_MCP_REACH_TIMEOUT_S = 1.0


async def _mcp_reachable(url: str) -> tuple[bool, str | None]:
    """Bounded TCP reachability probe of an MCP server URL (no request sent)."""
    from urllib.parse import urlparse

    try:
        u = urlparse(url)
        host = u.hostname
        port = u.port or (443 if u.scheme == "https" else 80)
        if not host:
            return False, "invalid MCP URL"
    except Exception:  # noqa: BLE001
        return False, "invalid MCP URL"
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=_MCP_REACH_TIMEOUT_S
        )
    except Exception as exc:  # noqa: BLE001 - any failure = unreachable
        return False, f"{type(exc).__name__} connecting to {host}:{port}"
    writer.close()
    try:
        await writer.wait_closed()
    except Exception:  # noqa: BLE001  # pragma: no cover
        pass
    return True, None


async def _mcp_domain_states(rt, profile) -> dict:
    """{domain: {state, required, configured, transport, ...}}."""
    from maiw_api.profile import MCP_DOMAINS

    circuit_labels: dict = {}
    registry = getattr(rt, "circuit_registry", None)
    if registry is not None:
        try:
            circuit_labels = registry.operational_status()
        except Exception:  # noqa: BLE001  # pragma: no cover
            circuit_labels = {}
    endpoints = getattr(rt, "mcp_domain_endpoints", None)
    if not isinstance(endpoints, dict):
        endpoints = {}

    domains = list(MCP_DOMAINS) + [
        d for d in circuit_labels if d not in MCP_DOMAINS
    ]
    states: dict = {}
    for domain in domains:
        configured = getattr(rt, f"mcp_{domain}_available", False) is True
        entry: dict = {
            "required": domain in profile.required_mcp_domains,
            "configured": configured,
        }
        if not configured:
            entry["state"] = "NOT_CONFIGURED"
            states[domain] = entry
            continue
        transport, url = endpoints.get(domain, ("unknown", None))
        entry["transport"] = transport
        if transport == "url" and url:
            reachable, why = await _mcp_reachable(url)
            entry["reachable"] = reachable
            if not reachable:
                entry["state"] = "FAILED"
                entry["reason"] = why
                states[domain] = entry
                continue
        else:
            entry["reachable"] = transport == "in-memory"
        label = circuit_labels.get(domain, "HEALTHY")
        entry["circuit"] = label
        if label == "CIRCUIT OPEN":
            entry["state"] = "CIRCUIT_OPEN"
        elif label == "DEGRADED":
            entry["state"] = "DEGRADED"
        else:
            entry["state"] = "READY"
        states[domain] = entry
    return states


_SANDBOX_PROBE_TIMEOUT_S = 5.0


async def _probe_sandbox(name: str) -> tuple[str | None, str | None]:
    """
    ``(phase, error)`` of the OpenShell sandbox ``name`` via the OpenShell CLI
    (``MAIW_OPENSHELL_BIN``, default ``openshell``): ``openshell sandbox list
    -o json`` — read-only, bounded by a timeout.
    """
    import json
    import shutil

    binary = os.getenv("MAIW_OPENSHELL_BIN", "openshell")
    if shutil.which(binary) is None:
        return None, f"OpenShell CLI {binary!r} not found"
    try:
        proc = await asyncio.create_subprocess_exec(
            binary,
            "sandbox",
            "list",
            "-o",
            "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            out, _ = await asyncio.wait_for(
                proc.communicate(), timeout=_SANDBOX_PROBE_TIMEOUT_S
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return None, "OpenShell sandbox list timed out"
        for item in json.loads(out or b"[]"):
            if isinstance(item, dict) and item.get("name") == name:
                return str(item.get("phase") or ""), None
        return None, f"sandbox {name!r} not found"
    except Exception as exc:  # noqa: BLE001
        return None, f"sandbox probe failed: {type(exc).__name__}"


async def _sandbox_component(profile) -> dict:
    name = os.getenv("MAIW_SANDBOX_NAME", "").strip()
    base = {
        "mode": profile.sandbox_mode,
        "required": profile.sandbox_required,
        "critical": profile.sandbox_required,
    }
    if not name:
        if profile.sandbox_required:
            return {
                **base,
                "status": "failed",
                "reason": "MAIW_SANDBOX_MODE=required but MAIW_SANDBOX_NAME is not set",
            }
        return {**base, "status": "not_configured"}
    phase, err = await _probe_sandbox(name)
    entry = {**base, "name": name, "phase": phase}
    if phase == "Ready":
        return {**entry, "status": "ready"}
    reason = err or f"sandbox phase {phase!r} (expected Ready)"
    if profile.sandbox_required:
        return {**entry, "status": "failed", "reason": reason}
    return {**entry, "status": "degraded", "reason": reason}


@router.get("/ready")
async def readiness_check(request: Request):
    """
    Readiness probe — can the canonical shipped app do the work its selected
    deployment profile claims?  (``maiw_api.profile``; v2.0.1 P1-04 + round 2
    NEW-P1-03.)

    Critical (any failure → HTTP 503, ``status: NOT_READY``):
        profile              MAIW_DEPLOYMENT_PROFILE is valid
        runtime              MAIW runtime assembled by the lifespan
        persistence          durable ProcedureStateStore + GovernanceInbox —
                             directories exist, are listable and accept an
                             fsynced write/read/delete probe
        model_gateway        canonical ModelGateway constructed AND every
                             enabled role bound to an approved physical model
        governed_write_path  only for profiles that claim governed writes
                             (demo, reference_governed): DecisionEngine + MCP
                             client + equipment agent + every required MCP
                             write domain usable + its executor.  Profiles
                             without governed writes report ``not_offered``.
        mcp_domains          every REQUIRED domain is READY or DEGRADED
                             (NOT_CONFIGURED / CIRCUIT_OPEN / FAILED → 503).
                             Optional domains are reported, never critical.
        database             SELECT 1 on the data-path database (PGHOST/
                             PGPORT/POSTGRES_*) when the profile requires it
        sandbox_runtime      critical only when MAIW_SANDBOX_MODE=required:
                             sandbox MAIW_SANDBOX_NAME must be phase Ready

    Reported, not critical:
        model_provider       NIM circuit state — an unreachable provider makes
                             inference fail per request with a typed 503; it
                             does not make the process un-ready (all profiles)

    Liveness (``/api/v1/live``) never depends on any of these.
    """
    from fastapi.responses import JSONResponse

    from maiw_api.persistence import probe_persistence
    from maiw_api.profile import resolve_profile

    profile = resolve_profile()
    rt = getattr(request.app.state, "runtime", None)
    components: dict = {
        "profile": {
            "status": "ready" if profile.valid else "failed",
            **profile.as_dict(),
        }
    }

    if rt is None:
        components["runtime"] = {"status": "failed", "reason": "not initialized"}
        failed = ["runtime"] + (["profile"] if not profile.valid else [])
        return JSONResponse(
            status_code=503,
            content={
                "status": "NOT_READY",
                "timestamp": datetime.utcnow().isoformat(),
                "profile": profile.name,
                "failed_components": failed,
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

    # ── Canonical ModelGateway + physical model bindings (round 2) ────────────
    if rt.model_gateway is None:
        components["model_gateway"] = {
            "status": "failed",
            "reason": "ModelGateway not initialized",
        }
    else:
        violations: list = []
        try:
            violations = rt.model_gateway.registry.binding_violations()
            if not isinstance(violations, list):
                violations = []
        except Exception:  # noqa: BLE001 - non-canonical gateway object
            violations = []
        components["model_gateway"] = (
            {
                "status": "failed",
                "reason": "enabled role(s) bound to an unapproved physical model",
                "binding_violations": [
                    {k: v[k] for k in ("role", "model_id", "reason")}
                    for v in violations
                ],
            }
            if violations
            else {"status": "ready"}
        )

    # ── MCP domains (round 2: profile-aware, NOT_CONFIGURED ≠ HEALTHY) ─────────
    domain_states = await _mcp_domain_states(rt, profile)
    required_unusable = sorted(
        d
        for d, e in domain_states.items()
        if e["required"] and e["state"] not in _MCP_USABLE
    )
    missing_required = sorted(
        d for d in profile.required_mcp_domains if d not in domain_states
    )
    required_unusable += missing_required
    components["mcp_domains"] = {
        "status": "failed" if required_unusable else "ready",
        "required": sorted(profile.required_mcp_domains),
        "required_unusable": required_unusable,
        "domains": domain_states,
    }

    # ── Governed write path ───────────────────────────────────────────────────
    if profile.governed_writes:
        missing: list[str] = []
        if rt.decision_engine is None:
            missing.append("decision_engine")
        if rt.mcp_client is None:
            missing.append("mcp_client")
        if rt.equipment_agent is None:
            missing.append("equipment_agent")
        for domain in sorted(profile.required_mcp_domains):
            executor = getattr(rt, f"{domain}_executor", "n/a")
            if executor is None:
                missing.append(f"{domain}_executor")
        gwp: dict = {"status": "ready"}
        if missing or required_unusable:
            gwp = {"status": "failed"}
            if missing:
                gwp["missing"] = missing
            if required_unusable:
                gwp["unusable_mcp_domains"] = required_unusable
        components["governed_write_path"] = gwp
    else:
        components["governed_write_path"] = {
            "status": "not_offered",
            "critical": False,
            "reason": (
                f"profile {profile.name!r} does not offer governed operational "
                "writes (use MAIW_DEPLOYMENT_PROFILE=reference_governed with "
                "the required MCP write domains configured)"
            ),
        }

    # ── Database ──────────────────────────────────────────────────────────────
    if profile.database_required:
        components["database"] = await _probe_database_for_readiness()
    else:
        components["database"] = {"status": "not_required"}

    # ── Sandbox runtime (round 2: critical when the profile requires it) ──────
    components["sandbox_runtime"] = await _sandbox_component(profile)

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

    critical = (
        "profile",
        "runtime",
        "persistence",
        "model_gateway",
        "governed_write_path",
        "mcp_domains",
        "database",
        "sandbox_runtime",
    )
    failed = [c for c in critical if components[c].get("status") == "failed"]

    configured_labels = {
        d: ("CIRCUIT OPEN" if e["state"] == "CIRCUIT_OPEN" else e["state"])
        for d, e in domain_states.items()
    }
    body = {
        "status": "NOT_READY" if failed else "READY",
        "timestamp": datetime.utcnow().isoformat(),
        "version": _version_display(),
        "profile": profile.name,
        "failed_components": failed,
        "components": components,
        # Backward-compatible fields (pre-v2.0.1 consumers).  Round 2: an
        # unconfigured domain is NOT_CONFIGURED, never HEALTHY.
        "domain_health": configured_labels,
        "healthy_domains": [d for d, e in domain_states.items() if e["state"] == "READY"],
        "degraded_domains": [
            d for d, e in domain_states.items() if e["state"] == "DEGRADED"
        ],
        "circuit_open_domains": [
            d for d, e in domain_states.items() if e["state"] == "CIRCUIT_OPEN"
        ],
        "not_configured_domains": [
            d for d, e in domain_states.items() if e["state"] == "NOT_CONFIGURED"
        ],
    }
    return JSONResponse(status_code=503 if failed else 200, content=body)


@router.get("/health/simple")
async def health_simple():
    result = await _check_database()
    if result.get("status") == "healthy":
        return {"ok": True, "status": "healthy"}
    logger.error("Simple health check failed: %s", result.get("message"))
    return {"ok": False, "status": "unhealthy", "error": result.get("message")}


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
