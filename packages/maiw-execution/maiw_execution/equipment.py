# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""EquipmentActionExecutor — Equipment domain executor with state-drift guard."""

from __future__ import annotations

import logging
from typing import Any, Optional

from maiw_decision.models import DecisionResult
from maiw_mcp.contracts.actions import ActionProposal

from .base import ActionConflict, ActionUnsupported, BaseActionExecutor
from .outcome import ExecutionOutcome

logger = logging.getLogger(__name__)


class EquipmentActionExecutor(BaseActionExecutor):
    """
    Concrete executor for the Equipment domain.

    Extends BaseActionExecutor with a state-drift guard (guard 5):
    checks live asset status against proposal before writing. Best-effort —
    does not block execution when the state provider is unreachable.

    Execution routing (by proposal.action):
        warehouse.equipment.assign               → assign_skill
        warehouse.equipment.release              → release_skill
        warehouse.equipment.schedule_maintenance → maintenance_skill

    Outcome mapping: reads the ``outcome`` field on the provider result.
    """

    _ALLOWED_ACTIONS: frozenset[str] = frozenset({
        "warehouse.equipment.assign",
        "warehouse.equipment.release",
        "warehouse.equipment.schedule_maintenance",
    })

    def __init__(
        self,
        *,
        assign_skill: Any,
        release_skill: Optional[Any] = None,
        maintenance_skill: Optional[Any] = None,
        state_provider: Optional[Any] = None,
        max_decision_age_seconds: int = 300,
        **kwargs: Any,
    ) -> None:
        super().__init__(max_decision_age_seconds=max_decision_age_seconds, **kwargs)
        self._assign_skill = assign_skill
        self._release_skill = release_skill
        self._maintenance_skill = maintenance_skill
        self._state_provider = state_provider

    async def _check_additional_guards(self, proposal: ActionProposal) -> None:
        if not self._state_provider:
            return
        asset_id = proposal.parameters.get("asset_id")
        if not asset_id:
            return
        try:
            from maiw_state import StateRequirements

            warehouse_id = proposal.parameters.get("warehouse_id", "default")
            state = await self._state_provider.get_state(
                warehouse_id,
                StateRequirements(equipment=True, equipment_asset_id=asset_id),
            )
        except Exception:
            return  # Best-effort: don't block execution when state is unreachable
        if state.equipment:
            asset = next(
                (a for a in state.equipment.assets if a.asset_id == asset_id), None
            )
            if asset and asset.status in {"offline", "maintenance"}:
                raise ActionConflict(
                    f"Asset {asset_id!r} status drifted to {asset.status!r} since "
                    f"the decision snapshot; cannot execute safely"
                )

    async def _do_execute(
        self,
        proposal: ActionProposal,
        decision: DecisionResult,
        execution_id: str,
    ) -> tuple[dict[str, Any], str | None, ExecutionOutcome]:
        if proposal.action == "warehouse.equipment.assign":
            resp = await self._do_assign(proposal, decision, execution_id)
        elif proposal.action == "warehouse.equipment.release":
            resp = await self._do_release(proposal, decision, execution_id)
        else:
            resp = await self._do_maintenance(proposal, decision, execution_id)

        outcome_str = resp.get("outcome", "")
        outcome = _map_outcome(outcome_str, bool(resp.get("success", True)))
        provider_ref = str(resp.get("assignment_id") or resp.get("maintenance_id") or "") or None
        return resp, provider_ref, outcome

    async def _do_assign(
        self, proposal: ActionProposal, decision: DecisionResult, execution_id: str
    ) -> dict[str, Any]:
        if self._assign_skill is None:
            raise ActionUnsupported("No assign_skill configured on EquipmentActionExecutor")
        from maiw_mcp.contracts.equipment import EquipmentExecuteAssignRequest

        req = EquipmentExecuteAssignRequest(
            asset_id=proposal.parameters["asset_id"],
            assignee=proposal.parameters["assignee"],
            assignment_type=proposal.parameters.get("assignment_type", "task"),
            task_id=proposal.parameters.get("task_id"),
            duration_hours=proposal.parameters.get("duration_hours"),
            notes=proposal.parameters.get("notes"),
            proposal_id=proposal.proposal_id,
            decision_id=decision.result_id,
            execution_id=execution_id,
        )
        result = await self._assign_skill.execute(req)
        return result.model_dump()

    async def _do_release(
        self, proposal: ActionProposal, decision: DecisionResult, execution_id: str
    ) -> dict[str, Any]:
        if self._release_skill is None:
            raise ActionUnsupported("No release_skill configured on EquipmentActionExecutor")
        from maiw_mcp.contracts.equipment import EquipmentExecuteReleaseRequest

        req = EquipmentExecuteReleaseRequest(
            asset_id=proposal.parameters["asset_id"],
            released_by=proposal.parameters.get("released_by", "unknown"),
            notes=proposal.parameters.get("notes"),
            proposal_id=proposal.proposal_id,
            decision_id=decision.result_id,
            execution_id=execution_id,
        )
        result = await self._release_skill.execute(req)
        return result.model_dump()

    async def _do_maintenance(
        self, proposal: ActionProposal, decision: DecisionResult, execution_id: str
    ) -> dict[str, Any]:
        if self._maintenance_skill is None:
            raise ActionUnsupported("No maintenance_skill configured on EquipmentActionExecutor")
        from maiw_mcp.contracts.equipment import EquipmentExecuteMaintenanceRequest

        req = EquipmentExecuteMaintenanceRequest(
            asset_id=proposal.parameters["asset_id"],
            maintenance_type=proposal.parameters.get("maintenance_type", "preventive"),
            description=proposal.parameters.get("description", ""),
            scheduled_by=proposal.parameters.get("scheduled_by", "unknown"),
            scheduled_for=proposal.parameters.get("scheduled_for", ""),
            estimated_duration_minutes=proposal.parameters.get("estimated_duration_minutes", 60),
            priority=proposal.parameters.get("priority", "medium"),
            proposal_id=proposal.proposal_id,
            decision_id=decision.result_id,
            execution_id=execution_id,
        )
        result = await self._maintenance_skill.execute(req)
        return result.model_dump()


def _map_outcome(outcome_str: str, success: bool) -> ExecutionOutcome:
    _MAP = {
        "executed": ExecutionOutcome.EXECUTED,
        "no_op": ExecutionOutcome.NO_OP,
        "deferred": ExecutionOutcome.DEFERRED,
        "conflict": ExecutionOutcome.CONFLICT,
        "failed": ExecutionOutcome.FAILED,
        "unknown": ExecutionOutcome.UNKNOWN,
    }
    if outcome_str in _MAP:
        return _MAP[outcome_str]
    return ExecutionOutcome.EXECUTED if success else ExecutionOutcome.FAILED
