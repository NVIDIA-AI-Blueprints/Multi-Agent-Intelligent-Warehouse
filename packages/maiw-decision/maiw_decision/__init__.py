# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
maiw-decision — deterministic rule-based evaluation of ActionProposals.

Public surface
--------------
    ActionProposal          Typed warehouse write proposal (moved from maiw-mcp)
    RiskLevel               Risk classification enum (moved from maiw-mcp)
    DecisionEngine          Pure in-memory rule evaluator
    DecisionRequest         Input: ActionProposal + WarehouseStateSnapshot
    DecisionResult          Output: outcome + violations
    DecisionOutcome         Enum: APPROVED | REJECTED | REQUIRES_HUMAN_APPROVAL | REQUIRES_FRESH_STATE
    ConstraintViolation     Single violated rule
    DecisionAuditRecord     Structured log entry per evaluation
    ApprovalRecord          Approval evidence model (Phase 10E Batch 2)
    ApprovalState           Enum: PENDING | APPROVED | REJECTED | EXPIRED | CONSUMED
    AuthorityType           Enum: HUMAN | POLICY | SYSTEM
    ApprovalStore           Protocol for approval persistence
    InMemoryApprovalStore   Single-process in-memory implementation
"""

from .approval import ApprovalStore, InMemoryApprovalStore
from .audit import DecisionAuditRecord
from .engine import DecisionEngine
from .models import (
    ApprovalRecord,
    ApprovalState,
    AuthorityType,
    ConstraintViolation,
    DecisionOutcome,
    DecisionRequest,
    DecisionResult,
)
from .proposal import ActionProposal, RiskLevel

__all__ = [
    "ActionProposal",
    "ApprovalRecord",
    "ApprovalState",
    "ApprovalStore",
    "AuthorityType",
    "ConstraintViolation",
    "DecisionAuditRecord",
    "DecisionEngine",
    "DecisionOutcome",
    "DecisionRequest",
    "DecisionResult",
    "InMemoryApprovalStore",
    "RiskLevel",
]
