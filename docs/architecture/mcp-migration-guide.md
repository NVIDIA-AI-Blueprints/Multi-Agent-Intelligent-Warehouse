# MCP Migration Guide

## Overview

This guide provides comprehensive instructions for migrating the Warehouse Operational Assistant to the Model Context Protocol (MCP) architecture. The migration is designed to be completed in three phases, with each phase building upon the previous one.

## Table of Contents

1. [Migration Overview](#migration-overview)
2. [Phase 1: MCP Foundation](#phase-1-mcp-foundation)
3. [Phase 2: Agent Integration](#phase-2-agent-integration)
4. [Phase 3: Full Migration](#phase-3-full-migration)
5. [Migration Checklist](#migration-checklist)
6. [Troubleshooting](#troubleshooting)
7. [Best Practices](#best-practices)

## Migration Overview

### What is MCP?

The Model Context Protocol (MCP) is a standardized protocol for tool discovery, execution, and communication between AI agents and external systems. It provides:

- **Dynamic Tool Discovery**: Automatic discovery of available tools and capabilities
- **Standardized Communication**: Consistent interface for tool execution
- **Service Registry**: Centralized management of services and adapters
- **Health Monitoring**: Comprehensive monitoring and alerting
- **Scalability**: Easy addition of new tools and services

### Migration Benefits

- **Improved Tool Management**: Centralized tool discovery and execution
- **Enhanced Scalability**: Easy addition of new adapters and tools
- **Better Monitoring**: Comprehensive health monitoring and alerting
- **Standardized Interface**: Consistent API across all services
- **Reduced Complexity**: Simplified agent-to-tool communication

### Migration Timeline

| Phase | Duration | Focus | Status |
|-------|----------|-------|--------|
| Phase 1 | 2-3 weeks | Foundation & Infrastructure |  Complete |
| Phase 2 | 2-3 weeks | Agent Integration |  Complete |
| Phase 3 | 3-4 weeks | Full Migration |  In Progress |

## Phase 1: MCP Foundation

### Objectives

- Implement core MCP server and client infrastructure
- Create MCP-enabled base classes for adapters and tools
- Migrate ERP adapter as proof of concept
- Establish testing framework

### Components Implemented

#### 1. MCP Server (`src/api/services/mcp/server.py`)

The MCP server provides tool registration, discovery, and execution capabilities.

**Key Features:**
- Tool registration and management
- Tool discovery and listing
- Tool execution with parameter validation
- Resource and prompt management
- Error handling and logging

**Usage Example:**
```python
from src.api.services.mcp.server import MCPServer, MCPTool, MCPToolType

# Create server
server = MCPServer()

# Register a tool
tool = MCPTool(
    name="get_inventory",
    description="Get inventory levels",
    tool_type=MCPToolType.FUNCTION,
    parameters={
        "item_id": {"type": "string", "required": True},
        "location": {"type": "string", "required": False}
    },
    handler=inventory_handler
)

server.register_tool(tool)

# Start server
await server.start()
```

#### 2. MCP Client (`src/api/services/mcp/client.py`)

The MCP client enables communication with MCP servers and tool execution.

**Key Features:**
- Multi-server communication
- Tool discovery and execution
- Resource access and management
- Prompt management
- HTTP and WebSocket support

**Usage Example:**
```python
from src.api.services.mcp.client import MCPClient, MCPConnectionType

# Create client
client = MCPClient()

# Connect to server
await client.connect("http://localhost:8000", MCPConnectionType.HTTP)

# Discover tools
tools = await client.discover_tools()

# Execute tool
result = await client.execute_tool("get_inventory", {
    "item_id": "ITEM001",
    "location": "WAREHOUSE_A"
})
```

#### 3. Base Classes (`src/api/services/mcp/base.py`)

Base classes provide the foundation for MCP adapters and tools.

**Key Components:**
- `MCPAdapter`: Base class for all adapters
- `MCPToolBase`: Base class for tools
- `MCPManager`: System coordination and management
- Configuration classes and error handling

**Usage Example:**
```python
from src.api.services.mcp.base import MCPAdapter, AdapterConfig, AdapterType

class MyAdapter(MCPAdapter):
    def __init__(self, config: AdapterConfig):
        super().__init__(config)
        self._setup_tools()
    
    def _setup_tools(self):
        # Setup adapter-specific tools
        pass
    
    async def connect(self) -> bool:
        # Implement connection logic
        pass
    
    async def disconnect(self) -> None:
        # Implement disconnection logic
        pass
```

#### 4. ERP Adapter (`src/api/services/mcp/adapters/erp_adapter.py`)

The ERP adapter demonstrates MCP integration with enterprise resource planning systems.

**Key Features:**
- Customer and order management
- Inventory synchronization
- Financial reporting
- Sales analytics
- Integration with multiple ERP systems

### Testing Framework

Comprehensive testing framework with unit tests, integration tests, and performance tests.

**Test Files:**
- `tests/test_mcp_system.py`: Core MCP system tests
- `tests/integration/test_mcp_integration.py`: Integration tests
- `tests/performance/test_mcp_performance.py`: Performance tests

## Phase 2: Agent Integration

### Objectives

- Implement dynamic tool discovery and registration
- Update all agents to use MCP tools
- Create dynamic tool binding and execution framework
- Add MCP-based routing and tool selection
- Implement validation and error handling

### Components Implemented

#### 1. Tool Discovery Service (`src/api/services/mcp/tool_discovery.py`)

Dynamic tool discovery and registration system.

**Key Features:**
- Automatic tool discovery from MCP servers and adapters
- Tool categorization and filtering
- Usage tracking and performance monitoring
- Search and discovery capabilities
- Tool registration and management

**Usage Example:**
```python
from src.api.services.mcp.tool_discovery import ToolDiscoveryService, ToolCategory

# Create discovery service
discovery = ToolDiscoveryService()

# Start discovery
await discovery.start_discovery()

# Register discovery source
await discovery.register_discovery_source(
    "erp_adapter",
    erp_adapter,
    "mcp_adapter"
)

# Search for tools
tools = await discovery.search_tools("inventory")

# Get tools by category
equipment_tools = await discovery.get_tools_by_category(ToolCategory.EQUIPMENT)
```

#### 2. Tool Binding Service (`src/api/services/mcp/tool_binding.py`)

Dynamic tool binding and execution framework.

**Key Features:**
- Multiple binding strategies (exact, fuzzy, semantic, category, performance-based)
- Execution modes (sequential, parallel, pipeline, conditional)
- Tool binding and execution planning
- Performance monitoring and optimization

**Usage Example:**
```python
from src.api.services.mcp.tool_binding import ToolBindingService, BindingStrategy, ExecutionMode

# Create binding service
binding = ToolBindingService(discovery)

# Bind tools to agent
bindings = await binding.bind_tools(
    agent_id="equipment_agent",
    query="Get equipment status",
    intent="equipment_lookup",
    entities={"equipment_id": "EQ001"},
    context={},
    strategy=BindingStrategy.SEMANTIC_MATCH,
    max_tools=5
)

# Create execution plan
plan = await binding.create_execution_plan(
    context,
    bindings,
    ExecutionMode.SEQUENTIAL
)

# Execute plan
results = await binding.execute_plan(plan)
```

#### 3. Tool Routing Service (`src/api/services/mcp/tool_routing.py`)

Intelligent tool routing and selection.

**Key Features:**
- Multiple routing strategies (performance, accuracy, balanced, cost, latency optimized)
- Query complexity analysis
- Multi-criteria optimization for tool selection
- Context-aware tool matching
- Fallback and redundancy mechanisms

**Usage Example:**
```python
from src.api.services.mcp.tool_routing import ToolRoutingService, RoutingStrategy, RoutingContext

# Create routing service
routing = ToolRoutingService(discovery, binding)

# Create routing context
context = RoutingContext(
    query="Get equipment status for forklift EQ001",
    intent="equipment_lookup",
    entities={"equipment_id": "EQ001", "equipment_type": "forklift"},
    user_context={"priority": "high"},
    session_id="session_123",
    agent_id="equipment_agent"
)

# Route tools
decision = await routing.route_tools(
    context,
    strategy=RoutingStrategy.BALANCED,
    max_tools=5
)

# Get selected tools
selected_tools = decision.selected_tools
```

#### 4. Tool Validation Service (`src/api/services/mcp/tool_validation.py`)

Comprehensive validation and error handling.

**Key Features:**
- Input validation for tool parameters
- Tool capability validation
- Execution context validation
- Result validation and verification
- Error detection, classification, and recovery
- Retry logic and backoff strategies

**Usage Example:**
```python
from src.api.services.mcp.tool_validation import ToolValidationService, ValidationLevel

# Create validation service
validation = ToolValidationService(discovery)

# Validate tool execution
result = await validation.validate_tool_execution(
    tool_id="get_equipment_status",
    arguments={"equipment_id": "EQ001"},
    context=execution_context,
    validation_level=ValidationLevel.STANDARD
)

if result.is_valid:
    # Proceed with execution
    pass
else:
    # Handle validation errors
    for error in result.errors:
        print(f"Validation error: {error}")
```

#### 5. MCP-Enabled Agents

Updated agents with MCP integration:

- **Equipment Agent** (`src/api/agents/inventory/mcp_equipment_agent.py`)
- **Operations Agent** (`src/api/agents/operations/mcp_operations_agent.py`)
- **Safety Agent** (`src/api/agents/safety/mcp_safety_agent.py`)

**Key Features:**
- Dynamic tool discovery and execution
- MCP-based tool binding and routing
- Enhanced tool selection and validation
- Comprehensive error handling and fallback mechanisms

## Phase 3: Full Migration

### Objectives

- Migrate all remaining adapters to MCP protocol
- Implement service discovery and registry
- Add monitoring, logging, and management capabilities
- Create comprehensive documentation
- Implement end-to-end testing
- Update deployment configurations

### Components Implemented

#### 1. WMS Adapter (`src/api/services/mcp/adapters/wms_adapter.py`)

MCP-enabled Warehouse Management System adapter.

**Supported Systems:**
- SAP EWM (Extended Warehouse Management)
- Manhattan Associates WMS
- Oracle WMS
- HighJump WMS
- JDA/Blue Yonder WMS

**Key Features:**
- Inventory management and tracking
- Order processing and fulfillment
- Receiving and putaway operations
- Picking and shipping operations
- Warehouse configuration and optimization
- Reporting and analytics

#### 2. IoT Adapter (`src/api/services/mcp/adapters/iot_adapter.py`)

MCP-enabled Internet of Things adapter.

**Supported Platforms:**
- Azure IoT Hub
- AWS IoT Core
- Google Cloud IoT
- Custom IoT platforms

**Key Features:**
- Equipment monitoring and telemetry
- Environmental condition monitoring
- Safety and security monitoring
- Asset tracking and location services
- Predictive maintenance and analytics
- Real-time alerts and notifications

#### 3. RFID/Barcode Adapter (`src/api/services/mcp/adapters/rfid_barcode_adapter.py`)

MCP-enabled RFID and barcode scanning adapter.

**Supported Systems:**
- RFID readers and tags (UHF, HF, LF)
- Barcode scanners (1D, 2D, QR codes)
- Mobile scanning devices
- Fixed scanning stations

**Key Features:**
- RFID tag reading and writing
- Barcode scanning and validation
- Asset tracking and identification
- Inventory management and counting
- Mobile scanning operations
- Data validation and processing

#### 4. Time Attendance Adapter (`src/api/services/mcp/adapters/time_attendance_adapter.py`)

MCP-enabled time and attendance adapter.

**Supported Systems:**
- Biometric time clocks
- RFID/NFC card readers
- Mobile time tracking applications
- Web-based time entry systems

**Key Features:**
- Clock in/out operations
- Break and meal tracking
- Overtime calculation
- Shift management
- Attendance reporting
- Integration with HR systems

#### 5. Service Discovery (`src/api/services/mcp/service_discovery.py`)

Service discovery and registry system.

**Key Features:**
- Service registration and deregistration
- Service discovery and lookup
- Health monitoring and status tracking
- Load balancing and failover
- Service metadata management

#### 6. Monitoring System (`src/api/services/mcp/monitoring.py`)

Comprehensive monitoring, logging, and management.

**Key Features:**
- Metrics collection and analysis
- Alert management and notification
- System health monitoring
- Log management and analysis
- Performance monitoring

## Migration Checklist

### Pre-Migration

- [ ] Backup current system
- [ ] Review current architecture
- [ ] Identify integration points
- [ ] Plan migration timeline
- [ ] Set up development environment

### Phase 1: Foundation

- [x] Implement MCP server
- [x] Implement MCP client
- [x] Create base classes
- [x] Migrate ERP adapter
- [x] Create testing framework

### Phase 2: Agent Integration

- [x] Implement tool discovery service
- [x] Update Equipment agent
- [x] Update Operations agent
- [x] Update Safety agent
- [x] Implement tool binding service
- [x] Implement tool routing service
- [x] Implement tool validation service

### Phase 3: Full Migration

- [x] Migrate WMS adapter
- [x] Migrate IoT adapter
- [x] Migrate RFID/Barcode adapter
- [x] Migrate Time Attendance adapter
- [x] Implement service discovery
- [x] Implement monitoring system
- [ ] Create documentation
- [ ] Implement end-to-end testing
- [ ] Update deployment configurations
- [ ] Create rollback strategy

### Post-Migration

- [ ] Performance testing
- [ ] Security testing
- [ ] User acceptance testing
- [ ] Production deployment
- [ ] Monitoring and alerting setup
- [ ] Documentation updates

## Troubleshooting

### Common Issues

#### 1. Tool Discovery Failures

**Problem:** Tools not being discovered automatically.

**Solution:**
```python
# Check discovery service status
status = await discovery.get_discovery_status()
print(f"Discovery running: {status['running']}")
print(f"Sources: {status['sources']}")

# Manually register source
await discovery.register_discovery_source(
    "my_adapter",
    my_adapter,
    "mcp_adapter"
)
```

#### 2. Tool Execution Errors

**Problem:** Tools failing to execute.

**Solution:**
```python
# Validate tool execution
validation_result = await validation.validate_tool_execution(
    tool_id="my_tool",
    arguments={"param1": "value1"},
    context=execution_context
)

if not validation_result.is_valid:
    print(f"Validation errors: {validation_result.errors}")
```

#### 3. Service Registration Issues

**Problem:** Services not registering properly.

**Solution:**
```python
# Check service registry
services = await registry.get_all_services()
print(f"Registered services: {len(services)}")

# Check service health
for service in services:
    health = await registry.get_service_health(service.service_id)
    print(f"Service {service.service_name}: {health.is_healthy}")
```

### Debugging Tips

1. **Enable Debug Logging:**
```python
import logging
logging.getLogger("src.api.services.mcp").setLevel(logging.DEBUG)
```

2. **Check Service Status:**
```python
# Get monitoring dashboard
dashboard = await monitoring.get_monitoring_dashboard()
print(json.dumps(dashboard, indent=2))
```

3. **Validate Configuration:**
```python
# Check adapter configuration
config = adapter.config
print(f"Adapter type: {config.adapter_type}")
print(f"Connection string: {config.connection_string}")
```

## Best Practices

### 1. Tool Design

- **Single Responsibility**: Each tool should have a single, well-defined purpose
- **Parameter Validation**: Always validate input parameters
- **Error Handling**: Implement comprehensive error handling
- **Documentation**: Provide clear descriptions and examples

### 2. Adapter Development

- **Configuration Management**: Use configuration classes for settings
- **Connection Management**: Implement proper connection lifecycle
- **Resource Cleanup**: Always clean up resources on disconnect
- **Health Monitoring**: Implement health check endpoints

### 3. Service Integration

- **Service Discovery**: Register services with the discovery system
- **Health Monitoring**: Implement health check endpoints
- **Load Balancing**: Use load balancing for high availability
- **Error Recovery**: Implement retry and fallback mechanisms

### 4. Monitoring and Logging

- **Structured Logging**: Use structured logging with consistent format
- **Metrics Collection**: Collect relevant performance metrics
- **Alert Management**: Set up appropriate alerts and thresholds
- **Dashboard Monitoring**: Use monitoring dashboards for system health

### 5. Testing

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test component interactions
- **Performance Tests**: Test system performance under load
- **End-to-End Tests**: Test complete workflows

## Conclusion

The MCP migration provides a robust, scalable, and maintainable architecture for the Warehouse Operational Assistant. By following this guide and implementing the recommended best practices, you can successfully migrate to the MCP system while maintaining system reliability and performance.

For additional support or questions, please refer to the MCP system documentation or contact the development team.
