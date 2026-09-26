# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW SOP Engine V2 — typed per-step execution result.

This is the contract every runtime returns from ``SOPStepExecutor.execute_step()``
and the only thing a validator is allowed to inspect. It replaces the V1
approach of "the runtime advanced, therefore the step is done".

Naming note:
    ``contracts/task.py`` also defines a ``StepResult``/``StepStatus`` pair from
    Phase 18H. Those are the *V1* models; they have no consumers in the codebase
    but remain exported from ``maiw_agents.contracts`` for backward
    compatibility. The V2 models in this module are exported from
    ``maiw_agents.contracts`` as ``StepResultV2``/``StepStatusV2`` and from the
    ``maiw_agents`` package root as ``StepResult``/``StepStatus``.

Hard invariant:
    ``StepResult.output`` must never carry chain-of-thought. Evidence is
    structured references, not raw model reasoning. Enforced by a validator on
    the model itself, so violations fail loudly at construction time rather
    than leaking into the audit trail.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .sop_v2 import EscalationReasonCode, ValidatorType


# ── Step lifecycle ────────────────────────────────────────────────────────────

class StepStatus(str, Enum):
    """Lifecycle of a single SOP step execution."""

    PENDING = "pending"
    RUNNING = "running"
    VALIDATING = "validating"
    COMPLETED = "completed"
    RETRY = "retry"
    ESCALATED = "escalated"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    WAITING_FOR_GOVERNANCE = "waiting_for_governance"


# ── Evidence ──────────────────────────────────────────────────────────────────

class EvidenceRef(BaseModel):
    """
    A structured pointer to something that was observed.

    Evidence is a *reference plus a summary*, never a transcript. This keeps the
    audit trail reviewable and keeps model reasoning out of operational records.
    """

    type: str = Field(
        description="Evidence kind, e.g. 'capability_result', 'state_snapshot', 'validator_result'."
    )
    source: str = Field(
        description="Where it came from: capability_id, agent_id, validator_type, etc."
    )
    reference_id: str | None = Field(
        default=None,
        description="Linking id: trace_id, execution_id, context_snapshot_id, etc.",
    )
    timestamp: datetime
    summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Validation outcome ────────────────────────────────────────────────────────

class ValidationResult(BaseModel):
    """
    The verdict of a StepValidator.

    ``retryable=False`` is how a validator says "re-running this step cannot
    help" — e.g. an unregistered predicate, or a policy conflict. The engine
    honours it and stops burning the retry budget.
    """

    valid: bool
    validator_type: ValidatorType
    reason: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    retryable: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Step result ───────────────────────────────────────────────────────────────

# Keys that must never appear in a step's structured output.
_BANNED_OUTPUT_KEYS = frozenset({
    "chain_of_thought",
    "scratchpad",
    "hidden_reasoning",
    "raw_reasoning",
    "system_prompt",
})


class StepResult(BaseModel):
    """
    Typed result of executing one SOP step under one runtime.

    The runtime fills in ``output``, ``evidence`` and a provisional ``status``.
    The SOP Engine — not the runtime — decides the final status by running the
    step's validator. A runtime reporting ``status=COMPLETED`` is a *claim*,
    not a completion.
    """

    step_id: str
    status: StepStatus
    output: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured output from the runtime. Never chain-of-thought.",
    )
    evidence: list[EvidenceRef] = Field(default_factory=list)
    runtime: str = Field(
        description="Which executor produced this: 'deterministic', 'deep_agents', or a test name."
    )
    attempt: int = 1
    started_at: datetime
    completed_at: datetime | None = None
    error: str | None = None
    escalation_reason: EscalationReasonCode | None = None
    escalation_message: str | None = None
    validation_result: ValidationResult | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _no_chain_of_thought(self) -> "StepResult":
        found = _BANNED_OUTPUT_KEYS & set(self.output.keys())
        if found:
            raise ValueError(
                f"StepResult.output must not contain chain-of-thought fields: {sorted(found)}"
            )
        return self


__all__ = [
    "StepStatus",
    "EvidenceRef",
    "ValidationResult",
    "StepResult",
]
