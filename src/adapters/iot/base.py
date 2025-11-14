"""
Base IoT Adapter - Common interface and functionality for all IoT adapters.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from datetime import datetime
import logging
from enum import Enum

logger = logging.getLogger(__name__)

class IoTConnectionError(Exception):
    """Raised when IoT connection fails."""
    pass

class IoTDataError(Exception):
    """Raised when IoT data processing fails."""
    pass

class SensorType(Enum):
    """Sensor type enumeration."""
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    PRESSURE = "pressure"
    VIBRATION = "vibration"
    VOLTAGE = "voltage"
    CURRENT = "current"
    POWER = "power"
    MOTION = "motion"
    PROXIMITY = "proximity"
    LIGHT = "light"
    SOUND = "sound"
    GAS = "gas"
    SMOKE = "smoke"
    GPS = "gps"
    RFID = "rfid"
    BLUETOOTH = "bluetooth"
    WIFI = "wifi"

class EquipmentStatus(Enum):
    """Equipment status enumeration."""
    ONLINE = "online"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"
    ERROR = "error"
    WARNING = "warning"
    CRITICAL = "critical"

@dataclass
class SensorReading:
    """Sensor reading data structure."""
    sensor_id: str
    sensor_type: SensorType
    value: float
    unit: str
    timestamp: datetime
    location: Optional[str] = None
    equipment_id: Optional[str] = None
    quality: float = 1.0  # Data quality score (0-1)
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class Equipment:
    """Equipment data structure."""
    equipment_id: str
    name: str
    type: str
    location: str
    status: EquipmentStatus = EquipmentStatus.OFFLINE
    last_seen: Optional[datetime] = None
    sensors: List[str] = None  # List of sensor IDs
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class Alert:
    """Alert data structure."""
    alert_id: str
    equipment_id: str
    sensor_id: Optional[str] = None
    alert_type: str = "threshold"
    severity: str = "warning"
    message: str = ""
    value: Optional[float] = None
    threshold: Optional[float] = None
    timestamp: datetime = None
    acknowledged: bool = False
    resolved: bool = False

class BaseIoTAdapter(ABC):
    """
    Base class for all IoT adapters.
    
    Provides common interface and functionality for integrating with
    IoT sensors and equipment monitoring systems.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the IoT adapter.
        
        Args:
            config: Configuration dictionary containing connection details
        """
        self.config = config
        self.connected = False
        self.logger = logging.getLogger(f"{self.__class__.__module__}.{self.__class__.__name__}")
        self._equipment_cache: Dict[str, Equipment] = {}
        self._sensor_cache: Dict[str, SensorReading] = {}
    
    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish connection to the IoT system.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> bool:
        """
        Disconnect from the IoT system.
        
        Returns:
            bool: True if disconnection successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def get_sensor_readings(self, sensor_id: Optional[str] = None,
                                equipment_id: Optional[str] = None,
                                start_time: Optional[datetime] = None,
                                end_time: Optional[datetime] = None) -> List[SensorReading]:
        """
        Retrieve sensor readings.
        
        Args:
            sensor_id: Optional specific sensor filter
            equipment_id: Optional equipment filter
            start_time: Optional start time filter
            end_time: Optional end time filter
            
        Returns:
            List[SensorReading]: List of sensor readings
        """
        pass
    
    @abstractmethod
    async def get_equipment_status(self, equipment_id: Optional[str] = None) -> List[Equipment]:
        """
        Retrieve equipment status information.
        
        Args:
            equipment_id: Optional specific equipment filter
            
        Returns:
            List[Equipment]: List of equipment
        """
        pass
    
    @abstractmethod
    async def get_alerts(self, equipment_id: Optional[str] = None,
                        severity: Optional[str] = None,
                        resolved: Optional[bool] = None) -> List[Alert]:
        """
        Retrieve alerts from the IoT system.
        
        Args:
            equipment_id: Optional equipment filter
            severity: Optional severity filter
            resolved: Optional resolved status filter
            
        Returns:
            List[Alert]: List of alerts
        """
        pass
    
    @abstractmethod
    async def acknowledge_alert(self, alert_id: str) -> bool:
        """
        Acknowledge an alert.
        
        Args:
            alert_id: ID of alert to acknowledge
            
        Returns:
            bool: True if acknowledgment successful
        """
        pass
    
    @abstractmethod
    async def get_system_status(self) -> Dict[str, Any]:
        """
        Get IoT system status and health information.
        
        Returns:
            Dict[str, Any]: System status information
        """
        pass
    
    async def start_real_time_monitoring(self, callback: callable) -> bool:
        """
        Start real-time monitoring with callback.
        
        Args:
            callback: Function to call when new data is received
            
        Returns:
            bool: True if monitoring started successfully
        """
        # Default implementation - override in subclasses
        self.logger.warning("Real-time monitoring not implemented in base class")
        return False
    
    async def stop_real_time_monitoring(self) -> bool:
        """
        Stop real-time monitoring.
        
        Returns:
            bool: True if monitoring stopped successfully
        """
        # Default implementation - override in subclasses
        self.logger.warning("Real-time monitoring not implemented in base class")
        return False
    
    def _validate_config(self, required_fields: List[str]) -> bool:
        """
        Validate configuration has required fields.
        
        Args:
            required_fields: List of required configuration fields
            
        Returns:
            bool: True if valid, False otherwise
        """
        missing_fields = [field for field in required_fields if field not in self.config]
        if missing_fields:
            self.logger.error(f"Missing required configuration fields: {missing_fields}")
            return False
        return True
    
    def _log_operation(self, operation: str, details: Optional[Dict[str, Any]] = None):
        """
        Log IoT operation for audit purposes.
        
        Args:
            operation: Operation name
            details: Optional operation details
        """
        log_data = {
            "adapter": self.__class__.__name__,
            "operation": operation,
            "timestamp": datetime.now().isoformat()
        }
        if details:
            log_data.update(details)
        
        self.logger.info(f"IoT Operation: {operation}", extra=log_data)
    
    def _check_thresholds(self, reading: SensorReading, thresholds: Dict[str, float]) -> List[Alert]:
        """
        Check sensor reading against thresholds and generate alerts.
        
        Args:
            reading: Sensor reading to check
            thresholds: Threshold configuration
            
        Returns:
            List[Alert]: Generated alerts
        """
        alerts = []
        
        if reading.sensor_type.value in thresholds:
            threshold_config = thresholds[reading.sensor_type.value]
            value = reading.value
            
            # Check high threshold
            if "high" in threshold_config and value > threshold_config["high"]:
                alert = Alert(
                    alert_id=f"{reading.sensor_id}_{reading.timestamp.isoformat()}_high",
                    equipment_id=reading.equipment_id or "unknown",
                    sensor_id=reading.sensor_id,
                    alert_type="threshold_high",
                    severity="warning" if value < threshold_config.get("critical_high", float('inf')) else "critical",
                    message=f"{reading.sensor_type.value} is above threshold: {value} {reading.unit} > {threshold_config['high']} {reading.unit}",
                    value=value,
                    threshold=threshold_config["high"],
                    timestamp=reading.timestamp
                )
                alerts.append(alert)
            
            # Check low threshold
            if "low" in threshold_config and value < threshold_config["low"]:
                alert = Alert(
                    alert_id=f"{reading.sensor_id}_{reading.timestamp.isoformat()}_low",
                    equipment_id=reading.equipment_id or "unknown",
                    sensor_id=reading.sensor_id,
                    alert_type="threshold_low",
                    severity="warning" if value > threshold_config.get("critical_low", float('-inf')) else "critical",
                    message=f"{reading.sensor_type.value} is below threshold: {value} {reading.unit} < {threshold_config['low']} {reading.unit}",
                    value=value,
                    threshold=threshold_config["low"],
                    timestamp=reading.timestamp
                )
                alerts.append(alert)
        
        return alerts
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on the IoT connection.
        
        Returns:
            Dict[str, Any]: Health check results
        """
        try:
            status = await self.get_system_status()
            return {
                "status": "healthy" if self.connected else "disconnected",
                "connected": self.connected,
                "system_status": status,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "connected": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
