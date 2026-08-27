# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
DecisionEngine — deterministic rule evaluation for ActionProposals.

Rules (evaluated in order, first match wins)
--------------------------------------------
1. READ_ONLY risk → APPROVED immediately (read actions bypass the engine).
2. Required state component absent or stale → REQUIRES_FRESH_STATE.
3. equipment domain + asset_id provided but not found in snapshot → REJECTED.
4. LOW risk + requires_approval=False → APPROVED.
5. requires_approval=True (any risk) → REQUIRES_HUMAN_APPROVAL.
6. MEDIUM / HIGH / CRITICAL risk → REQUIRES_HUMAN_APPROVAL.
7. Fallback → APPROVED (LOW risk, requires_approval=False, all checks passed).

The engine is deliberately small.  It never executes actions, never writes
to any external system, and has no async I/O.  All evaluation is pure
in-memory rule processing.
"""

from __future__ import annotations

from maiw_mcp.contracts.actions import RiskLevel
from maiw_state.errors import StateFreshnessError

from .audit import DecisionAuditRecord
from .models import (
    ApprovalState,
    ConstraintViolation,
    DecisionOutcome,
    DecisionRequest,
    DecisionResult,
)

_ENGINE_VERSION = "1.0.0"


class DecisionEngine:
    """
    Evaluate an ActionProposal against a WarehouseStateSnapshot.

    Usage
    -----
        engine = DecisionEngine()
        result, audit = engine.evaluate(request)

    Returns
    -------
    (DecisionResult, DecisionAuditRecord)
        Both are returned together so callers can ship the audit record
        without a second method call.
    """

    @property
    def version(self) -> str:
        return _ENGINE_VERSION

    def evaluate(
        self, request: DecisionRequest
    ) -> tuple[DecisionResult, DecisionAuditRecord]:
        """
        Evaluate *request* and return (result, audit_record).

        This method is synchronous — all rules are in-memory checks.
        """
        proposal = request.proposal
        snapshot = request.state
        violations: list[ConstraintViolation] = []

        # Rule 1: READ_ONLY bypasses all further checks
        if proposal.risk_level == RiskLevel.READ_ONLY:
            return self._build(
                request=request,
                outcome=DecisionOutcome.APPROVED,
                violations=[],
            )

        # Rule 2: Equipment domain — check state freshness when asset_id given
        if proposal.domain == "equipment":
            outcome = self._check_equipment_freshness(request, violations)
            if outcome is not None:
                return self._build(
                    request=request, outcome=outcome, violations=violations
                )

            # Rule 3: asset_id given but not found in snapshot
            asset_id = proposal.parameters.get("asset_id")
            if asset_id and snapshot.state.equipment is not None:
                found = snapshot.state.equipment.find_asset(asset_id)
                if found is None:
                    violations.append(
                        ConstraintViolation(
                            rule="equipment.asset_not_found",
                            message=f"Asset '{asset_id}' not found in state snapshot",
                            details={
                                "asset_id": asset_id,
                                "snapshot_id": snapshot.snapshot_id,
                            },
                        )
                    )
                    return self._build(
                        request=request,
                        outcome=DecisionOutcome.REJECTED,
                        violations=violations,
                    )

        # Rule 4: LOW risk + no approval required → APPROVED
        if proposal.risk_level == RiskLevel.LOW and not proposal.requires_approval:
            return self._build(
                request=request,
                outcome=DecisionOutcome.APPROVED,
                violations=[],
            )

        # Rule 5+6: requires_approval=True or MEDIUM/HIGH/CRITICAL → human approval
        if proposal.requires_approval or proposal.risk_level in (
            RiskLevel.MEDIUM,
            RiskLevel.HIGH,
            RiskLevel.CRITICAL,
        ):
            violations.append(
                ConstraintViolation(
                    rule="approval.required",
                    message=(
                        f"risk_level={proposal.risk_level.value} with "
                        f"requires_approval={proposal.requires_approval} "
                        "requires human approval"
                    ),
                    details={
                        "risk_level": proposal.risk_level.value,
                        "requires_approval": proposal.requires_approval,
                    },
                )
            )
            return self._build(
                request=request,
                outcome=DecisionOutcome.REQUIRES_HUMAN_APPROVAL,
                violations=violations,
            )

        # Rule 7: Fallback — all checks passed
        return self._build(
            request=request,
            outcome=DecisionOutcome.APPROVED,
            violations=[],
        )

    def authorize_with_approval(
        self,
        request: DecisionRequest,
        approval: "ApprovalRecord",
        *,
        expected_decision_id: str | None = None,
    ) -> tuple[DecisionResult, DecisionAuditRecord]:
        """
        Re-evaluate a REQUIRES_HUMAN_APPROVAL proposal that now has approval evidence.

        Approval grants authority for the human-approval gate only. Hard
        constraints (REQUIRES_FRESH_STATE, REJECTED) still apply and cannot
        be overridden by approval evidence.

        Checks (in order):
        0. Approval has not been consumed (CONSUMED → already used).
        1. ApprovalRecord binds to the correct proposal_id.
        1b. If expected_decision_id provided: decision_id binding check.
        1c. If both warehouse_ids set: warehouse binding check.
        2. Approval has not expired.
        3. Approval is not a rejection (state == APPROVED).
        4. Hard constraints still pass (equipment freshness, asset presence).
        5. If all pass: return APPROVED.
        """
        proposal = request.proposal
        snapshot = request.state
        violations: list[ConstraintViolation] = []

        # Check 0: single-use — CONSUMED approval must never re-authorize
        if approval.state == ApprovalState.CONSUMED:
            violations.append(
                ConstraintViolation(
                    rule="approval.already_consumed",
                    message=f"ApprovalRecord approval_id={approval.approval_id!r} has already been consumed",
                    details={
                        "approval_id": approval.approval_id,
                        "state": approval.state.value,
                    },
                )
            )
            return self._build(
                request=request, outcome=DecisionOutcome.REJECTED, violations=violations
            )

        # Check 1: proposal_id binding
        if approval.proposal_id != proposal.proposal_id:
            violations.append(
                ConstraintViolation(
                    rule="approval.proposal_mismatch",
                    message=(
                        f"ApprovalRecord.proposal_id={approval.proposal_id!r} "
                        f"does not match proposal.proposal_id={proposal.proposal_id!r}"
                    ),
                    details={
                        "approval_proposal_id": approval.proposal_id,
                        "proposal_id": proposal.proposal_id,
                    },
                )
            )
            return self._build(
                request=request, outcome=DecisionOutcome.REJECTED, violations=violations
            )

        # Check 1b: decision_id binding (when caller supplies expected value)
        if (
            expected_decision_id is not None
            and approval.decision_id != expected_decision_id
        ):
            violations.append(
                ConstraintViolation(
                    rule="approval.decision_mismatch",
                    message=(
                        f"ApprovalRecord.decision_id={approval.decision_id!r} "
                        f"does not match expected_decision_id={expected_decision_id!r}"
                    ),
                    details={
                        "approval_decision_id": approval.decision_id,
                        "expected_decision_id": expected_decision_id,
                    },
                )
            )
            return self._build(
                request=request, outcome=DecisionOutcome.REJECTED, violations=violations
            )

        # Check 1c: warehouse_id binding (confused deputy prevention)
        if approval.warehouse_id is not None:
            proposal_wh = proposal.parameters.get("warehouse_id")
            if proposal_wh is not None and approval.warehouse_id != proposal_wh:
                violations.append(
                    ConstraintViolation(
                        rule="approval.warehouse_mismatch",
                        message=(
                            f"ApprovalRecord.warehouse_id={approval.warehouse_id!r} "
                            f"does not match proposal warehouse_id={proposal_wh!r}"
                        ),
                        details={
                            "approval_warehouse_id": approval.warehouse_id,
                            "proposal_warehouse_id": proposal_wh,
                        },
                    )
                )
                return self._build(
                    request=request,
                    outcome=DecisionOutcome.REJECTED,
                    violations=violations,
                )

        # Check 2: expiry
        if approval.is_expired():
            violations.append(
                ConstraintViolation(
                    rule="approval.expired",
                    message=f"ApprovalRecord expired at {approval.expires_at}",
                    details={"expires_at": str(approval.expires_at)},
                )
            )
            return self._build(
                request=request, outcome=DecisionOutcome.REJECTED, violations=violations
            )

        # Check 3: rejection or non-APPROVED state
        if not approval.approved:
            violations.append(
                ConstraintViolation(
                    rule="approval.not_approved",
                    message=(
                        f"ApprovalRecord is not in APPROVED state "
                        f"(state={approval.state.value!r}, approved_by={approval.approved_by!r})"
                    ),
                    details={
                        "state": approval.state.value,
                        "approved_by": approval.approved_by,
                    },
                )
            )
            return self._build(
                request=request, outcome=DecisionOutcome.REJECTED, violations=violations
            )

        # Check 4: hard constraints still apply
        if proposal.domain == "equipment":
            outcome = self._check_equipment_freshness(request, violations)
            if outcome is not None:
                return self._build(
                    request=request, outcome=outcome, violations=violations
                )

            asset_id = proposal.parameters.get("asset_id")
            if asset_id and snapshot.state.equipment is not None:
                found = snapshot.state.equipment.find_asset(asset_id)
                if found is None:
                    violations.append(
                        ConstraintViolation(
                            rule="equipment.asset_not_found",
                            message=f"Asset '{asset_id}' not found in state snapshot",
                            details={
                                "asset_id": asset_id,
                                "snapshot_id": snapshot.snapshot_id,
                            },
                        )
                    )
                    return self._build(
                        request=request,
                        outcome=DecisionOutcome.REJECTED,
                        violations=violations,
                    )

        # All checks passed — approval grants authority
        return self._build(
            request=request, outcome=DecisionOutcome.APPROVED, violations=[]
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _check_equipment_freshness(
        self,
        request: DecisionRequest,
        violations: list[ConstraintViolation],
    ) -> DecisionOutcome | None:
        """
        Return REQUIRES_FRESH_STATE if equipment state is absent or stale.

        Returns None if state is acceptable.
        """
        snapshot = request.state
        asset_id = request.proposal.parameters.get("asset_id")

        if asset_id is None:
            # No specific asset required — no freshness check needed
            return None

        if snapshot.state.equipment is None:
            violations.append(
                ConstraintViolation(
                    rule="state.equipment_absent",
                    message="Equipment state is absent in the snapshot",
                    details={"snapshot_id": snapshot.snapshot_id},
                )
            )
            return DecisionOutcome.REQUIRES_FRESH_STATE

        if snapshot.is_equipment_stale():
            age_ms = snapshot.equipment_age_ms() or 0
            stale_after_ms = snapshot.state.equipment.freshness.stale_after_ms
            violations.append(
                ConstraintViolation(
                    rule="state.equipment_stale",
                    message=(
                        f"Equipment state is stale: age_ms={age_ms} "
                        f"exceeds stale_after_ms={stale_after_ms}"
                    ),
                    details={
                        "age_ms": age_ms,
                        "stale_after_ms": stale_after_ms,
                        "snapshot_id": snapshot.snapshot_id,
                    },
                )
            )
            return DecisionOutcome.REQUIRES_FRESH_STATE

        return None

    def _build(
        self,
        *,
        request: DecisionRequest,
        outcome: DecisionOutcome,
        violations: list[ConstraintViolation],
    ) -> tuple[DecisionResult, DecisionAuditRecord]:
        result = DecisionResult(
            request_id=request.request_id,
            proposal_id=request.proposal.proposal_id,
            outcome=outcome,
            violations=violations,
            engine_version=_ENGINE_VERSION,
        )
        audit = DecisionAuditRecord.from_result(
            result,
            snapshot_id=request.state.snapshot_id,
            action=request.proposal.action,
            domain=request.proposal.domain,
            risk_level=request.proposal.risk_level.value,
            trace_id=request.trace_id,
        )
        return result, audit
