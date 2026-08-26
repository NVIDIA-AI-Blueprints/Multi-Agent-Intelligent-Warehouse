# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 10E Batch 3 — UNKNOWN resolution via state-based reconciliation.

ReconciliationOutcome answers:
    "What did MAIW subsequently establish about that uncertain write?"

ExecutionOutcome answers:
    "What did the write attempt itself report?"

These are distinct and both are preserved. ExecutionOutcome.UNKNOWN is NEVER
rewritten to EXECUTED after reconciliation — the original write history is immutable.
ReconciliationRecord is stored alongside the original ExecutionRecord.

Identity binding: reconciliation operates on the original execution_id, proposal_id,
decision_id, and approval_id. It resolves uncertainty about an EXISTING execution.
No new proposal, decision, or approval is created.

Architecture invariant: ReconciliationStrategy.read_current_state() must read
authoritative state through canonical MCP read skills. DemoWarehouseWorld and
provider internals must never be consulted directly.

SINGLE-PROCESS SAFETY: ReconciliationService is stateless. All persistence is
in ExecutionRegistry which is already labeled single-process.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


class ReconciliationOutcome(str, Enum):
    """
    Result of a reconciliation attempt against authoritative warehouse state.

    CONFIRMED_EXECUTED     — Authoritative state shows the intended mutation
                             occurred. Effective operational status is
                             "effectively_executed".
    CONFIRMED_NOT_EXECUTED — Authoritative state shows the mutation did not
                             occur. Safe for higher-level re-evaluation.
                             Do NOT auto-retry in Batch 3.
    INDETERMINATE          — Cannot determine from current state alone.
                             Manual operator reconciliation required.
                             Effective status remains "unknown".
    """

    CONFIRMED_EXECUTED = "confirmed_executed"
    CONFIRMED_NOT_EXECUTED = "confirmed_not_executed"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True)
class ExecutionIntent:
    """
    Compact immutable snapshot of execution intent, recorded at begin() time.

    Captured from ActionProposal before the write so reconciliation never
    depends on the mutable original proposal object. Contains everything
    needed to: (a) identify the write attempted, (b) read authoritative state
    to confirm it, (c) compare against the expected postcondition.

    Fields
    ------
    capability      : The MCP action name (e.g. "warehouse.labor.allocate")
    proposal_id     : Echoes ActionProposal.proposal_id — full audit chain
    decision_id     : Echoes DecisionResult.result_id
    warehouse_id    : Scoping identifier for confused-deputy prevention
    target          : Primary entity being mutated (asset_id / task_id / zone)
    expected_effect : Capability-specific postcondition map; set by _build_intent()
    approval_id     : ApprovalRecord identity (when present)
    idempotency_key : Caller-supplied deduplication key (when present)
    trace_id        : Lifecycle correlation identifier
    """

    capability: str
    proposal_id: str
    decision_id: str
    warehouse_id: str | None = None
    target: str | None = None
    expected_effect: dict = field(default_factory=dict)
    approval_id: str | None = None
    idempotency_key: str | None = None
    trace_id: str | None = None


@dataclass
class ReconciliationRecord:
    """
    Result of one reconciliation attempt.

    Stored in ExecutionRecord.reconciliation alongside the original
    ExecutionOutcome.UNKNOWN — the original is never mutated.

    Fields
    ------
    reconciliation_id : Unique ID for this reconciliation event
    outcome           : ReconciliationOutcome
    reconciled_at     : UTC timestamp
    evidence          : Raw state dict read from authoritative source (for audit)
    trace_id          : Propagated from the reconcile() call
    error             : Set when read or check failed; outcome is then INDETERMINATE
    """

    reconciliation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    outcome: ReconciliationOutcome = ReconciliationOutcome.INDETERMINATE
    reconciled_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    evidence: dict = field(default_factory=dict)
    trace_id: str | None = None
    error: str | None = None


@runtime_checkable
class ReconciliationStrategy(Protocol):
    """
    Pluggable read + compare interface for a specific warehouse capability.

    Implementations MUST:
    - Read authoritative state through canonical MCP read skills.
    - Never access DemoWarehouseWorld or provider internals directly.
    - Return INDETERMINATE (not raise) when comparison is inconclusive.

    This protocol allows the same ReconciliationService to work against any
    provider (simulation, SAP EWM, Manhattan, etc.) by swapping the strategy.
    """

    async def read_current_state(self, intent: ExecutionIntent) -> dict:
        """
        Read the authoritative current state relevant to intent.

        Must call a canonical MCP read skill. Must not access simulation
        internals. May raise on network/provider failure (service catches it).
        """
        ...

    def check_postcondition(
        self,
        intent: ExecutionIntent,
        current_state: dict,
    ) -> ReconciliationOutcome:
        """
        Compare current_state against intent.expected_effect.

        Must not raise. Return INDETERMINATE if inconclusive.
        """
        ...


class ReconciliationService:
    """
    Resolve UNKNOWN executions through authoritative state comparison.

    Usage
    -----
        service = ReconciliationService()
        record = await service.reconcile(exec_record, strategy=strategy, trace_id=t)
        registry.set_reconciliation(execution_id, record)

    History preservation
    --------------------
    ExecutionOutcome.UNKNOWN is never mutated. The ReconciliationRecord is stored
    alongside the original outcome in ExecutionRecord.reconciliation. Use
    ExecutionRecord.effective_status to get the derived operational view.

    No automatic retry
    ------------------
    CONFIRMED_NOT_EXECUTED means the mutation is known absent and is safe for
    higher-level re-evaluation. ReconciliationService does not create a new
    proposal, decision, or approval.
    """

    async def reconcile(
        self,
        execution_record: Any,  # ExecutionRecord — kept as Any to avoid circular
        *,
        strategy: ReconciliationStrategy,
        trace_id: str | None = None,
    ) -> ReconciliationRecord:
        """
        Reconcile an UNKNOWN execution against authoritative state.

        Parameters
        ----------
        execution_record : ExecutionRecord
            Must have outcome == UNKNOWN. Raises ValueError if not.
        strategy : ReconciliationStrategy
            Reads authoritative state and checks the postcondition.
            Must not access simulation internals.
        trace_id : str | None
            Propagated to log events and the returned ReconciliationRecord.

        Returns
        -------
        ReconciliationRecord
            Caller stores it via registry.set_reconciliation(execution_id, record).
        """
        from .outcome import ExecutionOutcome  # local to avoid circular

        execution_id = execution_record.execution_id
        intent: ExecutionIntent | None = execution_record.intent

        if execution_record.outcome != ExecutionOutcome.UNKNOWN:
            raise ValueError(
                f"Cannot reconcile execution_id={execution_id!r}: "
                f"outcome is {execution_record.outcome!r}, expected UNKNOWN"
            )

        logger.info(
            "reconciliation.started: execution_id=%s capability=%s "
            "proposal_id=%s decision_id=%s approval_id=%s trace_id=%s",
            execution_id,
            intent.capability if intent else "unknown",
            intent.proposal_id if intent else "unknown",
            intent.decision_id if intent else "unknown",
            intent.approval_id if intent else "unknown",
            trace_id,
        )

        if intent is None:
            logger.warning(
                "reconciliation.indeterminate: execution_id=%s — no ExecutionIntent "
                "recorded; operator reconciliation required. trace_id=%s",
                execution_id,
                trace_id,
            )
            return ReconciliationRecord(
                outcome=ReconciliationOutcome.INDETERMINATE,
                evidence={"reason": "no_intent_snapshot"},
                trace_id=trace_id,
                error="ExecutionRecord has no intent snapshot; reconciliation cannot proceed",
            )

        # Read authoritative state through canonical read path
        try:
            current_state = await strategy.read_current_state(intent)
        except Exception as exc:
            logger.error(
                "reconciliation.indeterminate: execution_id=%s — state read failed: %s "
                "trace_id=%s",
                execution_id,
                exc,
                trace_id,
            )
            return ReconciliationRecord(
                outcome=ReconciliationOutcome.INDETERMINATE,
                evidence={"reason": "read_failed", "error": str(exc)},
                trace_id=trace_id,
                error=str(exc),
            )

        # Compare current state against expected postcondition
        try:
            outcome = strategy.check_postcondition(intent, current_state)
        except Exception as exc:
            logger.error(
                "reconciliation.indeterminate: execution_id=%s — postcondition check "
                "raised: %s trace_id=%s",
                execution_id,
                exc,
                trace_id,
            )
            return ReconciliationRecord(
                outcome=ReconciliationOutcome.INDETERMINATE,
                evidence={"reason": "check_failed", "partial_state": current_state, "error": str(exc)},
                trace_id=trace_id,
                error=str(exc),
            )

        logger.info(
            "reconciliation.%s: execution_id=%s capability=%s "
            "proposal_id=%s decision_id=%s approval_id=%s trace_id=%s",
            outcome.value,
            execution_id,
            intent.capability,
            intent.proposal_id,
            intent.decision_id,
            intent.approval_id,
            trace_id,
        )

        return ReconciliationRecord(
            outcome=outcome,
            evidence=current_state,
            trace_id=trace_id,
        )
