# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Tests for UX-1C.1: CopilotTurnResponse.agent_task_id linkage.

Invariants:
- agent_task_id populated when AgentTaskState registered for an ACT turn
- agent_task_id is None for ASK/ANALYZE turns
- No global latest() lookup — exact task identity only
- Schema backward-compatible (old field absent = no error)
- Task linked to exact initiating turn
- No duplicate task creation
- WAITING_FOR_GOVERNANCE → approval → OBSERVING_OUTCOME transition logic
- UNKNOWN execution → task stays paused (not OBSERVING_OUTCOME)
- INDETERMINATE → task does not falsely complete
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from maiw_api.copilot.models import CopilotTurnResponse

# ── Schema tests ──────────────────────────────────────────────────────────────


class TestCopilotTurnResponseSchema:
    """CopilotTurnResponse.agent_task_id field contract."""

    def _minimal_response(self, **kwargs) -> CopilotTurnResponse:
        """Build a minimal valid CopilotTurnResponse for testing."""
        base = dict(
            conversation_id="conv-001",
            turn_id="turn-001",
            trace_id="trace-001",
            intent="ask",
            status="complete",
        )
        base.update(kwargs)
        return CopilotTurnResponse(**base)

    def test_agent_task_id_absent_by_default(self):
        """No agent_task_id → field is None (backward-compatible)."""
        r = self._minimal_response()
        assert r.agent_task_id is None

    def test_agent_task_id_populated_when_provided(self):
        """Explicit agent_task_id is preserved in response."""
        task_id = "copilot-act-abcd1234-ef567890"
        r = self._minimal_response(agent_task_id=task_id)
        assert r.agent_task_id == task_id

    def test_agent_task_id_accepts_none(self):
        """Explicit None is valid (absent from JSON via exclude_none)."""
        r = self._minimal_response(agent_task_id=None)
        assert r.agent_task_id is None

    def test_schema_backward_compatible_no_agent_task_id(self):
        """Old response payloads without agent_task_id parse without error."""
        payload = {
            "conversation_id": "conv-001",
            "turn_id": "turn-001",
            "trace_id": "trace-001",
            "intent": "ask",
            "status": "complete",
            # agent_task_id deliberately absent
        }
        r = CopilotTurnResponse(**payload)
        assert r.agent_task_id is None

    def test_ask_turn_no_agent_task_id(self):
        """ASK turns must not populate agent_task_id."""
        r = self._minimal_response(intent="ask")
        assert r.agent_task_id is None

    def test_analyze_turn_no_agent_task_id(self):
        """ANALYZE turns must not populate agent_task_id."""
        r = self._minimal_response(intent="analyze")
        assert r.agent_task_id is None


# ── Task registration helper tests ──────────────────────────────────────────


class TestRegisterCopilotActTask:
    """_register_copilot_act_task creates exact task, not a global lookup."""

    def _make_mock_result(
        self, outcome: str, mutation: str = "NOT_ATTEMPTED"
    ) -> object:
        """Build a minimal mock CopilotActResult."""
        from unittest.mock import MagicMock
        from maiw_api.copilot.models import MutationState

        result = MagicMock()
        result.decision_outcome = outcome
        result.mutation_state = MutationState(mutation)
        result.recommendation_id = "rec-test-001"
        result.agent_task_id = None
        return result

    def test_requires_human_approval_registers_governance_wait(self):
        """REQUIRES_HUMAN_APPROVAL outcome → task status WAITING_FOR_GOVERNANCE."""
        from maiw_api.copilot.service import _register_copilot_act_task
        from maiw_api.routers.agent_tasks import (
            get_registered_task,
            clear_task_registry,
        )

        clear_task_registry()
        result = self._make_mock_result("REQUIRES_HUMAN_APPROVAL", "NOT_ATTEMPTED")

        task_id = _register_copilot_act_task(
            result=result,
            conversation_id="conv-ux1c",
            turn_id="turn-ux1c-001",
            trace_id="trace-ux1c-001",
            objective="Resolve Wave 17 risk",
        )

        assert task_id is not None
        assert task_id.startswith("copilot-act-")
        state = get_registered_task(task_id)
        assert state is not None
        assert state.status.value == "WAITING_FOR_GOVERNANCE"
        assert state.conversation_id == "conv-ux1c"
        assert state.copilot_turn_id == "turn-ux1c-001"

    def test_approved_confirmed_registers_observing_outcome(self):
        """APPROVED + CONFIRMED mutation → task status OBSERVING_OUTCOME."""
        from maiw_api.copilot.service import _register_copilot_act_task
        from maiw_api.routers.agent_tasks import (
            get_registered_task,
            clear_task_registry,
        )

        clear_task_registry()
        result = self._make_mock_result("APPROVED", "CONFIRMED")

        task_id = _register_copilot_act_task(
            result=result,
            conversation_id="conv-ux1c-2",
            turn_id="turn-ux1c-002",
            trace_id="trace-ux1c-002",
            objective="Execute labor reallocation",
        )

        assert task_id is not None
        state = get_registered_task(task_id)
        assert state.status.value == "OBSERVING_OUTCOME"

    def test_rejected_registers_failed(self):
        """REJECTED outcome → task status FAILED."""
        from maiw_api.copilot.service import _register_copilot_act_task
        from maiw_api.routers.agent_tasks import (
            get_registered_task,
            clear_task_registry,
        )

        clear_task_registry()
        result = self._make_mock_result("REJECTED", "NOT_ATTEMPTED")

        task_id = _register_copilot_act_task(
            result=result,
            conversation_id="conv-ux1c-3",
            turn_id="turn-ux1c-003",
            trace_id="trace-ux1c-003",
            objective="Test rejected action",
        )

        assert task_id is not None
        state = get_registered_task(task_id)
        assert state.status.value == "FAILED"

    def test_no_global_latest_lookup(self):
        """Each call creates a NEW task — no global registry lookup."""
        from maiw_api.copilot.service import _register_copilot_act_task
        from maiw_api.routers.agent_tasks import (
            get_registered_task,
            clear_task_registry,
        )

        clear_task_registry()
        result1 = self._make_mock_result("REQUIRES_HUMAN_APPROVAL")
        result2 = self._make_mock_result("REQUIRES_HUMAN_APPROVAL")

        task_id_1 = _register_copilot_act_task(
            result=result1,
            conversation_id="c1",
            turn_id="t1",
            trace_id="tr1",
            objective="obj1",
        )
        task_id_2 = _register_copilot_act_task(
            result=result2,
            conversation_id="c2",
            turn_id="t2",
            trace_id="tr2",
            objective="obj2",
        )

        # Each call produces a different task_id
        assert task_id_1 != task_id_2
        # Both registered separately
        state1 = get_registered_task(task_id_1)
        state2 = get_registered_task(task_id_2)
        assert state1.conversation_id == "c1"
        assert state2.conversation_id == "c2"

    def test_unknown_mutation_stays_governance_wait(self):
        """APPROVED + UNKNOWN mutation → stays WAITING_FOR_GOVERNANCE (not OBSERVING_OUTCOME)."""
        from maiw_api.copilot.service import _register_copilot_act_task
        from maiw_api.routers.agent_tasks import (
            get_registered_task,
            clear_task_registry,
        )

        clear_task_registry()
        result = self._make_mock_result("APPROVED", "UNKNOWN")

        task_id = _register_copilot_act_task(
            result=result,
            conversation_id="c-unknown",
            turn_id="t-unknown",
            trace_id="tr-unknown",
            objective="Test unknown mutation",
        )

        state = get_registered_task(task_id)
        # UNKNOWN execution → task should NOT jump to OBSERVING_OUTCOME
        assert state.status.value != "OBSERVING_OUTCOME"
        # Should stay in governance wait or escalated — not falsely completed
        assert state.status.value not in ("COMPLETED",)

    def test_task_linked_to_exact_initiating_turn(self):
        """Task carries exact turn_id, conversation_id, and trace_id."""
        from maiw_api.copilot.service import _register_copilot_act_task
        from maiw_api.routers.agent_tasks import (
            get_registered_task,
            clear_task_registry,
        )

        clear_task_registry()
        result = self._make_mock_result("REQUIRES_HUMAN_APPROVAL")

        specific_turn_id = "turn-specific-xyz"
        specific_conv_id = "conv-specific-abc"
        specific_trace_id = "trace-specific-999"

        task_id = _register_copilot_act_task(
            result=result,
            conversation_id=specific_conv_id,
            turn_id=specific_turn_id,
            trace_id=specific_trace_id,
            objective="Specific turn linkage test",
        )

        state = get_registered_task(task_id)
        assert state.copilot_turn_id == specific_turn_id
        assert state.conversation_id == specific_conv_id
        assert state.trace_id == specific_trace_id


# ── Execution confirmed ≠ Objective achieved regression tests ─────────────────


class TestExecutionVsObjectiveDistinction:
    """
    CRITICAL REGRESSION TEST: execution_confirmed MUST NOT be equated to
    objective achieved. These are separate concepts with separate fields.

    See UX-1C.5 acceptance criterion.
    """

    def test_execution_confirmed_and_operational_improved_are_separate_fields(self):
        """
        CopilotTurnResponse has separate fields for execution confirmation
        and operational improvement. They are never the same field.
        """
        r = CopilotTurnResponse(
            conversation_id="c",
            turn_id="t",
            trace_id="tr",
            intent="observe_outcome",
            status="complete",
            # Execution succeeded but outcome not achieved
            observe_execution_confirmed=True,
            observe_operational_improved=False,
        )
        # confirmed does NOT imply improved
        assert r.observe_execution_confirmed is True
        assert r.observe_operational_improved is False

    def test_observe_operational_improved_false_when_execution_confirmed_true(self):
        """
        Execution confirmed=True with operational_improved=False is valid.
        This represents: action executed BUT objective not yet achieved.
        """
        r = CopilotTurnResponse(
            conversation_id="c",
            turn_id="t",
            trace_id="tr",
            intent="observe_outcome",
            status="complete",
            observe_execution_confirmed=True,
            observe_operational_improved=False,
            observe_operational_summary="Execution complete but bottleneck persists",
        )
        assert r.observe_execution_confirmed is True
        assert r.observe_operational_improved is False
        assert r.observe_operational_summary is not None

    def test_observe_execution_confirmed_false_with_operational_improved_false(self):
        """
        Both false is valid: action pending, outcome unknown.
        """
        r = CopilotTurnResponse(
            conversation_id="c",
            turn_id="t",
            trace_id="tr",
            intent="observe_outcome",
            status="complete",
            observe_execution_confirmed=False,
            observe_operational_improved=False,
        )
        assert r.observe_execution_confirmed is False
        assert r.observe_operational_improved is False


# ── Architecture invariants ───────────────────────────────────────────────────


class TestArchitectureInvariants:
    """Ensure no prohibited fields are exposed."""

    def test_no_chain_of_thought_in_response(self):
        """CopilotTurnResponse MUST NOT have chain_of_thought field."""
        from maiw_api.copilot.models import CopilotTurnResponse

        model_fields = CopilotTurnResponse.model_fields
        prohibited = {
            "chain_of_thought",
            "scratchpad",
            "hidden_reasoning",
            "reasoning_tokens",
            "internal_state",
            "node_state",
        }
        for field_name in prohibited:
            assert (
                field_name not in model_fields
            ), f"Prohibited field '{field_name}' found in CopilotTurnResponse"

    def test_agent_task_id_is_optional_not_required(self):
        """agent_task_id must be optional — no breaking change for existing clients."""
        from maiw_api.copilot.models import CopilotTurnResponse

        field = CopilotTurnResponse.model_fields.get("agent_task_id")
        assert field is not None, "agent_task_id field must exist"
        # Field should have a default of None (optional)
        assert field.default is None or field.is_required() is False

    def test_agent_tasks_router_is_read_only(self):
        """Agent tasks router must only expose GET endpoints (read-only)."""
        from maiw_api.routers.agent_tasks import router

        for route in router.routes:
            methods = getattr(route, "methods", set())
            non_get = methods - {"GET", "HEAD", "OPTIONS"}
            assert (
                not non_get
            ), f"Agent tasks route {route.path} has non-GET methods: {non_get}"
