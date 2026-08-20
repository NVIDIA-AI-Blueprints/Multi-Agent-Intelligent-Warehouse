# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
DecisionEngine data models.

DecisionOutcome
---------------
The four possible outcomes of a decision evaluation.  The engine never
"executes" an action — it only classifies the proposal.

ConstraintViolation
-------------------
A single rule that was violated.  Multiple violations may exist per
evaluation; all are included in the DecisionResult.

DecisionRequest
---------------
Input to the DecisionEngine: an ActionProposal paired with a
WarehouseStateSnapshot.  The snapshot is required so that the engine
always evaluates against a consistent, timestamped view of reality.

DecisionResult
--------------
Output of the DecisionEngine evaluation.  Immutable; assigned a UUID at
creation time for audit linkage.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from maiw_mcp.contracts.actions import ActionProposal
from maiw_state.warehouse import WarehouseStateSnapshot


class DecisionOutcome(str, Enum):
    """
    Outcome of a DecisionEngine evaluation.

    Values
    ------
    APPROVED
        All rules passed; the action may proceed.  The caller is still
        responsible for the actual execution — the engine never mutates
        any system.
    REJECTED
        One or more hard constraints were violated.  The action must not
        proceed.
    REQUIRES_HUMAN_APPROVAL
        The proposal exceeds the autonomous-approval threshold.  A human
        must review and approve before execution.
    REQUIRES_FRESH_STATE
        A required state component is stale or absent.  The caller should
        refresh state and re-submit.
    """

    APPROVED = "approved"
    REJECTED = "rejected"
    REQUIRES_HUMAN_APPROVAL = "requires_human_approval"
    REQUIRES_FRESH_STATE = "requires_fresh_state"


class ConstraintViolation(BaseModel):
    """A single rule that blocked or flagged a proposal."""

    rule: str = Field(description="Machine-readable rule identifier")
    message: str = Field(description="Human-readable explanation")
    details: dict[str, Any] = Field(default_factory=dict)


class DecisionRequest(BaseModel):
    """
    Input to the DecisionEngine.

    The engine evaluates *proposal* against the operational reality
    captured in *state*.  Both are required.
    """

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    proposal: ActionProposal
    state: WarehouseStateSnapshot
    requested_by: str = "unknown"
    trace_id: str | None = None


class DecisionResult(BaseModel):
    """
    Output of a single DecisionEngine evaluation.

    Fields
    ------
    result_id:
        UUID for audit linkage.
    request_id:
        Echoes ``DecisionRequest.request_id``.
    proposal_id:
        Echoes ``ActionProposal.proposal_id``.
    outcome:
        The classification result.
    violations:
        All constraint violations found (empty for APPROVED).
    evaluated_at:
        UTC timestamp of evaluation.
    engine_version:
        Version string from DecisionEngine; bumped when rule logic changes.
    """

    result_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str
    proposal_id: str
    outcome: DecisionOutcome
    violations: list[ConstraintViolation] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    engine_version: str = "1.0.0"
