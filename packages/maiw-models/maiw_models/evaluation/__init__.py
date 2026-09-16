# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
maiw_models.evaluation — Phase 18B/18D/18E evaluation foundation.

Typed infrastructure for offline multi-model benchmarking (18C+).

Architecture invariants:
  - Evaluation must NOT invoke DecisionEngine, ApprovalStore, ActionExecutor,
    or MCP write capabilities.
  - Evaluation calls go through ModelGateway only.
  - Evaluation results must not contaminate Copilot conversation state.
"""

from __future__ import annotations

from .calibration import (
    CRITICAL_GRADERS,
    NON_CRITICAL_GRADERS,
    CalibratedCaseResult,
    LatencySample,
    RegradeRecord,
    compute_latency_stats,
    is_critical,
    policy_label,
    regrade_result,
)
from .fixtures import (
    ALL_18D_FIXTURE_CASES,
    ALL_18D_FIXTURE_INPUTS,
    ALL_18E_FIXTURE_CASES,
    ALL_18E_FIXTURE_INPUTS,
    ALL_FIXTURE_CASES,
    ALL_FIXTURE_INPUTS,
    ALL_KNOWN_CASES,
    ALL_KNOWN_INPUTS,
    NANO_QUALIFICATION_CORPUS,
    POLICY_ELIGIBILITY,
    analyze_action,
    analyze_action_input,
    comparative_reasoning,
    comparative_reasoning_input,
    equipment_ask_low,
    equipment_ask_low_input,
    equipment_failure,
    equipment_failure_input,
    evidence_ask_labor,
    evidence_ask_labor_input,
    get_fixture_case,
    get_fixture_input,
    get_policy_eligibility,
    healthy_baseline,
    healthy_baseline_ask,
    healthy_baseline_ask_input,
    healthy_baseline_input,
    wave17_labor_risk,
    wave17_labor_risk_input,
    wave17_risk_low,
    wave17_risk_low_input,
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
from .qualification import (
    CaseComparisonRow,
    MATERIAL_LATENCY_ADVANTAGE_THRESHOLD,
    NanoQualificationConfig,
    QualificationRunResult,
    QualificationSample,
    build_comparison_row,
    classify_case_comparison,
    compute_qualification_run,
)
from .resolver import (
    ContextEntity,
    EntityResolver,
    ResolvedEntity,
    build_allowed_surface_forms,
    resolve_entity_reference,
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
    # 18B Fixtures
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
    # 18D Fixtures
    "ALL_18D_FIXTURE_CASES",
    "ALL_18D_FIXTURE_INPUTS",
    "ALL_KNOWN_CASES",
    "ALL_KNOWN_INPUTS",
    "evidence_ask_labor",
    "evidence_ask_labor_input",
    "analyze_action",
    "analyze_action_input",
    "comparative_reasoning",
    "comparative_reasoning_input",
    # 18E Fixtures
    "ALL_18E_FIXTURE_CASES",
    "ALL_18E_FIXTURE_INPUTS",
    "NANO_QUALIFICATION_CORPUS",
    "POLICY_ELIGIBILITY",
    "wave17_risk_low",
    "wave17_risk_low_input",
    "equipment_ask_low",
    "equipment_ask_low_input",
    "healthy_baseline_ask",
    "healthy_baseline_ask_input",
    "get_policy_eligibility",
    # 18E Qualification
    "NanoQualificationConfig",
    "QualificationSample",
    "QualificationRunResult",
    "CaseComparisonRow",
    "MATERIAL_LATENCY_ADVANTAGE_THRESHOLD",
    "compute_qualification_run",
    "classify_case_comparison",
    "build_comparison_row",
    # 18D Resolver
    "ContextEntity",
    "EntityResolver",
    "ResolvedEntity",
    "build_allowed_surface_forms",
    "resolve_entity_reference",
    # 18D Calibration
    "CRITICAL_GRADERS",
    "NON_CRITICAL_GRADERS",
    "CalibratedCaseResult",
    "LatencySample",
    "RegradeRecord",
    "compute_latency_stats",
    "is_critical",
    "policy_label",
    "regrade_result",
]
