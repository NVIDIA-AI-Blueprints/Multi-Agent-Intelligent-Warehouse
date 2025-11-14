"""
Integration tests for MCP rollback and fallback mechanisms.

This module tests the comprehensive rollback and fallback functionality including:
- Tool-level rollback and fallback
- Agent-level rollback and fallback
- System-level rollback and fallback
- Emergency rollback procedures
- Monitoring and alerting
- Recovery procedures
"""

import asyncio
import pytest
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.services.mcp.rollback import (
    MCPRollbackManager, MCPToolFallback, MCPAgentFallback, MCPSystemFallback,
    RollbackConfig, FallbackConfig, RollbackLevel, FallbackMode, RollbackMetrics
)
from src.api.services.mcp.base import MCPError
from src.api.services.mcp.client import MCPClient, MCPConnectionType
from src.api.services.mcp.server import MCPServer, MCPTool, MCPToolType


class TestMCPRollbackManager:
    """Test MCP rollback manager functionality."""

    @pytest.fixture
    async def rollback_manager(self):
        """Create rollback manager for testing."""
        rollback_config = RollbackConfig(
            enabled=True,
            automatic_rollback=True,
            rollback_thresholds={
                "error_rate": 0.1,
                "response_time": 5.0,
                "memory_usage": 0.8
            }
        )
        fallback_config = FallbackConfig(
            enabled=True,
            tool_fallback=True,
            agent_fallback=True,
            system_fallback=True
        )
        
        manager = MCPRollbackManager(rollback_config, fallback_config)
        await manager.initialize()
        yield manager

    async def test_rollback_manager_initialization(self, rollback_manager):
        """Test rollback manager initialization."""
        assert rollback_manager.config.enabled is True
        assert rollback_manager.fallback_config.enabled is True
        assert rollback_manager.is_rolling_back is False
        assert rollback_manager.is_fallback_active is False

    async def test_rollback_trigger_automatic(self, rollback_manager):
        """Test automatic rollback triggering."""
        # Update metrics to trigger rollback
        rollback_manager.update_metrics(
            error_rate=0.15,  # Above threshold of 0.1
            response_time=6.0,  # Above threshold of 5.0
            memory_usage=0.9   # Above threshold of 0.8
        )
        
        # Check rollback triggers
        await rollback_manager._check_rollback_triggers()
        
        # Verify rollback was triggered
        assert rollback_manager.metrics.rollback_count > 0
        assert rollback_manager.metrics.last_rollback is not None

    async def test_rollback_trigger_manual(self, rollback_manager):
        """Test manual rollback triggering."""
        # Trigger manual rollback
        await rollback_manager._trigger_rollback(RollbackLevel.SYSTEM, "Manual rollback test")
        
        # Verify rollback was triggered
        assert rollback_manager.metrics.rollback_count > 0
        assert rollback_manager.metrics.last_rollback is not None
        assert len(rollback_manager.rollback_history) > 0

    async def test_rollback_levels(self, rollback_manager):
        """Test different rollback levels."""
        # Test tool-level rollback
        await rollback_manager._execute_rollback(RollbackLevel.TOOL, "Tool rollback test")
        
        # Test agent-level rollback
        await rollback_manager._execute_rollback(RollbackLevel.AGENT, "Agent rollback test")
        
        # Test system-level rollback
        await rollback_manager._execute_rollback(RollbackLevel.SYSTEM, "System rollback test")
        
        # Test emergency rollback
        await rollback_manager._execute_rollback(RollbackLevel.EMERGENCY, "Emergency rollback test")
        
        # Verify all rollbacks were recorded
        assert len(rollback_manager.rollback_history) >= 4

    async def test_legacy_implementation_registration(self, rollback_manager):
        """Test legacy implementation registration."""
        async def legacy_tool(parameters: dict):
            return {"status": "success", "data": "legacy_data"}
        
        # Register legacy implementation
        rollback_manager.register_legacy_implementation("test_tool", legacy_tool)
        
        # Verify registration
        assert "test_tool" in rollback_manager.legacy_implementations

    async def test_fallback_handler_registration(self, rollback_manager):
        """Test fallback handler registration."""
        async def custom_fallback(operation: str, parameters: dict):
            return {"status": "fallback", "operation": operation}
        
        # Register custom fallback handler
        rollback_manager.register_fallback_handler("custom_operation", custom_fallback)
        
        # Verify registration
        assert "custom_operation" in rollback_manager.fallback_handlers

    async def test_execute_with_fallback_success(self, rollback_manager):
        """Test execute with fallback - success case."""
        async def mcp_operation(operation: str, *args, **kwargs):
            return {"status": "success", "operation": operation}
        
        # Mock MCP operation
        rollback_manager._execute_mcp_operation = mcp_operation
        
        # Execute operation
        result = await rollback_manager.execute_with_fallback("test_operation", "arg1", key="value")
        
        # Verify success
        assert result["status"] == "success"
        assert result["operation"] == "test_operation"

    async def test_execute_with_fallback_failure(self, rollback_manager):
        """Test execute with fallback - failure case."""
        async def mcp_operation(operation: str, *args, **kwargs):
            raise MCPError("MCP operation failed")
        
        async def legacy_operation(operation: str, *args, **kwargs):
            return {"status": "fallback", "operation": operation}
        
        # Mock operations
        rollback_manager._execute_mcp_operation = mcp_operation
        rollback_manager.legacy_implementations["test_operation"] = legacy_operation
        
        # Execute operation
        result = await rollback_manager.execute_with_fallback("test_operation", "arg1", key="value")
        
        # Verify fallback
        assert result["status"] == "fallback"
        assert result["operation"] == "test_operation"

    async def test_metrics_update(self, rollback_manager):
        """Test metrics update functionality."""
        # Update metrics
        rollback_manager.update_metrics(
            error_rate=0.05,
            response_time=2.0,
            memory_usage=0.6,
            tool_failures=5,
            agent_failures=2,
            system_failures=1
        )
        
        # Verify metrics
        assert rollback_manager.metrics.error_rate == 0.05
        assert rollback_manager.metrics.response_time == 2.0
        assert rollback_manager.metrics.memory_usage == 0.6
        assert rollback_manager.metrics.tool_failures == 5
        assert rollback_manager.metrics.agent_failures == 2
        assert rollback_manager.metrics.system_failures == 1

    async def test_rollback_status(self, rollback_manager):
        """Test rollback status reporting."""
        # Update metrics
        rollback_manager.update_metrics(error_rate=0.15)
        
        # Trigger rollback
        await rollback_manager._trigger_rollback(RollbackLevel.SYSTEM, "Test rollback")
        
        # Get status
        status = rollback_manager.get_rollback_status()
        
        # Verify status
        assert "is_rolling_back" in status
        assert "is_fallback_active" in status
        assert "metrics" in status
        assert "rollback_count" in status
        assert "last_rollback" in status
        assert "rollback_history" in status
        assert status["rollback_count"] > 0


class TestMCPToolFallback:
    """Test MCP tool fallback functionality."""

    @pytest.fixture
    async def rollback_manager(self):
        """Create rollback manager for testing."""
        rollback_config = RollbackConfig(enabled=True)
        fallback_config = FallbackConfig(enabled=True)
        manager = MCPRollbackManager(rollback_config, fallback_config)
        await manager.initialize()
        return manager

    @pytest.fixture
    def tool_fallback(self, rollback_manager):
        """Create tool fallback for testing."""
        return MCPToolFallback("test_tool", "Test tool", rollback_manager)

    async def test_tool_fallback_initialization(self, tool_fallback):
        """Test tool fallback initialization."""
        assert tool_fallback.name == "test_tool"
        assert tool_fallback.description == "Test tool"
        assert tool_fallback.legacy_implementation is None

    async def test_legacy_implementation_setting(self, tool_fallback):
        """Test setting legacy implementation."""
        async def legacy_impl(parameters: dict):
            return {"status": "legacy", "data": "legacy_data"}
        
        tool_fallback.set_legacy_implementation(legacy_impl)
        assert tool_fallback.legacy_implementation is not None

    async def test_tool_execution_success(self, tool_fallback):
        """Test tool execution - success case."""
        async def mcp_execution(parameters: dict):
            return {"status": "success", "data": "mcp_data"}
        
        # Mock MCP execution
        tool_fallback._execute_mcp_tool = mcp_execution
        
        # Execute tool
        result = await tool_fallback.execute({"item_id": "ITEM001"})
        
        # Verify success
        assert result["status"] == "success"
        assert result["data"] == "mcp_data"

    async def test_tool_execution_fallback(self, tool_fallback):
        """Test tool execution - fallback case."""
        async def mcp_execution(parameters: dict):
            raise MCPError("MCP execution failed")
        
        async def legacy_execution(parameters: dict):
            return {"status": "legacy", "data": "legacy_data"}
        
        # Mock executions
        tool_fallback._execute_mcp_tool = mcp_execution
        tool_fallback.set_legacy_implementation(legacy_execution)
        
        # Execute tool
        result = await tool_fallback.execute({"item_id": "ITEM001"})
        
        # Verify fallback
        assert result["status"] == "legacy"
        assert result["data"] == "legacy_data"

    async def test_tool_execution_no_fallback(self, tool_fallback):
        """Test tool execution - no fallback available."""
        async def mcp_execution(parameters: dict):
            raise MCPError("MCP execution failed")
        
        # Mock MCP execution
        tool_fallback._execute_mcp_tool = mcp_execution
        
        # Execute tool without fallback
        with pytest.raises(MCPError, match="No fallback implementation"):
            await tool_fallback.execute({"item_id": "ITEM001"})


class TestMCPAgentFallback:
    """Test MCP agent fallback functionality."""

    @pytest.fixture
    async def rollback_manager(self):
        """Create rollback manager for testing."""
        rollback_config = RollbackConfig(enabled=True)
        fallback_config = FallbackConfig(enabled=True)
        manager = MCPRollbackManager(rollback_config, fallback_config)
        await manager.initialize()
        return manager

    @pytest.fixture
    def agent_fallback(self, rollback_manager):
        """Create agent fallback for testing."""
        return MCPAgentFallback("test_agent", rollback_manager)

    async def test_agent_fallback_initialization(self, agent_fallback):
        """Test agent fallback initialization."""
        assert agent_fallback.name == "test_agent"
        assert agent_fallback.legacy_agent is None

    async def test_legacy_agent_setting(self, agent_fallback):
        """Test setting legacy agent."""
        class MockLegacyAgent:
            async def process(self, request: dict):
                return {"status": "legacy", "agent": "legacy_agent"}
        
        legacy_agent = MockLegacyAgent()
        agent_fallback.set_legacy_agent(legacy_agent)
        assert agent_fallback.legacy_agent is not None

    async def test_agent_processing_success(self, agent_fallback):
        """Test agent processing - success case."""
        async def mcp_processing(request: dict):
            return {"status": "success", "agent": "mcp_agent"}
        
        # Mock MCP processing
        agent_fallback._process_mcp_request = mcp_processing
        
        # Process request
        result = await agent_fallback.process({"action": "test"})
        
        # Verify success
        assert result["status"] == "success"
        assert result["agent"] == "mcp_agent"

    async def test_agent_processing_fallback(self, agent_fallback):
        """Test agent processing - fallback case."""
        async def mcp_processing(request: dict):
            raise MCPError("MCP processing failed")
        
        class MockLegacyAgent:
            async def process(self, request: dict):
                return {"status": "legacy", "agent": "legacy_agent"}
        
        # Mock processing
        agent_fallback._process_mcp_request = mcp_processing
        agent_fallback.set_legacy_agent(MockLegacyAgent())
        
        # Process request
        result = await agent_fallback.process({"action": "test"})
        
        # Verify fallback
        assert result["status"] == "legacy"
        assert result["agent"] == "legacy_agent"

    async def test_agent_processing_no_fallback(self, agent_fallback):
        """Test agent processing - no fallback available."""
        async def mcp_processing(request: dict):
            raise MCPError("MCP processing failed")
        
        # Mock MCP processing
        agent_fallback._process_mcp_request = mcp_processing
        
        # Process request without fallback
        with pytest.raises(MCPError, match="No fallback implementation"):
            await agent_fallback.process({"action": "test"})


class TestMCPSystemFallback:
    """Test MCP system fallback functionality."""

    @pytest.fixture
    async def rollback_manager(self):
        """Create rollback manager for testing."""
        rollback_config = RollbackConfig(enabled=True)
        fallback_config = FallbackConfig(enabled=True)
        manager = MCPRollbackManager(rollback_config, fallback_config)
        await manager.initialize()
        return manager

    @pytest.fixture
    def system_fallback(self, rollback_manager):
        """Create system fallback for testing."""
        return MCPSystemFallback(rollback_manager)

    async def test_system_fallback_initialization(self, system_fallback):
        """Test system fallback initialization."""
        assert system_fallback.mcp_enabled is True
        assert system_fallback.legacy_system is None

    async def test_legacy_system_setting(self, system_fallback):
        """Test setting legacy system."""
        class MockLegacySystem:
            async def initialize(self):
                pass
            
            async def execute_operation(self, operation: str, *args, **kwargs):
                return {"status": "legacy", "operation": operation}
        
        legacy_system = MockLegacySystem()
        system_fallback.set_legacy_system(legacy_system)
        assert system_fallback.legacy_system is not None

    async def test_system_initialization_success(self, system_fallback):
        """Test system initialization - success case."""
        async def mcp_initialization():
            pass
        
        # Mock MCP initialization
        system_fallback._initialize_mcp_system = mcp_initialization
        
        # Initialize system
        await system_fallback.initialize()
        
        # Verify success
        assert system_fallback.mcp_enabled is True

    async def test_system_initialization_fallback(self, system_fallback):
        """Test system initialization - fallback case."""
        async def mcp_initialization():
            raise MCPError("MCP initialization failed")
        
        class MockLegacySystem:
            async def initialize(self):
                pass
        
        # Mock initialization
        system_fallback._initialize_mcp_system = mcp_initialization
        system_fallback.set_legacy_system(MockLegacySystem())
        
        # Initialize system
        await system_fallback.initialize()
        
        # Verify fallback
        assert system_fallback.mcp_enabled is False

    async def test_operation_execution_mcp_success(self, system_fallback):
        """Test operation execution - MCP success case."""
        async def mcp_operation(operation: str, *args, **kwargs):
            return {"status": "success", "operation": operation}
        
        # Mock MCP operation
        system_fallback._execute_mcp_operation = mcp_operation
        
        # Execute operation
        result = await system_fallback.execute_operation("test_operation", "arg1", key="value")
        
        # Verify success
        assert result["status"] == "success"
        assert result["operation"] == "test_operation"

    async def test_operation_execution_fallback(self, system_fallback):
        """Test operation execution - fallback case."""
        async def mcp_operation(operation: str, *args, **kwargs):
            raise MCPError("MCP operation failed")
        
        class MockLegacySystem:
            async def execute_operation(self, operation: str, *args, **kwargs):
                return {"status": "legacy", "operation": operation}
        
        # Mock operations
        system_fallback._execute_mcp_operation = mcp_operation
        system_fallback.set_legacy_system(MockLegacySystem())
        
        # Execute operation
        result = await system_fallback.execute_operation("test_operation", "arg1", key="value")
        
        # Verify fallback
        assert result["status"] == "legacy"
        assert result["operation"] == "test_operation"

    async def test_operation_execution_legacy_mode(self, system_fallback):
        """Test operation execution - legacy mode."""
        class MockLegacySystem:
            async def execute_operation(self, operation: str, *args, **kwargs):
                return {"status": "legacy", "operation": operation}
        
        # Set legacy mode
        system_fallback.mcp_enabled = False
        system_fallback.set_legacy_system(MockLegacySystem())
        
        # Execute operation
        result = await system_fallback.execute_operation("test_operation", "arg1", key="value")
        
        # Verify legacy execution
        assert result["status"] == "legacy"
        assert result["operation"] == "test_operation"


class TestRollbackIntegration:
    """Test rollback integration scenarios."""

    @pytest.fixture
    async def full_rollback_system(self):
        """Create full rollback system for testing."""
        rollback_config = RollbackConfig(
            enabled=True,
            automatic_rollback=True,
            rollback_thresholds={
                "error_rate": 0.1,
                "response_time": 5.0,
                "memory_usage": 0.8
            }
        )
        fallback_config = FallbackConfig(
            enabled=True,
            tool_fallback=True,
            agent_fallback=True,
            system_fallback=True
        )
        
        manager = MCPRollbackManager(rollback_config, fallback_config)
        await manager.initialize()
        
        # Create system components
        tool = MCPToolFallback("test_tool", "Test tool", manager)
        agent = MCPAgentFallback("test_agent", manager)
        system = MCPSystemFallback(manager)
        
        return {
            "manager": manager,
            "tool": tool,
            "agent": agent,
            "system": system
        }

    async def test_end_to_end_rollback_scenario(self, full_rollback_system):
        """Test end-to-end rollback scenario."""
        manager = full_rollback_system["manager"]
        tool = full_rollback_system["tool"]
        agent = full_rollback_system["agent"]
        system = full_rollback_system["system"]
        
        # Set up legacy implementations
        async def legacy_tool(parameters: dict):
            return {"status": "legacy_tool", "data": "legacy_data"}
        
        class MockLegacyAgent:
            async def process(self, request: dict):
                return {"status": "legacy_agent", "data": "legacy_data"}
        
        class MockLegacySystem:
            async def initialize(self):
                pass
            
            async def execute_operation(self, operation: str, *args, **kwargs):
                return {"status": "legacy_system", "operation": operation}
        
        # Register legacy implementations
        tool.set_legacy_implementation(legacy_tool)
        agent.set_legacy_agent(MockLegacyAgent())
        system.set_legacy_system(MockLegacySystem())
        
        # Simulate high error rate to trigger rollback
        manager.update_metrics(error_rate=0.15)
        
        # Check rollback triggers
        await manager._check_rollback_triggers()
        
        # Verify rollback was triggered
        assert manager.metrics.rollback_count > 0
        assert manager.metrics.last_rollback is not None

    async def test_gradual_rollback_scenario(self, full_rollback_system):
        """Test gradual rollback scenario."""
        manager = full_rollback_system["manager"]
        
        # Test tool-level rollback
        await manager._execute_rollback(RollbackLevel.TOOL, "Tool-level rollback")
        
        # Test agent-level rollback
        await manager._execute_rollback(RollbackLevel.AGENT, "Agent-level rollback")
        
        # Test system-level rollback
        await manager._execute_rollback(RollbackLevel.SYSTEM, "System-level rollback")
        
        # Verify all rollbacks were recorded
        assert len(manager.rollback_history) >= 3

    async def test_emergency_rollback_scenario(self, full_rollback_system):
        """Test emergency rollback scenario."""
        manager = full_rollback_system["manager"]
        
        # Trigger emergency rollback
        await manager._execute_rollback(RollbackLevel.EMERGENCY, "Emergency rollback")
        
        # Verify emergency rollback was recorded
        assert len(manager.rollback_history) >= 1
        assert manager.rollback_history[-1]["level"] == "emergency"

    async def test_rollback_recovery_scenario(self, full_rollback_system):
        """Test rollback recovery scenario."""
        manager = full_rollback_system["manager"]
        
        # Trigger rollback
        await manager._trigger_rollback(RollbackLevel.SYSTEM, "Test rollback")
        
        # Wait for cooldown
        await asyncio.sleep(0.1)
        
        # Reset metrics to normal levels
        manager.update_metrics(
            error_rate=0.05,
            response_time=2.0,
            memory_usage=0.6
        )
        
        # Verify system can recover
        assert manager.metrics.error_rate < manager.config.rollback_thresholds["error_rate"]
        assert manager.metrics.response_time < manager.config.rollback_thresholds["response_time"]
        assert manager.metrics.memory_usage < manager.config.rollback_thresholds["memory_usage"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
