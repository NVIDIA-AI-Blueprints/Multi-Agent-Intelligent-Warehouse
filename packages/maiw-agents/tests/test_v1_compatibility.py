# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Every existing v1 SOP must load and run through the V2 SOP Engine with no YAML
modification, and traverse exactly the steps it traversed before.

This is the backward-compatibility gate from ADR constraint 5.
"""

from __future__ import annotations

import pytest

from maiw_agents.contracts.procedure_state import ProcedureStatus
from maiw_agents.contracts.sop import load_sop
from maiw_agents.contracts.sop_v2 import ValidatorType
from maiw_agents.sop_engine import SOPEngine

from conftest import ScriptedExecutor

V1_SOPS = [
    ("operations_coordination/wave_risk_resolution.v1.yaml",
     "operations_coordination.wave_risk_resolution"),
    ("labor/labor_constraint_assessment.v1.yaml",
     "labor.labor_constraint_assessment"),
    ("wave/wave_risk_assessment.v1.yaml",
     "wave.wave_risk_assessment"),
]


@pytest.fixture(params=V1_SOPS, ids=[s[1] for s in V1_SOPS])
def v1_sop(request, sop_dir):
    rel, expected_id = request.param
    path = sop_dir / rel
    if not path.exists():
        pytest.skip(f"SOP not found: {path}")
    sop = load_sop(path)
    assert sop.id == expected_id
    return sop


# ── Loading ───────────────────────────────────────────────────────────────────

def test_v1_sop_loads_unmodified(v1_sop):
    assert v1_sop.steps, "v1 SOP must still parse into steps"


def test_v1_steps_declare_no_v2_fields(v1_sop):
    """V1 YAML sets none of the v2 fields — they must all default to None."""
    for step in v1_sop.steps:
        assert step.completion is None
        assert step.retry_policy is None
        assert step.timeout_seconds is None
        assert step.required_inputs is None
        assert step.evidence_requirements is None
        assert step.objective is None
        assert step.expected_output is None


# ── Running through the V2 engine ─────────────────────────────────────────────

async def test_v1_sop_runs_through_engine(v1_sop, definition, context):
    engine = SOPEngine(executor=ScriptedExecutor())

    state = await engine.run_procedure(
        definition=definition,
        sop=v1_sop,
        agent_task_id="task-v1-compat",
        context=context,
    )

    assert state.status is ProcedureStatus.COMPLETED
    assert state.completed_step_ids, "at least one step must complete"


async def test_v1_steps_complete_via_legacy_success(v1_sop, definition, context):
    engine = SOPEngine(executor=ScriptedExecutor())

    state = await engine.run_procedure(
        definition=definition,
        sop=v1_sop,
        agent_task_id="task-v1-compat",
        context=context,
    )

    for step_id in state.completed_step_ids:
        result = state.step_results.get(step_id)
        if result is None:
            continue  # condition-skipped step
        assert result.validation_result is not None
        assert result.validation_result.validator_type is ValidatorType.LEGACY_SUCCESS
        assert result.validation_result.valid is True


async def test_v1_traversal_matches_pre_v2_next_step_semantics(v1_sop, definition, context):
    """
    Pre-V2, MAIWDeterministicRuntime advanced via `current_step_id = step.next_step_id`
    and terminated on None. The engine must reproduce that traversal exactly — the
    expected chain is derived from the SOP itself, so this holds both before and
    after the V1 procedure migration made the next_step_id chains explicit.
    """
    expected: list[str] = []
    by_id = {s.id: s for s in v1_sop.steps}
    current = v1_sop.steps[0].id
    while current is not None:
        step = by_id[current]
        expected.append(step.id)
        current = step.next_step_id

    engine = SOPEngine(executor=ScriptedExecutor())
    state = await engine.run_procedure(
        definition=definition,
        sop=v1_sop,
        agent_task_id="task-v1-compat",
        context=context,
    )

    assert state.branch_history == expected


async def test_v1_run_produces_no_escalation(v1_sop, definition, context):
    engine = SOPEngine(executor=ScriptedExecutor())

    state = await engine.run_procedure(
        definition=definition,
        sop=v1_sop,
        agent_task_id="task-v1-compat",
        context=context,
    )

    for result in state.step_results.values():
        assert result.escalation_reason is None
        assert result.error is None


# ── V2 proof SOP coexists with v1 ─────────────────────────────────────────────

def test_v2_proof_sop_loads(sop_dir):
    path = sop_dir / "operations_coordination" / "wave_risk_resolution.v2.yaml"
    if not path.exists():
        pytest.skip(f"V2 proof SOP not found: {path}")

    sop = load_sop(path)
    assert sop.id == "operations_coordination.wave_risk_resolution_v2"
    assert sop.version == "2.0"


def test_v1_and_v2_are_distinct_artifacts(sop_dir):
    """
    The v1 file remains a separate, pure-V1 artifact alongside the v2 re-authoring.

    v1 is on the 1.x line and declares none of the V2 step fields; v2 is 2.0 and
    does. The V1 procedure migration moved v1 from 1.0 to 1.1 (explicit
    next_step_id chain, a V1 navigation field) — that does not make it a V2 SOP.
    """
    v1 = load_sop(sop_dir / "operations_coordination" / "wave_risk_resolution.v1.yaml")
    v2_path = sop_dir / "operations_coordination" / "wave_risk_resolution.v2.yaml"
    if not v2_path.exists():
        pytest.skip("V2 proof SOP not found")
    v2 = load_sop(v2_path)

    assert v1.id != v2.id
    assert v1.version.startswith("1.")
    assert v2.version.startswith("2.")
    assert all(s.completion is None for s in v1.steps)
    assert any(s.completion is not None for s in v2.steps)
