# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 10E Batch 1 — Ambiguous write semantics (Sections 9 & 10).

The highest-priority test in Phase 10E.

Section 9: timeout/failure BEFORE mutation → outcome = FAILED
    provider physical_mutations = 0
    automatic_retry_count = 0

Section 10: mutation occurs, response lost → outcome = UNKNOWN
    NOT outcome = FAILED
    provider physical_mutations = 1
    automatic_retry_count = 0
    UNKNOWN must be terminal — no automatic retry
"""

from __future__ import annotations

import asyncio
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
from maiw_execution.outcome import AmbiguousWriteError
from maiw_mcp.contracts.actions import ActionProposal
from maiw_mcp.contracts.labor import LaborAllocateResult
from maiw_mcp.errors import BackendUnavailable


def _approved_decision(proposal_id: str) -> DecisionResult:
    return DecisionResult(
        request_id="req-1",
        proposal_id=proposal_id,
        outcome=DecisionOutcome.APPROVED,
        evaluated_at=datetime.now(timezone.utc),
    )


def _labor_proposal() -> ActionProposal:
    return ActionProposal.for_labor_allocate(
        task_id="T-AMBIG",
        task_type="PICK",
        worker_ids=["W-001"],
        zone="ZONE-A",
        reason="ambiguous write test",
        requested_by="reliability-test",
    )


# ── Section 9: pre-mutation failure → FAILED ──────────────────────────────────


class TestPreMutationFailure:
    """
    Provider raises BEFORE mutation (BackendUnavailable, network error).
    Expected: outcome = FAILED, physical_mutation_occurred = False.
    """

    def test_backend_unavailable_before_mutation_produces_failed(self):
        skill = MagicMock()
        skill.execute = AsyncMock(
            side_effect=BackendUnavailable("provider unreachable")
        )
        executor = LaborActionExecutor(allocate_skill=skill)
        proposal = _labor_proposal()
        decision = _approved_decision(proposal.proposal_id)

        result = asyncio.run(executor.execute(proposal, decision))

        assert result.outcome == ExecutionOutcome.FAILED
        assert result.executed is False
        assert result.success is False
        assert result.physical_mutation_occurred is False

    def test_generic_exception_before_mutation_produces_failed(self):
        skill = MagicMock()
        skill.execute = AsyncMock(
            side_effect=RuntimeError("DB connection lost")
        )
        executor = LaborActionExecutor(allocate_skill=skill)
        proposal = _labor_proposal()
        decision = _approved_decision(proposal.proposal_id)

        result = asyncio.run(executor.execute(proposal, decision))

        assert result.outcome == ExecutionOutcome.FAILED

    def test_failed_outcome_does_not_retry_automatically(self):
        """The executor calls the provider exactly once for a FAILED outcome."""
        skill = MagicMock()
        skill.execute = AsyncMock(
            side_effect=BackendUnavailable("provider unreachable")
        )
        executor = LaborActionExecutor(allocate_skill=skill)
        proposal = _labor_proposal()
        decision = _approved_decision(proposal.proposal_id)

        asyncio.run(executor.execute(proposal, decision))

        # Called exactly once — no automatic retry
        assert skill.execute.call_count == 1

    def test_failed_is_distinguishable_from_unknown(self):
        skill = MagicMock()
        skill.execute = AsyncMock(side_effect=BackendUnavailable("gone"))
        executor = LaborActionExecutor(allocate_skill=skill)
        proposal = _labor_proposal()
        decision = _approved_decision(proposal.proposal_id)

        result = asyncio.run(executor.execute(proposal, decision))

        assert result.outcome == ExecutionOutcome.FAILED
        assert result.outcome != ExecutionOutcome.UNKNOWN


# ── Section 10: post-mutation failure → UNKNOWN ───────────────────────────────


class TestPostMutationAmbiguousWrite:
    """
    Provider mutates state, then raises AmbiguousWriteError (simulating response lost).
    Expected: outcome = UNKNOWN, NOT FAILED.
    physical_mutation_occurred = True.
    No automatic retry.
    """

    def test_ambiguous_write_error_produces_unknown_not_failed(self):
        skill = MagicMock()
        skill.execute = AsyncMock(
            side_effect=AmbiguousWriteError(
                "Provider mutated state but response was lost (MCP timeout after write)"
            )
        )
        executor = LaborActionExecutor(allocate_skill=skill)
        proposal = _labor_proposal()
        decision = _approved_decision(proposal.proposal_id)

        result = asyncio.run(executor.execute(proposal, decision))

        assert result.outcome == ExecutionOutcome.UNKNOWN
        assert result.outcome != ExecutionOutcome.FAILED
        assert result.executed is False   # compat: False because not confirmed
        assert result.success is False    # compat: False
        assert result.physical_mutation_occurred is True

    def test_unknown_outcome_contains_error_message(self):
        skill = MagicMock()
        skill.execute = AsyncMock(
            side_effect=AmbiguousWriteError("network timeout after write")
        )
        executor = LaborActionExecutor(allocate_skill=skill)
        proposal = _labor_proposal()
        decision = _approved_decision(proposal.proposal_id)

        result = asyncio.run(executor.execute(proposal, decision))

        assert result.error_message is not None
        assert len(result.error_message) > 0

    def test_unknown_does_not_retry_automatically(self):
        """Provider called exactly once — UNKNOWN is terminal in Batch 1."""
        skill = MagicMock()
        skill.execute = AsyncMock(
            side_effect=AmbiguousWriteError("response lost")
        )
        executor = LaborActionExecutor(allocate_skill=skill)
        proposal = _labor_proposal()
        decision = _approved_decision(proposal.proposal_id)

        asyncio.run(executor.execute(proposal, decision))

        assert skill.execute.call_count == 1

    def test_unknown_with_registry_prevents_subsequent_retry(self):
        """
        After UNKNOWN, calling execute() again with the same idempotency_key
        returns UNKNOWN immediately without calling the provider again.
        """
        registry = ExecutionRegistry()
        skill = MagicMock()
        skill.execute = AsyncMock(
            side_effect=AmbiguousWriteError("response lost")
        )

        proposal = ActionProposal.for_labor_allocate(
            task_id="T-AMBIG", task_type="PICK", worker_ids=["W-001"],
            zone="ZONE-A", reason="test", requested_by="test",
            idempotency_key="IDEMP-AMBIG",
        )
        decision = _approved_decision(proposal.proposal_id)
        executor = LaborActionExecutor(allocate_skill=skill, registry=registry)

        async def run():
            r1 = await executor.execute(proposal, decision)
            r2 = await executor.execute(proposal, decision)
            return r1, r2

        r1, r2 = asyncio.run(run())

        # Both return UNKNOWN
        assert r1.outcome == ExecutionOutcome.UNKNOWN
        assert r2.outcome == ExecutionOutcome.UNKNOWN
        # Provider called only once — no retry on UNKNOWN
        assert skill.execute.call_count == 1

    def test_unknown_result_marks_reconciliation_needed(self):
        """
        The caller can detect UNKNOWN and surface RECONCILIATION_REQUIRED.
        MAIW must never claim the write succeeded.
        """
        skill = MagicMock()
        skill.execute = AsyncMock(side_effect=AmbiguousWriteError("timeout"))
        executor = LaborActionExecutor(allocate_skill=skill)
        proposal = _labor_proposal()
        decision = _approved_decision(proposal.proposal_id)

        result = asyncio.run(executor.execute(proposal, decision))

        assert result.outcome == ExecutionOutcome.UNKNOWN
        assert not result.success   # do not claim success
        assert not result.executed  # do not claim executed


# ── Section 10: provider-level fault injection via SimulationLaborProvider ────


class TestProviderFaultInjection:
    """
    Uses SimulationLaborProvider's _post_mutation_fault to inject
    AmbiguousWriteError after world state has been mutated.
    """

    def _make_world(self):
        import sys
        sys.path.insert(0, "/home/nvidia/Multi-Agent-Intelligent-Warehouse")
        from maiw_api.demo.world import DemoWarehouseWorld
        from maiw_api.demo.events import ScenarioEventBus
        world = DemoWarehouseWorld()
        # Set up a task and a worker
        from maiw_api.demo.world import TaskState, WorkerState
        world.tasks["T-FAULT"] = TaskState(
            task_id="T-FAULT", task_type="PICK", zone="ZONE-A",
            status="pending", priority="medium",
        )
        world.workers["W-001"] = WorkerState(
            worker_id="W-001", username="worker1", full_name="Worker One",
            role="operator", status="active", zone="ZONE-A",
        )
        bus = MagicMock()
        bus.publish_labor_write = AsyncMock()
        return world, bus

    def test_mutation_committed_before_fault(self):
        """World state IS mutated even when AmbiguousWriteError fires."""
        world, bus = self._make_world()
        from maiw_api.demo.providers.labor import SimulationLaborProvider

        provider = SimulationLaborProvider(world=world, bus=bus)
        provider._post_mutation_fault = AmbiguousWriteError("response lost after mutation")

        from maiw_mcp.contracts.labor import LaborAllocateRequest
        req = LaborAllocateRequest(
            warehouse_id="default", task_id="T-FAULT", task_type="PICK",
            worker_ids=["W-001"], proposal_id="p-1", decision_id="d-1",
            execution_id="exec-fault",
        )

        with pytest.raises(AmbiguousWriteError):
            asyncio.run(provider.execute_labor_allocation(req))

        # Mutation occurred in world despite the error
        assert world.tasks["T-FAULT"].status == "in_progress"
        assert world.tasks["T-FAULT"].assigned_to == "W-001"
        assert provider._mutation_count == 1

    def test_executor_receives_unknown_from_provider_fault(self):
        """Full stack: provider mutates + faults → executor returns UNKNOWN."""
        world, bus = self._make_world()
        from maiw_api.demo.providers.labor import SimulationLaborProvider
        from maiw_skills.labor.skills import ProposeLaborAllocationSkill  # noqa: F401

        provider = SimulationLaborProvider(world=world, bus=bus)
        provider._post_mutation_fault = AmbiguousWriteError("network timeout post-write")

        # Build a skill that calls the provider directly (skip MCP transport)
        skill = MagicMock()

        async def _skill_execute(req):
            return await provider.execute_labor_allocation(req)

        skill.execute = _skill_execute

        executor = LaborActionExecutor(allocate_skill=skill)
        proposal = ActionProposal.for_labor_allocate(
            task_id="T-FAULT", task_type="PICK", worker_ids=["W-001"],
            zone="ZONE-A", reason="fault test", requested_by="test",
        )
        decision = _approved_decision(proposal.proposal_id)

        result = asyncio.run(executor.execute(proposal, decision))

        # Executor sees UNKNOWN (mutation occurred, response lost)
        assert result.outcome == ExecutionOutcome.UNKNOWN
        assert result.physical_mutation_occurred is True
        # World mutation is committed
        assert world.tasks["T-FAULT"].status == "in_progress"
