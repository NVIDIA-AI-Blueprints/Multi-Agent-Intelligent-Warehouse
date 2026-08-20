# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Common capability contract types.

CapabilityMetadata is attached to every vendor-neutral warehouse capability.
It carries the semantic name, version, and policy annotations used by the
Skill Registry, telemetry, and (future) Decision Engine.

The metadata is NOT used for routing at runtime yet — it is carried by the
capability definition and emitted in telemetry.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CapabilityMetadata(BaseModel):
    """
    Declarative metadata for a warehouse MCP capability.

    Fields
    ------
    name:
        Stable semantic name in ``warehouse.<domain>.<action>`` format.
        This is also the MCP tool name on the server.
    version:
        Integer version — increment on breaking contract changes.
    domain:
        Warehouse domain: ``inventory``, ``wave``, ``labor``, ``equipment``, …
    side_effect:
        ``"read"`` | ``"write"`` | ``"action"``
    risk:
        ``"low"`` | ``"medium"`` | ``"high"``
    idempotent:
        Whether repeated identical calls produce the same result.
    timeout_seconds:
        Suggested client-side timeout.
    required_permission:
        Permission string required to invoke (e.g. ``"inventory:read"``).
        ``None`` means no specific permission check is defined yet.
    description:
        Human-readable description for discovery and documentation.
    """

    name: str = Field(..., pattern=r"^warehouse\.[a-z_]+\.[a-z_]+$")
    version: int = 1
    domain: str
    side_effect: str = "read"
    risk: str = "low"
    idempotent: bool = True
    timeout_seconds: int = 30
    required_permission: str | None = None
    description: str = ""
