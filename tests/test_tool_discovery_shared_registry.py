# SPDX-License-Identifier: Apache-2.0
"""
Regression tests for the tool-discovery registry fragmentation bug.

Observed failure (2026-07-28, local deployment):
    Nine separate `ToolDiscoveryService()` instances are constructed across the
    codebase (5 agents, 2 planner graphs, the MCP router, the evidence
    collector). Each keeps its own `discovered_tools` dict plus its own 30s
    discovery loop and 300s cleanup loop, so a source registered by one agent is
    invisible to every other consumer.

    The planner graph builds its own instance and registers no adapters into it,
    so `get_available_tools()` returns 0 and the equipment/safety agents stall
    until their 45s budget expires and emit
    "The system is taking longer than expected to process it."

    Log signature (same request, interleaved, different objects):
        Tool discovery completed: 0 tools discovered from 0 sources
        Tool discovery completed: 4 tools discovered from 1 sources

These tests pin the *contract* we want: all consumers share one registry, and a
tool registered anywhere is discoverable everywhere.
"""

import asyncio
from types import SimpleNamespace

from src.api.services.mcp.tool_discovery import ToolDiscoveryService


class _FakeTool:
    """Stand-in for an MCP tool.

    Must satisfy every attribute `_discover_from_mcp_adapter` touches --
    name/description/parameters/tool_type.value/handler -- because that method
    swallows AttributeError into a log line and returns 0 tools, which would
    make a shape mismatch look identical to the fragmentation bug.
    """

    def __init__(self, name):
        self.name = name
        self.description = f"fake tool {name}"
        self.parameters = {}
        self.tool_type = SimpleNamespace(value="function")
        self.handler = lambda **kw: None


class _FakeAdapter:
    """Minimal stand-in for an MCP adapter (mirrors EquipmentMCPAdapter shape)."""

    def __init__(self, names):
        self.tools = {n: _FakeTool(n) for n in names}
        self.config = SimpleNamespace(
            adapter_type=SimpleNamespace(value="equipment_asset_tools")
        )


def test_service_is_shared_not_per_consumer():
    """Every consumer must resolve to the SAME service object.

    Currently fails: there is no shared accessor, and each call site does
    `ToolDiscoveryService()`, producing independent registries.
    """
    from src.api.services.mcp.tool_discovery import get_tool_discovery_service

    assert get_tool_discovery_service() is get_tool_discovery_service()


def test_source_registered_by_one_consumer_is_visible_to_another():
    """An adapter registered by the equipment agent must be visible to the planner graph.

    This is the exact production failure: the planner graph asks its own instance
    and gets 0 tools while the agent's instance holds 4.
    """
    from src.api.services.mcp.tool_discovery import get_tool_discovery_service

    async def scenario():
        agent_view = get_tool_discovery_service()
        await agent_view.register_discovery_source(
            "equipment_asset_tools", _FakeAdapter(["get_equipment_status"]), "mcp_adapter"
        )
        await agent_view.discover_all_tools()

        planner_view = get_tool_discovery_service()
        # get_available_tools() returns List[Dict], not tool objects.
        tools = await planner_view.get_available_tools()
        names = {t["name"] for t in tools}
        assert "get_equipment_status" in names, (
            f"planner saw {len(tools)} tools {names}; registry is fragmented"
        )

    asyncio.run(scenario())


def test_discovery_does_not_duplicate_tools_on_each_cycle():
    """A tool must be registered once, not once per discovery cycle.

    `register_discovery_source` runs an immediate discovery, and the 30s
    `_discovery_loop` runs `discover_all_tools()` again -- each pass storing the
    SAME tool under a fresh uuid4 key. The registry therefore grows without
    bound while `_cleanup_old_data` reaps the stale copies 300s later, which is
    the observed production churn:

        Cleaned up 4 old tools
        Tool discovery completed: 0 tools discovered from 0 sources

    Expected: one logical tool -> one registry entry, however many cycles run.
    """
    from src.api.services.mcp.tool_discovery import get_tool_discovery_service

    async def scenario():
        svc = get_tool_discovery_service()
        await svc.register_discovery_source(
            "equipment_asset_tools", _FakeAdapter(["get_equipment_status"]), "mcp_adapter"
        )
        await svc.discover_all_tools()
        await svc.discover_all_tools()

        tools = await svc.get_available_tools()
        matching = [t for t in tools if t["name"] == "get_equipment_status"]
        assert len(matching) == 1, (
            f"tool registered {len(matching)}x after 3 discovery passes; "
            "registry duplicates on every cycle"
        )

    asyncio.run(scenario())


def test_independent_instances_do_not_share_state():
    """Documents the CURRENT broken behaviour so the fix is provably a change.

    Two directly-constructed services must not see each other's sources. This
    test passes today and must KEEP passing after the fix — direct construction
    stays available for tests and isolation; only the shared accessor is added.
    """

    async def scenario():
        a = ToolDiscoveryService()
        b = ToolDiscoveryService()
        await a.register_discovery_source(
            "equipment_asset_tools", _FakeAdapter(["get_equipment_status"]), "mcp_adapter"
        )
        await a.discover_all_tools()

        assert len(await b.get_available_tools()) == 0

    asyncio.run(scenario())
