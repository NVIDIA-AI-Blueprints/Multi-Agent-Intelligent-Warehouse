"""
Load testing for the MCP system.

This module contains comprehensive load tests including:
- Stress testing
- Performance testing
- Scalability testing
- Endurance testing
- Spike testing
"""

import asyncio
import pytest
import time
import statistics
import psutil
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.services.mcp.server import MCPServer, MCPTool, MCPToolType
from src.api.services.mcp.client import MCPClient, MCPConnectionType
from src.api.services.mcp.tool_discovery import ToolDiscoveryService, ToolDiscoveryConfig
from src.api.services.mcp.tool_binding import ToolBindingService, BindingStrategy, ExecutionMode
from src.api.services.mcp.tool_routing import ToolRoutingService, RoutingStrategy
from src.api.services.mcp.tool_validation import ToolValidationService, ValidationLevel
from src.api.services.mcp.service_discovery import ServiceRegistry, ServiceType
from src.api.services.mcp.monitoring import MCPMonitoring


class TestMCPStressTesting:
    """Stress testing for the MCP system."""

    @pytest.fixture
    async def mcp_server(self):
        """Create MCP server for stress testing."""
        server = MCPServer()
        await server.start()
        yield server
        await server.stop()

    @pytest.fixture
    async def mcp_client(self):
        """Create MCP client for stress testing."""
        client = MCPClient()
        yield client
        await client.disconnect()

    @pytest.fixture
    async def discovery_service(self):
        """Create tool discovery service for stress testing."""
        config = ToolDiscoveryConfig(
            discovery_interval=1,
            max_tools_per_source=1000
        )
        discovery = ToolDiscoveryService(config)
        await discovery.start_discovery()
        yield discovery
        await discovery.stop_discovery()

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

    @pytest.mark.stress
    async def test_resource_exhaustion_recovery(self, mcp_server, mcp_client):
        """Test system recovery from resource exhaustion."""
        
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Create resource exhaustion
        tasks = []
        for i in range(5000):  # Create many tasks
            task = mcp_client.execute_tool("get_inventory", {"item_id": f"ITEM{i:06d}"})
            tasks.append(task)
        
        # Execute all tasks
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Wait for system to recover
        await asyncio.sleep(5)
        
        # Test system recovery
        recovery_result = await mcp_client.execute_tool("get_inventory", {"item_id": "ITEM001"})
        assert recovery_result is not None, "System should recover from resource exhaustion"

    @pytest.mark.stress
    async def test_cascade_failure_prevention(self, mcp_server, mcp_client, discovery_service):
        """Test prevention of cascade failures."""
        
        # Register many adapters
        for i in range(100):
            mock_adapter = MagicMock()
            mock_adapter.get_tools.return_value = [
                MCPTool(
                    name=f"tool_{i}_{j}",
                    description=f"Tool {j} from adapter {i}",
                    tool_type=MCPToolType.FUNCTION,
                    parameters={},
                    handler=AsyncMock(return_value={"result": f"data_{i}_{j}"})
                )
                for j in range(10)
            ]
            
            await discovery_service.register_discovery_source(f"adapter_{i}", mock_adapter, "mcp_adapter")
        
        await asyncio.sleep(2)  # Allow discovery
        
        # Test system stability with many adapters
        tools = await discovery_service.search_tools("")
        assert len(tools) > 0, "Should handle many adapters without cascade failure"

    @pytest.mark.stress
    async def test_network_partition_tolerance(self, mcp_server, mcp_client):
        """Test network partition tolerance."""
        
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Simulate network partition
        await mcp_client.disconnect()
        
        # Wait for partition
        await asyncio.sleep(2)
        
        # Test reconnection
        success = await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        assert success, "Should recover from network partition"
        
        # Test functionality after recovery
        result = await mcp_client.execute_tool("get_inventory", {"item_id": "ITEM001"})
        assert result is not None, "Should function after network recovery"


class TestMCPPerformanceTesting:
    """Performance testing for the MCP system."""

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

    @pytest.mark.performance
    async def test_latency_under_load(self, mcp_server, mcp_client):
        """Test latency under various load conditions."""
        
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Test different load levels
        load_levels = [1, 5, 10, 20, 50, 100]
        latency_results = {}
        
        for load in load_levels:
            latencies = []
            
            # Execute operations under load
            for batch in range(10):  # 10 batches per load level
                tasks = []
                for i in range(load):
                    start_time = time.time()
                    task = mcp_client.execute_tool("get_inventory", {"item_id": f"ITEM{batch * load + i:06d}"})
                    tasks.append((task, start_time))
                
                results = await asyncio.gather(*[task for task, _ in tasks], return_exceptions=True)
                
                # Calculate latencies
                for i, result in enumerate(results):
                    if not isinstance(result, Exception) and result.success:
                        end_time = time.time()
                        latency = end_time - tasks[i][1]
                        latencies.append(latency)
            
            if latencies:
                avg_latency = statistics.mean(latencies)
                p95_latency = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
                p99_latency = statistics.quantiles(latencies, n=100)[98]  # 99th percentile
                
                latency_results[load] = {
                    'avg': avg_latency,
                    'p95': p95_latency,
                    'p99': p99_latency
                }
                
                print(f"Load {load}: Avg={avg_latency:.3f}s, P95={p95_latency:.3f}s, P99={p99_latency:.3f}s")
        
        # Assertions
        for load, latencies in latency_results.items():
            assert latencies['avg'] < 1.0, f"Average latency should be < 1s at load {load}: {latencies['avg']:.3f}s"
            assert latencies['p95'] < 2.0, f"95th percentile latency should be < 2s at load {load}: {latencies['p95']:.3f}s"

    @pytest.mark.performance
    async def test_throughput_scaling(self, mcp_server, mcp_client):
        """Test throughput scaling with load."""
        
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Test throughput at different load levels
        load_levels = [1, 5, 10, 20, 50, 100]
        throughput_results = {}
        
        for load in load_levels:
            start_time = time.time()
            completed_operations = 0
            
            # Run for 30 seconds
            while time.time() - start_time < 30:
                tasks = []
                for i in range(load):
                    task = mcp_client.execute_tool("get_inventory", {"item_id": f"ITEM{completed_operations + i:06d}"})
                    tasks.append(task)
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                completed_operations += len([r for r in results if not isinstance(r, Exception) and r.success])
            
            total_time = time.time() - start_time
            throughput = completed_operations / total_time
            throughput_results[load] = throughput
            
            print(f"Load {load}: {throughput:.2f} ops/sec")
        
        # Check throughput scaling
        assert throughput_results[1] > 0, "Should have some throughput at load 1"
        assert throughput_results[10] > throughput_results[1], "Throughput should scale with load"
        assert throughput_results[50] > throughput_results[10], "Throughput should continue scaling"

    @pytest.mark.performance
    async def test_memory_efficiency(self, mcp_server, mcp_client):
        """Test memory efficiency under load."""
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Test memory usage at different load levels
        load_levels = [1, 10, 50, 100, 500]
        memory_results = {}
        
        for load in load_levels:
            # Execute operations
            tasks = []
            for i in range(load * 10):  # 10 batches per load level
                task = mcp_client.execute_tool("get_inventory", {"item_id": f"ITEM{i:06d}"})
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Measure memory usage
            current_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = current_memory - initial_memory
            memory_per_operation = memory_increase / (load * 10)
            
            memory_results[load] = {
                'total_memory': current_memory,
                'memory_increase': memory_increase,
                'memory_per_operation': memory_per_operation
            }
            
            print(f"Load {load}: Memory={current_memory:.1f}MB (+{memory_increase:.1f}MB), Per op={memory_per_operation:.3f}MB")
        
        # Assertions
        for load, memory in memory_results.items():
            assert memory['memory_increase'] < 1000, f"Memory increase should be reasonable at load {load}: {memory['memory_increase']:.1f}MB"
            assert memory['memory_per_operation'] < 1.0, f"Memory per operation should be efficient at load {load}: {memory['memory_per_operation']:.3f}MB"

    @pytest.mark.performance
    async def test_cpu_efficiency(self, mcp_server, mcp_client):
        """Test CPU efficiency under load."""
        
        process = psutil.Process(os.getpid())
        
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Test CPU usage at different load levels
        load_levels = [1, 10, 50, 100]
        cpu_results = {}
        
        for load in load_levels:
            # Start CPU monitoring
            process.cpu_percent()  # Initialize
            start_cpu = process.cpu_percent()
            
            # Execute operations
            tasks = []
            for i in range(load * 20):  # 20 batches per load level
                task = mcp_client.execute_tool("get_inventory", {"item_id": f"ITEM{i:06d}"})
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Measure CPU usage
            end_cpu = process.cpu_percent()
            avg_cpu = (start_cpu + end_cpu) / 2
            
            cpu_results[load] = avg_cpu
            print(f"Load {load}: CPU={avg_cpu:.1f}%")
        
        # Assertions
        for load, cpu in cpu_results.items():
            assert cpu < 100, f"CPU usage should be reasonable at load {load}: {cpu:.1f}%"

    @pytest.mark.performance
    async def test_response_time_consistency(self, mcp_server, mcp_client):
        """Test response time consistency."""
        
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Execute many operations and measure response times
        response_times = []
        for i in range(1000):
            start_time = time.time()
            result = await mcp_client.execute_tool("get_inventory", {"item_id": f"ITEM{i:06d}"})
            end_time = time.time()
            
            if result.success:
                response_times.append(end_time - start_time)
        
        # Calculate consistency metrics
        avg_response_time = statistics.mean(response_times)
        std_response_time = statistics.stdev(response_times)
        cv = std_response_time / avg_response_time  # Coefficient of variation
        
        print(f"Response Time Consistency - Avg: {avg_response_time:.3f}s, Std: {std_response_time:.3f}s, CV: {cv:.3f}")
        
        # Assertions
        assert cv < 0.5, f"Response time should be consistent (CV < 0.5): {cv:.3f}"

    @pytest.mark.performance
    async def test_concurrent_user_simulation(self, mcp_server, mcp_client):
        """Test concurrent user simulation."""
        
        # Simulate multiple users
        num_users = 50
        operations_per_user = 20
        
        async def simulate_user(user_id):
            client = MCPClient()
            await client.connect("http://localhost:8000", MCPConnectionType.HTTP)
            
            user_operations = []
            for i in range(operations_per_user):
                start_time = time.time()
                result = await client.execute_tool("get_inventory", {"item_id": f"USER{user_id}_ITEM{i:03d}"})
                end_time = time.time()
                
                if result.success:
                    user_operations.append(end_time - start_time)
            
            await client.disconnect()
            return user_operations
        
        # Execute user simulations concurrently
        user_tasks = [simulate_user(i) for i in range(num_users)]
        user_results = await asyncio.gather(*user_tasks)
        
        # Analyze results
        all_operations = []
        for user_ops in user_results:
            all_operations.extend(user_ops)
        
        avg_response_time = statistics.mean(all_operations)
        p95_response_time = statistics.quantiles(all_operations, n=20)[18]
        
        print(f"Concurrent Users - Users: {num_users}, Ops per user: {operations_per_user}, Avg response: {avg_response_time:.3f}s, P95: {p95_response_time:.3f}s")
        
        # Assertions
        assert avg_response_time < 1.0, f"Average response time should be reasonable: {avg_response_time:.3f}s"
        assert p95_response_time < 2.0, f"95th percentile response time should be reasonable: {p95_response_time:.3f}s"


class TestMCPScalabilityTesting:
    """Scalability testing for the MCP system."""

    @pytest.fixture
    async def mcp_server(self):
        """Create MCP server for scalability testing."""
        server = MCPServer()
        await server.start()
        yield server
        await server.stop()

    @pytest.fixture
    async def mcp_client(self):
        """Create MCP client for scalability testing."""
        client = MCPClient()
        yield client
        await client.disconnect()

    @pytest.mark.scalability
    async def test_horizontal_scaling(self, mcp_server, mcp_client):
        """Test horizontal scaling capabilities."""
        
        # Simulate multiple server instances
        num_servers = 5
        clients_per_server = 20
        
        async def simulate_server(server_id):
            clients = []
            for i in range(clients_per_server):
                client = MCPClient()
                await client.connect("http://localhost:8000", MCPConnectionType.HTTP)
                clients.append(client)
            
            # Execute operations
            tasks = []
            for i, client in enumerate(clients):
                task = client.execute_tool("get_inventory", {"item_id": f"SERVER{server_id}_ITEM{i:03d}"})
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Cleanup
            for client in clients:
                await client.disconnect()
            
            return len([r for r in results if not isinstance(r, Exception) and r.success])
        
        # Simulate all servers
        server_tasks = [simulate_server(i) for i in range(num_servers)]
        server_results = await asyncio.gather(*server_tasks)
        
        total_successful = sum(server_results)
        total_operations = num_servers * clients_per_server
        success_rate = total_successful / total_operations
        
        print(f"Horizontal Scaling - Servers: {num_servers}, Clients per server: {clients_per_server}, Success rate: {success_rate:.2%}")
        
        # Assertions
        assert success_rate > 0.8, f"Should maintain good success rate with horizontal scaling: {success_rate:.2%}"

    @pytest.mark.scalability
    async def test_vertical_scaling(self, mcp_server, mcp_client):
        """Test vertical scaling capabilities."""
        
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Test different resource levels
        resource_levels = [1, 2, 4, 8, 16]  # Simulate different CPU cores
        throughput_results = {}
        
        for resources in resource_levels:
            # Simulate resource allocation
            with patch('src.api.services.mcp.server.MCPServer._get_available_resources') as mock_resources:
                mock_resources.return_value = resources
                
                start_time = time.time()
                completed_operations = 0
                
                # Run for 30 seconds
                while time.time() - start_time < 30:
                    tasks = []
                    for i in range(resources * 10):  # Scale operations with resources
                        task = mcp_client.execute_tool("get_inventory", {"item_id": f"ITEM{completed_operations + i:06d}"})
                        tasks.append(task)
                    
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    completed_operations += len([r for r in results if not isinstance(r, Exception) and r.success])
                
                total_time = time.time() - start_time
                throughput = completed_operations / total_time
                throughput_results[resources] = throughput
                
                print(f"Resources {resources}: {throughput:.2f} ops/sec")
        
        # Check scaling efficiency
        base_throughput = throughput_results[1]
        for resources, throughput in throughput_results.items():
            if resources > 1:
                efficiency = throughput / (base_throughput * resources)
                print(f"Resources {resources}: Efficiency {efficiency:.2f}")
                assert efficiency > 0.5, f"Should maintain reasonable efficiency at {resources} resources: {efficiency:.2f}"

    @pytest.mark.scalability
    async def test_database_scaling(self, mcp_server, mcp_client, discovery_service):
        """Test database scaling capabilities."""
        
        # Register many adapters to simulate database load
        num_adapters = 100
        tools_per_adapter = 50
        
        for adapter_id in range(num_adapters):
            mock_adapter = MagicMock()
            mock_adapter.get_tools.return_value = [
                MCPTool(
                    name=f"tool_{adapter_id}_{i}",
                    description=f"Tool {i} from adapter {adapter_id}",
                    tool_type=MCPToolType.FUNCTION,
                    parameters={},
                    handler=AsyncMock(return_value={"result": f"data_{adapter_id}_{i}"})
                )
                for i in range(tools_per_adapter)
            ]
            
            await discovery_service.register_discovery_source(f"adapter_{adapter_id}", mock_adapter, "mcp_adapter")
        
        await asyncio.sleep(2)  # Allow discovery
        
        # Test database operations under load
        start_time = time.time()
        
        # Search operations
        search_tasks = []
        for i in range(100):
            task = discovery_service.search_tools(f"tool_{i % num_adapters}")
            search_tasks.append(task)
        
        search_results = await asyncio.gather(*search_tasks)
        
        # Tool execution operations
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        execution_tasks = []
        for i in range(100):
            task = mcp_client.execute_tool("get_inventory", {"item_id": f"ITEM{i:06d}"})
            execution_tasks.append(task)
        
        execution_results = await asyncio.gather(*execution_tasks)
        
        total_time = time.time() - start_time
        
        successful_searches = len([r for r in search_results if r])
        successful_executions = len([r for r in execution_results if not isinstance(r, Exception) and r.success])
        
        print(f"Database Scaling - Adapters: {num_adapters}, Tools per adapter: {tools_per_adapter}, Search success: {successful_searches}/100, Execution success: {successful_executions}/100, Time: {total_time:.2f}s")
        
        # Assertions
        assert successful_searches > 80, f"Should handle database scaling for searches: {successful_searches}/100"
        assert successful_executions > 80, f"Should handle database scaling for executions: {successful_executions}/100"

    @pytest.mark.scalability
    async def test_network_scaling(self, mcp_server, mcp_client):
        """Test network scaling capabilities."""
        
        # Test different network loads
        network_loads = [1, 5, 10, 20, 50, 100]
        network_results = {}
        
        for load in network_loads:
            # Create multiple clients to simulate network load
            clients = []
            for i in range(load):
                client = MCPClient()
                await client.connect("http://localhost:8000", MCPConnectionType.HTTP)
                clients.append(client)
            
            # Execute operations
            start_time = time.time()
            tasks = []
            for i, client in enumerate(clients):
                task = client.execute_tool("get_inventory", {"item_id": f"ITEM{i:06d}"})
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            end_time = time.time()
            
            # Calculate metrics
            execution_time = end_time - start_time
            successful_results = [r for r in results if not isinstance(r, Exception) and r.success]
            success_rate = len(successful_results) / len(results)
            throughput = len(successful_results) / execution_time
            
            network_results[load] = {
                'execution_time': execution_time,
                'success_rate': success_rate,
                'throughput': throughput
            }
            
            print(f"Network Load {load}: Time={execution_time:.3f}s, Success={success_rate:.2%}, Throughput={throughput:.2f} ops/sec")
            
            # Cleanup
            for client in clients:
                await client.disconnect()
        
        # Check network scaling
        for load, results in network_results.items():
            assert results['success_rate'] > 0.7, f"Should maintain good success rate at network load {load}: {results['success_rate']:.2%}"
            assert results['throughput'] > 0, f"Should have some throughput at network load {load}: {results['throughput']:.2f} ops/sec"


class TestMCPEnduranceTesting:
    """Endurance testing for the MCP system."""

    @pytest.fixture
    async def mcp_server(self):
        """Create MCP server for endurance testing."""
        server = MCPServer()
        await server.start()
        yield server
        await server.stop()

    @pytest.fixture
    async def mcp_client(self):
        """Create MCP client for endurance testing."""
        client = MCPClient()
        yield client
        await client.disconnect()

    @pytest.mark.endurance
    async def test_24_hour_endurance(self, mcp_server, mcp_client):
        """Test 24-hour endurance run."""
        
        # Note: This test is marked as endurance and should be run separately
        # For CI/CD, we'll run a shorter version
        
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Run for 1 hour instead of 24 hours for testing
        test_duration = 3600  # 1 hour
        start_time = time.time()
        completed_operations = 0
        failed_operations = 0
        memory_samples = []
        
        process = psutil.Process(os.getpid())
        
        while time.time() - start_time < test_duration:
            # Create batch of operations
            tasks = []
            for i in range(10):  # 10 operations per batch
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
            
            # Sample memory every 5 minutes
            if int(time.time() - start_time) % 300 == 0:
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
            memory_stable = memory_variance < 200  # Less than 200MB variance
        else:
            memory_stable = True
        
        print(f"Endurance Test - Duration: {total_time:.1f}s, Throughput: {throughput:.2f} ops/sec, Success: {success_rate:.2%}, Memory stable: {memory_stable}")
        
        # Assertions
        assert throughput > 1, f"Should maintain reasonable throughput: {throughput:.2f} ops/sec"
        assert success_rate > 0.8, f"Should maintain good success rate: {success_rate:.2%}"
        assert memory_stable, "Memory usage should be stable"

    @pytest.mark.endurance
    async def test_memory_leak_detection(self, mcp_server, mcp_client):
        """Test for memory leaks during extended operation."""
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Run for 30 minutes
        test_duration = 1800  # 30 minutes
        start_time = time.time()
        memory_samples = []
        
        while time.time() - start_time < test_duration:
            # Execute operations
            tasks = []
            for i in range(100):
                task = mcp_client.execute_tool("get_inventory", {"item_id": f"ITEM{i:06d}"})
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Sample memory every 5 minutes
            if int(time.time() - start_time) % 300 == 0:
                current_memory = process.memory_info().rss / 1024 / 1024  # MB
                memory_samples.append(current_memory)
                print(f"Time: {int(time.time() - start_time)}s, Memory: {current_memory:.1f}MB")
        
        # Analyze memory trend
        if len(memory_samples) > 1:
            memory_trend = statistics.linear_regression(range(len(memory_samples)), memory_samples)
            memory_leak = memory_trend.slope > 1.0  # More than 1MB per 5 minutes
        else:
            memory_leak = False
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        total_memory_increase = final_memory - initial_memory
        
        print(f"Memory Leak Test - Initial: {initial_memory:.1f}MB, Final: {final_memory:.1f}MB, Increase: {total_memory_increase:.1f}MB, Leak: {memory_leak}")
        
        # Assertions
        assert not memory_leak, "Should not have memory leaks"
        assert total_memory_increase < 500, f"Total memory increase should be reasonable: {total_memory_increase:.1f}MB"

    @pytest.mark.endurance
    async def test_connection_stability(self, mcp_server, mcp_client):
        """Test connection stability over time."""
        
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Test connection stability for 1 hour
        test_duration = 3600  # 1 hour
        start_time = time.time()
        connection_failures = 0
        total_operations = 0
        
        while time.time() - start_time < test_duration:
            try:
                result = await mcp_client.execute_tool("get_inventory", {"item_id": f"ITEM{total_operations:06d}"})
                if not result.success:
                    connection_failures += 1
                total_operations += 1
            except Exception as e:
                connection_failures += 1
                total_operations += 1
                print(f"Connection failure at {int(time.time() - start_time)}s: {e}")
            
            # Wait 1 second between operations
            await asyncio.sleep(1)
        
        failure_rate = connection_failures / total_operations
        
        print(f"Connection Stability - Duration: {test_duration}s, Operations: {total_operations}, Failures: {connection_failures}, Failure rate: {failure_rate:.2%}")
        
        # Assertions
        assert failure_rate < 0.01, f"Connection failure rate should be low: {failure_rate:.2%}"

    @pytest.mark.endurance
    async def test_resource_utilization_stability(self, mcp_server, mcp_client):
        """Test resource utilization stability over time."""
        
        process = psutil.Process(os.getpid())
        
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Monitor resource utilization for 30 minutes
        test_duration = 1800  # 30 minutes
        start_time = time.time()
        cpu_samples = []
        memory_samples = []
        
        while time.time() - start_time < test_duration:
            # Execute operations
            tasks = []
            for i in range(50):
                task = mcp_client.execute_tool("get_inventory", {"item_id": f"ITEM{i:06d}"})
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Sample resources every 5 minutes
            if int(time.time() - start_time) % 300 == 0:
                current_cpu = process.cpu_percent()
                current_memory = process.memory_info().rss / 1024 / 1024  # MB
                cpu_samples.append(current_cpu)
                memory_samples.append(current_memory)
                print(f"Time: {int(time.time() - start_time)}s, CPU: {current_cpu:.1f}%, Memory: {current_memory:.1f}MB")
        
        # Analyze resource stability
        cpu_variance = statistics.variance(cpu_samples) if len(cpu_samples) > 1 else 0
        memory_variance = statistics.variance(memory_samples) if len(memory_samples) > 1 else 0
        
        cpu_stable = cpu_variance < 100  # Less than 100% variance
        memory_stable = memory_variance < 100  # Less than 100MB variance
        
        print(f"Resource Stability - CPU variance: {cpu_variance:.1f}, Memory variance: {memory_variance:.1f}, CPU stable: {cpu_stable}, Memory stable: {memory_stable}")
        
        # Assertions
        assert cpu_stable, "CPU utilization should be stable"
        assert memory_stable, "Memory utilization should be stable"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "stress or performance or scalability or endurance"])
