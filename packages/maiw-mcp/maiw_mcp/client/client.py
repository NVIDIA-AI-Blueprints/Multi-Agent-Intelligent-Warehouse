# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Official MCP v2 capability client (mcp 2.0.0, protocol 2026-07-28).

Wraps ``mcp.client.Client`` — the high-level MCP v2 client.
Skills and agents call ``MAIWMCPClient.invoke()`` with a semantic capability
name and a payload dict.  Transport details and server URLs are fully hidden.

Production transport: Streamable HTTP (stateless — no session affinity needed)
Test transport: In-memory (pass MCPServer instance via CapabilityRegistry)

Architecture
------------
    Skill
      ↓
    MAIWMCPClient.invoke("warehouse.inventory.get", payload)
      ↓
    CapabilityRegistry.resolve()  →  server URL
      ↓
    mcp.client.Client(server_url)     ← official MCP v2 Client
      ↓
    client.call_tool("warehouse.inventory.get", payload)
      ↓
    [MCP 2026-07-28 over Streamable HTTP]
      ↓
    MCPServer (mcp_servers/inventory/server.py)

MCP v1 → v2 migration notes
----------------------------
Removed:
    - streamablehttp_client (renamed + superseded by Client)
    - ClientSession (superseded by Client)
    - session.initialize() handshake (handled internally by Client)
    - create_connected_server_and_client_session (use Client(server) instead)

Renamed:
    - result.isError  →  result.is_error
    - tool.inputSchema  →  tool.input_schema
"""

from __future__ import annotations

import json
import logging
import time
from importlib.metadata import version as pkg_version
from typing import Any

from mcp import types
from mcp.client import Client

from maiw_mcp.errors import (
    BackendUnavailable,
    CapabilityNotFound,
    MCPContractError,
    MCPTimeout,
    MCPToolError,
    MCPUnavailable,
)
from maiw_mcp.registry.registry import CapabilityRegistry
from maiw_mcp.telemetry.telemetry import CapabilityTelemetry

logger = logging.getLogger(__name__)

_MCP_SDK_VERSION = pkg_version("mcp")


class MAIWMCPClient:
    """
    Capability client using the official MCP v2 Python SDK.

    One ``invoke()`` call opens a connection via ``mcp.client.Client``,
    calls the tool, then closes the connection.  The ``Client`` handles
    the full MCP 2026-07-28 lifecycle internally — no manual initialize
    handshake, no persistent session management required.

    Production connections are stateless: ``Client(url)`` works behind
    any load balancer or Kubernetes service without session affinity.

    Parameters
    ----------
    registry:
        Maps capability names to server URLs.
    telemetry:
        Emits structured JSON log per call.  Defaults to a no-op instance.
    """

    def __init__(
        self,
        registry: CapabilityRegistry,
        *,
        telemetry: CapabilityTelemetry | None = None,
    ) -> None:
        self._registry = registry
        self._telemetry = telemetry or CapabilityTelemetry()

    async def invoke(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        trace_id: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> dict[str, Any]:
        """
        Invoke a warehouse capability via the MCP 2026-07-28 protocol.

        Parameters
        ----------
        capability:
            Semantic name, e.g. ``"warehouse.inventory.get"``.
        payload:
            Validated request dict (use ``request.model_dump(exclude_none=True)``).
        trace_id:
            Correlation ID propagated from ModelGateway / agent span.
        timeout_seconds:
            Client-side read timeout per round trip.

        Returns
        -------
        dict
            Parsed JSON result from the MCP tool.

        Raises
        ------
        CapabilityNotFound
            No server registered for this capability.
        MCPTimeout
            Server did not respond within ``timeout_seconds``.
        MCPToolError
            Server returned ``is_error=True`` in the tool result.
        MCPContractError
            Tool result could not be parsed as JSON or was not a dict.
        MCPUnavailable
            Transport-level or protocol-level error.
        """
        server_url = self._registry.resolve(capability)
        start = time.monotonic()

        try:
            result = await self._call_tool(capability, payload, server_url, timeout_seconds)
        except (CapabilityNotFound, MCPToolError, MCPContractError, BackendUnavailable):
            raise
        except TimeoutError as exc:
            latency_ms = (time.monotonic() - start) * 1000
            self._telemetry.record_failure(
                capability=capability,
                server_url=server_url,
                latency_ms=latency_ms,
                error=exc,
                trace_id=trace_id,
            )
            raise MCPTimeout(f"Timeout after {timeout_seconds}s calling {capability!r}") from exc
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            self._telemetry.record_failure(
                capability=capability,
                server_url=server_url,
                latency_ms=latency_ms,
                error=exc,
                trace_id=trace_id,
            )
            raise MCPUnavailable(
                f"MCP invocation failed for {capability!r}: {type(exc).__name__}: {exc}"
            ) from exc

        latency_ms = (time.monotonic() - start) * 1000
        self._telemetry.record_success(
            capability=capability,
            server_url=server_url,
            latency_ms=latency_ms,
            trace_id=trace_id,
        )
        return result

    async def _call_tool(
        self,
        capability: str,
        payload: dict[str, Any],
        server_url: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        # mcp.client.Client handles the full MCP lifecycle:
        # - connection (Streamable HTTP for string URLs, in-memory for MCPServer instances)
        # - initialize handshake
        # - tools/call request
        # - session teardown
        async with Client(server_url, read_timeout_seconds=timeout_seconds) as client:
            call_result: types.CallToolResult = await client.call_tool(capability, payload)

        if call_result.is_error:
            error_text = self._extract_text(call_result)
            raise MCPToolError(f"{capability!r} returned error: {error_text}")

        return self._parse_result(call_result)

    def _extract_text(self, result: types.CallToolResult) -> str:
        for block in result.content:
            if isinstance(block, types.TextContent):
                return block.text
        return str(result.content)

    def _parse_result(self, result: types.CallToolResult) -> dict[str, Any]:
        # Prefer structuredContent if available
        if result.structured_content is not None:
            return result.structured_content

        # Fall back to parsing JSON from TextContent
        text = self._extract_text(result)
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, ValueError) as exc:
            raise MCPContractError(
                f"MCP tool result is not valid JSON: {text[:200]!r}"
            ) from exc

        if not isinstance(parsed, dict):
            raise MCPContractError(
                f"MCP tool result is not a JSON object; got {type(parsed).__name__}"
            )
        return parsed
