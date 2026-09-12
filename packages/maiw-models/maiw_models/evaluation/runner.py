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
Phase 18C: Benchmark runner.

Orchestrates multi-model evaluation for the fixed-context benchmark corpus:

    EvaluationCase
        ↓
    OperationalContextSnapshot replay (same context for all models)
        ↓
    for each candidate model (sequential — default for latency fairness):
        ModelGateway.evaluate_with_model()
        ↓
        BenchmarkModelResult (with grader scores)
        ↓
    Oracle computation
        ↓
    Router regret analysis
        ↓
    BenchmarkCaseResult

Architecture invariants (§24):
    - NEVER modifies Copilot conversation
    - NEVER creates ActionProposal, approval, or MCP write
    - NEVER calls governance or DecisionEngine
    - NEVER mutates LIVE scenario state
    - Always calls through ModelGateway (never direct NIMClient)
    - Sequential by default for latency fairness (parallel is wrong here)

Usage:
    runner = EvaluationRunner(gateway, registry)
    run = await runner.run_benchmark(
        cases=ALL_FIXTURE_CASES,
        deployment_mode=DeploymentMode.NVIDIA_HOSTED,
    )
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Any

from ..gateway import ModelGateway
from ..models import DeploymentMode, ModelRequest, ReasoningLevel, RiskLevel
from ..registry import ModelRegistry
from ..router import ModelRouter
from ..routing import PolicyFilter
from .benchmark import (
    BenchmarkCaseResult,
    BenchmarkMetadata,
    BenchmarkModelResult,
    BenchmarkRun,
    OracleResult,
    RouterSelectionRecord,
    compute_decision_gate,
    compute_oracle,
    compute_quality_score,
    compute_router_regret,
)
from .fixtures import (
    FIXTURE_DATASET_ID,
    FIXTURE_DATAPACK_CHECKSUM,
    get_fixture_input,
)
from .graders import EvaluationGrader, default_graders, run_graders
from .models import EvaluationCase, make_evaluation_run_key

logger = logging.getLogger(__name__)

# ── Reasoning/Risk level parsing ──────────────────────────────────────────────

_REASONING_MAP: dict[str, ReasoningLevel] = {
    "low": ReasoningLevel.LOW,
    "medium": ReasoningLevel.MEDIUM,
    "high": ReasoningLevel.HIGH,
}

_RISK_MAP: dict[str, RiskLevel] = {
    "low": RiskLevel.LOW,
    "medium": RiskLevel.MEDIUM,
    "high": RiskLevel.HIGH,
    "critical": RiskLevel.CRITICAL,
}


def _make_request_from_case(
    case: EvaluationCase,
    messages: list[dict[str, Any]],
    deployment_mode: DeploymentMode,
) -> ModelRequest:
    """Build a ModelRequest from an EvaluationCase + replayed messages."""
    reasoning = _REASONING_MAP.get(case.reasoning_level, ReasoningLevel.MEDIUM)
    risk = _RISK_MAP.get(case.risk_level, RiskLevel.LOW)
    return ModelRequest(
        task=f"warehouse.benchmark.{case.task_family.value.lower()}.{case.case_id}",
        messages=messages,
        reasoning=reasoning,
        risk_level=risk,
        deployment_mode=deployment_mode,
    )


def _build_fixture_messages(case: EvaluationCase) -> list[dict[str, Any]]:
    """
    Build minimal messages for a fixture case without a live WS2 snapshot.

    For the fixture corpus, we use a system prompt derived from the case's
    context_entities and a user turn with the case prompt.  This is
    deterministic across all models for the same case.
    """
    # Build a compact system prompt from the fixture context.
    entity_list = "\n".join(f"  - {e}" for e in case.context_entities)
    system = (
        "You are MAIW Copilot, an AI assistant for warehouse operations.\n"
        "Answer questions using ONLY the operational context provided below.\n"
        "Do not fabricate entity IDs, names, or facts not present in the context.\n\n"
        f"OPERATIONAL CONTEXT (fixture: {case.case_id}):\n"
        f"In-scope entity IDs:\n{entity_list}\n"
        f"Evaluation case metadata: {case.metadata}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": case.prompt},
    ]


# ── Router selection recording ────────────────────────────────────────────────


def record_router_selection(
    case: EvaluationCase,
    registry: ModelRegistry,
    deployment_mode: DeploymentMode,
) -> RouterSelectionRecord:
    """
    Run the production rule router (with no inference) and record its selection.

    This is independent of the forced-model evaluation — it captures what the
    current routing policy would choose for the same request.
    """
    messages = _build_fixture_messages(case)
    request = _make_request_from_case(case, messages, deployment_mode)
    router = ModelRouter(registry)
    policy_filter = PolicyFilter(registry)

    try:
        decision = router.route(request)
        candidate_ids = policy_filter.candidate_model_ids(request, deployment_mode)
        return RouterSelectionRecord(
            case_id=case.case_id,
            selected_model_id=decision.selected_model_id,
            selected_role=decision.selected_role,
            routing_rule=decision.routing_rule,
            routing_reason=decision.routing_reason,
            routing_strategy=decision.routing_strategy,
            routing_latency_ms=decision.routing_latency_ms,
            candidate_models=candidate_ids,
            policy_compliant=True,
        )
    except Exception as exc:
        logger.error("Router failed for case %s: %s", case.case_id, exc)
        return RouterSelectionRecord(
            case_id=case.case_id,
            selected_model_id="<router error>",
            selected_role="<unknown>",
            routing_rule="error",
            routing_reason=str(exc),
            routing_strategy="rules",
            routing_latency_ms=0.0,
            candidate_models=[],
            policy_compliant=False,
        )


# ── Evaluation runner ─────────────────────────────────────────────────────────


class EvaluationRunner:
    """
    Orchestrates multi-model benchmark evaluation for a fixture corpus.

    Architecture:
        - Calls ModelGateway.evaluate_with_model() for each (case, model) pair.
        - Sequential evaluation (not concurrent) for latency fairness.
        - Applies deterministic graders from 18B.
        - Records router selection independently.
        - Computes oracle and regret per case.
        - Accumulates results into BenchmarkRun.
    """

    def __init__(
        self,
        gateway: ModelGateway,
        registry: ModelRegistry,
        graders: list[EvaluationGrader] | None = None,
    ) -> None:
        self._gateway = gateway
        self._registry = registry
        self._graders = graders or default_graders()

    async def run_case(
        self,
        case: EvaluationCase,
        candidate_model_ids: list[str],
        deployment_mode: DeploymentMode = DeploymentMode.NVIDIA_HOSTED,
        dataset_id: str = FIXTURE_DATASET_ID,
        semantic_checksum: str = FIXTURE_DATAPACK_CHECKSUM,
        scenario_id: str | None = None,
        context_snapshot_id: str | None = None,
        warehouse_state_snapshot_id: str | None = None,
    ) -> list[BenchmarkModelResult]:
        """
        Run all candidate models against one EvaluationCase.

        All models receive the EXACT SAME messages (replay context invariant).
        Sequential by default for latency fairness.

        Returns list of BenchmarkModelResult, one per candidate model.
        """
        # Build messages ONCE — same for all models (fixed-context invariant §2).
        messages = _build_fixture_messages(case)
        request_template = _make_request_from_case(case, messages, deployment_mode)

        prompt_hash = hashlib.sha256(case.prompt.encode()).hexdigest()
        effective_scenario_id = scenario_id or case.case_id
        effective_context_id = context_snapshot_id or case.context_snapshot_id

        results: list[BenchmarkModelResult] = []

        for model_id in candidate_model_ids:
            logger.info(
                "EvaluationRunner: case=%s model=%s",
                case.case_id,
                model_id,
            )

            # Build per-model request (same messages, same deployment_mode).
            model_request = ModelRequest(
                task=request_template.task,
                messages=messages,  # same messages — fixed context invariant
                reasoning=request_template.reasoning,
                risk_level=request_template.risk_level,
                deployment_mode=deployment_mode,
            )

            # Evaluate run key (reproducibility identity).
            eval_run_key = make_evaluation_run_key(
                dataset_id=dataset_id,
                prompt_hash=prompt_hash,
                model_id=model_id,
                deployment_id=deployment_mode.value,
                context_snapshot_id=effective_context_id,
                warehouse_state_snapshot_id=warehouse_state_snapshot_id,
            )

            # Forced-model evaluation — no fallback.
            eval_result = await self._gateway.evaluate_with_model(
                request=model_request,
                model_id=model_id,
                allow_out_of_policy=False,
            )

            # Build a minimal ModelEvaluationResult for the graders.
            from .models import ModelEvaluationResult

            grader_input = ModelEvaluationResult(
                evaluation_input_id=case.case_id,
                model_id=model_id,
                deployment_id=deployment_mode.value,
                response=eval_result.response_content,
                latency_ms=eval_result.total_latency_ms,
                routing_latency_ms=eval_result.routing_latency_ms,
                routing_strategy="forced_evaluation",
                candidate_models=eval_result.candidate_models,
                input_tokens=eval_result.input_tokens,
                output_tokens=eval_result.output_tokens,
                error=eval_result.error,
            )

            # Run deterministic graders (same graders for all models).
            if eval_result.error is None and eval_result.response_content is not None:
                grader_results = run_graders(case, grader_input, self._graders)
            else:
                # No response — all graders mark failed (except skipped ones).
                grader_results = run_graders(case, grader_input, self._graders)

            quality_score, applicable, passed = compute_quality_score(grader_results)
            quality_pass = (
                quality_score == 1.0
                and applicable > 0
                and eval_result.error is None
                and not eval_result.timed_out
            )

            # Policy interpretation (§19).
            interpretation = ""
            if not eval_result.policy_compliant and quality_pass:
                interpretation = "OFFLINE QUALITY PASS / NOT PRODUCTION ELIGIBLE UNDER CURRENT POLICY"

            benchmark_result = BenchmarkModelResult(
                evaluation_run_key=eval_run_key,
                case_id=case.case_id,
                dataset_id=dataset_id,
                semantic_checksum=semantic_checksum,
                scenario_id=effective_scenario_id,
                context_snapshot_id=effective_context_id,
                warehouse_state_snapshot_id=warehouse_state_snapshot_id,
                prompt_hash=prompt_hash,
                model_id=model_id,
                deployment=deployment_mode.value,
                grader_results=grader_results,
                quality_score=quality_score,
                quality_pass=quality_pass,
                applicable_graders=applicable,
                passed_graders=passed,
                routing_latency_ms=eval_result.routing_latency_ms,
                inference_latency_ms=eval_result.inference_latency_ms,
                total_latency_ms=eval_result.total_latency_ms,
                routing_strategy="forced_evaluation",
                provider="nvidia-nim",
                candidate_models=eval_result.candidate_models,
                input_tokens=eval_result.input_tokens,
                output_tokens=eval_result.output_tokens,
                cost="unavailable",
                timeout=eval_result.timed_out,
                error=eval_result.error,
                fallback_used=False,  # forced evaluation never falls back
                policy_compliant=eval_result.policy_compliant,
                interpretation=interpretation,
                response_snippet=(
                    eval_result.response_content[:300]
                    if eval_result.response_content
                    else None
                ),
            )
            results.append(benchmark_result)

        return results

    async def run_benchmark(
        self,
        cases: list[EvaluationCase],
        deployment_mode: DeploymentMode = DeploymentMode.NVIDIA_HOSTED,
        dataset_id: str = FIXTURE_DATASET_ID,
        semantic_checksum: str = FIXTURE_DATAPACK_CHECKSUM,
        endpoint_status: str = "NOT RUN — ENDPOINT UNAVAILABLE",
    ) -> BenchmarkRun:
        """
        Run the full benchmark: all cases × all eligible models.

        Builds candidate_model_ids from the first case's request policy
        (all fixture cases use the same deployment_mode; candidates are
        re-computed per case to handle heterogeneous risk/reasoning levels).

        Returns a complete BenchmarkRun ready for artifact serialisation.
        """
        all_model_ids: set[str] = set()
        case_results: list[BenchmarkCaseResult] = []
        policy_filter = PolicyFilter(self._registry)

        for case in cases:
            # Per-case candidate computation (risk/reasoning may differ).
            messages = _build_fixture_messages(case)
            request = _make_request_from_case(case, messages, deployment_mode)
            candidate_ids = policy_filter.candidate_model_ids(request, deployment_mode)
            all_model_ids.update(candidate_ids)

            logger.info(
                "EvaluationRunner: benchmark case=%s candidates=%s",
                case.case_id,
                candidate_ids,
            )

            # 1. Record router selection (rule router, no inference).
            router_selection = record_router_selection(
                case, self._registry, deployment_mode
            )

            # 2. Run all eligible models (sequential for latency fairness).
            model_results = await self.run_case(
                case=case,
                candidate_model_ids=candidate_ids,
                deployment_mode=deployment_mode,
                dataset_id=dataset_id,
                semantic_checksum=semantic_checksum,
            )

            # 3. Oracle computation.
            oracle = compute_oracle(model_results)

            # 4. Router regret.
            regret = compute_router_regret(
                router_model=router_selection.selected_model_id,
                oracle=oracle,
                model_results=model_results,
            )

            case_results.append(
                BenchmarkCaseResult(
                    case_id=case.case_id,
                    case_prompt=case.prompt,
                    task_family=case.task_family.value,
                    model_results=model_results,
                    router_selection=router_selection,
                    oracle=oracle,
                    regret=regret,
                )
            )

        # 5. Decision gate.
        decision_gate = compute_decision_gate(case_results)

        metadata = BenchmarkMetadata(
            dataset_id=dataset_id,
            semantic_checksum=semantic_checksum,
            run_timestamp=datetime.now(timezone.utc).isoformat(),
            cases_count=len(cases),
            models_evaluated=sorted(all_model_ids),
            deployment_mode=deployment_mode.value,
            phase="18C",
            endpoint_status=endpoint_status,
        )

        return BenchmarkRun(
            metadata=metadata,
            cases=case_results,
            decision_gate=decision_gate,
        )
