# API Documentation

## Overview

The Multi-Agent-Intelligent-Warehouse provides a comprehensive REST API for warehouse operations management. The API is built with FastAPI and provides OpenAPI/Swagger documentation.

**Current Status**: All core endpoints are working and tested. Recent fixes have resolved critical issues with equipment assignments and chat interface. MCP framework is now fully integrated with dynamic tool discovery and execution. MCP Testing UI is available via navigation menu.

## MCP Integration Status

###  MCP Framework Fully Integrated
- **MCP Planner Graph**: Complete workflow orchestration with MCP-enhanced intent classification
- **MCP Agents**: Equipment, Operations, and Safety agents with dynamic tool discovery
- **Tool Discovery**: Real-time tool registration and discovery across all agent types
- **Tool Execution**: Intelligent planning and execution of MCP tools
- **Cross-Agent Integration**: Seamless communication and tool sharing between agents
- **End-to-End Workflow**: Complete query processing pipeline with MCP tool results

### MCP Components
- `src/api/graphs/mcp_integrated_planner_graph.py` - MCP-enabled planner graph
- `src/api/agents/*/mcp_*_agent.py` - MCP-enabled specialized agents
- `src/api/services/mcp/` - Complete MCP framework implementation
- Dynamic tool discovery, binding, routing, and validation services

## Base URL

- **Development**: `http://localhost:8001`
- **Production**: `https://api.warehouse-assistant.com`

## Recent Fixes & Updates

###  Equipment Assignments Endpoint Fixed
- **Endpoint**: `GET /api/v1/equipment/assignments`
- **Status**:  **Working** - No more 404 errors
- **Test Endpoint**: `GET /api/v1/equipment/assignments/test`
- **Response**: Returns proper JSON with equipment assignments

###  Chat Interface Fixed
- **Component**: ChatInterfaceNew.tsx
- **Issue**: "event is undefined" runtime error
- **Status**:  **Fixed** - Removed unused event parameter
- **Impact**: Chat interface now works without runtime errors

###  MessageBubble Component Fixed
- **Component**: MessageBubble.tsx
- **Issue**: Missing opening brace syntax error
- **Status**:  **Fixed** - Component compiles successfully
- **Impact**: UI renders properly without blocking errors

## Authentication

Most API endpoints require authentication using JWT tokens. Include the token in the Authorization header:

```http
Authorization: Bearer <your-jwt-token>
```

**Note:** Some endpoints are public and do not require authentication (e.g., `/api/v1/auth/users/public`).

### Authentication Endpoints

#### GET /api/v1/auth/users/public
Get list of users for dropdown selection (public endpoint, no authentication required).

**Response:**
```json
[
  {
    "id": 1,
    "username": "admin",
    "full_name": "System Administrator",
    "role": "admin"
  },
  {
    "id": 2,
    "username": "operator1",
    "full_name": "John Doe",
    "role": "operator"
  }
]
```

**Note:** Only returns active users with basic information (id, username, full_name, role).

#### GET /api/v1/auth/users
Get all users (admin only, requires authentication).

**Response:**
```json
[
  {
    "id": 1,
    "username": "admin",
    "email": "admin@example.com",
    "full_name": "System Administrator",
    "role": "admin",
    "status": "active",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z",
    "last_login": "2024-01-15T10:30:00Z"
  }
]
```

## API Endpoints

### Health & Status

#### GET /api/v1/health
Get system health status.

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "timestamp": "2024-01-01T00:00:00Z",
  "services": {
    "database": "healthy",
    "vector_db": "healthy",
    "redis": "healthy"
  }
}
```

#### GET /api/v1/ready
Get system readiness status.

**Response:**
```json
{
  "status": "ready",
  "version": "0.1.0",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

### Chat & AI

#### POST /api/v1/chat
Send a message to the AI assistant.

**Request:**
```json
{
  "message": "What equipment is available for maintenance?",
  "session_id": "optional-session-id",
  "context": {
    "user_role": "maintenance_technician",
    "location": "warehouse_a"
  }
}
```

**Response:**
```json
{
  "response": "Based on the current inventory, the following equipment is available for maintenance...",
  "session_id": "session-123",
  "agent_used": "equipment_agent",
  "confidence": 0.95,
  "sources": [
    {
      "type": "equipment_data",
      "title": "Equipment Status Report",
      "url": "/api/v1/equipment/status"
    }
  ],
  "reasoning": {
    "type": "analytical",
    "steps": [
      "Analyzed current equipment status",
      "Checked maintenance schedules",
      "Identified available equipment"
    ]
  }
}
```

### Equipment Management

#### GET /api/v1/equipment
Get list of equipment.

**Query Parameters:**
- `status` (optional): Filter by equipment status
- `type` (optional): Filter by equipment type
- `location` (optional): Filter by location
- `limit` (optional): Number of results (default: 50)
- `offset` (optional): Pagination offset (default: 0)

**Response:**
```json
{
  "equipment": [
    {
      "id": "equip-123",
      "name": "Forklift A1",
      "type": "forklift",
      "status": "operational",
      "location": "Zone A",
      "last_maintenance": "2024-01-01T00:00:00Z",
      "next_maintenance": "2024-02-01T00:00:00Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

#### GET /api/v1/equipment/assignments
Get equipment assignments.

**Query Parameters:**
- `asset_id` (optional): Filter by specific equipment asset
- `assignee` (optional): Filter by assignee
- `active_only` (optional): Show only active assignments (default: true)

**Response:**
```json
[
  {
    "id": 8,
    "asset_id": "AGV-01",
    "task_id": "TASK-003",
    "assignee": "operator2",
    "assignment_type": "task",
    "assigned_at": "2025-09-14T16:33:47.064012+00:00",
    "released_at": null,
    "notes": null
  }
]
```

#### GET /api/v1/equipment/{equipment_id}
Get specific equipment details.

**Response:**
```json
{
  "id": "equip-123",
  "name": "Forklift A1",
  "type": "forklift",
  "status": "operational",
  "location": "Zone A",
  "specifications": {
    "capacity": "5000kg",
    "fuel_type": "electric",
    "battery_level": 85
  },
  "maintenance_history": [
    {
      "date": "2024-01-01T00:00:00Z",
      "type": "routine",
      "description": "Monthly inspection",
      "technician": "John Doe"
    }
  ]
}
```

#### POST /api/v1/equipment/{equipment_id}/maintenance
Schedule maintenance for equipment.

**Request:**
```json
{
  "type": "routine",
  "scheduled_date": "2024-02-01T09:00:00Z",
  "description": "Monthly inspection",
  "technician": "John Doe",
  "priority": "medium"
}
```

**Response:**
```json
{
  "maintenance_id": "maint-123",
  "status": "scheduled",
  "scheduled_date": "2024-02-01T09:00:00Z",
  "estimated_duration": "2 hours"
}
```

### Operations Management

#### GET /api/v1/operations
Get list of operations.

**Query Parameters:**
- `status` (optional): Filter by operation status
- `type` (optional): Filter by operation type
- `assigned_to` (optional): Filter by assigned person
- `date_from` (optional): Filter by start date
- `date_to` (optional): Filter by end date

**Response:**
```json
{
  "operations": [
    {
      "id": "op-123",
      "name": "Inventory Count - Zone A",
      "type": "cycle_count",
      "status": "in_progress",
      "assigned_to": "Jane Smith",
      "scheduled_start": "2024-01-01T09:00:00Z",
      "scheduled_end": "2024-01-01T17:00:00Z",
      "priority": "high"
    }
  ],
  "total": 1
}
```

#### POST /api/v1/operations
Create a new operation.

**Request:**
```json
{
  "name": "Inventory Count - Zone B",
  "type": "cycle_count",
  "assigned_to": "Jane Smith",
  "scheduled_start": "2024-01-02T09:00:00Z",
  "scheduled_end": "2024-01-02T17:00:00Z",
  "priority": "medium",
  "description": "Monthly inventory count for Zone B"
}
```

**Response:**
```json
{
  "operation_id": "op-124",
  "status": "created",
  "scheduled_start": "2024-01-02T09:00:00Z"
}
```

### Safety Management

#### GET /api/v1/safety/incidents
Get list of safety incidents.

**Query Parameters:**
- `severity` (optional): Filter by severity level
- `status` (optional): Filter by incident status
- `date_from` (optional): Filter by incident date
- `date_to` (optional): Filter by incident date

**Response:**
```json
{
  "incidents": [
    {
      "id": "inc-123",
      "type": "near_miss",
      "severity": "medium",
      "status": "investigating",
      "description": "Forklift operator narrowly avoided collision",
      "location": "Zone A - Aisle 3",
      "reported_by": "John Doe",
      "occurred_at": "2024-01-01T14:30:00Z",
      "reported_at": "2024-01-01T14:35:00Z"
    }
  ],
  "total": 1
}
```

#### POST /api/v1/safety/incidents
Report a new safety incident.

**Request:**
```json
{
  "type": "injury",
  "severity": "high",
  "description": "Employee injured while operating forklift",
  "location": "Zone A - Aisle 3",
  "occurred_at": "2024-01-01T14:30:00Z",
  "injured_person": "Jane Smith",
  "witnesses": ["John Doe", "Bob Wilson"]
}
```

**Response:**
```json
{
  "incident_id": "inc-124",
  "status": "reported",
  "assigned_to": "Safety Team",
  "priority": "urgent"
}
```

### Inventory Management

#### GET /api/v1/inventory/items
Get list of inventory items.

**Query Parameters:**
- `category` (optional): Filter by item category
- `location` (optional): Filter by location
- `status` (optional): Filter by item status
- `search` (optional): Search by item name or code

**Response:**
```json
{
  "items": [
    {
      "id": "item-123",
      "code": "WIDGET-001",
      "name": "Widget Type A",
      "category": "electronics",
      "quantity": 150,
      "location": "Zone A - Shelf 1",
      "status": "active",
      "last_counted": "2024-01-01T00:00:00Z"
    }
  ],
  "total": 1
}
```

#### GET /api/v1/inventory/items/{item_id}/movements
Get movement history for an item.

**Response:**
```json
{
  "item_id": "item-123",
  "movements": [
    {
      "id": "mov-123",
      "type": "inbound",
      "quantity": 50,
      "quantity_before": 100,
      "quantity_after": 150,
      "reference": "PO-2024-001",
      "timestamp": "2024-01-01T10:00:00Z",
      "operator": "John Doe"
    }
  ],
  "total": 1
}
```

### Migration Management

#### GET /api/v1/migrations/status
Get database migration status.

**Response:**
```json
{
  "status": "ok",
  "version": "0.1.0",
  "applied_count": 3,
  "pending_count": 0,
  "total_count": 3,
  "applied_migrations": [
    {
      "version": "001",
      "description": "Initial schema",
      "applied_at": "2024-01-01T00:00:00Z",
      "execution_time_ms": 1500
    }
  ],
  "pending_migrations": []
}
```

#### POST /api/v1/migrations/migrate
Run database migrations.

**Request:**
```json
{
  "target_version": "003",
  "dry_run": false
}
```

**Response:**
```json
{
  "status": "ok",
  "message": "Migrations completed successfully",
  "dry_run": false,
  "target_version": "003"
}
```

### Monitoring & Metrics

#### GET /api/v1/metrics
Get Prometheus metrics.

**Response:**
```
# HELP http_requests_total Total number of HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="GET",endpoint="/api/v1/health"} 100

# HELP http_request_duration_seconds HTTP request duration in seconds
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{method="GET",endpoint="/api/v1/health",le="0.1"} 95
```

## Error Responses

All endpoints may return the following error responses:

### 400 Bad Request
```json
{
  "error": "validation_error",
  "message": "Invalid request parameters",
  "details": {
    "field": "scheduled_date",
    "issue": "Invalid date format"
  }
}
```

### 401 Unauthorized
```json
{
  "error": "authentication_error",
  "message": "Invalid or missing authentication token"
}
```

### 403 Forbidden
```json
{
  "error": "authorization_error",
  "message": "Insufficient permissions for this operation"
}
```

### 404 Not Found
```json
{
  "error": "not_found",
  "message": "Resource not found",
  "resource": "equipment",
  "id": "equip-123"
}
```

### 500 Internal Server Error
```json
{
  "error": "internal_error",
  "message": "An internal server error occurred",
  "request_id": "req-123"
}
```

## Rate Limiting

API requests are rate limited to prevent abuse:

- **Authenticated users**: 1000 requests per hour
- **Unauthenticated users**: 100 requests per hour

Rate limit headers are included in responses:

```http
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1640995200
```

## Pagination

List endpoints support pagination using `limit` and `offset` parameters:

- `limit`: Number of items per page (default: 50, max: 100)
- `offset`: Number of items to skip (default: 0)

Pagination metadata is included in responses:

```json
{
  "data": [...],
  "pagination": {
    "total": 1000,
    "limit": 50,
    "offset": 0,
    "has_next": true,
    "has_prev": false
  }
}
```

## WebSocket Endpoints

### /ws/chat
Real-time chat connection for live AI assistance.

**Connection:**
```javascript
const ws = new WebSocket('ws://localhost:8001/ws/chat?token=<jwt-token>');
```

**Message Format:**
```json
{
  "type": "message",
  "content": "What equipment needs maintenance?",
  "session_id": "session-123"
}
```

**Response Format:**
```json
{
  "type": "response",
  "content": "Based on the current status...",
  "agent_used": "equipment_agent",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

## SDKs and Client Libraries

### Python
```python
from warehouse_assistant import WarehouseAssistant

client = WarehouseAssistant(
    base_url="http://localhost:8001",
    api_key="your-api-key"
)

# Send a chat message
response = client.chat.send_message(
    message="What equipment is available?",
    session_id="session-123"
)
```

### JavaScript
```javascript
import { WarehouseAssistant } from '@warehouse-assistant/client';

const client = new WarehouseAssistant({
  baseUrl: 'http://localhost:8001',
  apiKey: 'your-api-key'
});

// Send a chat message
const response = await client.chat.sendMessage({
  message: 'What equipment is available?',
  sessionId: 'session-123'
});
```

## OpenAPI Specification

The complete OpenAPI specification is available at:

- **Swagger UI**: `http://localhost:8001/docs`
- **ReDoc**: `http://localhost:8001/redoc`
- **OpenAPI JSON**: `http://localhost:8001/openapi.json`

## Support

For API support and questions:

- **Documentation**: [https://docs.warehouse-assistant.com](https://docs.warehouse-assistant.com)
- **Issues**: [https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/issues](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/issues)
- **Email**: support@warehouse-assistant.com
