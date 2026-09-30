# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Bounded loop semantics — the generic SOP Engine, with no domain attached.

The invariant under test, in one sentence:

    The SOP Engine controls the loop. The model may provide evidence, but it
    cannot decide that the loop is finished.

Everything here uses ``t_loop_*`` throwaway predicates and synthetic SOPs. There
is no warehouse, no inventory, no SKU and no domain package import anywhere in
this file — that is deliberate. If any of these tests needed a warehouse to
pass, the loop would not be a reusable engine feature and the Standalone Engine
Qualification claim in the design doc would be false.

The adversarial cases are the point. A loop that merely counts to three is not
interesting; a loop that a model cannot talk its way out of is.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from maiw_agents.contracts.procedure_state import ProcedureStatus
from maiw_agents.contracts.sop import SOPStep, SOPValidationError, validate_sop
from maiw_agents.contracts.sop_v2 import (
    EscalationReasonCode,
    LoopPolicy,
    RetryPolicy,
    StepCompletionSpec,
    ValidatorType,
)
from maiw_agents.contracts.step_result import EvidenceRef, StepResult, StepStatus
from maiw_agents.sop_engine import SOPEngine
from maiw_agents.sop_engine.engine import LoopDecision
from maiw_agents.sop_engine.validators import register_predicate, unregister_predicate

from conftest import ScriptedExecutor, make_sop, make_step_result, now


# ── A world the loop can watch change ─────────────────────────────────────────


class FlippingWorld:
    """
    Authoritative state that becomes satisfactory after N reads.

    Separating "what the world is" from "what the executor says" is what makes
    it possible to test that the engine believes the former.
    """

    def __init__(self, satisfied_after: int = 99) -> None:
        self.reads = 0
        self._satisfied_after = satisfied_after

    def model_dump(self) -> dict[str, Any]:
        self.reads += 1
        return {"t_loop_ready": self.reads >= self._satisfied_after}


@pytest.fixture
def loop_predicate():
    """Register a throwaway predicate for the duration of one test."""
    name = "t_loop_ready"

    def predicate(state: dict[str, Any], args: dict[str, Any]) -> bool:
        return bool(state.get("t_loop_ready"))

    register_predicate(name, predicate)
    yield name
    unregister_predicate(name)


def loop_step(
    step_id: str = "reassess",
    *,
    predicate: str = "t_loop_ready",
    max_iterations: int = 3,
    exit_step_id: str | None = None,
    exhaustion_step_id: str | None = None,
    max_total_seconds: float | None = None,
    next_step_id: str | None = None,
) -> SOPStep:
    return SOPStep(
        id=step_id,
        action="no_op",
        next_step_id=next_step_id,
        completion=StepCompletionSpec(
            validator_type=ValidatorType.STATE_PREDICATE,
            predicate_name=predicate,
        ),
        loop=LoopPolicy(
            max_iterations=max_iterations,
            exit_step_id=exit_step_id,
            exhaustion_step_id=exhaustion_step_id,
            max_total_seconds=max_total_seconds,
        ),
    )


def terminal_step(step_id: str) -> SOPStep:
    return SOPStep(id=step_id, action="no_op", next_step_id=None)


async def run(sop, executor, snapshot, definition, context):
    engine = SOPEngine(executor=executor, trace_id=context.trace_id)
    return await engine.run_procedure(
        definition=definition,
        sop=sop,
        agent_task_id="task-loop",
        context=context,
        warehouse_state_snapshot=snapshot,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 1. A loop must be bounded above zero
# ══════════════════════════════════════════════════════════════════════════════


def test_loop_max_iterations_must_be_at_least_one():
    with pytest.raises(ValidationError):
        LoopPolicy(max_iterations=0)


def test_loop_max_iterations_has_a_hard_ceiling():
    """An unbounded-in-practice loop is not a bounded loop."""
    with pytest.raises(ValidationError):
        LoopPolicy(max_iterations=21)


def test_loop_total_seconds_must_be_positive():
    with pytest.raises(ValidationError):
        LoopPolicy(max_total_seconds=0.0)


def test_loop_defaults_are_conservative():
    policy = LoopPolicy()
    assert policy.max_iterations == 3
    assert policy.exit_step_id is None
    assert policy.exhaustion_step_id is None
    assert policy.max_total_seconds is None


# ══════════════════════════════════════════════════════════════════════════════
# 2. The attempt count is bounded and is the iteration count
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_loop_runs_exactly_max_iterations_when_never_satisfied(
    loop_predicate, definition, context
):
    sop = make_sop([loop_step(max_iterations=4)])
    executor = ScriptedExecutor()
    world = FlippingWorld(satisfied_after=99)  # never

    final = await run(sop, executor, world, definition, context)

    assert executor.step_ids == ["reassess"] * 4
    assert final.attempt_by_step["reassess"] == 4
    assert final.loop_iterations("reassess") == 4


@pytest.mark.asyncio
async def test_loop_iteration_counter_is_the_attempt_counter(
    loop_predicate, definition, context
):
    """
    A looping step may not also declare a retry_policy, so these two numbers are
    the same by construction. Asserting it here keeps them from quietly diverging.
    """
    sop = make_sop([loop_step(max_iterations=3)])
    executor = ScriptedExecutor()

    final = await run(sop, executor, FlippingWorld(), definition, context)

    step_id = "reassess"
    assert final.loop_iterations(step_id) == final.attempt_by_step[step_id] == 3
    # The engine hands each iteration its true cumulative attempt number.
    assert [attempt for _, attempt in executor.calls] == [1, 2, 3]


@pytest.mark.asyncio
async def test_non_looping_step_attempt_numbering_is_unchanged(definition, context):
    """Regression guard: cumulative attempts must not renumber ordinary retries."""
    sop = make_sop([
        SOPStep(
            id="plain",
            action="no_op",
            next_step_id=None,
            completion=StepCompletionSpec(
                validator_type=ValidatorType.SCHEMA, schema_fields=["never_present"]
            ),
            retry_policy=RetryPolicy(max_attempts=3, backoff_seconds=0.0),
        )
    ])
    executor = ScriptedExecutor()

    await run(sop, executor, None, definition, context)

    assert [attempt for _, attempt in executor.calls] == [1, 2, 3]


# ══════════════════════════════════════════════════════════════════════════════
# 3. The loop exits when the predicate holds — and only then
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_loop_exits_as_soon_as_the_predicate_holds(
    loop_predicate, definition, context
):
    sop = make_sop([
        loop_step(max_iterations=5, exit_step_id="done"),
        terminal_step("done"),
    ])
    executor = ScriptedExecutor()
    world = FlippingWorld(satisfied_after=2)

    final = await run(sop, executor, world, definition, context)

    assert final.status is ProcedureStatus.COMPLETED
    assert final.attempt_by_step["reassess"] == 2, "must not keep looping once satisfied"
    assert final.completed_step_ids == ["reassess", "done"]


@pytest.mark.asyncio
async def test_loop_exit_uses_exit_step_id_over_next_step_id(
    loop_predicate, definition, context
):
    sop = make_sop([
        loop_step(max_iterations=3, exit_step_id="via_exit", next_step_id="via_next"),
        terminal_step("via_exit"),
        terminal_step("via_next"),
    ])
    executor = ScriptedExecutor()

    final = await run(sop, executor, FlippingWorld(satisfied_after=1), definition, context)

    assert final.completed_step_ids == ["reassess", "via_exit"]
    assert "via_next" not in final.completed_step_ids


@pytest.mark.asyncio
async def test_loop_without_exit_step_id_falls_through_to_next_step_id(
    loop_predicate, definition, context
):
    sop = make_sop([
        loop_step(max_iterations=3, next_step_id="after"),
        terminal_step("after"),
    ])
    executor = ScriptedExecutor()

    final = await run(sop, executor, FlippingWorld(satisfied_after=1), definition, context)

    assert final.completed_step_ids == ["reassess", "after"]


@pytest.mark.asyncio
async def test_state_changing_mid_loop_exits_the_loop(loop_predicate, definition, context):
    """Failure path D: the world changes on attempt 2 and the loop notices."""
    sop = make_sop([loop_step(max_iterations=5, exit_step_id="done"), terminal_step("done")])
    executor = ScriptedExecutor()
    world = FlippingWorld(satisfied_after=2)

    final = await run(sop, executor, world, definition, context)

    assert final.status is ProcedureStatus.COMPLETED
    assert world.reads == 2, "the loop re-read authoritative state each iteration"


# ══════════════════════════════════════════════════════════════════════════════
# 4. Exhaustion escalates — and cannot be laundered into success
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_exhaustion_without_a_handler_escalates_the_procedure(
    loop_predicate, definition, context
):
    sop = make_sop([loop_step(max_iterations=2)])
    executor = ScriptedExecutor()

    final = await run(sop, executor, FlippingWorld(), definition, context)

    assert final.status is ProcedureStatus.ESCALATED
    assert final.loop_exhausted_step_ids == ["reassess"]
    result = final.step_results["reassess"]
    assert result.status is StepStatus.ESCALATED
    assert result.escalation_reason is EscalationReasonCode.LOOP_BUDGET_EXHAUSTED


@pytest.mark.asyncio
async def test_exhaustion_routes_to_the_declared_handler(
    loop_predicate, definition, context
):
    sop = make_sop([
        loop_step(max_iterations=2, exit_step_id="done", exhaustion_step_id="escalate"),
        terminal_step("done"),
        terminal_step("escalate"),
    ])
    executor = ScriptedExecutor()

    final = await run(sop, executor, FlippingWorld(), definition, context)

    assert "escalate" in final.completed_step_ids
    assert "done" not in final.completed_step_ids


@pytest.mark.asyncio
async def test_a_clean_escalation_handler_cannot_turn_exhaustion_into_completion(
    loop_predicate, definition, context
):
    """
    The handler step runs and validates perfectly well. The PROCEDURE must still
    end ESCALATED — an unresolved exception that reports itself tidily is still
    an unresolved exception.
    """
    sop = make_sop([
        loop_step(max_iterations=2, exhaustion_step_id="escalate"),
        terminal_step("escalate"),
    ])
    executor = ScriptedExecutor()

    final = await run(sop, executor, FlippingWorld(), definition, context)

    assert final.step_results["escalate"].status is StepStatus.COMPLETED
    assert final.status is ProcedureStatus.ESCALATED
    assert final.loop_exhausted_step_ids == ["reassess"]


@pytest.mark.asyncio
async def test_exhaustion_message_names_the_budget(loop_predicate, definition, context):
    sop = make_sop([loop_step(max_iterations=2)])

    final = await run(sop, ScriptedExecutor(), FlippingWorld(), definition, context)

    message = final.step_results["reassess"].escalation_message or ""
    assert "2" in message and "reassess" in message


# ══════════════════════════════════════════════════════════════════════════════
# 5. The loop is bounded by wall clock as well as by count
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_loop_total_time_budget_ends_the_loop_early(
    loop_predicate, definition, context
):
    """
    max_iterations is generous; max_total_seconds is not. The loop must stop on
    whichever bound is reached first.
    """
    sop = make_sop([loop_step(max_iterations=20, max_total_seconds=0.05)])

    class SlowExecutor(ScriptedExecutor):
        async def execute_step(self, **kwargs):
            await asyncio.sleep(0.03)
            return await super().execute_step(**kwargs)

    executor = SlowExecutor()
    final = await run(sop, executor, FlippingWorld(), definition, context)

    assert final.status is ProcedureStatus.ESCALATED
    assert final.loop_exhausted_step_ids == ["reassess"]
    assert final.attempt_by_step["reassess"] < 20, "time budget must bind before the count"
    assert "budget" in (final.step_results["reassess"].escalation_message or "")


@pytest.mark.asyncio
async def test_loop_start_time_is_recorded_once_not_per_iteration(
    loop_predicate, definition, context
):
    """The time budget spans the whole loop; restamping it each pass would void it."""
    sop = make_sop([loop_step(max_iterations=3)])

    final = await run(sop, ScriptedExecutor(), FlippingWorld(), definition, context)

    assert "reassess" in final.loop_started_at
    assert final.loop_started_at["reassess"] <= final.last_updated_at


# ══════════════════════════════════════════════════════════════════════════════
# 6. Evidence survives every iteration
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_every_iteration_contributes_evidence(loop_predicate, definition, context):
    sop = make_sop([loop_step(max_iterations=3)])

    final = await run(sop, ScriptedExecutor(), FlippingWorld(), definition, context)

    verdicts = [
        ref for ref in final.evidence_refs
        if ref.metadata.get("step_id") == "reassess"
    ]
    attempts = sorted({ref.metadata.get("attempt") for ref in verdicts})
    assert attempts == [1, 2, 3], "no iteration's evidence may be lost"


@pytest.mark.asyncio
async def test_evidence_names_the_predicate_that_was_evaluated(
    loop_predicate, definition, context
):
    sop = make_sop([loop_step(max_iterations=2)])

    final = await run(sop, ScriptedExecutor(), FlippingWorld(), definition, context)

    named = [
        ref for ref in final.evidence_refs
        if ref.metadata.get("predicate_name") == "t_loop_ready"
    ]
    assert len(named) == 2


@pytest.mark.asyncio
async def test_step_results_holds_the_latest_iteration_evidence_refs_hold_all(
    loop_predicate, definition, context
):
    """
    ``step_results`` is a step_id → latest-result map by design. The complete
    per-iteration trail lives in ``evidence_refs``, which is append-only.
    """
    sop = make_sop([loop_step(max_iterations=3)])

    final = await run(sop, ScriptedExecutor(), FlippingWorld(), definition, context)

    assert final.step_results["reassess"].attempt == 3
    reassess_refs = [
        r for r in final.evidence_refs if r.metadata.get("step_id") == "reassess"
    ]
    assert len(reassess_refs) >= 3


# ══════════════════════════════════════════════════════════════════════════════
# 7. A duplicate attempt does not double-advance
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_each_iteration_advances_the_counter_exactly_once(
    loop_predicate, definition, context
):
    sop = make_sop([loop_step(max_iterations=4)])
    executor = ScriptedExecutor()

    final = await run(sop, executor, FlippingWorld(), definition, context)

    assert len(executor.calls) == final.attempt_by_step["reassess"] == 4


@pytest.mark.asyncio
async def test_looping_step_is_completed_once_not_once_per_iteration(
    loop_predicate, definition, context
):
    sop = make_sop([
        loop_step(max_iterations=5, exit_step_id="done"),
        terminal_step("done"),
    ])

    final = await run(sop, ScriptedExecutor(), FlippingWorld(satisfied_after=3), definition, context)

    assert final.completed_step_ids.count("reassess") == 1


# ══════════════════════════════════════════════════════════════════════════════
# 8. The model cannot force an exit
# ══════════════════════════════════════════════════════════════════════════════


class ClaimsSuccessExecutor(ScriptedExecutor):
    """A runtime that insists, every single time, that the step is done."""

    RUNTIME_NAME = "overconfident_model"

    async def execute_step(self, *, step, attempt, **kwargs):
        self.calls.append((step.id, attempt))
        return make_step_result(
            step.id,
            status=StepStatus.COMPLETED,
            output={"done": True, "confidence": 1.0},
            runtime=self.RUNTIME_NAME,
            attempt=attempt,
        )


@pytest.mark.asyncio
async def test_model_claiming_completed_cannot_exit_the_loop(
    loop_predicate, definition, context
):
    sop = make_sop([
        loop_step(max_iterations=3, exit_step_id="done"),
        terminal_step("done"),
    ])
    executor = ClaimsSuccessExecutor()
    world = FlippingWorld(satisfied_after=99)  # the world never agrees

    final = await run(sop, executor, world, definition, context)

    assert len(executor.calls) == 3, "the model's claim did not shorten the loop"
    assert final.status is ProcedureStatus.ESCALATED
    assert "done" not in final.completed_step_ids


@pytest.mark.asyncio
async def test_model_output_cannot_supply_loop_control_fields(
    loop_predicate, definition, context
):
    """
    A runtime returning ``exit_loop``/``iterations_remaining`` in its output
    changes nothing: the engine reads neither.
    """

    class LoopControlSmugglingExecutor(ScriptedExecutor):
        async def execute_step(self, *, step, attempt, **kwargs):
            self.calls.append((step.id, attempt))
            return make_step_result(
                step.id,
                status=StepStatus.FAILED,
                output={
                    "exit_loop": True,
                    "iterations_remaining": 99,
                    "max_iterations": 99,
                    "loop": {"exit_step_id": "done"},
                },
                attempt=attempt,
            )

    sop = make_sop([
        loop_step(max_iterations=2, exit_step_id="done"),
        terminal_step("done"),
    ])
    executor = LoopControlSmugglingExecutor()

    final = await run(sop, executor, FlippingWorld(), definition, context)

    assert len(executor.calls) == 2
    assert final.status is ProcedureStatus.ESCALATED


# ══════════════════════════════════════════════════════════════════════════════
# 9. The model cannot force an extra iteration
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_model_claiming_failure_cannot_extend_a_satisfied_loop(
    loop_predicate, definition, context
):
    """
    The mirror image of the previous section. The world is satisfactory on the
    first read; a runtime reporting FAILED must not buy itself another pass.
    """

    class ClaimsFailureExecutor(ScriptedExecutor):
        """Cries failure on the loop step only, so the exit path stays observable."""

        async def execute_step(self, *, step, attempt, **kwargs):
            if step.id != "reassess":
                return await super().execute_step(step=step, attempt=attempt, **kwargs)
            self.calls.append((step.id, attempt))
            return make_step_result(
                step.id, status=StepStatus.FAILED, output={}, attempt=attempt
            )

    sop = make_sop([
        loop_step(max_iterations=5, exit_step_id="done"),
        terminal_step("done"),
    ])
    executor = ClaimsFailureExecutor()

    final = await run(sop, executor, FlippingWorld(satisfied_after=1), definition, context)

    reassess_calls = [c for c in executor.calls if c[0] == "reassess"]
    assert len(reassess_calls) == 1, "the validator, not the runtime, ended the loop"
    assert final.status is ProcedureStatus.COMPLETED


@pytest.mark.asyncio
async def test_a_model_cannot_exceed_the_iteration_budget_by_any_means(
    loop_predicate, definition, context
):
    sop = make_sop([loop_step(max_iterations=2)])
    executor = ScriptedExecutor()

    final = await run(sop, executor, FlippingWorld(satisfied_after=1000), definition, context)

    assert len(executor.calls) == 2
    assert final.attempt_by_step["reassess"] == 2


def test_executor_protocol_exposes_no_loop_control():
    """The runtime seam has no parameter through which loop control could arrive."""
    from maiw_agents.sop_engine.executor import SOPStepExecutor

    params = set(inspect.signature(SOPStepExecutor.execute_step).parameters)
    assert params == {
        "self", "definition", "step", "procedure_state", "context", "attempt",
    }
    for forbidden in ("iterations_remaining", "loop", "max_iterations", "should_continue"):
        assert forbidden not in params


# ══════════════════════════════════════════════════════════════════════════════
# 10. A write step can never be loop-retried
# ══════════════════════════════════════════════════════════════════════════════


def test_loop_on_a_governed_write_action_is_rejected_at_construction():
    with pytest.raises(ValidationError, match="governed write action"):
        SOPStep(
            id="propose",
            action="emit_recommended_action",
            next_step_id=None,
            completion=StepCompletionSpec(
                validator_type=ValidatorType.STATE_PREDICATE,
                predicate_name="t_loop_ready",
            ),
            loop=LoopPolicy(max_iterations=3),
        )


def test_governed_write_actions_are_declared_not_inferred():
    from maiw_agents.contracts.sop import GOVERNED_WRITE_ACTIONS

    assert "emit_recommended_action" in GOVERNED_WRITE_ACTIONS


def test_retry_policy_still_refuses_ambiguous_write_states():
    """The pre-existing no-blind-retry rule must be untouched by loop support."""
    with pytest.raises(ValidationError):
        RetryPolicy(retry_on=["WRITE_AMBIGUOUS"])
    with pytest.raises(ValidationError):
        RetryPolicy(retry_on=["EXECUTION_INDETERMINATE"])


# ══════════════════════════════════════════════════════════════════════════════
# 11. Structural rules that make the loop safe by construction
# ══════════════════════════════════════════════════════════════════════════════


def test_loop_requires_an_explicit_completion_spec():
    with pytest.raises(ValidationError, match="no completion spec"):
        SOPStep(id="s", action="no_op", loop=LoopPolicy())


def test_loop_rejects_legacy_success_as_an_exit_criterion():
    with pytest.raises(ValidationError, match="LEGACY_SUCCESS"):
        SOPStep(
            id="s",
            action="no_op",
            completion=StepCompletionSpec(validator_type=ValidatorType.LEGACY_SUCCESS),
            loop=LoopPolicy(),
        )


def test_loop_and_retry_policy_are_mutually_exclusive():
    with pytest.raises(ValidationError, match="mutually exclusive"):
        SOPStep(
            id="s",
            action="no_op",
            completion=StepCompletionSpec(
                validator_type=ValidatorType.SCHEMA, schema_fields=["x"]
            ),
            loop=LoopPolicy(),
            retry_policy=RetryPolicy(),
        )


@pytest.mark.parametrize("field_name", ["exit_step_id", "exhaustion_step_id"])
def test_loop_targets_may_not_be_the_loop_step_itself(field_name):
    with pytest.raises(ValidationError, match="must not be the loop step itself"):
        SOPStep(
            id="s",
            action="no_op",
            completion=StepCompletionSpec(
                validator_type=ValidatorType.SCHEMA, schema_fields=["x"]
            ),
            loop=LoopPolicy(**{field_name: "s"}),
        )


def test_validate_sop_rejects_unknown_loop_targets():
    sop = make_sop([loop_step(exhaustion_step_id="nowhere"), terminal_step("done")])
    with pytest.raises(SOPValidationError, match="unknown step 'nowhere'"):
        validate_sop(sop)


def test_validate_sop_rejects_a_loop_reachable_from_its_own_exit():
    """An outer cycle would reset the counter and void the bound entirely."""
    sop = make_sop([
        loop_step(exit_step_id="cleanup"),
        SOPStep(id="cleanup", action="no_op", next_step_id="reassess"),
    ])
    with pytest.raises(SOPValidationError, match="reachable from its own exit"):
        validate_sop(sop)


def test_validate_sop_rejects_a_loop_reachable_from_its_own_exhaustion_branch():
    sop = make_sop([
        loop_step(exit_step_id="done", exhaustion_step_id="retry_everything"),
        terminal_step("done"),
        SOPStep(id="retry_everything", action="no_op", next_step_id="reassess"),
    ])
    with pytest.raises(SOPValidationError, match="reachable from its own exit"):
        validate_sop(sop)


def test_validate_sop_accepts_a_well_formed_loop():
    sop = make_sop([
        loop_step(exit_step_id="done", exhaustion_step_id="escalate"),
        terminal_step("done"),
        terminal_step("escalate"),
    ])
    validate_sop(sop)  # must not raise


# ══════════════════════════════════════════════════════════════════════════════
# 12. Non-iterable outcomes are not relabelled as loop exhaustion
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_unknown_predicate_escalates_immediately_without_looping(
    definition, context
):
    """
    A missing predicate reports ``retryable=False``. Looping on it would waste
    the budget and then blame the wrong thing.
    """
    sop = make_sop([loop_step(predicate="t_loop_not_registered", max_iterations=5)])
    executor = ScriptedExecutor()

    final = await run(sop, executor, FlippingWorld(), definition, context)

    assert len(executor.calls) == 1, "a non-retryable verdict must not be looped"
    assert final.status is ProcedureStatus.FAILED
    assert final.loop_exhausted_step_ids == []


@pytest.mark.asyncio
async def test_executor_escalation_inside_a_loop_is_final(loop_predicate, definition, context):
    """Failure path B: a capability reported unavailable is not a loop iteration."""

    class UnavailableExecutor(ScriptedExecutor):
        async def execute_step(self, *, step, attempt, **kwargs):
            self.calls.append((step.id, attempt))
            return StepResult(
                step_id=step.id,
                status=StepStatus.ESCALATED,
                runtime="test",
                attempt=attempt,
                started_at=now(),
                completed_at=now(),
                escalation_reason=EscalationReasonCode.CAPABILITY_UNAVAILABLE,
            )

    sop = make_sop([loop_step(max_iterations=5)])
    executor = UnavailableExecutor()

    final = await run(sop, executor, FlippingWorld(), definition, context)

    assert len(executor.calls) == 1
    assert final.status is ProcedureStatus.ESCALATED
    assert (
        final.step_results["reassess"].escalation_reason
        is EscalationReasonCode.CAPABILITY_UNAVAILABLE
    ), "the real reason must survive, not be replaced by loop exhaustion"


# ══════════════════════════════════════════════════════════════════════════════
# 13. The loop state machine itself
# ══════════════════════════════════════════════════════════════════════════════


def test_loop_decision_has_exactly_three_states():
    assert {d.value for d in LoopDecision} == {"exit", "retry", "exhausted"}


def test_loop_decision_is_owned_by_the_engine_module():
    assert LoopDecision.__module__ == "maiw_agents.sop_engine.engine"


@pytest.mark.parametrize(
    "iterations,max_iterations,expected",
    [(0, 3, LoopDecision.RETRY), (2, 3, LoopDecision.RETRY), (3, 3, LoopDecision.EXHAUSTED)],
)
def test_loop_decision_boundary(iterations, max_iterations, expected, definition, context):
    from conftest import make_procedure_state

    engine = SOPEngine(executor=ScriptedExecutor())
    step = loop_step(max_iterations=max_iterations)
    state = make_procedure_state(
        current_step_id="reassess",
        attempt_by_step={"reassess": iterations} if iterations else {},
    )

    decision, _ = engine._loop_decision(state, step)
    assert decision is expected


# ══════════════════════════════════════════════════════════════════════════════
# 14. The loop is domain-neutral
# ══════════════════════════════════════════════════════════════════════════════


ENGINE_PATH = (
    Path(__file__).resolve().parent.parent / "maiw_agents" / "sop_engine" / "engine.py"
)

# Matched against whole underscore-separated identifier segments, so `timezone`
# does not count as `zone` and `attempt` does not count as `temp`.
_WAREHOUSE_TOKENS = frozenset({
    "inventory", "sku", "skus", "picking", "pick", "picks", "equipment",
    "forklift", "labor", "worker", "workers", "wave", "waves", "replenish",
    "replenishment", "zone", "zones", "bin", "bins", "location", "locations",
    "order", "orders", "carrier", "cutoff",
})


def test_engine_module_imports_nothing_domain_specific():
    tree = ast.parse(ENGINE_PATH.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
            imported.extend(a.name for a in node.names)

    for name in imported:
        lowered = name.lower()
        for token in ("inventory", "equipment", "labor", "wave", "picking"):
            assert token not in lowered, (
                f"generic SOP engine imports domain module/name {name!r} — the loop "
                "must be reusable outside the warehouse domain"
            )


def test_engine_code_contains_no_warehouse_vocabulary():
    """
    Docstrings may say 'warehouse_state_snapshot' (a parameter name that predates
    this work); executable code must not name a domain concept.
    """
    tree = ast.parse(ENGINE_PATH.read_text(encoding="utf-8"))
    offenders: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            candidate = node.id.lower()
        elif isinstance(node, ast.Attribute):
            candidate = node.attr.lower()
        else:
            continue  # string constants are docstrings and log messages
        # `warehouse_state_snapshot` is the pre-existing name of the opaque
        # state handle the engine passes through without interpreting.
        if candidate.startswith("warehouse_state"):
            continue
        if _WAREHOUSE_TOKENS & set(candidate.split("_")):
            offenders.add(candidate)
    assert not offenders, f"domain vocabulary in generic engine code: {sorted(offenders)}"


def test_loop_contracts_import_no_domain_module():
    for module in ("sop_v2.py", "procedure_state.py"):
        path = Path(__file__).resolve().parent.parent / "maiw_agents" / "contracts" / module
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names]
                if isinstance(node, ast.ImportFrom):
                    names.append(node.module or "")
                for name in names:
                    for token in ("inventory", "equipment", "labor", "wave"):
                        assert token not in name.lower(), (
                            f"{module} imports domain name {name!r}"
                        )


def test_this_test_module_imports_no_domain_package():
    """
    Meta-test. If the generic loop suite ever needs a domain package to pass,
    the loop is not a generic engine feature.
    """
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for token in ("inventory", "equipment", "labor", "wave"):
                assert token not in node.module.lower(), (
                    f"generic loop tests import domain module {node.module!r}"
                )


# ══════════════════════════════════════════════════════════════════════════════
# 15. No workflow DSL was introduced
# ══════════════════════════════════════════════════════════════════════════════


def test_loop_policy_has_no_expression_field():
    fields = set(LoopPolicy.model_fields)
    assert fields == {
        "max_iterations", "exit_step_id", "exhaustion_step_id", "max_total_seconds",
    }
    for forbidden in ("condition", "expression", "while_", "until", "predicate", "body"):
        assert forbidden not in fields


def test_loop_policy_contains_no_eval():
    source = inspect.getsource(LoopPolicy)
    for token in ("eval(", "exec(", "compile(", "__import__"):
        assert token not in source


def test_loop_body_is_a_single_step_not_a_sequence():
    """
    A multi-step loop body could re-enter a governed write. The contract offers
    no way to express one: there is no ``loop_back_step_id``.
    """
    assert "loop_back_step_id" not in LoopPolicy.model_fields
    assert "body_step_ids" not in LoopPolicy.model_fields


# ══════════════════════════════════════════════════════════════════════════════
# 16. Backward compatibility
# ══════════════════════════════════════════════════════════════════════════════


def test_loop_is_optional_and_defaults_to_none():
    step = SOPStep(id="s", action="no_op")
    assert step.loop is None


@pytest.mark.asyncio
async def test_a_sop_with_no_loops_behaves_exactly_as_before(definition, context):
    sop = make_sop([
        SOPStep(id="a", action="no_op", next_step_id="b"),
        SOPStep(id="b", action="no_op", next_step_id=None),
    ])
    executor = ScriptedExecutor()

    final = await run(sop, executor, None, definition, context)

    assert final.status is ProcedureStatus.COMPLETED
    assert final.completed_step_ids == ["a", "b"]
    assert final.loop_exhausted_step_ids == []
    assert final.loop_started_at == {}


@pytest.mark.asyncio
async def test_a_skipped_step_is_traversed_but_not_completed(definition, context):
    """
    A step whose condition did not hold never reached the executor and never
    faced a validator. It belongs in branch_history, which records traversal,
    and not in completed_step_ids, which records completion.
    """
    from maiw_agents.contracts.sop import StepCondition

    sop = make_sop([
        SOPStep(
            id="conditional",
            action="no_op",
            next_step_id="always",
            condition=StepCondition(
                predicate="primary_constraint", operator="eq", value="not_this_one"
            ),
        ),
        terminal_step("always"),
    ])
    executor = ScriptedExecutor()

    final = await run(sop, executor, None, definition, context)

    assert executor.step_ids == ["always"], "skipped step must not reach the executor"
    assert final.branch_history == ["conditional", "always"]
    assert final.completed_step_ids == ["always"]
    assert "conditional" not in final.completed_step_ids


def test_procedure_state_loop_fields_default_empty():
    from conftest import make_procedure_state

    state = make_procedure_state()
    assert state.loop_started_at == {}
    assert state.loop_exhausted_step_ids == []
    assert state.loop_iterations("anything") == 0


def test_procedure_state_with_a_loop_is_serializable():
    """A loop must survive a round trip: bounded, deterministic, and persistable."""
    from conftest import make_procedure_state

    state = make_procedure_state(
        current_step_id="reassess",
        attempt_by_step={"reassess": 2},
        loop_exhausted_step_ids=["reassess"],
        evidence_refs=[
            EvidenceRef(
                type="validator_result",
                source="state_predicate",
                timestamp=now(),
                metadata={"step_id": "reassess", "attempt": 2},
            )
        ],
    )
    restored = type(state).model_validate_json(state.model_dump_json())

    assert restored.loop_iterations("reassess") == 2
    assert restored.loop_exhausted_step_ids == ["reassess"]
    assert restored.evidence_refs[0].metadata["attempt"] == 2
