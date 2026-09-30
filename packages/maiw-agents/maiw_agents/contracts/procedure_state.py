# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW SOP Engine V2 — procedure execution state.

``ProcedureExecutionState`` is the SOP Engine's own lifecycle record for one
run of one SOP. It is deliberately separate from ``AgentTaskState``:

    AgentTaskState          — the agent's task (what the operator sees)
    ProcedureExecutionState — the procedure's progression (which step, which
                              attempt, what evidence, what branch history)

They are linked by ``agent_task_id`` and ``trace_id`` rather than merged, so
the SOP Engine stays runtime-neutral and the existing task contract is
untouched.

The model is immutable in practice: the engine advances it with
``model_copy(update=...)`` so every transition produces a new value that can be
snapshotted, logged, or persisted without aliasing.

Persistence is out of scope for the V2 foundation — this is an in-memory
value type. See docs/architecture/SOP_ENGINE_V2_DESIGN.md Section 54.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from .step_result import EvidenceRef, StepResult


# ── Procedure status ──────────────────────────────────────────────────────────

class ProcedureStatus(str, Enum):
    """Terminal and non-terminal states of a procedure run."""

    RUNNING = "running"
    WAITING_FOR_GOVERNANCE = "waiting_for_governance"
    COMPLETED = "completed"
    ESCALATED = "escalated"
    FAILED = "failed"


# ── Procedure execution state ─────────────────────────────────────────────────

class ProcedureExecutionState(BaseModel):
    """
    The SOP Engine's record of one procedure execution.

    Identity: ``procedure_execution_id`` is a fresh UUID4 per run. It is a
    distinct identifier from the agent task id, the trace id, the proposal id
    and the execution id — all of which it references rather than reuses.
    """

    procedure_execution_id: str = Field(description="UUID4, unique per procedure run.")
    sop_id: str
    sop_version: str
    agent_task_id: str
    trace_id: str

    current_step_id: str | None = Field(
        default=None,
        description="Step awaiting execution. None once the procedure is finished.",
    )
    completed_step_ids: list[str] = Field(default_factory=list)
    attempt_by_step: dict[str, int] = Field(
        default_factory=dict,
        description="step_id → number of attempts made so far.",
    )
    step_results: dict[str, StepResult] = Field(
        default_factory=dict,
        description="step_id → most recent StepResult for that step.",
    )
    evidence_refs: list[EvidenceRef] = Field(
        default_factory=list,
        description="Evidence accumulated across every step, in observation order.",
    )

    # ── Bounded loop bookkeeping ──────────────────────────────────────────────
    # The iteration counter for a looping step is ``attempt_by_step`` — a loop
    # step may not declare a retry_policy, so its attempt count and its
    # iteration count are the same number by construction. The two fields below
    # carry only what ``attempt_by_step`` cannot express.

    loop_started_at: dict[str, datetime] = Field(
        default_factory=dict,
        description=(
            "step_id → when the engine first entered that looping step. The "
            "origin for LoopPolicy.max_total_seconds, which spans iterations."
        ),
    )
    loop_exhausted_step_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Looping steps whose budget ran out without the completion criterion "
            "holding. Non-empty means the procedure terminates as ESCALATED even "
            "if a downstream escalation-handling step ran cleanly — reaching the "
            "exhaustion branch is never a success."
        ),
    )

    status: ProcedureStatus
    branch_history: list[str] = Field(
        default_factory=list,
        description="step_ids in the order they were traversed, including skipped steps.",
    )

    started_at: datetime
    last_updated_at: datetime

    def next_attempt(self, step_id: str) -> int:
        """Return the attempt number the next execution of ``step_id`` would be."""
        return self.attempt_by_step.get(step_id, 0) + 1

    def loop_iterations(self, step_id: str) -> int:
        """
        Iterations of ``step_id`` completed so far.

        Identical to the attempt count: a looping step is forbidden from also
        declaring a retry_policy precisely so these two numbers cannot diverge.
        """
        return self.attempt_by_step.get(step_id, 0)


__all__ = [
    "ProcedureStatus",
    "ProcedureExecutionState",
]
