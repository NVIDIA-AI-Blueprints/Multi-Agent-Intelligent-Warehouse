# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW SOP Engine V2 — procedure lifecycle owner.

The engine owns everything about *running a procedure* that used to be spread
across (and duplicated between) the runtimes:

    step progression    which step runs next, including conditions and
                        on-failure branching
    validation          whether a step is actually complete
    retry               per-step budget, backoff, and the no-blind-retry rule
    loops               bounded, validator-driven reassessment of one step
    escalation          typed reason codes instead of model prose
    evidence            a structured audit trail per step and per procedure

The single rule this module exists to enforce:

    A step advances because its declared completion criterion was proven —
    not because a runtime or a model said it was done.

Its corollary, for bounded loops:

    The SOP Engine controls the loop. The model may provide evidence, but it
    cannot decide that the loop is finished.

    A runtime is handed one step and returns one claim about it. It is never
    asked whether to iterate again, never told how many iterations remain, and
    never given the option to select a successor. Loop continuation is decided
    here, from the validator's verdict and two engine-held bounds.

Domain neutrality:
    Nothing in this module knows about warehouses, inventory, equipment or
    labour. Loop semantics are expressed purely in terms of steps, validators
    and budgets, so the same machinery serves any domain that supplies a
    SOPStepExecutor and registered predicates.

Authority boundary (docs/architecture/SOP_ENGINE_V2_DESIGN.md Section 31):
    The SOP Engine does NOT own ActionExecutor, DecisionEngine, warehouse
    credentials, or WRITE tools, and imports none of them. Write-related steps
    pause at WAITING_FOR_GOVERNANCE and are resumed by the caller only after
    governance has run — and even then, only complete if authoritative state
    proves the change landed. See ``resume_after_governance``.

Persistence (production hardening):
    Supplying a ``ProcedureStateStore`` makes the procedure recoverable. The
    engine checkpoints after each lifecycle transition, so a restart can restore
    exactly which SOP version was running, which step and attempt were active,
    what evidence had been proven, and whether a write may already have
    occurred. Persistence changes nothing about authority: a restored procedure
    that was waiting on governance is still waiting on governance, and a
    restored post-write step still proves its outcome by re-reading
    authoritative state rather than by repeating the write. The engine runs
    unchanged with ``store=None``.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from ..contracts.agent import AgentDefinition
from ..contracts.procedure_state import ProcedureExecutionState, ProcedureStatus
from ..contracts.runtime import AgentExecutionContext
from ..contracts.sop import SOPDefinition, SOPStep
from ..contracts.sop_v2 import EscalationReasonCode, ValidatorType
from ..contracts.step_result import EvidenceRef, StepResult, StepStatus
from .executor import SOPStepExecutor
from .state_store import ProcedureStateStore
from .validators import (
    DEFAULT_EVIDENCE_VALIDATOR,
    DEFAULT_VALIDATOR_REGISTRY,
    StepValidationContext,
    ValidatorRegistry,
)

logger = logging.getLogger(__name__)

# Hard bound on step transitions per procedure run. validate_sop() already
# rejects next_step_id cycles statically, but on_failure_step_id branching and
# hand-built SOPDefinitions are not covered by that check.
_DEFAULT_MAX_TRANSITIONS = 100


def _now() -> datetime:
    return datetime.now(timezone.utc)


class LoopDecision(str, Enum):
    """
    The three outcomes of one bounded-loop iteration.

    This is the whole loop state machine. The engine evaluates it after every
    iteration of a looping step, using only the validator's verdict and the two
    engine-held bounds. No runtime, executor or model participates:

        LOOP_RUNNING ─ validator says the criterion holds ──────────→ EXIT
                     ├ criterion does not hold, budget remains ─────→ RETRY
                     └ criterion does not hold, budget spent ───────→ EXHAUSTED
    """

    EXIT = "exit"
    RETRY = "retry"
    EXHAUSTED = "exhausted"


class SOPEngine:
    """
    Internal SOP Engine. Owns procedure lifecycle, step progression, validation,
    retry, escalation, and evidence collection.

    Does NOT own: ActionExecutor, DecisionEngine, warehouse credentials, WRITE tools.
    """

    def __init__(
        self,
        *,
        executor: SOPStepExecutor,
        validator_registry: ValidatorRegistry | None = None,
        trace_id: str = "",
        max_transitions: int = _DEFAULT_MAX_TRANSITIONS,
        store: ProcedureStateStore | None = None,
    ) -> None:
        self._executor = executor
        self._validators = validator_registry or DEFAULT_VALIDATOR_REGISTRY
        self._trace_id = trace_id
        self._max_transitions = max_transitions
        # None = run without persistence. This is the pre-hardening behaviour and
        # remains the default so every existing caller is unaffected.
        self._store = store

    # ── Checkpointing ─────────────────────────────────────────────────────────

    async def _checkpoint(
        self,
        proc_state: ProcedureExecutionState,
        *,
        final: bool = False,
    ) -> ProcedureExecutionState:
        """
        Persist a lifecycle transition and adopt the store's new revision.

        Checkpointed: procedure created, step started, StepResult accepted,
        validation recorded, retry/loop count changed, branch taken, governance
        wait entered, governance resumed, escalation, terminal.

        Not checkpointed: token-level model activity, partial runtime output, or
        anything else that is not a procedure-level transition. A checkpoint is
        a point the procedure can be resumed from, not a trace.

        Terminal states are written exactly once, by the ``final=True`` call at
        the end of ``run_procedure``. Intermediate checkpoints skip them so the
        store's terminal-immutability rule is never tripped by the engine's own
        bookkeeping.
        """
        if self._store is None:
            return proc_state
        if not final and proc_state.is_terminal():
            return proc_state
        return await self._store.save(
            proc_state, expected_revision=proc_state.revision
        )

    # ── Public API ────────────────────────────────────────────────────────────

    async def run_procedure(
        self,
        *,
        definition: AgentDefinition,
        sop: SOPDefinition,
        agent_task_id: str,
        context: AgentExecutionContext,
        initial_state: ProcedureExecutionState | None = None,
        warehouse_state_snapshot: Any | None = None,
    ) -> ProcedureExecutionState:
        """
        Execute an SOP from the start, or resume from ``initial_state``.

        Returns the final ``ProcedureExecutionState``. The caller is responsible for:
          - creating a RecommendedAction from a WAITING_FOR_GOVERNANCE pause
          - calling ``resume_after_governance()`` once governance has completed

        Resuming after a restart: pass the state loaded from the store as
        ``initial_state``. Everything that governs progression — current step,
        completed steps, attempt counts, loop budgets, evidence, governance
        status — is carried on that state, so the resumed run picks up exactly
        where the crashed one stopped. Completed steps are not re-executed and
        loop budgets are not reset.
        """
        # Resuming a procedure that already finished is a no-op, and a no-op
        # must not write. Re-saving a terminal record would both trip the
        # store's immutability rule and add a revision that represents nothing.
        if initial_state is not None and initial_state.is_terminal():
            logger.info(
                "SOPEngine: procedure %s is already terminal (%s) — nothing to resume",
                initial_state.procedure_execution_id, initial_state.status.value,
            )
            return initial_state

        proc_state = await self._run_procedure_inner(
            definition=definition,
            sop=sop,
            agent_task_id=agent_task_id,
            context=context,
            initial_state=initial_state,
            warehouse_state_snapshot=warehouse_state_snapshot,
        )
        # Exactly one terminal/paused write, at the single exit point.
        return await self._checkpoint(proc_state, final=True)

    async def _run_procedure_inner(
        self,
        *,
        definition: AgentDefinition,
        sop: SOPDefinition,
        agent_task_id: str,
        context: AgentExecutionContext,
        initial_state: ProcedureExecutionState | None = None,
        warehouse_state_snapshot: Any | None = None,
    ) -> ProcedureExecutionState:
        """Procedure loop. Checkpoints non-terminal transitions only."""
        resuming = initial_state is not None
        proc_state = initial_state or self._init_state(sop, agent_task_id, context)

        # A restored procedure must never be re-advanced past its own ending.
        if proc_state.is_terminal():
            logger.info(
                "SOPEngine: refusing to resume terminal procedure %s (status=%s)",
                proc_state.procedure_execution_id, proc_state.status.value,
            )
            return proc_state

        # SOP version pinning: a restored procedure runs the version it started
        # under, or it does not run. Silently continuing under a newer SOP would
        # mean the steps already completed and the steps still to come came from
        # different procedures.
        if resuming:
            mismatch = self._version_mismatch(proc_state, sop)
            if mismatch is not None:
                return self._escalate(
                    proc_state, EscalationReasonCode.POLICY_CONFLICT, mismatch
                )

        step_index: dict[str, SOPStep] = {s.id: s for s in sop.steps}

        if proc_state.current_step_id is None and sop.steps:
            if proc_state.completed_step_ids or proc_state.branch_history:
                # Resumed at a procedure that had already run off the end of its
                # step chain. Restarting from step 0 would re-execute everything.
                return proc_state.model_copy(update={
                    "status": self._terminal_status(proc_state),
                    "last_updated_at": _now(),
                })
            proc_state = proc_state.model_copy(
                update={"current_step_id": sop.steps[0].id}
            )

        # Checkpoint: procedure created (or resumed and validated).
        proc_state = await self._checkpoint(proc_state)

        transitions = 0

        while proc_state.current_step_id is not None:
            transitions += 1
            if transitions > self._max_transitions:
                return self._escalate(
                    proc_state,
                    EscalationReasonCode.POLICY_CONFLICT,
                    f"Procedure exceeded {self._max_transitions} step transitions.",
                )

            step = step_index.get(proc_state.current_step_id)
            if step is None:
                return self._escalate(
                    proc_state,
                    EscalationReasonCode.INVALID_OUTPUT,
                    f"Unknown step_id: {proc_state.current_step_id}",
                )

            # Declarative condition (V1 feature): skip the step when it does not hold.
            if step.condition is not None:
                facts = dict(context.bounded_context)
                if not step.condition.evaluate(facts):
                    logger.debug(
                        "SOPEngine: step %s condition not met — skipping. sop=%s",
                        step.id, sop.id,
                    )
                    proc_state = self._skip(proc_state, step)
                    proc_state = await self._checkpoint(proc_state)  # branch taken
                    continue

            # Required inputs (V2): a step cannot run without the context it declares.
            missing_inputs = self._missing_required_inputs(step, context)
            if missing_inputs:
                return self._escalate(
                    proc_state,
                    EscalationReasonCode.MISSING_DATA,
                    step.escalation_reason
                    or f"Step {step.id} missing required inputs: {missing_inputs}",
                    step_id=step.id,
                )

            # Stamp the wall-clock origin for a loop's total-time budget on the
            # first entry into the step, not on each iteration.
            if step.loop is not None and step.id not in proc_state.loop_started_at:
                proc_state = proc_state.model_copy(update={
                    "loop_started_at": {**proc_state.loop_started_at, step.id: _now()},
                })

            # Checkpoint: step started. A crash after this point is recoverable
            # as "this step was in flight", which is what lets Scenario A
            # distinguish a step that never ran from one that may have.
            proc_state = await self._checkpoint(proc_state)

            proc_state, step_result = await self._run_step_with_retry(
                definition=definition,
                step=step,
                proc_state=proc_state,
                context=context,
                warehouse_state_snapshot=warehouse_state_snapshot,
            )

            if step_result.status == StepStatus.WAITING_FOR_GOVERNANCE:
                # Pause here. current_step_id stays on this step so the caller
                # can resume it after governance runs.
                return proc_state.model_copy(update={
                    "status": ProcedureStatus.WAITING_FOR_GOVERNANCE,
                    "last_updated_at": _now(),
                })

            if step_result.status == StepStatus.COMPLETED:
                # A looping step that completed has, by definition, had its
                # declared criterion proven — that is the loop's EXIT edge.
                override = step.loop.exit_step_id if step.loop is not None else None
                proc_state = self._advance(proc_state, step, override_next=override)
                proc_state = await self._checkpoint(proc_state)  # advance recorded
                continue

            # ── Bounded loop: the criterion did not hold (yet) ────────────────
            if step.loop is not None and self._loop_may_continue(step_result):
                decision, reason = self._loop_decision(proc_state, step)
                if decision is LoopDecision.RETRY:
                    logger.info(
                        "SOPEngine: loop step %s iteration %d/%d — criterion not met, "
                        "re-entering. sop=%s",
                        step.id,
                        proc_state.loop_iterations(step.id),
                        step.loop.max_iterations,
                        sop.id,
                    )
                    # Checkpoint: loop iteration count changed. This is what
                    # makes "attempt 2 of 3" survive a crash as 2 of 3.
                    proc_state = await self._checkpoint(proc_state)
                    # current_step_id is unchanged: the loop body is the step.
                    continue
                proc_state = self._record_loop_exhaustion(proc_state, step, step_result, reason)
                if step.loop.exhaustion_step_id is None:
                    return proc_state.model_copy(update={
                        "status": ProcedureStatus.ESCALATED,
                        "last_updated_at": _now(),
                    })
                proc_state = proc_state.model_copy(update={
                    "current_step_id": step.loop.exhaustion_step_id,
                    "branch_history": proc_state.branch_history + [step.id],
                    "last_updated_at": _now(),
                })
                proc_state = await self._checkpoint(proc_state)  # exhaustion branch
                continue

            # Step did not complete. Honour the declared failure branch if present.
            if step.on_failure_step_id is not None:
                logger.info(
                    "SOPEngine: step %s failed — branching to on_failure_step_id=%s",
                    step.id, step.on_failure_step_id,
                )
                proc_state = proc_state.model_copy(update={
                    "current_step_id": step.on_failure_step_id,
                    "branch_history": proc_state.branch_history + [step.id],
                    "last_updated_at": _now(),
                })
                proc_state = await self._checkpoint(proc_state)  # failure branch
                continue

            terminal = (
                ProcedureStatus.ESCALATED
                if step_result.status == StepStatus.ESCALATED
                else ProcedureStatus.FAILED
            )
            return proc_state.model_copy(update={
                "status": terminal,
                "last_updated_at": _now(),
            })

        return proc_state.model_copy(update={
            "status": self._terminal_status(proc_state),
            "last_updated_at": _now(),
        })

    async def resume_after_governance(
        self,
        *,
        definition: AgentDefinition,
        sop: SOPDefinition,
        proc_state: ProcedureExecutionState,
        context: AgentExecutionContext,
        governance_outcome: Any,
        warehouse_state_snapshot: Any | None = None,
    ) -> ProcedureExecutionState:
        """
        Resume a procedure paused at WAITING_FOR_GOVERNANCE.

        HARD INVARIANT (Design Section 34): a write-related step is NOT marked
        complete because governance returned APPROVED or because a call
        returned 2xx. If the step declares completion criteria, those criteria
        are evaluated against authoritative post-execution state. An
        indeterminate execution escalates as EXECUTION_INDETERMINATE rather
        than retrying the write.

        Restart safety: this method re-runs *validation only*. It never invokes
        the executor and never issues a write. A procedure that crashed after
        its write landed but before the authoritative re-read resumes here,
        re-reads, and completes — with the write still having happened exactly
        once.
        """
        step_id = proc_state.current_step_id
        if step_id is None:
            raise ValueError("resume_after_governance called but no current step")

        if proc_state.is_terminal():
            logger.info(
                "SOPEngine: refusing governance resume on terminal procedure %s (%s)",
                proc_state.procedure_execution_id, proc_state.status.value,
            )
            return proc_state

        version_mismatch = self._version_mismatch(proc_state, sop)
        if version_mismatch is not None:
            escalated = self._escalate(
                proc_state, EscalationReasonCode.POLICY_CONFLICT, version_mismatch
            )
            return await self._checkpoint(escalated, final=True)

        step = next((s for s in sop.steps if s.id == step_id), None)
        if step is None:
            raise ValueError(f"Current step {step_id} not found in SOP")

        decision = str(getattr(governance_outcome, "decision_outcome", "") or "")
        execution_status = str(getattr(governance_outcome, "execution_status", "") or "")

        outcome_output: dict[str, Any] = {
            "governance_decision": decision,
            "execution_status": execution_status,
        }

        step_result = StepResult(
            step_id=step_id,
            status=StepStatus.RUNNING,
            output=outcome_output,
            runtime="governance_resume",
            attempt=proc_state.attempt_by_step.get(step_id, 1),
            started_at=proc_state.started_at,
            completed_at=_now(),
            evidence=[],
        )

        val_ctx = StepValidationContext(
            step=step,
            procedure_state=proc_state,
            execution_context=context,
            warehouse_state_snapshot=warehouse_state_snapshot,
        )
        validator = self._validators.get_for_step(step)

        # Evidence requirements bind here too — this is the post-write reread,
        # the step where "we believe it worked" is least acceptable.
        evidence_check = await DEFAULT_EVIDENCE_VALIDATOR.validate(
            step, step_result, val_ctx
        )
        if not evidence_check.valid:
            failed = step_result.model_copy(update={
                "status": StepStatus.ESCALATED,
                "validation_result": evidence_check,
                "evidence": step_result.evidence + evidence_check.evidence,
                "escalation_reason": EscalationReasonCode.EVIDENCE_MISSING,
                "escalation_message": (
                    f"Post-governance evidence missing: {evidence_check.reason}"
                ),
            })
            escalated = proc_state.model_copy(update={
                "step_results": {**proc_state.step_results, step_id: failed},
                "evidence_refs": proc_state.evidence_refs + evidence_check.evidence,
                "status": ProcedureStatus.ESCALATED,
                "last_updated_at": _now(),
            })
            return await self._checkpoint(escalated, final=True)

        validation = await validator.validate(step, step_result, val_ctx)

        # An indeterminate execution is only resolvable by positive proof.
        # LEGACY_SUCCESS ("the runtime returned") is not proof that a write
        # landed, so it must not close out an ambiguous outcome.
        indeterminate = self._is_indeterminate(execution_status)
        if (
            validation.valid
            and indeterminate
            and validation.validator_type is ValidatorType.LEGACY_SUCCESS
        ):
            validation = validation.model_copy(update={
                "valid": False,
                "reason": (
                    f"execution status {execution_status!r} is indeterminate and the step "
                    "declares no completion criteria — authoritative state proof required"
                ),
                "retryable": False,
            })

        if validation.valid:
            completed_result = step_result.model_copy(update={
                "status": StepStatus.COMPLETED,
                "validation_result": validation,
                "evidence": step_result.evidence + validation.evidence,
            })
            updated = proc_state.model_copy(update={
                "step_results": {**proc_state.step_results, step_id: completed_result},
                "evidence_refs": proc_state.evidence_refs + validation.evidence,
                "status": ProcedureStatus.RUNNING,
                "last_updated_at": _now(),
            })
            advanced = self._advance(updated, step)
            if advanced.current_step_id is None:
                return await self._checkpoint(
                    advanced.model_copy(update={
                        "status": self._terminal_status(advanced),
                        "last_updated_at": _now(),
                    }),
                    final=True,
                )
            return await self._checkpoint(advanced)

        # Validation failed after governance. Distinguish "the write definitely
        # did not land" from "we cannot tell whether it landed" — the latter is
        # the dangerous case and must never be resolved by retrying the write.
        if indeterminate:
            reason_code = EscalationReasonCode.EXECUTION_INDETERMINATE
        else:
            reason_code = EscalationReasonCode.VALIDATION_FAILED

        failed_result = step_result.model_copy(update={
            "status": StepStatus.ESCALATED,
            "validation_result": validation,
            "evidence": step_result.evidence + validation.evidence,
            "escalation_reason": reason_code,
            "escalation_message": (
                f"Post-governance validation failed: {validation.reason}"
            ),
        })
        return await self._checkpoint(
            proc_state.model_copy(update={
                "step_results": {**proc_state.step_results, step_id: failed_result},
                "evidence_refs": proc_state.evidence_refs + validation.evidence,
                "status": ProcedureStatus.ESCALATED,
                "last_updated_at": _now(),
            }),
            final=True,
        )

    # ── Step execution ────────────────────────────────────────────────────────

    async def _run_step_with_retry(
        self,
        *,
        definition: AgentDefinition,
        step: SOPStep,
        proc_state: ProcedureExecutionState,
        context: AgentExecutionContext,
        warehouse_state_snapshot: Any | None = None,
    ) -> tuple[ProcedureExecutionState, StepResult]:
        retry_policy = step.retry_policy
        max_attempts = retry_policy.max_attempts if retry_policy else 1

        # Attempts accumulate across re-entries of the same step, so a looping
        # step's attempt count IS its iteration count. For a step entered once —
        # every step in every pre-loop SOP — base_attempt is 0 and the numbering
        # is exactly what it was before bounded loops existed.
        base_attempt = proc_state.attempt_by_step.get(step.id, 0)

        step_result: StepResult | None = None
        stopped_early = False

        for offset in range(1, max_attempts + 1):
            attempt = base_attempt + offset
            step_result = await self._execute_and_validate(
                definition=definition,
                step=step,
                proc_state=proc_state,
                context=context,
                attempt=attempt,
                warehouse_state_snapshot=warehouse_state_snapshot,
            )

            proc_state = proc_state.model_copy(update={
                "step_results": {**proc_state.step_results, step.id: step_result},
                "attempt_by_step": {**proc_state.attempt_by_step, step.id: attempt},
                "evidence_refs": (
                    proc_state.evidence_refs
                    + self._stamp_attempt(step_result.evidence, step.id, attempt)
                ),
                "last_updated_at": _now(),
            })

            # Checkpoint: StepResult accepted, validation recorded, attempt
            # count advanced. A crash after this point must not re-execute the
            # step — the stored result is reused and only validation replays.
            proc_state = await self._checkpoint(proc_state)

            if step_result.status in (
                StepStatus.COMPLETED,
                StepStatus.WAITING_FOR_GOVERNANCE,
                StepStatus.ESCALATED,
            ):
                return proc_state, step_result

            # A validator saying "not retryable" means re-running cannot help.
            if step_result.validation_result and not step_result.validation_result.retryable:
                stopped_early = True
                break

            if offset < max_attempts and retry_policy is not None:
                if retry_policy.backoff_seconds > 0:
                    await asyncio.sleep(retry_policy.backoff_seconds)

        assert step_result is not None  # max_attempts >= 1, loop always executes

        if stopped_early:
            # Preserve the real reason; do not mislabel it as budget exhaustion.
            return proc_state, step_result

        if retry_policy is not None and retry_policy.escalate_on_exhaustion:
            escalated = step_result.model_copy(update={
                "status": StepStatus.ESCALATED,
                "escalation_reason": EscalationReasonCode.RETRY_BUDGET_EXHAUSTED,
                "escalation_message": (
                    step.escalation_reason
                    or f"Step {step.id} failed after {max_attempts} attempts"
                ),
            })
            proc_state = proc_state.model_copy(update={
                "step_results": {**proc_state.step_results, step.id: escalated},
                "last_updated_at": _now(),
            })
            return proc_state, escalated

        return proc_state, step_result

    async def _execute_and_validate(
        self,
        *,
        definition: AgentDefinition,
        step: SOPStep,
        proc_state: ProcedureExecutionState,
        context: AgentExecutionContext,
        attempt: int,
        warehouse_state_snapshot: Any | None = None,
    ) -> StepResult:
        started_at = _now()

        # 1. Run the step via the runtime-specific executor (with optional timeout).
        try:
            coro = self._executor.execute_step(
                definition=definition,
                step=step,
                procedure_state=proc_state,
                context=context,
                attempt=attempt,
            )
            if step.timeout_seconds is not None:
                result = await asyncio.wait_for(coro, timeout=step.timeout_seconds)
            else:
                result = await coro
        except asyncio.TimeoutError:
            logger.warning(
                "SOPEngine: step %s timed out after %ss (attempt %d)",
                step.id, step.timeout_seconds, attempt,
            )
            return StepResult(
                step_id=step.id,
                status=StepStatus.TIMED_OUT,
                output={},
                runtime=getattr(self._executor, "RUNTIME_NAME", "unknown"),
                attempt=attempt,
                started_at=started_at,
                completed_at=_now(),
                error=f"Step exceeded timeout of {step.timeout_seconds}s",
                escalation_reason=EscalationReasonCode.TIMEOUT,
                escalation_message=step.escalation_reason
                or f"Step {step.id} timed out after {step.timeout_seconds}s",
            )
        except Exception as exc:
            logger.exception("SOPEngine: executor raised on step %s", step.id)
            return StepResult(
                step_id=step.id,
                status=StepStatus.FAILED,
                output={},
                runtime=getattr(self._executor, "RUNTIME_NAME", "unknown"),
                attempt=attempt,
                started_at=started_at,
                completed_at=_now(),
                error=f"Executor raised: {exc}",
                escalation_reason=EscalationReasonCode.MODEL_FAILURE,
            )

        # 2. A governance pause is not a completion claim — return it untouched.
        if result.status == StepStatus.WAITING_FOR_GOVERNANCE:
            return result

        # 3. An executor that already escalated (e.g. policy conflict) is final.
        if result.status == StepStatus.ESCALATED:
            return result

        # 4. Validate. The validator's verdict — not the executor's status — decides.
        try:
            validator = self._validators.get_for_step(step)
        except ValueError as exc:
            return result.model_copy(update={
                "status": StepStatus.ESCALATED,
                "escalation_reason": EscalationReasonCode.UNSUPPORTED_VALIDATOR,
                "escalation_message": str(exc),
            })

        val_ctx = StepValidationContext(
            step=step,
            procedure_state=proc_state,
            execution_context=context,
            warehouse_state_snapshot=warehouse_state_snapshot,
        )

        # 4a. Evidence requirements run FIRST. A step that cannot show its work
        #     has not completed, whatever its completion criterion would have
        #     said — and it is reported as EVIDENCE_MISSING rather than
        #     VALIDATION_FAILED, because the two call for different responses.
        evidence_check = await DEFAULT_EVIDENCE_VALIDATOR.validate(step, result, val_ctx)
        if not evidence_check.valid:
            logger.warning(
                "SOPEngine: step %s failed evidence requirements on attempt %d — %s",
                step.id, attempt, evidence_check.reason,
            )
            return result.model_copy(update={
                "status": StepStatus.FAILED,
                "completed_at": result.completed_at or _now(),
                "validation_result": evidence_check,
                "evidence": result.evidence + evidence_check.evidence,
                "escalation_reason": EscalationReasonCode.EVIDENCE_MISSING,
                "escalation_message": step.escalation_reason or evidence_check.reason,
            })

        validation = await validator.validate(step, result, val_ctx)

        if validation.valid:
            return result.model_copy(update={
                "status": StepStatus.COMPLETED,
                "completed_at": result.completed_at or _now(),
                "validation_result": validation,
                "evidence": result.evidence + validation.evidence,
            })

        return result.model_copy(update={
            "status": StepStatus.FAILED,
            "completed_at": result.completed_at or _now(),
            "validation_result": validation,
            "evidence": result.evidence + validation.evidence,
            "escalation_reason": EscalationReasonCode.VALIDATION_FAILED,
            "escalation_message": step.escalation_reason or validation.reason,
        })

    # ── State transitions ─────────────────────────────────────────────────────

    def _advance(
        self,
        proc_state: ProcedureExecutionState,
        step: SOPStep,
        *,
        override_next: str | None = None,
    ) -> ProcedureExecutionState:
        """
        Move to the next step.

        ``next_step_id is None`` terminates the procedure. This matches both the
        pre-V2 deterministic runtime and validate_sop()'s static cycle check, so
        existing v1 SOPs traverse exactly as they did before.

        ``override_next`` is used only for a looping step's EXIT edge, where the
        SOP may route a satisfied loop somewhere other than the step's default
        successor. It is supplied by the engine from the step's own declared
        ``loop.exit_step_id`` — never by a runtime.
        """
        return proc_state.model_copy(update={
            "current_step_id": override_next if override_next is not None else step.next_step_id,
            "completed_step_ids": proc_state.completed_step_ids + [step.id],
            "branch_history": proc_state.branch_history + [step.id],
            "last_updated_at": _now(),
        })

    def _skip(
        self,
        proc_state: ProcedureExecutionState,
        step: SOPStep,
    ) -> ProcedureExecutionState:
        """
        Move past a step whose declarative condition did not hold.

        A skipped step is recorded in ``branch_history`` — which documents every
        step traversed, including skipped ones — but NOT in
        ``completed_step_ids``. A step that never reached the executor and never
        faced a validator has not completed anything, and an audit trail that
        says otherwise is lying about what the procedure did.
        """
        return proc_state.model_copy(update={
            "current_step_id": step.next_step_id,
            "branch_history": proc_state.branch_history + [step.id],
            "last_updated_at": _now(),
        })

    # ── Bounded loop control ──────────────────────────────────────────────────

    @staticmethod
    def _loop_may_continue(step_result: StepResult) -> bool:
        """
        Is this non-completion an *iterable* outcome?

        A loop exists to wait for the world to reach a declared state. It is not
        a way to paper over an outcome that repetition cannot fix:

          * a validator reporting ``retryable=False`` (an unregistered predicate,
            a predicate that raised) will report it identically every iteration;
          * an executor that already ESCALATED has reported a terminal condition
            of its own, and the engine has never treated that as retryable.

        Both fall through to the normal failure handling so they escalate with
        their real reason rather than being relabelled as loop exhaustion.
        """
        if step_result.status is StepStatus.ESCALATED:
            return False
        validation = step_result.validation_result
        return validation is None or validation.retryable

    def _loop_decision(
        self,
        proc_state: ProcedureExecutionState,
        step: SOPStep,
    ) -> tuple[LoopDecision, str]:
        """
        Decide RETRY or EXHAUSTED for a loop whose criterion did not hold.

        Both bounds are held by the engine and read from the step's own declared
        policy. Nothing in this method consults the executor, the runtime, the
        model, or ``StepResult.output``.
        """
        loop = step.loop
        assert loop is not None  # only called for looping steps

        iterations = proc_state.loop_iterations(step.id)
        if iterations >= loop.max_iterations:
            return (
                LoopDecision.EXHAUSTED,
                f"Loop on step {step.id} ran its full budget of "
                f"{loop.max_iterations} iterations without the completion "
                "criterion holding.",
            )

        if loop.max_total_seconds is not None:
            started = proc_state.loop_started_at.get(step.id)
            if started is not None:
                elapsed = (_now() - started).total_seconds()
                if elapsed >= loop.max_total_seconds:
                    return (
                        LoopDecision.EXHAUSTED,
                        f"Loop on step {step.id} exceeded its total budget of "
                        f"{loop.max_total_seconds}s after {iterations} iteration(s).",
                    )

        return LoopDecision.RETRY, ""

    def _record_loop_exhaustion(
        self,
        proc_state: ProcedureExecutionState,
        step: SOPStep,
        step_result: StepResult,
        reason: str,
    ) -> ProcedureExecutionState:
        """
        Mark a loop as exhausted, preserving the last iteration's evidence.

        Recording the step_id in ``loop_exhausted_step_ids`` is what makes the
        outcome stick: even if the SOP routes to a tidy escalation-handling step
        that runs and validates cleanly, the procedure still terminates as
        ESCALATED. An unresolved exception must not be able to end as COMPLETED.
        """
        exhausted = step_result.model_copy(update={
            "status": StepStatus.ESCALATED,
            "escalation_reason": EscalationReasonCode.LOOP_BUDGET_EXHAUSTED,
            "escalation_message": step.escalation_reason or reason,
        })
        logger.warning(
            "SOPEngine: loop exhausted on step %s after %d iteration(s) — %s",
            step.id, proc_state.loop_iterations(step.id), reason,
        )
        return proc_state.model_copy(update={
            "step_results": {**proc_state.step_results, step.id: exhausted},
            "loop_exhausted_step_ids": proc_state.loop_exhausted_step_ids + [step.id],
            "last_updated_at": _now(),
        })

    @staticmethod
    def _terminal_status(proc_state: ProcedureExecutionState) -> ProcedureStatus:
        """A procedure that exhausted any loop terminates ESCALATED, not COMPLETED."""
        if proc_state.loop_exhausted_step_ids:
            return ProcedureStatus.ESCALATED
        return ProcedureStatus.COMPLETED

    @staticmethod
    def _stamp_attempt(
        evidence: list[EvidenceRef],
        step_id: str,
        attempt: int,
    ) -> list[EvidenceRef]:
        """
        Tag accumulated evidence with the attempt that produced it.

        ``step_results`` holds only the most recent result per step, so without
        this the audit trail for a loop could not distinguish "the SKU was still
        short on iteration 1" from "...and on iteration 3". Evidence is appended,
        never replaced, so every iteration's verdict survives in
        ``evidence_refs``.
        """
        return [
            ref.model_copy(update={
                "metadata": {**ref.metadata, "step_id": step_id, "attempt": attempt}
            })
            for ref in evidence
        ]

    def _escalate(
        self,
        proc_state: ProcedureExecutionState,
        reason_code: EscalationReasonCode,
        message: str,
        *,
        step_id: str | None = None,
    ) -> ProcedureExecutionState:
        """Terminate the procedure as ESCALATED, preserving the typed reason."""
        target_step = step_id or proc_state.current_step_id
        updates: dict[str, Any] = {
            "status": ProcedureStatus.ESCALATED,
            "last_updated_at": _now(),
        }
        if target_step is not None:
            existing = proc_state.step_results.get(target_step)
            escalated = (
                existing.model_copy(update={
                    "status": StepStatus.ESCALATED,
                    "escalation_reason": reason_code,
                    "escalation_message": message,
                })
                if existing is not None
                else StepResult(
                    step_id=target_step,
                    status=StepStatus.ESCALATED,
                    runtime="sop_engine",
                    started_at=_now(),
                    completed_at=_now(),
                    escalation_reason=reason_code,
                    escalation_message=message,
                )
            )
            updates["step_results"] = {**proc_state.step_results, target_step: escalated}

        logger.warning(
            "SOPEngine: escalating procedure %s at step %s — %s (%s)",
            proc_state.procedure_execution_id, target_step, message, reason_code.value,
        )
        return proc_state.model_copy(update=updates)

    def _init_state(
        self,
        sop: SOPDefinition,
        agent_task_id: str,
        context: AgentExecutionContext,
    ) -> ProcedureExecutionState:
        now = _now()
        return ProcedureExecutionState(
            procedure_execution_id=str(uuid.uuid4()),
            sop_id=sop.id,
            sop_version=sop.version,
            agent_task_id=agent_task_id,
            trace_id=context.trace_id or self._trace_id,
            current_step_id=None,
            status=ProcedureStatus.RUNNING,
            started_at=now,
            last_updated_at=now,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _missing_required_inputs(
        step: SOPStep,
        context: AgentExecutionContext,
    ) -> list[str]:
        if not step.required_inputs:
            return []
        bounded = context.bounded_context or {}
        return [key for key in step.required_inputs if key not in bounded]

    @staticmethod
    def _version_mismatch(
        proc_state: ProcedureExecutionState,
        sop: SOPDefinition,
    ) -> str | None:
        """
        Refuse to run a restored procedure against a different SOP version.

        ``sop_version`` on the procedure record is a pin, not a label. A
        procedure that completed steps 1–4 under v1.0 and would run steps 5–9
        under v1.1 has executed a procedure that never existed — the completed
        work and the remaining work came from different documents, and no audit
        of either one describes what actually happened.

        There is no auto-upgrade path and there is deliberately no override. If
        the pinned version cannot be supplied, the procedure fails safely with a
        structured reason and a human decides what to do, which is the correct
        outcome for a procedure that may already have written to the warehouse.
        """
        if proc_state.sop_id != sop.id:
            return (
                f"Restored procedure pins SOP {proc_state.sop_id!r} but was resumed "
                f"with SOP {sop.id!r}. Refusing to continue under a different procedure."
            )
        if proc_state.sop_version != sop.version:
            return (
                f"Restored procedure pins SOP {proc_state.sop_id!r} version "
                f"{proc_state.sop_version!r} but was resumed with version "
                f"{sop.version!r}. Procedures never auto-upgrade: supply the pinned "
                "version or escalate to a human."
            )
        return None

    @staticmethod
    def _is_indeterminate(execution_status: str) -> bool:
        lowered = execution_status.lower()
        return any(
            marker in lowered
            for marker in ("indeterminate", "unknown", "ambiguous", "timeout")
        )


__all__ = ["SOPEngine", "LoopDecision"]
