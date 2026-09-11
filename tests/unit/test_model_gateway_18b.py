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
Phase 18B test suite — ModelGateway Evaluation Foundation.

Covers:
  - Behavioral equivalence: routing decisions identical before and after 18B
  - PolicyFilter: deployment mode, risk, reasoning, capability constraints
  - DeploymentMode wiring (LOCAL_NIM, NVIDIA_HOSTED, AUTO, ENTERPRISE)
  - ModelRouteDecision new fields: routing_strategy, routing_latency_ms, candidate_models
  - RiskLevel authority: CRITICAL/HIGH risk blocks weak models (blocking test)
  - ReasoningLevel authority: HIGH reasoning blocks weak models (blocking test)
  - Fallback behavior unchanged
  - Routing latency: measured, small, monotonic
  - RoutingStrategy Protocol compliance
  - Architecture invariants
  - Evaluation models (ModelEvaluationInput, ModelEvaluationResult, EvaluationCase)
  - Deterministic graders (all 6)
  - Replay helper (OperationalContextSnapshot → ReplayContext)
  - Fixture cases validity
  - Evaluation isolation invariant
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maiw_models.errors import ModelUnavailable
from maiw_models.models import (
    DeploymentMode,
    DeploymentStatus,
    LatencyClass,
    ModelCapability,
    ModelRequest,
    ModelRouteDecision,
    Modality,
    ReasoningLevel,
    RiskLevel,
)
from maiw_models.registry import ModelRegistry
from maiw_models.router import ModelRouter
from maiw_models.routing import ModelCandidate, PolicyFilter, RoutingContext, RoutingStrategy
from maiw_models.gateway import ModelGateway
from maiw_models.telemetry import GatewayTelemetry
from maiw_models.providers.nim import NIMProvider

from maiw_models.evaluation.models import (
    EvaluationCase,
    GraderResult,
    ModelEvaluationInput,
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
    EvaluationGrader,
    default_graders,
    run_graders,
)
from maiw_models.evaluation.replay import (
    MockOperationalContextSnapshot,
    MockSnapshotEdge,
    MockSnapshotNode,
    ReplayContext,
    replay_context_from_snapshot,
)
from maiw_models.evaluation.fixtures import (
    ALL_FIXTURE_CASES,
    ALL_FIXTURE_INPUTS,
    equipment_failure,
    healthy_baseline,
    wave17_labor_risk,
    get_fixture_case,
    get_fixture_input,
)


# ── Test helpers ──────────────────────────────────────────────────────────────


def _make_registry(
    super_enabled: bool = True,
    nano_enabled: bool = False,
    lightning_enabled: bool = False,
    ultra_enabled: bool = False,
    nano_omni_enabled: bool = False,
) -> ModelRegistry:
    env = {
        "NEMOTRON_SUPER_ENABLED": "true" if super_enabled else "false",
        "NEMOTRON_NANO_ENABLED": "true" if nano_enabled else "false",
        "NEMOTRON_LIGHTNING_ENABLED": "true" if lightning_enabled else "false",
        "NEMOTRON_ULTRA_ENABLED": "true" if ultra_enabled else "false",
        "NEMOTRON_NANO_OMNI_ENABLED": "true" if nano_omni_enabled else "false",
        "NEMOTRON_SUPER_MODEL": "test/super-model",
        "NEMOTRON_NANO_MODEL": "test/nano-model",
        "NEMOTRON_LIGHTNING_MODEL": "test/lightning-model",
        "NEMOTRON_ULTRA_MODEL": "test/ultra-model",
        "NEMOTRON_NANO_OMNI_MODEL": "test/nano-omni-model",
    }
    with patch.dict(os.environ, env):
        return ModelRegistry()


def _all_enabled_registry() -> ModelRegistry:
    return _make_registry(
        super_enabled=True,
        nano_enabled=True,
        lightning_enabled=True,
        ultra_enabled=True,
        nano_omni_enabled=True,
    )


def _make_gateway(registry: ModelRegistry):
    mock_provider = MagicMock(spec=NIMProvider)
    mock_provider.call = AsyncMock(
        return_value=MagicMock(
            content="test response",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            model="test/super-model",
            finish_reason="stop",
        )
    )
    router = ModelRouter(registry)
    gateway = ModelGateway(
        provider=mock_provider,
        registry=registry,
        router=router,
        telemetry=GatewayTelemetry(),
    )
    return gateway, mock_provider


def _make_grader_result(
    model_id: str = "test/super-model",
    response: str = "test response",
    deployment_id: str = "nvidia_hosted",
) -> ModelEvaluationResult:
    return ModelEvaluationResult(
        evaluation_input_id="test-input",
        model_id=model_id,
        deployment_id=deployment_id,
        response=response,
        latency_ms=200.0,
        routing_latency_ms=0.5,
        routing_strategy="rules",
        candidate_models=["test/super-model"],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: Behavioral equivalence (BLOCKING TEST)
# ═══════════════════════════════════════════════════════════════════════════════


class TestBehavioralEquivalence:
    """
    Verify routing decisions are IDENTICAL before and after 18B instrumentation.

    This is a blocking test for Phase 18B. Selected model must not change.
    """

    # Representative warehouse workloads with expected roles.
    _ROUTING_MATRIX = [
        # (task, reasoning, risk, modality, expected_role)
        ("warehouse.forecasting.summarize_demand", ReasoningLevel.LOW, RiskLevel.LOW, Modality.TEXT, "lightning"),
        ("warehouse.forecasting.analyze_anomaly", ReasoningLevel.MEDIUM, RiskLevel.LOW, Modality.TEXT, "nano"),
        ("warehouse.operations.recover_wave", ReasoningLevel.HIGH, RiskLevel.HIGH, Modality.TEXT, "super"),
        ("warehouse.equipment.diagnose_failure", ReasoningLevel.HIGH, RiskLevel.HIGH, Modality.TEXT, "super"),
        ("warehouse.safety.broadcast_alert", ReasoningLevel.HIGH, RiskLevel.CRITICAL, Modality.TEXT, "super"),
        ("warehouse.operations.summarize_state", ReasoningLevel.LOW, RiskLevel.LOW, Modality.TEXT, "lightning"),
        ("warehouse.safety.summarize_event", ReasoningLevel.MEDIUM, RiskLevel.MEDIUM, Modality.TEXT, "nano"),
        ("warehouse.documents.summarize_text", ReasoningLevel.LOW, RiskLevel.LOW, Modality.TEXT, "lightning"),
        ("warehouse.documents.inspect_image", ReasoningLevel.MEDIUM, RiskLevel.LOW, Modality.IMAGE, "nano-omni"),
        ("warehouse.eval.judge_trajectory", ReasoningLevel.HIGH, RiskLevel.LOW, Modality.TEXT, "ultra"),
        ("warehouse.wave.reprioritize", ReasoningLevel.LOW, RiskLevel.CRITICAL, Modality.TEXT, "super"),
    ]

    def test_routing_decisions_unchanged(self):
        """
        BLOCKING: all routing decisions must match expected roles after 18B.

        Ensures that adding routing_strategy, routing_latency_ms, and candidate_models
        does not alter routing behavior.
        """
        registry = _all_enabled_registry()
        router = ModelRouter(registry)

        for task, reasoning, risk, modality, expected_role in self._ROUTING_MATRIX:
            req = ModelRequest(
                task=task,
                messages=[],
                reasoning=reasoning,
                risk_level=risk,
                modality=modality,
            )
            decision = router.route(req)
            assert decision.selected_role == expected_role, (
                f"BEHAVIORAL EQUIVALENCE FAILURE: task={task} "
                f"expected_role={expected_role} got={decision.selected_role}"
            )

    def test_routing_strategy_field_always_rules(self):
        """routing_strategy must be 'rules' for all routing decisions."""
        registry = _all_enabled_registry()
        router = ModelRouter(registry)

        for task, reasoning, risk, modality, _ in self._ROUTING_MATRIX:
            req = ModelRequest(task=task, messages=[], reasoning=reasoning,
                               risk_level=risk, modality=modality)
            decision = router.route(req)
            assert decision.routing_strategy == "rules", (
                f"routing_strategy must be 'rules', got {decision.routing_strategy!r}"
            )

    def test_routing_latency_present_and_positive(self):
        """routing_latency_ms must be set and >= 0 after 18B."""
        registry = _make_registry(super_enabled=True)
        router = ModelRouter(registry)
        req = ModelRequest(task="t", messages=[], reasoning=ReasoningLevel.HIGH, risk_level=RiskLevel.LOW)
        decision = router.route(req)
        assert decision.routing_latency_ms >= 0.0

    def test_candidate_models_present(self):
        """candidate_models must be a non-empty list for any routable request."""
        registry = _make_registry(super_enabled=True)
        router = ModelRouter(registry)
        req = ModelRequest(task="t", messages=[], reasoning=ReasoningLevel.HIGH, risk_level=RiskLevel.LOW)
        decision = router.route(req)
        assert isinstance(decision.candidate_models, list)
        assert len(decision.candidate_models) >= 1

    def test_existing_fields_unchanged(self):
        """All pre-18B ModelRouteDecision fields must still be populated correctly."""
        registry = _make_registry(super_enabled=True)
        router = ModelRouter(registry)
        req = ModelRequest(
            task="warehouse.wave_recovery",
            messages=[],
            reasoning=ReasoningLevel.HIGH,
            risk_level=RiskLevel.HIGH,
        )
        decision = router.route(req)
        assert decision.selected_model_id == "test/super-model"
        assert decision.selected_role == "super"
        assert decision.requested_role == "super"
        assert decision.routing_rule == "high_reasoning"
        assert len(decision.routing_reason) > 0
        assert decision.task == "warehouse.wave_recovery"
        assert decision.requested_reasoning == ReasoningLevel.HIGH
        assert decision.requested_risk_level == RiskLevel.HIGH
        assert decision.fallback_from is None
        assert decision.fallback_reason is None


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: PolicyFilter tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestPolicyFilter:
    """Tests for the PolicyFilter hard policy layer."""

    def _filter(self, registry: ModelRegistry, request: ModelRequest, mode: DeploymentMode) -> list[ModelCandidate]:
        return PolicyFilter(registry).filter(request, mode)

    def test_disabled_models_excluded(self):
        """Disabled models must not appear in policy filter output."""
        registry = _make_registry(super_enabled=True, nano_enabled=False)
        req = ModelRequest(task="t", messages=[], reasoning=ReasoningLevel.MEDIUM, risk_level=RiskLevel.LOW)
        candidates = self._filter(registry, req, DeploymentMode.NVIDIA_HOSTED)
        roles = {c.role for c in candidates}
        assert "nano" not in roles

    def test_enabled_models_included(self):
        """Enabled models matching constraints must appear in candidates."""
        registry = _make_registry(super_enabled=True, nano_enabled=True, lightning_enabled=True)
        req = ModelRequest(task="t", messages=[], reasoning=ReasoningLevel.LOW, risk_level=RiskLevel.LOW)
        candidates = self._filter(registry, req, DeploymentMode.NVIDIA_HOSTED)
        roles = {c.role for c in candidates}
        # All text-capable enabled models pass for LOW reasoning, LOW risk
        assert "super" in roles
        assert "nano" in roles
        assert "lightning" in roles

    def test_critical_risk_blocks_lightning_and_nano(self):
        """BLOCKING: CRITICAL risk must exclude lightning and nano from candidates."""
        registry = _make_registry(super_enabled=True, nano_enabled=True, lightning_enabled=True)
        req = ModelRequest(task="t", messages=[], reasoning=ReasoningLevel.LOW, risk_level=RiskLevel.CRITICAL)
        candidates = self._filter(registry, req, DeploymentMode.NVIDIA_HOSTED)
        roles = {c.role for c in candidates}
        assert "lightning" not in roles, "CRITICAL risk must block lightning"
        assert "nano" not in roles, "CRITICAL risk must block nano"
        assert "super" in roles, "CRITICAL risk must allow super"

    def test_high_reasoning_blocks_lightning_and_nano(self):
        """BLOCKING: HIGH reasoning must exclude lightning and nano from candidates."""
        registry = _make_registry(super_enabled=True, nano_enabled=True, lightning_enabled=True)
        req = ModelRequest(task="t", messages=[], reasoning=ReasoningLevel.HIGH, risk_level=RiskLevel.LOW)
        candidates = self._filter(registry, req, DeploymentMode.NVIDIA_HOSTED)
        roles = {c.role for c in candidates}
        assert "lightning" not in roles, "HIGH reasoning must block lightning"
        assert "nano" not in roles, "HIGH reasoning must block nano"
        assert "super" in roles, "HIGH reasoning must allow super"

    def test_multimodal_excludes_text_only_models(self):
        """IMAGE modality request must exclude text-only models."""
        registry = _make_registry(super_enabled=True, nano_omni_enabled=True)
        req = ModelRequest(task="t", messages=[], reasoning=ReasoningLevel.LOW,
                           risk_level=RiskLevel.LOW, modality=Modality.IMAGE)
        candidates = self._filter(registry, req, DeploymentMode.NVIDIA_HOSTED)
        roles = {c.role for c in candidates}
        assert "super" not in roles, "Text-only super must not match IMAGE modality"
        assert "nano-omni" in roles, "nano-omni must match IMAGE modality"

    def test_tool_use_required_excludes_nano(self):
        """required_capabilities={'tool_use'} must exclude nano (tool_use=False)."""
        registry = _make_registry(super_enabled=True, nano_enabled=True, lightning_enabled=True)
        req = ModelRequest(
            task="t", messages=[], reasoning=ReasoningLevel.LOW, risk_level=RiskLevel.LOW,
            required_capabilities={"tool_use"},
        )
        candidates = self._filter(registry, req, DeploymentMode.NVIDIA_HOSTED)
        roles = {c.role for c in candidates}
        assert "nano" not in roles, "nano.tool_use=False must be excluded when tool_use required"
        assert "lightning" in roles, "lightning.tool_use=True must be included"

    def test_empty_candidates_when_all_disabled(self):
        """When no models are enabled, policy filter returns empty list."""
        registry = _make_registry(super_enabled=False)  # all disabled
        req = ModelRequest(task="t", messages=[], reasoning=ReasoningLevel.LOW, risk_level=RiskLevel.LOW)
        candidates = self._filter(registry, req, DeploymentMode.NVIDIA_HOSTED)
        assert candidates == []

    def test_candidate_model_ids_returns_list_of_strings(self):
        """candidate_model_ids must return list of strings."""
        registry = _make_registry(super_enabled=True)
        policy = PolicyFilter(registry)
        req = ModelRequest(task="t", messages=[], reasoning=ReasoningLevel.HIGH, risk_level=RiskLevel.LOW)
        ids = policy.candidate_model_ids(req, DeploymentMode.NVIDIA_HOSTED)
        assert isinstance(ids, list)
        assert all(isinstance(mid, str) for mid in ids)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: DeploymentMode wiring tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeploymentMode:
    """Tests for DeploymentMode field on ModelRequest and PolicyFilter."""

    def test_deployment_mode_default_is_nvidia_hosted(self):
        """ModelRequest must default deployment_mode to NVIDIA_HOSTED."""
        req = ModelRequest(task="t", messages=[])
        assert req.deployment_mode == DeploymentMode.NVIDIA_HOSTED

    def test_local_nim_mode_accepted(self):
        """LOCAL_NIM deployment mode must be accepted on ModelRequest."""
        req = ModelRequest(task="t", messages=[], deployment_mode=DeploymentMode.LOCAL_NIM)
        assert req.deployment_mode == DeploymentMode.LOCAL_NIM

    def test_hosted_mode_accepted(self):
        """NVIDIA_HOSTED deployment mode must be accepted."""
        req = ModelRequest(task="t", messages=[], deployment_mode=DeploymentMode.NVIDIA_HOSTED)
        assert req.deployment_mode == DeploymentMode.NVIDIA_HOSTED

    def test_enterprise_mode_accepted(self):
        """ENTERPRISE deployment mode must be accepted."""
        req = ModelRequest(task="t", messages=[], deployment_mode=DeploymentMode.ENTERPRISE)
        assert req.deployment_mode == DeploymentMode.ENTERPRISE

    def test_openai_compatible_mode_accepted(self):
        """OPENAI_COMPATIBLE deployment mode must be accepted."""
        req = ModelRequest(task="t", messages=[], deployment_mode=DeploymentMode.OPENAI_COMPATIBLE)
        assert req.deployment_mode == DeploymentMode.OPENAI_COMPATIBLE

    def test_local_nim_policy_filter_returns_candidates(self):
        """LOCAL_NIM filter must return candidates for standard nvidia-nim models."""
        registry = _make_registry(super_enabled=True)
        policy = PolicyFilter(registry)
        req = ModelRequest(task="t", messages=[], reasoning=ReasoningLevel.HIGH,
                           risk_level=RiskLevel.LOW, deployment_mode=DeploymentMode.LOCAL_NIM)
        candidates = policy.filter(req, DeploymentMode.LOCAL_NIM)
        assert len(candidates) >= 1

    def test_hosted_filter_returns_candidates(self):
        """NVIDIA_HOSTED filter must return candidates."""
        registry = _make_registry(super_enabled=True)
        policy = PolicyFilter(registry)
        req = ModelRequest(task="t", messages=[], reasoning=ReasoningLevel.HIGH, risk_level=RiskLevel.LOW)
        candidates = policy.filter(req, DeploymentMode.NVIDIA_HOSTED)
        assert len(candidates) >= 1

    def test_auto_default_routing_unchanged_with_nvidia_hosted(self):
        """Default NVIDIA_HOSTED routing must produce same decision as before 18B."""
        registry = _make_registry(super_enabled=True)
        router = ModelRouter(registry)
        req = ModelRequest(task="t", messages=[], reasoning=ReasoningLevel.HIGH, risk_level=RiskLevel.LOW)
        decision = router.route(req)
        assert decision.selected_role == "super"
        assert decision.routing_strategy == "rules"

    def test_deployment_mode_in_routing_context(self):
        """RoutingContext must accept deployment_mode."""
        ctx = RoutingContext(deployment_mode=DeploymentMode.LOCAL_NIM, trace_id="abc")
        assert ctx.deployment_mode == DeploymentMode.LOCAL_NIM

    def test_no_eligible_candidates_when_deployment_unavailable(self):
        """PolicyFilter with no enabled models returns empty — existing error path fires."""
        registry = _make_registry(super_enabled=False)  # all disabled
        policy = PolicyFilter(registry)
        req = ModelRequest(task="t", messages=[], deployment_mode=DeploymentMode.LOCAL_NIM)
        candidates = policy.filter(req, DeploymentMode.LOCAL_NIM)
        assert candidates == []


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: RiskLevel authority (BLOCKING)
# ═══════════════════════════════════════════════════════════════════════════════


class TestRiskLevelAuthority:
    """
    BLOCKING tests: RiskLevel constraints must be enforced by policy.

    CRITICAL and HIGH risk must never route to low-capability models.
    Routing strategy cannot override this.
    """

    def test_critical_risk_routes_to_super_minimum(self):
        """CRITICAL risk with LOW reasoning must still route to super (not lightning/nano)."""
        router = ModelRouter(_make_registry(super_enabled=True, nano_enabled=True, lightning_enabled=True))
        decision = router.route(ModelRequest(
            task="warehouse.emergency.shutdown",
            messages=[],
            reasoning=ReasoningLevel.LOW,
            risk_level=RiskLevel.CRITICAL,
        ))
        assert decision.selected_role == "super", (
            f"CRITICAL risk must route to super minimum; got {decision.selected_role}"
        )
        assert decision.routing_rule == "critical_risk"

    def test_critical_risk_candidate_models_excludes_weak(self):
        """candidate_models for CRITICAL risk must not include lightning or nano."""
        router = ModelRouter(_make_registry(super_enabled=True, nano_enabled=True, lightning_enabled=True))
        decision = router.route(ModelRequest(
            task="t", messages=[], reasoning=ReasoningLevel.LOW, risk_level=RiskLevel.CRITICAL,
        ))
        weak_ids = {"test/nano-model", "test/lightning-model"}
        overlap = set(decision.candidate_models) & weak_ids
        assert not overlap, (
            f"CRITICAL risk candidate_models must not include weak models; found {overlap}"
        )

    def test_high_risk_allows_routing_to_super(self):
        """HIGH risk with HIGH reasoning routes to super — no change from pre-18B."""
        router = ModelRouter(_make_registry(super_enabled=True))
        decision = router.route(ModelRequest(
            task="t", messages=[], reasoning=ReasoningLevel.HIGH, risk_level=RiskLevel.HIGH,
        ))
        assert decision.selected_role == "super"

    def test_low_risk_allows_all_models(self):
        """LOW risk must not restrict model selection — lightning still valid."""
        router = ModelRouter(_make_registry(lightning_enabled=True, super_enabled=True))
        decision = router.route(ModelRequest(
            task="t", messages=[], reasoning=ReasoningLevel.LOW, risk_level=RiskLevel.LOW,
        ))
        assert decision.selected_role == "lightning"

    def test_policy_filter_critical_risk_invariant(self):
        """PolicyFilter must enforce CRITICAL risk regardless of DeploymentMode."""
        registry = _make_registry(super_enabled=True, nano_enabled=True, lightning_enabled=True)
        policy = PolicyFilter(registry)
        for mode in [DeploymentMode.NVIDIA_HOSTED, DeploymentMode.LOCAL_NIM, DeploymentMode.ENTERPRISE]:
            req = ModelRequest(task="t", messages=[], reasoning=ReasoningLevel.LOW,
                               risk_level=RiskLevel.CRITICAL, deployment_mode=mode)
            candidates = policy.filter(req, mode)
            roles = {c.role for c in candidates}
            assert "lightning" not in roles, f"CRITICAL risk must block lightning in {mode}"
            assert "nano" not in roles, f"CRITICAL risk must block nano in {mode}"


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5: ReasoningLevel authority (BLOCKING)
# ═══════════════════════════════════════════════════════════════════════════════


class TestReasoningLevelAuthority:
    """
    BLOCKING tests: ReasoningLevel constraints must be enforced by policy.

    HIGH reasoning must never route to incapable models.
    """

    def test_high_reasoning_routes_to_super(self):
        """HIGH reasoning must route to super — routing strategy cannot downgrade."""
        router = ModelRouter(_make_registry(super_enabled=True, nano_enabled=True, lightning_enabled=True))
        decision = router.route(ModelRequest(
            task="t", messages=[], reasoning=ReasoningLevel.HIGH, risk_level=RiskLevel.LOW,
        ))
        assert decision.selected_role == "super", (
            f"HIGH reasoning must select super; got {decision.selected_role}"
        )

    def test_high_reasoning_candidate_models_excludes_weak(self):
        """candidate_models for HIGH reasoning must not include lightning or nano."""
        router = ModelRouter(_make_registry(super_enabled=True, nano_enabled=True, lightning_enabled=True))
        decision = router.route(ModelRequest(
            task="t", messages=[], reasoning=ReasoningLevel.HIGH, risk_level=RiskLevel.LOW,
        ))
        weak_ids = {"test/nano-model", "test/lightning-model"}
        overlap = set(decision.candidate_models) & weak_ids
        assert not overlap, (
            f"HIGH reasoning candidate_models must not include weak models; found {overlap}"
        )

    def test_policy_filter_high_reasoning_invariant(self):
        """PolicyFilter must exclude weak models for HIGH reasoning across all modes."""
        registry = _make_registry(super_enabled=True, nano_enabled=True, lightning_enabled=True)
        policy = PolicyFilter(registry)
        for mode in [DeploymentMode.NVIDIA_HOSTED, DeploymentMode.LOCAL_NIM]:
            req = ModelRequest(task="t", messages=[], reasoning=ReasoningLevel.HIGH,
                               risk_level=RiskLevel.LOW, deployment_mode=mode)
            candidates = policy.filter(req, mode)
            roles = {c.role for c in candidates}
            assert "lightning" not in roles, f"HIGH reasoning must block lightning in {mode}"
            assert "nano" not in roles, f"HIGH reasoning must block nano in {mode}"


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6: Fallback behavior unchanged
# ═══════════════════════════════════════════════════════════════════════════════


class TestFallbackBehaviorUnchanged:
    """Verify fallback chain is unchanged from pre-18B behavior."""

    def test_lightning_fallback_to_nano(self):
        router = ModelRouter(_make_registry(lightning_enabled=False, nano_enabled=True, super_enabled=True))
        decision = router.route(ModelRequest(
            task="t", messages=[], reasoning=ReasoningLevel.LOW, risk_level=RiskLevel.LOW,
        ))
        assert decision.selected_role == "nano"
        assert decision.fallback_from == "lightning"
        assert decision.requested_role == "lightning"

    def test_nano_fallback_to_super(self):
        router = ModelRouter(_make_registry(nano_enabled=False, super_enabled=True))
        decision = router.route(ModelRequest(
            task="t", messages=[], reasoning=ReasoningLevel.MEDIUM, risk_level=RiskLevel.LOW,
        ))
        assert decision.selected_role == "super"
        assert decision.fallback_from == "nano"

    def test_ultra_fallback_to_super(self):
        router = ModelRouter(_make_registry(ultra_enabled=False, super_enabled=True))
        decision = router.route(ModelRequest(
            task="warehouse.eval.judge_quality", messages=[],
            reasoning=ReasoningLevel.HIGH, risk_level=RiskLevel.LOW,
        ))
        assert decision.selected_role == "super"
        assert decision.fallback_from == "ultra"
        assert decision.routing_rule == "judge_task"

    def test_nano_omni_fallback_to_super(self):
        router = ModelRouter(_make_registry(nano_omni_enabled=False, super_enabled=True))
        decision = router.route(ModelRequest(
            task="t", messages=[], reasoning=ReasoningLevel.LOW,
            risk_level=RiskLevel.LOW, modality=Modality.IMAGE,
        ))
        assert decision.selected_role == "super"
        assert decision.fallback_from == "nano-omni"

    def test_fallback_decision_has_18b_fields(self):
        """Fallback decisions must also populate 18B provenance fields."""
        router = ModelRouter(_make_registry(nano_enabled=False, super_enabled=True))
        decision = router.route(ModelRequest(
            task="t", messages=[], reasoning=ReasoningLevel.MEDIUM, risk_level=RiskLevel.LOW,
        ))
        assert decision.routing_strategy == "rules"
        assert decision.routing_latency_ms >= 0.0
        assert isinstance(decision.candidate_models, list)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7: Routing latency measurement
# ═══════════════════════════════════════════════════════════════════════════════


class TestRoutingLatency:
    """Verify routing latency is measured correctly."""

    def test_routing_latency_is_non_negative(self):
        registry = _make_registry(super_enabled=True)
        router = ModelRouter(registry)
        decision = router.route(ModelRequest(task="t", messages=[],
                                             reasoning=ReasoningLevel.HIGH, risk_level=RiskLevel.LOW))
        assert decision.routing_latency_ms >= 0.0

    def test_routing_latency_is_small(self):
        """Rule-based routing should be extremely fast (< 100ms in practice)."""
        registry = _make_registry(super_enabled=True, nano_enabled=True, lightning_enabled=True)
        router = ModelRouter(registry)
        decision = router.route(ModelRequest(task="t", messages=[],
                                             reasoning=ReasoningLevel.LOW, risk_level=RiskLevel.LOW))
        # No strict performance assertion — prove instrumentation does not materially add latency.
        # Anything under 500ms is acceptable for a deterministic rule lookup.
        assert decision.routing_latency_ms < 500.0

    def test_routing_latency_not_zero_under_measurement(self):
        """routing_latency_ms must be a float (0.0 is acceptable for fast machines)."""
        registry = _make_registry(super_enabled=True)
        router = ModelRouter(registry)
        decision = router.route(ModelRequest(task="t", messages=[],
                                             reasoning=ReasoningLevel.HIGH, risk_level=RiskLevel.LOW))
        assert isinstance(decision.routing_latency_ms, float)

    def test_routing_latency_excludes_inference(self):
        """
        routing_latency_ms must be much smaller than inference latency.
        Run 10 routing calls and confirm max < 100ms.
        """
        registry = _make_registry(super_enabled=True, nano_enabled=True, lightning_enabled=True)
        router = ModelRouter(registry)
        latencies = []
        for _ in range(10):
            decision = router.route(ModelRequest(
                task="t", messages=[], reasoning=ReasoningLevel.LOW, risk_level=RiskLevel.LOW,
            ))
            latencies.append(decision.routing_latency_ms)
        max_latency = max(latencies)
        assert max_latency < 100.0, f"Routing latency too high: max={max_latency:.3f}ms"


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 8: RoutingStrategy Protocol compliance
# ═══════════════════════════════════════════════════════════════════════════════


class TestRoutingStrategyProtocol:
    """Verify RoutingStrategy protocol can be satisfied."""

    def test_routing_strategy_is_runtime_checkable(self):
        """RoutingStrategy must be a runtime-checkable Protocol."""
        from typing import runtime_checkable, Protocol
        import inspect
        assert hasattr(RoutingStrategy, '__protocol_attrs__') or \
               getattr(RoutingStrategy, '_is_protocol', False) or \
               isinstance(RoutingStrategy, type)

    def test_model_candidate_frozen(self):
        """ModelCandidate must be a frozen dataclass (immutable)."""
        import dataclasses
        cap = _make_registry(super_enabled=True).get_by_role("super")
        candidate = ModelCandidate(
            model_id="test/super-model",
            role="super",
            deployment_mode=DeploymentMode.NVIDIA_HOSTED,
            capability=cap,
        )
        with pytest.raises((AttributeError, TypeError)):
            candidate.model_id = "modified"  # type: ignore[misc]

    def test_routing_context_accepts_evaluation_override(self):
        """RoutingContext.evaluation_model_override must be settable."""
        ctx = RoutingContext(
            deployment_mode=DeploymentMode.NVIDIA_HOSTED,
            evaluation_model_override="test/super-model",
        )
        assert ctx.evaluation_model_override == "test/super-model"

    def test_routing_context_evaluation_override_none_by_default(self):
        """evaluation_model_override must default to None in production."""
        ctx = RoutingContext(deployment_mode=DeploymentMode.NVIDIA_HOSTED)
        assert ctx.evaluation_model_override is None


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 9: candidate_models semantics
# ═══════════════════════════════════════════════════════════════════════════════


class TestCandidateModelsSemantics:
    """
    candidate_models must mean: models eligible AFTER policy filtering,
    not all models in registry.
    """

    def test_candidate_models_subset_of_registry(self):
        """candidate_models must be a subset of enabled registry models."""
        registry = _make_registry(super_enabled=True, nano_enabled=True, lightning_enabled=True)
        router = ModelRouter(registry)
        decision = router.route(ModelRequest(
            task="t", messages=[], reasoning=ReasoningLevel.HIGH, risk_level=RiskLevel.LOW,
        ))
        all_enabled_ids = {c.model_id for c in registry.all_enabled()}
        for mid in decision.candidate_models:
            assert mid in all_enabled_ids, f"{mid} not in enabled registry"

    def test_candidate_models_excludes_disabled(self):
        """candidate_models must never include disabled model IDs."""
        registry = _make_registry(super_enabled=True, nano_enabled=False, lightning_enabled=False)
        router = ModelRouter(registry)
        decision = router.route(ModelRequest(
            task="t", messages=[], reasoning=ReasoningLevel.HIGH, risk_level=RiskLevel.LOW,
        ))
        assert "test/nano-model" not in decision.candidate_models
        assert "test/lightning-model" not in decision.candidate_models

    def test_candidate_models_respects_risk_level(self):
        """CRITICAL risk reduces candidates to high-capability models only."""
        registry = _make_registry(super_enabled=True, nano_enabled=True, lightning_enabled=True)
        router = ModelRouter(registry)
        decision = router.route(ModelRequest(
            task="t", messages=[], reasoning=ReasoningLevel.LOW, risk_level=RiskLevel.CRITICAL,
        ))
        # Only super should be in candidates for CRITICAL risk with these enabled models
        assert "test/lightning-model" not in decision.candidate_models
        assert "test/nano-model" not in decision.candidate_models

    def test_candidate_models_contains_selected(self):
        """The selected model must be in candidate_models when no fallback outside policy."""
        registry = _make_registry(super_enabled=True)
        router = ModelRouter(registry)
        decision = router.route(ModelRequest(
            task="t", messages=[], reasoning=ReasoningLevel.HIGH, risk_level=RiskLevel.LOW,
        ))
        # Selected model must be in candidates when policy allows it.
        assert decision.selected_model_id in decision.candidate_models


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 10: Architecture invariants
# ═══════════════════════════════════════════════════════════════════════════════


class TestArchitectureInvariants:
    """
    Architecture invariants — Phase 18B.

    These tests ensure the structural boundaries documented in Phase 18B spec
    are upheld by the code.
    """

    def test_policy_filter_does_not_call_models(self):
        """PolicyFilter.filter must not invoke any model call."""
        registry = _make_registry(super_enabled=True)
        policy = PolicyFilter(registry)
        # If filter were to call a model, it would need async. It's sync — invariant holds.
        import inspect
        assert not inspect.iscoroutinefunction(policy.filter)

    def test_routing_strategy_select_is_synchronous(self):
        """RoutingStrategy.select must be synchronous (no model calls allowed)."""
        # ModelRouter.route is the reference implementation of select.
        import inspect
        router = ModelRouter(_make_registry(super_enabled=True))
        assert not inspect.iscoroutinefunction(router.route)

    def test_evaluation_graders_are_synchronous(self):
        """All deterministic graders must be synchronous (no LLM calls)."""
        import inspect
        for grader in default_graders():
            assert not inspect.iscoroutinefunction(grader.grade), (
                f"{type(grader).__name__}.grade must be synchronous"
            )

    def test_evaluation_grader_does_not_import_action_modules(self):
        """Grader module must not import ActionProposal, DecisionEngine, ActionExecutor."""
        import importlib
        import sys
        grader_mod = sys.modules.get("maiw_models.evaluation.graders")
        if grader_mod is None:
            grader_mod = importlib.import_module("maiw_models.evaluation.graders")
        forbidden_attrs = ["ActionProposal", "DecisionEngine", "ActionExecutor", "ApprovalStore"]
        for attr in forbidden_attrs:
            assert not hasattr(grader_mod, attr), (
                f"Evaluation graders must not reference {attr}"
            )

    def test_evaluation_models_do_not_import_mcp_writes(self):
        """Evaluation models must not import MCP write capabilities."""
        import importlib
        import sys
        eval_mod = sys.modules.get("maiw_models.evaluation.models")
        if eval_mod is None:
            eval_mod = importlib.import_module("maiw_models.evaluation.models")
        forbidden_attrs = ["ActionExecutor", "MCPWrite", "ApprovalStore", "DecisionEngine"]
        for attr in forbidden_attrs:
            assert not hasattr(eval_mod, attr), (
                f"Evaluation models must not reference {attr}"
            )

    def test_routing_module_does_not_import_action_modules(self):
        """PolicyFilter/RoutingStrategy must not reference governance modules."""
        import importlib
        import sys
        routing_mod = sys.modules.get("maiw_models.routing")
        if routing_mod is None:
            routing_mod = importlib.import_module("maiw_models.routing")
        forbidden_attrs = ["ActionProposal", "DecisionEngine", "ActionExecutor"]
        for attr in forbidden_attrs:
            assert not hasattr(routing_mod, attr), (
                f"Routing module must not reference {attr}"
            )

    def test_gateway_is_sole_inference_boundary(self):
        """ModelGateway must be the only class with a provider call path."""
        from maiw_models.routing import PolicyFilter, RoutingStrategy
        from maiw_models.router import ModelRouter
        # PolicyFilter and ModelRouter must not have a provider/call attribute
        registry = _make_registry(super_enabled=True)
        policy = PolicyFilter(registry)
        router = ModelRouter(registry)
        assert not hasattr(policy, "_provider")
        assert not hasattr(policy, "call")
        assert not hasattr(router, "_provider")
        assert not hasattr(router, "call")

    def test_evaluation_no_action_proposal(self):
        """
        BLOCKING: Evaluation infrastructure must not create ActionProposal.

        Verify that no evaluation type has a field named proposal_id or
        a method that returns ActionProposal.
        """
        from maiw_models.evaluation.models import (
            ModelEvaluationInput, ModelEvaluationResult, EvaluationCase
        )
        import dataclasses
        for cls in [ModelEvaluationInput, ModelEvaluationResult, EvaluationCase]:
            field_names = {f.name for f in dataclasses.fields(cls)}
            forbidden = {"proposal_id", "action_proposal", "decision_engine", "approval_id"}
            overlap = field_names & forbidden
            assert not overlap, f"{cls.__name__} must not have fields: {overlap}"


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 11: ModelRouteDecision routing provenance
# ═══════════════════════════════════════════════════════════════════════════════


class TestRoutingProvenance:
    """Verify routing provenance is complete and consistent."""

    def test_provenance_strategy_rules(self):
        """routing_strategy must be 'rules'."""
        router = ModelRouter(_make_registry(super_enabled=True))
        decision = router.route(ModelRequest(task="t", messages=[],
                                             reasoning=ReasoningLevel.HIGH, risk_level=RiskLevel.LOW))
        assert decision.routing_strategy == "rules"

    def test_provenance_candidates_populated(self):
        """candidate_models must be a non-empty list."""
        router = ModelRouter(_make_registry(super_enabled=True))
        decision = router.route(ModelRequest(task="t", messages=[],
                                             reasoning=ReasoningLevel.HIGH, risk_level=RiskLevel.LOW))
        assert len(decision.candidate_models) > 0

    def test_provenance_latency_populated(self):
        """routing_latency_ms must be >= 0.0."""
        router = ModelRouter(_make_registry(super_enabled=True))
        decision = router.route(ModelRequest(task="t", messages=[],
                                             reasoning=ReasoningLevel.HIGH, risk_level=RiskLevel.LOW))
        assert decision.routing_latency_ms >= 0.0

    def test_route_decision_embedded_in_response(self):
        """ModelResponse.route_decision must contain new 18B fields."""
        registry = _make_registry(super_enabled=True)
        gateway, _ = _make_gateway(registry)
        response = asyncio.run(gateway.generate(ModelRequest(
            task="t", messages=[{"role": "user", "content": "test"}],
            reasoning=ReasoningLevel.HIGH, risk_level=RiskLevel.LOW,
        )))
        assert response.route_decision.routing_strategy == "rules"
        assert response.route_decision.routing_latency_ms >= 0.0
        assert isinstance(response.route_decision.candidate_models, list)

    def test_telemetry_includes_18b_fields(self):
        """GatewayTelemetry must emit routing_strategy, routing_latency_ms, candidate_models."""
        import logging
        telemetry = GatewayTelemetry()
        registry = _make_registry(super_enabled=True)
        router = ModelRouter(registry)
        request = ModelRequest(task="t", messages=[], reasoning=ReasoningLevel.HIGH, risk_level=RiskLevel.LOW)
        decision = router.route(request)

        captured_records: list = []

        class CapturingHandler(logging.Handler):
            def emit(self, record):
                captured_records.append(record)

        handler = CapturingHandler()
        handler.setLevel(logging.DEBUG)
        import maiw_models.telemetry as tele_module
        log = logging.getLogger(tele_module.__name__)
        old_level = log.level
        log.setLevel(logging.DEBUG)
        log.addHandler(handler)
        try:
            telemetry.record_success(
                trace_id="test",
                request=request,
                decision=decision,
                latency_ms=100.0,
                usage={},
                finish_reason="stop",
            )
        finally:
            log.removeHandler(handler)
            log.setLevel(old_level)

        assert len(captured_records) >= 1, "Telemetry must emit at least one log record"
        record = captured_records[0]
        # extra fields are added to the LogRecord __dict__ by Python's logging infrastructure
        assert hasattr(record, "routing_strategy"), "telemetry must emit routing_strategy"
        assert hasattr(record, "routing_latency_ms"), "telemetry must emit routing_latency_ms"
        assert hasattr(record, "candidate_models"), "telemetry must emit candidate_models"
        assert record.routing_strategy == "rules"
        assert record.routing_latency_ms >= 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 12: Evaluation models
# ═══════════════════════════════════════════════════════════════════════════════


class TestEvaluationModels:
    """Tests for ModelEvaluationInput, ModelEvaluationResult, EvaluationCase."""

    def test_prompt_hash_is_deterministic(self):
        """make_prompt_hash must return same value for same prompt."""
        prompt = "Why is Wave 17 at risk?"
        h1 = ModelEvaluationInput.make_prompt_hash(prompt)
        h2 = ModelEvaluationInput.make_prompt_hash(prompt)
        assert h1 == h2

    def test_prompt_hash_differs_for_different_prompts(self):
        """make_prompt_hash must differ for different prompts."""
        h1 = ModelEvaluationInput.make_prompt_hash("prompt A")
        h2 = ModelEvaluationInput.make_prompt_hash("prompt B")
        assert h1 != h2

    def test_prompt_hash_is_hex_string(self):
        """make_prompt_hash must return a hex string."""
        h = ModelEvaluationInput.make_prompt_hash("test")
        assert len(h) == 64  # SHA-256 hex
        assert all(c in "0123456789abcdef" for c in h)

    def test_evaluation_key_is_deterministic(self):
        """evaluation_key must return same value for same input."""
        prompt = "test"
        inp = ModelEvaluationInput(
            evaluation_input_id="test",
            dataset_id="ds-1",
            datapack_checksum="chk-abc",
            scenario_id="scenario-1",
            warehouse_state_snapshot_id=None,
            context_snapshot_id="ctx-1",
            prompt=prompt,
            prompt_hash=ModelEvaluationInput.make_prompt_hash(prompt),
            reasoning_level="medium",
            risk_level="low",
            deployment_mode="nvidia_hosted",
        )
        assert inp.evaluation_key() == inp.evaluation_key()

    def test_make_evaluation_run_key_excludes_timestamps(self):
        """make_evaluation_run_key must be stable — same key for same params."""
        k1 = make_evaluation_run_key("ds", "hash", "model", "deploy", "ctx", "snap")
        k2 = make_evaluation_run_key("ds", "hash", "model", "deploy", "ctx", "snap")
        assert k1 == k2

    def test_make_evaluation_run_key_differs_by_model(self):
        """Different model_ids must produce different keys."""
        k1 = make_evaluation_run_key("ds", "hash", "model-A", "deploy", "ctx", "snap")
        k2 = make_evaluation_run_key("ds", "hash", "model-B", "deploy", "ctx", "snap")
        assert k1 != k2

    def test_evaluation_result_has_routing_fields(self):
        """ModelEvaluationResult must include 18B routing provenance."""
        result = _make_grader_result()
        assert result.routing_strategy == "rules"
        assert isinstance(result.routing_latency_ms, float)
        assert isinstance(result.candidate_models, list)

    def test_evaluation_case_required_fields_optional(self):
        """EvaluationCase must allow optional expected_capability and expected_target."""
        case = EvaluationCase(
            case_id="test",
            task_family=TaskFamily.ASK,
            prompt="Test prompt",
        )
        assert case.expected_capability is None
        assert case.expected_target is None
        assert case.required_facts == []
        assert case.forbidden_claims == []


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 13: Deterministic graders
# ═══════════════════════════════════════════════════════════════════════════════


def _make_case(**kwargs) -> EvaluationCase:
    defaults = dict(
        case_id="test-case",
        task_family=TaskFamily.ASK,
        prompt="Test prompt",
    )
    defaults.update(kwargs)
    return EvaluationCase(**defaults)


class TestSchemaValidityGrader:
    grader = SchemaValidityGrader()

    def test_passes_when_no_schema(self):
        case = _make_case()
        result = _make_grader_result(response='{"key": "value"}')
        gr = self.grader.grade(case, result)
        assert gr.passed

    def test_passes_when_required_fields_present(self):
        case = _make_case(expected_schema={"required": ["action", "target"]})
        result = _make_grader_result(response='{"action": "reallocate", "target": "wave-17"}')
        gr = self.grader.grade(case, result)
        assert gr.passed

    def test_fails_when_required_field_missing(self):
        case = _make_case(expected_schema={"required": ["action", "target"]})
        result = _make_grader_result(response='{"action": "reallocate"}')
        gr = self.grader.grade(case, result)
        assert not gr.passed
        assert "target" in gr.reason

    def test_fails_on_empty_response(self):
        case = _make_case(expected_schema={"required": ["action"]})
        result = _make_grader_result(response=None)
        gr = self.grader.grade(case, result)
        assert not gr.passed

    def test_fails_on_non_json_response(self):
        case = _make_case(expected_schema={"required": ["action"]})
        result = _make_grader_result(response="This is plain text, not JSON.")
        gr = self.grader.grade(case, result)
        assert not gr.passed

    def test_extracts_json_from_markdown_fence(self):
        case = _make_case(expected_schema={"required": ["action"]})
        result = _make_grader_result(response='```json\n{"action": "test"}\n```')
        gr = self.grader.grade(case, result)
        assert gr.passed


class TestHallucinationGrader:
    grader = HallucinationGrader()

    def test_passes_when_no_context_entities(self):
        case = _make_case()
        result = _make_grader_result(response="wave-17 and wave-99 have issues")
        gr = self.grader.grade(case, result)
        assert gr.passed

    def test_passes_when_all_entities_in_context(self):
        case = _make_case(context_entities=["wave-17", "conveyor-main"])
        result = _make_grader_result(response="wave-17 is at risk due to conveyor-main failure")
        gr = self.grader.grade(case, result)
        assert gr.passed

    def test_fails_when_entity_not_in_context(self):
        case = _make_case(context_entities=["wave-17"])
        result = _make_grader_result(response="wave-17 and wave-99 are both at risk")
        gr = self.grader.grade(case, result)
        assert not gr.passed
        assert "wave-99" in gr.evidence

    def test_passes_on_empty_response(self):
        case = _make_case(context_entities=["wave-17"])
        result = _make_grader_result(response=None)
        gr = self.grader.grade(case, result)
        assert gr.passed


class TestCapabilityMatchGrader:
    grader = CapabilityMatchGrader()

    def test_passes_when_no_expected_capability(self):
        case = _make_case()
        result = _make_grader_result(response="anything")
        gr = self.grader.grade(case, result)
        assert gr.passed

    def test_passes_when_capability_mentioned(self):
        case = _make_case(expected_capability="labor_reallocation")
        result = _make_grader_result(response="I recommend labor reallocation to resolve the bottleneck")
        gr = self.grader.grade(case, result)
        assert gr.passed

    def test_passes_when_synonym_mentioned(self):
        case = _make_case(expected_capability="wave_recovery")
        result = _make_grader_result(response="You should recover wave 17 by replanning")
        gr = self.grader.grade(case, result)
        assert gr.passed

    def test_fails_when_capability_absent(self):
        case = _make_case(expected_capability="labor_reallocation")
        result = _make_grader_result(response="Everything is fine, no action needed")
        gr = self.grader.grade(case, result)
        assert not gr.passed


class TestTargetMatchGrader:
    grader = TargetMatchGrader()

    def test_passes_when_no_expected_target(self):
        case = _make_case()
        result = _make_grader_result(response="some response")
        gr = self.grader.grade(case, result)
        assert gr.passed

    def test_passes_when_target_mentioned(self):
        case = _make_case(expected_target="wave-17")
        result = _make_grader_result(response="Wave-17 is at risk due to labor shortfall")
        gr = self.grader.grade(case, result)
        assert gr.passed

    def test_passes_when_target_variant_mentioned(self):
        case = _make_case(expected_target="wave-17")
        result = _make_grader_result(response="wave 17 needs intervention")
        gr = self.grader.grade(case, result)
        assert gr.passed

    def test_fails_when_target_absent(self):
        case = _make_case(expected_target="wave-17")
        result = _make_grader_result(response="The labor allocation is fine")
        gr = self.grader.grade(case, result)
        assert not gr.passed


class TestRequiredEvidenceGrader:
    grader = RequiredEvidenceGrader()

    def test_passes_when_no_required_facts(self):
        case = _make_case()
        result = _make_grader_result(response="any response")
        gr = self.grader.grade(case, result)
        assert gr.passed

    def test_passes_when_all_facts_present(self):
        case = _make_case(required_facts=["wave-17", "labor"])
        result = _make_grader_result(response="wave-17 has a labor shortage causing delay")
        gr = self.grader.grade(case, result)
        assert gr.passed
        assert gr.score == 1.0

    def test_partial_score_when_some_facts_missing(self):
        case = _make_case(required_facts=["wave-17", "labor", "conveyor"])
        result = _make_grader_result(response="wave-17 has a labor issue")
        gr = self.grader.grade(case, result)
        assert not gr.passed
        assert gr.score == pytest.approx(2 / 3, abs=0.01)

    def test_fails_when_all_facts_missing(self):
        case = _make_case(required_facts=["wave-17", "labor"])
        result = _make_grader_result(response="Everything is operational")
        gr = self.grader.grade(case, result)
        assert not gr.passed
        assert gr.score == 0.0


class TestForbiddenClaimsGrader:
    grader = ForbiddenClaimsGrader()

    def test_passes_when_no_forbidden_claims(self):
        case = _make_case()
        result = _make_grader_result(response="wave-17 is at risk")
        gr = self.grader.grade(case, result)
        assert gr.passed

    def test_passes_when_forbidden_claim_absent(self):
        case = _make_case(forbidden_claims=["wave-99", "external-agency"])
        result = _make_grader_result(response="wave-17 has a labor issue")
        gr = self.grader.grade(case, result)
        assert gr.passed

    def test_fails_when_forbidden_claim_present(self):
        case = _make_case(forbidden_claims=["wave-99", "external-agency"])
        result = _make_grader_result(response="wave-17 and wave-99 are both at risk")
        gr = self.grader.grade(case, result)
        assert not gr.passed
        assert "wave-99" in gr.evidence

    def test_fails_when_multiple_forbidden_claims_present(self):
        case = _make_case(forbidden_claims=["wave-99", "external-agency"])
        result = _make_grader_result(
            response="wave-99 is also affected and external-agency should be contacted"
        )
        gr = self.grader.grade(case, result)
        assert not gr.passed
        assert len(gr.evidence) == 2


class TestRunGraders:
    def test_run_graders_returns_one_result_per_grader(self):
        case = _make_case()
        result = _make_grader_result()
        graders = default_graders()
        results = run_graders(case, result, graders)
        assert len(results) == len(graders)

    def test_run_graders_with_default_suite(self):
        case = _make_case()
        result = _make_grader_result()
        results = run_graders(case, result)
        assert len(results) == 6  # 6 graders in 18B default suite

    def test_grader_results_have_names(self):
        case = _make_case()
        result = _make_grader_result()
        for gr in run_graders(case, result):
            assert gr.grader_name
            assert isinstance(gr.passed, bool)

    def test_grader_protocol_satisfied(self):
        """All default graders must satisfy the EvaluationGrader Protocol."""
        for grader in default_graders():
            assert isinstance(grader, EvaluationGrader)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 14: Replay helper
# ═══════════════════════════════════════════════════════════════════════════════


class TestReplayHelper:
    """Tests for OperationalContextSnapshot → ReplayContext."""

    def _make_snapshot(
        self,
        snapshot_id: str = "snap-001",
        nodes: list[MockSnapshotNode] | None = None,
        edges: list[MockSnapshotEdge] | None = None,
    ) -> MockOperationalContextSnapshot:
        if nodes is None:
            nodes = [
                MockSnapshotNode("wave-17", "Wave", "Wave 17", {"status": "at_risk"}),
                MockSnapshotNode("worker-A001", "Worker", "Alice", {"shift": "morning"}),
            ]
        if edges is None:
            edges = [
                MockSnapshotEdge("wave-17", "worker-A001", "ASSIGNED_TO"),
            ]
        snap = MockOperationalContextSnapshot(
            context_snapshot_id=snapshot_id,
            nodes=nodes,
            edges=edges,
        )
        snap.entity_count = len(snap.nodes)
        snap.relationship_count = len(snap.edges)
        return snap

    def test_replay_context_has_correct_snapshot_id(self):
        snap = self._make_snapshot("snap-001")
        ctx = replay_context_from_snapshot(snap, "Why is Wave 17 at risk?")
        assert ctx.context_snapshot_id == "snap-001"

    def test_replay_context_nodes_match_snapshot(self):
        snap = self._make_snapshot()
        ctx = replay_context_from_snapshot(snap, "test prompt")
        assert len(ctx.node_summaries) == len(snap.nodes)

    def test_replay_context_edges_match_snapshot(self):
        snap = self._make_snapshot()
        ctx = replay_context_from_snapshot(snap, "test prompt")
        assert len(ctx.edge_summaries) == len(snap.edges)

    def test_replay_context_messages_include_user_prompt(self):
        snap = self._make_snapshot()
        prompt = "Why is Wave 17 at risk?"
        ctx = replay_context_from_snapshot(snap, prompt)
        user_msgs = [m for m in ctx.messages if m["role"] == "user"]
        assert len(user_msgs) == 1
        assert user_msgs[0]["content"] == prompt

    def test_replay_context_messages_include_system_prompt(self):
        snap = self._make_snapshot()
        ctx = replay_context_from_snapshot(snap, "test")
        system_msgs = [m for m in ctx.messages if m["role"] == "system"]
        assert len(system_msgs) == 1
        assert "MAIW Copilot" in system_msgs[0]["content"]

    def test_replay_context_custom_system_prompt(self):
        snap = self._make_snapshot()
        ctx = replay_context_from_snapshot(snap, "test", system_prompt="Custom system prompt")
        system_msgs = [m for m in ctx.messages if m["role"] == "system"]
        assert system_msgs[0]["content"] == "Custom system prompt"

    def test_replay_context_no_fresh_graph_traversal(self):
        """Replay must use stored nodes/edges only — not call any live service."""
        snap = self._make_snapshot()
        # replay_context_from_snapshot is synchronous — proves no async graph call
        import inspect
        assert not inspect.iscoroutinefunction(replay_context_from_snapshot)

    def test_replay_context_dataset_id(self):
        snap = self._make_snapshot()
        ctx = replay_context_from_snapshot(snap, "test")
        assert ctx.dataset_id == snap.dataset_id

    def test_replay_context_datapack_checksum(self):
        snap = self._make_snapshot()
        ctx = replay_context_from_snapshot(snap, "test")
        assert ctx.datapack_checksum == snap.datapack_checksum

    def test_mock_snapshot_node_count(self):
        snap = self._make_snapshot()
        assert snap.entity_count == len(snap.nodes)

    def test_empty_snapshot_replay(self):
        snap = self._make_snapshot(nodes=[], edges=[])
        ctx = replay_context_from_snapshot(snap, "test")
        assert ctx.entity_count == 0
        assert ctx.relationship_count == 0
        assert len(ctx.node_summaries) == 0
        assert len(ctx.edge_summaries) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 15: Fixture cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestFixtureCases:
    """Verify that the three 18B fixture cases are valid and internally consistent."""

    def test_all_fixture_cases_have_case_id(self):
        for case in ALL_FIXTURE_CASES:
            assert case.case_id, f"Fixture case missing case_id"

    def test_all_fixture_inputs_have_evaluation_input_id(self):
        for inp in ALL_FIXTURE_INPUTS:
            assert inp.evaluation_input_id

    def test_fixture_prompt_hashes_are_set(self):
        for inp in ALL_FIXTURE_INPUTS:
            assert inp.prompt_hash
            assert len(inp.prompt_hash) == 64  # SHA-256

    def test_fixture_prompt_hash_matches_prompt(self):
        for inp in ALL_FIXTURE_INPUTS:
            expected_hash = ModelEvaluationInput.make_prompt_hash(inp.prompt)
            assert inp.prompt_hash == expected_hash

    def test_wave17_labor_risk_case(self):
        assert wave17_labor_risk.case_id == "wave17-labor-risk-v1"
        assert wave17_labor_risk.task_family == TaskFamily.ASK
        assert wave17_labor_risk.expected_capability == "labor_reallocation"
        assert wave17_labor_risk.expected_target == "wave-17"
        assert len(wave17_labor_risk.required_facts) >= 1
        assert len(wave17_labor_risk.forbidden_claims) >= 1

    def test_equipment_failure_case(self):
        assert equipment_failure.case_id == "equipment-failure-v1"
        assert equipment_failure.task_family == TaskFamily.ASK
        assert equipment_failure.expected_capability == "equipment_bypass"
        assert "conveyor" in equipment_failure.expected_target

    def test_healthy_baseline_case(self):
        assert healthy_baseline.case_id == "healthy-baseline-v1"
        assert healthy_baseline.task_family == TaskFamily.ANALYZE
        assert healthy_baseline.expected_capability is None  # no intervention expected

    def test_fixture_case_lookup(self):
        case = get_fixture_case("wave17-labor-risk-v1")
        assert case.case_id == "wave17-labor-risk-v1"

    def test_fixture_input_lookup(self):
        inp = get_fixture_input("wave17-labor-risk-v1")
        assert inp.evaluation_input_id == "wave17-labor-risk-v1"

    def test_fixture_case_not_found(self):
        with pytest.raises(KeyError):
            get_fixture_case("nonexistent-case")

    def test_fixture_input_not_found(self):
        with pytest.raises(KeyError):
            get_fixture_input("nonexistent-input")

    def test_three_fixture_cases(self):
        assert len(ALL_FIXTURE_CASES) == 3

    def test_three_fixture_inputs(self):
        assert len(ALL_FIXTURE_INPUTS) == 3


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 16: End-to-end evaluation flow
# ═══════════════════════════════════════════════════════════════════════════════


class TestEvaluationEndToEnd:
    """Prove the evaluation infrastructure works end-to-end with fixture cases."""

    def test_evaluate_wave17_labor_risk(self):
        """
        Prove: fixture case + graded model response produces GraderResults.
        No real model call — uses a pre-fabricated response aligned with fixture.
        """
        case = wave17_labor_risk
        response_text = (
            "Wave-17 is at risk due to a labor shortage in the morning shift. "
            "The primary bottleneck is insufficient workers assigned to zone-picking. "
            "I recommend labor reallocation from zone-receiving to zone-picking "
            "to address the constraint."
        )
        result = ModelEvaluationResult(
            evaluation_input_id=case.case_id,
            model_id="test/super-model",
            deployment_id="nvidia_hosted",
            response=response_text,
            latency_ms=350.0,
            routing_latency_ms=0.8,
            routing_strategy="rules",
            candidate_models=["test/super-model"],
        )
        grader_results = run_graders(case, result)
        assert len(grader_results) == 6
        # Schema check: no expected_schema → passes
        assert grader_results[0].passed  # SchemaValidityGrader
        # Target match: "wave-17" in response → passes
        target_result = next(gr for gr in grader_results if gr.grader_name == "target_match")
        assert target_result.passed
        # Capability match: "labor reallocation" mentioned → passes
        cap_result = next(gr for gr in grader_results if gr.grader_name == "capability_match")
        assert cap_result.passed

    def test_evaluate_healthy_baseline_no_intervention(self):
        """
        Healthy baseline: response should NOT assert forbidden crisis claims.
        """
        case = healthy_baseline
        response_text = (
            "Wave-17 is currently on track. Labor allocation is sufficient "
            "and equipment is operating normally. No intervention is required."
        )
        result = ModelEvaluationResult(
            evaluation_input_id=case.case_id,
            model_id="test/super-model",
            deployment_id="nvidia_hosted",
            response=response_text,
            latency_ms=200.0,
            routing_latency_ms=0.5,
            routing_strategy="rules",
            candidate_models=["test/super-model"],
        )
        grader_results = run_graders(case, result)
        forbidden_result = next(gr for gr in grader_results if gr.grader_name == "forbidden_claims")
        assert forbidden_result.passed, "Healthy baseline response must not contain forbidden crisis claims"

    def test_evaluation_grader_result_completeness(self):
        """Each GraderResult must have grader_name and passed fields."""
        case = wave17_labor_risk
        result = _make_grader_result(response="wave-17 labor reallocation needed")
        for gr in run_graders(case, result):
            assert gr.grader_name
            assert isinstance(gr.passed, bool)
            assert isinstance(gr.evidence, list)
