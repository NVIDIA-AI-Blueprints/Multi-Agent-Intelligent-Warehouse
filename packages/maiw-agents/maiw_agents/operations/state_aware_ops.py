# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
State-aware operations — Labor + Wave proposal orchestration.

Mirrors the pattern in maiw_agents.equipment.state_aware_ops.
All functions accept a sealed WarehouseStateSnapshot and proposal skills;
they never access DemoWarehouseWorld or SimulationProviders directly.

Architecture
------------
  RecommendedAction (from OperationalAssessment)
      ↓
  propose_labor_allocation() / propose_wave_reprioritization()
      ↓
  ProposeLaborAllocationSkill / ProposeWaveReprioritizationSkill  (in-process, no MCP)
      ↓
  DecisionEngine.evaluate()
      ↓
  LaborActionExecutor / WaveActionExecutor  (MCP write — only if APPROVED)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from maiw_decision import DecisionEngine
from maiw_decision.models import DecisionOutcome, DecisionRequest
from maiw_state import WarehouseStateSnapshot

logger = logging.getLogger(__name__)


async def propose_labor_allocation(
    *,
    task_id: str,
    task_type: str,
    worker_ids: list[str],
    zone: Optional[str] = None,
    priority: str = "medium",
    notes: Optional[str] = None,
    reason: str = "",
    requested_by: str = "operations-agent",
    warehouse_id: str = "default",
    trace_id: Optional[str] = None,
    snapshot: WarehouseStateSnapshot,
    decision_engine: DecisionEngine,
    propose_skill: Any,
    action_executor: Optional[Any] = None,
) -> dict[str, Any]:
    """
    State-aware labor allocation proposal.

    Steps
    -----
    1. Build ActionProposal via ProposeLaborAllocationSkill (in-process, no MCP).
    2. Evaluate with DecisionEngine against sealed snapshot.
    3. If APPROVED and action_executor is provided, execute.
    4. Return structured result dict.
    """
    try:
        proposal = await propose_skill.execute(
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
    except Exception as exc:
        logger.error("Labor proposal build failed for task=%s: %s", task_id, exc)
        return {
            "status": "error",
            "action": "warehouse.labor.allocate",
            "reason": f"Proposal build failed: {exc}",
        }

    request = DecisionRequest(
        proposal=proposal,
        state=snapshot,
        requested_by=requested_by,
        trace_id=trace_id,
    )
    result, _audit = decision_engine.evaluate(request)
    result.trace_id = trace_id

    if result.outcome == DecisionOutcome.APPROVED and action_executor is not None:
        try:
            exec_result = await action_executor.execute(
                proposal, result, trace_id=trace_id
            )
            return {
                "status": (
                    exec_result.outcome.value
                    if exec_result.outcome.value != "executed"
                    else "approved"
                ),
                "action": "warehouse.labor.allocate",
                "proposal_id": proposal.proposal_id,
                "decision_id": result.result_id,
                "execution": exec_result.model_dump(),
                "trace_id": trace_id,
            }
        except Exception as exc:
            logger.error(
                "Labor execution failed for proposal %s: %s", proposal.proposal_id, exc
            )
            return {
                "status": "execution_error",
                "action": "warehouse.labor.allocate",
                "proposal_id": proposal.proposal_id,
                "decision_id": result.result_id,
                "reason": str(exc),
                "trace_id": trace_id,
            }

    return {
        "status": result.outcome.value,
        "action": "warehouse.labor.allocate",
        "proposal_id": proposal.proposal_id,
        "decision_id": result.result_id,
        "violations": [v.model_dump() for v in result.violations],
        "trace_id": trace_id,
    }


async def propose_wave_reprioritization(
    *,
    wave_id: Optional[str] = None,
    zone: Optional[str] = None,
    new_priority: str,
    reason: str = "",
    requested_by: str = "operations-agent",
    warehouse_id: str = "default",
    trace_id: Optional[str] = None,
    snapshot: WarehouseStateSnapshot,
    decision_engine: DecisionEngine,
    propose_skill: Any,
    action_executor: Optional[Any] = None,
) -> dict[str, Any]:
    """
    State-aware wave reprioritization proposal.

    Steps
    -----
    1. Build ActionProposal via ProposeWaveReprioritizationSkill (in-process, no MCP).
    2. Evaluate with DecisionEngine against sealed snapshot.
    3. If APPROVED and action_executor is provided, execute.
    4. Return structured result dict.
    """
    try:
        proposal = await propose_skill.execute(
            wave_id=wave_id,
            zone=zone,
            new_priority=new_priority,
            reason=reason,
            requested_by=requested_by,
            warehouse_id=warehouse_id,
            trace_id=trace_id,
        )
    except Exception as exc:
        logger.error(
            "Wave reprioritization proposal build failed zone=%s: %s", zone, exc
        )
        return {
            "status": "error",
            "action": "warehouse.wave.reprioritize",
            "reason": f"Proposal build failed: {exc}",
        }

    request = DecisionRequest(
        proposal=proposal,
        state=snapshot,
        requested_by=requested_by,
        trace_id=trace_id,
    )
    result, _audit = decision_engine.evaluate(request)
    result.trace_id = trace_id

    if result.outcome == DecisionOutcome.APPROVED and action_executor is not None:
        try:
            exec_result = await action_executor.execute(
                proposal, result, trace_id=trace_id
            )
            return {
                "status": (
                    exec_result.outcome.value
                    if exec_result.outcome.value != "executed"
                    else "approved"
                ),
                "action": "warehouse.wave.reprioritize",
                "proposal_id": proposal.proposal_id,
                "decision_id": result.result_id,
                "execution": exec_result.model_dump(),
                "trace_id": trace_id,
            }
        except Exception as exc:
            logger.error(
                "Wave execution failed for proposal %s: %s", proposal.proposal_id, exc
            )
            return {
                "status": "execution_error",
                "action": "warehouse.wave.reprioritize",
                "proposal_id": proposal.proposal_id,
                "decision_id": result.result_id,
                "reason": str(exc),
                "trace_id": trace_id,
            }

    return {
        "status": result.outcome.value,
        "action": "warehouse.wave.reprioritize",
        "proposal_id": proposal.proposal_id,
        "decision_id": result.result_id,
        "violations": [v.model_dump() for v in result.violations],
        "trace_id": trace_id,
    }
