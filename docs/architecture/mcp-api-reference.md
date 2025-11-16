# MCP API Reference

## Overview

This document provides comprehensive API reference for the Model Context Protocol (MCP) implementation in the Warehouse Operational Assistant. The MCP system provides standardized interfaces for tool discovery, execution, and communication between AI agents and external systems.

## Table of Contents

1. [MCP Server API](#mcp-server-api)
2. [MCP Client API](#mcp-client-api)
3. [Tool Discovery API](#tool-discovery-api)
4. [Tool Binding API](#tool-binding-api)
5. [Tool Routing API](#tool-routing-api)
6. [Tool Validation API](#tool-validation-api)
7. [Service Discovery API](#service-discovery-api)
8. [Monitoring API](#monitoring-api)
9. [Adapter API](#adapter-api)
10. [Error Handling](#error-handling)

## MCP Server API

### MCPServer

The MCP server provides tool registration, discovery, and execution capabilities.

#### Methods

##### `__init__(self, config: Optional[MCPServerConfig] = None)`

Initialize the MCP server.

**Parameters:**
- `config` (Optional[MCPServerConfig]): Server configuration

**Example:**
```python
from src.api.services.mcp.server import MCPServer, MCPServerConfig

config = MCPServerConfig(
    host="localhost",
    port=8000,
    max_connections=100
)
server = MCPServer(config)
```

##### `async def start(self) -> None`

Start the MCP server.

**Example:**
```python
await server.start()
```

##### `async def stop(self) -> None`

Stop the MCP server.

**Example:**
```python
await server.stop()
```

##### `async def register_tool(self, tool: MCPTool) -> bool`

Register a tool with the server.

**Parameters:**
- `tool` (MCPTool): Tool to register

**Returns:**
- `bool`: True if registration successful

**Example:**
```python
tool = MCPTool(
    name="get_inventory",
    description="Get inventory levels",
    tool_type=MCPToolType.FUNCTION,
    parameters={
        "item_id": {"type": "string", "required": True}
    },
    handler=inventory_handler
)

success = await server.register_tool(tool)
```

##### `async def unregister_tool(self, tool_name: str) -> bool`

Unregister a tool from the server.

**Parameters:**
- `tool_name` (str): Name of tool to unregister

**Returns:**
- `bool`: True if unregistration successful

**Example:**
```python
success = await server.unregister_tool("get_inventory")
```

##### `async def discover_tools(self, category: Optional[str] = None) -> List[MCPTool]`

Discover available tools.

**Parameters:**
- `category` (Optional[str]): Tool category filter

**Returns:**
- `List[MCPTool]`: List of available tools

**Example:**
```python
# Get all tools
tools = await server.discover_tools()

# Get tools by category
inventory_tools = await server.discover_tools("inventory")
```

##### `async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> MCPToolResult`

Execute a tool with given arguments.

**Parameters:**
- `tool_name` (str): Name of tool to execute
- `arguments` (Dict[str, Any]): Tool arguments

**Returns:**
- `MCPToolResult`: Tool execution result

**Example:**
```python
result = await server.execute_tool("get_inventory", {
    "item_id": "ITEM001",
    "location": "WAREHOUSE_A"
})

if result.success:
    print(f"Result: {result.data}")
else:
    print(f"Error: {result.error}")
```

##### `async def get_tool_info(self, tool_name: str) -> Optional[MCPTool]`

Get information about a specific tool.

**Parameters:**
- `tool_name` (str): Name of tool

**Returns:**
- `Optional[MCPTool]`: Tool information or None

**Example:**
```python
tool_info = await server.get_tool_info("get_inventory")
if tool_info:
    print(f"Tool: {tool_info.name}")
    print(f"Description: {tool_info.description}")
```

##### `async def get_server_status(self) -> Dict[str, Any]`

Get server status and statistics.

**Returns:**
- `Dict[str, Any]`: Server status information

**Example:**
```python
status = await server.get_server_status()
print(f"Server running: {status['running']}")
print(f"Tools registered: {status['tools_count']}")
print(f"Active connections: {status['active_connections']}")
```

### MCPTool

Tool definition class.

#### Properties

- `name` (str): Tool name
- `description` (str): Tool description
- `tool_type` (MCPToolType): Tool type
- `parameters` (Dict[str, Any]): Tool parameters schema
- `handler` (Callable): Tool execution handler
- `category` (Optional[str]): Tool category
- `tags` (List[str]): Tool tags
- `version` (str): Tool version

#### Example

```python
from src.api.services.mcp.server import MCPTool, MCPToolType

tool = MCPTool(
    name="get_inventory",
    description="Get inventory levels for a specific item",
    tool_type=MCPToolType.FUNCTION,
    parameters={
        "item_id": {
            "type": "string",
            "description": "Item identifier",
            "required": True
        },
        "location": {
            "type": "string",
            "description": "Warehouse location",
            "required": False
        }
    },
    handler=inventory_handler,
    category="inventory",
    tags=["inventory", "warehouse"],
    version="1.0.0"
)
```

### MCPToolResult

Tool execution result.

#### Properties

- `success` (bool): Execution success status
- `data` (Any): Execution result data
- `error` (Optional[str]): Error message if failed
- `execution_time` (float): Execution time in seconds
- `metadata` (Dict[str, Any]): Additional metadata

#### Example

```python
result = MCPToolResult(
    success=True,
    data={"item_id": "ITEM001", "quantity": 100},
    execution_time=0.5,
    metadata={"source": "inventory_system"}
)
```

## MCP Client API

### MCPClient

The MCP client enables communication with MCP servers.

#### Methods

##### `__init__(self, config: Optional[MCPClientConfig] = None)`

Initialize the MCP client.

**Parameters:**
- `config` (Optional[MCPClientConfig]): Client configuration

**Example:**
```python
from src.api.services.mcp.client import MCPClient, MCPClientConfig

config = MCPClientConfig(
    timeout=30,
    retry_attempts=3
)
client = MCPClient(config)
```

##### `async def connect(self, server_url: str, connection_type: MCPConnectionType) -> bool`

Connect to an MCP server.

**Parameters:**
- `server_url` (str): Server URL
- `connection_type` (MCPConnectionType): Connection type

**Returns:**
- `bool`: True if connection successful

**Example:**
```python
from src.api.services.mcp.client import MCPConnectionType

success = await client.connect("http://localhost:8000", MCPConnectionType.HTTP)
```

##### `async def disconnect(self) -> None`

Disconnect from the server.

**Example:**
```python
await client.disconnect()
```

##### `async def discover_tools(self, category: Optional[str] = None) -> List[MCPTool]`

Discover available tools on the server.

**Parameters:**
- `category` (Optional[str]): Tool category filter

**Returns:**
- `List[MCPTool]`: List of available tools

**Example:**
```python
tools = await client.discover_tools("inventory")
```

##### `async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> MCPToolResult`

Execute a tool on the server.

**Parameters:**
- `tool_name` (str): Name of tool to execute
- `arguments` (Dict[str, Any]): Tool arguments

**Returns:**
- `MCPToolResult`: Tool execution result

**Example:**
```python
result = await client.execute_tool("get_inventory", {
    "item_id": "ITEM001"
})
```

##### `async def get_tool_info(self, tool_name: str) -> Optional[MCPTool]`

Get information about a specific tool.

**Parameters:**
- `tool_name` (str): Name of tool

**Returns:**
- `Optional[MCPTool]`: Tool information or None

**Example:**
```python
tool_info = await client.get_tool_info("get_inventory")
```

##### `async def get_server_status(self) -> Dict[str, Any]`

Get server status.

**Returns:**
- `Dict[str, Any]`: Server status information

**Example:**
```python
status = await client.get_server_status()
```

## Tool Discovery API

### ToolDiscoveryService

Dynamic tool discovery and registration service.

#### Methods

##### `__init__(self, config: Optional[ToolDiscoveryConfig] = None)`

Initialize the tool discovery service.

**Parameters:**
- `config` (Optional[ToolDiscoveryConfig]): Discovery configuration

**Example:**
```python
from src.api.services.mcp.tool_discovery import ToolDiscoveryService, ToolDiscoveryConfig

config = ToolDiscoveryConfig(
    discovery_interval=30,
    max_tools_per_source=100
)
discovery = ToolDiscoveryService(config)
```

##### `async def start_discovery(self) -> None`

Start the tool discovery process.

**Example:**
```python
await discovery.start_discovery()
```

##### `async def stop_discovery(self) -> None`

Stop the tool discovery process.

**Example:**
```python
await discovery.stop_discovery()
```

##### `async def register_discovery_source(self, source_id: str, source: Any, source_type: str) -> bool`

Register a discovery source.

**Parameters:**
- `source_id` (str): Unique source identifier
- `source` (Any): Source object
- `source_type` (str): Type of source

**Returns:**
- `bool`: True if registration successful

**Example:**
```python
success = await discovery.register_discovery_source(
    "erp_adapter",
    erp_adapter,
    "mcp_adapter"
)
```

##### `async def unregister_discovery_source(self, source_id: str) -> bool`

Unregister a discovery source.

**Parameters:**
- `source_id` (str): Source identifier

**Returns:**
- `bool`: True if unregistration successful

**Example:**
```python
success = await discovery.unregister_discovery_source("erp_adapter")
```

##### `async def search_tools(self, query: str, category: Optional[str] = None) -> List[DiscoveredTool]`

Search for tools using a query.

**Parameters:**
- `query` (str): Search query
- `category` (Optional[str]): Tool category filter

**Returns:**
- `List[DiscoveredTool]`: List of discovered tools

**Example:**
```python
tools = await discovery.search_tools("inventory", "warehouse")
```

##### `async def get_tools_by_category(self, category: ToolCategory) -> List[DiscoveredTool]`

Get tools by category.

**Parameters:**
- `category` (ToolCategory): Tool category

**Returns:**
- `List[DiscoveredTool]`: List of tools in category

**Example:**
```python
from src.api.services.mcp.tool_discovery import ToolCategory

inventory_tools = await discovery.get_tools_by_category(ToolCategory.INVENTORY)
```

##### `async def get_tool_usage_stats(self, tool_name: str) -> Dict[str, Any]`

Get tool usage statistics.

**Parameters:**
- `tool_name` (str): Tool name

**Returns:**
- `Dict[str, Any]`: Usage statistics

**Example:**
```python
stats = await discovery.get_tool_usage_stats("get_inventory")
print(f"Usage count: {stats['usage_count']}")
print(f"Average execution time: {stats['avg_execution_time']}")
```

## Tool Binding API

### ToolBindingService

Dynamic tool binding and execution framework.

#### Methods

##### `__init__(self, discovery_service: ToolDiscoveryService, config: Optional[ToolBindingConfig] = None)`

Initialize the tool binding service.

**Parameters:**
- `discovery_service` (ToolDiscoveryService): Tool discovery service
- `config` (Optional[ToolBindingConfig]): Binding configuration

**Example:**
```python
from src.api.services.mcp.tool_binding import ToolBindingService, ToolBindingConfig

config = ToolBindingConfig(
    max_tools_per_binding=10,
    binding_timeout=30
)
binding = ToolBindingService(discovery, config)
```

##### `async def bind_tools(self, agent_id: str, query: str, intent: str, entities: Dict[str, Any], context: Dict[str, Any], strategy: BindingStrategy = BindingStrategy.SEMANTIC_MATCH, max_tools: int = 5) -> List[ToolBinding]`

Bind tools to an agent based on query and context.

**Parameters:**
- `agent_id` (str): Agent identifier
- `query` (str): User query
- `intent` (str): Query intent
- `entities` (Dict[str, Any]): Extracted entities
- `context` (Dict[str, Any]): Execution context
- `strategy` (BindingStrategy): Binding strategy
- `max_tools` (int): Maximum number of tools to bind

**Returns:**
- `List[ToolBinding]`: List of tool bindings

**Example:**
```python
from src.api.services.mcp.tool_binding import BindingStrategy

bindings = await binding.bind_tools(
    agent_id="equipment_agent",
    query="Get equipment status",
    intent="equipment_lookup",
    entities={"equipment_id": "EQ001"},
    context={},
    strategy=BindingStrategy.SEMANTIC_MATCH,
    max_tools=5
)
```

##### `async def create_execution_plan(self, context: ExecutionContext, bindings: List[ToolBinding], mode: ExecutionMode = ExecutionMode.SEQUENTIAL) -> ExecutionPlan`

Create an execution plan for tool bindings.

**Parameters:**
- `context` (ExecutionContext): Execution context
- `bindings` (List[ToolBinding]): Tool bindings
- `mode` (ExecutionMode): Execution mode

**Returns:**
- `ExecutionPlan`: Execution plan

**Example:**
```python
from src.api.services.mcp.tool_binding import ExecutionMode

plan = await binding.create_execution_plan(
    context,
    bindings,
    ExecutionMode.SEQUENTIAL
)
```

##### `async def execute_plan(self, plan: ExecutionPlan) -> List[ExecutionResult]`

Execute a tool execution plan.

**Parameters:**
- `plan` (ExecutionPlan): Execution plan

**Returns:**
- `List[ExecutionResult]`: Execution results

**Example:**
```python
results = await binding.execute_plan(plan)
```

##### `async def get_binding_history(self, agent_id: str) -> List[ToolBinding]`

Get binding history for an agent.

**Parameters:**
- `agent_id` (str): Agent identifier

**Returns:**
- `List[ToolBinding]`: Binding history

**Example:**
```python
history = await binding.get_binding_history("equipment_agent")
```

## Tool Routing API

### ToolRoutingService

Intelligent tool routing and selection.

#### Methods

##### `__init__(self, discovery_service: ToolDiscoveryService, binding_service: ToolBindingService, config: Optional[ToolRoutingConfig] = None)`

Initialize the tool routing service.

**Parameters:**
- `discovery_service` (ToolDiscoveryService): Tool discovery service
- `binding_service` (ToolBindingService): Tool binding service
- `config` (Optional[ToolRoutingConfig]): Routing configuration

**Example:**
```python
from src.api.services.mcp.tool_routing import ToolRoutingService, ToolRoutingConfig

config = ToolRoutingConfig(
    routing_timeout=30,
    max_tools_per_route=5
)
routing = ToolRoutingService(discovery, binding, config)
```

##### `async def route_tools(self, context: RoutingContext, strategy: RoutingStrategy = RoutingStrategy.BALANCED, max_tools: int = 5) -> RoutingDecision`

Route tools based on context and strategy.

**Parameters:**
- `context` (RoutingContext): Routing context
- `strategy` (RoutingStrategy): Routing strategy
- `max_tools` (int): Maximum number of tools to route

**Returns:**
- `RoutingDecision`: Routing decision

**Example:**
```python
from src.api.services.mcp.tool_routing import RoutingStrategy, RoutingContext

context = RoutingContext(
    query="Get equipment status for forklift EQ001",
    intent="equipment_lookup",
    entities={"equipment_id": "EQ001", "equipment_type": "forklift"},
    user_context={"priority": "high"},
    session_id="session_123",
    agent_id="equipment_agent"
)

decision = await routing.route_tools(
    context,
    strategy=RoutingStrategy.BALANCED,
    max_tools=5
)
```

##### `async def get_routing_stats(self) -> Dict[str, Any]`

Get routing statistics.

**Returns:**
- `Dict[str, Any]`: Routing statistics

**Example:**
```python
stats = await routing.get_routing_stats()
print(f"Total routes: {stats['total_routes']}")
print(f"Average routing time: {stats['avg_routing_time']}")
```

## Tool Validation API

### ToolValidationService

Comprehensive validation and error handling.

#### Methods

##### `__init__(self, discovery_service: ToolDiscoveryService, config: Optional[ToolValidationConfig] = None)`

Initialize the tool validation service.

**Parameters:**
- `discovery_service` (ToolDiscoveryService): Tool discovery service
- `config` (Optional[ToolValidationConfig]): Validation configuration

**Example:**
```python
from src.api.services.mcp.tool_validation import ToolValidationService, ToolValidationConfig

config = ToolValidationConfig(
    validation_timeout=30,
    strict_validation=True
)
validation = ToolValidationService(discovery, config)
```

##### `async def validate_tool_execution(self, tool_id: str, arguments: Dict[str, Any], context: Dict[str, Any], validation_level: ValidationLevel = ValidationLevel.STANDARD) -> ValidationResult`

Validate tool execution parameters and context.

**Parameters:**
- `tool_id` (str): Tool identifier
- `arguments` (Dict[str, Any]): Tool arguments
- `context` (Dict[str, Any]): Execution context
- `validation_level` (ValidationLevel): Validation level

**Returns:**
- `ValidationResult`: Validation result

**Example:**
```python
from src.api.services.mcp.tool_validation import ValidationLevel

result = await validation.validate_tool_execution(
    tool_id="get_equipment_status",
    arguments={"equipment_id": "EQ001"},
    context=execution_context,
    validation_level=ValidationLevel.STANDARD
)

if result.is_valid:
    print("Validation passed")
else:
    for error in result.errors:
        print(f"Validation error: {error}")
```

##### `async def validate_tool_capabilities(self, tool_id: str, required_capabilities: List[str]) -> ValidationResult`

Validate tool capabilities.

**Parameters:**
- `tool_id` (str): Tool identifier
- `required_capabilities` (List[str]): Required capabilities

**Returns:**
- `ValidationResult`: Validation result

**Example:**
```python
result = await validation.validate_tool_capabilities(
    tool_id="get_equipment_status",
    required_capabilities=["equipment_lookup", "status_check"]
)
```

## Service Discovery API

### ServiceDiscoveryRegistry

Service discovery and registry system.

#### Methods

##### `__init__(self, config: Optional[ServiceDiscoveryConfig] = None)`

Initialize the service discovery registry.

**Parameters:**
- `config` (Optional[ServiceDiscoveryConfig]): Discovery configuration

**Example:**
```python
from src.api.services.mcp.service_discovery import ServiceDiscoveryRegistry, ServiceDiscoveryConfig

config = ServiceDiscoveryConfig(
    registry_ttl=300,
    health_check_interval=30
)
registry = ServiceDiscoveryRegistry(config)
```

##### `async def register_service(self, service: ServiceInfo) -> bool`

Register a service with the registry.

**Parameters:**
- `service` (ServiceInfo): Service information

**Returns:**
- `bool`: True if registration successful

**Example:**
```python
from src.api.services.mcp.service_discovery import ServiceInfo, ServiceType

service = ServiceInfo(
    service_id="erp_adapter_001",
    service_name="ERP Adapter",
    service_type=ServiceType.ADAPTER,
    endpoint="http://localhost:8001",
    version="1.0.0",
    capabilities=["inventory", "orders", "customers"]
)

success = await registry.register_service(service)
```

##### `async def unregister_service(self, service_id: str) -> bool`

Unregister a service from the registry.

**Parameters:**
- `service_id` (str): Service identifier

**Returns:**
- `bool`: True if unregistration successful

**Example:**
```python
success = await registry.unregister_service("erp_adapter_001")
```

##### `async def discover_services(self, service_type: Optional[ServiceType] = None, capabilities: Optional[List[str]] = None) -> List[ServiceInfo]`

Discover services by type and capabilities.

**Parameters:**
- `service_type` (Optional[ServiceType]): Service type filter
- `capabilities` (Optional[List[str]]): Required capabilities

**Returns:**
- `List[ServiceInfo]`: List of discovered services

**Example:**
```python
from src.api.services.mcp.service_discovery import ServiceType

# Discover all adapters
adapters = await registry.discover_services(ServiceType.ADAPTER)

# Discover services with specific capabilities
inventory_services = await registry.discover_services(
    capabilities=["inventory"]
)
```

##### `async def get_service_health(self, service_id: str) -> ServiceHealth`

Get service health status.

**Parameters:**
- `service_id` (str): Service identifier

**Returns:**
- `ServiceHealth`: Service health information

**Example:**
```python
health = await registry.get_service_health("erp_adapter_001")
print(f"Service healthy: {health.is_healthy}")
print(f"Last check: {health.last_check}")
```

## Monitoring API

### MCPMonitoringService

Comprehensive monitoring, logging, and management.

#### Methods

##### `__init__(self, config: Optional[MonitoringConfig] = None)`

Initialize the monitoring service.

**Parameters:**
- `config` (Optional[MonitoringConfig]): Monitoring configuration

**Example:**
```python
from src.api.services.mcp.monitoring import MCPMonitoringService, MonitoringConfig

config = MonitoringConfig(
    metrics_retention_days=30,
    alert_thresholds={
        "error_rate": 0.05,
        "response_time": 5.0
    }
)
monitoring = MCPMonitoringService(config)
```

##### `async def start_monitoring(self) -> None`

Start the monitoring service.

**Example:**
```python
await monitoring.start_monitoring()
```

##### `async def stop_monitoring(self) -> None`

Stop the monitoring service.

**Example:**
```python
await monitoring.stop_monitoring()
```

##### `async def record_metric(self, metric_name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None`

Record a metric.

**Parameters:**
- `metric_name` (str): Metric name
- `value` (float): Metric value
- `tags` (Optional[Dict[str, str]]): Metric tags

**Example:**
```python
await monitoring.record_metric(
    "tool_execution_time",
    1.5,
    {"tool_name": "get_inventory", "agent_id": "equipment_agent"}
)
```

##### `async def get_metrics(self, metric_name: Optional[str] = None, time_range: Optional[Tuple[datetime, datetime]] = None) -> List[MetricData]`

Get metrics data.

**Parameters:**
- `metric_name` (Optional[str]): Metric name filter
- `time_range` (Optional[Tuple[datetime, datetime]]): Time range filter

**Returns:**
- `List[MetricData]`: List of metric data

**Example:**
```python
from datetime import datetime, timedelta

# Get metrics for last hour
end_time = datetime.now()
start_time = end_time - timedelta(hours=1)

metrics = await monitoring.get_metrics(
    metric_name="tool_execution_time",
    time_range=(start_time, end_time)
)
```

##### `async def get_monitoring_dashboard(self) -> Dict[str, Any]`

Get monitoring dashboard data.

**Returns:**
- `Dict[str, Any]`: Dashboard data

**Example:**
```python
dashboard = await monitoring.get_monitoring_dashboard()
print(f"System health: {dashboard['system_health']}")
print(f"Active services: {dashboard['active_services']}")
```

## Adapter API

### MCPAdapter

Base class for all MCP adapters.

#### Methods

##### `__init__(self, config: AdapterConfig)`

Initialize the adapter.

**Parameters:**
- `config` (AdapterConfig): Adapter configuration

**Example:**
```python
from src.api.services.mcp.base import MCPAdapter, AdapterConfig, AdapterType

config = AdapterConfig(
    adapter_id="erp_adapter_001",
    adapter_name="ERP Adapter",
    adapter_type=AdapterType.ERP,
    connection_string="postgresql://user:pass@localhost:5432/erp",
    capabilities=["inventory", "orders", "customers"]
)

adapter = MCPAdapter(config)
```

##### `async def connect(self) -> bool`

Connect to the external system.

**Returns:**
- `bool`: True if connection successful

**Example:**
```python
success = await adapter.connect()
```

##### `async def disconnect(self) -> None`

Disconnect from the external system.

**Example:**
```python
await adapter.disconnect()
```

##### `async def health_check(self) -> bool`

Check adapter health.

**Returns:**
- `bool`: True if healthy

**Example:**
```python
healthy = await adapter.health_check()
```

##### `async def get_capabilities(self) -> List[str]`

Get adapter capabilities.

**Returns:**
- `List[str]`: List of capabilities

**Example:**
```python
capabilities = await adapter.get_capabilities()
```

## Error Handling

### MCPError

Base exception for MCP errors.

#### Properties

- `error_code` (str): Error code
- `error_message` (str): Error message
- `error_details` (Optional[Dict[str, Any]]): Additional error details

#### Example

```python
from src.api.services.mcp.base import MCPError

try:
    result = await client.execute_tool("invalid_tool", {})
except MCPError as e:
    print(f"Error code: {e.error_code}")
    print(f"Error message: {e.error_message}")
    print(f"Error details: {e.error_details}")
```

### Error Categories

- `CONNECTION_ERROR`: Connection-related errors
- `AUTHENTICATION_ERROR`: Authentication errors
- `VALIDATION_ERROR`: Validation errors
- `EXECUTION_ERROR`: Tool execution errors
- `DISCOVERY_ERROR`: Tool discovery errors
- `ROUTING_ERROR`: Tool routing errors

### Error Handling Best Practices

1. **Always handle MCPError exceptions**
2. **Check error codes for specific error types**
3. **Implement retry logic for transient errors**
4. **Log errors with appropriate context**
5. **Provide meaningful error messages to users**

## Conclusion

This API reference provides comprehensive documentation for all MCP components. For additional examples and usage patterns, refer to the MCP integration documentation and test files.
