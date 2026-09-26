# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""maiw-agents — production reasoning agents for MAIW (no src.* dependencies).

Public SOP Engine V2 surface is re-exported here. Note that ``StepResult`` and
``StepStatus`` at this level are the **V2** models from
``maiw_agents.contracts.step_result``; the Phase 18H models of the same name
remain available as ``maiw_agents.contracts.StepResult`` / ``StepStatus``.

Only lightweight contract modules are imported eagerly — nothing here pulls in
a runtime, a model provider, or an execution package.
"""

from .contracts.procedure_state import ProcedureExecutionState, ProcedureStatus
from .contracts.sop_v2 import (
    EscalationReasonCode,
    RetryPolicy,
    StepCompletionSpec,
    ValidatorType,
)
from .contracts.step_result import (
    EvidenceRef,
    StepResult,
    StepStatus,
    ValidationResult,
)
from .sop_engine import SOPEngine, SOPStepExecutor

__all__ = [
    # Step result contract (V2)
    "StepResult",
    "StepStatus",
    "EvidenceRef",
    "ValidationResult",
    # Procedure lifecycle
    "ProcedureExecutionState",
    "ProcedureStatus",
    # Step semantics
    "ValidatorType",
    "EscalationReasonCode",
    "StepCompletionSpec",
    "RetryPolicy",
    # Engine
    "SOPEngine",
    "SOPStepExecutor",
]
