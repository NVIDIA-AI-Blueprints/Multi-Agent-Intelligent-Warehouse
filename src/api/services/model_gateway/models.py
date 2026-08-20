# DEPRECATED compatibility shim — use maiw_models.models directly. Remove by Phase 9.
from maiw_models.models import *  # noqa: F401, F403
from maiw_models.models import (  # noqa: F401
    CostClass,
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
