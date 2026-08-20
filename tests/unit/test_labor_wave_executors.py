# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for LaborActionExecutor and WaveActionExecutor.

Mirrors the pattern from test_action_executor.py.
All tests use asyncio.run() — no pytest-asyncio required.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from maiw_decision.models import DecisionOutcome, DecisionResult
from maiw_mcp.contracts.actions import ActionProposal, RiskLevel
from src.api.agents.inventory.action_executor import (
    ActionDecisionMismatch,
    ActionExecutionResult,
    ActionExpired,
    ActionNotApproved,
    ActionUnsupported,
)
from src.api.agents.operations.labor_executor import LaborActionExecutor
from src.api.agents.operations.wave_executor import WaveActionExecutor

# ── Helpers ────────────────────────────────────────────────────────────────────


def _approved(proposal_id: str, age_seconds: float = 0.0) -> DecisionResult:
    evaluated_at = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    return DecisionResult(
        request_id="req-test",
        proposal_id=proposal_id,
        outcome=DecisionOutcome.APPROVED,
        evaluated_at=evaluated_at,
    )


def _rejected(proposal_id: str) -> DecisionResult:
    return DecisionResult(
        request_id="req-test",
        proposal_id=proposal_id,
        outcome=DecisionOutcome.REQUIRES_HUMAN_APPROVAL,
    )


def _labor_proposal(**kwargs) -> ActionProposal:
    defaults = dict(
        task_id="task-001",
        task_type="PICK",
        worker_ids=["w-001"],
        zone="A1",
        warehouse_id="WH-001",
    )
    defaults.update(kwargs)
    return ActionProposal.for_labor_allocate(**defaults)


def _wave_proposal(**kwargs) -> ActionProposal:
    defaults = dict(
        new_priority="high",
        zone="A1",
        warehouse_id="WH-001",
    )
    defaults.update(kwargs)
    return ActionProposal.for_wave_reprioritize(**defaults)


def _mock_allocate_skill(success=True):
    result = MagicMock()
    result.model_dump.return_value = {
        "success": success,
        "task_id": "task-001",
        "worker_ids": ["w-001"],
        "allocation_id": "alloc-001",
        "proposal_id": "p-1",
        "decision_id": "d-1",
    }
    skill = MagicMock()
    skill.execute = AsyncMock(return_value=result)
    return skill


def _mock_reprioritize_skill(success=True):
    result = MagicMock()
    result.model_dump.return_value = {
        "success": success,
        "new_priority": "high",
        "tasks_updated": 2,
        "proposal_id": "p-1",
        "decision_id": "d-1",
    }
    skill = MagicMock()
    skill.execute = AsyncMock(return_value=result)
    return skill


# ── LaborActionExecutor ────────────────────────────────────────────────────────


class TestLaborActionExecutorApprovedPath:
    def test_approved_path_calls_allocate_skill(self):
        skill = _mock_allocate_skill()
        executor = LaborActionExecutor(allocate_skill=skill)
        proposal = _labor_proposal()
        decision = _approved(proposal.proposal_id)

        result = asyncio.run(executor.execute(proposal, decision))

        skill.execute.assert_called_once()
        assert isinstance(result, ActionExecutionResult)
        assert result.executed is True
        assert result.success is True

    def test_approved_path_result_fields(self):
        skill = _mock_allocate_skill()
        executor = LaborActionExecutor(allocate_skill=skill)
        proposal = _labor_proposal()
        decision = _approved(proposal.proposal_id)

        result = asyncio.run(executor.execute(proposal, decision))

        assert result.action == "warehouse.labor.allocate"
        assert result.proposal_id == proposal.proposal_id
        assert result.decision_id == decision.result_id


class TestLaborActionExecutorGuards:
    def test_not_approved_raises_before_skill(self):
        skill = _mock_allocate_skill()
        executor = LaborActionExecutor(allocate_skill=skill)
        proposal = _labor_proposal()
        decision = _rejected(proposal.proposal_id)

        with pytest.raises(ActionNotApproved):
            asyncio.run(executor.execute(proposal, decision))
        skill.execute.assert_not_called()

    def test_proposal_decision_mismatch_raises(self):
        skill = _mock_allocate_skill()
        executor = LaborActionExecutor(allocate_skill=skill)
        proposal = _labor_proposal()
        wrong = _approved(str(uuid.uuid4()))  # different ID

        with pytest.raises(ActionDecisionMismatch):
            asyncio.run(executor.execute(proposal, wrong))
        skill.execute.assert_not_called()

    def test_unknown_action_blocked_by_allowlist(self):
        skill = _mock_allocate_skill()
        executor = LaborActionExecutor(allocate_skill=skill)
        proposal = ActionProposal(
            action="warehouse.labor.UNKNOWN_ATTACK",
            parameters={"warehouse_id": "WH-001"},
            domain="labor",
            risk_level=RiskLevel.MEDIUM,
            requires_approval=True,
        )
        decision = _approved(proposal.proposal_id)

        with pytest.raises(ActionUnsupported):
            asyncio.run(executor.execute(proposal, decision))
        skill.execute.assert_not_called()

    def test_expired_decision_raises(self):
        skill = _mock_allocate_skill()
        executor = LaborActionExecutor(
            allocate_skill=skill, max_decision_age_seconds=60
        )
        proposal = _labor_proposal()
        stale = _approved(proposal.proposal_id, age_seconds=120)

        with pytest.raises(ActionExpired):
            asyncio.run(executor.execute(proposal, stale))
        skill.execute.assert_not_called()

    def test_fresh_decision_within_window_does_not_expire(self):
        skill = _mock_allocate_skill()
        executor = LaborActionExecutor(
            allocate_skill=skill, max_decision_age_seconds=300
        )
        proposal = _labor_proposal()
        decision = _approved(proposal.proposal_id, age_seconds=10)

        result = asyncio.run(executor.execute(proposal, decision))
        assert result.success is True

    def test_allowed_actions_frozenset(self):
        assert LaborActionExecutor._ALLOWED_ACTIONS == frozenset(
            {"warehouse.labor.allocate"}
        )


# ── WaveActionExecutor ─────────────────────────────────────────────────────────


class TestWaveActionExecutorApprovedPath:
    def test_approved_path_calls_reprioritize_skill(self):
        skill = _mock_reprioritize_skill()
        executor = WaveActionExecutor(reprioritize_skill=skill)
        proposal = _wave_proposal()
        decision = _approved(proposal.proposal_id)

        result = asyncio.run(executor.execute(proposal, decision))

        skill.execute.assert_called_once()
        assert isinstance(result, ActionExecutionResult)
        assert result.executed is True
        assert result.success is True

    def test_approved_path_result_fields(self):
        skill = _mock_reprioritize_skill()
        executor = WaveActionExecutor(reprioritize_skill=skill)
        proposal = _wave_proposal()
        decision = _approved(proposal.proposal_id)

        result = asyncio.run(executor.execute(proposal, decision))

        assert result.action == "warehouse.wave.reprioritize"
        assert result.proposal_id == proposal.proposal_id
        assert result.decision_id == decision.result_id


class TestWaveActionExecutorGuards:
    def test_not_approved_raises_before_skill(self):
        skill = _mock_reprioritize_skill()
        executor = WaveActionExecutor(reprioritize_skill=skill)
        proposal = _wave_proposal()
        decision = _rejected(proposal.proposal_id)

        with pytest.raises(ActionNotApproved):
            asyncio.run(executor.execute(proposal, decision))
        skill.execute.assert_not_called()

    def test_proposal_decision_mismatch_raises(self):
        skill = _mock_reprioritize_skill()
        executor = WaveActionExecutor(reprioritize_skill=skill)
        proposal = _wave_proposal()
        wrong = _approved(str(uuid.uuid4()))

        with pytest.raises(ActionDecisionMismatch):
            asyncio.run(executor.execute(proposal, wrong))
        skill.execute.assert_not_called()

    def test_unknown_action_blocked_by_allowlist(self):
        skill = _mock_reprioritize_skill()
        executor = WaveActionExecutor(reprioritize_skill=skill)
        proposal = ActionProposal(
            action="warehouse.wave.INJECT_ARBITRARY",
            parameters={"warehouse_id": "WH-001"},
            domain="wave",
            risk_level=RiskLevel.MEDIUM,
            requires_approval=True,
        )
        decision = _approved(proposal.proposal_id)

        with pytest.raises(ActionUnsupported):
            asyncio.run(executor.execute(proposal, decision))
        skill.execute.assert_not_called()

    def test_expired_decision_raises(self):
        skill = _mock_reprioritize_skill()
        executor = WaveActionExecutor(
            reprioritize_skill=skill, max_decision_age_seconds=60
        )
        proposal = _wave_proposal()
        stale = _approved(proposal.proposal_id, age_seconds=120)

        with pytest.raises(ActionExpired):
            asyncio.run(executor.execute(proposal, stale))
        skill.execute.assert_not_called()

    def test_fresh_decision_within_window_does_not_expire(self):
        skill = _mock_reprioritize_skill()
        executor = WaveActionExecutor(
            reprioritize_skill=skill, max_decision_age_seconds=300
        )
        proposal = _wave_proposal()
        decision = _approved(proposal.proposal_id, age_seconds=5)

        result = asyncio.run(executor.execute(proposal, decision))
        assert result.success is True

    def test_allowed_actions_frozenset(self):
        assert WaveActionExecutor._ALLOWED_ACTIONS == frozenset(
            {"warehouse.wave.reprioritize"}
        )
