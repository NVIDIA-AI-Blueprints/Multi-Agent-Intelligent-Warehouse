# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 10E Batch 3 — Reconciliation tests.

Coverage
--------
Section 13a : ExecutionIntent construction and immutability
Section 13b : ReconciliationRecord defaults and fields
Section 13c : ReconciliationOutcome enum values
Section 13d : ExecutionRecord with intent + reconciliation + effective_status
Section 13e : ReconciliationService — non-UNKNOWN rejection
Section 13f : ReconciliationService — no intent → INDETERMINATE
Section 13g : ReconciliationService — read failure → INDETERMINATE
Section 13h : ReconciliationService — check_postcondition failure → INDETERMINATE
Section 13i : ReconciliationService — CONFIRMED_EXECUTED path
Section 13j : ReconciliationService — CONFIRMED_NOT_EXECUTED path
Section 13k : ReconciliationService — INDETERMINATE strategy
Section 13l : ExecutionOutcome.UNKNOWN preservation after reconciliation
Section 13m : ExecutionRegistry.begin() with intent kwarg
Section 13n : ExecutionRegistry.set_reconciliation() — happy path
Section 13o : ExecutionRegistry.set_reconciliation() — unknown execution_id warns
Section 13p : ExecutionRegistry.set_reconciliation() — non-UNKNOWN warns but stores
Section 13q : effective_status computed property — all branches
Section 13r : BaseActionExecutor._build_intent() base implementation
Section 13s : LaborActionExecutor._build_intent() — expected_effect
Section 13t : EquipmentActionExecutor._build_intent() — assign/release/maintenance
Section 13u : WaveActionExecutor._build_intent() — wave_id and zone paths
Section 13v : ReconciliationStrategy Protocol structural check
Section 13w : Audit trail — reconciliation_id, reconciled_at, evidence stored
Section 13x : Structured log events (no assertion — exercise code paths)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maiw_execution import (
    ExecutionIntent,
    ExecutionRecord,
    ExecutionRegistry,
    ReconciliationOutcome,
    ReconciliationRecord,
    ReconciliationService,
    ReconciliationStrategy,
)
from maiw_execution.outcome import ExecutionOutcome

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_intent(**kwargs) -> ExecutionIntent:
    defaults = dict(
        capability="warehouse.labor.allocate",
        proposal_id="prop-001",
        decision_id="dec-001",
        warehouse_id="DC-TEST",
        target="task-123",
        expected_effect={
            "task_id": "task-123",
            "expected_worker_ids": ["w1"],
            "expected_task_status": "in_progress",
        },
        approval_id="appr-001",
        idempotency_key="idem-001",
        trace_id="trace-001",
    )
    defaults.update(kwargs)
    return ExecutionIntent(**defaults)


def _make_record(
    execution_id: str = "exec-001",
    outcome: ExecutionOutcome | None = ExecutionOutcome.UNKNOWN,
    intent: ExecutionIntent | None = None,
) -> ExecutionRecord:
    return ExecutionRecord(
        execution_id=execution_id,
        idempotency_key="idem-001",
        capability="warehouse.labor.allocate",
        proposal_id="prop-001",
        started_at=datetime.now(timezone.utc),
        outcome=outcome,
        intent=intent,
    )


class _ConfirmedExecutedStrategy:
    async def read_current_state(self, intent: ExecutionIntent) -> dict:
        return {"allocations": [{"task_id": "task-123", "status": "in_progress"}]}

    def check_postcondition(
        self, intent: ExecutionIntent, state: dict
    ) -> ReconciliationOutcome:
        return ReconciliationOutcome.CONFIRMED_EXECUTED


class _ConfirmedNotExecutedStrategy:
    async def read_current_state(self, intent: ExecutionIntent) -> dict:
        return {"allocations": []}

    def check_postcondition(
        self, intent: ExecutionIntent, state: dict
    ) -> ReconciliationOutcome:
        return ReconciliationOutcome.CONFIRMED_NOT_EXECUTED


class _IndeterminateStrategy:
    async def read_current_state(self, intent: ExecutionIntent) -> dict:
        return {}

    def check_postcondition(
        self, intent: ExecutionIntent, state: dict
    ) -> ReconciliationOutcome:
        return ReconciliationOutcome.INDETERMINATE


class _ReadFailStrategy:
    async def read_current_state(self, intent: ExecutionIntent) -> dict:
        raise RuntimeError("MCP timeout")

    def check_postcondition(
        self, intent: ExecutionIntent, state: dict
    ) -> ReconciliationOutcome:
        return ReconciliationOutcome.CONFIRMED_EXECUTED


class _CheckFailStrategy:
    async def read_current_state(self, intent: ExecutionIntent) -> dict:
        return {"data": "ok"}

    def check_postcondition(
        self, intent: ExecutionIntent, state: dict
    ) -> ReconciliationOutcome:
        raise ValueError("postcondition logic error")


# ── Section 13a: ExecutionIntent construction and immutability ─────────────────


class TestExecutionIntentConstruction:
    def test_all_fields_set(self):
        intent = _make_intent()
        assert intent.capability == "warehouse.labor.allocate"
        assert intent.proposal_id == "prop-001"
        assert intent.decision_id == "dec-001"
        assert intent.warehouse_id == "DC-TEST"
        assert intent.target == "task-123"
        assert intent.expected_effect["task_id"] == "task-123"
        assert intent.approval_id == "appr-001"
        assert intent.idempotency_key == "idem-001"
        assert intent.trace_id == "trace-001"

    def test_frozen_prevents_mutation(self):
        intent = _make_intent()
        with pytest.raises((AttributeError, TypeError)):
            intent.capability = "changed"  # type: ignore[misc]

    def test_optional_fields_default_none(self):
        intent = ExecutionIntent(
            capability="warehouse.labor.allocate",
            proposal_id="p1",
            decision_id="d1",
        )
        assert intent.warehouse_id is None
        assert intent.target is None
        assert intent.approval_id is None
        assert intent.idempotency_key is None
        assert intent.trace_id is None

    def test_expected_effect_defaults_empty_dict(self):
        intent = ExecutionIntent(
            capability="warehouse.labor.allocate",
            proposal_id="p1",
            decision_id="d1",
        )
        assert intent.expected_effect == {}


# ── Section 13b: ReconciliationRecord defaults ─────────────────────────────────


class TestReconciliationRecordDefaults:
    def test_auto_reconciliation_id(self):
        r1 = ReconciliationRecord()
        r2 = ReconciliationRecord()
        assert r1.reconciliation_id != r2.reconciliation_id

    def test_default_outcome_is_indeterminate(self):
        record = ReconciliationRecord()
        assert record.outcome == ReconciliationOutcome.INDETERMINATE

    def test_reconciled_at_is_utc(self):
        record = ReconciliationRecord()
        assert record.reconciled_at.tzinfo is not None

    def test_optional_fields_default_none(self):
        record = ReconciliationRecord()
        assert record.trace_id is None
        assert record.error is None

    def test_can_set_all_fields(self):
        now = datetime.now(timezone.utc)
        record = ReconciliationRecord(
            reconciliation_id="r-001",
            outcome=ReconciliationOutcome.CONFIRMED_EXECUTED,
            reconciled_at=now,
            evidence={"key": "val"},
            trace_id="t-001",
            error=None,
        )
        assert record.outcome == ReconciliationOutcome.CONFIRMED_EXECUTED
        assert record.evidence == {"key": "val"}


# ── Section 13c: ReconciliationOutcome enum values ────────────────────────────


class TestReconciliationOutcomeEnum:
    def test_values(self):
        assert ReconciliationOutcome.CONFIRMED_EXECUTED.value == "confirmed_executed"
        assert (
            ReconciliationOutcome.CONFIRMED_NOT_EXECUTED.value
            == "confirmed_not_executed"
        )
        assert ReconciliationOutcome.INDETERMINATE.value == "indeterminate"

    def test_is_str_enum(self):
        assert isinstance(ReconciliationOutcome.CONFIRMED_EXECUTED, str)

    def test_three_members(self):
        assert len(list(ReconciliationOutcome)) == 3


# ── Section 13d: ExecutionRecord fields and effective_status ──────────────────


class TestExecutionRecordBatch3Fields:
    def test_intent_field_defaults_none(self):
        rec = _make_record(outcome=ExecutionOutcome.EXECUTED)
        assert rec.intent is None

    def test_reconciliation_field_defaults_none(self):
        rec = _make_record()
        assert rec.reconciliation is None

    def test_intent_stored(self):
        intent = _make_intent()
        rec = _make_record(intent=intent)
        assert rec.intent is intent

    def test_reconciliation_stored(self):
        rec = _make_record()
        recon_rec = ReconciliationRecord(
            outcome=ReconciliationOutcome.CONFIRMED_EXECUTED
        )
        rec.reconciliation = recon_rec
        assert rec.reconciliation.outcome == ReconciliationOutcome.CONFIRMED_EXECUTED


# ── Section 13e: ReconciliationService — non-UNKNOWN rejection ────────────────


class TestReconciliationServiceNonUnknownRejection:
    @pytest.mark.asyncio
    async def test_executed_outcome_raises(self):
        rec = _make_record(outcome=ExecutionOutcome.EXECUTED)
        service = ReconciliationService()
        with pytest.raises(ValueError, match="expected UNKNOWN"):
            await service.reconcile(rec, strategy=_ConfirmedExecutedStrategy())

    @pytest.mark.asyncio
    async def test_failed_outcome_raises(self):
        rec = _make_record(outcome=ExecutionOutcome.FAILED)
        service = ReconciliationService()
        with pytest.raises(ValueError, match="expected UNKNOWN"):
            await service.reconcile(rec, strategy=_ConfirmedExecutedStrategy())

    @pytest.mark.asyncio
    async def test_in_progress_raises(self):
        rec = _make_record(outcome=None)
        service = ReconciliationService()
        with pytest.raises(ValueError, match="expected UNKNOWN"):
            await service.reconcile(rec, strategy=_ConfirmedExecutedStrategy())


# ── Section 13f: ReconciliationService — no intent ────────────────────────────


class TestReconciliationServiceNoIntent:
    @pytest.mark.asyncio
    async def test_no_intent_returns_indeterminate(self):
        rec = _make_record(intent=None)
        service = ReconciliationService()
        result = await service.reconcile(
            rec, strategy=_ConfirmedExecutedStrategy(), trace_id="t1"
        )
        assert result.outcome == ReconciliationOutcome.INDETERMINATE
        assert result.error is not None
        assert "no intent" in result.error.lower() or "intent" in result.error.lower()

    @pytest.mark.asyncio
    async def test_no_intent_evidence_has_reason(self):
        rec = _make_record(intent=None)
        service = ReconciliationService()
        result = await service.reconcile(rec, strategy=_ConfirmedExecutedStrategy())
        assert result.evidence.get("reason") == "no_intent_snapshot"


# ── Section 13g: ReconciliationService — read failure ────────────────────────


class TestReconciliationServiceReadFailure:
    @pytest.mark.asyncio
    async def test_read_failure_returns_indeterminate(self):
        intent = _make_intent()
        rec = _make_record(intent=intent)
        service = ReconciliationService()
        result = await service.reconcile(
            rec, strategy=_ReadFailStrategy(), trace_id="t2"
        )
        assert result.outcome == ReconciliationOutcome.INDETERMINATE
        assert result.error == "MCP timeout"
        assert result.evidence.get("reason") == "read_failed"

    @pytest.mark.asyncio
    async def test_read_failure_sets_trace_id(self):
        intent = _make_intent()
        rec = _make_record(intent=intent)
        service = ReconciliationService()
        result = await service.reconcile(
            rec, strategy=_ReadFailStrategy(), trace_id="trace-xyz"
        )
        assert result.trace_id == "trace-xyz"


# ── Section 13h: ReconciliationService — check failure ───────────────────────


class TestReconciliationServiceCheckFailure:
    @pytest.mark.asyncio
    async def test_check_failure_returns_indeterminate(self):
        intent = _make_intent()
        rec = _make_record(intent=intent)
        service = ReconciliationService()
        result = await service.reconcile(rec, strategy=_CheckFailStrategy())
        assert result.outcome == ReconciliationOutcome.INDETERMINATE
        assert result.error == "postcondition logic error"
        assert result.evidence.get("reason") == "check_failed"


# ── Section 13i: ReconciliationService — CONFIRMED_EXECUTED ──────────────────


class TestReconciliationServiceConfirmedExecuted:
    @pytest.mark.asyncio
    async def test_confirmed_executed_outcome(self):
        intent = _make_intent()
        rec = _make_record(intent=intent)
        service = ReconciliationService()
        result = await service.reconcile(
            rec, strategy=_ConfirmedExecutedStrategy(), trace_id="t3"
        )
        assert result.outcome == ReconciliationOutcome.CONFIRMED_EXECUTED

    @pytest.mark.asyncio
    async def test_evidence_contains_state(self):
        intent = _make_intent()
        rec = _make_record(intent=intent)
        service = ReconciliationService()
        result = await service.reconcile(rec, strategy=_ConfirmedExecutedStrategy())
        assert "allocations" in result.evidence

    @pytest.mark.asyncio
    async def test_error_is_none_on_success(self):
        intent = _make_intent()
        rec = _make_record(intent=intent)
        service = ReconciliationService()
        result = await service.reconcile(rec, strategy=_ConfirmedExecutedStrategy())
        assert result.error is None


# ── Section 13j: ReconciliationService — CONFIRMED_NOT_EXECUTED ──────────────


class TestReconciliationServiceConfirmedNotExecuted:
    @pytest.mark.asyncio
    async def test_confirmed_not_executed_outcome(self):
        intent = _make_intent()
        rec = _make_record(intent=intent)
        service = ReconciliationService()
        result = await service.reconcile(rec, strategy=_ConfirmedNotExecutedStrategy())
        assert result.outcome == ReconciliationOutcome.CONFIRMED_NOT_EXECUTED

    @pytest.mark.asyncio
    async def test_no_automatic_retry(self):
        # CONFIRMED_NOT_EXECUTED must not trigger any retry side-effect
        # The reconcile() call returns a record only; no new proposal/decision/approval
        intent = _make_intent()
        rec = _make_record(intent=intent)
        service = ReconciliationService()
        result = await service.reconcile(rec, strategy=_ConfirmedNotExecutedStrategy())
        # Verify: reconcile() returns a ReconciliationRecord, not an execution result
        assert isinstance(result, ReconciliationRecord)
        # Original outcome is still UNKNOWN (not retried)
        assert rec.outcome == ExecutionOutcome.UNKNOWN


# ── Section 13k: ReconciliationService — INDETERMINATE strategy ──────────────


class TestReconciliationServiceIndeterminate:
    @pytest.mark.asyncio
    async def test_indeterminate_outcome(self):
        intent = _make_intent()
        rec = _make_record(intent=intent)
        service = ReconciliationService()
        result = await service.reconcile(rec, strategy=_IndeterminateStrategy())
        assert result.outcome == ReconciliationOutcome.INDETERMINATE


# ── Section 13l: ExecutionOutcome.UNKNOWN preservation ───────────────────────


class TestUnknownOutcomePreservation:
    @pytest.mark.asyncio
    async def test_unknown_not_overwritten_after_reconciliation(self):
        intent = _make_intent()
        rec = _make_record(intent=intent)
        registry = ExecutionRegistry()
        registry._by_execution_id[rec.execution_id] = rec

        service = ReconciliationService()
        recon = await service.reconcile(rec, strategy=_ConfirmedExecutedStrategy())
        registry.set_reconciliation(rec.execution_id, recon)

        # outcome is still UNKNOWN — the history is preserved
        assert rec.outcome == ExecutionOutcome.UNKNOWN
        # reconciliation record captures what we learned
        assert rec.reconciliation.outcome == ReconciliationOutcome.CONFIRMED_EXECUTED

    @pytest.mark.asyncio
    async def test_effective_status_updated_not_outcome(self):
        intent = _make_intent()
        rec = _make_record(intent=intent)
        registry = ExecutionRegistry()
        registry._by_execution_id[rec.execution_id] = rec

        service = ReconciliationService()
        recon = await service.reconcile(rec, strategy=_ConfirmedNotExecutedStrategy())
        registry.set_reconciliation(rec.execution_id, recon)

        assert rec.outcome == ExecutionOutcome.UNKNOWN
        assert rec.effective_status == "effectively_not_executed"


# ── Section 13m: ExecutionRegistry.begin() with intent ───────────────────────


class TestExecutionRegistryBeginWithIntent:
    def test_begin_stores_intent(self):
        registry = ExecutionRegistry()
        intent = _make_intent()
        result = registry.begin(
            "exec-A", "idem-A", "warehouse.labor.allocate", "prop-A", intent=intent
        )
        assert result is None
        stored = registry.get_by_execution_id("exec-A")
        assert stored is not None
        assert stored.intent is intent

    def test_begin_without_intent_stores_none(self):
        registry = ExecutionRegistry()
        registry.begin("exec-B", "idem-B", "warehouse.labor.allocate", "prop-B")
        stored = registry.get_by_execution_id("exec-B")
        assert stored.intent is None

    def test_duplicate_returns_existing_with_original_intent(self):
        registry = ExecutionRegistry()
        intent = _make_intent()
        registry.begin(
            "exec-C", "idem-C", "warehouse.labor.allocate", "prop-C", intent=intent
        )
        existing = registry.begin(
            "exec-C", "idem-C", "warehouse.labor.allocate", "prop-C"
        )
        assert existing is not None
        assert existing.intent is intent


# ── Section 13n: ExecutionRegistry.set_reconciliation() — happy path ─────────


class TestExecutionRegistrySetReconciliation:
    def test_sets_reconciliation_on_unknown_record(self):
        registry = ExecutionRegistry()
        rec = _make_record()
        registry._by_execution_id[rec.execution_id] = rec
        registry.mark_unknown(rec.execution_id)

        recon = ReconciliationRecord(outcome=ReconciliationOutcome.CONFIRMED_EXECUTED)
        registry.set_reconciliation(rec.execution_id, recon)
        assert rec.reconciliation is recon

    def test_effective_status_after_set(self):
        registry = ExecutionRegistry()
        rec = _make_record()
        registry._by_execution_id[rec.execution_id] = rec
        registry.mark_unknown(rec.execution_id)

        recon = ReconciliationRecord(
            outcome=ReconciliationOutcome.CONFIRMED_NOT_EXECUTED
        )
        registry.set_reconciliation(rec.execution_id, recon)
        assert rec.effective_status == "effectively_not_executed"


# ── Section 13o: set_reconciliation() unknown execution_id warns ─────────────


class TestExecutionRegistrySetReconciliationUnknownId:
    def test_unknown_execution_id_does_not_raise(self, caplog):
        registry = ExecutionRegistry()
        recon = ReconciliationRecord()
        with caplog.at_level(logging.WARNING, logger="maiw_execution.registry"):
            registry.set_reconciliation("no-such-id", recon)
        assert "no-such-id" in caplog.text or "unknown" in caplog.text.lower()


# ── Section 13p: set_reconciliation() non-UNKNOWN warns but stores ────────────


class TestExecutionRegistrySetReconciliationNonUnknown:
    def test_non_unknown_warns_but_stores(self, caplog):
        registry = ExecutionRegistry()
        rec = _make_record(outcome=ExecutionOutcome.EXECUTED)
        registry._by_execution_id[rec.execution_id] = rec
        recon = ReconciliationRecord(outcome=ReconciliationOutcome.CONFIRMED_EXECUTED)
        with caplog.at_level(logging.WARNING, logger="maiw_execution.registry"):
            registry.set_reconciliation(rec.execution_id, recon)
        # Should warn but still store
        assert rec.reconciliation is recon


# ── Section 13q: effective_status computed property — all branches ────────────


class TestEffectiveStatusProperty:
    def test_in_progress(self):
        rec = _make_record(outcome=None)
        assert rec.effective_status == "in_progress"

    def test_unknown_no_reconciliation(self):
        rec = _make_record(outcome=ExecutionOutcome.UNKNOWN)
        assert rec.effective_status == "unknown"

    def test_unknown_confirmed_executed(self):
        rec = _make_record(outcome=ExecutionOutcome.UNKNOWN)
        rec.reconciliation = ReconciliationRecord(
            outcome=ReconciliationOutcome.CONFIRMED_EXECUTED
        )
        assert rec.effective_status == "effectively_executed"

    def test_unknown_confirmed_not_executed(self):
        rec = _make_record(outcome=ExecutionOutcome.UNKNOWN)
        rec.reconciliation = ReconciliationRecord(
            outcome=ReconciliationOutcome.CONFIRMED_NOT_EXECUTED
        )
        assert rec.effective_status == "effectively_not_executed"

    def test_unknown_indeterminate_stays_unknown(self):
        rec = _make_record(outcome=ExecutionOutcome.UNKNOWN)
        rec.reconciliation = ReconciliationRecord(
            outcome=ReconciliationOutcome.INDETERMINATE
        )
        assert rec.effective_status == "unknown"

    def test_executed(self):
        rec = _make_record(outcome=ExecutionOutcome.EXECUTED)
        assert rec.effective_status == "executed"

    def test_failed(self):
        rec = _make_record(outcome=ExecutionOutcome.FAILED)
        assert rec.effective_status == "failed"

    def test_no_op(self):
        rec = _make_record(outcome=ExecutionOutcome.NO_OP)
        assert rec.effective_status == "no_op"


# ── Section 13r: BaseActionExecutor._build_intent() base implementation ───────


class TestBaseActionExecutorBuildIntent:
    def _make_proposal_and_decision(self, capability: str = "warehouse.labor.allocate"):
        from unittest.mock import MagicMock

        proposal = MagicMock()
        proposal.action = capability
        proposal.proposal_id = "prop-base"
        proposal.parameters = {"warehouse_id": "DC-1", "task_id": "t1"}
        proposal.idempotency_key = "idem-base"
        decision = MagicMock()
        decision.result_id = "dec-base"
        return proposal, decision

    def test_base_build_intent_capability(self):
        from maiw_execution.base import BaseActionExecutor

        executor = BaseActionExecutor.__new__(BaseActionExecutor)
        proposal, decision = self._make_proposal_and_decision()
        intent = executor._build_intent(proposal, decision, trace_id="t1")
        assert intent.capability == "warehouse.labor.allocate"
        assert intent.proposal_id == "prop-base"
        assert intent.decision_id == "dec-base"
        assert intent.warehouse_id == "DC-1"
        assert intent.idempotency_key == "idem-base"
        assert intent.trace_id == "t1"

    def test_base_build_intent_empty_expected_effect(self):
        from maiw_execution.base import BaseActionExecutor

        executor = BaseActionExecutor.__new__(BaseActionExecutor)
        proposal, decision = self._make_proposal_and_decision()
        intent = executor._build_intent(proposal, decision)
        assert intent.expected_effect == {}


# ── Section 13s: LaborActionExecutor._build_intent() ─────────────────────────


class TestLaborBuildIntent:
    def _make_labor_proposal(self):
        proposal = MagicMock()
        proposal.action = "warehouse.labor.allocate"
        proposal.proposal_id = "prop-labor"
        proposal.parameters = {
            "warehouse_id": "DC-2",
            "task_id": "task-lab-1",
            "worker_ids": ["w1", "w2"],
        }
        proposal.idempotency_key = "idem-lab"
        decision = MagicMock()
        decision.result_id = "dec-lab"
        return proposal, decision

    def test_labor_intent_target_is_task_id(self):
        from maiw_execution.labor import LaborActionExecutor

        executor = LaborActionExecutor.__new__(LaborActionExecutor)
        proposal, decision = self._make_labor_proposal()
        intent = executor._build_intent(proposal, decision, trace_id="tl")
        assert intent.target == "task-lab-1"

    def test_labor_intent_expected_effect(self):
        from maiw_execution.labor import LaborActionExecutor

        executor = LaborActionExecutor.__new__(LaborActionExecutor)
        proposal, decision = self._make_labor_proposal()
        intent = executor._build_intent(proposal, decision)
        assert intent.expected_effect["task_id"] == "task-lab-1"
        assert intent.expected_effect["expected_worker_ids"] == ["w1", "w2"]
        assert intent.expected_effect["expected_task_status"] == "in_progress"


# ── Section 13t: EquipmentActionExecutor._build_intent() ─────────────────────


class TestEquipmentBuildIntent:
    def _make_eq_proposal(self, action: str, params: dict):
        proposal = MagicMock()
        proposal.action = action
        proposal.proposal_id = "prop-eq"
        proposal.parameters = params
        proposal.idempotency_key = "idem-eq"
        decision = MagicMock()
        decision.result_id = "dec-eq"
        return proposal, decision

    def test_assign_intent_expected_status(self):
        from maiw_execution.equipment import EquipmentActionExecutor

        executor = EquipmentActionExecutor.__new__(EquipmentActionExecutor)
        proposal, decision = self._make_eq_proposal(
            "warehouse.equipment.assign",
            {"asset_id": "asset-1", "assignee": "ops-agent", "warehouse_id": "DC-3"},
        )
        intent = executor._build_intent(proposal, decision)
        assert intent.target == "asset-1"
        assert intent.expected_effect["expected_status"] == "assigned"
        assert intent.expected_effect["expected_assignee"] == "ops-agent"

    def test_release_intent_expected_status(self):
        from maiw_execution.equipment import EquipmentActionExecutor

        executor = EquipmentActionExecutor.__new__(EquipmentActionExecutor)
        proposal, decision = self._make_eq_proposal(
            "warehouse.equipment.release",
            {"asset_id": "asset-2", "warehouse_id": "DC-3"},
        )
        intent = executor._build_intent(proposal, decision)
        assert intent.expected_effect["expected_status"] == "available"

    def test_maintenance_intent_expected_status(self):
        from maiw_execution.equipment import EquipmentActionExecutor

        executor = EquipmentActionExecutor.__new__(EquipmentActionExecutor)
        proposal, decision = self._make_eq_proposal(
            "warehouse.equipment.schedule_maintenance",
            {"asset_id": "asset-3", "warehouse_id": "DC-3"},
        )
        intent = executor._build_intent(proposal, decision)
        assert intent.expected_effect["expected_status"] == "maintenance"


# ── Section 13u: WaveActionExecutor._build_intent() ──────────────────────────


class TestWaveBuildIntent:
    def _make_wave_proposal(self, wave_id=None, zone=None):
        proposal = MagicMock()
        proposal.action = "warehouse.wave.reprioritize"
        proposal.proposal_id = "prop-wave"
        proposal.parameters = {
            "warehouse_id": "DC-4",
            "wave_id": wave_id,
            "zone": zone,
            "new_priority": "high",
        }
        proposal.idempotency_key = "idem-wave"
        decision = MagicMock()
        decision.result_id = "dec-wave"
        return proposal, decision

    def test_wave_intent_wave_id_target(self):
        from maiw_execution.wave import WaveActionExecutor

        executor = WaveActionExecutor.__new__(WaveActionExecutor)
        proposal, decision = self._make_wave_proposal(wave_id="wave-7")
        intent = executor._build_intent(proposal, decision)
        assert intent.target == "wave-7"
        assert intent.expected_effect["wave_id"] == "wave-7"
        assert intent.expected_effect["expected_priority"] == "high"

    def test_wave_intent_zone_target(self):
        from maiw_execution.wave import WaveActionExecutor

        executor = WaveActionExecutor.__new__(WaveActionExecutor)
        proposal, decision = self._make_wave_proposal(zone="zone_A")
        intent = executor._build_intent(proposal, decision)
        assert intent.target == "zone_A"
        assert intent.expected_effect["zone"] == "zone_A"


# ── Section 13v: ReconciliationStrategy Protocol structural check ──────────────


class TestReconciliationStrategyProtocol:
    def test_confirmed_executed_satisfies_protocol(self):
        assert isinstance(_ConfirmedExecutedStrategy(), ReconciliationStrategy)

    def test_confirmed_not_executed_satisfies_protocol(self):
        assert isinstance(_ConfirmedNotExecutedStrategy(), ReconciliationStrategy)

    def test_indeterminate_satisfies_protocol(self):
        assert isinstance(_IndeterminateStrategy(), ReconciliationStrategy)

    def test_class_without_methods_does_not_satisfy(self):
        class NotAStrategy:
            pass

        assert not isinstance(NotAStrategy(), ReconciliationStrategy)


# ── Section 13w: Audit trail ─────────────────────────────────────────────────


class TestAuditTrail:
    @pytest.mark.asyncio
    async def test_reconciliation_id_is_unique(self):
        intent = _make_intent()
        rec1 = _make_record("exec-R1", intent=intent)
        rec2 = _make_record(
            "exec-R2", intent=_make_intent(proposal_id="prop-R2", decision_id="dec-R2")
        )
        service = ReconciliationService()
        r1 = await service.reconcile(rec1, strategy=_ConfirmedExecutedStrategy())
        r2 = await service.reconcile(rec2, strategy=_ConfirmedExecutedStrategy())
        assert r1.reconciliation_id != r2.reconciliation_id

    @pytest.mark.asyncio
    async def test_evidence_contains_authoritative_state(self):
        intent = _make_intent()
        rec = _make_record(intent=intent)
        service = ReconciliationService()
        result = await service.reconcile(rec, strategy=_ConfirmedExecutedStrategy())
        assert result.evidence.get("allocations") is not None

    @pytest.mark.asyncio
    async def test_trace_id_propagated_to_record(self):
        intent = _make_intent()
        rec = _make_record(intent=intent)
        service = ReconciliationService()
        result = await service.reconcile(
            rec, strategy=_ConfirmedExecutedStrategy(), trace_id="audit-trace-001"
        )
        assert result.trace_id == "audit-trace-001"


# ── Section 13x: Structured log events (smoke test) ─────────────────────────


class TestStructuredLogEvents:
    @pytest.mark.asyncio
    async def test_started_log_emitted(self, caplog):
        intent = _make_intent()
        rec = _make_record(intent=intent)
        service = ReconciliationService()
        with caplog.at_level(logging.INFO, logger="maiw_execution.reconciliation"):
            await service.reconcile(
                rec, strategy=_ConfirmedExecutedStrategy(), trace_id="log-t1"
            )
        assert "reconciliation.started" in caplog.text

    @pytest.mark.asyncio
    async def test_outcome_log_emitted(self, caplog):
        intent = _make_intent()
        rec = _make_record(intent=intent)
        service = ReconciliationService()
        with caplog.at_level(logging.INFO, logger="maiw_execution.reconciliation"):
            await service.reconcile(
                rec, strategy=_ConfirmedExecutedStrategy(), trace_id="log-t2"
            )
        assert "reconciliation.confirmed_executed" in caplog.text

    @pytest.mark.asyncio
    async def test_indeterminate_no_intent_log_emitted(self, caplog):
        rec = _make_record(intent=None)
        service = ReconciliationService()
        with caplog.at_level(logging.WARNING, logger="maiw_execution.reconciliation"):
            await service.reconcile(
                rec, strategy=_ConfirmedExecutedStrategy(), trace_id="log-t3"
            )
        assert "reconciliation.indeterminate" in caplog.text
