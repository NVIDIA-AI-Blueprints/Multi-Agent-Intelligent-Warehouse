"""
Asset Tracking IoT Adapter.

Provides integration with asset tracking systems for
RFID, Bluetooth, GPS, and other asset location technologies.
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

class AssetTrackingAdapter(BaseIoTAdapter):
    """
    Asset Tracking Adapter for warehouse asset monitoring.
    
    Tracks assets using RFID, Bluetooth, GPS, and other location technologies
    for real-time asset visibility and management.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Asset Tracking adapter.
        
        Args:
            config: Configuration containing:
                - host: Asset tracking system host
                - port: Port (default: 8080)
                - protocol: Connection protocol (http, mqtt, websocket)
                - username: Authentication username
                - password: Authentication password
                - api_key: API key for HTTP authentication
                - tracking_zones: List of tracking zones
                - asset_types: List of asset types to track
        """
        super().__init__(config)
        self.host = config.get('host')
        self.port = config.get('port', 8080)
        self.protocol = config.get('protocol', 'http')
        self.username = config.get('username')
        self.password = config.get('password')
        self.api_key = config.get('api_key')
        self.tracking_zones = config.get('tracking_zones', ['warehouse', 'loading_dock', 'office', 'maintenance'])
        self.asset_types = config.get('asset_types', ['forklift', 'pallet', 'container', 'tool', 'equipment'])
        
        self.session: Optional[httpx.AsyncClient] = None
        self.websocket = None
        
        # Asset tracking endpoints
        if self.protocol == 'http':
            self.base_url = f"http://{self.host}:{self.port}/api/v1"
            self.endpoints = {
                'assets': '/assets',
                'locations': '/locations',
                'readings': '/tracking/readings',
                'alerts': '/tracking/alerts',
                'status': '/tracking/status'
            }
    
    async def connect(self) -> bool:
        """Establish connection to asset tracking system."""
        try:
            if not self._validate_config(['host']):
                return False
            
            if self.protocol == 'http':
                return await self._connect_http()
            elif self.protocol == 'websocket':
                return await self._connect_websocket()
            else:
                self.logger.error(f"Unsupported protocol: {self.protocol}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to connect to asset tracking system: {e}")
            raise IoTConnectionError(f"Asset tracking connection failed: {e}")
    
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
                self.logger.info("Successfully connected to asset tracking system via HTTP")
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
            
            uri = f"ws://{self.host}:{self.port}/ws/tracking"
            self.websocket = await websockets.connect(uri)
            
            self.connected = True
            self.logger.info("Successfully connected to asset tracking system via WebSocket")
            return True
            
        except ImportError:
            self.logger.error("websockets library not installed. Install with: pip install websockets")
            return False
        except Exception as e:
            self.logger.error(f"WebSocket connection failed: {e}")
            return False
    
    async def disconnect(self) -> bool:
        """Disconnect from asset tracking system."""
        try:
            if self.session:
                await self.session.aclose()
                self.session = None
            
            if self.websocket:
                await self.websocket.close()
                self.websocket = None
            
            self.connected = False
            self.logger.info("Disconnected from asset tracking system")
            return True
        except Exception as e:
            self.logger.error(f"Error disconnecting from asset tracking system: {e}")
            return False
    
    async def get_sensor_readings(self, sensor_id: Optional[str] = None,
                                equipment_id: Optional[str] = None,
                                start_time: Optional[datetime] = None,
                                end_time: Optional[datetime] = None) -> List[SensorReading]:
        """Retrieve asset tracking sensor readings."""
        try:
            if not self.connected:
                raise IoTConnectionError("Not connected to asset tracking system")
            
            if self.protocol == 'http':
                return await self._get_sensor_readings_http(sensor_id, equipment_id, start_time, end_time)
            else:
                # For WebSocket, return cached readings
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
            self.logger.error(f"Failed to get asset tracking readings: {e}")
            raise IoTDataError(f"Asset tracking readings retrieval failed: {e}")
    
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
                sensor_type=SensorType(reading_data.get('sensor_type', 'gps')),
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
        """Retrieve tracked asset status."""
        try:
            if not self.connected:
                raise IoTConnectionError("Not connected to asset tracking system")
            
            if self.protocol == 'http':
                return await self._get_equipment_status_http(equipment_id)
            else:
                # For WebSocket, return cached equipment
                equipment_list = list(self._equipment_cache.values())
                
                if equipment_id:
                    equipment_list = [e for e in equipment_list if e.equipment_id == equipment_id]
                
                return equipment_list
                
        except Exception as e:
            self.logger.error(f"Failed to get asset tracking status: {e}")
            raise IoTDataError(f"Asset tracking status retrieval failed: {e}")
    
    async def _get_equipment_status_http(self, equipment_id: Optional[str] = None) -> List[Equipment]:
        """Get equipment status via HTTP API."""
        url = self.endpoints['assets']
        if equipment_id:
            url = f"{url}/{equipment_id}"
        
        response = await self.session.get(url)
        response.raise_for_status()
        
        data = response.json()
        equipment_list = []
        
        assets_data = data.get('assets', []) if isinstance(data, dict) else [data]
        
        for asset_data in assets_data:
            equipment = Equipment(
                equipment_id=asset_data.get('asset_id', ''),
                name=asset_data.get('name', ''),
                type=asset_data.get('type', ''),
                location=asset_data.get('location', ''),
                status=EquipmentStatus.ONLINE if asset_data.get('online', False) else EquipmentStatus.OFFLINE,
                last_seen=datetime.fromisoformat(asset_data.get('last_seen', datetime.now().isoformat())) if asset_data.get('last_seen') else None,
                sensors=asset_data.get('sensors', []),
                metadata=asset_data.get('metadata')
            )
            equipment_list.append(equipment)
        
        self._log_operation("get_equipment_status", {"count": len(equipment_list)})
        return equipment_list
    
    async def get_alerts(self, equipment_id: Optional[str] = None,
                        severity: Optional[str] = None,
                        resolved: Optional[bool] = None) -> List[Alert]:
        """Retrieve asset tracking alerts."""
        try:
            if not self.connected:
                raise IoTConnectionError("Not connected to asset tracking system")
            
            if self.protocol == 'http':
                return await self._get_alerts_http(equipment_id, severity, resolved)
            else:
                # For WebSocket, return cached alerts
                alerts = []
                # This would be populated by real-time monitoring
                return alerts
                
        except Exception as e:
            self.logger.error(f"Failed to get asset tracking alerts: {e}")
            raise IoTDataError(f"Asset tracking alerts retrieval failed: {e}")
    
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
        """Acknowledge an asset tracking alert.
        
        Args:
            alert_id: ID of the alert to acknowledge
            
        Returns:
            True if acknowledgment was successful, False otherwise
            
        Raises:
            IoTConnectionError: If not connected to the system
            IoTDataError: If acknowledgment fails
        """
        try:
            if not self.connected:
                raise IoTConnectionError("Not connected to asset tracking system")
            
            if self.protocol == 'http':
                response = await self.session.post(f"{self.endpoints['alerts']}/{alert_id}/acknowledge")
                response.raise_for_status()
                # Check response content to verify acknowledgment
                response_data = response.json() if response.content else {}
                acknowledged = response_data.get('acknowledged', False)
                if acknowledged:
                    self.logger.info(f"Successfully acknowledged alert {alert_id}")
                    return True
                else:
                    self.logger.warning(f"Alert {alert_id} acknowledgment request completed but not confirmed")
                    return False
            else:
                # For WebSocket, send acknowledgment
                if not self.websocket:
                    self.logger.error("WebSocket connection not available for acknowledgment")
                    return False
                
                ack_message = {"type": "acknowledge_alert", "alert_id": alert_id}
                await self.websocket.send(json.dumps(ack_message))
                self.logger.info(f"Sent acknowledgment request for alert {alert_id} via WebSocket")
                # For WebSocket, we assume success if message was sent
                # In a real implementation, you might wait for a confirmation message
                return True
                
        except httpx.HTTPStatusError as e:
            self.logger.error(f"HTTP error acknowledging alert {alert_id}: {e.response.status_code}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to acknowledge asset tracking alert {alert_id}: {e}")
            raise IoTDataError(f"Asset tracking alert acknowledgment failed: {e}")
    
    async def get_asset_location_history(self, asset_id: str, 
                                       start_time: Optional[datetime] = None,
                                       end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get location history for a specific asset."""
        try:
            if not self.connected:
                raise IoTConnectionError("Not connected to asset tracking system")
            
            if self.protocol == 'http':
                params = {}
                if start_time:
                    params['start_time'] = start_time.isoformat()
                if end_time:
                    params['end_time'] = end_time.isoformat()
                
                response = await self.session.get(f"{self.endpoints['assets']}/{asset_id}/history", params=params)
                response.raise_for_status()
                
                data = response.json()
                return data.get('history', [])
            else:
                # For WebSocket, return cached history
                return []
                
        except Exception as e:
            self.logger.error(f"Failed to get asset location history: {e}")
            raise IoTDataError(f"Asset location history retrieval failed: {e}")
    
    async def get_assets_in_zone(self, zone: str) -> List[Dict[str, Any]]:
        """Get all assets currently in a specific zone."""
        try:
            if not self.connected:
                raise IoTConnectionError("Not connected to asset tracking system")
            
            if self.protocol == 'http':
                response = await self.session.get(f"{self.endpoints['locations']}/{zone}/assets")
                response.raise_for_status()
                
                data = response.json()
                return data.get('assets', [])
            else:
                # For WebSocket, return cached assets in zone
                assets = []
                for equipment in self._equipment_cache.values():
                    if equipment.location == zone:
                        assets.append({
                            'asset_id': equipment.equipment_id,
                            'name': equipment.name,
                            'type': equipment.type,
                            'location': equipment.location,
                            'last_seen': equipment.last_seen.isoformat() if equipment.last_seen else None
                        })
                return assets
                
        except Exception as e:
            self.logger.error(f"Failed to get assets in zone: {e}")
            raise IoTDataError(f"Assets in zone retrieval failed: {e}")
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get asset tracking system status."""
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
                    "tracking_zones": self.tracking_zones,
                    "asset_types": self.asset_types,
                    "equipment_count": len(self._equipment_cache),
                    "sensor_count": len(self._sensor_cache)
                }
            
        except Exception as e:
            self.logger.error(f"Failed to get asset tracking system status: {e}")
            return {"status": "error", "connected": False, "error": str(e)}
    
    async def start_real_time_monitoring(self, callback: callable) -> bool:
        """Start real-time asset tracking monitoring."""
        try:
            if not self.connected:
                raise IoTConnectionError("Not connected to asset tracking system")
            
            self._monitoring_callback = callback
            self._monitoring = True
            
            if self.protocol == 'websocket':
                # Start WebSocket monitoring loop
                asyncio.create_task(self._websocket_monitoring_loop())
                self.logger.info("Started real-time asset tracking monitoring via WebSocket")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start real-time asset tracking monitoring: {e}")
            return False
    
    async def stop_real_time_monitoring(self) -> bool:
        """Stop real-time asset tracking monitoring."""
        try:
            self._monitoring = False
            self._monitoring_callback = None
            
            self.logger.info("Stopped real-time asset tracking monitoring")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to stop real-time asset tracking monitoring: {e}")
            return False
    
    async def _websocket_monitoring_loop(self):
        """WebSocket monitoring loop for asset tracking."""
        try:
            while self._monitoring and self.websocket:
                message = await self.websocket.recv()
                data = json.loads(message)
                
                # Process different message types
                if data.get('type') == 'asset_location':
                    self._process_asset_location_message(data)
                elif data.get('type') == 'asset_alert':
                    self._process_asset_alert_message(data)
                
                # Call monitoring callback if set
                if self._monitoring_callback:
                    await self._monitoring_callback("asset_tracking", data)
                    
        except Exception as e:
            self.logger.error(f"WebSocket asset tracking monitoring loop error: {e}")
    
    def _process_asset_location_message(self, data: Dict[str, Any]):
        """Process asset location message."""
        asset_id = data.get('asset_id')
        location = data.get('location')
        
        if asset_id in self._equipment_cache:
            equipment = self._equipment_cache[asset_id]
            equipment.location = location
            equipment.last_seen = datetime.now()
            equipment.status = EquipmentStatus.ONLINE
    
    def _process_asset_alert_message(self, data: Dict[str, Any]):
        """Process asset alert message."""
        # Process asset alerts
        pass
    
    def _encode_basic_auth(self, username: str, password: str) -> str:
        """Encode basic authentication credentials."""
        import base64
        credentials = f"{username}:{password}"
        return base64.b64encode(credentials.encode()).decode()
