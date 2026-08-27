# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
StateFreshness — temporal quality annotation for every state component.

Every piece of operational state carries freshness information so that the
DecisionEngine and agents can reason about data age without understanding
backend internals.

Design
------
- ``observed_at``: when the data was read from the source system (UTC).
- ``age_ms``: milliseconds since observed_at, computed at snapshot creation.
  ``None`` means the component was pre-loaded and age is unknown.
- ``stale``: True when age_ms > stale_after_ms.
- ``stale_after_ms``: configurable per-component threshold (default 30 s).

The DecisionEngine blocks write proposals when required state is stale.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

_DEFAULT_STALE_MS = 30_000  # 30 seconds


class StateFreshness(BaseModel):
    """Temporal quality annotation for a single state component."""

    observed_at: datetime = Field(
        description="When this data was read from the source (UTC)"
    )
    age_ms: int | None = Field(
        default=None,
        description="Milliseconds between observed_at and snapshot creation; None if unknown",
    )
    stale: bool = Field(
        default=False,
        description="True when age_ms exceeds stale_after_ms",
    )
    stale_after_ms: int = Field(
        default=_DEFAULT_STALE_MS,
        description="Staleness threshold in milliseconds",
    )

    @classmethod
    def now(cls, *, stale_after_ms: int = _DEFAULT_STALE_MS) -> StateFreshness:
        """Create a freshness record stamped at the current UTC moment."""
        return cls(
            observed_at=datetime.now(timezone.utc),
            age_ms=0,
            stale=False,
            stale_after_ms=stale_after_ms,
        )

    @classmethod
    def from_observed_at(
        cls,
        observed_at: datetime,
        *,
        snapshot_at: datetime | None = None,
        stale_after_ms: int = _DEFAULT_STALE_MS,
    ) -> StateFreshness:
        """
        Compute freshness relative to a snapshot timestamp.

        Parameters
        ----------
        observed_at:
            When the data was originally read.
        snapshot_at:
            When the snapshot is being assembled (defaults to now).
        stale_after_ms:
            Staleness threshold.
        """
        if snapshot_at is None:
            snapshot_at = datetime.now(timezone.utc)

        # Ensure both are tz-aware for comparison
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        if snapshot_at.tzinfo is None:
            snapshot_at = snapshot_at.replace(tzinfo=timezone.utc)

        age_ms = max(0, int((snapshot_at - observed_at).total_seconds() * 1000))
        return cls(
            observed_at=observed_at,
            age_ms=age_ms,
            stale=age_ms > stale_after_ms,
            stale_after_ms=stale_after_ms,
        )
