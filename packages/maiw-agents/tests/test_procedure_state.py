# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""ProcedureExecutionState identity, advancement and attempt tracking."""

from __future__ import annotations

import uuid

from maiw_agents.contracts.procedure_state import ProcedureExecutionState, ProcedureStatus
from maiw_agents.contracts.sop import SOPStep
from maiw_agents.sop_engine import SOPEngine

from conftest import ScriptedExecutor, make_procedure_state, make_sop


# ── Identity ──────────────────────────────────────────────────────────────────

def test_procedure_execution_id_is_a_uuid4():
    state = make_procedure_state()
    parsed = uuid.UUID(state.procedure_execution_id)
    assert parsed.version == 4


async def test_each_run_gets_a_distinct_procedure_execution_id(definition, context):
    sop = make_sop([SOPStep(id="a", action="no_op")])
    engine = SOPEngine(executor=ScriptedExecutor())

    first = await engine.run_procedure(
        definition=definition, sop=sop, agent_task_id="task-1", context=context
    )
    second = await engine.run_procedure(
        definition=definition, sop=sop, agent_task_id="task-1", context=context
    )

    assert first.procedure_execution_id != second.procedure_execution_id


async def test_ids_link_to_trace_and_agent_task(definition, context):
    sop = make_sop([SOPStep(id="a", action="no_op")], sop_id="ops.x", version="3.1")
    engine = SOPEngine(executor=ScriptedExecutor())

    state = await engine.run_procedure(
        definition=definition, sop=sop, agent_task_id="task-abc", context=context
    )

    assert state.agent_task_id == "task-abc"
    assert state.trace_id == context.trace_id
    assert state.sop_id == "ops.x"
    assert state.sop_version == "3.1"
    # The procedure id is its own identifier, not a reuse of any linked id.
    assert state.procedure_execution_id not in {
        state.agent_task_id, state.trace_id, state.sop_id
    }


def test_trace_id_falls_back_to_engine_trace_id(definition):
    from maiw_agents.contracts.runtime import AgentExecutionContext

    engine = SOPEngine(executor=ScriptedExecutor(), trace_id="engine-trace")
    ctx = AgentExecutionContext(warehouse_id="wh", trace_id="")
    sop = make_sop([SOPStep(id="a", action="no_op")])

    state = engine._init_state(sop, "task-1", ctx)
    assert state.trace_id == "engine-trace"


# ── Initial state ─────────────────────────────────────────────────────────────

def test_init_state_starts_running_with_no_current_step(definition, context):
    engine = SOPEngine(executor=ScriptedExecutor())
    sop = make_sop([SOPStep(id="a", action="no_op")])

    state = engine._init_state(sop, "task-1", context)

    assert state.status is ProcedureStatus.RUNNING
    assert state.current_step_id is None
    assert state.completed_step_ids == []
    assert state.attempt_by_step == {}
    assert state.step_results == {}
    assert state.evidence_refs == []
    assert state.branch_history == []


# ── Attempt tracking ──────────────────────────────────────────────────────────

def test_next_attempt_starts_at_one():
    state = make_procedure_state()
    assert state.next_attempt("s1") == 1


def test_next_attempt_increments_from_recorded_attempts():
    state = make_procedure_state(attempt_by_step={"s1": 2})
    assert state.next_attempt("s1") == 3
    assert state.next_attempt("other") == 1


# ── Advancement ───────────────────────────────────────────────────────────────

def test_advance_records_completion_and_branch_history(definition, context):
    engine = SOPEngine(executor=ScriptedExecutor())
    state = make_procedure_state(current_step_id="a")
    step = SOPStep(id="a", action="no_op", next_step_id="b")

    advanced = engine._advance(state, step)

    assert advanced.current_step_id == "b"
    assert advanced.completed_step_ids == ["a"]
    assert advanced.branch_history == ["a"]
    assert advanced.last_updated_at >= state.last_updated_at


def test_advance_with_no_next_step_terminates(definition, context):
    engine = SOPEngine(executor=ScriptedExecutor())
    state = make_procedure_state(current_step_id="a")
    step = SOPStep(id="a", action="no_op")

    advanced = engine._advance(state, step)
    assert advanced.current_step_id is None


def test_advance_does_not_mutate_the_original():
    engine = SOPEngine(executor=ScriptedExecutor())
    state = make_procedure_state(current_step_id="a")
    step = SOPStep(id="a", action="no_op", next_step_id="b")

    engine._advance(state, step)

    assert state.current_step_id == "a"
    assert state.completed_step_ids == []


# ── Status vocabulary ─────────────────────────────────────────────────────────

def test_procedure_status_values():
    assert {s.value for s in ProcedureStatus} == {
        "running", "waiting_for_governance", "completed", "escalated", "failed",
    }


def test_procedure_state_is_serialisable():
    """Procedure state must round-trip for future persistence and audit export."""
    state = make_procedure_state(current_step_id="a", completed_step_ids=["z"])
    dumped = state.model_dump(mode="json")
    restored = ProcedureExecutionState.model_validate(dumped)
    assert restored.procedure_execution_id == state.procedure_execution_id
    assert restored.completed_step_ids == ["z"]
