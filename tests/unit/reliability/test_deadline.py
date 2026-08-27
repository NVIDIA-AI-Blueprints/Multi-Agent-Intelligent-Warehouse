# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for RequestDeadline — deterministic, no sleeps.

All time is controlled via FakeClock instances.
"""

import pytest

from maiw_mcp.deadline import RequestDeadline, RequestDeadlineExceeded

# ---------------------------------------------------------------------------
# FakeClock helper
# ---------------------------------------------------------------------------


class FakeClock:
    """Controllable monotonic clock for deterministic tests."""

    def __init__(self, start: float = 0.0) -> None:
        self._t = start

    def __call__(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t += seconds

    def set(self, t: float) -> None:
        self._t = t


# ---------------------------------------------------------------------------
# 14a — Construction: from_timeout
# ---------------------------------------------------------------------------


class TestFromTimeout:
    def test_fresh_deadline_not_expired(self):
        clock = FakeClock(start=100.0)
        dl = RequestDeadline.from_timeout(30.0, clock=clock)
        assert not dl.expired

    def test_started_at_matches_clock_at_creation(self):
        clock = FakeClock(start=500.0)
        dl = RequestDeadline.from_timeout(10.0, clock=clock)
        assert dl.started_at == 500.0

    def test_deadline_at_is_start_plus_budget(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(20.0, clock=clock)
        assert dl.deadline_at == 20.0

    def test_total_budget_seconds(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(45.0, clock=clock)
        assert dl.total_budget_seconds == pytest.approx(45.0)

    def test_zero_timeout_raises(self):
        with pytest.raises(ValueError, match="positive"):
            RequestDeadline.from_timeout(0.0)

    def test_negative_timeout_raises(self):
        with pytest.raises(ValueError, match="positive"):
            RequestDeadline.from_timeout(-1.0)


# ---------------------------------------------------------------------------
# 14b — Elapsed / remaining
# ---------------------------------------------------------------------------


class TestElapsedRemaining:
    def test_elapsed_zero_at_creation(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(30.0, clock=clock)
        assert dl.elapsed_seconds == pytest.approx(0.0)

    def test_elapsed_reflects_clock_advance(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(30.0, clock=clock)
        clock.advance(7.5)
        assert dl.elapsed_seconds == pytest.approx(7.5)

    def test_remaining_equals_budget_at_creation(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(30.0, clock=clock)
        assert dl.remaining_seconds == pytest.approx(30.0)

    def test_remaining_decreases_with_elapsed(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(30.0, clock=clock)
        clock.advance(10.0)
        assert dl.remaining_seconds == pytest.approx(20.0)

    def test_remaining_ms_matches_remaining_seconds(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(30.0, clock=clock)
        clock.advance(5.0)
        assert dl.remaining_ms == pytest.approx(25_000.0)

    def test_remaining_never_negative(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(10.0, clock=clock)
        clock.advance(100.0)
        assert dl.remaining_seconds == pytest.approx(0.0)
        assert dl.remaining_ms == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 14c — Expiry boundary
# ---------------------------------------------------------------------------


class TestExpiryBoundary:
    def test_not_expired_before_deadline(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(10.0, clock=clock)
        clock.advance(9.999)
        assert not dl.expired

    def test_expired_at_exact_deadline(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(10.0, clock=clock)
        clock.advance(10.0)
        assert dl.expired

    def test_expired_past_deadline(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(10.0, clock=clock)
        clock.advance(10.001)
        assert dl.expired

    def test_remaining_zero_when_expired(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(10.0, clock=clock)
        clock.advance(15.0)
        assert dl.remaining_seconds == 0.0

    def test_remaining_ms_zero_when_expired(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(10.0, clock=clock)
        clock.advance(15.0)
        assert dl.remaining_ms == 0.0


# ---------------------------------------------------------------------------
# 14d — effective_timeout child semantics
# ---------------------------------------------------------------------------


class TestEffectiveTimeout:
    def test_child_smaller_than_remaining(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(30.0, clock=clock)
        clock.advance(5.0)  # 25s remaining
        result = dl.effective_timeout(10.0)
        assert result == pytest.approx(10.0)

    def test_child_larger_than_remaining(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(30.0, clock=clock)
        clock.advance(25.0)  # 5s remaining
        result = dl.effective_timeout(10.0)
        assert result == pytest.approx(5.0)

    def test_child_equal_to_remaining(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(30.0, clock=clock)
        clock.advance(20.0)  # 10s remaining
        result = dl.effective_timeout(10.0)
        assert result == pytest.approx(10.0)

    def test_expired_deadline_raises(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(10.0, clock=clock)
        clock.advance(15.0)
        with pytest.raises(RequestDeadlineExceeded) as exc_info:
            dl.effective_timeout(5.0)
        assert exc_info.value.expired_by_ms == pytest.approx(5000.0, abs=1.0)

    def test_zero_local_timeout_raises_value_error(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(30.0, clock=clock)
        with pytest.raises(ValueError, match="positive"):
            dl.effective_timeout(0.0)

    def test_negative_local_timeout_raises_value_error(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(30.0, clock=clock)
        with pytest.raises(ValueError, match="positive"):
            dl.effective_timeout(-1.0)

    def test_child_cannot_extend_parent_deadline(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(5.0, clock=clock)
        clock.advance(2.0)  # 3s remaining
        result = dl.effective_timeout(1000.0)  # huge local timeout
        assert result == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# 14e — Unlimited deadline
# ---------------------------------------------------------------------------


class TestUnlimited:
    def test_unlimited_not_expired(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.unlimited(clock=clock)
        clock.advance(999999.0)
        assert not dl.expired

    def test_unlimited_remaining_is_inf(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.unlimited(clock=clock)
        assert dl.remaining_seconds == float("inf")

    def test_unlimited_remaining_ms_is_inf(self):
        dl = RequestDeadline.unlimited()
        assert dl.remaining_ms == float("inf")

    def test_unlimited_total_budget_is_inf(self):
        dl = RequestDeadline.unlimited()
        assert dl.total_budget_seconds == float("inf")

    def test_unlimited_effective_timeout_returns_local(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.unlimited(clock=clock)
        clock.advance(100.0)
        assert dl.effective_timeout(7.5) == pytest.approx(7.5)

    def test_unlimited_deadline_at_is_none(self):
        dl = RequestDeadline.unlimited()
        assert dl.deadline_at is None


# ---------------------------------------------------------------------------
# 14f — Injected fake clock end-to-end
# ---------------------------------------------------------------------------


class TestFakeClockInjection:
    def test_all_properties_use_injected_clock(self):
        clock = FakeClock(start=1000.0)
        dl = RequestDeadline.from_timeout(60.0, clock=clock)

        assert dl.started_at == 1000.0
        assert dl.deadline_at == 1060.0
        assert dl.elapsed_seconds == pytest.approx(0.0)
        assert dl.remaining_seconds == pytest.approx(60.0)
        assert not dl.expired

        clock.advance(30.0)
        assert dl.elapsed_seconds == pytest.approx(30.0)
        assert dl.remaining_seconds == pytest.approx(30.0)
        assert not dl.expired

        clock.advance(30.0)
        assert dl.elapsed_seconds == pytest.approx(60.0)
        assert dl.remaining_seconds == pytest.approx(0.0)
        assert dl.expired

    def test_two_clocks_are_independent(self):
        c1 = FakeClock(start=0.0)
        c2 = FakeClock(start=0.0)
        dl1 = RequestDeadline.from_timeout(10.0, clock=c1)
        dl2 = RequestDeadline.from_timeout(10.0, clock=c2)

        c1.advance(11.0)
        assert dl1.expired
        assert not dl2.expired

    def test_deadline_is_frozen_immutable(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(10.0, clock=clock)
        with pytest.raises(Exception):
            dl.started_at = 99.0  # type: ignore[misc]

    def test_repr_unlimited(self):
        dl = RequestDeadline.unlimited()
        assert "unlimited" in repr(dl)

    def test_repr_with_budget(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(30.0, clock=clock)
        r = repr(dl)
        assert "30.0s" in r
        assert "expired=False" in r


# ---------------------------------------------------------------------------
# 14g — RequestDeadlineExceeded semantics
# ---------------------------------------------------------------------------


class TestRequestDeadlineExceeded:
    def test_exception_carries_expired_by_ms(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(10.0, clock=clock)
        clock.advance(12.5)  # 2.5s over
        with pytest.raises(RequestDeadlineExceeded) as exc_info:
            dl.effective_timeout(5.0)
        assert exc_info.value.expired_by_ms == pytest.approx(2500.0, abs=1.0)

    def test_exception_message_contains_ms(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(10.0, clock=clock)
        clock.advance(11.0)
        with pytest.raises(RequestDeadlineExceeded, match="1000.0 ms"):
            dl.effective_timeout(5.0)

    def test_exception_is_subclass_of_exception(self):
        exc = RequestDeadlineExceeded(expired_by_ms=100.0)
        assert isinstance(exc, Exception)

    def test_expired_deadline_raises_on_first_effective_timeout_call(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(1.0, clock=clock)
        clock.advance(1.001)
        with pytest.raises(RequestDeadlineExceeded):
            dl.effective_timeout(0.5)
