# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
WebSocket integrations against the installed ``websockets`` release.

The Compose deployment exercises MCP over streamable HTTP only, so nothing
else runs the code paths that call ``websockets.connect``. Each test here
drives one of them against a real ``websockets`` server on localhost:

- EquipmentMonitorAdapter (protocol ``websocket``): connect, push, disconnect
- AssetTrackingAdapter (protocol ``websocket``): push, alert acknowledgement
- MCPClient (legacy WebSocket transport): JSON-RPC handshake and tool call
"""

from __future__ import annotations

import asyncio
import json

import pytest
from websockets.asyncio.server import serve

from src.adapters.iot.asset_tracking import AssetTrackingAdapter
from src.adapters.iot.equipment_monitor import EquipmentMonitorAdapter
from src.api.services.mcp.client import MCPClient, MCPConnectionType


class _Peer:
    """A localhost WebSocket server that records what clients send."""

    def __init__(self, on_message=None):
        self.paths: list[str] = []
        self.received: list[dict] = []
        self.connected = asyncio.Event()
        self.closed = asyncio.Event()
        self._connection = None
        self._on_message = on_message

    async def handler(self, connection):
        self._connection = connection
        self.paths.append(connection.request.path)
        self.connected.set()
        try:
            async for raw in connection:
                message = json.loads(raw)
                self.received.append(message)
                if self._on_message:
                    reply = self._on_message(message)
                    if reply is not None:
                        await connection.send(json.dumps(reply))
        finally:
            self.closed.set()

    async def push(self, payload: dict) -> None:
        await self._connection.send(json.dumps(payload))


@pytest.fixture
async def peer_server():
    peers = []

    async def start(on_message=None):
        peer = _Peer(on_message)
        server = await serve(peer.handler, "127.0.0.1", 0)
        peers.append(server)
        return peer, server.sockets[0].getsockname()[1]

    yield start
    for server in peers:
        server.close()
        await server.wait_closed()


async def _wait_for(event: asyncio.Event) -> None:
    await asyncio.wait_for(event.wait(), timeout=5)


async def test_equipment_monitor_websocket_receives_pushes(peer_server):
    peer, port = await peer_server()
    adapter = EquipmentMonitorAdapter(
        {"host": "127.0.0.1", "port": port, "protocol": "websocket"}
    )
    received = asyncio.Event()
    seen = {}

    async def on_update(source, data):
        seen.update(source=source, data=data)
        received.set()

    assert await adapter.connect() is True
    await _wait_for(peer.connected)
    assert peer.paths == ["/ws"]

    assert await adapter.start_real_time_monitoring(on_update) is True
    await peer.push({"equipment_id": "FL-01", "status": "online"})
    await _wait_for(received)
    assert seen == {
        "source": "websocket",
        "data": {"equipment_id": "FL-01", "status": "online"},
    }

    assert await adapter.disconnect() is True
    await _wait_for(peer.closed)


async def test_asset_tracking_websocket_pushes_and_acknowledges(peer_server):
    peer, port = await peer_server()
    adapter = AssetTrackingAdapter(
        {"host": "127.0.0.1", "port": port, "protocol": "websocket"}
    )
    received = asyncio.Event()
    seen = {}

    async def on_update(source, data):
        seen.update(source=source, data=data)
        received.set()

    assert await adapter.connect() is True
    await _wait_for(peer.connected)
    assert peer.paths == ["/ws/tracking"]

    assert await adapter.start_real_time_monitoring(on_update) is True
    location = {"type": "asset_location", "asset_id": "PAL-9", "location": "dock-2"}
    await peer.push(location)
    await _wait_for(received)
    assert seen == {"source": "asset_tracking", "data": location}

    assert await adapter.acknowledge_alert("ALERT-7") is True
    for _ in range(50):
        if peer.received:
            break
        await asyncio.sleep(0.05)
    assert peer.received == [{"type": "acknowledge_alert", "alert_id": "ALERT-7"}]

    await adapter.stop_real_time_monitoring()
    assert await adapter.disconnect() is True
    await _wait_for(peer.closed)


def _json_rpc(message: dict) -> dict:
    results = {
        "initialize": {"capabilities": {"tools": {}}},
        "tools/list": {
            "tools": [
                {
                    "name": "get_status",
                    "description": "Equipment status",
                    "inputSchema": {"type": "object"},
                }
            ]
        },
        "resources/list": {"resources": []},
        "prompts/list": {"prompts": []},
        "tools/call": {"content": [{"type": "text", "text": "FL-01 online"}]},
    }
    return {"jsonrpc": "2.0", "id": message["id"], "result": results[message["method"]]}


async def test_mcp_client_websocket_transport(peer_server):
    peer, port = await peer_server(on_message=_json_rpc)
    client = MCPClient()

    assert (
        await client.connect_server(
            "equipment", MCPConnectionType.WEBSOCKET, f"ws://127.0.0.1:{port}/mcp"
        )
        is True
    )
    assert "get_status" in client.tools

    result = await client.call_tool("get_status", {"asset_id": "FL-01"})
    assert result == {"content": [{"type": "text", "text": "FL-01 online"}]}
    assert [m["method"] for m in peer.received] == [
        "initialize",
        "tools/list",
        "resources/list",
        "prompts/list",
        "tools/call",
    ]
    assert peer.received[-1]["params"] == {
        "name": "get_status",
        "arguments": {"asset_id": "FL-01"},
    }

    assert await client.disconnect_server("equipment") is True
    await _wait_for(peer.closed)
