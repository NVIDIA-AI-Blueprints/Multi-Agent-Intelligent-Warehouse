# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW SOP v2 step-semantics contracts — SOP Engine V2 Foundation.

This module carries the *declarative* half of SOP Engine V2: what it means for
a step to be "done", how many times it may be retried, and the typed vocabulary
used when a step cannot complete.

It deliberately contains NO execution logic and NO imports from any runtime.
``contracts/sop.py`` imports these models to extend ``SOPStep`` with optional
v2 fields; every one of those fields defaults to ``None`` so that v1 SOP YAML
loads and runs without modification.

Governance:
    Nothing in this module may authorize an operational write. A completion
    spec describes *evidence of completion*; it never grants authority.
    See docs/architecture/SOP_ENGINE_V2_DESIGN.md Section 14.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


# ── Validator taxonomy ────────────────────────────────────────────────────────

class ValidatorType(str, Enum):
    """
    How a step's completion is proven.

    Only the four values below are implemented in the V2 foundation.
    MODEL_JUDGE, HUMAN, and COMPOSITE are deliberately deferred — see
    docs/architecture/SOP_ENGINE_V2_DESIGN.md Sections 13 and 15.
    """

    SCHEMA = "schema"
    """Required keys must be present in StepResult.output."""

    STATE_PREDICATE = "state_predicate"
    """A registered, code-defined predicate must hold against authoritative state."""

    CAPABILITY_RESULT = "capability_result"
    """A named capability's structured result must be present in StepResult.output."""

    LEGACY_SUCCESS = "legacy_success"
    """V1 compatibility: the step advances if the runtime returned without failure."""

    # Deferred — NOT implemented in the V2 foundation:
    # HUMAN = "human"
    # MODEL_JUDGE = "model_judge"
    # COMPOSITE = "composite"


# ── Escalation reason codes ───────────────────────────────────────────────────

class EscalationReasonCode(str, Enum):
    """
    Typed escalation vocabulary.

    Replaces free-form model prose so the operator escalation inbox receives
    structured, actionable reasons.
    """

    INVALID_OUTPUT = "invalid_output"
    MISSING_DATA = "missing_data"
    MODEL_FAILURE = "model_failure"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    VALIDATION_FAILED = "validation_failed"
    TIMEOUT = "timeout"
    POLICY_CONFLICT = "policy_conflict"
    EXECUTION_INDETERMINATE = "execution_indeterminate"
    RETRY_BUDGET_EXHAUSTED = "retry_budget_exhausted"
    UNSUPPORTED_VALIDATOR = "unsupported_validator"
    UNSUPPORTED_STRATEGY = "unsupported_strategy"
    """No configured operational strategy can address the situation."""

    LOOP_BUDGET_EXHAUSTED = "loop_budget_exhausted"
    """A bounded reassessment loop ran its full budget without the declared
    completion criterion ever holding. Distinct from RETRY_BUDGET_EXHAUSTED,
    which means a *single* step attempt kept failing: here every attempt ran
    cleanly and the world simply never reached the required state."""


# ── Step completion specification ─────────────────────────────────────────────

class StepCompletionSpec(BaseModel):
    """
    Declares what "done" means for a single SOP step.

    A step with ``completion is None`` keeps V1 behaviour: it is validated by
    the LEGACY_SUCCESS validator and advances whenever the runtime returned
    without reporting failure.
    """

    validator_type: ValidatorType

    # SCHEMA
    schema_fields: list[str] | None = Field(
        default=None,
        description="For SCHEMA: output keys that must be present in StepResult.output.",
    )

    # STATE_PREDICATE
    predicate_name: str | None = Field(
        default=None,
        description=(
            "For STATE_PREDICATE: name of a predicate registered in code via "
            "register_predicate(). Never an expression — no eval() from YAML."
        ),
    )
    predicate_args: dict[str, Any] | None = Field(
        default=None,
        description="For STATE_PREDICATE: arguments passed to the registered predicate.",
    )

    # CAPABILITY_RESULT
    required_capability_result: str | None = Field(
        default=None,
        description="For CAPABILITY_RESULT: capability id whose result must appear in output.",
    )
    required_result_fields: list[str] | None = Field(
        default=None,
        description="For CAPABILITY_RESULT: fields required inside that capability result.",
    )

    @model_validator(mode="after")
    def _check_required_fields_for_type(self) -> "StepCompletionSpec":
        """A completion spec must carry the parameters its validator needs."""
        if self.validator_type is ValidatorType.STATE_PREDICATE and not self.predicate_name:
            raise ValueError(
                "StepCompletionSpec with validator_type=STATE_PREDICATE requires predicate_name."
            )
        if (
            self.validator_type is ValidatorType.CAPABILITY_RESULT
            and not self.required_capability_result
        ):
            raise ValueError(
                "StepCompletionSpec with validator_type=CAPABILITY_RESULT requires "
                "required_capability_result."
            )
        return self


# ── Retry policy ──────────────────────────────────────────────────────────────

# Outcomes that must never be retried blindly: retrying an ambiguous write can
# duplicate a real-world side effect. These require an authoritative re-read.
_NEVER_RETRY = frozenset({
    "WRITE_AMBIGUOUS",
    "EXECUTION_INDETERMINATE",
})


class RetryPolicy(BaseModel):
    """
    Per-step retry budget.

    Hard rule: ambiguous write outcomes are never retried. A write whose
    outcome is unknown must be resolved by reading authoritative state, not by
    issuing the write again.
    """

    max_attempts: int = Field(ge=1, le=10, default=3)
    retry_on: list[str] = Field(
        default_factory=lambda: ["VALIDATION_FAILED", "CAPABILITY_UNAVAILABLE"]
    )
    backoff_seconds: float = Field(ge=0.0, le=30.0, default=1.0)
    escalate_on_exhaustion: bool = True

    @model_validator(mode="after")
    def _no_write_retry(self) -> "RetryPolicy":
        forbidden = {r.upper() for r in self.retry_on} & _NEVER_RETRY
        if forbidden:
            raise ValueError(
                f"Ambiguous write states must not be retried blindly "
                f"(found {sorted(forbidden)} in retry_on) — require authoritative reread."
            )
        return self


# ── Loop policy ───────────────────────────────────────────────────────────────

class LoopPolicy(BaseModel):
    """
    Bounded, validator-driven repetition of ONE SOP step.

    This is deliberately the smallest loop construct that is still useful. It is
    not a control-flow DSL: there is no expression language, no ``while``, no
    ``foreach``, no counter arithmetic and no way for a SOP author (or a model)
    to write a condition. The only question asked at the end of each iteration
    is the one the step already declares in its ``completion`` spec, answered by
    a registered validator against authoritative state.

    The invariant this exists to enforce:

        The SOP Engine controls the loop. The model may provide evidence, but
        it cannot decide that the loop is finished.

    A model returning ``status=COMPLETED`` does not exit the loop — the
    validator's verdict does. A model returning ``status=FAILED`` does not
    extend the loop — if the validator says the criterion holds, the loop exits
    anyway. Neither runtime is ever asked "should we go round again?".

    Loop body
        The loop body is the step itself. There is no multi-step loop: a
        back-edge spanning several steps would make it possible to re-enter a
        governed write, which is exactly the failure mode the no-blind-retry
        rule exists to prevent. See ``SOPStep`` for the validators that refuse
        a loop on a write/governance step.

    Bounds
        Every loop is bounded twice over — by ``max_iterations`` (a count) and
        optionally by ``max_total_seconds`` (wall clock across all iterations).
        Neither bound is model-supplied.

    Counter
        The authoritative iteration counter is
        ``ProcedureExecutionState.attempt_by_step[step_id]``, which the engine
        already maintains per step attempt. A loop step may not also declare a
        ``retry_policy`` precisely so that "attempts" and "iterations" stay the
        same number — two repetition budgets on one step is the conflation this
        contract exists to avoid.
    """

    max_iterations: int = Field(
        ge=1,
        le=20,
        default=3,
        description=(
            "Maximum number of times this step may run. The engine stops at this "
            "bound regardless of what any runtime or model reports."
        ),
    )
    exit_step_id: str | None = Field(
        default=None,
        description=(
            "Step to proceed to when the completion criterion holds. "
            "None means fall through to the step's own next_step_id."
        ),
    )
    exhaustion_step_id: str | None = Field(
        default=None,
        description=(
            "Step to proceed to when the budget is exhausted — typically a "
            "structured human-escalation step. None means escalate the procedure "
            "immediately. Either way the procedure terminates as ESCALATED: "
            "reaching this branch is never a success."
        ),
    )
    max_total_seconds: float | None = Field(
        default=None,
        gt=0.0,
        le=3600.0,
        description=(
            "Wall-clock budget measured from the first entry into the loop step, "
            "across all iterations. None means only max_iterations bounds the loop."
        ),
    )


__all__ = [
    "ValidatorType",
    "EscalationReasonCode",
    "StepCompletionSpec",
    "RetryPolicy",
    "LoopPolicy",
]
