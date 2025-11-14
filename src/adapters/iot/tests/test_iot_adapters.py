"""
Tests for IoT adapters.
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from src.adapters.iot.base import (
    BaseIoTAdapter, SensorReading, Equipment, Alert,
    SensorType, EquipmentStatus, IoTConnectionError, IoTDataError
)
from src.adapters.iot.equipment_monitor import EquipmentMonitorAdapter
from src.adapters.iot.environmental import EnvironmentalSensorAdapter
from src.adapters.iot.safety_sensors import SafetySensorAdapter
from src.adapters.iot.asset_tracking import AssetTrackingAdapter
from src.adapters.iot.factory import IoTAdapterFactory
from src.api.services.iot.integration_service import IoTIntegrationService

class TestBaseIoTAdapter:
    """Test base IoT adapter functionality."""
    
    def test_base_adapter_initialization(self):
        """Test base adapter initialization."""
        config = {"test": "value"}
        adapter = BaseIoTAdapter(config)
        
        assert adapter.config == config
        assert adapter.connected == False
        assert adapter.logger is not None
        assert adapter._equipment_cache == {}
        assert adapter._sensor_cache == {}
    
    def test_validate_config_success(self):
        """Test successful config validation."""
        config = {"required_field": "value", "optional_field": "value"}
        adapter = BaseIoTAdapter(config)
        
        result = adapter._validate_config(["required_field"])
        assert result == True
    
    def test_validate_config_failure(self):
        """Test failed config validation."""
        config = {"optional_field": "value"}
        adapter = BaseIoTAdapter(config)
        
        result = adapter._validate_config(["required_field"])
        assert result == False
    
    def test_log_operation(self):
        """Test operation logging."""
        config = {"test": "value"}
        adapter = BaseIoTAdapter(config)
        
        # Should not raise any exceptions
        adapter._log_operation("test_operation", {"key": "value"})
    
    def test_check_thresholds(self):
        """Test threshold checking."""
        config = {"test": "value"}
        adapter = BaseIoTAdapter(config)
        
        reading = SensorReading(
            sensor_id="test_sensor",
            sensor_type=SensorType.TEMPERATURE,
            value=25.0,
            unit="°C",
            timestamp=datetime.now()
        )
        
        thresholds = {
            SensorType.TEMPERATURE: {"high": 30, "low": 20}
        }
        
        alerts = adapter._check_thresholds(reading, thresholds)
        assert len(alerts) == 0  # Value is within thresholds
        
        # Test high threshold
        reading.value = 35.0
        alerts = adapter._check_thresholds(reading, thresholds)
        assert len(alerts) == 1
        assert alerts[0].alert_type == "threshold_high"
        assert alerts[0].severity == "warning"
        
        # Test low threshold
        reading.value = 15.0
        alerts = adapter._check_thresholds(reading, thresholds)
        assert len(alerts) == 1
        assert alerts[0].alert_type == "threshold_low"
        assert alerts[0].severity == "warning"

class TestEquipmentMonitorAdapter:
    """Test Equipment Monitor adapter."""
    
    @pytest.fixture
    def equipment_config(self):
        return {
            "host": "test-equipment.com",
            "protocol": "http",
            "username": "test_user",
            "password": "test_password"
        }
    
    @pytest.fixture
    def equipment_adapter(self, equipment_config):
        return EquipmentMonitorAdapter(equipment_config)
    
    def test_equipment_adapter_initialization(self, equipment_config):
        """Test equipment adapter initialization."""
        adapter = EquipmentMonitorAdapter(equipment_config)
        
        assert adapter.host == "test-equipment.com"
        assert adapter.protocol == "http"
        assert adapter.username == "test_user"
        assert adapter.port == 1883  # Default port
    
    @pytest.mark.asyncio
    async def test_equipment_adapter_connect_http(self, equipment_adapter):
        """Test equipment adapter HTTP connection."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_client.return_value.get.return_value = mock_response
            
            result = await equipment_adapter._connect_http()
            assert result == True
            assert equipment_adapter.connected == True
    
    def test_equipment_adapter_mqtt_config(self):
        """Test equipment adapter MQTT configuration."""
        config = {
            "host": "mqtt-broker.com",
            "protocol": "mqtt",
            "client_id": "test_client",
            "topics": ["equipment/+/status"]
        }
        
        adapter = EquipmentMonitorAdapter(config)
        assert adapter.protocol == "mqtt"
        assert adapter.client_id == "test_client"
        assert adapter.topics == ["equipment/+/status"]

class TestEnvironmentalAdapter:
    """Test Environmental Sensor adapter."""
    
    @pytest.fixture
    def environmental_config(self):
        return {
            "host": "test-environmental.com",
            "protocol": "http",
            "username": "env_user",
            "password": "env_password",
            "zones": ["warehouse", "office"]
        }
    
    @pytest.fixture
    def environmental_adapter(self, environmental_config):
        return EnvironmentalSensorAdapter(environmental_config)
    
    def test_environmental_adapter_initialization(self, environmental_config):
        """Test environmental adapter initialization."""
        adapter = EnvironmentalSensorAdapter(environmental_config)
        
        assert adapter.host == "test-environmental.com"
        assert adapter.protocol == "http"
        assert adapter.zones == ["warehouse", "office"]
    
    @pytest.mark.asyncio
    async def test_environmental_adapter_connect_http(self, environmental_adapter):
        """Test environmental adapter HTTP connection."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_client.return_value.get.return_value = mock_response
            
            result = await environmental_adapter._connect_http()
            assert result == True
            assert environmental_adapter.connected == True
    
    def test_environmental_adapter_modbus_config(self):
        """Test environmental adapter Modbus configuration."""
        config = {
            "host": "modbus-server.com",
            "protocol": "modbus",
            "modbus_config": {
                "timeout": 10,
                "register_map": {
                    "temperature": {
                        "address": 100,
                        "scale": 0.1,
                        "unit": "°C"
                    }
                }
            }
        }
        
        adapter = EnvironmentalSensorAdapter(config)
        assert adapter.protocol == "modbus"
        assert adapter.modbus_config["timeout"] == 10

class TestSafetySensorAdapter:
    """Test Safety Sensor adapter."""
    
    @pytest.fixture
    def safety_config(self):
        return {
            "host": "test-safety.com",
            "protocol": "http",
            "username": "safety_user",
            "password": "safety_password",
            "emergency_contacts": [
                {"name": "Emergency Team", "phone": "+1-555-911"}
            ],
            "safety_zones": ["warehouse", "loading_dock"]
        }
    
    @pytest.fixture
    def safety_adapter(self, safety_config):
        return SafetySensorAdapter(safety_config)
    
    def test_safety_adapter_initialization(self, safety_config):
        """Test safety adapter initialization."""
        adapter = SafetySensorAdapter(safety_config)
        
        assert adapter.host == "test-safety.com"
        assert adapter.protocol == "http"
        assert len(adapter.emergency_contacts) == 1
        assert adapter.safety_zones == ["warehouse", "loading_dock"]
    
    @pytest.mark.asyncio
    async def test_safety_adapter_connect_http(self, safety_adapter):
        """Test safety adapter HTTP connection."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_client.return_value.get.return_value = mock_response
            
            result = await safety_adapter._connect_http()
            assert result == True
            assert safety_adapter.connected == True
    
    @pytest.mark.asyncio
    async def test_safety_adapter_trigger_emergency(self, safety_adapter):
        """Test safety adapter emergency protocol."""
        safety_adapter.connected = True
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_client.return_value.post.return_value = mock_response
            
            result = await safety_adapter.trigger_emergency_protocol("fire", "warehouse")
            assert result == True

class TestAssetTrackingAdapter:
    """Test Asset Tracking adapter."""
    
    @pytest.fixture
    def asset_config(self):
        return {
            "host": "test-asset-tracking.com",
            "protocol": "http",
            "username": "tracking_user",
            "password": "tracking_password",
            "tracking_zones": ["warehouse", "loading_dock"],
            "asset_types": ["forklift", "pallet"]
        }
    
    @pytest.fixture
    def asset_adapter(self, asset_config):
        return AssetTrackingAdapter(asset_config)
    
    def test_asset_adapter_initialization(self, asset_config):
        """Test asset adapter initialization."""
        adapter = AssetTrackingAdapter(asset_config)
        
        assert adapter.host == "test-asset-tracking.com"
        assert adapter.protocol == "http"
        assert adapter.tracking_zones == ["warehouse", "loading_dock"]
        assert adapter.asset_types == ["forklift", "pallet"]
    
    @pytest.mark.asyncio
    async def test_asset_adapter_connect_http(self, asset_adapter):
        """Test asset adapter HTTP connection."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_client.return_value.get.return_value = mock_response
            
            result = await asset_adapter._connect_http()
            assert result == True
            assert asset_adapter.connected == True
    
    @pytest.mark.asyncio
    async def test_asset_adapter_get_assets_in_zone(self, asset_adapter):
        """Test getting assets in a specific zone."""
        asset_adapter.connected = True
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "assets": [
                    {
                        "asset_id": "forklift_001",
                        "name": "Forklift 001",
                        "type": "forklift",
                        "location": "warehouse"
                    }
                ]
            }
            mock_client.return_value.get.return_value = mock_response
            
            assets = await asset_adapter.get_assets_in_zone("warehouse")
            assert len(assets) == 1
            assert assets[0]["asset_id"] == "forklift_001"

class TestIoTAdapterFactory:
    """Test IoT adapter factory."""
    
    def test_factory_registration(self):
        """Test adapter registration."""
        # Test that default adapters are registered
        adapters = IoTAdapterFactory.list_adapters()
        assert "equipment_monitor" in adapters
        assert "environmental" in adapters
        assert "safety_sensors" in adapters
        assert "asset_tracking" in adapters
    
    def test_factory_create_adapter(self):
        """Test adapter creation."""
        config = {
            "host": "test.com",
            "protocol": "http"
        }
        
        adapter = IoTAdapterFactory.create_adapter("equipment_monitor", config)
        assert isinstance(adapter, EquipmentMonitorAdapter)
        assert adapter.config == config
    
    def test_factory_create_invalid_adapter(self):
        """Test creating invalid adapter type."""
        with pytest.raises(ValueError):
            IoTAdapterFactory.create_adapter("invalid_type", {})

class TestIoTIntegrationService:
    """Test IoT integration service."""
    
    @pytest.fixture
    def iot_service(self):
        return IoTIntegrationService()
    
    @pytest.fixture
    def mock_adapter(self):
        adapter = Mock(spec=BaseIoTAdapter)
        adapter.connected = True
        adapter.connect = AsyncMock(return_value=True)
        adapter.disconnect = AsyncMock(return_value=True)
        adapter.health_check = AsyncMock(return_value={"status": "healthy"})
        adapter.get_sensor_readings = AsyncMock(return_value=[])
        adapter.get_equipment_status = AsyncMock(return_value=[])
        adapter.get_alerts = AsyncMock(return_value=[])
        adapter.acknowledge_alert = AsyncMock(return_value=True)
        adapter.start_real_time_monitoring = AsyncMock(return_value=True)
        adapter.stop_real_time_monitoring = AsyncMock(return_value=True)
        return adapter
    
    @pytest.mark.asyncio
    async def test_add_iot_connection(self, iot_service, mock_adapter):
        """Test adding IoT connection."""
        with patch('adapters.iot.factory.IoTAdapterFactory.create_adapter') as mock_factory:
            mock_factory.return_value = mock_adapter
            
            result = await iot_service.add_iot_connection(
                "equipment_monitor", 
                {"test": "config"}, 
                "test_connection"
            )
            
            assert result == True
            assert "test_connection" in iot_service.adapters
    
    @pytest.mark.asyncio
    async def test_remove_iot_connection(self, iot_service, mock_adapter):
        """Test removing IoT connection."""
        iot_service.adapters["test_connection"] = mock_adapter
        
        result = await iot_service.remove_iot_connection("test_connection")
        
        assert result == True
        assert "test_connection" not in iot_service.adapters
    
    @pytest.mark.asyncio
    async def test_get_connection_status(self, iot_service, mock_adapter):
        """Test getting connection status."""
        iot_service.adapters["test_connection"] = mock_adapter
        
        status = await iot_service.get_connection_status("test_connection")
        
        assert status["status"] == "healthy"
        mock_adapter.health_check.assert_called_once()
    
    def test_list_connections(self, iot_service, mock_adapter):
        """Test listing connections."""
        iot_service.adapters["test_connection"] = mock_adapter
        
        connections = iot_service.list_connections()
        
        assert len(connections) == 1
        assert connections[0]["connection_id"] == "test_connection"
    
    @pytest.mark.asyncio
    async def test_get_aggregated_sensor_data(self, iot_service, mock_adapter):
        """Test getting aggregated sensor data."""
        # Mock sensor readings
        reading = SensorReading(
            sensor_id="temp_001",
            sensor_type=SensorType.TEMPERATURE,
            value=22.5,
            unit="°C",
            timestamp=datetime.now(),
            location="warehouse"
        )
        mock_adapter.get_sensor_readings = AsyncMock(return_value=[reading])
        iot_service.adapters["test_connection"] = mock_adapter
        
        aggregated = await iot_service.get_aggregated_sensor_data()
        
        assert "aggregated_sensors" in aggregated
        assert aggregated["total_readings"] == 1
        assert len(aggregated["aggregated_sensors"]) == 1
    
    @pytest.mark.asyncio
    async def test_get_equipment_health_summary(self, iot_service, mock_adapter):
        """Test getting equipment health summary."""
        # Mock equipment
        equipment = Equipment(
            equipment_id="equipment_001",
            name="Test Equipment",
            type="forklift",
            location="warehouse",
            status=EquipmentStatus.ONLINE
        )
        mock_adapter.get_equipment_status = AsyncMock(return_value=[equipment])
        iot_service.adapters["test_connection"] = mock_adapter
        
        summary = await iot_service.get_equipment_health_summary()
        
        assert summary["total_equipment"] == 1
        assert summary["online_equipment"] == 1
        assert summary["offline_equipment"] == 0

class TestDataStructures:
    """Test IoT data structures."""
    
    def test_sensor_reading(self):
        """Test sensor reading creation."""
        reading = SensorReading(
            sensor_id="TEMP001",
            sensor_type=SensorType.TEMPERATURE,
            value=22.5,
            unit="°C",
            timestamp=datetime.now(),
            location="warehouse"
        )
        
        assert reading.sensor_id == "TEMP001"
        assert reading.sensor_type == SensorType.TEMPERATURE
        assert reading.value == 22.5
        assert reading.unit == "°C"
        assert reading.location == "warehouse"
    
    def test_equipment(self):
        """Test equipment creation."""
        equipment = Equipment(
            equipment_id="EQ001",
            name="Test Equipment",
            type="forklift",
            location="warehouse",
            status=EquipmentStatus.ONLINE
        )
        
        assert equipment.equipment_id == "EQ001"
        assert equipment.name == "Test Equipment"
        assert equipment.type == "forklift"
        assert equipment.location == "warehouse"
        assert equipment.status == EquipmentStatus.ONLINE
    
    def test_alert(self):
        """Test alert creation."""
        alert = Alert(
            alert_id="ALERT001",
            equipment_id="EQ001",
            sensor_id="TEMP001",
            alert_type="threshold_high",
            severity="warning",
            message="Temperature is above threshold",
            value=35.0,
            threshold=30.0,
            timestamp=datetime.now()
        )
        
        assert alert.alert_id == "ALERT001"
        assert alert.equipment_id == "EQ001"
        assert alert.sensor_id == "TEMP001"
        assert alert.alert_type == "threshold_high"
        assert alert.severity == "warning"
        assert alert.value == 35.0
        assert alert.threshold == 30.0

if __name__ == "__main__":
    pytest.main([__file__])
