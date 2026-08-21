# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
InventoryLookupSkill — the operational bridge between agents and MCP v2.

A skill represents one warehouse operational behavior (inventory lookup).
MCP represents the execution capability (warehouse.inventory.get tool).
These are deliberately separate concepts:

    - The skill knows WHAT to do (look up inventory for a SKU).
    - MCP knows HOW to execute it (which server, which transport).

Agents call the skill.  The skill calls the capability client.
The agent never knows about MCP servers, URLs, or transport.

Usage in agents
---------------
    from src.api.skills.inventory import InventoryLookupSkill, get_inventory_skill
    from maiw_mcp.contracts.inventory import InventoryLookupRequest

    skill = await get_inventory_skill()
    result = await skill.execute(InventoryLookupRequest(sku="SKU-001"))

    # Agent sees only warehouse semantics:
    print(result.total_available)
    print(result.is_low_stock)
    print(result.source)  # "maiw-backend" — agent does NOT act on this

Architecture
------------
    OperationsCoordinationAgent._lookup_inventory_sku("SKU-001")
        ↓
    InventoryLookupSkill.execute(InventoryLookupRequest(sku="SKU-001"))
        ↓
    MAIWMCPClient.invoke("warehouse.inventory.get", payload)
        ↓
    [MCP v2 protocol: Streamable HTTP or in-memory]
        ↓
    InventoryMCPServer → MAIWInventoryAdapter → InventoryQueries → PostgreSQL

    The agent at the top does not know the backend at the bottom.
"""

from __future__ import annotations

import logging
import os

from maiw_mcp.client.client import MAIWMCPClient
from maiw_mcp.contracts.inventory import (
    InventoryLookupRequest,
    InventoryLookupResult,
    INVENTORY_GET_METADATA,
)
from maiw_mcp.errors import MCPContractError, MAIWMCPError
from maiw_mcp.registry.registry import CapabilityRegistry
from maiw_mcp.telemetry.telemetry import CapabilityTelemetry

logger = logging.getLogger(__name__)


class InventoryLookupSkill:
    """
    Warehouse inventory lookup via MCP v2.

    This is the first official MAIW skill: it maps the agent's semantic need
    ("I need to know the stock level for SKU X") to the MCP capability
    ``warehouse.inventory.get``.

    Parameters
    ----------
    client:
        A configured ``MAIWMCPClient`` instance.  Injected so it can be
        replaced with a mock in tests.
    """

    def __init__(self, client: MAIWMCPClient) -> None:
        self._client = client

    async def execute(
        self,
        request: InventoryLookupRequest,
        *,
        trace_id: str | None = None,
    ) -> InventoryLookupResult:
        """
        Look up inventory for a SKU via the MCP v2 inventory server.

        Parameters
        ----------
        request:
            Validated lookup request.  Only ``sku`` is required.
        trace_id:
            Correlation ID propagated from the calling agent span.

        Returns
        -------
        InventoryLookupResult
            Validated, typed result.  Source field identifies the backend.

        Raises
        ------
        MAIWMCPError
            Any transport, protocol, or contract error is surfaced as a
            typed subclass of MAIWMCPError.
        """
        payload = request.model_dump(exclude_none=True)
        raw = await self._client.invoke(
            INVENTORY_GET_METADATA.name,
            payload,
            trace_id=trace_id,
        )

        try:
            return InventoryLookupResult.model_validate(raw)
        except Exception as exc:
            raise MCPContractError(
                f"warehouse.inventory.get result failed contract validation: {exc}"
            ) from exc


# ── Singleton factory ──────────────────────────────────────────────────────────

_inventory_skill: InventoryLookupSkill | None = None


async def get_inventory_skill() -> InventoryLookupSkill:
    """
    Return the process-level InventoryLookupSkill singleton.

    Reads ``MAIW_MCP_SERVER_INVENTORY_URL`` from the environment to configure
    the capability registry.

    Raises
    ------
    RuntimeError
        If ``MAIW_MCP_SERVER_INVENTORY_URL`` is not set (production guard).
    """
    global _inventory_skill
    if _inventory_skill is None:
        registry = CapabilityRegistry.from_env()
        telemetry = CapabilityTelemetry()
        client = MAIWMCPClient(registry, telemetry=telemetry)
        _inventory_skill = InventoryLookupSkill(client)
        logger.info(
            "InventoryLookupSkill initialised. Capabilities: %s",
            registry.all_capabilities(),
        )
    return _inventory_skill


def reset_inventory_skill() -> None:
    """Reset the singleton — for testing only."""
    global _inventory_skill
    _inventory_skill = None
