"""
Safety Sensor IoT Adapter.

Provides integration with safety monitoring systems for
fire detection, gas monitoring, emergency systems, and safety equipment.
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

class SafetySensorAdapter(BaseIoTAdapter):
    """
    Safety Sensor Adapter for warehouse safety monitoring.
    
    Monitors fire detection, gas levels, emergency systems, safety equipment,
    and other critical safety factors in warehouse operations.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Safety Sensor adapter.
        
        Args:
            config: Configuration containing:
                - host: Safety sensor system host
                - port: Port (default: 8080)
                - protocol: Connection protocol (http, mqtt, bacnet)
                - username: Authentication username
                - password: Authentication password
                - api_key: API key for HTTP authentication
                - emergency_contacts: List of emergency contact information
                - safety_zones: List of safety zones to monitor
        """
        super().__init__(config)
        self.host = config.get('host')
        self.port = config.get('port', 8080)
        self.protocol = config.get('protocol', 'http')
        self.username = config.get('username')
        self.password = config.get('password')
        self.api_key = config.get('api_key')
        self.emergency_contacts = config.get('emergency_contacts', [])
        self.safety_zones = config.get('safety_zones', ['warehouse', 'loading_dock', 'office', 'maintenance'])
        
        self.session: Optional[httpx.AsyncClient] = None
        self.bacnet_client = None
        
        # Safety monitoring endpoints
        if self.protocol == 'http':
            self.base_url = f"http://{self.host}:{self.port}/api/v1"
            self.endpoints = {
                'sensors': '/safety/sensors',
                'readings': '/safety/readings',
                'alerts': '/safety/alerts',
                'emergency': '/safety/emergency',
                'status': '/safety/status'
            }
    
    async def connect(self) -> bool:
        """Establish connection to safety sensor system."""
        try:
            if not self._validate_config(['host']):
                return False
            
            if self.protocol == 'http':
                return await self._connect_http()
            elif self.protocol == 'bacnet':
                return await self._connect_bacnet()
            else:
                self.logger.error(f"Unsupported protocol: {self.protocol}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to connect to safety sensors: {e}")
            raise IoTConnectionError(f"Safety sensor connection failed: {e}")
    
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
                self.logger.info("Successfully connected to safety sensors via HTTP")
                return True
            else:
                self.logger.error(f"HTTP connection test failed: {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.error(f"HTTP connection failed: {e}")
            return False
    
    async def _connect_bacnet(self) -> bool:
        """Connect using BACnet protocol."""
        try:
            from bacpypes3.app import Application
            from bacpypes3.core import run
            
            # BACnet connection setup
            self.bacnet_client = Application()
            
            # This is a simplified example - actual implementation would depend on BACnet configuration
            self.connected = True
            self.logger.info("Successfully connected to safety sensors via BACnet")
            return True
            
        except ImportError:
            self.logger.error("bacpypes3 library not installed. Install with: pip install bacpypes3")
            return False
        except Exception as e:
            self.logger.error(f"BACnet connection failed: {e}")
            return False
    
    async def disconnect(self) -> bool:
        """Disconnect from safety sensor system."""
        try:
            if self.session:
                await self.session.aclose()
                self.session = None
            
            if self.bacnet_client:
                # Clean up BACnet connection
                self.bacnet_client = None
            
            self.connected = False
            self.logger.info("Disconnected from safety sensors")
            return True
        except Exception as e:
            self.logger.error(f"Error disconnecting from safety sensors: {e}")
            return False
    
    async def get_sensor_readings(self, sensor_id: Optional[str] = None,
                                equipment_id: Optional[str] = None,
                                start_time: Optional[datetime] = None,
                                end_time: Optional[datetime] = None) -> List[SensorReading]:
        """Retrieve safety sensor readings."""
        try:
            if not self.connected:
                raise IoTConnectionError("Not connected to safety sensors")
            
            if self.protocol == 'http':
                return await self._get_sensor_readings_http(sensor_id, equipment_id, start_time, end_time)
            elif self.protocol == 'bacnet':
                return await self._get_sensor_readings_bacnet(sensor_id, equipment_id)
            else:
                return []
                
        except Exception as e:
            self.logger.error(f"Failed to get safety sensor readings: {e}")
            raise IoTDataError(f"Safety sensor readings retrieval failed: {e}")
    
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
                sensor_type=SensorType(reading_data.get('sensor_type', 'smoke')),
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
    
    async def _get_sensor_readings_bacnet(self, sensor_id: Optional[str] = None,
                                        equipment_id: Optional[str] = None) -> List[SensorReading]:
        """Get sensor readings via BACnet."""
        readings = []
        
        try:
            # BACnet object reading - simplified example
            # Actual implementation would depend on BACnet device configuration
            
            # Simulate reading safety sensors
            safety_sensors = [
                {'type': 'smoke', 'value': 0.0, 'unit': 'ppm', 'location': 'warehouse'},
                {'type': 'gas', 'value': 0.0, 'unit': 'ppm', 'location': 'loading_dock'},
                {'type': 'temperature', 'value': 22.5, 'unit': '°C', 'location': 'office'},
                {'type': 'motion', 'value': 1.0, 'unit': 'detected', 'location': 'warehouse'}
            ]
            
            for sensor_data in safety_sensors:
                if sensor_id and sensor_data['type'] != sensor_id:
                    continue
                
                reading = SensorReading(
                    sensor_id=f"safety_{sensor_data['type']}_{sensor_data['location']}",
                    sensor_type=SensorType(sensor_data['type']),
                    value=sensor_data['value'],
                    unit=sensor_data['unit'],
                    timestamp=datetime.now(),
                    location=sensor_data['location'],
                    equipment_id=equipment_id,
                    quality=1.0,
                    metadata={'protocol': 'bacnet'}
                )
                readings.append(reading)
        
        except Exception as e:
            self.logger.error(f"Error reading BACnet objects: {e}")
        
        self._log_operation("get_sensor_readings_bacnet", {"count": len(readings)})
        return readings
    
    async def get_equipment_status(self, equipment_id: Optional[str] = None) -> List[Equipment]:
        """Retrieve safety equipment status."""
        try:
            if not self.connected:
                raise IoTConnectionError("Not connected to safety sensors")
            
            if self.protocol == 'http':
                return await self._get_equipment_status_http(equipment_id)
            else:
                # For BACnet, create equipment based on safety zones
                equipment_list = []
                for zone in self.safety_zones:
                    equipment = Equipment(
                        equipment_id=f"safety_{zone}",
                        name=f"Safety Monitor - {zone.title()}",
                        type="safety_monitor",
                        location=zone,
                        status=EquipmentStatus.ONLINE if self.connected else EquipmentStatus.OFFLINE,
                        last_seen=datetime.now(),
                        sensors=[f"smoke_{zone}", f"gas_{zone}", f"motion_{zone}"],
                        metadata={'zone': zone, 'safety_critical': True}
                    )
                    equipment_list.append(equipment)
                
                return equipment_list
                
        except Exception as e:
            self.logger.error(f"Failed to get safety equipment status: {e}")
            raise IoTDataError(f"Safety equipment status retrieval failed: {e}")
    
    async def _get_equipment_status_http(self, equipment_id: Optional[str] = None) -> List[Equipment]:
        """Get equipment status via HTTP API."""
        response = await self.session.get(self.endpoints['sensors'])
        response.raise_for_status()
        
        data = response.json()
        equipment_list = []
        
        for sensor_data in data.get('sensors', []):
            zone = sensor_data.get('zone', 'unknown')
            equipment_id = f"safety_{zone}"
            
            # Check if equipment already exists
            existing_equipment = next((e for e in equipment_list if e.equipment_id == equipment_id), None)
            
            if not existing_equipment:
                equipment = Equipment(
                    equipment_id=equipment_id,
                    name=f"Safety Monitor - {zone.title()}",
                    type="safety_monitor",
                    location=zone,
                    status=EquipmentStatus.ONLINE,
                    last_seen=datetime.now(),
                    sensors=[],
                    metadata={'zone': zone, 'safety_critical': True}
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
        """Retrieve safety alerts."""
        try:
            if not self.connected:
                raise IoTConnectionError("Not connected to safety sensors")
            
            if self.protocol == 'http':
                return await self._get_alerts_http(equipment_id, severity, resolved)
            else:
                # For BACnet, generate alerts based on current readings
                return await self._generate_safety_alerts_from_readings()
                
        except Exception as e:
            self.logger.error(f"Failed to get safety alerts: {e}")
            raise IoTDataError(f"Safety alerts retrieval failed: {e}")
    
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
    
    async def _generate_safety_alerts_from_readings(self) -> List[Alert]:
        """Generate safety alerts based on current sensor readings."""
        alerts = []
        
        # Get current readings
        readings = await self.get_sensor_readings()
        
        # Define safety thresholds
        safety_thresholds = {
            SensorType.SMOKE: {"high": 10, "critical_high": 50},  # ppm
            SensorType.GAS: {"high": 25, "critical_high": 100},   # ppm
            SensorType.TEMPERATURE: {"high": 40, "critical_high": 60},  # °C
            SensorType.MOTION: {"high": 1, "critical_high": 1}  # detected
        }
        
        for reading in readings:
            sensor_alerts = self._check_thresholds(reading, safety_thresholds)
            alerts.extend(sensor_alerts)
        
        return alerts
    
    async def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge a safety alert."""
        try:
            if not self.connected:
                raise IoTConnectionError("Not connected to safety sensors")
            
            if self.protocol == 'http':
                response = await self.session.post(f"{self.endpoints['alerts']}/{alert_id}/acknowledge")
                response.raise_for_status()
                return True
            else:
                # For BACnet, log acknowledgment
                self.logger.info(f"Acknowledged safety alert: {alert_id}")
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to acknowledge safety alert: {e}")
            raise IoTDataError(f"Safety alert acknowledgment failed: {e}")
    
    async def trigger_emergency_protocol(self, emergency_type: str, location: str) -> bool:
        """Trigger emergency protocol for safety incidents."""
        try:
            if not self.connected:
                raise IoTConnectionError("Not connected to safety sensors")
            
            emergency_data = {
                "emergency_type": emergency_type,
                "location": location,
                "timestamp": datetime.now().isoformat(),
                "contacts": self.emergency_contacts
            }
            
            if self.protocol == 'http':
                response = await self.session.post(self.endpoints['emergency'], json=emergency_data)
                response.raise_for_status()
                return True
            else:
                # For BACnet, log emergency
                self.logger.critical(f"EMERGENCY PROTOCOL TRIGGERED: {emergency_type} at {location}")
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to trigger emergency protocol: {e}")
            raise IoTDataError(f"Emergency protocol trigger failed: {e}")
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get safety sensor system status."""
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
                    "safety_zones": self.safety_zones,
                    "emergency_contacts": len(self.emergency_contacts),
                    "sensor_count": len(self._sensor_cache)
                }
            
        except Exception as e:
            self.logger.error(f"Failed to get safety system status: {e}")
            return {"status": "error", "connected": False, "error": str(e)}
    
    def _encode_basic_auth(self, username: str, password: str) -> str:
        """Encode basic authentication credentials."""
        import base64
        credentials = f"{username}:{password}"
        return base64.b64encode(credentials.encode()).decode()
