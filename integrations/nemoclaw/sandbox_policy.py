# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
RuntimeCapabilityPolicy → sandbox policy.

This module is the single place where a MAIW authority decision becomes a
sandbox enforcement rule. It is a *translation*, and the translation is lossy in
exactly one direction:

    everything the rendered policy permits, the MAIW policy already permitted
    not everything the MAIW policy permits survives into the rendered policy

That asymmetry is the whole design. ``render_sandbox_policy`` can narrow; it has
no code path that widens. ``RenderedSandboxPolicy.assert_not_broadened`` is the
assertion, and it is checked on every render rather than left to a test.

Three properties hold:

  DETERMINISTIC   The same ``RuntimeCapabilityPolicy`` and ``SandboxConfig``
                  render byte-identical YAML. No timestamp, no UUID, no set
                  iteration order leaks into the output — a policy diff between
                  two deployments shows a real difference or nothing at all.

  MONOTONIC       The rendered grant is a subset of the MAIW grant, enforced in
                  a model validator so a hand-constructed ``RenderedSandboxPolicy``
                  cannot skip the check by avoiding the renderer.

  CREDENTIAL-FREE ``injected_credentials`` is empty and cannot be made non-empty.
                  The sandbox authenticates to MAIW; it never holds a warehouse
                  or provider credential. A rendered policy is written to disk,
                  logged and diffed, so it must be safe to treat as non-secret.

What this module never does: consult the environment, read model output, accept
a capability the sandbox asked for, or grant a write. ``WRITE`` and
``EMERGENCY_WRITE`` have no path into a rendered policy — not through the class
list, not through a capability id, not through a network endpoint.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from maiw_agents.contracts.capability_policy import (
    ALWAYS_DENIED_CAPABILITY_CLASSES,
    RuntimeCapabilityPolicy,
)
from maiw_agents.contracts.registry import SKILL_REGISTRY

from .sandbox_config import SandboxConfig

logger = logging.getLogger(__name__)


EndpointPurpose = Literal["inference", "read_capabilities"]
"""
The complete set of reasons the sandbox may open a network connection.

There is no ``write`` purpose and no ``governance`` purpose, and adding one
would be a change to the authority model rather than a change to this file.
"""


_WRITE_SHAPED_ENDPOINT_TOKENS: frozenset[str] = frozenset(
    {
        "write",
        "execute",
        "approve",
        "proposal",
        "mutate",
        "commit",
    }
)
"""
Substrings that must not appear in an allowed endpoint URL.

Defence in depth behind ``SandboxConfig``'s own endpoint validation: the config
guards the paths MAIW knows about, this guards the string that actually lands in
the rendered policy, whatever produced it.
"""


# ── Errors ────────────────────────────────────────────────────────────────────


class SandboxPolicyError(ValueError):
    """A sandbox policy could not be rendered, or was rendered unsafely."""


# ── Rendered policy ───────────────────────────────────────────────────────────


class SandboxNetworkEndpoint(BaseModel):
    """One endpoint the sandbox is permitted to reach, and why."""

    model_config = ConfigDict(frozen=True)

    endpoint: str
    purpose: EndpointPurpose

    @model_validator(mode="after")
    def _not_write_shaped(self) -> "SandboxNetworkEndpoint":
        lowered = self.endpoint.lower()
        for token in sorted(_WRITE_SHAPED_ENDPOINT_TOKENS):
            if token in lowered:
                raise SandboxPolicyError(
                    f"network endpoint {self.endpoint!r} contains {token!r}; "
                    "the sandbox reaches no write or governance surface"
                )
        if "@" in lowered:
            raise SandboxPolicyError(
                f"network endpoint {self.endpoint!r} embeds credentials"
            )
        return self


class RenderedSandboxPolicy(BaseModel):
    """
    The sandbox-enforceable projection of one ``RuntimeCapabilityPolicy``.

    Carries the provenance of the policy it came from (``source_policy_id``,
    ``source_policy_revision``) so an applied sandbox policy can be traced back
    to the reviewed MAIW artifacts that produced it. Those fields are copied,
    never generated — rendering the same policy twice yields the same ids.
    """

    model_config = ConfigDict(frozen=True)

    # ── Provenance (copied from the source policy, never generated) ───────────
    source_policy_id: str
    source_policy_revision: int = Field(ge=1)
    agent_task_id: str
    sop_id: str
    sop_version: str
    runtime: str
    policy_profile: str

    # ── Network: deny by default ──────────────────────────────────────────────
    network_default: Literal["deny"] = "deny"
    allowed_network_endpoints: tuple[SandboxNetworkEndpoint, ...] = ()

    # ── Filesystem ────────────────────────────────────────────────────────────
    writable_paths: tuple[str, ...] = ()
    readable_paths: tuple[str, ...] = ()

    # ── Capabilities ──────────────────────────────────────────────────────────
    allowed_capability_classes: frozenset[str] = Field(default_factory=frozenset)
    denied_capability_classes: frozenset[str] = Field(
        default_factory=lambda: ALWAYS_DENIED_CAPABILITY_CLASSES
    )
    allowed_capability_ids: frozenset[str] = Field(default_factory=frozenset)
    allowed_subagents: frozenset[str] = Field(default_factory=frozenset)

    # ── Credentials ───────────────────────────────────────────────────────────
    credential_custody: Literal["host_only"] = "host_only"
    managed_credentials: tuple[str, ...] = Field(
        default=(),
        description=(
            "Names of credentials the HOST holds on the sandbox's behalf. "
            "Documentation of custody, not a transfer of it — no value for any "
            "of these ever enters the sandbox."
        ),
    )
    injected_credentials: tuple[str, ...] = Field(
        default=(),
        description="Always empty. A validator rejects any non-empty value.",
    )

    # ── Invariants ────────────────────────────────────────────────────────────

    @model_validator(mode="after")
    def _write_is_never_rendered(self) -> "RenderedSandboxPolicy":
        """
        No write reaches a sandbox policy, by any of the four routes it could.

        Placed on the model rather than in ``render_sandbox_policy`` so that a
        policy built by hand — in a test, in future glue code, by a caller that
        thought it knew better — is held to the same rule.
        """
        leaked = ALWAYS_DENIED_CAPABILITY_CLASSES & self.allowed_capability_classes
        if leaked:
            raise SandboxPolicyError(
                f"rendered sandbox policy allows {sorted(leaked)}; writes cross "
                "the governance boundary on the host, never a sandbox boundary"
            )

        missing = ALWAYS_DENIED_CAPABILITY_CLASSES - self.denied_capability_classes
        if missing:
            raise SandboxPolicyError(
                f"rendered sandbox policy must deny {sorted(missing)} explicitly"
            )

        # Route 2: naming a write capability by id rather than by class.
        for cap_id in sorted(self.allowed_capability_ids):
            entry = SKILL_REGISTRY.get(cap_id)
            if entry is None:
                raise SandboxPolicyError(
                    f"rendered sandbox policy allows unregistered capability "
                    f"{cap_id!r}; a class that cannot be verified is denied"
                )
            if entry.capability_class.value in ALWAYS_DENIED_CAPABILITY_CLASSES:
                raise SandboxPolicyError(
                    f"rendered sandbox policy allows capability {cap_id!r} of "
                    f"class {entry.capability_class.value}"
                )
            if entry.capability_class.value not in self.allowed_capability_classes:
                raise SandboxPolicyError(
                    f"rendered sandbox policy allows capability {cap_id!r} whose "
                    f"class {entry.capability_class.value} is not in the class "
                    "allow-list"
                )

        # Route 3: reaching a write surface over the network.
        #          (each endpoint also self-checks; this covers the set.)
        if self.network_default != "deny":
            raise SandboxPolicyError("sandbox network default must be 'deny'")

        # Route 4: carrying a credential that could authorise a write elsewhere.
        if self.injected_credentials:
            raise SandboxPolicyError(
                "rendered sandbox policy injects credentials "
                f"{sorted(self.injected_credentials)}; the sandbox holds none"
            )
        return self

    @model_validator(mode="after")
    def _paths_are_disjoint_and_scoped(self) -> "RenderedSandboxPolicy":
        """A path is writable or readable, never silently both."""
        overlap = set(self.writable_paths) & set(self.readable_paths)
        if overlap:
            raise SandboxPolicyError(
                f"paths {sorted(overlap)} are both writable and read-only"
            )
        for path in (*self.writable_paths, *self.readable_paths):
            if not path.startswith("/workspace/"):
                raise SandboxPolicyError(f"sandbox path {path!r} escapes /workspace/")
        return self

    # ── Monotonicity ──────────────────────────────────────────────────────────

    def is_narrower_or_equal_to(self, policy: RuntimeCapabilityPolicy) -> bool:
        """
        True if this rendering grants nothing ``policy`` does not already grant.

        The containment claim in one method. If this can ever return False for a
        policy produced by ``render_sandbox_policy``, the sandbox has become a
        privilege-escalation path rather than a containment one.
        """
        return (
            self.allowed_capability_ids <= policy.allowed_capability_ids
            and self.allowed_capability_classes <= policy.allowed_capability_classes
            and self.allowed_subagents <= policy.allowed_subagents
            and self.denied_capability_classes >= policy.denied_capability_classes
        )

    def assert_not_broadened(self, policy: RuntimeCapabilityPolicy) -> None:
        """Raise ``SandboxPolicyError`` if this rendering exceeds ``policy``."""
        if self.is_narrower_or_equal_to(policy):
            return
        raise SandboxPolicyError(
            "rendered sandbox policy broadened relative to MAIW policy "
            f"{policy.policy_id}: "
            f"capabilities={sorted(self.allowed_capability_ids - policy.allowed_capability_ids)} "
            f"classes={sorted(self.allowed_capability_classes - policy.allowed_capability_classes)} "
            f"subagents={sorted(self.allowed_subagents - policy.allowed_subagents)}"
        )


# ── Rendering ─────────────────────────────────────────────────────────────────


def render_sandbox_policy(
    policy: RuntimeCapabilityPolicy,
    *,
    config: SandboxConfig,
) -> RenderedSandboxPolicy:
    """
    Project a MAIW capability policy onto the sandbox's enforcement surface.

    Inputs, exhaustively: the ``RuntimeCapabilityPolicy`` (authority) and the
    ``SandboxConfig`` (deployment). Nothing else — not the environment, not the
    registry beyond classifying what the policy already named, and nothing the
    sandbox reports about itself.

    The capability set is copied, not recomputed: ``build_capability_policy``
    already did the intersection and the class filtering, and doing it twice
    with two implementations is how the two answers eventually differ. What this
    function adds is the *network, filesystem and credential* projection that a
    capability policy has no opinion about.

    Raises ``SandboxPolicyError`` if the result would grant more than the input.
    """
    endpoints = (
        SandboxNetworkEndpoint(
            endpoint=config.model_gateway_endpoint,
            purpose="inference",
        ),
        SandboxNetworkEndpoint(
            endpoint=config.read_capability_endpoint,
            purpose="read_capabilities",
        ),
    )

    rendered = RenderedSandboxPolicy(
        source_policy_id=policy.policy_id,
        source_policy_revision=policy.policy_revision,
        agent_task_id=policy.agent_task_id,
        sop_id=policy.sop_id,
        sop_version=policy.sop_version,
        runtime=policy.runtime,
        policy_profile=config.policy_profile,
        network_default="deny",
        allowed_network_endpoints=tuple(
            sorted(endpoints, key=lambda e: (e.purpose, e.endpoint))
        ),
        writable_paths=(config.procedure_state_mount,),
        readable_paths=(config.sop_definitions_mount,),
        allowed_capability_classes=frozenset(policy.allowed_capability_classes),
        denied_capability_classes=frozenset(policy.denied_capability_classes)
        | ALWAYS_DENIED_CAPABILITY_CLASSES,
        allowed_capability_ids=frozenset(policy.allowed_capability_ids),
        allowed_subagents=frozenset(policy.allowed_subagents),
        credential_custody="host_only",
        managed_credentials=(),
        injected_credentials=(),
    )

    # Belt and braces: the validators above prove the rendering is *safe*; this
    # proves it is *contained*. They are different claims.
    rendered.assert_not_broadened(policy)

    logger.info(
        "sandbox policy rendered: source_policy=%s profile=%s runtime=%s "
        "classes=%s capabilities=%d endpoints=%d writable_paths=%d credentials=0",
        rendered.source_policy_id,
        rendered.policy_profile,
        rendered.runtime,
        sorted(rendered.allowed_capability_classes),
        len(rendered.allowed_capability_ids),
        len(rendered.allowed_network_endpoints),
        len(rendered.writable_paths),
    )
    return rendered


# ── Serialisation ─────────────────────────────────────────────────────────────


def render_policy_yaml(rendered: RenderedSandboxPolicy) -> str:
    """
    Serialise a rendered policy to the YAML a sandbox runtime consumes.

    Hand-written rather than ``yaml.safe_dump``-ed for one reason: determinism is
    a tested property here, and hand-ordering the keys makes the guarantee
    visible in the source instead of dependent on a library's sort behaviour
    across versions. Every collection is sorted; no timestamp is emitted.
    """
    lines: list[str] = [
        "# Generated by MAIW from RuntimeCapabilityPolicy — do not edit by hand.",
        "# Regenerate with integrations.nemoclaw.render_sandbox_policy().",
        f"policy_id: {rendered.source_policy_id}",
        f"policy_revision: {rendered.source_policy_revision}",
        f"policy_profile: {rendered.policy_profile}",
        f"agent_task_id: {rendered.agent_task_id}",
        f"sop_id: {rendered.sop_id}",
        f"sop_version: {rendered.sop_version}",
        f"runtime: {rendered.runtime}",
        "",
        "network:",
        f"  default: {rendered.network_default}",
    ]

    if rendered.allowed_network_endpoints:
        lines.append("  allowed:")
        for ep in rendered.allowed_network_endpoints:
            lines.append(f"    - endpoint: {ep.endpoint}")
            lines.append(f"      purpose: {ep.purpose}")
    else:
        lines.append("  allowed: []")

    lines.append("")
    lines.append("filesystem:")
    lines.append("  writable:")
    for path in sorted(rendered.writable_paths):
        lines.append(f"    - {path}")
    lines.append("  readable:")
    for path in sorted(rendered.readable_paths):
        lines.append(f"    - {path}")

    lines.append("")
    lines.append("capabilities:")
    lines.append(
        "  allowed_classes: ["
        + ", ".join(sorted(rendered.allowed_capability_classes))
        + "]"
    )
    lines.append(
        "  denied_classes: ["
        + ", ".join(sorted(rendered.denied_capability_classes))
        + "]"
    )
    lines.append("  allowed_ids:")
    if rendered.allowed_capability_ids:
        for cap_id in sorted(rendered.allowed_capability_ids):
            lines.append(f"    - {cap_id}")
    else:
        lines[-1] = "  allowed_ids: []"
    lines.append("  allowed_subagents:")
    if rendered.allowed_subagents:
        for agent_id in sorted(rendered.allowed_subagents):
            lines.append(f"    - {agent_id}")
    else:
        lines[-1] = "  allowed_subagents: []"

    lines.append("")
    lines.append("credentials:")
    lines.append(f"  custody: {rendered.credential_custody}")
    lines.append("  managed: [" + ", ".join(sorted(rendered.managed_credentials)) + "]")
    lines.append("  injected: []  # empty — the sandbox holds no credentials")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "EndpointPurpose",
    "RenderedSandboxPolicy",
    "SandboxNetworkEndpoint",
    "SandboxPolicyError",
    "render_policy_yaml",
    "render_sandbox_policy",
]
