# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
DomainCircuitRegistry — one CircuitBreaker per MCP domain.

Domain isolation is the critical invariant:
    A Labor MCP outage must NOT affect Equipment or Inventory workflows.

Each warehouse MCP domain (equipment, labor, wave, inventory) has its own
independent circuit breaker.  A circuit tripping in one domain has zero
effect on calls routed to other domains.

Usage
-----
    from maiw_mcp.circuit_registry import DomainCircuitRegistry

    registry = DomainCircuitRegistry.for_domains(
        domains=["equipment", "labor", "wave", "inventory"],
        failure_threshold=5,
        cooldown_seconds=30.0,
        success_threshold=1,
    )

    # In MAIWMCPClient.invoke(), extract domain from capability name:
    #   "warehouse.equipment.assign" → "equipment"
    breaker = registry.get("equipment")
    if breaker:
        result = await breaker.call(some_mcp_coro())
"""

from __future__ import annotations

import time
from typing import Callable

from .circuit_breaker import CircuitBreaker, CircuitState

_MCP_DOMAINS = ("equipment", "labor", "wave", "inventory")


class DomainCircuitRegistry:
    """
    Registry of per-domain circuit breakers for MCP calls.

    Domain isolation guarantee: each domain has an independent CircuitBreaker.
    A CIRCUIT OPEN in one domain never rejects calls for another domain.
    """

    def __init__(self, breakers: dict[str, CircuitBreaker]) -> None:
        self._breakers = breakers

    @classmethod
    def for_domains(
        cls,
        domains: list[str] | tuple[str, ...] = _MCP_DOMAINS,
        *,
        failure_threshold: int = 5,
        cooldown_seconds: float = 30.0,
        success_threshold: int = 1,
        clock: Callable[[], float] = time.monotonic,
    ) -> "DomainCircuitRegistry":
        breakers = {
            domain: CircuitBreaker(
                domain=domain,
                failure_threshold=failure_threshold,
                cooldown_seconds=cooldown_seconds,
                success_threshold=success_threshold,
                clock=clock,
            )
            for domain in domains
        }
        return cls(breakers)

    def get(self, domain: str) -> CircuitBreaker | None:
        """Return the circuit breaker for *domain*, or None if unregistered."""
        return self._breakers.get(domain)

    def all_domains(self) -> list[str]:
        return list(self._breakers.keys())

    def all_stats(self) -> list[dict]:
        """Return stats for all domain circuit breakers — for /runtime/status."""
        return [breaker.get_stats() for breaker in self._breakers.values()]

    def operational_status(self) -> dict[str, str]:
        """
        Return per-domain operational label.

        Labels:
            HEALTHY     — circuit CLOSED, no recent failures
            DEGRADED    — circuit CLOSED but failure_count > 0 (approaching threshold)
            CIRCUIT OPEN — circuit OPEN or HALF_OPEN
        """
        result = {}
        for domain, breaker in self._breakers.items():
            state = breaker.state
            if state == CircuitState.CLOSED:
                if breaker._failure_count > 0:
                    label = "DEGRADED"
                else:
                    label = "HEALTHY"
            else:
                label = "CIRCUIT OPEN"
            result[domain] = label
        return result

    def reset_all(self) -> None:
        """Force all circuits to CLOSED — for testing and operator override."""
        for breaker in self._breakers.values():
            breaker.reset()
