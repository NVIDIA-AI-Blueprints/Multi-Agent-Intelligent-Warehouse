# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Deployment profiles (v2.0.1 round 2, audit NEW-P1-03).

Readiness must reflect what the *selected profile* claims the deployment can
do.  Before round 2 it reported unconfigured MCP domains as HEALTHY and stayed
READY with every configured MCP domain circuit-open, so a deployment whose
governed write path could not work still said "ready".

Profiles (``MAIW_DEPLOYMENT_PROFILE``):

``demo``
    SimulationProviders behind in-memory MCP servers (``MAIW_DEMO_MODE=true``).
    Governed writes run against the simulation.  All four MCP domains are
    required (they are in-process, so they are always configured when demo
    wiring succeeded).  No database required.

``reference`` (default when not in demo mode)
    Durable persistence + ModelGateway + sandbox inference boundary + the
    database-backed read routes.  This profile does NOT offer governed
    operational writes: MCP write domains are optional and the governed write
    path is reported ``not_offered`` (never "ready").

``reference_governed``
    ``reference`` plus governed operational writes.  Every required MCP write
    domain (default ``equipment,labor,wave``; override with
    ``MAIW_REQUIRED_MCP_DOMAINS``) must be configured, reachable and not
    circuit-open, otherwise ``/api/v1/ready`` is 503.

Sandbox: when ``MAIW_SANDBOX_MODE=required`` the sandbox named by
``MAIW_SANDBOX_NAME`` must be ``Ready`` for the API to be ready; otherwise the
sandbox is reported (``not_configured`` / ``degraded``) but not critical.

Everything here is read from the environment at call time — no import-time
state.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

PROFILE_ENV = "MAIW_DEPLOYMENT_PROFILE"
REQUIRED_MCP_DOMAINS_ENV = "MAIW_REQUIRED_MCP_DOMAINS"

DEMO = "demo"
REFERENCE = "reference"
REFERENCE_GOVERNED = "reference_governed"
PROFILES = (DEMO, REFERENCE, REFERENCE_GOVERNED)

MCP_DOMAINS: tuple[str, ...] = ("equipment", "labor", "wave", "inventory")
# Domains that carry governed write capabilities (assign/release/maintenance,
# allocate, reprioritize).  Inventory is read-only.
MCP_WRITE_DOMAINS: tuple[str, ...] = ("equipment", "labor", "wave")


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class DeploymentProfile:
    name: str
    valid: bool
    governed_writes: bool
    required_mcp_domains: frozenset[str]
    database_required: bool
    sandbox_required: bool
    sandbox_mode: str
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "valid": self.valid,
            "governed_writes": self.governed_writes,
            "required_mcp_domains": sorted(self.required_mcp_domains),
            "database_required": self.database_required,
            "sandbox_required": self.sandbox_required,
            "sandbox_mode": self.sandbox_mode,
            **({"error": self.error} if self.error else {}),
        }


def resolve_profile(env: Mapping[str, str] | None = None) -> DeploymentProfile:
    """Resolve the active deployment profile from the environment."""
    env = os.environ if env is None else env
    demo_mode = _truthy(env.get("MAIW_DEMO_MODE"))
    raw = (env.get(PROFILE_ENV) or "").strip().lower()
    name = raw or (DEMO if demo_mode else REFERENCE)
    sandbox_mode = (env.get("MAIW_SANDBOX_MODE") or "disabled").strip().lower()
    sandbox_required = sandbox_mode == "required"

    error = None
    valid = name in PROFILES
    if not valid:
        error = f"unknown {PROFILE_ENV}={raw!r}; expected one of {list(PROFILES)}"

    if name == DEMO:
        governed = True
        required = frozenset(MCP_DOMAINS)
        db_required = False
    elif name == REFERENCE_GOVERNED:
        governed = True
        listed = env.get(REQUIRED_MCP_DOMAINS_ENV)
        if listed is not None and listed.strip():
            required = frozenset(
                d.strip().lower() for d in listed.split(",") if d.strip()
            )
            unknown = sorted(required - set(MCP_DOMAINS))
            if unknown:
                valid = False
                error = f"{REQUIRED_MCP_DOMAINS_ENV} names unknown domain(s) {unknown}"
        else:
            required = frozenset(MCP_WRITE_DOMAINS)
        db_required = True
    else:  # reference (and the invalid case, which fails readiness anyway)
        governed = False
        required = frozenset()
        db_required = True

    explicit_db = env.get("MAIW_READINESS_REQUIRE_DATABASE")
    if explicit_db is not None and explicit_db.strip():
        db_required = _truthy(explicit_db)

    return DeploymentProfile(
        name=name,
        valid=valid,
        governed_writes=governed,
        required_mcp_domains=required,
        database_required=db_required,
        sandbox_required=sandbox_required,
        sandbox_mode=sandbox_mode,
        error=error,
    )


__all__ = [
    "DEMO",
    "REFERENCE",
    "REFERENCE_GOVERNED",
    "PROFILES",
    "PROFILE_ENV",
    "REQUIRED_MCP_DOMAINS_ENV",
    "MCP_DOMAINS",
    "MCP_WRITE_DOMAINS",
    "DeploymentProfile",
    "resolve_profile",
]
