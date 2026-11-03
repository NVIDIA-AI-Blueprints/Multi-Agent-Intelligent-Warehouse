# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
The maiw_skills singleton factories build a usable MCP client for their domain.

Since #71 the six labor and wave factories called
``CapabilityRegistry.register(METADATA)`` with one argument (it takes a
capability name and a server URL) and then ``MAIWMCPClient(server_url=...)``
(the client takes a registry), so every call raised TypeError. The equipment
factories built a registry with ``CapabilityRegistry.from_env()``, which only
reads the inventory URL, so their client could not resolve its own capability.

The shipped API builds these skills from the runtime's client instead, so no
deployment test called the factories (SonarQube python:S930 found them).
"""

from __future__ import annotations

import asyncio

import pytest

from maiw_mcp.client.client import MAIWMCPClient
from maiw_skills.equipment import skills as equipment
from maiw_skills.labor import skills as labor
from maiw_skills.wave import skills as wave

LABOR_URL = "http://labor.test/mcp"
WAVE_URL = "http://wave.test/mcp"
EQUIPMENT_URL = "http://equipment.test/mcp"

# (module, factory, singleton, URL variable, URL, capability)
MCP_FACTORIES = [
    (
        labor,
        "get_labor_capacity_skill",
        "_labor_capacity_skill",
        "MAIW_MCP_SERVER_LABOR_URL",
        LABOR_URL,
        "warehouse.labor.get_capacity",
    ),
    (
        labor,
        "get_labor_allocation_skill",
        "_labor_allocation_skill",
        "MAIW_MCP_SERVER_LABOR_URL",
        LABOR_URL,
        "warehouse.labor.get_allocation",
    ),
    (
        labor,
        "get_execute_labor_allocation_skill",
        "_execute_labor_allocation_skill",
        "MAIW_MCP_SERVER_LABOR_URL",
        LABOR_URL,
        "warehouse.labor.allocate",
    ),
    (
        wave,
        "get_wave_get_skill",
        "_wave_get_skill",
        "MAIW_MCP_SERVER_WAVE_URL",
        WAVE_URL,
        "warehouse.wave.get",
    ),
    (
        wave,
        "get_wave_risk_skill",
        "_wave_risk_skill",
        "MAIW_MCP_SERVER_WAVE_URL",
        WAVE_URL,
        "warehouse.wave.get_risk",
    ),
    (
        wave,
        "get_execute_wave_reprioritization_skill",
        "_execute_wave_reprioritization_skill",
        "MAIW_MCP_SERVER_WAVE_URL",
        WAVE_URL,
        "warehouse.wave.reprioritize",
    ),
    (
        equipment,
        "get_equipment_status_skill",
        "_equipment_status_skill",
        "MAIW_MCP_SERVER_EQUIPMENT_URL",
        EQUIPMENT_URL,
        "warehouse.equipment.get_status",
    ),
    (
        equipment,
        "get_equipment_telemetry_skill",
        "_equipment_telemetry_skill",
        "MAIW_MCP_SERVER_EQUIPMENT_URL",
        EQUIPMENT_URL,
        "warehouse.equipment.get_telemetry",
    ),
    (
        equipment,
        "get_execute_equipment_assignment_skill",
        "_execute_equipment_assignment_skill",
        "MAIW_MCP_SERVER_EQUIPMENT_URL",
        EQUIPMENT_URL,
        "warehouse.equipment.assign",
    ),
    (
        equipment,
        "get_execute_equipment_release_skill",
        "_execute_equipment_release_skill",
        "MAIW_MCP_SERVER_EQUIPMENT_URL",
        EQUIPMENT_URL,
        "warehouse.equipment.release",
    ),
    (
        equipment,
        "get_execute_equipment_maintenance_skill",
        "_execute_equipment_maintenance_skill",
        "MAIW_MCP_SERVER_EQUIPMENT_URL",
        EQUIPMENT_URL,
        "warehouse.equipment.schedule_maintenance",
    ),
]
IDS = [f[1] for f in MCP_FACTORIES]


@pytest.mark.parametrize(
    "module,factory,singleton,env,url,capability", MCP_FACTORIES, ids=IDS
)
def test_factory_builds_a_client_that_routes_its_capability(
    monkeypatch, module, factory, singleton, env, url, capability
):
    monkeypatch.setattr(module, singleton, None)
    monkeypatch.setenv(env, url)

    skill = asyncio.run(getattr(module, factory)())

    client = skill._client
    assert isinstance(client, MAIWMCPClient)
    assert client._registry.resolve(capability) == url
    # Singleton: a second call returns the same skill.
    assert asyncio.run(getattr(module, factory)()) is skill


@pytest.mark.parametrize(
    "module,factory,singleton,env,url,capability", MCP_FACTORIES, ids=IDS
)
def test_factory_without_its_server_url_raises_runtime_error(
    monkeypatch, module, factory, singleton, env, url, capability
):
    monkeypatch.setattr(module, singleton, None)
    monkeypatch.delenv(env, raising=False)

    with pytest.raises(RuntimeError, match=env):
        asyncio.run(getattr(module, factory)())


@pytest.mark.parametrize(
    "module,factory,singleton",
    [
        (
            labor,
            "get_propose_labor_allocation_skill",
            "_propose_labor_allocation_skill",
        ),
        (
            wave,
            "get_propose_wave_reprioritization_skill",
            "_propose_wave_reprioritization_skill",
        ),
        (equipment, "get_equipment_assignment_skill", "_equipment_assignment_skill"),
    ],
)
def test_local_proposal_factories_need_no_server(
    monkeypatch, module, factory, singleton
):
    monkeypatch.setattr(module, singleton, None)
    for env in (
        "MAIW_MCP_SERVER_LABOR_URL",
        "MAIW_MCP_SERVER_WAVE_URL",
        "MAIW_MCP_SERVER_EQUIPMENT_URL",
    ):
        monkeypatch.delenv(env, raising=False)

    assert asyncio.run(getattr(module, factory)()) is not None
