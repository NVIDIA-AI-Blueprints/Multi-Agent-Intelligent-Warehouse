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

    return {
        "runtime_initialized": True,
        "uptime_seconds": uptime_s,
        "environment": os.getenv("ENVIRONMENT", "development"),
        # ModelGateway / reasoning
        "model_gateway_available": rt.model_gateway is not None,
        "decision_engine_available": rt.decision_engine is not None,
        "state_provider_available": rt.state_provider is not None,
        # MCP domains
        "inventory_mcp_configured": rt.mcp_inventory_available,
        "equipment_mcp_configured": rt.mcp_equipment_available,
        "labor_mcp_configured": rt.mcp_labor_available,
        "wave_mcp_configured": rt.mcp_wave_available,
        # Canonical agents
        "equipment_agent_available": rt.equipment_agent is not None,
        "operations_agent_available": rt.operations_agent is not None,
        "safety_agent_available": rt.safety_agent is not None,
        # Action executors
        "equipment_executor_available": rt.equipment_executor is not None,
        "labor_executor_available": rt.labor_executor is not None,
        "wave_executor_available": rt.wave_executor is not None,
    }
