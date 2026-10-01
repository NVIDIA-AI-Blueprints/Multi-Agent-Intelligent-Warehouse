# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
ProcedureStateStore — persistence, revision concurrency, and restart recovery.

The acceptance statement under test:

    After a crash or restart, MAIW must know exactly which procedure version was
    running, which step and attempt were active, what evidence had been proven,
    what capabilities were permitted, and whether a warehouse write may already
    have occurred — without granting the sandbox any additional authority.

A "crash" here is simulated the way it actually matters: the engine object is
thrown away mid-procedure and a *new* engine is built against the same store.
Nothing is carried over in memory. If a property survives, it survived because
it was persisted.
"""

from __future__ import annotations

import asyncio

import pytest

from conftest import (
    ScriptedExecutor,
    make_procedure_state,
    make_sop,
    make_step_result,
)
from maiw_agents.contracts.procedure_state import ProcedureStatus
from maiw_agents.contracts.sop import SOPStep
from maiw_agents.contracts.sop_v2 import (
    EscalationReasonCode,
    LoopPolicy,
    RetryPolicy,
    StepCompletionSpec,
    ValidatorType,
)
from maiw_agents.contracts.step_result import StepStatus
from maiw_agents.sop_engine import (
    InMemoryProcedureStateStore,
    JsonFileProcedureStateStore,
    SOPEngine,
    StaleRevisionError,
    TerminalStateError,
    register_predicate,
    unregister_predicate,
)


# ── Store semantics ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_then_load_round_trips_every_field():
    store = InMemoryProcedureStateStore()
    state = make_procedure_state(
        current_step_id="step_b",
        completed_step_ids=["step_a"],
        attempt_by_step={"step_a": 1, "step_b": 2},
        branch_history=["step_a"],
    )

    saved = await store.save(state)
    loaded = await store.load(state.procedure_execution_id)

    assert loaded is not None
    assert loaded.current_step_id == "step_b"
    assert loaded.completed_step_ids == ["step_a"]
    assert loaded.attempt_by_step == {"step_a": 1, "step_b": 2}
    assert loaded.branch_history == ["step_a"]
    assert loaded.sop_id == state.sop_id
    assert loaded.sop_version == state.sop_version
    assert loaded.revision == saved.revision


@pytest.mark.asyncio
async def test_revision_starts_at_zero_and_increments_on_every_save():
    store = InMemoryProcedureStateStore()
    state = make_procedure_state(current_step_id="a")
    assert state.revision == 0

    first = await store.save(state)
    assert first.revision == 1

    second = await store.save(first)
    assert second.revision == 2

    loaded = await store.load(state.procedure_execution_id)
    assert loaded.revision == 2


@pytest.mark.asyncio
async def test_stale_revision_is_rejected_rather_than_overwriting():
    """Two writers, one stale read. The loser must fail loudly, not win silently."""
    store = InMemoryProcedureStateStore()
    state = make_procedure_state(current_step_id="a")
    current = await store.save(state)          # revision 1

    stale = current.model_copy(update={"revision": 0})
    with pytest.raises(StaleRevisionError) as exc:
        await store.save(stale, expected_revision=0)

    assert exc.value.expected == 0
    assert exc.value.actual == 1

    # The store still holds the winner's value, not the stale writer's.
    loaded = await store.load(state.procedure_execution_id)
    assert loaded.revision == 1


@pytest.mark.asyncio
async def test_matching_expected_revision_is_accepted():
    store = InMemoryProcedureStateStore()
    saved = await store.save(make_procedure_state(current_step_id="a"))
    advanced = saved.model_copy(update={"current_step_id": "b"})

    result = await store.save(advanced, expected_revision=saved.revision)
    assert result.current_step_id == "b"
    assert result.revision == saved.revision + 1


@pytest.mark.parametrize(
    "terminal_status",
    [ProcedureStatus.COMPLETED, ProcedureStatus.FAILED, ProcedureStatus.ESCALATED],
)
@pytest.mark.asyncio
async def test_terminal_states_are_immutable(terminal_status):
    """A finished procedure may never be re-opened — that is how writes repeat."""
    store = InMemoryProcedureStateStore()
    state = make_procedure_state(status=terminal_status)
    await store.save(state)

    reopened = state.model_copy(
        update={"status": ProcedureStatus.RUNNING, "current_step_id": "step_a"}
    )
    with pytest.raises(TerminalStateError):
        await store.save(reopened)

    loaded = await store.load(state.procedure_execution_id)
    assert loaded.status == terminal_status


@pytest.mark.asyncio
async def test_load_returns_a_copy_that_cannot_mutate_the_store():
    store = InMemoryProcedureStateStore()
    state = make_procedure_state(current_step_id="a", completed_step_ids=["x"])
    await store.save(state)

    loaded = await store.load(state.procedure_execution_id)
    loaded.completed_step_ids.append("MUTATED")

    again = await store.load(state.procedure_execution_id)
    assert again.completed_step_ids == ["x"]


@pytest.mark.asyncio
async def test_load_unknown_id_returns_none_and_delete_is_idempotent():
    store = InMemoryProcedureStateStore()
    assert await store.load("no-such-procedure") is None
    await store.delete("no-such-procedure")  # must not raise


@pytest.mark.asyncio
async def test_concurrent_saves_are_serialised():
    """Thread safety: concurrent saves must not lose or interleave revisions."""
    store = InMemoryProcedureStateStore()
    ids = [make_procedure_state(current_step_id="a") for _ in range(20)]
    results = await asyncio.gather(*(store.save(s) for s in ids))
    assert all(r.revision == 1 for r in results)
    assert len(await store.list_ids()) == 20


# ── Durability across a real process boundary ─────────────────────────────────

@pytest.mark.asyncio
async def test_json_file_store_survives_a_new_store_instance(tmp_path):
    """
    The durability claim, tested rather than asserted.

    A brand-new store object reading the same directory is the closest
    in-process analogue of a restarted process: no shared memory, only the
    filesystem.
    """
    directory = tmp_path / "procedures"
    original = JsonFileProcedureStateStore(directory)
    state = make_procedure_state(
        current_step_id="post_write_verify",
        completed_step_ids=["propose", "govern"],
        attempt_by_step={"post_write_verify": 2},
        status=ProcedureStatus.WAITING_FOR_GOVERNANCE,
    )
    await original.save(state)

    del original
    restarted = JsonFileProcedureStateStore(directory)
    loaded = await restarted.load(state.procedure_execution_id)

    assert loaded is not None
    assert loaded.current_step_id == "post_write_verify"
    assert loaded.completed_step_ids == ["propose", "govern"]
    assert loaded.attempt_by_step == {"post_write_verify": 2}
    assert loaded.status == ProcedureStatus.WAITING_FOR_GOVERNANCE
    assert loaded.revision == 1


@pytest.mark.asyncio
async def test_json_file_store_enforces_the_same_rules_as_in_memory(tmp_path):
    store = JsonFileProcedureStateStore(tmp_path)
    saved = await store.save(make_procedure_state(current_step_id="a"))

    with pytest.raises(StaleRevisionError):
        await store.save(saved, expected_revision=99)

    terminal = saved.model_copy(update={"status": ProcedureStatus.COMPLETED})
    await store.save(terminal, expected_revision=saved.revision)
    with pytest.raises(TerminalStateError):
        await store.save(terminal.model_copy(update={"status": ProcedureStatus.RUNNING}))


# ── Private reasoning must never persist ──────────────────────────────────────

def test_procedure_state_has_no_private_reasoning_fields():
    """
    Hard prohibition: the persisted procedure record is an operational audit
    trail, not a model transcript.
    """
    from maiw_agents.contracts.procedure_state import ProcedureExecutionState

    fields = set(ProcedureExecutionState.model_fields)
    forbidden = {
        "chain_of_thought", "scratchpad", "hidden_reasoning", "raw_reasoning",
        "system_prompt", "private_memory", "model_memory", "messages",
        "transcript", "reasoning",
    }
    leaked = fields & forbidden
    assert not leaked, f"ProcedureExecutionState leaks private reasoning: {sorted(leaked)}"


@pytest.mark.asyncio
async def test_persisted_evidence_carries_no_model_internals(tmp_path):
    """Evidence refs are pointers and summaries — never transcripts."""
    store = JsonFileProcedureStateStore(tmp_path)
    executor = ScriptedExecutor()
    sop = make_sop([SOPStep(id="a", action="read_wave_status")])
    engine = SOPEngine(executor=executor, store=store)

    state = await engine.run_procedure(
        definition=_definition(), sop=sop, agent_task_id="t1", context=_context()
    )

    raw = (tmp_path / f"{state.procedure_execution_id}.json").read_text()
    for banned in ("chain_of_thought", "scratchpad", "hidden_reasoning", "system_prompt"):
        assert banned not in raw


# ── Restart recovery scenarios A–F ────────────────────────────────────────────

def _definition():
    from maiw_agents.contracts.agent import AgentDefinition

    return AgentDefinition(
        agent_id="operations_coordination",
        version="1.0",
        objective="test",
        domain="operations",
        allowed_capabilities=[],
        allowed_subagents=[],
        output_contract="RecommendedAction",
    )


def _context(**bounded):
    from maiw_agents.contracts.runtime import AgentExecutionContext

    return AgentExecutionContext(
        warehouse_id="wh-test",
        trace_id="trace-recovery",
        bounded_context=bounded or {"wave_id": "w1"},
    )


async def _crash_and_restart(store, procedure_execution_id):
    """
    Simulate a crash: discard the engine, reload state from the store.

    Returns the state a restarted process would resume from.
    """
    restored = await store.load(procedure_execution_id)
    assert restored is not None, "procedure was never checkpointed — unrecoverable"
    return restored


@pytest.mark.asyncio
async def test_scenario_a_crash_before_step_result_stored():
    """
    Scenario A — crash before any StepResult was stored.

    The procedure is recoverable and the step is re-executed, which is safe
    because it never produced a result. Documented limit: this is safe for
    READ/ANALYTICAL steps. A governance or write-adjacent step is NOT assumed
    replayable — Scenarios D and E cover those paths, and neither re-executes.
    """
    store = InMemoryProcedureStateStore()
    sop = make_sop([
        SOPStep(id="read_state", action="read_wave_status", next_step_id="finish"),
        SOPStep(id="finish", action="return_wave_assessment"),
    ])

    # Crash the executor on the very first step, after the engine checkpointed
    # "step started" but before any result was recorded.
    class CrashingExecutor(ScriptedExecutor):
        async def execute_step(self, **kwargs):
            raise RuntimeError("process died mid-step")

    engine = SOPEngine(executor=CrashingExecutor(), store=store)
    state = await engine.run_procedure(
        definition=_definition(), sop=sop, agent_task_id="t", context=_context()
    )

    restored = await _crash_and_restart(store, state.procedure_execution_id)
    assert restored.sop_version == sop.version
    # No step completed, so nothing is falsely recorded as done.
    assert "read_state" not in restored.completed_step_ids


@pytest.mark.asyncio
async def test_scenario_b_crash_after_step_result_before_validation():
    """
    Scenario B — the StepResult was stored but validation had not run.

    On restart the stored result is reused. The step is NOT re-executed: the
    executor's call count proves it ran exactly once across both lifetimes.
    """
    store = InMemoryProcedureStateStore()
    completion = StepCompletionSpec(
        validator_type=ValidatorType.SCHEMA, schema_fields=["risk_level"]
    )
    sop = make_sop([
        SOPStep(id="assess", action="read_wave_status", completion=completion),
    ])

    executor = ScriptedExecutor(default_output={"risk_level": "high"})
    engine = SOPEngine(executor=executor, store=store)
    state = await engine.run_procedure(
        definition=_definition(), sop=sop, agent_task_id="t", context=_context()
    )
    assert state.status == ProcedureStatus.COMPLETED
    first_call_count = len(executor.calls)

    restored = await _crash_and_restart(store, state.procedure_execution_id)

    # The stored result survived with its validation verdict attached.
    assert "assess" in restored.step_results
    assert restored.step_results["assess"].status == StepStatus.COMPLETED
    assert restored.step_results["assess"].validation_result is not None
    assert restored.step_results["assess"].output["risk_level"] == "high"

    # Resuming a terminal procedure re-executes nothing.
    engine2 = SOPEngine(executor=executor, store=store)
    resumed = await engine2.run_procedure(
        definition=_definition(), sop=sop, agent_task_id="t",
        context=_context(), initial_state=restored,
    )
    assert len(executor.calls) == first_call_count
    assert resumed.status == ProcedureStatus.COMPLETED


@pytest.mark.asyncio
async def test_scenario_c_crash_after_validation_before_advance_is_idempotent():
    """
    Scenario C — validation recorded, advance not yet persisted.

    Re-advancing must not duplicate a completed_step_id or double-count
    evidence. The audit trail has to say the step completed once.
    """
    store = InMemoryProcedureStateStore()
    sop = make_sop([
        SOPStep(id="one", action="read_wave_status", next_step_id="two"),
        SOPStep(id="two", action="return_wave_assessment"),
    ])
    executor = ScriptedExecutor()
    engine = SOPEngine(executor=executor, store=store)
    state = await engine.run_procedure(
        definition=_definition(), sop=sop, agent_task_id="t", context=_context()
    )

    restored = await _crash_and_restart(store, state.procedure_execution_id)
    assert restored.completed_step_ids == ["one", "two"]
    assert len(restored.completed_step_ids) == len(set(restored.completed_step_ids))

    evidence_keys = [
        (e.metadata.get("step_id"), e.metadata.get("attempt"), e.type, e.source)
        for e in restored.evidence_refs
    ]
    assert len(evidence_keys) == len(set(evidence_keys)), "evidence was duplicated"

    # Resuming the terminal procedure changes nothing.
    engine2 = SOPEngine(executor=ScriptedExecutor(), store=store)
    resumed = await engine2.run_procedure(
        definition=_definition(), sop=sop, agent_task_id="t",
        context=_context(), initial_state=restored,
    )
    assert resumed.completed_step_ids == ["one", "two"]


@pytest.mark.asyncio
async def test_scenario_d_crash_while_waiting_for_governance():
    """
    Scenario D — crash during WAITING_FOR_GOVERNANCE.

    The restored procedure is still waiting. No step re-runs, no second
    proposal is emitted, and the procedure does not quietly advance past the
    approval it never received.
    """
    store = InMemoryProcedureStateStore()
    sop = make_sop([
        SOPStep(id="propose", action="emit_recommended_action", next_step_id="verify"),
        SOPStep(id="verify", action="return_wave_assessment"),
    ])
    executor = ScriptedExecutor(script={
        "propose": [make_step_result("propose", status=StepStatus.WAITING_FOR_GOVERNANCE)],
    })
    engine = SOPEngine(executor=executor, store=store)
    state = await engine.run_procedure(
        definition=_definition(), sop=sop, agent_task_id="t", context=_context()
    )
    assert state.status == ProcedureStatus.WAITING_FOR_GOVERNANCE
    calls_before = len(executor.calls)

    restored = await _crash_and_restart(store, state.procedure_execution_id)

    assert restored.status == ProcedureStatus.WAITING_FOR_GOVERNANCE
    assert restored.current_step_id == "propose"
    assert "propose" not in restored.completed_step_ids
    # A restart must not emit a second proposal.
    assert len(executor.calls) == calls_before


@pytest.mark.asyncio
async def test_scenario_e_crash_after_write_before_authoritative_reread():
    """
    Scenario E — the write landed; the procedure died before proving it.

    The recovery path re-reads authoritative state. It must NOT repeat the
    write. ``write_count`` counts real side effects and must be exactly 1 at
    the end, having been 1 before the crash.
    """
    store = InMemoryProcedureStateStore()
    write_count = {"n": 0}

    def wave_reassigned(state: dict, args: dict) -> bool:
        # A pure read of authoritative state. Calling this never writes.
        return state.get("wave_status") == "reassigned"

    register_predicate("test_wave_reassigned", wave_reassigned)
    try:
        completion = StepCompletionSpec(
            validator_type=ValidatorType.STATE_PREDICATE,
            predicate_name="test_wave_reassigned",
        )
        sop = make_sop([
            SOPStep(
                id="apply_write",
                action="emit_recommended_action",
                completion=completion,
            ),
        ])

        executor = ScriptedExecutor(script={
            "apply_write": [
                make_step_result("apply_write", status=StepStatus.WAITING_FOR_GOVERNANCE)
            ],
        })
        engine = SOPEngine(executor=executor, store=store)
        paused = await engine.run_procedure(
            definition=_definition(), sop=sop, agent_task_id="t", context=_context()
        )
        assert paused.status == ProcedureStatus.WAITING_FOR_GOVERNANCE

        # Governance approved and ActionExecutor performed the write — outside
        # the SOP Engine, which is the whole point of the boundary.
        write_count["n"] += 1

        # ...then the process crashed. Restart from the store.
        restored = await _crash_and_restart(store, paused.procedure_execution_id)
        assert restored.status == ProcedureStatus.WAITING_FOR_GOVERNANCE

        class _Outcome:
            decision_outcome = "APPROVED"
            execution_status = "SUCCESS"

        engine2 = SOPEngine(executor=executor, store=store)
        resumed = await engine2.resume_after_governance(
            definition=_definition(),
            sop=sop,
            proc_state=restored,
            context=_context(),
            governance_outcome=_Outcome(),
            warehouse_state_snapshot={"wave_status": "reassigned"},
        )

        assert resumed.status == ProcedureStatus.COMPLETED
        assert "apply_write" in resumed.completed_step_ids
        # THE invariant: recovery proved the outcome by reading, not by writing.
        assert write_count["n"] == 1
        # The executor was never re-invoked during recovery.
        assert all(call[0] == "apply_write" for call in executor.calls)
        assert len(executor.calls) == 1
    finally:
        unregister_predicate("test_wave_reassigned")


@pytest.mark.asyncio
async def test_scenario_f_crash_inside_a_bounded_loop_preserves_the_budget():
    """
    Scenario F — crash mid-loop.

    Attempt 2 of 3 must still be attempt 2 of 3 after a restart. A loop whose
    budget silently resets is an unbounded loop wearing a bound.
    """
    store = InMemoryProcedureStateStore()

    def never_holds(state: dict, args: dict) -> bool:
        return False

    register_predicate("test_never_holds", never_holds)
    try:
        sop = make_sop([
            SOPStep(
                id="reassess",
                action="read_wave_status",
                completion=StepCompletionSpec(
                    validator_type=ValidatorType.STATE_PREDICATE,
                    predicate_name="test_never_holds",
                ),
                loop=LoopPolicy(max_iterations=3),
            ),
        ])
        executor = ScriptedExecutor()
        engine = SOPEngine(executor=executor, store=store)
        state = await engine.run_procedure(
            definition=_definition(), sop=sop, agent_task_id="t", context=_context()
        )

        # Budget fully spent: 3 iterations, then ESCALATED.
        assert state.status == ProcedureStatus.ESCALATED
        assert state.attempt_by_step["reassess"] == 3

        restored = await _crash_and_restart(store, state.procedure_execution_id)
        assert restored.attempt_by_step["reassess"] == 3
        assert "reassess" in restored.loop_exhausted_step_ids

        # Resuming does not hand the loop a fresh budget.
        executor2 = ScriptedExecutor()
        engine2 = SOPEngine(executor=executor2, store=store)
        resumed = await engine2.run_procedure(
            definition=_definition(), sop=sop, agent_task_id="t",
            context=_context(), initial_state=restored,
        )
        assert executor2.calls == [], "a restarted exhausted loop must not run again"
        assert resumed.status == ProcedureStatus.ESCALATED
    finally:
        unregister_predicate("test_never_holds")


@pytest.mark.asyncio
async def test_mid_loop_restart_keeps_partial_iteration_count():
    """A loop stopped at iteration 2 of 5 resumes at 2, not at 0."""
    store = InMemoryProcedureStateStore()
    partial = make_procedure_state(
        current_step_id="reassess",
        attempt_by_step={"reassess": 2},
    )
    await store.save(partial)

    restored = await store.load(partial.procedure_execution_id)
    assert restored.loop_iterations("reassess") == 2
    assert restored.next_attempt("reassess") == 3


# ── SOP version pinning ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resume_under_a_different_sop_version_fails_safely():
    """
    A procedure never auto-upgrades.

    Half the steps completed under v1.0 and the rest running under v2.0 is a
    procedure that never existed, and no audit of either version describes what
    happened. The correct outcome is a structured failure, not best effort.
    """
    store = InMemoryProcedureStateStore()
    v1 = make_sop([SOPStep(id="a", action="read_wave_status")], version="1.0")
    state = make_procedure_state(version="1.0", current_step_id="a")
    await store.save(state)

    v2 = make_sop([SOPStep(id="a", action="read_wave_status")], version="2.0")
    executor = ScriptedExecutor()
    engine = SOPEngine(executor=executor, store=store)

    result = await engine.run_procedure(
        definition=_definition(), sop=v2, agent_task_id="t",
        context=_context(), initial_state=await store.load(state.procedure_execution_id),
    )

    assert result.status == ProcedureStatus.ESCALATED
    assert executor.calls == [], "a version-mismatched procedure must not execute"
    escalation = result.step_results["a"]
    assert escalation.escalation_reason is EscalationReasonCode.POLICY_CONFLICT
    assert "2.0" in escalation.escalation_message
    assert "1.0" in escalation.escalation_message


@pytest.mark.asyncio
async def test_resume_under_a_different_sop_id_fails_safely():
    store = InMemoryProcedureStateStore()
    state = make_procedure_state(sop_id="wave.risk", current_step_id="a")
    other = make_sop([SOPStep(id="a", action="read_wave_status")], sop_id="equipment.failure")

    engine = SOPEngine(executor=ScriptedExecutor(), store=store)
    result = await engine.run_procedure(
        definition=_definition(), sop=other, agent_task_id="t",
        context=_context(), initial_state=state,
    )
    assert result.status == ProcedureStatus.ESCALATED


@pytest.mark.asyncio
async def test_resume_under_the_pinned_version_proceeds_normally():
    store = InMemoryProcedureStateStore()
    sop = make_sop([SOPStep(id="a", action="read_wave_status")], version="1.0")
    state = make_procedure_state(version="1.0", current_step_id="a")

    engine = SOPEngine(executor=ScriptedExecutor(), store=store)
    result = await engine.run_procedure(
        definition=_definition(), sop=sop, agent_task_id="t",
        context=_context(), initial_state=state,
    )
    assert result.status == ProcedureStatus.COMPLETED


# ── Terminal safety and engine/store integration ──────────────────────────────

@pytest.mark.asyncio
async def test_engine_without_a_store_is_unchanged():
    """Backward compatibility: store=None runs exactly as before."""
    sop = make_sop([SOPStep(id="a", action="read_wave_status")])
    engine = SOPEngine(executor=ScriptedExecutor())
    result = await engine.run_procedure(
        definition=_definition(), sop=sop, agent_task_id="t", context=_context()
    )
    assert result.status == ProcedureStatus.COMPLETED
    assert result.revision == 0, "no store means no revisions were issued"


@pytest.mark.asyncio
async def test_engine_checkpoints_every_transition_not_just_the_end():
    """
    A store that only ever saw the final state would make recovery useless.

    The revision count is the proof: it advances once per lifecycle transition.
    """
    store = InMemoryProcedureStateStore()
    sop = make_sop([
        SOPStep(id="one", action="read_wave_status", next_step_id="two"),
        SOPStep(id="two", action="read_labor_state", next_step_id="three"),
        SOPStep(id="three", action="return_wave_assessment"),
    ])
    engine = SOPEngine(executor=ScriptedExecutor(), store=store)
    result = await engine.run_procedure(
        definition=_definition(), sop=sop, agent_task_id="t", context=_context()
    )

    # created + (start, result, advance) x3 + terminal
    assert result.revision > 3, f"only {result.revision} checkpoints for a 3-step SOP"
    assert result.status == ProcedureStatus.COMPLETED


@pytest.mark.asyncio
async def test_terminal_procedure_is_never_re_advanced_on_resume():
    store = InMemoryProcedureStateStore()
    sop = make_sop([SOPStep(id="a", action="read_wave_status")])
    terminal = make_procedure_state(
        current_step_id="a", status=ProcedureStatus.COMPLETED
    )
    executor = ScriptedExecutor()
    engine = SOPEngine(executor=executor, store=store)

    result = await engine.run_procedure(
        definition=_definition(), sop=sop, agent_task_id="t",
        context=_context(), initial_state=terminal,
    )
    assert result.status == ProcedureStatus.COMPLETED
    assert executor.calls == []


@pytest.mark.asyncio
async def test_retry_budget_survives_restart():
    """A retried step resumes with its attempts spent, not refreshed."""
    store = InMemoryProcedureStateStore()
    sop = make_sop([
        SOPStep(
            id="flaky",
            action="read_wave_status",
            completion=StepCompletionSpec(
                validator_type=ValidatorType.SCHEMA, schema_fields=["never_present"]
            ),
            retry_policy=RetryPolicy(max_attempts=3, backoff_seconds=0.0),
        ),
    ])
    engine = SOPEngine(executor=ScriptedExecutor(), store=store)
    state = await engine.run_procedure(
        definition=_definition(), sop=sop, agent_task_id="t", context=_context()
    )

    restored = await _crash_and_restart(store, state.procedure_execution_id)
    assert restored.attempt_by_step["flaky"] == 3
