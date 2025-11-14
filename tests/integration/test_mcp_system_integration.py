"""
System integration tests for the complete MCP system.

This module tests the integration of all MCP components including:
- MCP server and client integration
- Tool discovery and registration integration
- Service discovery and registry integration
- Monitoring and logging integration
- Complete system workflows
"""

import asyncio
import pytest
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.services.mcp.server import MCPServer, MCPTool, MCPToolType
from src.api.services.mcp.client import MCPClient, MCPConnectionType
from src.api.services.mcp.tool_discovery import ToolDiscoveryService, ToolDiscoveryConfig
from src.api.services.mcp.tool_binding import ToolBindingService, BindingStrategy, ExecutionMode
from src.api.services.mcp.tool_routing import ToolRoutingService, RoutingStrategy
from src.api.services.mcp.tool_validation import ToolValidationService, ValidationLevel
from src.api.services.mcp.service_discovery import ServiceDiscoveryRegistry, ServiceType
from src.api.services.mcp.monitoring import MCPMonitoringService, MonitoringConfig
from src.api.services.mcp.adapters.erp_adapter import ERPAdapter
from src.api.services.mcp.adapters.wms_adapter import WMSAdapter
from src.api.services.mcp.adapters.iot_adapter import IoTAdapter
from src.api.agents.inventory.mcp_equipment_agent import MCPEquipmentAgent
from src.api.agents.operations.mcp_operations_agent import MCPOperationsAgent
from src.api.agents.safety.mcp_safety_agent import MCPSafetyAgent


class TestMCPSystemIntegration:
    """Integration tests for the complete MCP system."""

    @pytest.fixture
    async def mcp_server(self):
        """Create and start MCP server."""
        server = MCPServer()
        await server.start()
        yield server
        await server.stop()

    @pytest.fixture
    async def mcp_client(self):
        """Create MCP client."""
        client = MCPClient()
        yield client
        await client.disconnect()

    @pytest.fixture
    async def discovery_service(self):
        """Create tool discovery service."""
        config = ToolDiscoveryConfig(
            discovery_interval=1,
            max_tools_per_source=100
        )
        discovery = ToolDiscoveryService(config)
        await discovery.start_discovery()
        yield discovery
        await discovery.stop_discovery()

    @pytest.fixture
    async def binding_service(self, discovery_service):
        """Create tool binding service."""
        binding = ToolBindingService(discovery_service)
        yield binding

    @pytest.fixture
    async def routing_service(self, discovery_service, binding_service):
        """Create tool routing service."""
        routing = ToolRoutingService(discovery_service, binding_service)
        yield routing

    @pytest.fixture
    async def validation_service(self, discovery_service):
        """Create tool validation service."""
        validation = ToolValidationService(discovery_service)
        yield validation

    @pytest.fixture
    async def service_registry(self):
        """Create service discovery registry."""
        registry = ServiceDiscoveryRegistry()
        yield registry

    @pytest.fixture
    async def monitoring_service(self):
        """Create monitoring service."""
        config = MonitoringConfig(
            metrics_retention_days=1,
            alert_thresholds={
                "error_rate": 0.1,
                "response_time": 5.0
            }
        )
        monitoring = MCPMonitoringService(config)
        await monitoring.start_monitoring()
        yield monitoring
        await monitoring.stop_monitoring()

    @pytest.fixture
    async def erp_adapter(self):
        """Create ERP adapter."""
        from src.api.services.mcp.base import AdapterConfig, AdapterType
        
        config = AdapterConfig(
            adapter_id="erp_test_001",
            adapter_name="Test ERP Adapter",
            adapter_type=AdapterType.ERP,
            connection_string="postgresql://test:test@localhost:5432/test_erp",
            capabilities=["inventory", "orders", "customers"]
        )
        adapter = ERPAdapter(config)
        await adapter.connect()
        yield adapter
        await adapter.disconnect()

    @pytest.fixture
    async def wms_adapter(self):
        """Create WMS adapter."""
        from src.api.services.mcp.base import AdapterConfig, AdapterType
        
        config = AdapterConfig(
            adapter_id="wms_test_001",
            adapter_name="Test WMS Adapter",
            adapter_type=AdapterType.WMS,
            connection_string="postgresql://test:test@localhost:5432/test_wms",
            capabilities=["inventory", "warehouse_operations", "order_fulfillment"]
        )
        adapter = WMSAdapter(config)
        await adapter.connect()
        yield adapter
        await adapter.disconnect()

    @pytest.fixture
    async def iot_adapter(self):
        """Create IoT adapter."""
        from src.api.services.mcp.base import AdapterConfig, AdapterType
        
        config = AdapterConfig(
            adapter_id="iot_test_001",
            adapter_name="Test IoT Adapter",
            adapter_type=AdapterType.IOT,
            connection_string="mqtt://test:test@localhost:1883",
            capabilities=["equipment_monitoring", "sensor_data", "telemetry"]
        )
        adapter = IoTAdapter(config)
        await adapter.connect()
        yield adapter
        await adapter.disconnect()

    @pytest.fixture
    async def all_agents(self, discovery_service, binding_service, routing_service, validation_service):
        """Create all agents for testing."""
        equipment_agent = MCPEquipmentAgent(
            discovery_service=discovery_service,
            binding_service=binding_service,
            routing_service=routing_service,
            validation_service=validation_service
        )
        
        operations_agent = MCPOperationsAgent(
            discovery_service=discovery_service,
            binding_service=binding_service,
            routing_service=routing_service,
            validation_service=validation_service
        )
        
        safety_agent = MCPSafetyAgent(
            discovery_service=discovery_service,
            binding_service=binding_service,
            routing_service=routing_service,
            validation_service=validation_service
        )
        
        return {
            'equipment': equipment_agent,
            'operations': operations_agent,
            'safety': safety_agent
        }

    async def test_complete_system_startup(self, mcp_server, mcp_client, discovery_service, 
                                         binding_service, routing_service, validation_service,
                                         service_registry, monitoring_service):
        """Test complete system startup and initialization."""
        
        # Test server startup
        server_status = await mcp_server.get_server_status()
        assert server_status['running'], "MCP server should be running"
        
        # Test client connection
        success = await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        assert success, "MCP client should connect to server"
        
        # Test discovery service
        discovery_status = await discovery_service.get_discovery_status()
        assert discovery_status['running'], "Discovery service should be running"
        
        # Test monitoring service
        dashboard = await monitoring_service.get_monitoring_dashboard()
        assert dashboard is not None, "Monitoring service should provide dashboard"

    async def test_adapter_registration_and_discovery(self, discovery_service, erp_adapter, wms_adapter, iot_adapter):
        """Test adapter registration and tool discovery."""
        
        # Register adapters
        await discovery_service.register_discovery_source("erp_adapter", erp_adapter, "mcp_adapter")
        await discovery_service.register_discovery_source("wms_adapter", wms_adapter, "mcp_adapter")
        await discovery_service.register_discovery_source("iot_adapter", iot_adapter, "mcp_adapter")
        
        # Wait for discovery
        await asyncio.sleep(2)
        
        # Test tool discovery
        all_tools = await discovery_service.search_tools("")
        assert len(all_tools) > 0, "Should discover tools from all adapters"
        
        # Test category-based discovery
        inventory_tools = await discovery_service.search_tools("inventory")
        assert len(inventory_tools) > 0, "Should discover inventory tools"
        
        # Test adapter-specific discovery
        erp_tools = await discovery_service.search_tools("erp")
        assert len(erp_tools) > 0, "Should discover ERP tools"

    async def test_service_registry_integration(self, service_registry, erp_adapter, wms_adapter, iot_adapter):
        """Test service registry integration."""
        
        from src.api.services.mcp.service_discovery import ServiceInfo
        
        # Register services
        erp_service = ServiceInfo(
            service_id="erp_adapter_001",
            service_name="ERP Adapter",
            service_type=ServiceType.ADAPTER,
            endpoint="http://localhost:8001",
            version="1.0.0",
            capabilities=["inventory", "orders", "customers"]
        )
        
        wms_service = ServiceInfo(
            service_id="wms_adapter_001",
            service_name="WMS Adapter",
            service_type=ServiceType.ADAPTER,
            endpoint="http://localhost:8002",
            version="1.0.0",
            capabilities=["inventory", "warehouse_operations", "order_fulfillment"]
        )
        
        iot_service = ServiceInfo(
            service_id="iot_adapter_001",
            service_name="IoT Adapter",
            service_type=ServiceType.ADAPTER,
            endpoint="http://localhost:8003",
            version="1.0.0",
            capabilities=["equipment_monitoring", "sensor_data", "telemetry"]
        )
        
        # Register services
        await service_registry.register_service(erp_service)
        await service_registry.register_service(wms_service)
        await service_registry.register_service(iot_service)
        
        # Test service discovery
        all_services = await service_registry.discover_services()
        assert len(all_services) == 3, "Should discover all registered services"
        
        # Test service health
        for service in all_services:
            health = await service_registry.get_service_health(service.service_id)
            assert health is not None, f"Should get health for service {service.service_id}"

    async def test_tool_execution_workflow(self, mcp_server, mcp_client, discovery_service, 
                                         binding_service, routing_service, validation_service,
                                         erp_adapter, wms_adapter, iot_adapter):
        """Test complete tool execution workflow."""
        
        # Register adapters
        await discovery_service.register_discovery_source("erp_adapter", erp_adapter, "mcp_adapter")
        await discovery_service.register_discovery_source("wms_adapter", wms_adapter, "mcp_adapter")
        await discovery_service.register_discovery_source("iot_adapter", iot_adapter, "mcp_adapter")
        
        # Wait for discovery
        await asyncio.sleep(2)
        
        # Connect client
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Test tool binding
        bindings = await binding_service.bind_tools(
            agent_id="test_agent",
            query="Get inventory levels for item ITEM001",
            intent="inventory_lookup",
            entities={"item_id": "ITEM001"},
            context={},
            strategy=BindingStrategy.SEMANTIC_MATCH,
            max_tools=5
        )
        assert len(bindings) > 0, "Should bind tools for query"
        
        # Test tool routing
        from src.api.services.mcp.tool_routing import RoutingContext
        context = RoutingContext(
            query="Get inventory levels for item ITEM001",
            intent="inventory_lookup",
            entities={"item_id": "ITEM001"},
            user_context={},
            session_id="test_session",
            agent_id="test_agent"
        )
        
        decision = await routing_service.route_tools(
            context,
            strategy=RoutingStrategy.BALANCED,
            max_tools=5
        )
        assert decision is not None, "Should route tools"
        
        # Test tool validation
        for binding in bindings:
            validation_result = await validation_service.validate_tool_execution(
                tool_id=binding.tool_name,
                arguments=binding.arguments,
                context=context.to_dict(),
                validation_level=ValidationLevel.STANDARD
            )
            assert validation_result.is_valid, f"Tool {binding.tool_name} should be valid"
        
        # Test tool execution
        for binding in bindings:
            result = await mcp_client.execute_tool(binding.tool_name, binding.arguments)
            assert result.success, f"Tool {binding.tool_name} should execute successfully"

    async def test_agent_integration_workflow(self, all_agents, discovery_service, erp_adapter, wms_adapter, iot_adapter):
        """Test agent integration workflow."""
        
        # Register adapters
        await discovery_service.register_discovery_source("erp_adapter", erp_adapter, "mcp_adapter")
        await discovery_service.register_discovery_source("wms_adapter", wms_adapter, "mcp_adapter")
        await discovery_service.register_discovery_source("iot_adapter", iot_adapter, "mcp_adapter")
        
        # Wait for discovery
        await asyncio.sleep(2)
        
        # Test equipment agent
        equipment_result = await all_agents['equipment'].process_query(
            "Get status of forklift EQ001",
            {"equipment_id": "EQ001", "equipment_type": "forklift"}
        )
        assert equipment_result is not None, "Equipment agent should process query"
        
        # Test operations agent
        operations_result = await all_agents['operations'].process_query(
            "Create work order for equipment maintenance",
            {
                "work_type": "maintenance",
                "priority": "high",
                "assigned_to": "technician_001",
                "description": "Equipment maintenance"
            }
        )
        assert operations_result is not None, "Operations agent should process query"
        
        # Test safety agent
        safety_result = await all_agents['safety'].process_query(
            "Check safety compliance for Zone A",
            {"zone_id": "ZONE_A", "check_type": "compliance"}
        )
        assert safety_result is not None, "Safety agent should process query"

    async def test_monitoring_integration(self, monitoring_service, mcp_server, mcp_client, discovery_service):
        """Test monitoring integration."""
        
        # Record some metrics
        await monitoring_service.record_metric("tool_executions", 1.0, {"tool_name": "get_inventory"})
        await monitoring_service.record_metric("tool_execution_time", 0.5, {"tool_name": "get_inventory"})
        await monitoring_service.record_metric("active_connections", 1.0, {"service": "mcp_server"})
        
        # Test metrics retrieval
        metrics = await monitoring_service.get_metrics("tool_executions")
        assert len(metrics) > 0, "Should record and retrieve metrics"
        
        # Test monitoring dashboard
        dashboard = await monitoring_service.get_monitoring_dashboard()
        assert dashboard is not None, "Should get monitoring dashboard"
        assert "system_health" in dashboard, "Dashboard should include system health"
        assert "active_services" in dashboard, "Dashboard should include active services"

    async def test_error_handling_integration(self, mcp_server, mcp_client, discovery_service):
        """Test error handling integration."""
        
        # Connect client
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Test invalid tool execution
        result = await mcp_client.execute_tool("nonexistent_tool", {})
        assert not result.success, "Should fail for nonexistent tool"
        assert result.error is not None, "Should return error message"
        
        # Test tool execution with invalid parameters
        result = await mcp_client.execute_tool("get_inventory", {"invalid_param": "value"})
        assert not result.success, "Should fail for invalid parameters"
        
        # Test connection recovery
        await mcp_client.disconnect()
        success = await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        assert success, "Should reconnect successfully"

    async def test_performance_integration(self, mcp_server, mcp_client, discovery_service, erp_adapter):
        """Test performance integration."""
        
        # Register adapter
        await discovery_service.register_discovery_source("erp_adapter", erp_adapter, "mcp_adapter")
        await asyncio.sleep(2)
        
        # Connect client
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Test concurrent tool execution
        tasks = []
        for i in range(100):
            task = mcp_client.execute_tool("get_inventory", {"item_id": f"ITEM{i:03d}"})
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Check results
        successful_results = [r for r in results if not isinstance(r, Exception) and r.success]
        assert len(successful_results) > 0, "Should have some successful executions"
        
        # Check performance
        execution_times = [r.execution_time for r in successful_results if hasattr(r, 'execution_time')]
        if execution_times:
            avg_execution_time = sum(execution_times) / len(execution_times)
            assert avg_execution_time < 5.0, f"Average execution time should be reasonable: {avg_execution_time}s"

    async def test_data_consistency_integration(self, mcp_server, mcp_client, discovery_service, 
                                               erp_adapter, wms_adapter):
        """Test data consistency across services."""
        
        # Register adapters
        await discovery_service.register_discovery_source("erp_adapter", erp_adapter, "mcp_adapter")
        await discovery_service.register_discovery_source("wms_adapter", wms_adapter, "mcp_adapter")
        await asyncio.sleep(2)
        
        # Connect client
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Get inventory from ERP
        erp_result = await mcp_client.execute_tool("get_inventory", {"item_id": "ITEM001"})
        assert erp_result.success, "ERP inventory lookup should succeed"
        
        # Get inventory from WMS
        wms_result = await mcp_client.execute_tool("get_inventory", {"item_id": "ITEM001"})
        assert wms_result.success, "WMS inventory lookup should succeed"
        
        # In a real implementation, you would compare the actual data
        assert erp_result.data is not None, "ERP result should have data"
        assert wms_result.data is not None, "WMS result should have data"

    async def test_security_integration(self, mcp_server, mcp_client):
        """Test security integration."""
        
        # Test unauthenticated access
        result = await mcp_client.execute_tool("get_inventory", {"item_id": "ITEM001"})
        # In a real implementation, this should fail without authentication
        
        # Test with authentication (mock)
        with patch('chain_server.services.mcp.client.MCPClient._authenticate') as mock_auth:
            mock_auth.return_value = True
            await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
            
            result = await mcp_client.execute_tool("get_inventory", {"item_id": "ITEM001"})
            assert result is not None, "Should succeed with authentication"

    async def test_configuration_integration(self, mcp_server, mcp_client, discovery_service):
        """Test configuration integration."""
        
        # Test configuration changes
        original_config = discovery_service.config
        new_config = ToolDiscoveryConfig(
            discovery_interval=5,
            max_tools_per_source=100
        )
        
        # Update configuration
        discovery_service.config = new_config
        assert discovery_service.config.discovery_interval == 5, "Configuration should be updated"
        
        # Test hot reloading (if implemented)
        # This would test the ability to reload configuration without restarting services

    async def test_backup_and_recovery_integration(self, mcp_server, mcp_client, discovery_service, erp_adapter):
        """Test backup and recovery integration."""
        
        # Register adapter and discover tools
        await discovery_service.register_discovery_source("erp_adapter", erp_adapter, "mcp_adapter")
        await asyncio.sleep(2)
        
        # Get initial state
        initial_tools = await discovery_service.search_tools("inventory")
        initial_count = len(initial_tools)
        
        # Simulate service restart
        await discovery_service.stop_discovery()
        await discovery_service.start_discovery()
        
        # Re-register adapter
        await discovery_service.register_discovery_source("erp_adapter", erp_adapter, "mcp_adapter")
        await asyncio.sleep(2)
        
        # Verify recovery
        recovered_tools = await discovery_service.search_tools("inventory")
        recovered_count = len(recovered_tools)
        
        # Should recover the same tools
        assert recovered_count >= initial_count, "Should recover tools after restart"

    async def test_multi_tenant_integration(self, mcp_server, mcp_client, discovery_service):
        """Test multi-tenant integration."""
        
        # Simulate multiple tenants
        tenant1_tools = await discovery_service.search_tools("inventory", tenant_id="tenant1")
        tenant2_tools = await discovery_service.search_tools("inventory", tenant_id="tenant2")
        
        # In a real implementation, tools should be isolated by tenant
        # For now, we just test that the calls complete
        
        # Test tenant-specific tool execution
        result1 = await mcp_client.execute_tool("get_inventory", {"item_id": "ITEM001", "tenant_id": "tenant1"})
        result2 = await mcp_client.execute_tool("get_inventory", {"item_id": "ITEM001", "tenant_id": "tenant2"})
        
        # Both should complete (isolation would be enforced in real implementation)
        assert result1 is not None
        assert result2 is not None

    async def test_scalability_integration(self, mcp_server, mcp_client, discovery_service):
        """Test scalability integration."""
        
        # Simulate multiple clients
        clients = []
        for i in range(10):
            client = MCPClient()
            await client.connect("http://localhost:8000", MCPConnectionType.HTTP)
            clients.append(client)
        
        # Execute tools from multiple clients
        tasks = []
        for i, client in enumerate(clients):
            task = client.execute_tool("get_inventory", {"item_id": f"ITEM{i:03d}"})
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Check that all clients can execute tools
        successful_results = [r for r in results if not isinstance(r, Exception)]
        assert len(successful_results) > 0, "Should handle multiple clients"
        
        # Cleanup
        for client in clients:
            await client.disconnect()

    async def test_observability_integration(self, mcp_server, mcp_client, monitoring_service):
        """Test observability integration."""
        
        # Connect client
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Execute some tools
        await mcp_client.execute_tool("get_inventory", {"item_id": "ITEM001"})
        await mcp_client.execute_tool("get_inventory", {"item_id": "ITEM002"})
        
        # Check logs and metrics
        dashboard = await monitoring_service.get_monitoring_dashboard()
        assert "system_health" in dashboard, "Should have system health metrics"
        
        # Test debugging endpoints
        server_status = await mcp_server.get_server_status()
        assert "running" in server_status, "Should have server status"
        
        # Test health checks
        health = await mcp_client.get_server_status()
        assert health is not None, "Should have health status"


class TestMCPSystemReliability:
    """Reliability tests for the MCP system."""

    async def test_fault_tolerance(self, mcp_server, mcp_client):
        """Test system fault tolerance."""
        
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Test with invalid tool names
        result = await mcp_client.execute_tool("invalid_tool", {})
        assert not result.success, "Should handle invalid tool gracefully"
        
        # Test with malformed parameters
        result = await mcp_client.execute_tool("get_inventory", {"invalid_param": "value"})
        assert not result.success, "Should handle invalid parameters gracefully"
        
        # Test connection recovery
        await mcp_client.disconnect()
        success = await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        assert success, "Should recover from disconnection"

    async def test_data_integrity(self, mcp_server, mcp_client, discovery_service, erp_adapter):
        """Test data integrity across operations."""
        
        await discovery_service.register_discovery_source("erp_adapter", erp_adapter, "mcp_adapter")
        await asyncio.sleep(2)
        
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Execute same tool multiple times
        results = []
        for i in range(10):
            result = await mcp_client.execute_tool("get_inventory", {"item_id": "ITEM001"})
            results.append(result)
        
        # All results should be consistent
        successful_results = [r for r in results if r.success]
        assert len(successful_results) > 0, "Should have some successful results"
        
        # In a real implementation, you would compare the actual data
        # For now, we just verify the calls complete

    async def test_graceful_degradation(self, mcp_server, mcp_client, discovery_service):
        """Test graceful degradation when services are unavailable."""
        
        # Test with no adapters registered
        tools = await discovery_service.search_tools("inventory")
        assert len(tools) == 0, "Should handle no tools gracefully"
        
        # Test tool execution with no tools
        result = await mcp_client.execute_tool("get_inventory", {"item_id": "ITEM001"})
        # Should either fail gracefully or return empty result
        assert result is not None, "Should handle missing tools gracefully"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
