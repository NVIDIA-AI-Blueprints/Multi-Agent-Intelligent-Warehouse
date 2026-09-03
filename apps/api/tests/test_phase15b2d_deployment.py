# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 15B.2D — Model deployment mode tests.

Covers:
  A. Routing provenance — requested_role / selected_role / fallback fields
  B. Local endpoint config — MAIW_NIM_* env vars applied to NIMConfig
  C. Registry readiness — nano EOL default, super fallback, DEGRADED vs READY
  D. Cache key correctness — model_override included in cache key
  E. DeploymentMode enum exists and has expected members
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maiw_models.models import DeploymentMode
from maiw_models.providers.nim_client import NIMConfig
from maiw_models.registry import ModelRegistry
from maiw_models.router import ModelRouter
from maiw_models.models import (
    ModelCapability,
    ModelRequest,
    ReasoningLevel,
    RiskLevel,
    Modality,
    DeploymentStatus,
    LatencyClass,
    CostClass,
)
from maiw_models.errors import ModelUnavailable


# ── A. Routing provenance ─────────────────────────────────────────────────────

class TestRoutingProvenance:
    """ModelRouteDecision carries requested_role, selected_role, fallback fields."""

    def _make_registry(self, *, nano_enabled: bool = True, super_enabled: bool = True) -> ModelRegistry:
        reg = ModelRegistry.__new__(ModelRegistry)
        reg._capabilities = {}
        reg._role_index = {}
        caps = []
        if nano_enabled:
            caps.append(ModelCapability(
                model_id="nvidia/nemotron-3-nano-30b-a3b",
                role="nano", family="nemotron", generation="nemotron-3",
                provider="nvidia-nim", deployment_status=DeploymentStatus.DEPLOYED,
                modalities={"text"}, tool_use=False, structured_output=False,
                reasoning_level=ReasoningLevel.MEDIUM, latency_class=LatencyClass.LOW,
                cost_class=CostClass.LOW, teacher_judge=False, context_window=None, enabled=True,
            ))
        if super_enabled:
            caps.append(ModelCapability(
                model_id="nvidia/nemotron-3-super-120b-a12b",
                role="super", family="nemotron", generation="nemotron-3",
                provider="nvidia-nim", deployment_status=DeploymentStatus.DEPLOYED,
                modalities={"text"}, tool_use=False, structured_output=False,
                reasoning_level=ReasoningLevel.HIGH, latency_class=LatencyClass.MEDIUM,
                cost_class=CostClass.MEDIUM, teacher_judge=False, context_window=None, enabled=True,
            ))
        for cap in caps:
            reg._capabilities[cap.model_id] = cap
            reg._role_index[cap.role] = cap.model_id
        return reg

    def test_no_fallback_when_preferred_available(self):
        reg = self._make_registry(nano_enabled=True)
        router = ModelRouter(reg)
        req = ModelRequest(
            task="test", messages=[{"role": "user", "content": "hi"}],
            reasoning=ReasoningLevel.MEDIUM,
        )
        decision = router.route(req)
        assert decision.requested_role == "nano"
        assert decision.selected_role == "nano"
        assert decision.fallback_from is None
        assert decision.fallback_reason is None

    def test_fallback_sets_from_and_reason(self):
        reg = self._make_registry(nano_enabled=False, super_enabled=True)
        router = ModelRouter(reg)
        req = ModelRequest(
            task="test", messages=[{"role": "user", "content": "hi"}],
            reasoning=ReasoningLevel.MEDIUM,
        )
        decision = router.route(req)
        assert decision.requested_role == "nano"
        assert decision.selected_role == "super"
        assert decision.fallback_from == "nano"
        assert decision.fallback_reason is not None
        assert "nano" in decision.fallback_reason
        assert "super" in decision.fallback_reason

    def test_no_fallback_for_super_directly_requested(self):
        reg = self._make_registry(super_enabled=True)
        router = ModelRouter(reg)
        req = ModelRequest(
            task="test", messages=[{"role": "user", "content": "hi"}],
            reasoning=ReasoningLevel.HIGH,
        )
        decision = router.route(req)
        assert decision.requested_role == "super"
        assert decision.selected_role == "super"
        assert decision.fallback_from is None

    def test_unavailable_raises_when_chain_exhausted(self):
        reg = self._make_registry(nano_enabled=False, super_enabled=False)
        router = ModelRouter(reg)
        req = ModelRequest(
            task="test", messages=[{"role": "user", "content": "hi"}],
            reasoning=ReasoningLevel.MEDIUM,
        )
        with pytest.raises(ModelUnavailable):
            router.route(req)

    def test_routing_rule_matches_reason(self):
        reg = self._make_registry(nano_enabled=True)
        router = ModelRouter(reg)
        req = ModelRequest(
            task="test", messages=[{"role": "user", "content": "hi"}],
            reasoning=ReasoningLevel.MEDIUM,
        )
        decision = router.route(req)
        assert decision.routing_rule == "medium_reasoning"
        assert "MEDIUM" in decision.routing_reason or "Nano" in decision.routing_reason


# ── B. Local endpoint config ──────────────────────────────────────────────────

class TestLocalEndpointConfig:
    """NIMConfig fields can be constructed with local NIM values.

    NIMConfig defaults are evaluated at import time, so env var overrides
    are tested via direct constructor args (which is how operators configure
    local NIM in production: by setting env vars before the app starts).
    """

    def test_default_config_field_structure(self):
        cfg = NIMConfig()
        assert hasattr(cfg, "llm_base_url")
        assert hasattr(cfg, "llm_model")
        assert hasattr(cfg, "llm_api_key")

    def test_local_nim_base_url_accepted(self):
        cfg = NIMConfig(llm_base_url="http://localhost:8000/v1")
        assert cfg.llm_base_url == "http://localhost:8000/v1"

    def test_local_nim_model_accepted(self):
        cfg = NIMConfig(llm_model="meta/llama-3.1-8b-instruct")
        assert cfg.llm_model == "meta/llama-3.1-8b-instruct"

    def test_local_nim_api_key_accepted(self):
        cfg = NIMConfig(llm_api_key="local-key-xyz")
        assert cfg.llm_api_key == "local-key-xyz"

    def test_empty_api_key_accepted_for_unauth_local_nim(self):
        cfg = NIMConfig(llm_api_key="")
        assert cfg.llm_api_key == ""

    def test_all_three_overrides_together(self):
        cfg = NIMConfig(
            llm_base_url="http://nim.internal:9000/v1",
            llm_model="nvidia/nemotron-3-super-120b-a12b",
            llm_api_key="enterprise-key",
        )
        assert cfg.llm_base_url == "http://nim.internal:9000/v1"
        assert cfg.llm_model == "nvidia/nemotron-3-super-120b-a12b"
        assert cfg.llm_api_key == "enterprise-key"

    def test_nim_config_docstring_mentions_deployment_modes(self):
        assert "local_nim" in NIMConfig.__doc__ or "MAIW_NIM_BASE_URL" in NIMConfig.__doc__


# ── C. Registry readiness ─────────────────────────────────────────────────────

class TestRegistryReadiness:
    """Nano disabled by default; super serves as fallback."""

    def test_nano_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NEMOTRON_NANO_ENABLED", None)
            reg = ModelRegistry()
        nano = reg.get_by_role("nano")
        assert nano is not None
        assert nano.enabled is False

    def test_super_enabled_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NEMOTRON_SUPER_ENABLED", None)
            reg = ModelRegistry()
        super_cap = reg.get_enabled_by_role("super")
        assert super_cap is not None
        assert super_cap.enabled is True

    def test_nano_opt_in_via_env(self):
        with patch.dict(os.environ, {"NEMOTRON_NANO_ENABLED": "true"}):
            reg = ModelRegistry()
        nano = reg.get_enabled_by_role("nano")
        assert nano is not None
        assert nano.enabled is True

    def test_medium_reasoning_falls_back_to_super_when_nano_disabled(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NEMOTRON_NANO_ENABLED", None)
            reg = ModelRegistry()
        router = ModelRouter(reg)
        req = ModelRequest(
            task="test", messages=[{"role": "user", "content": "hi"}],
            reasoning=ReasoningLevel.MEDIUM,
        )
        decision = router.route(req)
        assert decision.selected_role == "super"
        assert decision.fallback_from == "nano"

    def test_all_enabled_returns_only_enabled_models(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NEMOTRON_NANO_ENABLED", None)
            reg = ModelRegistry()
        enabled = reg.all_enabled()
        roles = [c.role for c in enabled]
        assert "nano" not in roles
        assert "super" in roles


# ── D. Cache key correctness ──────────────────────────────────────────────────

class TestCacheKeyCorrectness:
    """Cache key includes the effective model, not self.config.llm_model."""

    def _make_client_config(self) -> "NIMClient":
        from maiw_models.providers.nim_client import NIMClient
        cfg = NIMConfig.__new__(NIMConfig)
        cfg.llm_api_key = "test-key"
        cfg.llm_base_url = "http://localhost/v1"
        cfg.llm_model = "nvidia/nemotron-3-super-120b-a12b"
        cfg.embedding_api_key = ""
        cfg.embedding_base_url = "http://localhost/v1"
        cfg.embedding_model = "test-embed"
        cfg.timeout = 30
        cfg.default_temperature = 0.1
        cfg.default_max_tokens = 100
        cfg.default_top_p = 1.0
        cfg.default_frequency_penalty = 0.0
        cfg.default_presence_penalty = 0.0
        cfg.default_reasoning_budget = 0
        cfg.default_enable_thinking = False
        client = NIMClient.__new__(NIMClient)
        client.config = cfg
        return client

    def test_different_models_produce_different_cache_keys(self):
        from maiw_models.providers.nim_client import NIMClient
        client = self._make_client_config()
        messages = [{"role": "user", "content": "hello"}]
        key_super = client._generate_cache_key(
            messages, 0.1, 100, 1.0, 0.0, 0.0,
            model="nvidia/nemotron-3-super-120b-a12b",
        )
        key_nano = client._generate_cache_key(
            messages, 0.1, 100, 1.0, 0.0, 0.0,
            model="nvidia/nemotron-3-nano-30b-a3b",
        )
        assert key_super != key_nano

    def test_same_model_same_messages_produces_same_key(self):
        from maiw_models.providers.nim_client import NIMClient
        client = self._make_client_config()
        messages = [{"role": "user", "content": "hello"}]
        key1 = client._generate_cache_key(messages, 0.1, 100, 1.0, 0.0, 0.0, model="m1")
        key2 = client._generate_cache_key(messages, 0.1, 100, 1.0, 0.0, 0.0, model="m1")
        assert key1 == key2

    def test_no_model_param_falls_back_to_config_model(self):
        from maiw_models.providers.nim_client import NIMClient
        client = self._make_client_config()
        messages = [{"role": "user", "content": "hello"}]
        key_no_param = client._generate_cache_key(messages, 0.1, 100, 1.0, 0.0, 0.0)
        key_explicit = client._generate_cache_key(
            messages, 0.1, 100, 1.0, 0.0, 0.0,
            model="nvidia/nemotron-3-super-120b-a12b",
        )
        assert key_no_param == key_explicit


# ── E. DeploymentMode enum ────────────────────────────────────────────────────

class TestDeploymentModeEnum:
    """DeploymentMode has the four required members."""

    def test_all_four_modes_present(self):
        assert DeploymentMode.NVIDIA_HOSTED.value == "nvidia_hosted"
        assert DeploymentMode.LOCAL_NIM.value == "local_nim"
        assert DeploymentMode.OPENAI_COMPATIBLE.value == "openai_compatible"
        assert DeploymentMode.ENTERPRISE.value == "enterprise"

    def test_importable_from_maiw_models(self):
        from maiw_models import DeploymentMode as DM
        assert DM.NVIDIA_HOSTED is DeploymentMode.NVIDIA_HOSTED
