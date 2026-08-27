# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 10E Batch 1 — trace_id continuity (Section 11).

trace_id is the full-request lifecycle correlation identifier.
It must survive:
  1. ActionExecutionResult construction (field present, value preserved)
  2. execute() keyword parameter → result.trace_id (no post-construction injection)
  3. FAILED path (backend failure): trace_id still in result
  4. UNKNOWN path (AmbiguousWriteError): trace_id still in result
  5. DEFERRED path (NoOpActionExecutor): trace_id still in result
  6. model_dump() serialization: trace_id key present

Architecture invariant: trace_id is passed directly to execute(); there must be
NO post-construction injection pattern (`exec_result.trace_id = trace_id`).
That pattern was removed in Phase 10E Batch 1 — tests here enforce the new contract.

MCP trace boundary (PARTIAL — documented gap):
  trace_id reaches execute() and is stamped on ActionExecutionResult.
  execution_id crosses the MCP write-request boundary (LaborAllocateRequest,
  WaveReprioritizeRequest, equipment write requests all carry execution_id).
  trace_id does NOT cross the MCP boundary — it is absent from write-request
  contracts and therefore never visible inside the provider.
  This is classified as PARTIAL propagation for Batch 1.
  Full MCP trace propagation requires adding trace_id to write-request contracts
  and forwarding it through _do_execute() — deferred past Batch 1.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from maiw_decision.models import DecisionOutcome, DecisionResult
from maiw_execution import (
    ActionExecutionResult,
    ExecutionOutcome,
    LaborActionExecutor,
)
from maiw_execution.base import NoOpActionExecutor
from maiw_execution.outcome import AmbiguousWriteError
from maiw_mcp.contracts.actions import ActionProposal
from maiw_mcp.contracts.labor import LaborAllocateResult
from maiw_mcp.errors import BackendUnavailable

import uuid

TRACE_ID = "trace-10e-0001"


def _approved_decision(proposal_id: str) -> DecisionResult:
    return DecisionResult(
        request_id="req-trace",
        proposal_id=proposal_id,
        outcome=DecisionOutcome.APPROVED,
        evaluated_at=datetime.now(timezone.utc),
    )


def _labor_proposal() -> ActionProposal:
    return ActionProposal.for_labor_allocate(
        task_id="T-TRACE",
        task_type="PICK",
        worker_ids=["W-001"],
        zone="ZONE-A",
        reason="trace test",
        requested_by="test",
    )


def _success_skill() -> MagicMock:
    skill = MagicMock()
    skill.execute = AsyncMock(
        return_value=LaborAllocateResult(
            success=True,
            allocation_id=str(uuid.uuid4()),
            task_id="T-TRACE",
            worker_ids=["W-001"],
            proposal_id="p-1",
            decision_id="d-1",
            outcome="executed",
        )
    )
    return skill


# ── Section 11a: trace_id in ActionExecutionResult ────────────────────────────


class TestTraceIdInResult:
    """trace_id is a first-class field on ActionExecutionResult."""

    def test_trace_id_propagated_from_constructor(self):
        result = ActionExecutionResult(
            outcome=ExecutionOutcome.EXECUTED,
            action="warehouse.labor.allocate",
            proposal_id="p-1",
            decision_id="d-1",
            trace_id=TRACE_ID,
        )
        assert result.trace_id == TRACE_ID

    def test_trace_id_none_when_not_supplied(self):
        result = ActionExecutionResult(
            outcome=ExecutionOutcome.EXECUTED,
            action="warehouse.labor.allocate",
            proposal_id="p-1",
            decision_id="d-1",
        )
        assert result.trace_id is None

    def test_trace_id_in_model_dump(self):
        result = ActionExecutionResult(
            outcome=ExecutionOutcome.EXECUTED,
            action="test",
            proposal_id="p1",
            decision_id="d1",
            trace_id=TRACE_ID,
        )
        d = result.model_dump()
        assert "trace_id" in d
        assert d["trace_id"] == TRACE_ID

    def test_trace_id_none_serializes_as_none(self):
        result = ActionExecutionResult(
            outcome=ExecutionOutcome.EXECUTED,
            action="test",
            proposal_id="p1",
            decision_id="d1",
        )
        d = result.model_dump()
        assert "trace_id" in d
        assert d["trace_id"] is None


# ── Section 11b: trace_id through execute() keyword parameter ─────────────────


class TestTraceIdThroughExecute:
    """
    trace_id is accepted as a keyword-only parameter on execute().
    No post-construction injection (`exec_result.trace_id = trace_id`) is allowed.
    """

    def test_trace_id_keyword_param_survives_to_result_on_executed(self):
        executor = LaborActionExecutor(allocate_skill=_success_skill())
        proposal = _labor_proposal()
        decision = _approved_decision(proposal.proposal_id)

        result = asyncio.run(executor.execute(proposal, decision, trace_id=TRACE_ID))

        assert result.trace_id == TRACE_ID

    def test_trace_id_none_when_not_passed(self):
        executor = LaborActionExecutor(allocate_skill=_success_skill())
        proposal = _labor_proposal()
        decision = _approved_decision(proposal.proposal_id)

        result = asyncio.run(executor.execute(proposal, decision))

        assert result.trace_id is None

    def test_different_trace_ids_are_independent(self):
        """Two executions with different trace_ids get different values."""
        executor1 = LaborActionExecutor(allocate_skill=_success_skill())
        executor2 = LaborActionExecutor(allocate_skill=_success_skill())
        p1 = _labor_proposal()
        p2 = _labor_proposal()
        d1 = _approved_decision(p1.proposal_id)
        d2 = _approved_decision(p2.proposal_id)

        r1 = asyncio.run(executor1.execute(p1, d1, trace_id="trace-AAA"))
        r2 = asyncio.run(executor2.execute(p2, d2, trace_id="trace-BBB"))

        assert r1.trace_id == "trace-AAA"
        assert r2.trace_id == "trace-BBB"


# ── Section 11c: trace_id on all outcome paths ───────────────────────────────


class TestTraceIdOnAllPaths:
    """trace_id must appear in the result regardless of outcome."""

    def test_trace_id_on_executed_path(self):
        executor = LaborActionExecutor(allocate_skill=_success_skill())
        proposal = _labor_proposal()
        decision = _approved_decision(proposal.proposal_id)

        result = asyncio.run(executor.execute(proposal, decision, trace_id=TRACE_ID))

        assert result.outcome == ExecutionOutcome.EXECUTED
        assert result.trace_id == TRACE_ID

    def test_trace_id_on_failed_path(self):
        """BackendUnavailable → FAILED; trace_id still present."""
        skill = MagicMock()
        skill.execute = AsyncMock(
            side_effect=BackendUnavailable("provider unreachable")
        )
        executor = LaborActionExecutor(allocate_skill=skill)
        proposal = _labor_proposal()
        decision = _approved_decision(proposal.proposal_id)

        result = asyncio.run(executor.execute(proposal, decision, trace_id=TRACE_ID))

        assert result.outcome == ExecutionOutcome.FAILED
        assert result.trace_id == TRACE_ID

    def test_trace_id_on_unknown_path(self):
        """AmbiguousWriteError → UNKNOWN; trace_id still present."""
        skill = MagicMock()
        skill.execute = AsyncMock(
            side_effect=AmbiguousWriteError("response lost after write")
        )
        executor = LaborActionExecutor(allocate_skill=skill)
        proposal = _labor_proposal()
        decision = _approved_decision(proposal.proposal_id)

        result = asyncio.run(executor.execute(proposal, decision, trace_id=TRACE_ID))

        assert result.outcome == ExecutionOutcome.UNKNOWN
        assert result.trace_id == TRACE_ID

    def test_trace_id_on_no_op_path(self):
        """Provider returns no_op outcome; trace_id still present."""
        from maiw_mcp.contracts.labor import LaborAllocateResult

        skill = MagicMock()
        skill.execute = AsyncMock(
            return_value=LaborAllocateResult(
                success=True,
                allocation_id=None,
                task_id="T-TRACE",
                worker_ids=["W-001"],
                proposal_id="p-1",
                decision_id="d-1",
                outcome="no_op",
            )
        )
        executor = LaborActionExecutor(allocate_skill=skill)
        proposal = _labor_proposal()
        decision = _approved_decision(proposal.proposal_id)

        result = asyncio.run(executor.execute(proposal, decision, trace_id=TRACE_ID))

        assert result.outcome == ExecutionOutcome.NO_OP
        assert result.trace_id == TRACE_ID

    def test_trace_id_on_deferred_path_noop_executor(self):
        """NoOpActionExecutor → DEFERRED; trace_id still present."""
        executor = NoOpActionExecutor()
        proposal = _labor_proposal()
        decision = _approved_decision(proposal.proposal_id)

        result = asyncio.run(executor.execute(proposal, decision, trace_id=TRACE_ID))

        assert result.outcome == ExecutionOutcome.DEFERRED
        assert result.trace_id == TRACE_ID


# ── Section 11d: execution_id stability ──────────────────────────────────────


class TestExecutionIdStability:
    """execution_id is generated once before the write and must not change."""

    def test_execution_id_generated_and_stable(self):
        executor = LaborActionExecutor(allocate_skill=_success_skill())
        proposal = _labor_proposal()
        decision = _approved_decision(proposal.proposal_id)

        result = asyncio.run(executor.execute(proposal, decision))

        assert result.execution_id is not None
        assert len(result.execution_id) > 0

    def test_execution_id_is_uuid_like(self):
        executor = LaborActionExecutor(allocate_skill=_success_skill())
        proposal = _labor_proposal()
        decision = _approved_decision(proposal.proposal_id)

        result = asyncio.run(executor.execute(proposal, decision))

        # Must parse as a UUID
        parsed = uuid.UUID(result.execution_id)
        assert str(parsed) == result.execution_id

    def test_execution_id_distinct_across_calls(self):
        """Each call generates a fresh execution_id (no deterministic reuse)."""
        executor1 = LaborActionExecutor(allocate_skill=_success_skill())
        executor2 = LaborActionExecutor(allocate_skill=_success_skill())
        p1 = _labor_proposal()
        p2 = _labor_proposal()

        r1 = asyncio.run(executor1.execute(p1, _approved_decision(p1.proposal_id)))
        r2 = asyncio.run(executor2.execute(p2, _approved_decision(p2.proposal_id)))

        assert r1.execution_id != r2.execution_id

    def test_execution_id_in_model_dump(self):
        executor = LaborActionExecutor(allocate_skill=_success_skill())
        proposal = _labor_proposal()
        decision = _approved_decision(proposal.proposal_id)

        result = asyncio.run(executor.execute(proposal, decision, trace_id=TRACE_ID))
        d = result.model_dump()

        assert "execution_id" in d
        assert d["execution_id"] == result.execution_id


# ── Section 11e: MCP trace boundary — documented gap ─────────────────────────


class TestMCPTraceBoundary:
    """
    Documents the PARTIAL classification of trace propagation in Batch 1.

    COMPLETE: trace_id and execution_id are present on ActionExecutionResult.
    PARTIAL:  execution_id crosses the MCP write-request boundary (present in
              LaborAllocateRequest, WaveReprioritizeRequest, equipment write
              requests). trace_id does NOT — it is absent from all write-request
              contracts and therefore never visible inside the provider.

    These tests prove the current boundary precisely so future batches can
    extend propagation without ambiguity about what Batch 1 delivered.
    """

    def test_execution_id_present_in_labor_write_request_contract(self):
        """execution_id field exists on the write-request contract → crosses MCP."""
        from maiw_mcp.contracts.labor import LaborAllocateRequest

        fields = LaborAllocateRequest.model_fields
        assert "execution_id" in fields

    def test_trace_id_absent_from_labor_write_request_contract(self):
        """trace_id field is NOT on the write-request contract → stops at executor."""
        from maiw_mcp.contracts.labor import LaborAllocateRequest

        fields = LaborAllocateRequest.model_fields
        assert "trace_id" not in fields

    def test_execution_id_present_in_wave_write_request_contract(self):
        from maiw_mcp.contracts.wave import WaveReprioritizeRequest

        fields = WaveReprioritizeRequest.model_fields
        assert "execution_id" in fields

    def test_trace_id_absent_from_wave_write_request_contract(self):
        from maiw_mcp.contracts.wave import WaveReprioritizeRequest

        fields = WaveReprioritizeRequest.model_fields
        assert "trace_id" not in fields

    def test_execution_id_present_in_equipment_assign_request_contract(self):
        from maiw_mcp.contracts.equipment import EquipmentExecuteAssignRequest

        fields = EquipmentExecuteAssignRequest.model_fields
        assert "execution_id" in fields

    def test_trace_id_absent_from_equipment_assign_request_contract(self):
        from maiw_mcp.contracts.equipment import EquipmentExecuteAssignRequest

        fields = EquipmentExecuteAssignRequest.model_fields
        assert "trace_id" not in fields

    def test_execution_id_forwarded_to_skill_in_labor_do_execute(self):
        """
        The execution_id generated in execute() is forwarded into the skill call.
        Captures the exact request passed to the skill and verifies execution_id matches.
        """
        captured_requests = []

        async def capturing_skill(req):
            captured_requests.append(req)
            from maiw_mcp.contracts.labor import LaborAllocateResult

            return LaborAllocateResult(
                success=True,
                allocation_id="alloc-1",
                task_id="T-TRACE",
                worker_ids=["W-001"],
                proposal_id="p-1",
                decision_id="d-1",
                outcome="executed",
            )

        skill = MagicMock()
        skill.execute = capturing_skill
        executor = LaborActionExecutor(allocate_skill=skill)
        proposal = _labor_proposal()
        decision = _approved_decision(proposal.proposal_id)

        result = asyncio.run(executor.execute(proposal, decision, trace_id=TRACE_ID))

        assert len(captured_requests) == 1
        req = captured_requests[0]
        # execution_id crosses the MCP boundary
        assert req.execution_id == result.execution_id
        # trace_id does NOT cross (field absent from contract)
        assert not hasattr(req, "trace_id") or getattr(req, "trace_id", None) is None
