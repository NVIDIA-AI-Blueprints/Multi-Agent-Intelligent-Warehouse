# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
DecisionAuditRecord — structured log entry per engine evaluation.

Every evaluation produces one audit record.  Records are intended to be
emitted to a structured log sink (stdout JSON, OpenTelemetry, etc.) and
are NOT persisted by the engine itself.

Callers receive the record alongside the ``DecisionResult`` and may
ship it to their audit trail.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .models import DecisionOutcome, DecisionResult


class DecisionAuditRecord(BaseModel):
    """
    Immutable audit record for one DecisionEngine evaluation.

    Fields
    ------
    result_id:
        Matches ``DecisionResult.result_id`` for cross-reference.
    proposal_id:
        Matches ``ActionProposal.proposal_id``.
    snapshot_id:
        Matches ``WarehouseStateSnapshot.snapshot_id``; the exact state
        version that was evaluated.
    action:
        The action string from the proposal.
    domain:
        The domain string from the proposal.
    risk_level:
        The risk level string from the proposal.
    outcome:
        The evaluation outcome.
    violation_count:
        Number of constraint violations found.
    violation_rules:
        Machine-readable rule identifiers for violated rules.
    engine_version:
        Engine version at time of evaluation.
    evaluated_at:
        UTC timestamp of evaluation.
    trace_id:
        Propagated from the ``DecisionRequest`` for distributed tracing.
    """

    result_id: str
    proposal_id: str
    snapshot_id: str
    action: str
    domain: str
    risk_level: str
    outcome: DecisionOutcome
    violation_count: int = 0
    violation_rules: list[str] = Field(default_factory=list)
    engine_version: str
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    trace_id: str | None = None

    @classmethod
    def from_result(
        cls,
        result: DecisionResult,
        *,
        snapshot_id: str,
        action: str,
        domain: str,
        risk_level: str,
        trace_id: str | None = None,
    ) -> DecisionAuditRecord:
        """Construct an audit record from a DecisionResult."""
        return cls(
            result_id=result.result_id,
            proposal_id=result.proposal_id,
            snapshot_id=snapshot_id,
            action=action,
            domain=domain,
            risk_level=risk_level,
            outcome=result.outcome,
            violation_count=len(result.violations),
            violation_rules=[v.rule for v in result.violations],
            engine_version=result.engine_version,
            evaluated_at=result.evaluated_at,
            trace_id=trace_id,
        )

    def to_log_dict(self) -> dict:
        """Serialize to a flat dict suitable for structured logging."""
        return {
            "event": "decision_engine.evaluation",
            "result_id": self.result_id,
            "proposal_id": self.proposal_id,
            "snapshot_id": self.snapshot_id,
            "action": self.action,
            "domain": self.domain,
            "risk_level": self.risk_level,
            "outcome": self.outcome.value,
            "violation_count": self.violation_count,
            "violation_rules": self.violation_rules,
            "engine_version": self.engine_version,
            "evaluated_at": self.evaluated_at.isoformat(),
            "trace_id": self.trace_id,
        }
