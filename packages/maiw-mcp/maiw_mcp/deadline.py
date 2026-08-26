# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
RequestDeadline — lightweight monotonic-clock budget for request-scoped timeouts.

Semantics
---------
DEADLINE = parent workflow budget (set once at request ingress; never extended)
TIMEOUT  = local operation ceiling (may be reduced by remaining budget; never
           extended beyond the parent deadline)

A child operation picks:
    effective_timeout = min(local_timeout, deadline.remaining_seconds)

If the deadline has already expired, ``effective_timeout()`` raises
``RequestDeadlineExceeded`` rather than returning a zero or negative value
that downstream libraries (httpx, asyncio.wait_for) interpret inconsistently.

Clock injection
---------------
Pass ``clock`` (a zero-argument callable returning float seconds) to override
the default ``time.monotonic``.  This makes all derived properties deterministic
in tests without sleeping.

    fake = FakeClock(start=0.0)
    dl = RequestDeadline.from_timeout(10.0, clock=fake)
    fake.advance(5.0)
    assert dl.remaining_seconds == 5.0

Usage
-----
    dl = RequestDeadline.from_timeout(30.0)
    timeout = dl.effective_timeout(local_timeout_seconds=5.0)   # → 5.0
    await asyncio.wait_for(coro(), timeout=timeout)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class RequestDeadlineExceeded(Exception):
    """Raised when the parent request deadline has already expired."""

    def __init__(self, expired_by_ms: float) -> None:
        self.expired_by_ms = expired_by_ms
        super().__init__(
            f"Request deadline exceeded by {expired_by_ms:.1f} ms"
        )


# ---------------------------------------------------------------------------
# Core dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RequestDeadline:
    """
    Immutable monotonic-clock budget snapshot.

    Parameters
    ----------
    started_at:
        Monotonic timestamp (seconds) at which the deadline was created.
    deadline_at:
        Monotonic timestamp (seconds) at which the budget expires.
        ``None`` means unlimited — all ``remaining_*`` properties return
        ``float('inf')`` and ``expired`` is always ``False``.
    _clock:
        Zero-argument callable returning monotonic seconds.  Defaults to
        ``time.monotonic``.  Use a ``FakeClock`` in tests.
    """

    started_at: float
    deadline_at: float | None
    _clock: Callable[[], float] = field(
        default=time.monotonic, compare=False, repr=False
    )

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def from_timeout(
        cls,
        seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> "RequestDeadline":
        """Create a deadline that expires *seconds* from now.

        Raises ``ValueError`` for non-positive *seconds*.
        """
        if seconds <= 0:
            raise ValueError(
                f"timeout must be positive, got {seconds!r}"
            )
        now = clock()
        return cls(started_at=now, deadline_at=now + seconds, _clock=clock)

    @classmethod
    def unlimited(
        cls,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> "RequestDeadline":
        """Create a deadline with no expiry (useful for tests and CLI paths)."""
        return cls(started_at=clock(), deadline_at=None, _clock=clock)

    # ------------------------------------------------------------------
    # Derived properties — all computed against live clock
    # ------------------------------------------------------------------

    @property
    def total_budget_seconds(self) -> float:
        """Total budget granted at creation; ``inf`` for unlimited."""
        if self.deadline_at is None:
            return float("inf")
        return self.deadline_at - self.started_at

    @property
    def elapsed_seconds(self) -> float:
        """Seconds elapsed since the deadline was created."""
        return self._clock() - self.started_at

    @property
    def remaining_seconds(self) -> float:
        """Seconds remaining before expiry; ``inf`` for unlimited.

        Returns a non-negative float — callers that need to distinguish
        "just expired" from "deeply expired" should check ``expired`` first.
        """
        if self.deadline_at is None:
            return float("inf")
        return max(0.0, self.deadline_at - self._clock())

    @property
    def remaining_ms(self) -> float:
        """Milliseconds remaining; ``inf`` for unlimited."""
        r = self.remaining_seconds
        return r if r == float("inf") else r * 1000.0

    @property
    def expired(self) -> bool:
        """``True`` if the deadline has passed."""
        if self.deadline_at is None:
            return False
        return self._clock() >= self.deadline_at

    # ------------------------------------------------------------------
    # Helper for child operations
    # ------------------------------------------------------------------

    def effective_timeout(self, local_timeout_seconds: float) -> float:
        """Return the timeout a child operation should use.

        Semantics:
            effective = min(local_timeout_seconds, remaining budget)

        Raises
        ------
        ValueError
            If *local_timeout_seconds* is not positive.
        RequestDeadlineExceeded
            If the parent deadline has already expired.
        """
        if local_timeout_seconds <= 0:
            raise ValueError(
                f"local_timeout_seconds must be positive, got {local_timeout_seconds!r}"
            )
        if self.expired:
            over_ms = (self._clock() - self.deadline_at) * 1000.0  # type: ignore[operator]
            raise RequestDeadlineExceeded(expired_by_ms=over_ms)
        remaining = self.remaining_seconds
        if remaining == float("inf"):
            return local_timeout_seconds
        return min(local_timeout_seconds, remaining)

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        if self.deadline_at is None:
            return "RequestDeadline(unlimited)"
        remaining = self.remaining_seconds
        return (
            f"RequestDeadline("
            f"budget={self.total_budget_seconds:.1f}s, "
            f"remaining={remaining:.3f}s, "
            f"expired={self.expired})"
        )
