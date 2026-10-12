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
Approved physical model deployments and the DeploymentResolver (v2.0.1 round 2).

Before v2.0.1 round 2 the approved-family policy checked a ``generation`` label
that was hard-coded per *role*, while the physical model ID dispatched to the
provider came from ``NEMOTRON_<ROLE>_MODEL`` with no validation.  An approved
role could therefore be bound to any model ID (audit NEW-P1-01).

This module closes that gap with one small, canonical table and one resolver:

    logical role ──► configured physical model ID (env / registry)
                 ──► APPROVED_DEPLOYMENTS lookup by *model ID*
                 ──► generation ∈ APPROVED_MODEL_GENERATIONS and role matches?
                 ──► ResolvedDeployment  (the ONLY thing the provider receives)

*   The physical model ID and its generation are bound together in
    ``APPROVED_DEPLOYMENTS``.  The generation is never inferred from a role
    name or by parsing the model ID string.
*   An environment variable can only *select* one of the approved IDs for its
    role.  Any other value — an unknown ID, a look-alike ID, or an approved ID
    of a different role — fails closed with ``ModelPolicyViolation`` before any
    provider call.
*   After the provider answers, ``verify_response_identity`` compares the model
    the provider reports with the dispatched ID; a substitution raises
    ``ModelIdentityMismatch`` and the response is discarded.  A response with
    no usable identity (missing, empty, non-string) raises
    ``ModelIdentityUnverifiable`` and is discarded too (round 3): a successful
    answer is always ``identity_verified=True``.

Changing the table is a code change (reviewed), never a runtime configuration.
The approved generation set itself is fixed: it cannot be widened by this
table, by a constructor argument, or by an environment variable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .errors import (
    ModelIdentityMismatch,
    ModelIdentityUnverifiable,
    ModelPolicyViolation,
)
from .models import DeploymentMode

# MAIW v2 approved model generations (Nemotron 3 / Nemotron 3.5).  This is the
# single definition; PolicyFilter.APPROVED_MODEL_GENERATIONS refers to it.
APPROVED_MODEL_GENERATIONS: frozenset[str] = frozenset({"nemotron-3", "nemotron-3.5"})


@dataclass(frozen=True)
class ApprovedDeployment:
    """One approved (role, physical model ID, generation) binding."""

    role: str
    model_id: str
    generation: str
    provider: str = "nvidia-nim"
    note: str = ""


# Canonical approved physical deployments.
#
# Inventory checked against https://integrate.api.nvidia.com/v1/models on
# 2026-10-09 (v2.0.1 round 2).  Super, Lightning and Ultra are listed there;
# Super and Lightning were also dispatched live by the v2.0.1 re-audit.
# ``nvidia/nemotron-3-nano-30b-a3b`` (Nemotron 3 Nano) is still an approved
# Nemotron 3 *model* — it can be served by a self-hosted NIM — but the hosted
# endpoint retired it on 2026-09-01 (HTTP 410), so the Nano role is DISABLED
# by default in the registry (see registry._ENABLED_DEFAULTS).
#
# There is deliberately no Nano-Omni entry: no multimodal Nemotron 3 model has
# been qualified for MAIW, so the vision role fails closed (MODEL_UNAVAILABLE /
# MODEL_POLICY_VIOLATION) whatever NEMOTRON_NANO_OMNI_MODEL says.
APPROVED_DEPLOYMENTS: tuple[ApprovedDeployment, ...] = (
    ApprovedDeployment(
        role="lightning",
        model_id="nvidia/nemotron-3.5-lightning-30b-a3b",
        generation="nemotron-3.5",
    ),
    ApprovedDeployment(
        role="nano",
        model_id="nvidia/nemotron-3-nano-30b-a3b",
        generation="nemotron-3",
        note="hosted endpoint end-of-life 2026-09-01; self-hosted NIM only",
    ),
    ApprovedDeployment(
        role="super",
        model_id="nvidia/nemotron-3-super-120b-a12b",
        generation="nemotron-3",
    ),
    ApprovedDeployment(
        role="ultra",
        model_id="nvidia/nemotron-3-ultra-550b-a55b",
        generation="nemotron-3",
    ),
)


@dataclass(frozen=True)
class ResolvedDeployment:
    """
    The physical deployment a request is dispatched to.

    Produced only by ``DeploymentResolver.resolve``; ModelGateway passes
    ``model_id`` from this object — and nothing else — to the provider.
    """

    role: str
    model_id: str
    generation: str
    provider: str
    deployment_mode: DeploymentMode


class DeploymentResolver:
    """
    Bounded resolver: logical role + configured physical model ID →
    approved ``ResolvedDeployment``, or a typed ``ModelPolicyViolation``.

    The default instance uses ``APPROVED_DEPLOYMENTS``.  Unit tests may inject
    another table, but every entry must still declare a generation inside
    ``APPROVED_MODEL_GENERATIONS`` — the approved family cannot be widened.
    """

    def __init__(
        self, approved: Iterable[ApprovedDeployment] = APPROVED_DEPLOYMENTS
    ) -> None:
        by_id: dict[str, ApprovedDeployment] = {}
        for entry in approved:
            if entry.generation not in APPROVED_MODEL_GENERATIONS:
                raise ValueError(
                    f"ApprovedDeployment {entry.model_id!r} declares generation "
                    f"{entry.generation!r}, outside the approved MAIW family "
                    f"{sorted(APPROVED_MODEL_GENERATIONS)}."
                )
            if not entry.model_id or entry.model_id != entry.model_id.strip():
                raise ValueError(f"Invalid approved model ID {entry.model_id!r}.")
            if entry.model_id in by_id:
                raise ValueError(f"Duplicate approved model ID {entry.model_id!r}.")
            by_id[entry.model_id] = entry
        self._by_id = by_id

    # ── queries ──────────────────────────────────────────────────────────────

    def approved_model_ids(self) -> frozenset[str]:
        return frozenset(self._by_id)

    def approved_for_role(self, role: str) -> list[str]:
        return [e.model_id for e in self._by_id.values() if e.role == role]

    def generation_for(self, model_id: str) -> str | None:
        """Generation bound to an approved physical model ID (None if unknown)."""
        entry = self._by_id.get(model_id)
        return entry.generation if entry is not None else None

    def violation(self, role: str, model_id: str | None) -> tuple[str, str] | None:
        """
        Return ``(reason, message)`` when ``model_id`` may not serve ``role``,
        or ``None`` when the binding is approved.
        """
        if not model_id or not model_id.strip():
            return ("EMPTY_MODEL_ID", f"role {role!r} has no physical model ID")
        entry = self._by_id.get(model_id)
        if entry is None:
            return (
                "UNAPPROVED_MODEL_ID",
                f"physical model {model_id!r} bound to role {role!r} is not an "
                f"approved MAIW deployment (approved for {role!r}: "
                f"{self.approved_for_role(role) or 'none'})",
            )
        if entry.role != role:
            return (
                "ROLE_MISMATCH",
                f"physical model {model_id!r} is approved for role "
                f"{entry.role!r}, not {role!r}",
            )
        if entry.generation not in APPROVED_MODEL_GENERATIONS:  # pragma: no cover
            return (
                "UNAPPROVED_GENERATION",
                f"physical model {model_id!r} generation {entry.generation!r} "
                f"is not approved",
            )
        return None

    # ── enforcement ──────────────────────────────────────────────────────────

    def resolve(
        self,
        role: str,
        model_id: str | None,
        deployment_mode: DeploymentMode = DeploymentMode.NVIDIA_HOSTED,
    ) -> ResolvedDeployment:
        """Resolve or raise ``ModelPolicyViolation`` (never calls a provider)."""
        problem = self.violation(role, model_id)
        if problem is not None:
            reason, message = problem
            raise ModelPolicyViolation(
                f"MODEL_POLICY_VIOLATION ({reason}): {message}",
                model_id=model_id,
                role=role,
                reason=reason,
            )
        entry = self._by_id[model_id]  # type: ignore[index]
        return ResolvedDeployment(
            role=entry.role,
            model_id=entry.model_id,
            generation=entry.generation,
            provider=entry.provider,
            deployment_mode=deployment_mode,
        )

    @staticmethod
    def verify_response_identity(
        resolved: ResolvedDeployment, reported_model_id: object
    ) -> bool:
        """
        Compare the provider-reported model with the dispatched deployment.

        Returns True only when the provider reported exactly the dispatched
        ID.  Fails closed otherwise (v2.0.1 round 3):

        * missing / empty / whitespace-only identity → ``ModelIdentityUnverifiable``
          (``reason="MISSING"``)
        * a non-string identity → ``ModelIdentityUnverifiable``
          (``reason="MALFORMED"``)
        * any other string (another approved model, a case or whitespace
          variant, an unapproved model) → ``ModelIdentityMismatch``
        """
        if reported_model_id is None or (
            isinstance(reported_model_id, str) and not reported_model_id.strip()
        ):
            raise ModelIdentityUnverifiable(
                f"MODEL_IDENTITY_UNVERIFIABLE: dispatched approved model "
                f"{resolved.model_id!r} (role {resolved.role!r}) but the provider "
                "response reported no model identity; response discarded",
                model_id=resolved.model_id,
                role=resolved.role,
                reason="MISSING",
            )
        if not isinstance(reported_model_id, str):
            raise ModelIdentityUnverifiable(
                f"MODEL_IDENTITY_UNVERIFIABLE: dispatched approved model "
                f"{resolved.model_id!r} (role {resolved.role!r}) but the provider "
                f"reported a malformed model identity "
                f"({type(reported_model_id).__name__}); response discarded",
                model_id=resolved.model_id,
                role=resolved.role,
                reason="MALFORMED",
            )
        if reported_model_id != resolved.model_id:
            raise ModelIdentityMismatch(
                f"MODEL_IDENTITY_MISMATCH: dispatched approved model "
                f"{resolved.model_id!r} (role {resolved.role!r}) but the provider "
                f"reported {reported_model_id!r}; response discarded",
                model_id=resolved.model_id,
                reported_model_id=reported_model_id,
                role=resolved.role,
            )
        return True


_default_resolver: DeploymentResolver | None = None


def default_resolver() -> DeploymentResolver:
    """The canonical resolver over ``APPROVED_DEPLOYMENTS`` (immutable)."""
    global _default_resolver
    if _default_resolver is None:
        _default_resolver = DeploymentResolver()
    return _default_resolver


__all__ = [
    "APPROVED_DEPLOYMENTS",
    "APPROVED_MODEL_GENERATIONS",
    "ApprovedDeployment",
    "DeploymentResolver",
    "ResolvedDeployment",
    "default_resolver",
]
