"""
Environmental Sensor IoT Adapter.

Provides integration with environmental monitoring systems for
temperature, humidity, air quality, and other environmental factors.
"""
import asyncio
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import httpx
import logging
from .base import (
    BaseIoTAdapter, SensorReading, Equipment, Alert,
    SensorType, EquipmentStatus, IoTConnectionError, IoTDataError
)

logger = logging.getLogger(__name__)

class EnvironmentalSensorAdapter(BaseIoTAdapter):
    """
    Environmental Sensor Adapter for warehouse environmental monitoring.
    
    Monitors temperature, humidity, air quality, lighting, and other
    environmental factors that affect warehouse operations.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Environmental Sensor adapter.
        
        Args:
            config: Configuration containing:
                - host: Environmental sensor system host
                - port: Port (default: 8080)
                - protocol: Connection protocol (http, mqtt, modbus)
                - username: Authentication username
                - password: Authentication password
                - api_key: API key for HTTP authentication
                - modbus_config: Modbus configuration (for Modbus protocol)
                - zones: List of environmental zones to monitor
        """
        super().__init__(config)
        self.host = config.get('host')
        self.port = config.get('port', 8080)
        self.protocol = config.get('protocol', 'http')
        self.username = config.get('username')
        self.password = config.get('password')
        self.api_key = config.get('api_key')
        self.modbus_config = config.get('modbus_config', {})
        self.zones = config.get('zones', ['warehouse', 'loading_dock', 'office'])
        
        self.session: Optional[httpx.AsyncClient] = None
        self.modbus_client = None
        
        # Environmental monitoring endpoints
        if self.protocol == 'http':
            self.base_url = f"http://{self.host}:{self.port}/api/v1"
            self.endpoints = {
                'sensors': '/environmental/sensors',
                'readings': '/environmental/readings',
                'zones': '/environmental/zones',
                'alerts': '/environmental/alerts',
                'status': '/environmental/status'
            }
    
    async def connect(self) -> bool:
        """Establish connection to environmental sensor system."""
        try:
            if not self._validate_config(['host']):
                return False
            
            if self.protocol == 'http':
                return await self._connect_http()
            elif self.protocol == 'modbus':
                return await self._connect_modbus()
            else:
                self.logger.error(f"Unsupported protocol: {self.protocol}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to connect to environmental sensors: {e}")
            raise IoTConnectionError(f"Environmental sensor connection failed: {e}")
    
    async def _connect_http(self) -> bool:
        """Connect using HTTP REST API."""
        try:
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'
            elif self.username and self.password:
                headers['Authorization'] = f'Basic {self._encode_basic_auth(self.username, self.password)}'
            
            self.session = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=30.0
            )
            
            # Test connection
            response = await self.session.get(self.endpoints['status'])
            if response.status_code == 200:
                self.connected = True
                self.logger.info("Successfully connected to environmental sensors via HTTP")
                return True
            else:
                self.logger.error(f"HTTP connection test failed: {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.error(f"HTTP connection failed: {e}")
            return False
    
    async def _connect_modbus(self) -> bool:
        """Connect using Modbus protocol."""
        try:
            from pymodbus.client import ModbusTcpClient
            
            self.modbus_client = ModbusTcpClient(
                host=self.host,
                port=self.port,
                timeout=self.modbus_config.get('timeout', 10)
            )
            
            if self.modbus_client.connect():
                self.connected = True
                self.logger.info("Successfully connected to environmental sensors via Modbus")
                return True
            else:
                self.logger.error("Failed to connect to Modbus server")
                return False
                
        except ImportError:
            self.logger.error("pymodbus library not installed. Install with: pip install pymodbus")
            return False
        except Exception as e:
            self.logger.error(f"Modbus connection failed: {e}")
            return False
    
    async def disconnect(self) -> bool:
        """Disconnect from environmental sensor system."""
        try:
            if self.session:
                await self.session.aclose()
                self.session = None
            
            if self.modbus_client:
                self.modbus_client.close()
                self.modbus_client = None
            
            self.connected = False
            self.logger.info("Disconnected from environmental sensors")
            return True
        except Exception as e:
            self.logger.error(f"Error disconnecting from environmental sensors: {e}")
            return False
    
    async def get_sensor_readings(self, sensor_id: Optional[str] = None,
                                equipment_id: Optional[str] = None,
                                start_time: Optional[datetime] = None,
                                end_time: Optional[datetime] = None) -> List[SensorReading]:
        """Retrieve environmental sensor readings."""
        try:
            if not self.connected:
                raise IoTConnectionError("Not connected to environmental sensors")
            
            if self.protocol == 'http':
                return await self._get_sensor_readings_http(sensor_id, equipment_id, start_time, end_time)
            elif self.protocol == 'modbus':
                return await self._get_sensor_readings_modbus(sensor_id, equipment_id)
            else:
                return []
                
        except Exception as e:
            self.logger.error(f"Failed to get environmental sensor readings: {e}")
            raise IoTDataError(f"Environmental sensor readings retrieval failed: {e}")
    
    async def _get_sensor_readings_http(self, sensor_id: Optional[str] = None,
                                      equipment_id: Optional[str] = None,
                                      start_time: Optional[datetime] = None,
                                      end_time: Optional[datetime] = None) -> List[SensorReading]:
        """Get sensor readings via HTTP API."""
        params = {}
        if sensor_id:
            params['sensor_id'] = sensor_id
        if equipment_id:
            params['equipment_id'] = equipment_id
        if start_time:
            params['start_time'] = start_time.isoformat()
        if end_time:
            params['end_time'] = end_time.isoformat()
        
        response = await self.session.get(self.endpoints['readings'], params=params)
        response.raise_for_status()
        
        data = response.json()
        readings = []
        
        for reading_data in data.get('readings', []):
            reading = SensorReading(
                sensor_id=reading_data.get('sensor_id', ''),
                sensor_type=SensorType(reading_data.get('sensor_type', 'temperature')),
                value=float(reading_data.get('value', 0)),
                unit=reading_data.get('unit', ''),
                timestamp=datetime.fromisoformat(reading_data.get('timestamp', datetime.now().isoformat())),
                location=reading_data.get('location'),
                equipment_id=reading_data.get('equipment_id'),
                quality=float(reading_data.get('quality', 1.0)),
                metadata=reading_data.get('metadata')
            )
            readings.append(reading)
        
        self._log_operation("get_sensor_readings", {"count": len(readings)})
        return readings
    
    async def _get_sensor_readings_modbus(self, sensor_id: Optional[str] = None,
                                        equipment_id: Optional[str] = None) -> List[SensorReading]:
        """Get sensor readings via Modbus."""
        readings = []
        
        try:
            # Read holding registers for sensor data
            # This is a simplified example - actual implementation would depend on device configuration
            register_map = self.modbus_config.get('register_map', {})
            
            for sensor_type, config in register_map.items():
                if sensor_id and config.get('sensor_id') != sensor_id:
                    continue
                
                address = config.get('address', 0)
                count = config.get('count', 1)
                scale = config.get('scale', 1.0)
                unit = config.get('unit', '')
                
                result = self.modbus_client.read_holding_registers(address, count)
                
                if not result.isError():
                    raw_value = result.registers[0]
                    value = raw_value * scale
                    
                    reading = SensorReading(
                        sensor_id=config.get('sensor_id', f"{sensor_type}_{address}"),
                        sensor_type=SensorType(sensor_type),
                        value=value,
                        unit=unit,
                        timestamp=datetime.now(),
                        location=config.get('location'),
                        equipment_id=equipment_id,
                        quality=1.0,
                        metadata={'modbus_address': address, 'raw_value': raw_value}
                    )
                    readings.append(reading)
        
        except Exception as e:
            self.logger.error(f"Error reading Modbus registers: {e}")
        
        self._log_operation("get_sensor_readings_modbus", {"count": len(readings)})
        return readings
    
    async def get_equipment_status(self, equipment_id: Optional[str] = None) -> List[Equipment]:
        """Retrieve environmental equipment status."""
        try:
            if not self.connected:
                raise IoTConnectionError("Not connected to environmental sensors")
            
            if self.protocol == 'http':
                return await self._get_equipment_status_http(equipment_id)
            else:
                # For Modbus, create equipment based on configuration
                equipment_list = []
                for zone in self.zones:
                    equipment = Equipment(
                        equipment_id=f"env_{zone}",
                        name=f"Environmental Monitor - {zone.title()}",
                        type="environmental_monitor",
                        location=zone,
                        status=EquipmentStatus.ONLINE if self.connected else EquipmentStatus.OFFLINE,
                        last_seen=datetime.now(),
                        sensors=[f"temp_{zone}", f"humidity_{zone}", f"air_quality_{zone}"],
                        metadata={'zone': zone}
                    )
                    equipment_list.append(equipment)
                
                return equipment_list
                
        except Exception as e:
            self.logger.error(f"Failed to get environmental equipment status: {e}")
            raise IoTDataError(f"Environmental equipment status retrieval failed: {e}")
    
    async def _get_equipment_status_http(self, equipment_id: Optional[str] = None) -> List[Equipment]:
        """Get equipment status via HTTP API."""
        response = await self.session.get(self.endpoints['sensors'])
        response.raise_for_status()
        
        data = response.json()
        equipment_list = []
        
        for sensor_data in data.get('sensors', []):
            zone = sensor_data.get('zone', 'unknown')
            equipment_id = f"env_{zone}"
            
            # Check if equipment already exists
            existing_equipment = next((e for e in equipment_list if e.equipment_id == equipment_id), None)
            
            if not existing_equipment:
                equipment = Equipment(
                    equipment_id=equipment_id,
                    name=f"Environmental Monitor - {zone.title()}",
                    type="environmental_monitor",
                    location=zone,
                    status=EquipmentStatus.ONLINE,
                    last_seen=datetime.now(),
                    sensors=[],
                    metadata={'zone': zone}
                )
                equipment_list.append(equipment)
                existing_equipment = equipment
            
            # Add sensor to equipment
            if sensor_data.get('sensor_id') not in existing_equipment.sensors:
                existing_equipment.sensors.append(sensor_data.get('sensor_id'))
        
        self._log_operation("get_equipment_status", {"count": len(equipment_list)})
        return equipment_list
    
    async def get_alerts(self, equipment_id: Optional[str] = None,
                        severity: Optional[str] = None,
                        resolved: Optional[bool] = None) -> List[Alert]:
        """Retrieve environmental alerts."""
        try:
            if not self.connected:
                raise IoTConnectionError("Not connected to environmental sensors")
            
            if self.protocol == 'http':
                return await self._get_alerts_http(equipment_id, severity, resolved)
            else:
                # For Modbus, generate alerts based on current readings
                return await self._generate_alerts_from_readings()
                
        except Exception as e:
            self.logger.error(f"Failed to get environmental alerts: {e}")
            raise IoTDataError(f"Environmental alerts retrieval failed: {e}")
    
    async def _get_alerts_http(self, equipment_id: Optional[str] = None,
                              severity: Optional[str] = None,
                              resolved: Optional[bool] = None) -> List[Alert]:
        """Get alerts via HTTP API."""
        params = {}
        if equipment_id:
            params['equipment_id'] = equipment_id
        if severity:
            params['severity'] = severity
        if resolved is not None:
            params['resolved'] = resolved
        
        response = await self.session.get(self.endpoints['alerts'], params=params)
        response.raise_for_status()
        
        data = response.json()
        alerts = []
        
        for alert_data in data.get('alerts', []):
            alert = Alert(
                alert_id=alert_data.get('alert_id', ''),
                equipment_id=alert_data.get('equipment_id', ''),
                sensor_id=alert_data.get('sensor_id'),
                alert_type=alert_data.get('alert_type', 'threshold'),
                severity=alert_data.get('severity', 'warning'),
                message=alert_data.get('message', ''),
                value=float(alert_data.get('value')) if alert_data.get('value') else None,
                threshold=float(alert_data.get('threshold')) if alert_data.get('threshold') else None,
                timestamp=datetime.fromisoformat(alert_data.get('timestamp', datetime.now().isoformat())),
                acknowledged=bool(alert_data.get('acknowledged', False)),
                resolved=bool(alert_data.get('resolved', False))
            )
            alerts.append(alert)
        
        self._log_operation("get_alerts", {"count": len(alerts)})
        return alerts
    
    async def _generate_alerts_from_readings(self) -> List[Alert]:
        """Generate alerts based on current sensor readings."""
        alerts = []
        
        # Get current readings
        readings = await self.get_sensor_readings()
        
        # Define thresholds for different sensor types
        thresholds = {
            SensorType.TEMPERATURE: {"low": 15, "high": 30, "critical_low": 5, "critical_high": 40},
            SensorType.HUMIDITY: {"low": 30, "high": 70, "critical_low": 20, "critical_high": 85},
            SensorType.PRESSURE: {"low": 950, "high": 1050, "critical_low": 900, "critical_high": 1100}
        }
        
        for reading in readings:
            sensor_alerts = self._check_thresholds(reading, thresholds)
            alerts.extend(sensor_alerts)
        
        return alerts
    
    async def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an environmental alert."""
        try:
            if not self.connected:
                raise IoTConnectionError("Not connected to environmental sensors")
            
            if self.protocol == 'http':
                response = await self.session.post(f"{self.endpoints['alerts']}/{alert_id}/acknowledge")
                response.raise_for_status()
                return True
            else:
                # For Modbus, log acknowledgment
                self.logger.info(f"Acknowledged environmental alert: {alert_id}")
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to acknowledge environmental alert: {e}")
            raise IoTDataError(f"Environmental alert acknowledgment failed: {e}")
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get environmental sensor system status."""
        try:
            if not self.connected:
                return {"status": "disconnected", "connected": False}
            
            if self.protocol == 'http':
                response = await self.session.get(self.endpoints['status'])
                return response.json()
            else:
                return {
                    "status": "connected",
                    "connected": True,
                    "protocol": self.protocol,
                    "zones": self.zones,
                    "sensor_count": len(self._sensor_cache)
                }
            
        except Exception as e:
            self.logger.error(f"Failed to get environmental system status: {e}")
            return {"status": "error", "connected": False, "error": str(e)}
    
    def _encode_basic_auth(self, username: str, password: str) -> str:
        """Encode basic authentication credentials."""
        import base64
        credentials = f"{username}:{password}"
        return base64.b64encode(credentials.encode()).decode()
