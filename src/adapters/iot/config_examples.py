"""
IoT Configuration Examples.

Provides example configurations for different IoT systems
to help with setup and integration.
"""

# Equipment Monitor Configuration Examples
EQUIPMENT_MONITOR_HTTP_CONFIG = {
    "host": "equipment-monitor.company.com",
    "port": 8080,
    "protocol": "http",
    "username": "iot_user",
    "password": "secure_password",
    "api_key": "your_api_key_here"
}

EQUIPMENT_MONITOR_MQTT_CONFIG = {
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

EQUIPMENT_MONITOR_WEBSOCKET_CONFIG = {
    "host": "equipment-monitor.company.com",
    "port": 8080,
    "protocol": "websocket",
    "username": "ws_user",
    "password": "ws_password"
}

# Environmental Sensor Configuration Examples
ENVIRONMENTAL_HTTP_CONFIG = {
    "host": "environmental-sensors.company.com",
    "port": 8080,
    "protocol": "http",
    "username": "env_user",
    "password": "env_password",
    "api_key": "env_api_key",
    "zones": ["warehouse", "loading_dock", "office", "maintenance"]
}

ENVIRONMENTAL_MODBUS_CONFIG = {
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
            },
            "pressure": {
                "address": 102,
                "count": 1,
                "scale": 1.0,
                "unit": "hPa",
                "sensor_id": "pressure_001",
                "location": "warehouse"
            }
        }
    },
    "zones": ["warehouse", "loading_dock", "office"]
}

# Safety Sensor Configuration Examples
SAFETY_HTTP_CONFIG = {
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

SAFETY_BACNET_CONFIG = {
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

# Asset Tracking Configuration Examples
ASSET_TRACKING_HTTP_CONFIG = {
    "host": "asset-tracking.company.com",
    "port": 8080,
    "protocol": "http",
    "username": "tracking_user",
    "password": "tracking_password",
    "api_key": "tracking_api_key",
    "tracking_zones": ["warehouse", "loading_dock", "office", "maintenance"],
    "asset_types": ["forklift", "pallet", "container", "tool", "equipment"]
}

ASSET_TRACKING_WEBSOCKET_CONFIG = {
    "host": "asset-tracking.company.com",
    "port": 8080,
    "protocol": "websocket",
    "username": "ws_tracking_user",
    "password": "ws_tracking_password",
    "tracking_zones": ["warehouse", "loading_dock", "office"],
    "asset_types": ["forklift", "pallet", "container"]
}

# Configuration validation schemas
IoT_CONFIG_SCHEMAS = {
    "equipment_monitor": {
        "required": ["host"],
        "optional": ["port", "protocol", "username", "password", "client_id", "topics", "api_key"],
        "defaults": {
            "port": 1883,
            "protocol": "mqtt"
        }
    },
    "environmental": {
        "required": ["host"],
        "optional": ["port", "protocol", "username", "password", "api_key", "modbus_config", "zones"],
        "defaults": {
            "port": 8080,
            "protocol": "http",
            "zones": ["warehouse"]
        }
    },
    "safety_sensors": {
        "required": ["host"],
        "optional": ["port", "protocol", "username", "password", "api_key", "emergency_contacts", "safety_zones"],
        "defaults": {
            "port": 8080,
            "protocol": "http",
            "safety_zones": ["warehouse"]
        }
    },
    "asset_tracking": {
        "required": ["host"],
        "optional": ["port", "protocol", "username", "password", "api_key", "tracking_zones", "asset_types"],
        "defaults": {
            "port": 8080,
            "protocol": "http",
            "tracking_zones": ["warehouse"],
            "asset_types": ["equipment"]
        }
    }
}

def validate_iot_config(iot_type: str, config: dict) -> tuple[bool, list[str]]:
    """
    Validate IoT configuration.
    
    Args:
        iot_type: Type of IoT system
        config: Configuration dictionary
        
    Returns:
        tuple: (is_valid, error_messages)
    """
    if iot_type not in IoT_CONFIG_SCHEMAS:
        return False, [f"Unsupported IoT type: {iot_type}"]
    
    schema = IoT_CONFIG_SCHEMAS[iot_type]
    errors = []
    
    # Check required fields
    for field in schema["required"]:
        if field not in config:
            errors.append(f"Missing required field: {field}")
    
    # Apply defaults
    for field, default_value in schema["defaults"].items():
        if field not in config:
            config[field] = default_value
    
    return len(errors) == 0, errors

def get_config_example(iot_type: str, protocol: str = "http") -> dict:
    """
    Get configuration example for IoT type and protocol.
    
    Args:
        iot_type: Type of IoT system
        protocol: Protocol type (http, mqtt, websocket, modbus, bacnet)
        
    Returns:
        dict: Example configuration
    """
    examples = {
        "equipment_monitor": {
            "http": EQUIPMENT_MONITOR_HTTP_CONFIG,
            "mqtt": EQUIPMENT_MONITOR_MQTT_CONFIG,
            "websocket": EQUIPMENT_MONITOR_WEBSOCKET_CONFIG
        },
        "environmental": {
            "http": ENVIRONMENTAL_HTTP_CONFIG,
            "modbus": ENVIRONMENTAL_MODBUS_CONFIG
        },
        "safety_sensors": {
            "http": SAFETY_HTTP_CONFIG,
            "bacnet": SAFETY_BACNET_CONFIG
        },
        "asset_tracking": {
            "http": ASSET_TRACKING_HTTP_CONFIG,
            "websocket": ASSET_TRACKING_WEBSOCKET_CONFIG
        }
    }
    
    return examples.get(iot_type, {}).get(protocol, {})

def get_all_config_examples() -> dict:
    """
    Get all configuration examples.
    
    Returns:
        dict: All configuration examples organized by type and protocol
    """
    return {
        "equipment_monitor": {
            "http": EQUIPMENT_MONITOR_HTTP_CONFIG,
            "mqtt": EQUIPMENT_MONITOR_MQTT_CONFIG,
            "websocket": EQUIPMENT_MONITOR_WEBSOCKET_CONFIG
        },
        "environmental": {
            "http": ENVIRONMENTAL_HTTP_CONFIG,
            "modbus": ENVIRONMENTAL_MODBUS_CONFIG
        },
        "safety_sensors": {
            "http": SAFETY_HTTP_CONFIG,
            "bacnet": SAFETY_BACNET_CONFIG
        },
        "asset_tracking": {
            "http": ASSET_TRACKING_HTTP_CONFIG,
            "websocket": ASSET_TRACKING_WEBSOCKET_CONFIG
        }
    }
