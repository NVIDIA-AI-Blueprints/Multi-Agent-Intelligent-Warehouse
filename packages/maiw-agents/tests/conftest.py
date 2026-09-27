# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Shared fixtures for the SOP Engine V2 test suite.

These tests exercise maiw-agents in isolation: no database, no network, no
model provider, no execution package.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

# Ensure THIS package copy is imported, not a sibling editable install.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))

REPO_ROOT = _PACKAGE_ROOT.parent.parent
SOP_DIR = REPO_ROOT / "agents" / "sops"

from maiw_agents.contracts.agent import AgentDefinition  # noqa: E402
from maiw_agents.contracts.procedure_state import (  # noqa: E402
    ProcedureExecutionState,
    ProcedureStatus,
)
from maiw_agents.contracts.runtime import AgentExecutionContext  # noqa: E402
from maiw_agents.contracts.sop import SOPDefinition, SOPStep  # noqa: E402
from maiw_agents.contracts.step_result import StepResult, StepStatus  # noqa: E402


def now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def sop_dir() -> Path:
    return SOP_DIR


@pytest.fixture
def definition() -> AgentDefinition:
    return AgentDefinition(
        agent_id="operations_coordination",
        version="1.0",
        objective="Resolve wave risk before carrier cutoff",
        domain="operations",
        allowed_capabilities=[],
        allowed_subagents=[],
        output_contract="RecommendedAction",
    )


@pytest.fixture
def context() -> AgentExecutionContext:
    return AgentExecutionContext(
        warehouse_id="wh-test",
        trace_id="trace-sop-engine-v2",
        bounded_context={
            "wave_id": "wave-17",
            "at_risk_count": 3,
            "carrier_cutoff_minutes": 47,
            "primary_constraint": "labor",
            "domains_affected": "labor",
        },
    )


def make_sop(steps: list[SOPStep], *, sop_id: str = "test.sop", version: str = "1.0") -> SOPDefinition:
    """Build a minimal valid SOPDefinition around the given steps."""
    return SOPDefinition(
        id=sop_id,
        version=version,
        agent="operations_coordination",
        objective="test procedure",
        steps=steps,
        stop_conditions=["objective_met"],
    )


def make_procedure_state(
    *,
    sop_id: str = "test.sop",
    version: str = "1.0",
    current_step_id: str | None = None,
    status: ProcedureStatus = ProcedureStatus.RUNNING,
    **overrides: Any,
) -> ProcedureExecutionState:
    base = dict(
        procedure_execution_id=str(uuid.uuid4()),
        sop_id=sop_id,
        sop_version=version,
        agent_task_id="task-test",
        trace_id="trace-sop-engine-v2",
        current_step_id=current_step_id,
        status=status,
        started_at=now(),
        last_updated_at=now(),
    )
    base.update(overrides)
    return ProcedureExecutionState(**base)


def make_step_result(
    step_id: str,
    *,
    status: StepStatus = StepStatus.COMPLETED,
    output: dict[str, Any] | None = None,
    runtime: str = "test",
    attempt: int = 1,
) -> StepResult:
    return StepResult(
        step_id=step_id,
        status=status,
        output=output or {},
        runtime=runtime,
        attempt=attempt,
        started_at=now(),
        completed_at=now(),
    )


class ScriptedExecutor:
    """
    A SOPStepExecutor test double.

    ``script`` maps step_id → a list of StepResults (or callables) to return on
    successive attempts. Records every call so tests can assert exactly which
    steps ran, in what order, and how many times.
    """

    RUNTIME_NAME = "scripted"

    def __init__(
        self,
        script: dict[str, list[Any]] | None = None,
        *,
        default_status: StepStatus = StepStatus.COMPLETED,
        default_output: dict[str, Any] | None = None,
    ) -> None:
        self.script = script or {}
        self.default_status = default_status
        self.default_output = default_output or {}
        self.calls: list[tuple[str, int]] = []

    async def execute_step(
        self,
        *,
        definition: AgentDefinition,
        step: SOPStep,
        procedure_state: ProcedureExecutionState,
        context: AgentExecutionContext,
        attempt: int,
    ) -> StepResult:
        self.calls.append((step.id, attempt))

        scripted = self.script.get(step.id)
        if scripted:
            index = min(attempt - 1, len(scripted) - 1)
            entry = scripted[index]
            if callable(entry):
                entry = entry(step, attempt)
            return entry.model_copy(update={"attempt": attempt})

        return make_step_result(
            step.id,
            status=self.default_status,
            output=dict(self.default_output),
            runtime=self.RUNTIME_NAME,
            attempt=attempt,
        )

    @property
    def step_ids(self) -> list[str]:
        return [step_id for step_id, _ in self.calls]
