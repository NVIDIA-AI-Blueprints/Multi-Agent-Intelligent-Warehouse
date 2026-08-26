# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
State-aware equipment operations — pure logic with no heavy runtime imports.

This module contains the core state-assembly and decision-engine logic for
equipment operations.  It deliberately imports only from lightweight packages
(maiw-mcp, maiw-state, maiw-decision) so that unit tests can import it without
needing asyncpg, redis, pymilvus, or other infrastructure dependencies.

The ``EquipmentAssetOperationsAgent`` delegates its state-aware methods here.

Phase 6 additions
-----------------
- ``propose_equipment_assignment()`` now accepts an optional ``action_executor``
  and calls it when the decision is APPROVED.
- ``propose_equipment_release()`` — full state/decide/execute path for release.
- ``propose_schedule_maintenance()`` — state/decide path for maintenance (MEDIUM
  risk, so always REQUIRES_HUMAN_APPROVAL — no executor call).
- ``get_equipment_state_snapshot()`` — unchanged read path.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from maiw_decision import DecisionEngine
from maiw_decision.models import DecisionOutcome, DecisionRequest
from maiw_mcp.contracts.actions import ActionProposal
from maiw_mcp.contracts.equipment import EquipmentAssignmentRequest
from maiw_state import StateRequirements, WarehouseStateSnapshot

logger = logging.getLogger(__name__)


async def propose_equipment_assignment(
    *,
    asset_id: str,
    assignee: str,
    assignment_type: str = "task",
    task_id: Optional[str] = None,
    duration_hours: Optional[float] = None,
    notes: Optional[str] = None,
    warehouse_id: str = "default",
    trace_id: Optional[str] = None,
    state_provider: Any,
    decision_engine: DecisionEngine,
    assignment_skill: Any,
    action_executor: Optional[Any] = None,
) -> dict[str, Any]:
    """
    State-aware equipment assignment.

    Steps:
    1. Assemble WarehouseState for the target asset via state_provider.
    2. Seal into WarehouseStateSnapshot.
    3. Build ActionProposal via assignment_skill (never writes DB).
    4. Evaluate with DecisionEngine.
    5. If APPROVED and action_executor is provided, execute immediately.
    6. Return structured decision/execution dict.

    Raises nothing intentionally — errors are captured in the returned dict
    with status="error".
    """
    # Step 1: Assemble state
    requirements = StateRequirements(
        equipment=True,
        equipment_asset_id=asset_id,
    )
    try:
        state = await state_provider.get_state(
            warehouse_id, requirements, trace_id=trace_id
        )
    except Exception as exc:
        logger.error("State assembly failed for assignment of %s: %s", asset_id, exc)
        return {
            "status": "error",
            "action": "warehouse.equipment.assign",
            "reason": f"State assembly failed: {exc}",
            "executed": False,
            "trace_id": trace_id,
        }

    snapshot = WarehouseStateSnapshot.seal(state)
    logger.info(
        "Equipment state assembled: snapshot_id=%s asset_id=%s assets=%d",
        snapshot.snapshot_id,
        asset_id,
        len(state.equipment.assets) if state.equipment else 0,
    )

    # Step 2: Build ActionProposal via skill (read-only — validates but never writes)
    try:
        assign_req = EquipmentAssignmentRequest(
            asset_id=asset_id,
            assignee=assignee,
            assignment_type=assignment_type,
            task_id=task_id,
            duration_hours=int(duration_hours) if duration_hours else None,
            notes=notes or "",
        )
        proposal = await assignment_skill.execute(assign_req, trace_id=trace_id)
    except Exception as exc:
        logger.error("ActionProposal creation failed for %s: %s", asset_id, exc)
        return {
            "status": "error",
            "action": "warehouse.equipment.assign",
            "reason": f"Proposal creation failed: {exc}",
            "executed": False,
            "snapshot_id": snapshot.snapshot_id,
            "trace_id": trace_id,
        }

    # Step 3: Evaluate with DecisionEngine (synchronous, pure in-memory)
    dec_request = DecisionRequest(
        proposal=proposal,
        state=snapshot,
        requested_by=assignee,
        trace_id=trace_id,
    )
    result, audit = decision_engine.evaluate(dec_request)

    logger.info(
        "DecisionEngine: %s proposal_id=%s decision_id=%s snapshot_id=%s",
        result.outcome.value,
        proposal.proposal_id,
        result.result_id,
        snapshot.snapshot_id,
    )

    reason = (
        result.violations[0].message if result.violations else "all checks passed"
    )

    # Step 4: Execute if APPROVED and executor provided
    if result.outcome == DecisionOutcome.APPROVED and action_executor is not None:
        return await _execute_action(
            proposal=proposal,
            decision=result,
            action_executor=action_executor,
            snapshot_id=snapshot.snapshot_id,
            trace_id=trace_id,
        )

    return {
        "status": result.outcome.value,
        "action": "warehouse.equipment.assign",
        "proposal_id": proposal.proposal_id,
        "decision_id": result.result_id,
        "reason": reason,
        "executed": False,
        "snapshot_id": snapshot.snapshot_id,
        "trace_id": trace_id,
        "violations": [v.model_dump() for v in result.violations],
    }


async def propose_equipment_release(
    *,
    asset_id: str,
    released_by: str,
    notes: Optional[str] = None,
    warehouse_id: str = "default",
    trace_id: Optional[str] = None,
    state_provider: Any,
    decision_engine: DecisionEngine,
    action_executor: Optional[Any] = None,
) -> dict[str, Any]:
    """
    State-aware equipment release.

    LOW risk (requires_approval=False) so the DecisionEngine auto-approves
    unless equipment state is absent/stale or the asset is not in the snapshot.

    When an executor is provided and the decision is APPROVED, execution
    happens immediately and ``executed: true`` is returned.
    """
    requirements = StateRequirements(
        equipment=True,
        equipment_asset_id=asset_id,
    )
    try:
        state = await state_provider.get_state(
            warehouse_id, requirements, trace_id=trace_id
        )
    except Exception as exc:
        logger.error("State assembly failed for release of %s: %s", asset_id, exc)
        return {
            "status": "error",
            "action": "warehouse.equipment.release",
            "reason": f"State assembly failed: {exc}",
            "executed": False,
            "trace_id": trace_id,
        }

    snapshot = WarehouseStateSnapshot.seal(state)

    # Build proposal directly (no MCP call needed for LOW risk proposal)
    proposal = ActionProposal.for_equipment_release(
        asset_id=asset_id,
        released_by=released_by,
        notes=notes,
        reason=f"Release {asset_id} from assignment",
        requested_by=released_by or "operations-agent",
        trace_id=trace_id,
    )

    dec_request = DecisionRequest(
        proposal=proposal,
        state=snapshot,
        requested_by=released_by or "unknown",
        trace_id=trace_id,
    )
    result, audit = decision_engine.evaluate(dec_request)

    logger.info(
        "DecisionEngine: %s proposal_id=%s action=release asset_id=%s",
        result.outcome.value, proposal.proposal_id, asset_id,
    )

    if result.outcome == DecisionOutcome.APPROVED and action_executor is not None:
        return await _execute_action(
            proposal=proposal,
            decision=result,
            action_executor=action_executor,
            snapshot_id=snapshot.snapshot_id,
            trace_id=trace_id,
        )

    reason = result.violations[0].message if result.violations else "all checks passed"
    return {
        "status": result.outcome.value,
        "action": "warehouse.equipment.release",
        "proposal_id": proposal.proposal_id,
        "decision_id": result.result_id,
        "reason": reason,
        "executed": False,
        "snapshot_id": snapshot.snapshot_id,
        "trace_id": trace_id,
        "violations": [v.model_dump() for v in result.violations],
    }


async def propose_schedule_maintenance(
    *,
    asset_id: str,
    maintenance_type: str,
    description: str,
    scheduled_by: str,
    scheduled_for: str,
    estimated_duration_minutes: int = 60,
    priority: str = "medium",
    warehouse_id: str = "default",
    trace_id: Optional[str] = None,
    state_provider: Any,
    decision_engine: DecisionEngine,
    action_executor: Optional[Any] = None,
) -> dict[str, Any]:
    """
    State-aware maintenance scheduling.

    MEDIUM risk (requires_approval=True) so the DecisionEngine always returns
    REQUIRES_HUMAN_APPROVAL unless state guards fire first.  The action_executor
    parameter is accepted for interface symmetry but is never called because
    maintenance proposals don't auto-execute.
    """
    requirements = StateRequirements(
        equipment=True,
        equipment_asset_id=asset_id,
    )
    try:
        state = await state_provider.get_state(
            warehouse_id, requirements, trace_id=trace_id
        )
    except Exception as exc:
        logger.error("State assembly failed for maintenance of %s: %s", asset_id, exc)
        return {
            "status": "error",
            "action": "warehouse.equipment.schedule_maintenance",
            "reason": f"State assembly failed: {exc}",
            "executed": False,
            "trace_id": trace_id,
        }

    snapshot = WarehouseStateSnapshot.seal(state)

    proposal = ActionProposal.for_schedule_maintenance(
        asset_id=asset_id,
        maintenance_type=maintenance_type,
        description=description,
        scheduled_by=scheduled_by,
        scheduled_for=scheduled_for,
        estimated_duration_minutes=estimated_duration_minutes,
        priority=priority,
        reason=f"Schedule {maintenance_type} maintenance for {asset_id}",
        requested_by=scheduled_by or "operations-agent",
        trace_id=trace_id,
    )

    dec_request = DecisionRequest(
        proposal=proposal,
        state=snapshot,
        requested_by=scheduled_by or "unknown",
        trace_id=trace_id,
    )
    result, audit = decision_engine.evaluate(dec_request)

    logger.info(
        "DecisionEngine: %s proposal_id=%s action=schedule_maintenance asset_id=%s",
        result.outcome.value, proposal.proposal_id, asset_id,
    )

    # MEDIUM risk: never auto-executes regardless of executor
    reason = result.violations[0].message if result.violations else "all checks passed"
    return {
        "status": result.outcome.value,
        "action": "warehouse.equipment.schedule_maintenance",
        "proposal_id": proposal.proposal_id,
        "decision_id": result.result_id,
        "reason": reason,
        "executed": False,
        "snapshot_id": snapshot.snapshot_id,
        "trace_id": trace_id,
        "violations": [v.model_dump() for v in result.violations],
    }


async def _execute_action(
    *,
    proposal: ActionProposal,
    decision: Any,
    action_executor: Any,
    snapshot_id: str,
    trace_id: Optional[str],
) -> dict[str, Any]:
    """
    Call action_executor.execute() and return a structured execution result dict.

    Captures all errors and maps them to status="error".
    """
    try:
        exec_result = await action_executor.execute(proposal, decision, trace_id=trace_id)
        return {
            "status": exec_result.outcome.value,
            "action": proposal.action,
            "proposal_id": proposal.proposal_id,
            "decision_id": decision.result_id,
            "execution_id": exec_result.execution_id,
            "success": exec_result.success,
            "reason": "approved and executed",
            "executed": exec_result.executed,
            "snapshot_id": snapshot_id,
            "trace_id": trace_id,
            "violations": [],
            "provider_reference": exec_result.provider_reference,
            "backend_response": exec_result.backend_response,
        }
    except Exception as exc:
        logger.error(
            "Execution failed after APPROVED decision: proposal_id=%s error=%s",
            proposal.proposal_id,
            exc,
        )
        return {
            "status": "error",
            "action": proposal.action,
            "proposal_id": proposal.proposal_id,
            "decision_id": decision.result_id,
            "reason": f"Execution failed: {exc}",
            "executed": False,
            "snapshot_id": snapshot_id,
            "trace_id": trace_id,
            "violations": [],
        }


async def get_equipment_state_snapshot(
    *,
    asset_id: Optional[str] = None,
    equipment_type: Optional[str] = None,
    zone: Optional[str] = None,
    warehouse_id: str = "default",
    trace_id: Optional[str] = None,
    state_provider: Any,
) -> Optional[dict[str, Any]]:
    """
    Assemble a WarehouseStateSnapshot for equipment and return a structured
    summary suitable for agent reasoning context.

    Returns None when state assembly fails (logged as a warning).
    """
    requirements = StateRequirements(
        equipment=True,
        equipment_asset_id=asset_id,
        equipment_type=equipment_type,
        equipment_zone=zone,
    )
    try:
        state = await state_provider.get_state(
            warehouse_id, requirements, trace_id=trace_id
        )
    except Exception as exc:
        logger.warning("State assembly failed for read query: %s", exc)
        return None

    snapshot = WarehouseStateSnapshot.seal(state)
    eq = state.equipment

    return {
        "snapshot_id": snapshot.snapshot_id,
        "warehouse_id": snapshot.warehouse_id,
        "observed_at": state.observed_at.isoformat(),
        "equipment": {
            "total_count": eq.total_count if eq else 0,
            "available_count": eq.available_count if eq else 0,
            "assets": [
                {
                    "asset_id": a.asset_id,
                    "type": a.equipment_type,
                    "zone": a.zone,
                    "status": a.status,
                }
                for a in (eq.assets if eq else [])
            ],
            "freshness": {
                "age_ms": eq.freshness.age_ms if eq else None,
                "stale": eq.freshness.stale if eq else None,
            },
        } if eq else None,
        "provenance": [
            {
                "domain": p.domain,
                "capability": p.capability,
                "source": p.source.value,
                "latency_ms": p.latency_ms,
            }
            for p in state.provenance
        ],
    }
