# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
maiw-execution — shared execution boundary primitives.

Architecture rule
-----------------
The ONLY path from an agent to a write capability is:

    ActionProposal
        ↓
    DecisionEngine.evaluate()  →  APPROVED
        ↓
    BaseActionExecutor.execute()  (guards 1-4)
        ↓
    _do_execute()  (domain-specific skill call)
        ↓
    MCP write capability

Guard lifecycle (enforced in execute() before any write):
    1. APPROVED gate          — decision.outcome must be APPROVED
    2. Proposal/decision bind — decision.proposal_id == proposal.proposal_id
    3. Action allowlist       — proposal.action in _ALLOWED_ACTIONS frozenset
    4. Staleness check        — decision age <= max_decision_age_seconds
    5. Additional guards hook — subclass override (_check_additional_guards)
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
    """Raised when proposal.action is not in the executor's _ALLOWED_ACTIONS frozenset."""


class ActionExpired(ValueError):
    """Raised when the decision is older than max_decision_age_seconds."""


class ActionConflict(RuntimeError):
    """Raised when domain state drifted since the snapshot (subclass guard)."""


class ActionExecutionError(RuntimeError):
    """Raised when the MCP write capability fails after all guards have passed."""


# ── Execution result ───────────────────────────────────────────────────────────


class ActionExecutionResult(BaseModel):
    """Result of a BaseActionExecutor.execute() call."""

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
    trace_id: str | None = None


# ── Protocol ───────────────────────────────────────────────────────────────────


@runtime_checkable
class ActionExecutor(Protocol):
    """Structural protocol satisfied by any executor with an execute() method."""

    async def execute(
        self,
        proposal: ActionProposal,
        decision: DecisionResult,
    ) -> ActionExecutionResult: ...


# ── NoOpActionExecutor ─────────────────────────────────────────────────────────


class NoOpActionExecutor:
    """
    Stub executor for environments where execution is not yet wired.
    Returns executed=False and logs a warning.
    """

    async def execute(
        self,
        proposal: ActionProposal,
        decision: DecisionResult,
    ) -> ActionExecutionResult:
        if decision.outcome != DecisionOutcome.APPROVED:
            raise ActionNotApproved(
                f"NoOpActionExecutor: non-APPROVED outcome {decision.outcome.value!r}"
            )
        logger.warning(
            "NoOpActionExecutor: proposal %s approved but no executor configured; skipped.",
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


# ── BaseActionExecutor ─────────────────────────────────────────────────────────


class BaseActionExecutor:
    """
    Abstract base for domain action executors.

    Subclasses must set:
        _ALLOWED_ACTIONS: frozenset[str]  — allowlisted action names

    Subclasses must implement:
        async _do_execute(proposal, decision) -> tuple[dict, str | None]
            Returns (backend_response, provider_reference).

    Subclasses may override:
        async _check_additional_guards(proposal) -> None
            Raise ActionConflict if domain state has drifted.
    """

    _ALLOWED_ACTIONS: frozenset[str] = frozenset()

    def __init__(self, *, max_decision_age_seconds: int = 300) -> None:
        self._max_decision_age_seconds = max_decision_age_seconds

    async def execute(
        self,
        proposal: ActionProposal,
        decision: DecisionResult,
    ) -> ActionExecutionResult:
        # Guard 1: APPROVED gate
        if decision.outcome != DecisionOutcome.APPROVED:
            raise ActionNotApproved(
                f"Cannot execute proposal {proposal.proposal_id!r}: "
                f"decision outcome is {decision.outcome.value!r}, not approved"
            )

        # Guard 2: Proposal/decision binding
        if decision.proposal_id != proposal.proposal_id:
            raise ActionDecisionMismatch(
                f"Decision proposal_id {decision.proposal_id!r} does not match "
                f"proposal proposal_id {proposal.proposal_id!r}"
            )

        # Guard 3: Action allowlist
        if proposal.action not in self._ALLOWED_ACTIONS:
            raise ActionUnsupported(
                f"Action {proposal.action!r} is not in the "
                f"{type(self).__name__} allowlist"
            )

        # Guard 4: Staleness check
        now_utc = datetime.now(timezone.utc)
        age_seconds = (now_utc - decision.evaluated_at).total_seconds()
        if age_seconds > self._max_decision_age_seconds:
            raise ActionExpired(
                f"Decision {decision.result_id!r} expired: "
                f"age {age_seconds:.0f}s > max {self._max_decision_age_seconds}s"
            )

        # Guard 5: Domain-specific additional guards (state-drift, etc.)
        await self._check_additional_guards(proposal)

        execution_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)

        try:
            backend_resp, provider_ref = await self._do_execute(proposal, decision)
        except (
            ActionNotApproved,
            ActionDecisionMismatch,
            ActionUnsupported,
            ActionExpired,
            ActionConflict,
        ):
            raise
        except Exception as exc:
            raise ActionExecutionError(
                f"Execution of {proposal.action!r} failed for proposal "
                f"{proposal.proposal_id!r}: {exc}"
            ) from exc

        completed_at = datetime.now(timezone.utc)
        logger.info(
            "%s: executed action=%s proposal_id=%s execution_id=%s",
            type(self).__name__,
            proposal.action,
            proposal.proposal_id,
            execution_id,
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

    async def _check_additional_guards(self, proposal: ActionProposal) -> None:
        """Override in subclasses to add domain-specific pre-execution guards."""

    async def _do_execute(
        self,
        proposal: ActionProposal,
        decision: DecisionResult,
    ) -> tuple[dict[str, Any], str | None]:
        """
        Perform the domain-specific MCP write.
        Returns (backend_response, provider_reference).
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement _do_execute()"
        )
