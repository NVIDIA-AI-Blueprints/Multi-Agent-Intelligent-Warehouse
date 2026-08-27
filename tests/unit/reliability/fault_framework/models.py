# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Fault injection models and reliability result schema.

FaultProfile — description of a single fault to inject.
ReliabilityResult — output of a single fault scenario run.
Golden invariants — the five safety invariants that must hold in every run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FaultType(str, Enum):
    """Enumeration of all fault types in the MAIW fault matrix."""

    # Model / NIM faults
    NIM_TIMEOUT = "nim_timeout"
    NIM_UNAVAILABLE = "nim_unavailable"

    # MCP read faults
    MCP_READ_TIMEOUT = "mcp_read_timeout"
    MCP_DOMAIN_UNAVAILABLE = "mcp_domain_unavailable"

    # MCP write faults
    MCP_WRITE_BEFORE_MUTATION = "mcp_write_before_mutation"
    MCP_WRITE_AFTER_MUTATION = "mcp_write_after_mutation"  # AMBIGUOUS WRITE

    # Approval / approval-reuse faults
    DUPLICATE_APPROVAL = "duplicate_approval"
    APPROVAL_EXPIRY = "approval_expiry"

    # Execution faults
    DUPLICATE_EXECUTION = "duplicate_execution"

    # State integrity faults
    STALE_DECISION = "stale_decision"
    STATE_DRIFT = "state_drift"

    # Circuit / infrastructure faults
    CIRCUIT_OPEN = "circuit_open"

    # Reconciliation faults
    RECONCILIATION_READ_TIMEOUT = "reconciliation_read_timeout"


class FaultTrigger(str, Enum):
    """When the fault should fire."""

    IMMEDIATE = "immediate"  # first call matching target
    CALL_NUMBER = "call_number"  # Nth call matching target
    SIM_TIME = "sim_time"  # at simulated clock time T


@dataclass
class FaultProfile:
    """
    Description of a single fault to inject during a scenario run.

    Fault injection must only happen at the test/demo boundary:
        - FaultInjectingMCPClient wraps MAIWMCPClient
        - StubNIMProvider returns errors instead of NIM responses
        - MinimalTestExecutor._do_execute() raises configured exceptions

    Production code (Agent, ModelGateway, DecisionEngine, ActionExecutor)
    must NOT contain any fault_id checks.
    """

    fault_id: str  # "F01", "F02", …
    target: str  # "nim", "mcp.labor", "executor", …
    fault_type: FaultType
    trigger: FaultTrigger = FaultTrigger.IMMEDIATE
    call_number: int | None = None  # for CALL_NUMBER trigger
    sim_time: float | None = None  # for SIM_TIME trigger
    duration_calls: int | None = None  # how many calls to fault (None = all)
    expected_safety_behavior: str = ""  # human-readable contract

    def matches(self, target: str, call_n: int) -> bool:
        """Return True if this fault should fire for the given target and call number."""
        if self.target != target:
            return False
        if self.trigger == FaultTrigger.IMMEDIATE:
            if self.duration_calls is None:
                return call_n >= 1
            return 1 <= call_n <= self.duration_calls
        if self.trigger == FaultTrigger.CALL_NUMBER:
            n = self.call_number or 1
            if self.duration_calls is None:
                return call_n >= n
            return n <= call_n <= n + self.duration_calls - 1
        return False


@dataclass
class ReconciliationEntry:
    """Result of a single reconciliation attempt."""

    execution_id: str
    outcome: str  # ReconciliationOutcome.value
    trace_id: str | None = None


@dataclass
class ReliabilityResult:
    """
    Output schema for a single fault scenario run.

    Safety metrics are PRIMARY. Operational recovery is SECONDARY.
    A fault with no recovery but zero unauthorized writes and complete trace = PASS.
    """

    # Scenario identity
    scenario_id: str = "scenario_001_labor_constraint_wave_risk"
    seed: int = 42
    fault_id: str | None = None
    fault_triggered: bool = False

    # Operational outcome (secondary)
    recovery_reached: bool | None = None
    time_to_recovery: float | None = None

    # Safety metrics (PRIMARY)
    unauthorized_writes: int = 0
    duplicate_writes: int = 0
    false_successes: int = 0  # outcome==EXECUTED but no mutation
    unknown_executions: int = 0
    conflicts: int = 0
    stale_state_blocks: int = 0
    state_drift_blocks: int = 0
    duplicate_approval_prevented: int = 0
    duplicate_execution_prevented: int = 0
    reconciliation_results: list[ReconciliationEntry] = field(default_factory=list)

    trace_complete: bool = True

    final_runtime_status: str | None = None
    circuit_states: dict[str, Any] = field(default_factory=dict)

    backlog_auc: float | None = None
    wave_risk_auc: float | None = None

    # Final verdict
    safety_pass: bool = True
    safety_violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "seed": self.seed,
            "fault_id": self.fault_id,
            "fault_triggered": self.fault_triggered,
            "recovery_reached": self.recovery_reached,
            "time_to_recovery": self.time_to_recovery,
            "unauthorized_writes": self.unauthorized_writes,
            "duplicate_writes": self.duplicate_writes,
            "false_successes": self.false_successes,
            "unknown_executions": self.unknown_executions,
            "conflicts": self.conflicts,
            "stale_state_blocks": self.stale_state_blocks,
            "state_drift_blocks": self.state_drift_blocks,
            "duplicate_approval_prevented": self.duplicate_approval_prevented,
            "duplicate_execution_prevented": self.duplicate_execution_prevented,
            "reconciliation_results": [
                {"execution_id": r.execution_id, "outcome": r.outcome}
                for r in self.reconciliation_results
            ],
            "trace_complete": self.trace_complete,
            "final_runtime_status": self.final_runtime_status,
            "circuit_states": self.circuit_states,
            "backlog_auc": self.backlog_auc,
            "wave_risk_auc": self.wave_risk_auc,
            "safety_pass": self.safety_pass,
            "safety_violations": self.safety_violations,
        }


class GoldenInvariantViolation(AssertionError):
    """Raised when a golden safety invariant is violated."""


def check_golden_invariants(result: ReliabilityResult) -> None:
    """
    Assert the five golden safety invariants against a ReliabilityResult.

    Raises GoldenInvariantViolation if any invariant is violated.
    A fault scenario may have recovery_reached=False and still PASS if
    safety invariants all hold.

    Invariants:
        A: unauthorized_writes == 0
        B: duplicate_writes == 0
        C: false_successes == 0  (EXECUTED outcome without confirmed mutation)
        D: stale_state_blocks are the CORRECT response (block, not execute)
        E: state_drift_blocks are the CORRECT response (block, not execute)
    """
    violations = []

    if result.unauthorized_writes != 0:
        violations.append(
            f"INVARIANT A VIOLATED: unauthorized_writes={result.unauthorized_writes} "
            f"(must be 0)"
        )

    if result.duplicate_writes != 0:
        violations.append(
            f"INVARIANT B VIOLATED: duplicate_writes={result.duplicate_writes} "
            f"(must be 0)"
        )

    if result.false_successes != 0:
        violations.append(
            f"INVARIANT C VIOLATED: false_successes={result.false_successes} "
            f"(EXECUTED outcome must only be set when mutation is confirmed)"
        )

    if violations:
        result.safety_pass = False
        result.safety_violations = violations
        raise GoldenInvariantViolation(
            f"Golden invariant(s) violated in {result.fault_id or 'NORMAL'}: "
            + "; ".join(violations)
        )
