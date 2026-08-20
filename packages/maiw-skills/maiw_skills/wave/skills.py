# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Wave skills — operational bridge between agents and Wave MCP v2.

Read skills (no side effects):
    WaveGetSkill             — warehouse.wave.get  (read)
    WaveRiskSkill            — warehouse.wave.get_risk (read/computation)

Proposal skills (build ActionProposal locally, no MCP call):
    ProposeWaveReprioritizationSkill  — builds ActionProposal.for_wave_reprioritize() in-process

Execution skills (called only after DecisionEngine APPROVED):
    ExecuteWaveReprioritizationSkill  — warehouse.wave.reprioritize

Architecture invariant
----------------------
Proposal skills NEVER call MCP.  Only execution skills reach MCP write capabilities,
and only after WaveActionExecutor has verified a bound APPROVED DecisionResult.
"""

from __future__ import annotations

import logging
import os

from maiw_mcp.client.client import MAIWMCPClient
from maiw_mcp.contracts.actions import ActionProposal
from maiw_mcp.contracts.wave import (
    WAVE_GET_METADATA,
    WAVE_GET_RISK_METADATA,
    WAVE_REPRIORITIZE_METADATA,
    WaveGetRequest,
    WaveGetResult,
    WaveReprioritizeRequest,
    WaveReprioritizeResult,
    WaveRiskRequest,
    WaveRiskResult,
)
from maiw_mcp.errors import MCPContractError
from maiw_mcp.registry.registry import CapabilityRegistry
from maiw_mcp.telemetry.telemetry import CapabilityTelemetry

logger = logging.getLogger(__name__)


class WaveGetSkill:
    """Wave task context lookup via warehouse.wave.get MCP tool."""

    def __init__(self, client: MAIWMCPClient) -> None:
        self._client = client

    async def execute(
        self,
        request: WaveGetRequest,
        *,
        trace_id: str | None = None,
    ) -> WaveGetResult:
        payload = request.model_dump(exclude_none=True)
        raw = await self._client.invoke(WAVE_GET_METADATA.name, payload)
        try:
            return WaveGetResult.model_validate(raw)
        except Exception as exc:
            raise MCPContractError(
                f"warehouse.wave.get result failed contract validation: {exc}"
            ) from exc


class WaveRiskSkill:
    """Wave OTIF risk assessment via warehouse.wave.get_risk MCP tool."""

    def __init__(self, client: MAIWMCPClient) -> None:
        self._client = client

    async def execute(
        self,
        request: WaveRiskRequest,
        *,
        trace_id: str | None = None,
    ) -> WaveRiskResult:
        payload = request.model_dump(exclude_none=True)
        raw = await self._client.invoke(WAVE_GET_RISK_METADATA.name, payload)
        try:
            return WaveRiskResult.model_validate(raw)
        except Exception as exc:
            raise MCPContractError(
                f"warehouse.wave.get_risk result failed contract validation: {exc}"
            ) from exc


class ProposeWaveReprioritizationSkill:
    """
    Wave reprioritization proposal — built locally without an MCP call.

    Architecture invariant: this skill NEVER calls MCP.
    """

    async def execute(
        self,
        *,
        wave_id: str | None = None,
        zone: str | None = None,
        new_priority: str,
        reason: str = "",
        requested_by: str = "operations-agent",
        warehouse_id: str = "default",
        trace_id: str | None = None,
    ) -> ActionProposal:
        return ActionProposal.for_wave_reprioritize(
            wave_id=wave_id,
            zone=zone,
            new_priority=new_priority,
            reason=reason,
            requested_by=requested_by,
            warehouse_id=warehouse_id,
            trace_id=trace_id,
        )


class ExecuteWaveReprioritizationSkill:
    """Execute an approved wave reprioritization via warehouse.wave.reprioritize MCP tool."""

    def __init__(self, client: MAIWMCPClient) -> None:
        self._client = client

    async def execute(
        self,
        request: WaveReprioritizeRequest,
    ) -> WaveReprioritizeResult:
        payload = request.model_dump(exclude_none=True)
        raw = await self._client.invoke(WAVE_REPRIORITIZE_METADATA.name, payload)
        try:
            return WaveReprioritizeResult.model_validate(raw)
        except Exception as exc:
            raise MCPContractError(
                f"warehouse.wave.reprioritize result failed contract validation: {exc}"
            ) from exc


# ── Singleton factories ────────────────────────────────────────────────────────

_wave_get_skill: WaveGetSkill | None = None
_wave_risk_skill: WaveRiskSkill | None = None
_propose_wave_reprioritization_skill: ProposeWaveReprioritizationSkill | None = None
_execute_wave_reprioritization_skill: ExecuteWaveReprioritizationSkill | None = None


async def get_wave_get_skill() -> WaveGetSkill:
    global _wave_get_skill
    if _wave_get_skill is None:
        url = os.environ.get("MAIW_MCP_SERVER_WAVE_URL")
        if not url:
            raise RuntimeError(
                "MAIW_MCP_SERVER_WAVE_URL not set — cannot create WaveGetSkill"
            )
        registry = CapabilityRegistry()
        registry.register(WAVE_GET_METADATA)
        telemetry = CapabilityTelemetry()
        client = MAIWMCPClient(server_url=url, registry=registry, telemetry=telemetry)
        _wave_get_skill = WaveGetSkill(client)
        logger.info("WaveGetSkill initialised (url=%s)", url)
    return _wave_get_skill


async def get_wave_risk_skill() -> WaveRiskSkill:
    global _wave_risk_skill
    if _wave_risk_skill is None:
        url = os.environ.get("MAIW_MCP_SERVER_WAVE_URL")
        if not url:
            raise RuntimeError(
                "MAIW_MCP_SERVER_WAVE_URL not set — cannot create WaveRiskSkill"
            )
        registry = CapabilityRegistry()
        registry.register(WAVE_GET_RISK_METADATA)
        telemetry = CapabilityTelemetry()
        client = MAIWMCPClient(server_url=url, registry=registry, telemetry=telemetry)
        _wave_risk_skill = WaveRiskSkill(client)
        logger.info("WaveRiskSkill initialised (url=%s)", url)
    return _wave_risk_skill


async def get_propose_wave_reprioritization_skill() -> ProposeWaveReprioritizationSkill:
    global _propose_wave_reprioritization_skill
    if _propose_wave_reprioritization_skill is None:
        _propose_wave_reprioritization_skill = ProposeWaveReprioritizationSkill()
        logger.info("ProposeWaveReprioritizationSkill initialised (local proposal builder, no MCP)")
    return _propose_wave_reprioritization_skill


async def get_execute_wave_reprioritization_skill() -> ExecuteWaveReprioritizationSkill:
    global _execute_wave_reprioritization_skill
    if _execute_wave_reprioritization_skill is None:
        url = os.environ.get("MAIW_MCP_SERVER_WAVE_URL")
        if not url:
            raise RuntimeError(
                "MAIW_MCP_SERVER_WAVE_URL not set — cannot create ExecuteWaveReprioritizationSkill"
            )
        registry = CapabilityRegistry()
        registry.register(WAVE_REPRIORITIZE_METADATA)
        telemetry = CapabilityTelemetry()
        client = MAIWMCPClient(server_url=url, registry=registry, telemetry=telemetry)
        _execute_wave_reprioritization_skill = ExecuteWaveReprioritizationSkill(client)
        logger.info("ExecuteWaveReprioritizationSkill initialised (url=%s)", url)
    return _execute_wave_reprioritization_skill
