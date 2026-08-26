# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
maiw-execution — shared execution boundary primitives.

Phase 10E Batch 1: canonical ExecutionOutcome, ExecutionRegistry integration,
trace propagation, and execution_id survival through the write path.

Architecture rule
-----------------
The ONLY path from an agent to a write capability is:

    ActionProposal
        ↓
    DecisionEngine.evaluate()  →  APPROVED
        ↓
    BaseActionExecutor.execute()  (guards 1-5)
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

Execution outcomes (Phase 10E)
------------------------------
    EXECUTED  — provider confirmed mutation occurred
    NO_OP     — desired state already existed; no mutation required
    DEFERRED  — valid request, cannot execute now
    CONFLICT  — current warehouse state prevents this action
    UNKNOWN   — mutation may have occurred; response was lost (AmbiguousWriteError)
    FAILED    — no mutation occurred; provider rejected or was unreachable

Identity chain
--------------
    trace_id        — full request lifecycle correlation
    proposal_id     — the proposed warehouse change
    decision_id     — the authority evaluation
    execution_id    — this logical execution attempt (generated before write,
                      propagated through MCP to the provider)
    idempotency_key — identity of the intended logical mutation (caller-supplied)
    provider_reference — backend-specific transaction/allocation reference
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, Field, model_validator

from maiw_decision.models import DecisionOutcome, DecisionResult
from maiw_mcp.contracts.actions import ActionProposal
from maiw_mcp.deadline import RequestDeadline, RequestDeadlineExceeded

from .outcome import AmbiguousWriteError, ExecutionOutcome
from .reconciliation import ExecutionIntent
from .registry import ExecutionRecord, ExecutionRegistry

logger = logging.getLogger(__name__)


# ── Typed execution errors (guard violations) ──────────────────────────────────
# These are raised BEFORE any write attempt; they represent programming errors
# or authorization failures, not backend/provider failures.


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
    """
    Kept for backward compatibility with external callers that may import it.
    BaseActionExecutor no longer raises this — backend failures are returned
    as ActionExecutionResult(outcome=FAILED) instead.
    """


# ── Canonical execution result ─────────────────────────────────────────────────


class ActionExecutionResult(BaseModel):
    """
    Result of a BaseActionExecutor.execute() call.

    Phase 10E: ``outcome`` is the canonical field. ``executed`` and ``success``
    are backward-compatible derived fields — do not set them independently.
    """

    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    outcome: ExecutionOutcome = ExecutionOutcome.FAILED

    # Backward-compat fields — derived from outcome by model_validator.
    # Do not set these independently; the validator will override them.
    executed: bool = False
    success: bool = False

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

    # Mutation evidence for reliability testing (not a production business field)
    physical_mutation_occurred: bool | None = None

    @model_validator(mode="after")
    def _derive_compat_from_outcome(self) -> "ActionExecutionResult":
        """outcome is authoritative — derive executed and success from it."""
        self.executed = self.outcome == ExecutionOutcome.EXECUTED
        self.success = self.outcome in (ExecutionOutcome.EXECUTED, ExecutionOutcome.NO_OP)
        return self


# ── Protocol ───────────────────────────────────────────────────────────────────


@runtime_checkable
class ActionExecutor(Protocol):
    """Structural protocol satisfied by any executor with an execute() method."""

    async def execute(
        self,
        proposal: ActionProposal,
        decision: DecisionResult,
        *,
        trace_id: str | None = None,
        deadline: RequestDeadline | None = None,
    ) -> ActionExecutionResult: ...


# ── NoOpActionExecutor ─────────────────────────────────────────────────────────


class NoOpActionExecutor:
    """
    Stub executor for environments where execution is not yet wired.
    Returns outcome=DEFERRED and logs a warning.
    """

    async def execute(
        self,
        proposal: ActionProposal,
        decision: DecisionResult,
        *,
        trace_id: str | None = None,
        deadline: RequestDeadline | None = None,
    ) -> ActionExecutionResult:
        if deadline is not None and deadline.expired:
            raise RequestDeadlineExceeded(
                expired_by_ms=(deadline._clock() - deadline.deadline_at) * 1000.0  # type: ignore[operator]
            )
        if decision.outcome != DecisionOutcome.APPROVED:
            raise ActionNotApproved(
                f"NoOpActionExecutor: non-APPROVED outcome {decision.outcome.value!r}"
            )
        logger.warning(
            "NoOpActionExecutor: proposal %s approved but no executor configured; deferred.",
            proposal.proposal_id,
        )
        now = datetime.now(timezone.utc)
        return ActionExecutionResult(
            outcome=ExecutionOutcome.DEFERRED,
            action=proposal.action,
            proposal_id=proposal.proposal_id,
            decision_id=decision.result_id,
            backend_response={"note": "no_executor_configured"},
            started_at=now,
            completed_at=None,
            executed_at=now,
            trace_id=trace_id,
        )


# ── BaseActionExecutor ─────────────────────────────────────────────────────────


class BaseActionExecutor:
    """
    Abstract base for domain action executors.

    Subclasses must set:
        _ALLOWED_ACTIONS: frozenset[str]  — allowlisted action names

    Subclasses must implement:
        async _do_execute(proposal, decision, execution_id)
            -> tuple[dict, str | None, ExecutionOutcome]
            Returns (backend_response, provider_reference, outcome).

    Subclasses may override:
        async _check_additional_guards(proposal) -> None
            Raise ActionConflict if domain state has drifted.

    Phase 10E registry:
        Pass ``registry=ExecutionRegistry()`` to enable single-process idempotency.
        SINGLE-PROCESS SAFETY only — multi-replica idempotency requires Batch 3.
    """

    _ALLOWED_ACTIONS: frozenset[str] = frozenset()

    def __init__(
        self,
        *,
        max_decision_age_seconds: int = 300,
        registry: Optional[ExecutionRegistry] = None,
    ) -> None:
        self._max_decision_age_seconds = max_decision_age_seconds
        self._registry = registry

    async def execute(
        self,
        proposal: ActionProposal,
        decision: DecisionResult,
        *,
        trace_id: str | None = None,
        deadline: RequestDeadline | None = None,
    ) -> ActionExecutionResult:
        """
        Execute an approved action proposal through all guards.

        trace_id is accepted directly — no post-construction injection needed.

        Returns ActionExecutionResult with canonical outcome field.
        Guard violations (pre-execution authorization failures) still raise.
        Backend/provider failures return result with outcome=FAILED.
        Ambiguous writes (post-mutation response lost) return outcome=UNKNOWN.
        Deadline expired before write → raises RequestDeadlineExceeded (no mutation).
        """
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

        # Guard 6: Deadline — must check immediately before write; no mutation on expiry
        if deadline is not None and deadline.expired:
            raise RequestDeadlineExceeded(
                expired_by_ms=(deadline._clock() - deadline.deadline_at) * 1000.0  # type: ignore[operator]
            )

        # Generate execution_id before the write — stable for the full lifecycle
        execution_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)

        # Build intent snapshot before any write (immutable; used by reconciliation)
        intent = self._build_intent(proposal, decision, trace_id=trace_id)

        # Idempotency check — single-process guard
        if self._registry is not None:
            existing = self._registry.begin(
                execution_id,
                proposal.idempotency_key,
                proposal.action,
                proposal.proposal_id,
                intent=intent,
            )
            if existing is not None:
                return self._idempotent_result(existing, proposal, decision, execution_id, trace_id)

        # ── Write path ─────────────────────────────────────────────────────────
        try:
            backend_resp, provider_ref, outcome = await self._do_execute(
                proposal, decision, execution_id
            )
        except (
            ActionNotApproved,
            ActionDecisionMismatch,
            ActionUnsupported,
            ActionExpired,
            ActionConflict,
        ):
            # Guard-type exceptions re-raise — they indicate pre-write authorization failure
            raise
        except AmbiguousWriteError as exc:
            # Mutation occurred; response was lost — UNKNOWN, do NOT retry
            if self._registry is not None:
                self._registry.mark_unknown(execution_id)
            result = ActionExecutionResult(
                execution_id=execution_id,
                outcome=ExecutionOutcome.UNKNOWN,
                action=proposal.action,
                proposal_id=proposal.proposal_id,
                decision_id=decision.result_id,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                executed_at=datetime.now(timezone.utc),
                error_message=str(exc),
                trace_id=trace_id,
                physical_mutation_occurred=True,
            )
            if self._registry is not None:
                self._registry.complete(execution_id, ExecutionOutcome.UNKNOWN, result)
            logger.error(
                "%s: UNKNOWN execution action=%s proposal_id=%s execution_id=%s — "
                "mutation may have occurred; reconciliation required",
                type(self).__name__, proposal.action, proposal.proposal_id, execution_id,
            )
            return result
        except Exception as exc:
            # Pre-mutation or unclassified backend failure — FAILED
            result = ActionExecutionResult(
                execution_id=execution_id,
                outcome=ExecutionOutcome.FAILED,
                action=proposal.action,
                proposal_id=proposal.proposal_id,
                decision_id=decision.result_id,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                executed_at=datetime.now(timezone.utc),
                error_message=str(exc),
                trace_id=trace_id,
                physical_mutation_occurred=False,
            )
            if self._registry is not None:
                self._registry.complete(execution_id, ExecutionOutcome.FAILED, result)
            logger.error(
                "%s: FAILED execution action=%s proposal_id=%s execution_id=%s: %s",
                type(self).__name__, proposal.action, proposal.proposal_id, execution_id, exc,
            )
            return result

        completed_at = datetime.now(timezone.utc)
        logger.info(
            "%s: %s action=%s proposal_id=%s execution_id=%s",
            type(self).__name__,
            outcome.value,
            proposal.action,
            proposal.proposal_id,
            execution_id,
        )

        result = ActionExecutionResult(
            execution_id=execution_id,
            outcome=outcome,
            action=proposal.action,
            proposal_id=proposal.proposal_id,
            decision_id=decision.result_id,
            provider_reference=provider_ref or None,
            backend_response=backend_resp,
            started_at=started_at,
            completed_at=completed_at,
            executed_at=completed_at,
            trace_id=trace_id,
            physical_mutation_occurred=(outcome == ExecutionOutcome.EXECUTED),
        )

        if self._registry is not None:
            self._registry.complete(execution_id, outcome, result)

        return result

    def _idempotent_result(
        self,
        existing: "ExecutionRecord",
        proposal: ActionProposal,
        decision: DecisionResult,
        current_execution_id: str,
        trace_id: str | None,
    ) -> ActionExecutionResult:
        """Return a result for a duplicate execution attempt."""
        if existing.outcome is None:
            # Prior attempt is still in-flight — treat as UNKNOWN
            logger.warning(
                "%s: duplicate detected for in-flight execution_id=%s or "
                "idempotency_key=%r; returning UNKNOWN",
                type(self).__name__, existing.execution_id, existing.idempotency_key,
            )
            return ActionExecutionResult(
                execution_id=existing.execution_id,
                outcome=ExecutionOutcome.UNKNOWN,
                action=proposal.action,
                proposal_id=proposal.proposal_id,
                decision_id=decision.result_id,
                error_message="Duplicate detected for in-flight execution",
                trace_id=trace_id,
            )

        if existing.outcome == ExecutionOutcome.UNKNOWN:
            # Prior attempt ended UNKNOWN — do not re-execute; reconciliation required
            logger.warning(
                "%s: prior execution execution_id=%s is UNKNOWN; "
                "returning UNKNOWN — reconciliation required before retry",
                type(self).__name__, existing.execution_id,
            )
            return ActionExecutionResult(
                execution_id=existing.execution_id,
                outcome=ExecutionOutcome.UNKNOWN,
                action=proposal.action,
                proposal_id=proposal.proposal_id,
                decision_id=decision.result_id,
                error_message="Prior execution is UNKNOWN; reconciliation required",
                trace_id=trace_id,
            )

        # Prior attempt completed — return NO_OP pointing to original result.
        # outcome=NO_OP means "this logical execution already completed earlier"
        # (not "desired state pre-existed"); backend_response carries replay metadata
        # so callers can distinguish idempotent replay from a genuine no-mutation read.
        logger.info(
            "%s: idempotent replay — prior execution_id=%s completed with outcome=%s; "
            "suppressing duplicate physical mutation",
            type(self).__name__, existing.execution_id, existing.outcome.value,
        )
        prior_resp = existing.result.backend_response if existing.result else {}
        return ActionExecutionResult(
            execution_id=existing.execution_id,
            outcome=ExecutionOutcome.NO_OP,
            action=proposal.action,
            proposal_id=proposal.proposal_id,
            decision_id=decision.result_id,
            provider_reference=existing.result.provider_reference if existing.result else None,
            backend_response={
                **prior_resp,
                "replayed": True,
                "original_execution_id": existing.execution_id,
                "original_outcome": existing.outcome.value,
            },
            trace_id=trace_id,
        )

    async def _check_additional_guards(self, proposal: ActionProposal) -> None:
        """Override in subclasses to add domain-specific pre-execution guards."""

    def _build_intent(
        self,
        proposal: ActionProposal,
        decision: DecisionResult,
        *,
        trace_id: str | None = None,
    ) -> ExecutionIntent:
        """
        Build an immutable ExecutionIntent snapshot before the write.

        Override in domain subclasses to provide precise expected_effect.
        The base implementation captures capability/ID fields with an empty
        expected_effect; reconciliation will return INDETERMINATE without a
        populated expected_effect.

        The returned ExecutionIntent is stored in ExecutionRecord.intent at
        registry.begin() time. It must be captured before any write so
        reconciliation never depends on mutable proposal/decision objects.
        """
        return ExecutionIntent(
            capability=proposal.action,
            proposal_id=proposal.proposal_id,
            decision_id=decision.result_id,
            warehouse_id=proposal.parameters.get("warehouse_id"),
            target=None,
            expected_effect={},
            approval_id=None,
            idempotency_key=proposal.idempotency_key,
            trace_id=trace_id,
        )

    async def _do_execute(
        self,
        proposal: ActionProposal,
        decision: DecisionResult,
        execution_id: str,
    ) -> tuple[dict[str, Any], str | None, ExecutionOutcome]:
        """
        Perform the domain-specific MCP write.

        Parameters
        ----------
        execution_id:
            Stable MAIW-generated identity for this write attempt.
            Must be propagated through the skill call into the MCP payload
            and returned in the provider result.

        Returns
        -------
        (backend_response, provider_reference, outcome)
            backend_response  : raw dict from the provider
            provider_reference: backend-generated transaction ID (allocation_id, etc.)
            outcome           : canonical ExecutionOutcome for this write
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement _do_execute()"
        )
