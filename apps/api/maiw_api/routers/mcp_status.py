# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MCP Status router — Batch E.

Replaces src/api/routers/mcp.py (legacy custom MCP system) with a canonical
MCP v2 status endpoint.

The legacy router imported:
    ToolDiscoveryService, ToolBindingService, ToolRoutingService,
    mcp_integrated_planner_graph — all retired.

This router exposes:
    GET /api/v1/mcp/status
        Current capability registry state and domain availability flags.
    GET /api/v1/mcp/capabilities
        List of all registered capability names.

No write endpoints — the MCP layer is invoked by agents through the
canonical pipeline, not directly by REST callers.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from maiw_api.dependencies import get_runtime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/mcp", tags=["MCP"])


@router.get("/status", response_model=Dict[str, Any])
async def get_mcp_status(runtime=Depends(get_runtime)):
    """
    Return the current state of the MCP CapabilityRegistry.

    Response::

        {
            "protocol": "MCP 2026-07-28",
            "client_ready": true,
            "domains": {
                "inventory":  { "available": true,  "url": "http://..." },
                "equipment":  { "available": false, "url": null },
                "labor":      { "available": false, "url": null },
                "wave":       { "available": false, "url": null },
            },
            "registered_capabilities": ["warehouse.inventory.get", ...],
        }
    """
    registry = getattr(runtime, "mcp_registry", None)

    capabilities: List[str] = []
    if registry is not None:
        try:
            capabilities = registry.all_capabilities()
        except Exception:
            pass

    def _url_for(domain: str) -> str | None:
        if registry is None:
            return None
        for cap in capabilities:
            if cap.startswith(f"warehouse.{domain}."):
                try:
                    return registry.resolve(cap)
                except Exception:
                    pass
        return None

    return {
        "protocol": "MCP 2026-07-28",
        "client_ready": runtime.mcp_client is not None,
        "domains": {
            "inventory": {
                "available": runtime.mcp_inventory_available,
                "url": _url_for("inventory"),
            },
            "equipment": {
                "available": runtime.mcp_equipment_available,
                "url": _url_for("equipment"),
            },
            "labor": {
                "available": runtime.mcp_labor_available,
                "url": _url_for("labor"),
            },
            "wave": {
                "available": runtime.mcp_wave_available,
                "url": _url_for("wave"),
            },
        },
        "registered_capabilities": capabilities,
    }


@router.get("/capabilities", response_model=List[str])
async def list_capabilities(runtime=Depends(get_runtime)):
    """List all registered MCP capability names."""
    registry = getattr(runtime, "mcp_registry", None)
    if registry is None:
        return []
    try:
        return registry.all_capabilities()
    except Exception:
        return []
