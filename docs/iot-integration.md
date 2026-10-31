# IoT Integration Guide

This guide explains how to integrate IoT sensors and equipment monitoring systems with the Warehouse Operational Assistant.

## Supported IoT Systems

The system supports integration with various IoT technologies:

- **Equipment Monitoring** - Real-time equipment status and performance tracking
- **Environmental Sensors** - Temperature, humidity, air quality, and environmental monitoring
- **Safety Sensors** - Fire detection, gas monitoring, emergency systems, and safety equipment
- **Asset Tracking** - RFID, Bluetooth, GPS, and other asset location technologies

## Architecture Overview

The IoT integration system consists of:

1. **Base IoT Adapter** - Common interface for all IoT systems
2. **Specific Adapters** - Implementation for each IoT system type
3. **Factory Pattern** - Creates and manages adapter instances
4. **Integration Service** - Unified service for IoT operations
5. **REST API** - HTTP endpoints for IoT operations

## Quick Start

> **Release API:** `apps/api/maiw_api/app.py` mounts the IoT router **read-only** — only its GET endpoints are available. Adding/removing connections, acknowledging alerts and starting/stopping monitoring (POST/DELETE) return 404/405, so step 1 below is not available in the release API and steps 2–3 only work for connections that already exist.

### 1. Add an IoT Connection (not available in the release API)

```bash
curl -X POST "http://localhost:8001/api/v1/iot/connections/equipment_monitor_main" \
  -H "Content-Type: application/json" \
  -d '{
    "iot_type": "equipment_monitor",
    "config": {
      "host": "equipment-monitor.company.com",
      "protocol": "http",
      "username": "iot_user",
      "password": "secure_password"
    }
  }'
```

### 2. Check Connection Status

```bash
curl "http://localhost:8001/api/v1/iot/connections/equipment_monitor_main/status"
```

### 3. Get Sensor Readings

```bash
curl "http://localhost:8001/api/v1/iot/connections/equipment_monitor_main/sensor-readings"
```

## Configuration Examples

### Equipment Monitor Configuration

#### HTTP Protocol
```python
equipment_http_config = {
    "host": "equipment-monitor.company.com",
    "port": 8080,
    "protocol": "http",
    "username": "iot_user",
    "password": "secure_password",
    "api_key": "your_api_key_here"
}
```

#### MQTT Protocol
```python
equipment_mqtt_config = {
    "host": "mqtt-broker.company.com",
    "port": 1883,
    "protocol": "mqtt",
    "username": "mqtt_user",
    "password": "mqtt_password",
    "client_id": "warehouse_equipment_monitor",
    "topics": [
        "equipment/+/status",
        "equipment/+/sensors",
        "equipment/+/alerts"
    ]
}
```

#### WebSocket Protocol
```python
equipment_websocket_config = {
    "host": "equipment-monitor.company.com",
    "port": 8080,
    "protocol": "websocket",
    "username": "ws_user",
    "password": "ws_password"
}
```

### Environmental Sensor Configuration

#### HTTP Protocol
```python
environmental_http_config = {
    "host": "environmental-sensors.company.com",
    "port": 8080,
    "protocol": "http",
    "username": "env_user",
    "password": "env_password",
    "api_key": "env_api_key",
    "zones": ["warehouse", "loading_dock", "office", "maintenance"]
}
```

#### Modbus Protocol
```python
environmental_modbus_config = {
    "host": "modbus-server.company.com",
    "port": 502,
    "protocol": "modbus",
    "modbus_config": {
        "timeout": 10,
        "register_map": {
            "temperature": {
                "address": 100,
                "count": 1,
                "scale": 0.1,
                "unit": "°C",
                "sensor_id": "temp_001",
                "location": "warehouse"
            },
            "humidity": {
                "address": 101,
                "count": 1,
                "scale": 0.1,
                "unit": "%",
                "sensor_id": "humidity_001",
                "location": "warehouse"
            }
        }
    },
    "zones": ["warehouse", "loading_dock", "office"]
}
```

### Safety Sensor Configuration

#### HTTP Protocol
```python
safety_http_config = {
    "host": "safety-system.company.com",
    "port": 8080,
    "protocol": "http",
    "username": "safety_user",
    "password": "safety_password",
    "api_key": "safety_api_key",
    "emergency_contacts": [
        {"name": "Emergency Response Team", "phone": "+1-555-911", "email": "emergency@company.com"},
        {"name": "Safety Manager", "phone": "+1-555-1234", "email": "safety@company.com"}
    ],
    "safety_zones": ["warehouse", "loading_dock", "office", "maintenance"]
}
```

#### BACnet Protocol
```python
safety_bacnet_config = {
    "host": "bacnet-controller.company.com",
    "port": 47808,
    "protocol": "bacnet",
    "username": "bacnet_user",
    "password": "bacnet_password",
    "emergency_contacts": [
        {"name": "Emergency Response Team", "phone": "+1-555-911", "email": "emergency@company.com"}
    ],
    "safety_zones": ["warehouse", "loading_dock", "office"]
}
```

### Asset Tracking Configuration

#### HTTP Protocol
```python
asset_tracking_http_config = {
    "host": "asset-tracking.company.com",
    "port": 8080,
    "protocol": "http",
    "username": "tracking_user",
    "password": "tracking_password",
    "api_key": "tracking_api_key",
    "tracking_zones": ["warehouse", "loading_dock", "office", "maintenance"],
    "asset_types": ["forklift", "pallet", "container", "tool", "equipment"]
}
```

#### WebSocket Protocol
```python
asset_tracking_websocket_config = {
    "host": "asset-tracking.company.com",
    "port": 8080,
    "protocol": "websocket",
    "username": "ws_tracking_user",
    "password": "ws_tracking_password",
    "tracking_zones": ["warehouse", "loading_dock", "office"],
    "asset_types": ["forklift", "pallet", "container"]
}
```

## API Endpoints

### Connection Management

- `POST /api/v1/iot/connections/{connection_id}` - Add IoT connection (not mounted in the release API)
- `DELETE /api/v1/iot/connections/{connection_id}` - Remove IoT connection (not mounted in the release API)
- `GET /api/v1/iot/connections` - List all connections
- `GET /api/v1/iot/connections/{connection_id}/status` - Get connection status
- `GET /api/v1/iot/connections/status` - Get all connection status

### Sensor Operations

- `GET /api/v1/iot/connections/{connection_id}/sensor-readings` - Get sensor readings
- `GET /api/v1/iot/sensor-readings/aggregated` - Get aggregated sensor data

### Equipment Operations

- `GET /api/v1/iot/connections/{connection_id}/equipment` - Get equipment status
- `GET /api/v1/iot/equipment/health-summary` - Get equipment health summary

### Alert Operations

- `GET /api/v1/iot/connections/{connection_id}/alerts` - Get alerts
- `GET /api/v1/iot/alerts/all` - Get all alerts
- `POST /api/v1/iot/connections/{connection_id}/alerts/{alert_id}/acknowledge` - Acknowledge alert (not mounted in the release API)

### Monitoring Operations

- `POST /api/v1/iot/monitoring/start` - Start real-time monitoring (not mounted in the release API)
- `POST /api/v1/iot/monitoring/stop` - Stop real-time monitoring (not mounted in the release API)

## Data Models

### Sensor Reading

```python
{
    "sensor_id": "TEMP001",
    "sensor_type": "temperature",
    "value": 22.5,
    "unit": "°C",
    "timestamp": "2024-01-15T10:00:00Z",
    "location": "warehouse",
    "equipment_id": "EQ001",
    "quality": 1.0
}
```

### Equipment

```python
{
    "equipment_id": "EQ001",
    "name": "Forklift 001",
    "type": "forklift",
    "location": "warehouse",
    "status": "online",
    "last_seen": "2024-01-15T10:00:00Z",
    "sensors": ["TEMP001", "VIB001"],
    "metadata": {"model": "Toyota 8FGU25"}
}
```

### Alert

```python
{
    "alert_id": "ALERT001",
    "equipment_id": "EQ001",
    "sensor_id": "TEMP001",
    "alert_type": "threshold_high",
    "severity": "warning",
    "message": "Temperature is above threshold: 35.0 °C > 30.0 °C",
    "value": 35.0,
    "threshold": 30.0,
    "timestamp": "2024-01-15T10:00:00Z",
    "acknowledged": false,
    "resolved": false
}
```

## Real-time Monitoring

The IoT integration system supports real-time monitoring through various protocols:

### MQTT Monitoring
```python
# MQTT topics for equipment monitoring
topics = [
    "equipment/+/status",      # Equipment status updates
    "equipment/+/sensors",     # Sensor readings
    "equipment/+/alerts"       # Alert notifications
]
```

### WebSocket Monitoring
```python
# WebSocket connection for real-time data
websocket_url = "ws://iot-system.company.com:8080/ws"
```

### HTTP Polling
```python
# HTTP polling for sensor data
polling_interval = 30  # seconds
```

## Error Handling

The IoT integration system provides comprehensive error handling:

- **IoTConnectionError** - Connection-related errors
- **IoTDataError** - Data processing errors
- **HTTP 400** - Bad request (invalid parameters)
- **HTTP 404** - Connection not found
- **HTTP 500** - Internal server error

## Monitoring and Logging

All IoT operations are logged for audit purposes:

```python
{
    "adapter": "EquipmentMonitorAdapter",
    "operation": "get_sensor_readings",
    "timestamp": "2024-01-15T10:00:00Z",
    "count": 150
}
```

## Best Practices

### 1. Connection Management

- Use descriptive connection IDs
- Implement connection pooling for high-volume operations
- Monitor connection health regularly
- Handle connection failures gracefully

### 2. Data Synchronization

- Use batch operations for large data sets
- Implement incremental sync for better performance
- Handle data conflicts appropriately
- Validate data before synchronization

### 3. Real-time Monitoring

- Use appropriate protocols for real-time data
- Implement proper error handling for monitoring
- Set up alerting for monitoring failures
- Monitor system performance

### 4. Security

- Use secure authentication methods
- Encrypt sensitive configuration data
- Implement proper access controls
- Regular security audits

## Troubleshooting

### Common Issues

1. **Connection Timeout**
   - Check network connectivity
   - Verify IoT system availability
   - Adjust timeout settings

2. **Authentication Failures**
   - Verify credentials
   - Check user permissions
   - Ensure proper authentication method

3. **Data Mapping Issues**
   - Verify field mappings
   - Check data formats
   - Validate required fields

4. **Protocol Issues**
   - Verify protocol configuration
   - Check port accessibility
   - Ensure proper protocol libraries are installed

### Debug Mode

Enable debug logging for detailed troubleshooting:

```python
import logging
logging.getLogger('src.adapters.iot').setLevel(logging.DEBUG)
```

## Performance Optimization

### 1. Connection Pooling

```python
# Configure connection pooling
config = {
    "host": "iot-system.company.com",
    "pool_size": 10,
    "max_overflow": 20,
    "pool_timeout": 30
}
```

### 2. Batch Operations

```python
# Process multiple readings in batches
batch_size = 100
for i in range(0, len(readings), batch_size):
    batch = readings[i:i + batch_size]
    await adapter.process_readings(batch)
```

### 3. Caching

```python
# Implement caching for frequently accessed data
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_equipment_info(equipment_id):
    return adapter.get_equipment(equipment_id)
```

## Testing

### Unit Tests

```bash
# Run IoT adapter tests
pytest src/adapters/iot/tests/test_iot_adapters.py -v
```

## Support

For additional support:

1. Check the API documentation at `/docs`
2. Review the logs for error details
3. Test with the health check endpoint
4. Contact the development team

## Changelog

### Version 1.0.0
- Initial release
- Support for Equipment Monitor, Environmental, Safety, and Asset Tracking
- REST API for IoT operations
- Real-time monitoring capabilities
- Comprehensive error handling and logging
