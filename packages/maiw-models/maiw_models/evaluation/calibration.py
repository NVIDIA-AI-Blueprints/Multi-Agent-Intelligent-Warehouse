# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Phase 18D: Grader calibration — re-grade saved 18C results.

This module re-grades saved ModelEvaluationResult records from 18C baseline.json
through the calibrated 18D graders WITHOUT re-calling models.

Outputs:
  - Per-result: ORIGINAL SCORE | CALIBRATED SCORE | DELTA | REASON
  - Grader-level classification: TRUE MODEL ERROR | FALSE GRADER FAILURE | AMBIGUOUS
  - Structured grader_diagnostics.json artifact

Architecture invariants:
  - NEVER calls any model or provider.
  - NEVER modifies baseline.json or BASELINE_ROUTER_REPORT.md.
  - Input: saved response strings from baseline.json.
  - Output: calibrated GraderResult lists + comparison records.

Grader criticality classification (§26):
  CRITICAL (blocking):
    - hallucination        — unsupported warehouse fact asserted
    - capability_match     — wrong capability recommended
    - target_match         — wrong target entity
    - schema_validity      — invalid required schema
  NON-CRITICAL (informational):
    - required_evidence    — evidence completeness (partial pass possible)
    - forbidden_claims     — strict claim guard

A model is ACCEPTABLE for evaluation if ALL critical graders pass (§27).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .graders import GraderResult, default_graders, run_graders
from .models import EvaluationCase, ModelEvaluationResult

# ── Grader criticality ────────────────────────────────────────────────────────


CRITICAL_GRADERS: frozenset[str] = frozenset(
    {
        "hallucination",
        "capability_match",
        "target_match",
        "schema_validity",
    }
)

NON_CRITICAL_GRADERS: frozenset[str] = frozenset(
    {
        "required_evidence",
        "forbidden_claims",
    }
)


def is_critical(grader_name: str) -> bool:
    """Return True if this grader is in the CRITICAL (blocking) set."""
    return grader_name in CRITICAL_GRADERS


# ── Grader failure classification ────────────────────────────────────────────


FAILURE_CLASS_TRUE_MODEL_ERROR = "TRUE MODEL ERROR"
FAILURE_CLASS_FALSE_GRADER_FAILURE = "FALSE GRADER FAILURE"
FAILURE_CLASS_AMBIGUOUS = "AMBIGUOUS"


# ── Re-grading record ─────────────────────────────────────────────────────────


@dataclass
class RegradeRecord:
    """
    Comparison of original 18C grader result vs calibrated 18D grader result.

    Per §16: ORIGINAL SCORE | CALIBRATED SCORE | DELTA | REASON
    """

    case_id: str
    model_id: str
    grader_name: str
    original_passed: bool
    calibrated_passed: bool
    delta: int  # calibrated - original: +1 = fixed false failure, -1 = newly failing, 0 = same
    original_reason: str
    calibrated_reason: str
    failure_class: str  # TRUE MODEL ERROR | FALSE GRADER FAILURE | AMBIGUOUS | N/A

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "model_id": self.model_id,
            "grader_name": self.grader_name,
            "original_passed": self.original_passed,
            "calibrated_passed": self.calibrated_passed,
            "delta": self.delta,
            "original_reason": self.original_reason,
            "calibrated_reason": self.calibrated_reason,
            "failure_class": self.failure_class,
            "critical": is_critical(self.grader_name),
        }


@dataclass
class CalibratedCaseResult:
    """
    Calibration result for one (case, model) pair.

    Includes original scores, calibrated scores, and per-grader delta records.
    """

    case_id: str
    model_id: str
    original_score: float
    calibrated_score: float
    score_delta: float
    original_pass: bool
    calibrated_pass: bool
    regrade_records: list[RegradeRecord] = field(default_factory=list)
    # "ACCEPTABLE" when all critical graders pass after calibration
    evaluation_verdict: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "model_id": self.model_id,
            "original_score": round(self.original_score, 4),
            "calibrated_score": round(self.calibrated_score, 4),
            "score_delta": round(self.score_delta, 4),
            "original_pass": self.original_pass,
            "calibrated_pass": self.calibrated_pass,
            "evaluation_verdict": self.evaluation_verdict,
            "regrade_records": [r.to_dict() for r in self.regrade_records],
        }


# ── Re-grader ─────────────────────────────────────────────────────────────────


def regrade_result(
    case: EvaluationCase,
    result: ModelEvaluationResult,
    original_grader_results: list[dict[str, Any]],
) -> CalibratedCaseResult:
    """
    Re-grade a saved 18C result through calibrated 18D graders.

    Does NOT call any model or provider.  Uses stored response text only.

    Args:
        case:                   The EvaluationCase for this result.
        result:                 Reconstructed ModelEvaluationResult from saved data.
        original_grader_results: Raw grader result dicts from baseline.json.

    Returns:
        CalibratedCaseResult with per-grader delta records.
    """
    # Run calibrated graders on the SAME response text (no model re-call).
    calibrated_results = run_graders(case, result)

    # Build lookup for originals by grader name.
    original_by_name: dict[str, dict[str, Any]] = {
        g["name"]: g for g in original_grader_results
    }

    # Compute calibrated score.
    _SKIP_REASONS = {
        "No expected_schema defined — schema check skipped.",
        "No context_entities defined — hallucination check skipped.",
        "No expected_capability defined — capability check skipped.",
        "No expected_target defined — target check skipped.",
        "No required_facts defined — evidence check skipped.",
        "No forbidden_claims defined — forbidden claim check skipped.",
    }

    applicable_calibrated = [
        r for r in calibrated_results if r.reason not in _SKIP_REASONS
    ]
    cal_passed = sum(1 for r in applicable_calibrated if r.passed)
    cal_score = (
        cal_passed / len(applicable_calibrated) if applicable_calibrated else 1.0
    )

    orig_score = sum(
        1
        for g in original_grader_results
        if g.get("passed", False) and g.get("reason", "") not in _SKIP_REASONS
    )
    orig_applicable = sum(
        1 for g in original_grader_results if g.get("reason", "") not in _SKIP_REASONS
    )
    orig_score_frac = orig_score / orig_applicable if orig_applicable > 0 else 1.0

    regrade_records: list[RegradeRecord] = []
    for cal in calibrated_results:
        orig = original_by_name.get(cal.grader_name)
        if orig is None:
            # New grader added in 18D — no original to compare.
            continue

        orig_passed = orig.get("passed", False)
        cal_passed_bool = cal.passed
        delta = (1 if cal_passed_bool else 0) - (1 if orig_passed else 0)

        # Classify the failure.
        if orig_passed and cal_passed_bool:
            failure_class = "N/A"  # consistent pass
        elif not orig_passed and not cal_passed_bool:
            # Both fail — likely TRUE MODEL ERROR.
            failure_class = FAILURE_CLASS_TRUE_MODEL_ERROR
        elif not orig_passed and cal_passed_bool:
            # Original failed, calibrated passes — was FALSE GRADER FAILURE.
            failure_class = FAILURE_CLASS_FALSE_GRADER_FAILURE
        else:
            # Original passed, calibrated fails — should not happen with 18D
            # changes (we only relax, not tighten); if it does, flag AMBIGUOUS.
            failure_class = FAILURE_CLASS_AMBIGUOUS

        regrade_records.append(
            RegradeRecord(
                case_id=case.case_id,
                model_id=result.model_id if hasattr(result, "model_id") else "unknown",
                grader_name=cal.grader_name,
                original_passed=orig_passed,
                calibrated_passed=cal_passed_bool,
                delta=delta,
                original_reason=orig.get("reason", ""),
                calibrated_reason=cal.reason,
                failure_class=failure_class,
            )
        )

    # Verdict: ACCEPTABLE if all critical graders pass after calibration.
    critical_results = {
        r.grader_name: r.passed
        for r in calibrated_results
        if r.grader_name in CRITICAL_GRADERS and r.reason not in _SKIP_REASONS
    }
    all_critical_pass = all(critical_results.values()) if critical_results else True
    verdict = "ACCEPTABLE" if all_critical_pass else "NOT ACCEPTABLE"

    model_id = result.model_id if hasattr(result, "model_id") else "unknown"

    return CalibratedCaseResult(
        case_id=case.case_id,
        model_id=model_id,
        original_score=orig_score_frac,
        calibrated_score=cal_score,
        score_delta=cal_score - orig_score_frac,
        original_pass=(orig_score_frac == 1.0),
        calibrated_pass=(cal_score == 1.0),
        regrade_records=regrade_records,
        evaluation_verdict=verdict,
    )


# ── Latency sample classification ────────────────────────────────────────────


@dataclass
class LatencySample:
    """
    One latency observation for a (model, deployment, case) tuple.

    Captures all fields needed to classify and compare samples per §22–§24.
    """

    sample_id: str
    case_id: str
    model_id: str
    requested_model: str
    actual_model: str
    deployment: str
    provider: str
    routing_ms: float
    inference_ms: float
    total_ms: float
    input_tokens: int | None
    output_tokens: int | None
    fallback_used: bool
    retry_count: int
    error: str | None
    warmup: bool  # True = warm-up call, excluded from timing summary
    run_index: int  # 1-based; warm-up is 0

    @property
    def tokens_per_sec(self) -> float | None:
        """Tokens/sec for output tokens if available."""
        if self.output_tokens and self.inference_ms > 0:
            return round(self.output_tokens / (self.inference_ms / 1000), 2)
        return None

    def clean(self) -> bool:
        """True if this sample is uncontaminated (no fallback, no error)."""
        return not self.fallback_used and self.error is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "case_id": self.case_id,
            "model_id": self.model_id,
            "requested_model": self.requested_model,
            "actual_model": self.actual_model,
            "deployment": self.deployment,
            "provider": self.provider,
            "routing_ms": self.routing_ms,
            "inference_ms": self.inference_ms,
            "total_ms": self.total_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "tokens_per_sec": self.tokens_per_sec,
            "fallback_used": self.fallback_used,
            "retry_count": self.retry_count,
            "error": self.error,
            "warmup": self.warmup,
            "run_index": self.run_index,
            "clean": self.clean(),
        }


def compute_latency_stats(samples: list[LatencySample]) -> dict[str, Any]:
    """
    Compute latency statistics for a list of clean (non-warmup, non-fallback) samples.

    Per §24: N, median, p95 (where N sufficient), min, max, error count, fallback count.
    """
    clean_samples = [s for s in samples if not s.warmup and s.clean()]
    all_non_warmup = [s for s in samples if not s.warmup]

    total_ms_values = sorted(s.total_ms for s in clean_samples)
    error_count = sum(1 for s in all_non_warmup if s.error is not None)
    fallback_count = sum(1 for s in all_non_warmup if s.fallback_used)

    if not total_ms_values:
        return {
            "n": 0,
            "median_ms": None,
            "p95_ms": None,
            "min_ms": None,
            "max_ms": None,
            "error_count": error_count,
            "fallback_count": fallback_count,
            "note": "No clean samples available.",
        }

    n = len(total_ms_values)
    median_ms = total_ms_values[n // 2]
    p95_ms = total_ms_values[int(n * 0.95)] if n >= 20 else None

    return {
        "n": n,
        "median_ms": round(median_ms, 1),
        "p95_ms": round(p95_ms, 1) if p95_ms is not None else None,
        "min_ms": round(total_ms_values[0], 1),
        "max_ms": round(total_ms_values[-1], 1),
        "error_count": error_count,
        "fallback_count": fallback_count,
        "note": "p95 unavailable (N < 20)" if p95_ms is None else None,
    }


# ── Nano policy eligibility labeling ─────────────────────────────────────────


def policy_label(risk_level: str, reasoning_level: str) -> str:
    """
    Return the policy eligibility label for Nano given risk + reasoning.

    Nano is POLICY ELIGIBLE only for low/medium risk AND low/medium reasoning.
    HIGH reasoning or CRITICAL risk → RESEARCH ONLY per PolicyFilter rules.

    Per §4: do NOT alter production eligibility to obtain data.
    """
    high_reasoning = reasoning_level.lower() == "high"
    critical_risk = risk_level.lower() == "critical"
    high_risk = risk_level.lower() == "high"

    if high_reasoning or critical_risk or high_risk:
        return "RESEARCH ONLY — NOT PRODUCTION ELIGIBLE"
    return "POLICY ELIGIBLE"
