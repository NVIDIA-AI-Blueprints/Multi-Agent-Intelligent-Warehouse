# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
CircuitBreaker — generic async circuit breaker for MAIW external dependency calls.

Boundaries
----------
Only wrap external dependencies: NIM/ModelGateway, MCP domain servers.
Never wrap deterministic in-process components: DecisionEngine, WarehouseStateProvider,
BaseActionExecutor, ReconciliationService.

State machine
-------------
    CLOSED  ──(consecutive_failures >= threshold)──►  OPEN
       ▲                                                  │
       │                                              cooldown
       │                                                  │
       └──(probe succeeds)──  HALF_OPEN  ◄────────────────┘
                                  │
                     (probe fails)│
                                  ▼
                                OPEN  (cooldown resets)

HALF_OPEN allows exactly one probe call. While probing, additional callers
receive CircuitOpen immediately — they do not queue behind the probe.

Parameters
----------
failure_threshold : int
    Consecutive failures in CLOSED state before tripping to OPEN (default 5).
cooldown_seconds : float
    Minimum seconds to stay OPEN before allowing a HALF_OPEN probe (default 30).
success_threshold : int
    Consecutive successes in HALF_OPEN needed to close the circuit (default 1).

Usage
-----
    breaker = CircuitBreaker(failure_threshold=5, cooldown_seconds=30.0)

    try:
        result = await breaker.call(some_async_coroutine())
    except CircuitOpen as exc:
        # fast-fail — dependency is known broken
        ...
    except SomeServiceError:
        # breaker counted this failure
        ...

Clock injection (for tests)
------------------------------
    fake = FakeClock(); breaker = CircuitBreaker(..., clock=fake)
    fake.advance(35.0)   # jump past cooldown
"""

from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enumerations and exceptions
# ---------------------------------------------------------------------------


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpen(Exception):
    """
    Raised when a call is rejected because the circuit is OPEN.

    This is distinct from MCPUnavailable / ModelUnavailable (which indicate
    the service is currently unreachable) — CircuitOpen means the breaker has
    decided not to attempt the call at all.
    """

    def __init__(self, domain: str, cooldown_remaining_s: float) -> None:
        self.domain = domain
        self.cooldown_remaining_s = cooldown_remaining_s
        super().__init__(
            f"Circuit OPEN for {domain!r} — "
            f"cooldown {cooldown_remaining_s:.1f}s remaining"
        )


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------


class CircuitBreaker:
    """
    Async circuit breaker for a single external dependency.

    Thread-safe via asyncio.Lock — one state transition at a time.
    """

    def __init__(
        self,
        *,
        domain: str = "unknown",
        failure_threshold: int = 5,
        cooldown_seconds: float = 30.0,
        success_threshold: int = 1,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.domain = domain
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.success_threshold = success_threshold
        self._clock = clock

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._success_count: int = 0
        self._opened_at: float | None = None
        self._probing: bool = False  # True while HALF_OPEN probe is in flight

        self._lock = asyncio.Lock()

        # Counters for observability
        self._total_calls: int = 0
        self._total_rejected: int = 0
        self._total_failures: int = 0
        self._total_successes: int = 0
        self._trip_count: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def call(self, coro: Awaitable[Any]) -> Any:
        """
        Execute *coro* under circuit protection.

        Raises
        ------
        CircuitOpen
            The circuit is OPEN and the call is rejected fast.
        Exception
            Whatever the wrapped coroutine raises — the breaker counts it
            as a failure and re-raises transparently.
        """
        async with self._lock:
            state = self._resolve_state()
            if state == CircuitState.OPEN:
                remaining = self._cooldown_remaining()
                self._total_rejected += 1
                raise CircuitOpen(domain=self.domain, cooldown_remaining_s=remaining)
            if state == CircuitState.HALF_OPEN and self._probing:
                # A probe is already in flight; reject additional callers.
                self._total_rejected += 1
                raise CircuitOpen(domain=self.domain, cooldown_remaining_s=0.0)
            if state == CircuitState.HALF_OPEN:
                self._probing = True
            self._total_calls += 1

        try:
            result = await coro
        except Exception as exc:
            async with self._lock:
                self._on_failure(exc)
            raise
        else:
            async with self._lock:
                self._on_success()
            return result
        finally:
            async with self._lock:
                self._probing = False

    @property
    def state(self) -> CircuitState:
        """Current circuit state (resolved from time-based transitions)."""
        return self._resolve_state()

    def reset(self) -> None:
        """Force circuit to CLOSED — for testing and operator override."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._opened_at = None
        self._probing = False
        logger.info("circuit_breaker.reset: domain=%s", self.domain)

    def get_stats(self) -> dict:
        state = self._resolve_state()
        cooldown_remaining = (
            self._cooldown_remaining() if state == CircuitState.OPEN else 0.0
        )
        return {
            "domain": self.domain,
            "state": state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "total_calls": self._total_calls,
            "total_rejected": self._total_rejected,
            "total_failures": self._total_failures,
            "total_successes": self._total_successes,
            "trip_count": self._trip_count,
            "cooldown_remaining_s": round(cooldown_remaining, 2),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_state(self) -> CircuitState:
        """Compute the effective state — transitions OPEN→HALF_OPEN by time."""
        if self._state == CircuitState.OPEN:
            if self._opened_at is not None and self._cooldown_remaining() <= 0:
                self._state = CircuitState.HALF_OPEN
                self._probing = False
                logger.info(
                    "circuit_breaker.half_open: domain=%s cooldown_elapsed",
                    self.domain,
                )
        return self._state

    def _cooldown_remaining(self) -> float:
        if self._opened_at is None:
            return 0.0
        elapsed = self._clock() - self._opened_at
        return max(0.0, self.cooldown_seconds - elapsed)

    def _on_failure(self, exc: Exception) -> None:
        self._total_failures += 1
        if self._state == CircuitState.HALF_OPEN:
            # Probe failed — trip back to OPEN
            self._state = CircuitState.OPEN
            self._opened_at = self._clock()
            self._failure_count = 1
            self._success_count = 0
            self._trip_count += 1
            logger.warning(
                "circuit_breaker.open (probe_failed): domain=%s error=%s",
                self.domain,
                type(exc).__name__,
            )
        elif self._state == CircuitState.CLOSED:
            self._failure_count += 1
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = self._clock()
                self._success_count = 0
                self._trip_count += 1
                logger.warning(
                    "circuit_breaker.open: domain=%s failures=%d threshold=%d",
                    self.domain,
                    self._failure_count,
                    self.failure_threshold,
                )

    def _on_success(self) -> None:
        self._total_successes += 1
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._success_count = 0
                self._opened_at = None
                logger.info(
                    "circuit_breaker.closed (probe_succeeded): domain=%s",
                    self.domain,
                )
        elif self._state == CircuitState.CLOSED:
            # Reset consecutive failure counter on success
            self._failure_count = 0

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(domain={self.domain!r}, "
            f"state={self.state.value}, "
            f"failures={self._failure_count}/{self.failure_threshold})"
        )
