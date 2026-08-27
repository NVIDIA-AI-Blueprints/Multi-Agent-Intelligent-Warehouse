# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
GET /api/v1/runtime/status — safe read-only view of MAIWRuntime component
availability.

Returns only boolean presence flags and version metadata — no credentials,
no raw configuration values, no stack traces.
"""

from __future__ import annotations

import os
from datetime import datetime

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/v1", tags=["Runtime"])

_start_time = datetime.utcnow()


@router.get("/runtime/status")
async def runtime_status(request: Request):
    """
    Non-secret runtime availability status for the Command Center.

    Fields reflect what was successfully initialised during startup.
    No credentials or config values are returned.
    """
    rt = getattr(request.app.state, "runtime", None)

    uptime_s = int((datetime.utcnow() - _start_time).total_seconds())

    if rt is None:
        return {
            "runtime_initialized": False,
            "uptime_seconds": uptime_s,
            "environment": os.getenv("ENVIRONMENT", "development"),
        }

    # ── Circuit breaker states (Phase 10E Batch 5) ────────────────────────────
    nim_circuit_state = "unknown"
    nim_circuit_stats: dict = {}
    if rt.nim_circuit is not None:
        nim_circuit_stats = rt.nim_circuit.get_stats()
        nim_circuit_state = nim_circuit_stats.get("state", "unknown")

    domain_circuit_stats: list = []
    domain_operational_status: dict = {}
    if rt.circuit_registry is not None:
        domain_circuit_stats = rt.circuit_registry.all_stats()
        domain_operational_status = rt.circuit_registry.operational_status()

    # Overall MAIW operational status — HEALTHY if all domains healthy and NIM not OPEN
    nim_label = (
        "HEALTHY"
        if nim_circuit_state == "closed"
        else ("CIRCUIT OPEN" if nim_circuit_state == "open" else "DEGRADED")
    )
    overall_degraded = nim_label != "HEALTHY" or any(
        v != "HEALTHY" for v in domain_operational_status.values()
    )
    maiw_operational_status = "DEGRADED" if overall_degraded else "HEALTHY"

    return {
        "runtime_initialized": True,
        "uptime_seconds": uptime_s,
        "environment": os.getenv("ENVIRONMENT", "development"),
        # Overall operational label
        "maiw_operational_status": maiw_operational_status,
        # ModelGateway / reasoning
        "model_gateway_available": rt.model_gateway is not None,
        "model_gateway_status": nim_label,
        "decision_engine_available": rt.decision_engine is not None,
        "state_provider_available": rt.state_provider is not None,
        # MCP domains — availability flags
        "inventory_mcp_configured": rt.mcp_inventory_available,
        "equipment_mcp_configured": rt.mcp_equipment_available,
        "labor_mcp_configured": rt.mcp_labor_available,
        "wave_mcp_configured": rt.mcp_wave_available,
        # MCP domain operational status (HEALTHY / DEGRADED / CIRCUIT OPEN)
        "domain_health": domain_operational_status,
        # Canonical agents
        "equipment_agent_available": rt.equipment_agent is not None,
        "operations_agent_available": rt.operations_agent is not None,
        "safety_agent_available": rt.safety_agent is not None,
        # Action executors
        "equipment_executor_available": rt.equipment_executor is not None,
        "labor_executor_available": rt.labor_executor is not None,
        "wave_executor_available": rt.wave_executor is not None,
        # Circuit breaker detail — for operator dashboards
        "circuit_states": {
            "nim": nim_circuit_stats,
            "domains": domain_circuit_stats,
        },
    }
