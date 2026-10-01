# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
RuntimeCapabilityPolicy → sandbox policy: write isolation, monotonicity, determinism.

These are the tests that have to hold whether or not NemoClaw or OpenShell is
installed, because they are about what MAIW *hands* a sandbox rather than what a
sandbox does with it. A rendered policy that leaks a write capability is a
defect on a host with no sandbox at all — it just has no effect there yet.

The adversary assumed throughout is a compromised sandbox plus a caller that
builds a policy by hand to get around the renderer. That second one is why most
assertions here construct ``RenderedSandboxPolicy`` directly instead of going
through ``render_sandbox_policy``: a rule that only the renderer enforces is a
rule that the next integration forgets.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from maiw_agents.contracts.agent import AgentDefinition, GovernanceBoundary
from maiw_agents.contracts.capability_policy import (
    ALWAYS_DENIED_CAPABILITY_CLASSES,
    RuntimeCapabilityPolicy,
    build_capability_policy,
)
from maiw_agents.contracts.registry import SKILL_REGISTRY, CapabilityClass
from maiw_agents.contracts.sop import SOPDefinition

from integrations.nemoclaw import (
    RenderedSandboxPolicy,
    SandboxConfig,
    SandboxMode,
    SandboxNetworkEndpoint,
    SandboxPolicyError,
    SandboxRuntimeKind,
    render_policy_yaml,
    render_sandbox_policy,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

READ_CAPS = ["warehouse.wave.status", "warehouse.wave.inspect_tasks"]
ANALYTICAL_CAPS = ["warehouse.wave.evaluate_reprioritization"]
PROPOSAL_CAPS = ["warehouse.wave.reprioritize"]
WRITE_CAPS = [
    cap_id
    for cap_id, entry in SKILL_REGISTRY.items()
    if entry.capability_class is CapabilityClass.WRITE
]


@pytest.fixture
def definition() -> AgentDefinition:
    return AgentDefinition(
        agent_id="operations_coordination",
        version="1.0",
        objective="Resolve wave risk before carrier cutoff",
        domain="operations",
        allowed_capabilities=[*READ_CAPS, *ANALYTICAL_CAPS, *PROPOSAL_CAPS],
        allowed_subagents=["labor_specialist"],
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
        allowed_capabilities=[*READ_CAPS, *ANALYTICAL_CAPS, *PROPOSAL_CAPS],
        allowed_subagents=["labor_specialist"],
        steps=[],
    )


@pytest.fixture
def config() -> SandboxConfig:
    return SandboxConfig(
        mode=SandboxMode.SANDBOX_REQUIRED,
        runtime_kind=SandboxRuntimeKind.OPENSHELL,
        model_gateway_endpoint="http://maiw-api:8000/api/v1/inference",
        read_capability_endpoint="http://maiw-api:8000/api/v1/capabilities/read",
    )


@pytest.fixture
def policy(definition: AgentDefinition, sop: SOPDefinition) -> RuntimeCapabilityPolicy:
    return build_capability_policy(
        definition=definition,
        sop=sop,
        agent_task_id="task-sandbox-1",
        runtime="deterministic",
    )


def _rendered_kwargs(policy: RuntimeCapabilityPolicy, **overrides):
    """Minimal valid kwargs for a hand-built RenderedSandboxPolicy."""
    base = dict(
        source_policy_id=policy.policy_id,
        source_policy_revision=policy.policy_revision,
        agent_task_id=policy.agent_task_id,
        sop_id=policy.sop_id,
        sop_version=policy.sop_version,
        runtime=policy.runtime,
        policy_profile="maiw-readonly-reasoning",
        allowed_capability_classes=frozenset({"READ"}),
        denied_capability_classes=ALWAYS_DENIED_CAPABILITY_CLASSES,
        allowed_capability_ids=frozenset({"warehouse.wave.status"}),
        writable_paths=("/workspace/procedure_state",),
        readable_paths=("/workspace/sop_definitions",),
    )
    base.update(overrides)
    return base


# ── Write isolation ───────────────────────────────────────────────────────────


class TestWriteIsolation:
    """WRITE has four possible routes into a sandbox policy. All four are shut."""

    def test_renderer_excludes_write_capability_classes(self, policy, config):
        rendered = render_sandbox_policy(policy, config=config)
        assert "WRITE" not in rendered.allowed_capability_classes
        assert "EMERGENCY_WRITE" not in rendered.allowed_capability_classes
        assert ALWAYS_DENIED_CAPABILITY_CLASSES <= rendered.denied_capability_classes

    def test_renderer_excludes_write_capability_ids(self, policy, config):
        rendered = render_sandbox_policy(policy, config=config)
        for cap_id in rendered.allowed_capability_ids:
            entry = SKILL_REGISTRY[cap_id]
            assert entry.capability_class is not CapabilityClass.WRITE
            assert entry.capability_class is not CapabilityClass.EMERGENCY_WRITE

    def test_no_write_shaped_network_endpoint(self, policy, config):
        rendered = render_sandbox_policy(policy, config=config)
        endpoints = [ep.endpoint.lower() for ep in rendered.allowed_network_endpoints]
        assert endpoints, "a sandbox with no endpoints could not do inference"
        for endpoint in endpoints:
            assert "write" not in endpoint
            assert "execute" not in endpoint
            assert "approve" not in endpoint

    @pytest.mark.parametrize("denied_class", sorted(ALWAYS_DENIED_CAPABILITY_CLASSES))
    def test_hand_built_policy_cannot_allow_a_write_class(self, policy, denied_class):
        """Route 1: naming the class directly on a hand-built policy."""
        with pytest.raises((SandboxPolicyError, ValidationError)):
            RenderedSandboxPolicy(
                **_rendered_kwargs(
                    policy,
                    allowed_capability_classes=frozenset({"READ", denied_class}),
                )
            )

    @pytest.mark.skipif(not WRITE_CAPS, reason="no WRITE capability registered")
    def test_hand_built_policy_cannot_allow_a_write_capability_id(self, policy):
        """Route 2: naming a write capability by id, sidestepping the class list."""
        with pytest.raises((SandboxPolicyError, ValidationError)):
            RenderedSandboxPolicy(
                **_rendered_kwargs(
                    policy,
                    allowed_capability_ids=frozenset({WRITE_CAPS[0]}),
                )
            )

    def test_hand_built_policy_cannot_drop_the_deny_list(self, policy):
        with pytest.raises((SandboxPolicyError, ValidationError)):
            RenderedSandboxPolicy(
                **_rendered_kwargs(policy, denied_capability_classes=frozenset())
            )

    def test_write_shaped_endpoint_is_rejected(self):
        """Route 3: reaching a write surface over the network."""
        with pytest.raises((SandboxPolicyError, ValidationError)):
            SandboxNetworkEndpoint(
                endpoint="http://maiw-api:8000/api/v1/actions/execute",
                purpose="read_capabilities",
            )

    def test_unregistered_capability_is_rejected(self, policy):
        """A class MAIW cannot verify is a class MAIW does not vouch for."""
        with pytest.raises((SandboxPolicyError, ValidationError)):
            RenderedSandboxPolicy(
                **_rendered_kwargs(
                    policy,
                    allowed_capability_ids=frozenset({"warehouse.wave.invented"}),
                )
            )

    def test_proposal_capability_is_allowed_and_is_not_a_write(self, policy, config):
        """
        PROPOSAL-class capabilities survive rendering, and that is correct.

        ``warehouse.wave.reprioritize`` builds an ``ActionProposal`` locally; the
        capability that actually writes is ``warehouse.wave.reprioritize_direct``,
        which is WRITE-class and appears on no policy. Conflating the two would
        either break every SOP or hide a real write — so the distinction is
        asserted rather than assumed.
        """
        rendered = render_sandbox_policy(policy, config=config)
        assert "warehouse.wave.reprioritize" in rendered.allowed_capability_ids
        assert (
            "warehouse.wave.reprioritize_direct" not in rendered.allowed_capability_ids
        )
        assert (
            SKILL_REGISTRY["warehouse.wave.reprioritize_direct"].capability_class
            is CapabilityClass.WRITE
        )


# ── Credentials ───────────────────────────────────────────────────────────────


class TestCredentialCustody:
    def test_renderer_injects_no_credentials(self, policy, config):
        rendered = render_sandbox_policy(policy, config=config)
        assert rendered.injected_credentials == ()
        assert rendered.managed_credentials == ()
        assert rendered.credential_custody == "host_only"

    def test_rendered_policy_contains_no_secret_shaped_text(self, policy, config):
        """
        A rendered policy is logged, diffed and written to disk. It has to be
        safe to treat as non-secret, so nothing secret-shaped may appear in it.
        """
        rendered = render_sandbox_policy(policy, config=config)
        blob = f"{rendered!r}{render_policy_yaml(rendered)}".lower()
        for needle in ("password", "api_key", "apikey", "secret", "bearer", "token"):
            assert needle not in blob, f"{needle!r} appears in the rendered policy"

    def test_hand_built_policy_cannot_inject_credentials(self, policy):
        with pytest.raises((SandboxPolicyError, ValidationError)):
            RenderedSandboxPolicy(
                **_rendered_kwargs(policy, injected_credentials=("NVIDIA_API_KEY",))
            )


# ── Network ───────────────────────────────────────────────────────────────────


class TestNetworkPolicy:
    def test_network_is_deny_by_default(self, policy, config):
        rendered = render_sandbox_policy(policy, config=config)
        assert rendered.network_default == "deny"

    def test_only_inference_and_read_endpoints_are_allowed(self, policy, config):
        rendered = render_sandbox_policy(policy, config=config)
        purposes = sorted(ep.purpose for ep in rendered.allowed_network_endpoints)
        assert purposes == ["inference", "read_capabilities"]

    def test_hand_built_policy_cannot_set_network_default_allow(self, policy):
        with pytest.raises((SandboxPolicyError, ValidationError)):
            RenderedSandboxPolicy(**_rendered_kwargs(policy, network_default="allow"))


# ── Filesystem ────────────────────────────────────────────────────────────────


class TestFilesystemPolicy:
    def test_only_procedure_state_is_writable(self, policy, config):
        rendered = render_sandbox_policy(policy, config=config)
        assert rendered.writable_paths == (config.procedure_state_mount,)

    def test_sop_definitions_are_read_only(self, policy, config):
        rendered = render_sandbox_policy(policy, config=config)
        assert config.sop_definitions_mount in rendered.readable_paths
        assert config.sop_definitions_mount not in rendered.writable_paths

    def test_path_cannot_escape_workspace(self, policy):
        with pytest.raises((SandboxPolicyError, ValidationError)):
            RenderedSandboxPolicy(**_rendered_kwargs(policy, writable_paths=("/etc",)))

    def test_path_cannot_be_writable_and_readable(self, policy):
        with pytest.raises((SandboxPolicyError, ValidationError)):
            RenderedSandboxPolicy(
                **_rendered_kwargs(
                    policy,
                    writable_paths=("/workspace/shared",),
                    readable_paths=("/workspace/shared",),
                )
            )


# ── Monotonicity ──────────────────────────────────────────────────────────────


class TestMonotonicity:
    def test_rendered_policy_is_a_subset_of_the_maiw_policy(self, policy, config):
        rendered = render_sandbox_policy(policy, config=config)
        assert rendered.is_narrower_or_equal_to(policy)
        rendered.assert_not_broadened(policy)

    def test_broadened_policy_is_detected(self, policy, config):
        """
        A rendering that gained a capability the MAIW policy never granted.

        Constructed by rendering against a *wider* policy and then comparing to
        the narrow one — the same shape as a sandbox policy outliving a SOP that
        was tightened underneath it.
        """
        wide = policy.model_copy(
            update={
                "allowed_capability_ids": policy.allowed_capability_ids
                | {"warehouse.labor.capacity"},
                "allowed_capability_classes": policy.allowed_capability_classes,
            }
        )
        rendered_wide = render_sandbox_policy(wide, config=config)
        assert not rendered_wide.is_narrower_or_equal_to(policy)
        with pytest.raises(SandboxPolicyError, match="broadened"):
            rendered_wide.assert_not_broadened(policy)

    def test_rendering_twice_does_not_grow_the_grant(self, policy, config):
        """A restart re-renders; a re-render must not accumulate authority."""
        first = render_sandbox_policy(policy, config=config)
        second = render_sandbox_policy(policy, config=config)
        assert second.allowed_capability_ids == first.allowed_capability_ids
        second.assert_not_broadened(policy)
        assert second.is_narrower_or_equal_to(policy)

    def test_narrowed_sop_narrows_the_rendered_policy(self, definition, config):
        """The SOP is the narrower of the two allow-lists and still wins."""
        narrow_sop = SOPDefinition(
            id="operations_coordination.wave_risk_resolution_v2",
            version="2.0",
            agent="operations_coordination",
            objective="Resolve wave risk",
            allowed_capabilities=["warehouse.wave.status"],
            allowed_subagents=[],
            steps=[],
        )
        narrow_policy = build_capability_policy(
            definition=definition,
            sop=narrow_sop,
            agent_task_id="task-sandbox-1",
            runtime="deterministic",
        )
        rendered = render_sandbox_policy(narrow_policy, config=config)
        assert rendered.allowed_capability_ids == frozenset({"warehouse.wave.status"})


# ── Immutability ──────────────────────────────────────────────────────────────


class TestImmutability:
    def test_rendered_policy_is_frozen(self, policy, config):
        rendered = render_sandbox_policy(policy, config=config)
        with pytest.raises(ValidationError):
            rendered.allowed_capability_classes = frozenset({"READ", "WRITE"})

    def test_config_is_frozen(self, config):
        with pytest.raises(ValidationError):
            config.mode = SandboxMode.DISABLED

    def test_endpoint_is_frozen(self, policy, config):
        rendered = render_sandbox_policy(policy, config=config)
        with pytest.raises(ValidationError):
            rendered.allowed_network_endpoints[0].endpoint = "http://evil/"


# ── Determinism + golden ──────────────────────────────────────────────────────


class TestDeterminism:
    def test_same_inputs_render_identical_yaml(self, policy, config):
        a = render_policy_yaml(render_sandbox_policy(policy, config=config))
        b = render_policy_yaml(render_sandbox_policy(policy, config=config))
        assert a == b

    def test_capability_set_order_does_not_affect_output(self, policy, config):
        """
        frozenset iteration order is not stable across processes. If it leaked
        into the YAML, two identically-configured deployments would show a
        spurious policy diff — and a real one would be invisible in the noise.
        """
        shuffled = policy.model_copy(
            update={
                "allowed_capability_ids": frozenset(
                    reversed(sorted(policy.allowed_capability_ids))
                )
            }
        )
        assert render_policy_yaml(
            render_sandbox_policy(policy, config=config)
        ) == render_policy_yaml(render_sandbox_policy(shuffled, config=config))

    def test_golden_yaml(self, definition, sop, config):
        """
        The full rendered policy for Proof SOP A, pinned.

        A golden test on a security boundary earns its maintenance cost: any
        change to what the sandbox is granted shows up here as a reviewable diff
        rather than as a passing test suite.
        """
        pinned = build_capability_policy(
            definition=definition,
            sop=sop,
            agent_task_id="task-golden",
            runtime="deterministic",
        ).model_copy(update={"policy_id": "00000000-0000-4000-8000-000000000000"})

        actual = render_policy_yaml(render_sandbox_policy(pinned, config=config))
        expected = """\
# Generated by MAIW from RuntimeCapabilityPolicy — do not edit by hand.
# Regenerate with integrations.nemoclaw.render_sandbox_policy().
policy_id: 00000000-0000-4000-8000-000000000000
policy_revision: 1
policy_profile: maiw-readonly-reasoning
agent_task_id: task-golden
sop_id: operations_coordination.wave_risk_resolution_v2
sop_version: 2.0
runtime: deterministic

network:
  default: deny
  allowed:
    - endpoint: http://maiw-api:8000/api/v1/inference
      purpose: inference
    - endpoint: http://maiw-api:8000/api/v1/capabilities/read
      purpose: read_capabilities

filesystem:
  writable:
    - /workspace/procedure_state
  readable:
    - /workspace/sop_definitions

capabilities:
  allowed_classes: [ANALYTICAL, PROPOSAL, READ]
  denied_classes: [EMERGENCY_WRITE, WRITE]
  allowed_ids:
    - warehouse.wave.evaluate_reprioritization
    - warehouse.wave.inspect_tasks
    - warehouse.wave.reprioritize
    - warehouse.wave.status
  allowed_subagents:
    - labor_specialist

credentials:
  custody: host_only
  managed: []
  injected: []  # empty — the sandbox holds no credentials
"""
        assert actual == expected
