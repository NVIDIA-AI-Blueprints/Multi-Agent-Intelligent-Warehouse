# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW SOP Engine V2.

Owns procedure lifecycle, step progression, completion validation, retry,
escalation, and evidence collection — independently of any runtime.

    SOPEngine           procedure lifecycle owner
    SOPStepExecutor     the per-step runtime seam
    ValidatorRegistry   selects the validator that proves a step is complete

Authority boundary — enforced by test_security_boundary.py:
    This package imports nothing from ``maiw_execution`` and holds no reference
    to ActionExecutor, DecisionEngine, warehouse credentials, or WRITE tools.
    No validator can authorize an operational write.
"""

from .engine import SOPEngine
from .executor import SOPStepExecutor
from .validators import (
    DEFAULT_VALIDATOR_REGISTRY,
    CapabilityResultValidator,
    LegacySuccessValidator,
    SchemaValidator,
    StatePredicateValidator,
    StepValidationContext,
    StepValidator,
    ValidatorRegistry,
    get_registered_predicates,
    register_predicate,
    unregister_predicate,
)

__all__ = [
    "SOPEngine",
    "SOPStepExecutor",
    "StepValidator",
    "StepValidationContext",
    "SchemaValidator",
    "StatePredicateValidator",
    "CapabilityResultValidator",
    "LegacySuccessValidator",
    "ValidatorRegistry",
    "DEFAULT_VALIDATOR_REGISTRY",
    "register_predicate",
    "unregister_predicate",
    "get_registered_predicates",
]
