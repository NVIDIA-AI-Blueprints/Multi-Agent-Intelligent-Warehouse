# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""maiw-execution — shared execution boundary: BaseActionExecutor, typed errors, domain executors."""

from .base import (
    ActionConflict,
    ActionDecisionMismatch,
    ActionExecutionError,
    ActionExecutionResult,
    ActionExecutor,
    ActionExpired,
    ActionNotApproved,
    ActionUnsupported,
    BaseActionExecutor,
    NoOpActionExecutor,
)
from .equipment import EquipmentActionExecutor
from .labor import LaborActionExecutor
from .outcome import AmbiguousWriteError, ExecutionOutcome
from .reconciliation import (
    ExecutionIntent,
    ReconciliationOutcome,
    ReconciliationRecord,
    ReconciliationService,
    ReconciliationStrategy,
)
from .registry import ExecutionRecord, ExecutionRegistry
from .wave import WaveActionExecutor

__all__ = [
    # Errors (guard violations — still raise)
    "ActionNotApproved",
    "ActionDecisionMismatch",
    "ActionUnsupported",
    "ActionExpired",
    "ActionConflict",
    "ActionExecutionError",
    # Ambiguous write signal
    "AmbiguousWriteError",
    # Canonical outcome
    "ExecutionOutcome",
    # Idempotency registry
    "ExecutionRecord",
    "ExecutionRegistry",
    # Result & protocol
    "ActionExecutionResult",
    "ActionExecutor",
    # Executors
    "NoOpActionExecutor",
    "BaseActionExecutor",
    "EquipmentActionExecutor",
    "LaborActionExecutor",
    "WaveActionExecutor",
    # Reconciliation (Batch 3)
    "ExecutionIntent",
    "ReconciliationOutcome",
    "ReconciliationRecord",
    "ReconciliationService",
    "ReconciliationStrategy",
]
