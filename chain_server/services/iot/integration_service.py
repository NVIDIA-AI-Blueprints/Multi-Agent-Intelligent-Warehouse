"""
IoT Integration Service - Manages IoT adapter connections and operations.
"""

import asyncio
from typing import Dict, List, Optional, Any, Union, Callable
from datetime import datetime, timedelta
import logging
from adapters.iot import IoTAdapterFactory, BaseIoTAdapter
from adapters.iot.base import (
    SensorReading,
    Equipment,
    Alert,
    SensorType,
    EquipmentStatus,
)

logger = logging.getLogger(__name__)


class IoTIntegrationService:
    """
    Service for managing IoT integrations and operations.

    Provides a unified interface for working with multiple IoT systems
    and handles connection management, data synchronization, and real-time monitoring.
    """

    def __init__(self):
        self.adapters: Dict[str, BaseIoTAdapter] = {}
        self.logger = logging.getLogger(
            f"{self.__class__.__module__}.{self.__class__.__name__}"
        )
        self._monitoring_callbacks: List[Callable] = []
        self._monitoring_active = False

    async def add_iot_connection(
        self, iot_type: str, config: Dict[str, Any], connection_id: str
    ) -> bool:
        """
        Add a new IoT connection.

        Args:
            iot_type: Type of IoT system (equipment_monitor, environmental, safety_sensors, asset_tracking)
            config: Configuration for the IoT connection
            connection_id: Unique identifier for this connection

        Returns:
            bool: True if connection added successfully
        """
        try:
            adapter = IoTAdapterFactory.create_adapter(iot_type, config, connection_id)

            # Test connection
            connected = await adapter.connect()
            if connected:
                self.adapters[connection_id] = adapter
                self.logger.info(f"Added IoT connection: {connection_id} ({iot_type})")

                # Start real-time monitoring if callbacks are registered
                if self._monitoring_callbacks:
                    await self._start_monitoring_for_adapter(adapter)

                return True
            else:
                self.logger.error(f"Failed to connect to IoT system: {connection_id}")
                return False

        except Exception as e:
            self.logger.error(f"Error adding IoT connection {connection_id}: {e}")
            return False

    async def remove_iot_connection(self, connection_id: str) -> bool:
        """
        Remove an IoT connection.

        Args:
            connection_id: Connection identifier to remove

        Returns:
            bool: True if connection removed successfully
        """
        try:
            if connection_id in self.adapters:
                adapter = self.adapters[connection_id]

                # Stop monitoring if active
                if self._monitoring_active:
                    await adapter.stop_real_time_monitoring()

                await adapter.disconnect()
                del self.adapters[connection_id]

                # Also remove from factory cache
                IoTAdapterFactory.remove_adapter(
                    adapter.__class__.__name__.lower().replace("adapter", ""),
                    connection_id,
                )

                self.logger.info(f"Removed IoT connection: {connection_id}")
                return True
            else:
                self.logger.warning(f"IoT connection not found: {connection_id}")
                return False

        except Exception as e:
            self.logger.error(f"Error removing IoT connection {connection_id}: {e}")
            return False

    async def get_connection_status(
        self, connection_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get connection status for IoT systems.

        Args:
            connection_id: Optional specific connection to check

        Returns:
            Dict[str, Any]: Connection status information
        """
        if connection_id:
            if connection_id in self.adapters:
                adapter = self.adapters[connection_id]
                return await adapter.health_check()
            else:
                return {"status": "not_found", "connected": False}
        else:
            # Check all connections
            status = {}
            for conn_id, adapter in self.adapters.items():
                status[conn_id] = await adapter.health_check()
            return status

    async def get_sensor_readings(
        self,
        connection_id: str,
        sensor_id: Optional[str] = None,
        equipment_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[SensorReading]:
        """
        Get sensor readings from a specific IoT connection.

        Args:
            connection_id: IoT connection identifier
            sensor_id: Optional specific sensor filter
            equipment_id: Optional equipment filter
            start_time: Optional start time filter
            end_time: Optional end time filter

        Returns:
            List[SensorReading]: Sensor readings
        """
        if connection_id not in self.adapters:
            raise ValueError(f"IoT connection not found: {connection_id}")

        adapter = self.adapters[connection_id]
        return await adapter.get_sensor_readings(
            sensor_id, equipment_id, start_time, end_time
        )

    async def get_sensor_readings_all(
        self,
        sensor_id: Optional[str] = None,
        equipment_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, List[SensorReading]]:
        """
        Get sensor readings from all IoT connections.

        Args:
            sensor_id: Optional specific sensor filter
            equipment_id: Optional equipment filter
            start_time: Optional start time filter
            end_time: Optional end time filter

        Returns:
            Dict[str, List[SensorReading]]: Sensor readings by connection ID
        """
        results = {}

        for connection_id, adapter in self.adapters.items():
            try:
                readings = await adapter.get_sensor_readings(
                    sensor_id, equipment_id, start_time, end_time
                )
                results[connection_id] = readings
            except Exception as e:
                self.logger.error(
                    f"Error getting sensor readings from {connection_id}: {e}"
                )
                results[connection_id] = []

        return results

    async def get_equipment_status(
        self, connection_id: str, equipment_id: Optional[str] = None
    ) -> List[Equipment]:
        """
        Get equipment status from a specific IoT connection.

        Args:
            connection_id: IoT connection identifier
            equipment_id: Optional specific equipment filter

        Returns:
            List[Equipment]: Equipment status
        """
        if connection_id not in self.adapters:
            raise ValueError(f"IoT connection not found: {connection_id}")

        adapter = self.adapters[connection_id]
        return await adapter.get_equipment_status(equipment_id)

    async def get_equipment_status_all(
        self, equipment_id: Optional[str] = None
    ) -> Dict[str, List[Equipment]]:
        """
        Get equipment status from all IoT connections.

        Args:
            equipment_id: Optional specific equipment filter

        Returns:
            Dict[str, List[Equipment]]: Equipment status by connection ID
        """
        results = {}

        for connection_id, adapter in self.adapters.items():
            try:
                equipment = await adapter.get_equipment_status(equipment_id)
                results[connection_id] = equipment
            except Exception as e:
                self.logger.error(
                    f"Error getting equipment status from {connection_id}: {e}"
                )
                results[connection_id] = []

        return results

    async def get_alerts(
        self,
        connection_id: str,
        equipment_id: Optional[str] = None,
        severity: Optional[str] = None,
        resolved: Optional[bool] = None,
    ) -> List[Alert]:
        """
        Get alerts from a specific IoT connection.

        Args:
            connection_id: IoT connection identifier
            equipment_id: Optional equipment filter
            severity: Optional severity filter
            resolved: Optional resolved status filter

        Returns:
            List[Alert]: Alerts
        """
        if connection_id not in self.adapters:
            raise ValueError(f"IoT connection not found: {connection_id}")

        adapter = self.adapters[connection_id]
        return await adapter.get_alerts(equipment_id, severity, resolved)

    async def get_alerts_all(
        self,
        equipment_id: Optional[str] = None,
        severity: Optional[str] = None,
        resolved: Optional[bool] = None,
    ) -> Dict[str, List[Alert]]:
        """
        Get alerts from all IoT connections.

        Args:
            equipment_id: Optional equipment filter
            severity: Optional severity filter
            resolved: Optional resolved status filter

        Returns:
            Dict[str, List[Alert]]: Alerts by connection ID
        """
        results = {}

        for connection_id, adapter in self.adapters.items():
            try:
                alerts = await adapter.get_alerts(equipment_id, severity, resolved)
                results[connection_id] = alerts
            except Exception as e:
                self.logger.error(f"Error getting alerts from {connection_id}: {e}")
                results[connection_id] = []

        return results

    async def acknowledge_alert(self, connection_id: str, alert_id: str) -> bool:
        """
        Acknowledge an alert in a specific IoT connection.

        Args:
            connection_id: IoT connection identifier
            alert_id: Alert ID to acknowledge

        Returns:
            bool: True if acknowledgment successful
        """
        if connection_id not in self.adapters:
            raise ValueError(f"IoT connection not found: {connection_id}")

        adapter = self.adapters[connection_id]
        return await adapter.acknowledge_alert(alert_id)

    async def get_aggregated_sensor_data(
        self,
        sensor_type: Optional[SensorType] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get aggregated sensor data across all IoT connections.

        Args:
            sensor_type: Optional sensor type filter
            start_time: Optional start time filter
            end_time: Optional end time filter

        Returns:
            Dict[str, Any]: Aggregated sensor data
        """
        all_readings = await self.get_sensor_readings_all(
            start_time=start_time, end_time=end_time
        )

        # Aggregate by sensor type
        aggregated = {}
        total_readings = 0

        for connection_id, readings in all_readings.items():
            for reading in readings:
                if sensor_type and reading.sensor_type != sensor_type:
                    continue

                sensor_key = (
                    f"{reading.sensor_type.value}_{reading.location or 'unknown'}"
                )

                if sensor_key not in aggregated:
                    aggregated[sensor_key] = {
                        "sensor_type": reading.sensor_type.value,
                        "location": reading.location,
                        "values": [],
                        "timestamps": [],
                        "equipment_ids": set(),
                        "connections": set(),
                    }

                aggregated[sensor_key]["values"].append(reading.value)
                aggregated[sensor_key]["timestamps"].append(reading.timestamp)
                if reading.equipment_id:
                    aggregated[sensor_key]["equipment_ids"].add(reading.equipment_id)
                aggregated[sensor_key]["connections"].add(connection_id)

                total_readings += 1

        # Calculate statistics
        for sensor_key, data in aggregated.items():
            values = data["values"]
            data["count"] = len(values)
            data["min"] = min(values) if values else 0
            data["max"] = max(values) if values else 0
            data["avg"] = sum(values) / len(values) if values else 0
            data["latest"] = values[-1] if values else 0
            data["latest_timestamp"] = (
                data["timestamps"][-1].isoformat() if data["timestamps"] else None
            )
            data["equipment_ids"] = list(data["equipment_ids"])
            data["connections"] = list(data["connections"])
            del data["values"]  # Remove raw values to reduce response size
            del data["timestamps"]

        return {
            "aggregated_sensors": list(aggregated.values()),
            "total_readings": total_readings,
            "sensor_types": len(aggregated),
            "connections": list(self.adapters.keys()),
            "timestamp": datetime.now().isoformat(),
        }

    async def get_equipment_health_summary(self) -> Dict[str, Any]:
        """
        Get equipment health summary across all IoT connections.

        Returns:
            Dict[str, Any]: Equipment health summary
        """
        all_equipment = await self.get_equipment_status_all()

        total_equipment = 0
        online_equipment = 0
        offline_equipment = 0
        maintenance_equipment = 0
        error_equipment = 0

        equipment_by_type = {}
        equipment_by_location = {}

        for connection_id, equipment_list in all_equipment.items():
            for equipment in equipment_list:
                total_equipment += 1

                # Count by status
                if equipment.status == EquipmentStatus.ONLINE:
                    online_equipment += 1
                elif equipment.status == EquipmentStatus.OFFLINE:
                    offline_equipment += 1
                elif equipment.status == EquipmentStatus.MAINTENANCE:
                    maintenance_equipment += 1
                elif equipment.status == EquipmentStatus.ERROR:
                    error_equipment += 1

                # Count by type
                if equipment.type not in equipment_by_type:
                    equipment_by_type[equipment.type] = 0
                equipment_by_type[equipment.type] += 1

                # Count by location
                if equipment.location not in equipment_by_location:
                    equipment_by_location[equipment.location] = 0
                equipment_by_location[equipment.location] += 1

        return {
            "total_equipment": total_equipment,
            "online_equipment": online_equipment,
            "offline_equipment": offline_equipment,
            "maintenance_equipment": maintenance_equipment,
            "error_equipment": error_equipment,
            "equipment_by_type": equipment_by_type,
            "equipment_by_location": equipment_by_location,
            "connections": list(self.adapters.keys()),
            "timestamp": datetime.now().isoformat(),
        }

    async def start_real_time_monitoring(self, callback: Callable) -> bool:
        """
        Start real-time monitoring across all IoT connections.

        Args:
            callback: Function to call when new data is received

        Returns:
            bool: True if monitoring started successfully
        """
        try:
            self._monitoring_callbacks.append(callback)
            self._monitoring_active = True

            # Start monitoring for all existing adapters
            for adapter in self.adapters.values():
                await self._start_monitoring_for_adapter(adapter)

            self.logger.info("Started real-time IoT monitoring")
            return True

        except Exception as e:
            self.logger.error(f"Failed to start real-time monitoring: {e}")
            return False

    async def stop_real_time_monitoring(self) -> bool:
        """
        Stop real-time monitoring across all IoT connections.

        Returns:
            bool: True if monitoring stopped successfully
        """
        try:
            self._monitoring_active = False
            self._monitoring_callbacks.clear()

            # Stop monitoring for all adapters
            for adapter in self.adapters.values():
                await adapter.stop_real_time_monitoring()

            self.logger.info("Stopped real-time IoT monitoring")
            return True

        except Exception as e:
            self.logger.error(f"Failed to stop real-time monitoring: {e}")
            return False

    async def _start_monitoring_for_adapter(self, adapter: BaseIoTAdapter):
        """Start monitoring for a specific adapter."""
        try:
            await adapter.start_real_time_monitoring(self._iot_data_callback)
        except Exception as e:
            self.logger.error(
                f"Failed to start monitoring for adapter {adapter.__class__.__name__}: {e}"
            )

    async def _iot_data_callback(self, source: str, data: Any):
        """Callback for IoT data from adapters."""
        try:
            # Call all registered callbacks
            for callback in self._monitoring_callbacks:
                await callback(source, data)
        except Exception as e:
            self.logger.error(f"Error in IoT data callback: {e}")

    def list_connections(self) -> List[Dict[str, Any]]:
        """
        List all IoT connections.

        Returns:
            List[Dict[str, Any]]: Connection information
        """
        connections = []
        for connection_id, adapter in self.adapters.items():
            connections.append(
                {
                    "connection_id": connection_id,
                    "adapter_type": adapter.__class__.__name__,
                    "connected": adapter.connected,
                    "config_keys": list(adapter.config.keys()),
                }
            )
        return connections


# Global IoT integration service instance
iot_service = IoTIntegrationService()


async def get_iot_service() -> IoTIntegrationService:
    """Get the global IoT integration service instance."""
    return iot_service
