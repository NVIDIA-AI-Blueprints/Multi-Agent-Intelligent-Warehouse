# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
WaveActionExecutor — the narrow execution boundary between DecisionEngine and Wave MCP writes.

Architecture rule
-----------------
The ONLY path from an agent to a wave write capability is:

    ActionProposal
        ↓
    DecisionEngine.evaluate()  →  APPROVED
        ↓
    WaveActionExecutor.execute()
        ↓
    MCP write capability  (warehouse.wave.reprioritize)

Same typed error hierarchy as EquipmentActionExecutor.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from maiw_decision.models import DecisionOutcome, DecisionResult
from maiw_mcp.contracts.actions import ActionProposal
from src.api.agents.inventory.action_executor import (
    ActionConflict,
    ActionDecisionMismatch,
    ActionExecutionError,
    ActionExecutionResult,
    ActionExpired,
    ActionNotApproved,
    ActionUnsupported,
)

logger = logging.getLogger(__name__)


class WaveActionExecutor:
    """
    Concrete executor for the Wave domain.

    Guards (checked in order before any write):
    1. APPROVED gate — raises ActionNotApproved
    2. Proposal/decision binding — raises ActionDecisionMismatch
    3. Action allowlist — raises ActionUnsupported
    4. Stale-decision guard — raises ActionExpired

    Execution routing (by proposal.action):
        warehouse.wave.reprioritize → reprioritize_skill
    """

    _ALLOWED_ACTIONS = frozenset({
        "warehouse.wave.reprioritize",
    })

    def __init__(
        self,
        *,
        reprioritize_skill: Any,
        max_decision_age_seconds: int = 300,
    ) -> None:
        self._reprioritize_skill = reprioritize_skill
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
                f"Action {proposal.action!r} is not in the WaveActionExecutor allowlist"
            )

        # 4. Stale-decision guard
        now_utc = datetime.now(timezone.utc)
        age_seconds = (now_utc - decision.evaluated_at).total_seconds()
        if age_seconds > self._max_decision_age_seconds:
            raise ActionExpired(
                f"Decision {decision.result_id!r} expired: "
                f"age {age_seconds:.0f}s > max {self._max_decision_age_seconds}s"
            )

        execution_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)

        try:
            backend_resp = await self._do_reprioritize(proposal, decision)
        except (ActionNotApproved, ActionDecisionMismatch, ActionUnsupported, ActionExpired, ActionConflict):
            raise
        except Exception as exc:
            raise ActionExecutionError(
                f"Execution of {proposal.action!r} failed for proposal "
                f"{proposal.proposal_id!r}: {exc}"
            ) from exc

        completed_at = datetime.now(timezone.utc)
        logger.info(
            "WaveActionExecutor: executed action=%s proposal_id=%s execution_id=%s",
            proposal.action, proposal.proposal_id, execution_id,
        )

        return ActionExecutionResult(
            execution_id=execution_id,
            executed=True,
            success=True,
            action=proposal.action,
            proposal_id=proposal.proposal_id,
            decision_id=decision.result_id,
            provider_reference=None,
            backend_response=backend_resp,
            started_at=started_at,
            completed_at=completed_at,
            executed_at=completed_at,
        )

    async def _do_reprioritize(
        self, proposal: ActionProposal, decision: DecisionResult
    ) -> dict:
        from maiw_mcp.contracts.wave import WaveReprioritizeRequest

        params = proposal.parameters
        req = WaveReprioritizeRequest(
            warehouse_id=params.get("warehouse_id", "default"),
            wave_id=params.get("wave_id"),
            zone=params.get("zone"),
            new_priority=params.get("new_priority", "high"),
            reason=proposal.reason,
            proposal_id=proposal.proposal_id,
            decision_id=decision.result_id,
        )
        result = await self._reprioritize_skill.execute(req)
        return result.model_dump()
