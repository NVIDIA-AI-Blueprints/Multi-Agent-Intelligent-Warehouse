# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW SOP Engine V2 — the runtime seam.

``SOPStepExecutor`` sits *beneath* the existing ``AgentRuntime`` Protocol and
splits a previously monolithic responsibility in two:

    SOP Engine   decides WHICH step runs, WHETHER it is complete, WHEN to
                 retry, and WHEN to escalate.
    Executor     decides HOW one named step is fulfilled by one runtime.

That split is what makes runtimes replaceable. Any future runtime (NemoClaw,
Codex, another agentic framework) that implements ``execute_step()`` inherits
correct completion, retry, escalation and evidence semantics for free — it
does not get to reimplement, reinterpret, or skip them.

An executor returns a *claim* about the step (a ``StepResult``). It never
decides the next step, and its own ``status`` field is advisory: the SOP
Engine overwrites it with the validator's verdict.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..contracts.agent import AgentDefinition
from ..contracts.procedure_state import ProcedureExecutionState
from ..contracts.runtime import AgentExecutionContext
from ..contracts.sop import SOPStep
from ..contracts.step_result import StepResult


@runtime_checkable
class SOPStepExecutor(Protocol):
    """
    Runtime-neutral per-step execution protocol.

    Implementations must not:
        - advance the procedure or choose the next step
        - call ActionExecutor, DecisionEngine, or any WRITE capability
        - treat their own ``StepResult.status`` as authoritative completion
    """

    async def execute_step(
        self,
        *,
        definition: AgentDefinition,
        step: SOPStep,
        procedure_state: ProcedureExecutionState,
        context: AgentExecutionContext,
        attempt: int,
    ) -> StepResult:
        ...


__all__ = ["SOPStepExecutor"]
