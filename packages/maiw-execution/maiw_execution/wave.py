# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""WaveActionExecutor — Wave domain executor."""

from __future__ import annotations

import logging
from typing import Any

from maiw_decision.models import DecisionResult
from maiw_mcp.contracts.actions import ActionProposal

from .base import BaseActionExecutor
from .outcome import ExecutionOutcome

logger = logging.getLogger(__name__)


class WaveActionExecutor(BaseActionExecutor):
    """
    Concrete executor for the Wave domain.

    Execution routing (by proposal.action):
        warehouse.wave.reprioritize → reprioritize_skill
    """

    _ALLOWED_ACTIONS: frozenset[str] = frozenset({
        "warehouse.wave.reprioritize",
    })

    def __init__(
        self,
        *,
        reprioritize_skill: Any,
        max_decision_age_seconds: int = 300,
        **kwargs: Any,
    ) -> None:
        super().__init__(max_decision_age_seconds=max_decision_age_seconds, **kwargs)
        self._reprioritize_skill = reprioritize_skill

    async def _do_execute(
        self,
        proposal: ActionProposal,
        decision: DecisionResult,
        execution_id: str,
    ) -> tuple[dict[str, Any], str | None, ExecutionOutcome]:
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
            execution_id=execution_id,
        )
        result = await self._reprioritize_skill.execute(req)
        resp = result.model_dump()

        outcome_str = resp.get("outcome", "")
        if outcome_str == "no_op":
            outcome = ExecutionOutcome.NO_OP
        elif outcome_str == "failed":
            outcome = ExecutionOutcome.FAILED
        elif outcome_str == "conflict":
            outcome = ExecutionOutcome.CONFLICT
        elif outcome_str == "deferred":
            outcome = ExecutionOutcome.DEFERRED
        else:
            outcome = ExecutionOutcome.EXECUTED if result.success else ExecutionOutcome.FAILED

        return resp, None, outcome
