"""
Monitoring integration tests for the MCP system.

This module tests monitoring and observability aspects including:
- Metrics collection and aggregation
- Health monitoring and alerting
- Logging and audit trails
- Performance monitoring
- System diagnostics
"""

import asyncio
import pytest
import json
import time
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


class TestMCPMetricsCollection:
    """Test MCP metrics collection and aggregation."""

    @pytest.fixture
    async def monitoring_service(self):
        """Create monitoring service for testing."""
        config = MonitoringConfig(
            metrics_retention_days=1,
            alert_thresholds={
                "error_rate": 0.1,
                "response_time": 5.0,
                "memory_usage": 0.8
            }
        )
        monitoring = MCPMonitoringService(config)
        await monitoring.start_monitoring()
        yield monitoring
        await monitoring.stop_monitoring()

    async def test_metrics_recording(self, monitoring_service):
        """Test basic metrics recording."""
        
        # Record various metrics
        await monitoring_service.record_metric("tool_executions", 1.0, {"tool_name": "get_inventory"})
        await monitoring_service.record_metric("tool_execution_time", 0.5, {"tool_name": "get_inventory"})
        await monitoring_service.record_metric("active_connections", 1.0, {"service": "mcp_server"})
        await monitoring_service.record_metric("memory_usage", 0.6, {"component": "mcp_server"})
        
        # Retrieve metrics
        tool_executions = await monitoring_service.get_metrics("tool_executions")
        execution_times = await monitoring_service.get_metrics("tool_execution_time")
        connections = await monitoring_service.get_metrics("active_connections")
        memory = await monitoring_service.get_metrics("memory_usage")
        
        # Verify metrics were recorded
        assert len(tool_executions) > 0, "Should record tool execution metrics"
        assert len(execution_times) > 0, "Should record execution time metrics"
        assert len(connections) > 0, "Should record connection metrics"
        assert len(memory) > 0, "Should record memory metrics"

    async def test_metrics_aggregation(self, monitoring_service):
        """Test metrics aggregation over time."""
        
        # Record metrics over time
        for i in range(100):
            await monitoring_service.record_metric("response_time", 0.1 + (i % 10) * 0.01, {"endpoint": "api"})
            await monitoring_service.record_metric("error_count", 1 if i % 20 == 0 else 0, {"error_type": "validation"})
        
        # Get aggregated metrics
        response_times = await monitoring_service.get_metrics("response_time")
        error_counts = await monitoring_service.get_metrics("error_count")
        
        # Verify aggregation
        assert len(response_times) > 0, "Should aggregate response time metrics"
        assert len(error_counts) > 0, "Should aggregate error count metrics"
        
        # Check that we have multiple data points
        assert len(response_times) >= 100, "Should have all recorded response times"
        assert len(error_counts) >= 100, "Should have all recorded error counts"

    async def test_metrics_filtering(self, monitoring_service):
        """Test metrics filtering by tags."""
        
        # Record metrics with different tags
        await monitoring_service.record_metric("tool_executions", 1.0, {"tool_name": "get_inventory", "agent": "equipment"})
        await monitoring_service.record_metric("tool_executions", 1.0, {"tool_name": "get_orders", "agent": "operations"})
        await monitoring_service.record_metric("tool_executions", 1.0, {"tool_name": "get_safety", "agent": "safety"})
        
        # Filter by tool name
        inventory_metrics = await monitoring_service.get_metrics("tool_executions", tags={"tool_name": "get_inventory"})
        assert len(inventory_metrics) > 0, "Should filter by tool name"
        
        # Filter by agent
        equipment_metrics = await monitoring_service.get_metrics("tool_executions", tags={"agent": "equipment"})
        assert len(equipment_metrics) > 0, "Should filter by agent"

    async def test_metrics_time_range(self, monitoring_service):
        """Test metrics filtering by time range."""
        
        # Record metrics at different times
        now = datetime.utcnow()
        one_hour_ago = now - timedelta(hours=1)
        two_hours_ago = now - timedelta(hours=2)
        
        # Mock time for testing
        with patch('chain_server.services.mcp.monitoring.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value = two_hours_ago
            await monitoring_service.record_metric("old_metric", 1.0, {})
            
            mock_datetime.utcnow.return_value = one_hour_ago
            await monitoring_service.record_metric("recent_metric", 1.0, {})
            
            mock_datetime.utcnow.return_value = now
            await monitoring_service.record_metric("current_metric", 1.0, {})
        
        # Filter by time range
        recent_metrics = await monitoring_service.get_metrics("recent_metric", time_range=(one_hour_ago, now))
        assert len(recent_metrics) > 0, "Should filter by time range"

    async def test_metrics_retention(self, monitoring_service):
        """Test metrics retention policy."""
        
        # Record many metrics
        for i in range(1000):
            await monitoring_service.record_metric("test_metric", float(i), {"index": str(i)})
        
        # Check retention
        metrics = await monitoring_service.get_metrics("test_metric")
        assert len(metrics) > 0, "Should retain some metrics"
        
        # In a real implementation, you would test that old metrics are purged
        # based on the retention policy

    async def test_metrics_performance(self, monitoring_service):
        """Test metrics recording performance."""
        
        # Test high-frequency metrics recording
        start_time = time.time()
        
        for i in range(10000):
            await monitoring_service.record_metric("performance_test", float(i), {"iteration": str(i)})
        
        end_time = time.time()
        recording_time = end_time - start_time
        throughput = 10000 / recording_time
        
        print(f"Metrics Recording Performance - Time: {recording_time:.3f}s, Throughput: {throughput:.2f} metrics/sec")
        
        # Assertions
        assert throughput > 1000, f"Should record metrics quickly: {throughput:.2f} metrics/sec"


class TestMCPHealthMonitoring:
    """Test MCP health monitoring and alerting."""

    @pytest.fixture
    async def monitoring_service(self):
        """Create monitoring service for testing."""
        config = MonitoringConfig(
            metrics_retention_days=1,
            alert_thresholds={
                "error_rate": 0.1,
                "response_time": 5.0,
                "memory_usage": 0.8
            }
        )
        monitoring = MCPMonitoringService(config)
        await monitoring.start_monitoring()
        yield monitoring
        await monitoring.stop_monitoring()

    async def test_health_check_monitoring(self, monitoring_service, mcp_server, mcp_client):
        """Test health check monitoring."""
        
        # Connect client
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Record health metrics
        await monitoring_service.record_metric("health_check", 1.0, {"service": "mcp_server", "status": "healthy"})
        await monitoring_service.record_metric("health_check", 1.0, {"service": "mcp_client", "status": "healthy"})
        
        # Get health metrics
        health_metrics = await monitoring_service.get_metrics("health_check")
        assert len(health_metrics) > 0, "Should record health check metrics"
        
        # Check health status
        dashboard = await monitoring_service.get_monitoring_dashboard()
        assert "system_health" in dashboard, "Should include system health in dashboard"

    async def test_alert_threshold_monitoring(self, monitoring_service):
        """Test alert threshold monitoring."""
        
        # Record metrics that exceed thresholds
        await monitoring_service.record_metric("error_rate", 0.15, {"service": "mcp_server"})  # Exceeds 0.1 threshold
        await monitoring_service.record_metric("response_time", 6.0, {"endpoint": "api"})  # Exceeds 5.0 threshold
        await monitoring_service.record_metric("memory_usage", 0.9, {"component": "mcp_server"})  # Exceeds 0.8 threshold
        
        # Check alert generation
        dashboard = await monitoring_service.get_monitoring_dashboard()
        assert "alerts" in dashboard, "Should generate alerts for threshold breaches"
        
        # Verify alert content
        alerts = dashboard.get("alerts", [])
        assert len(alerts) > 0, "Should have alerts for threshold breaches"

    async def test_service_health_monitoring(self, monitoring_service, mcp_server, mcp_client):
        """Test service health monitoring."""
        
        # Record service health metrics
        await monitoring_service.record_metric("service_health", 1.0, {"service": "mcp_server", "status": "healthy"})
        await monitoring_service.record_metric("service_health", 1.0, {"service": "mcp_client", "status": "healthy"})
        await monitoring_service.record_metric("service_health", 0.0, {"service": "database", "status": "unhealthy"})
        
        # Get service health
        health_metrics = await monitoring_service.get_metrics("service_health")
        assert len(health_metrics) > 0, "Should record service health metrics"
        
        # Check service status
        dashboard = await monitoring_service.get_monitoring_dashboard()
        assert "active_services" in dashboard, "Should track active services"

    async def test_resource_monitoring(self, monitoring_service):
        """Test resource monitoring."""
        
        # Record resource metrics
        await monitoring_service.record_metric("cpu_usage", 0.5, {"component": "mcp_server"})
        await monitoring_service.record_metric("memory_usage", 0.6, {"component": "mcp_server"})
        await monitoring_service.record_metric("disk_usage", 0.3, {"component": "mcp_server"})
        await monitoring_service.record_metric("network_usage", 0.4, {"component": "mcp_server"})
        
        # Get resource metrics
        cpu_metrics = await monitoring_service.get_metrics("cpu_usage")
        memory_metrics = await monitoring_service.get_metrics("memory_usage")
        disk_metrics = await monitoring_service.get_metrics("disk_usage")
        network_metrics = await monitoring_service.get_metrics("network_usage")
        
        # Verify resource monitoring
        assert len(cpu_metrics) > 0, "Should monitor CPU usage"
        assert len(memory_metrics) > 0, "Should monitor memory usage"
        assert len(disk_metrics) > 0, "Should monitor disk usage"
        assert len(network_metrics) > 0, "Should monitor network usage"

    async def test_alert_escalation(self, monitoring_service):
        """Test alert escalation."""
        
        # Record escalating error rates
        await monitoring_service.record_metric("error_rate", 0.05, {"service": "mcp_server"})  # Normal
        await monitoring_service.record_metric("error_rate", 0.12, {"service": "mcp_server"})  # Warning
        await monitoring_service.record_metric("error_rate", 0.25, {"service": "mcp_server"})  # Critical
        
        # Check alert escalation
        dashboard = await monitoring_service.get_monitoring_dashboard()
        assert "alerts" in dashboard, "Should generate alerts"
        
        # Verify escalation levels
        alerts = dashboard.get("alerts", [])
        critical_alerts = [alert for alert in alerts if alert.get("severity") == "critical"]
        assert len(critical_alerts) > 0, "Should escalate to critical alerts"

    async def test_health_recovery_monitoring(self, monitoring_service):
        """Test health recovery monitoring."""
        
        # Record service going down and recovering
        await monitoring_service.record_metric("service_health", 0.0, {"service": "mcp_server", "status": "down"})
        await monitoring_service.record_metric("service_health", 0.0, {"service": "mcp_server", "status": "down"})
        await monitoring_service.record_metric("service_health", 1.0, {"service": "mcp_server", "status": "healthy"})
        
        # Check recovery detection
        dashboard = await monitoring_service.get_monitoring_dashboard()
        assert "system_health" in dashboard, "Should detect service recovery"


class TestMCPLoggingIntegration:
    """Test MCP logging and audit trail integration."""

    @pytest.fixture
    async def monitoring_service(self):
        """Create monitoring service for testing."""
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

    async def test_audit_trail_logging(self, monitoring_service, mcp_server, mcp_client):
        """Test audit trail logging."""
        
        # Connect client
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Execute operations to generate audit trail
        await mcp_client.execute_tool("get_inventory", {"item_id": "ITEM001"})
        await mcp_client.execute_tool("get_inventory", {"item_id": "ITEM002"})
        
        # Record audit events
        await monitoring_service.record_metric("audit_event", 1.0, {
            "event_type": "tool_execution",
            "user_id": "user_001",
            "tool_name": "get_inventory",
            "parameters": {"item_id": "ITEM001"},
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Get audit trail
        audit_metrics = await monitoring_service.get_metrics("audit_event")
        assert len(audit_metrics) > 0, "Should record audit events"

    async def test_security_event_logging(self, monitoring_service):
        """Test security event logging."""
        
        # Record security events
        await monitoring_service.record_metric("security_event", 1.0, {
            "event_type": "authentication_failure",
            "user_id": "user_001",
            "ip_address": "192.168.1.100",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        await monitoring_service.record_metric("security_event", 1.0, {
            "event_type": "authorization_denied",
            "user_id": "user_002",
            "resource": "admin_tool",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Get security events
        security_metrics = await monitoring_service.get_metrics("security_event")
        assert len(security_metrics) > 0, "Should record security events"

    async def test_error_logging(self, monitoring_service):
        """Test error logging."""
        
        # Record various errors
        await monitoring_service.record_metric("error_log", 1.0, {
            "error_type": "validation_error",
            "error_message": "Invalid parameter",
            "component": "tool_validation",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        await monitoring_service.record_metric("error_log", 1.0, {
            "error_type": "connection_error",
            "error_message": "Connection timeout",
            "component": "mcp_client",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Get error logs
        error_metrics = await monitoring_service.get_metrics("error_log")
        assert len(error_metrics) > 0, "Should record error logs"

    async def test_performance_logging(self, monitoring_service):
        """Test performance logging."""
        
        # Record performance metrics
        await monitoring_service.record_metric("performance_log", 1.0, {
            "operation": "tool_execution",
            "duration": 0.5,
            "tool_name": "get_inventory",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        await monitoring_service.record_metric("performance_log", 1.0, {
            "operation": "tool_discovery",
            "duration": 0.1,
            "tools_found": 10,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Get performance logs
        performance_metrics = await monitoring_service.get_metrics("performance_log")
        assert len(performance_metrics) > 0, "Should record performance logs"

    async def test_structured_logging(self, monitoring_service):
        """Test structured logging format."""
        
        # Record structured log entry
        log_entry = {
            "level": "INFO",
            "message": "Tool execution completed",
            "component": "mcp_server",
            "tool_name": "get_inventory",
            "execution_time": 0.5,
            "user_id": "user_001",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await monitoring_service.record_metric("structured_log", 1.0, log_entry)
        
        # Get structured logs
        log_metrics = await monitoring_service.get_metrics("structured_log")
        assert len(log_metrics) > 0, "Should record structured logs"
        
        # Verify log structure
        log_data = log_metrics[0].data
        assert "level" in log_data, "Should include log level"
        assert "message" in log_data, "Should include log message"
        assert "component" in log_data, "Should include component"

    async def test_log_aggregation(self, monitoring_service):
        """Test log aggregation and analysis."""
        
        # Record many log entries
        for i in range(100):
            await monitoring_service.record_metric("log_entry", 1.0, {
                "level": "INFO" if i % 10 != 0 else "ERROR",
                "component": f"component_{i % 5}",
                "message": f"Log message {i}",
                "timestamp": datetime.utcnow().isoformat()
            })
        
        # Get aggregated logs
        log_metrics = await monitoring_service.get_metrics("log_entry")
        assert len(log_metrics) > 0, "Should aggregate log entries"
        
        # Analyze log levels
        error_logs = [log for log in log_metrics if log.data.get("level") == "ERROR"]
        info_logs = [log for log in log_metrics if log.data.get("level") == "INFO"]
        
        assert len(error_logs) > 0, "Should have error logs"
        assert len(info_logs) > 0, "Should have info logs"


class TestMCPPerformanceMonitoring:
    """Test MCP performance monitoring."""

    @pytest.fixture
    async def monitoring_service(self):
        """Create monitoring service for testing."""
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

    async def test_response_time_monitoring(self, monitoring_service, mcp_server, mcp_client):
        """Test response time monitoring."""
        
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Execute operations and record response times
        for i in range(50):
            start_time = time.time()
            result = await mcp_client.execute_tool("get_inventory", {"item_id": f"ITEM{i:03d}"})
            end_time = time.time()
            
            if result.success:
                response_time = end_time - start_time
                await monitoring_service.record_metric("response_time", response_time, {
                    "endpoint": "tool_execution",
                    "tool_name": "get_inventory"
                })
        
        # Get response time metrics
        response_times = await monitoring_service.get_metrics("response_time")
        assert len(response_times) > 0, "Should record response times"
        
        # Calculate statistics
        times = [metric.value for metric in response_times]
        avg_time = sum(times) / len(times)
        max_time = max(times)
        
        print(f"Response Time Monitoring - Avg: {avg_time:.3f}s, Max: {max_time:.3f}s")
        
        # Assertions
        assert avg_time < 1.0, f"Average response time should be reasonable: {avg_time:.3f}s"
        assert max_time < 2.0, f"Maximum response time should be reasonable: {max_time:.3f}s"

    async def test_throughput_monitoring(self, monitoring_service, mcp_server, mcp_client):
        """Test throughput monitoring."""
        
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Record throughput over time
        start_time = time.time()
        operations_completed = 0
        
        for batch in range(10):
            batch_start = time.time()
            
            # Execute batch of operations
            tasks = []
            for i in range(10):
                task = mcp_client.execute_tool("get_inventory", {"item_id": f"ITEM{batch * 10 + i:03d}"})
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            batch_end = time.time()
            
            # Count successful operations
            successful = len([r for r in results if not isinstance(r, Exception) and r.success])
            operations_completed += successful
            
            # Record throughput
            batch_throughput = successful / (batch_end - batch_start)
            await monitoring_service.record_metric("throughput", batch_throughput, {
                "time_window": "batch",
                "batch_number": str(batch)
            })
        
        total_time = time.time() - start_time
        overall_throughput = operations_completed / total_time
        
        # Record overall throughput
        await monitoring_service.record_metric("overall_throughput", overall_throughput, {
            "time_window": "total",
            "operations": str(operations_completed)
        })
        
        # Get throughput metrics
        throughput_metrics = await monitoring_service.get_metrics("throughput")
        overall_metrics = await monitoring_service.get_metrics("overall_throughput")
        
        assert len(throughput_metrics) > 0, "Should record batch throughput"
        assert len(overall_metrics) > 0, "Should record overall throughput"
        
        print(f"Throughput Monitoring - Overall: {overall_throughput:.2f} ops/sec")

    async def test_resource_utilization_monitoring(self, monitoring_service):
        """Test resource utilization monitoring."""
        
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        
        # Monitor resource utilization
        for i in range(20):
            # Record CPU usage
            cpu_percent = process.cpu_percent()
            await monitoring_service.record_metric("cpu_usage", cpu_percent, {
                "component": "mcp_server",
                "measurement": str(i)
            })
            
            # Record memory usage
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            await monitoring_service.record_metric("memory_usage", memory_mb, {
                "component": "mcp_server",
                "measurement": str(i)
            })
            
            # Wait between measurements
            await asyncio.sleep(0.1)
        
        # Get resource metrics
        cpu_metrics = await monitoring_service.get_metrics("cpu_usage")
        memory_metrics = await monitoring_service.get_metrics("memory_usage")
        
        assert len(cpu_metrics) > 0, "Should monitor CPU usage"
        assert len(memory_metrics) > 0, "Should monitor memory usage"
        
        # Calculate resource statistics
        cpu_values = [metric.value for metric in cpu_metrics]
        memory_values = [metric.value for metric in memory_metrics]
        
        avg_cpu = sum(cpu_values) / len(cpu_values)
        avg_memory = sum(memory_values) / len(memory_values)
        
        print(f"Resource Monitoring - Avg CPU: {avg_cpu:.1f}%, Avg Memory: {avg_memory:.1f}MB")

    async def test_error_rate_monitoring(self, monitoring_service, mcp_server, mcp_client):
        """Test error rate monitoring."""
        
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Execute operations with some failures
        total_operations = 100
        successful_operations = 0
        failed_operations = 0
        
        for i in range(total_operations):
            try:
                result = await mcp_client.execute_tool("get_inventory", {"item_id": f"ITEM{i:03d}"})
                if result.success:
                    successful_operations += 1
                else:
                    failed_operations += 1
            except Exception:
                failed_operations += 1
        
        # Calculate error rate
        error_rate = failed_operations / total_operations
        
        # Record error rate
        await monitoring_service.record_metric("error_rate", error_rate, {
            "service": "mcp_server",
            "time_window": "test"
        })
        
        # Get error rate metrics
        error_rate_metrics = await monitoring_service.get_metrics("error_rate")
        assert len(error_rate_metrics) > 0, "Should record error rate"
        
        print(f"Error Rate Monitoring - Rate: {error_rate:.2%}")

    async def test_concurrent_operations_monitoring(self, monitoring_service, mcp_server, mcp_client):
        """Test concurrent operations monitoring."""
        
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Execute concurrent operations
        concurrency_levels = [1, 5, 10, 20]
        
        for concurrency in concurrency_levels:
            start_time = time.time()
            
            # Create concurrent tasks
            tasks = []
            for i in range(concurrency):
                task = mcp_client.execute_tool("get_inventory", {"item_id": f"ITEM{i:03d}"})
                tasks.append(task)
            
            # Execute concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            end_time = time.time()
            execution_time = end_time - start_time
            
            # Count successful operations
            successful = len([r for r in results if not isinstance(r, Exception) and r.success])
            success_rate = successful / concurrency
            
            # Record concurrency metrics
            await monitoring_service.record_metric("concurrent_operations", successful, {
                "concurrency_level": str(concurrency),
                "success_rate": str(success_rate),
                "execution_time": str(execution_time)
            })
        
        # Get concurrency metrics
        concurrency_metrics = await monitoring_service.get_metrics("concurrent_operations")
        assert len(concurrency_metrics) > 0, "Should monitor concurrent operations"
        
        print(f"Concurrent Operations Monitoring - Levels tested: {concurrency_levels}")


class TestMCPSystemDiagnostics:
    """Test MCP system diagnostics and troubleshooting."""

    @pytest.fixture
    async def monitoring_service(self):
        """Create monitoring service for testing."""
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

    async def test_system_health_dashboard(self, monitoring_service, mcp_server, mcp_client):
        """Test system health dashboard."""
        
        # Connect client
        await mcp_client.connect("http://localhost:8000", MCPConnectionType.HTTP)
        
        # Record various metrics
        await monitoring_service.record_metric("system_health", 1.0, {"component": "mcp_server"})
        await monitoring_service.record_metric("system_health", 1.0, {"component": "mcp_client"})
        await monitoring_service.record_metric("active_connections", 1.0, {"service": "mcp_server"})
        await monitoring_service.record_metric("tool_executions", 10.0, {"tool_name": "get_inventory"})
        
        # Get system health dashboard
        dashboard = await monitoring_service.get_monitoring_dashboard()
        
        # Verify dashboard content
        assert "system_health" in dashboard, "Should include system health"
        assert "active_services" in dashboard, "Should include active services"
        assert "metrics_summary" in dashboard, "Should include metrics summary"

    async def test_diagnostic_metrics(self, monitoring_service):
        """Test diagnostic metrics collection."""
        
        # Record diagnostic metrics
        await monitoring_service.record_metric("diagnostic", 1.0, {
            "check_type": "connectivity",
            "status": "healthy",
            "component": "database"
        })
        
        await monitoring_service.record_metric("diagnostic", 1.0, {
            "check_type": "memory",
            "status": "healthy",
            "component": "mcp_server"
        })
        
        await monitoring_service.record_metric("diagnostic", 0.0, {
            "check_type": "disk_space",
            "status": "warning",
            "component": "storage"
        })
        
        # Get diagnostic metrics
        diagnostic_metrics = await monitoring_service.get_metrics("diagnostic")
        assert len(diagnostic_metrics) > 0, "Should collect diagnostic metrics"
        
        # Analyze diagnostic status
        healthy_checks = [m for m in diagnostic_metrics if m.data.get("status") == "healthy"]
        warning_checks = [m for m in diagnostic_metrics if m.data.get("status") == "warning"]
        
        assert len(healthy_checks) > 0, "Should have healthy diagnostic checks"
        assert len(warning_checks) > 0, "Should have warning diagnostic checks"

    async def test_troubleshooting_metrics(self, monitoring_service):
        """Test troubleshooting metrics."""
        
        # Record troubleshooting metrics
        await monitoring_service.record_metric("troubleshooting", 1.0, {
            "issue_type": "slow_response",
            "root_cause": "database_latency",
            "resolution": "connection_pool_tuning"
        })
        
        await monitoring_service.record_metric("troubleshooting", 1.0, {
            "issue_type": "memory_leak",
            "root_cause": "unclosed_connections",
            "resolution": "connection_cleanup"
        })
        
        # Get troubleshooting metrics
        troubleshooting_metrics = await monitoring_service.get_metrics("troubleshooting")
        assert len(troubleshooting_metrics) > 0, "Should collect troubleshooting metrics"

    async def test_performance_bottleneck_detection(self, monitoring_service):
        """Test performance bottleneck detection."""
        
        # Record performance metrics that indicate bottlenecks
        await monitoring_service.record_metric("bottleneck_detection", 1.0, {
            "bottleneck_type": "cpu_bound",
            "severity": "high",
            "component": "tool_execution"
        })
        
        await monitoring_service.record_metric("bottleneck_detection", 1.0, {
            "bottleneck_type": "memory_bound",
            "severity": "medium",
            "component": "data_processing"
        })
        
        # Get bottleneck metrics
        bottleneck_metrics = await monitoring_service.get_metrics("bottleneck_detection")
        assert len(bottleneck_metrics) > 0, "Should detect performance bottlenecks"

    async def test_system_capacity_monitoring(self, monitoring_service):
        """Test system capacity monitoring."""
        
        # Record capacity metrics
        await monitoring_service.record_metric("capacity_usage", 0.6, {
            "resource_type": "cpu",
            "current_usage": 60.0,
            "max_capacity": 100.0
        })
        
        await monitoring_service.record_metric("capacity_usage", 0.8, {
            "resource_type": "memory",
            "current_usage": 800.0,
            "max_capacity": 1000.0
        })
        
        # Get capacity metrics
        capacity_metrics = await monitoring_service.get_metrics("capacity_usage")
        assert len(capacity_metrics) > 0, "Should monitor system capacity"
        
        # Check capacity thresholds
        high_usage = [m for m in capacity_metrics if m.value > 0.7]
        assert len(high_usage) > 0, "Should detect high capacity usage"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
