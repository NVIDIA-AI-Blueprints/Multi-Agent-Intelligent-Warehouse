# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
The sandbox boundary as an ``AgentRuntime`` decorator.

``SandboxedAgentRuntime`` wraps an existing runtime — ``MAIWDeterministicRuntime``
or ``DeepAgentsRuntime``, unmodified — and adds exactly three things around it:

    1. render the MAIW capability policy into a sandbox policy
    2. obtain a sandbox and apply that policy, or fail closed
    3. delegate to the wrapped runtime

It reimplements no step sequencing, no capability check, no governance
transition. If it did, there would be two implementations of MAIW's operational
semantics and they would drift — which is the failure mode the whole
containment-not-migration principle exists to avoid.

    OpenShell enforces the security boundary; NemoClaw packages and operates it;
    MAIW continues to define what the agent is allowed to do and remains the
    sole authority over warehouse actions.

The decorator is the "packages and operates it" half. The authority half is
already in ``maiw_agents.contracts.capability_policy`` and stays there.

**What a sandbox does not do.** It does not authorise anything. Every capability
check that runs unsandboxed still runs sandboxed, in the same place, through the
same ``authorize_step``. The sandbox is a second wall behind the first, for the
case where the first is defeated by a bug. A deployment that treated the sandbox
as the control and relaxed the policy would have fewer walls, not more.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from maiw_agents.contracts.agent import AgentDefinition
from maiw_agents.contracts.capability_policy import (
    RuntimeCapabilityPolicy,
    build_capability_policy,
)
from maiw_agents.contracts.runtime import (
    AgentExecutionContext,
    AgentRuntime,
    AgentTaskResult,
)
from maiw_agents.contracts.sop import SOPDefinition
from maiw_agents.contracts.task import AgentTaskState

from .sandbox_config import SandboxConfig, SandboxMode, SandboxRuntimeKind
from .sandbox_policy import RenderedSandboxPolicy, render_sandbox_policy

logger = logging.getLogger(__name__)


# ── Errors ────────────────────────────────────────────────────────────────────

class SandboxUnavailableError(RuntimeError):
    """
    A sandbox was required and could not be provided.

    Raised rather than returned. A caller that forgets to inspect a returned
    status silently runs unsandboxed; a caller that forgets to catch an
    exception fails the task. Under ``SANDBOX_REQUIRED`` the second is the only
    acceptable outcome, so this is an exception.
    """

    def __init__(self, *, reason: str, mode: SandboxMode) -> None:
        self.reason = reason
        self.mode = mode
        super().__init__(
            f"sandbox required (mode={mode.value}) but unavailable: {reason}. "
            "Refusing to fall back to unsandboxed execution."
        )


class SandboxPolicyApplicationError(SandboxUnavailableError):
    """
    The sandbox started but its policy could not be applied.

    A subclass of unavailability on purpose. A sandbox running without its
    policy is not a partially-contained sandbox — it is an uncontained process
    that happens to be in a container, which is strictly worse than no sandbox
    because it looks contained in the logs.
    """


# ── Availability ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SandboxAvailability:
    """Whether a sandbox can be provided, and what is backing it."""

    available: bool
    runtime_kind: SandboxRuntimeKind
    detail: str
    version: str | None = None


# ── Provisioner seam ──────────────────────────────────────────────────────────

@runtime_checkable
class SandboxProvisioner(Protocol):
    """
    The seam a concrete sandbox technology implements.

    Two methods, deliberately. A provisioner reports whether it can contain a
    workload and applies a policy to it. It does not get to inspect the policy's
    contents and negotiate, does not return a modified policy, and has no
    method that could report partial success — ``apply_policy`` either applies
    the whole policy or raises.
    """

    async def probe(self) -> SandboxAvailability:
        """Report whether a sandbox can be created right now."""
        ...

    async def apply_policy(self, rendered: RenderedSandboxPolicy) -> None:
        """
        Apply the rendered policy to the sandbox, or raise.

        Must be all-or-nothing. A provisioner that applied the filesystem rules
        but failed on the network rules must raise, not return.
        """
        ...


class UnavailableSandboxProvisioner:
    """
    A provisioner that is honest about providing nothing.

    The default, and the one that is correct on a host where neither NemoClaw
    nor OpenShell is installed. Paired with ``SANDBOX_REQUIRED`` it makes every
    task fail — which is the point: a deployment that claims containment on a
    host that cannot provide it should not run.
    """

    def __init__(self, *, detail: str = "no sandbox runtime configured") -> None:
        self._detail = detail

    async def probe(self) -> SandboxAvailability:
        return SandboxAvailability(
            available=False,
            runtime_kind=SandboxRuntimeKind.NONE,
            detail=self._detail,
        )

    async def apply_policy(self, rendered: RenderedSandboxPolicy) -> None:
        raise SandboxPolicyApplicationError(
            reason=self._detail, mode=SandboxMode.SANDBOX_REQUIRED
        )


class OpenShellSandboxProvisioner:
    """
    The intended production provisioner — OpenShell under NemoClaw.

    Unimplemented, and failing rather than approximating. OpenShell is not
    installed on any host this has run on, so there is no API to write against
    and no version to pin. Writing a plausible-looking implementation against a
    guessed API would produce something that imports cleanly, passes a mocked
    test, and does not contain anything.

    ``probe`` reports unavailable, so ``SANDBOX_REQUIRED`` fails closed and
    ``SANDBOX_PREFERRED`` warns. Neither silently pretends.

    To qualify: install NemoClaw and OpenShell, pin both versions in
    ``SandboxConfig``, implement ``apply_policy`` against the real API, and run
    the ``sandbox``-marked tests. See
    ``docs/architecture/NEMOCLAW_OPENSHELL_INTEGRATION.md`` § Current
    qualification status.
    """

    REQUIRES = "nemoclaw + openshell"

    async def probe(self) -> SandboxAvailability:
        try:  # pragma: no cover — exercised only on a qualified host
            import openshell  # type: ignore[import-not-found]  # noqa: F401
        except ImportError:
            return SandboxAvailability(
                available=False,
                runtime_kind=SandboxRuntimeKind.OPENSHELL,
                detail=(
                    "openshell is not importable on this host; the OpenShell "
                    "boundary cannot be created"
                ),
            )
        return SandboxAvailability(  # pragma: no cover
            available=False,
            runtime_kind=SandboxRuntimeKind.OPENSHELL,
            detail=(
                "openshell is importable but the MAIW adapter is not yet "
                "implemented against a pinned version"
            ),
        )

    async def apply_policy(self, rendered: RenderedSandboxPolicy) -> None:
        raise SandboxPolicyApplicationError(
            reason=(
                "OpenShellSandboxProvisioner.apply_policy is not implemented; "
                "NemoClaw/OpenShell were not available to qualify against"
            ),
            mode=SandboxMode.SANDBOX_REQUIRED,
        )


class ContainerSandboxProvisioner:
    """
    An OCI-container boundary proxy, for hosts without OpenShell.

    Enforces the same rendered policy shape OpenShell would — deny-by-default
    network, one writable mount, read-only SOP definitions, no injected
    credentials — using a container runtime. ``probe`` checks that a runtime
    binary exists and that its daemon answers.

    This is *weaker* than OpenShell and the documentation says so. A container
    with ``--network=none`` and read-only mounts is a real boundary, but it is
    not the boundary this integration is designed around, and a deployment
    using it should know which one it has.
    """

    def __init__(self, *, binary: str = "docker", probe_timeout: float = 20.0) -> None:
        self._binary = binary
        self._probe_timeout = probe_timeout

    async def probe(self) -> SandboxAvailability:
        path = shutil.which(self._binary)
        if path is None:
            return SandboxAvailability(
                available=False,
                runtime_kind=SandboxRuntimeKind.CONTAINER,
                detail=f"{self._binary!r} is not on PATH",
            )
        try:
            proc = await asyncio.create_subprocess_exec(
                path, "info", "--format", "{{.ServerVersion}}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self._probe_timeout
            )
        except (asyncio.TimeoutError, OSError) as exc:
            return SandboxAvailability(
                available=False,
                runtime_kind=SandboxRuntimeKind.CONTAINER,
                detail=f"{self._binary} probe failed: {exc}",
            )

        if proc.returncode != 0:
            return SandboxAvailability(
                available=False,
                runtime_kind=SandboxRuntimeKind.CONTAINER,
                detail=(
                    f"{self._binary} daemon unreachable: "
                    f"{stderr.decode(errors='replace').strip()[:200]}"
                ),
            )

        version = stdout.decode(errors="replace").strip() or None
        return SandboxAvailability(
            available=True,
            runtime_kind=SandboxRuntimeKind.CONTAINER,
            detail=f"{self._binary} daemon reachable",
            version=version,
        )

    async def apply_policy(self, rendered: RenderedSandboxPolicy) -> None:
        """
        Translate the rendered policy into container runtime arguments.

        Not implemented: doing so means owning container lifecycle — creating
        it, streaming the procedure in and the recommendation out, reaping it on
        failure — which is NemoClaw's job in the target architecture, not
        MAIW's. Phase 20A stops at the contract and the probe deliberately
        rather than growing a second container operator that NemoClaw would
        later replace.

        ``container_run_args`` below renders the arguments this would use, so
        the mapping is reviewable and testable without MAIW running containers.
        """
        raise SandboxPolicyApplicationError(
            reason=(
                "ContainerSandboxProvisioner.apply_policy is not implemented; "
                "container lifecycle is NemoClaw's responsibility. See "
                "container_run_args() for the policy→runtime argument mapping."
            ),
            mode=SandboxMode.SANDBOX_REQUIRED,
        )


def container_run_args(rendered: RenderedSandboxPolicy) -> list[str]:
    """
    The container-runtime arguments a rendered policy maps onto.

    Separated from ``apply_policy`` so the *mapping* can be reviewed and tested
    without MAIW taking on container lifecycle. Read this to answer "what would
    the boundary actually be?" without starting anything.

    Network is ``none`` unconditionally. The allowed endpoints in the policy are
    reachable through a host-managed egress proxy, not by relaxing this flag:
    handing the container a network namespace and an allow-list would put the
    allow-list inside the blast radius of the thing it constrains.
    """
    args = [
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
    ]
    for path in sorted(rendered.writable_paths):
        args.append(f"--mount=type=bind,target={path},readonly=false")
    for path in sorted(rendered.readable_paths):
        args.append(f"--mount=type=bind,target={path},readonly=true")
    # No --env flags are emitted: injected_credentials is empty by construction
    # and the environment is not a policy surface.
    return args


# ── The decorator ─────────────────────────────────────────────────────────────

class SandboxedAgentRuntime:
    """
    An ``AgentRuntime`` that establishes a sandbox boundary before delegating.

    Implements the ``AgentRuntime`` Protocol structurally, so it is substitutable
    anywhere a runtime is expected and composes with either concrete runtime.

    The wrapped runtime is unaware it is sandboxed. That is the containment
    property stated as a code fact: if ``SandboxedAgentRuntime`` were deleted,
    MAIW's capability enforcement, governance handoff and procedure persistence
    would be unchanged, and only the second wall would be gone.
    """

    RUNTIME_NAME = "sandboxed"

    def __init__(
        self,
        *,
        inner: AgentRuntime,
        config: SandboxConfig,
        provisioner: SandboxProvisioner | None = None,
    ) -> None:
        self._inner = inner
        self._config = config
        self._provisioner = provisioner or _default_provisioner(config)
        self._last_rendered_policy: RenderedSandboxPolicy | None = None
        self._last_availability: SandboxAvailability | None = None

    # ── Introspection (host-side only) ────────────────────────────────────────

    @property
    def config(self) -> SandboxConfig:
        return self._config

    @property
    def last_rendered_policy(self) -> RenderedSandboxPolicy | None:
        """The most recent rendering, for audit and for tests. Never sent in."""
        return self._last_rendered_policy

    @property
    def last_availability(self) -> SandboxAvailability | None:
        return self._last_availability

    # ── AgentRuntime ──────────────────────────────────────────────────────────

    async def run_task(
        self,
        definition: AgentDefinition,
        sop: SOPDefinition,
        state: AgentTaskState,
        context: AgentExecutionContext,
    ) -> AgentTaskResult:
        """
        Establish the boundary, then run the wrapped runtime inside it.

        Order matters and is not an implementation detail. The policy is built
        and rendered *before* the sandbox is consulted, so a policy that cannot
        be rendered safely fails the task without anything having been started.
        The sandbox is then asked to enforce a policy that already exists rather
        than being asked what it is willing to enforce.
        """
        if self._config.mode is SandboxMode.DISABLED:
            logger.debug(
                "sandbox disabled; delegating directly to %s",
                type(self._inner).__name__,
            )
            return await self._inner.run_task(definition, sop, state, context)

        policy = build_capability_policy(
            definition=definition,
            sop=sop,
            agent_task_id=state.task_id,
            runtime=getattr(self._inner, "RUNTIME_NAME", self.RUNTIME_NAME),
        )
        rendered = render_sandbox_policy(policy, config=self._config)
        self._last_rendered_policy = rendered

        await self._establish_boundary(rendered, policy)

        return await self._inner.run_task(definition, sop, state, context)

    # ── Boundary establishment ────────────────────────────────────────────────

    async def _establish_boundary(
        self,
        rendered: RenderedSandboxPolicy,
        policy: RuntimeCapabilityPolicy,
    ) -> None:
        """
        Obtain a sandbox and apply the policy, honouring the configured mode.

        There is no branch in this method that reaches the wrapped runtime with
        ``SANDBOX_REQUIRED`` set and no applied policy. Every failure path under
        that mode raises.
        """
        mode = self._config.mode

        availability = await self._probe()
        self._last_availability = availability

        if not availability.available:
            if mode is SandboxMode.SANDBOX_REQUIRED:
                raise SandboxUnavailableError(
                    reason=availability.detail, mode=mode
                )
            logger.warning(
                "SANDBOX UNAVAILABLE — continuing unsandboxed (mode=%s): %s. "
                "MAIW capability policy %s still applies; the sandbox was the "
                "second wall, not the only one.",
                mode.value, availability.detail, policy.policy_id,
            )
            return

        try:
            await self._provisioner.apply_policy(rendered)
        except SandboxUnavailableError:
            # Already the right shape; re-raise under REQUIRED, degrade otherwise.
            if mode is SandboxMode.SANDBOX_REQUIRED:
                raise
            logger.warning(
                "SANDBOX POLICY NOT APPLIED — continuing unsandboxed (mode=%s)",
                mode.value,
            )
            return
        except Exception as exc:  # noqa: BLE001 — any failure is a failure to contain
            if mode is SandboxMode.SANDBOX_REQUIRED:
                raise SandboxPolicyApplicationError(
                    reason=f"{type(exc).__name__}: {exc}", mode=mode
                ) from exc
            logger.warning(
                "SANDBOX POLICY NOT APPLIED — continuing unsandboxed (mode=%s): "
                "%s: %s",
                mode.value, type(exc).__name__, exc,
            )
            return

        logger.info(
            "sandbox boundary established: runtime=%s policy=%s profile=%s "
            "capabilities=%d network_default=deny credentials=0",
            availability.runtime_kind.value,
            rendered.source_policy_id,
            rendered.policy_profile,
            len(rendered.allowed_capability_ids),
        )

    async def _probe(self) -> SandboxAvailability:
        """Probe the provisioner, converting an unexpected failure into unavailability."""
        try:
            return await self._provisioner.probe()
        except Exception as exc:  # noqa: BLE001 — a probe that errors has not proved availability
            logger.warning(
                "sandbox probe raised %s: %s — treating as unavailable",
                type(exc).__name__, exc,
            )
            return SandboxAvailability(
                available=False,
                runtime_kind=self._config.runtime_kind,
                detail=f"probe raised {type(exc).__name__}: {exc}",
            )


def _default_provisioner(config: SandboxConfig) -> SandboxProvisioner:
    """Pick a provisioner from the configured runtime kind."""
    if config.runtime_kind is SandboxRuntimeKind.OPENSHELL:
        return OpenShellSandboxProvisioner()
    if config.runtime_kind is SandboxRuntimeKind.CONTAINER:
        return ContainerSandboxProvisioner()
    return UnavailableSandboxProvisioner()


__all__ = [
    "ContainerSandboxProvisioner",
    "OpenShellSandboxProvisioner",
    "SandboxAvailability",
    "SandboxPolicyApplicationError",
    "SandboxProvisioner",
    "SandboxUnavailableError",
    "SandboxedAgentRuntime",
    "UnavailableSandboxProvisioner",
    "container_run_args",
]
