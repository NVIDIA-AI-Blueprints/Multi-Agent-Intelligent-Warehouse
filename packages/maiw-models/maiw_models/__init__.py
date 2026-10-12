# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
maiw-models — ModelGateway, NIMProvider, and all model-layer types.

Canonical import (Phase 8+):
    from maiw_models import ModelGateway, ModelRequest, get_model_gateway

Legacy compatibility path (DEPRECATED — remove by Phase 9):
    from src.api.services.model_gateway import ModelGateway  # still works via shim
"""

from __future__ import annotations

import logging
import os

from .deployment import (
    APPROVED_DEPLOYMENTS,
    APPROVED_MODEL_GENERATIONS,
    ApprovedDeployment,
    DeploymentResolver,
    ResolvedDeployment,
    default_resolver,
)
from .errors import (
    ModelConfigurationError,
    ModelGatewayError,
    ModelIdentityMismatch,
    ModelIdentityUnverifiable,
    ModelPolicyViolation,
    ModelResponseError,
    ModelTimeout,
    ModelUnavailable,
    StructuredOutputError,
)
from .gateway import ModelGateway
from .models import (
    CostClass,
    DeploymentMode,
    DeploymentStatus,
    LatencyClass,
    ModelCapability,
    ModelRequest,
    ModelResponse,
    ModelRouteDecision,
    Modality,
    ReasoningLevel,
    RiskLevel,
)
from .providers.nim import NIMProvider
from .providers.nim_client import NIMClient, LLMResponse
from .registry import ModelRegistry, TRANSPORT_SMOKE_TEST_MODEL
from .router import ModelRouter
from .routing import ModelCandidate, PolicyFilter, RoutingContext, RoutingStrategy
from .telemetry import GatewayTelemetry

logger = logging.getLogger(__name__)

# ── Singleton ─────────────────────────────────────────────────────────────────

_gateway_instance: ModelGateway | None = None


async def get_model_gateway(nim_circuit=None) -> ModelGateway:
    """
    Return the process-level ModelGateway singleton.

    Creates it on first call using the global NIMClient.

    Parameters
    ----------
    nim_circuit:
        Optional CircuitBreaker for the NIM provider.  Passed through to
        ModelGateway so that repeated NIM failures trip the circuit.
        Only used during initial construction — subsequent calls return the
        cached instance regardless of nim_circuit.
    """
    global _gateway_instance
    if _gateway_instance is None:
        from maiw_models.providers.nim_client import get_nim_client

        nim_client = await get_nim_client()
        registry = ModelRegistry()
        provider = NIMProvider(nim_client)
        router = ModelRouter(registry)
        telemetry = GatewayTelemetry()
        _gateway_instance = ModelGateway(
            provider=provider,
            registry=registry,
            router=router,
            telemetry=telemetry,
            nim_circuit=nim_circuit,
        )
        logger.info(
            "ModelGateway initialised (maiw_models). Enabled models: %s",
            [c.model_id for c in registry.all_enabled()],
        )
        violations = registry.binding_violations()
        if violations:
            logger.error(
                "ModelGateway: %d enabled role(s) bound to an unapproved physical "
                "model — those roles fail closed (MODEL_POLICY_VIOLATION) and "
                "/api/v1/ready reports NOT_READY: %s",
                len(violations),
                [(v["role"], v["model_id"], v["reason"]) for v in violations],
            )
    return _gateway_instance


def reset_model_gateway() -> None:
    """Reset the singleton — for testing only."""
    global _gateway_instance
    _gateway_instance = None


def is_model_gateway_enabled() -> bool:
    """Check the MODEL_GATEWAY_ENABLED feature flag (default true)."""
    value = os.getenv("MODEL_GATEWAY_ENABLED", "true").strip().lower()
    return value not in {"0", "false", "no", "off"}


__all__ = [
    # Gateway
    "ModelGateway",
    "get_model_gateway",
    "reset_model_gateway",
    "is_model_gateway_enabled",
    # Request / Response
    "ModelRequest",
    "ModelResponse",
    "ModelRouteDecision",
    "ModelCapability",
    # Enums
    "Modality",
    "ReasoningLevel",
    "RiskLevel",
    "LatencyClass",
    "CostClass",
    "DeploymentMode",
    "DeploymentStatus",
    # Errors
    "ModelGatewayError",
    "ModelUnavailable",
    "ModelTimeout",
    "ModelConfigurationError",
    "ModelResponseError",
    "StructuredOutputError",
    "ModelPolicyViolation",
    "ModelIdentityMismatch",
    "ModelIdentityUnverifiable",
    # v2.0.1 round 2: physical model identity
    "APPROVED_DEPLOYMENTS",
    "APPROVED_MODEL_GENERATIONS",
    "ApprovedDeployment",
    "DeploymentResolver",
    "ResolvedDeployment",
    "default_resolver",
    # Provider
    "NIMProvider",
    "NIMClient",
    "LLMResponse",
    # Infrastructure
    "ModelRegistry",
    "ModelRouter",
    "GatewayTelemetry",
    # Phase 18B: routing protocol + policy
    "RoutingStrategy",
    "PolicyFilter",
    "ModelCandidate",
    "RoutingContext",
    # Phase 20C: model family compliance
    "TRANSPORT_SMOKE_TEST_MODEL",
]
