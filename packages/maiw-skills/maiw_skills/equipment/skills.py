# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Equipment skills — the operational bridge between agents and MCP v2.

Read skills (no side effects):
    EquipmentStatusSkill      — warehouse.equipment.get_status  (read)
    EquipmentTelemetrySkill   — warehouse.equipment.get_telemetry (read)

Proposal skills (build ActionProposal locally, no MCP call):
    EquipmentAssignmentSkill  — builds ActionProposal.for_equipment_assign() in-process

Execution skills (called only after DecisionEngine APPROVED):
    ExecuteEquipmentAssignmentSkill  — warehouse.equipment.assign
    ExecuteEquipmentReleaseSkill     — warehouse.equipment.release
    ExecuteEquipmentMaintenanceSkill — warehouse.equipment.schedule_maintenance

Architecture invariant
----------------------
Proposal skills NEVER call MCP.  They construct ActionProposal objects locally
and return them to the agent layer for forwarding to DecisionEngine.  Only
execution skills reach MCP write capabilities, and only after EquipmentActionExecutor
has verified a bound APPROVED DecisionResult.
"""

from __future__ import annotations

import logging
import os

from maiw_mcp.client.client import MAIWMCPClient
from maiw_mcp.contracts.actions import ActionProposal
from maiw_mcp.contracts.equipment import (
    EQUIPMENT_ASSIGN_METADATA,
    EQUIPMENT_GET_STATUS_METADATA,
    EQUIPMENT_GET_TELEMETRY_METADATA,
    EQUIPMENT_RELEASE_METADATA,
    EQUIPMENT_SCHEDULE_MAINTENANCE_METADATA,
    EquipmentAssignmentRequest,
    EquipmentExecuteAssignRequest,
    EquipmentExecuteAssignResult,
    EquipmentExecuteMaintenanceRequest,
    EquipmentExecuteMaintenanceResult,
    EquipmentExecuteReleaseRequest,
    EquipmentExecuteReleaseResult,
    EquipmentStatusRequest,
    EquipmentStatusResult,
    EquipmentTelemetryRequest,
    EquipmentTelemetryResult,
)
from maiw_mcp.errors import MCPContractError, MAIWMCPError
from maiw_mcp.registry.registry import CapabilityRegistry
from maiw_mcp.telemetry.telemetry import CapabilityTelemetry

logger = logging.getLogger(__name__)


class EquipmentStatusSkill:
    """
    Warehouse equipment status lookup via MCP v2.

    Maps the agent's semantic need ("I need to know the status of equipment
    in zone X") to the MCP capability ``warehouse.equipment.get_status``.
    """

    def __init__(self, client: MAIWMCPClient) -> None:
        self._client = client

    async def execute(
        self,
        request: EquipmentStatusRequest,
        *,
        trace_id: str | None = None,
    ) -> EquipmentStatusResult:
        """
        Retrieve equipment status via the MCP v2 equipment server.

        Parameters
        ----------
        request:
            Validated status request.  All filters are optional.
        trace_id:
            Correlation ID propagated from the calling agent span.

        Returns
        -------
        EquipmentStatusResult

        Raises
        ------
        MAIWMCPError
            Any transport, protocol, or contract error.
        """
        payload = request.model_dump(exclude_none=True)
        raw = await self._client.invoke(
            EQUIPMENT_GET_STATUS_METADATA.name,
            payload,
            trace_id=trace_id,
        )

        try:
            return EquipmentStatusResult.model_validate(raw)
        except Exception as exc:
            raise MCPContractError(
                f"warehouse.equipment.get_status result failed contract validation: {exc}"
            ) from exc


class EquipmentTelemetrySkill:
    """
    Equipment telemetry lookup via MCP v2.

    Maps the agent's need ("I need sensor data for asset AMR-001 from the
    last 24 hours") to ``warehouse.equipment.get_telemetry``.
    """

    def __init__(self, client: MAIWMCPClient) -> None:
        self._client = client

    async def execute(
        self,
        request: EquipmentTelemetryRequest,
        *,
        trace_id: str | None = None,
    ) -> EquipmentTelemetryResult:
        """
        Retrieve equipment telemetry via the MCP v2 equipment server.

        Parameters
        ----------
        request:
            Validated telemetry request.  ``asset_id`` is required.
        trace_id:
            Correlation ID propagated from the calling agent span.

        Returns
        -------
        EquipmentTelemetryResult

        Raises
        ------
        MAIWMCPError
            Any transport, protocol, or contract error.
        """
        payload = request.model_dump(exclude_none=True)
        raw = await self._client.invoke(
            EQUIPMENT_GET_TELEMETRY_METADATA.name,
            payload,
            trace_id=trace_id,
        )

        try:
            return EquipmentTelemetryResult.model_validate(raw)
        except Exception as exc:
            raise MCPContractError(
                f"warehouse.equipment.get_telemetry result failed contract validation: {exc}"
            ) from exc


class EquipmentAssignmentSkill:
    """
    Equipment assignment proposal — built locally without an MCP call.

    Constructs an ActionProposal.for_equipment_assign() in-process.
    The proposal is returned to the caller for forwarding to DecisionEngine.

    Architecture invariant: this skill NEVER calls MCP.  No client is required.
    """

    async def execute(
        self,
        request: EquipmentAssignmentRequest,
        *,
        trace_id: str | None = None,
    ) -> ActionProposal:
        """
        Build an assignment ActionProposal locally.

        Returns
        -------
        ActionProposal
            Proposal for the assignment — not yet executed.
        """
        return ActionProposal.for_equipment_assign(
            asset_id=request.asset_id,
            assignee=request.assignee,
            assignment_type=request.assignment_type,
            task_id=request.task_id,
            duration_hours=request.duration_hours,
            notes=request.notes,
            reason=request.reason,
            requested_by=request.requested_by,
            trace_id=trace_id,
        )


class ExecuteEquipmentAssignmentSkill:
    """Execute an approved equipment assignment via warehouse.equipment.assign."""

    def __init__(self, client: MAIWMCPClient) -> None:
        self._client = client

    async def execute(
        self,
        request: EquipmentExecuteAssignRequest,
    ) -> EquipmentExecuteAssignResult:
        payload = request.model_dump(exclude_none=True)
        raw = await self._client.invoke(
            EQUIPMENT_ASSIGN_METADATA.name,
            payload,
        )
        try:
            return EquipmentExecuteAssignResult.model_validate(raw)
        except Exception as exc:
            raise MCPContractError(
                f"warehouse.equipment.assign result failed contract validation: {exc}"
            ) from exc


class ExecuteEquipmentReleaseSkill:
    """Execute an approved equipment release via warehouse.equipment.release."""

    def __init__(self, client: MAIWMCPClient) -> None:
        self._client = client

    async def execute(
        self,
        request: EquipmentExecuteReleaseRequest,
    ) -> EquipmentExecuteReleaseResult:
        payload = request.model_dump(exclude_none=True)
        raw = await self._client.invoke(
            EQUIPMENT_RELEASE_METADATA.name,
            payload,
        )
        try:
            return EquipmentExecuteReleaseResult.model_validate(raw)
        except Exception as exc:
            raise MCPContractError(
                f"warehouse.equipment.release result failed contract validation: {exc}"
            ) from exc


class ExecuteEquipmentMaintenanceSkill:
    """Execute an approved maintenance schedule via warehouse.equipment.schedule_maintenance."""

    def __init__(self, client: MAIWMCPClient) -> None:
        self._client = client

    async def execute(
        self,
        request: EquipmentExecuteMaintenanceRequest,
    ) -> EquipmentExecuteMaintenanceResult:
        payload = request.model_dump(exclude_none=True)
        raw = await self._client.invoke(
            EQUIPMENT_SCHEDULE_MAINTENANCE_METADATA.name,
            payload,
        )
        try:
            return EquipmentExecuteMaintenanceResult.model_validate(raw)
        except Exception as exc:
            raise MCPContractError(
                f"warehouse.equipment.schedule_maintenance result failed contract validation: {exc}"
            ) from exc


# ── Singleton factories ────────────────────────────────────────────────────────

_equipment_status_skill: EquipmentStatusSkill | None = None
_equipment_telemetry_skill: EquipmentTelemetrySkill | None = None
_equipment_assignment_skill: EquipmentAssignmentSkill | None = None
_execute_equipment_assignment_skill: ExecuteEquipmentAssignmentSkill | None = None
_execute_equipment_release_skill: ExecuteEquipmentReleaseSkill | None = None
_execute_equipment_maintenance_skill: ExecuteEquipmentMaintenanceSkill | None = None


async def get_equipment_status_skill() -> EquipmentStatusSkill:
    """
    Return the process-level EquipmentStatusSkill singleton.

    Reads ``MAIW_MCP_SERVER_EQUIPMENT_URL`` from the environment.

    Raises
    ------
    RuntimeError
        If ``MAIW_MCP_SERVER_EQUIPMENT_URL`` is not set.
    """
    global _equipment_status_skill
    if _equipment_status_skill is None:
        registry = CapabilityRegistry.from_env()
        telemetry = CapabilityTelemetry()
        client = MAIWMCPClient(registry, telemetry=telemetry)
        _equipment_status_skill = EquipmentStatusSkill(client)
        logger.info(
            "EquipmentStatusSkill initialised. Capabilities: %s",
            registry.all_capabilities(),
        )
    return _equipment_status_skill


async def get_equipment_telemetry_skill() -> EquipmentTelemetrySkill:
    """Return the process-level EquipmentTelemetrySkill singleton."""
    global _equipment_telemetry_skill
    if _equipment_telemetry_skill is None:
        registry = CapabilityRegistry.from_env()
        telemetry = CapabilityTelemetry()
        client = MAIWMCPClient(registry, telemetry=telemetry)
        _equipment_telemetry_skill = EquipmentTelemetrySkill(client)
        logger.info(
            "EquipmentTelemetrySkill initialised. Capabilities: %s",
            registry.all_capabilities(),
        )
    return _equipment_telemetry_skill


async def get_equipment_assignment_skill() -> EquipmentAssignmentSkill:
    """Return the process-level EquipmentAssignmentSkill singleton.

    No MCP client needed — proposals are built locally.
    """
    global _equipment_assignment_skill
    if _equipment_assignment_skill is None:
        _equipment_assignment_skill = EquipmentAssignmentSkill()
        logger.info(
            "EquipmentAssignmentSkill initialised (local proposal builder, no MCP)."
        )
    return _equipment_assignment_skill


async def get_execute_equipment_assignment_skill() -> ExecuteEquipmentAssignmentSkill:
    """Return the process-level ExecuteEquipmentAssignmentSkill singleton."""
    global _execute_equipment_assignment_skill
    if _execute_equipment_assignment_skill is None:
        registry = CapabilityRegistry.from_env()
        telemetry = CapabilityTelemetry()
        client = MAIWMCPClient(registry, telemetry=telemetry)
        _execute_equipment_assignment_skill = ExecuteEquipmentAssignmentSkill(client)
        logger.info("ExecuteEquipmentAssignmentSkill initialised.")
    return _execute_equipment_assignment_skill


async def get_execute_equipment_release_skill() -> ExecuteEquipmentReleaseSkill:
    """Return the process-level ExecuteEquipmentReleaseSkill singleton."""
    global _execute_equipment_release_skill
    if _execute_equipment_release_skill is None:
        registry = CapabilityRegistry.from_env()
        telemetry = CapabilityTelemetry()
        client = MAIWMCPClient(registry, telemetry=telemetry)
        _execute_equipment_release_skill = ExecuteEquipmentReleaseSkill(client)
        logger.info("ExecuteEquipmentReleaseSkill initialised.")
    return _execute_equipment_release_skill


async def get_execute_equipment_maintenance_skill() -> ExecuteEquipmentMaintenanceSkill:
    """Return the process-level ExecuteEquipmentMaintenanceSkill singleton."""
    global _execute_equipment_maintenance_skill
    if _execute_equipment_maintenance_skill is None:
        registry = CapabilityRegistry.from_env()
        telemetry = CapabilityTelemetry()
        client = MAIWMCPClient(registry, telemetry=telemetry)
        _execute_equipment_maintenance_skill = ExecuteEquipmentMaintenanceSkill(client)
        logger.info("ExecuteEquipmentMaintenanceSkill initialised.")
    return _execute_equipment_maintenance_skill


def reset_equipment_skills() -> None:
    """Reset all equipment skill singletons — for testing only."""
    global _equipment_status_skill, _equipment_telemetry_skill, _equipment_assignment_skill
    global _execute_equipment_assignment_skill, _execute_equipment_release_skill, _execute_equipment_maintenance_skill
    _equipment_status_skill = None
    _equipment_telemetry_skill = None
    _equipment_assignment_skill = None
    _execute_equipment_assignment_skill = None
    _execute_equipment_release_skill = None
    _execute_equipment_maintenance_skill = None
