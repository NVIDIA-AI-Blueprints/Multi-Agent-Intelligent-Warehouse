# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW SOP Engine V2.

Owns procedure lifecycle, step progression, completion validation, retry,
escalation, and evidence collection — independently of any runtime.

    SOPEngine                   procedure lifecycle owner
    LoopDecision                the bounded-loop state machine (EXIT/RETRY/EXHAUSTED)
    SOPStepExecutor             the per-step runtime seam
    ValidatorRegistry           selects the validator that proves a step is complete
    EvidenceRequirementsValidator
                                enforces declared evidence as a completion
                                precondition, ahead of the completion validator
    ProcedureStateStore         durable procedure record — makes a crashed
                                procedure recoverable without re-executing it

Authority boundary — enforced by test_security_boundary.py:
    This package imports nothing from ``maiw_execution`` and holds no reference
    to ActionExecutor, DecisionEngine, warehouse credentials, or WRITE tools.
    No validator can authorize an operational write, and persisting procedure
    state does not move any authority into this package.
"""

from .engine import LoopDecision, SOPEngine
from .executor import SOPStepExecutor
from .state_store import (
    InMemoryProcedureStateStore,
    JsonFileProcedureStateStore,
    ProcedureStateStore,
    ProcedureStateStoreError,
    StaleRevisionError,
    TerminalStateError,
)
from .validators import (
    DEFAULT_EVIDENCE_VALIDATOR,
    DEFAULT_VALIDATOR_REGISTRY,
    CapabilityResultValidator,
    EvidenceRequirementsValidator,
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
    "LoopDecision",
    "SOPStepExecutor",
    "StepValidator",
    "StepValidationContext",
    "SchemaValidator",
    "StatePredicateValidator",
    "CapabilityResultValidator",
    "LegacySuccessValidator",
    "EvidenceRequirementsValidator",
    "DEFAULT_EVIDENCE_VALIDATOR",
    "ValidatorRegistry",
    "DEFAULT_VALIDATOR_REGISTRY",
    "register_predicate",
    "unregister_predicate",
    "get_registered_predicates",
    "ProcedureStateStore",
    "ProcedureStateStoreError",
    "StaleRevisionError",
    "TerminalStateError",
    "InMemoryProcedureStateStore",
    "JsonFileProcedureStateStore",
]
