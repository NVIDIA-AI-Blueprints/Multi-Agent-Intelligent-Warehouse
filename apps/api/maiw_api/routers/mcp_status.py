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
                "inventory":  { "available": true,  "transport": "url",
                                "url": "http://..." },
                "equipment":  { "available": true,  "transport": "in-memory",
                                "url": null },
                "labor":      { "available": false, "transport": null,
                                "url": null },
                "wave":       { "available": false, "transport": null,
                                "url": null },
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

    endpoints = getattr(runtime, "mcp_domain_endpoints", None)
    if not isinstance(endpoints, dict):
        endpoints = {}

    def _domain(domain: str) -> Dict[str, Any]:
        # Transport is reported as /api/v1/ready's mcp_domains does: "url" for
        # HTTP servers, "in-memory" for the in-process MCPServer instances
        # Demo Mode registers.  Only a URL string is ever returned as "url" —
        # registry.resolve() yields an MCPServer object for in-memory domains.
        transport, url = endpoints.get(domain, (None, None))
        if transport is None and registry is not None:
            for cap in capabilities:
                if cap.startswith(f"warehouse.{domain}."):
                    try:
                        target = registry.resolve(cap)
                    except Exception:
                        continue
                    if isinstance(target, str):
                        transport, url = "url", target
                    else:
                        transport = "in-memory"
                    break
        return {
            "available": getattr(runtime, f"mcp_{domain}_available", False),
            "transport": transport,
            "url": url if transport == "url" and isinstance(url, str) else None,
        }

    return {
        "protocol": "MCP 2026-07-28",
        "client_ready": runtime.mcp_client is not None,
        "domains": {
            domain: _domain(domain)
            for domain in ("inventory", "equipment", "labor", "wave")
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
