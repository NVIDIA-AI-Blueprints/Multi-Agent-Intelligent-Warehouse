# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""LaborActionExecutor — Labor domain executor."""

from __future__ import annotations

import logging
from typing import Any

from maiw_decision.models import DecisionResult
from maiw_mcp.contracts.actions import ActionProposal

from .base import BaseActionExecutor

logger = logging.getLogger(__name__)


class LaborActionExecutor(BaseActionExecutor):
    """
    Concrete executor for the Labor domain.

    Execution routing (by proposal.action):
        warehouse.labor.allocate → allocate_skill
    """

    _ALLOWED_ACTIONS: frozenset[str] = frozenset({
        "warehouse.labor.allocate",
    })

    def __init__(
        self,
        *,
        allocate_skill: Any,
        max_decision_age_seconds: int = 300,
    ) -> None:
        super().__init__(max_decision_age_seconds=max_decision_age_seconds)
        self._allocate_skill = allocate_skill

    async def _do_execute(
        self,
        proposal: ActionProposal,
        decision: DecisionResult,
    ) -> tuple[dict[str, Any], str | None]:
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
        )
        result = await self._allocate_skill.execute(req)
        resp = result.model_dump()
        return resp, resp.get("allocation_id")
