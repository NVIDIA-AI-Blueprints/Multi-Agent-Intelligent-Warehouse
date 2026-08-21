# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW API Composition Root.

This module is the single place where the runtime object graph is assembled:

    ModelGateway
    MCP clients (per domain)
    StateProvider
    DecisionEngine
    ActionExecutors (Equipment, Labor, Wave)
    Agent instances

Phase 8 status: Structure is defined; full wiring is deferred to Phase 9
when agents are migrated from src/api/agents/ to packages/maiw-agents/.

Usage:
    from apps.api.maiw_api.bootstrap import get_runtime
    runtime = await get_runtime()
    gateway = runtime.model_gateway
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_runtime: "MAIWRuntime | None" = None


@dataclass
class MAIWRuntime:
    """
    Container for all lazily-initialized runtime singletons.

    Agents and routers receive runtime objects through this container rather
    than constructing their own dependencies.
    """

    model_gateway: Any = None  # maiw_models.ModelGateway
    decision_engine: Any = None  # maiw_decision.DecisionEngine
    equipment_executor: Any = None  # EquipmentActionExecutor
    labor_executor: Any = None  # LaborActionExecutor
    wave_executor: Any = None  # WaveActionExecutor
    state_provider: Any = None  # WarehouseStateProvider


async def get_runtime() -> MAIWRuntime:
    """
    Return (or build) the process-level runtime singleton.

    Call once at application startup; subsequent calls return the same object.
    """
    global _runtime
    if _runtime is not None:
        return _runtime

    logger.info("MAIW bootstrap: assembling runtime...")
    runtime = MAIWRuntime()

    # ModelGateway
    try:
        from maiw_models import get_model_gateway
        runtime.model_gateway = await get_model_gateway()
        logger.info("MAIW bootstrap: ModelGateway ready")
    except Exception as exc:
        logger.warning("MAIW bootstrap: ModelGateway unavailable — %s", exc)

    # DecisionEngine (synchronous, no I/O)
    try:
        from maiw_decision import DecisionEngine
        runtime.decision_engine = DecisionEngine()
        logger.info("MAIW bootstrap: DecisionEngine ready")
    except Exception as exc:
        logger.warning("MAIW bootstrap: DecisionEngine unavailable — %s", exc)

    # EquipmentActionExecutor
    try:
        from src.api.agents.inventory.action_executor import EquipmentActionExecutor
        from maiw_skills.equipment import (
            get_execute_equipment_assignment_skill,
            get_execute_equipment_release_skill,
            get_execute_equipment_maintenance_skill,
        )
        runtime.equipment_executor = EquipmentActionExecutor(
            assign_skill=await get_execute_equipment_assignment_skill(),
            release_skill=await get_execute_equipment_release_skill(),
            maintenance_skill=await get_execute_equipment_maintenance_skill(),
        )
        logger.info("MAIW bootstrap: EquipmentActionExecutor ready")
    except Exception as exc:
        logger.warning("MAIW bootstrap: EquipmentActionExecutor unavailable — %s", exc)

    # LaborActionExecutor
    try:
        from src.api.agents.operations.labor_executor import LaborActionExecutor
        from maiw_skills.labor import get_execute_labor_allocation_skill
        runtime.labor_executor = LaborActionExecutor(
            allocate_skill=await get_execute_labor_allocation_skill(),
        )
        logger.info("MAIW bootstrap: LaborActionExecutor ready")
    except Exception as exc:
        logger.warning("MAIW bootstrap: LaborActionExecutor unavailable — %s", exc)

    # WaveActionExecutor
    try:
        from src.api.agents.operations.wave_executor import WaveActionExecutor
        from maiw_skills.wave import get_execute_wave_reprioritization_skill
        runtime.wave_executor = WaveActionExecutor(
            reprioritize_skill=await get_execute_wave_reprioritization_skill(),
        )
        logger.info("MAIW bootstrap: WaveActionExecutor ready")
    except Exception as exc:
        logger.warning("MAIW bootstrap: WaveActionExecutor unavailable — %s", exc)

    _runtime = runtime
    logger.info("MAIW bootstrap: runtime assembly complete")
    return _runtime


def reset_runtime() -> None:
    """Reset the runtime singleton — for testing only."""
    global _runtime
    _runtime = None
