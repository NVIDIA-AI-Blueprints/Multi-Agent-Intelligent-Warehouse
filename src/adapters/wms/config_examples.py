"""
WMS Configuration Examples.

Provides example configurations for different WMS systems
to help with setup and integration.
"""

# SAP EWM Configuration Example
SAP_EWM_CONFIG = {
    "host": "sap-ewm.company.com",
    "port": 8000,
    "client": "100",
    "user": "WMS_USER",
    "password": "secure_password",
    "system_id": "EWM",
    "warehouse_number": "1000",
    "use_rfc": False  # Use REST API instead of RFC
}

# Manhattan WMS Configuration Example
MANHATTAN_CONFIG = {
    "host": "manhattan-wms.company.com",
    "port": 8080,
    "username": "wms_user",
    "password": "secure_password",
    "facility_id": "FAC001",
    "client_id": "CLIENT001",
    "use_ssl": True
}

# Oracle WMS Configuration Example
ORACLE_CONFIG = {
    "host": "oracle-wms.company.com",
    "port": 8000,
    "username": "wms_user",
    "password": "secure_password",
    "organization_id": "ORG001",
    "warehouse_id": "WH001",
    "use_ssl": True,
    "database_config": {
        "host": "oracle-db.company.com",
        "port": 1521,
        "service_name": "WMS",
        "username": "wms_db_user",
        "password": "db_password"
    }
}

# Configuration validation schemas
WMS_CONFIG_SCHEMAS = {
    "sap_ewm": {
        "required": ["host", "user", "password", "warehouse_number"],
        "optional": ["port", "client", "system_id", "use_rfc"],
        "defaults": {
            "port": 8000,
            "use_rfc": False
        }
    },
    "manhattan": {
        "required": ["host", "username", "password", "facility_id"],
        "optional": ["port", "client_id", "use_ssl"],
        "defaults": {
            "port": 8080,
            "use_ssl": True
        }
    },
    "oracle": {
        "required": ["host", "username", "password", "organization_id"],
        "optional": ["port", "warehouse_id", "use_ssl", "database_config"],
        "defaults": {
            "port": 8000,
            "use_ssl": True
        }
    }
}

def validate_wms_config(wms_type: str, config: dict) -> tuple[bool, list[str]]:
    """
    Validate WMS configuration.
    
    Args:
        wms_type: Type of WMS system
        config: Configuration dictionary
        
    Returns:
        tuple: (is_valid, error_messages)
    """
    if wms_type not in WMS_CONFIG_SCHEMAS:
        return False, [f"Unsupported WMS type: {wms_type}"]
    
    schema = WMS_CONFIG_SCHEMAS[wms_type]
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

def get_config_example(wms_type: str) -> dict:
    """
    Get configuration example for WMS type.
    
    Args:
        wms_type: Type of WMS system
        
    Returns:
        dict: Example configuration
    """
    examples = {
        "sap_ewm": SAP_EWM_CONFIG,
        "manhattan": MANHATTAN_CONFIG,
        "oracle": ORACLE_CONFIG
    }
    
    return examples.get(wms_type, {})
