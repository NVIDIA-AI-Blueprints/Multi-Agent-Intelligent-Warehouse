# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 10E Batch 5 — Circuit Breaker state machine tests.

Covers:
    CB1  Starts in CLOSED state
    CB2  Accumulates failures and trips to OPEN at threshold
    CB3  Rejects calls immediately when OPEN (CircuitOpen raised)
    CB4  Transitions to HALF_OPEN after cooldown
    CB5  Closes on successful probe from HALF_OPEN
    CB6  Re-trips to OPEN on failed probe from HALF_OPEN (cooldown resets)
    CB7  Success in CLOSED resets failure counter
    CB8  Partial failures below threshold do not trip circuit
    CB9  get_stats returns correct fields
    CB10 reset() forces circuit to CLOSED
    CB11 CircuitOpen carries domain and cooldown_remaining_s
    CB12 Circuit is closed = failure_count resets on success
    CB13 DomainCircuitRegistry.for_domains creates independent per-domain breakers
    CB14 Domain isolation: tripping one domain does NOT affect others
    CB15 DomainCircuitRegistry.operational_status returns correct labels
    CB16 Config properties exist and have defaults
    CB17 MAIWMCPClient accepts circuit_registry kwarg
    CB18 ModelGateway accepts nim_circuit kwarg
"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeClock:
    def __init__(self, t: float = 0.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


async def _ok():
    return "ok"


async def _fail():
    raise RuntimeError("simulated failure")


# ---------------------------------------------------------------------------
# CB1 — Starts CLOSED
# ---------------------------------------------------------------------------


def test_starts_closed():
    from maiw_mcp.circuit_breaker import CircuitBreaker, CircuitState

    b = CircuitBreaker(domain="test")
    assert b.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# CB2 — Trips to OPEN at failure threshold
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trips_to_open_at_threshold():
    from maiw_mcp.circuit_breaker import CircuitBreaker, CircuitState

    clock = FakeClock()
    b = CircuitBreaker(
        domain="test", failure_threshold=3, cooldown_seconds=30.0, clock=clock
    )

    for _ in range(3):
        with pytest.raises(RuntimeError):
            await b.call(_fail())

    assert b.state == CircuitState.OPEN


# ---------------------------------------------------------------------------
# CB3 — Rejects calls when OPEN
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rejects_when_open():
    from maiw_mcp.circuit_breaker import CircuitBreaker, CircuitOpen, CircuitState

    clock = FakeClock()
    b = CircuitBreaker(
        domain="test", failure_threshold=1, cooldown_seconds=30.0, clock=clock
    )

    with pytest.raises(RuntimeError):
        await b.call(_fail())

    assert b.state == CircuitState.OPEN

    with pytest.raises(CircuitOpen) as exc_info:
        await b.call(_ok())

    assert exc_info.value.domain == "test"
    assert exc_info.value.cooldown_remaining_s > 0


# ---------------------------------------------------------------------------
# CB4 — Transitions to HALF_OPEN after cooldown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transitions_to_half_open_after_cooldown():
    from maiw_mcp.circuit_breaker import CircuitBreaker, CircuitState

    clock = FakeClock()
    b = CircuitBreaker(
        domain="test", failure_threshold=1, cooldown_seconds=30.0, clock=clock
    )

    with pytest.raises(RuntimeError):
        await b.call(_fail())

    assert b.state == CircuitState.OPEN

    clock.advance(35.0)  # past cooldown
    # Calling state property triggers time-based transition
    assert b.state == CircuitState.HALF_OPEN


# ---------------------------------------------------------------------------
# CB5 — Closes on successful probe from HALF_OPEN
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_closes_on_successful_probe():
    from maiw_mcp.circuit_breaker import CircuitBreaker, CircuitState

    clock = FakeClock()
    b = CircuitBreaker(
        domain="test",
        failure_threshold=1,
        cooldown_seconds=30.0,
        success_threshold=1,
        clock=clock,
    )

    with pytest.raises(RuntimeError):
        await b.call(_fail())

    clock.advance(31.0)
    assert b.state == CircuitState.HALF_OPEN

    result = await b.call(_ok())
    assert result == "ok"
    assert b.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# CB6 — Re-trips on failed probe, cooldown resets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_re_trips_on_failed_probe():
    from maiw_mcp.circuit_breaker import CircuitBreaker, CircuitState

    clock = FakeClock()
    b = CircuitBreaker(
        domain="test", failure_threshold=1, cooldown_seconds=30.0, clock=clock
    )

    with pytest.raises(RuntimeError):
        await b.call(_fail())

    clock.advance(31.0)
    assert b.state == CircuitState.HALF_OPEN

    with pytest.raises(RuntimeError):
        await b.call(_fail())

    assert b.state == CircuitState.OPEN
    # Cooldown should have reset (new opened_at)
    assert b._cooldown_remaining() > 0


# ---------------------------------------------------------------------------
# CB7 — Success in CLOSED resets failure counter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_success_resets_failure_counter_in_closed():
    from maiw_mcp.circuit_breaker import CircuitBreaker, CircuitState

    clock = FakeClock()
    b = CircuitBreaker(
        domain="test", failure_threshold=3, cooldown_seconds=30.0, clock=clock
    )

    # Two failures
    for _ in range(2):
        with pytest.raises(RuntimeError):
            await b.call(_fail())

    assert b._failure_count == 2
    assert b.state == CircuitState.CLOSED

    # One success resets counter
    await b.call(_ok())
    assert b._failure_count == 0
    assert b.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# CB8 — Partial failures below threshold don't trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_partial_failures_dont_trip():
    from maiw_mcp.circuit_breaker import CircuitBreaker, CircuitState

    b = CircuitBreaker(domain="test", failure_threshold=5)
    for _ in range(4):
        with pytest.raises(RuntimeError):
            await b.call(_fail())
    assert b.state == CircuitState.CLOSED
    assert b._failure_count == 4


# ---------------------------------------------------------------------------
# CB9 — get_stats returns expected fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_stats_fields():
    from maiw_mcp.circuit_breaker import CircuitBreaker

    b = CircuitBreaker(domain="equipment", failure_threshold=5)
    await b.call(_ok())
    stats = b.get_stats()
    assert stats["domain"] == "equipment"
    assert stats["state"] == "closed"
    assert stats["failure_threshold"] == 5
    assert "total_calls" in stats
    assert "total_failures" in stats
    assert "trip_count" in stats


# ---------------------------------------------------------------------------
# CB10 — reset() forces CLOSED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_forces_closed():
    from maiw_mcp.circuit_breaker import CircuitBreaker, CircuitState

    clock = FakeClock()
    b = CircuitBreaker(
        domain="test", failure_threshold=1, cooldown_seconds=30.0, clock=clock
    )
    with pytest.raises(RuntimeError):
        await b.call(_fail())
    assert b.state == CircuitState.OPEN
    b.reset()
    assert b.state == CircuitState.CLOSED
    assert b._failure_count == 0


# ---------------------------------------------------------------------------
# CB11 — CircuitOpen carries correct domain and cooldown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_circuit_open_has_domain_and_cooldown():
    from maiw_mcp.circuit_breaker import CircuitBreaker, CircuitOpen

    clock = FakeClock()
    b = CircuitBreaker(
        domain="labor", failure_threshold=1, cooldown_seconds=30.0, clock=clock
    )
    with pytest.raises(RuntimeError):
        await b.call(_fail())

    clock.advance(5.0)  # 5s into cooldown, 25s remaining

    with pytest.raises(CircuitOpen) as exc_info:
        await b.call(_ok())

    exc = exc_info.value
    assert exc.domain == "labor"
    assert 20.0 < exc.cooldown_remaining_s <= 30.0


# ---------------------------------------------------------------------------
# CB12 — Consecutive successes needed in HALF_OPEN (success_threshold > 1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_success_threshold_in_half_open():
    from maiw_mcp.circuit_breaker import CircuitBreaker, CircuitState

    clock = FakeClock()
    b = CircuitBreaker(
        domain="test",
        failure_threshold=1,
        cooldown_seconds=10.0,
        success_threshold=2,
        clock=clock,
    )
    with pytest.raises(RuntimeError):
        await b.call(_fail())

    clock.advance(11.0)
    assert b.state == CircuitState.HALF_OPEN

    # First probe success — still HALF_OPEN (need 2)
    await b.call(_ok())
    # Hmm — after a success in HALF_OPEN, _probing is cleared. State should be HALF_OPEN still.
    # Actually our breaker checks success_count >= success_threshold. Let's check.
    # After first success: success_count=1 < 2, stays HALF_OPEN.
    # But _probing is reset to False in finally — so a second probe can enter.
    assert b._success_count == 1
    assert b.state == CircuitState.HALF_OPEN

    # Second probe — closes
    await b.call(_ok())
    assert b.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# CB13 — DomainCircuitRegistry creates independent per-domain breakers
# ---------------------------------------------------------------------------


def test_domain_registry_creates_per_domain_breakers():
    from maiw_mcp.circuit_registry import DomainCircuitRegistry

    reg = DomainCircuitRegistry.for_domains(
        domains=["equipment", "labor", "wave", "inventory"],
        failure_threshold=3,
        cooldown_seconds=30.0,
    )
    for domain in ("equipment", "labor", "wave", "inventory"):
        b = reg.get(domain)
        assert b is not None
        assert b.domain == domain
        assert b.failure_threshold == 3

    # All breakers are distinct objects
    eq = reg.get("equipment")
    lab = reg.get("labor")
    assert eq is not lab


# ---------------------------------------------------------------------------
# CB14 — Domain isolation: tripping one domain doesn't affect others
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_domain_isolation():
    from maiw_mcp.circuit_breaker import CircuitOpen, CircuitState
    from maiw_mcp.circuit_registry import DomainCircuitRegistry

    reg = DomainCircuitRegistry.for_domains(
        domains=["equipment", "labor"],
        failure_threshold=2,
        cooldown_seconds=30.0,
    )
    labor_breaker = reg.get("labor")
    equipment_breaker = reg.get("equipment")

    # Trip labor circuit
    for _ in range(2):
        with pytest.raises(RuntimeError):
            await labor_breaker.call(_fail())

    assert labor_breaker.state == CircuitState.OPEN

    # Equipment circuit unaffected
    assert equipment_breaker.state == CircuitState.CLOSED
    result = await equipment_breaker.call(_ok())
    assert result == "ok"


# ---------------------------------------------------------------------------
# CB15 — DomainCircuitRegistry.operational_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_operational_status_labels():
    from maiw_mcp.circuit_breaker import CircuitState
    from maiw_mcp.circuit_registry import DomainCircuitRegistry

    clock = FakeClock()
    reg = DomainCircuitRegistry.for_domains(
        domains=["equipment", "labor"],
        failure_threshold=2,
        cooldown_seconds=30.0,
        clock=clock,
    )

    status = reg.operational_status()
    assert status["equipment"] == "HEALTHY"
    assert status["labor"] == "HEALTHY"

    # Introduce 1 failure — DEGRADED
    lab = reg.get("labor")
    with pytest.raises(RuntimeError):
        await lab.call(_fail())
    status = reg.operational_status()
    assert status["labor"] == "DEGRADED"
    assert status["equipment"] == "HEALTHY"

    # Trip labor to OPEN
    with pytest.raises(RuntimeError):
        await lab.call(_fail())
    status = reg.operational_status()
    assert status["labor"] == "CIRCUIT OPEN"
    assert status["equipment"] == "HEALTHY"


# ---------------------------------------------------------------------------
# CB16 — Config properties exist and have defaults
# ---------------------------------------------------------------------------


def test_config_circuit_breaker_defaults():
    from maiw_api.config import Settings

    s = Settings()
    assert s.circuit_failure_threshold == 5
    assert s.circuit_cooldown_seconds == 30.0
    assert s.circuit_success_threshold == 1


def test_config_circuit_breaker_env_override(monkeypatch):
    monkeypatch.setenv("MAIW_CIRCUIT_FAILURE_THRESHOLD", "3")
    monkeypatch.setenv("MAIW_CIRCUIT_COOLDOWN_SECONDS", "60")
    monkeypatch.setenv("MAIW_CIRCUIT_SUCCESS_THRESHOLD", "2")
    from maiw_api.config import Settings

    s = Settings()
    assert s.circuit_failure_threshold == 3
    assert s.circuit_cooldown_seconds == 60.0
    assert s.circuit_success_threshold == 2


# ---------------------------------------------------------------------------
# CB17 — MAIWMCPClient accepts circuit_registry kwarg
# ---------------------------------------------------------------------------


def test_mcp_client_accepts_circuit_registry():
    import inspect
    from maiw_mcp.client.client import MAIWMCPClient

    sig = inspect.signature(MAIWMCPClient.__init__)
    assert "circuit_registry" in sig.parameters


# ---------------------------------------------------------------------------
# CB18 — ModelGateway accepts nim_circuit kwarg
# ---------------------------------------------------------------------------


def test_model_gateway_accepts_nim_circuit():
    import inspect
    from maiw_models.gateway import ModelGateway

    sig = inspect.signature(ModelGateway.__init__)
    assert "nim_circuit" in sig.parameters
