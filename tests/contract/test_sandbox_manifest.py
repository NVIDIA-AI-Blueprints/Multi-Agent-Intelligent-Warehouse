# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
NemoClaw agent manifest: derived from policy, honest about qualification.

The manifest is what a sandbox operator reads. Two properties matter more than
its contents:

  it is *derived*    — a hand-written manifest is a second statement of the
                       boundary that can disagree with the first
  it is *honest*     — on a host with no NemoClaw installed it says
                       CONFIGURATION_PENDING rather than looking qualified

The checked-in ``agent_manifest.yaml`` is tested against the renderer so the two
cannot drift apart silently.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from maiw_agents.contracts.agent import AgentDefinition, GovernanceBoundary
from maiw_agents.contracts.capability_policy import build_capability_policy
from maiw_agents.contracts.sop import SOPDefinition

from integrations.nemoclaw import (
    MANIFEST_SCHEMA_VERSION,
    STATUS_CONFIGURATION_PENDING,
    STATUS_QUALIFIED,
    SandboxConfig,
    SandboxMode,
    SandboxRuntimeKind,
    render_agent_manifest,
    render_sandbox_policy,
)

MANIFEST_PATH = (
    Path(__file__).resolve().parents[2] / "integrations" / "nemoclaw" / "agent_manifest.yaml"
)

CAPS = [
    "warehouse.wave.status",
    "warehouse.wave.inspect_tasks",
    "warehouse.wave.evaluate_reprioritization",
    "warehouse.wave.reprioritize",
]


@pytest.fixture
def definition() -> AgentDefinition:
    return AgentDefinition(
        agent_id="operations_coordination",
        version="1.0",
        objective="Resolve wave risk before carrier cutoff",
        domain="operations",
        allowed_capabilities=CAPS,
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
        allowed_capabilities=CAPS,
        allowed_subagents=["labor_specialist"],
        steps=[],
    )


def _config(**overrides) -> SandboxConfig:
    base = dict(
        mode=SandboxMode.SANDBOX_REQUIRED,
        runtime_kind=SandboxRuntimeKind.OPENSHELL,
        model_gateway_endpoint="http://maiw-api:8000/api/v1/inference",
        read_capability_endpoint="http://maiw-api:8000/api/v1/capabilities/read",
    )
    base.update(overrides)
    return SandboxConfig(**base)


@pytest.fixture
def manifest(definition, sop):
    config = _config()
    policy = build_capability_policy(
        definition=definition, sop=sop,
        agent_task_id="task-manifest", runtime="deterministic",
    ).model_copy(update={"policy_id": "00000000-0000-4000-8000-000000000000"})
    return render_agent_manifest(
        render_sandbox_policy(policy, config=config), config=config
    )


class TestManifestDeclaresTheBoundary:
    def test_no_write_mcp_endpoints(self, manifest):
        assert manifest["mcp"]["write_servers"] == []
        assert manifest["mcp"]["write_servers_exposed"] is False

    def test_governance_components_are_not_in_the_sandbox(self, manifest):
        governance = manifest["governance"]
        assert governance["authority"] == "maiw_host"
        assert governance["action_executor_in_sandbox"] is False
        assert governance["decision_engine_in_sandbox"] is False

    def test_no_write_capability_classes(self, manifest):
        assert "WRITE" not in manifest["capabilities"]["allowed_classes"]
        assert "EMERGENCY_WRITE" not in manifest["capabilities"]["allowed_classes"]
        assert manifest["capabilities"]["denied_classes"] == [
            "EMERGENCY_WRITE", "WRITE",
        ]

    def test_network_is_deny_by_default(self, manifest):
        assert manifest["network"]["default"] == "deny"
        purposes = sorted(e["purpose"] for e in manifest["network"]["allowed"])
        assert purposes == ["inference", "read_capabilities"]

    def test_no_credentials_are_injected(self, manifest):
        assert manifest["credentials"]["injected"] == []
        assert manifest["credentials"]["custody"] == "host_only"

    def test_maiw_remains_the_model_selection_authority(self, manifest):
        """
        The hard rule of the inference design, asserted as manifest data.

        NemoClaw/OpenShell may proxy the transport. They may not become the
        model router — MAIW's ModelGateway carries the policy filter, the
        deployment resolver and the routing provenance, and a second router
        would silently bypass all three.
        """
        inference = manifest["inference"]
        assert inference["model_selection_authority"] == "maiw.ModelGateway"
        assert inference["use_platform_model_router"] is False
        assert inference["route"] == "maiw_model_gateway"

    def test_only_procedure_state_is_writable(self, manifest):
        assert manifest["filesystem"]["writable"] == ["/workspace/procedure_state"]
        assert manifest["filesystem"]["readable"] == ["/workspace/sop_definitions"]


class TestManifestIsHonestAboutQualification:
    def test_unqualified_host_renders_configuration_pending(self, manifest):
        assert manifest["status"] == STATUS_CONFIGURATION_PENDING
        assert manifest["platform"]["nemoclaw_version"] is None
        assert manifest["platform"]["openshell_version"] is None

    def test_qualified_config_renders_qualified(self, definition, sop):
        config = _config(
            nemoclaw_version="0.1.0",
            openshell_version="0.1.0",
            image_reference="nvcr.io/nvidia/maiw-agent:0.1.0",
        )
        policy = build_capability_policy(
            definition=definition, sop=sop,
            agent_task_id="task-manifest", runtime="deterministic",
        )
        rendered = render_agent_manifest(
            render_sandbox_policy(policy, config=config), config=config
        )
        assert rendered["status"] == STATUS_QUALIFIED

    def test_schema_version_is_alpha_until_qualified(self):
        """``v1alpha1`` records that this schema has never met a real NemoClaw."""
        assert MANIFEST_SCHEMA_VERSION.endswith("v1alpha1")


class TestManifestIsDeterministic:
    def test_same_inputs_render_an_equal_manifest(self, definition, sop):
        config = _config()
        policy = build_capability_policy(
            definition=definition, sop=sop,
            agent_task_id="task-manifest", runtime="deterministic",
        )
        rendered = render_sandbox_policy(policy, config=config)
        assert render_agent_manifest(rendered, config=config) == render_agent_manifest(
            rendered, config=config
        )

    def test_no_timestamp_leaks_into_the_manifest(self, manifest):
        blob = repr(manifest).lower()
        for needle in ("rendered_at", "timestamp", "generated_at"):
            assert needle not in blob


class TestCheckedInManifestMatchesTheRenderer:
    def test_manifest_file_exists_and_parses(self):
        assert MANIFEST_PATH.exists(), f"{MANIFEST_PATH} is missing"
        assert yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_checked_in_manifest_equals_the_rendered_one(self, manifest):
        """
        The committed draft is generated, not transcribed.

        A drifting checked-in manifest is how a reviewed boundary and a deployed
        boundary come apart, so the file is pinned to the renderer's output.
        """
        on_disk = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
        assert on_disk == manifest

    def test_checked_in_manifest_declares_configuration_pending(self):
        on_disk = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
        assert on_disk["status"] == STATUS_CONFIGURATION_PENDING
        assert on_disk["mcp"]["write_servers"] == []
        assert on_disk["credentials"]["injected"] == []
