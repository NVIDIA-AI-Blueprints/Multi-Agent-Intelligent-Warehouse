# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW Labor MCP Server — official MCP Python SDK v2 (mcp 2.0.0).

Exposes vendor-neutral warehouse labor capabilities as MCP tools:

    warehouse.labor.get_capacity    — workforce availability by zone/shift (READ)
    warehouse.labor.get_allocation  — active task assignments per worker (READ)
    warehouse.labor.allocate        — execute approved labor allocation write (WRITE)

Architecture invariant
----------------------
MCP tools expose EXECUTABLE operations only.
Proposal generation (ActionProposal.for_labor_allocate) is built locally in the
agent/skill layer — no MCP round-trip is required.

Write tools are called ONLY after LaborActionExecutor verifies a bound
APPROVED DecisionResult.

    MCP Client
      ↓
    LaborMCPServer (this file)
      ↓
    LaborProvider (configurable backend)
      ↓
    MAIWLaborAdapter → OperationsActionTools → PostgreSQL
    OR  MockLaborProvider (for testing)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from mcp.server import MCPServer

from maiw_contracts.labor import (
    LABOR_ALLOCATE_METADATA,
    LABOR_GET_ALLOCATION_METADATA,
    LABOR_GET_CAPACITY_METADATA,
    LaborAllocateRequest,
    LaborAllocationRequest,
    LaborCapacityRequest,
)
from maiw_mcp.errors import BackendUnavailable, WriteNotApplied
from maiw_mcp.write_disposition import not_applied_result

logger = logging.getLogger(__name__)

# ── Server instance ───────────────────────────────────────────────────────────

mcp_server = MCPServer(
    "MAIW Labor Server",
    instructions=(
        "Provides vendor-neutral warehouse labor capabilities. "
        "Use warehouse.labor.get_capacity to query workforce availability. "
        "Use warehouse.labor.get_allocation to see active task assignments. "
        "Write tools (allocate) execute APPROVED operations only — "
        "they require both proposal_id and decision_id bound to an APPROVED DecisionResult."
    ),
)

# ── Provider registry ─────────────────────────────────────────────────────────

_provider = None  # type: Any


def configure_server(provider: Any) -> None:
    """Set the backend provider used by this server."""
    global _provider
    _provider = provider
    logger.info("LaborMCPServer: configured with provider %s", type(provider).__name__)


def _get_provider() -> Any:
    global _provider
    if _provider is None:
        _provider = _build_default_provider()
    return _provider


def _build_default_provider() -> Any:
    from mcp_servers.labor.adapters.maiw_backend import MAIWLaborAdapter
    logger.info("LaborMCPServer: using MAIWLaborAdapter (PostgreSQL/WMS backend)")
    return MAIWLaborAdapter()


# ── Tools ─────────────────────────────────────────────────────────────────────


@mcp_server.tool(
    name=LABOR_GET_CAPACITY_METADATA.name,
    description=LABOR_GET_CAPACITY_METADATA.description,
)
async def warehouse_labor_get_capacity(
    warehouse_id: str = "default",
    zone: str | None = None,
    shift: str | None = None,
    status_filter: str = "active",
) -> str:
    provider = _get_provider()
    req = LaborCapacityRequest(
        warehouse_id=warehouse_id,
        zone=zone,
        shift=shift,
        status_filter=status_filter,
    )
    try:
        result = await provider.get_labor_capacity(req)
    except Exception as exc:
        raise BackendUnavailable(f"Labor capacity fetch failed: {exc}") from exc
    return json.dumps(result.model_dump())


@mcp_server.tool(
    name=LABOR_GET_ALLOCATION_METADATA.name,
    description=LABOR_GET_ALLOCATION_METADATA.description,
)
async def warehouse_labor_get_allocation(
    warehouse_id: str = "default",
    worker_id: str | None = None,
    zone: str | None = None,
    task_type: str | None = None,
    status_filter: str | None = None,
) -> str:
    provider = _get_provider()
    req = LaborAllocationRequest(
        warehouse_id=warehouse_id,
        worker_id=worker_id,
        zone=zone,
        task_type=task_type,
        status_filter=status_filter,
    )
    try:
        result = await provider.get_labor_allocation(req)
    except Exception as exc:
        raise BackendUnavailable(f"Labor allocation fetch failed: {exc}") from exc
    return json.dumps(result.model_dump())


@mcp_server.tool(
    name=LABOR_ALLOCATE_METADATA.name,
    description=LABOR_ALLOCATE_METADATA.description,
)
async def warehouse_labor_allocate(
    warehouse_id: str,
    task_id: str,
    task_type: str,
    worker_ids: list[str],
    proposal_id: str,
    decision_id: str,
    zone: str | None = None,
    priority: str = "medium",
    notes: str | None = None,
    execution_id: str | None = None,
) -> str:
    provider = _get_provider()
    req = LaborAllocateRequest(
        warehouse_id=warehouse_id,
        task_id=task_id,
        task_type=task_type,
        worker_ids=worker_ids,
        zone=zone,
        priority=priority,
        notes=notes,
        proposal_id=proposal_id,
        decision_id=decision_id,
        execution_id=execution_id,
    )
    try:
        result = await provider.execute_labor_allocation(req)
    except WriteNotApplied as exc:
        # v2.0.1 round 4: the provider certified no mutation → typed NOT_APPLIED
        return not_applied_result(str(exc), exc.rejection_code)
    except Exception as exc:
        raise BackendUnavailable(f"Labor allocation write failed: {exc}") from exc
    return json.dumps(result.model_dump())


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Dockerfile.mcp runs ``python -m mcp_servers.labor.server``; without this
    # block the module only imported, exited 0 and the container restart-looped.
    transport = os.getenv("MAIW_MCP_TRANSPORT", "stdio")
    port = int(os.getenv("MAIW_MCP_LABOR_PORT", "8767"))
    host = os.getenv("MAIW_MCP_LABOR_HOST", "0.0.0.0")

    if transport == "streamable-http":
        mcp_server.run("streamable-http", host=host, port=port, stateless_http=True)
    elif transport == "sse":
        mcp_server.run("sse", host=host, port=port)
    else:
        mcp_server.run("stdio")
