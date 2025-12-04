"""
MCP Monitoring, Logging, and Management

This module provides comprehensive monitoring, logging, and management capabilities
for the MCP system, including metrics collection, alerting, and system management.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Union, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json
import uuid
import time
from collections import defaultdict, deque

from .service_discovery import ServiceRegistry, ServiceInfo, ServiceHealth
from .tool_discovery import ToolDiscoveryService, DiscoveredTool

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Metric type enumeration."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


class AlertSeverity(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class LogLevel(Enum):
    """Log level enumeration."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Metric:
    """Metric data structure."""

    name: str
    value: float
    metric_type: MetricType
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    description: str = ""


@dataclass
class Alert:
    """Alert data structure."""

    alert_id: str
    name: str
    description: str
    severity: AlertSeverity
    source: str
    metric_name: str
    threshold: float
    current_value: float
    triggered_at: datetime = field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    status: str = "active"  # active, resolved, acknowledged


@dataclass
class LogEntry:
    """Log entry data structure."""

    log_id: str
    level: LogLevel
    message: str
    source: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    trace_id: Optional[str] = None


@dataclass
class SystemHealth:
    """System health information."""

    overall_status: str  # healthy, degraded, unhealthy
    services_healthy: int
    services_total: int
    tools_available: int
    active_connections: int
    memory_usage: float
    cpu_usage: float
    last_updated: datetime = field(default_factory=datetime.utcnow)


class MetricsCollector:
    """
    Metrics collection and management.

    This collector provides:
    - Metric collection and storage
    - Metric aggregation and calculation
    - Metric export and reporting
    - Performance monitoring
    """

    def __init__(self, retention_days: int = 30):
        self.retention_days = retention_days
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10000))
        self.counters: Dict[str, float] = defaultdict(float)
        self.gauges: Dict[str, float] = defaultdict(float)
        self.histograms: Dict[str, List[float]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._cleanup_task = None
        self._running = False

    async def start(self) -> None:
        """Start metrics collection."""
        if self._running:
            return

        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Metrics collector started")

    async def stop(self) -> None:
        """Stop metrics collection."""
        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info("Metrics collector stopped")

    async def record_metric(
        self,
        name: str,
        value: float,
        metric_type: MetricType,
        labels: Dict[str, str] = None,
        description: str = "",
    ) -> None:
        """Record a metric."""
        async with self._lock:
            metric = Metric(
                name=name,
                value=value,
                metric_type=metric_type,
                labels=labels or {},
                description=description,
            )

            metric_key = f"{name}:{json.dumps(labels or {}, sort_keys=True)}"
            self.metrics[metric_key].append(metric)

            # Update aggregated metrics
            if metric_type == MetricType.COUNTER:
                self.counters[metric_key] += value
            elif metric_type == MetricType.GAUGE:
                self.gauges[metric_key] = value
            elif metric_type == MetricType.HISTOGRAM:
                self.histograms[metric_key].append(value)

    async def get_metric(
        self, name: str, labels: Dict[str, str] = None
    ) -> Optional[Metric]:
        """Get latest metric value."""
        async with self._lock:
            metric_key = f"{name}:{json.dumps(labels or {}, sort_keys=True)}"
            metrics = self.metrics.get(metric_key)
            return metrics[-1] if metrics else None

    async def get_metric_summary(
        self, name: str, labels: Dict[str, str] = None
    ) -> Dict[str, Any]:
        """Get metric summary statistics."""
        async with self._lock:
            metric_key = f"{name}:{json.dumps(labels or {}, sort_keys=True)}"
            metrics = self.metrics.get(metric_key)

            if not metrics:
                return {}

            values = [m.value for m in metrics]

            return {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "avg": sum(values) / len(values),
                "latest": values[-1],
                "first_seen": metrics[0].timestamp.isoformat(),
                "last_seen": metrics[-1].timestamp.isoformat(),
            }

    async def get_metrics_by_name(
        self, name: str, labels: Dict[str, str] = None
    ) -> List[Metric]:
        """
        Get all metrics with a given name, optionally filtered by labels.
        
        If labels is None, returns all metrics with the given name regardless of labels.
        If labels is provided, returns only metrics matching those exact labels.
        """
        async with self._lock:
            if labels is None:
                # Return all metrics with this name, regardless of labels
                all_matching = []
                for metric_key, metrics_list in self.metrics.items():
                    if metric_key.startswith(f"{name}:"):
                        all_matching.extend(list(metrics_list))
                return all_matching
            else:
                # Return metrics matching exact labels
                metric_key = f"{name}:{json.dumps(labels, sort_keys=True)}"
                metrics = self.metrics.get(metric_key)
                return list(metrics) if metrics else []

    async def get_all_metrics(self) -> Dict[str, List[Metric]]:
        """Get all metrics."""
        async with self._lock:
            return {key: list(metrics) for key, metrics in self.metrics.items()}

    async def export_metrics(self, format: str = "json") -> str:
        """Export metrics in specified format."""
        async with self._lock:
            if format == "json":
                return json.dumps(
                    {
                        "metrics": {
                            key: [
                                {
                                    "name": m.name,
                                    "value": m.value,
                                    "type": m.metric_type.value,
                                    "labels": m.labels,
                                    "timestamp": m.timestamp.isoformat(),
                                }
                                for m in metrics
                            ]
                            for key, metrics in self.metrics.items()
                        }
                    },
                    indent=2,
                )
            else:
                # Prometheus format
                lines = []
                for key, metrics in self.metrics.items():
                    if not metrics:
                        continue

                    latest = metrics[-1]
                    labels_str = ",".join(
                        [f'{k}="{v}"' for k, v in latest.labels.items()]
                    )
                    lines.append(
                        f"{latest.name}{{{labels_str}}} {latest.value} {int(latest.timestamp.timestamp())}"
                    )

                return "\n".join(lines)

    async def _cleanup_loop(self) -> None:
        """Cleanup old metrics."""
        while self._running:
            try:
                await asyncio.sleep(3600)  # Run every hour
                if self._running:
                    await self._cleanup_old_metrics()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in metrics cleanup: {e}")

    async def _cleanup_old_metrics(self) -> None:
        """Remove old metrics."""
        cutoff_time = datetime.utcnow() - timedelta(days=self.retention_days)

        async with self._lock:
            for key, metrics in self.metrics.items():
                # Remove old metrics
                while metrics and metrics[0].timestamp < cutoff_time:
                    metrics.popleft()


class AlertManager:
    """
    Alert management and notification.

    This manager provides:
    - Alert rule definition and management
    - Alert triggering and resolution
    - Alert notification and escalation
    - Alert history and reporting
    """

    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics_collector = metrics_collector
        self.alerts: Dict[str, Alert] = {}
        self.alert_rules: Dict[str, Dict[str, Any]] = {}
        self.notification_callbacks: List[Callable] = []
        self._lock = asyncio.Lock()
        self._check_task = None
        self._running = False

    async def start(self) -> None:
        """Start alert management."""
        if self._running:
            return

        self._running = True
        self._check_task = asyncio.create_task(self._alert_check_loop())
        logger.info("Alert manager started")

    async def stop(self) -> None:
        """Stop alert management."""
        self._running = False

        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass

        logger.info("Alert manager stopped")

    async def add_alert_rule(
        self,
        rule_name: str,
        metric_name: str,
        threshold: float,
        operator: str,  # >, <, >=, <=, ==, !=
        severity: AlertSeverity,
        description: str = "",
    ) -> None:
        """Add an alert rule."""
        async with self._lock:
            self.alert_rules[rule_name] = {
                "metric_name": metric_name,
                "threshold": threshold,
                "operator": operator,
                "severity": severity,
                "description": description,
            }

    async def remove_alert_rule(self, rule_name: str) -> bool:
        """Remove an alert rule."""
        async with self._lock:
            if rule_name in self.alert_rules:
                del self.alert_rules[rule_name]
                return True
            return False

    async def add_notification_callback(self, callback: Callable) -> None:
        """Add notification callback."""
        self.notification_callbacks.append(callback)

    async def get_active_alerts(self) -> List[Alert]:
        """Get active alerts."""
        async with self._lock:
            return [alert for alert in self.alerts.values() if alert.status == "active"]

    async def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        async with self._lock:
            if alert_id in self.alerts:
                self.alerts[alert_id].status = "acknowledged"
                return True
            return False

    async def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an alert."""
        async with self._lock:
            if alert_id in self.alerts:
                alert = self.alerts[alert_id]
                alert.status = "resolved"
                alert.resolved_at = datetime.utcnow()
                return True
            return False

    async def _alert_check_loop(self) -> None:
        """Alert checking loop."""
        while self._running:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                if self._running:
                    await self._check_alerts()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in alert check loop: {e}")

    async def _check_alerts(self) -> None:
        """Check all alert rules."""
        for rule_name, rule in self.alert_rules.items():
            try:
                metric = await self.metrics_collector.get_metric(rule["metric_name"])
                if not metric:
                    continue

                triggered = self._evaluate_condition(
                    metric.value, rule["threshold"], rule["operator"]
                )

                if triggered:
                    await self._trigger_alert(rule_name, rule, metric)
                else:
                    await self._resolve_alert_if_exists(rule_name)

            except Exception as e:
                logger.error(f"Error checking alert rule {rule_name}: {e}")

    def _evaluate_condition(
        self, value: float, threshold: float, operator: str
    ) -> bool:
        """Evaluate alert condition."""
        if operator == ">":
            return value > threshold
        elif operator == "<":
            return value < threshold
        elif operator == ">=":
            return value >= threshold
        elif operator == "<=":
            return value <= threshold
        elif operator == "==":
            return value == threshold
        elif operator == "!=":
            return value != threshold
        else:
            return False

    async def _trigger_alert(
        self, rule_name: str, rule: Dict[str, Any], metric: Metric
    ) -> None:
        """Trigger an alert."""
        alert_id = f"{rule_name}_{int(time.time())}"

        # Check if alert already exists
        existing_alert = None
        for alert in self.alerts.values():
            if alert.name == rule_name and alert.status == "active":
                existing_alert = alert
                break

        if existing_alert:
            return  # Alert already active

        alert = Alert(
            alert_id=alert_id,
            name=rule_name,
            description=rule["description"],
            severity=rule["severity"],
            source="mcp_monitoring",
            metric_name=rule["metric_name"],
            threshold=rule["threshold"],
            current_value=metric.value,
        )

        async with self._lock:
            self.alerts[alert_id] = alert

        # Send notifications
        await self._send_notifications(alert)

        logger.warning(
            f"Alert triggered: {rule_name} - {metric.value} {rule['operator']} {rule['threshold']}"
        )

    async def _resolve_alert_if_exists(self, rule_name: str) -> None:
        """Resolve alert if it exists and condition is no longer met."""
        for alert in self.alerts.values():
            if alert.name == rule_name and alert.status == "active":
                await self.resolve_alert(alert.alert_id)
                logger.info(f"Alert resolved: {rule_name}")
                break

    async def _send_notifications(self, alert: Alert) -> None:
        """Send alert notifications."""
        for callback in self.notification_callbacks:
            try:
                await callback(alert)
            except Exception as e:
                logger.error(f"Error sending notification: {e}")


class SystemLogger:
    """
    System logging and log management.

    This logger provides:
    - Structured logging
    - Log aggregation and filtering
    - Log export and analysis
    - Performance logging
    """

    def __init__(self, retention_days: int = 30):
        self.retention_days = retention_days
        self.logs: deque = deque(maxlen=100000)
        self._lock = asyncio.Lock()
        self._cleanup_task = None
        self._running = False

    async def start(self) -> None:
        """Start system logging."""
        if self._running:
            return

        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("System logger started")

    async def stop(self) -> None:
        """Stop system logging."""
        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info("System logger stopped")

    async def log(
        self,
        level: LogLevel,
        message: str,
        source: str,
        metadata: Dict[str, Any] = None,
        trace_id: str = None,
    ) -> str:
        """Log a message."""
        log_id = str(uuid.uuid4())

        log_entry = LogEntry(
            log_id=log_id,
            level=level,
            message=message,
            source=source,
            metadata=metadata or {},
            trace_id=trace_id,
        )

        async with self._lock:
            self.logs.append(log_entry)

        # Also log to standard logger
        getattr(logger, level.value)(f"[{source}] {message}")

        return log_id

    async def get_logs(
        self,
        level: LogLevel = None,
        source: str = None,
        start_time: datetime = None,
        end_time: datetime = None,
        limit: int = 1000,
    ) -> List[LogEntry]:
        """Get logs with filters."""
        async with self._lock:
            filtered_logs = []

            for log_entry in reversed(self.logs):  # Most recent first
                if limit and len(filtered_logs) >= limit:
                    break

                # Apply filters
                if level and log_entry.level != level:
                    continue

                if source and log_entry.source != source:
                    continue

                if start_time and log_entry.timestamp < start_time:
                    continue

                if end_time and log_entry.timestamp > end_time:
                    continue

                filtered_logs.append(log_entry)

            return filtered_logs

    async def export_logs(self, format: str = "json") -> str:
        """Export logs in specified format."""
        async with self._lock:
            if format == "json":
                return json.dumps(
                    [
                        {
                            "log_id": log.log_id,
                            "level": log.level.value,
                            "message": log.message,
                            "source": log.source,
                            "timestamp": log.timestamp.isoformat(),
                            "metadata": log.metadata,
                            "trace_id": log.trace_id,
                        }
                        for log in self.logs
                    ],
                    indent=2,
                )
            else:
                # Plain text format
                lines = []
                for log in self.logs:
                    lines.append(
                        f"{log.timestamp.isoformat()} [{log.level.value.upper()}] [{log.source}] {log.message}"
                    )

                return "\n".join(lines)

    async def _cleanup_loop(self) -> None:
        """Cleanup old logs."""
        while self._running:
            try:
                await asyncio.sleep(3600)  # Run every hour
                if self._running:
                    await self._cleanup_old_logs()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in log cleanup: {e}")

    async def _cleanup_old_logs(self) -> None:
        """Remove old logs."""
        cutoff_time = datetime.utcnow() - timedelta(days=self.retention_days)

        async with self._lock:
            # Remove old logs from the beginning of the deque
            while self.logs and self.logs[0].timestamp < cutoff_time:
                self.logs.popleft()


class MCPMonitoring:
    """
    Main MCP monitoring and management system.

    This system provides:
    - Comprehensive monitoring of MCP services
    - Metrics collection and analysis
    - Alert management and notification
    - System health monitoring
    - Log management and analysis
    """

    def __init__(
        self, service_registry: ServiceRegistry, tool_discovery: ToolDiscoveryService
    ):
        self.service_registry = service_registry
        self.tool_discovery = tool_discovery
        self.metrics_collector = MetricsCollector()
        self.alert_manager = AlertManager(self.metrics_collector)
        self.system_logger = SystemLogger()
        self._running = False

    async def start(self) -> None:
        """Start MCP monitoring system."""
        if self._running:
            return

        self._running = True

        # Start all components
        await self.metrics_collector.start()
        await self.alert_manager.start()
        await self.system_logger.start()

        # Set up default alert rules
        await self._setup_default_alert_rules()

        # Start monitoring tasks
        asyncio.create_task(self._monitoring_loop())

        logger.info("MCP monitoring system started")

    async def stop(self) -> None:
        """Stop MCP monitoring system."""
        self._running = False

        await self.metrics_collector.stop()
        await self.alert_manager.stop()
        await self.system_logger.stop()

        logger.info("MCP monitoring system stopped")

    async def get_system_health(self) -> SystemHealth:
        """Get overall system health."""
        services = await self.service_registry.get_all_services()
        healthy_services = sum(1 for s in services if s.status.value == "running")

        # Get tool count
        tools = self.tool_discovery.get_discovery_status()
        tools_available = tools.get("total_tools", 0)

        # Get system metrics
        memory_usage = await self._get_memory_usage()
        cpu_usage = await self._get_cpu_usage()

        # Determine overall status
        if healthy_services == len(services) and tools_available > 0:
            overall_status = "healthy"
        elif healthy_services > len(services) * 0.7:
            overall_status = "degraded"
        else:
            overall_status = "unhealthy"

        return SystemHealth(
            overall_status=overall_status,
            services_healthy=healthy_services,
            services_total=len(services),
            tools_available=tools_available,
            active_connections=0,  # Would be calculated from actual connections
            memory_usage=memory_usage,
            cpu_usage=cpu_usage,
        )

    async def get_monitoring_dashboard(self) -> Dict[str, Any]:
        """Get monitoring dashboard data."""
        health = await self.get_system_health()
        active_alerts = await self.alert_manager.get_active_alerts()
        recent_logs = await self.system_logger.get_logs(limit=100)

        return {
            "health": {
                "overall_status": health.overall_status,
                "services_healthy": health.services_healthy,
                "services_total": health.services_total,
                "tools_available": health.tools_available,
                "memory_usage": health.memory_usage,
                "cpu_usage": health.cpu_usage,
            },
            "alerts": {
                "active_count": len(active_alerts),
                "alerts": [
                    {
                        "id": alert.alert_id,
                        "name": alert.name,
                        "severity": alert.severity.value,
                        "description": alert.description,
                        "triggered_at": alert.triggered_at.isoformat(),
                    }
                    for alert in active_alerts
                ],
            },
            "logs": {
                "recent_count": len(recent_logs),
                "logs": [
                    {
                        "level": log.level.value,
                        "message": log.message,
                        "source": log.source,
                        "timestamp": log.timestamp.isoformat(),
                    }
                    for log in recent_logs[-10:]  # Last 10 logs
                ],
            },
        }

    async def _setup_default_alert_rules(self) -> None:
        """Set up default alert rules."""
        # Service health alerts
        await self.alert_manager.add_alert_rule(
            "service_down",
            "services_healthy",
            1,
            "<",
            AlertSeverity.CRITICAL,
            "One or more services are down",
        )

        # Memory usage alerts
        await self.alert_manager.add_alert_rule(
            "high_memory_usage",
            "memory_usage_percent",
            90,
            ">",
            AlertSeverity.WARNING,
            "High memory usage detected",
        )

        # CPU usage alerts
        await self.alert_manager.add_alert_rule(
            "high_cpu_usage",
            "cpu_usage_percent",
            90,
            ">",
            AlertSeverity.WARNING,
            "High CPU usage detected",
        )

    async def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await asyncio.sleep(60)  # Run every minute
                if self._running:
                    await self._collect_system_metrics()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")

    async def _collect_system_metrics(self) -> None:
        """Collect system metrics."""
        try:
            # Collect service metrics
            services = await self.service_registry.get_all_services()
            await self.metrics_collector.record_metric(
                "services_total", len(services), MetricType.GAUGE, {"type": "count"}
            )

            healthy_services = sum(1 for s in services if s.status.value == "running")
            await self.metrics_collector.record_metric(
                "services_healthy",
                healthy_services,
                MetricType.GAUGE,
                {"type": "count"},
            )

            # Collect tool metrics
            tool_stats = self.tool_discovery.get_tool_statistics()
            await self.metrics_collector.record_metric(
                "tools_available",
                tool_stats.get("total_tools", 0),
                MetricType.GAUGE,
                {"type": "count"},
            )

            # Collect system metrics
            memory_usage = await self._get_memory_usage()
            await self.metrics_collector.record_metric(
                "memory_usage_percent",
                memory_usage,
                MetricType.GAUGE,
                {"type": "system"},
            )

            cpu_usage = await self._get_cpu_usage()
            await self.metrics_collector.record_metric(
                "cpu_usage_percent", cpu_usage, MetricType.GAUGE, {"type": "system"}
            )

        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")

    async def _get_memory_usage(self) -> float:
        """Get memory usage percentage."""
        try:
            import psutil

            return psutil.virtual_memory().percent
        except ImportError:
            return 0.0
        except Exception:
            return 0.0

    async def _get_cpu_usage(self) -> float:
        """Get CPU usage percentage."""
        try:
            import psutil

            return psutil.cpu_percent()
        except ImportError:
            return 0.0
        except Exception:
            return 0.0
