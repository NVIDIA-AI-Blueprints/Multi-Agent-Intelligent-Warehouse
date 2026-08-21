# DEPRECATED compatibility shim — use maiw_models.errors directly. Remove by Phase 9.
from maiw_models.errors import *  # noqa: F401, F403
from maiw_models.errors import (  # noqa: F401
    ModelConfigurationError,
    ModelGatewayError,
    ModelResponseError,
    ModelTimeout,
    ModelUnavailable,
    StructuredOutputError,
)
