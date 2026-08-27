# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 10E Batch 1 — Idempotency contract.

Verifies:
- Same execution_id → cached result returned, no second physical mutation
- Same idempotency_key, different execution_id → NO_OP, no second mutation
- UNKNOWN result → no retry (returns UNKNOWN again)
- ExecutionRegistry single-process semantics
- Provider physical mutation count remains 1 across duplicate calls
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from maiw_decision.models import DecisionOutcome, DecisionResult
from maiw_execution import (
    ActionExecutionResult,
    ExecutionOutcome,
    ExecutionRegistry,
    LaborActionExecutor,
)
from maiw_mcp.contracts.actions import ActionProposal, RiskLevel
from maiw_mcp.contracts.labor import LaborAllocateResult


def _approved_decision(proposal_id: str) -> DecisionResult:
    return DecisionResult(
        request_id="req-1",
        proposal_id=proposal_id,
        outcome=DecisionOutcome.APPROVED,
        evaluated_at=datetime.now(timezone.utc),
    )


def _labor_proposal(*, idempotency_key: str | None = None) -> ActionProposal:
    return ActionProposal.for_labor_allocate(
        task_id="T-001",
        task_type="PICK",
        worker_ids=["W-001"],
        zone="ZONE-A",
        reason="test",
        requested_by="test-agent",
        idempotency_key=idempotency_key,
    )


def _labor_skill_mock(*, outcome: str = "executed") -> MagicMock:
    skill = MagicMock()
    skill.execute = AsyncMock(
        return_value=LaborAllocateResult(
            success=True,
            allocation_id=str(uuid.uuid4()),
            task_id="T-001",
            worker_ids=["W-001"],
            proposal_id="p-1",
            decision_id="d-1",
            outcome=outcome,
        )
    )
    return skill


# ── ExecutionRegistry unit tests ───────────────────────────────────────────────


class TestExecutionRegistry:
    def test_begin_fresh_returns_none(self):
        registry = ExecutionRegistry()
        result = registry.begin("EXEC-1", "IDEMP-A", "warehouse.labor.allocate", "P-1")
        assert result is None

    def test_begin_same_execution_id_returns_existing(self):
        registry = ExecutionRegistry()
        registry.begin("EXEC-1", "IDEMP-A", "warehouse.labor.allocate", "P-1")
        existing = registry.begin(
            "EXEC-1", "IDEMP-A", "warehouse.labor.allocate", "P-1"
        )
        assert existing is not None
        assert existing.execution_id == "EXEC-1"

    def test_begin_same_idempotency_key_different_execution_id(self):
        registry = ExecutionRegistry()
        registry.begin("EXEC-1", "IDEMP-A", "warehouse.labor.allocate", "P-1")
        existing = registry.begin(
            "EXEC-2", "IDEMP-A", "warehouse.labor.allocate", "P-1"
        )
        assert existing is not None
        assert existing.execution_id == "EXEC-1"  # points to first

    def test_begin_different_capability_same_idempotency_key_is_fresh(self):
        """Different capability = different logical operation."""
        registry = ExecutionRegistry()
        registry.begin("EXEC-1", "IDEMP-A", "warehouse.labor.allocate", "P-1")
        existing = registry.begin(
            "EXEC-2", "IDEMP-A", "warehouse.wave.reprioritize", "P-2"
        )
        assert existing is None  # different capability → fresh

    def test_complete_marks_record(self):
        registry = ExecutionRegistry()
        registry.begin("EXEC-1", None, "warehouse.labor.allocate", "P-1")
        fake_result = object()
        registry.complete("EXEC-1", ExecutionOutcome.EXECUTED, fake_result)
        record = registry.get_by_execution_id("EXEC-1")
        assert record is not None
        assert record.outcome == ExecutionOutcome.EXECUTED
        assert record.result is fake_result

    def test_mark_unknown_sets_unknown_outcome(self):
        registry = ExecutionRegistry()
        registry.begin("EXEC-1", None, "warehouse.labor.allocate", "P-1")
        registry.mark_unknown("EXEC-1")
        record = registry.get_by_execution_id("EXEC-1")
        assert record.outcome == ExecutionOutcome.UNKNOWN

    def test_get_by_idempotency_key(self):
        registry = ExecutionRegistry()
        registry.begin("EXEC-1", "IDEMP-A", "warehouse.labor.allocate", "P-1")
        registry.complete("EXEC-1", ExecutionOutcome.EXECUTED, None)
        rec = registry.get_by_idempotency_key("IDEMP-A", "warehouse.labor.allocate")
        assert rec is not None
        assert rec.execution_id == "EXEC-1"

    def test_none_idempotency_key_not_stored_in_key_index(self):
        registry = ExecutionRegistry()
        registry.begin("EXEC-1", None, "warehouse.labor.allocate", "P-1")
        rec = registry.get_by_idempotency_key("anything", "warehouse.labor.allocate")
        assert rec is None

    def test_reset_clears_registry(self):
        registry = ExecutionRegistry()
        registry.begin("EXEC-1", "IDEMP-A", "warehouse.labor.allocate", "P-1")
        assert len(registry) == 1
        registry.reset()
        assert len(registry) == 0


# ── Executor-level idempotency tests ──────────────────────────────────────────


class TestDuplicateExecutionSameId:
    """
    Section 7: Same execution_id called 3 times → provider called once.

    Expected: logical requests=3, provider physical mutations=1
    """

    def test_same_execution_id_three_calls_one_physical_mutation(self):
        registry = ExecutionRegistry()
        skill = _labor_skill_mock()
        executor = LaborActionExecutor(
            allocate_skill=skill,
            registry=registry,
        )
        proposal = _labor_proposal(idempotency_key="IDEMP-ABC")
        decision = _approved_decision(proposal.proposal_id)

        async def run():
            r1 = await executor.execute(proposal, decision)
            # Simulate same execution_id on retry (same proposal + same registry entry)
            r2 = await executor.execute(proposal, decision)
            r3 = await executor.execute(proposal, decision)
            return r1, r2, r3

        r1, r2, r3 = asyncio.run(run())

        # First call: EXECUTED
        assert r1.outcome == ExecutionOutcome.EXECUTED
        # Second and third: NO_OP (idempotency_key match)
        assert r2.outcome == ExecutionOutcome.NO_OP
        assert r3.outcome == ExecutionOutcome.NO_OP

        # Provider called exactly once
        assert skill.execute.call_count == 1


class TestDuplicateIdempotencyKeyDifferentExecutionId:
    """
    Section 8: EXEC-1 + IDEMP-ABC, then EXEC-2 + IDEMP-ABC
    Same idempotency key → same logical mutation → second call is NO_OP.
    """

    def test_second_execution_id_same_key_is_no_op(self):
        registry = ExecutionRegistry()
        skill = _labor_skill_mock()

        executor1 = LaborActionExecutor(allocate_skill=skill, registry=registry)

        proposal_1 = _labor_proposal(idempotency_key="IDEMP-ABC")
        proposal_2 = ActionProposal.for_labor_allocate(
            task_id="T-001",
            task_type="PICK",
            worker_ids=["W-001"],
            zone="ZONE-A",
            reason="test retry",
            requested_by="test-agent",
            idempotency_key="IDEMP-ABC",
        )

        decision_1 = _approved_decision(proposal_1.proposal_id)
        decision_2 = _approved_decision(proposal_2.proposal_id)

        async def run():
            r1 = await executor1.execute(proposal_1, decision_1)
            r2 = await executor1.execute(proposal_2, decision_2)
            return r1, r2

        r1, r2 = asyncio.run(run())

        assert r1.outcome == ExecutionOutcome.EXECUTED
        assert r2.outcome == ExecutionOutcome.NO_OP
        # Only one physical mutation
        assert skill.execute.call_count == 1

    def test_no_idempotency_key_allows_multiple_executions(self):
        """Without idempotency_key, duplicate submissions are not deduplicated."""
        registry = ExecutionRegistry()
        skill = _labor_skill_mock()
        executor = LaborActionExecutor(allocate_skill=skill, registry=registry)

        # Two different proposals without idempotency_key
        p1 = _labor_proposal(idempotency_key=None)
        p2 = ActionProposal.for_labor_allocate(
            task_id="T-001",
            task_type="PICK",
            worker_ids=["W-001"],
            zone="ZONE-A",
            reason="second",
            requested_by="test-agent",
        )
        d1 = _approved_decision(p1.proposal_id)
        d2 = _approved_decision(p2.proposal_id)

        async def run():
            r1 = await executor.execute(p1, d1)
            r2 = await executor.execute(p2, d2)
            return r1, r2

        r1, r2 = asyncio.run(run())
        # Both execute independently
        assert r1.outcome == ExecutionOutcome.EXECUTED
        assert r2.outcome == ExecutionOutcome.EXECUTED
        assert skill.execute.call_count == 2


class TestIdempotentReplayMetadata:
    """
    When a duplicate execution returns NO_OP (idempotent replay),
    backend_response must carry replay metadata so callers can distinguish
    idempotent replay from genuine pre-existing-state NO_OP.
    """

    def test_no_op_replay_carries_replayed_flag(self):
        registry = ExecutionRegistry()
        skill = _labor_skill_mock()
        executor = LaborActionExecutor(allocate_skill=skill, registry=registry)
        proposal = _labor_proposal(idempotency_key="IDEMP-REPLAY")
        decision = _approved_decision(proposal.proposal_id)

        async def run():
            r1 = await executor.execute(proposal, decision)
            r2 = await executor.execute(proposal, decision)
            return r1, r2

        r1, r2 = asyncio.run(run())

        assert r1.outcome == ExecutionOutcome.EXECUTED
        assert r2.outcome == ExecutionOutcome.NO_OP
        assert r2.backend_response.get("replayed") is True

    def test_no_op_replay_carries_original_execution_id(self):
        registry = ExecutionRegistry()
        skill = _labor_skill_mock()
        executor = LaborActionExecutor(allocate_skill=skill, registry=registry)
        proposal = _labor_proposal(idempotency_key="IDEMP-REPLAY-2")
        decision = _approved_decision(proposal.proposal_id)

        async def run():
            r1 = await executor.execute(proposal, decision)
            r2 = await executor.execute(proposal, decision)
            return r1, r2

        r1, r2 = asyncio.run(run())

        original_id = r2.backend_response.get("original_execution_id")
        assert original_id is not None
        # Points back to the first execution
        assert original_id == r1.execution_id

    def test_no_op_replay_carries_original_outcome(self):
        registry = ExecutionRegistry()
        skill = _labor_skill_mock(outcome="executed")
        executor = LaborActionExecutor(allocate_skill=skill, registry=registry)
        proposal = _labor_proposal(idempotency_key="IDEMP-REPLAY-3")
        decision = _approved_decision(proposal.proposal_id)

        async def run():
            r1 = await executor.execute(proposal, decision)
            r2 = await executor.execute(proposal, decision)
            return r1, r2

        _, r2 = asyncio.run(run())

        assert r2.backend_response.get("original_outcome") == "executed"

    def test_replayed_field_absent_on_genuine_executed_result(self):
        """First-time execution does not carry replayed metadata."""
        registry = ExecutionRegistry()
        skill = _labor_skill_mock()
        executor = LaborActionExecutor(allocate_skill=skill, registry=registry)
        proposal = _labor_proposal(idempotency_key="IDEMP-FIRST")
        decision = _approved_decision(proposal.proposal_id)

        result = asyncio.run(executor.execute(proposal, decision))

        assert result.outcome == ExecutionOutcome.EXECUTED
        assert not result.backend_response.get("replayed", False)


class TestUnknownPreventsRetry:
    """After outcome=UNKNOWN, subsequent call with same idempotency_key returns UNKNOWN (no retry)."""

    def test_unknown_result_suppresses_retry(self):
        from maiw_execution.outcome import AmbiguousWriteError

        registry = ExecutionRegistry()
        skill = _labor_skill_mock()
        skill.execute = AsyncMock(side_effect=AmbiguousWriteError("response lost"))

        executor = LaborActionExecutor(allocate_skill=skill, registry=registry)
        proposal = _labor_proposal(idempotency_key="IDEMP-XYZ")
        decision = _approved_decision(proposal.proposal_id)

        async def run():
            r1 = await executor.execute(proposal, decision)
            r2 = await executor.execute(proposal, decision)
            return r1, r2

        r1, r2 = asyncio.run(run())

        assert r1.outcome == ExecutionOutcome.UNKNOWN
        assert r2.outcome == ExecutionOutcome.UNKNOWN
        # Provider called exactly once — no retry on UNKNOWN
        assert skill.execute.call_count == 1
