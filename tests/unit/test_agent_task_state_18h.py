# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 18H — AgentTaskState lifecycle tests.

Tests:
    - Valid status transitions are allowed
    - Invalid status transitions are rejected
    - Terminal states cannot transition further
    - increment_iteration() enforces max_iterations
    - State is immutable (transition returns new object)
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone


def _make_state(status="PENDING", iteration=0, max_iter=10):
    from maiw_agents.contracts import AgentTaskState, AgentTaskStatus

    return AgentTaskState(
        task_id="task-test-001",
        agent_id="labor",
        sop_id="labor.labor_constraint_assessment",
        sop_version="1.0",
        objective="Test objective.",
        status=AgentTaskStatus(status),
        iteration=iteration,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class TestAgentTaskStatusTransitions:
    """Valid and invalid transitions from AgentTaskStatus."""

    def test_pending_to_running(self):
        from maiw_agents.contracts import AgentTaskStatus

        state = _make_state("PENDING")
        new_state = state.transition(AgentTaskStatus.RUNNING)
        assert new_state.status == AgentTaskStatus.RUNNING

    def test_running_to_waiting_for_governance(self):
        from maiw_agents.contracts import AgentTaskStatus

        state = _make_state("RUNNING")
        new_state = state.transition(AgentTaskStatus.WAITING_FOR_GOVERNANCE)
        assert new_state.status == AgentTaskStatus.WAITING_FOR_GOVERNANCE

    def test_running_to_completed(self):
        from maiw_agents.contracts import AgentTaskStatus

        state = _make_state("RUNNING")
        new_state = state.transition(AgentTaskStatus.COMPLETED)
        assert new_state.status == AgentTaskStatus.COMPLETED

    def test_running_to_failed(self):
        from maiw_agents.contracts import AgentTaskStatus

        state = _make_state("RUNNING")
        new_state = state.transition(AgentTaskStatus.FAILED)
        assert new_state.status == AgentTaskStatus.FAILED

    def test_running_to_escalated(self):
        from maiw_agents.contracts import AgentTaskStatus

        state = _make_state("RUNNING")
        new_state = state.transition(AgentTaskStatus.ESCALATED)
        assert new_state.status == AgentTaskStatus.ESCALATED

    def test_invalid_pending_to_completed(self):
        from maiw_agents.contracts import AgentTaskStatus

        state = _make_state("PENDING")
        with pytest.raises(ValueError):
            state.transition(AgentTaskStatus.COMPLETED)

    def test_invalid_pending_to_failed(self):
        """PENDING → FAILED is allowed (fast-fail path). Test PENDING → ESCALATED instead."""
        from maiw_agents.contracts import AgentTaskStatus

        state = _make_state("PENDING")
        # PENDING → ESCALATED is invalid (must go through RUNNING first)
        with pytest.raises(ValueError):
            state.transition(AgentTaskStatus.ESCALATED)

    def test_completed_is_terminal(self):
        from maiw_agents.contracts import AgentTaskStatus

        state = _make_state("COMPLETED")
        with pytest.raises(ValueError):
            state.transition(AgentTaskStatus.RUNNING)

    def test_failed_is_terminal(self):
        from maiw_agents.contracts import AgentTaskStatus

        state = _make_state("FAILED")
        with pytest.raises(ValueError):
            state.transition(AgentTaskStatus.RUNNING)

    def test_escalated_is_terminal(self):
        from maiw_agents.contracts import AgentTaskStatus

        state = _make_state("ESCALATED")
        with pytest.raises(ValueError):
            state.transition(AgentTaskStatus.RUNNING)


class TestAgentTaskStateImmutability:
    """transition() must return a new object — state is immutable."""

    def test_transition_returns_new_object(self):
        from maiw_agents.contracts import AgentTaskStatus

        state = _make_state("PENDING")
        new_state = state.transition(AgentTaskStatus.RUNNING)
        assert new_state is not state
        assert state.status.value == "PENDING"
        assert new_state.status.value == "RUNNING"


class TestIncrementIteration:
    """increment_iteration() must advance and report limit_reached."""

    def test_increments(self):
        state = _make_state(iteration=3)
        new_state, limit_reached = state.increment_iteration(max_iterations=10)
        assert new_state.iteration == 4
        assert limit_reached is False

    def test_does_not_mutate_original(self):
        state = _make_state(iteration=0)
        _, _ = state.increment_iteration(max_iterations=10)
        assert state.iteration == 0

    def test_at_limit_signals_limit_reached(self):
        """At max_iterations, returns limit_reached=True (no raise — caller escalates)."""
        state = _make_state(iteration=10)
        _, limit_reached = state.increment_iteration(max_iterations=10)
        assert limit_reached is True


class TestTerminalStatusHelper:
    """is_terminal() must return True only for terminal states."""

    @pytest.mark.parametrize("status", ["COMPLETED", "ESCALATED", "FAILED"])
    def test_terminal_statuses(self, status):
        from maiw_agents.contracts.task import is_terminal, AgentTaskStatus

        assert is_terminal(AgentTaskStatus(status)) is True

    @pytest.mark.parametrize(
        "status", ["PENDING", "RUNNING", "WAITING_FOR_GOVERNANCE", "WAITING_FOR_INPUT"]
    )
    def test_non_terminal_statuses(self, status):
        from maiw_agents.contracts.task import is_terminal, AgentTaskStatus

        assert is_terminal(AgentTaskStatus(status)) is False
