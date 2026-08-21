# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
ModelGateway compatibility shim.

DEPRECATED — Phase 8 compatibility re-export.
The canonical import path is now:
    from maiw_models import ModelGateway, ModelRequest, get_model_gateway

This module re-exports everything from maiw_models so that existing code
using `from src.api.services.model_gateway import ...` continues to work
without modification during the migration period.

REMOVE BY: Phase 9
"""

import maiw_models as _maiw_models

from maiw_models import (  # noqa: F401
    CostClass,
    DeploymentStatus,
    GatewayTelemetry,
    LatencyClass,
    ModelCapability,
    ModelConfigurationError,
    ModelGateway,
    ModelGatewayError,
    ModelRegistry,
    ModelRequest,
    ModelResponse,
    ModelRouteDecision,
    ModelRouter,
    ModelTimeout,
    ModelUnavailable,
    Modality,
    NIMProvider,
    ReasoningLevel,
    RiskLevel,
    StructuredOutputError,
    get_model_gateway,
    is_model_gateway_enabled,
)

# Expose the private singleton directly so tests that write to
# gw_module._gateway_instance and then call reset still work.
# DEPRECATED: Do not depend on this in new code.
_gateway_instance = _maiw_models._gateway_instance


def reset_model_gateway() -> None:
    """Reset the ModelGateway singleton (compatibility wrapper)."""
    import sys
    _maiw_models.reset_model_gateway()
    # Also clear this shim module's copy so test assertions on gw_module work.
    sys.modules[__name__]._gateway_instance = None
