# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Test doubles for fault injection scenarios.

All doubles live in this test module — production packages contain none of this.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable
from unittest.mock import AsyncMock, MagicMock

from maiw_execution.base import (
    ActionConflict,
    BaseActionExecutor,
    ActionExecutionResult,
)
from maiw_execution.outcome import ExecutionOutcome
from maiw_execution.registry import ExecutionRegistry

# ---------------------------------------------------------------------------
# FakeClock — injectable monotonic clock for time-based tests
# ---------------------------------------------------------------------------


class FakeClock:
    def __init__(self, t: float = 0.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


# ---------------------------------------------------------------------------
# MinimalTestExecutor — parameterizable executor for fault scenario tests
# ---------------------------------------------------------------------------

_TEST_ACTION = "test.action.execute"


class MinimalTestExecutor(BaseActionExecutor):
    """
    Minimal executor for testing BaseActionExecutor guard behaviour.

    Configure _do_execute_fn to simulate different outcomes:
        - None (default) → EXECUTED
        - raises AmbiguousWriteError → UNKNOWN (F06 hero fault)
        - raises RuntimeError → FAILED (F05 write before mutation)
        - raises ActionConflict → blocked by guard 5 (F10 state drift)
    """

    _ALLOWED_ACTIONS: frozenset = frozenset([_TEST_ACTION])

    def __init__(
        self,
        do_execute_fn: Callable | None = None,
        check_guards_fn: Callable | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._do_execute_fn = do_execute_fn
        self._check_guards_fn = check_guards_fn

    async def _do_execute(
        self,
        proposal,
        decision,
        execution_id: str,
    ):
        if self._do_execute_fn is not None:
            return await self._do_execute_fn(proposal, decision, execution_id)
        return {"status": "ok"}, "ref-001", ExecutionOutcome.EXECUTED

    async def _check_additional_guards(self, proposal) -> None:
        if self._check_guards_fn is not None:
            await self._check_guards_fn(proposal)


# ---------------------------------------------------------------------------
# make_test_proposal — minimal ActionProposal for testing
# ---------------------------------------------------------------------------


def make_test_proposal(
    action: str = _TEST_ACTION,
    proposal_id: str | None = None,
    idempotency_key: str | None = None,
    risk_level: str = "low",
    domain: str = "test",
) -> Any:
    """Build a minimal ActionProposal stub for executor tests."""
    from maiw_mcp.contracts.actions import ActionProposal, RiskLevel

    return ActionProposal(
        proposal_id=proposal_id or str(uuid.uuid4()),
        action=action,
        domain=domain,
        reason="Test proposal",
        risk_level=RiskLevel(risk_level),
        idempotency_key=idempotency_key or str(uuid.uuid4()),
        parameters={},
    )


# ---------------------------------------------------------------------------
# make_approved_decision — APPROVED DecisionResult for testing
# ---------------------------------------------------------------------------


def make_approved_decision(
    proposal_id: str,
    evaluated_at: datetime | None = None,
) -> Any:
    """Build a minimal APPROVED DecisionResult for executor tests."""
    from maiw_decision.models import DecisionOutcome, DecisionResult

    return DecisionResult(
        result_id=str(uuid.uuid4()),
        request_id=str(uuid.uuid4()),
        proposal_id=proposal_id,
        outcome=DecisionOutcome.APPROVED,
        violations=[],
        evaluated_at=evaluated_at or datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# make_test_snapshot — minimal WarehouseStateSnapshot for decision engine tests
# ---------------------------------------------------------------------------


def make_test_snapshot(warehouse_id: str = "wh-test") -> Any:
    """Build a minimal WarehouseStateSnapshot stub for engine tests."""
    snap = MagicMock()
    snap.warehouse_id = warehouse_id
    snap.snapshot_id = str(uuid.uuid4())
    snap.state = MagicMock()
    snap.state.equipment = None
    snap.state.labor = None
    snap.state.waves = None
    return snap


# ---------------------------------------------------------------------------
# StubNIMProvider — fake NIM provider that raises configured exceptions
# ---------------------------------------------------------------------------


class StubNIMProvider:
    """
    Fake NIM provider for ModelGateway fault injection tests.

    Does not call any real NIM endpoint. Returns a stub LLMResponse
    or raises a configured exception to simulate NIM faults.
    """

    def __init__(
        self,
        raises: Exception | None = None,
        response_text: str = "stub response",
    ) -> None:
        self._raises = raises
        self._response_text = response_text

    async def call(self, *, model_id: str, request: Any, capability: Any) -> Any:
        if self._raises is not None:
            raise self._raises
        stub = MagicMock()
        stub.content = self._response_text
        stub.model = model_id
        stub.finish_reason = "stop"
        stub.usage = MagicMock()
        stub.usage.prompt_tokens = 10
        stub.usage.completion_tokens = 5
        stub.usage.total_tokens = 15
        return stub
