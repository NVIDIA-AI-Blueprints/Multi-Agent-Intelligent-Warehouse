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

from maiw_mcp.circuit_breaker import CircuitOpen
from maiw_mcp.circuit_registry import DomainCircuitRegistry
from maiw_mcp.deadline import RequestDeadline, RequestDeadlineExceeded
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
        circuit_registry: DomainCircuitRegistry | None = None,
    ) -> None:
        self._registry = registry
        self._telemetry = telemetry or CapabilityTelemetry()
        self._circuit_registry = circuit_registry

    async def invoke(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        trace_id: str | None = None,
        timeout_seconds: float = 30.0,
        deadline: RequestDeadline | None = None,
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
            Client-side read timeout per round trip.  When a *deadline* is
            supplied this becomes the upper bound for the local operation;
            the effective timeout is ``min(timeout_seconds, remaining_budget)``.
        deadline:
            Parent request deadline.  When supplied and already expired,
            raises ``RequestDeadlineExceeded`` before any network call.
            When the remaining budget is smaller than ``timeout_seconds``,
            the tighter value is used.

        Returns
        -------
        dict
            Parsed JSON result from the MCP tool.

        Raises
        ------
        RequestDeadlineExceeded
            Parent request deadline was already exhausted before the call.
        CapabilityNotFound
            No server registered for this capability.
        MCPTimeout
            Server did not respond within the effective timeout (parent budget
            still existed at call time; the child operation simply ran long).
        MCPToolError
            Server returned ``is_error=True`` in the tool result.
        MCPContractError
            Tool result could not be parsed as JSON or was not a dict.
        MCPUnavailable
            Transport-level or protocol-level error.
        """
        # Deadline guard — reject before any network call
        if deadline is not None:
            effective_timeout = deadline.effective_timeout(timeout_seconds)
        else:
            effective_timeout = timeout_seconds

        # Circuit breaker — extract domain from "warehouse.<domain>.<action>"
        parts = capability.split(".")
        domain = parts[1] if len(parts) >= 3 else "unknown"
        breaker = self._circuit_registry.get(domain) if self._circuit_registry else None

        server_url = self._registry.resolve(capability)
        # Telemetry fields must be plain strings — MCPServer instances are not
        # serialisable via dataclasses.asdict() (deepcopy fails on SSL objects).
        server_label = server_url if isinstance(server_url, str) else type(server_url).__name__
        start = time.monotonic()

        async def _do_call() -> dict:
            return await self._call_tool(capability, payload, server_url, effective_timeout)

        try:
            if breaker is not None:
                # CircuitOpen is raised by breaker.call() when circuit is OPEN.
                # All exceptions from _do_call() trip the circuit failure counter —
                # including MCPTimeout and MCPUnavailable (infrastructure failures)
                # as well as MCPToolError (server responded with error). This is an
                # intentional tradeoff: consistent server-side errors also indicate
                # degradation worth tracking.
                result = await breaker.call(_do_call())
            else:
                result = await _do_call()
        except CircuitOpen as exc:
            # Translate to MCPUnavailable so callers see a uniform error type.
            # CircuitOpen is also added to _raise_typed_http → 503 in demo.py.
            raise MCPUnavailable(
                f"Circuit OPEN for MCP domain {domain!r} — "
                f"cooldown {exc.cooldown_remaining_s:.1f}s remaining"
            ) from exc
        except RequestDeadlineExceeded:
            raise  # parent budget exhausted — not MCPTimeout
        except (CapabilityNotFound, MCPToolError, MCPContractError, BackendUnavailable):
            raise
        except MCPUnavailable:
            raise
        except TimeoutError as exc:
            latency_ms = (time.monotonic() - start) * 1000
            self._telemetry.record_failure(
                capability=capability,
                server_url=server_label,
                latency_ms=latency_ms,
                error=exc,
                trace_id=trace_id,
            )
            raise MCPTimeout(
                f"Timeout after {effective_timeout:.1f}s calling {capability!r}"
            ) from exc
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            self._telemetry.record_failure(
                capability=capability,
                server_url=server_label,
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
            server_url=server_label,
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
        # structured_content may be an SDK auto-wrap of a string-returning tool:
        # {"result": "<json string>"}.  In that case parse the inner value.
        sc = result.structured_content
        if sc is not None:
            if isinstance(sc, dict) and list(sc.keys()) == ["result"] and isinstance(sc.get("result"), str):
                try:
                    parsed = json.loads(sc["result"])
                    if isinstance(parsed, dict):
                        return parsed
                except (json.JSONDecodeError, ValueError):
                    pass
            elif isinstance(sc, dict):
                return sc

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
