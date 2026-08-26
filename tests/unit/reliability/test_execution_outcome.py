# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 10E Batch 1 — ExecutionOutcome semantics.

Verifies:
- Canonical outcome enum values
- Backward-compat derived fields (executed, success)
- Outcome model construction
- Outcome identity (no collision between values)
"""

from __future__ import annotations

import pytest

from maiw_execution import ActionExecutionResult, ExecutionOutcome


class TestExecutionOutcomeEnum:
    def test_all_six_values_exist(self):
        values = {o.value for o in ExecutionOutcome}
        assert values == {"executed", "no_op", "deferred", "conflict", "unknown", "failed"}

    def test_values_are_strings(self):
        for o in ExecutionOutcome:
            assert isinstance(o.value, str)

    def test_no_two_outcomes_share_value(self):
        values = [o.value for o in ExecutionOutcome]
        assert len(values) == len(set(values))


class TestCompatibilityFields:
    """executed and success are derived from outcome — canonical field is outcome."""

    def _make(self, outcome: ExecutionOutcome) -> ActionExecutionResult:
        return ActionExecutionResult(
            outcome=outcome, action="test", proposal_id="p1", decision_id="d1"
        )

    def test_executed_outcome_sets_executed_true_success_true(self):
        r = self._make(ExecutionOutcome.EXECUTED)
        assert r.executed is True
        assert r.success is True

    def test_no_op_outcome_sets_executed_false_success_true(self):
        r = self._make(ExecutionOutcome.NO_OP)
        assert r.executed is False
        assert r.success is True

    def test_deferred_outcome_sets_both_false(self):
        r = self._make(ExecutionOutcome.DEFERRED)
        assert r.executed is False
        assert r.success is False

    def test_conflict_outcome_sets_both_false(self):
        r = self._make(ExecutionOutcome.CONFLICT)
        assert r.executed is False
        assert r.success is False

    def test_unknown_outcome_sets_both_false(self):
        r = self._make(ExecutionOutcome.UNKNOWN)
        assert r.executed is False
        assert r.success is False

    def test_failed_outcome_sets_both_false(self):
        r = self._make(ExecutionOutcome.FAILED)
        assert r.executed is False
        assert r.success is False

    def test_outcome_is_authoritative_overrides_direct_executed_field(self):
        """If someone tries to set executed=True with outcome=FAILED, outcome wins."""
        r = ActionExecutionResult(
            outcome=ExecutionOutcome.FAILED,
            executed=True,  # will be overridden
            success=True,   # will be overridden
            action="test", proposal_id="p1", decision_id="d1",
        )
        assert r.executed is False
        assert r.success is False
        assert r.outcome == ExecutionOutcome.FAILED

    def test_no_op_and_executed_are_distinct_outcomes(self):
        assert ExecutionOutcome.NO_OP != ExecutionOutcome.EXECUTED
        r_exec = self._make(ExecutionOutcome.EXECUTED)
        r_noop = self._make(ExecutionOutcome.NO_OP)
        assert r_exec.executed is True
        assert r_noop.executed is False
        assert r_exec.success == r_noop.success  # both success=True

    def test_unknown_is_not_failed(self):
        """UNKNOWN must be distinguishable from FAILED — never treat timeout as FAILED."""
        assert ExecutionOutcome.UNKNOWN != ExecutionOutcome.FAILED
        r = self._make(ExecutionOutcome.UNKNOWN)
        assert r.outcome == ExecutionOutcome.UNKNOWN
        assert r.outcome != ExecutionOutcome.FAILED


class TestResultConstruction:
    def test_execution_id_generated_when_not_supplied(self):
        r = ActionExecutionResult(
            outcome=ExecutionOutcome.EXECUTED,
            action="warehouse.labor.allocate",
            proposal_id="p-1",
            decision_id="d-1",
        )
        assert r.execution_id is not None
        assert len(r.execution_id) > 0

    def test_trace_id_propagated(self):
        r = ActionExecutionResult(
            outcome=ExecutionOutcome.EXECUTED,
            action="test", proposal_id="p1", decision_id="d1",
            trace_id="trace-abc",
        )
        assert r.trace_id == "trace-abc"

    def test_model_dump_includes_outcome_field(self):
        r = ActionExecutionResult(
            outcome=ExecutionOutcome.EXECUTED, action="test",
            proposal_id="p1", decision_id="d1",
        )
        d = r.model_dump()
        assert "outcome" in d
        assert d["outcome"] == "executed"
        assert "executed" in d
        assert "success" in d

    def test_physical_mutation_occurred_field(self):
        r = ActionExecutionResult(
            outcome=ExecutionOutcome.UNKNOWN, action="test",
            proposal_id="p1", decision_id="d1",
            physical_mutation_occurred=True,
        )
        assert r.physical_mutation_occurred is True
