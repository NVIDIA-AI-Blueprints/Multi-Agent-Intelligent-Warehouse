# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW Equipment MCP Server — official MCP Python SDK v2 (mcp 2.0.0).

MCP protocol version: 2026-07-28

Exposes vendor-neutral warehouse equipment capabilities as MCP tools:

    warehouse.equipment.get_status          — current status/availability of assets (READ)
    warehouse.equipment.get_telemetry       — sensor/telemetry data for an asset (READ)
    warehouse.equipment.assign              — execute approved assignment write (WRITE)
    warehouse.equipment.release             — execute approved release write (WRITE)
    warehouse.equipment.schedule_maintenance — execute approved maintenance write (WRITE)

Architecture invariant
----------------------
MCP tools in this server represent EXECUTABLE warehouse operations only.
Proposal generation (ActionProposal construction) happens locally in the
agent/skill layer — no MCP round-trip is required and none is allowed.

Write tools are called ONLY after EquipmentActionExecutor verifies a bound
APPROVED DecisionResult.  The LLM and DecisionEngine never call write tools
directly.

    MCP Client (MAIWMCPClient using mcp.client.Client)
      ↓ [Streamable HTTP or in-memory transport]
    MCPServer (this file)
      ↓
    EquipmentProvider (configurable backend)
      ↓
    MAIWEquipmentAdapter → EquipmentAssetTools → PostgreSQL
    OR  MockEquipmentProvider (for testing)

Running
-------
    # Development (stdio)
    python -m mcp_servers.equipment.server

    # Production (Streamable HTTP, stateless mode for K8s horizontal scaling)
    MAIW_MCP_TRANSPORT=streamable-http MAIW_MCP_EQUIPMENT_PORT=8766 \\
        python -m mcp_servers.equipment.server

    # In tests — use Client(mcp_server) for in-memory transport (no network)
    async with Client(mcp_server) as client:
        result = await client.call_tool("warehouse.equipment.get_status", {})
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from mcp.server import MCPServer

from maiw_mcp.contracts.equipment import (
    EQUIPMENT_ASSIGN_METADATA,
    EQUIPMENT_GET_STATUS_METADATA,
    EQUIPMENT_GET_TELEMETRY_METADATA,
    EQUIPMENT_RELEASE_METADATA,
    EQUIPMENT_SCHEDULE_MAINTENANCE_METADATA,
    EquipmentExecuteAssignRequest,
    EquipmentExecuteMaintenanceRequest,
    EquipmentExecuteReleaseRequest,
    EquipmentStatusRequest,
    EquipmentTelemetryRequest,
)
from maiw_mcp.errors import BackendUnavailable

logger = logging.getLogger(__name__)

# ── Server instance ───────────────────────────────────────────────────────────

mcp_server = MCPServer(
    "MAIW Equipment Server",
    instructions=(
        "Provides vendor-neutral warehouse equipment capabilities. "
        "Use warehouse.equipment.get_status to query asset availability and fleet status. "
        "Use warehouse.equipment.get_telemetry to retrieve sensor data for a specific asset. "
        "Write tools (assign, release, schedule_maintenance) execute APPROVED operations only — "
        "they require both proposal_id and decision_id bound to an APPROVED DecisionResult."
    ),
)

# ── Provider registry ─────────────────────────────────────────────────────────

_provider = None  # type: Any  # EquipmentProvider | None


def configure_server(provider: Any) -> None:
    """
    Set the backend provider used by this server.

    Must be called before the first tool invocation.
    In production, called once at startup with MAIWEquipmentAdapter.
    In tests, called with MockEquipmentProvider.
    """
    global _provider
    _provider = provider
    logger.info(
        "EquipmentMCPServer: configured with provider %s",
        type(provider).__name__,
    )


def _get_provider() -> Any:
    global _provider
    if _provider is None:
        _provider = _build_default_provider()
    return _provider


def _build_default_provider() -> Any:
    from mcp_servers.equipment.adapters.maiw_backend import MAIWEquipmentAdapter
    from src.api.agents.inventory.equipment_asset_tools import EquipmentAssetTools

    tools = EquipmentAssetTools()
    logger.info("EquipmentMCPServer: using MAIWEquipmentAdapter (PostgreSQL backend)")
    return MAIWEquipmentAdapter(tools)


# ── Tools ─────────────────────────────────────────────────────────────────────


@mcp_server.tool(
    name=EQUIPMENT_GET_STATUS_METADATA.name,
    description=EQUIPMENT_GET_STATUS_METADATA.description,
)
async def warehouse_equipment_get_status(
    asset_id: str | None = None,
    equipment_type: str | None = None,
    zone: str | None = None,
    status_filter: str | None = None,
) -> str:
    """
    Get current status and availability of warehouse equipment.

    Returns a JSON object with ``equipment`` (list of assets), ``summary``
    (counts per type/status), and ``total_count``.
    """
    try:
        request = EquipmentStatusRequest(
            asset_id=asset_id,
            equipment_type=equipment_type,
            zone=zone,
            status_filter=status_filter,
        )
    except Exception as exc:
        return json.dumps({"error": f"Invalid request: {exc}"})

    provider = _get_provider()
    try:
        result = await provider.get_equipment_status(request)
    except BackendUnavailable as exc:
        logger.warning("warehouse.equipment.get_status: BackendUnavailable: %s", exc)
        raise

    return json.dumps(result.model_dump(mode="json"), default=str)


@mcp_server.tool(
    name=EQUIPMENT_GET_TELEMETRY_METADATA.name,
    description=EQUIPMENT_GET_TELEMETRY_METADATA.description,
)
async def warehouse_equipment_get_telemetry(
    asset_id: str,
    metric: str | None = None,
    hours_back: int = 24,
) -> str:
    """
    Get sensor/telemetry data for a specific equipment asset.

    Returns a JSON object with ``telemetry_data`` (time-series points),
    ``available_metrics``, and ``data_points``.
    """
    try:
        request = EquipmentTelemetryRequest(
            asset_id=asset_id,
            metric=metric,
            hours_back=hours_back,
        )
    except Exception as exc:
        return json.dumps({"error": f"Invalid request: {exc}", "asset_id": asset_id})

    provider = _get_provider()
    try:
        result = await provider.get_equipment_telemetry(request)
    except BackendUnavailable as exc:
        logger.warning(
            "warehouse.equipment.get_telemetry: BackendUnavailable for %s: %s",
            asset_id,
            exc,
        )
        raise

    return json.dumps(result.model_dump(mode="json"), default=str)


@mcp_server.tool(
    name=EQUIPMENT_ASSIGN_METADATA.name,
    description=EQUIPMENT_ASSIGN_METADATA.description,
)
async def warehouse_equipment_assign(
    asset_id: str,
    assignee: str,
    proposal_id: str,
    decision_id: str,
    assignment_type: str = "task",
    task_id: str | None = None,
    duration_hours: float | None = None,
    notes: str | None = None,
) -> str:
    """
    Execute an approved equipment assignment write.

    Called ONLY after DecisionEngine returns APPROVED with a bound proposal_id.
    Writes to equipment_assignments and updates asset status.
    """
    try:
        request = EquipmentExecuteAssignRequest(
            asset_id=asset_id,
            assignee=assignee,
            assignment_type=assignment_type,
            task_id=task_id,
            duration_hours=duration_hours,
            notes=notes,
            proposal_id=proposal_id,
            decision_id=decision_id,
        )
    except Exception as exc:
        return json.dumps({"error": f"Invalid request: {exc}", "asset_id": asset_id})

    provider = _get_provider()
    try:
        result = await provider.execute_equipment_assignment(request)
    except BackendUnavailable as exc:
        logger.warning(
            "warehouse.equipment.assign: BackendUnavailable for %s: %s",
            asset_id,
            exc,
        )
        raise

    return json.dumps(result.model_dump(mode="json"), default=str)


@mcp_server.tool(
    name=EQUIPMENT_RELEASE_METADATA.name,
    description=EQUIPMENT_RELEASE_METADATA.description,
)
async def warehouse_equipment_release(
    asset_id: str,
    released_by: str,
    proposal_id: str,
    decision_id: str,
    notes: str | None = None,
) -> str:
    """
    Execute an approved equipment release write.

    Called ONLY after DecisionEngine returns APPROVED with a bound proposal_id.
    """
    try:
        request = EquipmentExecuteReleaseRequest(
            asset_id=asset_id,
            released_by=released_by,
            notes=notes,
            proposal_id=proposal_id,
            decision_id=decision_id,
        )
    except Exception as exc:
        return json.dumps({"error": f"Invalid request: {exc}", "asset_id": asset_id})

    provider = _get_provider()
    try:
        result = await provider.execute_equipment_release(request)
    except BackendUnavailable as exc:
        logger.warning(
            "warehouse.equipment.release: BackendUnavailable for %s: %s",
            asset_id,
            exc,
        )
        raise

    return json.dumps(result.model_dump(mode="json"), default=str)


@mcp_server.tool(
    name=EQUIPMENT_SCHEDULE_MAINTENANCE_METADATA.name,
    description=EQUIPMENT_SCHEDULE_MAINTENANCE_METADATA.description,
)
async def warehouse_equipment_schedule_maintenance(
    asset_id: str,
    maintenance_type: str,
    description: str,
    scheduled_by: str,
    scheduled_for: str,
    proposal_id: str,
    decision_id: str,
    estimated_duration_minutes: int = 60,
    priority: str = "medium",
) -> str:
    """
    Execute an approved maintenance schedule write.

    Called ONLY after DecisionEngine returns APPROVED with a bound proposal_id.
    """
    try:
        request = EquipmentExecuteMaintenanceRequest(
            asset_id=asset_id,
            maintenance_type=maintenance_type,
            description=description,
            scheduled_by=scheduled_by,
            scheduled_for=scheduled_for,
            estimated_duration_minutes=estimated_duration_minutes,
            priority=priority,
            proposal_id=proposal_id,
            decision_id=decision_id,
        )
    except Exception as exc:
        return json.dumps({"error": f"Invalid request: {exc}", "asset_id": asset_id})

    provider = _get_provider()
    try:
        result = await provider.execute_schedule_maintenance(request)
    except BackendUnavailable as exc:
        logger.warning(
            "warehouse.equipment.schedule_maintenance: BackendUnavailable for %s: %s",
            asset_id,
            exc,
        )
        raise

    return json.dumps(result.model_dump(mode="json"), default=str)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    transport = os.getenv("MAIW_MCP_TRANSPORT", "stdio")
    port = int(os.getenv("MAIW_MCP_EQUIPMENT_PORT", "8766"))
    host = os.getenv("MAIW_MCP_EQUIPMENT_HOST", "0.0.0.0")

    if transport == "streamable-http":
        mcp_server.run("streamable-http", host=host, port=port, stateless_http=True)
    elif transport == "sse":
        mcp_server.run("sse", host=host, port=port)
    else:
        mcp_server.run("stdio")
