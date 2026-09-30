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

Persistence (production hardening): this model is the unit a
``ProcedureStateStore`` saves and loads. Every field below is chosen to be
durable and replayable — see ``revision`` for the concurrency contract and
``maiw_agents.sop_engine.state_store`` for the store protocol.

HARD PROHIBITION — private reasoning must never persist:
    No field on this model may carry chain-of-thought, a scratchpad, hidden or
    raw reasoning, a system prompt, or model-internal private memory. The
    procedure record is an operational audit trail, not a transcript. Enforced
    by ``_BANNED_STATE_FIELDS`` below and by a dedicated test.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .step_result import EvidenceRef, StepResult


# ── Procedure status ──────────────────────────────────────────────────────────

class ProcedureStatus(str, Enum):
    """Terminal and non-terminal states of a procedure run."""

    RUNNING = "running"
    WAITING_FOR_GOVERNANCE = "waiting_for_governance"
    COMPLETED = "completed"
    ESCALATED = "escalated"
    FAILED = "failed"


TERMINAL_PROCEDURE_STATUSES: frozenset[ProcedureStatus] = frozenset({
    ProcedureStatus.COMPLETED,
    ProcedureStatus.ESCALATED,
    ProcedureStatus.FAILED,
})
"""Statuses after which a procedure record may never be mutated again."""


# Field names that must never appear on the persisted procedure record.
_BANNED_STATE_FIELDS = frozenset({
    "chain_of_thought",
    "scratchpad",
    "hidden_reasoning",
    "raw_reasoning",
    "system_prompt",
    "private_memory",
    "model_memory",
})


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

    # ── Persistence bookkeeping ───────────────────────────────────────────────

    revision: int = Field(
        default=0,
        ge=0,
        description=(
            "Optimistic-concurrency counter. Starts at 0 for a state that has "
            "never been stored and is incremented by ProcedureStateStore.save() "
            "on every successful write. A caller passing expected_revision that "
            "does not match the stored value is writing against a stale read and "
            "is rejected with StaleRevisionError."
        ),
    )

    @model_validator(mode="after")
    def _no_private_reasoning(self) -> "ProcedureExecutionState":
        """
        The persisted procedure record must never carry model-internal reasoning.

        This guards against a future field being added carelessly: the check is
        on the model's own field names, so it fires at construction time for
        every instance rather than relying on review to catch it.
        """
        found = _BANNED_STATE_FIELDS & set(type(self).model_fields)
        if found:
            raise ValueError(
                "ProcedureExecutionState must not carry private model reasoning; "
                f"forbidden fields present: {sorted(found)}"
            )
        return self

    def is_terminal(self) -> bool:
        """True once the procedure may no longer advance."""
        return self.status in TERMINAL_PROCEDURE_STATUSES

    def evidence_for_attempt(self, step_id: str, attempt: int) -> list[EvidenceRef]:
        """
        Evidence stamped as belonging to ``step_id`` at exactly ``attempt``.

        Attempt correlation is what stops a failed attempt's evidence from
        silently satisfying a later one: the engine stamps every accumulated
        EvidenceRef with the step and attempt that produced it, and this accessor
        refuses to widen that match.
        """
        return [
            ref
            for ref in self.evidence_refs
            if ref.metadata.get("step_id") == step_id
            and ref.metadata.get("attempt") == attempt
        ]

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
    "TERMINAL_PROCEDURE_STATUSES",
    "ProcedureExecutionState",
]
