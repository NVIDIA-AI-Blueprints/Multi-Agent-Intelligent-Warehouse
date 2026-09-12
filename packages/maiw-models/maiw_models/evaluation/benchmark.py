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
Phase 18C: BenchmarkRun result schema, quality scoring, oracle, and router regret.

Result hierarchy:
    BenchmarkRun
        metadata: BenchmarkMetadata
        cases[]:
            BenchmarkCaseResult
                model_results[]: BenchmarkModelResult
                router_selection: RouterSelectionRecord
                oracle: OracleResult
                regret: RouterRegret
    decision_gate: "CURRENT ROUTER SUFFICIENT" | "CURRENT ROUTER HAS MEASURABLE GAPS"

Invariants:
    - cost is always reported as "unavailable" (no pricing metadata in repo/config)
    - quality_score = passed_graders / applicable_graders (graders that did work)
    - oracle is computed from benchmark results only — NOT from production logic
    - router regret is split by dimension (quality / latency); never collapsed
    - policy_compliant=False + quality pass → report as OFFLINE QUALITY PASS /
      NOT PRODUCTION ELIGIBLE UNDER CURRENT POLICY
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .graders import GraderResult

# ── Quality scoring ───────────────────────────────────────────────────────────

# Graders that unconditionally pass when their case field is absent are
# "not applicable" for that run.  We identify them by their skip reason.
_SKIP_REASONS_NOT_APPLICABLE = {
    "No expected_schema defined — schema check skipped.",
    "No context_entities defined — hallucination check skipped.",
    "No expected_capability defined — capability check skipped.",
    "No expected_target defined — target check skipped.",
    "No required_facts defined — evidence check skipped.",
    "No forbidden_claims defined — forbidden claim check skipped.",
}


def compute_quality_score(grader_results: list[GraderResult]) -> tuple[float, int, int]:
    """
    Compute composite quality score from grader results.

    Returns:
        (score, applicable_count, passed_count)
        score = passed / applicable.  1.0 when no applicable graders ran.

    Applicable graders are those that actually checked something (i.e. the
    corresponding EvaluationCase field was set).  Skipped graders are excluded
    from the denominator to avoid penalising cases with minimal expectations.
    """
    applicable = [
        r for r in grader_results if r.reason not in _SKIP_REASONS_NOT_APPLICABLE
    ]
    if not applicable:
        return 1.0, 0, 0
    passed = sum(1 for r in applicable if r.passed)
    score = passed / len(applicable)
    return round(score, 4), len(applicable), passed


# ── Per-model benchmark result ────────────────────────────────────────────────


@dataclass
class BenchmarkModelResult:
    """
    Complete result for one (case, model) evaluation run.

    Includes full reproducibility identity, quality scores, system metrics,
    and per-grader results (never hidden behind the composite score alone).

    Spec §13 reproducibility fields:
        evaluation_run_key, case_id, dataset_id, semantic_checksum,
        scenario_id, context_snapshot_id, warehouse_state_snapshot_id,
        prompt_hash, model_id, deployment
    """

    # ── Reproducibility identity ──────────────────────────────────────────────
    evaluation_run_key: str
    case_id: str
    dataset_id: str
    semantic_checksum: str
    scenario_id: str
    context_snapshot_id: str | None
    warehouse_state_snapshot_id: str | None
    prompt_hash: str
    model_id: str
    deployment: str  # e.g. "nvidia_hosted"

    # ── Quality ───────────────────────────────────────────────────────────────
    grader_results: list[GraderResult] = field(default_factory=list)
    quality_score: float = 0.0  # passed_graders / applicable_graders
    quality_pass: bool = False  # True when quality_score == 1.0 and error is None
    applicable_graders: int = 0
    passed_graders: int = 0

    # ── System metrics ────────────────────────────────────────────────────────
    routing_latency_ms: float = 0.0  # policy check time
    inference_latency_ms: float = 0.0  # provider call time
    total_latency_ms: float = 0.0  # routing + inference
    routing_strategy: str = "forced_evaluation"
    provider: str = "nvidia-nim"
    candidate_models: list[str] = field(default_factory=list)

    # ── Token usage ───────────────────────────────────────────────────────────
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost: str = "unavailable"  # no pricing metadata in repo/config

    # ── Outcome ───────────────────────────────────────────────────────────────
    timeout: bool = False
    error: str | None = None
    fallback_used: bool = False  # always False for forced evaluation
    policy_compliant: bool = True

    # ── Interpretation ───────────────────────────────────────────────────────
    interpretation: str = ""
    # "OFFLINE QUALITY PASS / NOT PRODUCTION ELIGIBLE UNDER CURRENT POLICY"
    # when policy_compliant=False and quality_pass=True

    # ── Raw response (bounded) ────────────────────────────────────────────────
    response_snippet: str | None = None  # first 300 chars only

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluation_run_key": self.evaluation_run_key,
            "case_id": self.case_id,
            "dataset_id": self.dataset_id,
            "semantic_checksum": self.semantic_checksum,
            "scenario_id": self.scenario_id,
            "context_snapshot_id": self.context_snapshot_id,
            "warehouse_state_snapshot_id": self.warehouse_state_snapshot_id,
            "prompt_hash": self.prompt_hash,
            "model_id": self.model_id,
            "deployment": self.deployment,
            "quality": {
                "score": self.quality_score,
                "pass": self.quality_pass,
                "applicable_graders": self.applicable_graders,
                "passed_graders": self.passed_graders,
                "graders": [
                    {
                        "name": g.grader_name,
                        "passed": g.passed,
                        "score": g.score,
                        "reason": g.reason,
                        "evidence": g.evidence,
                    }
                    for g in self.grader_results
                ],
            },
            "latency": {
                "routing_ms": self.routing_latency_ms,
                "inference_ms": self.inference_latency_ms,
                "total_ms": self.total_latency_ms,
            },
            "provider": self.provider,
            "routing_strategy": self.routing_strategy,
            "candidate_models": self.candidate_models,
            "tokens": {
                "input": self.input_tokens,
                "output": self.output_tokens,
                "cost": self.cost,
            },
            "outcome": {
                "timeout": self.timeout,
                "error": self.error,
                "fallback_used": self.fallback_used,
                "policy_compliant": self.policy_compliant,
            },
            "interpretation": self.interpretation,
            "response_snippet": self.response_snippet,
        }


# ── Oracle ────────────────────────────────────────────────────────────────────


@dataclass
class OracleResult:
    """
    Offline oracle selection for one benchmark case.

    Three oracle dimensions (§17):
        BEST QUALITY         — highest quality_score among all results
        FASTEST PASSING      — minimum total_latency_ms among quality_pass=True results
        LOWEST COST PASSING  — always "unavailable" (no pricing metadata)

    Oracle is computed from benchmark results only — NOT production routing logic.
    """

    best_quality_model: str | None = None  # model_id with highest quality_score
    best_quality_score: float = 0.0
    fastest_passing_model: str | None = None  # min latency among passing models
    fastest_passing_latency_ms: float = 0.0
    lowest_cost_passing_model: str = "unavailable"  # always — no pricing metadata
    passing_models: list[str] = field(
        default_factory=list
    )  # all models with quality_pass=True

    def to_dict(self) -> dict[str, Any]:
        return {
            "best_quality": {
                "model_id": self.best_quality_model,
                "quality_score": self.best_quality_score,
            },
            "fastest_passing": {
                "model_id": self.fastest_passing_model,
                "total_latency_ms": self.fastest_passing_latency_ms,
            },
            "lowest_cost_passing": {
                "model_id": self.lowest_cost_passing_model,
                "note": "Cost metadata unavailable in current repo/config.",
            },
            "passing_models": self.passing_models,
        }


def compute_oracle(model_results: list[BenchmarkModelResult]) -> OracleResult:
    """
    Compute the offline oracle from benchmark results for one case.

    Best quality: highest quality_score (ties broken by lower total_latency_ms).
    Fastest passing: minimum total_latency_ms among quality_pass=True results.
    Cost: always unavailable.
    """
    if not model_results:
        return OracleResult()

    # Best quality — highest score, break ties by latency.
    sorted_by_quality = sorted(
        model_results,
        key=lambda r: (-r.quality_score, r.total_latency_ms),
    )
    best = sorted_by_quality[0]
    best_quality_model = best.model_id if best.quality_score > 0 else None

    # Fastest passing.
    passing = [r for r in model_results if r.quality_pass and r.error is None]
    passing_models = [r.model_id for r in passing]
    if passing:
        fastest = min(passing, key=lambda r: r.total_latency_ms)
        fastest_passing_model = fastest.model_id
        fastest_passing_latency_ms = fastest.total_latency_ms
    else:
        fastest_passing_model = None
        fastest_passing_latency_ms = 0.0

    return OracleResult(
        best_quality_model=best_quality_model,
        best_quality_score=best.quality_score if best_quality_model else 0.0,
        fastest_passing_model=fastest_passing_model,
        fastest_passing_latency_ms=fastest_passing_latency_ms,
        lowest_cost_passing_model="unavailable",
        passing_models=passing_models,
    )


# ── Router regret ─────────────────────────────────────────────────────────────


@dataclass
class RouterRegret:
    """
    Router regret for one case — split by dimension (never collapsed).

    quality_regret: router chose a model that missed graders the oracle passed.
    latency_regret: router chose a slower model when a faster model also passed.

    policy interpretation (§19): if quality_regret is True but the better model
    is not policy-compliant, this is NOT a router bug — it is an offline
    observation only.  See quality_regret_policy_note.
    """

    router_model: str
    quality_regret: bool = False
    latency_regret: bool = False
    quality_regret_detail: str = ""
    latency_regret_detail: str = ""
    quality_regret_policy_note: str = ""  # set when better model is out-of-policy

    def to_dict(self) -> dict[str, Any]:
        return {
            "router_model": self.router_model,
            "quality_regret": self.quality_regret,
            "latency_regret": self.latency_regret,
            "quality_regret_detail": self.quality_regret_detail,
            "latency_regret_detail": self.latency_regret_detail,
            "quality_regret_policy_note": self.quality_regret_policy_note,
        }


def compute_router_regret(
    router_model: str,
    oracle: OracleResult,
    model_results: list[BenchmarkModelResult],
) -> RouterRegret:
    """
    Compute quality and latency regret for the router's selection.

    quality_regret: oracle.best_quality_model != router_model AND
                    oracle's best quality_score > router's quality_score.

    latency_regret: oracle.fastest_passing_model is not None AND
                    oracle.fastest_passing_model != router_model AND
                    router is slower (or didn't pass).
    """
    router_result = next((r for r in model_results if r.model_id == router_model), None)

    # ── Quality regret ────────────────────────────────────────────────────────
    quality_regret = False
    quality_regret_detail = ""
    quality_regret_policy_note = ""

    if (
        oracle.best_quality_model is not None
        and oracle.best_quality_model != router_model
        and oracle.best_quality_score
        > (router_result.quality_score if router_result else 0.0)
    ):
        quality_regret = True
        router_score = router_result.quality_score if router_result else 0.0
        quality_regret_detail = (
            f"Router chose {router_model} (quality={router_score:.2f}) but "
            f"{oracle.best_quality_model} achieved quality={oracle.best_quality_score:.2f}."
        )
        # Check if the better model is policy-compliant.
        better_result = next(
            (r for r in model_results if r.model_id == oracle.best_quality_model), None
        )
        if better_result and not better_result.policy_compliant:
            quality_regret_policy_note = (
                f"OFFLINE QUALITY PASS / NOT PRODUCTION ELIGIBLE UNDER CURRENT POLICY: "
                f"{oracle.best_quality_model} passed offline but is not eligible under "
                f"current deployment policy. This is not a router bug."
            )

    # ── Latency regret ────────────────────────────────────────────────────────
    latency_regret = False
    latency_regret_detail = ""

    if (
        oracle.fastest_passing_model is not None
        and oracle.fastest_passing_model != router_model
    ):
        router_passed = router_result is not None and router_result.quality_pass
        router_latency = (
            router_result.total_latency_ms if router_result else float("inf")
        )

        if router_passed and router_latency > oracle.fastest_passing_latency_ms:
            latency_regret = True
            latency_regret_detail = (
                f"Router chose {router_model} ({router_latency:.0f}ms) but "
                f"{oracle.fastest_passing_model} also passed and was faster "
                f"({oracle.fastest_passing_latency_ms:.0f}ms)."
            )
        elif not router_passed and oracle.fastest_passing_model is not None:
            latency_regret = True
            latency_regret_detail = (
                f"Router chose {router_model} which did not pass quality check. "
                f"{oracle.fastest_passing_model} passed at "
                f"{oracle.fastest_passing_latency_ms:.0f}ms."
            )

    return RouterRegret(
        router_model=router_model,
        quality_regret=quality_regret,
        latency_regret=latency_regret,
        quality_regret_detail=quality_regret_detail,
        latency_regret_detail=latency_regret_detail,
        quality_regret_policy_note=quality_regret_policy_note,
    )


# ── Router selection record ───────────────────────────────────────────────────


@dataclass
class RouterSelectionRecord:
    """
    Records what the current rule-based router selected for a case.

    Populated by running ModelRouter.route() with the same request as the
    benchmark — independently of the forced-model evaluation calls.
    """

    case_id: str
    selected_model_id: str
    selected_role: str
    routing_rule: str
    routing_reason: str
    routing_strategy: str
    routing_latency_ms: float
    candidate_models: list[str]
    policy_compliant: bool = True  # router always selects from policy-compliant set

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "selected_model_id": self.selected_model_id,
            "selected_role": self.selected_role,
            "routing_rule": self.routing_rule,
            "routing_reason": self.routing_reason,
            "routing_strategy": self.routing_strategy,
            "routing_latency_ms": self.routing_latency_ms,
            "candidate_models": self.candidate_models,
            "policy_compliant": self.policy_compliant,
        }


# ── Case result ───────────────────────────────────────────────────────────────


@dataclass
class BenchmarkCaseResult:
    """
    All model results for one EvaluationCase plus oracle and regret analysis.
    """

    case_id: str
    case_prompt: str
    task_family: str
    model_results: list[BenchmarkModelResult] = field(default_factory=list)
    router_selection: RouterSelectionRecord | None = None
    oracle: OracleResult = field(default_factory=OracleResult)
    regret: RouterRegret | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "case_prompt": self.case_prompt,
            "task_family": self.task_family,
            "model_results": [r.to_dict() for r in self.model_results],
            "router_selection": (
                self.router_selection.to_dict() if self.router_selection else None
            ),
            "oracle": self.oracle.to_dict(),
            "regret": self.regret.to_dict() if self.regret else None,
        }


# ── Benchmark metadata ────────────────────────────────────────────────────────


@dataclass
class BenchmarkMetadata:
    """
    Metadata for a complete benchmark run.
    """

    dataset_id: str
    semantic_checksum: str
    run_timestamp: str
    cases_count: int
    models_evaluated: list[str]
    deployment_mode: str
    phase: str = "18C"
    endpoint_status: str = "NOT RUN — ENDPOINT UNAVAILABLE"
    # Set to actual endpoint URL when live benchmark completes.

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "dataset_id": self.dataset_id,
            "semantic_checksum": self.semantic_checksum,
            "run_timestamp": self.run_timestamp,
            "cases_count": self.cases_count,
            "models_evaluated": self.models_evaluated,
            "deployment_mode": self.deployment_mode,
            "endpoint_status": self.endpoint_status,
        }


# ── Benchmark run ─────────────────────────────────────────────────────────────


@dataclass
class BenchmarkRun:
    """
    Complete benchmark run result.

    decision_gate is set after analysis:
        "CURRENT ROUTER SUFFICIENT"
        "CURRENT ROUTER HAS MEASURABLE GAPS"

    Serialisation target: artifacts/phase18/baseline.json
    """

    metadata: BenchmarkMetadata
    cases: list[BenchmarkCaseResult] = field(default_factory=list)
    decision_gate: str = ""  # set by compute_decision_gate()

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "cases": [c.to_dict() for c in self.cases],
            "decision_gate": self.decision_gate,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


# ── Decision gate ─────────────────────────────────────────────────────────────


def compute_decision_gate(cases: list[BenchmarkCaseResult]) -> str:
    """
    Determine whether the current router has measurable gaps.

    CURRENT ROUTER HAS MEASURABLE GAPS when:
        - Any case shows quality_regret=True (router missed graders oracle passed)
          AND the better model was policy_compliant.
        - Any case shows latency_regret=True (router chose slower model when
          faster model also passed).

    Policy interpretation: quality_regret where better model is out-of-policy
    does NOT count as a gap (see RouterRegret.quality_regret_policy_note).

    Returns one of:
        "CURRENT ROUTER SUFFICIENT"
        "CURRENT ROUTER HAS MEASURABLE GAPS"
    """
    for case in cases:
        if case.regret is None:
            continue
        regret = case.regret

        # Quality regret counts only when the better model is policy-compliant.
        if regret.quality_regret and not regret.quality_regret_policy_note:
            return "CURRENT ROUTER HAS MEASURABLE GAPS"

        # Latency regret always counts.
        if regret.latency_regret:
            return "CURRENT ROUTER HAS MEASURABLE GAPS"

    return "CURRENT ROUTER SUFFICIENT"
