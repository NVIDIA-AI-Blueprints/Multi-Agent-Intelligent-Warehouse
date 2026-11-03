# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
IoT adapters never report an acknowledgment or emergency dispatch that did not happen.

The BACnet, Modbus and WebSocket paths of ``acknowledge_alert`` used to log and
return True, and ``SafetySensorAdapter.trigger_emergency_protocol`` logged
"EMERGENCY PROTOCOL TRIGGERED" and returned True over BACnet without sending
anything (SonarQube python:S3516).
"""

from __future__ import annotations

import paho.mqtt.client as mqtt
import pytest

from src.adapters.iot.base import IoTDataError
from src.adapters.iot.environmental import EnvironmentalSensorAdapter
from src.adapters.iot.equipment_monitor import EquipmentMonitorAdapter
from src.adapters.iot.safety_sensors import SafetySensorAdapter


def _connected(adapter_cls, protocol):
    adapter = adapter_cls({"host": "device.invalid", "protocol": protocol})
    adapter.connected = True
    return adapter


async def test_safety_bacnet_acknowledgment_is_not_reported_as_done():
    adapter = _connected(SafetySensorAdapter, "bacnet")
    assert await adapter.acknowledge_alert("ALERT-1") is False


async def test_safety_bacnet_emergency_dispatch_fails_loudly(caplog):
    adapter = _connected(SafetySensorAdapter, "bacnet")
    with pytest.raises(IoTDataError, match="not supported"):
        await adapter.trigger_emergency_protocol("fire", "Zone A")
    assert "EMERGENCY PROTOCOL TRIGGERED" not in caplog.text
    assert "EMERGENCY PROTOCOL NOT DISPATCHED" in caplog.text


async def test_environmental_modbus_acknowledgment_is_not_reported_as_done():
    adapter = _connected(EnvironmentalSensorAdapter, "modbus")
    assert await adapter.acknowledge_alert("ALERT-2") is False


async def test_equipment_websocket_acknowledgment_is_not_reported_as_done():
    adapter = _connected(EquipmentMonitorAdapter, "websocket")
    assert await adapter.acknowledge_alert("ALERT-3") is False


async def test_equipment_mqtt_without_client_is_not_reported_as_done():
    adapter = _connected(EquipmentMonitorAdapter, "mqtt")
    assert adapter.mqtt_client is None
    assert await adapter.acknowledge_alert("ALERT-4") is False


class _Client:
    """Stands in for a paho client; ``publish`` returns an info with ``rc``."""

    def __init__(self, rc):
        self.rc = rc
        self.published = []

    def publish(self, topic, payload):
        self.published.append((topic, payload))
        info = mqtt.MQTTMessageInfo(1)
        info.rc = self.rc
        return info


async def test_equipment_mqtt_acknowledgment_follows_the_publish_result():
    adapter = _connected(EquipmentMonitorAdapter, "mqtt")

    adapter.mqtt_client = _Client(mqtt.MQTT_ERR_SUCCESS)
    assert await adapter.acknowledge_alert("ALERT-5") is True
    assert adapter.mqtt_client.published == [
        ("alerts/ALERT-5/acknowledge", '{"acknowledged": true}')
    ]

    adapter.mqtt_client = _Client(mqtt.MQTT_ERR_NO_CONN)
    assert await adapter.acknowledge_alert("ALERT-6") is False
