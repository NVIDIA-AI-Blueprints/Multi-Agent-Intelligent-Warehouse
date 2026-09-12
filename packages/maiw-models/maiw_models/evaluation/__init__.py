# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
maiw_models.evaluation — Phase 18B evaluation foundation.

Typed infrastructure for offline multi-model benchmarking (18C+).

Architecture invariants:
  - Evaluation must NOT invoke DecisionEngine, ApprovalStore, ActionExecutor,
    or MCP write capabilities.
  - Evaluation calls go through ModelGateway only.
  - Evaluation results must not contaminate Copilot conversation state.
"""

from __future__ import annotations

from .fixtures import (
    ALL_FIXTURE_CASES,
    ALL_FIXTURE_INPUTS,
    equipment_failure,
    equipment_failure_input,
    get_fixture_case,
    get_fixture_input,
    healthy_baseline,
    healthy_baseline_input,
    wave17_labor_risk,
    wave17_labor_risk_input,
)
from .graders import (
    CapabilityMatchGrader,
    EvaluationGrader,
    ForbiddenClaimsGrader,
    HallucinationGrader,
    RequiredEvidenceGrader,
    SchemaValidityGrader,
    TargetMatchGrader,
    default_graders,
    run_graders,
)
from .models import (
    EvaluationCallResult,
    EvaluationCase,
    GraderResult,
    ModelEvaluationInput,
    ModelEvaluationResult,
    TaskFamily,
    make_evaluation_run_key,
)
from .replay import (
    MockOperationalContextSnapshot,
    MockSnapshotEdge,
    MockSnapshotNode,
    ReplayContext,
    replay_context_from_snapshot,
)

__all__ = [
    # Data models (18B)
    "ModelEvaluationInput",
    "ModelEvaluationResult",
    "EvaluationCase",
    "GraderResult",
    "TaskFamily",
    "make_evaluation_run_key",
    # Phase 18C: forced-model evaluation result
    "EvaluationCallResult",
    # Replay
    "ReplayContext",
    "replay_context_from_snapshot",
    "MockOperationalContextSnapshot",
    "MockSnapshotNode",
    "MockSnapshotEdge",
    # Graders
    "EvaluationGrader",
    "SchemaValidityGrader",
    "HallucinationGrader",
    "CapabilityMatchGrader",
    "TargetMatchGrader",
    "RequiredEvidenceGrader",
    "ForbiddenClaimsGrader",
    "default_graders",
    "run_graders",
    # Fixtures
    "ALL_FIXTURE_CASES",
    "ALL_FIXTURE_INPUTS",
    "wave17_labor_risk",
    "wave17_labor_risk_input",
    "equipment_failure",
    "equipment_failure_input",
    "healthy_baseline",
    "healthy_baseline_input",
    "get_fixture_case",
    "get_fixture_input",
]
