# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 10E Batch 6 — Fault injection test framework.

Architecture rule: all fault injection lives in this test infrastructure.
Production code (Agent, ModelGateway, DecisionEngine, ActionExecutor) must never
contain if-fault_id checks.
"""

from .models import (
    FaultProfile,
    FaultTrigger,
    FaultType,
    GoldenInvariantViolation,
    ReliabilityResult,
    check_golden_invariants,
)
from .fakes import (
    FakeClock,
    MinimalTestExecutor,
    StubNIMProvider,
    make_approved_decision,
    make_test_proposal,
    make_test_snapshot,
)

__all__ = [
    "FaultProfile",
    "FaultTrigger",
    "FaultType",
    "GoldenInvariantViolation",
    "ReliabilityResult",
    "check_golden_invariants",
    "FakeClock",
    "MinimalTestExecutor",
    "StubNIMProvider",
    "make_approved_decision",
    "make_test_proposal",
    "make_test_snapshot",
]
