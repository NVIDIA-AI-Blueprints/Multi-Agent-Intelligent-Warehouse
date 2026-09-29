# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Cross-runtime equivalence (Design Section 45).

The point of the SOPStepExecutor seam is that procedure semantics stop being a
property of the runtime. The same SOP, run through two different executors,
must produce the same step traversal, the same validator decisions, and the
same authority boundary — differing only in how each step was fulfilled.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from maiw_agents.contracts.procedure_state import ProcedureStatus
from maiw_agents.contracts.sop import SOPStep
from maiw_agents.contracts.sop_v2 import StepCompletionSpec, ValidatorType
from maiw_agents.contracts.step_result import EvidenceRef, StepResult, StepStatus
from maiw_agents.sop_engine import SOPEngine, SOPStepExecutor

from conftest import make_sop


def _procedure():
    """One procedure exercising schema completion, a skip condition and a chain."""
    return make_sop([
        SOPStep(
            id="establish_state", action="gather_operational_context", next_step_id="diagnose",
            completion=StepCompletionSpec(
                validator_type=ValidatorType.SCHEMA,
                schema_fields=["wave_id", "at_risk_count"],
            ),
        ),
        SOPStep(
            id="diagnose", action="determine_primary_constraint", next_step_id="recommend",
            completion=StepCompletionSpec(
                validator_type=ValidatorType.SCHEMA, schema_fields=["primary_constraint"]
            ),
        ),
        SOPStep(id="recommend", action="select_recommendation"),
    ])


_FIXTURE_OUTPUT = {
    "wave_id": "wave-17",
    "at_risk_count": 3,
    "primary_constraint": "labor",
}


class _DeterministicStepExecutor:
    """Mimics the deterministic runtime: results arrive via bounded context."""

    RUNTIME_NAME = "deterministic"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def execute_step(self, *, definition, step, procedure_state, context, attempt):
        self.calls.append(step.id)
        output = {}
        if step.completion and step.completion.schema_fields:
            for field in step.completion.schema_fields:
                if field in _FIXTURE_OUTPUT:
                    output[field] = _FIXTURE_OUTPUT[field]
        return StepResult(
            step_id=step.id, status=StepStatus.COMPLETED, output=output,
            runtime=self.RUNTIME_NAME, attempt=attempt,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            evidence=[EvidenceRef(
                type="step_execution", source=self.RUNTIME_NAME,
                timestamp=datetime.now(timezone.utc), summary=f"ran {step.id}",
            )],
        )


class _DeepAgentsStepExecutorMock:
    """Mimics the Deep Agents runtime: a model returns a structured claim."""

    RUNTIME_NAME = "deep_agents"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def execute_step(self, *, definition, step, procedure_state, context, attempt):
        self.calls.append(step.id)
        # The "model" returns the same facts, wrapped as its own claim.
        output = {}
        if step.completion and step.completion.schema_fields:
            for field in step.completion.schema_fields:
                if field in _FIXTURE_OUTPUT:
                    output[field] = _FIXTURE_OUTPUT[field]
        return StepResult(
            step_id=step.id, status=StepStatus.COMPLETED, output=output,
            runtime=self.RUNTIME_NAME, attempt=attempt,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            evidence=[EvidenceRef(
                type="model_response", source=self.RUNTIME_NAME,
                timestamp=datetime.now(timezone.utc),
                summary=f"model response for step {step.id!r}",
                metadata={"model_claimed_status": "completed"},
            )],
        )


@pytest.fixture
def both_runs(definition, context):
    async def _run(executor):
        engine = SOPEngine(executor=executor)
        return await engine.run_procedure(
            definition=definition, sop=_procedure(),
            agent_task_id="task-equivalence", context=context,
        )

    return _run


# ── Equivalence ───────────────────────────────────────────────────────────────

async def test_both_executors_satisfy_the_protocol():
    assert isinstance(_DeterministicStepExecutor(), SOPStepExecutor)
    assert isinstance(_DeepAgentsStepExecutorMock(), SOPStepExecutor)


async def test_same_steps_completed(both_runs):
    det = _DeterministicStepExecutor()
    deep = _DeepAgentsStepExecutorMock()

    det_state = await both_runs(det)
    deep_state = await both_runs(deep)

    assert det_state.status is deep_state.status is ProcedureStatus.COMPLETED
    assert det_state.completed_step_ids == deep_state.completed_step_ids
    assert det_state.completed_step_ids == ["establish_state", "diagnose", "recommend"]


async def test_same_traversal_order(both_runs):
    det = _DeterministicStepExecutor()
    deep = _DeepAgentsStepExecutorMock()

    await both_runs(det)
    await both_runs(deep)

    assert det.calls == deep.calls


async def test_same_validator_types_applied(both_runs):
    det_state = await both_runs(_DeterministicStepExecutor())
    deep_state = await both_runs(_DeepAgentsStepExecutorMock())

    def validators(state):
        return {
            step_id: result.validation_result.validator_type
            for step_id, result in state.step_results.items()
        }

    assert validators(det_state) == validators(deep_state)
    assert validators(det_state) == {
        "establish_state": ValidatorType.SCHEMA,
        "diagnose": ValidatorType.SCHEMA,
        "recommend": ValidatorType.LEGACY_SUCCESS,
    }


async def test_same_attempt_counts(both_runs):
    det_state = await both_runs(_DeterministicStepExecutor())
    deep_state = await both_runs(_DeepAgentsStepExecutorMock())

    assert det_state.attempt_by_step == deep_state.attempt_by_step


async def test_runtime_is_the_only_difference_in_results(both_runs):
    det_state = await both_runs(_DeterministicStepExecutor())
    deep_state = await both_runs(_DeepAgentsStepExecutorMock())

    for step_id in det_state.step_results:
        det_result = det_state.step_results[step_id]
        deep_result = deep_state.step_results[step_id]

        assert det_result.status is deep_result.status
        assert det_result.output == deep_result.output
        assert det_result.validation_result.valid == deep_result.validation_result.valid
        assert det_result.runtime != deep_result.runtime


# ── The boundary holds for both ───────────────────────────────────────────────

async def test_both_runtimes_fail_the_same_unsatisfiable_step(definition, context):
    sop = make_sop([
        SOPStep(
            id="impossible", action="no_op",
            completion=StepCompletionSpec(
                validator_type=ValidatorType.SCHEMA, schema_fields=["never_produced"]
            ),
        )
    ])

    statuses = []
    for executor in (_DeterministicStepExecutor(), _DeepAgentsStepExecutorMock()):
        engine = SOPEngine(executor=executor)
        state = await engine.run_procedure(
            definition=definition, sop=sop, agent_task_id="t", context=context
        )
        statuses.append(state.status)

    assert statuses == [ProcedureStatus.FAILED, ProcedureStatus.FAILED]


async def test_neither_executor_can_advance_itself(both_runs):
    """
    Neither executor sets current_step_id or completed_step_ids — progression is
    written only by the engine.
    """
    for executor_cls in (_DeterministicStepExecutor, _DeepAgentsStepExecutorMock):
        import inspect

        source = inspect.getsource(executor_cls.execute_step)
        assert "current_step_id" not in source
        assert "next_step_id" not in source


async def test_both_produce_evidence_for_every_completed_step(both_runs):
    for executor in (_DeterministicStepExecutor(), _DeepAgentsStepExecutorMock()):
        state = await both_runs(executor)
        for step_id in state.completed_step_ids:
            assert state.step_results[step_id].evidence, (
                f"{step_id} completed with no evidence under {executor.RUNTIME_NAME}"
            )
