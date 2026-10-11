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
    UNKNOWN   — mutation may have occurred and MAIW cannot tell: AmbiguousWriteError;
                any MCP transport failure AFTER tools/call was dispatched
                (round 3); and — round 4, NEW4-P1-01 — any server-reported
                error or non-success result after dispatch that does not carry
                the explicit ``execution_disposition = NOT_APPLIED``
    FAILED    — no mutation occurred: the request was provably never
                dispatched, or the server explicitly certified NOT_APPLIED
                (rejected before any mutation)

Failure classification (rounds 3 + 4) — ``classify_write_failure``:

    AmbiguousWriteError                → UNKNOWN  (mutation known to have occurred)
    WriteNotDispatched                 → FAILED   (request could not be built;
                                                   nothing was sent)
    MCPNotDispatched                   → FAILED   (MCPConnectFailed,
                                                   MCPConnectTimeout, MCPCircuitOpen)
    MCPToolNotApplied                  → FAILED   (server certified NOT_APPLIED in
                                                   structuredContent)
    WriteNotApplied                    → FAILED   (in-process provider certified
                                                   no mutation)
    MCPToolError (any other, incl.     → UNKNOWN  (isError alone is NOT proof of
      MCPToolErrorOutcomeUnknown)                  non-execution — round 4)
    MCPDispatchOutcomeUnknown          → UNKNOWN  (MCPResponseLost,
                                                   MCPTimeoutAfterDispatch)
    MCPTimeout (phase not recorded)    → UNKNOWN  (a timed-out call was in flight)
    MCPContractError                   → UNKNOWN  (the server answered; the answer
                                                   could not be read)
    CapabilityNotFound / deadline      → FAILED   (nothing was sent)
    anything else                      → UNKNOWN  (fail safe — round 4: the phase
                                                   is not known, so non-execution
                                                   is not proven)

A non-error provider result reporting FAILED / CONFLICT / DEFERRED (or
``success=false``) is likewise only a definite non-execution when it carries
``execution_disposition = "NOT_APPLIED"``; otherwise it becomes UNKNOWN
(``SERVER_FAILURE_UNCERTIFIED``).  A result with ``success=false`` and a
success outcome (``executed`` / ``no_op``) is contradictory → UNKNOWN
(``SERVER_RESULT_CONTRADICTORY``).

An UNKNOWN result is never retried here; the registry blocks every further
write to the same domain target until the UNKNOWN is reconciled.

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
from maiw_decision.proposal import ActionProposal
from maiw_mcp.deadline import RequestDeadline, RequestDeadlineExceeded
from maiw_mcp.errors import (
    CapabilityNotFound,
    MCPContractError,
    MCPDispatchOutcomeUnknown,
    MCPNotDispatched,
    MCPTimeout,
    MCPToolError,
    MCPToolNotApplied,
    WriteNotApplied,
)
from maiw_mcp.write_disposition import certifies_not_applied, describe_disposition

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


class WriteNotDispatched(RuntimeError):
    """
    Raised by a domain executor when the write request could not even be
    built (invalid parameters) — nothing was sent, so the outcome is a
    definite FAILED.  Round 4: every other unclassified exception is UNKNOWN.
    """


# ── Write-failure classification (v2.0.1 round 3, NEW3-P1-02) ─────────────────


def classify_write_failure(
    exc: BaseException,
) -> tuple[ExecutionOutcome, str, bool | None]:
    """
    Map an exception raised by a domain write to ``(outcome, error_code,
    physical_mutation_occurred)``.  See the module docstring for the table.
    ``physical_mutation_occurred`` is ``None`` when it is genuinely unknown.

    Round 4 (NEW4-P1-01): only a provable non-dispatch or an explicit
    ``NOT_APPLIED`` certification yields FAILED; the order of the checks
    matters (``MCPToolErrorOutcomeUnknown`` is both an ``MCPToolError`` and an
    ``MCPDispatchOutcomeUnknown``; ``WriteNotApplied`` is a
    ``BackendUnavailable``).
    """
    if isinstance(exc, AmbiguousWriteError):
        return ExecutionOutcome.UNKNOWN, "AMBIGUOUS_WRITE", True
    if isinstance(exc, WriteNotDispatched):
        return ExecutionOutcome.FAILED, "NOT_DISPATCHED", False
    if isinstance(exc, MCPNotDispatched):
        return ExecutionOutcome.FAILED, "MCP_NOT_DISPATCHED", False
    if isinstance(exc, MCPToolNotApplied):
        return ExecutionOutcome.FAILED, "MCP_TOOL_NOT_APPLIED", False
    if isinstance(exc, WriteNotApplied):
        return ExecutionOutcome.FAILED, "WRITE_NOT_APPLIED", False
    if isinstance(exc, MCPToolError):
        return ExecutionOutcome.UNKNOWN, "MCP_TOOL_ERROR", None
    if isinstance(exc, MCPDispatchOutcomeUnknown):
        return ExecutionOutcome.UNKNOWN, "MCP_RESPONSE_LOST", None
    if isinstance(exc, MCPTimeout):
        return ExecutionOutcome.UNKNOWN, "MCP_TIMEOUT", None
    if isinstance(exc, MCPContractError):
        return ExecutionOutcome.UNKNOWN, "MCP_RESPONSE_UNREADABLE", None
    if isinstance(exc, (CapabilityNotFound, RequestDeadlineExceeded)):
        return ExecutionOutcome.FAILED, "NOT_DISPATCHED", False
    return ExecutionOutcome.UNKNOWN, "EXECUTION_OUTCOME_UNKNOWN", None


# Journal vocabulary for ``ActionExecutionResult.dispatch_status`` (round 4).
DISPATCH_NOT_DISPATCHED = "not_dispatched"
DISPATCH_REJECTED_BEFORE_MUTATION = "rejected_before_mutation"
DISPATCH_SERVER_ERROR = "dispatched_server_error"
DISPATCH_NO_RESPONSE = "dispatched_no_response"
DISPATCH_UNREADABLE_RESPONSE = "dispatched_unreadable_response"
DISPATCH_MUTATION_KNOWN = "dispatched_mutation_known"
DISPATCH_RESPONSE_RECEIVED = "dispatched_response_received"
DISPATCH_UNKNOWN = "unknown"


def _dispatch_status(exc: BaseException) -> str:
    if isinstance(exc, AmbiguousWriteError):
        return DISPATCH_MUTATION_KNOWN
    if isinstance(
        exc,
        (
            WriteNotDispatched,
            MCPNotDispatched,
            CapabilityNotFound,
            RequestDeadlineExceeded,
        ),
    ):
        return DISPATCH_NOT_DISPATCHED
    if isinstance(exc, (MCPToolNotApplied, WriteNotApplied)):
        return DISPATCH_REJECTED_BEFORE_MUTATION
    if isinstance(exc, MCPToolError):
        return DISPATCH_SERVER_ERROR
    if isinstance(exc, (MCPDispatchOutcomeUnknown, MCPTimeout)):
        return DISPATCH_NO_RESPONSE
    if isinstance(exc, MCPContractError):
        return DISPATCH_UNREADABLE_RESPONSE
    return DISPATCH_UNKNOWN


def _server_disposition(exc: BaseException) -> str | None:
    if isinstance(exc, (MCPToolNotApplied, WriteNotApplied)):
        return "NOT_APPLIED"
    observed = getattr(exc, "observed_disposition", None)
    if isinstance(observed, str):
        return observed
    if isinstance(exc, MCPToolError):
        return "absent"
    return None


_UNCERTAINTY_REASONS = {
    "AMBIGUOUS_WRITE": "provider reported the mutation occurred but the response was lost",
    "MCP_TOOL_ERROR": (
        "server returned a tool error after tools/call was dispatched without "
        "certifying NOT_APPLIED; the mutation may have been applied"
    ),
    "MCP_RESPONSE_LOST": "tools/call was dispatched and no usable response arrived",
    "MCP_TIMEOUT": "a dispatched call timed out",
    "MCP_RESPONSE_UNREADABLE": "the server answered but the answer could not be read",
    "EXECUTION_OUTCOME_UNKNOWN": (
        "unclassified failure during the write; non-execution is not proven"
    ),
    "SERVER_FAILURE_UNCERTIFIED": (
        "server reported a non-success outcome without certifying NOT_APPLIED; "
        "the mutation may have been applied"
    ),
    "SERVER_REPORTED_UNKNOWN": "server reported the outcome as unknown",
    "SERVER_RESULT_CONTRADICTORY": (
        "server result says success=false with a success outcome; neither "
        "execution nor non-execution is established"
    ),
}


_NON_EXECUTION_OUTCOMES = frozenset(
    {ExecutionOutcome.FAILED, ExecutionOutcome.CONFLICT, ExecutionOutcome.DEFERRED}
)


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

    # Round 4 (NEW4-P1-01) journal evidence: how far the write got, what the
    # server certified (``NOT_APPLIED`` / absent / malformed …) and, for an
    # UNKNOWN, why non-execution is not proven.
    dispatch_status: str | None = None
    server_disposition: str | None = None
    uncertainty_reason: str | None = None

    @model_validator(mode="after")
    def _derive_compat_from_outcome(self) -> "ActionExecutionResult":
        """outcome is authoritative — derive executed and success from it."""
        self.executed = self.outcome == ExecutionOutcome.EXECUTED
        self.success = self.outcome in (
            ExecutionOutcome.EXECUTED,
            ExecutionOutcome.NO_OP,
        )
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
                return self._idempotent_result(
                    existing, proposal, decision, execution_id, trace_id
                )

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
        except Exception as exc:
            outcome, error_code, mutation = classify_write_failure(exc)
            dispatch_status = _dispatch_status(exc)
            if outcome == ExecutionOutcome.UNKNOWN:
                # The write may have been applied; the response was lost.
                # UNKNOWN — never FAILED, never retried here (round 3).
                if self._registry is not None:
                    self._registry.mark_unknown(execution_id)
            result = ActionExecutionResult(
                execution_id=execution_id,
                outcome=outcome,
                action=proposal.action,
                proposal_id=proposal.proposal_id,
                decision_id=decision.result_id,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                executed_at=datetime.now(timezone.utc),
                error_code=error_code,
                error_message=str(exc),
                trace_id=trace_id,
                physical_mutation_occurred=mutation,
                dispatch_status=dispatch_status,
                server_disposition=_server_disposition(exc),
                uncertainty_reason=(
                    _UNCERTAINTY_REASONS.get(error_code)
                    if outcome == ExecutionOutcome.UNKNOWN
                    else None
                ),
            )
            if self._registry is not None:
                self._registry.complete(execution_id, outcome, result)
            if outcome == ExecutionOutcome.UNKNOWN:
                logger.error(
                    "%s: UNKNOWN execution action=%s proposal_id=%s execution_id=%s "
                    "(%s) — mutation may have occurred; reconciliation required, "
                    "no retry",
                    type(self).__name__,
                    proposal.action,
                    proposal.proposal_id,
                    execution_id,
                    error_code,
                )
            else:
                logger.error(
                    "%s: FAILED execution action=%s proposal_id=%s execution_id=%s "
                    "(%s): %s",
                    type(self).__name__,
                    proposal.action,
                    proposal.proposal_id,
                    execution_id,
                    error_code,
                    exc,
                )
            return result

        completed_at = datetime.now(timezone.utc)

        # Round 4 (NEW4-P1-01): the server answered with a result.  A result
        # that claims non-execution (FAILED / CONFLICT / DEFERRED) is only
        # trusted when it carries the explicit NOT_APPLIED disposition; any
        # other non-success after dispatch may hide an applied mutation.
        error_code: str | None = None
        mutation: bool | None = None
        disposition = describe_disposition(backend_resp)
        if (
            isinstance(backend_resp, dict)
            and backend_resp.get("success") is False
            and outcome in (ExecutionOutcome.EXECUTED, ExecutionOutcome.NO_OP)
        ):
            # ``success: false`` with a success outcome (e.g. the contract's
            # default ``outcome="executed"`` left on a failure result) is
            # contradictory: neither success nor non-execution is established.
            logger.error(
                "%s: contradictory provider result for action=%s execution_id=%s "
                "(success=false, outcome=%s) — treating as UNKNOWN",
                type(self).__name__,
                proposal.action,
                execution_id,
                outcome.value,
            )
            outcome = ExecutionOutcome.UNKNOWN
            error_code = "SERVER_RESULT_CONTRADICTORY"
        elif outcome in _NON_EXECUTION_OUTCOMES:
            if certifies_not_applied(backend_resp):
                mutation = False
            else:
                logger.error(
                    "%s: provider reported %s for action=%s execution_id=%s "
                    "without execution_disposition=NOT_APPLIED (%s) — "
                    "treating as UNKNOWN",
                    type(self).__name__,
                    outcome.value,
                    proposal.action,
                    execution_id,
                    disposition,
                )
                outcome = ExecutionOutcome.UNKNOWN
                error_code = "SERVER_FAILURE_UNCERTIFIED"
        elif outcome == ExecutionOutcome.UNKNOWN:
            error_code = "SERVER_REPORTED_UNKNOWN"
        else:
            mutation = outcome == ExecutionOutcome.EXECUTED

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
            error_code=error_code,
            physical_mutation_occurred=mutation,
            dispatch_status=DISPATCH_RESPONSE_RECEIVED,
            server_disposition=(
                disposition if outcome != ExecutionOutcome.EXECUTED else None
            ),
            uncertainty_reason=(
                _UNCERTAINTY_REASONS.get(error_code or "")
                if outcome == ExecutionOutcome.UNKNOWN
                else None
            ),
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
                type(self).__name__,
                existing.execution_id,
                existing.idempotency_key,
            )
            return ActionExecutionResult(
                execution_id=existing.execution_id,
                outcome=ExecutionOutcome.UNKNOWN,
                action=proposal.action,
                proposal_id=proposal.proposal_id,
                decision_id=decision.result_id,
                error_code="DUPLICATE_IN_FLIGHT",
                error_message="Duplicate detected for in-flight execution",
                backend_response={"blocked_by_execution_id": existing.execution_id},
                trace_id=trace_id,
            )

        if existing.outcome == ExecutionOutcome.UNKNOWN and (
            existing.effective_status == "effectively_executed"
        ):
            # Round 3: the UNKNOWN was reconciled as executed — replay, no write.
            return ActionExecutionResult(
                execution_id=existing.execution_id,
                outcome=ExecutionOutcome.NO_OP,
                action=proposal.action,
                proposal_id=proposal.proposal_id,
                decision_id=decision.result_id,
                backend_response={
                    "replayed": True,
                    "original_execution_id": existing.execution_id,
                    "original_outcome": ExecutionOutcome.UNKNOWN.value,
                    "effective_status": existing.effective_status,
                },
                trace_id=trace_id,
            )

        if existing.outcome == ExecutionOutcome.UNKNOWN and (
            existing.effective_status == "effectively_not_executed"
        ):
            # Reconciled as NOT executed: this attempt does not write either;
            # the caller re-proposes (new idempotency key) through governance.
            return ActionExecutionResult(
                execution_id=existing.execution_id,
                outcome=ExecutionOutcome.FAILED,
                action=proposal.action,
                proposal_id=proposal.proposal_id,
                decision_id=decision.result_id,
                error_code="PRIOR_ATTEMPT_NOT_EXECUTED",
                error_message=(
                    "Prior attempt with this identity was reconciled as not "
                    "executed; re-propose with a new idempotency key"
                ),
                backend_response={"original_execution_id": existing.execution_id},
                trace_id=trace_id,
                physical_mutation_occurred=False,
            )

        if existing.outcome == ExecutionOutcome.UNKNOWN:
            # Prior attempt ended UNKNOWN — do not re-execute; reconciliation required
            logger.warning(
                "%s: prior execution execution_id=%s is UNKNOWN; "
                "returning UNKNOWN — reconciliation required before retry",
                type(self).__name__,
                existing.execution_id,
            )
            return ActionExecutionResult(
                execution_id=existing.execution_id,
                outcome=ExecutionOutcome.UNKNOWN,
                action=proposal.action,
                proposal_id=proposal.proposal_id,
                decision_id=decision.result_id,
                error_code="RECONCILIATION_REQUIRED",
                error_message="Prior execution is UNKNOWN; reconciliation required",
                backend_response={"blocked_by_execution_id": existing.execution_id},
                trace_id=trace_id,
            )

        if existing.outcome in _NON_EXECUTION_OUTCOMES:
            # Round 4 (fourth re-audit NEW4-P2-01): a replay of a definite
            # non-execution must not answer success semantics (``no_op``).  It
            # answers the original outcome again — still without writing; a
            # new attempt needs a new idempotency key (re-proposal).
            prior = existing.result
            return ActionExecutionResult(
                execution_id=existing.execution_id,
                outcome=existing.outcome,
                action=proposal.action,
                proposal_id=proposal.proposal_id,
                decision_id=decision.result_id,
                error_code=(
                    getattr(prior, "error_code", None) or "IDEMPOTENT_REPLAY"
                ),
                error_message=(
                    "Idempotent replay of a prior attempt that did not execute; "
                    "nothing was written. Re-propose with a new idempotency key."
                ),
                backend_response={
                    "replayed": True,
                    "original_execution_id": existing.execution_id,
                    "original_outcome": existing.outcome.value,
                },
                trace_id=trace_id,
                physical_mutation_occurred=False,
                dispatch_status=DISPATCH_NOT_DISPATCHED,
            )

        # Prior attempt completed — return NO_OP pointing to original result.
        # outcome=NO_OP means "this logical execution already completed earlier"
        # (not "desired state pre-existed"); backend_response carries replay metadata
        # so callers can distinguish idempotent replay from a genuine no-mutation read.
        logger.info(
            "%s: idempotent replay — prior execution_id=%s completed with outcome=%s; "
            "suppressing duplicate physical mutation",
            type(self).__name__,
            existing.execution_id,
            existing.outcome.value,
        )
        prior_resp = existing.result.backend_response if existing.result else {}
        return ActionExecutionResult(
            execution_id=existing.execution_id,
            outcome=ExecutionOutcome.NO_OP,
            action=proposal.action,
            proposal_id=proposal.proposal_id,
            decision_id=decision.result_id,
            provider_reference=(
                existing.result.provider_reference if existing.result else None
            ),
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
        raise NotImplementedError(f"{type(self).__name__} must implement _do_execute()")
