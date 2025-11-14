"""
Performance tests for the MCP system.

This module contains comprehensive performance tests including:
- Load testing
- Stress testing
- Memory usage testing
- Concurrent execution testing
- Latency testing
- Throughput testing
"""

import asyncio
import pytest
import time
import psutil
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch
import statistics

from src.api.services.mcp.server import MCPServer, MCPTool, MCPToolType
from src.api.services.mcp.client import MCPClient, MCPConnectionType
from src.api.services.mcp.tool_discovery import ToolDiscoveryService, ToolDiscoveryConfig
from src.api.services.mcp.tool_binding import ToolBindingService, BindingStrategy, ExecutionMode
from src.api.services.mcp.tool_routing import ToolRoutingService, RoutingStrategy
from src.api.services.mcp.tool_validation import ToolValidationService, ValidationLevel
from src.api.services.mcp.service_discovery import ServiceDiscoveryRegistry, ServiceType
from src.api.services.mcp.monitoring import MCPMonitoringService, MonitoringConfig


class TestMCPLoadPerformance:
    """Load testing for the MCP system."""

    @pytest.fixture
    async def mcp_server(self):
        """Create MCP server for performance testing."""
        server = MCPServer()
        await server.start()
        yield server
        await server.stop()

    @pytest.fixture
    async def mcp_client(self):
        """Create MCP client for performance testing."""
        client = MCPClient()
        yield client
        await client.disconnect()

    @pytest.fixture
    async def discovery_service(self):
        """Create tool discovery service for performance testing."""
        config = ToolDiscoveryConfig(
            discovery_interval=1,
            max_tools_per_source=1000
        )
        discovery = ToolDiscoveryService(config)
        await discovery.start_discovery()
        yield discovery
        await discovery.stop_discovery()

    @pytest.mark.performance
    async def test_single_tool_execution_latency(self, mcp_server, mcp_client):
        """Test latency of single tool execution."""
        
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Warm up
        await mcp_client.execute_tool("get_inventory", {"item_id": "ITEM001"})
        
        # Measure latency
        latencies = []
        for i in range(100):
            start_time = time.time()
            result = await mcp_client.execute_tool("get_inventory", {"item_id": f"ITEM{i:03d}"})
            end_time = time.time()
            
            if result.success:
                latencies.append(end_time - start_time)
        
        # Calculate statistics
        avg_latency = statistics.mean(latencies)
        p95_latency = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
        p99_latency = statistics.quantiles(latencies, n=100)[98]  # 99th percentile
        
        # Assertions
        assert avg_latency < 0.1, f"Average latency should be < 100ms: {avg_latency:.3f}s"
        assert p95_latency < 0.2, f"95th percentile latency should be < 200ms: {p95_latency:.3f}s"
        assert p99_latency < 0.5, f"99th percentile latency should be < 500ms: {p99_latency:.3f}s"
        
        print(f"Latency Stats - Avg: {avg_latency:.3f}s, P95: {p95_latency:.3f}s, P99: {p99_latency:.3f}s")

    @pytest.mark.performance
    async def test_concurrent_tool_execution(self, mcp_server, mcp_client):
        """Test performance under concurrent tool execution."""
        
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Test different concurrency levels
        concurrency_levels = [1, 5, 10, 20, 50, 100]
        results = {}
        
        for concurrency in concurrency_levels:
            start_time = time.time()
            
            # Create concurrent tasks
            tasks = []
            for i in range(concurrency):
                task = mcp_client.execute_tool("get_inventory", {"item_id": f"ITEM{i:03d}"})
                tasks.append(task)
            
            # Execute concurrently
            results_list = await asyncio.gather(*tasks, return_exceptions=True)
            
            end_time = time.time()
            execution_time = end_time - start_time
            
            # Calculate metrics
            successful_results = [r for r in results_list if not isinstance(r, Exception) and r.success]
            success_rate = len(successful_results) / len(results_list)
            throughput = concurrency / execution_time
            
            results[concurrency] = {
                'execution_time': execution_time,
                'success_rate': success_rate,
                'throughput': throughput
            }
            
            print(f"Concurrency {concurrency}: {execution_time:.3f}s, {success_rate:.2%} success, {throughput:.2f} ops/sec")
        
        # Assertions
        assert results[1]['success_rate'] > 0.9, "Single execution should have high success rate"
        assert results[10]['success_rate'] > 0.8, "10 concurrent executions should maintain good success rate"
        assert results[50]['success_rate'] > 0.7, "50 concurrent executions should maintain reasonable success rate"

    @pytest.mark.performance
    async def test_throughput_under_load(self, mcp_server, mcp_client):
        """Test system throughput under sustained load."""
        
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Test sustained load for 60 seconds
        test_duration = 60
        start_time = time.time()
        completed_operations = 0
        failed_operations = 0
        
        while time.time() - start_time < test_duration:
            # Create batch of operations
            tasks = []
            for i in range(10):  # Batch size
                task = mcp_client.execute_tool("get_inventory", {"item_id": f"ITEM{completed_operations + i:06d}"})
                tasks.append(task)
            
            # Execute batch
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Count results
            for result in results:
                if isinstance(result, Exception) or not result.success:
                    failed_operations += 1
                else:
                    completed_operations += 1
        
        total_time = time.time() - start_time
        total_operations = completed_operations + failed_operations
        throughput = total_operations / total_time
        success_rate = completed_operations / total_operations
        
        print(f"Sustained Load - Duration: {total_time:.1f}s, Operations: {total_operations}, Throughput: {throughput:.2f} ops/sec, Success: {success_rate:.2%}")
        
        # Assertions
        assert throughput > 10, f"Should maintain reasonable throughput: {throughput:.2f} ops/sec"
        assert success_rate > 0.8, f"Should maintain good success rate: {success_rate:.2%}"

    @pytest.mark.performance
    async def test_memory_usage_under_load(self, mcp_server, mcp_client):
        """Test memory usage under sustained load."""
        
        process = psutil.Process(os.getpid())
        
        # Get initial memory usage
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Execute many operations to test memory usage
        memory_samples = []
        for batch in range(100):  # 100 batches
            # Create batch of operations
            tasks = []
            for i in range(50):  # 50 operations per batch
                task = mcp_client.execute_tool("get_inventory", {"item_id": f"ITEM{batch * 50 + i:06d}"})
                tasks.append(task)
            
            # Execute batch
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Sample memory usage
            current_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_samples.append(current_memory)
            
            # Check for memory leaks
            if batch % 10 == 0:
                memory_increase = current_memory - initial_memory
                print(f"Batch {batch}: Memory usage: {current_memory:.1f}MB (+{memory_increase:.1f}MB)")
        
        # Calculate memory statistics
        max_memory = max(memory_samples)
        final_memory = memory_samples[-1]
        memory_increase = final_memory - initial_memory
        
        print(f"Memory Usage - Initial: {initial_memory:.1f}MB, Max: {max_memory:.1f}MB, Final: {final_memory:.1f}MB, Increase: {memory_increase:.1f}MB")
        
        # Assertions
        assert memory_increase < 500, f"Memory increase should be reasonable: {memory_increase:.1f}MB"
        assert max_memory < 2000, f"Maximum memory usage should be reasonable: {max_memory:.1f}MB"

    @pytest.mark.performance
    async def test_tool_discovery_performance(self, discovery_service):
        """Test tool discovery performance."""
        
        # Create mock adapters with many tools
        mock_adapters = []
        for adapter_id in range(10):
            adapter = MagicMock()
            adapter.get_tools.return_value = [
                MCPTool(
                    name=f"tool_{adapter_id}_{i}",
                    description=f"Tool {i} from adapter {adapter_id}",
                    tool_type=MCPToolType.FUNCTION,
                    parameters={},
                    handler=AsyncMock()
                )
                for i in range(100)  # 100 tools per adapter
            ]
            mock_adapters.append(adapter)
        
        # Register adapters
        for i, adapter in enumerate(mock_adapters):
            await discovery_service.register_discovery_source(f"adapter_{i}", adapter, "mcp_adapter")
        
        # Wait for discovery
        await asyncio.sleep(2)
        
        # Test search performance
        search_times = []
        for i in range(100):
            start_time = time.time()
            tools = await discovery_service.search_tools(f"tool_{i % 10}")
            end_time = time.time()
            search_times.append(end_time - start_time)
        
        avg_search_time = statistics.mean(search_times)
        max_search_time = max(search_times)
        
        print(f"Tool Discovery - Avg search time: {avg_search_time:.3f}s, Max search time: {max_search_time:.3f}s")
        
        # Assertions
        assert avg_search_time < 0.1, f"Average search time should be fast: {avg_search_time:.3f}s"
        assert max_search_time < 0.5, f"Maximum search time should be reasonable: {max_search_time:.3f}s"

    @pytest.mark.performance
    async def test_tool_binding_performance(self, discovery_service, binding_service):
        """Test tool binding performance."""
        
        # Register mock adapter with many tools
        mock_adapter = MagicMock()
        mock_adapter.get_tools.return_value = [
            MCPTool(
                name=f"tool_{i}",
                description=f"Tool {i} for testing",
                tool_type=MCPToolType.FUNCTION,
                parameters={},
                handler=AsyncMock()
            )
            for i in range(1000)
        ]
        
        await discovery_service.register_discovery_source("mock_adapter", mock_adapter, "mcp_adapter")
        await asyncio.sleep(2)
        
        # Test binding performance
        binding_times = []
        for i in range(100):
            start_time = time.time()
            bindings = await binding_service.bind_tools(
                agent_id="test_agent",
                query=f"Test query {i}",
                intent="test_intent",
                entities={},
                context={},
                strategy=BindingStrategy.SEMANTIC_MATCH,
                max_tools=10
            )
            end_time = time.time()
            binding_times.append(end_time - start_time)
        
        avg_binding_time = statistics.mean(binding_times)
        max_binding_time = max(binding_times)
        
        print(f"Tool Binding - Avg binding time: {avg_binding_time:.3f}s, Max binding time: {max_binding_time:.3f}s")
        
        # Assertions
        assert avg_binding_time < 0.1, f"Average binding time should be fast: {avg_binding_time:.3f}s"
        assert max_binding_time < 0.5, f"Maximum binding time should be reasonable: {max_binding_time:.3f}s"

    @pytest.mark.performance
    async def test_tool_routing_performance(self, discovery_service, binding_service, routing_service):
        """Test tool routing performance."""
        
        # Register mock adapter
        mock_adapter = MagicMock()
        mock_adapter.get_tools.return_value = [
            MCPTool(
                name=f"tool_{i}",
                description=f"Tool {i} for routing test",
                tool_type=MCPToolType.FUNCTION,
                parameters={},
                handler=AsyncMock()
            )
            for i in range(500)
        ]
        
        await discovery_service.register_discovery_source("mock_adapter", mock_adapter, "mcp_adapter")
        await asyncio.sleep(2)
        
        # Test routing performance
        routing_times = []
        for i in range(100):
            from src.api.services.mcp.tool_routing import RoutingContext
            
            context = RoutingContext(
                query=f"Test query {i}",
                intent="test_intent",
                entities={},
                user_context={},
                session_id=f"session_{i}",
                agent_id="test_agent"
            )
            
            start_time = time.time()
            decision = await routing_service.route_tools(
                context,
                strategy=RoutingStrategy.BALANCED,
                max_tools=10
            )
            end_time = time.time()
            routing_times.append(end_time - start_time)
        
        avg_routing_time = statistics.mean(routing_times)
        max_routing_time = max(routing_times)
        
        print(f"Tool Routing - Avg routing time: {avg_routing_time:.3f}s, Max routing time: {max_routing_time:.3f}s")
        
        # Assertions
        assert avg_routing_time < 0.1, f"Average routing time should be fast: {avg_routing_time:.3f}s"
        assert max_routing_time < 0.5, f"Maximum routing time should be reasonable: {max_routing_time:.3f}s"

    @pytest.mark.performance
    async def test_tool_validation_performance(self, discovery_service, validation_service):
        """Test tool validation performance."""
        
        # Register mock adapter
        mock_adapter = MagicMock()
        mock_adapter.get_tools.return_value = [
            MCPTool(
                name=f"tool_{i}",
                description=f"Tool {i} for validation test",
                tool_type=MCPToolType.FUNCTION,
                parameters={
                    "param1": {"type": "string", "required": True},
                    "param2": {"type": "integer", "required": False}
                },
                handler=AsyncMock()
            )
            for i in range(100)
        ]
        
        await discovery_service.register_discovery_source("mock_adapter", mock_adapter, "mcp_adapter")
        await asyncio.sleep(2)
        
        # Test validation performance
        validation_times = []
        for i in range(1000):
            start_time = time.time()
            result = await validation_service.validate_tool_execution(
                tool_id=f"tool_{i % 100}",
                arguments={"param1": f"value_{i}"},
                context={},
                validation_level=ValidationLevel.STANDARD
            )
            end_time = time.time()
            validation_times.append(end_time - start_time)
        
        avg_validation_time = statistics.mean(validation_times)
        max_validation_time = max(validation_times)
        
        print(f"Tool Validation - Avg validation time: {avg_validation_time:.3f}s, Max validation time: {max_validation_time:.3f}s")
        
        # Assertions
        assert avg_validation_time < 0.01, f"Average validation time should be very fast: {avg_validation_time:.3f}s"
        assert max_validation_time < 0.1, f"Maximum validation time should be reasonable: {max_validation_time:.3f}s"

    @pytest.mark.performance
    async def test_service_discovery_performance(self, service_registry):
        """Test service discovery performance."""
        
        from src.api.services.mcp.service_discovery import ServiceInfo
        
        # Register many services
        services = []
        for i in range(1000):
            service = ServiceInfo(
                service_id=f"service_{i}",
                service_name=f"Service {i}",
                service_type=ServiceType.ADAPTER,
                endpoint=f"http://localhost:{8000 + i}",
                version="1.0.0",
                capabilities=[f"capability_{j}" for j in range(10)]
            )
            services.append(service)
            await service_registry.register_service(service)
        
        # Test discovery performance
        discovery_times = []
        for i in range(100):
            start_time = time.time()
            discovered_services = await service_registry.discover_services()
            end_time = time.time()
            discovery_times.append(end_time - start_time)
        
        avg_discovery_time = statistics.mean(discovery_times)
        max_discovery_time = max(discovery_times)
        
        print(f"Service Discovery - Avg discovery time: {avg_discovery_time:.3f}s, Max discovery time: {max_discovery_time:.3f}s")
        
        # Assertions
        assert avg_discovery_time < 0.1, f"Average discovery time should be fast: {avg_discovery_time:.3f}s"
        assert max_discovery_time < 0.5, f"Maximum discovery time should be reasonable: {max_discovery_time:.3f}s"

    @pytest.mark.performance
    async def test_monitoring_performance(self, monitoring_service):
        """Test monitoring system performance."""
        
        # Record many metrics
        start_time = time.time()
        
        for i in range(10000):
            await monitoring_service.record_metric(
                "test_metric",
                float(i),
                {"tag1": f"value_{i % 100}", "tag2": f"value_{i % 50}"}
            )
        
        recording_time = time.time() - start_time
        recording_throughput = 10000 / recording_time
        
        print(f"Metric Recording - Time: {recording_time:.3f}s, Throughput: {recording_throughput:.2f} metrics/sec")
        
        # Test metric retrieval
        start_time = time.time()
        metrics = await monitoring_service.get_metrics("test_metric")
        retrieval_time = time.time() - start_time
        
        print(f"Metric Retrieval - Time: {retrieval_time:.3f}s, Metrics retrieved: {len(metrics)}")
        
        # Assertions
        assert recording_throughput > 1000, f"Should record metrics quickly: {recording_throughput:.2f} metrics/sec"
        assert retrieval_time < 1.0, f"Should retrieve metrics quickly: {retrieval_time:.3f}s"
        assert len(metrics) > 0, "Should retrieve some metrics"

    @pytest.mark.performance
    async def test_end_to_end_performance(self, mcp_server, mcp_client, discovery_service, 
                                        binding_service, routing_service, validation_service):
        """Test end-to-end performance of the complete MCP system."""
        
        # Register mock adapter
        mock_adapter = MagicMock()
        mock_adapter.get_tools.return_value = [
            MCPTool(
                name=f"tool_{i}",
                description=f"Tool {i} for end-to-end test",
                tool_type=MCPToolType.FUNCTION,
                parameters={
                    "param1": {"type": "string", "required": True},
                    "param2": {"type": "integer", "required": False}
                },
                handler=AsyncMock(return_value={"result": f"data_{i}"})
            )
            for i in range(100)
        ]
        
        await discovery_service.register_discovery_source("mock_adapter", mock_adapter, "mcp_adapter")
        await asyncio.sleep(2)
        
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Test complete workflow performance
        workflow_times = []
        for i in range(100):
            start_time = time.time()
            
            # 1. Search for tools
            tools = await discovery_service.search_tools(f"tool_{i % 100}")
            
            # 2. Bind tools
            bindings = await binding_service.bind_tools(
                agent_id="test_agent",
                query=f"Test query {i}",
                intent="test_intent",
                entities={},
                context={},
                strategy=BindingStrategy.SEMANTIC_MATCH,
                max_tools=5
            )
            
            # 3. Route tools
            from src.api.services.mcp.tool_routing import RoutingContext
            context = RoutingContext(
                query=f"Test query {i}",
                intent="test_intent",
                entities={},
                user_context={},
                session_id=f"session_{i}",
                agent_id="test_agent"
            )
            decision = await routing_service.route_tools(context, RoutingStrategy.BALANCED, max_tools=5)
            
            # 4. Validate tools
            for binding in bindings:
                await validation_service.validate_tool_execution(
                    tool_id=binding.tool_name,
                    arguments=binding.arguments,
                    context={},
                    validation_level=ValidationLevel.STANDARD
                )
            
            # 5. Execute tools
            for binding in bindings:
                await mcp_client.execute_tool(binding.tool_name, binding.arguments)
            
            end_time = time.time()
            workflow_times.append(end_time - start_time)
        
        avg_workflow_time = statistics.mean(workflow_times)
        max_workflow_time = max(workflow_times)
        
        print(f"End-to-End Workflow - Avg time: {avg_workflow_time:.3f}s, Max time: {max_workflow_time:.3f}s")
        
        # Assertions
        assert avg_workflow_time < 0.5, f"Average workflow time should be reasonable: {avg_workflow_time:.3f}s"
        assert max_workflow_time < 2.0, f"Maximum workflow time should be reasonable: {max_workflow_time:.3f}s"


class TestMCPStressPerformance:
    """Stress testing for the MCP system."""

    @pytest.mark.stress
    async def test_maximum_concurrent_connections(self, mcp_server):
        """Test maximum number of concurrent connections."""
        
        clients = []
        max_clients = 0
        
        try:
            # Gradually increase number of clients
            for i in range(1000):  # Try up to 1000 clients
                client = MCPClient()
                success = await client.connect("http://localhost:8000", MCPConnectionType.HTTP)
                
                if success:
                    clients.append(client)
                    max_clients = i + 1
                else:
                    break
        except Exception as e:
            print(f"Failed to create client {max_clients + 1}: {e}")
        
        print(f"Maximum concurrent connections: {max_clients}")
        
        # Cleanup
        for client in clients:
            await client.disconnect()
        
        # Assertions
        assert max_clients > 10, f"Should support at least 10 concurrent connections: {max_clients}"

    @pytest.mark.stress
    async def test_maximum_throughput(self, mcp_server, mcp_client):
        """Test maximum system throughput."""
        
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Test different batch sizes to find optimal throughput
        batch_sizes = [1, 5, 10, 20, 50, 100, 200, 500]
        max_throughput = 0
        optimal_batch_size = 1
        
        for batch_size in batch_sizes:
            start_time = time.time()
            completed_operations = 0
            
            # Run for 10 seconds
            while time.time() - start_time < 10:
                tasks = []
                for i in range(batch_size):
                    task = mcp_client.execute_tool("get_inventory", {"item_id": f"ITEM{completed_operations + i:06d}"})
                    tasks.append(task)
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                completed_operations += len([r for r in results if not isinstance(r, Exception) and r.success])
            
            total_time = time.time() - start_time
            throughput = completed_operations / total_time
            
            if throughput > max_throughput:
                max_throughput = throughput
                optimal_batch_size = batch_size
            
            print(f"Batch size {batch_size}: {throughput:.2f} ops/sec")
        
        print(f"Maximum throughput: {max_throughput:.2f} ops/sec (batch size: {optimal_batch_size})")
        
        # Assertions
        assert max_throughput > 50, f"Should achieve reasonable maximum throughput: {max_throughput:.2f} ops/sec"

    @pytest.mark.stress
    async def test_memory_under_extreme_load(self, mcp_server, mcp_client):
        """Test memory usage under extreme load."""
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Create extreme load
        tasks = []
        for i in range(10000):  # 10,000 concurrent operations
            task = mcp_client.execute_tool("get_inventory", {"item_id": f"ITEM{i:06d}"})
            tasks.append(task)
        
        # Execute all operations
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        successful_results = [r for r in results if not isinstance(r, Exception) and r.success]
        success_rate = len(successful_results) / len(results)
        
        print(f"Extreme Load - Memory increase: {memory_increase:.1f}MB, Success rate: {success_rate:.2%}")
        
        # Assertions
        assert memory_increase < 1000, f"Memory increase should be reasonable: {memory_increase:.1f}MB"
        assert success_rate > 0.5, f"Should maintain reasonable success rate: {success_rate:.2%}"

    @pytest.mark.stress
    async def test_sustained_load_stability(self, mcp_server, mcp_client):
        """Test system stability under sustained load."""
        
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Run sustained load for 5 minutes
        test_duration = 300  # 5 minutes
        start_time = time.time()
        completed_operations = 0
        failed_operations = 0
        memory_samples = []
        
        process = psutil.Process(os.getpid())
        
        while time.time() - start_time < test_duration:
            # Create batch of operations
            tasks = []
            for i in range(20):  # 20 operations per batch
                task = mcp_client.execute_tool("get_inventory", {"item_id": f"ITEM{completed_operations + i:06d}"})
                tasks.append(task)
            
            # Execute batch
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Count results
            for result in results:
                if isinstance(result, Exception) or not result.success:
                    failed_operations += 1
                else:
                    completed_operations += 1
            
            # Sample memory every 30 seconds
            if int(time.time() - start_time) % 30 == 0:
                current_memory = process.memory_info().rss / 1024 / 1024  # MB
                memory_samples.append(current_memory)
                print(f"Time: {int(time.time() - start_time)}s, Memory: {current_memory:.1f}MB, Ops: {completed_operations}")
        
        total_time = time.time() - start_time
        total_operations = completed_operations + failed_operations
        throughput = total_operations / total_time
        success_rate = completed_operations / total_operations
        
        # Check memory stability
        if len(memory_samples) > 1:
            memory_variance = statistics.variance(memory_samples)
            memory_stable = memory_variance < 100  # Less than 100MB variance
        else:
            memory_stable = True
        
        print(f"Sustained Load - Duration: {total_time:.1f}s, Throughput: {throughput:.2f} ops/sec, Success: {success_rate:.2%}, Memory stable: {memory_stable}")
        
        # Assertions
        assert throughput > 5, f"Should maintain reasonable throughput: {throughput:.2f} ops/sec"
        assert success_rate > 0.7, f"Should maintain good success rate: {success_rate:.2%}"
        assert memory_stable, "Memory usage should be stable"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "performance"])
