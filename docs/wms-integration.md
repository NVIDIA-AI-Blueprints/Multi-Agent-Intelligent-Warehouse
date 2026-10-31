# WMS Integration Guide

This guide explains how to integrate external WMS systems with the Warehouse Operational Assistant.

## Supported WMS Systems

The system supports integration with the following WMS systems:

- **SAP Extended Warehouse Management (EWM)**
- **Manhattan Associates WMS**
- **Oracle WMS**

## Architecture Overview

The WMS integration system consists of:

1. **Base WMS Adapter** - Common interface for all WMS systems
2. **Specific Adapters** - Implementation for each WMS system
3. **Factory Pattern** - Creates and manages adapter instances
4. **Integration Service** - Unified service for WMS operations
5. **REST API** - HTTP endpoints for WMS operations

## Quick Start

> **Release API:** `apps/api/maiw_api/app.py` mounts the WMS router **read-only** — only its GET endpoints are available. Adding/removing connections, creating or updating tasks and orders, and inventory sync (POST/DELETE/PATCH) return 404/405, so step 1 below is not available in the release API and steps 2–3 only work for connections that already exist.

### 1. Add a WMS Connection (not available in the release API)

```bash
curl -X POST "http://localhost:8001/api/v1/wms/connections?connection_id=sap_ewm_main" \
  -H "Content-Type: application/json" \
  -d '{
    "wms_type": "sap_ewm",
    "config": {
      "host": "sap-ewm.company.com",
      "user": "WMS_USER",
      "password": "secure_password",
      "warehouse_number": "1000"
    }
  }'
```

### 2. Check Connection Status

```bash
curl "http://localhost:8001/api/v1/wms/connections/sap_ewm_main/status"
```

### 3. Get Inventory

```bash
curl "http://localhost:8001/api/v1/wms/connections/sap_ewm_main/inventory"
```

## Configuration Examples

### SAP EWM Configuration

```python
sap_config = {
    "host": "sap-ewm.company.com",
    "port": 8000,
    "client": "100",
    "user": "WMS_USER",
    "password": "secure_password",
    "system_id": "EWM",
    "warehouse_number": "1000",
    "use_rfc": False  # Use REST API
}
```

### Manhattan WMS Configuration

```python
manhattan_config = {
    "host": "manhattan-wms.company.com",
    "port": 8080,
    "username": "wms_user",
    "password": "secure_password",
    "facility_id": "FAC001",
    "client_id": "CLIENT001",
    "use_ssl": True
}
```

### Oracle WMS Configuration

```python
oracle_config = {
    "host": "oracle-wms.company.com",
    "port": 8000,
    "username": "wms_user",
    "password": "secure_password",
    "organization_id": "ORG001",
    "warehouse_id": "WH001",
    "use_ssl": True
}
```

## API Endpoints

### Connection Management

- `POST /api/v1/wms/connections?connection_id=...` - Add WMS connection (not mounted in the release API)
- `DELETE /api/v1/wms/connections/{connection_id}` - Remove WMS connection (not mounted in the release API)
- `GET /api/v1/wms/connections` - List all connections
- `GET /api/v1/wms/connections/{connection_id}/status` - Get connection status
- `GET /api/v1/wms/connections/status` - Get all connection status

### Inventory Operations

- `GET /api/v1/wms/connections/{connection_id}/inventory` - Get inventory
- `GET /api/v1/wms/inventory/aggregated` - Get aggregated inventory
- `POST /api/v1/wms/sync/inventory` - Sync inventory between systems (not mounted in the release API)

### Task Operations

- `GET /api/v1/wms/connections/{connection_id}/tasks` - Get tasks
- `POST /api/v1/wms/connections/{connection_id}/tasks` - Create task (not mounted in the release API)
- `PATCH /api/v1/wms/connections/{connection_id}/tasks/{task_id}` - Update task status (not mounted in the release API)

### Order Operations

- `GET /api/v1/wms/connections/{connection_id}/orders` - Get orders
- `POST /api/v1/wms/connections/{connection_id}/orders` - Create order (not mounted in the release API)

### Location Operations

- `GET /api/v1/wms/connections/{connection_id}/locations` - Get locations

## Data Models

### Inventory Item

```python
{
    "sku": "SKU001",
    "name": "Product Name",
    "quantity": 100,
    "available_quantity": 95,
    "reserved_quantity": 5,
    "location": "A1-B2-C3",
    "zone": "ZONE_A",
    "status": "active"
}
```

### Task

```python
{
    "task_id": "TASK001",
    "task_type": "pick",
    "priority": 1,
    "status": "pending",
    "assigned_to": "worker001",
    "location": "A1-B2-C3",
    "destination": "PACK_STATION_1",
    "notes": "Urgent order"
}
```

### Order

```python
{
    "order_id": "ORDER001",
    "order_type": "sales",
    "status": "pending",
    "priority": 1,
    "customer_id": "CUST001",
    "required_date": "2024-01-15T10:00:00Z"
}
```

## Error Handling

The WMS integration system provides comprehensive error handling:

- **WMSConnectionError** - Connection-related errors
- **WMSDataError** - Data processing errors
- **HTTP 400** - Bad request (invalid parameters)
- **HTTP 404** - Connection not found
- **HTTP 500** - Internal server error

## Monitoring and Logging

All WMS operations are logged for audit purposes:

```python
{
    "adapter": "SAPEWMAdapter",
    "operation": "get_inventory",
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

### 3. Error Handling

- Implement retry logic for transient failures
- Log all errors with sufficient context
- Provide meaningful error messages to users
- Monitor error rates and patterns

### 4. Security

- Use secure authentication methods
- Encrypt sensitive configuration data
- Implement proper access controls
- Regular security audits

## Troubleshooting

### Common Issues

1. **Connection Timeout**
   - Check network connectivity
   - Verify WMS system availability
   - Adjust timeout settings

2. **Authentication Failures**
   - Verify credentials
   - Check user permissions
   - Ensure proper authentication method

3. **Data Mapping Issues**
   - Verify field mappings
   - Check data formats
   - Validate required fields

### Debug Mode

Enable debug logging for detailed troubleshooting:

```python
import logging
logging.getLogger('src.adapters.wms').setLevel(logging.DEBUG)
```

## Performance Optimization

### 1. Connection Pooling

```python
# Configure connection pooling
config = {
    "host": "wms.company.com",
    "pool_size": 10,
    "max_overflow": 20,
    "pool_timeout": 30
}
```

### 2. Batch Operations

```python
# Process multiple items in batches
batch_size = 100
for i in range(0, len(items), batch_size):
    batch = items[i:i + batch_size]
    await adapter.update_inventory(batch)
```

### 3. Caching

```python
# Implement caching for frequently accessed data
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_location_info(location_id):
    return adapter.get_location(location_id)
```

## Testing

### Unit Tests

```bash
# Run WMS adapter tests
pytest src/adapters/wms/tests/test_wms_adapters.py -v
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
- Support for SAP EWM, Manhattan, and Oracle WMS
- REST API for WMS operations
- Comprehensive error handling and logging
