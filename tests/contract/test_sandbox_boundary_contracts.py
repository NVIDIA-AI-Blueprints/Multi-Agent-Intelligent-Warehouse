# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
The two messages that cross the sandbox boundary, validated from the host side.

Every test here assumes the sandbox is lying. That is not pessimism about
NemoClaw — it is the only assumption under which these validators are worth
having. If the sandbox were trusted, the boundary would not need checking and
this module would be ceremony.

What is being protected, concretely: a compromised sandbox must not be able to
make the host act on a recommendation bound to a different procedure, a stale
world, or a procedure that already finished; and a replayed governance outcome
must not be able to re-drive a procedure past a write that already happened.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from maiw_agents.assessment import RecommendedAction
from maiw_agents.contracts.delegation import GovernanceOutcome
from maiw_agents.contracts.procedure_state import (
    ProcedureExecutionState,
    ProcedureStatus,
)

from integrations.nemoclaw import (
    GovernanceInbox,
    SandboxBoundaryViolation,
    SandboxGovernanceInput,
    SandboxRecommendedActionOutput,
    validate_governance_input,
    validate_sandbox_output,
)

PROC_ID = "proc-1111"
TASK_ID = "task-2222"
TRACE_ID = "trace-3333"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _proc_state(
    *,
    status: ProcedureStatus = ProcedureStatus.RUNNING,
    revision: int = 3,
    procedure_execution_id: str = PROC_ID,
    agent_task_id: str = TASK_ID,
) -> ProcedureExecutionState:
    return ProcedureExecutionState(
        procedure_execution_id=procedure_execution_id,
        sop_id="operations_coordination.wave_risk_resolution_v2",
        sop_version="2.0",
        agent_task_id=agent_task_id,
        trace_id=TRACE_ID,
        status=status,
        revision=revision,
        started_at=_now(),
        last_updated_at=_now(),
    )


def _recommended_action() -> RecommendedAction:
    return RecommendedAction(
        domain="wave",
        capability="warehouse.wave.reprioritize",
        target="wave-17",
        objective="Reprioritise wave 17 ahead of carrier cutoff",
        rationale="3 tasks at risk, 47 minutes to cutoff, labor is the constraint",
        priority="high",
    )


def _output(**overrides) -> SandboxRecommendedActionOutput:
    base = dict(
        procedure_execution_id=PROC_ID,
        agent_task_id=TASK_ID,
        trace_id=TRACE_ID,
        recommended_action=_recommended_action(),
        procedure_state_revision=3,
    )
    base.update(overrides)
    return SandboxRecommendedActionOutput(**base)


def _governance_input(**overrides) -> SandboxGovernanceInput:
    base = dict(
        procedure_execution_id=PROC_ID,
        agent_task_id=TASK_ID,
        governance_outcome=GovernanceOutcome(
            proposal_id="proposal-9999",
            decision_outcome="APPROVED",
            execution_id="exec-4444",
            execution_status="EXECUTED",
            trace_id=TRACE_ID,
        ),
        expected_procedure_revision=3,
    )
    base.update(overrides)
    return SandboxGovernanceInput(**base)


# ── sandbox → host ────────────────────────────────────────────────────────────

class TestRecommendedActionEgress:
    def test_well_formed_output_is_accepted_and_unwrapped(self):
        action = validate_sandbox_output(_output(), procedure_state=_proc_state())
        assert isinstance(action, RecommendedAction)
        assert action.capability == "warehouse.wave.reprioritize"

    def test_mismatched_procedure_is_rejected(self):
        with pytest.raises(SandboxBoundaryViolation, match="procedure_execution_id"):
            validate_sandbox_output(
                _output(procedure_execution_id="proc-other"),
                procedure_state=_proc_state(),
            )

    def test_mismatched_task_is_rejected(self):
        with pytest.raises(SandboxBoundaryViolation, match="agent_task_id"):
            validate_sandbox_output(
                _output(agent_task_id="task-other"), procedure_state=_proc_state()
            )

    def test_stale_revision_is_rejected(self):
        """A recommendation computed against a world that has already moved."""
        with pytest.raises(SandboxBoundaryViolation, match="stale"):
            validate_sandbox_output(
                _output(procedure_state_revision=2), procedure_state=_proc_state(revision=3)
            )

    def test_future_revision_is_rejected(self):
        """The sandbox cannot know a revision the host has not written yet."""
        with pytest.raises(SandboxBoundaryViolation, match="revision"):
            validate_sandbox_output(
                _output(procedure_state_revision=9), procedure_state=_proc_state(revision=3)
            )

    @pytest.mark.parametrize(
        "status",
        [ProcedureStatus.COMPLETED, ProcedureStatus.ESCALATED, ProcedureStatus.FAILED],
    )
    def test_terminal_procedure_accepts_nothing(self, status):
        with pytest.raises(SandboxBoundaryViolation, match="terminal"):
            validate_sandbox_output(
                _output(), procedure_state=_proc_state(status=status)
            )

    def test_output_is_frozen(self):
        from pydantic import ValidationError

        output = _output()
        with pytest.raises(ValidationError):
            output.procedure_execution_id = "proc-other"

    def test_recommended_action_carries_no_mcp_parameters(self):
        """
        The egress contract cannot smuggle call parameters out of the sandbox.

        ``RecommendedAction`` is semantic by construction — domain, capability,
        target, objective, rationale, priority, subtype. There is no ``params``
        field for a compromised sandbox to populate, which is why governance can
        safely treat it as a suggestion rather than an instruction.
        """
        fields = set(RecommendedAction.model_fields)
        assert fields == {
            "domain", "capability", "target", "objective",
            "rationale", "priority", "subtype",
        }
        for forbidden in ("params", "parameters", "mcp_tool", "payload", "sql"):
            assert forbidden not in fields


# ── host → sandbox ────────────────────────────────────────────────────────────

class TestGovernanceIngress:
    def test_well_formed_outcome_is_accepted(self):
        outcome = validate_governance_input(
            _governance_input(),
            procedure_state=_proc_state(status=ProcedureStatus.WAITING_FOR_GOVERNANCE),
        )
        assert isinstance(outcome, GovernanceOutcome)
        assert outcome.decision_outcome == "APPROVED"

    def test_mismatched_procedure_is_rejected(self):
        with pytest.raises(SandboxBoundaryViolation, match="procedure_execution_id"):
            validate_governance_input(
                _governance_input(procedure_execution_id="proc-other"),
                procedure_state=_proc_state(
                    status=ProcedureStatus.WAITING_FOR_GOVERNANCE
                ),
            )

    def test_mismatched_task_is_rejected(self):
        with pytest.raises(SandboxBoundaryViolation, match="agent_task_id"):
            validate_governance_input(
                _governance_input(agent_task_id="task-other"),
                procedure_state=_proc_state(
                    status=ProcedureStatus.WAITING_FOR_GOVERNANCE
                ),
            )

    def test_revision_mismatch_is_rejected(self):
        with pytest.raises(SandboxBoundaryViolation, match="revision"):
            validate_governance_input(
                _governance_input(expected_procedure_revision=1),
                procedure_state=_proc_state(
                    status=ProcedureStatus.WAITING_FOR_GOVERNANCE, revision=3
                ),
            )

    @pytest.mark.parametrize(
        "status",
        [
            ProcedureStatus.RUNNING,
            ProcedureStatus.COMPLETED,
            ProcedureStatus.ESCALATED,
            ProcedureStatus.FAILED,
        ],
    )
    def test_procedure_not_waiting_rejects_the_outcome(self, status):
        """
        A governance outcome has nothing to resume unless the procedure paused
        for one. Accepting it against a RUNNING procedure would let a replayed
        message advance a procedure mid-step.
        """
        with pytest.raises(SandboxBoundaryViolation, match="waiting_for_governance"):
            validate_governance_input(
                _governance_input(), procedure_state=_proc_state(status=status)
            )


class TestGovernanceIdempotency:
    def test_first_delivery_is_accepted(self):
        inbox = GovernanceInbox()
        assert inbox.accept(_governance_input()) is True

    def test_duplicate_delivery_is_dropped(self):
        """
        The dangerous restart delivers a message twice, not zero times.

        An APPROVED outcome applied twice would re-run the post-governance steps
        against a world that already moved — the duplicate-write shape.
        """
        inbox = GovernanceInbox()
        first = _governance_input()
        assert inbox.accept(first) is True
        assert inbox.accept(_governance_input()) is False
        assert inbox.has_seen(first) is True

    def test_retransmission_with_a_new_timestamp_still_collides(self):
        """Keyed on the proposal, not on the message envelope."""
        inbox = GovernanceInbox()
        assert inbox.accept(_governance_input(timestamp=_now())) is True
        assert inbox.accept(_governance_input(timestamp=_now())) is False

    def test_a_different_proposal_is_not_a_duplicate(self):
        inbox = GovernanceInbox()
        assert inbox.accept(_governance_input()) is True
        other = _governance_input(
            governance_outcome=GovernanceOutcome(
                proposal_id="proposal-0001", decision_outcome="APPROVED"
            )
        )
        assert inbox.accept(other) is True

    def test_validate_drops_duplicates_through_the_inbox(self):
        inbox = GovernanceInbox()
        state = _proc_state(status=ProcedureStatus.WAITING_FOR_GOVERNANCE)
        validate_governance_input(_governance_input(), procedure_state=state, inbox=inbox)
        assert inbox.accept(_governance_input()) is False

    def test_mismatch_is_rejected_before_the_inbox_records_it(self):
        """
        A rejected message must not consume its own idempotency key.

        Otherwise an attacker could burn the key for a legitimate outcome by
        sending a malformed copy of it first, and the real one would be silently
        dropped as a duplicate.
        """
        inbox = GovernanceInbox()
        bad = _governance_input(agent_task_id="task-other")
        with pytest.raises(SandboxBoundaryViolation):
            validate_governance_input(
                bad,
                procedure_state=_proc_state(
                    status=ProcedureStatus.WAITING_FOR_GOVERNANCE
                ),
                inbox=inbox,
            )
        good = _governance_input()
        assert inbox.accept(good) is True
