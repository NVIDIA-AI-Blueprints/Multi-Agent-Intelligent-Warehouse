# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""LaborActionExecutor — Labor domain executor."""

from __future__ import annotations

import logging
from typing import Any

from maiw_decision.models import DecisionResult
from maiw_mcp.contracts.actions import ActionProposal

from .base import BaseActionExecutor
from .outcome import ExecutionOutcome
from .reconciliation import ExecutionIntent

logger = logging.getLogger(__name__)


class LaborActionExecutor(BaseActionExecutor):
    """
    Concrete executor for the Labor domain.

    Execution routing (by proposal.action):
        warehouse.labor.allocate → allocate_skill

    Outcome mapping (from provider result.outcome field):
        "executed"  → EXECUTED
        "no_op"     → NO_OP
        "deferred"  → DEFERRED
        "conflict"  → CONFLICT
        "failed"    → FAILED (also: success=False with no allocation_id)
        (default)   → EXECUTED
    """

    _ALLOWED_ACTIONS: frozenset[str] = frozenset(
        {
            "warehouse.labor.allocate",
        }
    )

    def __init__(
        self,
        *,
        allocate_skill: Any,
        max_decision_age_seconds: int = 300,
        **kwargs: Any,
    ) -> None:
        super().__init__(max_decision_age_seconds=max_decision_age_seconds, **kwargs)
        self._allocate_skill = allocate_skill

    def _build_intent(
        self,
        proposal: ActionProposal,
        decision: DecisionResult,
        *,
        trace_id: str | None = None,
    ) -> ExecutionIntent:
        params = proposal.parameters
        return ExecutionIntent(
            capability=proposal.action,
            proposal_id=proposal.proposal_id,
            decision_id=decision.result_id,
            warehouse_id=params.get("warehouse_id"),
            target=params.get("task_id"),
            expected_effect={
                "task_id": params.get("task_id"),
                "expected_worker_ids": params.get("worker_ids", []),
                "expected_task_status": "in_progress",
            },
            idempotency_key=proposal.idempotency_key,
            trace_id=trace_id,
        )

    async def _do_execute(
        self,
        proposal: ActionProposal,
        decision: DecisionResult,
        execution_id: str,
    ) -> tuple[dict[str, Any], str | None, ExecutionOutcome]:
        from maiw_mcp.contracts.labor import LaborAllocateRequest

        params = proposal.parameters
        req = LaborAllocateRequest(
            warehouse_id=params.get("warehouse_id", "default"),
            task_id=params["task_id"],
            task_type=params.get("task_type", "PICK"),
            worker_ids=params.get("worker_ids", []),
            zone=params.get("zone"),
            priority=params.get("priority", "medium"),
            notes=params.get("notes"),
            proposal_id=proposal.proposal_id,
            decision_id=decision.result_id,
            execution_id=execution_id,
        )
        result = await self._allocate_skill.execute(req)
        resp = result.model_dump()

        outcome = _map_outcome(resp.get("outcome", ""), result.success)
        return resp, resp.get("allocation_id"), outcome


def _map_outcome(outcome_str: str, success: bool) -> ExecutionOutcome:
    """Map a provider outcome string to the canonical ExecutionOutcome."""
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
    # Legacy: derive from success flag when outcome field is absent
    return ExecutionOutcome.EXECUTED if success else ExecutionOutcome.FAILED
