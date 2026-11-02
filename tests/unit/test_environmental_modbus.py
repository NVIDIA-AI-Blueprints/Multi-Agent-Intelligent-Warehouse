# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
EnvironmentalSensorAdapter Modbus path against the installed pymodbus 3.x.

pymodbus 3.x made ``count`` keyword-only on ``read_holding_registers``; a
positional call raises TypeError, which the adapter logged and swallowed, so
every Modbus read returned no readings. This test reads holding registers
from a real pymodbus TCP server on localhost.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time

import pytest
from pymodbus.server import ModbusTcpServer
from pymodbus.simulator import DataType, SimData, SimDevice

from src.adapters.iot.environmental import EnvironmentalSensorAdapter

# Holding registers 0..9; register 4 holds 215 (21.5 °C at scale 0.1),
# register 7 holds 48 (48 % humidity).
REGISTERS = [0, 0, 0, 0, 215, 0, 0, 48, 0, 0]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def modbus_server():
    port = _free_port()
    device = SimDevice(1, [SimData(0, values=REGISTERS, datatype=DataType.REGISTERS)])
    loop = asyncio.new_event_loop()
    holder = {}

    async def serve():
        # the server must be created inside its running loop
        holder["server"] = ModbusTcpServer(device, address=("127.0.0.1", port))
        await holder["server"].serve_forever()

    def run():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(serve())

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            time.sleep(0.1)
    yield port
    asyncio.run_coroutine_threadsafe(holder["server"].shutdown(), loop).result(5)
    thread.join(5)
    loop.close()


async def test_modbus_holding_registers_become_sensor_readings(modbus_server):
    adapter = EnvironmentalSensorAdapter(
        {
            "host": "127.0.0.1",
            "port": modbus_server,
            "protocol": "modbus",
            "modbus_config": {
                "timeout": 2,
                "register_map": {
                    "temperature": {
                        "sensor_id": "temp-1",
                        "address": 4,
                        "count": 1,
                        "scale": 0.1,
                        "unit": "C",
                    },
                    "humidity": {
                        "sensor_id": "hum-1",
                        "address": 7,
                        "count": 1,
                        "unit": "%",
                    },
                },
            },
        }
    )

    assert await adapter.connect() is True
    try:
        readings = await adapter.get_sensor_readings()
    finally:
        await adapter.disconnect()

    by_id = {r.sensor_id: r for r in readings}
    assert set(by_id) == {"temp-1", "hum-1"}
    assert by_id["temp-1"].value == pytest.approx(21.5)
    assert by_id["temp-1"].metadata["raw_value"] == 215
    assert by_id["hum-1"].value == 48
