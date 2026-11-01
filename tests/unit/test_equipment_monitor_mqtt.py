# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
EquipmentMonitorAdapter MQTT path against paho-mqtt 2.x.

paho-mqtt 2.0 made the callback API version the client's first positional
argument and changed the on_connect / on_disconnect signatures. These tests
build a real paho client (network calls stubbed) and drive the adapter's
callbacks with paho's own types.
"""

from __future__ import annotations

import asyncio
import json
import threading

import paho.mqtt.client as mqtt
import pytest
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.reasoncodes import ReasonCode

from src.adapters.iot.equipment_monitor import EquipmentMonitorAdapter


@pytest.fixture
def no_network(monkeypatch):
    monkeypatch.setattr(
        mqtt.Client, "connect", lambda self, *a, **k: mqtt.MQTT_ERR_SUCCESS
    )
    monkeypatch.setattr(mqtt.Client, "loop_start", lambda self: mqtt.MQTT_ERR_SUCCESS)
    monkeypatch.setattr(mqtt.Client, "is_connected", lambda self: True)


def _adapter() -> EquipmentMonitorAdapter:
    return EquipmentMonitorAdapter(
        {"host": "broker.invalid", "protocol": "mqtt", "client_id": "maiw-test"}
    )


async def test_connect_builds_paho2_client(no_network):
    adapter = _adapter()

    assert await adapter.connect() is True

    client = adapter.mqtt_client
    assert isinstance(client, mqtt.Client)
    assert client._callback_api_version == mqtt.CallbackAPIVersion.VERSION2
    assert client._client_id == b"maiw-test"
    assert adapter.connected is True


async def test_connect_and_disconnect_callbacks_use_v2_signatures(no_network):
    adapter = _adapter()
    await adapter.connect()
    client = adapter.mqtt_client
    adapter.connected = False

    client.on_connect(
        client,
        None,
        mqtt.ConnectFlags(session_present=False),
        ReasonCode(PacketTypes.CONNACK, "Success"),
        None,
    )
    assert adapter.connected is True

    client.on_disconnect(
        client,
        None,
        mqtt.DisconnectFlags(is_disconnect_packet_from_server=False),
        ReasonCode(PacketTypes.DISCONNECT, "Normal disconnection"),
        None,
    )
    assert adapter.connected is False

    client.on_connect(
        client,
        None,
        mqtt.ConnectFlags(session_present=False),
        ReasonCode(PacketTypes.CONNACK, "Not authorized"),
        None,
    )
    assert adapter.connected is False


async def test_message_from_network_thread_reaches_monitoring_callback(no_network):
    adapter = _adapter()
    await adapter.connect()
    received = asyncio.Event()
    seen = {}

    async def on_update(topic, payload):
        seen["topic"] = topic
        seen["payload"] = payload
        received.set()

    adapter._monitoring_callback = on_update

    msg = mqtt.MQTTMessage(topic=b"equipment/FL-01/sensors")
    msg.payload = json.dumps(
        {
            "sensors": [
                {"sensor_id": "temp-1", "sensor_type": "temperature", "value": 21.5}
            ]
        }
    ).encode()

    # paho delivers messages on its own network thread, outside the event loop
    worker = threading.Thread(
        target=adapter.mqtt_client.on_message, args=(adapter.mqtt_client, None, msg)
    )
    worker.start()
    worker.join()

    await asyncio.wait_for(received.wait(), timeout=5)
    assert seen["topic"] == "equipment/FL-01/sensors"
    assert adapter._sensor_cache["temp-1"].value == 21.5
