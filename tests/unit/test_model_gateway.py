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
Unit tests for ModelGateway — Phase 1 modernization.

All tests are synchronous (asyncio.run where async is needed) so they
run under the current pytest environment without pytest-asyncio version
constraints.  They cover:
  - ModelRegistry: registration, enabled/disabled, role lookup
  - ModelRouter: routing policy for all major cases, fallback chain
  - ModelGateway: end-to-end with mocked provider
  - NIMClient: model_override parameter
  - ForecastingAgent: uses model_gateway not nim_client directly
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.services.model_gateway.errors import ModelUnavailable
from src.api.services.model_gateway.models import (
    DeploymentStatus,
    LatencyClass,
    ModelCapability,
    ModelRequest,
    ModelRouteDecision,
    Modality,
    ReasoningLevel,
    RiskLevel,
)
from src.api.services.model_gateway.registry import ModelRegistry
from src.api.services.model_gateway.router import ModelRouter
from src.api.services.model_gateway.gateway import ModelGateway
from src.api.services.model_gateway.telemetry import GatewayTelemetry
from src.api.services.model_gateway.providers.nim import NIMProvider

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_registry(
    super_enabled: bool = True,
    nano_enabled: bool = False,
    lightning_enabled: bool = False,
    ultra_enabled: bool = False,
    nano_omni_enabled: bool = False,
) -> ModelRegistry:
    """Build a registry with deterministic env vars (no side effects on real env)."""
    env = {
        "NEMOTRON_SUPER_ENABLED": "true" if super_enabled else "false",
        "NEMOTRON_NANO_ENABLED": "true" if nano_enabled else "false",
        "NEMOTRON_LIGHTNING_ENABLED": "true" if lightning_enabled else "false",
        "NEMOTRON_ULTRA_ENABLED": "true" if ultra_enabled else "false",
        "NEMOTRON_NANO_OMNI_ENABLED": "true" if nano_omni_enabled else "false",
        # Use sentinel model IDs so tests don't depend on real NIM names
        "NEMOTRON_SUPER_MODEL": "test/super-model",
        "NEMOTRON_NANO_MODEL": "test/nano-model",
        "NEMOTRON_LIGHTNING_MODEL": "test/lightning-model",
        "NEMOTRON_ULTRA_MODEL": "test/ultra-model",
        "NEMOTRON_NANO_OMNI_MODEL": "test/nano-omni-model",
    }
    with patch.dict(os.environ, env):
        return ModelRegistry()


def _make_gateway(registry: ModelRegistry) -> tuple[ModelGateway, AsyncMock]:
    """Return a ModelGateway wired to a mock NIMProvider."""
    mock_provider = MagicMock(spec=NIMProvider)
    mock_provider.call = AsyncMock(
        return_value=MagicMock(
            content="mocked response",
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


# ── ModelRegistry tests ────────────────────────────────────────────────────────


class TestModelRegistry:
    def test_all_five_roles_registered(self):
        registry = _make_registry(
            super_enabled=True,
            nano_enabled=True,
            lightning_enabled=True,
            ultra_enabled=True,
            nano_omni_enabled=True,
        )
        assert set(registry.all_roles()) == {
            "super",
            "nano",
            "lightning",
            "ultra",
            "nano-omni",
        }

    def test_enabled_super_only(self):
        registry = _make_registry(super_enabled=True)
        enabled = registry.all_enabled()
        assert len(enabled) == 1
        assert enabled[0].role == "super"

    def test_disabled_model_not_in_all_enabled(self):
        registry = _make_registry(super_enabled=True, nano_enabled=False)
        enabled_roles = {c.role for c in registry.all_enabled()}
        assert "nano" not in enabled_roles

    def test_get_by_role_returns_capability(self):
        registry = _make_registry(super_enabled=True)
        cap = registry.get_by_role("super")
        assert cap is not None
        assert cap.role == "super"
        assert cap.model_id == "test/super-model"

    def test_get_enabled_by_role_none_when_disabled(self):
        registry = _make_registry(nano_enabled=False)
        assert registry.get_enabled_by_role("nano") is None

    def test_model_ids_come_from_env(self):
        registry = _make_registry(super_enabled=True)
        cap = registry.get_by_role("super")
        assert cap.model_id == "test/super-model"

    def test_nano_omni_has_multimodal_modalities(self):
        registry = _make_registry(nano_omni_enabled=True)
        cap = registry.get_by_role("nano-omni")
        assert "image" in cap.modalities
        assert "text" in cap.modalities

    def test_ultra_is_teacher_judge(self):
        registry = _make_registry(ultra_enabled=True)
        cap = registry.get_by_role("ultra")
        assert cap.teacher_judge is True

    def test_reload_picks_up_env_change(self):
        registry = _make_registry(super_enabled=False)
        assert registry.get_enabled_by_role("super") is None
        with patch.dict(
            os.environ,
            {
                "NEMOTRON_SUPER_ENABLED": "true",
                "NEMOTRON_SUPER_MODEL": "test/super-model",
            },
        ):
            registry.reload()
        assert registry.get_enabled_by_role("super") is not None


# ── ModelRouter tests ──────────────────────────────────────────────────────────


class TestModelRouter:
    def _router(self, **kwargs) -> ModelRouter:
        return ModelRouter(_make_registry(**kwargs))

    def test_low_reasoning_routes_to_lightning(self):
        router = self._router(lightning_enabled=True, super_enabled=True)
        decision = router.route(
            ModelRequest(
                task="warehouse.forecasting.parse",
                messages=[],
                reasoning=ReasoningLevel.LOW,
                risk_level=RiskLevel.LOW,
            )
        )
        assert decision.selected_role == "lightning"

    def test_medium_reasoning_routes_to_nano(self):
        router = self._router(nano_enabled=True, super_enabled=True)
        decision = router.route(
            ModelRequest(
                task="warehouse.operations.reason",
                messages=[],
                reasoning=ReasoningLevel.MEDIUM,
                risk_level=RiskLevel.LOW,
            )
        )
        assert decision.selected_role == "nano"

    def test_high_reasoning_routes_to_super(self):
        router = self._router(super_enabled=True)
        decision = router.route(
            ModelRequest(
                task="warehouse.wave_recovery",
                messages=[],
                reasoning=ReasoningLevel.HIGH,
                risk_level=RiskLevel.LOW,
            )
        )
        assert decision.selected_role == "super"

    def test_multimodal_routes_to_nano_omni(self):
        router = self._router(nano_omni_enabled=True, super_enabled=True)
        decision = router.route(
            ModelRequest(
                task="warehouse.perception.inspect_pallet",
                messages=[],
                reasoning=ReasoningLevel.LOW,
                risk_level=RiskLevel.LOW,
                modality=Modality.IMAGE,
            )
        )
        assert decision.selected_role == "nano-omni"

    def test_judge_task_routes_to_ultra(self):
        router = self._router(ultra_enabled=True, super_enabled=True)
        decision = router.route(
            ModelRequest(
                task="warehouse.eval.judge_trajectory",
                messages=[],
                reasoning=ReasoningLevel.MEDIUM,
                risk_level=RiskLevel.LOW,
            )
        )
        assert decision.selected_role == "ultra"

    def test_critical_risk_routes_to_super_minimum(self):
        router = self._router(super_enabled=True)
        decision = router.route(
            ModelRequest(
                task="warehouse.wave.reprioritize",
                messages=[],
                reasoning=ReasoningLevel.LOW,
                risk_level=RiskLevel.CRITICAL,
            )
        )
        assert decision.selected_role == "super"

    def test_fallback_lightning_to_nano_when_lightning_disabled(self):
        router = self._router(
            lightning_enabled=False, nano_enabled=True, super_enabled=True
        )
        decision = router.route(
            ModelRequest(
                task="warehouse.forecast.parse",
                messages=[],
                reasoning=ReasoningLevel.LOW,
                risk_level=RiskLevel.LOW,
            )
        )
        assert decision.selected_role == "nano"
        assert decision.fallback_from == "lightning"
        assert decision.fallback_reason is not None

    def test_fallback_nano_to_super_when_nano_disabled(self):
        router = self._router(nano_enabled=False, super_enabled=True)
        decision = router.route(
            ModelRequest(
                task="warehouse.operations.reason",
                messages=[],
                reasoning=ReasoningLevel.MEDIUM,
                risk_level=RiskLevel.LOW,
            )
        )
        assert decision.selected_role == "super"
        assert decision.fallback_from == "nano"

    def test_fallback_ultra_to_super(self):
        router = self._router(ultra_enabled=False, super_enabled=True)
        decision = router.route(
            ModelRequest(
                task="warehouse.eval.judge_trajectory",
                messages=[],
                reasoning=ReasoningLevel.HIGH,
                risk_level=RiskLevel.LOW,
            )
        )
        assert decision.selected_role == "super"
        assert decision.fallback_from == "ultra"

    def test_model_unavailable_when_all_disabled(self):
        router = ModelRouter(
            _make_registry(
                super_enabled=False,
                nano_enabled=False,
                lightning_enabled=False,
                ultra_enabled=False,
                nano_omni_enabled=False,
            )
        )
        with pytest.raises(ModelUnavailable):
            router.route(
                ModelRequest(
                    task="any.task",
                    messages=[],
                    reasoning=ReasoningLevel.LOW,
                    risk_level=RiskLevel.LOW,
                )
            )

    def test_route_decision_contains_task_and_reasoning(self):
        router = self._router(super_enabled=True)
        req = ModelRequest(
            task="warehouse.test.task",
            messages=[],
            reasoning=ReasoningLevel.HIGH,
            risk_level=RiskLevel.MEDIUM,
        )
        decision = router.route(req)
        assert decision.task == "warehouse.test.task"
        assert decision.requested_reasoning == ReasoningLevel.HIGH
        assert decision.requested_risk_level == RiskLevel.MEDIUM

    def test_no_fallback_when_preferred_available(self):
        router = self._router(super_enabled=True)
        decision = router.route(
            ModelRequest(
                task="t",
                messages=[],
                reasoning=ReasoningLevel.HIGH,
                risk_level=RiskLevel.LOW,
            )
        )
        assert decision.fallback_from is None
        assert decision.fallback_reason is None


# ── ModelGateway integration tests (mocked provider) ──────────────────────────


class TestModelGateway:
    def test_generate_returns_model_response(self):
        registry = _make_registry(super_enabled=True)
        gateway, mock_provider = _make_gateway(registry)

        response = asyncio.run(
            gateway.generate(
                ModelRequest(
                    task="warehouse.forecasting.generate_response",
                    messages=[{"role": "user", "content": "test"}],
                    reasoning=ReasoningLevel.MEDIUM,
                    risk_level=RiskLevel.LOW,
                )
            )
        )

        assert response.content == "mocked response"
        assert response.model_family == "nemotron"
        assert response.route_decision is not None
        assert response.latency_ms >= 0

    def test_route_decision_embedded_in_response(self):
        registry = _make_registry(super_enabled=True)
        gateway, _ = _make_gateway(registry)

        response = asyncio.run(
            gateway.generate(
                ModelRequest(
                    task="warehouse.test",
                    messages=[],
                    reasoning=ReasoningLevel.HIGH,
                    risk_level=RiskLevel.LOW,
                )
            )
        )

        assert response.route_decision.selected_role == "super"
        assert response.route_decision.task == "warehouse.test"

    def test_provider_called_with_correct_model_id(self):
        registry = _make_registry(super_enabled=True)
        gateway, mock_provider = _make_gateway(registry)

        asyncio.run(
            gateway.generate(
                ModelRequest(
                    task="warehouse.test",
                    messages=[{"role": "user", "content": "hello"}],
                    reasoning=ReasoningLevel.HIGH,
                    risk_level=RiskLevel.LOW,
                )
            )
        )

        mock_provider.call.assert_called_once()
        call_kwargs = mock_provider.call.call_args.kwargs
        assert call_kwargs["model_id"] == "test/super-model"

    def test_model_unavailable_propagates(self):
        registry = _make_registry(
            super_enabled=False,
            nano_enabled=False,
            lightning_enabled=False,
            ultra_enabled=False,
            nano_omni_enabled=False,
        )
        gateway, _ = _make_gateway(registry)

        with pytest.raises(ModelUnavailable):
            asyncio.run(
                gateway.generate(
                    ModelRequest(
                        task="t",
                        messages=[],
                        reasoning=ReasoningLevel.LOW,
                        risk_level=RiskLevel.LOW,
                    )
                )
            )

    def test_usage_included_in_response(self):
        registry = _make_registry(super_enabled=True)
        gateway, _ = _make_gateway(registry)

        response = asyncio.run(
            gateway.generate(
                ModelRequest(
                    task="t",
                    messages=[],
                    reasoning=ReasoningLevel.MEDIUM,
                    risk_level=RiskLevel.LOW,
                )
            )
        )
        assert response.usage.get("total_tokens") == 30


# ── NIMClient model_override tests ─────────────────────────────────────────────


class TestNIMClientModelOverride:
    def test_model_override_changes_payload_model(self):
        """model_override must be sent in the request payload, not self.config.llm_model."""
        from src.api.services.llm.nim_client import NIMClient, NIMConfig

        config = NIMConfig(
            llm_api_key="test-key",
            llm_model="nvidia/default-model",
        )
        client = NIMClient(config=config, enable_cache=False)

        captured_payload = {}

        async def fake_post(path, json=None, **kwargs):
            captured_payload.update(json or {})
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {},
                "model": "override/model",
            }
            return mock_resp

        client.llm_client.post = fake_post

        asyncio.run(
            client.generate_response(
                messages=[{"role": "user", "content": "hi"}],
                model_override="override/model",
            )
        )

        assert captured_payload.get("model") == "override/model"

    def test_no_model_override_uses_config_model(self):
        from src.api.services.llm.nim_client import NIMClient, NIMConfig

        config = NIMConfig(llm_api_key="test-key", llm_model="nvidia/config-model")
        client = NIMClient(config=config, enable_cache=False)

        captured_payload = {}

        async def fake_post(path, json=None, **kwargs):
            captured_payload.update(json or {})
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {},
                "model": "nvidia/config-model",
            }
            return mock_resp

        client.llm_client.post = fake_post

        asyncio.run(
            client.generate_response(
                messages=[{"role": "user", "content": "hi"}],
            )
        )

        assert captured_payload.get("model") == "nvidia/config-model"


# ── ForecastingAgent vertical slice ───────────────────────────────────────────


def _patch_missing_deps():
    """Inject stub modules so ForecastingAgent imports succeed without heavy deps."""
    import sys
    import types

    def _stub(name):
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)

    _stub("asyncpg")
    sys.modules["asyncpg"].create_pool = AsyncMock()

    _stub("redis")
    redis_asyncio = types.ModuleType("redis.asyncio")
    redis_asyncio.Redis = MagicMock
    sys.modules["redis.asyncio"] = redis_asyncio
    sys.modules["redis"].asyncio = redis_asyncio


class TestForecastingAgentGatewaySlice:
    def setup_method(self):
        _patch_missing_deps()

    def test_forecasting_agent_has_model_gateway_attribute(self):
        """Agent must declare model_gateway (not just nim_client)."""
        from src.api.agents.forecasting.forecasting_agent import ForecastingAgent

        agent = ForecastingAgent()
        assert hasattr(agent, "model_gateway")

    def test_forecasting_agent_gateway_none_before_init(self):
        from src.api.agents.forecasting.forecasting_agent import ForecastingAgent

        agent = ForecastingAgent()
        assert agent.model_gateway is None

    def test_forecasting_agent_uses_gateway_when_enabled(self):
        """When MODEL_GATEWAY_ENABLED=true, agent.nim_client must stay None after init."""
        from src.api.agents.forecasting.forecasting_agent import ForecastingAgent

        mock_gateway = MagicMock()
        mock_hybrid = AsyncMock()
        mock_tools = AsyncMock()
        mock_mcp = MagicMock()
        mock_discovery = MagicMock()
        mock_discovery.start_discovery = AsyncMock()
        mock_reasoning = AsyncMock()
        mock_config = MagicMock()
        mock_config.name = "forecasting"

        async def run():
            with patch.dict(os.environ, {"MODEL_GATEWAY_ENABLED": "true"}):
                with (
                    patch(
                        "src.api.agents.forecasting.forecasting_agent.get_model_gateway",
                        new=AsyncMock(return_value=mock_gateway),
                    ),
                    patch(
                        "src.api.agents.forecasting.forecasting_agent.get_nim_client",
                        new=AsyncMock(),
                    ),
                    patch(
                        "src.api.agents.forecasting.forecasting_agent.get_hybrid_retriever",
                        new=AsyncMock(return_value=mock_hybrid),
                    ),
                    patch(
                        "src.api.agents.forecasting.forecasting_agent.get_forecasting_action_tools",
                        new=AsyncMock(return_value=mock_tools),
                    ),
                    patch(
                        "src.api.agents.forecasting.forecasting_agent.MCPManager",
                        return_value=mock_mcp,
                    ),
                    patch(
                        "src.api.agents.forecasting.forecasting_agent.ToolDiscoveryService",
                        return_value=mock_discovery,
                    ),
                    patch(
                        "src.api.agents.forecasting.forecasting_agent.get_reasoning_engine",
                        new=AsyncMock(return_value=mock_reasoning),
                    ),
                    patch(
                        "src.api.agents.forecasting.forecasting_agent.load_agent_config",
                        return_value=mock_config,
                    ),
                ):
                    agent = ForecastingAgent()
                    await agent.initialize()
                    return agent

        agent = asyncio.run(run())
        assert agent.model_gateway is mock_gateway
        assert agent.nim_client is None  # legacy path must NOT be active

    def test_forecasting_agent_falls_back_to_nim_when_gateway_disabled(self):
        _patch_missing_deps()
        from src.api.agents.forecasting.forecasting_agent import ForecastingAgent

        mock_nim = MagicMock()
        mock_hybrid = AsyncMock()
        mock_tools = AsyncMock()
        mock_mcp = MagicMock()
        mock_discovery = MagicMock()
        mock_discovery.start_discovery = AsyncMock()
        mock_reasoning = AsyncMock()
        mock_config = MagicMock()
        mock_config.name = "forecasting"

        async def run():
            with patch.dict(os.environ, {"MODEL_GATEWAY_ENABLED": "false"}):
                with (
                    patch(
                        "src.api.agents.forecasting.forecasting_agent.get_nim_client",
                        new=AsyncMock(return_value=mock_nim),
                    ),
                    patch(
                        "src.api.agents.forecasting.forecasting_agent.get_hybrid_retriever",
                        new=AsyncMock(return_value=mock_hybrid),
                    ),
                    patch(
                        "src.api.agents.forecasting.forecasting_agent.get_forecasting_action_tools",
                        new=AsyncMock(return_value=mock_tools),
                    ),
                    patch(
                        "src.api.agents.forecasting.forecasting_agent.MCPManager",
                        return_value=mock_mcp,
                    ),
                    patch(
                        "src.api.agents.forecasting.forecasting_agent.ToolDiscoveryService",
                        return_value=mock_discovery,
                    ),
                    patch(
                        "src.api.agents.forecasting.forecasting_agent.get_reasoning_engine",
                        new=AsyncMock(return_value=mock_reasoning),
                    ),
                    patch(
                        "src.api.agents.forecasting.forecasting_agent.load_agent_config",
                        return_value=mock_config,
                    ),
                ):
                    agent = ForecastingAgent()
                    await agent.initialize()
                    return agent

        agent = asyncio.run(run())
        assert agent.nim_client is mock_nim
        assert agent.model_gateway is None  # gateway must NOT be active


# ── Feature flag ───────────────────────────────────────────────────────────────


class TestFeatureFlag:
    def test_gateway_enabled_by_default(self):
        from src.api.services.model_gateway import is_model_gateway_enabled

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MODEL_GATEWAY_ENABLED", None)
            assert is_model_gateway_enabled() is True

    def test_gateway_disabled_by_env(self):
        from src.api.services.model_gateway import is_model_gateway_enabled

        with patch.dict(os.environ, {"MODEL_GATEWAY_ENABLED": "false"}):
            assert is_model_gateway_enabled() is False

    def test_gateway_enabled_explicitly(self):
        from src.api.services.model_gateway import is_model_gateway_enabled

        with patch.dict(os.environ, {"MODEL_GATEWAY_ENABLED": "true"}):
            assert is_model_gateway_enabled() is True


# ── Singleton / reset ──────────────────────────────────────────────────────────


class TestGatewaySingleton:
    def test_reset_clears_singleton(self):
        from src.api.services.model_gateway import (
            reset_model_gateway,
            _gateway_instance,
        )
        import src.api.services.model_gateway as gw_module

        gw_module._gateway_instance = MagicMock()  # inject a fake instance
        reset_model_gateway()
        assert gw_module._gateway_instance is None


# ── Phase 1B: ModelCapability fields ──────────────────────────────────────────


class TestModelCapabilityFields:
    """Verify Phase 1B/1C additions to ModelCapability."""

    # ── Generation labels (Nemotron 3 / 3.5) ──────────────────────────────────

    def test_lightning_has_nemotron_35_generation(self):
        registry = _make_registry(lightning_enabled=True)
        cap = registry.get_by_role("lightning")
        assert cap.generation == "nemotron-3.5"

    def test_super_has_nemotron_3_generation(self):
        registry = _make_registry(super_enabled=True)
        cap = registry.get_by_role("super")
        assert cap.generation == "nemotron-3"

    def test_nano_has_nemotron_3_generation(self):
        registry = _make_registry(nano_enabled=True)
        cap = registry.get_by_role("nano")
        assert cap.generation == "nemotron-3"

    def test_ultra_has_nemotron_3_generation(self):
        registry = _make_registry(ultra_enabled=True)
        cap = registry.get_by_role("ultra")
        assert cap.generation == "nemotron-3"

    def test_nano_omni_generation_unknown_until_model_verified(self):
        """Nano Omni generation must remain 'unknown' until a real model is validated."""
        registry = _make_registry(nano_omni_enabled=True)
        cap = registry.get_by_role("nano-omni")
        assert cap.generation == "unknown"

    # ── DeploymentStatus (endpoint-validated 2026-08-20) ──────────────────────

    def test_lightning_deployment_status_deployed(self):
        registry = _make_registry(lightning_enabled=True)
        assert (
            registry.get_by_role("lightning").deployment_status
            == DeploymentStatus.DEPLOYED
        )

    def test_nano_deployment_status_deployed(self):
        registry = _make_registry(nano_enabled=True)
        assert (
            registry.get_by_role("nano").deployment_status == DeploymentStatus.DEPLOYED
        )

    def test_super_deployment_status_deployed(self):
        registry = _make_registry(super_enabled=True)
        assert (
            registry.get_by_role("super").deployment_status == DeploymentStatus.DEPLOYED
        )

    def test_ultra_deployment_status_deployed(self):
        registry = _make_registry(ultra_enabled=True)
        assert (
            registry.get_by_role("ultra").deployment_status == DeploymentStatus.DEPLOYED
        )

    def test_nano_omni_deployment_status_not_currently_deployed(self):
        """No verified Nemotron-3 Nano Omni model ID on NIM as of 2026-08-20."""
        registry = _make_registry(nano_omni_enabled=True)
        assert (
            registry.get_by_role("nano-omni").deployment_status
            == DeploymentStatus.NOT_CURRENTLY_DEPLOYED
        )

    # ── Tool use (endpoint-validated 2026-08-20) ───────────────────────────────

    def test_lightning_tool_use_confirmed_true(self):
        """Lightning forced tool_choice=function succeeded in endpoint test."""
        registry = _make_registry(lightning_enabled=True)
        assert registry.get_by_role("lightning").tool_use is True

    def test_nano_tool_use_confirmed_false(self):
        """Nano forced tool_choice returned plain text, not a tool call."""
        registry = _make_registry(nano_enabled=True)
        assert registry.get_by_role("nano").tool_use is False

    def test_super_tool_use_confirmed_false(self):
        """Super forced tool_choice returned plain text, not a tool call."""
        registry = _make_registry(super_enabled=True)
        assert registry.get_by_role("super").tool_use is False

    # ── Structured output (conservative until confirmed) ───────────────────────

    def test_all_roles_structured_output_false_until_confirmed(self):
        """JSON mode returned thinking traces, not pure JSON — not yet confirmed."""
        for role, kw in [
            ("lightning", {"lightning_enabled": True}),
            ("nano", {"nano_enabled": True}),
            ("super", {"super_enabled": True}),
            ("ultra", {"ultra_enabled": True}),
        ]:
            cap = _make_registry(**kw).get_by_role(role)
            assert (
                cap.structured_output is False
            ), f"{role}.structured_output must be False until confirmed"

    # ── Enabled defaults ───────────────────────────────────────────────────────

    def test_lightning_and_nano_and_super_enabled_by_default(self):
        """Phase 1C: Lightning, Nano, Super are all validated DEPLOYED → enabled by default."""
        env = {
            "NEMOTRON_LIGHTNING_MODEL": "test/lightning",
            "NEMOTRON_NANO_MODEL": "test/nano",
            "NEMOTRON_SUPER_MODEL": "test/super",
            "NEMOTRON_ULTRA_MODEL": "test/ultra",
            "NEMOTRON_NANO_OMNI_MODEL": "test/nano-omni",
        }
        # Unset all _ENABLED env vars so registry falls through to _ENABLED_DEFAULTS
        for key in [
            "NEMOTRON_LIGHTNING_ENABLED",
            "NEMOTRON_NANO_ENABLED",
            "NEMOTRON_SUPER_ENABLED",
            "NEMOTRON_ULTRA_ENABLED",
            "NEMOTRON_NANO_OMNI_ENABLED",
        ]:
            env.pop(key, None)
        with patch.dict(os.environ, env, clear=False):
            for key in [
                "NEMOTRON_LIGHTNING_ENABLED",
                "NEMOTRON_NANO_ENABLED",
                "NEMOTRON_SUPER_ENABLED",
                "NEMOTRON_ULTRA_ENABLED",
                "NEMOTRON_NANO_OMNI_ENABLED",
            ]:
                os.environ.pop(key, None)
            registry = ModelRegistry()
        enabled = {c.role for c in registry.all_enabled()}
        assert "lightning" in enabled, "Lightning must be enabled by default"
        assert "nano" in enabled, "Nano must be enabled by default"
        assert "super" in enabled, "Super must be enabled by default"

    def test_ultra_disabled_by_default(self):
        """Ultra has ~31s latency — requires explicit operator opt-in."""
        env = {
            "NEMOTRON_LIGHTNING_MODEL": "test/lightning",
            "NEMOTRON_NANO_MODEL": "test/nano",
            "NEMOTRON_SUPER_MODEL": "test/super",
            "NEMOTRON_ULTRA_MODEL": "test/ultra",
            "NEMOTRON_NANO_OMNI_MODEL": "test/nano-omni",
        }
        with patch.dict(os.environ, env, clear=False):
            for key in [
                "NEMOTRON_LIGHTNING_ENABLED",
                "NEMOTRON_NANO_ENABLED",
                "NEMOTRON_SUPER_ENABLED",
                "NEMOTRON_ULTRA_ENABLED",
                "NEMOTRON_NANO_OMNI_ENABLED",
            ]:
                os.environ.pop(key, None)
            registry = ModelRegistry()
        assert (
            registry.get_enabled_by_role("ultra") is None
        ), "Ultra must be disabled by default"

    def test_nano_omni_disabled_by_default_no_model_configured(self):
        """Nano Omni is NOT_CURRENTLY_DEPLOYED — disabled unless operator configures a model."""
        env = {
            "NEMOTRON_LIGHTNING_MODEL": "test/lightning",
            "NEMOTRON_NANO_MODEL": "test/nano",
            "NEMOTRON_SUPER_MODEL": "test/super",
            "NEMOTRON_ULTRA_MODEL": "test/ultra",
        }
        with patch.dict(os.environ, env, clear=False):
            for key in [
                "NEMOTRON_LIGHTNING_ENABLED",
                "NEMOTRON_NANO_ENABLED",
                "NEMOTRON_SUPER_ENABLED",
                "NEMOTRON_ULTRA_ENABLED",
                "NEMOTRON_NANO_OMNI_ENABLED",
                "NEMOTRON_NANO_OMNI_MODEL",
            ]:
                os.environ.pop(key, None)
            registry = ModelRegistry()
        assert registry.get_enabled_by_role("nano-omni") is None

    # ── Nano Omni sentinel guard ───────────────────────────────────────────────

    def test_nano_omni_sentinel_guard_auto_disables_when_no_model_configured(self):
        """When Nano Omni is enabled but model is sentinel → auto-disable with error log."""
        with patch.dict(
            os.environ,
            {
                "NEMOTRON_NANO_OMNI_ENABLED": "true",
                "NEMOTRON_NANO_OMNI_MODEL": "OPERATOR_MUST_CONFIGURE_NEMOTRON_NANO_OMNI_MODEL",
            },
        ):
            registry = ModelRegistry()
            assert registry.get_enabled_by_role("nano-omni") is None

    def test_nano_omni_sentinel_guard_with_env_unset(self):
        """Nano Omni enabled=true but no model env var → falls to sentinel → auto-disable."""
        with patch.dict(
            os.environ, {"NEMOTRON_NANO_OMNI_ENABLED": "true"}, clear=False
        ):
            os.environ.pop("NEMOTRON_NANO_OMNI_MODEL", None)
            registry = ModelRegistry()
            assert registry.get_enabled_by_role("nano-omni") is None

    # ── Other capability fields ────────────────────────────────────────────────

    def test_context_window_none_until_confirmed(self):
        """Context window is not confirmed from documentation — must remain None."""
        registry = _make_registry(super_enabled=True)
        assert registry.get_by_role("super").context_window is None

    def test_capability_has_family_field(self):
        registry = _make_registry(super_enabled=True)
        assert registry.get_by_role("super").family == "nemotron"

    def test_capability_has_provider_field(self):
        registry = _make_registry(super_enabled=True)
        assert registry.get_by_role("super").provider == "nvidia-nim"


# ── Phase 1C: Default model IDs ───────────────────────────────────────────────


class TestDefaultModelIds:
    """Verify that default model IDs are Nemotron 3 / 3.5 (not legacy llama-nemotron)."""

    def _default_registry(self) -> ModelRegistry:
        """Registry constructed with only model IDs fixed to sentinels; enabled flags default."""
        env = {
            "NEMOTRON_LIGHTNING_MODEL": "test/lightning",
            "NEMOTRON_NANO_MODEL": "test/nano",
            "NEMOTRON_SUPER_MODEL": "test/super",
            "NEMOTRON_ULTRA_MODEL": "test/ultra",
            "NEMOTRON_NANO_OMNI_MODEL": "test/nano-omni",
            "NEMOTRON_LIGHTNING_ENABLED": "true",
            "NEMOTRON_NANO_ENABLED": "true",
            "NEMOTRON_SUPER_ENABLED": "true",
            "NEMOTRON_ULTRA_ENABLED": "true",
            "NEMOTRON_NANO_OMNI_ENABLED": "true",
        }
        with patch.dict(os.environ, env):
            return ModelRegistry()

    def _real_default_registry(self) -> ModelRegistry:
        """Registry with NO model env overrides — reads hard-coded _DEFAULTS."""
        keys_to_clear = [
            "NEMOTRON_LIGHTNING_MODEL",
            "NEMOTRON_NANO_MODEL",
            "NEMOTRON_SUPER_MODEL",
            "NEMOTRON_ULTRA_MODEL",
            "NEMOTRON_NANO_OMNI_MODEL",
            "NEMOTRON_LIGHTNING_ENABLED",
            "NEMOTRON_NANO_ENABLED",
            "NEMOTRON_SUPER_ENABLED",
            "NEMOTRON_ULTRA_ENABLED",
            "NEMOTRON_NANO_OMNI_ENABLED",
        ]
        env_patch = {
            k: "" for k in keys_to_clear
        }  # placeholder so patch.dict tracks them
        with patch.dict(os.environ, {}, clear=False):
            for k in keys_to_clear:
                os.environ.pop(k, None)
            return ModelRegistry()

    def test_default_lightning_model_is_nemotron35(self):
        registry = self._real_default_registry()
        cap = registry.get_by_role("lightning")
        assert cap.model_id == "nvidia/nemotron-3.5-lightning-30b-a3b"

    def test_default_nano_model_is_nemotron3(self):
        registry = self._real_default_registry()
        cap = registry.get_by_role("nano")
        assert cap.model_id == "nvidia/nemotron-3-nano-30b-a3b"

    def test_default_super_model_is_nemotron3(self):
        registry = self._real_default_registry()
        cap = registry.get_by_role("super")
        assert cap.model_id == "nvidia/nemotron-3-super-120b-a12b"

    def test_default_ultra_model_is_nemotron3(self):
        registry = self._real_default_registry()
        cap = registry.get_by_role("ultra")
        assert cap.model_id == "nvidia/nemotron-3-ultra-550b-a55b"

    def test_no_legacy_llama_nemotron_in_defaults(self):
        """None of the legacy llama-nemotron model IDs must appear as defaults."""
        registry = self._real_default_registry()
        legacy_prefixes = ("llama-3.3-nemotron", "llama-3.1-nemotron", "llama-nemotron")
        for cap in registry._capabilities.values():
            for prefix in legacy_prefixes:
                assert (
                    prefix not in cap.model_id
                ), f"Legacy model ID found in role={cap.role}: {cap.model_id}"

    def test_moe_suffix_in_nemotron3_model_ids(self):
        """Nemotron 3 MoE models have active-param suffix (a3b, a12b, a55b)."""
        registry = self._real_default_registry()
        for role, expected_suffix in [
            ("lightning", "a3b"),
            ("nano", "a3b"),
            ("super", "a12b"),
            ("ultra", "a55b"),
        ]:
            cap = registry.get_by_role(role)
            assert (
                expected_suffix in cap.model_id
            ), f"{role}: expected '{expected_suffix}' suffix in model_id={cap.model_id}"


# ── Phase 1B: ModelRouteDecision fields ───────────────────────────────────────


class TestRouteDecisionFields:
    """Verify requested_role and routing_rule are populated correctly."""

    def _router(self, **kwargs) -> ModelRouter:
        return ModelRouter(_make_registry(**kwargs))

    def test_requested_role_matches_preferred_when_no_fallback(self):
        router = self._router(super_enabled=True)
        decision = router.route(
            ModelRequest(
                task="t",
                messages=[],
                reasoning=ReasoningLevel.HIGH,
                risk_level=RiskLevel.LOW,
            )
        )
        assert decision.requested_role == "super"
        assert decision.selected_role == "super"
        assert decision.fallback_from is None

    def test_requested_role_differs_from_selected_on_fallback(self):
        router = self._router(nano_enabled=False, super_enabled=True)
        decision = router.route(
            ModelRequest(
                task="t",
                messages=[],
                reasoning=ReasoningLevel.MEDIUM,
                risk_level=RiskLevel.LOW,
            )
        )
        assert decision.requested_role == "nano"
        assert decision.selected_role == "super"
        assert decision.fallback_from == "nano"

    def test_routing_rule_low_reasoning(self):
        router = self._router(lightning_enabled=True, super_enabled=True)
        decision = router.route(
            ModelRequest(
                task="t",
                messages=[],
                reasoning=ReasoningLevel.LOW,
                risk_level=RiskLevel.LOW,
            )
        )
        assert decision.routing_rule == "low_reasoning"

    def test_routing_rule_medium_reasoning(self):
        router = self._router(nano_enabled=True, super_enabled=True)
        decision = router.route(
            ModelRequest(
                task="t",
                messages=[],
                reasoning=ReasoningLevel.MEDIUM,
                risk_level=RiskLevel.LOW,
            )
        )
        assert decision.routing_rule == "medium_reasoning"

    def test_routing_rule_high_reasoning(self):
        router = self._router(super_enabled=True)
        decision = router.route(
            ModelRequest(
                task="t",
                messages=[],
                reasoning=ReasoningLevel.HIGH,
                risk_level=RiskLevel.LOW,
            )
        )
        assert decision.routing_rule == "high_reasoning"

    def test_routing_rule_critical_risk(self):
        router = self._router(super_enabled=True)
        decision = router.route(
            ModelRequest(
                task="t",
                messages=[],
                reasoning=ReasoningLevel.LOW,
                risk_level=RiskLevel.CRITICAL,
            )
        )
        assert decision.routing_rule == "critical_risk"
        assert decision.selected_role == "super"

    def test_routing_rule_judge_task(self):
        router = self._router(ultra_enabled=True, super_enabled=True)
        decision = router.route(
            ModelRequest(
                task="warehouse.eval.judge_trajectory",
                messages=[],
                reasoning=ReasoningLevel.LOW,
                risk_level=RiskLevel.LOW,
            )
        )
        assert decision.routing_rule == "judge_task"
        assert decision.selected_role == "ultra"

    def test_routing_rule_multimodal_input(self):
        router = self._router(nano_omni_enabled=True, super_enabled=True)
        decision = router.route(
            ModelRequest(
                task="t",
                messages=[],
                reasoning=ReasoningLevel.LOW,
                risk_level=RiskLevel.LOW,
                modality=Modality.IMAGE,
            )
        )
        assert decision.routing_rule == "multimodal_input"
        assert decision.selected_role == "nano-omni"

    def test_routing_reason_is_human_readable(self):
        router = self._router(super_enabled=True)
        decision = router.route(
            ModelRequest(
                task="t",
                messages=[],
                reasoning=ReasoningLevel.HIGH,
                risk_level=RiskLevel.LOW,
            )
        )
        assert len(decision.routing_reason) > 5
        assert (
            "Super" in decision.routing_reason
            or "super" in decision.routing_reason.lower()
        )

    def test_telemetry_fields_consistent(self):
        """routing_reason must describe the requested_role, not the fallback."""
        router = self._router(nano_enabled=False, super_enabled=True)
        decision = router.route(
            ModelRequest(
                task="t",
                messages=[],
                reasoning=ReasoningLevel.MEDIUM,
                risk_level=RiskLevel.LOW,
            )
        )
        # The routing_reason describes WHY nano was the preferred choice,
        # not why super was selected as fallback.
        assert (
            "nano" in decision.routing_reason.lower()
            or "medium" in decision.routing_reason.lower()
        )
        # The fallback fields explain the actual deviation.
        assert decision.fallback_from == "nano"
        assert decision.fallback_reason is not None


# ── Phase 1B: Routing Matrix — representative warehouse workloads ──────────────


import pytest


@pytest.mark.parametrize(
    "label,task,reasoning,risk,modality,expected_role,expect_fallback",
    [
        # Forecasting
        (
            "forecast.summarize",
            "warehouse.forecasting.summarize_demand",
            ReasoningLevel.LOW,
            RiskLevel.LOW,
            Modality.TEXT,
            "lightning",
            False,
        ),
        (
            "forecast.anomaly",
            "warehouse.forecasting.analyze_anomaly",
            ReasoningLevel.MEDIUM,
            RiskLevel.LOW,
            Modality.TEXT,
            "nano",
            False,
        ),
        # Operations
        (
            "ops.state",
            "warehouse.operations.summarize_state",
            ReasoningLevel.LOW,
            RiskLevel.LOW,
            Modality.TEXT,
            "lightning",
            False,
        ),
        (
            "ops.wave_recovery",
            "warehouse.operations.recover_wave",
            ReasoningLevel.HIGH,
            RiskLevel.HIGH,
            Modality.TEXT,
            "super",
            False,
        ),
        # Equipment
        (
            "equip.health",
            "warehouse.equipment.summarize_health",
            ReasoningLevel.LOW,
            RiskLevel.LOW,
            Modality.TEXT,
            "lightning",
            False,
        ),
        (
            "equip.failure",
            "warehouse.equipment.diagnose_failure",
            ReasoningLevel.HIGH,
            RiskLevel.HIGH,
            Modality.TEXT,
            "super",
            False,
        ),
        # Safety
        (
            "safety.event_summary",
            "warehouse.safety.summarize_event",
            ReasoningLevel.MEDIUM,
            RiskLevel.MEDIUM,
            Modality.TEXT,
            "nano",
            False,
        ),
        (
            "safety.broadcast",
            "warehouse.safety.broadcast_alert",
            ReasoningLevel.HIGH,
            RiskLevel.CRITICAL,
            Modality.TEXT,
            "super",
            False,
        ),
        # Documents
        (
            "doc.text",
            "warehouse.documents.summarize_text",
            ReasoningLevel.LOW,
            RiskLevel.LOW,
            Modality.TEXT,
            "lightning",
            False,
        ),
        (
            "doc.image",
            "warehouse.documents.inspect_image",
            ReasoningLevel.MEDIUM,
            RiskLevel.LOW,
            Modality.IMAGE,
            "nano-omni",
            False,
        ),
        # Eval
        (
            "eval.judge",
            "warehouse.eval.judge_trajectory",
            ReasoningLevel.HIGH,
            RiskLevel.LOW,
            Modality.TEXT,
            "ultra",
            False,
        ),
    ],
)
class TestRoutingMatrix:
    def _registry_all_enabled(self) -> ModelRegistry:
        env = {
            "NEMOTRON_LIGHTNING_ENABLED": "true",
            "NEMOTRON_NANO_ENABLED": "true",
            "NEMOTRON_SUPER_ENABLED": "true",
            "NEMOTRON_ULTRA_ENABLED": "true",
            "NEMOTRON_NANO_OMNI_ENABLED": "true",
            "NEMOTRON_LIGHTNING_MODEL": "test/lightning",
            "NEMOTRON_NANO_MODEL": "test/nano",
            "NEMOTRON_SUPER_MODEL": "test/super",
            "NEMOTRON_ULTRA_MODEL": "test/ultra",
            "NEMOTRON_NANO_OMNI_MODEL": "test/nano-omni",
        }
        with patch.dict(os.environ, env):
            return ModelRegistry()

    def test_routes_to_expected_role(
        self, label, task, reasoning, risk, modality, expected_role, expect_fallback
    ):
        registry = self._registry_all_enabled()
        router = ModelRouter(registry)
        decision = router.route(
            ModelRequest(
                task=task,
                messages=[],
                reasoning=reasoning,
                risk_level=risk,
                modality=modality,
            )
        )
        assert decision.selected_role == expected_role, (
            f"{label}: expected role={expected_role}, got role={decision.selected_role} "
            f"(rule={decision.routing_rule}, reason={decision.routing_reason})"
        )

    def test_fallback_behavior_correct(
        self, label, task, reasoning, risk, modality, expected_role, expect_fallback
    ):
        registry = self._registry_all_enabled()
        router = ModelRouter(registry)
        decision = router.route(
            ModelRequest(
                task=task,
                messages=[],
                reasoning=reasoning,
                risk_level=risk,
                modality=modality,
            )
        )
        if expect_fallback:
            assert decision.fallback_from is not None
        else:
            assert (
                decision.fallback_from is None
            ), f"{label}: unexpected fallback_from={decision.fallback_from}"

    def test_requested_role_recorded(
        self, label, task, reasoning, risk, modality, expected_role, expect_fallback
    ):
        registry = self._registry_all_enabled()
        router = ModelRouter(registry)
        decision = router.route(
            ModelRequest(
                task=task,
                messages=[],
                reasoning=reasoning,
                risk_level=risk,
                modality=modality,
            )
        )
        # requested_role must always be set (never None or empty)
        assert decision.requested_role, f"{label}: requested_role is empty"
        assert decision.routing_rule, f"{label}: routing_rule is empty"


# ── Phase 1B: Fallback coverage in routing matrix ─────────────────────────────


class TestRoutingMatrixFallbacks:
    """Verify fallback path produces correct requested_role vs selected_role."""

    def _router_super_only(self) -> ModelRouter:
        return ModelRouter(_make_registry(super_enabled=True))

    def test_low_reasoning_falls_back_to_super_when_all_small_disabled(self):
        router = self._router_super_only()
        decision = router.route(
            ModelRequest(
                task="warehouse.forecasting.parse",
                messages=[],
                reasoning=ReasoningLevel.LOW,
                risk_level=RiskLevel.LOW,
            )
        )
        assert decision.requested_role == "lightning"
        assert decision.selected_role == "super"
        assert decision.fallback_from == "lightning"
        assert decision.routing_rule == "low_reasoning"

    def test_medium_reasoning_falls_back_to_super_when_nano_disabled(self):
        router = self._router_super_only()
        decision = router.route(
            ModelRequest(
                task="warehouse.operations.state",
                messages=[],
                reasoning=ReasoningLevel.MEDIUM,
                risk_level=RiskLevel.LOW,
            )
        )
        assert decision.requested_role == "nano"
        assert decision.selected_role == "super"
        assert decision.routing_rule == "medium_reasoning"

    def test_ultra_falls_back_to_super(self):
        router = self._router_super_only()
        decision = router.route(
            ModelRequest(
                task="warehouse.eval.judge_quality",
                messages=[],
                reasoning=ReasoningLevel.HIGH,
                risk_level=RiskLevel.LOW,
            )
        )
        assert decision.requested_role == "ultra"
        assert decision.selected_role == "super"
        assert decision.routing_rule == "judge_task"
        assert decision.fallback_from == "ultra"

    def test_nano_omni_falls_back_to_super(self):
        router = self._router_super_only()
        decision = router.route(
            ModelRequest(
                task="warehouse.documents.inspect_image",
                messages=[],
                reasoning=ReasoningLevel.MEDIUM,
                risk_level=RiskLevel.LOW,
                modality=Modality.IMAGE,
            )
        )
        assert decision.requested_role == "nano-omni"
        assert decision.selected_role == "super"
        assert decision.routing_rule == "multimodal_input"
        assert decision.fallback_from == "nano-omni"


# ── Phase 1B: OperationsAgent gateway migration ───────────────────────────────


def _patch_missing_deps_for_ops():
    """Stub all heavy deps that block import of operations_agent."""
    import sys
    import types

    for name in ["asyncpg", "redis", "redis.asyncio"]:
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)
    sys.modules["redis"].asyncio = sys.modules["redis.asyncio"]
    sys.modules["redis.asyncio"].Redis = MagicMock


class TestOperationsAgentGatewaySlice:
    def setup_method(self):
        _patch_missing_deps_for_ops()

    def test_operations_agent_has_model_gateway_attr(self):
        from src.api.agents.operations.operations_agent import (
            OperationsCoordinationAgent,
        )

        agent = OperationsCoordinationAgent()
        assert hasattr(agent, "model_gateway")
        assert agent.model_gateway is None

    def test_operations_agent_uses_gateway_when_enabled(self):
        from src.api.agents.operations.operations_agent import (
            OperationsCoordinationAgent,
        )

        mock_gateway = MagicMock()
        mock_hybrid = AsyncMock()
        mock_tools = AsyncMock()
        mock_task_queries = MagicMock()
        mock_telemetry_queries = MagicMock()
        mock_sql = MagicMock()
        mock_config = MagicMock()
        mock_config.name = "operations"

        async def run():
            with patch.dict(os.environ, {"MODEL_GATEWAY_ENABLED": "true"}):
                with (
                    patch(
                        "src.api.agents.operations.operations_agent.get_model_gateway",
                        new=AsyncMock(return_value=mock_gateway),
                    ),
                    patch(
                        "src.api.agents.operations.operations_agent.get_hybrid_retriever",
                        new=AsyncMock(return_value=mock_hybrid),
                    ),
                    patch(
                        "src.api.agents.operations.operations_agent.get_operations_action_tools",
                        new=AsyncMock(return_value=mock_tools),
                    ),
                    patch(
                        "src.api.agents.operations.operations_agent.load_agent_config",
                        return_value=mock_config,
                    ),
                    patch(
                        "src.retrieval.structured.sql_retriever.get_sql_retriever",
                        new=AsyncMock(return_value=mock_sql),
                    ),
                ):
                    agent = OperationsCoordinationAgent()
                    await agent.initialize()
                    return agent

        agent = asyncio.run(run())
        assert agent.model_gateway is mock_gateway
        assert agent.nim_client is None


# ── Phase 1B: EquipmentAgent gateway migration ────────────────────────────────


class TestEquipmentAgentGatewaySlice:
    def setup_method(self):
        _patch_missing_deps_for_ops()

    def test_equipment_agent_has_model_gateway_attr(self):
        from src.api.agents.inventory.equipment_agent import (
            EquipmentAssetOperationsAgent,
        )

        agent = EquipmentAssetOperationsAgent()
        assert hasattr(agent, "model_gateway")
        assert agent.model_gateway is None

    def test_equipment_agent_uses_gateway_when_enabled(self):
        from src.api.agents.inventory.equipment_agent import (
            EquipmentAssetOperationsAgent,
        )

        mock_gateway = MagicMock()
        mock_hybrid = AsyncMock()
        mock_tools = AsyncMock()
        mock_memory = MagicMock()
        mock_config = MagicMock()
        mock_config.name = "equipment"

        async def run():
            with patch.dict(os.environ, {"MODEL_GATEWAY_ENABLED": "true"}):
                with (
                    patch(
                        "src.api.agents.inventory.equipment_agent.get_model_gateway",
                        new=AsyncMock(return_value=mock_gateway),
                    ),
                    patch(
                        "src.api.agents.inventory.equipment_agent.get_hybrid_retriever",
                        new=AsyncMock(return_value=mock_hybrid),
                    ),
                    patch(
                        "src.api.agents.inventory.equipment_agent.get_equipment_asset_tools",
                        new=AsyncMock(return_value=mock_tools),
                    ),
                    patch(
                        "src.api.agents.inventory.equipment_agent.get_memory_manager",
                        new=AsyncMock(return_value=mock_memory),
                    ),
                    patch(
                        "src.api.agents.inventory.equipment_agent.load_agent_config",
                        return_value=mock_config,
                    ),
                ):
                    agent = EquipmentAssetOperationsAgent()
                    await agent.initialize()
                    return agent

        agent = asyncio.run(run())
        assert agent.model_gateway is mock_gateway
        assert agent.nim_client is None


# ── Phase 1B: SafetyAgent gateway migration ───────────────────────────────────


class TestSafetyAgentGatewaySlice:
    def setup_method(self):
        _patch_missing_deps_for_ops()

    def test_safety_agent_has_model_gateway_attr(self):
        from src.api.agents.safety.safety_agent import SafetyComplianceAgent

        agent = SafetyComplianceAgent()
        assert hasattr(agent, "model_gateway")
        assert agent.model_gateway is None

    def test_safety_agent_uses_gateway_when_enabled(self):
        from src.api.agents.safety.safety_agent import SafetyComplianceAgent

        mock_gateway = MagicMock()
        mock_hybrid = AsyncMock()
        mock_tools = AsyncMock()
        mock_sql = MagicMock()
        mock_reasoning = AsyncMock()
        mock_config = MagicMock()
        mock_config.name = "safety"

        async def run():
            with patch.dict(os.environ, {"MODEL_GATEWAY_ENABLED": "true"}):
                with (
                    patch(
                        "src.api.agents.safety.safety_agent.get_model_gateway",
                        new=AsyncMock(return_value=mock_gateway),
                    ),
                    patch(
                        "src.api.agents.safety.safety_agent.get_hybrid_retriever",
                        new=AsyncMock(return_value=mock_hybrid),
                    ),
                    patch(
                        "src.api.agents.safety.safety_agent.get_safety_action_tools",
                        new=AsyncMock(return_value=mock_tools),
                    ),
                    patch(
                        "src.api.agents.safety.safety_agent.get_sql_retriever",
                        new=AsyncMock(return_value=mock_sql),
                    ),
                    patch(
                        "src.api.agents.safety.safety_agent.get_reasoning_engine",
                        new=AsyncMock(return_value=mock_reasoning),
                    ),
                    patch(
                        "src.api.agents.safety.safety_agent.load_agent_config",
                        return_value=mock_config,
                    ),
                ):
                    agent = SafetyComplianceAgent()
                    await agent.initialize()
                    return agent

        agent = asyncio.run(run())
        assert agent.model_gateway is mock_gateway
        assert agent.nim_client is None
