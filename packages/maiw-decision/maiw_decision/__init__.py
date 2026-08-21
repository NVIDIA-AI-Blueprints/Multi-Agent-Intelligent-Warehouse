# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
maiw-decision — deterministic rule-based evaluation of ActionProposals.

Public surface
--------------
    DecisionEngine          Pure in-memory rule evaluator
    DecisionRequest         Input: ActionProposal + WarehouseStateSnapshot
    DecisionResult          Output: outcome + violations
    DecisionOutcome         Enum: APPROVED | REJECTED | REQUIRES_HUMAN_APPROVAL | REQUIRES_FRESH_STATE
    ConstraintViolation     Single violated rule
    DecisionAuditRecord     Structured log entry per evaluation
"""

from .audit import DecisionAuditRecord
from .engine import DecisionEngine
from .models import (
    ConstraintViolation,
    DecisionOutcome,
    DecisionRequest,
    DecisionResult,
)

__all__ = [
    "ConstraintViolation",
    "DecisionAuditRecord",
    "DecisionEngine",
    "DecisionOutcome",
    "DecisionRequest",
    "DecisionResult",
]
