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
Phase 18E: Nano qualification methodology.

Defines:
  - NanoQualificationConfig  — run parameters (N, warmup, threshold)
  - QualificationSample      — one (case, model, rep) result with warm-up flag
  - QualificationRunResult   — per-case aggregate (accept rate, latency stats)
  - QualificationReport      — final qualification verdict

18E methodology invariants (spec §8–§13):
  - At least one warm-up call per model/deployment, EXCLUDED from latency stats.
  - N >= 5 measured repetitions per policy-eligible case where endpoint permits.
  - Sequential runs (§9): no concurrency.
  - Material latency advantage: >= 20% median improvement (§13).
  - Qualification threshold: all critical graders pass in >= 90% of runs (§12).
    For N=5 this requires 5/5 (100%) for strong conclusion.
  - Quality dominates latency (§13): faster but failing → does not qualify.
  - Alternating Nano/Super order to avoid warm-up bias (§8).
  - Fallback samples are flagged and excluded from qualification metrics.
  - No LLM-as-judge (§11).

This module is data models + helper functions only — no live inference.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

from .calibration import CRITICAL_GRADERS
from .graders import GraderResult

# ── Configuration ─────────────────────────────────────────────────────────────

MATERIAL_LATENCY_ADVANTAGE_THRESHOLD = 0.20  # 20% median improvement required (§13)
QUALIFICATION_ACCEPTANCE_RATE = 0.90         # 90% of N runs must pass all critical (§12)
DEFAULT_N_REPS = 5                           # measured repetitions per case (§8)
DEFAULT_WARMUP_REPS = 1                      # warm-up calls excluded from stats (§8)
DISPLAY_PREVIEW_CHARS = 300                  # max chars for display_preview (§4)


@dataclass
class NanoQualificationConfig:
    """
    Configuration for a Nano qualification run.

    Attributes:
        n_reps:             Number of measured repetitions per case.
        warmup_reps:        Warm-up calls excluded from latency/quality stats.
        material_threshold: Minimum fractional latency improvement for Nano to
                            count as materially faster than Super (§13).
        acceptance_rate:    Minimum fraction of measured runs where all critical
                            graders must pass for qualification (§12).
        alternating_order:  True = alternate Nano/Super per repetition to
                            mitigate warm-up bias (§8).
    """

    n_reps: int = DEFAULT_N_REPS
    warmup_reps: int = DEFAULT_WARMUP_REPS
    material_threshold: float = MATERIAL_LATENCY_ADVANTAGE_THRESHOLD
    acceptance_rate: float = QUALIFICATION_ACCEPTANCE_RATE
    alternating_order: bool = True


# ── Per-sample result ─────────────────────────────────────────────────────────


@dataclass
class QualificationSample:
    """
    One measured sample in a qualification run.

    Fields:
        case_id:            Evaluation case identifier.
        model_id:           Model that produced this sample.
        rep_index:          0-based repetition index (including warm-up).
        warmup:             True → excluded from latency and quality statistics.
        fallback_used:      True → excluded from qualification metrics.
        total_latency_ms:   End-to-end latency.
        grader_results:     Deterministic grader outputs.
        acceptable:         True when all applicable critical graders passed and
                            no error or fallback.
        error:              Error string if call failed; None on success.
        raw_response:       Full bounded model output (graders used this).
        display_preview:    Optional truncated preview (≤300 chars, display only).
        deployment:         Deployment identifier.
    """

    case_id: str
    model_id: str
    rep_index: int
    warmup: bool
    fallback_used: bool
    total_latency_ms: float
    grader_results: list[GraderResult] = field(default_factory=list)
    acceptable: bool = False
    error: str | None = None
    raw_response: str | None = None
    display_preview: str | None = None
    deployment: str = "nvidia_hosted"
    input_tokens: int | None = None
    output_tokens: int | None = None
    routing_latency_ms: float = 0.0
    inference_latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "model_id": self.model_id,
            "rep_index": self.rep_index,
            "warmup": self.warmup,
            "fallback_used": self.fallback_used,
            "total_latency_ms": self.total_latency_ms,
            "routing_latency_ms": self.routing_latency_ms,
            "inference_latency_ms": self.inference_latency_ms,
            "acceptable": self.acceptable,
            "error": self.error,
            # 18E §4: graders always used raw_response; preview is display-only.
            "raw_response": self.raw_response,
            "display_preview": self.display_preview,
            "deployment": self.deployment,
            "tokens": {
                "input": self.input_tokens,
                "output": self.output_tokens,
            },
            "graders": [
                {
                    "name": g.grader_name,
                    "passed": g.passed,
                    "score": g.score,
                    "reason": g.reason,
                }
                for g in self.grader_results
            ],
        }


# ── Per-case aggregate ────────────────────────────────────────────────────────


@dataclass
class QualificationRunResult:
    """
    Aggregate qualification result for one (case, model) pair.

    Computed from measured samples only (warm-up and fallback excluded).

    Fields:
        accept_count:       # measured runs where all critical graders passed.
        n_measured:         # measured runs (warm-up excluded).
        critical_fail_count: # measured runs where >= 1 critical grader failed.
        fallback_count:     # runs where fallback_used=True (excluded from metrics).
        warmup_count:       # warm-up runs excluded from stats.
        latency_median_ms:  Median total latency of measured runs.
        latency_p90_ms:     P90 total latency of measured runs.
        latency_min_ms:     Minimum measured latency.
        latency_max_ms:     Maximum measured latency.
        accept_rate:        accept_count / n_measured (0.0 if n_measured == 0).
        qualified:          True if accept_rate >= acceptance_rate and n_measured >= 1.
        grader_score_dist:  Per-grader pass rate across measured runs.
    """

    case_id: str
    model_id: str
    accept_count: int = 0
    n_measured: int = 0
    critical_fail_count: int = 0
    fallback_count: int = 0
    warmup_count: int = 0
    latency_median_ms: float = 0.0
    latency_p90_ms: float = 0.0
    latency_min_ms: float = 0.0
    latency_max_ms: float = 0.0
    accept_rate: float = 0.0
    qualified: bool = False
    grader_score_dist: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "model_id": self.model_id,
            "accept_count": self.accept_count,
            "n_measured": self.n_measured,
            "critical_fail_count": self.critical_fail_count,
            "fallback_count": self.fallback_count,
            "warmup_count": self.warmup_count,
            "latency": {
                "median_ms": self.latency_median_ms,
                "p90_ms": self.latency_p90_ms,
                "min_ms": self.latency_min_ms,
                "max_ms": self.latency_max_ms,
            },
            "accept_rate": self.accept_rate,
            "qualified": self.qualified,
            "grader_score_dist": self.grader_score_dist,
        }


# ── Qualification report ──────────────────────────────────────────────────────


@dataclass
class CaseComparisonRow:
    """One row in the Nano-vs-Super comparison table (spec §14)."""

    case_id: str
    policy_eligibility: str
    nano_accept: int | None       # None when Nano not available
    nano_n: int | None
    super_accept: int | None
    super_n: int | None
    nano_median_ms: float | None
    super_median_ms: float | None
    nano_critical_fails: int | None
    super_critical_fails: int | None
    classification: str  # NANO QUALIFIED | SUPER REQUIRED | NO MATERIAL DIFFERENCE | INCONCLUSIVE

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "policy_eligibility": self.policy_eligibility,
            "nano_accept": self.nano_accept,
            "nano_n": self.nano_n,
            "super_accept": self.super_accept,
            "super_n": self.super_n,
            "nano_median_ms": self.nano_median_ms,
            "super_median_ms": self.super_median_ms,
            "nano_critical_fails": self.nano_critical_fails,
            "super_critical_fails": self.super_critical_fails,
            "classification": self.classification,
        }


# ── Aggregation helpers ───────────────────────────────────────────────────────


def _critical_graders_all_passed(grader_results: list[GraderResult]) -> bool:
    """True when ALL applicable critical graders passed."""
    for g in grader_results:
        if g.grader_name in CRITICAL_GRADERS and not g.passed:
            return False
    return True


def compute_qualification_run(
    samples: list[QualificationSample],
    acceptance_rate: float = QUALIFICATION_ACCEPTANCE_RATE,
) -> QualificationRunResult:
    """
    Aggregate a list of QualificationSamples into a QualificationRunResult.

    Warm-up samples (warmup=True) and fallback samples (fallback_used=True)
    are excluded from latency and quality statistics.
    """
    if not samples:
        return QualificationRunResult(
            case_id="",
            model_id="",
        )

    case_id = samples[0].case_id
    model_id = samples[0].model_id

    warmup = [s for s in samples if s.warmup]
    fallbacks = [s for s in samples if not s.warmup and s.fallback_used]
    measured = [s for s in samples if not s.warmup and not s.fallback_used]

    accept = [s for s in measured if s.acceptable]
    critical_fails = [s for s in measured if not s.acceptable and not s.error]

    latencies = [s.total_latency_ms for s in measured]
    lat_median = statistics.median(latencies) if latencies else 0.0
    lat_p90 = (
        sorted(latencies)[int(len(latencies) * 0.9)] if len(latencies) >= 2 else (latencies[0] if latencies else 0.0)
    )
    lat_min = min(latencies) if latencies else 0.0
    lat_max = max(latencies) if latencies else 0.0

    n_measured = len(measured)
    accept_count = len(accept)
    rate = accept_count / n_measured if n_measured > 0 else 0.0
    qualified = rate >= acceptance_rate and n_measured > 0

    # Per-grader pass rate across measured runs.
    grader_names: set[str] = set()
    for s in measured:
        for g in s.grader_results:
            grader_names.add(g.grader_name)
    grader_score_dist: dict[str, float] = {}
    for gname in sorted(grader_names):
        passes = sum(
            1
            for s in measured
            for g in s.grader_results
            if g.grader_name == gname and g.passed
        )
        total_graded = sum(
            1 for s in measured for g in s.grader_results if g.grader_name == gname
        )
        grader_score_dist[gname] = passes / total_graded if total_graded > 0 else 0.0

    return QualificationRunResult(
        case_id=case_id,
        model_id=model_id,
        accept_count=accept_count,
        n_measured=n_measured,
        critical_fail_count=len(critical_fails),
        fallback_count=len(fallbacks),
        warmup_count=len(warmup),
        latency_median_ms=round(lat_median, 3),
        latency_p90_ms=round(lat_p90, 3),
        latency_min_ms=round(lat_min, 3),
        latency_max_ms=round(lat_max, 3),
        accept_rate=round(rate, 4),
        qualified=qualified,
        grader_score_dist={k: round(v, 4) for k, v in grader_score_dist.items()},
    )


def classify_case_comparison(
    nano_result: QualificationRunResult | None,
    super_result: QualificationRunResult | None,
    material_threshold: float = MATERIAL_LATENCY_ADVANTAGE_THRESHOLD,
) -> str:
    """
    Classify a Nano-vs-Super case comparison (spec §14).

    Returns one of:
        NANO QUALIFIED          — Nano passes all critical graders, material latency advantage
        SUPER REQUIRED          — Nano fails critical graders or unavailable
        NO MATERIAL DIFFERENCE  — both qualify but latency difference < threshold
        INCONCLUSIVE            — insufficient data
    """
    if nano_result is None or nano_result.n_measured == 0:
        return "INCONCLUSIVE"

    if super_result is None or super_result.n_measured == 0:
        return "INCONCLUSIVE"

    # Quality dominates — if Nano fails any critical grader, it does not qualify.
    if not nano_result.qualified:
        return "SUPER REQUIRED"

    if not super_result.qualified:
        # Super also failed — both inconclusive.
        return "INCONCLUSIVE"

    # Both qualify on quality — check latency advantage.
    if super_result.latency_median_ms <= 0:
        return "INCONCLUSIVE"

    improvement = (
        super_result.latency_median_ms - nano_result.latency_median_ms
    ) / super_result.latency_median_ms

    if improvement >= material_threshold:
        return "NANO QUALIFIED"

    return "NO MATERIAL DIFFERENCE"


def build_comparison_row(
    case_id: str,
    policy_eligibility: str,
    nano: QualificationRunResult | None,
    super_: QualificationRunResult | None,
    material_threshold: float = MATERIAL_LATENCY_ADVANTAGE_THRESHOLD,
) -> CaseComparisonRow:
    """Build a CaseComparisonRow for the spec §14 comparison table."""
    classification = classify_case_comparison(nano, super_, material_threshold)
    return CaseComparisonRow(
        case_id=case_id,
        policy_eligibility=policy_eligibility,
        nano_accept=nano.accept_count if nano else None,
        nano_n=nano.n_measured if nano else None,
        super_accept=super_.accept_count if super_ else None,
        super_n=super_.n_measured if super_ else None,
        nano_median_ms=nano.latency_median_ms if nano else None,
        super_median_ms=super_.latency_median_ms if super_ else None,
        nano_critical_fails=nano.critical_fail_count if nano else None,
        super_critical_fails=super_.critical_fail_count if super_ else None,
        classification=classification,
    )
