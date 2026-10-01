# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
NemoClaw agent manifest rendering.

A manifest is what NemoClaw is handed to operate a MAIW agent: the image, the
policy, the inference route, the mounts. It is *derived* from a
``RenderedSandboxPolicy`` rather than written alongside one, because a manifest
written by hand is a second statement of the boundary that can disagree with the
first.

Status on a host without NemoClaw installed: the manifest renders, and its
``status`` field says ``CONFIGURATION_PENDING``. The schema below is MAIW's
statement of what it needs a sandbox operator to guarantee; it is not a
transcription of a NemoClaw schema, because no installed NemoClaw was available
to transcribe. The field names will need reconciling against the real schema at
qualification time, and ``nemoclaw_version`` is the field that records when
that happened.
"""

from __future__ import annotations

from typing import Any

from .sandbox_config import SandboxConfig
from .sandbox_policy import RenderedSandboxPolicy

MANIFEST_SCHEMA_VERSION = "maiw.nemoclaw/v1alpha1"
"""
MAIW's own manifest schema version.

``v1alpha1`` is not modesty — it signals that this schema has never been
validated against an installed NemoClaw. It becomes ``v1`` when a qualification
run pins a NemoClaw version.
"""

STATUS_CONFIGURATION_PENDING = "CONFIGURATION_PENDING"
STATUS_QUALIFIED = "QUALIFIED"


def render_agent_manifest(
    rendered: RenderedSandboxPolicy,
    *,
    config: SandboxConfig,
) -> dict[str, Any]:
    """
    Build the manifest dict for one sandboxed procedure execution.

    Deterministic: every collection is sorted and no timestamp is emitted, so
    two renders of the same policy produce equal dicts and a manifest diff
    always means something.

    The ``mcp`` block is the part worth reading twice. It declares read servers
    and then states, as data rather than as a comment, that no write server is
    exposed. A sandbox operator reading only this manifest should be unable to
    conclude that a write endpoint was merely forgotten.
    """
    qualified = config.is_qualified and config.nemoclaw_version is not None

    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "status": STATUS_QUALIFIED if qualified else STATUS_CONFIGURATION_PENDING,
        "kind": "MAIWSandboxedAgent",
        "metadata": {
            "policy_id": rendered.source_policy_id,
            "policy_revision": rendered.source_policy_revision,
            "policy_profile": rendered.policy_profile,
            "agent_task_id": rendered.agent_task_id,
            "sop_id": rendered.sop_id,
            "sop_version": rendered.sop_version,
            "maiw_runtime": rendered.runtime,
        },
        "platform": {
            "nemoclaw_version": config.nemoclaw_version,
            "openshell_version": config.openshell_version,
            "runtime_kind": config.runtime_kind.value,
        },
        "agent": {
            "image": config.image_reference,
            "entrypoint": "maiw_agents.runtime",
            "sandbox_mode": config.mode.value,
        },
        "capabilities": {
            "allowed_classes": sorted(rendered.allowed_capability_classes),
            "denied_classes": sorted(rendered.denied_capability_classes),
            "allowed_ids": sorted(rendered.allowed_capability_ids),
            "allowed_subagents": sorted(rendered.allowed_subagents),
        },
        "network": {
            "default": rendered.network_default,
            "allowed": [
                {"endpoint": ep.endpoint, "purpose": ep.purpose}
                for ep in rendered.allowed_network_endpoints
            ],
        },
        "filesystem": {
            "writable": sorted(rendered.writable_paths),
            "readable": sorted(rendered.readable_paths),
        },
        "inference": {
            # MAIW selects the model; the sandbox transports the request.
            "route": "maiw_model_gateway",
            "endpoint": config.model_gateway_endpoint,
            "model_selection_authority": "maiw.ModelGateway",
            "use_platform_model_router": False,
        },
        "mcp": {
            "read_servers_via": config.read_capability_endpoint,
            "write_servers": [],
            "write_servers_exposed": False,
        },
        "credentials": {
            "custody": rendered.credential_custody,
            "managed": sorted(rendered.managed_credentials),
            "injected": [],
        },
        "governance": {
            # Stated in the manifest so an operator cannot configure otherwise.
            "authority": "maiw_host",
            "action_executor_in_sandbox": False,
            "decision_engine_in_sandbox": False,
            "recommended_action_egress": "SandboxRecommendedActionOutput",
            "governance_ingress": "SandboxGovernanceInput",
        },
    }


__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "STATUS_CONFIGURATION_PENDING",
    "STATUS_QUALIFIED",
    "render_agent_manifest",
]
