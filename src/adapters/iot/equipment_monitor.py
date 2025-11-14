"""
Equipment Monitor IoT Adapter.

Provides integration with equipment monitoring systems for
real-time tracking of warehouse equipment status and performance.
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

class EquipmentMonitorAdapter(BaseIoTAdapter):
    """
    Equipment Monitor Adapter for warehouse equipment tracking.
    
    Supports MQTT, HTTP REST API, and WebSocket connections for
    real-time equipment monitoring.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Equipment Monitor adapter.
        
        Args:
            config: Configuration containing:
                - host: Equipment monitor host
                - port: Equipment monitor port (default: 1883 for MQTT, 8080 for HTTP)
                - protocol: Connection protocol (mqtt, http, websocket)
                - username: Authentication username
                - password: Authentication password
                - client_id: MQTT client ID (for MQTT protocol)
                - topics: MQTT topics to subscribe to (for MQTT protocol)
                - api_key: API key for HTTP authentication
        """
        super().__init__(config)
        self.host = config.get('host')
        self.port = config.get('port', 1883)
        self.protocol = config.get('protocol', 'mqtt')
        self.username = config.get('username')
        self.password = config.get('password')
        self.client_id = config.get('client_id', 'warehouse_equipment_monitor')
        self.topics = config.get('topics', ['equipment/+/status', 'equipment/+/sensors'])
        self.api_key = config.get('api_key')
        
        self.session: Optional[httpx.AsyncClient] = None
        self.mqtt_client = None
        self.websocket = None
        self._monitoring = False
        self._monitoring_callback = None
        
        # Equipment monitoring endpoints
        if self.protocol == 'http':
            self.base_url = f"http://{self.host}:{self.port}/api/v1"
            self.endpoints = {
                'equipment': '/equipment',
                'sensors': '/sensors',
                'alerts': '/alerts',
                'status': '/status'
            }
    
    async def connect(self) -> bool:
        """Establish connection to equipment monitoring system."""
        try:
            if not self._validate_config(['host']):
                return False
            
            if self.protocol == 'mqtt':
                return await self._connect_mqtt()
            elif self.protocol == 'http':
                return await self._connect_http()
            elif self.protocol == 'websocket':
                return await self._connect_websocket()
            else:
                self.logger.error(f"Unsupported protocol: {self.protocol}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to connect to equipment monitor: {e}")
            raise IoTConnectionError(f"Equipment monitor connection failed: {e}")
    
    async def _connect_mqtt(self) -> bool:
        """Connect using MQTT protocol."""
        try:
            import paho.mqtt.client as mqtt
            
            self.mqtt_client = mqtt.Client(self.client_id)
            
            if self.username and self.password:
                self.mqtt_client.username_pw_set(self.username, self.password)
            
            # Set up callbacks
            self.mqtt_client.on_connect = self._on_mqtt_connect
            self.mqtt_client.on_message = self._on_mqtt_message
            self.mqtt_client.on_disconnect = self._on_mqtt_disconnect
            
            # Connect
            self.mqtt_client.connect(self.host, self.port, 60)
            self.mqtt_client.loop_start()
            
            # Wait for connection
            await asyncio.sleep(1)
            
            if self.mqtt_client.is_connected():
                self.connected = True
                self.logger.info("Successfully connected to equipment monitor via MQTT")
                return True
            else:
                self.logger.error("Failed to connect to MQTT broker")
                return False
                
        except ImportError:
            self.logger.error("paho-mqtt library not installed. Install with: pip install paho-mqtt")
            return False
        except Exception as e:
            self.logger.error(f"MQTT connection failed: {e}")
            return False
    
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
                self.logger.info("Successfully connected to equipment monitor via HTTP")
                return True
            else:
                self.logger.error(f"HTTP connection test failed: {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.error(f"HTTP connection failed: {e}")
            return False
    
    async def _connect_websocket(self) -> bool:
        """Connect using WebSocket protocol."""
        try:
            import websockets
            
            uri = f"ws://{self.host}:{self.port}/ws"
            self.websocket = await websockets.connect(uri)
            
            self.connected = True
            self.logger.info("Successfully connected to equipment monitor via WebSocket")
            return True
            
        except ImportError:
            self.logger.error("websockets library not installed. Install with: pip install websockets")
            return False
        except Exception as e:
            self.logger.error(f"WebSocket connection failed: {e}")
            return False
    
    async def disconnect(self) -> bool:
        """Disconnect from equipment monitoring system."""
        try:
            if self.mqtt_client:
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
                self.mqtt_client = None
            
            if self.session:
                await self.session.aclose()
                self.session = None
            
            if self.websocket:
                await self.websocket.close()
                self.websocket = None
            
            self.connected = False
            self.logger.info("Disconnected from equipment monitor")
            return True
        except Exception as e:
            self.logger.error(f"Error disconnecting from equipment monitor: {e}")
            return False
    
    async def get_sensor_readings(self, sensor_id: Optional[str] = None,
                                equipment_id: Optional[str] = None,
                                start_time: Optional[datetime] = None,
                                end_time: Optional[datetime] = None) -> List[SensorReading]:
        """Retrieve sensor readings from equipment monitor."""
        try:
            if not self.connected:
                raise IoTConnectionError("Not connected to equipment monitor")
            
            if self.protocol == 'http':
                return await self._get_sensor_readings_http(sensor_id, equipment_id, start_time, end_time)
            else:
                # For MQTT/WebSocket, return cached readings
                readings = list(self._sensor_cache.values())
                
                # Apply filters
                if sensor_id:
                    readings = [r for r in readings if r.sensor_id == sensor_id]
                if equipment_id:
                    readings = [r for r in readings if r.equipment_id == equipment_id]
                if start_time:
                    readings = [r for r in readings if r.timestamp >= start_time]
                if end_time:
                    readings = [r for r in readings if r.timestamp <= end_time]
                
                return readings
                
        except Exception as e:
            self.logger.error(f"Failed to get sensor readings: {e}")
            raise IoTDataError(f"Sensor readings retrieval failed: {e}")
    
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
        
        response = await self.session.get(self.endpoints['sensors'], params=params)
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
    
    async def get_equipment_status(self, equipment_id: Optional[str] = None) -> List[Equipment]:
        """Retrieve equipment status from equipment monitor."""
        try:
            if not self.connected:
                raise IoTConnectionError("Not connected to equipment monitor")
            
            if self.protocol == 'http':
                return await self._get_equipment_status_http(equipment_id)
            else:
                # For MQTT/WebSocket, return cached equipment
                equipment_list = list(self._equipment_cache.values())
                
                if equipment_id:
                    equipment_list = [e for e in equipment_list if e.equipment_id == equipment_id]
                
                return equipment_list
                
        except Exception as e:
            self.logger.error(f"Failed to get equipment status: {e}")
            raise IoTDataError(f"Equipment status retrieval failed: {e}")
    
    async def _get_equipment_status_http(self, equipment_id: Optional[str] = None) -> List[Equipment]:
        """Get equipment status via HTTP API."""
        url = self.endpoints['equipment']
        if equipment_id:
            url = f"{url}/{equipment_id}"
        
        response = await self.session.get(url)
        response.raise_for_status()
        
        data = response.json()
        equipment_list = []
        
        equipment_data_list = data.get('equipment', []) if isinstance(data, dict) else [data]
        
        for equipment_data in equipment_data_list:
            equipment = Equipment(
                equipment_id=equipment_data.get('equipment_id', ''),
                name=equipment_data.get('name', ''),
                type=equipment_data.get('type', ''),
                location=equipment_data.get('location', ''),
                status=EquipmentStatus(equipment_data.get('status', 'offline')),
                last_seen=datetime.fromisoformat(equipment_data.get('last_seen', datetime.now().isoformat())) if equipment_data.get('last_seen') else None,
                sensors=equipment_data.get('sensors', []),
                metadata=equipment_data.get('metadata')
            )
            equipment_list.append(equipment)
        
        self._log_operation("get_equipment_status", {"count": len(equipment_list)})
        return equipment_list
    
    async def get_alerts(self, equipment_id: Optional[str] = None,
                        severity: Optional[str] = None,
                        resolved: Optional[bool] = None) -> List[Alert]:
        """Retrieve alerts from equipment monitor."""
        try:
            if not self.connected:
                raise IoTConnectionError("Not connected to equipment monitor")
            
            if self.protocol == 'http':
                return await self._get_alerts_http(equipment_id, severity, resolved)
            else:
                # For MQTT/WebSocket, return cached alerts
                alerts = []
                # This would be populated by real-time monitoring
                return alerts
                
        except Exception as e:
            self.logger.error(f"Failed to get alerts: {e}")
            raise IoTDataError(f"Alerts retrieval failed: {e}")
    
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
    
    async def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        try:
            if not self.connected:
                raise IoTConnectionError("Not connected to equipment monitor")
            
            if self.protocol == 'http':
                response = await self.session.post(f"{self.endpoints['alerts']}/{alert_id}/acknowledge")
                response.raise_for_status()
                return True
            else:
                # For MQTT/WebSocket, publish acknowledgment
                if self.mqtt_client:
                    topic = f"alerts/{alert_id}/acknowledge"
                    self.mqtt_client.publish(topic, json.dumps({"acknowledged": True}))
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to acknowledge alert: {e}")
            raise IoTDataError(f"Alert acknowledgment failed: {e}")
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get equipment monitor system status."""
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
                    "equipment_count": len(self._equipment_cache),
                    "sensor_count": len(self._sensor_cache)
                }
            
        except Exception as e:
            self.logger.error(f"Failed to get system status: {e}")
            return {"status": "error", "connected": False, "error": str(e)}
    
    async def start_real_time_monitoring(self, callback: callable) -> bool:
        """Start real-time monitoring with callback."""
        try:
            if not self.connected:
                raise IoTConnectionError("Not connected to equipment monitor")
            
            self._monitoring_callback = callback
            self._monitoring = True
            
            if self.protocol == 'mqtt':
                # Subscribe to topics
                for topic in self.topics:
                    self.mqtt_client.subscribe(topic)
                self.logger.info("Started real-time monitoring via MQTT")
            elif self.protocol == 'websocket':
                # Start WebSocket monitoring loop
                asyncio.create_task(self._websocket_monitoring_loop())
                self.logger.info("Started real-time monitoring via WebSocket")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start real-time monitoring: {e}")
            return False
    
    async def stop_real_time_monitoring(self) -> bool:
        """Stop real-time monitoring."""
        try:
            self._monitoring = False
            self._monitoring_callback = None
            
            if self.protocol == 'mqtt':
                # Unsubscribe from topics
                for topic in self.topics:
                    self.mqtt_client.unsubscribe(topic)
            
            self.logger.info("Stopped real-time monitoring")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to stop real-time monitoring: {e}")
            return False
    
    def _on_mqtt_connect(self, client, userdata, flags, rc):
        """MQTT connection callback."""
        if rc == 0:
            self.logger.info("Connected to MQTT broker")
            self.connected = True
        else:
            self.logger.error(f"Failed to connect to MQTT broker: {rc}")
    
    def _on_mqtt_message(self, client, userdata, msg):
        """MQTT message callback."""
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode())
            
            # Process different message types
            if 'equipment' in topic and 'status' in topic:
                self._process_equipment_status_message(topic, payload)
            elif 'equipment' in topic and 'sensors' in topic:
                self._process_sensor_reading_message(topic, payload)
            
            # Call monitoring callback if set
            if self._monitoring_callback:
                asyncio.create_task(self._monitoring_callback(topic, payload))
                
        except Exception as e:
            self.logger.error(f"Error processing MQTT message: {e}")
    
    def _on_mqtt_disconnect(self, client, userdata, rc):
        """MQTT disconnection callback."""
        self.logger.info("Disconnected from MQTT broker")
        self.connected = False
    
    def _process_equipment_status_message(self, topic: str, payload: Dict[str, Any]):
        """Process equipment status message."""
        equipment_id = topic.split('/')[1]  # Extract equipment ID from topic
        
        equipment = Equipment(
            equipment_id=equipment_id,
            name=payload.get('name', equipment_id),
            type=payload.get('type', 'unknown'),
            location=payload.get('location', 'unknown'),
            status=EquipmentStatus(payload.get('status', 'offline')),
            last_seen=datetime.now(),
            sensors=payload.get('sensors', []),
            metadata=payload.get('metadata')
        )
        
        self._equipment_cache[equipment_id] = equipment
    
    def _process_sensor_reading_message(self, topic: str, payload: Dict[str, Any]):
        """Process sensor reading message."""
        equipment_id = topic.split('/')[1]  # Extract equipment ID from topic
        
        for sensor_data in payload.get('sensors', []):
            reading = SensorReading(
                sensor_id=sensor_data.get('sensor_id', ''),
                sensor_type=SensorType(sensor_data.get('sensor_type', 'temperature')),
                value=float(sensor_data.get('value', 0)),
                unit=sensor_data.get('unit', ''),
                timestamp=datetime.fromisoformat(sensor_data.get('timestamp', datetime.now().isoformat())),
                location=sensor_data.get('location'),
                equipment_id=equipment_id,
                quality=float(sensor_data.get('quality', 1.0)),
                metadata=sensor_data.get('metadata')
            )
            
            self._sensor_cache[reading.sensor_id] = reading
    
    async def _websocket_monitoring_loop(self):
        """WebSocket monitoring loop."""
        try:
            while self._monitoring and self.websocket:
                message = await self.websocket.recv()
                data = json.loads(message)
                
                # Process message
                if self._monitoring_callback:
                    await self._monitoring_callback("websocket", data)
                    
        except Exception as e:
            self.logger.error(f"WebSocket monitoring loop error: {e}")
    
    def _encode_basic_auth(self, username: str, password: str) -> str:
        """Encode basic authentication credentials."""
        import base64
        credentials = f"{username}:{password}"
        return base64.b64encode(credentials.encode()).decode()
