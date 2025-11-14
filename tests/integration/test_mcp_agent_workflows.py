"""
Integration tests for MCP agent workflows.

This module tests complete agent workflows using the MCP system including:
- Equipment agent workflows
- Operations agent workflows
- Safety agent workflows
- Cross-agent collaboration
- Real-world scenario testing
"""

import asyncio
import pytest
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.services.mcp.tool_discovery import ToolDiscoveryService, ToolDiscoveryConfig
from src.api.services.mcp.tool_binding import ToolBindingService, BindingStrategy, ExecutionMode
from src.api.services.mcp.tool_routing import ToolRoutingService, RoutingStrategy
from src.api.services.mcp.tool_validation import ToolValidationService, ValidationLevel
from src.api.services.mcp.service_discovery import ServiceDiscoveryRegistry, ServiceType
from src.api.services.mcp.monitoring import MCPMonitoringService, MonitoringConfig
from src.api.agents.inventory.mcp_equipment_agent import MCPEquipmentAgent
from src.api.agents.operations.mcp_operations_agent import MCPOperationsAgent
from src.api.agents.safety.mcp_safety_agent import MCPSafetyAgent


class TestEquipmentAgentWorkflows:
    """Test equipment agent workflows using MCP system."""

    @pytest.fixture
    async def setup_mcp_services(self):
        """Setup MCP services for testing."""
        # Create services
        discovery = ToolDiscoveryService(ToolDiscoveryConfig())
        binding = ToolBindingService(discovery)
        routing = ToolRoutingService(discovery, binding)
        validation = ToolValidationService(discovery)
        monitoring = MCPMonitoringService(MonitoringConfig())
        
        # Start services
        await discovery.start_discovery()
        await monitoring.start_monitoring()
        
        yield {
            'discovery': discovery,
            'binding': binding,
            'routing': routing,
            'validation': validation,
            'monitoring': monitoring
        }
        
        # Cleanup
        await discovery.stop_discovery()
        await monitoring.stop_monitoring()

    @pytest.fixture
    async def equipment_agent(self, setup_mcp_services):
        """Create equipment agent with MCP services."""
        services = await setup_mcp_services
        agent = MCPEquipmentAgent(
            discovery_service=services['discovery'],
            binding_service=services['binding'],
            routing_service=services['routing'],
            validation_service=services['validation']
        )
        return agent

    @pytest.fixture
    async def mock_equipment_tools(self, setup_mcp_services):
        """Create mock equipment tools for testing."""
        from src.api.services.mcp.server import MCPTool, MCPToolType
        
        services = await setup_mcp_services
        discovery = services['discovery']
        
        # Create mock adapter with equipment tools
        mock_adapter = MagicMock()
        mock_adapter.get_tools.return_value = [
            MCPTool(
                name="get_equipment_status",
                description="Get status of equipment",
                tool_type=MCPToolType.FUNCTION,
                parameters={
                    "equipment_id": {"type": "string", "required": True},
                    "include_history": {"type": "boolean", "required": False}
                },
                handler=AsyncMock(return_value={
                    "equipment_id": "EQ001",
                    "status": "operational",
                    "last_maintenance": "2024-01-15",
                    "next_maintenance": "2024-02-15",
                    "location": "Zone A"
                })
            ),
            MCPTool(
                name="schedule_maintenance",
                description="Schedule maintenance for equipment",
                tool_type=MCPToolType.FUNCTION,
                parameters={
                    "equipment_id": {"type": "string", "required": True},
                    "maintenance_type": {"type": "string", "required": True},
                    "scheduled_date": {"type": "string", "required": True}
                },
                handler=AsyncMock(return_value={
                    "maintenance_id": "MNT001",
                    "equipment_id": "EQ001",
                    "scheduled_date": "2024-02-15",
                    "status": "scheduled"
                })
            ),
            MCPTool(
                name="get_equipment_history",
                description="Get maintenance history for equipment",
                tool_type=MCPToolType.FUNCTION,
                parameters={
                    "equipment_id": {"type": "string", "required": True},
                    "start_date": {"type": "string", "required": False},
                    "end_date": {"type": "string", "required": False}
                },
                handler=AsyncMock(return_value={
                    "equipment_id": "EQ001",
                    "maintenance_records": [
                        {"date": "2024-01-15", "type": "preventive", "status": "completed"},
                        {"date": "2024-01-01", "type": "repair", "status": "completed"}
                    ]
                })
            ),
            MCPTool(
                name="update_equipment_location",
                description="Update equipment location",
                tool_type=MCPToolType.FUNCTION,
                parameters={
                    "equipment_id": {"type": "string", "required": True},
                    "new_location": {"type": "string", "required": True}
                },
                handler=AsyncMock(return_value={
                    "equipment_id": "EQ001",
                    "old_location": "Zone A",
                    "new_location": "Zone B",
                    "updated_at": "2024-01-20T10:30:00Z"
                })
            )
        ]
        
        # Register adapter
        await discovery.register_discovery_source("equipment_adapter", mock_adapter, "mcp_adapter")
        await asyncio.sleep(1)  # Allow discovery to run
        
        return mock_adapter

    async def test_equipment_status_check_workflow(self, equipment_agent, mock_equipment_tools):
        """Test equipment status check workflow."""
        
        # Test query
        query = "What is the status of forklift EQ001?"
        context = {
            "equipment_id": "EQ001",
            "equipment_type": "forklift",
            "user_id": "operator_001"
        }
        
        # Process query
        result = await equipment_agent.process_query(query, context)
        
        # Verify result
        assert result is not None, "Should return a result"
        assert "equipment_id" in result, "Should include equipment ID"
        assert "status" in result, "Should include equipment status"
        assert result["equipment_id"] == "EQ001", "Should return correct equipment ID"
        assert result["status"] == "operational", "Should return operational status"

    async def test_equipment_maintenance_scheduling_workflow(self, equipment_agent, mock_equipment_tools):
        """Test equipment maintenance scheduling workflow."""
        
        # Test query
        query = "Schedule preventive maintenance for forklift EQ001 on February 15th"
        context = {
            "equipment_id": "EQ001",
            "equipment_type": "forklift",
            "maintenance_type": "preventive",
            "scheduled_date": "2024-02-15",
            "user_id": "maintenance_001"
        }
        
        # Process query
        result = await equipment_agent.process_query(query, context)
        
        # Verify result
        assert result is not None, "Should return a result"
        assert "maintenance_id" in result, "Should include maintenance ID"
        assert "equipment_id" in result, "Should include equipment ID"
        assert result["equipment_id"] == "EQ001", "Should return correct equipment ID"
        assert result["scheduled_date"] == "2024-02-15", "Should return correct scheduled date"

    async def test_equipment_history_workflow(self, equipment_agent, mock_equipment_tools):
        """Test equipment maintenance history workflow."""
        
        # Test query
        query = "Show me the maintenance history for forklift EQ001"
        context = {
            "equipment_id": "EQ001",
            "equipment_type": "forklift",
            "user_id": "operator_001"
        }
        
        # Process query
        result = await equipment_agent.process_query(query, context)
        
        # Verify result
        assert result is not None, "Should return a result"
        assert "equipment_id" in result, "Should include equipment ID"
        assert "maintenance_records" in result, "Should include maintenance records"
        assert result["equipment_id"] == "EQ001", "Should return correct equipment ID"
        assert len(result["maintenance_records"]) > 0, "Should have maintenance records"

    async def test_equipment_location_update_workflow(self, equipment_agent, mock_equipment_tools):
        """Test equipment location update workflow."""
        
        # Test query
        query = "Move forklift EQ001 from Zone A to Zone B"
        context = {
            "equipment_id": "EQ001",
            "equipment_type": "forklift",
            "old_location": "Zone A",
            "new_location": "Zone B",
            "user_id": "operator_001"
        }
        
        # Process query
        result = await equipment_agent.process_query(query, context)
        
        # Verify result
        assert result is not None, "Should return a result"
        assert "equipment_id" in result, "Should include equipment ID"
        assert "old_location" in result, "Should include old location"
        assert "new_location" in result, "Should include new location"
        assert result["equipment_id"] == "EQ001", "Should return correct equipment ID"
        assert result["old_location"] == "Zone A", "Should return correct old location"
        assert result["new_location"] == "Zone B", "Should return correct new location"

    async def test_equipment_workflow_with_validation(self, equipment_agent, mock_equipment_tools, setup_mcp_services):
        """Test equipment workflow with tool validation."""
        
        services = await setup_mcp_services
        validation = services['validation']
        
        # Test query with validation
        query = "Get status of equipment EQ001"
        context = {
            "equipment_id": "EQ001",
            "equipment_type": "forklift",
            "user_id": "operator_001"
        }
        
        # Process query
        result = await equipment_agent.process_query(query, context)
        
        # Verify result
        assert result is not None, "Should return a result"
        
        # Verify validation was performed
        # In a real implementation, you would check validation logs or metrics
        assert "equipment_id" in result, "Should include equipment ID"

    async def test_equipment_workflow_error_handling(self, equipment_agent, mock_equipment_tools):
        """Test equipment workflow error handling."""
        
        # Test with invalid equipment ID
        query = "Get status of equipment INVALID_ID"
        context = {
            "equipment_id": "INVALID_ID",
            "equipment_type": "forklift",
            "user_id": "operator_001"
        }
        
        # Process query
        result = await equipment_agent.process_query(query, context)
        
        # Should handle error gracefully
        assert result is not None, "Should return a result even for invalid equipment"
        # In a real implementation, you would check for error indicators

    async def test_equipment_workflow_performance(self, equipment_agent, mock_equipment_tools):
        """Test equipment workflow performance."""
        
        # Test multiple queries
        queries = [
            "Get status of forklift EQ001",
            "Schedule maintenance for forklift EQ002",
            "Show history for forklift EQ003",
            "Move forklift EQ004 to Zone C"
        ]
        
        start_time = datetime.utcnow()
        
        # Process queries concurrently
        tasks = []
        for i, query in enumerate(queries):
            context = {
                "equipment_id": f"EQ00{i+1}",
                "equipment_type": "forklift",
                "user_id": "operator_001"
            }
            task = equipment_agent.process_query(query, context)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        end_time = datetime.utcnow()
        execution_time = (end_time - start_time).total_seconds()
        
        # Verify results
        assert len(results) == len(queries), "Should process all queries"
        assert all(result is not None for result in results), "All queries should return results"
        assert execution_time < 5.0, f"Should complete within reasonable time: {execution_time:.2f}s"


class TestOperationsAgentWorkflows:
    """Test operations agent workflows using MCP system."""

    @pytest.fixture
    async def setup_mcp_services(self):
        """Setup MCP services for testing."""
        discovery = ToolDiscoveryService(ToolDiscoveryConfig())
        binding = ToolBindingService(discovery)
        routing = ToolRoutingService(discovery, binding)
        validation = ToolValidationService(discovery)
        monitoring = MCPMonitoringService(MonitoringConfig())
        
        await discovery.start_discovery()
        await monitoring.start_monitoring()
        
        yield {
            'discovery': discovery,
            'binding': binding,
            'routing': routing,
            'validation': validation,
            'monitoring': monitoring
        }
        
        await discovery.stop_discovery()
        await monitoring.stop_monitoring()

    @pytest.fixture
    async def operations_agent(self, setup_mcp_services):
        """Create operations agent with MCP services."""
        services = await setup_mcp_services
        agent = MCPOperationsAgent(
            discovery_service=services['discovery'],
            binding_service=services['binding'],
            routing_service=services['routing'],
            validation_service=services['validation']
        )
        return agent

    @pytest.fixture
    async def mock_operations_tools(self, setup_mcp_services):
        """Create mock operations tools for testing."""
        from src.api.services.mcp.server import MCPTool, MCPToolType
        
        services = await setup_mcp_services
        discovery = services['discovery']
        
        # Create mock adapter with operations tools
        mock_adapter = MagicMock()
        mock_adapter.get_tools.return_value = [
            MCPTool(
                name="create_work_order",
                description="Create a new work order",
                tool_type=MCPToolType.FUNCTION,
                parameters={
                    "work_type": {"type": "string", "required": True},
                    "priority": {"type": "string", "required": True},
                    "assigned_to": {"type": "string", "required": True},
                    "description": {"type": "string", "required": True}
                },
                handler=AsyncMock(return_value={
                    "work_order_id": "WO001",
                    "work_type": "maintenance",
                    "priority": "high",
                    "assigned_to": "technician_001",
                    "status": "created"
                })
            ),
            MCPTool(
                name="schedule_operation",
                description="Schedule a warehouse operation",
                tool_type=MCPToolType.FUNCTION,
                parameters={
                    "operation_type": {"type": "string", "required": True},
                    "scheduled_time": {"type": "string", "required": True},
                    "resources": {"type": "array", "required": True}
                },
                handler=AsyncMock(return_value={
                    "operation_id": "OP001",
                    "operation_type": "picking",
                    "scheduled_time": "2024-01-20T14:00:00Z",
                    "status": "scheduled"
                })
            ),
            MCPTool(
                name="optimize_workflow",
                description="Optimize warehouse workflow",
                tool_type=MCPToolType.FUNCTION,
                parameters={
                    "workflow_type": {"type": "string", "required": True},
                    "constraints": {"type": "object", "required": False}
                },
                handler=AsyncMock(return_value={
                    "optimization_id": "OPT001",
                    "workflow_type": "picking",
                    "improvements": ["reduced_travel_time", "better_sequencing"],
                    "efficiency_gain": 15.5
                })
            ),
            MCPTool(
                name="get_workload_status",
                description="Get current workload status",
                tool_type=MCPToolType.FUNCTION,
                parameters={
                    "department": {"type": "string", "required": False},
                    "time_range": {"type": "string", "required": False}
                },
                handler=AsyncMock(return_value={
                    "total_work_orders": 25,
                    "completed_today": 18,
                    "in_progress": 7,
                    "overdue": 2,
                    "efficiency": 85.2
                })
            )
        ]
        
        # Register adapter
        await discovery.register_discovery_source("operations_adapter", mock_adapter, "mcp_adapter")
        await asyncio.sleep(1)
        
        return mock_adapter

    async def test_work_order_creation_workflow(self, operations_agent, mock_operations_tools):
        """Test work order creation workflow."""
        
        query = "Create a high priority maintenance work order for forklift EQ001"
        context = {
            "work_type": "maintenance",
            "priority": "high",
            "assigned_to": "technician_001",
            "description": "Forklift EQ001 maintenance",
            "user_id": "supervisor_001"
        }
        
        result = await operations_agent.process_query(query, context)
        
        assert result is not None, "Should return a result"
        assert "work_order_id" in result, "Should include work order ID"
        assert result["work_type"] == "maintenance", "Should return correct work type"
        assert result["priority"] == "high", "Should return correct priority"

    async def test_operation_scheduling_workflow(self, operations_agent, mock_operations_tools):
        """Test operation scheduling workflow."""
        
        query = "Schedule a picking operation for tomorrow at 2 PM"
        context = {
            "operation_type": "picking",
            "scheduled_time": "2024-01-21T14:00:00Z",
            "resources": ["picker_001", "forklift_EQ001"],
            "user_id": "supervisor_001"
        }
        
        result = await operations_agent.process_query(query, context)
        
        assert result is not None, "Should return a result"
        assert "operation_id" in result, "Should include operation ID"
        assert result["operation_type"] == "picking", "Should return correct operation type"
        assert result["scheduled_time"] == "2024-01-21T14:00:00Z", "Should return correct scheduled time"

    async def test_workflow_optimization_workflow(self, operations_agent, mock_operations_tools):
        """Test workflow optimization workflow."""
        
        query = "Optimize the picking workflow to improve efficiency"
        context = {
            "workflow_type": "picking",
            "constraints": {"max_travel_time": 30, "resource_availability": "limited"},
            "user_id": "supervisor_001"
        }
        
        result = await operations_agent.process_query(query, context)
        
        assert result is not None, "Should return a result"
        assert "optimization_id" in result, "Should include optimization ID"
        assert "improvements" in result, "Should include improvements"
        assert "efficiency_gain" in result, "Should include efficiency gain"

    async def test_workload_status_workflow(self, operations_agent, mock_operations_tools):
        """Test workload status workflow."""
        
        query = "What is the current workload status for the warehouse?"
        context = {
            "department": "warehouse",
            "time_range": "today",
            "user_id": "supervisor_001"
        }
        
        result = await operations_agent.process_query(query, context)
        
        assert result is not None, "Should return a result"
        assert "total_work_orders" in result, "Should include total work orders"
        assert "completed_today" in result, "Should include completed today"
        assert "efficiency" in result, "Should include efficiency metric"


class TestSafetyAgentWorkflows:
    """Test safety agent workflows using MCP system."""

    @pytest.fixture
    async def setup_mcp_services(self):
        """Setup MCP services for testing."""
        discovery = ToolDiscoveryService(ToolDiscoveryConfig())
        binding = ToolBindingService(discovery)
        routing = ToolRoutingService(discovery, binding)
        validation = ToolValidationService(discovery)
        monitoring = MCPMonitoringService(MonitoringConfig())
        
        await discovery.start_discovery()
        await monitoring.start_monitoring()
        
        yield {
            'discovery': discovery,
            'binding': binding,
            'routing': routing,
            'validation': validation,
            'monitoring': monitoring
        }
        
        await discovery.stop_discovery()
        await monitoring.stop_monitoring()

    @pytest.fixture
    async def safety_agent(self, setup_mcp_services):
        """Create safety agent with MCP services."""
        services = await setup_mcp_services
        agent = MCPSafetyAgent(
            discovery_service=services['discovery'],
            binding_service=services['binding'],
            routing_service=services['routing'],
            validation_service=services['validation']
        )
        return agent

    @pytest.fixture
    async def mock_safety_tools(self, setup_mcp_services):
        """Create mock safety tools for testing."""
        from src.api.services.mcp.server import MCPTool, MCPToolType
        
        services = await setup_mcp_services
        discovery = services['discovery']
        
        # Create mock adapter with safety tools
        mock_adapter = MagicMock()
        mock_adapter.get_tools.return_value = [
            MCPTool(
                name="check_safety_compliance",
                description="Check safety compliance for an area",
                tool_type=MCPToolType.FUNCTION,
                parameters={
                    "zone_id": {"type": "string", "required": True},
                    "check_type": {"type": "string", "required": True}
                },
                handler=AsyncMock(return_value={
                    "zone_id": "ZONE_A",
                    "check_type": "compliance",
                    "status": "compliant",
                    "issues_found": 0,
                    "last_check": "2024-01-20T10:00:00Z"
                })
            ),
            MCPTool(
                name="report_safety_incident",
                description="Report a safety incident",
                tool_type=MCPToolType.FUNCTION,
                parameters={
                    "incident_type": {"type": "string", "required": True},
                    "location": {"type": "string", "required": True},
                    "severity": {"type": "string", "required": True},
                    "description": {"type": "string", "required": True}
                },
                handler=AsyncMock(return_value={
                    "incident_id": "INC001",
                    "incident_type": "near_miss",
                    "location": "Zone A",
                    "severity": "low",
                    "status": "reported"
                })
            ),
            MCPTool(
                name="schedule_safety_training",
                description="Schedule safety training",
                tool_type=MCPToolType.FUNCTION,
                parameters={
                    "training_type": {"type": "string", "required": True},
                    "participants": {"type": "array", "required": True},
                    "scheduled_date": {"type": "string", "required": True}
                },
                handler=AsyncMock(return_value={
                    "training_id": "TRN001",
                    "training_type": "forklift_safety",
                    "participants": ["operator_001", "operator_002"],
                    "scheduled_date": "2024-01-25T09:00:00Z",
                    "status": "scheduled"
                })
            ),
            MCPTool(
                name="get_safety_metrics",
                description="Get safety metrics and statistics",
                tool_type=MCPToolType.FUNCTION,
                parameters={
                    "time_period": {"type": "string", "required": False},
                    "department": {"type": "string", "required": False}
                },
                handler=AsyncMock(return_value={
                    "time_period": "last_30_days",
                    "total_incidents": 3,
                    "incidents_by_severity": {"low": 2, "medium": 1, "high": 0},
                    "compliance_rate": 95.5,
                    "training_completion": 88.2
                })
            )
        ]
        
        # Register adapter
        await discovery.register_discovery_source("safety_adapter", mock_adapter, "mcp_adapter")
        await asyncio.sleep(1)
        
        return mock_adapter

    async def test_safety_compliance_check_workflow(self, safety_agent, mock_safety_tools):
        """Test safety compliance check workflow."""
        
        query = "Check safety compliance for Zone A"
        context = {
            "zone_id": "ZONE_A",
            "check_type": "compliance",
            "user_id": "safety_inspector_001"
        }
        
        result = await safety_agent.process_query(query, context)
        
        assert result is not None, "Should return a result"
        assert "zone_id" in result, "Should include zone ID"
        assert "status" in result, "Should include compliance status"
        assert result["zone_id"] == "ZONE_A", "Should return correct zone ID"
        assert result["status"] == "compliant", "Should return compliant status"

    async def test_safety_incident_reporting_workflow(self, safety_agent, mock_safety_tools):
        """Test safety incident reporting workflow."""
        
        query = "Report a near miss incident in Zone A involving forklift EQ001"
        context = {
            "incident_type": "near_miss",
            "location": "Zone A",
            "severity": "low",
            "description": "Forklift EQ001 near miss with pedestrian",
            "user_id": "operator_001"
        }
        
        result = await safety_agent.process_query(query, context)
        
        assert result is not None, "Should return a result"
        assert "incident_id" in result, "Should include incident ID"
        assert result["incident_type"] == "near_miss", "Should return correct incident type"
        assert result["severity"] == "low", "Should return correct severity"

    async def test_safety_training_scheduling_workflow(self, safety_agent, mock_safety_tools):
        """Test safety training scheduling workflow."""
        
        query = "Schedule forklift safety training for operators on January 25th"
        context = {
            "training_type": "forklift_safety",
            "participants": ["operator_001", "operator_002"],
            "scheduled_date": "2024-01-25T09:00:00Z",
            "user_id": "safety_coordinator_001"
        }
        
        result = await safety_agent.process_query(query, context)
        
        assert result is not None, "Should return a result"
        assert "training_id" in result, "Should include training ID"
        assert result["training_type"] == "forklift_safety", "Should return correct training type"
        assert len(result["participants"]) == 2, "Should include correct number of participants"

    async def test_safety_metrics_workflow(self, safety_agent, mock_safety_tools):
        """Test safety metrics workflow."""
        
        query = "Show me safety metrics for the last 30 days"
        context = {
            "time_period": "last_30_days",
            "department": "warehouse",
            "user_id": "safety_manager_001"
        }
        
        result = await safety_agent.process_query(query, context)
        
        assert result is not None, "Should return a result"
        assert "total_incidents" in result, "Should include total incidents"
        assert "compliance_rate" in result, "Should include compliance rate"
        assert "training_completion" in result, "Should include training completion"


class TestCrossAgentCollaboration:
    """Test cross-agent collaboration workflows."""

    @pytest.fixture
    async def setup_mcp_services(self):
        """Setup MCP services for testing."""
        discovery = ToolDiscoveryService(ToolDiscoveryConfig())
        binding = ToolBindingService(discovery)
        routing = ToolRoutingService(discovery, binding)
        validation = ToolValidationService(discovery)
        monitoring = MCPMonitoringService(MonitoringConfig())
        
        await discovery.start_discovery()
        await monitoring.start_monitoring()
        
        yield {
            'discovery': discovery,
            'binding': binding,
            'routing': routing,
            'validation': validation,
            'monitoring': monitoring
        }
        
        await discovery.stop_discovery()
        await monitoring.stop_monitoring()

    @pytest.fixture
    async def all_agents(self, setup_mcp_services):
        """Create all agents for cross-agent testing."""
        services = await setup_mcp_services
        
        equipment_agent = MCPEquipmentAgent(
            discovery_service=services['discovery'],
            binding_service=services['binding'],
            routing_service=services['routing'],
            validation_service=services['validation']
        )
        
        operations_agent = MCPOperationsAgent(
            discovery_service=services['discovery'],
            binding_service=services['binding'],
            routing_service=services['routing'],
            validation_service=services['validation']
        )
        
        safety_agent = MCPSafetyAgent(
            discovery_service=services['discovery'],
            binding_service=services['binding'],
            routing_service=services['routing'],
            validation_service=services['validation']
        )
        
        return {
            'equipment': equipment_agent,
            'operations': operations_agent,
            'safety': safety_agent
        }

    async def test_equipment_maintenance_safety_workflow(self, all_agents):
        """Test workflow involving equipment, operations, and safety agents."""
        
        # Step 1: Equipment agent checks equipment status
        equipment_result = await all_agents['equipment'].process_query(
            "Check status of forklift EQ001",
            {"equipment_id": "EQ001", "equipment_type": "forklift"}
        )
        
        # Step 2: Safety agent checks safety compliance
        safety_result = await all_agents['safety'].process_query(
            "Check safety compliance for Zone A before maintenance",
            {"zone_id": "ZONE_A", "check_type": "compliance"}
        )
        
        # Step 3: Operations agent schedules maintenance
        operations_result = await all_agents['operations'].process_query(
            "Schedule maintenance for forklift EQ001",
            {
                "work_type": "maintenance",
                "priority": "high",
                "assigned_to": "technician_001",
                "description": "Forklift EQ001 maintenance"
            }
        )
        
        # Verify all agents processed successfully
        assert equipment_result is not None, "Equipment agent should process query"
        assert safety_result is not None, "Safety agent should process query"
        assert operations_result is not None, "Operations agent should process query"

    async def test_incident_response_workflow(self, all_agents):
        """Test incident response workflow involving multiple agents."""
        
        # Step 1: Safety agent reports incident
        safety_result = await all_agents['safety'].process_query(
            "Report safety incident in Zone B",
            {
                "incident_type": "equipment_malfunction",
                "location": "Zone B",
                "severity": "medium",
                "description": "Forklift EQ002 malfunction"
            }
        )
        
        # Step 2: Equipment agent checks equipment status
        equipment_result = await all_agents['equipment'].process_query(
            "Check status of forklift EQ002",
            {"equipment_id": "EQ002", "equipment_type": "forklift"}
        )
        
        # Step 3: Operations agent creates work order
        operations_result = await all_agents['operations'].process_query(
            "Create urgent work order for forklift EQ002 repair",
            {
                "work_type": "repair",
                "priority": "urgent",
                "assigned_to": "technician_002",
                "description": "Forklift EQ002 repair due to malfunction"
            }
        )
        
        # Verify all agents processed successfully
        assert safety_result is not None, "Safety agent should process incident"
        assert equipment_result is not None, "Equipment agent should check equipment"
        assert operations_result is not None, "Operations agent should create work order"

    async def test_workflow_optimization_workflow(self, all_agents):
        """Test workflow optimization involving multiple agents."""
        
        # Step 1: Operations agent gets workload status
        operations_result = await all_agents['operations'].process_query(
            "Get current workload status",
            {"department": "warehouse", "time_range": "today"}
        )
        
        # Step 2: Equipment agent checks equipment availability
        equipment_result = await all_agents['equipment'].process_query(
            "Check availability of all forklifts",
            {"equipment_type": "forklift", "status": "operational"}
        )
        
        # Step 3: Safety agent checks safety compliance
        safety_result = await all_agents['safety'].process_query(
            "Check safety compliance for all zones",
            {"check_type": "compliance", "all_zones": True}
        )
        
        # Step 4: Operations agent optimizes workflow
        optimization_result = await all_agents['operations'].process_query(
            "Optimize warehouse workflow based on current status",
            {
                "workflow_type": "picking",
                "constraints": {
                    "equipment_availability": equipment_result,
                    "safety_compliance": safety_result
                }
            }
        )
        
        # Verify all agents processed successfully
        assert operations_result is not None, "Operations agent should get workload status"
        assert equipment_result is not None, "Equipment agent should check equipment"
        assert safety_result is not None, "Safety agent should check compliance"
        assert optimization_result is not None, "Operations agent should optimize workflow"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
