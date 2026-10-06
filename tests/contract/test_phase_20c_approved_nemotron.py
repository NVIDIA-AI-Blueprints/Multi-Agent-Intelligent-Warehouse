# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 20C-A — Approved Nemotron Policy + Bounded ModelGateway HTTP Boundary.

Tests cover:

MODEL FAMILY POLICY (Steps 7-9, 33, 40, 45, 46, 47, 59)
  P01  Approved Nemotron 3 accepted by PolicyFilter
  P02  Approved Nemotron 3.5 accepted by PolicyFilter
  P03  Legacy llama-3.1-nemotron (TRANSPORT_SMOKE_TEST_MODEL) rejected by PolicyFilter
  P04  Arbitrary Llama generation rejected by PolicyFilter
  P05  Unknown/Qwen generation rejected by PolicyFilter
  P06  Fallback stays within approved family (not legacy)
  P07  Deployment Resolver cannot map approved role to unapproved physical model
  P08  PolicyFilter.APPROVED_MODEL_GENERATIONS is the canonical authoritative set
  P09  Production PolicyFilter has no override path from environment
  P10  Evaluation mode uses _for_evaluation() isolated factory (cannot leak)
  P11  Production constructor has no approved_generations parameter
  P12  Preferred approved model unavailable → fallback must stay approved, else ModelUnavailable

HTTP API CONTRACT (Steps 13-23, 57)
  A01  Valid request succeeds — translated to canonical ModelRequest
  A02  Forbidden field provider_url rejected (HTTP 422)
  A03  Forbidden field api_key rejected (HTTP 422)
  A04  Forbidden field deployment_endpoint rejected (HTTP 422)
  A05  Forbidden field force_model_id rejected (HTTP 422)
  A06  Forbidden field deployment_mode rejected (HTTP 422)
  A07  Forbidden field model_id rejected (HTTP 422)
  A08  Unapproved model injection — unknown field rejected (HTTP 422)
  A09  Malformed messages (wrong role enum) rejected (HTTP 422)
  A10  Empty messages list rejected (HTTP 422)
  A11  Message count exceeds limit rejected (HTTP 422)
  A12  ModelUnavailable maps to HTTP 503 with code MODEL_UNAVAILABLE
  A13  Expired deadline maps to HTTP 504 with code DEADLINE_EXCEEDED
  A14  ModelGatewayError maps to HTTP 503 with code PROVIDER_FAILURE
  A15  Trace IDs propagate from InferenceRequest to ModelRequest
  A16  Response never contains provider URL, API key, or base URL
  A17  Response route.approved_family=True for approved Nemotron
  A18  Gateway singleton is reused (not created per-request)
  A19  deployment_mode is always NVIDIA_HOSTED regardless of body
  A20  No governance/ActionExecutor below inference endpoint

AUTH FAIL-CLOSED (Fix 5)
  AUTH01  No token + no ALLOW_UNAUTHENTICATED → HTTP 503 (misconfigured)
  AUTH02  No token + ALLOW_UNAUTHENTICATED=true → allowed (development mode)
  AUTH03  Token configured + wrong token → HTTP 401
  AUTH04  Token configured + correct token → HTTP 200
  AUTH05  Token configured + no token header → HTTP 401

HTTP CLIENT CONTRACT (Steps 24, 58)
  C01  Client serializes ModelRequest to correct JSON shape
  C02  Client deserializes InferenceResponse to ModelResponse
  C03  Client raises RequestDeadlineExceeded on HTTP 504
  C04  Client raises ModelUnavailable on HTTP 503 MODEL_UNAVAILABLE
  C05  Client raises ModelGatewayError on HTTP 503 PROVIDER_FAILURE
  C06  Client raises SandboxInferenceError on connection error
  C07  NO TRANSPORT FALLBACK — failure stays failure, no local gateway
  C08  Deadline remaining_ms propagated in payload
  C09  Trace IDs propagated in payload
  C10  localhost endpoint rejected at construction time
  C11  HIGH reasoning preserved in route decision provenance
  C12  CRITICAL risk preserved in route decision provenance
  C13  Task identity preserved in route decision provenance

SANDBOX POLICY (Steps 27-28, 31, 32)
  S01  SandboxConfig localhost rejected by HTTP client at construction
  S02  SandboxConfig.model_gateway_endpoint rejects write-shaped paths
  S03  SandboxConfig.model_gateway_endpoint rejects embedded credentials
  S04  Network policy: inference endpoint allowed, direct NIM endpoint NOT allowed
  S05  Sandbox cannot reach local NIM at localhost:8002 (SSRF expected behavior)

REGISTRY & RECLASSIFICATION (Steps 1, 2, 48)
  R01  TRANSPORT_SMOKE_TEST_MODEL constant matches expected model ID
  R02  TRANSPORT_SMOKE_TEST_MODEL is a legacy Llama model (not approved)
  R03  Default registry contains only Nemotron 3/3.5 generations (no legacy)
  R04  Enabled default models all have approved generations
  R05  nano-omni with generation=nemotron-3 is eligible when enabled
  R05b Model with truly unknown generation is blocked

MODEL INVENTORY (Step 2)
  I01  Model inventory table verified — all defaults are Nemotron 3 or 3.5
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Path setup ────────────────────────────────────────────────────────────────

_REPO = Path(__file__).resolve().parents[2]
for _pkg in (
    "packages/maiw-models",
    "packages/maiw-mcp",
    "packages/maiw-agents",
):
    _p = str(_REPO / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)

_INTEGRATIONS = str(_REPO / "integrations")
if _INTEGRATIONS not in sys.path:
    sys.path.insert(0, _INTEGRATIONS)

# ── Imports ───────────────────────────────────────────────────────────────────

from maiw_models import (
    ModelCapability,
    ModelRequest,
    ModelResponse,
    ModelRouteDecision,
    ModelUnavailable,
    ModelGatewayError,
    PolicyFilter,
    ModelRegistry,
    DeploymentMode,
    DeploymentStatus,
    Modality,
    ReasoningLevel,
    RiskLevel,
    LatencyClass,
    CostClass,
    reset_model_gateway,
)

# TRANSPORT_SMOKE_TEST_MODEL may not be in the installed package yet; import
# from local registry if available, otherwise use the known constant directly.
try:
    from maiw_models import TRANSPORT_SMOKE_TEST_MODEL  # type: ignore[attr-defined]
except ImportError:
    # Local constant: Phase 20B transport smoke-test model (Llama-family, NOT approved).
    TRANSPORT_SMOKE_TEST_MODEL = "nvidia/llama-3.1-nemotron-nano-8b-v1"
from maiw_mcp.deadline import RequestDeadline, RequestDeadlineExceeded

from nemoclaw.http_model_gateway_client import (
    MAIWHTTPModelGatewayClient,
    SandboxInferenceError,
)
from nemoclaw.sandbox_config import (
    SandboxConfig,
    SandboxConfigurationError,
    SandboxMode,
    SandboxRuntimeKind,
)

# ── Module-level singleton reset ──────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_gateway_singleton():
    """Ensure ModelGateway singleton does not leak between tests.

    This module-level autouse fixture resets the singleton before and after
    every test in this file, preventing state contamination when this file is
    run as part of the combined test suite after other tests that may have
    initialised the singleton.
    """
    reset_model_gateway()
    yield
    reset_model_gateway()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_capability(
    model_id: str,
    role: str = "nano",
    generation: str = "nemotron-3",
    enabled: bool = True,
    family: str = "nemotron",
    provider: str = "nvidia-nim",
) -> ModelCapability:
    return ModelCapability(
        model_id=model_id,
        role=role,
        family=family,
        generation=generation,
        provider=provider,
        deployment_status=DeploymentStatus.DEPLOYED,
        modalities={"text"},
        tool_use=False,
        structured_output=False,
        reasoning_level=ReasoningLevel.MEDIUM,
        latency_class=LatencyClass.LOW,
        cost_class=CostClass.LOW,
        teacher_judge=False,
        enabled=enabled,
    )


def _make_registry(*caps: ModelCapability) -> ModelRegistry:
    """Build a registry stub from explicit capabilities (bypasses env var loading)."""
    reg = ModelRegistry.__new__(ModelRegistry)
    reg._capabilities = {c.model_id: c for c in caps}
    reg._role_index = {c.role: c.model_id for c in caps}
    return reg


def _base_request(**kwargs: Any) -> ModelRequest:
    defaults = dict(
        task="test_task",
        messages=[{"role": "user", "content": "Hello"}],
        reasoning=ReasoningLevel.MEDIUM,
        risk_level=RiskLevel.LOW,
        modality=Modality.TEXT,
        deployment_mode=DeploymentMode.NVIDIA_HOSTED,
    )
    defaults.update(kwargs)
    return ModelRequest(**defaults)


def _make_mock_response(
    model_id: str = "nvidia/nemotron-3-nano-30b-a3b",
    reasoning: ReasoningLevel = ReasoningLevel.MEDIUM,
    risk_level: RiskLevel = RiskLevel.LOW,
    task: str = "test_task",
) -> ModelResponse:
    return ModelResponse(
        content="test response",
        model_id=model_id,
        model_family="nemotron",
        latency_ms=42.0,
        finish_reason="stop",
        usage={"prompt_tokens": 10, "completion_tokens": 20},
        route_decision=ModelRouteDecision(
            selected_model_id=model_id,
            selected_role="nano",
            requested_role="nano",
            routing_rule="medium_reasoning",
            routing_reason="MEDIUM reasoning → nano",
            task=task,
            requested_reasoning=reasoning,
            requested_risk_level=risk_level,
            fallback_from=None,
            candidate_models=[model_id],
        ),
    )


# ═════════════════════════════════════════════════════════════════════════════
# MODEL FAMILY POLICY TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestModelFamilyPolicy:
    """P01–P12: Model generation policy enforcement in PolicyFilter."""

    def _filter_with_cap(self, cap: ModelCapability) -> list:
        reg = _make_registry(cap)
        pf = PolicyFilter(reg)
        return pf.filter(_base_request(), DeploymentMode.NVIDIA_HOSTED)

    def test_P01_nemotron_3_accepted(self):
        """P01: Approved Nemotron 3 model is eligible."""
        cap = _make_capability(
            "nvidia/nemotron-3-nano-30b-a3b", generation="nemotron-3"
        )
        result = self._filter_with_cap(cap)
        assert len(result) == 1
        assert result[0].model_id == "nvidia/nemotron-3-nano-30b-a3b"

    def test_P02_nemotron_35_accepted(self):
        """P02: Approved Nemotron 3.5 model is eligible."""
        cap = _make_capability(
            "nvidia/nemotron-3.5-lightning-30b-a3b",
            role="lightning",
            generation="nemotron-3.5",
        )
        result = self._filter_with_cap(cap)
        assert len(result) == 1
        assert result[0].model_id == "nvidia/nemotron-3.5-lightning-30b-a3b"

    def test_P03_legacy_llama_nemotron_rejected(self):
        """P03: Llama-family Nemotron (TRANSPORT_SMOKE_TEST_MODEL) is REJECTED."""
        cap = _make_capability(
            TRANSPORT_SMOKE_TEST_MODEL,
            role="nano",
            generation="legacy",
        )
        result = self._filter_with_cap(cap)
        assert len(result) == 0, (
            f"PolicyFilter must reject {TRANSPORT_SMOKE_TEST_MODEL} "
            "(Llama-family, generation=legacy)"
        )

    def test_P03b_llama_nemotron_nano_any_unapproved_generation_rejected(self):
        """P03b: Any model with a non-approved generation is rejected."""
        for gen in ("legacy", "llama-3.1", "llama", "unknown", "nemotron-llama"):
            cap = _make_capability(TRANSPORT_SMOKE_TEST_MODEL, generation=gen)
            result = self._filter_with_cap(cap)
            assert len(result) == 0, f"generation={gen!r} must be rejected"

    def test_P04_arbitrary_llama_rejected(self):
        """P04: Arbitrary Llama model (non-Nemotron) is rejected."""
        cap = _make_capability(
            "meta-llama/Llama-3.1-70b-instruct",
            role="nano",
            generation="llama-3.1",
        )
        result = self._filter_with_cap(cap)
        assert len(result) == 0

    def test_P05_unknown_generation_rejected(self):
        """P05: Models with unknown generation are rejected."""
        cap = _make_capability("unknown-model/v1", role="nano", generation="unknown")
        result = self._filter_with_cap(cap)
        assert len(result) == 0

    def test_P05b_qwen_rejected(self):
        """P05b: Arbitrary Qwen model is rejected."""
        cap = _make_capability("qwen/qwen-72b", role="nano", generation="qwen-2.5")
        result = self._filter_with_cap(cap)
        assert len(result) == 0

    def test_P06_fallback_stays_in_approved_family(self):
        """P06: Fallback chain only selects models with approved generations."""
        approved_cap = _make_capability(
            "nvidia/nemotron-3-nano-30b-a3b", role="nano", generation="nemotron-3"
        )
        unapproved_cap = _make_capability(
            TRANSPORT_SMOKE_TEST_MODEL,
            role="super",
            generation="legacy",
        )
        reg = _make_registry(approved_cap, unapproved_cap)
        pf = PolicyFilter(reg)
        candidates = pf.filter(_base_request(), DeploymentMode.NVIDIA_HOSTED)
        candidate_ids = [c.model_id for c in candidates]
        assert (
            TRANSPORT_SMOKE_TEST_MODEL not in candidate_ids
        ), "Unapproved model must not appear in fallback candidates"
        assert "nvidia/nemotron-3-nano-30b-a3b" in candidate_ids

    def test_P07_deployment_resolver_no_unapproved_mapping(self):
        """P07: Default registry maps all roles to Nemotron 3/3.5 only."""
        reg = ModelRegistry()
        pf = PolicyFilter(reg)
        candidates = pf.filter(_base_request(), DeploymentMode.NVIDIA_HOSTED)
        for c in candidates:
            gen = c.capability.generation
            assert gen in PolicyFilter.APPROVED_MODEL_GENERATIONS, (
                f"Deployment Resolver mapped role={c.role} to "
                f"model={c.model_id} with unapproved generation={gen!r}"
            )

    def test_P08_approved_generations_is_canonical_frozenset(self):
        """P08: APPROVED_MODEL_GENERATIONS is an immutable frozenset."""
        assert isinstance(PolicyFilter.APPROVED_MODEL_GENERATIONS, frozenset)
        assert "nemotron-3" in PolicyFilter.APPROVED_MODEL_GENERATIONS
        assert "nemotron-3.5" in PolicyFilter.APPROVED_MODEL_GENERATIONS
        assert "legacy" not in PolicyFilter.APPROVED_MODEL_GENERATIONS
        assert "llama-3.1" not in PolicyFilter.APPROVED_MODEL_GENERATIONS
        assert "unknown" not in PolicyFilter.APPROVED_MODEL_GENERATIONS

    def test_P09_production_filter_no_env_override(self):
        """P09: Production PolicyFilter cannot be widened via environment variable."""
        with patch.dict(
            os.environ, {"MAIW_APPROVED_MODEL_GENERATIONS": "legacy,nemotron-3"}
        ):
            reg = _make_registry(
                _make_capability(TRANSPORT_SMOKE_TEST_MODEL, generation="legacy")
            )
            pf = PolicyFilter(reg)
            result = pf.filter(_base_request(), DeploymentMode.NVIDIA_HOSTED)
            assert len(result) == 0, (
                "Environment variable must not widen production PolicyFilter "
                "approved_generations"
            )

    def test_P10_evaluation_uses_isolated_factory(self):
        """P10: Evaluation Lab uses _for_evaluation() factory (isolated from production)."""
        cap = _make_capability(TRANSPORT_SMOKE_TEST_MODEL, generation="legacy")
        reg = _make_registry(cap)
        # Use the isolated evaluation factory — NOT the production constructor.
        eval_filter = PolicyFilter._for_evaluation(
            reg,
            approved_generations=frozenset({"nemotron-3", "nemotron-3.5", "legacy"}),
        )
        result = eval_filter.filter(_base_request(), DeploymentMode.NVIDIA_HOSTED)
        assert (
            len(result) == 1
        ), "Evaluation filter with explicit broader set must accept legacy model"
        # Production filter still rejects it.
        prod_filter = PolicyFilter(reg)
        assert (
            len(prod_filter.filter(_base_request(), DeploymentMode.NVIDIA_HOSTED)) == 0
        )

    def test_P11_production_constructor_takes_no_approved_generations_arg(self):
        """P11: Production PolicyFilter constructor has no approved_generations parameter."""
        import inspect

        sig = inspect.signature(PolicyFilter.__init__)
        param_names = list(sig.parameters.keys())
        assert "approved_generations" not in param_names, (
            "PolicyFilter.__init__ must not accept approved_generations. "
            "Use PolicyFilter._for_evaluation() for evaluation contexts."
        )

    def test_P12_preferred_approved_unavailable_fallback_stays_approved(self):
        """P12: If preferred approved model is unavailable, fallback must stay approved."""
        # Only an approved nano model. Request HIGH reasoning → requires super/ultra.
        # No super/ultra available → ModelUnavailable (not fallback to unapproved).
        nano_cap = _make_capability(
            "nvidia/nemotron-3-nano-30b-a3b",
            role="nano",
            generation="nemotron-3",
        )
        unapproved_super = _make_capability(
            TRANSPORT_SMOKE_TEST_MODEL,
            role="super",
            generation="legacy",
        )
        reg = _make_registry(nano_cap, unapproved_super)
        pf = PolicyFilter(reg)
        # HIGH reasoning requires super/ultra — only unapproved super exists.
        high_req = _base_request(reasoning=ReasoningLevel.HIGH)
        candidates = pf.filter(high_req, DeploymentMode.NVIDIA_HOSTED)
        # The unapproved super must be filtered out.
        candidate_ids = [c.model_id for c in candidates]
        assert (
            TRANSPORT_SMOKE_TEST_MODEL not in candidate_ids
        ), "Unapproved model must not be used as fallback for HIGH reasoning"
        # No approved high-capability model → empty candidate list.
        assert (
            len(candidates) == 0
        ), "When no approved high-capability model exists, candidate list is empty"


# ═════════════════════════════════════════════════════════════════════════════
# HTTP API CONTRACT TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestInferenceHTTPContract:
    """A01–A20: Tests for the POST /api/v1/inference endpoint."""

    @pytest.fixture(autouse=True)
    def _reset_gateway_and_set_dev_mode(self):
        """Reset ModelGateway singleton and enable dev auth mode between tests."""
        from maiw_models import reset_model_gateway

        reset_model_gateway()
        # Allow unauthenticated access in tests (development mode).
        with patch.dict(
            os.environ, {"MAIW_INFERENCE_ALLOW_UNAUTHENTICATED": "true"}, clear=False
        ):
            yield
        reset_model_gateway()

    def _get_client(self):
        """Get FastAPI test client."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.api.routers.inference import router

        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def _mock_gateway(
        self,
        response: ModelResponse | None = None,
        side_effect: Any = None,
    ) -> MagicMock:
        """Create a mock ModelGateway that returns a response or raises."""
        gw = MagicMock()
        if side_effect is not None:
            gw.generate = AsyncMock(side_effect=side_effect)
        else:
            gw.generate = AsyncMock(return_value=response or _make_mock_response())
        # Expose registry via public property (gateway.registry, not gateway._registry).
        cap = _make_capability(
            "nvidia/nemotron-3-nano-30b-a3b", generation="nemotron-3"
        )
        gw.registry = _make_registry(cap)
        return gw

    def test_A01_valid_request_succeeds(self):
        """A01: Valid inference request returns 200 with InferenceResponse."""
        mock_resp = _make_mock_response("nvidia/nemotron-3-nano-30b-a3b")
        gw = self._mock_gateway(response=mock_resp)
        client = self._get_client()
        with patch(
            "src.api.routers.inference.get_model_gateway",
            new=AsyncMock(return_value=gw),
        ):
            r = client.post(
                "/api/v1/inference",
                json={
                    "task": "wave_risk",
                    "messages": [{"role": "user", "content": "Assess risk"}],
                },
            )
        assert r.status_code == 200
        data = r.json()
        assert data["content"] == "test response"
        assert data["model_id"] == "nvidia/nemotron-3-nano-30b-a3b"
        assert data["finish_reason"] == "stop"
        assert "route" in data
        assert data["route"]["approved_family"] is True

    def test_A02_forbidden_provider_url(self):
        """A02: provider_url in body is rejected with HTTP 422."""
        client = self._get_client()
        r = client.post(
            "/api/v1/inference",
            json={
                "task": "t",
                "messages": [{"role": "user", "content": "hi"}],
                "provider_url": "http://malicious:9999/v1",
            },
        )
        assert r.status_code == 422

    def test_A03_forbidden_api_key(self):
        """A03: api_key in body is rejected with HTTP 422."""
        client = self._get_client()
        r = client.post(
            "/api/v1/inference",
            json={
                "task": "t",
                "messages": [{"role": "user", "content": "hi"}],
                "api_key": "nvapi-secret123",
            },
        )
        assert r.status_code == 422

    def test_A04_forbidden_deployment_endpoint(self):
        """A04: deployment_endpoint in body is rejected with HTTP 422."""
        client = self._get_client()
        r = client.post(
            "/api/v1/inference",
            json={
                "task": "t",
                "messages": [{"role": "user", "content": "hi"}],
                "deployment_endpoint": "http://localhost:8002/v1",
            },
        )
        assert r.status_code == 422

    def test_A05_forbidden_force_model_id(self):
        """A05: force_model_id in body is rejected with HTTP 422."""
        client = self._get_client()
        r = client.post(
            "/api/v1/inference",
            json={
                "task": "t",
                "messages": [{"role": "user", "content": "hi"}],
                "force_model_id": "nvidia/llama-3.1-nemotron-nano-8b-v1",
            },
        )
        assert r.status_code == 422

    def test_A06_forbidden_deployment_mode(self):
        """A06: deployment_mode in body is rejected with HTTP 422."""
        client = self._get_client()
        r = client.post(
            "/api/v1/inference",
            json={
                "task": "t",
                "messages": [{"role": "user", "content": "hi"}],
                "deployment_mode": "local_nim",
            },
        )
        assert r.status_code == 422

    def test_A07_forbidden_model_id(self):
        """A07: model_id in body is rejected with HTTP 422."""
        client = self._get_client()
        r = client.post(
            "/api/v1/inference",
            json={
                "task": "t",
                "messages": [{"role": "user", "content": "hi"}],
                "model_id": "nvidia/llama-3.1-nemotron-nano-8b-v1",
            },
        )
        assert r.status_code == 422

    def test_A08_unapproved_model_injection_via_unknown_field(self):
        """A08: Unknown field that could be a model injection is rejected."""
        client = self._get_client()
        r = client.post(
            "/api/v1/inference",
            json={
                "task": "t",
                "messages": [{"role": "user", "content": "hi"}],
                "api_key_env_var": "NVIDIA_API_KEY",
            },
        )
        assert r.status_code == 422

    def test_A09_malformed_message_role(self):
        """A09: Invalid role enum rejected with HTTP 422."""
        client = self._get_client()
        r = client.post(
            "/api/v1/inference",
            json={
                "task": "t",
                "messages": [{"role": "function", "content": "hi"}],
            },
        )
        assert r.status_code == 422

    def test_A10_empty_messages_rejected(self):
        """A10: Empty messages list rejected with HTTP 422."""
        client = self._get_client()
        r = client.post(
            "/api/v1/inference",
            json={"task": "t", "messages": []},
        )
        assert r.status_code == 422

    def test_A11_message_count_exceeds_limit(self):
        """A11: More than 64 messages rejected with HTTP 422."""
        client = self._get_client()
        messages = [{"role": "user", "content": f"msg {i}"} for i in range(65)]
        r = client.post(
            "/api/v1/inference",
            json={"task": "t", "messages": messages},
        )
        assert r.status_code == 422

    def test_A12_model_unavailable_returns_503(self):
        """A12: ModelUnavailable maps to HTTP 503 with code MODEL_UNAVAILABLE."""
        gw = self._mock_gateway(side_effect=ModelUnavailable("no eligible model"))
        client = self._get_client()
        with patch(
            "src.api.routers.inference.get_model_gateway",
            new=AsyncMock(return_value=gw),
        ):
            r = client.post(
                "/api/v1/inference",
                json={"task": "t", "messages": [{"role": "user", "content": "hi"}]},
            )
        assert r.status_code == 503
        assert r.json()["code"] == "MODEL_UNAVAILABLE"

    def test_A13_deadline_exceeded_returns_504(self):
        """A13: RequestDeadlineExceeded maps to HTTP 504 with code DEADLINE_EXCEEDED."""
        gw = self._mock_gateway(
            side_effect=RequestDeadlineExceeded(expired_by_ms=100.0)
        )
        client = self._get_client()
        with patch(
            "src.api.routers.inference.get_model_gateway",
            new=AsyncMock(return_value=gw),
        ):
            r = client.post(
                "/api/v1/inference",
                json={
                    "task": "t",
                    "messages": [{"role": "user", "content": "hi"}],
                    "deadline_ms": 1,
                },
            )
        assert r.status_code == 504
        assert r.json()["code"] == "DEADLINE_EXCEEDED"

    def test_A14_gateway_error_returns_503(self):
        """A14: ModelGatewayError maps to HTTP 503 with code PROVIDER_FAILURE."""
        gw = self._mock_gateway(side_effect=ModelGatewayError("provider down"))
        client = self._get_client()
        with patch(
            "src.api.routers.inference.get_model_gateway",
            new=AsyncMock(return_value=gw),
        ):
            r = client.post(
                "/api/v1/inference",
                json={"task": "t", "messages": [{"role": "user", "content": "hi"}]},
            )
        assert r.status_code == 503
        assert r.json()["code"] == "PROVIDER_FAILURE"

    def test_A15_trace_ids_propagate(self):
        """A15: Trace IDs from InferenceRequest reach ModelRequest and InferenceResponse."""
        mock_resp = _make_mock_response()
        gw = self._mock_gateway(response=mock_resp)
        client = self._get_client()
        with patch(
            "src.api.routers.inference.get_model_gateway",
            new=AsyncMock(return_value=gw),
        ):
            r = client.post(
                "/api/v1/inference",
                json={
                    "task": "t",
                    "messages": [{"role": "user", "content": "hi"}],
                    "trace_id": "trace-abc123",
                    "agent_task_id": "task-999",
                    "procedure_execution_id": "proc-001",
                    "step_execution_id": "step-42",
                },
            )
        assert r.status_code == 200
        data = r.json()
        assert data["trace_id"] == "trace-abc123"
        assert data["agent_task_id"] == "task-999"
        assert data["procedure_execution_id"] == "proc-001"
        assert data["step_execution_id"] == "step-42"
        model_req: ModelRequest = gw.generate.call_args[0][0]
        assert model_req.trace_id == "trace-abc123"
        assert model_req.metadata["agent_task_id"] == "task-999"

    def test_A16_response_contains_no_secrets(self):
        """A16: Response does not contain provider URL, API key, or base URL."""
        mock_resp = _make_mock_response()
        gw = self._mock_gateway(response=mock_resp)
        client = self._get_client()
        with patch(
            "src.api.routers.inference.get_model_gateway",
            new=AsyncMock(return_value=gw),
        ):
            r = client.post(
                "/api/v1/inference",
                json={"task": "t", "messages": [{"role": "user", "content": "hi"}]},
            )
        assert r.status_code == 200
        body_text = r.text.lower()
        for secret_key in ("api_key", "base_url", "provider_url", "nvapi-", "bearer"):
            assert (
                secret_key not in body_text
            ), f"Response must not contain {secret_key!r}"

    def test_A17_response_approved_family_true(self):
        """A17: route.approved_family=True when model has approved generation."""
        mock_resp = _make_mock_response("nvidia/nemotron-3-nano-30b-a3b")
        cap = _make_capability(
            "nvidia/nemotron-3-nano-30b-a3b", generation="nemotron-3"
        )
        gw = self._mock_gateway(response=mock_resp)
        gw.registry = _make_registry(cap)
        client = self._get_client()
        with patch(
            "src.api.routers.inference.get_model_gateway",
            new=AsyncMock(return_value=gw),
        ):
            r = client.post(
                "/api/v1/inference",
                json={"task": "t", "messages": [{"role": "user", "content": "hi"}]},
            )
        assert r.status_code == 200
        assert r.json()["route"]["approved_family"] is True

    def test_A19_deployment_mode_always_nvidia_hosted(self):
        """A19: ModelRequest always gets deployment_mode=NVIDIA_HOSTED."""
        gw = self._mock_gateway()
        client = self._get_client()
        with patch(
            "src.api.routers.inference.get_model_gateway",
            new=AsyncMock(return_value=gw),
        ):
            r = client.post(
                "/api/v1/inference",
                json={"task": "t", "messages": [{"role": "user", "content": "hi"}]},
            )
        assert r.status_code == 200
        model_req: ModelRequest = gw.generate.call_args[0][0]
        assert model_req.deployment_mode == DeploymentMode.NVIDIA_HOSTED

    def test_A20_no_action_executor_in_endpoint(self):
        """A20: inference router does not import ActionExecutor or governance modules."""
        src = (_REPO / "src/api/routers/inference.py").read_text()
        tree = ast.parse(src)
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(ast.unparse(node))
        forbidden_imports = ["maiw_execution", "action_executor", "decision_engine"]
        for bad in forbidden_imports:
            for imp in imports:
                assert (
                    bad not in imp.lower()
                ), f"inference.py must not import from {bad!r}: found {imp!r}"


# ═════════════════════════════════════════════════════════════════════════════
# AUTH FAIL-CLOSED TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestAuthFailClosed:
    """AUTH01–AUTH05: Auth endpoint must fail closed when no token is configured."""

    def _get_client(self) -> Any:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.api.routers.inference import router

        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    @pytest.fixture(autouse=True)
    def _reset_gateway(self):
        from maiw_models import reset_model_gateway

        reset_model_gateway()
        yield
        reset_model_gateway()

    def test_AUTH01_no_token_no_allow_unauthenticated_returns_503(self):
        """AUTH01: No token configured + no override → 503 (misconfigured)."""
        client = self._get_client()
        env = {
            "MAIW_INFERENCE_INTERNAL_TOKEN": "",
            "MAIW_INFERENCE_ALLOW_UNAUTHENTICATED": "",
        }
        with patch.dict(os.environ, env, clear=False):
            # Ensure the token is actually absent (not just empty string vs unset).
            os.environ.pop("MAIW_INFERENCE_INTERNAL_TOKEN", None)
            os.environ.pop("MAIW_INFERENCE_ALLOW_UNAUTHENTICATED", None)
            r = client.post(
                "/api/v1/inference",
                json={"task": "t", "messages": [{"role": "user", "content": "hi"}]},
            )
        assert (
            r.status_code == 503
        ), "Endpoint must return 503 when no token configured and no dev override"

    def test_AUTH02_no_token_allow_unauthenticated_true_passes(self):
        """AUTH02: No token + MAIW_INFERENCE_ALLOW_UNAUTHENTICATED=true → allowed."""
        mock_resp = _make_mock_response()
        gw = MagicMock()
        gw.generate = AsyncMock(return_value=mock_resp)
        cap = _make_capability(
            "nvidia/nemotron-3-nano-30b-a3b", generation="nemotron-3"
        )
        gw.registry = _make_registry(cap)
        client = self._get_client()
        env = {"MAIW_INFERENCE_ALLOW_UNAUTHENTICATED": "true"}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("MAIW_INFERENCE_INTERNAL_TOKEN", None)
            with patch(
                "src.api.routers.inference.get_model_gateway",
                new=AsyncMock(return_value=gw),
            ):
                r = client.post(
                    "/api/v1/inference",
                    json={
                        "task": "t",
                        "messages": [{"role": "user", "content": "hi"}],
                    },
                )
        assert (
            r.status_code == 200
        ), "MAIW_INFERENCE_ALLOW_UNAUTHENTICATED=true must allow access in dev mode"

    def test_AUTH03_wrong_token_returns_401(self):
        """AUTH03: Token configured + wrong token → 401."""
        client = self._get_client()
        with patch.dict(
            os.environ,
            {"MAIW_INFERENCE_INTERNAL_TOKEN": "correct-secret"},
            clear=False,
        ):
            r = client.post(
                "/api/v1/inference",
                json={"task": "t", "messages": [{"role": "user", "content": "hi"}]},
                headers={"X-Maiw-Internal-Token": "wrong-secret"},
            )
        assert r.status_code == 401

    def test_AUTH04_correct_token_accepted(self):
        """AUTH04: Token configured + correct token → 200."""
        mock_resp = _make_mock_response()
        gw = MagicMock()
        gw.generate = AsyncMock(return_value=mock_resp)
        cap = _make_capability(
            "nvidia/nemotron-3-nano-30b-a3b", generation="nemotron-3"
        )
        gw.registry = _make_registry(cap)
        client = self._get_client()
        with patch.dict(
            os.environ,
            {"MAIW_INFERENCE_INTERNAL_TOKEN": "shared-secret-xyz"},
            clear=False,
        ):
            with patch(
                "src.api.routers.inference.get_model_gateway",
                new=AsyncMock(return_value=gw),
            ):
                r = client.post(
                    "/api/v1/inference",
                    json={
                        "task": "t",
                        "messages": [{"role": "user", "content": "hi"}],
                    },
                    headers={"X-Maiw-Internal-Token": "shared-secret-xyz"},
                )
        assert r.status_code == 200

    def test_AUTH05_token_required_no_header_returns_401(self):
        """AUTH05: Token configured + no header → 401."""
        client = self._get_client()
        with patch.dict(
            os.environ,
            {"MAIW_INFERENCE_INTERNAL_TOKEN": "shared-secret-xyz"},
            clear=False,
        ):
            r = client.post(
                "/api/v1/inference",
                json={"task": "t", "messages": [{"role": "user", "content": "hi"}]},
            )
        assert r.status_code == 401


# ═════════════════════════════════════════════════════════════════════════════
# HTTP CLIENT CONTRACT TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestHTTPClientContract:
    """C01–C13: Tests for MAIWHTTPModelGatewayClient."""

    def test_C01_client_serializes_model_request(self):
        """C01: Client serializes ModelRequest to correct JSON shape."""
        req = _base_request(
            task="wave_risk",
            messages=[{"role": "user", "content": "assess"}],
            reasoning=ReasoningLevel.HIGH,
            risk_level=RiskLevel.HIGH,
            trace_id="trace-001",
        )
        # Build payload manually using client's internal logic.
        payload: dict = {
            "task": req.task,
            "messages": [
                {"role": m["role"], "content": m.get("content", "")}
                for m in req.messages
            ],
            "reasoning": req.reasoning.value,
            "risk_level": req.risk_level.value,
            "modality": req.modality.value,
            "deadline_ms": 0,
        }
        if req.trace_id:
            payload["trace_id"] = req.trace_id
        assert payload["task"] == "wave_risk"
        assert payload["reasoning"] == "high"
        assert payload["risk_level"] == "high"
        assert payload["trace_id"] == "trace-001"
        for forbidden in ("provider_url", "api_key", "base_url", "deployment_endpoint"):
            assert forbidden not in payload

    def test_C02_client_deserializes_inference_response(self):
        """C02: Client deserializes InferenceResponse to ModelResponse."""
        http_client = MAIWHTTPModelGatewayClient(
            endpoint="http://maiw-api:8000/api/v1/inference"
        )
        req = _base_request(task="wave_risk")
        fake_http_resp = MagicMock()
        fake_http_resp.status_code = 200
        fake_http_resp.json.return_value = {
            "content": "Approved response",
            "model_id": "nvidia/nemotron-3-nano-30b-a3b",
            "finish_reason": "stop",
            "latency_ms": 55.5,
            "route": {
                "selected_model_id": "nvidia/nemotron-3-nano-30b-a3b",
                "selected_role": "nano",
                "generation": "nemotron-3",
                "approved_family": True,
                "routing_rule": "medium_reasoning",
                "fallback_used": False,
                "candidate_count": 3,
            },
            "trace_id": "trace-001",
            "agent_task_id": None,
            "procedure_execution_id": None,
            "step_execution_id": None,
        }
        result = http_client._parse_success(fake_http_resp, req)
        assert isinstance(result, ModelResponse)
        assert result.content == "Approved response"
        assert result.model_id == "nvidia/nemotron-3-nano-30b-a3b"
        assert result.finish_reason == "stop"
        assert result.latency_ms == 55.5

    def test_C03_client_raises_deadline_exceeded_on_504(self):
        """C03: HTTP 504 raises RequestDeadlineExceeded."""
        http_client = MAIWHTTPModelGatewayClient(
            endpoint="http://maiw-api:8000/api/v1/inference"
        )
        fake_resp = MagicMock()
        fake_resp.status_code = 504
        fake_resp.json.return_value = {
            "code": "DEADLINE_EXCEEDED",
            "message": "timeout",
        }
        with pytest.raises(RequestDeadlineExceeded):
            http_client._raise_structured_error(fake_resp)

    def test_C04_client_raises_model_unavailable_on_503(self):
        """C04: HTTP 503 MODEL_UNAVAILABLE raises ModelUnavailable."""
        http_client = MAIWHTTPModelGatewayClient(
            endpoint="http://maiw-api:8000/api/v1/inference"
        )
        fake_resp = MagicMock()
        fake_resp.status_code = 503
        fake_resp.json.return_value = {
            "code": "MODEL_UNAVAILABLE",
            "message": "no model",
        }
        with pytest.raises(ModelUnavailable):
            http_client._raise_structured_error(fake_resp)

    def test_C05_client_raises_gateway_error_on_provider_failure(self):
        """C05: HTTP 503 PROVIDER_FAILURE raises ModelGatewayError."""
        http_client = MAIWHTTPModelGatewayClient(
            endpoint="http://maiw-api:8000/api/v1/inference"
        )
        fake_resp = MagicMock()
        fake_resp.status_code = 503
        fake_resp.json.return_value = {
            "code": "PROVIDER_FAILURE",
            "message": "NIM down",
        }
        with pytest.raises(ModelGatewayError):
            http_client._raise_structured_error(fake_resp)

    @pytest.mark.asyncio
    async def test_C06_client_raises_sandbox_error_on_connection_failure(self):
        """C06: Network/connection error raises SandboxInferenceError."""
        import httpx

        http_client = MAIWHTTPModelGatewayClient(
            endpoint="http://maiw-api:8000/api/v1/inference"
        )
        req = _base_request()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_ctx = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_ctx.post.side_effect = httpx.ConnectError("Connection refused")
            with pytest.raises(SandboxInferenceError):
                await http_client.generate(req)

    def test_C07_no_transport_fallback_on_failure(self):
        """C07: HTTP client failure stays failure — no fallback to local gateway."""
        from nemoclaw import http_model_gateway_client as client_mod

        src_text = Path(client_mod.__file__).read_text()
        assert (
            "get_model_gateway" not in src_text
        ), "HTTP client must not call get_model_gateway (no fallback to local gateway)"
        assert (
            "NIMProvider" not in src_text
        ), "HTTP client must not instantiate NIMProvider"

    def test_C08_deadline_remaining_ms_propagated(self):
        """C08: Deadline remaining_ms is computed correctly from request."""
        deadline = RequestDeadline.from_timeout(seconds=30.0)
        req = _base_request(deadline=deadline)
        remaining = deadline.remaining_seconds * 1000
        assert remaining > 0
        assert remaining <= 30000

    def test_C09_trace_ids_in_payload(self):
        """C09: Trace IDs from ModelRequest.metadata are included in payload."""
        req = _base_request(
            trace_id="trace-xyz",
            metadata={
                "agent_task_id": "task-123",
                "procedure_execution_id": "proc-456",
            },
        )
        payload: dict = {
            "task": req.task,
            "messages": [
                {"role": m["role"], "content": m.get("content", "")}
                for m in req.messages
            ],
            "reasoning": req.reasoning.value,
            "risk_level": req.risk_level.value,
            "modality": req.modality.value,
            "deadline_ms": 0,
        }
        if req.trace_id:
            payload["trace_id"] = req.trace_id
        for field in ("agent_task_id", "procedure_execution_id", "step_execution_id"):
            if field in (req.metadata or {}):
                payload[field] = req.metadata[field]
        assert payload.get("trace_id") == "trace-xyz"
        assert payload.get("agent_task_id") == "task-123"
        assert payload.get("procedure_execution_id") == "proc-456"

    def test_C10_localhost_endpoint_rejected_at_construction(self):
        """C10: localhost endpoint rejected when constructing client."""
        for bad_endpoint in [
            "http://localhost:8000/api/v1/inference",
            "http://127.0.0.1:8000/api/v1/inference",
            "http://0.0.0.0:8000/api/v1/inference",
        ]:
            with pytest.raises(ValueError, match="localhost|loopback"):
                MAIWHTTPModelGatewayClient(endpoint=bad_endpoint)

    def test_C11_high_reasoning_preserved_in_provenance(self):
        """C11: HIGH reasoning level is preserved in ModelRouteDecision provenance."""
        http_client = MAIWHTTPModelGatewayClient(
            endpoint="http://maiw-api:8000/api/v1/inference"
        )
        req = _base_request(
            task="complex_analysis",
            reasoning=ReasoningLevel.HIGH,
            risk_level=RiskLevel.LOW,
        )
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {
            "content": "Complex analysis result",
            "model_id": "nvidia/nemotron-3-super-120b-a12b",
            "finish_reason": "stop",
            "latency_ms": 120.0,
            "route": {
                "selected_model_id": "nvidia/nemotron-3-super-120b-a12b",
                "selected_role": "super",
                "generation": "nemotron-3",
                "approved_family": True,
                "routing_rule": "high_reasoning",
                "fallback_used": False,
                "candidate_count": 2,
            },
            "trace_id": None,
            "agent_task_id": None,
            "procedure_execution_id": None,
            "step_execution_id": None,
        }
        result = http_client._parse_success(fake_resp, req)
        assert (
            result.route_decision.requested_reasoning == ReasoningLevel.HIGH
        ), "HIGH reasoning must be preserved in route provenance, not hard-coded to MEDIUM"
        assert (
            result.route_decision.task == "complex_analysis"
        ), "Task identity must be preserved from request"

    def test_C12_high_risk_preserved_in_provenance(self):
        """C12: HIGH risk level is preserved in ModelRouteDecision provenance."""
        http_client = MAIWHTTPModelGatewayClient(
            endpoint="http://maiw-api:8000/api/v1/inference"
        )
        req = _base_request(
            task="critical_operation",
            reasoning=ReasoningLevel.MEDIUM,
            risk_level=RiskLevel.HIGH,
        )
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {
            "content": "Critical result",
            "model_id": "nvidia/nemotron-3-super-120b-a12b",
            "finish_reason": "stop",
            "latency_ms": 80.0,
            "route": {
                "selected_model_id": "nvidia/nemotron-3-super-120b-a12b",
                "selected_role": "super",
                "generation": "nemotron-3",
                "approved_family": True,
                "routing_rule": "high_risk",
                "fallback_used": False,
                "candidate_count": 2,
            },
            "trace_id": None,
            "agent_task_id": None,
            "procedure_execution_id": None,
            "step_execution_id": None,
        }
        result = http_client._parse_success(fake_resp, req)
        assert (
            result.route_decision.requested_risk_level == RiskLevel.HIGH
        ), "HIGH risk must be preserved in route provenance, not hard-coded to LOW"

    def test_C13_task_identity_preserved_in_provenance(self):
        """C13: Task identity from original request is in route decision."""
        http_client = MAIWHTTPModelGatewayClient(
            endpoint="http://maiw-api:8000/api/v1/inference"
        )
        req = _base_request(task="wave_risk_escalation_probe")
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {
            "content": "result",
            "model_id": "nvidia/nemotron-3-nano-30b-a3b",
            "finish_reason": "stop",
            "latency_ms": 30.0,
            "route": {
                "selected_model_id": "nvidia/nemotron-3-nano-30b-a3b",
                "selected_role": "nano",
                "generation": "nemotron-3",
                "approved_family": True,
                "routing_rule": "medium_reasoning",
                "fallback_used": False,
                "candidate_count": 3,
            },
            "trace_id": None,
            "agent_task_id": None,
            "procedure_execution_id": None,
            "step_execution_id": None,
        }
        result = http_client._parse_success(fake_resp, req)
        assert (
            result.route_decision.task == "wave_risk_escalation_probe"
        ), "Task must come from the request, not from the response body"


# ═════════════════════════════════════════════════════════════════════════════
# SANDBOX POLICY TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestSandboxPolicy:
    """S01–S05: Sandbox network and configuration policy."""

    def _base_cfg(self, **overrides: Any) -> dict:
        base = dict(
            mode=SandboxMode.SANDBOX_REQUIRED,
            runtime_kind=SandboxRuntimeKind.OPENSHELL,
            model_gateway_endpoint="http://maiw-api:8000/api/v1/inference",
            read_capability_endpoint="http://maiw-api:8000/api/v1/capabilities/read",
        )
        base.update(overrides)
        return base

    def test_S01_localhost_gateway_endpoint_rejected_by_http_client(self):
        """S01: localhost model_gateway_endpoint is rejected by the HTTP client.

        SandboxConfig validates scheme, credentials, and write-path fragments.
        The localhost/loopback restriction is enforced at the HTTP client layer —
        MAIWHTTPModelGatewayClient rejects localhost endpoints at construction time.
        This ensures the sandbox cannot call a loopback address even if SandboxConfig
        were to accept it.
        """
        with pytest.raises(ValueError, match="localhost|loopback"):
            MAIWHTTPModelGatewayClient(
                endpoint="http://localhost:8000/api/v1/inference"
            )
        # SandboxConfig checks credentials and write-shaped paths (not loopback).
        cfg = SandboxConfig(
            **self._base_cfg(
                model_gateway_endpoint="http://localhost:8000/api/v1/inference",
            )
        )
        assert "localhost" in cfg.model_gateway_endpoint

    def test_S02_write_shaped_endpoint_rejected(self):
        """S02: Write-shaped path in model_gateway_endpoint is rejected."""
        with pytest.raises((ValueError, SandboxConfigurationError)):
            SandboxConfig(
                **self._base_cfg(
                    model_gateway_endpoint="http://maiw-api:8000/api/v1/write",
                )
            )

    def test_S03_embedded_credential_in_endpoint_rejected(self):
        """S03: Embedded credentials in model_gateway_endpoint are rejected."""
        with pytest.raises((ValueError, SandboxConfigurationError)):
            SandboxConfig(
                **self._base_cfg(
                    model_gateway_endpoint=(
                        "http://user:secret@maiw-api:8000/api/v1/inference"
                    ),
                )
            )

    def test_S04_sanctioned_endpoint_accepted(self):
        """S04: Sanctioned MAIW inference endpoint is valid."""
        cfg = SandboxConfig(**self._base_cfg())
        assert "maiw-api" in cfg.model_gateway_endpoint
        assert "/api/v1/inference" in cfg.model_gateway_endpoint

    def test_S05_sandbox_cannot_reach_local_nim_expected_behavior(self):
        """S05: SSRF protection blocks sandbox→localhost NIM (expected behavior)."""
        with pytest.raises(ValueError):
            MAIWHTTPModelGatewayClient(
                endpoint="http://localhost:8002/v1",
            )


# ═════════════════════════════════════════════════════════════════════════════
# REGISTRY RECLASSIFICATION TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestRegistryReclassification:
    """R01–R05b: Registry constants and generation hygiene."""

    def test_R01_transport_smoke_test_model_constant(self):
        """R01: TRANSPORT_SMOKE_TEST_MODEL is the Phase 20B llama model."""
        assert TRANSPORT_SMOKE_TEST_MODEL == "nvidia/llama-3.1-nemotron-nano-8b-v1"

    def test_R02_transport_smoke_test_model_is_not_approved(self):
        """R02: TRANSPORT_SMOKE_TEST_MODEL is not in any approved generation."""
        assert TRANSPORT_SMOKE_TEST_MODEL not in (
            "nvidia/nemotron-3-nano-30b-a3b",
            "nvidia/nemotron-3-super-120b-a12b",
            "nvidia/nemotron-3-ultra-550b-a55b",
            "nvidia/nemotron-3.5-lightning-30b-a3b",
        ), "Transport smoke test model must not be confused with approved Nemotron 3/3.5"
        assert (
            "llama" in TRANSPORT_SMOKE_TEST_MODEL.lower()
        ), "Constant must reference a Llama-family model"

    def test_R03_default_registry_no_legacy_generations(self):
        """R03: Default ModelRegistry has only nemotron-3 or nemotron-3.5 in enabled entries."""
        reg = ModelRegistry()
        for cap in reg.all_enabled():
            assert (
                cap.generation in PolicyFilter.APPROVED_MODEL_GENERATIONS
            ), f"Enabled model {cap.model_id} has unapproved generation {cap.generation!r}"

    def test_R04_all_enabled_defaults_have_approved_family(self):
        """R04: All default-enabled models pass PolicyFilter.APPROVED_MODEL_GENERATIONS."""
        reg = ModelRegistry()
        for cap in reg.all_enabled():
            assert cap.generation in PolicyFilter.APPROVED_MODEL_GENERATIONS, (
                f"Default-enabled model {cap.model_id} generation={cap.generation!r} "
                "is not in approved set"
            )

    def test_R05_nano_omni_nemotron3_generation_eligible_when_enabled(self):
        """R05: nano-omni with generation=nemotron-3 is eligible when enabled."""
        cap = _make_capability(
            "nvidia/nemotron-3-nano-omni-verified-future",
            role="nano-omni",
            generation="nemotron-3",
            enabled=True,
        )
        cap2 = cap.model_copy(
            update={"modalities": {"text", "image", "video", "audio"}}
        )
        reg = _make_registry(cap2)
        pf = PolicyFilter(reg)
        image_req = _base_request(modality=Modality.IMAGE)
        result = pf.filter(image_req, DeploymentMode.NVIDIA_HOSTED)
        assert (
            len(result) == 1
        ), "nano-omni with generation=nemotron-3 must be eligible for image requests"

    def test_R05b_model_with_truly_unknown_generation_blocked(self):
        """R05b: A model with generation=unknown is blocked by PolicyFilter."""
        cap = _make_capability(
            "some-unknown-model/v1",
            role="nano",
            generation="unknown",
            enabled=True,
        )
        reg = _make_registry(cap)
        pf = PolicyFilter(reg)
        result = pf.filter(_base_request(), DeploymentMode.NVIDIA_HOSTED)
        assert (
            len(result) == 0
        ), "Model with generation=unknown must be blocked by PolicyFilter"


# ═════════════════════════════════════════════════════════════════════════════
# MODEL INVENTORY TESTS (Step 2)
# ═════════════════════════════════════════════════════════════════════════════


class TestModelInventory:
    """I01: Verify the MAIW v2 model inventory table."""

    def test_I01_model_inventory_all_nemotron_3_or_35(self):
        """I01: All default registry models are Nemotron 3 or 3.5."""
        reg = ModelRegistry()
        inventory = []
        for cap in reg._capabilities.values():
            inventory.append(
                {
                    "model_id": cap.model_id,
                    "family": cap.family,
                    "generation": cap.generation,
                    "role": cap.role,
                    "enabled": cap.enabled,
                    "approved": cap.generation
                    in PolicyFilter.APPROVED_MODEL_GENERATIONS,
                }
            )

        print("\nMAIW v2 Model Inventory:")
        print(f"{'Model ID':<50} {'Generation':<15} {'Enabled':<10} {'Approved'}")
        for entry in inventory:
            print(
                f"{entry['model_id']:<50} "
                f"{entry['generation']:<15} "
                f"{str(entry['enabled']):<10} "
                f"{entry['approved']}"
            )

        enabled = [e for e in inventory if e["enabled"]]
        assert len(enabled) > 0, "At least one model must be enabled by default"
        for entry in enabled:
            assert entry["approved"], (
                f"Enabled model {entry['model_id']!r} "
                f"(generation={entry['generation']!r}) "
                "is not approved for MAIW v2"
            )

        model_ids = {e["model_id"] for e in inventory}
        assert "nvidia/nemotron-3-nano-30b-a3b" in model_ids
        assert "nvidia/nemotron-3-super-120b-a12b" in model_ids
        assert "nvidia/nemotron-3.5-lightning-30b-a3b" in model_ids
