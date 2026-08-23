# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Capability Registry — maps semantic capability names to MCP server endpoints.

Agents and skills never know server URLs.  They invoke capabilities by name:

    client.invoke("warehouse.inventory.get", payload)

The registry resolves the URL.

Environment variable convention
--------------------------------
``MAIW_MCP_SERVER_INVENTORY_URL``  →  registers ``warehouse.inventory.*`` capabilities

Future additions follow the same pattern:
    MAIW_MCP_SERVER_WAVE_URL
    MAIW_MCP_SERVER_LABOR_URL
    MAIW_MCP_SERVER_EQUIPMENT_URL
"""

from __future__ import annotations

import logging
import os

from maiw_mcp.errors import CapabilityNotFound

logger = logging.getLogger(__name__)


class CapabilityRegistry:
    """
    Maps semantic warehouse capability names to MCP server endpoints.

    In production, endpoints are Streamable HTTP URLs (strings).
    In demo/test mode, endpoints may be MCPServer instances which the MCP
    client handles via in-memory transport — no extra HTTP servers needed.

    Thread-safe for read after construction (no mutation post-init in production).
    Call ``register()`` only during startup.
    """

    def __init__(self) -> None:
        self._routes: dict[str, object] = {}

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, capability: str, server_url: object) -> None:
        """Register a capability → server URL or MCPServer instance mapping."""
        self._routes[capability] = server_url
        label = server_url if isinstance(server_url, str) else type(server_url).__name__
        logger.info(
            "CapabilityRegistry: %s → %s",
            capability,
            label,
        )

    def register_domain(self, capabilities: list[str], server_url: object) -> None:
        """Register multiple capabilities to the same server."""
        for cap in capabilities:
            self.register(cap, server_url)

    # ── Resolution ────────────────────────────────────────────────────────────

    def resolve(self, capability: str) -> object:
        """
        Return the server URL for a capability.

        Raises
        ------
        CapabilityNotFound
            If no server is registered for the capability.
        """
        url = self._routes.get(capability)
        if url is None:
            registered = sorted(self._routes)
            raise CapabilityNotFound(
                f"No MCP server registered for capability {capability!r}. "
                f"Registered: {registered}"
            )
        return url

    def all_capabilities(self) -> list[str]:
        return sorted(self._routes)

    def is_registered(self, capability: str) -> bool:
        return capability in self._routes

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def from_env(cls) -> "CapabilityRegistry":
        """
        Build a registry from standard MAIW environment variables.

        Reads:
            MAIW_MCP_SERVER_INVENTORY_URL   → warehouse.inventory.* capabilities
        """
        registry = cls()

        inventory_url = os.getenv("MAIW_MCP_SERVER_INVENTORY_URL")
        if inventory_url:
            registry.register_domain(
                ["warehouse.inventory.get", "warehouse.inventory.locate"],
                inventory_url,
            )
        else:
            logger.warning(
                "CapabilityRegistry: MAIW_MCP_SERVER_INVENTORY_URL not set; "
                "warehouse.inventory.* capabilities will raise CapabilityNotFound"
            )

        return registry
