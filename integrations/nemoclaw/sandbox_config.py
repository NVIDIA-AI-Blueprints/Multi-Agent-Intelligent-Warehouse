# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Host-side deployment configuration for a sandboxed MAIW agent runtime.

A ``SandboxConfig`` answers deployment questions — *is there a sandbox, what
kind, where does inference go, which paths are mounted*. It deliberately does
**not** answer authority questions. Those are answered by
``RuntimeCapabilityPolicy``, which is derived from reviewed MAIW artifacts and
never from configuration.

    config  = where the agent runs and what it can reach
    policy  = what the agent is permitted to invoke

The split matters because configuration is the surface an operator edits and an
environment variable can reach. If capabilities were configurable, a deployment
change would be a privilege change. They are not, so it cannot be.

Read **before** the sandbox is created, on the host, by the host. Nothing inside
the sandbox supplies any field on this model — a sandbox that could describe its
own configuration could describe itself as unsandboxed.
"""

from __future__ import annotations

import logging
import os
from enum import Enum
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)


# ── Modes ─────────────────────────────────────────────────────────────────────


class SandboxMode(str, Enum):
    """
    How hard a missing sandbox should fail.

    ``SANDBOX_REQUIRED`` is the only mode that makes the containment claim
    load-bearing. In the other two, the sandbox is an optimisation; MAIW's own
    capability policy is still the thing preventing a write either way.
    """

    DISABLED = "disabled"
    """Normal operation. No sandbox is created and none is expected."""

    SANDBOX_REQUIRED = "required"
    """
    Fail closed. If the sandbox cannot be created, or its policy cannot be
    applied, the task fails. There is no unsandboxed fallback path — not as a
    retry, not as a degraded mode, not behind a flag.
    """

    SANDBOX_PREFERRED = "preferred"
    """
    Warn and continue unsandboxed if the sandbox is unavailable. Appropriate for
    development and for rollout, never for an environment whose threat model
    assumes the agent process is hostile.
    """


class SandboxRuntimeKind(str, Enum):
    """Which isolation technology backs the boundary."""

    NONE = "none"
    """No isolation technology selected."""

    OPENSHELL = "openshell"
    """
    OpenShell enforces the boundary and NemoClaw packages it. This is the
    intended production target. It requires both to be installed; see
    ``docs/architecture/NEMOCLAW_OPENSHELL_INTEGRATION.md`` for the
    qualification status on a given host.
    """

    CONTAINER = "container"
    """
    An OCI container runtime (Docker/Podman) applying the same rendered policy.
    A boundary proxy with the same shape as the OpenShell one — deny-by-default
    network, read-only mounts, no credentials — used where OpenShell is not
    installed. Weaker than OpenShell; it is not a substitute for it.
    """


# ── Errors ────────────────────────────────────────────────────────────────────


class SandboxConfigurationError(ValueError):
    """A configuration was rejected before any sandbox was created."""


# ── Config ────────────────────────────────────────────────────────────────────

_FORBIDDEN_ENDPOINT_SUBSTRINGS: frozenset[str] = frozenset(
    {
        "/write",
        "/execute",
        "/approve",
        "/proposals",
        "/actions",
    }
)
"""
Path fragments that would place a governance or execution surface inside the
sandbox's reach. Matched case-insensitively against every configured endpoint.

This is a configuration-time guard, not the primary control — the primary
control is that the host simply does not route these endpoints to the sandbox
network. It exists so that a mistaken endpoint is rejected loudly at startup
rather than quietly widening the boundary.
"""


class SandboxConfig(BaseModel):
    """
    Host-side deployment facts for one sandboxed runtime.

    Frozen: a config is resolved once, before the sandbox exists, and the
    rendered policy is derived from it. A mutable config would mean the policy
    that was applied and the policy that is reported could differ.
    """

    model_config = ConfigDict(frozen=True)

    mode: SandboxMode = SandboxMode.DISABLED
    runtime_kind: SandboxRuntimeKind = SandboxRuntimeKind.NONE

    policy_profile: str = Field(
        default="maiw-readonly-reasoning",
        description=(
            "Name of the boundary profile this deployment applies. A label for "
            "operators and audit logs — it grants nothing on its own."
        ),
    )

    model_gateway_endpoint: str = Field(
        description=(
            "Host-side MAIW endpoint that fronts ModelGateway. The sandbox "
            "reaches inference only through this URL and never holds a provider "
            "key. Model *selection* stays with ModelGateway on the host."
        ),
    )
    read_capability_endpoint: str = Field(
        description=(
            "Host-side MAIW endpoint serving READ/ANALYTICAL capability results. "
            "Read-only by construction; no write capability is routed here."
        ),
    )

    procedure_state_mount: str = Field(
        default="/workspace/procedure_state",
        description=(
            "The single writable path inside the sandbox. Holds the procedure "
            "checkpoint only. Authoritative procedure state lives on the host — "
            "this is a working copy, not the record of truth."
        ),
    )
    sop_definitions_mount: str = Field(
        default="/workspace/sop_definitions",
        description="Read-only mount of the SOP YAML the procedure is executing.",
    )

    image_reference: str | None = Field(
        default=None,
        description="Pinned agent image the sandbox runs. None until qualified.",
    )
    nemoclaw_version: str | None = Field(
        default=None,
        description="NemoClaw version this config was qualified against, if any.",
    )
    openshell_version: str | None = Field(
        default=None,
        description="OpenShell version this config was qualified against, if any.",
    )

    # ── Validation ────────────────────────────────────────────────────────────

    @field_validator("model_gateway_endpoint", "read_capability_endpoint")
    @classmethod
    def _endpoint_is_safe(cls, value: str) -> str:
        """
        Reject an endpoint that carries a credential or names a write surface.

        Userinfo (``https://user:secret@host/``) is rejected outright: an
        endpoint is rendered into the sandbox policy, and a policy is an
        artifact that gets logged, diffed and stored. A credential embedded in a
        URL is a credential that leaks into all three.
        """
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"endpoint {value!r} must be http or https, got scheme "
                f"{parsed.scheme!r}"
            )
        if not parsed.netloc:
            raise ValueError(f"endpoint {value!r} has no host")
        if "@" in parsed.netloc:
            raise ValueError(
                "endpoint must not embed credentials in its URL; the sandbox "
                "holds no credentials and a rendered policy is not a secret store"
            )
        lowered = value.lower()
        for fragment in sorted(_FORBIDDEN_ENDPOINT_SUBSTRINGS):
            if fragment in lowered:
                raise ValueError(
                    f"endpoint {value!r} names a governance/execution surface "
                    f"({fragment!r}); writes do not cross the sandbox boundary"
                )
        return value

    @field_validator("procedure_state_mount", "sop_definitions_mount")
    @classmethod
    def _mount_is_absolute_and_scoped(cls, value: str) -> str:
        """Mounts must be absolute and confined to ``/workspace``."""
        if not value.startswith("/"):
            raise ValueError(f"mount {value!r} must be an absolute path")
        if not value.startswith("/workspace/"):
            raise ValueError(
                f"mount {value!r} must live under /workspace/ — the sandbox is "
                "not given a path that could alias a host directory"
            )
        return value

    # ── Derived ───────────────────────────────────────────────────────────────

    @property
    def requires_sandbox(self) -> bool:
        """True when an unavailable sandbox must fail the task."""
        return self.mode is SandboxMode.SANDBOX_REQUIRED

    @property
    def is_qualified(self) -> bool:
        """
        True only when this config names the versions it was tested against.

        An unqualified config is usable in ``DISABLED`` and ``SANDBOX_PREFERRED``
        but is a reporting signal: the integration doc must not claim runtime
        qualification for a config that cannot say what it qualified against.
        """
        if self.runtime_kind is SandboxRuntimeKind.OPENSHELL:
            return bool(self.nemoclaw_version and self.openshell_version)
        if self.runtime_kind is SandboxRuntimeKind.CONTAINER:
            return bool(self.image_reference)
        return False

    # ── Construction from the environment ─────────────────────────────────────

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "SandboxConfig":
        """
        Build a config from host environment variables.

        Reads ``MAIW_SANDBOX_MODE``, ``MAIW_SANDBOX_RUNTIME``,
        ``MAIW_SANDBOX_MODEL_GATEWAY_ENDPOINT``,
        ``MAIW_SANDBOX_READ_ENDPOINT``, ``MAIW_SANDBOX_IMAGE``,
        ``MAIW_NEMOCLAW_VERSION``, ``MAIW_OPENSHELL_VERSION``.

        What this can set: where the sandbox runs and what it can reach.
        What this can never set: which capabilities the agent may invoke. There
        is no environment variable that widens a ``RuntimeCapabilityPolicy``,
        because the policy is not built from the environment at all.

        An unrecognised mode raises rather than defaulting. Defaulting a typo to
        ``DISABLED`` would turn a misconfiguration into a silently unsandboxed
        deployment — exactly the failure this module exists to prevent.
        """
        source = os.environ if env is None else env

        raw_mode = source.get("MAIW_SANDBOX_MODE", SandboxMode.DISABLED.value)
        try:
            mode = SandboxMode(raw_mode)
        except ValueError as exc:
            raise SandboxConfigurationError(
                f"MAIW_SANDBOX_MODE={raw_mode!r} is not one of "
                f"{[m.value for m in SandboxMode]}. Refusing to default — an "
                "unreadable mode must not become an unsandboxed deployment."
            ) from exc

        raw_kind = source.get("MAIW_SANDBOX_RUNTIME", SandboxRuntimeKind.NONE.value)
        try:
            runtime_kind = SandboxRuntimeKind(raw_kind)
        except ValueError as exc:
            raise SandboxConfigurationError(
                f"MAIW_SANDBOX_RUNTIME={raw_kind!r} is not one of "
                f"{[k.value for k in SandboxRuntimeKind]}."
            ) from exc

        if mode is not SandboxMode.DISABLED and runtime_kind is SandboxRuntimeKind.NONE:
            raise SandboxConfigurationError(
                f"MAIW_SANDBOX_MODE={mode.value!r} requires a sandbox runtime, "
                "but MAIW_SANDBOX_RUNTIME is 'none'."
            )

        return cls(
            mode=mode,
            runtime_kind=runtime_kind,
            model_gateway_endpoint=source.get(
                "MAIW_SANDBOX_MODEL_GATEWAY_ENDPOINT",
                "http://maiw-api:8000/api/v1/inference",
            ),
            read_capability_endpoint=source.get(
                "MAIW_SANDBOX_READ_ENDPOINT",
                "http://maiw-api:8000/api/v1/capabilities/read",
            ),
            image_reference=source.get("MAIW_SANDBOX_IMAGE"),
            nemoclaw_version=source.get("MAIW_NEMOCLAW_VERSION"),
            openshell_version=source.get("MAIW_OPENSHELL_VERSION"),
        )


__all__ = [
    "SandboxConfig",
    "SandboxConfigurationError",
    "SandboxMode",
    "SandboxRuntimeKind",
]
