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
Phase 18B: RoutingStrategy protocol + PolicyFilter.

Separates candidate eligibility (policy) from model ranking (routing strategy).

Conceptual flow:
    ALL REGISTERED MODELS
            ↓
    POLICY FILTER (PolicyFilter.filter)
            ↓
    ELIGIBLE CANDIDATES
            ↓
    ROUTING STRATEGY (ModelRouter / RuleBasedRoutingStrategy)
            ↓
    SELECTED MODEL

Policy decides what is allowed.
Routing strategy chooses among the allowed candidates.

Current architecture keeps ModelRouter as the single authority. This module
makes the policy/routing distinction explicit without restructuring ModelRouter.

RoutingStrategy is a typed Protocol — any class with a compatible ``select``
method satisfies it without inheritance. The deterministic ModelRouter is the
default and only production implementation.

This module is ADDITIVE — it does not change ModelRouter or ModelGateway behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .deployment import APPROVED_MODEL_GENERATIONS
from .models import (
    DeploymentMode,
    ModelCapability,
    ModelRequest,
    ModelRouteDecision,
    Modality,
    RiskLevel,
)
from .registry import ModelRegistry

# ── Candidate ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ModelCandidate:
    """
    A model considered eligible by the policy filter for a given request.

    Wraps ModelCapability with request-local deployment context.
    candidate_models in ModelRouteDecision contains model_ids of these objects.
    """

    model_id: str
    role: str
    deployment_mode: DeploymentMode
    capability: ModelCapability


# ── Routing context ───────────────────────────────────────────────────────────


@dataclass
class RoutingContext:
    """
    Contextual information supplied to a RoutingStrategy alongside the request.

    Populated by ModelGateway before invoking a strategy.
    """

    deployment_mode: DeploymentMode
    trace_id: str | None = None
    # Evaluation-only override — not used in production routing.
    # When set (evaluation mode only), forces a specific model through the
    # strategy.  Must be a model_id present in the eligible candidate list.
    # Strategies MUST ignore this field outside of evaluation mode.
    evaluation_model_override: str | None = None


# ── Protocol ──────────────────────────────────────────────────────────────────


@runtime_checkable
class RoutingStrategy(Protocol):
    """
    Typed protocol for model routing strategies.

    A strategy receives ONLY the eligible candidates (after policy filtering)
    and must select exactly one.  Strategies MUST NOT:
      - modify the candidate list;
      - invoke model calls;
      - access DecisionEngine, ApprovalStore, ActionExecutor, or MCP writes.

    All production routing uses ModelRouter (the rule-based implementation).
    """

    def select(
        self,
        request: ModelRequest,
        candidates: list[ModelCandidate],
        context: RoutingContext,
    ) -> ModelRouteDecision:
        """
        Select one candidate and return a fully populated ModelRouteDecision.

        Args:
            request:    Agent's model request (intent, reasoning, risk, etc.).
            candidates: Eligible candidates after policy filtering.
            context:    Routing context (deployment mode, trace_id, etc.).

        Returns:
            ModelRouteDecision with all provenance fields populated.

        Raises:
            ModelUnavailable: when no eligible candidate can serve the request.
        """
        ...


# ── Policy filter ─────────────────────────────────────────────────────────────


class PolicyFilter:
    """
    Hard policy layer — determines which models are ELIGIBLE for a request.

    Policy constraints applied (all must pass to be eligible):
        1. Model must be enabled (enabled=True in registry).
        2. Model generation must be in APPROVED_MODEL_GENERATIONS (Nemotron 3 / 3.5).
        2b. PHYSICAL IDENTITY (v2.0.1 round 2): the physical model ID itself must
            be an approved deployment for the candidate's role
            (DeploymentResolver / APPROVED_DEPLOYMENTS).
        3. Modality must be supported by the model.
        4. DeploymentMode must be compatible with the model's provider.
        5. RiskLevel constraint: CRITICAL risk → high-capability roles only.
        6. ReasoningLevel constraint: HIGH reasoning → high-capability roles only.
        7. Required capabilities (tool_use, structured_output, etc.).

    Constraint 2 is the MAIW v2 MODEL FAMILY POLICY:
        production/qualification profiles → ModelRequest → PolicyFilter →
        eligible deployments → ONLY Nemotron 3 / Nemotron 3.5

    Llama-family Nemotron models (e.g. nvidia/llama-3.1-nemotron-nano-8b-v1),
    arbitrary Llama, Qwen, or any other non-Nemotron-3/3.5 model are REJECTED.
    The generation is bound to the PHYSICAL model ID in the approved deployment
    table (maiw_models.deployment) — never to the role name, and never inferred
    by parsing the ID.  An environment variable that binds a role to an
    unapproved or mismatched ID makes that role ineligible here, and
    ModelRouter/ModelGateway reject it with ModelPolicyViolation before any
    provider call.

    PolicyFilter does NOT rank candidates — that is the routing strategy's job.
    Routing strategy MUST NOT select a model excluded by PolicyFilter.
    """

    # MAIW v2 approved model generations.  Only these values pass constraint 2.
    # This set is fixed for production routing and CANNOT be widened by any
    # constructor argument, environment variable, or runtime configuration.
    # Evaluation Lab must use PolicyFilter._for_evaluation() (isolated path).
    APPROVED_MODEL_GENERATIONS: frozenset[str] = APPROVED_MODEL_GENERATIONS

    # Roles that satisfy HIGH-risk or HIGH-reasoning minimum capability.
    _HIGH_CAPABILITY_ROLES: frozenset[str] = frozenset({"super", "ultra"})

    # Deployment mode → allowed provider tags.
    _DEPLOYMENT_ALLOWED_PROVIDERS: dict[DeploymentMode, set[str]] = {
        DeploymentMode.NVIDIA_HOSTED: {"nvidia-nim"},
        DeploymentMode.LOCAL_NIM: {"nvidia-nim"},  # operator sets MAIW_NIM_BASE_URL
        DeploymentMode.OPENAI_COMPATIBLE: {
            "nvidia-nim"
        },  # operator sets compatible URL
        DeploymentMode.ENTERPRISE: {"nvidia-nim"},
    }

    def __init__(self, registry: ModelRegistry) -> None:
        """
        Create a production PolicyFilter with the fixed approved model set.

        The approved generation set is always ``APPROVED_MODEL_GENERATIONS``
        (Nemotron 3 / Nemotron 3.5).  It cannot be widened through this
        constructor — neither by a subclass constructor argument nor by an
        environment variable.

        For evaluation contexts that need to test non-production models, use
        ``PolicyFilter._for_evaluation(registry, approved_generations)``.
        """
        self._registry = registry
        self._approved_generations: frozenset[str] = self.APPROVED_MODEL_GENERATIONS
        # Physical identity enforcement is always on in production.  Only the
        # evaluation-only factory below (offline research registries) turns it
        # off, together with its explicit generation override.
        self._enforce_physical_identity: bool = True

    @classmethod
    def _for_evaluation(
        cls,
        registry: ModelRegistry,
        approved_generations: frozenset[str],
    ) -> "PolicyFilter":
        """
        Factory for evaluation-only PolicyFilter with a broader approved set.

        MUST NOT be used in production routing paths.  The name prefix ``_``
        signals that this is an internal / test-only escape hatch — not a
        general-purpose override.

        Parameters
        ----------
        registry:
            Model registry for the evaluation context.
        approved_generations:
            Explicit set of generation strings accepted in this evaluation run.
            Must be a frozenset — callers cannot pass a mutable set.

        Returns
        -------
        PolicyFilter
            A PolicyFilter instance that accepts the explicitly-supplied
            generation set instead of the production APPROVED_MODEL_GENERATIONS.
        """
        instance = cls(registry)
        instance._approved_generations = approved_generations
        instance._enforce_physical_identity = False
        return instance

    def physical_identity_violation(
        self, role: str, cap: ModelCapability
    ) -> tuple[str, str] | None:
        """
        ``(reason, message)`` when ``cap.model_id`` is not an approved physical
        deployment for ``role``; ``None`` when it is (or for evaluation-only
        filters).  ``role`` is the role being routed to, which may differ from
        ``cap.role`` when two roles were bound to the same ID.
        """
        if not self._enforce_physical_identity:
            return None
        resolver = getattr(self._registry, "resolver", None)
        if resolver is None:  # pragma: no cover - registry always has one
            return ("UNAPPROVED_MODEL_ID", "no DeploymentResolver configured")
        return resolver.violation(role, cap.model_id)

    @property
    def approved_generations(self) -> frozenset[str]:
        """Read-only view of the approved model generation set for this filter."""
        return self._approved_generations

    def filter(
        self,
        request: ModelRequest,
        deployment_mode: DeploymentMode,
    ) -> list[ModelCandidate]:
        """
        Return eligible ModelCandidates for this request.

        Order reflects registry insertion order — no ranking applied.
        Empty list → no enabled model satisfies all policy constraints.
        """
        candidates: list[ModelCandidate] = []
        allowed_providers = self._DEPLOYMENT_ALLOWED_PROVIDERS.get(
            deployment_mode, {"nvidia-nim"}
        )

        for cap in self._registry._capabilities.values():
            if self._is_eligible(cap, request, allowed_providers):
                candidates.append(
                    ModelCandidate(
                        model_id=cap.model_id,
                        role=cap.role,
                        deployment_mode=deployment_mode,
                        capability=cap,
                    )
                )

        return candidates

    def _is_eligible(
        self,
        cap: ModelCapability,
        request: ModelRequest,
        allowed_providers: set[str],
    ) -> bool:
        """Return True only when ALL policy constraints are satisfied."""

        # 1. Must be enabled.
        if not cap.enabled:
            return False

        # 2. MODEL FAMILY POLICY: generation must be in approved set.
        # Nemotron 3 and Nemotron 3.5 are approved for MAIW v2 production and
        # qualification.  Llama-family Nemotron, arbitrary Llama, Qwen, and
        # any unknown generation are REJECTED.  The registry derives generation
        # from the approved deployment table keyed by physical model ID, so an
        # injected/unknown ID is labelled "unapproved" and rejected here.
        if cap.generation not in self._approved_generations:
            return False

        # 2b. PHYSICAL IDENTITY (v2.0.1 round 2): the dispatched model ID must
        # be the approved deployment for this role — a generation label alone
        # is not sufficient.
        if self.physical_identity_violation(cap.role, cap) is not None:
            return False

        # 3. Provider must match the deployment mode.
        if cap.provider not in allowed_providers:
            return False

        # 4. Modality support.
        req_modality = request.modality.value
        if req_modality != Modality.TEXT.value:
            # Non-text request → model must explicitly support the modality.
            if req_modality not in cap.modalities:
                return False
        else:
            # Text requests need "text" in modalities.
            if "text" not in cap.modalities:
                return False

        # 5. RiskLevel constraint.
        # CRITICAL risk → only high-capability models allowed.
        if request.risk_level == RiskLevel.CRITICAL:
            if cap.role not in self._HIGH_CAPABILITY_ROLES:
                return False

        # 6. ReasoningLevel constraint.
        # HIGH reasoning → only high-capability models allowed.
        if request.reasoning.value == "high":
            if cap.role not in self._HIGH_CAPABILITY_ROLES:
                return False

        # 7. Required capability tags.
        if request.required_capabilities:
            if "tool_use" in request.required_capabilities and not cap.tool_use:
                return False
            if (
                "structured_output" in request.required_capabilities
                and not cap.structured_output
            ):
                return False
            if (
                "teacher_judge" in request.required_capabilities
                and not cap.teacher_judge
            ):
                return False

        return True

    def is_request_eligible(
        self,
        cap: ModelCapability,
        request: ModelRequest,
    ) -> bool:
        """Check whether a single capability satisfies all policy constraints for request.

        Used by ModelRouter to validate fallback candidates without duplicating
        policy logic.  deployment_mode is taken from request.deployment_mode.
        """
        allowed_providers = self._DEPLOYMENT_ALLOWED_PROVIDERS.get(
            request.deployment_mode, {"nvidia-nim"}
        )
        return self._is_eligible(cap, request, allowed_providers)

    def candidate_model_ids(
        self,
        request: ModelRequest,
        deployment_mode: DeploymentMode,
    ) -> list[str]:
        """Convenience — return model_ids of eligible candidates (for telemetry)."""
        return [c.model_id for c in self.filter(request, deployment_mode)]
