# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
ActionExecutor — the narrow execution boundary between DecisionEngine and MCP writes.

Architecture rule
-----------------
The ONLY path from an agent to a write capability is:

    ActionProposal
        ↓
    DecisionEngine.evaluate()  →  APPROVED
        ↓
    ActionExecutor.execute()
        ↓
    MCP write capability

Never:
    LLM → MCP write

Typed errors
------------
All execution errors are typed so callers can handle them specifically:
    ActionNotApproved     — outcome was not APPROVED
    ActionDecisionMismatch — decision.proposal_id != proposal.proposal_id
    ActionUnsupported     — action is not in the executor's allowlist
    ActionExpired         — decision is older than max_decision_age_seconds
    ActionConflict        — asset state drifted since the snapshot (state-drift guard)
    ActionExecutionError  — backend write failed after all guards passed
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from maiw_decision.models import DecisionOutcome, DecisionResult
from maiw_mcp.contracts.actions import ActionProposal

logger = logging.getLogger(__name__)


# ── Typed execution errors ─────────────────────────────────────────────────────


class ActionNotApproved(ValueError):
    """Raised when execute() is called with a non-APPROVED decision outcome."""


class ActionDecisionMismatch(ValueError):
    """Raised when decision.proposal_id does not match proposal.proposal_id."""


class ActionUnsupported(ValueError):
    """Raised when proposal.action is not in the executor's allowlist."""


class ActionExpired(ValueError):
    """Raised when the decision is older than max_decision_age_seconds."""


class ActionConflict(RuntimeError):
    """Raised when asset state drifted since the snapshot (state-drift guard)."""


class ActionExecutionError(RuntimeError):
    """Raised when the MCP write capability fails after all guards have passed."""


# ── Execution result ───────────────────────────────────────────────────────────


class ActionExecutionResult(BaseModel):
    """
    Result of an ActionExecutor.execute() call.

    Fields
    ------
    execution_id:
        UUID for this specific execution. Useful for correlating with backend
        audit records and telemetry spans.
    executed:
        ``True`` when the write was performed; ``False`` when skipped (NoOp).
    success:
        ``True`` when the backend confirmed success.
    action:
        The action string from the proposal.
    proposal_id:
        Echoes ``ActionProposal.proposal_id``.
    decision_id:
        Echoes ``DecisionResult.result_id``; proves the decision gate was
        crossed before execution.
    provider_reference:
        Optional backend-specific reference (e.g. assignment_id as string).
    backend_response:
        Raw response from the MCP write capability.
    started_at:
        UTC timestamp when execution started.
    completed_at:
        UTC timestamp when execution completed (None for skipped/NoOp).
    executed_at:
        Alias for completed_at for backward compatibility.
    error_code:
        Short machine-readable error code if success=False.
    error_message:
        Human-readable error description if success=False.
    """

    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    executed: bool = True
    success: bool = True
    action: str
    proposal_id: str
    decision_id: str
    provider_reference: str | None = None
    backend_response: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error_code: str | None = None
    error_message: str | None = None


# ── Protocol ───────────────────────────────────────────────────────────────────


@runtime_checkable
class ActionExecutor(Protocol):
    """
    Structural protocol for proposal execution.

    Concrete implementations must:
    - Verify that ``decision.outcome == DecisionOutcome.APPROVED`` before
      proceeding; raise ``ActionNotApproved`` otherwise.
    - Call the appropriate MCP write capability.
    - Return ``ActionExecutionResult`` with ``executed=True``.
    """

    async def execute(
        self,
        proposal: ActionProposal,
        decision: DecisionResult,
    ) -> ActionExecutionResult: ...


# ── NoOpActionExecutor ─────────────────────────────────────────────────────────


class NoOpActionExecutor:
    """
    Stub executor for environments where execution is not yet wired.

    Returns a result with ``executed=False`` and logs a warning.
    This is the default when no concrete executor is injected.
    """

    async def execute(
        self,
        proposal: ActionProposal,
        decision: DecisionResult,
    ) -> ActionExecutionResult:
        if decision.outcome != DecisionOutcome.APPROVED:
            raise ActionNotApproved(
                f"NoOpActionExecutor.execute() called with non-APPROVED outcome: "
                f"{decision.outcome.value}"
            )
        logger.warning(
            "NoOpActionExecutor: proposal %s approved but no executor configured; "
            "execution skipped.",
            proposal.proposal_id,
        )
        now = datetime.now(timezone.utc)
        return ActionExecutionResult(
            executed=False,
            success=False,
            action=proposal.action,
            proposal_id=proposal.proposal_id,
            decision_id=decision.result_id,
            backend_response={"note": "no_executor_configured"},
            started_at=now,
            completed_at=None,
            executed_at=now,
        )


# ── EquipmentActionExecutor ────────────────────────────────────────────────────


class EquipmentActionExecutor:
    """
    Concrete executor for the Equipment domain.

    Guards (checked in order before any write):
    1. APPROVED gate — raises ActionNotApproved
    2. Proposal/decision binding — raises ActionDecisionMismatch
    3. Action allowlist — raises ActionUnsupported
    4. Stale-decision guard — raises ActionExpired
    5. State-drift guard — raises ActionConflict (best-effort, requires state_provider)

    Execution routing (by proposal.action):
        warehouse.equipment.assign              → assign_skill
        warehouse.equipment.release             → release_skill
        warehouse.equipment.schedule_maintenance → maintenance_skill
    """

    _ALLOWED_ACTIONS = frozenset({
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
    ) -> None:
        self._assign_skill = assign_skill
        self._release_skill = release_skill
        self._maintenance_skill = maintenance_skill
        self._state_provider = state_provider
        self._max_decision_age_seconds = max_decision_age_seconds

    async def execute(
        self,
        proposal: ActionProposal,
        decision: DecisionResult,
    ) -> ActionExecutionResult:
        # 1. APPROVED gate
        if decision.outcome != DecisionOutcome.APPROVED:
            raise ActionNotApproved(
                f"Cannot execute proposal {proposal.proposal_id!r}: "
                f"decision outcome is {decision.outcome.value!r}, not approved"
            )

        # 2. Decision/proposal binding
        if decision.proposal_id != proposal.proposal_id:
            raise ActionDecisionMismatch(
                f"Decision proposal_id {decision.proposal_id!r} does not match "
                f"proposal proposal_id {proposal.proposal_id!r}"
            )

        # 3. Action allowlist
        if proposal.action not in self._ALLOWED_ACTIONS:
            raise ActionUnsupported(
                f"Action {proposal.action!r} is not in the EquipmentActionExecutor allowlist"
            )

        # 4. Stale-decision guard
        now_utc = datetime.now(timezone.utc)
        age_seconds = (now_utc - decision.evaluated_at).total_seconds()
        if age_seconds > self._max_decision_age_seconds:
            raise ActionExpired(
                f"Decision {decision.result_id!r} expired: "
                f"age {age_seconds:.0f}s > max {self._max_decision_age_seconds}s"
            )

        # 5. Optional state-drift guard (best-effort — failure does not block)
        await self._check_state_drift(proposal)

        # 6. Execute via the appropriate skill
        execution_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)

        try:
            if proposal.action == "warehouse.equipment.assign":
                backend_resp = await self._do_assign(proposal, decision)
            elif proposal.action == "warehouse.equipment.release":
                backend_resp = await self._do_release(proposal, decision)
            else:
                backend_resp = await self._do_maintenance(proposal, decision)
        except (ActionNotApproved, ActionDecisionMismatch, ActionUnsupported, ActionExpired, ActionConflict):
            raise
        except Exception as exc:
            raise ActionExecutionError(
                f"Execution of {proposal.action!r} failed for proposal "
                f"{proposal.proposal_id!r}: {exc}"
            ) from exc

        completed_at = datetime.now(timezone.utc)
        provider_ref = str(backend_resp.get("assignment_id") or backend_resp.get("maintenance_id") or "")

        logger.info(
            "EquipmentActionExecutor: executed action=%s proposal_id=%s execution_id=%s",
            proposal.action, proposal.proposal_id, execution_id,
        )

        return ActionExecutionResult(
            execution_id=execution_id,
            executed=True,
            success=True,
            action=proposal.action,
            proposal_id=proposal.proposal_id,
            decision_id=decision.result_id,
            provider_reference=provider_ref or None,
            backend_response=backend_resp,
            started_at=started_at,
            completed_at=completed_at,
            executed_at=completed_at,
        )

    async def _check_state_drift(self, proposal: ActionProposal) -> None:
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

    async def _do_assign(
        self, proposal: ActionProposal, decision: DecisionResult
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
        )
        result = await self._assign_skill.execute(req)
        return result.model_dump()

    async def _do_release(
        self, proposal: ActionProposal, decision: DecisionResult
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
        )
        result = await self._release_skill.execute(req)
        return result.model_dump()

    async def _do_maintenance(
        self, proposal: ActionProposal, decision: DecisionResult
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
        )
        result = await self._maintenance_skill.execute(req)
        return result.model_dump()
