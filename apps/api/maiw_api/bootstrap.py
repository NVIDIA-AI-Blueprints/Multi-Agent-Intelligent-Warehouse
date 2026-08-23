# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW API Composition Root — Phase 9B.

MAIWRuntime is the single place where the runtime object graph is assembled:

    CapabilityRegistry  (all MCP domains registered)
    MAIWMCPClient       (shared across all skills)
    Read skills         (status, capacity, wave-get)
    WarehouseStateProvider
    Execution skills    (assign, release, maintenance, allocate, reprioritize)
    ActionExecutors     (Equipment, Labor, Wave)
    ModelGateway
    DecisionEngine
    EquipmentAssetOperationsAgent
    OperationsCoordinationAgent
    SafetyComplianceAgent

Dependency direction:
    apps/api → packages/* (one-way)
    packages/* never import from apps/api

Usage:
    from maiw_api.bootstrap import get_runtime
    runtime = await get_runtime()
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_runtime: "MAIWRuntime | None" = None

_EQUIPMENT_CAPABILITIES = [
    "warehouse.equipment.get_status",
    "warehouse.equipment.get_telemetry",
    "warehouse.equipment.assign",
    "warehouse.equipment.release",
    "warehouse.equipment.schedule_maintenance",
]

_LABOR_CAPABILITIES = [
    "warehouse.labor.get_capacity",
    "warehouse.labor.get_allocation",
    "warehouse.labor.allocate",
]

_WAVE_CAPABILITIES = [
    "warehouse.wave.get",
    "warehouse.wave.get_risk",
    "warehouse.wave.reprioritize",
]

_INVENTORY_CAPABILITIES = [
    "warehouse.inventory.get",
    "warehouse.inventory.locate",
]


_DEMO_MODE = os.getenv("MAIW_DEMO_MODE", "false").lower() in ("1", "true", "yes")


@dataclass
class MAIWRuntime:
    """
    Process-level singleton that holds all runtime objects.

    Agents and routers receive dependencies through this container rather than
    constructing their own.  All fields default to None; routers guard against
    None values and return 503 when a required component is unavailable.
    """

    # Demo / simulation controller (only set when MAIW_DEMO_MODE=true)
    demo_controller: Any = None  # maiw_api.demo.controller.DemoScenarioController

    # MCP layer
    mcp_registry: Any = None  # maiw_mcp.CapabilityRegistry
    mcp_client: Any = None  # maiw_mcp.MAIWMCPClient

    # Availability flags (True = successfully initialised at startup)
    mcp_inventory_available: bool = False
    mcp_equipment_available: bool = False
    mcp_labor_available: bool = False
    mcp_wave_available: bool = False

    # Model + decision
    model_gateway: Any = None  # maiw_models.ModelGateway
    decision_engine: Any = None  # maiw_decision.DecisionEngine

    # State
    state_provider: Any = None  # maiw_state.WarehouseStateProvider

    # Executors
    equipment_executor: Any = None  # maiw_execution.EquipmentActionExecutor
    labor_executor: Any = None  # maiw_execution.LaborActionExecutor
    wave_executor: Any = None  # maiw_execution.WaveActionExecutor

    # Canonical agents
    equipment_agent: Any = None  # maiw_agents.equipment.EquipmentAssetOperationsAgent
    operations_agent: Any = None  # maiw_agents.operations.OperationsCoordinationAgent
    safety_agent: Any = None  # maiw_agents.safety.SafetyComplianceAgent


async def get_runtime() -> MAIWRuntime:
    """
    Return (or build) the process-level runtime singleton.

    Safe to call multiple times — returns the cached instance after the
    first successful build.  Called once from the FastAPI lifespan.
    """
    global _runtime
    if _runtime is not None:
        return _runtime

    logger.info("MAIW bootstrap: assembling runtime...")
    runtime = MAIWRuntime()

    # ── 0. Demo mode — SimulationProviders replace DB-backed providers ─────────
    if _DEMO_MODE:
        try:
            from maiw_api.demo.controller import get_demo_controller
            from mcp_servers.inventory.server import configure_server as _cfg_inv
            from mcp_servers.equipment.server import configure_server as _cfg_eq
            from mcp_servers.labor.server import configure_server as _cfg_lab
            from mcp_servers.wave.server import configure_server as _cfg_wave

            ctrl = get_demo_controller()
            _cfg_inv(ctrl.providers.inventory)
            _cfg_eq(ctrl.providers.equipment)
            _cfg_lab(ctrl.providers.labor)
            _cfg_wave(ctrl.providers.wave)
            runtime.demo_controller = ctrl
            logger.info(
                "MAIW bootstrap: DEMO MODE active — "
                "SimulationProviders wired into all four MCP servers"
            )
        except Exception as exc:
            logger.error(
                "MAIW bootstrap: DEMO MODE requested but failed to wire providers — %s", exc
            )

    # ── 1. CapabilityRegistry ──────────────────────────────────────────────────
    try:
        from maiw_mcp.registry.registry import CapabilityRegistry

        registry = CapabilityRegistry()

        inventory_url = os.getenv("MAIW_MCP_SERVER_INVENTORY_URL")
        if inventory_url:
            registry.register_domain(_INVENTORY_CAPABILITIES, inventory_url)
            runtime.mcp_inventory_available = True

        equipment_url = os.getenv("MAIW_MCP_SERVER_EQUIPMENT_URL")
        if equipment_url:
            registry.register_domain(_EQUIPMENT_CAPABILITIES, equipment_url)
            runtime.mcp_equipment_available = True

        labor_url = os.getenv("MAIW_MCP_SERVER_LABOR_URL")
        if labor_url:
            registry.register_domain(_LABOR_CAPABILITIES, labor_url)
            runtime.mcp_labor_available = True

        wave_url = os.getenv("MAIW_MCP_SERVER_WAVE_URL")
        if wave_url:
            registry.register_domain(_WAVE_CAPABILITIES, wave_url)
            runtime.mcp_wave_available = True

        runtime.mcp_registry = registry
        logger.info(
            "MAIW bootstrap: CapabilityRegistry ready — %d capabilities registered",
            len(registry.all_capabilities()),
        )
    except Exception as exc:
        logger.warning("MAIW bootstrap: CapabilityRegistry unavailable — %s", exc)

    # ── 2. MAIWMCPClient ──────────────────────────────────────────────────────
    if runtime.mcp_registry is not None:
        try:
            from maiw_mcp.client.client import MAIWMCPClient

            runtime.mcp_client = MAIWMCPClient(runtime.mcp_registry)
            logger.info("MAIW bootstrap: MAIWMCPClient ready")
        except Exception as exc:
            logger.warning("MAIW bootstrap: MAIWMCPClient unavailable — %s", exc)

    # ── 3. ModelGateway ───────────────────────────────────────────────────────
    try:
        from maiw_models import get_model_gateway

        runtime.model_gateway = await get_model_gateway()
        logger.info("MAIW bootstrap: ModelGateway ready")
    except Exception as exc:
        logger.warning("MAIW bootstrap: ModelGateway unavailable — %s", exc)

    # ── 4. DecisionEngine ─────────────────────────────────────────────────────
    try:
        from maiw_decision import DecisionEngine

        runtime.decision_engine = DecisionEngine()
        logger.info("MAIW bootstrap: DecisionEngine ready")
    except Exception as exc:
        logger.warning("MAIW bootstrap: DecisionEngine unavailable — %s", exc)

    # ── 5. Read skills + WarehouseStateProvider ───────────────────────────────
    if runtime.mcp_client is not None:
        try:
            from maiw_skills.equipment.skills import EquipmentStatusSkill
            from maiw_state import WarehouseStateProvider

            equipment_status_skill = EquipmentStatusSkill(runtime.mcp_client)
            runtime.state_provider = WarehouseStateProvider(
                equipment_status_skill=equipment_status_skill,
            )
            logger.info("MAIW bootstrap: WarehouseStateProvider ready")
        except Exception as exc:
            logger.warning(
                "MAIW bootstrap: WarehouseStateProvider unavailable — %s", exc
            )

    # ── 6. Equipment execution skills + EquipmentActionExecutor ──────────────
    if runtime.mcp_client is not None and runtime.mcp_equipment_available:
        try:
            from maiw_skills.equipment.skills import (
                ExecuteEquipmentAssignmentSkill,
                ExecuteEquipmentMaintenanceSkill,
                ExecuteEquipmentReleaseSkill,
            )
            from maiw_execution import EquipmentActionExecutor

            assign_skill = ExecuteEquipmentAssignmentSkill(runtime.mcp_client)
            release_skill = ExecuteEquipmentReleaseSkill(runtime.mcp_client)
            maintenance_skill = ExecuteEquipmentMaintenanceSkill(runtime.mcp_client)

            runtime.equipment_executor = EquipmentActionExecutor(
                assign_skill=assign_skill,
                release_skill=release_skill,
                maintenance_skill=maintenance_skill,
                state_provider=runtime.state_provider,
            )
            logger.info("MAIW bootstrap: EquipmentActionExecutor ready")
        except Exception as exc:
            logger.warning(
                "MAIW bootstrap: EquipmentActionExecutor unavailable — %s", exc
            )

    # ── 7. Labor execution skill + LaborActionExecutor ────────────────────────
    if runtime.mcp_client is not None and runtime.mcp_labor_available:
        try:
            from maiw_skills.labor.skills import ExecuteLaborAllocationSkill
            from maiw_execution import LaborActionExecutor

            allocate_skill = ExecuteLaborAllocationSkill(runtime.mcp_client)
            runtime.labor_executor = LaborActionExecutor(allocate_skill=allocate_skill)
            logger.info("MAIW bootstrap: LaborActionExecutor ready")
        except Exception as exc:
            logger.warning("MAIW bootstrap: LaborActionExecutor unavailable — %s", exc)

    # ── 8. Wave execution skill + WaveActionExecutor ──────────────────────────
    if runtime.mcp_client is not None and runtime.mcp_wave_available:
        try:
            from maiw_skills.wave.skills import ExecuteWaveReprioritizationSkill
            from maiw_execution import WaveActionExecutor

            reprioritize_skill = ExecuteWaveReprioritizationSkill(runtime.mcp_client)
            runtime.wave_executor = WaveActionExecutor(
                reprioritize_skill=reprioritize_skill
            )
            logger.info("MAIW bootstrap: WaveActionExecutor ready")
        except Exception as exc:
            logger.warning("MAIW bootstrap: WaveActionExecutor unavailable — %s", exc)

    # ── 9. EquipmentAssetOperationsAgent ─────────────────────────────────────
    try:
        from maiw_agents.equipment import EquipmentAssetOperationsAgent
        from maiw_skills.equipment.skills import EquipmentAssignmentSkill

        assignment_skill = EquipmentAssignmentSkill()

        # EquipmentAssetTools is an integration adapter (SQL + MCP reads).
        # It is optional — the agent degrades gracefully without it.
        asset_tools = None
        try:
            from src.api.agents.inventory.equipment_asset_tools import (
                get_equipment_asset_tools,
            )

            asset_tools = await get_equipment_asset_tools()
            logger.info("MAIW bootstrap: EquipmentAssetTools ready")
        except Exception as exc:
            logger.warning("MAIW bootstrap: EquipmentAssetTools unavailable — %s", exc)

        runtime.equipment_agent = EquipmentAssetOperationsAgent(
            model_gateway=runtime.model_gateway,
            asset_tools=asset_tools,
            state_provider=runtime.state_provider,
            decision_engine=runtime.decision_engine,
            assignment_skill=assignment_skill,
            action_executor=runtime.equipment_executor,
        )
        logger.info("MAIW bootstrap: EquipmentAssetOperationsAgent ready")
    except Exception as exc:
        logger.warning(
            "MAIW bootstrap: EquipmentAssetOperationsAgent unavailable — %s", exc
        )

    # ── 10. OperationsCoordinationAgent ───────────────────────────────────────
    try:
        from maiw_agents.operations import OperationsCoordinationAgent

        runtime.operations_agent = OperationsCoordinationAgent(
            model_gateway=runtime.model_gateway,
        )
        logger.info("MAIW bootstrap: OperationsCoordinationAgent ready")
    except Exception as exc:
        logger.warning(
            "MAIW bootstrap: OperationsCoordinationAgent unavailable — %s", exc
        )

    # ── 11. SafetyComplianceAgent ─────────────────────────────────────────────
    try:
        from maiw_agents.safety import SafetyComplianceAgent

        runtime.safety_agent = SafetyComplianceAgent(
            model_gateway=runtime.model_gateway,
        )
        logger.info("MAIW bootstrap: SafetyComplianceAgent ready")
    except Exception as exc:
        logger.warning("MAIW bootstrap: SafetyComplianceAgent unavailable — %s", exc)

    _runtime = runtime
    logger.info("MAIW bootstrap: runtime assembly complete")
    return _runtime


def reset_runtime() -> None:
    """Reset the runtime singleton — for testing only."""
    global _runtime
    _runtime = None
