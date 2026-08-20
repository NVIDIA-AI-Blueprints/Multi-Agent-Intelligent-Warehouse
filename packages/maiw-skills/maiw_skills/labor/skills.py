# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Labor skills — operational bridge between agents and Labor MCP v2.

Read skills (no side effects):
    LaborCapacitySkill       — warehouse.labor.get_capacity  (read)
    LaborAllocationSkill     — warehouse.labor.get_allocation (read)

Proposal skills (build ActionProposal locally, no MCP call):
    ProposeLaborAllocationSkill  — builds ActionProposal.for_labor_allocate() in-process

Execution skills (called only after DecisionEngine APPROVED):
    ExecuteLaborAllocationSkill  — warehouse.labor.allocate

Architecture invariant
----------------------
Proposal skills NEVER call MCP.  Only execution skills reach MCP write capabilities,
and only after LaborActionExecutor has verified a bound APPROVED DecisionResult.
"""

from __future__ import annotations

import logging
import os

from maiw_mcp.client.client import MAIWMCPClient
from maiw_mcp.contracts.actions import ActionProposal
from maiw_mcp.contracts.labor import (
    LABOR_ALLOCATE_METADATA,
    LABOR_GET_ALLOCATION_METADATA,
    LABOR_GET_CAPACITY_METADATA,
    LaborAllocateRequest,
    LaborAllocateResult,
    LaborAllocationRequest,
    LaborAllocationResult,
    LaborCapacityRequest,
    LaborCapacityResult,
)
from maiw_mcp.errors import MCPContractError
from maiw_mcp.registry.registry import CapabilityRegistry
from maiw_mcp.telemetry.telemetry import CapabilityTelemetry

logger = logging.getLogger(__name__)


class LaborCapacitySkill:
    """Workforce capacity lookup via warehouse.labor.get_capacity MCP tool."""

    def __init__(self, client: MAIWMCPClient) -> None:
        self._client = client

    async def execute(
        self,
        request: LaborCapacityRequest,
        *,
        trace_id: str | None = None,
    ) -> LaborCapacityResult:
        payload = request.model_dump(exclude_none=True)
        raw = await self._client.invoke(LABOR_GET_CAPACITY_METADATA.name, payload)
        try:
            return LaborCapacityResult.model_validate(raw)
        except Exception as exc:
            raise MCPContractError(
                f"warehouse.labor.get_capacity result failed contract validation: {exc}"
            ) from exc


class LaborAllocationSkill:
    """Task allocation lookup via warehouse.labor.get_allocation MCP tool."""

    def __init__(self, client: MAIWMCPClient) -> None:
        self._client = client

    async def execute(
        self,
        request: LaborAllocationRequest,
        *,
        trace_id: str | None = None,
    ) -> LaborAllocationResult:
        payload = request.model_dump(exclude_none=True)
        raw = await self._client.invoke(LABOR_GET_ALLOCATION_METADATA.name, payload)
        try:
            return LaborAllocationResult.model_validate(raw)
        except Exception as exc:
            raise MCPContractError(
                f"warehouse.labor.get_allocation result failed contract validation: {exc}"
            ) from exc


class ProposeLaborAllocationSkill:
    """
    Labor allocation proposal — built locally without an MCP call.

    Architecture invariant: this skill NEVER calls MCP.
    """

    async def execute(
        self,
        *,
        task_id: str,
        task_type: str,
        worker_ids: list[str],
        zone: str | None = None,
        priority: str = "medium",
        notes: str | None = None,
        reason: str = "",
        requested_by: str = "operations-agent",
        warehouse_id: str = "default",
        trace_id: str | None = None,
    ) -> ActionProposal:
        return ActionProposal.for_labor_allocate(
            task_id=task_id,
            task_type=task_type,
            worker_ids=worker_ids,
            zone=zone,
            priority=priority,
            notes=notes,
            reason=reason,
            requested_by=requested_by,
            warehouse_id=warehouse_id,
            trace_id=trace_id,
        )


class ExecuteLaborAllocationSkill:
    """Execute an approved labor allocation via warehouse.labor.allocate MCP tool."""

    def __init__(self, client: MAIWMCPClient) -> None:
        self._client = client

    async def execute(
        self,
        request: LaborAllocateRequest,
    ) -> LaborAllocateResult:
        payload = request.model_dump(exclude_none=True)
        raw = await self._client.invoke(LABOR_ALLOCATE_METADATA.name, payload)
        try:
            return LaborAllocateResult.model_validate(raw)
        except Exception as exc:
            raise MCPContractError(
                f"warehouse.labor.allocate result failed contract validation: {exc}"
            ) from exc


# ── Singleton factories ────────────────────────────────────────────────────────

_labor_capacity_skill: LaborCapacitySkill | None = None
_labor_allocation_skill: LaborAllocationSkill | None = None
_propose_labor_allocation_skill: ProposeLaborAllocationSkill | None = None
_execute_labor_allocation_skill: ExecuteLaborAllocationSkill | None = None


async def get_labor_capacity_skill() -> LaborCapacitySkill:
    """
    Return the process-level LaborCapacitySkill singleton.
    Reads ``MAIW_MCP_SERVER_LABOR_URL`` from the environment.
    """
    global _labor_capacity_skill
    if _labor_capacity_skill is None:
        url = os.environ.get("MAIW_MCP_SERVER_LABOR_URL")
        if not url:
            raise RuntimeError(
                "MAIW_MCP_SERVER_LABOR_URL not set — cannot create LaborCapacitySkill"
            )
        registry = CapabilityRegistry()
        registry.register(LABOR_GET_CAPACITY_METADATA)
        telemetry = CapabilityTelemetry()
        client = MAIWMCPClient(server_url=url, registry=registry, telemetry=telemetry)
        _labor_capacity_skill = LaborCapacitySkill(client)
        logger.info("LaborCapacitySkill initialised (url=%s)", url)
    return _labor_capacity_skill


async def get_labor_allocation_skill() -> LaborAllocationSkill:
    global _labor_allocation_skill
    if _labor_allocation_skill is None:
        url = os.environ.get("MAIW_MCP_SERVER_LABOR_URL")
        if not url:
            raise RuntimeError(
                "MAIW_MCP_SERVER_LABOR_URL not set — cannot create LaborAllocationSkill"
            )
        registry = CapabilityRegistry()
        registry.register(LABOR_GET_ALLOCATION_METADATA)
        telemetry = CapabilityTelemetry()
        client = MAIWMCPClient(server_url=url, registry=registry, telemetry=telemetry)
        _labor_allocation_skill = LaborAllocationSkill(client)
        logger.info("LaborAllocationSkill initialised (url=%s)", url)
    return _labor_allocation_skill


async def get_propose_labor_allocation_skill() -> ProposeLaborAllocationSkill:
    global _propose_labor_allocation_skill
    if _propose_labor_allocation_skill is None:
        _propose_labor_allocation_skill = ProposeLaborAllocationSkill()
        logger.info("ProposeLaborAllocationSkill initialised (local proposal builder, no MCP)")
    return _propose_labor_allocation_skill


async def get_execute_labor_allocation_skill() -> ExecuteLaborAllocationSkill:
    global _execute_labor_allocation_skill
    if _execute_labor_allocation_skill is None:
        url = os.environ.get("MAIW_MCP_SERVER_LABOR_URL")
        if not url:
            raise RuntimeError(
                "MAIW_MCP_SERVER_LABOR_URL not set — cannot create ExecuteLaborAllocationSkill"
            )
        registry = CapabilityRegistry()
        registry.register(LABOR_ALLOCATE_METADATA)
        telemetry = CapabilityTelemetry()
        client = MAIWMCPClient(server_url=url, registry=registry, telemetry=telemetry)
        _execute_labor_allocation_skill = ExecuteLaborAllocationSkill(client)
        logger.info("ExecuteLaborAllocationSkill initialised (url=%s)", url)
    return _execute_labor_allocation_skill
