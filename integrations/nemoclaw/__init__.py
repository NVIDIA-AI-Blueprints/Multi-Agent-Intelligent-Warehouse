# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW ↔ NemoClaw/OpenShell containment integration.

    OpenShell enforces the security boundary; NemoClaw packages and operates it;
    MAIW continues to define what the agent is allowed to do and remains the
    sole authority over warehouse actions.

This package adds a sandbox boundary around an existing MAIW agent runtime. It
is **containment, not migration**: no MAIW semantics move into NemoClaw, no
authority moves out of MAIW, and deleting this package would leave capability
enforcement, governance and procedure persistence exactly as they are.

Module map:

    sandbox_config.py            deployment facts (mode, runtime kind, endpoints)
    sandbox_policy.py            RuntimeCapabilityPolicy → RenderedSandboxPolicy
    boundary_contracts.py        the two messages that cross, and host-side validation
    sandbox_adapter.py           SandboxedAgentRuntime + provisioners + fail-closed
    manifest.py                  NemoClaw agent manifest rendering
    http_model_gateway_client.py thin HTTP transport client (sandbox → host ModelGateway)

Import boundary: this package imports from ``maiw_agents``; nothing in
``packages/`` imports from here. The dependency points one way so that the
agent package stays sandbox-agnostic.

See ``docs/architecture/NEMOCLAW_OPENSHELL_INTEGRATION.md`` for the ownership
matrix, the threat model, and the current qualification status.
"""

from __future__ import annotations

from .boundary_contracts import (
    GovernanceInbox,
    JsonFileGovernanceInbox,
    SandboxBoundaryViolation,
    SandboxGovernanceInput,
    SandboxRecommendedActionOutput,
    validate_governance_input,
    validate_sandbox_output,
)
from .manifest import (
    MANIFEST_SCHEMA_VERSION,
    STATUS_CONFIGURATION_PENDING,
    STATUS_QUALIFIED,
    render_agent_manifest,
)
from .sandbox_adapter import (
    ContainerSandboxProvisioner,
    OpenShellSandboxProvisioner,
    SandboxAvailability,
    SandboxedAgentRuntime,
    SandboxPolicyApplicationError,
    SandboxProvisioner,
    SandboxUnavailableError,
    UnavailableSandboxProvisioner,
    container_run_args,
)
from .sandbox_config import (
    SandboxConfig,
    SandboxConfigurationError,
    SandboxMode,
    SandboxRuntimeKind,
)
from .sandbox_policy import (
    RenderedSandboxPolicy,
    SandboxNetworkEndpoint,
    SandboxPolicyError,
    render_policy_yaml,
    render_sandbox_policy,
)
from .http_model_gateway_client import (
    MAIWHTTPModelGatewayClient,
    SandboxInferenceError,
)

__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "STATUS_CONFIGURATION_PENDING",
    "STATUS_QUALIFIED",
    "ContainerSandboxProvisioner",
    "GovernanceInbox",
    "JsonFileGovernanceInbox",
    "OpenShellSandboxProvisioner",
    "RenderedSandboxPolicy",
    "SandboxAvailability",
    "SandboxBoundaryViolation",
    "SandboxConfig",
    "SandboxConfigurationError",
    "SandboxGovernanceInput",
    "SandboxMode",
    "SandboxNetworkEndpoint",
    "SandboxPolicyApplicationError",
    "SandboxPolicyError",
    "SandboxProvisioner",
    "SandboxRecommendedActionOutput",
    "SandboxRuntimeKind",
    "SandboxUnavailableError",
    "SandboxedAgentRuntime",
    "UnavailableSandboxProvisioner",
    "container_run_args",
    "render_agent_manifest",
    "render_policy_yaml",
    "render_sandbox_policy",
    "validate_governance_input",
    "validate_sandbox_output",
    # Phase 20C-A: HTTP inference transport
    "MAIWHTTPModelGatewayClient",
    "SandboxInferenceError",
]
