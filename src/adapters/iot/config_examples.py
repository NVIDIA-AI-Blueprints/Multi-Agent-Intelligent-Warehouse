"""
IoT Configuration Examples.

Provides example configurations for different IoT systems
to help with setup and integration.

⚠️  SECURITY WARNING: These are example configurations only.
    Never commit actual credentials or API keys to version control.
    Always use environment variables or secure configuration management
    for production deployments.

Example usage:
    import os
    config = {
        "host": "equipment-monitor.company.com",
        "port": 8080,
        "api_key": os.getenv("IOT_EQUIPMENT_API_KEY")  # Load from environment
    }
"""

import os

# Equipment Monitor Configuration Examples
# NOTE: In production, load sensitive values from environment variables
EQUIPMENT_MONITOR_HTTP_CONFIG = {
    "host": "equipment-monitor.company.com",
    "port": 8080,
    "protocol": "http",
    "username": os.getenv("IOT_EQUIPMENT_USERNAME", "iot_user"),  # Example: use env var
    "password": os.getenv("IOT_EQUIPMENT_PASSWORD", ""),  # Example: use env var
    "api_key": os.getenv("IOT_EQUIPMENT_API_KEY", "")  # Example: use env var
}

EQUIPMENT_MONITOR_MQTT_CONFIG = {
    "host": "mqtt-broker.company.com",
    "port": 1883,
    "protocol": "mqtt",
    "username": os.getenv("IOT_MQTT_USERNAME", "mqtt_user"),  # Example: use env var
    "password": os.getenv("IOT_MQTT_PASSWORD", ""),  # Example: use env var
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
    "username": os.getenv("IOT_WEBSOCKET_USERNAME", "ws_user"),  # Example: use env var
    "password": os.getenv("IOT_WEBSOCKET_PASSWORD", "")  # Example: use env var
}

# Environmental Sensor Configuration Examples
ENVIRONMENTAL_HTTP_CONFIG = {
    "host": "environmental-sensors.company.com",
    "port": 8080,
    "protocol": "http",
    "username": os.getenv("IOT_ENVIRONMENTAL_USERNAME", "env_user"),  # Example: use env var
    "password": os.getenv("IOT_ENVIRONMENTAL_PASSWORD", ""),  # Example: use env var
    "api_key": os.getenv("IOT_ENVIRONMENTAL_API_KEY", ""),  # Example: use env var
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
# Note: Modbus typically doesn't require authentication, but if your setup does,
# use environment variables: os.getenv("MODBUS_USERNAME"), os.getenv("MODBUS_PASSWORD")

# Safety Sensor Configuration Examples
SAFETY_HTTP_CONFIG = {
    "host": "safety-system.company.com",
    "port": 8080,
    "protocol": "http",
    "username": os.getenv("IOT_SAFETY_USERNAME", "safety_user"),  # Example: use env var
    "password": os.getenv("IOT_SAFETY_PASSWORD", ""),  # Example: use env var
    "api_key": os.getenv("IOT_SAFETY_API_KEY", ""),  # Example: use env var
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
    "username": os.getenv("IOT_BACNET_USERNAME", "bacnet_user"),  # Example: use env var
    "password": os.getenv("IOT_BACNET_PASSWORD", ""),  # Example: use env var
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
    "username": os.getenv("IOT_ASSET_TRACKING_USERNAME", "tracking_user"),  # Example: use env var
    "password": os.getenv("IOT_ASSET_TRACKING_PASSWORD", ""),  # Example: use env var
    "api_key": os.getenv("IOT_ASSET_TRACKING_API_KEY", ""),  # Example: use env var
    "tracking_zones": ["warehouse", "loading_dock", "office", "maintenance"],
    "asset_types": ["forklift", "pallet", "container", "tool", "equipment"]
}

ASSET_TRACKING_WEBSOCKET_CONFIG = {
    "host": "asset-tracking.company.com",
    "port": 8080,
    "protocol": "websocket",
    "username": os.getenv("IOT_ASSET_TRACKING_WS_USERNAME", "ws_tracking_user"),  # Example: use env var
    "password": os.getenv("IOT_ASSET_TRACKING_WS_PASSWORD", ""),  # Example: use env var
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
