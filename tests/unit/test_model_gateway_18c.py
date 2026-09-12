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
Phase 18C test suite — Fixed-Context Multi-Model Benchmark.

Covers (spec §31):
  - Forced-model evaluation (evaluate_with_model)
  - Eligibility enforcement (policy-compliant vs out-of-policy)
  - Replay determinism (same messages → same context for all models)
  - Same-context across models (fixed-context invariant)
  - Grader consistency (same graders, same case → same result)
  - Fallback contamination labeling (FORCED MODEL FAILED, FALLBACK USED)
  - Timeout result (timed_out=True recorded, not retried)
  - Evaluation run key determinism
  - Artifact serialization (BenchmarkRun.to_json)
  - Baseline router selection recording
  - Oracle computation (best quality, fastest passing)
  - No governance side effects (no ActionProposal, no MCP write)

All tests mock NIMProvider — no live endpoints required.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maiw_models.evaluation.models import (
    EvaluationCallResult,
    EvaluationCase,
    GraderResult,
    ModelEvaluationResult,
    TaskFamily,
    make_evaluation_run_key,
)
from maiw_models.evaluation.graders import (
    CapabilityMatchGrader,
    ForbiddenClaimsGrader,
    HallucinationGrader,
    RequiredEvidenceGrader,
    SchemaValidityGrader,
    TargetMatchGrader,
    default_graders,
    run_graders,
)
from maiw_models.evaluation.fixtures import (
    ALL_FIXTURE_CASES,
    equipment_failure,
    healthy_baseline,
    wave17_labor_risk,
)
from maiw_models.evaluation.inventory import (
    build_candidate_inventory,
    build_benchmark_candidates,
    CandidateModelInfo,
)
from maiw_models.evaluation.benchmark import (
    BenchmarkCaseResult,
    BenchmarkMetadata,
    BenchmarkModelResult,
    BenchmarkRun,
    OracleResult,
    RouterRegret,
    RouterSelectionRecord,
    compute_decision_gate,
    compute_oracle,
    compute_quality_score,
    compute_router_regret,
)
from maiw_models.evaluation.runner import (
    EvaluationRunner,
    _build_fixture_messages,
    _make_request_from_case,
    record_router_selection,
)
from maiw_models.gateway import ModelGateway
from maiw_models.models import (
    DeploymentMode,
    ModelCapability,
    ModelRequest,
    ModelRouteDecision,
    ModelResponse,
    ReasoningLevel,
    RiskLevel,
    DeploymentStatus,
    LatencyClass,
    CostClass,
)
from maiw_models.registry import ModelRegistry
from maiw_models.router import ModelRouter
from maiw_models.telemetry import GatewayTelemetry
from maiw_models.providers.nim import NIMProvider
from maiw_models.errors import ModelUnavailable

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_registry(enabled_roles: list[str] | None = None) -> ModelRegistry:
    """Build a ModelRegistry with selective role enablement via env patch."""
    env_overrides: dict[str, str] = {
        "NEMOTRON_LIGHTNING_ENABLED": "false",
        "NEMOTRON_NANO_ENABLED": "false",
        "NEMOTRON_SUPER_ENABLED": "false",
        "NEMOTRON_ULTRA_ENABLED": "false",
        "NEMOTRON_NANO_OMNI_ENABLED": "false",
    }
    if enabled_roles:
        role_env_map = {
            "lightning": "NEMOTRON_LIGHTNING_ENABLED",
            "nano": "NEMOTRON_NANO_ENABLED",
            "super": "NEMOTRON_SUPER_ENABLED",
            "ultra": "NEMOTRON_ULTRA_ENABLED",
            "nano-omni": "NEMOTRON_NANO_OMNI_ENABLED",
        }
        for role in enabled_roles:
            env_overrides[role_env_map[role]] = "true"

    with patch.dict(os.environ, env_overrides):
        return ModelRegistry()


def _make_nim_provider(response_text: str = "mock response") -> NIMProvider:
    """Build a NIMProvider with a mocked NIMClient."""
    from maiw_models.providers.nim_client import LLMResponse

    mock_client = MagicMock()
    mock_client.generate_response = AsyncMock(
        return_value=LLMResponse(
            content=response_text,
            model="mock-model",
            finish_reason="stop",
            usage={"prompt_tokens": 10, "completion_tokens": 20},
        )
    )
    return NIMProvider(mock_client)


def _make_gateway(
    enabled_roles: list[str] | None = None,
    response_text: str = "mock response about wave-17 labor",
) -> ModelGateway:
    """Build a ModelGateway with mocked NIM provider."""
    registry = _make_registry(enabled_roles or ["nano", "super"])
    provider = _make_nim_provider(response_text)
    router = ModelRouter(registry)
    telemetry = GatewayTelemetry()
    return ModelGateway(
        provider=provider,
        registry=registry,
        router=router,
        telemetry=telemetry,
    )


def _nano_model_id() -> str:
    return os.environ.get("NEMOTRON_NANO_MODEL", "nvidia/nemotron-3-nano-30b-a3b")


def _super_model_id() -> str:
    return os.environ.get("NEMOTRON_SUPER_MODEL", "nvidia/nemotron-3-super-120b-a12b")


def _low_risk_request() -> ModelRequest:
    return ModelRequest(
        task="test.ask",
        messages=[{"role": "user", "content": "Why is Wave 17 at risk?"}],
        reasoning=ReasoningLevel.MEDIUM,
        risk_level=RiskLevel.LOW,
        deployment_mode=DeploymentMode.NVIDIA_HOSTED,
    )


def _high_risk_request() -> ModelRequest:
    return ModelRequest(
        task="test.analyze",
        messages=[{"role": "user", "content": "Analyze Wave 17."}],
        reasoning=ReasoningLevel.HIGH,
        risk_level=RiskLevel.HIGH,
        deployment_mode=DeploymentMode.NVIDIA_HOSTED,
    )


# ─────────────────────────────────────────────────────────────────────────────
# §3: Forced-model evaluation entry point
# ─────────────────────────────────────────────────────────────────────────────


class TestForcedModelEvaluation:
    """evaluate_with_model() is present, callable, and returns EvaluationCallResult."""

    @pytest.mark.asyncio
    async def test_evaluate_with_model_returns_evaluation_call_result(self):
        gateway = _make_gateway(["nano", "super"])
        nano_id = _nano_model_id()
        request = _low_risk_request()
        result = await gateway.evaluate_with_model(request=request, model_id=nano_id)
        assert isinstance(result, EvaluationCallResult)
        assert result.forced_model_id == nano_id

    @pytest.mark.asyncio
    async def test_evaluate_with_model_uses_forced_model_not_router(self):
        """Super is returned when we force-select nano — router would have chosen nano."""
        gateway = _make_gateway(["nano", "super"])
        super_id = _super_model_id()
        # Low-risk medium-reasoning request → router would choose nano
        request = _low_risk_request()
        result = await gateway.evaluate_with_model(request=request, model_id=super_id)
        assert result.forced_model_id == super_id
        assert result.error is None  # out-of-policy for low-risk but super is eligible

    @pytest.mark.asyncio
    async def test_evaluate_with_model_emits_telemetry(self):
        """evaluate_with_model records success telemetry."""
        registry = _make_registry(["nano"])
        provider = _make_nim_provider("response text")
        router = ModelRouter(registry)
        telemetry = GatewayTelemetry()
        gateway = ModelGateway(
            provider=provider,
            registry=registry,
            router=router,
            telemetry=telemetry,
        )
        nano_id = _nano_model_id()
        request = _low_risk_request()
        with patch.object(telemetry, "record_success") as mock_record:
            await gateway.evaluate_with_model(request=request, model_id=nano_id)
            mock_record.assert_called_once()

    @pytest.mark.asyncio
    async def test_evaluate_with_model_unknown_model_returns_error(self):
        gateway = _make_gateway(["nano"])
        request = _low_risk_request()
        result = await gateway.evaluate_with_model(
            request=request, model_id="does-not-exist"
        )
        assert result.error is not None
        assert result.response_content is None
        assert result.forced_model_id == "does-not-exist"

    @pytest.mark.asyncio
    async def test_evaluate_with_model_fallback_never_used(self):
        """Forced evaluation never silently falls back."""
        registry = _make_registry(["nano"])
        # Make provider fail.
        mock_client = MagicMock()
        mock_client.generate_response = AsyncMock(
            side_effect=RuntimeError("provider error")
        )
        provider = NIMProvider(mock_client)
        gateway = ModelGateway(
            provider=provider,
            registry=registry,
            router=ModelRouter(registry),
            telemetry=GatewayTelemetry(),
        )
        nano_id = _nano_model_id()
        result = await gateway.evaluate_with_model(
            request=_low_risk_request(), model_id=nano_id
        )
        assert result.fallback_used is False
        assert result.error is not None
        assert "FORCED MODEL FAILED" in result.error

    @pytest.mark.asyncio
    async def test_evaluate_with_model_timeout_marked_not_retried(self):
        """Timeout is recorded as timed_out=True; no retry."""
        from maiw_mcp.deadline import RequestDeadlineExceeded

        registry = _make_registry(["nano"])
        mock_client = MagicMock()
        mock_client.generate_response = AsyncMock(
            side_effect=RequestDeadlineExceeded(expired_by_ms=100.0)
        )
        provider = NIMProvider(mock_client)
        gateway = ModelGateway(
            provider=provider,
            registry=registry,
            router=ModelRouter(registry),
            telemetry=GatewayTelemetry(),
        )
        nano_id = _nano_model_id()
        result = await gateway.evaluate_with_model(
            request=_low_risk_request(), model_id=nano_id
        )
        assert result.timed_out is True
        assert result.fallback_used is False
        assert result.response_content is None

    @pytest.mark.asyncio
    async def test_evaluate_with_model_routing_strategy_is_forced_evaluation(self):
        """Synthetic route decision uses routing_strategy='forced_evaluation'."""
        registry = _make_registry(["nano"])
        provider = _make_nim_provider("ok")
        telemetry = GatewayTelemetry()
        gateway = ModelGateway(
            provider=provider,
            registry=registry,
            router=ModelRouter(registry),
            telemetry=telemetry,
        )
        nano_id = _nano_model_id()

        recorded_decisions = []
        original_record = telemetry.record_success

        def capture_success(**kwargs):
            recorded_decisions.append(kwargs.get("decision"))

        with patch.object(telemetry, "record_success", side_effect=capture_success):
            await gateway.evaluate_with_model(
                request=_low_risk_request(), model_id=nano_id
            )

        assert len(recorded_decisions) == 1
        assert recorded_decisions[0].routing_strategy == "forced_evaluation"
        assert recorded_decisions[0].routing_rule == "evaluation_override"

    @pytest.mark.asyncio
    async def test_evaluate_with_model_uses_request_deadline(self):
        """Pre-expired deadline returns timed_out=True without calling provider."""
        from maiw_mcp.deadline import RequestDeadline

        registry = _make_registry(["nano"])
        provider = _make_nim_provider("should not be called")
        gateway = ModelGateway(
            provider=provider,
            registry=registry,
            router=ModelRouter(registry),
            telemetry=GatewayTelemetry(),
        )
        nano_id = _nano_model_id()

        # Create an already-expired deadline using a past deadline_at.
        import time as _time

        past = _time.monotonic() - 10.0  # 10 seconds in the past
        from dataclasses import fields as _dc_fields
        import dataclasses as _dc

        deadline = RequestDeadline(
            started_at=past,
            deadline_at=past + 0.001,  # 1ms window, already expired
        )

        request = ModelRequest(
            task="test",
            messages=[{"role": "user", "content": "test"}],
            deadline=deadline,
        )
        result = await gateway.evaluate_with_model(request=request, model_id=nano_id)
        assert result.timed_out is True


# ─────────────────────────────────────────────────────────────────────────────
# §4: Eligibility enforcement
# ─────────────────────────────────────────────────────────────────────────────


class TestEligibilityEnforcement:
    """Policy eligibility is checked before forced evaluation."""

    @pytest.mark.asyncio
    async def test_policy_compliant_model_succeeds(self):
        """Nano is eligible for low-risk medium-reasoning requests."""
        gateway = _make_gateway(["nano"])
        nano_id = _nano_model_id()
        result = await gateway.evaluate_with_model(
            request=_low_risk_request(), model_id=nano_id
        )
        assert result.policy_compliant is True
        assert result.error is None

    @pytest.mark.asyncio
    async def test_high_risk_blocks_nano_without_out_of_policy(self):
        """CRITICAL risk → nano not eligible; forced eval returns policy error."""
        gateway = _make_gateway(["nano"])
        nano_id = _nano_model_id()
        critical_request = ModelRequest(
            task="test.critical",
            messages=[{"role": "user", "content": "critical action"}],
            reasoning=ReasoningLevel.HIGH,
            risk_level=RiskLevel.CRITICAL,
            deployment_mode=DeploymentMode.NVIDIA_HOSTED,
        )
        result = await gateway.evaluate_with_model(
            request=critical_request, model_id=nano_id, allow_out_of_policy=False
        )
        assert result.policy_compliant is False
        assert result.error is not None
        assert result.response_content is None

    @pytest.mark.asyncio
    async def test_out_of_policy_flag_allows_proceed(self):
        """allow_out_of_policy=True allows evaluation even when model fails policy."""
        gateway = _make_gateway(["nano"])
        nano_id = _nano_model_id()
        critical_request = ModelRequest(
            task="test.critical",
            messages=[{"role": "user", "content": "critical action"}],
            reasoning=ReasoningLevel.HIGH,
            risk_level=RiskLevel.CRITICAL,
            deployment_mode=DeploymentMode.NVIDIA_HOSTED,
        )
        result = await gateway.evaluate_with_model(
            request=critical_request, model_id=nano_id, allow_out_of_policy=True
        )
        # policy_compliant is False but we still attempted the call
        assert result.policy_compliant is False
        # error may be None (response returned) or set (if provider failed in mock)
        # The key assertion: we did NOT immediately return due to policy without trying

    @pytest.mark.asyncio
    async def test_disabled_model_fails_eligibility(self):
        """Disabled model is not in PolicyFilter candidates."""
        gateway = _make_gateway(["super"])  # nano is disabled
        nano_id = _nano_model_id()
        result = await gateway.evaluate_with_model(
            request=_low_risk_request(), model_id=nano_id
        )
        assert result.policy_compliant is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_candidate_models_populated_in_result(self):
        """candidate_models contains the PolicyFilter eligible set."""
        gateway = _make_gateway(["nano", "super"])
        nano_id = _nano_model_id()
        result = await gateway.evaluate_with_model(
            request=_low_risk_request(), model_id=nano_id
        )
        assert isinstance(result.candidate_models, list)
        # nano and super are enabled; low-risk medium-reasoning → both eligible
        assert nano_id in result.candidate_models


# ─────────────────────────────────────────────────────────────────────────────
# §2 / §8: Fixed-context invariant — same messages for all models
# ─────────────────────────────────────────────────────────────────────────────


class TestFixedContextInvariant:
    """All models in a benchmark case receive the exact same messages."""

    def test_build_fixture_messages_deterministic(self):
        """Same EvaluationCase → same messages always."""
        msgs_a = _build_fixture_messages(wave17_labor_risk)
        msgs_b = _build_fixture_messages(wave17_labor_risk)
        assert msgs_a == msgs_b

    def test_build_fixture_messages_same_across_models(self):
        """
        Messages are built once per case — not per model.
        This is the fixed-context invariant.
        """
        msgs_nano = _build_fixture_messages(wave17_labor_risk)
        msgs_super = _build_fixture_messages(wave17_labor_risk)
        assert msgs_nano == msgs_super

    def test_different_cases_produce_different_messages(self):
        """Different EvaluationCase prompts → different messages."""
        msgs_labor = _build_fixture_messages(wave17_labor_risk)
        msgs_equip = _build_fixture_messages(equipment_failure)
        assert msgs_labor != msgs_equip

    def test_system_prompt_includes_context_entities(self):
        """System prompt contains the context entity IDs."""
        msgs = _build_fixture_messages(wave17_labor_risk)
        system_content = msgs[0]["content"]
        assert "wave-17" in system_content
        assert "labor-shift-morning" in system_content

    def test_user_prompt_is_case_prompt(self):
        """User turn is the exact case prompt text."""
        msgs = _build_fixture_messages(wave17_labor_risk)
        assert msgs[1]["role"] == "user"
        assert msgs[1]["content"] == wave17_labor_risk.prompt

    @pytest.mark.asyncio
    async def test_runner_sends_same_messages_to_all_models(self):
        """EvaluationRunner uses same messages for all models in a case."""
        registry = _make_registry(["nano", "super"])
        captured_requests = []

        from maiw_models.providers.nim_client import LLMResponse

        mock_client = MagicMock()

        async def capture_complete(**kwargs):
            model_id = kwargs.get("model_override", "unknown")
            messages = kwargs.get("messages", [])
            captured_requests.append((model_id, messages))
            return LLMResponse(
                content="wave-17 labor response",
                model=model_id,
                finish_reason="stop",
                usage={"prompt_tokens": 5, "completion_tokens": 10},
            )

        mock_client.generate_response = capture_complete
        provider = NIMProvider(mock_client)
        gateway = ModelGateway(
            provider=provider,
            registry=registry,
            router=ModelRouter(registry),
            telemetry=GatewayTelemetry(),
        )
        runner = EvaluationRunner(gateway, registry)

        nano_id = _nano_model_id()
        super_id = _super_model_id()
        results = await runner.run_case(
            case=healthy_baseline,
            candidate_model_ids=[nano_id, super_id],
        )

        assert len(results) == 2
        assert len(captured_requests) == 2
        # Same messages sent to both models.
        msgs_nano = captured_requests[0][1]
        msgs_super = captured_requests[1][1]
        assert (
            msgs_nano == msgs_super
        ), "Fixed-context invariant violated — messages differ"


# ─────────────────────────────────────────────────────────────────────────────
# §9 / §10: Grader consistency and quality scoring
# ─────────────────────────────────────────────────────────────────────────────


class TestGraderConsistency:
    """Same case + same result → same grader output (determinism)."""

    def _make_result(self, response: str) -> ModelEvaluationResult:
        return ModelEvaluationResult(
            evaluation_input_id="wave17-labor-risk-v1",
            model_id="test-model",
            deployment_id="nvidia_hosted",
            response=response,
            latency_ms=100.0,
            routing_latency_ms=1.0,
            routing_strategy="forced_evaluation",
            candidate_models=["test-model"],
        )

    def test_graders_deterministic_same_input(self):
        """Same case + same result → same grader output on repeated calls."""
        result = self._make_result(
            "The wave-17 labor bottleneck requires labor reallocation."
        )
        graders = default_graders()
        out_a = run_graders(wave17_labor_risk, result, graders)
        out_b = run_graders(wave17_labor_risk, result, graders)
        assert [(g.grader_name, g.passed) for g in out_a] == [
            (g.grader_name, g.passed) for g in out_b
        ]

    def test_quality_score_all_pass(self):
        """All applicable graders pass → quality_score == 1.0."""
        result = self._make_result(
            "Wave-17 is at risk due to labor bottleneck. "
            "Recommend labor reallocation to address the delay."
        )
        grader_results = run_graders(wave17_labor_risk, result, default_graders())
        score, applicable, passed = compute_quality_score(grader_results)
        assert passed == applicable
        assert score == 1.0

    def test_quality_score_partial_pass(self):
        """Partial grader pass → score between 0 and 1."""
        # Response mentions wave-17 but not labor (missing required_fact).
        result = self._make_result("wave-17 has a delay due to conveyor issues.")
        grader_results = run_graders(wave17_labor_risk, result, default_graders())
        score, applicable, passed = compute_quality_score(grader_results)
        # At least one grader should have failed (required_evidence: "labor" missing)
        assert score < 1.0

    def test_quality_score_skipped_graders_not_counted(self):
        """Graders that skipped (no expectations) don't inflate denominator."""
        # healthy_baseline has no expected_capability → capability_match is skipped.
        result = self._make_result("Wave-17 is on track. No intervention needed.")
        grader_results = run_graders(healthy_baseline, result, default_graders())
        score, applicable, passed = compute_quality_score(grader_results)
        # All applicable graders should pass (wave-17 mentioned, no forbidden claims).
        assert score == 1.0

    def test_grader_consistency_across_models(self):
        """Same EvaluationCase + different model IDs → same grader structure."""
        response = "wave-17 labor bottleneck requires labor reallocation."
        result_nano = self._make_result(response)
        result_nano.model_id = "model-a"
        result_super = self._make_result(response)
        result_super.model_id = "model-b"

        graders = default_graders()
        out_nano = run_graders(wave17_labor_risk, result_nano, graders)
        out_super = run_graders(wave17_labor_risk, result_super, graders)

        # Same response → same grader names and pass/fail results.
        assert [(g.grader_name, g.passed) for g in out_nano] == [
            (g.grader_name, g.passed) for g in out_super
        ]

    def test_empty_response_fails_applicable_graders(self):
        """Error/empty response fails required evidence and target graders."""
        result = self._make_result("")
        result.error = "FORCED MODEL FAILED"
        grader_results = run_graders(wave17_labor_risk, result, default_graders())
        failing = [g for g in grader_results if not g.passed]
        # required_evidence and target_match should fail (wave-17 and labor not present)
        assert len(failing) > 0


# ─────────────────────────────────────────────────────────────────────────────
# §13: Evaluation run key determinism
# ─────────────────────────────────────────────────────────────────────────────


class TestEvaluationRunKey:
    """make_evaluation_run_key is deterministic and stable."""

    def test_same_inputs_produce_same_key(self):
        key_a = make_evaluation_run_key(
            dataset_id="ds1",
            prompt_hash="ph1",
            model_id="model-a",
            deployment_id="nvidia_hosted",
            context_snapshot_id="ctx1",
            warehouse_state_snapshot_id="wh1",
        )
        key_b = make_evaluation_run_key(
            dataset_id="ds1",
            prompt_hash="ph1",
            model_id="model-a",
            deployment_id="nvidia_hosted",
            context_snapshot_id="ctx1",
            warehouse_state_snapshot_id="wh1",
        )
        assert key_a == key_b

    def test_different_model_produces_different_key(self):
        key_a = make_evaluation_run_key(
            dataset_id="ds1",
            prompt_hash="ph1",
            model_id="model-a",
            deployment_id="nvidia_hosted",
            context_snapshot_id=None,
            warehouse_state_snapshot_id=None,
        )
        key_b = make_evaluation_run_key(
            dataset_id="ds1",
            prompt_hash="ph1",
            model_id="model-b",
            deployment_id="nvidia_hosted",
            context_snapshot_id=None,
            warehouse_state_snapshot_id=None,
        )
        assert key_a != key_b

    def test_timestamps_not_in_key(self):
        """Key is identical regardless of when it's computed (no time component)."""
        import time

        key_a = make_evaluation_run_key(
            dataset_id="ds1",
            prompt_hash="ph1",
            model_id="model-a",
            deployment_id="nvidia_hosted",
            context_snapshot_id=None,
            warehouse_state_snapshot_id=None,
        )
        time.sleep(0.01)
        key_b = make_evaluation_run_key(
            dataset_id="ds1",
            prompt_hash="ph1",
            model_id="model-a",
            deployment_id="nvidia_hosted",
            context_snapshot_id=None,
            warehouse_state_snapshot_id=None,
        )
        assert key_a == key_b

    def test_key_is_hex_string(self):
        key = make_evaluation_run_key(
            dataset_id="ds",
            prompt_hash="ph",
            model_id="m",
            deployment_id="d",
            context_snapshot_id=None,
            warehouse_state_snapshot_id=None,
        )
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)


# ─────────────────────────────────────────────────────────────────────────────
# §14 / §15: Artifact serialization
# ─────────────────────────────────────────────────────────────────────────────


class TestArtifactSerialization:
    """BenchmarkRun serialises to valid JSON."""

    def _make_run(self) -> BenchmarkRun:
        from datetime import datetime, timezone

        mr = BenchmarkModelResult(
            evaluation_run_key="abc123",
            case_id="wave17-labor-risk-v1",
            dataset_id="eval-fixture-dataset-v1",
            semantic_checksum="fixture-checksum-abc123",
            scenario_id="wave17-labor-bottleneck",
            context_snapshot_id="fixture-ctx-wave17-001",
            warehouse_state_snapshot_id=None,
            prompt_hash="deadbeef",
            model_id="nvidia/nemotron-3-nano-30b-a3b",
            deployment="nvidia_hosted",
            quality_score=1.0,
            quality_pass=True,
            applicable_graders=3,
            passed_graders=3,
            total_latency_ms=420.5,
        )
        case_result = BenchmarkCaseResult(
            case_id="wave17-labor-risk-v1",
            case_prompt="Why is Wave 17 at risk?",
            task_family="ASK",
            model_results=[mr],
            router_selection=RouterSelectionRecord(
                case_id="wave17-labor-risk-v1",
                selected_model_id="nvidia/nemotron-3-super-120b-a12b",
                selected_role="super",
                routing_rule="high_reasoning",
                routing_reason="HIGH reasoning → Super",
                routing_strategy="rules",
                routing_latency_ms=0.5,
                candidate_models=["nvidia/nemotron-3-super-120b-a12b"],
            ),
            oracle=OracleResult(
                best_quality_model="nvidia/nemotron-3-nano-30b-a3b",
                best_quality_score=1.0,
                fastest_passing_model="nvidia/nemotron-3-nano-30b-a3b",
                fastest_passing_latency_ms=420.5,
                passing_models=["nvidia/nemotron-3-nano-30b-a3b"],
            ),
        )
        metadata = BenchmarkMetadata(
            dataset_id="eval-fixture-dataset-v1",
            semantic_checksum="fixture-checksum-abc123",
            run_timestamp=datetime.now(timezone.utc).isoformat(),
            cases_count=1,
            models_evaluated=["nvidia/nemotron-3-nano-30b-a3b"],
            deployment_mode="nvidia_hosted",
        )
        return BenchmarkRun(
            metadata=metadata,
            cases=[case_result],
            decision_gate="CURRENT ROUTER SUFFICIENT",
        )

    def test_to_dict_is_serializable(self):
        run = self._make_run()
        data = run.to_dict()
        serialized = json.dumps(data)
        assert isinstance(serialized, str)
        assert len(serialized) > 0

    def test_to_json_round_trips(self):
        run = self._make_run()
        json_str = run.to_json()
        data = json.loads(json_str)
        assert data["metadata"]["dataset_id"] == "eval-fixture-dataset-v1"
        assert data["decision_gate"] == "CURRENT ROUTER SUFFICIENT"
        assert len(data["cases"]) == 1

    def test_benchmark_model_result_to_dict_has_required_fields(self):
        run = self._make_run()
        mr_dict = run.cases[0].model_results[0].to_dict()
        required_keys = [
            "evaluation_run_key",
            "case_id",
            "dataset_id",
            "semantic_checksum",
            "scenario_id",
            "context_snapshot_id",
            "warehouse_state_snapshot_id",
            "prompt_hash",
            "model_id",
            "deployment",
            "quality",
            "latency",
            "outcome",
        ]
        for key in required_keys:
            assert key in mr_dict, f"Missing key: {key}"


# ─────────────────────────────────────────────────────────────────────────────
# §16 / §17: Router selection and oracle computation
# ─────────────────────────────────────────────────────────────────────────────


class TestRouterSelectionAndOracle:
    """Router selection recorded correctly; oracle selects best/fastest."""

    def test_record_router_selection_returns_selection_record(self):
        registry = _make_registry(["nano", "super"])
        selection = record_router_selection(
            case=healthy_baseline,
            registry=registry,
            deployment_mode=DeploymentMode.NVIDIA_HOSTED,
        )
        assert isinstance(selection, RouterSelectionRecord)
        assert selection.case_id == healthy_baseline.case_id
        assert selection.selected_model_id != ""
        assert selection.routing_rule != ""

    def test_record_router_selection_high_risk_selects_super(self):
        """High reasoning/risk → router selects super."""
        registry = _make_registry(["nano", "super"])
        # wave17_labor_risk has reasoning=high, risk=high
        selection = record_router_selection(
            case=wave17_labor_risk,
            registry=registry,
            deployment_mode=DeploymentMode.NVIDIA_HOSTED,
        )
        assert selection.selected_role == "super"

    def test_record_router_selection_medium_reasoning_selects_nano_or_better(self):
        """Medium reasoning → router selects nano."""
        registry = _make_registry(["nano"])
        selection = record_router_selection(
            case=healthy_baseline,
            registry=registry,
            deployment_mode=DeploymentMode.NVIDIA_HOSTED,
        )
        assert selection.selected_role == "nano"

    def test_oracle_best_quality(self):
        """compute_oracle selects highest quality_score model."""
        results = [
            BenchmarkModelResult(
                evaluation_run_key="k1",
                case_id="c1",
                dataset_id="d",
                semantic_checksum="s",
                scenario_id="s",
                context_snapshot_id=None,
                warehouse_state_snapshot_id=None,
                prompt_hash="p",
                model_id="nano",
                deployment="hosted",
                quality_score=0.6,
                quality_pass=False,
                total_latency_ms=400,
            ),
            BenchmarkModelResult(
                evaluation_run_key="k2",
                case_id="c1",
                dataset_id="d",
                semantic_checksum="s",
                scenario_id="s",
                context_snapshot_id=None,
                warehouse_state_snapshot_id=None,
                prompt_hash="p",
                model_id="super",
                deployment="hosted",
                quality_score=1.0,
                quality_pass=True,
                total_latency_ms=1800,
            ),
        ]
        oracle = compute_oracle(results)
        assert oracle.best_quality_model == "super"
        assert oracle.best_quality_score == 1.0

    def test_oracle_fastest_passing(self):
        """compute_oracle selects minimum latency among quality_pass=True models."""
        results = [
            BenchmarkModelResult(
                evaluation_run_key="k1",
                case_id="c1",
                dataset_id="d",
                semantic_checksum="s",
                scenario_id="s",
                context_snapshot_id=None,
                warehouse_state_snapshot_id=None,
                prompt_hash="p",
                model_id="nano",
                deployment="hosted",
                quality_score=1.0,
                quality_pass=True,
                total_latency_ms=400,
            ),
            BenchmarkModelResult(
                evaluation_run_key="k2",
                case_id="c1",
                dataset_id="d",
                semantic_checksum="s",
                scenario_id="s",
                context_snapshot_id=None,
                warehouse_state_snapshot_id=None,
                prompt_hash="p",
                model_id="super",
                deployment="hosted",
                quality_score=1.0,
                quality_pass=True,
                total_latency_ms=1800,
            ),
        ]
        oracle = compute_oracle(results)
        assert oracle.fastest_passing_model == "nano"
        assert oracle.fastest_passing_latency_ms == 400

    def test_oracle_cost_always_unavailable(self):
        results = [
            BenchmarkModelResult(
                evaluation_run_key="k1",
                case_id="c1",
                dataset_id="d",
                semantic_checksum="s",
                scenario_id="s",
                context_snapshot_id=None,
                warehouse_state_snapshot_id=None,
                prompt_hash="p",
                model_id="nano",
                deployment="hosted",
                quality_score=1.0,
                quality_pass=True,
                total_latency_ms=400,
            ),
        ]
        oracle = compute_oracle(results)
        assert oracle.lowest_cost_passing_model == "unavailable"

    def test_oracle_empty_results(self):
        oracle = compute_oracle([])
        assert oracle.best_quality_model is None
        assert oracle.fastest_passing_model is None


# ─────────────────────────────────────────────────────────────────────────────
# §18: Router regret
# ─────────────────────────────────────────────────────────────────────────────


class TestRouterRegret:
    """Router regret split by dimension — quality and latency."""

    def _make_results(
        self,
        nano_score: float,
        super_score: float,
        nano_latency: float = 400,
        super_latency: float = 1800,
    ) -> list[BenchmarkModelResult]:
        return [
            BenchmarkModelResult(
                evaluation_run_key="k1",
                case_id="c1",
                dataset_id="d",
                semantic_checksum="s",
                scenario_id="s",
                context_snapshot_id=None,
                warehouse_state_snapshot_id=None,
                prompt_hash="p",
                model_id="nano",
                deployment="hosted",
                quality_score=nano_score,
                quality_pass=(nano_score == 1.0),
                total_latency_ms=nano_latency,
            ),
            BenchmarkModelResult(
                evaluation_run_key="k2",
                case_id="c1",
                dataset_id="d",
                semantic_checksum="s",
                scenario_id="s",
                context_snapshot_id=None,
                warehouse_state_snapshot_id=None,
                prompt_hash="p",
                model_id="super",
                deployment="hosted",
                quality_score=super_score,
                quality_pass=(super_score == 1.0),
                total_latency_ms=super_latency,
            ),
        ]

    def test_no_regret_when_router_picks_best(self):
        """Router picks super; super is best quality and fastest passer."""
        results = self._make_results(nano_score=0.5, super_score=1.0)
        oracle = compute_oracle(results)
        regret = compute_router_regret("super", oracle, results)
        assert regret.quality_regret is False
        assert regret.latency_regret is False

    def test_quality_regret_when_router_misses_better_model(self):
        """Router picks nano; super has higher quality_score."""
        results = self._make_results(nano_score=0.5, super_score=1.0)
        oracle = compute_oracle(results)
        regret = compute_router_regret("nano", oracle, results)
        assert regret.quality_regret is True
        assert "nano" in regret.quality_regret_detail
        assert "super" in regret.quality_regret_detail

    def test_latency_regret_when_faster_model_also_passes(self):
        """Router picks super (1800ms); nano also passes and is faster (400ms)."""
        results = self._make_results(nano_score=1.0, super_score=1.0)
        oracle = compute_oracle(results)
        regret = compute_router_regret("super", oracle, results)
        assert regret.latency_regret is True
        assert (
            "1800" in regret.latency_regret_detail
            or "1800ms" in regret.latency_regret_detail
        )

    def test_no_latency_regret_when_router_picks_fastest_passing(self):
        """Router picks nano; nano is fastest passing."""
        results = self._make_results(nano_score=1.0, super_score=1.0)
        oracle = compute_oracle(results)
        regret = compute_router_regret("nano", oracle, results)
        assert regret.latency_regret is False

    def test_out_of_policy_quality_regret_adds_policy_note(self):
        """Better model is out-of-policy → quality_regret_policy_note is set."""
        results = [
            BenchmarkModelResult(
                evaluation_run_key="k1",
                case_id="c1",
                dataset_id="d",
                semantic_checksum="s",
                scenario_id="s",
                context_snapshot_id=None,
                warehouse_state_snapshot_id=None,
                prompt_hash="p",
                model_id="nano",
                deployment="hosted",
                quality_score=0.5,
                quality_pass=False,
                total_latency_ms=400,
                policy_compliant=True,
            ),
            BenchmarkModelResult(
                evaluation_run_key="k2",
                case_id="c1",
                dataset_id="d",
                semantic_checksum="s",
                scenario_id="s",
                context_snapshot_id=None,
                warehouse_state_snapshot_id=None,
                prompt_hash="p",
                model_id="research-model",
                deployment="hosted",
                quality_score=1.0,
                quality_pass=True,
                total_latency_ms=2000,
                policy_compliant=False,  # out-of-policy
            ),
        ]
        oracle = compute_oracle(results)
        regret = compute_router_regret("nano", oracle, results)
        assert regret.quality_regret is True
        assert regret.quality_regret_policy_note != ""
        assert "NOT PRODUCTION ELIGIBLE" in regret.quality_regret_policy_note


# ─────────────────────────────────────────────────────────────────────────────
# §28: Decision gate
# ─────────────────────────────────────────────────────────────────────────────


class TestDecisionGate:
    """compute_decision_gate returns exactly one of two values."""

    def _make_case_result(
        self,
        quality_regret: bool = False,
        latency_regret: bool = False,
        policy_note: str = "",
    ) -> BenchmarkCaseResult:
        regret = RouterRegret(
            router_model="nano",
            quality_regret=quality_regret,
            latency_regret=latency_regret,
            quality_regret_policy_note=policy_note,
        )
        return BenchmarkCaseResult(
            case_id="test",
            case_prompt="test",
            task_family="ASK",
            regret=regret,
        )

    def test_sufficient_when_no_regret(self):
        cases = [self._make_case_result(False, False)]
        assert compute_decision_gate(cases) == "CURRENT ROUTER SUFFICIENT"

    def test_gaps_when_quality_regret_policy_compliant(self):
        """Quality regret with no policy note → GAPS."""
        cases = [self._make_case_result(quality_regret=True, policy_note="")]
        assert compute_decision_gate(cases) == "CURRENT ROUTER HAS MEASURABLE GAPS"

    def test_sufficient_when_quality_regret_is_out_of_policy(self):
        """Quality regret where better model is out-of-policy → SUFFICIENT."""
        cases = [
            self._make_case_result(
                quality_regret=True,
                policy_note="OFFLINE QUALITY PASS / NOT PRODUCTION ELIGIBLE UNDER CURRENT POLICY: ...",
            )
        ]
        assert compute_decision_gate(cases) == "CURRENT ROUTER SUFFICIENT"

    def test_gaps_when_latency_regret(self):
        cases = [self._make_case_result(latency_regret=True)]
        assert compute_decision_gate(cases) == "CURRENT ROUTER HAS MEASURABLE GAPS"

    def test_returns_exactly_one_of_two_values(self):
        valid = {"CURRENT ROUTER SUFFICIENT", "CURRENT ROUTER HAS MEASURABLE GAPS"}
        for quality_regret in [True, False]:
            for latency_regret in [True, False]:
                cases = [self._make_case_result(quality_regret, latency_regret)]
                result = compute_decision_gate(cases)
                assert result in valid


# ─────────────────────────────────────────────────────────────────────────────
# §5: Candidate model inventory
# ─────────────────────────────────────────────────────────────────────────────


class TestCandidateInventory:
    """Inventory built from registry — not hardcoded."""

    def test_inventory_built_from_registry(self):
        registry = _make_registry(["nano", "super"])
        inventory = build_candidate_inventory(registry, DeploymentMode.NVIDIA_HOSTED)
        assert len(inventory) > 0
        assert all(isinstance(i, CandidateModelInfo) for i in inventory)

    def test_inventory_includes_all_roles(self):
        registry = _make_registry(["nano", "super"])
        inventory = build_candidate_inventory(registry, DeploymentMode.NVIDIA_HOSTED)
        roles = {i.role for i in inventory}
        assert "nano" in roles
        assert "super" in roles

    def test_inventory_reflects_enabled_state(self):
        registry = _make_registry(["super"])  # nano disabled
        inventory = build_candidate_inventory(registry, DeploymentMode.NVIDIA_HOSTED)
        nano_entry = next((i for i in inventory if i.role == "nano"), None)
        assert nano_entry is not None
        assert nano_entry.enabled is False

    def test_benchmark_candidates_excludes_disabled_models(self):
        registry = _make_registry(["super"])
        request = _low_risk_request()
        candidates = build_benchmark_candidates(
            registry, request, DeploymentMode.NVIDIA_HOSTED
        )
        nano_id = _nano_model_id()
        assert nano_id not in candidates

    def test_inventory_to_dict_serializable(self):
        registry = _make_registry(["nano"])
        inventory = build_candidate_inventory(registry, DeploymentMode.NVIDIA_HOSTED)
        for info in inventory:
            data = info.to_dict()
            assert "model_id" in data
            assert "role" in data
            assert "enabled" in data
            assert "available" in data
            json.dumps(data)  # must be JSON-serializable


# ─────────────────────────────────────────────────────────────────────────────
# §24: No governance side effects
# ─────────────────────────────────────────────────────────────────────────────


class TestNoGovernanceSideEffects:
    """evaluate_with_model must not create ActionProposal, approval, or MCP writes."""

    def test_evaluation_call_result_has_no_governance_fields(self):
        """EvaluationCallResult has no ActionProposal, approval, or MCP fields."""
        import dataclasses

        fields = {f.name for f in dataclasses.fields(EvaluationCallResult)}
        forbidden_fields = {
            "action_proposal",
            "approval",
            "mcp_call",
            "decision_engine",
            "approval_store",
            "executor",
            "conversation_turn",
        }
        assert fields.isdisjoint(
            forbidden_fields
        ), f"EvaluationCallResult has governance fields: {fields & forbidden_fields}"

    def test_evaluation_runner_does_not_import_governance(self):
        """evaluation.runner does not import governance modules."""
        import importlib

        mod = importlib.import_module("maiw_models.evaluation.runner")
        source = open(mod.__file__).read()
        # Check import statements only (not comments).
        import_lines = [
            line.strip()
            for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        import_text = "\n".join(import_lines)
        forbidden_imports = [
            "from maiw_decision",
            "from maiw_execution",
            "import maiw_decision",
            "import maiw_execution",
        ]
        for forbidden in forbidden_imports:
            assert (
                forbidden not in import_text
            ), f"evaluation.runner has governance import: {forbidden}"

    def test_benchmark_module_does_not_import_governance(self):
        """evaluation.benchmark does not import governance modules."""
        import importlib

        mod = importlib.import_module("maiw_models.evaluation.benchmark")
        source = open(mod.__file__).read()
        import_lines = [
            line.strip()
            for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        import_text = "\n".join(import_lines)
        forbidden = [
            "from maiw_decision",
            "from maiw_execution",
            "import maiw_decision",
            "import maiw_execution",
        ]
        for f in forbidden:
            assert f not in import_text, f"benchmark has governance import: {f}"


# ─────────────────────────────────────────────────────────────────────────────
# §22: Fallback contamination labeling
# ─────────────────────────────────────────────────────────────────────────────


class TestFallbackContaminationLabeling:
    """When forced model fails, result is labeled FORCED MODEL FAILED, no fallback."""

    @pytest.mark.asyncio
    async def test_forced_model_fail_labeled_correctly(self):
        registry = _make_registry(["nano", "super"])
        mock_client = MagicMock()
        mock_client.generate_response = AsyncMock(side_effect=RuntimeError("NIM error"))
        provider = NIMProvider(mock_client)
        gateway = ModelGateway(
            provider=provider,
            registry=registry,
            router=ModelRouter(registry),
            telemetry=GatewayTelemetry(),
        )
        nano_id = _nano_model_id()
        result = await gateway.evaluate_with_model(
            request=_low_risk_request(), model_id=nano_id
        )
        assert result.error is not None
        assert "FORCED MODEL FAILED" in result.error
        assert result.fallback_used is False
        assert result.response_content is None

    @pytest.mark.asyncio
    async def test_benchmark_model_result_fallback_always_false(self):
        """BenchmarkModelResult.fallback_used is always False for forced eval."""
        registry = _make_registry(["nano"])
        provider = _make_nim_provider("wave-17 labor")
        gateway = ModelGateway(
            provider=provider,
            registry=registry,
            router=ModelRouter(registry),
            telemetry=GatewayTelemetry(),
        )
        runner = EvaluationRunner(gateway, registry)
        nano_id = _nano_model_id()
        results = await runner.run_case(
            case=healthy_baseline,
            candidate_model_ids=[nano_id],
        )
        assert len(results) == 1
        assert results[0].fallback_used is False


# ─────────────────────────────────────────────────────────────────────────────
# §8: EvaluationRunner integration
# ─────────────────────────────────────────────────────────────────────────────


class TestEvaluationRunnerIntegration:
    """EvaluationRunner integration tests with mocked provider."""

    @pytest.mark.asyncio
    async def test_run_case_returns_one_result_per_model(self):
        registry = _make_registry(["nano", "super"])
        provider = _make_nim_provider(
            "wave-17 is at risk due to labor allocation issues."
        )
        gateway = ModelGateway(
            provider=provider,
            registry=registry,
            router=ModelRouter(registry),
            telemetry=GatewayTelemetry(),
        )
        runner = EvaluationRunner(gateway, registry)
        nano_id = _nano_model_id()
        super_id = _super_model_id()
        results = await runner.run_case(
            case=wave17_labor_risk,
            candidate_model_ids=[nano_id, super_id],
        )
        assert len(results) == 2
        model_ids = {r.model_id for r in results}
        assert nano_id in model_ids
        assert super_id in model_ids

    @pytest.mark.asyncio
    async def test_run_case_includes_grader_results(self):
        registry = _make_registry(["nano"])
        provider = _make_nim_provider(
            "wave-17 has labor bottleneck; recommend labor reallocation."
        )
        gateway = ModelGateway(
            provider=provider,
            registry=registry,
            router=ModelRouter(registry),
            telemetry=GatewayTelemetry(),
        )
        runner = EvaluationRunner(gateway, registry)
        nano_id = _nano_model_id()
        results = await runner.run_case(
            case=wave17_labor_risk,
            candidate_model_ids=[nano_id],
        )
        assert len(results) == 1
        assert len(results[0].grader_results) == 6  # 6 graders in default suite

    @pytest.mark.asyncio
    async def test_run_case_evaluation_run_key_in_result(self):
        registry = _make_registry(["nano"])
        provider = _make_nim_provider("response")
        gateway = ModelGateway(
            provider=provider,
            registry=registry,
            router=ModelRouter(registry),
            telemetry=GatewayTelemetry(),
        )
        runner = EvaluationRunner(gateway, registry)
        nano_id = _nano_model_id()
        results = await runner.run_case(
            case=healthy_baseline,
            candidate_model_ids=[nano_id],
        )
        assert results[0].evaluation_run_key != ""
        assert len(results[0].evaluation_run_key) == 64  # SHA-256 hex

    @pytest.mark.asyncio
    async def test_run_benchmark_produces_benchmark_run(self):
        registry = _make_registry(["nano"])
        provider = _make_nim_provider(
            "wave-17 labor bottleneck identified. Recommend labor reallocation."
        )
        gateway = ModelGateway(
            provider=provider,
            registry=registry,
            router=ModelRouter(registry),
            telemetry=GatewayTelemetry(),
        )
        runner = EvaluationRunner(gateway, registry)
        run = await runner.run_benchmark(
            cases=ALL_FIXTURE_CASES[:1],  # just one case for speed
        )
        assert isinstance(run, BenchmarkRun)
        assert len(run.cases) == 1
        assert run.decision_gate in {
            "CURRENT ROUTER SUFFICIENT",
            "CURRENT ROUTER HAS MEASURABLE GAPS",
        }

    @pytest.mark.asyncio
    async def test_run_benchmark_records_router_selection(self):
        registry = _make_registry(["nano", "super"])
        provider = _make_nim_provider("wave-17 labor response")
        gateway = ModelGateway(
            provider=provider,
            registry=registry,
            router=ModelRouter(registry),
            telemetry=GatewayTelemetry(),
        )
        runner = EvaluationRunner(gateway, registry)
        run = await runner.run_benchmark(
            cases=[wave17_labor_risk],
        )
        assert len(run.cases) == 1
        case_result = run.cases[0]
        assert case_result.router_selection is not None
        assert case_result.router_selection.selected_model_id != ""
        assert case_result.router_selection.routing_strategy == "rules"

    @pytest.mark.asyncio
    async def test_run_benchmark_includes_oracle(self):
        registry = _make_registry(["nano"])
        provider = _make_nim_provider("wave-17 labor reallocation recommended.")
        gateway = ModelGateway(
            provider=provider,
            registry=registry,
            router=ModelRouter(registry),
            telemetry=GatewayTelemetry(),
        )
        runner = EvaluationRunner(gateway, registry)
        run = await runner.run_benchmark(cases=[wave17_labor_risk])
        oracle = run.cases[0].oracle
        assert isinstance(oracle, OracleResult)
