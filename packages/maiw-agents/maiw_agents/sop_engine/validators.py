# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW SOP Engine V2 — step completion validators.

A validator answers exactly one question: *has this step's declared completion
criterion been proven?* It returns a verdict. It does not act.

HARD INVARIANT (docs/architecture/SOP_ENGINE_V2_DESIGN.md Section 14):
    No validator may invoke ActionExecutor, bypass DecisionEngine or human
    approval, call a WRITE/EMERGENCY_WRITE capability, or execute shell
    commands. This module imports nothing from ``maiw_execution`` and holds no
    reference to any executor. A validator that needs to confirm a write
    occurred does so by reading authoritative state (supplied to it as an
    already-captured snapshot), never by issuing the write again.

Validators are async because a future validator may need to await a READ
capability. The four implemented here are pure and complete synchronously.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Protocol, runtime_checkable

from ..contracts.procedure_state import ProcedureExecutionState
from ..contracts.runtime import AgentExecutionContext
from ..contracts.sop import SOPStep
from ..contracts.step_result import EvidenceRef, StepResult, StepStatus, ValidationResult
from ..contracts.sop_v2 import ValidatorType

logger = logging.getLogger(__name__)


# ── Validation context ────────────────────────────────────────────────────────

@dataclass
class StepValidationContext:
    """
    Everything a validator is permitted to see.

    Note what is absent: no ActionExecutor, no DecisionEngine, no MCP client,
    no write capability, no credentials. ``warehouse_state_snapshot`` is a
    *already-read* view of authoritative state supplied by the caller — the
    validator cannot go and fetch (or change) state itself.
    """

    step: SOPStep
    procedure_state: ProcedureExecutionState
    execution_context: AgentExecutionContext
    warehouse_state_snapshot: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Validator protocol ────────────────────────────────────────────────────────

@runtime_checkable
class StepValidator(Protocol):
    """Runtime-neutral step completion validator."""

    async def validate(
        self,
        step: SOPStep,
        result: StepResult,
        context: StepValidationContext,
    ) -> ValidationResult:
        ...


def _evidence(
    validator_type: ValidatorType,
    step: SOPStep,
    context: StepValidationContext,
    summary: str,
    **metadata: Any,
) -> EvidenceRef:
    """Build the structured evidence record a validator emits for its verdict."""
    return EvidenceRef(
        type="validator_result",
        source=validator_type.value,
        reference_id=context.procedure_state.trace_id or None,
        timestamp=datetime.now(timezone.utc),
        summary=summary,
        metadata={"step_id": step.id, **metadata},
    )


# ── SCHEMA ────────────────────────────────────────────────────────────────────

class SchemaValidator:
    """Completion requires the declared keys to be present in ``result.output``."""

    async def validate(
        self,
        step: SOPStep,
        result: StepResult,
        context: StepValidationContext,
    ) -> ValidationResult:
        if step.completion is None or step.completion.schema_fields is None:
            return ValidationResult(
                valid=True,
                validator_type=ValidatorType.SCHEMA,
                reason="no schema required",
                evidence=[_evidence(ValidatorType.SCHEMA, step, context, "no schema required")],
            )

        required = step.completion.schema_fields
        missing = [f for f in required if f not in result.output]
        if missing:
            return ValidationResult(
                valid=False,
                validator_type=ValidatorType.SCHEMA,
                reason=f"missing required fields: {missing}",
                retryable=True,
                evidence=[
                    _evidence(
                        ValidatorType.SCHEMA, step, context,
                        f"schema check failed: missing {missing}",
                        missing_fields=missing,
                        required_fields=required,
                    )
                ],
                metadata={"missing_fields": missing},
            )

        return ValidationResult(
            valid=True,
            validator_type=ValidatorType.SCHEMA,
            reason=f"all required fields present: {required}",
            evidence=[
                _evidence(
                    ValidatorType.SCHEMA, step, context,
                    f"schema check passed for {required}",
                    required_fields=required,
                )
            ],
        )


# ── STATE_PREDICATE ───────────────────────────────────────────────────────────

# Predicates are registered in *code*, never defined in YAML. A SOP names a
# predicate; it cannot supply an expression. This is the same no-eval principle
# that governs StepCondition.
_PREDICATES: dict[str, Callable[[dict[str, Any], dict[str, Any]], bool]] = {}


def register_predicate(
    name: str,
    fn: Callable[[dict[str, Any], dict[str, Any]], bool],
) -> None:
    """
    Register a named state predicate.

    ``fn(state_dict, args) -> bool`` must be pure and read-only. Registering a
    function that mutates warehouse state violates the validator authority rule.
    """
    _PREDICATES[name] = fn


def unregister_predicate(name: str) -> None:
    """Remove a registered predicate (used by tests to keep the registry clean)."""
    _PREDICATES.pop(name, None)


def get_registered_predicates() -> dict[str, Callable[[dict[str, Any], dict[str, Any]], bool]]:
    """Return a copy of the predicate registry (introspection / tests)."""
    return dict(_PREDICATES)


class StatePredicateValidator:
    """
    Completion requires a registered predicate to hold against authoritative state.

    This is the validator that enforces the post-write invariant: a write-related
    step completes only when a re-read of warehouse state proves the intended
    change actually happened.
    """

    async def validate(
        self,
        step: SOPStep,
        result: StepResult,
        context: StepValidationContext,
    ) -> ValidationResult:
        predicate_name = step.completion.predicate_name if step.completion else None

        if predicate_name is None:
            return ValidationResult(
                valid=True,
                validator_type=ValidatorType.STATE_PREDICATE,
                reason="no predicate required",
                evidence=[
                    _evidence(
                        ValidatorType.STATE_PREDICATE, step, context, "no predicate required"
                    )
                ],
            )

        fn = _PREDICATES.get(predicate_name)
        if fn is None:
            # Not retryable: re-running the step cannot register a predicate.
            return ValidationResult(
                valid=False,
                validator_type=ValidatorType.STATE_PREDICATE,
                reason=f"unknown predicate: {predicate_name}",
                retryable=False,
                evidence=[
                    _evidence(
                        ValidatorType.STATE_PREDICATE, step, context,
                        f"unknown predicate {predicate_name!r}",
                        predicate_name=predicate_name,
                    )
                ],
                metadata={"predicate_name": predicate_name},
            )

        args = (step.completion.predicate_args or {}) if step.completion else {}
        snapshot = context.warehouse_state_snapshot
        state_dict: dict[str, Any] = snapshot if isinstance(snapshot, dict) else {}
        if snapshot is not None and not isinstance(snapshot, dict):
            # Accept pydantic models / objects exposing model_dump() or __dict__.
            if hasattr(snapshot, "model_dump"):
                state_dict = snapshot.model_dump()
            elif hasattr(snapshot, "__dict__"):
                state_dict = dict(vars(snapshot))

        try:
            valid = bool(fn(state_dict, args))
        except Exception as exc:  # a broken predicate must not crash the engine
            logger.exception("StatePredicateValidator: predicate %r raised", predicate_name)
            return ValidationResult(
                valid=False,
                validator_type=ValidatorType.STATE_PREDICATE,
                reason=f"predicate {predicate_name!r} raised: {exc}",
                retryable=False,
                evidence=[
                    _evidence(
                        ValidatorType.STATE_PREDICATE, step, context,
                        f"predicate {predicate_name!r} raised an exception",
                        predicate_name=predicate_name,
                    )
                ],
            )

        summary = (
            f"predicate {predicate_name!r} "
            f"{'held' if valid else 'did not hold'} against authoritative state"
        )
        return ValidationResult(
            valid=valid,
            validator_type=ValidatorType.STATE_PREDICATE,
            reason=summary,
            # A false predicate means reality does not (yet) match the expectation.
            # Retrying the *step* is permitted; the engine never re-issues writes.
            retryable=True,
            evidence=[
                _evidence(
                    ValidatorType.STATE_PREDICATE, step, context, summary,
                    predicate_name=predicate_name,
                    predicate_args=args,
                    state_observed=bool(state_dict),
                )
            ],
            metadata={"predicate_name": predicate_name, "predicate_args": args},
        )


# ── CAPABILITY_RESULT ─────────────────────────────────────────────────────────

class CapabilityResultValidator:
    """Completion requires a named capability's structured result in the output."""

    async def validate(
        self,
        step: SOPStep,
        result: StepResult,
        context: StepValidationContext,
    ) -> ValidationResult:
        if step.completion is None or step.completion.required_capability_result is None:
            return ValidationResult(
                valid=True,
                validator_type=ValidatorType.CAPABILITY_RESULT,
                reason="no capability result required",
                evidence=[
                    _evidence(
                        ValidatorType.CAPABILITY_RESULT, step, context,
                        "no capability result required",
                    )
                ],
            )

        cap_id = step.completion.required_capability_result

        if cap_id not in result.output:
            return ValidationResult(
                valid=False,
                validator_type=ValidatorType.CAPABILITY_RESULT,
                reason=f"capability result '{cap_id}' not found in output",
                retryable=True,
                evidence=[
                    _evidence(
                        ValidatorType.CAPABILITY_RESULT, step, context,
                        f"capability result {cap_id!r} absent",
                        capability_id=cap_id,
                    )
                ],
                metadata={"capability_id": cap_id},
            )

        cap_result = result.output[cap_id]
        required_fields = step.completion.required_result_fields

        if required_fields:
            if not isinstance(cap_result, dict):
                return ValidationResult(
                    valid=False,
                    validator_type=ValidatorType.CAPABILITY_RESULT,
                    reason="capability result is not a dict",
                    retryable=True,
                    evidence=[
                        _evidence(
                            ValidatorType.CAPABILITY_RESULT, step, context,
                            f"capability result {cap_id!r} is not a mapping",
                            capability_id=cap_id,
                        )
                    ],
                    metadata={"capability_id": cap_id},
                )

            missing = [f for f in required_fields if f not in cap_result]
            if missing:
                return ValidationResult(
                    valid=False,
                    validator_type=ValidatorType.CAPABILITY_RESULT,
                    reason=f"missing capability result fields: {missing}",
                    retryable=True,
                    evidence=[
                        _evidence(
                            ValidatorType.CAPABILITY_RESULT, step, context,
                            f"capability result {cap_id!r} missing {missing}",
                            capability_id=cap_id,
                            missing_fields=missing,
                        )
                    ],
                    metadata={"capability_id": cap_id, "missing_fields": missing},
                )

        return ValidationResult(
            valid=True,
            validator_type=ValidatorType.CAPABILITY_RESULT,
            reason=f"capability result '{cap_id}' present and complete",
            evidence=[
                EvidenceRef(
                    type="capability_result",
                    source=cap_id,
                    reference_id=context.procedure_state.trace_id or None,
                    timestamp=datetime.now(timezone.utc),
                    summary=f"capability result {cap_id!r} present and complete",
                    metadata={
                        "step_id": step.id,
                        "required_result_fields": required_fields or [],
                    },
                )
            ],
            metadata={"capability_id": cap_id},
        )


# ── LEGACY_SUCCESS ────────────────────────────────────────────────────────────

class LegacySuccessValidator:
    """
    V1 compatibility.

    A step with no completion spec advances whenever the runtime returned
    without reporting a failure. This preserves pre-V2 semantics exactly for
    every existing SOP, while making the (weak) completion criterion explicit
    and auditable rather than implicit.
    """

    async def validate(
        self,
        step: SOPStep,
        result: StepResult,
        context: StepValidationContext,
    ) -> ValidationResult:
        if result.status in (StepStatus.FAILED, StepStatus.TIMED_OUT, StepStatus.ESCALATED):
            return ValidationResult(
                valid=False,
                validator_type=ValidatorType.LEGACY_SUCCESS,
                reason="runtime reported failure",
                retryable=True,
                evidence=[
                    _evidence(
                        ValidatorType.LEGACY_SUCCESS, step, context,
                        f"runtime reported {result.status.value}",
                        runtime=result.runtime,
                        runtime_status=result.status.value,
                    )
                ],
            )

        return ValidationResult(
            valid=True,
            validator_type=ValidatorType.LEGACY_SUCCESS,
            reason="legacy compatibility: runtime returned without error",
            evidence=[
                _evidence(
                    ValidatorType.LEGACY_SUCCESS, step, context,
                    "legacy compatibility: runtime returned without error",
                    runtime=result.runtime,
                )
            ],
        )


# ── Registry ──────────────────────────────────────────────────────────────────

class ValidatorRegistry:
    """
    Selects the validator for a step.

    Deliberately a closed set. Asking for MODEL_JUDGE or COMPOSITE raises
    rather than silently falling back to something permissive — an unsupported
    completion criterion must never be mistaken for a satisfied one.
    """

    def __init__(self, validators: dict[ValidatorType, StepValidator] | None = None) -> None:
        # `is None`, not truthiness: an explicitly empty registry must stay empty
        # so that every lookup raises rather than silently falling back.
        if validators is None:
            validators = {
                ValidatorType.SCHEMA: SchemaValidator(),
                ValidatorType.STATE_PREDICATE: StatePredicateValidator(),
                ValidatorType.CAPABILITY_RESULT: CapabilityResultValidator(),
                ValidatorType.LEGACY_SUCCESS: LegacySuccessValidator(),
            }
        self._validators: dict[ValidatorType, StepValidator] = validators

    def get(self, validator_type: ValidatorType) -> StepValidator:
        validator = self._validators.get(validator_type)
        if validator is None:
            raise ValueError(
                f"Unsupported validator type: {validator_type}. "
                "MODEL_JUDGE and COMPOSITE are not yet implemented."
            )
        return validator

    def get_for_step(self, step: SOPStep) -> StepValidator:
        """A step with no completion spec gets LEGACY_SUCCESS (V1 behaviour)."""
        if step.completion is None:
            return self.get(ValidatorType.LEGACY_SUCCESS)
        return self.get(step.completion.validator_type)

    def supported_types(self) -> set[ValidatorType]:
        return set(self._validators)


DEFAULT_VALIDATOR_REGISTRY = ValidatorRegistry()


__all__ = [
    "StepValidationContext",
    "StepValidator",
    "SchemaValidator",
    "StatePredicateValidator",
    "CapabilityResultValidator",
    "LegacySuccessValidator",
    "ValidatorRegistry",
    "DEFAULT_VALIDATOR_REGISTRY",
    "register_predicate",
    "unregister_predicate",
    "get_registered_predicates",
]
