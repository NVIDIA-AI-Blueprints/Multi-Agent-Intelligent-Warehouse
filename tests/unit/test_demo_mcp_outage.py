# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
maiw_api.demo.mcp_outage (fault F12) with a real CapabilityRegistry,
DomainCircuitRegistry and MAIWMCPClient on a fake clock.

The outage lasts until it is ended: after the cooldown the breaker's
half-open probe also fails to connect (nothing is sent) and the circuit opens
again.  Ending the outage restores the original routes and closes the circuit.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from maiw_api.demo.mcp_outage import (
    OutageError,
    UnreachableMCPServer,
    end_all_outages,
    end_outage,
    start_outage,
)
from maiw_mcp.circuit_registry import DomainCircuitRegistry
from maiw_mcp.client.client import MAIWMCPClient
from maiw_mcp.errors import MCPCircuitOpen, MCPConnectFailed, MCPNotDispatched
from maiw_mcp.registry.registry import CapabilityRegistry

LABOR = ["warehouse.labor.allocate", "warehouse.labor.get_capacity"]
EQUIPMENT = "warehouse.equipment.assign"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def runtime():
    clock = Clock()
    registry = CapabilityRegistry()
    labor_server, equipment_server = object(), object()
    registry.register_domain(LABOR, labor_server)
    registry.register(EQUIPMENT, equipment_server)
    circuits = DomainCircuitRegistry.for_domains(
        failure_threshold=3, cooldown_seconds=30.0, clock=clock
    )
    return SimpleNamespace(
        mcp_registry=registry,
        circuit_registry=circuits,
        mcp_client=MAIWMCPClient(registry, circuit_registry=circuits),
        demo_mcp_outages={},
        clock=clock,
        labor_server=labor_server,
        equipment_server=equipment_server,
    )


async def test_outage_trips_only_the_labor_circuit(runtime):
    result = await start_outage(runtime, "labor")

    assert result["circuit_state"] == "open"
    assert result["refused_connections"] == 3
    assert result["capabilities"] == LABOR
    for capability in LABOR:
        assert isinstance(
            runtime.mcp_registry.resolve(capability), UnreachableMCPServer
        )
    assert runtime.mcp_registry.resolve(EQUIPMENT) is runtime.equipment_server
    assert runtime.circuit_registry.operational_status() == {
        "equipment": "HEALTHY",
        "labor": "CIRCUIT OPEN",
        "wave": "HEALTHY",
        "inventory": "HEALTHY",
    }


async def test_outage_outlasts_the_cooldown_probe(runtime):
    await start_outage(runtime, "labor")
    breaker = runtime.circuit_registry.get("labor")

    with pytest.raises(MCPCircuitOpen):
        await runtime.mcp_client.invoke("warehouse.labor.allocate", {})

    runtime.clock.now += 31  # cooldown over → HALF_OPEN, one probe allowed
    assert breaker.get_stats()["state"] == "half_open"
    with pytest.raises(MCPConnectFailed) as excinfo:
        await runtime.mcp_client.invoke("warehouse.labor.allocate", {})
    assert isinstance(excinfo.value, MCPNotDispatched)  # tools/call never sent
    assert breaker.get_stats()["state"] == "open"


async def test_end_outage_restores_routes_and_closes_the_circuit(runtime):
    await start_outage(runtime, "labor")
    await start_outage(runtime, "labor")  # repeat: originals are kept, not overwritten

    assert end_outage(runtime, "labor") == {
        "domain": "labor",
        "circuit_state": "closed",
        "was_out": True,
    }
    for capability in LABOR:
        assert runtime.mcp_registry.resolve(capability) is runtime.labor_server
    assert runtime.demo_mcp_outages == {}
    assert end_outage(runtime, "labor")["was_out"] is False


async def test_end_all_outages(runtime):
    await start_outage(runtime, "labor")
    assert end_all_outages(runtime) == ["labor"]
    assert end_all_outages(runtime) == []
    assert runtime.circuit_registry.get("labor").get_stats()["state"] == "closed"


@pytest.mark.parametrize(
    ("domain", "code", "status"),
    [
        ("billing", "UNKNOWN_MCP_DOMAIN", 422),
        (None, "UNKNOWN_MCP_DOMAIN", 422),
        ("wave", "MCP_DOMAIN_NOT_CONFIGURED", 409),
    ],
)
async def test_rejected_domains(runtime, domain, code, status):
    with pytest.raises(OutageError) as excinfo:
        await start_outage(runtime, domain)
    assert (excinfo.value.code, excinfo.value.status_code) == (code, status)
    assert runtime.demo_mcp_outages == {}
