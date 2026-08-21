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
from .wave import WaveActionExecutor

__all__ = [
    # Errors
    "ActionNotApproved",
    "ActionDecisionMismatch",
    "ActionUnsupported",
    "ActionExpired",
    "ActionConflict",
    "ActionExecutionError",
    # Result & protocol
    "ActionExecutionResult",
    "ActionExecutor",
    # Executors
    "NoOpActionExecutor",
    "BaseActionExecutor",
    "EquipmentActionExecutor",
    "LaborActionExecutor",
    "WaveActionExecutor",
]
