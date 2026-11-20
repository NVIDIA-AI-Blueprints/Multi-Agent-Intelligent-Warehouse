# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Demo-only MCP domain outage: fault F12, "Labor MCP circuit open".

``start_outage`` makes one MCP domain's server unreachable for the API's
``MAIWMCPClient``.  Every ``warehouse.<domain>.*`` capability is routed to
``UnreachableMCPServer``, a client transport whose connect fails, so no
``tools/call`` is ever sent.  The domain's own circuit breaker then trips
through its normal state machine: ``start_outage`` makes ``failure_threshold``
connection attempts, each refused.  From then on:

* writes to that domain are rejected before dispatch (``MCPCircuitOpen``,
  execution outcome FAILED, never UNKNOWN), so nothing is written;
* after the cooldown the breaker lets one probe through, which also fails to
  connect, so the circuit opens again for as long as the outage lasts;
* the other domains keep their own breakers and servers (domain isolation),
  and ``/runtime/status`` reports the domain as ``CIRCUIT OPEN`` and MAIW as
  ``DEGRADED``.

``end_outage`` puts the original routes back and closes the circuit
(``CircuitBreaker.reset``, the operator override).  Starting or resetting a
scenario ends every outage.

Only the demo router calls this, and only while a demo scenario is active.
The capability registry is otherwise written only at startup; this changes
routes from the API's single event loop, between calls.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class UnreachableMCPServer:
    """MCP client transport whose connect is always refused; nothing is sent."""

    def __init__(self, domain: str) -> None:
        self.domain = domain

    async def __aenter__(self) -> Any:
        raise ConnectionRefusedError(
            f"demo outage: the {self.domain} MCP server is unreachable"
        )

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    def __repr__(self) -> str:
        return f"UnreachableMCPServer(domain={self.domain!r})"


class OutageError(ValueError):
    """A demo outage request cannot be applied; carries a code and HTTP status."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _domain_capabilities(runtime: Any, domain: str) -> list[str]:
    prefix = f"warehouse.{domain}."
    return [c for c in runtime.mcp_registry.all_capabilities() if c.startswith(prefix)]


def _require_domain(runtime: Any, domain: Any) -> tuple[Any, list[str]]:
    """Return (breaker, capabilities) for a domain that can have an outage."""
    if runtime.mcp_registry is None or runtime.circuit_registry is None:
        raise OutageError(
            "MCP_LAYER_UNAVAILABLE",
            "The MCP capability registry or circuit breakers are not configured",
            503,
        )
    domains = runtime.circuit_registry.all_domains()
    if not isinstance(domain, str) or domain not in domains:
        raise OutageError(
            "UNKNOWN_MCP_DOMAIN",
            f"payload.domain must be one of {sorted(domains)}; got {domain!r}",
            422,
        )
    capabilities = _domain_capabilities(runtime, domain)
    if not capabilities:
        raise OutageError(
            "MCP_DOMAIN_NOT_CONFIGURED",
            f"No MCP capabilities are registered for the {domain!r} domain",
            409,
        )
    return runtime.circuit_registry.get(domain), capabilities


async def _refused_connection(server: UnreachableMCPServer) -> None:
    from mcp.client import Client

    async with Client(server):
        pass  # pragma: no cover — connect always fails


async def start_outage(runtime: Any, domain: Any) -> dict[str, Any]:
    """Make *domain*'s MCP server unreachable and trip its circuit breaker."""
    from maiw_mcp.circuit_breaker import CircuitOpen

    breaker, capabilities = _require_domain(runtime, domain)
    outages: dict[str, dict[str, object]] = runtime.demo_mcp_outages
    server = UnreachableMCPServer(domain)
    if domain not in outages:
        outages[domain] = {c: runtime.mcp_registry.resolve(c) for c in capabilities}
        for capability in capabilities:
            runtime.mcp_registry.register(capability, server)

    attempts = 0
    for _ in range(breaker.failure_threshold):
        attempt = _refused_connection(server)
        try:
            await breaker.call(attempt)
        except CircuitOpen:
            attempt.close()  # rejected without running: already open
            break
        except ConnectionRefusedError:
            attempts += 1

    stats = breaker.get_stats()
    logger.warning(
        "Demo outage: %s MCP unreachable; circuit %s after %d refused connection(s)",
        domain,
        stats["state"],
        attempts,
    )
    return {
        "domain": domain,
        "circuit_state": stats["state"],
        "refused_connections": attempts,
        "cooldown_seconds": breaker.cooldown_seconds,
        "capabilities": capabilities,
    }


def end_outage(runtime: Any, domain: Any) -> dict[str, Any]:
    """Restore *domain*'s MCP routes and close its circuit."""
    breaker, _ = _require_domain(runtime, domain)
    routes = runtime.demo_mcp_outages.pop(domain, None)
    for capability, original in (routes or {}).items():
        runtime.mcp_registry.register(capability, original)
    breaker.reset()
    logger.info("Demo outage ended: %s MCP routes restored, circuit closed", domain)
    return {
        "domain": domain,
        "circuit_state": breaker.get_stats()["state"],
        "was_out": routes is not None,
    }


def end_all_outages(runtime: Any) -> list[str]:
    """End every demo outage (scenario start/reset). Returns the domains restored."""
    domains = list(getattr(runtime, "demo_mcp_outages", None) or {})
    for domain in domains:
        end_outage(runtime, domain)
    return domains
