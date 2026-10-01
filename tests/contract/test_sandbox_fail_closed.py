# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Fail-closed behaviour, prompt-injection resistance, and the static payload audit.

The single most important assertion in this file is
``test_required_mode_never_reaches_the_inner_runtime``. Every other containment
property is downstream of it: a sandbox that silently degrades to unsandboxed
execution has not weakened containment, it has removed it while continuing to
report success.

The prompt-injection tests are deliberately not about prompts. A model that has
been talked into wanting a write still has to get the capability past
``authorize_capability``, which never consults the model, the prompt, or the
sandbox. Testing the refusal at that seam is testing the thing that actually
holds; testing it at the prompt would be testing a string.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest

from maiw_agents.contracts.agent import AgentDefinition, GovernanceBoundary
from maiw_agents.contracts.capability_policy import (
    CapabilityDeniedError,
    authorize_capability,
    build_capability_policy,
)
from maiw_agents.contracts.registry import SKILL_REGISTRY, CapabilityClass
from maiw_agents.contracts.runtime import (
    AgentExecutionContext,
    AgentRuntime,
    AgentTaskResult,
)
from maiw_agents.contracts.sop import SOPDefinition
from maiw_agents.contracts.task import AgentTaskState, AgentTaskStatus

from integrations.nemoclaw import (
    ContainerSandboxProvisioner,
    OpenShellSandboxProvisioner,
    SandboxAvailability,
    SandboxConfig,
    SandboxConfigurationError,
    SandboxMode,
    SandboxPolicyApplicationError,
    SandboxRuntimeKind,
    SandboxUnavailableError,
    SandboxedAgentRuntime,
    UnavailableSandboxProvisioner,
    container_run_args,
    render_sandbox_policy,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_PKG = REPO_ROOT / "packages" / "maiw-agents" / "maiw_agents"
INTEGRATION_PKG = REPO_ROOT / "integrations" / "nemoclaw"

CAPS = [
    "warehouse.wave.status",
    "warehouse.wave.evaluate_reprioritization",
    "warehouse.wave.reprioritize",
]


# ── Doubles ───────────────────────────────────────────────────────────────────


class RecordingRuntime:
    """An inner runtime that records whether it was ever reached."""

    RUNTIME_NAME = "recording"

    def __init__(self) -> None:
        self.calls = 0

    async def run_task(self, definition, sop, state, context) -> AgentTaskResult:
        self.calls += 1
        return AgentTaskResult(
            task_id=state.task_id,
            agent_id=definition.agent_id,
            sop_id=sop.id,
            sop_version=sop.version,
            final_status=AgentTaskStatus.WAITING_FOR_GOVERNANCE,
        )


class WorkingProvisioner:
    """A provisioner that succeeds, for the happy path."""

    def __init__(self) -> None:
        self.applied = []

    async def probe(self) -> SandboxAvailability:
        return SandboxAvailability(
            available=True,
            runtime_kind=SandboxRuntimeKind.OPENSHELL,
            detail="test double",
            version="0.0.0-test",
        )

    async def apply_policy(self, rendered) -> None:
        self.applied.append(rendered)


class PolicyRejectingProvisioner(WorkingProvisioner):
    """Available, but cannot apply the policy — the worst case."""

    async def apply_policy(self, rendered) -> None:
        raise SandboxPolicyApplicationError(
            reason="policy engine refused the ruleset",
            mode=SandboxMode.SANDBOX_REQUIRED,
        )


class ExplodingProvisioner(WorkingProvisioner):
    """Raises something unexpected, not a sandbox error."""

    async def apply_policy(self, rendered) -> None:
        raise RuntimeError("kernel module missing")


class ExplodingProbeProvisioner(WorkingProvisioner):
    async def probe(self) -> SandboxAvailability:
        raise OSError("daemon socket vanished")


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def definition() -> AgentDefinition:
    return AgentDefinition(
        agent_id="operations_coordination",
        version="1.0",
        objective="Resolve wave risk",
        domain="operations",
        allowed_capabilities=CAPS,
        allowed_subagents=[],
        output_contract="RecommendedAction",
        governance_boundary=GovernanceBoundary(),
    )


@pytest.fixture
def sop() -> SOPDefinition:
    return SOPDefinition(
        id="operations_coordination.wave_risk_resolution_v2",
        version="2.0",
        agent="operations_coordination",
        objective="Resolve wave risk",
        allowed_capabilities=CAPS,
        allowed_subagents=[],
        steps=[],
    )


@pytest.fixture
def state() -> AgentTaskState:
    return AgentTaskState(
        task_id="task-failclosed",
        agent_id="operations_coordination",
        sop_id="operations_coordination.wave_risk_resolution_v2",
        sop_version="2.0",
        objective="Resolve wave risk",
    )


@pytest.fixture
def context() -> AgentExecutionContext:
    return AgentExecutionContext(warehouse_id="wh-test", trace_id="trace-failclosed")


def _config(mode: SandboxMode, **overrides) -> SandboxConfig:
    base = dict(
        mode=mode,
        runtime_kind=SandboxRuntimeKind.OPENSHELL,
        model_gateway_endpoint="http://maiw-api:8000/api/v1/inference",
        read_capability_endpoint="http://maiw-api:8000/api/v1/capabilities/read",
    )
    base.update(overrides)
    return SandboxConfig(**base)


# ── Fail closed ───────────────────────────────────────────────────────────────


class TestFailClosed:
    async def test_required_mode_never_reaches_the_inner_runtime(
        self, definition, sop, state, context
    ):
        """
        The load-bearing assertion of the whole integration.

        Under SANDBOX_REQUIRED with no sandbox, the task must fail *and* the
        wrapped runtime must never have run. Asserting only the exception would
        pass even if the runtime had already executed and the error were raised
        afterwards.
        """
        inner = RecordingRuntime()
        runtime = SandboxedAgentRuntime(
            inner=inner,
            config=_config(SandboxMode.SANDBOX_REQUIRED),
            provisioner=UnavailableSandboxProvisioner(),
        )
        with pytest.raises(SandboxUnavailableError, match="Refusing to fall back"):
            await runtime.run_task(definition, sop, state, context)
        assert inner.calls == 0

    async def test_required_mode_fails_when_policy_cannot_be_applied(
        self, definition, sop, state, context
    ):
        """
        A sandbox running without its policy is worse than no sandbox: it looks
        contained in the logs. It must fail like an absent one.
        """
        inner = RecordingRuntime()
        runtime = SandboxedAgentRuntime(
            inner=inner,
            config=_config(SandboxMode.SANDBOX_REQUIRED),
            provisioner=PolicyRejectingProvisioner(),
        )
        with pytest.raises(SandboxPolicyApplicationError):
            await runtime.run_task(definition, sop, state, context)
        assert inner.calls == 0

    async def test_required_mode_fails_on_an_unexpected_provisioner_error(
        self, definition, sop, state, context
    ):
        inner = RecordingRuntime()
        runtime = SandboxedAgentRuntime(
            inner=inner,
            config=_config(SandboxMode.SANDBOX_REQUIRED),
            provisioner=ExplodingProvisioner(),
        )
        with pytest.raises(
            SandboxPolicyApplicationError, match="kernel module missing"
        ):
            await runtime.run_task(definition, sop, state, context)
        assert inner.calls == 0

    async def test_a_probe_that_raises_is_unavailable_not_available(
        self, definition, sop, state, context
    ):
        """An error during the probe has not proved availability."""
        inner = RecordingRuntime()
        runtime = SandboxedAgentRuntime(
            inner=inner,
            config=_config(SandboxMode.SANDBOX_REQUIRED),
            provisioner=ExplodingProbeProvisioner(),
        )
        with pytest.raises(SandboxUnavailableError):
            await runtime.run_task(definition, sop, state, context)
        assert inner.calls == 0

    async def test_preferred_mode_warns_and_continues(
        self, definition, sop, state, context, caplog
    ):
        inner = RecordingRuntime()
        runtime = SandboxedAgentRuntime(
            inner=inner,
            config=_config(SandboxMode.SANDBOX_PREFERRED),
            provisioner=UnavailableSandboxProvisioner(),
        )
        with caplog.at_level(logging.WARNING):
            result = await runtime.run_task(definition, sop, state, context)
        assert inner.calls == 1
        assert result.final_status is AgentTaskStatus.WAITING_FOR_GOVERNANCE
        assert any("SANDBOX UNAVAILABLE" in r.message for r in caplog.records)

    async def test_disabled_mode_delegates_without_rendering_a_policy(
        self, definition, sop, state, context
    ):
        inner = RecordingRuntime()
        runtime = SandboxedAgentRuntime(
            inner=inner,
            config=_config(SandboxMode.DISABLED, runtime_kind=SandboxRuntimeKind.NONE),
            provisioner=UnavailableSandboxProvisioner(),
        )
        await runtime.run_task(definition, sop, state, context)
        assert inner.calls == 1
        assert runtime.last_rendered_policy is None

    async def test_happy_path_applies_the_policy_before_running(
        self, definition, sop, state, context
    ):
        inner = RecordingRuntime()
        provisioner = WorkingProvisioner()
        runtime = SandboxedAgentRuntime(
            inner=inner,
            config=_config(SandboxMode.SANDBOX_REQUIRED),
            provisioner=provisioner,
        )
        result = await runtime.run_task(definition, sop, state, context)
        assert inner.calls == 1
        assert len(provisioner.applied) == 1
        applied = provisioner.applied[0]
        assert "WRITE" not in applied.allowed_capability_classes
        assert applied.network_default == "deny"
        assert applied.injected_credentials == ()
        assert result.final_status is AgentTaskStatus.WAITING_FOR_GOVERNANCE

    async def test_policy_is_not_broadened_across_restarts(
        self, definition, sop, state, context
    ):
        """
        A restarted sandbox re-renders rather than restoring. Two runs of the
        same task must grant the identical set — a policy that grew across a
        restart would be a privilege-escalation path through the crash handler.
        """
        provisioner = WorkingProvisioner()
        runtime = SandboxedAgentRuntime(
            inner=RecordingRuntime(),
            config=_config(SandboxMode.SANDBOX_REQUIRED),
            provisioner=provisioner,
        )
        await runtime.run_task(definition, sop, state, context)
        await runtime.run_task(definition, sop, state, context)
        first, second = provisioner.applied
        assert second.allowed_capability_ids == first.allowed_capability_ids
        assert second.allowed_capability_classes == first.allowed_capability_classes
        assert second.allowed_subagents == first.allowed_subagents


# ── Configuration fails closed too ────────────────────────────────────────────


class TestConfigurationFailsClosed:
    def test_unknown_mode_raises_rather_than_defaulting(self):
        """Defaulting a typo to DISABLED would silently unsandbox a deployment."""
        with pytest.raises(SandboxConfigurationError, match="MAIW_SANDBOX_MODE"):
            SandboxConfig.from_env({"MAIW_SANDBOX_MODE": "requried"})

    def test_sandbox_mode_without_a_runtime_raises(self):
        with pytest.raises(
            SandboxConfigurationError, match="requires a sandbox runtime"
        ):
            SandboxConfig.from_env({"MAIW_SANDBOX_MODE": "required"})

    def test_endpoint_with_embedded_credentials_is_rejected(self):
        with pytest.raises(ValueError, match="credentials"):
            _config(
                SandboxMode.SANDBOX_REQUIRED,
                model_gateway_endpoint="https://user:hunter2@maiw-api/api/v1/inference",
            )

    def test_governance_endpoint_is_rejected(self):
        with pytest.raises(ValueError, match="governance/execution"):
            _config(
                SandboxMode.SANDBOX_REQUIRED,
                read_capability_endpoint="http://maiw-api:8000/api/v1/actions",
            )

    def test_mount_outside_workspace_is_rejected(self):
        with pytest.raises(ValueError, match="/workspace/"):
            _config(SandboxMode.SANDBOX_REQUIRED, procedure_state_mount="/var/lib/maiw")

    def test_unqualified_config_does_not_claim_qualification(self):
        assert _config(SandboxMode.SANDBOX_REQUIRED).is_qualified is False

    def test_openshell_config_is_qualified_only_with_both_versions(self):
        assert (
            _config(
                SandboxMode.SANDBOX_REQUIRED,
                nemoclaw_version="0.1.0",
                openshell_version="0.1.0",
            ).is_qualified
            is True
        )
        assert (
            _config(SandboxMode.SANDBOX_REQUIRED, nemoclaw_version="0.1.0").is_qualified
            is False
        )


# ── Prompt injection ──────────────────────────────────────────────────────────


class TestPromptInjectionCannotObtainWriteAuthority:
    """
    A model persuaded to want a write still cannot have one.

    The refusal does not happen in the prompt layer, so these tests exercise the
    authorization seam directly — that is where a real injection would land
    after the model had already been convinced.
    """

    @pytest.fixture
    def policy(self, definition, sop):
        return build_capability_policy(
            definition=definition,
            sop=sop,
            agent_task_id="task-injection",
            runtime="deterministic",
        )

    @pytest.mark.parametrize(
        "capability_id",
        [
            cap_id
            for cap_id, entry in SKILL_REGISTRY.items()
            if entry.capability_class
            in (CapabilityClass.WRITE, CapabilityClass.EMERGENCY_WRITE)
        ],
    )
    async def test_every_registered_write_capability_is_denied(
        self, policy, capability_id
    ):
        with pytest.raises(CapabilityDeniedError):
            await authorize_capability(policy, capability_id)

    async def test_undeclared_capability_is_denied(self, policy):
        """Deny-by-default: a READ capability the SOP never named is still denied."""
        with pytest.raises(CapabilityDeniedError, match="allow-list"):
            await authorize_capability(policy, "warehouse.labor.capacity")

    async def test_invented_capability_is_denied(self, policy):
        """A capability that does not exist cannot be classified, so it is denied."""
        with pytest.raises(CapabilityDeniedError, match="registry"):
            await authorize_capability(policy, "warehouse.wave.please_just_write_it")

    async def test_a_write_capability_cannot_be_smuggled_by_claiming_a_read_class(
        self, policy
    ):
        """
        Caller-supplied class is not trusted over the registry for a *denied*
        class, and an id outside the allow-list is denied regardless.
        """
        with pytest.raises(CapabilityDeniedError):
            await authorize_capability(
                policy, "warehouse.wave.reprioritize_direct", "READ"
            )

    def test_the_rendered_policy_the_sandbox_receives_contains_no_write(self, policy):
        rendered = render_sandbox_policy(
            policy, config=_config(SandboxMode.SANDBOX_REQUIRED)
        )
        blob = repr(rendered)
        assert "_direct" not in blob
        assert "WRITE" not in rendered.allowed_capability_classes


# ── Static payload audit ──────────────────────────────────────────────────────


def _module_imports(path: Path) -> set[str]:
    """Top-level module names imported by a Python file, via AST."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


SANDBOX_PAYLOAD_MODULES = [
    AGENTS_PKG / "sop_engine" / "engine.py",
    AGENTS_PKG / "sop_engine" / "validators.py",
    AGENTS_PKG / "sop_engine" / "executor.py",
    AGENTS_PKG / "sop_engine" / "state_store.py",
    AGENTS_PKG / "runtime" / "deterministic.py",
    AGENTS_PKG / "runtime" / "deep_agents_runtime.py",
    AGENTS_PKG / "contracts" / "capability_policy.py",
    AGENTS_PKG / "contracts" / "procedure_state.py",
]
"""
The modules that would ship inside the sandbox image.

Deliberately enumerated rather than globbed over ``maiw_agents``: the package
also contains ``*/state_aware_ops.py``, which holds a ``DecisionEngine`` and is
host-side by design. A glob would either fail on those or be weakened to pass,
and neither tells the truth about what goes in the image.
"""


class TestSandboxPayloadIsWriteFree:
    @pytest.mark.parametrize("module", SANDBOX_PAYLOAD_MODULES, ids=lambda p: p.name)
    def test_no_execution_package_import(self, module: Path):
        assert module.exists(), f"{module} is missing"
        assert "maiw_execution" not in _module_imports(module)

    @pytest.mark.parametrize("module", SANDBOX_PAYLOAD_MODULES, ids=lambda p: p.name)
    def test_no_decision_engine_import(self, module: Path):
        """
        ``DecisionEngine`` is a governance component. The sandbox payload reasons
        and recommends; it does not get a vote on its own proposals.
        """
        assert "maiw_decision" not in _module_imports(module)

    @pytest.mark.parametrize("module", SANDBOX_PAYLOAD_MODULES, ids=lambda p: p.name)
    def test_no_action_executor_binding(self, module: Path):
        """
        Mentions in prose are fine and frequent — the modules document the
        boundary they sit on. What must not exist is a binding: an import, an
        attribute access, or a call.
        """
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and "ActionExecutor" in node.id:
                pytest.fail(f"{module.name} binds the name {node.id!r}")
            if isinstance(node, ast.Attribute) and "ActionExecutor" in node.attr:
                pytest.fail(f"{module.name} accesses attribute {node.attr!r}")

    def test_state_aware_ops_is_excluded_from_the_payload(self):
        """
        The audit's own premise, asserted.

        ``state_aware_ops`` really does import ``DecisionEngine`` — it is
        host-side orchestration. If it ever stopped doing so this exclusion
        would be stale, and a stale exclusion list is how a module quietly
        rejoins a payload it was removed from.
        """
        host_side = AGENTS_PKG / "operations" / "state_aware_ops.py"
        assert host_side.exists()
        assert "maiw_decision" in _module_imports(host_side)
        assert host_side not in SANDBOX_PAYLOAD_MODULES

    def test_integration_package_holds_no_credentials(self):
        """A secret-shaped scan over everything this phase added."""
        for path in sorted(INTEGRATION_PKG.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for needle in (
                "NVIDIA_API_KEY=",
                "MAIW_NIM_API_KEY=",
                "Bearer ",
                "-----BEGIN",
            ):
                assert needle not in text, f"{needle!r} in {path.name}"

    def test_integration_package_is_not_imported_by_maiw_agents(self):
        """
        The dependency points one way. ``maiw_agents`` must stay unaware that a
        sandbox exists, so that deleting this integration cannot break it.
        """
        for path in AGENTS_PKG.rglob("*.py"):
            assert "integrations.nemoclaw" not in path.read_text(encoding="utf-8"), (
                f"{path} imports the sandbox integration"
            )


# ── Container argument mapping ────────────────────────────────────────────────


class TestContainerArgumentMapping:
    def test_network_is_none_regardless_of_allowed_endpoints(self, definition, sop):
        """
        Allowed endpoints are reached through a host-managed egress proxy, not by
        giving the container a network namespace and an allow-list — that would
        put the allow-list inside the blast radius of what it constrains.
        """
        policy = build_capability_policy(
            definition=definition,
            sop=sop,
            agent_task_id="task-args",
            runtime="deterministic",
        )
        rendered = render_sandbox_policy(
            policy, config=_config(SandboxMode.SANDBOX_REQUIRED)
        )
        args = container_run_args(rendered)
        assert "--network=none" in args
        assert "--read-only" in args
        assert "--cap-drop=ALL" in args
        assert "--security-opt=no-new-privileges" in args
        assert not any(arg.startswith("--env") for arg in args)
        assert any("readonly=false" in a and "procedure_state" in a for a in args)
        assert any("readonly=true" in a and "sop_definitions" in a for a in args)


# ── Provisioners are honest about being unqualified ───────────────────────────


class TestProvisionerHonesty:
    async def test_openshell_provisioner_reports_unavailable_when_not_installed(self):
        availability = await OpenShellSandboxProvisioner().probe()
        assert availability.available is False
        assert availability.runtime_kind is SandboxRuntimeKind.OPENSHELL

    async def test_openshell_apply_policy_raises_rather_than_pretending(
        self, definition, sop
    ):
        policy = build_capability_policy(
            definition=definition,
            sop=sop,
            agent_task_id="task-honest",
            runtime="deterministic",
        )
        rendered = render_sandbox_policy(
            policy, config=_config(SandboxMode.SANDBOX_REQUIRED)
        )
        with pytest.raises(SandboxPolicyApplicationError, match="not implemented"):
            await OpenShellSandboxProvisioner().apply_policy(rendered)

    async def test_container_probe_reports_a_missing_binary(self):
        availability = await ContainerSandboxProvisioner(
            binary="definitely-not-a-container-runtime"
        ).probe()
        assert availability.available is False
        assert "PATH" in availability.detail
